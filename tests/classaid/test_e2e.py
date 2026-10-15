# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Task 8.1: end-to-end P1 flow with the local runner and a fake LLM.

A student opens the sample task, runs it, runs the tests, asks in Heuristic mode; the
instructor switches the student to Silent; a second question is suppressed; the student
completes the task; the exported log reconstructs the whole process in order.
"""

import json
from collections.abc import Callable
from typing import Any

import pytest
from flask import Flask

from components.classaid_core import wait_for_job
from components.classaid_tasks.samples import add_sample_to_class, load_sample
from tests.conftest import AppClient

from .helpers import FakeLLM, set_available

STUDENT = 102


def job(app: Flask, client: AppClient, response_json: dict[str, Any] | None) -> dict[str, Any]:
    assert response_json is not None
    with app.app_context():
        wait_for_job(response_json['job_id'], timeout=60)
    data: dict[str, Any] | None = client.get(f"/classaid/api/jobs/{response_json['job_id']}").json
    assert data is not None
    return data


@pytest.mark.usefixtures('jdk')
def test_p1_end_to_end(app: Flask, fake_llm: FakeLLM, login_as: Callable[..., AppClient]) -> None:
    instructor = login_as('instructor')
    with app.app_context():
        task_id = add_sample_to_class('linked_list_remove', 1)
    set_available(instructor, task_id)
    sample, reference = load_sample('linked_list_remove')
    starter = {f.name: f.content for f in sample.spec.files}
    base = f'/classaid/api/tasks/{task_id}'

    # 1. the student opens the sample task
    student = login_as('student1')
    opened = student.get(base).json
    assert opened is not None
    assert opened['progress']['files'] == starter

    # 2. Run (main) with the starter code: remove() is a TODO that returns false
    run = job(app, student, student.post(f'{base}/run', json={'files': starter}).json)
    assert run['result']['status'] == 'ok'
    assert 'remove(5) -> false' in run['result']['stdout']

    # 3. Run Tests: partial credit
    tests = job(app, student, student.post(f'{base}/test', json={'files': starter}).json)
    assert 0 < tests['result']['score'] < 5
    assert tests['result']['stdout'] == ''

    # 4. a question in Heuristic mode (default class mode)
    ask1 = job(app, student, student.post(f'{base}/ask', json={'question': 'Where do I start?', 'files': starter}).json)
    assert ask1['status'] == 'done'
    assert 'removeHead()' in fake_llm.calls[0][-1]['content']   # the failing tests reached the model input
    test_source_line = 'assertEquals("[2, 3]", list.toString());'   # from the instructor's test file
    assert test_source_line in sample.spec.tests[0].content
    assert test_source_line not in json.dumps(fake_llm.calls)

    # 5. the instructor switches the student to Silent; the next poll shows it
    assert instructor.put(f'/classaid/api/modes/students/{STUDENT}', json={'mode': 'silent'}).status_code == 200
    state = student.get(f'/classaid/api/state?task={task_id}').json
    assert state is not None
    assert state['mode'] == {'mode': 'silent', 'source': 'student'}

    # 6. a second question is suppressed: no model call
    calls_before = len(fake_llm.calls)
    job(app, student, student.post(f'{base}/ask', json={'question': 'Just tell me?', 'files': starter}).json)
    assert len(fake_llm.calls) == calls_before
    messages = student.get(f'{base}/messages').json
    assert messages is not None
    assert [(m['role'], m['feedback_type'] or m['notice_kind']) for m in messages['messages']] == [
        ('student', None), ('assistant', 'heuristic'), ('student', None), ('notice', 'silent'),
    ]

    # 7. the student completes the task with a correct solution
    done = job(app, student, student.post(f'{base}/complete', json={'files': reference}).json)
    assert done['result']['score'] == 5.0
    progress = student.get(base).json
    assert progress is not None
    assert (progress['progress']['status'], progress['progress']['score']) == ('completed', 5.0)
    assert student.post(f'{base}/ask', json={'question': 'more?', 'files': reference}).status_code == 409

    # 8. the exported log reconstructs the process in order
    lines = [json.loads(line) for line in instructor.get('/classaid/api/export/events.jsonl').get_data(as_text=True).splitlines()]
    student_types = [line['type'] for line in lines if line['user_id'] == STUDENT]
    assert student_types == [
        'task_opened', 'run', 'test_run', 'question', 'feedback_generated',
        'question', 'feedback_suppressed', 'code_edit', 'task_completed',
        'task_opened',   # step 7 re-opened the task to check its status
    ]
    by_type = {line['type']: line for line in lines if line['user_id'] == STUDENT}
    assert by_type['run']['files'] == starter
    assert by_type['test_run']['payload']['result']['score'] == tests['result']['score']
    assert by_type['feedback_generated']['generation']['effective_mode'] == 'heuristic'
    assert by_type['feedback_suppressed']['generation']['effective_mode'] == 'silent'
    assert by_type['task_completed']['files'] == reference
    mode_change = next(line for line in lines if line['type'] == 'mode_changed')
    assert by_type['feedback_generated']['id'] < mode_change['id'] < by_type['feedback_suppressed']['id']
