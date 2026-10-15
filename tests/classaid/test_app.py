# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

from collections.abc import Callable

import pytest
from flask import Flask

from gened.component_registry import get_registered_components
from tests.conftest import AppClient


def test_app_is_classaid(app: Flask) -> None:
    assert app.config['APPLICATION_TITLE'] == 'ClassAid'
    assert str(app.config['DATABASE']).endswith('classaid_test.db')


def test_registered_components(app: Flask) -> None:
    """ ClassAid must not expose CodeHelp's query/tutor interfaces, which would bypass feedback modes. """
    with app.app_context():
        names = {c.name for c in get_registered_components()}
    assert names == {'classaid_core', 'classaid_tasks', 'classaid_agent'}


def test_landing_anonymous(client: AppClient) -> None:
    response = client.get('/')
    assert response.status_code == 200
    assert '<title>ClassAid</title>' in response.text


@pytest.mark.parametrize('username', ['student1', 'instructor'])
def test_login_and_class_home(login_as: Callable[..., AppClient], username: str) -> None:
    """ With Programming Tasks as the class's only tool, Gen-Ed's class home goes straight to it. """
    client = login_as(username)
    response = client.get('/classes/home')
    assert response.status_code == 302
    assert response.location == '/classaid/tasks'


def test_codehelp_routes_absent(login_as: Callable[..., AppClient]) -> None:
    client = login_as('student1')
    assert client.get('/help/').status_code == 404
    assert client.get('/tutor/new').status_code == 404
