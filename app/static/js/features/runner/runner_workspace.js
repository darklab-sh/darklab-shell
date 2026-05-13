// Workspace-terminal command parsing and path helpers used by runner.js.

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

function _workspaceCwd(tabId = activeTabId) {
  const tab = typeof getTab === 'function' ? getTab(tabId) : null;
  return _normalizeWorkspaceTerminalPath(tab && tab.workspaceCwd || '');
}

function _setWorkspaceCwd(tabId, path = '') {
  const tab = typeof getTab === 'function' ? getTab(tabId) : null;
  const normalized = _normalizeWorkspaceTerminalPath(path);
  if (tab) tab.workspaceCwd = normalized;
  if (typeof _applyComposerPromptMode === 'function') _applyComposerPromptMode();
  if (typeof schedulePersistTabSessionState === 'function') schedulePersistTabSessionState();
  return normalized;
}

function _workspaceDisplayPath(path = '') {
  if (typeof workspaceDisplayPath === 'function') return workspaceDisplayPath(_normalizeWorkspaceTerminalPath(path));
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
  if (typeof normalizeWorkspaceCommandPath === 'function') {
    return _normalizeWorkspaceTerminalPath(normalizeWorkspaceCommandPath(text || '.', normalizedCwd));
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
    const dirHints = typeof getWorkspaceAutocompleteDirectoryHints === 'function'
      ? getWorkspaceAutocompleteDirectoryHints()
      : [];
    if (dirHints.some(item => String(item && item.value || '') === target)) return true;
  }
  if (kind === 'file' || kind === 'any') {
    const fileHints = typeof getWorkspaceAutocompleteFileHints === 'function'
      ? getWorkspaceAutocompleteFileHints()
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
    const dirHints = typeof getWorkspaceAutocompleteDirectoryHints === 'function'
      ? getWorkspaceAutocompleteDirectoryHints()
      : [];
    (Array.isArray(dirHints) ? dirHints : []).forEach((item) => {
      const path = String(item && item.value || '').split('/').filter(Boolean).join('/');
      if (path) entries.push({ path, kind: 'directory' });
    });
  }
  if (kind === 'file' || kind === 'any') {
    const fileHints = typeof getWorkspaceAutocompleteFileHints === 'function'
      ? getWorkspaceAutocompleteFileHints()
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
  if (typeof refreshWorkspaceFileCache === 'function') {
    await refreshWorkspaceFileCache();
  }
}

function _isWorkspaceDeleteCommand(cmd) {
  if (!(typeof APP_CONFIG !== 'undefined' && APP_CONFIG && APP_CONFIG.workspace_enabled === true)) {
    return false;
  }
  const parts = _workspaceCommandTokens(cmd);
  const root = (parts[0] || '').toLowerCase();
  const action = (parts[1] || '').toLowerCase();
  return root === 'rm' || (root === 'file' && ['rm', 'delete'].includes(action));
}

function _isWorkspaceEditorCommand(cmd) {
  if (!(typeof APP_CONFIG !== 'undefined' && APP_CONFIG && APP_CONFIG.workspace_enabled === true)) {
    return false;
  }
  const parts = _workspaceCommandTokens(cmd);
  const root = (parts[0] || '').toLowerCase();
  const action = (parts[1] || '').toLowerCase();
  return root === 'file' && ['add', 'edit'].includes(action);
}

function _isWorkspaceDownloadCommand(cmd) {
  if (!(typeof APP_CONFIG !== 'undefined' && APP_CONFIG && APP_CONFIG.workspace_enabled === true)) {
    return false;
  }
  const parts = String(cmd || '').trim().split(/\s+/).filter(Boolean);
  return (parts[0] || '').toLowerCase() === 'file' && (parts[1] || '').toLowerCase() === 'download';
}

function _isWorkspaceMoveCommand(cmd) {
  if (!(typeof APP_CONFIG !== 'undefined' && APP_CONFIG && APP_CONFIG.workspace_enabled === true)) {
    return false;
  }
  return !!_workspaceMoveCommand(cmd);
}

function _isWorkspaceTerminalCommand(cmd) {
  if (!(typeof APP_CONFIG !== 'undefined' && APP_CONFIG && APP_CONFIG.workspace_enabled === true)) return false;
  const parts = _workspaceCommandTokens(cmd);
  const root = (parts[0] || '').toLowerCase();
  if (['cd', 'pwd', 'ls', 'll', 'cat', 'mkdir', 'grep', 'head', 'tail', 'wc', 'sort', 'uniq'].includes(root)) return true;
  if (root === 'file' && ['list', 'ls', 'show', 'add-dir', 'mkdir'].includes((parts[1] || '').toLowerCase())) return true;
  return false;
}
