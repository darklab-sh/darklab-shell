// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DarklabProjectAssessment } from '../../../app/static/js/features/projects/project_assessment.js'

function apiResponse(payload = {}, { ok = true } = {}) {
  return { ok, json: vi.fn(async () => payload) }
}

function makeContext(projectWorkspaceRequest, overrides = {}) {
  return {
    projectWorkspaceRequest,
    projectResponseError: vi.fn(async (_resp, fallback) => new Error(fallback)),
    formatDate: vi.fn(value => String(value || '').replace('T', ' ')),
    bindProjectRuntimePressable: vi.fn((element, options = {}) => {
      if (typeof options.onActivate === 'function') {
        element.addEventListener('click', options.onActivate)
      }
      return element
    }),
    emptyProjectPanel: vi.fn((text) => {
      const panel = document.createElement('div')
      panel.className = 'project-empty'
      panel.textContent = text
      return panel
    }),
    enhanceAppSelects: vi.fn(),
    renderProjectExplorer: vi.fn(),
    renderProjectMobileDetail: vi.fn(),
    setProjectWorkspaceMessage: vi.fn(),
    showConfirm: vi.fn(async options => options.actions.at(-1).id),
    actionSheetContainer: vi.fn(() => document.body),
    logClientError: vi.fn(),
    mobileView: vi.fn(() => 'list'),
    canMutateProjects: vi.fn(() => true),
    ...overrides,
  }
}

const cycle = {
  id: 'asmt_1',
  title: 'Network review',
  profile_key: 'network',
  profile_version: '1.0.0',
  status: 'active',
  started_at: '2026-08-05T10:00:00+00:00',
}

const profiles = [{
  key: 'network',
  version: '1.0.0',
  label: 'Network assessment',
  purpose: 'Review exposed network services.',
  target_types: ['domain', 'ip'],
  check_count: 2,
}]

const detail = {
  assessment: {
    ...cycle,
    profile_snapshot: {
      checks: [
        { key: 'service_inventory', label: 'Service inventory', purpose: 'Record exposed services.' },
        { key: 'dns_inventory', label: 'DNS inventory', purpose: 'Review DNS records.' },
      ],
    },
  },
  rollup: {
    total_checks: 2,
    applicable_checks: 2,
    covered_checks: 1,
    checks_awaiting_review: 1,
    untested_checks: 0,
    excluded_checks: 0,
    unavailable_evidence_checks: 1,
  },
  category_rollups: [{
    category: 'discovery',
    total_checks: 2,
    applicable_checks: 2,
    covered_checks: 1,
  }],
  checks: {
    checks: [
      {
        id: 'asmc_1',
        check_key: 'service_inventory',
        target_entity_id: 'ent_1',
        target_type: 'domain',
        target_value: 'example.com',
        policy_level: 'safe',
        state: 'covered',
        state_source: 'derived',
        evidence_count: 2,
        unavailable_evidence_count: 0,
      },
      {
        id: 'asmc_2',
        check_key: 'dns_inventory',
        target_entity_id: 'ent_1',
        target_type: 'domain',
        target_value: 'example.com',
        policy_level: 'safe',
        state: 'needs_review',
        state_source: 'manual',
        evidence_count: 1,
        unavailable_evidence_count: 1,
      },
    ],
    total: 75,
    limit: 50,
    offset: 0,
    has_more: true,
  },
}

function responseFor(url, options = {}) {
  if (options.method === 'POST') {
    return apiResponse({ assessment: { ...cycle, id: 'asmt_new' } })
  }
  if (/\/assessments\/[^?]+/.test(url)) return apiResponse(detail)
  return apiResponse({ assessments: [cycle], profiles, total: 1, limit: 100, offset: 0, has_more: false })
}

describe('project assessment controller', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    document.body.replaceChildren()
  })

  it('renders the same truthful coverage and target worklist on desktop and mobile', async () => {
    const projectWorkspaceRequest = vi.fn(async (url, options) => responseFor(url, options))
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = DarklabProjectAssessment.createProjectAssessmentController(ctx)

    await controller.load('prj_1', { render: false })
    const desktop = document.createElement('div')
    controller.renderAssessment(desktop, 'prj_1')
    const mobile = controller.renderMobileAssessmentTab('prj_1')

    for (const surface of [desktop, mobile]) {
      expect(surface.textContent).toContain('Network review')
      expect(surface.textContent).toContain('1Coveredof 2 applicable')
      expect(surface.textContent).toContain('1Awaiting review')
      expect(surface.textContent).toContain('1Evidence unavailablesaved source was removed')
      expect(surface.querySelector('.project-assessment-target-list')?.classList.contains('nice-scroll')).toBe(true)
      const disclosure = surface.querySelector('.project-assessment-target-toggle')
      expect(disclosure?.getAttribute('aria-expanded')).toBe('false')
      expect(surface.querySelector('.project-assessment-target-body')?.classList.contains('u-hidden')).toBe(true)
      disclosure.click()
      expect(disclosure.getAttribute('aria-expanded')).toBe('true')
      expect(surface.textContent).toContain('Service inventory')
      expect(surface.textContent).toContain('Needs review')
      expect(surface.textContent).toContain('Manual decision')
    }
    expect(mobile.classList.contains('is-mobile')).toBe(true)
    mobile.querySelector('.project-assessment-mobile-actions button').click()
    expect([...document.querySelectorAll('.action-sheet-item')].map(button => button.textContent)).toEqual([
      'Complete cycle',
      'Archive cycle',
    ])
    expect(ctx.enhanceAppSelects).toHaveBeenCalledTimes(2)
  })

  it('preserves cycle filters, paging, disclosure, and scroll state per project', async () => {
    const projectWorkspaceRequest = vi.fn(async (url, options) => responseFor(url, options))
    const controller = DarklabProjectAssessment.createProjectAssessmentController(
      makeContext(projectWorkspaceRequest),
    )
    await controller.load('prj_1', { render: false })
    await controller.setFilter('prj_1', 'category', 'discovery')
    await controller.setFilter('prj_1', 'state', 'needs_review')
    await controller.setPage('prj_1', 50)

    const detailUrls = projectWorkspaceRequest.mock.calls
      .map(([url]) => url)
      .filter(url => url.includes('/assessments/asmt_1?'))
    expect(detailUrls.at(-1)).toContain('limit=50&offset=50')
    expect(detailUrls.at(-1)).toContain('category=discovery')
    expect(detailUrls.at(-1)).toContain('state=needs_review')

    const container = document.createElement('div')
    controller.renderAssessment(container, 'prj_1')
    container.querySelector('.project-assessment-target-toggle').click()
    const list = container.querySelector('.project-assessment-target-list')
    list.scrollTop = 137
    list.dispatchEvent(new Event('scroll'))
    controller.renderAssessment(container, 'prj_1')

    const state = controller.stateFor('prj_1')
    expect(state.category).toBe('discovery')
    expect(state.checkState).toBe('needs_review')
    expect(state.offset).toBe(50)
    expect(state.checksScrollTop).toBe(137)
    expect(container.querySelector('.project-assessment-target-list').scrollTop).toBe(137)
    expect(container.querySelector('.project-assessment-target-toggle').getAttribute('aria-expanded')).toBe('true')

    controller.invalidate('prj_1')
    expect(state.loaded).toBe(false)
    expect(state.detail).toBeNull()
    expect(state.category).toBe('discovery')
    expect(state.checkState).toBe('needs_review')
    expect(state.offset).toBe(50)
    expect(state.checksScrollTop).toBe(137)
    expect(state.expandedTargets.has('domain:ent_1')).toBe(true)
  })

  it('starts a profile-driven cycle and keeps the action read-only for viewers', async () => {
    let cycles = []
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      if (options.method === 'POST') {
        cycles = [{ ...cycle, id: 'asmt_new' }]
        return apiResponse({ assessment: cycles[0] })
      }
      if (/\/assessments\/[^?]+/.test(url)) {
        return apiResponse({ ...detail, assessment: { ...detail.assessment, id: 'asmt_new' } })
      }
      return apiResponse({ assessments: cycles, profiles, total: cycles.length, limit: 100, offset: 0, has_more: false })
    })
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = DarklabProjectAssessment.createProjectAssessmentController(ctx)
    await controller.load('prj_1', { render: false })
    const container = document.createElement('div')
    controller.renderAssessment(container, 'prj_1')
    expect(container.querySelector('button[type="submit"]').disabled).toBe(false)

    await controller.createCycle('prj_1', 'network')
    expect(projectWorkspaceRequest).toHaveBeenCalledWith('/projects/prj_1/assessments', {
      method: 'POST',
      body: JSON.stringify({ profile_key: 'network' }),
    })
    expect(controller.stateFor('prj_1').selectedId).toBe('asmt_new')
    expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith('Assessment cycle started.')

    const viewerRequest = vi.fn(async () => apiResponse({ assessments: [], profiles, total: 0 }))
    const viewer = DarklabProjectAssessment.createProjectAssessmentController(makeContext(viewerRequest, {
      canMutateProjects: vi.fn(() => false),
    }))
    await viewer.load('prj_view', { render: false })
    const viewerContainer = document.createElement('div')
    viewer.renderAssessment(viewerContainer, 'prj_view')
    expect(viewerContainer.querySelector('button[type="submit"]').disabled).toBe(true)
    expect(viewerContainer.querySelector('button[type="submit"]').title).toContain('View-only')

    const viewerCycle = DarklabProjectAssessment.createProjectAssessmentController(makeContext(
      vi.fn(async (url, options) => responseFor(url, options)),
      { canMutateProjects: vi.fn(() => false) },
    ))
    await viewerCycle.load('prj_view_cycle', { render: false })
    const viewerCycleContainer = document.createElement('div')
    viewerCycle.renderAssessment(viewerCycleContainer, 'prj_view_cycle')
    const lifecycleButtons = [...viewerCycleContainer.querySelectorAll('.project-assessment-cycle-actions button')]
    expect(lifecycleButtons.map(button => button.textContent)).toEqual(['Complete cycle', 'Archive cycle'])
    expect(lifecycleButtons.every(button => button.disabled && button.title.includes('View-only'))).toBe(true)
  })

  it('confirms forward-only lifecycle changes and previews archived-cycle deletion', async () => {
    let current = { ...cycle }
    let deleted = false
    const projectWorkspaceRequest = vi.fn(async (url, options = {}) => {
      if (url.endsWith('/delete-preview')) {
        return apiResponse({
          preview: {
            can_delete: true,
            will_delete: { checks: 2, evidence_links: 3 },
          },
        })
      }
      if (options.method === 'PATCH') {
        current = { ...current, status: JSON.parse(options.body).status }
        return apiResponse({ assessment: current })
      }
      if (options.method === 'DELETE') {
        deleted = true
        return apiResponse({ ok: true })
      }
      if (/\/assessments\/[^?]+/.test(url)) {
        return apiResponse({ ...detail, assessment: { ...detail.assessment, ...current } })
      }
      return apiResponse({
        assessments: deleted ? [] : [current],
        profiles,
        total: deleted ? 0 : 1,
        limit: 100,
        offset: 0,
        has_more: false,
      })
    })
    const ctx = makeContext(projectWorkspaceRequest)
    const controller = DarklabProjectAssessment.createProjectAssessmentController(ctx)
    await controller.load('prj_1', { render: false })

    expect(await controller.transitionCycle('prj_1', 'completed')).toBe(true)
    expect(current.status).toBe('completed')
    expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith('Assessment cycle completed.')

    expect(await controller.transitionCycle('prj_1', 'archived')).toBe(true)
    expect(current.status).toBe('archived')
    expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith('Assessment cycle archived.')

    expect(await controller.deleteCycle('prj_1')).toBe(true)
    expect(deleted).toBe(true)
    expect(ctx.showConfirm.mock.calls.at(-1)[0].body.note).toContain('2 saved checks and 3 evidence links')
    expect(ctx.showConfirm.mock.calls.at(-1)[0].body.note).toContain('Source runs, findings, entities, and files stay intact.')
    expect(controller.stateFor('prj_1').assessments).toEqual([])
    expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith('Assessment cycle deleted.')
  })

  it('cancels lifecycle transitions without sending a mutation', async () => {
    const projectWorkspaceRequest = vi.fn(async (url, options) => responseFor(url, options))
    const ctx = makeContext(projectWorkspaceRequest, {
      showConfirm: vi.fn(async () => 'cancel'),
    })
    const controller = DarklabProjectAssessment.createProjectAssessmentController(ctx)
    await controller.load('prj_1', { render: false })

    expect(await controller.transitionCycle('prj_1', 'completed')).toBe(false)
    expect(projectWorkspaceRequest.mock.calls.some(([, options]) => options?.method === 'PATCH')).toBe(false)
  })
})
