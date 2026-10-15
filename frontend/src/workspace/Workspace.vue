<!-- SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
     SPDX-License-Identifier: AGPL-3.0-only -->
<script setup lang="ts">
/**
 * Student task workspace: task panel, editor (autosaved), Run / Run Tests / Complete Task,
 * output panel, and the TA Agent chat.  Polls /state every 3 s for the effective mode,
 * new chat messages, and the status of pending jobs.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { NAlert, NButton, NInput, NSpin, NTag, NTooltip, useDialog, useMessage } from 'naive-ui'
import CodeEditor from '../components/CodeEditor.vue'
import ChatMessageView from '../components/ChatMessageView.vue'
import MarkdownView from '../components/MarkdownView.vue'
import ModeBadge from '../components/ModeBadge.vue'
import RunResultView from '../components/RunResultView.vue'
import { api, ApiError } from '../api'
import type { Bootstrap } from '../bootstrap'
import { MODE_DESCRIPTIONS, MODE_LABELS, type Mode } from '../theme'
import type { ChatMessage, RunResult } from '../types'
import { createAutosave } from './autosave'
import type { JobKind, JobView, Progress, StateResponse, TaskView } from './types'

const props = defineProps<{ bootstrap: Bootstrap; taskId: number }>()
const POLL_MS = 3000

const toast = useMessage()
const dialog = useDialog()

const task = ref<TaskView | null>(null)
const progress = ref<Progress | null>(null)
const files = ref<Record<string, string>>({})
const activeFile = ref('')
const loadError = ref('')

const mode = ref<{ mode: Mode; source: 'class' | 'student' } | null>(null)
const messages = ref<ChatMessage[]>([])
const question = ref('')
const asking = ref(false)

const pendingJobs = ref<{ id: number; kind: JobKind; status: JobView['status'] }[]>([])
const lastResult = ref<RunResult | null>(null)
const lastError = ref('')

const chatList = ref<HTMLElement | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null

const readonly = computed(() => progress.value?.status === 'completed')
const runJob = computed(() => pendingJobs.value.find((j) => j.kind === 'run' || j.kind === 'tests' || j.kind === 'complete') ?? null)
const thinking = computed(() => pendingJobs.value.some((j) => j.kind === 'feedback'))
const fileNames = computed(() => Object.keys(files.value).sort((a, b) => (a === `${task.value?.entry}.java` ? 1 : b === `${task.value?.entry}.java` ? -1 : a.localeCompare(b))))
const lastMessageId = computed(() => messages.value.reduce((max, m) => Math.max(max, m.id), 0))
const shownResult = computed(() => (readonly.value ? progress.value?.final_result ?? null : lastResult.value))

const autosave = createAutosave(async () => {
  await api.put(`/tasks/${props.taskId}/code`, { files: files.value })
})

const SAVE_TEXT = { saved: 'Saved', pending: 'Unsaved changes', saving: 'Saving…', error: 'Not saved — retrying on next edit' } as const

function onEdit(value: string): void {
  if (readonly.value || files.value[activeFile.value] === value) return
  files.value = { ...files.value, [activeFile.value]: value }
  autosave.schedule()
}

async function load(): Promise<void> {
  const data = await api.get<{ task: TaskView; progress: Progress }>(`/tasks/${props.taskId}`)
  task.value = data.task
  progress.value = data.progress
  files.value = { ...data.progress.files }
  if (!activeFile.value || !(activeFile.value in files.value)) activeFile.value = fileNames.value[0] ?? ''
}

function scrollChat(): void {
  nextTick(() => chatList.value?.scrollTo({ top: chatList.value.scrollHeight, behavior: 'smooth' }))
}

async function poll(): Promise<void> {
  const jobs = pendingJobs.value.map((j) => j.id).join(',')
  let state: StateResponse
  try {
    state = await api.get<StateResponse>(`/state?task=${props.taskId}&after=${lastMessageId.value}&jobs=${jobs}`)
  } catch {
    return   // transient: try again on the next tick
  }
  if (mode.value && state.mode.mode !== mode.value.mode) {
    toast.info(`Your instructor changed the AI feedback mode to ${MODE_LABELS[state.mode.mode]}.`)
  }
  mode.value = state.mode
  if (state.messages?.length) {
    const known = new Set(messages.value.map((m) => m.id))
    messages.value.push(...state.messages.filter((m) => !known.has(m.id)))
    scrollChat()
  }
  for (const job of state.jobs) handleJob(job)
}

function handleJob(job: JobView): void {
  const pending = pendingJobs.value.find((j) => j.id === job.id)
  if (!pending) return
  pending.status = job.status
  if (job.status !== 'done' && job.status !== 'failed') return
  pendingJobs.value = pendingJobs.value.filter((j) => j.id !== job.id)
  if (job.status === 'failed') {
    lastError.value = job.error ?? 'Something went wrong.'
    if (job.kind === 'feedback') toast.error(lastError.value)
    return
  }
  if (job.kind === 'complete') {
    load().then(() => {
      dialog.success({
        title: 'Task completed',
        content: `Your score: ${progress.value?.score?.toFixed(1) ?? '–'} / 5`,
        positiveText: 'OK',
      })
    })
  } else if (job.result) {
    lastResult.value = job.result
  }
}

async function start(kind: 'run' | 'test' | 'complete'): Promise<void> {
  if (runJob.value || readonly.value) return
  lastError.value = ''
  autosave.cancel()
  try {
    const { job_id } = await api.post<{ job_id: number }>(`/tasks/${props.taskId}/${kind}`, { files: files.value })
    autosave.status.value = 'saved'   // running saves the code
    pendingJobs.value.push({ id: job_id, kind: kind === 'test' ? 'tests' : kind, status: 'queued' })
    setTimeout(poll, 600)
  } catch (e) {
    lastError.value = e instanceof ApiError ? e.message : 'Could not start the run.'
  }
}

function confirmComplete(): void {
  dialog.warning({
    title: 'Complete this task?',
    content: 'Your code will be checked by the instructor\'s tests and scored from 0 to 5. After completing, you can no longer edit the code or ask questions about this task.',
    positiveText: 'Complete task',
    negativeText: 'Keep working',
    onPositiveClick: () => { start('complete') },
  })
}

async function ask(): Promise<void> {
  const text = question.value.trim()
  if (!text || asking.value || readonly.value) return
  asking.value = true
  autosave.cancel()
  try {
    const { job_id } = await api.post<{ job_id: number; message_id: number }>(`/tasks/${props.taskId}/ask`, { question: text, files: files.value })
    autosave.status.value = 'saved'
    question.value = ''
    pendingJobs.value.push({ id: job_id, kind: 'feedback', status: 'queued' })
    await poll()
  } catch (e) {
    toast.error(e instanceof ApiError ? e.message : 'Could not send your question.')
  } finally {
    asking.value = false
  }
}

function onQuestionKey(event: KeyboardEvent): void {
  if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
    event.preventDefault()
    ask()
  }
}

async function rate(message: ChatMessage, value: 1 | -1 | null): Promise<void> {
  try {
    const res = await api.put<{ rating: 1 | -1 | null; message: string }>(`/messages/${message.id}/rating`, { value })
    message.rating = res.rating
    if (value !== null) toast.success(res.message)
  } catch (e) {
    toast.error(e instanceof ApiError ? e.message : 'Could not save your rating.')
  }
}

function warnUnsaved(event: BeforeUnloadEvent): void {
  if (autosave.status.value === 'pending' || autosave.status.value === 'saving') {
    autosave.flush()
    event.preventDefault()
  }
}

watch(readonly, (value) => { if (value) autosave.cancel() })

onMounted(async () => {
  try {
    await load()
    await poll()
    scrollChat()
    pollTimer = setInterval(poll, POLL_MS)
  } catch (e) {
    loadError.value = e instanceof ApiError ? e.message : 'Could not open this task.'
  }
  window.addEventListener('beforeunload', warnUnsaved)
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
  window.removeEventListener('beforeunload', warnUnsaved)
})
</script>

<template>
  <div class="ws">
    <NAlert v-if="loadError" type="error" :title="loadError" class="ws__alert">
      <a :href="String(bootstrap.taskListUrl)">Back to tasks</a>
    </NAlert>
    <div v-else-if="!task || !progress" class="ws__loading"><NSpin /></div>
    <template v-else>
      <header class="ws__bar">
        <a class="ws__back" :href="String(bootstrap.taskListUrl)">← Tasks</a>
        <h1 class="ws__title">{{ task.title }}</h1>
        <NTag v-if="readonly" round type="success">Completed · {{ progress.score?.toFixed(1) }} / 5</NTag>
        <NTag v-else round type="info">In progress</NTag>
        <div class="ws__bar-right">
          <span v-if="!readonly" class="ws__save" :class="`is-${autosave.status.value}`">{{ SAVE_TEXT[autosave.status.value] }}</span>
          <NTooltip v-if="mode">
            <template #trigger>
              <span class="ws__mode"><span class="ws__mode-label">AI feedback</span><ModeBadge :mode="mode.mode" /></span>
            </template>
            {{ MODE_DESCRIPTIONS[mode.mode] }}<template v-if="mode.source === 'student'"> (set for you by your instructor)</template>
          </NTooltip>
        </div>
      </header>

      <div class="ws__grid">
        <aside class="ws__panel ws__task">
          <h2 class="ws__panel-title">Task</h2>
          <MarkdownView :source="task.description" />
          <template v-if="task.examples">
            <h3 class="ws__subtitle">Examples</h3>
            <MarkdownView :source="task.examples" />
          </template>
          <p class="ws__hint">Run executes <code>{{ task.entry }}.main()</code>. Run Tests checks your code with the instructor's tests and shows your score.</p>
        </aside>

        <section class="ws__center">
          <div class="ws__toolbar">
            <div class="ws__tabs" role="tablist">
              <button
                v-for="name in fileNames" :key="name" type="button" role="tab" class="ws__tab"
                :class="{ 'is-active': name === activeFile }" :aria-selected="name === activeFile" @click="activeFile = name"
              >{{ name }}</button>
            </div>
            <div v-if="!readonly" class="ws__actions">
              <NButton size="small" :disabled="!!runJob" @click="start('run')">Run</NButton>
              <NButton size="small" type="primary" :disabled="!!runJob" @click="start('test')">Run Tests</NButton>
              <NButton size="small" type="primary" ghost :disabled="!!runJob" @click="confirmComplete">Complete Task</NButton>
            </div>
          </div>
          <div class="ws__editor">
            <CodeEditor v-if="activeFile" :key="activeFile" :model-value="files[activeFile]" :readonly="readonly" @update:model-value="onEdit" />
          </div>
          <div class="ws__panel ws__output" aria-live="polite">
            <div class="ws__output-head">
              <h2 class="ws__panel-title">{{ readonly ? 'Final result' : 'Output' }}</h2>
              <span v-if="runJob" class="ws__running"><NSpin :size="14" />
                {{ runJob.status === 'queued' ? 'Queued — waiting for a free runner…' : runJob.kind === 'complete' ? 'Checking your code…' : runJob.kind === 'tests' ? 'Running tests…' : 'Running…' }}
              </span>
            </div>
            <NAlert v-if="lastError" type="error" :title="lastError" />
            <RunResultView v-else-if="shownResult" :result="shownResult" />
            <p v-else-if="!runJob" class="ws__empty">Run your program or the tests to see the results here.</p>
          </div>
        </section>

        <aside class="ws__panel ws__chat">
          <h2 class="ws__panel-title">Ask the TA Agent</h2>
          <div v-if="mode?.mode === 'silent' && !readonly" class="ws__silent">AI feedback is paused by your instructor. You can still run your code and the tests.</div>
          <div ref="chatList" class="ws__messages">
            <p v-if="!messages.length" class="ws__empty">Ask a question about the task or your code.</p>
            <ChatMessageView v-for="m in messages" :key="m.id" :message="m" :readonly="readonly" @rate="(v) => rate(m, v)" />
            <div v-if="thinking" class="ws__thinking"><NSpin :size="14" /> TA Agent is thinking…</div>
          </div>
          <div v-if="!readonly" class="ws__composer">
            <NInput
              v-model:value="question" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :maxlength="4000"
              placeholder="Ask about your code… (Ctrl/⌘ + Enter to send)" @keydown="onQuestionKey"
            />
            <NButton type="primary" size="small" :loading="asking" :disabled="!question.trim()" @click="ask">Send</NButton>
          </div>
          <p v-else class="ws__empty">This task is completed; the conversation is read-only.</p>
        </aside>
      </div>
    </template>
  </div>
</template>

<style scoped>
.ws { padding: var(--ca-space-3) var(--ca-space-4) var(--ca-space-4); max-width: 1680px; margin: 0 auto; }
.ws__alert { max-width: 640px; margin: var(--ca-space-6) auto; }
.ws__loading { display: flex; justify-content: center; padding: var(--ca-space-6); }
.ws__bar { display: flex; align-items: center; gap: var(--ca-space-3); margin-bottom: var(--ca-space-3); flex-wrap: wrap; }
.ws__back { color: var(--ca-text-muted); font-size: var(--ca-text-sm); text-decoration: none; }
.ws__back:hover { color: var(--ca-primary); }
.ws__title { font-size: var(--ca-text-xl); font-weight: 700; margin: 0; }
.ws__bar-right { margin-left: auto; display: flex; align-items: center; gap: var(--ca-space-4); }
.ws__save { font-size: var(--ca-text-xs); color: var(--ca-text-subtle); }
.ws__save.is-pending, .ws__save.is-saving { color: var(--ca-warning); }
.ws__save.is-error { color: var(--ca-error); }
.ws__mode { display: inline-flex; align-items: center; gap: var(--ca-space-2); cursor: help; }
.ws__mode-label { font-size: var(--ca-text-xs); color: var(--ca-text-muted); }
.ws__grid { display: grid; grid-template-columns: 300px minmax(0, 1fr) 380px; gap: var(--ca-space-3); align-items: start; }
.ws__panel { background: var(--ca-surface); border: 1px solid var(--ca-border); border-radius: var(--ca-radius-lg); box-shadow: var(--ca-shadow-sm); padding: var(--ca-space-4); }
.ws__panel-title { font-size: var(--ca-text-sm); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; color: var(--ca-text-muted); margin: 0 0 var(--ca-space-3); }
.ws__subtitle { font-size: var(--ca-text-md); font-weight: 600; margin: var(--ca-space-4) 0 var(--ca-space-2); }
.ws__task { position: sticky; top: var(--ca-space-3); max-height: calc(100vh - 140px); overflow-y: auto; }
.ws__hint { margin-top: var(--ca-space-4); font-size: var(--ca-text-xs); color: var(--ca-text-muted); line-height: var(--ca-leading); }
.ws__center { display: flex; flex-direction: column; gap: var(--ca-space-3); min-width: 0; }
.ws__toolbar { display: flex; align-items: center; gap: var(--ca-space-2); flex-wrap: wrap; }
.ws__tabs { display: flex; gap: 4px; flex-wrap: wrap; }
.ws__tab { font-family: var(--ca-font-mono); font-size: var(--ca-text-sm); padding: 5px 12px; border-radius: var(--ca-radius-sm); border: 1px solid transparent; background: transparent; color: var(--ca-text-muted); cursor: pointer; }
.ws__tab:hover { background: var(--ca-surface-muted); }
.ws__tab.is-active { background: var(--ca-primary-soft); color: var(--ca-primary); border-color: color-mix(in srgb, var(--ca-primary) 25%, transparent); }
.ws__actions { margin-left: auto; display: flex; gap: var(--ca-space-2); }
.ws__editor { height: 52vh; min-height: 320px; background: var(--ca-surface); border-radius: var(--ca-radius-sm); }
.ws__output-head { display: flex; align-items: center; gap: var(--ca-space-3); margin-bottom: var(--ca-space-2); }
.ws__output-head .ws__panel-title { margin: 0; }
.ws__running { display: inline-flex; align-items: center; gap: 6px; font-size: var(--ca-text-sm); color: var(--ca-text-muted); }
.ws__empty { color: var(--ca-text-subtle); font-size: var(--ca-text-sm); margin: 0; }
.ws__chat { display: flex; flex-direction: column; position: sticky; top: var(--ca-space-3); height: calc(100vh - 140px); min-height: 420px; }
.ws__silent { background: var(--ca-mode-silent-soft); color: var(--ca-mode-silent-text); border-radius: var(--ca-radius-sm); padding: 8px 10px; font-size: var(--ca-text-sm); margin-bottom: var(--ca-space-3); }
.ws__messages { flex: 1; overflow-y: auto; padding-right: 4px; margin-bottom: var(--ca-space-3); }
.ws__thinking { display: flex; align-items: center; gap: 6px; font-size: var(--ca-text-sm); color: var(--ca-text-muted); padding: 4px 0; }
.ws__composer { display: flex; flex-direction: column; align-items: flex-end; gap: var(--ca-space-2); }
@media (max-width: 1100px) {
  .ws__grid { grid-template-columns: 1fr; }
  .ws__task, .ws__chat { position: static; height: auto; max-height: none; }
  .ws__chat { min-height: 360px; }
}
</style>
