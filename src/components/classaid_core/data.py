# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

from sqlite3 import Cursor

from gened.app_data import DataSource, Filters
from gened.db import get_db
from gened.tables import Col, DataTableSpec, NumCol, TimeCol, UserCol

TABLE_NAME = 'classaid_events'
DISPLAY_NAME = 'ClassAid Activity'


def get_events(filters: Filters, /, limit: int=-1, offset: int=0) -> Cursor:
    db = get_db()
    where_clause, where_params = filters.make_where(['consumer', 'class', 'user', 'role', 'row_id'])
    sql = f"""
        SELECT
            t.id AS id,
            json_array(users.display_name, auth_providers.name, users.display_extra) AS user,
            t.ts AS time,
            t.task_id AS task,
            t.type AS type,
            t.payload AS payload,
            t.user_id AS user_id,
            classes.id AS class_id
        FROM classaid_events AS t
        JOIN users ON t.user_id=users.id
        LEFT JOIN auth_providers ON users.auth_provider=auth_providers.id
        LEFT JOIN roles ON t.role_id=roles.id
        LEFT JOIN classes ON roles.class_id=classes.id
        LEFT JOIN classes_lti ON classes.id=classes_lti.class_id
        LEFT JOIN consumers ON consumers.id=classes_lti.lti_consumer_id
        WHERE {where_clause}
        ORDER BY t.id DESC
        LIMIT ?
        OFFSET ?
    """  # noqa: S608 -- where_clause is generated safely
    return db.execute(sql, [*where_params, limit, offset])


events_table = DataTableSpec(
    columns=[NumCol('id'), UserCol('user'), TimeCol('time'), NumCol('task'), Col('type'), Col('payload')],
)

events_data_source = DataSource(
    table_name=TABLE_NAME,
    display_name=DISPLAY_NAME,
    get_data=get_events,
    table_spec=events_table,
    time_col='ts',
)


def _delete_orphan_snapshots() -> None:
    get_db().execute("""
        DELETE FROM classaid_snapshots
        WHERE id NOT IN (SELECT snapshot_id FROM classaid_events WHERE snapshot_id IS NOT NULL)
    """)


class CoreDeletionHandler:
    """ Personal data deletion for the ClassAid activity log, snapshots, and jobs.

    Like Gen-Ed's own handlers, this keeps non-personal metadata (event types and times,
    class ids) for analysis, but removes content and the link to the user (user_id -1).
    The ClassAid deletion handlers (this one and AgentDeletionHandler) are the only code
    that modifies classaid_events.
    """

    @staticmethod
    def delete_user_data(user_id: int) -> None:
        db = get_db()
        db.execute("UPDATE classaid_events SET payload='{}', snapshot_id=NULL, user_id=-1 WHERE user_id=?", [user_id])
        db.execute("UPDATE classaid_jobs SET request='{}', result=NULL, error=NULL, user_id=-1 WHERE user_id=?", [user_id])
        _delete_orphan_snapshots()

    @staticmethod
    def delete_class_data(class_id: int) -> None:
        db = get_db()
        db.execute("UPDATE classaid_events SET payload='{}', snapshot_id=NULL, user_id=-1 WHERE class_id=?", [class_id])
        db.execute("UPDATE classaid_jobs SET request='{}', result=NULL, error=NULL, user_id=-1 WHERE class_id=?", [class_id])
        _delete_orphan_snapshots()
