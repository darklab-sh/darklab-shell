// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Private OAST reservation recovery, readiness polling, and guarded launch.

import { attachActiveRunFromMonitor as importedAttachActiveRunFromMonitor } from '../../runner_bridge.js';
import { logAssessmentClientFailure } from './project_assessment_client_log.js';
import {
  chooseHttpProfile,
  chooseParameterEvidence,
  planContent,
  previewPath,
  responseError,
  restoreFocus,
  text,
} from './project_assessment_actions.js';

const privateOastActionKey = 'oast_private_callback';
const liveStatuses = new Set(['reserved', 'active']);
const retryableStatuses = new Set(['closed', 'expired', 'failed']);
const visiblePollDelayMs = 3000;
const hiddenPollDelayMs = 15000;

function isPrivateOastCheck(check) {
  return String(check?.recommended_action_key || '') === privateOastActionKey;
}

function safeCorrelation(value) {
  const correlation = value && typeof value === 'object' ? value : {};
  return {
    id: text(correlation.id),
    project_id: text(correlation.project_id),
    assessment_id: text(correlation.assessment_id),
    check_id: text(correlation.check_id),
    action_key: text(correlation.action_key),
    run_id: text(correlation.run_id),
    status: text(correlation.status),
    provider_ready: correlation.provider_ready === true,
    interaction_count: Math.max(0, Number(correlation.interaction_count || 0)),
    duplicate_count: Math.max(0, Number(correlation.duplicate_count || 0)),
    rejected_count: Math.max(0, Number(correlation.rejected_count || 0)),
    error_code: text(correlation.error_code),
    created_at: text(correlation.created_at),
    updated_at: text(correlation.updated_at),
    activated_at: text(correlation.activated_at),
    closed_at: text(correlation.closed_at),
    active_until: text(correlation.active_until),
    purge_at: text(correlation.purge_at),
  };
}

function oastPlanContent(plan) {
  const content = planContent(plan);
  content.classList.add('project-assessment-oast-plan');
  const rows = [
    ['Callback', 'App-owned private identity'],
    ['Preparation window', `${Number(plan?.oast?.reservation_window_seconds || 0)} seconds`],
    ['Provider contact', 'Only after this preparation is confirmed'],
  ];
  rows.forEach(([labelText, valueText]) => {
    const row = document.createElement('div');
    row.className = 'finding-verification-plan-row';
    const label = document.createElement('span');
    label.className = 'finding-verification-plan-label';
    label.textContent = labelText;
    const value = document.createElement('span');
    value.className = 'finding-verification-plan-value';
    value.textContent = valueText;
    row.append(label, value);
    content.appendChild(row);
  });
  return content;
}

function createProjectAssessmentOastManager(context, hooks = {}) {
  const ctx = context || {};
  const states = new Map();

  function stateKey(projectId, assessmentId, checkId) {
    return [projectId, assessmentId, checkId].map(value => String(value || '')).join(':');
  }

  function stateFor(projectId, assessmentId, checkId) {
    const key = stateKey(projectId, assessmentId, checkId);
    if (!states.has(key)) {
      states.set(key, {
        projectId: text(projectId),
        assessmentId: text(assessmentId),
        checkId: text(checkId),
        correlations: [],
        loaded: false,
        loading: false,
        loadPromise: null,
        mutating: '',
        error: '',
        pollTimer: null,
      });
    }
    return states.get(key);
  }

  function renderViews() {
    hooks.renderViews?.();
  }

  function basePath(st) {
    return `/projects/${encodeURIComponent(st.projectId)}/assessments/${encodeURIComponent(st.assessmentId)}/checks/${encodeURIComponent(st.checkId)}/oast-correlations`;
  }

  function currentCorrelation(st) {
    return st.correlations.find(item => liveStatuses.has(String(item?.status || '')))
      || st.correlations[0]
      || null;
  }

  function replaceCorrelation(st, correlation) {
    const safe = safeCorrelation(correlation);
    if (!safe.id) throw new Error('The private OAST reservation response was incomplete.');
    st.correlations = [
      safe,
      ...st.correlations.filter(item => String(item?.id || '') !== safe.id),
    ];
    return safe;
  }

  function stopPolling(st) {
    if (st.pollTimer !== null) clearTimeout(st.pollTimer);
    st.pollTimer = null;
  }

  function shouldPoll(st, correlation) {
    if (ctx.canRunCommands?.() === false) return false;
    if (String(correlation?.status || '') === 'reserved') {
      return correlation?.provider_ready !== true;
    }
    return String(correlation?.status || '') === 'active';
  }

  function schedulePoll(st, correlationId) {
    stopPolling(st);
    const delay = document.visibilityState === 'hidden'
      ? hiddenPollDelayMs
      : visiblePollDelayMs;
    st.pollTimer = setTimeout(() => {
      st.pollTimer = null;
      void refreshCorrelation(st, correlationId);
    }, delay);
    st.pollTimer?.unref?.();
  }

  function logFailure(event, err, st, phase) {
    logAssessmentClientFailure(ctx, event, err, {
      phase,
      project_id: st.projectId,
      assessment_id: st.assessmentId,
      check_id: st.checkId,
      correlation_id: text(currentCorrelation(st)?.id),
    });
  }

  async function requestError(resp, fallback) {
    if (typeof ctx.projectResponseError === 'function') {
      return ctx.projectResponseError(resp, fallback);
    }
    const payload = await resp.json().catch(() => ({}));
    return responseError(payload, resp.status, fallback);
  }

  async function refreshCorrelation(st, correlationId, options = {}) {
    const id = text(correlationId);
    if (!id || ctx.canRunCommands?.() === false) return false;
    try {
      const resp = await ctx.projectWorkspaceRequest(
        `${basePath(st)}/${encodeURIComponent(id)}`,
        { cache: 'no-store' },
      );
      if (!resp.ok) throw await requestError(resp, 'Could not refresh this private OAST reservation.');
      const correlation = replaceCorrelation(st, (await resp.json())?.correlation);
      st.error = '';
      if (options.render !== false) renderViews();
      if (shouldPoll(st, correlation)) schedulePoll(st, correlation.id);
      else stopPolling(st);
      return true;
    } catch (err) {
      stopPolling(st);
      st.error = err?.message || 'Could not refresh this private OAST reservation.';
      logFailure('PROJECT_ASSESSMENT_CLIENT_OAST_STATUS_FAILED', err, st, 'oast_status');
      if (options.render !== false) renderViews();
      return false;
    }
  }

  async function loadHistory(projectId, assessmentId, checkId, options = {}) {
    const st = stateFor(projectId, assessmentId, checkId);
    if (st.loaded && options.force !== true) return true;
    if (st.loading && st.loadPromise) return st.loadPromise;
    st.loading = true;
    st.error = '';
    if (options.render !== false) renderViews();
    const promise = (async () => {
      try {
        const resp = await ctx.projectWorkspaceRequest(basePath(st), { cache: 'no-store' });
        if (!resp.ok) throw await requestError(resp, 'Could not recover private OAST reservations.');
        const payload = await resp.json();
        st.correlations = (Array.isArray(payload?.correlations) ? payload.correlations : [])
          .map(safeCorrelation)
          .filter(item => item.id);
        st.loaded = true;
        const correlation = currentCorrelation(st);
        if (correlation && shouldPoll(st, correlation)) schedulePoll(st, correlation.id);
        return true;
      } catch (err) {
        st.error = err?.message || 'Could not recover private OAST reservations.';
        logFailure('PROJECT_ASSESSMENT_CLIENT_OAST_HISTORY_FAILED', err, st, 'oast_history');
        return false;
      } finally {
        st.loading = false;
        st.loadPromise = null;
        if (options.render !== false) renderViews();
      }
    })();
    st.loadPromise = promise;
    return promise;
  }

  async function reviewedPlan(st, check, profiles, returnFocus) {
    const request = ctx.apiFetch || ctx.projectWorkspaceRequest;
    if (typeof request !== 'function' || typeof ctx.showConfirm !== 'function') {
      throw new Error('Private OAST plan confirmation is unavailable.');
    }
    let httpProfileId = '';
    if (ctx.canManageSecrets?.() !== false) {
      returnFocus?.removeAttribute('aria-busy');
      const profile = await chooseHttpProfile(ctx.showConfirm, profiles);
      if (profile.cancelled) return null;
      httpProfileId = profile.profileId;
      returnFocus?.setAttribute('aria-busy', 'true');
    }
    const actionPath = `${basePath(st).replace(/\/oast-correlations$/, '')}/recommended-action`;
    let evidence = null;
    let selectedPath = previewPath(actionPath, httpProfileId);
    let previewResp = await request(selectedPath, { cache: 'no-store' });
    let previewData = await previewResp.json().catch(() => ({}));
    if (!previewResp.ok) {
      throw responseError(previewData, previewResp.status, 'Could not load this private OAST action.');
    }
    let plan = previewData?.plan || {};
    if (plan.evidence_selection?.required && !plan.evidence_selection?.selected) {
      returnFocus?.removeAttribute('aria-busy');
      const selected = await chooseParameterEvidence(ctx.showConfirm, plan.evidence_selection);
      if (selected.cancelled) return null;
      evidence = selected.evidence;
      returnFocus?.setAttribute('aria-busy', 'true');
      if (evidence) {
        selectedPath = previewPath(actionPath, httpProfileId, evidence);
        previewResp = await request(selectedPath, { cache: 'no-store' });
        previewData = await previewResp.json().catch(() => ({}));
        if (!previewResp.ok) {
          throw responseError(previewData, previewResp.status, 'Could not load this private OAST action.');
        }
        plan = previewData?.plan || {};
      }
    }
    if (plan?.oast?.preparable !== true || !plan?.plan_digest) {
      throw new Error(text(plan?.unavailable_reason, 'Private OAST validation is unavailable.'));
    }
    if (!isPrivateOastCheck(check) || text(plan?.action?.key) !== privateOastActionKey) {
      throw new Error('The reviewed private OAST action no longer matches this check.');
    }
    return { evidence, httpProfileId, plan };
  }

  function confirmedPayload(reviewed) {
    return {
      confirmed: true,
      plan_digest: text(reviewed.plan?.plan_digest),
      ...(reviewed.httpProfileId ? { http_profile_id: reviewed.httpProfileId } : {}),
      ...(reviewed.evidence ? {
        source_run_id: text(reviewed.evidence.source_run_id),
        parameter_observation_id: text(reviewed.evidence.observation_id),
      } : {}),
    };
  }

  async function prepare(st, check, profiles, returnFocus) {
    let shouldRestoreFocus = true;
    try {
      returnFocus?.setAttribute('aria-busy', 'true');
      st.mutating = 'planning';
      st.error = '';
      renderViews();
      const reviewed = await reviewedPlan(st, check, profiles, returnFocus);
      if (!reviewed) return false;
      st.mutating = '';
      returnFocus?.removeAttribute('aria-busy');
      renderViews();
      const choice = await ctx.showConfirm({
        body: {
          text: 'Prepare this private blind-XSS callback?',
          note: 'This reserves one short-lived app-owned callback for the reviewed check. The scan does not start until the private worker makes it ready and you confirm the redacted plan again.',
        },
        content: oastPlanContent(reviewed.plan),
        tone: 'warning',
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'prepare', label: 'Prepare private callback', role: 'primary' },
        ],
        refocusOnResolve: false,
      });
      if (choice !== 'prepare') return false;
      returnFocus?.setAttribute('aria-busy', 'true');
      st.mutating = 'reserving';
      renderViews();
      const resp = await ctx.projectWorkspaceRequest(basePath(st), {
        method: 'POST',
        body: JSON.stringify(confirmedPayload(reviewed)),
      });
      if (!resp.ok) throw await requestError(resp, 'Could not prepare this private OAST callback.');
      const correlation = replaceCorrelation(st, (await resp.json())?.correlation);
      st.loaded = true;
      st.error = '';
      ctx.setProjectWorkspaceMessage?.('Private callback reserved. The worker is preparing it for this assessment check.');
      if (shouldPoll(st, correlation)) schedulePoll(st, correlation.id);
      return true;
    } catch (err) {
      st.error = err?.message || 'Could not prepare this private OAST callback.';
      ctx.setProjectWorkspaceMessage?.(st.error, { error: true });
      logFailure('PROJECT_ASSESSMENT_CLIENT_OAST_PREPARE_FAILED', err, st, 'oast_prepare');
      return false;
    } finally {
      st.mutating = '';
      returnFocus?.removeAttribute('aria-busy');
      renderViews();
      if (shouldRestoreFocus) restoreFocus(returnFocus);
    }
  }

  async function reviewAndLaunch(st, check, profiles, correlation, returnFocus) {
    const attach = ctx.attachActiveRunFromMonitor || importedAttachActiveRunFromMonitor;
    let shouldRestoreFocus = true;
    try {
      returnFocus?.setAttribute('aria-busy', 'true');
      st.mutating = 'checking';
      renderViews();
      if (!correlation.provider_ready) {
        const refreshed = await refreshCorrelation(st, correlation.id, { render: false });
        correlation = currentCorrelation(st);
        if (!refreshed || !correlation?.provider_ready) {
          ctx.setProjectWorkspaceMessage?.('The private callback is still being prepared.');
          return false;
        }
      }
      st.mutating = 'planning';
      const reviewed = await reviewedPlan(st, check, profiles, returnFocus);
      if (!reviewed) return false;
      st.mutating = '';
      returnFocus?.removeAttribute('aria-busy');
      renderViews();
      const choice = await ctx.showConfirm({
        body: {
          text: 'Start this private blind-XSS run?',
          note: 'The ready callback stays private. This starts the bounded Dalfox run against the one reviewed URL and selected saved query parameter; accepted interactions attach the source run as assessment evidence and require human review.',
        },
        content: oastPlanContent(reviewed.plan),
        tone: 'warning',
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'run', label: 'Start blind-XSS run', role: 'primary' },
        ],
        refocusOnResolve: false,
      });
      if (choice !== 'run') return false;
      returnFocus?.setAttribute('aria-busy', 'true');
      st.mutating = 'launching';
      renderViews();
      const resp = await ctx.projectWorkspaceRequest(
        `${basePath(st)}/${encodeURIComponent(correlation.id)}/launch`,
        {
          method: 'POST',
          body: JSON.stringify(confirmedPayload(reviewed)),
        },
      );
      if (!resp.ok) throw await requestError(resp, 'Could not start this private OAST run.');
      const payload = await resp.json();
      const run = payload?.run;
      if (!run?.run_id) throw new Error('The private OAST run started without a run identifier.');
      replaceCorrelation(st, {
        ...correlation,
        status: 'active',
        run_id: run.run_id,
        provider_ready: true,
      });
      if (typeof attach !== 'function') {
        throw new Error('The run started, but the terminal handoff is unavailable. Open it from History.');
      }
      const attached = await attach(run);
      if (!attached) {
        throw new Error('The run started, but it could not open in a terminal. Open it from History.');
      }
      schedulePoll(st, correlation.id);
      ctx.closeProjectWorkspace?.({ refocus: false });
      shouldRestoreFocus = false;
      return true;
    } catch (err) {
      st.error = err?.message || 'Could not start this private OAST run.';
      ctx.setProjectWorkspaceMessage?.(st.error, { error: true });
      logFailure('PROJECT_ASSESSMENT_CLIENT_OAST_LAUNCH_FAILED', err, st, 'oast_launch');
      return false;
    } finally {
      st.mutating = '';
      returnFocus?.removeAttribute('aria-busy');
      renderViews();
      if (shouldRestoreFocus) restoreFocus(returnFocus);
    }
  }

  async function open(projectId, detail, check, profiles, returnFocus = null) {
    const assessmentId = text(detail?.assessment?.id || check?.assessment_id);
    const checkId = text(check?.id);
    if (!projectId || !assessmentId || !checkId || !isPrivateOastCheck(check)) return false;
    if (ctx.canRunCommands?.() === false) {
      ctx.setProjectWorkspaceMessage?.(
        "View-only team members can't prepare or start private OAST runs. Switch to Personal or ask for operator access.",
        { error: true },
      );
      restoreFocus(returnFocus);
      return false;
    }
    const st = stateFor(projectId, assessmentId, checkId);
    returnFocus?.setAttribute('aria-busy', 'true');
    const loaded = await loadHistory(projectId, assessmentId, checkId, { render: false });
    returnFocus?.removeAttribute('aria-busy');
    renderViews();
    if (!loaded) {
      restoreFocus(returnFocus);
      return false;
    }
    const correlation = currentCorrelation(st);
    if (correlation?.status === 'active') {
      return openRunDetails(st, correlation, returnFocus);
    }
    if (correlation?.status === 'reserved') {
      return reviewAndLaunch(st, check, profiles, correlation, returnFocus);
    }
    if (detail?.assessment?.status !== 'active') {
      ctx.setProjectWorkspaceMessage?.('New private OAST callbacks require an active assessment cycle.', { error: true });
      restoreFocus(returnFocus);
      return false;
    }
    return prepare(st, check, profiles, returnFocus);
  }

  async function startNew(projectId, detail, check, profiles, returnFocus = null) {
    const st = stateFor(projectId, detail?.assessment?.id, check?.id);
    return prepare(st, check, profiles, returnFocus);
  }

  async function refresh(projectId, assessmentId, checkId, correlationId, returnFocus = null) {
    const st = stateFor(projectId, assessmentId, checkId);
    returnFocus?.setAttribute('aria-busy', 'true');
    const refreshed = await refreshCorrelation(st, correlationId);
    returnFocus?.removeAttribute('aria-busy');
    restoreFocus(returnFocus);
    return refreshed;
  }

  function openRunDetails(st, correlation, returnFocus = null) {
    const runId = text(correlation?.run_id);
    const openDetails = ctx.openHistoryRunDetails;
    if (!runId || typeof openDetails !== 'function') {
      ctx.setProjectWorkspaceMessage?.('Run Details is unavailable. Open this run from History.', { error: true });
      restoreFocus(returnFocus);
      return false;
    }
    ctx.closeProjectWorkspace?.({ refocus: false });
    openDetails({ id: runId });
    return true;
  }

  function invalidate(projectId = '') {
    const id = text(projectId);
    [...states.entries()].forEach(([key, st]) => {
      if (id && st.projectId !== id) return;
      stopPolling(st);
      states.delete(key);
    });
  }

  return {
    currentCorrelation,
    invalidate,
    loadHistory,
    open,
    openRunDetails,
    refresh,
    retryableStatuses,
    startNew,
    stateFor,
  };
}

export {
  createProjectAssessmentOastManager,
  hiddenPollDelayMs,
  isPrivateOastCheck,
  liveStatuses,
  privateOastActionKey,
  retryableStatuses,
  safeCorrelation,
  visiblePollDelayMs,
};
