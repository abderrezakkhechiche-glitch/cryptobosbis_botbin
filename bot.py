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

# ------------------- جلب جميع العملات البديلة -------------------
def get_all_altcoins():
    url = "https://api.binance.com/api/v3/exchangeInfo"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        symbols = data['symbols']
        
        # استبعاد العملات الرئيسية (BTC, ETH) والعملات المستقرة
        exclude = ['BTC', 'ETH', 'USDT', 'BUSD', 'USDC', 'DAI', 'TUSD', 'FDUSD', 'PAX', 'UST']
        
        altcoins = []
        for s in symbols:
            symbol = s['symbol']
            # نأخذ فقط الأزواج مع USDT
            if symbol.endswith('USDT') and s['status'] == 'TRADING':
                # استخراج اسم العملة الأساسية (مثلاً: BTC من BTCUSDT)
                base_asset = symbol.replace('USDT', '')
                
                # إذا كانت العملة الأساسية ليست من المستثنيات
                if base_asset not in exclude:
                    altcoins.append(symbol)
        
        return altcoins
    return []

# ------------------- جلب بيانات الشموع (فريم 4 ساعات) -------------------
def get_klines(symbol, interval='4h', limit=30):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            closes = [float(x[4]) for x in data]
            highs = [float(x[2]) for x in data]
            lows = [float(x[3]) for x in data]
            volumes = [float(x[5]) for x in data]
            return closes, highs, lows, volumes
    except:
        return None, None, None, None
    return None, None, None, None

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
    if macd_line.iloc[-1] > signal_line.iloc[-1]:
        return True
    return False

# ------------------- حساب المتوسطات المتحركة -------------------
def calculate_ema(closes, period):
    return pd.Series(closes).ewm(span=period, adjust=False).mean().iloc[-1]

# ------------------- التحليل السريع للـ ALTCOINS -------------------
def analyze_altcoin(symbol):
    closes, highs, lows, volumes = get_klines(symbol)
    if not closes or len(closes) < 20:
        return None
    
    current_price = closes[-1]
    prev_price = closes[-2]
    
    # المؤشرات
    rsi = calculate_rsi(closes)
    macd_buy = calculate_macd(closes)
    ema9 = calculate_ema(closes, 9)
    ema21 = calculate_ema(closes, 21)
    
    # شروط الدخول السريع (مناسبة للـ ALTCOINS)
    buy_signals = []
    
    # شرط 1: RSI أقل من 40 (منطقة ذروة بيع)
    if rsi < 40:
        buy_signals.append("RSI Oversold")
    
    # شرط 2: MACD إيجابي
    if macd_buy:
        buy_signals.append("MACD Bullish")
    
    # شرط 3: السعر فوق EMA9 (اتجاه صاعد قصير)
    if current_price > ema9:
        buy_signals.append("Price > EMA9")
    
    # شرط 4: EMA9 فوق EMA21 (اتجاه صاعد عام)
    if ema9 > ema21:
        buy_signals.append("EMA9 > EMA21")
    
    # شرط 5: ارتفاع عن الشمعة السابقة
    if current_price > prev_price * 1.01:  # ارتفاع 1% على الأقل
        buy_signals.append("Momentum +1%")
    
    # إذا تحقق شرطان على الأقل، نرسل إشارة
    if len(buy_signals) >= 2:
        # اختيار هدف عشوائي بين 2% و 5%
        target_percent = np.random.uniform(2.0, 5.0)
        target_price = round(current_price * (1 + target_percent/100), 8)
        
        return {
            'symbol': symbol.replace('USDT', '/USDT'),
            'entry': round(current_price, 8),
            'target': target_price,
            'target_percent': round(target_percent, 2),
            'rsi': round(rsi, 2),
            'signals': buy_signals,
            'time': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        }
    return None

# ------------------- إرسال إشارة ALTCOIN -------------------
async def send_altcoin_signal(signal):
    message = f"""
🚀 **ALTCOIN SIGNAL** 🚀

💰 {signal['symbol']}
📥 Entry: {signal['entry']}
🎯 Target: {signal['target']} ({signal['target_percent']}%)
📊 RSI: {signal['rsi']}
📈 Indicators: {', '.join(signal['signals'])}
⏰ Time: {signal['time']}

⚠️ Trade within 4 hours frame
"""
    await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode='Markdown')
    print(f"✅ Signal sent: {signal['symbol']}")

# ------------------- حفظ الإشارة لمتابعتها -------------------
def save_signal(signal):
    file_exists = os.path.isfile('alt_signals.csv')
    with open('alt_signals.csv', 'a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(['symbol', 'entry', 'target', 'target_percent', 'rsi', 'signals', 'time', 'status'])
        writer.writerow([
            signal['symbol'],
            signal['entry'],
            signal['target'],
            signal['target_percent'],
            signal['rsi'],
            '; '.join(signal['signals']),
            signal['time'],
            'pending'
        ])

# ------------------- مراقبة الصفقات النشطة -------------------
async def monitor_active_trades():
    if not os.path.isfile('alt_signals.csv'):
        return
    
    with open('alt_signals.csv', 'r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        trades = list(reader)
    
    changed = False
    updated_trades = []
    
    for trade in trades:
        if trade['status'] == 'active':
            symbol_clean = trade['symbol'].replace('/', '')
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol_clean}"
            response = requests.get(url)
            
            if response.status_code == 200:
                current = float(response.json()['price'])
                target = float(trade['target'])
                
                if current >= target:
                    entry = float(trade['entry'])
                    profit = ((current - entry) / entry) * 100
                    
                    message = f"""
✅ **ALTCOIN TARGET HIT** ✅

💰 {trade['symbol']}
📥 Entry: {entry}
🎯 Target: {target}
📈 Profit: {profit:.2f}%
⏰ Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}

🎉 Congratulations!
"""
                    await bot.send_message(chat_id=CHAT_ID, text=message)
                    trade['status'] = 'closed'
                    changed = True
        
        updated_trades.append(trade)
    
    if changed:
        with open('alt_signals.csv', 'w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=['symbol', 'entry', 'target', 'target_percent', 'rsi', 'signals', 'time', 'status'])
            writer.writeheader()
            writer.writerows(updated_trades)

# ------------------- الوظيفة الرئيسية -------------------
async def main():
    print(f"🔍 Scanning ALTCOINS at {datetime.utcnow()}")
    
    # 1. جلب جميع العملات البديلة
    all_alts = get_all_altcoins()
    print(f"✅ Found {len(all_alts)} altcoins")
    
    # 2. تحليل كل عملة بديلة
    signals_sent = 0
    for alt in all_alts[:50]:  # نكتفي بأول 50 عملة للسرعة
        signal = analyze_altcoin(alt)
        if signal:
            await send_altcoin_signal(signal)
            save_signal(signal)
            signals_sent += 1
            await asyncio.sleep(2)  # مهلة بين الإشارات
    
    # 3. مراقبة الصفقات النشطة
    await monitor_active_trades()
    
    print(f"✅ Done. Sent {signals_sent} signals")

if __name__ == "__main__":
    asyncio.run(main())
