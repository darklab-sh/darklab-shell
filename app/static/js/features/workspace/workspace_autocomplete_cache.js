function _workspaceApi() {
  return typeof window !== 'undefined' ? window : globalThis;
}

function _workspaceState() {
  return _workspaceApi().DarklabWorkspaceState || {};
}

async function refreshWorkspaceFileCache() {
  const state = _workspaceState();
  const fetcher = typeof state.apiFetch === 'function'
    ? state.apiFetch
    : typeof _workspaceApi().apiFetch === 'function'
      ? _workspaceApi().apiFetch
      : null;
  const isEnabled = typeof state.isEnabled === 'function'
    ? state.isEnabled
    : typeof _workspaceApi().isWorkspaceEnabled === 'function'
      ? _workspaceApi().isWorkspaceEnabled
      : null;
  if (!isEnabled || !isEnabled() || !fetcher) return state.files || [];
  try {
    if (typeof state.loadFilesPayload === 'function') {
      await state.loadFilesPayload();
      return state.files || [];
    }
    const resp = await fetcher('/workspace/files');
    const data = typeof state.parseJson === 'function'
      ? await state.parseJson(resp)
      : await resp.json();
    const nextOwner = typeof state.ownerFromPayload === 'function' ? state.ownerFromPayload(data) : {};
    const scopeKey = typeof state.activeScopeKeyFromOwner === 'function'
      ? state.activeScopeKeyFromOwner
      : null;
    const previousScopeKey = scopeKey
      ? scopeKey(state.owner)
      : 'personal';
    const nextScopeKey = scopeKey
      ? scopeKey(nextOwner)
      : previousScopeKey;
    if (previousScopeKey !== nextScopeKey && typeof state.resetForScopeChange === 'function') {
      state.resetForScopeChange();
    }
    if (typeof state.renderFiles === 'function') {
      state.renderFiles(data);
    } else {
      state.loaded = true;
      state.dirs = Array.isArray(data.directories) ? data.directories : [];
      state.files = Array.isArray(data.files) ? data.files : [];
    }
    return state.files || [];
  } catch (_) {
    return state.files || [];
  }
}

function getWorkspaceAutocompleteFileHints() {
  const state = _workspaceState();
  const files = Array.isArray(state.files) ? state.files : [];
  if (!state.loaded || !files.length) return [];
  const formatBytes = typeof state.formatBytes === 'function'
    ? state.formatBytes
    : value => `${Number(value) || 0} B`;
  return files.map(file => {
    const path = String(file.path || '').trim();
    return {
      value: path,
      description: `${state.owner && state.owner.scope === 'team' ? 'team' : 'personal'} file · ${formatBytes(file.size)}`,
    };
  }).filter(item => item.value);
}

function getWorkspaceAutocompleteDirectoryHints() {
  const state = _workspaceState();
  const dirs = Array.isArray(state.dirs) ? state.dirs : [];
  if (!state.loaded || !dirs.length) return [];
  return dirs.map(directory => {
    const path = String(directory.path || '').trim();
    return {
      value: path,
      description: `${state.owner && state.owner.scope === 'team' ? 'team' : 'personal'} folder`,
    };
  }).filter(item => item.value);
}

function getWorkspaceDirectoryEntries(path = '') {
  const state = _workspaceState();
  return typeof state.getDirectoryEntries === 'function' ? state.getDirectoryEntries(path) : [];
}

if (typeof window !== 'undefined') {
}

export {
  getWorkspaceAutocompleteDirectoryHints,
  getWorkspaceAutocompleteFileHints,
  getWorkspaceDirectoryEntries,
  refreshWorkspaceFileCache,
};
