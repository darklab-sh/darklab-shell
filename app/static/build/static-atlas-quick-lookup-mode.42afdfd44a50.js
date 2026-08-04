// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Atlas-owned Quick Lookup state and request controller. The surrounding
// overlay supplies navigation and the shared entity-profile renderer.

const LOOKUP_MODES = new Set(['auto', 'hostname', 'ip', 'url']);

function quickLookupElements(document) {
  const byId = (id) => document?.getElementById?.(id) || null;
  return {
    root: byId('atlas-quick-lookup'),
    form: byId('atlas-lookup-form'),
    formView: byId('atlas-lookup-form-view'),
    input: byId('atlas-lookup-input'),
    modeSelect: byId('atlas-lookup-mode'),
    scopeLabel: byId('atlas-lookup-scope'),
    status: byId('atlas-lookup-status'),
    resumeButton: byId('atlas-lookup-resume'),
    outcomeView: byId('atlas-lookup-outcome-view'),
    outcomeTitle: byId('atlas-lookup-outcome-title'),
    outcomeBody: byId('atlas-lookup-outcome-body'),
    outcomeContext: byId('atlas-lookup-outcome-context'),
    outcomeCandidates: byId('atlas-lookup-outcome-candidates'),
    outcomeActions: byId('atlas-lookup-outcome-actions'),
    outcomeNewButton: byId('atlas-lookup-outcome-new'),
    profileView: byId('atlas-lookup-profile-view'),
    profileHost: byId('atlas-lookup-profile'),
    profileNewButton: byId('atlas-lookup-profile-new'),
    openAtlasButton: byId('atlas-lookup-open-atlas'),
    profileScope: byId('atlas-lookup-profile-scope'),
  };
}

function quickLookupScope({ options = {}, teamScope = null } = {}) {
  const projectId = String(options.projectId || '').trim();
  const projectName = String(options.projectName || '').trim();
  if (projectId) {
    return {
      kind: 'project',
      id: projectId,
      projectId,
      label: `Project · ${projectName || projectId}`,
    };
  }
  const activeTeamId = typeof teamScope?.getActiveTeamId === 'function'
    ? String(teamScope.getActiveTeamId() || '')
    : '';
  const activeTeam = typeof teamScope?.getActiveTeam === 'function'
    ? teamScope.getActiveTeam()
    : null;
  if (activeTeamId) {
    return {
      kind: 'team',
      id: activeTeamId,
      projectId: '',
      label: `Team · ${String(activeTeam?.name || activeTeam?.slug || activeTeamId)}`,
    };
  }
  return { kind: 'personal', id: '', projectId: '', label: 'Personal' };
}

function normalizeMode(value) {
  const mode = String(value || 'auto').trim().toLowerCase();
  return LOOKUP_MODES.has(mode) ? mode : 'auto';
}

function lookupOutcomeCopy(result = {}) {
  const canonical = String(result.canonical_value || '').trim();
  if (result.match_state === 'ambiguous') {
    return {
      title: 'More than one saved entity matched',
      body: canonical
        ? `${canonical} has multiple records in this scope. Choose a record to continue.`
        : 'This value has multiple records in the current scope.',
    };
  }
  if (result.match_state === 'not_found') {
    if (result.parent_host_candidate) {
      return {
        title: 'No saved record for this URL',
        body: canonical
          ? `Atlas does not have a saved record for ${canonical} in this scope, but it does have data for the URL's parent host.`
          : "Atlas does not have a saved record for this URL, but it does have data for the URL's parent host.",
      };
    }
    return {
      title: 'No saved Atlas entity',
      body: canonical
        ? `Atlas does not have a saved record for ${canonical} in this scope. That does not mean the value itself is invalid.`
        : 'Atlas does not have a saved record for this value in the current scope. That does not mean the value itself is invalid.',
    };
  }
  return {
    title: 'Lookup unavailable',
    body: 'Atlas could not resolve this value in the current scope.',
  };
}

function candidateProvenanceLabel(value) {
  const labels = {
    direct_team: 'Direct team record',
    compatibility_visible: 'Compatibility-visible record',
    personal: 'Personal record',
  };
  return labels[String(value || '')] || 'Saved record';
}

function lookupCommandSuggestion(result = {}) {
  const entityType = String(result.detected_type || '').trim().toLowerCase();
  const value = String(result.canonical_value || '').trim();
  if (!value) return null;
  const quoted = `'${value.replace(/'/g, `'"'"'`)}'`;
  if (entityType === 'url') {
    return { label: 'Prefill curl check', command: `curl -I -- ${quoted}` };
  }
  if (entityType === 'domain' || entityType === 'ip') {
    return { label: 'Prefill nmap scan', command: `nmap -sV -- ${quoted}` };
  }
  return null;
}

function createAtlasQuickLookupMode({
  global = globalThis,
  elements = {},
  apiFetch,
  onFound = null,
  onOpenInAtlas = null,
  onSelectCandidate = null,
  onSwitchScope = null,
  onPrefillCommand = null,
  onReset = null,
  onStateChange = null,
  onLogEvent = null,
  onError = null,
} = {}) {
  const {
    root,
    form,
    formView,
    input,
    modeSelect,
    scopeLabel,
    status,
    resumeButton,
    outcomeView,
    outcomeTitle,
    outcomeBody,
    outcomeContext,
    outcomeCandidates,
    outcomeActions,
    outcomeNewButton,
    profileView,
    profileHost,
    profileNewButton,
    openAtlasButton,
  } = elements;

  const state = {
    active: false,
    root: 'form',
    rawDraft: '',
    selectedMode: 'auto',
    submittedRawValue: '',
    submittedMode: 'auto',
    submittedCanonicalValue: '',
    result: null,
    requestStatus: 'idle',
    requestMessage: '',
    launchScope: { kind: 'personal', id: '', label: 'Personal', projectId: '' },
    requestSeq: 0,
  };

  let requestController = null;
  let activeRequest = null;

  function nowMs() {
    return typeof global.performance?.now === 'function'
      ? global.performance.now()
      : Date.now();
  }

  function emitLogEvent(event, details = {}) {
    if (typeof onLogEvent === 'function') onLogEvent(event, details);
  }

  function requestScopeFields() {
    const scopeKind = ['personal', 'team', 'project'].includes(String(state.launchScope.kind || ''))
      ? String(state.launchScope.kind)
      : 'personal';
    return {
      lookup_mode: normalizeMode(state.selectedMode),
      scope_kind: scopeKind,
      project_scoped: !!state.launchScope.projectId,
    };
  }

  function discardActiveRequest(reason = 'aborted') {
    if (!activeRequest) return;
    emitLogEvent('ATLAS_QUICK_LOOKUP_REQUEST_DISCARDED', {
      ...requestScopeFields(),
      reason: String(reason || 'aborted'),
      request_seq: activeRequest.id,
      duration_ms: Math.max(0, Math.round(nowMs() - activeRequest.startedAt)),
    });
    activeRequest = null;
  }

  function settleActiveRequest(requestId, result) {
    if (!activeRequest || activeRequest.id !== requestId) return;
    emitLogEvent('ATLAS_QUICK_LOOKUP_REQUEST_SETTLED', {
      ...requestScopeFields(),
      detected_type: ['domain', 'ip', 'url'].includes(String(result?.detected_type || ''))
        ? String(result.detected_type)
        : '',
      match_state: ['found', 'not_found', 'ambiguous'].includes(String(result?.match_state || ''))
        ? String(result.match_state)
        : '',
      candidate_count: Array.isArray(result?.candidates) ? result.candidates.length : 0,
      parent_candidate: !!result?.parent_host_candidate,
      request_seq: requestId,
      duration_ms: Math.max(0, Math.round(nowMs() - activeRequest.startedAt)),
    });
    activeRequest = null;
  }

  function emitStateChange() {
    if (typeof onStateChange === 'function') onStateChange(state);
  }

  function abortRequest(reason = 'aborted') {
    if (requestController) requestController.abort();
    requestController = null;
    discardActiveRequest(reason);
  }

  function requestOptions(extra = {}) {
    if (requestController && requestController.signal) {
      return { ...extra, signal: requestController.signal };
    }
    return extra;
  }

  function isAbortError(err) {
    return !!err && (err.name === 'AbortError' || err.code === 20);
  }

  function setStatus(message = '', tone = '') {
    state.requestMessage = String(message || '');
    if (!status) return;
    status.textContent = state.requestMessage;
    status.classList.toggle('u-hidden', !state.requestMessage);
    status.classList.toggle('is-error', tone === 'error');
    status.classList.toggle('is-loading', tone === 'loading');
  }

  function render() {
    root?.classList.toggle('u-hidden', !state.active);
    formView?.classList.toggle('u-hidden', !state.active || state.root !== 'form');
    outcomeView?.classList.toggle('u-hidden', !state.active || state.root !== 'outcome');
    profileView?.classList.toggle('u-hidden', !state.active || state.root !== 'profile');
    if (input && input.value !== state.rawDraft) input.value = state.rawDraft;
    if (modeSelect && modeSelect.value !== state.selectedMode) modeSelect.value = state.selectedMode;
    if (scopeLabel) scopeLabel.textContent = state.launchScope.label || 'Personal';
    if (input) input.disabled = state.requestStatus === 'loading';
    if (modeSelect) modeSelect.disabled = state.requestStatus === 'loading';
    const submitButton = form?.querySelector?.('[type="submit"]');
    if (submitButton) {
      submitButton.disabled = state.requestStatus === 'loading';
      submitButton.textContent = state.requestStatus === 'loading' ? 'Looking up...' : 'Look up';
      submitButton.setAttribute('aria-busy', state.requestStatus === 'loading' ? 'true' : 'false');
    }
    if (resumeButton) {
      const canResume = !!state.result?.detail && state.root === 'form';
      resumeButton.classList.toggle('u-hidden', !canResume);
      resumeButton.disabled = !canResume;
    }
    if (openAtlasButton) openAtlasButton.disabled = !state.result?.detail;
    emitStateChange();
  }

  function focusInput() {
    global.setTimeout?.(() => input?.focus?.({ preventScroll: true }), 0);
  }

  function activate({ value = '', mode = 'auto', scope = null, submit = false } = {}) {
    abortRequest('new_lookup');
    state.active = true;
    state.root = 'form';
    state.rawDraft = String(value || '');
    state.selectedMode = normalizeMode(mode);
    state.submittedRawValue = '';
    state.submittedMode = state.selectedMode;
    state.submittedCanonicalValue = '';
    state.result = null;
    state.requestStatus = 'idle';
    state.launchScope = scope && typeof scope === 'object'
      ? { ...state.launchScope, ...scope }
      : { kind: 'personal', id: '', label: 'Personal', projectId: '' };
    setStatus();
    render();
    if (submit && state.rawDraft.trim()) return submitLookup();
    focusInput();
    return Promise.resolve(true);
  }

  function restore(snapshot = {}) {
    const result = snapshot.result && typeof snapshot.result === 'object'
      ? snapshot.result
      : null;
    const rootName = ['form', 'outcome', 'profile'].includes(String(snapshot.root || ''))
      ? String(snapshot.root)
      : (result?.detail ? 'profile' : 'form');
    abortRequest('new_lookup');
    state.requestSeq += 1;
    state.active = true;
    state.root = rootName;
    state.rawDraft = String(snapshot.rawDraft || '');
    state.selectedMode = normalizeMode(snapshot.selectedMode);
    state.submittedRawValue = String(snapshot.submittedRawValue || '');
    state.submittedMode = normalizeMode(snapshot.submittedMode || state.selectedMode);
    state.submittedCanonicalValue = String(snapshot.submittedCanonicalValue || result?.canonical_value || '');
    state.result = result;
    state.requestStatus = result ? 'success' : 'idle';
    state.launchScope = snapshot.launchScope && typeof snapshot.launchScope === 'object'
      ? { ...state.launchScope, ...snapshot.launchScope }
      : { kind: 'personal', id: '', label: 'Personal', projectId: '' };
    setStatus();
    render();
    if (state.root === 'form') focusInput();
    return true;
  }

  function deactivate() {
    abortRequest('closed');
    state.requestSeq += 1;
    state.active = false;
    state.requestStatus = 'idle';
    setStatus();
    render();
  }

  function showForm({ focus = true, message = '' } = {}) {
    abortRequest('new_lookup');
    state.requestSeq += 1;
    if (typeof onReset === 'function') onReset();
    state.root = 'form';
    state.requestStatus = 'idle';
    setStatus(message);
    render();
    if (focus) focusInput();
  }

  function showProfile(result = state.result) {
    if (!result?.detail) return false;
    state.result = result;
    state.root = 'profile';
    state.requestStatus = 'success';
    setStatus();
    render();
    return true;
  }

  function profileContextLabel() {
    const origin = state.result?.lookup_origin;
    if (origin?.kind === 'url_parent' && origin.canonical_value) {
      return `Known parent for ${origin.canonical_value} · ${state.launchScope.label || 'Personal'}`;
    }
    return state.launchScope.label || 'Personal';
  }

  function syncProfileDetail(detail) {
    const entity = detail?.entity || null;
    if (!entity?.id || !entity?.type) return false;
    state.result = {
      ...(state.result || {}),
      match_state: 'found',
      detected_type: String(entity.type),
      canonical_value: String(entity.canonical_value || state.submittedCanonicalValue || ''),
      detail,
    };
    if (openAtlasButton) openAtlasButton.disabled = false;
    return true;
  }

  function makeOutcomeButton(label, className, onClick) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = className;
    button.textContent = label;
    button.addEventListener('click', onClick);
    return button;
  }

  function renderCandidate(candidate, { parent = false } = {}) {
    const button = makeOutcomeButton(
      parent ? 'Open known parent host' : 'Open saved record',
      'btn btn-ghost panel-row panel-row-clickable atlas-lookup-candidate',
      () => selectCandidate(candidate, { parent }),
    );
    const identity = document.createElement('span');
    identity.className = 'atlas-lookup-candidate-identity';
    const type = document.createElement('span');
    type.className = 'badge badge-tone-muted';
    type.textContent = String(candidate.type || '').toUpperCase();
    const value = document.createElement('strong');
    value.textContent = String(candidate.canonical_value || candidate.entity_id || 'Saved entity');
    identity.append(type, value);

    const meta = document.createElement('span');
    meta.className = 'atlas-lookup-candidate-meta';
    const details = [candidateProvenanceLabel(candidate.provenance)];
    if (candidate.occurrence_count !== undefined) {
      const count = Number(candidate.occurrence_count || 0);
      details.push(`${count.toLocaleString()} observation${count === 1 ? '' : 's'}`);
    }
    if (candidate.last_seen_at) details.push(`Last seen ${String(candidate.last_seen_at)}`);
    if (candidate.suppressed) details.push('Suppressed');
    meta.textContent = details.join(' · ');
    const action = document.createElement('span');
    action.className = 'atlas-lookup-candidate-action';
    action.textContent = parent ? 'Open known parent host' : 'Open saved record';
    button.replaceChildren(identity, meta, action);
    return button;
  }

  function renderOutcome(result) {
    const copy = lookupOutcomeCopy(result);
    if (outcomeTitle) outcomeTitle.textContent = copy.title;
    if (outcomeBody) outcomeBody.textContent = copy.body;
    if (outcomeContext) {
      outcomeContext.replaceChildren();
      const value = document.createElement('code');
      value.textContent = String(result.canonical_value || state.submittedRawValue || '');
      if (value.textContent) outcomeContext.append('Requested value', value);
      outcomeContext.classList.toggle('u-hidden', !value.textContent);
    }
    if (outcomeCandidates) {
      outcomeCandidates.replaceChildren();
      const candidates = Array.isArray(result.candidates) ? result.candidates : [];
      if (result.match_state === 'ambiguous' && candidates.length) {
        const heading = document.createElement('strong');
        heading.textContent = 'Choose a saved record';
        outcomeCandidates.appendChild(heading);
        candidates.forEach(candidate => outcomeCandidates.appendChild(renderCandidate(candidate)));
        if (result.candidates_truncated) {
          const note = document.createElement('span');
          note.className = 'atlas-muted';
          note.textContent = 'Only the first bounded set of matches is shown.';
          outcomeCandidates.appendChild(note);
        }
      }
      const parent = result.parent_host_candidate;
      if (parent) {
        const heading = document.createElement('strong');
        heading.textContent = 'Known parent host';
        outcomeCandidates.appendChild(heading);
        if (parent.entity) outcomeCandidates.appendChild(renderCandidate(parent.entity, { parent: true }));
        (Array.isArray(parent.candidates) ? parent.candidates : [])
          .forEach(candidate => outcomeCandidates.appendChild(renderCandidate(candidate, { parent: true })));
        if (parent.candidates_truncated) {
          const note = document.createElement('span');
          note.className = 'atlas-muted';
          note.textContent = 'Only the first bounded set of parent-host matches is shown.';
          outcomeCandidates.appendChild(note);
        }
      }
      outcomeCandidates.classList.toggle('u-hidden', !outcomeCandidates.childElementCount);
    }
    if (outcomeActions) {
      Array.from(outcomeActions.children).forEach(child => {
        if (child !== outcomeNewButton) child.remove();
      });
      if (result.canonical_value && typeof onOpenInAtlas === 'function') {
        outcomeActions.appendChild(makeOutcomeButton(
          'Search Atlas',
          'btn btn-secondary btn-compact',
          () => onOpenInAtlas(result, { search: true }),
        ));
      }
      if (typeof onSwitchScope === 'function') {
        outcomeActions.appendChild(makeOutcomeButton(
          'Switch scope',
          'btn btn-ghost btn-compact',
          () => onSwitchScope(result),
        ));
      }
      const suggestion = lookupCommandSuggestion(result);
      if (suggestion && typeof onPrefillCommand === 'function') {
        outcomeActions.appendChild(makeOutcomeButton(
          suggestion.label,
          'btn btn-ghost btn-compact',
          () => onPrefillCommand(suggestion.command, result),
        ));
      }
    }
  }

  function showOutcome(result) {
    renderOutcome(result);
    state.root = 'outcome';
    state.requestStatus = 'success';
    setStatus();
    render();
  }

  async function selectCandidate(candidate, { parent = false } = {}) {
    if (!candidate?.entity_id || typeof onSelectCandidate !== 'function') return false;
    const requestId = state.requestSeq + 1;
    state.requestSeq = requestId;
    state.requestStatus = 'loading';
    const label = String(candidate.canonical_value || candidate.entity_id);
    if (outcomeBody) outcomeBody.textContent = `Loading ${label}...`;
    render();
    try {
      const resolved = await onSelectCandidate(candidate, {
        parent,
        lookupResult: state.result,
      });
      if (!state.active || requestId !== state.requestSeq || !resolved?.detail) return false;
      const previous = state.result || {};
      const nextResult = {
        ...previous,
        ...resolved,
        match_state: 'found',
        detected_type: String(candidate.type || resolved.detected_type || ''),
        canonical_value: String(candidate.canonical_value || resolved.canonical_value || ''),
        candidates: [],
        candidates_truncated: false,
        parent_host_candidate: null,
      };
      if (parent) {
        nextResult.lookup_origin = {
          kind: 'url_parent',
          detected_type: String(previous.detected_type || 'url'),
          canonical_value: String(previous.canonical_value || state.submittedCanonicalValue || state.submittedRawValue),
        };
      }
      state.result = nextResult;
      state.submittedCanonicalValue = nextResult.canonical_value;
      state.root = 'profile';
      if (typeof onFound === 'function') await onFound(nextResult);
      if (!state.active || requestId !== state.requestSeq) return false;
      return showProfile(nextResult);
    } catch (err) {
      if (requestId !== state.requestSeq || !state.active) return false;
      state.requestStatus = 'error';
      if (outcomeBody) outcomeBody.textContent = 'Atlas could not load that saved record. Choose another record or start a new lookup.';
      render();
      if (typeof onError === 'function') onError(err);
      return false;
    }
  }

  async function responseError(resp) {
    let payload = {};
    try { payload = await resp.json(); } catch (_) {}
    const err = new Error(String(payload.message || payload.error || `HTTP ${resp.status}`));
    err.status = Number(resp.status || 0);
    err.lookupHandled = err.status >= 400 && err.status < 500;
    return err;
  }

  async function submitLookup({ value: explicitValue, mode: explicitMode } = {}) {
    if (!state.active || state.requestStatus === 'loading') return false;
    state.rawDraft = explicitValue === undefined
      ? String(input?.value ?? state.rawDraft ?? '')
      : String(explicitValue ?? '');
    state.selectedMode = normalizeMode(
      explicitMode === undefined ? (modeSelect?.value || state.selectedMode) : explicitMode,
    );
    const value = state.rawDraft.trim();
    if (!value) {
      state.requestStatus = 'error';
      setStatus('Enter a hostname, IP address, or absolute HTTP(S) URL.', 'error');
      render();
      input?.focus?.({ preventScroll: true });
      return false;
    }

    abortRequest('new_lookup');
    const requestId = state.requestSeq + 1;
    state.requestSeq = requestId;
    requestController = typeof global.AbortController === 'function'
      ? new global.AbortController()
      : null;
    activeRequest = { id: requestId, startedAt: nowMs() };
    emitLogEvent('ATLAS_QUICK_LOOKUP_REQUEST_STARTED', {
      ...requestScopeFields(),
      request_seq: requestId,
    });
    state.submittedRawValue = value;
    state.submittedMode = state.selectedMode;
    state.requestStatus = 'loading';
    setStatus(`Looking for ${value} in ${state.launchScope.label || 'this scope'}...`, 'loading');
    render();
    try {
      const body = { mode: state.selectedMode, value };
      if (state.launchScope.projectId) body.project_id = state.launchScope.projectId;
      const resp = await apiFetch('/atlas/lookup', requestOptions({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }));
      if (!resp.ok) throw await responseError(resp);
      const result = await resp.json();
      if (!state.active || requestId !== state.requestSeq) {
        discardActiveRequest(state.active ? 'stale' : 'closed');
        return false;
      }
      state.result = result;
      state.submittedCanonicalValue = String(result.canonical_value || value);
      if (result.match_state === 'found' && result.detail) {
        state.root = 'profile';
        state.requestStatus = 'success';
        setStatus();
        if (typeof onFound === 'function') await onFound(result);
        if (!state.active || requestId !== state.requestSeq) {
          discardActiveRequest(state.active ? 'stale' : 'closed');
          return false;
        }
        settleActiveRequest(requestId, result);
        render();
        return true;
      }
      settleActiveRequest(requestId, result);
      showOutcome(result);
      return true;
    } catch (err) {
      if (isAbortError(err) || requestId !== state.requestSeq || !state.active) {
        discardActiveRequest(state.active ? 'stale' : 'closed');
        return false;
      }
      discardActiveRequest(err?.lookupHandled ? 'rejected' : 'failed');
      state.requestStatus = 'error';
      state.root = 'form';
      setStatus(err?.message || 'Quick Lookup failed. Try again.', 'error');
      render();
      if (typeof onError === 'function' && !err?.lookupHandled) onError(err);
      return false;
    } finally {
      if (requestId === state.requestSeq) requestController = null;
    }
  }

  function resumeResult() {
    if (!state.result?.detail) return false;
    return showProfile(state.result);
  }

  function invalidateScopeResult({ value, mode }) {
    abortRequest('scope_changed');
    state.requestSeq += 1;
    if (typeof onReset === 'function') onReset();
    state.root = 'form';
    state.rawDraft = String(value || '');
    state.selectedMode = normalizeMode(mode);
    state.submittedCanonicalValue = '';
    state.result = null;
    state.requestStatus = 'idle';
    setStatus();
    profileHost?.replaceChildren?.();
    render();
  }

  function updateScope(scope = {}) {
    state.launchScope = { ...state.launchScope, ...scope };
    render();
    if (!state.active || !state.submittedRawValue) {
      showForm({ focus: false, message: 'Scope changed. Enter a lookup for the new scope.' });
      return Promise.resolve(false);
    }
    const submittedValue = state.submittedRawValue;
    const submittedMode = state.submittedMode;
    invalidateScopeResult({ value: submittedValue, mode: submittedMode });
    return submitLookup({
      value: submittedValue,
      mode: submittedMode,
    });
  }

  form?.addEventListener('submit', (event) => {
    event.preventDefault();
    submitLookup();
  });
  input?.addEventListener('input', () => {
    state.rawDraft = String(input.value || '');
  });
  modeSelect?.addEventListener('change', () => {
    state.selectedMode = normalizeMode(modeSelect.value);
  });
  resumeButton?.addEventListener('click', resumeResult);
  outcomeNewButton?.addEventListener('click', () => showForm());
  profileNewButton?.addEventListener('click', () => showForm());
  openAtlasButton?.addEventListener('click', () => {
    if (state.result?.detail && typeof onOpenInAtlas === 'function') onOpenInAtlas(state.result);
  });

  render();

  return {
    state,
    profileHost,
    activate,
    deactivate,
    abortRequest,
    isActive: () => state.active,
    isProfileVisible: () => state.active && state.root === 'profile',
    render,
    profileContextLabel,
    restore,
    resumeResult,
    showForm,
    showProfile,
    syncProfileDetail,
    submit: submitLookup,
    updateScope,
  };
}

export {
  createAtlasQuickLookupMode,
  lookupOutcomeCopy,
  normalizeMode,
  quickLookupElements,
  quickLookupScope,
};
