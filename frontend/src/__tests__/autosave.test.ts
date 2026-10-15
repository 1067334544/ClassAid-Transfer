// SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createAutosave } from '../workspace/autosave'

describe('createAutosave', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('saves once, 2 s after the last edit (well within the 5 s requirement)', async () => {
    const save = vi.fn(() => Promise.resolve())
    const autosave = createAutosave(save)
    autosave.schedule()
    await vi.advanceTimersByTimeAsync(1500)
    autosave.schedule()            // another edit restarts the delay
    await vi.advanceTimersByTimeAsync(1500)
    expect(save).not.toHaveBeenCalled()
    expect(autosave.status.value).toBe('pending')
    await vi.advanceTimersByTimeAsync(600)
    expect(save).toHaveBeenCalledTimes(1)
    expect(autosave.status.value).toBe('saved')
  })

  it('flush saves pending edits immediately', async () => {
    const save = vi.fn(() => Promise.resolve())
    const autosave = createAutosave(save)
    autosave.schedule()
    await autosave.flush()
    expect(save).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(5000)
    expect(save).toHaveBeenCalledTimes(1)
  })

  it('reports errors and saves again after the next edit', async () => {
    const save = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue(undefined)
    const autosave = createAutosave(save)
    autosave.schedule()
    await vi.advanceTimersByTimeAsync(2100)
    expect(autosave.status.value).toBe('error')
    autosave.schedule()
    await vi.advanceTimersByTimeAsync(2100)
    expect(autosave.status.value).toBe('saved')
    expect(save).toHaveBeenCalledTimes(2)
  })

  it('an edit during a save triggers one more save afterwards', async () => {
    let resolve!: () => void
    const save = vi.fn(() => new Promise<void>((r) => { resolve = r }))
    const autosave = createAutosave(save, 100)
    autosave.schedule()
    await vi.advanceTimersByTimeAsync(150)
    expect(autosave.status.value).toBe('saving')
    autosave.schedule()
    await vi.advanceTimersByTimeAsync(150)   // timer fires while the first save is in flight
    resolve()
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(150)
    expect(save).toHaveBeenCalledTimes(2)
  })
})
