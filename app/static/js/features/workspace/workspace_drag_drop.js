let _workspaceDragPath = '';
let _workspaceDragKind = '';

function _workspaceDragApi() {
  return typeof window !== 'undefined' ? window : globalThis;
}

function _workspaceDragSourceFromEvent(event) {
  const api = _workspaceDragApi();
  const list = api.workspaceFileList || (typeof workspaceFileList !== 'undefined' ? workspaceFileList : null);
  const row = event.target && event.target.closest ? event.target.closest('.workspace-file-row[draggable="true"]') : null;
  return row && list && list.contains(row) ? row : null;
}

function _workspaceDropTargetFromEvent(event) {
  const api = _workspaceDragApi();
  const list = api.workspaceFileList || (typeof workspaceFileList !== 'undefined' ? workspaceFileList : null);
  const row = event.target && event.target.closest ? event.target.closest('[data-workspace-drop-target="folder"]') : null;
  return row && list && list.contains(row) ? row : null;
}

function _workspaceCanDropOnFolder(sourcePath, destinationPath) {
  const api = _workspaceDragApi();
  if (typeof api.isWorkspaceReadOnly === 'function' && api.isWorkspaceReadOnly()) return false;
  const source = String(sourcePath || '').trim();
  const destination = String(destinationPath || '').trim();
  if (!source) return false;
  if (!destination) return true;
  return source !== destination && !destination.startsWith(`${source}/`);
}

async function _handleWorkspaceDropMove(event) {
  const api = _workspaceDragApi();
  if (typeof api.workspaceCanWrite === 'function' && !api.workspaceCanWrite('move Files', { toast: true })) return;
  const target = _workspaceDropTargetFromEvent(event);
  if (!target || !_workspaceCanDropOnFolder(_workspaceDragPath, target.dataset.path || '')) return;
  event.preventDefault();
  target.classList.remove('workspace-drop-target');
  const destination = target.dataset.path || '';
  const source = _workspaceDragPath;
  const kind = _workspaceDragKind === 'folder' ? 'folder' : 'file';
  if (!source) return;
  const confirmed = typeof showConfirm === 'function'
    ? await showConfirm({
        body: {
          text: `Move ${kind} ${source}?`,
          note: destination ? `Destination folder: ${destination}` : 'Destination folder: Files',
        },
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'move', label: 'Move', role: 'primary' },
        ],
      })
    : 'move';
  if (confirmed !== 'move') return;
  try {
    await api.moveWorkspacePath(source, destination);
  } catch (err) {
    api._showWorkspaceToast(api._workspaceErrorMessage(err, 'Unable to move item'), 'error');
  }
}

const _workspaceDragFileList = _workspaceDragApi().workspaceFileList || (typeof workspaceFileList !== 'undefined' ? workspaceFileList : null);

_workspaceDragFileList?.addEventListener('dragstart', event => {
  const api = _workspaceDragApi();
  if (typeof api.workspaceCanWrite === 'function' && !api.workspaceCanWrite('move Files', { toast: true })) {
    event.preventDefault();
    return;
  }
  const row = _workspaceDragSourceFromEvent(event);
  if (!row) return;
  _workspaceDragPath = row.dataset.path || '';
  _workspaceDragKind = row.dataset.kind || '';
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', _workspaceDragPath);
  }
  row.classList.add('workspace-dragging');
});

_workspaceDragFileList?.addEventListener('dragend', event => {
  const row = _workspaceDragSourceFromEvent(event);
  if (row) row.classList.remove('workspace-dragging');
  _workspaceDragFileList.querySelectorAll('.workspace-drop-target').forEach(node => node.classList.remove('workspace-drop-target'));
  _workspaceDragPath = '';
  _workspaceDragKind = '';
});

_workspaceDragFileList?.addEventListener('dragover', event => {
  const target = _workspaceDropTargetFromEvent(event);
  if (!target || !_workspaceCanDropOnFolder(_workspaceDragPath, target.dataset.path || '')) return;
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
  target.classList.add('workspace-drop-target');
});

_workspaceDragFileList?.addEventListener('dragleave', event => {
  const target = _workspaceDropTargetFromEvent(event);
  if (!target) return;
  const related = event.relatedTarget;
  if (related && target.contains(related)) return;
  target.classList.remove('workspace-drop-target');
});

_workspaceDragFileList?.addEventListener('drop', event => {
  void _handleWorkspaceDropMove(event);
});

if (typeof window !== 'undefined') {
  Object.assign(window, {
    _workspaceDragSourceFromEvent,
    _workspaceDropTargetFromEvent,
    _workspaceCanDropOnFolder,
    _handleWorkspaceDropMove,
  });
}
