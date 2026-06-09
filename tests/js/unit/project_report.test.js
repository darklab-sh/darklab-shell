// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fromDomScripts } from './helpers/extract.js'

function apiResponse(payload = {}, { ok = true } = {}) {
  return {
    ok,
    json: vi.fn(async () => payload),
  }
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((promiseResolve, promiseReject) => {
    resolve = promiseResolve
    reject = promiseReject
  })
  return { promise, resolve, reject }
}

function loadReportModule(globals = {}) {
  const sandbox = {
    activeTeamScopeCan: vi.fn(() => true),
    teamScopeDeniedMessage: vi.fn(() => "View-only team members can't change team projects. Switch to Personal or ask for operator access."),
    enhanceAppSelects: vi.fn(),
    ...globals,
  }
  Object.assign(globalThis, sandbox)
  const reportApi = fromDomScripts(
    [
      'app/static/js/features/projects/project_shared_ui.js',
      'app/static/js/features/projects/project_report.js',
    ],
    { document, window },
    'globalThis.DarklabProjectReport',
  )
  return { reportApi, sandbox }
}

function makeContext(apiFetch = vi.fn(), overrides = {}) {
  const sharedUi = globalThis.DarklabProjectSharedUi?.createProjectSharedUiController?.({})
  return {
    apiFetch,
    getSelectedProjectId: vi.fn(() => 'proj_1'),
    selectedProject: vi.fn(() => ({ id: 'proj_1', name: 'Acme workspace', slug: 'acme-workspace' })),
    projectRunItems: vi.fn(summary => summary.runs || []),
    projectTargetItems: vi.fn(summary => summary.targets || []),
    projectFindingItems: vi.fn(() => [{ id: 'finding_1', title: 'Open redirect', severity: 'high' }]),
    projectArtifactItems: vi.fn(summary => summary.artifacts || []),
    projectArtifactDetail: vi.fn(item => item.workspace_path || item.kind || 'artifact'),
    formatDate: vi.fn(value => String(value || '')),
    bindProjectRuntimePressable: vi.fn(),
    emptyProjectPanel: vi.fn((text) => {
      const node = document.createElement('div')
      node.className = 'project-empty'
      node.textContent = text
      return node
    }),
    renderProjectExplorer: vi.fn(),
    setProjectWorkspaceMessage: vi.fn(),
    downloadUrlAsAttachment: vi.fn(),
    logClientError: vi.fn(),
    projectProvenanceSummaryElement: sharedUi?.projectProvenanceSummaryElement,
    ...overrides,
  }
}

const summary = {
  project: { id: 'proj_1', name: 'Acme workspace' },
  runs: [{
    id: 'run_1',
    command: 'nmap example.test',
    started: '2026-06-04T10:00:00Z',
    provenance: { origin: 'manual', confidence: 1.0 },
  }],
  targets: [{
    id: 'target_1',
    value: 'example.test',
    type: 'domain',
    provenance: { origin: 'manual', confidence: 1.0 },
  }],
  artifacts: [{ id: 'artifact_1', display_name: 'evidence.txt', workspace_path: 'reports/evidence.txt' }],
}

describe('project report controller', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    document.body.replaceChildren()
    delete globalThis.DarklabProjectReport
    delete globalThis.DarklabProjectSharedUi
    delete globalThis.activeTeamScopeCan
    delete globalThis.teamScopeDeniedMessage
    delete globalThis.enhanceAppSelects
  })

  it('loads the draft and renders the report editor with preview/export actions', async () => {
    const { reportApi } = loadReportModule()
    const apiFetch = vi.fn(async () => apiResponse({
      report: {
        updated: '2026-06-04T12:00:00Z',
        draft: {
          metadata: { engagement_name: 'Acme engagement' },
          selection: { run_ids: ['run_1'] },
          export: { redaction_mode: 'redacted' },
        },
      },
      templates: [{ id: 'standard', label: 'Standard', sections: [{ type: 'cover', title: 'Cover', enabled: true }] }],
    }))
    const controller = reportApi.createProjectReportController(makeContext(apiFetch))

    await controller.load('proj_1', { render: false })
    const container = document.createElement('div')
    controller.renderReport(container, 'proj_1', summary)

    expect(apiFetch).toHaveBeenCalledWith('/projects/proj_1/report', { cache: 'no-store' })
    expect(container.querySelector('[data-project-report-metadata="engagement_name"]').value).toBe('Acme engagement')
    const dateRange = container.querySelector('[data-project-report-metadata="date_range"]')
    expect(dateRange.placeholder).toBe('2026-06-01 to 2026-06-05')
    expect(dateRange.title).toContain('YYYY-MM-DD to YYYY-MM-DD')
    expect(container.querySelector('[data-project-report-selection="run_ids"]').checked).toBe(true)
    expect(container.querySelector('[data-project-report-action="save"]').textContent).toBe('Save draft')
    expect(container.querySelector('[data-project-report-action="reload"]').textContent).toBe('Reload saved')
    expect(container.querySelector('[data-project-report-template]')).toBeNull()
    expect(container.querySelector('[data-project-report-action="preview"]').textContent).toBe('Preview')
    expect(container.querySelector('[data-project-report-action="export"]').textContent).toBe('Export archive')
    expect(container.querySelector('.project-provenance-summary')?.textContent).toContain('manual (2)')

    const renderProjectMobileDetail = vi.fn()
    const mobileApiFetch = vi.fn(async () => apiResponse({
      report: {
        updated: '2026-06-04T12:30:00Z',
        draft: { metadata: { engagement_name: 'Mobile engagement' } },
      },
      templates: [],
    }))
    const mobileController = reportApi.createProjectReportController(makeContext(mobileApiFetch, {
      mobileView: vi.fn(() => 'detail'),
      renderProjectMobileDetail,
    }))
    const mobileHost = document.createElement('div')
    mobileHost.appendChild(mobileController.renderMobileReportTab('proj_mobile', summary))
    expect(mobileHost.textContent).toContain('Loading report draft...')
    await vi.waitFor(() => {
      expect(renderProjectMobileDetail).toHaveBeenCalled()
    })
    const loadedMobileHost = document.createElement('div')
    loadedMobileHost.appendChild(mobileController.renderMobileReportTab('proj_mobile', summary))
    expect(loadedMobileHost.querySelector('[data-project-report-metadata="engagement_name"]').value).toBe('Mobile engagement')
    expect(loadedMobileHost.querySelector('[data-project-report-selection="run_ids"]')).not.toBeNull()
    expect(loadedMobileHost.querySelector(
      '[data-project-report-action="selection-all"][data-selection-key="run_ids"]',
    )).not.toBeNull()
    expect(loadedMobileHost.querySelector('[data-project-report-action="preview"]')).not.toBeNull()

    const sharedUi = globalThis.DarklabProjectSharedUi?.createProjectSharedUiController?.({})
    const legacySummary = sharedUi.projectProvenanceSummary(
      {
        package_format_version: 1,
        provenance: {
          schema_version: 1,
          sources: {
            project_links: {
              origin_sources: [],
              note: 'Project-link origin details were not recorded in this older package.',
            },
          },
        },
      },
      { fallbackKind: 'evidence_package' },
    )
    const sourceChip = legacySummary.chips.find(chip => chip.label.startsWith('source:'))
    expect(sourceChip.label).toBe('source: not recorded')
    expect(sourceChip.title).toContain('older package')
    const row = sharedUi.itemRow({ title: 'Legacy package', chips: legacySummary.chips })
    const renderedChips = Array.from(row.querySelectorAll('.project-explorer-metadata-chip[title]'))
    expect(renderedChips.map(chip => chip.textContent)).toEqual(['provenance', 'source: not recorded'])
    expect(renderedChips[0].title).toContain('evidence package')
    expect(renderedChips[1].title).toContain('older package')
  })

  it('shows template choices only when more than one template is configured', async () => {
    const { reportApi } = loadReportModule()
    const apiFetch = vi.fn(async () => apiResponse({
      report: { updated: '', draft: {} },
      templates: [
        { id: 'standard', label: 'Standard engagement report', sections: [{ type: 'cover', title: 'Cover', enabled: true }] },
        { id: 'summary', label: 'Summary report', sections: [{ type: 'cover', title: 'Cover', enabled: true }] },
      ],
    }))
    const controller = reportApi.createProjectReportController(makeContext(apiFetch))

    await controller.load('proj_1', { render: false })
    const container = document.createElement('div')
    controller.renderReport(container, 'proj_1', summary)

    const template = container.querySelector('[data-project-report-template]')
    expect(template).not.toBeNull()
    expect(Array.from(template.options).map(option => option.textContent)).toEqual([
      'Choose a template',
      'Standard engagement report',
      'Summary report',
    ])
  })

  it('saves with the loaded updated token and the current draft fields', async () => {
    const { reportApi } = loadReportModule()
    const calls = []
    const apiFetch = vi.fn(async (url, options = {}) => {
      calls.push([url, options])
      if (options.method === 'POST') {
        return apiResponse({
          report: {
            updated: '2026-06-04T12:10:00Z',
            draft: JSON.parse(options.body).draft,
          },
        })
      }
      return apiResponse({
        report: {
          updated: '2026-06-04T12:00:00Z',
          draft: { metadata: { engagement_name: 'Old name' } },
        },
        templates: [],
      })
    })
    const ctx = makeContext(apiFetch)
    const controller = reportApi.createProjectReportController(ctx)
    await controller.load('proj_1', { render: false })
    const container = document.createElement('div')
    document.body.appendChild(container)
    controller.renderReport(container, 'proj_1', summary)

    const input = container.querySelector('[data-project-report-metadata="engagement_name"]')
    input.value = 'New report name'
    controller.handleInput({ target: input })
    const executiveSummaryToggle = container.querySelector('[data-project-report-section-toggle="1"]')
    executiveSummaryToggle.checked = false
    controller.handleChange({ target: executiveSummaryToggle })
    const save = container.querySelector('[data-project-report-action="save"]')
    await controller.handleClick({ target: save, preventDefault: vi.fn() })

    const saveBody = JSON.parse(calls.find(([url, options]) => url === '/projects/proj_1/report' && options.method === 'POST')[1].body)
    expect(calls.find(([url, options]) => url === '/projects/proj_1/report' && options.method === 'POST')[1].headers)
      .toEqual(expect.objectContaining({ 'Content-Type': 'application/json' }))
    expect(saveBody.expected_updated).toBe('2026-06-04T12:00:00Z')
    expect(saveBody.draft.metadata.engagement_name).toBe('New report name')
    expect(saveBody.draft.sections[1].enabled).toBe(false)
    expect(ctx.setProjectWorkspaceMessage).toHaveBeenCalledWith('Report draft saved.')

    const redaction = container.querySelector('[data-project-report-export="redaction_mode"]')
    const staleRoot = document.createElement('div')
    staleRoot.dataset.projectReportRoot = 'proj_1'
    staleRoot.innerHTML = `
      <select data-project-report-export="redaction_mode"><option value="redacted" selected>Redacted</option></select>
      <input type="checkbox" data-project-report-export="include_private_notes">
    `
    document.body.insertBefore(staleRoot, container)
    controller.stateFor('proj_1').preview = { html: '<main>Old redacted preview</main>' }
    redaction.value = 'raw'
    controller.handleChange({ target: redaction })
    await vi.waitFor(() => {
      expect(calls.some(([url, options]) => url === '/projects/proj_1/report/preview' && options.method === 'POST')).toBe(true)
    })
    const previewBody = JSON.parse(calls.find(([url, options]) => (
      url === '/projects/proj_1/report/preview' && options.method === 'POST'
    ))[1].body)
    expect(calls.find(([url, options]) => url === '/projects/proj_1/report/preview' && options.method === 'POST')[1].headers)
      .toEqual(expect.objectContaining({ 'Content-Type': 'application/json' }))
    expect(previewBody.draft.export.redaction_mode).toBe('raw')
  })

  it('clears stale preview output and confirms dirty reloads when editing report metadata', async () => {
    const { reportApi } = loadReportModule()
    const showConfirm = vi.fn(async () => 'cancel')
    const apiFetch = vi.fn(async () => apiResponse({
      report: {
        updated: '2026-06-04T12:00:00Z',
        draft: { metadata: { engagement_name: 'Old name' } },
      },
      templates: [],
    }))
    const controller = reportApi.createProjectReportController(makeContext(apiFetch, { showConfirm }))
    await controller.load('proj_1', { render: false })
    const st = controller.stateFor('proj_1')
    st.preview = { html: '<main>Old preview</main>' }

    const container = document.createElement('div')
    document.body.appendChild(container)
    controller.renderReport(container, 'proj_1', summary)
    expect(container.querySelector('.project-report-preview-frame')).not.toBeNull()
    expect(container.querySelector('[data-project-report-action="print"]').disabled).toBe(false)

    const input = container.querySelector('[data-project-report-metadata="engagement_name"]')
    input.value = 'Current report name'
    controller.handleInput({ target: input })

    expect(st.preview).toBeNull()
    expect(container.querySelector('.project-report-preview-frame')).toBeNull()
    expect(container.querySelector('[data-project-report-action="print"]').disabled).toBe(true)
    expect(container.textContent).toContain('Preview the report to render the current draft.')

    await controller.handleClick({
      target: container.querySelector('[data-project-report-action="reload"]'),
      preventDefault: vi.fn(),
    })
    expect(showConfirm).toHaveBeenCalledWith(expect.objectContaining({
      tone: 'warning',
      actions: expect.arrayContaining([
        expect.objectContaining({ id: 'cancel' }),
        expect.objectContaining({ id: 'reload' }),
      ]),
    }))
    expect(apiFetch).toHaveBeenCalledTimes(1)
    expect(st.dirty).toBe(true)

    showConfirm.mockResolvedValueOnce('reload')
    await controller.handleClick({
      target: container.querySelector('[data-project-report-action="reload"]'),
      preventDefault: vi.fn(),
    })
    const reloaded = controller.stateFor('proj_1')
    expect(apiFetch).toHaveBeenCalledTimes(2)
    expect(reloaded.dirty).toBe(false)
    expect(reloaded.draft.metadata.engagement_name).toBe('Old name')
  })

  it('keeps include-all selection dynamic when editing metadata', async () => {
    const { reportApi } = loadReportModule()
    const calls = []
    const apiFetch = vi.fn(async (url, options = {}) => {
      calls.push([url, options])
      if (options.method === 'POST') {
        return apiResponse({
          report: {
            updated: '2026-06-04T12:10:00Z',
            draft: JSON.parse(options.body).draft,
          },
        })
      }
      return apiResponse({ report: { updated: '2026-06-04T12:00:00Z', draft: {} }, templates: [] })
    })
    const controller = reportApi.createProjectReportController(makeContext(apiFetch))
    await controller.load('proj_1', { render: false })
    const container = document.createElement('div')
    document.body.appendChild(container)
    controller.renderReport(container, 'proj_1', summary)

    const input = container.querySelector('[data-project-report-metadata="engagement_name"]')
    input.value = 'Edited report'
    controller.handleInput({ target: input })
    await controller.handleClick({
      target: container.querySelector('[data-project-report-action="save"]'),
      preventDefault: vi.fn(),
    })

    const saveBody = JSON.parse(calls.find(([url, options]) => url === '/projects/proj_1/report' && options.method === 'POST')[1].body)
    expect(saveBody.draft.metadata.engagement_name).toBe('Edited report')
    expect(saveBody.draft.selection_modes).toEqual(expect.objectContaining({
      artifact_ids: 'all',
      finding_ids: 'all',
      run_ids: 'all',
      target_ids: 'all',
    }))
    expect(saveBody.draft.selection).toEqual(expect.objectContaining({
      artifact_ids: [],
      finding_ids: [],
      run_ids: [],
      target_ids: [],
    }))
  })

  it('renders paged report selectors without loading every finding or artifact', async () => {
    const { reportApi } = loadReportModule()
    const calls = []
    const apiFetch = vi.fn(async (url) => {
      calls.push(String(url))
      if (url === '/projects/proj_1/report') {
        return apiResponse({
          report: {
            updated: '',
            draft: {
              selection: { finding_ids: ['finding_off_page'] },
              selection_modes: { finding_ids: 'manual' },
            },
          },
          templates: [],
        })
      }
      if (url === '/projects/proj_1/runs?limit=50&offset=0') {
        return apiResponse({ runs: [{ id: 'run_page_1', command: 'nmap page 1' }], total: 1, limit: 50, offset: 0 })
      }
      if (url === '/projects/proj_1/runs?limit=50&offset=0&q=nuclei') {
        return apiResponse({ runs: [{ id: 'run_filtered_1', command: 'nuclei -u https://login.example' }], total: 1, limit: 50, offset: 0 })
      }
      if (url === '/projects/proj_1/targets?limit=50&offset=0') {
        return apiResponse({ targets: [{ id: 'target_page_1', value: 'page.example', type: 'domain' }], total: 1, limit: 50, offset: 0 })
      }
      if (url === '/projects/proj_1/targets?limit=50&offset=0&q=login') {
        return apiResponse({ targets: [{ id: 'target_filtered_1', value: 'login.example', type: 'domain' }], total: 2, limit: 50, offset: 0 })
      }
      if (url === '/projects/proj_1/findings?limit=50&offset=0&include_group_counts=0&orphan_filter=all') {
        return apiResponse({
          findings: [{ id: 'finding_page_1', title: 'Loaded page finding', severity: 'high' }],
          total: 75,
          limit: 50,
          offset: 0,
        })
      }
      if (url === '/projects/proj_1/findings?limit=50&offset=50&include_group_counts=0&orphan_filter=all') {
        return apiResponse({
          findings: [{ id: 'finding_page_2', title: 'Second page finding', severity: 'medium' }],
          total: 75,
          limit: 50,
          offset: 50,
        })
      }
      if (url === '/projects/proj_1/findings?limit=50&offset=0&include_group_counts=0&orphan_filter=all&q=redirect') {
        return apiResponse({
          findings: [{ id: 'finding_filtered_1', title: 'Open redirect on login', severity: 'medium' }],
          total: 1,
          limit: 50,
          offset: 0,
        })
      }
      if (url === '/projects/proj_1/artifacts?limit=50&offset=0') {
        return apiResponse({
          artifacts: [{ id: 'artifact_page_1', display_name: 'page-evidence.txt' }],
          total: 1,
          limit: 50,
          offset: 0,
        })
      }
      if (url === '/projects/proj_1/artifacts?limit=50&offset=0&q=evidence') {
        return apiResponse({
          artifacts: [{ id: 'artifact_filtered_1', display_name: 'filtered-evidence.txt' }],
          total: 1,
          limit: 50,
          offset: 0,
        })
      }
      return apiResponse({})
    })
    const loadProjectFindings = vi.fn()
    const loadAllProjectArtifacts = vi.fn()
    const controller = reportApi.createProjectReportController(makeContext(apiFetch, {
      projectFindingItems: vi.fn(() => []),
      projectArtifactItems: vi.fn(() => []),
      loadProjectFindings,
      loadAllProjectArtifacts,
    }))
    await controller.load('proj_1', { render: false })
    const container = document.createElement('div')
    controller.renderReport(container, 'proj_1', {
      ...summary,
      counts: { runs: 1, targets: 1, findings: 75, artifacts: 1 },
      runs: [],
      targets: [],
      artifacts: [],
    })

    expect(container.textContent).toContain('Loading findings...')
    await vi.waitFor(() => {
      expect(calls).toContain('/projects/proj_1/findings?limit=50&offset=0&include_group_counts=0&orphan_filter=all')
      expect(controller.stateFor('proj_1').selectionPages.finding_ids.loaded).toBe(true)
    })

    const loadedContainer = document.createElement('div')
    controller.renderReport(loadedContainer, 'proj_1', {
      ...summary,
      counts: { runs: 1, targets: 1, findings: 75, artifacts: 1 },
      runs: [],
      targets: [],
      artifacts: [],
    })
    expect(loadProjectFindings).not.toHaveBeenCalled()
    expect(loadAllProjectArtifacts).not.toHaveBeenCalled()
    expect(loadedContainer.textContent).toContain('Loaded page finding')
    expect(loadedContainer.textContent).not.toContain('Second page finding')
    expect(loadedContainer.textContent).toContain('1 selected; showing 1-1 of 75.')
    const loadedSummary = loadedContainer.querySelector('.project-report-selection-summary')
    expect(loadedSummary?.getAttribute('aria-live')).toBe('polite')
    expect(loadedSummary?.getAttribute('aria-atomic')).toBe('true')
    expect(loadedContainer.textContent).toContain('Selected findings')
    expect(loadedContainer.textContent).toContain('Not loaded yet: finding_off_page')
    const pageFinding = loadedContainer.querySelector('[data-project-report-selection="finding_ids"][value="finding_page_1"]')
    pageFinding.checked = true
    controller.handleChange({ target: pageFinding })
    expect(controller.stateFor('proj_1').draft.selection.finding_ids).toEqual(['finding_off_page', 'finding_page_1'])
    const selectedSummary = document.createElement('div')
    controller.renderReport(selectedSummary, 'proj_1', {
      ...summary,
      counts: { runs: 1, targets: 1, findings: 75, artifacts: 1 },
      runs: [],
      targets: [],
      artifacts: [],
    })
    expect(selectedSummary.textContent).toContain('Loaded page finding')
    expect(selectedSummary.textContent).toContain('high')
    expect(selectedSummary.textContent).toContain('Not loaded yet: finding_off_page')

    await controller.handleClick({
      target: loadedContainer.querySelector('[data-project-report-action="selection-next"][data-selection-key="finding_ids"]'),
      preventDefault: vi.fn(),
    })
    const secondPage = document.createElement('div')
    controller.renderReport(secondPage, 'proj_1', {
      ...summary,
      counts: { runs: 1, targets: 1, findings: 75, artifacts: 1 },
      runs: [],
      targets: [],
      artifacts: [],
    })
    expect(secondPage.textContent).toContain('Second page finding')
    expect(controller.stateFor('proj_1').draft.selection.finding_ids).toEqual(['finding_off_page', 'finding_page_1'])

    const targetSearch = secondPage.querySelector('[data-project-report-selection-filter="q"][data-selection-key="target_ids"]')
    targetSearch.value = 'login'
    controller.handleChange({ target: targetSearch })
    await vi.waitFor(() => {
      expect(calls).toContain('/projects/proj_1/targets?limit=50&offset=0&q=login')
      expect(controller.stateFor('proj_1').selectionPages.target_ids.items[0].id).toBe('target_filtered_1')
    })
    expect(controller.stateFor('proj_1').draft.selection_filters.target_ids).toEqual(expect.objectContaining({ q: 'login' }))
    expect(controller.stateFor('proj_1').draft.selection_modes.target_ids).toBe('all')
    expect(controller.stateFor('proj_1').draft.selection.target_ids).toEqual([])
    const filteredTargets = document.createElement('div')
    controller.renderReport(filteredTargets, 'proj_1', {
      ...summary,
      counts: { runs: 1, targets: 2, findings: 75, artifacts: 1 },
      runs: [],
      targets: [],
      artifacts: [],
    })
    expect(filteredTargets.textContent).toContain('All matching 2 selected')
    expect(filteredTargets.textContent).toContain('login.example')

    const findingSearch = filteredTargets.querySelector('[data-project-report-selection-filter="q"][data-selection-key="finding_ids"]')
    findingSearch.value = 'redirect'
    controller.handleInput({ target: findingSearch })
    expect(controller.stateFor('proj_1').draft.selection_filters.finding_ids).toEqual(expect.objectContaining({ q: 'redirect' }))
    await vi.waitFor(() => {
      expect(calls).toContain('/projects/proj_1/findings?limit=50&offset=0&include_group_counts=0&orphan_filter=all&q=redirect')
      expect(controller.stateFor('proj_1').selectionPages.finding_ids.items[0].id).toBe('finding_filtered_1')
    })
    const filteredFindings = document.createElement('div')
    controller.renderReport(filteredFindings, 'proj_1', {
      ...summary,
      counts: { runs: 1, targets: 2, findings: 75, artifacts: 1 },
      runs: [],
      targets: [],
      artifacts: [],
    })
    expect(filteredFindings.textContent).toContain('2 selected; showing 1 available')
    expect(filteredFindings.textContent).toContain('Open redirect on login')

    const runSearch = filteredFindings.querySelector('[data-project-report-selection-filter="q"][data-selection-key="run_ids"]')
    runSearch.value = 'nuclei'
    controller.handleInput({ target: runSearch })
    const artifactSearch = filteredFindings.querySelector('[data-project-report-selection-filter="q"][data-selection-key="artifact_ids"]')
    artifactSearch.value = 'evidence'
    controller.handleInput({ target: artifactSearch })
    expect(controller.stateFor('proj_1').draft.selection_filters.run_ids).toEqual({ q: 'nuclei' })
    expect(controller.stateFor('proj_1').draft.selection_filters.artifact_ids).toEqual({ q: 'evidence' })
    await vi.waitFor(() => {
      expect(calls).toContain('/projects/proj_1/runs?limit=50&offset=0&q=nuclei')
      expect(calls).toContain('/projects/proj_1/artifacts?limit=50&offset=0&q=evidence')
    })
  })

  it('ignores stale selector responses after a filter change starts a newer page load', async () => {
    const { reportApi } = loadReportModule()
    const staleTargets = deferred()
    const calls = []
    const renderProjectExplorer = vi.fn()
    const logClientError = vi.fn()
    const apiFetch = vi.fn((url) => {
      calls.push(String(url))
      if (url === '/projects/proj_1/report') {
        return Promise.resolve(apiResponse({ report: { updated: '', draft: {} }, templates: [] }))
      }
      if (url === '/projects/proj_1/targets?limit=50&offset=0') {
        return staleTargets.promise
      }
      if (url === '/projects/proj_1/targets?limit=50&offset=0&q=login') {
        return Promise.resolve(apiResponse({
          targets: [{ id: 'target_filtered_1', value: 'login.example', type: 'domain' }],
          total: 1,
          limit: 50,
          offset: 0,
        }))
      }
      if (url.includes('/runs?') || url.includes('/findings?') || url.includes('/artifacts?')) {
        return Promise.resolve(apiResponse({ runs: [], findings: [], artifacts: [], total: 0, limit: 50, offset: 0 }))
      }
      return Promise.resolve(apiResponse({}))
    })
    const controller = reportApi.createProjectReportController(makeContext(apiFetch, {
      renderProjectExplorer,
      logClientError,
      projectRunItems: vi.fn(() => []),
      projectTargetItems: vi.fn(() => []),
      projectArtifactItems: vi.fn(() => []),
      projectFindingItems: vi.fn(() => []),
    }))
    await controller.load('proj_1', { render: false })
    const container = document.createElement('div')
    controller.renderReport(container, 'proj_1', {
      ...summary,
      counts: { runs: 0, targets: 2, findings: 0, artifacts: 0 },
      runs: [],
      targets: [],
      artifacts: [],
    })

    await vi.waitFor(() => {
      expect(calls).toContain('/projects/proj_1/targets?limit=50&offset=0')
    })
    const targetSearch = container.querySelector('[data-project-report-selection-filter="q"][data-selection-key="target_ids"]')
    targetSearch.value = 'login'
    controller.handleChange({ target: targetSearch })
    await vi.waitFor(() => {
      expect(controller.stateFor('proj_1').selectionPages.target_ids.items[0].id).toBe('target_filtered_1')
    })
    renderProjectExplorer.mockClear()

    staleTargets.resolve(apiResponse({
      targets: [{ id: 'target_stale_1', value: 'stale.example', type: 'domain' }],
      total: 1,
      limit: 50,
      offset: 0,
    }))
    await Promise.resolve()
    await Promise.resolve()

    expect(controller.stateFor('proj_1').selectionPages.target_ids.items[0].id).toBe('target_filtered_1')
    expect(renderProjectExplorer).not.toHaveBeenCalled()
    expect(logClientError).not.toHaveBeenCalled()

    const failingLogClientError = vi.fn()
    const failingApiFetch = vi.fn((url) => {
      if (url === '/projects/proj_log/report') {
        return Promise.resolve(apiResponse({ report: { updated: '', draft: {} }, templates: [] }))
      }
      if (url === '/projects/proj_log/runs?limit=50&offset=0&q=secret-search') {
        return Promise.reject(new Error('network failed'))
      }
      return Promise.resolve(apiResponse({ targets: [], findings: [], artifacts: [], total: 0, limit: 50, offset: 0 }))
    })
    const failingController = reportApi.createProjectReportController(makeContext(failingApiFetch, {
      logClientError: failingLogClientError,
      projectRunItems: vi.fn(() => []),
      projectTargetItems: vi.fn(() => []),
      projectArtifactItems: vi.fn(() => []),
      projectFindingItems: vi.fn(() => []),
    }))
    await failingController.load('proj_log', { render: false })
    failingController.stateFor('proj_log').draft.selection_filters.run_ids = { q: 'secret-search' }
    const failingContainer = document.createElement('div')
    failingController.renderReport(failingContainer, 'proj_log', {
      project: { id: 'proj_log', name: 'Logging project' },
      counts: { runs: 1, targets: 0, findings: 0, artifacts: 0 },
      runs: [],
      targets: [],
      artifacts: [],
    })
    await vi.waitFor(() => {
      expect(failingLogClientError).toHaveBeenCalledWith(
        'failed to load report selector page',
        expect.any(Error),
        expect.objectContaining({
          selection_key: 'run_ids',
          offset: 0,
          limit: 50,
          filter_fields: ['q'],
          filter_active: { q: true },
          has_active_filter: true,
        }),
      )
    })
    expect(JSON.stringify(failingLogClientError.mock.calls[0][2])).not.toContain('secret-search')
  })

  it('keeps all-mode selections checked across pages when one item is excluded', async () => {
    const { reportApi } = loadReportModule()
    const apiFetch = vi.fn(async (url) => {
      if (url === '/projects/proj_1/report') {
        return apiResponse({ report: { updated: '', draft: {} }, templates: [] })
      }
      if (url === '/projects/proj_1/findings?limit=50&offset=0&include_group_counts=0&orphan_filter=all') {
        return apiResponse({
          findings: [{ id: 'finding_page_1', title: 'First page finding', severity: 'high' }],
          total: 75,
          limit: 50,
          offset: 0,
        })
      }
      if (url === '/projects/proj_1/findings?limit=50&offset=50&include_group_counts=0&orphan_filter=all') {
        return apiResponse({
          findings: [{ id: 'finding_page_2', title: 'Second page finding', severity: 'medium' }],
          total: 75,
          limit: 50,
          offset: 50,
        })
      }
      return apiResponse({ runs: [], targets: [], artifacts: [], total: 0, limit: 50, offset: 0 })
    })
    const controller = reportApi.createProjectReportController(makeContext(apiFetch, {
      projectRunItems: vi.fn(() => []),
      projectTargetItems: vi.fn(() => []),
      projectArtifactItems: vi.fn(() => []),
      projectFindingItems: vi.fn(() => []),
    }))
    await controller.load('proj_1', { render: false })
    const container = document.createElement('div')
    document.body.appendChild(container)
    controller.renderReport(container, 'proj_1', {
      ...summary,
      counts: { runs: 0, targets: 0, findings: 75, artifacts: 0 },
      runs: [],
      targets: [],
      artifacts: [],
    })
    await vi.waitFor(() => {
      expect(controller.stateFor('proj_1').selectionPages.finding_ids.loaded).toBe(true)
    })

    const firstPage = document.createElement('div')
    document.body.appendChild(firstPage)
    controller.renderReport(firstPage, 'proj_1', {
      ...summary,
      counts: { runs: 0, targets: 0, findings: 75, artifacts: 0 },
      runs: [],
      targets: [],
      artifacts: [],
    })
    await controller.handleClick({
      target: firstPage.querySelector('[data-project-report-action="selection-all"][data-selection-key="finding_ids"]'),
      preventDefault: vi.fn(),
    })
    expect(controller.stateFor('proj_1').draft.selection_modes.finding_ids).toBe('all')
    expect(controller.stateFor('proj_1').draft.selection_exclude_ids.finding_ids).toEqual([])

    await controller.handleClick({
      target: firstPage.querySelector('[data-project-report-action="selection-next"][data-selection-key="finding_ids"]'),
      preventDefault: vi.fn(),
    })
    const secondPage = document.createElement('div')
    document.body.appendChild(secondPage)
    controller.renderReport(secondPage, 'proj_1', {
      ...summary,
      counts: { runs: 0, targets: 0, findings: 75, artifacts: 0 },
      runs: [],
      targets: [],
      artifacts: [],
    })
    const secondFinding = secondPage.querySelector('[data-project-report-selection="finding_ids"][value="finding_page_2"]')
    expect(secondFinding.checked).toBe(true)
    secondFinding.checked = false
    controller.handleChange({ target: secondFinding })
    expect(controller.stateFor('proj_1').draft.selection_modes.finding_ids).toBe('all')
    expect(controller.stateFor('proj_1').draft.selection.finding_ids).toEqual([])
    expect(controller.stateFor('proj_1').draft.selection_exclude_ids.finding_ids).toEqual(['finding_page_2'])

    await controller.handleClick({
      target: secondPage.querySelector('[data-project-report-action="selection-prev"][data-selection-key="finding_ids"]'),
      preventDefault: vi.fn(),
    })
    const backToFirst = document.createElement('div')
    document.body.appendChild(backToFirst)
    controller.renderReport(backToFirst, 'proj_1', {
      ...summary,
      counts: { runs: 0, targets: 0, findings: 75, artifacts: 0 },
      runs: [],
      targets: [],
      artifacts: [],
    })
    expect(backToFirst.querySelector('[data-project-report-selection="finding_ids"][value="finding_page_1"]').checked).toBe(true)
    expect(backToFirst.textContent).toContain('All 74 selected')
    expect(backToFirst.textContent).toContain('Excluded findings')
    expect(backToFirst.textContent).toContain('Second page finding')
    expect(backToFirst.textContent).toContain('medium')
  })

  it('reloads filter-backed all selections with exclusions and preserves them on later saves', async () => {
    const { reportApi } = loadReportModule()
    const calls = []
    let savedDraft = {
      metadata: { engagement_name: 'Saved report' },
    }
    const apiFetch = vi.fn(async (url, options = {}) => {
      calls.push([String(url), options])
      if (url === '/projects/proj_1/report' && options.method === 'POST') {
        savedDraft = JSON.parse(options.body).draft
        return apiResponse({
          report: {
            updated: '2026-06-04T13:00:00Z',
            draft: savedDraft,
          },
        })
      }
      if (url === '/projects/proj_1/report') {
        return apiResponse({
          report: {
            updated: '2026-06-04T12:00:00Z',
            draft: savedDraft,
          },
          templates: [],
        })
      }
      if (url === '/projects/proj_1/findings?limit=50&offset=0&include_group_counts=0&orphan_filter=all') {
        return apiResponse({
          findings: [{ id: 'finding_page_1', title: 'First page finding', severity: 'high' }],
          total: 75,
          limit: 50,
          offset: 0,
        })
      }
      if (url === '/projects/proj_1/findings?limit=50&offset=0&include_group_counts=0&orphan_filter=all&q=redirect') {
        return apiResponse({
          findings: [{ id: 'finding_page_1', title: 'Redirect finding page one', severity: 'high' }],
          total: 75,
          limit: 50,
          offset: 0,
        })
      }
      if (url === '/projects/proj_1/findings?limit=50&offset=50&include_group_counts=0&orphan_filter=all&q=redirect') {
        return apiResponse({
          findings: [{ id: 'finding_page_2', title: 'Redirect finding page two', severity: 'medium' }],
          total: 75,
          limit: 50,
          offset: 50,
        })
      }
      return apiResponse({ runs: [], targets: [], artifacts: [], total: 0, limit: 50, offset: 0 })
    })
    const controller = reportApi.createProjectReportController(makeContext(apiFetch, {
      projectRunItems: vi.fn(() => []),
      projectTargetItems: vi.fn(() => []),
      projectArtifactItems: vi.fn(() => []),
      projectFindingItems: vi.fn(() => []),
    }))
    await controller.load('proj_1', { render: false })
    const firstPage = document.createElement('div')
    document.body.appendChild(firstPage)
    controller.renderReport(firstPage, 'proj_1', {
      ...summary,
      counts: { runs: 0, targets: 0, findings: 75, artifacts: 0 },
      runs: [],
      targets: [],
      artifacts: [],
    })
    await vi.waitFor(() => {
      expect(controller.stateFor('proj_1').selectionPages.finding_ids.loaded).toBe(true)
    })
    const search = firstPage.querySelector('[data-project-report-selection-filter="q"][data-selection-key="finding_ids"]')
    search.value = 'redirect'
    controller.handleInput({ target: search })
    await vi.waitFor(() => {
      expect(calls.map(([url]) => url)).toContain(
        '/projects/proj_1/findings?limit=50&offset=0&include_group_counts=0&orphan_filter=all&q=redirect',
      )
      expect(controller.stateFor('proj_1').selectionPages.finding_ids.items[0].id).toBe('finding_page_1')
    })
    const filteredFirstPage = document.createElement('div')
    document.body.appendChild(filteredFirstPage)
    controller.renderReport(filteredFirstPage, 'proj_1', {
      ...summary,
      counts: { runs: 0, targets: 0, findings: 75, artifacts: 0 },
      runs: [],
      targets: [],
      artifacts: [],
    })
    await controller.handleClick({
      target: filteredFirstPage.querySelector('[data-project-report-action="selection-all"][data-selection-key="finding_ids"]'),
      preventDefault: vi.fn(),
    })
    await controller.handleClick({
      target: filteredFirstPage.querySelector('[data-project-report-action="selection-next"][data-selection-key="finding_ids"]'),
      preventDefault: vi.fn(),
    })
    const filteredSecondPage = document.createElement('div')
    document.body.appendChild(filteredSecondPage)
    controller.renderReport(filteredSecondPage, 'proj_1', {
      ...summary,
      counts: { runs: 0, targets: 0, findings: 75, artifacts: 0 },
      runs: [],
      targets: [],
      artifacts: [],
    })
    const excludedFinding = filteredSecondPage.querySelector(
      '[data-project-report-selection="finding_ids"][value="finding_page_2"]',
    )
    expect(excludedFinding.checked).toBe(true)
    excludedFinding.checked = false
    controller.handleChange({ target: excludedFinding })
    await controller.handleClick({
      target: filteredSecondPage.querySelector('[data-project-report-action="save"]'),
      preventDefault: vi.fn(),
    })
    let saveBody = JSON.parse(
      calls.find(([url, options]) => url === '/projects/proj_1/report' && options.method === 'POST')[1].body,
    )
    expect(saveBody.draft.selection_modes.finding_ids).toBe('all')
    expect(saveBody.draft.selection_filters.finding_ids).toEqual(expect.objectContaining({ q: 'redirect' }))
    expect(saveBody.draft.selection_exclude_ids.finding_ids).toEqual(['finding_page_2'])
    expect(saveBody.draft.selection.finding_ids).toEqual([])

    const reloadRoot = document.createElement('div')
    document.body.appendChild(reloadRoot)
    controller.renderReport(reloadRoot, 'proj_1', {
      ...summary,
      counts: { runs: 0, targets: 0, findings: 75, artifacts: 0 },
      runs: [],
      targets: [],
      artifacts: [],
    })
    await controller.handleClick({
      target: reloadRoot.querySelector('[data-project-report-action="reload"]'),
      preventDefault: vi.fn(),
    })
    const reloadedFirstPage = document.createElement('div')
    document.body.appendChild(reloadedFirstPage)
    controller.renderReport(reloadedFirstPage, 'proj_1', {
      ...summary,
      counts: { runs: 0, targets: 0, findings: 75, artifacts: 0 },
      runs: [],
      targets: [],
      artifacts: [],
    })
    await vi.waitFor(() => {
      expect(controller.stateFor('proj_1').selectionPages.finding_ids.loaded).toBe(true)
    })
    const loadedFirstPage = document.createElement('div')
    document.body.appendChild(loadedFirstPage)
    controller.renderReport(loadedFirstPage, 'proj_1', {
      ...summary,
      counts: { runs: 0, targets: 0, findings: 75, artifacts: 0 },
      runs: [],
      targets: [],
      artifacts: [],
    })
    expect(loadedFirstPage.querySelector('[data-project-report-selection-filter="q"][data-selection-key="finding_ids"]').value)
      .toBe('redirect')
    expect(loadedFirstPage.querySelector('[data-project-report-selection="finding_ids"][value="finding_page_1"]').checked)
      .toBe(true)
    expect(loadedFirstPage.textContent).toContain('All matching 74 selected')

    await controller.handleClick({
      target: loadedFirstPage.querySelector('[data-project-report-action="selection-next"][data-selection-key="finding_ids"]'),
      preventDefault: vi.fn(),
    })
    const reloadedSecondPage = document.createElement('div')
    document.body.appendChild(reloadedSecondPage)
    controller.renderReport(reloadedSecondPage, 'proj_1', {
      ...summary,
      counts: { runs: 0, targets: 0, findings: 75, artifacts: 0 },
      runs: [],
      targets: [],
      artifacts: [],
    })
    expect(reloadedSecondPage.querySelector('[data-project-report-selection="finding_ids"][value="finding_page_2"]').checked)
      .toBe(false)

    const nameInput = reloadedSecondPage.querySelector('[data-project-report-metadata="engagement_name"]')
    nameInput.value = 'Renamed report'
    controller.handleInput({ target: nameInput })
    await controller.handleClick({
      target: reloadedSecondPage.querySelector('[data-project-report-action="save"]'),
      preventDefault: vi.fn(),
    })
    const saveCalls = calls.filter(([url, options]) => url === '/projects/proj_1/report' && options.method === 'POST')
    saveBody = JSON.parse(saveCalls.at(-1)[1].body)
    expect(saveBody.draft.metadata.engagement_name).toBe('Renamed report')
    expect(saveBody.draft.selection_modes.finding_ids).toBe('all')
    expect(saveBody.draft.selection_filters.finding_ids).toEqual(expect.objectContaining({ q: 'redirect' }))
    expect(saveBody.draft.selection_exclude_ids.finding_ids).toEqual(['finding_page_2'])
    expect(saveBody.draft.selection.finding_ids).toEqual([])
  })

  it('blocks view-only team members from save/raw controls without blocking preview or export', async () => {
    const { reportApi } = loadReportModule({
      activeTeamScopeCan: vi.fn(capability => capability !== 'mutate_projects'),
    })
    const calls = []
    const apiFetch = vi.fn(async (url, options = {}) => {
      calls.push([url, options])
      if (url.endsWith('/preview')) return apiResponse({ preview: { html: '<main>Preview</main>' } })
      return apiResponse({
        report: {
          updated: '2026-06-04T12:00:00Z',
          draft: { export: { redaction_mode: 'raw', include_private_notes: true } },
        },
        templates: [],
      })
    })
    const controller = reportApi.createProjectReportController(makeContext(apiFetch))
    await controller.load('proj_1', { render: false })
    const container = document.createElement('div')
    controller.renderReport(container, 'proj_1', summary)

    expect(container.querySelector('[data-project-report-action="save"]').disabled).toBe(true)
    expect(container.querySelector('[data-project-report-export="redaction_mode"]').disabled).toBe(true)
    expect(container.querySelector('[data-project-report-export="redaction_mode"]').value).toBe('redacted')
    expect(container.querySelector('[data-project-report-export="include_private_notes"]').disabled).toBe(true)
    expect(container.querySelector('[data-project-report-export="include_private_notes"]').checked).toBe(false)
    expect(container.querySelector('[data-project-report-action="preview"]').disabled).toBe(false)
    expect(container.querySelector('[data-project-report-action="export"]').disabled).toBe(false)
    expect(container.textContent).toContain("View-only team members can't change team projects")
    await controller.handleClick({
      target: container.querySelector('[data-project-report-action="preview"]'),
      preventDefault: vi.fn(),
    })
    const previewBody = JSON.parse(calls.find(([url, options]) => url === '/projects/proj_1/report/preview' && options.method === 'POST')[1].body)
    expect(previewBody.draft.export).toEqual({
      redaction_mode: 'redacted',
      include_private_notes: false,
    })
  })

  it('shows stale-save conflicts as report errors', async () => {
    const { reportApi } = loadReportModule()
    const apiFetch = vi.fn(async (url, options = {}) => {
      if (options.method === 'POST') {
        return apiResponse({ error: 'report draft changed; reload before saving' }, { ok: false })
      }
      return apiResponse({
        report: {
          updated: '2026-06-04T12:00:00Z',
          draft: { metadata: { engagement_name: 'Original report' } },
        },
        templates: [],
      })
    })
    const ctx = makeContext(apiFetch)
    const controller = reportApi.createProjectReportController(ctx)
    await controller.load('proj_1', { render: false })
    const container = document.createElement('div')
    document.body.appendChild(container)
    controller.renderReport(container, 'proj_1', summary)

    await controller.handleClick({
      target: container.querySelector('[data-project-report-action="save"]'),
      preventDefault: vi.fn(),
    })

    const st = controller.stateFor('proj_1')
    expect(st.error).toBe('report draft changed; reload before saving')
    expect(st.dirty).toBe(false)
    expect(ctx.setProjectWorkspaceMessage).not.toHaveBeenCalledWith('Report draft saved.')
    const rerendered = document.createElement('div')
    controller.renderReport(rerendered, 'proj_1', summary)
    expect(rerendered.querySelector('.project-report-message.is-error')?.textContent)
      .toBe('report draft changed; reload before saving')
  })

  it('reorders sections and preserves explicit empty selections', async () => {
    const { reportApi } = loadReportModule()
    const apiFetch = vi.fn(async () => apiResponse({
      report: { updated: '', draft: {} },
      templates: [],
    }))
    const ctx = makeContext(apiFetch)
    const controller = reportApi.createProjectReportController(ctx)
    await controller.load('proj_1', { render: false })
    const container = document.createElement('div')
    document.body.appendChild(container)
    controller.renderReport(container, 'proj_1', { ...summary, artifacts: [] })

    await vi.waitFor(() => {
      expect(controller.stateFor('proj_1').selectionPages.artifact_ids.loaded).toBe(true)
    })
    const loadedContainer = document.createElement('div')
    document.body.appendChild(loadedContainer)
    controller.renderReport(loadedContainer, 'proj_1', { ...summary, artifacts: [] })
    expect(loadedContainer.textContent).toContain('No artifacts available.')
    await controller.handleClick({
      target: loadedContainer.querySelector('[data-project-report-action="section-down"][data-section-index="0"]'),
      preventDefault: vi.fn(),
    })
    expect(controller.stateFor('proj_1').draft.sections.map(section => section.type).slice(0, 2)).toEqual([
      'executive_summary',
      'cover',
    ])

    await controller.handleClick({
      target: loadedContainer.querySelector('[data-project-report-action="selection-none"][data-selection-key="run_ids"]'),
      preventDefault: vi.fn(),
    })
    let st = controller.stateFor('proj_1')
    expect(st.draft.selection_modes.run_ids).toBe('manual')
    expect(st.draft.selection.run_ids).toEqual([])

    const afterNone = document.createElement('div')
    controller.renderReport(afterNone, 'proj_1', summary)
    expect(afterNone.querySelector('[data-project-report-selection="run_ids"]').checked).toBe(false)

    await controller.handleClick({
      target: afterNone.querySelector('[data-project-report-action="selection-all"][data-selection-key="run_ids"]'),
      preventDefault: vi.fn(),
    })
    st = controller.stateFor('proj_1')
    expect(st.draft.selection_modes.run_ids).toBe('all')
    expect(st.draft.selection.run_ids).toEqual([])
  })

  it('exports through the archive job and downloads through a ticket URL', async () => {
    vi.useFakeTimers()
    try {
      const { reportApi } = loadReportModule()
      const apiFetch = vi.fn(async (url, options = {}) => {
        if (url === '/projects/proj_1/report/export') {
          return apiResponse({ job: { id: 'job_1', status: 'queued', message: 'queued' } })
        }
        if (url === '/projects/proj_1/report/export-jobs/job_1') {
          return apiResponse({ job: { id: 'job_1', status: 'complete' } })
        }
        if (url === '/projects/proj_1/report/export-jobs/job_1/download-ticket') {
          return apiResponse({ url: '/downloads/report_ticket' })
        }
        return apiResponse({ report: { updated: '', draft: {} }, templates: [] })
      })
      const ctx = makeContext(apiFetch)
      const controller = reportApi.createProjectReportController(ctx)
      await controller.load('proj_1', { render: false })
      const container = document.createElement('div')
      document.body.appendChild(container)
      controller.renderReport(container, 'proj_1', summary)

      const exportButton = container.querySelector('[data-project-report-action="export"]')
      const exportPromise = controller.handleClick({ target: exportButton, preventDefault: vi.fn() })
      await vi.runOnlyPendingTimersAsync()
      await exportPromise

      expect(apiFetch).toHaveBeenCalledWith('/projects/proj_1/report/export', expect.objectContaining({ method: 'POST' }))
      expect(apiFetch).toHaveBeenCalledWith('/projects/proj_1/report/export', expect.objectContaining({
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }))
      expect(apiFetch).toHaveBeenCalledWith('/projects/proj_1/report/export-jobs/job_1', { cache: 'no-store' })
      expect(apiFetch).toHaveBeenCalledWith('/projects/proj_1/report/export-jobs/job_1/download-ticket', { method: 'POST', cache: 'no-store' })
      expect(ctx.downloadUrlAsAttachment).toHaveBeenCalledWith('/downloads/report_ticket', 'acme-workspace.zip', 'Report download started.')
    } finally {
      vi.useRealTimers()
    }
  })

  it('prints the current preview through the browser print flow', async () => {
    vi.useFakeTimers()
    try {
      const { reportApi } = loadReportModule()
      const apiFetch = vi.fn(async () => apiResponse({ report: { updated: '', draft: {} }, templates: [] }))
      const ctx = makeContext(apiFetch)
      const controller = reportApi.createProjectReportController(ctx)
      await controller.load('proj_1', { render: false })
      controller.stateFor('proj_1').preview = { html: '<!doctype html><title>Report</title><main>Ready</main>' }
      const container = document.createElement('div')
      document.body.appendChild(container)
      controller.renderReport(container, 'proj_1', summary)
      const printWindow = {
        document: { open: vi.fn(), write: vi.fn(), close: vi.fn() },
        focus: vi.fn(),
        print: vi.fn(),
      }
      vi.spyOn(window, 'open').mockReturnValue(printWindow)

      const printButton = container.querySelector('[data-project-report-action="print"]')
      await controller.handleClick({ target: printButton, preventDefault: vi.fn() })
      await vi.runOnlyPendingTimersAsync()

      expect(window.open).toHaveBeenCalledWith('', '_blank')
      expect(printWindow.document.write).toHaveBeenCalledWith('<!doctype html><title>Report</title><main>Ready</main>')
      expect(printWindow.print).toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
    }
  })
})
