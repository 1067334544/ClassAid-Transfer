# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Bundled sample tasks for verifying the ClassAid workflow.

Samples are NOT reviewed by an instructor and are not selected research tasks.
Each sample directory holds task.json (title, description, examples, entry,
weights), starter/*.java, tests/*.java, and reference/*.java (a reference
solution that is used only for verification and never stored in the task).
"""

from pathlib import Path

import click
import msgspec
from flask.cli import with_appcontext

from gened.db import get_db

from .data import ITEM_TYPE
from .model import TaskConfig, TaskFile, TaskSpec, validate_spec

SAMPLES_DIR = Path(__file__).resolve().parent / 'sample_tasks'


class _SampleMeta(msgspec.Struct, kw_only=True):
    title: str
    review_status: str
    description: str
    examples: str
    entry: str
    weights: dict[str, float]


def _java_files(directory: Path) -> list[TaskFile]:
    return [TaskFile(p.name, p.read_text(encoding='utf-8')) for p in sorted(directory.glob('*.java'))]


def load_sample(name: str) -> tuple[TaskConfig, dict[str, str]]:
    """ Returns the sample task and its reference solution files (starter files with the
    reference versions substituted).
    """
    directory = SAMPLES_DIR / name
    meta = msgspec.json.decode((directory / 'task.json').read_bytes(), type=_SampleMeta)
    spec = TaskSpec(
        description=meta.description,
        examples=meta.examples,
        entry=meta.entry,
        files=_java_files(directory / 'starter'),
        tests=_java_files(directory / 'tests'),
        weights=meta.weights,
    )
    if problems := validate_spec(spec):
        msg = f"Invalid sample task {name}: {problems}"
        raise ValueError(msg)
    reference = {f.name: f.content for f in spec.files} | {f.name: f.content for f in _java_files(directory / 'reference')}
    return TaskConfig(name=meta.title, spec=spec), reference


def sample_names() -> list[str]:
    return sorted(p.name for p in SAMPLES_DIR.iterdir() if (p / 'task.json').is_file())


def add_sample_to_class(name: str, class_id: int) -> int:
    """ Insert the sample as a (hidden) task in the class; returns the new item id. """
    task, _reference = load_sample(name)
    db = get_db()
    cur = db.execute("""
        INSERT INTO config_items (class_id, item_type, name, config, available, class_order)
        VALUES (?, ?, ?, ?, '9999-12-31', (SELECT COALESCE(MAX(class_order)+1, 0) FROM config_items WHERE class_id=? AND item_type=?))
    """, [class_id, ITEM_TYPE, task.name, task.to_json(), class_id, ITEM_TYPE])
    db.commit()
    item_id = cur.lastrowid
    assert item_id is not None
    return item_id


@click.command('sample-task')
@click.argument('class_id', type=int)
@click.option('--name', default='linked_list_remove', type=click.Choice(sample_names()), show_default=True)
@with_appcontext
def sample_task_command(class_id: int, name: str) -> None:
    """ Add a bundled sample task (hidden; NOT instructor-reviewed) to a class. """
    item_id = add_sample_to_class(name, class_id)
    click.secho(f"Added sample task '{name}' to class {class_id} as task {item_id} (hidden until an available date is set).", fg='green')
    click.secho("Sample tasks are NOT reviewed by an instructor; use them only to verify the workflow.", fg='yellow')
