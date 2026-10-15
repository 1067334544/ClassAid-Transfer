// SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
// SPDX-License-Identifier: AGPL-3.0-only

/** Startup data injected by the Flask page shell (templates/classaid_app.html). */
export interface Bootstrap {
  page: string
  apiBase: string
  user: { id: number; name: string }
  classId: number
  className: string
  role: 'instructor' | 'student'
  [key: string]: unknown
}

export function readBootstrap(): Bootstrap {
  const el = document.getElementById('classaid-bootstrap')
  if (!el?.textContent) {
    throw new Error('Missing #classaid-bootstrap data')
  }
  return JSON.parse(el.textContent) as Bootstrap
}
