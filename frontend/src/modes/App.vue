<!-- SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
     SPDX-License-Identifier: AGPL-3.0-only -->
<script setup lang="ts">
/**
 * Instructor mode control (paper §4.3): set the feedback mode for the whole class or for
 * individual students.  Refreshes every 5 s.  (The full real-time dashboard is phase P3.)
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { NAlert, NButton, NButtonGroup, NEmpty, NSpin, NTooltip, useDialog, useMessage } from 'naive-ui'
import ModeBadge from '../components/ModeBadge.vue'
import { api, ApiError } from '../api'
import type { Bootstrap } from '../bootstrap'
import { MODES, MODE_DESCRIPTIONS, MODE_LABELS, type Mode } from '../theme'

interface StudentRow {
  user_id: number
  name: string | null
  mode: Mode
  source: 'class' | 'student'
  current_task: { id: number; title: string | null; status: string } | null
}

const props = defineProps<{ bootstrap: Bootstrap }>()
const REFRESH_MS = 5000

const toast = useMessage()
const dialog = useDialog()
const classMode = ref<Mode | null>(null)
const students = ref<StudentRow[]>([])
const loading = ref(true)
const error = ref('')
const busy = ref(false)
let timer: ReturnType<typeof setInterval> | null = null

const counts = computed(() => Object.fromEntries(MODES.map((m) => [m, students.value.filter((s) => s.mode === m).length])) as Record<Mode, number>)
const individualCount = computed(() => students.value.filter((s) => s.source === 'student').length)

async function refresh(): Promise<void> {
  try {
    const data = await api.get<{ class_mode: Mode; students: StudentRow[] }>('/modes')
    classMode.value = data.class_mode
    students.value = data.students
    error.value = ''
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load the class.'
  } finally {
    loading.value = false
  }
}

function setAll(mode: Mode): void {
  const cleared = individualCount.value
  dialog.info({
    title: `Set the whole class to ${MODE_LABELS[mode]}?`,
    content: `Every student's feedback mode becomes ${MODE_LABELS[mode]}.` + (cleared ? ` This clears ${cleared} individual setting${cleared === 1 ? '' : 's'}.` : ''),
    positiveText: `Set all to ${MODE_LABELS[mode]}`,
    negativeText: 'Cancel',
    onPositiveClick: async () => {
      busy.value = true
      try {
        await api.put('/modes/class', { mode })
        toast.success(`Class mode set to ${MODE_LABELS[mode]}.`)
        await refresh()
      } catch (e) {
        toast.error(e instanceof ApiError ? e.message : 'Could not change the class mode.')
      } finally {
        busy.value = false
      }
    },
  })
}

async function setStudent(row: StudentRow, mode: Mode | null): Promise<void> {
  busy.value = true
  try {
    if (mode === null) {
      await api.delete(`/modes/students/${row.user_id}`)
      toast.success(`${row.name ?? 'Student'} now follows the class mode.`)
    } else {
      await api.put(`/modes/students/${row.user_id}`, { mode })
      toast.success(`${row.name ?? 'Student'} set to ${MODE_LABELS[mode]}.`)
    }
    await refresh()
  } catch (e) {
    toast.error(e instanceof ApiError ? e.message : 'Could not change the mode.')
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  await refresh()
  timer = setInterval(refresh, REFRESH_MS)
})
onBeforeUnmount(() => { if (timer) clearInterval(timer) })
</script>

<template>
  <div class="mc">
    <header class="mc__header">
      <div>
        <h1>Feedback mode control</h1>
        <p>{{ bootstrap.className }} · changes reach students' workspaces within a few seconds</p>
      </div>
      <NButton tag="a" :href="String(props.bootstrap.taskListUrl)">Tasks</NButton>
    </header>

    <NAlert v-if="error" type="error" :title="error" class="mc__alert" />
    <div v-if="loading" class="mc__loading"><NSpin /></div>
    <template v-else>
      <section class="mc__class">
        <div class="mc__class-mode">
          <span class="mc__label">Class mode</span>
          <ModeBadge v-if="classMode" :mode="classMode" size="large" />
          <span v-if="classMode" class="mc__desc">{{ MODE_DESCRIPTIONS[classMode] }}</span>
        </div>
        <div class="mc__set-all">
          <span class="mc__label">Set all students to</span>
          <NButtonGroup>
            <NTooltip v-for="m in MODES" :key="m">
              <template #trigger>
                <NButton :disabled="busy" :class="`mc__mode-btn mc__mode-btn--${m}`" @click="setAll(m)">{{ MODE_LABELS[m] }}</NButton>
              </template>
              {{ MODE_DESCRIPTIONS[m] }}
            </NTooltip>
          </NButtonGroup>
        </div>
        <div class="mc__counts">
          <span v-for="m in MODES" :key="m" class="mc__count"><ModeBadge :mode="m" size="small" /> {{ counts[m] }}</span>
          <span class="mc__count mc__count--muted">{{ individualCount }} individual</span>
        </div>
      </section>

      <NEmpty v-if="!students.length" description="No students in this class yet." class="mc__loading" />
      <section v-else class="mc__table-wrap">
        <table class="mc__table">
          <thead>
            <tr><th>Student</th><th>Effective mode</th><th>Current task</th><th class="mc__th-actions">Set individual mode</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in students" :key="row.user_id" :data-student="row.user_id">
              <td class="mc__name">{{ row.name ?? `Student ${row.user_id}` }}</td>
              <td><ModeBadge :mode="row.mode" :source="row.source" size="small" /></td>
              <td class="mc__task">
                <template v-if="row.current_task">{{ row.current_task.title }}<span v-if="row.current_task.status === 'completed'" class="mc__done"> · completed</span></template>
                <span v-else class="mc__muted">—</span>
              </td>
              <td class="mc__actions">
                <NButtonGroup size="tiny">
                  <NButton
                    v-for="m in MODES" :key="m" :disabled="busy"
                    :type="row.source === 'student' && row.mode === m ? 'primary' : 'default'"
                    :class="`mc__mode-btn mc__mode-btn--${m}`" @click="setStudent(row, m)"
                  >{{ MODE_LABELS[m] }}</NButton>
                </NButtonGroup>
                <NButton v-if="row.source === 'student'" size="tiny" quaternary :disabled="busy" @click="setStudent(row, null)">Use class mode</NButton>
              </td>
            </tr>
          </tbody>
        </table>
      </section>
    </template>
  </div>
</template>

<style scoped>
.mc { max-width: 1180px; margin: 0 auto; padding: var(--ca-space-5) var(--ca-space-4) var(--ca-space-6); }
.mc__header { display: flex; align-items: flex-end; justify-content: space-between; gap: var(--ca-space-4); margin-bottom: var(--ca-space-4); }
.mc__header h1 { font-size: var(--ca-text-2xl); font-weight: 700; margin: 0; }
.mc__header p { color: var(--ca-text-muted); margin: 2px 0 0; }
.mc__alert { margin-bottom: var(--ca-space-3); }
.mc__loading { display: flex; justify-content: center; padding: var(--ca-space-6) 0; }
.mc__class, .mc__table-wrap { background: var(--ca-surface); border: 1px solid var(--ca-border); border-radius: var(--ca-radius-lg); box-shadow: var(--ca-shadow-sm); padding: var(--ca-space-4) var(--ca-space-5); margin-bottom: var(--ca-space-4); }
.mc__class { display: grid; grid-template-columns: 1fr auto; gap: var(--ca-space-3) var(--ca-space-5); align-items: center; }
.mc__class-mode, .mc__set-all { display: flex; align-items: center; gap: var(--ca-space-3); flex-wrap: wrap; }
.mc__label { font-size: var(--ca-text-sm); font-weight: 600; color: var(--ca-text-muted); }
.mc__desc { font-size: var(--ca-text-sm); color: var(--ca-text-muted); }
.mc__counts { grid-column: 1 / -1; display: flex; gap: var(--ca-space-4); flex-wrap: wrap; padding-top: var(--ca-space-3); border-top: 1px solid var(--ca-border); font-size: var(--ca-text-sm); }
.mc__count { display: inline-flex; align-items: center; gap: 6px; font-weight: 600; }
.mc__count--muted { color: var(--ca-text-muted); font-weight: 500; }
.mc__table { width: 100%; border-collapse: collapse; font-size: var(--ca-text-sm); }
.mc__table th { text-align: left; color: var(--ca-text-muted); font-weight: 500; padding: 10px 8px; border-bottom: 1px solid var(--ca-border); }
.mc__table td { padding: 10px 8px; border-bottom: 1px solid var(--ca-border); vertical-align: middle; }
.mc__table tr:last-child td { border-bottom: 0; }
.mc__name { font-weight: 600; }
.mc__task { color: var(--ca-text); }
.mc__done { color: var(--ca-success); }
.mc__muted { color: var(--ca-text-subtle); }
.mc__actions { display: flex; align-items: center; gap: var(--ca-space-2); flex-wrap: wrap; }
.mc__th-actions { width: 1%; white-space: nowrap; }
</style>
