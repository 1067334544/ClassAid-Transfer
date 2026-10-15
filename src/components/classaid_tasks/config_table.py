# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

from jinja2 import Environment

from gened.class_config.types import ConfigTable

from .model import TaskConfig

tasks_help = Environment(autoescape=True).from_string("""\
  <p>Java programming tasks for the ClassAid student workspace.  Each task has starter code that students edit and run, and instructor JUnit tests (never shown to students) that score their work from 0 to 5 using per-test weights.</p>
  <p>New tasks are hidden from students until you set an available date.</p>
""")

tasks_config_table = ConfigTable(
    config_item_class=TaskConfig,
    name='classaid_task',
    display_name='task',
    display_name_plural='tasks',
    help_text=tasks_help,
    edit_form_template='classaid_task_edit_form.html',
)
