function cleanupNumber(value) {
  return Math.max(0, Number(value || 0));
}

function cleanupCountLabel(count, singular, plural) {
  const numeric = cleanupNumber(count);
  return `${numeric.toLocaleString()} ${numeric === 1 ? singular : plural}`;
}

function cleanupBucket(summary, bucket) {
  return (summary && summary.buckets && summary.buckets[bucket]) || {};
}

function cleanupBucketHasKind(summary, bucket, kind) {
  return Object.prototype.hasOwnProperty.call(cleanupBucket(summary, bucket), kind);
}

function cleanupBucketHasCounts(summary, bucket) {
  return cleanupBucketHasKind(summary, bucket, 'entities') || cleanupBucketHasKind(summary, bucket, 'findings');
}

function cleanupBucketCountOrFallback(summary, bucket, kind, fallback) {
  return cleanupBucketHasKind(summary, bucket, kind)
    ? cleanupNumber(cleanupBucket(summary, bucket)[kind])
    : cleanupNumber(fallback);
}

function cleanupReasonLabels(summary, bucket) {
  const seen = new Set();
  return (Array.isArray(summary?.reasons) ? summary.reasons : [])
    .filter(reason => String(reason?.bucket || '') === bucket && cleanupNumber(reason?.total) > 0)
    .map(reason => String(reason?.label || '').trim())
    .filter(label => {
      if (!label || seen.has(label)) return false;
      seen.add(label);
      return true;
    });
}

function cleanupReasonSentence(summary, bucket, fallback) {
  const labels = cleanupReasonLabels(summary, bucket);
  if (!labels.length) return fallback || '';
  if (labels.length === 1) return `Reason: ${labels[0]}.`;
  return `Reasons: ${labels.slice(0, 4).join(', ')}${labels.length > 4 ? ', and more' : ''}.`;
}

function cleanupItemCount(summary, bucket, fallbackEntities, fallbackFindings) {
  const entities = cleanupBucketCountOrFallback(summary, bucket, 'entities', fallbackEntities);
  const findings = cleanupBucketCountOrFallback(summary, bucket, 'findings', fallbackFindings);
  return { entities, findings, total: entities + findings };
}

function cleanupItemsLabel({ entities, findings }, { includeZero = true, kept = false } = {}) {
  const parts = [];
  if (includeZero || findings > 0) {
    const label = cleanupCountLabel(findings, 'finding', 'findings');
    parts.push(kept && findings > 0 ? `${label} kept by default` : label);
  }
  if (includeZero || entities > 0) {
    const label = cleanupCountLabel(entities, 'entity', 'entities');
    parts.push(kept && entities > 0 ? `${label} kept by default` : label);
  }
  if (!parts.length) return '';
  if (parts.length === 1) return parts[0];
  return `${parts[0]} and ${parts[1]}`;
}

function setCleanupNodeHidden(node, hidden) {
  if (!node) return;
  node.classList.toggle('u-hidden', hidden);
  node.hidden = hidden;
}

function cleanupMaybeSetNodeHidden(node, hidden, setNodeHidden) {
  if (typeof setNodeHidden === 'function') {
    setNodeHidden(node, hidden);
    return;
  }
  setCleanupNodeHidden(node, hidden);
}

function atlasRunCleanupCopy(cleanup) {
  const summary = cleanup?.cleanup_reasons || {};
  const disposable = cleanupItemCount(summary, 'disposable', cleanup?.entities, cleanup?.findings);
  const kept = cleanupItemCount(summary, 'kept_by_default', cleanup?.curated_entities, cleanup?.curated_findings);
  const notEligible = cleanupItemCount(summary, 'not_eligible');
  const hasDisposableSummary = cleanupBucketHasCounts(summary, 'disposable');
  const hasKeptSummary = cleanupBucketHasCounts(summary, 'kept_by_default');
  return {
    disposable,
    kept,
    notEligible,
    hasDisposable: hasDisposableSummary ? disposable.total > 0 : !!cleanup?.has_cleanup || disposable.total > 0,
    hasKept: hasKeptSummary ? kept.total > 0 : cleanupNumber(cleanup?.curated_total) > 0 || kept.total > 0,
    disposableLabel: `Also remove ${cleanupItemsLabel(disposable)} from Atlas`,
    disposableNote: [
      'These are disposable Atlas items only sourced by this run.',
      cleanupReasonSentence(summary, 'disposable', ''),
    ].filter(Boolean).join(' '),
    keptLabel: 'Also delete single-source Atlas items kept by default',
    keptNote: [
      `${cleanupItemsLabel(kept, { kept: true })} will be kept unless this is checked.`,
      cleanupReasonSentence(summary, 'kept_by_default', 'Kept by default because they are Project-linked, reviewed, labeled, or noted.'),
    ].filter(Boolean).join(' '),
    notEligibleNote: notEligible.total > 0
      ? [
        `${cleanupItemsLabel(notEligible, { includeZero: false })} not eligible for this cleanup.`,
        cleanupReasonSentence(summary, 'not_eligible', ''),
      ].filter(Boolean).join(' ')
      : '',
  };
}

function applyProjectRunEntityUnlinkPreview(control, preview) {
  if (!control) return;
  const summary = preview?.cleanup_reasons || {};
  const runCount = cleanupNumber(preview?.run_count);
  const disposableItems = cleanupItemCount(summary, 'disposable', preview?.removable);
  const keptItems = cleanupItemCount(summary, 'kept_by_default', preview?.curated ?? preview?.kept_curated);
  const removable = disposableItems.entities;
  const kept = keptItems.entities;
  const runFindings = cleanupNumber(preview?.run_findings);
  const removableFindings = cleanupNumber(preview?.removable_findings);
  const keptFindings = cleanupNumber(preview?.curated_findings ?? preview?.kept_curated_findings);
  const notEligible = cleanupItemCount(summary, 'not_eligible');
  const hide = removable <= 0 && kept <= 0 && runFindings <= 0 && notEligible.total <= 0;
  const setNodeHidden = control.setNodeHidden;

  cleanupMaybeSetNodeHidden(control.wrap, hide, setNodeHidden);
  control.checkbox.checked = false;
  control.checkbox.disabled = removable <= 0;
  control.curatedCheckbox.checked = false;
  control.curatedCheckbox.disabled = kept <= 0;

  cleanupMaybeSetNodeHidden(control.runFindingsNote, runFindings <= 0, setNodeHidden);
  control.runFindingsNote.textContent = runFindings > 0
    ? `Removing the run link will remove ${cleanupCountLabel(runFindings, 'finding', 'findings')} from this project's Findings tab.`
    : '';

  cleanupMaybeSetNodeHidden(control.label, removable <= 0, setNodeHidden);
  control.text.textContent = removable > 0
    ? 'Also remove disposable same-run Atlas entities from this project'
    : '';
  cleanupMaybeSetNodeHidden(control.note, removable <= 0, setNodeHidden);
  control.note.textContent = removable > 0
    ? [
      `This will unlink ${cleanupCountLabel(removable, 'entity', 'entities')} found only in ${runCount > 1 ? 'these runs' : 'this run'}.`,
      removableFindings > 0
        ? `${cleanupCountLabel(removableFindings, 'related finding', 'related findings')} will no longer appear in this project.`
        : '',
      cleanupReasonSentence(summary, 'disposable', ''),
    ].filter(Boolean).join(' ')
    : '';

  cleanupMaybeSetNodeHidden(control.curatedLabel, kept <= 0, setNodeHidden);
  control.curatedText.textContent = kept > 0
    ? `${removable > 0 ? 'Also remove' : 'Remove'} same-run Atlas entities kept by default from this project`
    : '';
  cleanupMaybeSetNodeHidden(control.curatedNote, kept <= 0, setNodeHidden);
  control.curatedNote.textContent = kept > 0
    ? [
      `${cleanupCountLabel(kept, 'entity', 'entities')} kept by default`,
      keptFindings > 0 ? `and ${cleanupCountLabel(keptFindings, 'related finding', 'related findings')}` : '',
      'will stay in this project unless this is checked.',
      cleanupReasonSentence(summary, 'kept_by_default', 'Kept by default because they are linked elsewhere, labeled, noted, reviewed, or have custom Project link metadata.'),
    ].filter(Boolean).join(' ')
    : '';

  if (!control.notEligibleNote) return;
  cleanupMaybeSetNodeHidden(control.notEligibleNote, notEligible.total <= 0, setNodeHidden);
  control.notEligibleNote.textContent = notEligible.total > 0
    ? [
      `${cleanupItemsLabel(notEligible, { includeZero: false })} not eligible for this cleanup.`,
      cleanupReasonSentence(summary, 'not_eligible', ''),
    ].filter(Boolean).join(' ')
    : '';
}

export {
  applyProjectRunEntityUnlinkPreview,
  atlasRunCleanupCopy,
  setCleanupNodeHidden,
};
