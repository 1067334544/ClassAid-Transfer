# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Code runners: compile and run student Java code and instructor JUnit tests.

Configuration (environment variables, copied into app.config by `init_app`):
  CLASSAID_RUNNER              'docker' (default) or 'local'
  CLASSAID_JAVA_HOME           JDK 21 home (local runner)
  CLASSAID_JUNIT_JAR           JUnit standalone jar (local runner; default: runner/lib/)
  CLASSAID_ALLOW_LOCAL_RUNNER  must be '1' to use the local runner outside of TESTING
  CLASSAID_DOCKER_IMAGE        image for the docker runner (default: classaid-runner:<version>)
"""

import os
import threading
from pathlib import Path

import click
from flask import Flask, current_app

from .base import CodeRunner
from .deps import DEFAULT_JUNIT_JAR, fetch_junit
from .docker import DEFAULT_IMAGE, DockerRunner
from .local import LocalRunner, check_local_runner_allowed
from .scoring import score_tests
from .types import Limits, RunnerConfigError, RunRequest, RunResult

_CONFIG_VARS = {
    'CLASSAID_RUNNER': 'docker',
    'CLASSAID_JAVA_HOME': None,
    'CLASSAID_JUNIT_JAR': str(DEFAULT_JUNIT_JAR),
    'CLASSAID_ALLOW_LOCAL_RUNNER': None,
    'CLASSAID_DOCKER_IMAGE': DEFAULT_IMAGE,
}

_EXT_KEY = 'classaid_runner'
_lock = threading.Lock()


def init_app(app: Flask) -> None:
    """ Load runner configuration and validate it.  Raises RunnerConfigError (so the
    application refuses to start) if the non-isolated local runner is configured
    outside of a development/testing configuration.
    """
    for var, default in _CONFIG_VARS.items():
        if var not in app.config:
            app.config[var] = os.environ.get(var, default)

    kind = app.config['CLASSAID_RUNNER']
    if kind == 'local':
        check_local_runner_allowed(
            testing=bool(app.config.get('TESTING')),
            allow_env=app.config['CLASSAID_ALLOW_LOCAL_RUNNER'],
        )
    elif kind != 'docker':
        msg = f"Unknown CLASSAID_RUNNER: {kind!r} (expected 'docker' or 'local')"
        raise RunnerConfigError(msg)

    app.cli.add_command(runner_deps_command)


def _build_runner(config: dict[str, object]) -> CodeRunner:
    if config['CLASSAID_RUNNER'] == 'local':
        java_home = config['CLASSAID_JAVA_HOME']
        if not java_home:
            msg = "CLASSAID_JAVA_HOME must be set to a JDK 21 home directory to use the local runner."
            raise RunnerConfigError(msg)
        return LocalRunner(Path(str(java_home)), Path(str(config['CLASSAID_JUNIT_JAR'])))
    return DockerRunner(str(config['CLASSAID_DOCKER_IMAGE']))


def get_runner() -> CodeRunner:
    """ The configured runner for the current app (created on first use). """
    app = current_app._get_current_object()  # type: ignore[attr-defined]  # noqa: SLF001 -- standard Flask idiom
    with _lock:
        if _EXT_KEY not in app.extensions:
            app.extensions[_EXT_KEY] = _build_runner(dict(app.config))
        runner: CodeRunner = app.extensions[_EXT_KEY]
    return runner


@click.command('runner-deps')
def runner_deps_command() -> None:
    """ Download the pinned JUnit jar used by the local code runner. """
    path = fetch_junit()
    click.secho(f"JUnit jar ready: {path}", fg='green')


__all__ = [
    "CodeRunner",
    "DockerRunner",
    "Limits",
    "LocalRunner",
    "RunRequest",
    "RunResult",
    "RunnerConfigError",
    "get_runner",
    "init_app",
    "score_tests",
]
