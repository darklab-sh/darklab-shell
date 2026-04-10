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
  if (typeof isHistSearchMode === 'function' && isHistSearchMode()) {
    exitHistSearch(false);
  }
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
      if (typeof focusAnyComposerInput === 'function' && focusAnyComposerInput({ preventScroll: true })) return;
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

function _setHistoryDeleteMessage(title, detail) {
  const msg = histDelMsg;
  if (!msg) return;
  msg.replaceChildren();
  msg.appendChild(document.createTextNode(title));
  msg.appendChild(document.createElement('br'));
  const note = document.createElement('span');
  note.className = 'history-delete-note';
  note.textContent = detail;
  msg.appendChild(note);
}

function _createHistoryEntry(run, isStarred) {
  const entry = document.createElement('div');
  entry.className = 'history-entry' + (isStarred ? ' starred' : '');
  const exitCls = run.exit_code === 0 ? 'exit-ok' : 'exit-fail';
  const time = new Date(run.started).toLocaleTimeString();

  const cmd = document.createElement('div');
  cmd.className = 'history-entry-cmd';
  cmd.textContent = run.command || '';
  entry.appendChild(cmd);

  const meta = document.createElement('div');
  meta.className = 'history-entry-meta';
  const timeEl = document.createElement('span');
  timeEl.textContent = time;
  meta.appendChild(timeEl);
  const exitEl = document.createElement('span');
  exitEl.className = exitCls;
  exitEl.textContent = `exit ${run.exit_code}`;
  meta.appendChild(exitEl);
  entry.appendChild(meta);

  const actions = document.createElement('div');
  actions.className = 'history-actions';

  const starBtn = document.createElement('button');
  starBtn.className = 'history-action-btn star-btn' + (isStarred ? ' starred' : '');
  starBtn.dataset.action = 'star';
  starBtn.textContent = isStarred ? '★ starred' : '☆ star';
  actions.appendChild(starBtn);

  const copyBtn = document.createElement('button');
  copyBtn.className = 'history-action-btn';
  copyBtn.dataset.action = 'copy';
  copyBtn.textContent = 'copy command';
  actions.appendChild(copyBtn);

  const permalinkBtn = document.createElement('button');
  permalinkBtn.className = 'history-action-btn';
  permalinkBtn.dataset.action = 'permalink';
  permalinkBtn.textContent = 'permalink';
  actions.appendChild(permalinkBtn);

  const deleteBtn = document.createElement('button');
  deleteBtn.className = 'history-action-btn';
  deleteBtn.dataset.action = 'delete';
  deleteBtn.textContent = 'delete';
  actions.appendChild(deleteBtn);

  entry.appendChild(actions);
  return entry;
}


// ── Run history panel ──
let pendingHistAction = null;

function confirmHistAction(type, id, command) {
  pendingHistAction = { type, id, command };
  const msg      = histDelMsg;
  const confirm  = histDelConfirmBtn;
  if (type === 'clear') {
    _setHistoryDeleteMessage('Clear run history?', 'This cannot be undone.');
    showHistoryDeleteNonfav();
    confirm.textContent   = 'Delete all';
  } else {
    _setHistoryDeleteMessage('Remove this run from history?', 'This cannot be undone.');
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
    historyList.replaceChildren();
    if (!data.runs.length) {
      const empty = document.createElement('div');
      empty.className = 'history-empty-state';
      empty.textContent = 'No runs yet.';
      historyList.appendChild(empty);
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
      const entry = _createHistoryEntry(run, isStarred);

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
        hideHistoryPanel();
        refreshHistoryPanel();
        renderHistory(); // keep chips in sync
      });

      entry.querySelector('[data-action="copy"]').addEventListener('click', () => {
        copyTextToClipboard(run.command)
          .then(() => showToast('Command copied to clipboard'))
          .catch(() => showToast('Failed to copy command', 'error'));
        const btn = entry.querySelector('[data-action="copy"]');
        if (btn && typeof btn.blur === 'function') setTimeout(() => btn.blur(), 0);
        hideHistoryPanel();
      });

      entry.querySelector('[data-action="permalink"]').addEventListener('click', () => {
        const url = `${location.origin}/history/${run.id}`;
        copyTextToClipboard(url)
          .then(() => showToast('Link copied to clipboard'))
          .catch(() => showToast('Failed to copy link', 'error'));
        const btn = entry.querySelector('[data-action="permalink"]');
        if (btn && typeof btn.blur === 'function') setTimeout(() => btn.blur(), 0);
        hideHistoryPanel();
      });
      entry.querySelector('[data-action="delete"]').addEventListener('click', () => {
        confirmHistAction('delete', run.id, run.command);
        hideHistoryPanel();
        const btn = entry.querySelector('[data-action="delete"]');
        if (btn && typeof btn.blur === 'function') setTimeout(() => btn.blur(), 0);
      });

      historyList.appendChild(entry);
    });
  });
}


// ── Ctrl+R reverse-history search ──

let _histSearchMode = false;
let _histSearchQuery = '';
let _histSearchIndex = -1;
let _histSearchPreDraft = '';

function isHistSearchMode() { return _histSearchMode; }

function _histSearchMatches() {
  if (!cmdHistory.length) return [];
  const q = _histSearchQuery.toLowerCase();
  if (!q) return cmdHistory.slice(0, 20);
  return cmdHistory.filter(c => c.toLowerCase().includes(q)).slice(0, 20);
}

function _hideHistSearchDropdown() {
  if (histSearchDropdown) histSearchDropdown.classList.add('u-hidden');
}

function _renderHistSearch() {
  if (!histSearchDropdown) return;
  const matches = _histSearchMatches();
  histSearchDropdown.replaceChildren();

  const header = document.createElement('div');
  header.className = 'hist-search-header';
  const label = document.createElement('span');
  label.className = 'hist-search-label';
  label.textContent = 'reverse-i-search: ';
  const querySpan = document.createElement('span');
  querySpan.className = 'hist-search-query';
  querySpan.textContent = _histSearchQuery || '';
  header.appendChild(label);
  header.appendChild(querySpan);
  histSearchDropdown.appendChild(header);

  if (!matches.length) {
    const empty = document.createElement('div');
    empty.className = 'hist-search-empty';
    empty.textContent = '(no matches)';
    histSearchDropdown.appendChild(empty);
  } else {
    matches.forEach((cmd, i) => {
      const item = document.createElement('div');
      item.className = 'hist-search-item' + (i === _histSearchIndex ? ' active' : '');
      if (_histSearchQuery) {
        const lower = cmd.toLowerCase();
        const qi = lower.indexOf(_histSearchQuery.toLowerCase());
        if (qi >= 0) {
          item.appendChild(document.createTextNode(cmd.slice(0, qi)));
          const mark = document.createElement('mark');
          mark.className = 'hist-search-match';
          mark.textContent = cmd.slice(qi, qi + _histSearchQuery.length);
          item.appendChild(mark);
          item.appendChild(document.createTextNode(cmd.slice(qi + _histSearchQuery.length)));
        } else {
          item.textContent = cmd;
        }
      } else {
        item.textContent = cmd;
      }
      item.addEventListener('mousedown', e => {
        e.preventDefault();
        _histSearchIndex = i;
        exitHistSearch(true);
      });
      histSearchDropdown.appendChild(item);
    });
  }

  // Position above the prompt line, like the ac-dropdown does
  histSearchDropdown.classList.remove('u-hidden');
  if (shellPromptWrap) {
    const rect = shellPromptWrap.getBoundingClientRect();
    histSearchDropdown.style.position = 'fixed';
    histSearchDropdown.style.left = rect.left + 'px';
    histSearchDropdown.style.width = rect.width + 'px';
    const dropH = histSearchDropdown.offsetHeight;
    histSearchDropdown.style.top = (rect.top - dropH - 4) + 'px';
  }
}

function enterHistSearch() {
  if (_histSearchMode) {
    // Ctrl+R again: cycle to next match
    const matches = _histSearchMatches();
    if (matches.length > 0) {
      _histSearchIndex = (_histSearchIndex + 1) % matches.length;
      if (typeof setComposerValue === 'function') {
        setComposerValue(matches[_histSearchIndex], matches[_histSearchIndex].length, matches[_histSearchIndex].length, { dispatch: false });
      }
      _renderHistSearch();
    }
    return;
  }
  _histSearchMode = true;
  _histSearchQuery = '';
  _histSearchIndex = -1;
  _histSearchPreDraft = (typeof getComposerValue === 'function') ? getComposerValue() : (cmdInput ? cmdInput.value : '');
  // Clear the input so the user types a fresh query rather than appending to the draft.
  // The draft is preserved in _histSearchPreDraft and restored on Escape / Ctrl+G.
  if (typeof setComposerValue === 'function') {
    setComposerValue('', 0, 0, { dispatch: false });
  } else if (cmdInput) {
    cmdInput.value = '';
  }
  if (typeof acHide === 'function') acHide();
  _renderHistSearch();
}

function exitHistSearch(accept, { keepCurrent = false } = {}) {
  if (!_histSearchMode) return;
  _histSearchMode = false;
  _hideHistSearchDropdown();
  if (accept) {
    const matches = _histSearchMatches();
    const chosen = _histSearchIndex >= 0 ? matches[_histSearchIndex] : (matches[0] || _histSearchPreDraft);
    if (typeof setComposerValue === 'function') {
      setComposerValue(chosen, chosen.length, chosen.length);
    } else if (cmdInput) {
      cmdInput.value = chosen;
      cmdInput.dispatchEvent(new Event('input'));
    }
  } else if (!keepCurrent) {
    if (typeof setComposerValue === 'function') {
      setComposerValue(_histSearchPreDraft, _histSearchPreDraft.length, _histSearchPreDraft.length);
    } else if (cmdInput) {
      cmdInput.value = _histSearchPreDraft;
      cmdInput.dispatchEvent(new Event('input'));
    }
  }
  _histSearchQuery = '';
  _histSearchIndex = -1;
  _histSearchPreDraft = '';
  if (typeof acHide === 'function') acHide();
}

function handleHistSearchInput(value) {
  _histSearchQuery = value;
  _histSearchIndex = -1;
  const matches = _histSearchMatches();
  if (matches.length > 0) {
    _histSearchIndex = 0;
  }
  _renderHistSearch();
}

function handleHistSearchKey(e) {
  if (!_histSearchMode) return false;
  if (e.key === 'Escape') {
    e.preventDefault();
    exitHistSearch(false);
    return true;
  }
  if (e.key === 'Enter') {
    e.preventDefault();
    // Accept the selected match (if any) then run it. If nothing matched, keep
    // the typed query in the input and run that instead of restoring the pre-draft.
    if (_histSearchIndex >= 0) {
      exitHistSearch(true);
    } else {
      exitHistSearch(false, { keepCurrent: true });
    }
    if (typeof submitComposerCommand === 'function') {
      submitComposerCommand(cmdInput.value, { dismissKeyboard: true });
    } else if (typeof runCommand === 'function') {
      runCommand();
    }
    return true;
  }
  if (e.key === 'Tab') {
    e.preventDefault();
    // Accept the selected match without running; fall back to keeping the query.
    if (_histSearchIndex >= 0) {
      exitHistSearch(true);
    } else {
      exitHistSearch(false, { keepCurrent: true });
    }
    return true;
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    const matches = _histSearchMatches();
    if (matches.length > 0) {
      _histSearchIndex = (_histSearchIndex + 1) % matches.length;
      if (typeof setComposerValue === 'function') {
        setComposerValue(matches[_histSearchIndex], matches[_histSearchIndex].length, matches[_histSearchIndex].length, { dispatch: false });
      } else if (cmdInput) {
        cmdInput.value = matches[_histSearchIndex];
      }
      _renderHistSearch();
    }
    return true;
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault();
    const matches = _histSearchMatches();
    if (matches.length > 0) {
      _histSearchIndex = _histSearchIndex <= 0 ? matches.length - 1 : _histSearchIndex - 1;
      if (typeof setComposerValue === 'function') {
        setComposerValue(matches[_histSearchIndex], matches[_histSearchIndex].length, matches[_histSearchIndex].length, { dispatch: false });
      } else if (cmdInput) {
        cmdInput.value = matches[_histSearchIndex];
      }
      _renderHistSearch();
    }
    return true;
  }
  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'r' || e.key === 'R')) {
    e.preventDefault();
    enterHistSearch(); // cycle
    return true;
  }
  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'g' || e.key === 'G')) {
    e.preventDefault();
    exitHistSearch(false);
    return true;
  }
  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'c' || e.key === 'C')) {
    e.preventDefault();
    exitHistSearch(false, { keepCurrent: true });
    return true;
  }
  // Let printable characters and backspace fall through to the input event
  return false;
}
