import { mkdirSync, readdirSync, writeFileSync } from 'fs'
import { dirname, relative, resolve } from 'path'
import { fileURLToPath } from 'url'

import { CAPTURE_SESSION_TOKEN } from '../../../config/playwright.visual.contracts.js'

import { ensurePromptReady } from './helpers.js'
import { assertVisualFlowGuardrails } from './visual_guardrails.js'

const __dir = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dir, '../../..')
const THEMES_DIR = resolve(REPO_ROOT, 'app/conf/themes')

export const CAPTURE_ROOT = process.env.CAPTURE_OUT_DIR
  ? resolve(REPO_ROOT, process.env.CAPTURE_OUT_DIR)
  : '/tmp/darklab_shell-ui-capture'

export const LONG_RUN_CMD = 'capture-long-run'
export const FAST_RUN_CMD = 'capture-fast-run'
export function resolveCaptureThemes() {
  const requested = String(process.env.CAPTURE_THEME || '').trim()
  if (!requested || requested === 'default') return [null]
  if (requested === 'all') {
    return readdirSync(THEMES_DIR)
      .filter((name) => name.endsWith('.yaml'))
      .map((name) => name.replace(/\.yaml$/, ''))
      .sort()
  }
  return [requested]
}

export function themeLabel(themeName) {
  return themeName || 'default'
}

export function createManifest(ui) {
  return {
    ui,
    generated_at: new Date().toISOString(),
    theme_mode: process.env.CAPTURE_THEME || 'default',
    entries: [],
  }
}

export function writeManifest(ui, manifest) {
  mkdirSync(CAPTURE_ROOT, { recursive: true })
  const path = resolve(CAPTURE_ROOT, `${ui}-manifest.json`)
  writeFileSync(path, JSON.stringify(manifest, null, 2))
}

export async function saveCapture(page, manifest, {
  ui,
  themeName = null,
  order,
  slug,
  title,
  route = '/',
} = {}) {
  const dir = resolve(CAPTURE_ROOT, ui, themeLabel(themeName))
  const file = `${String(order).padStart(2, '0')}-${slug}.png`
  const path = resolve(dir, file)
  mkdirSync(dir, { recursive: true })
  await page.waitForTimeout(120)
  await page.screenshot({ path, type: 'png', animations: 'disabled' })
  manifest.entries.push({
    ui,
    theme: themeLabel(themeName),
    title,
    route,
    file: relative(CAPTURE_ROOT, path),
  })
}

export async function installCommonCaptureMocks(page) {
  await page.addInitScript(
    ({ longCmd, fastCmd }) => {
      const originalFetch = window.fetch.bind(window)
      const encoder = new TextEncoder()

      Object.defineProperty(navigator, 'clipboard', {
        value: {
          writeText: (text) => {
            window.__clipboardText = text
            return Promise.resolve()
          },
        },
        configurable: true,
      })

      window.fetch = async (input, init) => {
        const url = typeof input === 'string' ? input : input?.url || ''
        const method = String(init?.method || 'GET').toUpperCase()
        const rawBody = typeof init?.body === 'string' ? init.body : ''

        if (url.endsWith('/run') && method === 'POST') {
          const payload = JSON.parse(rawBody || '{}')
          const command = payload.command || ''

          if (command === longCmd) {
            const body = new ReadableStream({
              start(controller) {
                controller.enqueue(
                  encoder.encode('data: {"type":"started","run_id":"capture-long-run"}\n\n'),
                )
                controller.enqueue(
                  encoder.encode('data: {"type":"output","text":"capture long run started\\n"}\n\n'),
                )
              },
            })
            return new Response(body, {
              status: 200,
              headers: { 'Content-Type': 'text/event-stream' },
            })
          }

          if (command === fastCmd) {
            return new Response(
              [
                'data: {"type":"started","run_id":"capture-fast-run"}\n\n',
                'data: {"type":"output","text":"capture fast run output\\n"}\n\n',
                'data: {"type":"exit","code":0,"elapsed":0.1}\n\n',
              ].join(''),
              {
                status: 200,
                headers: { 'Content-Type': 'text/event-stream' },
              },
            )
          }
        }

        return originalFetch(input, init)
      }
    },
    { longCmd: LONG_RUN_CMD, fastCmd: FAST_RUN_CMD },
  )
}

async function hydrateCaptureRecents(page) {
  await page.evaluate(async () => {
    try {
      const resp = await apiFetch('/history')
      const data = await resp.json()
      if (typeof hydrateCmdHistory === 'function') hydrateCmdHistory(data.runs || [])
    } catch (_) {
      // Keep captures usable even if history hydration fails.
    }
  })
}

export async function freshHome(
  page,
  {
    themeName = null,
    cancelWelcome = true,
    useCaptureSession = true,
    hydrateHistory = true,
    guardrailMode = null,
  } = {},
) {
  await page.context().clearCookies()
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await page.evaluate(({ sessionToken }) => {
    try {
      localStorage.clear()
      sessionStorage.clear()
      if (sessionToken) localStorage.setItem('session_token', sessionToken)
    } catch (_) {
      // Ignore storage-clear failures in non-standard contexts.
    }
  }, { sessionToken: useCaptureSession ? CAPTURE_SESSION_TOKEN : '' })
  await page.reload({ waitUntil: 'domcontentloaded' })
  if (themeName) {
    await page.evaluate((name) => {
      if (typeof applyThemeSelection === 'function') applyThemeSelection(name)
    }, themeName)
    await page.waitForFunction((name) => document.body?.dataset?.theme === name, themeName)
  } else {
    await page.waitForFunction(() => Boolean(document.body?.dataset?.theme))
  }
  await ensurePromptReady(page, { cancelWelcome })
  if (guardrailMode) {
    await assertVisualFlowGuardrails(page, {
      mode: guardrailMode,
      requireSeededHistory: useCaptureSession,
    })
  }
  if (hydrateHistory) await hydrateCaptureRecents(page)
}

export async function seedOutput(page, lines) {
  await page.evaluate((items) => {
    if (typeof clearTab === 'function' && typeof activeTabId !== 'undefined') {
      clearTab(activeTabId)
    }
    items.forEach(({ text, cls }) => {
      if (typeof appendLine === 'function' && typeof activeTabId !== 'undefined') {
        appendLine(text, cls || '', activeTabId)
      }
    })
  }, lines)
}

export async function waitForWorkflowsReady(page) {
  await page.waitForFunction(
    () => document.querySelectorAll('#rail-workflows-list > *').length > 0,
    { timeout: 10_000 },
  )
}
