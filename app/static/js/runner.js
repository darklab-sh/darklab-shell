// ── Shared command execution + desktop input wrapper ──
import { DarklabRunnerCore as importedRunnerCore } from './core/runner_core.js';
import { DarklabRunOutputModel as importedRunOutputModel } from './core/run_output_model.js';
import { copyTextToClipboard as importedCopyTextToClipboard } from './core/utils.js';
import {
  cmdInput as importedCmdInput,
  mobileCmdInput as importedMobileCmdInput,
  mobileRunBtn as importedMobileRunBtn,
  runBtn as importedRunBtn,
  runTimer as importedRunTimer,
  status as importedStatus,
} from './core/dom.js';
import {
  emitUiEvent as importedEmitUiEvent,
  getActiveTab as importedGetActiveTab,
  getActiveTabId as importedGetActiveTabId,
  getAppState as importedGetAppState,
  getTab as importedGetTab,
  getTabs as importedGetTabs,
  getWelcomeState as importedGetWelcomeState,
} from './core/state.js';
import {
  apiFetch as importedApiFetch,
  describeFetchError as importedDescribeFetchError,
  getSessionId as importedGetSessionId,
  logClientError as importedLogClientError,
  maskSessionToken as importedMaskSessionToken,
  updateSessionId as importedUpdateSessionId,
} from './session.js';
import {
  appendHighVolumeOutputFinalSummary as importedAppendHighVolumeOutputFinalSummary,
  appendLine as importedAppendLine,
  appendLines as importedAppendLines,
  currentPromptWorkspacePath as importedCurrentPromptWorkspacePath,
  disableHighVolumeOutputResumeControls as importedDisableHighVolumeOutputResumeControls,
  discardPendingOutputBatch as importedDiscardPendingOutputBatch,
  _maybeMountDeferredPrompt as importedMaybeMountDeferredPrompt,
  recordLiveOutputCoalescedLines as importedRecordLiveOutputCoalescedLines,
  renderCommandOutcomeSummary as importedRenderCommandOutcomeSummary,
  resetHighVolumeOutputState as importedResetHighVolumeOutputState,
  setTabCommandOutcomeSummary as importedSetTabCommandOutcomeSummary,
} from './output.js';
import {
  activateTab as importedActivateTab,
  clearTab as importedClearTab,
  createDefaultTabLabel as importedCreateDefaultTabLabel,
  createTab as importedCreateTab,
  setTabLabel as importedSetTabLabel,
  setTabRunningCommand as importedSetTabRunningCommand,
  setTabStatus as importedSetTabStatus,
} from './tabs.js';
import {
  blurVisibleComposerInputIfMobile as importedBlurVisibleComposerInputIfMobile,
  getComposerValue as importedGetComposerValue,
  hideTabKillBtn as importedHideTabKillBtn,
  isHistoryPanelOpen as importedIsHistoryPanelOpen,
  refocusComposerAfterAction as importedRefocusComposerAfterAction,
  setComposerValue as importedSetComposerValue,
  showTabKillBtn as importedShowTabKillBtn,
  syncRunButtonDisabled as importedSyncRunButtonDisabled,
} from './ui/ui_helpers.js';
import { showConfirm as importedShowConfirm } from './ui/ui_confirm.js';
import {
  cancelWelcome as importedCancelWelcome,
  welcomeOwnsTab as importedWelcomeOwnsTab,
} from './welcome_bridge.js';
import {
  closeTab as importedCloseTab,
  finalizeClosingTab as importedFinalizeClosingTab,
} from './features/tabs/tab_close_lifecycle.js';
import {
  moveWorkspacePath as importedMoveWorkspacePath,
  openWorkspaceEditorFromCommand as importedOpenWorkspaceEditorFromCommand,
  readWorkspaceFile as importedReadWorkspaceFile,
  refreshWorkspaceFiles as importedRefreshWorkspaceFiles,
} from './workspace.js';
import {
  getWorkspaceAutocompleteDirectoryHints as importedGetWorkspaceAutocompleteDirectoryHints,
  getWorkspaceAutocompleteFileHints as importedGetWorkspaceAutocompleteFileHints,
  getWorkspaceDirectoryEntries as importedGetWorkspaceDirectoryEntries,
  refreshWorkspaceFileCache as importedRefreshWorkspaceFileCache,
} from './features/workspace/workspace_autocomplete_cache.js';
import {
  _isActiveRunDetachedForRestore as importedIsActiveRunDetachedForRestore,
  _pruneDetachedActiveRunRestoreIds as importedPruneDetachedActiveRunRestoreIds,
  clearActiveRunDetachedForRestore as importedClearActiveRunDetachedForRestore,
} from './features/runner/runner_active_restore.js';
import { createRunnerPersistence as importedCreateRunnerPersistence } from './features/runner/runner_persistence.js';
import {
  _ensureWorkspaceCache as importedEnsureWorkspaceCache,
  _isWorkspaceDeleteCommand as importedIsWorkspaceDeleteCommand,
  _isWorkspaceDownloadCommand as importedIsWorkspaceDownloadCommand,
  _isWorkspaceEditorCommand as importedIsWorkspaceEditorCommand,
  _isWorkspaceMoveCommand as importedIsWorkspaceMoveCommand,
  _isWorkspaceTerminalCommand as importedIsWorkspaceTerminalCommand,
  _resolveExistingWorkspaceCommandPath as importedResolveExistingWorkspaceCommandPath,
  _resolveWorkspaceCommandPath as importedResolveWorkspaceCommandPath,
  _setWorkspaceCwd as importedSetWorkspaceCwd,
  _workspaceCommandTokens as importedWorkspaceCommandTokens,
  _workspaceCwd as importedWorkspaceCwd,
  _workspaceDeleteCommand as importedWorkspaceDeleteCommand,
  _workspaceDisplayPath as importedWorkspaceDisplayPath,
  _workspaceDownloadTarget as importedWorkspaceDownloadTarget,
  _workspaceEditorCommand as importedWorkspaceEditorCommand,
  _workspaceExpandPathPattern as importedWorkspaceExpandPathPattern,
  _workspaceListCommand as importedWorkspaceListCommand,
  _workspaceMoveCommand as importedWorkspaceMoveCommand,
  _workspacePathExists as importedWorkspacePathExists,
  _workspacePathHasGlob as importedWorkspacePathHasGlob,
} from './features/runner/runner_workspace.js';
import {
  addToHistory as importedAddToHistory,
  addToRecentPreview as importedAddToRecentPreview,
  hydrateCmdHistory as importedHydrateCmdHistory,
} from './features/history/history_recall.js';
import { loadSessionVariables as importedLoadSessionVariables } from './features/autocomplete/runtime_context.js';
import {
  flushRecentValues as importedFlushRecentValues,
  loadRecentValues as importedLoadRecentValues,
  rememberRecentValuesFromCommand as importedRememberRecentValuesFromCommand,
} from './features/autocomplete/suggestions.js';
import {
  loadStarredFromServer as importedLoadStarredFromServer,
  reloadSessionHistory as importedReloadSessionHistory,
} from './features/history/history_actions.js';
import {
  handleConfigCommand as importedHandleConfigCommand,
  handleThemeCommand as importedHandleThemeCommand,
} from './features/terminal/local_commands.js';
import {
  activeTeamScopeCan as importedActiveTeamScopeCan,
  teamScopeDeniedMessage as importedTeamScopeDeniedMessage,
} from './features/team_scope.js';
import { handleTourCommand as importedHandleTourCommand } from './features/tour/tour_cli.js';
import {
  hasComposerPromptHandler as importedHasComposerPromptHandler,
  setComposerPromptMode as importedSetComposerPromptMode,
} from './features/terminal/composer_prompt_bridge.js';
import {
  handleWorkflowTerminalCommand as importedHandleWorkflowTerminalCommand,
  hasWorkflowHandler as importedHasWorkflowHandler,
  reloadWorkflowCatalog as importedReloadWorkflowCatalog,
} from './features/workflows/workflows_bridge.js';
import {
  handleSecretCommand as importedHandleSecretCommand,
  hasSecretsHandler as importedHasSecretsHandler,
} from './features/preferences/secrets_bridge.js';
import {
  dismissMobileKeyboardAfterSubmit as importedDismissMobileKeyboardAfterSubmit,
  hasMobileShellLayoutHandler as importedHasMobileShellLayoutHandler,
} from './features/mobile/mobile_shell_layout_bridge.js';
import { setRunnerHandlers as importedSetRunnerHandlers } from './runner_bridge.js';
import {
  hasHistoryPanelHandler as importedHasHistoryPanelHandler,
  refreshHistoryPanel as importedRefreshHistoryPanel,
} from './features/history/history_panel_bridge.js';

// If no chunk arrives from the SSE stream for 45 seconds (> 2× the 20s server heartbeat),
// verify the backend's active-run registry before changing the tab state. Tiny heartbeat
// frames can be buffered by browsers, WSGI, proxies, or Docker networking, so "quiet stream"
// is not the same thing as "dead process".
// Keyed by tabId so multiple concurrent tabs each have their own independent timer.
const _stalledTimeouts = new Map();
const _stalledRuns = new Set();
const _runStreamStateByTabId = new Map();
const _streamRecoveryTimers = new Map();
const RUNNER_GLOBAL = typeof window !== 'undefined' ? window : globalThis;
let timerStart = 0;
let timerInterval = null;

function _runnerFn(name, imported = null) {
  if (typeof imported === 'function') return imported;
  const fn = RUNNER_GLOBAL && RUNNER_GLOBAL[name];
  if (typeof fn === 'function') return fn;
  return null;
}

function _runnerValue(name, imported = undefined) {
  return imported !== undefined ? imported : (RUNNER_GLOBAL ? RUNNER_GLOBAL[name] : undefined);
}

function _runnerIgnoreFailure(value) {
  return Promise.resolve(value).catch(() => {});
}

function _runnerEl(name, imported = undefined) {
  return _runnerValue(name, imported) || null;
}

function _runnerCurrentSessionId() {
  if (typeof importedGetSessionId === 'function') return importedGetSessionId();
  return SESSION_ID || _runnerValue('SESSION_ID') || '';
}

function _runnerState() {
  const state = _runnerFn('getAppState', importedGetAppState)?.();
  return state || _runnerValue('APP_STATE') || {};
}

function _runnerActiveTabId() {
  const id = _runnerFn('getActiveTabId', importedGetActiveTabId)?.();
  return id || _runnerState().activeTabId || null;
}

function _runnerTabs() {
  const tabs = _runnerFn('getTabs', importedGetTabs)?.();
  if (Array.isArray(tabs)) return tabs;
  const state = _runnerState();
  return Array.isArray(state.tabs) ? state.tabs : [];
}

var cmdInput = _runnerEl('cmdInput', importedCmdInput);
var mobileCmdInput = _runnerEl('mobileCmdInput', importedMobileCmdInput);
var runBtn = _runnerEl('runBtn', importedRunBtn);
var runTimer = _runnerEl('runTimer', importedRunTimer);
var status = _runnerEl('status', importedStatus);
var apiFetch = (...args) => _runnerFn('apiFetch', importedApiFetch)?.(...args);
var appendLine = (...args) => _runnerFn('appendLine', importedAppendLine)?.(...args);
var appendLines = (...args) => _runnerFn('appendLines', importedAppendLines)?.(...args);
var getTab = (...args) => _runnerFn('getTab', importedGetTab)?.(...args);
var getActiveTab = (...args) => _runnerFn('getActiveTab', importedGetActiveTab)?.(...args);
var activateTab = (...args) => _runnerFn('activateTab', importedActivateTab)?.(...args);
var clearTab = (...args) => _runnerFn('clearTab', importedClearTab)?.(...args);
var createTab = (...args) => _runnerFn('createTab', importedCreateTab)?.(...args);
var createDefaultTabLabel = (...args) => _runnerFn('createDefaultTabLabel', importedCreateDefaultTabLabel)?.(...args);
var closeTab = (...args) => _runnerFn('closeTab', importedCloseTab)?.(...args);
var finalizeClosingTab = (...args) => _runnerFn('finalizeClosingTab', importedFinalizeClosingTab)?.(...args);
var setTabStatus = (...args) => _runnerFn('setTabStatus', importedSetTabStatus)?.(...args);
var setTabRunningCommand = (tabId, command) => {
  const fn = _runnerFn('setTabRunningCommand', importedSetTabRunningCommand);
  if (typeof fn === 'function') return fn(tabId, command);
  const tab = typeof getTab === 'function' ? getTab(tabId) : null;
  if (tab) tab.command = command;
  return undefined;
};
var setTabLabel = (...args) => _runnerFn('setTabLabel', importedSetTabLabel)?.(...args);
var hideTabKillBtn = (...args) => _runnerFn('hideTabKillBtn', importedHideTabKillBtn)?.(...args);
var showTabKillBtn = (...args) => _runnerFn('showTabKillBtn', importedShowTabKillBtn)?.(...args);
var emitUiEvent = (...args) => _runnerFn('emitUiEvent', importedEmitUiEvent)?.(...args);
var logClientError = (...args) => _runnerFn('logClientError', importedLogClientError)?.(...args);
var maskSessionToken = (...args) => _runnerFn('maskSessionToken', importedMaskSessionToken)?.(...args);
var updateSessionId = (...args) => {
  const fn = _runnerFn('updateSessionId', importedUpdateSessionId);
  const result = typeof fn === 'function' ? fn(...args) : undefined;
  if (typeof importedGetSessionId === 'function') SESSION_ID = importedGetSessionId();
  else if (args.length) SESSION_ID = args[0] || SESSION_ID;
  return result;
};
var describeFetchError = (...args) => _runnerFn('describeFetchError', importedDescribeFetchError)?.(...args);
var isHistoryPanelOpen = (...args) => _runnerFn('isHistoryPanelOpen', importedIsHistoryPanelOpen)?.(...args);
var refreshHistoryPanel = (...args) => {
  const bridge = (
    typeof importedHasHistoryPanelHandler === 'function'
    && importedHasHistoryPanelHandler('refreshHistoryPanel')
    && typeof importedRefreshHistoryPanel === 'function'
      ? importedRefreshHistoryPanel
      : null
  );
  return _runnerFn('refreshHistoryPanel', bridge)?.(...args);
};
var refocusComposerAfterAction = (...args) => _runnerFn('refocusComposerAfterAction', importedRefocusComposerAfterAction)?.(...args);
var setComposerValue = (...args) => _runnerFn('setComposerValue', importedSetComposerValue)?.(...args);
var getComposerValue = (...args) => _runnerFn('getComposerValue', importedGetComposerValue)?.(...args);
var blurVisibleComposerInputIfMobile = (...args) => _runnerFn('blurVisibleComposerInputIfMobile', importedBlurVisibleComposerInputIfMobile)?.(...args);
var syncRunButtonDisabled = (...args) => _runnerFn('syncRunButtonDisabled', importedSyncRunButtonDisabled)?.(...args);
var appendHighVolumeOutputFinalSummary = (...args) => _runnerFn('appendHighVolumeOutputFinalSummary', importedAppendHighVolumeOutputFinalSummary)?.(...args);
var disableHighVolumeOutputResumeControls = (...args) => _runnerFn('disableHighVolumeOutputResumeControls', importedDisableHighVolumeOutputResumeControls)?.(...args);
var discardPendingOutputBatch = (...args) => _runnerFn('discardPendingOutputBatch', importedDiscardPendingOutputBatch)?.(...args);
var recordLiveOutputCoalescedLines = (...args) => _runnerFn('recordLiveOutputCoalescedLines', importedRecordLiveOutputCoalescedLines)?.(...args);
var renderCommandOutcomeSummary = (...args) => _runnerFn('renderCommandOutcomeSummary', importedRenderCommandOutcomeSummary)?.(...args);
var resetHighVolumeOutputState = (...args) => _runnerFn('resetHighVolumeOutputState', importedResetHighVolumeOutputState)?.(...args);
var setTabCommandOutcomeSummary = (...args) => _runnerFn('setTabCommandOutcomeSummary', importedSetTabCommandOutcomeSummary)?.(...args);
var currentPromptWorkspacePath = (...args) => _runnerFn('currentPromptWorkspacePath', importedCurrentPromptWorkspacePath)?.(...args);
var addToHistory = (...args) => _runnerFn('addToHistory', importedAddToHistory)?.(...args);
var addToRecentPreview = (...args) => _runnerFn('addToRecentPreview', importedAddToRecentPreview)?.(...args);
var hydrateCmdHistory = (...args) => _runnerFn('hydrateCmdHistory', importedHydrateCmdHistory)?.(...args);
var _runnerEnsureWorkspaceCacheAdapter = (...args) => _runnerFn('_ensureWorkspaceCache', importedEnsureWorkspaceCache)?.(...args);
var _runnerIsWorkspaceDeleteCommandAdapter = (...args) => _runnerFn('_isWorkspaceDeleteCommand', importedIsWorkspaceDeleteCommand)?.(...args);
var _runnerIsWorkspaceDownloadCommandAdapter = (...args) => _runnerFn('_isWorkspaceDownloadCommand', importedIsWorkspaceDownloadCommand)?.(...args);
var _runnerIsWorkspaceEditorCommandAdapter = (...args) => _runnerFn('_isWorkspaceEditorCommand', importedIsWorkspaceEditorCommand)?.(...args);
var _runnerIsWorkspaceMoveCommandAdapter = (...args) => _runnerFn('_isWorkspaceMoveCommand', importedIsWorkspaceMoveCommand)?.(...args);
var _runnerIsWorkspaceTerminalCommandAdapter = (...args) => _runnerFn('_isWorkspaceTerminalCommand', importedIsWorkspaceTerminalCommand)?.(...args);
var _runnerResolveExistingWorkspaceCommandPathAdapter = (...args) => _runnerFn('_resolveExistingWorkspaceCommandPath', importedResolveExistingWorkspaceCommandPath)?.(...args);
var _runnerResolveWorkspaceCommandPathAdapter = (...args) => _runnerFn('_resolveWorkspaceCommandPath', importedResolveWorkspaceCommandPath)?.(...args);
var _runnerSetWorkspaceCwdAdapter = (...args) => _runnerFn('_setWorkspaceCwd', importedSetWorkspaceCwd)?.(...args);
var _runnerWorkspaceCommandTokensAdapter = (...args) => _runnerFn('_workspaceCommandTokens', importedWorkspaceCommandTokens)?.(...args);
var _runnerWorkspaceCwdAdapter = (...args) => _runnerFn('_workspaceCwd', importedWorkspaceCwd)?.(...args);
var _runnerWorkspaceDeleteCommandAdapter = (...args) => _runnerFn('_workspaceDeleteCommand', importedWorkspaceDeleteCommand)?.(...args);
var _runnerWorkspaceDisplayPathAdapter = (...args) => _runnerFn('_workspaceDisplayPath', importedWorkspaceDisplayPath)?.(...args);
var _runnerWorkspaceDownloadTargetAdapter = (...args) => _runnerFn('_workspaceDownloadTarget', importedWorkspaceDownloadTarget)?.(...args);
var _runnerWorkspaceEditorCommandAdapter = (...args) => _runnerFn('_workspaceEditorCommand', importedWorkspaceEditorCommand)?.(...args);
var _runnerWorkspaceExpandPathPatternAdapter = (...args) => _runnerFn('_workspaceExpandPathPattern', importedWorkspaceExpandPathPattern)?.(...args);
var _runnerWorkspaceListCommandAdapter = (...args) => _runnerFn('_workspaceListCommand', importedWorkspaceListCommand)?.(...args);
var _runnerWorkspaceMoveCommandAdapter = (...args) => _runnerFn('_workspaceMoveCommand', importedWorkspaceMoveCommand)?.(...args);
var _runnerWorkspacePathExistsAdapter = (...args) => _runnerFn('_workspacePathExists', importedWorkspacePathExists)?.(...args);
var _runnerWorkspacePathHasGlobAdapter = (...args) => _runnerFn('_workspacePathHasGlob', importedWorkspacePathHasGlob)?.(...args);
var _formatWorkspaceBytes = (...args) => _runnerFn('_formatWorkspaceBytes')?.(...args);
var _maybeMountDeferredPrompt = (...args) => _runnerFn('_maybeMountDeferredPrompt', importedMaybeMountDeferredPrompt)?.(...args);
var _runnerActiveTeamScopeCanAdapter = (...args) => {
  const fn = _runnerFn('activeTeamScopeCan', importedActiveTeamScopeCan);
  return typeof fn === 'function' ? fn(...args) : true;
};
var attachInteractivePtyCommand = (...args) => _runnerFn('attachInteractivePtyCommand')?.(...args);
var _runnerCopyTextToClipboardAdapter = (...args) => {
  const fn = _runnerFn('copyTextToClipboard', importedCopyTextToClipboard);
  return typeof fn === 'function' ? fn(...args) : Promise.reject(new Error('clipboard unavailable'));
};
var createWorkspaceDirectory = (...args) => _runnerFn('createWorkspaceDirectory')?.(...args);
var dismissMobileKeyboardAfterSubmit = (...args) => {
  const fn = (
    typeof importedHasMobileShellLayoutHandler === 'function'
    && importedHasMobileShellLayoutHandler('dismissMobileKeyboardAfterSubmit')
  ) ? importedDismissMobileKeyboardAfterSubmit : _runnerFn('dismissMobileKeyboardAfterSubmit');
  return typeof fn === 'function' ? fn(...args) : undefined;
};
var downloadWorkspaceFile = (...args) => _runnerFn('downloadWorkspaceFile')?.(...args);
var flushRecentValues = _runnerFn('flushRecentValues', importedFlushRecentValues);
var getRunNotifyPreference = (...args) => _runnerFn('getRunNotifyPreference')?.(...args);
var _runnerHandleConfigCommandAdapter = (...args) => {
  const fn = (typeof importedHandleConfigCommand === 'function' && importedHandleConfigCommand)
    || _runnerFn('handleConfigCommand');
  return typeof fn === 'function' ? fn(...args) : false;
};
var _runnerHandleSecretCommandAdapter = (...args) => {
  const fn = (
    typeof importedHasSecretsHandler === 'function'
    && importedHasSecretsHandler('handleSecretCommand')
    && typeof importedHandleSecretCommand === 'function'
  ) ? importedHandleSecretCommand : _runnerFn('handleSecretCommand');
  return typeof fn === 'function' ? fn(...args) : false;
};
var _runnerHandleThemeCommandAdapter = (...args) => {
  const fn = (typeof importedHandleThemeCommand === 'function' && importedHandleThemeCommand)
    || _runnerFn('handleThemeCommand');
  return typeof fn === 'function' ? fn(...args) : false;
};
var _runnerHandleTourCommandAdapter = (...args) => {
  const fn = (typeof importedHandleTourCommand === 'function' && importedHandleTourCommand)
    || _runnerFn('handleTourCommand');
  return typeof fn === 'function' ? fn(...args) : false;
};
var _runnerHandleWorkflowTerminalCommandAdapter = (...args) => {
  const fn = (typeof importedHasWorkflowHandler === 'function' && importedHasWorkflowHandler('handleWorkflowTerminalCommand'))
    ? importedHandleWorkflowTerminalCommand
    : _runnerFn('handleWorkflowTerminalCommand');
  return typeof fn === 'function' ? fn(...args) : false;
};
var hideRunTimer = (...args) => _runnerFn('hideRunTimer')?.(...args);
var isInteractivePtyCommand = (...args) => _runnerFn('isInteractivePtyCommand')?.(...args);
var isProjectWorkspaceOpen = (...args) => _runnerFn('isProjectWorkspaceOpen')?.(...args);
var isRunButtonDisabled = (...args) => _runnerFn('isRunButtonDisabled')?.(...args);
var loadRecentValues = (...args) => _runnerFn('loadRecentValues', importedLoadRecentValues)?.(...args);
var loadStarredFromServer = (...args) => _runnerFn('loadStarredFromServer', importedLoadStarredFromServer)?.(...args);
var moveWorkspacePath = (...args) => {
  const fn = (typeof importedMoveWorkspacePath === 'function' && importedMoveWorkspacePath)
    || _runnerFn('moveWorkspacePath');
  return typeof fn === 'function' ? fn(...args) : undefined;
};
var notifyProjectWorkspaceChanged = (...args) => _runnerFn('notifyProjectWorkspaceChanged')?.(...args);
var openWorkspaceEditorFromCommand = (...args) => {
  const fn = (typeof importedOpenWorkspaceEditorFromCommand === 'function' && importedOpenWorkspaceEditorFromCommand)
    || _runnerFn('openWorkspaceEditorFromCommand');
  return typeof fn === 'function' ? fn(...args) : undefined;
};
var readWorkspaceFile = (...args) => {
  const fn = (typeof importedReadWorkspaceFile === 'function' && importedReadWorkspaceFile)
    || _runnerFn('readWorkspaceFile');
  return typeof fn === 'function' ? fn(...args) : undefined;
};
var refreshActiveProjectContext = (...args) => _runnerFn('refreshActiveProjectContext')?.(...args);
var refreshProjectWorkspace = (...args) => _runnerFn('refreshProjectWorkspace')?.(...args);
var refreshWorkspaceFiles = (...args) => {
  const fn = (typeof importedRefreshWorkspaceFiles === 'function' && importedRefreshWorkspaceFiles)
    || _runnerFn('refreshWorkspaceFiles');
  return typeof fn === 'function' ? fn(...args) : undefined;
};
var reloadSessionHistory = (...args) => _runnerFn('reloadSessionHistory', importedReloadSessionHistory)?.(...args);
var reloadWorkflowCatalog = (...args) => {
  const fn = (typeof importedHasWorkflowHandler === 'function' && importedHasWorkflowHandler('reloadWorkflowCatalog'))
    ? importedReloadWorkflowCatalog
    : _runnerFn('reloadWorkflowCatalog');
  return typeof fn === 'function' ? fn(...args) : undefined;
};
var rememberRecentValuesFromCommand = (...args) => {
  const fn = _runnerFn('rememberRecentValuesFromCommand', importedRememberRecentValuesFromCommand);
  return typeof fn === 'function' ? fn(...args) : undefined;
};
var restoreHistoryRunIntoTab = (...args) => _runnerFn('restoreHistoryRunIntoTab')?.(...args);
var setComposerPromptMode = (...args) => {
  const fn = (typeof importedHasComposerPromptHandler === 'function' && importedHasComposerPromptHandler('setComposerPromptMode'))
    ? importedSetComposerPromptMode
    : _runnerFn('setComposerPromptMode');
  return typeof fn === 'function' ? fn(...args) : undefined;
};
var setRunButtonDisabled = (...args) => {
  const fn = _runnerFn('setRunButtonDisabled');
  if (typeof fn === 'function') return fn(...args);
  if (runBtn) runBtn.disabled = !!args[0];
  const mobileRunBtn = _runnerEl('mobileRunBtn', importedMobileRunBtn);
  if (mobileRunBtn) mobileRunBtn.disabled = !!args[0];
  return undefined;
};
var showConfirm = (...args) => _runnerFn('showConfirm', importedShowConfirm)?.(...args);
var showRunTimer = (...args) => _runnerFn('showRunTimer')?.(...args);
var showToast = (...args) => _runnerFn('showToast')?.(...args);
var startInteractivePtyCommand = (...args) => _runnerFn('startInteractivePtyCommand')?.(...args);
var _runnerTeamScopeDeniedMessageAdapter = (...args) => {
  const fn = _runnerFn('teamScopeDeniedMessage', importedTeamScopeDeniedMessage);
  return typeof fn === 'function'
    ? fn(...args)
    : `View-only team members can't ${args[0] || 'run commands in team scope'}. Switch to Personal or ask for operator access.`;
};
var _runnerWorkspaceCanWriteAdapter = (...args) => {
  const fn = _runnerFn('workspaceCanWrite');
  return typeof fn === 'function' ? fn(...args) : true;
};
var acSpecialCommands = _runnerValue('acSpecialCommands') || {};
var pendingKillTabId = _runnerValue('pendingKillTabId') || null;
var APP_CONFIG = _runnerValue('APP_CONFIG') || {};
var CLIENT_ID = _runnerValue('CLIENT_ID') || '';
var SESSION_ID = (typeof importedGetSessionId === 'function' && importedGetSessionId())
  || _runnerValue('SESSION_ID')
  || '';
function _runnerCore() {
  return (typeof importedRunnerCore !== 'undefined' && importedRunnerCore)
    || null;
}
function _welcomeApi(name) {
  if (name === 'cancelWelcome' && typeof importedCancelWelcome === 'function') return importedCancelWelcome;
  if (name === 'welcomeOwnsTab' && typeof importedWelcomeOwnsTab === 'function') return importedWelcomeOwnsTab;
  return (typeof window !== 'undefined' && window[name])
    || (typeof globalThis !== 'undefined' && globalThis[name])
    || null;
}

function _isWelcomeActive() {
  const welcomeState = _runnerFn('getWelcomeState', importedGetWelcomeState)?.();
  return !!((_runnerValue('_welcomeActive'))
    || (welcomeState && welcomeState.active));
}

function _isWelcomeDone() {
  const welcomeState = _runnerFn('getWelcomeState', importedGetWelcomeState)?.();
  return !!((_runnerValue('_welcomeDone'))
    || (welcomeState && welcomeState.done));
}

function _welcomeOwns(tabId) {
  const owns = _welcomeApi('welcomeOwnsTab');
  return typeof owns === 'function' && owns(tabId);
}

function _cancelWelcome(tabId) {
  const cancel = _welcomeApi('cancelWelcome');
  if (typeof cancel === 'function') cancel(tabId);
}

function _requestWelcomeSettle(tabId) {
  const settle = _welcomeApi('requestWelcomeSettle');
  return typeof settle === 'function' ? settle(tabId) : false;
}
const _RUN_STREAM_MESSAGE_BATCH_LIMIT = 750;
const _RUN_STREAM_MESSAGE_BATCH_MS = 12;
let _runnerPersistence = null;
let _activeRunPollTimer = null;

function _runnerWorkspaceCacheApi() {
  return {
    getDirectoryEntries: (typeof importedGetWorkspaceDirectoryEntries !== 'undefined' && importedGetWorkspaceDirectoryEntries) || null,
    getDirectoryHints: (typeof importedGetWorkspaceAutocompleteDirectoryHints !== 'undefined' && importedGetWorkspaceAutocompleteDirectoryHints) || null,
    getFileHints: (typeof importedGetWorkspaceAutocompleteFileHints !== 'undefined' && importedGetWorkspaceAutocompleteFileHints) || null,
    refresh: (typeof importedRefreshWorkspaceFileCache !== 'undefined' && importedRefreshWorkspaceFileCache) || null,
  };
}

// Pending terminal confirmation: used by transcript-owned yes/no flows such as
// session-token migration and token-clear confirmation. While set, the next
// typed answer is consumed as part of the active script-style prompt instead of
// as a normal shell command.
let _pendingTerminalConfirm = null;

function _runnerPersistenceHelpers() {
  if (!_runnerPersistence) {
    const createPersistence = (typeof importedCreateRunnerPersistence !== 'undefined' && importedCreateRunnerPersistence)
      || null;
    if (typeof createPersistence !== 'function') {
      throw new Error('DarklabRunnerPersistence is unavailable');
    }
    _runnerPersistence = createPersistence({
      apiFetch,
      maskSessionToken,
      isHistoryPanelOpen: typeof isHistoryPanelOpen === 'function' ? isHistoryPanelOpen : null,
      refreshHistoryPanel: typeof refreshHistoryPanel === 'function' ? refreshHistoryPanel : null,
      logClientError: typeof logClientError === 'function' ? logClientError : null,
    });
  }
  return _runnerPersistence;
}

function _runnerIsActiveRunDetachedForRestore(runId) {
  const isDetached = (typeof importedIsActiveRunDetachedForRestore !== 'undefined' && importedIsActiveRunDetachedForRestore)
    || null;
  return typeof isDetached === 'function' ? isDetached(runId) : false;
}

function _runnerPruneDetachedActiveRunRestoreIds(activeRunIds) {
  const prune = (
    typeof importedPruneDetachedActiveRunRestoreIds !== 'undefined'
    && importedPruneDetachedActiveRunRestoreIds
  ) || null;
  if (typeof prune === 'function') prune(activeRunIds);
}

function _runnerClearActiveRunDetachedForRestore(runId) {
  const clear = (
    typeof importedClearActiveRunDetachedForRestore !== 'undefined'
    && importedClearActiveRunDetachedForRestore
  ) || null;
  if (typeof clear === 'function') clear(runId);
}

function _resetStalledTimeout(tabId) {
  clearTimeout(_stalledTimeouts.get(tabId));
  _stalledTimeouts.set(tabId, setTimeout(() => {
    const t = getTab(tabId);
    if (!t || t.killed) return;  // already handled
    const runGeneration = _tabRunGeneration(tabId);
    if (!runGeneration) return;
    _isRunStillActive(runGeneration).then(active => {
      const latest = getTab(tabId);
      if (!latest || latest.killed || _tabRunGeneration(tabId) !== runGeneration) return;
      if (active) {
        _markStalledButRunning(tabId);
        _resetStalledTimeout(tabId);
        return;
      }
      _markStalledAndInactive(tabId);
    });
  }, 45000));
}

function _clearStalledTimeout(tabId) {
  clearTimeout(_stalledTimeouts.get(tabId));
  _stalledTimeouts.delete(tabId);
  _stalledRuns.delete(tabId);
}

function _clearStreamRecoveryTimer(tabId) {
  clearTimeout(_streamRecoveryTimers.get(tabId));
  _streamRecoveryTimers.delete(tabId);
}

function _recoverStalledRun(tabId) {
  if (!_stalledRuns.has(tabId)) return;
  _stalledRuns.delete(tabId);
  appendLine('[connection re-established — live output resumed]', 'exit-ok', tabId);
  const t = getTab(tabId);
  if (!t || t.killed) return;
  if (tabId === _runnerActiveTabId()) {
    setStatus('running');
    syncActiveRunTimer(tabId);
  }
  setTabStatus(tabId, 'running');
  _setRunButtonDisabled(true);
  showTabKillBtn(tabId);
}

function _tabRunGeneration(tabId) {
  const t = getTab(tabId);
  return t && (t.runId || t.historyRunId) || '';
}

function _isRunStillActive(runId) {
  if (!runId || typeof apiFetch !== 'function') return Promise.resolve(false);
  return _fetchActiveRun(runId).then(Boolean);
}

function _activeRunsUrl({ includeScheduled = false } = {}) {
  return includeScheduled ? '/history/active?include_scheduled=1' : '/history/active';
}

function _fetchActiveRun(runId, { includeScheduled = false } = {}) {
  if (!runId || typeof apiFetch !== 'function') return Promise.resolve(null);
  return apiFetch(_activeRunsUrl({ includeScheduled }))
    .then(r => (r && r.ok !== false && typeof r.json === 'function') ? r.json() : null)
    .then(data => {
      const normalized = String(runId || '');
      return (Array.isArray(data && data.runs) ? data.runs : [])
        .find(run => String(run && run.run_id || '') === normalized) || null;
    })
    .catch(err => {
      _logRunnerError('active run stall check failed', err);
      return null;
    });
}

function _markStalledButRunning(tabId) {
  const firstNotice = !_stalledRuns.has(tabId);
  _stalledRuns.add(tabId);
  if (firstNotice) {
    appendLine('[stream quiet — no output or heartbeat reached the browser for 45s]', 'notice', tabId);
    appendLine('[process is still running; Kill remains available and live output will continue here if the stream resumes]', 'notice', tabId);
  }
  if (tabId === _runnerActiveTabId()) {
    setStatus('running');
    syncActiveRunTimer(tabId);
  }
  setTabStatus(tabId, 'running');
  _setRunButtonDisabled(true);
  const t = getTab(tabId);
  if (t) showTabKillBtn(tabId);
}

function _markStalledAndInactive(tabId) {
  const firstNotice = !_stalledRuns.has(tabId);
  _stalledRuns.add(tabId);
  if (firstNotice) {
    appendLine('[connection stalled — no stream activity arrived from the server for 45s]', 'denied', tabId);
  }
  appendLine('[process is no longer listed as active; check the history panel for the final result]', 'denied', tabId);
  if (tabId === _runnerActiveTabId()) setStatus('fail');
  setTabStatus(tabId, 'fail');
  stopTimer(); _setRunButtonDisabled(false); hideTabKillBtn(tabId);
}

function _handleStreamEndedWithoutExit(tabId) {
  _clearStalledTimeout(tabId);
  const runId = _tabRunGeneration(tabId);
  const existingTab = getTab(tabId);
  const includeScheduled = !!(existingTab && existingTab.scheduledRun);
  return _fetchActiveRun(runId, { includeScheduled }).then(activeRun => {
    const t = getTab(tabId);
    if (!t || t.killed) return;
    if (activeRun) {
      if (_activeRunIsInteractivePty(activeRun)) {
        if (typeof attachInteractivePtyCommand === 'function') {
          attachInteractivePtyCommand(activeRun, tabId).catch(err => {
            appendLine(`[server error] ${err.message || 'Interactive PTY reattach failed'}`, 'exit-fail', tabId);
            setTabStatus(tabId, 'fail');
          });
        }
        return;
      }
      _scheduleActiveRunStreamRecovery(activeRun, tabId, {
        after: t.lastEventId || activeRun.last_event_id || '',
        mode: t.attachMode || 'reconnected',
      });
      return;
    }
    _clearStreamRecoveryTimer(tabId);
    t.streamRecoveryAttempts = 0;
    stopTimer(); _setRunButtonDisabled(false); hideTabKillBtn(tabId);
  });
}

function _scheduleActiveRunStreamRecovery(run, tabId, { after = '', mode = 'reconnected' } = {}) {
  const t = getTab(tabId);
  if (!t || !run || !run.run_id) return false;
  if (_streamRecoveryTimers.has(tabId)) return true;
  const attempts = Number(t.streamRecoveryAttempts || 0) + 1;
  t.streamRecoveryAttempts = attempts;
  const recover = () => {
    _streamRecoveryTimers.delete(tabId);
    const latest = getTab(tabId);
    if (!latest || latest.killed || _tabRunGeneration(tabId) !== String(run.run_id || '')) return;
    _reattachActiveRunToTab(run, tabId, {
      after: latest.lastEventId || after || run.last_event_id || '',
      afterStreamRecovery: true,
      mode,
      preserveTranscript: true,
    });
  };
  if (attempts <= 1) {
    recover();
    return true;
  }
  const delayMs = Math.min(1000 * (2 ** Math.max(0, attempts - 2)), 5000);
  _streamRecoveryTimers.set(tabId, setTimeout(recover, delayMs));
  return true;
}

function _shouldSuppressStreamOutputLine(tab, line) {
  if (!tab || typeof line !== 'string') return false;
  const root = String(tab.command || '').trim().split(/\s+/, 1)[0].toLowerCase();
  if (root !== 'nc') return false;
  return /^Warning: inverse host lookup failed for /i.test(line);
}

// ── Status pill ──
// The HUD STATUS pill is a binary running-or-not indicator; the outcome of
// the last run (exit code, killed) is surfaced by the adjacent LAST EXIT
// pill, so the text only ever reads RUNNING or IDLE. The class name still
// tracks the underlying state (ok/fail/killed/idle/running) so existing CSS
// and test assertions that key off the pill's class keep working.
//
// setStatus also mirrors terminal states into the LAST EXIT pill so synthetic
// failures (denied, rate-limited, transport errors) surface there without
// every caller having to wire the two pills up separately. Callers that have
// a real exit code (the SSE exit handler, kill) override afterwards.
function setStatus(s) {
  status.className = 'status-pill ' + s;
  status.textContent = s === 'running' ? 'RUNNING' : 'IDLE';
  if (typeof emitUiEvent === 'function') {
    emitUiEvent('app:status-changed', { status: s });
    if (s === 'ok') emitUiEvent('app:last-exit-changed', { value: 0 });
    else if (s === 'fail') emitUiEvent('app:last-exit-changed', { value: 1 });
    else if (s === 'killed') emitUiEvent('app:last-exit-changed', { value: 'killed' });
  }
}

function setLastExit(value) {
  if (typeof emitUiEvent === 'function') emitUiEvent('app:last-exit-changed', { value });
  if (typeof importedEmitUiEvent === 'function' && importedEmitUiEvent !== emitUiEvent) {
    importedEmitUiEvent('app:last-exit-changed', { value });
  }
}

// ── Run notifications ──

function _maybeNotify(command, codeOrStatus, elapsed) {
  if (typeof getRunNotifyPreference !== 'function' || getRunNotifyPreference() !== 'on') return;
  if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return;
  // Use only the command root (first word) so arguments — which may contain
  // bearer tokens, API keys, auth headers, or sensitive targets — are never
  // surfaced in OS notifications or on the lock screen.
  const root = (command || '').split(/\s+/)[0] || '';
  const title = root ? '$ ' + root : '$';
  const body = codeOrStatus === 'killed'
    ? (elapsed ? `killed after ${elapsed}` : 'killed')
    : (elapsed ? `exit ${codeOrStatus} in ${elapsed}` : `exit ${codeOrStatus}`);
  try { new Notification(title, { body }); } catch(e) {}
}

// ── Run timer ──

function _formatElapsed(totalSecs) {
  return _runnerCore().formatElapsed(totalSecs);
}

function startTimer(startMs = Date.now()) {
  timerStart = startMs;
  showRunTimer();
  timerInterval = setInterval(() => {
    runTimer.textContent = _formatElapsed((Date.now() - timerStart) / 1000);
  }, 100);
}

function stopTimer() {
  clearInterval(timerInterval);
  timerInterval = null;
  hideRunTimer();
}

function syncActiveRunTimer(tabId = _runnerActiveTabId()) {
  const t = getTab(tabId);
  if (!t || t.st !== 'running' || !t.runStart) {
    stopTimer();
    return;
  }
  startTimer(t.runStart);
}

function _activeReconnectTabs() {
  return _runnerTabs().filter(t => t && t.st === 'running' && t.reconnectedRun && t.historyRunId);
}

function _shouldAutoRestoreActiveRun(run) {
  if (!run || typeof run !== 'object') return false;
  if (run.scheduled) return false;
  if (_runnerIsActiveRunDetachedForRestore(run.run_id)) return false;
  if (_activeRunIsInteractivePty(run) && typeof attachInteractivePtyCommand !== 'function') return false;
  if (run.owned_by_this_client) return true;
  if (run.owner_stale) return true;
  return !run.has_live_owner;
}

function _activeRunIsInteractivePty(run) {
  if (!run || typeof run !== 'object') return false;
  return run.run_type === 'pty' || run.interactive === true;
}

function _startedAtLabel(started) {
  const startedAt = new Date(started);
  return Number.isNaN(startedAt.getTime())
    ? 'unknown start time'
    : startedAt.toLocaleString();
}

function _activeRunTabForRestore(run) {
  const runId = String(run && run.run_id || '');
  if (!runId || !Array.isArray(_runnerTabs())) return null;
  const byRunId = _tabForActiveRunId(runId);
  if (byRunId) return byRunId;
  const ownerTabId = String(run && run.owner_tab_id || '');
  if (run && run.owned_by_this_client && ownerTabId) {
    return _runnerTabs().find(tab => tab && tab.id === ownerTabId) || null;
  }
  return null;
}

function _activeRunReattachNotice(run, { afterStreamRecovery = false } = {}) {
  const startedLabel = _startedAtLabel(run && run.started);
  return [
    afterStreamRecovery
      ? '[reattached to active run after stream recovery]'
      : '[reattached to active run after reload]',
    `[active run started at ${startedLabel}]`,
    '[live output will continue here]',
  ];
}

function _reattachActiveRunToTab(
  run,
  tabId,
  {
    after = '',
    afterStreamRecovery = false,
    mode = 'reconnected',
    preserveTranscript = false,
  } = {},
) {
  if (!run || !tabId) return false;
  if (!preserveTranscript) clearTab(tabId);
  const t = getTab(tabId);
  if (!t) return false;
  if (typeof setTabRunningCommand === 'function') {
    setTabRunningCommand(tabId, run.command);
  } else {
    if (!t.renamed) setTabLabel(tabId, run.command);
    t.command = run.command;
  }
  const runId = String(run.run_id || '');
  t.runId = runId;
  t.historyRunId = runId;
  t.scheduledRun = !!run.scheduled;
  t.scheduleId = String(run.schedule_id || '');
  t.reconnectedRun = true;
  t.attachMode = mode;
  t.killed = false;
  t.pendingKill = false;
  t.previewTruncated = false;
  t.fullOutputAvailable = false;
  t.fullOutputLoaded = false;
  t.runStart = Number.isNaN(Date.parse(run.started)) ? Date.now() : Date.parse(run.started);
  t.currentRunStartIndex = Number.isFinite(Number(t.currentRunStartIndex))
    ? Number(t.currentRunStartIndex)
    : (Array.isArray(t.rawLines) ? t.rawLines.length : 0);
  t.followOutput = true;
  const resumeAfter = String(after || t.lastEventId || run.last_event_id || '');
  if (!resumeAfter) t.lastEventId = '';
  if (!preserveTranscript || !Array.isArray(t.rawLines) || t.rawLines.length === 0) {
    appendCommandEcho(run.command, tabId);
  }
  const streamRecoveryNoticeShown = afterStreamRecovery && t.streamRecoveryNoticeRunId === runId;
  if (!streamRecoveryNoticeShown) {
    _activeRunReattachNotice(run, { afterStreamRecovery }).forEach(line => appendLine(line, 'notice', tabId));
  }
  if (afterStreamRecovery) t.streamRecoveryNoticeRunId = runId;
  setTabStatus(tabId, 'running');
  if (tabId === _runnerActiveTabId()) {
    setStatus('running');
    syncActiveRunTimer(tabId);
  }
  showTabKillBtn(tabId);
  _setRunButtonDisabled(true);
  _subscribeRunStream(runId, tabId, { after: resumeAfter });
  startPollingActiveRunsAfterReload();
  return true;
}

function restoreActiveRunsAfterReload(runs) {
  _runnerPruneDetachedActiveRunRestoreIds(new Set((Array.isArray(runs) ? runs : [])
    .map(run => run && run.run_id)
    .filter(Boolean)));
  const items = (Array.isArray(runs) ? runs : []).filter(_shouldAutoRestoreActiveRun);
  if (!items.length) {
    stopPollingActiveRunsAfterReload();
    return false;
  }

  let firstRestoredTabId = null;
  items.forEach((run, index) => {
    const originalTab = _activeRunTabForRestore(run);
    if (originalTab) {
      if (!firstRestoredTabId) firstRestoredTabId = originalTab.id;
      if (_activeRunIsInteractivePty(run) && typeof attachInteractivePtyCommand === 'function') {
        attachInteractivePtyCommand(run, originalTab.id).catch(err => {
          appendLine(`[server error] ${err.message || 'Interactive PTY reattach failed'}`, 'exit-fail', originalTab.id);
          setTabStatus(originalTab.id, 'fail');
        });
        return;
      }
      _reattachActiveRunToTab(run, originalTab.id, {
        after: originalTab.lastEventId || run.last_event_id || '',
        mode: originalTab.attachMode || 'reconnected',
        preserveTranscript: true,
      });
      return;
    }
    const bootstrapTab = index === 0 && _runnerTabs().length === 1 ? _runnerTabs()[0] : null;
    const canReuseBootstrapTab = !!(bootstrapTab
      && bootstrapTab.st === 'idle'
      && !bootstrapTab.renamed
      && !bootstrapTab.command
      && !bootstrapTab.historyRunId
      && !bootstrapTab.draftInput
      && Array.isArray(bootstrapTab.rawLines)
      && bootstrapTab.rawLines.length === 0);
    const tabId = canReuseBootstrapTab ? bootstrapTab.id : createTab();
    if (!tabId) return;
    if (!firstRestoredTabId) firstRestoredTabId = tabId;
    if (_activeRunIsInteractivePty(run) && typeof attachInteractivePtyCommand === 'function') {
      attachInteractivePtyCommand(run, tabId).catch(err => {
        appendLine(`[server error] ${err.message || 'Interactive PTY reattach failed'}`, 'exit-fail', tabId);
        setTabStatus(tabId, 'fail');
      });
      return;
    }
    _reattachActiveRunToTab(run, tabId, {
      after: run.last_event_id || '',
      mode: 'reconnected',
      preserveTranscript: false,
    });
  });

  if (!firstRestoredTabId) {
    stopPollingActiveRunsAfterReload();
    return false;
  }
  activateTab(firstRestoredTabId);
  syncActiveRunTimer(_runnerActiveTabId());
  return true;
}

function _attachActiveRunToTab(run, tabId, { mode = 'attached' } = {}) {
  if (!run || !tabId) return false;
  _runnerClearActiveRunDetachedForRestore(run.run_id);
  clearTab(tabId);
  const t = getTab(tabId);
  if (!t) return false;
  if (typeof setTabRunningCommand === 'function') {
    setTabRunningCommand(tabId, run.command);
  } else {
    if (!t.renamed) setTabLabel(tabId, run.command);
    t.command = run.command;
  }
  t.runId = run.run_id;
  t.historyRunId = run.run_id;
  t.scheduledRun = !!run.scheduled;
  t.scheduleId = String(run.schedule_id || '');
  t.lastEventId = '';
  t.attachMode = mode;
  t.reconnectedRun = true;
  t.killed = false;
  t.pendingKill = false;
  t.previewTruncated = false;
  t.fullOutputAvailable = false;
  t.fullOutputLoaded = false;
  t.runStart = Number.isNaN(Date.parse(run.started)) ? Date.now() : Date.parse(run.started);
  t.currentRunStartIndex = 0;
  t.followOutput = true;
  appendCommandEcho(run.command, tabId);
  const startedLabel = _startedAtLabel(run.started);
  appendLine(
    `[attached to active run started at ${startedLabel}]`,
    'notice',
    tabId,
  );
  appendLine('[restored available output; live output will continue here]', 'notice', tabId);
  setTabStatus(tabId, 'running');
  if (tabId === _runnerActiveTabId()) {
    setStatus('running');
    syncActiveRunTimer(tabId);
  }
  showTabKillBtn(tabId);
  _setRunButtonDisabled(true);
  _subscribeRunStream(run.run_id, tabId, { after: run.last_event_id || '' });
  return true;
}

function attachActiveRunFromMonitor(run) {
  if (!run || !run.run_id) return Promise.resolve(false);
  if (run.run_type === 'pty') {
    if (typeof attachInteractivePtyCommand !== 'function') return Promise.resolve(false);
    return attachInteractivePtyCommand(run);
  }
  const tabId = createTab();
  if (!tabId) return Promise.resolve(false);
  activateTab(tabId, { focusComposer: false });
  return Promise.resolve(_attachActiveRunToTab(run, tabId, { mode: 'attached' }));
}

function _tabForActiveRunId(runId) {
  const normalized = String(runId || '');
  if (!normalized || !Array.isArray(_runnerTabs())) return null;
  return _runnerTabs().find(tab => (
    tab && (tab.runId === normalized || tab.historyRunId === normalized)
  )) || null;
}

function _requestKillActiveRun(run, tabId = '') {
  const runId = String(run?.run_id || run?.id || '').trim();
  if (!runId || typeof apiFetch !== 'function') return Promise.resolve(false);
  return apiFetch('/kill', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ run_id: runId, tab_id: tabId }),
  }).then(resp => {
    if (resp && resp.ok) return true;
    return _readRunErrorMessage(resp || {}).then(message => {
      throw new Error(message || 'Could not kill this run.');
    });
  });
}

function killActiveRunFromMonitor(run) {
  const runId = String(run?.run_id || run?.id || '').trim();
  if (!runId) return Promise.resolve(false);
  const tab = _tabForActiveRunId(runId);
  const kill = () => {
    if (tab && tab.st === 'running') {
      doKill(tab.id);
      return Promise.resolve(true);
    }
    return _requestKillActiveRun(run, '');
  };
  if (typeof showConfirm !== 'function') return kill();
  return showConfirm({
    body: {
      text: 'Kill this active run?',
      note: 'This sends SIGTERM to the running process group. Other attached tabs will be notified.',
    },
    tone: 'danger',
    actions: [
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      { id: 'kill', label: 'Kill run', role: 'destructive' },
    ],
  }).then(result => (result === 'kill' ? kill() : false));
}

function _restoreCompletedReconnectedRun(tab, run) {
  const restore = (typeof window !== 'undefined' && window.restoreHistoryRunIntoTab)
    || (typeof globalThis !== 'undefined' && globalThis.restoreHistoryRunIntoTab)
    || (typeof restoreHistoryRunIntoTab !== 'undefined' ? restoreHistoryRunIntoTab : null);
  if (!tab || !run || typeof restore !== 'function') return Promise.resolve();
  return restore(run, { targetTabId: tab.id, hidePanelOnSuccess: false })
    .then(() => {
      const refreshed = getTab(tab.id);
      if (refreshed) refreshed.reconnectedRun = false;
      if (tab.id === _runnerActiveTabId()) stopTimer();
    })
    .catch(() => {
      appendLine('[reconnected run finished, but the saved result could not be restored automatically]', 'notice', tab.id);
      appendLine('[open the history panel to load the completed run]', 'notice', tab.id);
      setTabStatus(tab.id, 'fail');
      const refreshed = getTab(tab.id);
      if (refreshed) refreshed.reconnectedRun = false;
      if (tab.id === _runnerActiveTabId()) stopTimer();
    });
}

function _markReconnectedRunUnavailable(tab) {
  if (!tab) return;
  appendLine('[reconnected run is no longer active]', 'denied', tab.id);
  appendLine('[no saved result is available; the app may have restarted while the command was running]', 'denied', tab.id);
  setTabStatus(tab.id, 'fail');
  const refreshed = getTab(tab.id);
  if (refreshed) {
    refreshed.reconnectedRun = false;
    refreshed.runId = null;
  }
  if (tab.id === _runnerActiveTabId()) {
    setStatus('fail');
    stopTimer();
  }
  _setRunButtonDisabled(false);
  hideTabKillBtn(tab.id);
}

function pollActiveRunsAfterReload() {
  const reconnectTabs = _activeReconnectTabs();
  if (!reconnectTabs.length) {
    stopPollingActiveRunsAfterReload();
    return Promise.resolve();
  }

  return apiFetch('/history/active')
    .then(r => r.json())
    .then(data => {
      const activeIds = new Set((Array.isArray(data.runs) ? data.runs : []).map(run => run.run_id));
      return Promise.all(reconnectTabs.map(tab => {
        if (activeIds.has(tab.historyRunId)) return Promise.resolve();
        return apiFetch(`/history/${tab.historyRunId}?json&preview=1`)
          .then(r => r.ok ? r.json() : Promise.reject(new Error('run not ready')))
          .then(run => _restoreCompletedReconnectedRun(tab, run))
          .catch(() => _markReconnectedRunUnavailable(tab));
      }));
    })
    .finally(() => {
      if (!_activeReconnectTabs().length) stopPollingActiveRunsAfterReload();
    });
}

function startPollingActiveRunsAfterReload() {
  if (_activeRunPollTimer || !_activeReconnectTabs().length) return;
  _activeRunPollTimer = setInterval(() => {
    pollActiveRunsAfterReload().catch(err => _logRunnerError('active run reconnect poll failed', err));
  }, 5000);
}

function stopPollingActiveRunsAfterReload() {
  clearInterval(_activeRunPollTimer);
  _activeRunPollTimer = null;
}

function elapsedSeconds() {
  return timerStart ? (Date.now() - timerStart) / 1000 : null;
}

function _setRunButtonDisabled(disabled) {
  if (disabled) {
    if (runBtn) runBtn.disabled = true;
    const mobileRunBtn = _runnerEl('mobileRunBtn', importedMobileRunBtn);
    if (mobileRunBtn) mobileRunBtn.disabled = true;
  }
  if (disabled && typeof setRunButtonDisabled === 'function') {
    setRunButtonDisabled(disabled);
    return;
  }
  if (typeof setRunButtonDisabled === 'function') {
    setRunButtonDisabled(false);
    return;
  }
  if (runBtn) runBtn.disabled = false;
  const mobileRunBtn = _runnerEl('mobileRunBtn', importedMobileRunBtn);
  if (mobileRunBtn) mobileRunBtn.disabled = false;
}

function _syncMobileRunButtonAfterRunSettled() {
  if (typeof document === 'undefined' || !document.body?.classList?.contains('mobile-terminal-mode')) return;
  const mobileRunBtn = _runnerEl('mobileRunBtn', importedMobileRunBtn);
  const mobileCmd = _runnerEl('mobileCmdInput', importedMobileCmdInput);
  if (!mobileRunBtn || !mobileCmd) return;
  if (typeof syncRunButtonDisabled === 'function') {
    syncRunButtonDisabled();
    return;
  }
  mobileRunBtn.disabled = !String(mobileCmd.value || '').trim();
}

function _describeRunnerFetchError(err, context = 'server') {
  return describeFetchError(err, context);
}

function _logRunnerError(context, err, details = null) {
  logClientError(context, err, details);
}

function _logRunStreamCancelFailure(err, tabId, runId, operation) {
  _logRunnerError('run stream reader cancel failed', err, {
    event: 'RUN_STREAM_READER_CANCEL_FAILED',
    level: 'warning',
    tab_id: String(tabId || ''),
    run_id: String(runId || ''),
    operation,
  });
}

function _logRunStreamLifecycle(event, tabId, runId, operation) {
  _logRunnerError('run stream lifecycle', null, {
    event,
    level: 'debug',
    tab_id: String(tabId || ''),
    run_id: String(runId || ''),
    operation,
  });
}

function _handleKillRequestFailure(err, tabId) {
  _logRunnerError('kill request failed', err);
  showToast('Failed to send kill request; command may still be running');
  appendLine('[kill request failed] ' + _describeRunnerFetchError(err), 'notice', tabId);
}

function _handleKillRequestDenied(message, tabId, runId) {
  const t = getTab(tabId);
  if (t) {
    t.runId = runId || t.runId;
    t.killed = false;
    t.pendingKill = false;
    setTabStatus(tabId, 'running');
    showTabKillBtn(tabId);
  }
  appendLine(`[kill request denied] ${message || 'The server could not kill this run.'}`, 'notice', tabId);
  if (tabId === _runnerActiveTabId()) {
    setStatus('running');
    _setRunButtonDisabled(true);
  }
}

function _currentClientId() {
  return typeof CLIENT_ID !== 'undefined' ? String(CLIENT_ID || '') : '';
}

function _handleRunOwnerChanged(msg, tabId) {
  const t = getTab(tabId);
  if (!t) return;
  const ownerClientId = String(msg.owner_client_id || '');
  const ownedByThisClient = !!(ownerClientId && ownerClientId === _currentClientId());
  if (ownedByThisClient) {
    t.attachMode = t.attachMode || 'origin';
    if (t.st === 'running') showTabKillBtn(tabId);
    return;
  }
  t.attachMode = t.attachMode || 'attached';
  t.killed = false;
  t.pendingKill = false;
  if (t.st === 'running') showTabKillBtn(tabId);
}

function _handleRunKilled(msg, tabId) {
  const t = getTab(tabId);
  if (!t) return;
  const killerClientId = String(msg.killer_client_id || '');
  const killerTabId = String(msg.killer_tab_id || '');
  const killedByThisBrowser = !!(killerClientId && killerClientId === _currentClientId());
  const killedByThisTab = killedByThisBrowser && killerTabId && killerTabId === tabId;
  t.killed = true;
  t.pendingKill = false;
  if (typeof discardPendingOutputBatch === 'function') discardPendingOutputBatch(tabId);
  if (!killedByThisTab) {
    appendLine(
      killedByThisBrowser ? '[killed from another tab]' : '[killed by another browser]',
      'notice',
      tabId,
    );
  }
  setTabStatus(tabId, 'killed');
  if (typeof disableHighVolumeOutputResumeControls === 'function') {
    disableHighVolumeOutputResumeControls(tabId);
  }
  hideTabKillBtn(tabId);
  if (tabId === _runnerActiveTabId()) {
    setStatus('killed');
    _setRunButtonDisabled(false);
  }
}

function _markTabKilledByUser(tabId, secs, { suppressTranscript = false } = {}) {
  const t = getTab(tabId);
  if (!t) return;
  _clearStreamRecoveryTimer(tabId);
  t.killed = true;
  t.reconnectedRun = false;
  t.lastEventId = '';
  t.attachMode = '';
  t.streamRecoveryAttempts = 0;
  t.streamRecoveryNoticeRunId = '';
  stopTimer();
  if (typeof discardPendingOutputBatch === 'function') discardPendingOutputBatch(tabId);
  if (!t.closing && !suppressTranscript) {
    appendLine(`[killed by user${secs != null ? ' after ' + _formatElapsed(secs) : ''}]`, 'exit-fail', tabId);
  }
  _maybeNotify(t.command, 'killed', secs != null ? _formatElapsed(secs) : null);
  if (typeof emitUiEvent === 'function') emitUiEvent('app:last-exit-changed', { value: 'killed' });
  setTabStatus(tabId, 'killed');
  if (typeof disableHighVolumeOutputResumeControls === 'function') {
    disableHighVolumeOutputResumeControls(tabId);
  }
  hideTabKillBtn(tabId);
  if (tabId === _runnerActiveTabId()) {
    setStatus('killed');
    _setRunButtonDisabled(false);
  }
  if (typeof _maybeMountDeferredPrompt === 'function') {
    _maybeMountDeferredPrompt(tabId);
  }
}

function _handleRunTransportFailure(err, tabId) {
  _logRunnerError('run request failed', err);
  appendLine('[connection error] ' + _describeRunnerFetchError(err), 'exit-fail', tabId);
  if (tabId === _runnerActiveTabId()) setStatus('fail');
  setTabStatus(tabId, 'fail');
  if (typeof disableHighVolumeOutputResumeControls === 'function') {
    disableHighVolumeOutputResumeControls(tabId);
  }
  stopTimer(); _setRunButtonDisabled(false); hideTabKillBtn(tabId);
}

function _appendHighVolumeOutputFinalSummary(tabId) {
  if (typeof appendHighVolumeOutputFinalSummary === 'function') {
    appendHighVolumeOutputFinalSummary(tabId);
  }
}

async function _readRunErrorMessage(res) {
  const contentType = (res.headers && typeof res.headers.get === 'function' && res.headers.get('content-type')) || '';
  try {
    if (contentType.includes('application/json') && typeof res.json === 'function') {
      const data = await res.json();
      if (data && typeof data.message === 'string' && data.message.trim()) return data.message.trim();
      if (data && typeof data.error === 'string' && data.error.trim()) return data.error.trim();
    } else if (typeof res.text === 'function') {
      const text = (await res.text()).trim();
      if (text) return text;
    }
  } catch (err) {
    _logRunnerError('failed to parse run error response', err);
  }
  return '';
}

function _runActiveTeamScopeCan(capability) {
  return typeof _runnerActiveTeamScopeCanAdapter === 'function' ? _runnerActiveTeamScopeCanAdapter(capability) : true;
}

function _runTeamScopeDeniedMessage(action) {
  return typeof _runnerTeamScopeDeniedMessageAdapter === 'function'
    ? _runnerTeamScopeDeniedMessageAdapter(action)
    : `View-only team members can't ${action}. Switch to Personal or ask for operator access.`;
}

function _runStartDeniedMessage() {
  return _runTeamScopeDeniedMessage('run commands in team scope');
}

function _workspaceTerminalCanWrite(action = 'change Files') {
  if (typeof _runnerWorkspaceCanWriteAdapter === 'function') return _runnerWorkspaceCanWriteAdapter(action, { toast: false });
  return true;
}

function _workspaceTerminalDeniedMessage(action = 'change Files') {
  if (typeof _runnerTeamScopeDeniedMessageAdapter === 'function') return _runnerTeamScopeDeniedMessageAdapter(action);
  return `View-only team members can't ${action}. Switch to Personal or ask for operator access.`;
}

function _previewTruncationNotice(outputLineCount, fullOutputAvailable) {
  const shown = APP_CONFIG.max_output_lines || outputLineCount || 0;
  const total = outputLineCount || shown;
  if (fullOutputAvailable) {
    return `[preview truncated — only the last ${shown} lines are shown here, but the full output had ${total} lines. To view the full output, use either permalink button now; after another command, use this command's history permalink]`;
  }
  return `[preview truncated — only the last ${shown} lines are shown here, but the full output had ${total} lines. Full output persistence is disabled or unavailable]`;
}

function _streamOutputMetadata(msg) {
  if (!msg || typeof msg !== 'object') return null;
  const metadata = {};
  if (typeof msg.kind === 'string' && msg.kind) metadata.kind = msg.kind;
  if (typeof msg.role === 'string' && msg.role) metadata.role = msg.role;
  if (Array.isArray(msg.signals) && msg.signals.length) metadata.signals = msg.signals;
  if (Number.isInteger(msg.line_index)) metadata.line_index = msg.line_index;
  if (typeof msg.command_root === 'string' && msg.command_root) metadata.command_root = msg.command_root;
  if (typeof msg.target === 'string' && msg.target) metadata.target = msg.target;
  if (Array.isArray(msg.entities) && msg.entities.length) metadata.entities = msg.entities;
  return Object.keys(metadata).length ? metadata : null;
}

function _runnerRunOutputModel() {
  if (typeof importedRunOutputModel !== 'undefined' && importedRunOutputModel) return importedRunOutputModel;
  return null;
}

function _streamUnknownCollector(streamState) {
  const state = streamState || {};
  if (!state.unknownLineEventValues) state.unknownLineEventValues = new Set();
  return (family, value) => {
    const key = `${family}:${value}`;
    if (state.unknownLineEventValues.has(key)) return;
    state.unknownLineEventValues.add(key);
    _logRunnerError(`unknown run output ${family}`, new Error(String(value || 'unknown')));
  };
}

function _warnRunStreamSchema(streamState, family, value) {
  const state = streamState || {};
  if (!state.unknownLineEventValues) state.unknownLineEventValues = new Set();
  const key = `schema:${family}:${value}`;
  if (state.unknownLineEventValues.has(key)) return;
  state.unknownLineEventValues.add(key);
  _logRunnerError(`unknown run output schema ${family}`, new Error(String(value || 'unknown')));
}

function _handleRunStreamSchema(msg, streamState) {
  if (!msg || typeof msg !== 'object') return;
  const model = _runnerRunOutputModel();
  const supported = model ? Number(model.LINE_EVENT_SCHEMA_VERSION || 1) : 1;
  const version = Number(msg.v || 0);
  if (version > supported) _warnRunStreamSchema(streamState, 'version', msg.v);
  if (String(msg.kind || '') !== 'line_event') _warnRunStreamSchema(streamState, 'kind', msg.kind || '');
}

function _typedRunStreamLineMessage(msg, streamState) {
  if (!msg || typeof msg !== 'object') return msg;
  const model = _runnerRunOutputModel();
  if (!model || typeof model.fromWireLineEvent !== 'function') return msg;
  const hasTypedFields = msg.v !== undefined || msg.kind !== undefined || msg.role !== undefined || msg.signals !== undefined;
  if (!hasTypedFields) return msg;
  const version = Number(msg.v || 0);
  if (version > Number(model.LINE_EVENT_SCHEMA_VERSION || 1)) {
    _warnRunStreamSchema(streamState, 'version', msg.v);
  }
  const event = model.fromWireLineEvent(msg, _streamUnknownCollector(streamState));
  const legacy = typeof model.toLegacyWireLineEvent === 'function'
    ? model.toLegacyWireLineEvent(event)
    : { text: event.text || '', cls: event.legacy_cls || '' };
  return {
    ...msg,
    ...legacy,
    kind: event.kind || 'info',
    role: event.role || 'body',
    signals: event.signals || [],
    line_index: event.line_index,
    command_root: event.command_root || '',
    target: event.target || '',
    entities: event.entities || [],
  };
}

function _appendStreamLine(text, cls, tabId, msg, options = {}) {
  let metadata = _streamOutputMetadata(msg);
  if (options.liveOutput && APP_CONFIG && APP_CONFIG.high_volume_output_line_threshold) {
    metadata = metadata || {};
    metadata.live_output = true;
  }
  if (metadata) appendLine(text, cls, tabId, metadata);
  else appendLine(text, cls, tabId);
}

function _forEachStreamTextLine(text, callback) {
  const raw = String(text ?? '');
  if (raw === '') {
    callback('');
    return;
  }
  const lines = raw.split('\n');
  if (lines.length && lines[lines.length - 1] === '') lines.pop();
  lines.forEach(line => callback(line));
}

function _recordRunOutputCoalescing(msg, tabId) {
  const count = Math.max(0, Number(msg && msg.coalesced_line_count || 0));
  if (count && typeof recordLiveOutputCoalescedLines === 'function') {
    recordLiveOutputCoalescedLines(tabId, count);
  }
}

function _batchedStreamLineEntry(msg, lineText, streamState) {
  const lineMsg = _typedRunStreamLineMessage({
    ...msg,
    type: 'output',
    text: lineText,
  }, streamState);
  if (APP_CONFIG && APP_CONFIG.high_volume_output_line_threshold) {
    lineMsg.live_output = true;
  }
  return lineMsg;
}

function _handleRunOutputBatch(msg, tabId, streamState = null) {
  const t = getTab(tabId);
  if (t && t.killed) return;
  _recordRunOutputCoalescing(msg, tabId);
  const lines = Array.isArray(msg.lines) ? msg.lines : [];
  if (!lines.length) return;
  const entries = [];
  lines.forEach(rawLine => {
    if (!rawLine || typeof rawLine !== 'object') return;
    const lineMsg = _typedRunStreamLineMessage({ ...rawLine, type: 'output' }, streamState);
    if (t && typeof lineMsg.text === 'string' && /^Unsupported built-in command: /.test(lineMsg.text)) {
      t.unknownCommand = true;
    }
    _forEachStreamTextLine(lineMsg.text, line => {
      if (!_shouldSuppressStreamOutputLine(t, line)) {
        entries.push(_batchedStreamLineEntry(lineMsg, line, streamState));
      }
    });
  });
  if (entries.length && typeof appendLines === 'function') {
    appendLines(entries, tabId);
  }
}

function _runStreamQueueLength(streamState) {
  if (!streamState || !Array.isArray(streamState.messageQueue)) return 0;
  return streamState.messageQueue.length - Number(streamState.messageQueueIndex || 0);
}

function _runStreamNow() {
  if (typeof performance !== 'undefined' && typeof performance.now === 'function') {
    return performance.now();
  }
  return Date.now();
}

function _finishRunStreamIfQueueDrained(tabId, streamState) {
  if (!streamState || !streamState.readDone || _runStreamQueueLength(streamState) > 0) return false;
  if (streamState.messageQueueScheduled || streamState.messageQueueDraining) return false;
  if (_finishPausedRunStream(tabId, streamState)) return true;
  _runStreamStateByTabId.delete(tabId);
  if (!streamState.sawTerminalEvent) _handleStreamEndedWithoutExit(tabId);
  return true;
}

function _scheduleRunStreamMessageDrain(tabId, streamState, { defer = false } = {}) {
  if (!streamState || streamState.messageQueueScheduled) return;
  streamState.messageQueueScheduled = true;
  const run = () => _drainRunStreamMessageQueue(tabId, streamState);
  if (defer) setTimeout(run, 0);
  else Promise.resolve().then(run);
}

function _enqueueRunStreamMessages(messages, tabId, streamState) {
  if (!streamState || !Array.isArray(messages) || !messages.length) return;
  if (!Array.isArray(streamState.messageQueue)) {
    streamState.messageQueue = [];
    streamState.messageQueueIndex = 0;
  }
  streamState.messageQueue.push(...messages);
  _scheduleRunStreamMessageDrain(tabId, streamState);
}

function _drainRunStreamMessageQueue(tabId, streamState) {
  if (!streamState) return;
  streamState.messageQueueScheduled = false;
  streamState.messageQueueDraining = true;
  const queue = Array.isArray(streamState.messageQueue) ? streamState.messageQueue : [];
  const started = _runStreamNow();
  let index = Number(streamState.messageQueueIndex || 0);
  let processed = 0;

  while (index < queue.length) {
    const msg = queue[index];
    index += 1;
    processed += 1;
    if (msg && ['exit', 'error'].includes(String(msg.type || msg.event || ''))) {
      streamState.sawTerminalEvent = true;
    }
    _handleRunStreamMessage(msg, tabId, streamState);
    if (processed >= _RUN_STREAM_MESSAGE_BATCH_LIMIT) break;
    if (_runStreamNow() - started >= _RUN_STREAM_MESSAGE_BATCH_MS) break;
  }

  streamState.messageQueueIndex = index;
  if (index >= queue.length) {
    streamState.messageQueue = [];
    streamState.messageQueueIndex = 0;
  }
  streamState.messageQueueDraining = false;

  if (_runStreamQueueLength(streamState) > 0) {
    _scheduleRunStreamMessageDrain(tabId, streamState, { defer: true });
    return;
  }
  _finishRunStreamIfQueueDrained(tabId, streamState);
}

function appendCommandEcho(cmd, tabId) {
  appendLine(cmd, 'prompt-echo', tabId);
}

function appendPromptNewline(tabId) {
  appendLine('', 'prompt-echo', tabId);
}

function _brokerStreamUrl(runId, tabId, streamUrl = '', afterId = '') {
  const base = streamUrl || `/runs/${encodeURIComponent(runId)}/stream`;
  const params = [];
  if (tabId) params.push(`tab_id=${encodeURIComponent(tabId)}`);
  if (afterId) params.push(`after=${encodeURIComponent(afterId)}`);
  if (!params.length) return base;
  const separator = base.includes('?') ? '&' : '?';
  return `${base}${separator}${params.join('&')}`;
}

function _sseMessageFromChunk(part) {
  let eventId = '';
  const dataLines = [];
  String(part || '').split(/\r?\n/).forEach(line => {
    if (line.startsWith('id: ')) eventId = line.slice(4).trim();
    else if (line.startsWith('data: ')) dataLines.push(line.slice(6));
  });
  if (!dataLines.length) return null;
  const msg = JSON.parse(dataLines.join('\n'));
  if (eventId && msg && typeof msg === 'object' && !msg.event_id) msg.event_id = eventId;
  return msg;
}

function _markTabRunStarted(tabId, runId) {
  const t = getTab(tabId);
  if (!t || !runId) return;
  const sameRun = t.runId === runId || t.historyRunId === runId;
  t.runId = runId;
  t.historyRunId = runId;
  if (!sameRun) {
    t.lastEventId = '';
    t.streamRecoveryAttempts = 0;
    t.streamRecoveryNoticeRunId = '';
    _clearStreamRecoveryTimer(tabId);
  }
  if (!sameRun && typeof resetHighVolumeOutputState === 'function') {
    resetHighVolumeOutputState(tabId);
  }
  t.unknownCommand = false;
  t.reconnectedRun = false;
  if (t.pendingKill) {
    // Kill was requested before runId was available — send it now.
    t.pendingKill = false;
    apiFetch('/kill', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_id: t.runId, tab_id: tabId })
    }).catch(err => _handleKillRequestFailure(err, tabId));
    t.runId = null;
  } else {
    t.killed = false;
  }
}

function _handleRunStreamMessage(msg, tabId, streamState = null) {
  if (!msg || typeof msg !== 'object') return;
  const t = getTab(tabId);
  if (t && msg.event_id) t.lastEventId = String(msg.event_id || '');
  if (msg.type === 'schema' || msg.event === 'schema') {
    _handleRunStreamSchema(msg, streamState);
  } else if (msg.type === 'started') {
    _markTabRunStarted(tabId, msg.run_id);
  } else if (msg.type === 'notice') {
    msg = _typedRunStreamLineMessage(msg, streamState);
    _appendStreamLine(msg.text, 'notice', tabId, msg);
    const notifyProjectChange = typeof globalThis.notifyProjectWorkspaceChanged === 'function'
      ? globalThis.notifyProjectWorkspaceChanged
      : (typeof notifyProjectWorkspaceChanged === 'function' ? notifyProjectWorkspaceChanged : null);
    if (msg.project_linked && notifyProjectChange) {
      notifyProjectChange('run-linked', msg.project_id || '');
    }
    if (msg.project_entities_linked && notifyProjectChange) {
      notifyProjectChange('entities-linked', msg.project_id || '');
    }
    if (msg.project_auto_promoted) {
      if (notifyProjectChange) {
        notifyProjectChange('auto-promoted', msg.project_id || '');
      }
      if (typeof emitUiEvent === 'function') {
        emitUiEvent('app:project-auto-promoted', {
          project_id: msg.project_id || '',
          project_ids: Array.isArray(msg.project_ids) ? msg.project_ids : [],
          count: Number(msg.entity_count || msg.count || 0) || 0,
          promoted_count: Number(msg.promoted_count || 0) || 0,
        });
      }
    }
    if (msg.project_targets_discovered) {
      const rawCount = Number(msg.target_count || msg.count || 0);
      const count = Number.isFinite(rawCount) ? rawCount : 0;
      if (notifyProjectChange) {
        notifyProjectChange('target-discovered', msg.project_id || '');
      }
      if (typeof emitUiEvent === 'function') {
        emitUiEvent('app:project-target-discovered', {
          project_id: msg.project_id || '',
          project_name: msg.project_name || '',
          count,
        });
      }
    }
  } else if (msg.type === 'owner') {
    _handleRunOwnerChanged(msg, tabId);
  } else if (msg.type === 'killed') {
    _handleRunKilled(msg, tabId);
  } else if (msg.type === 'clear') {
    clearTab(tabId);
    const t = getTab(tabId);
    if (t) t.syntheticClear = true;
  } else if (msg.type === 'output_batch') {
    _handleRunOutputBatch(msg, tabId, streamState);
  } else if (msg.type === 'output') {
    _recordRunOutputCoalescing(msg, tabId);
    msg = _typedRunStreamLineMessage(msg, streamState);
    const t = getTab(tabId);
    if (t && t.killed) return;
    if (t && typeof msg.text === 'string' && /^Unsupported built-in command: /.test(msg.text)) {
      t.unknownCommand = true;
    }
    _forEachStreamTextLine(msg.text, line => {
      if (!_shouldSuppressStreamOutputLine(t, line)) {
        _appendStreamLine(line, msg.cls || '', tabId, msg, { liveOutput: true });
      }
    });
  } else if (msg.type === 'exit') {
    _clearStalledTimeout(tabId);
    _clearStreamRecoveryTimer(tabId);
    const t = getTab(tabId);
    if (t) {
      t.exitCode = msg.code;
      t.runId = null;
      t.reconnectedRun = false;
      t.lastEventId = '';
      t.attachMode = '';
      t.streamRecoveryAttempts = 0;
      t.streamRecoveryNoticeRunId = '';
      t.deferPromptMount = true;
      t.previewTruncated = !!msg.preview_truncated;
      t.fullOutputAvailable = !!msg.full_output_available;
      t.fullOutputLoaded = !msg.preview_truncated;
    }
    // If already killed by user, ignore the subsequent -15 exit code.
    if (t && t.killed) {
      t.killed = false;
      if (typeof discardPendingOutputBatch === 'function') discardPendingOutputBatch(tabId);
      _appendHighVolumeOutputFinalSummary(tabId);
      stopTimer();
      _setRunButtonDisabled(false); hideTabKillBtn(tabId);
      if (typeof disableHighVolumeOutputResumeControls === 'function') {
        disableHighVolumeOutputResumeControls(tabId);
      }
      const finalizeTabClose = typeof importedFinalizeClosingTab === 'function'
        ? importedFinalizeClosingTab
        : (typeof finalizeClosingTab === 'function' ? finalizeClosingTab : null);
      if (t.closing && finalizeTabClose) {
        finalizeTabClose(tabId);
        if (isHistoryPanelOpen()) refreshHistoryPanel();
      }
      if (isHistoryPanelOpen()) refreshHistoryPanel();
      if (!(t && t.closing) && typeof _maybeMountDeferredPrompt === 'function') {
        _maybeMountDeferredPrompt(tabId);
      }
      return;
    }
    const dur = msg.elapsed ? ` in ${msg.elapsed}s` : '';
    stopTimer();
    if (msg.preview_truncated) {
      appendLine(_previewTruncationNotice(msg.output_line_count, msg.full_output_available), 'notice', tabId);
    }
    if (msg.code === 0) {
      if (!(t && t.syntheticClear)) appendLine(`[process exited with code 0${dur}]`, 'exit-ok', tabId);
      _appendHighVolumeOutputFinalSummary(tabId);
      if (typeof renderCommandOutcomeSummary === 'function') renderCommandOutcomeSummary(tabId);
      if (tabId === _runnerActiveTabId()) setStatus('ok');
      setTabStatus(tabId, 'ok');
      if (typeof disableHighVolumeOutputResumeControls === 'function') {
        disableHighVolumeOutputResumeControls(tabId);
      }
    } else {
      appendLine(`[process exited with code ${msg.code}${dur}]`, 'exit-fail', tabId);
      _appendHighVolumeOutputFinalSummary(tabId);
      if (typeof renderCommandOutcomeSummary === 'function') renderCommandOutcomeSummary(tabId);
      if (tabId === _runnerActiveTabId()) setStatus('fail');
      setTabStatus(tabId, 'fail');
      if (typeof disableHighVolumeOutputResumeControls === 'function') {
        disableHighVolumeOutputResumeControls(tabId);
      }
    }
    if (typeof addToRecentPreview === 'function' && t && t.command && !t.unknownCommand) {
      addToRecentPreview(t.command);
    }
    if (t && t.command) _refreshProjectContextAfterCommand(t.command, msg.code);
    if (t && /^var(?:\s|$)/i.test(String(t.command || '')) && typeof importedLoadSessionVariables === 'function') {
      importedLoadSessionVariables().catch(() => {});
    }
    if (t) t.syntheticClear = false;
    _maybeNotify(t ? t.command : '', msg.code, msg.elapsed ? msg.elapsed + 's' : null);
    if (typeof emitUiEvent === 'function') emitUiEvent('app:last-exit-changed', { value: msg.code });
    _setRunButtonDisabled(false); hideTabKillBtn(tabId);
    _syncMobileRunButtonAfterRunSettled();
    const finalizeTabClose = typeof importedFinalizeClosingTab === 'function'
      ? importedFinalizeClosingTab
      : (typeof finalizeClosingTab === 'function' ? finalizeClosingTab : null);
    if (t && t.closing && finalizeTabClose) {
      finalizeTabClose(tabId);
      if (isHistoryPanelOpen()) refreshHistoryPanel();
      return;
    }
    if (isHistoryPanelOpen()) refreshHistoryPanel();
    _runnerWorkspaceCacheApi().refresh?.();
    if (typeof _maybeMountDeferredPrompt === 'function') _maybeMountDeferredPrompt(tabId);
  } else if (msg.type === 'error') {
    _clearStalledTimeout(tabId);
    appendLine('[error] ' + msg.text, 'exit-fail', tabId);
    if (tabId === _runnerActiveTabId()) setStatus('fail');
    setTabStatus(tabId, 'fail');
    if (typeof disableHighVolumeOutputResumeControls === 'function') {
      disableHighVolumeOutputResumeControls(tabId);
    }
    stopTimer(); _setRunButtonDisabled(false); hideTabKillBtn(tabId);
  }
}

function _sameTabRunStillActive(tabId, runId) {
  const t = getTab(tabId);
  return !!(
    t
    && t.st === 'running'
    && runId
    && (t.runId === runId || t.historyRunId === runId)
  );
}

function _streamResumeAfterId(tabId, state) {
  const t = getTab(tabId);
  return String((t && t.lastEventId) || (state && state.after) || '');
}

function _finishPausedRunStream(tabId, state) {
  const current = _runStreamStateByTabId.get(tabId);
  if (current !== state) return true;
  state.reader = null;
  state.starting = false;
  if (state.detached) {
    _runStreamStateByTabId.delete(tabId);
    return true;
  }
  if (!state.pausedForApi) return false;
  if (state.resumeAfterPause) {
    const runId = state.runId;
    const streamUrl = state.streamUrl || '';
    const after = _streamResumeAfterId(tabId, state);
    _runStreamStateByTabId.delete(tabId);
    if (_sameTabRunStillActive(tabId, runId)) {
      _subscribeRunStream(runId, tabId, { streamUrl, after });
    }
    return true;
  }
  return true;
}

function detachRunStreamForTab(tabId) {
  const state = _runStreamStateByTabId.get(tabId);
  if (!state) return false;
  state.detached = true;
  state.pausedForApi = false;
  state.resumeAfterPause = false;
  const reader = state.reader;
  state.reader = null;
  _runStreamStateByTabId.delete(tabId);
  _clearStalledTimeout(tabId);
  if (reader && typeof reader.cancel === 'function') {
    try {
      const cancelled = reader.cancel();
      if (cancelled && typeof cancelled.catch === 'function') {
        cancelled.catch((err) => {
          _logRunStreamCancelFailure(err, tabId, state.runId, 'detach');
        });
      }
    } catch (err) {
      _logRunStreamCancelFailure(err, tabId, state.runId, 'detach');
    }
  }
  _logRunStreamLifecycle('RUN_STREAM_DETACHED', tabId, state.runId, 'detach');
  return true;
}

function pauseBackgroundRunStreamsForStatusMonitor() {
  const keepTabId = _runnerActiveTabId();
  let paused = 0;
  _runStreamStateByTabId.forEach((state, tabId) => {
    if (!state || tabId === keepTabId || state.pausedForApi || state.detached) return;
    if (!_sameTabRunStillActive(tabId, state.runId)) {
      detachRunStreamForTab(tabId);
      return;
    }
    state.pausedForApi = true;
    state.resumeAfterPause = false;
    paused += 1;
    _clearStalledTimeout(tabId);
    const reader = state.reader;
    state.reader = null;
    state.starting = false;
    if (reader && typeof reader.cancel === 'function') {
      try {
        const cancelled = reader.cancel();
        if (cancelled && typeof cancelled.catch === 'function') {
          cancelled.catch((err) => {
            _logRunStreamCancelFailure(err, tabId, state.runId, 'pause-for-status-monitor');
          });
        }
      } catch (err) {
        _logRunStreamCancelFailure(err, tabId, state.runId, 'pause-for-status-monitor');
      }
    }
    _logRunStreamLifecycle('RUN_STREAM_PAUSED_FOR_STATUS_MONITOR', tabId, state.runId, 'pause-for-status-monitor');
  });
  return paused;
}

function resumeBackgroundRunStreamsAfterStatusMonitor() {
  _runStreamStateByTabId.forEach((state, tabId) => {
    if (!state || !state.pausedForApi || state.detached) return;
    if (state.reader) {
      state.resumeAfterPause = true;
      return;
    }
    const runId = state.runId;
    const streamUrl = state.streamUrl || '';
    const after = _streamResumeAfterId(tabId, state);
    _runStreamStateByTabId.delete(tabId);
    if (_sameTabRunStillActive(tabId, runId)) {
      _subscribeRunStream(runId, tabId, { streamUrl, after });
    }
  });
}

function _streamRunResponse(res, tabId, state = null) {
  if (!res.body || typeof res.body.getReader !== 'function') {
    appendLine('[server error] The server returned an invalid streaming response.', 'exit-fail', tabId);
    setStatus('fail'); setTabStatus(tabId, 'fail');
    stopTimer(); _setRunButtonDisabled(false); hideTabKillBtn(tabId);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  const streamState = state || _runStreamStateByTabId.get(tabId) || {};
  streamState.reader = reader;
  streamState.starting = false;
  streamState.runId = streamState.runId || _tabRunGeneration(tabId);
  _runStreamStateByTabId.set(tabId, streamState);
  if (streamState.pausedForApi && !streamState.resumeAfterPause) {
    streamState.reader = null;
    try {
      const cancelled = reader.cancel();
      if (cancelled && typeof cancelled.catch === 'function') cancelled.catch(() => {});
    } catch (_) {}
    return;
  }
  let buffer = '';

  _resetStalledTimeout(tabId);

  function read() {
    reader.read().then(({ done, value }) => {
      if (done) {
        streamState.readDone = true;
        streamState.reader = null;
        _finishRunStreamIfQueueDrained(tabId, streamState);
        return;
      }
      _recoverStalledRun(tabId);
      _resetStalledTimeout(tabId);
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop();
      const messages = [];
      parts.forEach(part => {
        try {
          const msg = _sseMessageFromChunk(part);
          if (msg) messages.push(msg);
        } catch(e) {}
      });
      _enqueueRunStreamMessages(messages, tabId, streamState);
      read();
    }).catch(err => {
      if (_finishPausedRunStream(tabId, streamState)) return;
      _runStreamStateByTabId.delete(tabId);
      appendLine(`[network error] ${_describeRunnerFetchError(err, 'server')}`, 'exit-fail', tabId);
      if (tabId === _runnerActiveTabId()) setStatus('fail');
      setTabStatus(tabId, 'fail');
      stopTimer(); _setRunButtonDisabled(false); hideTabKillBtn(tabId);
    });
  }
  read();
}

function _subscribeRunStream(runId, tabId, { streamUrl = '', after = '' } = {}) {
  if (!runId || !tabId || typeof apiFetch !== 'function') return Promise.resolve(false);
  const existing = _runStreamStateByTabId.get(tabId);
  if (existing && (existing.reader || existing.starting) && !existing.pausedForApi && !existing.detached) {
    return Promise.resolve(true);
  }
  const streamState = {
    runId,
    tabId,
    streamUrl,
    after,
    reader: null,
    starting: true,
    pausedForApi: false,
    resumeAfterPause: false,
    detached: false,
  };
  _runStreamStateByTabId.set(tabId, streamState);
  return apiFetch(_brokerStreamUrl(runId, tabId, streamUrl, after))
    .then(streamRes => {
      if (streamState.detached) return false;
      if (!streamRes.ok) {
        _runStreamStateByTabId.delete(tabId);
        return _readRunErrorMessage(streamRes).then(message => {
          const suffix = message ? ` ${message}` : '';
          appendLine(`[server error] The server could not stream the command.${suffix}`, 'exit-fail', tabId);
          if (tabId === _runnerActiveTabId()) setStatus('fail');
          setTabStatus(tabId, 'fail');
          stopTimer(); _setRunButtonDisabled(false); hideTabKillBtn(tabId);
          return false;
        });
      }
      _streamRunResponse(streamRes, tabId, streamState);
      return true;
    })
    .catch(err => {
      if (streamState.detached) return false;
      _runStreamStateByTabId.delete(tabId);
      appendLine(`[network error] ${_describeRunnerFetchError(err, 'server')}`, 'exit-fail', tabId);
      if (tabId === _runnerActiveTabId()) setStatus('fail');
      setTabStatus(tabId, 'fail');
      stopTimer(); _setRunButtonDisabled(false); hideTabKillBtn(tabId);
      return false;
    });
}

function _clearComposerInputs() {
  let cleared = false;
  for (const input of [cmdInput, mobileCmdInput]) {
    if (!input) continue;
    input.value = '';
    if (typeof input.setSelectionRange === 'function') input.setSelectionRange(0, 0);
    if (typeof input.dispatchEvent === 'function') input.dispatchEvent(new Event('input'));
    cleared = true;
  }
  if (typeof setComposerValue === 'function') setComposerValue('', 0, 0, { allowDuringRun: true });
  if (typeof syncRunButtonDisabled === 'function') syncRunButtonDisabled();
  return cleared;
}

function interruptPromptLine(tabId = _runnerActiveTabId()) {
  const t = getTab(tabId);
  if (t && t.st === 'running') return false;
  appendPromptNewline(tabId);
  _clearComposerInputs();
  refocusComposerAfterAction();
  if (tabId === _runnerActiveTabId()) setStatus('idle');
  return true;
}

// ── Kill confirmation modal ──
function confirmKill(tabId) {
  pendingKillTabId = tabId;
  if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
  showConfirm({
    body: {
      text: 'Kill the running process in this tab?',
      note: 'This sends SIGTERM to the entire process group.',
    },
    tone: 'danger',
    actions: [
      { id: 'cancel',  label: 'Cancel', role: 'cancel' },
      { id: 'confirm', label: '■ Kill', role: 'destructive' },
    ],
  }).then((result) => {
    const targetId = pendingKillTabId;
    pendingKillTabId = null;
    if (result === 'confirm' && targetId) doKill(targetId);
  });
}

function doKill(tabId) {
  const t = getTab(tabId);
  if (!t || t.st !== 'running') return;
  const secs = elapsedSeconds();
  const suppressKilledTranscript = !!t.closing;
  if (t.runId) {
    // runId already available — send kill immediately
    const runId = t.runId;
    apiFetch('/kill', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_id: runId, tab_id: tabId })
    }).then(resp => {
      if (!resp) {
        _handleKillRequestFailure(new Error('Kill request failed'), tabId);
        return false;
      }
      if (!resp.ok) {
        return _readRunErrorMessage(resp).then(message => {
          if (resp && resp.status === 403) _handleKillRequestDenied(message, tabId, runId);
          else _handleKillRequestFailure(new Error(message || 'Kill request failed'), tabId);
          return false;
        });
      }
      const current = getTab(tabId);
      if (current) current.runId = null;
      _markTabKilledByUser(tabId, secs, { suppressTranscript: suppressKilledTranscript });
      return true;
    }).catch(err => _handleKillRequestFailure(err, tabId));
  } else {
    // runId not yet available (SSE 'started' hasn't arrived) — flag it so the
    // started handler sends the kill request as soon as the run_id is known
    t.pendingKill = true;
    _markTabKilledByUser(tabId, secs, { suppressTranscript: suppressKilledTranscript });
  }
}

// ── Run command ──
// submitCommand(rawCmd) is the shared entry point for executing a command
// string. It does not read from or write to any DOM input — the caller
// supplies the value and owns input cleanup afterward.
//
// Return values (callers use these to decide what to do with their input):
//   'settle'  — empty input during welcome; caller should focus without clearing
//   true      — command submitted; caller should clear input and focus
//   false     — rejected or blocked; caller should leave input as-is
function _parseSyntheticPostFilterCommand(cmd) {
  return _runnerCore().parseSyntheticPostFilterCommand(cmd);
}

function _applySyntheticPostFilterLines(lineItems, spec) {
  return _runnerCore().applySyntheticPostFilterLines(lineItems, spec);
}

function _isSyntheticPostFilterCommand(cmd) {
  return _runnerCore().isSyntheticPostFilterCommand(cmd);
}

function _isSyntheticSortCommand(cmd) {
  return _runnerCore().isSyntheticSortCommand(cmd);
}

function _isSyntheticUniqCommand(cmd) {
  return _runnerCore().isSyntheticUniqCommand(cmd);
}

function _isSyntheticGrepCommand(cmd) {
  return _runnerCore().isSyntheticGrepCommand(cmd);
}

function _isSyntheticHeadCommand(cmd) {
  return _runnerCore().isSyntheticHeadCommand(cmd);
}

function _isSyntheticTailCommand(cmd) {
  return _runnerCore().isSyntheticTailCommand(cmd);
}

function _isSyntheticWcLineCountCommand(cmd) {
  return _runnerCore().isSyntheticWcLineCountCommand(cmd);
}

function _isExactSpecialBuiltInCommand(cmd) {
  const normalized = String(cmd || '').trim().toLowerCase().replace(/\s+/g, ' ');
  const rawKnown = (typeof acSpecialCommands !== 'undefined' && acSpecialCommands) || [];
  const known = Array.isArray(rawKnown)
    ? rawKnown
    : Object.values(rawKnown).flatMap((entry) => {
        if (typeof entry === 'string') return [entry];
        if (Array.isArray(entry)) return entry;
        if (entry && typeof entry === 'object') {
          return [entry.command, entry.value, entry.insertValue].filter(Boolean);
        }
        return [];
      });
  if (known.includes(normalized)) return true;
  // Fork bomb variants use non-standard whitespace; match the regex as a fallback
  // for the brief window before acSpecialCommands loads from /autocomplete.
  return /^:\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:$/.test(String(cmd || '').trim());
}

// ── Session token client-side command handlers ─────────────────────────────

function _isSessionTokenSubcommand(cmd) {
  // Only intercept subcommand variants; bare 'session-token' (status) goes to
  // the server so it can be handled as a normal built-in command with ANSI styling.
  const lower = (cmd || '').trim().toLowerCase();
  return lower.startsWith('session-token ');
}

function _isClientSideUiCommand(cmd) {
  const root = String(cmd || '').trim().split(/\s+/, 1)[0].toLowerCase();
  return root === 'theme' || root === 'config' || root === 'tour';
}

function _isClientSideSecretSetCommand(cmd) {
  const parts = String(cmd || '').trim().split(/\s+/).filter(Boolean);
  return parts[0]?.toLowerCase() === 'secret' && parts[1]?.toLowerCase() === 'set';
}

function _isTabCloseCommand(cmd) {
  return /^(exit|quit)$/i.test(String(cmd || '').trim());
}

function _historySafeCommand(cmd) {
  return _runnerPersistenceHelpers().historySafeCommand(cmd);
}

function _recordSuccessfulLocalCommand(cmd) {
  if (typeof addToRecentPreview !== 'function') return;
  const value = _historySafeCommand(cmd);
  if (value) addToRecentPreview(value);
}

function _isProjectWorkspaceCommand(cmd) {
  return String(cmd || '').trim().split(/\s+/, 1)[0].toLowerCase() === 'project';
}

function _runnerProjectWorkspaceSyncStorageKey() {
  return 'darklab_project_workspace_changed';
}

function _broadcastProjectWorkspaceChanged(cmd) {
  if (typeof emitUiEvent === 'function') {
    emitUiEvent('app:project-workspace-changed', { command: String(cmd || '') });
  }
  if (typeof localStorage === 'undefined' || !localStorage || typeof localStorage.setItem !== 'function') return;
  try {
    localStorage.setItem(_runnerProjectWorkspaceSyncStorageKey(), JSON.stringify({
      session_id: typeof SESSION_ID !== 'undefined' ? SESSION_ID : '',
      command: String(cmd || ''),
      changed_at: Date.now(),
    }));
  } catch (_) {
    // Cross-tab refresh is best-effort; the local tab still refreshes below.
  }
}

function _refreshProjectContextAfterCommand(cmd, exitCode) {
  if (Number(exitCode) !== 0 || !_isProjectWorkspaceCommand(cmd)) return;
  _broadcastProjectWorkspaceChanged(cmd);
  const refreshWorkspace = typeof refreshProjectWorkspace === 'function'
    && typeof isProjectWorkspaceOpen === 'function'
    && isProjectWorkspaceOpen()
    ? refreshProjectWorkspace
    : null;
  const refreshActive = refreshWorkspace || (
    typeof refreshActiveProjectContext === 'function' ? refreshActiveProjectContext : null
  );
  if (!refreshActive) return;
  try {
    const result = refreshActive();
    if (result && typeof result.catch === 'function') {
      result.catch(err => _logRunnerError('failed to refresh active project after command', err));
    }
  } catch (err) {
    _logRunnerError('failed to refresh active project after command', err);
  }
}

function _clientSideRunExitCodeFromStatus(statusValue) {
  return _runnerPersistenceHelpers().exitCodeFromStatus(statusValue);
}

function _finalizeClientSideCommandStatus(tabId, statusValue) {
  const failed = statusValue === 'fail';
  const exitCode = failed ? 1 : 0;
  const finalStatus = failed ? 'fail' : 'ok';
  const tab = typeof getTab === 'function' ? getTab(tabId) : null;
  if (tab) {
    tab.exitCode = exitCode;
    tab.runId = null;
    tab.reconnectedRun = false;
    tab.lastEventId = '';
    tab.attachMode = '';
  }
  if (tabId === _runnerActiveTabId()) setStatus(finalStatus);
  setTabStatus(tabId, finalStatus);
  if (typeof emitUiEvent === 'function') emitUiEvent('app:last-exit-changed', { value: exitCode });
}

function _persistClientSideRun(command, lineItems, statusValue, tabId = _runnerActiveTabId()) {
  _runnerPersistenceHelpers().persistClientSideRun(command, lineItems, statusValue, tabId);
}

function _persistSessionTokenRun(command, lineItems, statusValue = 'ok', tabId = _runnerActiveTabId()) {
  _persistClientSideRun(command, lineItems, statusValue, tabId);
}

function _sessionMigrationCountLabel(runCount = 0, workspaceFileCount = 0, workflowCount = 0, recentValueCount = 0) {
  const parts = [];
  if (runCount > 0) parts.push(`${runCount} run(s)`);
  if (workspaceFileCount > 0) parts.push(`${workspaceFileCount} workspace file(s)`);
  if (workflowCount > 0) parts.push(`${workflowCount} workflow(s)`);
  if (recentValueCount > 0) parts.push(`${recentValueCount} recent value(s)`);
  if (!parts.length) return 'no runs, workspace files, workflows, or recent values';
  if (parts.length === 1) return parts[0];
  return `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`;
}

function _sessionMigrationResultText(data = {}) {
  const workspaceFiles = Number(data.migrated_workspace_files || 0);
  const skippedWorkspaceFiles = Number(data.skipped_workspace_files || 0);
  const workspaceDirs = Number(data.migrated_workspace_directories || 0);
  const skippedWorkspaceDirs = Number(data.skipped_workspace_directories || 0);
  const recentValues = Number(data.migrated_recent_values || 0);
  const workspaceParts = [
    `${workspaceFiles} workspace file(s)`,
  ];
  if (workspaceDirs > 0) workspaceParts.push(`${workspaceDirs} folder(s)`);
  if (skippedWorkspaceFiles > 0) workspaceParts.push(`${skippedWorkspaceFiles} workspace file(s) skipped`);
  if (skippedWorkspaceDirs > 0) workspaceParts.push(`${skippedWorkspaceDirs} folder(s) skipped`);
  return `migrated — ${data.migrated_runs} run(s), ${data.migrated_snapshots} snapshot(s), `
    + `${data.migrated_stars ?? 0} starred command(s), ${data.migrated_workflows ?? 0} workflow(s), `
    + `${recentValues} recent value(s), `
    + `${workspaceParts.join(', ')}, `
    + 'and saved user options when the destination had none';
}

async function _doSessionMigration(fromId, toId, tabId) {
  // Use an explicit fetch (not apiFetch) so X-Session-ID is the OLD session ID
  // regardless of what SESSION_ID has been updated to.
  // Returns true on success so the caller switches identity only after a
  // successful migration — leaving the old session active on failure.
  let succeeded = false;
  try {
    const resp = await fetch('/session/migrate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Session-ID': fromId,
      },
      body: JSON.stringify({ from_session_id: fromId, to_session_id: toId }),
    });
    const data = await resp.json().catch(() => ({}));
    if (resp.ok && data.ok) {
      appendLine(_sessionMigrationResultText(data), '', tabId);
      succeeded = true;
    } else {
      appendLine(`[migration failed] ${data.error || resp.status}`, 'exit-fail', tabId);
    }
  } catch (err) {
    appendLine(`[migration failed] ${err.message || 'network error'}`, 'exit-fail', tabId);
    logClientError('session-token migrate', err);
  }
  return succeeded;
}

async function _seedLocalStorageStarsToServer() {
  // Migrate any stars stored in localStorage (legacy or anonymous-session
  // fallback) to the current server session, then clear the localStorage entry.
  // Only the successfully seeded commands are removed; any that fail are kept
  // in localStorage so they are not silently lost on a flaky network.
  let localStars;
  try { localStars = new Set(JSON.parse(localStorage.getItem('starred') || '[]')); }
  catch { localStars = new Set(); }
  if (!localStars.size) {
    // Clear the leftover key (typically a stale empty array from before stars
    // moved server-side) so it does not linger in localStorage indefinitely.
    localStorage.removeItem('starred');
    return;
  }
  const cmds = [...localStars];
  const results = await Promise.allSettled(cmds.map(async cmd => {
    const resp = await apiFetch('/session/starred', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: cmd }),
    });
    if (!resp.ok) throw new Error(String(resp.status));
    return cmd;
  }));
  const failed = cmds.filter((_, i) => results[i].status === 'rejected');
  if (failed.length === 0) {
    localStorage.removeItem('starred');
  } else {
    localStorage.setItem('starred', JSON.stringify(failed));
  }
  if (typeof loadStarredFromServer === 'function') await loadStarredFromServer();
}

function _setPendingTerminalConfirm(config) {
  _pendingTerminalConfirm = config || null;
  if (typeof setComposerPromptMode === 'function') {
    setComposerPromptMode(_pendingTerminalConfirm ? 'confirm' : null);
  }
}

function hasPendingTerminalConfirm() {
  return !!_pendingTerminalConfirm;
}

async function _runPendingTerminalConfirmHandler(promptTabId, handler) {
  const originalSetStatus = setStatus;
  let finalStatus = 'idle';
  try {
    setStatus = (statusValue) => {
      finalStatus = statusValue;
      originalSetStatus(statusValue);
    };
    await Promise.resolve(typeof handler === 'function' ? handler() : undefined);
  } finally {
    setStatus = originalSetStatus;
  }
  _finalizeClientSideCommandStatus(promptTabId, finalStatus);
}

function cancelPendingTerminalConfirm(tabId = _runnerActiveTabId()) {
  if (!_pendingTerminalConfirm) return false;
  const pending = _pendingTerminalConfirm;
  const promptTabId = pending.tabId || tabId || _runnerActiveTabId();
  _setPendingTerminalConfirm(null);
  const cancelHandler = typeof pending.onCancel === 'function'
    ? pending.onCancel
    : (typeof pending.onNo === 'function' ? pending.onNo : null);
  if (pending.kind === 'text') {
    Promise.resolve(typeof cancelHandler === 'function' ? cancelHandler() : undefined).catch((err) => {
      appendLine(`[error] ${err.message || 'network error'}`, 'exit-fail', promptTabId);
      setStatus('fail');
    });
    refocusComposerAfterAction();
    return true;
  }
  _runPendingTerminalConfirmHandler(promptTabId, cancelHandler).catch((err) => {
    appendLine(`[error] ${err.message || 'network error'}`, 'exit-fail', promptTabId);
    setStatus('fail');
    _finalizeClientSideCommandStatus(promptTabId, 'fail');
  });
  refocusComposerAfterAction();
  return true;
}

function _appendSessionTokenSetLines(token, tabId) {
  appendLine(`session token set: ${maskSessionToken(token)}`, '', tabId);
  appendLine('reload other tabs to apply the new session token', '', tabId);
}

function _clearVisibleSessionHistoryState() {
  if (typeof hydrateCmdHistory === 'function') hydrateCmdHistory([]);
}

async function _activateSessionTokenIdentity(token) {
  localStorage.setItem('session_token', token);
  updateSessionId(token);
  if (typeof loadRecentValues === 'function') await _runnerIgnoreFailure(loadRecentValues());
  await _seedLocalStorageStarsToServer();
  if (typeof reloadSessionHistory === 'function') await _runnerIgnoreFailure(reloadSessionHistory());
  if (typeof refreshWorkspaceFiles === 'function') void _runnerIgnoreFailure(refreshWorkspaceFiles());
  else _runnerWorkspaceCacheApi().refresh?.()?.catch?.(() => {});
  if (typeof reloadWorkflowCatalog === 'function') void _runnerIgnoreFailure(reloadWorkflowCatalog());
}

async function _sessionTokenGenerate(tabId) {
  const oldSessionId = _runnerCurrentSessionId();
  try {
    const resp = await apiFetch('/session/token/generate');
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      appendLine(`[error] Failed to generate session token — ${data.error || resp.status}`, 'exit-fail', tabId);
      setStatus('fail');
      return;
    }
    const data = await resp.json();
    const newToken = data.session_token;

    if (typeof flushRecentValues === 'function') {
      await _runnerIgnoreFailure(flushRecentValues());
    }

    // Check run/workspace counts on old session before switching identity.
    let runCount = 0;
    let workspaceFileCount = 0;
    let workflowCount = 0;
    let recentValueCount = 0;
    try {
      const countResp = await apiFetch('/session/run-count');
      if (countResp.ok) {
        const countData = await countResp.json();
        runCount = countData.count || 0;
        workspaceFileCount = countData.workspace_files || 0;
        workflowCount = countData.workflow_count || 0;
        recentValueCount = countData.recent_value_count || 0;
      }
    } catch (_) {}

    appendLine(`session token generated:  ${maskSessionToken(newToken)}`, '', tabId);
    appendLine('stored in localStorage as session_token', '', tabId);
    appendLine('use session-token set <value> on another device to continue your session', '', tabId);
    appendLine('warning: your session token grants full access to your session history — treat it like a password', 'notice', tabId);

    if (runCount > 0 || workspaceFileCount > 0 || workflowCount > 0 || recentValueCount > 0) {
      // Defer identity switch until the user answers the migration prompt so a
      // failed /session/migrate does not strand runs on the old session while
      // the active identity is already the new token.
      appendLine(
        `you have ${_sessionMigrationCountLabel(runCount, workspaceFileCount, workflowCount, recentValueCount)} in your previous session. migrate history, files, workflows, and recent values to your new session token?`,
        '',
        tabId
      );
      _setPendingTerminalConfirm({
        tabId,
        onYes: async () => {
          const migrated = await _doSessionMigration(oldSessionId, newToken, tabId);
          if (migrated) {
            localStorage.setItem('session_token', newToken);
            updateSessionId(newToken);
            await _seedLocalStorageStarsToServer();
            if (typeof reloadSessionHistory === 'function') await _runnerIgnoreFailure(reloadSessionHistory());
            if (typeof reloadWorkflowCatalog === 'function') void _runnerIgnoreFailure(reloadWorkflowCatalog());
            _recordSuccessfulLocalCommand('session-token generate');
            _persistSessionTokenRun('session-token generate', [
              { text: `session token generated:  ${maskSessionToken(newToken)}` },
              { text: 'history, files, workflows, and recent values migrated to the new session token' },
            ]);
          }
          setStatus('idle');
        },
        onNo: async () => {
          localStorage.setItem('session_token', newToken);
          updateSessionId(newToken);
          await _seedLocalStorageStarsToServer();
          if (typeof reloadSessionHistory === 'function') await _runnerIgnoreFailure(reloadSessionHistory());
          if (typeof reloadWorkflowCatalog === 'function') void _runnerIgnoreFailure(reloadWorkflowCatalog());
          _recordSuccessfulLocalCommand('session-token generate');
          appendLine('History, file, workflow, and recent-value migration skipped.', '', tabId);
          _persistSessionTokenRun('session-token generate', [
            { text: `session token generated:  ${maskSessionToken(newToken)}` },
            { text: 'History, file, workflow, and recent-value migration skipped.' },
          ]);
          setStatus('idle');
        },
      });
      setStatus('idle');
    } else {
      localStorage.setItem('session_token', newToken);
      updateSessionId(newToken);
      await _seedLocalStorageStarsToServer();
      if (typeof reloadSessionHistory === 'function') reloadSessionHistory().catch(() => {});
      _recordSuccessfulLocalCommand('session-token generate');
      _persistSessionTokenRun('session-token generate', [
        { text: `session token generated:  ${maskSessionToken(newToken)}` },
        { text: 'stored in localStorage as session_token' },
      ]);
      setStatus('ok');
    }
  } catch (err) {
    appendLine(`[error] ${err.message || 'network error'}`, 'exit-fail', tabId);
    logClientError('session-token generate', err);
    setStatus('fail');
  }
}

async function _sessionTokenSet(value, tabId) {
  if (!value) {
    appendLine('usage: session-token set <token>', '', tabId);
    setStatus('fail');
    return;
  }
  const isTok = value.startsWith('tok_');
  const isUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
  if (!isTok && !isUuid) {
    appendLine(`[error] invalid session token format — expected tok_... or a UUID`, 'exit-fail', tabId);
    setStatus('fail');
    return;
  }

  // For tok_ tokens, verify server-side existence before switching.
  // A typo would otherwise silently create a brand-new empty session.
  // Fail closed: any failure (network error, non-OK response, missing exists flag)
  // blocks the switch rather than allowing an unverified token through.
  if (isTok) {
    let verifyErr = null;
    try {
      const vResp = await apiFetch('/session/token/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: value }),
      });
      const vData = await vResp.json().catch(() => ({}));
      if (!vResp.ok) {
        verifyErr = 'token verification failed — server returned an error';
      } else if (vData.exists === false) {
        verifyErr = 'session token not found — this token was not issued by this server';
      }
    } catch (_) {
      verifyErr = 'token verification failed — server is unreachable';
    }
    if (verifyErr !== null) {
      appendLine(`[error] ${verifyErr}`, 'exit-fail', tabId);
      setStatus('fail');
      return;
    }
  }

  const oldSessionId = _runnerCurrentSessionId();

  if (typeof flushRecentValues === 'function') {
    await _runnerIgnoreFailure(flushRecentValues());
  }

  // Check current session's run/workspace counts before switching identity.
  let runCount = 0;
  let workspaceFileCount = 0;
  let workflowCount = 0;
  let recentValueCount = 0;
  try {
    const countResp = await apiFetch('/session/run-count');
    if (countResp.ok) {
      const countData = await countResp.json();
      runCount = countData.count || 0;
      workspaceFileCount = countData.workspace_files || 0;
      workflowCount = countData.workflow_count || 0;
      recentValueCount = countData.recent_value_count || 0;
    }
  } catch (_) {}

  if (runCount > 0 || workspaceFileCount > 0 || workflowCount > 0 || recentValueCount > 0) {
    // Defer identity switch until the user answers the migration prompt so a
    // failed /session/migrate does not strand runs on the old session while
    // the active identity is already the new token.
    appendLine(
      `you have ${_sessionMigrationCountLabel(runCount, workspaceFileCount, workflowCount, recentValueCount)} in your current session. migrate history, files, workflows, and recent values to this session token?`,
      '',
      tabId
    );
    _setPendingTerminalConfirm({
      tabId,
      onYes: async () => {
        const migrated = await _doSessionMigration(oldSessionId, value, tabId);
        if (migrated) {
          await _activateSessionTokenIdentity(value);
          _appendSessionTokenSetLines(value, tabId);
          _recordSuccessfulLocalCommand(`session-token set ${value}`);
          _persistSessionTokenRun(`session-token set ${value}`, [
            { text: `session token set: ${maskSessionToken(value)}` },
            { text: 'reload other tabs to apply the new session token' },
          ]);
        }
        setStatus('idle');
      },
      onNo: async () => {
        await _activateSessionTokenIdentity(value);
        _appendSessionTokenSetLines(value, tabId);
        _recordSuccessfulLocalCommand(`session-token set ${value}`);
        appendLine('History, file, workflow, and recent-value migration skipped.', '', tabId);
        _persistSessionTokenRun(`session-token set ${value}`, [
          { text: `session token set: ${maskSessionToken(value)}` },
          { text: 'reload other tabs to apply the new session token' },
          { text: 'History, file, workflow, and recent-value migration skipped.' },
        ]);
        setStatus('idle');
      },
      onCancel: async () => {
        appendLine('Session token set canceled.', '', tabId);
        setStatus('idle');
      },
    });
    setStatus('idle');
  } else {
    await _activateSessionTokenIdentity(value);
    _appendSessionTokenSetLines(value, tabId);
    _recordSuccessfulLocalCommand(`session-token set ${value}`);
    _persistSessionTokenRun(`session-token set ${value}`, [
      { text: `session token set: ${maskSessionToken(value)}` },
      { text: 'reload other tabs to apply the new session token' },
    ]);
    setStatus('ok');
  }
}

async function _sessionTokenCopy(tabId) {
  if (typeof flushRecentValues === 'function') {
    await _runnerIgnoreFailure(flushRecentValues());
  }
  const token = localStorage.getItem('session_token');
  if (!token) {
    appendLine('no session token is set — already using an anonymous session', '', tabId);
    setStatus('idle');
    return;
  }
  try {
    await _runnerCopyTextToClipboardAdapter(token);
    appendLine(`session token copied to clipboard: ${maskSessionToken(token)}`, '', tabId);
    _recordSuccessfulLocalCommand('session-token copy');
    _persistSessionTokenRun('session-token copy', [
      { text: `session token copied to clipboard: ${maskSessionToken(token)}` },
    ]);
    setStatus('ok');
  } catch (err) {
    appendLine('[error] failed to copy the session token to clipboard', 'exit-fail', tabId);
    logClientError('session-token copy', err);
    setStatus('fail');
  }
}

async function _sessionTokenClear(tabId) {
  if (!localStorage.getItem('session_token')) {
    appendLine('no session token is set — already using an anonymous session', '', tabId);
    setStatus('idle');
    return;
  }
  appendLine('warning: clearing the active session token removes it from this browser', 'notice', tabId);
  appendLine("run 'session-token copy' first if you want to save the current token before clearing it", 'notice', tabId);
  appendLine('clear the active session token and revert to an anonymous session?', '', tabId);
  _setPendingTerminalConfirm({
    tabId,
    onYes: async () => {
      localStorage.removeItem('session_token');
      const uuid = localStorage.getItem('session_id') || _runnerCurrentSessionId();
      updateSessionId(uuid);
      _clearVisibleSessionHistoryState();
      if (typeof reloadSessionHistory === 'function') await _runnerIgnoreFailure(reloadSessionHistory());
      if (typeof reloadWorkflowCatalog === 'function') void _runnerIgnoreFailure(reloadWorkflowCatalog());
      appendLine(`session token cleared — reverted to anonymous session (${maskSessionToken(uuid)})`, '', tabId);
      appendLine('your session token data remains in the server database', '', tabId);
      _recordSuccessfulLocalCommand('session-token clear');
      _persistSessionTokenRun('session-token clear', [
        { text: `session token cleared — reverted to anonymous session (${maskSessionToken(uuid)})` },
        { text: 'your session token data remains in the server database' },
      ]);
      setStatus('ok');
    },
    onNo: async () => {
      appendLine('Session token clear canceled.', '', tabId);
      setStatus('idle');
    },
  });
  setStatus('idle');
}

async function _sessionTokenRotate(tabId) {
  const oldSessionId = _runnerCurrentSessionId();
  try {
    const resp = await apiFetch('/session/token/generate');
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      appendLine(`[error] Failed to generate session token — ${data.error || resp.status}`, 'exit-fail', tabId);
      setStatus('fail');
      return;
    }
    const data = await resp.json();
    const newToken = data.session_token;

    // Migrate BEFORE updating SESSION_ID so the old ID is sent as X-Session-ID
    const migrateResp = await fetch('/session/migrate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Session-ID': oldSessionId,
      },
      body: JSON.stringify({ from_session_id: oldSessionId, to_session_id: newToken }),
    });
    const migrateData = await migrateResp.json().catch(() => ({}));

    if (!migrateResp.ok || !migrateData.ok) {
      appendLine(`[error] migration failed — session token NOT rotated: ${migrateData.error || migrateResp.status}`, 'exit-fail', tabId);
      appendLine('your previous session token is still active', '', tabId);
      setStatus('fail');
      return;
    }

    localStorage.setItem('session_token', newToken);
    updateSessionId(newToken);
    if (typeof reloadSessionHistory === 'function') reloadSessionHistory().catch(() => {});
    if (typeof refreshWorkspaceFiles === 'function') void _runnerIgnoreFailure(refreshWorkspaceFiles());
    else _runnerWorkspaceCacheApi().refresh?.()?.catch?.(() => {});
    if (typeof reloadWorkflowCatalog === 'function') void _runnerIgnoreFailure(reloadWorkflowCatalog());

    appendLine(`session token rotated: ${maskSessionToken(newToken)}`, '', tabId);
    appendLine(_sessionMigrationResultText(migrateData), '', tabId);
    appendLine('old session token is now inactive — reload other tabs to use the new token', '', tabId);
    _recordSuccessfulLocalCommand('session-token rotate');
    _persistSessionTokenRun('session-token rotate', [
      { text: `session token rotated: ${maskSessionToken(newToken)}` },
      { text: _sessionMigrationResultText(migrateData) },
      { text: 'old session token is now inactive — reload other tabs to use the new token' },
    ]);
    setStatus('ok');
  } catch (err) {
    appendLine(`[error] ${err.message || 'network error'}`, 'exit-fail', tabId);
    logClientError('session-token rotate', err);
    setStatus('fail');
  }
}

async function _sessionTokenList(tabId) {
  try {
    const resp = await apiFetch('/session/token/info');
    if (!resp.ok) {
      appendLine('[error] failed to load session token info', 'exit-fail', tabId);
      setStatus('fail');
      return;
    }
    const data = await resp.json();
    const w = 14;
    const kv = (k, v) => k.padEnd(w) + '  ' + v;
    if (data.token) {
      appendLine(kv('session token', maskSessionToken(data.token)), 'builtin-kv', tabId);
      appendLine(kv('status', 'active'), 'builtin-kv', tabId);
      if (data.created) appendLine(kv('created', data.created + ' UTC'), 'builtin-kv', tabId);
      appendLine(kv('storage', 'localStorage (session_token)'), 'builtin-kv', tabId);
    } else {
      appendLine(kv('session', maskSessionToken(_runnerCurrentSessionId())), 'builtin-kv', tabId);
      appendLine(kv('status', 'anonymous (no session token set)'), 'builtin-kv', tabId);
      appendLine(kv('tip', "run 'session-token generate' to create a persistent token"), 'builtin-kv', tabId);
    }
    _recordSuccessfulLocalCommand('session-token list');
    _persistSessionTokenRun('session-token list', [
      { text: data.token ? `session token  ${maskSessionToken(data.token)}` : `session  ${maskSessionToken(_runnerCurrentSessionId())}`, cls: 'builtin-kv' },
      { text: data.token ? 'status          active' : 'status          anonymous (no session token set)', cls: 'builtin-kv' },
    ]);
    setStatus('ok');
  } catch (err) {
    appendLine(`[error] ${err.message || 'network error'}`, 'exit-fail', tabId);
    logClientError('session-token list', err);
    setStatus('fail');
  }
}

async function _sessionTokenRevoke(token, tabId) {
  if (!token) {
    appendLine('usage: session-token revoke <token>', '', tabId);
    setStatus('fail');
    return;
  }
  if (!token.startsWith('tok_')) {
    appendLine('[error] only tok_ tokens can be revoked', 'exit-fail', tabId);
    setStatus('fail');
    return;
  }
  appendLine(`revoke session token ${maskSessionToken(token)}?`, '', tabId);
  appendLine(
    "warning: this token's history and workspace files will not be recoverable from the app after revocation.",
    'warning',
    tabId
  );
  _setPendingTerminalConfirm({
    tabId,
    onYes: async () => {
      await _sessionTokenRevokeConfirmed(token, tabId);
    },
    onNo: async () => {
      appendLine('Session token revoke canceled.', '', tabId);
      setStatus('idle');
    },
    onCancel: async () => {
      appendLine('Session token revoke canceled.', '', tabId);
      setStatus('idle');
    },
  });
  setStatus('idle');
}

async function _sessionTokenRevokeConfirmed(token, tabId) {
  try {
    const resp = await apiFetch('/session/token/revoke', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      appendLine(`[error] ${data.error || resp.status}`, 'exit-fail', tabId);
      setStatus('fail');
      return;
    }
    const isCurrentToken = token === _runnerCurrentSessionId();
    appendLine(`session token revoked: ${maskSessionToken(token)}`, '', tabId);
    if (isCurrentToken) {
      localStorage.removeItem('session_token');
      const uuid = localStorage.getItem('session_id') || _runnerCurrentSessionId();
      updateSessionId(uuid);
      _clearVisibleSessionHistoryState();
      if (typeof reloadSessionHistory === 'function') reloadSessionHistory().catch(() => {});
      appendLine(`reverted to anonymous session (${maskSessionToken(uuid)})`, '', tabId);
    } else {
      appendLine('token removed from server — any device using it is now on an empty anonymous session', '', tabId);
    }
    _recordSuccessfulLocalCommand(`session-token revoke ${token}`);
    _persistSessionTokenRun(`session-token revoke ${token}`, [
      { text: `session token revoked: ${maskSessionToken(token)}` },
    ]);
    setStatus('ok');
  } catch (err) {
    appendLine(`[error] ${err.message || 'network error'}`, 'exit-fail', tabId);
    logClientError('session-token revoke', err);
    setStatus('fail');
  }
}

function _workspacePlainLine(text = '') {
  return { text: String(text), cls: '' };
}

function _workspaceSplitLines(text = '') {
  const raw = String(text ?? '');
  if (!raw) return [];
  const lines = raw.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
  if (lines.length && lines[lines.length - 1] === '') lines.pop();
  return lines.map(line => _workspacePlainLine(line));
}

function _workspaceFileDescription(file) {
  const size = _workspaceFormatBytes(file && file.size);
  return `${String(file && file.name || file && file.path || '')}${file && file.mtime ? `\t${size}\t${file.mtime}` : `\t${size}`}`;
}

function _workspaceFormatBytes(size) {
  const formatted = typeof _formatWorkspaceBytes === 'function'
    ? _formatWorkspaceBytes(size)
    : null;
  return typeof formatted === 'string' && formatted ? formatted : `${Number(size) || 0} B`;
}

function _workspaceListLines(entries, target = '') {
  const rows = [];
  if (target) rows.push({ name: '../', type: 'dir', size: '-', modified: '' });
  (entries.folders || []).forEach(folder => {
    rows.push({
      name: `${String(folder && folder.name || folder && folder.path || '').replace(/\/+$/, '')}/`,
      type: 'dir',
      size: '-',
      modified: folder && folder.mtime ? String(folder.mtime) : '',
    });
  });
  (entries.files || []).forEach(file => {
    rows.push({
      name: String(file && file.name || file && file.path || ''),
      type: 'file',
      size: _workspaceFormatBytes(file && file.size),
      modified: file && file.mtime ? String(file.mtime) : '',
    });
  });
  if (!rows.length) return [_workspacePlainLine('(empty)')];
  const widths = {
    name: Math.max(...rows.map(row => row.name.length), 4),
    type: Math.max(...rows.map(row => row.type.length), 4),
    size: Math.max(...rows.map(row => row.size.length), 4),
  };
  return rows.map(row => _workspacePlainLine([
    row.name.padEnd(widths.name),
    row.type.padEnd(widths.type),
    row.size.padEnd(widths.size),
    row.modified,
  ].filter((part, index) => index < 3 || part).join('  ').trimEnd()));
}

function _workspaceShortListLines(entries) {
  const names = [];
  (entries.folders || []).forEach(folder => {
    const name = String(folder && folder.name || folder && folder.path || '').replace(/\/+$/, '');
    if (name) names.push(`${name}/`);
  });
  (entries.files || []).forEach(file => {
    const name = String(file && file.name || file && file.path || '');
    if (name) names.push(name);
  });
  if (!names.length) return [_workspacePlainLine('(empty)')];
  return [_workspacePlainLine(names.join(' '))];
}

function _workspaceListNames(entries) {
  const names = [];
  (entries.folders || []).forEach(folder => {
    const name = String(folder && folder.name || folder && folder.path || '').replace(/\/+$/, '');
    if (name) names.push(`${name}/`);
  });
  (entries.files || []).forEach(file => {
    const name = String(file && file.name || file && file.path || '');
    if (name) names.push(name);
  });
  return names;
}

function _workspaceRelativeListName(path = '', base = '', isDirectory = false) {
  const normalized = String(path || '').split('/').filter(Boolean).join('/');
  const normalizedBase = String(base || '').split('/').filter(Boolean).join('/');
  let relative = normalized;
  if (normalizedBase && normalized.startsWith(`${normalizedBase}/`)) {
    relative = normalized.slice(normalizedBase.length + 1);
  }
  relative = relative.split('/').filter(Boolean).join('/');
  if (!relative) return '';
  return isDirectory ? `${relative.replace(/\/+$/, '')}/` : relative;
}

function _workspaceDirectListEntries(entries, base = '') {
  const normalizedBase = String(base || '').split('/').filter(Boolean).join('/');
  const directFolders = new Map();
  const directFiles = [];
  const addDirectFolder = (path, fallbackName = '') => {
    const relative = _workspaceRelativeListName(path, normalizedBase, false)
      || String(fallbackName || '').replace(/\/+$/, '');
    const parts = relative.split('/').filter(Boolean);
    if (parts.length !== 1) return;
    const name = parts[0];
    const folderPath = normalizedBase ? `${normalizedBase}/${name}` : name;
    directFolders.set(folderPath, { name, path: folderPath });
  };
  (entries.folders || []).forEach(folder => {
    addDirectFolder(folder && folder.path, folder && folder.name);
  });
  (entries.files || []).forEach(file => {
    const path = String(file && file.path || '').split('/').filter(Boolean).join('/');
    const relative = _workspaceRelativeListName(path, normalizedBase, false);
    const parts = relative.split('/').filter(Boolean);
    if (parts.length > 1) {
      addDirectFolder(normalizedBase ? `${normalizedBase}/${parts[0]}` : parts[0], parts[0]);
    } else if (parts.length === 1) {
      directFiles.push({ ...file, path, name: parts[0] });
    }
  });
  return {
    folders: [...directFolders.values()].sort((a, b) => a.name.localeCompare(b.name)),
    files: directFiles.sort((a, b) => String(a.name || '').localeCompare(String(b.name || ''))),
  };
}

function _workspaceRecursiveEntries(base = '') {
  const folders = [];
  const files = [];
  const seenFolders = new Set();
  const queue = [String(base || '').split('/').filter(Boolean).join('/')];
  while (queue.length) {
    const current = queue.shift();
    const getDirectoryEntries = _runnerWorkspaceCacheApi().getDirectoryEntries;
    const entries = typeof getDirectoryEntries === 'function'
      ? getDirectoryEntries(current)
      : { folders: [], files: [] };
    (entries.folders || []).forEach((folder) => {
      const path = String(folder && folder.path || '').split('/').filter(Boolean).join('/');
      if (!path || seenFolders.has(path)) return;
      seenFolders.add(path);
      folders.push({
        ...folder,
        path,
        name: _workspaceRelativeListName(path, base, true).replace(/\/+$/, ''),
      });
      queue.push(path);
    });
    (entries.files || []).forEach((file) => {
      const path = String(file && file.path || '').split('/').filter(Boolean).join('/');
      if (!path) return;
      files.push({
        ...file,
        path,
        name: _workspaceRelativeListName(path, base, false),
      });
    });
  }
  return { folders, files };
}

function _workspaceDeleteUsageForCommand(parsed) {
  return parsed && parsed.usage ? parsed.usage : 'Usage: rm [-r|-f|-rf] <file-or-folder>';
}

async function _workspaceReadLines(path) {
  const data = await readWorkspaceFile(path);
  return _workspaceSplitLines(data && data.text || '');
}

function _workspaceStandaloneFilterSpec(parts) {
  const root = (parts[0] || '').toLowerCase();
  if (root === 'grep') {
    if (parts.length < 3) return { error: 'Usage: grep [-i|-v|-E] <search> <file>' };
    const flags = [];
    let index = 1;
    while (index < parts.length - 2 && /^-[ivE]+$/.test(parts[index])) {
      flags.push(parts[index]);
      index += 1;
    }
    if (index !== parts.length - 2) return { error: 'Usage: grep [-i|-v|-E] <search> <file>' };
    const stage = _parseSyntheticPostFilterCommand(`cat x | grep ${flags.join(' ')} ${JSON.stringify(parts[index])}`);
    if (!stage) return { error: 'grep supports only -i, -v, and -E.' };
    return { path: parts[index + 1], spec: stage };
  }
  if (root === 'head' || root === 'tail') {
    if (parts.length < 2) return { error: `Usage: ${root} [-n N] <file>` };
    const file = parts[parts.length - 1];
    const option = parts.slice(1, -1).join(' ');
    const stage = _parseSyntheticPostFilterCommand(`cat x | ${root}${option ? ' ' + option : ''}`);
    if (!stage) return { error: `Usage: ${root} [-n N] <file>` };
    return { path: file, spec: stage };
  }
  if (root === 'wc') {
    if (parts.length !== 3 || parts[1] !== '-l') return { error: 'Usage: wc -l <file>' };
    return { path: parts[2], spec: _parseSyntheticPostFilterCommand('cat x | wc -l') };
  }
  if (root === 'sort') {
    if (parts.length < 2 || parts.length > 3) return { error: 'Usage: sort [-r|-n|-u|-rn] <file>' };
    const file = parts[parts.length - 1];
    const option = parts.length === 3 ? parts[1] : '';
    const stage = _parseSyntheticPostFilterCommand(`cat x | sort${option ? ' ' + option : ''}`);
    if (!stage) return { error: 'sort supports only -r, -n, and -u flags.' };
    return { path: file, spec: stage };
  }
  if (root === 'uniq') {
    if (parts.length < 2 || parts.length > 3) return { error: 'Usage: uniq [-c] <file>' };
    const file = parts[parts.length - 1];
    const option = parts.length === 3 ? parts[1] : '';
    const stage = _parseSyntheticPostFilterCommand(`cat x | uniq${option ? ' ' + option : ''}`);
    if (!stage) return { error: 'uniq supports only -c.' };
    return { path: file, spec: stage };
  }
  return null;
}

async function _runWorkspaceListCommand(parts, tabId) {
  const parsed = _runnerWorkspaceListCommandAdapter(parts);
  if (!parsed || parsed.invalid) throw new Error(parsed?.usage || 'Usage: ls [-l] [folder]');
  const rawTarget = parsed.target;
  await _runnerEnsureWorkspaceCacheAdapter();
  if (_runnerWorkspacePathHasGlobAdapter(rawTarget)) {
    const matches = _runnerWorkspaceExpandPathPatternAdapter(rawTarget, { cwd: _runnerWorkspaceCwdAdapter(tabId), kind: 'any', defaultToCwd: true });
    if (!matches.length) throw new Error(`no matches: ${rawTarget}`);
    const entries = {
      folders: matches
        .filter(item => item.kind === 'directory')
        .map(item => ({
          path: item.path,
          name: _workspaceRelativeListName(item.path, _runnerWorkspaceCwdAdapter(tabId), true).replace(/\/+$/, ''),
        })),
      files: matches
        .filter(item => item.kind === 'file')
        .map(item => ({
          ...(item.item || {}),
          path: item.path,
          name: _workspaceRelativeListName(item.path, _runnerWorkspaceCwdAdapter(tabId), false),
        })),
    };
    return parsed.long ? _workspaceListLines(entries, '') : _workspaceShortListLines(entries);
  }
  const target = _runnerResolveExistingWorkspaceCommandPathAdapter(rawTarget, { cwd: _runnerWorkspaceCwdAdapter(tabId), kind: 'directory', defaultToCwd: true });
  const getDirectoryEntries = _runnerWorkspaceCacheApi().getDirectoryEntries;
  const entries = typeof getDirectoryEntries === 'function'
    ? getDirectoryEntries(target)
    : { folders: [], files: [] };
  const isRoot = !target;
  const directoryExists = isRoot || _runnerWorkspacePathExistsAdapter(target, 'directory');
  const getFileHints = _runnerWorkspaceCacheApi().getFileHints;
  const fileHints = typeof getFileHints === 'function' ? getFileHints() : [];
  const file = fileHints.find(item => String(item.value || '') === target);
  if (!directoryExists && file) return [_workspacePlainLine(target)];
  if (!directoryExists) throw new Error(`folder not found: ${_runnerWorkspaceDisplayPathAdapter(target)}`);
  const listingEntries = parsed.recursive ? _workspaceRecursiveEntries(target) : _workspaceDirectListEntries(entries, target);
  return parsed.long ? _workspaceListLines(listingEntries, target) : _workspaceShortListLines(listingEntries);
}

function _workspacePipeInputLinesForCommand(baseCommand, capturedLines, tabId) {
  const parts = _runnerWorkspaceCommandTokensAdapter(baseCommand);
  const root = (parts[0] || '').toLowerCase();
  const action = (parts[1] || '').toLowerCase();
  if (!(root === 'ls' || root === 'll' || (root === 'file' && ['list', 'ls'].includes(action)))) {
    return capturedLines;
  }
  const parsed = _runnerWorkspaceListCommandAdapter(parts);
  if (!parsed || parsed.invalid || parsed.long) return capturedLines;
  try {
    const rawTarget = parsed.target;
    if (_runnerWorkspacePathHasGlobAdapter(rawTarget)) {
      const matches = _runnerWorkspaceExpandPathPatternAdapter(rawTarget, {
        cwd: _runnerWorkspaceCwdAdapter(tabId),
        kind: 'any',
        defaultToCwd: true,
      });
      if (!matches.length) return capturedLines;
      return matches.map((item) => {
        const name = _workspaceRelativeListName(item.path, _runnerWorkspaceCwdAdapter(tabId), item.kind === 'directory');
        return _workspacePlainLine(item.kind === 'directory' ? `${name.replace(/\/+$/, '')}/` : name);
      });
    }
    const target = _runnerResolveExistingWorkspaceCommandPathAdapter(rawTarget, {
      cwd: _runnerWorkspaceCwdAdapter(tabId),
      kind: 'directory',
      defaultToCwd: true,
    });
    const isRoot = !target;
    const directoryExists = isRoot || _runnerWorkspacePathExistsAdapter(target, 'directory');
    const getFileHints = _runnerWorkspaceCacheApi().getFileHints;
    const fileHints = typeof getFileHints === 'function' ? getFileHints() : [];
    const file = fileHints.find(item => String(item.value || '') === target);
    if (!directoryExists || file) return capturedLines;
    const getDirectoryEntries = _runnerWorkspaceCacheApi().getDirectoryEntries;
    const entries = typeof getDirectoryEntries === 'function'
      ? getDirectoryEntries(target)
      : { folders: [], files: [] };
    const listingEntries = parsed.recursive ? _workspaceRecursiveEntries(target) : _workspaceDirectListEntries(entries, target);
    const names = _workspaceListNames(listingEntries);
    return names.length ? names.map(name => _workspacePlainLine(name)) : capturedLines;
  } catch (_) {
    return capturedLines;
  }
}

async function _handleWorkspaceTerminalCommand(cmd, tabId) {
  const parts = _runnerWorkspaceCommandTokensAdapter(cmd);
  const root = (parts[0] || '').toLowerCase();
  const action = (parts[1] || '').toLowerCase();
  appendCommandEcho(cmd, tabId);
  try {
    let outputLines = [];
    if (root === 'pwd') {
      outputLines = [_workspacePlainLine(_runnerWorkspaceDisplayPathAdapter(_runnerWorkspaceCwdAdapter(tabId)))];
    } else if (root === 'cd') {
      if (parts.length > 2) throw new Error('Usage: cd [folder]');
      await _runnerEnsureWorkspaceCacheAdapter();
      const target = _runnerResolveExistingWorkspaceCommandPathAdapter(parts[1] || '/', { cwd: _runnerWorkspaceCwdAdapter(tabId), kind: 'directory', defaultToCwd: false });
      if (target && !_runnerWorkspacePathExistsAdapter(target, 'directory')) {
        throw new Error(`folder not found: ${_runnerWorkspaceDisplayPathAdapter(target)}`);
      }
      _runnerSetWorkspaceCwdAdapter(tabId, target);
      outputLines = [_workspacePlainLine(_runnerWorkspaceDisplayPathAdapter(target))];
    } else if (root === 'ls' || root === 'll' || (root === 'file' && ['list', 'ls'].includes(action))) {
      outputLines = await _runWorkspaceListCommand(parts, tabId);
    } else if (root === 'cat' || (root === 'file' && action === 'show')) {
      const rawTarget = root === 'cat' ? parts[1] : parts[2];
      if (!rawTarget || (root === 'cat' ? parts.length !== 2 : parts.length !== 3)) {
        throw new Error(root === 'cat' ? 'Usage: cat <file>' : 'Usage: file show <file>');
      }
      await _runnerEnsureWorkspaceCacheAdapter();
      const target = _runnerResolveExistingWorkspaceCommandPathAdapter(rawTarget, { cwd: _runnerWorkspaceCwdAdapter(tabId), kind: 'file' });
      outputLines = await _workspaceReadLines(target);
    } else if (root === 'mkdir' || (root === 'file' && ['add-dir', 'mkdir'].includes(action))) {
      if (!_workspaceTerminalCanWrite('create folders in Files')) {
        throw new Error(_workspaceTerminalDeniedMessage('create folders in Files'));
      }
      const rawTarget = root === 'mkdir' ? parts[1] : parts[2];
      if (!rawTarget || (root === 'mkdir' ? parts.length !== 2 : parts.length !== 3)) {
        throw new Error(root === 'mkdir' ? 'Usage: mkdir <folder>' : 'Usage: file add-dir <folder>');
      }
      const target = _runnerResolveWorkspaceCommandPathAdapter(rawTarget, { cwd: _runnerWorkspaceCwdAdapter(tabId) });
      const data = await createWorkspaceDirectory(target);
      const path = data && data.directory && data.directory.path ? data.directory.path : target;
      outputLines = [_workspacePlainLine(`file: created folder ${path}`)];
    } else {
      const parsed = _workspaceStandaloneFilterSpec(parts);
      if (!parsed || parsed.error) throw new Error(parsed && parsed.error ? parsed.error : 'unsupported workspace command');
      await _runnerEnsureWorkspaceCacheAdapter();
      const target = _runnerResolveExistingWorkspaceCommandPathAdapter(parsed.path, { cwd: _runnerWorkspaceCwdAdapter(tabId), kind: 'file' });
      const inputLines = await _workspaceReadLines(target);
      outputLines = _applySyntheticPostFilterLines(inputLines, parsed.spec);
    }
    outputLines.forEach(line => appendLine(line.text, line.cls || '', tabId));
    _recordSuccessfulLocalCommand(cmd);
    _persistClientSideRun(cmd, outputLines, 'ok');
    setStatus('ok');
  } catch (err) {
    appendLine(`[error] ${err.message || 'workspace command failed'}`, 'exit-fail', tabId);
    logClientError('workspace terminal command', err);
    setStatus('fail');
  }
}

async function _handleSessionTokenCommand(cmd, tabId) {
  const parts = cmd.trim().split(/\s+/);
  const sub = (parts[1] || '').toLowerCase();
  appendCommandEcho(cmd);
  if (sub === 'generate') {
    await _sessionTokenGenerate(tabId);
  } else if (sub === 'copy') {
    await _sessionTokenCopy(tabId);
  } else if (sub === 'set') {
    const value = parts.slice(2).join(' ').trim();
    await _sessionTokenSet(value, tabId);
  } else if (sub === 'clear') {
    await _sessionTokenClear(tabId);
  } else if (sub === 'rotate') {
    await _sessionTokenRotate(tabId);
  } else if (sub === 'list') {
    await _sessionTokenList(tabId);
  } else if (sub === 'revoke') {
    const value = parts.slice(2).join(' ').trim();
    await _sessionTokenRevoke(value, tabId);
  } else {
    appendLine(`session-token: unknown subcommand '${sub}'`, 'exit-fail', tabId);
    appendLine('usage: session-token [generate | copy | set <value> | clear | rotate | list | revoke <token>]', '', tabId);
    setStatus('fail');
  }
}

async function _handleWorkspaceDeleteCommand(cmd, tabId) {
  const parsedDelete = _runnerWorkspaceDeleteCommandAdapter(cmd);
  let target = parsedDelete && !parsedDelete.invalid ? parsedDelete.target : '';
  appendCommandEcho(cmd);
  if (!_workspaceTerminalCanWrite('delete Files')) {
    appendLine(`[error] ${_workspaceTerminalDeniedMessage('delete Files')}`, 'exit-fail', tabId);
    setStatus('fail');
    return;
  }
  if (!target) {
    appendLine(_workspaceDeleteUsageForCommand(parsedDelete), 'exit-fail', tabId);
    setStatus('fail');
    return;
  }
  let targetInfo = null;
  let targetInfos = [];
  try {
    await _runnerEnsureWorkspaceCacheAdapter();
    const expandedTargets = _runnerWorkspacePathHasGlobAdapter(target)
      ? _runnerWorkspaceExpandPathPatternAdapter(target, { cwd: _runnerWorkspaceCwdAdapter(tabId), kind: 'any' })
      : [{ path: _runnerResolveExistingWorkspaceCommandPathAdapter(target, { cwd: _runnerWorkspaceCwdAdapter(tabId), kind: 'any' }) }];
    if (!expandedTargets.length) {
      throw new Error(`no matches: ${target}`);
    }
    targetInfos = [];
    for (const expandedTarget of expandedTargets) {
      const path = String(expandedTarget && expandedTarget.path || '').split('/').filter(Boolean).join('/');
      const existsResp = await apiFetch(`/workspace/files/info?path=${encodeURIComponent(path)}`);
      if (!existsResp.ok) {
        const data = await existsResp.json().catch(() => ({}));
        throw new Error(data && data.error ? data.error : `file or folder was not found (${existsResp.status})`);
      }
      const info = await existsResp.json().catch(() => ({}));
      targetInfos.push({ ...info, path: info && info.path ? String(info.path) : path });
    }
    targetInfo = targetInfos[0] || null;
    target = targetInfos.length === 1 ? String(targetInfo && targetInfo.path || target) : target;
  } catch (err) {
    appendLine(`[error] ${err.message || 'file or folder was not found'}`, 'exit-fail', tabId);
    logClientError('file rm validate', err);
    setStatus('fail');
    return;
  }
  const isMultiDelete = targetInfos.length > 1;
  const directoryInfos = targetInfos.filter(info => info && info.kind === 'directory');
  const isDirectory = targetInfo && targetInfo.kind === 'directory';
  const fileCount = targetInfos.reduce((total, info) => total + (Number(info && info.file_count) || 0), 0);
  if (directoryInfos.length && !(parsedDelete && parsedDelete.recursive)) {
    const folderLabel = directoryInfos.length === 1 ? String(directoryInfos[0].path || target) : `${directoryInfos.length} folders`;
    const matchedText = isMultiDelete ? `${folderLabel} matched` : `${folderLabel} is a folder`;
    appendLine(`[error] ${matchedText}; use rm -r ${target} or file delete -r ${target}`, 'exit-fail', tabId);
    setStatus('fail');
    return;
  }
  appendLine(
    isMultiDelete
      ? `delete ${targetInfos.length} matched session items for '${target}'?`
      : `delete session ${isDirectory ? 'folder' : 'file'} '${target}'?`,
    '',
    tabId,
  );
  if (directoryInfos.length && fileCount > 0) {
    appendLine(`warning: this will also delete ${fileCount} ${fileCount === 1 ? 'file' : 'files'} in this folder.`, 'warning', tabId);
  }
  _setPendingTerminalConfirm({
    tabId,
    onYes: async () => {
      try {
        const removedLines = [];
        for (const info of targetInfos) {
          const path = String(info && info.path || '').split('/').filter(Boolean).join('/');
          const resp = await apiFetch(`/workspace/files?path=${encodeURIComponent(path)}`, { method: 'DELETE' });
          if (!resp.ok) {
            const data = await resp.json().catch(() => ({}));
            throw new Error(data && data.error ? data.error : `file delete failed (${resp.status})`);
          }
          const removedText = info && info.kind === 'directory' ? `file: removed folder ${path}` : `file: removed ${path}`;
          removedLines.push({ text: removedText });
          appendLine(removedText, '', tabId);
        }
        _runnerWorkspaceCacheApi().refresh?.();
        _recordSuccessfulLocalCommand(cmd);
        _persistClientSideRun(cmd, removedLines, 'ok');
        setStatus('ok');
      } catch (err) {
        appendLine(`[error] ${err.message || 'network error'}`, 'exit-fail', tabId);
        logClientError('file rm', err);
        setStatus('fail');
      }
    },
    onNo: async () => {
      appendLine(`Session ${isMultiDelete ? 'items' : (isDirectory ? 'folder' : 'file')} delete canceled.`, '', tabId);
      setStatus('idle');
    },
  });
  setStatus('idle');
}

async function _handleWorkspaceMoveCommand(cmd, tabId) {
  const parsed = _runnerWorkspaceMoveCommandAdapter(cmd);
  appendCommandEcho(cmd);
  if (!_workspaceTerminalCanWrite('move Files')) {
    appendLine(`[error] ${_workspaceTerminalDeniedMessage('move Files')}`, 'exit-fail', tabId);
    setStatus('fail');
    return;
  }
  if (!parsed || parsed.invalid || !parsed.source || !parsed.destination) {
    appendLine(parsed?.usage || 'Usage: file move <source> <destination>', 'exit-fail', tabId);
    setStatus('fail');
    return;
  }
  if (typeof moveWorkspacePath !== 'function') {
    appendLine('[error] Files move is not ready — reload the page and try again', 'exit-fail', tabId);
    setStatus('fail');
    return;
  }
  try {
    await _runnerEnsureWorkspaceCacheAdapter();
    const sources = _runnerWorkspacePathHasGlobAdapter(parsed.source)
      ? _runnerWorkspaceExpandPathPatternAdapter(parsed.source, { cwd: _runnerWorkspaceCwdAdapter(tabId), kind: 'any' })
      : [{ path: _runnerResolveExistingWorkspaceCommandPathAdapter(parsed.source, { cwd: _runnerWorkspaceCwdAdapter(tabId), kind: 'any' }) }];
    if (!sources.length) {
      throw new Error(`no matches: ${parsed.source}`);
    }
    const destination = _runnerResolveWorkspaceCommandPathAdapter(parsed.destination, { cwd: _runnerWorkspaceCwdAdapter(tabId) });
    const movingMultiple = sources.length > 1;
    if (movingMultiple && !_runnerWorkspacePathExistsAdapter(destination, 'directory')) {
      throw new Error('destination must be an existing folder when moving multiple matches');
    }
    const movedLines = [];
    for (const sourceEntry of sources) {
      const source = String(sourceEntry && sourceEntry.path || '').split('/').filter(Boolean).join('/');
      const data = await moveWorkspacePath(source, destination);
      const moved = data && data.moved ? data.moved : {};
      const text = `file: moved ${moved.source || source} to ${moved.destination || destination}`;
      movedLines.push({ text });
      appendLine(text, '', tabId);
    }
    _runnerWorkspaceCacheApi().refresh?.();
    _recordSuccessfulLocalCommand(cmd);
    _persistClientSideRun(cmd, movedLines, 'ok');
    setStatus('ok');
  } catch (err) {
    appendLine(`[error] ${err.message || 'file move failed'}`, 'exit-fail', tabId);
    logClientError('file move', err);
    setStatus('fail');
  }
}

async function _handleWorkspaceEditorCommand(cmd, tabId) {
  const parsed = _runnerWorkspaceEditorCommandAdapter(cmd);
  appendCommandEcho(cmd);
  const writeAction = parsed && parsed.action === 'edit' ? 'edit Files' : 'create Files';
  if (!_workspaceTerminalCanWrite(writeAction)) {
    appendLine(`[error] ${_workspaceTerminalDeniedMessage(writeAction)}`, 'exit-fail', tabId);
    setStatus('fail');
    return;
  }
  if (!parsed || parsed.invalid || (parsed.action === 'edit' && !parsed.target)) {
    const action = parsed?.action || 'add';
    const operand = action === 'add' ? '[file]' : '<file>';
    appendLine(`Usage: file ${action} ${operand}`, 'exit-fail', tabId);
    setStatus('fail');
    return;
  }
  if (typeof openWorkspaceEditorFromCommand !== 'function') {
    appendLine('[error] Files panel is not ready — reload the page and try again', 'exit-fail', tabId);
    setStatus('fail');
    return;
  }
  try {
    if (parsed.action === 'edit') await _runnerEnsureWorkspaceCacheAdapter();
    const target = parsed.target
      ? (parsed.action === 'edit'
          ? _runnerResolveExistingWorkspaceCommandPathAdapter(parsed.target, { cwd: _runnerWorkspaceCwdAdapter(tabId), kind: 'file' })
          : _runnerResolveWorkspaceCommandPathAdapter(parsed.target, { cwd: _runnerWorkspaceCwdAdapter(tabId) }))
      : '';
    const opened = await openWorkspaceEditorFromCommand(parsed.action, target);
    if (opened === false) throw new Error(_workspaceTerminalDeniedMessage(writeAction));
    const targetLabel = target ? ` ${target}` : '';
    appendLine(`file: opened${targetLabel} in the file editor`, '', tabId);
    _recordSuccessfulLocalCommand(cmd);
    _persistClientSideRun(cmd, [{ text: `file: opened${targetLabel} in the file editor` }], 'ok');
    setStatus('ok');
  } catch (err) {
    appendLine(`[error] ${err.message || 'network error'}`, 'exit-fail', tabId);
    logClientError(`file ${parsed.action}`, err);
    setStatus('fail');
  }
}

async function _handleWorkspaceDownloadCommand(cmd, tabId) {
  let target = _runnerWorkspaceDownloadTargetAdapter(cmd);
  appendCommandEcho(cmd);
  if (!target) {
    appendLine('Usage: file download <file>', 'exit-fail', tabId);
    setStatus('fail');
    return;
  }
  if (typeof downloadWorkspaceFile !== 'function') {
    appendLine('[error] Files download is not ready — reload the page and try again', 'exit-fail', tabId);
    setStatus('fail');
    return;
  }
  try {
    await _runnerEnsureWorkspaceCacheAdapter();
    target = _runnerResolveExistingWorkspaceCommandPathAdapter(target, { cwd: _runnerWorkspaceCwdAdapter(tabId), kind: 'file' });
    const downloaded = await downloadWorkspaceFile(target);
    if (!downloaded) throw new Error('file download failed');
    const text = `file: downloading ${target}`;
    appendLine(text, '', tabId);
    _recordSuccessfulLocalCommand(cmd);
    _persistClientSideRun(cmd, [{ text }], 'ok');
    setStatus('ok');
  } catch (err) {
    appendLine(`[error] ${err.message || 'network error'}`, 'exit-fail', tabId);
    logClientError('file download', err);
    setStatus('fail');
  }
}

async function _runClientSideCommandWithOptionalPipe(cmd, tabId, runBaseCommand) {
  const spec = _parseSyntheticPostFilterCommand(cmd);
  const baseCommand = spec ? (spec.baseCommand || cmd) : cmd;
  const capturedLines = [];
  const originalAppendLine = appendLine;
  const originalAppendCommandEcho = appendCommandEcho;
  const originalRecordSuccessfulLocalCommand = _recordSuccessfulLocalCommand;
  const originalPersistSessionTokenRun = _persistSessionTokenRun;
  const originalPersistClientSideRun = _persistClientSideRun;
  const originalSetStatus = setStatus;
  let finalStatus = 'idle';
  const tab = typeof getTab === 'function' ? getTab(tabId) : null;
  if (tab) {
    tab.command = cmd;
  }

  if (tabId === _runnerActiveTabId()) originalSetStatus('running');
  if (typeof setTabStatus === 'function') setTabStatus(tabId, 'running');
  appendCommandEcho(cmd, tabId);
  try {
    _recordSuccessfulLocalCommand = () => {};
    _persistSessionTokenRun = () => {};
    _persistClientSideRun = () => {};
    setStatus = (statusValue) => {
      if (typeof _runnerActiveTabId() === 'undefined' || _runnerActiveTabId() === tabId) {
        finalStatus = statusValue;
      }
      originalSetStatus(statusValue);
    };
    appendCommandEcho = (echoCommand, echoTabId = null) => {
      const targetTabId = echoTabId || (typeof _runnerActiveTabId() !== 'undefined' ? _runnerActiveTabId() : tabId);
      if (targetTabId === tabId) return;
      originalAppendCommandEcho(echoCommand, echoTabId);
    };
    appendLine = (text, cls = '', lineTabId = null, metadata = null) => {
      const targetTabId = lineTabId || (typeof _runnerActiveTabId() !== 'undefined' ? _runnerActiveTabId() : tabId);
      if (targetTabId !== tabId) {
        originalAppendLine(text, cls, lineTabId, metadata);
        return;
      }
      capturedLines.push({
        text: String(text ?? ''),
        cls: String(cls || ''),
        tabId: targetTabId,
        metadata,
      });
    };
    const result = runBaseCommand(baseCommand);
    if (!_pendingTerminalConfirm) await result;
  } finally {
    appendLine = originalAppendLine;
    appendCommandEcho = originalAppendCommandEcho;
    _recordSuccessfulLocalCommand = originalRecordSuccessfulLocalCommand;
    _persistSessionTokenRun = originalPersistSessionTokenRun;
    _persistClientSideRun = originalPersistClientSideRun;
    setStatus = originalSetStatus;
  }

  const pipeInputLines = spec ? _workspacePipeInputLinesForCommand(baseCommand, capturedLines, tabId) : capturedLines;
  const outputLines = spec ? _applySyntheticPostFilterLines(pipeInputLines, spec) : capturedLines;
  outputLines.forEach((line) => {
    if (line.metadata) originalAppendLine(line.text, line.cls || '', tabId, line.metadata);
    else originalAppendLine(line.text, line.cls || '', tabId);
  });
  if (!_pendingTerminalConfirm) {
    _finalizeClientSideCommandStatus(tabId, finalStatus);
    if (finalStatus !== 'fail') _recordSuccessfulLocalCommand(cmd);
    _persistClientSideRun(cmd, outputLines, finalStatus, tabId);
  } else if (typeof setTabStatus === 'function') {
    setTabStatus(tabId, finalStatus === 'fail' ? 'fail' : 'idle');
  }
}

// ── End session token handlers ───────────────────────────────────────────────

function submitCommand(rawCmd) {
  // This is the main run path: validate local state, open the SSE stream, then
  // feed output into the active tab while mirroring completion into persistence.
  const cmd = (rawCmd || '').trim();
  if (!cmd) {
    if (_isWelcomeActive() && !_isWelcomeDone() && _welcomeOwns(_runnerActiveTabId())) {
      _requestWelcomeSettle(_runnerActiveTabId());
      return 'settle';
    }
    const _activeTab = getActiveTab();
    if (_activeTab && _activeTab.st === 'running') return true;
    appendPromptNewline(_runnerActiveTabId());
    setStatus('idle');
    return true;
  }

  // Intercept yes/no answer to a pending terminal confirmation prompt.
  if (_pendingTerminalConfirm) {
    const pending = _pendingTerminalConfirm;
    const promptTabId = pending.tabId || _runnerActiveTabId();
    appendCommandEcho(cmd, promptTabId);
    if (pending.kind === 'text') {
      _setPendingTerminalConfirm(null);
      Promise.resolve(typeof pending.onAnswer === 'function' ? pending.onAnswer(cmd) : undefined).catch((err) => {
        appendLine(`[error] ${err.message || 'network error'}`, 'exit-fail', promptTabId);
        setStatus('fail');
      });
      return true;
    }
    const answer = cmd.trim().toLowerCase();
    if (answer !== 'yes' && answer !== 'y' && answer !== 'no' && answer !== 'n') {
      appendLine('please answer yes or no', 'notice', promptTabId);
      return true;
    }
    _setPendingTerminalConfirm(null);
    if (answer === 'yes' || answer === 'y') {
      _runPendingTerminalConfirmHandler(promptTabId, pending.onYes).catch((err) => {
        appendLine(`[error] ${err.message || 'network error'}`, 'exit-fail', promptTabId);
        setStatus('fail');
        _finalizeClientSideCommandStatus(promptTabId, 'fail');
      });
    } else {
      _runPendingTerminalConfirmHandler(promptTabId, pending.onNo).catch((err) => {
        appendLine(`[error] ${err.message || 'network error'}`, 'exit-fail', promptTabId);
        setStatus('fail');
        _finalizeClientSideCommandStatus(promptTabId, 'fail');
      });
    }
    return true;
  }

  // If the active tab is currently running a command, open a new tab automatically
  // rather than streaming two commands' output on top of each other.
  // Use tab.st (set synchronously by setTabStatus) rather than tab.runId (set
  // asynchronously via SSE) to avoid a race condition where rapid Enter presses
  // fire before the server's 'started' message arrives.
  // If the welcome typeout is still running, cancel it and clear partial output
  if (_welcomeOwns(_runnerActiveTabId())) {
    _cancelWelcome(_runnerActiveTabId());
    clearTab(_runnerActiveTabId());
  }

  const activeTab = getActiveTab();
  if (activeTab && activeTab.st === 'running') {
    const newId = createTab(typeof createDefaultTabLabel === 'function'
      ? createDefaultTabLabel()
      : 'shell ' + (_runnerTabs().length + 1));
    if (!newId) return false; // tab limit reached — createTab already showed a toast
    // createTab calls activateTab internally, so the active tab id now points to the new tab
  }

  // Client-side validation mirrors server-side checks for immediate feedback
  const shellOps = /&&|\|\|?|;;?|`|\$\(|>>?|</;
  if (shellOps.test(cmd) && !_isSyntheticPostFilterCommand(cmd) && !_isExactSpecialBuiltInCommand(cmd)) {
    appendCommandEcho(cmd);
    appendLine('[denied] Shell operators (&&, |, ;, >, etc.) are not permitted.', 'denied');
    setStatus('fail');
    setLastExit(1);
    setTabStatus(_runnerActiveTabId(), 'fail');
    return false;
  }

  if (/(?<![\w:\/])\/data\b/.test(cmd) || /(?<![\w:\/])\/tmp\b/.test(cmd)) {
    appendCommandEcho(cmd);
    appendLine('[denied] Access to /data and /tmp is not permitted.', 'denied');
    setStatus('fail');
    setLastExit(1);
    setTabStatus(_runnerActiveTabId(), 'fail');
    return false;
  }

  if (_isTabCloseCommand(cmd)) {
    const closeActiveTab = typeof importedCloseTab === 'function'
      ? importedCloseTab
      : (typeof closeTab === 'function' ? closeTab : null);
    if (closeActiveTab) closeActiveTab(_runnerActiveTabId());
    return true;
  }

  addToHistory(_historySafeCommand(cmd));
  if (typeof rememberRecentValuesFromCommand === 'function') {
    try { rememberRecentValuesFromCommand(cmd); } catch (_) { /* autocomplete recents are best-effort */ }
  }

  if (typeof isInteractivePtyCommand === 'function' && isInteractivePtyCommand(cmd)) {
    void startInteractivePtyCommand(cmd, _runnerActiveTabId());
    return true;
  }

  // Session-token subcommands (generate / set / clear / rotate) run entirely
  // client-side.  The bare 'session-token' status command goes to the server.
  if (_isSessionTokenSubcommand(cmd)) {
    void _runClientSideCommandWithOptionalPipe(cmd, _runnerActiveTabId(), (baseCommand) => (
      _handleSessionTokenCommand(baseCommand, _runnerActiveTabId())
    ));
    return true;
  }

  if (_isClientSideSecretSetCommand(cmd)) {
    const safeCommand = _historySafeCommand(cmd);
    void _runClientSideCommandWithOptionalPipe(safeCommand, _runnerActiveTabId(), (baseCommand) => {
      if (typeof _runnerHandleSecretCommandAdapter === 'function') {
        return _runnerHandleSecretCommandAdapter(baseCommand, _runnerActiveTabId());
      }
      appendLine('[error] secret prompt is not ready — reload the page and try again', 'exit-fail', _runnerActiveTabId());
      setStatus('fail');
      return true;
    });
    return true;
  }

  if (_runnerIsWorkspaceTerminalCommandAdapter(cmd)) {
    void _runClientSideCommandWithOptionalPipe(cmd, _runnerActiveTabId(), (baseCommand) => (
      _handleWorkspaceTerminalCommand(baseCommand, _runnerActiveTabId())
    ));
    return true;
  }

  if (_runnerIsWorkspaceDeleteCommandAdapter(cmd)) {
    void _runClientSideCommandWithOptionalPipe(cmd, _runnerActiveTabId(), (baseCommand) => (
      _handleWorkspaceDeleteCommand(baseCommand, _runnerActiveTabId())
    ));
    return true;
  }

  if (_runnerIsWorkspaceMoveCommandAdapter(cmd)) {
    void _runClientSideCommandWithOptionalPipe(cmd, _runnerActiveTabId(), (baseCommand) => (
      _handleWorkspaceMoveCommand(baseCommand, _runnerActiveTabId())
    ));
    return true;
  }

  if (_runnerIsWorkspaceEditorCommandAdapter(cmd)) {
    void _runClientSideCommandWithOptionalPipe(cmd, _runnerActiveTabId(), (baseCommand) => (
      _handleWorkspaceEditorCommand(baseCommand, _runnerActiveTabId())
    ));
    return true;
  }

  if (_runnerIsWorkspaceDownloadCommandAdapter(cmd)) {
    void _runClientSideCommandWithOptionalPipe(cmd, _runnerActiveTabId(), (baseCommand) => (
      _handleWorkspaceDownloadCommand(baseCommand, _runnerActiveTabId())
    ));
    return true;
  }

  if (String(cmd || '').trim().toLowerCase().split(/\s+/, 1)[0] === 'workflow') {
    if (typeof _runnerHandleWorkflowTerminalCommandAdapter === 'function') {
      void _runnerHandleWorkflowTerminalCommandAdapter(cmd, _runnerActiveTabId());
      return true;
    }
    appendCommandEcho(cmd);
    appendLine('[error] workflow command is not ready — reload the page and try again', 'exit-fail', _runnerActiveTabId());
    setStatus('fail');
    return true;
  }

  if (_isClientSideUiCommand(cmd)) {
    const root = cmd.trim().split(/\s+/, 1)[0].toLowerCase();
    if (root === 'theme' && typeof _runnerHandleThemeCommandAdapter === 'function') {
      void _runClientSideCommandWithOptionalPipe(cmd, _runnerActiveTabId(), (baseCommand) => (
        _runnerHandleThemeCommandAdapter(baseCommand, _runnerActiveTabId())
      ));
      return true;
    }
    if (root === 'config' && typeof _runnerHandleConfigCommandAdapter === 'function') {
      void _runClientSideCommandWithOptionalPipe(cmd, _runnerActiveTabId(), (baseCommand) => (
        _runnerHandleConfigCommandAdapter(baseCommand, _runnerActiveTabId())
      ));
      return true;
    }
    if (root === 'tour' && typeof _runnerHandleTourCommandAdapter === 'function') {
      void _runClientSideCommandWithOptionalPipe(cmd, _runnerActiveTabId(), (baseCommand) => (
        _runnerHandleTourCommandAdapter(baseCommand, _runnerActiveTabId())
      ));
      return true;
    }
    appendCommandEcho(cmd);
    appendLine(`[error] ${root} command is not ready — reload the page and try again`, 'exit-fail', _runnerActiveTabId());
    setStatus('fail');
    return true;
  }

  if (!_runActiveTeamScopeCan('run_commands')) {
    appendCommandEcho(cmd);
    appendLine(`[denied] ${_runStartDeniedMessage()}`, 'denied', _runnerActiveTabId());
    setStatus('fail');
    setTabStatus(_runnerActiveTabId(), 'fail');
    return true;
  }

  // Re-lookup the active tab after the potential createTab() call above, which
  // may have changed _runnerActiveTabId() to point at the newly created tab.
  const _runTab = getActiveTab();
  if (typeof setTabRunningCommand === 'function') {
    setTabRunningCommand(_runnerActiveTabId(), cmd);
  } else {
    if (!_runTab || !_runTab.renamed) setTabLabel(_runnerActiveTabId(), cmd);
    if (_runTab) _runTab.command = cmd;
  }
  appendCommandEcho(cmd);
  // Set runStart after the prompt line so it doesn't receive an elapsed stamp
  if (_runTab) {
    _runTab.runStart = Date.now();
    _runTab.currentRunStartIndex = _runTab.rawLines.length;
    _runTab.previewTruncated = false;
    _runTab.fullOutputAvailable = false;
    _runTab.fullOutputLoaded = false;
    _runTab.historyRunId = null;
    _runTab.reconnectedRun = false;
    _runTab.commandOutcomeSummary = null;
    _runTab.lastEventId = '';
    _runTab.attachMode = '';
    _runTab.followOutput = true;
    _runTab.deferPromptMount = false;
  }
  setStatus('running');
  setTabStatus(_runnerActiveTabId(), 'running');
  _setRunButtonDisabled(true);
  showTabKillBtn(_runnerActiveTabId());
  startTimer();

  const tabId = _runnerActiveTabId();

  apiFetch('/runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command: cmd, tab_id: tabId, workspace_cwd: _runnerWorkspaceCwdAdapter(tabId) })
  }).then(res => {
    if (res.status === 403) {
      return res.json().then(data => {
        const message = data && data.error === 'team_forbidden'
          ? _runStartDeniedMessage()
          : (data.error || data.message || 'Command not allowed.');
        appendLine('[denied] ' + message, 'denied', tabId);
        setStatus('fail'); setTabStatus(tabId, 'fail');
        stopTimer(); _setRunButtonDisabled(false); hideTabKillBtn(tabId);
      });
    }
    if (res.status === 429) {
      appendLine('[rate limited] Too many requests. Please wait a moment.', 'denied', tabId);
      setStatus('fail'); setTabStatus(tabId, 'fail');
      stopTimer(); _setRunButtonDisabled(false); hideTabKillBtn(tabId);
      return;
    }
    if (!res.ok) {
      return _readRunErrorMessage(res).then(message => {
        const suffix = message ? ` ${message}` : '';
        appendLine(`[server error] The server could not start the command.${suffix}`, 'exit-fail', tabId);
        setStatus('fail'); setTabStatus(tabId, 'fail');
        stopTimer(); _setRunButtonDisabled(false); hideTabKillBtn(tabId);
      });
    }
    return res.json().then(data => {
      const runId = data && data.run_id;
      if (!runId) {
        appendLine('[server error] The server did not return a run id.', 'exit-fail', tabId);
        setStatus('fail'); setTabStatus(tabId, 'fail');
        stopTimer(); _setRunButtonDisabled(false); hideTabKillBtn(tabId);
        return;
      }
      _markTabRunStarted(tabId, runId);
      return _subscribeRunStream(runId, tabId, { streamUrl: data.stream });
    });
  }).catch(err => {
    _clearStalledTimeout(tabId);
    _handleRunTransportFailure(err, tabId);
  });
  return true;
}

function submitComposerCommand(rawCmd, { dismissKeyboard = false, focusAfterSubmit = true } = {}) {
  const result = submitCommand(rawCmd);
  if (result === true) {
    _clearComposerInputs();
    if (focusAfterSubmit) refocusComposerAfterAction();
    if (dismissKeyboard && typeof dismissMobileKeyboardAfterSubmit === 'function') {
      dismissMobileKeyboardAfterSubmit();
    }
  } else if (result === 'settle') {
    refocusComposerAfterAction();
  }
  return result;
}

function submitVisibleComposerCommand({ rawCmd = null, dismissKeyboard = false, focusAfterSubmit = true } = {}) {
  const value = typeof rawCmd === 'string'
    ? rawCmd
    : ((typeof getComposerValue === 'function') ? getComposerValue() : '');
  return submitComposerCommand(value, { dismissKeyboard, focusAfterSubmit });
}

function runCommand() {
  if (typeof isRunButtonDisabled === 'function' && isRunButtonDisabled()) return;
  const value = typeof getComposerValue === 'function' ? getComposerValue() : (cmdInput ? cmdInput.value : '');
  submitComposerCommand(value, { dismissKeyboard: true });
}

if (typeof importedSetRunnerHandlers === 'function') {
  importedSetRunnerHandlers({
    _recordSuccessfulLocalCommand,
    _seedLocalStorageStarsToServer,
    appendCommandEcho,
    attachActiveRunFromMonitor,
    cancelPendingTerminalConfirm,
    confirmKill,
    detachRunStreamForTab,
    doKill,
    hasPendingTerminalConfirm,
    interruptPromptLine,
    killActiveRunFromMonitor,
    pauseBackgroundRunStreamsForStatusMonitor,
    resumeBackgroundRunStreamsAfterStatusMonitor,
    runCommand,
    setStatus,
    submitCommand,
    submitComposerCommand,
    submitVisibleComposerCommand,
  });
}

export {
  _finalizeClientSideCommandStatus,
  _handleRunStreamMessage,
  _markTabRunStarted,
  _persistClientSideRun,
  _recordSuccessfulLocalCommand,
  _seedLocalStorageStarsToServer,
  _setPendingTerminalConfirm,
  appendCommandEcho,
  appendPromptNewline,
  attachActiveRunFromMonitor,
  cancelPendingTerminalConfirm,
  confirmKill,
  detachRunStreamForTab,
  doKill,
  hasPendingTerminalConfirm,
  interruptPromptLine,
  killActiveRunFromMonitor,
  pauseBackgroundRunStreamsForStatusMonitor,
  resumeBackgroundRunStreamsAfterStatusMonitor,
  restoreActiveRunsAfterReload,
  runCommand,
  setStatus,
  submitCommand,
  submitComposerCommand,
  submitVisibleComposerCommand,
};
