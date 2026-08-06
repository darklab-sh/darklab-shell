// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Shared finding details, remediation, and verification editor.
// Loaded lazily; Projects and Atlas open one overlay with saved callbacks.
import { apiFetch as importedApiFetch } from '../../session.js';
import { bindMobileSheet as importedBindMobileSheet } from '../../ui/mobile_sheet.js';
import { bindDismissible as importedBindDismissible } from '../../ui/ui_dismissible.js';
import { showConfirm as importedShowConfirm } from '../../ui/ui_confirm.js';
import {
  fetchAndRenderHistoryComparison as importedFetchAndRenderHistoryComparison,
  hasHistoryCompareHandler as importedHasHistoryCompareHandler,
} from '../run-comparison/history_compare_bridge.js';
import { attachActiveRunFromMonitor as importedAttachActiveRunFromMonitor } from '../../runner_bridge.js';
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
  const attachActiveRunFromMonitor = typeof importedAttachActiveRunFromMonitor === 'function'
    ? importedAttachActiveRunFromMonitor
    : null;
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
  const FINDING_SEVERITIES = new Set(['critical', 'high', 'medium', 'low', 'info']);
  const FINDING_CONFIDENCE = new Set(['unknown', 'low', 'medium', 'high']);
  const MAX_IDENTIFIER_COUNT = 50;
  const MAX_REFERENCE_COUNT = 50;
  const MAX_REFERENCE_LENGTH = 2048;
  const CVE_PATTERN = /^CVE-\d{4}-\d{4,}$/;
  const CWE_PATTERN = /^CWE-\d+$/;
  const CVSS_PATTERN = /^(?:CVSS:(?:2\.0|3\.[01]|4\.0)\/)?[A-Za-z]{1,4}:[A-Za-z0-9.-]+(?:\/[A-Za-z]{1,4}:[A-Za-z0-9.-]+)+$/;
  let state = {
    mode: 'triage',
    finding: null,
    options: {},
    bound: false,
    loadedTriage: null,
    verificationContext: null,
    recordEvidence: [],
    mergePreview: null,
    mergeSearchTimer: null,
    mergeSearchGeneration: 0,
    returnFocus: null,
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
      verification_disposition: item.verification_disposition && typeof item.verification_disposition === 'object'
        ? { ...item.verification_disposition }
        : null,
      remediation_group_id: text(item.remediation_group_id || item.remediation_id),
      remediation_group_merged: !!item.remediation_group_merged,
      remediation_group_member_count: Number(item.remediation_group_member_count || 1),
    };
  }

  function uniqueTokens(value) {
    return [...new Set(String(value || '')
      .split(/[\s,]+/)
      .map(item => item.trim().toUpperCase())
      .filter(Boolean))];
  }

  function recordFromForm({ allowDuplicate = false } = {}) {
    const cvssScoreText = String(el('finding-record-cvss-score')?.value || '').trim();
    const payload = {
      title: String(el('finding-record-title')?.value || '').trim(),
      severity: String(el('finding-record-severity')?.value || '').trim().toLowerCase(),
      summary: String(el('finding-record-summary')?.value || '').trim(),
      impact: String(el('finding-record-impact')?.value || '').trim(),
      reproduction_steps: String(el('finding-record-reproduction')?.value || '').trim(),
      confidence: String(el('finding-record-confidence')?.value || 'unknown').trim().toLowerCase(),
      cve_ids: uniqueTokens(el('finding-record-cves')?.value),
      cwe_ids: uniqueTokens(el('finding-record-cwes')?.value),
      cvss_vector: String(el('finding-record-cvss-vector')?.value || '').trim(),
      cvss_score: cvssScoreText ? Number(cvssScoreText) : null,
      references: String(el('finding-record-references')?.value || '')
        .split(/\r?\n/)
        .map(item => item.trim())
        .filter((item, index, items) => item && items.indexOf(item) === index),
      allow_duplicate: !!allowDuplicate,
    };
    if (state.finding) {
      payload.expected_revision = Number(state.finding.manual_revision || 0);
    } else {
      payload.target_id = String(el('finding-record-target')?.value || '').trim();
      payload.evidence = state.recordEvidence.map(item => ({
        evidence_type: String(item?.evidence_type || '').trim(),
        evidence_id: String(item?.evidence_id || '').trim(),
        line_number: Number.isInteger(Number(item?.line_number)) ? Number(item.line_number) : -1,
        snippet: String(item?.snippet || '').trim(),
      })).map(item => {
        if (item.evidence_type === 'run_line') return item;
        return { evidence_type: item.evidence_type, evidence_id: item.evidence_id };
      });
    }
    return payload;
  }

  function validateRecord(payload) {
    if (!state.finding && !payload.target_id) return 'Choose a confirmed Project target.';
    if (!payload.title) return 'Enter a finding title.';
    if (payload.title.length > 240) return 'Finding title must be 240 characters or fewer.';
    if (!FINDING_SEVERITIES.has(payload.severity)) return 'Choose a supported finding severity.';
    if (!FINDING_CONFIDENCE.has(payload.confidence)) return 'Choose a supported confidence level.';
    for (const [field, limit] of [
      ['summary', 4000],
      ['impact', MAX_TEXT_LENGTH],
      ['reproduction_steps', MAX_TEXT_LENGTH],
    ]) {
      if (String(payload[field] || '').length > limit) {
        return `${field.replace(/_/g, ' ')} must be ${limit.toLocaleString()} characters or fewer.`;
      }
    }
    for (const [field, pattern, label] of [
      ['cve_ids', CVE_PATTERN, 'CVE'],
      ['cwe_ids', CWE_PATTERN, 'CWE'],
    ]) {
      if (payload[field].length > MAX_IDENTIFIER_COUNT) {
        return `${label} IDs must contain ${MAX_IDENTIFIER_COUNT} items or fewer.`;
      }
      if (payload[field].some(item => !pattern.test(item))) return `Enter valid ${label} IDs.`;
    }
    if (payload.cvss_vector && (
      payload.cvss_vector.length > 256 || !CVSS_PATTERN.test(payload.cvss_vector)
    )) return 'Enter a valid CVSS vector.';
    if (payload.cvss_score !== null && (
      !Number.isFinite(payload.cvss_score) || payload.cvss_score < 0 || payload.cvss_score > 10
    )) return 'CVSS score must be between 0 and 10.';
    if (payload.references.length > MAX_REFERENCE_COUNT) {
      return `References must contain ${MAX_REFERENCE_COUNT} URLs or fewer.`;
    }
    for (const reference of payload.references) {
      if (reference.length > MAX_REFERENCE_LENGTH || reference.includes('\\') || /[\u0000-\u001f]/.test(reference)) {
        return 'References must use safe HTTP(S) URLs.';
      }
      try {
        const parsed = new URL(reference);
        if (!['http:', 'https:'].includes(parsed.protocol) || !parsed.hostname || parsed.username || parsed.password) {
          return 'References must use safe HTTP(S) URLs.';
        }
      } catch (_) {
        return 'References must use safe HTTP(S) URLs.';
      }
    }
    if (state.recordEvidence.length > 20) return 'A finding can start with at most 20 evidence links.';
    return '';
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
      el('finding-triage-verification-run'),
      el('finding-triage-verification-attach'),
      ...document.querySelectorAll('[data-finding-verification-use-suggestion]'),
      ...document.querySelectorAll('[data-finding-verification-unlink]'),
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

  function setMode(mode) {
    state.mode = mode === 'record' ? 'record' : 'triage';
    el('finding-triage-form')?.classList.toggle('u-hidden', state.mode !== 'triage');
    el('finding-record-form')?.classList.toggle('u-hidden', state.mode !== 'record');
    const title = el('finding-triage-title');
    if (title) {
      title.textContent = state.mode === 'record'
        ? (state.finding ? 'EDIT FINDING' : 'CREATE FINDING')
        : 'FINDING TRIAGE';
    }
  }

  function syncRecordSelects() {
    ['finding-record-target', 'finding-record-severity', 'finding-record-confidence']
      .map(el)
      .filter(Boolean)
      .forEach((select) => {
        if (typeof syncAppSelect === 'function') syncAppSelect(select);
      });
  }

  function setRecordDisabled(disabled) {
    el('finding-record-form')?.querySelectorAll('input, textarea, select, button')
      .forEach((node) => {
        node.disabled = !!disabled;
      });
    const target = el('finding-record-target');
    if (target && !disabled) target.disabled = !!state.finding;
    syncRecordSelects();
  }

  function targetLabel(target) {
    const type = text(target && target.type);
    const value = text(target && (target.value || target.canonical_value || target.id), 'Target');
    return type ? `${value} (${type})` : value;
  }

  function populateRecordTargets(targets, selectedId = '') {
    const select = el('finding-record-target');
    if (!select) return;
    clearNode(select);
    targets.forEach((target) => {
      const option = document.createElement('option');
      option.value = text(target && target.id);
      option.textContent = targetLabel(target);
      select.appendChild(option);
    });
    if (selectedId && targets.some(target => text(target && target.id) === selectedId)) {
      select.value = selectedId;
    }
  }

  function evidenceTitle(item) {
    const type = text(item && item.evidence_type, 'evidence').replace(/_/g, ' ');
    const rawLine = item && item.line_number;
    const line = rawLine !== null && rawLine !== undefined && rawLine !== ''
      && Number.isInteger(Number(rawLine))
      ? ` · line ${Number(rawLine)}`
      : '';
    return `${type}${line}`;
  }

  function renderRecordEvidence(evidence) {
    const section = el('finding-record-evidence-section');
    const container = el('finding-record-evidence');
    if (!section || !container) return;
    clearNode(container);
    section.classList.toggle('u-hidden', !evidence.length);
    evidence.forEach((item) => {
      const row = document.createElement('div');
      row.className = 'finding-record-evidence-item';
      const title = document.createElement('div');
      title.className = 'finding-record-evidence-title';
      title.textContent = evidenceTitle(item);
      const meta = document.createElement('div');
      meta.className = 'finding-record-evidence-meta';
      meta.textContent = text(item && (item.label || item.evidence_id), 'Saved Project evidence');
      row.append(title, meta);
      const snippetText = text(item && item.snippet);
      if (snippetText) {
        const snippet = document.createElement('div');
        snippet.className = 'finding-record-evidence-snippet';
        snippet.textContent = snippetText;
        row.appendChild(snippet);
      }
      container.appendChild(row);
    });
  }

  function populateRecord(finding, options) {
    const defaults = !finding && options.defaults && typeof options.defaults === 'object'
      ? options.defaults
      : {};
    const item = finding && typeof finding === 'object' ? finding : defaults;
    const suppliedTargets = Array.isArray(options.targets) ? options.targets : [];
    const currentTargetId = text(item.target_id || options.targetId);
    const targets = suppliedTargets.filter((target) => (
      text(target && target.review_state, 'confirmed') === 'confirmed'
      || text(target && target.id) === currentTargetId
    ));
    if (currentTargetId && !targets.some((target) => text(target && target.id) === currentTargetId)) {
      const suppliedTarget = options.target && typeof options.target === 'object'
        ? options.target
        : {};
      targets.push({
        id: currentTargetId,
        type: text(suppliedTarget.type || item.target_type),
        value: text(suppliedTarget.value || item.target_value, currentTargetId),
        review_state: 'confirmed',
      });
    }
    populateRecordTargets(targets, currentTargetId);
    const values = {
      'finding-record-title': item.title,
      'finding-record-summary': item.summary,
      'finding-record-impact': item.impact,
      'finding-record-reproduction': item.reproduction_steps,
      'finding-record-cves': Array.isArray(item.cve_ids) ? item.cve_ids.join(', ') : '',
      'finding-record-cwes': Array.isArray(item.cwe_ids) ? item.cwe_ids.join(', ') : '',
      'finding-record-cvss-vector': item.cvss_vector,
      'finding-record-cvss-score': item.cvss_score === null || item.cvss_score === undefined
        ? ''
        : item.cvss_score,
      'finding-record-references': Array.isArray(item.references) ? item.references.join('\n') : '',
    };
    Object.entries(values).forEach(([id, value]) => {
      const node = el(id);
      if (node) node.value = value === null || value === undefined ? '' : String(value);
    });
    const severityValue = String(item.severity || 'medium');
    const severity = el('finding-record-severity');
    if (severity) severity.value = FINDING_SEVERITIES.has(severityValue) ? severityValue : 'medium';
    const confidenceValue = String(item.confidence || 'unknown');
    const confidence = el('finding-record-confidence');
    if (confidence) confidence.value = FINDING_CONFIDENCE.has(confidenceValue)
      ? confidenceValue
      : 'unknown';
    state.recordEvidence = !finding && Array.isArray(options.evidence)
      ? options.evidence.slice()
      : [];
    renderRecordEvidence(state.recordEvidence);
    const save = el('finding-record-save');
    if (save) save.textContent = finding ? 'Save finding' : 'Create finding';
    return targets;
  }

  function isOpen() {
    return !!el('finding-triage-overlay')?.classList.contains('open');
  }

  function rememberReturnFocus(overlay, options = {}) {
    const requested = options && options.returnFocus;
    const active = typeof document !== 'undefined' ? document.activeElement : null;
    const target = requested || active;
    state.returnFocus = target
      && target !== document.body
      && typeof target.focus === 'function'
      && !overlay.contains(target)
      ? target
      : null;
  }

  function restoreReturnFocus(target) {
    if (
      !target
      || !target.isConnected
      || typeof target.focus !== 'function'
      || target.disabled
      || target.closest?.('[hidden], [aria-hidden="true"], .u-hidden')
    ) return false;
    try {
      target.focus({ preventScroll: true });
    } catch (_) {
      target.focus();
    }
    return document.activeElement === target;
  }

  function close(options = {}) {
    const overlay = el('finding-triage-overlay');
    if (!overlay) return;
    const returnFocus = state.returnFocus;
    overlay.classList.add('u-hidden');
    overlay.classList.remove('open');
    overlay.setAttribute('aria-hidden', 'true');
    state.finding = null;
    state.options = {};
    state.loadedTriage = null;
    state.verificationContext = null;
    state.recordEvidence = [];
    state.mergePreview = null;
    state.mergeSearchGeneration += 1;
    state.returnFocus = null;
    if (state.mergeSearchTimer) global.clearTimeout(state.mergeSearchTimer);
    state.mergeSearchTimer = null;
    if (!options || options.restoreFocus !== false) {
      global.setTimeout(() => {
        if (!restoreReturnFocus(returnFocus) && typeof refocusComposerAfterAction === 'function') {
          refocusComposerAfterAction({ defer: true });
        }
      }, 0);
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

  async function requestVerificationContext(projectId, findingId) {
    const resp = await api()(
      `/projects/${encodeURIComponent(projectId)}/findings/${encodeURIComponent(findingId)}/evidence`,
      { cache: 'no-store' },
    );
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data && data.error ? data.error : `HTTP ${resp.status}`);
    return data && data.verification && typeof data.verification === 'object'
      ? data.verification
      : {};
  }

  function renderDisposition(triage) {
    const node = el('finding-triage-disposition');
    if (!node) return;
    const disposition = triage && triage.verification_disposition;
    if (!disposition || typeof disposition !== 'object') {
      node.textContent = '';
      node.classList.add('u-hidden');
      return;
    }
    const actor = disposition.actor && typeof disposition.actor === 'object'
      ? disposition.actor
      : {};
    const actorLabel = text(actor.display_name)
      || (text(actor.kind) === 'team_member' ? 'a team member' : 'this session');
    const savedAt = text(disposition.updated_at);
    node.textContent = `Final disposition: ${verificationStatusLabel(disposition.status)} by ${actorLabel}${savedAt ? ` · ${savedAt}` : ''}`;
    node.classList.remove('u-hidden');
  }

  function compatibilityBadge(compatibility) {
    const stateValue = text(compatibility && compatibility.state, 'unavailable');
    const badge = document.createElement('span');
    const tone = stateValue === 'compatible'
      ? 'green'
      : (stateValue === 'incomparable' ? 'amber' : 'red');
    badge.className = `badge badge-tone-${tone}`;
    badge.textContent = stateValue === 'compatible'
      ? 'Comparable'
      : (stateValue === 'incomparable' ? 'Not comparable' : 'Evidence unavailable');
    return badge;
  }

  function verificationItem(titleText, metaText = '') {
    const row = document.createElement('div');
    row.className = 'finding-triage-verification-item';
    const title = document.createElement('div');
    title.className = 'finding-triage-verification-item-title';
    title.textContent = titleText;
    row.appendChild(title);
    if (metaText) {
      const meta = document.createElement('div');
      meta.className = 'finding-triage-verification-item-meta';
      meta.textContent = metaText;
      row.appendChild(meta);
    }
    return row;
  }

  function renderOriginChecks(checks) {
    const node = el('finding-triage-origin-checks');
    if (!node) return;
    clearNode(node);
    if (!checks.length) return;
    checks.forEach((check) => {
      const profile = [text(check.profile_key), text(check.profile_version) ? `v${text(check.profile_version)}` : '']
        .filter(Boolean)
        .join(' ');
      const row = verificationItem(
        text(check.check_key, 'Saved assessment check'),
        [profile, text(check.target_value), text(check.policy_level)].filter(Boolean).join(' · '),
      );
      const badges = document.createElement('div');
      badges.className = 'finding-triage-verification-item-badges';
      const source = document.createElement('span');
      source.className = `badge badge-tone-${check.source_state === 'available' ? 'cyan' : 'red'}`;
      source.textContent = check.source_state === 'available' ? 'Origin available' : 'Origin unavailable';
      badges.appendChild(source);
      if (check.profile_version_state === 'changed') {
        const drift = document.createElement('span');
        drift.className = 'badge badge-tone-amber';
        drift.textContent = `Profile now v${text(check.current_profile_version, 'unknown')}`;
        badges.appendChild(drift);
      } else if (check.profile_version_state === 'unavailable') {
        const drift = document.createElement('span');
        drift.className = 'badge badge-tone-muted';
        drift.textContent = 'Current profile unavailable';
        badges.appendChild(drift);
      }
      row.appendChild(badges);
      if (text(check.recommended_action_key)) {
        const actions = document.createElement('div');
        actions.className = 'finding-triage-verification-item-actions';
        const launch = document.createElement('button');
        launch.type = 'button';
        launch.className = 'btn btn-secondary btn-compact';
        launch.dataset.findingVerificationLaunch = text(check.check_id);
        launch.textContent = 'Run verification';
        launch.disabled = state.options.canRun === false || check.source_state !== 'available';
        if (state.options.canRun === false) {
          launch.title = "View-only team members can't start verification runs.";
        } else if (check.source_state !== 'available') {
          launch.title = 'The originating check is unavailable.';
        }
        launch.addEventListener('click', async () => {
          if (launch.dataset.pending === 'true') return;
          launch.dataset.pending = 'true';
          launch.disabled = true;
          try {
            await launchVerificationAction(check);
          } catch (err) {
            const message = el('finding-triage-verification-context-message');
            if (message) message.textContent = err.message || 'Could not start the verification run.';
          } finally {
            delete launch.dataset.pending;
            if (launch.isConnected) {
              launch.disabled = state.options.canRun === false || check.source_state !== 'available';
            }
          }
        });
        actions.appendChild(launch);
        row.appendChild(actions);
      }
      node.appendChild(row);
    });
  }

  function renderVerificationSuggestion(suggestion) {
    const node = el('finding-triage-verification-suggestion');
    if (!node) return;
    clearNode(node);
    const runId = text(suggestion && suggestion.run_id);
    if (!runId) {
      node.classList.add('u-hidden');
      return;
    }
    const suggestedStatus = text(suggestion.verification_status);
    const available = !!suggestion.available && ['verified', 'needs_retest'].includes(suggestedStatus);
    const row = verificationItem(
      available ? `Suggested status: ${verificationStatusLabel(suggestedStatus)}` : 'No final status suggested',
      `Based on compatible retest ${runId}`,
    );
    row.classList.add('finding-triage-verification-suggestion');
    const badges = document.createElement('div');
    badges.className = 'finding-triage-verification-item-badges';
    const badge = document.createElement('span');
    badge.className = `badge badge-tone-${available ? verificationStatusTone(suggestedStatus) : 'muted'}`;
    badge.textContent = available ? 'Evidence-backed suggestion' : 'Human review needed';
    badges.appendChild(badge);
    row.appendChild(badges);
    const reason = document.createElement('div');
    reason.className = 'finding-triage-verification-item-reason';
    reason.textContent = text(suggestion.reason);
    row.appendChild(reason);
    if (available) {
      const actions = document.createElement('div');
      actions.className = 'finding-triage-verification-item-actions';
      const apply = document.createElement('button');
      apply.type = 'button';
      apply.className = 'btn btn-secondary btn-compact';
      apply.dataset.findingVerificationUseSuggestion = suggestedStatus;
      apply.textContent = 'Use suggested status';
      apply.disabled = state.options.canEdit === false;
      apply.addEventListener('click', () => {
        const select = el('finding-triage-status');
        if (!select || state.options.canEdit === false) return;
        select.value = suggestedStatus;
        syncStatusSelect();
        setMessage(`${verificationStatusLabel(suggestedStatus)} is selected. Review the evidence, then save triage to record your decision.`);
      });
      actions.appendChild(apply);
      row.appendChild(actions);
    }
    node.appendChild(row);
    node.classList.remove('u-hidden');
  }

  function verificationPlanContent(plan) {
    const wrap = document.createElement('div');
    wrap.className = 'finding-verification-plan';
    const rows = [
      ['Command', plan.display_command],
      ['Target', `${text(plan.target?.type)} · ${text(plan.target?.value)}`],
      ['HTTP profile', text(plan.http_profile?.name, 'None')],
      ['Policy', text(plan.policy_level)],
      ['Scope', `${Number(plan.scope?.target_count || 1)} Project target · fan-out ${Number(plan.scope?.fan_out || 1)}`],
      ['Bounds', text(plan.bounds?.summary, 'One approved Project target')],
      ['Credentials', text(plan.bounds?.credential_use, 'none')],
    ];
    rows.forEach(([labelText, valueText]) => {
      const row = document.createElement('div');
      row.className = 'finding-verification-plan-row';
      const label = document.createElement('span');
      label.className = 'finding-verification-plan-label';
      label.textContent = labelText;
      const value = document.createElement(labelText === 'Command' ? 'code' : 'span');
      value.className = 'finding-verification-plan-value';
      value.textContent = text(valueText, 'None');
      row.append(label, value);
      wrap.appendChild(row);
    });
    return wrap;
  }

  async function launchVerificationAction(check) {
    const projectId = text(state.options && state.options.projectId);
    const findingId = text(state.finding && state.finding.id);
    const checkId = text(check && check.check_id);
    const message = el('finding-triage-verification-context-message');
    if (!projectId || !findingId || !checkId || state.options.canRun === false) return;
    if (message) message.textContent = 'Loading the current verification plan...';
    const url = `/projects/${encodeURIComponent(projectId)}/findings/${encodeURIComponent(findingId)}/verification-actions/${encodeURIComponent(checkId)}`;
    const previewResp = await api()(url, { cache: 'no-store' });
    const previewData = await previewResp.json().catch(() => ({}));
    if (!previewResp.ok) throw new Error(previewData?.error || `HTTP ${previewResp.status}`);
    const plan = previewData?.plan || {};
    if (!plan.launchable) {
      if (message) message.textContent = text(plan.unavailable_reason, 'This verification action is unavailable.');
      return;
    }
    if (!showConfirm) throw new Error('Verification launch confirmation is unavailable.');
    const choice = await showConfirm({
      body: {
        text: 'Start this verification run?',
        note: 'The run will be linked to this Project. Its result will not change the finding disposition automatically.',
      },
      content: verificationPlanContent(plan),
      tone: plan.policy_level === 'standard' ? 'warning' : null,
      actions: [
        { id: 'cancel', label: 'Cancel', role: 'cancel' },
        { id: 'run', label: 'Run verification', role: 'primary' },
      ],
      refocusOnResolve: false,
    });
    if (choice !== 'run') {
      if (message) message.textContent = '';
      return;
    }
    if (message) message.textContent = 'Starting the verification run...';
    const launchResp = await api()(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirmed: true, plan_digest: text(plan.plan_digest) }),
    });
    const launchData = await launchResp.json().catch(() => ({}));
    if (!launchResp.ok) throw new Error(launchData?.error || `HTTP ${launchResp.status}`);
    const run = launchData?.run;
    if (!run?.run_id) throw new Error('Verification run started without a run identifier.');
    if (typeof attachActiveRunFromMonitor !== 'function') {
      throw new Error('The verification run started, but the terminal handoff is unavailable. Open it from History.');
    }
    const attached = await attachActiveRunFromMonitor(run);
    if (!attached) {
      throw new Error('The verification run started, but it could not open in a terminal. Open it from History.');
    }
    close({ restoreFocus: false });
  }

  function comparisonFunction() {
    const hasImported = typeof importedHasHistoryCompareHandler === 'function'
      && importedHasHistoryCompareHandler('fetchAndRenderHistoryComparison');
    return hasImported && typeof importedFetchAndRenderHistoryComparison === 'function'
      ? importedFetchAndRenderHistoryComparison
      : null;
  }

  async function compareVerificationRun(run) {
    const comparison = run && run.comparison;
    const projectId = text(state.options && state.options.projectId);
    const compareFn = comparisonFunction();
    if (!comparison?.available || !compareFn) {
      setMessage('Run comparison is not available for this evidence.', { error: true });
      return;
    }
    const left = text(comparison.left_run_id);
    const right = text(comparison.right_run_id);
    const params = new URLSearchParams({ left, right, project_id: projectId });
    close({ restoreFocus: false });
    await compareFn(left, right, { url: `/history/compare?${params.toString()}` });
  }

  async function refreshVerificationContext() {
    const projectId = text(state.options && state.options.projectId);
    const findingId = text(state.finding && state.finding.id);
    const panel = el('finding-triage-verification-context');
    if (!projectId || !findingId || !panel) {
      panel?.classList.add('u-hidden');
      return;
    }
    panel.classList.remove('u-hidden');
    const message = el('finding-triage-verification-context-message');
    if (message) message.textContent = 'Loading saved verification evidence...';
    try {
      state.verificationContext = await requestVerificationContext(projectId, findingId);
      renderVerificationContext(state.verificationContext);
    } catch (err) {
      state.verificationContext = null;
      if (message) message.textContent = err.message || 'Could not load saved verification evidence.';
    }
  }

  async function unlinkVerificationRun(run) {
    const projectId = text(state.options && state.options.projectId);
    const findingId = text(state.finding && state.finding.id);
    const linkId = text(run && run.evidence_link_id);
    if (!projectId || !findingId || !linkId || state.options.canEdit === false) return;
    const resp = await api()(
      `/projects/${encodeURIComponent(projectId)}/findings/${encodeURIComponent(findingId)}/evidence/${encodeURIComponent(linkId)}`,
      { method: 'DELETE' },
    );
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data && data.error ? data.error : `HTTP ${resp.status}`);
    await refreshVerificationContext();
  }

  async function attachVerificationRun() {
    const projectId = text(state.options && state.options.projectId);
    const findingId = text(state.finding && state.finding.id);
    const select = el('finding-triage-verification-run');
    const runId = text(select && select.value);
    const candidates = Array.isArray(state.verificationContext?.candidate_runs)
      ? state.verificationContext.candidate_runs
      : [];
    const run = candidates.find(item => text(item && item.id) === runId);
    if (!projectId || !findingId || !run || state.options.canEdit === false) return;
    const compatibility = text(run.compatibility && run.compatibility.state, 'unavailable');
    if (compatibility !== 'compatible' && showConfirm) {
      const choice = await showConfirm({
        body: {
          text: 'Attach a run that is not comparable with the original evidence?',
          note: text(run.compatibility && run.compatibility.reason, 'The run can be saved as evidence, but it should not support a final verification disposition.'),
        },
        tone: 'warning',
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'attach', label: 'Attach evidence', role: 'warning' },
        ],
        refocusOnResolve: false,
      });
      if (choice !== 'attach') return;
    }
    const resp = await api()(
      `/projects/${encodeURIComponent(projectId)}/findings/${encodeURIComponent(findingId)}/evidence`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ evidence_type: 'retest_run', evidence_id: runId }),
      },
    );
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data && data.error ? data.error : `HTTP ${resp.status}`);
    await refreshVerificationContext();
  }

  function renderVerificationContext(context) {
    const message = el('finding-triage-verification-context-message');
    const checks = Array.isArray(context?.origin_checks) ? context.origin_checks : [];
    const retests = Array.isArray(context?.retest_runs) ? context.retest_runs : [];
    const candidates = Array.isArray(context?.candidate_runs) ? context.candidate_runs : [];
    renderVerificationSuggestion(context?.suggestion);
    renderOriginChecks(checks);
    const retestNode = el('finding-triage-retest-runs');
    clearNode(retestNode);
    retests.forEach((run) => {
      const row = verificationItem(
        text(run.command, `Saved run ${text(run.id)}`),
        [text(run.command_root), text(run.finished || run.started)].filter(Boolean).join(' · '),
      );
      const badges = document.createElement('div');
      badges.className = 'finding-triage-verification-item-badges';
      badges.appendChild(compatibilityBadge(run.compatibility));
      row.appendChild(badges);
      const reason = document.createElement('div');
      reason.className = 'finding-triage-verification-item-reason';
      reason.textContent = text(run.compatibility && run.compatibility.reason);
      row.appendChild(reason);
      const actions = document.createElement('div');
      actions.className = 'finding-triage-verification-item-actions';
      if (run.comparison?.available) {
        const compare = document.createElement('button');
        compare.type = 'button';
        compare.className = 'btn btn-secondary btn-compact';
        compare.dataset.findingVerificationCompare = text(run.id);
        compare.textContent = 'Compare with original';
        compare.addEventListener('click', () => compareVerificationRun(run));
        actions.appendChild(compare);
      }
      const unlink = document.createElement('button');
      unlink.type = 'button';
      unlink.className = 'btn btn-ghost btn-compact';
      unlink.dataset.findingVerificationUnlink = text(run.evidence_link_id);
      unlink.textContent = 'Remove evidence';
      unlink.disabled = state.options.canEdit === false;
      unlink.addEventListener('click', async () => {
        try {
          await unlinkVerificationRun(run);
        } catch (err) {
          if (message) message.textContent = err.message || 'Could not remove verification evidence.';
        }
      });
      actions.appendChild(unlink);
      row.appendChild(actions);
      retestNode?.appendChild(row);
    });
    const candidateWrap = el('finding-triage-verification-candidates');
    const select = el('finding-triage-verification-run');
    clearNode(select);
    candidates.forEach((run) => {
      const option = document.createElement('option');
      option.value = text(run.id);
      const compatibility = text(run.compatibility && run.compatibility.state, 'unavailable');
      option.textContent = `${text(run.command, run.id)} · ${compatibility.replace(/_/g, ' ')}`;
      select?.appendChild(option);
    });
    candidateWrap?.classList.toggle('u-hidden', !candidates.length);
    if (select && typeof syncAppSelect === 'function') syncAppSelect(select);
    const attach = el('finding-triage-verification-attach');
    if (attach) attach.disabled = state.options.canEdit === false || !candidates.length;
    if (message) {
      if (!checks.length && !retests.length) {
        message.textContent = context?.baseline_source_state === 'available'
          ? 'No assessment check or verification run is linked yet. Candidate runs are compared with the finding’s original run.'
          : 'Original evidence is unavailable. Any attached run will stay marked as unavailable for comparison.';
      } else if (!candidates.length) {
        message.textContent = 'No other completed Project runs are available to attach.';
      } else {
        message.textContent = '';
      }
    }
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
    renderDisposition(triage);
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

  function duplicateSummary(duplicates) {
    const items = Array.isArray(duplicates) ? duplicates : [];
    const titles = items.slice(0, 3).map(item => text(item && item.title, 'Untitled finding'));
    const suffix = items.length > 3 ? ` and ${items.length - 3} more` : '';
    return titles.length ? `${titles.join('; ')}${suffix}` : 'A similar finding already exists.';
  }

  async function confirmDuplicate(duplicates) {
    if (!showConfirm) return false;
    const action = state.finding ? 'Save anyway' : 'Create anyway';
    const choice = await showConfirm({
      body: {
        text: `${Array.isArray(duplicates) ? duplicates.length : 0} possible duplicate findings were found for this target.`,
        note: `${duplicateSummary(duplicates)} Review the match before keeping a separate finding.`,
      },
      tone: 'warning',
      actions: [
        { id: 'cancel', label: 'Cancel', role: 'cancel' },
        { id: 'override', label: action, role: 'warning' },
      ],
      refocusOnResolve: false,
    });
    return choice === 'override';
  }

  async function saveRecord({ allowDuplicate = false } = {}) {
    const projectId = text(state.options && state.options.projectId);
    if (!projectId) return;
    if (state.options && state.options.canEdit === false) {
      setMessage('View-only team members can read finding details but cannot save changes.', { error: true });
      return;
    }
    const payload = recordFromForm({ allowDuplicate });
    const validationError = validateRecord(payload);
    if (validationError) {
      setMessage(validationError, { error: true });
      return;
    }
    const findingId = text(state.finding && state.finding.id);
    const url = findingId
      ? `/projects/${encodeURIComponent(projectId)}/findings/${encodeURIComponent(findingId)}`
      : `/projects/${encodeURIComponent(projectId)}/findings`;
    setMessage('');
    setRecordDisabled(true);
    try {
      const resp = await api()(url, {
        method: findingId ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await resp.json().catch(() => ({}));
      if (resp.status === 409 && data && data.conflict === 'possible_duplicate') {
        setRecordDisabled(false);
        if (await confirmDuplicate(data.duplicates)) {
          await saveRecord({ allowDuplicate: true });
        }
        return;
      }
      if (resp.status === 409 && data && data.conflict === 'stale_revision') {
        setMessage(
          `This finding changed after the editor opened (current revision ${Number(data.current_revision || 0)}). Close and reopen it before saving.`,
          { error: true },
        );
        const onConflict = state.options && typeof state.options.onConflict === 'function'
          ? state.options.onConflict
          : null;
        if (onConflict) await onConflict(data, state.finding);
        return;
      }
      if (!resp.ok) throw new Error(data && data.error ? data.error : `HTTP ${resp.status}`);
      const finding = data && data.finding && typeof data.finding === 'object'
        ? data.finding
        : state.finding;
      const onSaved = state.options && typeof state.options.onSaved === 'function'
        ? state.options.onSaved
        : null;
      close();
      if (onSaved) await onSaved(finding, data);
    } catch (err) {
      setMessage(err.message || 'Could not save the finding.', { error: true });
    } finally {
      if (isOpen() && state.mode === 'record') {
        setRecordDisabled(!(state.options && state.options.canEdit !== false));
      }
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
    el('finding-record-form')?.addEventListener('submit', (event) => {
      event.preventDefault();
      saveRecord();
    });
    el('finding-record-cancel')?.addEventListener('click', close);
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
    el('finding-triage-verification-attach')?.addEventListener('click', async () => {
      const message = el('finding-triage-verification-context-message');
      try {
        await attachVerificationRun();
      } catch (err) {
        if (message) message.textContent = err.message || 'Could not attach verification evidence.';
      }
    });
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
    rememberReturnFocus(overlay, state.options);
    setMode('triage');
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
      await refreshVerificationContext();
      window.setTimeout(() => el('finding-triage-remediation')?.focus({ preventScroll: true }), 0);
    } catch (err) {
      setMessage(err.message || 'Could not load finding triage.', { error: true });
      setDisabled(true);
    }
  }

  async function openRecord(options = {}) {
    const overlay = el('finding-triage-overlay');
    if (!overlay || !el('finding-record-form')) {
      throw new Error('Finding editor is not available.');
    }
    const projectId = text(options && options.projectId);
    if (!projectId) throw new Error('Project is missing its identifier.');
    const finding = options && options.finding && typeof options.finding === 'object'
      ? options.finding
      : null;
    if (finding && text(finding.origin) !== 'manual') {
      throw new Error('Only assessor-authored findings can be edited here.');
    }
    if (finding && !text(finding.id)) throw new Error('Finding is missing its identifier.');
    bindOnce();
    state.finding = finding;
    state.options = options || {};
    rememberReturnFocus(overlay, state.options);
    setMode('record');
    const targets = populateRecord(finding, state.options);
    if (!finding && !targets.length) {
      state.finding = null;
      state.options = {};
      throw new Error('Create and confirm a Project target before adding a finding.');
    }
    const subtitle = el('finding-triage-subtitle');
    if (subtitle) subtitle.textContent = finding
      ? titleForFinding(finding)
      : 'Record an issue against a confirmed Project target.';
    setMessage(state.options.canEdit === false
      ? 'View-only team members can read finding details but cannot save changes.'
      : '');
    overlay.classList.remove('u-hidden');
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
    bindOpenChrome(overlay);
    setRecordDisabled(state.options.canEdit === false);
    global.setTimeout(() => {
      const focusTarget = finding ? el('finding-record-title') : el('finding-record-target');
      focusTarget?.focus({ preventScroll: true });
    }, 0);
  }

  DarklabFindingTriageEditor = {
    compactTriage,
    close,
    isOpen,
    open,
    openRecord,
    verificationStatusLabel,
    verificationStatusTone,
    verificationStates: VERIFICATION_STATES.slice(),
  };
})(typeof window !== 'undefined' ? window : globalThis);

const compactTriage = DarklabFindingTriageEditor.compactTriage;
const closeFindingTriageEditor = DarklabFindingTriageEditor.close;
const isFindingTriageEditorOpen = DarklabFindingTriageEditor.isOpen;
const openFindingTriageEditor = DarklabFindingTriageEditor.open;
const openFindingRecordEditor = DarklabFindingTriageEditor.openRecord;
const verificationStatusLabel = DarklabFindingTriageEditor.verificationStatusLabel;
const verificationStatusTone = DarklabFindingTriageEditor.verificationStatusTone;
const verificationStates = DarklabFindingTriageEditor.verificationStates;

export {
  DarklabFindingTriageEditor,
  closeFindingTriageEditor,
  compactTriage,
  isFindingTriageEditorOpen,
  openFindingTriageEditor,
  openFindingRecordEditor,
  verificationStatusLabel,
  verificationStatusTone,
  verificationStates,
};
