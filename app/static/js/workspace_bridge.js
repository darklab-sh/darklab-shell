// Neutral workspace boundary for shell modules that need to close Files
// without importing the full workspace panel and its search dependencies.

const WORKSPACE_BRIDGE_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

const workspaceHandlers = {
  closeWorkspace: null,
};

function setWorkspaceHandlers(handlers = {}) {
  if (typeof handlers.closeWorkspace === 'function') {
    workspaceHandlers.closeWorkspace = handlers.closeWorkspace;
  }
}

function hasWorkspaceHandler(name) {
  return typeof workspaceHandlers[name] === 'function';
}

function closeWorkspace(...args) {
  if (typeof workspaceHandlers.closeWorkspace === 'function') {
    return workspaceHandlers.closeWorkspace(...args);
  }
  const fallback = WORKSPACE_BRIDGE_GLOBAL && WORKSPACE_BRIDGE_GLOBAL.closeWorkspace;
  return typeof fallback === 'function' ? fallback(...args) : undefined;
}

export {
  closeWorkspace,
  hasWorkspaceHandler,
  setWorkspaceHandlers,
};
