// SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
// SPDX-License-Identifier: AGPL-3.0-only

/** Types for the workspace API responses. */
import type { Mode } from '../theme'
import type { ChatMessage, RunResult } from '../types'

export interface TaskView {
  id: number
  title: string
  description: string
  examples: string
  entry: string
  starter_files: Record<string, string>
}

export interface Progress {
  id: number
  task_id: number
  status: 'in_progress' | 'completed'
  files: Record<string, string>
  score: number | null
  final_result: RunResult | null
  started_at: string
  completed_at: string | null
}

export interface TaskListItem {
  id: number
  title: string
  status: 'not_started' | 'in_progress' | 'completed'
  score: number | null
  available?: string
}

export type JobKind = 'run' | 'tests' | 'complete' | 'feedback'

export interface JobView {
  id: number
  kind: JobKind
  status: 'queued' | 'running' | 'done' | 'failed'
  result?: RunResult
  error?: string
}

export interface StateResponse {
  mode: { mode: Mode; source: 'class' | 'student' }
  messages?: ChatMessage[]
  task_status?: 'in_progress' | 'completed' | null
  jobs: JobView[]
}
