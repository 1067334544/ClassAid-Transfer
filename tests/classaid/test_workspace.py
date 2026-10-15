# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Spec classaid/task-workspace: opening tasks and autosaving student code. """

import json
from collections.abc import Callable

from flask import Flask

from gened.db import get_db
from tests.conftest import AppClient

from .helpers import COUNTER_JAVA, COUNTER_MAIN, available_task, create_task, task_ids


def _events(app: Flask, event_type: str) -> list[dict[str, object]]:
    with app.app_context():
        rows = get_db().execute(
            "SELECT e.*, s.files AS snapshot FROM classaid_events e LEFT JOIN classaid_snapshots s ON s.id=e.snapshot_id WHERE type=? ORDER BY e.id",
            [event_type],
        ).fetchall()
    return [dict(r) for r in rows]


def test_first_open_loads_starter_code(app: Flask, login_as: Callable[..., AppClient]) -> None:
    """ Scenario: first open shows the starter code and the task description. """
    task_id = available_task(login_as('instructor'))
    student = login_as('student1')

    response = student.get(f'/classaid/api/tasks/{task_id}')
    assert response.status_code == 200
    data = response.json
    assert data is not None
    assert data['task']['title'] == 'Counter'
    assert 'increment()' in data['task']['description']
    assert data['task']['starter_files'] == {'Counter.java': COUNTER_JAVA, 'Main.java': COUNTER_MAIN}
    assert data['progress']['status'] == 'in_progress'
    assert data['progress']['files'] == {'Counter.java': COUNTER_JAVA, 'Main.java': COUNTER_MAIN}
    # tests are never part of what students receive
    assert 'HIDDEN-TEST-SOURCE' not in response.text
    assert 'CounterTest' not in response.text

    opened = _events(app, 'task_opened')
    assert [(e['user_id'], e['task_id'], e['role_id']) for e in opened] == [(102, task_id, 2)]


def test_refresh_restores_saved_code(app: Flask, login_as: Callable[..., AppClient]) -> None:
    """ Scenario: after editing (autosave) and refreshing, the edited code is shown, not the starter code. """
    task_id = available_task(login_as('instructor'))
    student = login_as('student1')
    student.get(f'/classaid/api/tasks/{task_id}')

    edited = {'Counter.java': COUNTER_JAVA.replace('+= 2', '+= 1'), 'Main.java': COUNTER_MAIN}
    response = student.put(f'/classaid/api/tasks/{task_id}/code', json={'files': edited})
    assert response.status_code == 200

    # a fresh session (e.g., after logging in again) sees the saved code
    again = login_as('student1').get(f'/classaid/api/tasks/{task_id}')
    assert again.json is not None
    assert again.json['progress']['files'] == edited

    edits = _events(app, 'code_edit')
    assert len(edits) == 1
    assert json.loads(str(edits[0]['payload'])) == {'reason': 'autosave'}
    assert json.loads(str(edits[0]['snapshot'])) == edited


def test_unchanged_save_not_logged(app: Flask, login_as: Callable[..., AppClient]) -> None:
    task_id = available_task(login_as('instructor'))
    student = login_as('student1')
    student.get(f'/classaid/api/tasks/{task_id}')
    files = {'Counter.java': COUNTER_JAVA, 'Main.java': COUNTER_MAIN}
    assert student.put(f'/classaid/api/tasks/{task_id}/code', json={'files': files}).status_code == 200
    assert _events(app, 'code_edit') == []


def test_students_are_independent(login_as: Callable[..., AppClient]) -> None:
    task_id = available_task(login_as('instructor'))
    s1, s2 = login_as('student1'), login_as('student2')
    s1.get(f'/classaid/api/tasks/{task_id}')
    s2.get(f'/classaid/api/tasks/{task_id}')
    s1.put(f'/classaid/api/tasks/{task_id}/code', json={'files': {'Counter.java': '// mine', 'Main.java': COUNTER_MAIN}})
    response = s2.get(f'/classaid/api/tasks/{task_id}')
    assert response.json is not None
    assert response.json['progress']['files']['Counter.java'] == COUNTER_JAVA


def test_non_member_denied(login_as: Callable[..., AppClient]) -> None:
    """ Scenario: a user who is not in the class cannot open its tasks. """
    task_id = available_task(login_as('instructor'))
    outsider = login_as('outsider', class_id=2)   # instructor of CS2-B, no role in CS2-A
    assert outsider.get(f'/classaid/api/tasks/{task_id}').status_code == 404
    assert outsider.put(f'/classaid/api/tasks/{task_id}/code', json={'files': {}}).status_code == 404
    # switching to a class without a role is not possible either
    assert outsider.get('/classes/switch/1').status_code == 302
    assert outsider.get(f'/classaid/api/tasks/{task_id}').status_code == 404


def test_hidden_task_not_openable_by_students(login_as: Callable[..., AppClient]) -> None:
    instructor = login_as('instructor')
    create_task(instructor, 'Hidden')
    task_id = max(task_ids(instructor))
    assert login_as('student1').get(f'/classaid/api/tasks/{task_id}').status_code == 404
    assert instructor.get(f'/classaid/api/tasks/{task_id}').status_code == 200  # instructor preview


def test_invalid_saves_rejected(login_as: Callable[..., AppClient]) -> None:
    task_id = available_task(login_as('instructor'))
    student = login_as('student1')
    url = f'/classaid/api/tasks/{task_id}/code'
    assert student.put(url, json={'files': {'Counter.java': COUNTER_JAVA, 'Main.java': COUNTER_MAIN}}).status_code == 409  # not opened yet
    student.get(f'/classaid/api/tasks/{task_id}')
    assert student.put(url, json={'files': {'Counter.java': 'x'}}).status_code == 400                      # missing file
    assert student.put(url, json={'files': {'Counter.java': 'x', 'Main.java': 'y', 'Extra.java': ''}}).status_code == 400
    assert student.put(url, json={'files': 'nope'}).status_code == 400
    assert student.put(url, data='not json').status_code == 415   # not a JSON request (see test_api_security)


def test_admin_without_role_can_preview(app: Flask, login_as: Callable[..., AppClient]) -> None:
    """ Admins act as instructors in any class with Gen-Ed role_id -1; events store NULL for it. """
    task_id = available_task(login_as('instructor'))
    admin = login_as('admin')
    assert admin.get(f'/classaid/api/tasks/{task_id}').status_code == 200
    opened = [e for e in _events(app, 'task_opened') if e['user_id'] == 105]
    assert len(opened) == 1
    assert opened[0]['role_id'] is None
