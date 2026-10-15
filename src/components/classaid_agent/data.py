# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

import msgspec

from gened.db import get_db

DELETED = '[deleted]'


def _scrub_user_id(value: object, user_id: int) -> object:
    """ Replace every occurrence of user_id (as an int, or as a str dict key/value) with -1. """
    if isinstance(value, dict):
        return {('-1' if k == str(user_id) else k): _scrub_user_id(v, user_id) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub_user_id(v, user_id) for v in value]
    if value == user_id and not isinstance(value, bool):
        return -1
    return value


class AgentDeletionHandler:
    """ Personal data deletion for chat messages, generation records, and individual modes.
    Keeps non-personal metadata (modes, feedback types, statuses, times) for analysis.
    """

    @staticmethod
    def delete_user_data(user_id: int) -> None:
        db = get_db()
        db.execute("UPDATE classaid_messages SET content=?, user_id=-1 WHERE user_id=?", [DELETED, user_id])
        db.execute("""
            UPDATE classaid_generations
            SET calls='[]', selection=NULL, error=NULL, user_id=-1,
                displayed_text=CASE WHEN displayed_text IS NOT NULL THEN ? ELSE NULL END
            WHERE user_id=?
        """, [DELETED, user_id])
        db.execute("DELETE FROM classaid_student_modes WHERE user_id=?", [user_id])
        # Instructors' mode_changed events name the affected students: unlink this user there too.
        rows = db.execute("SELECT id, payload FROM classaid_events WHERE type='mode_changed'").fetchall()
        for row in rows:
            payload = msgspec.json.decode(row['payload'])
            scrubbed = _scrub_user_id(payload, user_id)
            if scrubbed != payload:
                db.execute("UPDATE classaid_events SET payload=? WHERE id=?", [msgspec.json.encode(scrubbed).decode(), row['id']])

    @staticmethod
    def delete_class_data(class_id: int) -> None:
        db = get_db()
        db.execute("UPDATE classaid_messages SET content=?, user_id=-1 WHERE class_id=?", [DELETED, class_id])
        db.execute("""
            UPDATE classaid_generations
            SET calls='[]', selection=NULL, error=NULL, user_id=-1,
                displayed_text=CASE WHEN displayed_text IS NOT NULL THEN ? ELSE NULL END
            WHERE class_id=?
        """, [DELETED, class_id])
        db.execute("DELETE FROM classaid_student_modes WHERE class_id=?", [class_id])
        # The class's mode_changed events were already emptied by the core handler.
