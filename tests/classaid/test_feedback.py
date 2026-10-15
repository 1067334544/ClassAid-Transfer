# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Spec classaid/feedback-modes (with a fake LLM; no real requests). """

import json
from collections.abc import Callable
from typing import Any

import pytest
from flask import Flask

from components.classaid_agent.feedback import NO_KEY_NOTICE, SILENT_NOTICE
from components.classaid_core import wait_for_job
from components.classaid_core.api import ClassContext
from components.classaid_core.log import log_event
from gened.db import get_db
from tests.conftest import AppClient

from .helpers import COUNTER_JAVA, COUNTER_MAIN, FakeLLM, available_task

FILES = {'Counter.java': COUNTER_JAVA, 'Main.java': COUNTER_MAIN}
STUDENT = 102


@pytest.fixture
def setup(login_as: Callable[..., AppClient]) -> tuple[AppClient, AppClient, int]:
    instructor = login_as('instructor')
    task_id = available_task(instructor)
    student = login_as('student1')
    student.get(f'/classaid/api/tasks/{task_id}')
    return instructor, student, task_id


def ask(app: Flask, student: AppClient, task_id: int, question: str = 'Why does get() return 2?', files: dict[str, str] | None = None) -> dict[str, Any]:
    response = student.post(f'/classaid/api/tasks/{task_id}/ask', json={'question': question, 'files': files or FILES})
    assert response.status_code == 202, response.text
    data: dict[str, Any] | None = response.json
    assert data is not None
    with app.app_context():
        wait_for_job(data['job_id'], timeout=30)
    return data


def messages(student: AppClient, task_id: int) -> list[dict[str, Any]]:
    response = student.get(f'/classaid/api/tasks/{task_id}/messages')
    assert response.json is not None
    msgs: list[dict[str, Any]] = response.json['messages']
    return msgs


def generations(app: Flask) -> list[dict[str, Any]]:
    with app.app_context():
        return [dict(r) for r in get_db().execute("SELECT * FROM classaid_generations ORDER BY id")]


def events(app: Flask, event_type: str) -> list[dict[str, Any]]:
    with app.app_context():
        rows = get_db().execute("SELECT * FROM classaid_events WHERE type=? ORDER BY id", [event_type]).fetchall()
    return [dict(r) | {'payload': json.loads(r['payload'])} for r in rows]


def set_mode(instructor: AppClient, mode: str, student_id: int = STUDENT) -> None:
    assert instructor.put(f'/classaid/api/modes/students/{student_id}', json={'mode': mode}).status_code == 200


def log_failed_test_run(app: Flask, task_id: int) -> None:
    """ Record a 'test_run' event as if the student ran the tests (no JDK needed). """
    result = {
        'kind': 'tests', 'status': 'ok', 'compile': {'ok': True, 'diagnostics': []},
        'stdout': 'STDOUT-DURING-TESTS', 'stderr': '', 'stdout_truncated': False, 'stderr_truncated': False,
        'exit_code': 0, 'limit_exceeded': None, 'exception': None,
        'tests': [
            {'id': 'CounterTest#startsAtZero', 'name': 'startsAtZero()', 'status': 'passed', 'message': None, 'exception': None},
            {'id': 'CounterTest#incrementsByOne', 'name': 'incrementsByOne()', 'status': 'failed', 'message': 'expected: <1> but was: <2>', 'exception': None},
        ],
        'score': 1.3, 'duration_ms': 1, 'internal_error': None,
    }
    with app.app_context():
        ctx = ClassContext(user_id=STUDENT, class_id=1, role_id=2, role='student', class_enabled=True)
        log_event(ctx, 'test_run', task_id=task_id, payload={'job_id': 0, 'result': result}, files=FILES)
        get_db().commit()


# ---------------------------------------------------------------- request assembly (5.1)

def test_question_includes_task_context(app: Flask, fake_llm: FakeLLM, setup: tuple[AppClient, AppClient, int]) -> None:
    """ Scenario: after a failing test run, the question's input includes the question, the
    current code, and that test result -- and never the instructor's test source. """
    _instructor, student, task_id = setup
    log_failed_test_run(app, task_id)
    ask(app, student, task_id, 'Why does it fail?')

    (call,) = fake_llm.calls
    user_message = call[-1]['content']
    assert 'Why does it fail?' in user_message
    assert 'count += 2;' in user_message                       # current code
    assert 'Fix **Counter**' in user_message                  # task description
    assert 'incrementsByOne(): failed -- expected: <1> but was: <2>' in user_message
    assert 'score: 1.3 / 5' in user_message
    everything = json.dumps(fake_llm.calls)
    assert 'HIDDEN-TEST-SOURCE' not in everything
    assert 'assertEquals' not in everything
    assert 'STDOUT-DURING-TESTS' not in everything          # tests-mode output is never shown or sent


def test_history_is_included(app: Flask, fake_llm: FakeLLM, setup: tuple[AppClient, AppClient, int]) -> None:
    _instructor, student, task_id = setup
    ask(app, student, task_id, 'First question')
    ask(app, student, task_id, 'Second question')
    second = fake_llm.calls[1]
    assert [m['role'] for m in second] == ['system', 'user', 'assistant', 'user']
    assert second[1]['content'] == 'First question'
    assert second[2]['content'] == 'What does count hold after one call to increment()?'


# ---------------------------------------------------------------- mode templates (5.2)

def test_heuristic_mode(app: Flask, fake_llm: FakeLLM, setup: tuple[AppClient, AppClient, int]) -> None:
    _instructor, student, task_id = setup   # default class mode: heuristic
    ask(app, student, task_id, 'Just give me the correct increment method')
    system = fake_llm.calls[0][0]['content']
    assert 'FEEDBACK MODE: HEURISTIC' in system
    assert 'Do NOT give a complete solution' in system
    assert 'under 100 words' in system

    reply = messages(student, task_id)[-1]
    assert (reply['role'], reply['feedback_type'], reply['origin']) == ('assistant', 'heuristic', 'user_triggered')
    (gen,) = generations(app)
    assert (gen['status'], gen['effective_mode'], gen['mode_source'], gen['selected_type'], gen['prompt_version']) == \
        ('generated', 'heuristic', 'class', 'heuristic', 'heuristic.user.v1')


def test_technical_mode(app: Flask, fake_llm: FakeLLM, setup: tuple[AppClient, AppClient, int]) -> None:
    instructor, student, task_id = setup
    set_mode(instructor, 'technical')
    ask(app, student, task_id)
    system = fake_llm.calls[0][0]['content']
    assert 'FEEDBACK MODE: TECHNICAL' in system
    assert 'complete correction' in system
    reply = messages(student, task_id)[-1]
    assert reply['feedback_type'] == 'technical'
    assert '`count += 1;`' in reply['content']
    gen = generations(app)[0]
    assert (gen['mode_source'], gen['prompt_version']) == ('student', 'technical.user.v1')


# ---------------------------------------------------------------- auto (5.3)

def test_auto_mode_records_selection(app: Flask, fake_llm: FakeLLM, setup: tuple[AppClient, AppClient, int]) -> None:
    """ Scenario: in Auto mode the reply is labeled with the selected type, and the selected
    type and its reason are logged. """
    instructor, student, task_id = setup
    set_mode(instructor, 'auto')
    ask(app, student, task_id)

    assert [c[0]['content'].count('deciding which kind of feedback') for c in fake_llm.calls] == [1, 0]
    assert messages(student, task_id)[-1]['feedback_type'] == 'technical'
    gen = generations(app)[0]
    assert gen['selected_type'] == 'technical'
    selection = json.loads(gen['selection'])
    assert selection == {'selected_type': 'technical', 'reason': 'Concrete logic bug with a failing test.', 'fallback': False}
    calls = json.loads(gen['calls'])
    assert [c['purpose'] for c in calls] == ['select', 'generate']
    assert [c['prompt_version'] for c in calls] == ['auto.select.v1', 'technical.user.v1']
    (event,) = events(app, 'feedback_generated')
    assert event['payload']['selected_type'] == 'technical'
    assert event['payload']['effective_mode'] == 'auto'


def test_auto_mode_unparseable_selection_falls_back(app: Flask, fake_llm: FakeLLM, setup: tuple[AppClient, AppClient, int]) -> None:
    instructor, student, task_id = setup
    set_mode(instructor, 'auto')
    fake_llm.selection = 'I think heuristic would be best here.'   # not JSON
    ask(app, student, task_id)
    gen = generations(app)[0]
    selection = json.loads(gen['selection'])
    assert selection['fallback'] is True
    assert gen['selected_type'] == 'heuristic'   # no compile/runtime error -> heuristic
    assert messages(student, task_id)[-1]['feedback_type'] == 'heuristic'


# ---------------------------------------------------------------- silent, failures, mode timing (5.4)

def test_silent_mode_suppresses_feedback(app: Flask, fake_llm: FakeLLM, setup: tuple[AppClient, AppClient, int]) -> None:
    """ Scenario: in Silent mode the question is saved, the student sees the paused notice,
    there is no AI reply, and no model call is made. """
    instructor, student, task_id = setup
    set_mode(instructor, 'silent')
    ask(app, student, task_id, 'Help?')

    assert fake_llm.calls == []
    msgs = messages(student, task_id)
    assert [(m['role'], m['content']) for m in msgs] == [('student', 'Help?'), ('notice', SILENT_NOTICE)]
    assert msgs[1]['notice_kind'] == 'silent'
    gen = generations(app)[0]
    assert (gen['status'], gen['effective_mode'], gen['calls'], gen['model']) == ('suppressed', 'silent', '[]', None)
    assert len(events(app, 'feedback_suppressed')) == 1
    assert len(events(app, 'question')) == 1


def test_silent_mode_still_runs_code(setup: tuple[AppClient, AppClient, int]) -> None:
    """ Scenario: in Silent mode Run Tests still works (accepted; executed by the runner). """
    instructor, student, task_id = setup
    set_mode(instructor, 'silent')
    response = student.post(f'/classaid/api/tasks/{task_id}/test', json={'files': FILES})
    assert response.status_code == 202


def test_no_class_key(app: Flask, fake_llm: FakeLLM, setup: tuple[AppClient, AppClient, int]) -> None:
    """ Scenario: with no class API key, the student sees a not-configured notice, the question is
    saved, and the failure reason is logged -- not shown as AI feedback. """
    _instructor, student, task_id = setup
    with app.app_context():
        get_db().execute("UPDATE classes_user SET llm_api_key='' WHERE class_id=1")
        get_db().commit()
    ask(app, student, task_id, 'Help?')

    assert fake_llm.calls == []
    msgs = messages(student, task_id)
    assert [(m['role'], m['notice_kind'], m['content']) for m in msgs] == [('student', None, 'Help?'), ('notice', 'error', NO_KEY_NOTICE)]
    assert all(m['role'] != 'assistant' for m in msgs)
    gen = generations(app)[0]
    assert (gen['status'], gen['error']) == ('failed', 'no_key')
    assert events(app, 'feedback_failed')[0]['payload']['error'] == 'no_key'


def test_model_error_not_shown_as_feedback(app: Flask, fake_llm: FakeLLM, setup: tuple[AppClient, AppClient, int]) -> None:
    _instructor, student, task_id = setup
    fake_llm.fail_generate = True
    ask(app, student, task_id)
    reply = messages(student, task_id)[-1]
    assert (reply['role'], reply['notice_kind']) == ('notice', 'error')
    gen = generations(app)[0]
    assert (gen['status'], gen['error']) == ('failed', 'boom')
    assert json.loads(gen['calls'])[0]['raw'] == {'error': 'boom'}


def test_mode_switch_during_processing(app: Flask, fake_llm: FakeLLM, setup: tuple[AppClient, AppClient, int]) -> None:
    """ Scenario: the instructor switches the student to Technical while a Heuristic reply is
    being generated; that reply stays Heuristic and the next question is handled as Technical. """
    instructor, student, task_id = setup

    def instructor_switches() -> None:
        fake_llm.on_generate = None
        set_mode(instructor, 'technical')

    fake_llm.on_generate = instructor_switches
    ask(app, student, task_id, 'First')
    assert messages(student, task_id)[-1]['feedback_type'] == 'heuristic'

    ask(app, student, task_id, 'Second')
    assert messages(student, task_id)[-1]['feedback_type'] == 'technical'
    assert [g['effective_mode'] for g in generations(app)] == ['heuristic', 'technical']


# ---------------------------------------------------------------- ask and rating API (5.5)

def test_ask_validation(setup: tuple[AppClient, AppClient, int]) -> None:
    _instructor, student, task_id = setup
    url = f'/classaid/api/tasks/{task_id}/ask'
    assert student.post(url, json={'question': '   ', 'files': FILES}).status_code == 400
    assert student.post(url, json={'question': 'x' * 5000, 'files': FILES}).status_code == 400
    assert student.post(url, json={'question': 'ok', 'files': {}}).status_code == 400


def test_completed_task_chat_is_read_only(app: Flask, setup: tuple[AppClient, AppClient, int]) -> None:
    _instructor, student, task_id = setup
    with app.app_context():
        get_db().execute("UPDATE classaid_task_progress SET status='completed' WHERE user_id=? AND task_id=?", [STUDENT, task_id])
        get_db().commit()
    response = student.post(f'/classaid/api/tasks/{task_id}/ask', json={'question': 'Still there?', 'files': FILES})
    assert response.status_code == 409


@pytest.mark.usefixtures('fake_llm')
def test_rating_change(app: Flask, login_as: Callable[..., AppClient], setup: tuple[AppClient, AppClient, int]) -> None:
    """ Scenario: rating "not helpful" then "helpful" leaves "helpful" current; both are logged. """
    _instructor, student, task_id = setup
    ask(app, student, task_id)
    reply = messages(student, task_id)[-1]
    url = f"/classaid/api/messages/{reply['id']}/rating"

    response = student.put(url, json={'value': -1})
    assert response.json == {'message_id': reply['id'], 'rating': -1, 'message': 'Thanks for your feedback!'}
    student.put(url, json={'value': 1})
    assert messages(student, task_id)[-1]['rating'] == 1
    assert [(e['payload']['value'], e['payload']['previous']) for e in events(app, 'rating')] == [(-1, None), (1, -1)]

    student.put(url, json={'value': None})   # withdraw
    assert messages(student, task_id)[-1]['rating'] is None

    question = messages(student, task_id)[0]
    assert student.put(f"/classaid/api/messages/{question['id']}/rating", json={'value': 1}).status_code == 404  # not an AI message
    assert login_as('student2').put(url, json={'value': 1}).status_code == 404                                  # not theirs
    assert student.put(url, json={'value': 5}).status_code == 400
