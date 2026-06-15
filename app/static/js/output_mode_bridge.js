// Neutral output-mode boundary for timestamp preference synchronization.

const OUTPUT_MODE_BRIDGE_GLOBAL = typeof window !== 'undefined' ? window : globalThis;
let warnedMissingOutputModeHandler = false;
let setTimestampModeHandler = null;

function setOutputModeHandlers(handlers = {}) {
  if (typeof handlers.setTimestampMode === 'function') {
    setTimestampModeHandler = handlers.setTimestampMode;
    _logOutputModeBridgeDiagnostic('debug', 'OUTPUT_MODE_HANDLER_REGISTERED', {
      registered_handlers: ['setTimestampMode'],
    });
  }
}

function setTimestampMode(...args) {
  if (typeof setTimestampModeHandler !== 'function') {
    if (!warnedMissingOutputModeHandler) {
      warnedMissingOutputModeHandler = true;
      _logOutputModeBridgeDiagnostic('warning', 'OUTPUT_MODE_HANDLER_MISSING', {
        handler: 'setTimestampMode',
        requested_mode: args[0],
      });
    }
    return false;
  }
  setTimestampModeHandler(...args);
  return true;
}

function _bridgeWarningsEnabled() {
  const config = (
    OUTPUT_MODE_BRIDGE_GLOBAL?.APP_CONFIG
    && typeof OUTPUT_MODE_BRIDGE_GLOBAL.APP_CONFIG === 'object'
    && !Array.isArray(OUTPUT_MODE_BRIDGE_GLOBAL.APP_CONFIG)
  ) ? OUTPUT_MODE_BRIDGE_GLOBAL.APP_CONFIG : {};
  return config.frontend_bridge_warnings === true
    || config.debug === true
    || config.dev_mode === true
    || config.environment === 'development'
    || config.env === 'development';
}

function _logOutputModeBridgeDiagnostic(level, event, details = {}) {
  if (!_bridgeWarningsEnabled()) return;
  const consoleApi = OUTPUT_MODE_BRIDGE_GLOBAL?.console || globalThis?.console;
  const log = consoleApi && ((level === 'debug' ? consoleApi.debug : consoleApi.warn) || consoleApi.log);
  if (typeof log !== 'function') return;
  log.call(consoleApi, `[darklab] ${event}`, {
    event,
    level,
    ...details,
  });
}

export {
  setOutputModeHandlers,
  setTimestampMode,
};
