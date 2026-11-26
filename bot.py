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
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import pandas as pd

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BROKER_TZ = ZoneInfo("Europe/Athens")

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

def pip_size(pair):
    if pair in ["GBPJPY", "EURJPY", "USDJPY"]:
        return 0.01
    if pair in ["GBPUSD", "EURUSD", "AUDUSD", "NZDUSD", "USDCAD"]:
        return 0.0001
    if pair == "XAUUSD":
        return 0.1
    if pair == "BTCUSD":
        return 1.0
    return 1.0

def format_signal(pair, sig):
    candle_txt = sig.get('candle', '')
    now_broker = datetime.now(BROKER_TZ).strftime('%H:%M')
    ps = pip_size(pair)
    if sig['type'] == 'BUY':
        tp1_pips = (sig['tp1'] - sig['entry']) / ps
        tp2_pips = (sig['tp2'] - sig['entry']) / ps
        sl_pips = (sig['entry'] - sig['sl']) / ps
    else:
        tp1_pips = (sig['entry'] - sig['tp1']) / ps
        tp2_pips = (sig['entry'] - sig['tp2']) / ps
        sl_pips = (sig['sl'] - sig['entry']) / ps
    return (
        f"📊 {sig['type']} {pair}\n"
        f"🕯️ {sig['strategy']}\n"
        f"🎯 Entry: {fmt(pair, sig['entry'])}\n"
        f"🛑 SL: {fmt(pair, sig['sl'])} ({sl_pips:.1f} pips)\n"
        f"✅ TP1: {fmt(pair, sig['tp1'])} (Mid - {tp1_pips:.1f} pips)\n"
        f"✅ TP2: {fmt(pair, sig['tp2'])} (Opposite - {tp2_pips:.1f} pips)\n"
        f"📌 Prev H1 (Just-Closed): High {fmt(pair, sig['prev_high'])} | Low {fmt(pair, sig['prev_low'])}\n"
        f"🕯️ Candle: {candle_txt}\n"
        f"🕒 Time: {now_broker} SAST / Broker\n"
        f"📱 Check MT5 - confirm, use YOUR MT5 High/Low for exact SL"
    )

def _f(x):
    try:
        if hasattr(x, "iloc"):
            return float(x.iloc[0])
        return float(x)
    except Exception:
        return float(str(x))

def get_data(symbol, interval, period):
    interval_map = {"1h": "60m", "5m": "5m", "1m": "1m"}
    range_map = {"2d": "2d", "1d": "1d"}
    y_interval = interval_map.get(interval, interval)
    y_range = range_map.get(period, period)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"interval": y_interval, "range": y_range, "includePrePost": "false"}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}
    for attempt in range(2):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=15)
            if r.status_code == 429:
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
            print(f"Yahoo retry {symbol} {interval}: {e}")
            time.sleep(3)
            continue
    return None

def get_just_closed_h1(symbol):
    df_5m = get_data(symbol, "5m", "2d")
    if df_5m is None or len(df_5m) < 50:
        return None, None
    df_broker = df_5m.tz_convert(BROKER_TZ)
    df_1h = df_broker.resample("1h").agg({
        "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"
    }).dropna()
    if len(df_1h) < 3:
        return None, None
    prev = df_1h.iloc[-2]
    return _f(prev['High']), _f(prev['Low'])

# ============ STRATEGY 1 - LOCKED AS YOU CORRECTED ============
# New hour: Prev H1 marked. Check :05 -> :10 -> :15 -> :20 in order.
# RULE: If ANY 5M candle closes OUTSIDE Prev H1 range = NO SIGNAL, stop.
# Signal ONLY if 5M sweeps High/Low AND closes INSIDE range.
def check_strategy_1(df_5m, prev_high, prev_low, now, now_broker):
    closed = df_5m[df_5m.index + timedelta(minutes=5) <= now]
    if len(closed) == 0:
        return None
    hour_start_broker = now_broker.replace(minute=0, second=0, microsecond=0)
    hour_start_utc = hour_start_broker.astimezone(timezone.utc)
    window = closed[closed.index >= hour_start_utc].head(4)
    if len(window) == 0:
        return None
    mid = (prev_high + prev_low) / 2
    for idx, c in window.iterrows():
        high = _f(c['High'])
        low = _f(c['Low'])
        close = _f(c['Close'])
        candle_start = idx.astimezone(BROKER_TZ)
        candle_end = candle_start + timedelta(minutes=5)
        candle_txt = f"{candle_start.strftime('%H:%M')}-{candle_end.strftime('%H:%M')} 5M closed - swept + closed inside"
        if close > prev_high or close < prev_low:
            return None
        if high > prev_high and close < prev_high:
            if close <= mid:
                continue
            return {
                'type': 'SELL', 'strategy': 'STRATEGY 1 - Sweep High',
                'entry': close, 'sl': high,
                'tp1': mid, 'tp2': prev_low,
                'prev_high': prev_high, 'prev_low': prev_low,
                'candle': candle_txt
            }
        if low < prev_low and close > prev_low:
            if close >= mid:
                continue
            return {
                'type': 'BUY', 'strategy': 'STRATEGY 1 - Sweep Low',
                'entry': close, 'sl': low,
                'tp1': mid, 'tp2': prev_high,
                'prev_high': prev_high, 'prev_low': prev_low,
                'candle': candle_txt
            }
    return None

# ============ STRATEGY 2 - UPDATED: EQUAL HIGHS/LOWS + CHOCH / NECKLINE BREAK ============
# Double Top: 2x Equal Highs near Prev H1 High -> valley = neckline -> close BELOW neckline = CHOCH = SELL
# Double Bottom: 2x Equal Lows near Prev H1 Low -> peak = neckline -> close ABOVE neckline = CHOCH = BUY
def check_strategy_2(df_1m, prev_high, prev_low, now):
    mid = (prev_high + prev_low) / 2
    rng = prev_high - prev_low
    if rng == 0:
        return None
    closed = df_1m[df_1m.index + timedelta(minutes=1) <= now]
    if len(closed) < 20:
        return None
    recent = closed.iloc[-60:]
    close = _f(closed.iloc[-1]['Close'])
    candle_start = closed.index[-1].astimezone(BROKER_TZ)
    highs = [_f(x) for x in recent['High']]
    lows = [_f(x) for x in recent['Low']]
    closes = [_f(x) for x in recent['Close']]

    # --- DOUBLE TOP: Equal Highs ---
    # Find 2 peaks near Prev High, peaks must be EQUAL (within 10% of H1 range)
    # and both near Prev High (within 15% of range)
    top_idx = [i for i, h in enumerate(highs) if abs(h - prev_high) <= rng * 0.15]
    if len(top_idx) >= 2:
        # Take last 2 peaks
        p1_i = top_idx[-2]
        p2_i = top_idx[-1]
        p1 = highs[p1_i]
        p2 = highs[p2_i]
        # Equal Highs check: peaks close to each other
        if abs(p1 - p2) <= rng * 0.10 and p2_i > p1_i:
            # Neckline = lowest Low between the 2 peaks (the valley)
            valley = min(lows[p1_i:p2_i+1]) if p2_i > p1_i else None
            if valley is not None and close < valley:
                # CHOCH / Neckline break confirmed on closed 1M candle
                if close > mid:
                    return None  # Already past Mid, no trade
                sl = max(p1, p2) + rng * 0.05
                candle_txt = f"{candle_start.strftime('%H:%M')} 1M closed - Double Top Equal Highs + CHOCH below neckline {valley:.5f}"
                return {
                    'type': 'SELL', 'strategy': 'STRATEGY 2 - Double Top (Equal Highs + CHOCH)',
                    'entry': close, 'sl': sl,
                    'tp1': mid, 'tp2': prev_low,
                    'prev_high': prev_high, 'prev_low': prev_low,
                    'candle': candle_txt
                }

    # --- DOUBLE BOTTOM: Equal Lows ---
    bot_idx = [i for i, l in enumerate(lows) if abs(l - prev_low) <= rng * 0.15]
    if len(bot_idx) >= 2:
        p1_i = bot_idx[-2]
        p2_i = bot_idx[-1]
        p1 = lows[p1_i]
        p2 = lows[p2_i]
        # Equal Lows check
        if abs(p1 - p2) <= rng * 0.10 and p2_i > p1_i:
            # Neckline = highest High between the 2 bottoms (the peak)
            peak = max(highs[p1_i:p2_i+1]) if p2_i > p1_i else None
            if peak is not None and close > peak:
                # CHOCH / Neckline break confirmed
                if close < mid:
                    return None
                # Wait - BUY needs close BELOW Mid to have TP1 ahead. If close >= Mid, skip.
                # Actually for BUY we need close < Mid. The check above is inverted, fix:
                pass
            if peak is not None and close > peak:
                if close >= mid:
                    return None
                sl = min(p1, p2) - rng * 0.05
                candle_txt = f"{candle_start.strftime('%H:%M')} 1M closed - Double Bottom Equal Lows + CHOCH above neckline {peak:.5f}"
                return {
                    'type': 'BUY', 'strategy': 'STRATEGY 2 - Double Bottom (Equal Lows + CHOCH)',
                    'entry': close, 'sl': sl,
                    'tp1': mid, 'tp2': prev_high,
                    'prev_high': prev_high, 'prev_low': prev_low,
                    'candle': candle_txt
                }
    return None

def main():
    send_telegram("✅ KeedSweepBot v3 LIVE - Locked 12 Pairs | Just-Closed H1 | 5M S1 0-20min | 1M S2 Equal + CHOCH")
    while True:
        try:
            now = datetime.now(timezone.utc)
            now_broker = datetime.now(BROKER_TZ)
            hour_key = now_broker.strftime("%Y-%m-%d-%H")
            for pair, symbol in PAIRS.items():
                try:
                    prev_high, prev_low = get_just_closed_h1(symbol)
                    if prev_high is None:
                        continue
                    sig = None
                    if 0 <= now_broker.minute <= 20:
                        df_5m = get_data(symbol, "5m", "1d")
                        if df_5m is not None:
                            sig = check_strategy_1(df_5m, prev_high, prev_low, now, now_broker)
                    if sig is None:
                        df_1m = get_data(symbol, "1m", "1d")
                        if df_1m is not None:
                            sig = check_strategy_2(df_1m, prev_high, prev_low, now)
                    if sig:
                        key = f"{hour_key}-{pair}-{sig['strategy']}-{sig['type']}"
                        if key not in sent_signals:
                            sent_signals.add(key)
                            send_telegram(format_signal(pair, sig))
                            print(f"SENT: {pair} {sig['type']} {sig['strategy']}")
                except Exception as e:
                    print(f"Error {pair}: {e}")
                    continue
                time.sleep(1 + random.uniform(0, 0.5))
            if 0 <= datetime.now(BROKER_TZ).minute <= 21:
                time.sleep(20)
            else:
                time.sleep(60)
        except Exception as e:
            print(f"Loop error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
