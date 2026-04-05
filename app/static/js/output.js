// ── ANSI renderer ──
const ansi_up = new AnsiUp();
ansi_up.use_classes = false;

// ── Timestamp mode ──
// Cycles: 'off' → 'elapsed' → 'clock' → 'off'
// Body class 'ts-elapsed' / 'ts-clock' drives CSS ::before visibility — no JS
// needed to update existing lines when mode changes.
let tsMode = 'off';

// ── Line number mode ──
// Cycles: 'off' → 'on' → 'off'
// Body class 'ln-on' enables shared prefix rendering for output rows.
let lnMode = 'off';

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
}

function _setTsMode(mode) {
  tsMode = mode;
  document.body.classList.remove('ts-elapsed', 'ts-clock');
  if (mode === 'elapsed') document.body.classList.add('ts-elapsed');
  if (mode === 'clock') document.body.classList.add('ts-clock');
  syncOutputPrefixes();
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

  const tab = tabs.find(t => t.id === id);
  const now = Date.now();
  const runStart = tab?.runStart || 0;

  const span = document.createElement('span');
  span.className = 'line' + (cls ? ' ' + cls : '');

  // Set timestamp data attributes; CSS ::before reads these — no DOM children needed.
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
    span.appendChild(prefixEl);
    if (text) span.appendChild(document.createTextNode(' ' + text));
    rawTextForStorage = `${prefix}${text ? ' ' + text : ''}`;
  } else if (cls === 'exit-ok' || cls === 'exit-fail' || cls === 'denied' || cls === 'notice') {
    // Plain-text classes: render as text to avoid XSS via ANSI passthrough
    span.textContent = text;
  } else {
    span.innerHTML = ansi_up.ansi_to_html(text);
  }
  const prompt = (typeof shellPromptWrap !== 'undefined' && shellPromptWrap && shellPromptWrap.parentElement === out)
    ? shellPromptWrap
    : null;
  if (prompt) out.insertBefore(span, prompt);
  else out.appendChild(span);

  // Enforce max output lines — drop oldest lines from the top
  const max = APP_CONFIG.max_output_lines;
  if (max > 0) {
    const lines = out.querySelectorAll('.line');
    if (lines.length > max) {
      for (let i = 0; i < lines.length - max; i++) lines[i].remove();
    }
  }

  out.scrollTop = out.scrollHeight;

  syncOutputPrefixes(out);

  if (tab) {
    tab.rawLines.push({ text: rawTextForStorage, cls: cls || '', tsC, tsE: span.dataset.tsE || '' });
    if (max > 0 && tab.rawLines.length > max) tab.rawLines.splice(0, tab.rawLines.length - max);
  }
}
