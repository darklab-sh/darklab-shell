// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

/** Keep standalone operator pages private when a session or grant expires. */
export function createOperatorAccess({ root = document.querySelector('main'), fetcher = fetch,
  navigate = path => window.location.assign(path) } = {}) {
  let active = true, timer = null, checking = false;
  const controllers = new Set();
  const lost = () => { throw new Error('Operator access unavailable'); };
  const verifyActive = () => { if (!active) lost(); };
  const safeDestination = value => {
    try {
      const url = new URL(value, window.location.origin);
      return url.origin === window.location.origin && ['/auth/sign-in', '/admin/reauth'].includes(url.pathname)
        ? url.pathname + url.search : null;
    } catch { return null; }
  };
  function clear(message = 'Operator access is unavailable.') {
    active = false;
    clearInterval(timer);
    for (const controller of controllers) controller.abort();
    controllers.clear();
    const text = document.createElement('p');
    text.setAttribute('role', 'status');
    text.textContent = message;
    root?.replaceChildren(text);
    document.querySelector('.diag-refreshed-at')?.replaceChildren();
    document.querySelector('.diag-live-indicator')?.classList.remove('refreshing');
  }
  async function request(url, options = {}) {
    verifyActive();
    const controller = new AbortController();
    controllers.add(controller);
    const headers = new Headers(options.headers);
    headers.set('X-Requested-With', 'XMLHttpRequest');
    if (!['GET', 'HEAD', 'OPTIONS'].includes(String(options.method || 'GET').toUpperCase())) {
      const cookie = document.cookie.split(';').map(part => part.trim()).find(part => part.startsWith('darklab_csrf='));
      if (cookie) headers.set('X-Darklab-CSRF', decodeURIComponent(cookie.slice('darklab_csrf='.length)));
    }
    try {
      const response = await fetcher(url, { ...options, headers, credentials: 'same-origin', cache: 'no-store',
        redirect: 'error', signal: controller.signal });
      verifyActive();
      let unavailable = [401, 403, 404].includes(response.status);
      if (response.status === 503) {
        const error = await response.clone().json().catch(() => null);
        unavailable = error?.error === 'operator_access_unavailable';
        verifyActive();
      }
      if (unavailable) {
        controllers.delete(controller);
        clear(response.status === 401 ? 'Sign in or verify your identity to continue.' : undefined);
        const data = await response.json().catch(() => null);
        const destination = safeDestination(data?.destination);
        if (destination) {
          const link = document.createElement('a');
          link.href = destination;
          link.className = 'diag-back-btn';
          link.textContent = data?.error === 'reauthentication_required' ? 'Verify operator access' : 'Sign in';
          root?.append(link);
          navigate(destination);
        }
        lost();
      }
      // Body reads can finish after another concurrent request has lost access.
      return {
        ok: response.ok, status: response.status, headers: response.headers,
        async json() { const body = await response.json(); verifyActive(); return body; },
        async text() { const body = await response.text(); verifyActive(); return body; },
        async blob() { const body = await response.blob(); verifyActive(); return body; },
      };
    } finally { controllers.delete(controller); }
  }
  async function check() {
    if (!active || checking || document.visibilityState === 'hidden') return;
    checking = true;
    try {
      const next = window.location.pathname + window.location.search;
      await request('/admin/access?next=' + encodeURIComponent(next));
    } catch { /* Authorization failures clear the page; connection failures retry later. */ }
    finally { checking = false; }
  }
  function start() {
    if (timer !== null) return;
    timer = setInterval(check, 10000);
    document.addEventListener('visibilitychange', check);
    window.addEventListener('pagehide', () => clear());
    window.addEventListener('pageshow', event => { if (event.persisted) window.location.reload(); });
  }
  return { fetch: request, check, start, clear, get active() { return active; } };
}
