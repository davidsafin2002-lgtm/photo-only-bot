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
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'TAVDIN')  # Пароль по умолчанию
ADMIN_CHAT_IDS = [int(x) for x in os.getenv('ADMIN_CHAT_IDS', '').split(',') if x]  # Список ID админов

# Инициализация глобальной переменной
PAUSE_MODE = False  # По умолчанию бот активен

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Скрываем токен в логах HTTP
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

if not BOT_TOKEN or len(BOT_TOKEN) < 30:
    print("❌ ОШИБКА: BOT_TOKEN не найден!")
    exit(1)

print(f"✅ Токен загружен: {len(BOT_TOKEN)} символов")
print(f"📢 Канал: {CHANNEL_ID}")
print(f"👤 Админы: {ADMIN_CHAT_IDS}")

# Flask для UptimeRobot
app = Flask(__name__)

@app.route('/')
def health_check():
    return {
        "status": "ok",
        "bot": "running",
        "admins": len(ADMIN_CHAT_IDS),
        "timestamp": time.time()
    }

def run_flask():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

# Хранилище авторизованных пользователей
AUTHORIZED_USERS = {}

# Хранилище заблокированных пользователей
BANNED_USERS = set()

# Проверка подписки на канал
async def is_user_member(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except TelegramError as e:
        logger.warning(f"Ошибка проверки подписки для {user_id}: {e}")
        return False

# Проверка авторизации и подписки (общая функция)
async def check_access(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if user_id in BANNED_USERS:
        return False
    if user_id in ADMIN_CHAT_IDS:
        return True  # Админы пропускаются
    if user_id not in AUTHORIZED_USERS:
        return False
    # Проверка подписки для авторизованных
    return await is_user_member(user_id, context)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in BANNED_USERS:
        await update.message.reply_text("🚫 Вы заблокированы и не можете использовать бот.")
        return

    if user_id in ADMIN_CHAT_IDS:
        status = "⏸️ ПАУЗА" if PAUSE_MODE else "▶️ АКТИВЕН"
        await update.message.reply_text(
            f"🤖 **PhotoOnly Bot v2.5**\n\n"
            f"📊 {status}\n"
            f"📢 Канал: `{CHANNEL_ID}`\n\n"
            f"🔐 Вы админ!\n"
            f"👤 Ваши команды:\n"
            f"⏸️ `/pause` - Приостановить\n"
            f"▶️ `/resume` - Возобновить\n"
            f"ℹ️ `/status` - Статус\n"
            f"🔓 `/logout` - Выйти\n"
            f"🔑 `/list_auth` - Список авторизованных\n"
            f"🔓 `/deauth <ID>` - Деавторизовать\n"
            f"🚫 `/ban <ID>` - Заблокировать\n"
            f"✅ `/unban <ID>` - Разблокирован",
            parse_mode='Markdown'
        )
    elif user_id in AUTHORIZED_USERS:
        is_member = await is_user_member(user_id, context)
        if not is_member:
            del AUTHORIZED_USERS[user_id]  # Отменяем авторизацию
            await update.message.reply_text("❌ Вы отписались от канала. Авторизация отменена. Подпишитесь и используйте /auth.")
            return
        status = "⏸️ ПАУЗА" if PAUSE_MODE else "▶️ АКТИВЕН"
        await update.message.reply_text(
            f"🤖 **PhotoOnly Bot v2.5**\n\n"
            f"📊 {status}\n"
            f"📢 Канал: `{CHANNEL_ID}`\n\n"
            f"🔐 Вы авторизованы!\n"
            f"👤 Ваши команды:\n"
            f"⏸️ `/pause` - Приостановить\n"
            f"▶️ `/resume` - Возобновить\n"
            f"ℹ️ `/status` - Статус\n",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("🔐 Введите пароль для авторизации:\n`/auth ваш_пароль`")

async def auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in BANNED_USERS:
        await update.message.reply_text("🚫 Вы заблокированы и не можете авторизоваться.")
        return

    # Пропускаем проверку подписки для админов
    if user_id in ADMIN_CHAT_IDS:
        if context.args:
            password = context.args[0]
            if password == ADMIN_PASSWORD:
                AUTHORIZED_USERS[user_id] = True
                await update.message.reply_text(
                    "✅ Авторизация успешна!\n"
                    "🔑 Пожалуйста, нажмите /start, чтобы увидеть команды."
                )
            else:
                await update.message.reply_text("❌ Неверный пароль! Попробуйте снова.")
        else:
            await update.message.reply_text("🔐 Пожалуйста, укажите пароль: `/auth ваш_пароль`")
        return

    # Проверка подписки для обычных пользователей
    is_member = await is_user_member(user_id, context)
    if not is_member:
        await update.message.reply_text("❌ Вы должны быть подписаны на канал для авторизации!")
        return

    if context.args:
        password = context.args[0]
        if password == ADMIN_PASSWORD:
            AUTHORIZED_USERS[user_id] = True
            await update.message.reply_text(
                "✅ Авторизация успешна!\n"
                "🔑 Пожалуйста, нажмите /start, чтобы увидеть команды."
            )
        else:
            await update.message.reply_text("❌ Неверный пароль! Попробуйте снова.")
    else:
        await update.message.reply_text("🔐 Пожалуйста, укажите пароль: `/auth ваш_пароль`")

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in AUTHORIZED_USERS:
        del AUTHORIZED_USERS[user_id]
        await update.message.reply_text("🔓 Вы вышли из аккаунта.")
    else:
        await update.message.reply_text("🔐 Вы не авторизованы.")

async def pause_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in ADMIN_CHAT_IDS:
        # Проверка подписки для авторизованных пользователей
        if user_id not in AUTHORIZED_USERS:
            await update.message.reply_text("🔐 Только для авторизованных!")
            return
        is_member = await is_user_member(user_id, context)
        if not is_member:
            del AUTHORIZED_USERS[user_id]  # Отменяем авторизацию
            await update.message.reply_text("❌ Вы отписались от канала. Авторизация отменена. Подпишитесь и используйте /auth.")
            return

    global PAUSE_MODE
    PAUSE_MODE = True
    logger.info(f"⏸️ ПАУЗА от {user_id}")
    await update.message.reply_text("⏸️ **ПАУЗА!** Удаление остановлено.")

async def resume_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in ADMIN_CHAT_IDS:
        # Проверка подписки для авторизованных пользователей
        if user_id not in AUTHORIZED_USERS:
            await update.message.reply_text("🔐 Только для авторизованных!")
            return
        is_member = await is_user_member(user_id, context)
        if not is_member:
            del AUTHORIZED_USERS[user_id]  # Отменяем авторизацию
            await update.message.reply_text("❌ Вы отписались от канала. Авторизация отменена. Подпишитесь и используйте /auth.")
            return

    global PAUSE_MODE
    PAUSE_MODE = False
    logger.info(f"▶️ АКТИВЕН от {user_id}")
    await update.message.reply_text("▶️ **АКТИВЕН!** Удаляет НЕ-фото и НЕ-видео.")

async def status_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in ADMIN_CHAT_IDS:
        # Проверка подписки для авторизованных пользователей
        if user_id not in AUTHORIZED_USERS:
            await update.message.reply_text("🔐 Только для авторизованных!")
            return
        is_member = await is_user_member(user_id, context)
        if not is_member:
            del AUTHORIZED_USERS[user_id]  # Отменяем авторизацию
            await update.message.reply_text("❌ Вы отписались от канала. Авторизация отменена. Подпишитесь и используйте /auth.")
            return

    status = "⏸️ ПАУЗА" if PAUSE_MODE else "▶️ АКТИВЕН"
    authorized_count = len(AUTHORIZED_USERS)
    await update.message.reply_text(
        f"📊 **{status}**\n"
        f"📢 Канал: `{CHANNEL_ID}`\n"
        f"👤 Админы: {len(ADMIN_CHAT_IDS)}\n"
        f"🔑 Авторизовано пользователей: {authorized_count}",
        parse_mode='Markdown'
    )

# Команды для админов: управление авторизованными пользователями
async def list_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in ADMIN_CHAT_IDS:
        await update.message.reply_text("🔐 Только для админов!")
        return
    if AUTHORIZED_USERS:
        user_list = "\n".join([f"• {uid}" for uid in AUTHORIZED_USERS.keys()])
        await update.message.reply_text(
            f"🔑 **Авторизованные пользователи:**\n"
            f"{user_list}\n"
            f"👥 Всего: {len(AUTHORIZED_USERS)}",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("🔑 Нет авторизованных пользователей.")

async def deauth_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in ADMIN_CHAT_IDS:
        await update.message.reply_text("🔐 Только для админов!")
        return
    if context.args:
        try:
            target_id = int(context.args[0])
            if target_id in AUTHORIZED_USERS:
                del AUTHORIZED_USERS[target_id]
                await update.message.reply_text(f"✅ Пользователь {target_id} деавторизован.")
            else:
                await update.message.reply_text(f"❌ Пользователь {target_id} не авторизован.")
        except ValueError:
            await update.message.reply_text("❌ Укажите ID: `/deauth 123456789`")
    else:
        await update.message.reply_text("❌ Укажите ID: `/deauth 123456789`")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in ADMIN_CHAT_IDS:
        await update.message.reply_text("🔐 Только для админов!")
        return
    if context.args:
        try:
            target_id = int(context.args[0])
            if target_id in ADMIN_CHAT_IDS:
                await update.message.reply_text("❌ Нельзя заблокировать администратора!")
                return
            BANNED_USERS.add(target_id)
            await update.message.reply_text(f"🚫 Пользователь {target_id} заблокирован.")
        except ValueError:
            await update.message.reply_text("❌ Укажите ID: `/ban 123456789`")
    else:
        await update.message.reply_text("❌ Укажите ID: `/ban 123456789`")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in ADMIN_CHAT_IDS:
        await update.message.reply_text("🔐 Только для админов!")
        return
    if context.args:
        try:
            target_id = int(context.args[0])
            BANNED_USERS.discard(target_id)
            await update.message.reply_text(f"✅ Пользователь {target_id} разблокирован.")
        except ValueError:
            await update.message.reply_text("❌ Укажите ID: `/unban 123456789`")
    else:
        await update.message.reply_text("❌ Укажите ID: `/unban 123456789`")

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.channel_post:
        return

    post = update.channel_post
    if post.chat_id != CHANNEL_ID:
        return

    # Логирование для отладки
    user_id = post.from_user.id if post.from_user else None
    logger.info(f"Проверка сообщения #{post.message_id} от пользователя {user_id or 'Неизвестно'}")
    
    if not PAUSE_MODE and not post.photo and not post.video:
        try:
            await context.bot.delete_message(post.chat_id, post.message_id)
            logger.info(f"🗑️ УДАЛЕНО #{post.message_id}")
        except Exception as e:
            logger.error(f"❌ {e}")

def main():
    print("🚀 PhotoOnly Bot v2.5 с проверкой подписки перед каждой командой")
    
    # Запуск Flask
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("🌐 HTTP сервер запущен для UptimeRobot")

    # Telegram Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Команды для всех
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("auth", auth))
    application.add_handler(CommandHandler("logout", logout))

    # Команды для авторизованных
    application.add_handler(CommandHandler("pause", pause_bot))
    application.add_handler(CommandHandler("resume", resume_bot))
    application.add_handler(CommandHandler("status", status_bot))

    # Команды для админов
    application.add_handler(CommandHandler("list_auth", list_auth))
    application.add_handler(CommandHandler("deauth", deauth_user))
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("unban", unban_user))

    # Канал
    application.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & filters.Chat(chat_id=CHANNEL_ID),
        handle_channel_post
    ))

    print("✅ Запуск Telegram polling...")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
