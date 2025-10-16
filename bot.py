import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID', '-1001805328200'))
PAUSE_MODE = os.getenv('PAUSE_MODE', 'false').lower() == 'true'

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = "⏸️ ПАУЗА" if PAUSE_MODE else "▶️ АКТИВЕН"
    await update.message.reply_text(
        f"🤖 **PhotoOnly Bot v2.0**\n\n"
        f"📊 {status}\n"
        f"📢 Канал: `{CHANNEL_ID}`\n\n"
        f"⏸️ `/pause`\n"
        f"▶️ `/resume`\n"
        f"ℹ️ `/status`",
        parse_mode='Markdown'
    )

async def pause_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global PAUSE_MODE
    PAUSE_MODE = True
    logger.info("⏸️ ПАУЗА ВКЛЮЧЕНА!")
    await update.message.reply_text("⏸️ **ПАУЗА!** Удаление остановлено.")

async def resume_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global PAUSE_MODE
    PAUSE_MODE = False
    logger.info("▶️ БОТ АКТИВЕН!")
    await update.message.reply_text("▶️ **АКТИВЕН!** Удаляет НЕ-фото.")

async def status_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = "⏸️ ПАУЗА" if PAUSE_MODE else "▶️ АКТИВЕН"
    await update.message.reply_text(
        f"📊 **{status}**\n📢 Канал: `{CHANNEL_ID}`",
        parse_mode='Markdown'
    )

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global PAUSE_MODE
    if PAUSE_MODE or not update.channel_post:
        return
    
    post = update.channel_post
    if post.chat_id != CHANNEL_ID:
        return
    
    if not post.photo:
        try:
            await context.bot.delete_message(post.chat_id, post.message_id)
            logger.info(f"🗑️ УДАЛЕНО сообщение #{post.message_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка удаления: {e}")

def main():
    print("🚀 PhotoOnly Bot v2.0 - Совместим с Python 3.13")
    
    # Создаём Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("pause", pause_bot))
    application.add_handler(CommandHandler("resume", resume_bot))
    application.add_handler(CommandHandler("status", status_bot))
    
    # Канал
    application.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & filters.Chat(chat_id=CHANNEL_ID),
        handle_channel_post
    ))
    
    print("✅ Все обработчики добавлены")
    print("📱 Тест: /start в личке бота")
    
    # Запуск polling
    print("🚀 Запуск...")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()