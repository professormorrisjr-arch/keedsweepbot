# KeedSweepBot - TradingView Webhook Version - FINAL
# TradingView does the chart work, bot receives webhook -> sends to Telegram
# Deploy on Render as Web Service

import os
import requests
from flask import Flask, request, jsonify
from datetime import datetime, timezone

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Pairs allowed - 12 pairs final
PAIRS = [
    "EURUSD", "GBPUSD", "GBPJPY", "EURJPY", "EURGBP", "BTCUSD",
    "US30", "NAS100", "USDCAD", "USDCHF", "XAUUSD", "USDJPY"
]

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")

def format_signal(data):
    pair = data.get("pair", "UNKNOWN")
    strategy = data.get("strategy", "")
    direction = data.get("direction", "")
    entry = data.get("entry", "")
    sl = data.get("sl", "")
    tp1 = data.get("tp1", "")
    tp2 = data.get("tp2", "")
    prev_high = data.get("prev_high", "")
    prev_low = data.get("prev_low", "")

    emoji = "🔴" if direction == "SELL" else "🟢"
    return (
        f"{emoji} {direction} {pair} - {strategy}\n"
        f"Entry: {entry}\n"
        f"SL: {sl}\n"
        f"TP1: {tp1} (50%)\n"
        f"TP2: {tp2} (Opposite Line)\n"
        f"Prev 1H High: {prev_high} | Low: {prev_low}\n"
        f"Time: {datetime.now(timezone.utc).strftime('%H:%M')} UTC"
    )

@app.route("/", methods=["GET"])
def home():
    return "KeedSweepBot is LIVE - Waiting for TradingView webhook", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
        print(f"Webhook received: {data}")

        pair = data.get("pair", "").upper()
        # Clean TradingView symbol: e.g. OANDA:EURUSD -> EURUSD, BINANCE:BTCUSDT -> BTCUSD
        pair = pair.replace("OANDA:", "").replace("BINANCE:", "").replace("USDT", "").replace("USD", "USD")
        # Simple clean: keep only letters
        # If pair not in list, still allow but warn
        if pair not in PAIRS:
            print(f"Pair {pair} not in allowed list, but forwarding anyway")

        # Only forward if it's our strategies
        strategy = data.get("strategy", "")
        if "STRATEGY" not in strategy:
            print(f"Ignored - not a strategy signal: {strategy}")
            return jsonify({"status": "ignored"}), 200

        msg = format_signal(data)
        send_telegram(msg)
        print(f"Sent to Telegram: {msg}")
        return jsonify({"status": "sent"}), 200

    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({"status": "error", "error": str(e)}), 400

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    send_telegram("✅ KeedSweepBot is LIVE - TradingView Webhook Connected - 12 Pairs")
    app.run(host="0.0.0.0", port=port)
