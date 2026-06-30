import {
  DarklabRunOutputModel,
  _getTabPanelEl,
  _markTabRunStarted,
  _maybeMountDeferredPrompt,
  _workspaceCwd,
  activateTab,
  addToRecentPreview,
  appendCommandEcho,
  appendLine2 as appendLine,
  appendLines,
  clearActiveRunDetachedForRestore,
  clearTab2 as clearTab,
  confirmCloseRunningTab,
  confirmKill,
  createTab,
  finalizeClosingTab,
  getClientId,
  getOutput,
  refreshWorkspaceFileCache,
  setTabLabel,
  setTabRunningCommand,
  setTabStatus
} from "./static-chunk-neck7iig.fee9e04d3d57.js";
import "./static-chunk-poi5czx6.3f5c94749765.js";
import "./static-chunk-zpenfczu.1862ffb66041.js";
import {
  bindDismissible,
  bindFocusTrap
} from "./static-chunk-4m44pm74.0a8001fa1d52.js";
import {
  useMobileTerminalViewportMode
} from "./static-chunk-2bgb52uq.a327269283bb.js";
import {
  _readRunErrorMessage,
  _setRunButtonDisabled,
  _sseMessageFromChunk,
  emitUiEvent,
  getActiveTabId,
  getTab,
  hasHistoryPanelHandler,
  hideTabKillBtn,
  isHistoryPanelOpen,
  markInteractionSurfaceReady,
  refocusComposerAfterAction,
  refreshHistoryPanel,
  setStatus,
  showTabKillBtn,
  startPollingActiveRunsAfterReload,
  startTimer,
  stopTimer,
  syncActiveRunTimer
} from "./static-chunk-yo5cjr7d.b86e0c93eff0.js";
import {
  getAppConfig
} from "./static-chunk-gwztcp24.e58b5ff85d88.js";
import {
  apiFetch,
  hasRuntimeHandler,
  logClientError
} from "./static-chunk-2kxtimik.c9801087c7a7.js";

// app/static/js/pty.js
var PTY_DEFAULT_ROWS = 24;
var PTY_DEFAULT_COLS = 100;
var PTY_MIN_ROWS = 10;
var PTY_MIN_COLS = 40;
var PTY_INPUT_MAX_BYTES = 4096;
var PTY_INPUT_BATCH_MS = 16;
var PTY_RESIZE_POST_DELAY_MS = 120;
var PTY_STALE_SNAPSHOT_NOTICE_SECONDS = 5;
var _ptyModalState = {
  sessions: /* @__PURE__ */ new Map(),
  activeSession: null,
  pendingInput: /* @__PURE__ */ new Map()
};
var _xtermAssetsPromise = null;
var _xtermAssetPreloadScheduled = false;
var PTY_GLOBAL = typeof window !== "undefined" ? window : globalThis;
function _ptyGlobalFunction(name) {
  const fn = PTY_GLOBAL && PTY_GLOBAL[name];
  return typeof fn === "function" ? fn : null;
}
function _ptyGlobalValue(name) {
  return PTY_GLOBAL ? PTY_GLOBAL[name] : void 0;
}
function _ptyAppConfig() {
  const importedConfig = typeof getAppConfig === "function" ? getAppConfig() : null;
  const globalConfig = _ptyGlobalValue("APP_CONFIG") || null;
  if (importedConfig && globalConfig && importedConfig !== globalConfig) {
    return { ...importedConfig, ...globalConfig };
  }
  return importedConfig || globalConfig || {};
}
function _ptyActiveTabId() {
  if (typeof getActiveTabId === "function") return getActiveTabId();
  const read = _ptyGlobalFunction("getActiveTabId");
  return read ? read() : null;
}
function _ptyGetTab(tabId) {
  if (typeof getTab === "function") return getTab(tabId);
  const read = _ptyGlobalFunction("getTab");
  return read ? read(tabId) : null;
}
function _ptyApiFetch(...args) {
  const fetcher = (typeof hasRuntimeHandler === "function" && hasRuntimeHandler("apiFetch") && typeof apiFetch === "function" ? apiFetch : null) || _ptyGlobalFunction("apiFetch");
  if (!fetcher) throw new Error("apiFetch is unavailable");
  return fetcher(...args);
}
function _ptyLogClientError(...args) {
  const log = (typeof hasRuntimeHandler === "function" && hasRuntimeHandler("logClientError") && typeof logClientError === "function" ? logClientError : null) || _ptyGlobalFunction("logClientError");
  if (log) log(...args);
}
function _ptyLogClientEvent(context, err, details = {}) {
  _ptyLogClientError(context, err, details);
}
function _ptyRefreshHistoryPanelIfOpen() {
  const isOpen = typeof isHistoryPanelOpen === "function" && isHistoryPanelOpen || _ptyGlobalFunction("isHistoryPanelOpen");
  const refresh = (typeof hasHistoryPanelHandler === "function" && hasHistoryPanelHandler("refreshHistoryPanel") && typeof refreshHistoryPanel === "function" ? refreshHistoryPanel : null) || _ptyGlobalFunction("refreshHistoryPanel");
  if (isOpen && isOpen() && refresh) refresh();
}
function _refreshWorkspaceFileCache() {
  const refresh = typeof refreshWorkspaceFileCache !== "undefined" && refreshWorkspaceFileCache || _ptyGlobalFunction("refreshWorkspaceFileCache");
  if (typeof refresh === "function") return refresh();
  return null;
}
function _ptyClearActiveRunDetachedForRestore(runId) {
  const clear = typeof clearActiveRunDetachedForRestore !== "undefined" && clearActiveRunDetachedForRestore || _ptyGlobalFunction("clearActiveRunDetachedForRestore");
  if (typeof clear === "function") clear(runId);
}
function _ptyCall(name, importedOrFirstArg = void 0, ...rest) {
  const imported = typeof importedOrFirstArg === "function" ? importedOrFirstArg : null;
  const args = imported ? rest : arguments.length > 1 ? [importedOrFirstArg, ...rest] : [];
  const fn = imported || _ptyGlobalFunction(name);
  return fn ? fn(...args) : void 0;
}
function _ptyAppendLine(...args) {
  const append = typeof appendLine === "function" && appendLine || _ptyGlobalFunction("appendLine");
  return append ? append(...args) : void 0;
}
function _ptyAppendLines(...args) {
  const append = typeof appendLines === "function" && appendLines || _ptyGlobalFunction("appendLines");
  return append ? append(...args) : void 0;
}
function _ptyAppendCommandEcho(...args) {
  const append = typeof appendCommandEcho === "function" && appendCommandEcho || _ptyGlobalFunction("appendCommandEcho");
  return append ? append(...args) : void 0;
}
function _ptySetStatus(status) {
  _ptyCall("setStatus", setStatus, status);
}
function _ptySetRunButtonDisabled(disabled) {
  _ptyCall("_setRunButtonDisabled", _setRunButtonDisabled, disabled);
}
function _ptyShowTabKillBtn(tabId) {
  const show = typeof showTabKillBtn === "function" && showTabKillBtn || _ptyGlobalFunction("showTabKillBtn");
  if (show) show(tabId);
}
function _ptyHideTabKillBtn(tabId) {
  const hide = typeof hideTabKillBtn === "function" && hideTabKillBtn || _ptyGlobalFunction("hideTabKillBtn");
  if (hide) hide(tabId);
}
function _ptyStartPollingActiveRunsAfterReload() {
  const start = typeof startPollingActiveRunsAfterReload === "function" && startPollingActiveRunsAfterReload || _ptyGlobalFunction("startPollingActiveRunsAfterReload");
  if (start) start();
}
function _ptySyncActiveRunTimer(tabId) {
  const sync = typeof syncActiveRunTimer === "function" && syncActiveRunTimer || _ptyGlobalFunction("syncActiveRunTimer");
  if (sync) sync(tabId);
}
function _ptyStartTimer(...args) {
  const start = typeof startTimer === "function" && startTimer || _ptyGlobalFunction("startTimer");
  if (start) start(...args);
}
function _ptyStopTimer() {
  const stop = typeof stopTimer === "function" && stopTimer || _ptyGlobalFunction("stopTimer");
  if (stop) stop();
}
function _ptyReadRunErrorMessage(resp) {
  const read = typeof _readRunErrorMessage === "function" && _readRunErrorMessage || _ptyGlobalFunction("_readRunErrorMessage");
  return read ? read(resp) : Promise.resolve("");
}
function _ptySseMessageFromChunk(part) {
  const parse = typeof _sseMessageFromChunk === "function" && _sseMessageFromChunk || _ptyGlobalFunction("_sseMessageFromChunk");
  if (parse) return parse(part);
  let eventId = "";
  const dataLines = [];
  String(part || "").split(/\r?\n/).forEach((line) => {
    if (line.startsWith("id: ")) eventId = line.slice(4).trim();
    else if (line.startsWith("data: ")) dataLines.push(line.slice(6));
  });
  if (!dataLines.length) return null;
  const msg = JSON.parse(dataLines.join("\n"));
  if (eventId && msg && typeof msg === "object" && !msg.event_id) msg.event_id = eventId;
  return msg;
}
function _splitPtyCommand(cmd) {
  return String(cmd || "").trim().match(/"[^"]*"|'[^']*'|\S+/g) || [];
}
function _interactivePtySpecs() {
  const config = _ptyAppConfig();
  const configured = Array.isArray(config.interactive_pty_commands) ? config.interactive_pty_commands : [];
  if (configured.length) return configured;
  return [{
    root: "mtr",
    trigger_flag: "--interactive",
    default_rows: PTY_DEFAULT_ROWS,
    default_cols: PTY_DEFAULT_COLS,
    requires_args: true
  }];
}
function _interactivePtySpecForCommand(cmd) {
  const parts = _splitPtyCommand(cmd);
  const root = (parts[0] || "").toLowerCase();
  if (!root) return null;
  return _interactivePtySpecs().find((spec) => {
    const specRoot = String(spec && spec.root || "").toLowerCase();
    const trigger = String(spec && spec.trigger_flag || "");
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
  return typeof globalThis.Terminal === "function" && globalThis.FitAddon && typeof globalThis.FitAddon.FitAddon === "function";
}
function _interactivePtyEnabled() {
  return _ptyAppConfig().interactive_pty_enabled === true;
}
function _interactivePtyMobileUnsupported() {
  const useMobile = typeof useMobileTerminalViewportMode === "function" && useMobileTerminalViewportMode || _ptyGlobalFunction("useMobileTerminalViewportMode");
  if (useMobile) {
    return !!useMobile();
  }
  return !!(typeof document !== "undefined" && document.body && document.body.classList.contains("mobile-terminal-mode"));
}
function _ptyLazyAssetUrl(name, fallback) {
  const lazyAssetUrl = _ptyGlobalFunction("lazyAssetUrl");
  if (lazyAssetUrl) {
    const configured = lazyAssetUrl(name);
    if (configured) return configured;
  }
  return fallback;
}
function _loadPtyStylesheetOnce(href) {
  const selector = `link[rel="stylesheet"][href="${href}"]`;
  const existing = document.querySelector(selector);
  if (existing && existing.dataset && existing.dataset.ptyLoadState === "error") {
    existing.remove();
  } else if (existing) {
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = href;
    link.dataset.ptyLoadState = "loading";
    link.onload = () => {
      link.dataset.ptyLoadState = "loaded";
      resolve();
    };
    link.onerror = () => {
      link.dataset.ptyLoadState = "error";
      reject(new Error(`Could not load ${href}`));
    };
    document.head.appendChild(link);
  });
}
function _loadPtyScriptOnce(src, globalReady) {
  if (typeof globalReady === "function" && globalReady()) return Promise.resolve();
  const existing = document.querySelector(`script[src="${src}"]`);
  if (existing) {
    const loadState = existing.dataset ? existing.dataset.ptyLoadState : "";
    if (loadState === "error" || loadState === "loaded") {
      existing.remove();
      return _loadPtyScriptOnce(src, globalReady);
    }
    return new Promise((resolve, reject) => {
      if (typeof globalReady === "function" && globalReady()) {
        resolve();
        return;
      }
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener("error", () => reject(new Error(`Could not load ${src}`)), { once: true });
    });
  }
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.dataset.ptyLoadState = "loading";
    script.onload = () => {
      script.dataset.ptyLoadState = "loaded";
      resolve();
    };
    script.onerror = () => {
      script.dataset.ptyLoadState = "error";
      reject(new Error(`Could not load ${src}`));
    };
    document.head.appendChild(script);
  });
}
function _ensureXtermAssets() {
  if (!_xtermAssetsPromise) {
    const xtermCssUrl = _ptyLazyAssetUrl("xterm_css", "/vendor/xterm.css");
    const xtermJsUrl = _ptyLazyAssetUrl("xterm_js", "/vendor/xterm.js");
    const xtermFitJsUrl = _ptyLazyAssetUrl("xterm_fit_js", "/vendor/xterm-addon-fit.js");
    _xtermAssetsPromise = _loadPtyStylesheetOnce(xtermCssUrl).then(() => _loadPtyScriptOnce(xtermJsUrl, () => typeof globalThis.Terminal === "function")).then(() => _loadPtyScriptOnce(xtermFitJsUrl, () => globalThis.FitAddon && typeof globalThis.FitAddon.FitAddon === "function")).then(() => {
      if (!_xtermGlobalsAvailable()) throw new Error("Interactive terminal assets did not load");
    }).catch((err) => {
      _xtermAssetsPromise = null;
      throw err;
    });
  }
  return _xtermAssetsPromise;
}
function preloadInteractivePtyAssets() {
  if (!_interactivePtyEnabled()) return null;
  return _ensureXtermAssets().catch((err) => {
    _ptyLogClientError("failed to preload interactive PTY assets", err);
    return null;
  });
}
function _scheduleInteractivePtyAssetPreload() {
  if (_xtermAssetPreloadScheduled || !_interactivePtyEnabled()) return false;
  _xtermAssetPreloadScheduled = true;
  const preload = () => {
    void preloadInteractivePtyAssets();
  };
  if (typeof window !== "undefined" && typeof window.requestIdleCallback === "function") {
    window.requestIdleCallback(preload, { timeout: 1e3 });
  } else if (typeof window !== "undefined" && typeof window.setTimeout === "function") {
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
    background: "transparent",
    foreground: value("--fg", "#d8d8d8"),
    cursor: value("--green", "#90ee90"),
    selectionBackground: "rgba(144, 238, 144, 0.24)",
    black: value("--bg", "#05070a"),
    brightBlack: value("--muted", "#8a8f98"),
    white: value("--fg", "#d8d8d8"),
    brightWhite: value("--fg-bright", "#ffffff"),
    green: value("--green", "#90ee90"),
    brightGreen: value("--green", "#90ee90"),
    red: value("--danger", "#ff6b6b"),
    brightRed: value("--danger", "#ff6b6b"),
    yellow: value("--warning", "#f4d35e"),
    brightYellow: value("--warning", "#f4d35e"),
    blue: value("--link", "#8ab4ff"),
    brightBlue: value("--link", "#8ab4ff")
  };
}
function _ptyApplyLiveTheme(session = null) {
  if (!session) {
    let applied = false;
    _ptyModalState.sessions.forEach((activeSession) => {
      applied = _ptyApplyLiveTheme(activeSession) || applied;
    });
    return applied;
  }
  if (!session.term) return false;
  const nextTheme = _xtermTheme();
  try {
    if (session.term.options && typeof session.term.options === "object") {
      session.term.options.theme = nextTheme;
    } else if (typeof session.term.setOption === "function") {
      session.term.setOption("theme", nextTheme);
    } else {
      return false;
    }
    if (typeof session.term.refresh === "function") {
      session.term.refresh(0, Math.max(0, (session.term.rows || 1) - 1));
    }
    return true;
  } catch (err) {
    _ptyLogClientError("failed to refresh interactive PTY theme", err);
    return false;
  }
}
function _terminalFontSize() {
  if (!globalThis.getComputedStyle) return 13;
  const root = getComputedStyle(document.documentElement);
  const raw = root.getPropertyValue("--terminal-font-size").trim();
  const parsed = Number.parseFloat(raw || "");
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 13;
}
function _terminalLineHeight() {
  if (!globalThis.getComputedStyle) return 1.35;
  const root = getComputedStyle(document.documentElement);
  const raw = root.getPropertyValue("--terminal-line-height").trim();
  const parsed = Number.parseFloat(raw || "");
  if (!Number.isFinite(parsed) || parsed <= 0) return 1.35;
  return Math.max(1.35, Math.min(parsed, 1.65));
}
function _createPtyTerminalSession(screen, rows = PTY_DEFAULT_ROWS, cols = PTY_DEFAULT_COLS) {
  if (!_xtermGlobalsAvailable()) {
    throw new Error("Interactive terminal assets did not load");
  }
  const term = new globalThis.Terminal({
    allowProposedApi: false,
    cols,
    convertEol: false,
    cursorBlink: true,
    disableStdin: false,
    fontFamily: "var(--font-mono)",
    fontSize: _terminalFontSize(),
    lineHeight: _terminalLineHeight(),
    rows,
    scrollback: 1e3,
    theme: _xtermTheme()
  });
  const fitAddon = new globalThis.FitAddon.FitAddon();
  term.loadAddon(fitAddon);
  term.open(screen);
  return {
    screen,
    term,
    fitAddon,
    mirrorText: "",
    runId: "",
    inputDisposable: null,
    resizeObserver: null,
    resizeListener: null,
    resizeDisposable: null,
    resizePostTimer: null,
    lastResizeKey: ""
  };
}
function _ptyStripAnsi(text) {
  return String(text || "").replace(/\x1B\[[0-?]*[ -/]*[@-~]/g, "");
}
function _ptyMirrorWrite(session, text, { reset = false, newline = false } = {}) {
  if (!session || !session.screen || typeof text !== "string") return;
  const normalized = _ptyStripAnsi(text).replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  session.mirrorText = reset ? normalized : `${session.mirrorText || ""}${normalized}`;
  if (newline && session.mirrorText && !session.mirrorText.endsWith("\n")) {
    session.mirrorText += "\n";
  }
  session.screen.setAttribute("data-pty-transcript", session.mirrorText);
  let mirror = session.screen.querySelector(".pty-screen-text-mirror");
  if (!mirror) {
    mirror = document.createElement("span");
    mirror.className = "pty-screen-text-mirror";
    mirror.style.cssText = "position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden;white-space:pre-wrap;";
    session.screen.appendChild(mirror);
  }
  mirror.textContent = session.mirrorText;
}
function _ptyFit(session) {
  if (!session || !session.fitAddon) return;
  if (!_ptySessionIsVisible(session)) return;
  try {
    session.fitAddon.fit();
  } catch (_) {
  }
}
function _ptySize(session) {
  const rows = Number(session && session.term && session.term.rows) || PTY_DEFAULT_ROWS;
  const cols = Number(session && session.term && session.term.cols) || PTY_DEFAULT_COLS;
  return {
    rows: Math.max(PTY_MIN_ROWS, rows),
    cols: Math.max(PTY_MIN_COLS, cols)
  };
}
function _ptyPostResize(session) {
  if (!session || !session.runId) return;
  if (!_ptySessionIsVisible(session)) return;
  const size = _ptySize(session);
  const sizeKey = `${size.rows}x${size.cols}`;
  if (session.lastResizeKey === sizeKey && !session.resizePostTimer) return;
  if (session.resizePostTimer) {
    clearTimeout(session.resizePostTimer);
    session.resizePostTimer = null;
  }
  session.resizePostTimer = setTimeout(() => {
    session.resizePostTimer = null;
    if (!session.runId || !_ptySessionIsVisible(session)) return;
    const latestSize = _ptySize(session);
    const latestKey = `${latestSize.rows}x${latestSize.cols}`;
    if (session.lastResizeKey === latestKey) return;
    session.lastResizeKey = latestKey;
    _ptyApiFetch(`/pty/runs/${encodeURIComponent(session.runId)}/resize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(latestSize)
    }).catch(() => {
      session.lastResizeKey = "";
    });
  }, PTY_RESIZE_POST_DELAY_MS);
}
function _ptySessionIsVisible(session) {
  const screen = session && session.screen;
  if (!screen || !screen.isConnected) return false;
  const overlay = session.overlay || screen.closest(".pty-tab-overlay");
  if (overlay && overlay.getAttribute("aria-hidden") === "true") return false;
  const panel = screen.closest(".tab-panel");
  if (panel && !panel.classList.contains("active")) return false;
  return true;
}
function _ptyFitVisibleSessions() {
  _ptyModalState.sessions.forEach((session) => {
    if (!_ptySessionIsVisible(session)) return;
    _ptyFit(session);
    _ptyPostResize(session);
    if (session.term && typeof session.term.focus === "function") session.term.focus();
  });
}
function _ptyInstallResizeHandlers(session) {
  if (!session || !session.term) return;
  session.resizeDisposable = session.term.onResize(() => _ptyPostResize(session));
  const scheduleFit = () => {
    window.requestAnimationFrame(() => _ptyFit(session));
  };
  session.resizeListener = scheduleFit;
  window.addEventListener("resize", scheduleFit);
  if (typeof ResizeObserver === "function" && session.screen) {
    session.resizeObserver = new ResizeObserver(scheduleFit);
    session.resizeObserver.observe(session.screen);
  }
}
function _ptyDisposeResizeHandlers(session) {
  if (!session) return;
  if (session.runId) _ptyFlushInputQueue(session.runId, session.tabId || "");
  if (session.resizePostTimer) {
    clearTimeout(session.resizePostTimer);
    session.resizePostTimer = null;
  }
  if (session.inputDisposable && typeof session.inputDisposable.dispose === "function") {
    session.inputDisposable.dispose();
  }
  if (session.resizeDisposable && typeof session.resizeDisposable.dispose === "function") {
    session.resizeDisposable.dispose();
  }
  if (session.resizeObserver) session.resizeObserver.disconnect();
  if (session.resizeListener) window.removeEventListener("resize", session.resizeListener);
  session.inputDisposable = null;
  session.resizeDisposable = null;
  session.resizeObserver = null;
  session.resizeListener = null;
  if (session.runId) _ptyClearInputQueue(session.runId, session.tabId || "");
}
function _ptyInputPayload(data) {
  const text = String(data || "");
  if (!text || typeof TextEncoder !== "function") return { text, truncated: false };
  const encoder = new TextEncoder();
  if (encoder.encode(text).length <= PTY_INPUT_MAX_BYTES) return { text, truncated: false };
  let bytes = 0;
  let value = "";
  for (const char of text) {
    const charBytes = encoder.encode(char).length;
    if (bytes + charBytes > PTY_INPUT_MAX_BYTES) break;
    bytes += charBytes;
    value += char;
  }
  return { text: value, truncated: true };
}
function _ptyInputQueueKey(runId, tabId = "") {
  return `${String(runId || "")}\0${String(tabId || "")}`;
}
function _ptyPostInput(runId, data, tabId = "") {
  if (!runId || !data) return;
  const payload = _ptyInputPayload(data);
  if (!payload.text) return;
  if (payload.truncated) {
    _ptyAppendLine("[interactive PTY input truncated to 4096 bytes]", "notice", tabId || void 0);
  }
  _ptyApiFetch(`/pty/runs/${encodeURIComponent(runId)}/input`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ data: payload.text, tab_id: tabId || "" })
  }).then((resp) => {
    if (!resp || resp.ok) return;
    return _ptyReadRunErrorMessage(resp).then((message) => {
      if (message) {
        _ptyAppendLine(`[interactive PTY input ignored: ${message}]`, "notice", tabId || void 0);
      }
    });
  }).catch(() => {
  });
}
function _ptyFlushInputQueue(runId, tabId = "") {
  const key = _ptyInputQueueKey(runId, tabId);
  const pending = _ptyModalState.pendingInput.get(key);
  if (!pending) return;
  window.clearTimeout(pending.timer);
  _ptyModalState.pendingInput.delete(key);
  _ptyPostInput(pending.runId, pending.data, pending.tabId);
}
function _ptyClearInputQueue(runId, tabId = "") {
  const key = _ptyInputQueueKey(runId, tabId);
  const pending = _ptyModalState.pendingInput.get(key);
  if (!pending) return;
  window.clearTimeout(pending.timer);
  _ptyModalState.pendingInput.delete(key);
}
function _ptySendInput(runId, data, tabId = "") {
  if (!runId || !data) return;
  const key = _ptyInputQueueKey(runId, tabId);
  const existing = _ptyModalState.pendingInput.get(key);
  if (existing) {
    existing.data += String(data || "");
    return;
  }
  const pending = {
    runId,
    tabId,
    data: String(data || ""),
    timer: window.setTimeout(() => _ptyFlushInputQueue(runId, tabId), PTY_INPUT_BATCH_MS)
  };
  _ptyModalState.pendingInput.set(key, pending);
}
function _ptyCurrentClientId() {
  if (typeof getClientId === "function") return String(getClientId() || "");
  const legacyClientId = PTY_GLOBAL && typeof PTY_GLOBAL.CLIENT_ID === "string" ? PTY_GLOBAL.CLIENT_ID : "";
  return String(legacyClientId || "");
}
function _ptyConfirmSessionKill(session) {
  if (!session || !session.runId || !session.tabId) {
    _ptyCloseModal({ force: true }, session);
    return;
  }
  const confirm = typeof confirmKill === "function" && confirmKill || _ptyGlobalFunction("confirmKill");
  if (confirm) confirm(session.tabId);
}
function _ptyConfirmSessionClose(session) {
  if (!session || !session.runId || !session.tabId) {
    _ptyCloseModal({ force: true }, session);
    return;
  }
  const confirmCloseTab = typeof confirmCloseRunningTab === "function" ? confirmCloseRunningTab : _ptyGlobalFunction("confirmCloseRunningTab");
  if (confirmCloseTab) {
    confirmCloseTab(session.tabId);
    return;
  }
  _ptyConfirmSessionKill(session);
}
function _ptyInstallKeyboardHandlers(session) {
  if (!session || !session.term || typeof session.term.attachCustomKeyEventHandler !== "function") return;
  session.term.attachCustomKeyEventHandler((event) => {
    if (event && event.type === "keydown" && event.ctrlKey && !event.altKey && !event.metaKey && !event.shiftKey && String(event.key || "").toLowerCase() === "c") {
      return true;
    }
    return true;
  });
}
function _ptyModalRoot(target = null) {
  if (target && target.overlay) return target.overlay;
  if (typeof HTMLElement !== "undefined" && target instanceof HTMLElement) return target;
  return document.getElementById("pty-overlay");
}
function _ptyModalEls(target = null) {
  const overlay = _ptyModalRoot(target);
  const find = (selector) => overlay ? overlay.querySelector(selector) : null;
  return {
    overlay,
    modal: find("#pty-modal, .modal-card"),
    command: find("#pty-modal-command, .pty-modal-command"),
    status: find("#pty-modal-status, .pty-modal-status"),
    statusLabel: find("#pty-modal-status-label, .pty-modal-status-label"),
    elapsed: find("#pty-modal-elapsed, .pty-modal-elapsed"),
    screen: find("#pty-modal-screen, .pty-modal-screen"),
    closeBtn: find(".pty-modal-close"),
    killBtn: find("#pty-modal-kill, .pty-modal-kill")
  };
}
function _ptyRemoveIds(root) {
  if (!root || typeof root.querySelectorAll !== "function") return;
  root.removeAttribute("id");
  root.querySelectorAll("[id]").forEach((node) => node.removeAttribute("id"));
}
function _ptyBuildOverlay() {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay mobile-sheet-overlay pty-tab-overlay u-hidden";
  overlay.setAttribute("aria-hidden", "true");
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
  const normalizedTabId = String(tabId || "");
  const existing = Array.from(document.querySelectorAll(".pty-tab-overlay")).find((overlay2) => overlay2.dataset && overlay2.dataset.tabId === normalizedTabId);
  if (existing || !create) return existing || null;
  const base = document.getElementById("pty-overlay");
  const overlay = base && base.dataset.ptyAllocated !== "1" ? base : _ptyBuildOverlay();
  if (overlay !== base) _ptyRemoveIds(overlay);
  overlay.classList.add("pty-tab-overlay");
  overlay.dataset.ptyAllocated = "1";
  overlay.dataset.tabId = normalizedTabId;
  return overlay;
}
function _ptySessionForOverlay(overlay) {
  const runId = overlay && overlay.dataset ? overlay.dataset.runId : "";
  if (runId) return _ptyModalState.sessions.get(runId) || null;
  return Array.from(_ptyModalState.sessions.values()).find((session) => session && session.overlay === overlay) || null;
}
function _ptyPanelForTab(tabId) {
  if (!tabId) return null;
  const getPanel = typeof _getTabPanelEl === "function" && _getTabPanelEl || _ptyGlobalFunction("getTabPanel");
  if (getPanel) return getPanel(tabId);
  return Array.from(document.querySelectorAll(".tab-panel")).find((panel) => panel.dataset && panel.dataset.id === String(tabId)) || null;
}
function _ptyScopeModalToTab(tabId, session = null) {
  const overlay = session && session.overlay ? session.overlay : _ptyOverlayForTab(tabId, { create: true });
  const panel = _ptyPanelForTab(tabId);
  if (!overlay || !panel) return false;
  if (overlay.parentElement !== panel) panel.appendChild(overlay);
  overlay.dataset.tabId = tabId;
  return true;
}
function _ptySetModalStatus(text, tone = "", session = null) {
  const { status: statusEl, statusLabel } = _ptyModalEls(session);
  if (!statusEl) return;
  if (statusLabel) statusLabel.textContent = text;
  else statusEl.textContent = text;
  statusEl.dataset.tone = tone;
}
function _ptyFormatModalElapsed(totalSeconds) {
  const value = Math.max(0, Math.floor(Number(totalSeconds) || 0));
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor(value % 3600 / 60);
  const seconds = value % 60;
  const two = (part) => String(part).padStart(2, "0");
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
  if (target && typeof finalElapsed === "number") _ptySetModalElapsed(finalElapsed, target);
}
function _ptyStartModalTimer(session) {
  if (!session) return;
  _ptyStopModalTimer(session);
  session.startedAt = Date.now();
  _ptySetModalElapsed(0, session);
  session.timer = window.setInterval(() => {
    if (!session.startedAt) return;
    _ptySetModalElapsed((Date.now() - session.startedAt) / 1e3, session);
  }, 1e3);
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
  return !!(overlay && overlay.classList.contains("open"));
}
function _ptyLiveSessionForTab(tabId) {
  return Array.from(_ptyModalState.sessions.values()).find((session) => session && session.tabId === tabId && session.runId) || null;
}
function _ptyCloseModal({ force = false } = {}, session = null) {
  const target = session || _ptyModalState.activeSession;
  const { overlay, screen } = _ptyModalEls(target);
  if (!force && target && target.runId) return;
  if (overlay) {
    overlay.classList.add("u-hidden");
    overlay.classList.remove("open");
    overlay.setAttribute("aria-hidden", "true");
    delete overlay.dataset.runId;
  }
  if (screen) {
    screen.dataset.ptyActive = "0";
    screen.dataset.tabId = "";
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
  const tab = _ptyGetTab(tabId);
  if (tab) {
    tab.interactivePtyActive = false;
    tab.ptyTerminal = null;
  }
  if (!session) return false;
  if (session.term) session.term.options.disableStdin = true;
  _ptyDisposeResizeHandlers(session);
  session.detached = true;
  if (session.reader && typeof session.reader.cancel === "function") {
    try {
      const cancelled = session.reader.cancel();
      if (cancelled && typeof cancelled.catch === "function") {
        cancelled.catch((err) => {
          _ptyLogClientEvent("pty client reader cancel failed", err, {
            event: "PTY_CLIENT_READER_CANCEL_FAILED",
            level: "warning",
            tab_id: String(tabId || ""),
            run_id: String(session.runId || ""),
            detached: session.detached === true,
            modal_active: _ptyModalState.activeSession === session
          });
        });
      }
    } catch (err) {
      _ptyLogClientEvent("pty client reader cancel failed", err, {
        event: "PTY_CLIENT_READER_CANCEL_FAILED",
        level: "warning",
        tab_id: String(tabId || ""),
        run_id: String(session.runId || ""),
        detached: session.detached === true,
        modal_active: _ptyModalState.activeSession === session
      });
    }
  }
  _ptyLogClientEvent("pty client detached", null, {
    event: "PTY_CLIENT_DETACHED",
    level: "debug",
    tab_id: String(tabId || ""),
    run_id: String(session.runId || "")
  });
  if (session.term && typeof session.term.dispose === "function") {
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
  if (overlay.dataset.ptyBound === "1") return;
  overlay.dataset.ptyBound = "1";
  if (killBtn) {
    killBtn.addEventListener("click", () => _ptyKillModalRun(_ptySessionForOverlay(overlay)));
  }
  const bindDismissible2 = typeof bindDismissible === "function" && bindDismissible || _ptyGlobalFunction("bindDismissible");
  if (bindDismissible2) {
    bindDismissible2(overlay, {
      level: "modal",
      isOpen: () => _ptyIsModalOpen(_ptySessionForOverlay(overlay)),
      onClose: () => _ptyConfirmSessionClose(_ptySessionForOverlay(overlay)),
      closeButtons: closeBtn,
      closeOnBackdrop: false
    });
  }
  const bindFocusTrap2 = typeof bindFocusTrap === "function" && bindFocusTrap || _ptyGlobalFunction("bindFocusTrap");
  if (bindFocusTrap2) bindFocusTrap2(modal);
}
function _ptyOpenModal(tabId, command, rows, cols, runId = "") {
  const overlay = _ptyOverlayForTab(tabId, { create: true });
  if (!overlay) throw new Error("Interactive PTY modal is not available");
  if (!_ptyScopeModalToTab(tabId, { overlay })) throw new Error("Interactive PTY tab panel is not available");
  overlay.dataset.runId = String(runId || "");
  const { command: commandEl, screen } = _ptyModalEls(overlay);
  if (!screen) throw new Error("Interactive PTY modal is not available");
  screen.replaceChildren();
  screen.dataset.ptyActive = "1";
  screen.dataset.tabId = tabId;
  screen.dataset.rows = String(rows);
  screen.dataset.cols = String(cols);
  if (commandEl) commandEl.textContent = command || "interactive PTY";
  overlay.classList.remove("u-hidden");
  overlay.classList.add("open");
  overlay.setAttribute("aria-hidden", "false");
  const session = _createPtyTerminalSession(screen, rows, cols);
  session.tabId = tabId;
  session.runId = String(runId || "");
  session.overlay = overlay;
  session.timer = null;
  session.startedAt = 0;
  _ptyModalState.sessions.set(session.runId, session);
  _ptyModalState.activeSession = session;
  _ptyBindModalOnce(session);
  _ptySetModalStatus("starting", "running", session);
  _ptyStopModalTimer(session);
  _ptySetModalElapsed(0, session);
  _ptySetModalKillEnabled(false, session);
  _ptySetModalCloseEnabled(false, session);
  const markReady = typeof markInteractionSurfaceReady === "function" && markInteractionSurfaceReady || _ptyGlobalFunction("markInteractionSurfaceReady");
  if (markReady) markReady("pty", overlay, _ptyModalEls(session).modal);
  _ptyFit(session);
  window.setTimeout(() => {
    _ptyFit(session);
    if (session.term && typeof session.term.focus === "function") session.term.focus();
  }, 100);
  return session;
}
function _activeInteractivePtySession(tabId = null) {
  const targetTabId = tabId || _ptyActiveTabId() || "";
  const tab = _ptyGetTab(targetTabId);
  if (!tab || tab.st !== "running" || tab.interactivePtyActive !== true) return null;
  const session = _ptyLiveSessionForTab(targetTabId);
  if (session && session.screen && session.screen.dataset.ptyActive === "1") {
    return { screen: session.screen, term: session.term || tab.ptyTerminal || null };
  }
  const screen = Array.from(document.querySelectorAll('.pty-screen[data-pty-active="1"]')).find((candidate) => candidate.dataset && candidate.dataset.tabId === targetTabId);
  return screen ? { screen, term: tab.ptyTerminal || null } : null;
}
function focusActiveInteractivePty({ preventScroll = true } = {}) {
  const session = _activeInteractivePtySession();
  if (!session || !session.screen) return false;
  if (session.term && typeof session.term.focus === "function") {
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
  if (!entry || typeof entry !== "object") return null;
  const metadata = {};
  if (Array.isArray(entry.signals) && entry.signals.length) metadata.signals = entry.signals;
  if (Number.isInteger(entry.line_index)) metadata.line_index = entry.line_index;
  if (typeof entry.command_root === "string" && entry.command_root) metadata.command_root = entry.command_root;
  if (typeof entry.target === "string" && entry.target) metadata.target = entry.target;
  return Object.keys(metadata).length ? metadata : null;
}
function _ptyEntryForTranscript(entry) {
  if (entry && typeof entry === "object") {
    const model = typeof DarklabRunOutputModel !== "undefined" && DarklabRunOutputModel || _ptyGlobalValue("DarklabRunOutputModel") || null;
    const event = model && typeof model.fromWireLineEvent === "function" ? model.fromWireLineEvent(entry) : null;
    const legacy = event && model && typeof model.toLegacyWireLineEvent === "function" ? model.toLegacyWireLineEvent(event) : entry;
    const line = {
      text: String((event && event.text) ?? entry.text ?? ""),
      cls: String(legacy && legacy.cls || entry.cls || ""),
      metadata: _ptyHistoryLineMetadata(legacy || entry)
    };
    if (event && event.kind) line.kind = event.kind;
    else if (typeof entry.kind === "string" && entry.kind) line.kind = entry.kind;
    if (event && event.role) line.role = event.role;
    else if (typeof entry.role === "string" && entry.role) line.role = entry.role;
    return line;
  }
  return { text: String(entry ?? ""), cls: "", metadata: null };
}
function _ptyEntryRole(entry) {
  const model = typeof DarklabRunOutputModel !== "undefined" && DarklabRunOutputModel || _ptyGlobalValue("DarklabRunOutputModel") || null;
  if (model && typeof model.fromWireLineEvent === "function") {
    return String(model.fromWireLineEvent(entry || {}).role || "body");
  }
  return String(entry && entry.role || entry && entry.cls || "body");
}
function _isPtyMarkerEntry(entry) {
  return entry && typeof entry === "object" && _ptyEntryRole(entry) === "pty-marker";
}
function _ptyFinalFrameEntries(entries) {
  const source = Array.isArray(entries) ? entries : [];
  const markerIndex = source.findLastIndex((entry) => _isPtyMarkerEntry(entry));
  const frameEntries = markerIndex >= 0 ? source.slice(markerIndex + 1) : source;
  return frameEntries.filter((entry) => !_isPtyMarkerEntry(entry)).map(_ptyEntryForTranscript);
}
async function _ptyLoadSavedTranscript(runId) {
  if (!runId) return [];
  const resp = await _ptyApiFetch(`/history/${encodeURIComponent(runId)}?json&preview=1`);
  if (!resp || !resp.ok) throw new Error("Saved PTY output could not be loaded");
  const run = await resp.json();
  return _ptyFinalFrameEntries(Array.isArray(run.output_entries) ? run.output_entries : []);
}
function _ptySnapshotEntries(entries) {
  return (Array.isArray(entries) ? entries : []).filter((entry) => !_isPtyMarkerEntry(entry)).map(_ptyEntryForTranscript);
}
function _ptySnapshotText(entries) {
  return _ptySnapshotEntries(entries).map((entry) => entry.text).join("\r\n");
}
async function _ptyAppendSavedTranscript(tabId, runId) {
  if (!runId) return;
  try {
    const entries = await _ptyLoadSavedTranscript(runId);
    if (!entries.length) return;
    if (typeof _ptyAppendLines === "function") {
      await _ptyAppendLines(entries, tabId);
      return;
    }
    entries.forEach((entry) => _ptyAppendLine(entry, tabId));
  } catch (_) {
    _ptyAppendLine("[notice] Saved interactive PTY output could not be loaded.", "notice", tabId);
  }
}
async function _loadInteractivePtySnapshot(runId) {
  if (!runId) throw new Error("Missing PTY run id");
  const resp = await _ptyApiFetch(`/pty/runs/${encodeURIComponent(runId)}/snapshot`);
  if (!resp || !resp.ok) {
    const message = await _ptyReadRunErrorMessage(resp);
    throw new Error(message || "PTY snapshot is not available");
  }
  return resp.json();
}
function _prepareAttachedInteractivePtyTab(run, tabId) {
  const command = String(run && run.command || "interactive PTY");
  _ptyClearActiveRunDetachedForRestore(run.run_id);
  const clearTab2 = typeof clearTab === "function" && clearTab || _ptyGlobalFunction("clearTab");
  if (clearTab2) clearTab2(tabId);
  const tab = _ptyGetTab(tabId);
  if (!tab) return null;
  const setRunningCommand = typeof setTabRunningCommand === "function" && setTabRunningCommand || _ptyGlobalFunction("setTabRunningCommand");
  const setLabel = typeof setTabLabel === "function" && setTabLabel || _ptyGlobalFunction("setTabLabel");
  if (setRunningCommand) {
    setRunningCommand(tabId, command);
  } else {
    if (!tab.renamed && setLabel) setLabel(tabId, command);
    tab.command = command;
  }
  tab.runId = run.run_id;
  tab.historyRunId = run.run_id;
  tab.lastEventId = "";
  tab.attachMode = "attached";
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
  _ptyAppendCommandEcho(command, tabId);
  _ptyAppendLine("[reattached to active interactive PTY]", "notice", tabId);
  const snapshotAge = Number(run && run.snapshot_age_seconds);
  if (Number.isFinite(snapshotAge) && snapshotAge >= PTY_STALE_SNAPSHOT_NOTICE_SECONDS) {
    _ptyAppendLine(`[reattached - snapshot was ${Math.round(snapshotAge)}s old]`, "notice", tabId);
  }
  const setTabStatus2 = typeof setTabStatus === "function" && setTabStatus || _ptyGlobalFunction("setTabStatus");
  if (setTabStatus2) setTabStatus2(tabId, "running");
  if (tabId === _ptyActiveTabId()) _ptySetStatus("running");
  _ptyShowTabKillBtn(tabId);
  _ptySetRunButtonDisabled(true);
  if (tabId === _ptyActiveTabId()) _ptySyncActiveRunTimer(tabId);
  return tab;
}
function _ptyDisplaceSession(tabId, session, msg = {}) {
  if (msg && msg.displaced_client_id && msg.displaced_client_id !== _ptyCurrentClientId()) return false;
  if (msg && msg.displaced_tab_id && msg.displaced_tab_id !== tabId) return false;
  const tab = _ptyGetTab(tabId);
  if (tab) {
    tab.runId = null;
    tab.reconnectedRun = false;
    tab.lastEventId = "";
    tab.attachMode = "";
    tab.interactivePtyActive = false;
    tab.ptyTerminal = null;
  }
  if (session && session.screen && session.screen.dataset) session.screen.dataset.ptyActive = "0";
  if (session && session.term) session.term.options.disableStdin = true;
  _ptyDisposeResizeHandlers(session);
  if (session && session.term && typeof session.term.dispose === "function") {
    session.term.dispose();
  }
  if (session && session.runId) _ptyModalState.sessions.delete(session.runId);
  if (session) {
    session.detached = true;
    if (_ptyModalState.activeSession === session) _ptyModalState.activeSession = null;
    _ptyStopModalTimer(session);
    _ptySetModalStatus("moved", "fail", session);
    _ptyCloseModal({ force: true }, session);
  }
  _ptyAppendLine(msg.text || "[interactive PTY moved to another tab]", "notice", tabId);
  const setTabStatus2 = typeof setTabStatus === "function" && setTabStatus || _ptyGlobalFunction("setTabStatus");
  if (setTabStatus2) setTabStatus2(tabId, "idle");
  if (tabId === _ptyActiveTabId()) _ptySetStatus("idle");
  _ptySetRunButtonDisabled(false);
  _ptyHideTabKillBtn(tabId);
  _ptyStartPollingActiveRunsAfterReload();
  return true;
}
async function attachInteractivePtyCommand(runOrRunId, tabId = "") {
  const run = typeof runOrRunId === "object" && runOrRunId ? runOrRunId : { run_id: String(runOrRunId || "") };
  const runId = String(run.run_id || run.id || "").trim();
  if (!runId) return false;
  const snapshot = await _loadInteractivePtySnapshot(runId);
  const createTab2 = typeof createTab === "function" && createTab || _ptyGlobalFunction("createTab");
  const targetTabId = tabId || (createTab2 ? createTab2() : "");
  if (!targetTabId) return false;
  const activateTab2 = typeof activateTab === "function" && activateTab || _ptyGlobalFunction("activateTab");
  if (activateTab2) activateTab2(targetTabId, { focusComposer: false });
  const mergedRun = {
    ...run,
    ...snapshot,
    run_id: runId,
    command: snapshot.command || run.command || "interactive PTY",
    started: snapshot.started || run.started || ""
  };
  const tab = _prepareAttachedInteractivePtyTab(mergedRun, targetTabId);
  if (!tab) return false;
  await _ensureXtermAssets();
  const rows = _ptyDefaultDimension(snapshot.rows, PTY_DEFAULT_ROWS, PTY_MIN_ROWS, 60);
  const cols = _ptyDefaultDimension(snapshot.cols, PTY_DEFAULT_COLS, PTY_MIN_COLS, 240);
  const session = _ptyOpenModal(targetTabId, mergedRun.command, rows, cols, runId);
  tab.ptyTerminal = session.term;
  _ptyInstallKeyboardHandlers(session);
  session.inputDisposable = session.term.onData((dataChunk) => _ptySendInput(runId, dataChunk, targetTabId));
  _ptyInstallResizeHandlers(session);
  _ptyStartModalTimer(session);
  _ptySetModalStatus("running", "running", session);
  _ptySetModalKillEnabled(true, session);
  _ptySetModalCloseEnabled(true, session);
  const ansiSnapshot = snapshot.snapshot_format === "ansi" && typeof snapshot.ansi_snapshot === "string" ? snapshot.ansi_snapshot : "";
  if (ansiSnapshot && session.term && typeof session.term.write === "function") {
    session.term.write(ansiSnapshot);
    _ptyMirrorWrite(session, ansiSnapshot, { reset: true });
    if (snapshot.snapshot_truncated) _ptyAppendLine("[reattached PTY snapshot truncated to the latest terminal state]", "notice", targetTabId);
  } else if (session.term && typeof session.term.writeln === "function") {
    const snapshotText = _ptySnapshotText(snapshot.entries);
    if (snapshotText) {
      session.term.write(`${snapshotText}\r
`);
      _ptyMirrorWrite(session, `${snapshotText}
`, { reset: true });
    }
    session.term.writeln("[reattached - earlier formatting lost]");
    _ptyMirrorWrite(session, "[reattached - earlier formatting lost]\n");
  }
  _ptyPostResize(session);
  if (session.term && typeof session.term.focus === "function") session.term.focus();
  const after = String(snapshot.after_event_id || "");
  const streamUrl = `/pty/runs/${encodeURIComponent(runId)}/stream?tab_id=${encodeURIComponent(targetTabId)}` + (after ? `&after=${encodeURIComponent(after)}` : "");
  _ptyReadStream(streamUrl, targetTabId, session).catch((err) => {
    _failInteractivePtyTab(targetTabId, `[server error] ${err.message || "Interactive PTY failed"}`, session);
  });
  return true;
}
async function _ptyRunStillActive(runId) {
  if (!runId) return false;
  try {
    const resp = await _ptyApiFetch("/history/active");
    if (!resp || resp.ok === false || typeof resp.json !== "function") return false;
    const data = await resp.json();
    const runs = Array.isArray(data && data.runs) ? data.runs : [];
    return runs.some((run) => String(run && run.run_id || "") === String(runId));
  } catch (_) {
    return false;
  }
}
async function _ptyHandleStreamEndedWithoutExit(tabId, session) {
  const tab = _ptyGetTab(tabId);
  const runId = String(session && session.runId || tab && (tab.historyRunId || tab.runId) || "");
  const active = await _ptyRunStillActive(runId);
  if (active && tab && !tab.killed) {
    tab.reconnectedRun = true;
    tab.historyRunId = tab.historyRunId || runId;
    tab.interactivePtyActive = false;
    tab.ptyTerminal = null;
    if (session && session.screen && session.screen.dataset) session.screen.dataset.ptyActive = "0";
    if (session && session.term) session.term.options.disableStdin = true;
    _ptyDisposeResizeHandlers(session);
    if (session && session.term && typeof session.term.dispose === "function") {
      session.term.dispose();
    }
    if (session && session.runId) _ptyModalState.sessions.delete(session.runId);
    if (session) {
      if (_ptyModalState.activeSession === session) _ptyModalState.activeSession = null;
      _ptySetModalStatus("stream detached", "fail", session);
      _ptyCloseModal({ force: true }, session);
    }
    _ptyAppendLine("[interactive PTY stream detached - process is still running]", "notice", tabId);
    _ptyAppendLine("[use Status Monitor to reattach, track, or kill this run]", "notice", tabId);
    if (tabId === _ptyActiveTabId()) _ptySetStatus("running");
    const setTabStatus2 = typeof setTabStatus === "function" && setTabStatus || _ptyGlobalFunction("setTabStatus");
    if (setTabStatus2) setTabStatus2(tabId, "running");
    _ptySetRunButtonDisabled(true);
    _ptyShowTabKillBtn(tabId);
    _ptyStartPollingActiveRunsAfterReload();
    return;
  }
  await _ptyFinalize(tabId, session, { code: null, stream_ended_without_exit: true });
}
async function _ptyFinalize(tabId, session, msg = {}) {
  const code = msg && Object.prototype.hasOwnProperty.call(msg, "code") ? msg.code : null;
  const elapsed = msg && Object.prototype.hasOwnProperty.call(msg, "elapsed") ? msg.elapsed : null;
  const streamEndedWithoutExit = !!(msg && msg.stream_ended_without_exit);
  const tab = _ptyGetTab(tabId);
  const runId = String(session && session.runId || tab && (tab.historyRunId || tab.runId) || "");
  if (tab) {
    tab.exitCode = code;
    tab.runId = null;
    tab.reconnectedRun = false;
    tab.lastEventId = "";
    tab.attachMode = "";
    tab.deferPromptMount = true;
    tab.previewTruncated = !!(msg && msg.preview_truncated);
    tab.fullOutputAvailable = !!(msg && msg.full_output_available);
    tab.fullOutputLoaded = !(msg && msg.preview_truncated);
    tab.interactivePtyActive = false;
    tab.ptyTerminal = null;
  }
  if (session && session.screen && session.screen.dataset) session.screen.dataset.ptyActive = "0";
  if (session && session.term) session.term.options.disableStdin = true;
  _ptyDisposeResizeHandlers(session);
  if (session && session.term && typeof session.term.dispose === "function") {
    session.term.dispose();
  }
  if (session && session.runId) _ptyModalState.sessions.delete(session.runId);
  if (session) {
    if (_ptyModalState.activeSession === session) _ptyModalState.activeSession = null;
    _ptyStopModalTimer(session, typeof elapsed === "number" ? elapsed : null);
    _ptySetModalStatus(`exited ${code ?? "unknown"}`, Number(code) === 0 ? "ok" : "fail", session);
    _ptyCloseModal({ force: true }, session);
  }
  const killed = !!(tab && tab.killed);
  const ok = code !== null && code !== void 0 && Number(code) === 0 || killed;
  if (!(tab && tab.closing)) {
    await _ptyAppendSavedTranscript(tabId, runId);
  }
  const suffix = typeof elapsed === "number" ? ` in ${elapsed}s` : "";
  const line = streamEndedWithoutExit ? "[interactive PTY stream ended before an exit event; run is no longer active]" : `[interactive PTY exited with code ${code ?? "unknown"}${suffix}]`;
  _ptyAppendLine(line, ok ? "exit-ok" : "exit-fail", tabId);
  const addRecent = typeof addToRecentPreview === "function" && addToRecentPreview || _ptyGlobalFunction("addToRecentPreview");
  if (addRecent && tab && tab.command && !tab.unknownCommand) addRecent(tab.command);
  const importedEmit = typeof emitUiEvent === "function" ? emitUiEvent : null;
  const globalEmit = _ptyGlobalFunction("emitUiEvent");
  const emit = importedEmit || globalEmit;
  if (emit) emit("app:last-exit-changed", { value: code });
  if (globalEmit && globalEmit !== emit) globalEmit("app:last-exit-changed", { value: code });
  _ptySetStatus(ok ? "ok" : "fail");
  const setTabStatus2 = typeof setTabStatus === "function" && setTabStatus || _ptyGlobalFunction("setTabStatus");
  if (setTabStatus2) setTabStatus2(tabId, ok ? "idle" : "fail");
  _ptyStopTimer();
  _ptySetRunButtonDisabled(false);
  _ptyHideTabKillBtn(tabId);
  const finalizeTabClose = typeof finalizeClosingTab === "function" ? finalizeClosingTab : _ptyGlobalFunction("finalizeClosingTab");
  if (tab && tab.closing && finalizeTabClose) {
    finalizeTabClose(tabId);
    _ptyRefreshHistoryPanelIfOpen();
    return;
  }
  _ptyRefreshHistoryPanelIfOpen();
  _refreshWorkspaceFileCache();
  const mountDeferredPrompt = typeof _maybeMountDeferredPrompt === "function" && _maybeMountDeferredPrompt || _ptyGlobalFunction("_maybeMountDeferredPrompt");
  if (mountDeferredPrompt) mountDeferredPrompt(tabId);
  const refocus = typeof refocusComposerAfterAction === "function" && refocusComposerAfterAction || _ptyGlobalFunction("refocusComposerAfterAction");
  if (tabId === _ptyActiveTabId() && refocus) {
    refocus({ preventScroll: true });
  }
}
async function _ptyReadStream(streamUrl, tabId, session) {
  const res = await _ptyApiFetch(streamUrl);
  if (!res.ok || !res.body) {
    let message = "Interactive stream failed";
    try {
      if (res && typeof res.json === "function") {
        const data = await res.json();
        if (data && data.error) message = String(data.error);
      }
    } catch (_) {
    }
    throw new Error(message);
  }
  const reader = res.body.getReader();
  if (session) session.reader = reader;
  const decoder = new TextDecoder();
  let buf = "";
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
    const parts = buf.split("\n\n");
    buf = parts.pop() || "";
    for (const part of parts) {
      const msg = _ptySseMessageFromChunk(part);
      if (!msg || msg.type === "heartbeat") continue;
      const tab = _ptyGetTab(tabId);
      if (!tab) continue;
      if (msg.type === "output") {
        if (session && session.term && typeof session.term.write === "function") {
          session.term.write(msg.text || "");
          _ptyMirrorWrite(session, msg.text || "");
          const getOutput2 = typeof getOutput === "function" && getOutput || _ptyGlobalFunction("getOutput");
          const out = getOutput2 ? getOutput2(tabId) : null;
          if (out && tab.followOutput !== false) out.scrollTop = out.scrollHeight;
        }
      } else if (msg.type === "notice" || msg.type === "error") {
        if (session && session.term && typeof session.term.writeln === "function") {
          session.term.writeln(`\r
${msg.text || "[interactive PTY notice]"}`);
          _ptyMirrorWrite(session, `
${msg.text || "[interactive PTY notice]"}
`);
        } else {
          _ptyAppendLine(msg.text || "[interactive PTY notice]", "notice", tabId);
        }
      } else if (msg.type === "killed") {
        tab.killed = true;
        tab.pendingKill = false;
        if (session && session.term && typeof session.term.writeln === "function") {
          session.term.writeln("\r\n[interactive PTY kill requested]");
          _ptyMirrorWrite(session, "\n[interactive PTY kill requested]\n");
        } else {
          _ptyAppendLine("[interactive PTY kill requested]", "notice", tabId);
        }
      } else if (msg.type === "exit") {
        await _ptyFinalize(tabId, session, msg);
        return;
      } else if (msg.type === "displaced") {
        if (_ptyDisplaceSession(tabId, session, msg)) return;
      }
    }
  }
  if (session && session.detached) return;
  await _ptyHandleStreamEndedWithoutExit(tabId, session);
}
function _prepareInteractivePtyTab(cmd, tabId) {
  const tab = _ptyGetTab(tabId);
  const setRunningCommand = typeof setTabRunningCommand === "function" && setTabRunningCommand || _ptyGlobalFunction("setTabRunningCommand");
  if (setRunningCommand) setRunningCommand(tabId, cmd);
  else if (tab) tab.command = cmd;
  _ptyAppendCommandEcho(cmd, tabId);
  if (tab) {
    tab.runStart = Date.now();
    tab.currentRunStartIndex = tab.rawLines.length;
    tab.previewTruncated = false;
    tab.fullOutputAvailable = false;
    tab.fullOutputLoaded = false;
    tab.historyRunId = null;
    tab.reconnectedRun = false;
    tab.lastEventId = "";
    tab.attachMode = "";
    tab.followOutput = true;
    tab.deferPromptMount = false;
    tab.interactivePtyActive = true;
    tab.ptyTerminal = null;
  }
  _ptySetStatus("running");
  const setTabStatus2 = typeof setTabStatus === "function" && setTabStatus || _ptyGlobalFunction("setTabStatus");
  if (setTabStatus2) setTabStatus2(tabId, "running");
  _ptySetRunButtonDisabled(true);
  _ptyShowTabKillBtn(tabId);
  _ptyStartTimer();
}
function _failInteractivePtyTab(tabId, message, session = null) {
  const tab = _ptyGetTab(tabId);
  if (tab) {
    tab.interactivePtyActive = false;
    tab.ptyTerminal = null;
  }
  const ownsModal = !!(session && _ptyModalState.activeSession === session);
  if (session && session.screen && session.screen.dataset) session.screen.dataset.ptyActive = "0";
  if (session && session.term) session.term.options.disableStdin = true;
  _ptyDisposeResizeHandlers(session);
  if (session && session.term && typeof session.term.dispose === "function") {
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
  _ptyAppendLine(message, "exit-fail", tabId);
  _ptySetStatus("fail");
  const setTabStatus2 = typeof setTabStatus === "function" && setTabStatus || _ptyGlobalFunction("setTabStatus");
  if (setTabStatus2) setTabStatus2(tabId, "fail");
  _ptyStopTimer();
  _ptySetRunButtonDisabled(false);
  _ptyHideTabKillBtn(tabId);
  const refocus = typeof refocusComposerAfterAction === "function" && refocusComposerAfterAction || _ptyGlobalFunction("refocusComposerAfterAction");
  if (tabId === _ptyActiveTabId() && refocus) {
    refocus({ preventScroll: true });
  }
}
async function startInteractivePtyCommand(cmd, tabId) {
  if (!_interactivePtyEnabled()) {
    _ptyAppendCommandEcho(cmd, tabId);
    _failInteractivePtyTab(tabId, "[denied] Interactive PTY mode is disabled on this instance.");
    return;
  }
  if (_interactivePtyMobileUnsupported()) {
    _ptyAppendCommandEcho(cmd, tabId);
    _failInteractivePtyTab(tabId, "[denied] Interactive PTY shells are only supported on desktop browsers.");
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
    if (!_ptyPanelForTab(tabId)) throw new Error("Interactive PTY tab panel is not available");
    const workspaceCwd = typeof _workspaceCwd === "function" && _workspaceCwd || _ptyGlobalFunction("_workspaceCwd");
    const res = await _ptyApiFetch("/pty/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        command: cmd,
        tab_id: tabId,
        rows: size.rows,
        cols: size.cols,
        workspace_cwd: workspaceCwd ? workspaceCwd(tabId) : ""
      })
    });
    if (!res.ok) {
      const data2 = await res.json().catch(() => ({}));
      throw new Error(data2.error || "Interactive PTY command could not start");
    }
    const data = await res.json();
    const runId = data.run_id;
    if (!runId) throw new Error("Interactive PTY command did not return a run id");
    session = _ptyOpenModal(tabId, cmd, rows, cols, runId);
    const tab = _ptyGetTab(tabId);
    if (tab) tab.ptyTerminal = session.term;
    _ptyInstallKeyboardHandlers(session);
    session.inputDisposable = session.term.onData((dataChunk) => _ptySendInput(runId, dataChunk, tabId));
    _ptyInstallResizeHandlers(session);
    _ptyStartModalTimer(session);
    _ptySetModalStatus("running", "running", session);
    _ptySetModalKillEnabled(true, session);
    _ptySetModalCloseEnabled(true, session);
    const markStarted = typeof _markTabRunStarted === "function" && _markTabRunStarted || _ptyGlobalFunction("_markTabRunStarted");
    if (markStarted) markStarted(tabId, runId);
    _ptyPostResize(session);
    if (session.term && typeof session.term.focus === "function") session.term.focus();
    const streamUrl = `${data.stream}?tab_id=${encodeURIComponent(tabId)}`;
    await _ptyReadStream(streamUrl, tabId, session);
  } catch (err) {
    _failInteractivePtyTab(tabId, `[server error] ${err.message || "Interactive PTY failed"}`, session);
  }
}
_scheduleInteractivePtyAssetPreload();
if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
  document.addEventListener("app:theme-changed", () => {
    _ptyApplyLiveTheme();
  });
  document.addEventListener("app:tab-activated", () => {
    window.requestAnimationFrame(_ptyFitVisibleSessions);
  });
}
if (typeof window !== "undefined") {
  Object.assign(window, {
    attachInteractivePtyCommand,
    detachInteractivePtyForTab,
    focusActiveInteractivePty,
    isInteractivePtyCommand,
    preloadInteractivePtyAssets,
    startInteractivePtyCommand
  });
}
export {
  _createPtyTerminalSession,
  _ensureXtermAssets,
  _failInteractivePtyTab,
  _interactivePtyEnabled,
  _interactivePtyMobileUnsupported,
  _loadPtyScriptOnce,
  _ptyApplyLiveTheme,
  _ptyCloseModal,
  _ptyDisplaceSession,
  _ptyFinalize,
  _ptyHandleStreamEndedWithoutExit,
  _ptyInputPayload,
  _ptyInstallKeyboardHandlers,
  _ptyOpenModal,
  _ptyPostResize,
  _ptyScopeModalToTab,
  _ptySendInput,
  _scheduleInteractivePtyAssetPreload,
  _xtermGlobalsAvailable,
  attachInteractivePtyCommand,
  detachInteractivePtyForTab,
  focusActiveInteractivePty,
  isInteractivePtyCommand,
  preloadInteractivePtyAssets,
  startInteractivePtyCommand
};
