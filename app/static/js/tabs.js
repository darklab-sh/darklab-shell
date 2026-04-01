// ── Tab state ──
let tabs = [];
let activeTabId = null;

function createTab(label) {
  const id = 'tab-' + Date.now();

  const tab = document.createElement('div');
  tab.className = 'tab';
  tab.dataset.id = id;
  tab.innerHTML = `<span class="tab-status idle"></span><span class="tab-label">${escapeHtml(label)}</span><span class="tab-close">✕</span>`;
  tab.addEventListener('click', e => {
    if (e.target.classList.contains('tab-close')) { closeTab(id); return; }
    activateTab(id);
  });
  tabsBar.appendChild(tab);

  const panel = document.createElement('div');
  panel.className = 'tab-panel';
  panel.dataset.id = id;
  panel.innerHTML = `
    <div class="terminal-body">
      <div class="output" id="output-${id}"></div>
      <div class="terminal-actions">
        <button class="term-action-btn tab-kill-btn" data-action="kill" data-tab="${id}" style="display:none;color:var(--red);border-color:var(--red)">■ Kill</button>
        <button class="term-action-btn" data-action="permalink" data-tab="${id}">permalink</button>
        <button class="term-action-btn" data-action="save"      data-tab="${id}">save</button>
        <button class="term-action-btn" data-action="clear"     data-tab="${id}">clear</button>
      </div>
    </div>`;
  panel.querySelectorAll('[data-action]').forEach(btn => {
    btn.addEventListener('click', () => {
      const action = btn.dataset.action;
      if (action === 'kill')      confirmKill(id);
      if (action === 'clear')     clearTab(id);
      if (action === 'save')      saveTab(id);
      if (action === 'permalink') permalinkTab(id);
    });
  });
  tabPanels.appendChild(panel);

  tabs.push({ id, label, runId: null, exitCode: null, rawLines: [], killed: false });
  activateTab(id);
  return id;
}

function activateTab(id) {
  activeTabId = id;
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.id === id));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.dataset.id === id));
  clearSearch();
}

function closeTab(id) {
  if (tabs.length === 1) return; // keep at least one tab
  const idx = tabs.findIndex(t => t.id === id);
  tabs.splice(idx, 1);
  document.querySelector(`.tab[data-id="${id}"]`).remove();
  document.querySelector(`.tab-panel[data-id="${id}"]`).remove();
  if (activeTabId === id) {
    activateTab(tabs[Math.min(idx, tabs.length - 1)].id);
  }
}

function setTabStatus(id, st) {
  const dot = document.querySelector(`.tab[data-id="${id}"] .tab-status`);
  if (dot) dot.className = `tab-status ${st}`;
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
  if (t) t.rawLines = [];
  setTabStatus(id, 'idle');
  if (id === activeTabId) { setStatus('idle'); clearSearch(); }
}

function saveTab(id) {
  const out = getOutput(id);
  if (!out || !out.querySelectorAll('.line').length) return;
  const text = Array.from(out.querySelectorAll('.line')).map(l => l.innerText).join('\n');
  const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  const blob = new Blob([text], { type: 'text/plain' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `shell.darklab.sh-${ts}.txt`;
  a.click();
  URL.revokeObjectURL(a.href);
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
    navigator.clipboard.writeText(url).then(() => showToast('Link copied to clipboard'));
  }).catch(() => showToast('Failed to create permalink'));
}
