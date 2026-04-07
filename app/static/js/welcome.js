// ── Welcome typeout animation ──
// Fetches welcome content from /welcome, /welcome/ascii, and /welcome/hints
// for desktop, and from /welcome/ascii-mobile plus /welcome/hints for the
// mobile variant. Renders the intro into the initial tab with status lines,
// typed commands, inline comment hints, and a closing hint row.
// Calling cancelWelcome() (e.g. when the user runs a command) stops the
// animation immediately; runner.js also calls clearTab to wipe partial output.

let _welcomeActive = false;
let _welcomeDone   = false;  // true once the animation has fully completed
let _welcomeTabId = null;
let _welcomeBanner = null;
let _welcomeLiveLine = null;
let _welcomeHintNode = null;
let _welcomeStatusNodes = [];
let _welcomePlan = null;
let _welcomeNextBlockIndex = 0;
let _welcomeSettleRequested = false;
let _welcomeBootPending = true;
const _welcomeWaiters = new Set();
const _welcomePrompt = 'anon@shell.darklab.sh:~$';
const _welcomeGroupOrder = ['basics', 'dns', 'web', 'recon', 'advanced'];
const _welcomeStatusFrames = ['loading /', 'loading -', 'loading \\', 'loading |'];

function _shouldUseMobileWelcomeSequence() {
  if (typeof useMobileTerminalViewportMode === 'function') {
    return useMobileTerminalViewportMode();
  }
  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
    return window.matchMedia('(max-width: 600px)').matches;
  }
  return false;
}

function welcomeOwnsTab(tabId) {
  return !!tabId && _welcomeTabId === tabId && (_welcomeActive || _welcomeDone);
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
  _welcomeSettleRequested = false;
}

function _setWelcomeBannerSettled(settled) {
  if (!_welcomeBanner) return;
  _welcomeBanner.classList.toggle('welcome-banner-settled', !!settled);
}

function _setWelcomeStatus(index, value) {
  const node = _welcomeStatusNodes[index];
  if (!node) return;
  node.dataset.state = value;
  node.textContent = value;
  node.classList.remove('welcome-status-loading', 'welcome-status-loaded');
  node.classList.add(value === 'loaded' ? 'welcome-status-loaded' : 'welcome-status-loading');
}

async function _spinWelcomeStatus(node, stepMs = 140) {
  if (!node) return;
  let frame = 0;
  node.dataset.state = 'loading';
  while (_welcomeActive && node.isConnected && node.dataset.state === 'loading') {
    node.textContent = _welcomeStatusFrames[frame % _welcomeStatusFrames.length];
    frame++;
    await _sleep(stepMs);
  }
}

function _appendWelcomeStatusRow(label, value = 'loading....') {
  const statusStack = _welcomeBanner.querySelector('.welcome-status-stack');
  if (!statusStack) return null;

  const statusLine = document.createElement('div');
  statusLine.className = 'line welcome-status-line welcome-status-line-enter';

  const labelSpan = document.createElement('span');
  labelSpan.className = 'welcome-status-label';
  labelSpan.textContent = `${label}:`;

  const valueSpan = document.createElement('span');
  valueSpan.className = value === 'loaded'
    ? 'welcome-status-loaded'
    : 'welcome-status-loading';
  valueSpan.textContent = value;
  valueSpan.dataset.state = value === 'loaded' ? 'loaded' : 'loading';

  statusLine.append(labelSpan, valueSpan);
  statusStack.appendChild(statusLine);
  _welcomeStatusNodes.push(valueSpan);
  if (value !== 'loaded') void _spinWelcomeStatus(valueSpan);

  requestAnimationFrame(() => {
    statusLine.classList.add('welcome-status-line-visible');
  });

  return valueSpan;
}

async function _runWelcomeStatusSequence(labels, intervalMs, staggerMs = null) {
  if (!_welcomeActive || !_welcomeBanner || !labels.length) return;
  const settlePromises = [];
  const STAGGER_MS = staggerMs == null
    ? Math.max(140, Math.floor(intervalMs * 0.32))
    : staggerMs;

  for (let i = 0; i < labels.length; i++) {
    if (!_welcomeActive) return;
    _appendWelcomeStatusRow(labels[i], 'loading....');
    settlePromises.push((async (index) => {
      await _sleep(intervalMs);
      if (_welcomeActive) _setWelcomeStatus(index, 'loaded');
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
  const out = getOutput(tabId);
  if (!out) return false;

  _renderWelcomeAsciiStream(tabId, asciiArt);
  if (!_welcomeActive) return false;

  const statusLabels = Array.isArray(APP_CONFIG.welcome_status_labels)
    ? APP_CONFIG.welcome_status_labels
        .map(label => String(label || '').trim().toUpperCase())
        .filter(Boolean)
        .slice(0, 6)
    : [];

  const effectiveStatusLabels = statusLabels.length
    ? statusLabels
    : ['CONFIG', 'RUNNER', 'HISTORY', 'LIMITS', 'AUTOCOMPLETE'];
  const introBlocks = includeBlocks ? blocks : [];
  _welcomePlan = {
    asciiArt,
    statusLabels: effectiveStatusLabels,
    blocks: introBlocks,
    hints,
  };
  if (_welcomeSettleRequested) {
    settleWelcome(tabId);
    return true;
  }

  const INTER_BLOCK_MS = APP_CONFIG.welcome_inter_block_ms ?? 1500;
  const POST_STATUS_PAUSE_MS = Math.max(0, Number(APP_CONFIG.welcome_post_status_pause_ms ?? 220) || 0);
  const STATUS_MS = Math.max(820, Math.floor(INTER_BLOCK_MS * 0.78));
  const STATUS_STAGGER_MS = Math.max(140, Math.floor(INTER_BLOCK_MS * 0.28));
  const CHAR_MS = APP_CONFIG.welcome_char_ms ?? 10;
  const JITTER = APP_CONFIG.welcome_jitter_ms ?? 10;
  const POST_CMD_MS = APP_CONFIG.welcome_post_cmd_ms ?? 700;
  const FIRST_PROMPT_IDLE_MS = Math.max(0, Number(APP_CONFIG.welcome_first_prompt_idle_ms ?? 2100) || 0);
  const HINT_INTERVAL_MS = Math.max(0, Number(APP_CONFIG.welcome_hint_interval_ms ?? 4200) || 0);
  const HINT_ROTATIONS = Math.max(0, Number(APP_CONFIG.welcome_hint_rotations ?? 2) || 0);

  await _runWelcomeStatusSequence(effectiveStatusLabels, STATUS_MS, STATUS_STAGGER_MS);
  if (!_welcomeActive) return false;
  if (_welcomeSettleRequested) {
    settleWelcome(tabId);
    return true;
  }
  _setWelcomeBannerSettled(true);
  await _sleep(Math.max(POST_STATUS_PAUSE_MS, Math.floor(INTER_BLOCK_MS * 0.24)));
  if (!_welcomeActive) return false;
  if (_welcomeSettleRequested) {
    settleWelcome(tabId);
    return true;
  }

  for (const [blockIndex, block] of introBlocks.entries()) {
    if (!_welcomeActive) break;
    if (_welcomeSettleRequested) {
      settleWelcome(tabId);
      return true;
    }

    const currentOut = getOutput(tabId);
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
      const commands = getOutput(tabId)?.querySelectorAll('.welcome-command');
      const featuredLine = commands && commands[commands.length - 1];
      if (featuredLine) {
        _ensureFeaturedWelcomeBadge(featuredLine, block.cmd);
      }
    }
  }

  if (_welcomeActive) {
    _welcomeDone = true;
    if (hints.length) {
      void _runWelcomeHintFeed(tabId, hints, HINT_INTERVAL_MS, HINT_ROTATIONS);
    } else {
      _appendWelcomeOutput(tabId, 'Enter runs the command · Up/Down navigates autocomplete · History keeps previous runs', 'welcome-hint');
      _welcomeActive = false;
      _welcomeBootPending = false;
      if (typeof mountShellPrompt === 'function' && tabId === activeTabId) mountShellPrompt(tabId);
    }
  }

  return true;
}

function cancelWelcome(tabId = null) {
  if (tabId && _welcomeTabId && _welcomeTabId !== tabId) return false;
  _welcomeActive = false;
  _welcomeDone   = false;
  _welcomeTabId = null;
  _welcomeBootPending = false;
  _flushWelcomeWaiters();
  _clearWelcomeLiveLine();
  _clearWelcomeBanner();
  _resetWelcomePlan();
  if (typeof mountShellPrompt === 'function' && tabId === activeTabId) {
    mountShellPrompt(tabId, true);
    setTimeout(() => {
      if (cmdInput && typeof cmdInput.focus === 'function') cmdInput.focus();
      if (typeof shellPromptWrap !== 'undefined' && shellPromptWrap) shellPromptWrap.classList.add('shell-prompt-focused');
    }, 0);
  }
  if (cmdInput && typeof cmdInput.focus === 'function') cmdInput.focus();
  if (typeof shellPromptWrap !== 'undefined' && shellPromptWrap) shellPromptWrap.classList.add('shell-prompt-focused');
  return true;
}

function requestWelcomeSettle(tabId = activeTabId) {
  if (!tabId || !_welcomeActive || _welcomeTabId !== tabId) return false;
  _welcomeSettleRequested = true;
  _flushWelcomeWaiters();
  if (_welcomePlan) {
    return settleWelcome(tabId);
  }
  return true;
}

async function _typeWelcomeCommand(tabId, cmd, { charMs, jitterMs, postMs, startDelayMs = 0, commentText = null, interactive = true } = {}) {
  const out = getOutput(tabId);
  if (!out) return false;

  const CHAR_MS = charMs ?? (APP_CONFIG.welcome_char_ms ?? 10);
  const JITTER = jitterMs ?? (APP_CONFIG.welcome_jitter_ms ?? 10);
  const POST_CMD_MS = postMs ?? (APP_CONFIG.welcome_post_cmd_ms ?? 700);

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
  if (!_welcomeActive) { typingSpan.remove(); _welcomeLiveLine = null; return false; }

  for (let i = 0; i < cmd.length; i++) {
    if (!_welcomeActive) { typingSpan.remove(); _welcomeLiveLine = null; return false; }
    wlcText.textContent = cmd.slice(0, i + 1);
    out.scrollTop = out.scrollHeight;
    await _sleep(CHAR_MS + Math.random() * JITTER);
  }

  await _sleep(POST_CMD_MS);
  if (!_welcomeActive) { typingSpan.remove(); _welcomeLiveLine = null; return false; }
  _finalizeWelcomeCommandLine(tabId, typingSpan, cmd, commentText, { interactive });
  return true;
}

function _renderWelcomeAsciiStream(tabId, asciiArt) {
  const out = getOutput(tabId);
  if (!out) return;

  const artLines = (asciiArt || 'shell.darklab.sh')
    .split('\n')
    .map(line => line.replace(/\s+$/g, ''))
    .filter(line => line.length > 0);

  const banner = document.createElement('div');
  banner.className = 'welcome-banner';

  const artBlock = document.createElement('pre');
  artBlock.className = 'line welcome-ascii-art';
  artBlock.setAttribute('aria-label', 'ASCII art banner');
  artBlock.textContent = artLines.join('\n');

  const statusStack = document.createElement('div');
  statusStack.className = 'welcome-status-stack';
  statusStack.setAttribute('aria-label', 'System status');
  _welcomeStatusNodes = [];

  banner.append(artBlock, statusStack);
  out.appendChild(banner);
  _welcomeBanner = banner;
  requestAnimationFrame(() => {
    banner.classList.add('welcome-banner-visible');
  });
  out.scrollTop = out.scrollHeight;
}

function _appendWelcomeCommand(tabId, cmd, commentText = null, { interactive = true } = {}) {
  const out = getOutput(tabId);
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
    if (_welcomeActive && welcomeOwnsTab(tabId)) settleWelcome(tabId);
    if (!cmdInput) return;
    cmdInput.value = cmd;
    cmdInput.focus();
    if (typeof cmdInput.setSelectionRange === 'function') {
      const end = cmdInput.value.length;
      cmdInput.setSelectionRange(end, end);
    }
    // Defer so the document click handler has already run before autocomplete updates.
    setTimeout(() => cmdInput.dispatchEvent(new Event('input')), 0);
  }
  if (interactive) {
    cmdText.addEventListener('click', loadCommand);
    cmdText.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        loadCommand();
      }
    });
  }
  out.appendChild(line);
  out.scrollTop = out.scrollHeight;
  return line;
}

function _finalizeWelcomeCommandLine(tabId, line, cmd, commentText = null, { interactive = true } = {}) {
  const out = getOutput(tabId);
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
      if (_welcomeActive && welcomeOwnsTab(tabId)) settleWelcome(tabId);
      if (!cmdInput) return;
      cmdInput.value = cmd;
      cmdInput.focus();
      if (typeof cmdInput.setSelectionRange === 'function') {
        const end = cmdInput.value.length;
        cmdInput.setSelectionRange(end, end);
      }
      setTimeout(() => cmdInput.dispatchEvent(new Event('input')), 0);
    }
    boundCmdText.addEventListener('click', loadCommand);
    boundCmdText.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        loadCommand();
      }
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
  const out = getOutput(tabId);
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

function _pickRandomHint(hints, used) {
  if (!hints.length) return '';
  const pool = hints.filter(hint => !used.has(hint));
  if (pool.length === 0) {
    used.clear();
    pool.push(...hints);
  }
  return pool[Math.floor(Math.random() * pool.length)] || '';
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
  return _welcomeActive
    && welcomeOwnsTab(tabId)
    && activeTabId === tabId
    && (!cmdInput || !cmdInput.value.trim());
}

async function _showWelcomeHint(tabId, text, initial = false) {
  const out = getOutput(tabId);
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
  if (!_welcomeActive) return null;

  _welcomeHintNode.textContent = `# ${String(text).trim()}`;
  requestAnimationFrame(() => {
    if (_welcomeHintNode) _welcomeHintNode.classList.add('welcome-hint-visible');
  });
  out.scrollTop = out.scrollHeight;
  return _welcomeHintNode;
}

async function _runWelcomeHintFeed(tabId, hints, intervalMs, maxRotations = 2) {
  if (!_welcomeActive || !_welcomeDone || !Array.isArray(hints) || !hints.length) return;

  const used = new Set();
  let current = _pickRandomHint(hints, used);
  if (!current) return;
  used.add(current);
  await _showWelcomeHint(tabId, current, true);
  if (typeof mountShellPrompt === 'function' && tabId === activeTabId) {
    mountShellPrompt(tabId, true);
    if (cmdInput && typeof cmdInput.focus === 'function') cmdInput.focus();
    if (typeof shellPromptWrap !== 'undefined' && shellPromptWrap) shellPromptWrap.classList.add('shell-prompt-focused');
  }

  let rotations = 0;
  while (_shouldRotateWelcomeHints(tabId) && rotations < maxRotations) {
    await _sleep(intervalMs);
    if (!_shouldRotateWelcomeHints(tabId)) break;

    current = _pickRandomHint(hints, used);
    if (!current) return;
    used.add(current);
    await _showWelcomeHint(tabId, current, false);
    rotations++;
  }

  _welcomeActive = false;
  if (typeof mountShellPrompt === 'function' && tabId === activeTabId) mountShellPrompt(tabId);
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
  badge.addEventListener('click', () => {
    line.querySelector('.welcome-command-text')?.click();
  });
  badge.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      line.querySelector('.welcome-command-text')?.click();
    }
  });
  line.insertBefore(badge, comment || null);
}

function _ensureWelcomeFinalHint(tabId, hints) {
  if (_welcomeHintNode) return;
  if (Array.isArray(hints) && hints.length) {
    const line = document.createElement('span');
    line.className = 'line welcome-hint welcome-hint-feed welcome-hint-visible';
    line.textContent = `# ${String(hints[0]).trim()}`;
    getOutput(tabId)?.appendChild(line);
    _welcomeHintNode = line;
    if (typeof mountShellPrompt === 'function' && tabId === activeTabId) mountShellPrompt(tabId, true);
    return;
  }
  _appendWelcomeOutput(tabId, 'Enter runs the command · Up/Down navigates autocomplete · History keeps previous runs', 'welcome-hint');
  if (typeof mountShellPrompt === 'function' && tabId === activeTabId) mountShellPrompt(tabId, true);
}

function settleWelcome(tabId = activeTabId) {
  if (!welcomeOwnsTab(tabId)) return false;
  const out = getOutput(tabId);
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
    else _appendWelcomeStatusRow(label, 'loaded');
  });
  _setWelcomeBannerSettled(true);

  const blocks = (_welcomePlan && Array.isArray(_welcomePlan.blocks)) ? _welcomePlan.blocks : [];
  for (let i = _welcomeNextBlockIndex; i < blocks.length; i++) {
    const line = _appendWelcomeCommand(tabId, blocks[i].cmd, blocks[i].out || null);
    if (i === 0) {
      _ensureFeaturedWelcomeBadge(line, blocks[i].cmd);
    }
  }
  _welcomeNextBlockIndex = blocks.length;

  _welcomeDone = true;
  _ensureWelcomeFinalHint(tabId, _welcomePlan && _welcomePlan.hints);
  _welcomeActive = false;
  _welcomeBootPending = false;
  if (typeof mountShellPrompt === 'function' && tabId === activeTabId) mountShellPrompt(tabId);
  out.scrollTop = out.scrollHeight;
  return true;
}

async function runWelcome() {
  const tabId = activeTabId;
  _welcomeBootPending = true;
  _welcomeActive = true;
  _welcomeDone = false;
  _welcomeTabId = activeTabId;
  _welcomeSettleRequested = false;
  if (typeof unmountShellPrompt === 'function') unmountShellPrompt();

  if (_shouldUseMobileWelcomeSequence()) {
    const [asciiArt, hintData] = await Promise.all([
      apiFetch('/welcome/ascii-mobile').then(r => r.text()).catch(err => {
        if (typeof logClientError === 'function') logClientError('failed to load /welcome/ascii-mobile', err);
        return '';
      }),
      apiFetch('/welcome/hints').then(r => r.json()).catch(err => {
        if (typeof logClientError === 'function') logClientError('failed to load /welcome/hints', err);
        return null;
      }),
    ]);
    const hints = (hintData && Array.isArray(hintData.items)) ? hintData.items : [];
    await _runWelcomeAnimation(tabId, {
      asciiArt,
      blocks: [],
      hints,
      includeBlocks: false,
    });
    if (!_welcomeActive && !_welcomeDone) {
      _welcomeTabId = null;
      _welcomeBootPending = false;
      if (typeof mountShellPrompt === 'function' && tabId === activeTabId) mountShellPrompt(tabId);
    }
    return;
  }

  const [data, asciiArt, hintData] = await Promise.all([
    apiFetch('/welcome').then(r => r.json()).catch(err => {
      if (typeof logClientError === 'function') logClientError('failed to load /welcome', err);
      return null;
    }),
    apiFetch('/welcome/ascii').then(r => r.text()).catch(err => {
      if (typeof logClientError === 'function') logClientError('failed to load /welcome/ascii', err);
      return '';
    }),
    apiFetch('/welcome/hints').then(r => r.json()).catch(err => {
      if (typeof logClientError === 'function') logClientError('failed to load /welcome/hints', err);
      return null;
    }),
  ]);
  if (!data || !data.length || !_welcomeActive) {
    _welcomeActive = false;
    _welcomeTabId = null;
    _welcomeBootPending = false;
    if (typeof mountShellPrompt === 'function' && tabId === activeTabId) mountShellPrompt(tabId);
    return;
  }
  const SAMPLE_COUNT   = Math.max(0, Number(APP_CONFIG.welcome_sample_count ?? 5) || 0);
  const sampledBlocks = SAMPLE_COUNT > 0 ? _sampleWelcomeBlocks(data, SAMPLE_COUNT) : [];
  const hints = (hintData && Array.isArray(hintData.items)) ? hintData.items : [];
  await _runWelcomeAnimation(tabId, {
    asciiArt,
    blocks: sampledBlocks,
    hints,
    includeBlocks: true,
  });
}
