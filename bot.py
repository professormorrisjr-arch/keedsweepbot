import os, time, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import yfinance as yf
import telebot

TOKEN = os.environ.get("9150633810:AAGGV8HhMKapNFmHdBXYt5NnGzmznbN9N50")
CHAT_ID = os.environ.get("7279745404", "")  # optional, bot will send to whoever did /start
bot = telebot.TeleBot(TOKEN)

# Keep alive for Render Free
def keep_alive():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), BaseHTTPRequestHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
keep_alive()

SYMBOLS = {
    "XAUUSD": "GC=F",
    "BTCUSD": "BTC-USD",
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "US30": "^DJI"
}

users = set()
sent_signals = set()  # to avoid sending same signal twice

@bot.message_handler(commands=['start'])
def start(m):
    users.add(m.chat.id)
    bot.reply_to(m, "🔥 KeedSweepBot ONLINE! - Hunting EVERY HOUR\nPairs: XAUUSD, BTCUSD, EURUSD, GBPUSD, US30\nRule: Sweep 1H High/Low + 5min Close Back Inside\nSL = Wick, TP = Opposite 1H Range")

def check_pair(name, ticker):
    try:
        # Get 1H data - last 2 candles
        df1h = yf.download(ticker, period="2d", interval="1h", progress=False)
        if len(df1h) < 2:
            return None
        # Previous CLOSED 1H candle = range
        prev = df1h.iloc[-2]
        range_high = float(prev['High'])
        range_low = float(prev['Low'])
        range_time = str(df1h.index[-2])

        # Get 5min data - last 12 candles = current hour
        df5 = yf.download(ticker, period="1d", interval="5m", progress=False)
        if len(df5) < 2:
            return None
        # Last closed 5min candle
        last5 = df5.iloc[-2]
        high5 = float(last5['High'])
        low5 = float(last5['Low'])
        close5 = float(last5['Close'])
        time5 = str(df5.index[-2])

        # Key to avoid duplicate
        key = f"{name}-{range_time}-{time5}"

        # SELL Sweep: wick above high, close back below high
        if high5 > range_high and close5 < range_high and key not in sent_signals:
            sent_signals.add(key)
            return f"🔴 SELL SWEEP - {name}\n\n1H Range: {range_low:.2f} - {range_high:.2f}\nSwept: {high5:.2f}\n5min Close Back: {close5:.2f}\n\nEntry: {close5:.2f}\nSL: {high5:.2f} (wick)\nTP: {range_low:.2f} (opposite range)\n\nDEMO ONLY - Wait for YES"

        # BUY Sweep: wick below low, close back above low
        if low5 < range_low and close5 > range_low and key not in sent_signals:
            sent_signals.add(key)
            return f"🟢 BUY SWEEP - {name}\n\n1H Range: {range_low:.2f} - {range_high:.2f}\nSwept: {low5:.2f}\n5min Close Back: {close5:.2f}\n\nEntry: {close5:.2f}\nSL: {low5:.2f} (wick)\nTP: {range_high:.2f} (opposite range)\n\nDEMO ONLY - Wait for YES"
        return None
    except Exception as e:
        print(f"Error {name}: {e}")
        return None

def hunt_loop():
    while True:
        for name, ticker in SYMBOLS.items():
            sig = check_pair(name, ticker)
            if sig and users:
                for uid in users:
                    try:
                        bot.send_message(uid, sig)
                    except Exception as e:
                        print(e)
            time.sleep(2)
        print("Hunt done, waiting 5min...")
        time.sleep(300)  # check every 5 min = every hour it will catch the sweep

threading.Thread(target=hunt_loop, daemon=True).start()
print("✅ KeedSweepBot ONLINE")
bot.infinity_polling()
