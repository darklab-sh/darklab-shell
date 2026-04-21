/**
 * Theme audit — not a correctness test. Walks every installed theme, opens the
 * mobile sheets, and reports WCAG contrast ratios for the pairs most likely to
 * break under low-alpha colored borders and light surfaces. Prints a table;
 * only hard-fails on catastrophic regressions (contrast < 1.20) so the suite
 * doesn't block on subjective aesthetic calls.
 *
 * Run: npx playwright test theme-audit --config config/playwright.config.js
 */

import { readdirSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'
import { test, expect } from '@playwright/test'
import { ensurePromptReady } from './helpers.js'

const __dir = dirname(fileURLToPath(import.meta.url))
const THEMES_DIR = resolve(__dir, '../../../app/conf/themes')
const MOBILE = { width: 390, height: 844 }

test.use({ hasTouch: true, isMobile: true })

function allThemeNames() {
  return readdirSync(THEMES_DIR)
    .filter((f) => f.endsWith('.yaml') && !f.endsWith('.local.yaml'))
    .map((f) => f.replace(/\.yaml$/, ''))
    .sort()
}

test('audit mobile surfaces across every installed theme', async ({ page }) => {
  test.setTimeout(120_000)

  const themes = allThemeNames()
  await page.setViewportSize(MOBILE)
  await page.goto('/')
  await ensurePromptReady(page)

  // Force both sheets visible so getComputedStyle returns the painted colors
  // instead of the default u-hidden state. This runs once — every theme reuses
  // the same open DOM and we only flip --theme vars between iterations.
  await page.evaluate(() => {
    const show = (id) => document.getElementById(id)?.classList.remove('u-hidden')
    show('mobile-menu-sheet')
    show('mobile-menu-sheet-scrim')
    show('mobile-recents-sheet')
    show('mobile-recents-sheet-scrim')
    show('mobile-recent-peek')
  })

  const results = []
  for (const themeName of themes) {
    await page.evaluate((name) => {
      if (typeof applyThemeSelection === 'function') applyThemeSelection(name, false)
    }, themeName)

    const metrics = await page.evaluate(() => {
      // Resolve rgba/hex strings into linear [r,g,b,a] arrays via a throwaway
      // element so the browser does all the color parsing for us.
      const probe = document.createElement('div')
      probe.style.display = 'none'
      document.body.appendChild(probe)
      const toRgba = (cssColor) => {
        probe.style.color = ''
        probe.style.color = cssColor
        const m = getComputedStyle(probe).color.match(
          /rgba?\(\s*([\d.]+)\s*[, ]\s*([\d.]+)\s*[, ]\s*([\d.]+)(?:\s*[,/]\s*([\d.]+))?/,
        )
        if (!m) return [0, 0, 0, 1]
        return [+m[1], +m[2], +m[3], m[4] == null ? 1 : +m[4]]
      }
      // WCAG relative luminance on sRGB. Alpha is folded against the provided
      // background so a colored low-alpha border composed over --surface
      // reports the apparent luminance, not the bare token value.
      const luminance = ([r, g, b]) => {
        const lin = (c) => {
          const n = c / 255
          return n <= 0.03928 ? n / 12.92 : Math.pow((n + 0.055) / 1.055, 2.4)
        }
        return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
      }
      const compose = (fg, bg) => {
        const a = fg[3]
        return [
          fg[0] * a + bg[0] * (1 - a),
          fg[1] * a + bg[1] * (1 - a),
          fg[2] * a + bg[2] * (1 - a),
          1,
        ]
      }
      const contrast = (fg, bg) => {
        const effective = fg[3] < 1 ? compose(fg, bg) : fg
        const l1 = luminance(effective)
        const l2 = luminance(bg)
        const [a, b] = l1 > l2 ? [l1, l2] : [l2, l1]
        return (a + 0.05) / (b + 0.05)
      }

      const readVar = (name) => {
        const raw = getComputedStyle(document.body).getPropertyValue(name).trim()
        return toRgba(raw)
      }

      const surface = readVar('--surface')
      const bg = readVar('--bg')
      const borderBright = readVar('--border-bright')
      const border = readVar('--border')
      const text = readVar('--text')
      const muted = readVar('--muted')
      const green = readVar('--green')
      const amber = readVar('--amber')
      const red = readVar('--red')

      // Pairs to audit. Each pair's bg is whichever surface that element sits
      // on in the real DOM (sheet body = --surface; peek row = --bg).
      const pairs = {
        sheetBorderOnSurface: contrast(borderBright, surface),
        sheetGrabOnSurface: contrast(borderBright, surface),
        sheetDividerOnSurface: contrast(border, surface),
        mutedOnSurface: contrast(muted, surface),
        textOnSurface: contrast(text, surface),
        greenAccentOnSurface: contrast(green, surface),
        amberOnSurface: contrast(amber, surface),
        redOnSurface: contrast(red, surface),
        peekBorderOnBg: contrast(borderBright, bg),
        peekMutedOnBg: contrast(muted, bg),
      }

      probe.remove()
      return pairs
    })

    results.push({ themeName, ...metrics })
  }

  // Format a compact report sorted by the weakest contrast pair per theme.
  const rows = results.map((r) => {
    const { themeName, ...pairs } = r
    const entries = Object.entries(pairs)
    const min = entries.reduce((a, b) => (a[1] < b[1] ? a : b))
    return { themeName, min: min[0], minRatio: min[1], ...pairs }
  })
  rows.sort((a, b) => a.minRatio - b.minRatio)

  const fmt = (n) => n.toFixed(2).padStart(4)
  const flag = (v) => (v < 1.3 ? '⚠' : v < 2 ? '·' : ' ')
  const cell = (v) => `${flag(v)}${fmt(v)}`
  const headers = [
    'theme'.padEnd(18),
    'border'.padStart(7),
    'grab'.padStart(7),
    'divider'.padStart(7),
    'muted'.padStart(7),
    'text'.padStart(7),
    'green'.padStart(7),
    'peek'.padStart(7),
    '  weakest',
  ]
  const lines = [
    '',
    '── Theme audit: mobile surface contrast (WCAG ratios on --surface / --bg) ──',
    '',
    '    border = --border-bright vs surface (sheet edge + grab handle)',
    '    divider = --border vs surface (item separators inside sheet)',
    '    peek = --border-bright vs bg (recent-peek row)',
    '    ⚠ = < 1.30 (likely invisible)   · = < 2.00 (low but may be intentional)',
    '',
    headers.join(''),
    '─'.repeat(headers.join('').length),
  ]
  for (const row of rows) {
    lines.push(
      [
        row.themeName.padEnd(18),
        cell(row.sheetBorderOnSurface).padStart(7),
        cell(row.sheetGrabOnSurface).padStart(7),
        cell(row.sheetDividerOnSurface).padStart(7),
        cell(row.mutedOnSurface).padStart(7),
        cell(row.textOnSurface).padStart(7),
        cell(row.greenAccentOnSurface).padStart(7),
        cell(row.peekBorderOnBg).padStart(7),
        `  ${cell(row.minRatio)} ${row.min}`,
      ].join(''),
    )
  }
  lines.push('')
  console.log(lines.join('\n'))

  // Hard gate: anything under 1.20 is effectively invisible. Everything else
  // is a judgment call the operator makes after reading the report.
  const broken = rows.filter((r) => r.minRatio < 1.2)
  expect(broken, `themes with invisible surfaces: ${broken.map((r) => r.themeName).join(', ')}`).toHaveLength(0)
})
