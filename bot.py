# v2 fix
import os, threading, requests, time
threading.Thread(target=lambda: __import__('http.server').HTTPServer(('0.0.0.0', int(os.environ.get('PORT',10000))), __import__('http.server').BaseHTTPRequestHandler).serve_forever(), daemon=True).start()
threading.Thread(target=keep_alive, daemon=True).start()
import requests, time, os
TOKEN = os.environ.get('BOT_TOKEN')
CHAT_ID = 7279745404

def send(t):
    requests.post(f'https://api.telegram.org/bot{TOKEN}/sendMessage', data={'chat_id': CHAT_ID, 'text': t})

def get_data(s, i, r):
    d = requests.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{s}?interval={i}&range={r}', headers={'User-Agent':'Mozilla/5.0'}).json()['chart']['result'][0]['indicators']['quote'][0]
    return d['high'], d['low'], d['close']

def check(sym, name):
    try:
        h, l, c = get_data(sym, '1h', '1d')
        hi = max(h[-3:])
        lo = min(l[-3:])
        cl = c[-1]
        if cl > hi: send(f'🚨 {name} BREAKOUT UP! {cl:.2f} broke {hi:.2f}')
        elif cl < lo: send(f'🚨 {name} BREAKOUT DOWN! {cl:.2f} broke {lo:.2f}')
    except Exception as e:
        print(e)

send('🔥 KeedSweepBot ONLINE on Render!')
while True:
    check('BTC-USD','BTC')
    check('ETH-USD','ETH')
    check('XAUUSD=X','GOLD')
    time.sleep(3600)
