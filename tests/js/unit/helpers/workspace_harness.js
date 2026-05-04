import { vi } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

const SEARCH_CORE_SRC = readFileSync(resolve(process.cwd(), 'app/static/js/search_core.js'), 'utf8')
const SEARCH_SRC = readFileSync(resolve(process.cwd(), 'app/static/js/search.js'), 'utf8')
const CORE_SRC = readFileSync(resolve(process.cwd(), 'app/static/js/workspace_core.js'), 'utf8')
const SRC = readFileSync(resolve(process.cwd(), 'app/static/js/workspace.js'), 'utf8')

export function responseJson(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

export async function flushWorkspacePromises() {
  for (let i = 0; i < 6; i += 1) await Promise.resolve()
}

export function setupWorkspace(apiFetch = vi.fn(), overrides = {}) {
  document.body.innerHTML = `
    <div id="workspace-summary"></div>
    <div id="workspace-message" class="u-hidden"></div>
    <nav id="workspace-breadcrumbs"></nav>
    <div id="workspace-file-list"></div>
    <div id="workspace-viewer-overlay" class="u-hidden">
    <section id="workspace-viewer" class="u-hidden">
      <div id="workspace-viewer-title"></div>
      <button type="button" id="workspace-viewer-refresh-btn" data-workspace-viewer-refresh>
        <span class="workspace-refresh-glyph"></span>
        <span>Refresh</span>
      </button>
      <button type="button" id="workspace-viewer-auto-refresh-toggle" data-workspace-viewer-auto-refresh aria-pressed="false">
        <span class="workspace-auto-refresh-glyph"></span>
        <span id="workspace-viewer-auto-refresh-label">Auto - off</span>
      </button>
      <button type="button" data-workspace-viewer-action="edit"></button>
      <button type="button" data-workspace-viewer-action="download"></button>
      <button type="button" data-workspace-viewer-action="delete"></button>
      <div class="workspace-viewer-header"></div>
      <div id="workspace-viewer-controls"></div>
      <div id="workspace-viewer-text"></div>
    </section>
    </div>
    <div id="workspace-editor-overlay" class="u-hidden">
    <form id="workspace-editor" class="u-hidden">
      <div id="workspace-editor-title"></div>
      <input id="workspace-path-input">
      <textarea id="workspace-text-input"></textarea>
      <button id="workspace-save-btn" type="submit"></button>
    </form>
    </div>
    <button id="workspace-refresh-btn" type="button"></button>
    <button id="workspace-new-folder-btn" type="button"></button>
    <button id="workspace-new-btn" type="button"></button>
    <button id="workspace-cancel-edit-btn" type="button"></button>
    <button id="workspace-close-viewer-btn" type="button"></button>
  `
  const testWindow = Object.create(window)
  testWindow.requestAnimationFrame = (fn) => {
    if (typeof fn === 'function') fn()
    return 1
  }
  const globals = {
    document,
    window: testWindow,
    URL,
    Blob,
    APP_CONFIG: { workspace_enabled: true },
    Element: window.Element,
    NodeFilter: window.NodeFilter,
    activeTabId: 'tab-1',
    getOutput: vi.fn(() => document.createElement('div')),
    searchScope: 'text',
    apiFetch,
    escapeRegex: (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'),
    showWorkspaceOverlay: vi.fn(),
    hideWorkspaceOverlay: vi.fn(),
    hideWorkspaceEditor: undefined,
    _closeMajorOverlays: vi.fn(),
    blurVisibleComposerInputIfMobile: vi.fn(),
    refocusComposerAfterAction: vi.fn(),
    applyMobileTextInputDefaults: vi.fn((input) => {
      input.setAttribute('autocomplete', 'off')
      input.setAttribute('autocapitalize', 'none')
      input.setAttribute('autocorrect', 'off')
      input.setAttribute('spellcheck', 'false')
      input.setAttribute('inputmode', 'text')
    }),
    showConfirm: vi.fn(() => Promise.resolve('delete')),
    showToast: vi.fn(),
    bindPressable: vi.fn((el, opts) => {
      if (!el || !opts || typeof opts.onActivate !== 'function') return null
      if (el.dataset) el.dataset.pressableBound = '1'
      el.addEventListener('click', opts.onActivate)
      el.addEventListener('keydown', event => {
        if (event.key !== 'Enter' && event.key !== ' ') return
        event.preventDefault()
        opts.onActivate(event)
      })
      return { dispose: vi.fn() }
    }),
    setTimeout: (fn) => {
      if (typeof fn === 'function') fn()
      return 0
    },
    clearTimeout: vi.fn(),
    setInterval: vi.fn(() => 0),
    clearInterval: vi.fn(),
    workspaceSummary: document.getElementById('workspace-summary'),
    workspaceMessage: document.getElementById('workspace-message'),
    workspaceBreadcrumbs: document.getElementById('workspace-breadcrumbs'),
    workspaceFileList: document.getElementById('workspace-file-list'),
    workspaceViewerOverlay: document.getElementById('workspace-viewer-overlay'),
    workspaceViewer: document.getElementById('workspace-viewer'),
    workspaceViewerTitle: document.getElementById('workspace-viewer-title'),
    workspaceViewerControls: document.getElementById('workspace-viewer-controls'),
    workspaceViewerText: document.getElementById('workspace-viewer-text'),
    workspaceViewerRefreshBtn: document.getElementById('workspace-viewer-refresh-btn'),
    workspaceViewerAutoRefreshToggle: document.getElementById('workspace-viewer-auto-refresh-toggle'),
    workspaceViewerAutoRefreshLabel: document.getElementById('workspace-viewer-auto-refresh-label'),
    workspaceEditorOverlay: document.getElementById('workspace-editor-overlay'),
    workspaceEditor: document.getElementById('workspace-editor'),
    workspaceEditorTitle: document.getElementById('workspace-editor-title'),
    workspacePathInput: document.getElementById('workspace-path-input'),
    workspaceTextInput: document.getElementById('workspace-text-input'),
    workspaceRefreshBtn: document.getElementById('workspace-refresh-btn'),
    workspaceNewBtn: document.getElementById('workspace-new-btn'),
    workspaceNewFolderBtn: document.getElementById('workspace-new-folder-btn'),
    workspaceCancelEditBtn: document.getElementById('workspace-cancel-edit-btn'),
    workspaceCloseViewerBtn: document.getElementById('workspace-close-viewer-btn'),
    workspaceSaveBtn: document.getElementById('workspace-save-btn'),
  }
  Object.assign(globals, overrides)
  const names = Object.keys(globals)
  const values = Object.values(globals)
  const returnExpr = `
    return {
      _formatWorkspaceBytes,
      renderWorkspaceFiles,
      renderWorkspaceBrowser,
      refreshWorkspaceFiles,
      saveWorkspaceFile,
      createWorkspaceDirectory,
      readWorkspaceFile,
      deleteWorkspacePath,
      deleteWorkspaceFile,
      moveWorkspacePath,
      openWorkspace,
      setWorkspaceMessage,
      showWorkspaceEditor,
      hideWorkspaceEditor,
      showWorkspaceViewer,
      hideWorkspaceViewer,
      openWorkspaceEditorFromCommand,
      getWorkspaceAutocompleteFileHints,
      handleWorkspaceFileAction,
      showWorkspaceViewerLoading,
      promptWorkspaceFolderName,
      promptWorkspaceMove,
    };
  `
  const fns = new Function(...names, `${SEARCH_CORE_SRC}\n${SEARCH_SRC}\n${CORE_SRC}\n${SRC}\n${returnExpr}`)(...values)
  return { ...fns, apiFetch, globals }
}
