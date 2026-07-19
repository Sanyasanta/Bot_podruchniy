from __future__ import annotations

from datetime import datetime
from typing import Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger


class ReminderScheduler:
    def __init__(self, db, notify: Callable[[int, str], None]):
        self.db = db
        self.notify = notify
        self.scheduler = AsyncIOScheduler()

    def start(self):
        if not self.scheduler.running:
            self.scheduler.start()

    def load_pending(self):
        for r in self.db.list_pending_reminders():
            try:
                run_at = datetime.fromisoformat(r["run_at"])  # stored as ISO string
            except Exception:
                continue
            self.schedule(r["id"], r["user_id"], r["text"], run_at)

    def schedule(self, reminder_id: int, user_id: int, text: str, run_at: datetime):
        # if time in past, fire soon
        trigger = DateTrigger(run_date=run_at)

        async def job():
            await self.notify(user_id, text)
            self.db.mark_done(reminder_id)

        self.scheduler.add_job(job, trigger=trigger, id=f"rem_{reminder_id}", replace_existing=True)
