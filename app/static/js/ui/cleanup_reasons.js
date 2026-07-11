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

function cleanupReasonSamples(summary) {
  const samples = summary?.samples || {};
  const groups = [];
  ['kept_by_default', 'not_eligible'].forEach(bucket => {
    ['entities', 'findings'].forEach(kind => {
      const group = samples?.[bucket]?.[kind] || {};
      const items = Array.isArray(group.items) ? group.items : [];
      const omitted = cleanupNumber(group.omitted);
      if (items.length || omitted > 0) groups.push({ bucket, kind, items, omitted });
    });
  });
  return groups;
}

function cleanupSampleBucketLabel(bucket) {
  if (bucket === 'kept_by_default') return 'Kept by default';
  if (bucket === 'not_eligible') return 'Not eligible';
  return 'Cleanup';
}

function cleanupSampleKindLabel(kind) {
  return kind === 'findings' ? 'findings' : 'entities';
}

function cleanupSampleDisplayValue(sample) {
  const value = String(sample?.display_value || '').trim();
  return value || (sample?.kind === 'findings' ? 'Untitled finding' : 'Unknown entity');
}

function appendCleanupSampleBadge(row, label, extraClass = '') {
  const text = String(label || '').trim();
  if (!text) return;
  const badge = document.createElement('span');
  badge.className = `badge badge-tone-muted cleanup-sample-badge${extraClass ? ` ${extraClass}` : ''}`;
  badge.textContent = text;
  row.appendChild(badge);
}

let cleanupSamplePanelIdCounter = 0;

function nextCleanupSamplePanelId() {
  cleanupSamplePanelIdCounter += 1;
  return `cleanup-samples-${cleanupSamplePanelIdCounter}`;
}

function cleanupSampleDetails(summary, { bindDisclosure, className = '' } = {}) {
  const groups = cleanupReasonSamples(summary);
  if (!groups.length) return null;
  if (typeof bindDisclosure !== 'function') {
    throw new Error('cleanupSampleDetails requires bindDisclosure');
  }
  const wrap = document.createElement('div');
  wrap.className = `cleanup-sample-details${className ? ` ${className}` : ''}`;
  wrap.dataset.cleanupSamples = '1';
  const trigger = document.createElement('button');
  trigger.type = 'button';
  trigger.className = 'btn btn-ghost btn-compact cleanup-sample-toggle';
  const glyph = document.createElement('span');
  glyph.className = 'cleanup-sample-toggle-glyph';
  const label = document.createElement('span');
  label.textContent = 'Sample rows';
  trigger.append(glyph, label);
  const panel = document.createElement('div');
  panel.className = 'cleanup-sample-panel nice-scroll u-hidden';
  panel.id = nextCleanupSamplePanelId();
  trigger.setAttribute('aria-controls', panel.id);

  groups.forEach(group => {
    const groupWrap = document.createElement('div');
    groupWrap.className = 'cleanup-sample-group';
    const title = document.createElement('div');
    title.className = 'cleanup-sample-group-title';
    title.textContent = `${cleanupSampleBucketLabel(group.bucket)} ${cleanupSampleKindLabel(group.kind)}`;
    groupWrap.appendChild(title);
    const list = document.createElement('ul');
    list.className = 'cleanup-sample-list';
    group.items.forEach(sample => {
      const item = document.createElement('li');
      item.className = 'cleanup-sample-item';
      const value = document.createElement('span');
      value.className = 'cleanup-sample-value';
      value.textContent = cleanupSampleDisplayValue(sample);
      item.appendChild(value);
      if (sample?.item_type) appendCleanupSampleBadge(item, sample.item_type, 'cleanup-sample-type');
      (Array.isArray(sample?.reasons) ? sample.reasons : []).forEach(reason => {
        appendCleanupSampleBadge(item, reason?.label);
      });
      list.appendChild(item);
    });
    if (group.omitted > 0) {
      const omitted = document.createElement('li');
      omitted.className = 'cleanup-sample-omitted';
      omitted.textContent = `and ${group.omitted.toLocaleString()} more`;
      list.appendChild(omitted);
    }
    groupWrap.appendChild(list);
    panel.appendChild(groupWrap);
  });

  function update(open) {
    glyph.textContent = open ? '▾' : '▸';
  }
  update(false);
  bindDisclosure(trigger, {
    panel,
    hiddenClass: 'u-hidden',
    openClass: null,
    initialOpen: false,
    onToggle: update,
  });
  wrap.append(trigger, panel);
  return wrap;
}

function syncCleanupSampleDetails(slot, summary, options = {}) {
  if (!slot) return;
  slot.replaceChildren();
  const details = cleanupSampleDetails(summary, options);
  if (details) slot.appendChild(details);
  setCleanupNodeHidden(slot, !details);
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
  syncCleanupSampleDetails(control.sampleDetails, summary, {
    bindDisclosure: control.bindDisclosure,
  });
}

export {
  applyProjectRunEntityUnlinkPreview,
  atlasRunCleanupCopy,
  cleanupSampleDetails,
  setCleanupNodeHidden,
  syncCleanupSampleDetails,
};
