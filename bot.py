import os
import logging
import threading
import time
from dotenv import load_dotenv
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError

# Загрузка .env
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID', '-1001805328200'))
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'TAVDIN')
ADMIN_CHAT_IDS = [int(x) for x in os.getenv('ADMIN_CHAT_IDS', '').split(',') if x]
MAIN_ADMIN_ID = int(os.getenv('MAIN_ADMIN_ID', '0'))

# Глобальные переменные
PAUSE_MODE = False
FORWARD_ENABLED = True  # По умолчанию включено

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Проверка токена
if not BOT_TOKEN or len(BOT_TOKEN) < 30:
    print("ОШИБКА: BOT_TOKEN не найден!")
    exit(1)

print(f"Токен: {len(BOT_TOKEN)} символов")
print(f"Канал: {CHANNEL_ID}")
print(f"Админы: {ADMIN_CHAT_IDS}")
print(f"Пересылка: {'ВКЛ' if FORWARD_ENABLED else 'ВЫКЛ'} (MAIN_ADMIN_ID={MAIN_ADMIN_ID})")

# Flask (UptimeRobot)
app = Flask(__name__)
@app.route('/')
def health_check():
    return {"status": "ok", "bot": "running", "admins": len(ADMIN_CHAT_IDS), "forward": FORWARD_ENABLED, "timestamp": time.time()}

def run_flask():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

# Хранилища
AUTHORIZED_USERS = {}
BANNED_USERS = set()

# Проверка подписки
async def is_user_member(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except TelegramError as e:
        logger.warning(f"Ошибка проверки подписки {user_id}: {e}")
        return False

# Ссылка на сообщение
def get_message_link(chat_id: int, message_id: int) -> str:
    clean_id = str(chat_id)[4:]
    return f"https://t.me/c/{clean_id}/{message_id}"

# Проверка доступа
async def check_access(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if user_id in BANNED_USERS:
        return False
    if user_id in ADMIN_CHAT_IDS:
        return True
    if user_id not in AUTHORIZED_USERS:
        return False
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
        await update.message.reply_text(
            f"<b>PhotoOnly Bot v2.7</b>\n\n"
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
            f"/forward on/off - Вкл/Выкл пересылку",
            parse_mode="HTML"
        )
    elif user_id in AUTHORIZED_USERS:
        if not await is_user_member(user_id, context):
            del AUTHORIZED_USERS[user_id]
            await update.message.reply_text("Вы отписались от канала. Авторизация отменена.")
            return
        await update.message.reply_text(
            f"<b>PhotoOnly Bot v2.7</b>\n\n"
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

async

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

# === КОМАНДА УПРАВЛЕНИЯ ПЕРЕСЫЛКОЙ ===
async def forward_control(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in ADMIN_CHAT_IDS:
        await update.message.reply_text("Только админы!")
        return

    if not context.args:
        await update.message.reply_text("Использование: `/forward on` или `/forward off`", parse_mode="Markdown")
        return

    arg = context.args[0].lower()
    global FORWARD_ENABLED

    if arg == "on":
        FORWARD_ENABLED = True
        await update.message.reply_text("Пересылка <b>ВКЛЮЧЕНА</b>", parse_mode="HTML")
        logger.info(f"Пересылка ВКЛЮЧЕНА админом {user_id}")
    elif arg == "off":
        FORWARD_ENABLED = False
        await update.message.reply_text("Пересылка <b>ВЫКЛЮЧЕНА</b>", parse_mode="HTML")
        logger.info(f"Пересылка ВЫКЛЮЧЕНА админом {user_id}")
    else:
        await update.message.reply_text("Неверная команда. Используйте: `on` или `off`", parse_mode="Markdown")

# === АДМИНСКИЕ КОМАНДЫ ===
async def list_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_CHAT_IDS:
        await update.message.reply_text("Только админы!")
        return
    if AUTHORIZED_USERS:
        users = "\n".join([f"• {uid}" for uid in AUTHORIZED_USERS.keys()])
        await update.message.reply_text(f"<b>Авторизованные:</b>\n{users}\nВсего: {len(AUTHORIZED_USERS)}", parse_mode="HTML")
    else:
        await update.message.reply_text("Нет авторизованных.")

async def deauth_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_CHAT_IDS:
        await update.message.reply_text("Только админы!")
        return
    if context.args:
        try:
            uid = int(context.args[0])
            if uid in AUTHORIZED_USERS:
                del AUTHORIZED_USERS[uid]
                await update.message.reply_text(f"Деавторизован {uid}")
            else:
                await update.message.reply_text(f"Не авторизован {uid}")
        except ValueError:
            await update.message.reply_text("Укажите ID: `/deauth 123`")
    else:
        await update.message.reply_text("Укажите ID")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_CHAT_IDS:
        await update.message.reply_text("Только админы!")
        return
    if context.args:
        try:
            uid = int(context.args[0])
            if uid in ADMIN_CHAT_IDS:
                await update.message.reply_text("Нельзя забанить админа!")
                return
            BANNED_USERS.add(uid)
            await update.message.reply_text(f"Заблокирован {uid}")
        except ValueError:
            await update.message.reply_text("Укажите ID: `/ban 123`")
    else:
        await update.message.reply_text("Укажите ID")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_CHAT_IDS:
        await update.message.reply_text("Только админы!")
        return
    if context.args:
        try:
            uid = int(context.args[0])
            BANNED_USERS.discard(uid)
            await update.message.reply_text(f"Разблокирован {uid}")
        except ValueError:
            await update.message.reply_text("Укажите ID: `/unban 123`")
    else:
        await update.message.reply_text("Укажите ID")

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

    # Удаляем НЕ фото/видео
    if not PAUSE_MODE and not post.photo and not post.video:
        try:
            await context.bot.delete_message(post.chat_id, msg_id)
            logger.info(f"УДАЛЕНО: {link}")
        except Exception as e:
            logger.error(f"ОШИБКА удаления {link}: {e}")
        return

    # Оставляем фото/видео
    logger.info(f"ОСТАВЛЕНО: {link} | Фото/Видео")

    # ПЕРЕСЫЛКА — ТОЛЬКО ЕСЛИ ВКЛЮЧЕНО
    if FORWARD_ENABLED and MAIN_ADMIN_ID and MAIN_ADMIN_ID != 0:
        try:
            await context.bot.forward_message(
                chat_id=MAIN_ADMIN_ID,
                from_chat_id=CHANNEL_ID,
                message_id=msg_id
            )
            logger.info(f"ПЕРЕСЛАНО админу {MAIN_ADMIN_ID}: {link}")
        except Exception as e:
            logger.error(f"ОШИБКА пересылки {MAIN_ADMIN_ID}: {e}")

# === ЗАПУСК ===
def main():
    print("PhotoOnly Bot v2.7 | Пересылка с /forward on/off")

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("HTTP сервер запущен")

    app = Application.builder().token(BOT_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("auth", auth))
    app.add_handler(CommandHandler("logout", logout))
    app.add_handler(CommandHandler("pause", pause_bot))
    app.add_handler(CommandHandler("resume", resume_bot))
    app.add_handler(CommandHandler("status", status_bot))
    app.add_handler(CommandHandler("forward", forward_control))  # НОВАЯ КОМАНДА
    app.add_handler(CommandHandler("list_auth", list_auth))
    app.add_handler(CommandHandler("deauth", deauth_user))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))

    # Канал
    app.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & filters.Chat(chat_id=CHANNEL_ID),
        handle_channel_post
    ))

    print("Запуск polling...")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
