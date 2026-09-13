// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// ── Shared utility module ──
import { DarklabSessionCore as importedSessionCore } from './core/session_core.js';
import { getAppConfig as importedGetAppConfig } from './core/config.js';
import { loadSessionPreferences as importedLoadSessionPreferences } from './features/preferences/preferences.js';
import { loadSessionVariables as importedLoadSessionVariables } from './features/autocomplete/runtime_context.js';
import { getActiveTeamId as importedGetActiveTeamId } from './features/team_scope.js';
import { refreshWorkspaceFileCache as importedRefreshWorkspaceFileCache } from './features/workspace/workspace_autocomplete_cache.js';
import { setRuntimeHandlers as importedSetRuntimeHandlers } from './runtime_bridge.js';
import {
  hasSecretsHandler as importedHasSecretsHandler,
  invalidateOptionsSecrets as importedInvalidateOptionsSecrets,
  refreshOptionsSecrets as importedRefreshOptionsSecrets,
} from './features/preferences/secrets_bridge.js';

// Browser identity uses either one portable access credential or one anonymous
// UUID. Reusable credential secrets stay out of UI state and cache keys.
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

function _restrictedBrowserSessionEnabled() {
  const config = typeof importedGetAppConfig === 'function' ? importedGetAppConfig() : {};
  return ['token_required', 'oidc_required', 'mixed'].includes(config?.access_profile);
}

function _cookieValue(name) {
  if (typeof document === 'undefined') return '';
  const prefix = `${encodeURIComponent(name)}=`;
  const item = String(document.cookie || '').split(';').map(value => value.trim())
    .find(value => value.startsWith(prefix));
  return item ? decodeURIComponent(item.slice(prefix.length)) : '';
}

var _sessionStorageApi = null;
var _sessionUuid = '';
var _browserIdentity = null;
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
  CLIENT_ID = core.getOrCreateStorageValue(_sessionStorageApi, 'client_id', _generateUUID);
  if (_restrictedBrowserSessionEnabled()) {
    // A credential redeemed by the server must never survive in browser
    // storage or enter normal application JavaScript.
    _sessionStorageApi.removeItem('access_credential');
    _sessionStorageApi.removeItem('anonymous_id');
    _sessionUuid = '';
    _browserIdentity = Object.freeze({ kind: 'browser_session', publicId: 'browser-session' });
    SESSION_ID = _browserIdentity.publicId;
    return;
  }
  _sessionUuid = core.getOrCreateStorageValue(_sessionStorageApi, 'anonymous_id', _generateUUID);
  _browserIdentity = core.resolveBrowserIdentity(_sessionStorageApi, _sessionUuid);
  SESSION_ID = _browserIdentity.publicId;
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
    authenticated: _browserIdentity?.kind === 'credential',
  });
  if (typeof console !== 'undefined' && typeof console.warn === 'function') {
    console.warn(`[client] session refresh task failed: ${task}`, err);
  }
}

function _sessionLogIdentityUpdated(reason) {
  _sessionLogEvent('session identity updated', 'SESSION_ID_UPDATED', 'info', {
    reason,
    authenticated: _browserIdentity?.kind === 'credential',
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

function _emitIdentityChanged(reason) {
  if (!SESSION_GLOBAL || typeof SESSION_GLOBAL.dispatchEvent !== 'function') return;
  const EventCtor = SESSION_GLOBAL.CustomEvent || globalThis.CustomEvent;
  if (typeof EventCtor !== 'function') return;
  SESSION_GLOBAL.dispatchEvent(new EventCtor('app:identity-changed', {
    detail: { reason, identity: getBrowserIdentitySnapshot() },
  }));
}

function _applyIdentityChange(reason) {
  _ensureSessionIdentity();
  _browserIdentity = _restrictedBrowserSessionEnabled()
    ? Object.freeze({ kind: 'browser_session', publicId: 'browser-session' })
    : _sessionCore().resolveBrowserIdentity(_sessionStorageApi, _sessionUuid);
  SESSION_ID = _browserIdentity.publicId;
  _sessionLogIdentityUpdated(reason);
  _sessionCallAsync('reloadSessionHistory', reason);
  _sessionCallAsync('loadSessionPreferences', reason);
  _sessionCallAsync('loadSessionVariables', reason);
  _sessionCallAsync('loadRecentValues', reason);
  _sessionCallAsync('loadScheduleAutocompleteHints', reason);
  _sessionCallAsync('loadWatcherAutocompleteHints', reason);
  _refreshWorkspaceFileCache()?.catch?.((err) => {
    _sessionLogRefreshTaskFailed('refreshWorkspaceFileCache', err, reason);
  });
  _sessionCallAsync('refreshTeamScopes', reason);
  _sessionCallAsync('refreshActiveProjectContext', reason);
  _sessionInvalidateOptionsSecrets();
  _sessionRefreshOptionsSecretsIfOpen(reason);
  _emitIdentityChanged(reason);
}

function activateAccessCredential(secret) {
  _ensureSessionIdentity();
  if (_restrictedBrowserSessionEnabled()) {
    _sessionStorageApi.removeItem('access_credential');
    _applyIdentityChange('browser-session-activated');
    return;
  }
  const normalized = String(secret || '').trim();
  if (!_sessionCore().credentialPublicId(normalized).startsWith('crd_')) {
    throw new Error('Invalid access credential format');
  }
  _sessionStorageApi.setItem('access_credential', normalized);
  _applyIdentityChange('credential-activated');
}

function clearAccessCredential({ freshAnonymous = true } = {}) {
  _ensureSessionIdentity();
  const hadCredential = _browserIdentity?.kind === 'credential';
  _sessionStorageApi.removeItem('access_credential');
  if (_restrictedBrowserSessionEnabled()) {
    _applyIdentityChange('browser-session-cleared');
    return;
  }
  if (freshAnonymous && hadCredential) {
    _sessionUuid = _generateUUID();
    _sessionStorageApi.setItem('anonymous_id', _sessionUuid);
  }
  _applyIdentityChange('credential-removed');
}

function getSessionId() {
  _ensureSessionIdentity();
  return SESSION_ID;
}

function getClientId() {
  _ensureSessionIdentity();
  return CLIENT_ID;
}

function getBrowserIdentitySnapshot() {
  _ensureSessionIdentity();
  return Object.freeze({
    kind: _browserIdentity.kind,
    anonymousId: _browserIdentity.kind === 'anonymous' ? _browserIdentity.anonymousId : '',
    credentialId: _browserIdentity.kind === 'credential' && _browserIdentity.publicId !== 'credential-invalid'
      ? _browserIdentity.publicId
      : '',
    validFormat: _browserIdentity.kind === 'browser_session' || _browserIdentity.publicId !== 'credential-invalid',
  });
}

// Keep browser identity current in other tabs. The initiating tab refreshes
// directly because the storage event only fires in the other tabs.
if (SESSION_GLOBAL && typeof SESSION_GLOBAL.addEventListener === 'function') {
  SESSION_GLOBAL.addEventListener('storage', (e) => {
    if (e.key === 'access_credential' || e.key === 'anonymous_id') _applyIdentityChange('storage-event');
  });
}

// Wrapper around fetch that sends exactly one browser identity header.
function apiFetch(url, options = {}) {
  _ensureSessionIdentity();
  const requestOptions = _sessionCore().withIdentityHeaders(options, _browserIdentity, CLIENT_ID);
  const teamId = typeof importedGetActiveTeamId === 'function'
    ? importedGetActiveTeamId()
    : '';
  if (teamId) {
    requestOptions.headers = Object.assign({}, requestOptions.headers || {}, { 'X-Team-ID': teamId });
  }
  const method = String(requestOptions.method || 'GET').toUpperCase();
  if (_restrictedBrowserSessionEnabled() && !['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
    const csrfToken = _cookieValue('darklab_csrf');
    if (csrfToken) {
      requestOptions.headers = Object.assign({}, requestOptions.headers || {}, {
        'X-Darklab-CSRF': csrfToken,
      });
    }
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
  activateAccessCredential,
  apiFetch,
  clearAccessCredential,
  describeFetchError,
  getBrowserIdentitySnapshot,
  getClientId,
  getSessionId,
  logClientError,
};

_ensureSessionIdentity();
