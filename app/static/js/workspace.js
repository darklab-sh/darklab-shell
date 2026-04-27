// ── Session workspace UI ──
// App-mediated file helper only. This does not expose shell navigation,
// redirection, or arbitrary host paths.

let _workspaceFiles = [];
let _workspaceDirs = [];
let _workspaceLoaded = false;
let _workspaceCurrentDir = '';
let _workspaceViewedPath = '';

function isWorkspaceEnabled() {
  return !!(typeof APP_CONFIG !== 'undefined' && APP_CONFIG && APP_CONFIG.workspace_enabled === true);
}

function _formatWorkspaceBytes(bytes) {
  const value = Number(bytes) || 0;
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1).replace(/\.0$/, '')} KB`;
  return `${(value / (1024 * 1024)).toFixed(1).replace(/\.0$/, '')} MB`;
}

function _workspaceErrorMessage(err, fallback = 'Files request failed') {
  if (err && typeof err.message === 'string' && err.message.trim()) return err.message.trim();
  return fallback;
}

async function _workspaceJson(resp) {
  let data = {};
  try {
    data = await resp.json();
  } catch (_) {
    data = {};
  }
  if (!resp.ok) {
    throw new Error(data && data.error ? data.error : `Files request failed (${resp.status})`);
  }
  return data;
}

function setWorkspaceMessage(message = '', tone = 'muted') {
  if (!workspaceMessage) return;
  workspaceMessage.textContent = message;
  workspaceMessage.classList.toggle('u-hidden', !message);
  workspaceMessage.classList.toggle('workspace-message-error', tone === 'error');
}

function _showWorkspaceToast(message, tone = 'error') {
  const text = String(message || '').trim();
  if (!text) return;
  if (typeof showToast === 'function') showToast(text, tone);
  else setWorkspaceMessage(text, tone);
}

function hideWorkspaceEditor() {
  if (workspaceEditor) workspaceEditor.classList.add('u-hidden');
}

function hideWorkspaceViewer() {
  if (workspaceViewer) workspaceViewer.classList.add('u-hidden');
  _workspaceViewedPath = '';
}

function _workspaceViewerPayload(path = '', text = '') {
  const rawText = String(text || '');
  const trimmed = rawText.trim();
  const looksJson = /\.json$/i.test(String(path || '')) || /^[{[]/.test(trimmed);
  if (!looksJson) return { text: rawText, format: '' };
  try {
    return {
      text: JSON.stringify(JSON.parse(trimmed), null, 2),
      format: 'json',
    };
  } catch (_) {
    return { text: rawText, format: '' };
  }
}

function showWorkspaceEditor(path = '', text = '') {
  if (!workspaceEditor) return;
  hideWorkspaceViewer();
  workspaceEditor.classList.remove('u-hidden');
  if (workspacePathInput) workspacePathInput.value = path;
  if (workspaceTextInput) workspaceTextInput.value = text;
  setTimeout(() => {
    if (workspacePathInput && !path) workspacePathInput.focus();
    else if (workspaceTextInput) workspaceTextInput.focus();
  }, 0);
}

function showWorkspaceViewer(path = '', text = '') {
  hideWorkspaceEditor();
  _workspaceViewedPath = String(path || '').trim();
  const payload = _workspaceViewerPayload(path, text);
  if (workspaceViewerTitle) workspaceViewerTitle.textContent = path;
  if (workspaceViewerText) {
    workspaceViewerText.textContent = payload.text;
    workspaceViewerText.classList.toggle('workspace-viewer-json', payload.format === 'json');
    workspaceViewerText.scrollTop = 0;
  }
  if (workspaceViewer) {
    workspaceViewer.dataset.format = payload.format;
    workspaceViewer.classList.remove('u-hidden');
    workspaceViewer.scrollTop = 0;
    if (typeof workspaceViewer.scrollIntoView === 'function') {
      workspaceViewer.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }
}

function _normalizeWorkspaceDir(path = '') {
  return String(path || '').split('/').map(part => part.trim()).filter(Boolean).join('/');
}

function _workspaceParentDir(path = '') {
  const parts = _normalizeWorkspaceDir(path).split('/').filter(Boolean);
  parts.pop();
  return parts.join('/');
}

function _workspaceFileBasename(path = '') {
  const parts = String(path || '').split('/').filter(Boolean);
  return parts[parts.length - 1] || String(path || '');
}

function _activateWorkspaceFolderRow(path, event = null) {
  if (event && event.target && event.target.closest && event.target.closest('[data-workspace-action]')) return;
  handleWorkspaceFileAction('open-folder', path);
}

function _bindWorkspaceFolderRow(row, path, label) {
  row.className = 'workspace-file-row workspace-folder-row';
  row.dataset.kind = 'folder';
  row.dataset.path = path;
  row.tabIndex = 0;
  row.setAttribute('role', 'button');
  row.setAttribute('aria-label', label);
  if (typeof bindPressable === 'function') {
    bindPressable(row, {
      onActivate: event => _activateWorkspaceFolderRow(path, event),
      refocusComposer: false,
      clearPressStyle: true,
    });
  } else {
    row.addEventListener('click', event => _activateWorkspaceFolderRow(path, event));
    row.addEventListener('keydown', event => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      _activateWorkspaceFolderRow(path, event);
    });
  }
}

function _workspacePathInCurrentDir(path = '') {
  const raw = String(path || '').trim();
  const current = _normalizeWorkspaceDir(_workspaceCurrentDir);
  if (!raw) return current ? `${current}/` : '';
  if (raw.includes('/')) return raw;
  return current ? `${current}/${raw}` : raw;
}

function _workspaceDirectEntries(dir = '') {
  const current = _normalizeWorkspaceDir(dir);
  const folders = new Map();
  const files = [];
  for (const directory of _workspaceDirs) {
    const path = String(directory.path || '').split('/').filter(Boolean).join('/');
    if (!path) continue;
    const prefix = current ? `${current}/` : '';
    if (current && path !== current && !path.startsWith(prefix)) continue;
    if (path === current) continue;
    const relative = current ? path.slice(prefix.length) : path;
    const parts = relative.split('/').filter(Boolean);
    if (parts.length >= 1) {
      const folderName = parts[0];
      const folderPath = current ? `${current}/${folderName}` : folderName;
      folders.set(folderPath, { name: folderName, path: folderPath });
    }
  }
  for (const file of _workspaceFiles) {
    const path = String(file.path || '').split('/').filter(Boolean).join('/');
    if (!path) continue;
    const prefix = current ? `${current}/` : '';
    if (current && path !== current && !path.startsWith(prefix)) continue;
    const relative = current ? path.slice(prefix.length) : path;
    if (!relative || relative === path && current && !path.startsWith(prefix)) continue;
    const parts = relative.split('/').filter(Boolean);
    if (parts.length > 1) {
      const folderName = parts[0];
      const folderPath = current ? `${current}/${folderName}` : folderName;
      folders.set(folderPath, { name: folderName, path: folderPath });
    } else if (parts.length === 1) {
      files.push({ ...file, path, name: parts[0] });
    }
  }
  return {
    folders: [...folders.values()].sort((a, b) => a.name.localeCompare(b.name)),
    files: files.sort((a, b) => String(a.name || '').localeCompare(String(b.name || ''))),
  };
}

function _workspaceFolderFileCount(path = '') {
  const normalized = _normalizeWorkspaceDir(path);
  if (!normalized) return 0;
  return _workspaceFiles.filter(file => {
    const filePath = String(file.path || '').split('/').filter(Boolean).join('/');
    return filePath.startsWith(`${normalized}/`);
  }).length;
}

function renderWorkspaceBreadcrumbs() {
  if (!workspaceBreadcrumbs) return;
  workspaceBreadcrumbs.textContent = '';
  const root = document.createElement('button');
  root.type = 'button';
  root.className = 'btn btn-secondary btn-compact';
  root.dataset.workspaceDir = '';
  root.textContent = 'Files';
  workspaceBreadcrumbs.appendChild(root);

  const parts = _normalizeWorkspaceDir(_workspaceCurrentDir).split('/').filter(Boolean);
  let acc = '';
  parts.forEach(part => {
    acc = acc ? `${acc}/${part}` : part;
    const separator = document.createElement('span');
    separator.className = 'workspace-breadcrumb-separator';
    separator.textContent = '/';
    const crumb = document.createElement('button');
    crumb.type = 'button';
    crumb.className = 'btn btn-secondary btn-compact';
    crumb.dataset.workspaceDir = acc;
    crumb.textContent = part;
    workspaceBreadcrumbs.appendChild(separator);
    workspaceBreadcrumbs.appendChild(crumb);
  });
}

function renderWorkspaceBrowser() {
  if (!workspaceFileList) return;
  workspaceFileList.textContent = '';
  renderWorkspaceBreadcrumbs();

  const { folders, files } = _workspaceDirectEntries(_workspaceCurrentDir);
  if (_workspaceCurrentDir) {
    const parent = document.createElement('div');
    const parentPath = _workspaceParentDir(_workspaceCurrentDir);
    _bindWorkspaceFolderRow(parent, parentPath, 'Open parent folder');
    parent.appendChild(_workspaceMetaNode('..', 'Parent folder', 'workspace-parent-icon', ''));
    parent.appendChild(_workspaceActionsNode([{ action: 'open-folder', label: 'Up', tone: 'secondary' }]));
    workspaceFileList.appendChild(parent);
  }

  for (const folder of folders) {
    const row = document.createElement('div');
    _bindWorkspaceFolderRow(row, folder.path, `Open folder ${folder.name}`);
    const count = _workspaceFolderFileCount(folder.path);
    row.appendChild(_workspaceMetaNode(
      folder.name,
      count ? `Folder · ${count} ${count === 1 ? 'file' : 'files'}` : 'Empty folder',
      'workspace-folder-icon',
      '>',
    ));
    row.appendChild(_workspaceActionsNode([
      { action: 'open-folder', label: 'Open', tone: 'secondary' },
      { action: 'delete-folder', label: 'Delete', tone: 'destructive' },
    ]));
    workspaceFileList.appendChild(row);
  }

  for (const file of files) {
    const row = document.createElement('div');
    row.className = 'workspace-file-row';
    row.dataset.kind = 'file';
    row.dataset.path = file.path;
    row.appendChild(_workspaceMetaNode(
      file.name || _workspaceFileBasename(file.path),
      `${_formatWorkspaceBytes(file.size)}${file.mtime ? ` · ${file.mtime}` : ''}`,
    ));
    row.appendChild(_workspaceActionsNode([
      { action: 'view', label: 'View', tone: 'secondary' },
      { action: 'edit', label: 'Edit', tone: 'secondary' },
      { action: 'download', label: 'Download', tone: 'secondary' },
      { action: 'delete', label: 'Delete', tone: 'destructive' },
    ]));
    workspaceFileList.appendChild(row);
  }

  if (!folders.length && !files.length && !_workspaceCurrentDir) {
    const empty = document.createElement('div');
    empty.className = 'workspace-empty';
    empty.textContent = 'No session files yet. Create a text file or save command output to use with file-enabled commands.';
    workspaceFileList.appendChild(empty);
  } else if (!folders.length && !files.length) {
    const empty = document.createElement('div');
    empty.className = 'workspace-empty';
    empty.textContent = 'This folder is empty.';
    workspaceFileList.appendChild(empty);
  }
}

function _workspaceMetaNode(nameText, detailsText, iconClass = '', iconText = '') {
  const meta = document.createElement('div');
  meta.className = 'workspace-file-meta';
  if (iconText) {
    const icon = document.createElement('span');
    icon.className = iconClass;
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = iconText;
    meta.appendChild(icon);
  }
  const text = document.createElement('div');
  text.className = 'workspace-file-meta-text';
  const name = document.createElement('div');
  name.className = 'workspace-file-name';
  name.textContent = nameText;
  const details = document.createElement('div');
  details.className = 'workspace-file-details';
  details.textContent = detailsText;
  text.appendChild(name);
  text.appendChild(details);
  meta.appendChild(text);
  return meta;
}

function _workspaceActionsNode(items = []) {
  const actions = document.createElement('div');
  actions.className = 'workspace-file-actions';
  for (const item of items) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `btn btn-${item.tone === 'destructive' ? 'destructive' : 'secondary'} btn-compact`;
    btn.dataset.workspaceAction = item.action;
    btn.textContent = item.label;
    actions.appendChild(btn);
  }
  return actions;
}

function renderWorkspaceFiles(payload = {}) {
  _workspaceLoaded = true;
  _workspaceDirs = Array.isArray(payload.directories) ? payload.directories : [];
  _workspaceFiles = Array.isArray(payload.files) ? payload.files : [];
  const currentHasEntries = !_workspaceCurrentDir || _workspaceFiles.some(file => {
    const path = String(file.path || '').split('/').filter(Boolean).join('/');
    return path === _workspaceCurrentDir || path.startsWith(`${_workspaceCurrentDir}/`);
  }) || _workspaceDirs.some(directory => {
    const path = String(directory.path || '').split('/').filter(Boolean).join('/');
    return path === _workspaceCurrentDir || path.startsWith(`${_workspaceCurrentDir}/`);
  });
  if (!currentHasEntries) _workspaceCurrentDir = '';
  const usage = payload.usage || {};
  const limits = payload.limits || {};
  const fileCount = Number(usage.file_count) || 0;
  const maxFiles = Number(limits.max_files) || 0;
  const bytesUsed = Number(usage.bytes_used) || 0;
  const quotaBytes = Number(limits.quota_bytes) || 0;

  if (workspaceSummary) {
    workspaceSummary.textContent = `${fileCount}${maxFiles ? ` / ${maxFiles}` : ''} files · ${_formatWorkspaceBytes(bytesUsed)}${quotaBytes ? ` / ${_formatWorkspaceBytes(quotaBytes)}` : ''}`;
  }
  if (!workspaceFileList) return;
  renderWorkspaceBrowser();
}

async function refreshWorkspaceFiles() {
  if (!isWorkspaceEnabled()) throw new Error('Files are disabled on this instance');
  setWorkspaceMessage('');
  if (workspaceSummary) workspaceSummary.textContent = 'Loading…';
  const resp = await apiFetch('/workspace/files');
  const data = await _workspaceJson(resp);
  renderWorkspaceFiles(data);
  return data;
}

async function refreshWorkspaceFilesFromButton() {
  if (!workspaceRefreshBtn) return;
  workspaceRefreshBtn.disabled = true;
  workspaceRefreshBtn.setAttribute('aria-label', 'Refreshing files');
  workspaceRefreshBtn.title = 'Refreshing files';
  try {
    const viewedPath = _workspaceViewedPath;
    await refreshWorkspaceFiles();
    if (viewedPath) {
      try {
        const data = await readWorkspaceFile(viewedPath);
        showWorkspaceViewer(data.path || viewedPath, data.text || '');
      } catch (err) {
        hideWorkspaceViewer();
        _showWorkspaceToast(_workspaceErrorMessage(err, 'Unable to refresh viewed file'), 'error');
      }
    }
  } catch (err) {
    _workspaceLoaded = false;
    _workspaceFiles = [];
    if (workspaceFileList) workspaceFileList.textContent = '';
    if (workspaceSummary) workspaceSummary.textContent = 'Unavailable';
    setWorkspaceMessage(_workspaceErrorMessage(err, 'Unable to refresh files'), 'error');
  } finally {
    workspaceRefreshBtn.disabled = false;
    workspaceRefreshBtn.setAttribute('aria-label', 'Refresh files');
    workspaceRefreshBtn.title = 'Refresh files';
  }
}

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

async function saveWorkspaceFile(path, text) {
  const resp = await apiFetch('/workspace/files', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, text }),
  });
  const data = await _workspaceJson(resp);
  renderWorkspaceFiles(data.workspace || {});
  hideWorkspaceEditor();
  hideWorkspaceViewer();
  setWorkspaceMessage(`Saved ${data.file?.path || path}`);
  return data;
}

async function createWorkspaceDirectory(path) {
  const normalized = _normalizeWorkspaceDir(path);
  const resp = await apiFetch('/workspace/directories', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path: normalized }),
  });
  const data = await _workspaceJson(resp);
  _workspaceCurrentDir = data.directory?.path || normalized;
  renderWorkspaceFiles(data.workspace || {});
  hideWorkspaceEditor();
  hideWorkspaceViewer();
  setWorkspaceMessage(`Created folder ${data.directory?.path || normalized}`);
  return data;
}

async function promptWorkspaceFolderName() {
  const current = _normalizeWorkspaceDir(_workspaceCurrentDir);
  const promptDefault = current ? `${current}/` : '';
  const entered = typeof window !== 'undefined' && typeof window.prompt === 'function'
    ? window.prompt('Folder name', promptDefault)
    : '';
  if (entered === null) return null;
  const raw = String(entered || '').trim();
  if (!raw) return null;
  const path = current && !raw.includes('/') ? `${current}/${raw}` : raw;
  try {
    return await createWorkspaceDirectory(path);
  } catch (err) {
    _showWorkspaceToast(_workspaceErrorMessage(err, 'Unable to create folder'), 'error');
    return null;
  }
}

async function readWorkspaceFile(path) {
  const resp = await apiFetch(`/workspace/files/read?path=${encodeURIComponent(path)}`);
  return _workspaceJson(resp);
}

async function deleteWorkspacePath(path) {
  const resp = await apiFetch(`/workspace/files?path=${encodeURIComponent(path)}`, { method: 'DELETE' });
  const data = await _workspaceJson(resp);
  renderWorkspaceFiles(data.workspace || {});
  hideWorkspaceViewer();
  const deleted = data.deleted || {};
  const kind = deleted.kind === 'directory' ? 'folder' : 'file';
  setWorkspaceMessage(`Deleted ${kind} ${path}`);
  return data;
}

async function deleteWorkspaceFile(path) {
  return deleteWorkspacePath(path);
}

async function downloadWorkspaceFile(path) {
  const resp = await apiFetch(`/workspace/files/download?path=${encodeURIComponent(path)}`);
  if (!resp.ok) {
    await _workspaceJson(resp);
    return false;
  }
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = path.split('/').filter(Boolean).pop() || 'workspace-file.txt';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return true;
}

async function openWorkspace() {
  if (!isWorkspaceEnabled()) return;
  _closeMajorOverlays();
  if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
  showWorkspaceOverlay();
  _workspaceCurrentDir = '';
  hideWorkspaceEditor();
  hideWorkspaceViewer();
  try {
    await refreshWorkspaceFiles();
  } catch (err) {
    _workspaceLoaded = false;
    _workspaceFiles = [];
    if (workspaceFileList) workspaceFileList.textContent = '';
    if (workspaceSummary) workspaceSummary.textContent = 'Unavailable';
    setWorkspaceMessage(_workspaceErrorMessage(err, 'Unable to load files'), 'error');
  }
}

async function openWorkspaceEditorFromCommand(action = 'add', path = '') {
  if (!isWorkspaceEnabled()) return false;
  await openWorkspace();
  const fileName = String(path || '').trim();
  if (String(action || '').toLowerCase() === 'edit' && fileName) {
    try {
      const data = await readWorkspaceFile(fileName);
      showWorkspaceEditor(data.path || fileName, data.text || '');
    } catch (err) {
      showWorkspaceEditor(fileName, '');
      setWorkspaceMessage(_workspaceErrorMessage(err, 'Unable to load session file'), 'error');
    }
    return true;
  }
  showWorkspaceEditor(fileName, '');
  return true;
}

function closeWorkspace() {
  hideWorkspaceOverlay();
  hideWorkspaceEditor();
  hideWorkspaceViewer();
  refocusComposerAfterAction({ defer: true });
}

async function handleWorkspaceFileAction(action, path) {
  try {
    setWorkspaceMessage('');
    if (action === 'open-folder') {
      _workspaceCurrentDir = _normalizeWorkspaceDir(path);
      hideWorkspaceViewer();
      renderWorkspaceBrowser();
    } else if (action === 'view') {
      const data = await readWorkspaceFile(path);
      showWorkspaceViewer(data.path || path, data.text || '');
    } else if (action === 'edit') {
      const data = await readWorkspaceFile(path);
      showWorkspaceEditor(data.path || path, data.text || '');
    } else if (action === 'download') {
      await downloadWorkspaceFile(path);
    } else if (action === 'delete') {
      const confirmed = typeof showConfirm === 'function'
        ? await showConfirm({
            body: { text: `Delete ${path}?`, note: 'This only removes the session file.' },
            tone: 'danger',
            actions: [
              { id: 'cancel', label: 'Cancel', role: 'cancel' },
              { id: 'delete', label: 'Delete', role: 'primary', tone: 'danger' },
            ],
          })
        : 'delete';
      if (confirmed === 'delete') await deleteWorkspacePath(path);
    } else if (action === 'delete-folder') {
      const count = _workspaceFolderFileCount(path);
      const note = count
        ? `This will also delete ${count} ${count === 1 ? 'file' : 'files'} in this folder.`
        : 'This only removes the empty session folder.';
      const confirmed = typeof showConfirm === 'function'
        ? await showConfirm({
            body: { text: `Delete folder ${path}?`, note },
            tone: 'danger',
            actions: [
              { id: 'cancel', label: 'Cancel', role: 'cancel' },
              { id: 'delete', label: 'Delete', role: 'primary', tone: 'danger' },
            ],
          })
        : 'delete';
      if (confirmed === 'delete') await deleteWorkspacePath(path);
    }
  } catch (err) {
    _showWorkspaceToast(_workspaceErrorMessage(err), 'error');
  }
}

workspaceRefreshBtn?.addEventListener('click', () => { refreshWorkspaceFilesFromButton(); });
workspaceNewBtn?.addEventListener('click', () => showWorkspaceEditor('', ''));
workspaceNewFolderBtn?.addEventListener('click', () => { promptWorkspaceFolderName(); });
workspaceCancelEditBtn?.addEventListener('click', () => hideWorkspaceEditor());
workspaceCloseViewerBtn?.addEventListener('click', () => hideWorkspaceViewer());
workspaceBreadcrumbs?.addEventListener('click', event => {
  const btn = event.target && event.target.closest ? event.target.closest('[data-workspace-dir]') : null;
  if (!btn) return;
  _workspaceCurrentDir = _normalizeWorkspaceDir(btn.dataset.workspaceDir || '');
  hideWorkspaceViewer();
  renderWorkspaceBrowser();
});
workspaceViewer?.addEventListener('click', event => {
  const btn = event.target && event.target.closest ? event.target.closest('[data-workspace-viewer-action]') : null;
  if (!btn || !_workspaceViewedPath) return;
  handleWorkspaceFileAction(btn.dataset.workspaceViewerAction, _workspaceViewedPath);
});
workspaceEditor?.addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    await saveWorkspaceFile(_workspacePathInCurrentDir(workspacePathInput?.value || ''), workspaceTextInput?.value || '');
  } catch (err) {
    setWorkspaceMessage(_workspaceErrorMessage(err, 'Unable to save session file'), 'error');
  }
});
workspaceFileList?.addEventListener('click', event => {
  const btn = event.target && event.target.closest ? event.target.closest('[data-workspace-action]') : null;
  if (!btn) return;
  const row = btn.closest('.workspace-file-row');
  if (!row || !workspaceFileList.contains(row)) return;
  const action = btn.dataset.workspaceAction;
  const path = row?.dataset.path || '';
  if (!path && action !== 'open-folder') return;
  handleWorkspaceFileAction(action, path);
});

if (typeof window !== 'undefined') {
  window.openWorkspace = openWorkspace;
  window.closeWorkspace = closeWorkspace;
  window.refreshWorkspaceFiles = refreshWorkspaceFiles;
  window.refreshWorkspaceFileCache = refreshWorkspaceFileCache;
  window.getWorkspaceAutocompleteFileHints = getWorkspaceAutocompleteFileHints;
  window.renderWorkspaceFiles = renderWorkspaceFiles;
  window.renderWorkspaceBrowser = renderWorkspaceBrowser;
  window.createWorkspaceDirectory = createWorkspaceDirectory;
  window.deleteWorkspacePath = deleteWorkspacePath;
  window.downloadWorkspaceFile = downloadWorkspaceFile;
  window.openWorkspaceEditorFromCommand = openWorkspaceEditorFromCommand;
  if (isWorkspaceEnabled()) setTimeout(() => { refreshWorkspaceFileCache(); }, 0);
}
