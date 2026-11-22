import os
import time
import threading
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timedelta, timezone

# ---------- CONFIG ----------
SYMBOLS = {
    "XAUUSD": {"category": "linear", "name": "XAUUSD"},
    "BTCUSD": {"category": "inverse", "name": "BTCUSD"},
       "EURUSD": {"category": "linear", "name": "EURUSD"},
    "GBPUSD": {"category": "linear", "name": "GBPUSD"},
    "US30": {"category": "linear", "name": "US30"},
}
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SA = timezone(timedelta(hours=2))
BYBIT = "https://api.bybit.com"

# ---------- KEEP ALIVE ----------
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"KeedSweepBot is live!")
    def log_message(self, *args):
        pass

def keep_alive():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()

threading.Thread(target=keep_alive, daemon=True).start()

# ---------- TELEGRAM ----------
def send(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Missing Telegram env vars")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg}, timeout=10
        )
        print(f"SENT: {msg}")
    except Exception as e:
        print(f"Telegram error: {e}")

# ---------- BYBIT ----------
def get_klines(symbol, category, interval, limit=5):
    try:
        r = requests.get(
            f"{BYBIT}/v5/market/kline",
            params={"category": category, "symbol": symbol, "interval": interval, "limit": limit},
            timeout=10
        )
        data = list(reversed(r.json()["result"]["list"]))
        return [{"start": int(x[0]), "open": float(x[1]), "high": float(x[2]),
                 "low": float(x[3]), "close": float(x[4])} for x in data]
    except Exception as e:
        print(f"Kline error {symbol}: {e}")
        return []

def get_live_price(symbol, category):
    try:
        r = requests.get(
            f"{BYBIT}/v5/market/tickers",
            params={"category": category, "symbol": symbol}, timeout=10
        )
        return float(r.json()["result"]["list"][0]["lastPrice"])
    except Exception as e:
        print(f"Price error {symbol}: {e}")
        return None

# ---------- MAIN ----------
def main():
    print("KeedSweepBot started - XAUUSD, BTCUSD, EURUSD, GBPUSD, US30 - every 10s")
    send("KeedSweepBot ONLINE ✅\nScanning XAUUSD, BTCUSD, EURUSD, GBPUSD, US30 every 10s\nSweep + 5m close inside = Signal")

    state = {s: {"swept": None, "current_5m_start": None, "done_this_hour": None} for s in SYMBOLS}

    while True:
        try:
            now = datetime.now(SA)
            current_hour = now.replace(minute=0, second=0, microsecond=0)

            for symbol, info in SYMBOLS.items():
                cat = info["category"]
                name = info["name"]
                st = state[symbol]

                if st["done_this_hour"] == current_hour:
                    continue

                # 1. REFERENCE = previous closed 1H
                h1 = get_klines(symbol, cat, "60", limit=3)
                if len(h1) < 2:
                    continue
                prev_1h = h1[-2]
                ref_high, ref_low = prev_1h["high"], prev_1h["low"]

                # 2. CURRENT 5m
                m5 = get_klines(symbol, cat, "5", limit=3)
                if len(m5) < 2:
                    continue
                current_5m = m5[-1]

                # New 5m candle? Previous one just closed - check signal
                if st["current_5m_start"] is not None and current_5m["start"] != st["current_5m_start"]:
                    closed_5m = m5[-2]
                    print(f"{name} 5m closed {closed_5m['close']} | swept={st['swept']} | ref {ref_low}-{ref_high}")

                    if st["swept"] == "high" and closed_5m["close"] < ref_high:
                        send(f"🔴 {name} SWEEP HIGH + CLOSE INSIDE\n"
                             f"1H Ref: {ref_low} - {ref_high}\n"
                             f"5m closed inside at {closed_5m['close']}\n"
                             f"Signal: SHORT | {now.strftime('%H:%M')} SA")
                        st["done_this_hour"] = current_hour
                        st["swept"] = None

                    elif st["swept"] == "low" and closed_5m["close"] > ref_low:
                        send(f"🟢 {name} SWEEP LOW + CLOSE INSIDE\n"
                             f"1H Ref: {ref_low} - {ref_high}\n"
                             f"5m closed inside at {closed_5m['close']}\n"
                             f"Signal: LONG | {now.strftime('%H:%M')} SA")
                        st["done_this_hour"] = current_hour
                        st["swept"] = None
                    else:
                        st["swept"] = None

                st["current_5m_start"] = current_5m["start"]

                # 3. LIVE PRICE SWEEP CHECK (every 10s)
                price = get_live_price(symbol, cat)
                if price is not None and st["swept"] is None:
                    if price > ref_high:
                        st["swept"] = "high"
                        print(f"{name} SWEPT HIGH! {price} > {ref_high}")
                    elif price < ref_low:
                        st["swept"] = "low"
                        print(f"{name} SWEPT LOW! {price} < {ref_low}")

            time.sleep(10)

        except Exception as e:
            print(f"Loop error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
