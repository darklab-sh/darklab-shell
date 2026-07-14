// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Neutral project-context boundary for shell-owned project actions.
// Lazy feature modules import these wrappers without importing shell_chrome.js.

const PROJECT_CONTEXT_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

const projectContextHandlers = PROJECT_CONTEXT_GLOBAL.__darklabProjectContextHandlers || {
  closeProjectWorkspace: null,
  cycleProjectWorkspaceTab: null,
  getActiveProjectContext: null,
  isProjectWorkspaceOpen: null,
  notifyProjectWorkspaceChanged: null,
  openEntityMetadataEditor: null,
  openProjectAutoPromoteRuleFromAtlas: null,
  openProjectWorkspace: null,
  refreshActiveProjectContext: null,
  refreshProjectWorkspace: null,
};

PROJECT_CONTEXT_GLOBAL.__darklabProjectContextHandlers = projectContextHandlers;

function setProjectContextHandlers(handlers = {}) {
  Object.keys(projectContextHandlers).forEach((name) => {
    if (typeof handlers[name] === 'function') {
      projectContextHandlers[name] = handlers[name];
    }
  });
}

function getActiveProjectContext(...args) {
  return typeof projectContextHandlers.getActiveProjectContext === 'function'
    ? projectContextHandlers.getActiveProjectContext(...args)
    : null;
}

function refreshActiveProjectContext(...args) {
  return typeof projectContextHandlers.refreshActiveProjectContext === 'function'
    ? projectContextHandlers.refreshActiveProjectContext(...args)
    : Promise.resolve(null);
}

function openProjectWorkspace(...args) {
  return typeof projectContextHandlers.openProjectWorkspace === 'function'
    ? projectContextHandlers.openProjectWorkspace(...args)
    : Promise.resolve(false);
}

function closeProjectWorkspace(...args) {
  return typeof projectContextHandlers.closeProjectWorkspace === 'function'
    ? projectContextHandlers.closeProjectWorkspace(...args)
    : undefined;
}

function cycleProjectWorkspaceTab(...args) {
  return typeof projectContextHandlers.cycleProjectWorkspaceTab === 'function'
    ? projectContextHandlers.cycleProjectWorkspaceTab(...args)
    : false;
}

function refreshProjectWorkspace(...args) {
  return typeof projectContextHandlers.refreshProjectWorkspace === 'function'
    ? projectContextHandlers.refreshProjectWorkspace(...args)
    : Promise.resolve(false);
}

function isProjectWorkspaceOpen(...args) {
  return typeof projectContextHandlers.isProjectWorkspaceOpen === 'function'
    ? !!projectContextHandlers.isProjectWorkspaceOpen(...args)
    : false;
}

function notifyProjectWorkspaceChanged(...args) {
  return typeof projectContextHandlers.notifyProjectWorkspaceChanged === 'function'
    ? projectContextHandlers.notifyProjectWorkspaceChanged(...args)
    : undefined;
}

function openProjectAutoPromoteRuleFromAtlas(...args) {
  return typeof projectContextHandlers.openProjectAutoPromoteRuleFromAtlas === 'function'
    ? projectContextHandlers.openProjectAutoPromoteRuleFromAtlas(...args)
    : Promise.resolve(false);
}

function openEntityMetadataEditor(...args) {
  return typeof projectContextHandlers.openEntityMetadataEditor === 'function'
    ? projectContextHandlers.openEntityMetadataEditor(...args)
    : undefined;
}

export {
  closeProjectWorkspace,
  cycleProjectWorkspaceTab,
  getActiveProjectContext,
  isProjectWorkspaceOpen,
  notifyProjectWorkspaceChanged,
  openEntityMetadataEditor,
  openProjectAutoPromoteRuleFromAtlas,
  openProjectWorkspace,
  refreshActiveProjectContext,
  refreshProjectWorkspace,
  setProjectContextHandlers,
};
