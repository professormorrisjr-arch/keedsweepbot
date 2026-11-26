# RENDER WEB SERVICE FIX - fake website so Render sees a port
import os
import threading
from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return "KeedSweepBot is alive"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()
# --- END WEB FIX - your bot code below ---

import time
import random
import requests
from datetime import datetime, timezone
import pandas as pd

# --- CONFIG ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# LOCKED 12 PAIRS - DO NOT CHANGE
PAIRS = {
    "GBPUSD": "GBPUSD=X",
    "GBPJPY": "GBPJPY=X",
    "EURUSD": "EURUSD=X",
    "XAUUSD": "GC=F",
    "US30": "^DJI",
    "NAS100": "^IXIC",
    "USDJPY": "USDJPY=X",
    "USDCAD": "USDCAD=X",
    "BTCUSD": "BTC-USD",
    "AUDUSD": "AUDUSD=X",
    "NZDUSD": "NZDUSD=X",
    "EURJPY": "EURJPY=X",
}

sent_signals = set()

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

def fmt(pair, price):
    if pair in ["GBPUSD", "EURUSD", "AUDUSD", "NZDUSD", "USDCAD"]:
        return f"{price:.5f}"
    if pair in ["GBPJPY", "EURJPY", "USDJPY"]:
        return f"{price:.3f}"
    return f"{price:.2f}"

def format_signal(pair, sig):
    return (
        f"📊 {sig['type']} {pair}\n"
        f"🕯️ {sig['strategy']}\n"
        f"🎯 Entry: {fmt(pair, sig['entry'])}\n"
        f"🛑 SL: {fmt(pair, sig['sl'])}\n"
        f"✅ TP1: {fmt(pair, sig['tp1'])} (Mid)\n"
        f"✅ TP2: {fmt(pair, sig['tp2'])} (Opposite Line)\n"
        f"📌 Prev High: {fmt(pair, sig['prev_high'])} | Low: {fmt(pair, sig['prev_low'])}\n"
        f"🕒 Time: {datetime.now(timezone.utc).strftime('%H:%M')} UTC"
    )

def _f(x):
    try:
        if hasattr(x, "iloc"):
            return float(x.iloc[0])
        return float(x)
    except Exception:
        return float(str(x))

# NEW: Direct Yahoo chart API - no yfinance, no crumb, no 429
def get_data(symbol, interval, period):
    # Map our intervals to Yahoo API
    interval_map = {"1h": "60m", "5m": "5m", "1m": "1m"}
    range_map = {"2d": "2d", "1d": "1d"}
    y_interval = interval_map.get(interval, interval)
    y_range = range_map.get(period, period)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"interval": y_interval, "range": y_range, "includePrePost": "false"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    }
    for attempt in range(2):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=15)
            if r.status_code == 429:
                print(f"429 for {symbol}, waiting 10s")
                time.sleep(10)
                continue
            data = r.json()
            result = data["chart"]["result"][0]
            timestamps = result["timestamp"]
            quote = result["indicators"]["quote"][0]
            df = pd.DataFrame({
                "High": quote["high"],
                "Low": quote["low"],
                "Close": quote["close"],
                "Open": quote["open"],
                "Volume": quote["volume"],
            }, index=pd.to_datetime(timestamps, unit="s", utc=True))
            df = df.dropna()
            if len(df) < 5:
                return None
            return df
        except Exception as e:
            print(f"Yahoo direct retry {symbol} {interval}: {e}")
            time.sleep(3)
            continue
    return None

# ============ STRATEGY 1 ============
def check_strategy_1_with_5m(df_5m, prev_high, prev_low):
    recent = df_5m.iloc[-4:-1]
    mid = (prev_high + prev_low) / 2
    for _, c in recent.iterrows():
        high = _f(c['High'])
        low = _f(c['Low'])
        close = _f(c['Close'])
        if high > prev_high and close < prev_high:
            if close <= mid:
                continue
            return {
                'type': 'SELL', 'strategy': 'STRATEGY 1 - Sweep High',
                'entry': close, 'sl': high,
                'tp1': mid, 'tp2': prev_low,
                'prev_high': prev_high, 'prev_low': prev_low
            }
        if low < prev_low and close > prev_low:
            if close >= mid:
                continue
            return {
                'type': 'BUY', 'strategy': 'STRATEGY 1 - Sweep Low',
                'entry': close, 'sl': low,
                'tp1': mid, 'tp2': prev_high,
                'prev_high': prev_high, 'prev_low': prev_low
            }
    return None

# ============ STRATEGY 2 ============
def check_strategy_2_with_1m(df_1m, prev_high, prev_low):
    mid = (prev_high + prev_low) / 2
    rng = prev_high - prev_low
    if rng == 0:
        return None
    df_closed = df_1m.iloc[:-1]
    recent = df_closed.iloc[-60:]
    if len(recent) < 10:
        return None
    close = _f(df_closed.iloc[-1]['Close'])
    lows = [_f(x) for x in recent['Low']]
    highs = [_f(x) for x in recent['High']]

    bottoms = [l for l in lows if abs(l - prev_low) <= rng * 0.15]
    if len(bottoms) >= 2:
        neckline = max([_f(x) for x in recent['High']])
        if close > neckline:
            if close >= mid:
                return None
            sl = min(bottoms) - rng * 0.05
            return {
                'type': 'BUY', 'strategy': 'STRATEGY 2 - Double Bottom',
                'entry': close, 'sl': sl,
                'tp1': mid, 'tp2': prev_high,
                'prev_high': prev_high, 'prev_low': prev_low
            }

    tops = [h for h in highs if abs(h - prev_high) <= rng * 0.15]
    if len(tops) >= 2:
        neckline = min([_f(x) for x in recent['Low']])
        if close < neckline:
            if close <= mid:
                return None
            sl = max(tops) + rng * 0.05
            return {
                'type': 'SELL', 'strategy': 'STRATEGY 2 - Double Top',
                'entry': close, 'sl': sl,
                'tp1': mid, 'tp2': prev_low,
                'prev_high': prev_high, 'prev_low': prev_low
            }
    return None

def main():
    send_telegram("✅ KeedSweepBot v3 LIVE - Locked 12 Pairs | 1H Levels | 5M S1 | 1M S2")
    while True:
        try:
            now = datetime.now(timezone.utc)
            hour_key = now.strftime("%Y-%m-%d-%H")
            for pair, symbol in PAIRS.items():
                try:
                    df_1h = get_data(symbol, "1h", "2d")
                    if df_1h is None:
                        continue
                    prev = df_1h.iloc[-2]
                    prev_high = _f(prev['High'])
                    prev_low = _f(prev['Low'])
                    sig = None

                    if 0 <= now.minute <= 15:
                        df_5m = get_data(symbol, "5m", "1d")
                        if df_5m is not None:
                            sig = check_strategy_1_with_5m(df_5m, prev_high, prev_low)

                    if sig is None:
                        df_1m = get_data(symbol, "1m", "1d")
                        if df_1m is not None:
                            sig = check_strategy_2_with_1m(df_1m, prev_high, prev_low)

                    if sig:
                        key = f"{hour_key}-{pair}-{sig['strategy']}-{sig['type']}"
                        if key not in sent_signals:
                            sent_signals.add(key)
                            send_telegram(format_signal(pair, sig))
                            print(f"SENT: {pair} {sig['type']} {sig['strategy']}")
                except Exception as e:
                    print(f"Error {pair}: {e}")
                    continue
                time.sleep(2 + random.uniform(0, 1))
            time.sleep(90)
        except Exception as e:
            print(f"Loop error: {e}")
            time.sleep(90)

if __name__ == "__main__":
    main()
