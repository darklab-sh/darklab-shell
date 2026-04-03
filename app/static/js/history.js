// ── Starred commands ──
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
let cmdHistory = [];

function addToHistory(cmd) {
  cmdHistory = [cmd, ...cmdHistory.filter(c => c !== cmd)].slice(0, APP_CONFIG.recent_commands_limit);
  renderHistory();
}

function renderHistory() {
  while (histRow.children.length > 1) histRow.removeChild(histRow.lastChild);
  if (!cmdHistory.length) { histRow.style.display = 'none'; return; }
  histRow.style.display = 'flex';

  const starred = _getStarred();
  // Starred commands first, then remaining in recency order
  const sorted = [
    ...cmdHistory.filter(c => starred.has(c)),
    ...cmdHistory.filter(c => !starred.has(c)),
  ];

  sorted.forEach(cmd => {
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
    chip.addEventListener('click', () => { cmdInput.value = cmd; cmdInput.focus(); });
    histRow.appendChild(chip);
  });
}


// ── Run history panel ──
let pendingHistAction = null;

function confirmHistAction(type, id) {
  pendingHistAction = { type, id };
  const msg      = document.getElementById('hist-del-msg');
  const nonfav   = document.getElementById('hist-del-nonfav');
  const confirm  = document.getElementById('hist-del-confirm');
  if (type === 'clear') {
    msg.innerHTML = 'Clear run history?<br><span style="color:var(--muted);font-size:11px">This cannot be undone.</span>';
    nonfav.style.display  = 'inline-block';
    confirm.textContent   = 'Delete all';
  } else {
    msg.innerHTML = 'Remove this run from history?<br><span style="color:var(--muted);font-size:11px">This cannot be undone.</span>';
    nonfav.style.display  = 'none';
    confirm.textContent   = 'Delete';
  }
  histDelOverlay.style.display = 'flex';
}

function executeHistAction(type) {
  const action = type || (pendingHistAction && pendingHistAction.type);
  const id     = pendingHistAction && pendingHistAction.id;
  pendingHistAction = null;
  if (action === 'delete') {
    apiFetch(`/history/${id}`, { method: 'DELETE' }).then(() => refreshHistoryPanel());
  } else if (action === 'clear-nonfav') {
    apiFetch('/history')
      .then(r => r.json())
      .then(data => {
        const starred  = _getStarred();
        const toDelete = data.runs.filter(r => !starred.has(r.command));
        return Promise.all(toDelete.map(r => apiFetch(`/history/${r.id}`, { method: 'DELETE' })));
      })
      .then(() => refreshHistoryPanel());
  } else {
    apiFetch('/history', { method: 'DELETE' }).then(() => refreshHistoryPanel());
  }
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

      // Click anywhere on the entry (except buttons) to load into a new tab
      entry.addEventListener('click', e => {
        if (e.target.closest('.history-action-btn')) return;
        const cmdEl = entry.querySelector('.history-entry-cmd');
        cmdEl.textContent = 'loading…';
        apiFetch(`/history/${run.id}?json`)
          .then(r => r.json())
          .then(fullRun => {
            const newId = createTab(fullRun.command);
            appendLine(`$ ${fullRun.command}`, '', newId);
            appendLine('', '', newId);
            (fullRun.output || []).forEach(line => appendLine(line, '', newId));
            appendLine(`\n[history — exit ${fullRun.exit_code}]`, fullRun.exit_code === 0 ? 'exit-ok' : 'exit-fail', newId);
            historyPanel.classList.remove('open');
          })
          .catch(() => {
            entry.querySelector('.history-entry-cmd').textContent = run.command;
            showToast('Failed to load run');
          });
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
        navigator.clipboard.writeText(run.command).then(() => showToast('Command copied to clipboard'));
      });

      entry.querySelector('[data-action="permalink"]').addEventListener('click', () => {
        const url = `${location.origin}/history/${run.id}`;
        navigator.clipboard.writeText(url).then(() => showToast('Link copied to clipboard'));
      });

      entry.querySelector('[data-action="delete"]').addEventListener('click', () => {
        confirmHistAction('delete', run.id);
      });

      historyList.appendChild(entry);
    });
  });
}
