from flask import Flask
import threading, os

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_flask, daemon=True).start()
import yfinance as yf
import pandas as pd
import telebot
import threading
import time

BOT_TOKEN = "8752039586:AAE8Kf--uWOy9sxnz_eRDMZm003-nxOxjwQ"
CHAT_ID = "7279745404"
ALLOWED_USER_ID = 7279745404

bot = telebot.TeleBot(BOT_TOKEN)


PAIRS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "EUR/JPY": "EURJPY=X",
    "USD/JPY": "USDJPY=X",
    "XAU/USD": "GC=F",
    "US30": "^DJI",
    "NAS100": "^NDX",
    "BTC/USD": "BTC-USD",
}

LAST_SENT = {}   # ✅ OUTSIDE, after the }

sent_signals = set()

def is_allowed(message):
    if message.from_user.id != ALLOWED_USER_ID:
        bot.reply_to(message, "⛔ This bot is private.")
        return False
    return True

def get_rsi(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def check_sweep(pair_name, symbol):
    try:
        df_1h = yf.download(symbol, period="2d", interval="1h", progress=False)
        if df_1h.empty or len(df_1h) < 5:
            return None
        if isinstance(df_1h.columns, pd.MultiIndex):
            df_1h.columns = df_1h.columns.get_level_values(0)

        swing_high = df_1h['High'].iloc[-3:-1].max()
        swing_low = df_1h['Low'].iloc[-3:-1].min()
        middle = (swing_high + swing_low) / 2
        range_size = swing_high - swing_low

        df_5m = yf.download(symbol, period="1d", interval="5m", progress=False)
        if df_5m.empty or len(df_5m) < 10:
            return None
        if isinstance(df_5m.columns, pd.MultiIndex):
            df_5m.columns = df_5m.columns.get_level_values(0)

        df_5m['RSI'] = get_rsi(df_5m['Close'])

        for i in range(len(df_5m)-4, len(df_5m)-1):
            row = df_5m.iloc[i]
            candle_time = str(df_5m.index[i])
            key = f"{pair_name}-{candle_time}-{row['Close']:.2f}"
            if key in sent_signals:
                continue

            price = float(row['Close'])
            high = float(row['High'])
            low = float(row['Low'])
            rsi = float(row['RSI']) if not pd.isna(row['RSI']) else 50

            if high > swing_high and price < swing_high and rsi > 65:
                sent_signals.add(key)
                sl = high + range_size * 0.1
                tp1 = middle
                tp2 = swing_low
                tp3 = swing_low - range_size * 0.5
                return f"🚨 KeedSweep AUTO Signal\n\nSELL 🔴 {pair_name} @ {price:.5f}\nSweep of High + Closed Inside\nRSI: {rsi:.1f}\nSL: {sl:.5f}\nTP1: {tp1:.5f} (Middle - 50%)\nTP2: {tp2:.5f} (Opposite - 30%)\nTP3: {tp3:.5f} (Beyond - 20% Runner)"

            if low < swing_low and price > swing_low and rsi < 35:
                sent_signals.add(key)
                sl = low - range_size * 0.1
                tp1 = middle
                tp2 = swing_high
                tp3 = swing_high + range_size * 0.5
                return f"🚨 KeedSweep AUTO Signal\n\nBUY 🟢 {pair_name} @ {price:.5f}\nSweep of Low + Closed Inside\nRSI: {rsi:.1f}\nSL: {sl:.5f}\nTP1: {tp1:.5f} (Middle - 50%)\nTP2: {tp2:.5f} (Opposite - 30%)\nTP3: {tp3:.5f} (Beyond - 20% Runner)"
        return None
    except Exception as e:
        print(f"Error {pair_name}: {e}")
        return None

def scan_all():
    signals = []
    for name, sym in PAIRS.items():
        s = check_sweep(name, sym)
        if s:
            signals.append(s)
    return signals

def auto_loop():
    while True:
        try:
            signals = scan_all()
            filtered = []
            now = time.time()
            for s in signals:
               direction = "BUY" if "BUY" in s else "SELL" if "SELL" in s else "?"
               pair = "?"
               for p in PAIRS:
                if p in s:
                    pair = p
                    break
            key = f"{pair}-{direction}"
            if key in LAST_SENT and now - LAST_SENT[key] < 3600:
                continue
            LAST_SENT[key] = now
            filtered.append(s)
        for s in filtered:
            bot.send_message(CHAT_ID, s)
            print(f"Scan done. Found {len(signals)} sweeps")
        except Exception as e:
            print(f"Auto loop error: {e}")
        time.sleep(900)

@bot.message_handler(commands=['start'])
def start(m):
    if not is_allowed(m):
        return
    bot.reply_to(m, "KeedSweepBot ONLINE ✅\nAll 8 pairs active.\nSweep + 5m Close Inside logic ON.\nTP System B: TP1 Middle / TP2 Opposite / TP3 Beyond\nSend /scan to scan now.")

@bot.message_handler(commands=['scan'])
def scan(m):
    if not is_allowed(m):
        return
    bot.reply_to(m, "Scanning all 8 pairs for sweeps... 🔍")
    signals = scan_all()
    if not signals:
        bot.reply_to(m, "No sweeps found. Market is clean, waiting. ✅")
    else:
        for s in signals:
            bot.send_message(m.chat.id, s)

@bot.message_handler(commands=['status'])
def status(m):
    if not is_allowed(m):
        return
    bot.reply_to(m, "KeedSweepBot ONLINE ✅\n8 pairs active\nMode: Sweep + 5m Close Inside\nTP: B - Middle / Opposite / Beyond\nScan: Every 15 min")

print("Bot starting...")
threading.Thread(target=auto_loop, daemon=True).start()
bot.infinity_polling()
