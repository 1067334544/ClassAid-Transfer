# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

from gened.db import get_db

from .config_table import tasks_config_table
from .model import TaskConfig

ITEM_TYPE = tasks_config_table.name

# Same "available anywhere on earth" rule as gened's ConfigTable.get_items()
_AVAILABLE_SQL = "available <= date('now', '+12 hours')"


def get_task(task_id: int, class_id: int, *, available_only: bool) -> TaskConfig | None:
    """ A task in the given class, or None if it does not exist there (or is not yet available). """
    sql = "SELECT * FROM config_items WHERE id=? AND class_id=? AND item_type=?"
    if available_only:
        sql += f" AND {_AVAILABLE_SQL}"
    row = get_db().execute(sql, [task_id, class_id, ITEM_TYPE]).fetchone()
    return TaskConfig.from_row(row) if row else None


def list_tasks(class_id: int, *, available_only: bool) -> list[tuple[TaskConfig, str]]:
    """ Tasks in the class in instructor-defined order, with their available dates. """
    sql = "SELECT * FROM config_items WHERE class_id=? AND item_type=?"
    if available_only:
        sql += f" AND {_AVAILABLE_SQL}"
    sql += " ORDER BY class_order ASC"
    rows = get_db().execute(sql, [class_id, ITEM_TYPE]).fetchall()
    return [(TaskConfig.from_row(row), str(row['available'])) for row in rows]


class TasksDeletionHandler:
    """ Personal data deletion for task progress: removes students' code and archived
    results and the link to the user; keeps status, score, and times for analysis.
    """

    @staticmethod
    def delete_user_data(user_id: int) -> None:
        get_db().execute(
            "UPDATE classaid_task_progress SET current_files='{}', final_result=NULL, user_id=-1 WHERE user_id=?", [user_id]
        )

    @staticmethod
    def delete_class_data(class_id: int) -> None:
        get_db().execute(
            "UPDATE classaid_task_progress SET current_files='{}', final_result=NULL, user_id=-1 WHERE class_id=?", [class_id]
        )
