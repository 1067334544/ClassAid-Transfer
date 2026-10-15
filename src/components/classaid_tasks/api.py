# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" JSON API for the student task workspace. """

from typing import Literal

import msgspec
from flask import Blueprint, Response, jsonify, make_response

from components.classaid_core.api import ApiError, ClassContext, api_route, json_body
from gened.db import get_db

from .data import get_task, list_tasks
from .model import TaskConfig
from .progress import open_task, save_files, validate_files
from .runner import RunResult
from .runs import job_view, student_result, submit_completion, submit_run

bp = Blueprint('classaid_tasks', __name__, url_prefix='/classaid', template_folder='templates')


def task_or_404(ctx: ClassContext, task_id: int) -> TaskConfig:
    """ The task, if it is in the caller's current class and (for students) available. """
    task = get_task(task_id, ctx.class_id, available_only=not ctx.is_instructor)
    if task is None:
        raise ApiError(404, "Task not found.")
    return task


@bp.route('/api/tasks')
@api_route()
def tasks_list(ctx: ClassContext) -> Response:
    """ Tasks in the current class.  Students see only available tasks; instructors see all. """
    tasks = list_tasks(ctx.class_id, available_only=not ctx.is_instructor)
    progress = {
        row['task_id']: row
        for row in get_db().execute("SELECT task_id, status, score FROM classaid_task_progress WHERE user_id=? AND class_id=?", [ctx.user_id, ctx.class_id])
    }

    def item(task: TaskConfig, available: str) -> dict[str, object]:
        mine = progress.get(task.row_id)
        data: dict[str, object] = {
            'id': task.row_id,
            'title': task.name,
            'status': mine['status'] if mine else 'not_started',
            'score': mine['score'] if mine else None,
        }
        if ctx.is_instructor:
            data['available'] = available
        return data

    return jsonify(tasks=[item(task, available) for task, available in tasks])


@bp.route('/api/tasks/<int:task_id>')
@api_route()
def task_open(ctx: ClassContext, task_id: int) -> Response:
    """ Open a task: its student-visible definition plus the caller's progress
    (started with the starter code on first open).
    """
    task = task_or_404(ctx, task_id)
    progress = open_task(ctx, task).to_json()
    if progress['final_result'] is not None:
        progress['final_result'] = student_result(msgspec.convert(progress['final_result'], RunResult))
    return jsonify(task=task.student_view(), progress=progress)


@bp.route('/api/tasks/<int:task_id>/code', methods=['PUT'])
@api_route(enabled_class=True)
def task_save_code(ctx: ClassContext, task_id: int) -> Response:
    """ Autosave the student's current code. """
    task = task_or_404(ctx, task_id)
    files = validate_files(task, json_body().get('files'))
    save_files(ctx, task, files, reason='autosave')
    return jsonify(saved=True)


def _start_run(ctx: ClassContext, task_id: int, kind: Literal['run', 'tests']) -> Response:
    task = task_or_404(ctx, task_id)
    files = validate_files(task, json_body().get('files'))
    save_files(ctx, task, files, reason=kind)   # running saves the code immediately
    job_id = submit_run(ctx, task, kind, files)
    return make_response(jsonify(job_id=job_id), 202)


@bp.route('/api/tasks/<int:task_id>/run', methods=['POST'])
@api_route(enabled_class=True)
def task_run(ctx: ClassContext, task_id: int) -> Response:
    """ Run the student's program (entry class main()).  Returns a job id to poll. """
    return _start_run(ctx, task_id, 'run')


@bp.route('/api/tasks/<int:task_id>/test', methods=['POST'])
@api_route(enabled_class=True)
def task_test(ctx: ClassContext, task_id: int) -> Response:
    """ Run the instructor tests against the student's code.  Returns a job id to poll. """
    return _start_run(ctx, task_id, 'tests')


@bp.route('/api/jobs/<int:job_id>')
@api_route()
def job_status(ctx: ClassContext, job_id: int) -> Response:
    """ Status (queued / running / done / failed) and result of one of the caller's jobs. """
    return jsonify(job_view(ctx, job_id))


@bp.route('/api/tasks/<int:task_id>/complete', methods=['POST'])
@api_route(enabled_class=True)
def task_complete(ctx: ClassContext, task_id: int) -> Response:
    """ Complete the task: run the instructor tests on the final code, score it (0-5),
    archive code/result, and make the task read-only.  Returns a job id to poll.
    """
    task = task_or_404(ctx, task_id)
    files = validate_files(task, json_body().get('files'))
    save_files(ctx, task, files, reason='complete')
    job_id = submit_completion(ctx, task, files)
    return make_response(jsonify(job_id=job_id), 202)
