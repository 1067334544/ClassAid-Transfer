// SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { ref, type Ref } from 'vue'

export type SaveStatus = 'saved' | 'pending' | 'saving' | 'error'

export interface Autosave {
  status: Ref<SaveStatus>
  /** Call after every edit: saves `delayMs` after the last edit. */
  schedule: () => void
  /** Save now if there are unsaved edits (e.g. before running code). */
  flush: () => Promise<void>
  cancel: () => void
}

/**
 * Debounced autosave.  The spec requires saving within 5 seconds of a pause in editing;
 * the default 2-second delay leaves room for a slow request.
 */
export function createAutosave(save: () => Promise<void>, delayMs = 2000): Autosave {
  const status = ref<SaveStatus>('saved')
  let timer: ReturnType<typeof setTimeout> | null = null
  let inFlight: Promise<void> | null = null
  let dirtyDuringSave = false

  async function run(): Promise<void> {
    timer = null
    if (inFlight) {
      dirtyDuringSave = true
      return inFlight
    }
    status.value = 'saving'
    inFlight = save()
      .then(() => {
        status.value = 'saved'
      })
      .catch(() => {
        status.value = 'error'
      })
      .finally(() => {
        inFlight = null
        if (dirtyDuringSave) {
          dirtyDuringSave = false
          schedule()
        }
      })
    return inFlight
  }

  function schedule(): void {
    status.value = 'pending'
    if (timer) clearTimeout(timer)
    timer = setTimeout(run, delayMs)
  }

  async function flush(): Promise<void> {
    if (timer) {
      clearTimeout(timer)
      await run()
    } else if (inFlight) {
      await inFlight
    }
  }

  function cancel(): void {
    if (timer) clearTimeout(timer)
    timer = null
  }

  return { status, schedule, flush, cancel }
}
