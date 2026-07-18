// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Neutral compare-action boundary shared by launcher and project run rows.

const HISTORY_COMPARE_BRIDGE_GLOBAL = typeof window !== 'undefined' ? window : globalThis;
const warnedMissingHistoryCompareHandlers = new Set();
let fetchAndRenderHistoryComparisonHandler = null;
let closeHistoryCompareActionMenusHandler = null;
let openHistoryCompareLauncherHandler = null;

function hasOwnHandler(handlers, name) {
  return Object.prototype.hasOwnProperty.call(handlers, name);
}

function _historyCompareBridgeWarningsEnabled() {
  const config = (
    HISTORY_COMPARE_BRIDGE_GLOBAL?.APP_CONFIG
    && typeof HISTORY_COMPARE_BRIDGE_GLOBAL.APP_CONFIG === 'object'
    && !Array.isArray(HISTORY_COMPARE_BRIDGE_GLOBAL.APP_CONFIG)
  ) ? HISTORY_COMPARE_BRIDGE_GLOBAL.APP_CONFIG : {};
  return config.frontend_bridge_warnings === true
    || config.debug === true
    || config.dev_mode === true
    || config.environment === 'development'
    || config.env === 'development';
}

function _logHistoryCompareBridgeDiagnostic(level, event, details = {}) {
  if (!_historyCompareBridgeWarningsEnabled()) return;
  const consoleApi = HISTORY_COMPARE_BRIDGE_GLOBAL?.console || globalThis?.console;
  const method = level === 'error' ? 'error' : level === 'warning' ? 'warn' : 'debug';
  const log = consoleApi && (consoleApi[method] || consoleApi.log);
  if (typeof log !== 'function') return;
  log.call(consoleApi, `[darklab] ${event}`, {
    event,
    level,
    ...details,
  });
}

function _warnMissingHistoryCompareHandler(name) {
  if (warnedMissingHistoryCompareHandlers.has(name)) return;
  warnedMissingHistoryCompareHandlers.add(name);
  _logHistoryCompareBridgeDiagnostic('warning', 'HISTORY_COMPARE_HANDLER_MISSING', {
    handler: name,
  });
}

function setHistoryCompareHandlers(handlers = {}) {
  if (hasOwnHandler(handlers, 'fetchAndRenderHistoryComparison')
    && handlers.fetchAndRenderHistoryComparison === null) {
    fetchAndRenderHistoryComparisonHandler = null;
  } else if (typeof handlers.fetchAndRenderHistoryComparison === 'function') {
    fetchAndRenderHistoryComparisonHandler = handlers.fetchAndRenderHistoryComparison;
  }
  if (hasOwnHandler(handlers, 'openHistoryCompareLauncher')
    && handlers.openHistoryCompareLauncher === null) {
    openHistoryCompareLauncherHandler = null;
  } else if (typeof handlers.openHistoryCompareLauncher === 'function') {
    openHistoryCompareLauncherHandler = handlers.openHistoryCompareLauncher;
  }
  if (hasOwnHandler(handlers, 'closeHistoryCompareActionMenus')
    && handlers.closeHistoryCompareActionMenus === null) {
    closeHistoryCompareActionMenusHandler = null;
  } else if (typeof handlers.closeHistoryCompareActionMenus === 'function') {
    closeHistoryCompareActionMenusHandler = handlers.closeHistoryCompareActionMenus;
  }
}

function hasHistoryCompareHandler(name) {
  const handlers = {
    closeHistoryCompareActionMenus: closeHistoryCompareActionMenusHandler,
    fetchAndRenderHistoryComparison: fetchAndRenderHistoryComparisonHandler,
    openHistoryCompareLauncher: openHistoryCompareLauncherHandler,
  };
  return typeof handlers[name] === 'function';
}

function closeHistoryCompareActionMenus(...args) {
  if (typeof closeHistoryCompareActionMenusHandler === 'function') {
    return closeHistoryCompareActionMenusHandler(...args);
  }
  _warnMissingHistoryCompareHandler('closeHistoryCompareActionMenus');
  return undefined;
}
closeHistoryCompareActionMenus.hasHandler = () => hasHistoryCompareHandler('closeHistoryCompareActionMenus');

function fetchAndRenderHistoryComparison(...args) {
  if (typeof fetchAndRenderHistoryComparisonHandler === 'function') {
    return fetchAndRenderHistoryComparisonHandler(...args);
  }
  _warnMissingHistoryCompareHandler('fetchAndRenderHistoryComparison');
  return undefined;
}
fetchAndRenderHistoryComparison.hasHandler = () => hasHistoryCompareHandler('fetchAndRenderHistoryComparison');

function openHistoryCompareLauncher(...args) {
  if (typeof openHistoryCompareLauncherHandler === 'function') {
    return openHistoryCompareLauncherHandler(...args);
  }
  _warnMissingHistoryCompareHandler('openHistoryCompareLauncher');
  return undefined;
}
openHistoryCompareLauncher.hasHandler = () => hasHistoryCompareHandler('openHistoryCompareLauncher');

export {
  closeHistoryCompareActionMenus,
  fetchAndRenderHistoryComparison,
  hasHistoryCompareHandler,
  openHistoryCompareLauncher,
  setHistoryCompareHandlers,
};
