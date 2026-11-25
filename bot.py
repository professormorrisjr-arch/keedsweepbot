import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=10)

# For UptimeRobot - keeps bot awake
@app.route("/", methods=["GET"])
def home():
    return "KeedSweepBot is LIVE", 200

# For TradingView - receives Strategy 1 & 2
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)

    pair = data.get("pair", "")
    strategy = data.get("strategy", "")
    direction = data.get("direction", "")
    entry = data.get("entry", "")
    sl = data.get("sl", "")
    tp1 = data.get("tp1", "")
    tp2 = data.get("tp2", "")
    prev_high = data.get("prev_high", "")
    prev_low = data.get("prev_low", "")

    emoji = "🔴" if direction == "SELL" else "🟢"
    msg = f"{emoji} {direction} {pair} - {strategy}\nEntry: {entry}\nSL: {sl}\nTP1: {tp1} (50%)\nTP2: {tp2} (Opposite Line)\nPrev 1H High: {prev_high} | Low: {prev_low}"

    send_telegram(msg)
    return jsonify({"status": "sent"}), 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
