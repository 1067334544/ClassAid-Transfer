-- SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
--
-- SPDX-License-Identifier: AGPL-3.0-only

-- Task definitions are stored in config_items (item_type='classaid_task').

-- Per-student progress on a task: the latest code (autosaved), and the archived
-- final result once the task is completed.
DROP TABLE IF EXISTS classaid_task_progress;
CREATE TABLE classaid_task_progress (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    role_id       INTEGER,
    class_id      INTEGER NOT NULL,
    task_id       INTEGER NOT NULL,  -- config_items.id; deliberately no FK: deleting a task must not delete student work
    status        TEXT NOT NULL DEFAULT 'in_progress' CHECK (status IN ('in_progress', 'completed')),
    current_files TEXT NOT NULL,     -- JSON object {filename: content}
    score         REAL,              -- 0-5, set on completion
    final_result  TEXT,              -- JSON RunResult of the completion test run
    started_at    DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
    updated_at    DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
    completed_at  DATETIME,
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(role_id) REFERENCES roles(id),
    FOREIGN KEY(class_id) REFERENCES classes(id)
);
DROP INDEX IF EXISTS classaid_task_progress_by_user_task;
CREATE UNIQUE INDEX classaid_task_progress_by_user_task ON classaid_task_progress(user_id, task_id) WHERE user_id != -1;  -- not unique for deleted users
DROP INDEX IF EXISTS classaid_task_progress_by_class;
CREATE INDEX classaid_task_progress_by_class ON classaid_task_progress(class_id);
