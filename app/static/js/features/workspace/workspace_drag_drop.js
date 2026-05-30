let _workspaceDragPath = '';
let _workspaceDragKind = '';

function _workspaceDragSourceFromEvent(event) {
  const row = event.target && event.target.closest ? event.target.closest('.workspace-file-row[draggable="true"]') : null;
  return row && workspaceFileList && workspaceFileList.contains(row) ? row : null;
}

function _workspaceDropTargetFromEvent(event) {
  const row = event.target && event.target.closest ? event.target.closest('[data-workspace-drop-target="folder"]') : null;
  return row && workspaceFileList && workspaceFileList.contains(row) ? row : null;
}

function _workspaceCanDropOnFolder(sourcePath, destinationPath) {
  if (typeof isWorkspaceReadOnly === 'function' && isWorkspaceReadOnly()) return false;
  const source = String(sourcePath || '').trim();
  const destination = String(destinationPath || '').trim();
  if (!source) return false;
  if (!destination) return true;
  return source !== destination && !destination.startsWith(`${source}/`);
}

async function _handleWorkspaceDropMove(event) {
  if (typeof workspaceCanWrite === 'function' && !workspaceCanWrite('move Files', { toast: true })) return;
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
    await moveWorkspacePath(source, destination);
  } catch (err) {
    _showWorkspaceToast(_workspaceErrorMessage(err, 'Unable to move item'), 'error');
  }
}

workspaceFileList?.addEventListener('dragstart', event => {
  if (typeof workspaceCanWrite === 'function' && !workspaceCanWrite('move Files', { toast: true })) {
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

workspaceFileList?.addEventListener('dragend', event => {
  const row = _workspaceDragSourceFromEvent(event);
  if (row) row.classList.remove('workspace-dragging');
  workspaceFileList.querySelectorAll('.workspace-drop-target').forEach(node => node.classList.remove('workspace-drop-target'));
  _workspaceDragPath = '';
  _workspaceDragKind = '';
});

workspaceFileList?.addEventListener('dragover', event => {
  const target = _workspaceDropTargetFromEvent(event);
  if (!target || !_workspaceCanDropOnFolder(_workspaceDragPath, target.dataset.path || '')) return;
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
  target.classList.add('workspace-drop-target');
});

workspaceFileList?.addEventListener('dragleave', event => {
  const target = _workspaceDropTargetFromEvent(event);
  if (!target) return;
  const related = event.relatedTarget;
  if (related && target.contains(related)) return;
  target.classList.remove('workspace-drop-target');
});

workspaceFileList?.addEventListener('drop', event => {
  void _handleWorkspaceDropMove(event);
});
