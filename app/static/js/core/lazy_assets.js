// Shared lazy asset loader for rarely-used classic scripts.
(function () {
  const _lazyAssetPromises = {};

  function _lazyAssetConfig() {
    let urls = {};
    if (typeof document !== 'undefined') {
      const node = document.getElementById('lazy-assets-json');
      if (node && node.textContent) {
        try {
          const parsed = JSON.parse(node.textContent);
          if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) urls = parsed;
        } catch (_) {
          urls = {};
        }
      }
    }
    const appConfigUrls = typeof window !== 'undefined'
      && window.APP_CONFIG
      && window.APP_CONFIG.lazy_asset_urls;
    if (appConfigUrls && typeof appConfigUrls === 'object' && !Array.isArray(appConfigUrls)) {
      urls = { ...urls, ...appConfigUrls };
    }
    return urls;
  }

  function _lazyAssetUrl(name) {
    const configured = _lazyAssetConfig()[name];
    if (typeof configured === 'string' && configured) return configured;
    if (name === 'export_pdf') return '/static/js/export_pdf.js';
    if (name === 'atlas_tabs') return '/static/js/features/atlas/atlas_tabs.js';
    if (name === 'atlas_entity_row') return '/static/js/features/atlas/atlas_entity_row.js';
    if (name === 'atlas_entity_detail') return '/static/js/features/atlas/atlas_entity_detail.js';
    if (name === 'atlas_overlay') return '/static/js/features/atlas/atlas_overlay.js';
    if (name === 'atlas_mobile') return '/static/js/features/atlas/atlas_mobile.js';
    if (name === 'findings_board') return '/static/js/features/findings/findings_board_modal.js';
    if (name === 'project_activity') return '/static/js/features/projects/project_activity.js';
    if (name === 'project_artifacts') return '/static/js/features/projects/project_artifacts.js';
    if (name === 'project_details') return '/static/js/features/projects/project_details.js';
    if (name === 'project_list') return '/static/js/features/projects/project_list.js';
    if (name === 'project_navigation') return '/static/js/features/projects/project_navigation.js';
    if (name === 'project_entity_editor') return '/static/js/features/projects/project_entity_editor.js';
    if (name === 'project_workspace_actions') return '/static/js/features/projects/project_workspace_actions.js';
    if (name === 'project_workspace_shell') return '/static/js/features/projects/project_workspace_shell.js';
    if (name === 'project_workspace_lifecycle') return '/static/js/features/projects/project_workspace_lifecycle.js';
    if (name === 'project_workspace_renderer') return '/static/js/features/projects/project_workspace_renderer.js';
    if (name === 'project_workspace_bootstrap') return '/static/js/features/projects/project_workspace_bootstrap.js';
    if (name === 'project_nested_sheets') return '/static/js/features/projects/project_nested_sheets.js';
    if (name === 'project_workspace_events') return '/static/js/features/projects/project_workspace_events.js';
    if (name === 'project_targets') return '/static/js/features/projects/project_targets.js';
    if (name === 'project_runs') return '/static/js/features/projects/project_runs.js';
    if (name === 'project_mobile_compare') return '/static/js/features/projects/project_mobile_compare.js';
    if (name === 'project_mobile_shell') return '/static/js/features/projects/project_mobile_shell.js';
    if (name === 'project_mobile_detail') return '/static/js/features/projects/project_mobile_detail.js';
    if (name === 'project_findings_data') return '/static/js/features/projects/project_findings_data.js';
    if (name === 'project_filters') return '/static/js/features/projects/project_filters.js';
    if (name === 'project_entities') return '/static/js/features/projects/project_entities.js';
    if (name === 'project_findings') return '/static/js/features/projects/project_findings.js';
    if (name === 'project_findings_board') return '/static/js/features/projects/project_findings_board.js';
    if (name === 'project_packages') return '/static/js/features/projects/project_packages.js';
    if (name === 'project_report') return '/static/js/features/projects/project_report.js';
    if (name === 'history_compare_core') return '/static/js/features/run-comparison/history_compare_core.js';
    if (name === 'history_compare_overlay') return '/static/js/features/run-comparison/history_compare_overlay.js';
    if (name === 'history_compare_controls') return '/static/js/features/run-comparison/history_compare_controls.js';
    if (name === 'history_compare_navigation') return '/static/js/features/run-comparison/history_compare_navigation.js';
    if (name === 'history_compare_renderer') return '/static/js/features/run-comparison/history_compare_renderer.js';
    if (name === 'history_compare_launcher') return '/static/js/features/run-comparison/history_compare_launcher.js';
    if (name === 'history_run_details') return '/static/js/features/history/history_run_details.js';
    if (name === 'options_session_token_controls') return '/static/js/features/preferences/session_token_controls.js';
    if (name === 'options_secrets_panel') return '/static/js/features/preferences/secrets_panel.js';
    if (name === 'options_teams_panel') return '/static/js/features/preferences/teams_panel.js';
    if (name === 'options_notification_channels') return '/static/js/features/preferences/notification_channels.js';
    if (name === 'command_registry') return '/static/js/features/command-registry/command_registry.js';
    if (name === 'workflows') return '/static/js/features/workflows/workflows.js';
    if (name === 'pty_controller') return '/static/js/pty.js';
    if (name === 'schedules_modal') return '/static/js/features/schedules/schedules_modal.js';
    if (name === 'tour_modal') return '/static/js/tour_modal.js';
    if (name === 'watchers_modal') return '/static/js/features/watchers/watchers_modal.js';
    if (name === 'status_monitor_core') return '/static/js/features/status-monitor/status_monitor_core.js';
    if (name === 'status_monitor_data') return '/static/js/features/status-monitor/status_monitor_data.js';
    if (name === 'status_monitor_resources') return '/static/js/features/status-monitor/status_monitor_resources.js';
    if (name === 'status_monitor') return '/static/js/status_monitor.js';
    if (name === 'jspdf') return '/vendor/jspdf.umd.min.js';
    if (name === 'xterm_css') return '/vendor/xterm.css';
    if (name === 'xterm_js') return '/vendor/xterm.js';
    if (name === 'xterm_fit_js') return '/vendor/xterm-addon-fit.js';
    return '';
  }

  function lazyAssetUrl(name) {
    return _lazyAssetUrl(name);
  }

  function loadLazyClassicScript(name, globalCheck) {
    if (typeof globalCheck === 'function' && globalCheck()) return Promise.resolve();
    if (_lazyAssetPromises[name]) return _lazyAssetPromises[name];
    const src = _lazyAssetUrl(name);
    if (!src) return Promise.reject(new Error(`Unknown lazy asset: ${name}`));
    _lazyAssetPromises[name] = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = src;
      script.async = true;
      script.onload = () => {
        if (typeof globalCheck !== 'function' || globalCheck()) resolve();
        else reject(new Error(`Lazy asset did not expose its expected global: ${src}`));
      };
      script.onerror = () => reject(new Error(`Failed to load lazy asset: ${src}`));
      (document.head || document.documentElement).appendChild(script);
    }).catch((err) => {
      delete _lazyAssetPromises[name];
      throw err;
    });
    return _lazyAssetPromises[name];
  }

  function loadLazyClassicScripts(items) {
    return items.reduce(
      (promise, item) => promise.then(() => loadLazyClassicScript(item.name, item.globalCheck)),
      Promise.resolve(),
    );
  }

  async function loadJsPdf() {
    await loadLazyClassicScript('jspdf', () => !!(window.jspdf && window.jspdf.jsPDF));
    return window.jspdf.jsPDF;
  }

  async function loadExportPdfUtils() {
    await loadLazyClassicScript('export_pdf', () => !!(
      window.ExportPdfUtils
      && typeof window.ExportPdfUtils.buildTerminalExportPdf === 'function'
    ));
    return window.ExportPdfUtils;
  }

  async function loadFindingsBoard() {
    await loadLazyClassicScript('findings_board', () => !!(
      window.openFindingsBoard
      && window.openFindingsBoard !== lazyOpenFindingsBoard
    ));
    return window.openFindingsBoard;
  }

  async function loadAtlasOverlay() {
    await loadLazyClassicScripts([
      {
        name: 'atlas_tabs',
        globalCheck: () => !!window.DarklabAtlasTabs,
      },
      {
        name: 'atlas_entity_row',
        globalCheck: () => !!window.DarklabAtlasEntityRow,
      },
      {
        name: 'atlas_entity_detail',
        globalCheck: () => !!window.DarklabAtlasDetail,
      },
      {
        name: 'atlas_overlay',
        globalCheck: () => !!(
          window.openAtlas
          && window.openAtlas !== lazyOpenAtlas
        ),
      },
      {
        name: 'atlas_mobile',
        globalCheck: () => (
          !!window.DarklabAtlasMobile
          || !document.getElementById('atlas-mobile-root')
        ),
      },
    ]);
    return window.openAtlas;
  }

  async function loadWatchersModal() {
    await loadLazyClassicScript('watchers_modal', () => !!(
      window.openWatchersModal
      && window.openWatchersModal !== lazyOpenWatchersModal
    ));
    return window.openWatchersModal;
  }

  async function loadProjectReport() {
    await loadLazyClassicScript('project_report', () => !!(
      window.DarklabProjectReport
      && typeof window.DarklabProjectReport.createProjectReportController === 'function'
    ));
    return window.DarklabProjectReport;
  }

  async function loadProjectActivity() {
    await loadLazyClassicScript('project_activity', () => !!(
      window.DarklabProjectActivity
      && typeof window.DarklabProjectActivity.createProjectActivityController === 'function'
    ));
    return window.DarklabProjectActivity;
  }

  async function loadProjectArtifacts() {
    await loadLazyClassicScript('project_artifacts', () => !!(
      window.DarklabProjectArtifacts
      && typeof window.DarklabProjectArtifacts.createProjectArtifactsController === 'function'
    ));
    return window.DarklabProjectArtifacts;
  }

  async function loadProjectPackages() {
    await loadLazyClassicScript('project_packages', () => !!(
      window.DarklabProjectPackages
      && typeof window.DarklabProjectPackages.createProjectPackagesController === 'function'
    ));
    return window.DarklabProjectPackages;
  }

  async function loadProjectWorkspace() {
    await loadLazyClassicScripts([
      {
        name: 'project_details',
        globalCheck: () => !!(
          window.DarklabProjectDetails
          && typeof window.DarklabProjectDetails.createProjectDetailsController === 'function'
        ),
      },
      {
        name: 'project_list',
        globalCheck: () => !!(
          window.DarklabProjectList
          && typeof window.DarklabProjectList.createProjectListController === 'function'
        ),
      },
      {
        name: 'project_navigation',
        globalCheck: () => !!(
          window.DarklabProjectNavigation
          && typeof window.DarklabProjectNavigation.createProjectNavigationController === 'function'
        ),
      },
      {
        name: 'project_entity_editor',
        globalCheck: () => !!(
          window.DarklabProjectEntityEditor
          && typeof window.DarklabProjectEntityEditor.createProjectEntityEditorController === 'function'
        ),
      },
      {
        name: 'project_workspace_actions',
        globalCheck: () => !!(
          window.DarklabProjectWorkspaceActions
          && typeof window.DarklabProjectWorkspaceActions.createProjectWorkspaceActionsController === 'function'
        ),
      },
      {
        name: 'project_workspace_shell',
        globalCheck: () => !!(
          window.DarklabProjectWorkspaceShell
          && typeof window.DarklabProjectWorkspaceShell.createProjectWorkspaceShellController === 'function'
        ),
      },
      {
        name: 'project_workspace_lifecycle',
        globalCheck: () => !!(
          window.DarklabProjectWorkspaceLifecycle
          && typeof window.DarklabProjectWorkspaceLifecycle.createProjectWorkspaceLifecycleController === 'function'
        ),
      },
      {
        name: 'project_workspace_renderer',
        globalCheck: () => !!(
          window.DarklabProjectWorkspaceRenderer
          && typeof window.DarklabProjectWorkspaceRenderer.createProjectWorkspaceRendererController === 'function'
        ),
      },
      {
        name: 'project_workspace_bootstrap',
        globalCheck: () => !!(
          window.DarklabProjectWorkspaceBootstrap
          && typeof window.DarklabProjectWorkspaceBootstrap.createProjectWorkspaceBootstrapController === 'function'
        ),
      },
      {
        name: 'project_nested_sheets',
        globalCheck: () => !!(
          window.DarklabProjectNestedSheets
          && typeof window.DarklabProjectNestedSheets.createProjectNestedSheetsController === 'function'
        ),
      },
      {
        name: 'project_workspace_events',
        globalCheck: () => !!(
          window.DarklabProjectWorkspaceEvents
          && typeof window.DarklabProjectWorkspaceEvents.createProjectWorkspaceEventsController === 'function'
        ),
      },
      {
        name: 'project_targets',
        globalCheck: () => !!(
          window.DarklabProjectTargets
          && typeof window.DarklabProjectTargets.createProjectTargetsController === 'function'
        ),
      },
      {
        name: 'project_runs',
        globalCheck: () => !!(
          window.DarklabProjectRuns
          && typeof window.DarklabProjectRuns.createProjectRunsController === 'function'
        ),
      },
      {
        name: 'project_mobile_compare',
        globalCheck: () => !!(
          window.DarklabProjectMobileCompare
          && typeof window.DarklabProjectMobileCompare.createProjectMobileCompareController === 'function'
        ),
      },
      {
        name: 'project_mobile_shell',
        globalCheck: () => !!(
          window.DarklabProjectMobileShell
          && typeof window.DarklabProjectMobileShell.createProjectMobileShellController === 'function'
        ),
      },
      {
        name: 'project_mobile_detail',
        globalCheck: () => !!(
          window.DarklabProjectMobileDetail
          && typeof window.DarklabProjectMobileDetail.createProjectMobileDetailController === 'function'
        ),
      },
      {
        name: 'project_findings_data',
        globalCheck: () => !!(
          window.DarklabProjectFindingsData
          && typeof window.DarklabProjectFindingsData.createProjectFindingsDataController === 'function'
        ),
      },
      {
        name: 'project_filters',
        globalCheck: () => !!(
          window.DarklabProjectFilters
          && typeof window.DarklabProjectFilters.createProjectFiltersController === 'function'
        ),
      },
      {
        name: 'project_entities',
        globalCheck: () => !!(
          window.DarklabProjectEntities
          && typeof window.DarklabProjectEntities.createProjectEntitiesController === 'function'
        ),
      },
      {
        name: 'project_findings',
        globalCheck: () => !!(
          window.DarklabProjectFindings
          && typeof window.DarklabProjectFindings.createProjectFindingsController === 'function'
        ),
      },
      {
        name: 'project_findings_board',
        globalCheck: () => !!(
          window.DarklabProjectFindingsBoard
          && typeof window.DarklabProjectFindingsBoard.createProjectFindingsBoardController === 'function'
        ),
      },
    ]);
    return window.DarklabProjectWorkspaceShell;
  }

  async function loadHistoryRunDetails() {
    await loadLazyClassicScript('history_run_details', () => !!(
      window.openHistoryRunDetails
      && window.openHistoryRunDetails !== lazyOpenHistoryRunDetails
    ));
    return window.openHistoryRunDetails;
  }

  async function loadOptionsPanels() {
    await loadLazyClassicScripts([
      {
        name: 'options_session_token_controls',
        globalCheck: () => typeof _updateOptionsSessionTokenStatus === 'function',
      },
      {
        name: 'options_secrets_panel',
        globalCheck: () => !!(
          window.refreshOptionsSecrets
          && window.refreshOptionsSecrets !== lazyRefreshOptionsSecrets
          && window.invalidateOptionsSecrets
          && window.invalidateOptionsSecrets !== lazyInvalidateOptionsSecrets
        ),
      },
      {
        name: 'options_teams_panel',
        globalCheck: () => !!(
          window.refreshOptionsTeams
          && window.refreshOptionsTeams !== lazyRefreshOptionsTeams
        ),
      },
      {
        name: 'options_notification_channels',
        globalCheck: () => !!(
          window.refreshNotificationChannels
          && window.refreshNotificationChannels !== lazyRefreshNotificationChannels
        ),
      },
    ]);
    return true;
  }

  async function loadCommandRegistry() {
    await loadLazyClassicScript('command_registry', () => !!(
      window.openCommandRegistry
      && window.openCommandRegistry !== lazyOpenCommandRegistry
    ));
    return window.openCommandRegistry;
  }

  async function loadWorkflows() {
    await loadLazyClassicScript('workflows', () => !!(
      window.renderWorkflowItems
      && window.renderWorkflowItems !== lazyRenderWorkflowItems
      && window.handleWorkflowTerminalCommand
      && window.handleWorkflowTerminalCommand !== lazyHandleWorkflowTerminalCommand
    ));
    return true;
  }

  async function lazyOpenWorkflowEditor(workflow = null) {
    await loadWorkflows();
    if (
      typeof window.openWorkflowEditor !== 'function'
      || window.openWorkflowEditor === lazyOpenWorkflowEditor
    ) {
      return false;
    }
    return window.openWorkflowEditor(workflow);
  }

  async function loadHistoryCompare() {
    await loadLazyClassicScripts([
      {
        name: 'history_compare_core',
        globalCheck: () => !!window.DarklabHistoryCompareCore,
      },
      {
        name: 'history_compare_overlay',
        globalCheck: () => !!(
          window.closeHistoryCompareOverlay
          && window.closeHistoryCompareOverlay !== lazyCloseHistoryCompareOverlay
          && window.isHistoryCompareOverlayOpen
          && window.isHistoryCompareOverlayOpen !== lazyIsHistoryCompareOverlayOpen
        ),
      },
      {
        name: 'history_compare_controls',
        globalCheck: () => typeof _closeHistoryCompareActionMenus === 'function',
      },
      {
        name: 'history_compare_navigation',
        globalCheck: () => typeof _historyCompareScrollToLine === 'function',
      },
      {
        name: 'history_compare_renderer',
        globalCheck: () => !!(
          window.fetchAndRenderHistoryComparison
          && window.fetchAndRenderHistoryComparison !== lazyFetchAndRenderHistoryComparison
        ),
      },
      {
        name: 'history_compare_launcher',
        globalCheck: () => !!(
          window.openHistoryCompareLauncher
          && window.openHistoryCompareLauncher !== lazyOpenHistoryCompareLauncher
        ),
      },
    ]);
    return window.openHistoryCompareLauncher;
  }

  async function loadPtyController() {
    await loadLazyClassicScript('pty_controller', () => !!(
      window.startInteractivePtyCommand
      && window.startInteractivePtyCommand !== lazyStartInteractivePtyCommand
      && window.attachInteractivePtyCommand
      && window.attachInteractivePtyCommand !== lazyAttachInteractivePtyCommand
      && typeof window.isInteractivePtyCommand === 'function'
    ));
    return window.startInteractivePtyCommand;
  }

  async function loadPtyAttachController() {
    await loadPtyController();
    return window.attachInteractivePtyCommand;
  }

  async function loadSchedulesModal() {
    await loadLazyClassicScript('schedules_modal', () => !!(
      window.openSchedulesModal
      && window.openSchedulesModal !== lazyOpenSchedulesModal
    ));
    return window.openSchedulesModal;
  }

  async function loadTourModal() {
    await loadLazyClassicScript('tour_modal', () => !!(
      window.openTourModal
      && window.openTourModal !== lazyOpenTourModal
    ));
    return window.openTourModal;
  }

  async function loadStatusMonitor() {
    await loadLazyClassicScripts([
      {
        name: 'status_monitor_core',
        globalCheck: () => !!window.DarklabStatusMonitorCore,
      },
      {
        name: 'status_monitor_data',
        globalCheck: () => !!window.DarklabStatusMonitorData,
      },
      {
        name: 'status_monitor_resources',
        globalCheck: () => !!window.DarklabStatusMonitorResources,
      },
      {
        name: 'status_monitor',
        globalCheck: () => !!(
          window.openStatusMonitor
          && window.openStatusMonitor !== lazyOpenStatusMonitor
        ),
      },
    ]);
    return window.openStatusMonitor;
  }

  async function lazyOpenFindingsBoard(options = {}) {
    const open = await loadFindingsBoard();
    if (typeof open !== 'function' || open === lazyOpenFindingsBoard) return false;
    return open(options);
  }

  async function lazyOpenAtlas(options = {}) {
    const open = await loadAtlasOverlay();
    if (typeof open !== 'function' || open === lazyOpenAtlas) return false;
    return open(options);
  }

  function lazyCloseAtlas(options = {}) {
    if (window.closeAtlas === lazyCloseAtlas) return false;
    if (typeof window.closeAtlas === 'function') return window.closeAtlas(options);
    return false;
  }

  function lazyIsAtlasOverlayOpen() {
    if (window.isAtlasOverlayOpen === lazyIsAtlasOverlayOpen) {
      const overlay = document.getElementById('atlas-overlay');
      return !!(overlay && overlay.classList.contains('open'));
    }
    if (typeof window.isAtlasOverlayOpen === 'function') return window.isAtlasOverlayOpen();
    return false;
  }

  function lazyCycleAtlasTab(offset) {
    if (window.cycleAtlasTab === lazyCycleAtlasTab) return false;
    if (typeof window.cycleAtlasTab === 'function') return window.cycleAtlasTab(offset);
    return false;
  }

  function lazyCloseFindingsBoard(options = {}) {
    if (window.closeFindingsBoard === lazyCloseFindingsBoard) return false;
    if (typeof window.closeFindingsBoard === 'function') return window.closeFindingsBoard(options);
    return false;
  }

  async function lazyOpenWatchersModal(options = {}) {
    const open = await loadWatchersModal();
    if (typeof open !== 'function' || open === lazyOpenWatchersModal) return false;
    return open(options);
  }

  function lazyCloseWatchersModal(options = {}) {
    if (window.closeWatchersModal === lazyCloseWatchersModal) return false;
    if (typeof window.closeWatchersModal === 'function') return window.closeWatchersModal(options);
    return false;
  }

  async function lazyOpenSchedulesModal(options = {}) {
    const open = await loadSchedulesModal();
    if (typeof open !== 'function' || open === lazyOpenSchedulesModal) return false;
    return open(options);
  }

  function lazyCloseSchedulesModal(options = {}) {
    if (window.closeSchedulesModal === lazyCloseSchedulesModal) return false;
    if (typeof window.closeSchedulesModal === 'function') return window.closeSchedulesModal(options);
    return false;
  }

  async function lazyOpenTourModal(options = {}) {
    const open = await loadTourModal();
    if (typeof open !== 'function' || open === lazyOpenTourModal) return false;
    return open(options);
  }

  function lazyCloseTourModal(options = {}) {
    if (window.closeTourModal === lazyCloseTourModal) return false;
    if (typeof window.closeTourModal === 'function') return window.closeTourModal(options);
    return false;
  }

  async function lazyOpenStatusMonitor(options = {}) {
    const open = await loadStatusMonitor();
    if (typeof open !== 'function' || open === lazyOpenStatusMonitor) return false;
    return open(options);
  }

  async function lazyOpenHistoryRunDetails(run) {
    const open = await loadHistoryRunDetails();
    if (typeof open !== 'function' || open === lazyOpenHistoryRunDetails) return false;
    return open(run);
  }

  async function lazyRefreshOptionsSecrets(options = {}) {
    await loadOptionsPanels();
    if (
      typeof window.refreshOptionsSecrets !== 'function'
      || window.refreshOptionsSecrets === lazyRefreshOptionsSecrets
    ) {
      return false;
    }
    return window.refreshOptionsSecrets(options);
  }

  async function lazyRefreshOptionsTeams(options = {}) {
    await loadOptionsPanels();
    if (
      typeof window.refreshOptionsTeams !== 'function'
      || window.refreshOptionsTeams === lazyRefreshOptionsTeams
    ) {
      return false;
    }
    return window.refreshOptionsTeams(options);
  }

  async function lazyRefreshNotificationChannels(options = {}) {
    await loadOptionsPanels();
    if (
      typeof window.refreshNotificationChannels !== 'function'
      || window.refreshNotificationChannels === lazyRefreshNotificationChannels
    ) {
      return false;
    }
    return window.refreshNotificationChannels(options);
  }

  function lazyInvalidateOptionsSecrets() {
    if (window.invalidateOptionsSecrets === lazyInvalidateOptionsSecrets) return false;
    if (typeof window.invalidateOptionsSecrets === 'function') return window.invalidateOptionsSecrets();
    return false;
  }

  async function lazyOpenCommandRegistry() {
    const open = await loadCommandRegistry();
    if (typeof open !== 'function' || open === lazyOpenCommandRegistry) return false;
    return open();
  }

  function lazyCloseCommandRegistry() {
    if (window.closeCommandRegistry === lazyCloseCommandRegistry) return false;
    if (typeof window.closeCommandRegistry === 'function') return window.closeCommandRegistry();
    if (typeof window.hideCommandRegistryOverlay === 'function') return window.hideCommandRegistryOverlay();
    return false;
  }

  function lazyHideCommandRegistryOverlay() {
    const overlay = document.getElementById('command-registry-overlay');
    if (!overlay) return false;
    overlay.classList.add('u-hidden');
    overlay.classList.remove('open');
    overlay.setAttribute('aria-hidden', 'true');
    return true;
  }

  function lazyIsCommandRegistryOverlayOpen() {
    if (window.isCommandRegistryOverlayOpen === lazyIsCommandRegistryOverlayOpen) {
      const overlay = document.getElementById('command-registry-overlay');
      return !!(overlay && overlay.classList.contains('open'));
    }
    if (typeof window.isCommandRegistryOverlayOpen === 'function') return window.isCommandRegistryOverlayOpen();
    return false;
  }

  function _workflowCachedItems() {
    return Array.isArray(window.__workflowCatalogItems)
      ? window.__workflowCatalogItems
      : [];
  }

  function _setWorkflowCachedItems(items) {
    window.__workflowCatalogItems = Array.isArray(items) ? items.slice() : [];
    return window.__workflowCatalogItems;
  }

  function _emitWorkflowCatalog(items) {
    if (typeof window.emitUiEvent === 'function') {
      window.emitUiEvent('app:workflows-rendered', {
        count: items.length,
        items: items.slice(),
      });
    }
  }

  let _workflowCatalogLoadPromise = null;

  function lazyRenderWorkflowItems(items, options = {}) {
    const nextItems = _setWorkflowCachedItems(items);
    if (options.emitCatalogEvent !== false) _emitWorkflowCatalog(nextItems);
    return nextItems;
  }

  async function lazyReloadWorkflowCatalog() {
    if (_workflowCatalogLoadPromise) return _workflowCatalogLoadPromise;
    if (typeof window.apiFetch !== 'function') return _workflowCachedItems();
    _workflowCatalogLoadPromise = (async () => {
      const resp = await window.apiFetch('/workflows');
      if (resp && resp.ok === false) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      return lazyRenderWorkflowItems(data.items || []);
    })();
    try {
      return await _workflowCatalogLoadPromise;
    } finally {
      _workflowCatalogLoadPromise = null;
    }
  }

  function lazyEnsureWorkflowCatalogLoaded() {
    const items = _workflowCachedItems();
    if (items.length) return Promise.resolve(items);
    return lazyReloadWorkflowCatalog();
  }

  async function lazyHandleWorkflowTerminalCommand(cmd, tabId) {
    await loadWorkflows();
    if (
      typeof window.handleWorkflowTerminalCommand !== 'function'
      || window.handleWorkflowTerminalCommand === lazyHandleWorkflowTerminalCommand
    ) {
      return false;
    }
    return window.handleWorkflowTerminalCommand(cmd, tabId);
  }

  async function lazyOpenHistoryCompareLauncher(run) {
    const open = await loadHistoryCompare();
    if (typeof open !== 'function' || open === lazyOpenHistoryCompareLauncher) return false;
    return open(run);
  }

  async function lazyFetchAndRenderHistoryComparison(leftId, rightId, options = {}) {
    await loadHistoryCompare();
    if (
      typeof window.fetchAndRenderHistoryComparison !== 'function'
      || window.fetchAndRenderHistoryComparison === lazyFetchAndRenderHistoryComparison
    ) {
      return false;
    }
    return window.fetchAndRenderHistoryComparison(leftId, rightId, options);
  }

  function lazyCloseHistoryCompareOverlay(options = {}) {
    if (window.closeHistoryCompareOverlay === lazyCloseHistoryCompareOverlay) return false;
    if (typeof window.closeHistoryCompareOverlay === 'function') return window.closeHistoryCompareOverlay(options);
    return false;
  }

  function lazyIsHistoryCompareOverlayOpen() {
    if (window.isHistoryCompareOverlayOpen === lazyIsHistoryCompareOverlayOpen) {
      const overlay = document.getElementById('history-compare-overlay');
      return !!(overlay && !overlay.classList.contains('u-hidden'));
    }
    if (typeof window.isHistoryCompareOverlayOpen === 'function') return window.isHistoryCompareOverlayOpen();
    return false;
  }

  function lazyCloseStatusMonitor(options = {}) {
    if (window.closeStatusMonitor === lazyCloseStatusMonitor) return false;
    if (typeof window.closeStatusMonitor === 'function') return window.closeStatusMonitor(options);
    return false;
  }

  function lazyIsStatusMonitorOpen() {
    if (window.isStatusMonitorOpen === lazyIsStatusMonitorOpen) return false;
    if (typeof window.isStatusMonitorOpen === 'function') return window.isStatusMonitorOpen();
    const monitor = document.getElementById('status-monitor');
    return !!(monitor && !monitor.classList.contains('u-hidden'));
  }

  function _splitInteractivePtyCommand(cmd) {
    return String(cmd || '').trim().match(/"[^"]*"|'[^']*'|\S+/g) || [];
  }

  function _interactivePtySpecs() {
    const configured = (
      window.APP_CONFIG
      && Array.isArray(window.APP_CONFIG.interactive_pty_commands)
    ) ? window.APP_CONFIG.interactive_pty_commands : [];
    if (configured.length) return configured;
    return [{ root: 'mtr', trigger_flag: '--interactive' }];
  }

  function lazyIsInteractivePtyCommand(cmd) {
    const parts = _splitInteractivePtyCommand(cmd);
    const root = String(parts[0] || '').toLowerCase();
    if (!root) return false;
    return _interactivePtySpecs().some((spec) => {
      const specRoot = String(spec && spec.root || '').toLowerCase();
      const trigger = String(spec && spec.trigger_flag || '');
      return specRoot === root && !!trigger && parts.slice(1).includes(trigger);
    });
  }

  async function lazyStartInteractivePtyCommand(cmd, tabId) {
    const start = await loadPtyController();
    if (typeof start !== 'function' || start === lazyStartInteractivePtyCommand) return false;
    return start(cmd, tabId);
  }

  async function lazyAttachInteractivePtyCommand(runOrRunId, tabId = '') {
    const attach = await loadPtyAttachController();
    if (typeof attach !== 'function' || attach === lazyAttachInteractivePtyCommand) return false;
    return attach(runOrRunId, tabId);
  }

  window.loadLazyClassicScript = loadLazyClassicScript;
  window.lazyAssetUrl = lazyAssetUrl;
  window.loadJsPdf = loadJsPdf;
  window.loadLazyClassicScripts = loadLazyClassicScripts;
  window.loadExportPdfUtils = loadExportPdfUtils;
  window.loadAtlasOverlay = loadAtlasOverlay;
  window.loadFindingsBoard = loadFindingsBoard;
  window.loadProjectActivity = loadProjectActivity;
  window.loadProjectArtifacts = loadProjectArtifacts;
  window.loadProjectWorkspace = loadProjectWorkspace;
  window.loadProjectPackages = loadProjectPackages;
  window.loadProjectReport = loadProjectReport;
  window.loadHistoryCompare = loadHistoryCompare;
  window.loadHistoryRunDetails = loadHistoryRunDetails;
  window.loadOptionsPanels = loadOptionsPanels;
  window.loadCommandRegistry = loadCommandRegistry;
  window.loadWorkflows = loadWorkflows;
  window.loadPtyController = loadPtyController;
  window.loadPtyAttachController = loadPtyAttachController;
  window.loadWatchersModal = loadWatchersModal;
  window.loadSchedulesModal = loadSchedulesModal;
  window.loadTourModal = loadTourModal;
  window.loadStatusMonitor = loadStatusMonitor;
  if (typeof window.openAtlas !== 'function') window.openAtlas = lazyOpenAtlas;
  if (typeof window.closeAtlas !== 'function') window.closeAtlas = lazyCloseAtlas;
  if (typeof window.isAtlasOverlayOpen !== 'function') window.isAtlasOverlayOpen = lazyIsAtlasOverlayOpen;
  if (typeof window.cycleAtlasTab !== 'function') window.cycleAtlasTab = lazyCycleAtlasTab;
  if (typeof window.openFindingsBoard !== 'function') window.openFindingsBoard = lazyOpenFindingsBoard;
  if (typeof window.closeFindingsBoard !== 'function') window.closeFindingsBoard = lazyCloseFindingsBoard;
  if (typeof window.openSchedulesModal !== 'function') window.openSchedulesModal = lazyOpenSchedulesModal;
  if (typeof window.closeSchedulesModal !== 'function') window.closeSchedulesModal = lazyCloseSchedulesModal;
  if (typeof window.openTourModal !== 'function') window.openTourModal = lazyOpenTourModal;
  if (typeof window.closeTourModal !== 'function') window.closeTourModal = lazyCloseTourModal;
  if (typeof window.openStatusMonitor !== 'function') window.openStatusMonitor = lazyOpenStatusMonitor;
  if (typeof window.closeStatusMonitor !== 'function') window.closeStatusMonitor = lazyCloseStatusMonitor;
  if (typeof window.isStatusMonitorOpen !== 'function') window.isStatusMonitorOpen = lazyIsStatusMonitorOpen;
  if (typeof window.openWatchersModal !== 'function') window.openWatchersModal = lazyOpenWatchersModal;
  if (typeof window.closeWatchersModal !== 'function') window.closeWatchersModal = lazyCloseWatchersModal;
  if (typeof window.openHistoryCompareLauncher !== 'function') window.openHistoryCompareLauncher = lazyOpenHistoryCompareLauncher;
  if (typeof window.fetchAndRenderHistoryComparison !== 'function') window.fetchAndRenderHistoryComparison = lazyFetchAndRenderHistoryComparison;
  if (typeof window.closeHistoryCompareOverlay !== 'function') window.closeHistoryCompareOverlay = lazyCloseHistoryCompareOverlay;
  if (typeof window.isHistoryCompareOverlayOpen !== 'function') window.isHistoryCompareOverlayOpen = lazyIsHistoryCompareOverlayOpen;
  if (typeof window.openHistoryRunDetails !== 'function') window.openHistoryRunDetails = lazyOpenHistoryRunDetails;
  if (typeof window.refreshOptionsSecrets !== 'function') window.refreshOptionsSecrets = lazyRefreshOptionsSecrets;
  if (typeof window.invalidateOptionsSecrets !== 'function') window.invalidateOptionsSecrets = lazyInvalidateOptionsSecrets;
  if (typeof window.refreshOptionsTeams !== 'function') window.refreshOptionsTeams = lazyRefreshOptionsTeams;
  if (typeof window.refreshNotificationChannels !== 'function') window.refreshNotificationChannels = lazyRefreshNotificationChannels;
  if (typeof window.openCommandRegistry !== 'function') window.openCommandRegistry = lazyOpenCommandRegistry;
  if (typeof window.closeCommandRegistry !== 'function') window.closeCommandRegistry = lazyCloseCommandRegistry;
  if (typeof window.hideCommandRegistryOverlay !== 'function') window.hideCommandRegistryOverlay = lazyHideCommandRegistryOverlay;
  if (typeof window.isCommandRegistryOverlayOpen !== 'function') {
    window.isCommandRegistryOverlayOpen = lazyIsCommandRegistryOverlayOpen;
  }
  if (typeof window.renderWorkflowItems !== 'function') window.renderWorkflowItems = lazyRenderWorkflowItems;
  if (typeof window.reloadWorkflowCatalog !== 'function') window.reloadWorkflowCatalog = lazyReloadWorkflowCatalog;
  if (typeof window.ensureWorkflowCatalogLoaded !== 'function') {
    window.ensureWorkflowCatalogLoaded = lazyEnsureWorkflowCatalogLoaded;
  }
  if (typeof window.handleWorkflowTerminalCommand !== 'function') {
    window.handleWorkflowTerminalCommand = lazyHandleWorkflowTerminalCommand;
  }
  if (typeof window.openWorkflowEditor !== 'function') window.openWorkflowEditor = lazyOpenWorkflowEditor;
  if (typeof window.isInteractivePtyCommand !== 'function') window.isInteractivePtyCommand = lazyIsInteractivePtyCommand;
  if (typeof window.startInteractivePtyCommand !== 'function') window.startInteractivePtyCommand = lazyStartInteractivePtyCommand;
  if (typeof window.attachInteractivePtyCommand !== 'function') window.attachInteractivePtyCommand = lazyAttachInteractivePtyCommand;
})();
