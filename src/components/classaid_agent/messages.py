# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Chat messages in the student task workspace. """

from dataclasses import dataclass
from typing import Any, Literal

from gened.db import get_db

Role = Literal['student', 'assistant', 'notice']

_MESSAGE_FIELDS = "id, role, content, feedback_type, origin, notice_kind, reply_to, current_rating AS rating, created_at"


@dataclass(frozen=True)
class Thread:
    """ The chat a message belongs to: one student's progress on one task. """
    progress_id: int
    user_id: int
    class_id: int
    task_id: int


@dataclass(frozen=True)
class MessageInfo:
    feedback_type: str | None = None   # assistant messages: 'heuristic' | 'technical'
    origin: str | None = None          # assistant messages: 'user_triggered' | 'proactive'
    notice_kind: str | None = None     # notices: 'silent' | 'error'
    reply_to: int | None = None
    generation_id: int | None = None


def add_message(thread: Thread, role: Role, content: str, info: MessageInfo | None = None) -> int:
    """ Insert a message (caller commits). """
    info = info or MessageInfo()
    cur = get_db().execute("""
        INSERT INTO classaid_messages
            (progress_id, user_id, class_id, task_id, role, content, feedback_type, origin, notice_kind, reply_to, generation_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [thread.progress_id, thread.user_id, thread.class_id, thread.task_id, role, content,
          info.feedback_type, info.origin, info.notice_kind, info.reply_to, info.generation_id])
    message_id = cur.lastrowid
    assert message_id is not None
    return message_id


def list_messages(progress_id: int, *, after_id: int = 0) -> list[dict[str, Any]]:
    rows = get_db().execute(
        f"SELECT {_MESSAGE_FIELDS} FROM classaid_messages WHERE progress_id=? AND id>? ORDER BY id",  # noqa: S608 -- constant SQL
        [progress_id, after_id],
    ).fetchall()
    return [dict(row) for row in rows]


def conversation_before(progress_id: int, message_id: int) -> list[dict[str, str]]:
    """ Earlier questions and AI feedback in this task (notices excluded), as chat turns. """
    rows = get_db().execute(
        "SELECT role, content FROM classaid_messages WHERE progress_id=? AND id<? AND role IN ('student', 'assistant') ORDER BY id",
        [progress_id, message_id],
    ).fetchall()
    return [{'role': 'user' if row['role'] == 'student' else 'assistant', 'content': row['content']} for row in rows]
