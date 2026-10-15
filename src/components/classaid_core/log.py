# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Append-only activity log.

This module is the only writer of `classaid_events` and `classaid_snapshots`, and
it only ever INSERTs.  The ClassAid deletion handlers (personal data deletion) are
the sole exception.
"""

import hashlib
from collections.abc import Mapping
from typing import Any

import msgspec

from gened.db import get_db

from .api import ClassContext

# Every event type the application may write.  Adding a type means documenting it here.
EVENT_TYPES = frozenset({
    # student activity
    'task_opened',         # payload: status
    'code_edit',           # payload: reason (autosave | run | tests | question | complete); snapshot
    'run',                 # payload: job_id, result | error; snapshot
    'test_run',            # payload: job_id, result | error; snapshot
    'question',            # payload: message_id, question; snapshot
    'rating',              # payload: message_id, value, previous
    'task_completed',      # payload: score, result; snapshot
    # feedback generation (one per question; details in classaid_generations)
    'feedback_generated',  # payload: generation_id, question_id, message_id, effective_mode, mode_source, selected_type
    'feedback_suppressed',
    'feedback_failed',
    # instructor actions
    'mode_changed',        # payload: scope, affected_students, before/after (and cleared modes for class scope)
})


class UnknownEventTypeError(ValueError):
    pass


def _canonical(files: Mapping[str, str]) -> bytes:
    return msgspec.json.encode(dict(sorted(files.items())))


def snapshot(user_id: int, files: Mapping[str, str]) -> int:
    """ Store a code snapshot (deduplicated per user by content hash) and return its id. """
    data = _canonical(files)
    digest = hashlib.sha256(data).hexdigest()
    db = get_db()
    db.execute(
        "INSERT OR IGNORE INTO classaid_snapshots (user_id, sha256, files) VALUES (?, ?, ?)",
        [user_id, digest, data.decode()],
    )
    row = db.execute("SELECT id FROM classaid_snapshots WHERE user_id=? AND sha256=?", [user_id, digest]).fetchone()
    snapshot_id: int = row['id']
    return snapshot_id


def log_event(
    ctx: ClassContext,
    event_type: str,
    *,
    task_id: int | None = None,
    payload: Mapping[str, Any] | None = None,
    files: Mapping[str, str] | None = None,
) -> int:
    """ Append one event for the given user/class.  If `files` is given, a snapshot of
    them is stored and linked to the event.  Returns the event id.

    Does not commit: callers commit with their own changes, so an event and the
    state change it records are written atomically.
    """
    if event_type not in EVENT_TYPES:
        raise UnknownEventTypeError(event_type)
    db = get_db()
    snapshot_id = snapshot(ctx.user_id, files) if files is not None else None
    cur = db.execute(
        "INSERT INTO classaid_events (user_id, role_id, class_id, task_id, type, payload, snapshot_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [ctx.user_id, ctx.role_id, ctx.class_id, task_id, event_type, msgspec.json.encode(payload or {}).decode(), snapshot_id],
    )
    event_id = cur.lastrowid
    assert event_id is not None
    return event_id
