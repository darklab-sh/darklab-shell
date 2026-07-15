// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// ── Shared history drawer logic ──
import {
  histClearAllBtn as importedHistClearAllBtn,
  histRow as importedHistRow,
  historyActiveFilters as importedHistoryActiveFilters,
  historyBulkToolbar as importedHistoryBulkToolbar,
  historyClearFiltersBtn as importedHistoryClearFiltersBtn,
  historyDateFilter as importedHistoryDateFilter,
  historyEntityInput as importedHistoryEntityInput,
  historyEntityTypeFilter as importedHistoryEntityTypeFilter,
  historyExitFilter as importedHistoryExitFilter,
  historyKindFilter as importedHistoryKindFilter,
  historyList as importedHistoryList,
  historyLoadOverlay as importedHistoryLoadOverlay,
  historyMobileFiltersToggle as importedHistoryMobileFiltersToggle,
  historyPagination as importedHistoryPagination,
  historyPaginationControls as importedHistoryPaginationControls,
  historyPaginationSummary as importedHistoryPaginationSummary,
  historyPanel as importedHistoryPanel,
  historyProjectFilter as importedHistoryProjectFilter,
  historyRootDropdown as importedHistoryRootDropdown,
  historyRootInput as importedHistoryRootInput,
  historySearchInput as importedHistorySearchInput,
  historySignalFilter as importedHistorySignalFilter,
  historyStarredToggle as importedHistoryStarredToggle,
  historyTypeFilter as importedHistoryTypeFilter,
} from './core/dom.js';
import { DarklabHistoryCore as importedHistoryCore } from './core/history_core.js';
import {
  emitUiEvent as importedEmitUiEvent,
  getAppState as importedGetAppState,
} from './core/state.js';
import {
  copyTextToClipboard as importedCopyTextToClipboard,
  downloadBlobAsAttachment as importedDownloadBlobAsAttachment,
  escapeHtml as importedEscapeHtml,
  showToast as importedShowToast,
} from './core/utils.js';
import { apiFetch as importedApiFetch } from './session.js';
import {
  blurActiveElement as importedBlurActiveElement,
  enhanceAppSelects as importedEnhanceAppSelects,
  focusElement as importedFocusElement,
  hideHistoryPanel as importedHideHistoryPanel,
  hideHistoryRow as importedHideHistoryRow,
  refocusComposerAfterAction as importedRefocusComposerAfterAction,
  setComposerValue as importedSetComposerValue,
  showHistoryPanel as importedShowHistoryPanel,
  showHistoryRow as importedShowHistoryRow,
  syncAppSelect as importedSyncAppSelect,
} from './ui/ui_helpers.js';
import { bindPressable as importedBindPressable } from './ui/ui_pressable.js';
import { showConfirm as importedShowConfirm } from './ui/ui_confirm.js';
import { openAtlas as importedOpenAtlas } from './features/atlas/atlas_bridge.js';
import { useMobileTerminalViewportMode as importedUseMobileTerminalViewportMode } from './features/mobile/mobile_shell_layout.js';
import {
  appendLine as importedAppendLine,
} from './output.js';
import {
  appendCommandEcho as importedAppendCommandEcho,
} from './runner_bridge.js';
import {
  activateTab as importedActivateTab,
} from './tabs.js';
import {
  toggleHistoryPanelSurface as importedToggleHistoryPanelSurface,
} from './controller_action_bridge.js';
import { setHistoryPanelHandlers as importedSetHistoryPanelHandlers } from './features/history/history_panel_bridge.js';
import {
  resetCmdHistoryNav as importedResetCmdHistoryNav,
} from './features/history/history_recall.js';
import {
  _closeHistoryActionMenus as importedCloseHistoryActionMenus,
  _closeHistoryRunActionMenus as importedCloseHistoryRunActionMenus,
  _getStarred as importedGetStarred,
  _positionHistoryActionMenu as importedPositionHistoryActionMenu,
  _resetHistoryActionMenuPosition as importedResetHistoryActionMenuPosition,
  _toggleStar as importedToggleStar,
} from './features/history/history_actions.js';
import {
  copyHistoryRunPermalink as importedCopyHistoryRunPermalink,
  copySnapshotLink as importedCopySnapshotLink,
  openSnapshotLink as importedOpenSnapshotLink,
} from './features/history/history_links.js';
import {
  _historyCanManageHistory as importedHistoryCanManageHistory,
  _historyMutationError as importedHistoryMutationError,
  _historyScopeDeniedMessage as importedHistoryScopeDeniedMessage,
  _historyShowPermissionDenied as importedHistoryShowPermissionDenied,
  _setHistoryLoadState as importedSetHistoryLoadState,
  confirmHistAction as importedConfirmHistAction,
} from './features/history/history_mutations.js';
import {
  _ensureHistoryProjectFilterOptions as importedEnsureHistoryProjectFilterOptions,
  _historyAddRunToActiveProject as importedHistoryAddRunToActiveProject,
  _historyAddRunToProject as importedHistoryAddRunToProject,
  _historyLoadActiveProject as importedHistoryLoadActiveProject,
  _historyLoadProjects as importedHistoryLoadProjects,
  _historyOrderProjectsForPicker as importedHistoryOrderProjectsForPicker,
  _historyProjectDisplayName as importedHistoryProjectDisplayName,
  _historyProjectFromLink as importedHistoryProjectFromLink,
  _historyProjectLabelForId as importedHistoryProjectLabelForId,
  _historyProjectPickerContent as importedHistoryProjectPickerContent,
  _historyProjectRunEntityOptionContent as importedHistoryProjectRunEntityOptionContent,
  _historyRefreshProjectRunEntityOption as importedHistoryRefreshProjectRunEntityOption,
  _historyRemoveRunFromProject as importedHistoryRemoveRunFromProject,
  _syncHistoryProjectFilterOptions as importedSyncHistoryProjectFilterOptions,
} from './features/history/history_project_actions.js';
import {
  _createHistoryEntry as importedCreateHistoryEntry,
  _createSnapshotHistoryEntry as importedCreateSnapshotHistoryEntry,
  _historyActionKeepsPanelOpen as importedHistoryActionKeepsPanelOpen,
  _historyEditEntityMetadata as importedHistoryEditEntityMetadata,
} from './features/history/history_rows.js';
import {
  _tabForHistoryRun as importedTabForHistoryRun,
  restoreHistoryRunIntoTab as importedRestoreHistoryRunIntoTab,
} from './features/history/history_restore.js';
import {
  closeHistoryCompareActionMenus as importedCloseHistoryCompareActionMenus,
  hasHistoryCompareHandler as importedHasHistoryCompareHandler,
  openHistoryCompareLauncher as importedOpenHistoryCompareLauncher,
} from './features/run-comparison/history_compare_bridge.js';
import {
  getActiveProjectContext as importedGetActiveProjectContext,
  refreshProjectWorkspace as importedRefreshProjectWorkspace,
} from './features/projects/project_context_bridge.js';

function _historyCore() {
  return (typeof importedHistoryCore !== 'undefined' && importedHistoryCore)
    || null;
}

const HISTORY_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

function _historyFn(name, imported = null) {
  if (typeof imported === 'function') return imported;
  const fn = HISTORY_GLOBAL && HISTORY_GLOBAL[name];
  return typeof fn === 'function' ? fn : null;
}

function _historyValue(name, imported = undefined) {
  if (imported !== undefined) return imported;
  if (HISTORY_GLOBAL && HISTORY_GLOBAL[name] !== undefined) return HISTORY_GLOBAL[name];
  if (
    typeof __darklabExtractGlobals !== 'undefined'
    && __darklabExtractGlobals
    && __darklabExtractGlobals[name] !== undefined
  ) {
    return __darklabExtractGlobals[name];
  }
  return undefined;
}

function _historyEl(name, imported = undefined) {
  return _historyValue(name, imported) || null;
}

function _historyAppConfig() {
  return _historyValue('APP_CONFIG') || {};
}

function _historyState() {
  const state = _historyFn('getAppState', importedGetAppState)?.();
  return state || _historyValue('APP_STATE') || {};
}

const _historyApiFetch = (...args) => _historyFn('apiFetch', importedApiFetch)?.(...args);
const _historyShowToast = (...args) => _historyFn('showToast', importedShowToast)?.(...args);
const _historyBindPressable = (...args) => _historyFn('bindPressable', importedBindPressable)?.(...args);
const _historyShowConfirm = (...args) => _historyFn('showConfirm', importedShowConfirm)?.(...args);
const _historyEmitUiEvent = (...args) => _historyFn('emitUiEvent', importedEmitUiEvent)?.(...args);
const _historyEscapeHtml = (text) => _historyFn('escapeHtml', importedEscapeHtml)?.(text) ?? String(text ?? '');
const _historyCopyTextToClipboard = (...args) => _historyFn('copyTextToClipboard', importedCopyTextToClipboard)?.(...args);
const _historyDownloadBlobAsAttachment = (...args) => {
  const globalDownloader = _historyFn('downloadBlobAsAttachment');
  const downloader = globalDownloader || _historyFn('downloadBlobAsAttachment', importedDownloadBlobAsAttachment);
  return downloader?.(...args);
};
const _historyEnhanceAppSelects = (...args) => _historyFn('enhanceAppSelects', importedEnhanceAppSelects)?.(...args);
const _historySyncAppSelect = (...args) => _historyFn('syncAppSelect', importedSyncAppSelect)?.(...args);
const _historyUseMobileTerminalViewportMode = () => !!_historyFn('useMobileTerminalViewportMode', importedUseMobileTerminalViewportMode)?.();

var histClearAllBtn = _historyEl('histClearAllBtn', importedHistClearAllBtn);
var histRow = _historyEl('histRow', importedHistRow);
var historyActiveFilters = _historyEl('historyActiveFilters', importedHistoryActiveFilters);
var historyBulkToolbar = _historyEl('historyBulkToolbar', importedHistoryBulkToolbar);
var historyClearFiltersBtn = _historyEl('historyClearFiltersBtn', importedHistoryClearFiltersBtn);
var historyDateFilter = _historyEl('historyDateFilter', importedHistoryDateFilter);
var historyEntityInput = _historyEl('historyEntityInput', importedHistoryEntityInput);
var historyEntityTypeFilter = _historyEl('historyEntityTypeFilter', importedHistoryEntityTypeFilter);
var historyExitFilter = _historyEl('historyExitFilter', importedHistoryExitFilter);
var historyKindFilter = _historyEl('historyKindFilter', importedHistoryKindFilter);
var historyList = _historyEl('historyList', importedHistoryList);
var historyLoadOverlay = _historyEl('historyLoadOverlay', importedHistoryLoadOverlay);
var historyMobileFiltersToggle = _historyEl('historyMobileFiltersToggle', importedHistoryMobileFiltersToggle);
var historyPagination = _historyEl('historyPagination', importedHistoryPagination);
var historyPaginationControls = _historyEl('historyPaginationControls', importedHistoryPaginationControls);
var historyPaginationSummary = _historyEl('historyPaginationSummary', importedHistoryPaginationSummary);
var historyPanel = _historyEl('historyPanel', importedHistoryPanel);
var historyProjectFilter = _historyEl('historyProjectFilter', importedHistoryProjectFilter);
var historyRootDropdown = _historyEl('historyRootDropdown', importedHistoryRootDropdown);
var historyRootInput = _historyEl('historyRootInput', importedHistoryRootInput);
var historySearchInput = _historyEl('historySearchInput', importedHistorySearchInput);
var historySignalFilter = _historyEl('historySignalFilter', importedHistorySignalFilter);
var historyStarredToggle = _historyEl('historyStarredToggle', importedHistoryStarredToggle);
var historyTypeFilter = _historyEl('historyTypeFilter', importedHistoryTypeFilter);
var _historyApiFetchAdapter = (...args) => _historyApiFetch(...args);
var _historyBindPressableAdapter = (...args) => _historyBindPressable(...args);
var _historyCopyTextToClipboardAdapter = (...args) => _historyCopyTextToClipboard(...args);
var _historyDownloadBlobAsAttachmentAdapter = (...args) => _historyDownloadBlobAsAttachment(...args);
var _historyEmitUiEventAdapter = (...args) => _historyEmitUiEvent(...args);
var _historyEnhanceAppSelectsAdapter = (...args) => _historyEnhanceAppSelects(...args);
var _historyEscapeHtmlAdapter = (text) => _historyEscapeHtml(text);
var _historyShowConfirmAdapter = (...args) => _historyShowConfirm(...args);
var _historyShowToastAdapter = (...args) => _historyShowToast(...args);
var _historySyncAppSelectAdapter = (...args) => _historySyncAppSelect(...args);
var _historyUseMobileTerminalViewportModeAdapter = () => _historyUseMobileTerminalViewportMode();
var _historyBlurActiveElementAdapter = (...args) => _historyFn('blurActiveElement', importedBlurActiveElement)?.(...args);
var _historyFocusElementAdapter = (...args) => _historyFn('focusElement', importedFocusElement)?.(...args);
var _historyHidePanelAdapter = (...args) => _historyFn('hideHistoryPanel', importedHideHistoryPanel)?.(...args);
var _historyHideRowAdapter = (...args) => _historyFn('hideHistoryRow', importedHideHistoryRow)?.(...args);
var _historyRefocusComposerAdapter = (...args) => _historyFn('refocusComposerAfterAction', importedRefocusComposerAfterAction)?.(...args);
var _historySetComposerValueAdapter = (...args) => _historyFn('setComposerValue', importedSetComposerValue)?.(...args);
var _historyShowPanelAdapter = (...args) => _historyFn('showHistoryPanel', importedShowHistoryPanel)?.(...args);
var _historyShowRowAdapter = (...args) => _historyFn('showHistoryRow', importedShowHistoryRow)?.(...args);
var _historyResetCmdNavAdapter = (...args) => _historyFn('resetCmdHistoryNav', importedResetCmdHistoryNav)?.(...args);
var _historyTogglePanelSurfaceAdapter = (...args) => _historyFn('toggleHistoryPanelSurface', importedToggleHistoryPanelSurface)?.(...args);
var _historyAppendLineAdapter = (...args) => _historyFn('appendLine', importedAppendLine)?.(...args);
var _historyAppendCommandEchoAdapter = (...args) => _historyFn('appendCommandEcho', importedAppendCommandEcho)?.(...args);
var _historyActivateTabAdapter = (...args) => _historyFn('activateTab', importedActivateTab)?.(...args);
var _historyCloseActionMenusAdapter = (...args) => _historyFn('_closeHistoryActionMenus', importedCloseHistoryActionMenus)?.(...args);
var _historyCloseCompareActionMenusAdapter = (...args) => (
  typeof importedHasHistoryCompareHandler === 'function'
  && importedHasHistoryCompareHandler('closeHistoryCompareActionMenus')
  && typeof importedCloseHistoryCompareActionMenus === 'function'
    ? importedCloseHistoryCompareActionMenus(...args)
    : undefined
);
var _historyCloseRunActionMenusAdapter = (...args) => _historyFn('_closeHistoryRunActionMenus', importedCloseHistoryRunActionMenus)?.(...args);
var _historyCreateEntryAdapter = (...args) => _historyFn('_createHistoryEntry', importedCreateHistoryEntry)?.(...args);
var _historyCreateSnapshotEntryAdapter = (...args) => _historyFn('_createSnapshotHistoryEntry', importedCreateSnapshotHistoryEntry)?.(...args);
var _historyEnsureProjectFilterOptionsAdapter = (...args) => importedEnsureHistoryProjectFilterOptions?.(...args);
var _historyGetStarredAdapter = (...args) => _historyFn('_getStarred', importedGetStarred)?.(...args);
var _historyActionKeepsPanelOpenAdapter = (...args) => _historyFn('_historyActionKeepsPanelOpen', importedHistoryActionKeepsPanelOpen)?.(...args);
var _historyEditEntityMetadataAdapter = (...args) => _historyFn('_historyEditEntityMetadata', importedHistoryEditEntityMetadata)?.(...args);
var _historyProjectFromLinkAdapter = (...args) => importedHistoryProjectFromLink?.(...args);
var _historyProjectDisplayNameAdapter = (...args) => importedHistoryProjectDisplayName?.(...args);
var _historyProjectLabelForIdAdapter = (...args) => importedHistoryProjectLabelForId?.(...args);
var _historyLoadActiveProjectAdapter = (...args) => importedHistoryLoadActiveProject?.(...args);
var _historyLoadProjectsAdapter = (...args) => importedHistoryLoadProjects?.(...args);
var _historyOrderProjectsForPickerAdapter = (...args) => importedHistoryOrderProjectsForPicker?.(...args);
var _historyProjectPickerContentAdapter = (...args) => importedHistoryProjectPickerContent?.(...args);
var _historyProjectRunEntityOptionContentAdapter = (...args) => importedHistoryProjectRunEntityOptionContent?.(...args);
var _historyRefreshProjectRunEntityOptionAdapter = (...args) => importedHistoryRefreshProjectRunEntityOption?.(...args);
var _historyAddRunToActiveProjectAdapter = (...args) => importedHistoryAddRunToActiveProject?.(...args);
var _historyAddRunToProjectAdapter = (...args) => importedHistoryAddRunToProject?.(...args);
var _historyRemoveRunFromProjectAdapter = (...args) => importedHistoryRemoveRunFromProject?.(...args);
var _historyRestoreRunIntoTabAdapter = (...args) => importedRestoreHistoryRunIntoTab?.(...args);
var _historyPositionActionMenuAdapter = (...args) => _historyFn('_positionHistoryActionMenu', importedPositionHistoryActionMenu)?.(...args);
var _historyResetActionMenuPositionAdapter = (...args) => _historyFn('_resetHistoryActionMenuPosition', importedResetHistoryActionMenuPosition)?.(...args);
var _historyTabForRunAdapter = (...args) => _historyFn('_tabForHistoryRun', importedTabForHistoryRun)?.(...args);
var _historyToggleStarAdapter = (...args) => _historyFn('_toggleStar', importedToggleStar)?.(...args);
var _historyCopyRunPermalinkAdapter = (...args) => _historyFn('copyHistoryRunPermalink', importedCopyHistoryRunPermalink)?.(...args);
var _historyCopySnapshotLinkAdapter = (...args) => _historyFn('copySnapshotLink', importedCopySnapshotLink)?.(...args);
var _historyOpenSnapshotLinkAdapter = (...args) => _historyFn('openSnapshotLink', importedOpenSnapshotLink)?.(...args);
var _historyGetActiveProjectContextAdapter = (...args) => _historyFn('getActiveProjectContext', importedGetActiveProjectContext)?.(...args);
var _historyOpenAtlasAdapter = (...args) => _historyFn('openAtlas', importedOpenAtlas)?.(...args);
function _historyOpenCompareLauncherAdapter(...args) {
  const importedReady = typeof importedOpenHistoryCompareLauncher === 'function'
    && (
      typeof importedOpenHistoryCompareLauncher.hasHandler !== 'function'
      || importedOpenHistoryCompareLauncher.hasHandler()
    );
  const launcher = importedReady
    ? importedOpenHistoryCompareLauncher
    : _historyFn('openHistoryCompareLauncher');
  if (typeof launcher !== 'function') return false;
  if (typeof launcher.hasHandler === 'function' && !launcher.hasHandler()) return false;
  try {
    const result = launcher(...args);
    return result !== false;
  } catch (_) {
    return false;
  }
}
var _historyOpenRunDetailsAdapter = (...args) => _historyFn('openHistoryRunDetails')?.(...args);
var _historyOpenSchedulesModalAdapter = (...args) => _historyFn('openSchedulesModal')?.(...args);
var _historyOpenWatchersModalAdapter = (...args) => _historyFn('openWatchersModal')?.(...args);
var _historyRefreshProjectWorkspaceAdapter = (...args) => _historyFn('refreshProjectWorkspace', importedRefreshProjectWorkspace)?.(...args);
var _historyCanManageHistoryAdapter = (...args) => _historyFn('_historyCanManageHistory', importedHistoryCanManageHistory)?.(...args);
var _historyMutationErrorAdapter = (...args) => _historyFn('_historyMutationError', importedHistoryMutationError)?.(...args);
var _historyScopeDeniedMessageAdapter = (...args) => _historyFn('_historyScopeDeniedMessage', importedHistoryScopeDeniedMessage)?.(...args);
var _historyShowPermissionDeniedAdapter = (...args) => _historyFn('_historyShowPermissionDenied', importedHistoryShowPermissionDenied)?.(...args);
var _historySetLoadStateAdapter = (...args) => _historyFn('_setHistoryLoadState', importedSetHistoryLoadState)?.(...args);
var _historyConfirmActionAdapter = (...args) => _historyFn('confirmHistAction', importedConfirmHistAction)?.(...args);

function _historyCmdHistory() {
  const state = _historyState();
  if (!Array.isArray(state.cmdHistory)) state.cmdHistory = [];
  return state.cmdHistory;
}

function _historyRecentPreviewHistory() {
  const state = _historyState();
  if (!Array.isArray(state.recentPreviewHistory)) state.recentPreviewHistory = [];
  return state.recentPreviewHistory;
}

function _setHistoryCmdHistory(commands) {
  _historyState().cmdHistory = Array.isArray(commands) ? commands : [];
}

// History drawer filters are deliberately simple in the first pass:
// server-backed search/filtering for persisted run attributes, plus a local
// starred-only toggle backed by the server cache.
let _historyFilterRefreshTimer = null;
let _historyFilters = {
  type: 'all',
  q: '',
  commandRoot: '',
  signal: 'all',
  kind: 'all',
  entity: '',
  entityType: 'all',
  exitCode: 'all',
  dateRange: 'all',
  projectId: 'all',
  starredOnly: false,
};
let _historyMobileAdvancedOpen = false;
let _historyProjectOptions = [];
let _historyProjectOptionsLoaded = false;
let _historyProjectOptionsLoading = null;

function getHistoryProjectOptionsState() {
  return {
    options: _historyProjectOptions,
    loaded: _historyProjectOptionsLoaded,
    loading: _historyProjectOptionsLoading,
  };
}

function setHistoryProjectOptionsState(updates = {}) {
  if (Object.prototype.hasOwnProperty.call(updates, 'options')) {
    _historyProjectOptions = Array.isArray(updates.options) ? updates.options : [];
  }
  if (Object.prototype.hasOwnProperty.call(updates, 'loaded')) {
    _historyProjectOptionsLoaded = updates.loaded === true;
  }
  if (Object.prototype.hasOwnProperty.call(updates, 'loading')) {
    _historyProjectOptionsLoading = updates.loading || null;
  }
  return getHistoryProjectOptionsState();
}

let _historySelection = {
  selectMode: false,
  selected: new Map(),
  visibleItems: [],
  bulkInFlight: false,
};
let _historyLatestPanelData = null;
let _historyRootSuggestions = [];
let _historyRootFiltered = [];
let _historyRootIndex = -1;
let _historyRootSuppressInputOnce = false;
let _historyRootInputFocused = false;
let _historyPaging = {
  page: 1,
  pageSize: (_historyAppConfig() && _historyAppConfig().history_panel_limit)
    ? Math.max(1, Number(_historyAppConfig().history_panel_limit) || 50)
    : 50,
  totalCount: 0,
  pageCount: 0,
  hasPrev: false,
  hasNext: false,
};
let _historyCompareState = {
  source: null,
  candidates: [],
  manualCandidates: [],
  manualLoaded: false,
  launcherRequestId: 0,
  manualRequestId: 0,
  manualPage: 1,
  manualHasNext: false,
  manualLoading: false,
  manualCollapsedGroups: new Set(),
  selected: null,
  manualQuery: '',
  initialViewMode: '',
};
let _historyCompareRowPairSequence = 0;
let _historyCompareUnitSequence = 0;
let _historyCompareRowHeightFrame = null;
let _historyCompareRowResizeObserver = null;
const _historyTextFilterKeys = new Set(['q', 'commandRoot', 'entity']);
const _historyRunOnlyFilterKeys = new Set([
  'commandRoot',
  'signal',
  'kind',
  'entity',
  'entityType',
  'exitCode',
  'starredOnly',
]);
const _historyStructuredFilterKeys = new Set(['signal', 'kind', 'entity', 'entityType']);

function _historyGlobal() {
  return typeof window !== 'undefined' ? window : globalThis;
}

function _publishHistoryState() {
  const global = _historyGlobal();
  if (!global || global.DarklabHistoryState) return;
  Object.defineProperties(global, {
    DarklabHistoryState: {
      configurable: true,
      value: {},
    },
    _historyFilters: {
      configurable: true,
      get: () => _historyFilters,
      set: value => { _historyFilters = value && typeof value === 'object' ? value : _historyFilters; },
    },
    _historyProjectOptions: {
      configurable: true,
      get: () => _historyProjectOptions,
      set: value => { _historyProjectOptions = Array.isArray(value) ? value : []; },
    },
    _historyProjectOptionsLoaded: {
      configurable: true,
      get: () => _historyProjectOptionsLoaded,
      set: value => { _historyProjectOptionsLoaded = value === true; },
    },
    _historyProjectOptionsLoading: {
      configurable: true,
      get: () => _historyProjectOptionsLoading,
      set: value => { _historyProjectOptionsLoading = value || null; },
    },
    _historyCompareState: {
      configurable: true,
      get: () => _historyCompareState,
      set: value => { _historyCompareState = value && typeof value === 'object' ? value : _historyCompareState; },
    },
    _historyCompareRowPairSequence: {
      configurable: true,
      get: () => _historyCompareRowPairSequence,
      set: value => { _historyCompareRowPairSequence = Number(value) || 0; },
    },
    _historyCompareUnitSequence: {
      configurable: true,
      get: () => _historyCompareUnitSequence,
      set: value => { _historyCompareUnitSequence = Number(value) || 0; },
    },
    _historyCompareRowHeightFrame: {
      configurable: true,
      get: () => _historyCompareRowHeightFrame,
      set: value => { _historyCompareRowHeightFrame = value; },
    },
    _historyCompareRowResizeObserver: {
      configurable: true,
      get: () => _historyCompareRowResizeObserver,
      set: value => { _historyCompareRowResizeObserver = value || null; },
    },
    _historyPaging: {
      configurable: true,
      get: () => _historyPaging,
      set: value => { _historyPaging = value && typeof value === 'object' ? value : _historyPaging; },
    },
  });
}

_publishHistoryState();

function _historyCompareCoreCall(name, ...args) {
  const _historyCompareCore = _historyValue('DarklabHistoryCompareCore') || null;
  const helper = _historyCompareCore && _historyCompareCore[name];
  if (typeof helper !== 'function') throw new Error(`DarklabHistoryCompareCore.${name} is unavailable`);
  return helper(...args);
}

function _closeHistoryCompareActionMenusIfLoaded() {
  if (typeof _historyCloseCompareActionMenusAdapter === 'function') _historyCloseCompareActionMenusAdapter();
}

function _compareFormatDate(value) {
  return _historyCompareCoreCall('compareFormatDate', value);
}

function _compareDateGroupLabel(value) {
  return _historyCompareCoreCall('compareDateGroupLabel', value);
}

function _compareFormatDuration(seconds) {
  return _historyCompareCoreCall('compareFormatDuration', seconds);
}

function _compareFormatDelta(value, suffix = '') {
  return _historyCompareCoreCall('compareFormatDelta', value, suffix);
}

function _historyCompareTotalChangedLines(totals = {}) {
  return _historyCompareCoreCall('totalChangedLines', totals);
}

function _historyCompareOmittedTotal(truncated = {}) {
  return _historyCompareCoreCall('omittedTotal', truncated);
}

function _historyCompareLineLimit(limits = {}) {
  return _historyCompareCoreCall('lineLimit', limits);
}

function _historyCompareCoerceViewMode(value) {
  return _historyCompareCoreCall('coerceViewMode', value);
}

function _historyCompareCoerceContext(value) {
  return _historyCompareCoreCall('coerceContext', value);
}

function _historyCompareStoredViewMode() {
  return _historyCompareCoreCall('storedViewMode');
}

function _historyCompareStoredContext() {
  return _historyCompareCoreCall('storedContext');
}

function _historyCompareViewportMode() {
  return _historyCompareCoreCall('viewportMode');
}

function _historyCompareUsesMobileLayout() {
  return _historyCompareCoreCall('usesMobileLayout');
}

function _historyCompareResolveViewMode(value = null) {
  return _historyCompareCoreCall('resolveViewMode', value);
}

function _historyCompareViewModeOptions() {
  return _historyCompareCoreCall('viewModeOptions');
}

function _historyCompareContextLimit(value = null) {
  return _historyCompareCoreCall('contextLimit', value);
}

function _historyCompareNumber(value, fallback = null) {
  return _historyCompareCoreCall('number', value, fallback);
}

function _historyCompareCssEscape(value) {
  return _historyCompareCoreCall('cssEscape', value);
}

function _historyCompareBucketTone(bucket = {}) {
  return _historyCompareCoreCall('bucketTone', bucket);
}

function _historyCompareBuildAnchorMap(data = {}) {
  return _historyCompareCoreCall('buildAnchorMap', data);
}

function _historyCompareAnchorTone(items = []) {
  return _historyCompareCoreCall('anchorTone', items);
}

function _normalizeHistoryFilterValue(value) {
  return _historyCore().normalizeFilterValue(value);
}

function _historyDefaultFilterValue(key) {
  return _historyTextFilterKeys.has(key) ? '' : 'all';
}

function _historyRunOnlyFilterIsActive(key, filters = _historyFilters) {
  if (!_historyRunOnlyFilterKeys.has(key)) return false;
  if (key === 'starredOnly') return !!filters.starredOnly;
  return _normalizeHistoryFilterValue(filters[key]) !== _historyDefaultFilterValue(key);
}

function _historyHasActiveRunOnlyFilters(filters = _historyFilters) {
  return [..._historyRunOnlyFilterKeys].some(key => _historyRunOnlyFilterIsActive(key, filters));
}

function _syncHistoryFilterControls() {
  if (typeof historySearchInput !== 'undefined' && historySearchInput) historySearchInput.value = _historyFilters.q;
  if (typeof historyMobileFiltersToggle !== 'undefined' && historyMobileFiltersToggle) {
    const activeCount = _historyActiveFilterItems().length;
    const selectedCount = _historySelection?.selected?.size || 0;
    const status = [];
    if (activeCount > 0) status.push(`${activeCount} ${activeCount === 1 ? 'filter' : 'filters'}`);
    if (selectedCount > 0) status.push(`${selectedCount} selected`);
    const baseLabel = _historyMobileAdvancedOpen ? 'hide history tools' : 'history tools';
    historyMobileFiltersToggle.textContent = status.length ? `${baseLabel} (${status.join(' · ')})` : baseLabel;
    historyMobileFiltersToggle.setAttribute('aria-expanded', _historyMobileAdvancedOpen ? 'true' : 'false');
  }
  if (typeof historyPanel !== 'undefined' && historyPanel) {
    historyPanel.classList.toggle('mobile-history-filters-open', !!_historyMobileAdvancedOpen);
    historyPanel.classList.toggle('mobile-history-tools-open', !!_historyMobileAdvancedOpen);
  }
  if (typeof historyTypeFilter !== 'undefined' && historyTypeFilter) historyTypeFilter.value = _historyFilters.type;
  if (typeof historyRootInput !== 'undefined' && historyRootInput) historyRootInput.value = _historyFilters.commandRoot;
  if (typeof historySignalFilter !== 'undefined' && historySignalFilter) historySignalFilter.value = _historyFilters.signal;
  if (typeof historyKindFilter !== 'undefined' && historyKindFilter) historyKindFilter.value = _historyFilters.kind;
  if (typeof historyEntityInput !== 'undefined' && historyEntityInput) historyEntityInput.value = _historyFilters.entity;
  if (typeof historyEntityTypeFilter !== 'undefined' && historyEntityTypeFilter) {
    historyEntityTypeFilter.value = _historyFilters.entityType;
  }
  if (typeof historyExitFilter !== 'undefined' && historyExitFilter) historyExitFilter.value = _historyFilters.exitCode;
  if (typeof historyDateFilter !== 'undefined' && historyDateFilter) historyDateFilter.value = _historyFilters.dateRange;
  if (typeof importedSyncHistoryProjectFilterOptions === 'function') importedSyncHistoryProjectFilterOptions();
  if (typeof historyStarredToggle !== 'undefined' && historyStarredToggle) historyStarredToggle.checked = !!_historyFilters.starredOnly;
  const runOnlyEnabled = _historyFilters.type !== 'snapshots';
  if (typeof historyRootInput !== 'undefined' && historyRootInput) historyRootInput.disabled = !runOnlyEnabled;
  if (typeof historySignalFilter !== 'undefined' && historySignalFilter) historySignalFilter.disabled = !runOnlyEnabled;
  if (typeof historyKindFilter !== 'undefined' && historyKindFilter) historyKindFilter.disabled = !runOnlyEnabled;
  if (typeof historyEntityInput !== 'undefined' && historyEntityInput) historyEntityInput.disabled = !runOnlyEnabled;
  if (typeof historyEntityTypeFilter !== 'undefined' && historyEntityTypeFilter) {
    historyEntityTypeFilter.disabled = !runOnlyEnabled;
  }
  if (typeof historyExitFilter !== 'undefined' && historyExitFilter) historyExitFilter.disabled = !runOnlyEnabled;
  if (typeof historyStarredToggle !== 'undefined' && historyStarredToggle) historyStarredToggle.disabled = !runOnlyEnabled;
  if (typeof _historySyncAppSelectAdapter === 'function') {
    if (typeof historyTypeFilter !== 'undefined') _historySyncAppSelectAdapter(historyTypeFilter);
    if (typeof historySignalFilter !== 'undefined') _historySyncAppSelectAdapter(historySignalFilter);
    if (typeof historyKindFilter !== 'undefined') _historySyncAppSelectAdapter(historyKindFilter);
    if (typeof historyEntityTypeFilter !== 'undefined') _historySyncAppSelectAdapter(historyEntityTypeFilter);
    if (typeof historyExitFilter !== 'undefined') _historySyncAppSelectAdapter(historyExitFilter);
    if (typeof historyDateFilter !== 'undefined') _historySyncAppSelectAdapter(historyDateFilter);
    if (typeof historyProjectFilter !== 'undefined') _historySyncAppSelectAdapter(historyProjectFilter);
  }
  if (typeof histClearAllBtn !== 'undefined' && histClearAllBtn) {
    histClearAllBtn.classList.toggle('u-hidden', _historyFilters.type === 'snapshots');
  }
}

function _historyHasActiveServerFilters() {
  return _historyCore().hasActiveServerFilters(_historyFilters);
}

function _historyHasAnyFilters() {
  return _historyCore().hasAnyFilters(_historyFilters);
}

function _historyResetRunOnlyFilters() {
  _historyFilters = _historyCore().resetRunOnlyFilters(_historyFilters);
}

function _historyLabelForType(type = _historyFilters.type) {
  return _historyCore().labelForType(type);
}

function _historySummaryLabel(totalCount = _historyPaging.totalCount) {
  return _historyCore().summaryLabel(_historyFilters.type, totalCount);
}

function _historyCommandRootsFromRuns(runs) {
  return _historyCore().commandRootsFromRuns(runs);
}

function _renderHistoryRootSuggestions(runs) {
  const nextSuggestions = _historyCommandRootsFromRuns(runs);
  const currentQuery = typeof historyRootInput !== 'undefined' && historyRootInput
    ? _normalizeHistoryFilterValue(historyRootInput.value)
    : _historyFilters.commandRoot;
  if (currentQuery) {
    // The server-side command_root filter is exact-root oriented. While the
    // user is typing a partial root, a refresh can legitimately return no
    // matching rows; do not let that transient response erase the suggestion
    // pool the user is actively choosing from.
    const merged = new Set([..._historyRootSuggestions, ...nextSuggestions]);
    _historyRootSuggestions = [...merged].sort((a, b) => a.localeCompare(b));
  } else {
    _historyRootSuggestions = nextSuggestions;
  }
  _historyRefreshRootDropdown();
}

function _historyProjectLabel(projectId) {
  const normalized = _normalizeHistoryFilterValue(projectId);
  if (!normalized || normalized === 'all') return '';
  const project = _historyProjectOptions.find(item => String(item && item.id || '') === normalized);
  const localLabel = project && String(project.name || project.slug || project.id || '').trim();
  return localLabel || _historyProjectLabelForIdAdapter(normalized) || normalized;
}

function _appendHistoryCommandEcho(tabId, command) {
  if (typeof _historyAppendCommandEchoAdapter === 'function') {
    _historyAppendCommandEchoAdapter(command, tabId);
    return;
  }
  _historyAppendLineAdapter(command, 'prompt-echo', tabId);
}

function _historyOutputLineMetadata(entry) {
  if (!entry || typeof entry !== 'object') return null;
  const metadata = {};
  if (Array.isArray(entry.signals) && entry.signals.length) metadata.signals = entry.signals;
  if (typeof entry.kind === 'string' && entry.kind) metadata.kind = entry.kind;
  if (typeof entry.role === 'string' && entry.role) metadata.role = entry.role;
  if (Number.isInteger(entry.line_index)) metadata.line_index = entry.line_index;
  if (Number.isInteger(entry.line_number)) metadata.line_number = entry.line_number;
  if (typeof entry.command_root === 'string' && entry.command_root) metadata.command_root = entry.command_root;
  if (typeof entry.target === 'string' && entry.target) metadata.target = entry.target;
  if (entry.template_provenance && typeof entry.template_provenance === 'object') {
    metadata.template_provenance = entry.template_provenance;
  }
  if (entry.source_detail && typeof entry.source_detail === 'object') {
    metadata.source_detail = entry.source_detail;
  }
  return Object.keys(metadata).length ? metadata : null;
}

function _appendHistoryOutputLine(entry, tabId) {
  if (entry && typeof entry === 'object') {
    const text = String(entry.text || '');
    const cls = String(entry.cls || '');
    const metadata = _historyOutputLineMetadata(entry);
    if (metadata) _historyAppendLineAdapter(text, cls, tabId, metadata);
    else _historyAppendLineAdapter(text, cls, tabId);
    return;
  }
  _historyAppendLineAdapter(String(entry || ''), '', tabId);
}

function _hideHistoryRootDropdown() {
  if (typeof historyRootDropdown === 'undefined' || !historyRootDropdown) return;
  historyRootDropdown.replaceChildren();
  historyRootDropdown.classList.add('u-hidden');
  _historyRootFiltered = [];
  _historyRootIndex = -1;
}

function _historyRootMatches(query) {
  return _historyCore().rootMatches(_historyRootSuggestions, query, 12);
}

function _acceptHistoryRootSuggestion(root) {
  _historyRootSuppressInputOnce = true;
  if (typeof historyRootInput !== 'undefined' && historyRootInput) historyRootInput.value = root;
  _hideHistoryRootDropdown();
  _setHistoryFilter('commandRoot', root);
  if (typeof historyRootInput !== 'undefined' && historyRootInput) {
    setTimeout(() => _historyFocusElementAdapter(historyRootInput, { preventScroll: true }), 0);
  }
}

function _renderHistoryRootDropdown(items, query) {
  if (typeof historyRootDropdown === 'undefined' || !historyRootDropdown) return;
  historyRootDropdown.replaceChildren();
  if (!items.length) {
    _hideHistoryRootDropdown();
    return;
  }
  const normalizedQuery = _normalizeHistoryFilterValue(query).toLowerCase();
  if (items.length === 1 && normalizedQuery && items[0].toLowerCase() === normalizedQuery) {
    _hideHistoryRootDropdown();
    return;
  }
  const mobileMode = typeof _historyUseMobileTerminalViewportModeAdapter === 'function' && _historyUseMobileTerminalViewportModeAdapter();
  historyRootDropdown.classList.toggle('ac-mobile', mobileMode);
  items.forEach((root, index) => {
    const item = document.createElement('div');
    item.className = 'ac-item dropdown-item dropdown-item-dense'
      + (index === _historyRootIndex ? ' ac-active dropdown-item-active' : '');
    const matchIndex = normalizedQuery ? root.toLowerCase().indexOf(normalizedQuery) : -1;
    if (matchIndex >= 0 && normalizedQuery) {
      item.innerHTML = _historyEscapeHtmlAdapter(root.slice(0, matchIndex))
        + '<span class="ac-match">' + _historyEscapeHtmlAdapter(root.slice(matchIndex, matchIndex + normalizedQuery.length)) + '</span>'
        + _historyEscapeHtmlAdapter(root.slice(matchIndex + normalizedQuery.length));
    } else {
      item.textContent = root;
    }
    item.addEventListener('mousedown', e => {
      e.preventDefault();
      e.stopPropagation();
      _acceptHistoryRootSuggestion(root);
    });
    item.addEventListener('touchstart', e => {
      e.preventDefault();
      e.stopPropagation();
      _acceptHistoryRootSuggestion(root);
    }, { passive: false });
    historyRootDropdown.appendChild(item);
  });
  historyRootDropdown.classList.remove('u-hidden');
}

function _historyRefreshRootDropdown() {
  const query = typeof historyRootInput !== 'undefined' && historyRootInput ? historyRootInput.value : _historyFilters.commandRoot;
  _historyRootFiltered = _historyRootMatches(query);
  if (_historyRootIndex >= _historyRootFiltered.length) _historyRootIndex = _historyRootFiltered.length - 1;
  _renderHistoryRootDropdown(_historyRootFiltered, query);
}

function _historyActiveFilterItems() {
  const projectLabel = _historyProjectLabel(_historyFilters.projectId);
  return _historyCore().activeFilterItems({
    ..._historyFilters,
    projectLabel,
  });
}

function _historySetPage(nextPage, { refresh = true } = {}) {
  const page = Math.max(1, Number(nextPage) || 1);
  if (_historyPaging.page !== page) {
    _historyPaging.page = page;
    _historyClearSelection({ render: false });
  }
  if (refresh) refreshHistoryPanel();
}

function _historyRenderPagination(visibleCount = 0) {
  if (typeof historyPagination === 'undefined' || !historyPagination) return;
  if (typeof historyPaginationSummary === 'undefined' || !historyPaginationSummary) return;
  if (typeof historyPaginationControls === 'undefined' || !historyPaginationControls) return;

  const { page, pageSize, totalCount, pageCount } = _historyPaging;
  const totalLabel = _historySummaryLabel(totalCount);
  if (totalCount > 0) {
    const start = ((page - 1) * pageSize) + 1;
    const count = Math.max(0, Number(visibleCount) || 0);
    const end = count > 0 ? Math.min(totalCount, start + count - 1) : start;
    historyPaginationSummary.textContent = `Showing ${start}-${end} of ${totalCount} ${totalLabel}`;
  } else {
    historyPaginationSummary.textContent = `Showing 0 of 0 ${_historySummaryLabel(0)}`;
  }

  historyPaginationControls.replaceChildren();

  const prevPage = page > 1 ? page - 1 : 1;
  const prevBtn = document.createElement('button');
  prevBtn.type = 'button';
  prevBtn.className = 'btn btn-secondary btn-compact history-pagination-chevron';
  prevBtn.textContent = '‹ Prev';
  prevBtn.disabled = page <= 1;
  prevBtn.setAttribute('aria-label', 'Previous page');
  prevBtn.addEventListener('click', () => _historySetPage(prevPage));
  historyPaginationControls.appendChild(prevBtn);

  const pageLabel = document.createElement('span');
  pageLabel.className = 'history-pagination-status';
  pageLabel.textContent = `Page ${pageCount > 0 ? page : 0} of ${pageCount}`;
  pageLabel.setAttribute('aria-live', 'polite');
  historyPaginationControls.appendChild(pageLabel);

  const nextPage = pageCount > page ? page + 1 : page;
  const nextBtn = document.createElement('button');
  nextBtn.type = 'button';
  nextBtn.className = 'btn btn-secondary btn-compact history-pagination-chevron';
  nextBtn.textContent = 'Next ›';
  nextBtn.disabled = page >= pageCount;
  nextBtn.setAttribute('aria-label', 'Next page');
  nextBtn.addEventListener('click', () => _historySetPage(nextPage));
  historyPaginationControls.appendChild(nextBtn);

  historyPagination.classList.remove('u-hidden');
}

function _renderHistoryActiveFilters() {
  if (typeof historyActiveFilters === 'undefined' || !historyActiveFilters) return;
  historyActiveFilters.replaceChildren();
  const items = _historyActiveFilterItems();
  historyActiveFilters.classList.toggle('u-hidden', !items.length);
  items.forEach(item => {
    const chip = document.createElement('div');
    chip.className = 'history-active-filter-chip chip chip-removable';
    chip.dataset.filterKey = item.key;
    const label = document.createElement('span');
    label.textContent = item.label;
    chip.appendChild(label);
    const removeBtn = document.createElement('button');
    removeBtn.className = 'history-active-filter-remove';
    removeBtn.type = 'button';
    removeBtn.setAttribute('aria-label', `Remove ${item.label} filter`);
    removeBtn.textContent = '✕';
    removeBtn.addEventListener('click', e => {
      e.preventDefault();
      e.stopPropagation();
      const resetValue = item.key === 'starredOnly' ? false : _historyDefaultFilterValue(item.key);
      _setHistoryFilter(item.key, resetValue);
    });
    chip.appendChild(removeBtn);
    historyActiveFilters.appendChild(chip);
  });
}

function _historyItemType(item) {
  return String(item?.type || 'run');
}

function _historyIsSelectableItem(item) {
  if (!item || !item.id) return false;
  const type = _historyItemType(item);
  if (type === 'snapshot') return true;
  if (type !== 'run') return false;
  return !!item.finished || item.exit_code != null;
}

function _historyIsSelectableRun(run) {
  return _historyItemType(run) === 'run' && _historyIsSelectableItem(run);
}

function _historySelectionKey(item) {
  return `${_historyItemType(item)}:${String(item?.id || '')}`;
}

function _historySelectedRuns() {
  return Array.from(_historySelection.selected.values()).filter(item => _historyItemType(item) === 'run');
}

function _historySelectedSnapshots() {
  return Array.from(_historySelection.selected.values()).filter(item => _historyItemType(item) === 'snapshot');
}

function _historyCssEscape(value) {
  if (typeof CSS !== 'undefined' && CSS && typeof CSS.escape === 'function') {
    return CSS.escape(String(value));
  }
  return String(value).replace(/["\\]/g, '\\$&');
}

function _historyClearSelection({ render = true } = {}) {
  _historySelection.selected.clear();
  if (render) _renderHistoryBulkToolbar();
}

function _historyResetSelectionOnClose() {
  _historySelection.selectMode = false;
  _historySelection.selected.clear();
  _historySelection.bulkInFlight = false;
  _historySelection.visibleItems = [];
  _historyCloseActionMenusAdapter();
  _closeHistoryBulkActionMenu();
  _renderHistoryBulkToolbar();
}

function _historySetSelectMode(enabled, { render = true } = {}) {
  _historySelection.selectMode = !!enabled;
  if (!_historySelection.selectMode) _historySelection.selected.clear();
  if (render) _historyRenderCurrentPanel();
}

function _historyToggleItemSelection(item, checked = null) {
  if (!_historyIsSelectableItem(item) || _historySelection.bulkInFlight) return;
  const itemKey = _historySelectionKey(item);
  const shouldSelect = checked === null ? !_historySelection.selected.has(itemKey) : !!checked;
  if (shouldSelect) _historySelection.selected.set(itemKey, item);
  else _historySelection.selected.delete(itemKey);
  _renderHistoryBulkToolbar();
  const checkbox = historyList?.querySelector?.(`[data-history-select-item-id="${_historyCssEscape(itemKey)}"]`);
  if (checkbox) checkbox.checked = _historySelection.selected.has(itemKey);
}

function _historyToggleRunSelection(run, checked = null) {
  _historyToggleItemSelection(run, checked);
}

function _historySelectAllVisibleItems() {
  if (_historySelection.bulkInFlight) return;
  const visibleSelectable = _historySelection.visibleItems.filter(_historyIsSelectableItem);
  const allSelected = visibleSelectable.length > 0
    && visibleSelectable.every(item => _historySelection.selected.has(_historySelectionKey(item)));
  visibleSelectable.forEach((item) => {
    if (!item.id) return;
    if (allSelected) {
      _historySelection.selected.delete(_historySelectionKey(item));
    } else {
      _historySelection.selected.set(_historySelectionKey(item), item);
    }
  });
  _historyRenderCurrentPanel();
}

function _historySetBulkBusy(busy) {
  _historySelection.bulkInFlight = !!busy;
  _renderHistoryBulkToolbar();
  if (historyList) {
    historyList.querySelectorAll('[data-action], .history-entry-select-row input').forEach((el) => {
      if ('disabled' in el) el.disabled = !!busy;
    });
  }
}

function _historyBulkCountsFromResponse(data) {
  return data && typeof data === 'object' && data.counts && typeof data.counts === 'object'
    ? data.counts
    : {};
}

function _historyBulkToast(message, counts = {}) {
  const hasPartial = Number(counts.rejected || 0) > 0
    || Number(counts.not_found || 0) > 0
    || Number(counts.not_linked || 0) > 0;
  if (hasPartial) _historyShowToastAdapter(message, 'success', { label: 'dismiss', onClick: () => {} });
  else _historyShowToastAdapter(message);
}

function _historyBulkReasonSummary(results = []) {
  if (!Array.isArray(results)) return '';
  const rejected = results.filter(item => item && item.status === 'rejected');
  if (!rejected.length) return '';
  const reasons = rejected.reduce((acc, item) => {
    const reason = String(item.reason || '').trim();
    acc.set(reason, (acc.get(reason) || 0) + 1);
    return acc;
  }, new Map());
  const labels = {
    running: 'still running',
    not_owned: 'not available in this session',
    policy_blocked: 'blocked by policy',
    builtin: 'built-in command',
  };
  return Array.from(reasons.entries()).map(([reason, count]) => {
    const label = labels[reason] || 'skipped';
    return `${count} ${label}`;
  }).join(' - ');
}

function _historyBulkResultText(action, projectName, counts = {}) {
  if (action === 'add') {
    const added = Number(counts.added || 0);
    const already = Number(counts.already_linked || 0);
    const rejected = Number(counts.rejected || 0) + Number(counts.not_found || 0);
    const pieces = [`Added ${added} ${added === 1 ? 'run' : 'runs'} to ${projectName}`];
    if (already) pieces.push(`${already} already linked`);
    if (rejected) pieces.push(`${rejected} skipped`);
    return pieces.join(' - ');
  }
  if (action === 'remove') {
    const removed = Number(counts.removed || 0);
    const notLinked = Number(counts.not_linked || 0);
    const rejected = Number(counts.rejected || 0) + Number(counts.not_found || 0);
    const pieces = [`Removed ${removed} ${removed === 1 ? 'run' : 'runs'} from ${projectName}`];
    if (notLinked) pieces.push(`${notLinked} not linked`);
    if (rejected) pieces.push(`${rejected} skipped`);
    return pieces.join(' - ');
  }
  const deleted = Number(counts.deleted || 0);
  const rejected = Number(counts.rejected || 0) + Number(counts.not_found || 0);
  const pieces = [`Deleted ${deleted} ${deleted === 1 ? 'run' : 'runs'}`];
  if (rejected) pieces.push(`${rejected} skipped`);
  return pieces.join(' - ');
}

function _historySelectedRunIds() {
  return _historySelectedRuns().map(run => String(run.id || '')).filter(Boolean);
}

function _historySelectedSnapshotIds() {
  return _historySelectedSnapshots().map(snapshot => String(snapshot.id || '')).filter(Boolean);
}

async function _historyRefreshAfterBulk() {
  try {
    await refreshHistoryPanel();
  } catch (_) {
    _historyShowToastAdapter('Bulk action finished, but history could not refresh. Refresh to see the latest state.', 'error');
  }
}

function _closeHistoryBulkActionMenu() {
  const toolbar = typeof historyBulkToolbar !== 'undefined' ? historyBulkToolbar : null;
  const wrap = toolbar?.querySelector?.('.history-bulk-actions-wrap.open');
  if (!wrap) return;
  wrap.classList.remove('open');
  wrap.querySelector('[data-action="history-bulk-menu"]')?.setAttribute('aria-expanded', 'false');
}

function _historyProjectsForSelectedLinks() {
  const projectsById = new Map();
  _historySelectedRuns().forEach((run) => {
    const runId = String(run && run.id || '');
    if (!runId) return;
    const links = Array.isArray(run.project_links) ? run.project_links : [];
    links.forEach((link) => {
      const project = typeof _historyProjectFromLinkAdapter === 'function' ? _historyProjectFromLinkAdapter(link) : null;
      if (!project || !project.id) return;
      const projectId = String(project.id);
      if (!projectsById.has(projectId)) projectsById.set(projectId, { project, runIds: new Set() });
      projectsById.get(projectId).runIds.add(runId);
    });
  });
  return Array.from(projectsById.values())
    .map(item => ({ project: item.project, runIds: Array.from(item.runIds) }))
    .filter(item => item.project && item.project.id && item.runIds.length);
}

function _historyMergeBulkProjectResponses(responses) {
  return responses.reduce((acc, data) => {
    const counts = _historyBulkCountsFromResponse(data);
    ['added', 'already_linked', 'removed', 'not_linked', 'not_found', 'rejected'].forEach((key) => {
      acc.counts[key] = Number(acc.counts[key] || 0) + Number(counts[key] || 0);
    });
    if (Array.isArray(data?.results)) acc.results.push(...data.results);
    return acc;
  }, {
    counts: { added: 0, already_linked: 0, removed: 0, not_linked: 0, not_found: 0, rejected: 0 },
    results: [],
  });
}

async function _historyBulkPostProject(project, action, options = {}) {
  const runIds = _historySelectedRunIds();
  if (!project || !project.id || !runIds.length) return;
  _historySetBulkBusy(true);
  try {
    const resp = await _historyApiFetchAdapter(`/projects/${encodeURIComponent(project.id)}/links`, {
      method: action === 'remove' ? 'DELETE' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        entity_type: 'run',
        entity_ids: runIds,
        source: 'manual',
        ...(options.includeEntities ? { include_entities: true } : {}),
      }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    const counts = _historyBulkCountsFromResponse(data);
    const projectName = _historyProjectDisplayNameAdapter(project) || 'project';
    _historySelection.selected.clear();
    const reasonSummary = _historyBulkReasonSummary(data.results);
    const entityAdded = Number(data && data.linked_entities && data.linked_entities.added || 0);
    const entitySummary = action === 'add' && entityAdded
      ? `${entityAdded.toLocaleString()} ${entityAdded === 1 ? 'entity' : 'entities'} added`
      : '';
    const message = [_historyBulkResultText(action, projectName, counts), entitySummary, reasonSummary].filter(Boolean).join(' - ');
    _historyBulkToast(message, counts);
    if (typeof _historyRefreshProjectWorkspaceAdapter === 'function') {
      try { await _historyRefreshProjectWorkspaceAdapter(); } catch (_) {}
    }
    await _historyRefreshAfterBulk();
  } catch (_) {
    _historyShowToastAdapter(action === 'remove' ? 'Failed to remove selected runs from project' : 'Failed to add selected runs to project', 'error');
  } finally {
    _historySetBulkBusy(false);
  }
}

async function _historyBulkRemoveFromAllProjects() {
  const projectGroups = _historyProjectsForSelectedLinks();
  if (!projectGroups.length) {
    _historyShowToastAdapter('Selected runs are not linked to any project', 'error');
    return;
  }
  const selectedCount = _historySelectedRunIds().length;
  const linkCount = projectGroups.reduce((total, item) => total + item.runIds.length, 0);
  const choice = await _historyShowConfirmAdapter({
    body: {
      text: `Remove ${selectedCount} selected ${selectedCount === 1 ? 'run' : 'runs'} from all linked projects?`,
      note: `This removes ${linkCount} project ${linkCount === 1 ? 'link' : 'links'} and leaves the run history intact.`,
    },
    tone: 'warning',
    actions: [
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      { id: 'remove', label: 'Remove from projects', role: 'destructive', tone: 'warning' },
    ],
    refocusOnResolve: false,
  });
  if (choice !== 'remove') return;
  _historySetBulkBusy(true);
  try {
    const responses = await Promise.all(projectGroups.map(async ({ project, runIds }) => {
      const resp = await _historyApiFetchAdapter(`/projects/${encodeURIComponent(project.id)}/links`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entity_type: 'run', entity_ids: runIds, source: 'manual' }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return resp.json();
    }));
    const data = _historyMergeBulkProjectResponses(responses);
    const counts = _historyBulkCountsFromResponse(data);
    _historySelection.selected.clear();
    const reasonSummary = _historyBulkReasonSummary(data.results);
    const removed = Number(counts.removed || 0);
    const notLinked = Number(counts.not_linked || 0);
    const rejected = Number(counts.rejected || 0) + Number(counts.not_found || 0);
    const pieces = [`Removed ${removed} project ${removed === 1 ? 'link' : 'links'}`];
    if (notLinked) pieces.push(`${notLinked} not linked`);
    if (rejected) pieces.push(`${rejected} skipped`);
    const message = [pieces.join(' - '), reasonSummary].filter(Boolean).join(' - ');
    _historyBulkToast(message, counts);
    if (typeof _historyRefreshProjectWorkspaceAdapter === 'function') {
      try { await _historyRefreshProjectWorkspaceAdapter(); } catch (_) {}
    }
    await _historyRefreshAfterBulk();
  } catch (_) {
    _historyShowToastAdapter('Failed to remove selected runs from projects', 'error');
  } finally {
    _historySetBulkBusy(false);
  }
}

async function _historyBulkAddToActiveProject() {
  const project = await _historyLoadActiveProjectAdapter();
  if (!project || !project.id) {
    _historyShowToastAdapter('No active project selected', 'error');
    return;
  }
  const runIds = _historySelectedRunIds();
  const entityOption = _historyProjectRunEntityOptionContentAdapter();
  await _historyRefreshProjectRunEntityOptionAdapter(entityOption, project, runIds);
  const choice = await _historyShowConfirmAdapter({
    body: `Add ${runIds.length} selected ${runIds.length === 1 ? 'run' : 'runs'} to ${_historyProjectDisplayNameAdapter(project) || 'the active project'}?`,
    content: entityOption.wrap.classList.contains('u-hidden') ? null : entityOption.wrap,
    tone: null,
    actions: [
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      { id: 'add', label: 'Add to project', role: 'primary' },
    ],
    refocusOnResolve: false,
  });
  if (choice !== 'add') return;
  await _historyBulkPostProject(project, 'add', {
    includeEntities: !!entityOption.checkbox.checked && !entityOption.checkbox.disabled,
  });
}

async function _historyBulkChooseProject(action) {
  const selectedCount = _historySelection.selected.size;
  let projects;
  try {
    const [loadedProjects, activeProject] = await Promise.all([
      _historyLoadProjectsAdapter(),
      _historyLoadActiveProjectAdapter().catch(() => null),
    ]);
    projects = _historyOrderProjectsForPickerAdapter(loadedProjects, activeProject);
  } catch (_) {
    _historyShowToastAdapter('Failed to load projects', 'error');
    return;
  }
  if (!projects.length) {
    _historyShowToastAdapter('No projects available', 'error');
    return;
  }
  const { wrap, select } = _historyProjectPickerContentAdapter(projects);
  const entityOption = _historyProjectRunEntityOptionContentAdapter();
  wrap.appendChild(entityOption.wrap);
  const runIds = _historySelectedRunIds();
  const updateEntityOption = () => {
    const selectedProject = projects.find(item => String(item.id || '') === select.value);
    _historyRefreshProjectRunEntityOptionAdapter(entityOption, selectedProject, runIds);
  };
  select.addEventListener('change', updateEntityOption);
  updateEntityOption();
  const help = wrap.querySelector('.history-project-picker-help');
  if (help) {
    help.textContent = 'Choose a project to link selected runs.';
  }
  const choicePromise = _historyShowConfirmAdapter({
    body: `Add ${selectedCount} selected ${selectedCount === 1 ? 'run' : 'runs'} to project`,
    content: wrap,
    tone: null,
    defaultFocus: select,
    actions: [
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      { id: action, label: 'Add to project', role: 'primary' },
    ],
    refocusOnResolve: false,
  });
  if (typeof _historyEnhanceAppSelectsAdapter === 'function') {
    _historyEnhanceAppSelectsAdapter(wrap);
    if (typeof _historyUseMobileTerminalViewportModeAdapter === 'function' && _historyUseMobileTerminalViewportModeAdapter()) {
      wrap.querySelector('.app-select-menu')?.classList.add('dropdown-up');
    }
  }
  const choice = await choicePromise;
  if (choice !== action) return;
  const project = projects.find(item => String(item.id || '') === select.value);
  await _historyBulkPostProject(project, action, {
    includeEntities: !!entityOption.checkbox.checked && !entityOption.checkbox.disabled,
  });
}

function _historyBulkDeleteLabel(runCount, snapshotCount) {
  if (runCount && snapshotCount) return `${runCount + snapshotCount} selected history items`;
  if (snapshotCount) return `${snapshotCount} selected ${snapshotCount === 1 ? 'snapshot' : 'snapshots'}`;
  return `${runCount} selected ${runCount === 1 ? 'run' : 'runs'}`;
}

function _historyBulkDeletedNoun(runCount, snapshotCount, deletedCount) {
  if (runCount && !snapshotCount) return deletedCount === 1 ? 'run' : 'runs';
  if (snapshotCount && !runCount) return deletedCount === 1 ? 'snapshot' : 'snapshots';
  return deletedCount === 1 ? 'item' : 'items';
}

function _historyMergeBulkDeleteResponses(responses) {
  return responses.reduce((acc, data) => {
    const counts = _historyBulkCountsFromResponse(data);
    ['deleted', 'not_found', 'rejected'].forEach((key) => {
      acc.counts[key] = Number(acc.counts[key] || 0) + Number(counts[key] || 0);
    });
    if (Array.isArray(data?.results)) acc.results.push(...data.results);
    return acc;
  }, { counts: { deleted: 0, not_found: 0, rejected: 0 }, results: [] });
}

async function _historyPostBulkDelete(url, payload) {
  const resp = await _historyApiFetchAdapter(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    if (typeof _historyMutationErrorAdapter === 'function') {
      throw await _historyMutationErrorAdapter(resp, 'Failed to delete selected history items');
    }
    throw new Error(`HTTP ${resp.status}`);
  }
  return resp.json();
}

function _historyBulkExportFilename(format) {
  const suffix = format === 'jsonl' ? 'jsonl' : 'txt';
  return `darklab-history-${new Date().toISOString().replace(/[:.]/g, '-')}.${suffix}`;
}

function _historyFilenameFromDisposition(value) {
  const match = /filename\*?=(?:UTF-8''|")?([^";]+)/i.exec(String(value || ''));
  if (!match) return '';
  try {
    return decodeURIComponent(match[1].replace(/"$/u, ''));
  } catch (_) {
    return match[1].replace(/"$/u, '');
  }
}

async function _historyBulkExportSelectedItems(format) {
  const runIds = _historySelectedRunIds();
  const snapshotIds = _historySelectedSnapshotIds();
  if (!runIds.length && !snapshotIds.length) return;
  const downloader = _historyDownloadBlobAsAttachmentAdapter;
  if (typeof downloader !== 'function') {
    _historyShowToastAdapter('Downloads are not available', 'error');
    return;
  }
  const exportFormat = format === 'jsonl' ? 'jsonl' : 'txt';
  _historySetBulkBusy(true);
  try {
    const resp = await _historyApiFetchAdapter('/history/bulk-export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        run_ids: runIds,
        snapshot_ids: snapshotIds,
        format: exportFormat,
      }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const blob = await resp.blob();
    const filename = _historyFilenameFromDisposition(resp.headers?.get?.('content-disposition'))
      || _historyBulkExportFilename(exportFormat);
    downloader(blob, filename, { container: historyPanel });
    _historyShowToastAdapter(`History ${exportFormat.toUpperCase()} export started`);
  } catch (_) {
    _historyShowToastAdapter('Failed to export selected history items', 'error');
  } finally {
    _historySetBulkBusy(false);
  }
}

async function _historyBulkDeleteSelectedItems() {
  const runIds = _historySelectedRunIds();
  const snapshotIds = _historySelectedSnapshotIds();
  if (!runIds.length && !snapshotIds.length) return;
  if (typeof _historyCanManageHistoryAdapter === 'function' && !_historyCanManageHistoryAdapter()) {
    if (typeof _historyShowPermissionDeniedAdapter === 'function') _historyShowPermissionDeniedAdapter('delete team history');
    return;
  }
  const label = _historyBulkDeleteLabel(runIds.length, snapshotIds.length);
  const choice = await _historyShowConfirmAdapter({
    body: {
      text: `Delete ${label}?`,
      note: runIds.length && snapshotIds.length
        ? 'This removes the selected run history and snapshots and cannot be undone.'
        : snapshotIds.length
          ? 'This removes the selected snapshots and cannot be undone.'
          : 'This removes the selected run history and cannot be undone.',
    },
    tone: 'warning',
    actions: [
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      { id: 'delete', label: 'Delete', role: 'destructive', tone: 'warning' },
    ],
    refocusOnResolve: false,
  });
  if (choice !== 'delete') return;
  _historySetBulkBusy(true);
  try {
    const requests = [];
    if (runIds.length) requests.push(_historyPostBulkDelete('/history/bulk-delete', { run_ids: runIds }));
    if (snapshotIds.length) requests.push(_historyPostBulkDelete('/share/bulk-delete', { snapshot_ids: snapshotIds }));
    const data = _historyMergeBulkDeleteResponses(await Promise.all(requests));
    const counts = _historyBulkCountsFromResponse(data);
    _historySelection.selected.clear();
    const reasonSummary = _historyBulkReasonSummary(data.results);
    const deleted = Number(counts.deleted || 0);
    const rejected = Number(counts.rejected || 0) + Number(counts.not_found || 0);
    const pieces = [`Deleted ${deleted} ${_historyBulkDeletedNoun(runIds.length, snapshotIds.length, deleted)}`];
    if (rejected) pieces.push(`${rejected} skipped`);
    const message = [pieces.join(' - '), reasonSummary].filter(Boolean).join(' - ');
    _historyBulkToast(message, counts);
    await _historyRefreshAfterBulk();
  } catch (err) {
    _historyShowToastAdapter(err.userFacing ? err.message : 'Failed to delete selected history items', 'error');
  } finally {
    _historySetBulkBusy(false);
  }
}

function _historyBuildBulkActionMenu(disabled) {
  const wrap = document.createElement('div');
  wrap.className = 'history-bulk-actions-wrap save-menu-wrap save-menu-down';
  const trigger = document.createElement('button');
  trigger.className = 'history-action-btn btn btn-secondary btn-compact';
  trigger.type = 'button';
  trigger.dataset.action = 'history-bulk-menu';
  trigger.textContent = 'Actions';
  trigger.setAttribute('aria-expanded', 'false');
  trigger.disabled = disabled;
  const menu = document.createElement('div');
  menu.className = 'history-bulk-actions-menu save-menu dropdown-surface';
  const activeProject = typeof _historyGetActiveProjectContextAdapter === 'function' ? _historyGetActiveProjectContextAdapter() : null;
  const selectedTypes = new Set(Array.from(_historySelection.selected.values()).map(_historyItemType));
  const hasOnlyRuns = selectedTypes.size === 1 && selectedTypes.has('run');
  const selectedRuns = _historySelectedRuns();
  const hasOnlyProjectLinkableRuns = hasOnlyRuns
    && selectedRuns.every(run => String(run?.run_kind || 'external') !== 'builtin');
  [
    ['bulk-add-active-project', 'add to active project'],
    ['bulk-add-project', 'add to project'],
    ['bulk-remove-project', 'remove from project'],
    ['bulk-export-txt', 'export text'],
    ['bulk-export-jsonl', 'export JSONL'],
    ['bulk-delete', 'delete'],
  ].forEach(([action, label]) => {
    const item = document.createElement('button');
    item.type = 'button';
    item.className = 'dropdown-item dropdown-item-compact';
    item.dataset.action = action;
    item.textContent = label;
    const projectActionDisabled = !['bulk-delete', 'bulk-export-txt', 'bulk-export-jsonl'].includes(action)
      && !hasOnlyProjectLinkableRuns;
    const historyDeleteDisabled = action === 'bulk-delete'
      && typeof _historyCanManageHistoryAdapter === 'function'
      && !_historyCanManageHistoryAdapter();
    item.disabled = disabled
      || projectActionDisabled
      || historyDeleteDisabled
      || (action === 'bulk-add-active-project' && !(activeProject && activeProject.id));
    if (action === 'bulk-add-active-project' && !(activeProject && activeProject.id)) {
      item.title = 'Select an active project first.';
    } else if (historyDeleteDisabled) {
      item.title = typeof _historyScopeDeniedMessageAdapter === 'function'
        ? _historyScopeDeniedMessageAdapter('delete team history')
        : 'View-only team members cannot delete team history.';
    } else if (projectActionDisabled) {
      item.title = 'Project actions apply to selected external runs.';
    }
    menu.appendChild(item);
  });
  wrap.append(trigger, menu);
  return wrap;
}

function _renderHistoryBulkToolbar() {
  if (typeof historyBulkToolbar === 'undefined' || !historyBulkToolbar) return;
  historyBulkToolbar.replaceChildren();
  const visibleSelectable = _historySelection.visibleItems.filter(_historyIsSelectableItem);
  const shouldShow = _historySelection.selectMode || visibleSelectable.length > 0;
  historyBulkToolbar.classList.toggle('u-hidden', !shouldShow);
  _syncHistoryFilterControls();
  if (!shouldShow) return;

  const selectRow = document.createElement('div');
  selectRow.className = 'history-bulk-select-row';
  const toggleLabel = document.createElement('label');
  toggleLabel.className = 'history-bulk-toggle control-row';
  const toggle = document.createElement('input');
  toggle.type = 'checkbox';
  toggle.checked = !!_historySelection.selectMode;
  toggle.disabled = _historySelection.bulkInFlight;
  const toggleText = document.createElement('span');
  toggleText.textContent = 'select';
  toggleLabel.append(toggle, toggleText);
  toggle.addEventListener('change', () => _historySetSelectMode(toggle.checked));
  selectRow.appendChild(toggleLabel);
  historyBulkToolbar.appendChild(selectRow);

  const count = document.createElement('span');
  count.className = 'history-bulk-count';
  const selectedCount = _historySelection.selected.size;
  count.textContent = `${selectedCount} selected`;
  count.setAttribute('aria-live', 'polite');
  selectRow.appendChild(count);

  const actionRow = document.createElement('div');
  actionRow.className = 'history-bulk-action-row';

  const allSelected = visibleSelectable.length > 0
    && visibleSelectable.every(item => _historySelection.selected.has(_historySelectionKey(item)));
  const someSelected = visibleSelectable.some(item => _historySelection.selected.has(_historySelectionKey(item)));
  const selectAll = document.createElement('button');
  selectAll.className = 'history-action-btn btn btn-secondary btn-compact';
  selectAll.type = 'button';
  selectAll.textContent = allSelected && someSelected ? 'Deselect all' : 'Select all';
  selectAll.disabled = !_historySelection.selectMode || !visibleSelectable.length || _historySelection.bulkInFlight;
  selectAll.setAttribute('aria-pressed', allSelected && someSelected ? 'true' : someSelected ? 'mixed' : 'false');
  selectAll.addEventListener('click', (event) => {
    event.stopPropagation();
    _historySelectAllVisibleItems();
  });
  actionRow.appendChild(selectAll);

  const clear = document.createElement('button');
  clear.className = 'history-action-btn btn btn-secondary btn-compact';
  clear.type = 'button';
  clear.textContent = 'Clear';
  clear.disabled = selectedCount === 0 || _historySelection.bulkInFlight;
  clear.addEventListener('click', (event) => {
    event.stopPropagation();
    _historyClearSelection({ render: false });
    _historyRenderCurrentPanel();
  });
  actionRow.appendChild(clear);

  const actions = _historyBuildBulkActionMenu(selectedCount === 0 || _historySelection.bulkInFlight);
  actionRow.appendChild(actions);
  historyBulkToolbar.appendChild(actionRow);
  _historyBindPressableAdapter(actions.querySelector('[data-action="history-bulk-menu"]'), {
    refocusComposer: false,
    onActivate: (event) => {
      event.preventDefault();
      event.stopPropagation();
      const open = !actions.classList.contains('open');
      actions.classList.toggle('open', open);
      actions.querySelector('[data-action="history-bulk-menu"]')?.setAttribute('aria-expanded', open ? 'true' : 'false');
    },
  });
  _historyBindPressableAdapter(actions.querySelector('[data-action="bulk-add-active-project"]'), {
    refocusComposer: false,
    onActivate: (event) => {
      event.preventDefault();
      event.stopPropagation();
      _closeHistoryBulkActionMenu();
      _historyBulkAddToActiveProject();
    },
  });
  _historyBindPressableAdapter(actions.querySelector('[data-action="bulk-add-project"]'), {
    refocusComposer: false,
    onActivate: (event) => {
      event.preventDefault();
      event.stopPropagation();
      _closeHistoryBulkActionMenu();
      _historyBulkChooseProject('add');
    },
  });
  _historyBindPressableAdapter(actions.querySelector('[data-action="bulk-remove-project"]'), {
    refocusComposer: false,
    onActivate: (event) => {
      event.preventDefault();
      event.stopPropagation();
      _closeHistoryBulkActionMenu();
      _historyBulkRemoveFromAllProjects();
    },
  });
  _historyBindPressableAdapter(actions.querySelector('[data-action="bulk-export-txt"]'), {
    refocusComposer: false,
    onActivate: (event) => {
      event.preventDefault();
      event.stopPropagation();
      _closeHistoryBulkActionMenu();
      _historyBulkExportSelectedItems('txt');
    },
  });
  _historyBindPressableAdapter(actions.querySelector('[data-action="bulk-export-jsonl"]'), {
    refocusComposer: false,
    onActivate: (event) => {
      event.preventDefault();
      event.stopPropagation();
      _closeHistoryBulkActionMenu();
      _historyBulkExportSelectedItems('jsonl');
    },
  });
  _historyBindPressableAdapter(actions.querySelector('[data-action="bulk-delete"]'), {
    refocusComposer: false,
    onActivate: (event) => {
      event.preventDefault();
      event.stopPropagation();
      _closeHistoryBulkActionMenu();
      _historyBulkDeleteSelectedItems();
    },
  });
}

function _buildHistoryRequestUrl() {
  return _historyCore().buildRequestUrl(_historyFilters, _historyPaging);
}

function _applyHistoryClientFilters(runs) {
  return Array.isArray(runs) ? runs.slice() : [];
}

function _renderHistoryEmptyState() {
  if (typeof historyList === 'undefined' || !historyList) return;
  const empty = document.createElement('div');
  empty.className = 'history-empty-state';
  const title = document.createElement('div');
  title.className = 'history-empty-state-title';
  const typeLabel = _historyLabelForType();
  title.textContent = _historyHasAnyFilters()
    ? `No matching ${typeLabel}.`
    : _historyFilters.type === 'snapshots'
      ? 'No snapshots yet.'
      : _historyFilters.type === 'runs'
        ? 'No runs yet.'
        : 'No history yet.';
  empty.appendChild(title);

  const detail = document.createElement('div');
  detail.className = 'history-empty-state-detail';
  detail.textContent = _historyHasAnyFilters()
    ? 'Adjust or clear the current filters to widen the history results.'
    : _historyFilters.type === 'snapshots'
      ? 'Saved snapshots will appear here for this browser session.'
      : _historyFilters.type === 'runs'
        ? 'Completed commands will appear here for this browser session.'
        : 'Completed commands and saved snapshots will appear here for this browser session.';
  empty.appendChild(detail);
  historyList.appendChild(empty);
  if (typeof historyPagination !== 'undefined' && historyPagination) {
    historyPagination.classList.remove('u-hidden');
  }
}

function _scheduleHistoryPanelRefresh() {
  if (_historyFilterRefreshTimer) clearTimeout(_historyFilterRefreshTimer);
  _historyFilterRefreshTimer = setTimeout(() => {
    _historyFilterRefreshTimer = null;
    refreshHistoryPanel();
  }, 120);
}

function _setHistoryFilter(key, value, { debounce = false } = {}) {
  if (key === 'starredOnly') _historyFilters.starredOnly = !!value;
  else _historyFilters[key] = _normalizeHistoryFilterValue(value) || _historyDefaultFilterValue(key);
  if (key === 'type' && _historyFilters.type === 'snapshots') _historyResetRunOnlyFilters();
  if (_historyStructuredFilterKeys.has(key) && _historyRunOnlyFilterIsActive(key) && _historyFilters.type === 'all') {
    _historyFilters.type = 'runs';
  }
  _historyPaging.page = 1;
  _historyClearSelection({ render: false });
  if (debounce) _scheduleHistoryPanelRefresh();
  else refreshHistoryPanel();
}

function openHistoryWithFilters(filters = {}) {
  const selection = window.getSelection?.();
  if (selection && typeof selection.removeAllRanges === 'function') {
    selection.removeAllRanges();
  }
  const nextFilters = {
    ..._historyFilters,
    ...filters,
  };
  if (Object.prototype.hasOwnProperty.call(filters, 'commandRoot')) {
    nextFilters.commandRoot = _normalizeHistoryFilterValue(filters.commandRoot);
  }
  _historyFilters = {
    type: _normalizeHistoryFilterValue(nextFilters.type) || 'all',
    q: _normalizeHistoryFilterValue(nextFilters.q),
    commandRoot: _normalizeHistoryFilterValue(nextFilters.commandRoot),
    signal: _normalizeHistoryFilterValue(nextFilters.signal) || 'all',
    kind: _normalizeHistoryFilterValue(nextFilters.kind) || 'all',
    entity: _normalizeHistoryFilterValue(nextFilters.entity),
    entityType: _normalizeHistoryFilterValue(nextFilters.entityType) || 'all',
    exitCode: _normalizeHistoryFilterValue(nextFilters.exitCode) || 'all',
    dateRange: _normalizeHistoryFilterValue(nextFilters.dateRange) || 'all',
    projectId: _normalizeHistoryFilterValue(nextFilters.projectId) || 'all',
    starredOnly: !!nextFilters.starredOnly,
  };
  if (_historyFilters.type === 'snapshots') _historyResetRunOnlyFilters();
  else if (_historyFilters.type === 'all' && _historyHasActiveRunOnlyFilters()) _historyFilters.type = 'runs';
  _historyPaging.page = 1;
  _historyClearSelection({ render: false });
  _syncHistoryFilterControls();
  _renderHistoryActiveFilters();
  _hideHistoryRootDropdown();
  if (typeof _historyTogglePanelSurfaceAdapter === 'function') {
    _historyTogglePanelSurfaceAdapter(true);
  } else {
    if (typeof _historyShowPanelAdapter === 'function') _historyShowPanelAdapter();
    refreshHistoryPanel();
  }
  return true;
}

function clearHistoryFilters() {
  _historyFilters = {
    type: 'all',
    q: '',
    commandRoot: '',
    signal: 'all',
    kind: 'all',
    entity: '',
    entityType: 'all',
    exitCode: 'all',
    dateRange: 'all',
    projectId: 'all',
    starredOnly: false,
  };
  _historyPaging.page = 1;
  _historyClearSelection({ render: false });
  _syncHistoryFilterControls();
  _renderHistoryActiveFilters();
  _hideHistoryRootDropdown();
  refreshHistoryPanel();
}

function resetHistoryMobileFilters() {
  _historyMobileAdvancedOpen = false;
  _syncHistoryFilterControls();
  _hideHistoryRootDropdown();
}

function toggleHistoryMobileFilters(force = null) {
  const next = force === null ? !_historyMobileAdvancedOpen : !!force;
  _historyMobileAdvancedOpen = next;
  _syncHistoryFilterControls();
  return _historyMobileAdvancedOpen;
}

function _makeOverflowChip(_count) {
  const chip = document.createElement('button');
  chip.className = 'hist-chip hist-chip-overflow chip chip-action';
  chip.textContent = '+ more';
  chip.title = 'Open history panel';
  chip.addEventListener('click', () => {
    if (!historyPanel) return;
    if (typeof resetHistoryMobileFilters === 'function') resetHistoryMobileFilters();
    _historyShowPanelAdapter();
    if (typeof refreshHistoryPanel === 'function') refreshHistoryPanel();
  });
  return chip;
}

function _applyDesktopChipOverflow() {
  const chips = Array.from(histRow.querySelectorAll('.hist-chip:not(.hist-chip-overflow)'));
  if (!chips.length) return;

  // getBoundingClientRect forces a synchronous layout so positions are accurate.
  // In jsdom all rects are zero so the guard below falls through cleanly.
  const firstTop = chips[0].getBoundingClientRect().top;

  // Find the first chip that has wrapped to a second row.
  let overflowIdx = chips.length;
  for (let i = 1; i < chips.length; i++) {
    if (chips[i].getBoundingClientRect().top > firstTop + 2) {
      overflowIdx = i;
      break;
    }
  }
  if (overflowIdx === chips.length) return; // all chips fit on one row

  // Remove overflowing chips and add the history shortcut chip.
  for (let i = chips.length - 1; i >= overflowIdx; i--) {
    histRow.removeChild(chips[i]);
  }
  const overflowChip = _makeOverflowChip();
  histRow.appendChild(overflowChip);

  // If the overflow chip itself wrapped (getBoundingClientRect forces another reflow),
  // keep pulling regular chips until the overflow chip sits on the first row.
  while (overflowChip.getBoundingClientRect().top > firstTop + 2) {
    const regularChips = Array.from(histRow.querySelectorAll('.hist-chip:not(.hist-chip-overflow)'));
    const lastRegularChip = regularChips[regularChips.length - 1];
    if (!lastRegularChip) break;
    histRow.removeChild(lastRegularChip);
  }
}

function _emitHistoryRendered() {
  if (typeof _historyEmitUiEventAdapter === 'function') {
    _historyEmitUiEventAdapter('app:history-rendered', {
      cmdHistory: _historyCmdHistory().slice(),
      recentPreviewHistory: _historyRecentPreviewHistory().slice(),
    });
  }
}

function renderHistory() {
  while (histRow.children.length > 1) histRow.removeChild(histRow.lastChild);
  const commands = _historyCmdHistory();
  if (!commands.length) {
    _historyHideRowAdapter();
    _emitHistoryRendered();
    return;
  }
  _historyShowRowAdapter();

  const starred = _historyGetStarredAdapter();
  // Starred commands first, then remaining in recency order
  const sorted = [
    ...commands.filter(c => starred.has(c)),
    ...commands.filter(c => !starred.has(c)),
  ];

  const isMobile = typeof _historyUseMobileTerminalViewportModeAdapter === 'function' && _historyUseMobileTerminalViewportModeAdapter();
  const visible = isMobile ? sorted.slice(0, 3) : sorted;

  visible.forEach(cmd => {
    const isStarred = starred.has(cmd);
    const chip = document.createElement('button');
    chip.className = 'hist-chip chip chip-action' + (isStarred ? ' starred' : '');
    chip.title = cmd;

    const textEl = document.createElement('span');
    textEl.textContent = cmd;

    if (!isMobile) {
      const starEl = document.createElement('span');
      starEl.className = 'chip-star';
      starEl.textContent = isStarred ? '★' : '☆';
      starEl.title = isStarred ? 'Unstar' : 'Star';
      starEl.addEventListener('click', e => {
        e.stopPropagation();
        _historyToggleStarAdapter(cmd);
        renderHistory();
      });
      chip.appendChild(starEl);
    }

    chip.appendChild(textEl);
    chip.addEventListener('click', () => {
      _historyBlurActiveElementAdapter();
      _historySetComposerValueAdapter(cmd, cmd.length, cmd.length);
      if (_historyRefocusComposerAdapter({ preventScroll: true })) return;
      _historyResetCmdNavAdapter();
    });
    histRow.appendChild(chip);
  });

  if (isMobile && visible.length < sorted.length) {
    histRow.appendChild(_makeOverflowChip());
  } else if (!isMobile) {
    _applyDesktopChipOverflow();
  }

  _emitHistoryRendered();
}

// Re-measure chip overflow when the window is resized on desktop.
if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
  window.addEventListener('resize', () => {
    if (typeof _historyUseMobileTerminalViewportModeAdapter === 'function' && !_historyUseMobileTerminalViewportModeAdapter()) {
      renderHistory();
    }
  });
}



function _historyRenderPanelData(data) {
  historyList.replaceChildren();
  _historyPaging.page = Math.max(1, Number(data.page) || _historyPaging.page || 1);
  _historyPaging.pageSize = Math.max(1, Number(data.page_size) || _historyPaging.pageSize || 1);
  _historyPaging.totalCount = Math.max(0, Number(data.total_count ?? data.items?.length ?? data.runs?.length ?? 0) || 0);
  _historyPaging.pageCount = Math.max(0, Number(data.page_count) || 0);
  _historyPaging.hasPrev = !!data.has_prev;
  _historyPaging.hasNext = !!data.has_next;
  const visibleItems = _applyHistoryClientFilters(Array.isArray(data.items) ? data.items : data.runs);
  _historySelection.visibleItems = visibleItems.filter(_historyIsSelectableItem);
  _renderHistoryBulkToolbar();
  _renderHistoryRootSuggestions(_historyFilters.type === 'snapshots' ? [] : (Array.isArray(data.roots) ? data.roots : data.runs));
  if (!visibleItems.length) {
    _historyRenderPagination(0);
    _renderHistoryEmptyState();
    if (typeof _historyEmitUiEventAdapter === 'function') {
      _historyEmitUiEventAdapter('app:history-panel-refreshed', {
        items: [],
        runs: [],
        roots: Array.isArray(data.roots) ? data.roots.slice() : [],
        paging: { ..._historyPaging },
        filters: { ..._historyFilters },
      });
    }
    return;
  }

  const starred = _historyGetStarredAdapter();
  visibleItems.forEach(item => {
      if (item.type === 'snapshot') {
        const selectable = _historyIsSelectableItem(item);
        const selected = _historySelection.selected.has(_historySelectionKey(item));
        const entry = _historyCreateSnapshotEntryAdapter(item, {
          selectMode: _historySelection.selectMode,
          selectable,
          selected,
          selectionBusy: _historySelection.bulkInFlight,
        });
        entry.addEventListener('click', e => {
          if (e.target.closest('[data-action]')) return;
          const renderedForSelection = entry.classList.contains('history-entry-selecting')
            || !!entry.querySelector('[data-action="select-run"]');
          if (_historySelection.selectMode || renderedForSelection) {
            e.preventDefault();
            e.stopPropagation();
            _historyToggleItemSelection(item);
            return;
          }
          _historyOpenSnapshotLinkAdapter(item);
          _historyHidePanelAdapter();
        });
        const selectionBox = entry.querySelector('[data-action="select-run"]');
        if (selectionBox) {
          selectionBox.addEventListener('change', e => {
            e.stopPropagation();
            _historyToggleItemSelection(item, e.target.checked);
          });
        }

        _historyBindPressableAdapter(entry.querySelector('[data-action="open"]'), {
          onActivate: () => {
            _historyOpenSnapshotLinkAdapter(item);
            _historyHidePanelAdapter();
          },
        });
        _historyBindPressableAdapter(entry.querySelector('[data-action="link"]'), {
          onActivate: () => {
            _historyCopySnapshotLinkAdapter(item).catch(() => _historyShowToastAdapter('Failed to copy link', 'error'));
            if (!_historyActionKeepsPanelOpenAdapter('permalink')) _historyHidePanelAdapter();
          },
        });
        _historyBindPressableAdapter(entry.querySelector('[data-action="edit-metadata"]'), {
          refocusComposer: false,
          onActivate: () => {
            _historyEditEntityMetadataAdapter('snapshot', item);
          },
        });
        _historyBindPressableAdapter(entry.querySelector('[data-action="delete"]'), {
          onActivate: () => {
            _historyConfirmActionAdapter('delete', item.id, item.label || 'snapshot', 'snapshot');
          },
        });
        historyList.appendChild(entry);
        return;
      }

      const run = item;
      const isStarred = starred.has(run.command);
      const selectable = _historyIsSelectableRun(run);
      const selected = _historySelection.selected.has(_historySelectionKey(run));
      const entry = _historyCreateEntryAdapter(run, isStarred, {
        selectMode: _historySelection.selectMode,
        selectable,
        selected,
        selectionBusy: _historySelection.bulkInFlight,
      });

      // Click anywhere on the entry (except buttons) to inspect the run. The
      // modal keeps restore and re-run affordances available without hiding
      // structured findings behind project-only views.
      entry.addEventListener('click', e => {
        if (e.target.closest('[data-action]')) return;
        const renderedForSelection = entry.classList.contains('history-entry-selecting')
          || !!entry.querySelector('[data-action="select-run"]');
        if (_historySelection.selectMode || renderedForSelection) {
          e.preventDefault();
          e.stopPropagation();
          _historyToggleRunSelection(run);
          return;
        }
        _historyOpenRunDetailsAdapter(run);
      });

      const selectionBox = entry.querySelector('[data-action="select-run"]');
      if (selectionBox) {
        selectionBox.addEventListener('change', e => {
          e.stopPropagation();
          _historyToggleRunSelection(run, e.target.checked);
        });
      }

      _historyBindPressableAdapter(entry.querySelector('[data-action="star"]'), {
        onActivate: () => {
          const wasStarred = _historyGetStarredAdapter().has(run.command);
          _historyToggleStarAdapter(run.command);
          const commands = _historyCmdHistory();
          if (!wasStarred && !commands.includes(run.command)) {
            _setHistoryCmdHistory([run.command, ...commands].slice(0, _historyAppConfig().recent_commands_limit));
          }
          if (!_historyActionKeepsPanelOpenAdapter('star')) _historyHidePanelAdapter();
          refreshHistoryPanel();
          renderHistory();
        },
      });

      _historyBindPressableAdapter(entry.querySelector('[data-action="open-schedule"]'), {
        refocusComposer: false,
        onActivate: (event) => {
          event.preventDefault();
          event.stopPropagation();
          const target = event.currentTarget;
          const ownerKind = target?.dataset?.scheduleOwnerKind || run.schedule_owner_kind || '';
          const watcherId = target?.dataset?.scheduleOwnerId || run.schedule_owner_id || run.watcher_id || '';
          const scheduleId = target?.dataset?.scheduleId || run.schedule_id || '';
          if (ownerKind === 'watcher' && watcherId && typeof _historyOpenWatchersModalAdapter === 'function') {
            void _historyOpenWatchersModalAdapter({ watcherId });
          } else if (scheduleId && typeof _historyOpenSchedulesModalAdapter === 'function') {
            void _historyOpenSchedulesModalAdapter({ scheduleId });
          }
        },
      });

      _historyBindPressableAdapter(entry.querySelector('[data-action="copy-command"]'), {
        onActivate: () => {
          _historyCloseActionMenusAdapter();
          _historyCopyTextToClipboardAdapter(run.command)
            .then(() => _historyShowToastAdapter('Command copied'))
            .catch(() => _historyShowToastAdapter('Failed to copy command', 'error'));
        },
      });

      _historyBindPressableAdapter(entry.querySelector('[data-action="restore"]'), {
        onActivate: () => {
          const existing = _historyTabForRunAdapter(run);
          const canUpgradeExisting = !!(existing && run.full_output_available && existing.previewTruncated);
          if (existing && !canUpgradeExisting) {
            _historyActivateTabAdapter(existing.id);
            _historyHidePanelAdapter();
            return;
          }
          const cmdEl = entry.querySelector('.history-entry-cmd');
          cmdEl.textContent = 'loading…';
          if (historyLoadOverlay) {
            historyLoadOverlay.classList.add('open');
            historyLoadOverlay.setAttribute('aria-hidden', 'false');
          }
          _historySetLoadStateAdapter(true);
          _historyRestoreRunIntoTabAdapter(run, {
            targetTabId: canUpgradeExisting ? existing.id : null,
            hidePanelOnSuccess: true,
          })
            .catch(() => {
              entry.querySelector('.history-entry-cmd').textContent = run.command;
              _historyShowToastAdapter('Failed to load run');
            })
            .finally(() => {
              if (historyLoadOverlay) {
                historyLoadOverlay.classList.remove('open');
                historyLoadOverlay.setAttribute('aria-hidden', 'true');
              }
              _historySetLoadStateAdapter(false);
            });
        },
      });

      _historyBindPressableAdapter(entry.querySelector('[data-action="history-menu"]'), {
        refocusComposer: false,
        onActivate: (event) => {
          event.preventDefault();
          event.stopPropagation();
          const wrap = entry.querySelector('.history-action-menu-wrap');
          if (!wrap) return;
          const open = !wrap.classList.contains('open');
          _historyCloseActionMenusAdapter(open ? wrap : null);
          wrap.classList.toggle('open', open);
          entry.querySelector('[data-action="history-menu"]')?.setAttribute('aria-expanded', open ? 'true' : 'false');
          if (open) _historyPositionActionMenuAdapter(wrap);
          else _historyResetActionMenuPositionAdapter(wrap);
        },
      });
      _historyBindPressableAdapter(entry.querySelector('[data-action="permalink"]'), {
        onActivate: () => {
          _historyCloseActionMenusAdapter();
          _historyCopyRunPermalinkAdapter(run).catch(() => _historyShowToastAdapter('Failed to copy link', 'error'));
          if (!_historyActionKeepsPanelOpenAdapter('permalink')) _historyHidePanelAdapter();
        },
      });
      _historyBindPressableAdapter(entry.querySelector('[data-action="edit-metadata"]'), {
        refocusComposer: false,
        onActivate: () => {
          _historyCloseActionMenusAdapter();
          _historyEditEntityMetadataAdapter('run', run);
        },
      });
      _historyBindPressableAdapter(entry.querySelector('[data-action="open-atlas"]'), {
        refocusComposer: false,
        onActivate: (event) => {
          event.preventDefault();
          event.stopPropagation();
          _historyCloseActionMenusAdapter();
          if (typeof _historyOpenAtlasAdapter === 'function') void _historyOpenAtlasAdapter({ source: 'history-run' });
        },
      });
      _historyBindPressableAdapter(entry.querySelector('[data-action="watch-command"]'), {
        refocusComposer: false,
        onActivate: (event) => {
          event.preventDefault();
          event.stopPropagation();
          _historyCloseActionMenusAdapter();
          if (typeof _historyOpenWatchersModalAdapter === 'function') void _historyOpenWatchersModalAdapter({ baselineRun: run });
        },
      });
      _historyBindPressableAdapter(entry.querySelector('[data-action="compare"]'), {
        refocusComposer: false,
        onActivate: () => {
          _historyCloseActionMenusAdapter();
          const opened = _historyOpenCompareLauncherAdapter(run);
          if (!opened) {
            _historyShowToastAdapter('Run comparison is not available.', 'error');
            return;
          }
          if (!_historyActionKeepsPanelOpenAdapter('compare')) _historyHidePanelAdapter();
        },
      });
      _historyBindPressableAdapter(entry.querySelector('[data-action="add-active-project"]'), {
        refocusComposer: false,
        onActivate: (event) => {
          event.preventDefault();
          event.stopPropagation();
          _historyCloseActionMenusAdapter();
          _historyAddRunToActiveProjectAdapter(run).catch(() => _historyShowToastAdapter('Failed to add run to active project', 'error'));
        },
      });
      _historyBindPressableAdapter(entry.querySelector('[data-action="add-project"]'), {
        refocusComposer: false,
        onActivate: (event) => {
          event.preventDefault();
          event.stopPropagation();
          _historyCloseActionMenusAdapter();
          _historyAddRunToProjectAdapter(run).catch(() => _historyShowToastAdapter('Failed to add run to project', 'error'));
        },
      });
      _historyBindPressableAdapter(entry.querySelector('[data-action="remove-project"]'), {
        refocusComposer: false,
        onActivate: (event) => {
          event.preventDefault();
          event.stopPropagation();
          _historyCloseActionMenusAdapter();
          _historyRemoveRunFromProjectAdapter(run).catch(() => _historyShowToastAdapter('Failed to remove run from project', 'error'));
        },
      });
      _historyBindPressableAdapter(entry.querySelector('[data-action="copy-run-id"]'), {
        onActivate: () => {
          _historyCloseActionMenusAdapter();
          _historyCopyTextToClipboardAdapter(run.id)
            .then(() => _historyShowToastAdapter('Run ID copied'))
            .catch(() => _historyShowToastAdapter('Failed to copy run ID', 'error'));
        },
      });
      _historyBindPressableAdapter(entry.querySelector('[data-action="delete"]'), {
        onActivate: () => {
          _historyCloseActionMenusAdapter();
          _historyConfirmActionAdapter('delete', run.id, run.command);
        },
      });

      historyList.appendChild(entry);
    });
    _historyRenderPagination(visibleItems.length);
    if (typeof _historyEmitUiEventAdapter === 'function') {
      _historyEmitUiEventAdapter('app:history-panel-refreshed', {
        items: visibleItems.slice(),
        runs: visibleItems.filter(item => item.type === 'run').slice(),
        roots: Array.isArray(data.roots) ? data.roots.slice() : [],
        paging: { ..._historyPaging },
        filters: { ..._historyFilters },
      });
    }
}

function _historyRenderCurrentPanel() {
  if (!_historyLatestPanelData) {
    _renderHistoryBulkToolbar();
    return refreshHistoryPanel();
  }
  _historyRenderPanelData(_historyLatestPanelData);
  return Promise.resolve();
}

function refreshHistoryPanel() {
  // The panel is populated on demand so we always fetch the latest persisted
  // history instead of assuming the in-memory tab state is authoritative.
  return Promise.resolve(_historyEnsureProjectFilterOptionsAdapter())
    .catch(() => [])
    .then(() => {
      _syncHistoryFilterControls();
      _renderHistoryActiveFilters();
      return _historyApiFetchAdapter(_buildHistoryRequestUrl());
    })
    .then(r => r.json())
    .then(data => {
      _historyLatestPanelData = data;
      _historyRenderPanelData(data);
    });
}

if (typeof document !== 'undefined' && typeof document.addEventListener === 'function') {
  document.addEventListener('click', (event) => {
    if (event.target && event.target.closest && event.target.closest('.history-action-menu-wrap')) return;
    if (event.target && event.target.closest && event.target.closest('.history-bulk-actions-wrap')) return;
    if (event.target && event.target.closest && event.target.closest('.history-compare-actions-menu-wrap')) return;
    if (event.target && event.target.closest && event.target.closest('.history-run-action-menu-wrap')) return;
    _historyCloseActionMenusAdapter();
    _closeHistoryBulkActionMenu();
    _closeHistoryCompareActionMenusIfLoaded();
    _historyCloseRunActionMenusAdapter();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      _historyCloseActionMenusAdapter();
      _closeHistoryBulkActionMenu();
      _closeHistoryCompareActionMenusIfLoaded();
      _historyCloseRunActionMenusAdapter();
    }
  });
}
if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
  window.addEventListener('resize', () => {
    _historyCloseActionMenusAdapter();
    _closeHistoryBulkActionMenu();
    _closeHistoryCompareActionMenusIfLoaded();
    _historyCloseRunActionMenusAdapter();
  });
  window.addEventListener('scroll', () => {
    _historyCloseActionMenusAdapter();
    _closeHistoryBulkActionMenu();
    _closeHistoryCompareActionMenusIfLoaded();
    _historyCloseRunActionMenusAdapter();
  }, true);
}

if (typeof historySearchInput !== 'undefined' && historySearchInput) {
  historySearchInput.addEventListener('input', e => {
    _setHistoryFilter('q', e.target.value, { debounce: true });
  });
}

if (typeof historyMobileFiltersToggle !== 'undefined' && historyMobileFiltersToggle) {
  historyMobileFiltersToggle.addEventListener('click', e => {
    e.preventDefault();
    e.stopPropagation();
    toggleHistoryMobileFilters();
  });
}

if (typeof historyRootInput !== 'undefined' && historyRootInput) {
  historyRootInput.addEventListener('input', e => {
    if (_historyRootSuppressInputOnce) {
      _historyRootSuppressInputOnce = false;
      return;
    }
    _historyRootIndex = -1;
    _historyRefreshRootDropdown();
    _setHistoryFilter('commandRoot', e.target.value, { debounce: true });
  });
  historyRootInput.addEventListener('focus', () => {
    _historyRootInputFocused = true;
    _historyRootIndex = -1;
    _historyRefreshRootDropdown();
  });
  historyRootInput.addEventListener('blur', () => {
    setTimeout(() => {
      _historyRootInputFocused = false;
      _hideHistoryRootDropdown();
    }, 0);
  });
  historyRootInput.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      e.preventDefault();
      _hideHistoryRootDropdown();
      return;
    }
    if (e.key === 'ArrowDown') {
      if (!_historyRootFiltered.length) return;
      e.preventDefault();
      _historyRootIndex = (_historyRootIndex + 1) % _historyRootFiltered.length;
      _renderHistoryRootDropdown(_historyRootFiltered, historyRootInput.value);
      return;
    }
    if (e.key === 'ArrowUp') {
      if (!_historyRootFiltered.length) return;
      e.preventDefault();
      _historyRootIndex = _historyRootIndex <= 0 ? _historyRootFiltered.length - 1 : _historyRootIndex - 1;
      _renderHistoryRootDropdown(_historyRootFiltered, historyRootInput.value);
      return;
    }
    if (e.key === 'Enter' && _historyRootIndex >= 0 && _historyRootFiltered[_historyRootIndex]) {
      e.preventDefault();
      _acceptHistoryRootSuggestion(_historyRootFiltered[_historyRootIndex]);
    }
  });
}

if (typeof historyTypeFilter !== 'undefined' && historyTypeFilter) {
  historyTypeFilter.addEventListener('change', e => {
    _setHistoryFilter('type', e.target.value);
  });
}

if (typeof historyExitFilter !== 'undefined' && historyExitFilter) {
  historyExitFilter.addEventListener('change', e => {
    _setHistoryFilter('exitCode', e.target.value);
  });
}

if (typeof historySignalFilter !== 'undefined' && historySignalFilter) {
  historySignalFilter.addEventListener('change', e => {
    _setHistoryFilter('signal', e.target.value);
  });
}

if (typeof historyKindFilter !== 'undefined' && historyKindFilter) {
  historyKindFilter.addEventListener('change', e => {
    _setHistoryFilter('kind', e.target.value);
  });
}

if (typeof historyEntityInput !== 'undefined' && historyEntityInput) {
  historyEntityInput.addEventListener('input', e => {
    _setHistoryFilter('entity', e.target.value, { debounce: true });
  });
}

if (typeof historyEntityTypeFilter !== 'undefined' && historyEntityTypeFilter) {
  historyEntityTypeFilter.addEventListener('change', e => {
    _setHistoryFilter('entityType', e.target.value);
  });
}

if (typeof historyDateFilter !== 'undefined' && historyDateFilter) {
  historyDateFilter.addEventListener('change', e => {
    _setHistoryFilter('dateRange', e.target.value);
  });
}

if (typeof historyProjectFilter !== 'undefined' && historyProjectFilter) {
  historyProjectFilter.addEventListener('focus', () => {
    _historyEnsureProjectFilterOptionsAdapter().catch(() => {});
  });
  historyProjectFilter.addEventListener('change', e => {
    _setHistoryFilter('projectId', e.target.value);
  });
}

if (typeof historyStarredToggle !== 'undefined' && historyStarredToggle) {
  historyStarredToggle.addEventListener('change', e => {
    _setHistoryFilter('starredOnly', e.target.checked);
  });
}

if (typeof historyClearFiltersBtn !== 'undefined' && historyClearFiltersBtn) {
  historyClearFiltersBtn.addEventListener('click', () => clearHistoryFilters());
}

_syncHistoryFilterControls();

if (typeof importedSetHistoryPanelHandlers === 'function') {
  importedSetHistoryPanelHandlers({
    openHistoryWithFilters,
    refreshHistoryPanel,
    renderHistory,
    resetHistoryMobileFilters,
    resetHistorySelectionOnClose: _historyResetSelectionOnClose,
  });
}

export {
  _applyHistoryClientFilters,
  _buildHistoryRequestUrl,
  _closeHistoryCompareActionMenusIfLoaded,
  _compareDateGroupLabel,
  _compareFormatDate,
  _compareFormatDelta,
  _compareFormatDuration,
  _historyCompareAnchorTone,
  _historyCompareBucketTone,
  _historyCompareBuildAnchorMap,
  _historyCompareCoerceContext,
  _historyCompareCoerceViewMode,
  _historyCompareContextLimit,
  _historyCompareCssEscape,
  _historyCompareLineLimit,
  _historyCompareNumber,
  _historyCompareOmittedTotal,
  _historyCompareResolveViewMode,
  _historyCompareStoredContext,
  _historyCompareStoredViewMode,
  _historyCompareTotalChangedLines,
  _historyCompareViewportMode,
  _historyCompareViewModeOptions,
  _historyCore,
  _historyDefaultFilterValue,
  _historyHasActiveRunOnlyFilters,
  _historyHasActiveServerFilters,
  _historyHasAnyFilters,
  _historyLabelForType,
  _historyResetRunOnlyFilters,
  _historyRunOnlyFilterIsActive,
  _historySummaryLabel,
  _normalizeHistoryFilterValue,
  clearHistoryFilters,
  getHistoryProjectOptionsState,
  openHistoryWithFilters,
  refreshHistoryPanel,
  renderHistory,
  resetHistoryMobileFilters,
  setHistoryProjectOptionsState,
  _historyResetSelectionOnClose as resetHistorySelectionOnClose,
  toggleHistoryMobileFilters,
};
