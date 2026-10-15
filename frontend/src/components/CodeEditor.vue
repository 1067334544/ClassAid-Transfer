<!-- SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
     SPDX-License-Identifier: AGPL-3.0-only -->
<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { EditorView, basicSetup } from 'codemirror'
import { EditorState, Compartment } from '@codemirror/state'
import { java } from '@codemirror/lang-java'

const props = withDefaults(defineProps<{ modelValue: string; readonly?: boolean }>(), { readonly: false })
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const host = ref<HTMLDivElement | null>(null)
let view: EditorView | null = null
const readOnly = new Compartment()

const theme = EditorView.theme({
  '&': { fontSize: 'var(--ca-text-md)', height: '100%', backgroundColor: 'var(--ca-surface)' },
  '.cm-scroller': { fontFamily: 'var(--ca-font-mono)', lineHeight: '1.6' },
  '.cm-gutters': { backgroundColor: 'var(--ca-surface-muted)', borderRight: '1px solid var(--ca-border)', color: 'var(--ca-text-subtle)' },
  '.cm-activeLine': { backgroundColor: 'color-mix(in srgb, var(--ca-primary) 5%, transparent)' },
  '.cm-activeLineGutter': { backgroundColor: 'color-mix(in srgb, var(--ca-primary) 9%, transparent)' },
  '&.cm-focused': { outline: 'none' },
})

onMounted(() => {
  view = new EditorView({
    parent: host.value!,
    state: EditorState.create({
      doc: props.modelValue,
      extensions: [
        basicSetup,
        java(),
        theme,
        readOnly.of([EditorState.readOnly.of(props.readonly), EditorView.editable.of(!props.readonly)]),
        EditorView.updateListener.of((update) => {
          if (update.docChanged) emit('update:modelValue', update.state.doc.toString())
        }),
      ],
    }),
  })
})

watch(() => props.modelValue, (value) => {
  if (view && value !== view.state.doc.toString()) {
    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: value } })
  }
})

watch(() => props.readonly, (value) => {
  view?.dispatch({ effects: readOnly.reconfigure([EditorState.readOnly.of(value), EditorView.editable.of(!value)]) })
})

onBeforeUnmount(() => view?.destroy())
</script>

<template>
  <div ref="host" class="ca-editor" :class="{ 'is-readonly': readonly }" />
</template>

<style scoped>
.ca-editor { height: 100%; min-height: 200px; border: 1px solid var(--ca-border); border-radius: var(--ca-radius-sm); overflow: hidden; }
.ca-editor.is-readonly { opacity: 0.9; }
.ca-editor :deep(.cm-editor) { height: 100%; }
</style>
