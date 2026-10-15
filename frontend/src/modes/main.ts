// SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { createApp, h } from 'vue'
import AppProvider from '../AppProvider.vue'
import App from './App.vue'
import { readBootstrap } from '../bootstrap'
import { setApiBase } from '../api'

const bootstrap = readBootstrap()
setApiBase(bootstrap.apiBase)

createApp({ render: () => h(AppProvider, null, { default: () => h(App, { bootstrap }) }) }).mount('#classaid-app')
