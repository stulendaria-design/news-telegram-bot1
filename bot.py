import asyncio
import feedparser
import json
import os
from datetime import datetime, time, timezone, timedelta
from email.utils import parsedate_to_datetime
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

# ===== НАСТРОЙКИ =====
BOT_TOKEN = "8449062989:AAEkfS6kb9tQeER7yBOpa2rkJCdCAlT3xpY"
CHANNEL_ID = "@news_of_starups"
YOUR_CHAT_ID = 1123186704
RSS_URL = "https://techcrunch.com/feed/?size=10"
SENT_FILE = "/tmp/sent.json"
APPROVED_FILE = "/tmp/approved.json"
MSK = timezone(timedelta(hours=3))
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

def load_approved():
    if os.path.exists(APPROVED_FILE):
        with open(APPROVED_FILE, 'r') as f:
            return json.load(f)
    return []

def save_approved(link, title):
    approved = load_approved()
    approved.append({'link': link, 'title': title, 'date': str(datetime.now(MSK))})
    with open(APPROVED_FILE, 'w') as f:
        json.dump(approved[-100:], f)

def parse_time(time_str):
    try:
        return parsedate_to_datetime(time_str)
    except:
        return datetime.now(MSK)

async def send_for_moderation(application, title, link, summary):
    clean_link = link.replace('&', '&amp;').replace('|', '%7C')
    keyboard = [[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve|{clean_link}|{title}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"reject|{clean_link}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = f"📰 *{title}*\n\n{summary[:200]}...\n\n[Читать]({link})"
    await application.bot.send_message(
        chat_id=YOUR_CHAT_ID,
        text=text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    print(f"📨 Отправлено на модерацию: {title[:40]}")

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
        await context.bot.send_message(chat_id=CHANNEL_ID, text=original_text, parse_mode="Markdown")
        save_sent(link)
        if title:
            save_approved(link, title)
        await query.edit_message_text(f"{original_text}\n\n✅ Одобрено и опубликовано")
        print(f"✅ Одобрено: {title[:40]}")
    elif action == "reject":
        save_sent(link)
        await query.edit_message_text(f"{query.message.text}\n\n❌ Отклонено")
        print(f"❌ Отклонено: {link}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📰 Бот для сбора новостей работает!\n\n"
        "Команды:\n"
        "/last — проверить новые новости прямо сейчас\n"
        "/digest_now — получить дайджест за неделю\n"
        "Новости приходят на модерацию в 00 и 30 мин каждого часа с 8:00 до 23:00"
    )

async def cmd_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Проверяю RSS, ждите...")
    await check_rss_now(context.application)
    await update.message.reply_text("✅ Готово!")

async def cmd_digest_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    approved = load_approved()
    week_ago = datetime.now(MSK) - timedelta(days=7)
    weekly = [item for item in approved if parse_time(item['date']) >= week_ago]
    if not weekly:
        await update.message.reply_text("📭 За неделю не было опубликовано ни одной новости.")
        return
    digest = "📅 *Дайджест недели*\n\n"
    for idx, item in enumerate(weekly[-12:], 1):
        digest += f"{idx}. [{item['title']}]({item['link']})\n"
    await update.message.reply_text(digest, parse_mode="Markdown")

async def check_rss_now(application):
    sent_links = load_sent()
    feed = feedparser.parse(RSS_URL)
    new_count = 0
    for entry in feed.entries[:10]:
        link = entry.get('link', '')
        if link and link not in sent_links:
            await send_for_moderation(
                application,
                entry.get('title', 'Без заголовка'),
                link,
                entry.get('summary', '')
            )
            new_count += 1
            await asyncio.sleep(3)
    print(f"🔍 Принудительная проверка: {new_count} новых новостей")

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
                await asyncio.sleep(wait_seconds - 5)
            sent_links = load_sent()
            feed = feedparser.parse(RSS_URL)
            new_count = 0
            for entry in feed.entries[:5]:
                link = entry.get('link', '')
                if link and link not in sent_links:
                    await send_for_moderation(
                        application,
                        entry.get('title', 'Без заголовка'),
                        link,
                        entry.get('summary', '')
                    )
                    new_count += 1
                    await asyncio.sleep(3)
            if new_count:
                print(f"[{datetime.now(MSK)}] Найдено {new_count} новых новостей")
            else:
                print(f"[{datetime.now(MSK)}] Новых новостей нет")
        else:
            await asyncio.sleep(3600)

async def weekly_digest_job(application):
    while True:
        now = datetime.now(MSK)
        days_until_sunday = (6 - now.weekday()) % 7
        next_sunday = now + timedelta(days=days_until_sunday)
        next_run = next_sunday.replace(hour=10, minute=0, second=0, microsecond=0)
        wait_seconds = (next_run - now).total_seconds()
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)
        approved = load_approved()
        week_ago = datetime.now(MSK) - timedelta(days=7)
        weekly = [item for item in approved if parse_time(item['date']) >= week_ago]
        if weekly:
            digest = "📅 *Еженедельный дайджест новостей*\n\n"
            for idx, item in enumerate(weekly[-15:], 1):
                digest += f"{idx}. [{item['title']}]({item['link']})\n"
            await application.bot.send_message(chat_id=CHANNEL_ID, text=digest, parse_mode="Markdown")

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("last", cmd_last))
    application.add_handler(CommandHandler("digest_now", cmd_digest_now))

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(scheduled_check(application))
    loop.create_task(weekly_digest_job(application))
    application.run_polling()

if __name__ == "__main__":
    main()