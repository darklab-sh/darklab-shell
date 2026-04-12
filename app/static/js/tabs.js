// ── Desktop UI module ──
let _tabsScrollControlsBound = false;
let _draggedTabId = null;
let _dragMoved = false;
let _tabDragSuppressClickUntil = 0;
let _touchDragState = null;
let _tabSeq = 0;

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
  // Touch drag state spans document-level listeners, so cleanup has to fully
  // unwind everything even when the gesture is cancelled mid-drag.
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
  // Only the active tab owns the live prompt node. Moving that one node keeps
  // prompt state continuous when switching tabs instead of cloning inputs.
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

function _createTabHeader(id, label) {
  const tab = document.createElement('div');
  tab.className = 'tab';
  tab.dataset.id = id;

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
  closeBtn.textContent = '✕';
  tab.appendChild(closeBtn);

  return { tab, labelEl };
}

function _createTabActionButton(id, action, label, { hidden = false, danger = false } = {}) {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'term-action-btn' + (action === 'kill' ? ' tab-kill-btn' : '') + (danger ? ' tab-kill-btn-danger' : '');
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
  output.className = 'output';
  output.id = `output-${id}`;
  terminalBody.appendChild(output);

  const followBtn = document.createElement('button');
  followBtn.type = 'button';
  followBtn.className = 'output-follow-btn';
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
  const wordmark = document.createElement('a');
  wordmark.className = 'terminal-wordmark';
  wordmark.href = APP_CONFIG.project_readme || '#';
  wordmark.target = '_blank';
  wordmark.rel = 'noopener noreferrer';
  const wmVersion = APP_CONFIG.version ? ` v${APP_CONFIG.version}` : '';
  wordmark.textContent = `${APP_CONFIG.app_name || 'darklab shell'}${wmVersion}`;
  terminalActions.appendChild(wordmark);
  terminalActions.appendChild(_createTabActionButton(id, 'kill', '■ Kill', { hidden: true, danger: true }));
  terminalActions.appendChild(_createTabActionButton(id, 'permalink', 'permalink'));
  terminalActions.appendChild(_createTabActionButton(id, 'copy', 'copy'));
  terminalActions.appendChild(_createTabActionButton(id, 'save', 'save txt'));
  terminalActions.appendChild(_createTabActionButton(id, 'html', 'save html'));
  terminalActions.appendChild(_createTabActionButton(id, 'clear', 'clear'));
  terminalBody.appendChild(terminalActions);

  panel.appendChild(terminalBody);
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

  const { tab, labelEl } = _createTabHeader(id, label);
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
    outputEl.addEventListener('scroll', () => {
      const t = getTab(id);
      if (!t || t.suppressOutputScrollTracking) return;
      t.followOutput = _isOutputAtTail(outputEl);
      updateOutputFollowButton(id);
    }, { passive: true });
  }
  terminalBody?.addEventListener('click', e => {
    if (id !== activeTabId) return;
    if (e.target.closest('.term-action-btn')) return;
    if (e.target.closest('.welcome-command-loadable')) return;
    // Don't steal focus while the user has text selected — they may be about to copy.
    if (typeof window !== 'undefined' && window.getSelection && window.getSelection().toString().length > 0) return;
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
    draftInput: '',
  });
  updateOutputFollowButton(id);
  activateTab(id);
  updateNewTabBtn();
  updateTabScrollButtons();
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
  if (prevId && prevId !== id) {
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
  if (shouldScrollActiveTabIntoView()) ensureActiveTabVisible(id);
  updateTabScrollButtons();
  clearSearch();
  // Hide the autocomplete dropdown and clear the filtered list so stale
  // suggestions from the previous tab's typing session don't persist.
  if (typeof acHide === 'function') acHide();
  if (typeof acFiltered !== 'undefined') acFiltered = [];
  const draft = (t && t.st !== 'running') ? (t.draftInput || '') : '';
  if (typeof setComposerValue === 'function') {
    setComposerValue(draft, draft.length, draft.length, { dispatch: false });
  }
  resetCmdHistoryNav();
  if (focusComposer && typeof focusAnyComposerInput === 'function') focusAnyComposerInput({ preventScroll: true });
  if (typeof syncRunButtonDisabled === 'function') syncRunButtonDisabled();
  updateOutputFollowButton(id);
}

function closeTab(id) {
  // Closing a tab may need to preserve run state until the kill flow or output
  // persistence finishes, so final removal is sometimes deferred.
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
  updateOutputFollowButton(id);
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
    if (typeof refocusComposerAfterAction === 'function') refocusComposerAfterAction({ preventScroll: true });
    return;
  }
  const text = lines.map(l => l.text.replace(/\x1b\[[0-9;]*[A-Za-z]/g, '')).join('\n');
  copyTextToClipboard(text)
    .then(() => showToast('Copied to clipboard'))
    .catch(() => showToast('Failed to copy', 'error'))
    .finally(() => {
      if (typeof refocusComposerAfterAction === 'function') refocusComposerAfterAction({ preventScroll: true });
    });
}

// ── Plain text save ──
// Reads from rawLines rather than DOM innerText so that CSS ::before timestamp
// content and ANSI escape codes don't appear in the saved file.
function saveTab(id) {
  const t = getTab(id);
  const lines = _getExportableRawLines(t);
  if (!lines.length) {
    showToast('No output to export');
    if (typeof refocusComposerAfterAction === 'function') refocusComposerAfterAction({ preventScroll: true });
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
  if (typeof refocusComposerAfterAction === 'function') refocusComposerAfterAction({ preventScroll: true });
}

// ── HTML snapshot export ──
// Generates a themed HTML file with terminal styling, ANSI colors rendered
// as inline spans, and clock timestamps shown alongside each line.
async function exportTabHtml(id) {
  const t = getTab(id);
  if (!t || !t.rawLines.length) { showToast('No output to export'); if (typeof refocusComposerAfterAction === 'function') refocusComposerAfterAction({ preventScroll: true }); return; }
  if (!window.ExportHtmlUtils) {
    showToast('Failed to export html', 'error');
    if (typeof refocusComposerAfterAction === 'function') refocusComposerAfterAction({ preventScroll: true });
    return;
  }

  try {
    const appName = APP_CONFIG.app_name || 'darklab shell';
    const exportedAt = new Date().toLocaleString();

    const linesHtml = t.rawLines.map(({ text, cls, tsC }) => {
      const tsSpan = tsC ? `<span class="ts">${ExportHtmlUtils.escapeExportHtml(tsC)}</span>` : '';
      let content;
      if (cls === 'prompt-echo') {
        content = ExportHtmlUtils.renderExportPromptEcho(text);
      } else if (cls === 'exit-ok' || cls === 'exit-fail' || cls === 'denied' || cls === 'notice') {
        content = ExportHtmlUtils.escapeExportHtml(text);
      } else {
        content = ansi_up.ansi_to_html(text);
      }
      return `<span class="line${cls ? ' ' + cls : ''}">${tsSpan}${content}</span>`;
    }).join('\n');

    const fontFacesCss = await ExportHtmlUtils.fetchVendorFontFacesCss().catch(() => '');
    const html = ExportHtmlUtils.buildTerminalExportHtml({
      appName,
      title: t.label,
      metaHtml: `exported ${ExportHtmlUtils.escapeExportHtml(exportedAt)}`,
      linesHtml,
      fontFacesCss,
    });

    const blob = new Blob([html], { type: 'text/html' });
    const a = document.createElement('a');
    const fileTs = ExportHtmlUtils.exportTimestamp();
    a.href = URL.createObjectURL(blob);
    a.download = `${appName}-${fileTs}.html`;
    a.click();
    URL.revokeObjectURL(a.href);
  } catch {
    showToast('Failed to export html', 'error');
  } finally {
    if (typeof refocusComposerAfterAction === 'function') refocusComposerAfterAction({ preventScroll: true });
  }
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
