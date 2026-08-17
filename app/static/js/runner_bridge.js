// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Neutral Runner boundary for UI modules that would otherwise cycle through
// runner.js.
//
// Contract: runner.js must call setRunnerHandlers(...) before consumers invoke
// these delegates. If APP_CONFIG.frontend_bridge_warnings/debug/dev_mode is
// enabled, a missing handler warns once and then returns the documented
// compatibility fallback.

const RUNNER_BRIDGE_GLOBAL = typeof window !== 'undefined' ? window : globalThis;
const warnedMissingRunnerHandlers = new Set();
const runnerHandlers = RUNNER_BRIDGE_GLOBAL.__darklabRunnerHandlers || {
  _readRunErrorMessage: null,
  _seedLocalStorageStarsToServer: null,
  _setRunButtonDisabled: null,
  _sseMessageFromChunk: null,
  appendCommandEcho: null,
  attachActiveRunFromMonitor: null,
  cancelPendingTerminalConfirm: null,
  confirmKill: null,
  detachRunStreamForTab: null,
  doKill: null,
  hasPendingTerminalConfirm: null,
  interruptPromptLine: null,
  killActiveRunFromMonitor: null,
  pauseBackgroundRunStreamsForStatusMonitor: null,
  resumeBackgroundRunStreamsAfterStatusMonitor: null,
  runCommand: null,
  setStatus: null,
  startPollingActiveRunsAfterReload: null,
  startTimer: null,
  stopTimer: null,
  submitCommand: null,
  submitComposerCommand: null,
  submitVisibleComposerCommand: null,
  syncActiveRunTimer: null,
  syncPendingTerminalConfirmPromptMode: null,
};

if (RUNNER_BRIDGE_GLOBAL) {
  RUNNER_BRIDGE_GLOBAL.__darklabRunnerHandlers = runnerHandlers;
}

function setRunnerHandlers(handlers = {}) {
  const registered = [];
  Object.keys(runnerHandlers).forEach((name) => {
    if (typeof handlers[name] === 'function') {
      runnerHandlers[name] = handlers[name];
      registered.push(name);
    }
  });
  _logRunnerBridgeDiagnostic('debug', 'RUNNER_BRIDGE_HANDLER_REGISTERED', {
    registered_handlers: registered,
  });
}

function hasRunnerHandler(name) {
  return typeof runnerHandlers[name] === 'function';
}

function _bridgeWarningsEnabled() {
  const config = (
    RUNNER_BRIDGE_GLOBAL?.APP_CONFIG
    && typeof RUNNER_BRIDGE_GLOBAL.APP_CONFIG === 'object'
    && !Array.isArray(RUNNER_BRIDGE_GLOBAL.APP_CONFIG)
  ) ? RUNNER_BRIDGE_GLOBAL.APP_CONFIG : {};
  return config.frontend_bridge_warnings === true
    || config.debug === true
    || config.dev_mode === true
    || config.environment === 'development'
    || config.env === 'development';
}

function _warnMissingRunnerHandler(name) {
  if (warnedMissingRunnerHandlers.has(name) || !_bridgeWarningsEnabled()) return;
  warnedMissingRunnerHandlers.add(name);
  _logRunnerBridgeDiagnostic(_criticalRunnerHandlerLevel(name), 'RUNNER_BRIDGE_HANDLER_MISSING', {
    handler: name,
    fallback_type: _runnerFallbackType(name),
  });
}

function _logRunnerBridgeDiagnostic(level, event, details = {}) {
  if (!_bridgeWarningsEnabled()) return;
  const consoleApi = RUNNER_BRIDGE_GLOBAL?.console || globalThis?.console;
  const method = level === 'error' ? 'error' : level === 'warning' ? 'warn' : 'debug';
  const log = consoleApi && (consoleApi[method] || consoleApi.log);
  if (typeof log !== 'function') return;
  log.call(consoleApi, `[darklab] ${event}`, {
    event,
    level,
    ...details,
  });
}

function _criticalRunnerHandlerLevel(name) {
  return [
    'doKill',
    'killActiveRunFromMonitor',
    'runCommand',
    'submitCommand',
    'submitComposerCommand',
    'submitVisibleComposerCommand',
  ].includes(name) ? 'error' : 'warning';
}

function _runnerFallbackType(name) {
  if (name === '_readRunErrorMessage' || name === '_seedLocalStorageStarsToServer') return 'resolved_promise';
  if (name === 'hasPendingTerminalConfirm' || name.startsWith('submit')) return 'boolean';
  return 'undefined';
}

function _callRunnerHandler(name, fallback, args) {
  if (typeof runnerHandlers[name] === 'function') return runnerHandlers[name](...args);
  _warnMissingRunnerHandler(name);
  return fallback;
}

function _readRunErrorMessage(...args) { return _callRunnerHandler('_readRunErrorMessage', Promise.resolve(''), args); }
function _seedLocalStorageStarsToServer(...args) { return _callRunnerHandler('_seedLocalStorageStarsToServer', Promise.resolve(), args); }
function _setRunButtonDisabled(...args) { return _callRunnerHandler('_setRunButtonDisabled', undefined, args); }
function _sseMessageFromChunk(...args) { return _callRunnerHandler('_sseMessageFromChunk', null, args); }
function appendCommandEcho(...args) { return _callRunnerHandler('appendCommandEcho', undefined, args); }
function attachActiveRunFromMonitor(...args) { return _callRunnerHandler('attachActiveRunFromMonitor', undefined, args); }
function cancelPendingTerminalConfirm(...args) { return _callRunnerHandler('cancelPendingTerminalConfirm', undefined, args); }
function confirmKill(...args) { return _callRunnerHandler('confirmKill', undefined, args); }
function detachRunStreamForTab(...args) { return _callRunnerHandler('detachRunStreamForTab', undefined, args); }
function doKill(...args) { return _callRunnerHandler('doKill', undefined, args); }
function hasPendingTerminalConfirm(...args) { return _callRunnerHandler('hasPendingTerminalConfirm', false, args); }
function interruptPromptLine(...args) { return _callRunnerHandler('interruptPromptLine', undefined, args); }
function killActiveRunFromMonitor(...args) { return _callRunnerHandler('killActiveRunFromMonitor', undefined, args); }
function pauseBackgroundRunStreamsForStatusMonitor(...args) { return _callRunnerHandler('pauseBackgroundRunStreamsForStatusMonitor', undefined, args); }
function resumeBackgroundRunStreamsAfterStatusMonitor(...args) { return _callRunnerHandler('resumeBackgroundRunStreamsAfterStatusMonitor', undefined, args); }
function runCommand(...args) { return _callRunnerHandler('runCommand', undefined, args); }
function setStatus(...args) { return _callRunnerHandler('setStatus', undefined, args); }
function startPollingActiveRunsAfterReload(...args) { return _callRunnerHandler('startPollingActiveRunsAfterReload', undefined, args); }
function startTimer(...args) { return _callRunnerHandler('startTimer', undefined, args); }
function stopTimer(...args) { return _callRunnerHandler('stopTimer', undefined, args); }
function submitCommand(...args) { return _callRunnerHandler('submitCommand', false, args); }
function submitComposerCommand(...args) { return _callRunnerHandler('submitComposerCommand', false, args); }
function submitVisibleComposerCommand(...args) { return _callRunnerHandler('submitVisibleComposerCommand', false, args); }
function syncActiveRunTimer(...args) { return _callRunnerHandler('syncActiveRunTimer', undefined, args); }
function syncPendingTerminalConfirmPromptMode(...args) { return _callRunnerHandler('syncPendingTerminalConfirmPromptMode', undefined, args); }

if (RUNNER_BRIDGE_GLOBAL) {
  RUNNER_BRIDGE_GLOBAL.DarklabRunner = {
    _readRunErrorMessage,
    _seedLocalStorageStarsToServer,
    _setRunButtonDisabled,
    _sseMessageFromChunk,
    appendCommandEcho,
    attachActiveRunFromMonitor,
    cancelPendingTerminalConfirm,
    confirmKill,
    detachRunStreamForTab,
    doKill,
    hasPendingTerminalConfirm,
    hasRunnerHandler,
    interruptPromptLine,
    killActiveRunFromMonitor,
    pauseBackgroundRunStreamsForStatusMonitor,
    resumeBackgroundRunStreamsAfterStatusMonitor,
    runCommand,
    setRunnerHandlers,
    setStatus,
    startPollingActiveRunsAfterReload,
    startTimer,
    stopTimer,
    submitCommand,
    submitComposerCommand,
    submitVisibleComposerCommand,
    syncActiveRunTimer,
    syncPendingTerminalConfirmPromptMode,
  };
}

export {
  _readRunErrorMessage,
  _seedLocalStorageStarsToServer,
  _setRunButtonDisabled,
  _sseMessageFromChunk,
  appendCommandEcho,
  attachActiveRunFromMonitor,
  cancelPendingTerminalConfirm,
  confirmKill,
  detachRunStreamForTab,
  doKill,
  hasPendingTerminalConfirm,
  hasRunnerHandler,
  interruptPromptLine,
  killActiveRunFromMonitor,
  pauseBackgroundRunStreamsForStatusMonitor,
  resumeBackgroundRunStreamsAfterStatusMonitor,
  runCommand,
  setRunnerHandlers,
  setStatus,
  startPollingActiveRunsAfterReload,
  startTimer,
  stopTimer,
  submitCommand,
  submitComposerCommand,
  submitVisibleComposerCommand,
  syncActiveRunTimer,
  syncPendingTerminalConfirmPromptMode,
};
