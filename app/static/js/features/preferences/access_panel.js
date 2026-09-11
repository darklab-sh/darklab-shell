// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { showToast as importedShowToast } from '../../core/utils.js';
import {
  activateAccessCredential as importedActivateAccessCredential,
  apiFetch as importedApiFetch,
  clearAccessCredential as importedClearAccessCredential,
  getBrowserIdentitySnapshot as importedGetBrowserIdentitySnapshot,
} from '../../session.js';
import { showConfirm as importedShowConfirm } from '../../ui/ui_confirm.js';
import { applyMobileTextInputDefaults as importedApplyMobileTextInputDefaults } from '../../ui/ui_helpers.js';
import { clearCredentialReveal, showCredentialReveal } from './credential_reveal.js';
import { credentialState, renderCredentialRows } from './credential_rows.js';

const elements = {
  panel: document.getElementById('options-panel-access'),
  summary: document.getElementById('options-access-summary'),
  summaryDetail: document.getElementById('options-access-summary-detail'),
  message: document.getElementById('options-access-msg'),
  affectedWork: document.getElementById('options-access-affected-work'),
  anonymousActions: document.getElementById('options-access-anonymous-actions'),
  authenticatedActions: document.getElementById('options-access-authenticated-actions'),
  keep: document.getElementById('options-access-keep-btn'),
  use: document.getElementById('options-access-use-btn'),
  discardInvalid: document.getElementById('options-access-discard-invalid-btn'),
  add: document.getElementById('options-access-add-btn'),
  remove: document.getElementById('options-access-remove-btn'),
  refresh: document.getElementById('options-access-refresh-btn'),
  credentialsSection: document.getElementById('options-access-credentials-section'),
  credentials: document.getElementById('options-access-credentials'),
  editor: document.getElementById('options-access-editor'),
  redemption: document.getElementById('options-access-redemption'),
  redemptionInput: document.getElementById('options-access-redemption-input'),
  redemptionApply: document.getElementById('options-access-redemption-apply'),
  redemptionCancel: document.getElementById('options-access-redemption-cancel'),
  reveal: document.getElementById('options-access-reveal'),
};

let credentials = [];
let refreshSequence = 0;
let pendingAction = '';
let editorReturnFocus = null;
let redemptionReturnFocus = null;

function _markAccessPanelReady() {
  [
    elements.keep,
    elements.use,
    elements.discardInvalid,
    elements.add,
    elements.remove,
    elements.refresh,
  ].forEach((control) => {
    if (control) control.disabled = false;
  });
  if (elements.panel) {
    elements.panel.dataset.accessPanelBound = '1';
    elements.panel.removeAttribute('aria-busy');
  }
}

function _setMessage(message = '', tone = '') {
  if (!elements.message) return;
  elements.message.textContent = message;
  elements.message.className = `options-access-message${tone ? ` is-${tone}` : ''}`;
  elements.message.setAttribute('role', tone === 'error' ? 'alert' : 'status');
  elements.message.setAttribute('aria-live', tone === 'error' ? 'assertive' : 'polite');
  elements.message.hidden = !message;
}

function _clearAffectedWorkReview() {
  if (!elements.affectedWork) return;
  elements.affectedWork.replaceChildren();
  elements.affectedWork.hidden = true;
}

function _renderAffectedWorkReview(disposition) {
  _clearAffectedWorkReview();
  const items = Array.isArray(disposition?.affected) ? disposition.affected : [];
  if (!elements.affectedWork || !items.length) return;
  const heading = document.createElement('strong');
  heading.textContent = 'Review affected future work';
  const description = document.createElement('p');
  description.className = 'options-access-description';
  description.textContent = 'These items were created or last changed with the revoked credential. Their current state is shown below.';
  const list = document.createElement('ul');
  list.className = 'options-access-affected-list';
  items.forEach((item) => {
    const entry = document.createElement('li');
    entry.textContent = `${item.kind}: ${item.label || item.id} (${item.state})`;
    list.append(entry);
  });
  elements.affectedWork.append(heading, description, list);
  elements.affectedWork.hidden = false;
}

async function _responsePayload(response) {
  try { return await response.json(); } catch (_) { return {}; }
}

async function _request(url, options = {}) {
  const response = await importedApiFetch(url, { cache: 'no-store', ...options });
  const payload = await _responsePayload(response);
  if (!response.ok) {
    const error = new Error(payload.message || payload.error || `Request failed (${response.status})`);
    error.code = payload.error || '';
    error.status = response.status;
    throw error;
  }
  return payload;
}

function _setIdentityLayout(authenticated) {
  if (elements.anonymousActions) elements.anonymousActions.hidden = authenticated;
  if (elements.authenticatedActions) elements.authenticatedActions.hidden = !authenticated;
  if (elements.credentialsSection) elements.credentialsSection.hidden = !authenticated;
}

function _renderAnonymous({ invalid = false } = {}) {
  credentials = [];
  _setIdentityLayout(false);
  if (elements.credentials) elements.credentials.replaceChildren();
  if (elements.discardInvalid) elements.discardInvalid.hidden = !invalid;
  if (elements.summary) elements.summary.textContent = invalid ? 'Credential needs attention' : 'Anonymous workspace';
  if (elements.summaryDetail) {
    elements.summaryDetail.textContent = invalid
      ? 'The credential saved in this browser is malformed or no longer accepted. Remove it before continuing anonymously.'
      : 'This workspace is tied to this browser. Keep it to use the same workspace on other devices.';
  }
}

function _renderAuthenticated() {
  const currentId = importedGetBrowserIdentitySnapshot().credentialId;
  const current = credentials.find(item => item.id === currentId);
  if (elements.discardInvalid) elements.discardInvalid.hidden = true;
  _setIdentityLayout(true);
  if (elements.summary) elements.summary.textContent = 'Kept workspace';
  if (elements.summaryDetail) {
    const label = current?.label || current?.public_prefix || 'Current credential';
    elements.summaryDetail.textContent = `${label} is providing access on this browser.`;
  }
  if (elements.credentials) {
    renderCredentialRows(elements.credentials, credentials, {
      currentCredentialId: currentId,
      onAction: _handleCredentialAction,
    });
  }
}

async function refreshAccessPanel({ force = false } = {}) {
  _clearAffectedWorkReview();
  const sequence = ++refreshSequence;
  const identity = importedGetBrowserIdentitySnapshot();
  if (identity.kind !== 'credential') {
    _renderAnonymous();
    return { identity, credentials: [] };
  }
  if (!identity.validFormat) {
    _renderAnonymous({ invalid: true });
    _setMessage('This browser has an invalid saved credential. Remove it to continue.', 'error');
    return { identity, credentials: [] };
  }
  if (force) _setMessage('Refreshing access…');
  try {
    await _request('/auth/principal');
    const credentialsPayload = await _request('/auth/credentials');
    if (sequence !== refreshSequence) return null;
    credentials = Array.isArray(credentialsPayload.credentials) ? credentialsPayload.credentials : [];
    _renderAuthenticated();
    if (force) _setMessage('Access is up to date.', 'success');
    return { identity, credentials };
  } catch (error) {
    if (sequence !== refreshSequence) return null;
    _renderAnonymous({ invalid: true });
    _setMessage(error.message || 'Could not load access.', 'error');
    return null;
  }
}

function _field(label, input) {
  const wrapper = document.createElement('label');
  wrapper.className = 'form-fieldset options-access-editor-field';
  const text = document.createElement('span');
  text.className = 'form-label';
  text.textContent = label;
  wrapper.append(text, input);
  return wrapper;
}

function _input(type, value = '') {
  const input = document.createElement('input');
  input.type = type;
  input.className = 'form-control';
  input.value = value;
  input.autocomplete = 'off';
  input.dataset.bwignore = 'true';
  importedApplyMobileTextInputDefaults?.(input);
  return input;
}

function _localExpiry(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function _closeEditor({ restoreFocus = true } = {}) {
  if (!elements.editor) return;
  elements.editor.replaceChildren();
  elements.editor.hidden = true;
  if (restoreFocus && editorReturnFocus?.isConnected) editorReturnFocus.focus({ preventScroll: true });
  editorReturnFocus = null;
}

function _showEditor(mode, credential = null, returnFocus = null) {
  if (!elements.editor) return;
  _closeRedemption({ restoreFocus: false });
  editorReturnFocus = returnFocus;
  elements.editor.replaceChildren();
  elements.editor.hidden = false;
  const title = document.createElement('strong');
  title.textContent = mode === 'keep'
    ? 'Keep this workspace'
    : mode === 'create' ? 'Add an access credential' : mode === 'rename' ? 'Rename credential' : 'Change expiry';
  const description = document.createElement('p');
  description.className = 'options-access-description';
  description.textContent = mode === 'keep'
    ? 'Give this browser an optional label. Your current files and history will stay in the same workspace.'
    : mode === 'create'
      ? 'Create a credential for another browser or device. You will see the full value once.'
      : mode === 'rename' ? 'Labels help you recognize where a credential is used.' : 'Leave the expiry blank for no expiry.';
  elements.editor.append(title, description);
  let labelInput = null;
  let expiryInput = null;
  if (mode !== 'expiry') {
    labelInput = _input('text', credential?.label || (mode === 'keep' ? 'This browser' : ''));
    labelInput.maxLength = 64;
    labelInput.placeholder = 'Optional label';
    elements.editor.append(_field('Label', labelInput));
  }
  if (mode === 'create' || mode === 'expiry') {
    expiryInput = _input('datetime-local', _localExpiry(credential?.expires_at));
    elements.editor.append(_field('Expiry', expiryInput));
  }
  const error = document.createElement('div');
  error.className = 'options-access-message is-error';
  error.setAttribute('role', 'alert');
  error.setAttribute('aria-live', 'assertive');
  error.hidden = true;
  const actions = document.createElement('div');
  actions.className = 'options-access-actions';
  const save = document.createElement('button');
  save.type = 'button';
  save.className = 'btn btn-primary btn-compact';
  save.textContent = mode === 'keep' ? 'Keep workspace' : 'Save';
  const cancel = document.createElement('button');
  cancel.type = 'button';
  cancel.className = 'btn btn-ghost btn-compact';
  cancel.textContent = 'Cancel';
  cancel.addEventListener('click', () => _closeEditor());
  save.addEventListener('click', async () => {
    save.disabled = true;
    error.hidden = true;
    const expiresAt = expiryInput?.value ? new Date(expiryInput.value).toISOString() : null;
    try {
      if (mode === 'keep') {
        const payload = await _request('/auth/principals', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ label: labelInput?.value.trim() || '' }),
        });
        importedActivateAccessCredential(payload.secret);
        _closeEditor({ restoreFocus: false });
        await refreshAccessPanel();
        showCredentialReveal({ host: elements.reveal, secret: payload.secret, restoreFocus: elements.add });
        return;
      }
      if (mode === 'create') {
        const payload = await _request('/auth/credentials', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ type: 'portable', label: labelInput?.value.trim() || '', expires_at: expiresAt }),
        });
        _closeEditor({ restoreFocus: false });
        await refreshAccessPanel();
        showCredentialReveal({ host: elements.reveal, secret: payload.secret, restoreFocus: elements.add });
        return;
      }
      const body = mode === 'rename'
        ? { label: labelInput?.value.trim() || '' }
        : { expires_at: expiresAt };
      await _request(`/auth/credentials/${encodeURIComponent(credential.id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      _closeEditor();
      await refreshAccessPanel();
      _setMessage('Credential updated.', 'success');
    } catch (requestError) {
      error.textContent = requestError.message || 'Could not save the credential.';
      error.hidden = false;
      save.disabled = false;
    }
  });
  actions.append(save, cancel);
  elements.editor.append(actions, error);
  (labelInput || expiryInput)?.focus({ preventScroll: true });
}

function _openRedemption(returnFocus = null) {
  _closeEditor({ restoreFocus: false });
  if (!elements.redemption) return;
  redemptionReturnFocus = returnFocus;
  elements.redemption.hidden = false;
  if (elements.redemptionInput) {
    elements.redemptionInput.value = '';
    elements.redemptionInput.focus({ preventScroll: true });
  }
}

function _closeRedemption({ restoreFocus = true } = {}) {
  if (!elements.redemption) return;
  if (elements.redemptionInput) elements.redemptionInput.value = '';
  elements.redemption.hidden = true;
  if (restoreFocus && redemptionReturnFocus?.isConnected) redemptionReturnFocus.focus({ preventScroll: true });
  redemptionReturnFocus = null;
}

async function _redeemCredential() {
  const secret = String(elements.redemptionInput?.value || '').trim();
  if (!secret) {
    _setMessage('Paste an access credential first.', 'error');
    return;
  }
  elements.redemptionApply.disabled = true;
  try {
    await _request('/auth/credentials/redeem', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ secret }),
    });
    importedActivateAccessCredential(secret);
    _closeRedemption({ restoreFocus: false });
    await refreshAccessPanel();
    _setMessage('This browser now uses the existing workspace.', 'success');
  } catch (error) {
    if (elements.redemptionInput) elements.redemptionInput.value = '';
    _setMessage(error.message || 'That credential was not accepted.', 'error');
  } finally {
    elements.redemptionApply.disabled = false;
  }
}

function _durableWorkContent(disposition) {
  const wrapper = document.createElement('div');
  wrapper.className = 'options-access-revoke-preview';
  const items = Array.isArray(disposition?.affected) ? disposition.affected : [];
  const summary = document.createElement('p');
  summary.textContent = items.length
    ? `${items.length} future ${items.length === 1 ? 'task was' : 'tasks were'} created or last changed with this credential.`
    : 'No future schedules, watchers, or other durable work is attributed to this credential.';
  wrapper.append(summary);
  if (items.length) {
    const list = document.createElement('ul');
    items.slice(0, 8).forEach((item) => {
      const entry = document.createElement('li');
      entry.textContent = `${item.kind}: ${item.label || item.id} (${item.state})`;
      list.append(entry);
    });
    wrapper.append(list);
  }
  const pauseLabel = document.createElement('label');
  pauseLabel.className = 'form-check';
  const pause = document.createElement('input');
  pause.type = 'checkbox';
  pause.disabled = !items.some(item => item.pausable);
  const pauseText = document.createElement('span');
  pauseText.textContent = 'Also pause related future work';
  pauseLabel.append(pause, pauseText);
  wrapper.append(pauseLabel);
  return { wrapper, pause };
}

async function _revokeCredential(credential, { rotationReplacement = null } = {}) {
  const currentId = importedGetBrowserIdentitySnapshot().credentialId;
  const activePortable = credentials.filter(item => item.credential_type === 'portable' && credentialState(item) === 'Active');
  const isLastPortable = credential.credential_type === 'portable' && activePortable.length === 1;
  const payload = await _request(`/auth/credentials/${encodeURIComponent(credential.id)}/durable-work`);
  const content = _durableWorkContent(payload.durable_work || {});
  const choice = await importedShowConfirm({
    body: `${credential.id === currentId ? 'This credential is active in this browser. ' : ''}${isLastPortable ? 'This is the last active access credential. Operator recovery will be required after revocation. ' : ''}Revocation cannot be undone.`,
    content: content.wrapper,
    tone: 'danger',
    actions: [
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      { id: 'revoke', label: isLastPortable ? 'Revoke last credential' : 'Revoke', role: 'danger' },
    ],
    refocusOnResolve: false,
  });
  if (choice !== 'revoke') return false;
  const revoked = await _request(`/auth/credentials/${encodeURIComponent(credential.id)}/revoke`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      reason: rotationReplacement ? 'Rotated in Access' : 'Revoked in Access',
      confirm_lockout: isLastPortable,
      pause_related_work: content.pause.checked,
    }),
  });
  if (credential.id === currentId) {
    if (rotationReplacement) importedActivateAccessCredential(rotationReplacement);
    else importedClearAccessCredential();
  }
  await refreshAccessPanel();
  _renderAffectedWorkReview(revoked.durable_work || {});
  const paused = Number(revoked.durable_work?.paused_count || 0);
  _setMessage(paused ? `Credential revoked and ${paused} related tasks paused.` : 'Credential revoked.', 'success');
  (importedGetBrowserIdentitySnapshot().kind === 'credential' ? elements.add : elements.keep)?.focus?.({ preventScroll: true });
  return true;
}

async function _rotateCredential(credential) {
  const choice = await importedShowConfirm({
    body: 'A replacement will be created and shown once. The old credential stays active until you confirm that the replacement is saved.',
    tone: 'warning',
    actions: [
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      { id: 'continue', label: 'Create replacement', role: 'primary' },
    ],
    refocusOnResolve: false,
  });
  if (choice !== 'continue') return;
  const requestBody = {
    type: credential.credential_type,
    label: credential.label ? `${credential.label} replacement` : 'Replacement credential',
    scopes: credential.scopes || undefined,
  };
  if (credential.credential_type === 'portable') requestBody.expires_at = credential.expires_at || null;
  const response = await _request('/auth/credentials', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(requestBody),
  });
  await refreshAccessPanel();
  showCredentialReveal({
    host: elements.reveal,
    secret: response.secret,
    title: 'Save the replacement credential',
    note: 'The old credential is still active. After saving this value, you can review its durable work and revoke the old one.',
    onSaved: async secret => _revokeCredential(credential, { rotationReplacement: secret }),
    onClosed: () => refreshAccessPanel(),
    restoreFocus: elements.add,
  });
}

async function _handleCredentialAction(action, credential, returnFocus = null) {
  _setMessage('');
  try {
    if (action === 'rename' || action === 'expiry') _showEditor(action, credential, returnFocus);
    else if (action === 'rotate') await _rotateCredential(credential);
    else if (action === 'revoke') await _revokeCredential(credential);
  } catch (error) {
    _setMessage(error.message || 'The credential action failed.', 'error');
  }
}

async function _removeLocalAccess({ invalid = false } = {}) {
  const choice = await importedShowConfirm({
    body: invalid
      ? 'Remove the invalid credential saved in this browser and continue with a new anonymous workspace?'
      : 'Remove this credential from this browser? The credential will remain active on other devices until you revoke it.',
    actions: [
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      { id: 'remove', label: 'Remove from browser', role: 'danger' },
    ],
    refocusOnResolve: false,
  });
  if (choice !== 'remove') return;
  importedClearAccessCredential();
  _closeEditor({ restoreFocus: false });
  _closeRedemption({ restoreFocus: false });
  clearCredentialReveal({ restoreFocus: false });
  await refreshAccessPanel();
  _setMessage(
    invalid ? 'Invalid credential removed. This browser now has a new anonymous workspace.' : 'Local access removed. The kept workspace still exists.',
    'success',
  );
  elements.keep?.focus?.({ preventScroll: true });
  importedShowToast?.('Access removed from this browser');
}

async function openAccessAction(action = '') {
  pendingAction = String(action || '').toLowerCase();
  await refreshAccessPanel();
  const identity = importedGetBrowserIdentitySnapshot();
  if (pendingAction === 'use') _openRedemption(elements.use);
  else if (pendingAction === 'create' && identity.kind === 'credential') _showEditor('create', null, elements.add);
  else if (pendingAction === 'recover') {
    _setMessage('If every credential is lost, ask the local operator to run credential recover.', 'warning');
  } else if (['expiry', 'rotate', 'revoke'].includes(pendingAction)) {
    _setMessage(`Choose a credential below, then select ${pendingAction}.`);
  }
  pendingAction = '';
}

elements.keep?.addEventListener('click', () => _showEditor('keep', null, elements.keep));
elements.use?.addEventListener('click', () => _openRedemption(elements.use));
elements.discardInvalid?.addEventListener('click', () => void _removeLocalAccess({ invalid: true }));
elements.add?.addEventListener('click', () => _showEditor('create', null, elements.add));
elements.remove?.addEventListener('click', () => void _removeLocalAccess());
elements.refresh?.addEventListener('click', () => void refreshAccessPanel({ force: true }));
elements.redemptionApply?.addEventListener('click', () => void _redeemCredential());
elements.redemptionCancel?.addEventListener('click', () => _closeRedemption());
elements.redemptionInput?.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    event.preventDefault();
    void _redeemCredential();
  }
});

_markAccessPanelReady();

if (typeof window !== 'undefined') {
  window.addEventListener('app:identity-changed', () => void refreshAccessPanel());
  window.addEventListener('app:options-tab-changed', (event) => {
    if (event?.detail?.tab === 'access') void refreshAccessPanel();
  });
}

export {
  openAccessAction,
  refreshAccessPanel,
};
