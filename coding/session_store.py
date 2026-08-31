"""会话持久化：SQLite 存储 sessions / messages。

设计要点：
- sessions: 会话元数据（标题、创建/更新时间、消息数）
- messages: 每个会话的消息流（user / assistant / tool_call / tool_result / thinking）
- curator 通过 last_reviewed_msg_id 增量消费新消息
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    title        TEXT NOT NULL DEFAULT '新会话',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    message_count INTEGER NOT NULL DEFAULT 0,
    last_curator_msg_id INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL REFERENCES sessions(session_id),
    role        TEXT NOT NULL,
    content     TEXT NOT NULL DEFAULT '',
    meta        TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


class SessionStore:
    """线程安全的 SQLite 会话存储。"""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # ---------- sessions ----------

    def create_session(self, session_id: str | None = None, title: str | None = None) -> dict:
        session_id = session_id or uuid.uuid4().hex[:12]
        now = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO sessions (session_id, title, created_at, updated_at)"
                " VALUES (?, ?, ?, ?)",
                (session_id, title or "新会话", now, now),
            )
            self._conn.commit()
        return self.get_session(session_id)  # type: ignore[return-value]

    def get_session(self, session_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_sessions(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def update_title(self, session_id: str, title: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE session_id = ?",
                (title, _now(), session_id),
            )
            self._conn.commit()

    def delete_session(self, session_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            self._conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            self._conn.commit()

    def _touch(self, session_id: str) -> None:
        self._conn.execute(
            "UPDATE sessions SET updated_at = ?, message_count = message_count + 1"
            " WHERE session_id = ?",
            (_now(), session_id),
        )

    # ---------- messages ----------

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        meta: dict[str, Any] | None = None,
    ) -> int:
        """追加一条消息，返回消息自增 id。role ∈ {user, assistant, tool_call, tool_result, thinking}"""
        with self._lock:
            if not self._conn.execute(
                "SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone():
                self._conn.execute(
                    "INSERT INTO sessions (session_id, title, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?)",
                    (session_id, "新会话", _now(), _now()),
                )
            cur = self._conn.execute(
                "INSERT INTO messages (session_id, role, content, meta, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (session_id, role, content, json.dumps(meta or {}, ensure_ascii=False), _now()),
            )
            self._touch(session_id)
            self._conn.commit()
            return int(cur.lastrowid)

    def update_message_meta(self, session_id: str, message_id: int, meta: dict[str, Any]):
        """更新一条消息的 meta 字段（用于 plan 状态等实时更新）。"""
        with self._lock:
            self._conn.execute(
                "UPDATE messages SET meta = ? WHERE id = ? AND session_id = ?",
                (json.dumps(meta or {}, ensure_ascii=False), message_id, session_id),
            )
            self._touch(session_id)
            self._conn.commit()

    def list_messages(self, session_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY id", (session_id,)
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["meta"] = json.loads(d.get("meta") or "{}")
            except json.JSONDecodeError:
                d["meta"] = {}
            out.append(d)
        return out

    # ---------- curator 增量消费 ----------

    def fetch_new_messages(self, session_id: str) -> list[dict]:
        """返回 curator 尚未审阅过的消息。"""
        session = self.get_session(session_id)
        if not session:
            return []
        last_id = session["last_curator_msg_id"]
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE session_id = ? AND id > ? ORDER BY id",
                (session_id, last_id),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["meta"] = json.loads(d.get("meta") or "{}")
            except json.JSONDecodeError:
                d["meta"] = {}
            out.append(d)
        return out

    def mark_reviewed(self, session_id: str, up_to_msg_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET last_curator_msg_id = MAX(last_curator_msg_id, ?)"
                " WHERE session_id = ?",
                (up_to_msg_id, session_id),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
