// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { DarklabProjectWebSurface } from '../../../app/static/js/features/projects/project_web_surface.js'

function jsonResponse(payload, { ok = true } = {}) {
  return {
    ok,
    json: vi.fn(async () => payload),
  }
}

function capture(overrides = {}) {
  return {
    url: 'https://app.darklab.sh/login',
    status_code: 200,
    title: 'Darklab sign in',
    technologies: ['nginx', 'Flask'],
    captured_at: '2026-08-07T00:00:00+00:00',
    visual_hash: 'visual-one',
    profile_role: 'anonymous',
    metadata_state: 'available',
    capture_state: 'current',
    artifact: {
      id: 'artifact-1',
      display_name: 'app-darklab-sh.png',
      workspace_path: 'captures/app-darklab-sh.png',
      content_type: 'image/png',
      content_sha256: 'sha-one',
      file_status: 'available',
      file_available: true,
      file_status_detail: '',
    },
    source_run: {
      id: 'run-1234567890abcdef',
      command: 'httpx -screenshot https://app.darklab.sh',
    },
    url_entity_id: 'entity-url-1',
    host_entity_id: 'entity-host-1',
    ...overrides,
  }
}

function harness(responses) {
  const apiFetch = vi.fn(async (url) => {
    if (String(url).includes('/web-surface?')) return jsonResponse(responses(url))
    if (String(url).endsWith('/artifacts/artifact-1/download')) {
      return {
        ok: true,
        blob: vi.fn(async () => new Blob(['png'], { type: 'image/png' })),
      }
    }
    throw new Error(`Unexpected request: ${url}`)
  })
  const container = document.createElement('div')
  document.body.appendChild(container)
  const openEntityInAtlas = vi.fn()
  const openHistoryRunDetails = vi.fn()
  const closeProjectWorkspace = vi.fn()
  const logClientError = vi.fn()
  let controller
  const render = () => {
    container.replaceChildren()
    controller.render(container, 'project-1')
  }
  controller = DarklabProjectWebSurface.createProjectWebSurfaceController({
    apiFetch,
    projectResponseError: async (_resp, fallback) => new Error(fallback),
    emptyProjectPanel: (text) => {
      const node = document.createElement('div')
      node.className = 'empty-panel'
      node.textContent = text
      return node
    },
    formatDate: value => `date:${value}`,
    shortProjectRunId: value => String(value).slice(0, 8),
    bindProjectRuntimePressable: (button) => { button.dataset.pressableBound = '1' },
    renderProjectExplorer: render,
    renderProjectMobileDetail: vi.fn(),
    mobileView: () => 'list',
    closeProjectWorkspace,
    openEntityInAtlas,
    openHistoryRunDetails,
    logClientError,
    metaSeparator: ' · ',
  })
  return {
    apiFetch,
    closeProjectWorkspace,
    container,
    controller,
    logClientError,
    openEntityInAtlas,
    openHistoryRunDetails,
  }
}

describe('Project Web Surface gallery', () => {
  beforeEach(() => {
    document.body.replaceChildren()
    globalThis.URL.createObjectURL = vi.fn(() => 'blob:web-surface-one')
    globalThis.URL.revokeObjectURL = vi.fn()
  })

  afterEach(() => {
    document.body.replaceChildren()
    vi.restoreAllMocks()
  })

  it('renders authenticated screenshots with factual metadata and existing navigation actions', async () => {
    const unavailable = capture({
      url: 'https://old.darklab.sh/',
      title: '',
      capture_state: 'metadata_conflict',
      metadata_state: 'conflict',
      artifact: {
        id: 'artifact-2',
        display_name: 'old-darklab-sh.png',
        content_type: 'image/png',
        content_sha256: 'sha-two',
        file_available: true,
      },
      source_run: { id: 'run-two', command: 'httpx -screenshot https://old.darklab.sh' },
      url_entity_id: '',
    })
    const test = harness(() => ({
      captures: [capture(), unavailable],
      total: 2,
      limit: 24,
      offset: 0,
      has_more: false,
    }))

    test.controller.render(test.container, 'project-1')

    await vi.waitFor(() => expect(test.container.querySelectorAll('.project-web-surface-card')).toHaveLength(2))
    await vi.waitFor(() => expect(test.container.querySelector('.project-web-surface-image')?.src).toBe('blob:web-surface-one'))
    expect(test.apiFetch).toHaveBeenCalledWith(
      '/projects/project-1/web-surface?limit=24&offset=0',
      { cache: 'no-store' },
    )
    expect(test.apiFetch).toHaveBeenCalledWith(
      '/projects/project-1/artifacts/artifact-1/download',
      { cache: 'no-store' },
    )
    expect(test.container.textContent).toContain('Darklab sign in')
    expect(test.container.textContent).toContain('HTTP 200 · nginx, Flask · role: anonymous')
    expect(test.container.textContent).toContain('metadata conflict')
    expect(test.container.textContent).toContain('Conflicting capture metadata was rejected.')
    expect(test.container.querySelectorAll('.project-web-surface-image')).toHaveLength(2)
    expect(globalThis.URL.createObjectURL).toHaveBeenCalledOnce()

    const preview = test.container.querySelector('.project-web-surface-preview')
    preview.click()
    expect(preview.getAttribute('aria-expanded')).toBe('true')
    expect(preview.closest('.project-web-surface-card').classList.contains('is-expanded')).toBe(true)

    test.container.querySelector('.project-web-surface-action')?.click()
    expect(test.openEntityInAtlas).toHaveBeenCalledWith('project-1', {
      id: 'entity-url-1',
      type: 'url',
      canonical_value: 'https://app.darklab.sh/login',
    })
    const runButton = [...test.container.querySelectorAll('.project-web-surface-action')]
      .find(button => button.textContent === 'Run details')
    runButton.click()
    expect(test.closeProjectWorkspace).toHaveBeenCalledWith({ refocus: false })
    expect(test.openHistoryRunDetails).toHaveBeenCalledWith({
      id: 'run-1234567890abcdef',
      command: 'httpx -screenshot https://app.darklab.sh',
    })

    test.controller.invalidate('project-1')
    expect(globalThis.URL.revokeObjectURL).toHaveBeenCalledWith('blob:web-surface-one')
    expect(test.logClientError).not.toHaveBeenCalled()
  })

  it('pages captures without losing the bounded server window', async () => {
    const test = harness((url) => {
      const offset = Number(new URL(`https://example.test${url}`).searchParams.get('offset') || 0)
      return {
        captures: [capture({
          title: offset ? 'Second page' : 'First page',
          artifact: {
            ...capture().artifact,
            id: offset ? 'artifact-25' : 'artifact-1',
            file_available: !offset,
          },
          capture_state: offset ? 'unavailable' : 'current',
        })],
        total: 25,
        limit: 24,
        offset,
        has_more: offset === 0,
      }
    })

    test.controller.render(test.container, 'project-1')
    await vi.waitFor(() => expect(test.container.textContent).toContain('First page'))
    const next = [...test.container.querySelectorAll('.project-web-surface-pagination button')]
      .find(button => button.textContent === 'Next')
    next.click()

    await vi.waitFor(() => expect(test.container.textContent).toContain('Second page'))
    expect(test.apiFetch).toHaveBeenCalledWith(
      '/projects/project-1/web-surface?limit=24&offset=24',
      { cache: 'no-store' },
    )
    expect(test.container.textContent).toContain('25-25 of 25 captures')
    expect(test.container.textContent).toContain('Page 2')
  })

  it('shows a useful empty state without requesting image bytes', async () => {
    const test = harness(() => ({ captures: [], total: 0, limit: 24, offset: 0, has_more: false }))

    test.controller.render(test.container, 'project-1')

    await vi.waitFor(() => expect(test.container.textContent).toContain('No HTTPx screenshots are linked'))
    expect(test.apiFetch).toHaveBeenCalledOnce()
    expect(globalThis.URL.createObjectURL).not.toHaveBeenCalled()
  })
})
