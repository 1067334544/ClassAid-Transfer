# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" The bundled sample task (linked list remove): reference solution scores 5.0,
starter code scores less.
"""

import pytest
from flask import Flask

from components.classaid_tasks.data import get_task
from components.classaid_tasks.runs import execute
from components.classaid_tasks.samples import (
    add_sample_to_class,
    load_sample,
    sample_names,
)


def test_sample_is_valid_and_marked_unreviewed() -> None:
    assert 'linked_list_remove' in sample_names()
    task, reference = load_sample('linked_list_remove')
    assert len(task.spec.weights) >= 3
    assert {f.name for f in task.spec.files} == {'IntLinkedList.java', 'Main.java'}
    assert set(reference) == {'IntLinkedList.java', 'Main.java'}
    assert 'NOT REVIEWED BY AN INSTRUCTOR' in task.spec.files[0].content
    assert 'NOT REVIEWED BY AN INSTRUCTOR' in task.spec.tests[0].content


def test_add_sample_to_class_hidden(app: Flask) -> None:
    with app.app_context():
        item_id = add_sample_to_class('linked_list_remove', 1)
        assert get_task(item_id, 1, available_only=True) is None    # hidden from students
        task = get_task(item_id, 1, available_only=False)
    assert task is not None
    assert task.name == 'Linked list: remove a value (sample)'


def test_sample_task_cli(app: Flask) -> None:
    result = app.test_cli_runner().invoke(args=['sample-task', '2'])
    assert result.exit_code == 0, result.output
    assert 'NOT reviewed by an instructor' in result.output


@pytest.mark.usefixtures('jdk')
def test_reference_scores_full_and_starter_less(app: Flask) -> None:
    task, reference = load_sample('linked_list_remove')
    starter = {f.name: f.content for f in task.spec.files}
    with app.app_context():
        ref_result = execute(task, 'tests', reference)
        starter_result = execute(task, 'tests', starter)
        run_result = execute(task, 'run', reference)
    assert ref_result.score == 5.0, ref_result.tests
    assert starter_result.score is not None
    assert starter_result.score < 5.0
    assert run_result.stdout == 'before: [3, 5, 7] size=3\nremove(5) -> true\nafter:  [3, 7] size=2\n'
