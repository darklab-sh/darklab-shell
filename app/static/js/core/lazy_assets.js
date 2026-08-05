// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Shared lazy asset loader for rarely-used scripts and modules.
import { getAppConfig as importedGetAppConfig } from './config.js';
import { emitUiEvent as importedEmitUiEvent } from './state.js';
import {
  getAtlasDetailController as importedGetAtlasDetailController,
  setAtlasDetailHandlers as importedSetAtlasDetailHandlers,
  setAtlasDetailLoader as importedSetAtlasDetailLoader,
  setAtlasHandlers as importedSetAtlasHandlers,
} from '../features/atlas/atlas_bridge.js';
import { setAtlasMobileLoader as importedSetAtlasMobileLoader } from '../features/atlas/atlas_mobile_bridge.js';
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
import { setWorkspaceHandlers as importedSetWorkspaceHandlers } from '../workspace_bridge.js';

let exportedLoadAtlasOverlay = null;
let exportedLoadCommandRegistry = null;
let exportedLoadExportHtmlUtils = null;
let exportedLoadFindingsBoard = null;
let exportedLoadFindingTriageEditor = null;
let exportedLoadMobileRunningIndicator = null;
let exportedLoadSchedulesModal = null;
let exportedLoadTourCliCommand = null;
let exportedLoadWorkspaceSurface = null;
let exportedLoadWatchersModal = null;

(function () {
  const _lazyAssetPromises = {};
  const _lazyAssetLoadedLogged = new Set();
  const _lazyModuleAssetMeta = typeof WeakMap === 'function' ? new WeakMap() : null;
  const _lazyDomFragmentPromises = {};
  let _lazyAssetConfigInvalidLogged = false;
  const LAZY_DOM_FRAGMENTS = {
    atlas_overlay: {
      url: '/static/fragments/atlas_overlay.html',
      requiredId: 'atlas-overlay',
      beforeId: 'history-panel',
    },
  };
  let _atlasShellFallbackHandle = null;

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
      const type = value.type === 'module' || value.type === 'style' ? value.type : 'classic';
      if (url) return { url, type };
    }
    return { url: '', type: 'classic' };
  }

  function _lazyAssetEntry(name) {
    const configured = _lazyAssetConfig()[name];
    const normalized = _normalizeLazyAssetEntry(configured);
    if (normalized.url) return normalized;
    if (name === 'export_html') return { url: '/static/js/export_html.js', type: 'module' };
    if (name === 'export_pdf') return { url: '/static/js/export_pdf.js', type: 'module' };
    if (name === 'projects_css') return { url: '/static/css/features/projects.css', type: 'style' };
    if (name === 'project_assessment_css') {
      return { url: '/static/css/features/project-assessment.css', type: 'style' };
    }
    if (name === 'atlas_css') return { url: '/static/css/features/atlas.css', type: 'style' };
    if (name === 'atlas_mobile_css') return { url: '/static/css/features/atlas-mobile.css', type: 'style' };
    if (name === 'command_registry_css') return { url: '/static/css/features/command-registry.css', type: 'style' };
    if (name === 'run_comparison_css') return { url: '/static/css/features/run-comparison.css', type: 'style' };
    if (name === 'schedules_css') return { url: '/static/css/features/schedules.css', type: 'style' };
    if (name === 'status_monitor_css') return { url: '/static/css/features/status-monitor.css', type: 'style' };
    if (name === 'watchers_css') return { url: '/static/css/features/watchers.css', type: 'style' };
    if (name === 'workflows_css') return { url: '/static/css/features/workflows.css', type: 'style' };
    if (name === 'workspace_css') return { url: '/static/css/features/workspace.css', type: 'style' };
    if (name === 'atlas_tabs') return { url: '/static/js/features/atlas/atlas_tabs.js', type: 'module' };
    if (name === 'atlas_entity_row') return { url: '/static/js/features/atlas/atlas_entity_row.js', type: 'module' };
    if (name === 'atlas_entity_detail') return { url: '/static/js/features/atlas/atlas_entity_detail.js', type: 'module' };
    if (name === 'atlas_overlay') return { url: '/static/js/features/atlas/atlas_overlay.js', type: 'module' };
    if (name === 'atlas_mobile') return { url: '/static/js/features/atlas/atlas_mobile.js', type: 'module' };
    if (name === 'findings_board_bridge') {
      return { url: '/static/js/features/findings/findings_board_bridge.js', type: 'module' };
    }
    if (name === 'findings_board') return { url: '/static/js/features/findings/findings_board_modal.js', type: 'module' };
    if (name === 'finding_triage_editor') return { url: '/static/js/features/findings/finding_triage_editor.js', type: 'module' };
    if (name === 'project_activity') return { url: '/static/js/features/projects/project_activity.js', type: 'module' };
    if (name === 'project_assessment') return { url: '/static/js/features/projects/project_assessment.js', type: 'module' };
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
    if (name === 'tour_cli') return { url: '/static/js/features/tour/tour_cli.js', type: 'module' };
    if (name === 'tour_modal') return { url: '/static/js/tour_modal.js', type: 'module' };
    if (name === 'watchers_modal') return { url: '/static/js/features/watchers/watchers_modal.js', type: 'module' };
    if (name === 'status_monitor_core') return { url: '/static/js/features/status-monitor/status_monitor_core.js', type: 'module' };
    if (name === 'status_monitor_data') return { url: '/static/js/features/status-monitor/status_monitor_data.js', type: 'module' };
    if (name === 'status_monitor_resources') return { url: '/static/js/features/status-monitor/status_monitor_resources.js', type: 'module' };
    if (name === 'status_monitor') return { url: '/static/js/status_monitor.js', type: 'module' };
    if (name === 'workspace') return { url: '/static/js/workspace.js', type: 'module' };
    if (name === 'workspace_drag_drop') return { url: '/static/js/features/workspace/workspace_drag_drop.js', type: 'module' };
    if (name === 'jspdf') return { url: '/vendor/jspdf.umd.min.js', type: 'classic' };
    if (name === 'xterm_css') return { url: '/vendor/xterm.css', type: 'classic' };
    if (name === 'xterm_js') return { url: '/vendor/xterm.js', type: 'classic' };
    if (name === 'xterm_fit_js') return { url: '/vendor/xterm-addon-fit.js', type: 'classic' };
    return { url: '', type: 'classic' };
  }

  function _lazyAssetType(entry) {
    if (entry && entry.type === 'module') return 'module';
    if (entry && entry.type === 'style') return 'style';
    return 'classic';
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
      asset_type: _lazyAssetType(entry),
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
      asset_type: _lazyAssetType(entry),
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

  function _logLazyDomFragmentLoadFailed(name, config, err) {
    if (typeof importedLogClientError !== 'function') return;
    importedLogClientError('lazy DOM fragment load failed', err, {
      event: 'LAZY_DOM_FRAGMENT_LOAD_FAILED',
      level: 'error',
      fragment_name: String(name || '').slice(0, 120),
      src: _safeLazyAssetLogSrc(config && config.url),
    });
  }

  function _canMountLazyDomFragments() {
    return typeof document !== 'undefined'
      && !!document.body
      && typeof document.createElement === 'function'
      && typeof fetch === 'function';
  }

  function _mountLazyDomFragment(html, config) {
    const template = document.createElement('template');
    template.innerHTML = String(html || '').trim();
    if (!template.content || !template.content.childNodes.length) {
      throw new Error(`Lazy DOM fragment is empty: ${config.url}`);
    }
    const anchor = config.beforeId ? document.getElementById(config.beforeId) : null;
    if (anchor && anchor.parentNode) {
      anchor.parentNode.insertBefore(template.content, anchor);
    } else {
      document.body.appendChild(template.content);
    }
  }

  async function _ensureLazyDomFragment(name) {
    const config = LAZY_DOM_FRAGMENTS[name];
    if (!config || typeof document === 'undefined') return null;
    if (document.getElementById(config.requiredId)) return document.getElementById(config.requiredId);
    if (!_canMountLazyDomFragments()) return null;
    if (!_lazyDomFragmentPromises[name]) {
      _lazyDomFragmentPromises[name] = fetch(config.url, {
        credentials: 'same-origin',
        cache: 'no-cache',
      })
        .then((resp) => {
          if (!resp || !resp.ok) {
            const status = resp && typeof resp.status !== 'undefined' ? resp.status : 'unknown';
            throw new Error(`Failed to load lazy DOM fragment ${config.url}: ${status}`);
          }
          return resp.text();
        })
        .then((html) => {
          if (!document.getElementById(config.requiredId)) {
            _mountLazyDomFragment(html, config);
          }
          const mounted = document.getElementById(config.requiredId);
          if (!mounted) throw new Error(`Lazy DOM fragment missing required element: ${config.requiredId}`);
          return mounted;
        })
        .catch((err) => {
          _lazyDomFragmentPromises[name] = null;
          _logLazyDomFragmentLoadFailed(name, config, err);
          throw err;
        });
    }
    return _lazyDomFragmentPromises[name];
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

  function _hrefsMatch(currentHref, targetHref) {
    if (!currentHref || !targetHref) return false;
    try {
      const base = typeof window !== 'undefined' && window.location ? window.location.href : 'http://localhost/';
      return new URL(currentHref, base).href === new URL(targetHref, base).href;
    } catch (_) {
      return String(currentHref) === String(targetHref);
    }
  }

  function _findLazyStyleLink(name, src) {
    if (typeof document === 'undefined' || !document.querySelectorAll) return null;
    const links = document.querySelectorAll('link[rel="stylesheet"]');
    for (const link of links) {
      if (!link) continue;
      if (link.dataset && link.dataset.lazyAsset === name) return link;
      if (_hrefsMatch(link.href, src)) return link;
    }
    return null;
  }

  function _isSyntheticLazyStyleRuntime(link) {
    const runtimeNavigator = (typeof window !== 'undefined' && window.navigator)
      || (typeof globalThis !== 'undefined' && globalThis.navigator)
      || null;
    const userAgent = String(runtimeNavigator?.userAgent || '');
    if (/\bjsdom\b/i.test(userAgent)) return true;
    return !link || typeof link.addEventListener !== 'function';
  }

  function loadLazyStyle(name) {
    const entry = _lazyAssetEntry(name);
    if (_lazyAssetPromises[name]) {
      _logLazyAssetLoadStarted(name, entry, true);
      _lazyAssetPromises[name].then(() => _logLazyAssetLoaded(name, entry, null, true)).catch(() => {});
      return _lazyAssetPromises[name];
    }
    const src = entry.url;
    if (!src) {
      const err = new Error(`Unknown lazy asset: ${name}`);
      _logLazyAssetLoadFailed(name, entry, err, null);
      return Promise.reject(err);
    }
    const existing = _findLazyStyleLink(name, src);
    if (existing) {
      _lazyAssetPromises[name] = Promise.resolve().then(() => {
        _logLazyAssetLoaded(name, entry, null, true);
      });
      return _lazyAssetPromises[name];
    }
    const startedAt = _lazyAssetTimestamp();
    _logLazyAssetLoadStarted(name, entry, false);
    _lazyAssetPromises[name] = new Promise((resolve, reject) => {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = src;
      if (link.dataset) link.dataset.lazyAsset = name;
      if (_isSyntheticLazyStyleRuntime(link)) {
        resolve();
        return;
      }
      link.onload = () => resolve();
      link.onerror = () => reject(new Error(`Failed to load lazy stylesheet: ${src}`));
      (document.head || document.documentElement).appendChild(link);
    }).then((result) => {
      _logLazyAssetLoaded(name, entry, startedAt, false);
      return result;
    }).catch((err) => {
      delete _lazyAssetPromises[name];
      _logLazyAssetLoadFailed(name, entry, err, null);
      throw err;
    });
    return _lazyAssetPromises[name];
  }

  function loadLazyAsset(name, globalCheck) {
    const entry = _lazyAssetEntry(name);
    if (entry.type === 'module') return loadLazyModule(name, globalCheck);
    if (entry.type === 'style') return loadLazyStyle(name);
    return loadLazyClassicScript(name, globalCheck);
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

  async function loadExportHtmlUtils() {
    const existing = window.ExportHtmlUtils;
    if (
      existing
      && existing.isLazyExportHtmlBridge !== true
      && typeof existing.buildTerminalExportHtml === 'function'
    ) {
      return existing;
    }
    const htmlModule = await loadLazyAsset('export_html');
    return _requireLazyModuleExport(htmlModule, 'ExportHtmlUtils', value => (
      value && typeof value.buildTerminalExportHtml === 'function'
    ));
  }

  async function loadExportPdfUtils() {
    await loadExportHtmlUtils();
    const pdfModule = await loadLazyAsset('export_pdf');
    return _requireLazyModuleExport(pdfModule, 'ExportPdfUtils', value => (
      value && typeof value.buildTerminalExportPdf === 'function'
    ));
  }

  async function loadFindingsBoard() {
    const cssReady = loadLazyAsset('projects_css');
    const boardModule = await loadLazyAsset('findings_board');
    await cssReady;
    return {
      openFindingsBoard: _requireLazyModuleExport(boardModule, 'openFindingsBoard', value => (
        typeof value === 'function' && value !== lazyOpenFindingsBoard
      )),
      closeFindingsBoard: boardModule?.closeFindingsBoard || null,
      isFindingsBoardOpen: boardModule?.isFindingsBoardOpen || null,
    };
  }

  async function loadFindingTriageEditor() {
    const cssReady = loadLazyAsset('projects_css');
    const editorModule = await loadLazyAsset('finding_triage_editor');
    await cssReady;
    return _requireLazyModuleExport(editorModule, 'DarklabFindingTriageEditor', value => (
      value && typeof value.open === 'function' && typeof value.compactTriage === 'function'
    ));
  }

  function _requireLazyModuleExport(moduleApi, exportName, predicate = value => !!value) {
    const exported = moduleApi && moduleApi[exportName];
    if (predicate(exported)) return exported;
    const err = new Error(`Lazy module did not expose export: ${exportName}`);
    _logLazyModuleExportMissing(moduleApi, err, { exportName });
    throw err;
  }

  function _isAtlasMobileMode() {
    return !!(
      typeof document !== 'undefined'
      && document.body
      && document.body.classList.contains('mobile-terminal-mode')
    );
  }

  async function loadAtlasDetailRenderer() {
    const detailModule = await loadLazyAsset('atlas_entity_detail');
    const detailApi = _requireLazyModuleExport(detailModule, 'DarklabAtlasDetail');
    if (typeof importedSetAtlasDetailHandlers === 'function') {
      importedSetAtlasDetailHandlers({ DarklabAtlasDetail: detailApi });
    }
    return detailApi;
  }

  async function loadAtlasMobileController() {
    const cssReady = loadLazyAsset('atlas_mobile_css');
    const mobileModule = await loadLazyAsset('atlas_mobile');
    await cssReady;
    return mobileModule?.DarklabAtlasMobile || null;
  }

  async function loadAtlasOverlay() {
    await _ensureLazyDomFragment('atlas_overlay');
    const hasMobileAtlas = !!document.getElementById('atlas-mobile-root');
    const cssReady = loadLazyAsset('atlas_css');
    const mobileReady = hasMobileAtlas && _isAtlasMobileMode()
      ? loadAtlasMobileController()
      : Promise.resolve(null);
    const [
      tabsModule,
      entityRowModule,
      overlayModule,
      mobileApi,
    ] = await Promise.all([
      loadLazyAsset('atlas_tabs'),
      loadLazyAsset('atlas_entity_row'),
      loadLazyAsset('atlas_overlay'),
      mobileReady,
    ]);
    await cssReady;
    const DarklabAtlasOverlay = _requireLazyModuleExport(overlayModule, 'DarklabAtlasOverlay');
    const atlasApi = {
      DarklabAtlasTabs: _requireLazyModuleExport(tabsModule, 'DarklabAtlasTabs'),
      DarklabAtlasEntityRow: _requireLazyModuleExport(entityRowModule, 'DarklabAtlasEntityRow'),
      DarklabAtlasDetail: importedGetAtlasDetailController?.() || null,
      DarklabAtlasOverlay,
      DarklabAtlasMobile: mobileApi,
      loadAtlasDetail: loadAtlasDetailRenderer,
      loadAtlasMobile: loadAtlasMobileController,
      openAtlas: _requireLazyModuleExport(overlayModule, 'openAtlas', value => (
        typeof value === 'function' && value !== lazyOpenAtlas
      )),
      openAtlasQuickLookup: _requireLazyModuleExport(overlayModule, 'openAtlasQuickLookup', value => (
        typeof value === 'function' && value !== lazyOpenAtlasQuickLookup
      )),
      closeAtlas: overlayModule?.closeAtlas || null,
      isAtlasOverlayOpen: overlayModule?.isAtlasOverlayOpen || null,
      refreshAtlasOverlay: overlayModule?.refreshAtlasOverlay || null,
      cycleAtlasTab: overlayModule?.cycleAtlasTab || null,
    };
    if (typeof window !== 'undefined') {
      if (typeof atlasApi.openAtlas === 'function') window.openAtlas = atlasApi.openAtlas;
      if (typeof atlasApi.openAtlasQuickLookup === 'function') {
        window.openAtlasQuickLookup = atlasApi.openAtlasQuickLookup;
      }
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

  const ATLAS_INITIAL_TABS = Object.freeze({
    findings: { id: 'findings', type: '' },
    ip: { id: 'ip', type: 'ip' },
    domain: { id: 'domain', type: 'domain' },
    port: { id: 'port', type: 'port' },
    hash: { id: 'hash', type: 'hash' },
    cve: { id: 'cve', type: 'cve' },
    url: { id: 'url', type: 'url' },
  });

  function _atlasInitialTab(options = {}) {
    const requested = String(options && options.tab || 'findings');
    return ATLAS_INITIAL_TABS[requested] || ATLAS_INITIAL_TABS.findings;
  }

  function _createAtlasInitialLoad(options = {}) {
    if (typeof importedApiFetch !== 'function' || !importedHasRuntimeHandler?.('apiFetch')) return null;
    const tab = _atlasInitialTab(options);
    const projectId = String(options && options.projectId || '');
    const runId = String(options && options.runId || '').trim();
    const queryText = String(options && options.entityValue || '').trim();
    const orphanFilter = 'hide';
    const suppressionFilter = 'hide';
    const limit = 50;
    const offset = 0;
    const summaryParams = new URLSearchParams({
      orphan_filter: orphanFilter,
      suppression_filter: suppressionFilter,
    });
    if (runId) summaryParams.set('run_id', runId);
    if (projectId) summaryParams.set('project_id', projectId);
    const baseSummaryParams = new URLSearchParams({
      orphan_filter: orphanFilter,
      suppression_filter: suppressionFilter,
    });
    if (projectId) baseSummaryParams.set('project_id', projectId);
    const listParams = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
    });
    if (queryText) listParams.set('q', queryText);
    if (projectId) listParams.set('project_id', projectId);
    if (runId) listParams.set('run_id', runId);
    listParams.set('orphan_filter', orphanFilter);
    listParams.set('suppression_filter', suppressionFilter);
    const listUrl = tab.id === 'findings'
      ? `/atlas/findings?${listParams.toString()}`
      : (() => {
          listParams.set('type', tab.type);
          return `/atlas/entities?${listParams.toString()}`;
        })();
    return {
      tabId: tab.id,
      type: tab.type,
      projectId,
      runId,
      query: queryText,
      findingStatus: '',
      orphanFilter,
      suppressionFilter,
      limit,
      offset,
      summaryResp: importedApiFetch(`/atlas?${summaryParams.toString()}`, { cache: 'no-store' }),
      baseSummaryResp: runId
        ? importedApiFetch(`/atlas?${baseSummaryParams.toString()}`, { cache: 'no-store' })
        : null,
      listResp: importedApiFetch(listUrl, { cache: 'no-store' }),
    };
  }

  function _hideAtlasShellFallback() {
    const overlay = document.getElementById('atlas-overlay');
    if (!overlay) return;
    overlay.classList.add('u-hidden');
    overlay.classList.remove('open');
    overlay.setAttribute('aria-hidden', 'true');
  }

  function _atlasInitialLoadLogDetails(initialLoad, role, event, level, extras = {}) {
    return {
      event,
      level,
      role,
      tab: String(initialLoad?.tabId || ''),
      project_id: String(initialLoad?.projectId || '').slice(0, 160),
      run_id: String(initialLoad?.runId || '').slice(0, 160),
      query_active: !!String(initialLoad?.query || '').trim(),
      limit: Number(initialLoad?.limit || 0),
      offset: Number(initialLoad?.offset || 0),
      ...extras,
    };
  }

  function _logAtlasInitialPreloadFailed(initialLoad, role, err) {
    if (typeof importedLogClientError !== 'function') return;
    importedLogClientError('atlas initial preload failed', err, _atlasInitialLoadLogDetails(
      initialLoad,
      role,
      'ATLAS_INITIAL_PRELOAD_FAILED',
      'warning',
      { status: Number(err?.status || 0) },
    ));
  }

  function _logAtlasInitialPreloadAbandoned(initialLoad, reason) {
    if (typeof importedLogClientError !== 'function') return;
    importedLogClientError('atlas initial preload abandoned', null, _atlasInitialLoadLogDetails(
      initialLoad,
      'all',
      'ATLAS_INITIAL_PRELOAD_ABANDONED',
      'debug',
      { reason: String(reason || 'unused').slice(0, 120) },
    ));
  }

  function _settleAtlasInitialLoad(initialLoad, reason = '') {
    if (!initialLoad || typeof initialLoad !== 'object') return;
    if (reason) _logAtlasInitialPreloadAbandoned(initialLoad, reason);
    [
      ['summary', initialLoad.summaryResp],
      ['base_summary', initialLoad.baseSummaryResp],
      ['list', initialLoad.listResp],
    ].forEach(([role, promise]) => {
      if (promise && typeof promise.catch === 'function') {
        promise.catch((err) => {
          _logAtlasInitialPreloadFailed(initialLoad, role, err);
        });
      }
    });
  }

  function _bindAtlasShellFallbackDismiss(overlay, surface) {
    if (_atlasShellFallbackHandle && typeof _atlasShellFallbackHandle.dispose === 'function') {
      _atlasShellFallbackHandle.dispose();
    }
    let cancelled = false;
    let disposed = false;
    const closeControls = [
      surface?.querySelector?.(':scope > .sheet-grab') || null,
      document.querySelector('.atlas-close'),
    ].filter(Boolean);
    const close = (event) => {
      if (disposed || !overlay.classList.contains('open')) return;
      cancelled = true;
      _hideAtlasShellFallback();
      if (event && typeof event.preventDefault === 'function') event.preventDefault();
      if (event && typeof event.stopPropagation === 'function') event.stopPropagation();
    };
    const onKeydown = (event) => {
      if (!event || event.key !== 'Escape') return;
      close(event);
    };
    const onBackdropClick = (event) => {
      if (event && event.target !== overlay) return;
      close(event);
    };
    document.addEventListener('keydown', onKeydown, true);
    overlay.addEventListener('click', onBackdropClick);
    closeControls.forEach((control) => {
      control.addEventListener('click', close);
    });
    let handle = null;
    handle = {
      cancelled: () => cancelled,
      dispose: () => {
        if (disposed) return;
        disposed = true;
        document.removeEventListener('keydown', onKeydown, true);
        overlay.removeEventListener('click', onBackdropClick);
        closeControls.forEach((control) => {
          control.removeEventListener('click', close);
        });
        if (_atlasShellFallbackHandle === handle) _atlasShellFallbackHandle = null;
      },
    };
    _atlasShellFallbackHandle = handle;
    return handle;
  }

  async function _openAtlasShellFallback() {
    const overlay = await _ensureLazyDomFragment('atlas_overlay');
    if (!overlay) return null;
    const surface = document.getElementById('atlas-surface');
    const list = document.getElementById('atlas-list');
    overlay.classList.remove('u-hidden');
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
    if (list && !String(list.textContent || '').trim()) {
      list.textContent = 'Loading Atlas...';
    }
    if (typeof importedEmitUiEvent === 'function') {
      importedEmitUiEvent('app:interaction-surface-ready', { surface: 'atlas' });
    }
    return _bindAtlasShellFallbackDismiss(overlay, surface);
  }

  async function loadWatchersModal() {
    const cssReady = loadLazyAsset('watchers_css');
    const watchersModule = await loadLazyAsset('watchers_modal');
    await cssReady;
    return {
      openWatchersModal: _requireLazyModuleExport(watchersModule, 'openWatchersModal', value => (
        typeof value === 'function' && value !== lazyOpenWatchersModal
      )),
      closeWatchersModal: watchersModule?.closeWatchersModal || null,
      isWatchersOverlayOpen: watchersModule?.isWatchersOverlayOpen || null,
    };
  }

  async function loadProjectReport() {
    const cssReady = loadLazyAsset('projects_css');
    const reportModule = await loadLazyAsset('project_report');
    await cssReady;
    return _requireLazyModuleExport(reportModule, 'DarklabProjectReport', value => (
      value && typeof value.createProjectReportController === 'function'
    ));
  }

  async function loadProjectActivity() {
    const cssReady = loadLazyAsset('projects_css');
    const activityModule = await loadLazyAsset('project_activity');
    await cssReady;
    return _requireLazyModuleExport(activityModule, 'DarklabProjectActivity', value => (
      value && typeof value.createProjectActivityController === 'function'
    ));
  }

  async function loadProjectOverview() {
    const cssReady = loadLazyAsset('projects_css');
    const overviewModule = await loadLazyAsset('project_overview');
    await cssReady;
    return _requireLazyModuleExport(overviewModule, 'DarklabProjectOverview', value => (
      value && typeof value.createProjectOverviewController === 'function'
    ));
  }

  async function loadProjectMonitoring() {
    const cssReady = loadLazyAsset('projects_css');
    const monitoringModule = await loadLazyAsset('project_monitoring');
    await cssReady;
    return _requireLazyModuleExport(monitoringModule, 'DarklabProjectMonitoring', value => (
      value && typeof value.createProjectMonitoringController === 'function'
    ));
  }

  async function loadProjectAssessment() {
    const cssReady = loadLazyAsset('project_assessment_css');
    const assessmentModule = await loadLazyAsset('project_assessment');
    await cssReady;
    return _requireLazyModuleExport(assessmentModule, 'DarklabProjectAssessment', value => (
      value && typeof value.createProjectAssessmentController === 'function'
    ));
  }

  async function loadProjectArtifacts() {
    const cssReady = loadLazyAsset('projects_css');
    const artifactsModule = await loadLazyAsset('project_artifacts');
    await cssReady;
    return _requireLazyModuleExport(artifactsModule, 'DarklabProjectArtifacts', value => (
      value && typeof value.createProjectArtifactsController === 'function'
    ));
  }

  async function loadProjectPackages() {
    const cssReady = loadLazyAsset('projects_css');
    const packagesModule = await loadLazyAsset('project_packages');
    await cssReady;
    const DarklabProjectPackages = _requireLazyModuleExport(packagesModule, 'DarklabProjectPackages', value => (
      value && typeof value.createProjectPackagesController === 'function'
    ));
    window.DarklabProjectPackages = DarklabProjectPackages;
    return DarklabProjectPackages;
  }

  async function loadProjectNamespace(name, globalName, controllerName) {
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
  }

  const PROJECT_WORKSPACE_MODULE_LOADERS = Object.freeze({
    project_details: () => loadProjectNamespace(
      'project_details',
      'DarklabProjectDetails',
      'createProjectDetailsController',
    ),
    project_list: () => loadProjectNamespace(
      'project_list',
      'DarklabProjectList',
      'createProjectListController',
    ),
    project_navigation: () => loadProjectNamespace(
      'project_navigation',
      'DarklabProjectNavigation',
      'createProjectNavigationController',
    ),
    project_entity_editor: () => loadProjectNamespace(
      'project_entity_editor',
      'DarklabProjectEntityEditor',
      'createProjectEntityEditorController',
    ),
    project_workspace_actions: () => loadProjectNamespace(
      'project_workspace_actions',
      'DarklabProjectWorkspaceActions',
      'createProjectWorkspaceActionsController',
    ),
    project_workspace_shell: () => loadProjectNamespace(
      'project_workspace_shell',
      'DarklabProjectWorkspaceShell',
      'createProjectWorkspaceShellController',
    ),
    project_workspace_lifecycle: () => loadProjectNamespace(
      'project_workspace_lifecycle',
      'DarklabProjectWorkspaceLifecycle',
      'createProjectWorkspaceLifecycleController',
    ),
    project_workspace_renderer: () => loadProjectNamespace(
      'project_workspace_renderer',
      'DarklabProjectWorkspaceRenderer',
      'createProjectWorkspaceRendererController',
    ),
    project_workspace_bootstrap: () => loadProjectNamespace(
      'project_workspace_bootstrap',
      'DarklabProjectWorkspaceBootstrap',
      'createProjectWorkspaceBootstrapController',
    ),
    project_nested_sheets: () => loadProjectNamespace(
      'project_nested_sheets',
      'DarklabProjectNestedSheets',
      'createProjectNestedSheetsController',
    ),
    project_workspace_events: () => loadProjectNamespace(
      'project_workspace_events',
      'DarklabProjectWorkspaceEvents',
      'createProjectWorkspaceEventsController',
    ),
    project_targets: () => loadProjectNamespace(
      'project_targets',
      'DarklabProjectTargets',
      'createProjectTargetsController',
    ),
    project_runs: () => loadProjectNamespace(
      'project_runs',
      'DarklabProjectRuns',
      'createProjectRunsController',
    ),
    project_mobile_compare: () => loadProjectNamespace(
      'project_mobile_compare',
      'DarklabProjectMobileCompare',
      'createProjectMobileCompareController',
    ),
    project_mobile_shell: () => loadProjectNamespace(
      'project_mobile_shell',
      'DarklabProjectMobileShell',
      'createProjectMobileShellController',
    ),
    project_mobile_detail: () => loadProjectNamespace(
      'project_mobile_detail',
      'DarklabProjectMobileDetail',
      'createProjectMobileDetailController',
    ),
    project_findings_data: () => loadProjectNamespace(
      'project_findings_data',
      'DarklabProjectFindingsData',
      'createProjectFindingsDataController',
    ),
    project_filters: () => loadProjectNamespace(
      'project_filters',
      'DarklabProjectFilters',
      'createProjectFiltersController',
    ),
    project_entities: () => loadProjectNamespace(
      'project_entities',
      'DarklabProjectEntities',
      'createProjectEntitiesController',
    ),
    project_findings: () => loadProjectNamespace(
      'project_findings',
      'DarklabProjectFindings',
      'createProjectFindingsController',
    ),
    project_findings_board: () => loadProjectNamespace(
      'project_findings_board',
      'DarklabProjectFindingsBoard',
      'createProjectFindingsBoardController',
    ),
  });
  const PROJECT_WORKSPACE_MODULE_GLOBALS = Object.freeze({
    project_details: 'DarklabProjectDetails',
    project_list: 'DarklabProjectList',
    project_navigation: 'DarklabProjectNavigation',
    project_entity_editor: 'DarklabProjectEntityEditor',
    project_workspace_actions: 'DarklabProjectWorkspaceActions',
    project_workspace_shell: 'DarklabProjectWorkspaceShell',
    project_workspace_lifecycle: 'DarklabProjectWorkspaceLifecycle',
    project_workspace_renderer: 'DarklabProjectWorkspaceRenderer',
    project_workspace_bootstrap: 'DarklabProjectWorkspaceBootstrap',
    project_nested_sheets: 'DarklabProjectNestedSheets',
    project_workspace_events: 'DarklabProjectWorkspaceEvents',
    project_targets: 'DarklabProjectTargets',
    project_runs: 'DarklabProjectRuns',
    project_mobile_compare: 'DarklabProjectMobileCompare',
    project_mobile_shell: 'DarklabProjectMobileShell',
    project_mobile_detail: 'DarklabProjectMobileDetail',
    project_findings_data: 'DarklabProjectFindingsData',
    project_filters: 'DarklabProjectFilters',
    project_entities: 'DarklabProjectEntities',
    project_findings: 'DarklabProjectFindings',
    project_findings_board: 'DarklabProjectFindingsBoard',
  });
  const PROJECT_WORKSPACE_CORE_MODULES = Object.freeze([
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
  ]);
  const PROJECT_WORKSPACE_ALL_MODULES = Object.freeze(Object.keys(PROJECT_WORKSPACE_MODULE_LOADERS));

  async function loadProjectWorkspace(options = {}) {
    const cssReady = loadLazyAsset('projects_css');
    const requestedModules = Array.isArray(options.modules) && options.modules.length
      ? options.modules
      : (options.includeDeferred === true ? PROJECT_WORKSPACE_ALL_MODULES : PROJECT_WORKSPACE_CORE_MODULES);
    const moduleNames = Array.from(new Set(requestedModules.map(name => String(name || '').trim()).filter(Boolean)));
    const namespaces = await Promise.all(moduleNames.map(async (name) => {
      const loader = PROJECT_WORKSPACE_MODULE_LOADERS[name];
      if (!loader) throw new Error(`Unknown Project workspace module: ${name}`);
      const namespace = await loader();
      const globalName = PROJECT_WORKSPACE_MODULE_GLOBALS[name];
      return [globalName, namespace];
    }));
    await cssReady;
    return Object.fromEntries(namespaces);
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
    const cssReady = loadLazyAsset('command_registry_css');
    const registryModule = await loadLazyAsset('command_registry');
    await cssReady;
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
    const cssReady = loadLazyAsset('workflows_css');
    const workflowsModule = await loadLazyAsset('workflows');
    await cssReady;
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
    const cssReady = loadLazyAsset('run_comparison_css');
    const coreModule = await loadLazyAsset('history_compare_core');
    const overlayModule = await loadLazyAsset('history_compare_overlay');
    const controlsModule = await loadLazyAsset('history_compare_controls');
    const navigationModule = await loadLazyAsset('history_compare_navigation');
    const rendererModule = await loadLazyAsset('history_compare_renderer');
    const launcherModule = await loadLazyAsset('history_compare_launcher');
    await cssReady;
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
    const cssReady = loadLazyAsset('schedules_css');
    const schedulesModule = await loadLazyAsset('schedules_modal');
    await cssReady;
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

  async function loadTourCliCommand() {
    const tourModule = await loadLazyAsset('tour_cli');
    return _requireLazyModuleExport(tourModule, 'handleTourCommand', value => typeof value === 'function');
  }

  async function loadStatusMonitor() {
    const cssReady = loadLazyAsset('status_monitor_css');
    const coreModule = await loadLazyAsset('status_monitor_core');
    const dataModule = await loadLazyAsset('status_monitor_data');
    const resourcesModule = await loadLazyAsset('status_monitor_resources');
    const monitorModule = await loadLazyAsset('status_monitor');
    await cssReady;
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

  async function loadWorkspaceSurface() {
    const cssReady = loadLazyAsset('workspace_css');
    const workspaceModule = await loadLazyAsset('workspace');
    await loadLazyAsset('workspace_drag_drop');
    await cssReady;
    if (typeof importedSetWorkspaceHandlers === 'function') {
      importedSetWorkspaceHandlers(workspaceModule || {});
    }
    return workspaceModule;
  }

  async function lazyOpenFindingsBoard(options = {}) {
    const board = await loadFindingsBoard();
    const open = board?.openFindingsBoard;
    if (typeof open !== 'function' || open === lazyOpenFindingsBoard) return false;
    return open(options);
  }

  async function lazyOpenAtlas(options = {}) {
    const initialLoad = _createAtlasInitialLoad(options);
    let shellFallback = null;
    try {
      shellFallback = await _openAtlasShellFallback();
      const atlas = await loadAtlasOverlay();
      if (shellFallback && typeof shellFallback.cancelled === 'function' && shellFallback.cancelled()) {
        _settleAtlasInitialLoad(initialLoad, 'fallback_cancelled');
        if (typeof shellFallback.dispose === 'function') shellFallback.dispose();
        return false;
      }
      if (shellFallback && typeof shellFallback.dispose === 'function') shellFallback.dispose();
      shellFallback = null;
      const open = atlas?.openAtlas;
      if (typeof open !== 'function' || open === lazyOpenAtlas) {
        _settleAtlasInitialLoad(initialLoad, 'controller_unavailable');
        return false;
      }
      return initialLoad ? open({ ...options, initialLoad }) : open(options);
    } catch (err) {
      _settleAtlasInitialLoad(initialLoad, 'open_failed');
      if (shellFallback && typeof shellFallback.dispose === 'function') shellFallback.dispose();
      throw err;
    }
  }

  async function lazyOpenAtlasQuickLookup(options = {}) {
    let shellFallback = null;
    try {
      shellFallback = await _openAtlasShellFallback();
      const atlas = await loadAtlasOverlay();
      if (shellFallback && typeof shellFallback.cancelled === 'function' && shellFallback.cancelled()) {
        if (typeof shellFallback.dispose === 'function') shellFallback.dispose();
        return false;
      }
      if (shellFallback && typeof shellFallback.dispose === 'function') shellFallback.dispose();
      shellFallback = null;
      const open = atlas?.openAtlasQuickLookup;
      if (typeof open !== 'function' || open === lazyOpenAtlasQuickLookup) {
        const error = new Error('Quick Lookup controller is unavailable');
        error.quickLookupStage = 'controller';
        throw error;
      }
      return open(options);
    } catch (err) {
      if (shellFallback && typeof shellFallback.dispose === 'function') shellFallback.dispose();
      throw err;
    }
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

  async function lazyOpenHistoryCompareLauncher(run, options = {}) {
    const compare = await loadHistoryCompare();
    const open = compare?.openHistoryCompareLauncher;
    if (typeof open !== 'function' || open === lazyOpenHistoryCompareLauncher) return false;
    return open(run, options);
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
  window.loadExportHtmlUtils = loadExportHtmlUtils;
  window.loadExportPdfUtils = loadExportPdfUtils;
  window.loadAtlasOverlay = loadAtlasOverlay;
  window.loadFindingsBoard = loadFindingsBoard;
  window.loadFindingTriageEditor = loadFindingTriageEditor;
  window.loadProjectActivity = loadProjectActivity;
  window.loadProjectAssessment = loadProjectAssessment;
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
  window.loadTourCliCommand = loadTourCliCommand;
  window.loadTourModal = loadTourModal;
  window.loadStatusMonitor = loadStatusMonitor;
  window.loadMobileRunningIndicator = loadMobileRunningIndicator;
  window.loadWorkspaceSurface = loadWorkspaceSurface;
  exportedLoadAtlasOverlay = loadAtlasOverlay;
  exportedLoadCommandRegistry = loadCommandRegistry;
  exportedLoadFindingsBoard = loadFindingsBoard;
  exportedLoadFindingTriageEditor = loadFindingTriageEditor;
  exportedLoadMobileRunningIndicator = loadMobileRunningIndicator;
  exportedLoadSchedulesModal = loadSchedulesModal;
  exportedLoadTourCliCommand = loadTourCliCommand;
  exportedLoadWorkspaceSurface = loadWorkspaceSurface;
  exportedLoadWatchersModal = loadWatchersModal;
  if (typeof importedSetAtlasDetailLoader === 'function') importedSetAtlasDetailLoader(loadAtlasDetailRenderer);
  if (typeof importedSetAtlasMobileLoader === 'function') importedSetAtlasMobileLoader(loadAtlasMobileController);
  if (typeof window.openAtlas !== 'function') window.openAtlas = lazyOpenAtlas;
  if (typeof window.openAtlasQuickLookup !== 'function') {
    window.openAtlasQuickLookup = lazyOpenAtlasQuickLookup;
  }
  if (typeof window.closeAtlas !== 'function') window.closeAtlas = lazyCloseAtlas;
  if (typeof window.isAtlasOverlayOpen !== 'function') window.isAtlasOverlayOpen = lazyIsAtlasOverlayOpen;
  if (typeof window.cycleAtlasTab !== 'function') window.cycleAtlasTab = lazyCycleAtlasTab;
  if (typeof importedSetAtlasHandlers === 'function') {
    importedSetAtlasHandlers({
      openAtlas: lazyOpenAtlas,
      openAtlasQuickLookup: lazyOpenAtlasQuickLookup,
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
  exportedLoadExportHtmlUtils = loadExportHtmlUtils;
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

function loadFindingTriageEditor(...args) {
  return typeof exportedLoadFindingTriageEditor === 'function'
    ? exportedLoadFindingTriageEditor(...args)
    : Promise.resolve(null);
}

function loadExportHtmlUtils(...args) {
  return typeof exportedLoadExportHtmlUtils === 'function'
    ? exportedLoadExportHtmlUtils(...args)
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

function loadTourCliCommand(...args) {
  return typeof exportedLoadTourCliCommand === 'function'
    ? exportedLoadTourCliCommand(...args)
    : Promise.resolve(null);
}

function loadWatchersModal(...args) {
  return typeof exportedLoadWatchersModal === 'function'
    ? exportedLoadWatchersModal(...args)
    : Promise.resolve(null);
}

function loadWorkspaceSurface(...args) {
  return typeof exportedLoadWorkspaceSurface === 'function'
    ? exportedLoadWorkspaceSurface(...args)
    : Promise.resolve(null);
}

export {
  loadAtlasOverlay,
  loadCommandRegistry,
  loadExportHtmlUtils,
  loadFindingsBoard,
  loadFindingTriageEditor,
  loadMobileRunningIndicator,
  loadSchedulesModal,
  loadTourCliCommand,
  loadWorkspaceSurface,
  loadWatchersModal,
};
