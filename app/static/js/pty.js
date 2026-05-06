// Interactive PTY support for allowlisted screen tools. The backend owns the
// PTY process; xterm.js owns terminal rendering, keyboard input, and paste.

const PTY_DEFAULT_ROWS = 24;
const PTY_DEFAULT_COLS = 100;
const PTY_MIN_ROWS = 10;
const PTY_MIN_COLS = 40;
const PTY_INPUT_MAX_BYTES = 4096;
const _ptyModalState = {
  bound: false,
  session: null,
  startedAt: 0,
  timer: null,
};
let _xtermAssetsPromise = null;
let _xtermAssetPreloadScheduled = false;

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

function _interactivePtyEnabled() {
  return !!(
    typeof APP_CONFIG !== 'undefined'
    && APP_CONFIG
    && APP_CONFIG.interactive_pty_enabled === true
  );
}

function _interactivePtyMobileUnsupported() {
  if (typeof useMobileTerminalViewportMode === 'function') {
    return !!useMobileTerminalViewportMode();
  }
  return !!(
    typeof document !== 'undefined'
    && document.body
    && document.body.classList.contains('mobile-terminal-mode')
  );
}

function _loadPtyStylesheetOnce(href) {
  const selector = `link[rel="stylesheet"][href="${href}"]`;
  const existing = document.querySelector(selector);
  if (existing && existing.dataset && existing.dataset.ptyLoadState === 'error') {
    existing.remove();
  } else if (existing) {
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = href;
    link.dataset.ptyLoadState = 'loading';
    link.onload = () => {
      link.dataset.ptyLoadState = 'loaded';
      resolve();
    };
    link.onerror = () => {
      link.dataset.ptyLoadState = 'error';
      reject(new Error(`Could not load ${href}`));
    };
    document.head.appendChild(link);
  });
}

function _loadPtyScriptOnce(src, globalReady) {
  if (typeof globalReady === 'function' && globalReady()) return Promise.resolve();
  const existing = document.querySelector(`script[src="${src}"]`);
  if (existing) {
    const loadState = existing.dataset ? existing.dataset.ptyLoadState : '';
    if (loadState === 'error' || loadState === 'loaded') {
      existing.remove();
      return _loadPtyScriptOnce(src, globalReady);
    }
    return new Promise((resolve, reject) => {
      if (typeof globalReady === 'function' && globalReady()) {
        resolve();
        return;
      }
      existing.addEventListener('load', () => resolve(), { once: true });
      existing.addEventListener('error', () => reject(new Error(`Could not load ${src}`)), { once: true });
    });
  }
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = src;
    script.dataset.ptyLoadState = 'loading';
    script.onload = () => {
      script.dataset.ptyLoadState = 'loaded';
      resolve();
    };
    script.onerror = () => {
      script.dataset.ptyLoadState = 'error';
      reject(new Error(`Could not load ${src}`));
    };
    document.head.appendChild(script);
  });
}

function _ensureXtermAssets() {
  if (!_xtermAssetsPromise) {
    _xtermAssetsPromise = _loadPtyStylesheetOnce('/vendor/xterm.css')
      .then(() => _loadPtyScriptOnce('/vendor/xterm.js', () => typeof globalThis.Terminal === 'function'))
      .then(() => _loadPtyScriptOnce('/vendor/xterm-addon-fit.js', () => (
        globalThis.FitAddon && typeof globalThis.FitAddon.FitAddon === 'function'
      )))
      .then(() => {
        if (!_xtermGlobalsAvailable()) throw new Error('Interactive terminal assets did not load');
      })
      .catch((err) => {
        _xtermAssetsPromise = null;
        throw err;
      });
  }
  return _xtermAssetsPromise;
}

function preloadInteractivePtyAssets() {
  if (!_interactivePtyEnabled()) return null;
  return _ensureXtermAssets().catch((err) => {
    if (typeof logClientError === 'function') {
      logClientError('failed to preload interactive PTY assets', err);
    }
    return null;
  });
}

function _scheduleInteractivePtyAssetPreload() {
  if (_xtermAssetPreloadScheduled || !_interactivePtyEnabled()) return false;
  _xtermAssetPreloadScheduled = true;
  const preload = () => {
    void preloadInteractivePtyAssets();
  };
  if (typeof window !== 'undefined' && typeof window.requestIdleCallback === 'function') {
    window.requestIdleCallback(preload, { timeout: 1000 });
  } else if (typeof window !== 'undefined' && typeof window.setTimeout === 'function') {
    window.setTimeout(preload, 0);
  } else {
    preload();
  }
  return true;
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

function _ptyApplyLiveTheme(session = _ptyModalState.session) {
  if (!session || !session.term) return false;
  const nextTheme = _xtermTheme();
  try {
    if (session.term.options && typeof session.term.options === 'object') {
      session.term.options.theme = nextTheme;
    } else if (typeof session.term.setOption === 'function') {
      session.term.setOption('theme', nextTheme);
    } else {
      return false;
    }
    if (typeof session.term.refresh === 'function') {
      session.term.refresh(0, Math.max(0, (session.term.rows || 1) - 1));
    }
    return true;
  } catch (err) {
    if (typeof logClientError === 'function') {
      logClientError('failed to refresh interactive PTY theme', err);
    }
    return false;
  }
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

function _ptyInputPayload(data) {
  const text = String(data || '');
  if (!text || typeof TextEncoder !== 'function') return { text, truncated: false };
  const encoder = new TextEncoder();
  if (encoder.encode(text).length <= PTY_INPUT_MAX_BYTES) return { text, truncated: false };
  let bytes = 0;
  let value = '';
  for (const char of text) {
    const charBytes = encoder.encode(char).length;
    if (bytes + charBytes > PTY_INPUT_MAX_BYTES) break;
    bytes += charBytes;
    value += char;
  }
  return { text: value, truncated: true };
}

function _ptySendInput(runId, data, tabId = '') {
  if (!runId || !data || typeof apiFetch !== 'function') return;
  const payload = _ptyInputPayload(data);
  if (!payload.text) return;
  if (payload.truncated && typeof appendLine === 'function') {
    appendLine('[interactive PTY input truncated to 4096 bytes]', 'notice', tabId || undefined);
  }
  apiFetch(`/pty/runs/${encodeURIComponent(runId)}/input`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ data: payload.text }),
  }).catch(() => {});
}

function _ptyConfirmSessionKill(session) {
  if (!session || !session.runId || !session.tabId) {
    _ptyCloseModal({ force: true });
    return;
  }
  if (typeof confirmKill === 'function') confirmKill(session.tabId);
}

function _ptyInstallKeyboardHandlers(session) {
  if (!session || !session.term || typeof session.term.attachCustomKeyEventHandler !== 'function') return;
  session.term.attachCustomKeyEventHandler(event => {
    if (
      event
      && event.type === 'keydown'
      && event.ctrlKey
      && !event.altKey
      && !event.metaKey
      && !event.shiftKey
      && String(event.key || '').toLowerCase() === 'c'
    ) {
      // Let xterm emit \x03 through onData so tools can handle native Ctrl+C.
      return true;
    }
    return true;
  });
}

function _ptyModalEls() {
  return {
    overlay: document.getElementById('pty-overlay'),
    modal: document.getElementById('pty-modal'),
    command: document.getElementById('pty-modal-command'),
    status: document.getElementById('pty-modal-status'),
    statusLabel: document.getElementById('pty-modal-status-label'),
    elapsed: document.getElementById('pty-modal-elapsed'),
    screen: document.getElementById('pty-modal-screen'),
    closeBtn: document.querySelector('.pty-modal-close'),
    hideBtn: document.getElementById('pty-modal-hide'),
    killBtn: document.getElementById('pty-modal-kill'),
  };
}

function _ptyPanelForTab(tabId) {
  if (!tabId) return null;
  if (typeof getTabPanel === 'function') return getTabPanel(tabId);
  return Array.from(document.querySelectorAll('.tab-panel'))
    .find(panel => panel.dataset && panel.dataset.id === String(tabId)) || null;
}

function _ptyScopeModalToTab(tabId) {
  const { overlay } = _ptyModalEls();
  const panel = _ptyPanelForTab(tabId);
  if (!overlay || !panel) return false;
  if (overlay.parentElement !== panel) panel.appendChild(overlay);
  overlay.dataset.tabId = tabId;
  return true;
}

function _ptySetModalStatus(text, tone = '') {
  const { status: statusEl, statusLabel } = _ptyModalEls();
  if (!statusEl) return;
  if (statusLabel) statusLabel.textContent = text;
  else statusEl.textContent = text;
  statusEl.dataset.tone = tone;
}

function _ptyFormatModalElapsed(totalSeconds) {
  const value = Math.max(0, Math.floor(Number(totalSeconds) || 0));
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const seconds = value % 60;
  const two = part => String(part).padStart(2, '0');
  return hours > 0 ? `${hours}:${two(minutes)}:${two(seconds)}` : `${two(minutes)}:${two(seconds)}`;
}

function _ptySetModalElapsed(totalSeconds = 0) {
  const { elapsed } = _ptyModalEls();
  if (elapsed) elapsed.textContent = _ptyFormatModalElapsed(totalSeconds);
}

function _ptyStopModalTimer(finalElapsed = null) {
  if (_ptyModalState.timer) {
    window.clearInterval(_ptyModalState.timer);
    _ptyModalState.timer = null;
  }
  if (typeof finalElapsed === 'number') _ptySetModalElapsed(finalElapsed);
}

function _ptyStartModalTimer() {
  _ptyStopModalTimer();
  _ptyModalState.startedAt = Date.now();
  _ptySetModalElapsed(0);
  _ptyModalState.timer = window.setInterval(() => {
    if (!_ptyModalState.startedAt) return;
    _ptySetModalElapsed((Date.now() - _ptyModalState.startedAt) / 1000);
  }, 1000);
}

function _ptySetModalKillEnabled(enabled) {
  const { killBtn } = _ptyModalEls();
  if (killBtn) killBtn.disabled = !enabled;
}

function _ptySetModalCloseEnabled(enabled) {
  const { closeBtn } = _ptyModalEls();
  if (closeBtn) closeBtn.disabled = !enabled;
}

function _ptySetModalHideEnabled(enabled) {
  const { hideBtn } = _ptyModalEls();
  if (hideBtn) hideBtn.disabled = !enabled;
}

function _ptyIsModalOpen() {
  const { overlay } = _ptyModalEls();
  return !!(overlay && overlay.classList.contains('open'));
}

function _ptyIndicatorForTab(tabId) {
  const panel = _ptyPanelForTab(tabId);
  return panel ? panel.querySelector(':scope .pty-running-indicator') : null;
}

function _ptyRemoveRunningIndicator(tabId) {
  _ptyIndicatorForTab(tabId)?.remove();
}

function _ptyLiveSessionForTab(tabId) {
  const session = _ptyModalState.session;
  return session && session.tabId === tabId && session.runId ? session : null;
}

function _ptyShowModalForSession(session) {
  if (!session || !session.tabId) return false;
  const { overlay, screen } = _ptyModalEls();
  if (!overlay || !screen) return false;
  if (!_ptyScopeModalToTab(session.tabId)) return false;
  overlay.classList.remove('u-hidden');
  overlay.classList.add('open');
  overlay.setAttribute('aria-hidden', 'false');
  screen.dataset.ptyActive = '1';
  screen.dataset.tabId = session.tabId;
  _ptySetModalStatus('running', 'running');
  _ptySetModalKillEnabled(true);
  _ptySetModalCloseEnabled(true);
  _ptySetModalHideEnabled(true);
  _ptyFit(session);
  window.setTimeout(() => {
    _ptyFit(session);
    if (session.term && typeof session.term.focus === 'function') session.term.focus();
  }, 0);
  return true;
}

function reopenInteractivePtyModal(tabId = '') {
  const targetTabId = String(tabId || (typeof activeTabId !== 'undefined' ? activeTabId : '') || '');
  const session = _ptyLiveSessionForTab(targetTabId);
  if (session && _ptyShowModalForSession(session)) return true;
  if (typeof showToast === 'function') {
    showToast('Live PTY reattach is not available yet. Use the owning tab while it is open, or Status Monitor to track and kill the run.', 'error');
  }
  return false;
}

function _ptyUpsertRunningIndicator(tabId, options = {}) {
  const panel = _ptyPanelForTab(tabId);
  if (!panel) return null;
  const terminalBody = panel.querySelector(':scope > .terminal-body');
  if (!terminalBody) return null;
  const existing = _ptyIndicatorForTab(tabId);
  const indicator = existing || document.createElement('div');
  indicator.className = 'pty-running-indicator';
  indicator.dataset.tabId = tabId;
  indicator.dataset.state = options.state || 'running';

  const label = document.createElement('span');
  label.className = 'pty-running-indicator-label';
  label.textContent = options.label || 'Interactive PTY running';

  const detail = document.createElement('span');
  detail.className = 'pty-running-indicator-detail';
  detail.textContent = options.detail || 'The live terminal is attached to this tab.';

  const action = document.createElement('button');
  action.type = 'button';
  action.className = 'btn btn-secondary btn-compact pty-running-indicator-action';
  action.textContent = options.actionLabel || 'Reopen terminal';
  action.disabled = options.actionDisabled === true;
  action.addEventListener('click', event => {
    event.preventDefault();
    event.stopPropagation();
    reopenInteractivePtyModal(tabId);
  });

  indicator.replaceChildren(label, detail, action);
  const output = panel.querySelector(':scope > .terminal-body > .output');
  if (!existing) terminalBody.insertBefore(indicator, output ? output.nextSibling : terminalBody.firstChild);
  return indicator;
}

function _ptyCloseModal({ force = false } = {}) {
  const { overlay, screen } = _ptyModalEls();
  const session = _ptyModalState.session;
  if (!force && session && session.runId) return;
  if (overlay) {
    overlay.classList.add('u-hidden');
    overlay.classList.remove('open');
    overlay.setAttribute('aria-hidden', 'true');
  }
  if (screen) {
    screen.dataset.ptyActive = '0';
    screen.dataset.tabId = '';
    screen.replaceChildren();
  }
  _ptyStopModalTimer();
  _ptyModalState.startedAt = 0;
  _ptySetModalElapsed(0);
  _ptySetModalKillEnabled(false);
  _ptySetModalCloseEnabled(true);
  _ptySetModalHideEnabled(false);
}

function _ptyKillModalRun() {
  _ptyConfirmSessionKill(_ptyModalState.session);
}

function _ptyHideModal() {
  const { overlay } = _ptyModalEls();
  const session = _ptyModalState.session;
  if (!overlay || !session || !session.runId) return false;
  overlay.classList.add('u-hidden');
  overlay.classList.remove('open');
  overlay.setAttribute('aria-hidden', 'true');
  const indicator = _ptyIndicatorForTab(session.tabId);
  const action = indicator ? indicator.querySelector('.pty-running-indicator-action') : null;
  if (action && typeof action.focus === 'function') action.focus({ preventScroll: true });
  return true;
}

function _ptyBindModalOnce() {
  if (_ptyModalState.bound) return;
  const { overlay, modal, hideBtn, killBtn, closeBtn } = _ptyModalEls();
  if (!overlay || !modal) return;
  _ptyModalState.bound = true;
  if (hideBtn) {
    hideBtn.addEventListener('click', _ptyHideModal);
  }
  if (killBtn) {
    killBtn.addEventListener('click', _ptyKillModalRun);
  }
  if (typeof bindDismissible === 'function') {
    bindDismissible(overlay, {
      level: 'modal',
      isOpen: _ptyIsModalOpen,
      onClose: _ptyKillModalRun,
      closeButtons: closeBtn,
      closeOnBackdrop: false,
    });
  }
  if (typeof bindFocusTrap === 'function') bindFocusTrap(modal);
}

function _ptyOpenModal(tabId, command, rows, cols) {
  const { overlay, command: commandEl, screen } = _ptyModalEls();
  if (!overlay || !screen) throw new Error('Interactive PTY modal is not available');
  _ptyBindModalOnce();
  if (!_ptyScopeModalToTab(tabId)) throw new Error('Interactive PTY tab panel is not available');
  if (_ptyModalState.session) {
    _ptyDisposeResizeHandlers(_ptyModalState.session);
    if (_ptyModalState.session.term) _ptyModalState.session.term.dispose?.();
  }
  _ptyModalState.session = null;
  screen.replaceChildren();
  screen.dataset.ptyActive = '1';
  screen.dataset.tabId = tabId;
  screen.dataset.rows = String(rows);
  screen.dataset.cols = String(cols);
  if (commandEl) commandEl.textContent = command || 'interactive PTY';
  overlay.classList.remove('u-hidden');
  overlay.classList.add('open');
  overlay.setAttribute('aria-hidden', 'false');
  _ptySetModalStatus('starting', 'running');
  _ptyStopModalTimer();
  _ptyModalState.startedAt = 0;
  _ptySetModalElapsed(0);
  _ptySetModalKillEnabled(false);
  _ptySetModalCloseEnabled(false);
  _ptySetModalHideEnabled(false);
  if (typeof markInteractionSurfaceReady === 'function') {
    markInteractionSurfaceReady('pty', overlay, document.getElementById('pty-modal'));
  }
  const session = _createPtyTerminalSession(screen, rows, cols);
  session.tabId = tabId;
  _ptyModalState.session = session;
  _ptyUpsertRunningIndicator(tabId);
  _ptyFit(session);
  window.setTimeout(() => {
    _ptyFit(session);
    if (session.term && typeof session.term.focus === 'function') session.term.focus();
  }, 100);
  return session;
}

function _activeInteractivePtySession(tabId = null) {
  const targetTabId = tabId || (typeof activeTabId !== 'undefined' ? activeTabId : '');
  const tab = typeof getTab === 'function' ? getTab(targetTabId) : null;
  if (!tab || tab.st !== 'running' || tab.interactivePtyActive !== true) return null;
  const screen = Array.from(document.querySelectorAll('.pty-screen[data-pty-active="1"]'))
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

function _ptyHistoryLineMetadata(entry) {
  if (!entry || typeof entry !== 'object') return null;
  const metadata = {};
  if (Array.isArray(entry.signals) && entry.signals.length) metadata.signals = entry.signals;
  if (Number.isInteger(entry.line_index)) metadata.line_index = entry.line_index;
  if (typeof entry.command_root === 'string' && entry.command_root) metadata.command_root = entry.command_root;
  if (typeof entry.target === 'string' && entry.target) metadata.target = entry.target;
  return Object.keys(metadata).length ? metadata : null;
}

function _ptyEntryForTranscript(entry) {
  if (entry && typeof entry === 'object') {
    return {
      text: String(entry.text ?? ''),
      cls: String(entry.cls || ''),
      metadata: _ptyHistoryLineMetadata(entry),
    };
  }
  return { text: String(entry ?? ''), cls: '', metadata: null };
}

function _ptyFinalFrameEntries(entries) {
  const source = Array.isArray(entries) ? entries : [];
  const markerIndex = source.findLastIndex(entry => (
    entry && typeof entry === 'object' && String(entry.cls || '') === 'pty-marker'
  ));
  const frameEntries = markerIndex >= 0 ? source.slice(markerIndex + 1) : source;
  return frameEntries
    .filter(entry => !(entry && typeof entry === 'object' && String(entry.cls || '') === 'pty-marker'))
    .map(_ptyEntryForTranscript);
}

async function _ptyLoadSavedTranscript(runId) {
  if (!runId || typeof apiFetch !== 'function') return [];
  const resp = await apiFetch(`/history/${encodeURIComponent(runId)}?json&preview=1`);
  if (!resp || !resp.ok) throw new Error('Saved PTY output could not be loaded');
  const run = await resp.json();
  return _ptyFinalFrameEntries(Array.isArray(run.output_entries) ? run.output_entries : []);
}

async function _ptyAppendSavedTranscript(tabId, runId) {
  if (!runId) return;
  try {
    const entries = await _ptyLoadSavedTranscript(runId);
    if (!entries.length) return;
    if (typeof appendLines === 'function') {
      await appendLines(entries, tabId);
      return;
    }
    if (typeof appendLine === 'function') {
      entries.forEach(entry => appendLine(entry.text, entry.cls || '', tabId, entry.metadata || null));
    }
  } catch (_) {
    if (typeof appendLine === 'function') {
      appendLine('[notice] Saved interactive PTY output could not be loaded.', 'notice', tabId);
    }
  }
}

async function _ptyRunStillActive(runId) {
  if (!runId || typeof apiFetch !== 'function') return false;
  try {
    const resp = await apiFetch('/history/active');
    if (!resp || resp.ok === false || typeof resp.json !== 'function') return false;
    const data = await resp.json();
    const runs = Array.isArray(data && data.runs) ? data.runs : [];
    return runs.some(run => String(run && run.run_id || '') === String(runId));
  } catch (_) {
    return false;
  }
}

async function _ptyHandleStreamEndedWithoutExit(tabId, session) {
  const tab = typeof getTab === 'function' ? getTab(tabId) : null;
  const runId = String((session && session.runId) || (tab && (tab.historyRunId || tab.runId)) || '');
  const active = await _ptyRunStillActive(runId);
  if (active && tab && !tab.killed) {
    tab.reconnectedRun = true;
    tab.historyRunId = tab.historyRunId || runId;
    tab.interactivePtyActive = false;
    tab.ptyTerminal = null;
    if (session && session.screen && session.screen.dataset) session.screen.dataset.ptyActive = '0';
    if (session && session.term) session.term.options.disableStdin = true;
    _ptyDisposeResizeHandlers(session);
    if (session && session.term && typeof session.term.dispose === 'function') {
      session.term.dispose();
    }
    if (_ptyModalState.session === session) {
      _ptyModalState.session = null;
      _ptySetModalStatus('stream detached', 'fail');
      _ptyCloseModal({ force: true });
    }
    _ptyUpsertRunningIndicator(tabId, {
      state: 'detached',
      label: 'Interactive PTY still running',
      detail: 'Live terminal reattach is not available yet. Status Monitor can track or kill this run.',
      actionLabel: 'Reattach unavailable',
      actionDisabled: true,
    });
    if (typeof appendLine === 'function') {
      appendLine('[interactive PTY stream detached - process is still running]', 'notice', tabId);
      appendLine('[this tab will restore the saved result automatically when the run completes]', 'notice', tabId);
    }
    if (typeof setStatus === 'function' && tabId === activeTabId) setStatus('running');
    if (typeof setTabStatus === 'function') setTabStatus(tabId, 'running');
    if (typeof _setRunButtonDisabled === 'function') _setRunButtonDisabled(true);
    if (typeof showTabKillBtn === 'function') showTabKillBtn(tabId);
    if (typeof startPollingActiveRunsAfterReload === 'function') startPollingActiveRunsAfterReload();
    return;
  }
  await _ptyFinalize(tabId, session, { code: null });
}

async function _ptyFinalize(tabId, session, msg = {}) {
  const code = msg && Object.prototype.hasOwnProperty.call(msg, 'code') ? msg.code : null;
  const elapsed = msg && Object.prototype.hasOwnProperty.call(msg, 'elapsed') ? msg.elapsed : null;
  const tab = typeof getTab === 'function' ? getTab(tabId) : null;
  const runId = String((session && session.runId) || (tab && (tab.historyRunId || tab.runId)) || '');
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
  _ptyRemoveRunningIndicator(tabId);
  if (session && session.screen && session.screen.dataset) session.screen.dataset.ptyActive = '0';
  if (session && session.term) session.term.options.disableStdin = true;
  _ptyDisposeResizeHandlers(session);
  if (session && session.term && typeof session.term.dispose === 'function') {
    session.term.dispose();
  }
  if (_ptyModalState.session === session) {
    _ptyModalState.session = null;
    _ptyStopModalTimer(typeof elapsed === 'number' ? elapsed : null);
    _ptySetModalStatus(`exited ${code ?? 'unknown'}`, Number(code) === 0 ? 'ok' : 'fail');
    _ptyCloseModal({ force: true });
  }
  const killed = !!(tab && tab.killed);
  const ok = Number(code) === 0 || killed;
  if (!(tab && tab.closing)) {
    await _ptyAppendSavedTranscript(tabId, runId);
  }
  if (typeof appendLine === 'function') {
    const suffix = typeof elapsed === 'number' ? ` in ${elapsed}s` : '';
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
        if (session && session.term && typeof session.term.write === 'function') {
          session.term.write(msg.text || '');
          const out = typeof getOutput === 'function' ? getOutput(tabId) : null;
          if (out && tab.followOutput !== false) out.scrollTop = out.scrollHeight;
        }
      } else if (msg.type === 'notice' || msg.type === 'error') {
        if (session && session.term && typeof session.term.writeln === 'function') {
          session.term.writeln(`\r\n${msg.text || '[interactive PTY notice]'}`);
        } else if (typeof appendLine === 'function') {
          appendLine(msg.text || '[interactive PTY notice]', 'notice', tabId);
        }
      } else if (msg.type === 'killed') {
        tab.killed = true;
        tab.pendingKill = false;
        if (session && session.term && typeof session.term.writeln === 'function') {
          session.term.writeln('\r\n[interactive PTY kill requested]');
        } else if (typeof appendLine === 'function') {
          appendLine('[interactive PTY kill requested]', 'notice', tabId);
        }
      } else if (msg.type === 'exit') {
        await _ptyFinalize(tabId, session, msg);
        return;
      }
    }
  }
  await _ptyHandleStreamEndedWithoutExit(tabId, session);
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
  _ptyRemoveRunningIndicator(tabId);
  const ownsModal = !!(session && _ptyModalState.session === session);
  if (session && session.screen && session.screen.dataset) session.screen.dataset.ptyActive = '0';
  if (session && session.term) session.term.options.disableStdin = true;
  _ptyDisposeResizeHandlers(session);
  if (session && session.term && typeof session.term.dispose === 'function') {
    session.term.dispose();
  }
  if (ownsModal) {
    _ptyModalState.session = null;
    _ptyStopModalTimer();
    _ptyCloseModal({ force: true });
  } else if (!session && !_ptyModalState.session) {
    _ptyStopModalTimer();
    _ptyCloseModal({ force: true });
  }
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
  if (!_interactivePtyEnabled()) {
    if (typeof appendCommandEcho === 'function') appendCommandEcho(cmd, tabId);
    _failInteractivePtyTab(tabId, '[denied] Interactive PTY mode is disabled on this instance.');
    return;
  }
  if (_interactivePtyMobileUnsupported()) {
    if (typeof appendCommandEcho === 'function') appendCommandEcho(cmd, tabId);
    _failInteractivePtyTab(tabId, '[denied] Interactive PTY shells are only supported on desktop browsers.');
    return;
  }
  _prepareInteractivePtyTab(cmd, tabId);
  let session = null;
  try {
    const spec = _interactivePtySpecForCommand(cmd) || {};
    const rows = _ptyDefaultDimension(spec.default_rows, PTY_DEFAULT_ROWS, PTY_MIN_ROWS, 60);
    const cols = _ptyDefaultDimension(spec.default_cols, PTY_DEFAULT_COLS, PTY_MIN_COLS, 240);
    const size = { rows, cols };
    await _ensureXtermAssets();
    if (!_ptyPanelForTab(tabId)) throw new Error('Interactive PTY tab panel is not available');
    const res = await apiFetch('/pty/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        command: cmd,
        tab_id: tabId,
        rows: size.rows,
        cols: size.cols,
        workspace_cwd: typeof _workspaceCwd === 'function' ? _workspaceCwd(tabId) : '',
      }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.error || 'Interactive PTY command could not start');
    }
    const data = await res.json();
    const runId = data.run_id;
    if (!runId) throw new Error('Interactive PTY command did not return a run id');
    session = _ptyOpenModal(tabId, cmd, rows, cols);
    const tab = typeof getTab === 'function' ? getTab(tabId) : null;
    if (tab) tab.ptyTerminal = session.term;
    session.runId = runId;
    _ptyInstallKeyboardHandlers(session);
    session.inputDisposable = session.term.onData(dataChunk => _ptySendInput(runId, dataChunk, tabId));
    _ptyInstallResizeHandlers(session);
    _ptyStartModalTimer();
    _ptySetModalStatus('running', 'running');
    _ptySetModalKillEnabled(true);
    _ptySetModalCloseEnabled(true);
    _ptySetModalHideEnabled(true);
    if (typeof _markTabRunStarted === 'function') _markTabRunStarted(tabId, runId);
    _ptyPostResize(session);
    if (session.term && typeof session.term.focus === 'function') session.term.focus();
    const streamUrl = `${data.stream}?tab_id=${encodeURIComponent(tabId)}`;
    await _ptyReadStream(streamUrl, tabId, session);
  } catch (err) {
    _failInteractivePtyTab(tabId, `[server error] ${err.message || 'Interactive PTY failed'}`, session);
  }
}

_scheduleInteractivePtyAssetPreload();
if (typeof document !== 'undefined' && typeof document.addEventListener === 'function') {
  document.addEventListener('app:theme-changed', () => {
    _ptyApplyLiveTheme();
  });
}
