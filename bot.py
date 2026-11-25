# RENDER WEB FREE FIX - fake website so Render sees a port
import os
import threading
from flask import Flask
from zoneinfo import ZoneInfo
app = Flask(__name__)

@app.route('/')
def home():
    return "KeedSweepBot is alive"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()
# --- END FIX - your original bot code below ---
import os
import time
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta
import pytz

# ============ CONFIG ============
TOKEN = os.getenv("8752039586:AAE8Kf--uWOy9sxnz_eRDMZm003-nxOxjwQ")
CHAT_ID = os.getenv("7279745404")
SA_TZ = pytz.timezone("Africa/Johannesburg")

# 12 Pairs - Yahoo symbols
PAIRS = {
    "XAU/USD": "GC=F",
    "US30": "^DJI",
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "USDJPY=X",
    "AUD/USD": "AUDUSD=X",
    "USD/CAD": "USDCAD=X",
    "NZD/USD": "NZDUSD=X",
    "EUR/GBP": "EURGBP=X",
    "GBP/JPY": "GBPJPY=X",
    "USD/CHF": "USDCHF=X",
    "BTC/USD": "BTC-USD",
}

# Track 1 signal per hour per pair
last_signal_hour = {}

def send_telegram(msg):
    if not TOKEN or not CHAT_ID:
        print("Missing TOKEN / CHAT_ID")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        print("Telegram error:", e)

def is_session():
    now_sa = datetime.now(SA_TZ)
    h = now_sa.hour
    # London 09:00-13:00 SA, NY 15:30-20:00 SA
    if 9 <= h < 13:
        return True, "London 🇬🇧"
    if 15 <= h < 20:
        return True, "New York 🇺🇸"
    return False, "Off Session"

def get_data(symbol):
    # Get 1H + 5Min from Yahoo
    try:
        url_1h = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1h&range=2d"
        url_5m = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=5m&range=1d"
        r1 = requests.get(url_1h, headers={"User-Agent": "Mozilla/5.0"}, timeout=10).json()
        r5 = requests.get(url_5m, headers={"User-Agent": "Mozilla/5.0"}, timeout=10).json()
        h1 = r1["chart"]["result"][0]
        h5 = r5["chart"]["result"][0]
        df1h = pd.DataFrame({
            "Time": pd.to_datetime(h1["timestamp"], unit="s", utc=True),
            "High": h1["indicators"]["quote"][0]["high"],
            "Low": h1["indicators"]["quote"][0]["low"],
            "Close": h1["indicators"]["quote"][0]["close"],
        })
        df5m = pd.DataFrame({
            "Time": pd.to_datetime(h5["timestamp"], unit="s", utc=True),
            "Open": h5["indicators"]["quote"][0]["open"],
            "High": h5["indicators"]["quote"][0]["high"],
            "Low": h5["indicators"]["quote"][0]["low"],
            "Close": h5["indicators"]["quote"][0]["close"],
        })
        return df1h.dropna(), df5m.dropna()
    except Exception as e:
        print(f"Data error {symbol}:", e)
        return None, None

def check_pair(name, symbol):
    df1h, df5m = get_data(symbol)
    if df1h is None or len(df1h) < 2 or len(df5m) < 3:
        return

    now_sa = datetime.now(SA_TZ)
    # Previous 1H candle = Range
    prev_1h = df1h.iloc[-2]
    range_high = float(prev_1h["High"])
    range_low = float(prev_1h["Low"])
    range_size = range_high - range_low
    if range_size <= 0:
        return
    mid_range = (range_high + range_low) / 2
    
    # Hour key for 1 signal per hour
    hour_key = f"{name}_{now_sa.strftime('%Y-%m-%d-%H')}"
    if hour_key in last_signal_hour:
        return
         # Current hour start (SA time) -> convert to UTC to match Yahoo data
    hour_start_sa = now_sa.replace(minute=0, second=0, microsecond=0)
    hour_start_utc = hour_start_sa.astimezone(ZoneInfo("UTC"))
    curr_m5 = df5m[pd.to_datetime(df5m.index) >= pd.Timestamp(hour_start_utc)]

  

    # --- RULE: No close inside before sweep ---
    # If any earlier 5m candle in this hour already closed inside range before sweep, cancel
    # We check in order
    sweep_side = None
    sweep_close = None
    sweep_idx = -1

    for i in range(len(curr_m5)):
        c = curr_m5.iloc[i]
        o, h, l, cl = float(c["Open"]), float(c["High"]), float(c["Low"]), float(c["Close"])
        # If price already closed inside range BEFORE any sweep, this hour is dead
        if range_low < cl < range_high and sweep_side is None:
            # First candle closing inside without sweep = price lived inside, cancel
            # But allow if it's the sweep candle itself (handled below)
            # If open was outside and close inside with wick sweep, that's sweep
            # Check sweep first
            pass

        # Check sweep High: wick above High, close back inside
        if h > range_high and range_low < cl < range_high:
            # Must be first touch - check no earlier sweep in this hour
            if sweep_side is None:
                # Check earlier candles didn't already close inside
                earlier = curr_m5.iloc[:i]
                already_inside = False
                for _, ec in earlier.iterrows():
                    if range_low < float(ec["Close"]) < range_high:
                        already_inside = True
                        break
                if not already_inside:
                    sweep_side = "HIGH"
                    sweep_close = cl
                    sweep_idx = i
                    break
        # Check sweep Low: wick below Low, close back inside
        if l < range_low and range_low < cl < range_high:
            if sweep_side is None:
                earlier = curr_m5.iloc[:i]
                already_inside = False
                for _, ec in earlier.iterrows():
                    if range_low < float(ec["Close"]) < range_high:
                        already_inside = True
                        break
                if not already_inside:
                    sweep_side = "LOW"
                    sweep_close = cl
                    sweep_idx = i
                    break

    if sweep_side is None:
        return

    # --- VALID SIGNAL - TP1 / TP2 / SL (YOUR LOCKED VERSION) ---
    session, session_name = is_session()
    # Sweep wick = High/Low of sweep candle
    sweep_candle = curr_m5.iloc[sweep_idx]
    sweep_high_wick = float(sweep_candle["High"])
    sweep_low_wick = float(sweep_candle["Low"])

    if sweep_side == "HIGH":
        direction = "SELL 🔴"
        entry = sweep_close
        sl = sweep_high_wick + (range_size * 0.1)  # 10% buffer above wick
        tp1 = mid_range  # 50% of range
        tp2 = range_low  # Opposite point = Low
        rr1 = abs(entry - tp1) / abs(entry - sl) if entry != sl else 0
        rr2 = abs(entry - tp2) / abs(entry - sl) if entry != sl else 0
    else:
        direction = "BUY 🟢"
        entry = sweep_close
        sl = sweep_low_wick - (range_size * 0.1)  # 10% buffer below wick
        tp1 = mid_range  # 50% of range
        tp2 = range_high  # Opposite point = High
        rr1 = abs(tp1 - entry) / abs(sl - entry) if entry != sl else 0
        rr2 = abs(tp2 - entry) / abs(sl - entry) if entry != sl else 0

    msg = (
        f"🔥 *{name} {direction}*\n"
        f"Session: {session_name}\n"
        f"Time: {now_sa.strftime('%H:%M')} SA\n"
        f"1H Range: {range_low:.2f} - {range_high:.2f}\n"
        f"Range Size: {range_size:.2f}\n"
        f"Sweep: {sweep_side} within 0:15 ✅\n"
        f"5Min Close Inside ✅\n"
        f"----------------\n"
        f"Entry: {entry:.2f}\n"
        f"SL: {sl:.2f}\n"
        f"TP1 (50% Range): {tp1:.2f} | RR ~{rr1:.2f}R\n"
        f"TP2 (Opposite): {tp2:.2f} | RR ~{rr2:.2f}R\n"
        f"----------------\n"
        f"Plan: Take 50% at TP1, move SL to BE, let rest run to TP2"
    )
    print(msg)
    send_telegram(msg)
    last_signal_hour[hour_key] = True

def main_loop():
    send_telegram("✅ KeedSweepBot ONLINE - 1H Sweep | 0:15 | TP1 50% / TP2 Opposite | 12 Pairs")
    while True:
        session, session_name = is_session()
        if session:
            for name, symbol in PAIRS.items():
                try:
                    check_pair(name, symbol)
                except Exception as e:
                    print(f"Error {name}:", e)
                time.sleep(2)
            print(f"Scan done {datetime.now(SA_TZ).strftime('%H:%M')} - {session_name}")
            time.sleep(60)  # scan every 1 min during session
        else:
            print(f"Off session {datetime.now(SA_TZ).strftime('%H:%M')} - sleeping")
            time.sleep(300)
# --- TELEGRAM COMMANDS: /start and /scan ---
def get_updates(offset=None):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?timeout=5"
        if offset:
            url += f"&offset={offset}"
        r = requests.get(url, timeout=10).json()
        return r.get("result", [])
    except:
        return []

def listen_for_commands():
    offset = None
    print("Listening for /start and /scan...", flush=True)
    # Clear old stuck updates so old Render deploy stops stealing them
    try:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset=-1", timeout=10)
    except:
        pass
    while True:
        try:
            updates = get_updates(offset)
            if updates:
                print(f"Got {len(updates)} updates", flush=True)
            for u in updates:
                offset = u["update_id"] + 1
                msg = u.get("message", {})
                text = msg.get("text", "").lower().strip()
                # Handle /start@YourBotName too
                if text.startswith("/start"):
                    print("Got /start", flush=True)
                    send_telegram("✅ KeedSweepBot ONLINE - 1H Sweep | 0:15 | TP1 50% / TP2 Opposite")
                elif text.startswith("/scan"):
                    print("Got /scan", flush=True)
                    send_telegram("🔍 Scanning 12 pairs now...")
                    for name, symbol in PAIRS.items():
                        try:
                            check_pair(name, symbol)
                        except Exception as e:
                            print(f"Scan error {name}: {e}", flush=True)
                    send_telegram("✅ Scan done. Waiting for next 0:15 setup.")
        except Exception as e:
            print(f"Listen error: {e}", flush=True)
        time.sleep(3)

if __name__ == "__main__":
    import threading
    threading.Thread(target=listen_for_commands, daemon=True).start()
    main_loop()
