import { describe, expect, it, vi } from 'vitest'
import {
  applyRedactionRules,
  escapeHtml,
  showToast,
} from '../../../app/static/js/core/utils.js'
import {
  cmdInput,
  searchScopeButtons,
  terminalWrap,
} from '../../../app/static/js/core/dom.js'
import {
  APP_CONFIG,
  getAppConfig,
  setAppConfig,
} from '../../../app/static/js/core/config.js'
import {
  DarklabPreferenceCore,
  coerceLineNumberMode,
  normalizePromptUsername,
} from '../../../app/static/js/core/app_preferences_core.js'
import {
  DarklabAutocompleteCore,
  filterItems,
  tokenContextFromText,
} from '../../../app/static/js/core/autocomplete_core.js'
import { acHide } from '../../../app/static/js/autocomplete.js'
import {
  DarklabRunOutputModel,
  LineRole,
  fromWireLineEvent,
} from '../../../app/static/js/core/run_output_model.js'
import {
  APP_STATE_API,
  emitUiEvent,
  getActiveTabId,
  getAutocompleteState,
  getComposerState,
  getTabs,
  getWelcomeState,
  onUiEvent,
  setActiveTabId,
  setAutocompleteState,
  setComposerState,
  setTabs,
  setWelcomeState,
} from '../../../app/static/js/core/state.js'
import {
  DarklabSessionCore,
  describeFetchError,
  maskSessionToken,
} from '../../../app/static/js/core/session_core.js'
import {
  DarklabHistoryCore,
  labelForType,
  summaryLabel,
} from '../../../app/static/js/core/history_core.js'
import {
  DarklabRunnerCore,
  formatElapsed,
  parseSyntheticPostFilterCommand,
} from '../../../app/static/js/core/runner_core.js'
import {
  DarklabWorkspaceCore,
  displayPath,
  normalizeCommandPath,
} from '../../../app/static/js/core/workspace_core.js'
import {
  DarklabOutputCore,
  buildPromptLabel,
  normalizeSignals,
} from '../../../app/static/js/core/output_core.js'
import { setRuntimeHandlers } from '../../../app/static/js/runtime_bridge.js'
import {
  _runtimeWorkspaceCwd,
  loadSessionVariables,
} from '../../../app/static/js/features/autocomplete/runtime_context.js'
import {
  appendLine,
  appendLines,
  buildPromptLabel as outputBuildPromptLabel,
  createAnsiUpRenderer,
  currentPromptWorkspacePath,
  _renderAnsiWithEntityTokens,
  renderRestoredTabOutput,
} from '../../../app/static/js/output.js'
import {
  ExportHtmlUtils,
  buildExportMetaLine,
  renderExportPromptEcho,
} from '../../../app/static/js/export_html.js'
import {
  ExportPdfUtils,
  buildTerminalExportPdf,
} from '../../../app/static/js/export_pdf.js'
import {
  attachActiveRunFromMonitor,
  confirmKill,
  doKill,
  runCommand,
  submitCommand,
} from '../../../app/static/js/runner.js'
import {
  _ensureWorkspaceCache,
  _resolveWorkspaceCommandPath,
  _workspacePathExists,
} from '../../../app/static/js/features/runner/runner_workspace.js'
import {
  _isActiveRunDetachedForRestore,
  _pruneDetachedActiveRunRestoreIds,
  clearActiveRunDetachedForRestore,
  markActiveRunDetachedForRestore,
} from '../../../app/static/js/features/runner/runner_active_restore.js'
import {
  DarklabRunnerPersistence,
  createRunnerPersistence,
} from '../../../app/static/js/features/runner/runner_persistence.js'
import {
  attachInteractivePtyCommand,
  focusActiveInteractivePty,
  isInteractivePtyCommand,
  startInteractivePtyCommand,
} from '../../../app/static/js/pty.js'
import {
  DarklabSearchCore,
  formatFindingSummary,
  searchInputPlaceholder,
} from '../../../app/static/js/core/search_core.js'
import { bindPressable } from '../../../app/static/js/ui/ui_pressable.js'
import { bindDisclosure } from '../../../app/static/js/ui/ui_disclosure.js'
import {
  DarklabDismissible,
  bindDismissible,
  closeTopmostDismissible,
} from '../../../app/static/js/ui/ui_dismissible.js'
import { bindOutsideClickClose } from '../../../app/static/js/ui/ui_outside_click.js'
import { bindFocusTrap } from '../../../app/static/js/ui/ui_focus_trap.js'
import { bindMobileSheet } from '../../../app/static/js/ui/mobile_sheet.js'
import {
  DarklabTabStripEdges,
  bindTabStripEdgeListener,
  syncTabStripEdges,
} from '../../../app/static/js/ui/ui_tab_strip_edges.js'
import {
  closeActionSheet,
  openActionSheet,
} from '../../../app/static/js/ui/ui_action_sheet.js'
import {
  cancelConfirm,
  isConfirmOpen,
  showConfirm,
} from '../../../app/static/js/ui/ui_confirm.js'
import {
  focusElement,
  getComposerInputs,
  getComposerValue,
  getMobileKeyboardOffsetBaseline,
  getMobileViewportClosedHeight,
  isFaqOverlayOpen,
  hideSearchBar,
  hideWorkspaceOverlay,
  isOptionsOverlayOpen,
  isSearchBarOpen,
  isThemeOverlayOpen,
  isWorkflowsOverlayOpen,
  isWorkspaceOverlayOpen,
  refocusComposerAfterAction,
  setComposerValue,
  setVisibilityState,
  showWorkspaceOverlay,
  syncFocusedComposerState,
  syncMobileComposerKeyboardState,
  syncRunButtonDisabled,
  togglePanelOverlay,
} from '../../../app/static/js/ui/ui_helpers.js'
import {
  findWordBoundaryLeft,
  findWordBoundaryRight,
  getInputSelection,
  isTerminalWordChar,
} from '../../../app/static/js/features/terminal/composer_editing.js'
import {
  bindMobileComposerKeyboardListeners,
  bindMobileComposerSubmitAndInputListeners,
  queueMobileComposerKeyboardSync,
  syncMobileComposerKeyboard,
  syncMobileViewportHeight,
} from '../../../app/static/js/features/terminal/mobile_composer_keyboard.js'
import { createMobileRunningIndicator } from '../../../app/static/js/features/mobile/mobile_running_indicator.js'
import { dispatchMobileMenuAction } from '../../../app/static/js/features/mobile/mobile_menu_actions.js'
import {
  _cliAppendLine,
  _cliConfigEntries,
  _cliThemeEntries,
  handleConfigCommand,
  handleThemeCommand,
} from '../../../app/static/js/features/terminal/local_commands.js'
import {
  _syncTabDraggable,
  bindTabDragReorder,
} from '../../../app/static/js/features/tabs/tab_drag_reorder.js'
import {
  closeTab,
  confirmCloseRunningTab,
  finalizeClosingTab,
} from '../../../app/static/js/features/tabs/tab_close_lifecycle.js'
import {
  TAB_SESSION_STATE_KEY,
  restoreTabSessionState,
  schedulePersistTabSessionState,
} from '../../../app/static/js/features/tabs/tab_session_state.js'
import {
  copyTab,
  exportTabHtml,
  permalinkTab,
  saveTab,
} from '../../../app/static/js/features/tabs/tab_exports.js'
import {
  activateTab,
  clearTab,
  createTab,
  updateTabScrollButtons,
} from '../../../app/static/js/tabs.js'
import {
  clearSearch,
  navigateSearch,
  runSearch,
  setSearchScope,
} from '../../../app/static/js/search.js'
import {
  _toggleStar,
  reloadSessionHistory,
} from '../../../app/static/js/features/history/history_actions.js'
import { copyHistoryRunPermalink } from '../../../app/static/js/features/history/history_links.js'
import { enterHistSearch } from '../../../app/static/js/features/history/history_search.js'
import {
  restoreHistoryRun,
  restoreHistoryRunIntoTab,
} from '../../../app/static/js/features/history/history_restore.js'
import { _createHistoryEntry } from '../../../app/static/js/features/history/history_rows.js'
import { confirmHistAction } from '../../../app/static/js/features/history/history_mutations.js'
import { _historyLoadProjects } from '../../../app/static/js/features/history/history_project_actions.js'
import { hydrateCmdHistory } from '../../../app/static/js/features/history/history_recall.js'
import {
  closeHistoryRunOverlay,
  cycleHistoryRunOverlayTab,
  isHistoryRunOverlayOpen,
  openHistoryRunDetails,
} from '../../../app/static/js/features/history/history_run_details.js'
import {
  openHistoryWithFilters,
  refreshHistoryPanel,
  renderHistory,
} from '../../../app/static/js/history.js'
import {
  DarklabHistoryCompareCore,
  coerceViewMode,
  viewportMode,
} from '../../../app/static/js/features/run-comparison/history_compare_core.js'
import {
  _historyCompareSummaryText,
} from '../../../app/static/js/features/run-comparison/history_compare_controls.js'
import { openHistoryCompareLauncher } from '../../../app/static/js/features/run-comparison/history_compare_launcher.js'
import { _renderHistoryCompareNav } from '../../../app/static/js/features/run-comparison/history_compare_navigation.js'
import { closeHistoryCompareOverlay } from '../../../app/static/js/features/run-comparison/history_compare_overlay.js'
import { fetchAndRenderHistoryComparison } from '../../../app/static/js/features/run-comparison/history_compare_renderer.js'
import {
  fetchAndRenderHistoryComparison as bridgeFetchAndRenderHistoryComparison,
  hasHistoryCompareHandler,
  openHistoryCompareLauncher as bridgeOpenHistoryCompareLauncher,
  setHistoryCompareHandlers,
} from '../../../app/static/js/features/run-comparison/history_compare_bridge.js'
import {
  hasHistoryRunModalStateHandler,
  openHistoryRunDetails as bridgeOpenHistoryRunDetails,
  setHistoryRunModalStateHandlers,
} from '../../../app/static/js/features/history/history_run_modal_state_bridge.js'
import {
  activateOptionsTab,
  applyCompareContextPreference,
  applyCompareViewModePreference,
  applyHudClockPreference,
  applyPromptUsernamePreference,
  applyRunNotifyPreference,
  applyThemePreference,
  applyTimestampPreference,
  cycleOptionsTab,
  getOptionsModalLastTabPreference,
  getPreference,
  loadSessionPreferences,
  syncOptionsControls,
} from '../../../app/static/js/features/preferences/preferences.js'
import {
  handleSecretCommand,
  invalidateOptionsSecrets,
  openProviderStatusModal,
  openSecretEditor,
  refreshOptionsSecrets,
} from '../../../app/static/js/features/preferences/secrets_panel.js'
import { _updateOptionsSessionTokenStatus } from '../../../app/static/js/features/preferences/session_token_controls.js'
import { refreshOptionsTeams } from '../../../app/static/js/features/preferences/teams_panel.js'
import {
  openNotificationChannelEditor,
  refreshNotificationChannels,
} from '../../../app/static/js/features/preferences/notification_channels.js'
import {
  closeCommandCatalogModal,
  closeCommandRegistry,
  hideCommandRegistryOverlay,
  openCommandCatalogModal,
  openCommandRegistry,
  renderCommandCatalogModal,
  renderCommandRegistry,
  showCommandRegistryOverlay,
} from '../../../app/static/js/features/command-registry/command_registry.js'
import {
  _runtimeWorkflowContext,
  closeWorkflowEditor,
  ensureWorkflowCatalogLoaded,
  handleWorkflowTerminalCommand,
  openWorkflowEditor,
  reloadWorkflowCatalog,
  renderWorkflowItems,
} from '../../../app/static/js/features/workflows/workflows.js'
import {
  closeSchedulesModal,
  isSchedulesOverlayOpen,
  openSchedulesModal,
} from '../../../app/static/js/features/schedules/schedules_modal.js'
import {
  closeWatchersModal,
  isWatchersOverlayOpen,
  openWatchersModal,
} from '../../../app/static/js/features/watchers/watchers_modal.js'
import {
  _renderTourIllustration,
  _visibleTourModalChapters,
  closeTourModal,
  openTourModal,
} from '../../../app/static/js/tour_modal.js'
import {
  DarklabStatusMonitorCore,
  exitCodeLabel,
  formatMemoryBytes,
} from '../../../app/static/js/features/status-monitor/status_monitor_core.js'
import { DarklabStatusMonitorData } from '../../../app/static/js/features/status-monitor/status_monitor_data.js'
import {
  DarklabStatusMonitorResources,
  createStatusMonitorResources,
} from '../../../app/static/js/features/status-monitor/status_monitor_resources.js'
import {
  closeStatusMonitor,
  isStatusMonitorOpen,
  openStatusMonitor,
  refreshStatusMonitor,
} from '../../../app/static/js/status_monitor.js'
import {
  closeFindingsBoard,
  isFindingsBoardOpen,
  openFindingsBoard,
} from '../../../app/static/js/features/findings/findings_board_modal.js'
import {
  DarklabAtlasTabs,
  countForTab,
  labelForType as labelForAtlasType,
  tabById,
  totalEntityCount,
} from '../../../app/static/js/features/atlas/atlas_tabs.js'
import {
  DarklabAtlasEntityRow,
  renderAtlasEntityRow,
  renderProjectEntityRow,
} from '../../../app/static/js/features/atlas/atlas_entity_row.js'
import {
  DarklabAtlasDetail,
  formatCount as formatAtlasDetailCount,
  renderDetail as renderAtlasDetail,
  renderFindingDetail as renderAtlasFindingDetail,
} from '../../../app/static/js/features/atlas/atlas_entity_detail.js'
import {
  DarklabEntityMetadata,
  parseLabelInput as parseEntityMetadataLabels,
} from '../../../app/static/js/ui/ui_entity_metadata.js'
import {
  getWorkspaceAutocompleteDirectoryHints,
  getWorkspaceAutocompleteFileHints,
  getWorkspaceDirectoryEntries,
  refreshWorkspaceFileCache,
} from '../../../app/static/js/features/workspace/workspace_autocomplete_cache.js'
import {
  DarklabWorkspaceViewerFormats,
  viewerPayload as workspaceViewerPayload,
  viewerRawText as workspaceViewerRawText,
} from '../../../app/static/js/features/workspace/workspace_viewer_formats.js'
import {
  DarklabAtlasOverlay,
  closeAtlas,
  cycleAtlasTab,
  isAtlasOverlayOpen,
  openAtlas,
  refreshAtlasOverlay,
} from '../../../app/static/js/features/atlas/atlas_overlay.js'
import { setAtlasHandlers } from '../../../app/static/js/features/atlas/atlas_bridge.js'
import { DarklabAtlasMobile } from '../../../app/static/js/features/atlas/atlas_mobile.js'
import { ProjectTargetValidation } from '../../../app/static/js/features/projects/project_target_validation.js'
import { cycleProjectWorkspaceTab } from '../../../app/static/js/features/projects/project_context_bridge.js'
import { DarklabProjectWorkspaceConstants } from '../../../app/static/js/features/projects/project_workspace_constants.js'
import { DarklabProjectWorkspaceState } from '../../../app/static/js/features/projects/project_workspace_state.js'
import { DarklabProjectActiveContext } from '../../../app/static/js/features/projects/project_active_context.js'
import { DarklabProjectSharedUi } from '../../../app/static/js/features/projects/project_shared_ui.js'
import { DarklabProjectDetails } from '../../../app/static/js/features/projects/project_details.js'
import { DarklabProjectList } from '../../../app/static/js/features/projects/project_list.js'
import { DarklabProjectNavigation } from '../../../app/static/js/features/projects/project_navigation.js'
import { DarklabProjectEntityEditor } from '../../../app/static/js/features/projects/project_entity_editor.js'
import { DarklabProjectWorkspaceActions } from '../../../app/static/js/features/projects/project_workspace_actions.js'
import { DarklabProjectWorkspaceShell } from '../../../app/static/js/features/projects/project_workspace_shell.js'
import { DarklabProjectWorkspaceLifecycle } from '../../../app/static/js/features/projects/project_workspace_lifecycle.js'
import { DarklabProjectWorkspaceRenderer } from '../../../app/static/js/features/projects/project_workspace_renderer.js'
import { DarklabProjectWorkspaceBootstrap } from '../../../app/static/js/features/projects/project_workspace_bootstrap.js'
import { DarklabProjectNestedSheets } from '../../../app/static/js/features/projects/project_nested_sheets.js'
import { DarklabProjectWorkspaceEvents } from '../../../app/static/js/features/projects/project_workspace_events.js'
import { DarklabProjectTargets } from '../../../app/static/js/features/projects/project_targets.js'
import { DarklabProjectRuns } from '../../../app/static/js/features/projects/project_runs.js'
import { DarklabProjectMobileCompare } from '../../../app/static/js/features/projects/project_mobile_compare.js'
import { DarklabProjectMobileShell } from '../../../app/static/js/features/projects/project_mobile_shell.js'
import { DarklabProjectMobileDetail } from '../../../app/static/js/features/projects/project_mobile_detail.js'
import {
  DarklabProjectFindingsData,
  boardWorkflowState,
} from '../../../app/static/js/features/projects/project_findings_data.js'
import { DarklabProjectFilters } from '../../../app/static/js/features/projects/project_filters.js'
import { DarklabProjectEntities } from '../../../app/static/js/features/projects/project_entities.js'
import { DarklabProjectFindings } from '../../../app/static/js/features/projects/project_findings.js'
import { DarklabProjectFindingsBoard } from '../../../app/static/js/features/projects/project_findings_board.js'
import { DarklabProjectReport } from '../../../app/static/js/features/projects/project_report.js'
import { DarklabProjectActivity } from '../../../app/static/js/features/projects/project_activity.js'
import { DarklabProjectArtifacts } from '../../../app/static/js/features/projects/project_artifacts.js'
import { DarklabProjectOverview } from '../../../app/static/js/features/projects/project_overview.js'
import { DarklabProjectPackages } from '../../../app/static/js/features/projects/project_packages.js'

let freshModuleCounter = 0

function freshModuleUrl(relativePath) {
  freshModuleCounter += 1
  return `${new URL(relativePath, import.meta.url).href}?fresh=${freshModuleCounter}`
}

function snapshotGlobals(target, names) {
  return new Map(names.map((name) => [
    name,
    {
      exists: Object.prototype.hasOwnProperty.call(target, name),
      value: target[name],
    },
  ]))
}

function restoreGlobals(target, snapshot) {
  snapshot.forEach((entry, name) => {
    if (entry.exists) {
      target[name] = entry.value
    } else {
      delete target[name]
    }
  })
}

describe('core ESM exports', () => {
  it('exports representative core helpers as ESM APIs', () => {
    expect(escapeHtml('<b>safe</b>')).toBe('&lt;b&gt;safe&lt;/b&gt;')
    expect(applyRedactionRules('token=secret', [{ pattern: 'secret', replacement: '[redacted]' }]))
      .toBe('token=[redacted]')
    expect(DarklabSessionCore.maskSessionToken).toBe(maskSessionToken)
    expect(DarklabHistoryCore.labelForType).toBe(labelForType)
    expect(DarklabRunnerCore.formatElapsed).toBe(formatElapsed)
    expect(DarklabWorkspaceCore.displayPath).toBe(displayPath)
    expect(DarklabOutputCore.buildPromptLabel).toBe(buildPromptLabel)
    expect(DarklabPreferenceCore.coerceLineNumberMode).toBe(coerceLineNumberMode)
    expect(DarklabAutocompleteCore.filterItems).toBe(filterItems)
    expect(DarklabRunOutputModel.fromWireLineEvent).toBe(fromWireLineEvent)
    expect(DarklabSearchCore.formatFindingSummary).toBe(formatFindingSummary)
  })

  it('distinguishes loaded bridge wrappers from registered lazy handlers', () => {
    const compareHandler = vi.fn(() => 'compare-opened')
    const detailsHandler = vi.fn(() => 'details-opened')
    try {
      setHistoryCompareHandlers({
        fetchAndRenderHistoryComparison: null,
        openHistoryCompareLauncher: null,
      })
      setHistoryRunModalStateHandlers({ openHistoryRunDetails: null })

      expect(bridgeFetchAndRenderHistoryComparison.hasHandler()).toBe(false)
      expect(bridgeOpenHistoryCompareLauncher.hasHandler()).toBe(false)
      expect(bridgeOpenHistoryRunDetails.hasHandler()).toBe(false)
      expect(hasHistoryCompareHandler('fetchAndRenderHistoryComparison')).toBe(false)
      expect(hasHistoryRunModalStateHandler('openHistoryRunDetails')).toBe(false)
      expect(bridgeFetchAndRenderHistoryComparison('run-left', 'run-right')).toBeUndefined()
      expect(bridgeOpenHistoryCompareLauncher({ id: 'run-left' })).toBeUndefined()
      expect(bridgeOpenHistoryRunDetails({ id: 'run-left' })).toBeUndefined()

      setHistoryCompareHandlers({
        fetchAndRenderHistoryComparison: compareHandler,
        openHistoryCompareLauncher: compareHandler,
      })
      setHistoryRunModalStateHandlers({ openHistoryRunDetails: detailsHandler })

      expect(bridgeFetchAndRenderHistoryComparison.hasHandler()).toBe(true)
      expect(bridgeOpenHistoryCompareLauncher.hasHandler()).toBe(true)
      expect(bridgeOpenHistoryRunDetails.hasHandler()).toBe(true)
      expect(bridgeFetchAndRenderHistoryComparison('run-left', 'run-right')).toBe('compare-opened')
      expect(bridgeOpenHistoryCompareLauncher({ id: 'run-left' })).toBe('compare-opened')
      expect(bridgeOpenHistoryRunDetails({ id: 'run-left' })).toBe('details-opened')
    } finally {
      setHistoryCompareHandlers({
        fetchAndRenderHistoryComparison: null,
        openHistoryCompareLauncher: null,
      })
      setHistoryRunModalStateHandlers({ openHistoryRunDetails: null })
    }
  })

  it('keeps Project Runs compare honest when the ESM bridge handler is not ready', () => {
    const bridgeGlobal = typeof window !== 'undefined' ? window : globalThis
    const globals = snapshotGlobals(bridgeGlobal, ['fetchAndRenderHistoryComparison'])
    const fallbackCompare = vi.fn()
    try {
      const controller = DarklabProjectRuns.createProjectRunsController({})
      setHistoryCompareHandlers({ fetchAndRenderHistoryComparison: null })
      bridgeGlobal.fetchAndRenderHistoryComparison = fallbackCompare

      controller.compareRuns('project-1', 'run-1', 'run', 'run-2')

      expect(fallbackCompare).toHaveBeenCalledWith('run-1', 'run-2', {
        url: '/history/compare?left=run-1&project_id=project-1&right=run-2',
      })

      delete bridgeGlobal.fetchAndRenderHistoryComparison
      expect(() => controller.compareRuns('project-1', 'run-1', 'run', 'run-2'))
        .toThrow('Run comparison is not available.')
    } finally {
      setHistoryCompareHandlers({ fetchAndRenderHistoryComparison: null })
      restoreGlobals(bridgeGlobal, globals)
    }
  })

  it('exports representative owner APIs without requiring browser-global mirrors', async () => {
    expect(appendLine).toBeTypeOf('function')
    expect(buildExportMetaLine).toBeTypeOf('function')
    expect(buildTerminalExportPdf).toBeTypeOf('function')
    expect(runCommand).toBeTypeOf('function')
    expect(attachInteractivePtyCommand).toBeTypeOf('function')
    expect(runSearch).toBeTypeOf('function')
    expect(refreshHistoryPanel).toBeTypeOf('function')
    expect(fetchAndRenderHistoryComparison).toBeTypeOf('function')
    expect(loadSessionPreferences).toBeTypeOf('function')
    expect(openCommandRegistry).toBeTypeOf('function')
    expect(ensureWorkflowCatalogLoaded).toBeTypeOf('function')
    expect(openStatusMonitor).toBeTypeOf('function')
    expect(openAtlas).toBeTypeOf('function')
    expect(DarklabProjectWorkspaceState).toBeTruthy()
    expect(DarklabProjectOverview.createProjectOverviewController).toBeTypeOf('function')

    const bridgeGlobal = typeof window !== 'undefined' ? window : globalThis
    const globals = snapshotGlobals(bridgeGlobal, [
      'APP_CONFIG',
      '__darklabRunnerHandlers',
      '__darklabTabHandlers',
      'DarklabRunner',
      'DarklabTabs',
    ])
    const originalWarn = bridgeGlobal.console.warn
    const originalError = bridgeGlobal.console.error
    try {
      const diagnostics = []
      bridgeGlobal.console.warn = (...args) => diagnostics.push(args)
      bridgeGlobal.console.error = (...args) => diagnostics.push(args)
      bridgeGlobal.APP_CONFIG = { frontend_bridge_warnings: true }
      delete bridgeGlobal.__darklabRunnerHandlers
      delete bridgeGlobal.__darklabTabHandlers
      delete bridgeGlobal.DarklabRunner
      delete bridgeGlobal.DarklabTabs

      const runnerBridge = await import(freshModuleUrl('../../../app/static/js/runner_bridge.js'))
      const tabsBridge = await import(freshModuleUrl('../../../app/static/js/tabs_bridge.js'))
      const outputBridge = await import(freshModuleUrl('../../../app/static/js/output_bridge.js'))
      const historyCompareBridge = await import(
        freshModuleUrl('../../../app/static/js/features/run-comparison/history_compare_bridge.js')
      )
      const historyRunModalStateBridge = await import(
        freshModuleUrl('../../../app/static/js/features/history/history_run_modal_state_bridge.js')
      )

      expect(runnerBridge.runCommand('echo ok')).toBeUndefined()
      expect(runnerBridge.runCommand('echo ok')).toBeUndefined()
      expect(tabsBridge.createTab('Imported tab')).toBeNull()
      await expect(outputBridge.appendLines([])).resolves.toBeUndefined()
      expect(historyCompareBridge.openHistoryCompareLauncher()).toBeUndefined()
      expect(historyCompareBridge.openHistoryCompareLauncher()).toBeUndefined()
      expect(historyRunModalStateBridge.openHistoryRunDetails({ id: 'run-missing' })).toBeUndefined()
      expect(historyRunModalStateBridge.openHistoryRunDetails({ id: 'run-missing' })).toBeUndefined()

      expect(diagnostics.filter(args => args[0] === '[darklab] RUNNER_BRIDGE_HANDLER_MISSING'))
        .toHaveLength(1)
      expect(diagnostics).toContainEqual([
        '[darklab] RUNNER_BRIDGE_HANDLER_MISSING',
        expect.objectContaining({
          event: 'RUNNER_BRIDGE_HANDLER_MISSING',
          level: 'error',
          handler: 'runCommand',
        }),
      ])
      expect(diagnostics).toContainEqual([
        '[darklab] TABS_BRIDGE_HANDLER_MISSING',
        expect.objectContaining({
          event: 'TABS_BRIDGE_HANDLER_MISSING',
          level: 'warning',
          handler: 'createTab',
        }),
      ])
      expect(diagnostics).toContainEqual([
        '[darklab] OUTPUT_BRIDGE_HANDLER_MISSING',
        expect.objectContaining({
          event: 'OUTPUT_BRIDGE_HANDLER_MISSING',
          level: 'error',
          handler: 'appendLines',
        }),
      ])
      expect(diagnostics.filter(args => args[0] === '[darklab] HISTORY_COMPARE_HANDLER_MISSING'))
        .toHaveLength(1)
      expect(diagnostics).toContainEqual([
        '[darklab] HISTORY_COMPARE_HANDLER_MISSING',
        expect.objectContaining({
          event: 'HISTORY_COMPARE_HANDLER_MISSING',
          level: 'warning',
          handler: 'openHistoryCompareLauncher',
        }),
      ])
      expect(diagnostics.filter(args => args[0] === '[darklab] HISTORY_RUN_MODAL_STATE_HANDLER_MISSING'))
        .toHaveLength(1)
      expect(diagnostics).toContainEqual([
        '[darklab] HISTORY_RUN_MODAL_STATE_HANDLER_MISSING',
        expect.objectContaining({
          event: 'HISTORY_RUN_MODAL_STATE_HANDLER_MISSING',
          level: 'warning',
          handler: 'openHistoryRunDetails',
        }),
      ])
    } finally {
      bridgeGlobal.console.warn = originalWarn
      bridgeGlobal.console.error = originalError
      restoreGlobals(bridgeGlobal, globals)
    }
  })

  it('keeps mutable app state behind the explicit state API', () => {
    const nextTabs = [{ id: 'state-esm-tab', title: 'State API' }]
    setTabs(nextTabs)
    setActiveTabId('state-esm-tab')
    expect(getTabs()).toBe(nextTabs)
    expect(getActiveTabId()).toBe('state-esm-tab')
    expect(APP_STATE_API.getTabs()).toBe(nextTabs)
    expect(APP_STATE_API.getActiveTabId()).toBe('state-esm-tab')

    const originalEmitUiEvent = globalThis.emitUiEvent
    const originalOnUiEvent = globalThis.onUiEvent
    try {
      let emittedArgs = null
      globalThis.emitUiEvent = (...args) => {
        emittedArgs = args
        return 'updated-emit'
      }
      expect(emitUiEvent('app:test', { value: 1 })).toBe('updated-emit')
      expect(emittedArgs).toEqual(['app:test', { value: 1 }])

      const unsubscribe = () => 'removed'
      const handler = () => {}
      const options = { once: true }
      let subscribedArgs = null
      globalThis.onUiEvent = (...args) => {
        subscribedArgs = args
        return unsubscribe
      }
      expect(onUiEvent('app:test', handler, options)).toBe(unsubscribe)
      expect(subscribedArgs).toEqual(['app:test', handler, options])
    } finally {
      globalThis.emitUiEvent = originalEmitUiEvent
      globalThis.onUiEvent = originalOnUiEvent
    }
  })

  it('builds workspace prompt labels from ESM tab state without a global cwd reader', () => {
    const originalTabs = getTabs()
    const originalActiveTabId = getActiveTabId()
    const originalConfig = getAppConfig()
    const originalGlobalWorkspaceCwd = globalThis._workspaceCwd
    const originalWindowWorkspaceCwd = typeof window !== 'undefined' ? window._workspaceCwd : undefined
    try {
      delete globalThis._workspaceCwd
      if (typeof window !== 'undefined') delete window._workspaceCwd
      setAppConfig({ ...originalConfig, workspace_enabled: true })
      setTabs([{ id: 'prompt-esm-tab', workspaceCwd: 'reports/nuclei' }])
      setActiveTabId('prompt-esm-tab')

      expect(currentPromptWorkspacePath()).toBe('/reports/nuclei')
      expect(outputBuildPromptLabel()).toContain(':/reports/nuclei $')
    } finally {
      setTabs(originalTabs)
      setActiveTabId(originalActiveTabId)
      setAppConfig(originalConfig)
      if (typeof originalGlobalWorkspaceCwd === 'function') {
        globalThis._workspaceCwd = originalGlobalWorkspaceCwd
      }
      if (typeof window !== 'undefined' && typeof originalWindowWorkspaceCwd === 'function') {
        window._workspaceCwd = originalWindowWorkspaceCwd
      }
    }
  })

  it('builds autocomplete workspace cwd from the imported workspace helper', () => {
    const originalTabs = getTabs()
    const originalActiveTabId = getActiveTabId()
    const originalGlobalWorkspaceCwd = globalThis._workspaceCwd
    const originalWindowWorkspaceCwd = typeof window !== 'undefined' ? window._workspaceCwd : undefined
    try {
      delete globalThis._workspaceCwd
      if (typeof window !== 'undefined') delete window._workspaceCwd
      setTabs([{ id: 'autocomplete-esm-tab', workspaceCwd: ' reports / nuclei ' }])
      setActiveTabId('autocomplete-esm-tab')

      expect(_runtimeWorkspaceCwd()).toBe('reports/nuclei')
    } finally {
      setTabs(originalTabs)
      setActiveTabId(originalActiveTabId)
      if (typeof originalGlobalWorkspaceCwd === 'function') {
        globalThis._workspaceCwd = originalGlobalWorkspaceCwd
      }
      if (typeof window !== 'undefined' && typeof originalWindowWorkspaceCwd === 'function') {
        window._workspaceCwd = originalWindowWorkspaceCwd
      }
    }
  })

  it('opens Atlas entity chips through the imported bridge without a global opener', async () => {
    const bridgeGlobal = typeof window !== 'undefined' ? window : globalThis
    const globals = snapshotGlobals(bridgeGlobal, ['openAtlas'])
    const originalBody = document.body.innerHTML
    const openSpy = vi.fn()
    try {
      delete bridgeGlobal.openAtlas
      setAtlasHandlers({ openAtlas: openSpy })

      const line = document.createElement('div')
      line.className = 'line'
      const content = document.createElement('span')
      content.className = 'line-content'
      _renderAnsiWithEntityTokens(content, 'scan ip.darklab.sh', [{
        type: 'domain',
        value: 'ip.darklab.sh',
        canonical_value: 'ip.darklab.sh',
        start: 5,
        end: 18,
      }], 'atlas-chip-tab')
      line.appendChild(content)
      document.body.appendChild(line)

      await vi.waitFor(() => {
        expect(document.querySelector('.atlas-entity-token')).not.toBeNull()
      })

      document.querySelector('.atlas-entity-token')
        .dispatchEvent(new MouseEvent('click', { bubbles: true }))

      expect(openSpy).toHaveBeenCalledWith({
        source: 'output-entity',
        tab: 'domain',
        entityType: 'domain',
        entityValue: 'ip.darklab.sh',
        forceView: 'detail',
        refreshIntel: false,
        addActiveProject: false,
      })
    } finally {
      setAtlasHandlers({ openAtlas })
      document.body.innerHTML = originalBody
      restoreGlobals(bridgeGlobal, globals)
    }
  })

  it('loads session-scoped lazy data through imported runtime fetch without a global mirror', async () => {
    const bridgeGlobal = typeof window !== 'undefined' ? window : globalThis
    const globals = snapshotGlobals(bridgeGlobal, [
      'apiFetch',
      'fetch',
      'showToast',
      'getTabs',
      'getTab',
      'createTab',
      'clearTab',
      'appendLine',
      'setTabStatus',
      'renderCommandOutcomeSummary',
      'hideTabKillBtn',
      '_appendHistoryCommandEcho',
      '_appendHistoryOutputLine',
      'requestAnimationFrame',
    ])
    const runtimeHandlers = bridgeGlobal.__darklabRuntimeHandlers
    const originalRuntimeHandlers = runtimeHandlers
      ? {
          apiFetch: runtimeHandlers.apiFetch,
          logClientError: runtimeHandlers.logClientError,
        }
      : null
    const originalBody = document.body.innerHTML
    const originalTabs = getTabs()
    const originalActiveTabId = getActiveTabId()
    try {
      delete bridgeGlobal.apiFetch
      const fetch = vi.fn(async (url, options = {}) => ({
        ok: true,
        json: async () => ({
          secrets: [{
            name: 'SHODAN_API_KEY',
            consumer_envs: ['SHODAN_API_KEY'],
            updated_at: '2026-05-14T10:00:00+00:00',
          }],
        }),
        url,
        options,
      }))
      bridgeGlobal.fetch = fetch
      bridgeGlobal.showToast = vi.fn()
      bridgeGlobal.requestAnimationFrame = (callback) => setTimeout(callback, 0)
      document.body.innerHTML = `
        <button id="options-provider-status-btn"></button>
        <button id="options-secret-new-btn"></button>
        <button id="options-secrets-refresh-btn"></button>
        <div id="options-secrets-msg"></div>
        <div id="options-secrets-list"></div>
        <div id="tabs-bar"></div>
        <div id="tab-panels"></div>
        <input id="cmd" />
        <span id="status"></span>
      `

      invalidateOptionsSecrets()
      await refreshOptionsSecrets({ force: true })

      expect(fetch).toHaveBeenCalledWith('/session/secrets', expect.objectContaining({
        cache: 'no-store',
        headers: expect.objectContaining({
          'X-Session-ID': expect.any(String),
        }),
      }))
      expect(document.getElementById('options-secrets-list').textContent).toContain('SHODAN_API_KEY')
      expect(bridgeGlobal.showToast).not.toHaveBeenCalledWith(expect.stringContaining('apiFetch unavailable'), 'error')

      const runtimeApiFetch = vi.fn(async (url) => {
        if (url === '/session/variables') {
          return {
            ok: true,
            json: async () => ({ variables: [{ name: 'TARGET_HOST', value: 'darklab.sh' }] }),
          }
        }
        if (url === '/history/run-restored?json') {
          return {
            ok: true,
            json: async () => ({
              id: 'run-restored',
              command: 'nmap darklab.sh',
              exit_code: 0,
              full_output_available: true,
              output_entries: [{ text: 'open', cls: 'stdout' }],
            }),
          }
        }
        if (url === '/history/compare?left=run-left&right=run-right') {
          return {
            ok: true,
            json: async () => ({
              left_run_id: 'run-left',
              right_run_id: 'run-right',
              left: { id: 'run-left', command: 'nmap old', exit_code: 0, output_line_count: 1 },
              right: { id: 'run-right', command: 'nmap new', exit_code: 0, output_line_count: 1 },
              deltas: {},
              totals: { changed_lines: 0 },
              hunks: [],
              objects: {},
            }),
          }
        }
        throw new Error(`unexpected runtime fetch ${url}`)
      })
      setRuntimeHandlers({ apiFetch: runtimeApiFetch, logClientError: vi.fn() })
      const rawFetch = vi.fn(() => Promise.reject(new Error('raw fetch should not be used')))
      bridgeGlobal.fetch = rawFetch

      await expect(loadSessionVariables()).resolves.toEqual([
        { name: 'TARGET_HOST', value: 'darklab.sh' },
      ])

      bridgeGlobal.getTabs = vi.fn(() => [])
      bridgeGlobal.getTab = vi.fn(() => null)
      bridgeGlobal.createTab = vi.fn(() => 'legacy-tab')
      bridgeGlobal.clearTab = vi.fn()
      bridgeGlobal.appendLine = vi.fn()
      bridgeGlobal.setTabStatus = vi.fn()
      bridgeGlobal.renderCommandOutcomeSummary = vi.fn()
      bridgeGlobal.hideTabKillBtn = vi.fn()
      bridgeGlobal._appendHistoryCommandEcho = vi.fn()
      bridgeGlobal._appendHistoryOutputLine = vi.fn()

      await expect(restoreHistoryRunIntoTab({
        id: 'run-restored',
        full_output_available: true,
      })).resolves.toBe('tab-1')
      expect(bridgeGlobal.createTab).not.toHaveBeenCalled()
      expect(bridgeGlobal.getTab).not.toHaveBeenCalled()

      fetchAndRenderHistoryComparison('run-left', 'run-right')
      await Promise.resolve()
      await Promise.resolve()

      expect(runtimeApiFetch).toHaveBeenCalledWith('/session/variables')
      expect(runtimeApiFetch).toHaveBeenCalledWith('/history/run-restored?json')
      expect(runtimeApiFetch).toHaveBeenCalledWith('/history/compare?left=run-left&right=run-right', undefined)
      expect(rawFetch).not.toHaveBeenCalled()
    } finally {
      setTabs(originalTabs)
      setActiveTabId(originalActiveTabId)
      document.body.innerHTML = originalBody
      if (runtimeHandlers && originalRuntimeHandlers) {
        runtimeHandlers.apiFetch = originalRuntimeHandlers.apiFetch
        runtimeHandlers.logClientError = originalRuntimeHandlers.logClientError
      }
      restoreGlobals(bridgeGlobal, globals)
      invalidateOptionsSecrets()
    }
  })

  it('returns loaded lazy module API objects through the runtime loader contract', async () => {
    const lazyGlobal = typeof window !== 'undefined' ? window : globalThis
    const globals = snapshotGlobals(lazyGlobal, [
      '__darklabImportModule',
      'loadLazyAsset',
      'loadExportPdfUtils',
      'loadFindingsBoard',
    ])
    const originalLazyAssetsJson = document.getElementById('lazy-assets-json')
    const lazyAssetsJson = document.createElement('script')
    lazyAssetsJson.id = 'lazy-assets-json'
    lazyAssetsJson.type = 'application/json'
    lazyAssetsJson.textContent = JSON.stringify({
      export_pdf: { url: '/static/js/export_pdf.contract.js', type: 'module' },
      findings_board: { url: '/static/js/findings_board.contract.js', type: 'module' },
    })
    const importCalls = []
    try {
      originalLazyAssetsJson?.remove()
      document.body.appendChild(lazyAssetsJson)
      lazyGlobal.__darklabImportModule = vi.fn(async (src) => {
        importCalls.push(src)
        if (src.includes('export_pdf.contract.js')) {
          return {
            ExportPdfUtils: {
              buildTerminalExportPdf: () => 'pdf-doc',
              loadJsPdf: () => 'js-pdf',
            },
          }
        }
        if (src.includes('findings_board.contract.js')) {
          return {
            openFindingsBoard: () => 'opened',
            closeFindingsBoard: () => 'closed',
            isFindingsBoardOpen: () => true,
          }
        }
        throw new Error(`unexpected import ${src}`)
      })

      await import(freshModuleUrl('../../../app/static/js/core/lazy_assets.js'))

      const rawModule = await lazyGlobal.loadLazyAsset('export_pdf')
      expect(rawModule.ExportPdfUtils.buildTerminalExportPdf()).toBe('pdf-doc')

      const pdfUtils = await lazyGlobal.loadExportPdfUtils()
      expect(pdfUtils.loadJsPdf()).toBe('js-pdf')

      const findingsBoard = await lazyGlobal.loadFindingsBoard()
      expect(findingsBoard.openFindingsBoard()).toBe('opened')
      expect(findingsBoard.closeFindingsBoard()).toBe('closed')
      expect(findingsBoard.isFindingsBoardOpen()).toBe(true)
      expect(importCalls).toEqual([
        '/static/js/export_pdf.contract.js',
        '/static/js/findings_board.contract.js',
      ])
    } finally {
      lazyAssetsJson.remove()
      if (originalLazyAssetsJson) document.body.appendChild(originalLazyAssetsJson)
      restoreGlobals(lazyGlobal, globals)
    }
  })

  it('logs a bounded error when a lazy module API contract is missing', async () => {
    const lazyGlobal = typeof window !== 'undefined' ? window : globalThis
    const globals = snapshotGlobals(lazyGlobal, [
      '__darklabImportModule',
      'loadExportPdfUtils',
    ])
    const originalLazyAssetsJson = document.getElementById('lazy-assets-json')
    const lazyAssetsJson = document.createElement('script')
    const logClientError = vi.fn()
    lazyAssetsJson.id = 'lazy-assets-json'
    lazyAssetsJson.type = 'application/json'
    lazyAssetsJson.textContent = JSON.stringify({
      export_pdf: { url: '/static/js/export_pdf.missing.js?secret=drop-me', type: 'module' },
    })
    try {
      originalLazyAssetsJson?.remove()
      document.body.appendChild(lazyAssetsJson)
      window.DarklabRuntime?.setRuntimeHandlers({ logClientError })
      lazyGlobal.__darklabImportModule = vi.fn(async () => ({
        WrongExport: true,
        helper: () => {},
      }))

      await import(freshModuleUrl('../../../app/static/js/core/lazy_assets.js'))

      await expect(lazyGlobal.loadExportPdfUtils()).rejects.toThrow(
        'Lazy module did not expose export: ExportPdfUtils',
      )
      expect(logClientError).toHaveBeenCalledWith(
        'lazy module export missing',
        expect.any(Error),
        expect.objectContaining({
          event: 'LAZY_MODULE_EXPORT_MISSING',
          level: 'error',
          export_name: 'ExportPdfUtils',
          src: '/static/js/export_pdf.missing.js',
          module_keys: ['WrongExport', 'helper'],
        }),
      )
    } finally {
      window.DarklabRuntime?.setRuntimeHandlers({ logClientError: () => {} })
      lazyAssetsJson.remove()
      if (originalLazyAssetsJson) document.body.appendChild(originalLazyAssetsJson)
      restoreGlobals(lazyGlobal, globals)
    }
  })

  it('exports UI and feature helper primitives as direct imports', () => {
    expect(Array.isArray(searchScopeButtons)).toBe(true)
    expect(bindPressable).toBeTypeOf('function')
    expect(bindDisclosure).toBeTypeOf('function')
    expect(bindDismissible).toBeTypeOf('function')
    expect(bindFocusTrap).toBeTypeOf('function')
    expect(bindMobileSheet).toBeTypeOf('function')
    expect(isTerminalWordChar('a')).toBe(true)
    expect(syncMobileComposerKeyboard).toBeTypeOf('function')
    expect(handleThemeCommand).toBeTypeOf('function')
    expect(cycleOptionsTab).toBeTypeOf('function')
    expect(cycleProjectWorkspaceTab).toBeTypeOf('function')
    expect(dispatchMobileMenuAction).toBeTypeOf('function')
    expect(bindTabDragReorder).toBeTypeOf('function')
    expect(confirmCloseRunningTab).toBeTypeOf('function')
    expect(schedulePersistTabSessionState).toBeTypeOf('function')
    expect(saveTab).toBeTypeOf('function')
    expect(activateTab).toBeTypeOf('function')
  })
})
