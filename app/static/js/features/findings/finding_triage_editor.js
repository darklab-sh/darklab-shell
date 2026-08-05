// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Shared finding remediation and verification editor.
// Loaded before shell_chrome.js; Projects and Atlas open it with a saved callback.
import { apiFetch as importedApiFetch } from '../../session.js';
import { bindMobileSheet as importedBindMobileSheet } from '../../ui/mobile_sheet.js';
import { bindDismissible as importedBindDismissible } from '../../ui/ui_dismissible.js';
import { showConfirm as importedShowConfirm } from '../../ui/ui_confirm.js';
import {
  enhanceAppSelects as importedEnhanceAppSelects,
  refocusComposerAfterAction as importedRefocusComposerAfterAction,
  syncAppSelect as importedSyncAppSelect,
} from '../../ui/ui_helpers.js';

let DarklabFindingTriageEditor = null;

(function findingTriageEditorModule(global) {
  'use strict';
  const bindDismissible = typeof importedBindDismissible === 'function' ? importedBindDismissible : null;
  const bindMobileSheet = typeof importedBindMobileSheet === 'function' ? importedBindMobileSheet : null;
  const enhanceAppSelects = typeof importedEnhanceAppSelects === 'function' ? importedEnhanceAppSelects : null;
  const refocusComposerAfterAction = typeof importedRefocusComposerAfterAction === 'function' ? importedRefocusComposerAfterAction : null;
  const showConfirm = typeof importedShowConfirm === 'function' ? importedShowConfirm : null;
  const syncAppSelect = typeof importedSyncAppSelect === 'function' ? importedSyncAppSelect : null;

  const VERIFICATION_STATES = [
    { value: 'not_started', label: 'Not started' },
    { value: 'ready_to_verify', label: 'Ready to verify' },
    { value: 'verified', label: 'Verified' },
    { value: 'needs_retest', label: 'Needs retest' },
    { value: 'not_applicable', label: 'Not applicable' },
  ];

  const MAX_TEXT_LENGTH = 20000;
  let state = {
    finding: null,
    options: {},
    bound: false,
    loadedTriage: null,
    mergePreview: null,
    mergeSearchTimer: null,
    mergeSearchGeneration: 0,
  };

  function el(id) {
    return document.getElementById(id);
  }

  function api() {
    return (typeof importedApiFetch === 'function' && importedApiFetch)
      || (typeof global.fetch === 'function' ? global.fetch.bind(global) : null);
  }

  function text(value, fallback = '') {
    const normalized = String(value || '').trim();
    return normalized || fallback;
  }

  function titleForFinding(finding) {
    return text(finding && (finding.title || finding.raw_line || finding.id), 'Finding');
  }

  function verificationStatusLabel(value) {
    const normalized = String(value || 'not_started');
    const found = VERIFICATION_STATES.find(item => item.value === normalized);
    return found ? found.label : normalized;
  }

  function verificationStatusTone(value) {
    const normalized = String(value || 'not_started');
    if (normalized === 'verified') return 'green';
    if (normalized === 'needs_retest') return 'amber';
    return 'muted';
  }

  function reviewStateLabel(value) {
    const normalized = text(value, 'new').replace(/_/g, ' ');
    return normalized.charAt(0).toUpperCase() + normalized.slice(1);
  }

  function compactTriage(triage) {
    const item = triage && typeof triage === 'object' ? triage : {};
    return {
      verification_status: String(item.verification_status || 'not_started'),
      has_remediation: !!String(item.remediation || '').trim() || !!item.has_remediation,
      has_verification_steps: !!String(item.verification_steps || '').trim() || !!item.has_verification_steps,
      has_verification_notes: !!String(item.verification_notes || '').trim() || !!item.has_verification_notes,
      remediation_preview: text(item.remediation_preview || item.remediation),
      verification_steps_preview: text(item.verification_steps_preview || item.verification_steps),
      remediation_id: text(item.remediation_id),
      remediation_source: text(item.remediation_source, 'observation'),
      remediation_updated_at: text(item.remediation_updated_at),
      remediation_group_id: text(item.remediation_group_id || item.remediation_id),
      remediation_group_merged: !!item.remediation_group_merged,
      remediation_group_member_count: Number(item.remediation_group_member_count || 1),
    };
  }

  function triageFromForm() {
    return {
      remediation: String(el('finding-triage-remediation')?.value || '').trim(),
      verification_steps: String(el('finding-triage-verification-steps')?.value || '').trim(),
      verification_status: String(el('finding-triage-status')?.value || 'not_started'),
      verification_notes: String(el('finding-triage-verification-notes')?.value || '').trim(),
    };
  }

  function syncStatusSelect() {
    const statusSelect = el('finding-triage-status');
    if (statusSelect && typeof syncAppSelect === 'function') syncAppSelect(statusSelect);
  }

  function setDisabled(disabled) {
    [
      el('finding-triage-remediation'),
      el('finding-triage-verification-steps'),
      el('finding-triage-status'),
      el('finding-triage-verification-notes'),
      el('finding-triage-save'),
      el('finding-triage-merge-apply'),
    ].forEach((node) => {
      if (node) node.disabled = !!disabled;
    });
    const allowReadOnlyPreview = !!(
      disabled && state.options.canEdit === false && state.loadedTriage
    );
    [
      el('finding-triage-merge-toggle'),
      el('finding-triage-merge-search'),
      ...document.querySelectorAll('.finding-triage-merge-candidate'),
    ].forEach((node) => {
      if (node) node.disabled = !!disabled && !allowReadOnlyPreview;
    });
    syncStatusSelect();
  }

  function setMessage(message = '', { error = false } = {}) {
    const node = el('finding-triage-message');
    if (!node) return;
    node.textContent = message;
    node.classList.toggle('u-hidden', !message);
    node.classList.toggle('is-error', !!error);
  }

  function isOpen() {
    return !!el('finding-triage-overlay')?.classList.contains('open');
  }

  function close() {
    const overlay = el('finding-triage-overlay');
    if (!overlay) return;
    overlay.classList.add('u-hidden');
    overlay.classList.remove('open');
    overlay.setAttribute('aria-hidden', 'true');
    state.finding = null;
    state.options = {};
    state.loadedTriage = null;
    state.mergePreview = null;
    state.mergeSearchGeneration += 1;
    if (state.mergeSearchTimer) global.clearTimeout(state.mergeSearchTimer);
    state.mergeSearchTimer = null;
    if (typeof refocusComposerAfterAction === 'function') {
      refocusComposerAfterAction({ defer: true });
    }
  }

  async function requestTriage(findingId) {
    const resp = await api()(`/findings/${encodeURIComponent(findingId)}/triage`, { cache: 'no-store' });
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data && data.error ? data.error : `HTTP ${resp.status}`);
    }
    const data = await resp.json().catch(() => ({}));
    return data && data.triage && typeof data.triage === 'object' ? data.triage : {};
  }

  function populate(triage) {
    const status = String(triage && triage.verification_status || 'not_started');
    const remediation = el('finding-triage-remediation');
    const steps = el('finding-triage-verification-steps');
    const statusSelect = el('finding-triage-status');
    const notes = el('finding-triage-verification-notes');
    if (remediation) remediation.value = String(triage && triage.remediation || '');
    if (steps) steps.value = String(triage && triage.verification_steps || '');
    if (statusSelect) statusSelect.value = VERIFICATION_STATES.some(item => item.value === status) ? status : 'not_started';
    if (notes) notes.value = String(triage && triage.verification_notes || '');
    renderMergeSummary(triage);
    syncStatusSelect();
  }

  function clearNode(node) {
    if (node) node.replaceChildren();
  }

  function identityLabel(item) {
    const vulnerability = text(item && item.vulnerability_id);
    return vulnerability || text(item && item.rule_identity, 'Saved scanner rule');
  }

  function renderMergeSummary(triage) {
    const node = el('finding-triage-merge-summary');
    if (!node) return;
    const count = Math.max(1, Number(triage && triage.remediation_group_member_count || 1));
    node.textContent = count > 1
      ? `This guidance is shared across ${count.toLocaleString()} explicitly merged remediation identities.`
      : 'This finding currently uses its exact target and vulnerability or rule as its remediation group.';
  }

  function resetMergePanel({ collapse = false } = {}) {
    state.mergePreview = null;
    const results = el('finding-triage-merge-results');
    const preview = el('finding-triage-merge-preview');
    const actions = el('finding-triage-merge-actions');
    clearNode(results);
    clearNode(preview);
    preview?.classList.add('u-hidden');
    actions?.classList.add('u-hidden');
    if (collapse) {
      el('finding-triage-merge-panel')?.classList.add('u-hidden');
      el('finding-triage-merge-toggle')?.setAttribute('aria-expanded', 'false');
      const search = el('finding-triage-merge-search');
      if (search) search.value = '';
    }
  }

  function formIsDirty() {
    if (!state.loadedTriage) return false;
    return JSON.stringify(triageFromForm()) !== JSON.stringify(state.loadedTriage);
  }

  function candidateMeta(item) {
    return [identityLabel(item), text(item && item.affected_subject)]
      .filter(Boolean)
      .join(' · ');
  }

  function renderCandidates(candidates) {
    const results = el('finding-triage-merge-results');
    if (!results) return;
    clearNode(results);
    if (!candidates.length) {
      results.textContent = 'No other saved findings matched.';
      return;
    }
    candidates.forEach((candidate) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'finding-triage-merge-candidate';
      button.dataset.findingId = text(candidate.finding_id);
      const title = document.createElement('span');
      title.className = 'finding-triage-merge-candidate-title';
      title.textContent = text(candidate.title, 'Finding');
      const meta = document.createElement('span');
      meta.className = 'finding-triage-merge-candidate-meta';
      meta.textContent = candidateMeta(candidate);
      button.append(title, meta);
      button.addEventListener('click', () => previewMerge(candidate, button));
      results.appendChild(button);
    });
  }

  async function searchMergeCandidates() {
    const findingId = text(state.finding && state.finding.id);
    const query = String(el('finding-triage-merge-search')?.value || '').trim();
    const results = el('finding-triage-merge-results');
    state.mergeSearchGeneration += 1;
    const generation = state.mergeSearchGeneration;
    resetMergePanel();
    if (!findingId || query.length < 2) {
      if (results) results.textContent = query ? 'Enter at least two characters.' : '';
      return;
    }
    if (results) results.textContent = 'Searching saved findings...';
    try {
      const resp = await api()(`/findings/${encodeURIComponent(findingId)}/remediation-merge/candidates`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data && data.error ? data.error : `HTTP ${resp.status}`);
      if (generation !== state.mergeSearchGeneration) return;
      renderCandidates(Array.isArray(data.candidates) ? data.candidates : []);
    } catch (err) {
      if (generation === state.mergeSearchGeneration && results) {
        results.textContent = err.message || 'Could not search saved findings.';
      }
    }
  }

  function scheduleMergeSearch() {
    if (state.mergeSearchTimer) global.clearTimeout(state.mergeSearchTimer);
    state.mergeSearchTimer = global.setTimeout(searchMergeCandidates, 250);
  }

  function renderMergePreview(preview) {
    const node = el('finding-triage-merge-preview');
    if (!node) return;
    clearNode(node);
    const heading = document.createElement('div');
    heading.className = 'finding-triage-merge-preview-title';
    heading.textContent = `${Number(preview.observation_count || 0).toLocaleString()} observations will share one remediation group.`;
    const note = document.createElement('div');
    note.className = 'finding-triage-guidance-note';
    note.textContent = 'Evidence, validation method, verification steps, status, and notes will stay separate.';
    const target = preview.target && typeof preview.target === 'object' ? preview.target : {};
    const outcome = document.createElement('div');
    outcome.className = 'finding-triage-guidance-note';
    const guidance = text(target.remediation_preview);
    outcome.textContent = guidance
      ? `The selected finding wins. Its current review state is ${reviewStateLabel(target.review_state)}, and its guidance starts: ${guidance}`
      : `The selected finding wins. Its current review state is ${reviewStateLabel(target.review_state)}, and it has no saved guidance.`;
    const list = document.createElement('ul');
    list.className = 'finding-triage-merge-observations';
    const observations = Array.isArray(preview.observations) ? preview.observations : [];
    observations.slice(0, 5).forEach((observation) => {
      const item = document.createElement('li');
      const title = document.createElement('div');
      title.textContent = text(observation.title, 'Finding');
      const meta = document.createElement('div');
      meta.className = 'finding-triage-merge-observation-meta';
      meta.textContent = [text(observation.validation_method), identityLabel(observation)]
        .filter(Boolean)
        .join(' · ');
      item.append(title, meta);
      list.appendChild(item);
    });
    if (observations.length > 5) {
      const more = document.createElement('li');
      more.className = 'finding-triage-merge-observation-meta';
      more.textContent = `and ${(observations.length - 5).toLocaleString()} more observations`;
      list.appendChild(more);
    }
    node.append(heading, note, outcome, list);
    node.classList.remove('u-hidden');
    el('finding-triage-merge-actions')?.classList.remove('u-hidden');
  }

  async function previewMerge(candidate, button) {
    const findingId = text(state.finding && state.finding.id);
    const targetFindingId = text(candidate && candidate.finding_id);
    if (!findingId || !targetFindingId) return;
    state.mergePreview = null;
    el('finding-triage-merge-actions')?.classList.add('u-hidden');
    const previewNode = el('finding-triage-merge-preview');
    if (previewNode) {
      previewNode.textContent = 'Checking affected observations...';
      previewNode.classList.remove('u-hidden');
    }
    document.querySelectorAll('.finding-triage-merge-candidate.is-selected')
      .forEach(node => node.classList.remove('is-selected'));
    button?.classList.add('is-selected');
    try {
      const resp = await api()(`/findings/${encodeURIComponent(findingId)}/remediation-merge/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_finding_id: targetFindingId }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data && data.error ? data.error : `HTTP ${resp.status}`);
      state.mergePreview = {
        ...data.preview,
        target_finding_id: targetFindingId,
      };
      renderMergePreview(state.mergePreview);
    } catch (err) {
      if (previewNode) previewNode.textContent = err.message || 'Could not preview this merge.';
    }
  }

  async function applyMerge() {
    const findingId = text(state.finding && state.finding.id);
    const preview = state.mergePreview;
    if (!findingId || !preview) return;
    if (formIsDirty()) {
      setMessage('Save or cancel your triage edits before merging remediation groups.', { error: true });
      return;
    }
    const choice = showConfirm ? await showConfirm({
      body: {
        text: `Merge remediation for ${text(preview.source && preview.source.title, 'this finding')} with ${text(preview.target && preview.target.title, 'the selected finding')}?`,
        note: `${Number(preview.observation_count || 0).toLocaleString()} observations will share review state and remediation guidance. Their evidence and verification work stay separate.`,
      },
      tone: 'warning',
      actions: [
        { id: 'cancel', label: 'Cancel', role: 'cancel' },
        { id: 'merge', label: 'Merge groups', role: 'warning' },
      ],
      refocusOnResolve: false,
    }) : 'merge';
    if (choice !== 'merge') return;
    setMessage('Merging remediation groups...');
    setDisabled(true);
    try {
      const resp = await api()(`/findings/${encodeURIComponent(findingId)}/remediation-merge`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_finding_id: preview.target_finding_id,
          preview_token: preview.preview_token,
        }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data && data.error ? data.error : `HTTP ${resp.status}`);
      const triage = await requestTriage(findingId);
      populate(triage);
      state.loadedTriage = triageFromForm();
      resetMergePanel({ collapse: true });
      setMessage(`Merged ${Number(data.merge && data.merge.member_count || 0).toLocaleString()} remediation identities without combining their evidence or verification.`);
      const onSaved = state.options && typeof state.options.onSaved === 'function' ? state.options.onSaved : null;
      if (state.finding && typeof state.finding === 'object') state.finding.triage = compactTriage(triage);
      if (onSaved) await onSaved(triage, state.finding);
    } catch (err) {
      setMessage(err.message || 'Could not merge remediation groups.', { error: true });
    } finally {
      if (isOpen()) setDisabled(!(state.options && state.options.canEdit !== false));
    }
  }

  function validate(payload) {
    for (const field of ['remediation', 'verification_steps', 'verification_notes']) {
      if (String(payload[field] || '').length > MAX_TEXT_LENGTH) {
        return `${field.replace(/_/g, ' ')} must be ${MAX_TEXT_LENGTH.toLocaleString()} characters or fewer.`;
      }
    }
    return '';
  }

  async function save() {
    const findingId = String(state.finding && state.finding.id || '');
    if (!findingId) return;
    if (state.options && state.options.canEdit === false) {
      setMessage('View-only team members can read these details but cannot save changes.', { error: true });
      return;
    }
    const payload = triageFromForm();
    const validationError = validate(payload);
    if (validationError) {
      setMessage(validationError, { error: true });
      return;
    }
    setMessage('');
    setDisabled(true);
    try {
      const resp = await api()(`/findings/${encodeURIComponent(findingId)}/triage`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data && data.error ? data.error : `HTTP ${resp.status}`);
      const triage = data && data.triage && typeof data.triage === 'object' ? data.triage : payload;
      if (state.finding && typeof state.finding === 'object') {
        state.finding.triage = compactTriage(triage);
        state.finding.verification_status = state.finding.triage.verification_status;
      }
      state.loadedTriage = triageFromForm();
      const onSaved = state.options && typeof state.options.onSaved === 'function' ? state.options.onSaved : null;
      const savedFinding = state.finding;
      close();
      if (onSaved) await onSaved(triage, savedFinding);
    } catch (err) {
      setMessage(err.message || 'Could not save finding triage.', { error: true });
    } finally {
      if (isOpen()) setDisabled(!(state.options && state.options.canEdit !== false));
    }
  }

  function bindOnce() {
    if (state.bound) return;
    state.bound = true;
    el('finding-triage-form')?.addEventListener('submit', (event) => {
      event.preventDefault();
      save();
    });
    el('finding-triage-close')?.addEventListener('click', close);
    el('finding-triage-cancel')?.addEventListener('click', close);
    el('finding-triage-merge-toggle')?.addEventListener('click', () => {
      const panel = el('finding-triage-merge-panel');
      const toggle = el('finding-triage-merge-toggle');
      const opening = !!panel?.classList.contains('u-hidden');
      panel?.classList.toggle('u-hidden', !opening);
      toggle?.setAttribute('aria-expanded', opening ? 'true' : 'false');
      if (opening) global.setTimeout(() => el('finding-triage-merge-search')?.focus(), 0);
    });
    el('finding-triage-merge-search')?.addEventListener('input', scheduleMergeSearch);
    el('finding-triage-merge-apply')?.addEventListener('click', applyMerge);
    const overlay = el('finding-triage-overlay');
    if (overlay && typeof bindDismissible === 'function') {
      bindDismissible(overlay, {
        level: 'modal',
        isOpen,
        onClose: close,
        closeButtons: null,
      });
    }
    if (overlay && typeof bindMobileSheet === 'function') {
      bindMobileSheet(el('finding-triage-modal'), { onClose: close });
    }
  }

  function bindOpenChrome(overlay) {
    if (typeof enhanceAppSelects === 'function') enhanceAppSelects(overlay);
  }

  async function open(finding, options = {}) {
    const overlay = el('finding-triage-overlay');
    if (!overlay) throw new Error('Finding triage editor is not available.');
    const findingId = String(finding && finding.id || '');
    if (!findingId) throw new Error('Finding is missing its identifier.');
    bindOnce();
    state.finding = finding;
    state.options = options || {};
    const subtitle = el('finding-triage-subtitle');
    if (subtitle) subtitle.textContent = titleForFinding(finding);
    setMessage('Loading...');
    resetMergePanel({ collapse: true });
    populate(compactTriage(finding.triage || { verification_status: finding.verification_status }));
    setDisabled(true);
    overlay.classList.remove('u-hidden');
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
    bindOpenChrome(overlay);
    const canEdit = state.options.canEdit !== false;
    try {
      const triage = await requestTriage(findingId);
      populate(triage);
      state.loadedTriage = triageFromForm();
      setMessage(canEdit ? '' : 'View-only team members can read these details but cannot save changes.');
      setDisabled(!canEdit);
      window.setTimeout(() => el('finding-triage-remediation')?.focus({ preventScroll: true }), 0);
    } catch (err) {
      setMessage(err.message || 'Could not load finding triage.', { error: true });
      setDisabled(true);
    }
  }

  DarklabFindingTriageEditor = {
    compactTriage,
    close,
    isOpen,
    open,
    verificationStatusLabel,
    verificationStatusTone,
    verificationStates: VERIFICATION_STATES.slice(),
  };
})(typeof window !== 'undefined' ? window : globalThis);

const compactTriage = DarklabFindingTriageEditor.compactTriage;
const closeFindingTriageEditor = DarklabFindingTriageEditor.close;
const isFindingTriageEditorOpen = DarklabFindingTriageEditor.isOpen;
const openFindingTriageEditor = DarklabFindingTriageEditor.open;
const verificationStatusLabel = DarklabFindingTriageEditor.verificationStatusLabel;
const verificationStatusTone = DarklabFindingTriageEditor.verificationStatusTone;
const verificationStates = DarklabFindingTriageEditor.verificationStates;

export {
  DarklabFindingTriageEditor,
  closeFindingTriageEditor,
  compactTriage,
  isFindingTriageEditorOpen,
  openFindingTriageEditor,
  verificationStatusLabel,
  verificationStatusTone,
  verificationStates,
};
