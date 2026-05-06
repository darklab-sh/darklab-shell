// Interactive PTY support for allowlisted screen tools. The backend owns the
// PTY process; xterm.js owns terminal rendering, keyboard input, and paste.

const PTY_DEFAULT_ROWS = 24;
const PTY_DEFAULT_COLS = 100;
const PTY_MIN_ROWS = 10;
const PTY_MIN_COLS = 40;
const PTY_INPUT_MAX_BYTES = 4096;
const _ptyModalState = {
  sessions: new Map(),
  activeSession: null,
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

function _ptyApplyLiveTheme(session = null) {
  if (!session) {
    let applied = false;
    _ptyModalState.sessions.forEach(activeSession => {
      applied = _ptyApplyLiveTheme(activeSession) || applied;
    });
    return applied;
  }
  if (!session.term) return false;
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
    body: JSON.stringify({ data: payload.text, tab_id: tabId || '' }),
  }).then(resp => {
    if (!resp || resp.ok) return;
    return (typeof _readRunErrorMessage === 'function' ? _readRunErrorMessage(resp) : Promise.resolve(''))
      .then(message => {
        if (message && typeof appendLine === 'function') {
          appendLine(`[interactive PTY input ignored: ${message}]`, 'notice', tabId || undefined);
        }
      });
  }).catch(() => {});
}

function _ptyConfirmSessionKill(session) {
  if (!session || !session.runId || !session.tabId) {
    _ptyCloseModal({ force: true }, session);
    return;
  }
  if (typeof confirmKill === 'function') confirmKill(session.tabId);
}

function _ptyConfirmSessionClose(session) {
  if (!session || !session.runId || !session.tabId) {
    _ptyCloseModal({ force: true }, session);
    return;
  }
  if (typeof confirmCloseRunningTab === 'function') {
    confirmCloseRunningTab(session.tabId);
    return;
  }
  _ptyConfirmSessionKill(session);
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

function _ptyModalRoot(target = null) {
  if (target && target.overlay) return target.overlay;
  if (typeof HTMLElement !== 'undefined' && target instanceof HTMLElement) return target;
  return document.getElementById('pty-overlay');
}

function _ptyModalEls(target = null) {
  const overlay = _ptyModalRoot(target);
  const find = (selector) => (overlay ? overlay.querySelector(selector) : null);
  return {
    overlay,
    modal: find('#pty-modal, .modal-card'),
    command: find('#pty-modal-command, .pty-modal-command'),
    status: find('#pty-modal-status, .pty-modal-status'),
    statusLabel: find('#pty-modal-status-label, .pty-modal-status-label'),
    elapsed: find('#pty-modal-elapsed, .pty-modal-elapsed'),
    screen: find('#pty-modal-screen, .pty-modal-screen'),
    closeBtn: find('.pty-modal-close'),
    killBtn: find('#pty-modal-kill, .pty-modal-kill'),
  };
}

function _ptyRemoveIds(root) {
  if (!root || typeof root.querySelectorAll !== 'function') return;
  root.removeAttribute('id');
  root.querySelectorAll('[id]').forEach(node => node.removeAttribute('id'));
}

function _ptyBuildOverlay() {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay mobile-sheet-overlay pty-tab-overlay u-hidden';
  overlay.setAttribute('aria-hidden', 'true');
  overlay.innerHTML = `
    <div class="modal-card mobile-sheet-surface pty-modal" role="dialog" aria-modal="false" aria-label="Interactive PTY">
      <div class="pty-modal-header">
        <div class="pty-modal-title-wrap">
          <span class="faq-title">INTERACTIVE PTY</span>
          <span class="pty-modal-command">waiting for command</span>
        </div>
        <div class="pty-modal-actions">
          <span class="pty-modal-status" data-tone="">
            <span class="pty-modal-status-label">waiting</span>
            <span class="pty-modal-elapsed">00:00</span>
          </span>
          <button type="button" class="btn btn-destructive btn-compact pty-modal-kill" disabled>Kill</button>
          <button type="button" class="close-btn pty-modal-close" aria-label="Close interactive PTY" disabled>✕</button>
        </div>
      </div>
      <section class="pty-screen pty-modal-screen" role="application" aria-label="Interactive PTY terminal"></section>
    </div>
  `;
  return overlay;
}

function _ptyOverlayForTab(tabId, { create = false } = {}) {
  const normalizedTabId = String(tabId || '');
  const existing = Array.from(document.querySelectorAll('.pty-tab-overlay'))
    .find(overlay => overlay.dataset && overlay.dataset.tabId === normalizedTabId);
  if (existing || !create) return existing || null;
  const base = document.getElementById('pty-overlay');
  const overlay = base && base.dataset.ptyAllocated !== '1' ? base : _ptyBuildOverlay();
  if (overlay !== base) _ptyRemoveIds(overlay);
  overlay.dataset.ptyAllocated = '1';
  overlay.dataset.tabId = normalizedTabId;
  return overlay;
}

function _ptySessionForOverlay(overlay) {
  const runId = overlay && overlay.dataset ? overlay.dataset.runId : '';
  if (runId) return _ptyModalState.sessions.get(runId) || null;
  return Array.from(_ptyModalState.sessions.values())
    .find(session => session && session.overlay === overlay) || null;
}

function _ptyPanelForTab(tabId) {
  if (!tabId) return null;
  if (typeof getTabPanel === 'function') return getTabPanel(tabId);
  return Array.from(document.querySelectorAll('.tab-panel'))
    .find(panel => panel.dataset && panel.dataset.id === String(tabId)) || null;
}

function _ptyScopeModalToTab(tabId, session = null) {
  const overlay = session && session.overlay
    ? session.overlay
    : _ptyOverlayForTab(tabId, { create: true });
  const panel = _ptyPanelForTab(tabId);
  if (!overlay || !panel) return false;
  if (overlay.parentElement !== panel) panel.appendChild(overlay);
  overlay.dataset.tabId = tabId;
  return true;
}

function _ptySetModalStatus(text, tone = '', session = null) {
  const { status: statusEl, statusLabel } = _ptyModalEls(session);
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

function _ptySetModalElapsed(totalSeconds = 0, session = null) {
  const { elapsed } = _ptyModalEls(session);
  if (elapsed) elapsed.textContent = _ptyFormatModalElapsed(totalSeconds);
}

function _ptyStopModalTimer(session = null, finalElapsed = null) {
  const target = session || _ptyModalState.activeSession;
  if (target && target.timer) {
    window.clearInterval(target.timer);
    target.timer = null;
  }
  if (target && typeof finalElapsed === 'number') _ptySetModalElapsed(finalElapsed, target);
}

function _ptyStartModalTimer(session) {
  if (!session) return;
  _ptyStopModalTimer(session);
  session.startedAt = Date.now();
  _ptySetModalElapsed(0, session);
  session.timer = window.setInterval(() => {
    if (!session.startedAt) return;
    _ptySetModalElapsed((Date.now() - session.startedAt) / 1000, session);
  }, 1000);
}

function _ptySetModalKillEnabled(enabled, session = null) {
  const { killBtn } = _ptyModalEls(session);
  if (killBtn) killBtn.disabled = !enabled;
}

function _ptySetModalCloseEnabled(enabled, session = null) {
  const { closeBtn } = _ptyModalEls(session);
  if (closeBtn) closeBtn.disabled = !enabled;
}

function _ptyIsModalOpen(session = null) {
  const { overlay } = _ptyModalEls(session);
  return !!(overlay && overlay.classList.contains('open'));
}

function _ptyLiveSessionForTab(tabId) {
  return Array.from(_ptyModalState.sessions.values())
    .find(session => session && session.tabId === tabId && session.runId) || null;
}

function _ptyCloseModal({ force = false } = {}, session = null) {
  const target = session || _ptyModalState.activeSession;
  const { overlay, screen } = _ptyModalEls(target);
  if (!force && target && target.runId) return;
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
  _ptyStopModalTimer(target);
  if (target) target.startedAt = 0;
  _ptySetModalElapsed(0, target);
  _ptySetModalKillEnabled(false, target);
  _ptySetModalCloseEnabled(true, target);
  if (_ptyModalState.activeSession === target) _ptyModalState.activeSession = null;
}

function _ptyKillModalRun(session = null) {
  _ptyConfirmSessionKill(session || _ptyModalState.activeSession);
}

function detachInteractivePtyForTab(tabId) {
  const session = _ptyLiveSessionForTab(tabId);
  const tab = typeof getTab === 'function' ? getTab(tabId) : null;
  if (tab) {
    tab.interactivePtyActive = false;
    tab.ptyTerminal = null;
  }
  if (!session) return false;
  if (session.term) session.term.options.disableStdin = true;
  _ptyDisposeResizeHandlers(session);
  session.detached = true;
  if (session.reader && typeof session.reader.cancel === 'function') {
    try {
      const cancelled = session.reader.cancel();
      if (cancelled && typeof cancelled.catch === 'function') cancelled.catch(() => {});
    } catch (_) {}
  }
  if (session.term && typeof session.term.dispose === 'function') {
    session.term.dispose();
  }
  if (session.runId) _ptyModalState.sessions.delete(session.runId);
  if (_ptyModalState.activeSession === session) _ptyModalState.activeSession = null;
  _ptyCloseModal({ force: true }, session);
  return true;
}

function _ptyBindModalOnce(session) {
  const { overlay, modal, killBtn, closeBtn } = _ptyModalEls(session);
  if (!overlay || !modal) return;
  if (overlay.dataset.ptyBound === '1') return;
  overlay.dataset.ptyBound = '1';
  if (killBtn) {
    killBtn.addEventListener('click', () => _ptyKillModalRun(_ptySessionForOverlay(overlay)));
  }
  if (typeof bindDismissible === 'function') {
    bindDismissible(overlay, {
      level: 'modal',
      isOpen: () => _ptyIsModalOpen(_ptySessionForOverlay(overlay)),
      onClose: () => _ptyConfirmSessionClose(_ptySessionForOverlay(overlay)),
      closeButtons: closeBtn,
      closeOnBackdrop: false,
    });
  }
  if (typeof bindFocusTrap === 'function') bindFocusTrap(modal);
}

function _ptyOpenModal(tabId, command, rows, cols, runId = '') {
  const overlay = _ptyOverlayForTab(tabId, { create: true });
  if (!overlay) throw new Error('Interactive PTY modal is not available');
  if (!_ptyScopeModalToTab(tabId, { overlay })) throw new Error('Interactive PTY tab panel is not available');
  overlay.dataset.runId = String(runId || '');
  const { command: commandEl, screen } = _ptyModalEls(overlay);
  if (!screen) throw new Error('Interactive PTY modal is not available');
  screen.replaceChildren();
  screen.dataset.ptyActive = '1';
  screen.dataset.tabId = tabId;
  screen.dataset.rows = String(rows);
  screen.dataset.cols = String(cols);
  if (commandEl) commandEl.textContent = command || 'interactive PTY';
  overlay.classList.remove('u-hidden');
  overlay.classList.add('open');
  overlay.setAttribute('aria-hidden', 'false');
  const session = _createPtyTerminalSession(screen, rows, cols);
  session.tabId = tabId;
  session.runId = String(runId || '');
  session.overlay = overlay;
  session.timer = null;
  session.startedAt = 0;
  _ptyModalState.sessions.set(session.runId, session);
  _ptyModalState.activeSession = session;
  _ptyBindModalOnce(session);
  _ptySetModalStatus('starting', 'running', session);
  _ptyStopModalTimer(session);
  _ptySetModalElapsed(0, session);
  _ptySetModalKillEnabled(false, session);
  _ptySetModalCloseEnabled(false, session);
  if (typeof markInteractionSurfaceReady === 'function') {
    markInteractionSurfaceReady('pty', overlay, _ptyModalEls(session).modal);
  }
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
  const session = _ptyLiveSessionForTab(targetTabId);
  if (session && session.screen && session.screen.dataset.ptyActive === '1') {
    return { screen: session.screen, term: session.term || tab.ptyTerminal || null };
  }
  const screen = Array.from(document.querySelectorAll('.pty-screen[data-pty-active="1"]'))
    .find(candidate => candidate.dataset && candidate.dataset.tabId === targetTabId);
  return screen ? { screen, term: tab.ptyTerminal || null } : null;
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

function _ptySnapshotEntries(entries) {
  return (Array.isArray(entries) ? entries : [])
    .filter(entry => !(entry && typeof entry === 'object' && String(entry.cls || '') === 'pty-marker'))
    .map(_ptyEntryForTranscript);
}

function _ptySnapshotText(entries) {
  return _ptySnapshotEntries(entries).map(entry => entry.text).join('\r\n');
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

async function _loadInteractivePtySnapshot(runId) {
  if (!runId || typeof apiFetch !== 'function') throw new Error('Missing PTY run id');
  const resp = await apiFetch(`/pty/runs/${encodeURIComponent(runId)}/snapshot`);
  if (!resp || !resp.ok) {
    const message = typeof _readRunErrorMessage === 'function'
      ? await _readRunErrorMessage(resp)
      : '';
    throw new Error(message || 'PTY snapshot is not available');
  }
  return resp.json();
}

function _prepareAttachedInteractivePtyTab(run, tabId) {
  const command = String(run && run.command || 'interactive PTY');
  if (typeof clearActiveRunDetachedForRestore === 'function') clearActiveRunDetachedForRestore(run.run_id);
  if (typeof clearTab === 'function') clearTab(tabId);
  const tab = typeof getTab === 'function' ? getTab(tabId) : null;
  if (!tab) return null;
  if (typeof setTabRunningCommand === 'function') {
    setTabRunningCommand(tabId, command);
  } else {
    if (!tab.renamed && typeof setTabLabel === 'function') setTabLabel(tabId, command);
    tab.command = command;
  }
  tab.runId = run.run_id;
  tab.historyRunId = run.run_id;
  tab.lastEventId = '';
  tab.attachMode = 'attached';
  tab.reconnectedRun = true;
  tab.killed = false;
  tab.pendingKill = false;
  tab.previewTruncated = false;
  tab.fullOutputAvailable = false;
  tab.fullOutputLoaded = false;
  tab.runStart = Number.isNaN(Date.parse(run.started)) ? Date.now() : Date.parse(run.started);
  tab.currentRunStartIndex = 0;
  tab.followOutput = true;
  tab.deferPromptMount = false;
  tab.interactivePtyActive = true;
  tab.ptyTerminal = null;
  if (typeof appendCommandEcho === 'function') appendCommandEcho(command, tabId);
  if (typeof appendLine === 'function') {
    appendLine('[reattached to active interactive PTY]', 'notice', tabId);
  }
  if (typeof setTabStatus === 'function') setTabStatus(tabId, 'running');
  if (tabId === activeTabId && typeof setStatus === 'function') setStatus('running');
  if (typeof showTabKillBtn === 'function') showTabKillBtn(tabId);
  if (typeof _setRunButtonDisabled === 'function') _setRunButtonDisabled(true);
  if (typeof syncActiveRunTimer === 'function' && tabId === activeTabId) syncActiveRunTimer(tabId);
  return tab;
}

async function attachInteractivePtyCommand(runOrRunId, tabId = '') {
  const run = typeof runOrRunId === 'object' && runOrRunId
    ? runOrRunId
    : { run_id: String(runOrRunId || '') };
  const runId = String(run.run_id || run.id || '').trim();
  if (!runId) return false;
  const snapshot = await _loadInteractivePtySnapshot(runId);
  const targetTabId = tabId || (typeof createTab === 'function' ? createTab() : '');
  if (!targetTabId) return false;
  if (typeof activateTab === 'function') activateTab(targetTabId, { focusComposer: false });
  const mergedRun = {
    ...run,
    ...snapshot,
    run_id: runId,
    command: snapshot.command || run.command || 'interactive PTY',
    started: snapshot.started || run.started || '',
  };
  const tab = _prepareAttachedInteractivePtyTab(mergedRun, targetTabId);
  if (!tab) return false;
  await _ensureXtermAssets();
  const rows = _ptyDefaultDimension(snapshot.rows, PTY_DEFAULT_ROWS, PTY_MIN_ROWS, 60);
  const cols = _ptyDefaultDimension(snapshot.cols, PTY_DEFAULT_COLS, PTY_MIN_COLS, 240);
  const session = _ptyOpenModal(targetTabId, mergedRun.command, rows, cols, runId);
  tab.ptyTerminal = session.term;
  _ptyInstallKeyboardHandlers(session);
  session.inputDisposable = session.term.onData(dataChunk => _ptySendInput(runId, dataChunk, targetTabId));
  _ptyInstallResizeHandlers(session);
  _ptyStartModalTimer(session);
  _ptySetModalStatus('running', 'running', session);
  _ptySetModalKillEnabled(true, session);
  _ptySetModalCloseEnabled(true, session);
  const ansiSnapshot = snapshot.snapshot_format === 'ansi' && typeof snapshot.ansi_snapshot === 'string'
    ? snapshot.ansi_snapshot
    : '';
  if (ansiSnapshot && session.term && typeof session.term.write === 'function') {
    session.term.write(ansiSnapshot);
    if (snapshot.snapshot_truncated && typeof appendLine === 'function') {
      appendLine('[reattached PTY snapshot truncated to the latest terminal state]', 'notice', targetTabId);
    }
  } else if (session.term && typeof session.term.writeln === 'function') {
    const snapshotText = _ptySnapshotText(snapshot.entries);
    if (snapshotText) session.term.write(`${snapshotText}\r\n`);
    session.term.writeln('[reattached - earlier formatting lost]');
  }
  _ptyPostResize(session);
  if (session.term && typeof session.term.focus === 'function') session.term.focus();
  const after = String(snapshot.after_event_id || '');
  const streamUrl = `/pty/runs/${encodeURIComponent(runId)}/stream?tab_id=${encodeURIComponent(targetTabId)}`
    + (after ? `&after=${encodeURIComponent(after)}` : '');
  _ptyReadStream(streamUrl, targetTabId, session).catch(err => {
    _failInteractivePtyTab(targetTabId, `[server error] ${err.message || 'Interactive PTY failed'}`, session);
  });
  return true;
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
    if (session && session.runId) _ptyModalState.sessions.delete(session.runId);
    if (session) {
      if (_ptyModalState.activeSession === session) _ptyModalState.activeSession = null;
      _ptySetModalStatus('stream detached', 'fail', session);
      _ptyCloseModal({ force: true }, session);
    }
    if (typeof appendLine === 'function') {
      appendLine('[interactive PTY stream detached - process is still running]', 'notice', tabId);
      appendLine('[use Status Monitor to reattach, track, or kill this run]', 'notice', tabId);
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
  if (session && session.screen && session.screen.dataset) session.screen.dataset.ptyActive = '0';
  if (session && session.term) session.term.options.disableStdin = true;
  _ptyDisposeResizeHandlers(session);
  if (session && session.term && typeof session.term.dispose === 'function') {
    session.term.dispose();
  }
  if (session && session.runId) _ptyModalState.sessions.delete(session.runId);
  if (session) {
    if (_ptyModalState.activeSession === session) _ptyModalState.activeSession = null;
    _ptyStopModalTimer(session, typeof elapsed === 'number' ? elapsed : null);
    _ptySetModalStatus(`exited ${code ?? 'unknown'}`, Number(code) === 0 ? 'ok' : 'fail', session);
    _ptyCloseModal({ force: true }, session);
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
  if (session) session.reader = reader;
  const decoder = new TextDecoder();
  let buf = '';
  while (true) {
    let chunk;
    try {
      chunk = await reader.read();
    } catch (err) {
      if (session && session.detached) return;
      throw err;
    }
    const { done, value } = chunk;
    if (session && session.detached) return;
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
  if (session && session.detached) return;
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
  const ownsModal = !!(session && _ptyModalState.activeSession === session);
  if (session && session.screen && session.screen.dataset) session.screen.dataset.ptyActive = '0';
  if (session && session.term) session.term.options.disableStdin = true;
  _ptyDisposeResizeHandlers(session);
  if (session && session.term && typeof session.term.dispose === 'function') {
    session.term.dispose();
  }
  if (session && session.runId) _ptyModalState.sessions.delete(session.runId);
  if (session) {
    if (ownsModal) _ptyModalState.activeSession = null;
    _ptyStopModalTimer(session);
    _ptyCloseModal({ force: true }, session);
  } else if (!session) {
    const orphanOverlay = _ptyOverlayForTab(tabId, { create: false });
    if (orphanOverlay && !_ptySessionForOverlay(orphanOverlay)) {
      _ptyCloseModal({ force: true }, { overlay: orphanOverlay });
    }
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
    session = _ptyOpenModal(tabId, cmd, rows, cols, runId);
    const tab = typeof getTab === 'function' ? getTab(tabId) : null;
    if (tab) tab.ptyTerminal = session.term;
    _ptyInstallKeyboardHandlers(session);
    session.inputDisposable = session.term.onData(dataChunk => _ptySendInput(runId, dataChunk, tabId));
    _ptyInstallResizeHandlers(session);
    _ptyStartModalTimer(session);
    _ptySetModalStatus('running', 'running', session);
    _ptySetModalKillEnabled(true, session);
    _ptySetModalCloseEnabled(true, session);
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
