import os, time, threading
from datetime import datetime, timezone, timedelta
import yfinance as yf
import requests
import pandas as pd
from flask import Flask

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")

# 12 Pairs - Locked, never change
PAIRS = {
    "GBPUSD": "GBPUSD=X",
    "GBPJPY": "GBPJPY=X",
    "EURUSD": "EURUSD=X",
    "XAUUSD": "GC=F",
    "US30": "^DJI",
    "NAS100": "^NDX",
    "USDJPY": "USDJPY=X",
    "USDCAD": "USDCAD=X",
    "BTCUSD": "BTC-USD",
    "AUDUSD": "AUDUSD=X",
    "NZDUSD": "NZDUSD=X",
    "EURJPY": "EURJPY=X",
}

# ================= KEEP ALIVE =================
app = Flask(__name__)
@app.route("/")
def home():
    return "KeedSweepBot LIVE - 24/7"

def keep_alive():
    port = int(os.environ.get("PORT", 10000))
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=port), daemon=True).start()
    print(f"Keep alive on {port}", flush=True)

# ================= TELEGRAM =================
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        print(f"Telegram sent: {msg[:60]}", flush=True)
    except Exception as e:
        print(f"Telegram error: {e}", flush=True)

# ================= DATA =================
def get_df(ticker, period, interval):
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=False)
        if df is None or len(df) < 5:
            return None
        try:
            df.columns = df.columns.get_level_values(0)
        except:
            pass
        return df
    except Exception as e:
        print(f"Data error {ticker} {interval}: {e}", flush=True)
        return None

def fmt(p, pair):
    # JPY / Indices / BTC need fewer decimals
    if "JPY" in pair or pair in ["US30", "NAS100"]:
        return round(float(p), 2)
    if pair == "BTCUSD":
        return round(float(p), 1)
    if pair == "XAUUSD":
        return round(float(p), 2)
    return round(float(p), 5)

# ================= STATE =================
# Prevents 2 signals same pair + same hour + same strategy
sent = set()  # (pair, hour_key, strategy)
# Locked H/L per pair per hour
locked_range = {}  # pair -> (hour_key, H, L)

def get_range(pair, ticker, hour_key):
    # If already locked this hour, return it - NEVER change mid-hour
    if pair in locked_range and locked_range[pair][0] == hour_key:
        return locked_range[pair][1], locked_range[pair][2]

    df1h = get_df(ticker, "2d", "1h")
    if df1h is None:
        return None, None
    # Previous 1H candle that just closed = [-1] if we are in new hour, [-2] if data lags
    # We use the last COMPLETED candle: the one before current forming hour
    # At XX:05, last closed is the XX:00 candle's previous. yfinance 1h last row is often the just-closed one.
    # So we take [-2] as the completed range candle to be safe, unless [-1] is fully closed.
    # Simplest reliable: [-2] is definitely closed.
    prev = df1h.iloc[-2]
    H = float(prev["High"]); L = float(prev["Low"])
    locked_range[pair] = (hour_key, H, L)
    print(f"{pair} New Range locked {hour_key} H={H} L={L}", flush=True)
    return H, L

# ================= STRATEGY 1 =================
def check_strategy1(pair, ticker, H, L, hour_key):
    # Only 00:00 - 00:15
    now = datetime.now(timezone.utc)
    if now.minute >= 15:
        return None
    if (pair, hour_key, "S1") in sent:
        return None

    df5 = get_df(ticker, "1d", "5m")
    if df5 is None:
        return None

    # Only the 3 x 5M candles of THIS hour, that are fully closed
    # Candle 1: :00-:05, Candle 2: :05-:10, Candle 3: :10-:15
    for idx, row in df5.iterrows():
        # idx is UTC time of candle open
        if idx.hour != now.hour or idx.date() != now.date():
            continue
        if idx.minute not in [0, 5, 10]:
            continue
        # Must be fully closed: candle end < now
        candle_end = idx + timedelta(minutes=5)
        if candle_end.tz_localize(None) > now.replace(tzinfo=None):
            continue  # still forming, NEVER use

        low = float(row["Low"]); high = float(row["High"]); close = float(row["Close"])

        # BUY: wick BELOW L, close back ABOVE L (inside)
        if low < L and close > L and close < H:
            return {"pair": pair, "strategy": "STRATEGY 1 - Sweep Low", "dir": "BUY 🟢",
                    "entry": close, "sl": low, "tp1": (H+L)/2, "tp2": H, "H": H, "L": L}
        # SELL: wick ABOVE H, close back BELOW H (inside)
        if high > H and close < H and close > L:
            return {"pair": pair, "strategy": "STRATEGY 1 - Sweep High", "dir": "SELL 🔴",
                    "entry": close, "sl": high, "tp1": (H+L)/2, "tp2": L, "H": H, "L": L}
    return None

# ================= STRATEGY 2 =================
def check_strategy2(pair, ticker, H, L, hour_key):
    # Only if Strategy 1 did NOT give signal this hour
    if (pair, hour_key, "S1") in sent:
        return None
    if (pair, hour_key, "S2") in sent:
        return None

    df1 = get_df(ticker, "1d", "1m")
    if df1 is None or len(df1) < 20:
        return None

    now = datetime.now(timezone.utc)
    # Only 1M candles of THIS hour, fully closed
    hour_df = df1[df1.index.hour == now.hour]
    hour_df = hour_df[hour_df.index.date == now.date()]
    if len(hour_df) < 10:
        return None

    tol = (H - L) * 0.15  # tap must be within 15% of range height from H/L

    # --- Double Bottom -> BUY ---
    # Find 2 lows near L
    lows = hour_df[hour_df["Low"] <= L + tol]
    if len(lows) >= 2:
        first = lows.iloc[0]; second = lows.iloc[-1]
        if second.name > first.name:  # second after first
            # Neckline = highest High between the two bottoms
            between = hour_df[(hour_df.index > first.name) & (hour_df.index < second.name)]
            if len(between) > 0:
                neck = float(between["High"].max())
                last = hour_df.iloc[-2]  # last CLOSED 1M candle
                last_close = float(last["Close"])
                if last_close > neck:  # break above neckline, closed
                    sl = float(lows["Low"].min())
                    return {"pair": pair, "strategy": "STRATEGY 2 - Double Bottom", "dir": "BUY 🟢",
                            "entry": last_close, "sl": sl, "tp1": (H+L)/2, "tp2": H, "H": H, "L": L}

    # --- Double Top -> SELL ---
    highs = hour_df[hour_df["High"] >= H - tol]
    if len(highs) >= 2:
        first = highs.iloc[0]; second = highs.iloc[-1]
        if second.name > first.name:
            between = hour_df[(hour_df.index > first.name) & (hour_df.index < second.name)]
            if len(between) > 0:
                neck = float(between["Low"].min())
                last = hour_df.iloc[-2]
                last_close = float(last["Close"])
                if last_close < neck:  # break below neckline, closed
                    sl = float(highs["High"].max())
                    return {"pair": pair, "strategy": "STRATEGY 2 - Double Top", "dir": "SELL 🔴",
                            "entry": last_close, "sl": sl, "tp1": (H+L)/2, "tp2": L, "H": H, "L": L}
    return None

# ================= SCAN =================
def scan_all(hour_key):
    for pair, ticker in PAIRS.items():
        try:
            H, L = get_range(pair, ticker, hour_key)
            if H is None:
                continue

            # Try Strategy 1 first (00-15)
            res = check_strategy1(pair, ticker, H, L, hour_key)
            strat_key = "S1"
            if res is None:
                # Strategy 2 backup (00-59) if S1 missed
                res = check_strategy2(pair, ticker, H, L, hour_key)
                strat_key = "S2"

            if res:
                sent.add((pair, hour_key, strat_key))
                msg = (
                    f"{res['dir'].split()[0]} *{pair}*\n"
                    f"{res['strategy']}\n"
                    f"Entry: {fmt(res['entry'], pair)}\n"
                    f"SL: {fmt(res['sl'], pair)}\n"
                    f"TP1: {fmt(res['tp1'], pair)} (Mid)\n"
                    f"TP2: {fmt(res['tp2'], pair)} (Opposite Line)\n"
                    f"Prev High: {fmt(res['H'], pair)} | Low: {fmt(res['L'], pair)}"
                )
                send_telegram(msg)
                print(f"SIGNAL {pair} {res['strategy']} {res['dir']}", flush=True)
            else:
                print(f"No setup: {pair} H={fmt(H,pair)} L={fmt(L,pair)}", flush=True)
        except Exception as e:
            print(f"Error {pair}: {e}", flush=True)

# ================= MAIN =================
def main():
    keep_alive()
    send_telegram("✅ *KeedSweepBot LIVE - 24/7*\n12 Pairs | 1H Range | S1: 5M Sweep 00-15 | S2: 1M Double Top/Bottom\nTP1 Mid | TP2 Opposite | No Sessions")
    print("Bot started 24/7", flush=True)
    while True:
        try:
            now = datetime.now(timezone.utc)
            hour_key = now.strftime("%Y-%m-%d-%H")
            print(f"--- Scan {hour_key} {now.strftime('%H:%M')} UTC ---", flush=True)
            scan_all(hour_key)
            time.sleep(60)  # Check every minute
        except Exception as e:
            print(f"Main error: {e}", flush=True)
            time.sleep(60)

if __name__ == "__main__":
    main()
