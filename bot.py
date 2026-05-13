import os
import threading
import asyncio
import feedparser
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes
from flask import Flask

# ===== НАСТРОЙКИ (ПРОВЕРЬ ИХ!) =====
BOT_TOKEN = "8832452173:AAG4lB8O5xr9YyPoXjlVgewFVmBx5ei2kU8"
CHANNEL_ID = "@news_of_starups"
YOUR_CHAT_ID = 1123186704
RSS_FEEDS = [
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/?size=10"},
    {"name": "Hacker News", "url": "https://news.ycombinator.com/rss"}
]
SENT_FILE = "/tmp/sent.json"
# ===================================

# --- 1. СОЗДАЁМ ВЕБ-СЕРВЕР ДЛЯ RENDER ---
app = Flask(__name__)

@app.route('/')
def health_check():
    return "OK", 200

def run_web_server():
    """Запускает Flask-сервер на порту, который ожидает Render."""
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)

# --- 2. ВСЯ ЛОГИКА ТВОЕГО БОТА ---
def load_sent():
    if os.path.exists(SENT_FILE):
        with open(SENT_FILE, 'r') as f:
            return set(json.load(f))
    return set()

def save_sent(link):
    sent = load_sent()
    sent.add(link)
    with open(SENT_FILE, 'w') as f:
        json.dump(list(sent), f)

async def send_for_moderation(application, title, link, summary, source_name):
    keyboard = [[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve|{link}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"reject|{link}")
    ]]
    text = f"📰 *{title}*\n📌 {source_name}\n\n{summary[:150]}...\n\n[Читать]({link})"
    await application.bot.send_message(
        chat_id=YOUR_CHAT_ID,
        text=text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, link = query.data.split('|')
    if action == "approve":
        await context.bot.send_message(chat_id=CHANNEL_ID, text=query.message.text, parse_mode="Markdown")
        save_sent(link)
        await query.edit_message_text(f"{query.message.text}\n\n✅ Одобрено")
    else:
        save_sent(link)
        await query.edit_message_text(f"{query.message.text}\n\n❌ Отклонено")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sources = ", ".join([f['name'] for f in RSS_FEEDS])
    await update.message.reply_text(
        f"📰 Бот запущен!\n📡 Источники: {sources}\n\n/last — проверить новости\n/test — тест"
    )

async def cmd_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Проверяю RSS, ждите...")
    sent = load_sent()
    total = 0
    for feed_info in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_info['url'])
            for entry in feed.entries[:5]:
                link = entry.get('link')
                if link and link not in sent:
                    await send_for_moderation(
                        context.application,
                        entry.get('title', 'Без заголовка'),
                        link,
                        entry.get('summary', ''),
                        feed_info['name']
                    )
                    total += 1
                    await asyncio.sleep(2)
        except Exception as e:
            print(f"Ошибка: {e}")
    await update.message.reply_text(f"✅ Готово! Найдено {total} новых новостей.")

async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message_text = " ".join(context.args)
        if not message_text:
            await update.message.reply_text("Напиши текст, например: /test Привет!")
            return
        await context.bot.send_message(chat_id=CHANNEL_ID, text=f"📢 {message_text}")
        await update.message.reply_text("✅ Тест отправлен!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

def run_bot():
    """Запускает Telegram-бота в отдельном потоке."""
    telegram_app = Application.builder().token(BOT_TOKEN).build()
    telegram_app.add_handler(CallbackQueryHandler(button_callback))
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("last", cmd_last))
    telegram_app.add_handler(CommandHandler("test", cmd_test))
    
    telegram_app.run_polling()

# --- 3. ТОЧКА ВХОДА (ЗАПУСКАЕМ ВСЁ ВМЕСТЕ) ---
if __name__ == "__main__":
    # Запускаем веб-сервер Flask в ОТДЕЛЬНОМ ПОТОКЕ
    web_thread = threading.Thread(target=run_web_server)
    web_thread.daemon = True  # Поток завершится вместе с главной программой
    web_thread.start()
    
    # Запускаем Telegram-бота в ОСНОВНОМ ПОТОКЕ
    run_bot()