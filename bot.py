import os
import logging
import asyncio
import threading
import time
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from telegram.error import BadRequest

load_dotenv()

# === НАСТРОЙКИ ===
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID', '-1003008235648'))
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'TAVDIN')
ADMIN_CHAT_IDS = [int(x) for x in os.getenv('ADMIN_CHAT_IDS', '').split(',') if x]
SUPER_ADMIN_ID = int(os.getenv('SUPER_ADMIN_ID', '0'))
FORWARD_TO_IDS = [int(x) for x in os.getenv('FORWARD_TO_IDS', '').split(',') if x]

PAUSE_MODE = False
FORWARD_ENABLED = True

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

AUTHORIZED_USERS = {}
BANNED_USERS = set()
AMSTERDAM_TZ = ZoneInfo("Europe/Amsterdam")

# === ВСПОМОГАТЕЛЬНЫЕ ===
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
        [InlineKeyboardButton("ПАУЗА", callback_data="pause"),
         InlineKeyboardButton("АКТИВЕН", callback_data="resume")],
        [InlineKeyboardButton("Статус", callback_data="status"),
         InlineKeyboardButton("Выйти", callback_data="logout")]
    ]
    if user_id == SUPER_ADMIN_ID:
        fwd_text = "ПЕРЕСЫЛЯ ВКЛ" if FORWARD_ENABLED else "ПЕРЕСЫЛКА ВЫКЛ"
        keyboard.insert(2, [InlineKeyboardButton(fwd_text, callback_data="toggle_forward")])
    if user_id in ADMIN_CHAT_IDS:
        keyboard.append([InlineKeyboardButton("Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

def admin_panel():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Список авторизованных", callback_data="list_auth")],
        [InlineKeyboardButton("Деавторизовать", callback_data="deauth_start")],
        [InlineKeyboardButton("Забанить", callback_data="ban_start")],
        [InlineKeyboardButton("Разбанить", callback_data="unban_start")],
        [InlineKeyboardButton("Назад", callback_data="back_main")]
    ])

def get_main_text():
    status = "ПАУЗА" if PAUSE_MODE else "АКТИВЕН"
    return f"<b>PhotoOnly Bot v5.0 </b>\n\nСтатус: <b>{status}</b>\nКанал: <code>{CHANNEL_ID}</code>\n\nУправляйте кнопками:"

# === /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in BANNED_USERS:
        return await update.message.reply_text("Вы заблокированы.")
    if user_id not in AUTHORIZED_USERS and user_id not in ADMIN_CHAT_IDS:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Ввести пароль", callback_data="auth_prompt")]])
        return await update.message.reply_text(
            "<b>PhotoOnly Bot v5.0 </b>\n\nДля доступа нужен пароль.\nНажмите кнопку ниже:",
            parse_mode="HTML", reply_markup=keyboard
        )
    await update.message.reply_text(get_main_text(), parse_mode="HTML", reply_markup=main_menu(user_id))

# === АВТОРИЗАЦИЯ И ID ===
async def auth_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите пароль:\n`/auth ваш_пароль`", parse_mode="Markdown")
    context.user_data["awaiting_auth"] = True

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()

    if context.user_data.get("awaiting_auth"):
        if text.lower().startswith("/auth "):
            password = text[6:].strip()
            if password == ADMIN_PASSWORD:
                AUTHORIZED_USERS[user_id] = True
                await update.message.reply_text("Авторизация успешна!")
                await start(update, context)
            else:
                await update.message.reply_text("Неверный пароль.")
            context.user_data["awaiting_auth"] = False
        return

    expected = context.user_data.get("expecting_id")
    if not expected: return
    try:
        target_id = int(text)
    except ValueError:
        await update.message.reply_text("Ошибка: только цифры ID.")
        return

    action = expected["action"]
    msg = expected["message"]
    result = ""

    if action == "deauth":
        result = f"Деавторизован {target_id}" if AUTHORIZED_USERS.pop(target_id, None) else f"ID {target_id} не авторизован"
    elif action == "ban":
        if target_id in ADMIN_CHAT_IDS:
            result = "Нельзя забанить админа!"
        else:
            BANNED_USERS.add(target_id)
            result = f"Заблокирован {target_id}"
    elif action == "unban":
        BANNED_USERS.discard(target_id)
        result = f"Разблокирован {target_id}"

    await context.bot.edit_message_text(
        chat_id=msg.chat_id, message_id=msg.message_id,
        text=f"{result}\n\n{get_main_text()}",
        parse_mode="HTML", reply_markup=main_menu(user_id)
    )
    context.user_data.clear()

# === КНОПКИ ===
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if not await check_access(user_id, context):
        await query.edit_message_text("Доступ запрещён.")
        return

    global PAUSE_MODE, FORWARD_ENABLED

    try:
        if data in ["pause", "resume"]:
            if (data == "pause" and PAUSE_MODE) or (data == "resume" and not PAUSE_MODE): return
            PAUSE_MODE = data == "pause"
            await query.edit_message_text(get_main_text(), parse_mode="HTML", reply_markup=main_menu(user_id))

        elif data == "status":
            fwd = "ВКЛЮЧЕНА" if FORWARD_ENABLED else "ВЫКЛЮЧЕНА"
            status_msg = (
                f"<b>Статус:</b> {'ПАУЗА' if PAUSE_MODE else 'АКТИВЕН'}\n"
                f"<b>Пересылка:</b> {fwd}\n"
                f"<b>Авторизовано:</b> {len(AUTHORIZED_USERS)}\n"
                f"<b>Забанено:</b> {len(BANNED_USERS)}\n\n"
                f"Нажмите любую кнопку для возврата"
            )
            await query.edit_message_text(status_msg, parse_mode="HTML", reply_markup=main_menu(user_id))

        elif data == "logout":
            AUTHORIZED_USERS.pop(user_id, None)
            await query.edit_message_text("Вы вышли.\n/start — войти снова")

        elif data == "toggle_forward" and user_id == SUPER_ADMIN_ID:
            FORWARD_ENABLED = not FORWARD_ENABLED
            await query.edit_message_text(get_main_text(), parse_mode="HTML", reply_markup=main_menu(user_id))

        elif data == "admin_panel" and user_id in ADMIN_CHAT_IDS:
            await query.edit_message_text("Админ-панель", reply_markup=admin_panel())

        elif data == "back_main":
            await query.edit_message_text(get_main_text(), parse_mode="HTML", reply_markup=main_menu(user_id))

        elif data == "list_auth" and user_id in ADMIN_CHAT_IDS:
            users = "\n".join([f"• {uid}" for uid in AUTHORIZED_USERS.keys()]) or "Пусто"
            await query.edit_message_text(f"<b>Авторизованные:</b>\n{users}\n\n<i>Назад</i>", parse_mode="HTML", reply_markup=admin_panel())

        elif data == "auth_prompt":
            await auth_prompt(update, context)

        elif data in ["deauth_start", "ban_start", "unban_start"] and user_id in ADMIN_CHAT_IDS:
            action = {"deauth_start": "deauth", "ban_start": "ban", "unban_start": "unban"}[data]
            action_text = {"deauth": "Деавторизовать", "ban": "Забанить", "unban": "Разбанить"}[action]
            await query.edit_message_text(f"{action_text} пользователя:\n\nНапишите ID:")
            context.user_data["expecting_id"] = {"action": action, "message": query.message}

    except BadRequest as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Ошибка: {e}")

# === КАНАЛ ===
async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post = update.channel_post
    if not post or post.chat_id != CHANNEL_ID: return
    if not PAUSE_MODE and not (post.photo or post.video):
        try: await post.delete()
        except: pass
        return
    if FORWARD_ENABLED and FORWARD_TO_IDS:
        for uid in FORWARD_TO_IDS:
            try: await post.forward(uid)
            except: pass

# === АВТОУДАЛЕНИЕ + ЕЖЕДНЕВНЫЙ ОТЧЁТ ===
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

async def daily_report(app):
    while True:
        now = datetime.now(AMSTERDAM_TZ)
        next_run = datetime.combine(now.date(), time(9, 0), tzinfo=AMSTERDAM_TZ)
        if now.hour >= 9: next_run += timedelta(days=1)
        await asyncio.sleep((next_run - now).total_seconds())
        try:
            status = "ПАУЗА" if PAUSE_MODE else "АКТИВЕН"
            fwd = "ВКЛЮЧЕНА" if FORWARD_ENABLED else "ВЫКЛЮЧЕНА"
            await app.bot.send_message(
                SUPER_ADMIN_ID,
                f"<b>Бот жив! Ежедневный отчёт</b>\n\n"
                f"Дата: {now.strftime('%d.%m.%Y %H:%M')} (NL)\n"
                f"Статус: <b>{status}</b>\n"
                f"Пересылка: <b>{fwd}</b>\n"
                f"Авторизовано: {len(AUTHORIZED_USERS)}\n"
                f"Забанено: {len(BANNED_USERS)}\n\n"
                f"Render Free  — 100% работает 24/7",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Отчёт не отправлен: {e}")

async def post_init(app):
    asyncio.create_task(cleanup_task(app))
    asyncio.create_task(daily_report(app))

# === ЖЁСТКИЙ АНТИ-СОН ДЛЯ RENDER FREE 2025 (УЗБЕКИСТАН) ===
def render_keep_alive():
    url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}"
    while True:
        try:
            requests.get(url, timeout=10)
            print(f"[{datetime.now()}] RENDER KEEP-ALIVE ПИНГ — БОТ ЖИВ! URL: {url}")
        except:
            print(f"[{datetime.now()}] RENDER KEEP-ALIVE ОШИБКА — продолжаем")
        time.sleep(300)

threading.Thread(target=render_keep_alive, daemon=True).start()

# === ЗАПУСК ===
application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(button_handler))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
application.add_handler(MessageHandler(filters.ChatType.CHANNEL & filters.Chat(CHANNEL_ID), handle_channel_post))

webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{BOT_TOKEN}"
print(f"PhotoOnly Bot v5.0  | 100% НЕ СПИТ | {datetime.now().strftime('%H:%M %d.%m.%Y')}")
print(f"Webhook: {webhook_url}")

application.run_webhook(
    listen="0.0.0.0",
    port=int(os.environ.get("PORT", 10000)),
    url_path=BOT_TOKEN,
    webhook_url=webhook_url
)
