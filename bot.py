import asyncio
import feedparser
import os
import json
import requests
from datetime import datetime, timedelta, timezone
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

# ===== НАСТРОЙКИ =====
BOT_TOKEN = "8832452173:AAG4lB8O5xr9YyPoXjlVgewFVmBx5ei2kU8"
CHANNEL_ID = "@news_of_starups"
YOUR_CHAT_ID = 1123186704

# Список RSS-лент
RSS_FEEDS = [
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/?size=10"},
    {"name": "Hacker News", "url": "https://news.ycombinator.com/rss"}
]

SENT_FILE = "/tmp/sent.json"
MSK = timezone(timedelta(hours=3))
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
# =====================

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

# Функция для безопасного получения значения из словаря feedparser
def get_feed_entry(entry, key, default='Без заголовка'):
    try:
        value = entry.get(key, default)
        if not value:
            return default
        return value
    except:
        return default

# Функция для загрузки и парсинга RSS с правильными заголовками
def fetch_rss_feed(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            # Парсим содержимое ответа
            feed = feedparser.parse(response.content)
            return feed, response.status_code
        else:
            print(f"❌ Ошибка HTTP {response.status_code} для {url}")
            return None, response.status_code
    except Exception as e:
        print(f"❌ Ошибка запроса: {e}")
        return None, None

async def send_for_moderation(application, title, link, summary, source_name):
    keyboard = [[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve|{link}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"reject|{link}")
    ]]
    text = f"📰 *{get_feed_entry(title)}*\n📌 {source_name}\n\n{get_feed_entry(summary, 'summary')[:150]}...\n\n[Читать]({link})"
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
        print(f"✅ Одобрено: {link[:50]}")
    else:
        save_sent(link)
        await query.edit_message_text(f"{query.message.text}\n\n❌ Отклонено")
        print(f"❌ Отклонено: {link[:50]}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📰 Бот для сбора новостей работает!\n\n"
        f"📡 Источники: {', '.join([f['name'] for f in RSS_FEEDS])}\n\n"
        "Команды:\n"
        "/last — проверить новые новости сейчас\n"
        "/test — отправить тестовое сообщение в канал"
    )

async def cmd_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Проверяю RSS, ждите...")
    sent = load_sent()
    total = 0
    
    for feed_info in RSS_FEEDS:
        print(f"📡 Проверяю {feed_info['name']}: {feed_info['url']}")
        feed, status_code = fetch_rss_feed(feed_info['url'])
        
        if feed is None or status_code != 200:
            await update.message.reply_text(f"⚠️ Не удалось загрузить {feed_info['name']}. Код ошибки: {status_code}")
            continue
            
        entries = feed.entries
        print(f"📊 Найдено записей: {len(entries)}")
        
        for entry in entries[:5]:
            link = get_feed_entry(entry, 'link')
            title = get_feed_entry(entry, 'title')
            summary = get_feed_entry(entry, 'summary')
            
            if link and link not in sent:
                print(f"🆕 Новая новость [{feed_info['name']}]: {title[:40]}")
                await send_for_moderation(
                    context.application,
                    title,
                    link,
                    summary,
                    feed_info['name']
                )
                total += 1
                await asyncio.sleep(2)
            else:
                print(f"⏭️ Пропущено (уже было): {title[:40]}")
    
    await update.message.reply_text(f"✅ Готово! Найдено {total} новых новостей.")
    print(f"🔍 Принудительная проверка завершена: {total} новых новостей")

async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тестовая отправка сообщения в канал"""
    try:
        message_text = " ".join(context.args)
        if not message_text:
            await update.message.reply_text("❌ Напиши текст после команды, например: /test Привет, канал!")
            return
        await context.bot.send_message(chat_id=CHANNEL_ID, text=f"📢 {message_text}")
        await update.message.reply_text(f"✅ Тестовое сообщение отправлено в канал: {message_text[:50]}")
        print(f"✅ Тест отправлен в канал: {message_text[:50]}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
        print(f"❌ Ошибка теста: {e}")

def main():
    print("🚀 Бот запускается...")
    print(f"📡 Источники: {', '.join([f['name'] for f in RSS_FEEDS])}")
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("last", cmd_last))
    application.add_handler(CommandHandler("test", cmd_test))
    print("✅ Бот успешно запущен и готов к работе!")
    application.run_polling()

if __name__ == "__main__":
    main()