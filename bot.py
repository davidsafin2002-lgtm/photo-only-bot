import os
import logging
import threading
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError

# === ЗАГРУЗКА ПЕРЕМЕННЫХ ===
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID', '-1001805328200'))
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'TAVDIN')
ADMIN_CHAT_IDS = [int(x) for x in os.getenv('ADMIN_CHAT_IDS', '').split(',') if x]
SUPER_ADMIN_ID = int(os.getenv('SUPER_ADMIN_ID', '0'))
FORWARD_TO_IDS = [int(x) for x in os.getenv('FORWARD_TO_IDS', '').split(',') if x]

# === ГЛОБАЛЬНЫЕ ===
PAUSE_MODE = False
FORWARD_ENABLED = True

# === ЛОГИ ===
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

if not BOT_TOKEN or len(BOT_TOKEN) < 30:
    print("ОШИБКА: BOT_TOKEN не найден!")
    exit(1)

print(f"Токен: {len(BOT_TOKEN)} символов")
print(f"Канал: {CHANNEL_ID}")
print(f"Админы: {ADMIN_CHAT_IDS}")
print(f"Главный: {SUPER_ADMIN_ID}")
print(f"Пересылка → {FORWARD_TO_IDS}")

# === FLASK ===
app = Flask(__name__)
@app.route('/')
def health_check():
    return {"status": "ok", "bot": "running", "forward": FORWARD_ENABLED, "timestamp": time.time()}

def run_flask():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

# === ХРАНИЛИЩА ===
AUTHORIZED_USERS = {}
BANNED_USERS = set()

# === ВСПОМОГАТЕЛЬНЫЕ ===
async def is_user_member(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except TelegramError as e:
        logger.warning(f"Ошибка подписки {user_id}: {e}")
        return False

def get_message_link(chat_id: int, message_id: int) -> str:
    clean_id = str(chat_id)[4:]
    return f"https://t.me/c/{clean_id}/{message_id}"

async def check_access(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if user_id in BANNED_USERS: return False
    if user_id in ADMIN_CHAT_IDS: return True
    if user_id not in AUTHORIZED_USERS: return False
    if not await is_user_member(user_id, context):
        del AUTHORIZED_USERS[user_id]
        return False
    return True

# === КОМАНДЫ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in BANNED_USERS:
        await update.message.reply_text("Вы заблокированы.")
        return

    status = "ПАУЗА" if PAUSE_MODE else "АКТИВЕН"
    fwd_status = "ВКЛЮЧЕНА" if FORWARD_ENABLED else "ВЫКЛЮЧЕНА"

    if user_id in ADMIN_CHAT_IDS:
        fwd_control = "/forward on/off - Вкл/Выкл пересылку\n" if user_id == SUPER_ADMIN_ID else ""
        await update.message.reply_text(
            f"<b>PhotoOnly Bot v2.9</b>\n\n"
            f"{status}\n"
            f"Пересылка: <b>{fwd_status}</b>\n"
            f"Канал: <code>{CHANNEL_ID}</code>\n\n"
            f"<b>Вы админ!</b>\n"
            f"Команды:\n"
            f"/pause - Приостановить\n"
            f"/resume - Возобновить\n"
            f"/status - Статус\n"
            f"/logout - Выйти\n"
            f"/list_auth - Список\n"
            f"/deauth &lt;ID&gt; - Деавторизовать\n"
            f"/ban &lt;ID&gt; - Заблокировать\n"
            f"/unban &lt;ID&gt; - Разблокировать\n"
            f"{fwd_control}",
            parse_mode="HTML"
        )
    elif user_id in AUTHORIZED_USERS:
        if not await is_user_member(user_id, context):
            del AUTHORIZED_USERS[user_id]
            await update.message.reply_text("Вы отписались от канала. Авторизация отменена.")
            return
        await update.message.reply_text(
            f"<b>PhotoOnly Bot v2.9</b>\n\n"
            f"{status}\n"
            f"Канал: <code>{CHANNEL_ID}</code>\n\n"
            f"<b>Вы авторизованы!</b>\n"
            f"Команды:\n"
            f"/pause - Приостановить\n"
            f"/resume - Возобновить\n"
            f"/status - Статус\n"
            f"/logout - Выйти",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("Введите пароль:\n`/auth <пароль>`", parse_mode="Markdown")

# === ДРУГИЕ КОМАНДЫ (auth, logout, pause, resume, status, forward_control, list_auth, deauth, ban, unban) ===
# (оставлены без изменений — вставь из предыдущей версии)

# === АВТОУДАЛЕНИЕ СООБЩЕНИЙ В ЛИЧКЕ С СУПЕР-АДМИНОМ ===
async def cleanup_old_messages(application: Application):
    if not SUPER_ADMIN_ID:
        return
    bot = application.bot
    cutoff_time = datetime.now() - timedelta(hours=48)  # 2 суток

    try:
        async for message in bot.get_chat_history(chat_id=SUPER_ADMIN_ID, limit=1000):
            if not message.forward_from_chat or message.forward_from_chat.id != CHANNEL_ID:
                await asyncio.sleep(0.05)
                continue  # пропускаем не из канала

            if message.date < cutoff_time:
                try:
                    await bot.delete_message(chat_id=SUPER_ADMIN_ID, message_id=message.message_id)
                    logger.info(f"Удалено старое сообщение #{message.message_id} от {message.date.strftime('%Y-%m-%d %H:%M')}")
                except Exception as e:
                    logger.warning(f"Не удалось удалить #{message.message_id}: {e}")
                await asyncio.sleep(0.1)  # защита от rate limit
    except Exception as e:
        logger.error(f"Ошибка при очистке: {e}")

# === ФОНОВАЯ ЗАДАЧА ===
def start_cleanup_job(application: Application):
    async def job():
        while True:
            await cleanup_old_messages(application)
            await asyncio.sleep(6 * 60 * 60)  # каждые 6 часов
    loop = asyncio.get_event_loop()
    loop.create_task(job())

# === ОБРАБОТКА КАНАЛА ===
async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.channel_post:
        return
    post = update.channel_post
    if post.chat_id != CHANNEL_ID:
        return

    msg_id = post.message_id
    link = get_message_link(post.chat_id, msg_id)
    user_id = post.from_user.id if post.from_user else None
    username = post.from_user.username if post.from_user and post.from_user.username else "Неизвестно"

    logger.info(f"ПРОВЕРКА: {link} | от @{username} ({user_id})")

    if not PAUSE_MODE and not post.photo and not post.video:
        try:
            await context.bot.delete_message(post.chat_id, msg_id)
            logger.info(f"УДАЛЕНО: {link}")
        except Exception as e:
            logger.error(f"ОШИБКА удаления {link}: {e}")
        return

    logger.info(f"ОСТАВЛЕНО: {link} | Фото/Видео")

    if FORWARD_ENABLED and FORWARD_TO_IDS:
        for target_id in FORWARD_TO_IDS:
            try:
                await context.bot.forward_message(
                    chat_id=target_id,
                    from_chat_id=CHANNEL_ID,
                    message_id=msg_id
                )
                logger.info(f"ПЕРЕСЛАНО {target_id}: {link}")
            except Exception as e:
                logger.error(f"ОШИБКА пересылки {target_id}: {e}")

# === ЗАПУСК ===
import asyncio

def main():
    print("PhotoOnly Bot v2.9 | Автоудаление старых пересланных сообщений (2 суток)")

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("HTTP сервер запущен")

    application = Application.builder().token(BOT_TOKEN).build()

    # === КОМАНДЫ ===
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("auth", auth))
    application.add_handler(CommandHandler("logout", logout))
    application.add_handler(CommandHandler("pause", pause_bot))
    application.add_handler(CommandHandler("resume", resume_bot))
    application.add_handler(CommandHandler("status", status_bot))
    application.add_handler(CommandHandler("forward", forward_control))
    application.add_handler(CommandHandler("list_auth", list_auth))
    application.add_handler(CommandHandler("deauth", deauth_user))
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("unban", unban_user))

    # === КАНАЛ ===
    application.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & filters.Chat(chat_id=CHANNEL_ID),
        handle_channel_post
    ))

    # === ФОНОВАЯ ОЧИСТКА ===
    if SUPER_ADMIN_ID:
        application.job_queue.run_once(lambda ctx: start_cleanup_job(application), 10)

    print("Запуск polling...")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
