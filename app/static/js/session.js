// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// ── Shared utility module ──
import { DarklabSessionCore as importedSessionCore } from './core/session_core.js';
import { getAppConfig as importedGetAppConfig } from './core/config.js';
import { redeemStoredCredential as importedRedeemStoredCredential, rememberBrowserSession as importedRememberBrowserSession } from './core/browser_credentials.js';
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

// Authenticated browsers use a protected cookie; anonymous browsers use a UUID.
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

function _browserSessionEnabled() {
  const config = typeof importedGetAppConfig === 'function' ? importedGetAppConfig() : {};
  return ['token_required', 'oidc_required', 'mixed'].includes(config?.access_profile)
    || Boolean(_cookieValue('darklab_csrf')) || Boolean(_sessionStorage().getItem('browser_session'));
}

function _browserSessionIdentity({ initial = false } = {}) {
  const config = typeof importedGetAppConfig === 'function' ? importedGetAppConfig() : {};
  const saved = _sessionStorageApi.getItem('browser_session');
  const loaded = config?.browser_identity?.credential_id || config?.browser_identity?.principal_id;
  const publicId = (initial ? loaded : saved) || loaded || saved || 'browser-session';
  _sessionStorageApi.setItem('browser_session', publicId);
  return Object.freeze({ kind: 'browser_session', publicId });
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
var _sessionCsrfToken = '';
var _identityNavigationPending = false;
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
  _sessionCsrfToken = _cookieValue('darklab_csrf');
  if (_browserSessionEnabled()) {
    // A credential redeemed by the server must never survive in browser
    // storage or enter normal application JavaScript.
    _sessionStorageApi.removeItem('access_credential');
    // Keep an unrelated anonymous workspace available after explicit sign-out.
    _sessionUuid = _sessionStorageApi.getItem('anonymous_id') || '';
    _browserIdentity = _browserSessionIdentity({ initial: true });
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
    authenticated: _browserIdentity?.kind === 'browser_session',
  });
  if (typeof console !== 'undefined' && typeof console.warn === 'function') {
    console.warn(`[client] session refresh task failed: ${task}`, err);
  }
}

function _sessionLogIdentityUpdated(reason) {
  _sessionLogEvent('session identity updated', 'SESSION_ID_UPDATED', 'info', {
    reason,
    authenticated: _browserIdentity?.kind === 'browser_session',
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
  _browserIdentity = _browserSessionEnabled()
    ? _browserSessionIdentity()
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

function activateAccessCredential(secret, { attached = false, refresh = true } = {}) {
  _ensureSessionIdentity();
  const normalized = String(secret || '').trim();
  if (!_sessionCore().credentialPublicId(normalized).startsWith('crd_')) {
    throw new Error('Invalid access credential format');
  }
  if (!_cookieValue('darklab_csrf')) throw new Error('Sign-in needs HTTPS and browser cookies.');
  _sessionCsrfToken = _cookieValue('darklab_csrf');
  importedRememberBrowserSession(_sessionStorageApi, { credential_id: _sessionCore().credentialPublicId(normalized) });
  if (attached) {
    // The former anonymous identity is retired by attachment. Do not reuse it.
    _sessionUuid = _generateUUID();
    _sessionStorageApi.setItem('anonymous_id', _sessionUuid);
  }
  if (refresh) _applyIdentityChange('browser-session-activated');
  else _identityNavigationPending = true;
}

function clearAccessCredential({ freshAnonymous = true } = {}) {
  _ensureSessionIdentity();
  const hadCredential = _browserIdentity?.kind === 'credential';
  _sessionStorageApi.removeItem('access_credential');
  _sessionStorageApi.removeItem('browser_session');
  _credentialMigration = null;
  if (_browserSessionEnabled()) {
    return;
  }
  if (freshAnonymous && hadCredential) {
    _sessionUuid = _generateUUID();
    _sessionStorageApi.setItem('anonymous_id', _sessionUuid);
  }
  _sessionUuid ||= _sessionCore().getOrCreateStorageValue(_sessionStorageApi, 'anonymous_id', _generateUUID);
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
    credentialId: _browserIdentity.publicId.startsWith('crd_')
      ? _browserIdentity.publicId
      : '',
    validFormat: _browserIdentity.kind === 'browser_session' || _browserIdentity.publicId !== 'credential-invalid',
  });
}

// Keep browser identity current in other tabs. The initiating tab refreshes
// directly because the storage event only fires in the other tabs.
if (SESSION_GLOBAL && typeof SESSION_GLOBAL.addEventListener === 'function') {
  SESSION_GLOBAL.addEventListener('storage', (e) => {
    if (['access_credential', 'anonymous_id', 'browser_session'].includes(e.key)) {
      _credentialMigration = null;
      if (e.key === 'browser_session') {
        SESSION_GLOBAL.location?.reload?.();
      } else _applyIdentityChange('storage-event');
    }
  });
}

// Wrapper around fetch that sends exactly one browser identity header.
let _signInNavigationPending = false;
const BROWSER_SESSION_ERRORS = new Set([
  'credential_required', 'idle_browser_session', 'expired_browser_session',
  'revoked_browser_session', 'unknown_browser_session', 'malformed_browser_session',
]);

function redirectToSignIn() {
  const location = SESSION_GLOBAL?.location;
  if (_signInNavigationPending || !location || location.pathname.startsWith('/auth/')) return;
  _signInNavigationPending = true;
  // Carry only the local route. Query strings and fragments can contain
  // sensitive user input and must not enter the sign-in request or its logs.
  location.replace(`/auth/sign-in?next=${encodeURIComponent(location.pathname || '/')}`);
}

async function apiFetch(url, options = {}) {
  _ensureSessionIdentity();
  if (_identityNavigationPending) throw new Error('Browser access is changing.');
  if (_browserIdentity.kind === 'browser_session' && _cookieValue('darklab_csrf') !== _sessionCsrfToken) {
    _identityNavigationPending = true;
    SESSION_GLOBAL.location?.reload?.();
    throw new Error('Browser access changed in another tab.');
  }
  if (_browserIdentity.kind === 'credential' && url !== '/auth/credentials/redeem') {
    if (!_credentialMigration) {
      _credentialMigration = importedRedeemStoredCredential(_sessionStorageApi);
    }
    const migration = await _credentialMigration;
    if (migration && !migration.ok) return migration.clone();
    _browserIdentity = _browserSessionIdentity();
    SESSION_ID = _browserIdentity.publicId;
    _sessionCsrfToken = _cookieValue('darklab_csrf');
    // Server-rendered navigation and all cached state must belong to this
    // session before any normal request continues under its authority.
    if (!_identityNavigationPending) {
      _identityNavigationPending = true;
      SESSION_GLOBAL.location?.reload?.();
    }
    throw new Error('Browser sign-in completed. Reloading.');
  }
  const requestOptions = _sessionCore().withIdentityHeaders(options, _browserIdentity, CLIENT_ID);
  const teamId = typeof importedGetActiveTeamId === 'function'
    ? importedGetActiveTeamId()
    : '';
  if (teamId) {
    requestOptions.headers = Object.assign({}, requestOptions.headers || {}, { 'X-Team-ID': teamId });
  }
  const method = String(requestOptions.method || 'GET').toUpperCase();
  if (_browserSessionEnabled() && !['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
    const csrfToken = _cookieValue('darklab_csrf');
    if (csrfToken) {
      requestOptions.headers = Object.assign({}, requestOptions.headers || {}, {
        'X-Darklab-CSRF': csrfToken,
      });
    }
  }
  const response = await fetch(url, requestOptions);
  // A successful local mutation may rotate the session (for example Team roles).
  // Other tabs detect that cookie change before sending another scoped request.
  if (response.ok && !['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
    _sessionCsrfToken = _cookieValue('darklab_csrf');
  }
  if (_browserSessionEnabled() && response.status === 401) {
    try {
      const payload = await response.clone().json();
      const code = typeof payload.error === 'string' ? payload.error : payload.error?.code;
      if (BROWSER_SESSION_ERRORS.has(code)) redirectToSignIn();
    } catch (_) {
      // Keep the original response available for the caller's error handling.
    }
  }
  return response;
}

var _credentialMigration = null;

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
  redirectToSignIn,
};

_ensureSessionIdentity();
