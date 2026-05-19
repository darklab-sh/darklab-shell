// History delete/clear confirmations and shared loading state.

let pendingHistAction = null;

function _historyCleanupLabel(cleanup) {
  const entities = Number(cleanup?.entities || 0);
  const findings = Number(cleanup?.findings || 0);
  return `${findings.toLocaleString()} ${findings === 1 ? 'finding' : 'findings'} and `
    + `${entities.toLocaleString()} ${entities === 1 ? 'entity' : 'entities'}`;
}

function _historyCuratedCleanupLabel(cleanup) {
  const entities = Number(cleanup?.curated_entities || 0);
  const findings = Number(cleanup?.curated_findings || 0);
  return `${findings.toLocaleString()} curated ${findings === 1 ? 'finding' : 'findings'} and `
    + `${entities.toLocaleString()} curated ${entities === 1 ? 'entity' : 'entities'}`;
}

function _buildHistoryAtlasCleanupContent(cleanup) {
  const curated = Number(cleanup?.curated_total || 0);
  if (!cleanup?.has_cleanup && curated <= 0) return null;
  const wrap = document.createElement('div');
  wrap.className = 'modal-inline-field';
  const fieldset = document.createElement('div');
  fieldset.className = 'form-fieldset';
  if (cleanup?.has_cleanup) {
    const label = document.createElement('label');
    label.className = 'form-check';
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = true;
    checkbox.dataset.historyAtlasCleanup = '1';
    const text = document.createElement('span');
    text.textContent = `Also remove ${_historyCleanupLabel(cleanup)} from Atlas`;
    label.append(checkbox, text);
    const note = document.createElement('div');
    note.className = 'history-bulk-note';
    note.textContent = 'These are disposable Atlas items only sourced by this run.';
    fieldset.append(label, note);
  }
  if (curated > 0) {
    const curatedLabel = document.createElement('label');
    curatedLabel.className = 'form-check';
    const curatedCheckbox = document.createElement('input');
    curatedCheckbox.type = 'checkbox';
    curatedCheckbox.checked = false;
    curatedCheckbox.dataset.historyAtlasCleanupCurated = '1';
    const curatedText = document.createElement('span');
    curatedText.textContent = 'Also delete curated single-source Atlas items';
    curatedLabel.append(curatedCheckbox, curatedText);
    const curatedNote = document.createElement('div');
    curatedNote.className = 'history-bulk-note';
    curatedNote.textContent = `${_historyCuratedCleanupLabel(cleanup)} will be kept unless this is checked. Curated means project-linked, project-visible, reviewed, labeled, or noted.`;
    fieldset.append(curatedLabel, curatedNote);
  }
  wrap.appendChild(fieldset);
  return wrap;
}

async function _loadHistoryAtlasCleanup(runId) {
  try {
    const resp = await apiFetch(`/history/${encodeURIComponent(runId)}/atlas-cleanup-preview`, { cache: 'no-store' });
    if (!resp.ok) return null;
    const data = await resp.json().catch(() => ({}));
    return data.cleanup || null;
  } catch (_) {
    return null;
  }
}

function confirmHistAction(type, id, command, itemType = 'run') {
  pendingHistAction = { type, id, command, itemType };
  const runDelete = type === 'delete' && itemType !== 'snapshot' && id;
  const isBulk = type === 'clear';
  const buildBody = (cleanup) => (isBulk
    ? { text: 'Delete all runs and snapshots?', note: 'This cannot be undone.' }
    : itemType === 'snapshot'
      ? { text: 'Remove this snapshot from history?', note: 'This cannot be undone.' }
      : {
          text: 'Remove this run from history?',
          note: cleanup?.has_cleanup
            ? 'The run transcript will be removed. Atlas cleanup is optional.'
            : 'This cannot be undone.',
        });
  const actions = isBulk
    ? [
        { id: 'cancel', label: 'Cancel', role: 'cancel' },
        { id: 'nonfav', label: 'Delete Non-Favorites', role: 'secondary', tone: 'warning' },
        { id: 'all',    label: 'Delete all', role: 'destructive', tone: 'warning' },
      ]
    : [
        { id: 'cancel', label: 'Cancel', role: 'cancel' },
        { id: 'one',    label: 'Delete', role: 'destructive', tone: 'warning' },
      ];
  const showDeleteConfirm = (cleanup) => {
    const content = runDelete ? _buildHistoryAtlasCleanupContent(cleanup) : null;
    return showConfirm({
      body: buildBody(cleanup),
      content,
      tone: 'warning',
      actions,
      refocusOnResolve: false,
    }).then((choice) => {
      if (!choice || choice === 'cancel') {
        pendingHistAction = null;
        return;
      }
      if (pendingHistAction && content) {
        pendingHistAction.pruneCuratedAtlas = !!content.querySelector('[data-history-atlas-cleanup-curated]')?.checked;
        pendingHistAction.pruneAtlas = !!content.querySelector('[data-history-atlas-cleanup]')?.checked
          || pendingHistAction.pruneCuratedAtlas;
      }
      if (choice === 'nonfav') executeHistAction('clear-nonfav');
      else if (choice === 'all') executeHistAction();
      else if (choice === 'one') executeHistAction('delete');
    });
  };
  if (runDelete) {
    _loadHistoryAtlasCleanup(id).then(showDeleteConfirm);
  } else {
    showDeleteConfirm(null);
  }
}

function executeHistAction(type) {
  const action  = type || (pendingHistAction && pendingHistAction.type);
  const id      = pendingHistAction && pendingHistAction.id;
  const command = pendingHistAction && pendingHistAction.command;
  const itemType = pendingHistAction && pendingHistAction.itemType;
  const pruneAtlas = !!(pendingHistAction && pendingHistAction.pruneAtlas);
  const pruneCuratedAtlas = !!(pendingHistAction && pendingHistAction.pruneCuratedAtlas);
  pendingHistAction = null;
  if (action === 'delete') {
    const params = new URLSearchParams();
    if (pruneAtlas) params.set('prune_atlas', '1');
    if (pruneCuratedAtlas) params.set('prune_curated_atlas', '1');
    const query = params.toString();
    const deleteUrl = itemType === 'snapshot'
      ? `/share/${id}`
      : `/history/${id}${query ? `?${query}` : ''}`;
    apiFetch(deleteUrl, { method: 'DELETE' }).then(() => {
      if (itemType === 'snapshot') {
        refreshHistoryPanel();
        return;
      }
      const s = _getStarred();
      if (s.has(command)) {
        s.delete(command);
        _saveStarred(s);
        apiFetch('/session/starred', {
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ command }),
        }).catch(() => {});
      }
      cmdHistory = cmdHistory.filter(c => c !== command);
      recentPreviewHistory = recentPreviewHistory.filter(c => c !== command);
      renderHistory();
      refreshHistoryPanel();
    }).catch(() => showToast('Failed to delete run'));
  } else if (action === 'clear-nonfav') {
    apiFetch('/history?type=runs')
      .then(r => r.json())
      .then(data => {
        const starred   = _getStarred();
        const toDelete  = data.runs.filter(r => !starred.has(r.command));
        const deleteCmds = new Set(toDelete.map(r => r.command));
        cmdHistory = cmdHistory.filter(c => !deleteCmds.has(c));
        recentPreviewHistory = recentPreviewHistory.filter(c => !deleteCmds.has(c));
        renderHistory();
        return Promise.all(toDelete.map(r => apiFetch(`/history/${r.id}`, { method: 'DELETE' })));
      })
      .then(() => refreshHistoryPanel())
      .catch(() => showToast('Failed to clear history'));
  } else {
    apiFetch('/history', { method: 'DELETE' }).then(() => {
      _saveStarred(new Set());
      apiFetch('/session/starred', { method: 'DELETE' }).catch(() => {});
      cmdHistory = [];
      recentPreviewHistory = [];
      renderHistory();
      refreshHistoryPanel();
    }).catch(() => showToast('Failed to clear history'));
  }
}

function _setHistoryLoadState(loading) {
  if (!historyLoadOverlay) return;
  if (loading) showHistoryLoadOverlay();
  else hideHistoryLoadOverlay();
}
