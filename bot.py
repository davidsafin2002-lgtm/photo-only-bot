import os
import logging
import threading
import time
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError

# === ЗАГРУЗКА ПЕРЕМЕННЫХ ===
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID', '-1003008235648'))
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'TAVDIN')
ADMIN_CHAT_IDS = [int(x) for x in os.getenv('ADMIN_CHAT_IDS', '').split(',') if x]
SUPER_ADMIN_ID = int(os.getenv('SUPER_ADMIN_ID', '0'))
FORWARD_TO_IDS = [int(x) for x in os.getenv('FORWARD_TO_IDS', '').split(',') if x]

# === ГЛОБАЛЬНЫЕ ===
PAUSE_MODE = False
FORWARD_ENABLED = True
last_notify_time = 0  # Для уведомлений о попытках /forward

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
print(f"Пересылка → {FORWARD_TO_IDS or '[]'}")

# === FLASK ===
app = Flask(__name__)

@app.route('/')
def health_check():
    return {"status": "ok", "bot": "running", "mode": "webhook", "timestamp": time.time()}

# === Webhook endpoint ===
@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    asyncio.create_task(application.process_update(update))
    return '', 200

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
            f"<b>PhotoOnly Bot v3.1</b>\n\n"
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
        await update.message.reply_text(
            f"<b>PhotoOnly Bot v3.1</b>\n\n"
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

# === ОСТАЛЬНЫЕ КОМАНДЫ (auth, logout, pause_bot, resume_bot, status_bot) ===
# (вставь из предыдущей версии — они не изменились)

async def auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in BANNED_USERS:
        await update.message.reply_text("Вы заблокированы.")
        return

    if user_id in ADMIN_CHAT_IDS:
        if context.args and context.args[0] == ADMIN_PASSWORD:
            AUTHORIZED_USERS[user_id] = True
            await update.message.reply_text("Авторизация успешна!")
        else:
            await update.message.reply_text("Неверный пароль!")
        return

    if not await is_user_member(user_id, context):
        await update.message.reply_text("Подпишитесь на канал для авторизации!")
        return

    if context.args and context.args[0] == ADMIN_PASSWORD:
        AUTHORIZED_USERS[user_id] = True
        await update.message.reply_text("Авторизация успешна!")
    else:
        await update.message.reply_text("Неверный пароль!")

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in AUTHORIZED_USERS:
        del AUTHORIZED_USERS[user_id]
        await update.message.reply_text("Вы вышли.")
    else:
        await update.message.reply_text("Вы не авторизованы.")

async def pause_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not await check_access(user_id, context):
        await update.message.reply_text("Только для авторизованных!")
        return
    global PAUSE_MODE
    PAUSE_MODE = True
    logger.info(f"ПАУЗА от {user_id}")
    await update.message.reply_text("<b>ПАУЗА!</b> Удаление остановлено.", parse_mode="HTML")

async def resume_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not await check_access(user_id, context):
        await update.message.reply_text("Только для авторизованных!")
        return
    global PAUSE_MODE
    PAUSE_MODE = False
    logger.info(f"АКТИВЕН от {user_id}")
    await update.message.reply_text("<b>АКТИВЕН!</b> Удаляет НЕ-фото/видео.", parse_mode="HTML")

async def status_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not await check_access(user_id, context):
        await update.message.reply_text("Только для авторизованных!")
        return
    status = "ПАУЗА" if PAUSE_MODE else "АКТИВЕН"
    fwd_status = "ВКЛЮЧЕНА" if FORWARD_ENABLED else "ВЫКЛЮЧЕНА"
    await update.message.reply_text(
        f"<b>{status}</b>\n"
        f"Пересылка: <b>{fwd_status}</b>\n"
        f"Канал: <code>{CHANNEL_ID}</code>\n"
        f"Админы: {len(ADMIN_CHAT_IDS)}\n"
        f"Авторизовано: {len(AUTHORIZED_USERS)}",
        parse_mode="HTML"
    )

# === /forward с уведомлениями ===
async def forward_control(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_notify_time
    user_id = update.message.from_user.id
    username = update.message.from_user.username or "Без юзернейма"

    if user_id != SUPER_ADMIN_ID:
        await update.message.reply_text("Только главный админ может управлять пересылкой!")

        current_time = time.time()
        if current_time - last_notify_time > 10:
            try:
                await context.bot.send_message(
                    chat_id=SUPER_ADMIN_ID,
                    text=f"<b>Попытка использовать /forward</b>\n"
                         f"Пользователь: @{username} (ID: <code>{user_id}</code>)",
                    parse_mode="HTML"
                )
                last_notify_time = current_time
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление: {e}")
        logger.info(f"Попытка /forward от {user_id} (@{username})")
        return

    if not context.args:
        await update.message.reply_text("Использование: `/forward on` или `/forward off`", parse_mode="Markdown")
        return

    arg = context.args[0].lower()
    global FORWARD_ENABLED

    if arg == "on":
        FORWARD_ENABLED = True
        await update.message.reply_text("Пересылка <b>ВКЛЮЧЕНА</b>", parse_mode="HTML")
        logger.info(f"Пересылка ВКЛЮЧЕНА {user_id}")
    elif arg == "off":
        FORWARD_ENABLED = False
        await update.message.reply_text("Пересылка <b>ВЫКЛЮЧЕНА</b>", parse_mode="HTML")
        logger.info(f"Пересылка ВЫКЛЮЧЕНА {user_id}")
    else:
        await update.message.reply_text("Используйте: `on` или `off`", parse_mode="Markdown")

# === ОБРАБОТКА КАНАЛА ===
async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.channel_post:
        return
    post = update.channel_post
    if post.chat_id != CHANNEL_ID:
        return

    msg_id = post.message_id
    link = get_message_link(post.chat_id, msg_id)

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

# === АВТОУДАЛЕНИЕ ===
async def cleanup_task(application):
    while True:
        if SUPER_ADMIN_ID:
            try:
                bot = application.bot
                cutoff_time = datetime.now() - timedelta(hours=48)
                async for message in bot.get_chat_history(chat_id=SUPER_ADMIN_ID, limit=1000):
                    if message.forward_from_chat and message.forward_from_chat.id == CHANNEL_ID:
                        if message.date < cutoff_time:
                            try:
                                await bot.delete_message(chat_id=SUPER_ADMIN_ID, message_id=message.message_id)
                                logger.info(f"Удалено старое сообщение #{message.message_id}")
                            except Exception as e:
                                logger.warning(f"Не удалось удалить #{message.message_id}: {e}")
                            await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Ошибка автоочистки: {e}")
        await asyncio.sleep(6 * 60 * 60)

# === ЗАПУСК ===
async def post_init(application: Application):
    asyncio.create_task(cleanup_task(application))

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)

def main():
    print("PhotoOnly Bot v3.1 | Webhook — НЕ засыпает!")

    # Запуск Flask
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Приложение
    global application
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("auth", auth))
    application.add_handler(CommandHandler("logout", logout))
    application.add_handler(CommandHandler("pause", pause_bot))
    application.add_handler(CommandHandler("resume", resume_bot))
    application.add_handler(CommandHandler("status", status_bot))
    application.add_handler(CommandHandler("forward", forward_control))
    # ... другие команды ...

    # Канал
    application.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & filters.Chat(chat_id=CHANNEL_ID),
        handle_channel_post
    ))

    # Webhook
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{BOT_TOKEN}"
    print(f"Webhook URL: {webhook_url}")
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get('PORT', 10000)),
        url_path=BOT_TOKEN,
        webhook_url=webhook_url
    )

if __name__ == '__main__':
    main()
