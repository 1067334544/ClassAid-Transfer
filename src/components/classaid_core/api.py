# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Helpers for ClassAid's JSON API routes.

Gen-Ed's route access checks answer failures with HTML redirects/pages; JSON
clients (the Vue pages) need JSON errors instead.  `api_route` checks login and
an active class (and optionally the instructor role / an enabled class) and makes
the caller's class context available.
"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any, Literal
from urllib.parse import urlsplit

from flask import Response, jsonify, make_response, request

from gened.auth import get_auth


@dataclass(frozen=True)
class ClassContext:
    user_id: int
    class_id: int
    role_id: int | None   # None for admins acting in a class without a role (Gen-Ed uses role_id -1)
    role: Literal['instructor', 'student']
    class_enabled: bool

    @property
    def is_instructor(self) -> bool:
        return self.role == 'instructor'


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def json_body() -> dict[str, Any]:
    """ The request's JSON object body (ApiError 400 if missing or not an object). """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError(400, "Expected a JSON object body.")
    return data


def json_error(status: int, message: str) -> Response:
    return make_response(jsonify(error=message), status)


def current_class_context() -> ClassContext | None:
    auth = get_auth()
    if auth.user_id is None or auth.cur_class is None:
        return None
    cur = auth.cur_class
    return ClassContext(
        user_id=auth.user_id,
        class_id=cur.class_id,
        role_id=cur.role_id if cur.role_id > 0 else None,
        role=cur.role,
        class_enabled=bool(cur.class_enabled),  # Gen-Ed passes the SQLite integer through
    )


_SAFE_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS'})
_BODY_METHODS = frozenset({'POST', 'PUT', 'PATCH'})


def cross_site_check() -> Response | None:
    """ CSRF protection for state-changing JSON requests (Gen-Ed has no CSRF tokens and relies
    on SameSite=Lax cookies; this adds two more checks):
      - POST/PUT/PATCH bodies must be JSON (Content-Type: application/json), which cross-site
        HTML forms cannot send without a CORS preflight -> 415 otherwise (other methods,
        e.g. DELETE, always require a preflight cross-site);
      - if the browser sends an Origin header, it must be this site -> 403 otherwise.
    """
    if request.method in _SAFE_METHODS:
        return None
    origin = request.headers.get('Origin')
    if origin is not None and urlsplit(origin).netloc != request.host:
        return json_error(403, "Cross-site request rejected.")
    if request.method in _BODY_METHODS and not request.is_json:
        return json_error(415, "Expected a JSON request body (Content-Type: application/json).")
    return None


def _access_error(ctx: ClassContext | None, *, instructor: bool, enabled_class: bool) -> Response | None:
    if get_auth().user_id is None:
        return json_error(401, "Login required.")
    if ctx is None:
        return json_error(403, "No active class.")
    if instructor and not ctx.is_instructor:
        return json_error(403, "Instructor access required.")
    if enabled_class and not ctx.class_enabled:
        return json_error(403, "The current class is archived or disabled.")
    return None


def api_route(
    *, instructor: bool = False, enabled_class: bool = False,
) -> Callable[[Callable[..., Any]], Callable[..., Response | Any]]:
    """ Decorator for JSON API routes.  The wrapped function receives the caller's
    ClassContext as its first argument.  Failures return JSON errors:
      401 not logged in; 403 no active class, not an instructor (if required), or
      class disabled (if `enabled_class`), or a cross-site request; 415 for a
      state-changing request without a JSON body.  ApiError raised in the route becomes a
      JSON error with its status.
    """
    def decorator(f: Callable[..., Any]) -> Callable[..., Response | Any]:
        @wraps(f)
        def wrapped(*args: Any, **kwargs: Any) -> Response | Any:
            if (rejected := cross_site_check()) is not None:
                return rejected
            ctx = current_class_context()
            if (denied := _access_error(ctx, instructor=instructor, enabled_class=enabled_class)) is not None:
                return denied
            assert ctx is not None
            try:
                return f(ctx, *args, **kwargs)
            except ApiError as e:
                return json_error(e.status, e.message)
        return wrapped
    return decorator
