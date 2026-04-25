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

function setupWorkspace(apiFetch = vi.fn()) {
  document.body.innerHTML = `
    <div id="workspace-summary"></div>
    <div id="workspace-message" class="u-hidden"></div>
    <div id="workspace-file-list"></div>
    <section id="workspace-viewer" class="u-hidden">
      <div id="workspace-viewer-title"></div>
      <pre id="workspace-viewer-text"></pre>
    </section>
    <form id="workspace-editor" class="u-hidden">
      <input id="workspace-path-input">
      <textarea id="workspace-text-input"></textarea>
      <button id="workspace-save-btn" type="submit"></button>
    </form>
    <button id="workspace-new-btn" type="button"></button>
    <button id="workspace-cancel-edit-btn" type="button"></button>
    <button id="workspace-close-viewer-btn" type="button"></button>
  `
  const globals = {
    document,
    window,
    URL,
    Blob,
    apiFetch,
    showWorkspaceOverlay: vi.fn(),
    hideWorkspaceOverlay: vi.fn(),
    hideWorkspaceEditor: undefined,
    _closeMajorOverlays: vi.fn(),
    blurVisibleComposerInputIfMobile: vi.fn(),
    refocusComposerAfterAction: vi.fn(),
    showConfirm: vi.fn(() => Promise.resolve('delete')),
    setTimeout: (fn) => {
      if (typeof fn === 'function') fn()
      return 0
    },
    workspaceSummary: document.getElementById('workspace-summary'),
    workspaceMessage: document.getElementById('workspace-message'),
    workspaceFileList: document.getElementById('workspace-file-list'),
    workspaceViewer: document.getElementById('workspace-viewer'),
    workspaceViewerTitle: document.getElementById('workspace-viewer-title'),
    workspaceViewerText: document.getElementById('workspace-viewer-text'),
    workspaceEditor: document.getElementById('workspace-editor'),
    workspacePathInput: document.getElementById('workspace-path-input'),
    workspaceTextInput: document.getElementById('workspace-text-input'),
    workspaceNewBtn: document.getElementById('workspace-new-btn'),
    workspaceCancelEditBtn: document.getElementById('workspace-cancel-edit-btn'),
    workspaceCloseViewerBtn: document.getElementById('workspace-close-viewer-btn'),
    workspaceSaveBtn: document.getElementById('workspace-save-btn'),
  }
  const names = Object.keys(globals)
  const values = Object.values(globals)
  const returnExpr = `
    return {
      _formatWorkspaceBytes,
      renderWorkspaceFiles,
      refreshWorkspaceFiles,
      saveWorkspaceFile,
      readWorkspaceFile,
      deleteWorkspaceFile,
      openWorkspace,
      setWorkspaceMessage,
      showWorkspaceEditor,
      hideWorkspaceEditor,
      showWorkspaceViewer,
      hideWorkspaceViewer,
      getWorkspaceAutocompleteFileHints,
      handleWorkspaceFileAction,
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

  it('shows an empty state when the workspace has no files', () => {
    const { renderWorkspaceFiles } = setupWorkspace()

    renderWorkspaceFiles({ files: [], usage: { bytes_used: 0, file_count: 0 }, limits: { max_files: 10 } })

    expect(document.querySelector('.workspace-empty').textContent).toContain('No workspace files yet')
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

  it('shows file contents in a read-only viewer and keeps edit mode separate', async () => {
    const apiFetch = vi.fn((url) => {
      if (String(url).startsWith('/workspace/files/read')) {
        return Promise.resolve(responseJson({ path: 'response.html', text: '<html></html>' }))
      }
      return Promise.resolve(responseJson({}))
    })
    const { handleWorkspaceFileAction, showWorkspaceEditor, hideWorkspaceViewer } = setupWorkspace(apiFetch)
    const viewer = document.getElementById('workspace-viewer')
    const editor = document.getElementById('workspace-editor')

    showWorkspaceEditor('response.html', '<html></html>')
    await handleWorkspaceFileAction('view', 'response.html')

    expect(apiFetch).toHaveBeenCalledWith('/workspace/files/read?path=response.html')
    expect(viewer.classList.contains('u-hidden')).toBe(false)
    expect(editor.classList.contains('u-hidden')).toBe(true)
    expect(document.getElementById('workspace-viewer-title').textContent).toBe('response.html')
    expect(document.getElementById('workspace-viewer-text').textContent).toBe('<html></html>')

    hideWorkspaceViewer()

    expect(viewer.classList.contains('u-hidden')).toBe(true)
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
      { value: 'targets.txt', description: 'workspace file · 11 B' },
      { value: 'ffuf.json', description: 'workspace file · 2 KB' },
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
})
