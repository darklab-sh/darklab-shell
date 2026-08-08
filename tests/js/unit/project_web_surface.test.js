// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { DarklabProjectWebSurface } from '../../../app/static/js/features/projects/project_web_surface.js'
import { DarklabProjectPackages } from '../../../app/static/js/features/projects/project_packages.js'

function jsonResponse(payload, { ok = true } = {}) {
  return {
    ok,
    json: vi.fn(async () => payload),
  }
}

function touchEvent(type, touches = [], changedTouches = []) {
  const event = new Event(type, { bubbles: true, cancelable: true })
  Object.defineProperty(event, 'touches', { value: touches })
  Object.defineProperty(event, 'changedTouches', { value: changedTouches })
  return event
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
    comparison: {
      state: 'changed',
      basis: 'exact_url_and_profile_role',
      previous_capture: {
        artifact_id: 'artifact-previous',
        source_run_id: 'run-previous',
        captured_at: '2026-08-06T00:00:00+00:00',
        visual_hash: 'visual-previous',
      },
    },
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

function harness(responses, contextOverrides = {}) {
  const apiFetch = vi.fn(async (url) => {
    if (String(url).includes('/web-surface?')) return jsonResponse(responses(url))
    if (/\/artifacts\/artifact-[^/]+\/download$/.test(String(url))) {
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
  const openPackageWithArtifact = vi.fn()
  const openReportWithArtifact = vi.fn()
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
    bindDismissible: (overlay, options) => {
      const backdrop = (event) => {
        if (event.target === overlay && options.isOpen()) options.onClose()
      }
      const close = () => { if (options.isOpen()) options.onClose() }
      overlay.addEventListener('click', backdrop)
      options.closeButtons.addEventListener('click', close)
      return {
        dispose: () => {
          overlay.removeEventListener('click', backdrop)
          options.closeButtons.removeEventListener('click', close)
        },
      }
    },
    bindFocusTrap: vi.fn(() => ({ dispose: vi.fn() })),
    focusElement: (element) => { element?.focus(); return Boolean(element) },
    showModalOverlay: (overlay) => { overlay.style.display = 'flex' },
    hideModalOverlay: (overlay) => { overlay.style.display = 'none' },
    markInteractionSurfaceReady: vi.fn(),
    renderProjectExplorer: render,
    renderProjectMobileDetail: vi.fn(),
    mobileView: () => 'list',
    closeProjectWorkspace,
    canMutateProjects: vi.fn(() => true),
    openPackageWithArtifact,
    openReportWithArtifact,
    openEntityInAtlas,
    openHistoryRunDetails,
    logClientError,
    metaSeparator: ' · ',
    ...contextOverrides,
  })
  return {
    apiFetch,
    closeProjectWorkspace,
    container,
    controller,
    logClientError,
    openEntityInAtlas,
    openHistoryRunDetails,
    openPackageWithArtifact,
    openReportWithArtifact,
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
    expect(test.container.textContent).toContain('Visual hash changed since date:2026-08-06T00:00:00+00:00.')
    expect(test.container.textContent).toContain('metadata conflict')
    expect(test.container.textContent).toContain('Conflicting capture metadata was rejected.')
    expect(test.container.textContent).toContain("package handoff starts in Raw because images can't be redacted automatically")
    expect(test.container.querySelectorAll('.project-web-surface-image')).toHaveLength(2)
    expect(globalThis.URL.createObjectURL).toHaveBeenCalledOnce()

    const preview = test.container.querySelector('.project-web-surface-preview')
    preview.click()
    expect(preview.getAttribute('aria-expanded')).toBe('true')
    expect(preview.closest('.project-web-surface-card').classList.contains('is-expanded')).toBe(true)

    const atlasButton = [...test.container.querySelectorAll('.project-web-surface-card .project-web-surface-action')]
      .find(button => button.textContent === 'Open URL in Atlas')
    atlasButton.click()
    expect(test.openEntityInAtlas).toHaveBeenCalledWith('project-1', {
      id: 'entity-url-1',
      type: 'url',
      canonical_value: 'https://app.darklab.sh/login',
    })
    const packageButton = [...test.container.querySelectorAll('.project-web-surface-card .project-web-surface-action')]
      .find(button => button.textContent === 'Add to package')
    packageButton.click()
    expect(test.openPackageWithArtifact).toHaveBeenCalledWith('project-1', 'artifact-1')
    const reportButton = [...test.container.querySelectorAll('.project-web-surface-card .project-web-surface-action')]
      .find(button => button.textContent === 'Add to report')
    reportButton.click()
    expect(test.openReportWithArtifact).toHaveBeenCalledWith('project-1', expect.objectContaining({
      id: 'artifact-1',
      display_name: 'app-darklab-sh.png',
    }))
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

  it('opens a full screenshot viewer with keyboard and touch navigation', async () => {
    const second = capture({
      url: 'https://admin.darklab.sh/',
      title: 'Darklab admin',
      status_code: 401,
      profile_role: 'authenticated',
      artifact: {
        ...capture().artifact,
        id: 'artifact-2',
        display_name: 'admin-darklab-sh.png',
        content_sha256: 'sha-two',
      },
      source_run: { id: 'run-two', command: 'httpx -screenshot https://admin.darklab.sh' },
      comparison: { state: 'no_baseline', basis: 'exact_url_and_profile_role' },
    })
    const test = harness(() => ({
      captures: [capture(), second],
      total: 2,
      limit: 24,
      offset: 0,
      has_more: false,
    }))

    test.controller.render(test.container, 'project-1')
    await vi.waitFor(() => expect(test.container.querySelectorAll('.project-web-surface-card')).toHaveLength(2))
    const fullView = [...test.container.querySelectorAll('.project-web-surface-action')]
      .find(button => button.textContent === 'Full view')
    fullView.focus()
    fullView.click()

    const overlay = document.getElementById('project-web-surface-viewer-overlay')
    await vi.waitFor(() => expect(overlay.style.display).toBe('flex'))
    await vi.waitFor(() => expect(overlay.querySelector('.project-web-surface-viewer-image')?.src).toBe('blob:web-surface-one'))
    const artifactOneDownloads = test.apiFetch.mock.calls
      .filter(([url]) => String(url).endsWith('/artifacts/artifact-1/download'))
    expect(artifactOneDownloads).toHaveLength(1)
    expect(overlay.getAttribute('aria-hidden')).toBe('false')
    expect(overlay.querySelector('#project-web-surface-viewer-title')?.textContent).toBe('Darklab sign in')
    expect(overlay.querySelector('.project-web-surface-viewer-position')?.textContent).toBe('1 of 2')
    expect(overlay.querySelector('.project-web-surface-viewer-previous')?.disabled).toBe(true)

    const body = overlay.querySelector('.project-web-surface-viewer-body')
    body.scrollTop = 120
    overlay.querySelector('.project-web-surface-viewer').dispatchEvent(
      new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true, cancelable: true }),
    )
    expect(overlay.querySelector('#project-web-surface-viewer-title')?.textContent).toBe('Darklab admin')
    expect(overlay.querySelector('.project-web-surface-viewer-position')?.textContent).toBe('2 of 2')
    expect(overlay.querySelector('.project-web-surface-viewer-next')?.disabled).toBe(true)
    expect(body.scrollTop).toBe(0)

    body.dispatchEvent(touchEvent('touchstart', [{ clientX: 20, clientY: 30 }]))
    body.dispatchEvent(touchEvent('touchend', [], [{ clientX: 100, clientY: 34 }]))
    expect(overlay.querySelector('#project-web-surface-viewer-title')?.textContent).toBe('Darklab sign in')

    overlay.querySelector('.project-web-surface-viewer-close').click()
    expect(overlay.style.display).toBe('none')
    expect(overlay.getAttribute('aria-hidden')).toBe('true')
    await vi.waitFor(() => expect(document.activeElement).toBe(fullView))
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

  it('applies collection filters, reports bounded searches, and groups the visible page', async () => {
    const second = capture({
      url: 'https://admin.darklab.sh/',
      title: 'Admin',
      status_code: 401,
      technologies: ['Caddy'],
      profile_role: 'authenticated',
      visual_hash: 'visual-two',
      capture_state: 'unavailable',
      artifact: {
        ...capture().artifact,
        id: 'artifact-2',
        file_available: false,
      },
      source_run: { id: 'run-two', command: 'httpx -screenshot https://admin.darklab.sh' },
      comparison: { state: 'no_baseline', basis: 'exact_url_and_profile_role' },
    })
    const test = harness((url) => {
      const params = new URL(`https://example.test${url}`).searchParams
      const filtered = Boolean(params.get('target'))
      return {
        captures: filtered ? [capture()] : [capture(), second],
        total: filtered ? 1 : 2,
        limit: 24,
        offset: 0,
        candidate_total: filtered ? 500 : 2,
        candidate_limit: 200,
        candidate_truncated: filtered,
        comparison_candidate_limit: 200,
        comparison_candidate_truncated: filtered,
        has_more: false,
      }
    })

    test.controller.render(test.container, 'project-1')
    await vi.waitFor(() => expect(test.container.textContent).toContain('Admin'))

    const group = test.container.querySelector('select[aria-label="Group Web Surface captures"]')
    group.value = 'status'
    group.dispatchEvent(new Event('change', { bubbles: true }))
    expect(test.container.textContent).toContain('HTTP 200 (1)')
    expect(test.container.textContent).toContain('HTTP 401 (1)')
    group.value = 'change_state'
    group.dispatchEvent(new Event('change', { bubbles: true }))
    expect(test.container.textContent).toContain('Visual changed (1)')
    expect(test.container.textContent).toContain('No baseline (1)')

    const values = {
      target: 'app.darklab.sh',
      status_code: '200',
      technology: 'nginx',
      profile_role: 'anonymous',
      visual_hash: 'visual-one',
      change_state: 'changed',
    }
    Object.entries(values).forEach(([name, value]) => {
      test.container.querySelector(`[name="${name}"]`).value = value
    })
    test.container.querySelector('.project-web-surface-controls').dispatchEvent(
      new Event('submit', { bubbles: true, cancelable: true }),
    )

    await vi.waitFor(() => expect(test.container.textContent).not.toContain('Admin'))
    expect(test.apiFetch).toHaveBeenCalledWith(
      '/projects/project-1/web-surface?limit=24&offset=0&target=app.darklab.sh&status_code=200&technology=nginx&profile_role=anonymous&visual_hash=visual-one&change_state=changed',
      { cache: 'no-store' },
    )
    expect(test.container.textContent).toContain("Filters searched the newest 200 of 500 captures. Older captures weren't included.")
    expect(test.container.textContent).toContain('Change comparisons use the newest 200 of 500 captures.')
    expect(test.container.textContent).toContain('Visual changed (1)')

    const clear = [...test.container.querySelectorAll('.project-web-surface-control-actions button')]
      .find(button => button.textContent === 'Clear filters')
    clear.click()
    await vi.waitFor(() => expect(test.container.textContent).toContain('Admin'))
    expect(test.controller.page('project-1').filters).toEqual({
      target: '',
      status_code: '',
      technology: '',
      profile_role: '',
      visual_hash: '',
      change_state: '',
    })
  })

  it('shows a useful empty state without requesting image bytes', async () => {
    const test = harness(() => ({ captures: [], total: 0, limit: 24, offset: 0, has_more: false }))

    test.controller.render(test.container, 'project-1')

    await vi.waitFor(() => expect(test.container.textContent).toContain('No HTTPx screenshots are linked'))
    expect(test.apiFetch).toHaveBeenCalledOnce()
    expect(globalThis.URL.createObjectURL).not.toHaveBeenCalled()
  })

  it('keeps package and report handoffs out of view-only project scopes', async () => {
    const test = harness(
      () => ({ captures: [capture()], total: 1, limit: 24, offset: 0, has_more: false }),
      { canMutateProjects: vi.fn(() => false) },
    )

    test.controller.render(test.container, 'project-1')

    await vi.waitFor(() => expect(test.container.textContent).toContain('Darklab sign in'))
    expect(test.container.textContent).not.toContain('Screenshot handoffs keep redaction explicit')
    expect(test.container.textContent).not.toContain('Add to package')
    expect(test.container.textContent).not.toContain('Add to report')
  })

  it('opens the package builder with only the handed-off screenshot selected and an explicit raw default', async () => {
    const overlay = document.createElement('div')
    const body = document.createElement('div')
    overlay.appendChild(body)
    document.body.appendChild(overlay)
    const artifacts = [
      { id: 'artifact-1', run_id: 'run-1', display_name: 'capture.png', file_status: 'available' },
      { id: 'artifact-2', run_id: 'run-1', display_name: 'other.png', file_status: 'available' },
    ]
    const summary = {
      project: { id: 'project-1', name: 'Web Surface' },
      runs: [{ id: 'run-1', command: 'httpx -screenshot https://app.darklab.sh', started: '' }],
      findings: [],
      targets: [],
      artifacts,
      counts: {},
    }
    const controller = DarklabProjectPackages.createProjectPackagesController({
      apiFetch: vi.fn(async () => jsonResponse({ presets: [] })),
      wizardOverlay: overlay,
      wizardBody: body,
      getSelectedProjectId: () => 'project-1',
      selectedProject: () => summary.project,
      projectSummary: () => summary,
      projectRunItems: value => value?.runs || [],
      projectArtifactItems: value => value?.artifacts || [],
      projectTargetItems: value => value?.targets || [],
      projectFindingItems: () => [],
      projectFindingsLoaded: () => true,
      projectFilesEnabled: () => true,
      projectArtifactStatus: artifact => artifact.file_status,
      projectArtifactDetail: artifact => artifact.display_name,
      formatDate: value => value,
      formatBytes: value => String(value),
      makeProjectButton: (label, action, projectId) => {
        const button = document.createElement('button')
        button.type = 'button'
        button.textContent = label
        button.dataset.projectAction = action
        button.dataset.projectId = projectId
        return button
      },
      bindProjectRuntimePressable: vi.fn(),
      emptyProjectPanel: (text) => {
        const panel = document.createElement('div')
        panel.textContent = text
        return panel
      },
      renderProjectExplorer: vi.fn(),
      setProjectWorkspaceMessage: vi.fn(),
      syncProjectWorkspaceNestedSuppression: vi.fn(),
      focusProjectNestedSheet: vi.fn(),
      installProjectMobileKeyboardGuards: vi.fn(),
    })

    controller.openWizardForArtifacts('project-1', ['artifact-1'])

    await vi.waitFor(() => expect(body.textContent).toContain("Screenshot files are binary and can't be redacted automatically"))
    expect(body.querySelector('.project-package-step.is-active')?.textContent).toContain('Include')
    expect(body.querySelector('[data-project-package-selection="artifact"][value="artifact-1"]')?.checked).toBe(true)
    expect(body.querySelector('[data-project-package-selection="artifact"][value="artifact-2"]')?.checked).toBe(false)
    await controller.handleAction(body.querySelector('[data-project-action="package-wizard-next"]'))
    expect(body.querySelector('[data-project-package-field="redaction_mode"]')?.value).toBe('raw')
    expect(body.textContent).toContain('Include selected raw artifacts')
  })
})
