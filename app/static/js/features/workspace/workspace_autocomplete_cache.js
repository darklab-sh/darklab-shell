async function refreshWorkspaceFileCache() {
  if (!isWorkspaceEnabled()) return _workspaceFiles;
  try {
    const resp = await apiFetch('/workspace/files');
    const data = await _workspaceJson(resp);
    const nextOwner = typeof _workspaceOwnerFromPayload === 'function' ? _workspaceOwnerFromPayload(data) : {};
    const previousScopeKey = typeof _workspaceActiveScopeKeyFromOwner === 'function'
      ? _workspaceActiveScopeKeyFromOwner(_workspaceOwner)
      : 'personal';
    const nextScopeKey = typeof _workspaceActiveScopeKeyFromOwner === 'function'
      ? _workspaceActiveScopeKeyFromOwner(nextOwner)
      : previousScopeKey;
    if (previousScopeKey !== nextScopeKey && typeof _workspaceResetForScopeChange === 'function') {
      _workspaceResetForScopeChange();
    }
    if (typeof renderWorkspaceFiles === 'function') {
      renderWorkspaceFiles(data);
    } else {
      _workspaceLoaded = true;
      _workspaceDirs = Array.isArray(data.directories) ? data.directories : [];
      _workspaceFiles = Array.isArray(data.files) ? data.files : [];
    }
    return _workspaceFiles;
  } catch (_) {
    return _workspaceFiles;
  }
}

function getWorkspaceAutocompleteFileHints() {
  if (!_workspaceLoaded || !Array.isArray(_workspaceFiles) || !_workspaceFiles.length) return [];
  return _workspaceFiles.map(file => {
    const path = String(file.path || '').trim();
    return {
      value: path,
      description: `${_workspaceOwner && _workspaceOwner.scope === 'team' ? 'team' : 'personal'} file · ${_formatWorkspaceBytes(file.size)}`,
    };
  }).filter(item => item.value);
}

function getWorkspaceAutocompleteDirectoryHints() {
  if (!_workspaceLoaded || !Array.isArray(_workspaceDirs) || !_workspaceDirs.length) return [];
  return _workspaceDirs.map(directory => {
    const path = String(directory.path || '').trim();
    return {
      value: path,
      description: `${_workspaceOwner && _workspaceOwner.scope === 'team' ? 'team' : 'personal'} folder`,
    };
  }).filter(item => item.value);
}

function getWorkspaceDirectoryEntries(path = '') {
  return _workspaceDirectEntries(path);
}
