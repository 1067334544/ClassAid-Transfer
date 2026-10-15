<!-- SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
     SPDX-License-Identifier: AGPL-3.0-only -->
<script setup lang="ts">
import { computed } from 'vue'
import { MODE_LABELS, type Mode } from '../theme'

const props = withDefaults(defineProps<{
  mode: Mode
  size?: 'small' | 'medium' | 'large'
  source?: 'class' | 'student' | null
}>(), { size: 'medium', source: null })

const label = computed(() => MODE_LABELS[props.mode])
</script>

<template>
  <span class="ca-mode-badge" :class="[`ca-mode-${mode}`, `ca-mode-badge--${size}`]" :data-mode="mode">
    <span class="ca-mode-badge__dot" aria-hidden="true" />
    <span class="ca-mode-badge__label">{{ label }}</span>
    <span v-if="source" class="ca-mode-badge__source">{{ source === 'student' ? 'individual' : 'class' }}</span>
  </span>
</template>

<style scoped>
.ca-mode-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: 999px;
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
  background: var(--mode-soft);
  color: var(--mode-text);
  border: 1px solid color-mix(in srgb, var(--mode-solid) 28%, transparent);
}
.ca-mode-badge--small { font-size: var(--ca-text-xs); padding: 4px 8px; }
.ca-mode-badge--medium { font-size: var(--ca-text-sm); padding: 5px 10px; }
.ca-mode-badge--large { font-size: var(--ca-text-md); padding: 7px 14px; }
.ca-mode-badge__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--mode-solid);
}
.ca-mode-badge__source {
  font-weight: 500;
  opacity: 0.75;
  padding-left: 6px;
  border-left: 1px solid color-mix(in srgb, var(--mode-solid) 30%, transparent);
}
.ca-mode-heuristic { --mode-solid: var(--ca-mode-heuristic); --mode-soft: var(--ca-mode-heuristic-soft); --mode-text: var(--ca-mode-heuristic-text); }
.ca-mode-technical { --mode-solid: var(--ca-mode-technical); --mode-soft: var(--ca-mode-technical-soft); --mode-text: var(--ca-mode-technical-text); }
.ca-mode-auto { --mode-solid: var(--ca-mode-auto); --mode-soft: var(--ca-mode-auto-soft); --mode-text: var(--ca-mode-auto-text); }
.ca-mode-silent { --mode-solid: var(--ca-mode-silent); --mode-soft: var(--ca-mode-silent-soft); --mode-text: var(--ca-mode-silent-text); }
</style>
