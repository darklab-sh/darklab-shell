// ── Shared utility module ──
// Session identity: check for a persistent session token first (set by
// 'session-token generate' / 'session-token set'), then fall back to the
// auto-generated UUID.  The UUID is always preserved so clearing a session
// token reverts to the original anonymous session rather than losing identity.
const SessionCore = window.DarklabSessionCore;

function _generateUUID() {
  return SessionCore.generateUUID(typeof crypto !== 'undefined' ? crypto : window.crypto);
}

let _sessionUuid = SessionCore.getOrCreateStorageValue(localStorage, 'session_id', _generateUUID);

let CLIENT_ID = SessionCore.getOrCreateStorageValue(localStorage, 'client_id', _generateUUID);

let SESSION_ID = SessionCore.resolveSessionId(localStorage, _sessionUuid);

// Update SESSION_ID at runtime after a session token is set, changed, or
// cleared.  Called by the session-token terminal commands after they update
// localStorage — avoids a page reload to apply the new identity.
function updateSessionId(newId) {
  SESSION_ID = newId || SessionCore.resolveSessionId(localStorage, _sessionUuid);
  if (typeof loadSessionPreferences === 'function') {
    loadSessionPreferences().catch(() => {});
  }
  if (typeof loadSessionVariables === 'function') {
    loadSessionVariables().catch(() => {});
  }
  if (typeof loadRecentDomains === 'function') {
    loadRecentDomains().catch(() => {});
  }
}

// Keep SESSION_ID current in other open tabs when session_token changes in
// localStorage (the storage event only fires in tabs that did not make the
// change, so this does not double-apply in the tab that called updateSessionId).
// Also reload starred commands, recent chips, and the options-panel token
// display so passive tabs reflect the new session identity immediately.
window.addEventListener('storage', (e) => {
  if (e.key === 'session_token') {
    SESSION_ID = e.newValue || _sessionUuid;
    if (typeof reloadSessionHistory === 'function') reloadSessionHistory().catch(() => {});
    if (typeof loadSessionPreferences === 'function') loadSessionPreferences().catch(() => {});
    if (typeof loadSessionVariables === 'function') loadSessionVariables().catch(() => {});
    if (typeof loadRecentDomains === 'function') loadRecentDomains().catch(() => {});
    if (typeof _updateOptionsSessionTokenStatus === 'function') _updateOptionsSessionTokenStatus();
  }
});

// Return a display-safe masked version of a session token or UUID.
// tok_a1b2c3d4... → tok_a1b2••••
// uuid...         → 8-char-prefix••••••••
function maskSessionToken(token) {
  return SessionCore.maskSessionToken(token);
}

// Wrapper around fetch that always includes the session ID header so every API
// request stays scoped to the same anonymous browser session.
function apiFetch(url, options = {}) {
  return fetch(url, SessionCore.withSessionHeaders(options, SESSION_ID, CLIENT_ID));
}

function describeFetchError(err, context = 'server') {
  return SessionCore.describeFetchError(err, context);
}

function logClientError(context, err) {
  if (typeof console !== 'undefined' && typeof console.warn === 'function') {
    console.warn(`[client] ${context}`, err);
  }
  const message = (err && typeof err.message === 'string') ? err.message : String(err || '');
  apiFetch('/log', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ context, message }),
  }).catch(() => {});
}
