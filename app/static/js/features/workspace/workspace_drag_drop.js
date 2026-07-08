import { workspaceFileList as importedWorkspaceFileList } from '../../core/dom.js';
import { showConfirm as importedShowConfirm } from '../../ui/ui_confirm.js';

let _workspaceDragPath = '';
let _workspaceDragKind = '';

function _workspaceDragApi() {
  return typeof window !== 'undefined' ? window : globalThis;
}

function _workspaceDragFileListRef() {
  const api = _workspaceDragApi();
  return api.workspaceFileList
    || (typeof importedWorkspaceFileList !== 'undefined' && importedWorkspaceFileList)
    || null;
}

function _workspaceDragShowConfirm() {
  return (typeof importedShowConfirm !== 'undefined' && importedShowConfirm)
    || (typeof _workspaceDragApi().showConfirm === 'function' ? _workspaceDragApi().showConfirm : null);
}

function _workspaceDragCanWrite(action) {
  const api = _workspaceDragApi();
  const state = api.DarklabWorkspaceState || {};
  const canWrite = typeof state.canWrite === 'function'
    ? state.canWrite
    : (typeof api.workspaceCanWrite === 'function' ? api.workspaceCanWrite : null);
  return typeof canWrite !== 'function' || canWrite(action, { toast: true });
}

function _workspaceDragSourceFromEvent(event) {
  const list = _workspaceDragFileListRef();
  const row = event.target && event.target.closest ? event.target.closest('.workspace-file-row[draggable="true"]') : null;
  return row && list && list.contains(row) ? row : null;
}

function _workspaceDropTargetFromEvent(event) {
  const list = _workspaceDragFileListRef();
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
  const state = api.DarklabWorkspaceState || {};
  if (!_workspaceDragCanWrite('move Files')) return;
  const target = _workspaceDropTargetFromEvent(event);
  if (!target || !_workspaceCanDropOnFolder(_workspaceDragPath, target.dataset.path || '')) return;
  event.preventDefault();
  target.classList.remove('workspace-drop-target');
  const destination = target.dataset.path || '';
  const source = _workspaceDragPath;
  const kind = _workspaceDragKind === 'folder' ? 'folder' : 'file';
  if (!source) return;
  const confirmMove = _workspaceDragShowConfirm();
  const confirmed = typeof confirmMove === 'function'
    ? await confirmMove({
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
    const movePath = typeof state.movePath === 'function'
      ? state.movePath
      : api.moveWorkspacePath;
    if (typeof movePath === 'function') await movePath(source, destination);
  } catch (err) {
    const message = typeof state.errorMessage === 'function'
      ? state.errorMessage(err, 'Unable to move item')
      : 'Unable to move item';
    if (typeof api._showWorkspaceToast === 'function') api._showWorkspaceToast(message, 'error');
  }
}

const _workspaceDragFileList = _workspaceDragFileListRef();

_workspaceDragFileList?.addEventListener('dragstart', event => {
  if (!_workspaceDragCanWrite('move Files')) {
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
}

export {
  _handleWorkspaceDropMove,
  _workspaceDragCanWrite,
  _workspaceCanDropOnFolder,
  _workspaceDropTargetFromEvent,
  _workspaceDragSourceFromEvent,
};
