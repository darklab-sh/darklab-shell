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
    return {
      title: 'No saved Atlas entity',
      body: canonical
        ? `Atlas does not have a saved record for ${canonical} in this scope.`
        : 'Atlas does not have a saved record for this value in the current scope.',
    };
  }
  return {
    title: 'Lookup unavailable',
    body: 'Atlas could not resolve this value in the current scope.',
  };
}

function createAtlasQuickLookupMode({
  global = globalThis,
  elements = {},
  apiFetch,
  onFound = null,
  onOpenInAtlas = null,
  onStateChange = null,
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
    submittedCanonicalValue: '',
    result: null,
    requestStatus: 'idle',
    requestMessage: '',
    launchScope: { kind: 'personal', id: '', label: 'Personal', projectId: '' },
    requestSeq: 0,
  };

  let requestController = null;

  function emitStateChange() {
    if (typeof onStateChange === 'function') onStateChange(state);
  }

  function abortRequest() {
    if (requestController) requestController.abort();
    requestController = null;
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
    abortRequest();
    state.active = true;
    state.root = 'form';
    state.rawDraft = String(value || '');
    state.selectedMode = normalizeMode(mode);
    state.submittedRawValue = '';
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

  function deactivate() {
    abortRequest();
    state.requestSeq += 1;
    state.active = false;
    state.requestStatus = 'idle';
    setStatus();
    render();
  }

  function showForm({ focus = true, message = '' } = {}) {
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

  function showOutcome(result) {
    const copy = lookupOutcomeCopy(result);
    if (outcomeTitle) outcomeTitle.textContent = copy.title;
    if (outcomeBody) outcomeBody.textContent = copy.body;
    state.root = 'outcome';
    state.requestStatus = 'success';
    setStatus();
    render();
  }

  async function responseError(resp) {
    let payload = {};
    try { payload = await resp.json(); } catch (_) {}
    const err = new Error(String(payload.message || payload.error || `HTTP ${resp.status}`));
    err.status = Number(resp.status || 0);
    err.lookupHandled = err.status >= 400 && err.status < 500;
    return err;
  }

  async function submitLookup() {
    if (!state.active || state.requestStatus === 'loading') return false;
    state.rawDraft = String(input?.value ?? state.rawDraft ?? '');
    state.selectedMode = normalizeMode(modeSelect?.value || state.selectedMode);
    const value = state.rawDraft.trim();
    if (!value) {
      state.requestStatus = 'error';
      setStatus('Enter a hostname, IP address, or absolute HTTP(S) URL.', 'error');
      render();
      input?.focus?.({ preventScroll: true });
      return false;
    }

    abortRequest();
    const requestId = state.requestSeq + 1;
    state.requestSeq = requestId;
    requestController = typeof global.AbortController === 'function'
      ? new global.AbortController()
      : null;
    state.submittedRawValue = value;
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
      if (!state.active || requestId !== state.requestSeq) return false;
      state.result = result;
      state.submittedCanonicalValue = String(result.canonical_value || value);
      if (result.match_state === 'found' && result.detail) {
        state.root = 'profile';
        state.requestStatus = 'success';
        setStatus();
        if (typeof onFound === 'function') await onFound(result);
        if (!state.active || requestId !== state.requestSeq) return false;
        render();
        return true;
      }
      showOutcome(result);
      return true;
    } catch (err) {
      if (isAbortError(err) || requestId !== state.requestSeq || !state.active) return false;
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

  function updateScope(scope = {}) {
    state.launchScope = { ...state.launchScope, ...scope };
    render();
    if (!state.active || !state.submittedRawValue) {
      showForm({ focus: false, message: 'Scope changed. Enter a lookup for the new scope.' });
      return Promise.resolve(false);
    }
    state.rawDraft = state.submittedRawValue;
    state.requestStatus = 'idle';
    return submitLookup();
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
