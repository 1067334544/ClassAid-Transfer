# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

import threading
import time
from pathlib import Path
from typing import Any

import pytest
from flask import Flask

import classaid
from components.classaid_core import JobOwner, submit_job, wait_for_job
from gened.db import get_db
from gened.db_admin import init_db

from .conftest import _test_data_sql

OWNER = JobOwner(user_id=102, class_id=1)


@pytest.fixture
def app_cap2(tmp_path: Path) -> Flask:
    """ A ClassAid app whose runner pool allows only 2 concurrent jobs. """
    app = classaid.create_app(
        test_config={'TESTING': True, 'DATABASE': str(tmp_path / 'jobs.db'), 'CLASSAID_RUN_CONCURRENCY': 2},
        instance_path=tmp_path,
    )
    with app.app_context():
        init_db()
        get_db().executescript(_test_data_sql)
    return app


def _statuses(app: Flask) -> list[str]:
    with app.app_context():
        return [r['status'] for r in get_db().execute("SELECT status FROM classaid_jobs ORDER BY id")]


def test_jobs_queue_beyond_concurrency_cap(app_cap2: Flask) -> None:
    """ Concurrency cap 2, 4 jobs submitted: 2 run, 2 wait as 'queued', and all 4 finish. """
    release = threading.Event()

    def blocking(_job_id: int, request: dict[str, Any]) -> dict[str, Any]:
        release.wait(timeout=10)
        return {'echo': request['n']}

    with app_cap2.app_context():
        job_ids = [submit_job('test', 'runner', blocking, {'n': n}, OWNER) for n in range(4)]

    deadline = time.monotonic() + 5
    while _statuses(app_cap2).count('running') < 2 and time.monotonic() < deadline:
        time.sleep(0.02)
    statuses = _statuses(app_cap2)
    assert statuses.count('running') == 2
    assert statuses.count('queued') == 2

    release.set()
    with app_cap2.app_context():
        for job_id in job_ids:
            wait_for_job(job_id, timeout=10)
        rows = get_db().execute("SELECT status, result, started_at, finished_at FROM classaid_jobs ORDER BY id").fetchall()
    assert [r['status'] for r in rows] == ['done'] * 4
    assert [r['result'] for r in rows] == [f'{{"echo":{n}}}' for n in range(4)]
    assert all(r['started_at'] and r['finished_at'] for r in rows)


def test_failed_job_records_error(app: Flask) -> None:
    def broken(_job_id: int, _request: dict[str, Any]) -> dict[str, Any]:
        msg = "boom"
        raise RuntimeError(msg)

    with app.app_context():
        job_id = submit_job('test', 'llm', broken, {}, OWNER)
        wait_for_job(job_id, timeout=10)
        row = get_db().execute("SELECT status, error, result FROM classaid_jobs WHERE id=?", [job_id]).fetchone()
    assert row['status'] == 'failed'
    assert row['error'] == 'RuntimeError: boom'
    assert row['result'] is None


def test_job_runs_with_app_context(app: Flask) -> None:
    """ Job functions can use the database (they run inside an app context in the worker). """
    def count_users(_job_id: int, _request: dict[str, Any]) -> dict[str, Any]:
        return {'users': get_db().execute("SELECT COUNT(*) FROM users").fetchone()[0]}

    with app.app_context():
        expected = get_db().execute("SELECT COUNT(*) FROM users").fetchone()[0]
        job_id = submit_job('test', 'runner', count_users, {}, OWNER)
        wait_for_job(job_id, timeout=10)
        row = get_db().execute("SELECT status, result FROM classaid_jobs WHERE id=?", [job_id]).fetchone()
    assert row['status'] == 'done'
    assert row['result'] == f'{{"users":{expected}}}'
