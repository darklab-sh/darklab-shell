// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Reviewed ZAP setup, durable job recovery, and result handoff for Assessment.

import { logAssessmentClientFailure } from './project_assessment_client_log.js';

const activeStatuses = new Set([
  'queued',
  'submitting',
  'running',
  'cancel_requested',
  'downloading',
]);

const resultStatuses = new Set(['ready', 'imported']);
const pollDelayMs = 2000;

function text(value, fallback = '') {
  const normalized = String(value || '').trim();
  return normalized || fallback;
}

function restoreFocus(target) {
  if (!target?.isConnected || target.disabled || typeof target.focus !== 'function') return;
  try {
    target.focus({ preventScroll: true });
  } catch (_) {
    target.focus();
  }
}

function profileProtectedCount(profile) {
  const counts = profile?.reference_counts || {};
  return ['secret_refs', 'file_refs', 'headers', 'capture_rules']
    .reduce((total, key) => total + Math.max(0, Number(counts?.[key] || 0)), 0);
}

function zapProfileIssue(profile) {
  if (!profile || profile.enabled === false) return 'Disabled';
  if (text(profile.role, 'anonymous').toLowerCase() !== 'anonymous') {
    return 'Only anonymous profiles are supported';
  }
  if (
    profileProtectedCount(profile) > 0
    || (Array.isArray(profile.credential_use) && profile.credential_use.length > 0)
    || profile.proxy_configured
    || profile.proxy_url
    || profile.login_workflow_id
    || Number(profile.capture_rule_count || 0) > 0
    || (Array.isArray(profile.token_capture_rules) && profile.token_capture_rules.length > 0)
  ) {
    return 'Credentials and protected references are not supported yet';
  }
  return '';
}

function makeElement(tag, className = '', content = '') {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (content !== '') element.textContent = String(content);
  return element;
}

function targetChoices(detail, currentCheck) {
  const rows = Array.isArray(detail?.checks?.checks) ? detail.checks.checks : [];
  const choices = new Map();
  [...rows, currentCheck].forEach((check) => {
    const id = text(check?.target_entity_id);
    if (id && check?.target_type === 'url' && !choices.has(id)) {
      choices.set(id, {
        id,
        value: text(check?.target_value, id),
      });
    }
  });
  return [...choices.values()];
}

function setupContent(detail, check, profiles) {
  const content = makeElement('div', 'project-assessment-zap-setup');
  const profileField = makeElement('label', 'project-assessment-zap-field');
  profileField.appendChild(makeElement('span', '', 'Anonymous HTTP profile'));
  const profileSelect = makeElement('select', 'form-select');
  profileSelect.setAttribute('aria-label', 'HTTP profile for ZAP scan');
  const candidates = Array.isArray(profiles) ? profiles : [];
  candidates.forEach((profile) => {
    const option = document.createElement('option');
    const issue = zapProfileIssue(profile);
    option.value = text(profile?.id);
    option.disabled = Boolean(issue);
    option.textContent = [
      text(profile?.name, 'HTTP profile'),
      issue || 'Ready for ZAP',
    ].join(' · ');
    profileSelect.appendChild(option);
  });
  const supported = candidates.find(profile => !zapProfileIssue(profile));
  profileSelect.value = text(supported?.id);
  profileField.appendChild(profileSelect);
  content.appendChild(profileField);

  const choices = targetChoices(detail, check);
  const targetGroup = makeElement('fieldset', 'project-assessment-zap-targets nice-scroll');
  targetGroup.appendChild(makeElement('legend', '', 'Project URL targets'));
  choices.forEach((target) => {
    const label = makeElement('label', 'project-assessment-zap-target');
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.value = target.id;
    input.checked = target.id === text(check?.target_entity_id);
    label.append(input, makeElement('span', '', target.value));
    targetGroup.appendChild(label);
  });
  content.appendChild(targetGroup);

  const policyField = makeElement('label', 'project-assessment-zap-field');
  policyField.appendChild(makeElement('span', '', 'Scan policy'));
  const policySelect = makeElement('select', 'form-select');
  policySelect.setAttribute('aria-label', 'ZAP scan policy');
  [['safe', 'Safe · crawl and passive scan'], ['intrusive', 'Intrusive · bounded active scan']]
    .forEach(([value, label]) => {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = label;
      policySelect.appendChild(option);
    });
  policyField.appendChild(policySelect);
  content.appendChild(policyField);

  const exclusionsField = makeElement('label', 'project-assessment-zap-field');
  exclusionsField.appendChild(makeElement('span', '', 'Extra path exclusions'));
  const exclusions = makeElement('textarea', 'form-textarea');
  exclusions.rows = 4;
  exclusions.placeholder = '/logout\n/app/private';
  exclusions.setAttribute('aria-label', 'Extra ZAP path exclusions');
  exclusionsField.append(
    exclusions,
    makeElement('small', '', 'Optional. Enter one absolute path prefix per line.'),
  );
  content.appendChild(exclusionsField);

  const error = makeElement('div', 'project-assessment-zap-form-error');
  error.setAttribute('role', 'alert');
  content.appendChild(error);
  return {
    content,
    error,
    exclusions,
    profileSelect,
    policySelect,
    targetInputs: [...targetGroup.querySelectorAll('input[type="checkbox"]')],
  };
}

function selectionFromSetup(setup) {
  return {
    http_profile_id: text(setup.profileSelect.value),
    policy_level: text(setup.policySelect.value, 'safe'),
    scope_exclusions: setup.exclusions.value
      .split('\n')
      .map(value => value.trim())
      .filter(Boolean),
    target_entity_ids: setup.targetInputs
      .filter(input => input.checked)
      .map(input => input.value),
  };
}

function validateSelection(selection) {
  if (!selection.http_profile_id) return 'Select an anonymous HTTP profile that is ready for ZAP.';
  if (selection.target_entity_ids.length < 1 || selection.target_entity_ids.length > 8) {
    return 'Select between one and eight Project URL targets.';
  }
  if (selection.scope_exclusions.length > 50) return 'Use no more than 50 path exclusions.';
  return '';
}

function planContent(plan) {
  const content = makeElement('div', 'project-assessment-zap-plan');
  const summary = plan?.summary || {};
  const rows = [
    ['Policy', text(summary.policy_level, 'safe')],
    ['Authentication role', text(summary.authentication_role, 'anonymous')],
    ['Targets', `${Number(summary.targets?.length || 0)} Project URL${summary.targets?.length === 1 ? '' : 's'}`],
    ['Included scope rules', Number(summary.include_rule_count || 0)],
    ['Excluded scope rules', Number(summary.exclusion_rule_count || 0)],
    ['Jobs', (Array.isArray(summary.job_types) ? summary.job_types : []).join(', ')],
    ['Time limit', `${Number(summary.job_timeout_seconds || 0)} seconds`],
    ['Report', text(summary.report_file, 'ZAP JSON')],
  ];
  rows.forEach(([labelText, valueText]) => {
    const row = makeElement('div', 'finding-verification-plan-row');
    row.append(
      makeElement('span', 'finding-verification-plan-label', labelText),
      makeElement('span', 'finding-verification-plan-value', valueText),
    );
    content.appendChild(row);
  });
  const targets = makeElement('div', 'project-assessment-zap-plan-targets');
  targets.appendChild(makeElement('strong', '', 'Reviewed targets'));
  const targetList = makeElement('ul');
  (Array.isArray(summary.targets) ? summary.targets : []).forEach((target) => {
    targetList.appendChild(makeElement('li', '', target));
  });
  targets.appendChild(targetList);
  content.appendChild(targets);
  content.append(
    makeElement('strong', 'project-assessment-zap-plan-heading', 'Exact non-secret Automation Framework plan'),
    makeElement('pre', 'project-assessment-zap-yaml nice-scroll', text(plan?.plan_yaml)),
  );
  return content;
}

function createProjectAssessmentZapManager(context, hooks = {}) {
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
        jobs: [],
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

  function logFailure(event, err, st, phase, details = {}) {
    logAssessmentClientFailure(ctx, event, err, {
      phase,
      project_id: st.projectId,
      assessment_id: st.assessmentId,
      check_id: st.checkId,
      job_id: text(details.job_id),
    });
  }

  async function responseError(resp, fallback) {
    if (typeof ctx.projectResponseError === 'function') return ctx.projectResponseError(resp, fallback);
    return new Error(fallback);
  }

  function basePath(st) {
    return `/projects/${encodeURIComponent(st.projectId)}/assessments/${encodeURIComponent(st.assessmentId)}/checks/${encodeURIComponent(st.checkId)}`;
  }

  function latestJob(st) {
    return st.jobs[0] || null;
  }

  function stopPolling(st) {
    if (st.pollTimer !== null) clearTimeout(st.pollTimer);
    st.pollTimer = null;
  }

  async function refreshJob(st, jobId) {
    try {
      const resp = await ctx.projectWorkspaceRequest(
        `${basePath(st)}/zap-jobs/${encodeURIComponent(jobId)}`,
        { cache: 'no-store' },
      );
      if (!resp.ok) throw await responseError(resp, 'Could not refresh this ZAP job.');
      const job = (await resp.json())?.job || null;
      if (!job?.id) throw new Error('The ZAP job response was incomplete.');
      st.jobs = [job, ...st.jobs.filter(item => String(item?.id || '') !== String(job.id))];
      st.error = '';
      renderViews();
      if (activeStatuses.has(String(job.status || ''))) schedulePoll(st, job.id);
      else stopPolling(st);
      return true;
    } catch (err) {
      stopPolling(st);
      st.error = err?.message || 'Could not refresh this ZAP job.';
      logFailure(
        'PROJECT_ASSESSMENT_CLIENT_ZAP_JOB_REFRESH_FAILED',
        err,
        st,
        'zap_job_refresh',
        { job_id: jobId },
      );
      renderViews();
      return false;
    }
  }

  function schedulePoll(st, jobId) {
    stopPolling(st);
    st.pollTimer = setTimeout(() => {
      st.pollTimer = null;
      void refreshJob(st, jobId);
    }, pollDelayMs);
    st.pollTimer?.unref?.();
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
        const resp = await ctx.projectWorkspaceRequest(`${basePath(st)}/zap-jobs`, { cache: 'no-store' });
        if (!resp.ok) throw await responseError(resp, 'Could not load ZAP job history.');
        const payload = await resp.json();
        st.jobs = Array.isArray(payload?.jobs) ? payload.jobs : [];
        st.loaded = true;
        const job = latestJob(st);
        if (job && activeStatuses.has(String(job.status || ''))) schedulePoll(st, job.id);
        return true;
      } catch (err) {
        st.error = err?.message || 'Could not load ZAP job history.';
        logFailure('PROJECT_ASSESSMENT_CLIENT_ZAP_JOB_HISTORY_FAILED', err, st, 'zap_job_history');
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

  async function chooseSetup(detail, check, profiles) {
    if (typeof ctx.showConfirm !== 'function') {
      throw new Error('ZAP plan confirmation is unavailable.');
    }
    const setup = setupContent(detail, check, profiles);
    const hasSupportedProfile = Boolean(setup.profileSelect.value);
    const actions = [{ id: 'cancel', label: 'Cancel', role: 'cancel' }];
    if (hasSupportedProfile) {
      actions.push({
        id: 'review',
        label: 'Review exact plan',
        role: 'primary',
        onActivate: () => {
          const message = validateSelection(selectionFromSetup(setup));
          setup.error.textContent = message;
          return !message;
        },
      });
    }
    const choice = await ctx.showConfirm({
      body: {
        text: 'Set up an external ZAP scan.',
        note: hasSupportedProfile
          ? 'Nothing is submitted yet. The next screen shows the exact non-secret plan and requires a fresh confirmation.'
          : 'Create or enable an anonymous HTTP profile without credentials or protected references before using ZAP.',
      },
      content: setup.content,
      actions,
      defaultFocus: hasSupportedProfile ? setup.profileSelect : 'cancel',
      refocusOnResolve: false,
    });
    const selection = selectionFromSetup(setup);
    const message = validateSelection(selection);
    if (choice !== 'review' || message) return null;
    return selection;
  }

  async function reviewAndQueue(st, detail, check, profiles, returnFocus) {
    if (ctx.canRunCommands?.() === false) {
      ctx.setProjectWorkspaceMessage?.(
        "View-only team members can't start ZAP scans. Switch to Personal or ask for operator access.",
        { error: true },
      );
      restoreFocus(returnFocus);
      return false;
    }
    let shouldRestoreFocus = true;
    try {
      const selection = await chooseSetup(detail, check, profiles);
      if (!selection) return false;
      returnFocus?.setAttribute('aria-busy', 'true');
      st.mutating = 'planning';
      st.error = '';
      renderViews();
      const planResp = await ctx.projectWorkspaceRequest(`${basePath(st)}/zap-plan`, {
        method: 'POST',
        body: JSON.stringify(selection),
      });
      if (!planResp.ok) throw await responseError(planResp, 'Could not review this ZAP plan.');
      const plan = (await planResp.json())?.plan || null;
      if (!plan?.plan_digest || !plan?.plan_yaml) throw new Error('The reviewed ZAP plan was incomplete.');
      st.mutating = '';
      returnFocus?.removeAttribute('aria-busy');
      renderViews();
      const intrusive = plan?.summary?.policy_level === 'intrusive';
      const choice = await ctx.showConfirm({
        body: {
          text: intrusive ? 'Queue this intrusive ZAP scan?' : 'Queue this ZAP scan?',
          note: intrusive
            ? 'This starts a bounded active scan against the reviewed Project URLs. Review every target and plan line before continuing.'
            : 'The worker will crawl and passively scan only the reviewed Project URLs. Findings stay in an Atlas draft until someone reviews and applies it.',
        },
        content: planContent(plan),
        tone: intrusive ? 'warning' : null,
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'queue', label: intrusive ? 'Queue intrusive scan' : 'Queue ZAP scan', role: 'primary' },
        ],
        refocusOnResolve: false,
      });
      if (choice !== 'queue') return false;
      returnFocus?.setAttribute('aria-busy', 'true');
      st.mutating = 'submitting';
      renderViews();
      const submitResp = await ctx.projectWorkspaceRequest(`${basePath(st)}/zap-jobs`, {
        method: 'POST',
        body: JSON.stringify({
          ...selection,
          confirmed: true,
          plan_digest: plan.plan_digest,
        }),
      });
      if (!submitResp.ok) throw await responseError(submitResp, 'Could not queue this ZAP scan.');
      const job = (await submitResp.json())?.job || null;
      if (!job?.id) throw new Error('The queued ZAP job response was incomplete.');
      st.jobs = [job, ...st.jobs.filter(item => String(item?.id || '') !== String(job.id))];
      st.loaded = true;
      ctx.setProjectWorkspaceMessage?.('ZAP scan queued. Progress will stay with this assessment check.');
      if (activeStatuses.has(String(job.status || ''))) schedulePoll(st, job.id);
      shouldRestoreFocus = false;
      return true;
    } catch (err) {
      st.error = err?.message || 'Could not start this ZAP scan.';
      ctx.setProjectWorkspaceMessage?.(st.error, { error: true });
      logFailure('PROJECT_ASSESSMENT_CLIENT_ZAP_PLAN_FAILED', err, st, 'zap_plan');
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
    if (!projectId || !assessmentId || !checkId || check?.target_type !== 'url') return false;
    const st = stateFor(projectId, assessmentId, checkId);
    returnFocus?.setAttribute('aria-busy', 'true');
    const loaded = await loadHistory(projectId, assessmentId, checkId, { render: false });
    returnFocus?.removeAttribute('aria-busy');
    renderViews();
    if (!loaded) {
      restoreFocus(returnFocus);
      return false;
    }
    const job = latestJob(st);
    if (job && (activeStatuses.has(String(job.status || '')) || resultStatuses.has(String(job.status || '')))) {
      restoreFocus(returnFocus);
      return true;
    }
    if (detail?.assessment?.status !== 'active') {
      ctx.setProjectWorkspaceMessage?.('New ZAP scans require an active assessment cycle.', { error: true });
      restoreFocus(returnFocus);
      return false;
    }
    return reviewAndQueue(st, detail, check, profiles, returnFocus);
  }

  async function startNew(projectId, detail, check, profiles, returnFocus = null) {
    const st = stateFor(projectId, detail?.assessment?.id, check?.id);
    return reviewAndQueue(st, detail, check, profiles, returnFocus);
  }

  async function cancel(projectId, assessmentId, checkId, job, returnFocus = null) {
    const st = stateFor(projectId, assessmentId, checkId);
    if (!job?.cancelable || ctx.canRunCommands?.() === false || st.mutating) return false;
    if (typeof ctx.showConfirm !== 'function') return false;
    const choice = await ctx.showConfirm({
      body: {
        text: 'Cancel this ZAP scan?',
        note: 'The worker will request remote cancellation and keep the final status with this assessment check.',
      },
      tone: 'warning',
      actions: [
        { id: 'keep', label: 'Keep running', role: 'cancel' },
        { id: 'cancel_zap', label: 'Cancel ZAP scan', tone: 'warning' },
      ],
      refocusOnResolve: false,
    });
    if (choice !== 'cancel_zap') {
      restoreFocus(returnFocus);
      return false;
    }
    st.mutating = 'canceling';
    renderViews();
    try {
      const resp = await ctx.projectWorkspaceRequest(
        `${basePath(st)}/zap-jobs/${encodeURIComponent(job.id)}`,
        { method: 'DELETE' },
      );
      if (!resp.ok) throw await responseError(resp, 'Could not cancel this ZAP scan.');
      const updated = (await resp.json())?.job || null;
      if (!updated?.id) throw new Error('The canceled ZAP job response was incomplete.');
      st.jobs = [updated, ...st.jobs.filter(item => String(item?.id || '') !== String(updated.id))];
      if (activeStatuses.has(String(updated.status || ''))) schedulePoll(st, updated.id);
      else stopPolling(st);
      ctx.setProjectWorkspaceMessage?.('ZAP cancellation requested.');
      return true;
    } catch (err) {
      st.error = err?.message || 'Could not cancel this ZAP scan.';
      ctx.setProjectWorkspaceMessage?.(st.error, { error: true });
      logFailure(
        'PROJECT_ASSESSMENT_CLIENT_ZAP_CANCEL_FAILED',
        err,
        st,
        'zap_cancel',
        { job_id: job?.id },
      );
      return false;
    } finally {
      st.mutating = '';
      renderViews();
      restoreFocus(returnFocus);
    }
  }

  async function openFiles(job) {
    if (!job?.files_path || typeof ctx.openWorkspace !== 'function') return false;
    try {
      await ctx.openWorkspace();
      return true;
    } catch (err) {
      ctx.setProjectWorkspaceMessage?.(err?.message || 'Could not open Files.', { error: true });
      logAssessmentClientFailure(ctx, 'PROJECT_ASSESSMENT_CLIENT_ZAP_FILES_OPEN_FAILED', err, {
        phase: 'zap_files_handoff',
        job_id: text(job?.id),
      });
      return false;
    }
  }

  async function openAtlas(projectId, projectName = '', job = null) {
    if (typeof ctx.openAtlas !== 'function') return false;
    try {
      const options = {
        projectId,
        projectName,
        tab: 'findings',
        source: 'project_assessment_zap',
      };
      if (job?.status === 'ready' && job?.atlas_draft_id) {
        options.importDraftId = String(job.atlas_draft_id);
      }
      await ctx.openAtlas(options);
      return true;
    } catch (err) {
      ctx.setProjectWorkspaceMessage?.(err?.message || 'Could not open Atlas.', { error: true });
      logAssessmentClientFailure(ctx, 'PROJECT_ASSESSMENT_CLIENT_ZAP_ATLAS_OPEN_FAILED', err, {
        phase: 'zap_atlas_handoff',
        project_id: text(projectId),
        job_id: text(job?.id),
      });
      return false;
    }
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
    cancel,
    invalidate,
    loadHistory,
    open,
    openAtlas,
    openFiles,
    startNew,
    stateFor,
  };
}

export {
  activeStatuses,
  createProjectAssessmentZapManager,
  resultStatuses,
  zapProfileIssue,
};
