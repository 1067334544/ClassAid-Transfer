# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" DockerRunner: runs student code in a throwaway, locked-down container.

This is the only runner that may be used with students.  Each run gets a fresh
container from an image containing JDK 21, the compiled ClassAidHarness, and the
pinned JUnit jar (see container/Dockerfile) with:
  - no network (--network none)
  - read-only root filesystem; writable tmpfs only at /work (cwd, java.io.tmpdir)
  - non-root user, all capabilities dropped, no-new-privileges
  - memory, CPU and process-count limits
The harness result file is written to a per-run host directory mounted at /out.
"""

import shutil
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
from .deps import JUNIT_VERSION
from .types import RunnerConfigError, RunRequest, RunResult

DEFAULT_IMAGE = f'classaid-runner:junit-{JUNIT_VERSION}'
OUTPUT_FILE_LIMIT = 1024 * 1024  # 1 MiB, enforced via ulimit inside the container
_ULIMIT_BLOCK = 512
CONTAINER_UID = '65534:65534'  # nobody:nogroup


class DockerRunner(CodeRunner):
    isolated = True

    def __init__(self, image: str, docker: str = 'docker'):
        docker_path = shutil.which(docker)
        if docker_path is None:
            msg = "The docker runner requires the `docker` CLI, which was not found on PATH."
            raise RunnerConfigError(msg)
        self._docker = docker_path
        self._image = image

    def _command(self, request: RunRequest, name: str, out_dir: Path) -> list[str]:
        limits = request.limits
        wall_s = limits.time_ms / 1000 + STARTUP_SLACK_S
        cpu_s = int(wall_s * 3) + 1
        file_blocks = OUTPUT_FILE_LIMIT // _ULIMIT_BLOCK
        container_mem_mb = limits.memory_mb + 256  # heap + JVM overhead
        java_cmd = (
            f'java -Xmx{limits.memory_mb}m -Xss1m -XX:MaxMetaspaceSize=128m -XX:+UseSerialGC '
            '-XX:TieredStopAtLevel=1 -Dfile.encoding=UTF-8 -Djava.io.tmpdir=/work '
            '-cp /opt/classaid/harness:/opt/classaid/junit.jar ClassAidHarness'
        )
        return [
            self._docker, 'run', '--rm', '-i',
            '--name', name,
            '--network', 'none',
            '--read-only',
            '--tmpfs', '/work:rw,exec,size=64m,mode=1777',
            '-v', f'{out_dir}:/out:rw',
            '--user', CONTAINER_UID,
            '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges',
            '--memory', f'{container_mem_mb}m',
            '--memory-swap', f'{container_mem_mb}m',
            '--cpus', '1',
            '--pids-limit', '128',
            '--workdir', '/work',
            '--env', 'HOME=/work',
            self._image,
            '/bin/sh', '-c', f'ulimit -c 0; ulimit -t {cpu_s}; ulimit -f {file_blocks}; exec {java_cmd}',
        ]

    def run(self, request: RunRequest, weights: Mapping[str, float] | None = None) -> RunResult:
        start = time.monotonic()
        run_dir = Path(tempfile.mkdtemp(prefix='classaid-docker-'))
        out_dir = run_dir / 'out'
        out_dir.mkdir()
        out_dir.chmod(0o777)  # writable by the unprivileged container user
        nonce = new_nonce()
        name = f'classaid-run-{nonce}'
        stdout_path = run_dir / 'stdout.txt'
        stderr_path = run_dir / 'stderr.txt'
        wall_s = request.limits.time_ms / 1000 + STARTUP_SLACK_S

        wall_timeout = False
        exit_code: int | None = None
        try:
            with stdout_path.open('wb') as out, stderr_path.open('wb') as err:
                proc = subprocess.Popen(  # noqa: S603 -- fixed command; student code is passed via stdin
                    self._command(request, name, out_dir),
                    stdin=subprocess.PIPE, stdout=out, stderr=err,
                )
                try:
                    proc.communicate(harness_input(request, f'/out/result-{nonce}.json'), timeout=wall_s)
                except subprocess.TimeoutExpired:
                    wall_timeout = True
                    # Killing the CLI client does not stop the container; kill it by name.
                    subprocess.run([self._docker, 'kill', name], capture_output=True, timeout=30, check=False)  # noqa: S603
                    proc.kill()
                    proc.wait()
                exit_code = proc.returncode

            return build_result(request, weights, ProcessOutcome(
                result_path=out_dir / f'result-{nonce}.json',
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                exit_code=exit_code,
                wall_timeout=wall_timeout,
                output_file_limit=OUTPUT_FILE_LIMIT,
                duration_ms=int((time.monotonic() - start) * 1000),
            ))
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)
