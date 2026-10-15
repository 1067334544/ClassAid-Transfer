# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Page routes for the Vue pages and the class home entry point. """

import json
import re
from collections.abc import Callable

import pytest
from flask import Flask

from classaid.assets import MANIFEST
from gened.db import get_db
from tests.conftest import AppClient

from .helpers import available_task

pytestmark = pytest.mark.skipif(not MANIFEST.exists(), reason="Frontend not built: run `pnpm --dir frontend build`.")


def bootstrap_of(html: str) -> dict[str, object]:
    match = re.search(r'<script id="classaid-bootstrap" type="application/json">(.*?)</script>', html, re.DOTALL)
    assert match
    data: dict[str, object] = json.loads(match.group(1))
    return data


def test_class_home_offers_programming_tasks(login_as: Callable[..., AppClient]) -> None:
    """ Programming Tasks is the class's only tool, so Gen-Ed's class home goes straight to it. """
    response = login_as('student1').get('/classes/home')
    assert response.status_code == 302
    assert response.location == '/classaid/tasks'


def test_task_list_page(login_as: Callable[..., AppClient]) -> None:
    response = login_as('student1').get('/classaid/tasks')
    assert response.status_code == 200
    data = bootstrap_of(response.text)
    assert (data['page'], data['role'], data['classId'], data['apiBase']) == ('task_list', 'student', 1, '/classaid/api')
    assert '/static/dist/assets/workspace-' in response.text


def test_workspace_page(login_as: Callable[..., AppClient]) -> None:
    task_id = available_task(login_as('instructor'))
    response = login_as('student1').get(f'/classaid/tasks/{task_id}')
    assert response.status_code == 200
    data = bootstrap_of(response.text)
    assert (data['page'], data['taskId'], data['taskListUrl']) == ('workspace', task_id, '/classaid/tasks')


def test_modes_page_instructor_only(login_as: Callable[..., AppClient]) -> None:
    assert login_as('instructor').get('/classaid/modes').status_code == 200
    assert login_as('student1').get('/classaid/modes').status_code == 403
    assert login_as('student1').get('/classaid/styleguide').status_code == 403


def test_pages_require_login(client: AppClient) -> None:
    response = client.get('/classaid/tasks')
    assert response.status_code == 302
    assert '/auth/login' in response.location


def test_task_list_api_includes_own_progress(login_as: Callable[..., AppClient]) -> None:
    task_id = available_task(login_as('instructor'))
    student = login_as('student1')
    tasks = student.get('/classaid/api/tasks').json
    assert tasks is not None
    assert tasks['tasks'] == [{'id': task_id, 'title': 'Counter', 'status': 'not_started', 'score': None}]
    student.get(f'/classaid/api/tasks/{task_id}')
    tasks = student.get('/classaid/api/tasks').json
    assert tasks is not None
    assert tasks['tasks'][0]['status'] == 'in_progress'
    # another student's progress is not mixed in
    other = login_as('student2').get('/classaid/api/tasks').json
    assert other is not None
    assert other['tasks'][0]['status'] == 'not_started'


def test_login_lands_on_tasks_even_without_class_key(app: Flask, client: AppClient) -> None:
    """ Gen-Ed's class home requires a class API key; ClassAid's landing page does not, so students
    can work (and see the "not configured" notice only in the chat) without one. """
    with app.app_context():
        get_db().execute("UPDATE classes_user SET llm_api_key='' WHERE class_id=1")
        get_db().execute("UPDATE users SET last_class_id=1 WHERE id=102")   # as after joining the class
        get_db().commit()
    response = client.login('student1', 'student1pw')
    assert response.status_code == 302
    assert response.location == '/classaid/tasks'
    assert client.get('/classaid/tasks').status_code == 200


def test_page_without_active_class_redirects_to_class_choice(login_as: Callable[..., AppClient]) -> None:
    admin = login_as('admin', class_id=None)
    response = admin.get('/classaid/tasks')
    assert response.status_code == 302
    assert response.location == '/profile/'
