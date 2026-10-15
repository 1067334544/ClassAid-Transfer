# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Spec classaid/mode-control. """

import json
from collections.abc import Callable
from typing import Any

import pytest
from flask import Flask

from components.classaid_agent.modes import get_effective_mode
from gened.db import get_db
from tests.conftest import AppClient

from .helpers import available_task

STUDENT_A, STUDENT_B = 102, 103   # student1, student2 in CS2-A
CLASS_A = 1


def effective(app: Flask, user_id: int) -> tuple[str, str]:
    with app.app_context():
        eff = get_effective_mode(CLASS_A, user_id)
    return eff.mode, eff.source


def mode_events(app: Flask) -> list[dict[str, Any]]:
    with app.app_context():
        rows = get_db().execute("SELECT user_id, role_id, payload FROM classaid_events WHERE type='mode_changed' ORDER BY id").fetchall()
    return [{'user_id': r['user_id'], 'role_id': r['role_id'], 'payload': json.loads(r['payload'])} for r in rows]


@pytest.fixture
def instructor(login_as: Callable[..., AppClient]) -> AppClient:
    return login_as('instructor')


def test_default_class_mode_is_heuristic(app: Flask) -> None:
    assert effective(app, STUDENT_A) == ('heuristic', 'class')


def test_no_individual_mode_uses_class_mode(app: Flask, instructor: AppClient) -> None:
    """ Scenario: class mode Auto, student A has no individual mode -> Auto. """
    assert instructor.put('/classaid/api/modes/class', json={'mode': 'auto'}).status_code == 200
    assert effective(app, STUDENT_A) == ('auto', 'class')


def test_individual_mode_overrides_class_mode(app: Flask, instructor: AppClient) -> None:
    """ Scenario: class mode Auto, student B's individual mode Technical -> Technical. """
    instructor.put('/classaid/api/modes/class', json={'mode': 'auto'})
    assert instructor.put(f'/classaid/api/modes/students/{STUDENT_B}', json={'mode': 'technical'}).status_code == 200
    assert effective(app, STUDENT_B) == ('technical', 'student')
    assert effective(app, STUDENT_A) == ('auto', 'class')


def test_set_one_student(app: Flask, instructor: AppClient) -> None:
    """ Scenario: setting student B to Technical changes only B. """
    response = instructor.put(f'/classaid/api/modes/students/{STUDENT_B}', json={'mode': 'technical'})
    assert response.json == {'user_id': STUDENT_B, 'mode': 'technical', 'source': 'student'}
    assert effective(app, STUDENT_B) == ('technical', 'student')
    assert effective(app, STUDENT_A) == ('heuristic', 'class')

    (event,) = mode_events(app)
    assert event['user_id'] == 101   # the acting instructor
    assert event['payload']['scope'] == 'student'
    assert event['payload']['affected_students'] == [STUDENT_B]
    assert event['payload']['before'] == {str(STUDENT_B): {'mode': 'heuristic', 'source': 'class'}}
    assert event['payload']['after'] == {str(STUDENT_B): {'mode': 'technical', 'source': 'student'}}


def test_clear_individual_mode(app: Flask, instructor: AppClient) -> None:
    """ Scenario: clearing B's individual mode returns B to the class mode (Heuristic). """
    instructor.put(f'/classaid/api/modes/students/{STUDENT_B}', json={'mode': 'technical'})
    response = instructor.delete(f'/classaid/api/modes/students/{STUDENT_B}')
    assert response.status_code == 200
    assert effective(app, STUDENT_B) == ('heuristic', 'class')
    assert mode_events(app)[-1]['payload']['action'] == 'clear'


def test_set_all(app: Flask, instructor: AppClient) -> None:
    """ Scenario: B has Technical; "set all to Heuristic" sets the class mode, clears B's
    individual mode, and every student's effective mode is Heuristic.  The event records
    the cleared individual mode. """
    instructor.put('/classaid/api/modes/class', json={'mode': 'auto'})
    instructor.put(f'/classaid/api/modes/students/{STUDENT_B}', json={'mode': 'technical'})
    instructor.put(f'/classaid/api/modes/students/{STUDENT_A}', json={'mode': 'silent'})

    assert instructor.put('/classaid/api/modes/class', json={'mode': 'heuristic'}).status_code == 200
    assert effective(app, STUDENT_A) == ('heuristic', 'class')
    assert effective(app, STUDENT_B) == ('heuristic', 'class')

    payload = mode_events(app)[-1]['payload']
    assert payload['scope'] == 'class'
    assert payload['class_mode_before'] == 'auto'
    assert payload['class_mode_after'] == 'heuristic'
    assert payload['cleared_student_modes'] == [{'user_id': STUDENT_A, 'mode': 'silent'}, {'user_id': STUDENT_B, 'mode': 'technical'}]
    assert payload['affected_students'] == [STUDENT_A, STUDENT_B]


def test_students_cannot_change_modes(app: Flask, login_as: Callable[..., AppClient]) -> None:
    """ Scenario: a student sending a mode change request is refused; modes are unchanged. """
    student = login_as('student1')
    assert student.put('/classaid/api/modes/class', json={'mode': 'technical'}).status_code == 403
    assert student.put(f'/classaid/api/modes/students/{STUDENT_A}', json={'mode': 'technical'}).status_code == 403
    assert student.delete(f'/classaid/api/modes/students/{STUDENT_A}').status_code == 403
    assert student.get('/classaid/api/modes').status_code == 403
    assert effective(app, STUDENT_A) == ('heuristic', 'class')
    assert mode_events(app) == []


def test_other_class_instructor_cannot_change_modes(app: Flask, login_as: Callable[..., AppClient]) -> None:
    outsider = login_as('outsider', class_id=2)
    # acting on CS2-B (their own class): students of CS2-A are not found there
    assert outsider.put(f'/classaid/api/modes/students/{STUDENT_A}', json={'mode': 'technical'}).status_code == 404
    # and a class-wide change only affects CS2-B
    assert outsider.put('/classaid/api/modes/class', json={'mode': 'silent'}).status_code == 200
    assert effective(app, STUDENT_A) == ('heuristic', 'class')


def test_invalid_mode_rejected(instructor: AppClient) -> None:
    assert instructor.put('/classaid/api/modes/class', json={'mode': 'Technical!'}).status_code == 400
    assert instructor.put(f'/classaid/api/modes/students/{STUDENT_A}', json={}).status_code == 400
    assert instructor.put('/classaid/api/modes/students/101', json={'mode': 'auto'}).status_code == 404  # an instructor, not a student


def test_mode_list(login_as: Callable[..., AppClient], instructor: AppClient) -> None:
    """ Scenario: the list shows one row per student with effective mode and its source (plus current task). """
    task_id = available_task(instructor)
    login_as('student1').get(f'/classaid/api/tasks/{task_id}')
    instructor.put(f'/classaid/api/modes/students/{STUDENT_B}', json={'mode': 'technical'})

    response = instructor.get('/classaid/api/modes')
    assert response.status_code == 200
    data = response.json
    assert data is not None
    assert data['class_mode'] == 'heuristic'
    assert data['students'] == [
        {'user_id': STUDENT_A, 'name': 'Sam Student', 'mode': 'heuristic', 'source': 'class',
         'current_task': {'id': task_id, 'title': 'Counter', 'status': 'in_progress'}},
        {'user_id': STUDENT_B, 'name': 'Sky Student', 'mode': 'technical', 'source': 'student', 'current_task': None},
    ]
