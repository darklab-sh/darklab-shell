// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Durable assessment-batch planning and monitor state for the Assessment tab.

import { createProjectAssessmentBatchRenderer } from './project_assessment_batch_renderer.js';
import { createAssessmentBatchRetryPreview } from './project_assessment_batch_retry.js';
import { logAssessmentClientFailure } from './project_assessment_client_log.js';

const ACTIVE_BATCH_STATUSES = new Set(['queued', 'running', 'canceling']);
const DEFAULT_SELECTION = Object.freeze({
  includeStandard: false,
  itemLimit: 128,
  maxParallel: 8,
  maxOwnerParallel: 16,
  maxInstanceParallel: 32,
});

function createProjectAssessmentBatchManager(context, hooks = {}) {
  const ctx = context || {};
  const renderViews = hooks.renderViews || (() => {});
  const states = new Map();
  const renderer = createProjectAssessmentBatchRenderer(ctx, {
    cancelBatch,
    createPreview,
    loadMoreBatchItems,
    loadMorePreviewItems,
    newPlan,
    retryBatch,
    selectBatch,
    setSelection,
    startBatch,
  });

  function stateKey(projectId, assessmentId) {
    return `${String(projectId || '')}:${String(assessmentId || '')}`;
  }

  function defaultState(projectId, assessmentId) {
    return {
      projectId: String(projectId || ''),
      assessmentId: String(assessmentId || ''),
      loaded: false,
      loading: false,
      loadPromise: null,
      generation: 0,
      error: '',
      planning: false,
      previewing: false,
      starting: false,
      canceling: false,
      batches: [],
      selectedBatchId: '',
      batch: null,
      batchItems: [],
      batchItemsCursor: null,
      batchItemsLoading: false,
      events: [],
      eventCursor: 0,
      preview: null,
      previewItems: [],
      previewItemsCursor: null,
      previewItemsLoading: false,
      previewDirty: false,
      pollTimer: null,
      renderAssessment: null,
      renderDetail: null,
      selection: {
        ...DEFAULT_SELECTION,
        excludedTargetIds: new Set(),
        excludedCategories: new Set(),
      },
    };
  }

  function stateFor(projectId, assessmentId) {
    const key = stateKey(projectId, assessmentId);
    if (!states.has(key)) states.set(key, defaultState(projectId, assessmentId));
    return states.get(key);
  }

  async function responseError(resp, fallback) {
    if (typeof ctx.projectResponseError === 'function') {
      return ctx.projectResponseError(resp, fallback);
    }
    return new Error(fallback);
  }

  function logFailure(event, err, st, details = {}) {
    logAssessmentClientFailure(ctx, event, err, {
      phase: 'assessment_batch',
      project_id: st?.projectId || '',
      assessment_id: st?.assessmentId || '',
      batch_id: st?.selectedBatchId || '',
      ...details,
    });
  }

  function clearPoll(st) {
    if (st.pollTimer !== null) globalThis.clearTimeout(st.pollTimer);
    st.pollTimer = null;
  }

  function invalidate(projectId = '') {
    const id = String(projectId || '');
    [...states.entries()].forEach(([key, st]) => {
      if (id && st.projectId !== id) return;
      clearPoll(st);
      st.generation += 1;
      states.delete(key);
    });
  }

  function schedulePoll(st, delay = null) {
    clearPoll(st);
    if (!ACTIVE_BATCH_STATUSES.has(String(st.batch?.status || ''))) return;
    const hidden = typeof document !== 'undefined' && document.visibilityState === 'hidden';
    st.pollTimer = globalThis.setTimeout(() => {
      st.pollTimer = null;
      void refreshBatch(st, { render: true });
    }, delay ?? (hidden ? 10000 : 2500));
  }

  function scrollContainersFor(section) {
    const containers = [];
    let current = section?.parentElement || null;
    while (current) {
      if (current.classList?.contains('project-explorer-body')
          || current.classList?.contains('project-mobile-detail-body')) {
        containers.push({ element: current, top: current.scrollTop, left: current.scrollLeft });
      }
      current = current.parentElement;
    }
    return containers;
  }

  function restorePolledFocus(section, focusKey) {
    if (!focusKey) return;
    const keyedTarget = [...section.querySelectorAll('[data-assessment-batch-focus-key]')]
      .find(node => node.dataset.assessmentBatchFocusKey === focusKey);
    const target = keyedTarget?.matches?.('select.app-select-native')
      ? keyedTarget.nextElementSibling?.querySelector('.app-select-trigger')
      : keyedTarget;
    restoreFocus(target);
  }

  function renderPolledSections(st) {
    if (typeof document === 'undefined' || !st.renderAssessment) return false;
    const sections = [...document.querySelectorAll('.project-assessment-batch')]
      .filter(section => (
        section.dataset.projectId === st.projectId
        && section.dataset.assessmentId === st.assessmentId
      ));
    let updated = false;
    sections.forEach((section) => {
      const currentMonitor = section.querySelector(':scope > .project-assessment-batch-monitor');
      if (!currentMonitor) return;
      const active = document.activeElement;
      const keyedActive = active?.closest?.('[data-assessment-batch-focus-key]');
      const enhancedSelect = active?.closest?.('.app-select')?.previousElementSibling;
      const focusKey = section.contains(active)
        ? String(
          keyedActive?.dataset?.assessmentBatchFocusKey
          || enhancedSelect?.dataset?.assessmentBatchFocusKey
          || '',
        )
        : '';
      const scrollContainers = scrollContainersFor(section);
      const nextSection = renderer.render(
        st.projectId,
        st.renderAssessment,
        st.renderDetail,
        st,
      );
      const nextMonitor = nextSection.querySelector(':scope > .project-assessment-batch-monitor');
      if (!nextMonitor) return;
      currentMonitor.replaceWith(nextMonitor);

      const currentError = section.querySelector(':scope > .project-assessment-batch-error');
      const nextError = nextSection.querySelector(':scope > .project-assessment-batch-error');
      if (currentError && nextError) currentError.replaceWith(nextError);
      else if (currentError) currentError.remove();
      else if (nextError) section.querySelector(':scope > .project-assessment-section-heading')?.after(nextError);

      ctx.enhanceAppSelects?.(nextMonitor);
      scrollContainers.forEach(snapshot => {
        snapshot.element.scrollTop = snapshot.top;
        snapshot.element.scrollLeft = snapshot.left;
      });
      restorePolledFocus(section, focusKey);
      scrollContainers.forEach(snapshot => {
        snapshot.element.scrollTop = snapshot.top;
        snapshot.element.scrollLeft = snapshot.left;
      });
      updated = true;
    });
    return updated;
  }

  async function requestJson(url, options, fallback) {
    const resp = await ctx.projectWorkspaceRequest(url, options);
    if (!resp.ok) throw await responseError(resp, fallback);
    return resp.json();
  }

  async function loadBatchItemPage(st, { append = false } = {}) {
    if (!st.selectedBatchId || st.batchItemsLoading) return false;
    const cursor = append ? st.batchItemsCursor : 0;
    if (append && cursor === null) return false;
    st.batchItemsLoading = true;
    try {
      const params = new URLSearchParams({ cursor: String(cursor || 0), limit: '100' });
      const payload = await requestJson(
        `/assessment-batches/${encodeURIComponent(st.selectedBatchId)}/items?${params}`,
        { cache: 'no-store' },
        'Could not load assessment batch items.',
      );
      st.batchItems = append
        ? [...st.batchItems, ...(Array.isArray(payload?.items) ? payload.items : [])]
        : (Array.isArray(payload?.items) ? payload.items : []);
      st.batchItemsCursor = payload?.next_cursor ?? null;
      return true;
    } finally {
      st.batchItemsLoading = false;
    }
  }

  async function refreshVisibleBatchItems(st) {
    const visibleCount = Math.max(100, st.batchItems.length);
    await loadBatchItemPage(st);
    let lastCursor = null;
    while (st.batchItemsCursor !== null && st.batchItems.length < visibleCount) {
      const cursor = st.batchItemsCursor;
      if (cursor === lastCursor) break;
      lastCursor = cursor;
      await loadBatchItemPage(st, { append: true });
      if (st.batchItemsCursor === cursor) break;
    }
  }

  async function loadEvents(st) {
    if (!st.selectedBatchId) return false;
    const params = new URLSearchParams({ cursor: String(st.eventCursor || 0), limit: '100' });
    const payload = await requestJson(
      `/assessment-batches/${encodeURIComponent(st.selectedBatchId)}/events?${params}`,
      { cache: 'no-store' },
      'Could not load assessment batch activity.',
    );
    const incoming = Array.isArray(payload?.events) ? payload.events : [];
    if (incoming.length) {
      st.events = [...st.events, ...incoming].slice(-200);
      st.eventCursor = Math.max(st.eventCursor, ...incoming.map(item => Number(item?.sequence || 0)));
    }
    return Boolean(payload?.has_more);
  }

  async function refreshBatch(st, { render = false } = {}) {
    if (!st.selectedBatchId) return false;
    const generation = st.generation;
    try {
      const payload = await requestJson(
        `/assessment-batches/${encodeURIComponent(st.selectedBatchId)}`,
        { cache: 'no-store' },
        'Could not refresh the assessment batch.',
      );
      if (st.generation !== generation) return false;
      st.batch = payload?.batch || null;
      const index = st.batches.findIndex(item => item?.batch_id === st.selectedBatchId);
      if (index >= 0 && st.batch) st.batches.splice(index, 1, st.batch);
      else if (st.batch) st.batches.unshift(st.batch);
      await Promise.all([refreshVisibleBatchItems(st), loadEvents(st)]);
      st.error = '';
      schedulePoll(st);
      return true;
    } catch (err) {
      if (st.generation !== generation) return false;
      st.error = err?.message || 'Could not refresh the assessment batch.';
      logFailure('PROJECT_ASSESSMENT_BATCH_CLIENT_REFRESH_FAILED', err, st);
      schedulePoll(st, 10000);
      return false;
    } finally {
      if (render && st.generation === generation) renderPolledSections(st);
    }
  }

  async function load(projectId, assessmentId, { force = false, render = true } = {}) {
    const st = stateFor(projectId, assessmentId);
    if (st.loaded && !force) return true;
    if (st.loading && st.loadPromise && !force) return st.loadPromise;
    const generation = st.generation + 1;
    st.generation = generation;
    st.loading = true;
    st.error = '';
    const promise = (async () => {
      try {
        const params = new URLSearchParams({ assessment_id: st.assessmentId, limit: '20' });
        const payload = await requestJson(
          `/projects/${encodeURIComponent(st.projectId)}/assessment-batches?${params}`,
          { cache: 'no-store' },
          'Could not load assessment batches.',
        );
        if (st.generation !== generation) return false;
        st.batches = Array.isArray(payload?.batches) ? payload.batches : [];
        if (!st.batches.some(item => item?.batch_id === st.selectedBatchId)) {
          st.selectedBatchId = String(st.batches[0]?.batch_id || '');
        }
        st.batch = st.batches.find(item => item?.batch_id === st.selectedBatchId) || null;
        st.loaded = true;
        if (st.batch) {
          st.batchItems = [];
          st.batchItemsCursor = null;
          st.events = [];
          st.eventCursor = 0;
          await Promise.all([loadBatchItemPage(st), loadEvents(st)]);
          schedulePoll(st);
        }
        return true;
      } catch (err) {
        if (st.generation !== generation) return false;
        st.error = err?.message || 'Could not load assessment batches.';
        logFailure('PROJECT_ASSESSMENT_BATCH_CLIENT_LOAD_FAILED', err, st);
        return false;
      } finally {
        if (st.generation === generation) {
          st.loading = false;
          st.loadPromise = null;
          if (render) renderViews();
        }
      }
    })();
    st.loadPromise = promise;
    return promise;
  }

  function selectionPayload(st) {
    return {
      excluded_target_entity_ids: [...st.selection.excludedTargetIds].sort(),
      excluded_categories: [...st.selection.excludedCategories].sort(),
      include_standard: st.selection.includeStandard,
      item_limit: st.selection.itemLimit,
      max_parallel: st.selection.maxParallel,
      max_owner_parallel: st.selection.maxOwnerParallel,
      max_instance_parallel: st.selection.maxInstanceParallel,
    };
  }

  async function loadPreviewItemPage(st, { append = false } = {}) {
    const previewId = String(st.preview?.preview_id || '');
    if (!previewId || st.previewItemsLoading) return false;
    const cursor = append ? st.previewItemsCursor : 0;
    if (append && cursor === null) return false;
    st.previewItemsLoading = true;
    try {
      const params = new URLSearchParams({ cursor: String(cursor || 0), limit: '100' });
      const payload = await requestJson(
        `/assessment-batch-previews/${encodeURIComponent(previewId)}/items?${params}`,
        { cache: 'no-store' },
        'Could not load assessment plan commands.',
      );
      st.previewItems = append
        ? [...st.previewItems, ...(Array.isArray(payload?.items) ? payload.items : [])]
        : (Array.isArray(payload?.items) ? payload.items : []);
      st.previewItemsCursor = payload?.next_cursor ?? null;
      return true;
    } finally {
      st.previewItemsLoading = false;
    }
  }

  async function createPreview(projectId, assessmentId) {
    const st = stateFor(projectId, assessmentId);
    if (st.previewing || st.starting) return false;
    st.previewing = true;
    st.error = '';
    renderViews();
    try {
      const payload = await requestJson(
        `/projects/${encodeURIComponent(projectId)}/assessments/${encodeURIComponent(assessmentId)}/batch-previews`,
        { method: 'POST', body: JSON.stringify(selectionPayload(st)) },
        'Could not preview this assessment plan.',
      );
      st.preview = payload?.preview || null;
      st.previewItems = [];
      st.previewItemsCursor = null;
      st.previewDirty = false;
      st.planning = true;
      await loadPreviewItemPage(st);
      return true;
    } catch (err) {
      st.error = err?.message || 'Could not preview this assessment plan.';
      logFailure('PROJECT_ASSESSMENT_BATCH_CLIENT_PREVIEW_FAILED', err, st);
      return false;
    } finally {
      st.previewing = false;
      renderViews();
    }
  }

  async function retryBatch(projectId, assessmentId) {
    const st = stateFor(projectId, assessmentId);
    return createAssessmentBatchRetryPreview(st, {
      loadPreviewItemPage,
      logFailure,
      renderViews,
      requestJson,
      selectionPayload,
    });
  }

  function restoreFocus(target) {
    if (!target?.isConnected || target.disabled || typeof target.focus !== 'function') return;
    try { target.focus({ preventScroll: true }); } catch (_) { target.focus(); }
  }

  async function confirmAction(options, returnFocus) {
    if (typeof ctx.showConfirm !== 'function') return false;
    const choice = await ctx.showConfirm({ ...options, refocusOnResolve: false });
    restoreFocus(returnFocus);
    return choice === options.confirmId;
  }

  function standardConfirmationNote(preview) {
    const summary = preview?.summary || {};
    const concurrency = preview?.concurrency || {};
    const targets = Number(summary.selected_target_count || 0);
    const commands = Number(preview?.selected_item_count || 0);
    const explicit = Number(summary.explicit_request_limit_item_count || 0);
    const toolBounded = Number(summary.tool_bounded_request_item_count || 0);
    return `${targets} ${targets === 1 ? 'target' : 'targets'}; ${commands} ${commands === 1 ? 'command' : 'commands'}; fan-out ${Number(summary.fan_out || 0)} with up to ${Number(concurrency.batch || 0)} concurrent; request bounds: ${explicit} explicit-limit and ${toolBounded} tool-bounded commands; maximum per-command time bound ${Number(summary.maximum_item_duration_bound_seconds || 0)} seconds; credentials: ${String(summary.credential_classification || 'none')}.`;
  }

  async function startBatch(projectId, assessmentId, returnFocus = null) {
    const st = stateFor(projectId, assessmentId);
    if (!st.preview || st.previewDirty || st.starting) return false;
    const standard = Boolean(st.preview?.summary?.requires_standard_confirmation);
    const retry = Boolean(st.preview?.source_batch_id);
    const nucleiPreflight = st.preview?.summary?.nuclei_preflight || null;
    let nucleiSnapshotConfirmed = false;
    if (nucleiPreflight?.state === 'stale') {
      nucleiSnapshotConfirmed = await confirmAction({
        body: {
          text: 'Continue with stale managed Nuclei templates?',
          note: `${Number(nucleiPreflight.command_count || 0)} planned Nuclei commands will use template release ${String(nucleiPreflight.release_version || 'unknown')} and the exact snapshot digest shown in the preview. Updating and rebuilding the preview is recommended when network access is available.`,
        },
        tone: 'warning',
        confirmId: 'continue_nuclei_snapshot',
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          {
            id: 'continue_nuclei_snapshot',
            label: 'Continue with current snapshot',
            role: 'secondary',
            tone: 'warning',
          },
        ],
      }, returnFocus);
      if (!nucleiSnapshotConfirmed) return false;
    }
    const confirmId = retry ? 'start_retry' : (standard ? 'start_standard' : 'start');
    const confirmed = await confirmAction({
      body: {
        text: retry
          ? 'Retry failed or unfinished assessment commands?'
          : (standard ? 'Run safe and standard assessment commands?' : 'Run this assessment plan?'),
        note: retry
          ? 'This creates a new batch. Succeeded source commands, completed runs, and existing evidence stay unchanged.'
          : (standard
          ? standardConfirmationNote(st.preview)
          : 'The batch keeps completed evidence if another command fails or you cancel later.'),
      },
      tone: standard ? 'warning' : null,
      confirmId,
      actions: [
        { id: 'cancel', label: 'Cancel', role: 'cancel' },
        {
          id: confirmId,
          label: retry ? 'Start retry' : (standard ? 'Run safe and standard' : 'Run assessment plan'),
          role: standard ? 'secondary' : 'primary',
          tone: standard ? 'warning' : null,
        },
      ],
    }, returnFocus);
    if (!confirmed) return false;
    if (retry && standard) {
      const standardConfirmed = await confirmAction({
        body: {
          text: 'Include standard commands in this retry?',
          note: standardConfirmationNote(st.preview),
        },
        tone: 'warning',
        confirmId: 'start_retry_standard',
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'start_retry_standard', label: 'Include standard and retry', tone: 'warning' },
        ],
      }, returnFocus);
      if (!standardConfirmed) return false;
    }
    st.starting = true;
    st.error = '';
    renderViews();
    try {
      const payload = await requestJson(
        retry
          ? `/projects/${encodeURIComponent(projectId)}/assessment-batches/${encodeURIComponent(st.preview.source_batch_id)}/retry`
          : `/projects/${encodeURIComponent(projectId)}/assessments/${encodeURIComponent(assessmentId)}/assessment-batches`,
        {
          method: 'POST',
          body: JSON.stringify({
            preview_id: st.preview.preview_id,
            plan_digest: st.preview.plan_digest,
            confirmed: true,
            nuclei_snapshot_confirmed: nucleiSnapshotConfirmed,
            standard_confirmed: standard,
          }),
        },
        'Could not start this assessment batch.',
      );
      st.batch = payload?.batch || null;
      st.selectedBatchId = String(st.batch?.batch_id || '');
      st.batches = [st.batch, ...st.batches.filter(item => item?.batch_id !== st.selectedBatchId)].filter(Boolean);
      st.batchItems = [];
      st.batchItemsCursor = null;
      st.events = [];
      st.eventCursor = 0;
      st.preview = null;
      st.previewItems = [];
      st.previewItemsCursor = null;
      st.planning = false;
      await Promise.all([loadBatchItemPage(st), loadEvents(st)]);
      schedulePoll(st);
      ctx.setProjectWorkspaceMessage?.(retry ? 'Assessment batch retry started.' : 'Assessment batch started.');
      return true;
    } catch (err) {
      st.error = err?.message || 'Could not start this assessment batch.';
      logFailure('PROJECT_ASSESSMENT_BATCH_CLIENT_START_FAILED', err, st);
      return false;
    } finally {
      st.starting = false;
      renderViews();
    }
  }

  async function cancelBatch(projectId, assessmentId, returnFocus = null) {
    const st = stateFor(projectId, assessmentId);
    if (!ACTIVE_BATCH_STATUSES.has(String(st.batch?.status || '')) || st.canceling) return false;
    const confirmed = await confirmAction({
      body: {
        text: 'Cancel this assessment batch?',
        note: 'No new commands will start. Active commands receive a cancellation request, while completed runs and evidence stay saved.',
      },
      tone: 'warning',
      confirmId: 'cancel_batch',
      actions: [
        { id: 'keep', label: 'Keep running', role: 'cancel' },
        { id: 'cancel_batch', label: 'Cancel batch', tone: 'warning' },
      ],
    }, returnFocus);
    if (!confirmed) return false;
    st.canceling = true;
    st.error = '';
    renderViews();
    try {
      const payload = await requestJson(
        `/projects/${encodeURIComponent(projectId)}/assessment-batches/${encodeURIComponent(st.selectedBatchId)}/cancel`,
        { method: 'POST', body: JSON.stringify({}) },
        'Could not cancel this assessment batch.',
      );
      st.batch = payload?.batch || st.batch;
      schedulePoll(st, 250);
      ctx.setProjectWorkspaceMessage?.('Assessment batch cancellation requested.');
      return true;
    } catch (err) {
      st.error = err?.message || 'Could not cancel this assessment batch.';
      logFailure('PROJECT_ASSESSMENT_BATCH_CLIENT_CANCEL_FAILED', err, st);
      return false;
    } finally {
      st.canceling = false;
      renderViews();
    }
  }

  function setSelection(projectId, assessmentId, key, value) {
    const st = stateFor(projectId, assessmentId);
    if (key === 'excludedTargetIds' || key === 'excludedCategories') {
      st.selection[key] = new Set(Array.isArray(value) ? value.map(String) : []);
    } else if (key in DEFAULT_SELECTION) {
      st.selection[key] = key === 'includeStandard' ? Boolean(value) : Number(value);
    } else {
      return false;
    }
    st.previewDirty = Boolean(st.preview);
    renderViews();
    return true;
  }

  function newPlan(projectId, assessmentId) {
    const st = stateFor(projectId, assessmentId);
    if (ACTIVE_BATCH_STATUSES.has(String(st.batch?.status || ''))) return false;
    st.planning = true;
    st.preview = null;
    st.previewItems = [];
    st.previewItemsCursor = null;
    st.previewDirty = false;
    st.error = '';
    renderViews();
    return true;
  }

  async function selectBatch(projectId, assessmentId, batchId) {
    const st = stateFor(projectId, assessmentId);
    const nextId = String(batchId || '');
    if (!nextId || nextId === st.selectedBatchId) return false;
    clearPoll(st);
    st.selectedBatchId = nextId;
    st.batch = st.batches.find(item => item?.batch_id === nextId) || null;
    st.batchItems = [];
    st.batchItemsCursor = null;
    st.events = [];
    st.eventCursor = 0;
    st.error = '';
    renderViews();
    return refreshBatch(st, { render: true });
  }

  async function focusBatch(projectId, assessmentId, batchId) {
    const st = stateFor(projectId, assessmentId);
    const nextId = String(batchId || '');
    if (!nextId) return false;
    const loaded = await load(projectId, assessmentId);
    if (!loaded) return false;
    if (st.selectedBatchId === nextId && st.batch) {
      renderViews();
      return true;
    }
    return selectBatch(projectId, assessmentId, nextId);
  }

  async function loadMorePreviewItems(projectId, assessmentId) {
    const st = stateFor(projectId, assessmentId);
    const loaded = await loadPreviewItemPage(st, { append: true });
    renderViews();
    return loaded;
  }

  async function loadMoreBatchItems(projectId, assessmentId) {
    const st = stateFor(projectId, assessmentId);
    const loaded = await loadBatchItemPage(st, { append: true });
    renderViews();
    return loaded;
  }

  function ensure(projectId, assessmentId) {
    const st = stateFor(projectId, assessmentId);
    if (!st.loaded && !st.loading) void load(projectId, assessmentId);
    return st;
  }

  function renderSection(projectId, assessment, detail, { mobile = false } = {}) {
    const assessmentId = String(assessment?.id || '');
    if (!projectId || !assessmentId) return null;
    const st = ensure(projectId, assessmentId);
    st.renderAssessment = assessment;
    st.renderDetail = detail;
    if (st.loaded && !st.batch && assessment?.status !== 'active') return null;
    return renderer.render(projectId, assessment, detail, st, { mobile });
  }

  return { focusBatch, invalidate, load, renderSection, stateFor };
}

export { ACTIVE_BATCH_STATUSES, createProjectAssessmentBatchManager };
