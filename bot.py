import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ✅ Загружаем .env (локально) или Environment Variables (Render)
load_dotenv()

# ✅ Читаем токен безопасно
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID', '-1001805328200'))
PAUSE_MODE = os.getenv('PAUSE_MODE', 'false').lower() == 'true'

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

# Проверка токена
if not BOT_TOKEN or len(BOT_TOKEN) < 30:
    print("❌ ОШИБКА: BOT_TOKEN не найден!")
    print("1. Проверьте .env файл (локально)")
    print("2. Или Environment Variables в Render")
    exit(1)

print(f"✅ Токен загружен: {len(BOT_TOKEN)} символов")
print(f"📢 Канал: {CHANNEL_ID}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = "⏸️ ПАУЗА" if PAUSE_MODE else "▶️ АКТИВЕН"
    await update.message.reply_text(
        f"🤖 **PhotoOnly Bot** (Secure)\n\n"
        f"{status}\n"
        f"📢 Канал: `{CHANNEL_ID}`\n\n"
        f"🔒 Токен защищён\n"
        f"⏸️ `/pause` - пауза\n"
        f"▶️ `/resume` - активен",
        parse_mode='Markdown'
    )

async def pause_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global PAUSE_MODE
    PAUSE_MODE = True
    logger.info("⏸️ ПАУЗА ВКЛЮЧЕНА!")
    await update.message.reply_text("⏸️ **ПАУЗА!** Бот НЕ удаляет ничего!")

async def resume_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global PAUSE_MODE
    PAUSE_MODE = False
    logger.info("▶️ АКТИВЕН!")
    await update.message.reply_text("▶️ **АКТИВЕН!** Удаляет не-фото!")

async def status_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = "⏸️ ПАУЗА (НЕ удаляет)" if PAUSE_MODE else "▶️ АКТИВЕН (удаляет)"
    await update.message.reply_text(
        f"📊 **СТАТУС** (Secure)\n\n"
        f"{status}\n"
        f"📢 Канал: `{CHANNEL_ID}`\n"
        f"🔒 Токен: защищён\n\n"
        f"⏸️ `/pause`\n"
        f"▶️ `/resume`",
        parse_mode='Markdown'
    )

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global PAUSE_MODE
    if PAUSE_MODE or not update.channel_post:
        if PAUSE_MODE:
            logger.info("⏸️ ПАУЗА - пропуск")
        return
    
    post = update.channel_post
    if post.chat_id != CHANNEL_ID:
        return
    
    is_photo = bool(post.photo)
    logger.info(f"📢 Пост #{post.message_id}: фото={is_photo}")
    
    if not is_photo:
        try:
            await context.bot.delete_message(post.chat_id, post.message_id)
            logger.info(f"🗑️ УДАЛЕНО {post.message_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка удаления: {e}")

def main():
    print("🚀 PhotoOnly Bot (SECURE)")
    print(f"⏸️ Начальный режим: {'ПАУЗА' if PAUSE_MODE else 'АКТИВЕН'}")
    
    # Создаём приложение
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .read_timeout(20)
        .write_timeout(20)
        .connect_timeout(20)
        .build()
    )
    
    # Обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("pause", pause_bot))
    application.add_handler(CommandHandler("resume", resume_bot))
    application.add_handler(CommandHandler("status", status_bot))
    
    application.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & filters.Chat(chat_id=CHANNEL_ID),
        handle_channel_post
    ))
    
    print("✅ Запуск polling...")
    print("📱 Тест: /start в личке бота")
    
    # Запуск
    application.run_polling(
        drop_pending_updates=True,
        poll_interval=1.0,
        timeout=20,
        bootstrap_retries=5
    )

if __name__ == '__main__':
    main()