import { expect } from '@playwright/test'

import {
  CAPTURE_SEEDED_HISTORY_MIN_ROOTS,
  CAPTURE_SEEDED_HISTORY_MIN_RUNS,
  CAPTURE_SESSION_TOKEN,
  DESKTOP_VISUAL_CONTRACT,
  MOBILE_VISUAL_CONTRACT,
} from '../../../config/playwright.visual.contracts.js'

function contractFor(mode) {
  if (mode === 'desktop') return DESKTOP_VISUAL_CONTRACT
  if (mode === 'mobile') return MOBILE_VISUAL_CONTRACT
  throw new Error(`Unknown visual contract mode: ${mode}`)
}

export async function assertVisualFlowGuardrails(
  page,
  { mode, requireSeededHistory = false, expectedSessionToken = CAPTURE_SESSION_TOKEN } = {},
) {
  const contract = contractFor(mode)
  const viewport = page.viewportSize()
  expect(viewport).toEqual(contract.viewport)

  const state = await page.evaluate(async () => {
    const sessionToken = (() => {
      try {
        return localStorage.getItem('session_token') || ''
      } catch (_) {
        return ''
      }
    })()
    const requestJson = async (url) => {
      const options = {
        cache: 'no-store',
        credentials: 'same-origin',
      }
      if (typeof apiFetch === 'function') {
        const resp = await apiFetch(url, options)
        return resp.json()
      }
      const headers = sessionToken ? { 'X-Session-ID': sessionToken } : {}
      const resp = await fetch(url, { ...options, headers })
      return resp.json()
    }

    const status = await requestJson('/status')
    const history = await requestJson('/history?include_total=1&page_size=1')
    return {
      devicePixelRatio: window.devicePixelRatio,
      maxTouchPoints: navigator.maxTouchPoints || 0,
      userAgent: navigator.userAgent,
      mobileTerminalMode: document.body.classList.contains('mobile-terminal-mode'),
      sessionToken,
      status,
      historyRuns: Math.max(
        0,
        Number(history.total_count ?? history.runs?.length ?? 0) || 0,
      ),
      historyRoots: Array.isArray(history.roots) ? history.roots.length : 0,
    }
  })

  expect(state.devicePixelRatio).toBe(contract.deviceScaleFactor)
  expect(state.mobileTerminalMode).toBe(contract.mobileTerminalMode)

  if (contract.hasTouch) expect(state.maxTouchPoints).toBeGreaterThan(0)
  else expect(state.maxTouchPoints).toBe(0)

  if (contract.userAgentIncludes) {
    expect(state.userAgent).toContain(contract.userAgentIncludes)
  }

  expect(state.status.db).toBe('ok')
  expect(['ok', 'none', 'down']).toContain(state.status.redis)

  if (requireSeededHistory) {
    expect(state.sessionToken).toBe(expectedSessionToken)
    expect(state.historyRuns).toBeGreaterThanOrEqual(CAPTURE_SEEDED_HISTORY_MIN_RUNS)
    expect(state.historyRoots).toBeGreaterThanOrEqual(CAPTURE_SEEDED_HISTORY_MIN_ROOTS)
    expect(state.status.redis).toBe('ok')
  }
}
