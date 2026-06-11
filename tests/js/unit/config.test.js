import { readFileSync } from 'fs'
import { resolve } from 'path'
import { fromDomScript, fromDomScripts } from './helpers/extract.js'

const CONFIG_SRC = readFileSync(resolve(process.cwd(), 'app/static/js/core/config.js'), 'utf8')

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
    const window = {}
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
  })

  it('falls back to an existing window APP_CONFIG object for non-template harnesses', () => {
    const bootstrap = { app_name: 'harness', recent_commands_limit: 3 }
    const document = { getElementById: () => null }
    const window = { APP_CONFIG: bootstrap }
    const { APP_CONFIG } = fromDomScript('app/static/js/core/config.js', { document, window }, 'APP_CONFIG')

    expect(APP_CONFIG).toBe(bootstrap)
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
              findings_board: '/static/js/features/findings/findings_board_modal.js?v=board-hash',
              atlas_tabs: '/static/js/features/atlas/atlas_tabs.js?v=atlas-tabs-hash',
              atlas_entity_row: '/static/js/features/atlas/atlas_entity_row.js?v=atlas-row-hash',
              atlas_entity_detail: '/static/js/features/atlas/atlas_entity_detail.js?v=atlas-detail-hash',
              atlas_overlay: '/static/js/features/atlas/atlas_overlay.js?v=atlas-overlay-hash',
              atlas_mobile: '/static/js/features/atlas/atlas_mobile.js?v=atlas-mobile-hash',
              schedules_modal: '/static/js/features/schedules/schedules_modal.js?v=schedules-hash',
              project_activity: '/static/js/features/projects/project_activity.js?v=activity-hash',
              project_artifacts: '/static/js/features/projects/project_artifacts.js?v=artifacts-hash',
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
              project_packages: '/static/js/features/projects/project_packages.js?v=packages-hash',
              project_report: '/static/js/features/projects/project_report.js?v=report-hash',
              history_run_details: '/static/js/features/history/history_run_details.js?v=history-details-hash',
              pty_controller: '/static/js/pty.js?v=pty-hash',
              status_monitor_core: '/static/js/features/status-monitor/status_monitor_core.js?v=status-core-hash',
              status_monitor_data: '/static/js/features/status-monitor/status_monitor_data.js?v=status-data-hash',
              status_monitor_resources: '/static/js/features/status-monitor/status_monitor_resources.js?v=status-resources-hash',
              status_monitor: '/static/js/status_monitor.js?v=status-hash',
              tour_modal: '/static/js/tour_modal.js?v=tour-hash',
              watchers_modal: '/static/js/features/watchers/watchers_modal.js?v=watchers-hash',
            }),
          }
        : id === 'atlas-mobile-root'
          ? {}
        : null,
    }
    const window = {}

    fromDomScripts(
      ['app/static/js/core/lazy_assets.js'],
      { document, window },
      'window',
    )

    const openPromise = window.openFindingsBoard({ source: 'unit' })
    expect(appended).toHaveLength(1)
    expect(appended[0].src).toBe('/static/js/features/findings/findings_board_modal.js?v=board-hash')

    const realOpen = vi.fn(async options => ({ opened: options.source }))
    window.openFindingsBoard = realOpen
    appended[0].onload()

    await expect(openPromise).resolves.toEqual({ opened: 'unit' })
    expect(realOpen).toHaveBeenCalledWith({ source: 'unit' })

    const atlasPromise = window.openAtlas({ source: 'rail' })
    await vi.waitFor(() => expect(appended).toHaveLength(2))
    expect(appended[1].src).toBe('/static/js/features/atlas/atlas_tabs.js?v=atlas-tabs-hash')

    window.DarklabAtlasTabs = {}
    appended[1].onload()
    await vi.waitFor(() => expect(appended).toHaveLength(3))
    expect(appended[2].src).toBe('/static/js/features/atlas/atlas_entity_row.js?v=atlas-row-hash')

    window.DarklabAtlasEntityRow = {}
    appended[2].onload()
    await vi.waitFor(() => expect(appended).toHaveLength(4))
    expect(appended[3].src).toBe('/static/js/features/atlas/atlas_entity_detail.js?v=atlas-detail-hash')

    window.DarklabAtlasDetail = {}
    appended[3].onload()
    await vi.waitFor(() => expect(appended).toHaveLength(5))
    expect(appended[4].src).toBe('/static/js/features/atlas/atlas_overlay.js?v=atlas-overlay-hash')

    const realAtlasOpen = vi.fn(async options => ({ atlas: options.source }))
    window.openAtlas = realAtlasOpen
    appended[4].onload()
    await vi.waitFor(() => expect(appended).toHaveLength(6))
    expect(appended[5].src).toBe('/static/js/features/atlas/atlas_mobile.js?v=atlas-mobile-hash')

    window.DarklabAtlasMobile = {}
    appended[5].onload()

    await expect(atlasPromise).resolves.toEqual({ atlas: 'rail' })
    expect(realAtlasOpen).toHaveBeenCalledWith({ source: 'rail' })

    const reportPromise = window.loadProjectReport()
    await vi.waitFor(() => expect(appended).toHaveLength(7))
    expect(appended[6].src).toBe('/static/js/features/projects/project_report.js?v=report-hash')

    window.DarklabProjectReport = { createProjectReportController: vi.fn() }
    appended[6].onload()

    await expect(reportPromise).resolves.toBe(window.DarklabProjectReport)

    const activityPromise = window.loadProjectActivity()
    await vi.waitFor(() => expect(appended).toHaveLength(8))
    expect(appended[7].src).toBe('/static/js/features/projects/project_activity.js?v=activity-hash')

    window.DarklabProjectActivity = { createProjectActivityController: vi.fn() }
    appended[7].onload()

    await expect(activityPromise).resolves.toBe(window.DarklabProjectActivity)

    const artifactsPromise = window.loadProjectArtifacts()
    await vi.waitFor(() => expect(appended).toHaveLength(9))
    expect(appended[8].src).toBe('/static/js/features/projects/project_artifacts.js?v=artifacts-hash')

    window.DarklabProjectArtifacts = { createProjectArtifactsController: vi.fn() }
    appended[8].onload()

    await expect(artifactsPromise).resolves.toBe(window.DarklabProjectArtifacts)

    const packagesPromise = window.loadProjectPackages()
    await vi.waitFor(() => expect(appended).toHaveLength(10))
    expect(appended[9].src).toBe('/static/js/features/projects/project_packages.js?v=packages-hash')

    window.DarklabProjectPackages = { createProjectPackagesController: vi.fn() }
    appended[9].onload()

    await expect(packagesPromise).resolves.toBe(window.DarklabProjectPackages)

    const historyDetailsPromise = window.openHistoryRunDetails({ id: 'run-1' })
    await vi.waitFor(() => expect(appended).toHaveLength(11))
    expect(appended[10].src).toBe('/static/js/features/history/history_run_details.js?v=history-details-hash')

    const realHistoryDetailsOpen = vi.fn(run => ({ runId: run.id }))
    window.openHistoryRunDetails = realHistoryDetailsOpen
    appended[10].onload()

    await expect(historyDetailsPromise).resolves.toEqual({ runId: 'run-1' })
    expect(realHistoryDetailsOpen).toHaveBeenCalledWith({ id: 'run-1' })

    window.APP_CONFIG = {
      interactive_pty_commands: [{ root: 'mtr', trigger_flag: '--interactive' }],
    }
    expect(window.isInteractivePtyCommand('mtr --interactive darklab.sh')).toBe(true)
    expect(window.isInteractivePtyCommand('mtr darklab.sh')).toBe(false)

    const ptyPromise = window.startInteractivePtyCommand('mtr --interactive darklab.sh', 'tab-1')
    await vi.waitFor(() => expect(appended).toHaveLength(12))
    expect(appended[11].src).toBe('/static/js/pty.js?v=pty-hash')

    const realPtyStart = vi.fn(async (cmd, tabId) => ({ cmd, tabId }))
    const realPtyAttach = vi.fn(async (run, tabId) => ({ run, tabId }))
    window.startInteractivePtyCommand = realPtyStart
    window.attachInteractivePtyCommand = realPtyAttach
    appended[11].onload()

    await expect(ptyPromise).resolves.toEqual({
      cmd: 'mtr --interactive darklab.sh',
      tabId: 'tab-1',
    })
    expect(realPtyStart).toHaveBeenCalledWith('mtr --interactive darklab.sh', 'tab-1')

    await expect(window.attachInteractivePtyCommand({ run_id: 'pty-run-1' }, 'tab-2')).resolves.toEqual({
      run: { run_id: 'pty-run-1' },
      tabId: 'tab-2',
    })
    expect(realPtyAttach).toHaveBeenCalledWith({ run_id: 'pty-run-1' }, 'tab-2')

    const schedulesPromise = window.openSchedulesModal({ scheduleId: 'sch_1' })
    expect(appended).toHaveLength(13)
    expect(appended[12].src).toBe('/static/js/features/schedules/schedules_modal.js?v=schedules-hash')

    const realSchedulesOpen = vi.fn(async options => ({ schedule: options.scheduleId }))
    window.openSchedulesModal = realSchedulesOpen
    appended[12].onload()

    await expect(schedulesPromise).resolves.toEqual({ schedule: 'sch_1' })
    expect(realSchedulesOpen).toHaveBeenCalledWith({ scheduleId: 'sch_1' })

    const tourPromise = window.openTourModal({ source: 'welcome' })
    expect(appended).toHaveLength(14)
    expect(appended[13].src).toBe('/static/js/tour_modal.js?v=tour-hash')

    const realTourOpen = vi.fn(options => ({ tour: options.source }))
    window.openTourModal = realTourOpen
    appended[13].onload()

    await expect(tourPromise).resolves.toEqual({ tour: 'welcome' })
    expect(realTourOpen).toHaveBeenCalledWith({ source: 'welcome' })

    const statusPromise = window.openStatusMonitor({ source: 'unit' })
    await vi.waitFor(() => expect(appended).toHaveLength(15))
    expect(appended).toHaveLength(15)
    expect(appended[14].src).toBe('/static/js/features/status-monitor/status_monitor_core.js?v=status-core-hash')

    window.DarklabStatusMonitorCore = {}
    appended[14].onload()
    await vi.waitFor(() => expect(appended).toHaveLength(16))
    expect(appended).toHaveLength(16)
    expect(appended[15].src).toBe('/static/js/features/status-monitor/status_monitor_data.js?v=status-data-hash')

    window.DarklabStatusMonitorData = {}
    appended[15].onload()
    await vi.waitFor(() => expect(appended).toHaveLength(17))
    expect(appended).toHaveLength(17)
    expect(appended[16].src).toBe('/static/js/features/status-monitor/status_monitor_resources.js?v=status-resources-hash')

    window.DarklabStatusMonitorResources = {}
    appended[16].onload()
    await vi.waitFor(() => expect(appended).toHaveLength(18))
    expect(appended).toHaveLength(18)
    expect(appended[17].src).toBe('/static/js/status_monitor.js?v=status-hash')

    const realStatusOpen = vi.fn(async options => ({ status: options.source }))
    window.openStatusMonitor = realStatusOpen
    appended[17].onload()

    await expect(statusPromise).resolves.toEqual({ status: 'unit' })
    expect(realStatusOpen).toHaveBeenCalledWith({ source: 'unit' })

    const watchersPromise = window.openWatchersModal({ watcherId: 'wat_1' })
    expect(appended).toHaveLength(19)
    expect(appended[18].src).toBe('/static/js/features/watchers/watchers_modal.js?v=watchers-hash')

    const realWatchersOpen = vi.fn(async options => ({ watcher: options.watcherId }))
    window.openWatchersModal = realWatchersOpen
    appended[18].onload()

    await expect(watchersPromise).resolves.toEqual({ watcher: 'wat_1' })
    expect(realWatchersOpen).toHaveBeenCalledWith({ watcherId: 'wat_1' })
  })

  it('lazy-loads the project workspace controller cluster in order', async () => {
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
            textContent: JSON.stringify(Object.fromEntries(
              projectWorkspaceScripts.map(([name]) => [
                name,
                `/static/js/features/projects/${name}.js?v=${name}-hash`,
              ]),
            )),
          }
        : null,
    }
    const window = {}

    fromDomScripts(
      ['app/static/js/core/lazy_assets.js'],
      { document, window },
      'window',
    )

    const loadPromise = window.loadProjectWorkspace()
    for (const [index, [name, globalName, factoryName]] of projectWorkspaceScripts.entries()) {
      await vi.waitFor(() => expect(appended).toHaveLength(index + 1))
      expect(appended[index].src).toBe(`/static/js/features/projects/${name}.js?v=${name}-hash`)
      window[globalName] = { [factoryName]: vi.fn() }
      appended[index].onload()
    }

    await expect(loadPromise).resolves.toBe(window.DarklabProjectWorkspaceShell)
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
            textContent: JSON.stringify(Object.fromEntries(historyCompareScripts)),
          }
        : null,
    }
    const window = {}

    fromDomScripts(
      ['app/static/js/core/lazy_assets.js'],
      { document, window },
      'window',
    )

    const openPromise = window.openHistoryCompareLauncher({ id: 'run-1' })

    await vi.waitFor(() => expect(appended).toHaveLength(1))
    expect(appended[0].src).toBe('/static/js/features/run-comparison/history_compare_core.js?v=compare-core-hash')
    window.DarklabHistoryCompareCore = {}
    appended[0].onload()

    await vi.waitFor(() => expect(appended).toHaveLength(2))
    expect(appended[1].src).toBe('/static/js/features/run-comparison/history_compare_overlay.js?v=compare-overlay-hash')
    window.closeHistoryCompareOverlay = vi.fn()
    window.isHistoryCompareOverlayOpen = vi.fn()
    appended[1].onload()

    await vi.waitFor(() => expect(appended).toHaveLength(3))
    expect(appended[2].src).toBe('/static/js/features/run-comparison/history_compare_controls.js?v=compare-controls-hash')
    globalThis._closeHistoryCompareActionMenus = vi.fn()
    appended[2].onload()

    await vi.waitFor(() => expect(appended).toHaveLength(4))
    expect(appended[3].src).toBe('/static/js/features/run-comparison/history_compare_navigation.js?v=compare-navigation-hash')
    globalThis._historyCompareScrollToLine = vi.fn()
    appended[3].onload()

    await vi.waitFor(() => expect(appended).toHaveLength(5))
    expect(appended[4].src).toBe('/static/js/features/run-comparison/history_compare_renderer.js?v=compare-renderer-hash')
    window.fetchAndRenderHistoryComparison = vi.fn()
    appended[4].onload()

    await vi.waitFor(() => expect(appended).toHaveLength(6))
    expect(appended[5].src).toBe('/static/js/features/run-comparison/history_compare_launcher.js?v=compare-launcher-hash')
    const realOpen = vi.fn(run => ({ runId: run.id }))
    window.openHistoryCompareLauncher = realOpen
    appended[5].onload()

    await expect(openPromise).resolves.toEqual({ runId: 'run-1' })
    expect(realOpen).toHaveBeenCalledWith({ id: 'run-1' })

    delete globalThis._closeHistoryCompareActionMenus
    delete globalThis._historyCompareScrollToLine
  })

  it('lazy-loads the Options panel controller cluster in order', async () => {
    const appended = []
    const optionsPanelScripts = [
      ['options_session_token_controls', '/static/js/features/preferences/session_token_controls.js?v=session-token-hash'],
      ['options_secrets_panel', '/static/js/features/preferences/secrets_panel.js?v=secrets-hash'],
      ['options_teams_panel', '/static/js/features/preferences/teams_panel.js?v=teams-hash'],
      ['options_notification_channels', '/static/js/features/preferences/notification_channels.js?v=notifications-hash'],
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
    const window = {}

    fromDomScripts(
      ['app/static/js/core/lazy_assets.js'],
      { document, window },
      'window',
    )

    const loadPromise = window.loadOptionsPanels()

    await vi.waitFor(() => expect(appended).toHaveLength(1))
    expect(appended[0].src).toBe('/static/js/features/preferences/session_token_controls.js?v=session-token-hash')
    globalThis._updateOptionsSessionTokenStatus = vi.fn()
    appended[0].onload()

    await vi.waitFor(() => expect(appended).toHaveLength(2))
    expect(appended[1].src).toBe('/static/js/features/preferences/secrets_panel.js?v=secrets-hash')
    window.refreshOptionsSecrets = vi.fn(async () => true)
    window.invalidateOptionsSecrets = vi.fn()
    appended[1].onload()

    await vi.waitFor(() => expect(appended).toHaveLength(3))
    expect(appended[2].src).toBe('/static/js/features/preferences/teams_panel.js?v=teams-hash')
    window.refreshOptionsTeams = vi.fn(async () => true)
    appended[2].onload()

    await vi.waitFor(() => expect(appended).toHaveLength(4))
    expect(appended[3].src).toBe('/static/js/features/preferences/notification_channels.js?v=notifications-hash')
    window.refreshNotificationChannels = vi.fn(async () => true)
    appended[3].onload()

    await expect(loadPromise).resolves.toBe(true)

    delete globalThis._updateOptionsSessionTokenStatus
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
              command_registry: '/static/js/features/command-registry/command_registry.js?v=registry-hash',
            }),
          }
        : null,
    }
    const window = {}

    fromDomScripts(
      ['app/static/js/core/lazy_assets.js'],
      { document, window },
      'window',
    )

    const openPromise = window.openCommandRegistry()
    expect(appended).toHaveLength(1)
    expect(appended[0].src).toBe('/static/js/features/command-registry/command_registry.js?v=registry-hash')

    const realOpen = vi.fn(() => ({ opened: true }))
    window.openCommandRegistry = realOpen
    appended[0].onload()

    await expect(openPromise).resolves.toEqual({ opened: true })
    expect(realOpen).toHaveBeenCalledTimes(1)
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
              workflows: '/static/js/features/workflows/workflows.js?v=workflows-hash',
            }),
          }
        : null,
    }
    const window = {
      emitUiEvent: (name, detail) => {
        events.push({ name, detail })
      },
    }

    fromDomScripts(
      ['app/static/js/core/lazy_assets.js'],
      { document, window },
      'window',
    )

    const items = [{ title: 'DNS check' }]
    expect(window.renderWorkflowItems(items)).toEqual(items)
    expect(window.__workflowCatalogItems).toEqual(items)
    expect(events).toEqual([
      {
        name: 'app:workflows-rendered',
        detail: { count: 1, items },
      },
    ])

    const commandPromise = window.handleWorkflowTerminalCommand('workflow list', 'tab-1')
    expect(appended).toHaveLength(1)
    expect(appended[0].src).toBe('/static/js/features/workflows/workflows.js?v=workflows-hash')

    const realHandler = vi.fn(async () => true)
    window.renderWorkflowItems = vi.fn()
    window.handleWorkflowTerminalCommand = realHandler
    appended[0].onload()

    await expect(commandPromise).resolves.toBe(true)
    expect(realHandler).toHaveBeenCalledWith('workflow list', 'tab-1')
  })
})
