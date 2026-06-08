// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fromDomScripts } from './helpers/extract.js'

function apiResponse(payload = {}, { ok = true } = {}) {
  return {
    ok,
    json: vi.fn(async () => payload),
  }
}

function loadActivityModule() {
  const activityApi = fromDomScripts(
    ['app/static/js/features/projects/project_activity.js'],
    { document, window },
    'globalThis.DarklabProjectActivity',
  )
  return activityApi
}

function loadEntityEditorModule() {
  const editorApi = fromDomScripts(
    ['app/static/js/features/projects/project_entity_editor.js'],
    { document, window },
    'globalThis.DarklabProjectEntityEditor',
  )
  return editorApi
}

function makeContext(projectWorkspaceRequest, overrides = {}) {
  return {
    projectWorkspaceRequest,
    projectResponseError: vi.fn(async (_resp, fallback) => new Error(fallback)),
    formatDate: vi.fn(value => String(value || '').replace('T', ' ')),
    makeProjectButton: vi.fn((label, action, projectId) => {
      const btn = document.createElement('button')
      btn.type = 'button'
      btn.textContent = label
      btn.dataset.projectAction = action
      btn.dataset.projectId = projectId
      return btn
    }),
    bindProjectRuntimePressable: vi.fn(),
    emptyProjectPanel: vi.fn((text) => {
      const panel = document.createElement('div')
      panel.className = 'project-empty'
      panel.textContent = text
      return panel
    }),
    renderProjectExplorer: vi.fn(),
    openProjectObject: vi.fn(),
    ...overrides,
  }
}

function deferredResponse(payload) {
  let resolve
  const promise = new Promise((done) => {
    resolve = () => done(apiResponse(payload))
  })
  return { promise, resolve }
}

const eventPayload = {
  events: [{
    id: 'aud_1',
    created: '2026-06-06T12:00:00+00:00',
    event_type: 'finding.review_change',
    actor: { display_name: 'Nona', member_id: 'mem_1', role: 'owner' },
    target: { type: 'finding', id: 'fnd_1', href: '' },
    details: { review_state: 'confirmed' },
  }],
  limit: 25,
  offset: 0,
  has_more: false,
  retention_days: 90,
}

describe('project activity controller', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    document.body.replaceChildren()
    delete globalThis.DarklabProjectActivity
  })

  it('loads and renders project activity filters, rows, and safe details', async () => {
    const activityApi = loadActivityModule()
    const projectWorkspaceRequest = vi.fn(async () => apiResponse(eventPayload))
    const controller = activityApi.createProjectActivityController(makeContext(projectWorkspaceRequest))

    await controller.load('proj_1', { render: false })
    const container = document.createElement('div')
    controller.renderActivity(container, 'proj_1', { project: { id: 'proj_1' } })

    expect(projectWorkspaceRequest).toHaveBeenCalledWith(
      '/projects/proj_1/activity?limit=25&offset=0',
      { cache: 'no-store' },
    )
    expect(container.querySelector('[data-project-activity-filter="event_type"]').placeholder)
      .toBe('finding.review_change')
    expect(container.querySelector('[data-project-activity-filter="actor"]').placeholder)
      .toBe('name or member id')
    expect(container.querySelector('[data-project-activity-filter="date_from"]').type).toBe('date')
    expect(container.querySelector('[data-project-activity-filter="date_to"]').type).toBe('date')
    expect(container.querySelector('.project-activity-table')).not.toBeNull()
    expect(container.querySelector('.project-activity-table-wrap')?.classList.contains('nice-scroll')).toBe(true)
    expect(container.querySelector('.project-activity-row')?.textContent).toContain('Finding Review Change')
    expect(container.querySelector('.project-activity-row')?.textContent).toContain('Nona · owner')
    expect(container.querySelector('details.project-activity-details')).toBeNull()
    expect(container.querySelector('.project-activity-details-toggle')?.dataset.disclosureBound).toBe('1')
    expect(container.querySelector('.project-activity-details-toggle')?.getAttribute('aria-expanded')).toBe('false')
    expect(container.querySelector('.project-activity-detail-list')?.classList.contains('u-hidden')).toBe(true)
    expect(container.querySelector('.project-activity-detail-list')?.classList.contains('nice-scroll')).toBe(true)
    container.querySelector('.project-activity-details-toggle').click()
    expect(container.querySelector('.project-activity-details-toggle')?.getAttribute('aria-expanded')).toBe('true')
    expect(container.querySelector('.project-activity-detail-list')?.classList.contains('u-hidden')).toBe(false)
    expect(container.querySelector('.project-activity-details pre')).toBeNull()
    expect(container.querySelector('.project-activity-detail-list')?.textContent).toContain('review state')
    expect(container.querySelector('.project-activity-detail-list')?.textContent).toContain('confirmed')

    expect(controller.stateFor('proj_1').loaded).toBe(true)
    controller.invalidate('proj_1')
    expect(controller.stateFor('proj_1').loaded).toBe(false)
  })

  it('only offers target types that can appear in project scope', async () => {
    const activityApi = loadActivityModule()
    const projectWorkspaceRequest = vi.fn(async () => apiResponse(eventPayload))
    const controller = activityApi.createProjectActivityController(makeContext(projectWorkspaceRequest))

    await controller.load('proj_1', { render: false })
    const container = document.createElement('div')
    controller.renderActivity(container, 'proj_1', { project: { id: 'proj_1' } })

    const options = Array.from(
      container.querySelectorAll('[data-project-activity-filter="target_type"] option'),
    ).map(option => option.value)

    expect(options).toEqual(['', 'project', 'finding', 'target', 'run', 'package', 'report', 'file', 'label', 'note', 'import'])
    expect(options).not.toContain('notification')
    expect(options).not.toContain('schedule')
    expect(options).not.toContain('watcher')
    expect(options).not.toContain('secret')
    expect(options).not.toContain('team')
  })

  it('opens the related workspace object when a project target is clicked', async () => {
    const activityApi = loadActivityModule()
    const projectWorkspaceRequest = vi.fn(async () => apiResponse(eventPayload))
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = activityApi.createProjectActivityController(ctx)

    await controller.load('proj_1', { render: false })
    const container = document.createElement('div')
    document.body.appendChild(container)
    controller.renderActivity(container, 'proj_1', { project: { id: 'proj_1' } })

    const targetLink = container.querySelector('.project-activity-target-link')
    expect(targetLink).not.toBeNull()
    expect(targetLink.tagName).toBe('BUTTON')
    expect(targetLink.classList.contains('btn-ghost')).toBe(true)
    expect(targetLink.dataset.projectActivityAction).toBe('open-target')
    expect(targetLink.dataset.targetTab).toBe('findings')
    expect(targetLink.dataset.targetType).toBe('finding')
    expect(targetLink.dataset.targetId).toBe('fnd_1')

    await controller.handleClick({ target: targetLink, preventDefault: vi.fn() })
    expect(ctx.openProjectObject).toHaveBeenCalledWith('proj_1', {
      tab: 'findings',
      targetType: 'finding',
      targetId: 'fnd_1',
    })
  })

  it('keeps server-route targets as plain anchors', async () => {
    const activityApi = loadActivityModule()
    const projectWorkspaceRequest = vi.fn(async () => apiResponse({
      ...eventPayload,
      events: [{
        ...eventPayload.events[0],
        id: 'aud_run',
        event_type: 'project.link',
        target: { type: 'run', id: 'run_9', href: '/history/run_9' },
      }],
    }))
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = activityApi.createProjectActivityController(ctx)

    await controller.load('proj_1', { render: false })
    const container = document.createElement('div')
    controller.renderActivity(container, 'proj_1', { project: { id: 'proj_1' } })

    const anchor = container.querySelector('.project-activity-row td a')
    expect(anchor).not.toBeNull()
    expect(anchor.getAttribute('href')).toBe('/history/run_9')
    expect(container.querySelector('.project-activity-target-link')).toBeNull()
  })

  it('prefers stored file path detail keys in row summaries', async () => {
    const activityApi = loadActivityModule()
    const projectWorkspaceRequest = vi.fn(async () => apiResponse({
      ...eventPayload,
      events: [{
        id: 'aud_file',
        created: '2026-06-06T12:05:00+00:00',
        event_type: 'file.move',
        actor: { display_name: 'Nona', role: 'owner' },
        target: { type: 'file', id: 'reports/final.md', href: '' },
        details: {
          count: 1,
          result: 'ok',
          file_count: 1,
          source_path: 'reports/draft.md',
          destination_path: 'reports/final.md',
          file_path: 'reports/final.md',
        },
      }],
    }))
    const controller = activityApi.createProjectActivityController(makeContext(projectWorkspaceRequest))

    await controller.load('proj_1', { render: false })
    const container = document.createElement('div')
    controller.renderActivity(container, 'proj_1', { project: { id: 'proj_1' } })
    const rowText = container.querySelector('.project-activity-row')?.textContent || ''

    expect(rowText).toContain('file path: reports/final.md')
    expect(rowText).toContain('source path: reports/draft.md')
    expect(rowText).toContain('destination path: reports/final.md')
  })

  it('logs project activity load failures with bounded context', async () => {
    const activityApi = loadActivityModule()
    const projectWorkspaceRequest = vi.fn(async () => apiResponse({ message: 'denied' }, { ok: false }))
    const logClientError = vi.fn()
    const controller = activityApi.createProjectActivityController(makeContext(projectWorkspaceRequest, { logClientError }))

    await controller.load('proj_1', { render: false })
    const container = document.createElement('div')
    controller.renderActivity(container, 'proj_1', { project: { id: 'proj_1' } })

    expect(container.textContent).toContain('Could not load project activity.')
    expect(logClientError).toHaveBeenCalledWith(
      'failed to load project activity {"project_id":"proj_1"}',
      expect.any(Error),
    )
  })

  it('logs project Recent activity load failures with bounded target context', async () => {
    const editorApi = loadEntityEditorModule()
    const projectWorkspaceRequest = vi.fn(async () => apiResponse({ message: 'denied' }, { ok: false }))
    const logClientError = vi.fn()
    const activityRoot = document.createElement('div')
    const ctx = {
      activityRoot,
      entityEditorLabelForType: vi.fn(() => 'Finding'),
      entityLabelValues: vi.fn(() => []),
      entityNoteBody: vi.fn(() => ''),
      entityTitleForEditor: vi.fn(() => 'Finding 1'),
      focusProjectNestedSheet: vi.fn(),
      form: document.createElement('form'),
      installProjectMobileKeyboardGuards: vi.fn(),
      labelsInput: document.createElement('input'),
      logClientError,
      noteInput: document.createElement('textarea'),
      overlay: document.createElement('div'),
      projectResponseError: vi.fn(async (_resp, fallback) => new Error(fallback)),
      projectWorkspaceRequest,
      syncProjectWorkspaceNestedSuppression: vi.fn(),
      title: document.createElement('h2'),
      subtitle: document.createElement('p'),
    }
    const controller = editorApi.createProjectEntityEditorController(ctx)

    controller.open('proj_1', 'finding', { id: 'fnd_1', title: 'Finding 1' })

    await vi.waitFor(() => {
      expect(activityRoot.textContent).toContain('Could not load recent activity.')
    })
    expect(logClientError).toHaveBeenCalledWith(
      'failed to load project recent activity {"project_id":"proj_1","target_type":"finding","target_id":"fnd_1"}',
      expect.any(Error),
    )
  })

  it('ignores stale Project Activity responses that resolve out of order', async () => {
    const activityApi = loadActivityModule()
    const first = deferredResponse({
      ...eventPayload,
      events: [{
        ...eventPayload.events[0],
        id: 'aud_old',
        details: { review_state: 'old' },
      }],
      offset: 0,
    })
    const second = deferredResponse({
      ...eventPayload,
      events: [{
        ...eventPayload.events[0],
        id: 'aud_new',
        details: { review_state: 'newer' },
      }],
      offset: 25,
    })
    const projectWorkspaceRequest = vi.fn()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)
    const controller = activityApi.createProjectActivityController(makeContext(projectWorkspaceRequest))

    const firstLoad = controller.load('proj_1', { render: false, offset: 0 })
    const secondLoad = controller.load('proj_1', { render: false, offset: 25 })
    second.resolve()
    await secondLoad
    first.resolve()
    await firstLoad

    const st = controller.stateFor('proj_1')
    expect(st.offset).toBe(25)
    expect(st.events.map(event => event.id)).toEqual(['aud_new'])
    expect(st.events[0].details.review_state).toBe('newer')
    expect(st.loading).toBe(false)
  })

  it('applies filters and clears them without preloading the full audit history', async () => {
    const activityApi = loadActivityModule()
    const projectWorkspaceRequest = vi.fn(async () => apiResponse(eventPayload))
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = activityApi.createProjectActivityController(ctx)

    await controller.load('proj_1', { render: false })
    const container = document.createElement('div')
    document.body.appendChild(container)
    controller.renderActivity(container, 'proj_1', { project: { id: 'proj_1' } })

    container.querySelector('[data-project-activity-filter="event_type"]').value = 'finding.review_change'
    container.querySelector('[data-project-activity-filter="actor"]').value = 'nona'
    await controller.handleClick({
      target: container.querySelector('[data-project-activity-action="apply"]'),
      preventDefault: vi.fn(),
    })

    expect(projectWorkspaceRequest).toHaveBeenLastCalledWith(
      '/projects/proj_1/activity?event_type=finding.review_change&actor=nona&limit=25&offset=0',
      { cache: 'no-store' },
    )
    await controller.handleClick({
      target: container.querySelector('[data-project-activity-action="clear"]'),
      preventDefault: vi.fn(),
    })
    expect(projectWorkspaceRequest).toHaveBeenLastCalledWith(
      '/projects/proj_1/activity?limit=25&offset=0',
      { cache: 'no-store' },
    )
    expect(ctx.renderProjectExplorer).toHaveBeenCalled()
  })

  it('renders empty and mobile activity states with collapsed details', async () => {
    const activityApi = loadActivityModule()
    const emptyRequest = vi.fn(async () => apiResponse({
      events: [],
      limit: 25,
      offset: 0,
      has_more: false,
      retention_days: 90,
    }))
    const emptyController = activityApi.createProjectActivityController(makeContext(emptyRequest))
    await emptyController.load('proj_1', { render: false })
    const emptyContainer = document.createElement('div')
    emptyController.renderActivity(emptyContainer, 'proj_1', { project: { id: 'proj_1' } })
    expect(emptyContainer.textContent).toContain('No project activity yet.')
    expect(emptyContainer.textContent).toContain('Audit rows older than 90 days')

    const eventRequest = vi.fn(async () => apiResponse(eventPayload))
    const eventController = activityApi.createProjectActivityController(makeContext(eventRequest))
    await eventController.load('proj_1', { render: false })
    const mobile = eventController.renderMobileActivityTab('proj_1', { project: { id: 'proj_1' } })
    expect(mobile.querySelector('.project-activity-mobile-row')?.textContent).toContain('Finding Review Change')
    expect(mobile.querySelector('details.project-activity-details')).toBeNull()
    expect(mobile.querySelector('.project-activity-details-toggle')?.dataset.disclosureBound).toBe('1')
  })
})
