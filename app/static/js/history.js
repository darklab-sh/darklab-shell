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
  cmdHistory.forEach(cmd => {
    const chip = document.createElement('button');
    chip.className = 'hist-chip';
    chip.textContent = cmd;
    chip.title = cmd;
    chip.addEventListener('click', () => { cmdInput.value = cmd; cmdInput.focus(); });
    histRow.appendChild(chip);
  });
}

// ── Run history panel ──
let pendingHistAction = null;

function confirmHistAction(type, id) {
  pendingHistAction = { type, id };
  const msg = document.getElementById('hist-del-msg');
  if (type === 'clear') {
    msg.innerHTML = 'Clear all run history?<br><span style="color:var(--muted);font-size:11px">This cannot be undone.</span>';
  } else {
    msg.innerHTML = 'Remove this run from history?<br><span style="color:var(--muted);font-size:11px">This cannot be undone.</span>';
  }
  histDelOverlay.style.display = 'flex';
}

function executeHistAction() {
  if (!pendingHistAction) return;
  const { type, id } = pendingHistAction;
  pendingHistAction = null;
  if (type === 'delete') {
    apiFetch(`/history/${id}`, { method: 'DELETE' }).then(() => refreshHistoryPanel());
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
    data.runs.forEach(run => {
      const entry = document.createElement('div');
      entry.className = 'history-entry';
      const exitCls = run.exit_code === 0 ? 'exit-ok' : 'exit-fail';
      const time = new Date(run.started).toLocaleTimeString();
      entry.innerHTML = `
        <div class="history-entry-cmd">${escapeHtml(run.command)}</div>
        <div class="history-entry-meta">
          <span>${time}</span>
          <span class="${exitCls}">exit ${run.exit_code}</span>
        </div>
        <div class="history-actions">
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
