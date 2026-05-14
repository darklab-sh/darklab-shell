// History delete/clear confirmations and shared loading state.

let pendingHistAction = null;

function confirmHistAction(type, id, command, itemType = 'run') {
  pendingHistAction = { type, id, command, itemType };
  const isBulk = type === 'clear';
  const body = isBulk
    ? { text: 'Delete all runs and snapshots?', note: 'This cannot be undone.' }
    : itemType === 'snapshot'
      ? { text: 'Remove this snapshot from history?', note: 'This cannot be undone.' }
      : { text: 'Remove this run from history?', note: 'This cannot be undone.' };
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
  showConfirm({ body, tone: 'warning', actions, refocusOnResolve: false }).then((choice) => {
    if (!choice || choice === 'cancel') {
      pendingHistAction = null;
      return;
    }
    if (choice === 'nonfav') executeHistAction('clear-nonfav');
    else if (choice === 'all') executeHistAction();
    else if (choice === 'one') executeHistAction('delete');
  });
}

function executeHistAction(type) {
  const action  = type || (pendingHistAction && pendingHistAction.type);
  const id      = pendingHistAction && pendingHistAction.id;
  const command = pendingHistAction && pendingHistAction.command;
  const itemType = pendingHistAction && pendingHistAction.itemType;
  pendingHistAction = null;
  if (action === 'delete') {
    const deleteUrl = itemType === 'snapshot' ? `/share/${id}` : `/history/${id}`;
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
