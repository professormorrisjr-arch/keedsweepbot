# KeedSweepBot v2 - FINAL
# Pairs: 12 - BTCUSD in, AUDUSD out
# Marking: ONLY previous 1H candle that just closed. Delete old hours.
# Strategy 1: Sweep + Close Inside, 0:00-0:15
# Strategy 2: Double Top/Bottom near Prev H/L, 0:00-0:59, same marking
# Telegram + Render ready

import os
import time
import requests
from datetime import datetime, timezone

# --- CONFIG ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PAIRS = ["EURUSD","GBPUSD","GBPJPY","EURJPY","EURGBP","BTCUSD",
         "US30","NAS100","USDCAD","USDCHF","XAUUSD","USDJPY"]

TOL_5MIN = 0.15  # 15% of Prev Range
TOL_1MIN = 0.05  # 5% of Prev Range
MIN_PULLBACK = 0.25

# --- TELEGRAM ---
def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")

def format_signal(pair, sig, prev_high, prev_low):
    emoji = "🔴" if sig['direction'] == "SELL" else "🟢"
    return (f"{emoji} {sig['direction']} {pair} - {sig['strategy']}\n"
            f"Entry: {sig['entry']}\nSL: {sig['sl']}\n"
            f"TP1: {sig['tp1']} (50%)\nTP2: {sig['tp2']} (Opposite Line)\n"
            f"Prev 1H High: {prev_high} | Low: {prev_low}\n"
            f"Time: {datetime.now(timezone.utc).strftime('%H:%M')} UTC")

# --- 1. MARKING - SAME FOR BOTH STRATEGIES ---
def get_prev_1h_range(candles_1h):
    # Drop forming candle, take ONLY last closed one
    # Delete old hours - we only ever use this ONE candle
    closed = [c for c in candles_1h if c.get('is_closed', True)]
    prev = closed[-1]
    prev_high = prev['high']
    prev_low = prev['low']
    prev_range = prev_high - prev_low
    mid = (prev_high + prev_low) / 2
    print(f"Prev 1H used: {prev['time']} High={prev_high} Low={prev_low}")
    return prev_high, prev_low, prev_range, mid

# --- 2. STRATEGY 1 - SWEEP + CLOSE INSIDE - 0:00-0:15 ONLY ---
def check_strategy_1(candles_5m, prev_high, prev_low, current_minute):
    if current_minute > 15:
        return None
    last = candles_5m[-1]
    # SELL: wick above High, close back INSIDE range
    if last['high'] > prev_high and last['close'] < prev_high and last['close'] > prev_low:
        return {"strategy": "STRATEGY 1 - SWEEP", "direction": "SELL",
                "entry": last['close'], "sl": last['high'],
                "tp1": (prev_high + prev_low)/2, "tp2": prev_low}
    # BUY: wick below Low, close back INSIDE range
    if last['low'] < prev_low and last['close'] > prev_low and last['close'] < prev_high:
        return {"strategy": "STRATEGY 1 - SWEEP", "direction": "BUY",
                "entry": last['close'], "sl": last['low'],
                "tp1": (prev_high + prev_low)/2, "tp2": prev_high}
    return None

# --- 3. STRATEGY 2 - DOUBLE TOP/BOTTOM NEAR PREV H/L - 0:00-0:59 ---
# Same marking as Strategy 1. Confirmation is different.
def find_peaks_5m(candles_5m, prev_high, prev_low, prev_range, direction):
    recent = candles_5m[-12:]
    tol = prev_range * TOL_5MIN
    if direction == "SELL":  # Double Top NEAR Prev High
        highs = [(i,c['high']) for i,c in enumerate(recent) if abs(c['high']-prev_high) <= prev_range*0.5]
        if len(highs) < 2: return None
        p1_idx,p1 = highs[-2]; p2_idx,p2 = highs[-1]
        if (p2_idx-p1_idx) < 3: return None
        if abs(p1-p2) > tol: return None
        neckline = min(c['low'] for c in recent[p1_idx:p2_idx+1])
        if (min(p1,p2)-neckline) < prev_range*MIN_PULLBACK: return None
        return (p1,p2,neckline)
    else:  # Double Bottom NEAR Prev Low
        lows = [(i,c['low']) for i,c in enumerate(recent) if abs(c['low']-prev_low) <= prev_range*0.5]
        if len(lows) < 2: return None
        p1_idx,p1 = lows[-2]; p2_idx,p2 = lows[-1]
        if (p2_idx-p1_idx) < 3: return None
        if abs(p1-p2) > tol: return None
        neckline = max(c['high'] for c in recent[p1_idx:p2_idx+1])
        if (neckline-max(p1,p2)) < prev_range*MIN_PULLBACK: return None
        return (p1,p2,neckline)

def confirm_equal_on_1m(candles_1m, prev_range, direction):
    tol_1m = prev_range * TOL_1MIN
    recent_1m = candles_1m[-60:]
    if direction == "SELL":
        top = max(c['high'] for c in recent_1m)
        return len([c for c in recent_1m if abs(c['high']-top) <= tol_1m]) >= 2
    else:
        bottom = min(c['low'] for c in recent_1m)
        return len([c for c in recent_1m if abs(c['low']-bottom) <= tol_1m]) >= 2

def check_strategy_2(candles_5m, candles_1m, prev_high, prev_low, prev_range):
    dt = find_peaks_5m(candles_5m, prev_high, prev_low, prev_range, "SELL")
    if dt:
        p1,p2,neckline = dt
        if confirm_equal_on_1m(candles_1m, prev_range, "SELL"):
            if candles_1m[-1]['close'] < neckline:
                return {"strategy": "STRATEGY 2 - DOUBLE TOP", "direction": "SELL",
                        "entry": candles_1m[-1]['close'], "sl": max(p1,p2),
                        "tp1": (prev_high+prev_low)/2, "tp2": prev_low}
    db = find_peaks_5m(candles_5m, prev_high, prev_low, prev_range, "BUY")
    if db:
        p1,p2,neckline = db
        if confirm_equal_on_1m(candles_1m, prev_range, "BUY"):
            if candles_1m[-1]['close'] > neckline:
                return {"strategy": "STRATEGY 2 - DOUBLE BOTTOM", "direction": "BUY",
                        "entry": candles_1m[-1]['close'], "sl": min(p1,p2),
                        "tp1": (prev_high+prev_low)/2, "tp2": prev_high}
    return None

# --- 4. SCAN - 12 PAIRS ---
def scan_pair(pair, candles_1h, candles_5m, candles_1m, current_minute):
    prev_high, prev_low, prev_range, mid = get_prev_1h_range(candles_1h)
    sig1 = check_strategy_1(candles_5m, prev_high, prev_low, current_minute)
    if sig1:
        send_telegram(format_signal(pair, sig1, prev_high, prev_low))
        return sig1
    sig2 = check_strategy_2(candles_5m, candles_1m, prev_high, prev_low, prev_range)
    if sig2:
        send_telegram(format_signal(pair, sig2, prev_high, prev_low))
        return sig2
    return None

if __name__ == "__main__":
    send_telegram("✅ KeedSweepBot v2 LIVE - 12 Pairs, Strategy 1 + 2")
    while True:
        for pair in PAIRS:
            # TODO: Connect your data feed here
            # candles_1h = get_candles(pair, "1h")
            # candles_5m = get_candles(pair, "5m")
            # candles_1m = get_candles(pair, "1m")
            # scan_pair(pair, candles_1h, candles_5m, candles_1m, datetime.now(timezone.utc).minute)
            pass
        time.sleep(60)
