// SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ChatMessageView from '../components/ChatMessageView.vue'
import ModeBadge from '../components/ModeBadge.vue'
import RunResultView from '../components/RunResultView.vue'
import MarkdownView from '../components/MarkdownView.vue'
import type { ChatMessage, RunResult } from '../types'

const base: ChatMessage = {
  id: 1, role: 'assistant', content: 'Look at **head**.', feedback_type: 'heuristic', origin: 'user_triggered',
  notice_kind: null, reply_to: null, rating: null, created_at: '2026-10-14 10:00:00',
}

describe('ChatMessageView', () => {
  it('labels AI feedback with its type and offers ratings', async () => {
    const wrapper = mount(ChatMessageView, { props: { message: base } })
    expect(wrapper.find('.ca-msg__type').text()).toBe('Heuristic')
    expect(wrapper.html()).toContain('<strong>head</strong>')
    await wrapper.find('[aria-label="Helpful"]').trigger('click')
    expect(wrapper.emitted('rate')).toEqual([[1]])
  })

  it('clicking the current rating withdraws it', async () => {
    const wrapper = mount(ChatMessageView, { props: { message: { ...base, rating: -1 } } })
    await wrapper.find('[aria-label="Not helpful"]').trigger('click')
    expect(wrapper.emitted('rate')).toEqual([[null]])
  })

  it('shows notices as notices, never as AI feedback, without ratings', () => {
    const notice: ChatMessage = { ...base, role: 'notice', feedback_type: null, origin: null, notice_kind: 'silent', content: 'AI feedback is currently paused by your instructor.' }
    const wrapper = mount(ChatMessageView, { props: { message: notice } })
    expect(wrapper.find('.ca-msg--notice').exists()).toBe(true)
    expect(wrapper.find('.ca-msg--assistant').exists()).toBe(false)
    expect(wrapper.find('[aria-label="Helpful"]').exists()).toBe(false)
  })

  it('hides ratings when read-only', () => {
    const wrapper = mount(ChatMessageView, { props: { message: base, readonly: true } })
    expect(wrapper.find('[aria-label="Helpful"]').exists()).toBe(false)
  })
})

describe('ModeBadge', () => {
  it('shows the mode name and source', () => {
    const wrapper = mount(ModeBadge, { props: { mode: 'technical', source: 'student' } })
    expect(wrapper.text()).toContain('Technical')
    expect(wrapper.text()).toContain('individual')
    expect(wrapper.attributes('data-mode')).toBe('technical')
  })
})

describe('MarkdownView', () => {
  it('escapes raw HTML', () => {
    const wrapper = mount(MarkdownView, { props: { source: '<script>alert(1)</script> <img src=x onerror=alert(1)>' } })
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.find('img').exists()).toBe(false)
  })
})

const result = (over: Partial<RunResult>): RunResult => ({
  kind: 'tests', status: 'ok', compile: { ok: true, diagnostics: [] }, stdout: '', stderr: '', stdout_truncated: false,
  stderr_truncated: false, exit_code: 0, limit_exceeded: null, exception: null, tests: null, score: null, duration_ms: 1,
  internal_error: null, ...over,
})

describe('RunResultView', () => {
  it('summarizes test results and the score', () => {
    const wrapper = mount(RunResultView, { props: { result: result({
      score: 2.5,
      tests: [
        { id: 'T#a', name: 'a()', status: 'passed', message: null, exception: null },
        { id: 'T#b', name: 'b()', status: 'failed', message: 'expected: <1> but was: <2>', exception: null },
      ],
    }) } })
    expect(wrapper.find('.ca-result__headline').text()).toBe('1 of 2 tests passed')
    expect(wrapper.find('.ca-result__score').text()).toContain('2.5')
    expect(wrapper.text()).toContain('expected: <1> but was: <2>')
  })

  it('shows compile errors with their location', () => {
    const wrapper = mount(RunResultView, { props: { result: result({
      kind: 'run', status: 'compile_error',
      compile: { ok: false, diagnostics: [{ kind: 'error', file: 'A.java', line: 3, column: 9, in_tests: false, message: "';' expected" }] },
    }) } })
    expect(wrapper.find('.ca-result__headline').text()).toBe('Compilation failed')
    expect(wrapper.find('.ca-result__loc').text()).toBe('A.java:3:9')
  })

  it('never shows program output for test runs', () => {
    const wrapper = mount(RunResultView, { props: { result: result({ stdout: 'SECRET' }) } })
    expect(wrapper.text()).not.toContain('SECRET')
  })
})
