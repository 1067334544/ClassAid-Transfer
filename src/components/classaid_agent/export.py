# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Export of a class's complete ClassAid activity log as JSON Lines.

One line per event, in order.  Each line carries the event, the code snapshot it
references (if any), and -- for feedback events -- the full generation record (mode,
selection, prompt version, every model call's input and output, the text shown).
Together these suffice to reconstruct, in order, each student's activity, the help
they received and why, and the instructor's mode changes.
"""

from collections.abc import Iterator
from typing import Any

import msgspec

from gened.db import get_db

_GENERATION_FIELDS = (
    'id', 'question_id', 'trigger_event_id', 'trigger', 'effective_mode', 'mode_source', 'status',
    'selected_type', 'selection', 'model', 'prompt_version', 'calls', 'displayed_text', 'error', 'latency_ms',
)
_JSON_COLUMNS = ('selection', 'calls')


def _generation(row: Any) -> dict[str, Any]:
    data = {field: row[field] for field in _GENERATION_FIELDS}
    for column in _JSON_COLUMNS:
        if data[column] is not None:
            data[column] = msgspec.json.decode(data[column])
    return data


def export_class_events(class_id: int) -> Iterator[str]:
    db = get_db()
    generations = {
        row['id']: _generation(row)
        for row in db.execute("SELECT * FROM classaid_generations WHERE class_id=?", [class_id])
    }
    rows = db.execute("""
        SELECT e.id, e.ts, e.user_id, users.display_name AS user_name, roles.role, e.task_id, e.type, e.payload,
               s.files AS snapshot
        FROM classaid_events e
        LEFT JOIN users ON users.id = e.user_id
        LEFT JOIN roles ON roles.id = e.role_id
        LEFT JOIN classaid_snapshots s ON s.id = e.snapshot_id
        WHERE e.class_id = ?
        ORDER BY e.id
    """, [class_id])
    for row in rows:
        payload = msgspec.json.decode(row['payload'])
        line: dict[str, Any] = {
            'id': row['id'],
            'ts': row['ts'],
            'user_id': row['user_id'],
            'user_name': row['user_name'],
            'role': row['role'],
            'task_id': row['task_id'],
            'type': row['type'],
            'payload': payload,
            'files': msgspec.json.decode(row['snapshot']) if row['snapshot'] else None,
        }
        if (generation_id := payload.get('generation_id')) is not None:
            line['generation'] = generations.get(generation_id)
        yield msgspec.json.encode(line).decode() + '\n'
