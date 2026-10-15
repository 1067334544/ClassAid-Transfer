# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Data types shared by all code runners.

`RunResult` is the single result format that the rest of ClassAid (student
output panel, scoring, activity log, later error analysis) relies on.  Every
runner must produce identical results for the same code, apart from
environment-dependent fields such as timings.
"""

from typing import Literal

import msgspec

RunKind = Literal['run', 'tests']

RunStatus = Literal[
    'ok',               # program finished / test run completed (individual tests may still fail)
    'compile_error',
    'runtime_error',    # uncaught exception (incl. StackOverflowError) in `run` mode
    'timeout',          # wall-clock limit exceeded
    'memory_exceeded',  # OutOfMemoryError or killed for memory
    'exited',           # student code called System.exit()
    'internal_error',   # runner/harness failure, not attributable to student code
]

LimitKind = Literal['time', 'memory', 'output']

TestStatus = Literal['passed', 'failed', 'error', 'timeout', 'skipped', 'not_run']


class Limits(msgspec.Struct, kw_only=True, frozen=True):
    time_ms: int = 5000           # wall-clock limit for student code (run: main; tests: whole test run)
    test_timeout_ms: int = 2000   # per-test limit within a test run
    memory_mb: int = 256          # JVM heap
    output_bytes: int = 64_000    # stdout/stderr returned to callers (each)
    max_frames: int = 20          # stack frames reported per exception


class RunRequest(msgspec.Struct, kw_only=True, frozen=True):
    kind: RunKind
    files: dict[str, str]                         # student files: {"LinkedList.java": "..."}
    entry: str = 'Main'                           # class whose main() is run in 'run' mode
    tests: dict[str, str] = msgspec.field(default_factory=dict)   # instructor tests (used in 'tests' mode)
    limits: Limits = msgspec.field(default_factory=Limits)


class Diagnostic(msgspec.Struct, kw_only=True, frozen=True):
    kind: Literal['error', 'warning']
    file: str | None          # None for diagnostics located in instructor tests
    line: int | None
    column: int | None
    in_tests: bool
    message: str


class CompileResult(msgspec.Struct, kw_only=True, frozen=True):
    ok: bool
    diagnostics: list[Diagnostic]


class Frame(msgspec.Struct, kw_only=True, frozen=True):
    file: str
    line: int
    method: str
    class_: str = msgspec.field(name='class')


class ExceptionInfo(msgspec.Struct, kw_only=True, frozen=True):
    type: str
    message: str | None
    frames: list[Frame]       # only frames located in student files


class TestResult(msgspec.Struct, kw_only=True, frozen=True):
    id: str                   # "TestClass#method": key for instructor-defined weights
    name: str                 # display name
    status: TestStatus
    message: str | None = None
    exception: ExceptionInfo | None = None


class RunResult(msgspec.Struct, kw_only=True, frozen=True):
    kind: RunKind
    status: RunStatus
    compile: CompileResult | None          # None only if the harness never reported (internal error, kill)
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool
    exit_code: int | None
    limit_exceeded: LimitKind | None
    exception: ExceptionInfo | None = None
    tests: list[TestResult] | None = None  # 'tests' mode only
    score: float | None = None             # 'tests' mode only: 0.0-5.0
    duration_ms: int = 0                   # environment-dependent
    internal_error: str | None = None      # diagnostic text for 'internal_error'


class HarnessResult(msgspec.Struct, kw_only=True, frozen=True):
    """ The JSON object written by ClassAidHarness.java. """
    mode: RunKind
    status: Literal['ok', 'compile_error', 'runtime_error', 'timeout', 'exited', 'internal_error']
    compile: CompileResult | None = None
    exception: ExceptionInfo | None = None
    tests: list[TestResult] | None = None
    harness_ms: int = 0


class RunnerConfigError(Exception):
    pass
