// SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { createApp, h } from 'vue'
import AppProvider from '../AppProvider.vue'
import App from './App.vue'

createApp({ render: () => h(AppProvider, null, { default: () => h(App) }) }).mount('#classaid-app')
