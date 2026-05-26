import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'fs'
import { dirname, relative, resolve } from 'path'
import { fileURLToPath } from 'url'

import { CAPTURE_SESSION_TOKEN } from '../../../.tooling/playwright.visual.contracts.js'

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
export const INTERACTIVE_CAPTURE_CMD = 'mtr --interactive darklab.sh'
export const WORKSPACE_CAPTURE_CMD = 'curl -L -o response.html https://noc.darklab.sh'
export const COMPARE_CAPTURE_LEFT_ID = 'capture-compare-left'
export const COMPARE_CAPTURE_RIGHT_ID = 'capture-compare-right'

export const CAPTURE_ATLAS_DATA = {
  summary: {
    total: 5,
    counts: { ip: 2, domain: 2, hash: 0, cve: 1, url: 0 },
    findings: 2,
  },
  findingCounts: { new: 1, reviewed: 1, important: 0, false_positive: 0, needs_followup: 0 },
  findings: [
    {
      id: 'capture-finding-443',
      title: '443/tcp open https',
      raw_line: '443/tcp open https nginx',
      review_state: 'new',
      status: 'new',
      severity: 'medium',
      tool_root: 'nmap',
      entity_id: 'capture-ent-ip',
      entity_type: 'ip',
      entity_value: '107.178.109.44',
      run_id: 'capture-run-nmap',
      run_command: 'nmap -sV 107.178.109.44',
      occurrence_count: 2,
      last_seen_at: '2026-05-15T00:01:00Z',
    },
    {
      id: 'capture-finding-cve',
      title: 'CVE-2026-0001 mentioned in service banner',
      raw_line: 'nginx banner references CVE-2026-0001',
      review_state: 'reviewed',
      status: 'reviewed',
      severity: 'low',
      tool_root: 'nuclei',
      entity_id: 'capture-ent-cve',
      entity_type: 'cve',
      entity_value: 'CVE-2026-0001',
      run_id: 'capture-run-nuclei',
      run_command: 'nuclei -u https://darklab.sh',
      occurrence_count: 1,
      last_seen_at: '2026-05-15T00:03:00Z',
    },
  ],
  entities: [
    {
      id: 'capture-ent-ip',
      type: 'ip',
      canonical_value: '107.178.109.44',
      occurrence_count: 4,
      run_count: 2,
      project_link_count: 1,
      project_links: [{ project_id: 'capture-project', project_name: 'Capture Investigation' }],
      labels: [{ label: 'edge' }],
      note: { body: 'Public edge host gathered during capture setup.' },
      first_seen_at: '2026-05-15T00:00:00Z',
      last_seen_at: '2026-05-15T00:04:00Z',
    },
    {
      id: 'capture-ent-ip-v6',
      type: 'ip',
      canonical_value: '2606:4700:3033::6815:423',
      occurrence_count: 2,
      run_count: 1,
      project_link_count: 0,
      project_links: [],
      labels: [],
      note: null,
      first_seen_at: '2026-05-15T00:02:00Z',
      last_seen_at: '2026-05-15T00:04:00Z',
    },
    {
      id: 'capture-ent-domain',
      type: 'domain',
      canonical_value: 'darklab.sh',
      occurrence_count: 5,
      run_count: 3,
      project_link_count: 1,
      project_links: [{ project_id: 'capture-project', project_name: 'Capture Investigation' }],
      labels: [{ label: 'primary' }],
      note: null,
      first_seen_at: '2026-05-15T00:00:00Z',
      last_seen_at: '2026-05-15T00:05:00Z',
    },
    {
      id: 'capture-ent-domain-noc',
      type: 'domain',
      canonical_value: 'noc.darklab.sh',
      occurrence_count: 3,
      run_count: 2,
      project_link_count: 1,
      project_links: [{ project_id: 'capture-project', project_name: 'Capture Investigation' }],
      labels: [],
      note: null,
      first_seen_at: '2026-05-15T00:01:00Z',
      last_seen_at: '2026-05-15T00:05:00Z',
    },
    {
      id: 'capture-ent-cve',
      type: 'cve',
      canonical_value: 'CVE-2026-0001',
      occurrence_count: 1,
      run_count: 1,
      project_link_count: 0,
      project_links: [],
      labels: [],
      note: null,
      first_seen_at: '2026-05-15T00:03:00Z',
      last_seen_at: '2026-05-15T00:03:00Z',
    },
  ],
}

export const CAPTURE_COMPARE_DATA = {
  left_run_id: COMPARE_CAPTURE_LEFT_ID,
  right_run_id: COMPARE_CAPTURE_RIGHT_ID,
  left: {
    id: COMPARE_CAPTURE_LEFT_ID,
    command: 'nmap -sV darklab.sh',
    started: '2026-05-12T18:20:00Z',
    finished: '2026-05-12T18:20:04Z',
    exit_code: 0,
    duration_seconds: 4,
    output_line_count: 5,
  },
  right: {
    id: COMPARE_CAPTURE_RIGHT_ID,
    command: 'nmap -sV darklab.sh',
    started: '2026-05-12T18:26:00Z',
    finished: '2026-05-12T18:26:05Z',
    exit_code: 0,
    duration_seconds: 5,
    output_line_count: 5,
  },
  deltas: {
    exit_code_changed: false,
    exit_code: { left: 0, right: 0 },
    duration_seconds: { delta: 1 },
    output_lines: { delta: 0 },
    findings: { delta: 0 },
  },
  totals: {
    left_total_lines: 4,
    right_total_lines: 4,
    equal_line_count: 2,
    changed_line_count: 1,
    added_line_count: 1,
    removed_line_count: 1,
  },
  limits: {
    line_display_truncate: 4000,
    lazy_equal_page_limit: 5000,
    lazy_equal_byte_limit: 512000,
    minimap_buckets: 256,
  },
  truncated: {
    hunks_omitted: 0,
    lines_omitted: { left: 0, right: 0, total: 0 },
  },
  hunks: [
    {
      op: 'equal',
      left: {
        start: 0,
        end: 2,
        lines: [
          { text: 'Starting Nmap 7.95 ( https://nmap.org ) at 2026-05-12 18:20 UTC', line_index: 0 },
          { text: '80/tcp open http', line_index: 1 },
        ],
      },
      right: {
        start: 0,
        end: 2,
        lines: [
          { text: 'Starting Nmap 7.95 ( https://nmap.org ) at 2026-05-12 18:26 UTC', line_index: 0 },
          { text: '80/tcp open http', line_index: 1 },
        ],
      },
      changed_pairs: [{
        left_index: 0,
        right_index: 0,
        segments: {
          left: [
            { text: 'Starting Nmap 7.95 ( https://nmap.org ) at 2026-05-12 18:' },
            { text: '20', changed: true },
            { text: ' UTC' },
          ],
          right: [
            { text: 'Starting Nmap 7.95 ( https://nmap.org ) at 2026-05-12 18:' },
            { text: '26', changed: true },
            { text: ' UTC' },
          ],
        },
      }],
      left_unpaired: [],
      right_unpaired: [],
    },
    {
      op: 'replace',
      left: {
        start: 2,
        end: 3,
        lines: [{ text: '8080/tcp open http-proxy', line_index: 2 }],
      },
      right: {
        start: 2,
        end: 3,
        lines: [{ text: '443/tcp open https', line_index: 2 }],
      },
      changed_pairs: [{
        left_index: 0,
        right_index: 0,
        segments: {
          left: [
            { text: '8080/tcp open ' },
            { text: 'http-proxy', changed: true },
          ],
          right: [
            { text: '443/tcp open ' },
            { text: 'https', changed: true },
          ],
        },
      }],
      left_unpaired: [],
      right_unpaired: [],
    },
    {
      op: 'insert',
      left: { start: 3, end: 3 },
      right: {
        start: 3,
        end: 4,
        lines: [{ text: '8443/tcp open ssl/https-alt', line_index: 3 }],
      },
    },
    {
      op: 'delete',
      left: {
        start: 3,
        end: 4,
        lines: [{ text: 'Nmap done: 1 IP address (1 host up) scanned in 0.41 seconds', line_index: 3 }],
      },
      right: { start: 4, end: 4 },
    },
  ],
  density_buckets: [
    { start: 0, end: 1, equal: 0, changed: 1, added: 0, removed: 0 },
    { start: 1, end: 2, equal: 1, changed: 0, added: 0, removed: 0 },
    { start: 2, end: 3, equal: 0, changed: 1, added: 0, removed: 0 },
    { start: 3, end: 4, equal: 0, changed: 0, added: 1, removed: 1 },
  ],
  objects: {
    findings: {
      added: [{
        id: 'capture-finding-right',
        title: 'open port 443',
        raw_line: '443/tcp open https',
        severity: 'medium',
        review_state: 'new',
        line_number: 2,
        compare_line_index: 2,
      }],
      removed: [{
        id: 'capture-finding-left',
        title: 'open port 8080',
        raw_line: '8080/tcp open http-proxy',
        severity: 'low',
        review_state: 'new',
        line_number: 2,
        compare_line_index: 2,
      }],
      unchanged_count: 1,
    },
    artifacts: {
      added: [{
        id: 'capture-artifact-right',
        workspace_path: 'reports/right-nmap.txt',
        display_name: 'right-nmap.txt',
        kind: 'output',
        byte_size: 128,
        detected_by: 'workspace_flag',
      }],
      removed: [{
        id: 'capture-artifact-left',
        workspace_path: 'reports/left-nmap.txt',
        display_name: 'left-nmap.txt',
        kind: 'output',
        byte_size: 112,
        detected_by: 'workspace_flag',
      }],
      unchanged_count: 0,
    },
  },
}

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
  [WORKSPACE_CAPTURE_CMD]: {
    output: [
      '[workspace] writing response.html',
      'HTTP/2 200',
      'saved response.html',
    ],
    elapsed: 0.2,
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
    ({
      longCmd,
      fastCmd,
      interactiveCmd,
      mockRuns,
      compareData,
      compareLeftId,
      compareRightId,
      atlasData,
    }) => {
      const originalFetch = window.fetch.bind(window)
      const encoder = new TextEncoder()
      let mockRunIndex = 0
      let ptyController = null
      const mockStreams = new Map()

      const sseEvent = (payload) => `data: ${JSON.stringify(payload)}\n\n`
      const jsonResponse = (payload) => new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
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
        const parsedUrl = (() => {
          try {
            return new URL(url, window.location.href)
          } catch (_) {
            return null
          }
        })()
        const path = parsedUrl?.pathname || url.split('?')[0]

        if (method === 'GET' && path === '/atlas') {
          return jsonResponse(atlasData.summary)
        }

        if (method === 'GET' && path === '/atlas/findings') {
          return jsonResponse({
            findings: atlasData.findings,
            total: atlasData.findings.length,
            limit: 50,
            offset: 0,
            counts: atlasData.findingCounts,
          })
        }

        if (method === 'GET' && path === '/atlas/entities') {
          const entityType = String(parsedUrl?.searchParams.get('type') || '')
          const entities = atlasData.entities.filter(entity => !entityType || entity.type === entityType)
          return jsonResponse({
            entities,
            total: entities.length,
            limit: 50,
            offset: 0,
          })
        }

        if (method === 'GET' && path.startsWith('/atlas/entities/')) {
          const entityId = decodeURIComponent(path.replace('/atlas/entities/', '').split('/')[0])
          const entity = atlasData.entities.find(item => item.id === entityId)
          if (!entity) {
            return new Response(JSON.stringify({ error: 'entity not found' }), {
              status: 404,
              headers: { 'Content-Type': 'application/json' },
            })
          }
          return jsonResponse({
            entity,
            intel_snapshots: entity.type === 'ip'
              ? [{
                  provider: 'Shodan',
                  status: 'ok',
                  summary: '2 open ports and 1 hostname',
                  data: {
                    providers: {
                      shodan: {
                        ports: [80, 443],
                        hostnames: ['edge.darklab.sh'],
                        cves: ['CVE-2026-0001'],
                        services: [
                          { port: 443, transport: 'tcp', product: 'nginx' },
                        ],
                      },
                    },
                  },
                  fetched_at: '2026-05-15T00:06:00Z',
                }]
              : [],
            intel_summary: entity.type === 'ip'
              ? {
                  status: 'available',
                  providers_with_data: ['shodan', 'censys'],
                  highlight_count: 3,
                  highlights: [
                    {
                      label: 'Open ports',
                      value: '80, 443',
                      provider: 'shodan',
                      provider_label: 'Shodan',
                      tone: 'neutral',
                    },
                    {
                      label: 'Hostname',
                      value: 'edge.darklab.sh',
                      provider: 'shodan',
                      provider_label: 'Shodan',
                      tone: 'neutral',
                    },
                    {
                      label: 'CVEs',
                      value: 'CVE-2026-0001',
                      provider: 'shodan',
                      provider_label: 'Shodan',
                      tone: 'warning',
                    },
                  ],
                  updated_at: '2026-05-15T00:06:00Z',
                }
              : { status: 'none', providers_with_data: [], highlight_count: 0, highlights: [] },
            runs: [
              {
                run_id: 'capture-run-nmap',
                command: 'nmap -sV 107.178.109.44',
                occurrence_count: 2,
                last_seen_at: '2026-05-15T00:04:00Z',
              },
            ],
            findings: atlasData.findings.filter(finding => finding.entity_id === entity.id),
          })
        }

        if (url.endsWith('/config')) {
          const original = await originalFetch(input, init)
          const cfg = await original.clone().json()
          return new Response(JSON.stringify({
            ...cfg,
            interactive_pty_enabled: true,
            interactive_pty_commands: [{
              root: 'mtr',
              trigger_flag: '--interactive',
              default_rows: 12,
              default_cols: 80,
              requires_args: true,
              allow_input: true,
            }],
          }), {
            status: original.status,
            headers: { 'Content-Type': 'application/json' },
          })
        }

        if (url.includes('/history/compare?') && method === 'GET') {
          return new Response(JSON.stringify(compareData), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        }

        if (url.endsWith('/workspace/files') && method === 'GET') {
          return new Response(JSON.stringify({
            files: [{
              name: 'response.html',
              path: 'response.html',
              size: 164,
              mtime: '2026-05-12 18:24',
              artifact_count: 1,
              artifact_run_count: 1,
              project_names: ['Capture Project'],
            }],
            directories: [],
            usage: { file_count: 1, bytes_used: 164 },
            limits: { max_files: 100, quota_bytes: 1048576 },
          }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        }

        if (url.includes('/workspace/files/read') && method === 'GET') {
          return new Response(JSON.stringify({
            path: 'response.html',
            size: 164,
            text: '<!doctype html>\n<title>darklab_shell capture</title>\n<body>captured response file</body>\n',
            rawText: '<!doctype html>\n<title>darklab_shell capture</title>\n<body>captured response file</body>\n',
            format: 'html',
          }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        }

        if (url.endsWith(`/history/${compareLeftId}/compare-candidates`) && method === 'GET') {
          return new Response(JSON.stringify({
            source: compareData.left,
            suggested: { ...compareData.right, confidence: 'exact_command', confidence_label: 'Exact command' },
            candidates: [{ ...compareData.right, confidence: 'exact_command', confidence_label: 'Exact command' }],
          }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        }

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

        if (url.endsWith('/pty/runs') && method === 'POST') {
          const payload = JSON.parse(rawBody || '{}')
          if (String(payload.command || '') !== interactiveCmd) return originalFetch(input, init)
          return new Response(JSON.stringify({
            run_id: 'capture-pty-run',
            stream: '/pty/runs/capture-pty-run/stream',
            command: 'mtr darklab.sh',
            interactive: true,
            rows: 12,
            cols: 80,
          }), {
            status: 202,
            headers: { 'Content-Type': 'application/json' },
          })
        }

        if (url.endsWith('/pty/runs/capture-pty-run/snapshot')) {
          return new Response(JSON.stringify({
            run_id: 'capture-pty-run',
            command: interactiveCmd,
            started: '2026-05-12T18:30:00Z',
            rows: 12,
            cols: 80,
            after_event_id: '1770000000000-2',
            entries: [{ text: 'capture hop darklab.sh', cls: '' }],
            snapshot_format: 'ansi',
            ansi_snapshot: '\u001b[0m\u001b[2J\u001b[Hcapture hop darklab.sh\u001b[2;1Hpress q to quit\u001b[1;1H',
            snapshot_truncated: false,
          }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        }

        if (url.includes('/pty/runs/capture-pty-run/stream')) {
          const body = new ReadableStream({
            start(controller) {
              ptyController = controller
              controller.enqueue(encoder.encode(sseEvent({ type: 'started', run_id: 'capture-pty-run' })))
              controller.enqueue(encoder.encode(sseEvent({ type: 'output', text: 'capture hop darklab.sh\r\n' })))
              controller.enqueue(encoder.encode(sseEvent({ type: 'output', text: ' 1  192.0.2.1    0.4 ms\r\n' })))
              controller.enqueue(encoder.encode(sseEvent({ type: 'output', text: ' 2  darklab.sh   12.7 ms\r\n' })))
            },
          })
          return new Response(body, {
            status: 200,
            headers: { 'Content-Type': 'text/event-stream' },
          })
        }

        if (url.endsWith('/pty/runs/capture-pty-run/resize') && method === 'POST') {
          return new Response('{}', {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        }

        if (url.endsWith('/pty/runs/capture-pty-run/input') && method === 'POST') {
          return new Response('{}', {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        }

        if (url.includes('/history/capture-pty-run')) {
          return new Response(JSON.stringify({
            id: 'capture-pty-run',
            command: interactiveCmd,
            exit_code: 143,
            output_entries: [
              { text: 'capture hop darklab.sh', cls: '' },
              { text: ' 1  192.0.2.1    0.4 ms', cls: '' },
              { text: ' 2  darklab.sh   12.7 ms', cls: '' },
            ],
          }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        }

        if (url.endsWith('/kill') && method === 'POST' && rawBody.includes('capture-pty-run')) {
          if (ptyController) {
            ptyController.enqueue(encoder.encode(sseEvent({ type: 'exit', code: 143, elapsed: 0.1 })))
            ptyController.close()
            ptyController = null
          }
          return new Response('{}', {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
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
    {
      longCmd: LONG_RUN_CMD,
      fastCmd: FAST_RUN_CMD,
      interactiveCmd: INTERACTIVE_CAPTURE_CMD,
      mockRuns: CAPTURE_MOCK_RUNS,
      compareData: CAPTURE_COMPARE_DATA,
      compareLeftId: COMPARE_CAPTURE_LEFT_ID,
      compareRightId: COMPARE_CAPTURE_RIGHT_ID,
      atlasData: CAPTURE_ATLAS_DATA,
    },
  )
}

export async function activeHistoryRunId(page, expectedCommand = '') {
  return page.waitForFunction(
    (command) => {
      const tab = typeof getActiveTab === 'function' ? getActiveTab() : null
      if (!tab) return ''
      if (command && tab.command !== command) return ''
      return tab.historyRunId || tab.runId || ''
    },
    expectedCommand,
    { timeout: 15_000 },
  ).then(handle => handle.jsonValue())
}

export async function createCaptureProjectFixture(page, {
  name = 'Capture Investigation',
  runIds = [],
  target = 'capture.darklab.sh',
  note = 'Capture project notes show how investigations stay organized.',
} = {}) {
  return page.evaluate(async ({ projectName, linkedRunIds, targetValue, noteBody }) => {
    const requestJson = async (url, options = {}) => {
      const resp = await apiFetch(url, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...(options.headers || {}),
        },
      })
      const data = await resp.json().catch(() => ({}))
      if (!resp.ok) throw new Error(data.error || `Request failed: ${url}`)
      return data
    }

    const created = await requestJson('/projects', {
      method: 'POST',
      body: JSON.stringify({ name: projectName }),
    })
    const project = created.project
    await requestJson('/projects/active', {
      method: 'POST',
      body: JSON.stringify({ project_id: project.id }),
    })
    await requestJson(`/entities/project/${encodeURIComponent(project.id)}/labels`, {
      method: 'POST',
      body: JSON.stringify({ label: 'capture' }),
    })
    await requestJson(`/entities/project/${encodeURIComponent(project.id)}/note`, {
      method: 'PUT',
      body: JSON.stringify({ body: noteBody }),
    })
    const linked = []
    for (const runId of linkedRunIds.filter(Boolean)) {
      try {
        await requestJson(`/projects/${encodeURIComponent(project.id)}/links`, {
          method: 'POST',
          body: JSON.stringify({ entity_type: 'run', entity_id: runId, source: 'manual' }),
        })
        linked.push(runId)
      } catch (_) {
        // Capture runs are often mocked in-browser and may not exist in the
        // server history table. Keep the project scene useful by showing the
        // active project, labels, notes, and target even without a linked run.
      }
    }
    const targetBody = { type: 'domain', value: targetValue }
    if (linked[0]) targetBody.source_run_id = linked[0]
    const targetResp = await requestJson(`/projects/${encodeURIComponent(project.id)}/targets`, {
      method: 'POST',
      body: JSON.stringify(targetBody),
    })
    await requestJson(`/entities/target/${encodeURIComponent(targetResp.target.id)}/labels`, {
      method: 'POST',
      body: JSON.stringify({ label: 'external' }),
    })
    return project
  }, {
    projectName: name,
    linkedRunIds: runIds,
    targetValue: target,
    noteBody: note,
  })
}

export async function openCaptureRunComparison(page) {
  await page.evaluate(({ leftId, rightId }) => {
    if (typeof fetchAndRenderHistoryComparison !== 'function') {
      throw new Error('Run comparison UI is not loaded')
    }
    fetchAndRenderHistoryComparison(leftId, rightId)
  }, {
    leftId: COMPARE_CAPTURE_LEFT_ID,
    rightId: COMPARE_CAPTURE_RIGHT_ID,
  })
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
