function _historyRelativeTime(startedAt, now = new Date()) {
  return _historyCore.relativeTime(startedAt, now);
}

function _historyMetaKindBadge(kind, label = kind.toUpperCase()) {
  const badge = document.createElement('span');
  const tone = kind === 'run' ? 'badge-tone-green' : 'badge-tone-muted';
  badge.className = `history-entry-kind history-entry-kind-${kind} badge ${tone}`;
  badge.textContent = label;
  return badge;
}

function _historyEntityLabelValues(entity) {
  const labels = entity && Array.isArray(entity.labels) ? entity.labels : [];
  return labels
    .map(label => String(label && typeof label === 'object' ? label.label : label || '').trim())
    .filter(Boolean);
}

function _historyEntityNoteBody(entity) {
  const note = entity && entity.note && typeof entity.note === 'object' ? entity.note : null;
  return note ? String(note.body || '').trim() : '';
}

function _appendHistoryMetadataBadges(parent, entity) {
  if (!parent) return;
  const labels = _historyEntityLabelValues(entity);
  const visibleLabels = labels.slice(0, 3);
  visibleLabels.forEach((label) => {
    const badge = document.createElement('span');
    badge.className = 'history-entry-label-badge badge badge-tone-muted';
    badge.textContent = label;
    badge.title = `label: ${label}`;
    parent.appendChild(badge);
  });
  if (labels.length > visibleLabels.length) {
    const overflow = document.createElement('span');
    overflow.className = 'history-entry-label-badge badge badge-tone-muted';
    overflow.textContent = `+${labels.length - visibleLabels.length}`;
    overflow.title = `${labels.length - visibleLabels.length} more labels`;
    parent.appendChild(overflow);
  }
  if (_historyEntityNoteBody(entity)) {
    const note = document.createElement('span');
    note.className = 'history-entry-note-badge badge badge-tone-cyan';
    note.textContent = 'note';
    note.title = 'note saved';
    parent.appendChild(note);
  }
}

function _historyExitCodeNumber(exitCode) {
  return _historyCore.exitCodeNumber(exitCode);
}

function _historyIsGracefulTerminationExitCode(exitCode) {
  return _historyCore.isGracefulTerminationExitCode(exitCode);
}

function _historyIsFailedExitCode(exitCode) {
  return _historyCore.isFailedExitCode(exitCode);
}

function _historyExitLabel(exitCode) {
  return _historyCore.exitLabel(exitCode);
}

function _historyExitClass(exitCode) {
  return _historyCore.exitClass(exitCode);
}

function _historyCountLabel(count, singular, plural) {
  const numeric = Math.max(0, Number(count || 0));
  return `${numeric.toLocaleString()} ${numeric === 1 ? singular : plural}`;
}

function _historyElapsedSeconds(run) {
  return _historyCore.elapsedSeconds(run);
}

function _historyElapsedLabel(run) {
  return _historyCore.elapsedLabel(run);
}

function _createHistoryActionMenu(run, { includeDelete = false } = {}) {
  const wrap = document.createElement('div');
  wrap.className = 'history-action-menu-wrap save-menu-wrap save-menu-down';
  const trigger = document.createElement('button');
  trigger.className = 'history-action-btn btn btn-secondary btn-compact';
  trigger.type = 'button';
  trigger.dataset.action = 'history-menu';
  trigger.textContent = 'more';
  trigger.setAttribute('aria-label', 'More history actions');
  trigger.setAttribute('aria-expanded', 'false');
  const menu = document.createElement('div');
  menu.className = 'history-action-menu save-menu dropdown-surface';
  const projectLinks = Array.isArray(run?.project_links) ? run.project_links : [];
  const isProjectLinkableRun = String(run?.run_kind || 'external') !== 'builtin';
  const items = [
    ['edit-metadata', 'edit'],
  ];
  if (isProjectLinkableRun) items.push(['open-atlas', 'open in atlas']);
  items.push(
    ['permalink', 'permalink'],
    ['compare', 'compare'],
  );
  if (isProjectLinkableRun && projectLinks.length) {
    items.push(['remove-project', 'remove from project']);
  } else if (isProjectLinkableRun) {
    items.push(['add-active-project', 'add to active project']);
    items.push(['add-project', 'add to project']);
  }
  items.push(['copy-run-id', 'copy run id']);
  if (includeDelete) items.push(['delete', 'delete']);
  items.forEach(([action, label]) => {
    const item = document.createElement('button');
    item.type = 'button';
    item.className = 'dropdown-item dropdown-item-compact';
    item.dataset.action = action;
    item.dataset.runId = String(run.id || '');
    item.textContent = label;
    menu.appendChild(item);
  });
  wrap.append(trigger, menu);
  return wrap;
}

function _createHistoryEntry(run, isStarred, options = {}) {
  const entry = document.createElement('div');
  const selectMode = !!options.selectMode;
  const selectable = options.selectable !== false;
  const selected = !!options.selected;
  entry.className = 'history-entry chrome-row chrome-row-clickable'
    + (isStarred ? ' starred row-accent-amber' : '')
    + (selectMode ? ' history-entry-selecting' : '');
  const exitCls = _historyExitClass(run.exit_code);
  const startedAt = new Date(run.started);
  const now = new Date();
  const validDate = !Number.isNaN(startedAt.getTime());
  const time = startedAt.toLocaleTimeString();
  const showDate = validDate && (
    startedAt.getFullYear() !== now.getFullYear()
    || startedAt.getMonth() !== now.getMonth()
    || startedAt.getDate() !== now.getDate()
  );

  const header = document.createElement('div');
  header.className = 'history-entry-header';

  if (selectMode) {
    const selectionBusy = !!options.selectionBusy;
    const selectLabel = document.createElement('label');
    selectLabel.className = 'history-entry-select-row' + (selectable && !selectionBusy ? '' : ' history-entry-select-disabled');
    if (!selectable) {
      selectLabel.title = 'This run cannot be selected until it has finished.';
    } else if (selectionBusy) {
      selectLabel.title = 'Bulk action is finishing.';
    }
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.dataset.action = 'select-run';
    checkbox.dataset.historySelectItemId = `run:${String(run.id || '')}`;
    checkbox.checked = selected;
    checkbox.disabled = !selectable || selectionBusy;
    checkbox.setAttribute('aria-label', `Select run: ${run.command || run.id || 'run'}`);
    selectLabel.appendChild(checkbox);
    header.appendChild(selectLabel);
  }

  const starBtn = document.createElement('button');
  starBtn.className = 'history-entry-star' + (isStarred ? ' starred' : '');
  starBtn.dataset.action = 'star';
  starBtn.type = 'button';
  const starLabel = isStarred
    ? 'Unstar — stop pinning this command to the top of history'
    : 'Star — keep this command pinned at the top of history';
  starBtn.setAttribute('aria-label', starLabel);
  starBtn.title = starLabel;
  starBtn.textContent = isStarred ? '★' : '☆';
  header.appendChild(starBtn);

  const cmd = document.createElement('div');
  cmd.className = 'history-entry-cmd';
  cmd.textContent = run.command || '';
  header.appendChild(cmd);
  entry.appendChild(header);

  const meta = document.createElement('div');
  meta.className = 'history-entry-meta';
  meta.appendChild(_historyMetaKindBadge('run'));
  if (run.scheduled || run.schedule_id) {
    const scheduledBadge = _historyMetaKindBadge('schedule', 'scheduled');
    scheduledBadge.title = run.schedule_id ? `Schedule ${run.schedule_id}` : 'Scheduled run';
    if (run.schedule_id) {
      scheduledBadge.classList.add('history-entry-kind-action');
      scheduledBadge.dataset.action = 'open-schedule';
      scheduledBadge.dataset.scheduleId = run.schedule_id;
      scheduledBadge.setAttribute('role', 'button');
      scheduledBadge.tabIndex = 0;
      scheduledBadge.setAttribute('aria-label', `Open schedule ${run.schedule_id}`);
    }
    meta.appendChild(scheduledBadge);
  }
  _appendHistoryMetadataBadges(meta, run);
  const timeEl = document.createElement('span');
  timeEl.textContent = time;
  if (validDate) timeEl.title = startedAt.toLocaleString();
  meta.appendChild(timeEl);
  if (showDate) {
    const dateEl = document.createElement('span');
    dateEl.className = 'history-entry-date';
    dateEl.textContent = startedAt.toLocaleDateString();
    meta.appendChild(dateEl);
  }
  const elapsedLabel = _historyElapsedLabel(run);
  if (elapsedLabel) {
    const elapsedEl = document.createElement('span');
    elapsedEl.className = 'history-entry-elapsed';
    elapsedEl.textContent = elapsedLabel;
    meta.appendChild(elapsedEl);
  }
  const artifactCount = Number(run.artifact_count || (Array.isArray(run.artifacts) ? run.artifacts.length : 0));
  if (Number.isFinite(artifactCount) && artifactCount > 0) {
    const artifactEl = document.createElement('span');
    artifactEl.className = 'history-entry-artifacts';
    artifactEl.textContent = artifactCount === 1 ? '1 artifact' : `${artifactCount} artifacts`;
    meta.appendChild(artifactEl);
  }
  const exitEl = document.createElement('span');
  exitEl.className = exitCls;
  exitEl.textContent = _historyExitLabel(run.exit_code);
  meta.appendChild(exitEl);
  entry.appendChild(meta);

  const isExternalRun = String(run.run_kind || 'external') !== 'builtin';
  if (isExternalRun) {
    const atlasEntityCount = Number(run.atlas_entity_count || 0);
    const atlasFindingCount = Number(run.atlas_finding_count || 0);
    if (atlasEntityCount > 0 || atlasFindingCount > 0) {
      const atlasMeta = document.createElement('div');
      atlasMeta.className = 'history-entry-atlas';
      atlasMeta.textContent = `Atlas: ${_historyCountLabel(atlasEntityCount, 'entity', 'entities')} · ${_historyCountLabel(atlasFindingCount, 'finding', 'findings')}`;
      entry.appendChild(atlasMeta);
    }
  }

  const actions = document.createElement('div');
  actions.className = 'history-actions';
  const isMobile = typeof useMobileTerminalViewportMode === 'function' && useMobileTerminalViewportMode();

  const copyCommandBtn = document.createElement('button');
  copyCommandBtn.className = 'history-action-btn btn btn-secondary btn-compact';
  copyCommandBtn.type = 'button';
  copyCommandBtn.dataset.action = 'copy-command';
  copyCommandBtn.textContent = 'copy command';
  actions.appendChild(copyCommandBtn);

  const restoreBtn = document.createElement('button');
  restoreBtn.className = 'history-action-btn btn btn-secondary btn-compact';
  restoreBtn.type = 'button';
  restoreBtn.dataset.action = 'restore';
  restoreBtn.textContent = 'restore';
  actions.appendChild(restoreBtn);

  if (!isMobile) {
    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'history-action-btn btn btn-secondary btn-compact';
    deleteBtn.type = 'button';
    deleteBtn.dataset.action = 'delete';
    deleteBtn.textContent = 'delete';
    actions.appendChild(deleteBtn);
  }

  actions.appendChild(_createHistoryActionMenu(run, { includeDelete: isMobile }));

  entry.appendChild(actions);
  return entry;
}

function _createSnapshotHistoryEntry(snapshot, options = {}) {
  const entry = document.createElement('div');
  const selectMode = !!options.selectMode;
  const selectable = options.selectable !== false;
  const selected = !!options.selected;
  entry.className = 'history-entry history-entry-snapshot chrome-row chrome-row-clickable'
    + (selectMode ? ' history-entry-selecting' : '');

  const header = document.createElement('div');
  header.className = 'history-entry-header';

  if (selectMode) {
    const selectionBusy = !!options.selectionBusy;
    const selectLabel = document.createElement('label');
    selectLabel.className = 'history-entry-select-row' + (selectable && !selectionBusy ? '' : ' history-entry-select-disabled');
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.dataset.action = 'select-run';
    checkbox.dataset.historySelectItemId = `snapshot:${String(snapshot.id || '')}`;
    checkbox.checked = selected;
    checkbox.disabled = !selectable || selectionBusy;
    checkbox.setAttribute('aria-label', `Select snapshot: ${snapshot.label || snapshot.id || 'snapshot'}`);
    selectLabel.appendChild(checkbox);
    header.appendChild(selectLabel);
  }

  const title = document.createElement('div');
  title.className = 'history-entry-cmd';
  title.textContent = snapshot.label || 'snapshot';
  header.appendChild(title);
  entry.appendChild(header);

  const meta = document.createElement('div');
  meta.className = 'history-entry-meta';
  meta.appendChild(_historyMetaKindBadge('snapshot'));
  _appendHistoryMetadataBadges(meta, snapshot);
  const createdAt = new Date(snapshot.created);
  const timeEl = document.createElement('span');
  timeEl.textContent = Number.isNaN(createdAt.getTime())
    ? ''
    : _historyRelativeTime(createdAt);
  if (!Number.isNaN(createdAt.getTime())) timeEl.title = createdAt.toLocaleString();
  meta.appendChild(timeEl);
  entry.appendChild(meta);

  const actions = document.createElement('div');
  actions.className = 'history-actions';

  const openBtn = document.createElement('button');
  openBtn.className = 'history-action-btn btn btn-secondary btn-compact';
  openBtn.type = 'button';
  openBtn.dataset.action = 'open';
  openBtn.textContent = 'open';
  actions.appendChild(openBtn);

  const linkBtn = document.createElement('button');
  linkBtn.className = 'history-action-btn btn btn-secondary btn-compact';
  linkBtn.type = 'button';
  linkBtn.dataset.action = 'link';
  linkBtn.textContent = 'copy link';
  actions.appendChild(linkBtn);

  const editBtn = document.createElement('button');
  editBtn.className = 'history-action-btn btn btn-secondary btn-compact';
  editBtn.type = 'button';
  editBtn.dataset.action = 'edit-metadata';
  editBtn.textContent = 'edit';
  actions.appendChild(editBtn);

  const deleteBtn = document.createElement('button');
  deleteBtn.className = 'history-action-btn btn btn-secondary btn-compact';
  deleteBtn.type = 'button';
  deleteBtn.dataset.action = 'delete';
  deleteBtn.textContent = 'delete';
  actions.appendChild(deleteBtn);

  entry.appendChild(actions);
  return entry;
}

function _historyActionKeepsPanelOpen(action) {
  if (action === 'star') return true;
  if (action === 'compare') return true;
  if (action === 'edit-metadata') return true;
  const mobileMode = typeof useMobileTerminalViewportMode === 'function' && useMobileTerminalViewportMode();
  if (!mobileMode) return false;
  return action === 'permalink';
}

function _historyEditEntityMetadata(entityType, entity) {
  const editor = typeof globalThis !== 'undefined' ? globalThis.openEntityMetadataEditor : null;
  if (typeof editor !== 'function') {
    showToast('Metadata editor is not available', 'error');
    return;
  }
  editor(entityType, entity, {
    onSaved: async () => {
      refreshHistoryPanel();
      showToast('Metadata saved');
    },
  });
}
