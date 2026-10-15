// SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
// SPDX-License-Identifier: AGPL-3.0-only

/**
 * Maps the design tokens in src/classaid/static/theme.css (the single source of the
 * visual specification, design.md D11) onto Naive UI's theme overrides.  The tokens are
 * read from CSS custom properties at runtime, so they are never duplicated here.
 */
import type { GlobalThemeOverrides } from 'naive-ui'

export type Mode = 'heuristic' | 'technical' | 'auto' | 'silent'

export const MODES: readonly Mode[] = ['heuristic', 'technical', 'auto', 'silent']

export const MODE_LABELS: Record<Mode, string> = {
  heuristic: 'Heuristic',
  technical: 'Technical',
  auto: 'Auto',
  silent: 'Silent',
}

export const MODE_DESCRIPTIONS: Record<Mode, string> = {
  heuristic: 'Hints and guiding questions, without the solution.',
  technical: 'Direct explanations and corrected code.',
  auto: 'The assistant chooses hints or direct help for each question.',
  silent: 'AI feedback is paused; keep working on your own.',
}

export function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(`--ca-${name}`).trim()
}

export function themeOverrides(): GlobalThemeOverrides {
  const font = token('font')
  const mono = token('font-mono')
  return {
    common: {
      primaryColor: token('primary'),
      primaryColorHover: token('primary-hover'),
      primaryColorPressed: token('primary-pressed'),
      primaryColorSuppl: token('primary-hover'),
      infoColor: token('info'),
      successColor: token('success'),
      warningColor: token('warning'),
      errorColor: token('error'),
      textColorBase: token('text'),
      textColor1: token('text'),
      textColor2: token('text'),
      textColor3: token('text-muted'),
      borderColor: token('border'),
      dividerColor: token('border'),
      bodyColor: token('bg'),
      cardColor: token('surface'),
      fontFamily: font,
      fontFamilyMono: mono,
      fontSize: token('text-md'),
      fontSizeMedium: token('text-md'),
      borderRadius: token('radius'),
      borderRadiusSmall: token('radius-sm'),
      boxShadow1: token('shadow-sm'),
      boxShadow2: token('shadow'),
      boxShadow3: token('shadow-lg'),
    },
    Card: {
      borderRadius: token('radius-lg'),
      borderColor: token('border'),
    },
    Button: {
      fontWeight: '500',
    },
  }
}
