// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// History delete/clear confirmations and shared loading state.
import { historyLoadOverlay as importedHistoryLoadOverlay } from '../../core/dom.js';
import { getAppState as importedGetAppState } from '../../core/state.js';
import { showToast as importedShowToast } from '../../core/utils.js';
import {
  activeTeamScopeCan as importedActiveTeamScopeCan,
  teamScopeDeniedMessage as importedTeamScopeDeniedMessage,
} from '../team_scope.js';
import { showConfirm as importedShowConfirm } from '../../ui/ui_confirm.js';
import {
  _getStarred as importedGetStarred,
  _saveStarred as importedSaveStarred,
} from './history_actions.js';
import {
  refreshHistoryPanel as importedRefreshHistoryPanel,
  renderHistory as importedRenderHistory,
} from '../../history.js';
import {
  apiFetch as importedRuntimeApiFetch,
  hasRuntimeHandler as importedHasRuntimeHandler,
} from '../../runtime_bridge.js';
import { bindDisclosure as importedBindDisclosure } from '../../ui/ui_disclosure.js';
import { atlasRunCleanupCopy, cleanupSampleDetails } from '../../ui/cleanup_reasons.js';

let _pendingHistActionFallback = null;
const HISTORY_MUTATIONS_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

function _historyMutationState() {
  if (typeof importedGetAppState === 'function') return importedGetAppState();
  if (typeof HISTORY_MUTATIONS_GLOBAL.APP_STATE_API?.getState === 'function') return HISTORY_MUTATIONS_GLOBAL.APP_STATE_API.getState();
  return HISTORY_MUTATIONS_GLOBAL.APP_STATE || null;
}

function _historyPendingAction() {
  const state = _historyMutationState();
  if (state) return state.pendingHistAction || null;
  return _pendingHistActionFallback;
}

function _historySetPendingAction(action) {
  const state = _historyMutationState();
  if (state) state.pendingHistAction = action || null;
  _pendingHistActionFallback = action || null;
  return action || null;
}

function _historyMutationCmdHistory() {
  const state = _historyMutationState();
  if (state && Array.isArray(state.cmdHistory)) return state.cmdHistory;
  return [];
}

function _historyMutationSetCmdHistory(next) {
  const value = Array.isArray(next) ? next : [];
  const state = _historyMutationState();
  if (state) state.cmdHistory = value;
  return value;
}

function _historyMutationRecentPreviewHistory() {
  const state = _historyMutationState();
  if (state && Array.isArray(state.recentPreviewHistory)) return state.recentPreviewHistory;
  return [];
}

function _historyMutationSetRecentPreviewHistory(next) {
  const value = Array.isArray(next) ? next : [];
  const state = _historyMutationState();
  if (state) state.recentPreviewHistory = value;
  return value;
}

function _historyMutationGetStarred() {
  const getStarred = (typeof importedGetStarred !== 'undefined' && importedGetStarred)
    || HISTORY_MUTATIONS_GLOBAL._getStarred;
  return typeof getStarred === 'function' ? getStarred() : new Set();
}

function _historyMutationSaveStarred(starred) {
  const saveStarred = (typeof importedSaveStarred !== 'undefined' && importedSaveStarred)
    || HISTORY_MUTATIONS_GLOBAL._saveStarred;
  if (typeof saveStarred === 'function') saveStarred(starred);
}

function _historyMutationLoadOverlay() {
  return (typeof importedHistoryLoadOverlay !== 'undefined' && importedHistoryLoadOverlay)
    || HISTORY_MUTATIONS_GLOBAL.historyLoadOverlay
    || null;
}

function _historyActiveScopeCan(capability) {
  const can = (typeof importedActiveTeamScopeCan !== 'undefined' && importedActiveTeamScopeCan)
    || null;
  return typeof can === 'function' ? can(capability) : true;
}

function _historyScopeDeniedMessage(action) {
  const denied = (typeof importedTeamScopeDeniedMessage !== 'undefined' && importedTeamScopeDeniedMessage)
    || null;
  return typeof denied === 'function'
    ? denied(action)
    : `View-only team members can't ${action}. Switch to Personal or ask for operator access.`;
}

function _historyMutationShowToast(message, tone = 'success') {
  const toast = (typeof importedShowToast !== 'undefined' && importedShowToast)
    || HISTORY_MUTATIONS_GLOBAL.showToast
    || null;
  if (typeof toast === 'function') toast(message, tone);
}

function _historyMutationShowConfirm(options) {
  const confirm = (typeof importedShowConfirm !== 'undefined' && importedShowConfirm)
    || HISTORY_MUTATIONS_GLOBAL.showConfirm
    || null;
  return typeof confirm === 'function' ? confirm(options) : Promise.resolve(null);
}

function _historyMutationRenderHistory() {
  const render = (typeof importedRenderHistory !== 'undefined' && importedRenderHistory)
    || HISTORY_MUTATIONS_GLOBAL.renderHistory;
  if (typeof render === 'function') render();
}

function _historyMutationRefreshHistoryPanel() {
  const refresh = (typeof importedRefreshHistoryPanel !== 'undefined' && importedRefreshHistoryPanel)
    || HISTORY_MUTATIONS_GLOBAL.refreshHistoryPanel;
  if (typeof refresh === 'function') refresh();
}

function _historyMutationApiFetch(...args) {
  const fetcher = (
    typeof importedHasRuntimeHandler === 'function'
    && importedHasRuntimeHandler('apiFetch')
    && typeof importedRuntimeApiFetch === 'function'
      ? importedRuntimeApiFetch
      : null
  ) || HISTORY_MUTATIONS_GLOBAL.apiFetch;
  return typeof fetcher === 'function' ? fetcher(...args) : Promise.reject(new Error('apiFetch unavailable'));
}

function _historyCanManageHistory() {
  return _historyActiveScopeCan('manage_history');
}

function _historyShowPermissionDenied(action = 'delete team history') {
  _historyMutationShowToast(_historyScopeDeniedMessage(action), 'error');
}

async function _historyMutationError(resp, fallback) {
  let message = fallback;
  try {
    const data = typeof resp.json === 'function' ? await resp.json() : {};
    if (data && data.error === 'team_forbidden') {
      message = _historyScopeDeniedMessage('delete team history');
    } else if (data && typeof data.message === 'string' && data.message.trim()) {
      message = data.message.trim();
    } else if (data && typeof data.error === 'string' && data.error.trim()) {
      message = data.error.trim();
    }
  } catch (_) {}
  const err = new Error(message || fallback);
  err.userFacing = true;
  return err;
}

function _buildHistoryAtlasCleanupContent(cleanup) {
  const copy = atlasRunCleanupCopy(cleanup);
  if (!copy.hasDisposable && !copy.hasKept && !copy.notEligibleNote) return null;
  const wrap = document.createElement('div');
  wrap.className = 'modal-inline-field';
  const fieldset = document.createElement('div');
  fieldset.className = 'form-fieldset';
  if (copy.hasDisposable) {
    const label = document.createElement('label');
    label.className = 'form-check';
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = false;
    checkbox.dataset.historyAtlasCleanup = '1';
    const text = document.createElement('span');
    text.textContent = copy.disposableLabel;
    label.append(checkbox, text);
    const note = document.createElement('div');
    note.className = 'cleanup-reason-note history-bulk-note';
    note.textContent = copy.disposableNote;
    fieldset.append(label, note);
  }
  if (copy.hasKept) {
    const curatedLabel = document.createElement('label');
    curatedLabel.className = 'form-check';
    const curatedCheckbox = document.createElement('input');
    curatedCheckbox.type = 'checkbox';
    curatedCheckbox.checked = false;
    curatedCheckbox.dataset.historyAtlasCleanupCurated = '1';
    const curatedText = document.createElement('span');
    curatedText.textContent = copy.keptLabel;
    curatedLabel.append(curatedCheckbox, curatedText);
    const curatedNote = document.createElement('div');
    curatedNote.className = 'cleanup-reason-note history-bulk-note';
    curatedNote.textContent = copy.keptNote;
    fieldset.append(curatedLabel, curatedNote);
  }
  if (copy.notEligibleNote) {
    const excludedNote = document.createElement('div');
    excludedNote.className = 'cleanup-reason-note history-bulk-note';
    excludedNote.textContent = copy.notEligibleNote;
    fieldset.appendChild(excludedNote);
  }
  const samples = cleanupSampleDetails(cleanup?.cleanup_reasons, {
    bindDisclosure: importedBindDisclosure,
  });
  if (samples) fieldset.appendChild(samples);
  wrap.appendChild(fieldset);
  return wrap;
}

async function _loadHistoryAtlasCleanup(runId) {
  try {
    const resp = await _historyMutationApiFetch(`/history/${encodeURIComponent(runId)}/atlas-cleanup-preview`, { cache: 'no-store' });
    if (!resp.ok) return null;
    const data = await resp.json().catch(() => ({}));
    return data.cleanup || null;
  } catch (_) {
    return null;
  }
}

function confirmHistAction(type, id, command, itemType = 'run') {
  if ((type === 'delete' || type === 'clear') && !_historyCanManageHistory()) {
    _historyShowPermissionDenied('delete team history');
    return;
  }
  _historySetPendingAction({ type, id, command, itemType });
  const runDelete = type === 'delete' && itemType !== 'snapshot' && id;
  const isBulk = type === 'clear';
  const buildBody = (cleanup) => (isBulk
    ? { text: 'Delete all runs and snapshots?', note: 'This cannot be undone.' }
    : itemType === 'snapshot'
      ? { text: 'Remove this snapshot from history?', note: 'This cannot be undone.' }
      : {
          text: 'Remove this run from history?',
          note: cleanup?.has_cleanup
            ? 'The run transcript will be removed. Atlas cleanup is optional.'
            : 'This cannot be undone.',
        });
  const actions = isBulk
    ? [
        { id: 'cancel', label: 'Cancel', role: 'cancel' },
        { id: 'nonfav', label: 'Delete Non-Favorites', role: 'secondary', tone: 'warning' },
        { id: 'all',    label: 'Delete all', role: 'destructive', tone: 'warning' },
      ]
    : [
        { id: 'cancel', label: 'Cancel', role: 'cancel' },
        { id: 'one',    label: 'Delete', role: 'destructive', tone: 'warning' },
      ];
  const showDeleteConfirm = (cleanup) => {
    const content = runDelete ? _buildHistoryAtlasCleanupContent(cleanup) : null;
    return _historyMutationShowConfirm({
      body: buildBody(cleanup),
      content,
      tone: 'warning',
      actions,
      refocusOnResolve: false,
    }).then((choice) => {
      if (!choice || choice === 'cancel') {
        _historySetPendingAction(null);
        return;
      }
      const pending = _historyPendingAction();
      if (pending && content) {
        pending.pruneCuratedAtlas = !!content.querySelector('[data-history-atlas-cleanup-curated]')?.checked;
        pending.pruneAtlas = !!content.querySelector('[data-history-atlas-cleanup]')?.checked
          || pending.pruneCuratedAtlas;
        _historySetPendingAction(pending);
      }
      if (choice === 'nonfav') executeHistAction('clear-nonfav');
      else if (choice === 'all') executeHistAction();
      else if (choice === 'one') executeHistAction('delete');
    });
  };
  if (runDelete) {
    _loadHistoryAtlasCleanup(id).then(showDeleteConfirm);
  } else {
    showDeleteConfirm(null);
  }
}

function executeHistAction(type) {
  const pending = _historyPendingAction();
  const action  = type || (pending && pending.type);
  const id      = pending && pending.id;
  const command = pending && pending.command;
  const itemType = pending && pending.itemType;
  const pruneAtlas = !!(pending && pending.pruneAtlas);
  const pruneCuratedAtlas = !!(pending && pending.pruneCuratedAtlas);
  _historySetPendingAction(null);
  if (action === 'delete') {
    const params = new URLSearchParams();
    if (pruneAtlas) params.set('prune_atlas', '1');
    if (pruneCuratedAtlas) params.set('prune_curated_atlas', '1');
    const query = params.toString();
    const deleteUrl = itemType === 'snapshot'
      ? `/share/${id}`
      : `/history/${id}${query ? `?${query}` : ''}`;
    _historyMutationApiFetch(deleteUrl, { method: 'DELETE' }).then(async (resp) => {
      if (!resp.ok) throw await _historyMutationError(resp, 'Failed to delete run');
      if (itemType === 'snapshot') {
        _historyMutationRefreshHistoryPanel();
        return;
      }
      const s = _historyMutationGetStarred();
      if (s.has(command)) {
        s.delete(command);
        _historyMutationSaveStarred(s);
        _historyMutationApiFetch('/session/starred', {
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ command }),
        }).catch(() => {});
      }
      _historyMutationSetCmdHistory(_historyMutationCmdHistory().filter(c => c !== command));
      _historyMutationSetRecentPreviewHistory(
        _historyMutationRecentPreviewHistory().filter(c => c !== command),
      );
      _historyMutationRenderHistory();
      _historyMutationRefreshHistoryPanel();
    }).catch((err) => _historyMutationShowToast(err.userFacing ? err.message : 'Failed to delete run', 'error'));
  } else if (action === 'clear-nonfav') {
    _historyMutationApiFetch('/history?type=runs')
      .then(r => r.json())
      .then(data => {
        const starred   = _historyMutationGetStarred();
        const toDelete  = data.runs.filter(r => !starred.has(r.command));
        const deleteCmds = new Set(toDelete.map(r => r.command));
        _historyMutationSetCmdHistory(_historyMutationCmdHistory().filter(c => !deleteCmds.has(c)));
        _historyMutationSetRecentPreviewHistory(
          _historyMutationRecentPreviewHistory().filter(c => !deleteCmds.has(c)),
        );
        _historyMutationRenderHistory();
        return Promise.all(toDelete.map(async (r) => {
          const resp = await _historyMutationApiFetch(`/history/${r.id}`, { method: 'DELETE' });
          if (!resp.ok) throw await _historyMutationError(resp, 'Failed to clear history');
          return resp;
        }));
      })
      .then(() => _historyMutationRefreshHistoryPanel())
      .catch((err) => _historyMutationShowToast(err.userFacing ? err.message : 'Failed to clear history', 'error'));
  } else {
    _historyMutationApiFetch('/history', { method: 'DELETE' }).then(async (resp) => {
      if (!resp.ok) throw await _historyMutationError(resp, 'Failed to clear history');
      _historyMutationSaveStarred(new Set());
      _historyMutationApiFetch('/session/starred', { method: 'DELETE' }).catch(() => {});
      _historyMutationSetCmdHistory([]);
      _historyMutationSetRecentPreviewHistory([]);
      _historyMutationRenderHistory();
      _historyMutationRefreshHistoryPanel();
    }).catch((err) => _historyMutationShowToast(err.userFacing ? err.message : 'Failed to clear history', 'error'));
  }
}

function _setHistoryLoadState(loading) {
  if (!_historyMutationLoadOverlay()) return;
  if (loading && typeof HISTORY_MUTATIONS_GLOBAL.showHistoryLoadOverlay === 'function') {
    HISTORY_MUTATIONS_GLOBAL.showHistoryLoadOverlay();
  } else if (!loading && typeof HISTORY_MUTATIONS_GLOBAL.hideHistoryLoadOverlay === 'function') {
    HISTORY_MUTATIONS_GLOBAL.hideHistoryLoadOverlay();
  }
}

if (typeof window !== 'undefined') {
}

export {
  _buildHistoryAtlasCleanupContent,
  _historyActiveScopeCan,
  _historyCanManageHistory,
  _historyMutationError,
  _historyScopeDeniedMessage,
  _historyShowPermissionDenied,
  _loadHistoryAtlasCleanup,
  _setHistoryLoadState,
  confirmHistAction,
  executeHistAction,
};
