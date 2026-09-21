// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { browserCookie, redeemStoredCredential } from './core/browser_credentials.js';

const recovery = document.querySelector('[data-browser-sign-in]');
if (recovery) {
  const saved = recovery.querySelector('[data-use-saved-credential]');
  const anonymous = recovery.querySelector('[data-continue-anonymous]');
  const message = recovery.querySelector('[role="status"]');
  const discard = recovery.querySelector('[data-remove-saved-credential]');
  const hasSaved = Boolean(localStorage.getItem('access_credential'));
  if (discard) {
    discard.closest('label').classList.toggle('u-hidden', !hasSaved);
    discard.addEventListener('change', () => { anonymous.disabled = hasSaved && !discard.checked; });
  }
  if (saved) {
    saved.classList.toggle('u-hidden', !hasSaved);
    saved.disabled = false;
    saved.addEventListener('click', async () => {
      saved.disabled = true;
      try {
        const response = await redeemStoredCredential(localStorage);
        if (!response?.ok) throw new Error('Sign-in failed');
        window.location.assign(recovery.dataset.next || '/');
      } catch (_) {
        message.textContent = 'The saved credential could not be exchanged. Check HTTPS and cookies, or sign in with an active credential.';
        saved.disabled = false;
      }
    });
  }
  anonymous?.addEventListener('click', async () => {
    if (localStorage.getItem('access_credential') && !discard?.checked) return;
    anonymous.disabled = true;
    try {
      const csrf = browserCookie('darklab_csrf');
      const response = await fetch('/auth/logout', {
        method: 'POST', credentials: 'same-origin', cache: 'no-store',
        headers: csrf ? { 'X-Darklab-CSRF': csrf } : {},
      });
      if (!response.ok) throw new Error('Sign-out failed');
      localStorage.removeItem('access_credential');
      localStorage.removeItem('browser_session');
      window.location.assign('/');
    } catch (_) {
      message.textContent = 'Could not sign out. Reload this page and try again.';
      anonymous.disabled = false;
    }
  });
  if (anonymous) anonymous.disabled = hasSaved && !discard?.checked;
}
