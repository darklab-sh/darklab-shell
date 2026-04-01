// ── ANSI renderer ──
const ansi_up = new AnsiUp();
ansi_up.use_classes = false;

// Append a line of output to a tab's output panel.
// Stores raw text (with original ANSI codes) in tab.rawLines for permalink
// colour preservation — ansi_up processes codes into HTML spans and discards
// the originals, so we capture them here before rendering.
function appendLine(text, cls, tabId) {
  const id = tabId || activeTabId;
  const out = getOutput(id);
  if (!out) return;

  const span = document.createElement('span');
  span.className = 'line' + (cls ? ' ' + cls : '');
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

  const t = tabs.find(t => t.id === (tabId || activeTabId));
  if (t) {
    t.rawLines.push({ text, cls: cls || '' });
    if (max > 0 && t.rawLines.length > max) t.rawLines.splice(0, t.rawLines.length - max);
  }
}
