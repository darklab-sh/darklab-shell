// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Manual Assessment evidence controls shared by desktop and mobile surfaces.

const MAX_EVIDENCE_ID_LENGTH = 512;
const EVIDENCE_TYPE_LABELS = {
  run: 'Saved run',
  workflow_execution: 'Workflow execution',
  finding: 'Finding',
  atlas_entity: 'Atlas entity',
  run_artifact: 'Run artifact',
  workspace_artifact: 'Workspace artifact',
  screenshot: 'Saved screenshot',
};

function restoreFocus(target) {
  if (!target?.isConnected || target.disabled || typeof target.focus !== 'function') return;
  try {
    target.focus({ preventScroll: true });
  } catch (_) {
    target.focus();
  }
}

function checkDefinition(detail, check) {
  const definitions = Array.isArray(detail?.assessment?.profile_snapshot?.checks)
    ? detail.assessment.profile_snapshot.checks
    : [];
  return definitions.find(item => String(item?.key || '') === String(check?.check_key || '')) || null;
}

function compatibleEvidenceTypes(detail, check) {
  const rules = Array.isArray(checkDefinition(detail, check)?.evidence_rules)
    ? checkDefinition(detail, check).evidence_rules
    : [];
  const accepted = new Set(rules.flatMap(rule => (
    Array.isArray(rule?.evidence_types) ? rule.evidence_types : []
  )).map(value => String(value || '')));
  return Object.keys(EVIDENCE_TYPE_LABELS).filter(value => accepted.has(value));
}

function manualEvidenceItems(check) {
  return Array.isArray(check?.manual_evidence?.evidence)
    ? check.manual_evidence.evidence.filter(item => item?.id)
    : [];
}

function evidenceEditor(detail, check) {
  const content = document.createElement('div');
  content.className = 'project-assessment-evidence-editor';
  const evidenceTypes = compatibleEvidenceTypes(detail, check);
  const existingItems = manualEvidenceItems(check);

  let existing = null;
  if (existingItems.length) {
    const field = document.createElement('label');
    field.className = 'project-assessment-evidence-field';
    const label = document.createElement('span');
    label.textContent = 'Existing manual link';
    existing = document.createElement('select');
    existing.className = 'form-select';
    existing.setAttribute('aria-label', 'Existing manual evidence link');
    existingItems.forEach((item) => {
      const option = document.createElement('option');
      option.value = String(item.id || '');
      const type = EVIDENCE_TYPE_LABELS[item.evidence_type] || item.evidence_type || 'Evidence';
      const state = item.source_state === 'unavailable' ? ' · unavailable' : '';
      option.textContent = `${type}: ${String(item.evidence_id || '')}${state}`;
      existing.appendChild(option);
    });
    field.append(label, existing);
    content.appendChild(field);
  }

  const typeField = document.createElement('label');
  typeField.className = 'project-assessment-evidence-field';
  const typeLabel = document.createElement('span');
  typeLabel.textContent = 'Saved evidence type';
  const evidenceType = document.createElement('select');
  evidenceType.className = 'form-select';
  evidenceType.setAttribute('aria-label', 'Saved evidence type');
  evidenceTypes.forEach((value) => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = EVIDENCE_TYPE_LABELS[value];
    evidenceType.appendChild(option);
  });
  evidenceType.disabled = evidenceTypes.length === 0;
  typeField.append(typeLabel, evidenceType);

  const idField = document.createElement('label');
  idField.className = 'project-assessment-evidence-field';
  const idLabel = document.createElement('span');
  idLabel.textContent = 'Saved evidence ID';
  const evidenceId = document.createElement('input');
  evidenceId.type = 'text';
  evidenceId.className = 'form-control';
  evidenceId.maxLength = MAX_EVIDENCE_ID_LENGTH;
  evidenceId.autocomplete = 'off';
  evidenceId.placeholder = 'Paste the ID from the saved run, finding, entity, or file.';
  evidenceId.disabled = evidenceTypes.length === 0;
  idField.append(idLabel, evidenceId);

  const guidance = document.createElement('small');
  guidance.className = 'project-assessment-evidence-guidance';
  guidance.textContent = evidenceTypes.length
    ? 'The saved item must belong to this Project and satisfy this check’s frozen evidence rules.'
    : 'This check doesn’t accept manually linked evidence.';

  if (check?.manual_evidence?.has_more) {
    const bounded = document.createElement('small');
    bounded.className = 'project-assessment-evidence-guidance';
    bounded.textContent = `Showing the newest ${existingItems.length} of ${Number(check.manual_evidence.total || existingItems.length)} manual links.`;
    content.append(typeField, idField, guidance, bounded);
  } else {
    content.append(typeField, idField, guidance);
  }

  const error = document.createElement('p');
  error.className = 'project-assessment-evidence-error';
  error.hidden = true;
  error.setAttribute('role', 'alert');
  content.appendChild(error);

  return { content, error, evidenceId, evidenceType, existing, evidenceTypes };
}

async function openAssessmentEvidenceEditor(context, options = {}) {
  const ctx = context || {};
  const projectId = String(options.projectId || '');
  const assessmentId = String(options.detail?.assessment?.id || options.check?.assessment_id || '');
  const checkId = String(options.check?.id || '');
  if (!projectId || !assessmentId || !checkId) return false;
  if (ctx.canMutateProjects?.() === false) {
    ctx.setProjectWorkspaceMessage?.(
      "View-only team members can't change assessment evidence. Switch to Personal or ask for operator access.",
      { error: true },
    );
    return false;
  }
  if (options.detail?.assessment?.status !== 'active') {
    ctx.setProjectWorkspaceMessage?.('Completed and archived assessment evidence is read-only.', { error: true });
    return false;
  }
  if (typeof ctx.showConfirm !== 'function') {
    const err = new Error('Assessment evidence controls are unavailable.');
    ctx.setProjectWorkspaceMessage?.(err.message, { error: true });
    ctx.logClientError?.('PROJECT_ASSESSMENT_CLIENT_EVIDENCE_CONFIRM_UNAVAILABLE', err, {
      page: 'project_assessment',
      phase: 'evidence',
      project_id: projectId,
      assessment_id: assessmentId,
      check_id: checkId,
    });
    return false;
  }

  const editor = evidenceEditor(options.detail, options.check);
  const path = `/projects/${encodeURIComponent(projectId)}/assessments/${encodeURIComponent(assessmentId)}/checks/${encodeURIComponent(checkId)}/evidence`;

  async function mutate(url, requestOptions, fallback, action) {
    editor.error.hidden = true;
    try {
      const resp = await ctx.projectWorkspaceRequest(url, requestOptions);
      if (!resp.ok) {
        if (typeof ctx.projectResponseError === 'function') {
          throw await ctx.projectResponseError(resp, fallback);
        }
        throw new Error(fallback);
      }
      const payload = await resp.json();
      await options.onSaved?.(payload, action);
      return true;
    } catch (err) {
      editor.error.textContent = err?.message || fallback;
      editor.error.hidden = false;
      ctx.logClientError?.('PROJECT_ASSESSMENT_CLIENT_EVIDENCE_UPDATE_FAILED', err, {
        page: 'project_assessment',
        phase: 'evidence',
        action,
        project_id: projectId,
        assessment_id: assessmentId,
        check_id: checkId,
      });
      return false;
    }
  }

  const actions = [{ id: 'cancel', label: 'Cancel', role: 'cancel' }];
  if (editor.existing) {
    actions.push({
      id: 'remove',
      label: 'Remove selected link',
      role: 'destructive',
      onActivate: () => {
        const linkId = String(editor.existing.value || '');
        if (!linkId) return false;
        return mutate(
          `${path}/${encodeURIComponent(linkId)}`,
          { method: 'DELETE' },
          'Could not remove this assessment evidence link.',
          'unlinked',
        );
      },
    });
  }
  if (editor.evidenceTypes.length) {
    actions.push({
      id: 'link',
      label: 'Link evidence',
      role: 'primary',
      onActivate: () => {
        const evidenceId = String(editor.evidenceId.value || '').trim();
        if (!evidenceId) {
          editor.error.textContent = 'A saved evidence ID is required.';
          editor.error.hidden = false;
          editor.evidenceId.focus();
          return false;
        }
        return mutate(
          path,
          {
            method: 'POST',
            body: JSON.stringify({
              evidence_type: editor.evidenceType.value,
              evidence_id: evidenceId,
            }),
          },
          'Could not link this saved evidence.',
          'linked',
        );
      },
    });
  }

  try {
    const choice = await ctx.showConfirm({
      body: {
        text: 'Manage linked evidence',
        note: 'Linking or removing a reference recalculates this check. Removing a link never deletes the saved run, finding, entity, or file.',
      },
      content: editor.content,
      actions,
      defaultFocus: editor.existing || (editor.evidenceTypes.length ? editor.evidenceType : 'cancel'),
      refocusOnResolve: false,
    });
    if (!['link', 'remove'].includes(choice)) restoreFocus(options.returnFocus);
    return ['link', 'remove'].includes(choice);
  } catch (err) {
    restoreFocus(options.returnFocus);
    ctx.setProjectWorkspaceMessage?.(
      err?.message || 'Could not open the assessment evidence editor.',
      { error: true },
    );
    ctx.logClientError?.('PROJECT_ASSESSMENT_CLIENT_EVIDENCE_CONFIRM_FAILED', err, {
      page: 'project_assessment',
      phase: 'evidence',
      project_id: projectId,
      assessment_id: assessmentId,
      check_id: checkId,
    });
    return false;
  }
}

export { openAssessmentEvidenceEditor };
