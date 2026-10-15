# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" CSRF hardening for the JSON API: JSON-only bodies and same-origin Origin headers. """

from collections.abc import Callable

from tests.conftest import AppClient

from .helpers import COUNTER_JAVA, COUNTER_MAIN, available_task

FILES = {'Counter.java': COUNTER_JAVA, 'Main.java': COUNTER_MAIN}


def test_cross_site_origin_rejected(login_as: Callable[..., AppClient]) -> None:
    """ A request from another site (browser-sent Origin) is rejected, even with a valid session. """
    instructor = login_as('instructor')
    response = instructor.put('/classaid/api/modes/class', json={'mode': 'silent'}, headers={'Origin': 'https://evil.example'})
    assert response.status_code == 403
    assert response.json == {'error': 'Cross-site request rejected.'}
    # the mode was not changed
    modes = instructor.get('/classaid/api/modes').json
    assert modes is not None
    assert modes['class_mode'] == 'heuristic'


def test_same_origin_accepted(login_as: Callable[..., AppClient]) -> None:
    instructor = login_as('instructor')
    response = instructor.put('/classaid/api/modes/class', json={'mode': 'auto'}, headers={'Origin': 'http://localhost'})
    assert response.status_code == 200


def test_form_submission_rejected(login_as: Callable[..., AppClient]) -> None:
    """ A cross-site HTML form (urlencoded body, no JSON) cannot drive state-changing endpoints. """
    instructor = login_as('instructor')
    task_id = available_task(instructor)
    student = login_as('student1')
    student.get(f'/classaid/api/tasks/{task_id}')
    for url, data in [
        ('/classaid/api/modes/class', {'mode': 'silent'}),
        (f'/classaid/api/tasks/{task_id}/ask', {'question': 'hi'}),
        (f'/classaid/api/tasks/{task_id}/run', {'files': 'x'}),
    ]:
        client = instructor if 'modes' in url else student
        response = client.post(url, data=data) if 'modes' not in url else client.put(url, data=data)
        assert response.status_code == 415, url


def test_reads_do_not_require_json(login_as: Callable[..., AppClient]) -> None:
    assert login_as('student1').get('/classaid/api/tasks').status_code == 200
