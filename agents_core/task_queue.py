"""
File d'attente de tâches persistante (SQLite).
Commune à tous les agents — FIFO avec pause/reprise.
"""
import sqlite3
import threading
import logging
import time
from datetime import datetime, timezone
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class TaskStatus:
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class Task:
    def __init__(self, task_id: int, payload: str, correlation_id: str,
                 sender: str, reply_to: Optional[str], received_at: str):
        self.id = task_id
        self.payload = payload
        self.correlation_id = correlation_id
        self.sender = sender
        self.reply_to = reply_to
        self.received_at = received_at


class TaskQueue:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._paused = False
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    received_at     TEXT NOT NULL,
                    started_at      TEXT,
                    completed_at    TEXT,
                    payload         TEXT NOT NULL,
                    correlation_id  TEXT NOT NULL,
                    sender          TEXT NOT NULL,
                    reply_to        TEXT,
                    status          TEXT NOT NULL DEFAULT 'pending',
                    result          TEXT,
                    duration_s      REAL
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def enqueue(self, payload: str, correlation_id: str, sender: str,
                reply_to: Optional[str] = None) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO tasks (received_at, payload, correlation_id, sender, reply_to, status) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (now, payload, correlation_id, sender, reply_to, TaskStatus.PENDING)
            )
            task_id = cur.lastrowid
        logger.info(f"[TaskQueue] Tâche #{task_id} en file (sender={sender})")
        return task_id

    def _next_task(self) -> Optional[Task]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY id LIMIT 1",
                (TaskStatus.PENDING,)
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE tasks SET status = ?, started_at = ? WHERE id = ?",
                (TaskStatus.IN_PROGRESS, datetime.now(timezone.utc).isoformat(), row["id"])
            )
        return Task(
            task_id=row["id"],
            payload=row["payload"],
            correlation_id=row["correlation_id"],
            sender=row["sender"],
            reply_to=row["reply_to"],
            received_at=row["received_at"],
        )

    def complete(self, task_id: int, result: str, success: bool = True):
        now = datetime.now(timezone.utc).isoformat()
        status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
        with self._connect() as conn:
            row = conn.execute("SELECT started_at FROM tasks WHERE id = ?", (task_id,)).fetchone()
            duration = None
            if row and row["started_at"]:
                try:
                    started = datetime.fromisoformat(row["started_at"])
                    duration = (datetime.now(timezone.utc) - started).total_seconds()
                except Exception:
                    pass
            conn.execute(
                "UPDATE tasks SET status = ?, completed_at = ?, result = ?, duration_s = ? WHERE id = ?",
                (status, now, result[:4000], duration, task_id)
            )
        logger.info(f"[TaskQueue] Tâche #{task_id} {'terminée' if success else 'échouée'} en {duration:.1f}s" if duration else f"[TaskQueue] Tâche #{task_id} {status}")

    def pause(self):
        with self._lock:
            self._paused = True
        logger.info("[TaskQueue] En pause")

    def resume(self):
        with self._lock:
            self._paused = False
        logger.info("[TaskQueue] Reprise")

    @property
    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    def start_worker(self, handler: Callable[[Task], tuple[str, bool]]):
        """
        Lance le worker en arrière-plan.
        handler(task) → (result_str, success_bool)
        """
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            args=(handler,),
            daemon=True,
            name="task-queue-worker",
        )
        self._worker_thread.start()

    def stop_worker(self):
        self._running = False

    def _worker_loop(self, handler: Callable):
        while self._running:
            if self.is_paused:
                time.sleep(1)
                continue
            task = self._next_task()
            if task is None:
                time.sleep(0.5)
                continue
            try:
                result, success = handler(task)
            except Exception as e:
                result, success = str(e), False
            self.complete(task.id, result, success)

    def daily_stats(self) -> dict:
        today = datetime.now(timezone.utc).date().isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT status, duration_s FROM tasks WHERE DATE(received_at) = ?", (today,)
            ).fetchall()
        total = len(rows)
        completed = sum(1 for r in rows if r["status"] == TaskStatus.COMPLETED)
        failed = sum(1 for r in rows if r["status"] == TaskStatus.FAILED)
        durations = [r["duration_s"] for r in rows if r["duration_s"] is not None]
        avg_duration = sum(durations) / len(durations) if durations else 0
        return {
            "date": today,
            "total": total,
            "completed": completed,
            "failed": failed,
            "pending": total - completed - failed,
            "avg_duration_s": round(avg_duration, 2),
        }
