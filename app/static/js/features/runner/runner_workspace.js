// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Workspace-terminal command parsing and path helpers used by runner.js.

import { getAppConfig as importedGetAppConfig } from '../../core/config.js';
import {
  getActiveTabId as importedGetActiveTabId,
  getTab as importedGetTab,
} from '../../core/state.js';
import {
  displayPath as importedWorkspaceDisplayPath,
  normalizeCommandPath as importedNormalizeWorkspaceCommandPath,
} from '../../core/workspace_core.js';
import { schedulePersistTabSessionState as importedSchedulePersistTabSessionState } from '../tabs/tab_session_state.js';
import {
  getWorkspaceAutocompleteDirectoryHints as importedGetWorkspaceAutocompleteDirectoryHints,
  getWorkspaceAutocompleteFileHints as importedGetWorkspaceAutocompleteFileHints,
  refreshWorkspaceFileCache as importedRefreshWorkspaceFileCache,
} from '../workspace/workspace_autocomplete_cache.js';
import { loadWorkspaceFilesPayload as importedLoadWorkspaceFilesPayload } from '../../workspace_bridge.js';
import {
  hasComposerPromptHandler as importedHasComposerPromptHandler,
  syncShellPrompt as importedSyncShellPrompt,
} from '../terminal/composer_prompt_bridge.js';

const RUNNER_WORKSPACE_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

function _runnerWorkspaceConfig() {
  if (typeof importedGetAppConfig !== 'undefined' && typeof importedGetAppConfig === 'function') {
    return importedGetAppConfig() || {};
  }
  return RUNNER_WORKSPACE_GLOBAL.APP_CONFIG || {};
}

function _runnerWorkspaceEnabled() {
  return _runnerWorkspaceConfig().workspace_enabled === true;
}

function _runnerWorkspaceActiveTabId() {
  if (typeof importedGetActiveTabId !== 'undefined' && typeof importedGetActiveTabId === 'function') {
    return importedGetActiveTabId();
  }
  return typeof RUNNER_WORKSPACE_GLOBAL.APP_STATE_API?.getActiveTabId === 'function'
    ? RUNNER_WORKSPACE_GLOBAL.APP_STATE_API.getActiveTabId()
    : null;
}

function _runnerWorkspaceGetTab(tabId) {
  if (typeof importedGetTab !== 'undefined' && typeof importedGetTab === 'function') return importedGetTab(tabId);
  return typeof RUNNER_WORKSPACE_GLOBAL.APP_STATE_API?.getTab === 'function'
    ? RUNNER_WORKSPACE_GLOBAL.APP_STATE_API.getTab(tabId)
    : null;
}

function _runnerWorkspaceDisplayPath(path = '') {
  const display = (typeof importedWorkspaceDisplayPath !== 'undefined' && importedWorkspaceDisplayPath)
    || RUNNER_WORKSPACE_GLOBAL.workspaceDisplayPath;
  if (display === _workspaceDisplayPath) return null;
  return typeof display === 'function' ? display(_normalizeWorkspaceTerminalPath(path)) : null;
}

function _runnerWorkspaceNormalizeCommandPath(path = '', cwd = '') {
  const normalize = (
    typeof importedNormalizeWorkspaceCommandPath !== 'undefined'
    && importedNormalizeWorkspaceCommandPath
  ) || RUNNER_WORKSPACE_GLOBAL.normalizeWorkspaceCommandPath;
  return typeof normalize === 'function' ? normalize(path, cwd) : null;
}

function _runnerWorkspaceSchedulePersistTabSessionState() {
  const schedulePersist = (
    typeof importedSchedulePersistTabSessionState !== 'undefined'
    && importedSchedulePersistTabSessionState
  ) || RUNNER_WORKSPACE_GLOBAL.schedulePersistTabSessionState;
  if (typeof schedulePersist === 'function') schedulePersist();
}

function _workspaceCacheApi() {
  return {
    getDirectoryHints: (typeof importedGetWorkspaceAutocompleteDirectoryHints !== 'undefined' && importedGetWorkspaceAutocompleteDirectoryHints)
      || RUNNER_WORKSPACE_GLOBAL.getWorkspaceAutocompleteDirectoryHints,
    getFileHints: (typeof importedGetWorkspaceAutocompleteFileHints !== 'undefined' && importedGetWorkspaceAutocompleteFileHints)
      || RUNNER_WORKSPACE_GLOBAL.getWorkspaceAutocompleteFileHints,
    refresh: (typeof importedRefreshWorkspaceFileCache !== 'undefined' && importedRefreshWorkspaceFileCache)
      || RUNNER_WORKSPACE_GLOBAL.refreshWorkspaceFileCache,
  };
}

function _workspaceDeleteCommand(cmd) {
  const parts = _workspaceCommandTokens(cmd);
  const root = (parts[0] || '').toLowerCase();
  const fileAction = (parts[1] || 'delete').toLowerCase();
  const usage = root === 'file'
    ? `Usage: file ${fileAction} [-r|-f|-rf] <file-or-folder>`
    : 'Usage: rm [-r|-f|-rf] <file-or-folder>';
  const start = root === 'file' ? 2 : 1;
  if (root === 'file' && !['rm', 'delete'].includes((parts[1] || '').toLowerCase())) return null;
  if (root !== 'rm' && root !== 'file') return null;
  const args = parts.slice(start);
  const flags = [];
  const targets = [];
  args.forEach((part) => {
    if (/^-[rf]+$/.test(part)) flags.push(part);
    else if (String(part || '').startsWith('-')) targets.push(part);
    else targets.push(part);
  });
  const recursive = flags.some(flag => flag.includes('r'));
  const force = flags.some(flag => flag.includes('f'));
  const invalid = targets.length !== 1 || args.some(part => String(part || '').startsWith('-') && !/^-[rf]+$/.test(part));
  return {
    target: invalid ? '' : targets[0],
    recursive,
    force,
    usage,
    invalid,
  };
}

function _workspaceDeleteTarget(cmd) {
  const parsed = _workspaceDeleteCommand(cmd);
  return parsed && !parsed.invalid ? parsed.target : '';
}

function _workspaceMoveCommand(cmd) {
  const parts = _workspaceCommandTokens(cmd);
  const root = (parts[0] || '').toLowerCase();
  if (root === 'mv') {
    return {
      source: parts.length === 3 ? parts[1] : '',
      destination: parts.length === 3 ? parts[2] : '',
      usage: 'Usage: mv <source> <destination>',
      invalid: parts.length !== 3,
    };
  }
  const action = (parts[1] || '').toLowerCase();
  if (root !== 'file' || action !== 'move') return null;
  return {
    source: parts.length === 4 ? parts[2] : '',
    destination: parts.length === 4 ? parts[3] : '',
    usage: 'Usage: file move <source> <destination>',
    invalid: parts.length !== 4,
  };
}

function _workspaceCopyCommand(cmd) {
  const parts = _workspaceCommandTokens(cmd);
  const root = (parts[0] || '').toLowerCase();
  if (root === 'cp') {
    return {
      source: parts.length === 3 ? parts[1] : '',
      destination: parts.length === 3 ? parts[2] : '',
      usage: 'Usage: cp <source> <destination>',
      invalid: parts.length !== 3,
    };
  }
  const action = (parts[1] || '').toLowerCase();
  if (root !== 'file' || action !== 'copy') return null;
  return {
    source: parts.length === 4 ? parts[2] : '',
    destination: parts.length === 4 ? parts[3] : '',
    usage: 'Usage: file copy <source> <destination>',
    invalid: parts.length !== 4,
  };
}

function _workspaceTouchCommand(cmd) {
  const parts = _workspaceCommandTokens(cmd);
  const root = (parts[0] || '').toLowerCase();
  if (root === 'touch') {
    return {
      target: parts.length === 2 ? parts[1] : '',
      usage: 'Usage: touch <file>',
      invalid: parts.length !== 2,
    };
  }
  const action = (parts[1] || '').toLowerCase();
  if (root !== 'file' || action !== 'touch') return null;
  return {
    target: parts.length === 3 ? parts[2] : '',
    usage: 'Usage: file touch <file>',
    invalid: parts.length !== 3,
  };
}

function _workspaceListCommand(parts) {
  const root = (parts[0] || '').toLowerCase();
  const parseListArgs = (args, usage) => {
    let long = false;
    let recursive = false;
    const targets = [];
    let invalid = false;
    args.forEach((part) => {
      const value = String(part || '');
      if (/^-[lR]+$/.test(value)) {
        if (value.includes('l')) long = true;
        if (value.includes('R')) recursive = true;
      } else if (value.startsWith('-')) {
        invalid = true;
      } else {
        targets.push(part);
      }
    });
    if (targets.length > 1) invalid = true;
    return {
      target: targets[0] || '',
      long,
      recursive,
      usage,
      invalid,
    };
  };
  if (root === 'll') {
    const parsed = parseListArgs(parts.slice(1), 'Usage: ll [-R] [folder]');
    parsed.long = true;
    return parsed;
  }
  const usage = root === 'file' ? 'Usage: file list [-lR] [folder]' : 'Usage: ls [-lR] [folder]';
  const start = root === 'file' ? 2 : 1;
  if (root === 'file' && !['list', 'ls'].includes((parts[1] || '').toLowerCase())) return null;
  return parseListArgs(parts.slice(start), usage);
}

function _workspaceListTarget(parts) {
  const parsed = _workspaceListCommand(parts);
  if (parsed && !parsed.invalid) {
    return parsed.target;
  }
  return '';
}

function _workspaceEditorCommand(cmd) {
  const parts = _workspaceCommandTokens(cmd);
  const root = (parts[0] || '').toLowerCase();
  const action = (parts[1] || '').toLowerCase();
  if (root !== 'file' || !['add', 'edit'].includes(action)) return null;
  return { action, target: parts.length === 3 ? parts[2] : '', invalid: parts.length > 3 };
}

function _workspaceDownloadTarget(cmd) {
  const parts = _workspaceCommandTokens(cmd);
  const root = (parts[0] || '').toLowerCase();
  const action = (parts[1] || '').toLowerCase();
  if (root === 'file' && action === 'download' && parts.length === 3) return parts[2];
  return '';
}

function _workspaceDiffCommand(cmd) {
  const parts = _workspaceCommandTokens(cmd);
  const root = (parts[0] || '').toLowerCase();
  const isFileCommand = root === 'file';
  if (isFileCommand && (parts[1] || '').toLowerCase() !== 'diff') return null;
  if (!isFileCommand && root !== 'diff') return null;
  const usage = isFileCommand
    ? 'Usage: file diff [-q|--brief|-u|--unified|-y|--side-by-side] [--last | <source1> <source2>]'
    : 'Usage: diff [-q|--brief|-u|--unified|-y|--side-by-side] [--last | <source1> <source2>]';
  const modes = {
    '-q': 'brief',
    '--brief': 'brief',
    '-u': 'unified',
    '--unified': 'unified',
    '-y': 'side_by_side',
    '--side-by-side': 'side_by_side',
  };
  let mode = 'normal';
  let modeSelected = false;
  let parseOptions = true;
  let invalid = false;
  let last = false;
  const operands = [];
  parts.slice(isFileCommand ? 2 : 1).forEach((part) => {
    if (parseOptions && part === '--') {
      parseOptions = false;
      return;
    }
    if (parseOptions && String(part || '').startsWith('-')) {
      if (part === '--last') {
        if (last) invalid = true;
        last = true;
        return;
      }
      const selected = modes[part];
      if (!selected || (modeSelected && selected !== mode)) {
        invalid = true;
        return;
      }
      mode = selected;
      modeSelected = true;
      return;
    }
    operands.push(part);
  });
  if ((last && operands.length) || (!last && operands.length !== 2)) invalid = true;
  return {
    mode,
    last,
    left: invalid ? '' : operands[0],
    right: invalid ? '' : operands[1],
    usage,
    invalid,
  };
}

function _workspaceCommandTokens(cmd) {
  const tokens = [];
  const re = /"[^"]*"|'[^']*'|\S+/g;
  let match = re.exec(String(cmd || '').trim());
  while (match) {
    let token = match[0];
    if (token.length >= 2 && ((token[0] === '"' && token[token.length - 1] === '"') || (token[0] === "'" && token[token.length - 1] === "'"))) {
      token = token.slice(1, -1);
    }
    tokens.push(token);
    match = re.exec(String(cmd || '').trim());
  }
  return tokens;
}

function _workspaceCwd(tabId = _runnerWorkspaceActiveTabId()) {
  const tab = _runnerWorkspaceGetTab(tabId);
  return _normalizeWorkspaceTerminalPath(tab && tab.workspaceCwd || '');
}

function _setWorkspaceCwd(tabId, path = '') {
  const tab = _runnerWorkspaceGetTab(tabId);
  const normalized = _normalizeWorkspaceTerminalPath(path);
  if (tab) tab.workspaceCwd = normalized;
  const syncPrompt = (
    typeof importedHasComposerPromptHandler === 'function'
    && importedHasComposerPromptHandler('syncShellPrompt')
  ) ? importedSyncShellPrompt : RUNNER_WORKSPACE_GLOBAL.syncShellPrompt;
  if (typeof syncPrompt === 'function') syncPrompt();
  _runnerWorkspaceSchedulePersistTabSessionState();
  return normalized;
}

function _workspaceDisplayPath(path = '') {
  const displayed = _runnerWorkspaceDisplayPath(path);
  if (displayed !== null) return displayed;
  const normalized = _normalizeWorkspaceTerminalPath(path);
  return normalized ? `/${normalized}` : '/';
}

function _normalizeWorkspaceTerminalPath(path = '') {
  const parts = String(path || '').split('/').map(part => String(part || '').trim()).filter(Boolean);
  return parts.join('/');
}

function _resolveWorkspaceCommandPath(rawPath = '', { cwd = _workspaceCwd(), defaultToCwd = false } = {}) {
  const text = String(rawPath ?? '').trim();
  const normalizedCwd = _normalizeWorkspaceTerminalPath(cwd);
  if (!text && defaultToCwd) return normalizedCwd;
  const normalizedCommandPath = _runnerWorkspaceNormalizeCommandPath(text || '.', normalizedCwd);
  if (normalizedCommandPath !== null) {
    return _normalizeWorkspaceTerminalPath(normalizedCommandPath);
  }
  const base = text.startsWith('/') ? [] : normalizedCwd.split('/').filter(Boolean);
  const parts = String(text || '.').split('/').filter(Boolean);
  for (const part of parts) {
    if (part === '.') continue;
    if (part === '..') {
      if (!base.length) throw new Error('path escapes the session workspace');
      base.pop();
    } else {
      base.push(part);
    }
  }
  return base.join('/');
}

function _workspacePathExists(path = '', kind = 'any') {
  const target = String(path || '').split('/').filter(Boolean).join('/');
  if (!target) return kind === 'directory' || kind === 'any';
  if (kind === 'directory' || kind === 'any') {
    const getDirectoryHints = _workspaceCacheApi().getDirectoryHints;
    const dirHints = typeof getDirectoryHints === 'function'
      ? getDirectoryHints()
      : [];
    if (dirHints.some(item => String(item && item.value || '') === target)) return true;
  }
  if (kind === 'file' || kind === 'any') {
    const getFileHints = _workspaceCacheApi().getFileHints;
    const fileHints = typeof getFileHints === 'function'
      ? getFileHints()
      : [];
    if (fileHints.some(item => String(item && item.value || '') === target)) return true;
  }
  return false;
}

function _workspacePathHasGlob(path = '') {
  return String(path || '').includes('*');
}

function _workspaceGlobSegmentToRegExp(segment = '') {
  const escaped = String(segment || '').replace(/[.+?^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '[^/]*');
  return new RegExp(`^${escaped}$`);
}

function _workspaceGlobMatches(pattern = '', path = '') {
  const patternParts = String(pattern || '').split('/').filter(Boolean);
  const pathParts = String(path || '').split('/').filter(Boolean);
  if (patternParts.length !== pathParts.length) return false;
  return patternParts.every((part, index) => _workspaceGlobSegmentToRegExp(part).test(pathParts[index]));
}

function _workspaceEntryHints(kind = 'any') {
  const entries = [];
  if (kind === 'directory' || kind === 'any') {
    const getDirectoryHints = _workspaceCacheApi().getDirectoryHints;
    const dirHints = typeof getDirectoryHints === 'function'
      ? getDirectoryHints()
      : [];
    (Array.isArray(dirHints) ? dirHints : []).forEach((item) => {
      const path = String(item && item.value || '').split('/').filter(Boolean).join('/');
      if (path) entries.push({ path, kind: 'directory' });
    });
  }
  if (kind === 'file' || kind === 'any') {
    const getFileHints = _workspaceCacheApi().getFileHints;
    const fileHints = typeof getFileHints === 'function'
      ? getFileHints()
      : [];
    (Array.isArray(fileHints) ? fileHints : []).forEach((item) => {
      const path = String(item && item.value || '').split('/').filter(Boolean).join('/');
      if (path) entries.push({ path, kind: 'file', item });
    });
  }
  return entries.sort((a, b) => a.path.localeCompare(b.path));
}

function _workspaceExpandPathPattern(rawPath = '', { cwd = _workspaceCwd(), kind = 'any', defaultToCwd = false } = {}) {
  const target = _resolveWorkspaceCommandPath(rawPath, { cwd, defaultToCwd });
  if (!_workspacePathHasGlob(target)) {
    if (!_workspacePathExists(target, kind)) {
      return [];
    }
    const entry = _workspaceEntryHints(kind).find(item => item.path === target);
    return [entry || { path: target, kind: target && _workspacePathExists(target, 'file') ? 'file' : 'directory' }];
  }
  return _workspaceEntryHints(kind).filter(item => _workspaceGlobMatches(target, item.path));
}

function _resolveExistingWorkspaceCommandPath(rawPath = '', { cwd = _workspaceCwd(), kind = 'any', defaultToCwd = false } = {}) {
  const text = String(rawPath ?? '').trim();
  const target = _resolveWorkspaceCommandPath(text, { cwd, defaultToCwd });
  if (_workspacePathExists(target, kind)) return target;
  const normalizedRaw = String(text || '').split('/').filter(Boolean).join('/');
  if (text && !text.startsWith('/') && normalizedRaw && normalizedRaw !== target && _workspacePathExists(normalizedRaw, kind)) {
    return normalizedRaw;
  }
  return target;
}

async function _ensureWorkspaceCache() {
  const state = RUNNER_WORKSPACE_GLOBAL.DarklabWorkspaceState;
  const loadFilesPayload = (
    typeof importedLoadWorkspaceFilesPayload !== 'undefined'
    && importedLoadWorkspaceFilesPayload
  ) || RUNNER_WORKSPACE_GLOBAL.loadWorkspaceFilesPayload;
  if ((!state || state.loaded !== true) && typeof loadFilesPayload === 'function') {
    await loadFilesPayload();
    return;
  }
  const refresh = _workspaceCacheApi().refresh;
  if (typeof refresh === 'function') {
    await refresh();
  }
}

function _isWorkspaceDeleteCommand(cmd) {
  if (!_runnerWorkspaceEnabled()) {
    return false;
  }
  const parts = _workspaceCommandTokens(cmd);
  const root = (parts[0] || '').toLowerCase();
  const action = (parts[1] || '').toLowerCase();
  return root === 'rm' || (root === 'file' && ['rm', 'delete'].includes(action));
}

function _isWorkspaceEditorCommand(cmd) {
  if (!_runnerWorkspaceEnabled()) {
    return false;
  }
  const parts = _workspaceCommandTokens(cmd);
  const root = (parts[0] || '').toLowerCase();
  const action = (parts[1] || '').toLowerCase();
  return root === 'file' && ['add', 'edit'].includes(action);
}

function _isWorkspaceDownloadCommand(cmd) {
  if (!_runnerWorkspaceEnabled()) {
    return false;
  }
  const parts = String(cmd || '').trim().split(/\s+/).filter(Boolean);
  return (parts[0] || '').toLowerCase() === 'file' && (parts[1] || '').toLowerCase() === 'download';
}

function _isWorkspaceMoveCommand(cmd) {
  if (!_runnerWorkspaceEnabled()) {
    return false;
  }
  return !!_workspaceMoveCommand(cmd);
}

function _isWorkspaceCopyCommand(cmd) {
  if (!_runnerWorkspaceEnabled()) return false;
  return !!_workspaceCopyCommand(cmd);
}

function _isWorkspaceTerminalCommand(cmd) {
  const parts = _workspaceCommandTokens(cmd);
  const root = (parts[0] || '').toLowerCase();
  if (root === 'diff') return true;
  if (!_runnerWorkspaceEnabled()) return false;
  if (['cd', 'pwd', 'ls', 'll', 'cat', 'mkdir', 'touch', 'grep', 'head', 'tail', 'wc', 'sort', 'uniq'].includes(root)) return true;
  if (root === 'file' && ['list', 'ls', 'show', 'diff', 'touch', 'add-dir', 'mkdir'].includes((parts[1] || '').toLowerCase())) return true;
  return false;
}

if (typeof window !== 'undefined') {
}

export {
  _ensureWorkspaceCache,
  _isWorkspaceDeleteCommand,
  _isWorkspaceCopyCommand,
  _isWorkspaceDownloadCommand,
  _isWorkspaceEditorCommand,
  _isWorkspaceMoveCommand,
  _isWorkspaceTerminalCommand,
  _normalizeWorkspaceTerminalPath,
  _resolveExistingWorkspaceCommandPath,
  _resolveWorkspaceCommandPath,
  _setWorkspaceCwd,
  _workspaceCommandTokens,
  _workspaceCopyCommand,
  _workspaceCwd,
  _workspaceDeleteCommand,
  _workspaceDeleteTarget,
  _workspaceDiffCommand,
  _workspaceDisplayPath,
  _workspaceDownloadTarget,
  _workspaceEditorCommand,
  _workspaceEntryHints,
  _workspaceExpandPathPattern,
  _workspaceGlobMatches,
  _workspaceGlobSegmentToRegExp,
  _workspaceListCommand,
  _workspaceListTarget,
  _workspaceMoveCommand,
  _workspaceTouchCommand,
  _workspacePathExists,
  _workspacePathHasGlob,
};
