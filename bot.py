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

# ------------------- ملفات البيانات -------------------
SIGNALS_FILE = "signals_sent.csv"  # الإشارات التي أرسلها البوت
TRADES_FILE = "active_trades.csv"  # الصفقات التي دخلتها أنت لمتابعتها

# ------------------- جلب جميع أزواج USDT -------------------
def get_all_usdt_pairs():
    url = "https://api.binance.com/api/v3/exchangeInfo"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        symbols = data['symbols']
        # استبعاد العملات المستقرة (USDT, BUSD, USDC, DAI, TUSD, UST, etc.)
        exclude = ['USDT', 'BUSD', 'USDC', 'DAI', 'TUSD', 'UST', 'FDUSD']
        usdt_pairs = [
            s['symbol'] for s in symbols 
            if s['symbol'].endswith('USDT') 
            and s['status'] == 'TRADING'
            and not any(x in s['symbol'] for x in exclude)
        ]
        return usdt_pairs
    return []

# ------------------- جلب بيانات الشموع -------------------
def get_klines(symbol, interval='1h', limit=50):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            closes = [float(x[4]) for x in data]
            volumes = [float(x[5]) for x in data]
            return closes, volumes
    except:
        return None, None
    return None, None

# ------------------- حساب RSI -------------------
def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50
    deltas = np.diff(closes)
    gain = np.mean(deltas[deltas > 0]) if any(deltas > 0) else 0
    loss = -np.mean(deltas[deltas < 0]) if any(deltas < 0) else 0
    if loss == 0:
        return 100
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# ------------------- حساب MACD -------------------
def calculate_macd(closes):
    if len(closes) < 26:
        return False
    exp1 = pd.Series(closes).ewm(span=12, adjust=False).mean()
    exp2 = pd.Series(closes).ewm(span=26, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    
    # تقاطع إيجابي (MACD فوق Signal)
    if macd_line.iloc[-1] > signal_line.iloc[-1] and macd_line.iloc[-2] <= signal_line.iloc[-2]:
        return True
    return False

# ------------------- حساب المتوسط المتحرك -------------------
def calculate_ema(closes, period):
    return pd.Series(closes).ewm(span=period, adjust=False).mean().iloc[-1]

# ------------------- حساب متوسط الحجم -------------------
def calculate_avg_volume(volumes, period=20):
    if len(volumes) < period:
        return 0
    return np.mean(volumes[-period:])

# ------------------- التحليل الفني -------------------
def analyze_symbol(symbol):
    closes, volumes = get_klines(symbol)
    if not closes or len(closes) < 30 or not volumes:
        return None
    
    # المؤشرات
    rsi = calculate_rsi(closes)
    macd_buy = calculate_macd(closes)
    ema9 = calculate_ema(closes, 9)
    current_price = closes[-1]
    avg_volume = calculate_avg_volume(volumes)
    current_volume = volumes[-1]
    
    # شروط الدخول
    buy_signal = (
        rsi < 35 and                # ذروة بيع
        macd_buy and                 # تقاطع MACD إيجابي
        current_price > ema9 and     # فوق المتوسط القصير
        current_volume > avg_volume  # حجم تداول أعلى من المتوسط
    )
    
    if buy_signal:
        # هدف عشوائي بين 4% و 5%
        target_percent = np.random.uniform(4.0, 5.0)
        target_price = round(current_price * (1 + target_percent/100), 4)
        
        return {
            'symbol': symbol.replace('USDT', '/USDT'),
            'buy_at': round(current_price, 4),
            'target': target_price,
            'term': '0 - 10 Days',
            'exchange': 'Binance',
            'entry_price': current_price,
            'target_percent': round(target_percent, 2)
        }
    return None

# ------------------- حفظ الإشارة المرسلة -------------------
def save_signal(signal):
    file_exists = os.path.isfile(SIGNALS_FILE)
    with open(SIGNALS_FILE, 'a', newline='') as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(['symbol', 'buy_at', 'target', 'term', 'exchange', 'sent_time'])
        writer.writerow([
            signal['symbol'],
            signal['buy_at'],
            signal['target'],
            signal['term'],
            signal['exchange'],
            datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        ])

# ------------------- إرسال الإشارة -------------------
async def send_signal(signal):
    message = f"""
**MYH Bot**
Symbol: {signal['symbol']}
Buy at: {signal['buy_at']} or less
Target: {signal['target']}
Term: {signal['term']}
Exchange: {signal['exchange']}
"""
    await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode='Markdown')
    print(f"✅ Signal sent: {signal['symbol']}")
    
    # حفظ الإشارة
    save_signal(signal)
    
    # إضافة الصفقة للمتابعة (افتراضيًا بانتظار دخولك)
    add_to_pending(signal)

# ------------------- إضافة صفقة للمتابعة -------------------
def add_to_pending(signal):
    file_exists = os.path.isfile(TRADES_FILE)
    with open(TRADES_FILE, 'a', newline='') as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(['symbol', 'entry_price', 'target', 'status', 'entry_time', 'sent_time'])
        writer.writerow([
            signal['symbol'],
            signal['buy_at'],
            signal['target'],
            'pending',  # بانتظار أن يدخلها المستخدم
            '',
            datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        ])

# ------------------- مراقبة الصفقات النشطة -------------------
async def monitor_active_trades():
    if not os.path.isfile(TRADES_FILE):
        return
    
    with open(TRADES_FILE, 'r') as file:
        reader = csv.DictReader(file)
        trades = list(reader)
    
    changed = False
    updated_trades = []
    
    for trade in trades:
        if trade['status'] == 'active':
            # جلب السعر الحالي
            symbol_clean = trade['symbol'].replace('/', '')
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol_clean}"
            response = requests.get(url)
            
            if response.status_code == 200:
                current = float(response.json()['price'])
                target = float(trade['target'])
                
                if current >= target:
                    # هدف محقق
                    entry = float(trade['entry_price'])
                    profit = ((current - entry) / entry) * 100
                    
                    message = f"""
✅ **هدف محقق** ✅

العملة: {trade['symbol']}
سعر الدخول: {entry}
السعر الحالي: {current}
نسبة الربح: {profit:.2f}%
الهدف: {target}
🎯 تم تحقيق الهدف بنجاح!
"""
                    await bot.send_message(chat_id=CHAT_ID, text=message)
                    trade['status'] = 'closed'
                    changed = True
        
        updated_trades.append(trade)
    
    if changed:
        with open(TRADES_FILE, 'w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=['symbol', 'entry_price', 'target', 'status', 'entry_time', 'sent_time'])
            writer.writeheader()
            writer.writerows(updated_trades)

# ------------------- الوظيفة الرئيسية -------------------
async def main():
    print(f"🔍 بدء التحليل في {datetime.utcnow()}")
    
    # 1. جلب جميع أزواج USDT
    all_pairs = get_all_usdt_pairs()
    print(f"✅ تم العثور على {len(all_pairs)} زوج")
    
    # 2. تحليل كل زوج
    signals_found = 0
    for pair in all_pairs:
        signal = analyze_symbol(pair)
        if signal:
            await send_signal(signal)
            signals_found += 1
            await asyncio.sleep(2)  # مهلة بين الإشارات
    
    # 3. مراقبة الصفقات النشطة
    await monitor_active_trades()
    
    print(f"✅ انتهى. تم إرسال {signals_found} إشارة جديدة")

if __name__ == "__main__":
    asyncio.run(main())
