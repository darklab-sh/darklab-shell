function _workspaceApi() {
  return typeof window !== 'undefined' ? window : globalThis;
}

function _workspaceState() {
  return _workspaceApi().DarklabWorkspaceState || {};
}

async function refreshWorkspaceFileCache() {
  const api = _workspaceApi();
  const state = _workspaceState();
  const fetcher = typeof api.apiFetch === 'function'
    ? api.apiFetch
    : (typeof apiFetch === 'function' ? apiFetch : null);
  if (typeof api.isWorkspaceEnabled !== 'function' || !api.isWorkspaceEnabled() || !fetcher) return state.files || [];
  try {
    const resp = await fetcher('/workspace/files');
    const data = await api._workspaceJson(resp);
    const nextOwner = typeof api._workspaceOwnerFromPayload === 'function' ? api._workspaceOwnerFromPayload(data) : {};
    const previousScopeKey = typeof api._workspaceActiveScopeKeyFromOwner === 'function'
      ? api._workspaceActiveScopeKeyFromOwner(state.owner)
      : 'personal';
    const nextScopeKey = typeof api._workspaceActiveScopeKeyFromOwner === 'function'
      ? api._workspaceActiveScopeKeyFromOwner(nextOwner)
      : previousScopeKey;
    if (previousScopeKey !== nextScopeKey && typeof api._workspaceResetForScopeChange === 'function') {
      api._workspaceResetForScopeChange();
    }
    if (typeof api.renderWorkspaceFiles === 'function') {
      api.renderWorkspaceFiles(data);
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
  const api = _workspaceApi();
  const state = _workspaceState();
  const files = Array.isArray(state.files) ? state.files : [];
  if (!state.loaded || !files.length) return [];
  return files.map(file => {
    const path = String(file.path || '').trim();
    return {
      value: path,
      description: `${state.owner && state.owner.scope === 'team' ? 'team' : 'personal'} file · ${api._formatWorkspaceBytes(file.size)}`,
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
  return _workspaceApi()._workspaceDirectEntries(path);
}

if (typeof window !== 'undefined') {
  Object.assign(window, {
    refreshWorkspaceFileCache,
    getWorkspaceAutocompleteFileHints,
    getWorkspaceAutocompleteDirectoryHints,
    getWorkspaceDirectoryEntries,
  });
}
