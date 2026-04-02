// ── ANSI renderer ──
const ansi_up = new AnsiUp();
ansi_up.use_classes = false;

// ── Timestamp mode ──
// Cycles: 'off' → 'elapsed' → 'clock' → 'off'
// Body class 'ts-elapsed' / 'ts-clock' drives CSS ::before visibility — no JS
// needed to update existing lines when mode changes.
let tsMode = 'off';

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

  // Plain-text classes: render as text to avoid XSS via ANSI passthrough
  if (cls === 'exit-ok' || cls === 'exit-fail' || cls === 'denied' || cls === 'notice') {
    span.textContent = text;
  } else {
    span.innerHTML = ansi_up.ansi_to_html(text);
  }
  out.appendChild(span);

  // Enforce max output lines — drop oldest lines from the top
  const max = APP_CONFIG.max_output_lines;
  if (max > 0) {
    const lines = out.querySelectorAll('.line');
    if (lines.length > max) {
      for (let i = 0; i < lines.length - max; i++) lines[i].remove();
    }
  }

  out.scrollTop = out.scrollHeight;

  if (tab) {
    tab.rawLines.push({ text, cls: cls || '', tsC, tsE: span.dataset.tsE || '' });
    if (max > 0 && tab.rawLines.length > max) tab.rawLines.splice(0, tab.rawLines.length - max);
  }
}
