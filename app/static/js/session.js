// ── Shared utility module ──
// Session identity: check for a persistent session token first (set by
// 'session-token generate' / 'session-token set'), then fall back to the
// auto-generated UUID.  The UUID is always preserved so clearing a session
// token reverts to the original anonymous session rather than losing identity.
function _generateUUID() {
  // crypto.randomUUID() requires a secure context (HTTPS or localhost).
  // Fall back to crypto.getRandomValues() for HTTP LAN deployments
  // (e.g. accessing the app at http://192.168.x.x from a mobile device).
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    try { return crypto.randomUUID(); } catch (_) {}
  }
  const b = new Uint8Array(16);
  (window.crypto || crypto).getRandomValues(b);
  b[6] = (b[6] & 0x0f) | 0x40; // version 4
  b[8] = (b[8] & 0x3f) | 0x80; // variant bits
  const h = Array.from(b, x => x.toString(16).padStart(2, '0'));
  return `${h.slice(0,4).join('')}-${h.slice(4,6).join('')}-${h.slice(6,8).join('')}-${h.slice(8,10).join('')}-${h.slice(10).join('')}`;
}

let _sessionUuid = localStorage.getItem('session_id');
if (!_sessionUuid) {
  _sessionUuid = _generateUUID();
  localStorage.setItem('session_id', _sessionUuid);
}

let CLIENT_ID = localStorage.getItem('client_id');
if (!CLIENT_ID) {
  CLIENT_ID = _generateUUID();
  localStorage.setItem('client_id', CLIENT_ID);
}

let SESSION_ID = localStorage.getItem('session_token') || _sessionUuid;

// Update SESSION_ID at runtime after a session token is set, changed, or
// cleared.  Called by the session-token terminal commands after they update
// localStorage — avoids a page reload to apply the new identity.
function updateSessionId(newId) {
  SESSION_ID = newId || localStorage.getItem('session_token') || _sessionUuid;
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
  if (typeof token !== 'string' || !token) return '(none)';
  if (token.startsWith('tok_')) return 'tok_' + token.slice(4, 8) + '••••';
  return token.slice(0, 8) + '••••••••';
}

// Wrapper around fetch that always includes the session ID header so every API
// request stays scoped to the same anonymous browser session.
function apiFetch(url, options = {}) {
  options.headers = Object.assign({}, options.headers || {}, {
    'X-Session-ID': SESSION_ID,
    'X-Client-ID': CLIENT_ID
  });
  return fetch(url, options);
}

function describeFetchError(err, context = 'server') {
  const offlineMessage = `Unable to contact the ${context} right now. Please try again in a moment. If this keeps happening, contact the shell operator.`;
  const message = (err && typeof err.message === 'string') ? err.message.trim() : '';
  if (!message) return offlineMessage;
  const lower = message.toLowerCase();
  if (lower.includes('networkerror') || lower.includes('failed to fetch') || lower.includes('network down') || lower.includes('load failed')) {
    return offlineMessage;
  }
  return `Request to the ${context} failed: ${message}`;
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
