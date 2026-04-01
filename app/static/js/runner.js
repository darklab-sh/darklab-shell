// ── Status pill ──
function setStatus(s) {
  status.className = 'status-pill ' + s;
  const labels = { idle: 'IDLE', running: 'RUNNING', ok: 'EXIT 0', fail: 'ERROR', killed: 'KILLED' };
  status.textContent = labels[s] || s;
}

// ── Run timer ──
let timerInterval = null;
let timerStart = null;

function startTimer() {
  timerStart = Date.now();
  runTimer.style.display = 'inline';
  timerInterval = setInterval(() => {
    const s = ((Date.now() - timerStart) / 1000).toFixed(1);
    runTimer.textContent = `${s}s`;
  }, 100);
}

function stopTimer() {
  clearInterval(timerInterval);
  timerInterval = null;
  runTimer.style.display = 'none';
  runTimer.textContent = '';
}

function elapsedSeconds() {
  return timerStart ? ((Date.now() - timerStart) / 1000).toFixed(1) : null;
}

// ── Kill button ──
function getTabKillBtn(tabId) {
  return document.querySelector(`.tab-kill-btn[data-tab="${tabId}"]`);
}

function showTabKillBtn(tabId) {
  const btn = getTabKillBtn(tabId);
  if (btn) btn.style.display = 'inline-block';
}

function hideTabKillBtn(tabId) {
  const btn = getTabKillBtn(tabId);
  if (btn) btn.style.display = 'none';
}

// ── Kill confirmation modal ──
let pendingKillTabId = null;

function confirmKill(tabId) {
  pendingKillTabId = tabId;
  killOverlay.style.display = 'flex';
}

function doKill(tabId) {
  const t = tabs.find(t => t.id === tabId);
  if (!t || !t.runId) return;
  const secs = elapsedSeconds();
  apiFetch('/kill', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ run_id: t.runId })
  });
  t.runId = null;
  t.killed = true;
  stopTimer();
  appendLine(`\n[killed by user${secs ? ' after ' + secs + 's' : ''}]`, 'exit-fail', tabId);
  setTabStatus(tabId, 'killed');
  hideTabKillBtn(tabId);
  if (tabId === activeTabId) {
    setStatus('killed');
    runBtn.disabled = false;
  }
}

// ── Run command ──
function runCommand() {
  const cmd = cmdInput.value.trim();
  if (!cmd) return;

  // Client-side validation mirrors server-side checks for immediate feedback
  const shellOps = /&&|\|\|?|;;?|`|\$\(|>>?|</;
  if (shellOps.test(cmd)) {
    appendLine('\n$ ' + cmd + '\n', '');
    appendLine('[denied] Shell operators (&&, |, ;, >, etc.) are not permitted.', 'denied');
    setStatus('fail');
    return;
  }

  if (/(?<![\w:\/])\/data\b/.test(cmd) || /(?<![\w:\/])\/tmp\b/.test(cmd)) {
    appendLine('\n$ ' + cmd + '\n', '');
    appendLine('[denied] Access to /data and /tmp is not permitted.', 'denied');
    setStatus('fail');
    return;
  }

  addToHistory(cmd);
  setTabLabel(activeTabId, cmd);
  appendLine('\n$ ' + cmd + '\n', '');
  setStatus('running');
  setTabStatus(activeTabId, 'running');
  runBtn.disabled = true;
  showTabKillBtn(activeTabId);
  startTimer();

  const tabId = activeTabId;

  apiFetch('/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command: cmd })
  }).then(res => {
    if (res.status === 403) {
      return res.json().then(data => {
        appendLine('[denied] ' + (data.error || 'Command not allowed.'), 'denied', tabId);
        setStatus('fail'); setTabStatus(tabId, 'fail');
        stopTimer(); runBtn.disabled = false; hideTabKillBtn(tabId);
      });
    }
    if (res.status === 429) {
      appendLine('[rate limited] Too many requests. Please wait a moment.', 'denied', tabId);
      setStatus('fail'); setTabStatus(tabId, 'fail');
      stopTimer(); runBtn.disabled = false; hideTabKillBtn(tabId);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    function read() {
      reader.read().then(({ done, value }) => {
        if (done) { stopTimer(); runBtn.disabled = false; hideTabKillBtn(tabId); return; }
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop();
        parts.forEach(part => {
          if (part.startsWith('data: ')) {
            try {
              const msg = JSON.parse(part.slice(6));
              if (msg.type === 'started') {
                const t = tabs.find(t => t.id === tabId);
                if (t) { t.runId = msg.run_id; t.killed = false; }
              } else if (msg.type === 'notice') {
                appendLine(msg.text, 'notice', tabId);
              } else if (msg.type === 'output') {
                msg.text.split('\n').forEach((line, i, arr) => {
                  if (i < arr.length - 1 || line) appendLine(line, '', tabId);
                });
              } else if (msg.type === 'exit') {
                const t = tabs.find(t => t.id === tabId);
                if (t) { t.exitCode = msg.code; t.runId = null; }
                // If already killed by user, ignore the subsequent -15 exit code
                if (t && t.killed) {
                  t.killed = false;
                  stopTimer();
                  runBtn.disabled = false; hideTabKillBtn(tabId);
                  if (historyPanel.classList.contains('open')) refreshHistoryPanel();
                  return;
                }
                const dur = msg.elapsed ? ` in ${msg.elapsed}s` : '';
                stopTimer();
                if (msg.code === 0) {
                  appendLine(`\n[process exited with code 0${dur}]`, 'exit-ok', tabId);
                  if (tabId === activeTabId) setStatus('ok');
                  setTabStatus(tabId, 'ok');
                } else {
                  appendLine(`\n[process exited with code ${msg.code}${dur}]`, 'exit-fail', tabId);
                  if (tabId === activeTabId) setStatus('fail');
                  setTabStatus(tabId, 'fail');
                }
                runBtn.disabled = false; hideTabKillBtn(tabId);
                if (historyPanel.classList.contains('open')) refreshHistoryPanel();
              } else if (msg.type === 'error') {
                appendLine('\n[error] ' + msg.text, 'exit-fail', tabId);
                if (tabId === activeTabId) setStatus('fail');
                setTabStatus(tabId, 'fail');
                stopTimer(); runBtn.disabled = false; hideTabKillBtn(tabId);
              }
            } catch(e) {}
          }
        });
        read();
      });
    }
    read();
  }).catch(err => {
    appendLine('\n[fetch error] ' + err.message, 'exit-fail', tabId);
    if (tabId === activeTabId) setStatus('fail');
    setTabStatus(tabId, 'fail');
    stopTimer(); runBtn.disabled = false; hideTabKillBtn(tabId);
  });
}
