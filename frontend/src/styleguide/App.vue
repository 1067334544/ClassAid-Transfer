<!-- SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
     SPDX-License-Identifier: AGPL-3.0-only -->
<script setup lang="ts">
/**
 * Style preview (task 7.2): every visual element of the ClassAid pages with sample data,
 * for reviewing the visual specification before the real pages are built.
 */
import { ref } from 'vue'
import { NButton, NCard, NInput, NSpace, NTag } from 'naive-ui'
import ModeBadge from '../components/ModeBadge.vue'
import ChatMessageView from '../components/ChatMessageView.vue'
import RunResultView from '../components/RunResultView.vue'
import CodeEditor from '../components/CodeEditor.vue'
import MarkdownView from '../components/MarkdownView.vue'
import { MODES, MODE_DESCRIPTIONS, type Mode } from '../theme'
import type { ChatMessage, RunResult } from '../types'

const swatches = [
  ['primary', 'Primary'], ['primary-soft', 'Primary soft'], ['text', 'Text'], ['text-muted', 'Text muted'],
  ['border', 'Border'], ['bg', 'Background'], ['success', 'Success'], ['error', 'Error'], ['warning', 'Warning'], ['info', 'Info'],
]
const modeSwatches = MODES.flatMap((m) => [[`mode-${m}`, `${m}`], [`mode-${m}-soft`, `${m} soft`]])

const code = ref(`public boolean remove(int value) {
    if (head == null) {
        return false;
    }
    Node prev = head;
    while (prev.next != null && prev.next.value != value) {
        prev = prev.next;
    }
    // TODO: what if the head holds the value?
    prev.next = prev.next.next;
    size--;
    return true;
}`)

const now = '2026-10-14 10:00:00'
const chat: ChatMessage[] = [
  { id: 1, role: 'student', content: 'Why does removeHead fail? My list still starts with 1.', feedback_type: null, origin: null, notice_kind: null, reply_to: null, rating: null, created_at: now },
  { id: 2, role: 'assistant', content: 'Good question! Look at where your loop **starts**: `prev` begins at `head`, so which node is the first one you ever compare against `value`?\n\n- Trace `remove(1)` on `[1, 2, 3]` by hand.\n- What should `head` point to after removing the first node?', feedback_type: 'heuristic', origin: 'user_triggered', notice_kind: null, reply_to: 1, rating: 1, created_at: now },
  { id: 3, role: 'student', content: 'Can you just show me the fix?', feedback_type: null, origin: null, notice_kind: null, reply_to: null, rating: null, created_at: now },
  { id: 4, role: 'assistant', content: 'Your loop compares `prev.next.value`, so the head node itself is never checked. Handle it before the loop:\n\n```java\nif (head.value == value) {\n    head = head.next;\n    size--;\n    return true;\n}\n```\n\nThis works because removing the head only requires moving the `head` reference to the second node.', feedback_type: 'technical', origin: 'user_triggered', notice_kind: null, reply_to: 3, rating: null, created_at: now },
  { id: 5, role: 'notice', content: 'AI feedback is currently paused by your instructor.  Keep working: try tracing your code or running the tests.', feedback_type: null, origin: null, notice_kind: 'silent', reply_to: 3, rating: null, created_at: now },
  { id: 6, role: 'notice', content: 'The AI assistant could not respond right now.  Please try again in a moment.', feedback_type: null, origin: null, notice_kind: 'error', reply_to: 3, rating: null, created_at: now },
]

const base = { stdout: '', stderr: '', stdout_truncated: false, stderr_truncated: false, exit_code: 0, limit_exceeded: null, exception: null, tests: null, score: null, duration_ms: 812, internal_error: null } as const
const results: { title: string; result: RunResult }[] = [
  { title: 'Run: success', result: { ...base, kind: 'run', status: 'ok', compile: { ok: true, diagnostics: [] }, stdout: 'before: [3, 5, 7] size=3\nremove(5) -> true\nafter:  [3, 7] size=2\n' } },
  { title: 'Run: compile error', result: { ...base, kind: 'run', status: 'compile_error', compile: { ok: false, diagnostics: [{ kind: 'error', file: 'IntLinkedList.java', line: 48, column: 25, in_tests: false, message: "';' expected" }] } } },
  { title: 'Run: exception', result: { ...base, kind: 'run', status: 'runtime_error', compile: { ok: true, diagnostics: [] }, exit_code: 1, exception: { type: 'java.lang.NullPointerException', message: 'Cannot read field "next" because "prev" is null', frames: [{ file: 'IntLinkedList.java', line: 52, method: 'remove', class: 'IntLinkedList' }, { file: 'Main.java', line: 8, method: 'main', class: 'Main' }] } } },
  { title: 'Run Tests: partial', result: { ...base, kind: 'tests', status: 'ok', compile: { ok: true, diagnostics: [] }, score: 3.2, tests: [
    { id: 'T#a', name: 'removeFromEmptyList()', status: 'passed', message: null, exception: null },
    { id: 'T#b', name: 'removeMiddle()', status: 'passed', message: null, exception: null },
    { id: 'T#c', name: 'removeHead()', status: 'failed', message: 'expected: <[2, 3]> but was: <[1, 2, 3]>', exception: null },
    { id: 'T#d', name: 'removeTail()', status: 'error', message: 'Cannot read field "next" because "prev" is null', exception: null },
    { id: 'T#e', name: 'sizeUpdates()', status: 'timeout', message: 'sizeUpdates() timed out after 2 seconds', exception: null },
  ] } },
]

const students: { name: string; mode: Mode; source: 'class' | 'student'; task: string }[] = [
  { name: 'Sam Student', mode: 'heuristic', source: 'class', task: 'Linked list: remove a value' },
  { name: 'Sky Student', mode: 'technical', source: 'student', task: 'Linked list: remove a value' },
  { name: 'Ana Student', mode: 'auto', source: 'student', task: '—' },
  { name: 'Lee Student', mode: 'silent', source: 'student', task: 'Linked list: remove a value' },
]
const question = ref('')
</script>

<template>
  <div class="sg">
    <header class="sg__header">
      <h1>ClassAid visual specification</h1>
      <p>Preview of every element used in the student workspace and instructor pages (sample data). Tokens live in <code>src/classaid/static/theme.css</code>.</p>
    </header>

    <section class="sg__section">
      <h2>Colors</h2>
      <div class="sg__swatches">
        <div v-for="[name, label] in swatches" :key="name" class="sg__swatch">
          <div class="sg__chip" :style="{ background: `var(--ca-${name})` }" />
          <span>{{ label }}</span>
        </div>
      </div>
      <h3>Feedback modes (paper §4.3: Auto purple, Technical blue, Heuristic yellow, Silent gray)</h3>
      <div class="sg__swatches">
        <div v-for="[name, label] in modeSwatches" :key="name" class="sg__swatch">
          <div class="sg__chip" :style="{ background: `var(--ca-${name})` }" />
          <span>{{ label }}</span>
        </div>
      </div>
    </section>

    <section class="sg__section">
      <h2>Typography</h2>
      <div class="sg__type">
        <div style="font-size: var(--ca-text-2xl); font-weight: 700">Linked list: remove a value</div>
        <div style="font-size: var(--ca-text-xl); font-weight: 600">Section heading</div>
        <div style="font-size: var(--ca-text-lg)">Body large — task descriptions</div>
        <div style="font-size: var(--ca-text-md)">Body — chat, panels, and controls. 中文界面示例：运行测试、完成任务。</div>
        <div style="font-size: var(--ca-text-sm); color: var(--ca-text-muted)">Small muted — metadata and hints</div>
        <div style="font-family: var(--ca-font-mono); font-size: var(--ca-text-md)">prev.next = prev.next.next; // monospace</div>
      </div>
    </section>

    <section class="sg__section">
      <h2>Buttons and controls</h2>
      <NSpace>
        <NButton type="primary">Run Tests</NButton>
        <NButton>Run</NButton>
        <NButton type="primary" ghost>Complete Task</NButton>
        <NButton tertiary>Cancel</NButton>
        <NButton type="primary" loading>Running…</NButton>
        <NButton disabled>Disabled</NButton>
        <NButton type="error" secondary>Clear individual mode</NButton>
      </NSpace>
      <NSpace style="margin-top: 12px">
        <NTag type="success" round>in progress</NTag>
        <NTag round>completed</NTag>
        <NTag type="warning" round>queued</NTag>
      </NSpace>
    </section>

    <section class="sg__section">
      <h2>Feedback mode badges</h2>
      <NSpace vertical>
        <NSpace align="center">
          <ModeBadge v-for="m in MODES" :key="m" :mode="m" size="small" />
        </NSpace>
        <NSpace align="center">
          <ModeBadge v-for="m in MODES" :key="m" :mode="m" />
        </NSpace>
        <NSpace align="center">
          <ModeBadge mode="technical" source="student" />
          <ModeBadge mode="heuristic" source="class" />
        </NSpace>
      </NSpace>
      <div class="sg__mode-banners">
        <div v-for="m in MODES" :key="m" class="sg__mode-banner">
          <ModeBadge :mode="m" size="large" />
          <span>{{ MODE_DESCRIPTIONS[m] }}</span>
        </div>
      </div>
    </section>

    <section class="sg__section">
      <h2>Student workspace (layout sketch)</h2>
      <div class="sg__workspace">
        <NCard class="sg__task" size="small" title="Linked list: remove a value">
          <template #header-extra><ModeBadge mode="heuristic" size="small" /></template>
          <MarkdownView source="Implement `remove(int value)`: remove the **first** node that holds `value` and return `true`, or return `false` if it is not in the list. Keep `size()` correct." />
        </NCard>
        <div class="sg__editor">
          <div class="sg__toolbar">
            <span class="sg__file">IntLinkedList.java</span>
            <span class="sg__file sg__file--inactive">Main.java</span>
            <NSpace style="margin-left: auto">
              <NButton size="small">Run</NButton>
              <NButton size="small" type="primary">Run Tests</NButton>
              <NButton size="small" type="primary" ghost>Complete Task</NButton>
            </NSpace>
          </div>
          <div style="height: 300px"><CodeEditor v-model="code" /></div>
        </div>
        <NCard class="sg__chat" size="small" title="Ask the TA Agent">
          <div class="sg__chat-list">
            <ChatMessageView v-for="m in chat" :key="m.id" :message="m" />
          </div>
          <NInput v-model:value="question" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" placeholder="Ask about your code…" />
          <NButton type="primary" size="small" style="margin-top: 8px">Send</NButton>
        </NCard>
      </div>
    </section>

    <section class="sg__section">
      <h2>Output panel</h2>
      <div class="sg__results">
        <NCard v-for="r in results" :key="r.title" size="small" :title="r.title">
          <RunResultView :result="r.result" />
        </NCard>
      </div>
    </section>

    <section class="sg__section">
      <h2>Instructor mode control (list)</h2>
      <NCard size="small">
        <div class="sg__class-row">
          <span>Class mode</span>
          <ModeBadge mode="heuristic" />
          <NSpace style="margin-left: auto">
            <NButton v-for="m in MODES" :key="m" size="small">Set all: {{ m }}</NButton>
          </NSpace>
        </div>
        <table class="sg__table">
          <thead><tr><th>Student</th><th>Effective mode</th><th>Current task</th><th /></tr></thead>
          <tbody>
            <tr v-for="s in students" :key="s.name">
              <td>{{ s.name }}</td>
              <td><ModeBadge :mode="s.mode" :source="s.source" size="small" /></td>
              <td class="sg__muted">{{ s.task }}</td>
              <td><NSpace><NButton v-for="m in MODES" :key="m" size="tiny" quaternary>{{ m }}</NButton></NSpace></td>
            </tr>
          </tbody>
        </table>
      </NCard>
    </section>
  </div>
</template>

<style scoped>
.sg { max-width: 1240px; margin: 0 auto; padding: var(--ca-space-5) var(--ca-space-4) var(--ca-space-6); font-family: var(--ca-font); color: var(--ca-text); }
.sg__header h1 { font-size: var(--ca-text-2xl); font-weight: 700; margin: 0 0 4px; }
.sg__header p { color: var(--ca-text-muted); margin: 0; }
.sg__section { background: var(--ca-surface); border: 1px solid var(--ca-border); border-radius: var(--ca-radius-lg); box-shadow: var(--ca-shadow-sm); padding: var(--ca-space-5); margin-top: var(--ca-space-5); }
.sg__section h2 { font-size: var(--ca-text-xl); font-weight: 600; margin: 0 0 var(--ca-space-4); }
.sg__section h3 { font-size: var(--ca-text-md); font-weight: 600; color: var(--ca-text-muted); margin: var(--ca-space-4) 0 var(--ca-space-3); }
.sg__swatches { display: flex; flex-wrap: wrap; gap: var(--ca-space-3); }
.sg__swatch { display: flex; flex-direction: column; align-items: center; gap: 4px; font-size: var(--ca-text-xs); color: var(--ca-text-muted); width: 92px; }
.sg__chip { width: 92px; height: 44px; border-radius: var(--ca-radius-sm); border: 1px solid var(--ca-border); }
.sg__type > div { margin-bottom: 6px; }
.sg__mode-banners { display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--ca-space-3); margin-top: var(--ca-space-4); }
.sg__mode-banner { display: flex; align-items: center; gap: var(--ca-space-3); padding: var(--ca-space-3); border: 1px solid var(--ca-border); border-radius: var(--ca-radius); font-size: var(--ca-text-sm); color: var(--ca-text-muted); }
.sg__workspace { display: grid; grid-template-columns: 280px minmax(0, 1fr) 340px; gap: var(--ca-space-4); align-items: start; }
.sg__toolbar { display: flex; align-items: center; gap: var(--ca-space-2); margin-bottom: var(--ca-space-2); }
.sg__file { font-family: var(--ca-font-mono); font-size: var(--ca-text-sm); padding: 4px 10px; border-radius: var(--ca-radius-sm); background: var(--ca-primary-soft); color: var(--ca-primary); }
.sg__file--inactive { background: transparent; color: var(--ca-text-muted); }
.sg__chat-list { max-height: 420px; overflow-y: auto; margin-bottom: var(--ca-space-3); }
.sg__results { display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--ca-space-4); }
.sg__class-row { display: flex; align-items: center; gap: var(--ca-space-3); margin-bottom: var(--ca-space-3); font-weight: 600; }
.sg__table { width: 100%; border-collapse: collapse; font-size: var(--ca-text-sm); }
.sg__table th { text-align: left; color: var(--ca-text-muted); font-weight: 500; padding: 8px; border-bottom: 1px solid var(--ca-border); }
.sg__table td { padding: 8px; border-bottom: 1px solid var(--ca-border); }
.sg__muted { color: var(--ca-text-muted); }
</style>
