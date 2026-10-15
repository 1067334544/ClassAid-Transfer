# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Java-side dependencies of the code runners: the JUnit standalone jar and the
compiled ClassAidHarness.
"""

import hashlib
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from .types import RunnerConfigError

JUNIT_VERSION = '1.14.4'  # JUnit Platform 1.14.4 = JUnit 5.14.4 (Jupiter API)
JUNIT_JAR_NAME = f'junit-platform-console-standalone-{JUNIT_VERSION}.jar'
JUNIT_URL = f'https://repo1.maven.org/maven2/org/junit/platform/junit-platform-console-standalone/{JUNIT_VERSION}/{JUNIT_JAR_NAME}'
JUNIT_SHA256 = '7c6968cbcaf4301c729f202b23b7d736c5d88be625fc7d27ad5d746146a8bc28'

RUNNER_DIR = Path(__file__).resolve().parent
HARNESS_SOURCE = RUNNER_DIR / 'java' / 'ClassAidHarness.java'
DEFAULT_JUNIT_JAR = RUNNER_DIR / 'lib' / JUNIT_JAR_NAME  # gitignored; populated by fetch_junit()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_junit(target: Path = DEFAULT_JUNIT_JAR) -> Path:
    """ Download the pinned JUnit standalone jar (if not already present) and verify its checksum. """
    if target.exists() and _sha256(target) == JUNIT_SHA256:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix('.download')
    with urllib.request.urlopen(JUNIT_URL, timeout=60) as response:
        tmp.write_bytes(response.read())
    if (digest := _sha256(tmp)) != JUNIT_SHA256:
        tmp.unlink()
        msg = f"Checksum mismatch for {JUNIT_JAR_NAME}: got {digest}, expected {JUNIT_SHA256}"
        raise RunnerConfigError(msg)
    tmp.replace(target)
    return target


def check_junit(jar: Path) -> Path:
    if not jar.is_file():
        msg = f"JUnit jar not found at {jar}.  Run `flask --app classaid runner-deps` to download it."
        raise RunnerConfigError(msg)
    return jar


def java_bin(java_home: Path, tool: str = 'java') -> Path:
    path = java_home / 'bin' / tool
    if not path.is_file():
        msg = f"'{tool}' not found in CLASSAID_JAVA_HOME ({java_home}).  A JDK 21 is required."
        raise RunnerConfigError(msg)
    return path


def ensure_harness(java_home: Path, junit_jar: Path, cache_root: Path | None = None) -> Path:
    """ Compile ClassAidHarness.java (once per source/JDK/JUnit combination) and return the
    directory containing its class files.
    """
    javac = java_bin(java_home, 'javac')
    key = hashlib.sha256(
        HARNESS_SOURCE.read_bytes() + str(java_home.resolve()).encode() + JUNIT_SHA256.encode()
    ).hexdigest()[:16]
    root = cache_root or Path(tempfile.gettempdir()) / 'classaid-harness'
    out_dir = root / key
    marker = out_dir / '.complete'
    if marker.exists():
        return out_dir

    out_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(  # noqa: S603 -- fixed arguments
        [str(javac), '-encoding', 'UTF-8', '-cp', str(junit_jar), '-d', str(out_dir), str(HARNESS_SOURCE)],
        capture_output=True, text=True, timeout=120, check=False,
    )
    if proc.returncode != 0:
        msg = f"Failed to compile the code-runner harness:\n{proc.stderr}"
        raise RunnerConfigError(msg)
    marker.touch()
    return out_dir
