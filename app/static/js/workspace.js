// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// ── Session workspace UI ──
// App-mediated file helper only. Output sinks call this boundary; it does not
// expose shell navigation, raw redirection, or arbitrary host paths.

import {
  workspaceBreadcrumbs,
  workspaceCancelEditBtn,
  workspaceCloseViewerBtn,
  workspaceEditor,
  workspaceEditorOverlay,
  workspaceEditorTitle,
  workspaceFileUsage,
  workspaceFileUsageFill,
  workspaceFileList,
  workspaceLabelsInput,
  workspaceMessage,
  workspaceModal,
  workspaceNewBtn,
  workspaceNewFolderBtn,
  workspaceNotesInput,
  workspaceOverlay,
  workspacePathInput,
  workspaceRefreshBtn,
  workspaceResultSummary,
  workspaceReadOnlyStatus,
  workspaceSaveBtn,
  workspaceScopeBadge,
  workspaceSearchInput,
  workspaceSortSelect,
  workspaceStorageUsage,
  workspaceStorageUsageFill,
  workspaceSummary,
  workspaceTextInput,
  workspaceUpBtn,
  workspaceViewer,
  workspaceViewerAutoRefreshLabel,
  workspaceViewerAutoRefreshToggle,
  workspaceViewerControls,
  workspaceViewerOverlay,
  workspaceViewerRefreshBtn,
  workspaceViewerText,
  workspaceViewerTitle,
} from './core/dom.js';
import { downloadUrlAsAttachment, showToast } from './core/utils.js';
import { APP_CONFIG } from './core/config.js';
import { DarklabWorkspaceCore as importedWorkspaceCore } from './core/workspace_core.js';
import { setRuntimeHandlers as importedSetRuntimeHandlers } from './runtime_bridge.js';
import { apiFetch as importedApiFetch } from './session.js';
import { activeTeamScopeCan, getActiveTeamId, teamScopeDeniedMessage } from './features/team_scope.js';
import {
  getWorkspaceAutocompleteDirectoryHints as importedGetWorkspaceAutocompleteDirectoryHints,
  getWorkspaceAutocompleteFileHints as importedGetWorkspaceAutocompleteFileHints,
  getWorkspaceDirectoryEntries as importedGetWorkspaceDirectoryEntries,
  refreshWorkspaceFileCache as importedRefreshWorkspaceFileCache,
} from './features/workspace/workspace_autocomplete_cache.js';
import {
  DarklabWorkspaceViewerFormats as importedWorkspaceViewerFormats,
  viewerPayload as importedViewerPayload,
  viewerRawText as importedViewerRawText,
} from './features/workspace/workspace_viewer_formats.js';
import { createTextSearchController } from './search.js';
import { closeMajorOverlays as importedCloseMajorOverlays } from './ui/overlay_actions_bridge.js';
import { setWorkspaceHandlers as importedSetWorkspaceHandlers } from './workspace_bridge.js';
import { DarklabEntityMetadata as importedEntityMetadata } from './ui/ui_entity_metadata.js';
import {
  applyMobileTextInputDefaults,
  blurVisibleComposerInputIfMobile,
  focusElement,
  hideWorkspaceOverlay,
  markInteractionSurfaceReady,
  refocusComposerAfterAction,
  showWorkspaceOverlay,
  syncAppSelect,
} from './ui/ui_helpers.js';
import { showConfirm } from './ui/ui_confirm.js';

let _workspaceFiles = [];
let _workspaceDirs = [];
let _workspaceLimits = {};
let _workspaceLoaded = false;
let _workspaceCurrentDir = '';
let _workspaceCurrentScopeKey = 'personal';
let _workspaceFilterQuery = '';
let _workspaceSortKey = 'name';
let _workspaceOpenActionMenu = null;
const _workspaceDirByScope = new Map();
let _workspaceFilesLoadPromise = null;
let _workspaceOwner = {
  scope: 'personal',
  team_id: '',
  label: 'Personal',
  read_only: false,
  read_only_reason: '',
};

function _workspaceGlobal() {
  return typeof window !== 'undefined' ? window : globalThis;
}

function _workspaceApiFetch() {
  if (typeof importedApiFetch !== 'function') throw new Error('apiFetch is not available');
  return importedApiFetch;
}

function _publishWorkspaceState() {
  const global = _workspaceGlobal();
  if (!global || global.DarklabWorkspaceState) return;
  Object.defineProperties(global, {
    DarklabWorkspaceState: {
      configurable: true,
      value: {},
    },
  });
  Object.defineProperties(global.DarklabWorkspaceState, {
    files: {
      configurable: true,
      get: () => _workspaceFiles,
      set: value => { _workspaceFiles = Array.isArray(value) ? value : []; },
    },
    dirs: {
      configurable: true,
      get: () => _workspaceDirs,
      set: value => { _workspaceDirs = Array.isArray(value) ? value : []; },
    },
    limits: {
      configurable: true,
      get: () => _workspaceLimits,
      set: value => { _workspaceLimits = value && typeof value === 'object' ? value : {}; },
    },
    loaded: {
      configurable: true,
      get: () => _workspaceLoaded,
      set: value => { _workspaceLoaded = value === true; },
    },
    owner: {
      configurable: true,
      get: () => _workspaceOwner,
      set: value => { _workspaceOwner = value && typeof value === 'object' ? value : _workspaceOwner; },
    },
    currentDir: {
      configurable: true,
      get: () => _workspaceCurrentDir,
      set: value => { _workspaceCurrentDir = _normalizeWorkspaceDir(value); },
    },
    currentScopeKey: {
      configurable: true,
      get: () => _workspaceCurrentScopeKey,
      set: value => { _workspaceCurrentScopeKey = String(value || 'personal'); },
    },
    apiFetch: {
      configurable: true,
      value: (...args) => _workspaceApiFetch()(...args),
    },
    activeScopeKeyFromOwner: {
      configurable: true,
      value: _workspaceActiveScopeKeyFromOwner,
    },
    formatBytes: {
      configurable: true,
      value: _formatWorkspaceBytes,
    },
    errorMessage: {
      configurable: true,
      value: _workspaceErrorMessage,
    },
    getDirectoryEntries: {
      configurable: true,
      value: _workspaceDirectEntries,
    },
    isEnabled: {
      configurable: true,
      value: isWorkspaceEnabled,
    },
    canWrite: {
      configurable: true,
      value: workspaceCanWrite,
    },
    loadFilesPayload: {
      configurable: true,
      value: (...args) => loadWorkspaceFilesPayload(...args),
    },
    movePath: {
      configurable: true,
      value: moveWorkspacePath,
    },
    ownerFromPayload: {
      configurable: true,
      value: _workspaceOwnerFromPayload,
    },
    parseJson: {
      configurable: true,
      value: _workspaceJson,
    },
    renderFiles: {
      configurable: true,
      value: renderWorkspaceFiles,
    },
    resetForScopeChange: {
      configurable: true,
      value: _workspaceResetForScopeChange,
    },
  });
}

_publishWorkspaceState();

let _workspaceViewedPath = '';
let _workspaceViewerPayloadCache = null;
let _workspaceViewerSearchController = null;
let _workspaceViewerRefreshTimer = null;
let _workspaceViewerAutoRefreshSeconds = 0;
let _workspaceViewerRefreshSpinTimer = null;
let _workspaceViewerRefreshInFlight = false;
let _workspaceViewerAutoRefreshEnabled = false;
let _workspaceViewedSize = null;
function WorkspaceCore() {
  return (typeof importedWorkspaceCore !== 'undefined' && importedWorkspaceCore)
    || null;
}

function _workspaceEntityMetadataClient() {
  return (typeof importedEntityMetadata !== 'undefined' && importedEntityMetadata) || {};
}

function _workspaceViewerFormats() {
  return (typeof importedWorkspaceViewerFormats !== 'undefined' && importedWorkspaceViewerFormats) || {};
}

function _workspaceFileCacheApi() {
  return {
    getDirectoryEntries: (typeof importedGetWorkspaceDirectoryEntries !== 'undefined' && importedGetWorkspaceDirectoryEntries)
      || null,
    getDirectoryHints: (typeof importedGetWorkspaceAutocompleteDirectoryHints !== 'undefined' && importedGetWorkspaceAutocompleteDirectoryHints)
      || null,
    getFileHints: (typeof importedGetWorkspaceAutocompleteFileHints !== 'undefined' && importedGetWorkspaceAutocompleteFileHints)
      || null,
    refresh: (typeof importedRefreshWorkspaceFileCache !== 'undefined' && importedRefreshWorkspaceFileCache)
      || null,
  };
}

const WORKSPACE_PREVIEW_LINE_LIMIT = 10000;
const WORKSPACE_PREVIEW_TABLE_LIMIT = 250;
const WORKSPACE_VIEWER_AUTO_REFRESH_MS = 5000;
const WORKSPACE_VIEWER_AUTO_REFRESH_MAX_BYTES = 1024 * 1024;
const WORKSPACE_VIEWER_BOTTOM_THRESHOLD = 24;
const WORKSPACE_VIEWER_REFRESH_SPINNER_MS = 650;
const WORKSPACE_VIEWER_SEARCH_DELAY_MS = 250;
const WORKSPACE_VIEWER_LARGE_SEARCH_DELAY_MS = 600;
const WORKSPACE_VIEWER_LARGE_SEARCH_LINE_THRESHOLD = 2000;
const WORKSPACE_VIEWER_LARGE_SEARCH_CHAR_THRESHOLD = 500000;
const WORKSPACE_VIEWER_LARGE_SEARCH_SIZE_THRESHOLD = 1024 * 1024;
const WORKSPACE_VIEWER_LARGE_SEARCH_MIN_CHARS = 3;
const WORKSPACE_MANAGE_CAPABILITY = 'manage_workspace_files';

function isWorkspaceEnabled() {
  return !!(typeof APP_CONFIG !== 'undefined' && APP_CONFIG && APP_CONFIG.workspace_enabled === true);
}

function _formatWorkspaceBytes(bytes) {
  return WorkspaceCore().formatBytes(bytes);
}

function _workspaceErrorMessage(err, fallback = 'Files request failed') {
  if (err && typeof err.message === 'string' && err.message.trim()) return err.message.trim();
  return fallback;
}

function _workspaceActiveScopeKeyFromOwner(owner = _workspaceOwner) {
  const scope = String(owner?.scope || '').trim();
  const teamId = String(owner?.team_id || '').trim();
  if (scope === 'team' && teamId) return `team:${teamId}`;
  if (typeof getActiveTeamId === 'function') {
    const activeTeamId = String(getActiveTeamId() || '').trim();
    if (activeTeamId) return `team:${activeTeamId}`;
  }
  return 'personal';
}

function _workspaceReadOnlyReason(action = 'change Files') {
  if (_workspaceOwner.read_only_reason) return _workspaceOwner.read_only_reason;
  if (_workspaceOwner.scope === 'team' && typeof teamScopeDeniedMessage === 'function') {
    return teamScopeDeniedMessage(action);
  }
  return `Files are read-only right now, so you can't ${action}.`;
}

function isWorkspaceReadOnly() {
  if (_workspaceOwner.read_only) return true;
  if (_workspaceOwner.scope === 'team' && typeof activeTeamScopeCan === 'function') {
    return !activeTeamScopeCan(WORKSPACE_MANAGE_CAPABILITY);
  }
  return false;
}

function workspaceCanWrite(action = 'change Files', { toast = false } = {}) {
  if (!isWorkspaceReadOnly()) return true;
  if (toast) _showWorkspaceToast(_workspaceReadOnlyReason(action), 'error');
  return false;
}

function _workspaceOwnerFromPayload(payload = {}) {
  const owner = payload.owner && typeof payload.owner === 'object' ? payload.owner : {};
  const scope = String(owner.scope || '').trim() === 'team' ? 'team' : 'personal';
  return {
    scope,
    owner_id: String(owner.owner_id || ''),
    team_id: scope === 'team' ? String(owner.team_id || '') : '',
    label: String(owner.label || (scope === 'team' ? 'Team' : 'Personal')),
    team_status: String(owner.team_status || ''),
    role: String(owner.role || ''),
    read_only: owner.read_only === true,
    read_only_reason: String(owner.read_only_reason || owner.write_denial || ''),
  };
}

function _workspaceSetCurrentDir(path = '') {
  _workspaceCurrentDir = _normalizeWorkspaceDir(path);
  _workspaceDirByScope.set(_workspaceCurrentScopeKey, _workspaceCurrentDir);
}

function _workspaceApplyOwner(owner = _workspaceOwner) {
  const previousScopeKey = _workspaceCurrentScopeKey;
  const nextScopeKey = _workspaceActiveScopeKeyFromOwner(owner);
  if (previousScopeKey && previousScopeKey !== nextScopeKey) {
    _workspaceDirByScope.set(previousScopeKey, _normalizeWorkspaceDir(_workspaceCurrentDir));
    _workspaceCurrentDir = _workspaceDirByScope.get(nextScopeKey) || '';
  }
  _workspaceCurrentScopeKey = nextScopeKey;
  _workspaceOwner = owner;
}

function _workspaceOwnerLabel() {
  if (_workspaceOwner.scope !== 'team') return 'Personal';
  return _workspaceOwner.label || 'Team';
}

function _workspaceSyncWriteControls() {
  const readOnly = isWorkspaceReadOnly();
  const title = readOnly ? _workspaceReadOnlyReason('change Files') : '';
  if (workspaceScopeBadge) {
    workspaceScopeBadge.classList.toggle('is-read-only', readOnly);
    workspaceScopeBadge.title = readOnly
      ? title
      : `Active Files scope: ${_workspaceOwnerLabel()}`;
  }
  if (workspaceReadOnlyStatus) {
    workspaceReadOnlyStatus.classList.toggle('u-hidden', !readOnly);
    workspaceReadOnlyStatus.title = title;
  }
  [workspaceNewBtn, workspaceNewFolderBtn].forEach(btn => {
    if (!btn) return;
    btn.disabled = readOnly;
    btn.setAttribute('aria-disabled', readOnly ? 'true' : 'false');
    if (title) btn.title = title;
    else btn.removeAttribute('title');
  });
  if (workspaceSaveBtn) {
    workspaceSaveBtn.disabled = readOnly;
    workspaceSaveBtn.setAttribute('aria-disabled', readOnly ? 'true' : 'false');
    if (title) workspaceSaveBtn.title = title;
    else workspaceSaveBtn.removeAttribute('title');
  }
  if (workspaceTextInput) workspaceTextInput.readOnly = readOnly;
  [workspaceLabelsInput, workspaceNotesInput].forEach(input => {
    if (!input) return;
    input.readOnly = readOnly;
    input.disabled = readOnly;
  });
  if (workspaceViewer) {
    workspaceViewer.querySelectorAll('[data-workspace-viewer-action="edit"], [data-workspace-viewer-action="delete"]').forEach(btn => {
      btn.disabled = readOnly;
      btn.setAttribute('aria-disabled', readOnly ? 'true' : 'false');
      if (title) btn.title = title;
      else btn.removeAttribute('title');
    });
  }
}

function _workspaceResetForScopeChange() {
  hideWorkspaceEditor();
  hideWorkspaceViewer();
  _workspaceResetBrowserControls();
  _workspaceLoaded = false;
  _workspaceFiles = [];
  _workspaceDirs = [];
}

async function _workspaceJson(resp) {
  let data = {};
  try {
    data = await resp.json();
  } catch (_) {
    data = {};
  }
  if (!resp.ok) {
    const message = data && typeof data.message === 'string' ? data.message.trim() : '';
    const error = data && typeof data.error === 'string' ? data.error.trim() : '';
    if (message) throw new Error(message);
    if (error === 'team_forbidden') throw new Error(_workspaceReadOnlyReason('change Files'));
    if (error === 'team_archived') throw new Error('Archived teams are read-only in Files.');
    throw new Error(error || `Files request failed (${resp.status})`);
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

function _workspaceViewerIsOpen() {
  return !!(
    workspaceViewer &&
    !workspaceViewer.classList.contains('u-hidden') &&
    (typeof workspaceViewerOverlay === 'undefined' || !workspaceViewerOverlay || !workspaceViewerOverlay.classList.contains('u-hidden'))
  );
}

function _workspaceViewerFileSize(path = '') {
  const target = String(path || '').split('/').filter(Boolean).join('/');
  const file = _workspaceFiles.find(item => String(item?.path || '').split('/').filter(Boolean).join('/') === target);
  const size = Number(file?.size);
  return Number.isFinite(size) ? size : null;
}

function _workspaceFileReadBlockedReason(path = '') {
  const maxFileBytes = Number(_workspaceLimits?.max_file_bytes);
  if (!(maxFileBytes > 0)) return '';
  const fileSize = _workspaceViewerFileSize(path);
  if (!(Number.isFinite(fileSize) && fileSize > maxFileBytes)) return '';
  return 'file exceeds workspace max file size';
}

function _workspaceFileByPath(path = '') {
  const target = String(path || '').split('/').filter(Boolean).join('/');
  if (!target) return null;
  return _workspaceFiles.find(item => String(item?.path || '').split('/').filter(Boolean).join('/') === target) || null;
}

function _workspaceLabelValues(file) {
  const labels = file && Array.isArray(file.labels) ? file.labels : [];
  return labels
    .map(label => String(label && typeof label === 'object' ? label.label : label || '').trim())
    .filter(Boolean);
}

function _workspaceNoteBody(file) {
  const note = file && file.note && typeof file.note === 'object' ? file.note : null;
  return note ? String(note.body || '').trim() : '';
}

function _workspaceMetadataOptionsForPath(path = '', fallback = {}) {
  const file = fallback && (Array.isArray(fallback.labels) || fallback.note) ? fallback : _workspaceFileByPath(path);
  return {
    labels: _workspaceLabelValues(file),
    noteBody: _workspaceNoteBody(file),
  };
}

function _workspaceMetadataChips(file) {
  const chips = _workspaceLabelValues(file).map(label => ({ label, kind: 'label' }));
  if (_workspaceNoteBody(file)) chips.push({ label: 'note', kind: 'note' });
  return chips;
}

async function _syncWorkspaceFileMetadata(path, { labels = [], noteBody = '' } = {}) {
  const metadataClient = _workspaceEntityMetadataClient();
  await metadataClient.syncEntityLabels('workspace_file', path, Array.isArray(labels) ? labels : []);
  await metadataClient.syncEntityNote('workspace_file', path, noteBody);
}

function _workspaceAutoRefreshDisabledReason() {
  if (Number.isFinite(_workspaceViewedSize) && _workspaceViewedSize > WORKSPACE_VIEWER_AUTO_REFRESH_MAX_BYTES) {
    return 'Auto-refresh is disabled for files larger than 1 MB to avoid reformatting large previews while browsing.';
  }
  return '';
}

function _workspaceViewerShouldFollow() {
  if (!workspaceViewerText) return true;
  const maxScrollTop = Math.max(0, workspaceViewerText.scrollHeight - workspaceViewerText.clientHeight);
  if (maxScrollTop <= WORKSPACE_VIEWER_BOTTOM_THRESHOLD) return true;
  return workspaceViewerText.scrollTop >= maxScrollTop - WORKSPACE_VIEWER_BOTTOM_THRESHOLD;
}

function _workspaceViewerRestoreScroll({ follow = true, scrollTop = 0 } = {}) {
  if (!workspaceViewerText) return;
  if (follow) {
    workspaceViewerText.scrollTop = Math.max(0, workspaceViewerText.scrollHeight - workspaceViewerText.clientHeight);
    return;
  }
  workspaceViewerText.scrollTop = Math.max(0, Number(scrollTop) || 0);
}

function _workspaceStopViewerAutoRefresh() {
  if (_workspaceViewerRefreshTimer) {
    clearInterval(_workspaceViewerRefreshTimer);
    _workspaceViewerRefreshTimer = null;
  }
  _workspaceViewerAutoRefreshSeconds = 0;
}

function _workspaceSyncViewerAutoRefreshToggle() {
  if (typeof workspaceViewerAutoRefreshToggle === 'undefined' || !workspaceViewerAutoRefreshToggle) return;
  const disabledReason = _workspaceAutoRefreshDisabledReason();
  if (disabledReason && _workspaceViewerAutoRefreshEnabled) {
    _workspaceViewerAutoRefreshEnabled = false;
    _workspaceStopViewerAutoRefresh();
  }
  workspaceViewerAutoRefreshToggle.setAttribute('aria-disabled', disabledReason ? 'true' : 'false');
  workspaceViewerAutoRefreshToggle.setAttribute('aria-pressed', _workspaceViewerAutoRefreshEnabled ? 'true' : 'false');
  workspaceViewerAutoRefreshToggle.title = disabledReason || (_workspaceViewerAutoRefreshEnabled
    ? 'Disable viewer auto refresh'
    : 'Enable viewer auto refresh');
  const label = typeof workspaceViewerAutoRefreshLabel !== 'undefined' && workspaceViewerAutoRefreshLabel
    ? workspaceViewerAutoRefreshLabel
    : workspaceViewerAutoRefreshToggle.querySelector('span:last-child');
  if (label) {
    label.textContent = _workspaceViewerAutoRefreshEnabled
      ? `Auto - ${Math.max(1, _workspaceViewerAutoRefreshSeconds || Math.ceil(WORKSPACE_VIEWER_AUTO_REFRESH_MS / 1000))}s`
      : 'Auto - off';
  }
}

function _workspaceStartViewerAutoRefresh() {
  _workspaceStopViewerAutoRefresh();
  _workspaceViewerAutoRefreshSeconds = Math.ceil(WORKSPACE_VIEWER_AUTO_REFRESH_MS / 1000);
  _workspaceSyncViewerAutoRefreshToggle();
  if (!_workspaceViewerAutoRefreshEnabled || !_workspaceViewedPath || !_workspaceViewerIsOpen()) return;
  _workspaceViewerRefreshTimer = setInterval(() => {
    if (!_workspaceViewerAutoRefreshEnabled || !_workspaceViewerIsOpen()) {
      _workspaceStopViewerAutoRefresh();
      _workspaceSyncViewerAutoRefreshToggle();
      return;
    }
    _workspaceViewerAutoRefreshSeconds -= 1;
    _workspaceSyncViewerAutoRefreshToggle();
    if (_workspaceViewerAutoRefreshSeconds > 0 || _workspaceViewerRefreshInFlight) return;
    refreshWorkspaceViewedFile({ auto: true })
      .catch(() => {})
      .finally(() => {
        if (!_workspaceViewerAutoRefreshEnabled || !_workspaceViewerIsOpen()) return;
        _workspaceViewerAutoRefreshSeconds = Math.ceil(WORKSPACE_VIEWER_AUTO_REFRESH_MS / 1000);
        _workspaceSyncViewerAutoRefreshToggle();
      });
  }, 1000);
}

function _workspaceFlashViewerRefreshSpinner(target = null) {
  const btn = target || (typeof workspaceViewerRefreshBtn !== 'undefined' ? workspaceViewerRefreshBtn : null);
  if (!btn) return;
  btn.classList.add('is-refreshing');
  if (_workspaceViewerRefreshSpinTimer) clearTimeout(_workspaceViewerRefreshSpinTimer);
  _workspaceViewerRefreshSpinTimer = setTimeout(() => {
    if (typeof workspaceViewerRefreshBtn !== 'undefined' && workspaceViewerRefreshBtn) {
      workspaceViewerRefreshBtn.classList.remove('is-refreshing');
    }
    if (typeof workspaceViewerAutoRefreshToggle !== 'undefined' && workspaceViewerAutoRefreshToggle) {
      workspaceViewerAutoRefreshToggle.classList.remove('is-refreshing');
    }
    _workspaceViewerRefreshSpinTimer = null;
  }, WORKSPACE_VIEWER_REFRESH_SPINNER_MS);
}

function _workspaceSetViewerRefreshBusy(isBusy = false) {
  if (typeof workspaceViewerRefreshBtn === 'undefined' || !workspaceViewerRefreshBtn) return;
  workspaceViewerRefreshBtn.disabled = !!isBusy;
  workspaceViewerRefreshBtn.setAttribute('aria-label', isBusy ? 'Refreshing viewed file' : 'Refresh viewed file');
  workspaceViewerRefreshBtn.title = isBusy ? 'Refreshing viewed file' : 'Refresh viewed file';
}

function hideWorkspaceEditor() {
  if (workspaceEditor) workspaceEditor.classList.add('u-hidden');
  if (workspacePathInput) {
    workspacePathInput.readOnly = false;
    workspacePathInput.classList.remove('workspace-path-readonly');
  }
  if (typeof workspaceLabelsInput !== 'undefined' && workspaceLabelsInput) workspaceLabelsInput.value = '';
  if (typeof workspaceNotesInput !== 'undefined' && workspaceNotesInput) workspaceNotesInput.value = '';
  if (typeof workspaceEditorOverlay !== 'undefined' && workspaceEditorOverlay) {
    workspaceEditorOverlay.classList.add('u-hidden');
    workspaceEditorOverlay.classList.remove('open');
  }
}

function hideWorkspaceViewer() {
  _workspaceStopViewerAutoRefresh();
  if (workspaceViewer) workspaceViewer.classList.add('u-hidden');
  if (typeof workspaceViewerOverlay !== 'undefined' && workspaceViewerOverlay) {
    workspaceViewerOverlay.classList.add('u-hidden');
    workspaceViewerOverlay.classList.remove('open');
    workspaceViewerOverlay.classList.remove('workspace-viewer-overlay-elevated');
  }
  if (_workspaceViewerRefreshSpinTimer) {
    clearTimeout(_workspaceViewerRefreshSpinTimer);
    _workspaceViewerRefreshSpinTimer = null;
  }
  if (typeof workspaceViewerRefreshBtn !== 'undefined' && workspaceViewerRefreshBtn) {
    workspaceViewerRefreshBtn.classList.remove('is-refreshing');
    _workspaceSetViewerRefreshBusy(false);
  }
  if (typeof workspaceViewerAutoRefreshToggle !== 'undefined' && workspaceViewerAutoRefreshToggle) {
    workspaceViewerAutoRefreshToggle.classList.remove('is-refreshing');
  }
  if (_workspaceViewerSearchController) _workspaceViewerSearchController.clear();
  _workspaceViewerSearchController = null;
  if (typeof workspaceViewerControls !== 'undefined' && workspaceViewerControls) {
    workspaceViewerControls.replaceChildren();
  }
  _workspaceViewedPath = '';
  _workspaceViewedSize = null;
  _workspaceViewerPayloadCache = null;
}

function showWorkspaceViewerLoading(path = '', message = 'Loading preview...') {
  hideWorkspaceEditor();
  _workspaceStopViewerAutoRefresh();
  _workspaceViewedPath = String(path || '').trim();
  _workspaceViewedSize = _workspaceViewerFileSize(path);
  _workspaceViewerPayloadCache = null;
  if (_workspaceViewerSearchController) _workspaceViewerSearchController.clear();
  _workspaceViewerSearchController = null;
  if (workspaceViewer) {
    workspaceViewer.querySelector('.workspace-viewer-mode-controls')?.remove();
    workspaceViewer.dataset.format = 'loading';
    workspaceViewer.dataset.viewMode = 'preview';
    workspaceViewer.classList.remove('u-hidden');
    workspaceViewer.scrollTop = 0;
  }
  if (workspaceViewerTitle) workspaceViewerTitle.textContent = path;
  if (typeof workspaceViewerControls !== 'undefined' && workspaceViewerControls) {
    workspaceViewerControls.replaceChildren();
  }
  _workspaceSyncViewerAutoRefreshToggle();
  if (workspaceViewerText) {
    workspaceViewerText.className = 'workspace-viewer-text nice-scroll';
    workspaceViewerText.replaceChildren();
    const notice = document.createElement('div');
    notice.className = 'workspace-preview-notice workspace-preview-loading';
    notice.textContent = message;
    workspaceViewerText.appendChild(notice);
    workspaceViewerText.scrollTop = 0;
  }
  if (typeof workspaceViewerOverlay !== 'undefined' && workspaceViewerOverlay) {
    workspaceViewerOverlay.classList.remove('u-hidden');
    workspaceViewerOverlay.classList.add('open');
  }
}

function _workspaceShowViewerBusy(message = 'Loading preview...') {
  if (_workspaceViewerSearchController) _workspaceViewerSearchController.clear();
  _workspaceViewerSearchController = null;
  if (typeof workspaceViewerControls !== 'undefined' && workspaceViewerControls) {
    workspaceViewerControls.replaceChildren();
  }
  if (!workspaceViewerText) return;
  workspaceViewerText.className = 'workspace-viewer-text nice-scroll';
  workspaceViewerText.replaceChildren();
  const notice = document.createElement('div');
  notice.className = 'workspace-preview-notice workspace-preview-loading';
  notice.textContent = message;
  workspaceViewerText.appendChild(notice);
  workspaceViewerText.scrollTop = 0;
}

function _workspaceAfterPaint() {
  return new Promise(resolve => {
    if (typeof window !== 'undefined' && typeof window.requestAnimationFrame === 'function') {
      window.requestAnimationFrame(() => setTimeout(resolve, 0));
      return;
    }
    setTimeout(resolve, 0);
  });
}

function _workspaceViewerPayload(path = '', text = '') {
  const formatter = (typeof importedViewerPayload !== 'undefined' && importedViewerPayload)
    || _workspaceViewerFormats().viewerPayload;
  return formatter(path, text, {
    tableLimit: WORKSPACE_PREVIEW_TABLE_LIMIT,
  });
}

function _workspaceViewerRawText(payload) {
  const formatter = (typeof importedViewerRawText !== 'undefined' && importedViewerRawText)
    || _workspaceViewerFormats().viewerRawText;
  return formatter(payload);
}

function _workspaceUsesLargeSearchMode({ lineCount = 0, charCount = 0, size = null } = {}) {
  const numericSize = size == null ? NaN : Number(size);
  return (
    Number(lineCount) >= WORKSPACE_VIEWER_LARGE_SEARCH_LINE_THRESHOLD ||
    Number(charCount) >= WORKSPACE_VIEWER_LARGE_SEARCH_CHAR_THRESHOLD ||
    (Number.isFinite(numericSize) && numericSize >= WORKSPACE_VIEWER_LARGE_SEARCH_SIZE_THRESHOLD)
  );
}

function _workspaceRenderViewerSearchControls(wrap, { lineCount = 0, charCount = 0 } = {}) {
  if (typeof workspaceViewerControls !== 'undefined' && workspaceViewerControls) {
    workspaceViewerControls.replaceChildren();
  }
  const controls = document.createElement('div');
  controls.className = 'workspace-viewer-search search-bar';
  const search = document.createElement('input');
  search.type = 'text';
  search.className = 'form-control form-control-compact form-control-quiet';
  search.placeholder = 'Search file...';
  search.setAttribute('aria-label', 'Search file preview');
  if (typeof applyMobileTextInputDefaults === 'function') applyMobileTextInputDefaults(search);

  const toggles = document.createElement('div');
  toggles.className = 'search-toggles';
  const caseBtn = document.createElement('button');
  caseBtn.type = 'button';
  caseBtn.className = 'toggle-btn';
  caseBtn.title = 'Case sensitive (Aa)';
  caseBtn.setAttribute('aria-label', 'Case sensitive');
  caseBtn.setAttribute('aria-pressed', 'false');
  caseBtn.textContent = 'Aa';
  const regexBtn = document.createElement('button');
  regexBtn.type = 'button';
  regexBtn.className = 'toggle-btn';
  regexBtn.title = 'Regular expression (.*)';
  regexBtn.setAttribute('aria-label', 'Regular expression');
  regexBtn.setAttribute('aria-pressed', 'false');
  regexBtn.textContent = '.*';
  toggles.append(caseBtn, regexBtn);

  const count = document.createElement('span');
  count.className = 'search-count';
  const nav = document.createElement('div');
  nav.className = 'search-nav';
  const prevBtn = document.createElement('button');
  prevBtn.type = 'button';
  prevBtn.className = 'btn btn-ghost btn-icon-only btn-compact';
  prevBtn.setAttribute('aria-label', 'Previous match');
  prevBtn.title = 'Previous match (Shift+Enter)';
  prevBtn.textContent = '↑';
  const nextBtn = document.createElement('button');
  nextBtn.type = 'button';
  nextBtn.className = 'btn btn-ghost btn-icon-only btn-compact';
  nextBtn.setAttribute('aria-label', 'Next match');
  nextBtn.title = 'Next match (Enter)';
  nextBtn.textContent = '↓';
  nav.append(prevBtn, nextBtn);

  controls.append(search, toggles, count, nav);

  if (typeof createTextSearchController === 'function') {
    const isLargePreview = _workspaceUsesLargeSearchMode({
      lineCount,
      charCount,
      size: _workspaceViewedSize,
    });
    _workspaceViewerSearchController = createTextSearchController({
      root: wrap,
      input: search,
      countEl: count,
      caseBtn,
      regexBtn,
      prevBtn,
      nextBtn,
      lineSelector: '.workspace-line-row',
      searchDelayMs: isLargePreview ? WORKSPACE_VIEWER_LARGE_SEARCH_DELAY_MS : WORKSPACE_VIEWER_SEARCH_DELAY_MS,
      minQueryLength: isLargePreview ? WORKSPACE_VIEWER_LARGE_SEARCH_MIN_CHARS : 0,
      minQueryMessage: `type ${WORKSPACE_VIEWER_LARGE_SEARCH_MIN_CHARS}+ chars`,
      lazyHighlight: isLargePreview,
      lineTextSelector: '.workspace-line-text',
    });
  }
  if (typeof workspaceViewerControls !== 'undefined' && workspaceViewerControls) {
    workspaceViewerControls.appendChild(controls);
  }
  return controls;
}

function _workspaceRenderTextPreview(payload, { raw = false } = {}) {
  const text = raw ? _workspaceViewerRawText(payload) : String(payload?.text || '');
  const lines = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
  const shown = lines.slice(0, WORKSPACE_PREVIEW_LINE_LIMIT);
  const wrap = document.createElement('div');
  wrap.className = 'workspace-line-preview';
  wrap.style.setProperty('--workspace-line-number-width', `${String(Math.max(1, shown.length)).length + 1}ch`);
  _workspaceRenderViewerSearchControls(wrap, { lineCount: shown.length, charCount: text.length });
  if (payload?.notice && !raw) {
    const notice = document.createElement('div');
    notice.className = 'workspace-preview-notice';
    notice.textContent = payload.notice;
    wrap.appendChild(notice);
  }
  shown.forEach((line, index) => {
    const row = document.createElement('div');
    row.className = 'workspace-line-row';
    row.dataset.lineNumber = String(index + 1);
    const number = document.createElement('span');
    number.className = 'workspace-line-number';
    number.textContent = String(index + 1);
    const body = document.createElement('span');
    body.className = 'workspace-line-text';
    body.textContent = line;
    row.append(number, body);
    wrap.appendChild(row);
  });
  if (lines.length > shown.length) {
    const notice = document.createElement('div');
    notice.className = 'workspace-preview-notice';
    notice.textContent = `Showing first ${shown.length} of ${lines.length} lines. Download or edit to inspect the full file.`;
    wrap.appendChild(notice);
  }
  return wrap;
}

function _workspaceRenderTablePreview(payload) {
  const rows = Array.isArray(payload?.table) ? payload.table : [];
  const table = document.createElement('table');
  table.className = 'workspace-preview-table';
  const thead = document.createElement('thead');
  const headRow = document.createElement('tr');
  (rows[0] || []).forEach(cell => {
    const th = document.createElement('th');
    th.textContent = cell;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);
  const tbody = document.createElement('tbody');
  rows.slice(1).forEach(row => {
    const tr = document.createElement('tr');
    row.forEach(cell => {
      const td = document.createElement('td');
      td.textContent = cell;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  const wrap = document.createElement('div');
  wrap.className = 'workspace-table-preview';
  wrap.appendChild(table);
  if (String(payload?.text || '').split(/\r\n|\r|\n/).filter(Boolean).length > WORKSPACE_PREVIEW_TABLE_LIMIT + 1) {
    const notice = document.createElement('div');
    notice.className = 'workspace-preview-notice';
    notice.textContent = `Showing first ${WORKSPACE_PREVIEW_TABLE_LIMIT} rows. Download or edit to inspect the full file.`;
    wrap.appendChild(notice);
  }
  return wrap;
}

function _workspaceRenderHttpPreview(payload) {
  const data = payload?.http || {};
  const wrap = document.createElement('div');
  wrap.className = 'workspace-http-preview';
  const status = document.createElement('div');
  status.className = 'workspace-http-status';
  status.textContent = data.status || 'HTTP response';
  wrap.appendChild(status);
  const headers = document.createElement('dl');
  headers.className = 'workspace-http-headers';
  (Array.isArray(data.headers) ? data.headers : []).forEach(header => {
    const dt = document.createElement('dt');
    dt.textContent = header.name;
    const dd = document.createElement('dd');
    dd.textContent = header.value;
    headers.append(dt, dd);
  });
  wrap.appendChild(headers);
  if (data.body) {
    const bodyLabel = document.createElement('div');
    bodyLabel.className = 'workspace-preview-subtitle';
    bodyLabel.textContent = 'Body';
    wrap.appendChild(bodyLabel);
    wrap.appendChild(_workspaceRenderTextPreview({ text: data.body }));
  }
  return wrap;
}

function _workspaceRenderViewerPayload(payload, { raw = false } = {}) {
  if (!workspaceViewerText) return;
  if (_workspaceViewerSearchController) _workspaceViewerSearchController.clear();
  _workspaceViewerSearchController = null;
  if (typeof workspaceViewerControls !== 'undefined' && workspaceViewerControls) {
    workspaceViewerControls.replaceChildren();
  }
  workspaceViewerText.replaceChildren();
  const format = raw ? 'raw' : (payload?.format || 'text');
  workspaceViewerText.className = 'workspace-viewer-text nice-scroll';
  workspaceViewerText.classList.toggle('workspace-viewer-json', format === 'json' || format === 'jsonl' || format === 'xml');
  workspaceViewerText.classList.toggle('workspace-viewer-table-wrap', !raw && (format === 'csv' || format === 'tsv'));
  if (!raw && (format === 'csv' || format === 'tsv') && payload?.table) {
    workspaceViewerText.appendChild(_workspaceRenderTablePreview(payload));
  } else if (!raw && format === 'http' && payload?.http) {
    workspaceViewerText.appendChild(_workspaceRenderHttpPreview(payload));
  } else {
    workspaceViewerText.appendChild(_workspaceRenderTextPreview(payload, { raw }));
  }
  workspaceViewerText.scrollTop = 0;
  if (workspaceViewer) {
    workspaceViewer.dataset.viewMode = raw ? 'raw' : 'preview';
    workspaceViewer.querySelectorAll('[data-workspace-preview-mode]').forEach((btn) => {
      const active = btn.dataset.workspacePreviewMode === workspaceViewer.dataset.viewMode;
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }
}

function _workspaceRenderViewerModeControls(payload) {
  if (!workspaceViewer || !payload) return;
  workspaceViewer.querySelector('.workspace-viewer-mode-controls')?.remove();
  if (payload.format === 'text') return;
  const controls = document.createElement('div');
  controls.className = 'workspace-viewer-mode-controls';
  const label = document.createElement('span');
  label.className = 'workspace-preview-kind';
  label.textContent = `${payload.format || 'plain'} preview`;
  const preview = document.createElement('button');
  preview.type = 'button';
  preview.className = 'toggle-btn';
  preview.dataset.workspacePreviewMode = 'preview';
  preview.setAttribute('aria-pressed', 'true');
  preview.textContent = 'Preview';
  const raw = document.createElement('button');
  raw.type = 'button';
  raw.className = 'toggle-btn';
  raw.dataset.workspacePreviewMode = 'raw';
  raw.setAttribute('aria-pressed', 'false');
  raw.textContent = 'Raw';
  controls.append(label, preview, raw);
  const header = workspaceViewer.querySelector('.workspace-viewer-header');
  if (header && header.parentNode) header.parentNode.insertBefore(controls, header.nextSibling);
}

async function switchWorkspaceViewerMode(raw = false) {
  if (!_workspaceViewerPayloadCache) return;
  _workspaceShowViewerBusy(raw ? 'Loading raw view...' : 'Loading preview...');
  await _workspaceAfterPaint();
  _workspaceRenderViewerPayload(_workspaceViewerPayloadCache, { raw });
}

function showWorkspaceEditor(path = '', text = '', { readOnlyPath = false, labels = [], noteBody = '' } = {}) {
  if (!workspaceEditor) return;
  if (!workspaceCanWrite(path ? 'edit Files' : 'create Files', { toast: true })) return;
  hideWorkspaceViewer();
  workspaceEditor.classList.remove('u-hidden');
  if (typeof workspaceEditorOverlay !== 'undefined' && workspaceEditorOverlay) {
    workspaceEditorOverlay.classList.remove('u-hidden');
    workspaceEditorOverlay.classList.add('open');
  }
  if (typeof workspaceEditorTitle !== 'undefined' && workspaceEditorTitle) {
    workspaceEditorTitle.textContent = path ? `Editing ${path}` : 'New file';
  }
  if (workspacePathInput) {
    workspacePathInput.value = path;
    workspacePathInput.readOnly = !!readOnlyPath;
    workspacePathInput.classList.toggle('workspace-path-readonly', !!readOnlyPath);
  }
  if (typeof workspaceLabelsInput !== 'undefined' && workspaceLabelsInput) {
    workspaceLabelsInput.value = (Array.isArray(labels) ? labels : []).join(', ');
  }
  if (typeof workspaceNotesInput !== 'undefined' && workspaceNotesInput) {
    workspaceNotesInput.value = String(noteBody || '');
  }
  if (workspaceTextInput) workspaceTextInput.value = text;
  _workspaceSyncWriteControls();
  setTimeout(() => {
    const active = document.activeElement;
    const activeIsEditable = active instanceof HTMLInputElement
      || active instanceof HTMLTextAreaElement
      || active instanceof HTMLSelectElement
      || active?.isContentEditable;
    const editorHost = (typeof workspaceEditorOverlay !== 'undefined' && workspaceEditorOverlay)
      ? workspaceEditorOverlay
      : workspaceEditor;
    if (activeIsEditable && editorHost?.contains(active)) return;
    if (workspacePathInput && !path) focusElement(workspacePathInput);
    else if (workspaceTextInput) focusElement(workspaceTextInput);
  }, 0);
}

function showWorkspaceViewer(path = '', text = '', { size = null, elevated = false } = {}) {
  hideWorkspaceEditor();
  _workspaceViewedPath = String(path || '').trim();
  const numericSize = size == null ? NaN : Number(size);
  _workspaceViewedSize = Number.isFinite(numericSize) ? numericSize : _workspaceViewerFileSize(path);
  const payload = _workspaceViewerPayload(path, text);
  _workspaceViewerPayloadCache = payload;
  if (workspaceViewerTitle) workspaceViewerTitle.textContent = path;
  _workspaceRenderViewerModeControls(payload);
  _workspaceRenderViewerPayload(payload, { raw: false });
  if (workspaceViewer) {
    workspaceViewer.dataset.format = payload.format;
    workspaceViewer.classList.remove('u-hidden');
    workspaceViewer.scrollTop = 0;
    if (typeof workspaceViewerOverlay !== 'undefined' && workspaceViewerOverlay) {
      workspaceViewerOverlay.classList.toggle('workspace-viewer-overlay-elevated', !!elevated);
      workspaceViewerOverlay.classList.remove('u-hidden');
      workspaceViewerOverlay.classList.add('open');
    }
  }
  _workspaceSyncViewerAutoRefreshToggle();
  _workspaceStartViewerAutoRefresh();
}

async function refreshWorkspaceViewedFile({ auto = false, suppressErrorToast = false } = {}) {
  if (!_workspaceViewedPath || _workspaceViewerRefreshInFlight) return null;
  const viewedPath = _workspaceViewedPath;
  const scrollState = {
    follow: _workspaceViewerShouldFollow(),
    scrollTop: workspaceViewerText ? workspaceViewerText.scrollTop : 0,
  };
  const raw = workspaceViewer?.dataset?.viewMode === 'raw';
  _workspaceViewerRefreshInFlight = true;
  if (!auto) _workspaceSetViewerRefreshBusy(true);
  try {
    if (!auto) {
      _workspaceShowViewerBusy('Refreshing preview...');
      await _workspaceAfterPaint();
    }
    const data = await readWorkspaceFile(viewedPath);
    const nextPath = data.path || viewedPath;
    const numericSize = data.size == null ? NaN : Number(data.size);
    _workspaceViewedSize = Number.isFinite(numericSize) ? numericSize : _workspaceViewerFileSize(nextPath);
    const payload = _workspaceViewerPayload(nextPath, data.text || '');
    _workspaceViewedPath = String(nextPath || '').trim();
    _workspaceViewerPayloadCache = payload;
    if (workspaceViewerTitle) workspaceViewerTitle.textContent = nextPath;
    _workspaceRenderViewerModeControls(payload);
    _workspaceRenderViewerPayload(payload, { raw });
    if (workspaceViewer) workspaceViewer.dataset.format = payload.format;
    _workspaceSyncViewerAutoRefreshToggle();
    _workspaceViewerRestoreScroll(scrollState);
    _workspaceFlashViewerRefreshSpinner(auto && typeof workspaceViewerAutoRefreshToggle !== 'undefined'
      ? workspaceViewerAutoRefreshToggle
      : null);
    return data;
  } catch (err) {
    if (!auto && !suppressErrorToast) _showWorkspaceToast(_workspaceErrorMessage(err, 'Unable to refresh viewed file'), 'error');
    throw err;
  } finally {
    _workspaceViewerRefreshInFlight = false;
    if (!auto) _workspaceSetViewerRefreshBusy(false);
  }
}

function _normalizeWorkspaceDir(path = '') {
  return WorkspaceCore().normalizeDir(path);
}

function normalizeWorkspaceCommandPath(path = '', cwd = '') {
  return WorkspaceCore().normalizeCommandPath(path, cwd);
}

function workspaceDisplayPath(path = '') {
  return WorkspaceCore().displayPath(path);
}

function _workspaceParentDir(path = '') {
  return WorkspaceCore().parentDir(path);
}

function _workspaceFileBasename(path = '') {
  return WorkspaceCore().basename(path);
}

function _bindWorkspaceFolderRow(row, path) {
  row.className = 'workspace-file-row workspace-folder-row';
  row.dataset.kind = 'folder';
  row.dataset.path = path;
  row.dataset.workspaceDropTarget = 'folder';
  row.setAttribute('role', 'row');
}

function _workspacePathInCurrentDir(path = '') {
  const raw = String(path || '').trim();
  const current = _normalizeWorkspaceDir(_workspaceCurrentDir);
  if (!raw) return current ? `${current}/` : '';
  if (raw.includes('/')) return raw;
  return current ? `${current}/${raw}` : raw;
}

function _workspaceDestinationPathInCurrentDir(path = '') {
  const raw = String(path || '').trim();
  if (!raw || raw === '/') return '';
  return _workspacePathInCurrentDir(raw);
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

function _workspaceResetActionMenuPosition(menu) {
  if (!menu) return;
  menu.style.position = '';
  menu.style.left = '';
  menu.style.right = '';
  menu.style.top = '';
  menu.style.bottom = '';
  menu.style.maxHeight = '';
  menu.style.overflowY = '';
}

function _closeWorkspaceActionMenu({ returnFocus = false } = {}) {
  const state = _workspaceOpenActionMenu;
  if (!state) return false;
  state.wrap.classList.remove('open');
  state.trigger.setAttribute('aria-expanded', 'false');
  _workspaceResetActionMenuPosition(state.menu);
  _workspaceOpenActionMenu = null;
  if (returnFocus && state.trigger.isConnected) {
    focusElement(state.trigger, { preventScroll: true });
  }
  return true;
}

function _positionWorkspaceActionMenu(trigger, menu) {
  if (!trigger || !menu || typeof trigger.getBoundingClientRect !== 'function') return;
  const triggerRect = trigger.getBoundingClientRect();
  const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0;
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
  const gutter = 8;
  const menuWidth = Math.max(180, menu.offsetWidth || 180);
  const menuHeight = Math.max(1, menu.scrollHeight || menu.offsetHeight || 1);
  const spaceBelow = Math.max(0, viewportHeight - triggerRect.bottom - gutter);
  const spaceAbove = Math.max(0, triggerRect.top - gutter);
  const openBelow = spaceBelow >= menuHeight || spaceBelow >= spaceAbove;
  const availableHeight = Math.max(48, openBelow ? spaceBelow : spaceAbove);
  const visibleHeight = Math.min(menuHeight, availableHeight);
  const left = Math.min(
    Math.max(gutter, triggerRect.right - menuWidth),
    Math.max(gutter, viewportWidth - menuWidth - gutter),
  );
  const top = openBelow
    ? triggerRect.bottom + 4
    : Math.max(gutter, triggerRect.top - visibleHeight - 4);
  menu.style.position = 'fixed';
  menu.style.left = `${left}px`;
  menu.style.right = 'auto';
  menu.style.top = `${top}px`;
  menu.style.bottom = 'auto';
  if (menuHeight > availableHeight) {
    menu.style.maxHeight = `${availableHeight}px`;
    menu.style.overflowY = 'auto';
  }
}

function _openWorkspaceActionMenu(wrap, trigger, menu) {
  _closeWorkspaceActionMenu();
  wrap.classList.add('open');
  trigger.setAttribute('aria-expanded', 'true');
  _workspaceOpenActionMenu = { wrap, trigger, menu };
  _positionWorkspaceActionMenu(trigger, menu);
  const firstItem = menu.querySelector('[role="menuitem"]:not(:disabled)');
  if (firstItem) focusElement(firstItem, { preventScroll: true });
}

function _workspaceActionMenuKeydown(event, menu) {
  const items = [...menu.querySelectorAll('[role="menuitem"]:not(:disabled)')];
  if (!items.length) return;
  if (event.key === 'Escape') {
    event.preventDefault();
    event.stopPropagation();
    _closeWorkspaceActionMenu({ returnFocus: true });
    return;
  }
  if (event.key === 'Tab') {
    _closeWorkspaceActionMenu();
    return;
  }
  if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
  event.preventDefault();
  const currentIndex = Math.max(0, items.indexOf(document.activeElement));
  let nextIndex = currentIndex;
  if (event.key === 'Home') nextIndex = 0;
  else if (event.key === 'End') nextIndex = items.length - 1;
  else if (event.key === 'ArrowDown') nextIndex = (currentIndex + 1) % items.length;
  else nextIndex = (currentIndex - 1 + items.length) % items.length;
  focusElement(items[nextIndex], { preventScroll: true });
}

function _workspaceFriendlyTimestamp(value = '') {
  const exact = String(value || '').trim();
  if (!exact) return '';
  const parsed = new Date(exact);
  if (Number.isNaN(parsed.getTime())) return exact;
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(parsed);
  } catch (_) {
    return parsed.toLocaleString();
  }
}

function _workspaceFileIcon(path = '', kind = 'file') {
  if (kind === 'folder') return { className: 'is-folder', glyph: '▱' };
  const name = String(path || '').toLowerCase();
  const extension = name.includes('.') ? name.split('.').pop() : '';
  if (['json', 'jsonl', 'ndjson'].includes(extension)) {
    return { className: 'is-json', glyph: '{}' };
  }
  if (['html', 'htm', 'xml'].includes(extension)) {
    return { className: 'is-markup', glyph: '<>' };
  }
  if (['txt', 'log', 'md', 'csv', 'tsv', 'yaml', 'yml'].includes(extension)) {
    return { className: 'is-text', glyph: 'T' };
  }
  return { className: 'is-file', glyph: '◇' };
}

function _workspaceArtifactDetails(file) {
  const artifactCount = Number(file && file.artifact_count ? file.artifact_count : 0);
  const runCount = Number(file && file.artifact_run_count ? file.artifact_run_count : 0);
  const projects = Array.isArray(file?.project_names) ? file.project_names.filter(Boolean) : [];
  const parts = [];
  if (artifactCount) parts.push(artifactCount === 1 ? '1 artifact' : `${artifactCount} artifacts`);
  if (runCount) parts.push(runCount === 1 ? '1 run' : `${runCount} runs`);
  if (projects.length) parts.push(projects.slice(0, 2).join(', '));
  return parts.join(' · ');
}

function _workspaceSearchText(file) {
  const labels = _workspaceLabelValues(file);
  const note = _workspaceNoteBody(file);
  return [
    file?.name,
    file?.path,
    _workspaceArtifactDetails(file),
    ...labels,
    note,
  ].filter(Boolean).join(' ').toLocaleLowerCase();
}

function _workspaceSortedAndFilteredEntries() {
  const direct = _workspaceDirectEntries(_workspaceCurrentDir);
  const query = _workspaceFilterQuery.trim().toLocaleLowerCase();
  const folders = direct.folders
    .filter(folder => !query || `${folder.name} ${folder.path}`.toLocaleLowerCase().includes(query))
    .sort((left, right) => left.name.localeCompare(right.name, undefined, { numeric: true, sensitivity: 'base' }));
  const files = direct.files.filter(file => !query || _workspaceSearchText(file).includes(query));
  files.sort((left, right) => {
    let result = 0;
    if (_workspaceSortKey === 'modified') {
      result = (Date.parse(right.mtime || '') || 0) - (Date.parse(left.mtime || '') || 0);
    } else if (_workspaceSortKey === 'size') {
      result = Number(right.size || 0) - Number(left.size || 0);
    }
    if (!result) {
      result = String(left.name || '').localeCompare(
        String(right.name || ''),
        undefined,
        { numeric: true, sensitivity: 'base' },
      );
    }
    return result;
  });
  return {
    folders,
    files,
    total: direct.folders.length + direct.files.length,
  };
}

function _workspaceParentRow() {
  if (!_workspaceCurrentDir) return null;
  const parentPath = _workspaceParentDir(_workspaceCurrentDir);
  const parentLabel = parentPath ? `Files/${parentPath}` : 'Files';
  const row = document.createElement('div');
  _bindWorkspaceFolderRow(row, parentPath);
  row.classList.add('workspace-parent-row');
  row.dataset.workspaceParent = 'true';
  row.draggable = false;
  row.appendChild(_workspaceNameNode(
    '..',
    parentPath,
    'folder',
    `Parent folder · ${parentLabel}`,
    { accessibleName: `Open parent folder ${parentLabel}` },
  ));
  row.appendChild(_workspaceContextNode('Parent folder'));
  row.appendChild(_workspaceValueNode('', 'workspace-modified-cell'));
  row.appendChild(_workspaceValueNode('', 'workspace-size-cell'));
  const actions = document.createElement('div');
  actions.className = 'workspace-file-actions workspace-parent-actions';
  actions.setAttribute('role', 'cell');
  row.appendChild(actions);
  return row;
}

function renderWorkspaceBreadcrumbs() {
  if (!workspaceBreadcrumbs) return;
  workspaceBreadcrumbs.textContent = '';
  const root = document.createElement('button');
  root.type = 'button';
  root.className = 'btn btn-ghost btn-compact workspace-breadcrumb';
  root.dataset.workspaceDir = '';
  root.textContent = 'Files';
  if (!_workspaceCurrentDir) root.setAttribute('aria-current', 'page');
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
    crumb.className = 'btn btn-ghost btn-compact workspace-breadcrumb';
    crumb.dataset.workspaceDir = acc;
    crumb.textContent = part;
    if (acc === _workspaceCurrentDir) crumb.setAttribute('aria-current', 'page');
    workspaceBreadcrumbs.appendChild(separator);
    workspaceBreadcrumbs.appendChild(crumb);
  });
  if (workspaceUpBtn) {
    const atRoot = !_workspaceCurrentDir;
    workspaceUpBtn.disabled = atRoot;
    workspaceUpBtn.setAttribute('aria-disabled', atRoot ? 'true' : 'false');
    workspaceUpBtn.title = atRoot ? 'Already at the Files root' : 'Open parent folder';
  }
}

function renderWorkspaceBrowser() {
  if (!workspaceFileList) return;
  _closeWorkspaceActionMenu();
  workspaceFileList.textContent = '';
  renderWorkspaceBreadcrumbs();
  const readOnly = isWorkspaceReadOnly();

  const { folders, files, total } = _workspaceSortedAndFilteredEntries();
  const visible = folders.length + files.length;
  if (workspaceResultSummary) {
    const itemLabel = total === 1 ? 'item' : 'items';
    workspaceResultSummary.textContent = _workspaceFilterQuery.trim()
      ? `${visible} of ${total} ${itemLabel}`
      : `${total} ${itemLabel}`;
  }

  const parentRow = _workspaceParentRow();
  if (parentRow) workspaceFileList.appendChild(parentRow);

  for (const folder of folders) {
    const row = document.createElement('div');
    _bindWorkspaceFolderRow(row, folder.path);
    const count = _workspaceFolderFileCount(folder.path);
    row.appendChild(_workspaceNameNode(
      folder.name,
      folder.path,
      'folder',
      count ? `Folder · ${count} ${count === 1 ? 'file' : 'files'}` : 'Empty folder',
    ));
    row.appendChild(_workspaceContextNode(
      count ? `${count} ${count === 1 ? 'file' : 'files'}` : 'Empty',
    ));
    row.appendChild(_workspaceValueNode('', 'workspace-modified-cell'));
    row.appendChild(_workspaceValueNode('', 'workspace-size-cell'));
    row.appendChild(_workspaceActionsNode([
      { action: 'move-folder', label: 'Move', write: true },
      { action: 'delete-folder', label: 'Delete', write: true, destructive: true },
    ], `Actions for folder ${folder.name}`));
    row.draggable = !readOnly;
    workspaceFileList.appendChild(row);
  }

  for (const file of files) {
    const row = document.createElement('div');
    row.className = 'workspace-file-row';
    row.dataset.kind = 'file';
    row.dataset.path = file.path;
    row.setAttribute('role', 'row');
    row.draggable = !readOnly;
    const artifactDetails = _workspaceArtifactDetails(file);
    const friendlyTimestamp = _workspaceFriendlyTimestamp(file.mtime);
    row.appendChild(_workspaceNameNode(
      file.name || _workspaceFileBasename(file.path),
      file.path,
      'file',
      [_formatWorkspaceBytes(file.size), friendlyTimestamp].filter(Boolean).join(' · '),
    ));
    row.appendChild(_workspaceContextNode(artifactDetails, _workspaceMetadataChips(file)));
    row.appendChild(_workspaceValueNode(friendlyTimestamp, 'workspace-modified-cell', file.mtime));
    row.appendChild(_workspaceValueNode(_formatWorkspaceBytes(file.size), 'workspace-size-cell'));
    row.appendChild(_workspaceActionsNode([
      { action: 'edit', label: 'Edit', write: true },
      { action: 'move', label: 'Move', write: true },
      { action: 'download', label: 'Download' },
      { action: 'delete', label: 'Delete', write: true, destructive: true },
    ], `Actions for ${file.name || _workspaceFileBasename(file.path)}`));
    workspaceFileList.appendChild(row);
  }

  if (!folders.length && !files.length && _workspaceFilterQuery.trim()) {
    const empty = document.createElement('div');
    empty.className = 'workspace-empty';
    empty.setAttribute('role', 'row');
    const copy = document.createElement('div');
    copy.setAttribute('role', 'cell');
    copy.textContent = `No files or folders match “${_workspaceFilterQuery.trim()}”.`;
    const clear = document.createElement('button');
    clear.type = 'button';
    clear.className = 'btn btn-secondary btn-compact';
    clear.dataset.workspaceClearFilter = 'true';
    clear.textContent = 'Clear search';
    copy.appendChild(clear);
    empty.appendChild(copy);
    workspaceFileList.appendChild(empty);
  } else if (!folders.length && !files.length && !_workspaceCurrentDir) {
    const empty = document.createElement('div');
    empty.className = 'workspace-empty';
    empty.setAttribute('role', 'row');
    const copy = document.createElement('div');
    copy.setAttribute('role', 'cell');
    copy.textContent = 'No Files yet. Create a text file or save command output to use with file-enabled commands.';
    empty.appendChild(copy);
    workspaceFileList.appendChild(empty);
  } else if (!folders.length && !files.length) {
    const empty = document.createElement('div');
    empty.className = 'workspace-empty';
    empty.setAttribute('role', 'row');
    const copy = document.createElement('div');
    copy.setAttribute('role', 'cell');
    copy.textContent = 'This folder is empty.';
    empty.appendChild(copy);
    workspaceFileList.appendChild(empty);
  }
}

function _workspaceNameNode(nameText, path, kind, detailsText = '', { accessibleName = '' } = {}) {
  const meta = document.createElement('div');
  meta.className = 'workspace-file-meta';
  meta.setAttribute('role', 'cell');
  const iconSpec = _workspaceFileIcon(path, kind);
  const icon = document.createElement('span');
  icon.className = `workspace-file-icon ${iconSpec.className}`;
  icon.setAttribute('aria-hidden', 'true');
  icon.textContent = iconSpec.glyph;
  meta.appendChild(icon);
  const text = document.createElement('div');
  text.className = 'workspace-file-meta-text';
  const name = document.createElement('button');
  name.type = 'button';
  name.className = 'btn btn-ghost workspace-file-name workspace-item-open';
  name.dataset.workspaceAction = kind === 'folder' ? 'open-folder' : 'view';
  name.setAttribute(
    'aria-label',
    accessibleName || `${kind === 'folder' ? 'Open folder' : 'View file'} ${nameText}`,
  );
  name.textContent = nameText;
  const details = document.createElement('div');
  details.className = 'workspace-file-details';
  details.textContent = detailsText;
  text.appendChild(name);
  text.appendChild(details);
  meta.appendChild(text);
  return meta;
}

function _workspaceMetadataChipsNode(chips = []) {
  const visibleChips = Array.isArray(chips) ? chips.filter(chip => chip && chip.label) : [];
  if (!visibleChips.length) return null;
  const chipWrap = document.createElement('div');
  chipWrap.className = 'workspace-metadata-chips';
  for (const chip of visibleChips) {
    const chipNode = document.createElement('span');
    chipNode.className = `workspace-metadata-chip ${chip.kind === 'note' ? 'is-note' : 'is-label'}`;
    chipNode.textContent = chip.label;
    chipWrap.appendChild(chipNode);
  }
  return chipWrap;
}

function _workspaceContextNode(contextText = '', chips = []) {
  const context = document.createElement('div');
  context.className = 'workspace-context-cell';
  context.setAttribute('role', 'cell');
  const copy = document.createElement('span');
  copy.className = 'workspace-context-copy';
  copy.textContent = contextText || '—';
  context.appendChild(copy);
  const chipWrap = _workspaceMetadataChipsNode(chips);
  if (chipWrap) context.appendChild(chipWrap);
  return context;
}

function _workspaceValueNode(value = '', className = '', exactValue = '') {
  const cell = document.createElement('div');
  cell.className = `workspace-value-cell ${className}`.trim();
  cell.setAttribute('role', 'cell');
  if (exactValue) {
    const time = document.createElement('time');
    time.dateTime = String(exactValue);
    time.title = String(exactValue);
    time.textContent = value || '—';
    cell.appendChild(time);
  } else {
    cell.textContent = value || '—';
  }
  return cell;
}

function _workspaceActionsNode(items = [], accessibleLabel = 'File actions') {
  const actions = document.createElement('div');
  actions.className = 'workspace-file-actions';
  actions.setAttribute('role', 'cell');
  const wrap = document.createElement('div');
  wrap.className = 'workspace-action-menu-wrap';
  const trigger = document.createElement('button');
  trigger.type = 'button';
  trigger.className = 'btn btn-ghost btn-compact workspace-action-menu-trigger';
  trigger.dataset.workspaceMenuTrigger = 'true';
  trigger.setAttribute('aria-label', accessibleLabel);
  trigger.setAttribute('aria-haspopup', 'menu');
  trigger.setAttribute('aria-expanded', 'false');
  trigger.textContent = '⋯';
  const menu = document.createElement('div');
  menu.className = 'workspace-action-menu dropdown-surface';
  menu.setAttribute('role', 'menu');
  const readOnly = isWorkspaceReadOnly();
  const readOnlyTitle = readOnly ? _workspaceReadOnlyReason('change Files') : '';
  for (const item of items) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `dropdown-item dropdown-item-touch${item.destructive ? ' is-destructive' : ''}`;
    btn.setAttribute('role', 'menuitem');
    btn.dataset.workspaceAction = item.action;
    if (item.write && readOnly) {
      btn.disabled = true;
      btn.setAttribute('aria-disabled', 'true');
      btn.title = readOnlyTitle;
    }
    btn.textContent = item.label;
    menu.appendChild(btn);
  }
  trigger.addEventListener('click', event => {
    event.preventDefault();
    event.stopPropagation();
    if (_workspaceOpenActionMenu?.wrap === wrap) {
      _closeWorkspaceActionMenu({ returnFocus: true });
    } else {
      _openWorkspaceActionMenu(wrap, trigger, menu);
    }
  });
  trigger.addEventListener('keydown', event => {
    if (event.key === 'ArrowDown' && _workspaceOpenActionMenu?.wrap !== wrap) {
      event.preventDefault();
      _openWorkspaceActionMenu(wrap, trigger, menu);
    }
  });
  menu.addEventListener('keydown', event => _workspaceActionMenuKeydown(event, menu));
  wrap.append(trigger, menu);
  actions.appendChild(wrap);
  return actions;
}

function _workspaceUsagePercent(value, limit) {
  const normalizedValue = Math.max(0, Number(value) || 0);
  const normalizedLimit = Math.max(0, Number(limit) || 0);
  if (!normalizedLimit) return 0;
  return Math.min(100, (normalizedValue / normalizedLimit) * 100);
}

function _workspaceSetUsageLoading(label = 'Loading…') {
  if (workspaceFileUsage) workspaceFileUsage.textContent = label;
  if (workspaceStorageUsage) workspaceStorageUsage.textContent = label;
  if (workspaceFileUsageFill) workspaceFileUsageFill.style.width = '0%';
  if (workspaceStorageUsageFill) workspaceStorageUsageFill.style.width = '0%';
  if (workspaceSummary) workspaceSummary.setAttribute('aria-label', label);
}

function _workspaceResetBrowserControls() {
  _workspaceFilterQuery = '';
  _workspaceSortKey = 'name';
  if (workspaceSearchInput) workspaceSearchInput.value = '';
  if (workspaceSortSelect) {
    workspaceSortSelect.value = 'name';
    if (typeof syncAppSelect === 'function') syncAppSelect(workspaceSortSelect);
  }
  _closeWorkspaceActionMenu();
}

function renderWorkspaceFiles(payload = {}) {
  _workspaceLoaded = true;
  _workspaceApplyOwner(_workspaceOwnerFromPayload(payload));
  _workspaceDirs = Array.isArray(payload.directories) ? payload.directories : [];
  _workspaceFiles = Array.isArray(payload.files) ? payload.files : [];
  _workspaceLimits = payload.limits && typeof payload.limits === 'object' ? payload.limits : {};
  const currentHasEntries = !_workspaceCurrentDir || _workspaceFiles.some(file => {
    const path = String(file.path || '').split('/').filter(Boolean).join('/');
    return path === _workspaceCurrentDir || path.startsWith(`${_workspaceCurrentDir}/`);
  }) || _workspaceDirs.some(directory => {
    const path = String(directory.path || '').split('/').filter(Boolean).join('/');
    return path === _workspaceCurrentDir || path.startsWith(`${_workspaceCurrentDir}/`);
  });
  if (!currentHasEntries) _workspaceSetCurrentDir('');
  const usage = payload.usage || {};
  const limits = payload.limits || {};
  const fileCount = Number(usage.file_count) || 0;
  const maxFiles = Number(limits.max_files) || 0;
  const bytesUsed = Number(usage.bytes_used) || 0;
  const quotaBytes = Number(limits.quota_bytes) || 0;

  const ownerLabel = _workspaceOwnerLabel();
  const readOnly = isWorkspaceReadOnly();
  const fileUsageText = `${fileCount}${maxFiles ? ` / ${maxFiles}` : ''}`;
  const storageUsageText = `${_formatWorkspaceBytes(bytesUsed)}${quotaBytes ? ` / ${_formatWorkspaceBytes(quotaBytes)}` : ''}`;
  if (workspaceScopeBadge) {
    workspaceScopeBadge.textContent = ownerLabel;
    workspaceScopeBadge.classList.toggle('is-read-only', readOnly);
    workspaceScopeBadge.title = readOnly ? _workspaceReadOnlyReason('change Files') : `Active Files scope: ${ownerLabel}`;
  }
  if (workspaceFileUsage) workspaceFileUsage.textContent = fileUsageText;
  if (workspaceStorageUsage) workspaceStorageUsage.textContent = storageUsageText;
  if (workspaceFileUsageFill) {
    workspaceFileUsageFill.style.width = `${_workspaceUsagePercent(fileCount, maxFiles)}%`;
  }
  if (workspaceStorageUsageFill) {
    workspaceStorageUsageFill.style.width = `${_workspaceUsagePercent(bytesUsed, quotaBytes)}%`;
  }
  if (workspaceSummary) {
    const readOnlySuffix = readOnly ? ', read-only' : '';
    workspaceSummary.setAttribute(
      'aria-label',
      `${ownerLabel}, ${fileUsageText} files, ${storageUsageText}${readOnlySuffix}`,
    );
  }
  if (workspaceReadOnlyStatus) {
    workspaceReadOnlyStatus.classList.toggle('u-hidden', !readOnly);
    workspaceReadOnlyStatus.title = readOnly ? _workspaceReadOnlyReason('change Files') : '';
  }
  _workspaceSyncWriteControls();
  if (!workspaceFileList) return;
  renderWorkspaceBrowser();
}

async function loadWorkspaceFilesPayload(options = {}) {
  if (!isWorkspaceEnabled()) throw new Error('Files are disabled on this instance');
  if (_workspaceFilesLoadPromise && options.force !== true) return _workspaceFilesLoadPromise;
  const request = (async () => {
    const resp = await _workspaceApiFetch()('/workspace/files', { cache: 'no-store' });
    const data = await _workspaceJson(resp);
    renderWorkspaceFiles(data);
    return data;
  })();
  _workspaceFilesLoadPromise = request;
  try {
    return await request;
  } finally {
    if (_workspaceFilesLoadPromise === request) _workspaceFilesLoadPromise = null;
  }
}

async function refreshWorkspaceFiles(options = {}) {
  setWorkspaceMessage('');
  _workspaceSetUsageLoading();
  return loadWorkspaceFilesPayload(options);
}

async function refreshWorkspaceFilesFromButton() {
  if (!workspaceRefreshBtn) return;
  workspaceRefreshBtn.disabled = true;
  workspaceRefreshBtn.setAttribute('aria-label', 'Refreshing files');
  workspaceRefreshBtn.title = 'Refreshing files';
  try {
    const viewedPath = _workspaceViewedPath;
    await refreshWorkspaceFiles({ force: true });
    if (viewedPath) {
      try {
        await refreshWorkspaceViewedFile({ suppressErrorToast: true });
      } catch (err) {
        hideWorkspaceViewer();
        _showWorkspaceToast(_workspaceErrorMessage(err, 'Unable to refresh viewed file'), 'error');
      }
    }
  } catch (err) {
    _workspaceLoaded = false;
    _workspaceFiles = [];
    if (workspaceFileList) workspaceFileList.textContent = '';
    _workspaceSetUsageLoading('Unavailable');
    _showWorkspaceToast(_workspaceErrorMessage(err, 'Unable to refresh files'), 'error');
  } finally {
    workspaceRefreshBtn.disabled = false;
    workspaceRefreshBtn.setAttribute('aria-label', 'Refresh files');
    workspaceRefreshBtn.title = 'Refresh files';
  }
}

async function saveWorkspaceFile(path, text, metadata = null) {
  if (!workspaceCanWrite('save Files', { toast: true })) throw new Error(_workspaceReadOnlyReason('save Files'));
  const resp = await _workspaceApiFetch()('/workspace/files', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, text }),
  });
  const data = await _workspaceJson(resp);
  const savedPath = data.file?.path || path;
  if (metadata) {
    await _syncWorkspaceFileMetadata(savedPath, metadata);
    try {
      await refreshWorkspaceFiles();
    } catch (_) {
      renderWorkspaceFiles(data.workspace || {});
    }
  } else {
    renderWorkspaceFiles(data.workspace || {});
  }
  hideWorkspaceEditor();
  hideWorkspaceViewer();
  _showWorkspaceToast(`Saved ${savedPath}`, 'success');
  return data;
}

async function writeWorkspaceTextFile(path, text, { append = false } = {}) {
  if (!workspaceCanWrite('write Files', { toast: true })) throw new Error(_workspaceReadOnlyReason('write Files'));
  const resp = await _workspaceApiFetch()('/workspace/files', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(append ? { path, text, append: true } : { path, text }),
  });
  const data = await _workspaceJson(resp);
  renderWorkspaceFiles(data.workspace || {});
  return data;
}

async function createWorkspaceDirectory(path) {
  if (!workspaceCanWrite('create folders in Files', { toast: true })) throw new Error(_workspaceReadOnlyReason('create folders in Files'));
  const normalized = _normalizeWorkspaceDir(path);
  const resp = await _workspaceApiFetch()('/workspace/directories', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path: normalized }),
  });
  const data = await _workspaceJson(resp);
  _workspaceSetCurrentDir(data.directory?.path || normalized);
  renderWorkspaceFiles(data.workspace || {});
  hideWorkspaceEditor();
  hideWorkspaceViewer();
  _showWorkspaceToast(`Created folder ${data.directory?.path || normalized}`, 'success');
  return data;
}

async function promptWorkspaceFolderName() {
  if (!workspaceCanWrite('create folders in Files', { toast: true })) return null;
  const current = _normalizeWorkspaceDir(_workspaceCurrentDir);
  const promptDefault = current ? `${current}/` : '';
  if (typeof showConfirm !== 'function') {
    _showWorkspaceToast('Unable to open folder prompt', 'error');
    return null;
  }

  const field = document.createElement('div');
  field.className = 'workspace-folder-form';
  const id = `workspace-folder-input-${Date.now()}`;
  const label = document.createElement('label');
  label.className = 'workspace-label';
  label.setAttribute('for', id);
  label.textContent = 'Folder Name';
  const input = document.createElement('input');
  input.id = id;
  input.className = 'form-input form-control';
  input.type = 'text';
  input.placeholder = current ? `${current}/reports` : 'reports';
  if (typeof applyMobileTextInputDefaults === 'function') {
    applyMobileTextInputDefaults(input);
  } else {
    input.autocomplete = 'off';
    input.autocapitalize = 'none';
    input.autocorrect = 'off';
    input.spellcheck = false;
    input.inputMode = 'text';
  }
  input.value = promptDefault;
  const error = document.createElement('div');
  error.className = 'workspace-folder-error u-hidden';
  field.append(label, input, error);

  const setError = (message = '') => {
    error.textContent = message;
    error.classList.toggle('u-hidden', !message);
  };
  let created = null;
  const createFromInput = async () => {
    setError('');
    const raw = String(input.value || '').trim();
    if (!raw) {
      setError('Enter a folder name.');
      focusElement(input);
      return false;
    }
    const path = current && !raw.includes('/') ? `${current}/${raw}` : raw;
    try {
      created = await createWorkspaceDirectory(path);
      return true;
    } catch (err) {
      setError(_workspaceErrorMessage(err, 'Unable to create folder'));
      focusElement(input);
      return false;
    }
  };
  input.addEventListener('keydown', event => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    const createBtn = document.querySelector('#confirm-host [data-confirm-action-id="create"]');
    if (createBtn && typeof createBtn.click === 'function') createBtn.click();
  });

  const choice = await showConfirm({
    body: {
      text: 'Create a workspace folder?',
      note: current ? `Current folder: ${current}` : 'Create it at the Files root or include a path.',
    },
    content: field,
    defaultFocus: input,
    actions: [
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      { id: 'create', label: 'Create folder', role: 'primary', onActivate: createFromInput },
    ],
  });
  return choice === 'create' ? created : null;
}

async function promptWorkspaceMove(sourcePath, { kind = 'file' } = {}) {
  if (!workspaceCanWrite('move Files', { toast: true })) return null;
  const source = String(sourcePath || '').trim();
  if (!source || typeof showConfirm !== 'function') {
    _showWorkspaceToast('Unable to open move prompt', 'error');
    return null;
  }

  const field = document.createElement('div');
  field.className = 'workspace-folder-form';
  const id = `workspace-move-input-${Date.now()}`;
  const label = document.createElement('label');
  label.className = 'workspace-label';
  label.setAttribute('for', id);
  label.textContent = 'Destination';
  const input = document.createElement('input');
  input.id = id;
  input.className = 'form-input form-control';
  input.type = 'text';
  input.placeholder = _workspaceCurrentDir ? `${_workspaceCurrentDir}/` : 'reports';
  input.value = _workspaceCurrentDir ? `${_workspaceCurrentDir}/` : '';
  if (typeof applyMobileTextInputDefaults === 'function') {
    applyMobileTextInputDefaults(input);
  }
  const error = document.createElement('div');
  error.className = 'workspace-folder-error u-hidden';
  field.append(label, input, error);

  const setError = (message = '') => {
    error.textContent = message;
    error.classList.toggle('u-hidden', !message);
  };
  let moved = null;
  const moveFromInput = async () => {
    setError('');
    try {
      const destination = _workspaceDestinationPathInCurrentDir(input.value);
      moved = await moveWorkspacePath(source, destination);
      return true;
    } catch (err) {
      setError(_workspaceErrorMessage(err, 'Unable to move item'));
      focusElement(input);
      return false;
    }
  };
  input.addEventListener('keydown', event => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    const moveBtn = document.querySelector('#confirm-host [data-confirm-action-id="move"]');
    if (moveBtn && typeof moveBtn.click === 'function') moveBtn.click();
  });

  const labelKind = kind === 'directory' || kind === 'folder' ? 'folder' : 'file';
  const choice = await showConfirm({
    body: {
      text: `Move ${labelKind} ${source}?`,
      note: 'Choose a destination folder, or enter a full destination path to rename while moving.',
    },
    content: field,
    defaultFocus: input,
    actions: [
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      { id: 'move', label: 'Move', role: 'primary', onActivate: moveFromInput },
    ],
  });
  return choice === 'move' ? moved : null;
}

async function readWorkspaceFile(path) {
  const resp = await _workspaceApiFetch()(`/workspace/files/read?path=${encodeURIComponent(path)}`);
  return _workspaceJson(resp);
}

async function deleteWorkspacePath(path) {
  if (!workspaceCanWrite('delete Files', { toast: true })) throw new Error(_workspaceReadOnlyReason('delete Files'));
  const resp = await _workspaceApiFetch()(`/workspace/files?path=${encodeURIComponent(path)}`, { method: 'DELETE' });
  const data = await _workspaceJson(resp);
  renderWorkspaceFiles(data.workspace || {});
  hideWorkspaceViewer();
  const deleted = data.deleted || {};
  const kind = deleted.kind === 'directory' ? 'folder' : 'file';
  _showWorkspaceToast(`Deleted ${kind} ${path}`, 'success');
  return data;
}

async function moveWorkspacePath(source, destination) {
  if (!workspaceCanWrite('move Files', { toast: true })) throw new Error(_workspaceReadOnlyReason('move Files'));
  const resp = await _workspaceApiFetch()('/workspace/files/move', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source, destination }),
  });
  const data = await _workspaceJson(resp);
  renderWorkspaceFiles(data.workspace || {});
  hideWorkspaceViewer();
  const moved = data.moved || {};
  _showWorkspaceToast(`Moved ${moved.source || source} to ${moved.destination || destination || 'Files'}`, 'success');
  return data;
}

async function copyWorkspacePath(source, destination) {
  if (!workspaceCanWrite('copy Files', { toast: true })) throw new Error(_workspaceReadOnlyReason('copy Files'));
  const resp = await _workspaceApiFetch()('/workspace/files/copy', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source, destination }),
  });
  const data = await _workspaceJson(resp);
  renderWorkspaceFiles(data.workspace || {});
  return data;
}

async function touchWorkspaceFile(path) {
  if (!workspaceCanWrite('touch Files', { toast: true })) throw new Error(_workspaceReadOnlyReason('touch Files'));
  const resp = await _workspaceApiFetch()('/workspace/files/touch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  });
  const data = await _workspaceJson(resp);
  renderWorkspaceFiles(data.workspace || {});
  return data;
}

async function deleteWorkspaceFile(path) {
  return deleteWorkspacePath(path);
}

async function downloadWorkspaceFile(path) {
  const resp = await _workspaceApiFetch()('/workspace/files/download-ticket', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  });
  if (!resp.ok) {
    await _workspaceJson(resp);
    return false;
  }
  const data = await _workspaceJson(resp);
  downloadUrlAsAttachment(
    data.url,
    { filename: path.split('/').filter(Boolean).pop() || 'workspace-file.txt' },
  );
  return true;
}

async function openWorkspace() {
  if (!isWorkspaceEnabled()) return;
  const global = _workspaceGlobal();
  if (typeof importedCloseMajorOverlays === 'function') importedCloseMajorOverlays();
  if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
  _workspaceResetBrowserControls();
  showWorkspaceOverlay();
  hideWorkspaceEditor();
  hideWorkspaceViewer();
  try {
    await refreshWorkspaceFiles();
  } catch (err) {
    _workspaceLoaded = false;
    _workspaceFiles = [];
    if (workspaceFileList) workspaceFileList.textContent = '';
    _workspaceSetUsageLoading('Unavailable');
    _showWorkspaceToast(_workspaceErrorMessage(err, 'Unable to load files'), 'error');
  }
  if (typeof markInteractionSurfaceReady === 'function') {
    markInteractionSurfaceReady('workspace', workspaceOverlay, workspaceModal);
  }
}

async function openWorkspaceEditorFromCommand(action = 'add', path = '') {
  if (!isWorkspaceEnabled()) return false;
  if (!workspaceCanWrite(String(action || '').toLowerCase() === 'edit' ? 'edit Files' : 'create Files', { toast: true })) return false;
  if (typeof hideWorkspaceOverlay === 'function') hideWorkspaceOverlay();
  if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
  hideWorkspaceViewer();
  const fileName = String(path || '').trim();
  if (String(action || '').toLowerCase() === 'edit' && fileName) {
    const blockedReason = _workspaceFileReadBlockedReason(fileName);
    if (blockedReason) {
      _showWorkspaceToast(blockedReason, 'error');
      return false;
    }
    try {
      const data = await readWorkspaceFile(fileName);
      const editorPath = data.path || fileName;
      showWorkspaceEditor(editorPath, data.text || '', {
        readOnlyPath: true,
        ..._workspaceMetadataOptionsForPath(editorPath, data),
      });
    } catch (err) {
      hideWorkspaceEditor();
      _showWorkspaceToast(_workspaceErrorMessage(err, 'Unable to load workspace file'), 'error');
      return false;
    }
    return true;
  }
  showWorkspaceEditor(fileName, '');
  return true;
}

function closeWorkspace() {
  _workspaceResetBrowserControls();
  hideWorkspaceOverlay();
  hideWorkspaceEditor();
  hideWorkspaceViewer();
  refocusComposerAfterAction({ defer: true });
}

async function handleWorkspaceFileAction(action, path) {
  try {
    setWorkspaceMessage('');
    if (action === 'open-folder') {
      _workspaceSetCurrentDir(path);
      hideWorkspaceViewer();
      renderWorkspaceBrowser();
    } else if (action === 'view') {
      const blockedReason = _workspaceFileReadBlockedReason(path);
      if (blockedReason) {
        _showWorkspaceToast(blockedReason, 'error');
        return;
      }
      showWorkspaceViewerLoading(path);
      await _workspaceAfterPaint();
      const data = await readWorkspaceFile(path);
      if (_workspaceViewedPath !== String(path || '').trim()) return;
      showWorkspaceViewer(data.path || path, data.text || '', { size: data.size });
    } else if (action === 'edit') {
      if (!workspaceCanWrite('edit Files', { toast: true })) return;
      const blockedReason = _workspaceFileReadBlockedReason(path);
      if (blockedReason) {
        _showWorkspaceToast(blockedReason, 'error');
        return;
      }
      showWorkspaceViewerLoading(path, 'Loading file for edit...');
      await _workspaceAfterPaint();
      const data = await readWorkspaceFile(path);
      if (_workspaceViewedPath !== String(path || '').trim()) return;
      const editorPath = data.path || path;
      showWorkspaceEditor(editorPath, data.text || '', {
        readOnlyPath: true,
        ..._workspaceMetadataOptionsForPath(editorPath, data),
      });
    } else if (action === 'download') {
      await downloadWorkspaceFile(path);
    } else if (action === 'move') {
      if (!workspaceCanWrite('move Files', { toast: true })) return;
      await promptWorkspaceMove(path, { kind: 'file' });
    } else if (action === 'delete') {
      if (!workspaceCanWrite('delete Files', { toast: true })) return;
      const confirmed = typeof showConfirm === 'function'
        ? await showConfirm({
            body: { text: `Delete ${path}?`, note: 'This only removes the workspace file.' },
            tone: 'danger',
            actions: [
              { id: 'cancel', label: 'Cancel', role: 'cancel' },
              { id: 'delete', label: 'Delete', role: 'destructive' },
            ],
          })
        : 'delete';
      if (confirmed === 'delete') await deleteWorkspacePath(path);
    } else if (action === 'delete-folder') {
      if (!workspaceCanWrite('delete Files', { toast: true })) return;
      const count = _workspaceFolderFileCount(path);
      const note = count
        ? `This will also delete ${count} ${count === 1 ? 'file' : 'files'} in this folder.`
        : 'This only removes the empty workspace folder.';
      const confirmed = typeof showConfirm === 'function'
        ? await showConfirm({
            body: { text: `Delete folder ${path}?`, note },
            tone: 'danger',
            actions: [
              { id: 'cancel', label: 'Cancel', role: 'cancel' },
              { id: 'delete', label: 'Delete', role: 'destructive' },
            ],
          })
        : 'delete';
      if (confirmed === 'delete') await deleteWorkspacePath(path);
    } else if (action === 'move-folder') {
      if (!workspaceCanWrite('move Files', { toast: true })) return;
      await promptWorkspaceMove(path, { kind: 'folder' });
    }
  } catch (err) {
    if (action === 'view' || action === 'edit') hideWorkspaceViewer();
    _showWorkspaceToast(_workspaceErrorMessage(err), 'error');
  }
}

workspaceRefreshBtn?.addEventListener('click', () => { refreshWorkspaceFilesFromButton(); });
workspaceViewerRefreshBtn?.addEventListener('click', () => { refreshWorkspaceViewedFile().catch(() => {}); });
workspaceViewerAutoRefreshToggle?.addEventListener('click', () => {
  if (workspaceViewerAutoRefreshToggle.getAttribute('aria-disabled') === 'true') return;
  _workspaceViewerAutoRefreshEnabled = !_workspaceViewerAutoRefreshEnabled;
  if (_workspaceViewerAutoRefreshEnabled) _workspaceStartViewerAutoRefresh();
  else {
    _workspaceStopViewerAutoRefresh();
    workspaceViewerAutoRefreshToggle.classList.remove('is-refreshing');
    _workspaceSyncViewerAutoRefreshToggle();
  }
});
workspaceNewBtn?.addEventListener('click', () => {
  if (!workspaceCanWrite('create Files', { toast: true })) return;
  showWorkspaceEditor('', '');
});
workspaceNewFolderBtn?.addEventListener('click', () => { promptWorkspaceFolderName(); });
workspaceCancelEditBtn?.addEventListener('click', () => hideWorkspaceEditor());
workspaceCloseViewerBtn?.addEventListener('click', () => hideWorkspaceViewer());
workspaceUpBtn?.addEventListener('click', () => {
  if (!_workspaceCurrentDir) return;
  _workspaceSetCurrentDir(_workspaceParentDir(_workspaceCurrentDir));
  hideWorkspaceViewer();
  renderWorkspaceBrowser();
});
workspaceSearchInput?.addEventListener('input', () => {
  _workspaceFilterQuery = String(workspaceSearchInput.value || '');
  renderWorkspaceBrowser();
});
workspaceSortSelect?.addEventListener('change', () => {
  const selected = String(workspaceSortSelect.value || 'name');
  _workspaceSortKey = ['name', 'modified', 'size'].includes(selected) ? selected : 'name';
  renderWorkspaceBrowser();
});
workspaceBreadcrumbs?.addEventListener('click', event => {
  const btn = event.target && event.target.closest ? event.target.closest('[data-workspace-dir]') : null;
  if (!btn) return;
  _workspaceSetCurrentDir(btn.dataset.workspaceDir || '');
  hideWorkspaceViewer();
  renderWorkspaceBrowser();
});
workspaceViewer?.addEventListener('click', event => {
  const refreshBtn = event.target && event.target.closest ? event.target.closest('[data-workspace-viewer-refresh]') : null;
  if (refreshBtn) {
    if (typeof workspaceViewerRefreshBtn !== 'undefined' && refreshBtn === workspaceViewerRefreshBtn) return;
    refreshWorkspaceViewedFile().catch(() => {});
    return;
  }
  const autoRefreshBtn = event.target && event.target.closest ? event.target.closest('[data-workspace-viewer-auto-refresh]') : null;
  if (autoRefreshBtn) {
    if (typeof workspaceViewerAutoRefreshToggle !== 'undefined' && autoRefreshBtn === workspaceViewerAutoRefreshToggle) return;
    if (autoRefreshBtn.getAttribute('aria-disabled') === 'true') return;
    _workspaceViewerAutoRefreshEnabled = !_workspaceViewerAutoRefreshEnabled;
    if (_workspaceViewerAutoRefreshEnabled) _workspaceStartViewerAutoRefresh();
    else {
      _workspaceStopViewerAutoRefresh();
      autoRefreshBtn.classList.remove('is-refreshing');
      _workspaceSyncViewerAutoRefreshToggle();
    }
    return;
  }
  const modeBtn = event.target && event.target.closest ? event.target.closest('[data-workspace-preview-mode]') : null;
  if (modeBtn && _workspaceViewerPayloadCache) {
    switchWorkspaceViewerMode(modeBtn.dataset.workspacePreviewMode === 'raw').catch(() => {});
    return;
  }
  const btn = event.target && event.target.closest ? event.target.closest('[data-workspace-viewer-action]') : null;
  if (!btn || !_workspaceViewedPath) return;
  handleWorkspaceFileAction(btn.dataset.workspaceViewerAction, _workspaceViewedPath);
});
workspaceEditor?.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!workspaceCanWrite('save Files', { toast: true })) return;
  try {
    await saveWorkspaceFile(
      _workspacePathInCurrentDir(workspacePathInput?.value || ''),
      workspaceTextInput?.value || '',
      {
        labels: _workspaceEntityMetadataClient().parseLabelInput(
          typeof workspaceLabelsInput !== 'undefined' && workspaceLabelsInput ? workspaceLabelsInput.value : '',
        ),
        noteBody: typeof workspaceNotesInput !== 'undefined' && workspaceNotesInput ? workspaceNotesInput.value : '',
      },
    );
  } catch (err) {
    _showWorkspaceToast(_workspaceErrorMessage(err, 'Unable to save workspace file'), 'error');
  }
});
workspaceFileList?.addEventListener('click', event => {
  const clearFilter = event.target && event.target.closest
    ? event.target.closest('[data-workspace-clear-filter]')
    : null;
  if (clearFilter) {
    _workspaceFilterQuery = '';
    if (workspaceSearchInput) {
      workspaceSearchInput.value = '';
      focusElement(workspaceSearchInput, { preventScroll: true });
    }
    renderWorkspaceBrowser();
    return;
  }
  const btn = event.target && event.target.closest ? event.target.closest('[data-workspace-action]') : null;
  if (!btn) return;
  if (btn.disabled || btn.getAttribute('aria-disabled') === 'true') return;
  const row = btn.closest('.workspace-file-row');
  if (!row || !workspaceFileList.contains(row)) return;
  const action = btn.dataset.workspaceAction;
  const path = row?.dataset.path || '';
  if (!path && action !== 'open-folder') return;
  _closeWorkspaceActionMenu();
  handleWorkspaceFileAction(action, path);
});
document.addEventListener('click', event => {
  if (!_workspaceOpenActionMenu) return;
  const target = event.target;
  if (target && typeof target.closest === 'function' && target.closest('.workspace-action-menu-wrap')) return;
  _closeWorkspaceActionMenu();
});
document.addEventListener('keydown', event => {
  if (event.key !== 'Escape' || !_workspaceOpenActionMenu) return;
  event.preventDefault();
  event.stopPropagation();
  _closeWorkspaceActionMenu({ returnFocus: true });
}, true);
if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
  window.addEventListener('app:scope-changed', () => {
    _workspaceResetForScopeChange();
    _workspaceSetUsageLoading('Loading…');
    if (workspaceFileList) workspaceFileList.textContent = '';
    if (isWorkspaceEnabled()) {
      _workspaceFileCacheApi().refresh?.().catch(() => {});
    }
  });
  window.addEventListener('app:scope-capabilities-changed', () => {
    _workspaceSyncWriteControls();
    if (workspaceFileList) renderWorkspaceBrowser();
  });
}
if (typeof window !== 'undefined') {
  if (isWorkspaceEnabled()) setTimeout(() => { _workspaceFileCacheApi().refresh?.(); }, 0);
}
if (typeof importedSetRuntimeHandlers === 'function') {
  importedSetRuntimeHandlers({ refreshWorkspaceFiles, loadWorkspaceFilesPayload });
}
if (typeof importedSetWorkspaceHandlers === 'function') {
  importedSetWorkspaceHandlers({
    closeWorkspace,
    copyWorkspacePath,
    createWorkspaceDirectory,
    downloadWorkspaceFile,
    _formatWorkspaceBytes,
    hideWorkspaceEditor,
    hideWorkspaceViewer,
    loadWorkspaceFilesPayload,
    moveWorkspacePath,
    openWorkspace,
    openWorkspaceEditorFromCommand,
    readWorkspaceFile,
    refreshWorkspaceFiles,
    showWorkspaceViewer,
    touchWorkspaceFile,
    writeWorkspaceTextFile,
    workspaceCanWrite,
  });
}

export {
  closeWorkspace,
  copyWorkspacePath,
  createWorkspaceDirectory,
  hideWorkspaceEditor,
  hideWorkspaceViewer,
  _formatWorkspaceBytes,
  downloadWorkspaceFile,
  moveWorkspacePath,
  openWorkspace,
  openWorkspaceEditorFromCommand,
  readWorkspaceFile,
  refreshWorkspaceFiles,
  loadWorkspaceFilesPayload,
  showWorkspaceViewer,
  touchWorkspaceFile,
  writeWorkspaceTextFile,
  workspaceCanWrite,
};
