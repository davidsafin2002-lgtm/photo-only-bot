import os
import logging
import threading
import time
from dotenv import load_dotenv
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Загрузка переменных окружения
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID', '-1001805328200'))
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'TAVDIN')  # Пароль по умолчанию
ADMIN_CHAT_IDS = [int(x) for x in os.getenv('ADMIN_CHAT_IDS', '').split(',') if x]  # Список ID админов

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
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

# Хранилище авторизованных пользователей (в памяти)
AUTHORIZED_USERS = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in ADMIN_CHAT_IDS or user_id in AUTHORIZED_USERS:
        status = "⏸️ ПАУЗА" if 'PAUSE_MODE' in globals() and PAUSE_MODE else "▶️ АКТИВЕН"
        await update.message.reply_text(
            f"🤖 **PhotoOnly Bot v2.1**\n\n"
            f"📊 {status}\n"
            f"📢 Канал: `{CHANNEL_ID}`\n\n"
            f"🔐 Вы авторизованы!\n"
            f"👤 Команды:\n"
            f"⏸️ `/pause` - Приостановить\n"
            f"▶️ `/resume` - Возобновить\n"
            f"ℹ️ `/status` - Статус\n"
            f"🔓 `/logout` - Выйти",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("🔐 Введите пароль для авторизации:\n`/auth <ваш_пароль>`")

async def auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if context.args:
        password = context.args[0]
        if password == ADMIN_PASSWORD:
            AUTHORIZED_USERS[user_id] = True
            await update.message.reply_text("✅ Авторизация успешна! Используйте команды.")
        else:
            await update.message.reply_text("❌ Неверный пароль!")
    else:
        await update.message.reply_text("🔐 Укажите пароль: `/auth TAVDIN`")

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in AUTHORIZED_USERS:
        del AUTHORIZED_USERS[user_id]
        await update.message.reply_text("🔓 Вы вышли из аккаунта.")
    else:
        await update.message.reply_text("🔐 Вы не авторизованы.")

async def pause_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in ADMIN_CHAT_IDS or user_id in AUTHORIZED_USERS:
        global PAUSE_MODE
        PAUSE_MODE = True
        logger.info(f"⏸️ ПАУЗА от {user_id}")
        await update.message.reply_text("⏸️ **ПАУЗА!** Удаление остановлено.")
    else:
        await update.message.reply_text("🔐 Только для авторизованных!")

async def resume_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in ADMIN_CHAT_IDS or user_id in AUTHORIZED_USERS:
        global PAUSE_MODE
        PAUSE_MODE = False
        logger.info(f"▶️ АКТИВЕН от {user_id}")
        await update.message.reply_text("▶️ **АКТИВЕН!** Удаляет НЕ-фото.")
    else:
        await update.message.reply_text("🔐 Только для авторизованных!")

async def status_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in ADMIN_CHAT_IDS or user_id in AUTHORIZED_USERS:
        status = "⏸️ ПАУЗА" if 'PAUSE_MODE' in globals() and PAUSE_MODE else "▶️ АКТИВЕН"
        await update.message.reply_text(
            f"📊 **{status}**\n"
            f"📢 Канал: `{CHANNEL_ID}`\n"
            f"👤 Админы: {len(ADMIN_CHAT_IDS)}",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("🔐 Только для авторизованных!")

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.channel_post:
        return

    post = update.channel_post
    if post.chat_id != CHANNEL_ID:
        return

    user_id = post.from_user.id if post.from_user else None
    # Белый список: админы могут отправлять всё
    if user_id in ADMIN_CHAT_IDS:
        logger.info(f"👤 Админ {user_id} отправил сообщение #{post.message_id}")
        return

    if not PAUSE_MODE and not post.photo:
        try:
            await context.bot.delete_message(post.chat_id, post.message_id)
            logger.info(f"🗑️ УДАЛЕНО #{post.message_id}")
        except Exception as e:
            logger.error(f"❌ {e}")

def main():
    print("🚀 PhotoOnly Bot v2.1 с авторизацией и админами")
    
    # Запуск Flask
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("🌐 HTTP сервер запущен для UptimeRobot")

    # Telegram Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("auth", auth))
    application.add_handler(CommandHandler("logout", logout))
    application.add_handler(CommandHandler("pause", pause_bot))
    application.add_handler(CommandHandler("resume", resume_bot))
    application.add_handler(CommandHandler("status", status_bot))

    # Канал
    application.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & filters.Chat(chat_id=CHANNEL_ID),
        handle_channel_post
    ))

    print("✅ Запуск Telegram polling...")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
