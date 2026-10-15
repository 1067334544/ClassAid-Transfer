<!-- SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
     SPDX-License-Identifier: AGPL-3.0-only -->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { NAlert, NButton, NEmpty, NSpin, NTag } from 'naive-ui'
import ModeBadge from '../components/ModeBadge.vue'
import { api, ApiError } from '../api'
import type { Bootstrap } from '../bootstrap'
import { MODE_DESCRIPTIONS, type Mode } from '../theme'
import type { StateResponse, TaskListItem } from './types'

const props = defineProps<{ bootstrap: Bootstrap }>()
const isInstructor = props.bootstrap.role === 'instructor'

const tasks = ref<TaskListItem[]>([])
const mode = ref<{ mode: Mode; source: 'class' | 'student' } | null>(null)
const loading = ref(true)
const error = ref('')

const STATUS: Record<TaskListItem['status'], { label: string; type: 'default' | 'success' | 'info' }> = {
  not_started: { label: 'Not started', type: 'default' },
  in_progress: { label: 'In progress', type: 'info' },
  completed: { label: 'Completed', type: 'success' },
}

function hiddenFromStudents(task: TaskListItem): boolean {
  return Boolean(task.available) && task.available! > new Date().toISOString().slice(0, 10)
}

onMounted(async () => {
  try {
    const [list, state] = await Promise.all([
      api.get<{ tasks: TaskListItem[] }>('/tasks'),
      api.get<StateResponse>('/state'),
    ])
    tasks.value = list.tasks
    mode.value = state.mode
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Could not load tasks.'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="tl">
    <header class="tl__header">
      <div>
        <h1>Tasks</h1>
        <p>{{ bootstrap.className }}</p>
      </div>
      <div class="tl__actions">
        <div v-if="mode && !isInstructor" class="tl__mode">
          <span>AI feedback mode</span>
          <ModeBadge :mode="mode.mode" />
          <span class="tl__mode-desc">{{ MODE_DESCRIPTIONS[mode.mode] }}</span>
        </div>
        <template v-if="isInstructor">
          <NButton tag="a" :href="String(bootstrap.modesUrl)" type="primary">Mode control</NButton>
          <NButton tag="a" href="/instructor/config/">Manage tasks</NButton>
        </template>
      </div>
    </header>

    <NAlert v-if="error" type="error" :title="error" />
    <div v-else-if="loading" class="tl__loading"><NSpin /></div>
    <NEmpty v-else-if="!tasks.length" :description="isInstructor ? 'No tasks yet. Create one under Manage tasks.' : 'No tasks are available yet.'" class="tl__empty" />
    <div v-else class="tl__grid">
      <a v-for="(task, index) in tasks" :key="task.id" class="tl__card" :href="`/classaid/tasks/${task.id}`">
        <div class="tl__card-top">
          <span class="tl__index">Task {{ index + 1 }}</span>
          <NTag size="small" round :type="STATUS[task.status].type">{{ STATUS[task.status].label }}</NTag>
        </div>
        <h2>{{ task.title }}</h2>
        <div class="tl__card-bottom">
          <span v-if="task.status === 'completed' && task.score !== null" class="tl__score">Score <strong>{{ task.score.toFixed(1) }}</strong> / 5</span>
          <span v-else class="tl__open">{{ task.status === 'not_started' ? 'Start →' : 'Continue →' }}</span>
          <span v-if="isInstructor && hiddenFromStudents(task)" class="tl__hidden">hidden from students</span>
        </div>
      </a>
    </div>
  </div>
</template>

<style scoped>
.tl { max-width: 1080px; margin: 0 auto; padding: var(--ca-space-5) var(--ca-space-4) var(--ca-space-6); }
.tl__header { display: flex; align-items: flex-end; justify-content: space-between; gap: var(--ca-space-4); flex-wrap: wrap; margin-bottom: var(--ca-space-5); }
.tl__header h1 { font-size: var(--ca-text-2xl); font-weight: 700; margin: 0; }
.tl__header p { color: var(--ca-text-muted); margin: 2px 0 0; }
.tl__actions { display: flex; align-items: center; gap: var(--ca-space-2); flex-wrap: wrap; }
.tl__mode { display: flex; align-items: center; gap: var(--ca-space-2); background: var(--ca-surface); border: 1px solid var(--ca-border); border-radius: var(--ca-radius); padding: 8px 12px; font-size: var(--ca-text-sm); color: var(--ca-text-muted); }
.tl__mode-desc { max-width: 280px; }
.tl__loading, .tl__empty { padding: var(--ca-space-6) 0; display: flex; justify-content: center; }
.tl__grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: var(--ca-space-4); }
.tl__card {
  display: flex; flex-direction: column; gap: var(--ca-space-2);
  background: var(--ca-surface); border: 1px solid var(--ca-border); border-radius: var(--ca-radius-lg);
  box-shadow: var(--ca-shadow-sm); padding: var(--ca-space-4); color: var(--ca-text); text-decoration: none;
  transition: box-shadow 0.15s, border-color 0.15s, transform 0.15s;
}
.tl__card:hover { box-shadow: var(--ca-shadow); border-color: var(--ca-primary); transform: translateY(-1px); color: var(--ca-text); }
.tl__card-top { display: flex; justify-content: space-between; align-items: center; }
.tl__index { font-size: var(--ca-text-xs); color: var(--ca-text-subtle); text-transform: uppercase; letter-spacing: 0.04em; }
.tl__card h2 { font-size: var(--ca-text-lg); font-weight: 600; margin: 0; line-height: 1.35; }
.tl__card-bottom { display: flex; justify-content: space-between; align-items: center; margin-top: auto; padding-top: var(--ca-space-2); font-size: var(--ca-text-sm); }
.tl__score strong { font-size: var(--ca-text-lg); }
.tl__open { color: var(--ca-primary); font-weight: 500; }
.tl__hidden { color: var(--ca-warning); font-size: var(--ca-text-xs); }
</style>
