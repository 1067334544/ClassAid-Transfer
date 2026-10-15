-- SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
--
-- SPDX-License-Identifier: AGPL-3.0-only

-- Append-only activity log.  Application code only ever INSERTs into this table;
-- the sole exception is the component's DeletionHandler (user/class data deletion).
DROP TABLE IF EXISTS classaid_events;
CREATE TABLE classaid_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),  -- UTC, millisecond precision
    user_id     INTEGER NOT NULL,
    role_id     INTEGER,
    class_id    INTEGER NOT NULL,
    task_id     INTEGER,             -- config_items.id of a classaid_task (NULL for class-level events)
    type        TEXT NOT NULL,
    payload     TEXT NOT NULL DEFAULT '{}',  -- JSON
    snapshot_id INTEGER,
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(role_id) REFERENCES roles(id),
    FOREIGN KEY(class_id) REFERENCES classes(id),
    FOREIGN KEY(snapshot_id) REFERENCES classaid_snapshots(id)
);
DROP INDEX IF EXISTS classaid_events_by_class_ts;
CREATE INDEX classaid_events_by_class_ts ON classaid_events(class_id, ts);
DROP INDEX IF EXISTS classaid_events_by_user;
CREATE INDEX classaid_events_by_user ON classaid_events(user_id);
DROP INDEX IF EXISTS classaid_events_by_role;
CREATE INDEX classaid_events_by_role ON classaid_events(role_id);

-- Code snapshots, deduplicated per user by content hash (edit events are frequent).
DROP TABLE IF EXISTS classaid_snapshots;
CREATE TABLE classaid_snapshots (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    sha256  TEXT NOT NULL,
    files   TEXT NOT NULL,  -- JSON object: {filename: content}
    FOREIGN KEY(user_id) REFERENCES users(id)
);
DROP INDEX IF EXISTS classaid_snapshots_by_user_hash;
CREATE UNIQUE INDEX classaid_snapshots_by_user_hash ON classaid_snapshots(user_id, sha256) WHERE user_id != -1;

-- Background jobs (code runs, feedback generation).  Executed by an in-process
-- thread pool; status: queued -> running -> done | failed.
DROP TABLE IF EXISTS classaid_jobs;
CREATE TABLE classaid_jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed')),
    user_id     INTEGER NOT NULL,
    class_id    INTEGER NOT NULL,
    task_id     INTEGER,
    request     TEXT NOT NULL DEFAULT '{}',  -- JSON
    result      TEXT,                        -- JSON
    error       TEXT,
    created_at  DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
    started_at  DATETIME,
    finished_at DATETIME,
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(class_id) REFERENCES classes(id)
);
DROP INDEX IF EXISTS classaid_jobs_by_user;
CREATE INDEX classaid_jobs_by_user ON classaid_jobs(user_id, id);
