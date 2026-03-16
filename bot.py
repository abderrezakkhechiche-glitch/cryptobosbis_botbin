import os
import asyncio
import requests
from datetime import datetime
from telegram import Bot
import pandas as pd
import numpy as np

# ------------------- الإعدادات -------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
bot = Bot(token=BOT_TOKEN)

# ------------------- جلب جميع أزواج USDT من بايننس -------------------
def get_all_usdt_pairs():
    url = "https://api.binance.com/api/v3/exchangeInfo"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        symbols = data['symbols']
        usdt_pairs = [s['symbol'] for s in symbols if s['symbol'].endswith('USDT') and s['status'] == 'TRADING']
        return usdt_pairs
    return []

# ------------------- جلب بيانات الشموع -------------------
def get_klines(symbol, interval='1h', limit=50):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        closes = [float(x[4]) for x in data]
        return closes
    return None

# ------------------- حساب RSI -------------------
def calculate_rsi(closes, period=14):
    deltas = np.diff(closes)
    seed = deltas[:period+1]
    up = seed[seed >= 0].sum()/period
    down = -seed[seed < 0].sum()/period
    rs = up/down
    rsi = np.zeros_like(closes)
    rsi[:period] = 100 - 100/(1+rs)
    
    for i in range(period, len(closes)):
        delta = deltas[i-1]
        if delta > 0:
            upval = delta
            downval = 0
        else:
            upval = 0
            downval = -delta
        up = (up*(period-1) + upval)/period
        down = (down*(period-1) + downval)/period
        rs = up/down
        rsi[i] = 100 - 100/(1+rs)
    return rsi

# ------------------- حساب المتوسطات المتحركة -------------------
def calculate_ema(closes, period):
    return pd.Series(closes).ewm(span=period, adjust=False).mean().values

# ------------------- التحليل الفني -------------------
def analyze_symbol(symbol):
    closes = get_klines(symbol)
    if not closes or len(closes) < 30:
        return None
    
    rsi = calculate_rsi(closes)[-1]
    ema9 = calculate_ema(closes, 9)[-1]
    ema21 = calculate_ema(closes, 21)[-1]
    current_price = closes[-1]
    prev_price = closes[-2]
    
    buy_signal = False
    reason = ""
    
    if rsi < 40 and current_price > ema9 and ema9 > ema21 and current_price > prev_price:
        buy_signal = True
        reason = f"RSI={rsi:.1f}, EMA9↑EMA21"
    
    if buy_signal:
        target1 = round(current_price * 1.03, 2)
        target2 = round(current_price * 1.05, 2)
        stop_loss = round(current_price * 0.98, 2)
        
        return {
            'symbol': symbol,
            'entry': current_price,
            'target1': target1,
            'target2': target2,
            'stop_loss': stop_loss,
            'rsi': round(rsi, 2),
            'reason': reason,
            'time': datetime.utcnow()
        }
    return None

# ------------------- إرسال توصية -------------------
async def send_signal(signal):
    message = f"""
🚀 إشارة شراء جديدة 🚀

💰 العملة: {signal['symbol']}
📥 سعر الدخول: {signal['entry']}
🎯 الهدف الأول (3%): {signal['target1']}
🎯 الهدف الثاني (5%): {signal['target2']}
🛑 وقف الخسارة: {signal['stop_loss']}

📊 RSI: {signal['rsi']}
📈 سبب: {signal['reason']}
⏰ الوقت: {signal['time'].strftime('%Y-%m-%d %H:%M:%S')}
"""
    await bot.send_message(chat_id=CHAT_ID, text=message)
    print(f"✅ Signal sent for {signal['symbol']}")

# ------------------- الرئيسية -------------------
async def main():
    print(f"🔍 Fetching all USDT pairs from Binance...")
    all_pairs = get_all_usdt_pairs()
    print(f"✅ Found {len(all_pairs)} USDT pairs")
    
    print(f"🔍 Analyzing at {datetime.utcnow()}")
    for symbol in all_pairs:
        signal = analyze_symbol(symbol)
        if signal:
            await send_signal(signal)
            await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(main())
