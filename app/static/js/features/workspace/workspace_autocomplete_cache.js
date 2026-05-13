async function refreshWorkspaceFileCache() {
  if (!isWorkspaceEnabled()) return _workspaceFiles;
  try {
    const resp = await apiFetch('/workspace/files');
    const data = await _workspaceJson(resp);
    _workspaceLoaded = true;
    _workspaceDirs = Array.isArray(data.directories) ? data.directories : [];
    _workspaceFiles = Array.isArray(data.files) ? data.files : [];
    if (workspaceOverlay && workspaceOverlay.classList.contains('open')) renderWorkspaceFiles(data);
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
      description: `session file · ${_formatWorkspaceBytes(file.size)}`,
    };
  }).filter(item => item.value);
}

function getWorkspaceAutocompleteDirectoryHints() {
  if (!_workspaceLoaded || !Array.isArray(_workspaceDirs) || !_workspaceDirs.length) return [];
  return _workspaceDirs.map(directory => {
    const path = String(directory.path || '').trim();
    return {
      value: path,
      description: 'session folder',
    };
  }).filter(item => item.value);
}

function getWorkspaceDirectoryEntries(path = '') {
  return _workspaceDirectEntries(path);
}
