// Interactive PTY support for allowlisted screen tools. The backend owns the
// PTY process; xterm.js owns terminal rendering, keyboard input, and paste.

const PTY_DEFAULT_ROWS = 24;
const PTY_DEFAULT_COLS = 100;
const PTY_MIN_ROWS = 10;
const PTY_MIN_COLS = 40;

function _splitPtyCommand(cmd) {
  return String(cmd || '').trim().match(/"[^"]*"|'[^']*'|\S+/g) || [];
}

function _interactivePtySpecs() {
  const configured = (
    typeof APP_CONFIG !== 'undefined'
    && APP_CONFIG
    && Array.isArray(APP_CONFIG.interactive_pty_commands)
  ) ? APP_CONFIG.interactive_pty_commands : [];
  if (configured.length) return configured;
  return [{
    root: 'mtr',
    trigger_flag: '--interactive',
    default_rows: PTY_DEFAULT_ROWS,
    default_cols: PTY_DEFAULT_COLS,
    requires_args: true,
  }];
}

function _interactivePtySpecForCommand(cmd) {
  const parts = _splitPtyCommand(cmd);
  const root = (parts[0] || '').toLowerCase();
  if (!root) return null;
  return _interactivePtySpecs().find((spec) => {
    const specRoot = String(spec && spec.root || '').toLowerCase();
    const trigger = String(spec && spec.trigger_flag || '');
    return specRoot === root && !!trigger && parts.slice(1).includes(trigger);
  }) || null;
}

function isInteractivePtyCommand(cmd) {
  return !!_interactivePtySpecForCommand(cmd);
}

function _ptyDefaultDimension(value, fallback, minValue, maxValue) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(minValue, Math.min(parsed, maxValue));
}

function _xtermGlobalsAvailable() {
  return (
    typeof globalThis.Terminal === 'function'
    && globalThis.FitAddon
    && typeof globalThis.FitAddon.FitAddon === 'function'
  );
}

function _xtermTheme() {
  const style = globalThis.getComputedStyle ? getComputedStyle(document.body) : null;
  const value = (name, fallback) => {
    if (!style) return fallback;
    return style.getPropertyValue(name).trim() || fallback;
  };
  return {
    background: 'transparent',
    foreground: value('--fg', '#d8d8d8'),
    cursor: value('--green', '#90ee90'),
    selectionBackground: 'rgba(144, 238, 144, 0.24)',
    black: value('--bg', '#05070a'),
    brightBlack: value('--muted', '#8a8f98'),
    white: value('--fg', '#d8d8d8'),
    brightWhite: value('--fg-bright', '#ffffff'),
    green: value('--green', '#90ee90'),
    brightGreen: value('--green', '#90ee90'),
    red: value('--danger', '#ff6b6b'),
    brightRed: value('--danger', '#ff6b6b'),
    yellow: value('--warning', '#f4d35e'),
    brightYellow: value('--warning', '#f4d35e'),
    blue: value('--link', '#8ab4ff'),
    brightBlue: value('--link', '#8ab4ff'),
  };
}

function _terminalFontSize() {
  if (!globalThis.getComputedStyle) return 13;
  const root = getComputedStyle(document.documentElement);
  const raw = root.getPropertyValue('--terminal-font-size').trim();
  const parsed = Number.parseFloat(raw || '');
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 13;
}

function _terminalLineHeight() {
  if (!globalThis.getComputedStyle) return 1.35;
  const root = getComputedStyle(document.documentElement);
  const raw = root.getPropertyValue('--terminal-line-height').trim();
  const parsed = Number.parseFloat(raw || '');
  if (!Number.isFinite(parsed) || parsed <= 0) return 1.35;
  return Math.max(1.35, Math.min(parsed, 1.65));
}

function _createPtyTerminalSession(screen, rows = PTY_DEFAULT_ROWS, cols = PTY_DEFAULT_COLS) {
  if (!_xtermGlobalsAvailable()) {
    throw new Error('Interactive terminal assets did not load');
  }
  const term = new globalThis.Terminal({
    allowProposedApi: false,
    cols,
    convertEol: false,
    cursorBlink: true,
    disableStdin: false,
    fontFamily: 'var(--font-mono)',
    fontSize: _terminalFontSize(),
    lineHeight: _terminalLineHeight(),
    rows,
    scrollback: 1000,
    theme: _xtermTheme(),
  });
  const fitAddon = new globalThis.FitAddon.FitAddon();
  term.loadAddon(fitAddon);
  term.open(screen);
  return {
    screen,
    term,
    fitAddon,
    runId: '',
    inputDisposable: null,
    resizeObserver: null,
    resizeListener: null,
    resizeDisposable: null,
  };
}

function _ptyFit(session) {
  if (!session || !session.fitAddon) return;
  try {
    session.fitAddon.fit();
  } catch (_) {
    // xterm can reject fit before layout is stable; later resize passes retry.
  }
}

function _ptySize(session) {
  const rows = Number(session && session.term && session.term.rows) || PTY_DEFAULT_ROWS;
  const cols = Number(session && session.term && session.term.cols) || PTY_DEFAULT_COLS;
  return {
    rows: Math.max(PTY_MIN_ROWS, rows),
    cols: Math.max(PTY_MIN_COLS, cols),
  };
}

function _ptyPostResize(session) {
  if (!session || !session.runId || typeof apiFetch !== 'function') return;
  apiFetch(`/pty/runs/${encodeURIComponent(session.runId)}/resize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(_ptySize(session)),
  }).catch(() => {});
}

function _ptyInstallResizeHandlers(session) {
  if (!session || !session.term) return;
  session.resizeDisposable = session.term.onResize(() => _ptyPostResize(session));
  const scheduleFit = () => {
    window.requestAnimationFrame(() => _ptyFit(session));
  };
  session.resizeListener = scheduleFit;
  window.addEventListener('resize', scheduleFit);
  if (typeof ResizeObserver === 'function' && session.screen) {
    session.resizeObserver = new ResizeObserver(scheduleFit);
    session.resizeObserver.observe(session.screen);
  }
}

function _ptyDisposeResizeHandlers(session) {
  if (!session) return;
  if (session.inputDisposable && typeof session.inputDisposable.dispose === 'function') {
    session.inputDisposable.dispose();
  }
  if (session.resizeDisposable && typeof session.resizeDisposable.dispose === 'function') {
    session.resizeDisposable.dispose();
  }
  if (session.resizeObserver) session.resizeObserver.disconnect();
  if (session.resizeListener) window.removeEventListener('resize', session.resizeListener);
  session.inputDisposable = null;
  session.resizeDisposable = null;
  session.resizeObserver = null;
  session.resizeListener = null;
}

function _ptySendInput(runId, data) {
  if (!runId || !data || typeof apiFetch !== 'function') return;
  apiFetch(`/pty/runs/${encodeURIComponent(runId)}/input`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ data: String(data).slice(0, 4096) }),
  }).catch(() => {});
}

function _ptyAppendSession(tabId, rows, cols) {
  const out = typeof getOutput === 'function' ? getOutput(tabId) : null;
  if (!out) return null;
  const wrap = document.createElement('div');
  wrap.className = 'pty-session';
  const label = document.createElement('div');
  label.className = 'pty-session-label';
  label.textContent = 'interactive PTY';
  const screen = document.createElement('div');
  screen.className = 'pty-screen';
  screen.tabIndex = 0;
  screen.setAttribute('role', 'application');
  screen.setAttribute('aria-label', 'Interactive PTY terminal');
  screen.dataset.rows = String(rows);
  screen.dataset.cols = String(cols);
  screen.dataset.ptyActive = '1';
  screen.dataset.tabId = tabId;
  wrap.append(label, screen);
  out.appendChild(wrap);
  out.scrollTop = out.scrollHeight;
  const session = _createPtyTerminalSession(screen, rows, cols);
  _ptyFit(session);
  return session;
}

function _activeInteractivePtySession(tabId = null) {
  const targetTabId = tabId || (typeof activeTabId !== 'undefined' ? activeTabId : '');
  const tab = typeof getTab === 'function' ? getTab(targetTabId) : null;
  if (!tab || tab.st !== 'running' || tab.interactivePtyActive !== true) return null;
  const screen = Array.from(document.querySelectorAll('.tab-panel .pty-screen[data-pty-active="1"]'))
    .find(candidate => candidate.dataset && candidate.dataset.tabId === targetTabId);
  if (!screen) return null;
  return { screen, term: tab.ptyTerminal || null };
}

function focusActiveInteractivePty({ preventScroll = true } = {}) {
  const session = _activeInteractivePtySession();
  if (!session || !session.screen) return false;
  if (session.term && typeof session.term.focus === 'function') {
    session.term.focus();
    return true;
  }
  try {
    session.screen.focus({ preventScroll });
  } catch (_) {
    session.screen.focus();
  }
  return true;
}

function _ptyFinalize(tabId, session, msg = {}) {
  const code = msg && Object.prototype.hasOwnProperty.call(msg, 'code') ? msg.code : null;
  const elapsed = msg && Object.prototype.hasOwnProperty.call(msg, 'elapsed') ? msg.elapsed : null;
  const tab = typeof getTab === 'function' ? getTab(tabId) : null;
  if (tab) {
    tab.exitCode = code;
    tab.runId = null;
    tab.reconnectedRun = false;
    tab.lastEventId = '';
    tab.attachMode = '';
    tab.deferPromptMount = true;
    tab.previewTruncated = !!(msg && msg.preview_truncated);
    tab.fullOutputAvailable = !!(msg && msg.full_output_available);
    tab.fullOutputLoaded = !(msg && msg.preview_truncated);
    tab.interactivePtyActive = false;
    tab.ptyTerminal = null;
  }
  if (session && session.screen && session.screen.dataset) session.screen.dataset.ptyActive = '0';
  if (session && session.term) session.term.options.disableStdin = true;
  _ptyDisposeResizeHandlers(session);
  const killed = !!(tab && tab.killed);
  const ok = Number(code) === 0 || killed;
  if (typeof appendLine === 'function') {
    const suffix = typeof elapsed === 'number' ? ` in ${elapsed}s` : '';
    if (msg && msg.preview_truncated && typeof _previewTruncationNotice === 'function') {
      appendLine(
        _previewTruncationNotice(msg.output_line_count, msg.full_output_available),
        'notice',
        tabId,
      );
    }
    appendLine(`[interactive PTY exited with code ${code ?? 'unknown'}${suffix}]`, ok ? 'exit-ok' : 'exit-fail', tabId);
  }
  if (typeof addToRecentPreview === 'function' && tab && tab.command && !tab.unknownCommand) {
    addToRecentPreview(tab.command);
  }
  if (typeof emitUiEvent === 'function') emitUiEvent('app:last-exit-changed', { value: code });
  if (typeof setStatus === 'function') setStatus(ok ? 'ok' : 'fail');
  if (typeof setTabStatus === 'function') setTabStatus(tabId, ok ? 'idle' : 'fail');
  if (typeof stopTimer === 'function') stopTimer();
  if (typeof _setRunButtonDisabled === 'function') _setRunButtonDisabled(false);
  if (typeof hideTabKillBtn === 'function') hideTabKillBtn(tabId);
  if (tab && tab.closing && typeof finalizeClosingTab === 'function') {
    finalizeClosingTab(tabId);
    if (typeof isHistoryPanelOpen === 'function' && isHistoryPanelOpen() && typeof refreshHistoryPanel === 'function') {
      refreshHistoryPanel();
    }
    return;
  }
  if (typeof isHistoryPanelOpen === 'function' && isHistoryPanelOpen() && typeof refreshHistoryPanel === 'function') {
    refreshHistoryPanel();
  }
  if (typeof refreshWorkspaceFileCache === 'function') refreshWorkspaceFileCache();
  if (typeof _maybeMountDeferredPrompt === 'function') _maybeMountDeferredPrompt(tabId);
  if (tabId === activeTabId && typeof refocusComposerAfterAction === 'function') {
    refocusComposerAfterAction({ preventScroll: true });
  }
}

async function _ptyReadStream(streamUrl, tabId, session) {
  const res = await apiFetch(streamUrl);
  if (!res.ok || !res.body) throw new Error('Interactive stream failed');
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const parts = buf.split('\n\n');
    buf = parts.pop() || '';
    for (const part of parts) {
      const msg = typeof _sseMessageFromChunk === 'function' ? _sseMessageFromChunk(part) : null;
      if (!msg || msg.type === 'heartbeat') continue;
      const tab = typeof getTab === 'function' ? getTab(tabId) : null;
      if (!tab) continue;
      if (msg.type === 'output') {
        session.term.write(msg.text || '');
        const out = typeof getOutput === 'function' ? getOutput(tabId) : null;
        if (out && tab.followOutput !== false) out.scrollTop = out.scrollHeight;
      } else if (msg.type === 'notice' || msg.type === 'error') {
        if (typeof appendLine === 'function') appendLine(msg.text || '[interactive PTY notice]', 'notice', tabId);
      } else if (msg.type === 'exit') {
        _ptyFinalize(tabId, session, msg);
        return;
      }
    }
  }
}

function _prepareInteractivePtyTab(cmd, tabId) {
  const tab = typeof getTab === 'function' ? getTab(tabId) : null;
  if (typeof setTabRunningCommand === 'function') setTabRunningCommand(tabId, cmd);
  else if (tab) tab.command = cmd;
  if (typeof appendCommandEcho === 'function') appendCommandEcho(cmd, tabId);
  if (tab) {
    tab.runStart = Date.now();
    tab.currentRunStartIndex = tab.rawLines.length;
    tab.previewTruncated = false;
    tab.fullOutputAvailable = false;
    tab.fullOutputLoaded = false;
    tab.historyRunId = null;
    tab.reconnectedRun = false;
    tab.lastEventId = '';
    tab.attachMode = '';
    tab.followOutput = true;
    tab.deferPromptMount = false;
    tab.interactivePtyActive = true;
    tab.ptyTerminal = null;
  }
  if (typeof setStatus === 'function') setStatus('running');
  if (typeof setTabStatus === 'function') setTabStatus(tabId, 'running');
  if (typeof _setRunButtonDisabled === 'function') _setRunButtonDisabled(true);
  if (typeof showTabKillBtn === 'function') showTabKillBtn(tabId);
  if (typeof startTimer === 'function') startTimer();
}

function _failInteractivePtyTab(tabId, message, session = null) {
  const tab = typeof getTab === 'function' ? getTab(tabId) : null;
  if (tab) {
    tab.interactivePtyActive = false;
    tab.ptyTerminal = null;
  }
  if (session && session.screen && session.screen.dataset) session.screen.dataset.ptyActive = '0';
  if (session && session.term) session.term.options.disableStdin = true;
  _ptyDisposeResizeHandlers(session);
  if (typeof appendLine === 'function') appendLine(message, 'exit-fail', tabId);
  if (typeof setStatus === 'function') setStatus('fail');
  if (typeof setTabStatus === 'function') setTabStatus(tabId, 'fail');
  if (typeof stopTimer === 'function') stopTimer();
  if (typeof _setRunButtonDisabled === 'function') _setRunButtonDisabled(false);
  if (typeof hideTabKillBtn === 'function') hideTabKillBtn(tabId);
  if (tabId === activeTabId && typeof refocusComposerAfterAction === 'function') {
    refocusComposerAfterAction({ preventScroll: true });
  }
}

async function startInteractivePtyCommand(cmd, tabId) {
  if (!(typeof APP_CONFIG !== 'undefined' && APP_CONFIG && APP_CONFIG.interactive_pty_enabled === true)) {
    if (typeof appendCommandEcho === 'function') appendCommandEcho(cmd, tabId);
    _failInteractivePtyTab(tabId, '[denied] Interactive PTY mode is disabled on this instance.');
    return;
  }
  _prepareInteractivePtyTab(cmd, tabId);
  let session = null;
  try {
    const spec = _interactivePtySpecForCommand(cmd) || {};
    const rows = _ptyDefaultDimension(spec.default_rows, PTY_DEFAULT_ROWS, PTY_MIN_ROWS, 60);
    const cols = _ptyDefaultDimension(spec.default_cols, PTY_DEFAULT_COLS, PTY_MIN_COLS, 240);
    session = _ptyAppendSession(tabId, rows, cols);
    if (!session) throw new Error('Interactive PTY output could not be mounted');
    const size = _ptySize(session);
    const res = await apiFetch('/pty/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: cmd, tab_id: tabId, rows: size.rows, cols: size.cols }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.error || 'Interactive PTY command could not start');
    }
    const data = await res.json();
    const runId = data.run_id;
    if (!runId) throw new Error('Interactive PTY command did not return a run id');
    session.runId = runId;
    const tab = typeof getTab === 'function' ? getTab(tabId) : null;
    if (tab) tab.ptyTerminal = session.term;
    if (typeof _markTabRunStarted === 'function') _markTabRunStarted(tabId, runId);
    session.inputDisposable = session.term.onData(dataChunk => _ptySendInput(runId, dataChunk));
    _ptyInstallResizeHandlers(session);
    focusActiveInteractivePty({ preventScroll: true });
    window.setTimeout(() => {
      _ptyFit(session);
      _ptyPostResize(session);
    }, 100);
    await _ptyReadStream(data.stream, tabId, session);
  } catch (err) {
    _failInteractivePtyTab(tabId, `[server error] ${err.message || 'Interactive PTY failed'}`, session);
  }
}
