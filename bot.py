# KeedSweepBot - FINAL + TELEGRAM + BTCUSD
# Strategy 1: Sweep | Strategy 2: Double Top/Bottom near Prev 1H High/Low
# Runs every hour on Render, sends to Telegram

import os
import time
import requests
from datetime import datetime, timezone

# --- CONFIG ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PAIRS = [
    "EURUSD", "GBPUSD", "GBPJPY", "EURJPY", "EURGBP", "BTCUSD",
    "US30", "NAS100", "USDCAD", "USDCHF", "XAUUSD", "USDJPY"
]

TOL_5MIN = 0.15
TOL_1MIN = 0.05
MIN_PULLBACK = 0.25

# --- TELEGRAM ---
def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured, printing instead:")
        print(message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")

def format_signal(pair, sig, prev_high, prev_low):
    emoji = "🔴" if sig['direction'] == "SELL" else "🟢"
    return (
        f"{emoji} {sig['direction']} {pair} - {sig['strategy']}\n"
        f"Entry: {sig['entry']}\n"
        f"SL: {sig['sl']}\n"
        f"TP1: {sig['tp1']} (50%)\n"
        f"TP2: {sig['tp2']} (Opposite Line)\n"
        f"Prev 1H High: {prev_high} | Low: {prev_low}\n"
        f"Time: {datetime.now(timezone.utc).strftime('%H:%M')} UTC"
    )

# --- CORE LOGIC ---
def get_prev_1h_range(candles_1h):
    prev = candles_1h[-1]  # Previous hour, e.g. at 10:40pm = 09:00pm candle
    return prev['high'], prev['low'], prev['high'] - prev['low'], (prev['high'] + prev['low']) / 2

def check_strategy_1(candles_5m, prev_high, prev_low, current_minute):
    if current_minute > 15:
        return None
    last = candles_5m[-1]
    if last['close'] < prev_high and last['high'] > prev_high:
        return {"strategy": "STRATEGY 1 - SWEEP", "direction": "SELL", "entry": last['close'], "sl": last['high'] + 2, "tp1": (prev_high + prev_low)/2, "tp2": prev_low}
    if last['close'] > prev_low and last['low'] < prev_low:
        return {"strategy": "STRATEGY 1 - SWEEP", "direction": "BUY", "entry": last['close'], "sl": last['low'] - 2, "tp1": (prev_high + prev_low)/2, "tp2": prev_high}
    return None

def find_peaks_5m(candles_5m, prev_high, prev_low, prev_range, direction):
    recent = candles_5m[-12:]
    if len(recent) < 6:
        return None
    tol = prev_range * TOL_5MIN
    if direction == "SELL":
        highs = [(i, c['high']) for i, c in enumerate(recent) if abs(c['high'] - prev_high) <= prev_range * 0.5]
        if len(highs) < 2: return None
        p1_idx, p1 = highs[-2]; p2_idx, p2 = highs[-1]
        if (p2_idx - p1_idx) < 3: return None
        if abs(p1 - p2) > tol: return None
        neckline = min(c['low'] for c in recent[p1_idx:p2_idx+1])
        if (min(p1, p2) - neckline) < (prev_range * MIN_PULLBACK): return None
        return (p1, p2, neckline)
    else:
        lows = [(i, c['low']) for i, c in enumerate(recent) if abs(c['low'] - prev_low) <= prev_range * 0.5]
        if len(lows) < 2: return None
        p1_idx, p1 = lows[-2]; p2_idx, p2 = lows[-1]
        if (p2_idx - p1_idx) < 3: return None
        if abs(p1 - p2) > tol: return None
        neckline = max(c['high'] for c in recent[p1_idx:p2_idx+1])
        if (neckline - max(p1, p2)) < (prev_range * MIN_PULLBACK): return None
        return (p1, p2, neckline)

def confirm_equal_on_1m(candles_1m, prev_range, direction):
    tol_1m = prev_range * TOL_1MIN
    recent_1m = candles_1m[-60:]
    if direction == "SELL":
        top = max(c['high'] for c in recent_1m)
        return len([c for c in recent_1m if abs(c['high'] - top) <= tol_1m]) >= 2
    else:
        bottom = min(c['low'] for c in recent_1m)
        return len([c for c in recent_1m if abs(c['low'] - bottom) <= tol_1m]) >= 2

def check_strategy_2(candles_5m, candles_1m, prev_high, prev_low, prev_range):
    dt = find_peaks_5m(candles_5m, prev_high, prev_low, prev_range, "SELL")
    if dt:
        p1, p2, neckline = dt
        if confirm_equal_on_1m(candles_1m, prev_range, "SELL"):
            if candles_1m[-1]['close'] < neckline:
                return {"strategy": "STRATEGY 2 - DOUBLE TOP", "direction": "SELL", "entry": candles_1m[-1]['close'], "sl": max(p1, p2) + 2, "tp1": (prev_high + prev_low)/2, "tp2": prev_low}
    db = find_peaks_5m(candles_5m, prev_high, prev_low, prev_range, "BUY")
    if db:
        p1, p2, neckline = db
        if confirm_equal_on_1m(candles_1m, prev_range, "BUY"):
            if candles_1m[-1]['close'] > neckline:
                return {"strategy": "STRATEGY 2 - DOUBLE BOTTOM", "direction": "BUY", "entry": candles_1m[-1]['close'], "sl": min(p1, p2) - 2, "tp1": (prev_high + prev_low)/2, "tp2": prev_high}
    return None

def scan_pair(pair, candles_1h, candles_5m, candles_1m):
    prev_high, prev_low, prev_range, mid = get_prev_1h_range(candles_1h)
    now_min = datetime.now().minute
    sig1 = check_strategy_1(candles_5m, prev_high, prev_low, now_min)
    if sig1:
        send_telegram(format_signal(pair, sig1, prev_high, prev_low))
        return sig1
    sig2 = check_strategy_2(candles_5m, candles_1m, prev_high, prev_low, prev_range)
    if sig2:
        send_telegram(format_signal(pair, sig2, prev_high, prev_low))
        return sig2
    return None

# --- MAIN LOOP FOR RENDER ---
if __name__ == "__main__":
    send_telegram("✅ KeedSweepBot is LIVE - 12 Pairs, Strategy 1 + 2, Every Hour")
    while True:
        for pair in PAIRS:
            # TODO: Connect your data feed here - get_candles(pair, timeframe)
            # candles_1h = get_candles(pair, "1h")
            # candles_5m = get_candles(pair, "5m")
            # candles_1m = get_candles(pair, "1m")
            # scan_pair(pair, candles_1h, candles_5m, candles_1m)
            pass
        time.sleep(60)
