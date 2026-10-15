# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Shared logic for runners that execute ClassAidHarness in a JVM and collect
its result file plus the program's stdout/stderr.
"""

import secrets
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import msgspec

from .scoring import score_tests
from .types import (
    HarnessResult,
    LimitKind,
    RunRequest,
    RunResult,
    RunStatus,
)

# Extra wall-clock time on top of the student-code limit for JVM startup and compilation.
STARTUP_SLACK_S = 10


class CodeRunner(ABC):
    """ Compiles and runs student Java code (and instructor JUnit tests) in some environment. """

    #: True only for runners that isolate student code (no network, no host file access, ...).
    isolated: bool = False

    @abstractmethod
    def run(self, request: RunRequest, weights: Mapping[str, float] | None = None) -> RunResult:
        """ Run the request.  In 'tests' mode, the result is scored using `weights`
        (test id -> weight; see scoring.score_tests).
        """


def new_nonce() -> str:
    return secrets.token_hex(16)


def harness_input(request: RunRequest, result_path: str) -> bytes:
    limits = request.limits
    return msgspec.json.encode({
        'mode': request.kind,
        'files': request.files,
        'tests': request.tests if request.kind == 'tests' else {},
        'entry': request.entry,
        'time_limit_ms': limits.time_ms,
        'test_timeout_ms': limits.test_timeout_ms,
        'max_frames': limits.max_frames,
        'result_path': result_path,
    })


def read_capped(path: Path, cap: int) -> tuple[str, bool, int]:
    """ Read at most `cap` bytes of a captured output file.
    Returns (text, truncated, total_size).
    """
    if not path.exists():
        return '', False, 0
    size = path.stat().st_size
    with path.open('rb') as f:
        data = f.read(cap)
    return data.decode('utf-8', errors='replace'), size > cap, size


@dataclass(frozen=True, kw_only=True)
class ProcessOutcome:
    """ What a runner observed when executing the harness process. """
    result_path: Path
    stdout_path: Path
    stderr_path: Path
    exit_code: int | None
    wall_timeout: bool
    output_file_limit: int  # max size of a captured output file (enforced with ulimit -f)
    duration_ms: int


def build_result(request: RunRequest, weights: Mapping[str, float] | None, outcome: ProcessOutcome) -> RunResult:
    """ Translate the harness result file (if any) and process outcome into a RunResult. """
    result_path = outcome.result_path
    exit_code = outcome.exit_code
    cap = request.limits.output_bytes
    stdout, stdout_trunc, stdout_size = read_capped(outcome.stdout_path, cap)
    stderr, stderr_trunc, stderr_size = read_capped(outcome.stderr_path, cap)
    output_limit_hit = max(stdout_size, stderr_size) >= outcome.output_file_limit

    harness: HarnessResult | None = None
    internal_error: str | None = None
    if result_path.exists():
        try:
            harness = msgspec.json.decode(result_path.read_bytes(), type=HarnessResult)
        except msgspec.DecodeError as e:
            internal_error = f"Invalid harness result: {e}"

    status: RunStatus
    limit: LimitKind | None = None
    if harness is not None:
        status = harness.status
        if harness.exception and harness.exception.type == 'java.lang.OutOfMemoryError':
            status, limit = 'memory_exceeded', 'memory'
        elif status == 'timeout':
            limit = 'time'
    elif outcome.wall_timeout:
        status, limit = 'timeout', 'time'
    elif 'OutOfMemoryError' in stderr:
        status, limit = 'memory_exceeded', 'memory'
    else:
        status = 'internal_error'
        internal_error = internal_error or f"No result from harness (exit code {exit_code}).\n{stderr[-2000:]}"

    if limit is None and (output_limit_hit or stdout_trunc or stderr_trunc):
        limit = 'output'

    tests = harness.tests if harness else None
    score = None
    if request.kind == 'tests':
        # Compile errors, timeouts, etc. still produce a score: missing/failed tests earn nothing.
        score = score_tests(tests, weights or {})

    return RunResult(
        kind=request.kind,
        status=status,
        compile=harness.compile if harness else None,
        stdout=stdout,
        stderr=stderr,
        stdout_truncated=stdout_trunc,
        stderr_truncated=stderr_trunc,
        exit_code=exit_code,
        limit_exceeded=limit,
        exception=harness.exception if harness else None,
        tests=tests,
        score=score,
        duration_ms=outcome.duration_ms,
        internal_error=internal_error,
    )
