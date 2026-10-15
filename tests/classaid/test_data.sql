-- SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
--
-- SPDX-License-Identifier: AGPL-3.0-only

-- Test data for the ClassAid application.
-- Local logins: <username> / <username>pw  (e.g., student1 / student1pw)

INSERT INTO classes (id, name, enabled)
VALUES
    (1, 'CS2-A', 1),
    (2, 'CS2-B', 1);

INSERT INTO users (id, auth_provider, full_name, email, auth_name, is_admin, is_tester, query_tokens)
VALUES
    -- provider 1 = local
    (101, 1, 'Ida Instructor', null, 'instructor', false, false, 0),
    (102, 1, 'Sam Student', null, 'student1', false, false, 0),
    (103, 1, 'Sky Student', null, 'student2', false, false, 0),
    (104, 1, 'Olu Outsider', null, 'outsider', false, false, 0),  -- instructor of CS2-B only; no role in CS2-A
    (105, 1, 'Ada Admin', null, 'admin', true, false, 0);

-- Both classes have a (fake) class API key so students can reach the (mocked) LLM.
INSERT INTO classes_user (class_id, llm_api_key, link_key, link_reg_expires, link_anon_login, creator_user_id, model_id)
VALUES
    (1, 'fake-class-key', 'v2.cs2a', '9999-12-31', 0, 101, 1),
    (2, 'fake-class-key', 'v2.cs2b', '9999-12-31', 0, 104, 1);

INSERT INTO auth_local (user_id, username, password)
VALUES
    (101, 'instructor', 'pbkdf2:sha256:1000$VY9FAULJWEIPPQqP$8604fcd6508bb50484da869cd404b59f9eedf4dcd13e671a3667440e15db06ea'),
    (102, 'student1', 'pbkdf2:sha256:1000$oEsWBpcMGAcjKNd5$9f3d72f8c4a580f6eeb346e1cb1263451ed44a224d97a46df1ecaa2a971036a4'),
    (103, 'student2', 'pbkdf2:sha256:1000$ekpiZ2RDML7hkYM0$38f15f502749f3931575552e744842d9bad349c6cb3770dfca09a27bfef327b7'),
    (104, 'outsider', 'pbkdf2:sha256:1000$IG6Fj7GZztT1vdPd$09e1c820e6c0a4d6cbe7c4205817c25c47217de9e40a8815443042e63b640f4e'),
    (105, 'admin', 'pbkdf2:sha256:1000$So4Ojm5m1lFGWOwS$6e18b7f615effc0b2424a12a8826b09caa4f3ca7177ca7639d3d203ea897af98');

INSERT INTO roles (id, user_id, class_id, role)
VALUES
    (1, 101, 1, 'instructor'),
    (2, 102, 1, 'student'),
    (3, 103, 1, 'student'),
    (4, 104, 2, 'instructor');
