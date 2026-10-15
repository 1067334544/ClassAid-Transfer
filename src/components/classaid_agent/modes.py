# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Instructor-controlled feedback modes (paper §4.2.4, §4.3).

A student's effective mode is their individual mode if one is set, otherwise the
class mode.  "Set all" sets the class mode and clears every individual mode.
"""

from typing import Literal, get_args

import msgspec

from components.classaid_core.api import ApiError, ClassContext
from components.classaid_core.log import log_event
from gened.db import get_db

Mode = Literal['heuristic', 'technical', 'auto', 'silent']
MODES: tuple[Mode, ...] = get_args(Mode)
ModeSource = Literal['class', 'student']
DEFAULT_CLASS_MODE: Mode = 'heuristic'

_NOW = "strftime('%Y-%m-%d %H:%M:%f', 'now')"


class EffectiveMode(msgspec.Struct, frozen=True):
    mode: Mode
    source: ModeSource


def parse_mode(value: object) -> Mode:
    if value not in MODES:
        raise ApiError(400, f"Invalid mode: {value!r} (expected one of {', '.join(MODES)}).")
    mode: Mode = value  # narrowed by the membership check
    return mode


def get_class_mode(class_id: int) -> Mode:
    row = get_db().execute("SELECT class_mode FROM classaid_class_settings WHERE class_id=?", [class_id]).fetchone()
    mode: Mode = row['class_mode'] if row else DEFAULT_CLASS_MODE
    return mode


def get_effective_mode(class_id: int, user_id: int) -> EffectiveMode:
    row = get_db().execute("SELECT mode FROM classaid_student_modes WHERE class_id=? AND user_id=?", [class_id, user_id]).fetchone()
    if row:
        return EffectiveMode(mode=row['mode'], source='student')
    return EffectiveMode(mode=get_class_mode(class_id), source='class')


def class_student_ids(class_id: int) -> list[int]:
    rows = get_db().execute(
        "SELECT user_id FROM roles WHERE class_id=? AND role='student' AND active=1 ORDER BY user_id", [class_id]
    ).fetchall()
    return [row['user_id'] for row in rows]


def _require_student(class_id: int, user_id: int) -> None:
    if user_id not in class_student_ids(class_id):
        raise ApiError(404, "Student not found in this class.")


def set_student_mode(ctx: ClassContext, student_id: int, mode: Mode | None) -> EffectiveMode:
    """ Set (or, with mode=None, clear) one student's individual mode.  Logs 'mode_changed'. """
    _require_student(ctx.class_id, student_id)
    before = get_effective_mode(ctx.class_id, student_id)
    db = get_db()
    if mode is None:
        db.execute("DELETE FROM classaid_student_modes WHERE class_id=? AND user_id=?", [ctx.class_id, student_id])
    else:
        db.execute(
            f"""INSERT INTO classaid_student_modes (class_id, user_id, mode) VALUES (?, ?, ?)
                ON CONFLICT (class_id, user_id) DO UPDATE SET mode=excluded.mode, updated_at={_NOW}""",  # noqa: S608 -- constant SQL
            [ctx.class_id, student_id, mode],
        )
    after = get_effective_mode(ctx.class_id, student_id)
    log_event(ctx, 'mode_changed', payload={
        'scope': 'student',
        'action': 'clear' if mode is None else 'set',
        'affected_students': [student_id],
        'before': {str(student_id): msgspec.to_builtins(before)},
        'after': {str(student_id): msgspec.to_builtins(after)},
    })
    db.commit()
    return after


def set_class_mode(ctx: ClassContext, mode: Mode) -> None:
    """ Apply a mode to the whole class: set the class mode and clear all individual modes,
    so every student's effective mode is `mode`.  Logs 'mode_changed' including the
    individual modes that were cleared.
    """
    db = get_db()
    students = class_student_ids(ctx.class_id)
    before = {str(sid): msgspec.to_builtins(get_effective_mode(ctx.class_id, sid)) for sid in students}
    previous_class_mode = get_class_mode(ctx.class_id)
    cleared = [
        {'user_id': row['user_id'], 'mode': row['mode']}
        for row in db.execute("SELECT user_id, mode FROM classaid_student_modes WHERE class_id=? ORDER BY user_id", [ctx.class_id])
    ]
    db.execute(
        f"""INSERT INTO classaid_class_settings (class_id, class_mode) VALUES (?, ?)
            ON CONFLICT (class_id) DO UPDATE SET class_mode=excluded.class_mode, updated_at={_NOW}""",  # noqa: S608 -- constant SQL
        [ctx.class_id, mode],
    )
    db.execute("DELETE FROM classaid_student_modes WHERE class_id=?", [ctx.class_id])
    log_event(ctx, 'mode_changed', payload={
        'scope': 'class',
        'action': 'set',
        'class_mode_before': previous_class_mode,
        'class_mode_after': mode,
        'cleared_student_modes': cleared,
        'affected_students': students,
        'before': before,
        'after': {str(sid): {'mode': mode, 'source': 'class'} for sid in students},
    })
    db.commit()
