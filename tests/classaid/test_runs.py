# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Spec classaid/code-execution via the workspace API: Run / Run Tests as background jobs. """

import json
from collections.abc import Callable
from typing import Any

import pytest
from flask import Flask

from components.classaid_core import wait_for_job
from gened.db import get_db
from tests.conftest import AppClient

from .helpers import COUNTER_FIXED, COUNTER_JAVA, COUNTER_MAIN, available_task

BUGGY = {'Counter.java': COUNTER_JAVA, 'Main.java': COUNTER_MAIN}
FIXED = {'Counter.java': COUNTER_FIXED, 'Main.java': COUNTER_MAIN}


def start(client: AppClient, task_id: int, kind: str, files: dict[str, str]) -> int:
    response = client.post(f'/classaid/api/tasks/{task_id}/{kind}', json={'files': files})
    assert response.status_code == 202, response.text
    assert response.json is not None
    job_id: int = response.json['job_id']
    return job_id


def finish(app: Flask, client: AppClient, job_id: int) -> dict[str, Any]:
    with app.app_context():
        wait_for_job(job_id, timeout=60)
    response = client.get(f'/classaid/api/jobs/{job_id}')
    assert response.status_code == 200
    assert response.json is not None
    data: dict[str, Any] = response.json
    return data


@pytest.fixture
def opened(login_as: Callable[..., AppClient]) -> tuple[AppClient, int]:
    task_id = available_task(login_as('instructor'))
    student = login_as('student1')
    student.get(f'/classaid/api/tasks/{task_id}')
    return student, task_id


@pytest.mark.usefixtures('jdk')
def test_run_program(app: Flask, opened: tuple[AppClient, int]) -> None:
    student, task_id = opened
    job = finish(app, student, start(student, task_id, 'run', BUGGY))
    assert job['status'] == 'done'
    assert job['kind'] == 'run'
    result = job['result']
    assert result['status'] == 'ok'
    assert result['stdout'] == '2\n'
    assert result['tests'] is None


@pytest.mark.usefixtures('jdk')
def test_run_tests_scored(app: Flask, opened: tuple[AppClient, int]) -> None:
    """ Weights: startsAtZero 1 (passes), incrementsByOne 3 (fails) -> 5 * 1/4 = 1.25 -> 1.3 """
    student, task_id = opened
    result = finish(app, student, start(student, task_id, 'test', BUGGY))['result']
    assert result['status'] == 'ok'
    by_id = {t['id']: t for t in result['tests']}
    assert by_id['CounterTest#startsAtZero']['status'] == 'passed'
    assert by_id['CounterTest#incrementsByOne']['status'] == 'failed'
    assert by_id['CounterTest#incrementsByOne']['message'] == 'expected: <1> but was: <2>'
    assert result['score'] == 1.3

    fixed = finish(app, student, start(student, task_id, 'test', FIXED))['result']
    assert fixed['score'] == 5.0


@pytest.mark.usefixtures('jdk')
def test_test_results_do_not_leak_test_source(app: Flask, opened: tuple[AppClient, int]) -> None:
    """ Scenario: test results show names, status, failure messages -- never the test source,
    and in tests mode never the program's output. """
    student, task_id = opened
    chatty = {'Counter.java': COUNTER_JAVA.replace('public int get() {', 'public int get() { System.out.println("PRINTED-IN-TESTS");'), 'Main.java': COUNTER_MAIN}
    job_id = start(student, task_id, 'test', chatty)
    response_text = student.get(f'/classaid/api/jobs/{job_id}').get_data(as_text=True)
    job = finish(app, student, job_id)
    full_text = json.dumps(job) + response_text
    assert 'HIDDEN-TEST-SOURCE' not in full_text
    assert 'assertEquals' not in full_text
    assert 'PRINTED-IN-TESTS' not in full_text
    assert job['result']['stdout'] == ''
    assert {t['name'] for t in job['result']['tests']} == {'startsAtZero()', 'incrementsByOne()'}
    # the stored job request holds only the student's code, not the tests
    with app.app_context():
        request = get_db().execute("SELECT request FROM classaid_jobs WHERE id=?", [job_id]).fetchone()['request']
    assert 'HIDDEN-TEST-SOURCE' not in request


@pytest.mark.usefixtures('jdk')
def test_runs_are_logged(app: Flask, opened: tuple[AppClient, int]) -> None:
    student, task_id = opened
    run_id = start(student, task_id, 'run', FIXED)
    finish(app, student, run_id)
    test_id = start(student, task_id, 'test', FIXED)
    finish(app, student, test_id)
    with app.app_context():
        rows = get_db().execute("""
            SELECT e.type, e.payload, s.files FROM classaid_events e
            LEFT JOIN classaid_snapshots s ON s.id = e.snapshot_id
            WHERE e.type IN ('code_edit', 'run', 'test_run') ORDER BY e.id
        """).fetchall()
    assert [r['type'] for r in rows] == ['code_edit', 'run', 'test_run']  # code saved once (unchanged before tests)
    assert json.loads(rows[0]['payload']) == {'reason': 'run'}
    run_payload = json.loads(rows[1]['payload'])
    assert run_payload['job_id'] == run_id
    assert run_payload['result']['stdout'] == '1\n'
    test_payload = json.loads(rows[2]['payload'])
    assert test_payload['job_id'] == test_id
    assert test_payload['result']['score'] == 5.0
    assert all(json.loads(r['files']) == FIXED for r in rows)


def test_runner_unavailable(app: Flask, opened: tuple[AppClient, int]) -> None:
    """ Without a working runner the job fails and students get a generic message. """
    app.config['CLASSAID_JAVA_HOME'] = '/nonexistent-jdk'
    app.extensions.pop('classaid_runner', None)
    student, task_id = opened
    job = finish(app, student, start(student, task_id, 'run', BUGGY))
    assert job['status'] == 'failed'
    assert job['error'] == "The code runner is unavailable right now.  Please tell your instructor."
    assert 'nonexistent' not in json.dumps(job)


def test_jobs_are_private(app: Flask, login_as: Callable[..., AppClient], opened: tuple[AppClient, int]) -> None:
    app.config['CLASSAID_JAVA_HOME'] = '/nonexistent-jdk'
    app.extensions.pop('classaid_runner', None)
    student, task_id = opened
    job_id = start(student, task_id, 'run', BUGGY)
    finish(app, student, job_id)
    assert login_as('student2').get(f'/classaid/api/jobs/{job_id}').status_code == 404


def test_run_requires_open_task(login_as: Callable[..., AppClient]) -> None:
    task_id = available_task(login_as('instructor'))
    student = login_as('student1')
    response = student.post(f'/classaid/api/tasks/{task_id}/run', json={'files': BUGGY})
    assert response.status_code == 409
