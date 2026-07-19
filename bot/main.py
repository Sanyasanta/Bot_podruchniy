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


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "Привет! Я личный бот заметок и напоминаний.\n\n"
        "Команды:\n"
        "/ping — проверить, что я жив\n"
        "/note <текст> — добавить заметку\n"
        "/notes — показать заметки\n"
        "/find <подстрока> — поиск по заметкам\n"
        "/remind <текст> | <YYYY-MM-DD HH:MM> — создать напоминание\n"
        "/reminders — активные напоминания"
    )


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
