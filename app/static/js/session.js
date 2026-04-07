// ── Shared utility module ──
// Generated once per browser, persisted in localStorage.
// Sent as X-Session-ID on every API request so run history is scoped per user.
let SESSION_ID = localStorage.getItem('session_id');
if (!SESSION_ID) {
  SESSION_ID = crypto.randomUUID();
  localStorage.setItem('session_id', SESSION_ID);
}

// Wrapper around fetch that always includes the session ID header
function apiFetch(url, options = {}) {
  options.headers = Object.assign({}, options.headers || {}, {
    'X-Session-ID': SESSION_ID
  });
  return fetch(url, options);
}

function describeFetchError(err, context = 'server') {
  const message = (err && typeof err.message === 'string') ? err.message.trim() : '';
  if (!message) return `Unable to reach the ${context}. Check that it is running and try again.`;
  const lower = message.toLowerCase();
  if (lower.includes('networkerror') || lower.includes('failed to fetch') || lower.includes('network down') || lower.includes('load failed')) {
    return `Unable to reach the ${context}. Check that it is running and try again.`;
  }
  return `Request to the ${context} failed: ${message}`;
}

function logClientError(context, err) {
  if (typeof console !== 'undefined' && typeof console.warn === 'function') {
    console.warn(`[client] ${context}`, err);
  }
}
