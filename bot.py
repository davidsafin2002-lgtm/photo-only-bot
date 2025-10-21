import os
import logging
import threading
import time
from dotenv import load_dotenv
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError

# Загрузка переменных окружения
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID', '-1001805328200'))
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'TAVDIN')
ADMIN_CHAT_IDS = [int(x) for x in os.getenv('ADMIN_CHAT_IDS', '').split(',') if x]

# Инициализация
PAUSE_MODE = False

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

if not BOT_TOKEN or len(BOT_TOKEN) < 30:
    print("ОШИБКА: BOT_TOKEN не найден!")
    exit(1)

print(f"Токен загружен: {len(BOT_TOKEN)} символов")
print(f"Канал: {CHANNEL_ID}")
print(f"Админы: {ADMIN_CHAT_IDS}")

# Flask для UptimeRobot
app = Flask(__name__)

@app.route('/')
def health_check():
    return {"status": "ok", "bot": "running", "admins": len(ADMIN_CHAT_IDS), "timestamp": time.time()}

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

# Генерация ссылки на сообщение в канале
def get_message_link(chat_id: int, message_id: int) -> str:
    # Для каналов: https://t.me/c/{channel_id_without_minus}/{message_id}
    clean_id = str(chat_id)[4:]  # Убираем -100
    return f"https://t.me/c/{clean_id}/{message_id}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in BANNED_USERS:
        await update.message.reply_text("Вы заблокированы и не можете использовать бот.")
        return

    if user_id in ADMIN_CHAT_IDS:
        status = "ПАУЗА" if PAUSE_MODE else "АКТИВЕН"
        await update.message.reply_text(
            f"**PhotoOnly Bot v2.5**\n\n"
            f"{status}\n"
            f"Канал: `{CHANNEL_ID}`\n\n"
            f"Вы админ!\n"
            f"Команды:\n"
            f"`/pause` - Приостановить\n"
            f"`/resume` - Возобновить\n"
            f"`/status` - Статус\n"
            f"`/logout` - Выйти\n"
            f"`/list_auth` - Список авторизованных\n"
            f"`/deauth <ID>` - Деавторизовать\n"
            f"`/ban <ID>` - Заблокировать\n"
            f"`/unban <ID>` - Разблокировать",
            parse_mode='Markdown'
        )
    elif user_id in AUTHORIZED_USERS:
        is_member = await is_user_member(user_id, context)
        if not is_member:
            del AUTHORIZED_USERS[user_id]
            await update.message.reply_text("Вы отписались от канала. Авторизация отменена. Подпишитесь и используйте /auth.")
            return
        status = "ПАУЗА" if PAUSE_MODE else "АКТИВЕН"
        await update.message.reply_text(
            f"**PhotoOnly Bot v2.5**\n\n"
            f"{status}\n"
            f"Канал: `{CHANNEL_ID}`\n\n"
            f"Вы авторизованы!\n"
            f"Команды:\n"
            f"`/pause` - Приостановить\n"
            f"`/resume` - Возобновить\n"
            f"`/status` - Статус\n",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("Введите пароль для авторизации:\n`/auth <ваш_пароль>`")

async def auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in BANNED_USERS:
        await update.message.reply_text("Вы заблокированы и не можете авторизоваться.")
        return

    if user_id in ADMIN_CHAT_IDS:
        if context.args and context.args[0] == ADMIN_PASSWORD:
            AUTHORIZED_USERS[user_id] = True
            await update.message.reply_text("Авторизация успешна!\nНажмите /start.")
        else:
            await update.message.reply_text("Неверный пароль!")
        return

    is_member = await is_user_member(user_id, context)
    if not is_member:
        await update.message.reply_text("Вы должны быть подписаны на канал для авторизации!")
        return

    if context.args and context.args[0] == ADMIN_PASSWORD:
        AUTHORIZED_USERS[user_id] = True
        await update.message.reply_text("Авторизация успешна!\nНажмите /start.")
    else:
        await update.message.reply_text("Неверный пароль!")

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in AUTHORIZED_USERS:
        del AUTHORIZED_USERS[user_id]
        await update.message.reply_text("Вы вышли из аккаунта.")
    else:
        await update.message.reply_text("Вы не авторизованы.")

# Универсальная проверка доступа
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

async def pause_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not await check_access(user_id, context):
        await update.message.reply_text("Только для авторизованных и подписанных!")
        return
    global PAUSE_MODE
    PAUSE_MODE = True
    logger.info(f"ПАУЗА от {user_id}")
    await update.message.reply_text("**ПАУЗА!** Удаление остановлено.")

async def resume_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not await check_access(user_id, context):
        await update.message.reply_text("Только для авторизованных и подписанных!")
        return
    global PAUSE_MODE
    PAUSE_MODE = False
    logger.info(f"АКТИВЕН от {user_id}")
    await update.message.reply_text("**АКТИВЕН!** Удаляет НЕ-фото и НЕ-видео.")

async def status_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not await check_access(user_id, context):
        await update.message.reply_text("Только для авторизованных и подписанных!")
        return
    status = "ПАУЗА" if PAUSE_MODE else "АКТИВЕН"
    await update.message.reply_text(
        f"**{status}**\n"
        f"Канал: `{CHANNEL_ID}`\n"
        f"Админы: {len(ADMIN_CHAT_IDS)}\n"
        f"Авторизовано: {len(AUTHORIZED_USERS)}",
        parse_mode='Markdown'
    )

# Админские команды
async def list_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in ADMIN_CHAT_IDS:
        await update.message.reply_text("Только для админов!")
        return
    if AUTHORIZED_USERS:
        user_list = "\n".join([f"• {uid}" for uid in AUTHORIZED_USERS.keys()])
        await update.message.reply_text(f"**Авторизованные:**\n{user_list}\nВсего: {len(AUTHORIZED_USERS)}", parse_mode='Markdown')
    else:
        await update.message.reply_text("Нет авторизованных пользователей.")

async def deauth_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in ADMIN_CHAT_IDS:
        await update.message.reply_text("Только для админов!")
        return
    if context.args:
        try:
            target_id = int(context.args[0])
            if target_id in AUTHORIZED_USERS:
                del AUTHORIZED_USERS[target_id]
                await update.message.reply_text(f"Пользователь {target_id} деавторизован.")
            else:
                await update.message.reply_text(f"Пользователь {target_id} не авторизован.")
        except ValueError:
            await update.message.reply_text("Укажите ID: `/deauth 123456789`")
    else:
        await update.message.reply_text("Укажите ID: `/deauth 123456789`")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in ADMIN_CHAT_IDS:
        await update.message.reply_text("Только для админов!")
        return
    if context.args:
        try:
            target_id = int(context.args[0])
            if target_id in ADMIN_CHAT_IDS:
                await update.message.reply_text("Нельзя заблокировать администратора!")
                return
            BANNED_USERS.add(target_id)
            await update.message.reply_text(f"Пользователь {target_id} заблокирован.")
        except ValueError:
            await update.message.reply_text("Укажите ID: `/ban 123456789`")
    else:
        await update.message.reply_text("Укажите ID: `/ban 123456789`")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in ADMIN_CHAT_IDS:
        await update.message.reply_text("Только для админов!")
        return
    if context.args:
        try:
            target_id = int(context.args[0])
            BANNED_USERS.discard(target_id)
            await update.message.reply_text(f"Пользователь {target_id} разблокирован.")
        except ValueError:
            await update.message.reply_text("Укажите ID: `/unban 123456789`")
    else:
        await update.message.reply_text("Укажите ID: `/unban 123456789`")

# Обработка сообщений в канале
async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.channel_post:
        return

    post = update.channel_post
    if post.chat_id != CHANNEL_ID:
        return

    message_id = post.message_id
    link = get_message_link(post.chat_id, message_id)
    user_id = post.from_user.id if post.from_user else None
    username = post.from_user.username if post.from_user and post.from_user.username else "Неизвестно"

    # ЛОГИРУЕМ ССЫЛКУ
    logger.info(f"ПРОВЕРКА: {link} | от @{username} ({user_id}) | ID: {message_id}")

    if not PAUSE_MODE and not post.photo and not post.video:
        try:
            await context.bot.delete_message(post.chat_id, message_id)
            logger.info(f"УДАЛЕНО: {link}")
        except Exception as e:
            logger.error(f"ОШИБКА удаления {link}: {e}")
    else:
        logger.info(f"ОСТАВЛЕНО: {link} | Фото/Видео")

def main():
    print("PhotoOnly Bot v2.5 с ссылками в логах")

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("HTTP сервер запущен")

    application = Application.builder().token(BOT_TOKEN).build()

    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("auth", auth))
    application.add_handler(CommandHandler("logout", logout))
    application.add_handler(CommandHandler("pause", pause_bot))
    application.add_handler(CommandHandler("resume", resume_bot))
    application.add_handler(CommandHandler("status", status_bot))
    application.add_handler(CommandHandler("list_auth", list_auth))
    application.add_handler(CommandHandler("deauth", deauth_user))
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("unban", unban_user))

    # Канал
    application.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & filters.Chat(chat_id=CHANNEL_ID),
        handle_channel_post
    ))

    print("Запуск polling...")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
