// ── Shared output logic ──
function createAnsiUpRenderer() {
  if (typeof AnsiUp === 'function') {
    try {
      const instance = new AnsiUp();
      if (instance && typeof instance.ansi_to_html === 'function') {
        instance.use_classes = false;
        return instance;
      }
    } catch (err) {
      // Fall through to the plain-text renderer below.
    }
  }
  return {
    use_classes: false,
    ansi_to_html(text) {
      return escapeHtml(String(text ?? ''));
    },
  };
}

const ansi_up = createAnsiUpRenderer();

// ── Timestamp mode ──
// Cycles: 'off' → 'elapsed' → 'clock' → 'off'
// Body class 'ts-elapsed' / 'ts-clock' drives CSS ::before visibility — no JS
// needed to update existing lines when mode changes.
let tsMode = 'off';

// ── Line number mode ──
// Cycles: 'off' → 'on' → 'off'
// Body class 'ln-on' enables shared prefix rendering for output rows.
let lnMode = 'off';

const _OUTPUT_SYNC_BURST_LIMIT = 60;
const _OUTPUT_BATCH_SIZE = 80;
const _pendingOutputBatches = new Map();

function _outputPromptPrefix() {
  const promptPrefix = document.querySelector('#shell-prompt-wrap .prompt-prefix');
  const text = promptPrefix ? String(promptPrefix.textContent || '').trim() : '';
  return text || '$';
}

function _formatOutputPrefix(index, tsText, includeTimestamp) {
  const parts = [];
  if (lnMode === 'on') parts.push(String(index));
  if (includeTimestamp && tsText && (tsMode === 'elapsed' || tsMode === 'clock')) {
    parts.push(tsText);
  }
  return parts.join(' ');
}

function _isWelcomeLine(line) {
  if (!line || !line.classList) return false;
  return [...line.classList].some(cls => cls.startsWith('welcome-') || cls.startsWith('wlc-'));
}

function _getPendingOutputBatch(tabId) {
  let state = _pendingOutputBatches.get(tabId);
  if (!state) {
    state = {
      items: [],
      scheduled: false,
      burstCount: 0,
    };
    _pendingOutputBatches.set(tabId, state);
  }
  return state;
}

function _cancelPendingOutputBatch(tabId) {
  const state = _pendingOutputBatches.get(tabId);
  if (!state) return;
  if (state.handle != null) {
    clearTimeout(state.handle);
  }
  _pendingOutputBatches.delete(tabId);
}

function _schedulePendingOutputFlush(tabId) {
  const state = _getPendingOutputBatch(tabId);
  if (state.scheduled) return;
  state.scheduled = true;
  state.handle = setTimeout(() => _flushPendingOutputBatch(tabId), 16);
}

function _buildOutputLine(text, cls, tabId, now, runStart) {
  const span = document.createElement('span');
  span.className = 'line' + (cls ? ' ' + cls : '');
  const content = document.createElement('span');
  content.className = 'line-content';

  const tsC = new Date(now).toTimeString().slice(0, 8);
  span.dataset.tsC = tsC;
  if (runStart) {
    span.dataset.tsE = '+' + ((now - runStart) / 1000).toFixed(1) + 's';
  }

  let rawTextForStorage = text;
  if (cls === 'prompt-echo') {
    const prefix = _outputPromptPrefix();
    const prefixEl = document.createElement('span');
    prefixEl.className = 'prompt-prefix';
    prefixEl.textContent = prefix;
    content.appendChild(prefixEl);
    if (text) content.appendChild(document.createTextNode(' ' + text));
    rawTextForStorage = `${prefix}${text ? ' ' + text : ''}`;
  } else if (cls === 'exit-ok' || cls === 'exit-fail' || cls === 'denied' || cls === 'notice') {
    content.textContent = text;
  } else {
    content.innerHTML = ansi_up.ansi_to_html(text);
  }
  span.appendChild(content);

  return {
    span,
    rawLine: { text: rawTextForStorage, cls: cls || '', tsC, tsE: span.dataset.tsE || '' },
  };
}

function _appendOutputSpan(out, span) {
  const prompt = (typeof shellPromptWrap !== 'undefined' && shellPromptWrap && shellPromptWrap.parentElement === out)
    ? shellPromptWrap
    : null;
  if (prompt) out.insertBefore(span, prompt);
  else out.appendChild(span);
}

function _stickOutputToBottom(out, tab) {
  if (!out) return;
  if (tab) {
    tab._outputFollowToken = (tab._outputFollowToken || 0) + 1;
    tab.suppressOutputScrollTracking = true;
  }
  out.scrollTop = out.scrollHeight;
  if (tab) {
    const token = tab._outputFollowToken;
    setTimeout(() => {
      if (!getTab(tab.id) || tab._outputFollowToken !== token) return;
      out.scrollTop = out.scrollHeight;
      tab.suppressOutputScrollTracking = false;
    }, 16);
  }
}

function _syncTabRawLines(tab, rawLine) {
  if (!tab || !rawLine) return;
  tab.rawLines.push(rawLine);
  const max = APP_CONFIG.max_output_lines;
  if (max > 0 && tab.rawLines.length > max) {
    const removed = tab.rawLines.length - max;
    tab.rawLines.splice(0, removed);
    if (typeof tab.currentRunStartIndex === 'number' && tab.currentRunStartIndex >= 0) {
      tab.currentRunStartIndex = Math.max(0, tab.currentRunStartIndex - removed);
    }
  }
}

function _flushPendingOutputBatch(tabId) {
  const state = _pendingOutputBatches.get(tabId);
  if (!state) return;
  state.scheduled = false;
  state.handle = null;

  const out = getOutput(tabId);
  const tab = getTab(tabId);
  if (!out || !tab) {
    _cancelPendingOutputBatch(tabId);
    return;
  }

  const shouldStickToBottom = tab.followOutput !== false;
  const fragment = document.createDocumentFragment();
  const batch = state.items.splice(0, _OUTPUT_BATCH_SIZE);
  batch.forEach(entry => {
    fragment.appendChild(entry.span);
    _syncTabRawLines(tab, entry.rawLine);
  });
  _appendOutputSpan(out, fragment);

  const max = APP_CONFIG.max_output_lines;
  if (max > 0) {
    const lines = out.querySelectorAll('.line');
    if (lines.length > max) {
      for (let i = 0; i < lines.length - max; i++) lines[i].remove();
    }
  }

  syncOutputPrefixes(out);
  if (shouldStickToBottom) {
    setTimeout(() => _stickOutputToBottom(out, tab), 0);
  }

  if (state.items.length > 0) {
    _schedulePendingOutputFlush(tabId);
    return;
  }

  state.burstCount = 0;
  _maybeMountDeferredPrompt(tabId);
}

function _refreshFollowingOutputsAfterLayout() {
  if (!Array.isArray(tabs)) return;
  tabs.forEach(tab => {
    if (!tab || tab.followOutput === false) return;
    const out = getOutput(tab.id);
    if (!out) return;
    setTimeout(() => _stickOutputToBottom(out, tab), 16);
  });
}

function _maybeMountDeferredPrompt(tabId) {
  const tab = getTab(tabId);
  if (!tab || !tab.deferPromptMount || tab.st === 'running') return;
  const state = _pendingOutputBatches.get(tabId);
  if (state && (state.scheduled || state.items.length > 0)) return;
  tab.deferPromptMount = false;
  if (tabId === activeTabId && typeof mountShellPrompt === 'function') {
    mountShellPrompt(tabId, true);
  }
}

function syncOutputPrefixes(scope = document) {
  const isElement = scope && typeof scope.querySelectorAll === 'function';
  const looksLikeOutput = scope === document
    || (isElement && (
      scope.classList?.contains?.('output')
      || scope.querySelector?.('.line')
      || scope.querySelector?.('#shell-prompt-wrap')
    ));
  const outputs = scope === document
    ? [...document.querySelectorAll('.output')]
    : (looksLikeOutput ? [scope] : [...(scope?.querySelectorAll?.('.output') || [])]);

  outputs.forEach(out => {
    const lines = [...out.querySelectorAll('.line')];
    const prefixStrings = [];
    let visibleIndex = 0;

    lines.forEach(line => {
      if (_isWelcomeLine(line)) {
        line.dataset.prefix = '';
        return;
      }
      visibleIndex += 1;
      const tsText = tsMode === 'elapsed'
        ? String(line.dataset.tsE || '')
        : tsMode === 'clock'
          ? String(line.dataset.tsC || '')
          : '';
      const prefix = _formatOutputPrefix(visibleIndex, tsText, true);
      line.dataset.prefix = prefix;
      prefixStrings.push(prefix);
    });

    const prompt = out.querySelector('#shell-prompt-wrap');
    if (prompt) {
      const promptPrefix = lnMode === 'on' ? String(visibleIndex + 1) : '';
      prompt.dataset.prefix = promptPrefix;
      prefixStrings.push(promptPrefix);
    }

    const prefixWidth = Math.max(0, ...prefixStrings.map(s => String(s || '').length));
    out.style.setProperty('--output-prefix-width', `${prefixWidth}ch`);
  });
}

function _setLnMode(mode) {
  lnMode = mode;
  document.body.classList.toggle('ln-on', mode === 'on');
  const label = mode === 'on' ? 'line numbers: on' : 'line numbers: off';
  const lnBtn = document.getElementById('ln-btn');
  if (lnBtn) {
    lnBtn.textContent = label;
    lnBtn.classList.toggle('active', mode === 'on');
  }
  const mobileLn = document.querySelector('#mobile-menu [data-action="ln"]');
  if (mobileLn) mobileLn.textContent = label;
  syncOutputPrefixes();
  try {
    _refreshFollowingOutputsAfterLayout();
  } catch (_) {}
}

function _setTsMode(mode) {
  tsMode = mode;
  document.body.classList.remove('ts-elapsed', 'ts-clock');
  if (mode === 'elapsed') document.body.classList.add('ts-elapsed');
  if (mode === 'clock') document.body.classList.add('ts-clock');
  syncOutputPrefixes();
  try {
    _refreshFollowingOutputsAfterLayout();
  } catch (_) {}
}

_setLnMode('off');

// Append a line of output to a tab's output panel.
// Stores raw text (with original ANSI codes) in tab.rawLines for permalink and
// HTML export — ansi_up processes codes into HTML spans, so we capture them
// before rendering. Each line also receives data-ts-e (elapsed) and data-ts-c
// (clock) attributes used by the CSS ::before timestamp display.
function appendLine(text, cls, tabId) {
  const id = tabId || activeTabId;
  const out = getOutput(id);
  if (!out) return;

  const tab = getTab(id);
  const now = Date.now();
  const runStart = tab?.runStart || 0;
  const state = _getPendingOutputBatch(id);
  const shouldBatch = state.scheduled || state.items.length > 0 || state.burstCount >= _OUTPUT_SYNC_BURST_LIMIT;
  const { span, rawLine } = _buildOutputLine(text, cls, id, now, runStart);

  if (shouldBatch) {
    state.items.push({ span, rawLine });
    _schedulePendingOutputFlush(id);
    return;
  }

  state.burstCount += 1;

  _appendOutputSpan(out, span);

  // Enforce max output lines — drop oldest lines from the top
  const max = APP_CONFIG.max_output_lines;
  if (max > 0) {
    const lines = out.querySelectorAll('.line');
    if (lines.length > max) {
      for (let i = 0; i < lines.length - max; i++) lines[i].remove();
    }
  }

  syncOutputPrefixes(out);
  if (tab?.followOutput !== false) {
    setTimeout(() => _stickOutputToBottom(out, tab), 0);
  }

  _syncTabRawLines(tab, rawLine);
}
