<!-- SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
     SPDX-License-Identifier: AGPL-3.0-only -->
<script setup lang="ts">
import { NConfigProvider, NDialogProvider, NMessageProvider } from 'naive-ui'
import { themeOverrides } from './theme'

const overrides = themeOverrides()
</script>

<template>
  <NConfigProvider :theme-overrides="overrides">
    <NMessageProvider>
      <NDialogProvider>
        <slot />
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>
