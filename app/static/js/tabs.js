// ── Desktop UI module ──
let _tabsScrollControlsBound = false;
let _draggedTabId = null;
let _dragMoved = false;
let _tabDragSuppressClickUntil = 0;
let _touchDragState = null;

function _getTabEl(id) {
  return tabsBar ? tabsBar.querySelector(`.tab[data-id="${id}"]`) : null;
}

function _getTabPanelEl(id) {
  return tabPanels ? tabPanels.querySelector(`.tab-panel[data-id="${id}"]`) : null;
}

function _getTabStatusEl(id) {
  return _getTabEl(id)?.querySelector('.tab-status') || null;
}

function _getTabLabelEl(id) {
  return _getTabEl(id)?.querySelector('.tab-label') || null;
}

function _getTabOutputEl(id) {
  return _getTabPanelEl(id)?.querySelector('.output') || null;
}

function _blurActiveElement() {
  const activeEl = typeof document !== 'undefined' ? document.activeElement : null;
  if (activeEl && typeof activeEl.blur === 'function') activeEl.blur();
}

function _clearTabDropIndicators() {
  if (!tabsBar) return;
  tabsBar.querySelectorAll('.tab-drop-before, .tab-drop-after').forEach(node => {
    node.classList.remove('tab-drop-before', 'tab-drop-after');
  });
}

function _getNeighborTabIdAfterClose(idx, closingId) {
  if (!Array.isArray(tabs) || !tabs.length) return null;
  const next = tabs[idx + 1];
  if (next && next.id !== closingId) return next.id;
  const prev = tabs[idx - 1];
  if (prev && prev.id !== closingId) return prev.id;
  const fallback = tabs.find(tab => tab && tab.id !== closingId);
  return fallback ? fallback.id : null;
}

function refocusTabsTerminalInput() {
  if (typeof focusAnyComposerInput !== 'function') return;
  setTimeout(() => focusAnyComposerInput(), 0);
}

function updateTabScrollButtons() {
  const leftBtn = tabsScrollLeftBtn;
  const rightBtn = tabsScrollRightBtn;
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

function shouldScrollActiveTabIntoView() {
  return !(typeof document !== 'undefined'
    && document.body
    && document.body.classList
    && document.body.classList.contains('mobile-terminal-mode'));
}

function ensureActiveTabVisible(tabId) {
  const tabEl = _getTabEl(tabId);
  if (!tabEl || typeof tabEl.scrollIntoView !== 'function') return;
  tabEl.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' });
}

function scrollTabsBar(direction) {
  if (!tabsBar || typeof tabsBar.scrollBy !== 'function') return;
  tabsBar.scrollBy({ left: direction * 220, behavior: 'smooth' });
  setTimeout(updateTabScrollButtons, 180);
  refocusTabsTerminalInput();
}

function setupTabScrollControls() {
  if (_tabsScrollControlsBound) return;
  const leftBtn = tabsScrollLeftBtn;
  const rightBtn = tabsScrollRightBtn;
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
  setTabs(orderedIds.map(id => byId.get(id)).filter(Boolean));
}

function _tabFromClientX(clientX, excludeId = null) {
  if (!tabsBar) return null;
  const nodes = [...tabsBar.querySelectorAll('.tab')];
  return nodes.find(node => {
    if (!node || node.dataset.id === excludeId) return false;
    const rect = node.getBoundingClientRect();
    return clientX >= rect.left && clientX <= rect.right;
  }) || null;
}

function _reorderDraggedTab(dragged, target, clientX) {
  if (!dragged || !target || !tabsBar || dragged === target) return;
  const rect = target.getBoundingClientRect();
  const after = clientX > rect.left + (rect.width / 2);
  _clearTabDropIndicators();
  target.classList.add(after ? 'tab-drop-after' : 'tab-drop-before');
  if (after) {
    if (target.nextSibling !== dragged) tabsBar.insertBefore(dragged, target.nextSibling);
  } else if (target !== dragged.nextSibling) {
    tabsBar.insertBefore(dragged, target);
  }
}

function _touchDragAutoScroll(clientX) {
  if (!tabsBar || typeof tabsBar.scrollBy !== 'function') return;
  const rect = tabsBar.getBoundingClientRect();
  const edge = 36;
  if (clientX <= rect.left + edge) tabsBar.scrollBy({ left: -18, behavior: 'auto' });
  else if (clientX >= rect.right - edge) tabsBar.scrollBy({ left: 18, behavior: 'auto' });
}

function _cleanupTouchDrag() {
  if (!_touchDragState) return;
  document.removeEventListener('pointermove', _onTouchDragMove);
  document.removeEventListener('pointerup', _onTouchDragEnd);
  document.removeEventListener('pointercancel', _onTouchDragEnd);
  _clearTabDropIndicators();
  tabsBar?.classList.remove('tabs-bar-touch-sorting');
  _touchDragState.tab.classList.remove('tab-dragging', 'tab-touch-dragging');
  _touchDragState = null;
}

function _onTouchDragMove(e) {
  if (!_touchDragState || e.pointerId !== _touchDragState.pointerId) return;
  const dx = e.clientX - _touchDragState.startX;
  const dy = e.clientY - _touchDragState.startY;
  if (!_touchDragState.active) {
    if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return;
    _touchDragState.active = true;
    tabsBar?.classList.add('tabs-bar-touch-sorting');
    _touchDragState.tab.classList.add('tab-dragging', 'tab-touch-dragging');
  }
  e.preventDefault();
  const dragged = _touchDragState.tab;
  const target = _tabFromClientX(e.clientX, _touchDragState.id);
  if (target) {
    _reorderDraggedTab(dragged, target, e.clientX);
    _touchDragState.moved = true;
  } else {
    _clearTabDropIndicators();
  }
  _touchDragAutoScroll(e.clientX);
  updateTabScrollButtons();
}

function _onTouchDragEnd(e) {
  if (!_touchDragState || e.pointerId !== _touchDragState.pointerId) return;
  const state = _touchDragState;
  const moved = state.active && state.moved;
  _cleanupTouchDrag();
  if (!moved) return;
  syncTabOrderFromDom();
  updateTabScrollButtons();
  if (shouldScrollActiveTabIntoView()) ensureActiveTabVisible(activeTabId);
  _tabDragSuppressClickUntil = Date.now() + 220;
  if (state.id === activeTabId && typeof focusAnyComposerInput === 'function') focusAnyComposerInput();
}

function _startTouchTabDrag(tab, id, e) {
  if (!e || e.pointerType !== 'touch') return;
  if (e.target && e.target.closest && e.target.closest('.tab-close')) return;
  _cleanupTouchDrag();
  _touchDragState = {
    id,
    tab,
    pointerId: e.pointerId,
    startX: e.clientX,
    startY: e.clientY,
    active: false,
    moved: false,
  };
  document.addEventListener('pointermove', _onTouchDragMove, { passive: false });
  document.addEventListener('pointerup', _onTouchDragEnd);
  document.addEventListener('pointercancel', _onTouchDragEnd);
}

function bindTabDragReorder(tab, id) {
  if (!tab) return;
  tab.setAttribute('draggable', 'true');
  tab.addEventListener('pointerdown', e => _startTouchTabDrag(tab, id, e));

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
    if (shouldScrollActiveTabIntoView()) ensureActiveTabVisible(activeTabId);
  });

  tab.addEventListener('dragend', () => {
    tab.classList.remove('tab-dragging');
    if (_dragMoved) {
      syncTabOrderFromDom();
      updateTabScrollButtons();
      if (shouldScrollActiveTabIntoView()) ensureActiveTabVisible(activeTabId);
      _tabDragSuppressClickUntil = Date.now() + 160;
      if (id === activeTabId && typeof focusAnyComposerInput === 'function') focusAnyComposerInput();
    }
    _draggedTabId = null;
    _dragMoved = false;
  });
}

function unmountShellPrompt() {
  if (typeof shellPromptWrap === 'undefined' || !shellPromptWrap) return;
  const prevParent = shellPromptWrap.parentElement;
  if (shellPromptWrap.parentElement) shellPromptWrap.remove();
  if (prevParent && prevParent.classList && prevParent.classList.contains('output') && typeof syncOutputPrefixes === 'function') {
    syncOutputPrefixes(prevParent);
  }
}

function mountShellPrompt(tabId, force = false) {
  if (typeof shellPromptWrap === 'undefined' || !shellPromptWrap) return;
  const mobileMode = !!(document.body && document.body.classList.contains('mobile-terminal-mode'));
  if (!force && !mobileMode && _welcomeBootPending) {
    unmountShellPrompt();
    return;
  }
  if (mobileMode) {
    unmountShellPrompt();
    return;
  }
  const tabState = getTab(tabId);
  if (!force && tabState && tabState.deferPromptMount) {
    unmountShellPrompt();
    return;
  }
  // Keep the prompt hidden while the tab is running a command.
  if (tabState && tabState.st === 'running') {
    unmountShellPrompt();
    return;
  }
  if (!force && _welcomeActive && welcomeOwnsTab(tabId)) {
    unmountShellPrompt();
    return;
  }
  const panel = _getTabPanelEl(tabId);
  if (!panel) return;
  const out = panel.querySelector('.output');
  if (!out) return;
  const prevParent = shellPromptWrap.parentElement;
  if (prevParent !== out) {
    out.appendChild(shellPromptWrap);
  }
  out.scrollTop = out.scrollHeight;
  if (prevParent && prevParent.classList && prevParent.classList.contains('output') && typeof syncOutputPrefixes === 'function') {
    syncOutputPrefixes(prevParent);
  }
  if (typeof syncOutputPrefixes === 'function') syncOutputPrefixes(out);
}

function updateNewTabBtn() {
  const btn = newTabBtn;
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
  tab.innerHTML = `<span class="tab-status idle"></span><span class="tab-label">${escapeHtml(label)}</span><button class="tab-close" type="button" aria-label="Close tab">✕</button>`;
  tab.addEventListener('click', e => {
    if (Date.now() < _tabDragSuppressClickUntil) return;
    if (e.target.classList.contains('tab-close')) {
      closeTab(id);
      _blurActiveElement();
      return;
    }
    activateTab(id);
  });

  // Double-click tab label to rename
  const labelEl = tab.querySelector('.tab-label');
  labelEl.addEventListener('dblclick', e => {
    e.stopPropagation();
    startTabRename(id, labelEl);
  });
  bindTabDragReorder(tab, id);

  const newTabButton = newTabBtn;
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
  const outputEl = panel.querySelector('.output');
  if (outputEl) {
    outputEl.addEventListener('scroll', () => {
      const t = getTab(id);
      if (!t || t.suppressOutputScrollTracking) return;
      const nearBottom = outputEl.scrollTop + outputEl.clientHeight >= outputEl.scrollHeight - 8;
      t.followOutput = nearBottom;
    }, { passive: true });
  }
  panel.querySelector('.terminal-body')?.addEventListener('click', e => {
    if (id !== activeTabId) return;
    if (e.target.closest('.term-action-btn')) return;
    if (e.target.closest('.welcome-command-loadable')) return;
    if (typeof focusAnyComposerInput === 'function') focusAnyComposerInput();
  });
  panel.querySelectorAll('[data-action]').forEach(btn => {
    btn.addEventListener('click', () => {
      const action = btn.dataset.action;
      if (typeof useMobileTerminalViewportMode === 'function'
        && useMobileTerminalViewportMode()
        && typeof blurVisibleComposerInputIfMobile === 'function') {
        blurVisibleComposerInputIfMobile();
      }
      if (action === 'kill')      confirmKill(id);
      if (action === 'clear')     { cancelWelcome(id); clearTab(id, { preserveRunState: true }); }
      if (action === 'copy')      copyTab(id);
      if (action === 'save')      saveTab(id);
      if (action === 'html')      exportTabHtml(id);
      if (action === 'permalink') permalinkTab(id);
      if (typeof btn.blur === 'function') {
        setTimeout(() => {
          if (typeof btn.blur === 'function') btn.blur();
        }, 0);
      }
    });
  });
  tabPanels.appendChild(panel);

  tabs.push({
    id,
    label,
    command: '',
    runId: null,
    historyRunId: null,
    runStart: null,
    currentRunStartIndex: null,
    exitCode: null,
    rawLines: [],
    previewTruncated: false,
    fullOutputAvailable: false,
    fullOutputLoaded: false,
    followOutput: true,
    suppressOutputScrollTracking: false,
    deferPromptMount: false,
    closing: false,
    killed: false,
    pendingKill: false,
    st: 'idle',
    renamed: false,
  });
  activateTab(id);
  updateNewTabBtn();
  updateTabScrollButtons();
  return id;
}

function activateTab(id, { focusComposer = true } = {}) {
  setActiveTabId(id);
  tabsBar?.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.id === id));
  tabPanels?.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.dataset.id === id));
  mountShellPrompt(id);
  const t = getTab(id);
  setStatus(t ? (t.st || 'idle') : 'idle');
  if (shouldScrollActiveTabIntoView()) ensureActiveTabVisible(id);
  updateTabScrollButtons();
  clearSearch();
  if (typeof setComposerValue === 'function') {
    setComposerValue('', 0, 0);
  } else if (cmdInput) {
    cmdInput.value = '';
    cmdInput.dispatchEvent(new Event('input'));
  }
  resetCmdHistoryNav();
  if (focusComposer && typeof focusAnyComposerInput === 'function') focusAnyComposerInput({ preventScroll: true });
  if (typeof syncRunButtonDisabled === 'function') syncRunButtonDisabled();
}

function closeTab(id) {
  cancelWelcome(id);
  const idx = tabs.findIndex(t => t.id === id);
  if (typeof _cancelPendingOutputBatch === 'function') _cancelPendingOutputBatch(id);
  const closingTab = tabs[idx];
  if (closingTab) {
    closingTab._outputFollowToken = (closingTab._outputFollowToken || 0) + 1;
    closingTab.suppressOutputScrollTracking = false;
    closingTab.deferPromptMount = false;
  }
  if (closingTab && closingTab.st === 'running') {
    closingTab.closing = true;
    if (typeof doKill === 'function') doKill(id);
    if (activeTabId === id && tabs.length > 1) {
      const nextId = _getNeighborTabIdAfterClose(idx, id);
      if (nextId) activateTab(nextId, { focusComposer: false });
    }
    if (typeof syncRunButtonDisabled === 'function') syncRunButtonDisabled();
    updateNewTabBtn();
    updateTabScrollButtons();
    return;
  }
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
    if (typeof useMobileTerminalViewportMode === 'function'
      && useMobileTerminalViewportMode()
      && typeof blurVisibleComposerInputIfMobile === 'function') {
      setTimeout(() => blurVisibleComposerInputIfMobile(), 0);
    }
    _blurActiveElement();
    return;
  }
  tabs.splice(idx, 1);
  _getTabEl(id)?.remove();
  _getTabPanelEl(id)?.remove();
  if (activeTabId === id) {
    const nextId = _getNeighborTabIdAfterClose(Math.min(idx, tabs.length), id);
    if (nextId) activateTab(nextId, { focusComposer: false });
    if (typeof document !== 'undefined'
      && document.body
      && document.body.classList
      && document.body.classList.contains('mobile-terminal-mode')
      && typeof window !== 'undefined'
      && typeof window.scrollTo === 'function') {
      setTimeout(() => {
        try {
          window.scrollTo({ top: 0, behavior: 'auto' });
        } catch (_) {
          // jsdom does not implement scrollTo; browsers do.
        }
      }, 0);
    }
  }
  updateNewTabBtn();
  updateTabScrollButtons();
}

function setTabStatus(id, st) {
  const dot = _getTabStatusEl(id);
  if (dot) dot.className = `tab-status ${st}`;
  const t = getTab(id);
  if (t) t.st = st;
  if (id === activeTabId) {
    if (st === 'running') unmountShellPrompt();
    else mountShellPrompt(id);
    if (typeof syncRunButtonDisabled === 'function') syncRunButtonDisabled();
  }
}

function setTabLabel(id, label) {
  const lbl = _getTabLabelEl(id);
  if (lbl) lbl.textContent = label.length > 28 ? label.slice(0, 26) + '…' : label;
  const t = getTab(id);
  if (t) t.label = label;
}

function getOutput(id) {
  return _getTabOutputEl(id);
}

function clearTab(id, { preserveRunState = false } = {}) {
  if (typeof _cancelPendingOutputBatch === 'function') _cancelPendingOutputBatch(id);
  const out = getOutput(id);
  if (out) out.innerHTML = '';
  const t = getTab(id);
  const wasRunning = !!(t && t.st === 'running');
  if (t) {
    t._outputFollowToken = (t._outputFollowToken || 0) + 1;
    t.suppressOutputScrollTracking = false;
    t.deferPromptMount = false;
    t.rawLines = [];
    t.followOutput = true;
    t.suppressOutputScrollTracking = false;
    t.deferPromptMount = false;
    t.closing = false;
    if (!preserveRunState || !wasRunning) {
      t.runStart = null;
      t.currentRunStartIndex = null;
      t.previewTruncated = false;
      t.fullOutputAvailable = false;
      t.fullOutputLoaded = false;
      t.historyRunId = null;
    }
  }
  if (id === activeTabId && (!preserveRunState || !wasRunning)) {
    mountShellPrompt(id);
  }
  if (!preserveRunState || !wasRunning) {
    setTabStatus(id, 'idle');
    if (id === activeTabId) { setStatus('idle'); clearSearch(); }
  }
  if (typeof document !== 'undefined'
    && document.body
    && document.body.classList
    && document.body.classList.contains('mobile-terminal-mode')
    && typeof blurVisibleComposerInputIfMobile === 'function') {
    setTimeout(() => blurVisibleComposerInputIfMobile(), 0);
  }
}

function finalizeClosingTab(id) {
  const idx = tabs.findIndex(t => t.id === id);
  if (idx < 0) return false;
  const tab = tabs[idx];
  if (!tab || !tab.closing) return false;

  if (tabs.length === 1) {
    tab.closing = false;
    clearTab(id);
    setTabLabel(id, 'tab 1');
    if (typeof document !== 'undefined'
      && document.body
      && document.body.classList
      && document.body.classList.contains('mobile-terminal-mode')
      && typeof blurVisibleComposerInputIfMobile === 'function') {
      setTimeout(() => blurVisibleComposerInputIfMobile(), 0);
    }
    return true;
  }

  tabs.splice(idx, 1);
  _getTabEl(id)?.remove();
  _getTabPanelEl(id)?.remove();
  if (activeTabId === id && tabs.length) {
    const nextId = _getNeighborTabIdAfterClose(Math.min(idx, tabs.length), id);
    if (nextId) activateTab(nextId, { focusComposer: false });
  }
  updateNewTabBtn();
  updateTabScrollButtons();
  if (typeof syncRunButtonDisabled === 'function') syncRunButtonDisabled();
  return true;
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
  const t = getTab(id);
  const lines = _getExportableRawLines(t);
  if (!lines.length) {
    showToast('No output to copy yet');
    return;
  }
  const text = lines.map(l => l.text.replace(/\x1b\[[0-9;]*[A-Za-z]/g, '')).join('\n');
  copyTextToClipboard(text)
    .then(() => showToast('Copied to clipboard'))
    .catch(() => showToast('Failed to copy', 'error'));
}

// ── Plain text save ──
// Reads from rawLines rather than DOM innerText so that CSS ::before timestamp
// content and ANSI escape codes don't appear in the saved file.
function saveTab(id) {
  const t = getTab(id);
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
// Generates a themed HTML file with terminal styling, ANSI colors rendered
// as inline spans, and clock timestamps shown alongside each line.
function exportTabHtml(id) {
  const t = getTab(id);
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
  @font-face {
    font-family: 'JetBrains Mono';
    src: url('/vendor/fonts/JetBrainsMono-400.ttf') format('truetype');
    font-weight: 400;
    font-style: normal;
  }
  @font-face {
    font-family: 'JetBrains Mono';
    src: url('/vendor/fonts/JetBrainsMono-700.ttf') format('truetype');
    font-weight: 700;
    font-style: normal;
  }
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
  const t = getTab(id);
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
    if (shouldScrollActiveTabIntoView()) ensureActiveTabVisible(id);
  }
  function cancel() {
    if (done) return;
    done = true;
    if (labelEl.contains(input)) labelEl.removeChild(input);
    setTabLabel(id, original);
    updateTabScrollButtons();
    if (shouldScrollActiveTabIntoView()) ensureActiveTabVisible(id);
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
    if (shouldScrollActiveTabIntoView()) ensureActiveTabVisible(id);
  });
}

function _cloneShareLine(line) {
  if (typeof line === 'string') {
    return { text: line, cls: '', tsC: '', tsE: '' };
  }
  if (line && typeof line.text === 'string') {
    return {
      text: line.text,
      cls: String(line.cls || ''),
      tsC: String(line.tsC || ''),
      tsE: String(line.tsE || ''),
    };
  }
  return null;
}

function _shareLinesWithoutTruncationNotices(lines) {
  return (Array.isArray(lines) ? lines : [])
    .map(_cloneShareLine)
    .filter(line => line && !/^\[(?:preview|tab output) truncated/i.test(String(line.text || '')));
}

function _extractLatestFullRunShareContent(tab, fullRun) {
  const rawLines = Array.isArray(tab.rawLines) ? tab.rawLines : [];
  const runStartIndex = typeof tab.currentRunStartIndex === 'number' && tab.currentRunStartIndex >= 0
    ? tab.currentRunStartIndex
    : rawLines.length;
  const exitIndex = (() => {
    for (let i = rawLines.length - 1; i >= 0; i -= 1) {
      const cls = String(rawLines[i] && rawLines[i].cls || '');
      if (cls === 'exit-ok' || cls === 'exit-fail') return i;
    }
    return rawLines.length;
  })();
  const fullOutput = Array.isArray(fullRun && fullRun.output_entries)
    ? fullRun.output_entries
    : _shareLinesWithoutTruncationNotices(fullRun && fullRun.output);

  return [
    ..._shareLinesWithoutTruncationNotices(rawLines.slice(0, runStartIndex)),
    ..._shareLinesWithoutTruncationNotices(fullOutput),
    ..._shareLinesWithoutTruncationNotices(rawLines.slice(exitIndex)),
  ];
}

async function permalinkTab(id) {
  const t = getTab(id);
  if (!t || !t.rawLines.length) {
    showToast('No output to share yet');
    return;
  }
  let shareContent = _shareLinesWithoutTruncationNotices(t.rawLines);
  if (t.fullOutputAvailable && !t.fullOutputLoaded && t.historyRunId) {
    try {
      const res = await apiFetch(`/history/${t.historyRunId}?json`);
      const fullRun = await res.json();
      shareContent = _extractLatestFullRunShareContent(t, fullRun);
    } catch {
      shareContent = _shareLinesWithoutTruncationNotices(t.rawLines);
    }
  }
  apiFetch('/share', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ label: t.label, content: shareContent })
  }).then(r => r.json()).then(data => {
    const url = `${location.origin}${data.url}`;
    copyTextToClipboard(url)
      .then(() => showToast('Link copied to clipboard'))
      .catch(() => showToast('Failed to copy link', 'error'));
  }).catch(() => showToast('Failed to create permalink', 'error'))
    .finally(() => {
      if (typeof focusAnyComposerInput === 'function') focusAnyComposerInput();
    });
}
