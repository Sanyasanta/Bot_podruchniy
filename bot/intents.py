import json
from typing import Any, Dict, List

from bot.llm_providers import CloudflareAI


INTENT_SCHEMA = {
    "intent": "ask_ai|web_search|add_note|list_notes|find_notes|add_reminder|list_reminders|open_app|make_dir|run_safe|smalltalk",
    "args": {
        "text": "string?",
        "query": "string?",
        "time": "string?",
        "path": "string?",
        "app": "string?",
        "cmd": "string?",
    },
}


def build_prompt(history: List[Dict[str, str]], text: str, profile: Dict[str, Any] | None, memory: List[str]):
    profile_part = f"Name: {profile.get('name')}, TZ: {profile.get('tz_offset')}" if profile else ""
    memory_part = "\n".join([f"- {m}" for m in memory]) if memory else ""
    hist_lines = []
    for m in history[-6:]:
        role = m.get("role")
        content = m.get("content")
        hist_lines.append(f"{role}: {content}")
    hist_block = "\n".join(hist_lines)
    prompt = f"""
Ты — маршрутизатор задач. Определи намерение пользователя и верни ТОЛЬКО JSON без комментариев.
Поддерживаемые intents: {INTENT_SCHEMA['intent']}.
Параметры в args.
Если вопрос общий — intent=ask_ai.
Если просит найти в интернете — intent=web_search с args.query.
Если просит сохранить заметку — add_note с args.text.
Если просит показать заметки — list_notes.
Если просит найти заметку — find_notes с args.query.
Если просит напомнить — add_reminder с args.text и args.time (например: "2026-07-20 18:30" или "через 30м").
Если просит показать напоминания — list_reminders.
Если просит открыть приложение — open_app с args.app (например: chrome, code).
Если просит создать папку — make_dir с args.path.
Если просит выполнить команду — run_safe с args.cmd (только безопасные команды).
Если это приветствие/болтовня — smalltalk.

Контекст профиля: {profile_part}
Память важного: \n{memory_part}
История (последние сообщения):\n{hist_block}
Текущее сообщение пользователя: "{text}"
Верни JSON строго формата: {{"intent": str, "args": {{...}} }}
Без пояснений.
"""
    return prompt


async def detect_intent(ai: CloudflareAI, history: List[Dict[str, str]], text: str, profile: Dict[str, Any] | None, memory: List[str]) -> Dict[str, Any]:
    prompt = build_prompt(history, text, profile, memory)
    messages = [
        {"role": "system", "content": "Ты возвращаешь только JSON."},
        {"role": "user", "content": prompt},
    ]
    out = await ai.chat(messages)
    # Ensure valid JSON
    try:
        # Extract the first JSON object if model emits extra text
        start = out.find("{")
        end = out.rfind("}")
        if start != -1 and end != -1:
            out = out[start : end + 1]
        data = json.loads(out)
        if not isinstance(data, dict) or "intent" not in data:
            raise ValueError("invalid shape")
        if "args" not in data or not isinstance(data["args"], dict):
            data["args"] = {}
        return data
    except Exception:
        return {"intent": "ask_ai", "args": {"text": text}}
