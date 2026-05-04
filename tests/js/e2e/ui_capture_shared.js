import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'fs'
import { dirname, relative, resolve } from 'path'
import { fileURLToPath } from 'url'

import { CAPTURE_SESSION_TOKEN } from '../../../config/playwright.visual.contracts.js'

import { ensurePromptReady } from './helpers.js'
import { assertVisualFlowGuardrails } from './visual_guardrails.js'

const __dir = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dir, '../../..')
const THEMES_DIR = resolve(REPO_ROOT, 'app/conf/themes')
const APP_CONFIG_PATH = resolve(REPO_ROOT, 'app/config.py')

export const CAPTURE_ROOT = process.env.CAPTURE_OUT_DIR
  ? resolve(REPO_ROOT, process.env.CAPTURE_OUT_DIR)
  : '/tmp/darklab_shell-ui-capture'

export const LONG_RUN_CMD = 'capture-long-run'
export const FAST_RUN_CMD = 'capture-fast-run'
const CAPTURE_MOCK_RUNS = {
  hostname: {
    output: ['darklab_shell'],
    elapsed: 0.1,
  },
  date: {
    output: ['Fri Apr 24 17:30:00 CDT 2026'],
    elapsed: 0.1,
  },
  'ping -c 4 darklab.sh': {
    output: [
      'PING darklab.sh (104.21.4.35): 56 data bytes',
      '64 bytes from 104.21.4.35: icmp_seq=0 ttl=56 time=12.4 ms',
      '64 bytes from 104.21.4.35: icmp_seq=1 ttl=56 time=11.9 ms',
      '64 bytes from 104.21.4.35: icmp_seq=2 ttl=56 time=12.1 ms',
      '64 bytes from 104.21.4.35: icmp_seq=3 ttl=56 time=12.0 ms',
      '--- darklab.sh ping statistics ---',
      '4 packets transmitted, 4 packets received, 0.0% packet loss',
    ],
    elapsed: 0.4,
  },
}

function resolveDefaultCaptureTheme() {
  let configText = ''
  try {
    configText = readFileSync(APP_CONFIG_PATH, 'utf8')
  } catch (error) {
    throw new Error(`Could not read configured default capture theme from ${APP_CONFIG_PATH}: ${error.message}`)
  }
  const match = configText.match(/["']default_theme["']\s*:\s*["']([^"']+)["']/)
  if (!match) throw new Error(`Could not find default_theme in ${APP_CONFIG_PATH}`)
  const themeName = match[1].replace(/\.ya?ml$/i, '').trim()
  if (!themeName) throw new Error(`default_theme in ${APP_CONFIG_PATH} is empty`)
  const themeFile = resolve(THEMES_DIR, `${themeName}.yaml`)
  if (!existsSync(themeFile)) throw new Error(`Configured default theme does not exist: ${themeFile}`)
  return themeName
}

export function resolveCaptureThemes() {
  const requested = String(process.env.CAPTURE_THEME || '').trim()
  const variant = String(process.env.CAPTURE_THEME_VARIANT || '').trim().toLowerCase()
  if (!requested || requested === 'default') return [resolveDefaultCaptureTheme()]
  if (requested === 'all') {
    return readdirSync(THEMES_DIR)
      .filter((name) => name.endsWith('.yaml'))
      .map((name) => name.replace(/\.yaml$/, ''))
      .filter((name) => {
        if (!variant || variant === 'all') return true
        return captureThemeVariant(name) === variant
      })
      .sort()
  }
  return [requested]
}

function captureThemeVariant(themeName) {
  const file = resolve(THEMES_DIR, `${themeName}.yaml`)
  try {
    const text = readFileSync(file, 'utf8')
    const match = text.match(/^\s*color_scheme\s*:\s*(light|dark)\s*$/m)
    return match ? match[1] : ''
  } catch (_) {
    return ''
  }
}

export function themeLabel(themeName) {
  return themeName || 'default'
}

export function createManifest(ui) {
  const requested = String(process.env.CAPTURE_THEME || '').trim()
  return {
    ui,
    generated_at: new Date().toISOString(),
    theme_mode: requested && requested !== 'default' ? requested : resolveDefaultCaptureTheme(),
    theme_variant: process.env.CAPTURE_THEME_VARIANT || 'all',
    entries: [],
  }
}

export function writeManifest(ui, manifest) {
  mkdirSync(CAPTURE_ROOT, { recursive: true })
  const path = resolve(CAPTURE_ROOT, `${ui}-manifest.json`)
  writeFileSync(path, JSON.stringify(manifest, null, 2))
  writeCaptureReviewIndex()
}

function readCaptureManifest(ui) {
  const path = resolve(CAPTURE_ROOT, `${ui}-manifest.json`)
  if (!existsSync(path)) return null
  try {
    const parsed = JSON.parse(readFileSync(path, 'utf8'))
    return parsed && Array.isArray(parsed.entries) ? parsed : null
  } catch (_) {
    return null
  }
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function groupEntriesByTheme(entries) {
  const groups = new Map()
  for (const entry of entries) {
    const theme = entry?.theme || 'default'
    if (!groups.has(theme)) groups.set(theme, [])
    groups.get(theme).push(entry)
  }
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b))
}

function renderCaptureReviewSection(manifest) {
  const ui = manifest.ui || 'capture'
  const uiLabel = ui.charAt(0).toUpperCase() + ui.slice(1)
  const entries = Array.isArray(manifest.entries) ? manifest.entries : []
  const themes = groupEntriesByTheme(entries)
  const themeSummary = themes.length === 1 ? '1 theme' : `${themes.length} themes`
  const sceneSummary = entries.length === 1 ? '1 scene' : `${entries.length} scenes`
  return `
    <section class="ui-section">
      <header class="ui-heading">
        <div>
          <p class="eyebrow">${escapeHtml(uiLabel)}</p>
        </div>
        <div class="meta">${escapeHtml(sceneSummary)} · ${escapeHtml(themeSummary)}</div>
      </header>
      ${themes.map(([theme, themeEntries]) => `
        <details class="theme-section">
          <summary>
            <span class="theme-name"><span class="theme-toggle" aria-hidden="true"></span>${escapeHtml(theme)}</span>
            <small>${themeEntries.length} ${themeEntries.length === 1 ? 'scene' : 'scenes'}</small>
          </summary>
          <div class="scene-grid">
            ${themeEntries.map((entry) => `
              <article class="scene-card">
                <a
                  class="shot-link"
                  href="${escapeHtml(entry.file)}"
                  data-viewer-image="${escapeHtml(entry.file)}"
                  data-viewer-title="${escapeHtml(entry.title || entry.slug || 'Untitled scene')}"
                  data-viewer-theme="${escapeHtml(theme)}"
                  data-viewer-ui="${escapeHtml(ui)}"
                  data-viewer-route="${escapeHtml(entry.route || '/')}"
                >
                  <img src="${escapeHtml(entry.file)}" alt="${escapeHtml(`${entry.title || entry.slug || 'Capture scene'} — ${theme}`)}" loading="lazy">
                </a>
                <div class="scene-copy">
                  <h3>${escapeHtml(entry.title || entry.slug || 'Untitled scene')}</h3>
                  <p>${escapeHtml(entry.route || '/')}</p>
                </div>
              </article>
            `).join('')}
          </div>
        </details>
      `).join('')}
    </section>
  `
}

function writeCaptureReviewIndex() {
  const manifests = ['desktop', 'mobile'].map(readCaptureManifest).filter(Boolean)
  const generatedAt = new Date().toISOString()
  const body = manifests.length
    ? manifests.map(renderCaptureReviewSection).join('')
    : '<p class="empty">No capture manifests found yet.</p>'
  const html = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>darklab_shell UI Capture Review</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f1ea;
      --panel: #fffaf1;
      --text: #1c1b18;
      --muted: #69645b;
      --border: #d8d0bf;
      --accent: #11624f;
      --shadow: 0 18px 50px rgba(37, 31, 20, 0.12);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
    }
    main {
      width: min(1440px, calc(100% - 48px));
      margin: 0 auto;
      padding: 40px 0 56px;
    }
    .page-header {
      display: flex;
      justify-content: space-between;
      gap: 24px;
      align-items: flex-end;
      margin-bottom: 28px;
    }
    h1, h2, h3, p { margin: 0; }
    h1 { font-size: clamp(28px, 4vw, 44px); line-height: 1; }
    .subtitle, .meta, .scene-copy p, summary small, .empty {
      color: var(--muted);
      font-size: 14px;
    }
    .ui-section + .ui-section { margin-top: 36px; }
    .ui-heading {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 14px;
    }
    .eyebrow {
      color: var(--accent);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      margin-bottom: 4px;
    }
    .theme-section {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }
    .theme-section + .theme-section { margin-top: 14px; }
    summary {
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 14px 18px;
      font-weight: 700;
      border-bottom: 1px solid transparent;
    }
    .theme-name {
      display: inline-flex;
      align-items: center;
      gap: 9px;
    }
    .theme-toggle {
      display: inline-grid;
      place-items: center;
      width: 18px;
      height: 18px;
      border: 1px solid var(--border);
      border-radius: 4px;
      color: var(--accent);
      font-size: 14px;
      line-height: 1;
      background: rgba(255, 255, 255, 0.58);
    }
    .theme-toggle::before { content: "+"; }
    details[open] .theme-toggle::before { content: "-"; }
    details[open] summary { border-bottom-color: var(--border); }
    .scene-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 18px;
      padding: 18px;
    }
    .scene-card {
      min-width: 0;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #fff;
      overflow: hidden;
    }
    .shot-link {
      display: block;
      background: #e9e2d3;
      border-bottom: 1px solid var(--border);
    }
    img {
      display: block;
      width: 100%;
      aspect-ratio: 16 / 10;
      object-fit: contain;
    }
    .scene-copy { padding: 12px 14px 14px; }
    .scene-copy h3 {
      font-size: 15px;
      line-height: 1.25;
      margin-bottom: 5px;
    }
    .viewer {
      position: fixed;
      inset: 0;
      z-index: 1000;
      display: none;
      background: rgba(10, 10, 9, 0.94);
      color: #fff;
    }
    .viewer.open {
      display: grid;
      place-items: center;
    }
    .viewer-img {
      max-width: 100vw;
      max-height: 100vh;
      object-fit: contain;
    }
    .viewer-chrome,
    .viewer-nav {
      position: fixed;
      opacity: 1;
      transition: opacity 0.25s ease;
    }
    .viewer.is-idle .viewer-chrome,
    .viewer.is-idle .viewer-nav {
      opacity: 0;
      pointer-events: none;
    }
    .viewer-chrome {
      top: 0;
      left: 0;
      right: 0;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
      padding: 18px;
      background: linear-gradient(to bottom, rgba(0, 0, 0, 0.72), rgba(0, 0, 0, 0));
    }
    .viewer-title {
      font-weight: 800;
      font-size: 17px;
      line-height: 1.2;
    }
    .viewer-actions {
      display: flex;
      align-items: center;
      gap: 14px;
      margin-left: auto;
    }
    .viewer-meta {
      color: rgba(255, 255, 255, 0.72);
      font-size: 13px;
      text-align: right;
      white-space: nowrap;
    }
    .viewer-btn {
      appearance: none;
      border: 1px solid rgba(255, 255, 255, 0.28);
      background: rgba(0, 0, 0, 0.42);
      color: #fff;
      cursor: pointer;
      border-radius: 8px;
      min-width: 42px;
      min-height: 42px;
      font-size: 24px;
      line-height: 1;
    }
    .viewer-btn:hover,
    .viewer-btn:focus-visible {
      border-color: rgba(255, 255, 255, 0.72);
      background: rgba(255, 255, 255, 0.14);
      outline: none;
    }
    .viewer-prev,
    .viewer-next {
      top: 50%;
      transform: translateY(-50%);
      width: 52px;
      height: 76px;
    }
    .viewer-prev { left: 18px; }
    .viewer-next { right: 18px; }
    @media (max-width: 720px) {
      main {
        width: min(100% - 28px, 1440px);
        padding-top: 26px;
      }
      .page-header, .ui-heading {
        display: block;
      }
      .meta { margin-top: 8px; }
      .scene-grid {
        grid-template-columns: 1fr;
        padding: 12px;
      }
      .viewer-chrome {
        align-items: flex-start;
        gap: 10px;
        padding: 12px;
      }
      .viewer-actions {
        gap: 8px;
      }
      .viewer-meta {
        white-space: normal;
        max-width: 42vw;
      }
      .viewer-prev { left: 8px; }
      .viewer-next { right: 8px; }
    }
  </style>
</head>
<body>
  <main>
    <header class="page-header">
      <div>
        <p class="eyebrow">darklab_shell</p>
        <h1>UI Capture Review</h1>
      </div>
      <p class="subtitle">Generated ${escapeHtml(generatedAt)}</p>
    </header>
    ${body}
  </main>
  <div class="viewer" id="viewer" aria-hidden="true">
    <img class="viewer-img" id="viewer-img" alt="">
    <div class="viewer-chrome">
      <div class="viewer-title" id="viewer-title"></div>
      <div class="viewer-actions">
        <div class="viewer-meta" id="viewer-meta"></div>
        <button class="viewer-btn viewer-close" id="viewer-close" type="button" aria-label="Close viewer">x</button>
      </div>
    </div>
    <button class="viewer-btn viewer-nav viewer-prev" id="viewer-prev" type="button" aria-label="Previous image">&lt;</button>
    <button class="viewer-btn viewer-nav viewer-next" id="viewer-next" type="button" aria-label="Next image">&gt;</button>
  </div>
  <script>
    (() => {
      const links = Array.from(document.querySelectorAll('[data-viewer-image]'))
      const viewer = document.getElementById('viewer')
      const img = document.getElementById('viewer-img')
      const title = document.getElementById('viewer-title')
      const meta = document.getElementById('viewer-meta')
      const closeBtn = document.getElementById('viewer-close')
      const prevBtn = document.getElementById('viewer-prev')
      const nextBtn = document.getElementById('viewer-next')
      if (!links.length || !viewer || !img || !title || !meta) return

      let index = 0
      let idleTimer = null

      const showChrome = () => {
        viewer.classList.remove('is-idle')
        clearTimeout(idleTimer)
        idleTimer = setTimeout(() => viewer.classList.add('is-idle'), 2600)
      }

      const render = () => {
        const link = links[index]
        img.src = link.dataset.viewerImage || link.href
        img.alt = link.querySelector('img')?.alt || link.dataset.viewerTitle || 'Capture screenshot'
        title.textContent = link.dataset.viewerTitle || 'Untitled scene'
        meta.textContent = [link.dataset.viewerUi, link.dataset.viewerTheme, link.dataset.viewerRoute]
          .filter(Boolean)
          .join(' · ')
        showChrome()
      }

      const open = (nextIndex) => {
        index = nextIndex
        render()
        viewer.classList.add('open')
        viewer.setAttribute('aria-hidden', 'false')
        document.body.style.overflow = 'hidden'
      }

      const close = () => {
        viewer.classList.remove('open', 'is-idle')
        viewer.setAttribute('aria-hidden', 'true')
        document.body.style.overflow = ''
        clearTimeout(idleTimer)
      }

      const step = (delta) => {
        index = (index + delta + links.length) % links.length
        render()
      }

      links.forEach((link, i) => {
        link.addEventListener('click', (event) => {
          event.preventDefault()
          open(i)
        })
      })
      closeBtn?.addEventListener('click', close)
      prevBtn?.addEventListener('click', () => step(-1))
      nextBtn?.addEventListener('click', () => step(1))
      viewer.addEventListener('mousemove', showChrome)
      viewer.addEventListener('pointerdown', showChrome)
      document.addEventListener('keydown', (event) => {
        if (!viewer.classList.contains('open')) return
        if (event.key === 'Escape') close()
        if (event.key === 'ArrowLeft') step(-1)
        if (event.key === 'ArrowRight') step(1)
      })
    })()
  </script>
</body>
</html>
`
  writeFileSync(resolve(CAPTURE_ROOT, 'index.html'), html)
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
    ({ longCmd, fastCmd, mockRuns }) => {
      const originalFetch = window.fetch.bind(window)
      const encoder = new TextEncoder()
      let mockRunIndex = 0
      const mockStreams = new Map()

      const sseEvent = (payload) => `data: ${JSON.stringify(payload)}\n\n`
      const mockRunResponse = (mock) => {
        mockRunIndex += 1
        const runId = `capture-mock-run-${mockRunIndex}`
        const output = Array.isArray(mock.output) ? mock.output : []
        const body = [
          sseEvent({ type: 'started', run_id: runId }),
          ...output.map((line) => sseEvent({ type: 'output', text: `${line}\n` })),
          sseEvent({ type: 'exit', code: mock.exitCode || 0, elapsed: mock.elapsed || 0.1 }),
        ].join('')
        mockStreams.set(runId, body)
        return new Response(JSON.stringify({ run_id: runId, stream: `/runs/${runId}/stream` }), {
          status: 202,
          headers: { 'Content-Type': 'application/json' },
        })
      }

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

        if (url.endsWith('/runs') && method === 'POST') {
          const payload = JSON.parse(rawBody || '{}')
          const command = payload.command || ''

          if (Object.prototype.hasOwnProperty.call(mockRuns, command)) {
            return mockRunResponse(mockRuns[command])
          }

          if (command === longCmd) {
            return new Response(JSON.stringify({
              run_id: 'capture-long-run',
              stream: '/runs/capture-long-run/stream',
            }), {
              status: 202,
              headers: { 'Content-Type': 'application/json' },
            })
          }

          if (command === fastCmd) {
            mockStreams.set('capture-fast-run', [
              'data: {"type":"started","run_id":"capture-fast-run"}\n\n',
              'data: {"type":"output","text":"capture fast run output\\n"}\n\n',
              'data: {"type":"exit","code":0,"elapsed":0.1}\n\n',
            ].join(''))
            return new Response(JSON.stringify({
              run_id: 'capture-fast-run',
              stream: '/runs/capture-fast-run/stream',
            }), {
              status: 202,
              headers: { 'Content-Type': 'application/json' },
            })
          }
        }

        if (url.includes('/runs/capture-long-run/stream')) {
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

        const streamMatch = url.match(/\/runs\/([^/]+)\/stream/)
        if (streamMatch && mockStreams.has(streamMatch[1])) {
          return new Response(mockStreams.get(streamMatch[1]), {
            status: 200,
            headers: { 'Content-Type': 'text/event-stream' },
          })
        }

        return originalFetch(input, init)
      }
    },
    { longCmd: LONG_RUN_CMD, fastCmd: FAST_RUN_CMD, mockRuns: CAPTURE_MOCK_RUNS },
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
  await page.waitForFunction(
    () => window.__sessionPreferencesLoadState === 'settled',
    { timeout: 10_000 },
  )
  await page.waitForFunction(() => {
    if (typeof applyThemeSelection !== 'function') return false
    const registry = window.ThemeRegistry
    return Boolean(registry && Array.isArray(registry.themes))
  }, { timeout: 10_000 })
  if (themeName) {
    await page.waitForFunction((name) => {
      const registry = window.ThemeRegistry
      if (!registry || !Array.isArray(registry.themes)) return false
      return registry.themes.some((theme) => theme && theme.name === name)
    }, themeName, { timeout: 10_000 })
    let themeApplied = false
    for (let attempt = 0; attempt < 3 && !themeApplied; attempt += 1) {
      await page.evaluate((name) => {
        if (typeof applyThemeSelection === 'function') applyThemeSelection(name, false)
      }, themeName)
      try {
        await page.waitForFunction(
          (name) => {
            const bodyTheme = document.body?.dataset?.theme || ''
            const registry = window.ThemeRegistry
            const currentTheme = registry?.current?.name || ''
            const entry = Array.isArray(registry?.themes)
              ? registry.themes.find((theme) => theme && theme.name === name)
              : null
            const expectedBg = entry?.vars?.['--bg'] || ''
            const appliedBg = getComputedStyle(document.body).getPropertyValue('--bg').trim()
            return bodyTheme === name && currentTheme === name && (!expectedBg || appliedBg === expectedBg)
          },
          themeName,
          { timeout: 2_500 },
        )
        await page.waitForTimeout(100)
        themeApplied = true
      } catch (_) {
        if (attempt < 2) await page.waitForTimeout(250)
      }
    }
    if (!themeApplied) {
      await page.waitForFunction(
        (name) => {
          const bodyTheme = document.body?.dataset?.theme || ''
          const registry = window.ThemeRegistry
          const currentTheme = registry?.current?.name || ''
          const entry = Array.isArray(registry?.themes)
            ? registry.themes.find((theme) => theme && theme.name === name)
            : null
          const expectedBg = entry?.vars?.['--bg'] || ''
          const appliedBg = getComputedStyle(document.body).getPropertyValue('--bg').trim()
          return bodyTheme === name && currentTheme === name && (!expectedBg || appliedBg === expectedBg)
        },
        themeName,
        { timeout: 10_000 },
      )
      await page.waitForTimeout(100)
    }
  } else {
    await page.waitForFunction(() => Boolean(document.body?.dataset?.theme), { timeout: 10_000 })
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
