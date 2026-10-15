-- SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
--
-- SPDX-License-Identifier: AGPL-3.0-only

-- Feedback modes.  A student's effective mode is their individual mode if set,
-- otherwise the class mode (default 'heuristic' when a class has no settings row).
DROP TABLE IF EXISTS classaid_class_settings;
CREATE TABLE classaid_class_settings (
    class_id   INTEGER PRIMARY KEY,
    class_mode TEXT NOT NULL CHECK (class_mode IN ('heuristic', 'technical', 'auto', 'silent')),
    updated_at DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
    FOREIGN KEY(class_id) REFERENCES classes(id)
);

DROP TABLE IF EXISTS classaid_student_modes;
CREATE TABLE classaid_student_modes (
    class_id   INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    mode       TEXT NOT NULL CHECK (mode IN ('heuristic', 'technical', 'auto', 'silent')),
    updated_at DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
    PRIMARY KEY (class_id, user_id),
    FOREIGN KEY(class_id) REFERENCES classes(id),
    FOREIGN KEY(user_id) REFERENCES users(id)
);

-- Chat messages in a student's task workspace.
--   role 'student':   a question
--   role 'assistant': AI feedback (feedback_type heuristic|technical; origin user_triggered, later proactive)
--   role 'notice':    a system notice that is NOT AI feedback (notice_kind silent|error)
DROP TABLE IF EXISTS classaid_messages;
CREATE TABLE classaid_messages (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    progress_id    INTEGER NOT NULL,
    user_id        INTEGER NOT NULL,
    class_id       INTEGER NOT NULL,
    task_id        INTEGER NOT NULL,
    role           TEXT NOT NULL CHECK (role IN ('student', 'assistant', 'notice')),
    content        TEXT NOT NULL,
    feedback_type  TEXT CHECK (feedback_type IN ('heuristic', 'technical')),
    origin         TEXT CHECK (origin IN ('user_triggered', 'proactive')),
    notice_kind    TEXT CHECK (notice_kind IN ('silent', 'error')),
    reply_to       INTEGER,          -- for assistant/notice messages: the student message answered
    generation_id  INTEGER,
    current_rating INTEGER CHECK (current_rating IN (-1, 1)),  -- convenience copy; rating history is in classaid_events
    created_at     DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
    FOREIGN KEY(progress_id) REFERENCES classaid_task_progress(id),
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(class_id) REFERENCES classes(id),
    FOREIGN KEY(reply_to) REFERENCES classaid_messages(id),
    FOREIGN KEY(generation_id) REFERENCES classaid_generations(id)
);
DROP INDEX IF EXISTS classaid_messages_by_progress;
CREATE INDEX classaid_messages_by_progress ON classaid_messages(progress_id, id);
DROP INDEX IF EXISTS classaid_messages_by_user;
CREATE INDEX classaid_messages_by_user ON classaid_messages(user_id, id);

-- One record per feedback generation attempt (generated, suppressed by Silent mode, or failed):
-- everything needed to reconstruct why which help was (or was not) given.
DROP TABLE IF EXISTS classaid_generations;
CREATE TABLE classaid_generations (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL,
    class_id         INTEGER NOT NULL,
    task_id          INTEGER NOT NULL,
    question_id      INTEGER NOT NULL,     -- classaid_messages.id of the student question
    trigger_event_id INTEGER NOT NULL,     -- classaid_events.id of the triggering 'question' event
    trigger          TEXT NOT NULL DEFAULT 'user_triggered',
    effective_mode   TEXT NOT NULL CHECK (effective_mode IN ('heuristic', 'technical', 'auto', 'silent')),
    mode_source      TEXT NOT NULL CHECK (mode_source IN ('class', 'student')),
    status           TEXT NOT NULL CHECK (status IN ('generated', 'suppressed', 'failed')),
    selected_type    TEXT CHECK (selected_type IN ('heuristic', 'technical')),
    selection        TEXT,                 -- JSON: Auto-mode selection {reason, fallback, ...}
    model            TEXT,                 -- model shortname
    prompt_version   TEXT,                 -- e.g. 'heuristic.user.v1'
    calls            TEXT NOT NULL DEFAULT '[]',  -- JSON list: every model call {purpose, prompt_version, messages, raw, text, latency_ms}
    displayed_text   TEXT,                 -- what the student was shown
    error            TEXT,
    latency_ms       INTEGER,
    created_at       DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(class_id) REFERENCES classes(id),
    FOREIGN KEY(question_id) REFERENCES classaid_messages(id),
    FOREIGN KEY(trigger_event_id) REFERENCES classaid_events(id)
);
DROP INDEX IF EXISTS classaid_generations_by_user;
CREATE INDEX classaid_generations_by_user ON classaid_generations(user_id, id);
