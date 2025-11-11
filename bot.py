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
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

if not BOT_TOKEN:
    print("ОШИБКА: BOT_TOKEN не найден!")
    exit(1)

print(f"Токен: {len(BOT_TOKEN)} символов")
print(f"Канал: {CHANNEL_ID}")
print(f"Админы: {ADMIN_CHAT_IDS}")
print(f"Главный: {SUPER_ADMIN_ID}")
print(f"Пересылка → {FORWARD_TO_IDS or '[]'}")

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

# === КОМАНДЫ — КАК БЫЛО РАНЬШЕ ===
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
            f"<b>PhotoOnly Bot v3.4</b>\n\n"
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
        if not await is_user_member(user_id, context):
            del AUTHORIZED_USERS[user_id]
            await update.message.reply_text("Вы отписались от канала. Авторизация отменена.")
            return
        await update.message.reply_text(
            f"<b>PhotoOnly Bot v3.4</b>\n\n"
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

# === Админские команды ===
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

# === КАНАЛ ===
async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.channel_post or update.channel_post.chat_id != CHANNEL_ID:
        return
    post = update.channel_post
    msg_id = post.message_id
    link = get_message_link(post.chat_id, msg_id)

    if not PAUSE_MODE and not post.photo and not post.video:
        try:
            await post.delete()
            logger.info(f"УДАЛЕНО: {link}")
        except Exception as e:
            logger.error(f"ОШИБКА удаления {link}: {e}")
        return

    logger.info(f"ОСТАВЛЕНО: {link} | Фото/Видео")

    if FORWARD_ENABLED and FORWARD_TO_IDS:
        for target_id in FORWARD_TO_IDS:
            try:
                await post.forward(target_id)
                logger.info(f"ПЕРЕСЛАНО {target_id}: {link}")
            except Exception as e:
                logger.error(f"ОШИБКА пересылки {target_id}: {e}")

# === АВТОУДАЛЕНИЕ ===
async def cleanup_task(app):
    while True:
        await asyncio.sleep(6 * 3600)
        if SUPER_ADMIN_ID:
            try:
                cutoff = datetime.now() - timedelta(hours=48)
                async for msg in app.bot.get_chat_history(chat_id=SUPER_ADMIN_ID, limit=1000):
                    if msg.forward_from_chat and msg.forward_from_chat.id == CHANNEL_ID and msg.date < cutoff:
                        try:
                            await msg.delete()
                            logger.info(f"Удалено старое #{msg.message_id}")
                        except:
                            pass
                        await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Ошибка очистки: {e}")

async def post_init(app):
    asyncio.create_task(cleanup_task(app))

# === ЗАПУСК ===
application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("auth", auth))
application.add_handler(CommandHandler("logout", logout))
application.add_handler(CommandHandler("pause", pause_bot))
application.add_handler(CommandHandler("resume", resume_bot))
application.add_handler(CommandHandler("status", status_bot))
application.add_handler(CommandHandler("forward", forward_control))
application.add_handler(CommandHandler("list_auth", list_auth))
application.add_handler(CommandHandler("deauth", deauth_user))
application.add_handler(CommandHandler("ban", ban_user))
application.add_handler(CommandHandler("unban", unban_user))
application.add_handler(MessageHandler(filters.ChatType.CHANNEL & filters.Chat(CHANNEL_ID), handle_channel_post))

webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{BOT_TOKEN}"
print(f"PhotoOnly Bot v3.4 | Webhook — 100% uptime")
print(f"Webhook: {webhook_url}")

application.run_webhook(
    listen="0.0.0.0",
    port=int(os.environ.get("PORT", 10000)),
    url_path=BOT_TOKEN,
    webhook_url=webhook_url
)
