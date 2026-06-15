// Neutral controller-action boundary for feature modules that should not
// import the full controller module.

const CONTROLLER_ACTION_BRIDGE_GLOBAL = typeof window !== 'undefined' ? window : globalThis;
const warnedMissingControllerActionHandlers = new Set();
const controllerActionHandlers = {
  closeFaq: null,
  closeWorkflows: null,
  openFaq: null,
  openWorkflows: null,
  toggleHistoryPanelSurface: null,
  toggleRailCollapsed: null,
};

function setControllerActionHandlers(handlers = {}) {
  const registered = [];
  Object.keys(controllerActionHandlers).forEach((name) => {
    if (typeof handlers[name] === 'function') {
      controllerActionHandlers[name] = handlers[name];
      registered.push(name);
    }
  });
  _logControllerActionBridgeDiagnostic('debug', 'CONTROLLER_ACTION_HANDLER_REGISTERED', {
    registered_handlers: registered,
  });
}

function _bridgeWarningsEnabled() {
  const config = (
    CONTROLLER_ACTION_BRIDGE_GLOBAL?.APP_CONFIG
    && typeof CONTROLLER_ACTION_BRIDGE_GLOBAL.APP_CONFIG === 'object'
    && !Array.isArray(CONTROLLER_ACTION_BRIDGE_GLOBAL.APP_CONFIG)
  ) ? CONTROLLER_ACTION_BRIDGE_GLOBAL.APP_CONFIG : {};
  return config.frontend_bridge_warnings === true
    || config.debug === true
    || config.dev_mode === true
    || config.environment === 'development'
    || config.env === 'development';
}

function _logControllerActionBridgeDiagnostic(level, event, details = {}) {
  if (!_bridgeWarningsEnabled()) return;
  const consoleApi = CONTROLLER_ACTION_BRIDGE_GLOBAL?.console || globalThis?.console;
  const log = consoleApi && ((level === 'debug' ? consoleApi.debug : consoleApi.warn) || consoleApi.log);
  if (typeof log !== 'function') return;
  log.call(consoleApi, `[darklab] ${event}`, {
    event,
    level,
    ...details,
  });
}

function _callControllerActionHandler(name, args) {
  if (typeof controllerActionHandlers[name] === 'function') {
    return controllerActionHandlers[name](...args);
  }
  if (!warnedMissingControllerActionHandlers.has(name)) {
    warnedMissingControllerActionHandlers.add(name);
    _logControllerActionBridgeDiagnostic('warning', 'CONTROLLER_ACTION_HANDLER_MISSING', {
      handler: name,
      surface: name.includes('Workflows') ? 'workflows' : name.includes('Faq') ? 'faq' : 'shell',
    });
  }
  return undefined;
}

function openFaq(...args) {
  return _callControllerActionHandler('openFaq', args);
}

function closeFaq(...args) {
  return _callControllerActionHandler('closeFaq', args);
}

function openWorkflows(...args) {
  return _callControllerActionHandler('openWorkflows', args);
}

function closeWorkflows(...args) {
  return _callControllerActionHandler('closeWorkflows', args);
}

function toggleHistoryPanelSurface(...args) {
  return _callControllerActionHandler('toggleHistoryPanelSurface', args);
}

function toggleRailCollapsed(...args) {
  return _callControllerActionHandler('toggleRailCollapsed', args);
}

export {
  closeFaq,
  closeWorkflows,
  openFaq,
  openWorkflows,
  setControllerActionHandlers,
  toggleHistoryPanelSurface,
  toggleRailCollapsed,
};
