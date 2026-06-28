// ── Desktop UI module ──
// Fetches welcome content from /welcome, /welcome/ascii, and /welcome/hints
// for desktop, and from /welcome/ascii-mobile plus /welcome/hints-mobile for
// the mobile variant. Renders the intro into the initial tab with status
// lines, typed commands, inline comment hints, and a closing hint row.
// Calling cancelWelcome() (e.g. when the user runs a command) stops the
// animation immediately; runner.js also calls clearTab to wipe partial output.
import { getActiveTabId as importedGetActiveTabId, getWelcomeState as importedGetWelcomeState, setWelcomeState as importedSetWelcomeState } from './core/state.js';
import { getWelcomeIntroPreference as importedGetWelcomeIntroPreference, getTourSeenVersionPreference as importedGetTourSeenVersionPreference } from './features/preferences/preferences.js';
import { getAppConfig as importedGetAppConfig } from './core/config.js';
import {
  apiFetch as importedRuntimeApiFetch,
  hasRuntimeHandler as importedHasRuntimeHandler,
  logClientError as importedRuntimeLogClientError,
} from './runtime_bridge.js';
import { cmdInput as importedCmdInput, shellPromptWrap as importedShellPromptWrap } from './core/dom.js';
import { renderMotd as importedRenderMotd } from './core/utils.js';
import { appendPromptNewline as importedAppendPromptNewline } from './runner.js';
import { getOutput as importedGetOutput, mountShellPrompt as importedMountShellPrompt, unmountShellPrompt as importedUnmountShellPrompt } from './tabs.js';
import { buildPromptLabel as importedBuildPromptLabel } from './output.js';
import { useMobileTerminalViewportMode as importedUseMobileTerminalViewportMode } from './features/mobile/mobile_shell_layout.js';
import {
  refocusComposerAfterAction as importedRefocusComposerAfterAction,
  setComposerValue as importedSetComposerValue,
} from './ui/ui_helpers.js';
import { bindPressable as importedBindPressable } from './ui/ui_pressable.js';
import { setWelcomeHandlers as importedSetWelcomeHandlers } from './welcome_bridge.js';

const WELCOME_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

function _welcomeGlobalFunction(name) {
  const fn = WELCOME_GLOBAL && WELCOME_GLOBAL[name];
  return typeof fn === 'function' ? fn : null;
}

function _welcomeGlobalValue(name) {
  return WELCOME_GLOBAL ? WELCOME_GLOBAL[name] : undefined;
}

function _welcomeAppConfig() {
  if (typeof importedGetAppConfig === 'function') return importedGetAppConfig();
  return _welcomeGlobalValue('APP_CONFIG') || {};
}

function _welcomeActiveTabId() {
  if (typeof importedGetActiveTabId === 'function') return importedGetActiveTabId();
  const readActiveTabId = _welcomeGlobalFunction('getActiveTabId');
  return readActiveTabId ? readActiveTabId() : (_welcomeGlobalValue('APP_STATE')?.activeTabId || null);
}

function _welcomeGetOutput(tabId) {
  if (typeof importedGetOutput === 'function') return importedGetOutput(tabId);
  const getOutput = _welcomeGlobalFunction('getOutput');
  return getOutput ? getOutput(tabId) : null;
}

function _welcomeMountShellPrompt(tabId, force = false) {
  const mountShellPrompt = (typeof importedMountShellPrompt === 'function' && importedMountShellPrompt)
    || _welcomeGlobalFunction('mountShellPrompt');
  if (!mountShellPrompt) return;
  if (force) {
    mountShellPrompt(tabId, true);
    return;
  }
  mountShellPrompt(tabId);
}

function _welcomeUnmountShellPrompt(tabId) {
  const unmountShellPrompt = (typeof importedUnmountShellPrompt === 'function' && importedUnmountShellPrompt)
    || _welcomeGlobalFunction('unmountShellPrompt');
  if (unmountShellPrompt) unmountShellPrompt(tabId);
}

function _welcomeRefocusComposer(...args) {
  const refocus = (typeof importedRefocusComposerAfterAction === 'function' && importedRefocusComposerAfterAction)
    || _welcomeGlobalFunction('refocusComposerAfterAction');
  if (refocus) refocus(...args);
}

function _welcomeAppendPromptNewline(tabId) {
  const append = (typeof importedAppendPromptNewline === 'function' && importedAppendPromptNewline)
    || _welcomeGlobalFunction('appendPromptNewline');
  if (append) append(tabId);
}

function _welcomeSetComposerValue(value) {
  const setComposerValue = (typeof importedSetComposerValue === 'function' && importedSetComposerValue)
    || _welcomeGlobalFunction('setComposerValue');
  if (setComposerValue) setComposerValue(value);
}

function _welcomeBindPressable(el, opts) {
  const bind = (typeof importedBindPressable === 'function' && importedBindPressable)
    || _welcomeGlobalFunction('bindPressable');
  return bind ? bind(el, opts) : null;
}

function _welcomeApiFetch(...args) {
  const apiFetch = (
    typeof importedHasRuntimeHandler === 'function'
    && importedHasRuntimeHandler('apiFetch')
    && typeof importedRuntimeApiFetch === 'function'
      ? importedRuntimeApiFetch
      : null
  ) || _welcomeGlobalFunction('apiFetch');
  if (!apiFetch) throw new Error('apiFetch is unavailable');
  return apiFetch(...args);
}

function _welcomeLogClientError(context, err, details = null) {
  const logClientError = (
    typeof importedHasRuntimeHandler === 'function'
    && importedHasRuntimeHandler('logClientError')
    && typeof importedRuntimeLogClientError === 'function'
      ? importedRuntimeLogClientError
      : null
  ) || _welcomeGlobalFunction('logClientError');
  if (logClientError) logClientError(context, err, details);
}

function _welcomeCmdInput() {
  return (typeof importedCmdInput !== 'undefined' && importedCmdInput) || _welcomeGlobalValue('cmdInput') || null;
}

function _welcomeShellPromptWrap() {
  return (typeof importedShellPromptWrap !== 'undefined' && importedShellPromptWrap) || _welcomeGlobalValue('shellPromptWrap') || null;
}

let _welcomeActive = false;
let _welcomeDone = false;
let _welcomeTabId = null;
let _welcomeBanner = null;
let _welcomeLiveLine = null;
let _welcomeHintNode = null;
let _welcomeStatusNodes = [];
let _welcomePlan = null;
let _welcomeNextBlockIndex = 0;
let _welcomeSettleRequested = false;
let _welcomePromptAfterSettle = false;
let _welcomeBootPending = true;

const _welcomeWaiters = new Set();
const _welcomePrompt = typeof importedBuildPromptLabel === 'function'
  ? importedBuildPromptLabel()
  : 'anon@darklab.sh:~ $';
const _welcomeGroupOrder = ['basics', 'dns', 'web', 'recon', 'advanced'];
const _welcomeStatusFrames = ['initializing /', 'initializing -', 'initializing \\', 'initializing |'];
const _welcomeStatusPendingText = 'initializing...';
const _welcomeStatusReadyText = 'initialized';

function _getWelcomeIntroMode() {
  const readPreference = (typeof importedGetWelcomeIntroPreference === 'function' && importedGetWelcomeIntroPreference)
    || _welcomeGlobalFunction('getWelcomeIntroPreference');
  if (readPreference) return readPreference();
  return 'animated';
}

function _getEffectiveWelcomeStatusLabels() {
  const config = _welcomeAppConfig();
  const statusLabels = Array.isArray(config.welcome_status_labels)
    ? config.welcome_status_labels
        .map(label => String(label || '').trim().toUpperCase())
        .filter(Boolean)
        .slice(0, 6)
    : [];
  return statusLabels.length
    ? statusLabels
    : ['CONFIG', 'RUNNER', 'HISTORY', 'LIMITS', 'AUTOCOMPLETE'];
}

function _shouldUseMobileWelcomeSequence() {
  const useMobile = (typeof importedUseMobileTerminalViewportMode === 'function' && importedUseMobileTerminalViewportMode)
    || _welcomeGlobalFunction('useMobileTerminalViewportMode');
  if (useMobile) return useMobile();
  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
    return window.matchMedia('(max-width: 600px)').matches;
  }
  return false;
}

function _visibleWelcomeTourChapters() {
  const config = _welcomeAppConfig();
  return Array.isArray(config?.tour_chapters) ? config.tour_chapters : [];
}

function _welcomeTourSeenVersion() {
  const readPreference = (typeof importedGetTourSeenVersionPreference === 'function' && importedGetTourSeenVersionPreference)
    || _welcomeGlobalFunction('getTourSeenVersionPreference');
  if (readPreference) return Number(readPreference() || 0) || 0;
  return 0;
}

function _welcomeTourVersion() {
  return Number(_welcomeAppConfig()?.tour_version || 0) || 0;
}

function _welcomeTourCtaState() {
  const config = _welcomeAppConfig();
  if (!(config && config.tour_enabled === true)) return null;
  if (!_visibleWelcomeTourChapters().length) return null;
  const version = _welcomeTourVersion();
  const seenVersion = _welcomeTourSeenVersion();
  return {
    demoted: version > 0 && seenVersion === version,
  };
}

function _writeWelcomeState(next = {}) {
  const setWelcomeState = (typeof importedSetWelcomeState === 'function' && importedSetWelcomeState)
    || _welcomeGlobalFunction('setWelcomeState');
  if (setWelcomeState) setWelcomeState(next);
  if (Object.prototype.hasOwnProperty.call(next, 'active')) _welcomeActive = !!next.active;
  if (Object.prototype.hasOwnProperty.call(next, 'done')) _welcomeDone = !!next.done;
  if (Object.prototype.hasOwnProperty.call(next, 'tabId')) _welcomeTabId = next.tabId == null ? null : String(next.tabId);
  if (Object.prototype.hasOwnProperty.call(next, 'settleRequested')) _welcomeSettleRequested = !!next.settleRequested;
  if (Object.prototype.hasOwnProperty.call(next, 'promptAfterSettle')) _welcomePromptAfterSettle = !!next.promptAfterSettle;
  if (Object.prototype.hasOwnProperty.call(next, 'bootPending')) _welcomeBootPending = !!next.bootPending;
  const getWelcomeState = (typeof importedGetWelcomeState === 'function' && importedGetWelcomeState)
    || _welcomeGlobalFunction('getWelcomeState');
  return getWelcomeState ? getWelcomeState() : {
    active: _welcomeActive,
    done: _welcomeDone,
    tabId: _welcomeTabId,
    settleRequested: _welcomeSettleRequested,
    promptAfterSettle: _welcomePromptAfterSettle,
    bootPending: _welcomeBootPending,
  };
}

function _readWelcomeState() {
  const getWelcomeState = (typeof importedGetWelcomeState === 'function' && importedGetWelcomeState)
    || _welcomeGlobalFunction('getWelcomeState');
  const apiState = getWelcomeState ? getWelcomeState() : null;
  return {
    active: _welcomeActive || !!(apiState && apiState.active),
    done: _welcomeDone || !!(apiState && apiState.done),
    tabId: _welcomeTabId || (apiState && apiState.tabId) || null,
    settleRequested: _welcomeSettleRequested || !!(apiState && apiState.settleRequested),
    promptAfterSettle: _welcomePromptAfterSettle || !!(apiState && apiState.promptAfterSettle),
    bootPending: _welcomeBootPending || !!(apiState && apiState.bootPending),
  };
}

function _welcomeIsActive() {
  return !!_readWelcomeState().active;
}

function _welcomeIsSettling() {
  return !!_readWelcomeState().settleRequested;
}

function welcomeOwnsTab(tabId) {
  const state = _readWelcomeState();
  return !!tabId && state.tabId === tabId && (state.active || state.done);
}

function _sleep(ms) {
  return new Promise(resolve => {
    const waiter = {
      done: false,
      timer: null,
      resolve() {
        if (waiter.done) return;
        waiter.done = true;
        clearTimeout(waiter.timer);
        _welcomeWaiters.delete(waiter);
        resolve();
      }
    };
    waiter.timer = setTimeout(() => waiter.resolve(), ms);
    _welcomeWaiters.add(waiter);
  });
}

function _flushWelcomeWaiters() {
  [..._welcomeWaiters].forEach(waiter => waiter.resolve());
}

function _clearWelcomeLiveLine() {
  if (_welcomeLiveLine) _welcomeLiveLine.remove();
  _welcomeLiveLine = null;
}

function _clearWelcomeBanner() {
  if (_welcomeBanner) _welcomeBanner.remove();
  _welcomeBanner = null;
  _welcomeHintNode = null;
  _welcomeStatusNodes = [];
}

function _resetWelcomePlan() {
  _welcomePlan = null;
  _welcomeNextBlockIndex = 0;
  _writeWelcomeState({ settleRequested: false, promptAfterSettle: false });
}

function _setWelcomeBannerSettled(settled) {
  if (!_welcomeBanner) return;
  _welcomeBanner.classList.toggle('welcome-banner-settled', !!settled);
}

function _setWelcomeStatus(index, value) {
  const node = _welcomeStatusNodes[index];
  if (!node) return;
  node.dataset.state = value;
  node.textContent = value === 'loaded' ? _welcomeStatusReadyText : value;
  node.classList.remove('welcome-status-loading', 'welcome-status-loaded');
  node.classList.add(value === 'loaded' ? 'welcome-status-loaded' : 'welcome-status-loading');
}

async function _spinWelcomeStatus(node, stepMs = 140) {
  if (!node) return;
  let frame = 0;
  node.dataset.state = 'loading';
  while (_welcomeIsActive() && node.isConnected && node.dataset.state === 'loading') {
    node.textContent = _welcomeStatusFrames[frame % _welcomeStatusFrames.length];
    frame++;
    await _sleep(stepMs);
  }
}

function _appendWelcomeStatusRow(label, value = _welcomeStatusPendingText) {
  const statusStack = _welcomeBanner.querySelector('.welcome-status-stack');
  if (!statusStack) return null;

  const statusLine = document.createElement('div');
  statusLine.className = 'line welcome-status-line welcome-status-line-enter';

  const labelSpan = document.createElement('span');
  labelSpan.className = 'welcome-status-label';
  labelSpan.textContent = `${label}:`;

  const valueSpan = document.createElement('span');
  const isReady = value === 'loaded' || value === _welcomeStatusReadyText;
  valueSpan.className = isReady
    ? 'welcome-status-loaded'
    : 'welcome-status-loading';
  valueSpan.textContent = value;
  valueSpan.dataset.state = isReady ? 'loaded' : 'loading';

  statusLine.append(labelSpan, valueSpan);
  statusStack.appendChild(statusLine);
  _welcomeStatusNodes.push(valueSpan);
  if (!isReady) void _spinWelcomeStatus(valueSpan);

  requestAnimationFrame(() => {
    statusLine.classList.add('welcome-status-line-visible');
  });

  return valueSpan;
}

async function _runWelcomeStatusSequence(labels, intervalMs, staggerMs = null) {
  if (!_welcomeIsActive() || !_welcomeBanner || !labels.length) return;
  const settlePromises = [];
  const STAGGER_MS = staggerMs == null
    ? Math.max(140, Math.floor(intervalMs * 0.32))
    : staggerMs;

  for (let i = 0; i < labels.length; i++) {
    if (!_welcomeIsActive()) return;
    _appendWelcomeStatusRow(labels[i], _welcomeStatusPendingText);
    settlePromises.push((async (index) => {
      await _sleep(intervalMs);
      if (_welcomeIsActive()) _setWelcomeStatus(index, 'loaded');
    })(i));
    if (i + 1 < labels.length) {
      await _sleep(STAGGER_MS);
    }
  }

  await Promise.all(settlePromises);
}

async function _runWelcomeAnimation(tabId, {
  asciiArt = '',
  blocks = [],
  hints = [],
  includeBlocks = true,
} = {}) {
  const out = _welcomeGetOutput(tabId);
  if (!out) return false;

  _renderWelcomeAsciiStream(tabId, asciiArt);
  if (!_welcomeIsActive()) return false;

  const effectiveStatusLabels = _getEffectiveWelcomeStatusLabels();
  const introBlocks = includeBlocks ? blocks : [];
  _welcomePlan = {
    asciiArt,
    statusLabels: effectiveStatusLabels,
    blocks: introBlocks,
    hints,
  };
  if (_welcomeIsSettling()) {
    settleWelcome(tabId);
    return true;
  }

  const INTER_BLOCK_MS = _welcomeAppConfig().welcome_inter_block_ms ?? 1500;
  const POST_STATUS_PAUSE_MS = Math.max(0, Number(_welcomeAppConfig().welcome_post_status_pause_ms ?? 220) || 0);
  const STATUS_MS = Math.max(820, Math.floor(INTER_BLOCK_MS * 0.78));
  const STATUS_STAGGER_MS = Math.max(140, Math.floor(INTER_BLOCK_MS * 0.28));
  const CHAR_MS = _welcomeAppConfig().welcome_char_ms ?? 10;
  const JITTER = _welcomeAppConfig().welcome_jitter_ms ?? 10;
  const POST_CMD_MS = _welcomeAppConfig().welcome_post_cmd_ms ?? 700;
  const FIRST_PROMPT_IDLE_MS = Math.max(0, Number(_welcomeAppConfig().welcome_first_prompt_idle_ms ?? 2100) || 0);
  const HINT_INTERVAL_MS = Math.max(0, Number(_welcomeAppConfig().welcome_hint_interval_ms ?? 4200) || 0);

  await _runWelcomeStatusSequence(effectiveStatusLabels, STATUS_MS, STATUS_STAGGER_MS);
  if (!_welcomeIsActive()) return false;
  if (_welcomeIsSettling()) {
    settleWelcome(tabId);
    return true;
  }
  _setWelcomeBannerSettled(true);
  await _sleep(Math.max(POST_STATUS_PAUSE_MS, Math.floor(INTER_BLOCK_MS * 0.24)));
  if (!_welcomeIsActive()) return false;
  if (_welcomeIsSettling()) {
    settleWelcome(tabId);
    return true;
  }

  if (introBlocks.length) {
    _appendWelcomeSectionHeader(tabId, 'Recommended commands', 'recommended-commands');
  }
  for (const [blockIndex, block] of introBlocks.entries()) {
    if (!_welcomeIsActive()) break;
    if (_welcomeIsSettling()) {
      settleWelcome(tabId);
      return true;
    }

    const currentOut = _welcomeGetOutput(tabId);
    if (!currentOut) break;
    _welcomeNextBlockIndex = blockIndex;

    if (!await _typeWelcomeCommand(tabId, block.cmd, {
      charMs: CHAR_MS,
      jitterMs: JITTER,
      postMs: POST_CMD_MS,
      startDelayMs: blockIndex === 0 ? Math.max(FIRST_PROMPT_IDLE_MS, Math.floor(INTER_BLOCK_MS * 0.72)) : INTER_BLOCK_MS,
      commentText: block.out || null,
    })) return false;
    _welcomeNextBlockIndex = blockIndex + 1;

    if (blockIndex === 0) {
      const commands = _welcomeGetOutput(tabId)?.querySelectorAll('.welcome-command');
      const featuredLine = commands && commands[commands.length - 1];
      if (featuredLine) {
        _ensureFeaturedWelcomeBadge(featuredLine, block.cmd);
      }
    }
  }

  if (_welcomeIsActive()) {
    _appendWelcomeTourCta(tabId);
    _writeWelcomeState({ done: true });
    if (hints.length) {
      _appendWelcomeSectionHeader(tabId, 'Helpful hints', 'helpful-hints');
      void _runWelcomeHintFeed(tabId, hints, HINT_INTERVAL_MS);
    } else {
      _appendWelcomeOutput(tabId, 'Enter runs the command · Up/Down navigates autocomplete · History keeps previous runs', 'welcome-hint');
      _writeWelcomeState({ active: false, bootPending: false });
      if (tabId === _welcomeActiveTabId()) _welcomeMountShellPrompt(tabId);
    }
  }

  return true;
}

function cancelWelcome(tabId = null) {
  if (tabId && _welcomeTabId && _welcomeTabId !== tabId) return false;
  _writeWelcomeState({
    active: false,
    done: false,
    tabId: null,
    bootPending: false,
  });
  _flushWelcomeWaiters();
  _clearWelcomeLiveLine();
  _clearWelcomeBanner();
  _resetWelcomePlan();
  if (tabId === _welcomeActiveTabId()) {
    _welcomeMountShellPrompt(tabId, true);
    _welcomeRefocusComposer({ defer: true });
    setTimeout(() => {
      const shellPromptWrap = _welcomeShellPromptWrap();
      if (shellPromptWrap) shellPromptWrap.classList.add('shell-prompt-focused');
    }, 0);
  }
  _welcomeRefocusComposer();
  {
    const shellPromptWrap = _welcomeShellPromptWrap();
    if (shellPromptWrap) shellPromptWrap.classList.add('shell-prompt-focused');
  }
  return true;
}

function requestWelcomeSettle(tabId = _welcomeActiveTabId()) {
  const state = _readWelcomeState();
  if (!tabId || !state.active || state.tabId !== tabId) return false;
  _writeWelcomeState({ settleRequested: true });
  _flushWelcomeWaiters();
  if (_welcomePlan) {
    return settleWelcome(tabId);
  }
  return true;
}

async function _typeWelcomeCommand(tabId, cmd, { charMs, jitterMs, postMs, startDelayMs = 0, commentText = null, interactive = true } = {}) {
  const out = _welcomeGetOutput(tabId);
  if (!out) return false;

  const CHAR_MS = charMs ?? (_welcomeAppConfig().welcome_char_ms ?? 10);
  const JITTER = jitterMs ?? (_welcomeAppConfig().welcome_jitter_ms ?? 10);
  const POST_CMD_MS = postMs ?? (_welcomeAppConfig().welcome_post_cmd_ms ?? 700);

  const typingSpan = document.createElement('span');
  typingSpan.className = 'line wlc-live welcome-command';
  typingSpan.innerHTML =
    `<span class="wlc-prompt">${_welcomePrompt}</span>` +
    '<span class="wlc-command-text welcome-command-text"></span>' +
    '<span class="wlc-cursor"></span>';
  out.appendChild(typingSpan);
  _welcomeLiveLine = typingSpan;
  out.scrollTop = out.scrollHeight;

  const wlcText = typingSpan.querySelector('.wlc-command-text');

  // Let the prompt appear first, then begin typing the command text.
  if (startDelayMs > 0) {
    await _sleep(startDelayMs);
  } else {
    await _sleep(Math.min(80, CHAR_MS * 2));
  }
  if (!_welcomeIsActive()) { typingSpan.remove(); _welcomeLiveLine = null; return false; }

  for (let i = 0; i < cmd.length; i++) {
    if (!_welcomeIsActive()) { typingSpan.remove(); _welcomeLiveLine = null; return false; }
    wlcText.textContent = cmd.slice(0, i + 1);
    out.scrollTop = out.scrollHeight;
    await _sleep(CHAR_MS + Math.random() * JITTER);
  }

  await _sleep(POST_CMD_MS);
  if (!_welcomeIsActive()) { typingSpan.remove(); _welcomeLiveLine = null; return false; }
  _finalizeWelcomeCommandLine(tabId, typingSpan, cmd, commentText, { interactive });
  return true;
}

function _renderWelcomeAsciiStream(tabId, asciiArt) {
  // The banner animates as streamed output so it feels like terminal output
  // rather than a separately mounted hero component.
  const out = _welcomeGetOutput(tabId);
  if (!out) return;

  const artLines = (asciiArt || (_welcomeAppConfig().app_name || 'darklab_shell'))
    .split('\n')
    .map(line => line.replace(/\s+$/g, ''))
    .filter(line => line.length > 0);

  const banner = document.createElement('div');
  banner.className = 'welcome-banner';

  const artBlock = document.createElement('pre');
  artBlock.className = 'line welcome-ascii-art';
  artBlock.setAttribute('aria-label', 'ASCII art banner');
  artBlock.textContent = artLines.join('\n');

  const motdText = String(_welcomeAppConfig()?.motd || '').trim();
  let operatorNotice = null;
  if (motdText) {
    operatorNotice = document.createElement('div');
    operatorNotice.className = 'welcome-operator-notice';
    operatorNotice.setAttribute('aria-label', 'Operator message');

    const operatorLabel = document.createElement('div');
    operatorLabel.className = 'welcome-operator-label';
    operatorLabel.textContent = 'Message From The Operator';

    const operatorBody = document.createElement('div');
    operatorBody.className = 'welcome-operator-body';
    const renderMotd = (typeof importedRenderMotd === 'function' && importedRenderMotd)
      || _welcomeGlobalFunction('renderMotd');
    if (renderMotd) {
      operatorBody.innerHTML = renderMotd(motdText);
    } else {
      operatorBody.textContent = motdText;
    }

    operatorNotice.append(operatorLabel, operatorBody);
  }

  const statusStack = document.createElement('div');
  statusStack.className = 'welcome-status-stack';
  statusStack.setAttribute('aria-label', 'System status');
  _welcomeStatusNodes = [];

  if (operatorNotice) banner.appendChild(operatorNotice);
  banner.append(artBlock, statusStack);
  out.appendChild(banner);
  _welcomeBanner = banner;
  requestAnimationFrame(() => {
    banner.classList.add('welcome-banner-visible');
  });
  out.scrollTop = out.scrollHeight;
}

function _appendWelcomeCommand(tabId, cmd, commentText = null, { interactive = true } = {}) {
  const out = _welcomeGetOutput(tabId);
  if (!out) return;
  const line = document.createElement('span');
  line.className = 'line welcome-command' + (interactive ? '' : ' welcome-command-static');
  line.innerHTML =
    `<span class="wlc-prompt">${_welcomePrompt}</span>` +
    `<span class="wlc-command-text welcome-command-text"></span>`;
  const cmdText = line.querySelector('.wlc-command-text');
  cmdText.textContent = cmd;
  if (interactive) {
    cmdText.classList.add('welcome-command-loadable');
    cmdText.tabIndex = 0;
    cmdText.setAttribute('role', 'button');
    cmdText.title = 'Click to load into prompt';
    cmdText.setAttribute('aria-label', `Load command: ${cmd}`);
  }
  if (commentText) {
    const comment = document.createElement('span');
    comment.className = 'welcome-command-comment';
    comment.textContent = `  # ${String(commentText).trimStart()}`;
    line.appendChild(comment);
  }
  function loadCommand() {
    if (!interactive) return;
    if (_welcomeIsActive() && welcomeOwnsTab(tabId)) settleWelcome(tabId);
    _welcomeRefocusComposer();
    _welcomeSetComposerValue(cmd, cmd.length, cmd.length, { dispatch: false });
    // Defer so the document click handler has already run before autocomplete updates.
    setTimeout(() => {
      const cmdInput = _welcomeCmdInput();
      if (cmdInput && typeof cmdInput.dispatchEvent === 'function') cmdInput.dispatchEvent(new Event('input'));
    }, 0);
  }
  if (interactive) {
    // loadCommand already drives its own focus dance (refocus first, then set
    // composer value). bindPressable gives us click + keyboard activation
    // with press-highlight cleanup for role="button" spans without
    // double-refocusing the composer.
    _welcomeBindPressable(cmdText, {
      refocusComposer: false,
      clearPressStyle: true,
      onActivate: loadCommand,
    });
  }
  out.appendChild(line);
  out.scrollTop = out.scrollHeight;
  return line;
}

function _loadWelcomeTourCommand(tabId) {
  if (_welcomeIsActive() && welcomeOwnsTab(tabId)) settleWelcome(tabId);
  _welcomeRefocusComposer();
  _welcomeSetComposerValue('tour', 4, 4, { dispatch: false });
  setTimeout(() => {
    const cmdInput = _welcomeCmdInput();
    if (cmdInput && typeof cmdInput.dispatchEvent === 'function') cmdInput.dispatchEvent(new Event('input'));
  }, 0);
}

function _openWelcomeVisualTour(tabId) {
  const openTourModal = _welcomeGlobalFunction('openTourModal');
  if (!openTourModal) return false;
  if (_welcomeIsActive() && welcomeOwnsTab(tabId)) settleWelcome(tabId);
  return openTourModal({ source: 'welcome' });
}

function _appendWelcomeTourCta(tabId) {
  const state = _welcomeTourCtaState();
  const out = _welcomeGetOutput(tabId);
  if (!state || !out) return null;
  const existing = out.querySelector('[data-welcome-section="tour-cta"]');
  if (existing) return existing;

  const line = document.createElement('span');
  line.className = 'line welcome-tour-cta';
  line.classList.toggle('welcome-tour-cta-demoted', state.demoted);
  line.classList.toggle('welcome-tour-cta-emphasis', !state.demoted);
  line.dataset.welcomeSection = 'tour-cta';

  const label = document.createElement('span');
  label.className = 'welcome-tour-cta-label';
  label.textContent = 'Tour the app - type ';

  const chip = document.createElement('span');
  chip.className = 'welcome-tour-cta-command welcome-command-loadable';
  chip.textContent = 'tour';
  chip.tabIndex = 0;
  chip.setAttribute('role', 'button');
  chip.title = 'Click to load into prompt';
  chip.setAttribute('aria-label', 'Load command: tour');
  _welcomeBindPressable(chip, {
    refocusComposer: false,
    clearPressStyle: true,
    onActivate: () => _loadWelcomeTourCommand(tabId),
  });

  line.append(label, chip);
  const openTourModal = _welcomeGlobalFunction('openTourModal');
  const useMobile = (typeof importedUseMobileTerminalViewportMode === 'function' && importedUseMobileTerminalViewportMode)
    || _welcomeGlobalFunction('useMobileTerminalViewportMode');
  if (
    !(useMobile && useMobile())
    && openTourModal
  ) {
    const joiner = document.createElement('span');
    joiner.className = 'welcome-tour-cta-label';
    joiner.textContent = ' or ';
    const visual = document.createElement('span');
    visual.className = 'welcome-tour-cta-visual welcome-command-loadable';
    visual.textContent = 'open the visual tour';
    visual.tabIndex = 0;
    visual.setAttribute('role', 'button');
    visual.setAttribute('aria-label', 'Open the visual tour');
    _welcomeBindPressable(visual, {
      refocusComposer: false,
      clearPressStyle: true,
      onActivate: () => _openWelcomeVisualTour(tabId),
    });
    line.append(joiner, visual);
  }
  out.appendChild(line);
  out.scrollTop = out.scrollHeight;
  return line;
}

function _finalizeWelcomeCommandLine(tabId, line, cmd, commentText = null, { interactive = true } = {}) {
  const out = _welcomeGetOutput(tabId);
  if (!out || !line || !line.isConnected) return null;

  line.classList.remove('wlc-live', 'wlc-settling');
  line.classList.toggle('welcome-command-static', !interactive);

  const cursor = line.querySelector('.wlc-cursor');
  if (cursor) cursor.remove();

  const cmdText = line.querySelector('.wlc-command-text, .welcome-command-text');
  if (!cmdText) return line;
  cmdText.classList.add('welcome-command-text');
  cmdText.classList.remove('wlc-command-text');
  cmdText.textContent = cmd;

  if (interactive) {
    cmdText.classList.add('welcome-command-loadable');
    cmdText.tabIndex = 0;
    cmdText.setAttribute('role', 'button');
    cmdText.title = 'Click to load into prompt';
    cmdText.setAttribute('aria-label', `Load command: ${cmd}`);
    cmdText.replaceWith(cmdText.cloneNode(true));
    const boundCmdText = line.querySelector('.welcome-command-text');
    function loadCommand() {
      if (_welcomeIsActive() && welcomeOwnsTab(tabId)) settleWelcome(tabId);
      _welcomeRefocusComposer();
      _welcomeSetComposerValue(cmd, cmd.length, cmd.length, { dispatch: false });
      setTimeout(() => {
        const cmdInput = _welcomeCmdInput();
        if (cmdInput && typeof cmdInput.dispatchEvent === 'function') cmdInput.dispatchEvent(new Event('input'));
      }, 0);
    }
    _welcomeBindPressable(boundCmdText, {
      refocusComposer: false,
      clearPressStyle: true,
      onActivate: loadCommand,
    });
  } else {
    cmdText.classList.remove('welcome-command-loadable');
    cmdText.removeAttribute('tabindex');
    cmdText.removeAttribute('role');
    cmdText.removeAttribute('title');
    cmdText.removeAttribute('aria-label');
  }

  const existingComment = line.querySelector('.welcome-command-comment');
  if (existingComment) existingComment.remove();
  if (commentText) {
    const comment = document.createElement('span');
    comment.className = 'welcome-command-comment';
    comment.textContent = `  # ${String(commentText).trimStart()}`;
    line.appendChild(comment);
  }

  _welcomeLiveLine = null;
  out.scrollTop = out.scrollHeight;
  return line;
}

function _appendWelcomeOutput(tabId, text, cls = 'welcome-output') {
  const out = _welcomeGetOutput(tabId);
  if (!out) return;
  const line = document.createElement('span');
  line.className = `line ${cls}`;
  if (cls === 'welcome-output') {
    line.classList.add('welcome-comment');
    line.textContent = `# ${String(text).trimStart()}`;
  } else {
    line.textContent = text;
  }
  out.appendChild(line);
  out.scrollTop = out.scrollHeight;
}

function _appendWelcomeSectionHeader(tabId, text, sectionId = '', cls = 'welcome-section-header') {
  const out = _welcomeGetOutput(tabId);
  if (!out) return null;
  if (sectionId) {
    const existing = out.querySelector(`[data-welcome-section="${sectionId}"]`);
    if (existing) return existing;
  }
  const line = document.createElement('span');
  line.className = `line ${cls}`;
  if (sectionId) line.dataset.welcomeSection = sectionId;
  line.textContent = `# ${String(text).trim()}`;
  out.appendChild(line);
  out.scrollTop = out.scrollHeight;
  return line;
}

function _pickRandomHint(hints, used) {
  if (!hints.length) return '';
  const pool = hints.filter(hint => !used.has(hint));
  if (pool.length === 0) {
    used.clear();
    pool.push(...hints);
  }
  return pool[Math.floor(Math.random() * pool.length)] || '';
}

function _coerceWelcomeHintRotationLimit(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 0;
  return Math.max(0, Math.floor(parsed));
}

function _welcomeHintRotationBudget(value) {
  const limit = _coerceWelcomeHintRotationLimit(value);
  if (limit === 0) return Infinity;
  if (limit === 1) return 0;
  return Math.max(0, limit - 1);
}

function _pickRandomEntry(items) {
  if (!items.length) return null;
  return items[Math.floor(Math.random() * items.length)] || null;
}

function _sampleWelcomeBlocks(blocks, count = 5) {
  if (!Array.isArray(blocks) || !blocks.length) return [];
  const picked = [];
  const seen = new Set();

  function takeOne(items) {
    const candidates = items.filter(item => item && !seen.has(item.cmd));
    const choice = _pickRandomEntry(candidates);
    if (!choice) return null;
    seen.add(choice.cmd);
    picked.push(choice);
    return choice;
  }

  const grouped = new Map();
  blocks.forEach(block => {
    const key = block.group || 'misc';
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(block);
  });

  takeOne(blocks.filter(block => block.featured && (block.group || '') === 'basics'));

  for (const group of _welcomeGroupOrder) {
    if (picked.length >= count) break;
    takeOne(grouped.get(group) || []);
  }

  const featuredRemainder = blocks.filter(block => block.featured && !seen.has(block.cmd));
  while (picked.length < Math.min(count, blocks.length) && featuredRemainder.length) {
    const choice = takeOne(featuredRemainder);
    if (!choice) break;
  }

  const remainder = blocks.filter(block => !seen.has(block.cmd));
  while (picked.length < Math.min(count, blocks.length)) {
    const choice = takeOne(remainder);
    if (!choice) break;
  }

  return picked.slice(0, Math.min(count, blocks.length));
}

function _shouldRotateWelcomeHints(tabId) {
  const state = _readWelcomeState();
  return state.active
    && !state.settleRequested
    && welcomeOwnsTab(tabId)
    && _welcomeActiveTabId() === tabId
    && (!_welcomeCmdInput() || !_welcomeCmdInput().value.trim());
}

async function _showWelcomeHint(tabId, text, initial = false) {
  const out = _welcomeGetOutput(tabId);
  if (!out) return null;

  if (!_welcomeHintNode) {
    const line = document.createElement('span');
    line.className = 'line welcome-hint welcome-hint-feed';
    line.textContent = `# ${String(text).trim()}`;
    out.appendChild(line);
    _welcomeHintNode = line;
    requestAnimationFrame(() => line.classList.add('welcome-hint-visible'));
    out.scrollTop = out.scrollHeight;
    return line;
  }

  if (!initial) {
    _welcomeHintNode.classList.remove('welcome-hint-visible');
    await _sleep(220);
  }
  if (!_welcomeIsActive()) return null;

  _welcomeHintNode.textContent = `# ${String(text).trim()}`;
  requestAnimationFrame(() => {
    if (_welcomeHintNode) _welcomeHintNode.classList.add('welcome-hint-visible');
  });
  out.scrollTop = out.scrollHeight;
  return _welcomeHintNode;
}

async function _runWelcomeHintFeed(tabId, hints, intervalMs) {
  const state = _readWelcomeState();
  if (!state.active || !state.done || !Array.isArray(hints) || !hints.length) return;

  if (state.settleRequested) {
    settleWelcome(tabId);
    return;
  }

  const used = new Set();
  let current = _pickRandomHint(hints, used);
  if (!current) return;
  used.add(current);
  await _showWelcomeHint(tabId, current, true);
  if (tabId === _welcomeActiveTabId()) {
    _welcomeMountShellPrompt(tabId, true);
    _welcomeRefocusComposer();
    const shellPromptWrap = _welcomeShellPromptWrap();
    if (shellPromptWrap) shellPromptWrap.classList.add('shell-prompt-focused');
  }

  if (!(Number(intervalMs) > 0)) {
    _writeWelcomeState({ active: false });
    if (tabId === _welcomeActiveTabId()) _welcomeMountShellPrompt(tabId);
    return;
  }

  const rotationsRemainingStart = _welcomeHintRotationBudget(_welcomeAppConfig().welcome_hint_rotations);
  if (rotationsRemainingStart === 0) {
    _writeWelcomeState({ active: false });
    if (tabId === _welcomeActiveTabId()) _welcomeMountShellPrompt(tabId);
    return;
  }
  let rotationsRemaining = rotationsRemainingStart;

  while (_shouldRotateWelcomeHints(tabId)) {
    await _sleep(intervalMs);
    if (_welcomeIsSettling()) {
      settleWelcome(tabId);
      return;
    }
    if (!_shouldRotateWelcomeHints(tabId)) break;

    if (rotationsRemaining !== Infinity) {
      if (rotationsRemaining <= 0) break;
      rotationsRemaining--;
    }

    current = _pickRandomHint(hints, used);
    if (!current) return;
    used.add(current);
    await _showWelcomeHint(tabId, current, false);
  }

  _writeWelcomeState({ active: false });
  if (tabId === _welcomeActiveTabId()) _welcomeMountShellPrompt(tabId);
}

function _currentWelcomeHintText() {
  if (!_welcomeHintNode) return '';
  return String(_welcomeHintNode.textContent || '').replace(/^#\s*/, '').trim();
}

async function _resumeWelcomeHintFeed(tabId, hints, intervalMs) {
  const state = _readWelcomeState();
  if (!state.active || !state.done || !Array.isArray(hints) || !hints.length) return;
  if (!(Number(intervalMs) > 0)) {
    _writeWelcomeState({ active: false });
    return;
  }
  let rotationsRemaining = _welcomeHintRotationBudget(_welcomeAppConfig().welcome_hint_rotations);
  if (rotationsRemaining === 0) {
    _writeWelcomeState({ active: false });
    return;
  }

  const used = new Set();
  const current = _currentWelcomeHintText();
  if (current) used.add(current);

  while (_shouldRotateWelcomeHints(tabId)) {
    await _sleep(intervalMs);
    if (!_shouldRotateWelcomeHints(tabId)) break;

    if (rotationsRemaining !== Infinity) {
      if (rotationsRemaining <= 0) break;
      rotationsRemaining--;
    }

    const next = _pickRandomHint(hints, used);
    if (!next) break;
    used.add(next);
    await _showWelcomeHint(tabId, next, false);
  }

  _writeWelcomeState({ active: false });
  if (tabId === _welcomeActiveTabId()) _welcomeMountShellPrompt(tabId);
}

function _ensureFeaturedWelcomeBadge(line, cmd) {
  if (!line || line.querySelector('.welcome-command-badge')) return;
  const comment = line.querySelector('.welcome-command-comment');
  const badge = document.createElement('span');
  badge.className = 'welcome-command-badge welcome-command-loadable';
  badge.textContent = 'try this first';
  badge.tabIndex = 0;
  badge.setAttribute('role', 'button');
  badge.title = 'Click to load into prompt';
  badge.setAttribute('aria-label', `Load command: ${cmd}`);
  _welcomeBindPressable(badge, {
    refocusComposer: false,
    clearPressStyle: true,
    onActivate: () => {
      line.querySelector('.welcome-command-text')?.click();
    },
  });
  line.insertBefore(badge, comment || null);
}

function _ensureWelcomeFinalHint(tabId, hints) {
  // The final hint is anchored once at the end of the welcome flow so command
  // entry starts from a stable transcript instead of a still-rotating footer.
  if (_welcomeHintNode) return;
  if (Array.isArray(hints) && hints.length) {
    const finalHint = _pickRandomHint(hints, new Set()) || hints[0];
    const line = document.createElement('span');
    line.className = 'line welcome-hint welcome-hint-feed welcome-hint-visible';
    line.textContent = `# ${String(finalHint).trim()}`;
    _welcomeGetOutput(tabId)?.appendChild(line);
    _welcomeHintNode = line;
    if (tabId === _welcomeActiveTabId()) _welcomeMountShellPrompt(tabId, true);
    return;
  }
  _appendWelcomeOutput(tabId, 'Enter runs the command · Up/Down navigates autocomplete · History keeps previous runs', 'welcome-hint');
  if (tabId === _welcomeActiveTabId()) _welcomeMountShellPrompt(tabId, true);
}

function settleWelcome(tabId = _welcomeActiveTabId()) {
  // Settling collapses all pending typing/rotation work into the final state so
  // the user can start typing immediately without waiting for animation timers.
  if (!welcomeOwnsTab(tabId)) return false;
  const out = _welcomeGetOutput(tabId);
  if (!out) return false;

  _flushWelcomeWaiters();
  _clearWelcomeLiveLine();

  const asciiArt = _welcomePlan && typeof _welcomePlan.asciiArt === 'string'
    ? _welcomePlan.asciiArt
    : '';
  if (!_welcomeBanner) _renderWelcomeAsciiStream(tabId, asciiArt);

  const statusLabels = (_welcomePlan && Array.isArray(_welcomePlan.statusLabels) && _welcomePlan.statusLabels.length)
    ? _welcomePlan.statusLabels
    : ['CONFIG', 'RUNNER', 'HISTORY', 'LIMITS', 'AUTOCOMPLETE'];
  statusLabels.forEach((label, index) => {
    if (_welcomeStatusNodes[index]) _setWelcomeStatus(index, 'loaded');
    else _appendWelcomeStatusRow(label, _welcomeStatusReadyText);
  });
  _setWelcomeBannerSettled(true);

  const blocks = (_welcomePlan && Array.isArray(_welcomePlan.blocks)) ? _welcomePlan.blocks : [];
  if (blocks.length) {
    _appendWelcomeSectionHeader(tabId, 'Recommended commands', 'recommended-commands');
  }
  for (let i = _welcomeNextBlockIndex; i < blocks.length; i++) {
    const line = _appendWelcomeCommand(tabId, blocks[i].cmd, blocks[i].out || null);
    if (i === 0) {
      _ensureFeaturedWelcomeBadge(line, blocks[i].cmd);
    }
  }
  _welcomeNextBlockIndex = blocks.length;
  _appendWelcomeTourCta(tabId);

  _writeWelcomeState({ done: true });
  if (_welcomePlan && Array.isArray(_welcomePlan.hints) && _welcomePlan.hints.length) {
    _appendWelcomeSectionHeader(tabId, 'Helpful hints', 'helpful-hints');
  }
  _ensureWelcomeFinalHint(tabId, _welcomePlan && _welcomePlan.hints);
  _writeWelcomeState({ active: false, bootPending: false });
  if (tabId === _welcomeActiveTabId()) _welcomeMountShellPrompt(tabId);
  if (_readWelcomeState().promptAfterSettle) {
    _writeWelcomeState({ promptAfterSettle: false });
    _welcomeAppendPromptNewline(tabId);
  }
  out.scrollTop = out.scrollHeight;
  return true;
}

function _renderSettledWelcome(tabId, {
  asciiArt = '',
  blocks = [],
  hints = [],
  includeBlocks = true,
  rotateHints = false,
} = {}) {
  const out = _welcomeGetOutput(tabId);
  if (!out || !_welcomeIsActive()) return false;
  const introBlocks = includeBlocks ? blocks : [];
  _welcomePlan = {
    asciiArt,
    statusLabels: _getEffectiveWelcomeStatusLabels(),
    blocks: introBlocks,
    hints,
  };
  const settled = settleWelcome(tabId);
  if (settled && rotateHints && Array.isArray(hints) && hints.length) {
    _writeWelcomeState({ active: true, bootPending: false });
    const intervalMs = Math.max(0, Number(_welcomeAppConfig().welcome_hint_interval_ms ?? 4200) || 0);
    void _resumeWelcomeHintFeed(tabId, hints, intervalMs);
  }
  return settled;
}

async function runWelcome() {
  const tabId = _welcomeActiveTabId();
  const introMode = _getWelcomeIntroMode();
  if (introMode === 'remove') {
    _writeWelcomeState({
      bootPending: false,
      active: false,
      done: false,
      tabId: null,
    });
    if (tabId === _welcomeActiveTabId()) _welcomeMountShellPrompt(tabId);
    return;
  }
  _writeWelcomeState({
    bootPending: true,
    active: true,
    done: false,
    tabId: _welcomeActiveTabId(),
    settleRequested: false,
  });
  _welcomeUnmountShellPrompt();

  if (_shouldUseMobileWelcomeSequence()) {
    const [asciiArt, hintData] = await Promise.all([
      _welcomeApiFetch('/welcome/ascii-mobile').then(r => r.text()).catch(err => {
        _welcomeLogClientError('failed to load /welcome/ascii-mobile', err);
        return '';
      }),
      _welcomeApiFetch('/welcome/hints-mobile').then(r => r.json()).catch(err => {
        _welcomeLogClientError('failed to load /welcome/hints-mobile', err);
        return null;
      }),
    ]);
    const hints = (hintData && Array.isArray(hintData.items)) ? hintData.items : [];
    if (introMode === 'disable_animation') {
      _renderSettledWelcome(tabId, {
        asciiArt,
        blocks: [],
        hints,
        includeBlocks: false,
        rotateHints: true,
      });
      return;
    }
    await _runWelcomeAnimation(tabId, {
      asciiArt,
      blocks: [],
      hints,
      includeBlocks: false,
    });
    {
      const state = _readWelcomeState();
      if (!state.active && !state.done) {
      _writeWelcomeState({ tabId: null, bootPending: false });
      if (tabId === _welcomeActiveTabId()) _welcomeMountShellPrompt(tabId);
      }
    }
    return;
  }

  const [data, asciiArt, hintData] = await Promise.all([
    _welcomeApiFetch('/welcome').then(r => r.json()).catch(err => {
      _welcomeLogClientError('failed to load /welcome', err);
      return null;
    }),
    _welcomeApiFetch('/welcome/ascii').then(r => r.text()).catch(err => {
      _welcomeLogClientError('failed to load /welcome/ascii', err);
      return '';
    }),
    _welcomeApiFetch('/welcome/hints').then(r => r.json()).catch(err => {
      _welcomeLogClientError('failed to load /welcome/hints', err);
      return null;
    }),
  ]);
  if (!data || !data.length || !_welcomeIsActive()) {
    _writeWelcomeState({
      active: false,
      tabId: null,
      bootPending: false,
    });
    if (tabId === _welcomeActiveTabId()) _welcomeMountShellPrompt(tabId);
    return;
  }
  const SAMPLE_COUNT   = Math.max(0, Number(_welcomeAppConfig().welcome_sample_count ?? 5) || 0);
  const sampledBlocks = SAMPLE_COUNT > 0 ? _sampleWelcomeBlocks(data, SAMPLE_COUNT) : [];
  const hints = (hintData && Array.isArray(hintData.items)) ? hintData.items : [];
  if (introMode === 'disable_animation') {
    _renderSettledWelcome(tabId, {
      asciiArt,
      blocks: sampledBlocks,
      hints,
      includeBlocks: true,
      rotateHints: true,
    });
    return;
  }
  await _runWelcomeAnimation(tabId, {
    asciiArt,
    blocks: sampledBlocks,
    hints,
    includeBlocks: true,
  });
}

if (typeof window !== 'undefined') {
  if (typeof importedSetWelcomeHandlers === 'function') {
    importedSetWelcomeHandlers({ cancelWelcome, requestWelcomeSettle, welcomeOwnsTab });
  }
}

export {
  cancelWelcome,
  requestWelcomeSettle,
  runWelcome,
  settleWelcome,
  welcomeOwnsTab,
};
