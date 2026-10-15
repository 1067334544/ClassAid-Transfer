# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Shared helpers for ClassAid tests. """

import json
from typing import TYPE_CHECKING, Any

from werkzeug.test import TestResponse

from gened.llm import LLM
from tests.conftest import AppClient

if TYPE_CHECKING:
    from collections.abc import Callable

TABLE_URL = '/instructor/config/table/classaid_task'

COUNTER_JAVA = """\
public class Counter {
    private int count;
    public void increment() { count += 2; }   // bug: should add 1
    public int get() { return count; }
}
"""
COUNTER_MAIN = """\
public class Main {
    public static void main(String[] args) {
        Counter c = new Counter();
        c.increment();
        System.out.println(c.get());
    }
}
"""
COUNTER_TEST = """\
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

public class CounterTest {
    // HIDDEN-TEST-SOURCE
    @Test void startsAtZero() { assertEquals(0, new Counter().get()); }
    @Test void incrementsByOne() { Counter c = new Counter(); c.increment(); assertEquals(1, c.get()); }
}
"""
COUNTER_FIXED = COUNTER_JAVA.replace('count += 2;', 'count += 1;')


def counter_spec(**overrides: Any) -> dict[str, Any]:
    spec = {
        'description': 'Fix **Counter** so that `increment()` adds one.',
        'examples': 'After one `increment()`, `get()` returns `1`.',
        'entry': 'Main',
        'files': [{'name': 'Counter.java', 'content': COUNTER_JAVA}, {'name': 'Main.java', 'content': COUNTER_MAIN}],
        'tests': [{'name': 'CounterTest.java', 'content': COUNTER_TEST}],
        'weights': {'CounterTest#startsAtZero': 1, 'CounterTest#incrementsByOne': 3},
    }
    return spec | overrides


def create_task(instructor: AppClient, title: str, spec: dict[str, Any] | None = None) -> TestResponse:
    return instructor.post(f'{TABLE_URL}/create', data={'name': title, 'task_json': json.dumps(spec or counter_spec())})


def set_available(instructor: AppClient, task_id: int, available: str = '2000-01-01') -> None:
    response = instructor.post(f'{TABLE_URL}/update_available', json={'item_id': task_id, 'available': available})
    assert response.status_code == 200


def task_ids(client: AppClient) -> list[int]:
    response = client.get('/classaid/api/tasks')
    assert response.status_code == 200
    return [t['id'] for t in response.json['tasks']]  # type: ignore[index]


def available_task(instructor: AppClient, title: str = 'Counter', spec: dict[str, Any] | None = None) -> int:
    """ Create a task and make it available to students; returns its id. """
    response = create_task(instructor, title, spec)
    assert response.status_code == 302
    task_id = max(task_ids(instructor))
    set_available(instructor, task_id)
    return task_id


class FakeLLM:
    """ Records every model call and answers based on the instructions in the system message. """

    def __init__(self) -> None:
        self.calls: list[list[dict[str, Any]]] = []
        self.selection = '{"selected_type": "technical", "reason": "Concrete logic bug with a failing test."}'
        self.on_generate: Callable[[], None] | None = None
        self.fail_generate = False

    async def get_completion(self, _llm: LLM, *, messages: list[dict[str, Any]], **_kwargs: Any) -> tuple[dict[str, Any], str]:
        self.calls.append(messages)
        system = messages[0]['content']
        if 'deciding which kind of feedback' in system:
            return {'id': 'sel'}, self.selection
        if self.on_generate:
            self.on_generate()
        if self.fail_generate:
            return {'error': 'boom'}, 'Error (APIError).  Something went wrong with this query.'
        if 'FEEDBACK MODE: HEURISTIC' in system:
            return {'id': 'h'}, 'What does count hold after one call to increment()?'
        if 'FEEDBACK MODE: TECHNICAL' in system:
            return {'id': 't'}, 'Change `count += 2;` to `count += 1;` because each call should add one.'
        return {'id': '?'}, 'unexpected prompt'
