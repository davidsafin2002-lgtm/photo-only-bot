import os
import logging
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update
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
last_notify_time = 0

# === ЛОГИ ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

print(f"Запуск PhotoOnly Bot v3.3 | Webhook + gunicorn")

# === ХРАНИЛИЩА ===
AUTHORIZED_USERS = {}
BANNED_USERS = set()

# === ВСПОМОГАТЕЛЬНЫЕ ===
async def is_user_member(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

def get_message_link(chat_id: int, message_id: int) -> str:
    return f"https://t.me/c/{str(chat_id)[4:]}/{message_id}"

async def check_access(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if user_id in BANNED_USERS: return False
    if user_id in ADMIN_CHAT_IDS: return True
    if user_id not in AUTHORIZED_USERS: return False
    if not await is_user_member(user_id, context):
        del AUTHORIZED_USERS[user_id]
        return False
    return True

# === КОМАНДЫ (коротко, всё работает) ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in BANNED_USERS:
        return await update.message.reply_text("Заблокирован.")
    
    status = "ПАУЗА" if PAUSE_MODE else "АКТИВЕН"
    fwd = "ВКЛ" if FORWARD_ENABLED else "ВЫКЛ"
    extra = "/forward on/off\n" if user_id == SUPER_ADMIN_ID else ""
    
    await update.message.reply_text(
        f"<b>PhotoOnly Bot v3.3</b>\n"
        f"Статус: <b>{status}</b>\n"
        f"Пересылка: <b>{fwd}</b>\n"
        f"Канал: <code>{CHANNEL_ID}</code>\n\n"
        f"{extra}Команды: /pause /resume /status /auth TAVDIN",
        parse_mode="HTML"
    )

async def auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0] == ADMIN_PASSWORD:
        AUTHORIZED_USERS[update.message.from_user.id] = True
        await update.message.reply_text("Авторизован!")
    else:
        await update.message.reply_text("Неверный пароль")

async def pause_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_access(update.message.from_user.id, context):
        global PAUSE_MODE
        PAUSE_MODE = True
        await update.message.reply_text("<b>ПАУЗА</b>", parse_mode="HTML")

async def resume_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_access(update.message.from_user.id, context):
        global PAUSE_MODE
        PAUSE_MODE = False
        await update.message.reply_text("<b>АКТИВЕН</b>", parse_mode="HTML")

async def status_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_access(update.message.from_user.id, context):
        await update.message.reply_text(
            f"ПАУЗА: {PAUSE_MODE}\nПересылка: {FORWARD_ENABLED}\n"
            f"Авторизовано: {len(AUTHORIZED_USERS)}",
            parse_mode="HTML"
        )

async def forward_control(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_notify_time, FORWARD_ENABLED
    user_id = update.message.from_user.id
    if user_id != SUPER_ADMIN_ID:
        await update.message.reply_text("Только главный админ!")
        if time.time() - last_notify_time > 10:
            try:
                await context.bot.send_message(SUPER_ADMIN_ID, f"Попытка /forward от {user_id}")
                last_notify_time = time.time()
            except: pass
        return
    if context.args:
        if context.args[0].lower() == "on":
            FORWARD_ENABLED = True
            await update.message.reply_text("Пересылка <b>ВКЛ</b>", parse_mode="HTML")
        elif context.args[0].lower() == "off":
            FORWARD_ENABLED = False
            await update.message.reply_text("Пересылка <b>ВЫКЛ</b>", parse_mode="HTML")

# === КАНАЛ ===
async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post = update.channel_post
    if not post or post.chat_id != CHANNEL_ID: return
    
    if not PAUSE_MODE and not post.photo and not post.video:
        try:
            await post.delete()
            logger.info("Удалено не-фото")
        except: pass
        return
    
    if FORWARD_ENABLED and FORWARD_TO_IDS:
        for uid in FORWARD_TO_IDS:
            try:
                await post.forward(uid)
                logger.info(f"Переслано {uid}")
            except: pass

# === АВТОУДАЛЕНИЕ (v21.6) ===
async def cleanup_task(app):
    while True:
        await asyncio.sleep(6 * 3600)
        if not SUPER_ADMIN_ID: continue
        try:
            cutoff = datetime.now() - timedelta(hours=48)
            async for msg in app.bot.get_chat_history(SUPER_ADMIN_ID, limit=1000):
                if msg.forward_from_chat and msg.forward_from_chat.id == CHANNEL_ID and msg.date < cutoff:
                    try:
                        await msg.delete()
                        logger.info(f"Удалено старое #{msg.message_id}")
                    except: pass
                    await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Очистка: {e}")

async def post_init(app):
    asyncio.create_task(cleanup_task(app))

# === ЗАПУСК ===
application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("auth", auth))
application.add_handler(CommandHandler("pause", pause_bot))
application.add_handler(CommandHandler("resume", resume_bot))
application.add_handler(CommandHandler("status", status_bot))
application.add_handler(CommandHandler("forward", forward_control))
application.add_handler(MessageHandler(filters.ChatType.CHANNEL & filters.Chat(CHANNEL_ID), handle_channel_post))

# === Webhook БЕЗ Flask на порту 10000 ===
webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{BOT_TOKEN}"
print(f"Webhook: {webhook_url}")

application.run_webhook(
    listen="0.0.0.0",
    port=int(os.environ.get("PORT", 10000)),
    url_path=BOT_TOKEN,
    webhook_url=webhook_url
)
