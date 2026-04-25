// ── Session workspace UI ──
// App-mediated file helper only. This does not expose shell navigation,
// redirection, or arbitrary host paths.

let _workspaceFiles = [];
let _workspaceLoaded = false;

function _formatWorkspaceBytes(bytes) {
  const value = Number(bytes) || 0;
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1).replace(/\.0$/, '')} KB`;
  return `${(value / (1024 * 1024)).toFixed(1).replace(/\.0$/, '')} MB`;
}

function _workspaceErrorMessage(err, fallback = 'Workspace request failed') {
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
    throw new Error(data && data.error ? data.error : `Workspace request failed (${resp.status})`);
  }
  return data;
}

function setWorkspaceMessage(message = '', tone = 'muted') {
  if (!workspaceMessage) return;
  workspaceMessage.textContent = message;
  workspaceMessage.classList.toggle('u-hidden', !message);
  workspaceMessage.classList.toggle('workspace-message-error', tone === 'error');
}

function hideWorkspaceEditor() {
  if (workspaceEditor) workspaceEditor.classList.add('u-hidden');
}

function hideWorkspaceViewer() {
  if (workspaceViewer) workspaceViewer.classList.add('u-hidden');
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
  const payload = _workspaceViewerPayload(path, text);
  if (workspaceViewerTitle) workspaceViewerTitle.textContent = path;
  if (workspaceViewerText) {
    workspaceViewerText.textContent = payload.text;
    workspaceViewerText.classList.toggle('workspace-viewer-json', payload.format === 'json');
  }
  if (workspaceViewer) {
    workspaceViewer.dataset.format = payload.format;
    workspaceViewer.classList.remove('u-hidden');
  }
}

function renderWorkspaceFiles(payload = {}) {
  _workspaceLoaded = true;
  _workspaceFiles = Array.isArray(payload.files) ? payload.files : [];
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
  workspaceFileList.textContent = '';

  if (!_workspaceFiles.length) {
    const empty = document.createElement('div');
    empty.className = 'workspace-empty';
    empty.textContent = 'No workspace files yet. Create a text file to use in future workspace-aware commands.';
    workspaceFileList.appendChild(empty);
    return;
  }

  for (const file of _workspaceFiles) {
    const path = String(file.path || '');
    const row = document.createElement('div');
    row.className = 'workspace-file-row';
    row.dataset.path = path;

    const meta = document.createElement('div');
    meta.className = 'workspace-file-meta';
    const name = document.createElement('div');
    name.className = 'workspace-file-name';
    name.textContent = path;
    const details = document.createElement('div');
    details.className = 'workspace-file-details';
    details.textContent = `${_formatWorkspaceBytes(file.size)}${file.mtime ? ` · ${file.mtime}` : ''}`;
    meta.appendChild(name);
    meta.appendChild(details);

    const actions = document.createElement('div');
    actions.className = 'workspace-file-actions';
    const view = document.createElement('button');
    view.type = 'button';
    view.className = 'btn btn-secondary btn-compact';
    view.dataset.workspaceAction = 'view';
    view.textContent = 'View';
    const edit = document.createElement('button');
    edit.type = 'button';
    edit.className = 'btn btn-secondary btn-compact';
    edit.dataset.workspaceAction = 'edit';
    edit.textContent = 'Edit';
    const download = document.createElement('button');
    download.type = 'button';
    download.className = 'btn btn-secondary btn-compact';
    download.dataset.workspaceAction = 'download';
    download.textContent = 'Download';
    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'btn btn-destructive btn-compact';
    del.dataset.workspaceAction = 'delete';
    del.textContent = 'Delete';
    actions.appendChild(view);
    actions.appendChild(edit);
    actions.appendChild(download);
    actions.appendChild(del);

    row.appendChild(meta);
    row.appendChild(actions);
    workspaceFileList.appendChild(row);
  }
}

async function refreshWorkspaceFiles() {
  setWorkspaceMessage('');
  if (workspaceSummary) workspaceSummary.textContent = 'Loading…';
  const resp = await apiFetch('/workspace/files');
  const data = await _workspaceJson(resp);
  renderWorkspaceFiles(data);
  return data;
}

async function refreshWorkspaceFileCache() {
  try {
    const resp = await apiFetch('/workspace/files');
    const data = await _workspaceJson(resp);
    _workspaceLoaded = true;
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
      description: `workspace file · ${_formatWorkspaceBytes(file.size)}`,
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

async function readWorkspaceFile(path) {
  const resp = await apiFetch(`/workspace/files/read?path=${encodeURIComponent(path)}`);
  return _workspaceJson(resp);
}

async function deleteWorkspaceFile(path) {
  const resp = await apiFetch(`/workspace/files?path=${encodeURIComponent(path)}`, { method: 'DELETE' });
  const data = await _workspaceJson(resp);
  renderWorkspaceFiles(data.workspace || {});
  hideWorkspaceViewer();
  setWorkspaceMessage(`Deleted ${path}`);
  return data;
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
  _closeMajorOverlays();
  if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
  showWorkspaceOverlay();
  hideWorkspaceEditor();
  hideWorkspaceViewer();
  try {
    await refreshWorkspaceFiles();
  } catch (err) {
    _workspaceLoaded = false;
    _workspaceFiles = [];
    if (workspaceFileList) workspaceFileList.textContent = '';
    if (workspaceSummary) workspaceSummary.textContent = 'Unavailable';
    setWorkspaceMessage(_workspaceErrorMessage(err, 'Unable to load workspace'), 'error');
  }
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
    if (action === 'view') {
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
            body: { text: `Delete ${path}?`, note: 'This only removes the session workspace copy.' },
            tone: 'danger',
            actions: [
              { id: 'cancel', label: 'Cancel', role: 'cancel' },
              { id: 'delete', label: 'Delete', role: 'primary', tone: 'danger' },
            ],
          })
        : 'delete';
      if (confirmed === 'delete') await deleteWorkspaceFile(path);
    }
  } catch (err) {
    setWorkspaceMessage(_workspaceErrorMessage(err), 'error');
  }
}

workspaceNewBtn?.addEventListener('click', () => showWorkspaceEditor('', ''));
workspaceCancelEditBtn?.addEventListener('click', () => hideWorkspaceEditor());
workspaceCloseViewerBtn?.addEventListener('click', () => hideWorkspaceViewer());
workspaceEditor?.addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    await saveWorkspaceFile(workspacePathInput?.value || '', workspaceTextInput?.value || '');
  } catch (err) {
    setWorkspaceMessage(_workspaceErrorMessage(err, 'Unable to save workspace file'), 'error');
  }
});
workspaceFileList?.addEventListener('click', event => {
  const btn = event.target && event.target.closest ? event.target.closest('[data-workspace-action]') : null;
  if (!btn) return;
  const row = btn.closest('.workspace-file-row');
  const path = row?.dataset.path || '';
  if (!path) return;
  handleWorkspaceFileAction(btn.dataset.workspaceAction, path);
});

if (typeof window !== 'undefined') {
  window.openWorkspace = openWorkspace;
  window.closeWorkspace = closeWorkspace;
  window.refreshWorkspaceFiles = refreshWorkspaceFiles;
  window.refreshWorkspaceFileCache = refreshWorkspaceFileCache;
  window.getWorkspaceAutocompleteFileHints = getWorkspaceAutocompleteFileHints;
  window.renderWorkspaceFiles = renderWorkspaceFiles;
  setTimeout(() => { refreshWorkspaceFileCache(); }, 0);
}
