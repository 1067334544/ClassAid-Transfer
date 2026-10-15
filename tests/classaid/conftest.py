# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Fixtures for ClassAid tests.

Overrides the root `app` fixture so that `client` and other fixtures built on
it use the ClassAid application (with its own database and test data) rather
than CodeHelp.
"""

import os
import tempfile
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any

import openai
import pytest
from flask import Flask

import classaid
from gened.db import get_db
from gened.db_admin import init_db
from gened.llm import LLM
from gened.testing.mocks import mock_async_completion, mock_completion
from tests.conftest import AppClient

from .helpers import FakeLLM

_test_sql = Path(__file__).parent / 'test_data.sql'
_test_data_sql = _test_sql.read_text(encoding='utf8')

# ids from test_data.sql
CLASS_A = 1
CLASS_B = 2


def java_home() -> str | None:
    """ A JDK for the local code runner, from CLASSAID_JAVA_HOME or JAVA_HOME (None if unavailable). """
    for var in ('CLASSAID_JAVA_HOME', 'JAVA_HOME'):
        if (value := os.environ.get(var)) and (Path(value) / 'bin' / 'javac').is_file():
            return value
    return None


@pytest.fixture
def jdk() -> str:
    """ Skip tests that run student code when no JDK is configured. """
    home = java_home()
    if home is None:
        pytest.skip("No JDK: set CLASSAID_JAVA_HOME to a JDK 21 home to run code-execution tests.")
    return home


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> Generator[Flask]:
    """ A ClassAid application with a temporary, populated database.
    OpenAI completions are always mocked: ClassAid tests never send real requests.
    """
    monkeypatch.setattr(openai.resources.chat.Completions, "create", mock_completion(0.0))
    monkeypatch.setattr(openai.resources.chat.AsyncCompletions, "create", mock_async_completion(0.0))

    with tempfile.TemporaryDirectory() as temp_dir:
        instance_path = Path(temp_dir)
        app = classaid.create_app(
            test_config={
                'TESTING': True,
                'DATABASE': str(instance_path / 'classaid_test.db'),
                'SYSTEM_API_KEY': 'invalid',
                # Local (non-isolated) runner for tests; without a JDK, runs fail as "runner unavailable".
                'CLASSAID_RUNNER': 'local',
                'CLASSAID_JAVA_HOME': java_home() or '',
            },
            instance_path=instance_path,
        )

        with app.app_context():
            init_db()
            get_db().executescript(_test_data_sql)

        yield app


@pytest.fixture
def login_as(app: Flask) -> Callable[..., AppClient]:
    """ Factory: a new client logged in as the given local user (password '<username>pw'),
    with the given class (default: CS2-A) set as the active class.
    Each call returns an independent client (separate session), so tests can
    hold several users' sessions at once.
    """
    def _login(username: str, class_id: int | None = CLASS_A) -> AppClient:
        client = AppClient(app.test_client())
        response = client.login(username, f'{username}pw')
        assert response.status_code == 302, f"login failed for {username}"
        if class_id is not None:
            response = client.get(f'/classes/switch/{class_id}')
            assert response.status_code == 302
        return client

    return _login


@pytest.fixture
def fake_llm(monkeypatch: pytest.MonkeyPatch) -> FakeLLM:
    """ Replace LLM completions with a recording fake (see helpers.FakeLLM). """
    fake = FakeLLM()

    async def patched(self: LLM, **kwargs: Any) -> tuple[dict[str, Any], str]:
        return await fake.get_completion(self, **kwargs)

    monkeypatch.setattr(LLM, 'get_completion', patched)
    return fake
