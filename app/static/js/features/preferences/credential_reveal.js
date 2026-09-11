// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { copyTextToClipboard as importedCopyTextToClipboard } from '../../core/utils.js';

let activeReveal = null;

function clearCredentialReveal({ restoreFocus = true } = {}) {
  if (!activeReveal) return;
  const state = activeReveal;
  activeReveal = null;
  state.secret = '';
  state.host.replaceChildren();
  state.host.hidden = true;
  if (typeof state.onClosed === 'function') state.onClosed();
  if (restoreFocus && state.restoreFocus?.isConnected) {
    state.restoreFocus.focus({ preventScroll: true });
  }
}

function _button(label, className, activate) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = className;
  button.textContent = label;
  button.addEventListener('click', activate);
  return button;
}

function showCredentialReveal({ host, secret, title = 'Save this credential', note = '', onSaved = null, onClosed = null, restoreFocus = null }) {
  clearCredentialReveal({ restoreFocus: false });
  const normalized = String(secret || '');
  if (!host || !normalized) throw new Error('A reveal host and credential are required');

  const state = { host, secret: normalized, onSaved, onClosed, restoreFocus };
  activeReveal = state;
  host.replaceChildren();
  host.hidden = false;
  host.className = 'options-access-reveal';

  const heading = document.createElement('div');
  heading.className = 'options-access-reveal-title';
  heading.textContent = title;
  const description = document.createElement('p');
  description.className = 'options-access-description';
  description.textContent = note || 'This is the only time the full credential will be available. Save it somewhere secure.';
  const value = document.createElement('code');
  value.className = 'options-access-reveal-value';
  value.textContent = '•'.repeat(24);
  value.setAttribute('aria-label', 'Credential hidden');
  const status = document.createElement('div');
  status.className = 'options-access-message';
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  const actions = document.createElement('div');
  actions.className = 'options-access-actions';

  let revealed = false;
  const reveal = _button('Reveal', 'btn btn-secondary btn-compact', () => {
    if (activeReveal !== state) return;
    revealed = !revealed;
    value.textContent = revealed ? state.secret : '•'.repeat(24);
    value.setAttribute('aria-label', revealed ? 'Credential revealed' : 'Credential hidden');
    reveal.textContent = revealed ? 'Hide' : 'Reveal';
  });
  const copy = _button('Copy', 'btn btn-secondary btn-compact', async () => {
    if (activeReveal !== state) return;
    try {
      await importedCopyTextToClipboard(state.secret);
      status.textContent = 'Credential copied.';
      status.className = 'options-access-message is-success';
      status.setAttribute('role', 'status');
      status.setAttribute('aria-live', 'polite');
    } catch (_) {
      status.textContent = 'Could not copy the credential. Reveal it and copy it manually.';
      status.className = 'options-access-message is-error';
      status.setAttribute('role', 'alert');
      status.setAttribute('aria-live', 'assertive');
    }
  });
  const saved = _button('I saved it', 'btn btn-primary btn-compact', async () => {
    if (activeReveal !== state) return;
    saved.disabled = true;
    try {
      if (typeof state.onSaved === 'function') await state.onSaved(state.secret);
      clearCredentialReveal();
    } catch (error) {
      saved.disabled = false;
      status.textContent = error?.message || 'Could not finish saving the credential.';
      status.className = 'options-access-message is-error';
      status.setAttribute('role', 'alert');
      status.setAttribute('aria-live', 'assertive');
    }
  });
  const close = _button('Close', 'btn btn-ghost btn-compact', clearCredentialReveal);
  actions.append(reveal, copy, saved, close);
  host.append(heading, description, value, actions, status);
  reveal.focus({ preventScroll: true });
}

if (typeof window !== 'undefined') {
  window.addEventListener('app:options-closing', () => clearCredentialReveal({ restoreFocus: false }));
  window.addEventListener('app:identity-changed', () => clearCredentialReveal({ restoreFocus: false }));
}

export { clearCredentialReveal, showCredentialReveal };
