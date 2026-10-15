# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" LocalRunner: runs student code in a local JVM subprocess.

NOT ISOLATED.  Student code runs with the permissions of the server process; the
only protections are resource limits (JVM heap/stack flags, ulimit CPU time and
file size, a wall-clock timeout).  For local development and automated tests
only -- see `check_local_runner_allowed()`.
"""

import os
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path

from .base import (
    STARTUP_SLACK_S,
    CodeRunner,
    ProcessOutcome,
    build_result,
    harness_input,
    new_nonce,
)
from .deps import check_junit, ensure_harness, java_bin
from .types import RunnerConfigError, RunRequest, RunResult

# Max size of any file the student process writes (stdout/stderr captures included).
OUTPUT_FILE_LIMIT = 1024 * 1024  # 1 MiB
_ULIMIT_BLOCK = 512  # POSIX `ulimit -f` unit


def check_local_runner_allowed(*, testing: bool, allow_env: str | None) -> None:
    """ Refuse to use the non-isolated runner outside development/testing configurations. """
    if testing or (allow_env or '').strip().lower() in ('1', 'true', 'yes'):
        return
    msg = (
        "The local code runner does not isolate student code and must not be used in a deployment "
        "with students.  Use CLASSAID_RUNNER=docker, or set CLASSAID_ALLOW_LOCAL_RUNNER=1 for local development."
    )
    raise RunnerConfigError(msg)


class LocalRunner(CodeRunner):
    isolated = False

    def __init__(self, java_home: Path, junit_jar: Path):
        self._java = java_bin(java_home)
        self._junit_jar = check_junit(junit_jar)
        self._harness_dir = ensure_harness(java_home, junit_jar)

    def _command(self, request: RunRequest, work_dir: Path) -> list[str]:
        limits = request.limits
        wall_s = limits.time_ms / 1000 + STARTUP_SLACK_S
        cpu_s = int(wall_s * 3) + 1  # the JVM uses several threads (JIT, GC)
        file_blocks = OUTPUT_FILE_LIMIT // _ULIMIT_BLOCK
        java_cmd = [
            str(self._java),
            f'-Xmx{limits.memory_mb}m',
            '-Xss1m',
            '-XX:MaxMetaspaceSize=128m',
            '-XX:+UseSerialGC',
            '-XX:TieredStopAtLevel=1',  # faster startup; student programs are short
            '-Dfile.encoding=UTF-8',
            f'-Djava.io.tmpdir={work_dir}',
            '-cp', f'{self._harness_dir}{os.pathsep}{self._junit_jar}',
            'ClassAidHarness',
        ]
        # ulimit via /bin/sh rather than preexec_fn, which is unsafe in multi-threaded servers.
        script = f'ulimit -c 0; ulimit -t {cpu_s}; ulimit -f {file_blocks}; exec "$@"'
        return ['/bin/sh', '-c', script, 'classaid-run', *java_cmd]

    def run(self, request: RunRequest, weights: Mapping[str, float] | None = None) -> RunResult:
        start = time.monotonic()
        run_dir = Path(tempfile.mkdtemp(prefix='classaid-run-'))
        work_dir = run_dir / 'work'      # student code's cwd and tmpdir
        work_dir.mkdir()
        nonce = new_nonce()
        result_path = run_dir / f'result-{nonce}.json'
        stdout_path = run_dir / 'stdout.txt'
        stderr_path = run_dir / 'stderr.txt'
        wall_s = request.limits.time_ms / 1000 + STARTUP_SLACK_S

        wall_timeout = False
        exit_code: int | None = None
        try:
            with stdout_path.open('wb') as out, stderr_path.open('wb') as err:
                proc = subprocess.Popen(  # noqa: S603 -- fixed command; student code is passed via stdin
                    self._command(request, work_dir),
                    stdin=subprocess.PIPE, stdout=out, stderr=err,
                    cwd=work_dir,
                    env={'PATH': '/usr/bin:/bin', 'HOME': str(work_dir), 'LANG': 'C.UTF-8'},
                    start_new_session=True,  # own process group, so a timeout kills everything
                )
                try:
                    proc.communicate(harness_input(request, str(result_path)), timeout=wall_s)
                except subprocess.TimeoutExpired:
                    wall_timeout = True
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                exit_code = proc.returncode

            return build_result(request, weights, ProcessOutcome(
                result_path=result_path,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                exit_code=exit_code,
                wall_timeout=wall_timeout,
                output_file_limit=OUTPUT_FILE_LIMIT,
                duration_ms=int((time.monotonic() - start) * 1000),
            ))
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)
