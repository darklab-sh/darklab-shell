// ── Desktop UI module ──
let _tabsScrollControlsBound = false;
let _tabDragSuppressClickUntil = 0;
let _touchDragState = null;
let _tabSeq = 0;
const _TOUCH_TAB_DRAG_THRESHOLD = 14;
const _TOUCH_TAB_DRAG_HOLD_MS = 180;
const _POINTER_TAB_DRAG_THRESHOLD = 6;
const _RUNNING_LABEL_DELAY_MS = 500;
const _OUTPUT_USER_SCROLL_GRACE_MS = 800;

function _syncTabDraggable(tab) {
  if (!tab) return;
  tab.setAttribute('draggable', 'false');
}

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

function _tabFromClientX(clientX, excludeId = null) {
  if (!tabsBar) return null;
  const nodes = [...tabsBar.querySelectorAll('.tab')];
  return nodes.find(node => {
    if (!node || node.dataset.id === excludeId) return false;
    const rect = node.getBoundingClientRect();
    return clientX >= rect.left && clientX <= rect.right;
  }) || null;
}

function _edgeTabFromClientX(clientX, excludeId = null) {
  if (!tabsBar) return null;
  const nodes = [...tabsBar.querySelectorAll('.tab')].filter(node => node && node.dataset.id !== excludeId);
  if (!nodes.length) return null;
  const first = nodes[0];
  const last = nodes[nodes.length - 1];
  const firstRect = first.getBoundingClientRect();
  const lastRect = last.getBoundingClientRect();
  if (clientX < firstRect.left) return { target: first, after: false };
  if (clientX > lastRect.right) return { target: last, after: true };
  return null;
}

function _reorderDraggedTab(dragged, target, clientX) {
  if (!dragged || !target || !tabsBar || dragged === target) return false;
  const rect = target.getBoundingClientRect();
  const after = clientX > rect.left + (rect.width / 2);
  const noChange = after
    ? target.nextSibling === dragged
    : target === dragged.nextSibling;
  if (noChange) {
    _clearTabDropIndicators();
    return false;
  }
  _clearTabDropIndicators();
  target.classList.add(after ? 'tab-drop-after' : 'tab-drop-before');
  if (after) {
    if (target.nextSibling !== dragged) tabsBar.insertBefore(dragged, target.nextSibling);
  } else if (target !== dragged.nextSibling) {
    tabsBar.insertBefore(dragged, target);
  }
  return true;
}

function _touchDragAutoScroll(clientX) {
  if (!tabsBar || typeof tabsBar.scrollBy !== 'function') return;
  const rect = tabsBar.getBoundingClientRect();
  const edge = 36;
  if (clientX <= rect.left + edge) tabsBar.scrollBy({ left: -18, behavior: 'auto' });
  else if (clientX >= rect.right - edge) tabsBar.scrollBy({ left: 18, behavior: 'auto' });
}

function _getTrackedTouchPoint(e, touchId = null) {
  const pools = [];
  if (e && e.touches) pools.push(e.touches);
  if (e && e.changedTouches) pools.push(e.changedTouches);
  for (const pool of pools) {
    for (const touch of pool) {
      if (touchId === null || touch.identifier === touchId) return touch;
    }
  }
  return null;
}

function _cleanupTouchDrag() {
  // Touch drag state spans document-level listeners, so cleanup has to fully
  // unwind everything even when the gesture is cancelled mid-drag.
  if (!_touchDragState) return;
  if (
    _touchDragState.tab
    && typeof _touchDragState.pointerId === 'number'
    && typeof _touchDragState.tab.releasePointerCapture === 'function'
  ) {
    try { _touchDragState.tab.releasePointerCapture(_touchDragState.pointerId); } catch (_) {}
  }
  document.removeEventListener('pointermove', _onTouchDragMove);
  document.removeEventListener('pointerup', _onTouchDragEnd);
  document.removeEventListener('pointercancel', _onTouchDragEnd);
  document.removeEventListener('touchmove', _onTouchDragMove);
  document.removeEventListener('touchend', _onTouchDragEnd);
  document.removeEventListener('touchcancel', _onTouchDragEnd);
  _clearTabDropIndicators();
  tabsBar?.classList.remove('tabs-bar-touch-sorting');
  tabsBar?.classList.remove('tabs-bar-desktop-sorting');
  _touchDragState.tab.classList.remove('tab-dragging', 'tab-touch-dragging', 'tab-pointer-dragging');
  if (_touchDragState.holdTimer) clearTimeout(_touchDragState.holdTimer);
  _touchDragState = null;
}

function _onTouchDragMove(e) {
  if (!_touchDragState) return;
  let clientX;
  let clientY;
  if (_touchDragState.source === 'touch') {
    const point = _getTrackedTouchPoint(e, _touchDragState.touchId);
    if (!point) return;
    clientX = point.clientX;
    clientY = point.clientY;
  } else {
    if (e.pointerId !== _touchDragState.pointerId) return;
    clientX = e.clientX;
    clientY = e.clientY;
  }
  const dx = clientX - _touchDragState.startX;
  const dy = clientY - _touchDragState.startY;
  if (!_touchDragState.active) {
    if (_touchDragState.source === 'touch') {
      if (Math.abs(dx) >= _TOUCH_TAB_DRAG_THRESHOLD || Math.abs(dy) >= _TOUCH_TAB_DRAG_THRESHOLD) {
        if (_touchDragState.holdTimer) {
          clearTimeout(_touchDragState.holdTimer);
          _touchDragState.holdTimer = null;
        }
        _cleanupTouchDrag();
      }
      return;
    }
    if (Math.abs(dx) < _POINTER_TAB_DRAG_THRESHOLD && Math.abs(dy) < _POINTER_TAB_DRAG_THRESHOLD) return;
    _touchDragState.active = true;
    if (typeof e.preventDefault === 'function') e.preventDefault();
    if (typeof e.stopPropagation === 'function') e.stopPropagation();
    tabsBar?.classList.add('tabs-bar-desktop-sorting');
    _touchDragState.tab.classList.add('tab-dragging', 'tab-pointer-dragging');
  }
  if (typeof e.preventDefault === 'function') e.preventDefault();
  if (typeof e.stopPropagation === 'function') e.stopPropagation();
  const dragged = _touchDragState.tab;
  const target = _tabFromClientX(clientX, _touchDragState.id);
  const edgeDrop = target ? null : _edgeTabFromClientX(clientX, _touchDragState.id);
  if (target) {
    const changed = _reorderDraggedTab(dragged, target, clientX);
    if (changed) _touchDragState.moved = true;
  } else if (edgeDrop && edgeDrop.target !== dragged) {
    const firstTab = tabsBar.querySelector('.tab');
    const lastTab = tabsBar.querySelector('.tab:last-of-type');
    const noChange = (!edgeDrop.after && firstTab === dragged) || (edgeDrop.after && lastTab === dragged);
    if (noChange) {
      _clearTabDropIndicators();
      updateTabScrollButtons();
      return;
    }
    _clearTabDropIndicators();
    edgeDrop.target.classList.add(edgeDrop.after ? 'tab-drop-after' : 'tab-drop-before');
    if (edgeDrop.after) {
      tabsBar.appendChild(dragged);
    } else {
      tabsBar.insertBefore(dragged, tabsBar.querySelector('.tab'));
    }
    _touchDragState.moved = true;
  } else {
    _clearTabDropIndicators();
  }
  _touchDragAutoScroll(clientX);
  updateTabScrollButtons();
}

function _onTouchDragEnd(e) {
  if (!_touchDragState) return;
  if (_touchDragState.source === 'touch') {
    if (!_getTrackedTouchPoint(e, _touchDragState.touchId) && e.type !== 'touchcancel') return;
  } else if (e.pointerId !== _touchDragState.pointerId) {
    return;
  }
  const state = _touchDragState;
  const moved = state.active && state.moved;
  _cleanupTouchDrag();
  _syncTabDraggable(state.tab);
  if (!moved) return;
  syncTabOrderFromDom();
  updateTabScrollButtons();
  ensureActiveTabVisible(activeTabId);
  _tabDragSuppressClickUntil = Date.now() + (state.source === 'touch' ? 220 : 140);
  if (state.id === activeTabId) refocusComposerAfterAction();
}

function _startTouchTabDrag(tab, id, e) {
  if (!e) return;
  const isTouchEvent = e.type === 'touchstart';
  if (!isTouchEvent && e.pointerType === 'touch') return;
  if (!isTouchEvent && e.pointerType !== 'mouse') return;
  if (!isTouchEvent && typeof e.button === 'number' && e.button !== 0) return;
  if (e.target && e.target.closest && e.target.closest('.tab-close')) return;
  _syncTabDraggable(tab);
  _cleanupTouchDrag();
  const point = isTouchEvent ? _getTrackedTouchPoint(e) : e;
  if (!point) return;
  const pointerId = !isTouchEvent && typeof e.pointerId === 'number' ? e.pointerId : null;
  if (pointerId !== null && typeof tab.setPointerCapture === 'function') {
    try { tab.setPointerCapture(e.pointerId); } catch (_) {}
  }
  _touchDragState = {
    id,
    tab,
    source: isTouchEvent ? 'touch' : 'pointer',
    pointerId,
    touchId: isTouchEvent && typeof point.identifier === 'number' ? point.identifier : null,
    startX: point.clientX,
    startY: point.clientY,
    active: false,
    moved: false,
    holdTimer: null,
  };
  if (isTouchEvent) {
    _touchDragState.holdTimer = setTimeout(() => {
      if (!_touchDragState || _touchDragState.id !== id || _touchDragState.tab !== tab) return;
      _touchDragState.holdTimer = null;
      _touchDragState.active = true;
      tabsBar?.classList.add('tabs-bar-touch-sorting');
      _touchDragState.tab.classList.add('tab-dragging', 'tab-touch-dragging');
    }, _TOUCH_TAB_DRAG_HOLD_MS);
  }
  if (isTouchEvent) {
    document.addEventListener('touchmove', _onTouchDragMove, { passive: false });
    document.addEventListener('touchend', _onTouchDragEnd);
    document.addEventListener('touchcancel', _onTouchDragEnd);
  } else {
    document.addEventListener('pointermove', _onTouchDragMove, { passive: false });
    document.addEventListener('pointerup', _onTouchDragEnd);
    document.addEventListener('pointercancel', _onTouchDragEnd);
  }
}

function bindTabDragReorder(tab, id) {
  if (!tab) return;
  _syncTabDraggable(tab);
  tab.addEventListener('pointerdown', e => _startTouchTabDrag(tab, id, e));
  tab.addEventListener('touchstart', e => _startTouchTabDrag(tab, id, e), { passive: false });
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
  updateOutputFollowButton(id);
  if (typeof scheduleSearchDiscoverabilityRefresh === 'function') scheduleSearchDiscoverabilityRefresh();
  else if (typeof refreshSearchDiscoverabilityUi === 'function') refreshSearchDiscoverabilityUi();
  if (typeof schedulePersistTabSessionState === 'function') schedulePersistTabSessionState();
  if (typeof emitUiEvent === 'function') {
    emitUiEvent('app:tab-activated', { id, prevId, activeTabId });
  }
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
    if (typeof schedulePersistTabSessionState === 'function') schedulePersistTabSessionState();
    if (typeof emitUiEvent === 'function') {
      emitUiEvent('app:tab-closing-deferred', { id, activeTabId });
    }
    return;
  }
  if (tabs.length === 1) {
    // Last tab: reset to blank instead of closing
    clearTab(id);
    setTabLabel(id, createDefaultTabLabel(1));
    const t = tabs[0];
    t.runId = null;
    t.runStart = null;
    t.exitCode = null;
    t.command = '';
    _clearTabRunningLabelTimer(t);
    t.runningLabel = '';
    t.renamed = false;
    t.killed = false;
    t.pendingKill = false;
    if (typeof useMobileTerminalViewportMode === 'function'
      && useMobileTerminalViewportMode()
      && typeof blurVisibleComposerInputIfMobile === 'function') {
      setTimeout(() => blurVisibleComposerInputIfMobile(), 0);
    }
    blurActiveElement();
    if (typeof schedulePersistTabSessionState === 'function') schedulePersistTabSessionState();
    if (typeof emitUiEvent === 'function') {
      emitUiEvent('app:tab-closed', { id, activeTabId, preservedSingleTab: true });
    }
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
  if (typeof schedulePersistTabSessionState === 'function') schedulePersistTabSessionState();
  if (typeof emitUiEvent === 'function') {
    emitUiEvent('app:tab-closed', { id, activeTabId });
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

function finalizeClosingTab(id) {
  const idx = tabs.findIndex(t => t.id === id);
  if (idx < 0) return false;
  const tab = tabs[idx];
  if (!tab || !tab.closing) return false;

  if (tabs.length === 1) {
    tab.closing = false;
    clearTab(id);
    setTabLabel(id, createDefaultTabLabel(1));
    tab.command = '';
    _clearTabRunningLabelTimer(tab);
    tab.runningLabel = '';
    tab.renamed = false;
    if (typeof document !== 'undefined'
      && document.body
      && document.body.classList
      && document.body.classList.contains('mobile-terminal-mode')
      && typeof blurVisibleComposerInputIfMobile === 'function') {
      setTimeout(() => blurVisibleComposerInputIfMobile(), 0);
    }
    if (typeof schedulePersistTabSessionState === 'function') schedulePersistTabSessionState();
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
  if (typeof schedulePersistTabSessionState === 'function') schedulePersistTabSessionState();
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

function _getShareRedactionRules() {
  return APP_CONFIG && Array.isArray(APP_CONFIG.share_redaction_rules)
    ? APP_CONFIG.share_redaction_rules
    : [];
}

function _shareRedactionEnabled() {
  return !(APP_CONFIG && APP_CONFIG.share_redaction_enabled === false);
}

function _getRedactedLines(lines) {
  return typeof redactLineEntries === 'function'
    ? redactLineEntries(lines, _getShareRedactionRules())
    : (Array.isArray(lines) ? lines : []);
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

// Returns the gutter prefix for a raw line, respecting the current tsMode/lnMode
// toggles so exports match what the user sees in the terminal.
function _exportPrefix(line, zeroBasedIndex) {
  const parts = [];
  if (typeof lnMode !== 'undefined' && lnMode === 'on') parts.push(String(zeroBasedIndex + 1));
  if (typeof tsMode !== 'undefined') {
    if (tsMode === 'clock' && line.tsC) parts.push(line.tsC);
    else if (tsMode === 'elapsed' && line.tsE) parts.push(line.tsE);
  }
  return parts.join(' ');
}

function _normalizeTabTranscriptLine(line) {
  if (window.ExportHtmlUtils && typeof ExportHtmlUtils.normalizeExportTranscriptLine === 'function') {
    return ExportHtmlUtils.normalizeExportTranscriptLine(line);
  }
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

function _normalizeTabTranscriptLines(lines, { stripTruncationNotices = false } = {}) {
  if (window.ExportHtmlUtils && typeof ExportHtmlUtils.normalizeExportTranscriptLines === 'function') {
    return ExportHtmlUtils.normalizeExportTranscriptLines(lines, { stripTruncationNotices: stripTruncationNotices });
  }
  return (Array.isArray(lines) ? lines : [])
    .map(_normalizeTabTranscriptLine)
    .filter(line => {
      if (!line) return false;
      if (!stripTruncationNotices) return true;
      return !/^\[(?:preview|tab output) truncated/i.test(String(line.text || ''));
    });
}

function _buildTabExportModel(tab, { createdText = null } = {}) {
  const normalizedCreatedText = String(createdText || new Date().toLocaleString());
  if (window.ExportHtmlUtils && typeof ExportHtmlUtils.buildExportDocumentModel === 'function') {
    return ExportHtmlUtils.buildExportDocumentModel({
      appName: APP_CONFIG.app_name || 'darklab_shell',
      title: String(tab && tab.label || ''),
      label: tab && tab.label,
      createdText: normalizedCreatedText,
      runMeta: {
        exitCode: tab ? tab.exitCode : null,
        duration: null,
        lines: `${_normalizeTabTranscriptLines(tab && tab.rawLines).length} lines`,
        version: APP_CONFIG.version || null,
      },
      rawLines: tab && tab.rawLines,
    });
  }
  const rawLines = _normalizeTabTranscriptLines(tab && tab.rawLines);
  const appName = APP_CONFIG.app_name || 'darklab_shell';
  return {
    appName,
    title: String(tab && tab.label || ''),
    metaLine: ExportHtmlUtils.buildExportMetaLine({
      label: tab && tab.label,
      createdText: normalizedCreatedText,
    }),
    runMeta: {
      exitCode: tab ? tab.exitCode : null,
      duration: null,
      lines: `${rawLines.length} lines`,
      version: APP_CONFIG.version || null,
    },
    rawLines,
  };
}

// ── HTML snapshot export ──
async function exportTabHtml(id) {
  const t = getTab(id);
  if (!t || !t.rawLines.length) { showToast('No output to export'); if (typeof refocusComposerAfterAction === 'function') refocusComposerAfterAction({ preventScroll: true }); return; }
  if (!window.ExportHtmlUtils) {
    showToast('Failed to export html', 'error');
    if (typeof refocusComposerAfterAction === 'function') refocusComposerAfterAction({ preventScroll: true });
    return;
  }
  try {
    const exportModel = _buildTabExportModel(t);
    const { linesHtml, prefixWidth } = ExportHtmlUtils.buildExportLinesHtml(exportModel.rawLines, {
      getPrefix: (line, i) => _exportPrefix(line, i),
      ansiToHtml: (text) => ansi_up.ansi_to_html(text),
    });
    const [fontFacesCss, exportCss] = await Promise.all([
      ExportHtmlUtils.fetchVendorFontFacesCss().catch(() => ''),
      ExportHtmlUtils.fetchTerminalExportCss().catch(() => ''),
    ]);
    const html = ExportHtmlUtils.buildTerminalExportHtml({
      appName: exportModel.appName,
      title: exportModel.title,
      metaLine: exportModel.metaLine,
      runMeta: exportModel.runMeta,
      linesHtml,
      prefixWidth,
      fontFacesCss,
      exportCss,
    });
    const blob = new Blob([html], { type: 'text/html' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${exportModel.appName}-${ExportHtmlUtils.exportTimestamp()}.html`;
    a.click();
    URL.revokeObjectURL(a.href);
  } catch {
    showToast('Failed to export html', 'error');
  } finally {
    if (typeof refocusComposerAfterAction === 'function') refocusComposerAfterAction({ preventScroll: true });
  }
}

// ── PDF export ──
// Delegates to ExportPdfUtils (export_pdf.js) which is the single source of
// truth shared with permalink.html. This function handles only tab-specific
// guards and data collection.

async function exportTabPdf(id) {
  const t = getTab(id);
  if (!t || !t.rawLines.length) {
    showToast('No output to export');
    if (typeof refocusComposerAfterAction === 'function') refocusComposerAfterAction({ preventScroll: true });
    return;
  }
  if (!window.jspdf) {
    showToast('PDF library not loaded', 'error');
    if (typeof refocusComposerAfterAction === 'function') refocusComposerAfterAction({ preventScroll: true });
    return;
  }
  try {
    const { jsPDF } = window.jspdf;
    const exportModel = _buildTabExportModel(t);
    const doc = await ExportPdfUtils.buildTerminalExportPdf({
      jsPDF,
      appName: exportModel.appName,
      metaLine: exportModel.metaLine,
      runMeta: exportModel.runMeta,
      rawLines: exportModel.rawLines,
      getPrefix: (line, i) => _exportPrefix(line, i),
      ansiToHtml: (text) => ansi_up.ansi_to_html(text),
    });
    const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    doc.save(`${exportModel.appName}-${ts}.pdf`);
  } catch {
    showToast('Failed to export pdf', 'error');
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

function _shareLinesWithoutTruncationNotices(lines) {
  return _normalizeTabTranscriptLines(lines, { stripTruncationNotices: true });
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

function _shareSnapshotLabel(tab) {
  if (!tab) return 'snapshot';
  const customLabel = String(tab.label || '').trim();
  const latestCommand = String(tab.command || '').trim();
  if (tab.renamed && customLabel) return customLabel;
  return latestCommand || customLabel || 'snapshot';
}

async function permalinkTab(id) {
  const t = getTab(id);
  if (!t || !t.rawLines.length) {
    showToast('No output to share yet');
    return;
  }
  const redactionMode = typeof confirmPermalinkRedactionChoice === 'function'
    ? await confirmPermalinkRedactionChoice()
    : (_shareRedactionEnabled() ? 'redacted' : 'raw');
  if (redactionMode !== 'raw' && redactionMode !== 'redacted') {
    refocusComposerAfterAction();
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
  const applyRedaction = redactionMode === 'redacted';
  if (applyRedaction) shareContent = _getRedactedLines(shareContent);
  apiFetch('/share', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ label: _shareSnapshotLabel(t), content: shareContent, apply_redaction: applyRedaction })
  }).then(r => r.json()).then(data => {
    const url = `${location.origin}${data.url}`;
    shareUrl(url).catch(() => showToast('Failed to copy link', 'error'));
  }).catch(() => showToast('Failed to create permalink', 'error'))
    .finally(() => {
      refocusComposerAfterAction();
    });
}
