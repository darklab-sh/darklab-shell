// Neutral Output boundary for tabs and runtime consumers that would otherwise
// create cycles back through output.js.
//
// Contract: output.js must call setOutputHandlers(...) before consumers invoke
// these delegates. If APP_CONFIG.frontend_bridge_warnings/debug/dev_mode is
// enabled, a missing handler warns once and then returns the documented
// compatibility fallback.

const OUTPUT_BRIDGE_GLOBAL = typeof window !== 'undefined' ? window : globalThis;
const warnedMissingOutputHandlers = new Set();
const outputHandlers = {
  resetAnsiRendererForTab: null,
  dropAnsiRendererForTab: null,
  hasPendingOutputBatch: null,
  _maybeMountDeferredPrompt: null,
  syncOutputPrefixes: null,
  _resetTabOutputSignalCounts: null,
  _cancelPendingOutputBatch: null,
  _stickOutputToBottom: null,
  _restoreOutputTailAfterLayout: null,
  appendLine: null,
  appendLines: null,
  isTabSessionRestoreInProgress: null,
};

function setOutputHandlers(handlers = {}) {
  const registered = [];
  Object.keys(outputHandlers).forEach((name) => {
    if (typeof handlers[name] === 'function') {
      outputHandlers[name] = handlers[name];
      registered.push(name);
    }
  });
  _logOutputBridgeDiagnostic('debug', 'OUTPUT_BRIDGE_HANDLER_REGISTERED', {
    registered_handlers: registered,
  });
}

function hasOutputHandler(name) {
  return typeof outputHandlers[name] === 'function';
}

function _bridgeWarningsEnabled() {
  const config = (
    OUTPUT_BRIDGE_GLOBAL?.APP_CONFIG
    && typeof OUTPUT_BRIDGE_GLOBAL.APP_CONFIG === 'object'
    && !Array.isArray(OUTPUT_BRIDGE_GLOBAL.APP_CONFIG)
  ) ? OUTPUT_BRIDGE_GLOBAL.APP_CONFIG : {};
  return config.frontend_bridge_warnings === true
    || config.debug === true
    || config.dev_mode === true
    || config.environment === 'development'
    || config.env === 'development';
}

function _warnMissingOutputHandler(name) {
  if (warnedMissingOutputHandlers.has(name) || !_bridgeWarningsEnabled()) return;
  warnedMissingOutputHandlers.add(name);
  _logOutputBridgeDiagnostic(name === 'appendLine' || name === 'appendLines' ? 'error' : 'warning', 'OUTPUT_BRIDGE_HANDLER_MISSING', {
    handler: name,
    fallback: _outputFallback(name),
  });
}

function _logOutputBridgeDiagnostic(level, event, details = {}) {
  if (!_bridgeWarningsEnabled()) return;
  const consoleApi = OUTPUT_BRIDGE_GLOBAL?.console || globalThis?.console;
  const method = level === 'error' ? 'error' : level === 'warning' ? 'warn' : 'debug';
  const log = consoleApi && (consoleApi[method] || consoleApi.log);
  if (typeof log !== 'function') return;
  log.call(consoleApi, `[darklab] ${event}`, {
    event,
    level,
    ...details,
  });
}

function _outputFallback(name) {
  if (name === 'appendLines') return 'resolved_promise';
  if (name === 'hasPendingOutputBatch' || name === 'isTabSessionRestoreInProgress') return 'boolean';
  return 'undefined';
}

function _callOutputHandler(name, fallback, args) {
  if (typeof outputHandlers[name] === 'function') return outputHandlers[name](...args);
  _warnMissingOutputHandler(name);
  return fallback;
}

function resetAnsiRendererForTab(...args) { return _callOutputHandler('resetAnsiRendererForTab', undefined, args); }
function dropAnsiRendererForTab(...args) { return _callOutputHandler('dropAnsiRendererForTab', undefined, args); }
function hasPendingOutputBatch(...args) { return _callOutputHandler('hasPendingOutputBatch', false, args); }
function _maybeMountDeferredPrompt(...args) { return _callOutputHandler('_maybeMountDeferredPrompt', undefined, args); }
function syncOutputPrefixes(...args) { return _callOutputHandler('syncOutputPrefixes', undefined, args); }
function _resetTabOutputSignalCounts(...args) { return _callOutputHandler('_resetTabOutputSignalCounts', undefined, args); }
function _cancelPendingOutputBatch(...args) { return _callOutputHandler('_cancelPendingOutputBatch', undefined, args); }
function _stickOutputToBottom(...args) { return _callOutputHandler('_stickOutputToBottom', undefined, args); }
function _restoreOutputTailAfterLayout(...args) { return _callOutputHandler('_restoreOutputTailAfterLayout', undefined, args); }
function appendLine(...args) { return _callOutputHandler('appendLine', undefined, args); }
function appendLines(...args) { return _callOutputHandler('appendLines', Promise.resolve(), args); }
function isTabSessionRestoreInProgress(...args) {
  return _callOutputHandler('isTabSessionRestoreInProgress', false, args);
}

export {
  _cancelPendingOutputBatch,
  _maybeMountDeferredPrompt,
  _resetTabOutputSignalCounts,
  _restoreOutputTailAfterLayout,
  _stickOutputToBottom,
  appendLine,
  appendLines,
  dropAnsiRendererForTab,
  hasOutputHandler,
  hasPendingOutputBatch,
  isTabSessionRestoreInProgress,
  resetAnsiRendererForTab,
  setOutputHandlers,
  syncOutputPrefixes,
};
