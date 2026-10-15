# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

from gened.components import GenEdComponent

from .api import bp
from .data import AgentDeletionHandler

gened_component = GenEdComponent(
    package=__package__,
    name="classaid_agent",
    display_name="ClassAid TA Agent",
    description="Instructor-controlled feedback modes and AI feedback for students.",
    blueprint=bp,
    deletion_handler=AgentDeletionHandler,
    schema_file="schema.sql",
    migrations_dir="migrations",
    always_enabled=True,  # core of the ClassAid application; not toggleable per class
)

__all__ = [
    "gened_component",
]
