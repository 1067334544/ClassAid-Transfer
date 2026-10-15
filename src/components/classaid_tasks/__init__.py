# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

from gened.components import GenEdComponent

from .api import bp
from .config_table import tasks_config_table
from .data import TasksDeletionHandler

gened_component = GenEdComponent(
    package=__package__,
    name="classaid_tasks",
    display_name="Programming Tasks",
    description="Work on Java programming tasks: edit and run your code, run the tests, and ask the TA Agent for help.",
    blueprint=bp,
    icon="svg_tool_case",
    main_endpoint="classaid_pages.task_list",
    config_table=tasks_config_table,
    deletion_handler=TasksDeletionHandler,
    schema_file="schema.sql",
    migrations_dir="migrations",
    always_enabled=True,  # core of the ClassAid application; not toggleable per class
)

__all__ = [
    "gened_component",
]
