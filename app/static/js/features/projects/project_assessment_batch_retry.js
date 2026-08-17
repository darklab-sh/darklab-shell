// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Current-state retry preview helpers shared by the batch manager and renderer.

function hasRetryableBatchProgress(batch) {
  const progress = batch?.progress || {};
  return ['failed', 'unavailable', 'canceled', 'skipped', 'could_not_cancel']
    .some(key => Number(progress?.[key] || 0) > 0);
}

async function createAssessmentBatchRetryPreview(st, dependencies) {
  const {
    loadPreviewItemPage,
    logFailure,
    renderViews,
    requestJson,
    selectionPayload,
  } = dependencies;
  const sourceBatchId = String(st?.selectedBatchId || '');
  if (!sourceBatchId || st.previewing || st.starting) return false;
  st.previewing = true;
  st.error = '';
  renderViews();
  try {
    const payload = await requestJson(
      `/projects/${encodeURIComponent(st.projectId)}/assessment-batches/${encodeURIComponent(sourceBatchId)}/retry-previews`,
      { method: 'POST', body: JSON.stringify(selectionPayload(st)) },
      'Could not preview failed or unfinished assessment commands.',
    );
    st.preview = payload?.preview || null;
    st.previewItems = [];
    st.previewItemsCursor = null;
    st.previewDirty = false;
    st.planning = true;
    await loadPreviewItemPage(st);
    return true;
  } catch (err) {
    st.error = err?.message || 'Could not preview failed or unfinished assessment commands.';
    logFailure('PROJECT_ASSESSMENT_BATCH_CLIENT_RETRY_PREVIEW_FAILED', err, st, {
      source_batch_id: sourceBatchId,
    });
    return false;
  } finally {
    st.previewing = false;
    renderViews();
  }
}

export { createAssessmentBatchRetryPreview, hasRetryableBatchProgress };
