// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushWorkspacePromises, responseJson, setupWorkspace } from './helpers/workspace_harness.js'

describe('workspace UI helpers', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('renders workspace files with usage summary, row actions, and desktop file details', async () => {
    const workspacePayload = {
      files: [{
        path: 'targets.txt',
        size: 11,
        mtime: '2026-01-01T00:00:00Z',
        artifact_count: 1,
        artifact_run_count: 1,
        project_names: ['Signal Case'],
        labels: [{ label: 'important' }],
        note: { body: 'Retest after scanner update.' },
      }],
      usage: { bytes_used: 11, file_count: 1 },
      limits: { quota_bytes: 1024, max_files: 10 },
    }
    const apiFetch = vi.fn(url => Promise.resolve(responseJson(
      String(url) === '/workspace/files'
        ? workspacePayload
        : {
            path: 'targets.txt',
            text: [
              'darklab.sh',
              'ip.darklab.sh',
              ...Array.from({ length: 90 }, (_, index) => `target-${index + 1}.darklab.sh`),
            ].join('\n'),
            size: 26,
          },
    )))
    const { renderWorkspaceFiles } = setupWorkspace(apiFetch, { workspaceViewportWidth: 1200 })

    renderWorkspaceFiles(workspacePayload)

    expect(document.getElementById('workspace-scope-badge').textContent).toBe('Personal')
    expect(document.getElementById('workspace-file-usage').textContent).toBe('1 / 10')
    expect(document.getElementById('workspace-storage-usage').textContent).toBe('11 B / 1 KB')
    expect(document.getElementById('workspace-file-usage-fill').style.width).toBe('10%')
    expect(document.getElementById('workspace-summary').getAttribute('aria-label'))
      .toBe('Personal, 1 / 10 files, 11 B / 1 KB')
    expect(document.querySelector('.workspace-file-name').textContent).toBe('targets.txt')
    expect(document.querySelector('.workspace-context-copy').textContent)
      .toContain('1 artifact · 1 run · Signal Case')
    expect(document.querySelector('.workspace-modified-cell time').title)
      .toBe('2026-01-01T00:00:00Z')
    expect([...document.querySelectorAll('.workspace-metadata-chip')].map(node => node.textContent))
      .toEqual(['important', 'note'])
    expect([...document.querySelectorAll('[data-workspace-action]')].map(btn => btn.textContent)).toEqual([
      'targets.txt',
      'Edit',
      'Move',
      'Download',
      'Delete',
    ])

    document.querySelector('.workspace-context-cell').click()
    await flushWorkspacePromises()

    expect(document.querySelector('.workspace-file-row').classList.contains('is-selected')).toBe(true)
    expect(document.querySelector('.workspace-file-row').getAttribute('aria-selected')).toBe('true')
    expect(document.getElementById('workspace-inspector-empty').classList.contains('u-hidden')).toBe(true)
    expect(document.getElementById('workspace-inspector-content').textContent).toContain('targets.txt')
    expect(document.getElementById('workspace-inspector-content').textContent).toContain('Linked runs1')
    expect(document.getElementById('workspace-inspector-content').textContent).toContain('Signal Case')
    expect(document.getElementById('workspace-inspector-content').textContent).toContain('important')
    expect(document.getElementById('workspace-inspector-content').textContent)
      .toContain('Retest after scanner update.')
    expect(document.querySelector('.workspace-inspector-preview').textContent)
      .toContain('ip.darklab.sh')
    expect(document.querySelector('.workspace-inspector-preview-section').textContent)
      .toContain('Preview truncated')
  })

  it('filters file context, sorts files within folders, and supports the action menu keyboard', () => {
    const { renderWorkspaceFiles } = setupWorkspace()

    renderWorkspaceFiles({
      directories: [{ path: 'reports' }],
      files: [
        { path: 'alpha.txt', size: 10, mtime: '2026-01-01T00:00:00Z' },
        {
          path: 'zeta.json',
          size: 50,
          mtime: '2026-02-01T00:00:00Z',
          artifact_count: 1,
          project_names: ['Signal Case'],
        },
      ],
      usage: { bytes_used: 60, file_count: 2 },
      limits: { quota_bytes: 1024, max_files: 10 },
    })

    const visibleNames = () => [...document.querySelectorAll('.workspace-file-name')]
      .map(node => node.textContent)
    expect(visibleNames()).toEqual(['reports', 'alpha.txt', 'zeta.json'])

    const sort = document.getElementById('workspace-sort-select')
    sort.value = 'size'
    sort.dispatchEvent(new Event('change', { bubbles: true }))
    expect(visibleNames()).toEqual(['reports', 'zeta.json', 'alpha.txt'])

    const search = document.getElementById('workspace-search-input')
    search.value = 'signal case'
    search.dispatchEvent(new Event('input', { bubbles: true }))
    expect(visibleNames()).toEqual(['zeta.json'])
    expect(document.getElementById('workspace-result-summary').textContent).toBe('1 of 3 items')

    const trigger = document.querySelector('.workspace-action-menu-trigger')
    trigger.click()
    expect(trigger.getAttribute('aria-expanded')).toBe('true')
    expect(document.activeElement.textContent).toBe('Edit')

    const menu = document.querySelector('.workspace-action-menu')
    menu.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }))
    expect(document.activeElement.textContent).toBe('Move')
    menu.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(trigger.getAttribute('aria-expanded')).toBe('false')
    expect(document.activeElement).toBe(trigger)
  })

  it('renders team viewer and archived Files as read-only while keeping preview and download available', async () => {
    const apiFetch = vi.fn(() => Promise.resolve(responseJson({})))
    const { renderWorkspaceFiles, handleWorkspaceFileAction, globals } = setupWorkspace(apiFetch)

    renderWorkspaceFiles({
      owner: {
        scope: 'team',
        team_id: 'team_readonly',
        label: 'Team Alpha',
        read_only: true,
        read_only_reason: "Team viewers can view Files but can't change them.",
      },
      directories: [{ path: 'reports' }],
      files: [{ path: 'targets.txt', size: 11 }],
      usage: { bytes_used: 11, file_count: 1 },
      limits: { quota_bytes: 1024, max_files: 10 },
    })

    expect(document.getElementById('workspace-scope-badge').textContent).toBe('Team Alpha')
    expect(document.getElementById('workspace-summary').getAttribute('aria-label'))
      .toBe('Team Alpha, 1 / 10 files, 11 B / 1 KB, read-only')
    expect(document.getElementById('workspace-read-only-status').classList.contains('u-hidden')).toBe(false)
    expect(document.getElementById('workspace-read-only-status').title)
      .toBe("Team viewers can view Files but can't change them.")
    expect(document.getElementById('workspace-new-btn').disabled).toBe(true)
    expect(document.getElementById('workspace-new-folder-btn').disabled).toBe(true)
    expect(document.querySelector('.workspace-folder-row').draggable).toBe(false)
    expect(document.querySelector('.workspace-file-row[data-path="targets.txt"]').draggable).toBe(false)
    expect(document.querySelector('[data-workspace-action="view"]').disabled).toBe(false)
    expect(document.querySelector('[data-workspace-action="download"]').disabled).toBe(false)
    expect(document.querySelector('[data-workspace-action="edit"]').disabled).toBe(true)
    expect(document.querySelector('[data-workspace-action="move"]').disabled).toBe(true)
    expect(document.querySelector('[data-workspace-action="delete"]').disabled).toBe(true)

    await handleWorkspaceFileAction('delete', 'targets.txt')
    await flushWorkspacePromises()

    expect(globals.showConfirm).not.toHaveBeenCalled()
    expect(apiFetch).not.toHaveBeenCalledWith('/workspace/files?path=targets.txt', expect.anything())
    expect(globals.showToast).toHaveBeenCalledWith("Team viewers can view Files but can't change them.", 'error')
  })

  it('closes stale editors and reloads Files when the active scope changes', async () => {
    const apiFetch = vi.fn(() => Promise.resolve(responseJson({
      owner: {
        scope: 'team',
        team_id: 'team_reload',
        label: 'Team Reload',
        read_only: false,
      },
      directories: [],
      files: [{ path: 'team.txt', size: 9 }],
      usage: { bytes_used: 9, file_count: 1 },
      limits: { quota_bytes: 1024, max_files: 10 },
    })))
    const { globals, showWorkspaceEditor } = setupWorkspace(apiFetch)
    const scopeHandler = globals.window.addEventListener.mock.calls
      .find(([eventName]) => eventName === 'app:scope-changed')?.[1]

    showWorkspaceEditor('personal.txt', 'personal\n')
    expect(document.getElementById('workspace-editor-overlay').classList.contains('u-hidden')).toBe(false)

    scopeHandler()
    await flushWorkspacePromises()

    expect(document.getElementById('workspace-editor-overlay').classList.contains('u-hidden')).toBe(true)
    expect(apiFetch).toHaveBeenCalledWith('/workspace/files', { cache: 'no-store' })
    expect(document.getElementById('workspace-summary').getAttribute('aria-label'))
      .toBe('Team Reload, 1 / 10 files, 9 B / 1 KB')
    expect(document.querySelector('.workspace-file-name').textContent).toBe('team.txt')
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
      .toBe('amass-viz')
    expect([...document.querySelectorAll('.workspace-folder-row [data-workspace-action]')].map(btn => btn.textContent))
      .toEqual(['amass-viz', 'Move', 'Delete'])
    expect(document.querySelector('.workspace-folder-row').hasAttribute('tabindex')).toBe(false)

    document.querySelector('.workspace-folder-row .workspace-context-cell').click()

    expect([...document.querySelectorAll('.workspace-file-name')].map(node => node.textContent)).toEqual([
      '..',
      'assets',
      'amass.html',
    ])
    const parentRow = document.querySelector('.workspace-parent-row')
    expect(parentRow.dataset.path).toBe('')
    expect(parentRow.dataset.workspaceDropTarget).toBe('folder')
    expect(parentRow.draggable).toBe(false)
    expect(parentRow.querySelector('.workspace-file-name').getAttribute('aria-label'))
      .toBe('Open parent folder Files')
    expect(parentRow.querySelector('.workspace-file-details').textContent)
      .toBe('Parent folder · Files')
    expect([...document.querySelectorAll('#workspace-breadcrumbs [data-workspace-dir]')]
      .map(node => node.textContent)).toEqual(['Files', 'amass-viz'])

    document.getElementById('workspace-up-btn').click()

    expect([...document.querySelectorAll('.workspace-file-name')].map(node => node.textContent)).toEqual([
      'amass-viz',
      'targets.txt',
    ])

    document.querySelector('.workspace-folder-row .workspace-file-name').click()
    document.querySelector('.workspace-folder-row:not(.workspace-parent-row) .workspace-file-name').click()

    expect([...document.querySelectorAll('.workspace-file-name')].map(node => node.textContent)).toEqual([
      '..',
      'app.js',
    ])
    expect(document.querySelector('.workspace-parent-row').dataset.path).toBe('amass-viz')
    expect([...document.querySelectorAll('#workspace-breadcrumbs [data-workspace-dir]')]
      .map(node => node.textContent)).toEqual(['Files', 'amass-viz', 'assets'])

    document.querySelector('.workspace-parent-row .workspace-context-cell').click()

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

  it('renders explicit empty directories from the workspace payload', async () => {
    const apiFetch = vi.fn(() => responseJson({
      directories: [{ path: 'reports' }, { path: 'reports/empty' }],
      files: [{ path: 'targets.txt', size: 11 }],
      usage: { bytes_used: 11, file_count: 1 },
      limits: { quota_bytes: 4096, max_files: 10 },
    }))
    const { getWorkspaceAutocompleteDirectoryHints, renderWorkspaceFiles } = setupWorkspace(apiFetch)

    await flushWorkspacePromises()

    expect(apiFetch).toHaveBeenCalledWith('/workspace/files', { cache: 'no-store' })
    expect(getWorkspaceAutocompleteDirectoryHints().map(item => item.value)).toEqual(['reports', 'reports/empty'])

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
    expect(document.getElementById('workspace-up-btn').disabled).toBe(false)
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
    expect(globals.showToast).toHaveBeenCalledWith('Deleted folder reports', 'success')
  })

  it('moves files from the row action through the app-native prompt', async () => {
    const apiFetch = vi.fn((url, opts) => {
      if (String(url) === '/workspace/files/move' && opts?.method === 'POST') {
        return Promise.resolve(responseJson({
          moved: {
            source: 'targets.txt',
            destination: 'reports/targets.txt',
            kind: 'file',
            file_count: 1,
          },
          workspace: {
            directories: [{ path: 'reports' }],
            files: [{ path: 'reports/targets.txt', size: 11 }],
            usage: { bytes_used: 11, file_count: 1 },
            limits: { quota_bytes: 4096, max_files: 10 },
          },
        }))
      }
      return Promise.resolve(responseJson({}))
    })
    const showConfirm = vi.fn(async (opts) => {
      const input = opts.content.querySelector('input')
      input.value = 'reports'
      expect(opts.defaultFocus).toBe(input)
      expect(opts.body.text).toBe('Move file targets.txt?')
      return (await opts.actions.find(action => action.id === 'move').onActivate()) ? 'move' : null
    })
    const { renderWorkspaceFiles, globals } = setupWorkspace(apiFetch, { showConfirm })

    renderWorkspaceFiles({
      directories: [{ path: 'reports' }],
      files: [{ path: 'targets.txt', size: 11 }],
      usage: { bytes_used: 11, file_count: 1 },
      limits: { quota_bytes: 4096, max_files: 10 },
    })

    document.querySelector('[data-workspace-action="move"]').click()
    await flushWorkspacePromises()

    expect(apiFetch).toHaveBeenCalledWith('/workspace/files/move', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ source: 'targets.txt', destination: 'reports' }),
    }))
    expect(globals.showToast).toHaveBeenCalledWith('Moved targets.txt to reports/targets.txt', 'success')
    expect(document.querySelector('.workspace-file-name').textContent).toBe('reports')
  })

  it('moves a dragged file into a folder and back through the parent row after confirmation', async () => {
    const apiFetch = vi.fn((url, opts) => {
      if (String(url) === '/workspace/files/move' && opts?.method === 'POST') {
        const request = JSON.parse(opts.body)
        const movingToParent = request.source === 'reports/targets.txt'
        return Promise.resolve(responseJson({
          moved: {
            source: request.source,
            destination: movingToParent ? 'targets.txt' : 'reports/targets.txt',
            kind: 'file',
            file_count: 1,
          },
          workspace: {
            directories: [{ path: 'reports' }],
            files: [{ path: movingToParent ? 'targets.txt' : 'reports/targets.txt', size: 11 }],
            usage: { bytes_used: 11, file_count: 1 },
            limits: { quota_bytes: 4096, max_files: 10 },
          },
        }))
      }
      return Promise.resolve(responseJson({}))
    })
    const showConfirm = vi.fn(() => Promise.resolve('move'))
    const { renderWorkspaceFiles } = setupWorkspace(apiFetch, { showConfirm })

    renderWorkspaceFiles({
      directories: [{ path: 'reports' }],
      files: [{ path: 'targets.txt', size: 11 }],
      usage: { bytes_used: 11, file_count: 1 },
      limits: { quota_bytes: 4096, max_files: 10 },
    })

    const source = document.querySelector('.workspace-file-row[data-path="targets.txt"]')
    const destination = document.querySelector('.workspace-folder-row[data-path="reports"]')
    const dataTransfer = {
      effectAllowed: '',
      dropEffect: '',
      setData: vi.fn(),
      getData: vi.fn(() => 'targets.txt'),
    }
    const dragTo = (dragSource, dragDestination) => {
      for (const [node, type] of [
        [dragSource, 'dragstart'],
        [dragDestination, 'dragover'],
        [dragDestination, 'drop'],
      ]) {
        const event = new Event(type, { bubbles: true, cancelable: true })
        Object.defineProperty(event, 'dataTransfer', { configurable: true, value: dataTransfer })
        node.dispatchEvent(event)
      }
    }
    dragTo(source, destination)
    await flushWorkspacePromises()

    expect(showConfirm).toHaveBeenNthCalledWith(1, expect.objectContaining({
      body: {
        text: 'Move file targets.txt?',
        note: 'Destination folder: reports',
      },
    }))
    expect(apiFetch).toHaveBeenCalledWith('/workspace/files/move', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ source: 'targets.txt', destination: 'reports' }),
    }))

    document.querySelector('.workspace-folder-row[data-path="reports"] .workspace-file-name').click()
    const nestedSource = document.querySelector('.workspace-file-row[data-path="reports/targets.txt"]')
    const parentDestination = document.querySelector('.workspace-parent-row[data-path=""]')
    dragTo(nestedSource, parentDestination)
    await flushWorkspacePromises()

    expect(showConfirm).toHaveBeenNthCalledWith(2, expect.objectContaining({
      body: {
        text: 'Move file reports/targets.txt?',
        note: 'Destination folder: Files',
      },
    }))
    expect(apiFetch).toHaveBeenCalledWith('/workspace/files/move', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ source: 'reports/targets.txt', destination: '' }),
    }))
  })

  it('shows an empty state when the workspace has no files', () => {
    const { renderWorkspaceFiles } = setupWorkspace()

    renderWorkspaceFiles({ files: [], usage: { bytes_used: 0, file_count: 0 }, limits: { max_files: 10 } })

    expect(document.querySelector('.workspace-empty').textContent)
      .toBe('No Files yet. Create a text file or save command output to use with file-enabled commands.')
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

  it('prefills and saves workspace file labels and notes from the editor', async () => {
    const apiFetch = vi.fn((url, opts = {}) => {
      if (String(url) === '/workspace/files/read?path=targets.txt') {
        return Promise.resolve(responseJson({
          path: 'targets.txt',
          text: 'darklab.sh\n',
          labels: [{ label: 'scope' }],
          note: { body: 'seed note' },
        }))
      }
      if (String(url) === '/workspace/files' && opts.method === 'POST') {
        return Promise.resolve(responseJson({
          file: { path: 'targets.txt', size: 14 },
          workspace: {
            files: [{ path: 'targets.txt', size: 14 }],
            usage: { bytes_used: 14, file_count: 1 },
            limits: { quota_bytes: 4096, max_files: 10 },
          },
        }))
      }
      if (String(url) === '/entities/workspace_file/targets.txt/labels' && !opts.method) {
        return Promise.resolve(responseJson({ labels: [{ label: 'scope' }] }))
      }
      if (String(url) === '/entities/workspace_file/targets.txt/labels' && opts.method === 'DELETE') {
        return Promise.resolve(responseJson({ deleted: true }))
      }
      if (String(url) === '/entities/workspace_file/targets.txt/labels' && opts.method === 'POST') {
        return Promise.resolve(responseJson({ label: { label: 'review' } }, 201))
      }
      if (String(url) === '/entities/workspace_file/targets.txt/note' && opts.method === 'PUT') {
        return Promise.resolve(responseJson({ note: { body: 'updated note' } }))
      }
      if (String(url) === '/workspace/files' && !opts.method) {
        return Promise.resolve(responseJson({
          files: [{
            path: 'targets.txt',
            size: 14,
            labels: [{ label: 'review' }],
            note: { body: 'updated note' },
          }],
          usage: { bytes_used: 14, file_count: 1 },
          limits: { quota_bytes: 4096, max_files: 10 },
        }))
      }
      return Promise.resolve(responseJson({}))
    })
    const { openWorkspaceEditorFromCommand } = setupWorkspace(apiFetch)

    await openWorkspaceEditorFromCommand('edit', 'targets.txt')

    expect(document.getElementById('workspace-labels-input').value).toBe('scope')
    expect(document.getElementById('workspace-notes-input').value).toBe('seed note')

    document.getElementById('workspace-labels-input').value = 'review'
    document.getElementById('workspace-notes-input').value = 'updated note'
    document.getElementById('workspace-editor').dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }))
    for (let i = 0; i < 4; i += 1) await flushWorkspacePromises()

    expect(apiFetch).toHaveBeenCalledWith('/workspace/files', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ path: 'targets.txt', text: 'darklab.sh\n' }),
    }))
    expect(apiFetch).toHaveBeenCalledWith('/entities/workspace_file/targets.txt/labels', expect.objectContaining({
      method: 'DELETE',
      body: JSON.stringify({ label: 'scope' }),
    }))
    expect(apiFetch).toHaveBeenCalledWith('/entities/workspace_file/targets.txt/labels', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ label: 'review' }),
    }))
    expect(apiFetch).toHaveBeenCalledWith('/entities/workspace_file/targets.txt/note', expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({ body: 'updated note' }),
    }))
    expect([...document.querySelectorAll('.workspace-metadata-chip')].map(node => node.textContent))
      .toEqual(['review', 'note'])
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

  it('shows loading feedback before opening the editor for large files', async () => {
    let resolveRead
    let afterPaint
    const apiFetch = vi.fn((url) => {
      if (String(url).startsWith('/workspace/files/read')) {
        return new Promise(resolve => {
          resolveRead = () => resolve(responseJson({ path: 'large.txt', text: 'large file contents\n' }))
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

    const pending = handleWorkspaceFileAction('edit', 'large.txt')
    await flushWorkspacePromises()

    expect(document.getElementById('workspace-viewer-overlay').classList.contains('u-hidden')).toBe(false)
    expect(document.getElementById('workspace-viewer-title').textContent).toBe('large.txt')
    expect(document.getElementById('workspace-viewer').dataset.format).toBe('loading')
    expect(document.getElementById('workspace-viewer-text').textContent).toContain('Loading file for edit...')
    expect(document.getElementById('workspace-editor').classList.contains('u-hidden')).toBe(true)
    expect(apiFetch.mock.calls.some(([url]) => String(url).startsWith('/workspace/files/read'))).toBe(false)

    afterPaint()
    await flushWorkspacePromises()
    resolveRead()
    await pending
    await flushWorkspacePromises()

    expect(apiFetch).toHaveBeenCalledWith('/workspace/files/read?path=large.txt')
    expect(document.getElementById('workspace-viewer-overlay').classList.contains('u-hidden')).toBe(true)
    expect(document.getElementById('workspace-editor-overlay').classList.contains('u-hidden')).toBe(false)
    expect(document.getElementById('workspace-editor').classList.contains('u-hidden')).toBe(false)
    expect(document.getElementById('workspace-path-input').value).toBe('large.txt')
    expect(document.getElementById('workspace-path-input').readOnly).toBe(true)
    expect(document.getElementById('workspace-text-input').value).toBe('large file contents\n')
  })

  it('toasts and does not open the viewer for files that exceed the read limit', async () => {
    const apiFetch = vi.fn(() => Promise.resolve(responseJson({})))
    const { renderWorkspaceFiles, handleWorkspaceFileAction, globals } = setupWorkspace(apiFetch)

    renderWorkspaceFiles({
      files: [{ path: 'too-large.txt', size: 2048 }],
      usage: { bytes_used: 2048, file_count: 1 },
      limits: { quota_bytes: 4096, max_file_bytes: 1024, max_files: 10 },
    })

    await handleWorkspaceFileAction('view', 'too-large.txt')
    await flushWorkspacePromises()

    expect(apiFetch.mock.calls.some(([url]) => String(url).startsWith('/workspace/files/read'))).toBe(false)
    expect(document.getElementById('workspace-viewer-overlay').classList.contains('u-hidden')).toBe(true)
    expect(document.getElementById('workspace-viewer').classList.contains('u-hidden')).toBe(true)
    expect(globals.showToast).toHaveBeenCalledWith('file exceeds workspace max file size', 'error')
  })

  it('toasts and does not open the editor for oversized edit actions', async () => {
    const apiFetch = vi.fn(() => Promise.resolve(responseJson({})))
    const { renderWorkspaceFiles, handleWorkspaceFileAction, globals } = setupWorkspace(apiFetch)

    renderWorkspaceFiles({
      files: [{ path: 'huge.log', size: 4096 }],
      usage: { bytes_used: 4096, file_count: 1 },
      limits: { quota_bytes: 8192, max_file_bytes: 1024, max_files: 10 },
    })

    await handleWorkspaceFileAction('edit', 'huge.log')
    await flushWorkspacePromises()

    expect(apiFetch.mock.calls.some(([url]) => String(url).startsWith('/workspace/files/read'))).toBe(false)
    expect(document.getElementById('workspace-viewer-overlay').classList.contains('u-hidden')).toBe(true)
    expect(document.getElementById('workspace-editor-overlay').classList.contains('u-hidden')).toBe(true)
    expect(document.getElementById('workspace-editor').classList.contains('u-hidden')).toBe(true)
    expect(globals.showToast).toHaveBeenCalledWith('file exceeds workspace max file size', 'error')
  })

  it('closes the loading viewer when a read is rejected after opening', async () => {
    const apiFetch = vi.fn((url) => {
      if (String(url).startsWith('/workspace/files/read')) {
        return Promise.resolve(responseJson({ error: 'file exceeds workspace max file size' }, 413))
      }
      return Promise.resolve(responseJson({}))
    })
    const { handleWorkspaceFileAction, globals } = setupWorkspace(apiFetch)

    await handleWorkspaceFileAction('view', 'unknown-large.txt')
    await flushWorkspacePromises()

    expect(document.getElementById('workspace-viewer-overlay').classList.contains('u-hidden')).toBe(true)
    expect(document.getElementById('workspace-viewer').classList.contains('u-hidden')).toBe(true)
    expect(globals.showToast).toHaveBeenCalledWith('file exceeds workspace max file size', 'error')
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

    expect(apiFetch).toHaveBeenCalledWith('/workspace/files', { cache: 'no-store' })
    expect(apiFetch).toHaveBeenCalledWith('/workspace/files/read?path=targets.txt')
    expect(document.getElementById('workspace-viewer-title').textContent).toBe('targets.txt')
    expect(document.getElementById('workspace-viewer-text').textContent).toContain('updated target')
    expect(document.getElementById('workspace-summary').getAttribute('aria-label'))
      .toBe('Personal, 1 / 10 files, 18 B / 1 KB')
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
      if (url === '/workspace/files/download-ticket' && opts?.method === 'POST') {
        return Promise.resolve(responseJson({
          ok: true,
          url: '/workspace/files/download?ticket=workspace-ticket',
        }))
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

    expect(apiFetch).toHaveBeenCalledWith('/workspace/files/download-ticket', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: 'amass-viz/amass.html' }),
    })
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

    const searchableText = Array.from({ length: 2005 }, (_, index) => `line ${index + 1}`).join('\n')
    showWorkspaceViewer('searchable-large.txt', searchableText)

    const search = document.querySelector('.workspace-viewer-search input[type="text"]')
    search.value = 'de'
    search.dispatchEvent(new Event('input', { bubbles: true }))
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('type 3+ chars')
    expect(document.querySelectorAll('mark.search-hl')).toHaveLength(0)

    search.value = 'line 2000'
    search.dispatchEvent(new Event('input', { bubbles: true }))
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('searching...')
    runPendingSearch()
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('1 / 1')
    expect(document.querySelector('[data-line-number="2000"] mark.search-hl')?.textContent).toBe('line 2000')

    search.value = 'LINE 2000'
    search.dispatchEvent(new Event('input', { bubbles: true }))
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('searching...')
    runPendingSearch()
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('1 / 1')
    document.querySelector('.workspace-viewer-search [aria-label="Case sensitive"]').click()
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('no matches')
    document.querySelector('.workspace-viewer-search [aria-label="Regular expression"]').click()
    search.value = '^199[89]line 199[89]$'
    search.dispatchEvent(new Event('input', { bubbles: true }))
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('searching...')
    runPendingSearch()
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('no matches')
    search.value = '^line 199[89]$'
    search.dispatchEvent(new Event('input', { bubbles: true }))
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('searching...')
    runPendingSearch()
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('1 / 2')
    expect(document.querySelectorAll('mark.search-hl')).toHaveLength(1)
    expect(document.querySelector('[data-line-number="1998"] mark.search-hl')?.textContent).toBe('line 1998')
    search.focus()
    search.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('2 / 2')
    expect(document.querySelectorAll('mark.search-hl')).toHaveLength(1)
    expect(document.querySelector('[data-line-number="1999"] mark.search-hl')?.textContent).toBe('line 1999')
    expect(document.activeElement).toBe(search)
    document.querySelector('.workspace-viewer-search [aria-label="Previous match"]').click()
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('1 / 2')
    expect(document.querySelectorAll('mark.search-hl')).toHaveLength(1)
    expect(document.querySelector('[data-line-number="1998"] mark.search-hl')?.textContent).toBe('line 1998')

    search.value = ''
    search.dispatchEvent(new Event('input', { bubbles: true }))
    expect(document.querySelector('.workspace-viewer-search .search-count').textContent).toBe('')
    expect(document.querySelectorAll('mark.search-hl')).toHaveLength(0)

    expect(document.querySelector('[data-workspace-line-jump]')).toBeNull()
  }, 10_000)

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
      { value: 'targets.txt', description: 'personal file · 11 B' },
      { value: 'ffuf.json', description: 'personal file · 2 KB' },
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

    expect(apiFetch).toHaveBeenCalledWith('/workspace/files', { cache: 'no-store' })
    expect(document.querySelector('.workspace-file-name').textContent).toBe('urls.txt')

    apiFetch.mockClear()
    document.getElementById('workspace-refresh-btn').click()
    await flushWorkspacePromises()

    expect(apiFetch).toHaveBeenCalledWith('/workspace/files', { cache: 'no-store' })
    expect(document.getElementById('workspace-refresh-btn').disabled).toBe(false)
    expect(document.getElementById('workspace-refresh-btn').getAttribute('aria-label')).toBe('Refresh files')
  })

  it('shares the in-flight workspace file request between cache refreshes and modal opens', async () => {
    let resolveFiles
    const apiFetch = vi.fn(() => new Promise(resolve => {
      resolveFiles = resolve
    }))
    const { refreshWorkspaceFiles, refreshWorkspaceFileCache } = setupWorkspace(apiFetch, {
      setTimeout: vi.fn(() => 0),
    })

    const cacheLoad = refreshWorkspaceFileCache()
    const modalLoad = refreshWorkspaceFiles()

    expect(apiFetch).toHaveBeenCalledTimes(1)

    resolveFiles(responseJson({
      files: [{ path: 'urls.txt', size: 18 }],
      usage: { bytes_used: 18, file_count: 1 },
      limits: { quota_bytes: 2048, max_files: 5 },
    }))
    await Promise.all([cacheLoad, modalLoad])

    expect(apiFetch).toHaveBeenCalledTimes(1)
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
    const { saveWorkspaceFile, globals } = setupWorkspace(apiFetch)

    await saveWorkspaceFile('targets.txt', 'darklab.sh\n')

    expect(apiFetch).toHaveBeenCalledWith('/workspace/files', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ path: 'targets.txt', text: 'darklab.sh\n' }),
    }))
    expect(globals.showToast).toHaveBeenCalledWith('Saved targets.txt', 'success')
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
    const { createWorkspaceDirectory, globals } = setupWorkspace(apiFetch)

    await createWorkspaceDirectory('reports')

    expect(apiFetch).toHaveBeenCalledWith('/workspace/directories', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ path: 'reports' }),
    }))
    expect(globals.showToast).toHaveBeenCalledWith('Created folder reports', 'success')
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
      expect(opts.body.text).toBe('Create a workspace folder?')
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
