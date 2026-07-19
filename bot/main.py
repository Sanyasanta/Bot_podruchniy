import logging
import asyncio
from datetime import datetime

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest

from bot.config import load_config
from bot.db import Database
from bot.scheduler import ReminderScheduler
from bot.llm_providers import CloudflareAI
from bot.websearch import Tavily
from bot.intents import detect_intent
from bot.actions import (
    do_add_note,
    do_list_notes,
    do_find_notes,
    do_add_reminder,
    do_list_reminders,
    do_web,
    do_ask,
    do_open_app,
    do_make_dir,
    do_run_safe,
)


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.application.bot_data["db"]
    db.ensure_profile(update.effective_user.id, update.effective_user.first_name)
    text = (
        "🤖 Podruchniy готов к работе\n\n"
        "Привет! На связи Саша Булкин. Я собрал для тебя самые мощные и удобные нейросети для текста, изображений, видео и музыки.\n\n"
        "Что можно здесь:\n"
        "- ⚡️ Выбрать модель: от домашки до рабочих задач. 8 текстовых ИИ на выбор — ответ мгновенно.\n"
        "- 🎨 Изображения: сгенерировать картинку или отредактировать фото.\n"
        "- 🎬 Видео: сделать ролик, открытку или мем.\n"
        "- 🥁 Песни: создать джингл, саундтрек или частушки.\n"
        "- 🧠 О моделях: краткие описания, чтобы быстро подобрать нужную.\n\n"
        "Как пользоваться:\n"
        "- Пиши по‑человечески: ‘сохрани заметку купить молоко’, ‘напомни завтра в 9:30’, ‘найди новости про ИИ’, ‘объясни генераторы в Python’.\n"
        "- Или выбери раздел ниже.\n\n"
        "Подсказки команд: /ping, /note, /notes, /find, /remind, /reminders, /web, /ask, /tz, /profile"
    )
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡️ Текст", callback_data="nav:text"), InlineKeyboardButton(text="🎨 Изображения", callback_data="nav:image")],
            [InlineKeyboardButton(text="🎬 Видео", callback_data="nav:video"), InlineKeyboardButton(text="🥁 Песни", callback_data="nav:audio")],
            [InlineKeyboardButton(text="🧠 Модели", callback_data="nav:models")],
        ]
    )
    await update.effective_message.reply_text(text, reply_markup=kb)


from telegram import CallbackQuery
from telegram.ext import CallbackQueryHandler


async def nav_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data if query else ""
    mapping = {
        "nav:text": "Напиши текстовый запрос — отвечу сразу или подключу нужную модель.",
        "nav:image": "Генерация изображений в разработке. Можешь описать, что нужно — подготовлю промпт.",
        "nav:video": "Генерация видео в разработке. Опиши идею ролика — соберу промпт и план.",
        "nav:audio": "Генерация музыки в разработке. Напиши стиль и настроение — подготовлю промпт.",
        "nav:models": "Доступные режимы: текст, веб‑поиск, заметки, напоминания. Пиши запрос — подберу инструмент.",
    }
    msg = mapping.get(data, "Выбери раздел или просто задай вопрос текстом.")
    await query.answer()
    await query.message.reply_text(msg)


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("pong")


def parse_time(text: str):
    from datetime import datetime, timedelta
    text = text.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    lower = text.lower().replace("мин", "m").replace("ч", "h").replace("через ", "")
    try:
        if lower.endswith("h"):
            return datetime.now() + timedelta(hours=int(lower[:-1]))
        if lower.endswith("m"):
            return datetime.now() + timedelta(minutes=int(lower[:-1]))
    except Exception:
        return None
    return None


async def cmd_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.application.bot_data["db"]
    args = update.effective_message.text.split(maxsplit=1)
    if len(args) < 2:
        await update.effective_message.reply_text("Формат: /note <текст>")
        return
    text = args[1].strip()
    nid = db.add_note(update.effective_user.id, text)
    await update.effective_message.reply_text(f"Сохранил заметку #{nid}")


async def cmd_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.application.bot_data["db"]
    items = db.list_notes(update.effective_user.id)
    if not items:
        await update.effective_message.reply_text("У вас пока нет заметок")
        return
    text = "\n".join([f"#{n['id']}: {n['text']}" for n in items[:20]])
    await update.effective_message.reply_text(text)


async def cmd_find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.application.bot_data["db"]
    args = update.effective_message.text.split(maxsplit=1)
    if len(args) < 2:
        await update.effective_message.reply_text("Формат: /find <подстрока>")
        return
    query = args[1].strip()
    items = db.find_notes(update.effective_user.id, query)
    if not items:
        await update.effective_message.reply_text("Ничего не нашёл")
        return
    text = "\n".join([f"#{n['id']}: {n['text']}" for n in items[:20]])
    await update.effective_message.reply_text(text)


async def cmd_remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.application.bot_data["db"]
    scheduler: ReminderScheduler = context.application.bot_data["scheduler"]
    args = update.effective_message.text.split(maxsplit=1)
    if len(args) < 2:
        await update.effective_message.reply_text("Формат: /remind <текст> | <YYYY-MM-DD HH:MM или 'через 30м'>")
        return
    payload = args[1]
    if "|" in payload:
        left, right = [p.strip() for p in payload.split("|", 1)]
        t_left = parse_time(left)
        t_right = parse_time(right)
        if t_left and not t_right:
            text = right
            run_at = t_left
        elif t_right and not t_left:
            text = left
            run_at = t_right
        else:
            await update.effective_message.reply_text("Не понял время. Пример: /remind Позвонить | 2026-07-20 18:30 или /remind Позвонить | через 30м")
            return
    else:
        await update.effective_message.reply_text("Укажите время через вертикальную черту |, пример: /remind Текст | 2026-07-20 18:30")
        return

    rid = db.add_reminder(update.effective_user.id, text, run_at.isoformat(timespec="seconds"))
    scheduler.schedule(rid, update.effective_user.id, text, run_at)
    await update.effective_message.reply_text(f"Напоминание #{rid} на {run_at.strftime('%Y-%m-%d %H:%M')} создано")


async def cmd_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.application.bot_data["db"]
    items = db.list_pending_reminders(update.effective_user.id)
    if not items:
        await update.effective_message.reply_text("Нет активных напоминаний")
        return
    lines = [f"#{r['id']}: {r['text']} — {r['run_at']}" for r in items[:20]]
    await update.effective_message.reply_text("\n".join(lines))


async def cmd_web(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = context.application.bot_data["cfg"]
    api_key = cfg.tavily_api_key
    if not api_key:
        await update.effective_message.reply_text("Tavily API ключ не настроен")
        return
    args = update.effective_message.text.split(maxsplit=1)
    if len(args) < 2:
        await update.effective_message.reply_text("Формат: /web <запрос>")
        return
    query = args[1]
    tav = Tavily(api_key)
    try:
        results = await tav.search(query, max_results=5)
        if not results:
            await update.effective_message.reply_text("Ничего не найдено")
            return
        lines = []
        for r in results[:5]:
            title = r.get("title") or r.get("url")
            url = r.get("url")
            snippet = (r.get("content") or "").strip()
            if len(snippet) > 180:
                snippet = snippet[:180] + "…"
            lines.append(f"• {title}\n{url}\n{snippet}")
        await update.effective_message.reply_text("\n\n".join(lines))
    finally:
        await tav.close()


async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = context.application.bot_data["cfg"]
    if not (cfg.cf_account_id and cfg.cf_api_token):
        await update.effective_message.reply_text("Cloudflare Workers AI не настроен")
        return
    args = update.effective_message.text.split(maxsplit=1)
    if len(args) < 2:
        await update.effective_message.reply_text("Формат: /ask <вопрос>")
        return
    question = args[1]
    db: Database = context.application.bot_data["db"]
    history_rows = db.get_history(update.effective_user.id, limit=10)
    messages = [{"role": r["role"], "content": r["content"]} for r in history_rows]
    messages.append({"role": "user", "content": question})

    ai = CloudflareAI(cfg.cf_account_id, cfg.cf_api_token)
    try:
        answer = await ai.chat(messages)
    except Exception as e:
        await update.effective_message.reply_text(f"Ошибка LLM: {e}")
        return
    finally:
        await ai.close()

    db.add_message(update.effective_user.id, "user", question)
    db.add_message(update.effective_user.id, "assistant", answer)
    await update.effective_message.reply_text(answer)


async def cmd_tz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.application.bot_data["db"]
    args = update.effective_message.text.split(maxsplit=1)
    if len(args) < 2:
        await update.effective_message.reply_text("Формат: /tz <+HH:MM>")
        return
    tz = args[1].strip()
    db.set_tz(update.effective_user.id, tz)
    await update.effective_message.reply_text(f"Часовой пояс установлен: {tz}")


async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db: Database = context.application.bot_data["db"]
    db.ensure_profile(update.effective_user.id, update.effective_user.first_name)
    p = db.get_profile(update.effective_user.id)
    mem = db.get_memory_notes(update.effective_user.id, limit=3)
    name = p["name"] if p else ""
    tz = p["tz_offset"] if p else ""
    text = f"Профиль: {name}\nTZ: {tz or 'не задан'}\nПамять: {len(mem)} заметок"
    if mem:
        text += "\n\nПоследние заметки памяти:\n" + "\n".join(f"- {m}" for m in mem)
    await update.effective_message.reply_text(text)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Auto intent mode for plain text
    db: Database = context.application.bot_data["db"]
    cfg = context.application.bot_data["cfg"]
    db.ensure_profile(update.effective_user.id, update.effective_user.first_name)
    history_rows = db.get_history(update.effective_user.id, limit=10)
    history = [{"role": r["role"], "content": r["content"]} for r in history_rows]
    profile_row = db.get_profile(update.effective_user.id)
    profile = {"name": profile_row["name"], "tz_offset": profile_row["tz_offset"]} if profile_row else None
    memory = db.get_memory_notes(update.effective_user.id, limit=3)

    ai = CloudflareAI(cfg.cf_account_id, cfg.cf_api_token)
    try:
        intent = await detect_intent(ai, history, update.effective_message.text, profile, memory)
    except Exception as e:
        intent = {"intent": "ask_ai", "args": {"text": update.effective_message.text}}
    finally:
        await ai.close()

    if cfg.debug_intents:
        await update.effective_message.reply_text(f"intent={intent.get('intent')} args={intent.get('args')}")

    action = intent.get("intent")
    args = intent.get("args", {})

    # Route
    if action == "add_note":
        text = args.get("text") or update.effective_message.text
        reply = await do_add_note(db, update.effective_user.id, text)
    elif action == "list_notes":
        reply = await do_list_notes(db, update.effective_user.id)
    elif action == "find_notes":
        query = args.get("query") or update.effective_message.text
        reply = await do_find_notes(db, update.effective_user.id, query)
    elif action == "add_reminder":
        text = args.get("text") or update.effective_message.text
        time_str = args.get("time") or ""
        reply = await do_add_reminder(db, context.application.bot_data["scheduler"], update.effective_user.id, text, time_str)
    elif action == "list_reminders":
        reply = await do_list_reminders(db, update.effective_user.id)
    elif action == "web_search":
        if not cfg.tavily_api_key:
            reply = "Tavily API ключ не настроен"
        else:
            query = args.get("query") or update.effective_message.text
            reply = await do_web(cfg.tavily_api_key, query)
    elif action == "open_app":
        if not cfg.enable_open_apps:
            reply = "Открытие приложений недоступно в этом окружении"
        else:
            app_name = args.get("app") or ""
            reply = do_open_app(app_name, cfg.allowed_apps)
    elif action == "make_dir":
        path = args.get("path") or ""
        reply = do_make_dir(path, cfg.allowed_dirs)
    elif action == "run_safe":
        if not cfg.enable_shell:
            reply = "Команда недоступна в этом окружении"
        else:
            cmd = args.get("cmd") or ""
            reply = do_run_safe(cmd)
    elif action in ("smalltalk", "ask_ai"):
        # Use ask with memory
        ai2 = CloudflareAI(cfg.cf_account_id, cfg.cf_api_token)
        try:
            msgs = history + [{"role": "user", "content": update.effective_message.text}]
            reply = await do_ask(ai2, msgs, update.effective_user.id, db)
        except Exception as e:
            reply = f"Ошибка LLM: {e}"
        finally:
            await ai2.close()
    else:
        # Fallback
        ai2 = CloudflareAI(cfg.cf_account_id, cfg.cf_api_token)
        try:
            msgs = history + [{"role": "user", "content": update.effective_message.text}]
            reply = await do_ask(ai2, msgs, update.effective_user.id, db)
        except Exception as e:
            reply = f"Ошибка LLM: {e}"
        finally:
            await ai2.close()

    # Save interaction to history
    db.add_message(update.effective_user.id, "user", update.effective_message.text)
    db.add_message(update.effective_user.id, "assistant", reply)
    await update.effective_message.reply_text(reply)


async def cmd_shell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = context.application.bot_data["cfg"]
    if not cfg.enable_shell:
        await update.effective_message.reply_text("Команда недоступна в этом окружении")
        return
    allowed = {
        "open_chrome": "start chrome",
        "make_dir": "powershell -Command \"New-Item -ItemType Directory -Force -Path '{arg}'\"",
        "run": "{arg}",
    }
    args = update.effective_message.text.split(maxsplit=2)
    if len(args) < 2:
        await update.effective_message.reply_text("Формат: /shell <open_chrome|make_dir|run> [аргумент]")
        return
    action = args[1]
    param = args[2] if len(args) > 2 else ""
    if action not in allowed:
        await update.effective_message.reply_text("Недопустимая команда")
        return
    import subprocess
    try:
        cmd = allowed[action]
        if "{arg}" in cmd:
            cmd = cmd.format(arg=param)
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        out = result.stdout.strip() or result.stderr.strip() or "Ок"
        await update.effective_message.reply_text(out[:2000])
    except Exception as e:
        await update.effective_message.reply_text(f"Ошибка выполнения: {e}")


async def main_async():
    cfg = load_config()
    db = Database(cfg.db_path)

    request = HTTPXRequest(
        connection_pool_size=20,
        connect_timeout=30.0,
        read_timeout=60.0,
        write_timeout=60.0,
        pool_timeout=30.0,
    )
    app = Application.builder().token(cfg.bot_token).request(request).build()

    async def notify(user_id: int, text: str):
        await app.bot.send_message(user_id, f"⏰ Напоминание: {text}")

    sched = ReminderScheduler(db, notify)

    app.bot_data["db"] = db
    app.bot_data["scheduler"] = sched
    app.bot_data["cfg"] = cfg

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("note", cmd_note))
    app.add_handler(CommandHandler("notes", cmd_notes))
    app.add_handler(CommandHandler("find", cmd_find))
    app.add_handler(CommandHandler("remind", cmd_remind))
    app.add_handler(CommandHandler("reminders", cmd_reminders))
    app.add_handler(CommandHandler("web", cmd_web))
    app.add_handler(CommandHandler("ask", cmd_ask))
    app.add_handler(CommandHandler("shell", cmd_shell))
    app.add_handler(CommandHandler("tz", cmd_tz))
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CallbackQueryHandler(nav_callback, pattern=r"^nav:.*"))

    # Text handler for auto-intents (must be after command handlers)
    from telegram.ext import MessageHandler, filters
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    # Explicit async lifecycle for Python 3.14/Render
    await app.initialize()
    sched.start()
    sched.load_pending()
    await app.start()
    logging.info("Bot started. Polling...")
    try:
        await app.updater.start_polling()
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main_async())
