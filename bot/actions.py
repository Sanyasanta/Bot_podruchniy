import os
import subprocess
from typing import List, Dict, Any

from bot.db import Database
from bot.scheduler import ReminderScheduler
from bot.websearch import Tavily
from bot.llm_providers import CloudflareAI


def is_safe_path(path: str, allowed_dirs: List[str] | None) -> bool:
    if not allowed_dirs:
        return False
    norm = os.path.abspath(path)
    system_roots = [
        os.path.abspath("C:/Windows"), os.path.abspath("C:/Program Files"), os.path.abspath("C:/Program Files (x86)"),
        "/bin", "/etc", "/usr", "/lib", "/sbin", "/var"
    ]
    for s in system_roots:
        if norm.lower().startswith(os.path.abspath(s).lower()):
            return False
    for base in allowed_dirs:
        try:
            if norm.lower().startswith(os.path.abspath(base).lower()):
                return True
        except Exception:
            continue
    return False


async def do_add_note(db: Database, user_id: int, text: str) -> str:
    nid = db.add_note(user_id, text)
    return f"Сохранил заметку #{nid}"


async def do_list_notes(db: Database, user_id: int) -> str:
    items = db.list_notes(user_id)
    if not items:
        return "У вас пока нет заметок"
    return "\n".join([f"#{n['id']}: {n['text']}" for n in items[:20]])


async def do_find_notes(db: Database, user_id: int, query: str) -> str:
    items = db.find_notes(user_id, query)
    if not items:
        return "Ничего не нашёл"
    return "\n".join([f"#{n['id']}: {n['text']}" for n in items[:20]])


async def do_add_reminder(db: Database, sched: ReminderScheduler, user_id: int, text: str, time_str: str) -> str:
    from bot.main import parse_time
    t = parse_time(time_str)
    if not t:
        return "Не понял время. Пример: '2026-07-20 18:30' или 'через 30м'"
    rid = db.add_reminder(user_id, text, t.isoformat(timespec="seconds"))
    sched.schedule(rid, user_id, text, t)
    return f"Напоминание #{rid} на {t.strftime('%Y-%m-%d %H:%M')} создано"


async def do_list_reminders(db: Database, user_id: int) -> str:
    items = db.list_pending_reminders(user_id)
    if not items:
        return "Нет активных напоминаний"
    return "\n".join([f"#{r['id']}: {r['text']} — {r['run_at']}" for r in items[:20]])


async def do_web(api_key: str, query: str) -> str:
    tav = Tavily(api_key)
    try:
        results = await tav.search(query, max_results=5)
        if not results:
            return "Ничего не найдено"
        lines = []
        for r in results[:5]:
            title = r.get("title") or r.get("url")
            url = r.get("url")
            snippet = (r.get("content") or "").strip()
            if len(snippet) > 180:
                snippet = snippet[:180] + "…"
            lines.append(f"• {title}\n{url}\n{snippet}")
        return "\n\n".join(lines)
    finally:
        await tav.close()


async def do_ask(ai: CloudflareAI, messages: List[Dict[str, str]], user_id: int, db: Database) -> str:
    answer = await ai.chat(messages)
    # memory hook could be added here (e.g., summarization every N messages)
    return answer


def do_open_app(app: str, allowed_apps: List[str] | None) -> str:
    if not allowed_apps or app.lower() not in [a.lower() for a in allowed_apps]:
        return "Приложение не разрешено или не поддерживается"
    # Basic aliases for Windows
    aliases = {
        "chrome": "start chrome",
        "code": "start code",
        "notepad++": "start notepad++",
        "notepad": "start notepad",
    }
    cmd = aliases.get(app.lower())
    if not cmd:
        return "Не знаю как открыть это приложение"
    try:
        subprocess.Popen(cmd, shell=True)
        return "Открываю"
    except Exception as e:
        return f"Не удалось открыть: {e}"


def do_make_dir(path: str, allowed_dirs: List[str] | None) -> str:
    if not path:
        return "Укажите путь"
    if not is_safe_path(path, allowed_dirs):
        return "Путь не разрешён"
    try:
        os.makedirs(path, exist_ok=True)
        return "Папка создана"
    except Exception as e:
        return f"Ошибка: {e}"


def do_run_safe(cmd: str) -> str:
    if not cmd:
        return "Укажите команду"
    whitelist = ["whoami", "ver", "dir", "ls", "python --version"]
    if all(not cmd.lower().startswith(w) for w in whitelist):
        return "Команда не разрешена"
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        out = result.stdout.strip() or result.stderr.strip() or "Ок"
        return out[:2000]
    except Exception as e:
        return f"Ошибка: {e}"
