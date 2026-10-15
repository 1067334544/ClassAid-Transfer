<!-- SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
     SPDX-License-Identifier: AGPL-3.0-only -->
<script setup lang="ts">
import { computed } from 'vue'
import type { RunResult } from '../types'

const props = defineProps<{ result: RunResult }>()

const STATUS_TEXT: Record<RunResult['status'], string> = {
  ok: 'Finished',
  compile_error: 'Compilation failed',
  runtime_error: 'Runtime error',
  timeout: 'Time limit exceeded',
  memory_exceeded: 'Memory limit exceeded',
  exited: 'Program called System.exit()',
  internal_error: 'Internal error',
}

const TEST_ICONS: Record<string, string> = { passed: '✓', failed: '✗', error: '✗', timeout: '⏱', skipped: '–', not_run: '–' }

const headline = computed(() => {
  const r = props.result
  if (r.kind === 'tests' && r.status === 'ok' && r.tests) {
    const passed = r.tests.filter((t) => t.status === 'passed').length
    return `${passed} of ${r.tests.length} tests passed`
  }
  return STATUS_TEXT[r.status]
})
const good = computed(() => {
  const r = props.result
  return r.status === 'ok' && (r.kind === 'run' || (r.tests ?? []).every((t) => t.status === 'passed'))
})
const errors = computed(() => (props.result.compile?.diagnostics ?? []).filter((d) => d.kind === 'error'))
</script>

<template>
  <div class="ca-result">
    <div class="ca-result__head" :class="good ? 'is-good' : 'is-bad'">
      <span class="ca-result__headline">{{ headline }}</span>
      <span v-if="result.kind === 'tests' && result.score !== null" class="ca-result__score">
        Score <strong>{{ result.score.toFixed(1) }}</strong> / 5
      </span>
      <span v-if="result.limit_exceeded === 'output'" class="ca-result__note">output truncated</span>
    </div>

    <ul v-if="errors.length" class="ca-result__diags">
      <li v-for="(d, i) in errors" :key="i">
        <span class="ca-result__loc">{{ d.in_tests ? 'Instructor tests' : `${d.file}:${d.line}:${d.column}` }}</span>
        <span class="ca-result__msg">{{ d.message }}</span>
      </li>
    </ul>

    <div v-if="result.exception" class="ca-result__exception">
      <div class="ca-result__ex-type">{{ result.exception.type }}<template v-if="result.exception.message">: {{ result.exception.message }}</template></div>
      <div v-for="(f, i) in result.exception.frames" :key="i" class="ca-result__frame">at {{ f.class }}.{{ f.method }} ({{ f.file }}:{{ f.line }})</div>
    </div>

    <ul v-if="result.tests" class="ca-result__tests">
      <li v-for="t in result.tests" :key="t.id" :class="`is-${t.status}`">
        <span class="ca-result__icon" aria-hidden="true">{{ TEST_ICONS[t.status] }}</span>
        <span class="ca-result__test-name">{{ t.name }}</span>
        <span v-if="t.message" class="ca-result__test-msg">{{ t.message }}</span>
      </li>
    </ul>

    <pre v-if="result.kind === 'run' && (result.stdout || result.stderr)" class="ca-result__output"><span>{{ result.stdout }}</span><span class="ca-result__stderr">{{ result.stderr }}</span></pre>
  </div>
</template>

<style scoped>
.ca-result { font-size: var(--ca-text-sm); }
.ca-result__head { display: flex; align-items: center; gap: var(--ca-space-3); padding: 8px 12px; border-radius: var(--ca-radius-sm); font-weight: 600; }
.ca-result__head.is-good { background: var(--ca-success-soft); color: var(--ca-success); }
.ca-result__head.is-bad { background: var(--ca-error-soft); color: var(--ca-error); }
.ca-result__score { margin-left: auto; font-weight: 500; color: var(--ca-text); }
.ca-result__score strong { font-size: var(--ca-text-lg); }
.ca-result__note { font-weight: 500; font-size: var(--ca-text-xs); opacity: 0.8; }
.ca-result__diags, .ca-result__tests { list-style: none; margin: var(--ca-space-2) 0 0; padding: 0; }
.ca-result__diags li { display: flex; gap: var(--ca-space-2); padding: 4px 0; font-family: var(--ca-font-mono); }
.ca-result__loc { color: var(--ca-error); white-space: nowrap; }
.ca-result__exception { margin-top: var(--ca-space-2); font-family: var(--ca-font-mono); }
.ca-result__ex-type { color: var(--ca-error); font-weight: 600; }
.ca-result__frame { color: var(--ca-text-muted); padding-left: var(--ca-space-4); }
.ca-result__tests li { display: flex; align-items: baseline; gap: var(--ca-space-2); padding: 5px 0; border-bottom: 1px solid var(--ca-border); }
.ca-result__tests li:last-child { border-bottom: 0; }
.ca-result__icon { width: 1.2em; text-align: center; font-weight: 700; }
.is-passed .ca-result__icon { color: var(--ca-success); }
.is-failed .ca-result__icon, .is-error .ca-result__icon { color: var(--ca-error); }
.is-timeout .ca-result__icon { color: var(--ca-warning); }
.ca-result__test-name { font-family: var(--ca-font-mono); }
.ca-result__test-msg { color: var(--ca-text-muted); }
.ca-result__output {
  margin: var(--ca-space-2) 0 0;
  background: #1e2230;
  color: #e6e9f0;
  border-radius: var(--ca-radius-sm);
  padding: var(--ca-space-3);
  font-family: var(--ca-font-mono);
  font-size: var(--ca-text-sm);
  white-space: pre-wrap;
  max-height: 260px;
  overflow: auto;
}
.ca-result__stderr { color: #ff9b9b; }
</style>
