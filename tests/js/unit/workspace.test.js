import { beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

const SEARCH_SRC = readFileSync(resolve(process.cwd(), 'app/static/js/search.js'), 'utf8')
const SRC = readFileSync(resolve(process.cwd(), 'app/static/js/workspace.js'), 'utf8')

function responseJson(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

async function flushWorkspacePromises() {
  for (let i = 0; i < 6; i += 1) await Promise.resolve()
}

function setupWorkspace(apiFetch = vi.fn(), overrides = {}) {
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
    };
  `
  const fns = new Function(...names, `${SEARCH_SRC}\n${SRC}\n${returnExpr}`)(...values)
  return { ...fns, apiFetch, globals }
}

describe('workspace UI helpers', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('renders workspace files with usage summary and row actions', () => {
    const { renderWorkspaceFiles } = setupWorkspace()

    renderWorkspaceFiles({
      files: [{ path: 'targets.txt', size: 11, mtime: '2026-01-01T00:00:00Z' }],
      usage: { bytes_used: 11, file_count: 1 },
      limits: { quota_bytes: 1024, max_files: 10 },
    })

    expect(document.getElementById('workspace-summary').textContent).toBe('1 / 10 files · 11 B / 1 KB')
    expect(document.querySelector('.workspace-file-name').textContent).toBe('targets.txt')
    expect([...document.querySelectorAll('[data-workspace-action]')].map(btn => btn.textContent)).toEqual([
      'View',
      'Edit',
      'Download',
      'Delete',
    ])
  })

  it('renders nested workspace paths as navigable folders with breadcrumbs', () => {
    const { renderWorkspaceFiles } = setupWorkspace()

    renderWorkspaceFiles({
      files: [
        { path: 'targets.txt', size: 11 },
        { path: 'amass-viz/amass.html', size: 2048 },
        { path: 'amass-viz/assets/app.js', size: 512 },
      ],
      usage: { bytes_used: 2571, file_count: 3 },
      limits: { quota_bytes: 4096, max_files: 10 },
    })

    expect([...document.querySelectorAll('.workspace-file-name')].map(node => node.textContent)).toEqual([
      'amass-viz',
      'targets.txt',
    ])
    expect(document.querySelector('.workspace-folder-row [data-workspace-action="open-folder"]').textContent)
      .toBe('Open')
    expect([...document.querySelectorAll('.workspace-folder-row [data-workspace-action]')].map(btn => btn.textContent))
      .toEqual(['Open', 'Delete'])
    expect(document.querySelector('.workspace-folder-row').dataset.pressableBound).toBe('1')

    document.querySelector('.workspace-folder-row .workspace-file-name').click()

    expect([...document.querySelectorAll('.workspace-file-name')].map(node => node.textContent)).toEqual([
      '..',
      'assets',
      'amass.html',
    ])
    expect([...document.querySelectorAll('#workspace-breadcrumbs [data-workspace-dir]')]
      .map(node => node.textContent)).toEqual(['Files', 'amass-viz'])

    document.querySelector('.workspace-folder-row [data-workspace-action="open-folder"]').click()

    expect([...document.querySelectorAll('.workspace-file-name')].map(node => node.textContent)).toEqual([
      'amass-viz',
      'targets.txt',
    ])

    document.querySelector('.workspace-folder-row .workspace-file-name').click()
    document.querySelectorAll('.workspace-folder-row .workspace-file-name')[1].click()

    expect([...document.querySelectorAll('.workspace-file-name')].map(node => node.textContent)).toEqual([
      '..',
      'app.js',
    ])
    expect([...document.querySelectorAll('#workspace-breadcrumbs [data-workspace-dir]')]
      .map(node => node.textContent)).toEqual(['Files', 'amass-viz', 'assets'])

    document.querySelector('#workspace-breadcrumbs [data-workspace-dir="amass-viz"]').click()

    expect([...document.querySelectorAll('.workspace-file-name')].map(node => node.textContent)).toEqual([
      '..',
      'assets',
      'amass.html',
    ])

    document.querySelector('#workspace-breadcrumbs [data-workspace-dir=""]').click()

    expect([...document.querySelectorAll('.workspace-file-name')].map(node => node.textContent)).toEqual([
      'amass-viz',
      'targets.txt',
    ])
  })

  it('renders explicit empty directories from the workspace payload', () => {
    const { renderWorkspaceFiles } = setupWorkspace()

    renderWorkspaceFiles({
      directories: [{ path: 'reports' }, { path: 'reports/empty' }],
      files: [{ path: 'targets.txt', size: 11 }],
      usage: { bytes_used: 11, file_count: 1 },
      limits: { quota_bytes: 4096, max_files: 10 },
    })

    expect([...document.querySelectorAll('.workspace-file-name')].map(node => node.textContent)).toEqual([
      'reports',
      'targets.txt',
    ])

    document.querySelector('.workspace-folder-row [data-workspace-action="open-folder"]').click()

    expect([...document.querySelectorAll('.workspace-file-name')].map(node => node.textContent)).toEqual([
      '..',
      'empty',
    ])
  })

  it('confirms folder deletion with file counts before deleting from the browser', async () => {
    const apiFetch = vi.fn((url, opts) => {
      if (String(url).startsWith('/workspace/files?path=reports') && opts?.method === 'DELETE') {
        return Promise.resolve(responseJson({
          deleted: { path: 'reports', kind: 'directory', file_count: 2 },
          workspace: {
            directories: [],
            files: [{ path: 'targets.txt', size: 11 }],
            usage: { bytes_used: 11, file_count: 1 },
            limits: { quota_bytes: 4096, max_files: 10 },
          },
        }))
      }
      return Promise.resolve(responseJson({}))
    })
    const { renderWorkspaceFiles, globals } = setupWorkspace(apiFetch)

    renderWorkspaceFiles({
      directories: [{ path: 'reports' }],
      files: [
        { path: 'reports/one.txt', size: 1 },
        { path: 'reports/nested/two.txt', size: 1 },
        { path: 'targets.txt', size: 11 },
      ],
      usage: { bytes_used: 13, file_count: 3 },
      limits: { quota_bytes: 4096, max_files: 10 },
    })

    document.querySelector('.workspace-folder-row [data-workspace-action="delete-folder"]').click()
    await flushWorkspacePromises()

    expect(globals.showConfirm).toHaveBeenCalledWith(expect.objectContaining({
      body: {
        text: 'Delete folder reports?',
        note: 'This will also delete 2 files in this folder.',
      },
    }))
    expect(apiFetch).toHaveBeenCalledWith('/workspace/files?path=reports', { method: 'DELETE' })
    expect(document.getElementById('workspace-message').textContent).toBe('Deleted folder reports')
  })

  it('shows an empty state when the workspace has no files', () => {
    const { renderWorkspaceFiles } = setupWorkspace()

    renderWorkspaceFiles({ files: [], usage: { bytes_used: 0, file_count: 0 }, limits: { max_files: 10 } })

    expect(document.querySelector('.workspace-empty').textContent)
      .toBe('No session files yet. Create a text file or save command output to use with file-enabled commands.')
  })

  it('saves new files relative to the currently selected folder', async () => {
    const apiFetch = vi.fn((url, opts) => {
      if (String(url) === '/workspace/files' && opts?.method === 'POST') {
        return Promise.resolve(responseJson({
          file: { path: 'reports/notes.txt', size: 14 },
          workspace: {
            directories: [{ path: 'reports' }],
            files: [{ path: 'reports/notes.txt', size: 14 }],
            usage: { bytes_used: 14, file_count: 1 },
            limits: { quota_bytes: 4096, max_files: 10 },
          },
        }))
      }
      return Promise.resolve(responseJson({}))
    })
    const { renderWorkspaceFiles } = setupWorkspace(apiFetch)

    renderWorkspaceFiles({
      directories: [{ path: 'reports' }],
      files: [],
      usage: { bytes_used: 0, file_count: 0 },
      limits: { quota_bytes: 4096, max_files: 10 },
    })

    document.querySelector('.workspace-folder-row .workspace-file-name').click()
    document.getElementById('workspace-new-btn').click()

    expect(document.getElementById('workspace-editor-overlay').classList.contains('u-hidden')).toBe(false)
    expect(document.getElementById('workspace-editor-overlay').classList.contains('open')).toBe(true)
    expect(document.getElementById('workspace-editor').classList.contains('u-hidden')).toBe(false)
    expect(document.getElementById('workspace-editor-title').textContent).toBe('New file')
    expect(document.getElementById('workspace-path-input').value).toBe('')

    document.getElementById('workspace-path-input').value = 'notes.txt'
    document.getElementById('workspace-text-input').value = 'folder note\n'
    document.getElementById('workspace-editor').dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }))
    await flushWorkspacePromises()

    expect(apiFetch).toHaveBeenCalledWith('/workspace/files', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ path: 'reports/notes.txt', text: 'folder note\n' }),
    }))
  })

  it('keeps the editor hidden until the user starts or closes an edit', () => {
    const { showWorkspaceEditor, hideWorkspaceEditor } = setupWorkspace()
    const overlay = document.getElementById('workspace-editor-overlay')
    const editor = document.getElementById('workspace-editor')

    expect(overlay.classList.contains('u-hidden')).toBe(true)
    expect(editor.classList.contains('u-hidden')).toBe(true)

    document.getElementById('workspace-new-btn').click()

    expect(overlay.classList.contains('u-hidden')).toBe(false)
    expect(overlay.classList.contains('open')).toBe(true)
    expect(editor.classList.contains('u-hidden')).toBe(false)

    hideWorkspaceEditor()

    expect(overlay.classList.contains('u-hidden')).toBe(true)
    expect(overlay.classList.contains('open')).toBe(false)
    expect(editor.classList.contains('u-hidden')).toBe(true)

    showWorkspaceEditor('targets.txt', 'darklab.sh\n')

    expect(overlay.classList.contains('u-hidden')).toBe(false)
    expect(editor.classList.contains('u-hidden')).toBe(false)
    expect(document.getElementById('workspace-editor-title').textContent).toBe('Editing targets.txt')
    expect(document.getElementById('workspace-path-input').value).toBe('targets.txt')
    expect(document.getElementById('workspace-text-input').value).toBe('darklab.sh\n')
  })

  it('opens the editor with a prefilled file name from terminal commands', async () => {
    const apiFetch = vi.fn((url) => {
      if (String(url).startsWith('/workspace/files/read')) {
        return Promise.resolve(responseJson({ path: 'response.html', text: '<html></html>\n' }))
      }
      return Promise.resolve(responseJson({}))
    })
    const { openWorkspaceEditorFromCommand, globals } = setupWorkspace(apiFetch)

    await openWorkspaceEditorFromCommand('add', 'targets.txt')

    expect(globals.showWorkspaceOverlay).not.toHaveBeenCalled()
    expect(globals.hideWorkspaceOverlay).toHaveBeenCalled()
    expect(document.getElementById('workspace-editor-overlay').classList.contains('u-hidden')).toBe(false)
    expect(document.getElementById('workspace-editor').classList.contains('u-hidden')).toBe(false)
    expect(document.getElementById('workspace-path-input').value).toBe('targets.txt')

    await openWorkspaceEditorFromCommand('edit', 'response.html')

    expect(globals.showWorkspaceOverlay).not.toHaveBeenCalled()
    expect(globals.hideWorkspaceOverlay).toHaveBeenCalledTimes(2)
    expect(apiFetch).toHaveBeenCalledWith('/workspace/files/read?path=response.html')
    expect(document.getElementById('workspace-editor-overlay').classList.contains('u-hidden')).toBe(false)
    expect(document.getElementById('workspace-editor').classList.contains('u-hidden')).toBe(false)
    expect(document.getElementById('workspace-path-input').readOnly).toBe(true)
    expect(document.getElementById('workspace-path-input').value).toBe('response.html')
    expect(document.getElementById('workspace-text-input').value).toBe('<html></html>\n')
  })

  it('shows file contents in a read-only viewer and keeps edit mode separate', async () => {
    const apiFetch = vi.fn((url) => {
      if (String(url).startsWith('/workspace/files/read')) {
        return Promise.resolve(responseJson({ path: 'response.html', text: '<html></html>' }))
      }
      return Promise.resolve(responseJson({}))
    })
    const { handleWorkspaceFileAction, showWorkspaceEditor, hideWorkspaceViewer, globals } = setupWorkspace(apiFetch)
    const viewerOverlay = document.getElementById('workspace-viewer-overlay')
    const viewer = document.getElementById('workspace-viewer')
    const viewerText = document.getElementById('workspace-viewer-text')
    viewer.scrollTop = 80
    viewerText.scrollTop = 120
    const editor = document.getElementById('workspace-editor')

    showWorkspaceEditor('response.html', '<html></html>')
    await handleWorkspaceFileAction('view', 'response.html')

    expect(apiFetch).toHaveBeenCalledWith('/workspace/files/read?path=response.html')
    expect(viewerOverlay.classList.contains('u-hidden')).toBe(false)
    expect(viewerOverlay.classList.contains('open')).toBe(true)
    expect(viewer.classList.contains('u-hidden')).toBe(false)
    expect(editor.classList.contains('u-hidden')).toBe(true)
    expect(document.getElementById('workspace-viewer-title').textContent).toBe('response.html')
    expect(viewerText.textContent).toContain('<html></html>')
    expect(viewer.scrollTop).toBe(0)
    expect(viewerText.scrollTop).toBe(0)

    hideWorkspaceViewer()

    expect(viewerOverlay.classList.contains('u-hidden')).toBe(true)
    expect(viewerOverlay.classList.contains('open')).toBe(false)
    expect(viewer.classList.contains('u-hidden')).toBe(true)

    apiFetch.mockImplementation(() => Promise.resolve(responseJson({
      error: 'file appears to be binary; download it instead',
    }, 415)))
    await handleWorkspaceFileAction('view', 'asset.db')

    expect(document.getElementById('workspace-message').classList.contains('u-hidden')).toBe(true)
    expect(globals.showToast).toHaveBeenCalledWith('file appears to be binary; download it instead', 'error')
  })

  it('opens the viewer with a loading preview while a file read is pending', async () => {
    let resolveRead
    let afterPaint
    const apiFetch = vi.fn((url) => {
      if (String(url).startsWith('/workspace/files/read')) {
        return new Promise(resolve => {
          resolveRead = () => resolve(responseJson({ path: 'big.jsonl', text: '{"id":1}\n{"id":2}\n' }))
        })
      }
      return Promise.resolve(responseJson({}))
    })
    const { handleWorkspaceFileAction } = setupWorkspace(apiFetch, {
      window: {
        ...window,
        requestAnimationFrame: vi.fn((fn) => {
          afterPaint = fn
          return 1
        }),
      },
    })

    const pending = handleWorkspaceFileAction('view', 'big.jsonl')
    await flushWorkspacePromises()

    expect(document.getElementById('workspace-viewer-overlay').classList.contains('u-hidden')).toBe(false)
    expect(document.getElementById('workspace-viewer-title').textContent).toBe('big.jsonl')
    expect(document.getElementById('workspace-viewer').dataset.format).toBe('loading')
    expect(document.getElementById('workspace-viewer-text').textContent).toContain('Loading preview...')

    afterPaint()
    await flushWorkspacePromises()
    resolveRead()
    await pending
    await flushWorkspacePromises()

    expect(document.getElementById('workspace-viewer').dataset.format).toBe('jsonl')
    expect(document.getElementById('workspace-viewer-text').textContent).toContain('"id": 2')
  })

  it('refreshes the currently viewed file when the files list is refreshed', async () => {
    const apiFetch = vi.fn((url) => {
      if (String(url) === '/workspace/files') {
        return Promise.resolve(responseJson({
          files: [{ path: 'targets.txt', size: 18 }],
          usage: { bytes_used: 18, file_count: 1 },
          limits: { quota_bytes: 1024, max_files: 10 },
        }))
      }
      if (String(url).startsWith('/workspace/files/read')) {
        return Promise.resolve(responseJson({ path: 'targets.txt', text: 'updated target\n' }))
      }
      return Promise.resolve(responseJson({}))
    })
    const { showWorkspaceViewer } = setupWorkspace(apiFetch)

    showWorkspaceViewer('targets.txt', 'old target\n')
    document.getElementById('workspace-refresh-btn').click()
    await flushWorkspacePromises()
    await flushWorkspacePromises()

    expect(apiFetch).toHaveBeenCalledWith('/workspace/files')
    expect(apiFetch).toHaveBeenCalledWith('/workspace/files/read?path=targets.txt')
    expect(document.getElementById('workspace-viewer-title').textContent).toBe('targets.txt')
    expect(document.getElementById('workspace-viewer-text').textContent).toContain('updated target')
    expect(document.getElementById('workspace-summary').textContent).toBe('1 / 10 files · 18 B / 1 KB')
  })

  it('refreshes the viewer directly and keeps following when scrolled to the bottom', async () => {
    const apiFetch = vi.fn((url) => {
      if (String(url).startsWith('/workspace/files/read')) {
        return Promise.resolve(responseJson({ path: 'targets.txt', text: 'line 1\nline 2\nline 3\n' }))
      }
      return Promise.resolve(responseJson({}))
    })
    const { showWorkspaceViewer } = setupWorkspace(apiFetch, {
      window: {
        ...window,
        requestAnimationFrame: vi.fn((fn) => {
          if (typeof fn === 'function') fn()
          return 1
        }),
      },
    })
    const viewerText = document.getElementById('workspace-viewer-text')
    Object.defineProperty(viewerText, 'clientHeight', { configurable: true, value: 100 })
    Object.defineProperty(viewerText, 'scrollHeight', { configurable: true, value: 500 })

    showWorkspaceViewer('targets.txt', 'old\n')
    viewerText.scrollTop = 400
    document.getElementById('workspace-viewer-refresh-btn').click()
    await flushWorkspacePromises()

    expect(apiFetch).toHaveBeenCalledWith('/workspace/files/read?path=targets.txt')
    expect(viewerText.textContent).toContain('line 3')
    expect(viewerText.scrollTop).toBe(400)
  })

  it('keeps auto-refresh off by default and refreshes only after opt-in', async () => {
    const intervals = []
    const spinnerTimers = []
    const apiFetch = vi.fn((url) => {
      if (String(url).startsWith('/workspace/files/read')) {
        return Promise.resolve(responseJson({ path: 'live.txt', text: 'fresh content\n' }))
      }
      return Promise.resolve(responseJson({}))
    })
    const clearInterval = vi.fn()
    const { showWorkspaceViewer } = setupWorkspace(apiFetch, {
      setInterval: vi.fn((fn, ms) => {
        intervals.push({ fn, ms })
        return intervals.length
      }),
      clearInterval,
      setTimeout: vi.fn((fn) => {
        spinnerTimers.push(fn)
        return spinnerTimers.length
      }),
    })

    showWorkspaceViewer('live.txt', 'stale content\n')
    expect(intervals).toHaveLength(0)
    expect(document.getElementById('workspace-viewer-auto-refresh-toggle').getAttribute('aria-pressed')).toBe('false')
    expect(document.getElementById('workspace-viewer-auto-refresh-label').textContent).toBe('Auto - off')

    document.getElementById('workspace-viewer-auto-refresh-toggle').click()
    expect(intervals).toHaveLength(1)
    expect(intervals[0].ms).toBe(1000)
    expect(document.getElementById('workspace-viewer-auto-refresh-toggle').getAttribute('aria-pressed')).toBe('true')
    expect(document.getElementById('workspace-viewer-auto-refresh-label').textContent).toBe('Auto - 5s')

    for (let i = 0; i < 5; i += 1) {
      await intervals[0].fn()
      await flushWorkspacePromises()
    }
    await flushWorkspacePromises()
    expect(document.getElementById('workspace-viewer-text').textContent).toContain('fresh content')
    expect(document.getElementById('workspace-viewer-auto-refresh-toggle').classList.contains('is-refreshing')).toBe(true)
    expect(document.getElementById('workspace-viewer-auto-refresh-label').textContent).toBe('Auto - 5s')

    document.getElementById('workspace-viewer-auto-refresh-toggle').click()
    expect(document.getElementById('workspace-viewer-auto-refresh-toggle').getAttribute('aria-pressed')).toBe('false')
    expect(document.getElementById('workspace-viewer-auto-refresh-label').textContent).toBe('Auto - off')
    expect(document.getElementById('workspace-viewer-auto-refresh-toggle').classList.contains('is-refreshing')).toBe(false)
    expect(clearInterval).toHaveBeenCalledWith(1)
  })

  it('disables auto-refresh for large files with an explanatory tooltip', () => {
    const { renderWorkspaceFiles, showWorkspaceViewer } = setupWorkspace()

    renderWorkspaceFiles({
      files: [{ path: 'large.jsonl', size: 1024 * 1024 + 1 }],
      usage: { bytes_used: 1024 * 1024 + 1, file_count: 1 },
      limits: { quota_bytes: 5 * 1024 * 1024, max_files: 10 },
    })
    showWorkspaceViewer('large.jsonl', '{"id":1}\n{"id":2}\n')

    const auto = document.getElementById('workspace-viewer-auto-refresh-toggle')
    expect(auto.getAttribute('aria-disabled')).toBe('true')
    expect(auto.getAttribute('aria-pressed')).toBe('false')
    expect(auto.title).toContain('disabled for files larger than 1 MB')

    auto.click()

    expect(auto.getAttribute('aria-pressed')).toBe('false')
  })

  it('runs edit download and delete actions from the viewer header for the viewed file', async () => {
    const apiFetch = vi.fn((url, opts) => {
      if (String(url).startsWith('/workspace/files/read')) {
        return Promise.resolve(responseJson({ path: 'amass-viz/amass.html', text: '<html></html>' }))
      }
      if (String(url).startsWith('/workspace/files/download')) {
        return Promise.resolve(new Response(new Blob(['html']), { status: 200 }))
      }
      if (String(url).startsWith('/workspace/files?path=amass-viz%2Famass.html') && opts?.method === 'DELETE') {
        return Promise.resolve(responseJson({
          workspace: {
            files: [],
            usage: { bytes_used: 0, file_count: 0 },
            limits: { quota_bytes: 1024, max_files: 10 },
          },
        }))
      }
      return Promise.resolve(responseJson({}))
    })
    const { showWorkspaceViewer, globals } = setupWorkspace(apiFetch)
    const createdUrls = []
    globals.URL.createObjectURL = vi.fn((blob) => {
      createdUrls.push(blob)
      return 'blob:workspace-test'
    })
    globals.URL.revokeObjectURL = vi.fn()
    const clicked = vi.fn()
    const originalCreateElement = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tagName, options) => {
      const element = originalCreateElement(tagName, options)
      if (String(tagName).toLowerCase() === 'a') element.click = clicked
      return element
    })

    showWorkspaceViewer('amass-viz/amass.html', '<html></html>')
    document.querySelector('[data-workspace-viewer-action="edit"]').click()
    await flushWorkspacePromises()

    expect(apiFetch).toHaveBeenCalledWith('/workspace/files/read?path=amass-viz%2Famass.html')
    expect(document.getElementById('workspace-editor').classList.contains('u-hidden')).toBe(false)
    expect(document.getElementById('workspace-path-input').value).toBe('amass-viz/amass.html')
    expect(document.getElementById('workspace-path-input').readOnly).toBe(true)

    showWorkspaceViewer('amass-viz/amass.html', '<html></html>')
    document.querySelector('[data-workspace-viewer-action="download"]').click()
    await flushWorkspacePromises()

    expect(apiFetch).toHaveBeenCalledWith('/workspace/files/download?path=amass-viz%2Famass.html')
    expect(clicked).toHaveBeenCalled()

    showWorkspaceViewer('amass-viz/amass.html', '<html></html>')
    document.querySelector('[data-workspace-viewer-action="delete"]').click()
    await flushWorkspacePromises()

    expect(globals.showConfirm).toHaveBeenCalled()
    expect(apiFetch).toHaveBeenCalledWith(
      '/workspace/files?path=amass-viz%2Famass.html',
      { method: 'DELETE' },
    )
  })

  it('formats obvious JSON files in the read-only viewer', async () => {
    const { showWorkspaceViewer } = setupWorkspace()

    showWorkspaceViewer('ffuf.json', '{"url":"https://ip.darklab.sh","status":200}')

    expect(document.getElementById('workspace-viewer').dataset.format).toBe('json')
    expect(document.getElementById('workspace-viewer-text').classList.contains('workspace-viewer-json')).toBe(true)
    expect(document.getElementById('workspace-viewer-text').textContent)
      .toContain('"url": "https://ip.darklab.sh"')
    expect(document.querySelector('[data-workspace-preview-mode="preview"]').getAttribute('aria-pressed')).toBe('true')
    expect(document.querySelector('[data-workspace-preview-mode="raw"]').getAttribute('aria-pressed')).toBe('false')

    document.querySelector('[data-workspace-preview-mode="raw"]').click()
    await flushWorkspacePromises()

    expect(document.getElementById('workspace-viewer').dataset.viewMode).toBe('raw')
    expect(document.querySelector('[data-workspace-preview-mode="preview"]').getAttribute('aria-pressed')).toBe('false')
    expect(document.querySelector('[data-workspace-preview-mode="raw"]').getAttribute('aria-pressed')).toBe('true')
    expect(document.getElementById('workspace-viewer-text').textContent)
      .toContain('{"url":"https://ip.darklab.sh","status":200}')
  })

  it('shows loading feedback while switching between preview and raw modes', async () => {
    let afterPaint
    const { showWorkspaceViewer } = setupWorkspace(vi.fn(), {
      window: {
        ...window,
        requestAnimationFrame: vi.fn((fn) => {
          afterPaint = fn
          return 1
        }),
      },
    })

    showWorkspaceViewer('ffuf.json', '{"url":"https://ip.darklab.sh","status":200}')
    document.querySelector('[data-workspace-preview-mode="raw"]').click()
    await flushWorkspacePromises()

    expect(document.getElementById('workspace-viewer-text').textContent).toContain('Loading raw view...')

    afterPaint()
    await flushWorkspacePromises()

    expect(document.getElementById('workspace-viewer').dataset.viewMode).toBe('raw')
    expect(document.getElementById('workspace-viewer-text').textContent)
      .toContain('{"url":"https://ip.darklab.sh","status":200}')
  })

  it('formats JSONL files record-by-record with raw text available', async () => {
    const { showWorkspaceViewer } = setupWorkspace()

    showWorkspaceViewer(
      'httpx-results.jsonl',
      '{"url":"https://one.darklab.sh","status_code":200}\n{"url":"https://two.darklab.sh","status_code":404}\n',
    )

    expect(document.getElementById('workspace-viewer').dataset.format).toBe('jsonl')
    expect(document.getElementById('workspace-viewer-text').classList.contains('workspace-viewer-json')).toBe(true)
    expect(document.getElementById('workspace-viewer-text').textContent)
      .toContain('"url": "https://one.darklab.sh"')
    expect(document.getElementById('workspace-viewer-text').textContent)
      .toContain('"status_code": 404')
    expect(document.querySelector('.workspace-preview-kind')?.textContent).toBe('jsonl preview')

    document.querySelector('[data-workspace-preview-mode="raw"]').click()
    await flushWorkspacePromises()

    expect(document.getElementById('workspace-viewer').dataset.viewMode).toBe('raw')
    expect(document.getElementById('workspace-viewer-text').textContent)
      .toContain('{"url":"https://one.darklab.sh","status_code":200}')

    showWorkspaceViewer(
      'httpx-results.json',
      '{"url":"https://one.darklab.sh","status_code":200}\n{"url":"https://two.darklab.sh","status_code":404}\n',
    )

    expect(document.getElementById('workspace-viewer').dataset.format).toBe('jsonl')
    expect(document.getElementById('workspace-viewer-text').textContent)
      .toContain('"url": "https://two.darklab.sh"')

    showWorkspaceViewer('broken.jsonl', '{"url":"ok"}\n{"url":')

    expect(document.getElementById('workspace-viewer').dataset.format).toBe('text')
    expect(document.getElementById('workspace-viewer-text').textContent)
      .toContain('Malformed JSONL; showing raw text.')
  })

  it('renders CSV and TSV files as preview tables with raw text available', async () => {
    const { showWorkspaceViewer } = setupWorkspace()

    showWorkspaceViewer('dnsrecon-results.csv', 'host,type,value\n"www.darklab.sh",A,127.0.0.1\n')

    expect(document.getElementById('workspace-viewer').dataset.format).toBe('csv')
    expect(document.querySelector('.workspace-preview-table th')?.textContent).toBe('host')
    expect([...document.querySelectorAll('.workspace-preview-table td')].map(cell => cell.textContent))
      .toContain('www.darklab.sh')

    document.querySelector('[data-workspace-preview-mode="raw"]').click()
    await flushWorkspacePromises()

    expect(document.getElementById('workspace-viewer').dataset.viewMode).toBe('raw')
    expect(document.getElementById('workspace-viewer-text').textContent).toContain('host,type,value')
  })

  it('formats XML and falls back cleanly for malformed XML', () => {
    const { showWorkspaceViewer } = setupWorkspace()

    showWorkspaceViewer('sslscan.xml', '<root><finding severity="high">tls</finding></root>')

    expect(document.getElementById('workspace-viewer').dataset.format).toBe('xml')
    expect(document.getElementById('workspace-viewer-text').textContent)
      .toContain('  <finding severity="high">tls</finding>')

    showWorkspaceViewer('broken.xml', '<root><finding></root>')

    expect(document.getElementById('workspace-viewer').dataset.format).toBe('text')
    expect(document.getElementById('workspace-viewer-text').textContent)
      .toContain('Malformed XML; showing raw text.')
  })

  it('renders HTTP responses with status, headers, and body sections', () => {
    const { showWorkspaceViewer } = setupWorkspace()

    showWorkspaceViewer(
      'response.txt',
      'HTTP/2 200 OK\r\ncontent-type: text/html\r\nserver: darklab\r\n\r\n<html>ok</html>',
    )

    expect(document.getElementById('workspace-viewer').dataset.format).toBe('http')
    expect(document.querySelector('.workspace-http-status')?.textContent).toBe('HTTP/2 200 OK')
    expect(document.querySelector('.workspace-http-headers')?.textContent).toContain('content-type')
    expect(document.getElementById('workspace-viewer-text').textContent).toContain('<html>ok</html>')
  })

  it('uses a bounded line-aware preview for large text files', () => {
    const searchTimers = []
    const { showWorkspaceViewer } = setupWorkspace(vi.fn(), {
      setTimeout: vi.fn((fn, ms) => {
        const id = searchTimers.length + 1
        searchTimers.push({ id, fn, ms, cleared: false, ran: false })
        return id
      }),
      clearTimeout: vi.fn((id) => {
        const timer = searchTimers.find(item => item.id === id)
        if (timer) timer.cleared = true
      }),
    })
    const runPendingSearch = () => {
      const timer = searchTimers.find(item => !item.cleared && !item.ran && item.ms === 600)
      expect(timer?.ms).toBe(600)
      timer.ran = true
      timer.fn()
    }
    const text = Array.from({ length: 10005 }, (_, index) => `line ${index + 1}`).join('\n')

    showWorkspaceViewer('large.txt', text)

    expect(document.getElementById('workspace-viewer').dataset.format).toBe('text')
    expect(document.querySelector('[data-workspace-preview-mode]')).toBeNull()
    expect(document.querySelectorAll('.workspace-line-row')).toHaveLength(10000)
    expect(document.querySelector('.workspace-line-preview').style.getPropertyValue('--workspace-line-number-width'))
      .toBe('6ch')
    expect(document.getElementById('workspace-viewer-text').textContent)
      .toContain('Showing first 10000 of 10005 lines')
    expect(document.getElementById('workspace-viewer-controls').contains(
      document.querySelector('.workspace-viewer-search'),
    )).toBe(true)
    expect(document.getElementById('workspace-viewer-text').contains(
      document.querySelector('.workspace-viewer-search'),
    )).toBe(false)

    const search = document.querySelector('.workspace-viewer-search input[type="text"]')
    search.value = 'de'
    search.dispatchEvent(new Event('input', { bubbles: true }))
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('type 3+ chars')
    expect(document.querySelectorAll('mark.search-hl')).toHaveLength(0)

    search.value = 'line 10000'
    search.dispatchEvent(new Event('input', { bubbles: true }))
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('searching...')
    runPendingSearch()
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('1 / 1')
    expect(document.querySelector('[data-line-number="10000"] mark.search-hl')?.textContent).toBe('line 10000')

    search.value = 'LINE 10000'
    search.dispatchEvent(new Event('input', { bubbles: true }))
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('searching...')
    runPendingSearch()
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('1 / 1')
    document.querySelector('.workspace-viewer-search [aria-label="Case sensitive"]').click()
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('no matches')
    document.querySelector('.workspace-viewer-search [aria-label="Regular expression"]').click()
    search.value = '^999[89]line 999[89]$'
    search.dispatchEvent(new Event('input', { bubbles: true }))
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('searching...')
    runPendingSearch()
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('no matches')
    search.value = '^line 999[89]$'
    search.dispatchEvent(new Event('input', { bubbles: true }))
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('searching...')
    runPendingSearch()
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('1 / 2')
    expect(document.querySelectorAll('mark.search-hl')).toHaveLength(1)
    expect(document.querySelector('[data-line-number="9998"] mark.search-hl')?.textContent).toBe('line 9998')
    search.focus()
    search.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('2 / 2')
    expect(document.querySelectorAll('mark.search-hl')).toHaveLength(1)
    expect(document.querySelector('[data-line-number="9999"] mark.search-hl')?.textContent).toBe('line 9999')
    expect(document.activeElement).toBe(search)
    document.querySelector('.workspace-viewer-search [aria-label="Previous match"]').click()
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('1 / 2')
    expect(document.querySelectorAll('mark.search-hl')).toHaveLength(1)
    expect(document.querySelector('[data-line-number="9998"] mark.search-hl')?.textContent).toBe('line 9998')

    search.value = ''
    search.dispatchEvent(new Event('input', { bubbles: true }))
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('')
    expect(document.querySelectorAll('mark.search-hl')).toHaveLength(0)

    expect(document.querySelector('[data-workspace-line-jump]')).toBeNull()
  })

  it('uses large-search mode for short files with very long lines', () => {
    const searchTimers = []
    const { showWorkspaceViewer } = setupWorkspace(vi.fn(), {
      setTimeout: vi.fn((fn, ms) => {
        const id = searchTimers.length + 1
        searchTimers.push({ id, fn, ms, cleared: false, ran: false })
        return id
      }),
      clearTimeout: vi.fn((id) => {
        const timer = searchTimers.find(item => item.id === id)
        if (timer) timer.cleared = true
      }),
    })
    const runPendingSearch = () => {
      const timer = searchTimers.find(item => !item.cleared && !item.ran && item.ms === 600)
      expect(timer?.ms).toBe(600)
      timer.ran = true
      timer.fn()
    }
    const largeLine = `${'x'.repeat(500000)}detected target`

    showWorkspaceViewer('large-raw.jsonl', largeLine, { size: 1024 * 1024 })

    expect(document.querySelectorAll('.workspace-line-row')).toHaveLength(1)
    const search = document.querySelector('.workspace-viewer-search input[type="text"]')
    search.value = 'de'
    search.dispatchEvent(new Event('input', { bubbles: true }))
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('type 3+ chars')

    search.value = 'detected'
    search.dispatchEvent(new Event('input', { bubbles: true }))
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('searching...')
    runPendingSearch()
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('1 / 1')
    expect(document.querySelectorAll('mark.search-hl')).toHaveLength(1)
    expect(document.querySelector('mark.search-hl')?.textContent).toBe('detected')
  })

  it('serves current workspace files as autocomplete hints after the file list is loaded', () => {
    const { renderWorkspaceFiles, getWorkspaceAutocompleteFileHints } = setupWorkspace()

    expect(getWorkspaceAutocompleteFileHints()).toEqual([])

    renderWorkspaceFiles({
      files: [{ path: 'targets.txt', size: 11 }, { path: 'ffuf.json', size: 2048 }],
      usage: { bytes_used: 2059, file_count: 2 },
      limits: { quota_bytes: 4096, max_files: 10 },
    })

    expect(getWorkspaceAutocompleteFileHints()).toEqual([
      { value: 'targets.txt', description: 'session file · 11 B' },
      { value: 'ffuf.json', description: 'session file · 2 KB' },
    ])
  })

  it('refreshes from the workspace route', async () => {
    const apiFetch = vi.fn(() => Promise.resolve(responseJson({
      files: [{ path: 'urls.txt', size: 18 }],
      usage: { bytes_used: 18, file_count: 1 },
      limits: { quota_bytes: 2048, max_files: 5 },
    })))
    const { refreshWorkspaceFiles } = setupWorkspace(apiFetch)

    await refreshWorkspaceFiles()

    expect(apiFetch).toHaveBeenCalledWith('/workspace/files')
    expect(document.querySelector('.workspace-file-name').textContent).toBe('urls.txt')

    apiFetch.mockClear()
    document.getElementById('workspace-refresh-btn').click()
    await flushWorkspacePromises()

    expect(apiFetch).toHaveBeenCalledWith('/workspace/files')
    expect(document.getElementById('workspace-refresh-btn').disabled).toBe(false)
    expect(document.getElementById('workspace-refresh-btn').getAttribute('aria-label')).toBe('Refresh files')
  })

  it('saves editor contents through the workspace route', async () => {
    const apiFetch = vi.fn(() => Promise.resolve(responseJson({
      file: { path: 'targets.txt', size: 11 },
      workspace: {
        files: [{ path: 'targets.txt', size: 11 }],
        usage: { bytes_used: 11, file_count: 1 },
        limits: { quota_bytes: 1024, max_files: 10 },
      },
    })))
    const { saveWorkspaceFile } = setupWorkspace(apiFetch)

    await saveWorkspaceFile('targets.txt', 'darklab.sh\n')

    expect(apiFetch).toHaveBeenCalledWith('/workspace/files', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ path: 'targets.txt', text: 'darklab.sh\n' }),
    }))
    expect(document.getElementById('workspace-message').textContent).toBe('Saved targets.txt')
  })

  it('creates folders through the workspace directory route', async () => {
    const apiFetch = vi.fn(() => Promise.resolve(responseJson({
      directory: { path: 'reports' },
      workspace: {
        directories: [{ path: 'reports' }],
        files: [],
        usage: { bytes_used: 0, file_count: 0 },
        limits: { quota_bytes: 1024, max_files: 10 },
      },
    })))
    const { createWorkspaceDirectory } = setupWorkspace(apiFetch)

    await createWorkspaceDirectory('reports')

    expect(apiFetch).toHaveBeenCalledWith('/workspace/directories', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ path: 'reports' }),
    }))
    expect(document.getElementById('workspace-message').textContent).toBe('Created folder reports')
    expect(document.querySelector('#workspace-breadcrumbs').textContent).toContain('reports')
    expect(document.querySelector('.workspace-empty').textContent).toBe('This folder is empty.')
  })

  it('opens an app-native folder prompt instead of the browser prompt', async () => {
    const apiFetch = vi.fn(() => Promise.resolve(responseJson({
      directory: { path: 'reports' },
      workspace: {
        directories: [{ path: 'reports' }],
        files: [],
        usage: { bytes_used: 0, file_count: 0 },
        limits: { quota_bytes: 1024, max_files: 10 },
      },
    })))
    const nativePrompt = vi.fn()
    const showConfirm = vi.fn(async (opts) => {
      const input = opts.content.querySelector('input')
      input.value = 'reports'
      expect(opts.defaultFocus).toBe(input)
      expect(opts.body.text).toBe('Create a session folder?')
      return (await opts.actions.find(action => action.id === 'create').onActivate()) ? 'create' : null
    })
    const originalPrompt = window.prompt
    window.prompt = nativePrompt
    const { promptWorkspaceFolderName } = setupWorkspace(apiFetch, { showConfirm })

    try {
      await promptWorkspaceFolderName()
    } finally {
      window.prompt = originalPrompt
    }

    expect(nativePrompt).not.toHaveBeenCalled()
    expect(showConfirm).toHaveBeenCalledTimes(1)
    const input = showConfirm.mock.calls[0][0].content.querySelector('input')
    expect(input.getAttribute('autocapitalize')).toBe('none')
    expect(input.getAttribute('autocorrect')).toBe('off')
    expect(input.getAttribute('inputmode')).toBe('text')
    expect(apiFetch).toHaveBeenCalledWith('/workspace/directories', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ path: 'reports' }),
    }))
  })

  it('keeps the folder prompt open when validation fails', async () => {
    const apiFetch = vi.fn()
    const showConfirm = vi.fn(async (opts) => {
      const input = opts.content.querySelector('input')
      input.value = '   '
      const result = await opts.actions.find(action => action.id === 'create').onActivate()
      expect(opts.content.querySelector('.workspace-folder-error').textContent).toBe('Enter a folder name.')
      return result ? 'create' : null
    })
    const { promptWorkspaceFolderName } = setupWorkspace(apiFetch, { showConfirm })
    apiFetch.mockClear()

    const result = await promptWorkspaceFolderName()

    expect(result).toBeNull()
    expect(apiFetch).not.toHaveBeenCalled()
  })
})
