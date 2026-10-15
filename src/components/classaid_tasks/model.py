# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Java task definitions, stored as Gen-Ed config items (item_type 'classaid_task'). """

import re
from typing import Self

import msgspec
from werkzeug.datastructures import ImmutableMultiDict
from werkzeug.exceptions import BadRequest

from gened.class_config.types import ConfigItem

JAVA_FILE_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*\.java$')
TEST_ID_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*#[A-Za-z_][A-Za-z0-9_]*$')
MAX_FILE_CHARS = 50_000


class TaskFile(msgspec.Struct, frozen=True):
    name: str      # e.g. "LinkedList.java" (default package; file name = public class name)
    content: str


class TaskSpec(msgspec.Struct, kw_only=True, frozen=True):
    """ The task content edited by instructors (submitted as JSON from the edit form). """
    description: str = ''                                   # Markdown, shown to students
    examples: str = ''                                      # Markdown: sample input/output, shown to students
    entry: str = 'Main'                                     # class whose main() Run executes
    files: list[TaskFile] = msgspec.field(default_factory=list)    # starter code, shown to students
    tests: list[TaskFile] = msgspec.field(default_factory=list)    # instructor JUnit tests, never shown to students
    weights: dict[str, float] = msgspec.field(default_factory=dict)  # "TestClass#method" -> weight (unlisted: 1)


def _file_problems(spec: TaskSpec) -> list[str]:
    all_files = [*spec.files, *spec.tests]
    names = [f.name for f in all_files]
    problems = [f"Invalid Java file name: {name!r} (expected e.g. 'LinkedList.java')." for name in names if not JAVA_FILE_RE.match(name)]
    if len(set(names)) != len(names):
        problems.append("File names must be unique across starter files and test files.")
    problems.extend(f"{f.name} is too long (max {MAX_FILE_CHARS:,} characters)." for f in all_files if len(f.content) > MAX_FILE_CHARS)
    return problems


def _weight_problems(spec: TaskSpec) -> list[str]:
    problems = [f"Invalid test id: {test_id!r} (expected 'TestClass#method')." for test_id in spec.weights if not TEST_ID_RE.match(test_id)]
    problems.extend(f"Weight for {test_id} must be positive." for test_id, weight in spec.weights.items() if not weight > 0)
    return problems


def validate_spec(spec: TaskSpec) -> list[str]:
    """ Returns a list of problems (empty if the spec is valid). """
    problems = []
    if not spec.files:
        problems.append("At least one starter code file is required.")
    if not spec.tests:
        problems.append("At least one test file is required.")
    problems.extend(_file_problems(spec))
    if spec.entry and f"{spec.entry}.java" not in {f.name for f in spec.files}:
        problems.append(f"Entry class {spec.entry!r} must be one of the starter files.")
    problems.extend(_weight_problems(spec))
    return problems


class TaskConfig(ConfigItem):
    """ A ClassAid task.  `name` (the config item name) is the task title. """
    spec: TaskSpec = msgspec.field(default_factory=TaskSpec)

    @classmethod
    def initial(cls) -> Self:
        return cls(name='', spec=TaskSpec(
            files=[TaskFile('Main.java', 'public class Main {\n    public static void main(String[] args) {\n    }\n}\n')],
            tests=[TaskFile('MainTest.java', 'import org.junit.jupiter.api.Test;\nimport static org.junit.jupiter.api.Assertions.*;\n\npublic class MainTest {\n    @Test\n    void example() {\n    }\n}\n')],
        ))

    @classmethod
    def from_request_form(cls, form: ImmutableMultiDict[str, str]) -> Self:
        """ Build from the edit form: 'name' plus the task content as JSON in 'task_json'.
        The form validates in the browser; this is the server-side backstop.
        """
        try:
            spec = msgspec.json.decode(form['task_json'], type=TaskSpec)
        except (KeyError, msgspec.DecodeError, msgspec.ValidationError) as e:
            msg = f"Invalid task data: {e}"
            raise BadRequest(msg) from e
        if problems := validate_spec(spec):
            raise BadRequest("Invalid task: " + "  ".join(problems))
        name = form.get('name', '').strip()
        if not name:
            msg = "Task title is required."
            raise BadRequest(msg)
        return cls(name=name, spec=spec)

    def spec_builtins(self) -> dict[str, object]:
        """ The spec as plain JSON-able data (for the edit form). """
        data: dict[str, object] = msgspec.to_builtins(self.spec)
        return data

    def student_view(self) -> dict[str, object]:
        """ What students may see of the task definition: never the tests. """
        return {
            'id': self.row_id,
            'title': self.name,
            'description': self.spec.description,
            'examples': self.spec.examples,
            'entry': self.spec.entry,
            'starter_files': {f.name: f.content for f in self.spec.files},
        }
