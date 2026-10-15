// SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
// SPDX-License-Identifier: AGPL-3.0-only

/** Types mirroring the ClassAid JSON API. */

export type FeedbackType = 'heuristic' | 'technical'

export interface ChatMessage {
  id: number
  role: 'student' | 'assistant' | 'notice'
  content: string
  feedback_type: FeedbackType | null
  origin: 'user_triggered' | 'proactive' | null
  notice_kind: 'silent' | 'error' | null
  reply_to: number | null
  rating: 1 | -1 | null
  created_at: string
}

export interface Diagnostic {
  kind: 'error' | 'warning'
  file: string | null
  line: number | null
  column: number | null
  in_tests: boolean
  message: string
}

export interface Frame { file: string; line: number; method: string; class: string }

export interface ExceptionInfo { type: string; message: string | null; frames: Frame[] }

export interface TestResult {
  id: string
  name: string
  status: 'passed' | 'failed' | 'error' | 'timeout' | 'skipped' | 'not_run'
  message: string | null
  exception: ExceptionInfo | null
}

export interface RunResult {
  kind: 'run' | 'tests'
  status: 'ok' | 'compile_error' | 'runtime_error' | 'timeout' | 'memory_exceeded' | 'exited' | 'internal_error'
  compile: { ok: boolean; diagnostics: Diagnostic[] } | null
  stdout: string
  stderr: string
  stdout_truncated: boolean
  stderr_truncated: boolean
  exit_code: number | null
  limit_exceeded: 'time' | 'memory' | 'output' | null
  exception: ExceptionInfo | null
  tests: TestResult[] | null
  score: number | null
  duration_ms: number
  internal_error: string | null
}
