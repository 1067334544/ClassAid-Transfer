# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Run / Run Tests for the student workspace, executed as background jobs. """

from typing import Any

import msgspec
from flask import current_app

from components.classaid_core import JobOwner, submit_job
from components.classaid_core.api import ApiError, ClassContext
from components.classaid_core.log import log_event
from gened.db import get_db

from .data import get_task
from .model import TaskConfig
from .progress import mark_completed
from .runner import RunnerConfigError, RunRequest, RunResult, get_runner
from .runner.types import RunKind

EVENT_TYPES: dict[RunKind, str] = {'run': 'run', 'tests': 'test_run'}
COMPLETE_KIND = 'complete'
RUNNER_UNAVAILABLE = "The code runner is unavailable right now.  Please tell your instructor."
JOB_FAILED = "Something went wrong while processing your request.  Please try again."


def run_request(task: TaskConfig, kind: RunKind, files: dict[str, str]) -> RunRequest:
    return RunRequest(
        kind=kind,
        files=files,
        entry=task.spec.entry,
        tests={f.name: f.content for f in task.spec.tests} if kind == 'tests' else {},
    )


def execute(task: TaskConfig, kind: RunKind, files: dict[str, str]) -> RunResult:
    """ Run synchronously with the configured runner (in the caller's thread). """
    return get_runner().run(run_request(task, kind, files), task.spec.weights)


def student_result(result: RunResult) -> dict[str, Any]:
    """ The parts of a RunResult that students may see.  In 'tests' mode the program's
    output is withheld (it could reveal instructor tests), as are internal error details.
    """
    data: dict[str, Any] = msgspec.to_builtins(result)
    if result.kind == 'tests':
        data |= {'stdout': '', 'stderr': '', 'stdout_truncated': False, 'stderr_truncated': False}
    if result.internal_error:
        data['internal_error'] = "Internal error while running your code."
    return data


def _context_from(request: dict[str, Any]) -> ClassContext:
    return ClassContext(
        user_id=request['user_id'], class_id=request['class_id'], role_id=request['role_id'],
        role=request['role'], class_enabled=True,
    )


def _run_job(job_id: int, request: dict[str, Any]) -> dict[str, Any]:
    """ Job function (worker thread, app context): run the code and log the result. """
    ctx = _context_from(request)
    kind: RunKind = request['kind']
    task = get_task(request['task_id'], ctx.class_id, available_only=False)
    if task is None:
        msg = f"Task {request['task_id']} no longer exists."
        raise RuntimeError(msg)
    files: dict[str, str] = request['files']
    try:
        result = execute(task, kind, files)
    except RunnerConfigError:
        current_app.logger.exception("Code runner unavailable")
        log_event(ctx, EVENT_TYPES[kind], task_id=task.row_id, payload={'job_id': job_id, 'error': 'runner_unavailable'}, files=files)
        get_db().commit()
        raise
    log_event(ctx, EVENT_TYPES[kind], task_id=task.row_id, payload={'job_id': job_id, 'result': msgspec.to_builtins(result)}, files=files)
    get_db().commit()
    return {'result': msgspec.to_builtins(result)}


def submit_run(ctx: ClassContext, task: TaskConfig, kind: RunKind, files: dict[str, str]) -> int:
    """ Schedule a run of the student's code; returns the job id. """
    assert task.row_id is not None
    request = {
        'kind': kind, 'task_id': task.row_id, 'files': files,
        'user_id': ctx.user_id, 'class_id': ctx.class_id, 'role_id': ctx.role_id, 'role': ctx.role,
    }
    return submit_job(kind, 'runner', _run_job, request, JobOwner(ctx.user_id, ctx.class_id, task.row_id))


def _complete_job(_job_id: int, request: dict[str, Any]) -> dict[str, Any]:
    """ Job function: run the instructor tests on the submitted code and complete the task.
    A runner failure leaves the task in progress (the student can try again).
    """
    ctx = _context_from(request)
    task = get_task(request['task_id'], ctx.class_id, available_only=False)
    if task is None:
        msg = f"Task {request['task_id']} no longer exists."
        raise RuntimeError(msg)
    files: dict[str, str] = request['files']
    result = execute(task, 'tests', files)
    if result.status == 'internal_error':
        msg = f"Runner internal error: {result.internal_error}"
        raise RuntimeError(msg)
    assert result.score is not None
    result_data = msgspec.to_builtins(result)
    mark_completed(ctx, request['task_id'], files, result_data, result.score)
    return {'result': result_data}


def submit_completion(ctx: ClassContext, task: TaskConfig, files: dict[str, str]) -> int:
    """ Schedule completing the task with the given final code; returns the job id. """
    assert task.row_id is not None
    request = {
        'kind': 'tests', 'task_id': task.row_id, 'files': files,
        'user_id': ctx.user_id, 'class_id': ctx.class_id, 'role_id': ctx.role_id, 'role': ctx.role,
    }
    return submit_job(COMPLETE_KIND, 'runner', _complete_job, request, JobOwner(ctx.user_id, ctx.class_id, task.row_id))


def job_view(ctx: ClassContext, job_id: int) -> dict[str, Any]:
    """ Status and (student-safe) result of one of the caller's jobs. """
    row = get_db().execute(
        "SELECT id, kind, status, result, error FROM classaid_jobs WHERE id=? AND user_id=? AND class_id=?",
        [job_id, ctx.user_id, ctx.class_id],
    ).fetchone()
    if row is None:
        raise ApiError(404, "Job not found.")
    view: dict[str, Any] = {'id': row['id'], 'kind': row['kind'], 'status': row['status']}
    if row['status'] == 'done' and row['kind'] in (*EVENT_TYPES, COMPLETE_KIND):
        result = msgspec.json.decode(row['result'], type=dict[str, Any])['result']
        view['result'] = student_result(msgspec.convert(result, RunResult))
    elif row['status'] == 'failed':
        view['error'] = RUNNER_UNAVAILABLE if row['kind'] in (*EVENT_TYPES, COMPLETE_KIND) else JOB_FAILED
    return view
