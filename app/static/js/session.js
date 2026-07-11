// ── Shared utility module ──
import { DarklabSessionCore as importedSessionCore } from './core/session_core.js';
import { loadSessionPreferences as importedLoadSessionPreferences } from './features/preferences/preferences.js';
import { loadSessionVariables as importedLoadSessionVariables } from './features/autocomplete/runtime_context.js';
import { getActiveTeamId as importedGetActiveTeamId } from './features/team_scope.js';
import { refreshWorkspaceFileCache as importedRefreshWorkspaceFileCache } from './features/workspace/workspace_autocomplete_cache.js';
import { setRuntimeHandlers as importedSetRuntimeHandlers } from './runtime_bridge.js';
import { updateOptionsSessionTokenStatus as importedUpdateOptionsSessionTokenStatus } from './features/preferences/session_token_bridge.js';
import {
  hasSecretsHandler as importedHasSecretsHandler,
  invalidateOptionsSecrets as importedInvalidateOptionsSecrets,
  refreshOptionsSecrets as importedRefreshOptionsSecrets,
} from './features/preferences/secrets_bridge.js';

// Session identity: check for a persistent session token first (set by
// 'session-token generate' / 'session-token set'), then fall back to the
// auto-generated UUID.  The UUID is always preserved so clearing a session
// token reverts to the original anonymous session rather than losing identity.
var SessionCore = typeof importedSessionCore !== 'undefined' && importedSessionCore
  ? importedSessionCore
  : null;

var SESSION_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

function _sessionCore() {
  return (typeof importedSessionCore !== 'undefined' && importedSessionCore)
    || SessionCore
    || (SESSION_GLOBAL && SESSION_GLOBAL.DarklabSessionCore)
    || null;
}

function _sessionStorageFallback() {
  const data = new Map();
  return {
    getItem(key) {
      return data.has(String(key)) ? data.get(String(key)) : null;
    },
    setItem(key, value) {
      data.set(String(key), String(value));
    },
    removeItem(key) {
      data.delete(String(key));
    },
  };
}

function _sessionStorage() {
  if (typeof localStorage !== 'undefined' && localStorage) return localStorage;
  if (SESSION_GLOBAL && SESSION_GLOBAL.localStorage) return SESSION_GLOBAL.localStorage;
  if (!SESSION_GLOBAL.__darklabSessionMemoryStorage) {
    SESSION_GLOBAL.__darklabSessionMemoryStorage = _sessionStorageFallback();
  }
  return SESSION_GLOBAL.__darklabSessionMemoryStorage;
}

function _generateUUID() {
  const cryptoApi = typeof crypto !== 'undefined' ? crypto : SESSION_GLOBAL.crypto;
  return _sessionCore().generateUUID(cryptoApi);
}

var _sessionStorageApi = null;
var _sessionUuid = '';
var CLIENT_ID = '';
var SESSION_ID = '';
const SESSION_REFRESH_TASKS = [
  'reloadSessionHistory',
  'loadSessionPreferences',
  'loadSessionVariables',
  'loadRecentValues',
  'loadScheduleAutocompleteHints',
  'loadWatcherAutocompleteHints',
  'refreshWorkspaceFileCache',
  'refreshTeamScopes',
  'refreshActiveProjectContext',
  'refreshOptionsSecrets',
];

function _ensureSessionIdentity() {
  if (_sessionStorageApi && CLIENT_ID && SESSION_ID) return;
  const core = _sessionCore();
  _sessionStorageApi = _sessionStorage();
  _sessionUuid = core.getOrCreateStorageValue(_sessionStorageApi, 'session_id', _generateUUID);
  CLIENT_ID = core.getOrCreateStorageValue(_sessionStorageApi, 'client_id', _generateUUID);
  SESSION_ID = core.resolveSessionId(_sessionStorageApi, _sessionUuid);
}

function _refreshWorkspaceFileCache() {
  const refresh = (typeof importedRefreshWorkspaceFileCache !== 'undefined' && importedRefreshWorkspaceFileCache)
    || SESSION_GLOBAL.refreshWorkspaceFileCache;
  if (typeof refresh === 'function') return refresh();
  return null;
}

function _sessionLogEvent(context, event, level, details = {}) {
  logClientError(context, null, {
    event,
    level,
    ...details,
  });
}

function _sessionLogRefreshTaskFailed(task, err, reason) {
  _sessionLogEvent('session refresh task failed', 'SESSION_REFRESH_TASK_FAILED', 'warning', {
    task,
    reason,
    has_token: String(SESSION_ID || '').startsWith('tok_'),
  });
  if (typeof console !== 'undefined' && typeof console.warn === 'function') {
    console.warn(`[client] session refresh task failed: ${task}`, err);
  }
}

function _sessionLogIdentityUpdated(reason) {
  _sessionLogEvent('session identity updated', 'SESSION_ID_UPDATED', 'info', {
    reason,
    has_token: String(SESSION_ID || '').startsWith('tok_'),
    refresh_tasks: SESSION_REFRESH_TASKS,
  });
}

function _sessionCallAsync(name, reason = 'session-update') {
  const importedFns = {
    loadSessionPreferences: importedLoadSessionPreferences,
    loadSessionVariables: importedLoadSessionVariables,
  };
  const importedFn = importedFns[name];
  const fn = typeof importedFn === 'function'
    ? importedFn
    : (SESSION_GLOBAL && typeof SESSION_GLOBAL[name] === 'function' ? SESSION_GLOBAL[name] : null);
  if (!fn) return;
  const result = fn();
  if (result && typeof result.catch === 'function') {
    result.catch((err) => {
      _sessionLogRefreshTaskFailed(name, err, reason);
    });
  }
}

function _sessionRefreshOptionsSecretsIfOpen(reason = 'session-update') {
  const isOpen = typeof SESSION_GLOBAL.isOptionsOverlayOpen === 'function' ? SESSION_GLOBAL.isOptionsOverlayOpen : null;
  const refresh = (
    typeof importedHasSecretsHandler === 'function'
    && importedHasSecretsHandler('refreshOptionsSecrets')
    && typeof importedRefreshOptionsSecrets === 'function'
      ? importedRefreshOptionsSecrets
      : null
  ) || (typeof SESSION_GLOBAL.refreshOptionsSecrets === 'function' ? SESSION_GLOBAL.refreshOptionsSecrets : null);
  if (refresh && isOpen && isOpen()) {
    refresh({ force: true }).catch((err) => {
      _sessionLogRefreshTaskFailed('refreshOptionsSecrets', err, reason);
    });
  }
}

function _sessionInvalidateOptionsSecrets() {
  const invalidate = (
    typeof importedHasSecretsHandler === 'function'
    && importedHasSecretsHandler('invalidateOptionsSecrets')
    && typeof importedInvalidateOptionsSecrets === 'function'
      ? importedInvalidateOptionsSecrets
      : null
  ) || (typeof SESSION_GLOBAL.invalidateOptionsSecrets === 'function' ? SESSION_GLOBAL.invalidateOptionsSecrets : null);
  if (invalidate) invalidate();
}

function _sessionUpdateOptionsSessionTokenStatus() {
  if (typeof importedUpdateOptionsSessionTokenStatus === 'function') {
    importedUpdateOptionsSessionTokenStatus();
  }
}

if (typeof window !== 'undefined') {
}

// Update SESSION_ID at runtime after a session token is set, changed, or
// cleared.  Called by the session-token terminal commands after they update
// localStorage — avoids a page reload to apply the new identity.
function updateSessionId(newId) {
  _ensureSessionIdentity();
  SESSION_ID = newId || _sessionCore().resolveSessionId(_sessionStorageApi, _sessionUuid);
  _sessionLogIdentityUpdated('local-update');
  _sessionCallAsync('loadSessionPreferences', 'local-update');
  _sessionCallAsync('loadSessionVariables', 'local-update');
  _sessionCallAsync('loadRecentValues', 'local-update');
  _sessionCallAsync('loadScheduleAutocompleteHints', 'local-update');
  _sessionCallAsync('loadWatcherAutocompleteHints', 'local-update');
  _refreshWorkspaceFileCache()?.catch?.((err) => {
    _sessionLogRefreshTaskFailed('refreshWorkspaceFileCache', err, 'local-update');
  });
  _sessionCallAsync('refreshTeamScopes', 'local-update');
  _sessionCallAsync('refreshActiveProjectContext', 'local-update');
  _sessionInvalidateOptionsSecrets();
  _sessionRefreshOptionsSecretsIfOpen('local-update');
}

function getSessionId() {
  _ensureSessionIdentity();
  return SESSION_ID;
}

function getClientId() {
  _ensureSessionIdentity();
  return CLIENT_ID;
}

// Keep SESSION_ID current in other open tabs when session_token changes in
// localStorage (the storage event only fires in tabs that did not make the
// change, so this does not double-apply in the tab that called updateSessionId).
// Also reload starred commands, recent chips, and the options-panel token
// display so passive tabs reflect the new session identity immediately.
if (SESSION_GLOBAL && typeof SESSION_GLOBAL.addEventListener === 'function') {
  SESSION_GLOBAL.addEventListener('storage', (e) => {
    if (e.key === 'session_token') {
      _ensureSessionIdentity();
      SESSION_ID = e.newValue || _sessionUuid;
      _sessionLogIdentityUpdated('storage-event');
      _sessionCallAsync('reloadSessionHistory', 'storage-event');
      _sessionCallAsync('loadSessionPreferences', 'storage-event');
      _sessionCallAsync('loadSessionVariables', 'storage-event');
      _sessionCallAsync('loadRecentValues', 'storage-event');
      _sessionCallAsync('loadScheduleAutocompleteHints', 'storage-event');
      _sessionCallAsync('loadWatcherAutocompleteHints', 'storage-event');
      _refreshWorkspaceFileCache()?.catch?.((err) => {
        _sessionLogRefreshTaskFailed('refreshWorkspaceFileCache', err, 'storage-event');
      });
      _sessionCallAsync('refreshTeamScopes', 'storage-event');
      _sessionCallAsync('refreshActiveProjectContext', 'storage-event');
      _sessionUpdateOptionsSessionTokenStatus();
      _sessionInvalidateOptionsSecrets();
      _sessionRefreshOptionsSecretsIfOpen('storage-event');
    }
  });
}

// Return a display-safe masked version of a session token or UUID.
// tok_a1b2c3d4... → tok_a1b2••••
// uuid...         → 8-char-prefix••••••••
function maskSessionToken(token) {
  return _sessionCore().maskSessionToken(token);
}

// Wrapper around fetch that always includes the session ID header so every API
// request stays scoped to the same anonymous browser session.
function apiFetch(url, options = {}) {
  _ensureSessionIdentity();
  const requestOptions = _sessionCore().withSessionHeaders(options, SESSION_ID, CLIENT_ID);
  const teamId = typeof importedGetActiveTeamId === 'function'
    ? importedGetActiveTeamId()
    : '';
  if (teamId) {
    requestOptions.headers = Object.assign({}, requestOptions.headers || {}, { 'X-Team-ID': teamId });
  }
  return fetch(url, requestOptions);
}

function describeFetchError(err, context = 'server') {
  return _sessionCore().describeFetchError(err, context);
}

function _sanitizeClientLogSrc(value) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  try {
    const parsed = new URL(raw, SESSION_GLOBAL?.location?.href || 'http://localhost/');
    const version = parsed.searchParams.get('v');
    return version ? `${parsed.pathname}?v=${encodeURIComponent(version)}` : parsed.pathname;
  } catch (_) {
    return raw.split('?', 1)[0].slice(0, 300);
  }
}

function _sanitizeClientLogMessage(value) {
  return String(value || '').replace(/((?:https?:\/\/|\/)[^\s'"<>]+)/g, (match) => (
    _sanitizeClientLogSrc(match)
  ));
}

function _clientLogConsoleMethod(details) {
  const level = String(details && details.level || 'warning').toLowerCase();
  if (level === 'debug') return 'debug';
  if (level === 'error') return 'error';
  if (level === 'info') return 'info';
  return 'warn';
}

function logClientError(context, err, details = null) {
  const consoleMethod = _clientLogConsoleMethod(details);
  const consoleLog = typeof console !== 'undefined' && (console[consoleMethod] || console.warn);
  if (typeof consoleLog === 'function') {
    consoleLog.call(console, `[client] ${context}`, err);
  }
  const message = _sanitizeClientLogMessage(
    (err && typeof err.message === 'string') ? err.message : String(err || ''),
  );
  const body = { context, message };
  if (details && typeof details === 'object' && !Array.isArray(details)) {
    body.details = { ...details };
    if (err && typeof err === 'object') {
      if (!body.details.error_name && typeof err.name === 'string') body.details.error_name = err.name;
      if (!body.details.status && typeof err.status !== 'undefined') body.details.status = err.status;
    }
    if (typeof details.event === 'string') body.event = details.event;
    if (typeof details.level === 'string') body.level = details.level;
  }
  apiFetch('/log', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).catch((deliveryErr) => {
    const fallback = typeof console !== 'undefined' && (console.error || console.warn);
    if (typeof fallback === 'function') {
      fallback.call(console, '[client] failed to deliver client log', {
        event: 'CLIENT_LOG_DELIVERY_FAILED',
        level: 'error',
        context,
        source_event: body.event || '',
        message: deliveryErr && deliveryErr.message ? deliveryErr.message : String(deliveryErr || ''),
      });
    }
  });
}

if (typeof window !== 'undefined') {
  if (typeof importedSetRuntimeHandlers === 'function') {
    importedSetRuntimeHandlers({
      apiFetch,
      getSessionId,
      logClientError,
    });
  }
}

export {
  apiFetch,
  describeFetchError,
  getClientId,
  getSessionId,
  logClientError,
  maskSessionToken,
  updateSessionId,
};

_ensureSessionIdentity();
