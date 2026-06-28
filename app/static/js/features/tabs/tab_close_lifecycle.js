import {
  emitUiEvent as importedEmitUiEvent,
  getActiveTabId as importedGetActiveTabId,
  getTabs as importedGetTabs,
} from '../../core/state.js';
import { markActiveRunDetachedForRestore as importedMarkActiveRunDetachedForRestore } from '../runner/runner_active_restore.js';
import { useMobileTerminalViewportMode as importedUseMobileTerminalViewportMode } from '../mobile/mobile_shell_layout.js';
import {
  _cancelPendingOutputBatch as importedCancelPendingOutputBatch,
  dropAnsiRendererForTab as importedDropAnsiRendererForTab,
  resetAnsiRendererForTab as importedResetAnsiRendererForTab,
} from '../../output.js';
import {
  detachRunStreamForTab as importedDetachRunStreamForTab,
  doKill as importedDoKill,
} from '../../runner.js';
import {
  _clearTabRunningLabelTimer as importedClearTabRunningLabelTimer,
  _getNeighborTabIdAfterClose as importedGetNeighborTabIdAfterClose,
  _getTabEl as importedGetTabEl,
  _getTabPanelEl as importedGetTabPanelEl,
  activateTab as importedActivateTab,
  clearTab as importedClearTab,
  createDefaultTabLabel as importedCreateDefaultTabLabel,
  getOutput as importedGetOutput,
  setTabLabel as importedSetTabLabel,
  updateNewTabBtn as importedUpdateNewTabBtn,
  updateTabScrollButtons as importedUpdateTabScrollButtons,
} from '../../tabs_bridge.js';
import {
  blurActiveElement as importedBlurActiveElement,
  blurVisibleComposerInputIfMobile as importedBlurVisibleComposerInputIfMobile,
  syncRunButtonDisabled as importedSyncRunButtonDisabled,
} from '../../ui/ui_helpers.js';
import { showConfirm as importedShowConfirm } from '../../ui/ui_confirm.js';
import { cancelWelcome as importedCancelWelcome } from '../../welcome.js';
import { schedulePersistTabSessionState as importedSchedulePersistTabSessionState } from './tab_session_state.js';

const TAB_CLOSE_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

function _tabCloseGlobalFunction(name) {
  const fn = TAB_CLOSE_GLOBAL && TAB_CLOSE_GLOBAL[name];
  return typeof fn === 'function' ? fn : null;
}

function _tabCloseTabs() {
  if (typeof importedGetTabs !== 'undefined' && typeof importedGetTabs === 'function') return importedGetTabs();
  const readTabs = _tabCloseGlobalFunction('getTabs');
  if (readTabs) return readTabs();
  return [];
}

function _tabCloseActiveTabId() {
  if (typeof importedGetActiveTabId !== 'undefined' && typeof importedGetActiveTabId === 'function') {
    return importedGetActiveTabId();
  }
  const readActiveTabId = _tabCloseGlobalFunction('getActiveTabId');
  if (readActiveTabId) return readActiveTabId();
  return null;
}

function _tabCloseEmitUiEvent(name, detail = {}) {
  const emit = (typeof importedEmitUiEvent !== 'undefined' && importedEmitUiEvent)
    || _tabCloseGlobalFunction('emitUiEvent');
  if (typeof emit === 'function') emit(name, detail);
}

function _tabCloseBlurActiveElement() {
  const blur = (typeof importedBlurActiveElement !== 'undefined' && importedBlurActiveElement)
    || _tabCloseGlobalFunction('blurActiveElement');
  if (typeof blur === 'function') blur();
}

function _tabCloseBlurVisibleComposerInputIfMobile() {
  const blur = (
    typeof importedBlurVisibleComposerInputIfMobile !== 'undefined'
    && importedBlurVisibleComposerInputIfMobile
  ) || _tabCloseGlobalFunction('blurVisibleComposerInputIfMobile');
  if (typeof blur === 'function') blur();
}

function _tabCloseConfirm() {
  return (typeof importedShowConfirm !== 'undefined' && importedShowConfirm)
    || _tabCloseGlobalFunction('showConfirm');
}

function _tabCloseShowConfirm(options) {
  const confirm = _tabCloseConfirm();
  return typeof confirm === 'function' ? confirm(options) : null;
}

function _tabCloseMarkActiveRunDetachedForRestore(runId) {
  const markDetached = (
    typeof importedMarkActiveRunDetachedForRestore !== 'undefined'
    && importedMarkActiveRunDetachedForRestore
  ) || _tabCloseGlobalFunction('markActiveRunDetachedForRestore');
  if (typeof markDetached === 'function') markDetached(runId);
}

function _tabCloseSyncRunButtonDisabled() {
  const sync = (typeof importedSyncRunButtonDisabled !== 'undefined' && importedSyncRunButtonDisabled)
    || _tabCloseGlobalFunction('syncRunButtonDisabled');
  if (typeof sync === 'function') sync();
}

function _tabCloseUseMobileTerminalViewportMode() {
  const useMobile = (typeof importedUseMobileTerminalViewportMode !== 'undefined' && importedUseMobileTerminalViewportMode)
    || _tabCloseGlobalFunction('useMobileTerminalViewportMode');
  return typeof useMobile === 'function' && useMobile();
}

function _tabCloseResetAnsiRendererForTab(tabId) {
  const resetAnsi = (typeof importedResetAnsiRendererForTab !== 'undefined' && importedResetAnsiRendererForTab)
    || _tabCloseGlobalFunction('resetAnsiRendererForTab');
  if (typeof resetAnsi === 'function') resetAnsi(tabId);
}

function _tabCloseDropAnsiRendererForTab(tabId) {
  const dropAnsi = (typeof importedDropAnsiRendererForTab !== 'undefined' && importedDropAnsiRendererForTab)
    || _tabCloseGlobalFunction('dropAnsiRendererForTab');
  if (typeof dropAnsi === 'function') dropAnsi(tabId);
}

function _tabCloseCancelPendingOutputBatch(tabId) {
  const cancelBatch = (typeof importedCancelPendingOutputBatch !== 'undefined' && importedCancelPendingOutputBatch)
    || _tabCloseGlobalFunction('_cancelPendingOutputBatch');
  if (typeof cancelBatch === 'function') cancelBatch(tabId);
}

function _tabCloseClearTabRunningLabelTimer(tab) {
  const clearTimer = (typeof importedClearTabRunningLabelTimer !== 'undefined' && importedClearTabRunningLabelTimer)
    || _tabCloseGlobalFunction('_clearTabRunningLabelTimer');
  if (typeof clearTimer === 'function') clearTimer(tab);
}

function _tabCloseGetNeighborTabIdAfterClose(idx, id) {
  const getNeighbor = (typeof importedGetNeighborTabIdAfterClose !== 'undefined' && importedGetNeighborTabIdAfterClose)
    || _tabCloseGlobalFunction('_getNeighborTabIdAfterClose');
  return typeof getNeighbor === 'function' ? getNeighbor(idx, id) : null;
}

function _tabCloseGetTabEl(id) {
  const getEl = (typeof importedGetTabEl !== 'undefined' && importedGetTabEl)
    || _tabCloseGlobalFunction('_getTabEl');
  return typeof getEl === 'function' ? getEl(id) : null;
}

function _tabCloseGetTabPanelEl(id) {
  const getEl = (typeof importedGetTabPanelEl !== 'undefined' && importedGetTabPanelEl)
    || _tabCloseGlobalFunction('_getTabPanelEl');
  return typeof getEl === 'function' ? getEl(id) : null;
}

function _tabCloseActivateTab(id, options) {
  const activate = (typeof importedActivateTab !== 'undefined' && importedActivateTab)
    || _tabCloseGlobalFunction('activateTab');
  if (typeof activate === 'function') activate(id, options);
}

function _tabCloseUpdateNewTabBtn() {
  const update = (typeof importedUpdateNewTabBtn !== 'undefined' && importedUpdateNewTabBtn)
    || _tabCloseGlobalFunction('updateNewTabBtn');
  if (typeof update === 'function') update();
}

function _tabCloseUpdateTabScrollButtons() {
  const update = (typeof importedUpdateTabScrollButtons !== 'undefined' && importedUpdateTabScrollButtons)
    || _tabCloseGlobalFunction('updateTabScrollButtons');
  if (typeof update === 'function') update();
}

function _tabCloseSchedulePersistTabSessionState() {
  const schedule = (typeof importedSchedulePersistTabSessionState !== 'undefined' && importedSchedulePersistTabSessionState)
    || _tabCloseGlobalFunction('schedulePersistTabSessionState');
  if (typeof schedule === 'function') schedule();
}

function _tabCloseDetachRunStreamForTab(id) {
  const detach = (typeof importedDetachRunStreamForTab !== 'undefined' && importedDetachRunStreamForTab)
    || _tabCloseGlobalFunction('detachRunStreamForTab');
  if (typeof detach === 'function') detach(id);
}

function _tabCloseDetachInteractivePtyForTab(id) {
  const detach = _tabCloseGlobalFunction('detachInteractivePtyForTab');
  if (typeof detach === 'function') detach(id);
}

function _tabCloseDoKill(id) {
  const kill = (typeof importedDoKill !== 'undefined' && importedDoKill)
    || _tabCloseGlobalFunction('doKill');
  if (typeof kill === 'function') kill(id);
}

function _tabCloseClearTab(id) {
  const clear = (typeof importedClearTab !== 'undefined' && importedClearTab)
    || _tabCloseGlobalFunction('clearTab');
  if (typeof clear === 'function') clear(id);
}

function _tabCloseDefaultTabLabel(index) {
  const createLabel = (typeof importedCreateDefaultTabLabel !== 'undefined' && importedCreateDefaultTabLabel)
    || _tabCloseGlobalFunction('createDefaultTabLabel');
  return typeof createLabel === 'function' ? createLabel(index) : `Tab ${index}`;
}

function _tabCloseSetTabLabel(id, label) {
  const setLabel = (typeof importedSetTabLabel !== 'undefined' && importedSetTabLabel)
    || _tabCloseGlobalFunction('setTabLabel');
  if (typeof setLabel === 'function') setLabel(id, label);
}

function _tabCloseSyncMountedPromptLineNumber(id) {
  const getOutput = (typeof importedGetOutput === 'function' && importedGetOutput)
    || _tabCloseGlobalFunction('getOutput');
  const out = typeof getOutput === 'function' ? getOutput(id) : null;
  const prompt = TAB_CLOSE_GLOBAL && TAB_CLOSE_GLOBAL.shellPromptWrap;
  if (!prompt) return;
  if (out && prompt.parentElement !== out) out.appendChild(prompt);
  prompt.dataset.lineNumber = String((Number(out?.dataset?.outputLineCounter || 0) || 0) + 1);
}

function _tabCloseCancelWelcome(id) {
  const cancel = (typeof importedCancelWelcome !== 'undefined' && importedCancelWelcome)
    || _tabCloseGlobalFunction('cancelWelcome');
  if (typeof cancel === 'function') cancel(id);
}

function _resetPreservedSingleTabState(tab) {
  if (!tab) return;
  _tabCloseResetAnsiRendererForTab(tab.id);
  tab.command = '';
  tab.runId = null;
  tab.historyRunId = null;
  tab.lastEventId = '';
  tab.attachMode = '';
  tab.reconnectedRun = false;
  tab.runStart = null;
  tab.currentRunStartIndex = null;
  tab.exitCode = null;
  tab.previewTruncated = false;
  tab.fullOutputAvailable = false;
  tab.fullOutputLoaded = false;
  tab.followOutput = true;
  tab.outputUserScrollUntil = 0;
  tab.suppressOutputScrollTracking = false;
  tab.deferPromptMount = false;
  tab.closing = false;
  tab.killed = false;
  tab.pendingKill = false;
  tab.renamed = false;
  tab.workspaceCwd = '';
  tab.draftInput = '';
  tab.commandHistory = [];
  tab.historyNavIndex = -1;
  tab.historyNavDraft = '';
  tab._outputLineCounter = 0;
  _tabCloseClearTabRunningLabelTimer(tab);
  tab.runningLabel = '';
}

function _activateNeighborAfterClose(idx, id) {
  const currentTabs = _tabCloseTabs();
  if (_tabCloseActiveTabId() !== id) return;
  const nextId = _tabCloseGetNeighborTabIdAfterClose(Math.min(idx, currentTabs.length), id);
  if (nextId) _tabCloseActivateTab(nextId, { focusComposer: false });
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

function _removeClosedTabView(id, idx) {
  const currentTabs = _tabCloseTabs();
  currentTabs.splice(idx, 1);
  _tabCloseDropAnsiRendererForTab(id);
  _tabCloseGetTabEl(id)?.remove();
  _tabCloseGetTabPanelEl(id)?.remove();
  _activateNeighborAfterClose(idx, id);
  _tabCloseUpdateNewTabBtn();
  _tabCloseUpdateTabScrollButtons();
  _tabCloseSchedulePersistTabSessionState();
  _tabCloseEmitUiEvent('app:tab-closed', { id, activeTabId: _tabCloseActiveTabId() });
}

function detachRunningTabAndClose(id) {
  const currentTabs = _tabCloseTabs();
  const idx = currentTabs.findIndex(t => t.id === id);
  if (idx < 0) return false;
  const tab = currentTabs[idx];
  if (!tab || tab.st !== 'running') return false;
  const runId = tab.runId || tab.historyRunId || '';
  _tabCloseMarkActiveRunDetachedForRestore(runId);
  _tabCloseDetachRunStreamForTab(id);
  _tabCloseDetachInteractivePtyForTab(id);
  tab.closing = false;
  if (currentTabs.length === 1) {
    _resetPreservedSingleTabState(tab);
    _tabCloseClearTab(id);
    _tabCloseSetTabLabel(id, _tabCloseDefaultTabLabel(1));
    _tabCloseSyncMountedPromptLineNumber(id);
    _tabCloseBlurActiveElement();
    _tabCloseSchedulePersistTabSessionState();
    _tabCloseEmitUiEvent('app:tab-detached', { id, activeTabId: _tabCloseActiveTabId(), preservedSingleTab: true });
    _tabCloseEmitUiEvent('app:tab-closed', { id, activeTabId: _tabCloseActiveTabId(), preservedSingleTab: true });
    return true;
  }
  _removeClosedTabView(id, idx);
  _tabCloseEmitUiEvent('app:tab-detached', { id, activeTabId: _tabCloseActiveTabId() });
  return true;
}

function _deferRunningTabCloseForKill(id, idx) {
  const currentTabs = _tabCloseTabs();
  const closingTab = currentTabs[idx];
  if (!closingTab || closingTab.st !== 'running') return false;
  closingTab.closing = true;
  _tabCloseDoKill(id);
  if (_tabCloseActiveTabId() === id && currentTabs.length > 1) {
    const nextId = _tabCloseGetNeighborTabIdAfterClose(idx, id);
    if (nextId) _tabCloseActivateTab(nextId, { focusComposer: false });
  }
  _tabCloseSyncRunButtonDisabled();
  _tabCloseUpdateNewTabBtn();
  _tabCloseUpdateTabScrollButtons();
  _tabCloseSchedulePersistTabSessionState();
  _tabCloseEmitUiEvent('app:tab-closing-deferred', { id, activeTabId: _tabCloseActiveTabId() });
  return true;
}

function confirmCloseRunningTab(id) {
  const currentTabs = _tabCloseTabs();
  const idx = currentTabs.findIndex(t => t.id === id);
  const tab = currentTabs[idx];
  if (!tab || tab.st !== 'running') return Promise.resolve(false);
  const canDetach = !!(tab.runId || tab.historyRunId);
  const kill = () => _deferRunningTabCloseForKill(id, idx);
  if (typeof _tabCloseConfirm() !== 'function') {
    return Promise.resolve(canDetach ? detachRunningTabAndClose(id) : kill());
  }
  const actions = [
    ...(canDetach ? [{ id: 'detach', label: 'Keep running', role: 'primary' }] : []),
    { id: 'kill', label: 'Kill run', role: 'destructive' },
    { id: 'cancel', label: 'Cancel', role: 'cancel' },
  ];
  return _tabCloseShowConfirm({
    body: {
      text: 'Close this running tab?',
      note: canDetach
        ? 'Keep running detaches this tab only. The command keeps running and can be reopened from Status Monitor.'
        : 'The command is still starting, so it cannot be detached yet.',
    },
    tone: 'danger',
    actions,
  }).then(result => {
    if (result === 'detach') return detachRunningTabAndClose(id);
    if (result === 'kill') return kill();
    return false;
  });
}

function closeTab(id) {
  // Closing a tab may need to preserve run state until the kill flow or output
  // persistence finishes, so final removal is sometimes deferred.
  _tabCloseCancelWelcome(id);
  const currentTabs = _tabCloseTabs();
  const idx = currentTabs.findIndex(t => t.id === id);
  _tabCloseCancelPendingOutputBatch(id);
  const closingTab = currentTabs[idx];
  if (closingTab) {
    closingTab._outputFollowToken = (closingTab._outputFollowToken || 0) + 1;
    closingTab.suppressOutputScrollTracking = false;
    closingTab.deferPromptMount = false;
  }
  if (closingTab && closingTab.st === 'running') {
    confirmCloseRunningTab(id);
    return;
  }
  if (currentTabs.length === 1) {
    // Last tab: reset to blank instead of closing
    _resetPreservedSingleTabState(currentTabs[0]);
    _tabCloseClearTab(id);
    _tabCloseSetTabLabel(id, _tabCloseDefaultTabLabel(1));
    _tabCloseSyncMountedPromptLineNumber(id);
    if (_tabCloseUseMobileTerminalViewportMode()) {
      setTimeout(() => _tabCloseBlurVisibleComposerInputIfMobile(), 0);
    }
    _tabCloseBlurActiveElement();
    _tabCloseSchedulePersistTabSessionState();
    _tabCloseEmitUiEvent('app:tab-closed', { id, activeTabId: _tabCloseActiveTabId(), preservedSingleTab: true });
    return;
  }
  _removeClosedTabView(id, idx);
}

function finalizeClosingTab(id) {
  const currentTabs = _tabCloseTabs();
  const idx = currentTabs.findIndex(t => t.id === id);
  if (idx < 0) return false;
  const tab = currentTabs[idx];
  if (!tab || !tab.closing) return false;

  if (currentTabs.length === 1) {
    _resetPreservedSingleTabState(tab);
    _tabCloseClearTab(id);
    _tabCloseSetTabLabel(id, _tabCloseDefaultTabLabel(1));
    _tabCloseSyncMountedPromptLineNumber(id);
    if (typeof document !== 'undefined'
      && document.body
      && document.body.classList
      && document.body.classList.contains('mobile-terminal-mode')) {
      setTimeout(() => _tabCloseBlurVisibleComposerInputIfMobile(), 0);
    }
    _tabCloseSchedulePersistTabSessionState();
    return true;
  }

  currentTabs.splice(idx, 1);
  _tabCloseDropAnsiRendererForTab(id);
  _tabCloseGetTabEl(id)?.remove();
  _tabCloseGetTabPanelEl(id)?.remove();
  if (_tabCloseActiveTabId() === id && currentTabs.length) {
    const nextId = _tabCloseGetNeighborTabIdAfterClose(Math.min(idx, currentTabs.length), id);
    if (nextId) _tabCloseActivateTab(nextId, { focusComposer: false });
  }
  _tabCloseUpdateNewTabBtn();
  _tabCloseUpdateTabScrollButtons();
  _tabCloseSyncRunButtonDisabled();
  _tabCloseSchedulePersistTabSessionState();
  return true;
}

if (typeof window !== 'undefined') {
}

export {
  _activateNeighborAfterClose,
  _deferRunningTabCloseForKill,
  _removeClosedTabView,
  _resetPreservedSingleTabState,
  closeTab,
  confirmCloseRunningTab,
  detachRunningTabAndClose,
  finalizeClosingTab,
};
