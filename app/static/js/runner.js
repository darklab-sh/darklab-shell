// ── SSE stall detection ──
// If no chunk arrives from the SSE stream for 45 seconds (> 2× the 20s server heartbeat),
// the connection has silently died. Surface a notice and reset the UI so the user isn't
// left with a perpetually-spinning tab. The command may still be running server-side;
// the result will appear in the history panel once it completes.
// Keyed by tabId so multiple concurrent tabs each have their own independent timer.
const _stalledTimeouts = new Map();

function _resetStalledTimeout(tabId) {
  clearTimeout(_stalledTimeouts.get(tabId));
  _stalledTimeouts.set(tabId, setTimeout(() => {
    const t = tabs.find(t => t.id === tabId);
    if (!t || t.killed) return;  // already handled
    appendLine('[connection stalled — command may still be running on the server]', 'notice', tabId);
    appendLine('[check the history panel for the result once it completes]', 'notice', tabId);
    if (tabId === activeTabId) setStatus('fail');
    setTabStatus(tabId, 'fail');
    stopTimer(); runBtn.disabled = false; hideTabKillBtn(tabId);
  }, 45000));
}

function _clearStalledTimeout(tabId) {
  clearTimeout(_stalledTimeouts.get(tabId));
  _stalledTimeouts.delete(tabId);
}

// ── Status pill ──
function setStatus(s) {
  status.className = 'status-pill ' + s;
  const labels = { idle: 'IDLE', running: 'RUNNING', ok: 'EXIT 0', fail: 'ERROR', killed: 'KILLED' };
  status.textContent = labels[s] || s;
}

// ── Run timer ──
let timerInterval = null;
let timerStart = null;

// Format a duration in seconds as a compact human-readable string.
// Examples: 32.6 → "32.6s", 125.0 → "2m 5.0s", 3812.3 → "1h 3m 32.3s"
function _formatElapsed(totalSecs) {
  if (totalSecs < 60) return totalSecs.toFixed(1) + 's';
  const h = Math.floor(totalSecs / 3600);
  const m = Math.floor((totalSecs % 3600) / 60);
  const s = (totalSecs % 60).toFixed(1);
  return h > 0 ? `${h}h ${m}m ${s}s` : `${m}m ${s}s`;
}

function startTimer() {
  timerStart = Date.now();
  runTimer.style.display = 'inline';
  timerInterval = setInterval(() => {
    runTimer.textContent = _formatElapsed((Date.now() - timerStart) / 1000);
  }, 100);
}

function stopTimer() {
  clearInterval(timerInterval);
  timerInterval = null;
  runTimer.style.display = 'none';
  runTimer.textContent = '';
}

function elapsedSeconds() {
  return timerStart ? (Date.now() - timerStart) / 1000 : null;
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

function _describeRunnerFetchError(err, context = 'server') {
  if (typeof describeFetchError === 'function') return describeFetchError(err, context);
  const message = err && err.message ? err.message : 'unknown network error';
  return `Request to the ${context} failed: ${message}`;
}

function _logRunnerError(context, err) {
  if (typeof logClientError === 'function') logClientError(context, err);
}

function _handleKillRequestFailure(err, tabId) {
  _logRunnerError('kill request failed', err);
  showToast('Failed to send kill request; command may still be running');
  appendLine('[kill request failed] ' + _describeRunnerFetchError(err), 'notice', tabId);
}

function _handleRunTransportFailure(err, tabId) {
  _logRunnerError('run request failed', err);
  appendLine('[connection error] ' + _describeRunnerFetchError(err), 'exit-fail', tabId);
  if (tabId === activeTabId) setStatus('fail');
  setTabStatus(tabId, 'fail');
  stopTimer(); runBtn.disabled = false; hideTabKillBtn(tabId);
}

async function _readRunErrorMessage(res) {
  const contentType = (res.headers && typeof res.headers.get === 'function' && res.headers.get('content-type')) || '';
  try {
    if (contentType.includes('application/json') && typeof res.json === 'function') {
      const data = await res.json();
      if (data && typeof data.error === 'string' && data.error.trim()) return data.error.trim();
    } else if (typeof res.text === 'function') {
      const text = (await res.text()).trim();
      if (text) return text;
    }
  } catch (err) {
    _logRunnerError('failed to parse /run error response', err);
  }
  return '';
}

function _previewTruncationNotice(outputLineCount, fullOutputAvailable) {
  const shown = APP_CONFIG.max_output_lines || outputLineCount || 0;
  const total = outputLineCount || shown;
  if (fullOutputAvailable) {
    return `[preview truncated — only the last ${shown} lines are shown here, but the full output had ${total} lines. Use the permalink button below or in the history panel for complete results]`;
  }
  return `[preview truncated — only the last ${shown} lines are shown here, but the full output had ${total} lines. Full output persistence is disabled or unavailable]`;
}

function appendCommandEcho(cmd, tabId) {
  appendLine(cmd, 'prompt-echo', tabId);
}

function appendPromptNewline(tabId) {
  appendLine('', 'prompt-echo', tabId);
}

function interruptPromptLine(tabId = activeTabId) {
  const t = tabs.find(tab => tab.id === tabId);
  if (t && t.st === 'running') return false;
  appendPromptNewline(tabId);
  cmdInput.value = '';
  cmdInput.dispatchEvent(new Event('input'));
  cmdInput.focus();
  if (tabId === activeTabId) setStatus('idle');
  return true;
}

// ── Kill confirmation modal ──
let pendingKillTabId = null;

function confirmKill(tabId) {
  pendingKillTabId = tabId;
  killOverlay.style.display = 'flex';
}

function doKill(tabId) {
  const t = tabs.find(t => t.id === tabId);
  if (!t || t.st !== 'running') return;
  const secs = elapsedSeconds();
  if (t.runId) {
    // runId already available — send kill immediately
    apiFetch('/kill', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_id: t.runId })
    }).catch(err => _handleKillRequestFailure(err, tabId));
    t.runId = null;
  } else {
    // runId not yet available (SSE 'started' hasn't arrived) — flag it so the
    // started handler sends the kill request as soon as the run_id is known
    t.pendingKill = true;
  }
  t.killed = true;
  stopTimer();
  appendLine(`[killed by user${secs != null ? ' after ' + _formatElapsed(secs) : ''}]`, 'exit-fail', tabId);
  setTabStatus(tabId, 'killed');
  hideTabKillBtn(tabId);
  if (tabId === activeTabId) {
    setStatus('killed');
    runBtn.disabled = false;
  }
}

// ── Run command ──
function runCommand() {
  const raw = cmdInput.value;
  const cmd = raw.trim();
  if (!cmd) {
    if (
      typeof _welcomeActive !== 'undefined' && _welcomeActive
      && typeof welcomeOwnsTab === 'function' && welcomeOwnsTab(activeTabId)
    ) {
      if (typeof requestWelcomeSettle === 'function') requestWelcomeSettle(activeTabId);
      cmdInput.focus();
      return;
    }
    appendPromptNewline(activeTabId);
    cmdInput.value = '';
    cmdInput.dispatchEvent(new Event('input'));
    cmdInput.focus();
    setStatus('idle');
    return;
  }

  // If the active tab is currently running a command, open a new tab automatically
  // rather than streaming two commands' output on top of each other.
  // Use tab.st (set synchronously by setTabStatus) rather than tab.runId (set
  // asynchronously via SSE) to avoid a race condition where rapid Enter presses
  // fire before the server's 'started' message arrives.
  // If the welcome typeout is still running, cancel it and clear partial output
  if (welcomeOwnsTab(activeTabId)) {
    cancelWelcome(activeTabId);
    clearTab(activeTabId);
  }

  const activeTab = tabs.find(t => t.id === activeTabId);
  if (activeTab && activeTab.st === 'running') {
    const newId = createTab('tab ' + (tabs.length + 1));
    if (!newId) return; // tab limit reached — createTab already showed a toast
    // createTab calls activateTab internally, so activeTabId now points to the new tab
  }

  // Client-side validation mirrors server-side checks for immediate feedback
  const shellOps = /&&|\|\|?|;;?|`|\$\(|>>?|</;
  if (shellOps.test(cmd)) {
    appendCommandEcho(cmd);
    appendLine('[denied] Shell operators (&&, |, ;, >, etc.) are not permitted.', 'denied');
    setStatus('fail');
    return;
  }

  if (/(?<![\w:\/])\/data\b/.test(cmd) || /(?<![\w:\/])\/tmp\b/.test(cmd)) {
    appendCommandEcho(cmd);
    appendLine('[denied] Access to /data and /tmp is not permitted.', 'denied');
    setStatus('fail');
    return;
  }

  addToHistory(cmd);
  if (!activeTab || !activeTab.renamed) setTabLabel(activeTabId, cmd);
  const _cmdTab = tabs.find(t => t.id === activeTabId);
  if (_cmdTab) _cmdTab.command = cmd;
  appendCommandEcho(cmd);
  cmdInput.value = '';
  cmdInput.dispatchEvent(new Event('input'));
  cmdInput.focus();
  // Set runStart after the prompt line so it doesn't receive an elapsed stamp
  const _runTab = tabs.find(t => t.id === activeTabId);
  if (_runTab) _runTab.runStart = Date.now();
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
    if (!res.ok) {
      return _readRunErrorMessage(res).then(message => {
        const suffix = message ? ` ${message}` : '';
        appendLine(`[server error] The server could not start the command.${suffix}`, 'exit-fail', tabId);
        setStatus('fail'); setTabStatus(tabId, 'fail');
        stopTimer(); runBtn.disabled = false; hideTabKillBtn(tabId);
      });
    }
    if (!res.body || typeof res.body.getReader !== 'function') {
      appendLine('[server error] The server returned an invalid streaming response.', 'exit-fail', tabId);
      setStatus('fail'); setTabStatus(tabId, 'fail');
      stopTimer(); runBtn.disabled = false; hideTabKillBtn(tabId);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    _resetStalledTimeout(tabId);

    function read() {
      reader.read().then(({ done, value }) => {
        if (done) { _clearStalledTimeout(tabId); stopTimer(); runBtn.disabled = false; hideTabKillBtn(tabId); return; }
        _resetStalledTimeout(tabId);
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop();
        parts.forEach(part => {
          if (part.startsWith('data: ')) {
            try {
              const msg = JSON.parse(part.slice(6));
              if (msg.type === 'started') {
                const t = tabs.find(t => t.id === tabId);
                if (t) {
                  t.runId = msg.run_id;
                  if (t.pendingKill) {
                    // Kill was requested before runId was available — send it now
                    t.pendingKill = false;
                    apiFetch('/kill', {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ run_id: t.runId })
                    }).catch(err => _handleKillRequestFailure(err, tabId));
                    t.runId = null;
                  } else {
                    t.killed = false;
                  }
                }
              } else if (msg.type === 'notice') {
                appendLine(msg.text, 'notice', tabId);
              } else if (msg.type === 'clear') {
                clearTab(tabId);
                const t = tabs.find(t => t.id === tabId);
                if (t) t.syntheticClear = true;
              } else if (msg.type === 'output') {
                msg.text.split('\n').forEach((line, i, arr) => {
                  if (i < arr.length - 1 || line) appendLine(line, '', tabId);
                });
              } else if (msg.type === 'exit') {
                _clearStalledTimeout(tabId);
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
                if (msg.preview_truncated) {
                  appendLine(_previewTruncationNotice(msg.output_line_count, msg.full_output_available), 'notice', tabId);
                }
                if (msg.code === 0) {
                  if (!(t && t.syntheticClear)) appendLine(`[process exited with code 0${dur}]`, 'exit-ok', tabId);
                  if (tabId === activeTabId) setStatus('ok');
                  setTabStatus(tabId, 'ok');
                } else {
                  appendLine(`[process exited with code ${msg.code}${dur}]`, 'exit-fail', tabId);
                  if (tabId === activeTabId) setStatus('fail');
                  setTabStatus(tabId, 'fail');
                }
                if (t) t.syntheticClear = false;
                runBtn.disabled = false; hideTabKillBtn(tabId);
                if (historyPanel.classList.contains('open')) refreshHistoryPanel();
              } else if (msg.type === 'error') {
                _clearStalledTimeout(tabId);
                appendLine('[error] ' + msg.text, 'exit-fail', tabId);
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
    _clearStalledTimeout(tabId);
    _handleRunTransportFailure(err, tabId);
  });
}
