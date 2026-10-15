# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Per-student task progress: latest code, completion state, archived result. """

from typing import Any, Literal

import msgspec

from components.classaid_core.api import ApiError, ClassContext
from components.classaid_core.log import log_event
from gened.db import get_db

from .model import MAX_FILE_CHARS, TaskConfig

_NOW = "strftime('%Y-%m-%d %H:%M:%f', 'now')"


class Progress(msgspec.Struct, kw_only=True, frozen=True):
    id: int
    task_id: int
    status: Literal['in_progress', 'completed']
    files: dict[str, str]
    score: float | None
    final_result: dict[str, Any] | None
    started_at: str
    completed_at: str | None

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = msgspec.to_builtins(self)
        return data


def _from_row(row: Any) -> Progress:
    return Progress(
        id=row['id'],
        task_id=row['task_id'],
        status=row['status'],
        files=msgspec.json.decode(row['current_files']),
        score=row['score'],
        final_result=msgspec.json.decode(row['final_result']) if row['final_result'] else None,
        started_at=str(row['started_at']),
        completed_at=str(row['completed_at']) if row['completed_at'] else None,
    )


def get_progress(user_id: int, task_id: int) -> Progress | None:
    row = get_db().execute("SELECT * FROM classaid_task_progress WHERE user_id=? AND task_id=?", [user_id, task_id]).fetchone()
    return _from_row(row) if row else None


def open_task(ctx: ClassContext, task: TaskConfig) -> Progress:
    """ Get the user's progress on the task, starting it (with the starter code) on first open.
    Logs a 'task_opened' event.
    """
    assert task.row_id is not None
    db = get_db()
    starter = {f.name: f.content for f in task.spec.files}
    db.execute(
        "INSERT OR IGNORE INTO classaid_task_progress (user_id, role_id, class_id, task_id, current_files) VALUES (?, ?, ?, ?, ?)",
        [ctx.user_id, ctx.role_id, ctx.class_id, task.row_id, msgspec.json.encode(starter).decode()],
    )
    progress = get_progress(ctx.user_id, task.row_id)
    assert progress is not None
    log_event(ctx, 'task_opened', task_id=task.row_id, payload={'status': progress.status})
    db.commit()
    return progress


def validate_files(task: TaskConfig, files: object) -> dict[str, str]:
    """ Student code must consist of exactly the task's starter files (students edit, not add/remove, files). """
    if not isinstance(files, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in files.items()):
        raise ApiError(400, "'files' must be an object mapping file names to contents.")
    expected = {f.name for f in task.spec.files}
    if set(files) != expected:
        raise ApiError(400, f"Files must be exactly: {', '.join(sorted(expected))}.")
    if too_long := [name for name, content in files.items() if len(content) > MAX_FILE_CHARS]:
        raise ApiError(400, f"File too long (max {MAX_FILE_CHARS:,} characters): {', '.join(too_long)}.")
    return dict(files)


def require_in_progress(ctx: ClassContext, task: TaskConfig) -> Progress:
    assert task.row_id is not None
    progress = get_progress(ctx.user_id, task.row_id)
    if progress is None:
        raise ApiError(409, "Task has not been opened.")
    if progress.status != 'in_progress':
        raise ApiError(409, "Task is already completed.")
    return progress


def save_files(ctx: ClassContext, task: TaskConfig, files: dict[str, str], *, reason: str) -> Progress:
    """ Persist the student's latest code.  Logs a 'code_edit' event (with a snapshot) when
    the code changed.  `reason` records what triggered the save (autosave, run, tests, ...).
    """
    progress = require_in_progress(ctx, task)
    if files != progress.files:
        db = get_db()
        db.execute(
            f"UPDATE classaid_task_progress SET current_files=?, updated_at={_NOW} WHERE id=?",  # noqa: S608 -- constant SQL
            [msgspec.json.encode(files).decode(), progress.id],
        )
        log_event(ctx, 'code_edit', task_id=task.row_id, payload={'reason': reason}, files=files)
        db.commit()
        progress = msgspec.structs.replace(progress, files=files)
    return progress


def mark_completed(ctx: ClassContext, task_id: int, files: dict[str, str], result: dict[str, Any], score: float) -> None:
    """ Archive the final code and test result, record the score, and make the task
    read-only -- in one transaction, with a 'task_completed' event.
    No-op if the task is already completed.
    """
    db = get_db()
    cur = db.execute(
        f"""UPDATE classaid_task_progress
            SET status='completed', current_files=?, score=?, final_result=?, completed_at={_NOW}, updated_at={_NOW}
            WHERE user_id=? AND task_id=? AND status='in_progress'""",  # noqa: S608 -- constant SQL
        [msgspec.json.encode(files).decode(), score, msgspec.json.encode(result).decode(), ctx.user_id, task_id],
    )
    if cur.rowcount:
        log_event(ctx, 'task_completed', task_id=task_id, payload={'score': score, 'result': result}, files=files)
    db.commit()
