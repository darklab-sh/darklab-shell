// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Guarded preview, confirmation, and terminal handoff for Assessment actions.

import { attachActiveRunFromMonitor as importedAttachActiveRunFromMonitor } from '../../runner_bridge.js';

function text(value, fallback = '') {
  const normalized = String(value || '').trim();
  return normalized || fallback;
}

function responseError(payload, status, fallback) {
  return new Error(text(payload?.error, status ? `HTTP ${status}` : fallback));
}

function restoreFocus(target) {
  if (!target?.isConnected || target.disabled || typeof target.focus !== 'function') return;
  try {
    target.focus({ preventScroll: true });
  } catch (_) {
    target.focus();
  }
}

function planContent(plan) {
  const wrap = document.createElement('div');
  wrap.className = 'finding-verification-plan project-assessment-action-plan';
  const rows = [
    ['Command', plan.display_command],
    ['Target', `${text(plan.target?.type)} · ${text(plan.target?.value)}`],
    ...(plan.artifact_selection ? [
      ['OpenAPI schema', text(plan.artifact_selection?.selected?.name, 'None')],
      ['Read operations', plan.artifact_selection?.selected?.operation_count || 'None'],
    ] : []),
    ...(plan.nuclei_profile ? [
      ['Nuclei profile', text(plan.nuclei_profile.label)],
      ['Template source', text(plan.nuclei_profile.template_source).replaceAll('_', ' ')],
      ['Template families', (plan.nuclei_profile.template_families || []).join(', ')],
      ['Excluded templates', [
        ...(plan.nuclei_profile.excluded_tags || []),
        ...(plan.nuclei_profile.excluded_protocols || []),
      ].join(', ')],
      ['Template updates', plan.nuclei_profile.update_policy === 'explicit_only'
        ? 'Explicit action only'
        : text(plan.nuclei_profile.update_policy)],
    ] : []),
    ['HTTP profile', text(plan.http_profile?.name, 'None')],
    ['Profile role', text(plan.http_profile?.role, 'Anonymous')],
    ['Policy', text(plan.policy_level)],
    ['Scope', `${Number(plan.scope?.target_count || 1)} Project target · fan-out ${Number(plan.scope?.fan_out || 1)}`],
    ['Bounds', text(plan.bounds?.summary, 'One approved Project target')],
    ['Credentials', Array.isArray(plan.http_profile?.credential_use)
      ? plan.http_profile.credential_use.map(value => String(value).replaceAll('_', ' ')).join(', ')
      : text(plan.bounds?.credential_use, 'none')],
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

function profileIssue(profile) {
  if (profile?.enabled === false) return 'disabled';
  if (profile?.protected_references_visible === false) return 'permission required';
  const unavailableHeader = (Array.isArray(profile?.headers) ? profile.headers : [])
    .some(header => header?.available === false);
  const unavailableSecret = Object.values(profile?.secret_refs || {})
    .some(reference => reference && typeof reference === 'object' && reference.available === false);
  if (unavailableHeader || unavailableSecret) return 'missing Secret';
  return '';
}

function supportsHttpProfile(check) {
  const [kind, actionId] = String(check?.recommended_action_key || '').split(':', 2);
  return kind === 'command' && ['curl', 'httpx', 'katana', 'nuclei', 'dalfox', 'sqlmap'].includes(actionId);
}

async function chooseHttpProfile(confirm, profiles) {
  const candidates = Array.isArray(profiles) ? profiles : [];
  if (!candidates.length) return { cancelled: false, profileId: '' };
  const content = document.createElement('label');
  content.className = 'project-assessment-action-profile-field';
  const label = document.createElement('span');
  label.textContent = 'HTTP profile';
  const select = document.createElement('select');
  select.className = 'form-select';
  select.setAttribute('aria-label', 'HTTP profile for assessment run');
  const anonymous = document.createElement('option');
  anonymous.value = '';
  anonymous.textContent = 'No profile — unauthenticated';
  select.appendChild(anonymous);
  candidates.forEach((profile) => {
    const option = document.createElement('option');
    const issue = profileIssue(profile);
    option.value = String(profile?.id || '');
    option.textContent = `${text(profile?.name, 'HTTP profile')} · ${text(profile?.role, 'anonymous')}${issue ? ` · ${issue}` : ''}`;
    option.disabled = Boolean(issue);
    select.appendChild(option);
  });
  content.append(label, select);
  const choice = await confirm({
    body: {
      text: 'Choose the web role for this run.',
      note: 'The next screen shows the exact redacted plan. Secret values are never placed in the visible command.',
    },
    content,
    actions: [
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      { id: 'continue', label: 'Review run', role: 'primary' },
    ],
    defaultFocus: select,
    refocusOnResolve: false,
  });
  return { cancelled: choice !== 'continue', profileId: select.value };
}

async function chooseParameterEvidence(confirm, selection) {
  const candidates = Array.isArray(selection?.options) ? selection.options : [];
  if (!candidates.length) return { cancelled: false, evidence: null };
  const content = document.createElement('label');
  content.className = 'project-assessment-action-profile-field';
  const label = document.createElement('span');
  label.textContent = 'Saved parameter evidence';
  const select = document.createElement('select');
  select.className = 'form-select';
  select.setAttribute('aria-label', 'Saved parameter evidence for XSS validation');
  candidates.forEach((item, index) => {
    const option = document.createElement('option');
    option.value = String(index);
    option.textContent = `${text(item?.parameter, 'parameter')} · ${text(item?.location, 'location')} · ${text(item?.tool_version, 'Dalfox')}`;
    select.appendChild(option);
  });
  content.append(label, select);
  const choice = await confirm({
    body: {
      text: 'Choose the saved parameter to validate.',
      note: 'Only the selected query parameter is used. The next screen shows the exact bounded command before anything runs.',
    },
    content,
    actions: [
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      { id: 'continue', label: 'Review run', role: 'primary' },
    ],
    defaultFocus: select,
    refocusOnResolve: false,
  });
  const evidence = candidates[Number(select.value) || 0] || null;
  return { cancelled: choice !== 'continue', evidence };
}

async function chooseOpenApiArtifact(confirm, selection) {
  const candidates = Array.isArray(selection?.options) ? selection.options : [];
  if (!candidates.length) return { cancelled: false, artifact: null };
  const content = document.createElement('label');
  content.className = 'project-assessment-action-profile-field';
  const label = document.createElement('span');
  label.textContent = 'Saved OpenAPI JSON';
  const select = document.createElement('select');
  select.className = 'form-select';
  select.setAttribute('aria-label', 'Saved OpenAPI JSON for API negative testing');
  candidates.forEach((item, index) => {
    const option = document.createElement('option');
    option.value = String(index);
    option.textContent = `${text(item?.name, 'OpenAPI JSON')} · ${Number(item?.byte_size || 0).toLocaleString()} bytes · ${text(item?.run_id, 'saved run')}`;
    select.appendChild(option);
  });
  content.append(label, select);
  const choice = await confirm({
    body: {
      text: 'Choose the saved API contract to test.',
      note: 'The file is read from this Project, checked against its recorded digest, and limited to in-scope GET and HEAD operations before the plan is shown.',
    },
    content,
    actions: [
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      { id: 'continue', label: 'Review run', role: 'primary' },
    ],
    defaultFocus: select,
    refocusOnResolve: false,
  });
  const artifact = candidates[Number(select.value) || 0] || null;
  return { cancelled: choice !== 'continue', artifact };
}

function previewPath(path, httpProfileId, evidence = null, schemaArtifactId = '') {
  const params = new URLSearchParams();
  if (httpProfileId) params.set('http_profile_id', httpProfileId);
  if (evidence?.source_run_id) params.set('source_run_id', evidence.source_run_id);
  if (evidence?.observation_id) {
    params.set('parameter_observation_id', evidence.observation_id);
  }
  if (schemaArtifactId) params.set('schema_artifact_id', schemaArtifactId);
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

async function launchAssessmentAction(context, options = {}) {
  const ctx = context || {};
  const projectId = text(options.projectId);
  const assessmentId = text(options.assessmentId);
  const checkId = text(options.check?.id);
  const trigger = options.returnFocus || null;
  const request = ctx.apiFetch;
  const confirm = ctx.showConfirm;
  const attach = ctx.attachActiveRunFromMonitor || importedAttachActiveRunFromMonitor;
  let shouldRestoreFocus = true;
  if (!projectId || !assessmentId || !checkId || typeof request !== 'function') return false;
  const path = `/projects/${encodeURIComponent(projectId)}/assessments/${encodeURIComponent(assessmentId)}/checks/${encodeURIComponent(checkId)}/recommended-action`;
  try {
    trigger?.setAttribute('aria-busy', 'true');
    let httpProfileId = '';
    if (supportsHttpProfile(options.check) && options.canManageSecrets !== false) {
      if (typeof confirm !== 'function') {
        throw new Error('Assessment launch confirmation is unavailable.');
      }
      trigger?.removeAttribute('aria-busy');
      const selected = await chooseHttpProfile(confirm, options.httpProfiles);
      if (selected.cancelled) return false;
      httpProfileId = selected.profileId;
      trigger?.setAttribute('aria-busy', 'true');
    }
    let evidence = null;
    let schemaArtifactId = '';
    let selectedPreviewPath = previewPath(path, httpProfileId);
    let previewResp = await request(selectedPreviewPath, { cache: 'no-store' });
    let previewData = await previewResp.json().catch(() => ({}));
    if (!previewResp.ok) {
      throw responseError(previewData, previewResp.status, 'Could not load this assessment action.');
    }
    let plan = previewData?.plan || {};
    if (plan.evidence_selection?.required && !plan.evidence_selection?.selected) {
      if (typeof confirm !== 'function') {
        throw new Error('Assessment launch confirmation is unavailable.');
      }
      trigger?.removeAttribute('aria-busy');
      const selected = await chooseParameterEvidence(confirm, plan.evidence_selection);
      if (selected.cancelled) return false;
      evidence = selected.evidence;
      if (evidence) {
        trigger?.setAttribute('aria-busy', 'true');
        selectedPreviewPath = previewPath(path, httpProfileId, evidence);
        previewResp = await request(selectedPreviewPath, { cache: 'no-store' });
        previewData = await previewResp.json().catch(() => ({}));
        if (!previewResp.ok) {
          throw responseError(previewData, previewResp.status, 'Could not load this assessment action.');
        }
        plan = previewData?.plan || {};
      }
    }
    if (plan.artifact_selection?.required && !plan.artifact_selection?.selected) {
      if (typeof confirm !== 'function') {
        throw new Error('Assessment launch confirmation is unavailable.');
      }
      trigger?.removeAttribute('aria-busy');
      const selected = await chooseOpenApiArtifact(confirm, plan.artifact_selection);
      if (selected.cancelled) return false;
      schemaArtifactId = text(selected.artifact?.artifact_id);
      if (schemaArtifactId) {
        trigger?.setAttribute('aria-busy', 'true');
        selectedPreviewPath = previewPath(path, httpProfileId, evidence, schemaArtifactId);
        previewResp = await request(selectedPreviewPath, { cache: 'no-store' });
        previewData = await previewResp.json().catch(() => ({}));
        if (!previewResp.ok) {
          throw responseError(previewData, previewResp.status, 'Could not load this assessment action.');
        }
        plan = previewData?.plan || {};
      }
    }
    if (!plan.launchable) {
      ctx.setProjectWorkspaceMessage?.(
        text(plan.unavailable_reason, 'This assessment action is unavailable.'),
        { error: true },
      );
      return false;
    }
    if (typeof confirm !== 'function') {
      throw new Error('Assessment launch confirmation is unavailable.');
    }
    trigger?.removeAttribute('aria-busy');
    const choice = await confirm({
      body: {
        text: `Start ${text(plan.action?.id, 'this assessment action')}?`,
        note: 'The run will be linked to this Project. Compatible saved output can update this check. Reviewed validators may also create linked findings; no run closes findings automatically.',
      },
      content: planContent(plan),
      tone: ['standard', 'intrusive'].includes(plan.policy_level) ? 'warning' : null,
      actions: [
        { id: 'cancel', label: 'Cancel', role: 'cancel' },
        { id: 'run', label: 'Start run', role: 'primary' },
      ],
      refocusOnResolve: false,
    });
    if (choice !== 'run') return false;
    trigger?.setAttribute('aria-busy', 'true');
    const launchResp = await request(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        confirmed: true,
        plan_digest: text(plan.plan_digest),
        ...(httpProfileId ? { http_profile_id: httpProfileId } : {}),
        ...(schemaArtifactId ? { schema_artifact_id: schemaArtifactId } : {}),
        ...(evidence ? {
          source_run_id: text(evidence.source_run_id),
          parameter_observation_id: text(evidence.observation_id),
        } : {}),
      }),
    });
    const launchData = await launchResp.json().catch(() => ({}));
    if (!launchResp.ok) {
      throw responseError(launchData, launchResp.status, 'Could not start this assessment action.');
    }
    const run = launchData?.run;
    if (!run?.run_id) throw new Error('The assessment run started without a run identifier.');
    if (typeof attach !== 'function') {
      throw new Error('The run started, but the terminal handoff is unavailable. Open it from History.');
    }
    const attached = await attach(run);
    if (!attached) {
      throw new Error('The run started, but it could not open in a terminal. Open it from History.');
    }
    ctx.closeProjectWorkspace?.({ refocus: false });
    shouldRestoreFocus = false;
    return true;
  } catch (err) {
    ctx.setProjectWorkspaceMessage?.(
      err?.message || 'Could not start this assessment action.',
      { error: true },
    );
    ctx.logClientError?.('PROJECT_ASSESSMENT_CLIENT_ACTION_LAUNCH_FAILED', err, {
      page: 'project_assessment',
      project_id: projectId,
      assessment_id: assessmentId,
      assessment_check_id: checkId,
    });
    return false;
  } finally {
    trigger?.removeAttribute('aria-busy');
    if (shouldRestoreFocus) restoreFocus(trigger);
  }
}

export { launchAssessmentAction };
