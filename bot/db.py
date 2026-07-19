import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


class Database:
    def __init__(self, path: str):
        self.path = Path(path)
        # Ensure the parent directory exists
        if self.path.parent and not self.path.parent.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init(self):
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    run_at TIMESTAMP NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending','done','cancelled')) DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    # Notes
    def add_note(self, user_id: int, text: str) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO notes(user_id, text) VALUES (?, ?)", (user_id, text)
            )
            return cur.lastrowid

    def list_notes(self, user_id: int) -> List[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT id, text, created_at FROM notes WHERE user_id = ? ORDER BY id DESC",
                (user_id,),
            )
            return cur.fetchall()

    def find_notes(self, user_id: int, query: str) -> List[sqlite3.Row]:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT id, text, created_at FROM notes WHERE user_id = ? AND text LIKE ? ORDER BY id DESC",
                (user_id, f"%{query}%"),
            )
            return cur.fetchall()

    def delete_note(self, user_id: int, note_id: int) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id)
            )
            return cur.rowcount

    # Reminders
    def add_reminder(self, user_id: int, text: str, run_at_iso: str) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO reminders(user_id, text, run_at) VALUES (?, ?, ?)",
                (user_id, text, run_at_iso),
            )
            return cur.lastrowid

    def list_pending_reminders(self, user_id: Optional[int] = None) -> List[sqlite3.Row]:
        with self.connect() as conn:
            if user_id is None:
                cur = conn.execute(
                    "SELECT id, user_id, text, run_at FROM reminders WHERE status = 'pending' ORDER BY run_at ASC"
                )
            else:
                cur = conn.execute(
                    "SELECT id, user_id, text, run_at FROM reminders WHERE user_id = ? AND status = 'pending' ORDER BY run_at ASC",
                    (user_id,),
                )
            return cur.fetchall()

    def cancel_reminder(self, user_id: int, reminder_id: int) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "UPDATE reminders SET status = 'cancelled' WHERE id = ? AND user_id = ? AND status = 'pending'",
                (reminder_id, user_id),
            )
            return cur.rowcount

    def mark_done(self, reminder_id: int):
        with self.connect() as conn:
            conn.execute(
                "UPDATE reminders SET status = 'done' WHERE id = ?",
                (reminder_id,),
            )

    # Chat history
    def add_message(self, user_id: int, role: str, content: str):
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO chat_history(user_id, role, content) VALUES (?,?,?)",
                (user_id, role, content),
            )

    def get_history(self, user_id: int, limit: int = 10):
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT role, content FROM chat_history WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            )
            rows = cur.fetchall()
            rows.reverse()
            return rows
