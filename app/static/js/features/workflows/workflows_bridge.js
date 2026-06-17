// Neutral Workflows boundary for lazy placeholders and runtime consumers.

const WORKFLOW_BRIDGE_GLOBAL = typeof window !== 'undefined' ? window : globalThis;
const warnedMissingWorkflowHandlers = new Set();
const workflowHandlers = {
  renderWorkflowItems: null,
  reloadWorkflowCatalog: null,
  ensureWorkflowCatalogLoaded: null,
  handleWorkflowTerminalCommand: null,
  _runtimeWorkflowContext: null,
  openWorkflowEditor: null,
  closeWorkflowEditor: null,
};

function setWorkflowHandlers(handlers = {}) {
  const registered = [];
  Object.keys(workflowHandlers).forEach((name) => {
    if (typeof handlers[name] === 'function') {
      workflowHandlers[name] = handlers[name];
      registered.push(name);
    }
  });
  _logWorkflowBridgeDiagnostic('debug', 'WORKFLOW_BRIDGE_HANDLER_REGISTERED', {
    registered_handlers: registered,
  });
}

function hasWorkflowHandler(name) {
  return typeof workflowHandlers[name] === 'function';
}

function _workflowBridgeWarningsEnabled() {
  const config = (
    WORKFLOW_BRIDGE_GLOBAL?.APP_CONFIG
    && typeof WORKFLOW_BRIDGE_GLOBAL.APP_CONFIG === 'object'
    && !Array.isArray(WORKFLOW_BRIDGE_GLOBAL.APP_CONFIG)
  ) ? WORKFLOW_BRIDGE_GLOBAL.APP_CONFIG : {};
  return config.frontend_bridge_warnings === true
    || config.debug === true
    || config.dev_mode === true
    || config.environment === 'development'
    || config.env === 'development';
}

function _logWorkflowBridgeDiagnostic(level, event, details = {}) {
  if (!_workflowBridgeWarningsEnabled()) return;
  const consoleApi = WORKFLOW_BRIDGE_GLOBAL?.console || globalThis?.console;
  const log = consoleApi && ((level === 'debug' ? consoleApi.debug : consoleApi.warn) || consoleApi.log);
  if (typeof log !== 'function') return;
  log.call(consoleApi, `[darklab] ${event}`, {
    event,
    level,
    ...details,
  });
}

function _callWorkflowHandler(name, fallback, args) {
  if (typeof workflowHandlers[name] === 'function') return workflowHandlers[name](...args);
  if (!warnedMissingWorkflowHandlers.has(name)) {
    warnedMissingWorkflowHandlers.add(name);
    _logWorkflowBridgeDiagnostic('warning', 'WORKFLOW_BRIDGE_HANDLER_MISSING', {
      handler: name,
      command_root: name === 'handleWorkflowTerminalCommand' ? String(args[0] || '').split(/\s+/, 1)[0] : '',
      fallback: fallback === false ? 'false' : fallback === null ? 'null' : 'undefined',
    });
  }
  return fallback;
}

function renderWorkflowItems(...args) {
  return _callWorkflowHandler('renderWorkflowItems', undefined, args);
}

function reloadWorkflowCatalog(...args) {
  return _callWorkflowHandler('reloadWorkflowCatalog', undefined, args);
}

function ensureWorkflowCatalogLoaded(...args) {
  return _callWorkflowHandler('ensureWorkflowCatalogLoaded', undefined, args);
}

function handleWorkflowTerminalCommand(...args) {
  return _callWorkflowHandler('handleWorkflowTerminalCommand', false, args);
}

function _runtimeWorkflowContext(...args) {
  return _callWorkflowHandler('_runtimeWorkflowContext', null, args);
}

function openWorkflowEditor(...args) {
  return _callWorkflowHandler('openWorkflowEditor', false, args);
}

function closeWorkflowEditor(...args) {
  return _callWorkflowHandler('closeWorkflowEditor', false, args);
}

export {
  _runtimeWorkflowContext,
  closeWorkflowEditor,
  ensureWorkflowCatalogLoaded,
  handleWorkflowTerminalCommand,
  hasWorkflowHandler,
  openWorkflowEditor,
  reloadWorkflowCatalog,
  renderWorkflowItems,
  setWorkflowHandlers,
};
