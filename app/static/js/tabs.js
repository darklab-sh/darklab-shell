// ── Desktop UI module ──
let _tabsScrollControlsBound = false;
let _tabSeq = 0;
const _RUNNING_LABEL_DELAY_MS = 500;
const _OUTPUT_USER_SCROLL_GRACE_MS = 800;

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

function _nextDefaultTabNumber() {
  const numbers = (Array.isArray(tabs) ? tabs : [])
    .map(tab => String(tab && tab.label || '').trim().match(/^shell\s+(\d+)$/i))
    .filter(Boolean)
    .map(match => Number(match[1]))
    .filter(Number.isFinite);
  return numbers.length ? Math.max(...numbers) + 1 : 1;
}

function createDefaultTabLabel(index = null) {
  const explicitIndex = index !== null && index !== undefined && index !== '';
  const next = explicitIndex && Number.isFinite(Number(index)) ? Number(index) : _nextDefaultTabNumber();
  return `shell ${Math.max(1, next)}`;
}

function _truncateTabLabel(label) {
  const text = String(label || '');
  return text.length > 28 ? text.slice(0, 26) + '…' : text;
}

function _tabDisplayLabel(tab) {
  if (!tab) return '';
  if (tab.st === 'running' && tab.runningLabel) return tab.runningLabel;
  return tab.label || '';
}

function _renderTabLabel(id) {
  const tab = getTab(id);
  const lbl = _getTabLabelEl(id);
  if (lbl && tab) lbl.textContent = _truncateTabLabel(_tabDisplayLabel(tab));
}

function _clearTabRunningLabelTimer(tab) {
  if (!tab || !tab.runningLabelTimer) return;
  clearTimeout(tab.runningLabelTimer);
  tab.runningLabelTimer = null;
}

function _getTabOutputEl(id) {
  return _getTabPanelEl(id)?.querySelector('.output') || null;
}

function _markOutputUserScrollIntent(id) {
  const tab = getTab(id);
  if (!tab) return;
  tab.outputUserScrollUntil = Date.now() + _OUTPUT_USER_SCROLL_GRACE_MS;
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

function updateTabScrollButtons() {
  const leftBtn = tabsScrollLeftBtn;
  const rightBtn = tabsScrollRightBtn;
  if (!leftBtn || !rightBtn || !tabsBar) return;
  const maxScroll = Math.max(0, tabsBar.scrollWidth - tabsBar.clientWidth);
  if (maxScroll <= 1) {
    leftBtn.classList.add('u-hidden');
    rightBtn.classList.add('u-hidden');
    leftBtn.setAttribute('aria-hidden', 'true');
    rightBtn.setAttribute('aria-hidden', 'true');
    leftBtn.disabled = true;
    rightBtn.disabled = true;
    return;
  }
  leftBtn.classList.remove('u-hidden');
  rightBtn.classList.remove('u-hidden');
  leftBtn.setAttribute('aria-hidden', 'false');
  rightBtn.setAttribute('aria-hidden', 'false');
  leftBtn.disabled = tabsBar.scrollLeft <= 1;
  rightBtn.disabled = tabsBar.scrollLeft >= (maxScroll - 1);
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
  refocusComposerAfterAction({ defer: true });
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
  if (typeof emitUiEvent === 'function') {
    emitUiEvent('app:tab-order-changed', {
      order: orderedIds.slice(),
      activeTabId,
    });
  }
}

function unmountShellPrompt() {
  if (typeof shellPromptWrap === 'undefined' || !shellPromptWrap) return;
  const prevParent = shellPromptWrap.parentElement;
  shellPromptWrap.classList.add('u-hidden');
  if (shellPromptWrap.parentElement) shellPromptWrap.remove();
  if (prevParent && prevParent.classList && prevParent.classList.contains('output') && typeof syncOutputPrefixes === 'function') {
    syncOutputPrefixes(prevParent);
  }
}

function mountShellPrompt(tabId, force = false) {
  // Only the active tab owns the live prompt node. Moving that one node keeps
  // prompt state continuous when switching tabs instead of cloning inputs.
  if (typeof shellPromptWrap === 'undefined' || !shellPromptWrap) return;
  const mobileMode = !!(document.body && document.body.classList.contains('mobile-terminal-mode'));
  if (!force && typeof _tabSessionRestoreInProgress !== 'undefined' && _tabSessionRestoreInProgress) {
    unmountShellPrompt();
    return;
  }
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
  shellPromptWrap.classList.remove('u-hidden');
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

function _createTabHeader(id, label) {
  const tab = document.createElement('div');
  tab.className = 'tab';
  tab.dataset.id = id;

  // Mobile tab chrome shows a drag-grip glyph on the left; desktop hides it
  // via CSS. Rendered unconditionally so a viewport switch doesn't require
  // re-minting tab nodes.
  const grip = document.createElement('span');
  grip.className = 'tab-grip';
  grip.setAttribute('aria-hidden', 'true');
  tab.appendChild(grip);

  const status = document.createElement('span');
  status.className = 'tab-status idle';
  tab.appendChild(status);

  const labelEl = document.createElement('span');
  labelEl.className = 'tab-label';
  labelEl.textContent = label;
  tab.appendChild(labelEl);

  const closeBtn = document.createElement('button');
  closeBtn.className = 'tab-close';
  closeBtn.type = 'button';
  closeBtn.setAttribute('aria-label', 'Close tab');
  closeBtn.title = 'Close tab (Option+W / Alt+W when active)';
  closeBtn.textContent = '✕';
  tab.appendChild(closeBtn);

  return { tab, labelEl };
}

function _createTabActionButton(id, action, label, { hidden = false, danger = false } = {}) {
  const btn = document.createElement('button');
  btn.type = 'button';
  const base = danger ? 'btn btn-destructive btn-compact' : 'btn btn-secondary btn-compact';
  btn.className = base + (action === 'kill' ? ' tab-kill-btn' : '');
  btn.dataset.action = action;
  btn.dataset.tab = id;
  if (hidden) btn.hidden = true;
  btn.textContent = label;
  return btn;
}

function _getOutputFollowButton(id) {
  return _getTabPanelEl(id)?.querySelector('.output-follow-btn') || null;
}

function _isOutputAtTail(out) {
  if (!out) return true;
  const scrollTop = Number(out.scrollTop || 0);
  const clientHeight = Number(out.clientHeight || 0);
  const scrollHeight = Number(out.scrollHeight || 0);
  if (!Number.isFinite(scrollTop) || !Number.isFinite(clientHeight) || !Number.isFinite(scrollHeight)) return true;
  if (scrollHeight <= clientHeight + 2) return true;
  return Math.max(0, scrollHeight - (scrollTop + clientHeight)) <= 16;
}

function updateOutputFollowButton(id) {
  const tab = getTab(id);
  const out = getOutput(id);
  const btn = _getOutputFollowButton(id);
  if (!tab || !btn || !out) return;

  const hasOutput = Array.isArray(tab.rawLines) && tab.rawLines.length > 0;
  const atTail = _isOutputAtTail(out);
  if (atTail && tab.followOutput === false) tab.followOutput = true;
  const show = hasOutput && !atTail && tab.followOutput === false;
  const isLive = show && tab.st === 'running';
  const label = isLive ? 'jump to live' : 'jump to bottom';

  btn.hidden = !show;
  btn.textContent = label;
  btn.title = isLive ? 'Jump to the live output tail' : 'Jump to the bottom of the output';
  btn.setAttribute('aria-label', label);
  btn.classList.toggle('is-live', isLive);
  btn.classList.toggle('is-bottom', show && !isLive);
}

function _createTabPanel(id) {
  // Each tab panel contains both transcript output and its own action row so a
  // tab can be restored/shared without depending on global footer controls.
  const panel = document.createElement('div');
  panel.className = 'tab-panel';
  panel.dataset.id = id;

  const terminalBody = document.createElement('div');
  terminalBody.className = 'terminal-body';

  const output = document.createElement('div');
  output.className = 'output nice-scroll';
  output.id = `output-${id}`;
  terminalBody.appendChild(output);

  const followBtn = document.createElement('button');
  followBtn.type = 'button';
  followBtn.className = 'btn btn-ghost btn-compact output-follow-btn';
  followBtn.hidden = true;
  followBtn.textContent = 'jump to live';
  followBtn.title = 'Jump to the live output tail';
  followBtn.setAttribute('aria-label', 'Jump to the live output tail');
  followBtn.addEventListener('click', () => {
    const tab = getTab(id);
    const out = getOutput(id);
    if (!tab || !out) return;
    tab.followOutput = true;
    if (typeof _stickOutputToBottom === 'function') {
      _stickOutputToBottom(out, tab);
    } else {
      out.scrollTop = out.scrollHeight;
    }
    updateOutputFollowButton(id);
  });
  terminalBody.appendChild(followBtn);

  const terminalActions = document.createElement('div');
  terminalActions.className = 'terminal-actions';
  terminalActions.appendChild(_createTabActionButton(id, 'kill', '■ Kill', { hidden: true, danger: true }));
  terminalActions.appendChild(_createTabActionButton(id, 'permalink', 'share snapshot'));
  terminalActions.appendChild(_createTabActionButton(id, 'copy', 'copy'));
  const saveWrap = document.createElement('div');
  saveWrap.className = 'save-menu-wrap';
  const saveBtn = document.createElement('button');
  saveBtn.type = 'button';
  saveBtn.className = 'btn btn-secondary btn-compact';
  saveBtn.dataset.action = 'save-menu';
  saveBtn.dataset.tab = id;
  saveBtn.textContent = 'save';
  const saveMenu = document.createElement('div');
  saveMenu.className = 'save-menu dropdown-surface dropdown-up';
  [['save-txt', 'Plain text (.txt)'], ['save-html', 'Styled HTML (.html)'], ['save-pdf', 'PDF document (.pdf)']].forEach(([action, label]) => {
    const item = document.createElement('button');
    item.type = 'button';
    item.className = 'dropdown-item dropdown-item-compact';
    item.dataset.action = action;
    item.dataset.tab = id;
    item.textContent = label;
    saveMenu.appendChild(item);
  });
  saveWrap.appendChild(saveBtn);
  saveWrap.appendChild(saveMenu);
  terminalActions.appendChild(saveWrap);
  terminalActions.appendChild(_createTabActionButton(id, 'clear', 'clear'));
  terminalBody.appendChild(terminalActions);

  panel.appendChild(terminalBody);
  if (typeof bindOutsideClickClose === 'function') {
    bindOutsideClickClose(saveWrap, {
      triggers: saveBtn,
      isOpen: () => saveWrap.classList.contains('open'),
      onClose: () => saveWrap.classList.remove('open'),
    });
  }
  return { panel, output, terminalBody };
}

function createTab(label) {
  // Tabs are created fully client-side; history restore and shortcut flows all
  // funnel through this one constructor so the DOM/state shape stays uniform.
  if (APP_CONFIG.max_tabs > 0 && tabs.length >= APP_CONFIG.max_tabs) {
    showToast(`Tab limit reached (max ${APP_CONFIG.max_tabs})`);
    return null;
  }
  const id = 'tab-' + (++_tabSeq);
  const stableLabel = String(label || createDefaultTabLabel());

  const { tab, labelEl } = _createTabHeader(id, stableLabel);
  tab.addEventListener('click', e => {
    if (Date.now() < _tabDragSuppressClickUntil) return;
    if (e.target.classList.contains('tab-close')) {
      closeTab(id);
      blurActiveElement();
      return;
    }
    activateTab(id);
  });

  tab.addEventListener('dblclick', e => {
    if (e.target && e.target.closest && e.target.closest('.tab-close')) return;
    e.stopPropagation();
    startTabRename(id, labelEl);
  });

  // Double-click tab label to rename
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

  const { panel, output: outputEl, terminalBody } = _createTabPanel(id);
  if (outputEl) {
    const markUserScrollIntent = () => _markOutputUserScrollIntent(id);
    outputEl.addEventListener('wheel', markUserScrollIntent, { passive: true });
    outputEl.addEventListener('touchmove', markUserScrollIntent, { passive: true });
    outputEl.addEventListener('pointermove', e => {
      if (e.pointerType === 'touch' || e.pointerType === 'pen') markUserScrollIntent();
    }, { passive: true });
    outputEl.addEventListener('scroll', () => {
      const t = getTab(id);
      if (!t || t.suppressOutputScrollTracking) return;
      const atTail = _isOutputAtTail(outputEl);
      const userScrolling = Date.now() <= Number(t.outputUserScrollUntil || 0);
      if (!userScrolling && t.st === 'running' && t.followOutput !== false) {
        if (atTail) t.followOutput = true;
        updateOutputFollowButton(id);
        return;
      }
      t.followOutput = atTail;
      updateOutputFollowButton(id);
    }, { passive: true });
  }
  terminalBody?.addEventListener('click', e => {
    if (id !== activeTabId) return;
    if (e.target.closest('.btn')) return;
    if (e.target.closest('.welcome-command-loadable')) return;
    // Don't steal focus while the user has text selected — they may be about to copy.
    if (typeof window !== 'undefined' && window.getSelection && window.getSelection().toString().length > 0) return;
    refocusComposerAfterAction();
  });
  panel.querySelectorAll('[data-action]').forEach(btn => {
    const action = btn.dataset.action;
    // save-menu is a disclosure trigger: keep the dropdown-open affordance by
    // suppressing the auto-refocus so the user's attention stays on the menu
    // they just opened.
    const isDisclosure = action === 'save-menu';
    bindPressable(btn, {
      refocusComposer: !isDisclosure,
      onActivate: () => {
        if (typeof useMobileTerminalViewportMode === 'function'
          && useMobileTerminalViewportMode()
          && typeof blurVisibleComposerInputIfMobile === 'function') {
          blurVisibleComposerInputIfMobile();
        }
        if (action === 'kill')      confirmKill(id);
        if (action === 'clear')     { cancelWelcome(id); clearTab(id, { preserveRunState: true }); }
        if (action === 'copy')      copyTab(id);
        if (action === 'permalink') permalinkTab(id);
        if (action === 'save-menu') {
          btn.closest('.save-menu-wrap').classList.toggle('open');
          return;
        }
        if (action === 'save-txt' || action === 'save-html' || action === 'save-pdf') {
          const wrap = btn.closest('.save-menu-wrap');
          if (wrap) wrap.classList.remove('open');
        }
        if (action === 'save-txt')  saveTab(id);
        if (action === 'save-html') exportTabHtml(id);
        if (action === 'save-pdf')  void exportTabPdf(id);
      },
    });
  });
  tabPanels.appendChild(panel);

  tabs.push({
    id,
    label: stableLabel,
    runningLabel: '',
    runningLabelTimer: null,
    command: '',
    runId: null,
    historyRunId: null,
    lastEventId: '',
    attachMode: '',
    reconnectedRun: false,
    runStart: null,
    currentRunStartIndex: null,
    exitCode: null,
    rawLines: [],
    previewTruncated: false,
    fullOutputAvailable: false,
    fullOutputLoaded: false,
    followOutput: true,
    outputUserScrollUntil: 0,
    suppressOutputScrollTracking: false,
    deferPromptMount: false,
    closing: false,
    killed: false,
    pendingKill: false,
    st: 'idle',
    renamed: false,
    workspaceCwd: '',
    draftInput: '',
    commandHistory: [],
    historyNavIndex: -1,
    historyNavDraft: '',
  });
  updateOutputFollowButton(id);
  activateTab(id);
  updateNewTabBtn();
  updateTabScrollButtons();
  if (typeof schedulePersistTabSessionState === 'function') schedulePersistTabSessionState();
  if (typeof emitUiEvent === 'function') {
    emitUiEvent('app:tab-created', { id, label: stableLabel, activeTabId });
  }
  return id;
}

function activateTab(id, { focusComposer = true } = {}) {
  // Activation swaps the live prompt, the status pill, output-follow helpers,
  // and the visible transcript. Keep it centralized here to avoid drift.
  // Exit hist-search mode cleanly before switching tabs
  if (typeof isHistSearchMode === 'function' && isHistSearchMode()) {
    if (typeof exitHistSearch === 'function') exitHistSearch(false);
  }
  // Flush the current composer value into the leaving tab's draftInput before switching.
  const prevId = activeTabId;
  if (!_tabSessionRestoreInProgress && prevId && prevId !== id) {
    const prevTab = getTab(prevId);
    if (prevTab && prevTab.st === 'running') {
      prevTab.draftInput = '';
    } else if (prevTab) {
      prevTab.draftInput = (typeof getComposerValue === 'function') ? getComposerValue() : (cmdInput ? cmdInput.value : '');
    }
  }
  setActiveTabId(id);
  tabsBar?.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.id === id));
  tabPanels?.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.dataset.id === id));
  mountShellPrompt(id);
  const t = getTab(id);
  setStatus(t ? (t.st || 'idle') : 'idle');
  if (t && t.followOutput !== false) {
    const out = getOutput(id);
    if (out && typeof _restoreOutputTailAfterLayout === 'function') {
      _restoreOutputTailAfterLayout(out, t);
    } else if (out && typeof _stickOutputToBottom === 'function') {
      _stickOutputToBottom(out, t);
    }
  }
  ensureActiveTabVisible(id);
  updateTabScrollButtons();
  clearSearch();
  // Hide the autocomplete dropdown and clear the filtered list so stale
  // suggestions from the previous tab's typing session don't persist.
  if (typeof acHide === 'function') acHide();
  if (typeof acFiltered !== 'undefined') acFiltered = [];
  let draft = (t && t.st !== 'running') ? (t.draftInput || '') : '';
  if (!prevId && !draft && typeof getComposerValue === 'function') {
    const liveDraft = getComposerValue();
    if (liveDraft && liveDraft.trim()) draft = liveDraft;
  }
  if (typeof setComposerValue === 'function') {
    setComposerValue(draft, draft.length, draft.length, { dispatch: false });
  }
  resetCmdHistoryNav();
  if (typeof syncActiveRunTimer === 'function') syncActiveRunTimer(id);
  if (focusComposer) refocusComposerAfterAction({ preventScroll: true });
  if (typeof syncRunButtonDisabled === 'function') syncRunButtonDisabled();
  if (typeof _applyComposerPromptMode === 'function') _applyComposerPromptMode();
  updateOutputFollowButton(id);
  if (typeof scheduleSearchDiscoverabilityRefresh === 'function') scheduleSearchDiscoverabilityRefresh();
  else if (typeof refreshSearchDiscoverabilityUi === 'function') refreshSearchDiscoverabilityUi();
  if (typeof schedulePersistTabSessionState === 'function') schedulePersistTabSessionState();
  if (typeof emitUiEvent === 'function') {
    emitUiEvent('app:tab-activated', { id, prevId, activeTabId });
  }
}

function setTabStatus(id, st) {
  const dot = _getTabStatusEl(id);
  if (dot) dot.className = `tab-status ${st}`;
  const t = getTab(id);
  if (t) {
    t.st = st;
    if (st !== 'running') {
      _clearTabRunningLabelTimer(t);
      t.runningLabel = '';
    }
  }
  _renderTabLabel(id);
  if (id === activeTabId) {
    if (typeof _tabSessionRestoreInProgress !== 'undefined' && _tabSessionRestoreInProgress) {
      unmountShellPrompt();
    } else if (st === 'running') {
      unmountShellPrompt();
    } else {
      mountShellPrompt(id);
    }
    if (typeof syncRunButtonDisabled === 'function') syncRunButtonDisabled();
    if (typeof refreshSearchDiscoverabilityUi === 'function') refreshSearchDiscoverabilityUi();
  }
  updateOutputFollowButton(id);
  if (typeof schedulePersistTabSessionState === 'function') schedulePersistTabSessionState();
  if (typeof emitUiEvent === 'function') {
    emitUiEvent('app:tab-status-changed', { id, status: st, activeTabId });
  }
}

function setTabLabel(id, label) {
  const t = getTab(id);
  if (t) {
    t.label = String(label || '');
    _renderTabLabel(id);
  }
  if (id === activeTabId) ensureActiveTabVisible(id);
  if (typeof schedulePersistTabSessionState === 'function') schedulePersistTabSessionState();
}

function setTabRunningCommand(id, command) {
  const t = getTab(id);
  if (!t) return;
  const next = String(command || '').trim();
  if (!next) return;
  _clearTabRunningLabelTimer(t);
  t.command = next;
  t.runningLabel = '';
  t.runningLabelTimer = setTimeout(() => {
    t.runningLabelTimer = null;
    if (t.st !== 'running' || t.command !== next) return;
    t.runningLabel = next;
    _renderTabLabel(id);
    if (id === activeTabId) ensureActiveTabVisible(id);
  }, _RUNNING_LABEL_DELAY_MS);
  _renderTabLabel(id);
  if (id === activeTabId) ensureActiveTabVisible(id);
  if (typeof schedulePersistTabSessionState === 'function') schedulePersistTabSessionState();
}

function getOutput(id) {
  return _getTabOutputEl(id);
}

function clearTab(id, { preserveRunState = false } = {}) {
  if (typeof _cancelPendingOutputBatch === 'function') _cancelPendingOutputBatch(id);
  if (typeof resetAnsiRendererForTab === 'function') resetAnsiRendererForTab(id);
  const out = getOutput(id);
  if (out) {
    out.innerHTML = '';
    out.dataset.outputLineCounter = '0';
  }
  const t = getTab(id);
  const wasRunning = !!(t && t.st === 'running');
  if (t) {
    t._outputFollowToken = (t._outputFollowToken || 0) + 1;
    t._outputLineCounter = 0;
    t.suppressOutputScrollTracking = false;
    t.deferPromptMount = false;
    t.rawLines = [];
    if (typeof _resetTabOutputSignalCounts === 'function') _resetTabOutputSignalCounts(t);
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
      t.reconnectedRun = false;
      _clearTabRunningLabelTimer(t);
      t.runningLabel = '';
    }
  }
  if (id === activeTabId && (!preserveRunState || !wasRunning)) {
    mountShellPrompt(id);
  }
  if (id === activeTabId
    && (!preserveRunState || !wasRunning)
    && typeof setComposerValue === 'function'
    && !(typeof document !== 'undefined'
      && document.body
      && document.body.classList
      && document.body.classList.contains('mobile-terminal-mode'))) {
    setComposerValue('', 0, 0);
  }
  if (!preserveRunState || !wasRunning) {
    setTabStatus(id, 'idle');
    if (id === activeTabId) { setStatus('idle'); clearSearch(); }
  }
  updateOutputFollowButton(id);
  if (id === activeTabId && typeof refreshSearchDiscoverabilityUi === 'function') {
    refreshSearchDiscoverabilityUi();
  }
  if (typeof document !== 'undefined'
    && document.body
    && document.body.classList
    && document.body.classList.contains('mobile-terminal-mode')
    && typeof blurVisibleComposerInputIfMobile === 'function') {
    setTimeout(() => blurVisibleComposerInputIfMobile(), 0);
  }
  if (typeof schedulePersistTabSessionState === 'function') schedulePersistTabSessionState();
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
  focusElement(input);
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
