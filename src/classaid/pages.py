# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Page routes for the Vue pages (student workspace, instructor mode control, style preview).

Each route renders the shell template with a built frontend entry and startup data;
everything else happens through the JSON API.
"""

from typing import Any

from flask import Blueprint, abort, redirect, render_template, url_for
from werkzeug.wrappers.response import Response

from gened.access import Access, route_requires
from gened.auth import get_auth

from .assets import entry_assets

bp = Blueprint('classaid_pages', __name__, url_prefix='/classaid')


def _bootstrap(page: str, **extra: Any) -> dict[str, Any]:
    auth = get_auth()
    if auth.user is None or auth.cur_class is None:
        abort(403)
    return {
        'page': page,
        'apiBase': url_for('classaid_tasks.tasks_list').removesuffix('/tasks'),
        'user': {'id': auth.user.id, 'name': auth.user.display_name},
        'classId': auth.cur_class.class_id,
        'className': auth.cur_class.class_name,
        'role': auth.cur_class.role,
    } | extra


def render_page(entry: str, page: str, **extra: Any) -> str | Response:
    if get_auth().cur_class is None:
        # e.g. logged in without an active class: let the user pick one of their classes
        return redirect(url_for('profile.main'))
    return render_template('classaid_app.html', assets=entry_assets(entry), bootstrap=_bootstrap(page, **extra))


@bp.route('/styleguide')
@route_requires(Access.INSTRUCTOR)
def styleguide() -> str | Response:
    """ Visual specification preview (task 7.2). """
    return render_page('styleguide', 'styleguide')


@bp.route('/tasks')
@route_requires(Access.LOGIN)
def task_list() -> str | Response:
    """ The class's tasks (students: available ones, with their progress). """
    return render_page('workspace', 'task_list', taskId=None, modesUrl=url_for('.modes'))


@bp.route('/tasks/<int:task_id>')
@route_requires(Access.LOGIN)
def workspace(task_id: int) -> str | Response:
    """ The student task workspace (the JSON API enforces access to the task). """
    return render_page('workspace', 'workspace', taskId=task_id, taskListUrl=url_for('.task_list'))


@bp.route('/modes')
@route_requires(Access.INSTRUCTOR)
def modes() -> str | Response:
    """ Instructor mode control. """
    return render_page('modes', 'modes', taskListUrl=url_for('.task_list'))
