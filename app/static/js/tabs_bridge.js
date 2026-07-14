// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Neutral Tabs boundary for tab feature modules that would otherwise cycle
// through tabs.js during source-mode ESM evaluation.
//
// Contract: tabs.js must call setTabHandlers(...) before consumers invoke these
// delegates. If APP_CONFIG.frontend_bridge_warnings/debug/dev_mode is enabled,
// a missing handler warns once and then returns the documented compatibility
// fallback.

const TABS_BRIDGE_GLOBAL = typeof window !== 'undefined' ? window : globalThis;
const warnedMissingTabHandlers = new Set();
const tabHandlers = TABS_BRIDGE_GLOBAL.__darklabTabHandlers || {
  _clearTabRunningLabelTimer: null,
  _getNeighborTabIdAfterClose: null,
  _getTabEl: null,
  _getTabPanelEl: null,
  activateTab: null,
  clearTab: null,
  createDefaultTabLabel: null,
  createTab: null,
  ensureActiveTabVisible: null,
  getOutput: null,
  mountShellPrompt: null,
  setTabLabel: null,
  setTabStatus: null,
  syncTabOrderFromDom: null,
  unmountShellPrompt: null,
  updateNewTabBtn: null,
  updateOutputFollowButton: null,
  updateTabScrollButtons: null,
};

if (TABS_BRIDGE_GLOBAL) {
  TABS_BRIDGE_GLOBAL.__darklabTabHandlers = tabHandlers;
}

function setTabHandlers(handlers = {}) {
  const registered = [];
  Object.keys(tabHandlers).forEach((name) => {
    if (typeof handlers[name] === 'function') {
      tabHandlers[name] = handlers[name];
      registered.push(name);
    }
  });
  _logTabBridgeDiagnostic('debug', 'TABS_BRIDGE_HANDLER_REGISTERED', {
    registered_handlers: registered,
  });
}

function hasTabHandler(name) {
  return typeof tabHandlers[name] === 'function';
}

function _bridgeWarningsEnabled() {
  const config = (
    TABS_BRIDGE_GLOBAL?.APP_CONFIG
    && typeof TABS_BRIDGE_GLOBAL.APP_CONFIG === 'object'
    && !Array.isArray(TABS_BRIDGE_GLOBAL.APP_CONFIG)
  ) ? TABS_BRIDGE_GLOBAL.APP_CONFIG : {};
  return config.frontend_bridge_warnings === true
    || config.debug === true
    || config.dev_mode === true
    || config.environment === 'development'
    || config.env === 'development';
}

function _warnMissingTabHandler(name) {
  if (warnedMissingTabHandlers.has(name) || !_bridgeWarningsEnabled()) return;
  warnedMissingTabHandlers.add(name);
  _logTabBridgeDiagnostic('warning', 'TABS_BRIDGE_HANDLER_MISSING', {
    handler: name,
    fallback: _tabFallback(name),
  });
}

function _logTabBridgeDiagnostic(level, event, details = {}) {
  if (!_bridgeWarningsEnabled()) return;
  const consoleApi = TABS_BRIDGE_GLOBAL?.console || globalThis?.console;
  const log = consoleApi && ((level === 'debug' ? consoleApi.debug : consoleApi.warn) || consoleApi.log);
  if (typeof log !== 'function') return;
  log.call(consoleApi, `[darklab] ${event}`, {
    event,
    level,
    ...details,
  });
}

function _tabFallback(name) {
  if (name === '_getNeighborTabIdAfterClose' || name === '_getTabEl' || name === '_getTabPanelEl' || name === 'createTab' || name === 'getOutput') return 'null';
  if (name === 'createDefaultTabLabel') return 'generated_label';
  return 'undefined';
}

function _callTabHandler(name, fallback, args) {
  if (typeof tabHandlers[name] === 'function') return tabHandlers[name](...args);
  _warnMissingTabHandler(name);
  return fallback;
}

function _clearTabRunningLabelTimer(...args) { return _callTabHandler('_clearTabRunningLabelTimer', undefined, args); }
function _getNeighborTabIdAfterClose(...args) { return _callTabHandler('_getNeighborTabIdAfterClose', null, args); }
function _getTabEl(...args) { return _callTabHandler('_getTabEl', null, args); }
function _getTabPanelEl(...args) { return _callTabHandler('_getTabPanelEl', null, args); }
function activateTab(...args) { return _callTabHandler('activateTab', undefined, args); }
function clearTab(...args) { return _callTabHandler('clearTab', undefined, args); }
function createDefaultTabLabel(...args) { return _callTabHandler('createDefaultTabLabel', `shell ${args[0] || ''}`.trim(), args); }
function createTab(...args) { return _callTabHandler('createTab', null, args); }
function ensureActiveTabVisible(...args) { return _callTabHandler('ensureActiveTabVisible', undefined, args); }
function getOutput(...args) { return _callTabHandler('getOutput', null, args); }
function mountShellPrompt(...args) { return _callTabHandler('mountShellPrompt', undefined, args); }
function setTabLabel(...args) { return _callTabHandler('setTabLabel', undefined, args); }
function setTabStatus(...args) { return _callTabHandler('setTabStatus', undefined, args); }
function syncTabOrderFromDom(...args) { return _callTabHandler('syncTabOrderFromDom', undefined, args); }
function unmountShellPrompt(...args) { return _callTabHandler('unmountShellPrompt', undefined, args); }
function updateNewTabBtn(...args) { return _callTabHandler('updateNewTabBtn', undefined, args); }
function updateOutputFollowButton(...args) { return _callTabHandler('updateOutputFollowButton', undefined, args); }
function updateTabScrollButtons(...args) { return _callTabHandler('updateTabScrollButtons', undefined, args); }

if (TABS_BRIDGE_GLOBAL) {
  TABS_BRIDGE_GLOBAL.DarklabTabs = {
    _clearTabRunningLabelTimer,
    _getNeighborTabIdAfterClose,
    _getTabEl,
    _getTabPanelEl,
    activateTab,
    clearTab,
    createDefaultTabLabel,
    createTab,
    ensureActiveTabVisible,
    getOutput,
    hasTabHandler,
    mountShellPrompt,
    setTabHandlers,
    setTabLabel,
    setTabStatus,
    syncTabOrderFromDom,
    unmountShellPrompt,
    updateNewTabBtn,
    updateOutputFollowButton,
    updateTabScrollButtons,
  };
}

export {
  _clearTabRunningLabelTimer,
  _getNeighborTabIdAfterClose,
  _getTabEl,
  _getTabPanelEl,
  activateTab,
  clearTab,
  createDefaultTabLabel,
  createTab,
  ensureActiveTabVisible,
  getOutput,
  hasTabHandler,
  mountShellPrompt,
  setTabHandlers,
  setTabLabel,
  setTabStatus,
  syncTabOrderFromDom,
  unmountShellPrompt,
  updateNewTabBtn,
  updateOutputFollowButton,
  updateTabScrollButtons,
};
