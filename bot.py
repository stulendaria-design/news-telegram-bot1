import asyncio
import feedparser
from datetime import datetime
from telegram import Bot
from flask import Flask
import threading

# ===== НАСТРОЙКИ =====
BOT_TOKEN = "8449062989:AAEkfS6kb9tQeER7yBOpa2rkJCdCAlT3xpY"
CHAT_ID = "@news_of_starups"
RSS_URL = "https://techcrunch.com/feed/?size=10"
# =====================

bot = Bot(token=BOT_TOKEN)
app = Flask(__name__)

async def send_news():
    print(f"[{datetime.now()}] Бот запущен")
    
    try:
        me = await bot.get_me()
        print(f"✅ Бот @{me.username} работает!")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return
    
    while True:
        try:
            print(f"\n[{datetime.now()}] Проверяю RSS...")
            feed = feedparser.parse(RSS_URL)
            
            for entry in feed.entries[:3]:
                text = f"📰 *{entry.title}*\n\n{entry.summary[:200]}...\n\n[Читать]({entry.link})"
                await bot.send_message(CHAT_ID, text, parse_mode="Markdown")
                print(f"✅ Отправлено: {entry.title[:40]}")
                await asyncio.sleep(3)
            
            print(f"Жду 60 минут...")
            await asyncio.sleep(60 * 60)
            
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            await asyncio.sleep(60)

@app.route('/')
def hello():
    return "Бот работает!"

def run_flask():
    app.run(host='0.0.0.0', port=10000)

if __name__ == "__main__":
    # Запускаем Flask в отдельном потоке
    threading.Thread(target=run_flask).start()
    # Запускаем бота
    asyncio.run(send_news())