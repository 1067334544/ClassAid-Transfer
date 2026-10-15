<!-- SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
     SPDX-License-Identifier: AGPL-3.0-only -->
<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NTooltip } from 'naive-ui'
import MarkdownView from './MarkdownView.vue'
import type { ChatMessage } from '../types'
import { MODE_LABELS } from '../theme'

const props = withDefaults(defineProps<{ message: ChatMessage; readonly?: boolean }>(), { readonly: false })
const emit = defineEmits<{ rate: [value: 1 | -1 | null] }>()

const typeLabel = computed(() => (props.message.feedback_type ? MODE_LABELS[props.message.feedback_type] : ''))

function toggle(value: 1 | -1): void {
  emit('rate', props.message.rating === value ? null : value)
}
</script>

<template>
  <div v-if="message.role === 'student'" class="ca-msg ca-msg--student">
    <div class="ca-msg__bubble">{{ message.content }}</div>
  </div>

  <div v-else-if="message.role === 'assistant'" class="ca-msg ca-msg--assistant" :class="`ca-msg--${message.feedback_type}`">
    <div class="ca-msg__meta">
      <span class="ca-msg__who">TA Agent</span>
      <span class="ca-msg__type" :data-type="message.feedback_type">{{ typeLabel }}</span>
      <span v-if="message.origin === 'proactive'" class="ca-msg__auto">Auto generated</span>
    </div>
    <div class="ca-msg__bubble">
      <MarkdownView :source="message.content" />
    </div>
    <div v-if="!readonly" class="ca-msg__rating">
      <NTooltip>
        <template #trigger>
          <NButton size="tiny" quaternary :type="message.rating === 1 ? 'primary' : 'default'" aria-label="Helpful" @click="toggle(1)">
            👍
          </NButton>
        </template>
        Helpful
      </NTooltip>
      <NTooltip>
        <template #trigger>
          <NButton size="tiny" quaternary :type="message.rating === -1 ? 'error' : 'default'" aria-label="Not helpful" @click="toggle(-1)">
            👎
          </NButton>
        </template>
        Not helpful
      </NTooltip>
    </div>
  </div>

  <div v-else class="ca-msg ca-msg--notice" :class="`ca-msg--notice-${message.notice_kind}`" role="status">
    <span class="ca-msg__notice-icon" aria-hidden="true">{{ message.notice_kind === 'silent' ? '⏸' : '!' }}</span>
    <span>{{ message.content }}</span>
  </div>
</template>

<style scoped>
.ca-msg { display: flex; flex-direction: column; gap: 4px; margin-bottom: var(--ca-space-3); }
.ca-msg__bubble {
  border-radius: var(--ca-radius);
  padding: 10px 12px;
  font-size: var(--ca-text-md);
  line-height: var(--ca-leading);
}
.ca-msg--student { align-items: flex-end; }
.ca-msg--student .ca-msg__bubble {
  background: var(--ca-primary);
  color: #fff;
  max-width: 85%;
  white-space: pre-wrap;
  border-bottom-right-radius: 4px;
}
.ca-msg--assistant { align-items: flex-start; }
.ca-msg--assistant .ca-msg__bubble {
  background: var(--ca-surface);
  border: 1px solid var(--ca-border);
  border-left: 3px solid var(--accent);
  max-width: 95%;
  border-bottom-left-radius: 4px;
}
.ca-msg--heuristic { --accent: var(--ca-mode-heuristic); --accent-soft: var(--ca-mode-heuristic-soft); --accent-text: var(--ca-mode-heuristic-text); }
.ca-msg--technical { --accent: var(--ca-mode-technical); --accent-soft: var(--ca-mode-technical-soft); --accent-text: var(--ca-mode-technical-text); }
.ca-msg__meta { display: flex; align-items: center; gap: 8px; font-size: var(--ca-text-xs); color: var(--ca-text-muted); }
.ca-msg__who { font-weight: 600; color: var(--ca-text); }
.ca-msg__type {
  background: var(--accent-soft);
  color: var(--accent-text);
  border-radius: 999px;
  padding: 2px 8px;
  font-weight: 600;
}
.ca-msg__auto { background: var(--ca-info-soft); color: var(--ca-info); border-radius: 999px; padding: 2px 8px; }
.ca-msg__rating { display: flex; gap: 2px; }
.ca-msg--notice {
  flex-direction: row;
  align-items: flex-start;
  gap: 8px;
  font-size: var(--ca-text-sm);
  border-radius: var(--ca-radius);
  padding: 8px 12px;
}
.ca-msg--notice-silent { background: var(--ca-mode-silent-soft); color: var(--ca-mode-silent-text); }
.ca-msg--notice-error { background: var(--ca-error-soft); color: var(--ca-error); }
.ca-msg__notice-icon { font-weight: 700; }
</style>
