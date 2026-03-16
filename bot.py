import os
import csv
import asyncio
from datetime import datetime
from binance.client import Client
from telegram import Bot

# ------------------- الإعدادات -------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# إنشاء كائن بايننس (بدون مفتاح يكفي للبيانات العامة)
client = Client()

# إنشاء كائن تيليغرام
bot = Bot(token=BOT_TOKEN)

# ------------------- قراءة الصفقات من ملف CSV -------------------
def load_trades():
    trades = []
    with open('trades.csv', 'r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            trades.append({
                'symbol': row['symbol'],
                'entry_price': float(row['entry_price']),
                'target': float(row['target']),
                'status': row['status'],
                'entry_time': row['entry_time']
            })
    return trades

# ------------------- حفظ الصفقات بعد التحديث -------------------
def save_trades(trades):
    with open('trades.csv', 'w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=['symbol', 'entry_price', 'target', 'status', 'entry_time'])
        writer.writeheader()
        writer.writerows(trades)

# ------------------- حساب الربح الحالي -------------------
def check_profit(symbol, entry_price):
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        current_price = float(ticker['price'])
        profit = ((current_price - entry_price) / entry_price) * 100
        return profit
    except:
        return None  # لو الزوج مش موجود أو مشكلة في API

# ------------------- حساب الوقت المستغرق -------------------
def calculate_period(entry_time_str):
    entry_time = datetime.strptime(entry_time_str, "%Y-%m-%d %H:%M:%S")
    now = datetime.utcnow()
    delta = now - entry_time
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    # صياغة الوقت
    parts = []
    if delta.days > 0:
        parts.append(f"{delta.days} Days")
    if hours > 0:
        parts.append(f"{hours} Hours")
    if minutes > 0:
        parts.append(f"{minutes} Minutes")
    if seconds > 0 or not parts:
        parts.append(f"{seconds} Seconds")
    
    return ", ".join(parts)

# ------------------- إرسال الإشارة إلى تيليغرام -------------------
async def send_signal(symbol, profit, period):
    message = f"{symbol} Profit: {profit}% ✅😎💰\n⏰ Period: {period}"
    await bot.send_message(chat_id=CHAT_ID, text=message)
    print(f"📤 Signal sent: {message}")

# ------------------- الوظيفة الرئيسية -------------------
async def main():
    print(f"🔍 Checking trades at {datetime.utcnow()}")
    
    # تحميل الصفقات
    trades = load_trades()
    
    # متغير لمعرفة إذا حدث تغيير
    changed = False
    
    # فحص كل صفقة
    for trade in trades:
        if trade['status'] == 'open':
            profit = check_profit(trade['symbol'], trade['entry_price'])
            
            if profit and profit >= trade['target']:
                print(f"🎯 Target hit: {trade['symbol']} at {profit}%")
                
                # حساب الوقت
                period = calculate_period(trade['entry_time'])
                
                # إرسال الإشارة
                await send_signal(trade['symbol'], round(profit, 2), period)
                
                # تحديث الحالة
                trade['status'] = 'closed'
                changed = True
    
    # حفظ التغييرات
    if changed:
        save_trades(trades)
        print("💾 Trades updated")

# ------------------- نقطة البداية -------------------
if __name__ == "__main__":
    asyncio.run(main())
