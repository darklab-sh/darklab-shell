// ── Anonymous session ID ──
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
