// Shared lazy asset loader for rarely-used scripts and modules.
import { getAppConfig as importedGetAppConfig } from './config.js';
import { emitUiEvent as importedEmitUiEvent } from './state.js';
import { setAtlasHandlers as importedSetAtlasHandlers } from '../features/atlas/atlas_bridge.js';
import { setWorkflowHandlers as importedSetWorkflowHandlers } from '../features/workflows/workflows_bridge.js';
import { setHistoryCompareHandlers as importedSetHistoryCompareHandlers } from '../features/run-comparison/history_compare_bridge.js';
import { setCommandRegistryHandlers as importedSetCommandRegistryHandlers } from '../features/command-registry/command_registry_bridge.js';
import {
  apiFetch as importedApiFetch,
  hasRuntimeHandler as importedHasRuntimeHandler,
  logClientError as importedLogClientError,
  setRuntimeHandlers as importedSetRuntimeHandlers,
} from '../runtime_bridge.js';
import { setHistoryRunModalStateHandlers as importedSetHistoryRunModalStateHandlers } from '../features/history/history_run_modal_state_bridge.js';
import { setSecretsHandlers as importedSetSecretsHandlers } from '../features/preferences/secrets_bridge.js';

let exportedLoadAtlasOverlay = null;
let exportedLoadCommandRegistry = null;
let exportedLoadFindingsBoard = null;
let exportedLoadMobileRunningIndicator = null;
let exportedLoadSchedulesModal = null;
let exportedLoadWatchersModal = null;

(function () {
  const _lazyAssetPromises = {};
  const _lazyAssetLoadedLogged = new Set();
  const _lazyModuleAssetMeta = typeof WeakMap === 'function' ? new WeakMap() : null;
  let _lazyAssetConfigInvalidLogged = false;

  function _logLazyAssetConfigInvalid(err) {
    if (_lazyAssetConfigInvalidLogged || typeof importedLogClientError !== 'function') return;
    _lazyAssetConfigInvalidLogged = true;
    importedLogClientError('lazy asset config invalid', err, {
      event: 'LAZY_ASSET_CONFIG_INVALID',
      level: 'warning',
      source: 'lazy-assets-json',
    });
  }

  function _lazyAssetConfig() {
    let urls = {};
    if (typeof document !== 'undefined') {
      const node = document.getElementById('lazy-assets-json');
      if (node && node.textContent) {
        try {
          const parsed = JSON.parse(node.textContent);
          if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) urls = parsed;
        } catch (err) {
          _logLazyAssetConfigInvalid(err);
          urls = {};
        }
      }
    }
    const appConfig = typeof importedGetAppConfig === 'function' ? importedGetAppConfig() : {};
    const appConfigUrls = appConfig && appConfig.lazy_asset_urls;
    if (appConfigUrls && typeof appConfigUrls === 'object' && !Array.isArray(appConfigUrls)) {
      urls = { ...urls, ...appConfigUrls };
    }
    return urls;
  }

  function _normalizeLazyAssetEntry(value) {
    if (typeof value === 'string' && value) return { url: value, type: 'classic' };
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      const url = typeof value.url === 'string' ? value.url : '';
      const type = value.type === 'module' ? 'module' : 'classic';
      if (url) return { url, type };
    }
    return { url: '', type: 'classic' };
  }

  function _lazyAssetEntry(name) {
    const configured = _lazyAssetConfig()[name];
    const normalized = _normalizeLazyAssetEntry(configured);
    if (normalized.url) return normalized;
    if (name === 'export_pdf') return { url: '/static/js/export_pdf.js', type: 'module' };
    if (name === 'atlas_tabs') return { url: '/static/js/features/atlas/atlas_tabs.js', type: 'module' };
    if (name === 'atlas_entity_row') return { url: '/static/js/features/atlas/atlas_entity_row.js', type: 'module' };
    if (name === 'atlas_entity_detail') return { url: '/static/js/features/atlas/atlas_entity_detail.js', type: 'module' };
    if (name === 'atlas_overlay') return { url: '/static/js/features/atlas/atlas_overlay.js', type: 'module' };
    if (name === 'atlas_mobile') return { url: '/static/js/features/atlas/atlas_mobile.js', type: 'module' };
    if (name === 'findings_board') return { url: '/static/js/features/findings/findings_board_modal.js', type: 'module' };
    if (name === 'project_activity') return { url: '/static/js/features/projects/project_activity.js', type: 'module' };
    if (name === 'project_overview') return { url: '/static/js/features/projects/project_overview.js', type: 'module' };
    if (name === 'project_monitoring') return { url: '/static/js/features/projects/project_monitoring.js', type: 'module' };
    if (name === 'project_artifacts') return { url: '/static/js/features/projects/project_artifacts.js', type: 'module' };
    if (name === 'project_details') return { url: '/static/js/features/projects/project_details.js', type: 'module' };
    if (name === 'project_list') return { url: '/static/js/features/projects/project_list.js', type: 'module' };
    if (name === 'project_navigation') return { url: '/static/js/features/projects/project_navigation.js', type: 'module' };
    if (name === 'project_entity_editor') return { url: '/static/js/features/projects/project_entity_editor.js', type: 'module' };
    if (name === 'project_workspace_actions') return { url: '/static/js/features/projects/project_workspace_actions.js', type: 'module' };
    if (name === 'project_workspace_shell') return { url: '/static/js/features/projects/project_workspace_shell.js', type: 'module' };
    if (name === 'project_workspace_lifecycle') return { url: '/static/js/features/projects/project_workspace_lifecycle.js', type: 'module' };
    if (name === 'project_workspace_renderer') return { url: '/static/js/features/projects/project_workspace_renderer.js', type: 'module' };
    if (name === 'project_workspace_bootstrap') return { url: '/static/js/features/projects/project_workspace_bootstrap.js', type: 'module' };
    if (name === 'project_nested_sheets') return { url: '/static/js/features/projects/project_nested_sheets.js', type: 'module' };
    if (name === 'project_workspace_events') return { url: '/static/js/features/projects/project_workspace_events.js', type: 'module' };
    if (name === 'project_targets') return { url: '/static/js/features/projects/project_targets.js', type: 'module' };
    if (name === 'project_runs') return { url: '/static/js/features/projects/project_runs.js', type: 'module' };
    if (name === 'project_mobile_compare') return { url: '/static/js/features/projects/project_mobile_compare.js', type: 'module' };
    if (name === 'project_mobile_shell') return { url: '/static/js/features/projects/project_mobile_shell.js', type: 'module' };
    if (name === 'project_mobile_detail') return { url: '/static/js/features/projects/project_mobile_detail.js', type: 'module' };
    if (name === 'project_findings_data') return { url: '/static/js/features/projects/project_findings_data.js', type: 'module' };
    if (name === 'project_filters') return { url: '/static/js/features/projects/project_filters.js', type: 'module' };
    if (name === 'project_entities') return { url: '/static/js/features/projects/project_entities.js', type: 'module' };
    if (name === 'project_findings') return { url: '/static/js/features/projects/project_findings.js', type: 'module' };
    if (name === 'project_findings_board') return { url: '/static/js/features/projects/project_findings_board.js', type: 'module' };
    if (name === 'project_packages') return { url: '/static/js/features/projects/project_packages.js', type: 'module' };
    if (name === 'project_report') return { url: '/static/js/features/projects/project_report.js', type: 'module' };
    if (name === 'history_compare_core') return { url: '/static/js/features/run-comparison/history_compare_core.js', type: 'module' };
    if (name === 'history_compare_overlay') return { url: '/static/js/features/run-comparison/history_compare_overlay.js', type: 'module' };
    if (name === 'history_compare_controls') return { url: '/static/js/features/run-comparison/history_compare_controls.js', type: 'module' };
    if (name === 'history_compare_navigation') return { url: '/static/js/features/run-comparison/history_compare_navigation.js', type: 'module' };
    if (name === 'history_compare_renderer') return { url: '/static/js/features/run-comparison/history_compare_renderer.js', type: 'module' };
    if (name === 'history_compare_launcher') return { url: '/static/js/features/run-comparison/history_compare_launcher.js', type: 'module' };
    if (name === 'history_run_details') return { url: '/static/js/features/history/history_run_details.js', type: 'module' };
    if (name === 'options_session_token_controls') return { url: '/static/js/features/preferences/session_token_controls.js', type: 'module' };
    if (name === 'options_secrets_panel') return { url: '/static/js/features/preferences/secrets_panel.js', type: 'module' };
    if (name === 'options_teams_panel') return { url: '/static/js/features/preferences/teams_panel.js', type: 'module' };
    if (name === 'options_notification_channels') return { url: '/static/js/features/preferences/notification_channels.js', type: 'module' };
    if (name === 'command_registry') return { url: '/static/js/features/command-registry/command_registry.js', type: 'module' };
    if (name === 'workflows') return { url: '/static/js/features/workflows/workflows.js', type: 'module' };
    if (name === 'pty_controller') return { url: '/static/js/pty.js', type: 'module' };
    if (name === 'schedules_modal') return { url: '/static/js/features/schedules/schedules_modal.js', type: 'module' };
    if (name === 'mobile_running_indicator') {
      return { url: '/static/js/features/mobile/mobile_running_indicator.js', type: 'module' };
    }
    if (name === 'tour_modal') return { url: '/static/js/tour_modal.js', type: 'module' };
    if (name === 'watchers_modal') return { url: '/static/js/features/watchers/watchers_modal.js', type: 'module' };
    if (name === 'status_monitor_core') return { url: '/static/js/features/status-monitor/status_monitor_core.js', type: 'module' };
    if (name === 'status_monitor_data') return { url: '/static/js/features/status-monitor/status_monitor_data.js', type: 'module' };
    if (name === 'status_monitor_resources') return { url: '/static/js/features/status-monitor/status_monitor_resources.js', type: 'module' };
    if (name === 'status_monitor') return { url: '/static/js/status_monitor.js', type: 'module' };
    if (name === 'jspdf') return { url: '/vendor/jspdf.umd.min.js', type: 'classic' };
    if (name === 'xterm_css') return { url: '/vendor/xterm.css', type: 'classic' };
    if (name === 'xterm_js') return { url: '/vendor/xterm.js', type: 'classic' };
    if (name === 'xterm_fit_js') return { url: '/vendor/xterm-addon-fit.js', type: 'classic' };
    return { url: '', type: 'classic' };
  }

  function _lazyAssetUrl(name) {
    return _lazyAssetEntry(name).url;
  }

  function _safeLazyAssetLogSrc(src) {
    const raw = String(src || '');
    if (!raw) return '';
    try {
      const parsed = new URL(raw, typeof window !== 'undefined' && window.location ? window.location.href : 'http://localhost/');
      const version = parsed.searchParams.get('v');
      return version ? `${parsed.pathname}?v=${encodeURIComponent(version)}` : parsed.pathname;
    } catch (_) {
      return raw.split('?', 1)[0].slice(0, 300);
    }
  }

  function _logLazyAssetLoadFailed(name, entry, err, globalCheck) {
    if (typeof importedLogClientError !== 'function') return;
    importedLogClientError('lazy asset load failed', err, {
      event: 'LAZY_ASSET_LOAD_FAILED',
      level: 'error',
      asset_name: String(name || '').slice(0, 120),
      asset_type: entry && entry.type === 'module' ? 'module' : 'classic',
      src: _safeLazyAssetLogSrc(entry && entry.url),
      expected_global: typeof globalCheck === 'function',
    });
  }

  function _lazyAssetTimestamp() {
    if (typeof performance !== 'undefined' && typeof performance.now === 'function') {
      return performance.now();
    }
    return Date.now();
  }

  function _lazyAssetDurationMs(startedAt) {
    const duration = Math.max(0, _lazyAssetTimestamp() - Number(startedAt || 0));
    return Math.round(duration);
  }

  function _lazyAssetDiagnosticsEnabled() {
    const appConfig = typeof importedGetAppConfig === 'function' ? importedGetAppConfig() : {};
    return appConfig.frontend_bridge_warnings === true
      || appConfig.debug === true
      || appConfig.dev_mode === true
      || appConfig.environment === 'development'
      || appConfig.env === 'development'
      || appConfig.lazy_asset_debug === true;
  }

  function _logLazyAssetLifecycle(context, name, entry, details = {}) {
    if (!_lazyAssetDiagnosticsEnabled()) return;
    const consoleApi = (
      typeof window !== 'undefined' && window.console
    ) || (typeof globalThis !== 'undefined' && globalThis.console);
    const log = consoleApi && (consoleApi.debug || consoleApi.log);
    if (typeof log !== 'function') return;
    log.call(consoleApi, `[darklab] ${details.event || context}`, {
      asset_name: String(name || '').slice(0, 120),
      asset_type: entry && entry.type === 'module' ? 'module' : 'classic',
      src: _safeLazyAssetLogSrc(entry && entry.url),
      ...details,
    });
  }

  function _logLazyAssetLoadStarted(name, entry, cacheHit = false) {
    _logLazyAssetLifecycle('lazy asset load started', name, entry, {
      event: 'LAZY_ASSET_LOAD_STARTED',
      level: 'debug',
      cache_hit: cacheHit === true,
    });
  }

  function _logLazyAssetLoaded(name, entry, startedAt, cacheHit = false) {
    const firstLoad = !_lazyAssetLoadedLogged.has(name);
    if (!cacheHit) _lazyAssetLoadedLogged.add(name);
    if (!firstLoad && !cacheHit) return;
    _logLazyAssetLifecycle('lazy asset loaded', name, entry, {
      event: 'LAZY_ASSET_LOADED',
      level: firstLoad && !cacheHit ? 'info' : 'debug',
      duration_ms: cacheHit ? 0 : _lazyAssetDurationMs(startedAt),
      cache_hit: cacheHit === true,
    });
  }

  function _rememberLazyModuleMeta(moduleApi, name, entry) {
    if (
      !_lazyModuleAssetMeta
      || !moduleApi
      || (typeof moduleApi !== 'object' && typeof moduleApi !== 'function')
    ) return;
    try {
      _lazyModuleAssetMeta.set(moduleApi, {
        name: String(name || '').slice(0, 120),
        entry,
      });
    } catch (_) {}
  }

  function _lazyModuleMeta(moduleApi) {
    if (
      !_lazyModuleAssetMeta
      || !moduleApi
      || (typeof moduleApi !== 'object' && typeof moduleApi !== 'function')
    ) return null;
    try {
      return _lazyModuleAssetMeta.get(moduleApi) || null;
    } catch (_) {
      return null;
    }
  }

  function _lazyModuleExportKeys(moduleApi) {
    if (!moduleApi || (typeof moduleApi !== 'object' && typeof moduleApi !== 'function')) return [];
    try {
      return Object.keys(moduleApi).sort().slice(0, 80);
    } catch (_) {
      return [];
    }
  }

  function _logLazyModuleExportMissing(moduleApi, err, details = {}) {
    if (typeof importedLogClientError !== 'function') return;
    const meta = _lazyModuleMeta(moduleApi);
    importedLogClientError('lazy module export missing', err, {
      event: 'LAZY_MODULE_EXPORT_MISSING',
      level: 'error',
      asset_name: String(details.assetName || meta?.name || '').slice(0, 120),
      export_name: String(details.exportName || '').slice(0, 160),
      controller_name: String(details.controllerName || '').slice(0, 160),
      src: _safeLazyAssetLogSrc(details.src || meta?.entry?.url || ''),
      module_keys: _lazyModuleExportKeys(moduleApi),
    });
  }

  function lazyAssetUrl(name) {
    return _lazyAssetUrl(name);
  }

  function loadLazyClassicScript(name, globalCheck) {
    if (typeof globalCheck === 'function' && globalCheck()) return Promise.resolve();
    const entry = _lazyAssetEntry(name);
    if (_lazyAssetPromises[name]) {
      _logLazyAssetLoadStarted(name, entry, true);
      _lazyAssetPromises[name].then(() => _logLazyAssetLoaded(name, entry, null, true)).catch(() => {});
      return _lazyAssetPromises[name];
    }
    const src = entry.url;
    if (!src) {
      const err = new Error(`Unknown lazy asset: ${name}`);
      _logLazyAssetLoadFailed(name, entry, err, globalCheck);
      return Promise.reject(err);
    }
    const startedAt = _lazyAssetTimestamp();
    _logLazyAssetLoadStarted(name, entry, false);
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
    }).then((result) => {
      _logLazyAssetLoaded(name, entry, startedAt, false);
      return result;
    }).catch((err) => {
      delete _lazyAssetPromises[name];
      _logLazyAssetLoadFailed(name, entry, err, globalCheck);
      throw err;
    });
    return _lazyAssetPromises[name];
  }

  function loadLazyModule(name, globalCheck) {
    if (typeof globalCheck === 'function' && globalCheck()) return Promise.resolve();
    const entry = _lazyAssetEntry(name);
    if (_lazyAssetPromises[name]) {
      _logLazyAssetLoadStarted(name, entry, true);
      _lazyAssetPromises[name].then(() => _logLazyAssetLoaded(name, entry, null, true)).catch(() => {});
      return _lazyAssetPromises[name];
    }
    const src = entry.url;
    if (!src) {
      const err = new Error(`Unknown lazy asset: ${name}`);
      _logLazyAssetLoadFailed(name, entry, err, globalCheck);
      return Promise.reject(err);
    }
    const importer = typeof window !== 'undefined' && typeof window.__darklabImportModule === 'function'
      ? window.__darklabImportModule
      : (url) => import(url);
    const startedAt = _lazyAssetTimestamp();
    _logLazyAssetLoadStarted(name, entry, false);
    _lazyAssetPromises[name] = Promise.resolve()
      .then(() => importer(src))
      .then((moduleApi) => {
        if (typeof globalCheck !== 'function' || globalCheck()) {
          _rememberLazyModuleMeta(moduleApi, name, entry);
          _logLazyAssetLoaded(name, entry, startedAt, false);
          return moduleApi;
        }
        throw new Error(`Lazy module did not expose its expected global: ${src}`);
      })
      .catch((err) => {
        delete _lazyAssetPromises[name];
        _logLazyAssetLoadFailed(name, entry, err, globalCheck);
        throw err;
      });
    return _lazyAssetPromises[name];
  }

  function loadLazyAsset(name, globalCheck) {
    return _lazyAssetEntry(name).type === 'module'
      ? loadLazyModule(name, globalCheck)
      : loadLazyClassicScript(name, globalCheck);
  }

  function loadLazyClassicScripts(items) {
    return items.reduce(
      (promise, item) => promise.then(() => loadLazyAsset(item.name, item.globalCheck)),
      Promise.resolve(),
    );
  }

  async function loadJsPdf() {
    await loadLazyClassicScript('jspdf', () => !!(window.jspdf && window.jspdf.jsPDF));
    return window.jspdf.jsPDF;
  }

  async function loadExportPdfUtils() {
    const pdfModule = await loadLazyAsset('export_pdf');
    return _requireLazyModuleExport(pdfModule, 'ExportPdfUtils', value => (
      value && typeof value.buildTerminalExportPdf === 'function'
    ));
  }

  async function loadFindingsBoard() {
    const boardModule = await loadLazyAsset('findings_board');
    return {
      openFindingsBoard: _requireLazyModuleExport(boardModule, 'openFindingsBoard', value => (
        typeof value === 'function' && value !== lazyOpenFindingsBoard
      )),
      closeFindingsBoard: boardModule?.closeFindingsBoard || null,
      isFindingsBoardOpen: boardModule?.isFindingsBoardOpen || null,
    };
  }

  function _requireLazyModuleExport(moduleApi, exportName, predicate = value => !!value) {
    const exported = moduleApi && moduleApi[exportName];
    if (predicate(exported)) return exported;
    const err = new Error(`Lazy module did not expose export: ${exportName}`);
    _logLazyModuleExportMissing(moduleApi, err, { exportName });
    throw err;
  }

  async function loadAtlasOverlay() {
    const tabsModule = await loadLazyAsset('atlas_tabs');
    const entityRowModule = await loadLazyAsset('atlas_entity_row');
    const detailModule = await loadLazyAsset('atlas_entity_detail');
    const overlayModule = await loadLazyAsset('atlas_overlay');
    const mobileModule = document.getElementById('atlas-mobile-root')
      ? await loadLazyAsset('atlas_mobile')
      : null;
    const DarklabAtlasOverlay = _requireLazyModuleExport(overlayModule, 'DarklabAtlasOverlay');
    const atlasApi = {
      DarklabAtlasTabs: _requireLazyModuleExport(tabsModule, 'DarklabAtlasTabs'),
      DarklabAtlasEntityRow: _requireLazyModuleExport(entityRowModule, 'DarklabAtlasEntityRow'),
      DarklabAtlasDetail: _requireLazyModuleExport(detailModule, 'DarklabAtlasDetail'),
      DarklabAtlasOverlay,
      DarklabAtlasMobile: mobileModule?.DarklabAtlasMobile || null,
      openAtlas: _requireLazyModuleExport(overlayModule, 'openAtlas', value => (
        typeof value === 'function' && value !== lazyOpenAtlas
      )),
      closeAtlas: overlayModule?.closeAtlas || null,
      isAtlasOverlayOpen: overlayModule?.isAtlasOverlayOpen || null,
      refreshAtlasOverlay: overlayModule?.refreshAtlasOverlay || null,
      cycleAtlasTab: overlayModule?.cycleAtlasTab || null,
    };
    if (typeof window !== 'undefined') {
      if (typeof atlasApi.openAtlas === 'function') window.openAtlas = atlasApi.openAtlas;
      if (typeof atlasApi.closeAtlas === 'function') window.closeAtlas = atlasApi.closeAtlas;
      if (typeof atlasApi.isAtlasOverlayOpen === 'function') window.isAtlasOverlayOpen = atlasApi.isAtlasOverlayOpen;
      if (typeof atlasApi.refreshAtlasOverlay === 'function') window.refreshAtlasOverlay = atlasApi.refreshAtlasOverlay;
      if (typeof atlasApi.cycleAtlasTab === 'function') window.cycleAtlasTab = atlasApi.cycleAtlasTab;
    }
    if (typeof importedSetAtlasHandlers === 'function') {
      importedSetAtlasHandlers(atlasApi);
    }
    return atlasApi;
  }

  async function loadWatchersModal() {
    const watchersModule = await loadLazyAsset('watchers_modal');
    return {
      openWatchersModal: _requireLazyModuleExport(watchersModule, 'openWatchersModal', value => (
        typeof value === 'function' && value !== lazyOpenWatchersModal
      )),
      closeWatchersModal: watchersModule?.closeWatchersModal || null,
      isWatchersOverlayOpen: watchersModule?.isWatchersOverlayOpen || null,
    };
  }

  async function loadProjectReport() {
    const reportModule = await loadLazyAsset('project_report');
    return _requireLazyModuleExport(reportModule, 'DarklabProjectReport', value => (
      value && typeof value.createProjectReportController === 'function'
    ));
  }

  async function loadProjectActivity() {
    const activityModule = await loadLazyAsset('project_activity');
    return _requireLazyModuleExport(activityModule, 'DarklabProjectActivity', value => (
      value && typeof value.createProjectActivityController === 'function'
    ));
  }

  async function loadProjectOverview() {
    const overviewModule = await loadLazyAsset('project_overview');
    return _requireLazyModuleExport(overviewModule, 'DarklabProjectOverview', value => (
      value && typeof value.createProjectOverviewController === 'function'
    ));
  }

  async function loadProjectMonitoring() {
    const monitoringModule = await loadLazyAsset('project_monitoring');
    return _requireLazyModuleExport(monitoringModule, 'DarklabProjectMonitoring', value => (
      value && typeof value.createProjectMonitoringController === 'function'
    ));
  }

  async function loadProjectArtifacts() {
    const artifactsModule = await loadLazyAsset('project_artifacts');
    return _requireLazyModuleExport(artifactsModule, 'DarklabProjectArtifacts', value => (
      value && typeof value.createProjectArtifactsController === 'function'
    ));
  }

  async function loadProjectPackages() {
    const packagesModule = await loadLazyAsset('project_packages');
    const DarklabProjectPackages = _requireLazyModuleExport(packagesModule, 'DarklabProjectPackages', value => (
      value && typeof value.createProjectPackagesController === 'function'
    ));
    window.DarklabProjectPackages = DarklabProjectPackages;
    return DarklabProjectPackages;
  }

  async function loadProjectWorkspace() {
    const loadProjectNamespace = async (name, globalName, controllerName) => {
      const moduleApi = await loadLazyAsset(name);
      const namespace = moduleApi?.[globalName] || window[globalName];
      if (!namespace || typeof namespace[controllerName] !== 'function') {
        const err = new Error(`Lazy module ${name} did not expose ${globalName}.${controllerName}`);
        _logLazyModuleExportMissing(moduleApi, err, {
          assetName: name,
          exportName: globalName,
          controllerName,
        });
        throw err;
      }
      window[globalName] = namespace;
      return namespace;
    };

    const DarklabProjectDetails = await loadProjectNamespace(
      'project_details',
      'DarklabProjectDetails',
      'createProjectDetailsController',
    );
    const DarklabProjectList = await loadProjectNamespace(
      'project_list',
      'DarklabProjectList',
      'createProjectListController',
    );
    const DarklabProjectNavigation = await loadProjectNamespace(
      'project_navigation',
      'DarklabProjectNavigation',
      'createProjectNavigationController',
    );
    const DarklabProjectEntityEditor = await loadProjectNamespace(
      'project_entity_editor',
      'DarklabProjectEntityEditor',
      'createProjectEntityEditorController',
    );
    const DarklabProjectWorkspaceActions = await loadProjectNamespace(
      'project_workspace_actions',
      'DarklabProjectWorkspaceActions',
      'createProjectWorkspaceActionsController',
    );
    const DarklabProjectWorkspaceShell = await loadProjectNamespace(
      'project_workspace_shell',
      'DarklabProjectWorkspaceShell',
      'createProjectWorkspaceShellController',
    );
    const DarklabProjectWorkspaceLifecycle = await loadProjectNamespace(
      'project_workspace_lifecycle',
      'DarklabProjectWorkspaceLifecycle',
      'createProjectWorkspaceLifecycleController',
    );
    const DarklabProjectWorkspaceRenderer = await loadProjectNamespace(
      'project_workspace_renderer',
      'DarklabProjectWorkspaceRenderer',
      'createProjectWorkspaceRendererController',
    );
    const DarklabProjectWorkspaceBootstrap = await loadProjectNamespace(
      'project_workspace_bootstrap',
      'DarklabProjectWorkspaceBootstrap',
      'createProjectWorkspaceBootstrapController',
    );
    const DarklabProjectNestedSheets = await loadProjectNamespace(
      'project_nested_sheets',
      'DarklabProjectNestedSheets',
      'createProjectNestedSheetsController',
    );
    const DarklabProjectWorkspaceEvents = await loadProjectNamespace(
      'project_workspace_events',
      'DarklabProjectWorkspaceEvents',
      'createProjectWorkspaceEventsController',
    );
    const DarklabProjectTargets = await loadProjectNamespace(
      'project_targets',
      'DarklabProjectTargets',
      'createProjectTargetsController',
    );
    const DarklabProjectRuns = await loadProjectNamespace(
      'project_runs',
      'DarklabProjectRuns',
      'createProjectRunsController',
    );
    const DarklabProjectMobileCompare = await loadProjectNamespace(
      'project_mobile_compare',
      'DarklabProjectMobileCompare',
      'createProjectMobileCompareController',
    );
    const DarklabProjectMobileShell = await loadProjectNamespace(
      'project_mobile_shell',
      'DarklabProjectMobileShell',
      'createProjectMobileShellController',
    );
    const DarklabProjectMobileDetail = await loadProjectNamespace(
      'project_mobile_detail',
      'DarklabProjectMobileDetail',
      'createProjectMobileDetailController',
    );
    const DarklabProjectFindingsData = await loadProjectNamespace(
      'project_findings_data',
      'DarklabProjectFindingsData',
      'createProjectFindingsDataController',
    );
    const DarklabProjectFilters = await loadProjectNamespace(
      'project_filters',
      'DarklabProjectFilters',
      'createProjectFiltersController',
    );
    const DarklabProjectEntities = await loadProjectNamespace(
      'project_entities',
      'DarklabProjectEntities',
      'createProjectEntitiesController',
    );
    const DarklabProjectFindings = await loadProjectNamespace(
      'project_findings',
      'DarklabProjectFindings',
      'createProjectFindingsController',
    );
    const DarklabProjectFindingsBoard = await loadProjectNamespace(
      'project_findings_board',
      'DarklabProjectFindingsBoard',
      'createProjectFindingsBoardController',
    );

    return {
      DarklabProjectDetails,
      DarklabProjectList,
      DarklabProjectNavigation,
      DarklabProjectEntityEditor,
      DarklabProjectWorkspaceActions,
      DarklabProjectWorkspaceShell,
      DarklabProjectWorkspaceLifecycle,
      DarklabProjectWorkspaceRenderer,
      DarklabProjectWorkspaceBootstrap,
      DarklabProjectNestedSheets,
      DarklabProjectWorkspaceEvents,
      DarklabProjectTargets,
      DarklabProjectRuns,
      DarklabProjectMobileCompare,
      DarklabProjectMobileShell,
      DarklabProjectMobileDetail,
      DarklabProjectFindingsData,
      DarklabProjectFilters,
      DarklabProjectEntities,
      DarklabProjectFindings,
      DarklabProjectFindingsBoard,
    };
  }

  async function loadHistoryRunDetails() {
    const detailsModule = await loadLazyAsset('history_run_details');
    return _requireLazyModuleExport(
      detailsModule,
      'openHistoryRunDetails',
      value => typeof value === 'function' && value !== lazyOpenHistoryRunDetails,
    );
  }

  async function loadOptionsPanels() {
    const sessionTokenControls = await loadLazyAsset('options_session_token_controls');
    const secretsPanel = await loadLazyAsset('options_secrets_panel');
    const teamsPanel = await loadLazyAsset('options_teams_panel');
    const notificationChannels = await loadLazyAsset('options_notification_channels');
    return {
      _updateOptionsSessionTokenStatus: _requireLazyModuleExport(
        sessionTokenControls,
        '_updateOptionsSessionTokenStatus',
        value => typeof value === 'function',
      ),
      refreshOptionsSecrets: _requireLazyModuleExport(secretsPanel, 'refreshOptionsSecrets', value => (
        typeof value === 'function' && value !== lazyRefreshOptionsSecrets
      )),
      invalidateOptionsSecrets: _requireLazyModuleExport(secretsPanel, 'invalidateOptionsSecrets', value => (
        typeof value === 'function' && value !== lazyInvalidateOptionsSecrets
      )),
      openSecretEditor: secretsPanel?.openSecretEditor || null,
      openProviderStatusModal: secretsPanel?.openProviderStatusModal || null,
      refreshOptionsTeams: _requireLazyModuleExport(teamsPanel, 'refreshOptionsTeams', value => (
        typeof value === 'function' && value !== lazyRefreshOptionsTeams
      )),
      refreshNotificationChannels: _requireLazyModuleExport(
        notificationChannels,
        'refreshNotificationChannels',
        value => typeof value === 'function' && value !== lazyRefreshNotificationChannels,
      ),
      openNotificationChannelEditor: notificationChannels?.openNotificationChannelEditor || null,
    };
  }

  async function loadCommandRegistry() {
    const registryModule = await loadLazyAsset('command_registry');
    return {
      showCommandRegistryOverlay: registryModule?.showCommandRegistryOverlay || null,
      hideCommandRegistryOverlay: registryModule?.hideCommandRegistryOverlay || null,
      isCommandRegistryOverlayOpen: registryModule?.isCommandRegistryOverlayOpen || null,
      closeCommandRegistry: registryModule?.closeCommandRegistry || null,
      renderCommandRegistry: registryModule?.renderCommandRegistry || null,
      openCommandRegistry: _requireLazyModuleExport(registryModule, 'openCommandRegistry', value => (
        typeof value === 'function' && value !== lazyOpenCommandRegistry
      )),
      showCommandCatalogOverlay: registryModule?.showCommandCatalogOverlay || null,
      hideCommandCatalogOverlay: registryModule?.hideCommandCatalogOverlay || null,
      closeCommandCatalogModal: registryModule?.closeCommandCatalogModal || null,
      isCommandCatalogOverlayOpen: registryModule?.isCommandCatalogOverlayOpen || null,
      wireCommandCatalogExamples: registryModule?.wireCommandCatalogExamples || null,
      renderCommandCatalogModal: registryModule?.renderCommandCatalogModal || null,
      openCommandCatalogModal: registryModule?.openCommandCatalogModal || null,
    };
  }

  async function loadWorkflows() {
    const workflowsModule = await loadLazyAsset('workflows');
    return {
      renderWorkflowItems: _requireLazyModuleExport(workflowsModule, 'renderWorkflowItems', value => (
        typeof value === 'function' && value !== lazyRenderWorkflowItems
      )),
      reloadWorkflowCatalog: workflowsModule?.reloadWorkflowCatalog || null,
      ensureWorkflowCatalogLoaded: workflowsModule?.ensureWorkflowCatalogLoaded || null,
      handleWorkflowTerminalCommand: _requireLazyModuleExport(
        workflowsModule,
        'handleWorkflowTerminalCommand',
        value => typeof value === 'function' && value !== lazyHandleWorkflowTerminalCommand,
      ),
      _runtimeWorkflowContext: workflowsModule?._runtimeWorkflowContext || null,
      openWorkflowEditor: workflowsModule?.openWorkflowEditor || null,
      closeWorkflowEditor: workflowsModule?.closeWorkflowEditor || null,
    };
  }

  async function lazyOpenWorkflowEditor(workflow = null) {
    const workflows = await loadWorkflows();
    const open = workflows?.openWorkflowEditor;
    if (
      typeof open !== 'function'
      || open === lazyOpenWorkflowEditor
    ) {
      return false;
    }
    return open(workflow);
  }

  async function loadHistoryCompare() {
    const coreModule = await loadLazyAsset('history_compare_core');
    const overlayModule = await loadLazyAsset('history_compare_overlay');
    const controlsModule = await loadLazyAsset('history_compare_controls');
    const navigationModule = await loadLazyAsset('history_compare_navigation');
    const rendererModule = await loadLazyAsset('history_compare_renderer');
    const launcherModule = await loadLazyAsset('history_compare_launcher');
    _requireLazyModuleExport(coreModule, 'DarklabHistoryCompareCore');
    _requireLazyModuleExport(controlsModule, '_closeHistoryCompareActionMenus', value => typeof value === 'function');
    _requireLazyModuleExport(navigationModule, '_historyCompareScrollToLine', value => typeof value === 'function');
    return {
      closeHistoryCompareOverlay: _requireLazyModuleExport(
        overlayModule,
        'closeHistoryCompareOverlay',
        value => typeof value === 'function' && value !== lazyCloseHistoryCompareOverlay,
      ),
      isHistoryCompareOverlayOpen: _requireLazyModuleExport(
        overlayModule,
        'isHistoryCompareOverlayOpen',
        value => typeof value === 'function' && value !== lazyIsHistoryCompareOverlayOpen,
      ),
      fetchAndRenderHistoryComparison: _requireLazyModuleExport(
        rendererModule,
        'fetchAndRenderHistoryComparison',
        value => typeof value === 'function' && value !== lazyFetchAndRenderHistoryComparison,
      ),
      openHistoryCompareLauncher: _requireLazyModuleExport(
        launcherModule,
        'openHistoryCompareLauncher',
        value => typeof value === 'function' && value !== lazyOpenHistoryCompareLauncher,
      ),
    };
  }

  async function loadPtyController() {
    await loadLazyAsset('pty_controller', () => !!(
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
    const schedulesModule = await loadLazyAsset('schedules_modal');
    return {
      openSchedulesModal: _requireLazyModuleExport(schedulesModule, 'openSchedulesModal', value => (
        typeof value === 'function' && value !== lazyOpenSchedulesModal
      )),
      closeSchedulesModal: schedulesModule?.closeSchedulesModal || null,
      isSchedulesOverlayOpen: schedulesModule?.isSchedulesOverlayOpen || null,
    };
  }

  async function loadTourModal() {
    const tourModule = await loadLazyAsset('tour_modal');
    return {
      openTourModal: _requireLazyModuleExport(tourModule, 'openTourModal', value => (
        typeof value === 'function' && value !== lazyOpenTourModal
      )),
      closeTourModal: tourModule?.closeTourModal || null,
      _visibleTourModalChapters: tourModule?._visibleTourModalChapters || null,
      _renderTourIllustration: tourModule?._renderTourIllustration || null,
    };
  }

  async function loadStatusMonitor() {
    const coreModule = await loadLazyAsset('status_monitor_core');
    const dataModule = await loadLazyAsset('status_monitor_data');
    const resourcesModule = await loadLazyAsset('status_monitor_resources');
    const monitorModule = await loadLazyAsset('status_monitor');
    return {
      DarklabStatusMonitorCore: _requireLazyModuleExport(coreModule, 'DarklabStatusMonitorCore'),
      DarklabStatusMonitorData: _requireLazyModuleExport(dataModule, 'DarklabStatusMonitorData'),
      DarklabStatusMonitorResources: _requireLazyModuleExport(resourcesModule, 'DarklabStatusMonitorResources'),
      openStatusMonitor: _requireLazyModuleExport(monitorModule, 'openStatusMonitor', value => (
        typeof value === 'function' && value !== lazyOpenStatusMonitor
      )),
      closeStatusMonitor: monitorModule?.closeStatusMonitor || null,
      isStatusMonitorOpen: monitorModule?.isStatusMonitorOpen || null,
      refreshStatusMonitor: monitorModule?.refreshStatusMonitor || null,
    };
  }

  async function loadMobileRunningIndicator() {
    const moduleApi = await loadLazyAsset('mobile_running_indicator');
    return moduleApi && typeof moduleApi.createMobileRunningIndicator === 'function'
      ? { create: moduleApi.createMobileRunningIndicator }
      : null;
  }

  async function lazyOpenFindingsBoard(options = {}) {
    const board = await loadFindingsBoard();
    const open = board?.openFindingsBoard;
    if (typeof open !== 'function' || open === lazyOpenFindingsBoard) return false;
    return open(options);
  }

  async function lazyOpenAtlas(options = {}) {
    const atlas = await loadAtlasOverlay();
    const open = atlas?.openAtlas;
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

  function lazyIsFindingsBoardOpen() {
    if (window.isFindingsBoardOpen === lazyIsFindingsBoardOpen) {
      return !!document.getElementById('findings-board-overlay')?.classList.contains('open');
    }
    if (typeof window.isFindingsBoardOpen === 'function') return window.isFindingsBoardOpen();
    return false;
  }

  async function lazyOpenWatchersModal(options = {}) {
    const watchers = await loadWatchersModal();
    const open = watchers?.openWatchersModal;
    if (typeof open !== 'function' || open === lazyOpenWatchersModal) return false;
    return open(options);
  }

  async function lazyCloseWatchersModal(options = {}) {
    if (window.closeWatchersModal === lazyCloseWatchersModal) {
      const watchers = await loadWatchersModal();
      const close = watchers?.closeWatchersModal;
      if (typeof close === 'function') return close(options);
      return false;
    }
    if (typeof window.closeWatchersModal === 'function') return window.closeWatchersModal(options);
    return false;
  }

  function lazyIsWatchersOverlayOpen() {
    if (window.isWatchersOverlayOpen === lazyIsWatchersOverlayOpen) {
      return !!document.getElementById('watchers-overlay')?.classList.contains('open');
    }
    if (typeof window.isWatchersOverlayOpen === 'function') return window.isWatchersOverlayOpen();
    return false;
  }

  async function lazyOpenSchedulesModal(options = {}) {
    const schedules = await loadSchedulesModal();
    const open = schedules?.openSchedulesModal;
    if (typeof open !== 'function' || open === lazyOpenSchedulesModal) return false;
    return open(options);
  }

  async function lazyCloseSchedulesModal(options = {}) {
    if (window.closeSchedulesModal === lazyCloseSchedulesModal) {
      const schedules = await loadSchedulesModal();
      const close = schedules?.closeSchedulesModal;
      if (typeof close === 'function') return close(options);
      return false;
    }
    if (typeof window.closeSchedulesModal === 'function') return window.closeSchedulesModal(options);
    return false;
  }

  function lazyIsSchedulesOverlayOpen() {
    if (window.isSchedulesOverlayOpen === lazyIsSchedulesOverlayOpen) {
      return !!document.getElementById('schedules-overlay')?.classList.contains('open');
    }
    if (typeof window.isSchedulesOverlayOpen === 'function') return window.isSchedulesOverlayOpen();
    return false;
  }

  async function lazyOpenTourModal(options = {}) {
    const tour = await loadTourModal();
    const open = tour?.openTourModal;
    if (typeof open !== 'function' || open === lazyOpenTourModal) return false;
    return open(options);
  }

  function lazyCloseTourModal(options = {}) {
    if (window.closeTourModal === lazyCloseTourModal) {
      const overlay = document.getElementById('tour-overlay');
      if (!overlay) return false;
      overlay.classList.remove('open');
      overlay.classList.add('u-hidden');
      overlay.setAttribute('aria-hidden', 'true');
      return true;
    }
    if (typeof window.closeTourModal === 'function') return window.closeTourModal(options);
    return false;
  }

  async function lazyOpenStatusMonitor(options = {}) {
    const monitor = await loadStatusMonitor();
    const open = monitor?.openStatusMonitor;
    if (typeof open !== 'function' || open === lazyOpenStatusMonitor) return false;
    return open(options);
  }

  async function lazyOpenHistoryRunDetails(run) {
    const open = await loadHistoryRunDetails();
    if (typeof open !== 'function' || open === lazyOpenHistoryRunDetails) return false;
    return open(run);
  }

  async function lazyRefreshOptionsSecrets(options = {}) {
    const panels = await loadOptionsPanels();
    const refresh = panels?.refreshOptionsSecrets;
    if (
      typeof refresh !== 'function'
      || refresh === lazyRefreshOptionsSecrets
    ) {
      return false;
    }
    return refresh(options);
  }

  async function lazyRefreshOptionsTeams(options = {}) {
    const panels = await loadOptionsPanels();
    const refresh = panels?.refreshOptionsTeams;
    if (
      typeof refresh !== 'function'
      || refresh === lazyRefreshOptionsTeams
    ) {
      return false;
    }
    return refresh(options);
  }

  async function lazyRefreshNotificationChannels(options = {}) {
    const panels = await loadOptionsPanels();
    const refresh = panels?.refreshNotificationChannels;
    if (
      typeof refresh !== 'function'
      || refresh === lazyRefreshNotificationChannels
    ) {
      return false;
    }
    return refresh(options);
  }

  function lazyInvalidateOptionsSecrets() {
    if (window.invalidateOptionsSecrets === lazyInvalidateOptionsSecrets) return false;
    if (typeof window.invalidateOptionsSecrets === 'function') return window.invalidateOptionsSecrets();
    return false;
  }

  async function lazyOpenCommandRegistry() {
    const registry = await loadCommandRegistry();
    const open = registry?.openCommandRegistry;
    if (typeof open !== 'function' || open === lazyOpenCommandRegistry) return false;
    return open();
  }

  function lazyCloseCommandRegistry() {
    return lazyHideCommandRegistryOverlay();
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
    const overlay = document.getElementById('command-registry-overlay');
    return !!(overlay && overlay.classList.contains('open'));
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
    if (typeof importedEmitUiEvent === 'function') {
      importedEmitUiEvent('app:workflows-rendered', {
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
    if (typeof importedApiFetch !== 'function' || !importedHasRuntimeHandler?.('apiFetch')) return _workflowCachedItems();
    _workflowCatalogLoadPromise = (async () => {
      const resp = await importedApiFetch('/workflows');
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
    const workflows = await loadWorkflows();
    const handle = workflows?.handleWorkflowTerminalCommand;
    if (
      typeof handle !== 'function'
      || handle === lazyHandleWorkflowTerminalCommand
    ) {
      return false;
    }
    return handle(cmd, tabId);
  }

  async function lazyOpenHistoryCompareLauncher(run) {
    const compare = await loadHistoryCompare();
    const open = compare?.openHistoryCompareLauncher;
    if (typeof open !== 'function' || open === lazyOpenHistoryCompareLauncher) return false;
    return open(run);
  }

  async function lazyFetchAndRenderHistoryComparison(leftId, rightId, options = {}) {
    const compare = await loadHistoryCompare();
    const fetchAndRender = compare?.fetchAndRenderHistoryComparison;
    if (typeof fetchAndRender !== 'function' || fetchAndRender === lazyFetchAndRenderHistoryComparison) return false;
    return fetchAndRender(leftId, rightId, options);
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
    if (window.closeStatusMonitor === lazyCloseStatusMonitor) {
      document.body?.classList?.remove('status-monitor-mobile-open', 'status-monitor-desktop-open');
      document.querySelector('.status-monitor-scrim')?.classList?.add('u-hidden');
      document.getElementById('status-monitor')?.classList?.add('u-hidden');
      return true;
    }
    if (typeof window.closeStatusMonitor === 'function') return window.closeStatusMonitor(options);
    return false;
  }

  function lazyIsStatusMonitorOpen() {
    if (window.isStatusMonitorOpen === lazyIsStatusMonitorOpen) {
      const monitor = document.getElementById('status-monitor');
      return !!(monitor && !monitor.classList.contains('u-hidden'));
    }
    if (typeof window.isStatusMonitorOpen === 'function') return window.isStatusMonitorOpen();
    return false;
  }

  async function lazyRefreshStatusMonitor(options = {}) {
    const monitor = await loadStatusMonitor();
    const refresh = monitor?.refreshStatusMonitor;
    if (typeof refresh !== 'function' || refresh === lazyRefreshStatusMonitor) return false;
    return refresh(options);
  }

  function _splitInteractivePtyCommand(cmd) {
    return String(cmd || '').trim().match(/"[^"]*"|'[^']*'|\S+/g) || [];
  }

  function _interactivePtySpecs() {
    const appConfig = typeof importedGetAppConfig === 'function' ? importedGetAppConfig() : {};
    const configured = Array.isArray(appConfig.interactive_pty_commands)
      ? appConfig.interactive_pty_commands
      : [];
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
  window.loadLazyModule = loadLazyModule;
  window.loadLazyAsset = loadLazyAsset;
  window.lazyAssetUrl = lazyAssetUrl;
  window.loadJsPdf = loadJsPdf;
  window.loadLazyClassicScripts = loadLazyClassicScripts;
  window.loadExportPdfUtils = loadExportPdfUtils;
  window.loadAtlasOverlay = loadAtlasOverlay;
  window.loadFindingsBoard = loadFindingsBoard;
  window.loadProjectActivity = loadProjectActivity;
  window.loadProjectOverview = loadProjectOverview;
  window.loadProjectMonitoring = loadProjectMonitoring;
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
  window.loadMobileRunningIndicator = loadMobileRunningIndicator;
  exportedLoadAtlasOverlay = loadAtlasOverlay;
  exportedLoadCommandRegistry = loadCommandRegistry;
  exportedLoadFindingsBoard = loadFindingsBoard;
  exportedLoadMobileRunningIndicator = loadMobileRunningIndicator;
  exportedLoadSchedulesModal = loadSchedulesModal;
  exportedLoadWatchersModal = loadWatchersModal;
  if (typeof window.openAtlas !== 'function') window.openAtlas = lazyOpenAtlas;
  if (typeof window.closeAtlas !== 'function') window.closeAtlas = lazyCloseAtlas;
  if (typeof window.isAtlasOverlayOpen !== 'function') window.isAtlasOverlayOpen = lazyIsAtlasOverlayOpen;
  if (typeof window.cycleAtlasTab !== 'function') window.cycleAtlasTab = lazyCycleAtlasTab;
  if (typeof importedSetAtlasHandlers === 'function') {
    importedSetAtlasHandlers({
      openAtlas: lazyOpenAtlas,
      closeAtlas: lazyCloseAtlas,
      isAtlasOverlayOpen: lazyIsAtlasOverlayOpen,
      cycleAtlasTab: lazyCycleAtlasTab,
    });
  }
  if (typeof window.openFindingsBoard !== 'function') window.openFindingsBoard = lazyOpenFindingsBoard;
  if (typeof window.closeFindingsBoard !== 'function') window.closeFindingsBoard = lazyCloseFindingsBoard;
  if (typeof window.isFindingsBoardOpen !== 'function') window.isFindingsBoardOpen = lazyIsFindingsBoardOpen;
  if (typeof window.openSchedulesModal !== 'function') window.openSchedulesModal = lazyOpenSchedulesModal;
  if (typeof window.closeSchedulesModal !== 'function') window.closeSchedulesModal = lazyCloseSchedulesModal;
  if (typeof window.isSchedulesOverlayOpen !== 'function') window.isSchedulesOverlayOpen = lazyIsSchedulesOverlayOpen;
  if (typeof window.openTourModal !== 'function') window.openTourModal = lazyOpenTourModal;
  if (typeof window.closeTourModal !== 'function') window.closeTourModal = lazyCloseTourModal;
  if (typeof window.openStatusMonitor !== 'function') window.openStatusMonitor = lazyOpenStatusMonitor;
  if (typeof importedSetRuntimeHandlers === 'function') {
    importedSetRuntimeHandlers({
      openStatusMonitor: lazyOpenStatusMonitor,
      refreshStatusMonitor: lazyRefreshStatusMonitor,
    });
  }
  if (typeof window.closeStatusMonitor !== 'function') window.closeStatusMonitor = lazyCloseStatusMonitor;
  if (typeof window.isStatusMonitorOpen !== 'function') window.isStatusMonitorOpen = lazyIsStatusMonitorOpen;
  if (typeof window.openWatchersModal !== 'function') window.openWatchersModal = lazyOpenWatchersModal;
  if (typeof window.closeWatchersModal !== 'function') window.closeWatchersModal = lazyCloseWatchersModal;
  if (typeof window.isWatchersOverlayOpen !== 'function') window.isWatchersOverlayOpen = lazyIsWatchersOverlayOpen;
  if (typeof window.openHistoryCompareLauncher !== 'function') window.openHistoryCompareLauncher = lazyOpenHistoryCompareLauncher;
  if (typeof window.fetchAndRenderHistoryComparison !== 'function') window.fetchAndRenderHistoryComparison = lazyFetchAndRenderHistoryComparison;
  if (typeof importedSetHistoryCompareHandlers === 'function') {
    importedSetHistoryCompareHandlers({
      fetchAndRenderHistoryComparison: lazyFetchAndRenderHistoryComparison,
      openHistoryCompareLauncher: lazyOpenHistoryCompareLauncher,
    });
  }
  if (typeof window.closeHistoryCompareOverlay !== 'function') window.closeHistoryCompareOverlay = lazyCloseHistoryCompareOverlay;
  if (typeof window.isHistoryCompareOverlayOpen !== 'function') window.isHistoryCompareOverlayOpen = lazyIsHistoryCompareOverlayOpen;
  if (typeof window.openHistoryRunDetails !== 'function') window.openHistoryRunDetails = lazyOpenHistoryRunDetails;
  if (typeof importedSetHistoryRunModalStateHandlers === 'function') {
    importedSetHistoryRunModalStateHandlers({
      openHistoryRunDetails: lazyOpenHistoryRunDetails,
    });
  }
  if (typeof window.refreshOptionsSecrets !== 'function') window.refreshOptionsSecrets = lazyRefreshOptionsSecrets;
  if (typeof window.invalidateOptionsSecrets !== 'function') window.invalidateOptionsSecrets = lazyInvalidateOptionsSecrets;
  if (typeof importedSetSecretsHandlers === 'function') {
    importedSetSecretsHandlers({
      refreshOptionsSecrets: lazyRefreshOptionsSecrets,
      invalidateOptionsSecrets: lazyInvalidateOptionsSecrets,
    });
  }
  if (typeof window.refreshOptionsTeams !== 'function') window.refreshOptionsTeams = lazyRefreshOptionsTeams;
  if (typeof window.refreshNotificationChannels !== 'function') window.refreshNotificationChannels = lazyRefreshNotificationChannels;
  if (typeof window.openCommandRegistry !== 'function') window.openCommandRegistry = lazyOpenCommandRegistry;
  if (typeof importedSetCommandRegistryHandlers === 'function') {
    importedSetCommandRegistryHandlers({
      openCommandRegistry: lazyOpenCommandRegistry,
      closeCommandRegistry: lazyCloseCommandRegistry,
      closeCommandCatalogModal: () => {},
      hideCommandCatalogOverlay: () => {},
      isCommandCatalogOverlayOpen: () => false,
      isCommandRegistryOverlayOpen: lazyIsCommandRegistryOverlayOpen,
    });
  }
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
  if (typeof importedSetWorkflowHandlers === 'function') {
    importedSetWorkflowHandlers({
      renderWorkflowItems: lazyRenderWorkflowItems,
      reloadWorkflowCatalog: lazyReloadWorkflowCatalog,
      ensureWorkflowCatalogLoaded: lazyEnsureWorkflowCatalogLoaded,
      handleWorkflowTerminalCommand: lazyHandleWorkflowTerminalCommand,
      openWorkflowEditor: lazyOpenWorkflowEditor,
    });
  }
  if (typeof window.isInteractivePtyCommand !== 'function') window.isInteractivePtyCommand = lazyIsInteractivePtyCommand;
  if (typeof window.startInteractivePtyCommand !== 'function') window.startInteractivePtyCommand = lazyStartInteractivePtyCommand;
  if (typeof window.attachInteractivePtyCommand !== 'function') window.attachInteractivePtyCommand = lazyAttachInteractivePtyCommand;
})();

function loadAtlasOverlay(...args) {
  return typeof exportedLoadAtlasOverlay === 'function'
    ? exportedLoadAtlasOverlay(...args)
    : Promise.resolve(null);
}

function loadCommandRegistry(...args) {
  return typeof exportedLoadCommandRegistry === 'function'
    ? exportedLoadCommandRegistry(...args)
    : Promise.resolve(null);
}

function loadFindingsBoard(...args) {
  return typeof exportedLoadFindingsBoard === 'function'
    ? exportedLoadFindingsBoard(...args)
    : Promise.resolve(null);
}

function loadMobileRunningIndicator(...args) {
  return typeof exportedLoadMobileRunningIndicator === 'function'
    ? exportedLoadMobileRunningIndicator(...args)
    : Promise.resolve(null);
}

function loadSchedulesModal(...args) {
  return typeof exportedLoadSchedulesModal === 'function'
    ? exportedLoadSchedulesModal(...args)
    : Promise.resolve(null);
}

function loadWatchersModal(...args) {
  return typeof exportedLoadWatchersModal === 'function'
    ? exportedLoadWatchersModal(...args)
    : Promise.resolve(null);
}

export {
  loadAtlasOverlay,
  loadCommandRegistry,
  loadFindingsBoard,
  loadMobileRunningIndicator,
  loadSchedulesModal,
  loadWatchersModal,
};
