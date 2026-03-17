import os
import asyncio
import requests
import csv
from datetime import datetime, timedelta
from telegram import Bot
import numpy as np
import pandas as pd

# ------------------- الإعدادات -------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
bot = Bot(token=BOT_TOKEN)

SIGNALS_FILE = "signals.csv"
TRADES_FILE = "active_trades.csv"

# ------------------- جلب العملات البديلة -------------------
def get_altcoins():
    url = "https://api.binance.com/api/v3/exchangeInfo"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            symbols = data['symbols']
            exclude = ['BTC', 'ETH', 'USDT', 'BUSD', 'USDC', 'DAI', 'TUSD', 'FDUSD']
            altcoins = []
            for s in symbols:
                if s['symbol'].endswith('USDT') and s['status'] == 'TRADING':
                    base = s['symbol'].replace('USDT', '')
                    if base not in exclude and not any(char.isdigit() for char in base):
                        altcoins.append(s['symbol'])
            return altcoins[:100]
    except:
        return []
    return []

# ------------------- جلب البيانات -------------------
def get_klines(symbol):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=4h&limit=100"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            data = r.json()
            closes = [float(x[4]) for x in data]
            highs = [float(x[2]) for x in data]
            lows = [float(x[3]) for x in data]
            volumes = [float(x[5]) for x in data]
            return closes, highs, lows, volumes
    except:
        return None, None, None, None
    return None, None, None, None

# ------------------- ADX -------------------
def calculate_adx(highs, lows, closes, period=14):
    if len(highs) < period + 1:
        return 0
    
    tr_list = []
    plus_dm_list = []
    minus_dm_list = []
    
    for i in range(1, len(highs)):
        high = highs[i]
        low = lows[i]
        prev_high = highs[i-1]
        prev_low = lows[i-1]
        prev_close = closes[i-1]
        
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_list.append(tr)
        
        plus_dm = high - prev_high if high - prev_high > prev_low - low else 0
        minus_dm = prev_low - low if prev_low - low > high - prev_high else 0
        
        plus_dm_list.append(plus_dm)
        minus_dm_list.append(minus_dm)
    
    if len(tr_list) < period:
        return 0
    
    atr = np.mean(tr_list[-period:])
    plus_di = 100 * np.mean(plus_dm_list[-period:]) / atr if atr > 0 else 0
    minus_di = 100 * np.mean(minus_dm_list[-period:]) / atr if atr > 0 else 0
    
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) > 0 else 0
    return dx

# ------------------- RSI -------------------
def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50
    deltas = np.diff(closes[-period-1:])
    gain = np.mean(deltas[deltas > 0]) if any(deltas > 0) else 0
    loss = -np.mean(deltas[deltas < 0]) if any(deltas < 0) else 0
    if loss == 0:
        return 100
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# ------------------- Stochastic -------------------
def calculate_stochastic(highs, lows, closes, period=14):
    if len(highs) < period:
        return 50
    high_max = max(highs[-period:])
    low_min = min(lows[-period:])
    if high_max - low_min == 0:
        return 50
    k = 100 * (closes[-1] - low_min) / (high_max - low_min)
    return k

# ------------------- MACD -------------------
def calculate_macd_crossover(closes):
    if len(closes) < 26:
        return False
    exp1 = pd.Series(closes).ewm(span=12).mean()
    exp2 = pd.Series(closes).ewm(span=26).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=9).mean()
    return macd_line.iloc[-1] > signal_line.iloc[-1] and macd_line.iloc[-2] <= signal_line.iloc[-2]

# ------------------- EMA -------------------
def above_ema(closes, period):
    if len(closes) < period:
        return False
    ema = pd.Series(closes).ewm(span=period).mean().iloc[-1]
    return closes[-1] > ema

# ------------------- حجم التداول -------------------
def volume_confirm(volumes):
    if len(volumes) < 10:
        return False
    avg_vol = np.mean(volumes[-10:-1])
    return volumes[-1] > avg_vol * 1.1

# ------------------- التحليل الذكي -------------------
def smart_analysis(symbol):
    closes, highs, lows, volumes = get_klines(symbol)
    if not closes or len(closes) < 50:
        return None
    
    score = 0
    reasons = []
    
    # الطبقة 1: اتجاه قوي
    adx = calculate_adx(highs, lows, closes)
    if adx > 25:
        score += 1
        reasons.append(f"ADX {round(adx,1)}")
    
    # الطبقة 2: زخم مناسب
    rsi_val = calculate_rsi(closes)
    if 40 < rsi_val < 60:
        score += 1
        reasons.append(f"RSI {round(rsi_val,1)}")
    
    # الطبقة 3: خروج من ذروة بيع
    stoch = calculate_stochastic(highs, lows, closes)
    if stoch < 20:
        score += 1
        reasons.append(f"Stoch {round(stoch,1)}")
    
    # الطبقة 4: تقاطع MACD
    if calculate_macd_crossover(closes):
        score += 2
        reasons.append("MACD Crossover")
    
    # الطبقة 5: اتجاه عام صاعد
    if above_ema(closes, 50):
        score += 1
        reasons.append("Above EMA50")
    
    # الطبقة 6: حجم تداول قوي
    if volume_confirm(volumes):
        score += 1
        reasons.append("Volume Surge")
    
    # إذا وصلت النقاط لـ 5 أو أكثر → إشارة قوية
    if score >= 5:
        price = closes[-1]
        target1 = round(price * 1.03, 6)
        target2 = round(price * 1.06, 6)
        stop = round(price * 0.97, 6)
        
        return {
            'symbol': symbol,
            'display_symbol': symbol.replace('USDT', '/USDT'),
            'entry': price,
            'target1': target1,
            'target2': target2,
            'stop': stop,
            'score': score,
            'reasons': reasons,
            'time': datetime.utcnow()
        }
    return None

# ------------------- حفظ الإشارة -------------------
def save_signal(signal):
    file_exists = os.path.isfile(SIGNALS_FILE)
    with open(SIGNALS_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['symbol', 'entry', 'target1', 'target2', 'stop', 'score', 'reasons', 'sent_time'])
        writer.writerow([
            signal['symbol'],
            signal['entry'],
            signal['target1'],
            signal['target2'],
            signal['stop'],
            signal['score'],
            '; '.join(signal['reasons']),
            signal['time'].strftime('%Y-%m-%d %H:%M:%S')
        ])

# ------------------- إضافة صفقة للمتابعة -------------------
def add_to_tracking(signal):
    file_exists = os.path.isfile(TRADES_FILE)
    with open(TRADES_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['symbol', 'entry', 'target1', 'target2', 'stop', 'status', 'entry_time', 'signal_time'])
        writer.writerow([
            signal['symbol'],
            signal['entry'],
            signal['target1'],
            signal['target2'],
            signal['stop'],
            'pending',  # بانتظار دخول المستخدم
            '',  # وقت الدخول الفعلي
            signal['time'].strftime('%Y-%m-%d %H:%M:%S')
        ])

# ------------------- إرسال الإشارة -------------------
async def send_signal(s):
    msg = f"""
🧠 **إشارة ذكية - قم بالدخول يدوياً** 🧠

💰 {s['display_symbol']}
📥 دخول: {s['entry']}
🎯 هدف 1 (3%): {s['target1']}
🎯 هدف 2 (6%): {s['target2']}
🛑 وقف (3%): {s['stop']}

⚡ نقاط القوة: {s['score']}/8
📊 الأسباب: {', '.join(s['reasons'])}
⏰ {s['time'].strftime('%Y-%m-%d %H:%M')}

⚠️ بعد الدخول، سيتم تتبع الصفقة تلقائياً
"""
    await bot.send_message(chat_id=CHAT_ID, text=msg)
    print(f"✅ Signal sent: {s['symbol']}")

# ------------------- تحديث حالة الصفقة (بعد الدخول) -------------------
def mark_as_active(symbol, entry_price):
    """لما تدخل الصفقة يدوياً، تشغل هذه الدالة (يدوياً أو عن طريق أمر)"""
    if not os.path.isfile(TRADES_FILE):
        return
    
    with open(TRADES_FILE, 'r') as f:
        rows = list(csv.DictReader(f))
    
    for row in rows:
        if row['symbol'] == symbol and row['status'] == 'pending':
            row['status'] = 'active'
            row['entry'] = entry_price
            row['entry_time'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    with open(TRADES_FILE, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['symbol', 'entry', 'target1', 'target2', 'stop', 'status', 'entry_time', 'signal_time'])
        writer.writeheader()
        writer.writerows(rows)

# ------------------- مراقبة الصفقات النشطة -------------------
async def monitor_trades():
    if not os.path.isfile(TRADES_FILE):
        return
    
    with open(TRADES_FILE, 'r') as f:
        trades = list(csv.DictReader(f))
    
    updated = False
    
    for trade in trades:
        if trade['status'] == 'active':
            symbol = trade['symbol']
            entry = float(trade['entry'])
            target1 = float(trade['target1'])
            target2 = float(trade['target2'])
            stop = float(trade['stop'])
            
            # جلب السعر الحالي
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                current = float(r.json()['price'])
                
                # تحقيق الهدف الأول
                if current >= target1 and trade.get('target1_hit') != 'yes':
                    profit = ((current - entry) / entry) * 100
                    msg = f"""
✅ **هدف أول محقق** ✅

💰 {symbol.replace('USDT', '/USDT')}
📥 دخول: {entry}
🎯 هدف 1: {target1}
📈 الربح: {profit:.2f}%
⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}
"""
                    await bot.send_message(chat_id=CHAT_ID, text=msg)
                    trade['target1_hit'] = 'yes'
                    updated = True
                
                # تحقيق الهدف الثاني
                if current >= target2 and trade.get('target2_hit') != 'yes':
                    profit = ((current - entry) / entry) * 100
                    msg = f"""
🏆 **هدف ثاني محقق** 🏆

💰 {symbol.replace('USDT', '/USDT')}
📥 دخول: {entry}
🎯 هدف 2: {target2}
📈 الربح: {profit:.2f}%
⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}
"""
                    await bot.send_message(chat_id=CHAT_ID, text=msg)
                    trade['target2_hit'] = 'yes'
                    updated = True
                    trade['status'] = 'closed'  # نغلق الصفقة تلقائياً بعد الهدف الثاني
                
                # كسر وقف الخسارة
                if current <= stop and trade.get('stop_hit') != 'yes':
                    loss = ((entry - current) / entry) * 100
                    msg = f"""
❌ **وقف خسارة** ❌

💰 {symbol.replace('USDT', '/USDT')}
📥 دخول: {entry}
🛑 وقف: {stop}
📉 الخسارة: {loss:.2f}%
⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}
"""
                    await bot.send_message(chat_id=CHAT_ID, text=msg)
                    trade['stop_hit'] = 'yes'
                    updated = True
                    trade['status'] = 'closed'
    
    if updated:
        with open(TRADES_FILE, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['symbol', 'entry', 'target1', 'target2', 'stop', 'status', 'entry_time', 'signal_time', 'target1_hit', 'target2_hit', 'stop_hit'])
            writer.writeheader()
            writer.writerows(trades)

# ------------------- الرئيسية -------------------
async def main():
    print(f"🧠 Smart Tracker running at {datetime.utcnow()}")
    
    # 1. البحث عن إشارات جديدة
    coins = get_altcoins()
    print(f"✅ {len(coins)} coins loaded")
    
    for coin in coins:
        signal = smart_analysis(coin)
        if signal:
            await send_signal(signal)
            save_signal(signal)
            add_to_tracking(signal)
            await asyncio.sleep(3)
    
    # 2. مراقبة الصفقات النشطة
    await monitor_trades()
    
    print("✅ Scan complete")

if __name__ == "__main__":
    asyncio.run(main())
