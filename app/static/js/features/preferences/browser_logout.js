// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { getAppConfig } from '../../core/config.js';
import { showToast } from '../../core/utils.js';
import {
  apiFetch,
  clearAccessCredential,
  getBrowserIdentitySnapshot,
  redirectToSignIn,
} from '../../session.js';
import { showConfirm } from '../../ui/ui_confirm.js';
import { focusElement } from '../../ui/ui_helpers.js';

// Access and the shell menus share the same current-browser operation.
export async function logOutCurrentBrowser() {
  const identity = getBrowserIdentitySnapshot();
  if (identity.kind === 'browser_session') {
    const response = await apiFetch('/auth/logout', { method: 'POST', cache: 'no-store' });
    if (!response.ok) throw new Error('Could not log out. Try again.');
    redirectToSignIn();
  } else if (identity.kind === 'credential') {
    clearAccessCredential();
  }
}

let pending = false;

export async function confirmBrowserLogOut(returnFocus = null) {
  const identity = getBrowserIdentitySnapshot();
  if (pending || !['credential', 'browser_session'].includes(identity.kind)) return;
  pending = true;
  try {
    const provider = ['oidc_required', 'mixed'].includes(getAppConfig()?.access_profile);
    const choice = await showConfirm({
      body: 'Log out of this browser? Your workspace stays saved and other devices stay signed in.'
        + (identity.kind === 'credential' ? ' Keep your access credential to sign in again.' : '')
        + (provider ? ' If you use an identity provider, it stays signed in.' : ''),
      actions: [
        { id: 'cancel', label: 'Cancel', role: 'cancel' },
        { id: 'logout', label: 'Log out', role: 'destructive' },
      ],
      refocusOnResolve: false,
    });
    if (choice !== 'logout') return;
    const current = getBrowserIdentitySnapshot();
    if (current.kind !== identity.kind || current.credentialId !== identity.credentialId) {
      showToast('Your access changed. Open Log out again.');
      return;
    }
    await logOutCurrentBrowser();
    if (identity.kind === 'credential') showToast('Logged out of this browser');
  } catch (_) {
    showToast('Could not log out. Try again.');
  } finally {
    pending = false;
    focusElement(returnFocus, { preventScroll: true });
  }
}
