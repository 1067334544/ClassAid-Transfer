# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Background jobs: code runs and feedback generation.

Write requests return immediately with a job id; the job runs in an in-process
thread pool and its result is stored in `classaid_jobs`, where clients pick it up
by polling.  Each pool has a configurable concurrency cap; jobs beyond the cap
wait in the pool's queue with status 'queued'.

Single-process deployments only: job execution state lives in this process.
"""

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Literal

import msgspec
from flask import Flask, current_app

from gened.db import get_db

JobPool = Literal['runner', 'llm']
JobFn = Callable[[int, dict[str, Any]], dict[str, Any]]  # (job_id, request) -> result

_POOL_CONFIG: dict[JobPool, tuple[str, int]] = {
    'runner': ('CLASSAID_RUN_CONCURRENCY', 8),
    'llm': ('CLASSAID_LLM_CONCURRENCY', 8),
}
_EXT_KEY = 'classaid_jobs'
_executor_lock = threading.Lock()
_NOW = "strftime('%Y-%m-%d %H:%M:%f', 'now')"


@dataclass(frozen=True)
class JobOwner:
    user_id: int
    class_id: int
    task_id: int | None = None


class _JobExecutor:
    def __init__(self, app: Flask):
        self._pools: dict[JobPool, ThreadPoolExecutor] = {
            pool: ThreadPoolExecutor(max_workers=int(app.config.get(var, default)), thread_name_prefix=f'classaid-{pool}')
            for pool, (var, default) in _POOL_CONFIG.items()
        }
        self._futures: dict[int, Future[None]] = {}
        self._lock = threading.Lock()

    def submit(self, app: Flask, pool: JobPool, job_id: int, fn: JobFn, request: dict[str, Any]) -> None:
        future = self._pools[pool].submit(_work, app, job_id, fn, request)
        with self._lock:
            self._futures[job_id] = future
        future.add_done_callback(lambda _f: self._forget(job_id))

    def _forget(self, job_id: int) -> None:
        with self._lock:
            self._futures.pop(job_id, None)

    def wait(self, job_id: int, timeout: float | None = None) -> None:
        """ Block until the job finishes (used by tests and synchronous callers). """
        with self._lock:
            future = self._futures.get(job_id)
        if future is not None:
            future.result(timeout=timeout)


def _executor(app: Flask) -> _JobExecutor:
    with _executor_lock:
        if _EXT_KEY not in app.extensions:
            app.extensions[_EXT_KEY] = _JobExecutor(app)
        executor: _JobExecutor = app.extensions[_EXT_KEY]
    return executor


def _work(app: Flask, job_id: int, fn: JobFn, request: dict[str, Any]) -> None:
    with app.app_context():
        db = get_db()
        db.execute(f"UPDATE classaid_jobs SET status='running', started_at={_NOW} WHERE id=?", [job_id])  # noqa: S608 -- constant SQL
        db.commit()
        try:
            result = fn(job_id, request)
        except Exception as e:
            app.logger.exception(f"ClassAid job {job_id} failed")
            db.execute(f"UPDATE classaid_jobs SET status='failed', error=?, finished_at={_NOW} WHERE id=?", [f"{type(e).__name__}: {e}", job_id])  # noqa: S608
        else:
            db.execute(f"UPDATE classaid_jobs SET status='done', result=?, finished_at={_NOW} WHERE id=?", [msgspec.json.encode(result).decode(), job_id])  # noqa: S608
        db.commit()


def submit_job(kind: str, pool: JobPool, fn: JobFn, request: dict[str, Any], owner: JobOwner) -> int:
    """ Record a job (status 'queued') and schedule `fn(job_id, request)` on the given pool.
    `fn` runs inside an app context in a worker thread; its return value (JSON-able)
    becomes the job result.  Returns the job id.
    """
    db = get_db()
    cur = db.execute(
        "INSERT INTO classaid_jobs (kind, user_id, class_id, task_id, request) VALUES (?, ?, ?, ?, ?)",
        [kind, owner.user_id, owner.class_id, owner.task_id, msgspec.json.encode(request).decode()],
    )
    job_id = cur.lastrowid
    assert job_id is not None
    db.commit()  # the worker reads the row from its own connection

    app = current_app._get_current_object()  # type: ignore[attr-defined]  # noqa: SLF001 -- standard Flask idiom
    _executor(app).submit(app, pool, job_id, fn, request)
    return job_id


def wait_for_job(job_id: int, timeout: float | None = None) -> None:
    app = current_app._get_current_object()  # type: ignore[attr-defined]  # noqa: SLF001
    _executor(app).wait(job_id, timeout)
