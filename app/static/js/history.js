// ── Shared history/permalink logic ──
// Stored in localStorage as a JSON array of command strings.
// Stars float starred items to the top of both the chips row and history panel.

function _getStarred() {
  try { return new Set(JSON.parse(localStorage.getItem('starred') || '[]')); }
  catch { return new Set(); }
}
function _saveStarred(set) {
  localStorage.setItem('starred', JSON.stringify([...set]));
}
function _toggleStar(cmd) {
  const s = _getStarred();
  if (s.has(cmd)) s.delete(cmd); else s.add(cmd);
  _saveStarred(s);
}


// ── Command history chips ──

function resetCmdHistoryNav() {
  _cmdHistoryNavIndex = -1;
  _cmdHistoryNavDraft = '';
}

function navigateCmdHistory(delta) {
  if (!cmdHistory.length) return false;

  if (delta > 0) {
    if (_cmdHistoryNavIndex === -1) {
      _cmdHistoryNavDraft = cmdInput.value;
      _cmdHistoryNavIndex = 0;
    } else if (_cmdHistoryNavIndex < cmdHistory.length - 1) {
      _cmdHistoryNavIndex++;
    } else {
      return true;
    }
    _suspendCmdHistoryNavReset = true;
    setComposerValue(cmdHistory[_cmdHistoryNavIndex]);
    return true;
  }

  if (delta < 0) {
    if (_cmdHistoryNavIndex === -1) return false;
    if (_cmdHistoryNavIndex > 0) {
      _cmdHistoryNavIndex--;
      _suspendCmdHistoryNavReset = true;
      setComposerValue(cmdHistory[_cmdHistoryNavIndex]);
      return true;
    }
    _suspendCmdHistoryNavReset = true;
    setComposerValue(_cmdHistoryNavDraft);
    resetCmdHistoryNav();
    return true;
  }

  return false;
}

function addToHistory(cmd) {
  cmdHistory = [cmd, ...cmdHistory.filter(c => c !== cmd)].slice(0, APP_CONFIG.recent_commands_limit);
  resetCmdHistoryNav();
  renderHistory();
}

function hydrateCmdHistory(runs) {
  const items = Array.isArray(runs) ? runs : [];
  const seen = new Set();
  cmdHistory = items
    .map(run => run && typeof run.command === 'string' ? run.command : '')
    .filter(cmd => {
      if (!cmd || seen.has(cmd)) return false;
      seen.add(cmd);
      return true;
    })
    .slice(0, APP_CONFIG.recent_commands_limit);
  resetCmdHistoryNav();
  renderHistory();
}

function renderHistory() {
  while (histRow.children.length > 1) histRow.removeChild(histRow.lastChild);
  if (!cmdHistory.length) { hideHistoryRow(); return; }
  showHistoryRow();

  const starred = _getStarred();
  // Starred commands first, then remaining in recency order
  const sorted = [
    ...cmdHistory.filter(c => starred.has(c)),
    ...cmdHistory.filter(c => !starred.has(c)),
  ];
  const visible = (typeof useMobileTerminalViewportMode === 'function' && useMobileTerminalViewportMode())
    ? sorted.slice(0, 3)
    : sorted;

  visible.forEach(cmd => {
    const isStarred = starred.has(cmd);
    const chip = document.createElement('button');
    chip.className = 'hist-chip' + (isStarred ? ' starred' : '');
    chip.title = cmd;

    const starEl = document.createElement('span');
    starEl.className = 'chip-star';
    starEl.textContent = isStarred ? '★' : '☆';
    starEl.title = isStarred ? 'Unstar' : 'Star';
    starEl.addEventListener('click', e => {
      e.stopPropagation();
      _toggleStar(cmd);
      renderHistory();
    });

    const textEl = document.createElement('span');
    textEl.textContent = cmd;

    chip.appendChild(starEl);
    chip.appendChild(textEl);
    chip.addEventListener('click', () => {
      setComposerValue(cmd, cmd.length, cmd.length);
      const targetInput = (typeof getVisibleComposerInput === 'function')
        ? getVisibleComposerInput()
        : (typeof getVisibleMobileComposerInput === 'function' ? getVisibleMobileComposerInput() : cmdInput);
      if (targetInput && typeof targetInput.focus === 'function') targetInput.focus();
      resetCmdHistoryNav();
    });
    histRow.appendChild(chip);
  });

  if (visible.length < sorted.length) {
    const overflowChip = document.createElement('button');
    overflowChip.className = 'hist-chip hist-chip-overflow';
    overflowChip.textContent = `+${sorted.length - visible.length} more`;
    overflowChip.title = 'Open history panel';
    overflowChip.addEventListener('click', () => {
      if (!historyPanel) return;
      showHistoryPanel();
      if (typeof refreshHistoryPanel === 'function') refreshHistoryPanel();
    });
    histRow.appendChild(overflowChip);
  }
}


// ── Run history panel ──
let pendingHistAction = null;

function confirmHistAction(type, id, command) {
  pendingHistAction = { type, id, command };
  const msg      = document.getElementById('hist-del-msg');
  const confirm  = document.getElementById('hist-del-confirm');
  if (type === 'clear') {
    msg.innerHTML = 'Clear run history?<br><span style="color:var(--muted);font-size:11px">This cannot be undone.</span>';
    showHistoryDeleteNonfav();
    confirm.textContent   = 'Delete all';
  } else {
    msg.innerHTML = 'Remove this run from history?<br><span style="color:var(--muted);font-size:11px">This cannot be undone.</span>';
    hideHistoryDeleteNonfav();
    confirm.textContent   = 'Delete';
  }
  showHistoryDeleteOverlay();
}

function executeHistAction(type) {
  const action  = type || (pendingHistAction && pendingHistAction.type);
  const id      = pendingHistAction && pendingHistAction.id;
  const command = pendingHistAction && pendingHistAction.command;
  pendingHistAction = null;
  if (action === 'delete') {
    apiFetch(`/history/${id}`, { method: 'DELETE' }).then(() => {
      // Remove from starred set and chips — deleted history should not stay pinned
      const s = _getStarred();
      s.delete(command);
      _saveStarred(s);
      cmdHistory = cmdHistory.filter(c => c !== command);
      renderHistory();
      refreshHistoryPanel();
    }).catch(() => showToast('Failed to delete run'));
  } else if (action === 'clear-nonfav') {
    apiFetch('/history')
      .then(r => r.json())
      .then(data => {
        const starred   = _getStarred();
        const toDelete  = data.runs.filter(r => !starred.has(r.command));
        const deleteCmds = new Set(toDelete.map(r => r.command));
        // Remove deleted commands from chips; starred commands remain
        cmdHistory = cmdHistory.filter(c => !deleteCmds.has(c));
        renderHistory();
        return Promise.all(toDelete.map(r => apiFetch(`/history/${r.id}`, { method: 'DELETE' })));
      })
      .then(() => refreshHistoryPanel())
      .catch(() => showToast('Failed to clear history'));
  } else {
    apiFetch('/history', { method: 'DELETE' }).then(() => {
      // Wipe all starred state and chips — nothing left in history to pin
      _saveStarred(new Set());
      cmdHistory = [];
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

function refreshHistoryPanel() {
  apiFetch('/history').then(r => r.json()).then(data => {
    historyList.innerHTML = '';
    if (!data.runs.length) {
      historyList.innerHTML = '<div style="padding:16px;color:var(--muted);font-size:12px">No runs yet.</div>';
      return;
    }

    const starred = _getStarred();
    // Starred runs first, then by recency (server already sorts by recency)
    const sorted = [
      ...data.runs.filter(r => starred.has(r.command)),
      ...data.runs.filter(r => !starred.has(r.command)),
    ];

    sorted.forEach(run => {
      const isStarred = starred.has(run.command);
      const entry = document.createElement('div');
      entry.className = 'history-entry' + (isStarred ? ' starred' : '');
      const exitCls = run.exit_code === 0 ? 'exit-ok' : 'exit-fail';
      const time = new Date(run.started).toLocaleTimeString();
      entry.innerHTML = `
        <div class="history-entry-cmd">${escapeHtml(run.command)}</div>
        <div class="history-entry-meta">
          <span>${time}</span>
          <span class="${exitCls}">exit ${run.exit_code}</span>
        </div>
        <div class="history-actions">
          <button class="history-action-btn star-btn${isStarred ? ' starred' : ''}" data-action="star">${isStarred ? '★ starred' : '☆ star'}</button>
          <button class="history-action-btn" data-action="copy">copy command</button>
          <button class="history-action-btn" data-action="permalink">permalink</button>
          <button class="history-action-btn" data-action="delete">delete</button>
        </div>`;

      // Click anywhere on the entry (except buttons) to load into a new tab,
      // or switch to the existing tab if this command is already loaded there.
      entry.addEventListener('click', e => {
        if (e.target.closest('.history-action-btn')) return;

        // If a tab already has this command and already has the full output,
        // switch to it instead of duplicating. If the tab is still showing a
        // truncated preview and the full artifact exists, upgrade that tab in
        // place so the restored view stays consistent.
        const existing = tabs.find(t => t.command === run.command);
        const canUpgradeExisting = !!(existing && run.full_output_available && existing.previewTruncated);
        if (existing && !canUpgradeExisting) {
          activateTab(existing.id);
          hideHistoryPanel();
          return;
        }

        const cmdEl = entry.querySelector('.history-entry-cmd');
        cmdEl.textContent = 'loading…';
        _setHistoryLoadState(true);
        const restoreUrl = run.full_output_available
          ? `/history/${run.id}?json`
          : `/history/${run.id}?json&preview=1`
        apiFetch(restoreUrl)
          .then(r => r.json())
          .then(fullRun => {
            const previewNotice = fullRun.preview_notice || null;
            const newId = canUpgradeExisting ? existing.id : createTab(fullRun.command);
            if (canUpgradeExisting) clearTab(newId);
            const t = getTab(newId);
            if (t) {
              t.command = fullRun.command;
              t.previewTruncated = !!previewNotice;
              t.fullOutputAvailable = !!fullRun.full_output_available;
              t.fullOutputLoaded = !!fullRun.full_output_available && !previewNotice;
            }
            appendLine(`$ ${fullRun.command}`, '', newId);
            appendLine('', '', newId);
            (fullRun.output || []).forEach(line => appendLine(line, '', newId));
            if (previewNotice) {
              appendLine(previewNotice, 'notice', newId);
            }
            appendLine(`[history — exit ${fullRun.exit_code}]`, fullRun.exit_code === 0 ? 'exit-ok' : 'exit-fail', newId);
            hideHistoryPanel();
          })
          .catch(() => {
            entry.querySelector('.history-entry-cmd').textContent = run.command;
            showToast('Failed to load run');
          })
          .finally(() => _setHistoryLoadState(false));
      });

      entry.querySelector('[data-action="star"]').addEventListener('click', () => {
        const wasStarred = _getStarred().has(run.command);
        _toggleStar(run.command);
        // If the command is being starred and isn't in the chips list, add it
        if (!wasStarred && !cmdHistory.includes(run.command)) {
          cmdHistory = [run.command, ...cmdHistory].slice(0, APP_CONFIG.recent_commands_limit);
        }
        refreshHistoryPanel();
        renderHistory(); // keep chips in sync
      });

      entry.querySelector('[data-action="copy"]').addEventListener('click', () => {
        copyTextToClipboard(run.command)
          .then(() => showToast('Command copied to clipboard'))
          .catch(() => showToast('Failed to copy command', 'error'));
      });

      entry.querySelector('[data-action="permalink"]').addEventListener('click', () => {
        const url = `${location.origin}/history/${run.id}`;
        copyTextToClipboard(url)
          .then(() => showToast('Link copied to clipboard'))
          .catch(() => showToast('Failed to copy link', 'error'));
      });
      entry.querySelector('[data-action="delete"]').addEventListener('click', () => {
        confirmHistAction('delete', run.id, run.command);
      });

      historyList.appendChild(entry);
    });
  });
}
