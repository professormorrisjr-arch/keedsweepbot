# KeedSweepBot - OPTION 2 - SELF SCANNING - NO TRADINGVIEW
# Strategy 1: 1H Sweep 0:15 | Strategy 2: Double Top/Bottom | TP1 50% / TP2 Opposite
# Runs on Render Free + UptimeRobot

import os
import time
import threading
import requests
from datetime import datetime, timezone
from flask import Flask

# --- KEEP RENDER AWAKE ---
app = Flask(__name__)
@app.route('/')
def home():
    return "KeedSweepBot is alive - Option 2 Self Scanning"
def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
threading.Thread(target=run_web, daemon=True).start()

# --- CONFIG ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN") or ""
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("CHAT_ID") or ""

# Yahoo symbols
PAIRS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "GBPJPY": "GBPJPY=X",
    "EURJPY": "EURJPY=X",
    "EURGBP": "EURGBP=X",
    "BTCUSD": "BTC-USD",
    "US30": "^DJI",
    "NAS100": "^NDX",
    "USDCAD": "USDCAD=X",
    "USDCHF": "USDCHF=X",
    "XAUUSD": "GC=F",
    "USDJPY": "USDJPY=X",
}

TOL_5MIN = 0.15
TOL_1MIN = 0.05
MIN_PULLBACK = 0.25

sent_signals = set()  # to avoid sending same signal twice

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Missing Telegram Token/Chat ID")
        print(msg)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
        print("Sent:", msg[:60])
    except Exception as e:
        print("Telegram error:", e)

def get_candles(symbol, interval, period):
    try:
        import yfinance as yf
        df = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=False)
        if df is None or len(df) < 10:
            return []
        if hasattr(df.columns, 'get_level_values'):
            try:
                df.columns = df.columns.get_level_values(0)
            except:
                pass
        candles = []
        for i in range(len(df)):
            candles.append({
                'high': float(df['High'].iloc[i]),
                'low': float(df['Low'].iloc[i]),
                'close': float(df['Close'].iloc[i]),
                'open': float(df['Open'].iloc[i]),
            })
        return candles
    except Exception as e:
        print(f"Error {symbol} {interval}: {e}")
        return []

def check_strategy_1(candles_5m, prev_high, prev_low, current_minute):
    if current_minute > 15:
        return None
    if not candles_5m:
        return None
    last = candles_5m[-1]
    if last['close'] < prev_high and last['high'] > prev_high:
        return {"strategy": "STRATEGY 1 - SWEEP", "direction": "SELL", "entry": last['close'], "sl": last['high'], "tp1": (prev_high + prev_low)/2, "tp2": prev_low}
    if last['close'] > prev_low and last['low'] < prev_low:
        return {"strategy": "STRATEGY 1 - SWEEP", "direction": "BUY", "entry": last['close'], "sl": last['low'], "tp1": (prev_high + prev_low)/2, "tp2": prev_high}
    return None

def find_peaks_5m(candles_5m, prev_high, prev_low, prev_range, direction):
    recent = candles_5m[-12:]
    if len(recent) < 6:
        return None
    tol = prev_range * TOL_5MIN
    if direction == "SELL":
        highs = [(i, c['high']) for i, c in enumerate(recent) if abs(c['high'] - prev_high) <= prev_range * 0.5]
        if len(highs) < 2:
            return None
        p1_idx, p1 = highs[-2]
        p2_idx, p2 = highs[-1]
        if (p2_idx - p1_idx) < 3:
            return None
        if abs(p1 - p2) > tol:
            return None
        neckline = min(c['low'] for c in recent[p1_idx:p2_idx+1])
        if (min(p1, p2) - neckline) < (prev_range * MIN_PULLBACK):
            return None
        return (p1, p2, neckline)
    else:
        lows = [(i, c['low']) for i, c in enumerate(recent) if abs(c['low'] - prev_low) <= prev_range * 0.5]
        if len(lows) < 2:
            return None
        p1_idx, p1 = lows[-2]
        p2_idx, p2 = lows[-1]
        if (p2_idx - p1_idx) < 3:
            return None
        if abs(p1 - p2) > tol:
            return None
        neckline = max(c['high'] for c in recent[p1_idx:p2_idx+1])
        if (neckline - max(p1, p2)) < (prev_range * MIN_PULLBACK):
            return None
        return (p1, p2, neckline)

def confirm_equal_on_1m(candles_1m, prev_range, direction):
    if not candles_1m:
        return True
    tol_1m = prev_range * TOL_1MIN
    recent = candles_1m[-60:]
    if direction == "SELL":
        top = max(c['high'] for c in recent)
        return len([c for c in recent if abs(c['high'] - top) <= tol_1m]) >= 2
    else:
        bottom = min(c['low'] for c in recent)
        return len([c for c in recent if abs(c['low'] - bottom) <= tol_1m]) >= 2

def check_strategy_2(candles_5m, candles_1m, prev_high, prev_low, prev_range):
    dt = find_peaks_5m(candles_5m, prev_high, prev_low, prev_range, "SELL")
    if dt:
        p1, p2, neckline = dt
        if confirm_equal_on_1m(candles_1m, prev_range, "SELL"):
            if candles_1m and candles_1m[-1]['close'] < neckline:
                return {"strategy": "STRATEGY 2 - DOUBLE TOP", "direction": "SELL", "entry": candles_1m[-1]['close'], "sl": max(p1, p2), "tp1": (prev_high + prev_low)/2, "tp2": prev_low}
    db = find_peaks_5m(candles_5m, prev_high, prev_low, prev_range, "BUY")
    if db:
        p1, p2, neckline = db
        if confirm_equal_on_1m(candles_1m, prev_range, "BUY"):
            if candles_1m and candles_1m[-1]['close'] > neckline:
                return {"strategy": "STRATEGY 2 - DOUBLE BOTTOM", "direction": "BUY", "entry": candles_1m[-1]['close'], "sl": min(p1, p2), "tp1": (prev_high + prev_low)/2, "tp2": prev_high}
    return None

def format_signal(pair, sig, prev_high, prev_low):
    emoji = "🔴" if sig['direction'] == "SELL" else "🟢"
    return (
        f"{emoji} {sig['direction']} {pair} - {sig['strategy']}\n"
        f"Entry: {sig['entry']:.5f}\n"
        f"SL: {sig['sl']:.5f}\n"
        f"TP1: {sig['tp1']:.5f} (50%)\n"
        f"TP2: {sig['tp2']:.5f} (Opposite Line)\n"
        f"Prev 1H High: {prev_high:.5f} | Low: {prev_low:.5f}\n"
        f"Time: {datetime.now(timezone.utc).strftime('%H:%M')} UTC"
    )

def scan_pair(pair, symbol):
    # 1H candles - last closed = previous hour
    candles_1h = get_candles(symbol, "60m", "2d")
    if len(candles_1h) < 2:
        return
    prev = candles_1h[-2]  # previous closed 1H, not current forming
    prev_high, prev_low = prev['high'], prev['low']
    prev_range = prev_high - prev_low
    if prev_range == 0:
        return
    candles_5m = get_candles(symbol, "5m", "1d")
    candles_1m = get_candles(symbol, "1m", "1d")
    now_min = datetime.now(timezone.utc).minute

    sig = check_strategy_1(candles_5m, prev_high, prev_low, now_min)
    if not sig:
        sig = check_strategy_2(candles_5m, candles_1m, prev_high, prev_low, prev_range)
    if sig:
        key = f"{pair}-{sig['strategy']}-{sig['direction']}-{datetime.now(timezone.utc).strftime('%Y-%m-%d-%H')}-{round(sig['entry'],2)}"
        if key not in sent_signals:
            sent_signals.add(key)
            send_telegram(format_signal(pair, sig, prev_high, prev_low))

def main():
    send_telegram("✅ <b>KeedSweepBot ONLINE</b> - Option 2 Self Scanning | 12 Pairs | Strategy 1 + 2 | No TradingView")
    print("KeedSweepBot ONLINE - Option 2")
    while True:
        try:
            for pair, symbol in PAIRS.items():
                scan_pair(pair, symbol)
                time.sleep(2)
        except Exception as e:
            print("Loop error:", e)
        time.sleep(60)

if __name__ == "__main__":
    main()
