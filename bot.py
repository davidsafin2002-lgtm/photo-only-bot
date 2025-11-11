import os
import logging
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,      # <-- ДОБАВЛЕНО
    filters,
    ContextTypes
)
from telegram.error import TelegramError

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID', '-1003008235648'))
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'TAVDIN')
ADMIN_CHAT_IDS = [int(x) for x in os.getenv('ADMIN_CHAT_IDS', '').split(',') if x]
SUPER_ADMIN_ID = int(os.getenv('SUPER_ADMIN_ID', '0'))
FORWARD_TO_IDS = [int(x) for x in os.getenv('FORWARD_TO_IDS', '').split(',') if x]

PAUSE_MODE = False
FORWARD_ENABLED = True
last_notify_time = 0

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

AUTHORIZED_USERS = {}
BANNED_USERS = set()

async def is_user_member(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

async def check_access(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if user_id in BANNED_USERS: return False
    if user_id in ADMIN_CHAT_IDS: return True
    if user_id not in AUTHORIZED_USERS: return False
    if not await is_user_member(user_id, context):
        del AUTHORIZED_USERS[user_id]
        return False
    return True

# === КНОПКИ ===
def main_menu(user_id: int):
    keyboard = [
        [InlineKeyboardButton("Пауза", callback_data="pause"),
         InlineKeyboardButton("Активен", callback_data="resume")],
        [InlineKeyboardButton("Статус", callback_data="status"),
         InlineKeyboardButton("Выйти", callback_data="logout")]
    ]
    if user_id == SUPER_ADMIN_ID:
        fwd_text = "Пересылка ВЫКЛ" if FORWARD_ENABLED else "Пересылка ВКЛ"
        keyboard.insert(2, [InlineKeyboardButton(fwd_text, callback_data="toggle_forward")])
    if user_id in ADMIN_CHAT_IDS:
        keyboard.append([InlineKeyboardButton("Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

def admin_panel():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Список авторизованных", callback_data="list_auth")],
        [InlineKeyboardButton("Деавторизовать", callback_data="deauth_prompt")],
        [InlineKeyboardButton("Забанить", callback_data="ban_prompt")],
        [InlineKeyboardButton("Разбанить", callback_data="unban_prompt")],
        [InlineKeyboardButton("Назад", callback_data="back_main")]
    ])

# === /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in BANNED_USERS:
        return await update.message.reply_text("Вы заблокированы.")

    if user_id not in AUTHORIZED_USERS and user_id not in ADMIN_CHAT_IDS:
        return await update.message.reply_text("Введите пароль:\n`/auth...`", parse_mode="Markdown")

    status = "ПАУЗА" if PAUSE_MODE else "АКТИВЕН"
    await update.message.reply_text(
        f"<b>PhotoOnly Bot v3.5</b>\n\n"
        f"Статус: <b>{status}</b>\n"
        f"Канал: <code>{CHANNEL_ID}</code>\n\n"
        f"Управляйте кнопками ниже",
        parse_mode="HTML",
        reply_markup=main_menu(user_id)
    )

# === КНОПКИ ===
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if not await check_access(user_id, context):
        return await query.edit_message_text("Доступ запрещён.")

    global PAUSE_MODE, FORWARD_ENABLED

    if data == "pause":
        PAUSE_MODE = True
        await query.edit_message_reply_markup(reply_markup=main_menu(user_id))
        await query.message.reply_text("ПАУЗА! Удаление остановлено.")

    elif data == "resume":
        PAUSE_MODE = False
        await query.edit_message_reply_markup(reply_markup=main_menu(user_id))
        await query.message.reply_text("АКТИВЕН! Удаляет НЕ-фото/видео.")

    elif data == "status":
        fwd = "ВКЛЮЧЕНА" if FORWARD_ENABLED else "ВЫКЛЮЧЕНА"
        await query.message.reply_text(
            f"<b>Статус:</b> {'ПАУЗА' if PAUSE_MODE else 'АКТИВЕН'}\n"
            f"<b>Пересылка:</b> {fwd}\n"
            f"<b>Авторизовано:</b> {len(AUTHORIZED_USERS)}",
            parse_mode="HTML"
        )

    elif data == "logout":
        if user_id in AUTHORIZED_USERS:
            del AUTHORIZED_USERS[user_id]
        await query.edit_message_text("Вы вышли. Напишите /start для входа.")

    elif data == "toggle_forward" and user_id == SUPER_ADMIN_ID:
        FORWARD_ENABLED = not FORWARD_ENABLED
        await query.edit_message_reply_markup(reply_markup=main_menu(user_id))
        await query.message.reply_text(f"Пересылка {'ВКЛЮЧЕНА' if FORWARD_ENABLED else 'ВЫКЛЮЧЕНА'}")

    elif data == "admin_panel" and user_id in ADMIN_CHAT_IDS:
        await query.edit_message_text("Админ-панель", reply_markup=admin_panel())

    elif data == "back_main":
        await query.edit_message_text("Главное меню", reply_markup=main_menu(user_id))

    elif data == "list_auth" and user_id in ADMIN_CHAT_IDS:
        users = "\n".join([f"• {uid}" for uid in AUTHORIZED_USERS.keys()]) if AUTHORIZED_USERS else "Пусто"
        await query.message.reply_text(f"<b>Авторизованные:</b>\n{users}", parse_mode="HTML")

# === КАНАЛ ===
async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post = update.channel_post
    if not post or post.chat_id != CHANNEL_ID: return
    if not PAUSE_MODE and not post.photo and not post.video:
        try: await post.delete()
        except: pass
        return
    if FORWARD_ENABLED and FORWARD_TO_IDS:
        for uid in FORWARD_TO_IDS:
            try: await post.forward(uid)
            except: pass

# === АВТОУДАЛЕНИЕ ===
async def cleanup_task(app):
    while True:
        await asyncio.sleep(6 * 3600)
        if SUPER_ADMIN_ID:
            try:
                cutoff = datetime.now() - timedelta(hours=48)
                async for msg in app.bot.get_chat_history(SUPER_ADMIN_ID, limit=1000):
                    if msg.forward_from_chat and msg.forward_from_chat.id == CHANNEL_ID and msg.date < cutoff:
                        try: await msg.delete()
                        except: pass
                        await asyncio.sleep(0.1)
            except: pass

async def post_init(app):
    asyncio.create_task(cleanup_task(app))

# === ЗАПУСК ===
application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(button_handler))
application.add_handler(MessageHandler(filters.ChatType.CHANNEL & filters.Chat(CHANNEL_ID), handle_channel_post))

webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{BOT_TOKEN}"
print(f"PhotoOnly Bot v3.5 | КНОПКИ + WEBHOOK")
print(f"Webhook: {webhook_url}")

application.run_webhook(
    listen="0.0.0.0",
    port=int(os.environ.get("PORT", 10000)),
    url_path=BOT_TOKEN,
    webhook_url=webhook_url
)
