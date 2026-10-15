<!-- SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
     SPDX-License-Identifier: AGPL-3.0-only -->
<script setup lang="ts">
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'

const props = defineProps<{ source: string }>()

// html: false -- raw HTML in Markdown is escaped, so model or task text cannot inject markup.
const md = new MarkdownIt({ html: false, linkify: true, breaks: false })
const defaultLink = md.renderer.rules.link_open ?? ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))
md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  tokens[idx].attrSet('target', '_blank')
  tokens[idx].attrSet('rel', 'noopener noreferrer')
  return defaultLink(tokens, idx, options, env, self)
}

const html = computed(() => md.render(props.source || ''))
</script>

<template>
  <!-- eslint-disable-next-line vue/no-v-html -- rendered with html:false -->
  <div class="ca-markdown" v-html="html" />
</template>

<style scoped>
.ca-markdown { line-height: var(--ca-leading); overflow-wrap: anywhere; }
.ca-markdown :deep(p) { margin: 0 0 0.6em; }
.ca-markdown :deep(p:last-child) { margin-bottom: 0; }
/* Gen-Ed's Bulma reset removes list markers and colors <code>; restore our own styles. */
.ca-markdown :deep(ul), .ca-markdown :deep(ol) { margin: 0.2em 0 0.6em; padding-left: 1.4em; }
.ca-markdown :deep(ul) { list-style: disc; }
.ca-markdown :deep(ol) { list-style: decimal; }
.ca-markdown :deep(li) { margin: 0.15em 0; }
.ca-markdown :deep(strong) { font-weight: 600; color: inherit; }
.ca-markdown :deep(code) {
  font-family: var(--ca-font-mono);
  font-size: 0.92em;
  color: var(--ca-text);
  background: var(--ca-surface-muted);
  border: 1px solid var(--ca-border);
  border-radius: 4px;
  padding: 0.05em 0.35em;
}
.ca-markdown :deep(pre) {
  background: #1e2230;
  color: #e6e9f0;
  border-radius: var(--ca-radius-sm);
  padding: var(--ca-space-3);
  overflow-x: auto;
  margin: 0.4em 0 0.7em;
}
.ca-markdown :deep(pre code) { background: none; border: 0; padding: 0; color: inherit; font-size: var(--ca-text-sm); }
.ca-markdown :deep(a) { color: var(--ca-primary); }
</style>
