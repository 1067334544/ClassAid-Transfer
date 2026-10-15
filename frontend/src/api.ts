// SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
// SPDX-License-Identifier: AGPL-3.0-only

/**
 * JSON API client.  Requests are same-origin (session cookie), always send a JSON body
 * with Content-Type: application/json, and turn non-2xx responses into ApiError with
 * the server's message.
 */

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

let apiBase = '/classaid/api'

export function setApiBase(base: string): void {
  apiBase = base.replace(/\/$/, '')
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = {
    method,
    credentials: 'same-origin',
    headers: { Accept: 'application/json' },
  }
  if (body !== undefined) {
    init.headers = { ...init.headers, 'Content-Type': 'application/json' }
    init.body = JSON.stringify(body)
  }
  let response: Response
  try {
    response = await fetch(`${apiBase}${path}`, init)
  } catch {
    throw new ApiError(0, 'Could not reach the server.  Check your connection.')
  }
  if (response.redirected && response.url.includes('/auth/login')) {
    throw new ApiError(401, 'Your session has expired.  Please log in again.')
  }
  const isJson = response.headers.get('Content-Type')?.includes('application/json')
  const data = isJson ? await response.json() : null
  if (!response.ok) {
    throw new ApiError(response.status, (data && data.error) || `Request failed (${response.status}).`)
  }
  return data as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body: unknown = {}) => request<T>('POST', path, body),
  put: <T>(path: string, body: unknown = {}) => request<T>('PUT', path, body),
  delete: <T>(path: string) => request<T>('DELETE', path, {}),
}
