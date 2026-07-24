// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath, pathToFileURL } from 'url'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryStorage } from './helpers/extract.js'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../../')
const SHELL_ENTRY_URL = pathToFileURL(resolve(REPO_ROOT, 'app/static/js/shell_bootstrap.entry.js')).href
const moduleUrl = relativePath => pathToFileURL(resolve(REPO_ROOT, relativePath)).href
const buildFile = assetPath => resolve(REPO_ROOT, 'app', assetPath.replace(/^\/+/, ''))

function readBuildAsset(assetPath) {
  return readFileSync(buildFile(assetPath), 'utf8')
}

function importedBuildChunks(text) {
  return new Set([...text.matchAll(/["']\.\/(static-chunk-[^"']+\.js)["']/g)].map(match => match[1]))
}

const REPRESENTATIVE_LAZY_ENTRIES = [
  '/static/js/features/atlas/atlas_overlay.js',
  '/static/js/features/atlas/atlas_mobile.js',
  '/static/js/features/history/history_run_details.js',
  '/static/js/features/workflows/workflows.js',
]

const EAGER_SHELL_OWNER_SNIPPETS = [
  'setRunnerHandlers({',
  'setTabsHandlers({',
  'setOutputHandlers({',
  'setOutputModeHandlers({',
  'addEventListener("storage"',
  'addEventListener("pagehide"',
]

const SHELL_IDS = [
  'ac-dropdown',
  'cmd',
  'command-catalog-body',
  'command-catalog-overlay',
  'command-catalog-title',
  'command-registry-body',
  'command-registry-categories',
  'command-registry-modal',
  'command-registry-overlay',
  'command-registry-search',
  'command-registry-subtitle',
  'confirm-host',
  'faq-modal',
  'faq-overlay',
  'hamburger-btn',
  'header-title',
  'hist-clear-all-btn',
  'hist-search-dropdown',
  'history-active-filters',
  'history-bulk-toolbar',
  'history-clear-filters',
  'history-close',
  'history-date-filter',
  'history-entity-input',
  'history-entity-type-filter',
  'history-exit-filter',
  'history-kind-filter',
  'history-list',
  'history-load-overlay',
  'history-mobile-filters-toggle',
  'history-pagination',
  'history-pagination-controls',
  'history-pagination-summary',
  'history-panel',
  'history-project-filter',
  'history-root-dropdown',
  'history-root-input',
  'history-row',
  'history-search-input',
  'history-signal-filter',
  'history-starred-toggle',
  'history-type-filter',
  'hud',
  'hud-actions',
  'hud-clock',
  'hud-db',
  'hud-last-exit',
  'hud-latency',
  'hud-project',
  'hud-project-cell',
  'hud-redis',
  'hud-session',
  'hud-tabs',
  'hud-uptime',
  'ln-btn',
  'mobile-cmd',
  'mobile-composer',
  'mobile-composer-host',
  'mobile-composer-row',
  'mobile-header-actions',
  'mobile-kb-helper',
  'mobile-kill-btn',
  'mobile-menu-atlas-hint',
  'mobile-menu-files-hint',
  'mobile-menu-history-count',
  'mobile-menu-ln-state',
  'mobile-menu-project-hint',
  'mobile-menu-schedules-count',
  'mobile-menu-sheet',
  'mobile-menu-sheet-scrim',
  'mobile-menu-theme-hint',
  'mobile-menu-ts-state',
  'mobile-menu-ts-submenu',
  'mobile-menu-watchers-count',
  'mobile-menu-workflows-count',
  'mobile-recent-peek',
  'mobile-recent-peek-count',
  'mobile-recent-peek-preview',
  'mobile-recents-chips',
  'mobile-recents-clear',
  'mobile-recents-filter-root',
  'mobile-recents-filters-clear',
  'mobile-recents-filters-expanded',
  'mobile-recents-filters-toggle',
  'mobile-recents-list',
  'mobile-recents-pagination',
  'mobile-recents-pagination-controls',
  'mobile-recents-pagination-summary',
  'mobile-recents-search',
  'mobile-recents-sheet',
  'mobile-recents-sheet-scrim',
  'mobile-run-btn',
  'mobile-shell',
  'mobile-shell-chrome',
  'mobile-shell-overlays',
  'mobile-shell-transcript',
  'mobile-team-scope-label',
  'new-tab-btn',
  'options-command-outcome-summaries-toggle',
  'options-compare-context-select',
  'options-compare-view-mode-select',
  'options-hud-clock-select',
  'options-ln-toggle',
  'options-modal',
  'options-notify-toggle',
  'options-overlay',
  'options-panel-secrets',
  'options-project-auto-link-external-runs-toggle',
  'options-project-auto-link-run-entities-toggle',
  'options-prompt-username-error',
  'options-prompt-username-input',
  'options-share-redaction-select',
  'options-tabs',
  'options-ts-select',
  'options-welcome-select',
  'permalink-toast',
  'rail',
  'rail-collapse-btn',
  'rail-diag-btn',
  'rail-more-btn',
  'rail-more-menu',
  'rail-nav',
  'rail-recent-count',
  'rail-recent-header',
  'rail-recent-list',
  'rail-resize-handle',
  'rail-section-recent',
  'rail-section-workflows',
  'rail-split-area',
  'rail-splitter',
  'rail-wordmark-title',
  'rail-workflows-count',
  'rail-workflows-header',
  'rail-workflows-list',
  'run-btn',
  'run-timer',
  'search-bar',
  'search-case-btn',
  'search-close-btn',
  'search-count',
  'search-input',
  'search-next',
  'search-prev',
  'search-regex-btn',
  'search-signal-summary',
  'search-summary-btn',
  'search-toggle-btn',
  'shell-input-row',
  'shell-prompt-text',
  'shell-prompt-wrap',
  'shortcuts-list',
  'shortcuts-modal',
  'shortcuts-overlay',
  'status',
  'tab-panels',
  'tabbar-chrome',
  'tabbar-chrome-toggle',
  'tabs-bar',
  'tabs-scroll-left',
  'tabs-scroll-right',
  'team-scope-announcer',
  'team-scope-current',
  'team-scope-label',
  'team-scope-list',
  'team-scope-modal',
  'team-scope-overlay',
  'team-scope-status',
  'team-scope-trigger',
  'theme-modal',
  'theme-overlay',
  'theme-select',
  'ts-btn',
  'workflows-modal',
  'workflows-overlay',
  'workspace-breadcrumbs',
  'workspace-cancel-edit-btn',
  'workspace-close-viewer-btn',
  'workspace-editor',
  'workspace-editor-overlay',
  'workspace-editor-title',
  'workspace-file-usage',
  'workspace-file-usage-fill',
  'workspace-file-list',
  'workspace-inspector',
  'workspace-inspector-content',
  'workspace-inspector-empty',
  'workspace-labels-input',
  'workspace-message',
  'workspace-modal',
  'workspace-new-btn',
  'workspace-new-folder-btn',
  'workspace-notes-input',
  'workspace-overlay',
  'workspace-path-input',
  'workspace-refresh-btn',
  'workspace-result-summary',
  'workspace-read-only-status',
  'workspace-save-btn',
  'workspace-scope-badge',
  'workspace-search-input',
  'workspace-sort-select',
  'workspace-storage-usage',
  'workspace-storage-usage-fill',
  'workspace-summary',
  'workspace-text-input',
  'workspace-up-btn',
  'workspace-viewer',
  'workspace-viewer-auto-refresh-label',
  'workspace-viewer-auto-refresh-toggle',
  'workspace-viewer-controls',
  'workspace-viewer-overlay',
  'workspace-viewer-refresh-btn',
  'workspace-viewer-text',
  'workspace-viewer-title',
]

function tagForId(id) {
  if (id === 'cmd' || id === 'mobile-cmd' || id.endsWith('-input') || id.endsWith('-search')) return 'input'
  if (id.endsWith('-select')) return 'select'
  if (id.endsWith('-form')) return 'form'
  if (id.endsWith('-btn') || id.includes('-btn-') || id.endsWith('-toggle')) return 'button'
  if (id.endsWith('-list')) return 'ul'
  return 'div'
}

function shellConfig() {
  return {
    app_name: 'darklab',
    app_version: 'test',
    max_tabs: 5,
    max_output_lines: 100,
    recent_commands_limit: 20,
    default_theme: 'dark',
    themes: [
      { name: 'dark', label: 'Dark', mode: 'dark', colors: {} },
      { name: 'light', label: 'Light', mode: 'light', colors: {} },
    ],
    share_redaction_enabled: true,
    share_redaction_rules: [],
    features: {
      tour: false,
      workspace: true,
    },
  }
}

function responseJson(payload) {
  return Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve(payload),
    text: () => Promise.resolve(JSON.stringify(payload)),
  })
}

function scaffoldShellDom() {
  document.body.innerHTML = `
    <script id="app-config-json" type="application/json">${JSON.stringify(shellConfig())}</script>
    <script id="lazy-assets-json" type="application/json">{}</script>
    <main class="terminal-wrap"></main>
  `
  const root = document.querySelector('.terminal-wrap')
  SHELL_IDS.forEach((id) => {
    const el = document.createElement(tagForId(id))
    el.id = id
    root.appendChild(el)
  })
  document.getElementById('mobile-menu-sheet').innerHTML = `
    <button data-menu-action="ts-toggle"></button>
    <button data-menu-action="ts-set" data-ts-mode="off"></button>
    <button class="u-hidden" data-menu-action="compare-active"></button>
    <button data-menu-action="diag"></button>
  `
  document.getElementById('mobile-kb-helper').innerHTML = '<button data-kb-action="left"></button>'
  document.getElementById('faq-modal').innerHTML = '<button class="faq-close"></button><div class="faq-body"></div>'
  document.getElementById('workflows-modal').innerHTML = '<button class="workflows-close"></button>'
  document.getElementById('shortcuts-modal').innerHTML = '<button class="shortcuts-close"></button>'
  document.getElementById('theme-modal').innerHTML = '<button class="theme-close"></button>'
  document.getElementById('options-modal').innerHTML = '<button class="options-close"></button>'
  document.getElementById('workspace-modal').innerHTML = '<button class="workspace-close"></button>'
  document.getElementById('command-registry-modal').innerHTML = '<button class="command-registry-close"></button>'
  document.getElementById('rail-more-menu').innerHTML = '<button data-action="history"></button>'
  document.getElementById('mobile-recent-peek').innerHTML = '<span class="recent-peek-label"></span>'
  window.ThemeCssVars = { current: {}, fallback: {} }
  window.ThemeRegistry = {
    current: { name: 'dark', label: 'Dark', source: 'test', vars: {} },
    themes: [
      { name: 'dark', label: 'Dark', source: 'test', vars: {} },
      { name: 'light', label: 'Light', source: 'test', vars: {} },
    ],
  }
}

function installFetchMock() {
  vi.spyOn(globalThis, 'fetch').mockImplementation((url) => {
    const path = String(url || '')
    if (path.includes('/autocomplete')) {
      return responseJson({
        suggestions: [],
        context: {},
        wordlists: [],
        special_commands: [],
        builtin_command_roots: [],
      })
    }
    if (path.includes('/session/variables')) return responseJson({ variables: [] })
    if (path.includes('/recent-values')) return responseJson({ values: [] })
    if (path.includes('/history')) return responseJson({ runs: [], total: 0 })
    if (path.includes('/workspace')) return responseJson({ files: [], entries: [] })
    if (path.includes('/team-scopes')) return responseJson({ scopes: [], active_team_id: null })
    return responseJson({})
  })
}

function installStorage() {
  const local = new MemoryStorage()
  const session = new MemoryStorage()
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: local })
  Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, value: session })
  Object.defineProperty(window, 'localStorage', { configurable: true, value: local })
  Object.defineProperty(window, 'sessionStorage', { configurable: true, value: session })
}

beforeEach(() => {
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  installStorage()
  installFetchMock()
  scaffoldShellDom()
})

afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
  sessionStorage.clear()
  document.body.innerHTML = ''
})

describe('shell module entry', () => {
  it('loads the source-mode shell graph and keeps cross-module bridges live', async () => {
    await import(`${SHELL_ENTRY_URL}?test=${Date.now()}`)
    await Promise.resolve()
    const [
      tabsModule,
      outputModule,
      faqHelpersModule,
      themeModule,
      preferencesModule,
      stateModule,
      compareBridgeModule,
    ] = await Promise.all([
      import(moduleUrl('app/static/js/tabs.js')),
      import(moduleUrl('app/static/js/output.js')),
      import(moduleUrl('app/static/js/features/command-registry/faq_helpers.js')),
      import(moduleUrl('app/static/js/features/theme/theme.js')),
      import(moduleUrl('app/static/js/features/preferences/preferences.js')),
      import(moduleUrl('app/static/js/core/state.js')),
      import(moduleUrl('app/static/js/features/run-comparison/history_compare_bridge.js')),
    ])

    expect(typeof tabsModule.createTab).toBe('function')
    expect(typeof outputModule._stickOutputToBottom).toBe('function')
    expect(typeof faqHelpersModule.openAutocompleteForVisibleComposer).toBe('function')
    expect(typeof themeModule.applyThemeSelection).toBe('function')

    const tabId = tabsModule.createTab('module smoke')
    tabsModule.activateTab(tabId)
    const tab = stateModule.getTab(tabId)
    const out = tabsModule.getOutput(tabId)
    let scrollTop = 0
    Object.defineProperty(out, 'clientHeight', { configurable: true, get: () => 100 })
    Object.defineProperty(out, 'scrollHeight', { configurable: true, get: () => 300 })
    Object.defineProperty(out, 'scrollTop', {
      configurable: true,
      get: () => scrollTop,
      set: value => {
        scrollTop = value
      },
    })

    outputModule._stickOutputToBottom(out, tab)
    expect(scrollTop).toBe(300)

    themeModule.applyThemeSelection('light', true)
    await preferencesModule._persistCurrentSessionPreferences()
    expect(document.body.dataset.theme).toBe('light')
    expect(preferencesModule.getPreference('pref_theme_name')).toBe('light')

    const cmd = document.getElementById('cmd')
    cmd.value = 'nmap -'
    cmd.setSelectionRange(6, 6)
    stateModule.getAppState().acContextRegistry = {
      nmap: {
        flags: [{ value: '-sV', description: 'Version detection' }],
      },
    }
    expect(faqHelpersModule.openAutocompleteForVisibleComposer()).toBe(true)
    expect(document.querySelectorAll('#ac-dropdown .ac-item')).toHaveLength(1)

    const openComparison = vi.fn()
    compareBridgeModule.setHistoryCompareHandlers({ openHistoryCompareLauncher: openComparison })
    tab.st = 'ok'
    tab.historyRunId = 'run-module-smoke'
    tab.historyRunKind = 'external'
    stateModule.emitUiEvent('app:mobile-menu-show')
    const compareActive = document.querySelector('[data-menu-action="compare-active"]')
    expect(compareActive.classList.contains('u-hidden')).toBe(false)
    compareActive.click()
    expect(openComparison).toHaveBeenCalledWith(
      { id: 'run-module-smoke' },
      { returnFocus: document.getElementById('hamburger-btn') },
    )
    for (const state of [
      { st: 'running', historyRunId: 'run-module-smoke', historyRunKind: 'external' },
      { st: 'ok', historyRunId: 'run-module-smoke', historyRunKind: 'builtin' },
      { st: 'ok', historyRunId: '', historyRunKind: 'external' },
      { st: 'idle', historyRunId: null, historyRunKind: '' },
    ]) {
      Object.assign(tab, state)
      stateModule.emitUiEvent('app:mobile-menu-show')
      expect(compareActive.classList.contains('u-hidden')).toBe(true)
    }
  })

  it('keeps bundle-mode lazy entries on shared chunks without eager shell owner setup', () => {
    const manifest = JSON.parse(readFileSync(resolve(REPO_ROOT, 'app/static/build/manifest.json'), 'utf8'))
    const shellBundle = readBuildAsset(manifest.bundles['shell-bootstrap'].path)
    const shellChunks = importedBuildChunks(shellBundle)
    const lazyEntries = REPRESENTATIVE_LAZY_ENTRIES.map(source => ({
      source,
      text: readBuildAsset(manifest.static_assets[source].path),
    }))

    for (const { source, text } of lazyEntries) {
      const lazyChunks = importedBuildChunks(text)
      const sharedChunks = [...lazyChunks].filter(chunk => shellChunks.has(chunk))

      expect(lazyChunks.size, source).toBeGreaterThan(0)
      expect(sharedChunks.length, source).toBeGreaterThan(0)
      EAGER_SHELL_OWNER_SNIPPETS.forEach(snippet => {
        expect(text, `${source} should not contain ${snippet}`).not.toContain(snippet)
      })
    }
    expect(manifest.static_assets['/static/js/features/atlas/atlas_mobile_bridge.js']).toBeUndefined()
  })
})
