# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Spec classaid/task-workspace: instructor-defined Java tasks. """

import json
from collections.abc import Callable

from flask import Flask

from gened.db import get_db
from tests.conftest import AppClient

from .helpers import TABLE_URL, counter_spec, create_task, set_available, task_ids


def _task_rows(app: Flask) -> list[tuple[int, str, int]]:
    with app.app_context():
        return [
            (r['id'], r['name'], r['class_order'])
            for r in get_db().execute("SELECT id, name, class_order FROM config_items WHERE item_type='classaid_task' ORDER BY class_order")
        ]


def test_edit_form_renders(login_as: Callable[..., AppClient]) -> None:
    instructor = login_as('instructor')
    response = instructor.get(f'{TABLE_URL}/new')
    assert response.status_code == 200
    assert 'classaidTaskForm' in response.text
    assert 'Main.java' in response.text


def test_task_table_on_class_config_page(login_as: Callable[..., AppClient]) -> None:
    instructor = login_as('instructor')
    create_task(instructor, 'Counter')
    response = instructor.get('/instructor/config/')
    assert response.status_code == 200
    assert 'Counter' in response.text
    assert 'New tasks are hidden from students' in response.text


def test_create_task(app: Flask, login_as: Callable[..., AppClient]) -> None:
    """ Scenario: creating a task adds it to the class's task list in instructor-defined order. """
    instructor = login_as('instructor')
    assert create_task(instructor, 'Counter').status_code == 302
    assert create_task(instructor, 'Second task').status_code == 302

    rows = _task_rows(app)
    assert [(name, order) for _, name, order in rows] == [('Counter', 0), ('Second task', 1)]
    response = instructor.get('/classaid/api/tasks')
    assert [t['title'] for t in response.json['tasks']] == ['Counter', 'Second task']  # type: ignore[index]

    with app.app_context():
        config = json.loads(get_db().execute("SELECT config FROM config_items WHERE id=?", [rows[0][0]]).fetchone()['config'])
    assert config['spec']['weights'] == {'CounterTest#startsAtZero': 1, 'CounterTest#incrementsByOne': 3}


def test_new_task_hidden_until_available(app: Flask, login_as: Callable[..., AppClient]) -> None:
    """ Scenario: a task whose available date is in the future is not shown to students. """
    instructor = login_as('instructor')
    student = login_as('student1')
    create_task(instructor, 'Counter')
    (task_id, _, _), = _task_rows(app)

    assert task_ids(student) == []           # new tasks default to hidden
    assert task_ids(instructor) == [task_id]  # instructors see all tasks

    set_available(instructor, task_id, '2999-01-01')
    assert task_ids(student) == []

    set_available(instructor, task_id, '2000-01-01')
    assert task_ids(student) == [task_id]


def test_invalid_task_rejected(app: Flask, login_as: Callable[..., AppClient]) -> None:
    instructor = login_as('instructor')
    bad_specs = [
        counter_spec(tests=[]),                                                      # no tests
        counter_spec(files=[{'name': 'not java.txt', 'content': ''}]),               # bad file name
        counter_spec(entry='Missing'),                                               # entry not a starter file
        counter_spec(weights={'CounterTest#startsAtZero': 0}),                       # non-positive weight
        counter_spec(tests=[{'name': 'Counter.java', 'content': ''}]),               # duplicate file name
    ]
    for spec in bad_specs:
        assert create_task(instructor, 'Bad', spec).status_code == 400
    assert instructor.post(f'{TABLE_URL}/create', data={'name': 'Bad', 'task_json': '{not json'}).status_code == 400
    assert _task_rows(app) == []


def test_students_cannot_edit_tasks(login_as: Callable[..., AppClient]) -> None:
    student = login_as('student1')
    assert create_task(student, 'Sneaky').status_code == 403


def test_task_list_requires_class(login_as: Callable[..., AppClient]) -> None:
    admin_without_class = login_as('admin', class_id=None)
    response = admin_without_class.get('/classaid/api/tasks')
    assert response.status_code == 403
    assert response.json == {'error': 'No active class.'}
