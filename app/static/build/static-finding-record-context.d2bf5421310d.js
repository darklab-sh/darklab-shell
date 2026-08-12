// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Shared Project target loading and contextual manual-finding launch support.
import { apiFetch as importedApiFetch } from '../../session.js';
import { openFindingRecordEditor as importedOpenFindingRecordEditor } from './finding_triage_bridge.js';

const TARGET_PAGE_LIMIT = 100;
const MAX_TARGET_OPTIONS = 1000;

function text(value) {
  return String(value || '').trim();
}

async function responseError(resp, fallback) {
  const payload = await resp?.json?.().catch(() => ({}));
  return new Error(text(payload?.error) || fallback);
}

async function loadConfirmedProjectTargets(projectId, options = {}) {
  const normalizedProjectId = text(projectId);
  if (!normalizedProjectId) throw new Error('Project is missing its identifier.');
  const request = typeof options.request === 'function' ? options.request : importedApiFetch;
  const targets = [];
  let offset = 0;
  let total = 0;
  do {
    const params = new URLSearchParams({
      limit: String(TARGET_PAGE_LIMIT),
      offset: String(offset),
    });
    const resp = await request(
      `/projects/${encodeURIComponent(normalizedProjectId)}/targets?${params.toString()}`,
      { cache: 'no-store' },
    );
    if (!resp?.ok) throw await responseError(resp, 'Could not load Project targets.');
    const payload = await resp.json();
    const page = Array.isArray(payload?.targets) ? payload.targets : [];
    targets.push(...page.filter(target => text(target?.review_state || 'confirmed') === 'confirmed'));
    total = Math.max(0, Number(payload?.total || page.length || 0));
    offset += page.length;
    if (!page.length || offset >= total) break;
    if (offset >= MAX_TARGET_OPTIONS) {
      throw new Error('This Project has too many targets for the finding editor. Narrow the Project before continuing.');
    }
  } while (offset < total);
  const requiredTargetId = text(options.requiredTargetId);
  if (requiredTargetId && !targets.some(target => text(target?.id) === requiredTargetId)) {
    throw new Error('Confirm this entity as a Project target before recording a finding against it.');
  }
  return targets;
}

async function openContextualFindingRecord(options = {}) {
  const projectId = text(options.projectId);
  const targets = Array.isArray(options.targets)
    ? options.targets
    : await loadConfirmedProjectTargets(projectId, {
        request: options.request,
        requiredTargetId: options.targetId,
      });
  const inferredTargetId = !options.targetId && typeof options.selectTargetId === 'function'
    ? text(options.selectTargetId(targets))
    : '';
  const editorOptions = { ...options, projectId, targets };
  delete editorOptions.selectTargetId;
  if (inferredTargetId && targets.some(target => text(target?.id) === inferredTargetId)) {
    editorOptions.targetId = inferredTargetId;
  }
  const openEditor = typeof importedOpenFindingRecordEditor === 'function'
    ? importedOpenFindingRecordEditor
    : null;
  if (typeof openEditor !== 'function') throw new Error('Finding editor is unavailable.');
  return openEditor(editorOptions);
}

export {
  loadConfirmedProjectTargets,
  openContextualFindingRecord,
};
