import { beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

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
    <section id="workspace-viewer" class="u-hidden">
      <div id="workspace-viewer-title"></div>
      <button type="button" data-workspace-viewer-action="edit"></button>
      <button type="button" data-workspace-viewer-action="download"></button>
      <button type="button" data-workspace-viewer-action="delete"></button>
      <pre id="workspace-viewer-text"></pre>
    </section>
    <form id="workspace-editor" class="u-hidden">
      <input id="workspace-path-input">
      <textarea id="workspace-text-input"></textarea>
      <button id="workspace-save-btn" type="submit"></button>
    </form>
    <button id="workspace-refresh-btn" type="button"></button>
    <button id="workspace-new-folder-btn" type="button"></button>
    <button id="workspace-new-btn" type="button"></button>
    <button id="workspace-cancel-edit-btn" type="button"></button>
    <button id="workspace-close-viewer-btn" type="button"></button>
  `
  const globals = {
    document,
    window,
    URL,
    Blob,
    APP_CONFIG: { workspace_enabled: true },
    apiFetch,
    showWorkspaceOverlay: vi.fn(),
    hideWorkspaceOverlay: vi.fn(),
    hideWorkspaceEditor: undefined,
    _closeMajorOverlays: vi.fn(),
    blurVisibleComposerInputIfMobile: vi.fn(),
    refocusComposerAfterAction: vi.fn(),
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
    workspaceSummary: document.getElementById('workspace-summary'),
    workspaceMessage: document.getElementById('workspace-message'),
    workspaceBreadcrumbs: document.getElementById('workspace-breadcrumbs'),
    workspaceFileList: document.getElementById('workspace-file-list'),
    workspaceViewer: document.getElementById('workspace-viewer'),
    workspaceViewerTitle: document.getElementById('workspace-viewer-title'),
    workspaceViewerText: document.getElementById('workspace-viewer-text'),
    workspaceEditor: document.getElementById('workspace-editor'),
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
      promptWorkspaceFolderName,
    };
  `
  const fns = new Function(...names, `${SRC}\n${returnExpr}`)(...values)
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

    expect(document.getElementById('workspace-editor').classList.contains('u-hidden')).toBe(false)
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
    const editor = document.getElementById('workspace-editor')

    expect(editor.classList.contains('u-hidden')).toBe(true)

    document.getElementById('workspace-new-btn').click()

    expect(editor.classList.contains('u-hidden')).toBe(false)

    hideWorkspaceEditor()

    expect(editor.classList.contains('u-hidden')).toBe(true)

    showWorkspaceEditor('targets.txt', 'darklab.sh\n')

    expect(editor.classList.contains('u-hidden')).toBe(false)
    expect(document.getElementById('workspace-path-input').value).toBe('targets.txt')
    expect(document.getElementById('workspace-text-input').value).toBe('darklab.sh\n')
  })

  it('opens the editor with a prefilled file name from terminal commands', async () => {
    const apiFetch = vi.fn(() => Promise.resolve(new Response(JSON.stringify({
      files: [],
      usage: { bytes_used: 0, file_count: 0 },
      limits: { max_files: 10, quota_bytes: 1024 },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })))
    const { openWorkspaceEditorFromCommand } = setupWorkspace(apiFetch)

    await openWorkspaceEditorFromCommand('add', 'targets.txt')

    expect(document.getElementById('workspace-editor').classList.contains('u-hidden')).toBe(false)
    expect(document.getElementById('workspace-path-input').value).toBe('targets.txt')
  })

  it('shows file contents in a read-only viewer and keeps edit mode separate', async () => {
    const apiFetch = vi.fn((url) => {
      if (String(url).startsWith('/workspace/files/read')) {
        return Promise.resolve(responseJson({ path: 'response.html', text: '<html></html>' }))
      }
      return Promise.resolve(responseJson({}))
    })
    const { handleWorkspaceFileAction, showWorkspaceEditor, hideWorkspaceViewer, globals } = setupWorkspace(apiFetch)
    const viewer = document.getElementById('workspace-viewer')
    const viewerText = document.getElementById('workspace-viewer-text')
    viewer.scrollIntoView = vi.fn()
    viewer.scrollTop = 80
    viewerText.scrollTop = 120
    const editor = document.getElementById('workspace-editor')

    showWorkspaceEditor('response.html', '<html></html>')
    await handleWorkspaceFileAction('view', 'response.html')

    expect(apiFetch).toHaveBeenCalledWith('/workspace/files/read?path=response.html')
    expect(viewer.classList.contains('u-hidden')).toBe(false)
    expect(viewer.scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' })
    expect(editor.classList.contains('u-hidden')).toBe(true)
    expect(document.getElementById('workspace-viewer-title').textContent).toBe('response.html')
    expect(viewerText.textContent).toBe('<html></html>')
    expect(viewer.scrollTop).toBe(0)
    expect(viewerText.scrollTop).toBe(0)

    hideWorkspaceViewer()

    expect(viewer.classList.contains('u-hidden')).toBe(true)

    apiFetch.mockImplementation(() => Promise.resolve(responseJson({
      error: 'file appears to be binary; download it instead',
    }, 415)))
    await handleWorkspaceFileAction('view', 'asset.db')

    expect(document.getElementById('workspace-message').classList.contains('u-hidden')).toBe(true)
    expect(globals.showToast).toHaveBeenCalledWith('file appears to be binary; download it instead', 'error')
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
    expect(document.getElementById('workspace-viewer-text').textContent).toBe('updated target\n')
    expect(document.getElementById('workspace-summary').textContent).toBe('1 / 10 files · 18 B / 1 KB')
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

  it('formats obvious JSON files in the read-only viewer', () => {
    const { showWorkspaceViewer } = setupWorkspace()

    showWorkspaceViewer('ffuf.json', '{"url":"https://ip.darklab.sh","status":200}')

    expect(document.getElementById('workspace-viewer').dataset.format).toBe('json')
    expect(document.getElementById('workspace-viewer-text').classList.contains('workspace-viewer-json')).toBe(true)
    expect(document.getElementById('workspace-viewer-text').textContent).toBe(
      '{\n  "url": "https://ip.darklab.sh",\n  "status": 200\n}',
    )
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
