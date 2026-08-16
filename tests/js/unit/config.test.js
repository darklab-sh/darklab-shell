// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { readFileSync } from 'fs'
import { resolve } from 'path'
import { fromDomScript, fromDomScripts } from './helpers/extract.js'

const CONFIG_SRC = readFileSync(resolve(process.cwd(), 'app/static/js/core/config.js'), 'utf8')
const LAZY_ASSETS_SRC = readFileSync(resolve(process.cwd(), 'app/static/js/core/lazy_assets.js'), 'utf8')

describe('frontend config bootstrap', () => {
  it('reads APP_CONFIG from the server-rendered bootstrap JSON', () => {
    const bootstrap = {
      app_name: 'darklab_shell',
      prompt_username: 'anon',
      prompt_domain: 'darklab.sh',
      recent_commands_limit: 50,
      welcome_char_ms: 18,
      welcome_jitter_ms: 12,
      welcome_post_cmd_ms: 650,
      welcome_inter_block_ms: 850,
      welcome_first_prompt_idle_ms: 1500,
      welcome_post_status_pause_ms: 500,
      welcome_sample_count: 5,
      welcome_status_labels: ['CONFIG', 'RUNNER', 'HISTORY', 'LIMITS', 'AUTOCOMPLETE'],
      welcome_hint_interval_ms: 4200,
      welcome_hint_rotations: 0,
      tour_enabled: true,
      tour_version: 1,
      tour_chapters: [{ id: 'running_commands', title: 'Running commands', summary: 'Run a command.' }],
      tour_chapter_count: 8,
      share_redaction_enabled: true,
      share_redaction_rules: [{ label: 'bearer token' }],
    }
    const document = {
      getElementById: (id) => id === 'app-config-json'
        ? { textContent: JSON.stringify(bootstrap) }
        : null,
    }
    const window = { logClientError: vi.fn() }
    const { APP_CONFIG } = fromDomScript('app/static/js/core/config.js', { document, window }, 'APP_CONFIG')

    expect(APP_CONFIG).toMatchObject({
      app_name: expect.any(String),
      prompt_username: expect.any(String),
      prompt_domain: expect.any(String),
      welcome_char_ms: expect.any(Number),
      welcome_jitter_ms: expect.any(Number),
      welcome_post_cmd_ms: expect.any(Number),
      welcome_inter_block_ms: expect.any(Number),
      welcome_first_prompt_idle_ms: expect.any(Number),
      welcome_post_status_pause_ms: expect.any(Number),
      welcome_sample_count: expect.any(Number),
      welcome_status_labels: expect.any(Array),
      welcome_hint_interval_ms: expect.any(Number),
      welcome_hint_rotations: expect.any(Number),
      tour_enabled: expect.any(Boolean),
      tour_version: expect.any(Number),
      tour_chapters: expect.any(Array),
      tour_chapter_count: expect.any(Number),
      share_redaction_enabled: expect.any(Boolean),
      share_redaction_rules: expect.any(Array),
    })
    expect(APP_CONFIG).toEqual(bootstrap)
    expect(window.APP_CONFIG).toBe(APP_CONFIG)
    expect(window.DarklabConfig.getAppConfig()).toBe(APP_CONFIG)
    expect(window.logClientError).toHaveBeenCalledWith('app config loaded', null, {
      event: 'APP_CONFIG_LOADED',
      level: 'info',
      source: 'app-config-json',
      workspace_enabled: false,
      lazy_asset_count: 0,
    })
    expect(window.DarklabConfig.setAppConfig({ app_name: 'updated' })).toEqual({ app_name: 'updated' })
    expect(window.APP_CONFIG).toEqual({ app_name: 'updated' })
  })

  it('falls back to an existing window APP_CONFIG object for non-template harnesses', () => {
    const bootstrap = {
      app_name: 'harness',
      recent_commands_limit: 3,
      workspace_enabled: true,
      lazy_asset_urls: { project_report: '/static/js/features/projects/project_report.js' },
    }
    const document = {
      getElementById: (id) => id === 'app-config-json'
        ? { textContent: '{"broken": ' }
        : null,
    }
    const window = { APP_CONFIG: bootstrap, logClientError: vi.fn() }
    const { APP_CONFIG } = fromDomScript('app/static/js/core/config.js', { document, window }, 'APP_CONFIG')

    expect(APP_CONFIG).toBe(bootstrap)
    expect(window.logClientError).toHaveBeenCalledWith(
      'failed to parse app config bootstrap',
      expect.any(SyntaxError),
      {
        event: 'APP_CONFIG_PARSE_FAILED',
        level: 'warning',
        source: 'app-config-json',
        fallback: 'window.APP_CONFIG',
        text_length: '{"broken": '.length,
      },
    )
    expect(window.logClientError).toHaveBeenCalledWith(
      'app config loaded',
      null,
      {
        event: 'APP_CONFIG_LOADED',
        level: 'info',
        source: 'window.APP_CONFIG',
        workspace_enabled: true,
        lazy_asset_count: 1,
      },
    )
  })

  it('does not hard-code server config defaults in config.js', () => {
    const forbiddenFragments = [
      'DEFAULT_SHARE_REDACTION_RULES',
      "app_name: '",
      'recent_commands_limit:',
      'max_output_lines:',
      'max_tabs:',
      'history_panel_limit:',
      'command_timeout_seconds:',
      'welcome_char_ms:',
      'welcome_status_labels:',
    ]

    forbiddenFragments.forEach((fragment) => {
      expect(CONFIG_SRC).not.toContain(fragment)
    })
  })

  it('lazy-loads rarely used modal controllers on first open', async () => {
    const appended = []
    const document = {
      documentElement: {},
      head: {
        appendChild: (node) => {
          appended.push(node)
        },
      },
      createElement: (tagName) => ({ tagName, dataset: {} }),
      getElementById: (id) => id === 'lazy-assets-json'
        ? {
            textContent: JSON.stringify({
              findings_board: {
                url: '/static/js/features/findings/findings_board_modal.js?v=board-hash',
                type: 'module',
              },
              atlas_tabs: {
                url: '/static/js/features/atlas/atlas_tabs.js?v=atlas-tabs-hash',
                type: 'module',
              },
              atlas_entity_row: {
                url: '/static/js/features/atlas/atlas_entity_row.js?v=atlas-row-hash',
                type: 'module',
              },
              atlas_entity_detail: {
                url: '/static/js/features/atlas/atlas_entity_detail.js?v=atlas-detail-hash',
                type: 'module',
              },
              atlas_overlay: {
                url: '/static/js/features/atlas/atlas_overlay.js?v=atlas-overlay-hash',
                type: 'module',
              },
              atlas_mobile: {
                url: '/static/js/features/atlas/atlas_mobile.js?v=atlas-mobile-hash',
                type: 'module',
              },
              findings_board_bridge: {
                url: '/static/js/features/findings/findings_board_bridge.js?v=board-bridge-hash',
                type: 'module',
              },
              project_activity: {
                url: '/static/js/features/projects/project_activity.js?v=activity-hash',
                type: 'module',
              },
              project_assessment_css: {
                url: '/static/css/features/project-assessment.css?v=assessment-css-hash',
                type: 'style',
              },
              project_assessment: {
                url: '/static/js/features/projects/project_assessment.js?v=assessment-hash',
                type: 'module',
              },
              project_overview: {
                url: '/static/js/features/projects/project_overview.js?v=overview-hash',
                type: 'module',
              },
              project_artifacts: {
                url: '/static/js/features/projects/project_artifacts.js?v=artifacts-hash',
                type: 'module',
              },
              project_web_surface: {
                url: '/static/js/features/projects/project_web_surface.js?v=web-surface-hash',
                type: 'module',
              },
              project_details: '/static/js/features/projects/project_details.js?v=details-hash',
              project_list: '/static/js/features/projects/project_list.js?v=list-hash',
              project_navigation: '/static/js/features/projects/project_navigation.js?v=navigation-hash',
              project_entity_editor: '/static/js/features/projects/project_entity_editor.js?v=entity-editor-hash',
              project_workspace_actions: '/static/js/features/projects/project_workspace_actions.js?v=actions-hash',
              project_workspace_shell: '/static/js/features/projects/project_workspace_shell.js?v=shell-hash',
              project_workspace_lifecycle: '/static/js/features/projects/project_workspace_lifecycle.js?v=lifecycle-hash',
              project_workspace_renderer: '/static/js/features/projects/project_workspace_renderer.js?v=renderer-hash',
              project_workspace_bootstrap: '/static/js/features/projects/project_workspace_bootstrap.js?v=bootstrap-hash',
              project_nested_sheets: '/static/js/features/projects/project_nested_sheets.js?v=nested-hash',
              project_workspace_events: '/static/js/features/projects/project_workspace_events.js?v=events-hash',
              project_targets: '/static/js/features/projects/project_targets.js?v=targets-hash',
              project_runs: '/static/js/features/projects/project_runs.js?v=runs-hash',
              project_mobile_compare: '/static/js/features/projects/project_mobile_compare.js?v=mobile-compare-hash',
              project_mobile_shell: '/static/js/features/projects/project_mobile_shell.js?v=mobile-shell-hash',
              project_mobile_detail: '/static/js/features/projects/project_mobile_detail.js?v=mobile-detail-hash',
              project_findings_data: '/static/js/features/projects/project_findings_data.js?v=findings-data-hash',
              project_filters: '/static/js/features/projects/project_filters.js?v=filters-hash',
              project_entities: '/static/js/features/projects/project_entities.js?v=entities-hash',
              project_findings: '/static/js/features/projects/project_findings.js?v=findings-hash',
              project_findings_board: '/static/js/features/projects/project_findings_board.js?v=findings-board-hash',
              project_packages: {
                url: '/static/js/features/projects/project_packages.js?v=packages-hash',
                type: 'module',
              },
              project_report: {
                url: '/static/js/features/projects/project_report.js?v=report-hash',
                type: 'module',
              },
              history_run_details: {
                url: '/static/js/features/history/history_run_details.js?v=history-details-hash',
                type: 'module',
              },
              pty_controller: {
                url: '/static/js/pty.js?v=pty-hash',
                type: 'module',
              },
              schedules_modal: {
                url: '/static/js/features/schedules/schedules_modal.js?v=schedules-hash',
                type: 'module',
              },
              status_monitor_core: {
                url: '/static/js/features/status-monitor/status_monitor_core.js?v=status-core-hash',
                type: 'module',
              },
              status_monitor_data: {
                url: '/static/js/features/status-monitor/status_monitor_data.js?v=status-data-hash',
                type: 'module',
              },
              status_monitor_resources: {
                url: '/static/js/features/status-monitor/status_monitor_resources.js?v=status-resources-hash',
                type: 'module',
              },
              status_monitor: {
                url: '/static/js/status_monitor.js?v=status-hash',
                type: 'module',
              },
              tour_modal: {
                url: '/static/js/tour_modal.js?v=tour-hash',
                type: 'module',
              },
              watchers_modal: {
                url: '/static/js/features/watchers/watchers_modal.js?v=watchers-hash',
                type: 'module',
              },
            }),
          }
        : id === 'atlas-mobile-root'
          ? {}
        : null,
    }
    const imported = []
    const appConfig = {}
    const window = {
      logClientError: vi.fn(),
      __darklabImportModule: vi.fn(async (url) => {
        imported.push(url)
        if (url.includes('/atlas_tabs.js')) {
          const DarklabAtlasTabs = {}
          window.DarklabAtlasTabs = DarklabAtlasTabs
          return { DarklabAtlasTabs }
        }
        if (url.includes('/atlas_entity_row.js')) {
          const DarklabAtlasEntityRow = {}
          window.DarklabAtlasEntityRow = DarklabAtlasEntityRow
          return { DarklabAtlasEntityRow }
        }
        if (url.includes('/atlas_entity_detail.js')) {
          const DarklabAtlasDetail = {}
          window.DarklabAtlasDetail = DarklabAtlasDetail
          return { DarklabAtlasDetail }
        }
        if (url.includes('/atlas_overlay.js')) {
          const DarklabAtlasOverlay = {}
          const openAtlas = vi.fn(async options => ({ atlas: options.source }))
          const openAtlasQuickLookup = vi.fn(async options => ({ lookup: options.value }))
          window.DarklabAtlasOverlay = DarklabAtlasOverlay
          window.openAtlas = openAtlas
          window.openAtlasQuickLookup = openAtlasQuickLookup
          return { DarklabAtlasOverlay, openAtlas, openAtlasQuickLookup }
        }
        if (url.includes('/atlas_mobile.js')) {
          const DarklabAtlasMobile = {}
          window.DarklabAtlasMobile = DarklabAtlasMobile
          return { DarklabAtlasMobile }
        }
        if (url.includes('/findings_board_modal.js')) {
          const openFindingsBoard = vi.fn(async options => ({ opened: options.source }))
          window.openFindingsBoard = openFindingsBoard
          return { openFindingsBoard }
        }
        if (url.includes('/status_monitor_core.js')) {
          const DarklabStatusMonitorCore = {}
          window.DarklabStatusMonitorCore = DarklabStatusMonitorCore
          return { DarklabStatusMonitorCore }
        }
        if (url.includes('/status_monitor_data.js')) {
          const DarklabStatusMonitorData = {}
          window.DarklabStatusMonitorData = DarklabStatusMonitorData
          return { DarklabStatusMonitorData }
        }
        if (url.includes('/status_monitor_resources.js')) {
          const DarklabStatusMonitorResources = {}
          window.DarklabStatusMonitorResources = DarklabStatusMonitorResources
          return { DarklabStatusMonitorResources }
        }
        if (url.includes('/status_monitor.js')) {
          const openStatusMonitor = vi.fn(async options => ({ status: options.source }))
          window.openStatusMonitor = openStatusMonitor
          return { openStatusMonitor }
        }
        if (url.includes('/tour_modal.js')) {
          const openTourModal = vi.fn(options => ({ tour: options.source }))
          window.openTourModal = openTourModal
          return { openTourModal }
        }
        if (url.includes('/history_run_details.js')) {
          const openHistoryRunDetails = vi.fn(run => ({ runId: run.id }))
          window.openHistoryRunDetails = openHistoryRunDetails
          return { openHistoryRunDetails }
        }
        if (url.includes('/project_report.js')) {
          const DarklabProjectReport = { createProjectReportController: vi.fn() }
          window.DarklabProjectReport = DarklabProjectReport
          return { DarklabProjectReport }
        }
        if (url.includes('/project_activity.js')) {
          const DarklabProjectActivity = { createProjectActivityController: vi.fn() }
          window.DarklabProjectActivity = DarklabProjectActivity
          return { DarklabProjectActivity }
        }
        if (url.includes('/project_assessment.js')) {
          const DarklabProjectAssessment = { createProjectAssessmentController: vi.fn() }
          window.DarklabProjectAssessment = DarklabProjectAssessment
          return { DarklabProjectAssessment }
        }
        if (url.includes('/project_overview.js')) {
          const DarklabProjectOverview = { createProjectOverviewController: vi.fn() }
          window.DarklabProjectOverview = DarklabProjectOverview
          return { DarklabProjectOverview }
        }
        if (url.includes('/project_artifacts.js')) {
          const DarklabProjectArtifacts = { createProjectArtifactsController: vi.fn() }
          window.DarklabProjectArtifacts = DarklabProjectArtifacts
          return { DarklabProjectArtifacts }
        }
        if (url.includes('/project_web_surface.js')) {
          const DarklabProjectWebSurface = { createProjectWebSurfaceController: vi.fn() }
          window.DarklabProjectWebSurface = DarklabProjectWebSurface
          return { DarklabProjectWebSurface }
        }
        if (url.includes('/project_packages.js')) {
          const DarklabProjectPackages = { createProjectPackagesController: vi.fn() }
          window.DarklabProjectPackages = DarklabProjectPackages
          return { DarklabProjectPackages }
        }
        if (url.includes('/pty.js')) {
          window.startInteractivePtyCommand = vi.fn(async (cmd, tabId) => ({ cmd, tabId }))
          window.attachInteractivePtyCommand = vi.fn(async (run, tabId) => ({ run, tabId }))
          window.isInteractivePtyCommand = vi.fn((cmd) => cmd.includes('--interactive'))
        }
        if (url.includes('/schedules_modal.js')) {
          const openSchedulesModal = vi.fn(async options => ({ schedule: options.scheduleId }))
          window.openSchedulesModal = openSchedulesModal
          return { openSchedulesModal }
        }
        if (url.includes('/watchers_modal.js')) {
          const openWatchersModal = vi.fn(async options => ({ watcher: options.watcherId }))
          window.openWatchersModal = openWatchersModal
          return { openWatchersModal }
        }
      }),
    }

    fromDomScripts(
      ['app/static/js/core/lazy_assets.js'],
      { document, window, getAppConfig: () => appConfig },
      'window',
    )
    window.emitUiEvent = (name, detail) => {
      events.push({ name, detail })
    }

    const openPromise = window.openFindingsBoard({ source: 'unit' })
    await expect(openPromise).resolves.toEqual({ opened: 'unit' })
    expect(window.openFindingsBoard).toHaveBeenCalledWith({ source: 'unit' })

    const atlasPromise = window.openAtlas({ source: 'rail' })
    await vi.waitFor(() => expect(imported).toEqual([
      '/static/js/features/findings/findings_board_modal.js?v=board-hash',
      '/static/js/features/atlas/atlas_tabs.js?v=atlas-tabs-hash',
      '/static/js/features/atlas/atlas_entity_row.js?v=atlas-row-hash',
      '/static/js/features/atlas/atlas_overlay.js?v=atlas-overlay-hash',
    ]))
    expect(window.__darklabImportModule).toHaveBeenCalledWith('/static/js/features/atlas/atlas_tabs.js?v=atlas-tabs-hash')
    expect(window.__darklabImportModule).toHaveBeenCalledWith('/static/js/features/atlas/atlas_entity_row.js?v=atlas-row-hash')
    expect(window.__darklabImportModule).not.toHaveBeenCalledWith('/static/js/features/atlas/atlas_entity_detail.js?v=atlas-detail-hash')
    expect(window.__darklabImportModule).not.toHaveBeenCalledWith('/static/js/features/atlas/atlas_mobile.js?v=atlas-mobile-hash')
    expect(appended).toHaveLength(0)

    await expect(atlasPromise).resolves.toEqual({ atlas: 'rail' })
    expect(window.openAtlas).toHaveBeenCalledWith({ source: 'rail' })

    const lookupPromise = window.openAtlasQuickLookup({ value: 'example.com' })
    await expect(lookupPromise).resolves.toEqual({ lookup: 'example.com' })
    expect(window.openAtlasQuickLookup).toHaveBeenCalledWith({ value: 'example.com' })

    const reportPromise = window.loadProjectReport()
    const reportApi = await reportPromise
    expect(reportApi).toBe(window.DarklabProjectReport)
    expect(window.__darklabImportModule).toHaveBeenCalledWith('/static/js/features/projects/project_report.js?v=report-hash')

    const activityPromise = window.loadProjectActivity()
    const activityApi = await activityPromise
    expect(activityApi).toBe(window.DarklabProjectActivity)
    expect(window.__darklabImportModule).toHaveBeenCalledWith('/static/js/features/projects/project_activity.js?v=activity-hash')

    const assessmentPromise = window.loadProjectAssessment()
    const assessmentApi = await assessmentPromise
    expect(assessmentApi).toBe(window.DarklabProjectAssessment)
    expect(window.__darklabImportModule).toHaveBeenCalledWith(
      '/static/js/features/projects/project_assessment.js?v=assessment-hash',
    )

    const overviewPromise = window.loadProjectOverview()
    const overviewApi = await overviewPromise
    expect(overviewApi).toBe(window.DarklabProjectOverview)
    expect(window.__darklabImportModule).toHaveBeenCalledWith('/static/js/features/projects/project_overview.js?v=overview-hash')

    const artifactsPromise = window.loadProjectArtifacts()
    const artifactsApi = await artifactsPromise
    expect(artifactsApi).toBe(window.DarklabProjectArtifacts)
    expect(window.__darklabImportModule).toHaveBeenCalledWith('/static/js/features/projects/project_artifacts.js?v=artifacts-hash')

    const packagesPromise = window.loadProjectPackages()
    const packagesApi = await packagesPromise
    expect(packagesApi).toBe(window.DarklabProjectPackages)
    expect(window.__darklabImportModule).toHaveBeenCalledWith('/static/js/features/projects/project_packages.js?v=packages-hash')

    const historyDetailsPromise = window.openHistoryRunDetails({ id: 'run-1' })
    await expect(historyDetailsPromise).resolves.toEqual({ runId: 'run-1' })
    expect(window.__darklabImportModule).toHaveBeenCalledWith('/static/js/features/history/history_run_details.js?v=history-details-hash')
    expect(window.openHistoryRunDetails).toHaveBeenCalledWith({ id: 'run-1' })

    appConfig.interactive_pty_commands = [{ root: 'mtr', trigger_flag: '--interactive' }]
    expect(window.isInteractivePtyCommand('mtr --interactive darklab.sh')).toBe(true)
    expect(window.isInteractivePtyCommand('mtr darklab.sh')).toBe(false)

    const ptyPromise = window.startInteractivePtyCommand('mtr --interactive darklab.sh', 'tab-1')

    await expect(ptyPromise).resolves.toEqual({
      cmd: 'mtr --interactive darklab.sh',
      tabId: 'tab-1',
    })
    expect(window.startInteractivePtyCommand).toHaveBeenCalledWith('mtr --interactive darklab.sh', 'tab-1')

    await expect(window.attachInteractivePtyCommand({ run_id: 'pty-run-1' }, 'tab-2')).resolves.toEqual({
      run: { run_id: 'pty-run-1' },
      tabId: 'tab-2',
    })
    expect(window.attachInteractivePtyCommand).toHaveBeenCalledWith({ run_id: 'pty-run-1' }, 'tab-2')

    const schedulesPromise = window.openSchedulesModal({ scheduleId: 'sch_1' })
    await expect(schedulesPromise).resolves.toEqual({ schedule: 'sch_1' })
    expect(window.openSchedulesModal).toHaveBeenCalledWith({ scheduleId: 'sch_1' })
    expect(window.__darklabImportModule).toHaveBeenCalledWith('/static/js/features/schedules/schedules_modal.js?v=schedules-hash')

    const tourPromise = window.openTourModal({ source: 'welcome' })
    await expect(tourPromise).resolves.toEqual({ tour: 'welcome' })
    expect(window.openTourModal).toHaveBeenCalledWith({ source: 'welcome' })

    const statusPromise = window.openStatusMonitor({ source: 'unit' })
    await expect(statusPromise).resolves.toEqual({ status: 'unit' })
    expect(imported).toEqual([
      '/static/js/features/findings/findings_board_modal.js?v=board-hash',
      '/static/js/features/atlas/atlas_tabs.js?v=atlas-tabs-hash',
      '/static/js/features/atlas/atlas_entity_row.js?v=atlas-row-hash',
      '/static/js/features/atlas/atlas_overlay.js?v=atlas-overlay-hash',
      '/static/js/features/projects/project_report.js?v=report-hash',
      '/static/js/features/projects/project_activity.js?v=activity-hash',
      '/static/js/features/projects/project_assessment.js?v=assessment-hash',
      '/static/js/features/projects/project_overview.js?v=overview-hash',
      '/static/js/features/projects/project_artifacts.js?v=artifacts-hash',
      '/static/js/features/projects/project_packages.js?v=packages-hash',
      '/static/js/features/history/history_run_details.js?v=history-details-hash',
      '/static/js/pty.js?v=pty-hash',
      '/static/js/features/schedules/schedules_modal.js?v=schedules-hash',
      '/static/js/tour_modal.js?v=tour-hash',
      '/static/js/features/status-monitor/status_monitor_core.js?v=status-core-hash',
      '/static/js/features/status-monitor/status_monitor_data.js?v=status-data-hash',
      '/static/js/features/status-monitor/status_monitor_resources.js?v=status-resources-hash',
      '/static/js/status_monitor.js?v=status-hash',
    ])
    expect(window.openStatusMonitor).toHaveBeenCalledWith({ source: 'unit' })

    const watchersPromise = window.openWatchersModal({ watcherId: 'wat_1' })
    await expect(watchersPromise).resolves.toEqual({ watcher: 'wat_1' })
    expect(window.openWatchersModal).toHaveBeenCalledWith({ watcherId: 'wat_1' })
    expect(window.__darklabImportModule).toHaveBeenCalledWith('/static/js/features/watchers/watchers_modal.js?v=watchers-hash')

    const failureDocument = {
      documentElement: {},
      head: { appendChild: vi.fn() },
      createElement: (tagName) => ({ tagName, dataset: {} }),
      getElementById: (id) => id === 'lazy-assets-json'
        ? {
            textContent: JSON.stringify({
              atlas_tabs: {
                url: '/static/js/features/atlas/atlas_tabs.js?v=atlas-tabs-hash',
                type: 'module',
              },
              atlas_entity_row: {
                url: '/static/js/features/atlas/atlas_entity_row.js?v=atlas-row-hash',
                type: 'module',
              },
              atlas_overlay: {
                url: '/static/js/features/atlas/atlas_overlay.js?v=atlas-overlay-hash',
                type: 'module',
              },
            }),
          }
        : null,
    }
    const atlasInitialRequests = []
    const failureApiFetch = vi.fn(() => {
      const request = {
        catch: vi.fn(() => request),
      }
      atlasInitialRequests.push(request)
      return request
    })
    const failureWindow = {
      logClientError: vi.fn(),
      __darklabImportModule: vi.fn(async (url) => {
        if (url.includes('/atlas_tabs.js')) return { DarklabAtlasTabs: {} }
        if (url.includes('/atlas_entity_row.js')) return { DarklabAtlasEntityRow: {} }
        if (url.includes('/atlas_overlay.js')) throw new Error('atlas overlay failed')
        return {}
      }),
    }

    fromDomScripts(
      ['app/static/js/core/lazy_assets.js'],
      {
        document: failureDocument,
        window: failureWindow,
        apiFetch: failureApiFetch,
        hasRuntimeHandler: name => name === 'apiFetch',
      },
      'window',
    )

    await expect(failureWindow.openAtlas({ source: 'rail' })).rejects.toThrow('atlas overlay failed')
    expect(failureApiFetch).toHaveBeenCalledTimes(2)
    atlasInitialRequests.forEach((request) => {
      expect(request.catch).toHaveBeenCalledWith(expect.any(Function))
    })
    expect(LAZY_ASSETS_SRC).toContain("cache: 'no-cache'")
  })

  it('lazy-loads the project workspace core and targeted deferred controllers in parallel', async () => {
    const appended = []
    const projectWorkspaceScripts = [
      ['project_details', 'DarklabProjectDetails', 'createProjectDetailsController'],
      ['project_list', 'DarklabProjectList', 'createProjectListController'],
      ['project_navigation', 'DarklabProjectNavigation', 'createProjectNavigationController'],
      ['project_entity_editor', 'DarklabProjectEntityEditor', 'createProjectEntityEditorController'],
      ['project_workspace_actions', 'DarklabProjectWorkspaceActions', 'createProjectWorkspaceActionsController'],
      ['project_workspace_shell', 'DarklabProjectWorkspaceShell', 'createProjectWorkspaceShellController'],
      ['project_workspace_lifecycle', 'DarklabProjectWorkspaceLifecycle', 'createProjectWorkspaceLifecycleController'],
      ['project_workspace_renderer', 'DarklabProjectWorkspaceRenderer', 'createProjectWorkspaceRendererController'],
      ['project_workspace_bootstrap', 'DarklabProjectWorkspaceBootstrap', 'createProjectWorkspaceBootstrapController'],
      ['project_nested_sheets', 'DarklabProjectNestedSheets', 'createProjectNestedSheetsController'],
      ['project_workspace_events', 'DarklabProjectWorkspaceEvents', 'createProjectWorkspaceEventsController'],
      ['project_targets', 'DarklabProjectTargets', 'createProjectTargetsController'],
      ['project_runs', 'DarklabProjectRuns', 'createProjectRunsController'],
      ['project_mobile_compare', 'DarklabProjectMobileCompare', 'createProjectMobileCompareController'],
      ['project_mobile_shell', 'DarklabProjectMobileShell', 'createProjectMobileShellController'],
      ['project_mobile_detail', 'DarklabProjectMobileDetail', 'createProjectMobileDetailController'],
      ['project_findings_data', 'DarklabProjectFindingsData', 'createProjectFindingsDataController'],
      ['project_filters', 'DarklabProjectFilters', 'createProjectFiltersController'],
      ['project_entities', 'DarklabProjectEntities', 'createProjectEntitiesController'],
      ['project_findings', 'DarklabProjectFindings', 'createProjectFindingsController'],
      ['project_findings_board', 'DarklabProjectFindingsBoard', 'createProjectFindingsBoardController'],
      ['project_web_surface', 'DarklabProjectWebSurface', 'createProjectWebSurfaceController'],
    ]
    const projectWorkspaceCoreNames = [
      'project_details',
      'project_list',
      'project_navigation',
      'project_workspace_shell',
      'project_workspace_lifecycle',
      'project_workspace_renderer',
      'project_workspace_bootstrap',
      'project_workspace_events',
      'project_filters',
      'project_targets',
    ]
    const projectWorkspaceCoreScripts = projectWorkspaceCoreNames.map(name => (
      projectWorkspaceScripts.find(([scriptName]) => scriptName === name)
    ))
    const document = {
      documentElement: {},
      head: {
        appendChild: (node) => {
          appended.push(node)
        },
      },
      createEvent: () => {
        const event = { type: '', detail: null }
        event.initCustomEvent = (name, _bubbles, _cancelable, detail) => {
          event.type = name
          event.detail = detail
        }
        return event
      },
      dispatchEvent: (event) => {
        events.push({ name: event.type, detail: event.detail })
        return true
      },
      createElement: (tagName) => ({ tagName, dataset: {} }),
      getElementById: (id) => id === 'lazy-assets-json'
        ? {
            textContent: JSON.stringify(Object.fromEntries(
              projectWorkspaceScripts.map(([name]) => [
                name,
                {
                  url: `/static/js/features/projects/${name}.js?v=${name}-hash`,
                  type: 'module',
                },
              ]),
            )),
          }
        : null,
    }
    const imported = []
    const pendingProjectImports = new Map()
    const window = {
      logClientError: vi.fn(),
      __darklabImportModule: vi.fn((url) => {
        imported.push(url)
        const script = projectWorkspaceScripts.find(([name]) => url.includes(`/${name}.js`))
        if (!script) return Promise.resolve()
        const [, globalName, factoryName] = script
        let resolveImport
        const promise = new Promise((resolve) => {
          resolveImport = resolve
        }).then(() => {
          const api = { [factoryName]: vi.fn() }
          window[globalName] = api
          return { [globalName]: api }
        })
        pendingProjectImports.set(script[0], resolveImport)
        return promise
      }),
    }

    fromDomScripts(
      ['app/static/js/core/lazy_assets.js'],
      { document, window },
      'window',
    )

    const loadPromise = window.loadProjectWorkspace()
    await vi.waitFor(() => {
      expect(imported).toEqual(projectWorkspaceCoreScripts.map(([name]) => (
        `/static/js/features/projects/${name}.js?v=${name}-hash`
      )))
    })
    projectWorkspaceCoreScripts.forEach(([name]) => {
      pendingProjectImports.get(name)?.()
    })
    const workspaceApi = await loadPromise
    expect(workspaceApi).toEqual(expect.objectContaining({
      DarklabProjectDetails: window.DarklabProjectDetails,
      DarklabProjectList: window.DarklabProjectList,
      DarklabProjectNavigation: window.DarklabProjectNavigation,
      DarklabProjectWorkspaceShell: window.DarklabProjectWorkspaceShell,
      DarklabProjectWorkspaceLifecycle: window.DarklabProjectWorkspaceLifecycle,
      DarklabProjectWorkspaceRenderer: window.DarklabProjectWorkspaceRenderer,
      DarklabProjectWorkspaceBootstrap: window.DarklabProjectWorkspaceBootstrap,
      DarklabProjectWorkspaceEvents: window.DarklabProjectWorkspaceEvents,
      DarklabProjectTargets: window.DarklabProjectTargets,
      DarklabProjectFilters: window.DarklabProjectFilters,
    }))
    expect(workspaceApi).not.toHaveProperty('DarklabProjectRuns')
    expect(workspaceApi).not.toHaveProperty('DarklabProjectEntities')

    const deferredPromise = window.loadProjectWorkspace({
      modules: ['project_runs', 'project_entities', 'project_web_surface'],
    })
    await vi.waitFor(() => {
      expect(imported).toEqual([
        ...projectWorkspaceCoreScripts.map(([name]) => `/static/js/features/projects/${name}.js?v=${name}-hash`),
        '/static/js/features/projects/project_runs.js?v=project_runs-hash',
        '/static/js/features/projects/project_entities.js?v=project_entities-hash',
        '/static/js/features/projects/project_web_surface.js?v=project_web_surface-hash',
      ])
    })
    pendingProjectImports.get('project_runs')?.()
    pendingProjectImports.get('project_entities')?.()
    pendingProjectImports.get('project_web_surface')?.()
    const deferredApi = await deferredPromise
    expect(deferredApi).toEqual(expect.objectContaining({
      DarklabProjectRuns: window.DarklabProjectRuns,
      DarklabProjectEntities: window.DarklabProjectEntities,
      DarklabProjectWebSurface: window.DarklabProjectWebSurface,
    }))
    expect(appended).toEqual([])

    const failureDocument = {
      ...document,
      head: { appendChild: vi.fn() },
      dispatchEvent: vi.fn(() => true),
    }
    const failureImported = []
    const failureWindow = {
      __darklabImportModule: vi.fn(async (url) => {
        failureImported.push(url)
        const script = projectWorkspaceScripts.find(([name]) => url.includes(`/${name}.js`))
        if (!script) return {}
        const [, globalName, factoryName] = script
        const api = globalName === 'DarklabProjectWorkspaceShell'
          ? { createUnexpectedController: vi.fn() }
          : { [factoryName]: vi.fn() }
        failureWindow[globalName] = api
        return { [globalName]: api }
      }),
      logClientError: vi.fn(),
    }

    fromDomScripts(
      ['app/static/js/core/lazy_assets.js'],
      { document: failureDocument, window: failureWindow },
      'window',
    )

    await expect(failureWindow.loadProjectWorkspace()).rejects.toThrow(
      'Lazy module project_workspace_shell did not expose DarklabProjectWorkspaceShell.createProjectWorkspaceShellController',
    )
    expect(failureWindow.logClientError).toHaveBeenCalledWith(
      'lazy module export missing',
      expect.any(Error),
      {
        event: 'LAZY_MODULE_EXPORT_MISSING',
        level: 'error',
        asset_name: 'project_workspace_shell',
        export_name: 'DarklabProjectWorkspaceShell',
        controller_name: 'createProjectWorkspaceShellController',
        src: '/static/js/features/projects/project_workspace_shell.js?v=project_workspace_shell-hash',
        module_keys: ['DarklabProjectWorkspaceShell'],
      },
    )
    expect(failureImported).toContain('/static/js/features/projects/project_workspace_shell.js?v=project_workspace_shell-hash')
  })

  it('lazy-loads the history comparison controller cluster in order', async () => {
    const appended = []
    const historyCompareScripts = [
      ['history_compare_core', '/static/js/features/run-comparison/history_compare_core.js?v=compare-core-hash'],
      ['history_compare_overlay', '/static/js/features/run-comparison/history_compare_overlay.js?v=compare-overlay-hash'],
      ['history_compare_controls', '/static/js/features/run-comparison/history_compare_controls.js?v=compare-controls-hash'],
      ['history_compare_navigation', '/static/js/features/run-comparison/history_compare_navigation.js?v=compare-navigation-hash'],
      ['history_compare_renderer', '/static/js/features/run-comparison/history_compare_renderer.js?v=compare-renderer-hash'],
      ['history_compare_launcher', '/static/js/features/run-comparison/history_compare_launcher.js?v=compare-launcher-hash'],
    ]
    const document = {
      documentElement: {},
      head: {
        appendChild: (node) => {
          appended.push(node)
        },
      },
      createElement: (tagName) => ({ tagName, dataset: {} }),
      getElementById: (id) => id === 'lazy-assets-json'
        ? {
            textContent: JSON.stringify(Object.fromEntries(historyCompareScripts.map(([name, url]) => [
              name,
              { url, type: 'module' },
            ]))),
          }
        : null,
    }
    const imported = []
    const window = {
      logClientError: vi.fn(),
      __darklabImportModule: vi.fn(async (url) => {
        imported.push(url)
        if (url.includes('/history_compare_core.js')) {
          const DarklabHistoryCompareCore = {}
          window.DarklabHistoryCompareCore = DarklabHistoryCompareCore
          return { DarklabHistoryCompareCore }
        }
        if (url.includes('/history_compare_overlay.js')) {
          const closeHistoryCompareOverlay = vi.fn()
          const isHistoryCompareOverlayOpen = vi.fn()
          window.closeHistoryCompareOverlay = closeHistoryCompareOverlay
          window.isHistoryCompareOverlayOpen = isHistoryCompareOverlayOpen
          return { closeHistoryCompareOverlay, isHistoryCompareOverlayOpen }
        }
        if (url.includes('/history_compare_controls.js')) {
          const _closeHistoryCompareActionMenus = vi.fn()
          window._closeHistoryCompareActionMenus = _closeHistoryCompareActionMenus
          return { _closeHistoryCompareActionMenus }
        }
        if (url.includes('/history_compare_navigation.js')) {
          const _historyCompareScrollToLine = vi.fn()
          window._historyCompareScrollToLine = _historyCompareScrollToLine
          return { _historyCompareScrollToLine }
        }
        if (url.includes('/history_compare_renderer.js')) {
          const fetchAndRenderHistoryComparison = vi.fn()
          window.fetchAndRenderHistoryComparison = fetchAndRenderHistoryComparison
          return { fetchAndRenderHistoryComparison }
        }
        if (url.includes('/history_compare_launcher.js')) {
          const openHistoryCompareLauncher = vi.fn(run => ({ runId: run.id }))
          window.openHistoryCompareLauncher = openHistoryCompareLauncher
          return { openHistoryCompareLauncher }
        }
        return {}
      }),
    }

    fromDomScripts(
      ['app/static/js/core/lazy_assets.js'],
      { document, window },
      'window',
    )

    const openPromise = window.openHistoryCompareLauncher({ id: 'run-1' })

    await expect(openPromise).resolves.toEqual({ runId: 'run-1' })
    expect(window.openHistoryCompareLauncher).toHaveBeenCalledWith({ id: 'run-1' }, {})
    expect(imported).toEqual(historyCompareScripts.map(([, url]) => url))
    expect(appended).toEqual([])
    expect(window.logClientError).not.toHaveBeenCalled()

    window.logClientError.mockClear()
    await window.loadLazyAsset('history_compare_core')
    expect(window.__darklabImportModule).toHaveBeenCalledTimes(historyCompareScripts.length)
    expect(window.logClientError).not.toHaveBeenCalled()
  })

  it('logs lazy module load and export-contract failures with safe asset context', async () => {
    const document = {
      documentElement: {},
      head: { appendChild: vi.fn() },
      createElement: (tagName) => ({ tagName, dataset: {} }),
      getElementById: (id) => id === 'lazy-assets-json'
        ? {
            textContent: JSON.stringify({
              project_report: {
                url: '/static/js/features/projects/project_report.js?v=report-hash&token=secret',
                type: 'module',
              },
            }),
          }
        : null,
    }
    const failure = new Error('network failed')
    let importerMode = 'reject'
    const window = {
      location: { href: 'http://127.0.0.1/' },
      __darklabImportModule: vi.fn(async () => {
        if (importerMode === 'reject') throw failure
        return { OtherExport: vi.fn() }
      }),
      logClientError: vi.fn(),
    }

    fromDomScripts(
      ['app/static/js/core/lazy_assets.js'],
      { document, window },
      'window',
    )

    await expect(window.loadProjectReport()).rejects.toThrow('network failed')
    expect(window.logClientError).toHaveBeenCalledWith('lazy asset load failed', failure, {
      event: 'LAZY_ASSET_LOAD_FAILED',
      level: 'error',
      asset_name: 'project_report',
      asset_type: 'module',
      src: '/static/js/features/projects/project_report.js?v=report-hash',
      expected_global: false,
    })

    importerMode = 'missing-export'
    window.logClientError.mockClear()

    await expect(window.loadProjectReport()).rejects.toThrow(
      'Lazy module did not expose export: DarklabProjectReport',
    )
    expect(window.logClientError).toHaveBeenCalledWith(
      'lazy module export missing',
      expect.any(Error),
      {
        event: 'LAZY_MODULE_EXPORT_MISSING',
        level: 'error',
        asset_name: 'project_report',
        export_name: 'DarklabProjectReport',
        controller_name: '',
        src: '/static/js/features/projects/project_report.js?v=report-hash',
        module_keys: ['OtherExport'],
      },
    )
  })

  it('logs invalid lazy asset config without including the raw JSON body', async () => {
    const document = {
      documentElement: {},
      head: { appendChild: vi.fn() },
      createElement: (tagName) => ({ tagName, dataset: {} }),
      getElementById: (id) => id === 'lazy-assets-json'
        ? { textContent: '{"project_report": "secret-token"' }
        : null,
    }
    const window = {
      location: { href: 'http://127.0.0.1/' },
      DarklabProjectReport: { createProjectReportController: vi.fn() },
      __darklabImportModule: vi.fn(async () => {}),
      logClientError: vi.fn(),
    }

    fromDomScripts(
      ['app/static/js/core/lazy_assets.js'],
      { document, window },
      'window',
    )

    expect(window.lazyAssetUrl('project_report')).toBe('/static/js/features/projects/project_report.js')
    expect(window.lazyAssetUrl('project_report')).toBe('/static/js/features/projects/project_report.js')
    expect(window.__darklabImportModule).not.toHaveBeenCalled()
    expect(window.logClientError).toHaveBeenCalledTimes(1)
    const [context, err, details] = window.logClientError.mock.calls[0]
    expect(context).toBe('lazy asset config invalid')
    expect(err).toBeInstanceOf(SyntaxError)
    expect(details).toEqual({
      event: 'LAZY_ASSET_CONFIG_INVALID',
      level: 'warning',
      source: 'lazy-assets-json',
    })
    expect(JSON.stringify(window.logClientError.mock.calls)).not.toContain('secret-token')
  })

  it('lazy-loads the Options panel controller cluster in order', async () => {
    const appended = []
    const optionsPanelScripts = [
      ['options_session_token_controls', {
        url: '/static/js/features/preferences/session_token_controls.js?v=session-token-hash',
        type: 'module',
      }],
      ['options_secrets_panel', {
        url: '/static/js/features/preferences/secrets_panel.js?v=secrets-hash',
        type: 'module',
      }],
      ['options_teams_panel', {
        url: '/static/js/features/preferences/teams_panel.js?v=teams-hash',
        type: 'module',
      }],
      ['options_notification_channels', {
        url: '/static/js/features/preferences/notification_channels.js?v=notifications-hash',
        type: 'module',
      }],
    ]
    const document = {
      documentElement: {},
      head: {
        appendChild: (node) => {
          appended.push(node)
        },
      },
      createElement: (tagName) => ({ tagName, dataset: {} }),
      getElementById: (id) => id === 'lazy-assets-json'
        ? {
            textContent: JSON.stringify(Object.fromEntries(optionsPanelScripts)),
          }
        : null,
    }
    const imported = []
    const window = {
      __darklabImportModule: vi.fn(async (url) => {
        imported.push(url)
        if (url.includes('/session_token_controls.js')) {
          const _updateOptionsSessionTokenStatus = vi.fn()
          window._updateOptionsSessionTokenStatus = _updateOptionsSessionTokenStatus
          return { _updateOptionsSessionTokenStatus }
        }
        if (url.includes('/secrets_panel.js')) {
          const refreshOptionsSecrets = vi.fn(async () => true)
          const invalidateOptionsSecrets = vi.fn()
          const openSecretEditor = vi.fn()
          const openProviderStatusModal = vi.fn()
          window.refreshOptionsSecrets = refreshOptionsSecrets
          window.invalidateOptionsSecrets = invalidateOptionsSecrets
          return {
            refreshOptionsSecrets,
            invalidateOptionsSecrets,
            openSecretEditor,
            openProviderStatusModal,
          }
        }
        if (url.includes('/teams_panel.js')) {
          const refreshOptionsTeams = vi.fn(async () => true)
          window.refreshOptionsTeams = refreshOptionsTeams
          return { refreshOptionsTeams }
        }
        if (url.includes('/notification_channels.js')) {
          const refreshNotificationChannels = vi.fn(async () => true)
          const openNotificationChannelEditor = vi.fn()
          window.refreshNotificationChannels = refreshNotificationChannels
          return { refreshNotificationChannels, openNotificationChannelEditor }
        }
        return {}
      }),
    }

    fromDomScripts(
      ['app/static/js/core/lazy_assets.js'],
      { document, window },
      'window',
    )

    const loadPromise = window.loadOptionsPanels()

    await vi.waitFor(() => expect(imported).toEqual([
      '/static/js/features/preferences/session_token_controls.js?v=session-token-hash',
      '/static/js/features/preferences/secrets_panel.js?v=secrets-hash',
      '/static/js/features/preferences/teams_panel.js?v=teams-hash',
      '/static/js/features/preferences/notification_channels.js?v=notifications-hash',
    ]))
    expect(appended).toEqual([])

    const panels = await loadPromise
    expect(panels).toEqual(expect.objectContaining({
      _updateOptionsSessionTokenStatus: expect.any(Function),
      refreshOptionsSecrets: expect.any(Function),
      invalidateOptionsSecrets: expect.any(Function),
      openSecretEditor: expect.any(Function),
      openProviderStatusModal: expect.any(Function),
      refreshOptionsTeams: expect.any(Function),
      refreshNotificationChannels: expect.any(Function),
      openNotificationChannelEditor: expect.any(Function),
    }))
    expect(panels.refreshOptionsSecrets).toBe(window.refreshOptionsSecrets)
    expect(panels.refreshOptionsTeams).toBe(window.refreshOptionsTeams)
    expect(panels.refreshNotificationChannels).toBe(window.refreshNotificationChannels)
  })

  it('lazy-loads the command registry modal on first open', async () => {
    const appended = []
    const document = {
      documentElement: {},
      head: {
        appendChild: (node) => {
          appended.push(node)
        },
      },
      createElement: (tagName) => ({ tagName, dataset: {} }),
      getElementById: (id) => id === 'lazy-assets-json'
        ? {
            textContent: JSON.stringify({
              command_registry: {
                url: '/static/js/features/command-registry/command_registry.js?v=registry-hash',
                type: 'module',
              },
            }),
          }
        : null,
    }
    const imported = []
    const window = {
      __darklabImportModule: vi.fn(async (url) => {
        imported.push(url)
        const openCommandRegistry = vi.fn(() => ({ opened: true }))
        window.openCommandRegistry = openCommandRegistry
        return { openCommandRegistry }
      }),
    }

    fromDomScripts(
      ['app/static/js/core/lazy_assets.js'],
      { document, window },
      'window',
    )

    const openPromise = window.openCommandRegistry()

    await expect(openPromise).resolves.toEqual({ opened: true })
    expect(window.openCommandRegistry).toHaveBeenCalledTimes(1)
    expect(imported).toEqual(['/static/js/features/command-registry/command_registry.js?v=registry-hash'])
    expect(appended).toEqual([])
  })

  it('lazy-loads the Files surface and drag-drop helper together', async () => {
    const appended = []
    const document = {
      documentElement: {},
      head: {
        appendChild: (node) => {
          appended.push(node)
        },
      },
      createElement: (tagName) => ({ tagName, dataset: {} }),
      getElementById: (id) => id === 'lazy-assets-json'
        ? {
            textContent: JSON.stringify({
              workspace: {
                url: '/static/js/workspace.js?v=workspace-hash',
                type: 'module',
              },
              workspace_drag_drop: {
                url: '/static/js/features/workspace/workspace_drag_drop.js?v=drag-hash',
                type: 'module',
              },
            }),
          }
        : null,
    }
    const imported = []
    const workspaceModule = {
      openWorkspace: vi.fn(async () => true),
      closeWorkspace: vi.fn(),
    }
    const setWorkspaceHandlers = vi.fn()
    const window = {
      setWorkspaceHandlers,
      __darklabImportModule: vi.fn(async (url) => {
        imported.push(url)
        if (url.includes('/workspace.js')) return workspaceModule
        return { _workspaceDragSourceFromEvent: vi.fn() }
      }),
    }

    fromDomScripts(
      ['app/static/js/core/lazy_assets.js'],
      { document, window, setWorkspaceHandlers },
      'window',
    )

    await expect(window.loadWorkspaceSurface()).resolves.toBe(workspaceModule)

    expect(imported).toEqual([
      '/static/js/workspace.js?v=workspace-hash',
      '/static/js/features/workspace/workspace_drag_drop.js?v=drag-hash',
    ])
    expect(setWorkspaceHandlers).toHaveBeenCalledWith(workspaceModule)
    expect(appended).toEqual([])
  })

  it('lazy-loads workflow controllers while keeping the catalog cache eager', async () => {
    const appended = []
    const events = []
    const document = {
      documentElement: {},
      head: {
        appendChild: (node) => {
          appended.push(node)
        },
      },
      createElement: (tagName) => ({ tagName, dataset: {} }),
      getElementById: (id) => id === 'lazy-assets-json'
        ? {
            textContent: JSON.stringify({
              workflows: {
                url: '/static/js/features/workflows/workflows.js?v=workflows-hash',
                type: 'module',
              },
            }),
          }
        : null,
    }
    const imported = []
    const realHandler = vi.fn(async () => true)
    const window = {
      __darklabImportModule: vi.fn(async (url) => {
        imported.push(url)
        const renderWorkflowItems = vi.fn()
        const handleWorkflowTerminalCommand = realHandler
        window.renderWorkflowItems = renderWorkflowItems
        window.handleWorkflowTerminalCommand = realHandler
        return { renderWorkflowItems, handleWorkflowTerminalCommand }
      }),
    }

    fromDomScripts(
      ['app/static/js/core/lazy_assets.js'],
      { document, window, emitUiEvent: (name, detail) => events.push({ name, detail }) },
      'window',
    )

    const items = [{ title: 'DNS check' }]
    expect(window.renderWorkflowItems(items)).toEqual(items)
    expect(window.__workflowCatalogItems).toEqual(items)
    expect(events).toEqual([{
      name: 'app:workflows-rendered',
      detail: { count: 1, items },
    }])

    const execution = { appendLine: vi.fn(), setStatus: vi.fn() }
    const commandPromise = window.handleWorkflowTerminalCommand(
      'workflow list',
      'tab-1',
      execution,
    )

    await expect(commandPromise).resolves.toBe(true)
    expect(realHandler).toHaveBeenCalledWith('workflow list', 'tab-1', execution)
    expect(imported).toEqual(['/static/js/features/workflows/workflows.js?v=workflows-hash'])
    expect(appended).toEqual([])
  })
})
