// Neutral workspace boundary for shell modules that need Files actions without
// importing the full Files panel into the initial shell graph.

const WORKSPACE_BRIDGE_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

const workspaceHandlers = {
  closeWorkspace: null,
  createWorkspaceDirectory: null,
  downloadWorkspaceFile: null,
  _formatWorkspaceBytes: null,
  hideWorkspaceEditor: null,
  hideWorkspaceViewer: null,
  loadWorkspaceFilesPayload: null,
  moveWorkspacePath: null,
  openWorkspace: null,
  openWorkspaceEditorFromCommand: null,
  readWorkspaceFile: null,
  refreshWorkspaceFiles: null,
  showWorkspaceViewer: null,
  workspaceCanWrite: null,
};
let workspaceLoadPromise = null;

function setWorkspaceHandlers(handlers = {}) {
  Object.keys(workspaceHandlers).forEach((name) => {
    if (typeof handlers[name] === 'function') workspaceHandlers[name] = handlers[name];
  });
}

function hasWorkspaceHandler(name) {
  return typeof workspaceHandlers[name] === 'function';
}

function _workspaceBridgeFallback(name) {
  const fn = WORKSPACE_BRIDGE_GLOBAL && WORKSPACE_BRIDGE_GLOBAL[name];
  return typeof fn === 'function' && fn !== workspaceBridgeApi[name] ? fn : null;
}

function _workspaceHandler(name) {
  if (typeof workspaceHandlers[name] === 'function') return workspaceHandlers[name];
  return _workspaceBridgeFallback(name);
}

function _workspaceAssetEntry() {
  if (typeof document !== 'undefined') {
    const node = document.getElementById('lazy-assets-json');
    if (node && node.textContent) {
      try {
        const parsed = JSON.parse(node.textContent);
        const entry = parsed && parsed.workspace;
        if (typeof entry === 'string' && entry) return { url: entry };
        if (entry && typeof entry.url === 'string' && entry.url) return { url: entry.url };
      } catch (_) {
        // The lazy asset loader logs malformed config. Fall back quietly here.
      }
    }
  }
  return { url: '/static/js/workspace.js' };
}

async function _importWorkspaceModule(url) {
  const importer = WORKSPACE_BRIDGE_GLOBAL && typeof WORKSPACE_BRIDGE_GLOBAL.__darklabImportModule === 'function'
    ? WORKSPACE_BRIDGE_GLOBAL.__darklabImportModule
    : (assetUrl) => import(assetUrl);
  return importer(url);
}

async function _loadWorkspaceSurface(requiredHandler = '') {
  if (
    requiredHandler
    && typeof workspaceHandlers[requiredHandler] === 'function'
  ) {
    return workspaceHandlers;
  }
  if (!requiredHandler && Object.values(workspaceHandlers).some(handler => typeof handler === 'function')) {
    return workspaceHandlers;
  }
  if (!workspaceLoadPromise) {
    const loader = WORKSPACE_BRIDGE_GLOBAL && WORKSPACE_BRIDGE_GLOBAL.loadWorkspaceSurface;
    workspaceLoadPromise = Promise.resolve()
      .then(() => (typeof loader === 'function'
        ? loader()
        : _importWorkspaceModule(_workspaceAssetEntry().url)))
      .then((moduleApi) => {
        if (moduleApi && typeof moduleApi === 'object') setWorkspaceHandlers(moduleApi);
        return moduleApi;
      })
      .finally(() => {
        workspaceLoadPromise = null;
      });
  }
  return workspaceLoadPromise;
}

async function _callLoadedWorkspace(name, args) {
  let fn = _workspaceHandler(name);
  if (typeof fn !== 'function') {
    await _loadWorkspaceSurface(name);
    fn = _workspaceHandler(name);
  }
  return typeof fn === 'function' ? fn(...args) : undefined;
}

function _callWorkspace(name, args) {
  const fn = _workspaceHandler(name);
  return typeof fn === 'function' ? fn(...args) : undefined;
}

function closeWorkspace(...args) {
  return _callWorkspace('closeWorkspace', args);
}

async function createWorkspaceDirectory(...args) {
  return _callLoadedWorkspace('createWorkspaceDirectory', args);
}

async function downloadWorkspaceFile(...args) {
  return _callLoadedWorkspace('downloadWorkspaceFile', args);
}

function _formatWorkspaceBytes(bytes) {
  const formatted = _callWorkspace('_formatWorkspaceBytes', [bytes]);
  if (formatted !== undefined) return formatted;
  const value = Number(bytes) || 0;
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(value >= 10 * 1024 ? 0 : 1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(value >= 10 * 1024 * 1024 ? 0 : 1)} MB`;
}

function hideWorkspaceEditor(...args) {
  return _callWorkspace('hideWorkspaceEditor', args);
}

function hideWorkspaceViewer(...args) {
  return _callWorkspace('hideWorkspaceViewer', args);
}

async function loadWorkspaceFilesPayload(...args) {
  return _callLoadedWorkspace('loadWorkspaceFilesPayload', args);
}

async function moveWorkspacePath(...args) {
  return _callLoadedWorkspace('moveWorkspacePath', args);
}

async function openWorkspace(...args) {
  return _callLoadedWorkspace('openWorkspace', args);
}

async function openWorkspaceEditorFromCommand(...args) {
  return _callLoadedWorkspace('openWorkspaceEditorFromCommand', args);
}

async function readWorkspaceFile(...args) {
  return _callLoadedWorkspace('readWorkspaceFile', args);
}

async function refreshWorkspaceFiles(...args) {
  return _callLoadedWorkspace('refreshWorkspaceFiles', args);
}

async function showWorkspaceViewer(...args) {
  return _callLoadedWorkspace('showWorkspaceViewer', args);
}

function workspaceCanWrite(...args) {
  const result = _callWorkspace('workspaceCanWrite', args);
  return result === undefined ? true : !!result;
}

const workspaceBridgeApi = {
  closeWorkspace,
  createWorkspaceDirectory,
  downloadWorkspaceFile,
  _formatWorkspaceBytes,
  hasWorkspaceHandler,
  hideWorkspaceEditor,
  hideWorkspaceViewer,
  loadWorkspaceFilesPayload,
  moveWorkspacePath,
  openWorkspace,
  openWorkspaceEditorFromCommand,
  readWorkspaceFile,
  refreshWorkspaceFiles,
  setWorkspaceHandlers,
  showWorkspaceViewer,
  workspaceCanWrite,
};

export {
  closeWorkspace,
  createWorkspaceDirectory,
  downloadWorkspaceFile,
  _formatWorkspaceBytes,
  hasWorkspaceHandler,
  hideWorkspaceEditor,
  hideWorkspaceViewer,
  loadWorkspaceFilesPayload,
  moveWorkspacePath,
  openWorkspace,
  openWorkspaceEditorFromCommand,
  readWorkspaceFile,
  refreshWorkspaceFiles,
  setWorkspaceHandlers,
  showWorkspaceViewer,
  workspaceCanWrite,
};
