import os, time, threading, requests, traceback
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
from flask import Flask

app = Flask(__name__)
@app.route('/')
def home(): return "KeedSweepBot v3 LIVE - Locked + Range Filter"
@app.route('/health')
def health(): return "OK"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask, daemon=True).start()

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
print(f"TOKEN set: {bool(TOKEN)} CHAT_ID set: {bool(CHAT_ID)}", flush=True)

BROKER_TZ = ZoneInfo("Europe/Athens")

PAIRS = {
    "GBPUSD": "GBPUSD=X", "GBPJPY": "GBPJPY=X", "EURUSD": "EURUSD=X",
    "XAUUSD": "GC=F", "US30": "^DJI", "NAS100": "^IXIC",
    "USDJPY": "USDJPY=X", "USDCAD": "USDCAD=X", "BTCUSD": "BTC-USD",
    "AUDUSD": "AUDUSD=X", "NZDUSD": "NZDUSD=X", "EURJPY": "EURJPY=X",
}

PIP_SIZE = {
    "GBPUSD": 0.0001, "EURUSD": 0.0001, "AUDUSD": 0.0001, "NZDUSD": 0.0001,
    "USDCAD": 0.0001, "GBPJPY": 0.01, "USDJPY": 0.01, "EURJPY": 0.01,
    "XAUUSD": 0.1, "US30": 1.0, "NAS100": 1.0, "BTCUSD": 1.0,
}
MIN_RANGE_PIPS = {
    "GBPUSD": 8, "EURUSD": 8, "AUDUSD": 8, "NZDUSD": 8, "USDCAD": 8,
    "GBPJPY": 10, "USDJPY": 10, "EURJPY": 10,
    "XAUUSD": 80, "US30": 80, "NAS100": 80, "BTCUSD": 80,
}
MIN_SL_PIPS = 3.0

def to_pips(diff, sym):
    return abs(diff) / PIP_SIZE[sym]

def send(msg):
    if not TOKEN or not CHAT_ID:
        print("No Telegram creds", flush=True); return
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg}, timeout=15)
    except Exception as e:
        print("Send fail:", e, flush=True)

def fmt_price(sym, v):
    if sym in ["GBPJPY","USDJPY","EURJPY"]: return f"{v:.2f}"
    if sym == "XAUUSD": return f"{v:.2f}"
    if sym in ["US30","NAS100","BTCUSD"]: return f"{v:.2f}"
    return f"{v:.5f}"

def format_signal(sym, strat, direction, entry, sl, tp1, tp2, prev_high, prev_low, candle_time):
    mid = (prev_high + prev_low) / 2
    sl_p = to_pips(entry - sl, sym)
    tp1_p = to_pips(tp1 - entry, sym)
    tp2_p = to_pips(tp2 - entry, sym)
    rng = to_pips(prev_high - prev_low, sym)
    return (
        f"🔥 {sym} | {strat} | {direction}\n"
        f"📍 Entry: {fmt_price(sym, entry)}\n"
        f"🛑 SL: {fmt_price(sym, sl)} ({sl_p:.1f} pips)\n"
        f"🎯 TP1 Mid: {fmt_price(sym, tp1)} ({tp1_p:.1f} pips)\n"
        f"🎯 TP2 Opposite: {fmt_price(sym, tp2)} ({tp2_p:.1f} pips)\n"
        f"📊 Prev H1: H {fmt_price(sym, prev_high)} / L {fmt_price(sym, prev_low)} / Range {rng:.1f} pips\n"
        f"🕐 Candle: {candle_time} SAST\n"
        f"👉 Check MT5, use your risk. Trade with care."
    )

def get_data(ticker, interval, period="2d"):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval={interval}&range={period}"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        j = r.json()["chart"]["result"][0]
        ts = j["timestamp"]; q = j["indicators"]["quote"][0]
        df = pd.DataFrame({"t": pd.to_datetime(ts, unit="s", utc=True),
            "o": q["open"], "h": q["high"], "l": q["low"], "c": q["close"]})
        df = df.dropna().copy()
        df["t_broker"] = df["t"].dt.tz_convert(BROKER_TZ)
        return df
    except Exception as e:
        print(f"Data fail {ticker}: {e}", flush=True); return None

def get_just_closed_h1(df5):
    if df5 is None or df5.empty: return None
    df = df5.set_index("t_broker").resample("1h").agg({"o":"first","h":"max","l":"min","c":"last"}).dropna()
    if len(df) < 2: return None
    row = df.iloc[-2]
    return {"high": float(row["h"]), "low": float(row["l"]), "close": float(row["c"]), "time": df.index[-2]}

def check_range_ok(sym, prev_high, prev_low):
    rng = to_pips(prev_high - prev_low, sym)
    return rng >= MIN_RANGE_PIPS[sym], rng

def check_sl_ok(sym, entry, sl):
    return to_pips(entry - sl, sym) >= MIN_SL_PIPS

def check_s1(sym, df5, prev):
    if prev is None: return None
    ok, rng = check_range_ok(sym, prev["high"], prev["low"])
    if not ok: return None
    ph, pl, mid = prev["high"], prev["low"], (prev["high"]+prev["low"])/2
    now_b = datetime.now(BROKER_TZ)
    hour_start = now_b.replace(minute=0, second=0, microsecond=0)
    df = df5[df5["t_broker"] >= hour_start].copy()
    if df.empty: return None
    for _, row in df.iterrows():
        c = float(row["c"]); h = float(row["h"]); l = float(row["l"])
        if c > ph or c < pl:
            return None
        if h > ph and c < ph and c > pl:
            entry = c; sl = float(row["h"]); tp1 = mid; tp2 = pl
            if entry <= mid: return None
            if not check_sl_ok(sym, entry, sl): return None
            if to_pips(tp1 - entry, sym) < 1: return None
            return ("STRATEGY 1", "SELL 🔴", entry, sl, tp1, tp2, row["t_broker"])
        if l < pl and c > pl and c < ph:
            entry = c; sl = float(row["l"]); tp1 = mid; tp2 = ph
            if entry >= mid: return None
            if not check_sl_ok(sym, entry, sl): return None
            if to_pips(tp1 - entry, sym) < 1: return None
            return ("STRATEGY 1", "BUY 🟢", entry, sl, tp1, tp2, row["t_broker"])
        if row["t_broker"].minute > 20:
            break
    return None

def check_s2(sym, df1, prev):
    if prev is None: return None
    ok, rng = check_range_ok(sym, prev["high"], prev["low"])
    if not ok: return None
    ph, pl, mid = prev["high"], prev["low"], (prev["high"]+prev["low"])/2
    if df1 is None or len(df1) < 30: return None
    df = df1.tail(60).reset_index(drop=True)
    highs = df["h"].values; lows = df["l"].values; closes = df["c"].values
    for i in range(5, len(df)-5):
        for j in range(i+3, len(df)-2):
            p1, p2 = float(highs[i]), float(highs[j])
            if abs(p1 - p2) <= (ph - pl) * 0.10 and p1 >= ph - (ph-pl)*0.15 and p2 >= ph - (ph-pl)*0.15:
                valley = float(min(lows[i:j+1]))
                for k in range(j+1, len(df)):
                    if float(closes[k]) < valley:
                        entry = float(closes[k]); sl = max(p1, p2); tp1 = mid; tp2 = pl
                        if entry <= mid: return None
                        if not check_sl_ok(sym, entry, sl): return None
                        if to_pips(tp1 - entry, sym) < 1: return None
                        return ("STRATEGY 2", "SELL 🔴", entry, sl, tp1, tp2, df.iloc[k]["t_broker"])
                break
    for i in range(5, len(df)-5):
        for j in range(i+3, len(df)-2):
            p1, p2 = float(lows[i]), float(lows[j])
            if abs(p1 - p2) <= (ph - pl) * 0.10 and p1 <= pl + (ph-pl)*0.15 and p2 <= pl + (ph-pl)*0.15:
                peak = float(max(highs[i:j+1]))
                for k in range(j+1, len(df)):
                    if float(closes[k]) > peak:
                        entry = float(closes[k]); sl = min(p1, p2); tp1 = mid; tp2 = ph
                        if entry >= mid: return None
                        if not check_sl_ok(sym, entry, sl): return None
                        if to_pips(tp1 - entry, sym) < 1: return None
                        return ("STRATEGY 2", "BUY 🟢", entry, sl, tp1, tp2, df.iloc[k]["t_broker"])
                break
    return None

sent = {}
def bot_loop():
    send("✅ KeedSweepBot v3 LIVE - Locked 12 Pairs | Just-Closed H1 | 5M S1 0-20min | 1M S2 Equal + CHOCH | + Range Filter FIX")
    print("Bot loop started", flush=True)
    while True:
        try:
            for sym, ticker in PAIRS.items():
                try:
                    df5 = get_data(ticker, "5m")
                    if df5 is None: continue
                    prev = get_just_closed_h1(df5)
                    if prev is None: continue
                    key_base = f"{sym}_{prev['time']}"
                    s1 = check_s1(sym, df5, prev)
                    if s1:
                        key = key_base + "_S1_" + s1[1]
                        if key not in sent:
                            sent[key] = True
                            _, direction, entry, sl, tp1, tp2, ct = s1
                            send(format_signal(sym, "STRATEGY 1", direction, entry, sl, tp1, tp2, prev["high"], prev["low"], ct.strftime("%H:%M")))
                    df1 = get_data(ticker, "1m", period="1d")
                    s2 = check_s2(sym, df1, prev)
                    if s2:
                        key = key_base + "_S2_" + s2[1]
                        if key not in sent:
                            sent[key] = True
                            _, direction, entry, sl, tp1, tp2, ct = s2
                            send(format_signal(sym, "STRATEGY 2", direction, entry, sl, tp1, tp2, prev["high"], prev["low"], ct.strftime("%H:%M")))
                except Exception as e:
                    print(f"Pair err {sym}: {e}", flush=True)
            time.sleep(55)
        except Exception:
            traceback.print_exc(); time.sleep(10)

threading.Thread(target=bot_loop, daemon=True).start()
if __name__ == "__main__":
    while True:
        time.sleep(3600)
