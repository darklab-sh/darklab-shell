// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Project Assessment tab state and data controller.

import { createProjectAssessmentRenderer } from './project_assessment_renderer.js';
import { launchAssessmentAction } from './project_assessment_actions.js';
import {
  createProjectAssessmentOastManager,
  isPrivateOastCheck,
} from './project_assessment_oast.js';
import { createProjectAssessmentZapManager } from './project_assessment_zap.js';
import { createProjectHttpProfileManager } from './project_http_profiles.js';
import { openContextualFindingRecord } from '../findings/finding_record_context.js';
import { openFindingTriageEditor } from '../findings/finding_triage_bridge.js';

function createProjectAssessmentController(context) {
  const ctx = context || {};
  const states = new Map();
  const actionLaunches = new Set();

  function defaultState() {
    return {
      assessments: [],
      profiles: [],
      selectedId: '',
      detail: null,
      loaded: false,
      loading: false,
      loadPromise: null,
      loadGeneration: 0,
      detailLoading: false,
      detailPromise: null,
      detailGeneration: 0,
      creating: false,
      mutating: '',
      error: '',
      detailError: '',
      category: '',
      checkState: '',
      findingPriority: '',
      findingLimit: 10,
      findingOffset: 0,
      limit: 50,
      offset: 0,
      checksScrollTop: 0,
      expandedTargets: new Set(),
    };
  }

  function stateFor(projectId) {
    const id = String(projectId || '');
    if (!states.has(id)) states.set(id, defaultState());
    return states.get(id);
  }

  function cancelListRequest(st) {
    st.loadGeneration += 1;
    st.loading = false;
    st.loadPromise = null;
  }

  function cancelDetailRequest(st) {
    st.detailGeneration += 1;
    st.detailLoading = false;
    st.detailPromise = null;
  }

  function invalidate(projectId = '') {
    const id = String(projectId || '');
    const targets = id ? [states.get(id)] : Array.from(states.values());
    targets.filter(Boolean).forEach((st) => {
      cancelListRequest(st);
      cancelDetailRequest(st);
      st.assessments = [];
      st.profiles = [];
      st.detail = null;
      st.loaded = false;
      st.error = '';
      st.detailError = '';
    });
    httpProfileManager.invalidate(id);
    oastManager.invalidate(id);
    zapManager.invalidate(id);
  }

  async function responseError(resp, fallback) {
    if (typeof ctx.projectResponseError === 'function') {
      return ctx.projectResponseError(resp, fallback);
    }
    return new Error(fallback);
  }

  function logFailure(message, err, details = {}) {
    ctx.logClientError?.(message, err, { page: 'project_assessment', ...details });
  }

  function renderViews() {
    ctx.renderProjectExplorer?.();
    if (ctx.mobileView?.() === 'detail') ctx.renderProjectMobileDetail?.();
  }

  const httpProfileManager = createProjectHttpProfileManager(ctx, { renderViews });
  const oastManager = createProjectAssessmentOastManager(ctx, { renderViews });
  const zapManager = createProjectAssessmentZapManager(ctx, { renderViews });

  function loadOastHistoryForDetail(projectId, loadedDetail) {
    const assessmentId = String(loadedDetail?.assessment?.id || '');
    const checks = Array.isArray(loadedDetail?.checks?.checks)
      ? loadedDetail.checks.checks
      : [];
    checks.filter(isPrivateOastCheck).forEach((check) => {
      void oastManager.loadHistory(projectId, assessmentId, check?.id);
    });
  }

  function cycleSelection(st) {
    return st.assessments.find(item => String(item?.id || '') === st.selectedId)
      || st.assessments.find(item => String(item?.status || '') === 'active')
      || st.assessments[0]
      || null;
  }

  function checkQuery(st) {
    const params = new URLSearchParams({ limit: String(st.limit), offset: String(st.offset) });
    if (st.category) params.set('category', st.category);
    if (st.checkState) params.set('state', st.checkState);
    params.set('finding_limit', String(st.findingLimit));
    params.set('finding_offset', String(st.findingOffset));
    if (st.findingPriority) params.set('finding_priority', st.findingPriority);
    return params.toString();
  }

  async function loadDetail(projectId, options = {}) {
    const id = String(projectId || '');
    const st = stateFor(id);
    const selected = cycleSelection(st);
    if (!id || !selected) {
      cancelDetailRequest(st);
      st.detail = null;
      st.selectedId = '';
      st.detailError = '';
      return false;
    }
    st.selectedId = String(selected.id || '');
    if (st.detailLoading && st.detailPromise && options.force !== true) return st.detailPromise;
    const generation = st.detailGeneration + 1;
    st.detailGeneration = generation;
    st.detailLoading = true;
    st.detailError = '';
    const promise = (async () => {
      try {
        const resp = await ctx.projectWorkspaceRequest(
          `/projects/${encodeURIComponent(id)}/assessments/${encodeURIComponent(st.selectedId)}?${checkQuery(st)}`,
          { cache: 'no-store' },
        );
        if (st.detailGeneration !== generation) return false;
        if (!resp.ok) throw await responseError(resp, 'Could not load this assessment cycle.');
        const payload = await resp.json();
        if (st.detailGeneration !== generation) return false;
        st.detail = payload;
        loadOastHistoryForDetail(id, st.detail);
        return true;
      } catch (err) {
        if (st.detailGeneration !== generation) return false;
        st.detailError = err?.message || 'Could not load this assessment cycle.';
        logFailure('PROJECT_ASSESSMENT_CLIENT_DETAIL_LOAD_FAILED', err, {
          phase: 'detail',
          project_id: id,
          assessment_id: st.selectedId,
        });
        return false;
      } finally {
        if (st.detailGeneration === generation) {
          st.detailLoading = false;
          st.detailPromise = null;
          if (options.render !== false) renderViews();
        }
      }
    })();
    st.detailPromise = promise;
    return promise;
  }

  async function load(projectId, options = {}) {
    const id = String(projectId || '');
    if (!id) return false;
    const st = stateFor(id);
    if (st.loaded && options.force !== true) {
      if (!st.detail && st.selectedId) return loadDetail(id, options);
      return true;
    }
    if (st.loading && st.loadPromise && options.force !== true) return st.loadPromise;
    const generation = st.loadGeneration + 1;
    st.loadGeneration = generation;
    st.loading = true;
    st.error = '';
    const promise = (async () => {
      try {
        const params = new URLSearchParams({ include_archived: '1', limit: '100' });
        const resp = await ctx.projectWorkspaceRequest(
          `/projects/${encodeURIComponent(id)}/assessments?${params.toString()}`,
          { cache: 'no-store' },
        );
        if (st.loadGeneration !== generation) return false;
        if (!resp.ok) throw await responseError(resp, 'Could not load project assessments.');
        const payload = await resp.json();
        if (st.loadGeneration !== generation) return false;
        st.assessments = Array.isArray(payload?.assessments) ? payload.assessments : [];
        st.profiles = Array.isArray(payload?.profiles) ? payload.profiles : [];
        st.selectedId = String(cycleSelection(st)?.id || '');
        st.loaded = true;
        const detailLoad = st.selectedId
          ? loadDetail(id, { render: false, force: options.force === true })
          : Promise.resolve(false);
        void httpProfileManager.load(id);
        await detailLoad;
        if (st.loadGeneration !== generation) return false;
        if (!st.selectedId) st.detail = null;
        return true;
      } catch (err) {
        if (st.loadGeneration !== generation) return false;
        st.error = err?.message || 'Could not load project assessments.';
        logFailure('PROJECT_ASSESSMENT_CLIENT_LOAD_FAILED', err, { phase: 'list', project_id: id });
        return false;
      } finally {
        if (st.loadGeneration === generation) {
          st.loading = false;
          st.loadPromise = null;
          if (options.render !== false) renderViews();
        }
      }
    })();
    st.loadPromise = promise;
    return promise;
  }

  function resetDetailState(st, { findings = true } = {}) {
    cancelDetailRequest(st);
    st.detail = null;
    st.offset = 0;
    st.checksScrollTop = 0;
    st.expandedTargets.clear();
    if (findings) {
      st.findingPriority = '';
      st.findingOffset = 0;
    }
  }

  async function selectCycle(projectId, assessmentId) {
    const st = stateFor(projectId);
    const nextId = String(assessmentId || '');
    if (!nextId || nextId === st.selectedId) return false;
    st.selectedId = nextId;
    st.category = '';
    st.checkState = '';
    resetDetailState(st);
    renderViews();
    return loadDetail(projectId);
  }

  async function focusCycle(projectId, assessmentId, filters = {}) {
    const id = String(projectId || '');
    const nextId = String(assessmentId || '');
    if (!id || !nextId) return false;
    const st = stateFor(id);
    st.selectedId = nextId;
    st.category = String(filters.category || '');
    st.checkState = String(filters.state || '');
    st.findingPriority = String(filters.priority || '');
    st.findingOffset = 0;
    resetDetailState(st, { findings: false });
    renderViews();
    if (st.loaded && st.assessments.some(item => String(item?.id || '') === nextId)) {
      return loadDetail(id);
    }
    st.loaded = false;
    return load(id, { force: true });
  }

  async function setFilter(projectId, key, value) {
    const st = stateFor(projectId);
    const normalized = String(value || '');
    if (key === 'category') st.category = normalized;
    else if (key === 'state') st.checkState = normalized;
    else return false;
    resetDetailState(st, { findings: false });
    renderViews();
    return loadDetail(projectId);
  }

  async function setPage(projectId, offset) {
    const st = stateFor(projectId);
    const nextOffset = Math.max(0, Number(offset || 0));
    if (nextOffset === st.offset) return false;
    st.offset = nextOffset;
    st.checksScrollTop = 0;
    st.detail = null;
    renderViews();
    return loadDetail(projectId);
  }

  async function setFindingFilter(projectId, priority) {
    const st = stateFor(projectId);
    const normalized = String(priority || '');
    if (normalized === st.findingPriority && st.findingOffset === 0) return false;
    st.findingPriority = normalized;
    st.findingOffset = 0;
    st.detail = null;
    renderViews();
    return loadDetail(projectId);
  }

  async function setFindingPage(projectId, offset) {
    const st = stateFor(projectId);
    const nextOffset = Math.max(0, Number(offset || 0));
    if (nextOffset === st.findingOffset) return false;
    st.findingOffset = nextOffset;
    st.detail = null;
    renderViews();
    return loadDetail(projectId);
  }

  async function createCycle(projectId, profileKey) {
    const id = String(projectId || '');
    const st = stateFor(id);
    const key = String(profileKey || '').trim();
    if (!id || !key || st.creating) return false;
    st.creating = true;
    st.error = '';
    renderViews();
    try {
      const resp = await ctx.projectWorkspaceRequest(`/projects/${encodeURIComponent(id)}/assessments`, {
        method: 'POST',
        body: JSON.stringify({ profile_key: key }),
      });
      if (!resp.ok) throw await responseError(resp, 'Could not start the assessment.');
      const payload = await resp.json();
      st.loaded = false;
      st.selectedId = String(payload?.assessment?.id || '');
      st.category = '';
      st.checkState = '';
      resetDetailState(st);
      ctx.invalidateProjectOverview?.(id);
      ctx.setProjectWorkspaceMessage?.('Assessment cycle started.');
      const loaded = await load(id, { force: true, render: false });
      return loaded;
    } catch (err) {
      st.error = err?.message || 'Could not start the assessment.';
      logFailure('PROJECT_ASSESSMENT_CLIENT_CREATE_FAILED', err, {
        phase: 'create',
        project_id: id,
        profile_key: key,
      });
      return false;
    } finally {
      st.creating = false;
      renderViews();
    }
  }

  function selectedAssessment(projectId) {
    return cycleSelection(stateFor(projectId));
  }

  function restoreFocus(target) {
    if (!target?.isConnected || target.disabled || typeof target.focus !== 'function') return;
    try {
      target.focus({ preventScroll: true });
    } catch (_) {
      target.focus();
    }
  }

  async function confirmLifecycle(options, returnFocus = null) {
    if (typeof ctx.showConfirm !== 'function') {
      const err = new Error('Assessment lifecycle confirmations are unavailable.');
      ctx.setProjectWorkspaceMessage?.(err.message, { error: true });
      logFailure('PROJECT_ASSESSMENT_CLIENT_CONFIRM_UNAVAILABLE', err, { phase: 'confirmation' });
      return false;
    }
    const { confirmId, ...confirmOptions } = options;
    try {
      const choice = await ctx.showConfirm({ ...confirmOptions, refocusOnResolve: false });
      restoreFocus(returnFocus);
      return choice === confirmId;
    } catch (err) {
      ctx.setProjectWorkspaceMessage?.(err?.message || 'Could not open the assessment confirmation.', { error: true });
      logFailure('PROJECT_ASSESSMENT_CLIENT_CONFIRM_FAILED', err, { phase: 'confirmation' });
      return false;
    }
  }

  async function mutateCycle(projectId, action, request, successMessage, { resetSelection = false } = {}) {
    const id = String(projectId || '');
    const st = stateFor(id);
    if (!id || st.mutating) return false;
    st.mutating = String(action || 'update');
    renderViews();
    try {
      await request();
      if (resetSelection) {
        st.selectedId = '';
        st.category = '';
        st.checkState = '';
        resetDetailState(st);
      } else {
        st.loaded = false;
        cancelDetailRequest(st);
        st.detail = null;
      }
      ctx.invalidateProjectOverview?.(id);
      ctx.setProjectWorkspaceMessage?.(successMessage);
      const loaded = await load(id, { force: true, render: false });
      return loaded;
    } catch (err) {
      const message = err?.message || 'Could not update this assessment cycle.';
      ctx.setProjectWorkspaceMessage?.(message, { error: true });
      logFailure(`PROJECT_ASSESSMENT_CLIENT_${String(action || 'update').toUpperCase()}_FAILED`, err, {
        phase: 'lifecycle',
        action: String(action || 'update'),
        project_id: id,
        assessment_id: st.selectedId,
      });
      return false;
    } finally {
      st.mutating = '';
      renderViews();
    }
  }

  async function transitionCycle(projectId, status, returnFocus = null) {
    const assessment = selectedAssessment(projectId);
    const nextStatus = String(status || '');
    if (!assessment || !['completed', 'archived'].includes(nextStatus)) return false;
    const completing = nextStatus === 'completed';
    const actionLabel = completing ? 'Complete cycle' : 'Archive cycle';
    const confirmed = await confirmLifecycle({
      body: {
        text: `${actionLabel}: ${assessment.title || 'this assessment'}?`,
        note: completing
          ? 'Completed cycles keep their saved checks and evidence, but they become read-only.'
          : 'Archived cycles stay available for review and can be permanently deleted later.',
      },
      tone: 'warning',
      confirmId: nextStatus,
      actions: [
        { id: 'cancel', label: 'Cancel', role: 'cancel' },
        { id: nextStatus, label: actionLabel, tone: 'warning' },
      ],
    }, returnFocus);
    if (!confirmed) return false;
    return mutateCycle(projectId, completing ? 'complete' : 'archive', async () => {
      const resp = await ctx.projectWorkspaceRequest(
        `/projects/${encodeURIComponent(projectId)}/assessments/${encodeURIComponent(assessment.id)}`,
        { method: 'PATCH', body: JSON.stringify({ status: nextStatus }) },
      );
      if (!resp.ok) throw await responseError(resp, 'Could not update this assessment cycle.');
    }, completing ? 'Assessment cycle completed.' : 'Assessment cycle archived.');
  }

  async function deleteCycle(projectId, returnFocus = null) {
    const assessment = selectedAssessment(projectId);
    if (!assessment || assessment.status !== 'archived') return false;
    const st = stateFor(projectId);
    if (st.mutating) return false;
    st.mutating = 'delete_preview';
    renderViews();
    let preview;
    try {
      const resp = await ctx.projectWorkspaceRequest(
        `/projects/${encodeURIComponent(projectId)}/assessments/${encodeURIComponent(assessment.id)}/delete-preview`,
        { cache: 'no-store' },
      );
      if (!resp.ok) throw await responseError(resp, 'Could not preview assessment deletion.');
      preview = (await resp.json())?.preview || null;
    } catch (err) {
      ctx.setProjectWorkspaceMessage?.(err?.message || 'Could not preview assessment deletion.', { error: true });
      logFailure('PROJECT_ASSESSMENT_CLIENT_DELETE_PREVIEW_FAILED', err, {
        phase: 'delete_preview',
        project_id: String(projectId || ''),
        assessment_id: String(assessment.id || ''),
      });
      return false;
    } finally {
      st.mutating = '';
      renderViews();
    }
    if (!preview?.can_delete) return false;
    const counts = preview.will_delete || {};
    const confirmed = await confirmLifecycle({
      body: {
        text: `Delete assessment: ${assessment.title || 'this cycle'}?`,
        note: `This removes ${Number(counts.checks || 0)} saved checks and ${Number(counts.evidence_links || 0)} evidence links. Source runs, findings, entities, and files stay intact.`,
      },
      tone: 'danger',
      confirmId: 'delete',
      actions: [
        { id: 'cancel', label: 'Cancel', role: 'cancel' },
        { id: 'delete', label: 'Delete assessment', role: 'destructive' },
      ],
    }, returnFocus);
    if (!confirmed) return false;
    return mutateCycle(projectId, 'delete', async () => {
      const resp = await ctx.projectWorkspaceRequest(
        `/projects/${encodeURIComponent(projectId)}/assessments/${encodeURIComponent(assessment.id)}`,
        { method: 'DELETE' },
      );
      if (!resp.ok) throw await responseError(resp, 'Could not delete this assessment cycle.');
    }, 'Assessment cycle deleted.', { resetSelection: true });
  }

  async function createFinding(projectId, check, definition = {}, returnFocus = null) {
    const targetId = String(check?.target_entity_id || '');
    if (!projectId || !targetId || !check?.id) return false;
    if (ctx.canTriageFindings?.() === false) {
      ctx.setProjectWorkspaceMessage?.(
        "View-only team members can't create findings. Switch to Personal or ask for operator access.",
        { error: true },
      );
      return false;
    }
    ctx.setProjectWorkspaceMessage?.('');
    try {
      const openFindingEditor = typeof ctx.openContextualFindingRecord === 'function'
        ? ctx.openContextualFindingRecord
        : openContextualFindingRecord;
      await openFindingEditor({
        projectId,
        targetId,
        request: ctx.projectWorkspaceRequest,
        canEdit: true,
        returnFocus,
        defaults: {
          title: `${definition?.label || check?.check_key || 'Assessment check'}: ${check?.target_value || targetId}`,
          summary: definition?.purpose || check?.state_reason || '',
          severity: 'medium',
          confidence: 'unknown',
        },
        evidence: [{
          evidence_type: 'assessment_check',
          evidence_id: String(check.id),
          label: definition?.label || check?.check_key || 'Assessment check',
        }],
        onSaved: async () => {
          ctx.invalidateProjectFindings?.(projectId);
          ctx.invalidateProjectOverview?.(projectId);
          ctx.setProjectWorkspaceMessage?.('Finding created from the assessment check.');
          renderViews();
        },
      });
      return true;
    } catch (err) {
      ctx.setProjectWorkspaceMessage?.(err?.message || 'Could not open the finding editor.', { error: true });
      logFailure('PROJECT_ASSESSMENT_CLIENT_FINDING_EDITOR_FAILED', err, {
        phase: 'finding_editor',
        project_id: String(projectId || ''),
        assessment_check_id: String(check?.id || ''),
      });
      return false;
    }
  }

  async function openDeltaFinding(projectId, finding, returnFocus = null) {
    const findingId = String(finding?.id || '');
    if (!projectId || !findingId) return false;
    const openEditor = typeof ctx.openFindingTriageEditor === 'function'
      ? ctx.openFindingTriageEditor
      : openFindingTriageEditor;
    try {
      await openEditor(finding, {
        projectId,
        canEdit: ctx.canTriageFindings?.() !== false,
        returnFocus,
        onSaved: async () => {
          ctx.invalidateProjectFindings?.(projectId);
          ctx.invalidateProjectOverview?.(projectId);
          await loadDetail(projectId, { render: false });
          renderViews();
        },
      });
      return true;
    } catch (err) {
      ctx.setProjectWorkspaceMessage?.(err?.message || 'Could not open finding details.', { error: true });
      logFailure('PROJECT_ASSESSMENT_CLIENT_DELTA_FINDING_OPEN_FAILED', err, {
        phase: 'finding_delta',
        project_id: String(projectId || ''),
        finding_id: findingId,
      });
      return false;
    }
  }

  async function launchRecommendedAction(projectId, check, returnFocus = null) {
    const assessmentId = String(check?.assessment_id || stateFor(projectId).selectedId || '');
    const checkId = String(check?.id || '');
    const launchKey = `${String(projectId || '')}:${assessmentId}:${checkId}`;
    if (!projectId || !assessmentId || !checkId || actionLaunches.has(launchKey)) return false;
    if (ctx.canRunCommands?.() === false) {
      ctx.setProjectWorkspaceMessage?.(
        "View-only team members can't start assessment runs. Switch to Personal or ask for operator access.",
        { error: true },
      );
      return false;
    }
    actionLaunches.add(launchKey);
    try {
      return await launchAssessmentAction(ctx, {
        projectId,
        assessmentId,
        check,
        httpProfiles: httpProfileManager.profilesForLaunch(projectId),
        canManageSecrets: ctx.canManageSecrets?.() !== false,
        returnFocus,
      });
    } finally {
      actionLaunches.delete(launchKey);
    }
  }

  function openOast(projectId, detail, check, returnFocus = null) {
    return oastManager.open(
      projectId,
      detail,
      check,
      httpProfileManager.profilesForLaunch(projectId),
      returnFocus,
    );
  }

  function startNewOast(projectId, detail, check, returnFocus = null) {
    return oastManager.startNew(
      projectId,
      detail,
      check,
      httpProfileManager.profilesForLaunch(projectId),
      returnFocus,
    );
  }

  function openZap(projectId, detail, check, returnFocus = null) {
    return zapManager.open(
      projectId,
      detail,
      check,
      httpProfileManager.profilesForLaunch(projectId),
      returnFocus,
    );
  }

  function startNewZap(projectId, detail, check, returnFocus = null) {
    return zapManager.startNew(
      projectId,
      detail,
      check,
      httpProfileManager.profilesForLaunch(projectId),
      returnFocus,
    );
  }

  const renderer = createProjectAssessmentRenderer(ctx, {
    deleteCycle,
    createCycle,
    createFinding,
    load,
    loadDetail,
    launchRecommendedAction,
    cancelZap: zapManager.cancel,
    openOast,
    openOastRunDetails: oastManager.openRunDetails,
    refreshOast: oastManager.refresh,
    openZap,
    openZapAtlas: zapManager.openAtlas,
    openZapFiles: zapManager.openFiles,
    openDeltaFinding,
    selectCycle,
    setFilter,
    setFindingFilter,
    setFindingPage,
    setPage,
    transitionCycle,
    startNewOast,
    startNewZap,
    oastCurrentCorrelation: oastManager.currentCorrelation,
    oastStateFor: oastManager.stateFor,
    zapStateFor: zapManager.stateFor,
    renderHttpProfiles: (projectId, options = {}) => httpProfileManager.renderSection(projectId, options),
  });

  function ensureLoad(projectId) {
    const st = stateFor(projectId);
    if (!st.loaded && !st.loading) void load(projectId);
    return st;
  }

  function renderAssessment(container, projectId) {
    const st = ensureLoad(projectId);
    container.replaceChildren(renderer.renderContent(projectId, st, cycleSelection(st)));
    ctx.enhanceAppSelects?.(container);
  }

  function renderMobileAssessmentTab(projectId) {
    const st = ensureLoad(projectId);
    const content = renderer.renderContent(projectId, st, cycleSelection(st), { mobile: true });
    ctx.enhanceAppSelects?.(content);
    return content;
  }

  return {
    createCycle,
    deleteCycle,
    focusCycle,
    invalidate,
    load,
    loadDetail,
    oastStateFor: oastManager.stateFor,
    renderAssessment,
    renderMobileAssessmentTab,
    httpProfileStateFor: httpProfileManager.stateFor,
    selectCycle,
    setFilter,
    setFindingFilter,
    setFindingPage,
    setPage,
    stateFor,
    transitionCycle,
  };
}

const DarklabProjectAssessment = { createProjectAssessmentController };

export { DarklabProjectAssessment };
