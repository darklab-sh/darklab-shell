// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Only the one-time upgrade path reads an old browser-stored credential.
// Normal requests use the HttpOnly cookie and never carry that secret.
function browserCookie(name) {
  const prefix = `${encodeURIComponent(name)}=`;
  const item = String(document.cookie || '').split(';').map(value => value.trim())
    .find(value => value.startsWith(prefix));
  return item ? decodeURIComponent(item.slice(prefix.length)) : '';
}

function rememberBrowserSession(storage, authentication = {}) {
  const publicId = authentication.credential_id || authentication.principal_id || 'browser-session';
  storage.setItem('browser_session', publicId);
  storage.removeItem('access_credential');
  return publicId;
}

async function redeemStoredCredential(storage) {
  const secret = storage.getItem('access_credential');
  if (!secret) return null;
  const csrf = browserCookie('darklab_csrf');
  const response = await fetch('/auth/credentials/redeem', {
    method: 'POST', credentials: 'same-origin', cache: 'no-store',
    headers: { 'Content-Type': 'application/json', ...(csrf ? { 'X-Darklab-CSRF': csrf } : {}) },
    body: JSON.stringify({ secret }),
  });
  if (response.ok) {
    if (!browserCookie('darklab_csrf')) throw new Error('Sign-in needs HTTPS and browser cookies.');
    const payload = await response.clone().json();
    rememberBrowserSession(storage, payload.authentication);
  }
  return response;
}

export { browserCookie, rememberBrowserSession, redeemStoredCredential };
