import asyncio
import feedparser
import json
import os
import html
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from threading import Thread
from flask import Flask
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

# ===== НАСТРОЙКИ =====
BOT_TOKEN = "8449062989:AAFu7O6NQw7wF1O990Lf1FDoDniKFgbPG50"
CHANNEL_ID = "@news_of_starups"
YOUR_CHAT_ID = 1123186704

# Список RSS-лент
RSS_FEEDS = [
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/?size=10"},
    {"name": "Hacker News", "url": "https://news.ycombinator.com/rss"}
]

SENT_FILE = "/tmp/sent.json"
APPROVED_FILE = "/tmp/approved.json"
MSK = timezone(timedelta(hours=3))
# =====================

print("🚀 Бот запускается...")

# Flask-сервер
app_flask = Flask(__name__)

@app_flask.route('/')
def health_check():
    return "✅ Бот работает!", 200

def run_flask():
    print("🌐 Flask-сервер запущен на порту 10000")
    app_flask.run(host='0.0.0.0', port=10000)

Thread(target=run_flask, daemon=True).start()

# --- РАБОТА С ФАЙЛАМИ ---
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

def load_approved():
    if os.path.exists(APPROVED_FILE):
        with open(APPROVED_FILE, 'r') as f:
            return json.load(f)
    return []

def save_approved(link, title):
    approved = load_approved()
    approved.append({'link': link, 'title': title, 'date': str(datetime.now(MSK))})
    with open(APPROVED_FILE, 'w') as f:
        json.dump(approved[-200:], f)

def parse_time(time_str):
    try:
        return parsedate_to_datetime(time_str)
    except:
        return datetime.now(MSK)

def escape_html(text):
    """Безопасное экранирование текста для HTML"""
    if not text:
        return ""
    return html.escape(text[:300])

# --- ОТПРАВКА НА МОДЕРАЦИЮ ---
async def send_for_moderation(application, title, link, summary, source_name):
    print(f"📨 Отправляю на модерацию [{source_name}]: {title[:40]}")
    clean_link = link.replace('&', '&amp;').replace('|', '%7C')
    keyboard = [[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve|{clean_link}|{title}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"reject|{clean_link}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Экранируем текст для HTML
    safe_title = escape_html(title)
    safe_summary = escape_html(summary)
    safe_source = escape_html(source_name)
    
    text = f"📰 <b>{safe_title}</b>\n\n📌 Источник: {safe_source}\n\n{safe_summary}...\n\n<a href='{link}'>Читать полностью</a>"
    
    await application.bot.send_message(
        chat_id=YOUR_CHAT_ID,
        text=text,
        parse_mode="HTML",
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )
    print(f"✅ Отправлено на модерацию: {title[:40]}")

# --- ОБРАБОТЧИК КНОПОК ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split('|')
    if len(data) < 2:
        return
    action = data[0]
    link = data[1].replace('%7C', '|')
    if action == "approve":
        title = data[2] if len(data) > 2 else ""
        original_text = query.message.text
        await context.bot.send_message(chat_id=CHANNEL_ID, text=original_text, parse_mode="HTML", disable_web_page_preview=True)
        save_sent(link)
        if title:
            save_approved(link, title)
        await query.edit_message_text(f"{original_text}\n\n✅ Одобрено и опубликовано", parse_mode="HTML")
        print(f"✅ Одобрено: {title[:40]}")
    elif action == "reject":
        save_sent(link)
        await query.edit_message_text(f"{query.message.text}\n\n❌ Отклонено", parse_mode="HTML")
        print(f"❌ Отклонено: {link}")

# --- КОМАНДЫ БОТА ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sources = "\n".join([f"• {feed['name']}" for feed in RSS_FEEDS])
    await update.message.reply_text(
        f"📰 <b>Бот для сбора новостей</b>\n\n"
        f"✅ Работает с источниками:\n{sources}\n\n"
        f"<b>Команды:</b>\n"
        f"/last — проверить новые новости сейчас\n"
        f"/digest_now — дайджест за неделю\n"
        f"/test — отправить тестовое сообщение в канал\n\n"
        f"Новости приходят на модерацию в 00 и 30 мин каждого часа (8:00–23:00)",
        parse_mode="HTML"
    )

async def cmd_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Проверяю RSS, ждите...")
    try:
        await check_all_rss_now(context.application)
        await update.message.reply_text("✅ Готово!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
        print(f"❌ Ошибка в cmd_last: {e}")

async def cmd_digest_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    approved = load_approved()
    week_ago = datetime.now(MSK) - timedelta(days=7)
    weekly = [item for item in approved if parse_time(item['date']) >= week_ago]
    if not weekly:
        await update.message.reply_text("📭 За неделю не было опубликовано ни одной новости.")
        return
    digest = "<b>📅 Дайджест недели</b>\n\n"
    for idx, item in enumerate(weekly[-15:], 1):
        digest += f"{idx}. <a href='{item['link']}'>{item['title']}</a>\n"
    await update.message.reply_text(digest, parse_mode="HTML", disable_web_page_preview=True)

async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тестовая отправка сообщения в канал"""
    try:
        message_text = " ".join(context.args)
        if not message_text:
            await update.message.reply_text("❌ Напиши текст после команды, например: /test Привет, канал!")
            return
        await context.bot.send_message(chat_id=CHANNEL_ID, text=message_text)
        await update.message.reply_text(f"✅ Тестовое сообщение отправлено в канал: {message_text[:50]}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# --- ПРОВЕРКА ВСЕХ RSS ---
async def check_all_rss_now(application):
    print("🔍 Принудительная проверка всех RSS-источников")
    sent_links = load_sent()
    total_new = 0
    
    for feed_info in RSS_FEEDS:
        print(f"📡 Проверяю {feed_info['name']}: {feed_info['url']}")
        try:
            feed = feedparser.parse(feed_info['url'])
            print(f"📊 Всего записей: {len(feed.entries)}")
            for entry in feed.entries[:5]:
                link = entry.get('link', '')
                title = entry.get('title', 'Без заголовка')
                if link and link not in sent_links:
                    print(f"🆕 Новая новость [{feed_info['name']}]: {title[:40]}")
                    await send_for_moderation(
                        application,
                        title,
                        link,
                        entry.get('summary', ''),
                        feed_info['name']
                    )
                    total_new += 1
                    await asyncio.sleep(3)
                else:
                    print(f"⏭️ Пропущено (уже было): {title[:40]}")
        except Exception as e:
            print(f"❌ Ошибка при загрузке {feed_info['name']}: {e}")
    
    print(f"🔍 Принудительная проверка завершена: {total_new} новых новостей")

async def scheduled_check(application):
    print(f"[{datetime.now(MSK)}] Планировщик запущен")
    while True:
        now = datetime.now(MSK)
        if 8 <= now.hour < 23:
            if now.minute < 30:
                wait_seconds = (30 - now.minute) * 60 - now.second
            else:
                wait_seconds = (60 - now.minute) * 60 - now.second
            if wait_seconds > 10:
                print(f"💤 Сплю {wait_seconds} секунд до следующей проверки")
                await asyncio.sleep(wait_seconds - 5)
            
            print(f"🔍 Плановая проверка RSS в {datetime.now(MSK)}")
            sent_links = load_sent()
            total_new = 0
            
            for feed_info in RSS_FEEDS:
                try:
                    feed = feedparser.parse(feed_info['url'])
                    for entry in feed.entries[:5]:
                        link = entry.get('link', '')
                        if link and link not in sent_links:
                            await send_for_moderation(
                                application,
                                entry.get('title', 'Без заголовка'),
                                link,
                                entry.get('summary', ''),
                                feed_info['name']
                            )
                            total_new += 1
                            await asyncio.sleep(3)
                except Exception as e:
                    print(f"❌ Ошибка при загрузке {feed_info['name']}: {e}")
            
            if total_new:
                print(f"[{datetime.now(MSK)}] Найдено {total_new} новых новостей")
            else:
                print(f"[{datetime.now(MSK)}] Новых новостей нет")
        else:
            print(f"💤 Ночной режим: сейчас {now.hour}:{now.minute}, сплю час")
            await asyncio.sleep(3600)

async def weekly_digest_job(application):
    while True:
        now = datetime.now(MSK)
        days_until_sunday = (6 - now.weekday()) % 7
        next_sunday = now + timedelta(days=days_until_sunday)
        next_run = next_sunday.replace(hour=10, minute=0, second=0, microsecond=0)
        wait_seconds = (next_run - now).total_seconds()
        if wait_seconds > 0:
            print(f"💤 До воскресного дайджеста спать {wait_seconds // 3600} часов")
            await asyncio.sleep(wait_seconds)
        
        approved = load_approved()
        week_ago = datetime.now(MSK) - timedelta(days=7)
        weekly = [item for item in approved if parse_time(item['date']) >= week_ago]
        if weekly:
            digest = "<b>📅 Еженедельный дайджест новостей</b>\n\n"
            for idx, item in enumerate(weekly[-20:], 1):
                digest += f"{idx}. <a href='{item['link']}'>{item['title']}</a>\n"
            await application.bot.send_message(chat_id=CHANNEL_ID, text=digest, parse_mode="HTML", disable_web_page_preview=True)
            print(f"📅 Отправлен еженедельный дайджест: {len(weekly)} новостей")

# --- ЗАПУСК ---
def main():
    print("🚀 Запускаю основную функцию main()")
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("last", cmd_last))
    application.add_handler(CommandHandler("digest_now", cmd_digest_now))
    application.add_handler(CommandHandler("test", cmd_test))

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(scheduled_check(application))
    loop.create_task(weekly_digest_job(application))
    print("✅ Задачи запланированы, запускаю polling...")
    application.run_polling()

if __name__ == "__main__":
    main()