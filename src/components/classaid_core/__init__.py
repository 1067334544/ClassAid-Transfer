# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Shared ClassAid infrastructure used by the other ClassAid components:
the append-only activity log, code snapshots, and background jobs.
"""

from gened.components import GenEdComponent

from .data import CoreDeletionHandler, events_data_source
from .jobs import JobOwner, submit_job, wait_for_job

gened_component = GenEdComponent(
    package=__package__,
    name="classaid_core",
    display_name="ClassAid Activity",
    description="ClassAid activity log, code snapshots, and background jobs.",
    data_source=events_data_source,
    deletion_handler=CoreDeletionHandler,
    schema_file="schema.sql",
    migrations_dir="migrations",
    always_enabled=True,  # core of the ClassAid application; not toggleable per class
)

__all__ = [
    "JobOwner",
    "gened_component",
    "submit_job",
    "wait_for_job",
]
