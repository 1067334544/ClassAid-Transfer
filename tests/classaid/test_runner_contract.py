# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Runner contract tests: every CodeRunner must give the same structured results
for the same code.  Each case runs against the local runner (skipped without a
JDK) and the Docker runner (marked `docker`; skipped without Docker and the image).

Point the local runner at a JDK 21 with CLASSAID_JAVA_HOME (or JAVA_HOME), and
fetch the JUnit jar once with `flask --app classaid runner-deps`.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from components.classaid_tasks.runner import (
    CodeRunner,
    DockerRunner,
    Limits,
    LocalRunner,
    RunRequest,
)
from components.classaid_tasks.runner.deps import DEFAULT_JUNIT_JAR
from components.classaid_tasks.runner.docker import DEFAULT_IMAGE

LINKED_LIST = """\
public class LinkedList {
    static class Node {
        int value;
        Node next;
        Node(int value) { this.value = value; }
    }

    Node head;

    public void add(int value) {
        Node n = new Node(value);
        if (head == null) { head = n; return; }
        Node cur = head;
        while (cur.next != null) { cur = cur.next; }
        cur.next = n;
    }

    public int length() {
        int n = 0;
        Node cur = head;
        while (cur.next != null) {   // line 21: NPE on an empty list; off-by-one otherwise
            n++;
            cur = cur.next;
        }
        return n;
    }
}
"""

TESTS = """\
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

public class LinkedListTest {
    // SECRET-TEST-MARKER: must never appear in results returned to students
    @Test void addDoesNotThrow() { new LinkedList().add(1); }
    @Test void twoAdds() { LinkedList l = new LinkedList(); l.add(1); l.add(2); assertNotNull(l.head.next); }
    @Test void lengthOfThree() { LinkedList l = new LinkedList(); l.add(1); l.add(2); l.add(3); assertEquals(3, l.length()); }
}
"""
WEIGHTS = {'LinkedListTest#addDoesNotThrow': 1, 'LinkedListTest#twoAdds': 1, 'LinkedListTest#lengthOfThree': 2}

FAST = Limits(time_ms=3000, test_timeout_ms=500)


def main(body: str) -> dict[str, str]:
    return {'Main.java': f"public class Main {{\n    public static void main(String[] args) throws Exception {{\n        {body}\n    }}\n}}\n"}


def _java_home() -> Path | None:
    for var in ('CLASSAID_JAVA_HOME', 'JAVA_HOME'):
        if (value := os.environ.get(var)) and (Path(value) / 'bin' / 'javac').is_file():
            return Path(value)
    return None


@pytest.fixture(scope='session')
def local_runner() -> CodeRunner:
    java_home = _java_home()
    if java_home is None:
        pytest.skip("No JDK: set CLASSAID_JAVA_HOME to a JDK 21 home to run local-runner contract tests.")
    if not DEFAULT_JUNIT_JAR.is_file():
        pytest.skip("JUnit jar missing: run `flask --app classaid runner-deps`.")
    return LocalRunner(java_home, DEFAULT_JUNIT_JAR)


@pytest.fixture(scope='session')
def docker_runner() -> CodeRunner:
    if shutil.which('docker') is None:
        pytest.skip("Docker not available on this machine.")
    probe = subprocess.run(['docker', 'image', 'inspect', DEFAULT_IMAGE], capture_output=True, check=False)
    if probe.returncode != 0:
        pytest.skip(f"Docker image {DEFAULT_IMAGE} not built (see runner/container/Dockerfile).")
    return DockerRunner(DEFAULT_IMAGE)


@pytest.fixture(params=['local', pytest.param('docker', marks=pytest.mark.docker)])
def runner(request: pytest.FixtureRequest) -> CodeRunner:
    runner: CodeRunner = request.getfixturevalue(f'{request.param}_runner')
    return runner


# ------------------------------------------------------------------ run mode

def test_normal_run(runner: CodeRunner) -> None:
    files = {'LinkedList.java': LINKED_LIST} | main("LinkedList l = new LinkedList(); l.add(1); l.add(2); l.add(3); System.out.println(l.length() + 1);")
    result = runner.run(RunRequest(kind='run', files=files, limits=FAST))
    assert result.status == 'ok'
    assert result.compile is not None
    assert result.compile.ok
    assert result.stdout == '3\n'
    assert result.exit_code == 0
    assert result.limit_exceeded is None


def test_compile_error(runner: CodeRunner) -> None:
    broken = LINKED_LIST.replace('return n;', 'return n')
    result = runner.run(RunRequest(kind='run', files={'LinkedList.java': broken} | main(""), limits=FAST))
    assert result.status == 'compile_error'
    assert result.compile is not None
    assert not result.compile.ok
    diag = result.compile.diagnostics[0]
    assert (diag.kind, diag.file, diag.line) == ('error', 'LinkedList.java', 25)
    assert diag.column is not None
    assert "';' expected" in diag.message
    assert result.stdout == ''


def test_null_pointer_frame(runner: CodeRunner) -> None:
    files = {'LinkedList.java': LINKED_LIST} | main("System.out.println(new LinkedList().length());")
    result = runner.run(RunRequest(kind='run', files=files, limits=FAST))
    assert result.status == 'runtime_error'
    assert result.exception is not None
    assert result.exception.type == 'java.lang.NullPointerException'
    assert (result.exception.frames[0].file, result.exception.frames[0].line) == ('LinkedList.java', 21)
    assert [f.file for f in result.exception.frames] == ['LinkedList.java', 'Main.java']


def test_infinite_loop_times_out(runner: CodeRunner) -> None:
    result = runner.run(RunRequest(kind='run', files=main("System.out.println(\"start\"); while (true) { }"), limits=Limits(time_ms=1000)))
    assert result.status == 'timeout'
    assert result.limit_exceeded == 'time'
    assert result.stdout == 'start\n'


def test_infinite_recursion(runner: CodeRunner) -> None:
    files = {'Main.java': "public class Main {\n  static int f(int n) { return f(n + 1) + 1; }\n  public static void main(String[] a) { f(0); }\n}\n"}
    result = runner.run(RunRequest(kind='run', files=files, limits=FAST))
    assert result.status == 'runtime_error'
    assert result.exception is not None
    assert result.exception.type == 'java.lang.StackOverflowError'
    assert result.exception.frames[0].file == 'Main.java'


def test_memory_limit(runner: CodeRunner) -> None:
    body = "java.util.List<long[]> keep = new java.util.ArrayList<>(); while (true) { keep.add(new long[1_000_000]); }"
    result = runner.run(RunRequest(kind='run', files=main(body), limits=Limits(time_ms=5000, memory_mb=64)))
    assert result.status == 'memory_exceeded'
    assert result.limit_exceeded == 'memory'


def test_output_truncated(runner: CodeRunner) -> None:
    body = "String line = \"x\".repeat(99); for (int i = 0; i < 30_000; i++) { System.out.println(line); } System.out.flush();"
    result = runner.run(RunRequest(kind='run', files=main(body), limits=Limits(time_ms=5000, output_bytes=10_000)))
    assert result.status == 'ok'
    assert result.stdout_truncated
    assert result.limit_exceeded == 'output'
    assert len(result.stdout.encode()) <= 10_000


def test_system_exit(runner: CodeRunner) -> None:
    result = runner.run(RunRequest(kind='run', files=main("System.out.println(\"bye\"); System.exit(3);"), limits=FAST))
    assert result.status == 'exited'
    assert result.exit_code == 3
    assert result.stdout == 'bye\n'


def test_missing_entry_class(runner: CodeRunner) -> None:
    result = runner.run(RunRequest(kind='run', files={'LinkedList.java': LINKED_LIST}, entry='Main', limits=FAST))
    assert result.status == 'runtime_error'
    assert result.exception is not None
    assert result.exception.type == 'java.lang.ClassNotFoundException'


# ------------------------------------------------------------------ tests mode

def test_tests_partially_failing(runner: CodeRunner) -> None:
    """ Spec scenario: weights 1, 1, 2; first two pass, third fails -> 2.5 """
    request = RunRequest(kind='tests', files={'LinkedList.java': LINKED_LIST}, tests={'LinkedListTest.java': TESTS}, limits=FAST)
    result = runner.run(request, WEIGHTS)
    assert result.status == 'ok'
    assert result.tests is not None
    by_id = {t.id: t for t in result.tests}
    assert by_id['LinkedListTest#addDoesNotThrow'].status == 'passed'
    assert by_id['LinkedListTest#twoAdds'].status == 'passed'
    failed = by_id['LinkedListTest#lengthOfThree']
    assert failed.status == 'failed'
    assert failed.message == 'expected: <3> but was: <2>'
    assert result.score == 2.5


def test_tests_do_not_leak_test_source(runner: CodeRunner) -> None:
    probe = main("System.out.println(new java.io.File(\"LinkedListTest.java\").exists());")
    request = RunRequest(kind='tests', files={'LinkedList.java': LINKED_LIST} | probe, tests={'LinkedListTest.java': TESTS}, limits=FAST)
    result = runner.run(request, WEIGHTS)
    assert 'SECRET-TEST-MARKER' not in repr(result)
    # and the test source is not on disk where student code could read it
    run_result = runner.run(RunRequest(kind='run', files={'LinkedList.java': LINKED_LIST} | probe, limits=FAST))
    assert run_result.stdout == 'false\n'


def test_compile_error_in_tests_hides_location(runner: CodeRunner) -> None:
    """ Student code lacking a method the tests call: the diagnostic must not reveal test file positions. """
    no_length = LINKED_LIST.replace('public int length()', 'public int size()')
    request = RunRequest(kind='tests', files={'LinkedList.java': no_length}, tests={'LinkedListTest.java': TESTS}, limits=FAST)
    result = runner.run(request, WEIGHTS)
    assert result.status == 'compile_error'
    assert result.score == 0.0
    assert result.compile is not None
    test_diags = [d for d in result.compile.diagnostics if d.in_tests]
    assert test_diags
    assert all(d.file is None and d.line is None for d in test_diags)
    assert 'SECRET-TEST-MARKER' not in repr(result)


def test_test_timeout_is_per_test(runner: CodeRunner) -> None:
    looping = LINKED_LIST.replace('int n = 0;', 'int n = 0; while (n >= 0) { }')
    request = RunRequest(kind='tests', files={'LinkedList.java': looping}, tests={'LinkedListTest.java': TESTS}, limits=FAST)
    result = runner.run(request, WEIGHTS)
    assert result.tests is not None
    by_id = {t.id: t for t in result.tests}
    assert by_id['LinkedListTest#lengthOfThree'].status == 'timeout'
    assert by_id['LinkedListTest#addDoesNotThrow'].status == 'passed'
    assert result.score == 2.5


# ------------------------------------------------------------------ isolation (docker only)

@pytest.mark.docker
def test_no_network(docker_runner: CodeRunner) -> None:
    body = "new java.net.Socket(\"1.1.1.1\", 80).close(); System.out.println(\"connected\");"
    result = docker_runner.run(RunRequest(kind='run', files=main(body), limits=FAST))
    assert result.status == 'runtime_error'
    assert 'connected' not in result.stdout


@pytest.mark.docker
def test_cannot_read_server_files(docker_runner: CodeRunner, tmp_path: Path) -> None:
    secret = tmp_path / 'server_config.txt'
    secret.write_text('SERVER-SECRET')
    body = f"System.out.println(java.nio.file.Files.readString(java.nio.file.Path.of(\"{secret}\")));"
    result = docker_runner.run(RunRequest(kind='run', files=main(body), limits=FAST))
    assert result.status == 'runtime_error'
    assert 'SERVER-SECRET' not in result.stdout
