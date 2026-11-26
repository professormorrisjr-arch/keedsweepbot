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
# WINDOW: 00:00 - 00:15 only. 3 x 5M candles: 00-05, 05-10, 10-15
# RULE: ANY of those 3 candles that sweeps MUST close back inside
# Prev High / Prev Low = previous 1H candle High / Low - unchanged
# Live forming candle is NEVER used, only fully closed candles
def check_strategy_1_with_5m(df_5m, prev_high, prev_low, now):
    # Drop live forming candle - only closed candles
    df_closed = df_5m.iloc[:-1]

    # Only candles from THIS hour, in the 00-15 window
    window = []
    for idx, c in df_closed.iterrows():
        # idx is timestamp from yfinance
        ts = idx.to_pydatetime() if hasattr(idx, 'to_pydatetime') else idx
        # Convert to UTC for comparison
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts.year == now.year and ts.month == now.month and ts.day == now.day and ts.hour == now.hour and ts.minute < 15:
            window.append(c)

    # Should be max 3 candles: 00, 05, 10
    mid = (prev_high + prev_low) / 2
    for c in window:
        high = float(c['High'])
        low = float(c['Low'])
        close = float(c['Close'])

        # SELL: swept ABOVE Prev High + SAME 5M candle CLOSED BELOW Prev High (inside range)
        if high > prev_high and close < prev_high:
            return {
                'type': 'SELL', 'strategy': 'STRATEGY 1 - Sweep High',
                'entry': close, 'sl': high,
                'tp1': mid, 'tp2': prev_low,
                'prev_high': prev_high, 'prev_low': prev_low
            }
        # BUY: swept BELOW Prev Low + SAME 5M candle CLOSED ABOVE Prev Low (inside range)
        if low < prev_low and close > prev_low:
            return {
                'type': 'BUY', 'strategy': 'STRATEGY 1 - Sweep Low',
                'entry': close, 'sl': low,
                'tp1': mid, 'tp2': prev_high,
                'prev_high': prev_high, 'prev_low': prev_low
            }
    return None

# ============ STRATEGY 2: UNCHANGED ============
def check_strategy_2_with_1m(df_1m, prev_high, prev_low):
    mid = (prev_high + prev_low) / 2
    rng = prev_high - prev_low
    if rng == 0:
        return None
    df_closed = df_1m.iloc[:-1]  # ignore live 1M candle
    recent = df_closed.iloc[-60:]
    if len(recent) < 10:
        return None
    close = float(df_closed.iloc[-1]['Close'])
    lows = [float(x) for x in recent['Low']]
    highs = [float(x) for x in recent['High']]

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
                    df_1h = get_data(symbol, "1h", "2d")
                    if df_1h is None:
                        continue
                    # Prev 1H candle = H and L we both know
                    prev = df_1h.iloc[-2]
                    prev_high = float(prev['High'])
                    prev_low = float(prev['Low'])
                    sig = None

                    # STRATEGY 1 - ONLY 00-15 window
                    if 0 <= now.minute <= 15:
                        df_5m = get_data(symbol, "5m", "1d")
                        if df_5m is not None:
                            sig = check_strategy_1_with_5m(df_5m, prev_high, prev_low, now)

                    # STRATEGY 2 IF NO STRATEGY 1
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
