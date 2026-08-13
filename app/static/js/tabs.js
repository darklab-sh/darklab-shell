// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// ── Desktop UI module ──
import {
  cmdInput as importedCmdInput,
  newTabBtn as importedNewTabBtn,
  shellPromptWrap as importedShellPromptWrap,
  tabbarChrome as importedTabbarChrome,
  tabbarChromeToggle as importedTabbarChromeToggle,
  tabPanels as importedTabPanels,
  tabsBar as importedTabsBar,
  tabsScrollLeftBtn as importedTabsScrollLeftBtn,
  tabsScrollRightBtn as importedTabsScrollRightBtn,
} from './core/dom.js';
import {
  emitUiEvent as importedEmitUiEvent,
  getActiveTabId as importedGetActiveTabId,
  getTab as importedGetTab,
  getTabs as importedGetTabs,
  getWelcomeState as importedGetWelcomeState,
  setActiveTabId as importedSetActiveTabId,
  setAutocompleteState as importedSetAutocompleteState,
  setTabs as importedSetTabs,
} from './core/state.js';
import { showToast as importedShowToast } from './core/utils.js';
import {
  activeTeamScopeCan as importedActiveTeamScopeCan,
  teamScopeDeniedMessage as importedTeamScopeDeniedMessage,
} from './features/team_scope.js';
import {
  _cancelPendingOutputBatch as importedCancelPendingOutputBatch,
  _resetTabOutputSignalCounts as importedResetTabOutputSignalCounts,
  _restoreOutputTailAfterLayout as importedRestoreOutputTailAfterLayout,
  _stickOutputToBottom as importedStickOutputToBottom,
  hasOutputHandler as importedHasOutputHandler,
  resetAnsiRendererForTab as importedResetAnsiRendererForTab,
  syncOutputPrefixes as importedSyncOutputPrefixes,
} from './output_bridge.js';
import {
  cancelPendingTerminalConfirm as importedCancelPendingTerminalConfirm,
  confirmKill as importedConfirmKill,
  setStatus as importedSetStatus,
  syncPendingTerminalConfirmPromptMode as importedSyncPendingTerminalConfirmPromptMode,
  syncActiveRunTimer as importedSyncActiveRunTimer,
} from './runner_bridge.js';
import { bindOutsideClickClose as importedBindOutsideClickClose } from './ui/ui_outside_click.js';
import { bindPressable as importedBindPressable } from './ui/ui_pressable.js';
import {
  blurActiveElement as importedBlurActiveElement,
  blurVisibleComposerInputIfMobile as importedBlurVisibleComposerInputIfMobile,
  focusElement as importedFocusElement,
  getComposerValue as importedGetComposerValue,
  refocusComposerAfterAction as importedRefocusComposerAfterAction,
  setComposerValue as importedSetComposerValue,
  syncRunButtonDisabled as importedSyncRunButtonDisabled,
} from './ui/ui_helpers.js';
import {
  bindTabDragReorder as importedBindTabDragReorder,
  tabDragSuppressClickUntil as importedTabDragSuppressClickUntil,
} from './features/tabs/tab_drag_reorder.js';
import { closeTab as importedCloseTab } from './features/tabs/tab_close_lifecycle.js';
import {
  getPreference as importedGetPreference,
  setPreferenceCookie as importedSetPreferenceCookie,
} from './features/preferences/preferences.js';
import {
  exitHistSearch as importedExitHistSearch,
  isHistSearchMode as importedIsHistSearchMode,
} from './features/history/history_search.js';
import { resetCmdHistoryNav as importedResetCmdHistoryNav } from './features/history/history_recall.js';
import {
  copyTab as importedCopyTab,
  exportTabHtml as importedExportTabHtml,
  exportTabPdf as importedExportTabPdf,
  permalinkTab as importedPermalinkTab,
  saveTab as importedSaveTab,
} from './features/tabs/tab_exports.js';
import {
  _tabSessionRestoreInProgress as importedTabSessionRestoreInProgress,
  schedulePersistTabSessionState as importedSchedulePersistTabSessionState,
} from './features/tabs/tab_session_state.js';
import {
  hasComposerPromptHandler as importedHasComposerPromptHandler,
  syncShellPrompt as importedSyncShellPrompt,
} from './features/terminal/composer_prompt_bridge.js';
import {
  hasMobileShellLayoutHandler as importedHasMobileShellLayoutHandler,
  useMobileTerminalViewportMode as importedUseMobileTerminalViewportMode,
} from './features/mobile/mobile_shell_layout_bridge.js';
import {
  clearSearch as importedClearSearch,
  hasSearchHandler as importedHasSearchHandler,
  refreshSearchDiscoverabilityUi as importedRefreshSearchDiscoverabilityUi,
  scheduleSearchDiscoverabilityRefresh as importedScheduleSearchDiscoverabilityRefresh,
} from './search_bridge.js';
import { setTabHandlers as importedSetTabHandlers } from './tabs_bridge.js';

var _tabsScrollControlsBound = false;
var _tabSeq = 0;
var _RUNNING_LABEL_DELAY_MS = 500;
var _OUTPUT_USER_SCROLL_GRACE_MS = 800;

function _tabGlobal() {
  return typeof window !== 'undefined' ? window : globalThis;
}

function _tabGlobalFn(name, imported = null) {
  if (typeof imported === 'function') return imported;
  const global = _tabGlobal();
  const fn = global && global[name];
  return typeof fn === 'function' ? fn : null;
}

function _syncTabShellPrompt() {
  const syncPrompt = (
    typeof importedHasComposerPromptHandler === 'function'
    && importedHasComposerPromptHandler('syncShellPrompt')
  ) ? importedSyncShellPrompt : _tabGlobalFn('syncShellPrompt');
  if (typeof syncPrompt === 'function') syncPrompt();
}

function _tabUseMobileTerminalViewportMode() {
  if (
    typeof importedHasMobileShellLayoutHandler === 'function'
    && importedHasMobileShellLayoutHandler('useMobileTerminalViewportMode')
  ) {
    return importedUseMobileTerminalViewportMode();
  }
  return !!_tabGlobalFn('useMobileTerminalViewportMode')?.();
}

function _tabSearchFn(name, imported = null) {
  const bridgeReady = (
    typeof importedHasSearchHandler === 'function'
    && importedHasSearchHandler(name)
    && typeof imported === 'function'
  );
  return bridgeReady ? imported : _tabGlobalFn(name);
}

function _tabGlobalValue(name, imported = undefined) {
  const global = _tabGlobal();
  return imported !== undefined ? imported : (global ? global[name] : undefined);
}

function _tabsList() {
  const list = importedGetTabs();
  return Array.isArray(list) ? list : [];
}

function _activeTabId() {
  return importedGetActiveTabId();
}

function _setActiveTabId(id) {
  importedSetActiveTabId(id);
}

function _tabById(id) {
  return importedGetTab(id);
}

function _setTabsList(next) {
  importedSetTabs(Array.isArray(next) ? next : []);
}

function _appConfig() {
  return _tabGlobalValue('APP_CONFIG') || {};
}

function _tabEl(name, imported = undefined) {
  return _tabGlobalValue(name, imported) || null;
}

function _isTabSessionRestoreInProgress() {
  return !!_tabGlobalValue('_tabSessionRestoreInProgress', importedTabSessionRestoreInProgress);
}

function _schedulePersistTabSessionState() {
  _tabGlobalFn('schedulePersistTabSessionState', importedSchedulePersistTabSessionState)?.();
}

function _callTabGlobal(name, ...args) {
  const fn = _tabGlobalFn(name);
  return fn ? fn(...args) : undefined;
}

function _blurActiveElement(...args) { return _tabGlobalFn('blurActiveElement', importedBlurActiveElement)?.(...args); }
function _blurVisibleComposerInputIfMobile(...args) {
  return _tabGlobalFn('blurVisibleComposerInputIfMobile', importedBlurVisibleComposerInputIfMobile)?.(...args);
}
function _focusElement(...args) { return _tabGlobalFn('focusElement', importedFocusElement)?.(...args); }
function _getComposerValue(...args) { return _tabGlobalFn('getComposerValue', importedGetComposerValue)?.(...args); }
function _refocusComposerAfterAction(...args) {
  return _tabGlobalFn('refocusComposerAfterAction', importedRefocusComposerAfterAction)?.(...args);
}
function _setComposerValue(...args) { return _tabGlobalFn('setComposerValue', importedSetComposerValue)?.(...args); }
function _showToast(...args) { return _tabGlobalFn('showToast', importedShowToast)?.(...args); }
function _syncRunButtonDisabled(...args) {
  return _tabGlobalFn('syncRunButtonDisabled', importedSyncRunButtonDisabled)?.(...args);
}

function _tabWelcomeApi(name) {
  return _tabGlobalValue(name, null);
}

function _tabWelcomeActive() {
  const apiState = importedGetWelcomeState();
  return !!(_tabGlobalValue('_welcomeActive') || (apiState && apiState.active));
}

function _tabWelcomeBootPending() {
  const apiState = importedGetWelcomeState();
  return !!(_tabGlobalValue('_welcomeBootPending')
    || (apiState && apiState.bootPending && (apiState.active || apiState.done || apiState.tabId)));
}

function _tabWelcomeOwns(tabId) {
  const owns = _tabWelcomeApi('welcomeOwnsTab');
  return typeof owns === 'function' && owns(tabId);
}

function _tabCancelWelcome(tabId) {
  const cancel = _tabWelcomeApi('cancelWelcome');
  if (typeof cancel === 'function') cancel(tabId);
}

function _clearAutocompleteFilteredState() {
  importedSetAutocompleteState({ filtered: [], index: -1 });
}

function _getTabEl(id) {
  const bar = _tabEl('tabsBar', importedTabsBar);
  return bar ? bar.querySelector(`.tab[data-id="${id}"]`) : null;
}

function _getTabPanelEl(id) {
  const panels = _tabEl('tabPanels', importedTabPanels);
  return panels ? panels.querySelector(`.tab-panel[data-id="${id}"]`) : null;
}

function _getTabStatusEl(id) {
  return _getTabEl(id)?.querySelector('.tab-status') || null;
}

function _getTabLabelEl(id) {
  return _getTabEl(id)?.querySelector('.tab-label') || null;
}

function _nextDefaultTabNumber() {
  const numbers = _tabsList()
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
  const tab = _tabById(id);
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
  const tab = _tabById(id);
  if (!tab) return;
  tab.outputUserScrollUntil = Date.now() + _OUTPUT_USER_SCROLL_GRACE_MS;
}


function _getNeighborTabIdAfterClose(idx, closingId) {
  const list = _tabsList();
  if (!list.length) return null;
  const next = list[idx + 1];
  if (next && next.id !== closingId) return next.id;
  const prev = list[idx - 1];
  if (prev && prev.id !== closingId) return prev.id;
  const fallback = list.find(tab => tab && tab.id !== closingId);
  return fallback ? fallback.id : null;
}

function updateTabScrollButtons() {
  // Recompute chrome collapse first so the scroll-button math below reflects the
  // width the tab strip actually has after any collapse/expand.
  updateTabbarChromeFit();
  const leftBtn = _tabEl('tabsScrollLeftBtn', importedTabsScrollLeftBtn);
  const rightBtn = _tabEl('tabsScrollRightBtn', importedTabsScrollRightBtn);
  const bar = _tabEl('tabsBar', importedTabsBar);
  if (!leftBtn || !rightBtn || !bar) return;
  const maxScroll = Math.max(0, bar.scrollWidth - bar.clientWidth);
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
  leftBtn.disabled = bar.scrollLeft <= 1;
  rightBtn.disabled = bar.scrollLeft >= (maxScroll - 1);
}

// ── Tab-bar chrome auto-collapse ────────────────────────────────────────────
// When the tab strip runs low on room, the right-hand chrome (search, findings
// badge, summarize, line numbers, timestamps) auto-collapses to just the
// findings badge plus a toggle, so tabs reclaim the width. The findings badge
// (#search-signal-summary) is not a .chrome-collapsible, so it stays visible.
var PREF_TABBAR_CHROME = 'pref_tabbar_chrome'; // 'auto' (default) | 'expanded' (user-pinned open)
var _TABBAR_CHROME_FIT_BUFFER = 12;
var _tabbarChromeFullWidth = 0; // cached width of the chrome while fully expanded

function _readTabbarChromePref() {
  const value = _tabGlobalFn('getPreference', importedGetPreference)?.(PREF_TABBAR_CHROME) || '';
  return value === 'expanded' ? 'expanded' : 'auto';
}

// Intrinsic width of the tab content, independent of how much room is currently
// available — summing children avoids scrollWidth inflating to fill slack space.
function _tabsIntrinsicWidth() {
  const bar = _tabEl('tabsBar', importedTabsBar);
  if (!bar || !bar.children) return 0;
  let total = 0;
  let count = 0;
  for (const child of bar.children) {
    if (child && typeof child.offsetWidth === 'number') {
      total += child.offsetWidth;
      count += 1;
    }
  }
  if (count > 1 && typeof window.getComputedStyle === 'function') {
    const style = window.getComputedStyle(bar);
    const gap = parseFloat(style.columnGap || style.gap || '0') || 0;
    total += gap * (count - 1);
  }
  return total;
}

// Pure decision: collapse only when the tabs cannot fit alongside the full
// chrome. State-independent (uses intrinsic widths), so it never oscillates.
function _decideTabbarChromeCollapsed({ pref, tabsWidth, chromeFullWidth, barWidth, buffer = _TABBAR_CHROME_FIT_BUFFER }) {
  if (pref === 'expanded') return false;
  if (!(barWidth > 0) || !(chromeFullWidth > 0)) return false;
  return (tabsWidth + chromeFullWidth) > (barWidth - buffer);
}

function _shouldShowTabbarChromeToggle({ pref, collapsed, autoWouldCollapse }) {
  return !!(collapsed || (pref === 'expanded' && autoWouldCollapse));
}

function _applyTabbarChromeState(barEl, collapsed, pref, autoWouldCollapse = collapsed) {
  if (!barEl) return;
  barEl.classList.toggle('chrome-collapsed', collapsed);
  const toggle = _tabEl('tabbarChromeToggle', importedTabbarChromeToggle);
  if (!toggle) return;
  // The toggle is actionable when auto collapsed (expand) or while pinned open
  // only if auto mode would still need to collapse. Once tabs fit again, hide
  // the release-to-auto affordance so the chrome returns to its normal shape.
  const showToggle = _shouldShowTabbarChromeToggle({ pref, collapsed, autoWouldCollapse });
  toggle.classList.toggle('u-hidden', !showToggle);
  // Glyph points the way the controls will travel: » collapses them away, «
  // pulls them back into view.
  toggle.textContent = collapsed ? '«' : '»';
  toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
  toggle.title = collapsed
    ? 'Show search and display controls'
    : 'Collapse toolbar to make room for tabs';
}

function updateTabbarChromeFit() {
  const chrome = _tabEl('tabbarChrome', importedTabbarChrome);
  if (!chrome) return;
  const barEl = chrome.closest('.terminal-bar');
  if (!barEl) return;
  const pref = _readTabbarChromePref();
  const currentlyCollapsed = barEl.classList.contains('chrome-collapsed');
  // Cache the full chrome width whenever it is expanded so we can decide against
  // it later even while collapsed (when the controls are display:none).
  if (!currentlyCollapsed) {
    const width = chrome.scrollWidth;
    if (width > 0) _tabbarChromeFullWidth = width;
  }
  const tabsWidth = _tabsIntrinsicWidth();
  const autoWouldCollapse = _decideTabbarChromeCollapsed({
    pref: 'auto',
    tabsWidth,
    chromeFullWidth: _tabbarChromeFullWidth,
    barWidth: barEl.clientWidth,
  });
  const collapsed = _decideTabbarChromeCollapsed({
    pref,
    tabsWidth,
    chromeFullWidth: _tabbarChromeFullWidth,
    barWidth: barEl.clientWidth,
  });
  _applyTabbarChromeState(barEl, collapsed, pref, autoWouldCollapse);
}

function _toggleTabbarChrome() {
  const chrome = _tabEl('tabbarChrome', importedTabbarChrome);
  if (!chrome) return;
  const barEl = chrome.closest('.terminal-bar');
  const pref = _readTabbarChromePref();
  const currentlyCollapsed = !!(barEl && barEl.classList.contains('chrome-collapsed'));
  // Pinned open → release to auto. Auto+collapsed → pin open. Auto+open → no-op.
  const next = pref === 'expanded' ? 'auto' : (currentlyCollapsed ? 'expanded' : 'auto');
  _tabGlobalFn('setPreferenceCookie', importedSetPreferenceCookie)?.(PREF_TABBAR_CHROME, next);
  updateTabbarChromeFit();
  _refocusComposerAfterAction({ defer: true });
}

function ensureActiveTabVisible(tabId) {
  const tabEl = _getTabEl(tabId);
  if (!tabEl || typeof tabEl.scrollIntoView !== 'function') return;
  tabEl.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' });
}

function scrollTabsBar(direction) {
  const bar = _tabEl('tabsBar', importedTabsBar);
  if (!bar || typeof bar.scrollBy !== 'function') return;
  bar.scrollBy({ left: direction * 220, behavior: 'smooth' });
  setTimeout(updateTabScrollButtons, 180);
  _refocusComposerAfterAction({ defer: true });
}

function setupTabScrollControls() {
  if (_tabsScrollControlsBound) return;
  const leftBtn = _tabEl('tabsScrollLeftBtn', importedTabsScrollLeftBtn);
  const rightBtn = _tabEl('tabsScrollRightBtn', importedTabsScrollRightBtn);
  const bar = _tabEl('tabsBar', importedTabsBar);
  if (!leftBtn || !rightBtn || !bar) return;
  leftBtn.addEventListener('click', () => scrollTabsBar(-1));
  rightBtn.addEventListener('click', () => scrollTabsBar(1));
  bar.addEventListener('scroll', updateTabScrollButtons, { passive: true });
  window.addEventListener('resize', updateTabScrollButtons);
  const toggle = _tabEl('tabbarChromeToggle', importedTabbarChromeToggle);
  if (toggle) {
    toggle.addEventListener('click', _toggleTabbarChrome);
  }
  // Observe the bar's own width so rail drag-resize (which never fires
  // window.resize) and other layout shifts keep the chrome fit in sync.
  const chrome = _tabEl('tabbarChrome', importedTabbarChrome);
  const barEl = chrome
    ? chrome.closest('.terminal-bar')
    : null;
  if (barEl && typeof ResizeObserver === 'function') {
    new ResizeObserver(() => updateTabScrollButtons()).observe(barEl);
  }
  _tabsScrollControlsBound = true;
  updateTabScrollButtons();
}

function syncTabOrderFromDom() {
  const bar = _tabEl('tabsBar', importedTabsBar);
  if (!bar) return;
  const orderedIds = [...bar.querySelectorAll('.tab')].map(node => node.dataset.id);
  if (!orderedIds.length) return;
  const byId = new Map(_tabsList().map(tab => [tab.id, tab]));
  _setTabsList(orderedIds.map(id => byId.get(id)).filter(Boolean));
  importedEmitUiEvent('app:tab-order-changed', {
    order: orderedIds.slice(),
    activeTabId: _activeTabId(),
  });
}

function unmountShellPrompt() {
  const promptWrap = _tabEl('shellPromptWrap', importedShellPromptWrap);
  if (!promptWrap) return;
  const prevParent = promptWrap.parentElement;
  promptWrap.classList.add('u-hidden');
  if (promptWrap.parentElement) promptWrap.remove();
  if (prevParent && prevParent.classList && prevParent.classList.contains('output')) {
    _tabSyncOutputPrefixes(prevParent);
  }
}

function mountShellPrompt(tabId, force = false) {
  // Only the active tab owns the live prompt node. Moving that one node keeps
  // prompt state continuous when switching tabs instead of cloning inputs.
  const promptWrap = _tabEl('shellPromptWrap', importedShellPromptWrap);
  if (!promptWrap) return;
  const mobileMode = !!(document.body && document.body.classList.contains('mobile-terminal-mode'));
  if (!force && _isTabSessionRestoreInProgress()) {
    unmountShellPrompt();
    return;
  }
  if (!force && !mobileMode && _tabWelcomeBootPending()) {
    unmountShellPrompt();
    return;
  }
  if (mobileMode) {
    unmountShellPrompt();
    return;
  }
  const tabState = _tabById(tabId);
  if (!force && tabState && tabState.deferPromptMount) {
    unmountShellPrompt();
    return;
  }
  // Keep the prompt hidden while the tab is running a command.
  if (tabState && tabState.st === 'running') {
    unmountShellPrompt();
    return;
  }
  if (!force && _tabWelcomeActive() && _tabWelcomeOwns(tabId)) {
    unmountShellPrompt();
    return;
  }
  const panel = _getTabPanelEl(tabId);
  if (!panel) return;
  const out = panel.querySelector('.output');
  if (!out) return;
  const prevParent = promptWrap.parentElement;
  if (prevParent !== out) {
    out.appendChild(promptWrap);
  }
  promptWrap.classList.remove('u-hidden');
  out.scrollTop = out.scrollHeight;
  if (prevParent && prevParent.classList && prevParent.classList.contains('output')) {
    _tabSyncOutputPrefixes(prevParent);
  }
  _tabSyncOutputPrefixes(out);
}

function _syncMountedPromptLineNumber(tabId) {
  const promptWrap = _tabEl('shellPromptWrap', importedShellPromptWrap);
  const out = getOutput(tabId);
  if (!promptWrap || !out || promptWrap.parentElement !== out) return;
  promptWrap.dataset.lineNumber = String((Number(out.dataset.outputLineCounter || 0) || 0) + 1);
}

function updateNewTabBtn() {
  const btn = _tabEl('newTabBtn', importedNewTabBtn);
  if (!btn) return;
  const config = _appConfig();
  const maxTabs = Number(config.max_tabs || 0);
  const atLimit = maxTabs > 0 && _tabsList().length >= maxTabs;
  btn.disabled = atLimit;
  btn.title = atLimit ? `Tab limit reached (max ${maxTabs})` : '';
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
  if (action === 'permalink') _updateTabShareSnapshotActionButton(btn);
  return btn;
}

function _canCreateTabShareSnapshot() {
  return typeof importedActiveTeamScopeCan === 'function'
    ? importedActiveTeamScopeCan('manage_history')
    : true;
}

function _tabShareSnapshotDeniedTitle() {
  const deniedMessage = typeof importedTeamScopeDeniedMessage === 'function'
    ? importedTeamScopeDeniedMessage
    : null;
  return deniedMessage
    ? deniedMessage('create team history snapshots')
    : "View-only team members can't create team history snapshots. Switch to Personal or ask for operator access.";
}

function _tabOutputFn(name, imported = null) {
  const hasBridgeHandler = typeof importedHasOutputHandler === 'function' && importedHasOutputHandler(name);
  if (hasBridgeHandler && typeof imported === 'function') return imported;
  const legacy = _tabGlobalFn(name);
  return typeof legacy === 'function' ? legacy : null;
}

function _tabSyncOutputPrefixes(...args) {
  return _tabOutputFn('syncOutputPrefixes', importedSyncOutputPrefixes)?.(...args);
}

function _tabStickOutputToBottom(...args) {
  return _tabOutputFn('_stickOutputToBottom', importedStickOutputToBottom)?.(...args);
}

function _tabRestoreOutputTailAfterLayout(...args) {
  return _tabOutputFn('_restoreOutputTailAfterLayout', importedRestoreOutputTailAfterLayout)?.(...args);
}

function _tabCancelPendingOutputBatch(...args) {
  return _tabOutputFn('_cancelPendingOutputBatch', importedCancelPendingOutputBatch)?.(...args);
}

function _tabResetAnsiRendererForTab(...args) {
  return _tabOutputFn('resetAnsiRendererForTab', importedResetAnsiRendererForTab)?.(...args);
}

function _tabResetOutputSignalCounts(...args) {
  return _tabOutputFn('_resetTabOutputSignalCounts', importedResetTabOutputSignalCounts)?.(...args);
}

function _updateTabShareSnapshotActionButton(btn) {
  if (!btn) return;
  const allowed = _canCreateTabShareSnapshot();
  btn.disabled = !allowed;
  btn.title = allowed ? 'Share tab as permalink' : _tabShareSnapshotDeniedTitle();
}

function refreshShareSnapshotActions() {
  document.querySelectorAll('[data-action="permalink"][data-tab]').forEach(_updateTabShareSnapshotActionButton);
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
  const tab = _tabById(id);
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
    const tab = _tabById(id);
    const out = getOutput(id);
    if (!tab || !out) return;
    tab.followOutput = true;
    const stickOutputToBottom = _tabOutputFn('_stickOutputToBottom', importedStickOutputToBottom);
    if (stickOutputToBottom) {
      stickOutputToBottom(out, tab);
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
  const bindOutsideClickClose = _tabGlobalFn('bindOutsideClickClose', importedBindOutsideClickClose);
  if (bindOutsideClickClose) {
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
  const config = _appConfig();
  const maxTabs = Number(config.max_tabs || 0);
  if (maxTabs > 0 && _tabsList().length >= maxTabs) {
    _showToast(`Tab limit reached (max ${maxTabs})`);
    return null;
  }
  const id = 'tab-' + (++_tabSeq);
  const stableLabel = String(label || createDefaultTabLabel());

  const { tab, labelEl } = _createTabHeader(id, stableLabel);
  const closeCurrentTab = typeof importedCloseTab === 'function'
    ? importedCloseTab
    : _tabGlobalFn('closeTab');
  const bindDragReorder = typeof importedBindTabDragReorder === 'function'
    ? importedBindTabDragReorder
    : _tabGlobalFn('bindTabDragReorder');
  const copyCurrentTab = typeof importedCopyTab === 'function'
    ? importedCopyTab
    : _tabGlobalFn('copyTab');
  const permalinkCurrentTab = typeof importedPermalinkTab === 'function'
    ? importedPermalinkTab
    : _tabGlobalFn('permalinkTab');
  const saveCurrentTab = typeof importedSaveTab === 'function'
    ? importedSaveTab
    : _tabGlobalFn('saveTab');
  const exportCurrentTabHtml = typeof importedExportTabHtml === 'function'
    ? importedExportTabHtml
    : _tabGlobalFn('exportTabHtml');
  const exportCurrentTabPdf = typeof importedExportTabPdf === 'function'
    ? importedExportTabPdf
    : _tabGlobalFn('exportTabPdf');
  tab.addEventListener('click', e => {
    const suppressUntil = typeof importedTabDragSuppressClickUntil === 'function'
      ? importedTabDragSuppressClickUntil()
      : _tabGlobalValue('_tabDragSuppressClickUntil');
    if (Date.now() < Number(suppressUntil || 0)) return;
    if (e.target.classList.contains('tab-close')) {
      if (closeCurrentTab) closeCurrentTab(id);
      _blurActiveElement();
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
  if (bindDragReorder) bindDragReorder(tab, id);

  const newTabButton = _tabEl('newTabBtn', importedNewTabBtn);
  const bar = _tabEl('tabsBar', importedTabsBar);
  if (newTabButton && newTabButton.parentElement === bar) {
    bar.insertBefore(tab, newTabButton);
  } else {
    bar?.appendChild(tab);
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
      const t = _tabById(id);
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
    if (id !== _activeTabId()) return;
    if (e.target.closest('.btn')) return;
    if (e.target.closest('.welcome-command-loadable')) return;
    // Don't steal focus while the user has text selected — they may be about to copy.
    if (typeof window !== 'undefined' && window.getSelection && window.getSelection().toString().length > 0) return;
    _refocusComposerAfterAction();
  });
  panel.querySelectorAll('[data-action]').forEach(btn => {
    const action = btn.dataset.action;
    // save-menu is a disclosure trigger: keep the dropdown-open affordance by
    // suppressing the auto-refocus so the user's attention stays on the menu
    // they just opened.
    const isDisclosure = action === 'save-menu';
    const bindPressable = _tabGlobalFn('bindPressable', importedBindPressable);
    bindPressable?.(btn, {
      refocusComposer: !isDisclosure,
      onActivate: () => {
        if (_tabUseMobileTerminalViewportMode()) {
          _blurVisibleComposerInputIfMobile();
        }
        if (action === 'kill') {
          const confirmKill = (typeof importedConfirmKill === 'function' && importedConfirmKill)
            || _tabGlobalFn('confirmKill');
          confirmKill?.(id);
        }
        if (action === 'clear') {
          _tabGlobalFn(
            'cancelPendingTerminalConfirm',
            importedCancelPendingTerminalConfirm,
          )?.(id, { refocus: false });
          _tabCancelWelcome(id);
          clearTab(id, { preserveRunState: true });
        }
        if (action === 'copy' && copyCurrentTab) copyCurrentTab(id);
        if (action === 'permalink' && permalinkCurrentTab) permalinkCurrentTab(id);
        if (action === 'save-menu') {
          btn.closest('.save-menu-wrap').classList.toggle('open');
          return;
        }
        if (action === 'save-txt' || action === 'save-html' || action === 'save-pdf') {
          const wrap = btn.closest('.save-menu-wrap');
          if (wrap) wrap.classList.remove('open');
        }
        if (action === 'save-txt' && saveCurrentTab) saveCurrentTab(id);
        if (action === 'save-html' && exportCurrentTabHtml) exportCurrentTabHtml(id);
        if (action === 'save-pdf' && exportCurrentTabPdf) void exportCurrentTabPdf(id);
      },
    });
  });
  _tabEl('tabPanels', importedTabPanels)?.appendChild(panel);

  const list = _tabsList();
  list.push({
    id,
    label: stableLabel,
    runningLabel: '',
    runningLabelTimer: null,
    command: '',
    runId: null,
    historyRunId: null,
    historyRunKind: '',
    lastEventId: '',
    attachMode: '',
    reconnectedRun: false,
    runStart: null,
    currentRunStartIndex: null,
    exitCode: null,
    commandOutcomeSummary: null,
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
  _schedulePersistTabSessionState();
  importedEmitUiEvent('app:tab-created', { id, label: stableLabel, activeTabId: _activeTabId() });
  return id;
}

function activateTab(id, { focusComposer = true } = {}) {
  // Activation swaps the live prompt, the status pill, output-follow helpers,
  // and the visible transcript. Keep it centralized here to avoid drift.
  // Exit hist-search mode cleanly before switching tabs
  if (_tabGlobalFn('isHistSearchMode', importedIsHistSearchMode)?.()) {
    _tabGlobalFn('exitHistSearch', importedExitHistSearch)?.(false);
  }
  // Flush the current composer value into the leaving tab's draftInput before switching.
  const prevId = _activeTabId();
  if (!_isTabSessionRestoreInProgress() && prevId && prevId !== id) {
    const prevTab = _tabById(prevId);
    if (prevTab && prevTab.st === 'running') {
      prevTab.draftInput = '';
    } else if (prevTab) {
      const input = _tabEl('cmdInput', importedCmdInput);
      prevTab.draftInput = _getComposerValue?.() || (input ? input.value : '');
    }
  }
  _setActiveTabId(id);
  _tabEl('tabsBar', importedTabsBar)?.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.id === id));
  _tabEl('tabPanels', importedTabPanels)?.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.dataset.id === id));
  mountShellPrompt(id);
  const t = _tabById(id);
  const setStatus = (typeof importedSetStatus === 'function' && importedSetStatus)
    || _tabGlobalFn('setStatus');
  setStatus?.(t ? (t.st || 'idle') : 'idle');
  if (t && t.followOutput !== false) {
    const out = getOutput(id);
    const restoreTail = _tabOutputFn('_restoreOutputTailAfterLayout', importedRestoreOutputTailAfterLayout);
    const stickBottom = _tabOutputFn('_stickOutputToBottom', importedStickOutputToBottom);
    if (out && restoreTail) {
      restoreTail(out, t);
    } else if (out && stickBottom) {
      stickBottom(out, t);
    }
  }
  ensureActiveTabVisible(id);
  updateTabScrollButtons();
  _tabSearchFn('clearSearch', importedClearSearch)?.();
  // Hide the autocomplete dropdown and clear the filtered list so stale
  // suggestions from the previous tab's typing session don't persist.
  _tabGlobalFn('acHide')?.();
  _clearAutocompleteFilteredState();
  let draft = (t && t.st !== 'running') ? (t.draftInput || '') : '';
  if (!prevId && !draft) {
    const liveDraft = _getComposerValue?.();
    if (liveDraft && liveDraft.trim()) draft = liveDraft;
  }
  _setComposerValue(draft, draft.length, draft.length, { dispatch: false });
  _tabGlobalFn('resetCmdHistoryNav', importedResetCmdHistoryNav)?.();
  _tabGlobalFn('syncActiveRunTimer', importedSyncActiveRunTimer)?.(id);
  _tabGlobalFn(
    'syncPendingTerminalConfirmPromptMode',
    importedSyncPendingTerminalConfirmPromptMode,
  )?.(id);
  if (focusComposer) _refocusComposerAfterAction({ preventScroll: true });
  _syncRunButtonDisabled();
  _syncTabShellPrompt();
  updateOutputFollowButton(id);
  const scheduleSearchRefresh = _tabSearchFn(
    'scheduleSearchDiscoverabilityRefresh',
    importedScheduleSearchDiscoverabilityRefresh,
  );
  if (scheduleSearchRefresh) scheduleSearchRefresh();
  else _tabSearchFn('refreshSearchDiscoverabilityUi', importedRefreshSearchDiscoverabilityUi)?.();
  _schedulePersistTabSessionState();
  importedEmitUiEvent('app:tab-activated', { id, prevId, activeTabId: _activeTabId() });
}

function setTabStatus(id, st) {
  const dot = _getTabStatusEl(id);
  if (dot) dot.className = `tab-status ${st}`;
  const t = _tabById(id);
  if (t) {
    t.st = st;
    if (st !== 'running') {
      _clearTabRunningLabelTimer(t);
      t.runningLabel = '';
    }
  }
  _renderTabLabel(id);
  if (id === _activeTabId()) {
    if (_isTabSessionRestoreInProgress()) {
      unmountShellPrompt();
    } else if (st === 'running') {
      unmountShellPrompt();
    } else {
      mountShellPrompt(id);
    }
    _syncRunButtonDisabled();
    _tabSearchFn('refreshSearchDiscoverabilityUi', importedRefreshSearchDiscoverabilityUi)?.();
  }
  updateOutputFollowButton(id);
  _schedulePersistTabSessionState();
  importedEmitUiEvent('app:tab-status-changed', { id, status: st, activeTabId: _activeTabId() });
}

function setTabLabel(id, label) {
  const t = _tabById(id);
  if (t) {
    t.label = String(label || '');
    _renderTabLabel(id);
  }
  if (id === _activeTabId()) ensureActiveTabVisible(id);
  _schedulePersistTabSessionState();
}

function setTabRunningCommand(id, command) {
  const t = _tabById(id);
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
    if (id === _activeTabId()) ensureActiveTabVisible(id);
  }, _RUNNING_LABEL_DELAY_MS);
  _renderTabLabel(id);
  if (id === _activeTabId()) ensureActiveTabVisible(id);
  _schedulePersistTabSessionState();
}

function getOutput(id) {
  return _getTabOutputEl(id);
}

function clearTab(id, { preserveRunState = false } = {}) {
  _tabCancelPendingOutputBatch(id);
  _tabResetAnsiRendererForTab(id);
  const out = getOutput(id);
  if (out) {
    out.innerHTML = '';
    out.dataset.outputLineCounter = '0';
  }
  const t = _tabById(id);
  const wasRunning = !!(t && t.st === 'running');
  if (t) {
    t._outputFollowToken = (t._outputFollowToken || 0) + 1;
    t._outputLineCounter = 0;
    t.suppressOutputScrollTracking = false;
    t.deferPromptMount = false;
    t.rawLines = [];
    t.commandOutcomeSummary = null;
    _tabResetOutputSignalCounts(t);
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
      t.historyRunKind = '';
      t.reconnectedRun = false;
      _clearTabRunningLabelTimer(t);
      t.runningLabel = '';
    }
  }
  if (id === _activeTabId() && (!preserveRunState || !wasRunning)) {
    mountShellPrompt(id);
    _syncMountedPromptLineNumber(id);
  }
  if (id === _activeTabId()
    && (!preserveRunState || !wasRunning)
    && !(typeof document !== 'undefined'
      && document.body
      && document.body.classList
      && document.body.classList.contains('mobile-terminal-mode'))) {
    _setComposerValue('', 0, 0);
  }
  if (!preserveRunState || !wasRunning) {
    setTabStatus(id, 'idle');
    if (id === _activeTabId()) {
      const setStatus = (typeof importedSetStatus === 'function' && importedSetStatus)
        || _tabGlobalFn('setStatus');
      setStatus?.('idle');
      _tabSearchFn('clearSearch', importedClearSearch)?.();
    }
  }
  updateOutputFollowButton(id);
  if (id === _activeTabId()) {
    _tabSearchFn('refreshSearchDiscoverabilityUi', importedRefreshSearchDiscoverabilityUi)?.();
  }
  if (typeof document !== 'undefined'
    && document.body
    && document.body.classList
    && document.body.classList.contains('mobile-terminal-mode')
    && _tabGlobalFn('blurVisibleComposerInputIfMobile', importedBlurVisibleComposerInputIfMobile)) {
    setTimeout(() => _blurVisibleComposerInputIfMobile(), 0);
  }
  _schedulePersistTabSessionState();
}

// ── Tab rename ──
function startTabRename(id, labelEl) {
  const t = _tabById(id);
  if (!t) return;
  const original = t.label;

  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'tab-rename-input';
  input.value = original;
  labelEl.textContent = '';
  labelEl.appendChild(input);
  _focusElement(input);
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

document.addEventListener('app:scope-changed', () => {
  refreshShareSnapshotActions();
});
document.addEventListener('app:scope-capabilities-changed', () => {
  refreshShareSnapshotActions();
});

if (typeof window !== 'undefined') {
}

if (typeof importedSetTabHandlers === 'function') {
  importedSetTabHandlers({
    _clearTabRunningLabelTimer,
    _getNeighborTabIdAfterClose,
    _getTabEl,
    _getTabPanelEl,
    activateTab,
    clearTab,
    createDefaultTabLabel,
    createTab,
    ensureActiveTabVisible,
    getOutput,
    mountShellPrompt,
    setTabLabel,
    setTabStatus,
    syncTabOrderFromDom,
    unmountShellPrompt,
    updateNewTabBtn,
    updateOutputFollowButton,
    updateTabScrollButtons,
  });
}

export {
  _applyTabbarChromeState,
  _canCreateTabShareSnapshot,
  _clearTabRunningLabelTimer,
  _createTabActionButton,
  _createTabHeader,
  _createTabPanel,
  _decideTabbarChromeCollapsed,
  _getNeighborTabIdAfterClose,
  _getOutputFollowButton,
  _getTabEl,
  _getTabLabelEl,
  _getTabOutputEl,
  _getTabPanelEl,
  _getTabStatusEl,
  _isOutputAtTail,
  _markOutputUserScrollIntent,
  _nextDefaultTabNumber,
  _readTabbarChromePref,
  _renderTabLabel,
  _shouldShowTabbarChromeToggle,
  _tabCancelWelcome,
  _tabDisplayLabel,
  _tabShareSnapshotDeniedTitle,
  _tabWelcomeActive,
  _tabWelcomeApi,
  _tabWelcomeBootPending,
  _tabWelcomeOwns,
  _tabsIntrinsicWidth,
  _toggleTabbarChrome,
  _truncateTabLabel,
  _updateTabShareSnapshotActionButton,
  activateTab,
  clearTab,
  createDefaultTabLabel,
  createTab,
  ensureActiveTabVisible,
  getOutput,
  mountShellPrompt,
  refreshShareSnapshotActions,
  scrollTabsBar,
  setTabLabel,
  setTabRunningCommand,
  setTabStatus,
  setupTabScrollControls,
  startTabRename,
  syncTabOrderFromDom,
  unmountShellPrompt,
  updateNewTabBtn,
  updateOutputFollowButton,
  updateTabScrollButtons,
  updateTabbarChromeFit,
};
