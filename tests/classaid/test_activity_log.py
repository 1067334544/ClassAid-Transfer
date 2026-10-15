# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Spec classaid/activity-log: append-only events, traceability, export, data deletion.

Related scenarios tested elsewhere: "Run Tests is logged" (test_runs.test_runs_are_logged),
"Silent suppression" (test_feedback.test_silent_mode_suppresses_feedback), and
"changing a rating" (test_feedback.test_rating_change).
"""

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from flask import Flask

from components.classaid_core.api import ClassContext
from components.classaid_core.log import EVENT_TYPES, UnknownEventTypeError, log_event
from gened.data_deletion import delete_class_data
from gened.db import get_db
from tests.conftest import AppClient

from .helpers import COUNTER_JAVA, COUNTER_MAIN, available_task
from .test_feedback import FILES, ask, log_failed_test_run, messages

SRC = Path(__file__).resolve().parents[2] / 'src' / 'components'
STUDENT = 102


@pytest.fixture
def setup(login_as: Callable[..., AppClient]) -> tuple[AppClient, AppClient, int]:
    instructor = login_as('instructor')
    task_id = available_task(instructor)
    student = login_as('student1')
    student.get(f'/classaid/api/tasks/{task_id}')
    return instructor, student, task_id


def db_rows(app: Flask, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    with app.app_context():
        return [dict(r) for r in get_db().execute(sql, params or [])]


# ---------------------------------------------------------------- append-only (6.1)

def test_unknown_event_type_rejected(app: Flask) -> None:
    ctx = ClassContext(user_id=STUDENT, class_id=1, role_id=2, role='student', class_enabled=True)
    with app.app_context(), pytest.raises(UnknownEventTypeError):
        log_event(ctx, 'made_up_event')


def test_only_deletion_handlers_modify_the_log() -> None:
    """ No application path UPDATEs or DELETEs events or snapshots, except personal data deletion. """
    pattern = re.compile(r'(UPDATE|DELETE\s+FROM)\s+classaid_(events|snapshots)\b', re.IGNORECASE)
    offenders = {
        str(path.relative_to(SRC))
        for path in SRC.glob('classaid_*/**/*.py')
        if pattern.search(path.read_text(encoding='utf-8'))
    }
    assert offenders == {'classaid_core/data.py', 'classaid_agent/data.py'}


def test_p1_event_types_registered() -> None:
    assert {'task_opened', 'code_edit', 'run', 'test_run', 'question', 'rating', 'task_completed',
            'feedback_generated', 'feedback_suppressed', 'feedback_failed', 'mode_changed'} == EVENT_TYPES


# ---------------------------------------------------------------- traceability (6.1)

@pytest.mark.usefixtures('fake_llm')
def test_trace_a_feedback_message(app: Flask, setup: tuple[AppClient, AppClient, int]) -> None:
    """ Scenario: for an AI message, the triggering question, the code and run result at that
    time, the effective mode and its source, the prompt version, and the model's input and raw
    output can all be found. """
    instructor, student, task_id = setup
    instructor.put(f'/classaid/api/modes/students/{STUDENT}', json={'mode': 'technical'})
    log_failed_test_run(app, task_id)
    ask(app, student, task_id, 'Why does incrementsByOne fail?')
    # the student keeps editing afterwards: the trace must still show the code *at question time*
    student.put(f'/classaid/api/tasks/{task_id}/code', json={'files': {'Counter.java': '// later', 'Main.java': COUNTER_MAIN}})

    reply = messages(student, task_id)[-1]
    (gen,) = db_rows(app, "SELECT g.* FROM classaid_generations g JOIN classaid_messages m ON m.generation_id = g.id WHERE m.id=?", [reply['id']])
    (trigger,) = db_rows(app, """
        SELECT e.type, e.payload, s.files FROM classaid_events e LEFT JOIN classaid_snapshots s ON s.id = e.snapshot_id WHERE e.id=?
    """, [gen['trigger_event_id']])

    assert trigger['type'] == 'question'
    assert json.loads(trigger['payload'])['question'] == 'Why does incrementsByOne fail?'
    assert json.loads(trigger['files']) == FILES
    assert (gen['effective_mode'], gen['mode_source'], gen['prompt_version'], gen['displayed_text']) == \
        ('technical', 'student', 'technical.user.v1', reply['content'])
    (call,) = json.loads(gen['calls'])
    assert 'incrementsByOne(): failed' in call['messages'][-1]['content']   # run result at the time
    assert call['raw'] == {'id': 't'}
    assert call['text'] == reply['content']
    (generated,) = db_rows(app, "SELECT payload FROM classaid_events WHERE type='feedback_generated'")
    assert json.loads(generated['payload'])['message_id'] == reply['id']


# ---------------------------------------------------------------- export (6.2)

def _export(client: AppClient) -> list[dict[str, Any]]:
    response = client.get('/classaid/api/export/events.jsonl')
    assert response.status_code == 200
    assert response.mimetype == 'application/x-ndjson'
    return [json.loads(line) for line in response.get_data(as_text=True).splitlines()]


@pytest.mark.usefixtures('fake_llm')
def test_export_reconstructs_a_students_process(app: Flask, setup: tuple[AppClient, AppClient, int]) -> None:
    """ Scenario: the export contains every class event with time, student, task, and type, and
    is enough to rebuild a student's activity, feedback, and mode changes in order. """
    instructor, student, task_id = setup
    edited = {'Counter.java': COUNTER_JAVA.replace('+= 2', '+= 1'), 'Main.java': COUNTER_MAIN}
    student.put(f'/classaid/api/tasks/{task_id}/code', json={'files': edited})
    ask(app, student, task_id, 'Is it right now?', edited)
    reply = messages(student, task_id)[-1]
    student.put(f"/classaid/api/messages/{reply['id']}/rating", json={'value': 1})
    instructor.put(f'/classaid/api/modes/students/{STUDENT}', json={'mode': 'silent'})
    ask(app, student, task_id, 'And now?', edited)

    lines = _export(instructor)
    assert [line['id'] for line in lines] == sorted(line['id'] for line in lines)
    assert all({'ts', 'user_id', 'task_id', 'type'} <= line.keys() for line in lines)

    own = [line for line in lines if line['user_id'] == STUDENT]
    assert [line['type'] for line in own] == [
        'task_opened', 'code_edit', 'question', 'feedback_generated', 'rating', 'question', 'feedback_suppressed',
    ]
    assert own[1]['files'] == edited
    assert own[2]['payload']['question'] == 'Is it right now?'
    generated = own[3]['generation']
    assert (generated['status'], generated['effective_mode'], generated['displayed_text']) == ('generated', 'heuristic', reply['content'])
    assert generated['calls'][0]['messages'][-1]['content'].endswith('<student_question>\nIs it right now?\n</student_question>')
    assert own[4]['payload'] == {'message_id': reply['id'], 'value': 1, 'previous': None}
    assert own[6]['generation']['status'] == 'suppressed'

    (mode_change,) = [line for line in lines if line['type'] == 'mode_changed']
    assert (mode_change['user_id'], mode_change['role']) == (101, 'instructor')
    assert mode_change['payload']['affected_students'] == [STUDENT]
    assert own[4]['id'] < mode_change['id'] < own[5]['id']   # ordering shows when the mode changed


def test_export_requires_instructor(setup: tuple[AppClient, AppClient, int]) -> None:
    _instructor, student, _task_id = setup
    assert student.get('/classaid/api/export/events.jsonl').status_code == 403


def test_activity_in_gened_instructor_view(setup: tuple[AppClient, AppClient, int]) -> None:
    instructor, _student, _task_id = setup
    response = instructor.get('/instructor/')
    assert response.status_code == 200
    assert 'ClassAid Activity' in response.text


# ---------------------------------------------------------------- data deletion (6.3)

def _personal_rows(app: Flask, user_id: int) -> dict[str, int]:
    tables = ['classaid_events', 'classaid_snapshots', 'classaid_jobs', 'classaid_task_progress',
              'classaid_messages', 'classaid_generations', 'classaid_student_modes']
    return {t: db_rows(app, f"SELECT COUNT(*) AS n FROM {t} WHERE user_id=?", [user_id])[0]['n'] for t in tables}


@pytest.mark.usefixtures('fake_llm')
def test_student_deletes_their_data(app: Flask, setup: tuple[AppClient, AppClient, int]) -> None:
    """ Scenario: after a student deletes their data via the profile page, their ClassAid log,
    code, and chat can no longer be linked to them. """
    instructor, student, task_id = setup
    student.put(f'/classaid/api/tasks/{task_id}/code', json={'files': {'Counter.java': '// SECRET-CODE', 'Main.java': COUNTER_MAIN}})
    ask(app, student, task_id, 'SECRET-QUESTION')
    instructor.put(f'/classaid/api/modes/students/{STUDENT}', json={'mode': 'technical'})
    assert all(n > 0 for t, n in _personal_rows(app, STUDENT).items() if t != 'classaid_jobs')

    response = student.post('/profile/delete_data', data={'confirm_delete': 'DELETE'})
    assert response.status_code == 302

    assert _personal_rows(app, STUDENT) == dict.fromkeys(_personal_rows(app, STUDENT), 0)
    everything = json.dumps(db_rows(app, "SELECT payload FROM classaid_events")) + json.dumps(
        db_rows(app, "SELECT content FROM classaid_messages")) + json.dumps(db_rows(app, "SELECT calls, displayed_text FROM classaid_generations")) + json.dumps(
        db_rows(app, "SELECT current_files FROM classaid_task_progress")) + json.dumps(db_rows(app, "SELECT files FROM classaid_snapshots"))
    assert 'SECRET-CODE' not in everything
    assert 'SECRET-QUESTION' not in everything
    # the instructor's mode_changed event no longer names the student
    (mode_change,) = db_rows(app, "SELECT user_id, payload FROM classaid_events WHERE type='mode_changed'")
    payload = json.loads(mode_change['payload'])
    assert mode_change['user_id'] == 101
    assert payload['affected_students'] == [-1]
    assert str(STUDENT) not in payload['before']
    # non-personal metadata survives for analysis
    assert {r['type'] for r in db_rows(app, "SELECT type FROM classaid_events WHERE user_id=-1")} >= {'question', 'feedback_generated'}
    assert db_rows(app, "SELECT effective_mode FROM classaid_generations")[0]['effective_mode'] == 'heuristic'


@pytest.mark.usefixtures('fake_llm')
def test_class_data_deletion(app: Flask, setup: tuple[AppClient, AppClient, int]) -> None:
    instructor, student, task_id = setup
    ask(app, student, task_id, 'SECRET-QUESTION')
    instructor.put(f'/classaid/api/modes/students/{STUDENT}', json={'mode': 'technical'})
    with app.app_context():
        delete_class_data(1)
    for user_id in (STUDENT, 101):
        assert _personal_rows(app, user_id) == dict.fromkeys(_personal_rows(app, user_id), 0)
    assert 'SECRET-QUESTION' not in json.dumps(db_rows(app, "SELECT payload FROM classaid_events")) + json.dumps(db_rows(app, "SELECT content FROM classaid_messages"))
