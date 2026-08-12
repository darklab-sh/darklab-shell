// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Manual Assessment check decisions shared by desktop and mobile surfaces.

import { logAssessmentClientFailure } from './project_assessment_client_log.js';

const MANUAL_STATE_OPTIONS = [
  { value: 'blocked', label: 'Blocked' },
  { value: 'skipped', label: 'Intentionally skipped' },
  { value: 'not_applicable', label: 'Not applicable' },
];
const MAX_REASON_LENGTH = 1000;

function restoreFocus(target) {
  if (!target?.isConnected || target.disabled || typeof target.focus !== 'function') return;
  try {
    target.focus({ preventScroll: true });
  } catch (_) {
    target.focus();
  }
}

function manualStateEditor(check = {}) {
  const content = document.createElement('div');
  content.className = 'project-assessment-manual-state-editor';

  const stateField = document.createElement('label');
  stateField.className = 'project-assessment-manual-state-field';
  const stateLabel = document.createElement('span');
  stateLabel.textContent = 'Decision';
  const state = document.createElement('select');
  state.className = 'form-select';
  state.setAttribute('aria-label', 'Manual check decision');
  MANUAL_STATE_OPTIONS.forEach((item) => {
    const option = document.createElement('option');
    option.value = item.value;
    option.textContent = item.label;
    state.appendChild(option);
  });
  if (
    check?.state_source === 'manual'
    && MANUAL_STATE_OPTIONS.some(item => item.value === check?.state)
  ) {
    state.value = check.state;
  }
  stateField.append(stateLabel, state);

  const reasonField = document.createElement('label');
  reasonField.className = 'project-assessment-manual-state-field';
  const reasonLabel = document.createElement('span');
  reasonLabel.textContent = 'Reason';
  const reason = document.createElement('textarea');
  reason.className = 'form-control nice-scroll project-assessment-manual-state-reason';
  reason.maxLength = MAX_REASON_LENGTH;
  reason.required = true;
  reason.placeholder = 'Explain why this check is blocked, skipped, or not applicable.';
  reason.value = check?.state_source === 'manual' ? String(check?.state_reason || '') : '';
  reasonField.append(reasonLabel, reason);

  const error = document.createElement('p');
  error.className = 'project-assessment-manual-state-error';
  error.hidden = true;
  error.setAttribute('role', 'alert');

  content.append(stateField, reasonField, error);
  return { content, error, reason, state };
}

async function openAssessmentCheckStateEditor(context, options = {}) {
  const ctx = context || {};
  const projectId = String(options.projectId || '');
  const assessmentId = String(options.assessment?.id || options.check?.assessment_id || '');
  const checkId = String(options.check?.id || '');
  const manual = options.check?.state_source === 'manual';
  if (!projectId || !assessmentId || !checkId) return false;
  if (ctx.canMutateProjects?.() === false) {
    ctx.setProjectWorkspaceMessage?.(
      "View-only team members can't change assessment checks. Switch to Personal or ask for operator access.",
      { error: true },
    );
    return false;
  }
  if (options.assessment?.status !== 'active') {
    ctx.setProjectWorkspaceMessage?.('Completed and archived assessment checks are read-only.', { error: true });
    return false;
  }
  if (typeof ctx.showConfirm !== 'function') {
    const err = new Error('Assessment check decisions are unavailable.');
    ctx.setProjectWorkspaceMessage?.(err.message, { error: true });
    logAssessmentClientFailure(ctx, 'PROJECT_ASSESSMENT_CLIENT_CHECK_STATE_CONFIRM_UNAVAILABLE', err, {
      phase: 'check_state',
      project_id: projectId,
      assessment_id: assessmentId,
      check_id: checkId,
    });
    return false;
  }

  const editor = manualStateEditor(options.check);
  const path = `/projects/${encodeURIComponent(projectId)}/assessments/${encodeURIComponent(assessmentId)}/checks/${encodeURIComponent(checkId)}`;

  async function update(state, reason) {
    editor.error.hidden = true;
    try {
      const resp = await ctx.projectWorkspaceRequest(path, {
        method: 'PATCH',
        body: JSON.stringify({ state, reason }),
      });
      if (!resp.ok) {
        if (typeof ctx.projectResponseError === 'function') {
          throw await ctx.projectResponseError(resp, 'Could not save this assessment decision.');
        }
        throw new Error('Could not save this assessment decision.');
      }
      const payload = await resp.json();
      await options.onSaved?.(payload);
      return true;
    } catch (err) {
      editor.error.textContent = err?.message || 'Could not save this assessment decision.';
      editor.error.hidden = false;
      logAssessmentClientFailure(ctx, 'PROJECT_ASSESSMENT_CLIENT_CHECK_STATE_UPDATE_FAILED', err, {
        phase: 'check_state',
        project_id: projectId,
        assessment_id: assessmentId,
        check_id: checkId,
      });
      return false;
    }
  }

  const actions = [{ id: 'cancel', label: 'Cancel', role: 'cancel' }];
  if (manual) {
    actions.push({
      id: 'clear',
      label: 'Restore evidence-derived state',
      onActivate: () => update('not_started', ''),
    });
  }
  actions.push({
    id: 'save',
    label: 'Save decision',
    role: 'primary',
    onActivate: () => {
      const reason = String(editor.reason.value || '').trim();
      if (!reason) {
        editor.error.textContent = 'A reason is required for a manual decision.';
        editor.error.hidden = false;
        editor.reason.focus();
        return false;
      }
      return update(editor.state.value, reason);
    },
  });

  try {
    const choice = await ctx.showConfirm({
      body: {
        text: manual ? 'Edit this manual check decision' : 'Set a manual check decision',
        note: 'The decision applies only to this check in the active cycle. Restoring it uses the saved evidence to calculate the current state again.',
      },
      content: editor.content,
      actions,
      defaultFocus: editor.state,
      refocusOnResolve: false,
    });
    if (!['save', 'clear'].includes(choice)) restoreFocus(options.returnFocus);
    return ['save', 'clear'].includes(choice);
  } catch (err) {
    restoreFocus(options.returnFocus);
    ctx.setProjectWorkspaceMessage?.(
      err?.message || 'Could not open the assessment decision editor.',
      { error: true },
    );
    logAssessmentClientFailure(ctx, 'PROJECT_ASSESSMENT_CLIENT_CHECK_STATE_CONFIRM_FAILED', err, {
      phase: 'check_state',
      project_id: projectId,
      assessment_id: assessmentId,
      check_id: checkId,
    });
    return false;
  }
}

export { openAssessmentCheckStateEditor };
