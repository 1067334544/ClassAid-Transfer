# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" The polled /api/state endpoint: effective mode, new messages (by cursor), job status. """

from collections.abc import Callable
from typing import Any

import pytest
from flask import Flask

from components.classaid_core import wait_for_job
from tests.conftest import AppClient

from .helpers import COUNTER_JAVA, COUNTER_MAIN, available_task

FILES = {'Counter.java': COUNTER_JAVA, 'Main.java': COUNTER_MAIN}
STUDENT = 102


def state(client: AppClient, query: str = '') -> dict[str, Any]:
    response = client.get(f'/classaid/api/state{query}')
    assert response.status_code == 200
    data: dict[str, Any] | None = response.json
    assert data is not None
    return data


@pytest.fixture
def setup(login_as: Callable[..., AppClient]) -> tuple[AppClient, AppClient, int]:
    instructor = login_as('instructor')
    task_id = available_task(instructor)
    student = login_as('student1')
    student.get(f'/classaid/api/tasks/{task_id}')
    return instructor, student, task_id


def test_mode_change_seen_on_next_poll(setup: tuple[AppClient, AppClient, int]) -> None:
    """ Scenario (mode-control): after the instructor changes the student's mode, the next
    poll returns the new mode -- the workspace polls every 3 s, within the 5 s requirement. """
    instructor, student, _task_id = setup
    assert state(student)['mode'] == {'mode': 'heuristic', 'source': 'class'}
    instructor.put(f'/classaid/api/modes/students/{STUDENT}', json={'mode': 'silent'})
    assert state(student)['mode'] == {'mode': 'silent', 'source': 'student'}
    instructor.put('/classaid/api/modes/class', json={'mode': 'auto'})
    assert state(student)['mode'] == {'mode': 'auto', 'source': 'class'}


@pytest.mark.usefixtures('fake_llm')
def test_messages_by_cursor(app: Flask, setup: tuple[AppClient, AppClient, int]) -> None:
    _instructor, student, task_id = setup
    assert state(student, f'?task={task_id}')['messages'] == []

    ask = student.post(f'/classaid/api/tasks/{task_id}/ask', json={'question': 'Q1', 'files': FILES}).json
    assert ask is not None
    with app.app_context():
        wait_for_job(ask['job_id'], timeout=30)
    first = state(student, f"?task={task_id}&jobs={ask['job_id']}")
    assert [m['role'] for m in first['messages']] == ['student', 'assistant']
    assert first['jobs'] == [{'id': ask['job_id'], 'kind': 'feedback', 'status': 'done'}]
    assert first['task_status'] == 'in_progress'

    cursor = first['messages'][-1]['id']
    assert state(student, f'?task={task_id}&after={cursor}')['messages'] == []


def test_queued_job_status_visible(app: Flask, setup: tuple[AppClient, AppClient, int]) -> None:
    """ Jobs are reported while queued/running; other users' job ids are omitted. """
    app.config['CLASSAID_JAVA_HOME'] = '/nonexistent-jdk'
    app.extensions.pop('classaid_runner', None)
    _instructor, student, task_id = setup
    run = student.post(f'/classaid/api/tasks/{task_id}/run', json={'files': FILES}).json
    assert run is not None
    (job,) = state(student, f"?jobs={run['job_id']}")['jobs']
    assert job['status'] in ('queued', 'running', 'failed')
    with app.app_context():
        wait_for_job(run['job_id'], timeout=30)
    (job,) = state(student, f"?jobs={run['job_id']},999999")['jobs']
    assert job['status'] == 'failed'
    assert job['error'] == "The code runner is unavailable right now.  Please tell your instructor."


def test_state_hides_other_students_jobs(login_as: Callable[..., AppClient], app: Flask, setup: tuple[AppClient, AppClient, int]) -> None:
    app.config['CLASSAID_JAVA_HOME'] = '/nonexistent-jdk'
    app.extensions.pop('classaid_runner', None)
    _instructor, student, task_id = setup
    run = student.post(f'/classaid/api/tasks/{task_id}/run', json={'files': FILES}).json
    assert run is not None
    assert state(login_as('student2'), f"?jobs={run['job_id']}")['jobs'] == []


def test_state_for_unavailable_task(login_as: Callable[..., AppClient]) -> None:
    student = login_as('student1')
    assert student.get('/classaid/api/state?task=999').status_code == 404
