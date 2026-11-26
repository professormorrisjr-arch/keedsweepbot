import os
import time
import requests
from datetime import datetime, timezone
import yfinance as yf

# --- CONFIG ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# LOCKED 12 PAIRS - DO NOT CHANGE
PAIRS = {
    "GBPUSD": "GBPUSD=X",
    "GBPJPY": "GBPJPY=X",
    "EURUSD": "EURUSD=X",
    "XAUUSD": "GC=F",
    "US30": "^DJI",
    "NAS100": "^IXIC",
    "USDJPY": "USDJPY=X",
    "USDCAD": "USDCAD=X",
    "BTCUSD": "BTC-USD",
    "AUDUSD": "AUDUSD=X",
    "NZDUSD": "NZDUSD=X",
    "EURJPY": "EURJPY=X",
}

sent_signals = set()

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

def format_signal(pair, sig):
    return (
        f"📊 {sig['type']} {pair}\n"
        f"🕯️ {sig['strategy']}\n"
        f"🎯 Entry: {sig['entry']:.2f}\n"
        f"🛑 SL: {sig['sl']:.2f}\n"
        f"✅ TP1: {sig['tp1']:.2f} (Mid)\n"
        f"✅ TP2: {sig['tp2']:.2f} (Opposite Line)\n"
        f"📌 Prev High: {sig['prev_high']:.2f} | Low: {sig['prev_low']:.2f}\n"
        f"🕒 Time: {datetime.now(timezone.utc).strftime('%H:%M')} UTC"
    )

def get_data(symbol, interval, period):
    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if df is None or len(df) < 5:
        return None
    return df

# ============ STRATEGY 1: 1H Levels + 5M Confirmation ============
# Time: XX:00 - XX:15 only
# RULE: 5M candle must SWEEP past Prev High/Low AND CLOSE back inside range
# FIXED: Ignore live forming candle, only use fully closed candles
def check_strategy_1_with_5m(df_5m, prev_high, prev_low):
    # EXCLUDE last candle - it's still forming, not closed yet
    # Only check last 3 FULLY CLOSED 5M candles
    recent = df_5m.iloc[-4:-1]
    mid = (prev_high + prev_low) / 2
    for _, c in recent.iterrows():
        high = float(c['High'])
        low = float(c['Low'])
        close = float(c['Close'])
        # SELL: 5M wick ABOVE Prev High + SAME 5M candle CLOSED BELOW Prev High
        if high > prev_high and close < prev_high:
            return {
                'type': 'SELL', 'strategy': 'STRATEGY 1 - Sweep High',
                'entry': close, 'sl': high,
                'tp1': mid, 'tp2': prev_low,
                'prev_high': prev_high, 'prev_low': prev_low
            }
        # BUY: 5M wick BELOW Prev Low + SAME 5M candle CLOSED ABOVE Prev Low
        if low < prev_low and close > prev_low:
            return {
                'type': 'BUY', 'strategy': 'STRATEGY 1 - Sweep Low',
                'entry': close, 'sl': low,
                'tp1': mid, 'tp2': prev_high,
                'prev_high': prev_high, 'prev_low': prev_low
            }
    return None

# ============ STRATEGY 2: 1H Levels + 1M Confirmation ============
# Time: XX:00 - XX:59
# 1M Double Top/Bottom near Prev High/Low + 1M neckline break = Signal
# FIXED: Ignore live forming 1M candle
def check_strategy_2_with_1m(df_1m, prev_high, prev_low):
    mid = (prev_high + prev_low) / 2
    rng = prev_high - prev_low
    if rng == 0:
        return None
    # EXCLUDE last 1M candle - still forming
    df_closed = df_1m.iloc[:-1]
    recent = df_closed.iloc[-60:]
    if len(recent) < 10:
        return None
    close = float(df_closed.iloc[-1]['Close'])
    lows = [float(x) for x in recent['Low']]
    highs = [float(x) for x in recent['High']]

    # DOUBLE BOTTOM - BUY AT PREV LOW
    bottoms = [l for l in lows if abs(l - prev_low) <= rng * 0.15]
    if len(bottoms) >= 2:
        neckline = max([float(x) for x in recent['High']])
        if close > neckline:
            sl = min(bottoms) - rng * 0.05
            return {
                'type': 'BUY', 'strategy': 'STRATEGY 2 - Double Bottom',
                'entry': close, 'sl': sl,
                'tp1': mid, 'tp2': prev_high,
                'prev_high': prev_high, 'prev_low': prev_low
            }

    # DOUBLE TOP - SELL AT PREV HIGH
    tops = [h for h in highs if abs(h - prev_high) <= rng * 0.15]
    if len(tops) >= 2:
        neckline = min([float(x) for x in recent['Low']])
        if close < neckline:
            sl = max(tops) + rng * 0.05
            return {
                'type': 'SELL', 'strategy': 'STRATEGY 2 - Double Top',
                'entry': close, 'sl': sl,
                'tp1': mid, 'tp2': prev_low,
                'prev_high': prev_high, 'prev_low': prev_low
            }
    return None

def main():
    send_telegram("✅ KeedSweepBot v3 LIVE - Locked 12 Pairs | 1H Levels | 5M S1 | 1M S2")
    while True:
        try:
            now = datetime.now(timezone.utc)
            hour_key = now.strftime("%Y-%m-%d-%H")
            for pair, symbol in PAIRS.items():
                try:
                    # 1H LEVELS - candle that just closed
                    df_1h = get_data(symbol, "1h", "2d")
                    if df_1h is None:
                        continue
                    prev = df_1h.iloc[-2]
                    prev_high = float(prev['High'])
                    prev_low = float(prev['Low'])
                    sig = None

                    # STRATEGY 1 FIRST (00-15 min, 5M confirmation)
                    if 0 <= now.minute <= 15:
                        df_5m = get_data(symbol, "5m", "1d")
                        if df_5m is not None:
                            sig = check_strategy_1_with_5m(df_5m, prev_high, prev_low)

                    # STRATEGY 2 IF NO STRATEGY 1 (00-59 min, 1M confirmation)
                    if sig is None:
                        df_1m = get_data(symbol, "1m", "1d")
                        if df_1m is not None:
                            sig = check_strategy_2_with_1m(df_1m, prev_high, prev_low)

                    if sig:
                        key = f"{hour_key}-{pair}-{sig['strategy']}-{sig['type']}"
                        if key not in sent_signals:
                            sent_signals.add(key)
                            send_telegram(format_signal(pair, sig))
                            print(f"SENT: {pair} {sig['type']} {sig['strategy']}")
                except Exception as e:
                    print(f"Error {pair}: {e}")
                    continue
            time.sleep(60)
        except Exception as e:
            print(f"Loop error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
