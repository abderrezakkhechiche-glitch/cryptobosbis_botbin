import os
import asyncio
import requests
import csv
from datetime import datetime
from telegram import Bot
import numpy as np
import pandas as pd

# ------------------- الإعدادات -------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
bot = Bot(token=BOT_TOKEN)

# ------------------- جلب العملات البديلة -------------------
def get_altcoins():
    url = "https://api.binance.com/api/v3/exchangeInfo"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        symbols = data['symbols']
        exclude = ['BTC', 'ETH', 'USDT', 'BUSD', 'USDC', 'DAI']
        altcoins = []
        for s in symbols:
            if s['symbol'].endswith('USDT') and s['status'] == 'TRADING':
                base = s['symbol'].replace('USDT', '')
                if base not in exclude:
                    altcoins.append(s['symbol'])
        return altcoins[:50]  # أول 50 عملة
    return []

# ------------------- جلب البيانات -------------------
def get_klines(symbol):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=4h&limit=30"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            data = r.json()
            closes = [float(x[4]) for x in data]
            return closes
    except:
        return None
    return None

# ------------------- RSI -------------------
def calculate_rsi(closes):
    if len(closes) < 15:
        return 50
    deltas = np.diff(closes)
    gain = np.mean(deltas[deltas > 0]) if any(deltas > 0) else 0
    loss = -np.mean(deltas[deltas < 0]) if any(deltas < 0) else 0
    if loss == 0:
        return 100
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# ------------------- MACD -------------------
def macd_positive(closes):
    if len(closes) < 26:
        return False
    exp1 = pd.Series(closes).ewm(span=12).mean()
    exp2 = pd.Series(closes).ewm(span=26).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9).mean()
    return macd.iloc[-1] > signal.iloc[-1]

# ------------------- EMA9 -------------------
def above_ema9(closes):
    if len(closes) < 10:
        return False
    ema = pd.Series(closes).ewm(span=9).mean().iloc[-1]
    return closes[-1] > ema

# ------------------- التحليل السريع -------------------
def fast_analysis(symbol):
    closes = get_klines(symbol)
    if not closes or len(closes) < 26:
        return None

    conditions = []
    reasons = []

    # شرط RSI
    rsi_val = calculate_rsi(closes)
    if rsi_val < 45:
        conditions.append(True)
        reasons.append(f"RSI {round(rsi_val,1)}")
    else:
        conditions.append(False)

    # شرط EMA9
    if above_ema9(closes):
        conditions.append(True)
        reasons.append("EMA9+")
    else:
        conditions.append(False)

    # شرط MACD
    if macd_positive(closes):
        conditions.append(True)
        reasons.append("MACD+")
    else:
        conditions.append(False)

    # إذا تحقق شرط واحد على الأقل → إشارة
    if any(conditions):
        price = closes[-1]
        target = round(price * 1.04, 6)  # هدف 4%
        return {
            'symbol': symbol.replace('USDT', '/USDT'),
            'entry': round(price, 6),
            'target': target,
            'rsi': round(rsi_val, 1),
            'reasons': reasons,
            'time': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        }
    return None

# ------------------- إرسال الإشارة -------------------
async def send_signal(s):
    msg = f"""
⚡ **إشارة سريعة جداً** ⚡

💰 {s['symbol']}
📥 الدخول: {s['entry']}
🎯 الهدف (4%): {s['target']}
📊 RSI: {s['rsi']}
📈 الأسباب: {', '.join(s['reasons'])}
⏰ {s['time']}
"""
    await bot.send_message(chat_id=CHAT_ID, text=msg)
    print(f"✅ Signal sent: {s['symbol']}")

# ------------------- الرئيسية -------------------
async def main():
    print("⚡ Ultra Fast Strategy running...")
    coins = get_altcoins()
    print(f"✅ {len(coins)} coins loaded")

    for coin in coins:
        signal = fast_analysis(coin)
        if signal:
            await send_signal(signal)
            await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(main())
