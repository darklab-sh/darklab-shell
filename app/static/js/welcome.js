// ── Welcome typeout animation ──
// Fetches welcome.yaml blocks from /welcome and types each command out
// character-by-character into the initial tab, with a blinking cursor.
// Calling cancelWelcome() (e.g. when the user runs a command) stops the
// animation immediately; runner.js also calls clearTab to wipe partial output.

let _welcomeActive = false;
let _welcomeDone   = false;  // true once the animation has fully completed

function cancelWelcome() {
  _welcomeActive = false;
  _welcomeDone   = false;
}

async function runWelcome() {
  _welcomeActive = true;

  const data = await apiFetch('/welcome').then(r => r.json()).catch(() => null);
  if (!data || !data.length || !_welcomeActive) {
    _welcomeActive = false;
    return;
  }

  const tabId = activeTabId;
  const CHAR_MS        = APP_CONFIG.welcome_char_ms        ?? 10;
  const JITTER         = APP_CONFIG.welcome_jitter_ms      ?? 10;
  const POST_CMD_MS    = APP_CONFIG.welcome_post_cmd_ms    ?? 700;
  const INTER_BLOCK_MS = APP_CONFIG.welcome_inter_block_ms ?? 1500;

  for (const block of data) {
    if (!_welcomeActive) break;

    const out = getOutput(tabId);
    if (!out) break;

    // ── Build the live typing line ──
    // Structure: "$ " prefix | typed text so far | blinking block cursor
    const typingSpan = document.createElement('span');
    typingSpan.className = 'line';
    typingSpan.innerHTML =
      '<span class="wlc-prefix">$ </span>' +
      '<span class="wlc-text"></span>' +
      '<span class="wlc-cursor"></span>';
    out.appendChild(typingSpan);
    out.scrollTop = out.scrollHeight;

    const wlcText = typingSpan.querySelector('.wlc-text');

    // ── Type each character ──
    for (let i = 0; i < block.cmd.length; i++) {
      if (!_welcomeActive) { typingSpan.remove(); return; }
      wlcText.textContent = block.cmd.slice(0, i + 1);
      out.scrollTop = out.scrollHeight;
      await new Promise(r => setTimeout(r, CHAR_MS + Math.random() * JITTER));
    }

    // ── Pause with cursor blinking after typing, before showing output ──
    await new Promise(r => setTimeout(r, POST_CMD_MS));
    if (!_welcomeActive) { typingSpan.remove(); return; }

    // ── Commit: replace the live span with a proper stored line ──
    typingSpan.remove();
    appendLine('$ ' + block.cmd, '', tabId);

    // ── Optional output lines ──
    if (block.out) {
      block.out.split('\n').forEach(line => {
        if (_welcomeActive) appendLine(line, 'notice', tabId);
      });
    }

    // ── Blinking cursor pause before next block ──
    const cursorSpan = document.createElement('span');
    cursorSpan.className = 'line';
    cursorSpan.innerHTML = '<span class="wlc-cursor"></span>';
    out.appendChild(cursorSpan);
    out.scrollTop = out.scrollHeight;
    await new Promise(r => setTimeout(r, INTER_BLOCK_MS));
    cursorSpan.remove();
    if (!_welcomeActive) return;
  }

  _welcomeActive = false;
  _welcomeDone   = true;
}
