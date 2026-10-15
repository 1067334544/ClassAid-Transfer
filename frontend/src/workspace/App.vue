<!-- SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
     SPDX-License-Identifier: AGPL-3.0-only -->
<script setup lang="ts">
import type { Bootstrap } from '../bootstrap'
import TaskList from './TaskList.vue'
import Workspace from './Workspace.vue'

defineProps<{ bootstrap: Bootstrap }>()
</script>

<template>
  <Workspace v-if="bootstrap.page === 'workspace'" :bootstrap="bootstrap" :task-id="bootstrap.taskId as number" />
  <TaskList v-else :bootstrap="bootstrap" />
</template>
