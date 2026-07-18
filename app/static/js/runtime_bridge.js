// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Neutral runtime-service boundary for modules that would otherwise cycle
// through session.js or status_monitor.js.

const RUNTIME_BRIDGE_GLOBAL = typeof window !== 'undefined' ? window : globalThis;
const missingRuntimeHandlersLogged = new Set();
const runtimeHandlers = RUNTIME_BRIDGE_GLOBAL.__darklabRuntimeHandlers || {
  apiFetch: null,
  getSessionId: null,
  logClientError: null,
  openStatusMonitor: null,
  refreshWorkspaceFiles: null,
  refreshStatusMonitor: null,
};

if (RUNTIME_BRIDGE_GLOBAL) {
  RUNTIME_BRIDGE_GLOBAL.__darklabRuntimeHandlers = runtimeHandlers;
}

function setRuntimeHandlers(handlers = {}) {
  const registered = [];
  Object.keys(runtimeHandlers).forEach((name) => {
    if (typeof handlers[name] === 'function') {
      runtimeHandlers[name] = handlers[name];
      registered.push(name);
    }
  });
  _logRuntimeBridgeDiagnostic('debug', 'RUNTIME_HANDLER_REGISTERED', {
    registered_handlers: registered,
    available_handlers: _registeredRuntimeHandlers(),
  });
}

function hasRuntimeHandler(name) {
  return typeof runtimeHandlers[name] === 'function';
}

function _runtimeBridgeWarningsEnabled() {
  const config = (
    RUNTIME_BRIDGE_GLOBAL?.APP_CONFIG
    && typeof RUNTIME_BRIDGE_GLOBAL.APP_CONFIG === 'object'
    && !Array.isArray(RUNTIME_BRIDGE_GLOBAL.APP_CONFIG)
  ) ? RUNTIME_BRIDGE_GLOBAL.APP_CONFIG : {};
  return config.frontend_bridge_warnings === true
    || config.debug === true
    || config.dev_mode === true
    || config.environment === 'development'
    || config.env === 'development';
}

function _registeredRuntimeHandlers() {
  return Object.keys(runtimeHandlers).filter(name => typeof runtimeHandlers[name] === 'function');
}

function _logRuntimeBridgeDiagnostic(level, event, details = {}) {
  if (!_runtimeBridgeWarningsEnabled()) return;
  const consoleApi = RUNTIME_BRIDGE_GLOBAL?.console || globalThis?.console;
  const method = level === 'error' ? 'error' : level === 'warning' ? 'warn' : 'debug';
  const log = consoleApi && (consoleApi[method] || consoleApi.log);
  if (typeof log !== 'function') return;
  log.call(consoleApi, `[darklab] ${event}`, {
    event,
    level,
    ...details,
  });
}

function _logMissingRuntimeHandler(handler, requestedOperation, level = 'warning') {
  const key = `${handler}:${requestedOperation}`;
  if (missingRuntimeHandlersLogged.has(key)) return;
  missingRuntimeHandlersLogged.add(key);
  _logRuntimeBridgeDiagnostic(level, 'RUNTIME_HANDLER_MISSING', {
    handler,
    requested_operation: requestedOperation,
    registered_handlers: _registeredRuntimeHandlers(),
  });
}

function apiFetch(...args) {
  if (typeof runtimeHandlers.apiFetch !== 'function') {
    _logMissingRuntimeHandler('apiFetch', 'apiFetch', 'error');
    return Promise.reject(new Error('apiFetch is not available'));
  }
  return runtimeHandlers.apiFetch(...args);
}

function getSessionId() {
  return typeof runtimeHandlers.getSessionId === 'function'
    ? runtimeHandlers.getSessionId()
    : '';
}

function logClientError(...args) {
  if (typeof runtimeHandlers.logClientError === 'function') {
    return runtimeHandlers.logClientError(...args);
  }
  _logMissingRuntimeHandler('logClientError', String(args[0] || 'logClientError'), 'error');
  return undefined;
}

function refreshStatusMonitor(...args) {
  if (typeof runtimeHandlers.refreshStatusMonitor === 'function') {
    return runtimeHandlers.refreshStatusMonitor(...args);
  }
  _logMissingRuntimeHandler('refreshStatusMonitor', 'refreshStatusMonitor', 'warning');
  return null;
}

function refreshWorkspaceFiles(...args) {
  if (typeof runtimeHandlers.refreshWorkspaceFiles === 'function') {
    return runtimeHandlers.refreshWorkspaceFiles(...args);
  }
  _logMissingRuntimeHandler('refreshWorkspaceFiles', 'refreshWorkspaceFiles', 'warning');
  return null;
}

function openStatusMonitor(...args) {
  if (typeof runtimeHandlers.openStatusMonitor === 'function') {
    return runtimeHandlers.openStatusMonitor(...args);
  }
  _logMissingRuntimeHandler('openStatusMonitor', 'openStatusMonitor', 'warning');
  return null;
}

if (RUNTIME_BRIDGE_GLOBAL) {
  RUNTIME_BRIDGE_GLOBAL.DarklabRuntime = {
    apiFetch,
    getSessionId,
    hasRuntimeHandler,
    logClientError,
    openStatusMonitor,
    refreshStatusMonitor,
    refreshWorkspaceFiles,
    setRuntimeHandlers,
  };
}

export {
  apiFetch,
  getSessionId,
  hasRuntimeHandler,
  logClientError,
  openStatusMonitor,
  refreshStatusMonitor,
  refreshWorkspaceFiles,
  setRuntimeHandlers,
};
