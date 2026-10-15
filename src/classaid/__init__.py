# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

from pathlib import Path
from typing import Any

from flask.app import Flask

from components import classaid_agent, classaid_core, classaid_tasks
from components.classaid_tasks import runner
from components.classaid_tasks.samples import sample_task_command
from gened.base import GenEdAppBuilder

from . import pages


def create_app(test_config: dict[str, Any] | None = None, instance_path: Path | None = None) -> Flask:
    ''' Flask app factory.  Create and configure the ClassAid application. '''

    # App-specific configuration
    app_config = dict(
        APPLICATION_TITLE='ClassAid',
        APPLICATION_AUTHOR='ClassAid-Transfer contributors',
        FAVICON='icon.svg',
        # Land on the task list, not Gen-Ed's class home: class home requires a class API key,
        # but students must be able to work (edit, run, test) even when AI feedback is not configured.
        DEFAULT_LOGIN_ENDPOINT='classaid_pages.task_list',
        SUPPORT_EMAIL='',
        DATABASE_NAME='classaid.db',  # will be combined with app.instance_path in gened.create_app_base()
        # ClassAid does not use per-user query tokens; class API keys are required for students.
        DEFAULT_TOKENS=0,
        # Data retention length (prune user data with no activity for this period of time)
        RETENTION_TIME_DAYS=2*365,  # 2 years
    )

    # load test config if provided, potentially overriding above config
    if test_config is not None:
        app_config = app_config | test_config

    # create the base application
    builder = GenEdAppBuilder(__name__, app_config, instance_path)
    # CodeHelp's components (code_queries, tutors, and code_contexts, which only they use) are
    # intentionally *not* included: students must not be able to bypass instructor-controlled
    # feedback modes through the older CodeHelp interfaces.
    builder.add_component(classaid_core.gened_component)
    builder.add_component(classaid_tasks.gened_component)
    builder.add_component(classaid_agent.gened_component)
    app = builder.build()

    # Code-runner configuration; refuses to start with a non-isolated runner outside dev/testing.
    runner.init_app(app)
    app.cli.add_command(sample_task_command)
    app.register_blueprint(pages.bp)

    return app
