import asyncio
import feedparser
import json
import os
from datetime import datetime
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes
from flask import Flask
import threading

# ===== НАСТРОЙКИ =====
BOT_TOKEN = "8449062989:AAEkfS6kb9tQeER7yBOpa2rkJCdCAlT3xpY"
CHANNEL_ID = "@news_of_starups"
YOUR_CHAT_ID = 1123186704  # ТВОЙ личный ID (администратора)
RSS_URL = "https://techcrunch.com/feed/?size=10"
SENT_FILE = "/tmp/sent.json"  # Файл для запоминания отправленных новостей
# =====================

# Загружаем список отправленных новостей
def load_sent():
    if os.path.exists(SENT_FILE):
        with open(SENT_FILE, 'r') as f:
            return set(json.load(f))
    return set()

# Сохраняем отправленную новость
def save_sent(link):
    sent = load_sent()
    sent.add(link)
    with open(SENT_FILE, 'w') as f:
        json.dump(list(sent), f)

# Flask для Render
app_flask = Flask(__name__)

@app_flask.route('/')
def hello():
    return "Бот работает!"

# Отправка новости на модерацию
async def send_for_moderation(application, title, link, summary):
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve|{title}|{link}|{summary}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject|{title}|{link}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = f"📰 *{title}*\n\n{summary[:200]}...\n\n[Читать]({link})"
    
    await application.bot.send_message(
        chat_id=YOUR_CHAT_ID,
        text=text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    print(f"📨 Отправлено на модерацию: {title[:40]}")

# Обработчик кнопок
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data.split('|')
    action = data[0]
    title = data[1]
    link = data[2]
    
    if action == "approve":
        summary = data[3]
        text = f"📰 *{title}*\n\n{summary[:200]}...\n\n[Читать]({link})"
        await context.bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="Markdown")
        save_sent(link)
        await query.edit_message_text(f"✅ Одобрено: {title[:50]}")
        print(f"✅ Одобрено и отправлено в канал: {title[:40]}")
    
    elif action == "reject":
        await query.edit_message_text(f"❌ Отклонено: {title[:50]}")
        print(f"❌ Отклонено: {title[:40]}")

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бот работает! Новости будут приходить на модерацию.")

# Главный цикл проверки RSS
async def check_rss(application):
    print(f"[{datetime.now()}] Бот запущен, проверяю RSS...")
    sent_links = load_sent()
    
    while True:
        try:
            feed = feedparser.parse(RSS_URL)
            new_count = 0
            
            for entry in feed.entries[:5]:
                link = entry.get('link', '')
                if link not in sent_links:
                    await send_for_moderation(
                        application,
                        entry.get('title', 'Без заголовка'),
                        link,
                        entry.get('summary', '')
                    )
                    new_count += 1
                    await asyncio.sleep(5)
            
            if new_count == 0:
                print(f"[{datetime.now()}] Новых новостей нет")
            else:
                print(f"[{datetime.now()}] Отправлено на модерацию: {new_count} новостей")
            
            await asyncio.sleep(60 * 30)  # Проверка каждые 30 минут
            
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            await asyncio.sleep(60)

def run_flask():
    app_flask.run(host='0.0.0.0', port=10000)

def run_bot():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(CommandHandler("start", start))
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(check_rss(application))
    application.run_polling()

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    run_bot()