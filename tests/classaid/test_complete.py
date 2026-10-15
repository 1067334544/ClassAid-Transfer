# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Spec classaid/task-workspace: completing tasks, scoring, and read-only archives. """

import json
from collections.abc import Callable

import pytest
from flask import Flask

from gened.db import get_db
from tests.conftest import AppClient

from .helpers import COUNTER_JAVA, COUNTER_MAIN, available_task, counter_spec
from .test_runs import BUGGY, FIXED, finish


def complete(app: Flask, client: AppClient, task_id: int, files: dict[str, str]) -> dict[str, object]:
    response = client.post(f'/classaid/api/tasks/{task_id}/complete', json={'files': files})
    assert response.status_code == 202, response.text
    assert response.json is not None
    return finish(app, client, response.json['job_id'])


def progress_of(client: AppClient, task_id: int) -> dict[str, object]:
    response = client.get(f'/classaid/api/tasks/{task_id}')
    assert response.status_code == 200
    assert response.json is not None
    progress: dict[str, object] = response.json['progress']
    return progress


@pytest.fixture
def opened(login_as: Callable[..., AppClient]) -> tuple[AppClient, int]:
    task_id = available_task(login_as('instructor'))
    student = login_as('student1')
    student.get(f'/classaid/api/tasks/{task_id}')
    return student, task_id


@pytest.mark.usefixtures('jdk')
def test_complete_task(app: Flask, opened: tuple[AppClient, int]) -> None:
    """ Scenario: completing runs the instructor tests, shows a 0-5 score and per-test results,
    and marks the task completed. """
    student, task_id = opened
    job = complete(app, student, task_id, FIXED)
    assert job['status'] == 'done'
    assert job['result']['score'] == 5.0  # type: ignore[index]

    progress = progress_of(student, task_id)
    assert progress['status'] == 'completed'
    assert progress['score'] == 5.0
    assert progress['completed_at']
    assert progress['files'] == FIXED
    final = progress['final_result']
    assert isinstance(final, dict)
    assert {t['id']: t['status'] for t in final['tests']} == {'CounterTest#startsAtZero': 'passed', 'CounterTest#incrementsByOne': 'passed'}

    with app.app_context():
        events = get_db().execute("SELECT payload FROM classaid_events WHERE type='task_completed'").fetchall()
    assert len(events) == 1
    assert json.loads(events[0]['payload'])['score'] == 5.0


@pytest.mark.usefixtures('jdk')
def test_complete_partial_score(app: Flask, opened: tuple[AppClient, int]) -> None:
    student, task_id = opened
    complete(app, student, task_id, BUGGY)
    assert progress_of(student, task_id)['score'] == 1.3


@pytest.mark.usefixtures('jdk')
def test_complete_with_compile_error(app: Flask, opened: tuple[AppClient, int]) -> None:
    """ Scenario: completing code that does not compile scores 0 and keeps the compile error. """
    student, task_id = opened
    broken = {'Counter.java': COUNTER_JAVA.replace('return count;', 'return count'), 'Main.java': COUNTER_MAIN}
    complete(app, student, task_id, broken)
    progress = progress_of(student, task_id)
    assert progress['status'] == 'completed'
    assert progress['score'] == 0.0
    final = progress['final_result']
    assert isinstance(final, dict)
    assert final['status'] == 'compile_error'
    assert final['compile']['diagnostics'][0]['file'] == 'Counter.java'


@pytest.mark.usefixtures('jdk')
def test_completed_task_is_read_only(app: Flask, opened: tuple[AppClient, int]) -> None:
    """ Scenario: a completed task shows its final code, score, and chat read-only;
    editing, running, testing, and completing again are refused. """
    student, task_id = opened
    complete(app, student, task_id, FIXED)
    base = f'/classaid/api/tasks/{task_id}'
    assert student.put(f'{base}/code', json={'files': BUGGY}).status_code == 409
    assert student.post(f'{base}/run', json={'files': FIXED}).status_code == 409
    assert student.post(f'{base}/test', json={'files': FIXED}).status_code == 409
    assert student.post(f'{base}/complete', json={'files': FIXED}).status_code == 409
    assert progress_of(student, task_id)['files'] == FIXED


@pytest.mark.usefixtures('jdk')
def test_next_task_starts_fresh(app: Flask, login_as: Callable[..., AppClient]) -> None:
    """ Scenario: after completing task 1, task 2 opens with its own starter code. """
    instructor = login_as('instructor')
    task1 = available_task(instructor, 'Task 1')
    starter2 = {'Counter.java': '// task 2 starter\n' + COUNTER_JAVA, 'Main.java': COUNTER_MAIN}
    task2 = available_task(instructor, 'Task 2', counter_spec(files=[{'name': n, 'content': c} for n, c in starter2.items()]))
    student = login_as('student1')
    student.get(f'/classaid/api/tasks/{task1}')
    complete(app, student, task1, FIXED)

    progress = progress_of(student, task2)
    assert progress['status'] == 'in_progress'
    assert progress['files'] == starter2


def test_runner_failure_does_not_complete(app: Flask, opened: tuple[AppClient, int]) -> None:
    app.config['CLASSAID_JAVA_HOME'] = '/nonexistent-jdk'
    app.extensions.pop('classaid_runner', None)
    student, task_id = opened
    job = complete(app, student, task_id, FIXED)
    assert job['status'] == 'failed'
    assert progress_of(student, task_id)['status'] == 'in_progress'

