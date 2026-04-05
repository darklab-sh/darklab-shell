// ── Tab state ──
let tabs = [];
let activeTabId = null;
let _tabsScrollControlsBound = false;
let _draggedTabId = null;
let _dragMoved = false;
let _tabDragSuppressClickUntil = 0;

function updateTabScrollButtons() {
  const leftBtn = document.getElementById('tabs-scroll-left');
  const rightBtn = document.getElementById('tabs-scroll-right');
  if (!leftBtn || !rightBtn || !tabsBar) return;
  const maxScroll = Math.max(0, tabsBar.scrollWidth - tabsBar.clientWidth);
  if (maxScroll <= 1) {
    leftBtn.disabled = true;
    rightBtn.disabled = true;
    return;
  }
  leftBtn.disabled = tabsBar.scrollLeft <= 1;
  rightBtn.disabled = tabsBar.scrollLeft >= (maxScroll - 1);
}

function ensureActiveTabVisible(tabId) {
  const tabEl = document.querySelector(`.tab[data-id="${tabId}"]`);
  if (!tabEl || typeof tabEl.scrollIntoView !== 'function') return;
  tabEl.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' });
}

function scrollTabsBar(direction) {
  if (!tabsBar || typeof tabsBar.scrollBy !== 'function') return;
  tabsBar.scrollBy({ left: direction * 220, behavior: 'smooth' });
  setTimeout(updateTabScrollButtons, 180);
}

function setupTabScrollControls() {
  if (_tabsScrollControlsBound) return;
  const leftBtn = document.getElementById('tabs-scroll-left');
  const rightBtn = document.getElementById('tabs-scroll-right');
  if (!leftBtn || !rightBtn || !tabsBar) return;
  leftBtn.addEventListener('click', () => scrollTabsBar(-1));
  rightBtn.addEventListener('click', () => scrollTabsBar(1));
  tabsBar.addEventListener('scroll', updateTabScrollButtons, { passive: true });
  window.addEventListener('resize', updateTabScrollButtons);
  _tabsScrollControlsBound = true;
  updateTabScrollButtons();
}

function syncTabOrderFromDom() {
  if (!tabsBar) return;
  const orderedIds = [...tabsBar.querySelectorAll('.tab')].map(node => node.dataset.id);
  if (!orderedIds.length) return;
  const byId = new Map(tabs.map(tab => [tab.id, tab]));
  tabs = orderedIds.map(id => byId.get(id)).filter(Boolean);
}

function bindTabDragReorder(tab, id) {
  if (!tab) return;
  tab.setAttribute('draggable', 'true');

  tab.addEventListener('dragstart', e => {
    _draggedTabId = id;
    _dragMoved = false;
    tab.classList.add('tab-dragging');
    if (e.dataTransfer) {
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', id);
    }
  });

  tab.addEventListener('dragover', e => {
    if (!_draggedTabId || _draggedTabId === id || !tabsBar) return;
    const dragged = tabsBar.querySelector(`.tab[data-id="${_draggedTabId}"]`);
    if (!dragged) return;
    e.preventDefault();

    const rect = tab.getBoundingClientRect();
    const after = e.clientX > rect.left + (rect.width / 2);
    if (after) {
      if (tab.nextSibling !== dragged) tabsBar.insertBefore(dragged, tab.nextSibling);
    } else if (tab !== dragged.nextSibling) {
      tabsBar.insertBefore(dragged, tab);
    }
    _dragMoved = true;
  });

  tab.addEventListener('drop', e => {
    if (!_draggedTabId) return;
    e.preventDefault();
    syncTabOrderFromDom();
    updateTabScrollButtons();
    ensureActiveTabVisible(activeTabId);
  });

  tab.addEventListener('dragend', () => {
    tab.classList.remove('tab-dragging');
    if (_dragMoved) {
      syncTabOrderFromDom();
      updateTabScrollButtons();
      ensureActiveTabVisible(activeTabId);
      _tabDragSuppressClickUntil = Date.now() + 160;
      if (id === activeTabId && typeof cmdInput !== 'undefined' && cmdInput) {
        cmdInput.focus();
      }
    }
    _draggedTabId = null;
    _dragMoved = false;
  });
}

function unmountShellPrompt() {
  if (typeof shellPromptWrap === 'undefined' || !shellPromptWrap) return;
  if (shellPromptWrap.parentElement) shellPromptWrap.remove();
}

function mountShellPrompt(tabId, force = false) {
  if (typeof shellPromptWrap === 'undefined' || !shellPromptWrap) return;
  const tabState = tabs.find(t => t.id === tabId);
  // Never show a prompt while a command is running in this tab.
  if (tabState && tabState.st === 'running') {
    unmountShellPrompt();
    return;
  }
  if (!force && typeof _welcomeActive !== 'undefined' && _welcomeActive
      && typeof welcomeOwnsTab === 'function' && welcomeOwnsTab(tabId)) {
    unmountShellPrompt();
    return;
  }
  const panel = document.querySelector(`.tab-panel[data-id="${tabId}"]`);
  if (!panel) return;
  const out = panel.querySelector('.output');
  if (!out) return;
  out.appendChild(shellPromptWrap);
  out.scrollTop = out.scrollHeight;
  if (typeof syncOutputPrefixes === 'function') syncOutputPrefixes(out);
}

function updateNewTabBtn() {
  const btn = document.getElementById('new-tab-btn');
  if (!btn) return;
  const atLimit = APP_CONFIG.max_tabs > 0 && tabs.length >= APP_CONFIG.max_tabs;
  btn.disabled = atLimit;
  btn.title = atLimit ? `Tab limit reached (max ${APP_CONFIG.max_tabs})` : '';
}

function createTab(label) {
  if (APP_CONFIG.max_tabs > 0 && tabs.length >= APP_CONFIG.max_tabs) {
    showToast(`Tab limit reached (max ${APP_CONFIG.max_tabs})`);
    return null;
  }
  const id = 'tab-' + Date.now();

  const tab = document.createElement('div');
  tab.className = 'tab';
  tab.dataset.id = id;
  tab.innerHTML = `<span class="tab-status idle"></span><span class="tab-label">${escapeHtml(label)}</span><span class="tab-close">✕</span>`;
  tab.addEventListener('click', e => {
    if (Date.now() < _tabDragSuppressClickUntil) return;
    if (e.target.classList.contains('tab-close')) { closeTab(id); return; }
    activateTab(id);
  });

  // Double-click tab label to rename
  const labelEl = tab.querySelector('.tab-label');
  labelEl.addEventListener('dblclick', e => {
    e.stopPropagation();
    startTabRename(id, labelEl);
  });
  bindTabDragReorder(tab, id);

  const newTabButton = document.getElementById('new-tab-btn');
  if (newTabButton && newTabButton.parentElement === tabsBar) {
    tabsBar.insertBefore(tab, newTabButton);
  } else {
    tabsBar.appendChild(tab);
  }

  const panel = document.createElement('div');
  panel.className = 'tab-panel';
  panel.dataset.id = id;
  panel.innerHTML = `
    <div class="terminal-body">
      <div class="output" id="output-${id}"></div>
      <div class="terminal-actions">
        <button class="term-action-btn tab-kill-btn" data-action="kill" data-tab="${id}" style="display:none;color:var(--red);border-color:var(--red)">■ Kill</button>
        <button class="term-action-btn" data-action="permalink" data-tab="${id}">permalink</button>
        <button class="term-action-btn" data-action="copy"      data-tab="${id}">copy</button>
        <button class="term-action-btn" data-action="save"      data-tab="${id}">save txt</button>
        <button class="term-action-btn" data-action="html"      data-tab="${id}">save html</button>
        <button class="term-action-btn" data-action="clear"     data-tab="${id}">clear</button>
      </div>
    </div>`;
  panel.querySelector('.terminal-body')?.addEventListener('click', e => {
    if (id !== activeTabId) return;
    if (e.target.closest('.term-action-btn')) return;
    if (e.target.closest('.welcome-command-loadable')) return;
    if (typeof cmdInput !== 'undefined' && cmdInput) cmdInput.focus();
  });
  panel.querySelectorAll('[data-action]').forEach(btn => {
    btn.addEventListener('click', () => {
      const action = btn.dataset.action;
      if (action === 'kill')      confirmKill(id);
      if (action === 'clear')     { cancelWelcome(id); clearTab(id); }
      if (action === 'copy')      copyTab(id);
      if (action === 'save')      saveTab(id);
      if (action === 'html')      exportTabHtml(id);
      if (action === 'permalink') permalinkTab(id);
    });
  });
  tabPanels.appendChild(panel);

  tabs.push({ id, label, command: '', runId: null, runStart: null, exitCode: null, rawLines: [], killed: false, pendingKill: false, st: 'idle', renamed: false });
  activateTab(id);
  updateNewTabBtn();
  updateTabScrollButtons();
  return id;
}

function activateTab(id) {
  activeTabId = id;
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.id === id));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.dataset.id === id));
  mountShellPrompt(id);
  const t = tabs.find(t => t.id === id);
  setStatus(t ? (t.st || 'idle') : 'idle');
  ensureActiveTabVisible(id);
  updateTabScrollButtons();
  clearSearch();
  const input = document.getElementById('cmd');
  if (input) {
    input.value = '';
    if (typeof resetCmdHistoryNav === 'function') resetCmdHistoryNav();
    input.dispatchEvent(new Event('input'));
    input.focus();
  }
}

function closeTab(id) {
  cancelWelcome(id);
  if (tabs.length === 1) {
    // Last tab: reset to blank instead of closing
    clearTab(id);
    setTabLabel(id, 'tab 1');
    const t = tabs[0];
    t.runId = null;
    t.runStart = null;
    t.exitCode = null;
    t.killed = false;
    t.pendingKill = false;
    return;
  }
  const idx = tabs.findIndex(t => t.id === id);
  tabs.splice(idx, 1);
  document.querySelector(`.tab[data-id="${id}"]`).remove();
  document.querySelector(`.tab-panel[data-id="${id}"]`).remove();
  if (activeTabId === id) {
    activateTab(tabs[Math.min(idx, tabs.length - 1)].id);
  }
  updateNewTabBtn();
  updateTabScrollButtons();
}

function setTabStatus(id, st) {
  const dot = document.querySelector(`.tab[data-id="${id}"] .tab-status`);
  if (dot) dot.className = `tab-status ${st}`;
  const t = tabs.find(t => t.id === id);
  if (t) t.st = st;
  if (id === activeTabId) {
    if (st === 'running') unmountShellPrompt();
    else mountShellPrompt(id);
  }
}

function setTabLabel(id, label) {
  const lbl = document.querySelector(`.tab[data-id="${id}"] .tab-label`);
  if (lbl) lbl.textContent = label.length > 28 ? label.slice(0, 26) + '…' : label;
  const t = tabs.find(t => t.id === id);
  if (t) t.label = label;
}

function getOutput(id) {
  return document.getElementById('output-' + id);
}

function clearTab(id) {
  const out = getOutput(id);
  if (out) out.innerHTML = '';
  const t = tabs.find(t => t.id === id);
  if (t) { t.rawLines = []; t.runStart = null; }
  if (id === activeTabId) mountShellPrompt(id);
  setTabStatus(id, 'idle');
  if (id === activeTabId) { setStatus('idle'); clearSearch(); }
}

function _getExportableRawLines(tab) {
  if (!tab || !Array.isArray(tab.rawLines)) return [];
  return tab.rawLines.filter(line => {
    if (!line || typeof line.text !== 'string') return false;
    const cls = String(line.cls || '');
    if (cls === 'wlc-live' || cls.startsWith('welcome-')) return false;
    const plain = line.text.replace(/\x1b\[[0-9;]*[A-Za-z]/g, '').trim();
    return plain.length > 0;
  });
}

// ── Copy to clipboard ──
function copyTab(id) {
  const t = tabs.find(t => t.id === id);
  const lines = _getExportableRawLines(t);
  if (!lines.length) {
    showToast('No output to copy yet');
    return;
  }
  const text = lines.map(l => l.text.replace(/\x1b\[[0-9;]*[A-Za-z]/g, '')).join('\n');
  navigator.clipboard.writeText(text)
    .then(() => showToast('Copied to clipboard'))
    .catch(() => showToast('Failed to copy'));
}

// ── Plain text save ──
// Reads from rawLines rather than DOM innerText so that CSS ::before timestamp
// content and ANSI escape codes don't appear in the saved file.
function saveTab(id) {
  const t = tabs.find(t => t.id === id);
  const lines = _getExportableRawLines(t);
  if (!lines.length) {
    showToast('No output to export');
    return;
  }
  // Strip ANSI escape codes for plain text export
  const text = lines.map(l => l.text.replace(/\x1b\[[0-9;]*[A-Za-z]/g, '')).join('\n');
  const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  const blob = new Blob([text], { type: 'text/plain' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `${APP_CONFIG.app_name || 'shell'}-${ts}.txt`;
  a.click();
  URL.revokeObjectURL(a.href);
}

// ── HTML snapshot export ──
// Generates a self-contained HTML file with terminal styling, ANSI colors
// rendered as inline spans, and clock timestamps shown alongside each line.
function exportTabHtml(id) {
  const t = tabs.find(t => t.id === id);
  if (!t || !t.rawLines.length) { showToast('No output to export'); return; }

  const appName = APP_CONFIG.app_name || 'shell.darklab.sh';
  const exportedAt = new Date().toLocaleString();

  const linesHtml = t.rawLines.map(({ text, cls, tsC }) => {
    const tsSpan = tsC ? `<span class="ts">${escapeHtml(tsC)}</span>` : '';
    let content;
    if (cls === 'exit-ok' || cls === 'exit-fail' || cls === 'denied' || cls === 'notice') {
      content = escapeHtml(text);
    } else {
      content = ansi_up.ansi_to_html(text);
    }
    return `<span class="line${cls ? ' ' + cls : ''}">${tsSpan}${content}</span>`;
  }).join('\n');

  const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>${escapeHtml(t.label)} \u2014 ${escapeHtml(appName)}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
  body {
    background: #0d0d0d; color: #e0e0e0;
    font-family: 'JetBrains Mono', monospace; font-size: 13px;
    padding: 28px 32px; margin: 0; line-height: 1.65;
  }
  .header {
    margin-bottom: 20px; padding-bottom: 14px;
    border-bottom: 1px solid #1f1f1f;
  }
  .app-name { color: #39ff14; font-size: 18px; letter-spacing: 3px; margin-bottom: 6px; }
  .meta { color: #606060; font-size: 11px; }
  .output { white-space: pre-wrap; word-break: break-all; }
  .line { display: block; }
  .line.exit-ok   { color: #39ff14; font-weight: 700; margin-top: 8px; }
  .line.exit-fail { color: #ff3c3c; font-weight: 700; margin-top: 8px; }
  .line.denied    { color: #ffb800; font-weight: 700; }
  .line.notice    { color: #6ab0f5; font-style: italic; }
  .ts {
    display: inline-block; min-width: 58px; text-align: right;
    color: #505050; font-size: 10px; user-select: none;
    padding-right: 8px; margin-right: 6px;
    border-right: 1px solid #1f1f1f;
    font-variant-numeric: tabular-nums;
  }
</style>
</head>
<body>
<div class="header">
  <div class="app-name">${escapeHtml(appName)}</div>
  <div class="meta">${escapeHtml(t.label)} &nbsp;·&nbsp; exported ${escapeHtml(exportedAt)}</div>
</div>
<div class="output">
${linesHtml}
</div>
</body>
</html>`;

  const blob = new Blob([html], { type: 'text/html' });
  const a = document.createElement('a');
  const fileTs = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  a.href = URL.createObjectURL(blob);
  a.download = `${appName}-${fileTs}.html`;
  a.click();
  URL.revokeObjectURL(a.href);
}

// ── Tab rename ──
function startTabRename(id, labelEl) {
  const t = tabs.find(t => t.id === id);
  if (!t) return;
  const original = t.label;

  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'tab-rename-input';
  input.value = original;
  labelEl.textContent = '';
  labelEl.appendChild(input);
  input.focus();
  input.select();

  let done = false;
  function commit() {
    if (done) return;
    done = true;
    const next = input.value.trim() || original;
    if (labelEl.contains(input)) labelEl.removeChild(input);
    setTabLabel(id, next);
    if (t) t.renamed = true;
    updateTabScrollButtons();
    ensureActiveTabVisible(id);
  }
  function cancel() {
    if (done) return;
    done = true;
    if (labelEl.contains(input)) labelEl.removeChild(input);
    setTabLabel(id, original);
    updateTabScrollButtons();
    ensureActiveTabVisible(id);
  }

  input.addEventListener('keydown', e => {
    if (e.key === 'Enter')  { e.preventDefault(); e.stopPropagation(); commit(); }
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); cancel(); }
    e.stopPropagation(); // prevent Enter from firing run button
  });
  input.addEventListener('blur', commit);
  input.addEventListener('click', e => e.stopPropagation());
  input.addEventListener('input', () => {
    // Renaming can change tab width before commit, which affects scroll affordances.
    updateTabScrollButtons();
    ensureActiveTabVisible(id);
  });
}

function permalinkTab(id) {
  const t = tabs.find(t => t.id === id);
  if (!t || !t.rawLines.length) {
    showToast('No output to share yet');
    return;
  }
  apiFetch('/share', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ label: t.label, content: t.rawLines })
  }).then(r => r.json()).then(data => {
    const url = `${location.origin}${data.url}`;
    navigator.clipboard.writeText(url)
      .then(() => showToast('Link copied to clipboard'))
      .catch(() => showToast('Failed to copy link'));
  }).catch(() => showToast('Failed to create permalink'));
}
