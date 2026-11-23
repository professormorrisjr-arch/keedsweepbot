import os
import time
import threading
import yfinance as yf
import pandas as pd
import numpy as np
import telebot

# --- TOKEN - works with BOTH names ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN") or ""
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("CHAT_ID") or ""

if not TOKEN:
    print("❌ ERROR: No BOT TOKEN found. Add TELEGRAM_BOT_TOKEN in Render > Environment")
    raise SystemExit(1)

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# --- PAIRS TO SCAN ---
PAIRS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "USDJPY=X",
    "AUD/USD": "AUDUSD=X",
    "USD/CAD": "USDCAD=X",
    "XAU/USD": "GC=F",
    "BTC/USD": "BTC-USD",
    "ETH/USD": "ETH-USD",
}

def get_signal(symbol):
    try:
        df = yf.download(symbol, period="1d", interval="15m", progress=False)
        if df is None or len(df) < 50:
            return None
        # Flatten columns if needed
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        close = df["Close"]
        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rs = gain / (loss + 0.000001)
        rsi = 100 - (100 / (1 + rs))
        last_rsi = float(rsi.iloc[-1])
        last_price = float(close.iloc[-1])
        # EMA
        ema_fast = close.ewm(span=9).mean().iloc[-1]
        ema_slow = close.ewm(span=21).mean().iloc[-1]

        if last_rsi < 32 and ema_fast > ema_slow:
            return ("BUY 🟢", last_price, round(last_rsi, 1))
        if last_rsi > 68 and ema_fast < ema_slow:
            return ("SELL 🔴", last_price, round(last_rsi, 1))
        return None
    except Exception as e:
        print(f"Error scanning {symbol}: {e}")
        return None

def scan_all():
    results = []
    for name, symbol in PAIRS.items():
        sig = get_signal(symbol)
        if sig:
            direction, price, rsi = sig
            results.append(f"{direction} <b>{name}</b> @ {price:.5f} | RSI: {rsi}")
        time.sleep(1)
    return results

@bot.message_handler(commands=['start', 'help'])
def start(msg):
    bot.reply_to(msg, "👋 <b>KeedSweepBot ONLINE</b>\n\nCommands:\n/scan - Scan all pairs now\n/status - Check bot status\n\nI auto-scan every 30 mins and send signals here.")
    if CHAT_ID:
        try:
            bot.send_message(CHAT_ID, "✅ KeedSweepBot connected to your chat!")
        except:
            pass

@bot.message_handler(commands=['status'])
def status(msg):
    bot.reply_to(msg, "✅ Bot is running.\nPairs: EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CAD, XAU/USD, BTC/USD, ETH/USD")

@bot.message_handler(commands=['scan'])
def scan_cmd(msg):
    bot.reply_to(msg, "🔍 Scanning... give me 20 seconds...")
    results = scan_all()
    if results:
        text = "📊 <b>KeedSweep Signals</b>\n\n" + "\n".join(results)
    else:
        text = "📊 <b>KeedSweep Scan Complete</b>\n\nNo strong signals right now. Market is ranging. Wait for next scan."
    bot.send_message(msg.chat.id, text)

def auto_scan_loop():
    # Wait 60s after start, then every 30 mins
    time.sleep(60)
    while True:
        try:
            if CHAT_ID:
                results = scan_all()
                if results:
                    text = "🚨 <b>KeedSweep AUTO Signal</b>\n\n" + "\n".join(results) + "\n\nTrade with proper risk management."
                    bot.send_message(CHAT_ID, text)
        except Exception as e:
            print(f"Auto scan error: {e}")
        time.sleep(1800)  # 30 mins

if __name__ == "__main__":
    print("✅ KeedSweepBot ONLINE")
    t = threading.Thread(target=auto_scan_loop, daemon=True)
    t.start()
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
