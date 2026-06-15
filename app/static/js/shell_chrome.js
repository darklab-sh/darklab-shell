// ── Shell chrome controller ──
// Owns the desktop rail (Recent, Workflows, nav) and the bottom HUD.
// Loaded after the shell core, the active-project HUD helpers, and controller.js.
// The heavier Projects workspace controllers are loaded on first workspace open.

import {
  openOptions as importedOpenOptions,
  openThemeSelector as importedOpenThemeSelector,
} from './app.js';
import { closeMajorOverlays as importedCloseMajorOverlays } from './ui/overlay_actions_bridge.js';
import { setControllerActionHandlers as importedSetControllerActionHandlers } from './controller_action_bridge.js';
import {
  openFaq as importedOpenFaq,
  openWorkflows as importedOpenWorkflows,
  toggleHistoryPanelSurface as importedToggleHistoryPanelSurface,
} from './controller.js';
import { openWorkspace as importedOpenWorkspace } from './workspace.js';
import { setProjectContextHandlers as importedSetProjectContextHandlers } from './features/projects/project_context_bridge.js';
import { setProjectHudHandlers as importedSetProjectHudHandlers } from './features/projects/project_hud_bridge.js';
import { DarklabProjectActiveContext as importedProjectActiveContext } from './features/projects/project_active_context.js';
import { DarklabProjectSharedUi as importedProjectSharedUi } from './features/projects/project_shared_ui.js';
import { DarklabProjectWorkspaceState as importedProjectWorkspaceState } from './features/projects/project_workspace_state.js';
import {
  copyTab as importedCopyTab,
  exportTabHtml as importedExportTabHtml,
  exportTabPdf as importedExportTabPdf,
  permalinkTab as importedPermalinkTab,
  saveTab as importedSaveTab,
} from './features/tabs/tab_exports.js';
import {
  activeTeamScopeCan as importedActiveTeamScopeCan,
  teamScopeDeniedMessage as importedTeamScopeDeniedMessage,
} from './features/team_scope.js';
import {
  ensureWorkflowCatalogLoaded as importedEnsureWorkflowCatalogLoaded,
  hasWorkflowHandler as importedHasWorkflowHandler,
  renderWorkflowItems as importedRenderWorkflowItems,
} from './features/workflows/workflows_bridge.js';
import {
  getActiveTabId as importedGetActiveTabId,
  getAppState as importedGetAppState,
  getTab as importedGetTab,
  getTabs as importedGetTabs,
  emitUiEvent as importedEmitUiEvent,
  onUiEvent as importedOnUiEvent,
} from './core/state.js';
import {
  downloadBlobAsAttachment as importedDownloadBlobAsAttachment,
  downloadUrlAsAttachment as importedDownloadUrlAsAttachment,
  showToast as importedShowToast,
} from './core/utils.js';
import {
  apiFetch as importedApiFetch,
  logClientError as importedLogClientError,
  maskSessionToken as importedMaskSessionToken,
} from './session.js';
import { confirmKill as importedConfirmKill } from './runner_bridge.js';
import {
  getHudClockPreference as importedGetHudClockPreference,
  getPreference as importedGetPreference,
  setPreferenceCookie as importedSetPreferenceCookie,
} from './features/preferences/preferences.js';
import { _getStarred as importedGetStarred } from './features/history/history_actions.js';
import { DarklabEntityMetadata as importedEntityMetadata } from './ui/ui_entity_metadata.js';
import { ProjectTargetValidation as importedProjectTargetValidation } from './features/projects/project_target_validation.js';
import { DarklabProjectWorkspaceConstants as importedProjectWorkspaceConstants } from './features/projects/project_workspace_constants.js';
import { bindDisclosure as importedBindDisclosure } from './ui/ui_disclosure.js';
import { bindDismissible as importedBindDismissible } from './ui/ui_dismissible.js';
import { bindMobileSheet as importedBindMobileSheet } from './ui/mobile_sheet.js';
import { bindOutsideClickClose as importedBindOutsideClickClose } from './ui/ui_outside_click.js';
import { bindPressable as importedBindPressable } from './ui/ui_pressable.js';
import { showConfirm as importedShowConfirm } from './ui/ui_confirm.js';
import {
  blurVisibleComposerInputIfMobile as importedBlurVisibleComposerInputIfMobile,
  enhanceAppSelects as importedEnhanceAppSelects,
  markInteractionSurfaceReady as importedMarkInteractionSurfaceReady,
  refocusComposerAfterAction as importedRefocusComposerAfterAction,
  setComposerValue as importedSetComposerValue,
  showWorkflowsOverlay as importedShowWorkflowsOverlay,
} from './ui/ui_helpers.js';
import { useMobileTerminalViewportMode as importedUseMobileTerminalViewportMode } from './features/mobile/mobile_shell_layout.js';

let importedOpenAtlas;
let importedOpenFindingsBoard;
let importedOpenCommandRegistry;
let importedOpenSchedulesModal;
let importedOpenStatusMonitor;
let importedOpenWatchersModal;
let importedProjectActivity;
let importedProjectArtifacts;
let importedProjectDetails;
let importedProjectEntities;
let importedProjectEntityEditor;
let importedProjectFilters;
let importedProjectFindings;
let importedProjectFindingsBoard;
let importedProjectFindingsData;
let importedProjectList;
let importedProjectMobileCompare;
let importedProjectMobileDetail;
let importedProjectMobileShell;
let importedProjectNavigation;
let importedProjectNestedSheets;
let importedProjectPackages;
let importedProjectReport;
let importedProjectRuns;
let importedProjectTargets;
let importedProjectWorkspaceActions;
let importedProjectWorkspaceBootstrap;
let importedProjectWorkspaceEvents;
let importedProjectWorkspaceLifecycle;
let importedProjectWorkspaceRenderer;
let importedProjectWorkspaceShell;

(function initShellChrome(global) {
  if (typeof document === 'undefined') return;

  function _shellFn(name, imported = null) {
    if (typeof imported === 'function') return imported;
    const fn = global && global[name];
    return typeof fn === 'function' ? fn : null;
  }

  function _shellValue(name, imported = undefined) {
    return imported !== undefined ? imported : (global ? global[name] : undefined);
  }

  function _projectModule(name, imported = undefined) {
    return _shellValue(name, imported) || null;
  }

  const _shellApiFetch = (...args) => _shellFn('apiFetch', importedApiFetch)?.(...args);
  const _shellLogClientError = (...args) => _shellFn('logClientError', importedLogClientError)?.(...args);
  const _shellShowToast = (...args) => _shellFn('showToast', importedShowToast)?.(...args);
  const _shellBindPressable = (...args) => _shellFn('bindPressable', importedBindPressable)?.(...args);
  const _shellBindOutsideClickClose = (...args) => _shellFn('bindOutsideClickClose', importedBindOutsideClickClose)?.(...args);
  const _shellBindDisclosure = (...args) => _shellFn('bindDisclosure', importedBindDisclosure)?.(...args);
  const _shellGetPreference = (name) => _shellFn('getPreference', importedGetPreference)?.(name) || '';
  const _shellSetPreferenceCookie = (name, value) => _shellFn('setPreferenceCookie', importedSetPreferenceCookie)?.(name, value);
  const _shellRefocusComposer = (...args) => _shellFn('refocusComposerAfterAction', importedRefocusComposerAfterAction)?.(...args);
  const _shellSetComposerValue = (...args) => _shellFn('setComposerValue', importedSetComposerValue)?.(...args);
  const _shellDownloadBlobAsAttachment = (...args) => _shellFn('downloadBlobAsAttachment', importedDownloadBlobAsAttachment)?.(...args);
  const _shellDownloadUrlAsAttachment = (...args) => _shellFn('downloadUrlAsAttachment', importedDownloadUrlAsAttachment)?.(...args);
  const _shellMaskSessionToken = (token) => _shellFn('maskSessionToken', importedMaskSessionToken)?.(token) || token;
  const _shellShowConfirm = (...args) => _shellFn('showConfirm', importedShowConfirm)?.(...args);
  const _shellUseMobileTerminalViewportMode = () => !!_shellFn('useMobileTerminalViewportMode', importedUseMobileTerminalViewportMode)?.();
  const _shellGetActiveTabId = () => _shellFn('getActiveTabId', importedGetActiveTabId)?.() || null;
  const _shellGetAppState = () => _shellFn('getAppState', importedGetAppState)?.() || {};
  const _shellGetTab = (id) => _shellFn('getTab', importedGetTab)?.(id) || null;
  const _shellTabs = () => {
    const list = _shellFn('getTabs', importedGetTabs)?.();
    return Array.isArray(list) ? list : [];
  };
  const _shellEmitUiEvent = (...args) => _shellFn('emitUiEvent', importedEmitUiEvent)?.(...args);
  const _shellOnUiEvent = (...args) => _shellFn('onUiEvent', importedOnUiEvent)?.(...args);

  function _shellActiveTeamScopeCan(capability) {
    const can = (typeof importedActiveTeamScopeCan !== 'undefined' && importedActiveTeamScopeCan) || null;
    return typeof can === 'function' ? can(capability) : true;
  }

  function _shellTeamScopeDeniedMessage(action) {
    const denied = (typeof importedTeamScopeDeniedMessage !== 'undefined' && importedTeamScopeDeniedMessage) || null;
    return typeof denied === 'function'
      ? denied(action)
      : `View-only team members can't ${action}. Switch to Personal or ask for operator access.`;
  }

  function _shellEnhanceAppSelects() {
    return (typeof importedEnhanceAppSelects !== 'undefined' && importedEnhanceAppSelects) || null;
  }

  // ── Elements ────────────────────────────────────────────────────
  const rail              = document.getElementById('rail');
  if (!rail) return; // mobile-only DOM build; nothing to do

  const railCollapseBtn   = document.getElementById('rail-collapse-btn');
  const railResizeHandle  = document.getElementById('rail-resize-handle');
  const railSplitArea     = document.getElementById('rail-split-area');
  const railSplitter      = document.getElementById('rail-splitter');
  const railSectionRecent = document.getElementById('rail-section-recent');
  const railRecentBody    = document.getElementById('rail-recent-list');
  const railRecentCount   = document.getElementById('rail-recent-count');
  const railRecentHeader  = document.getElementById('rail-recent-header');
  const railSectionWorkflows = document.getElementById('rail-section-workflows');
  const railWorkflowsBody = document.getElementById('rail-workflows-list');
  const railWorkflowsHeader = document.getElementById('rail-workflows-header');
  const railWorkflowsCount = document.getElementById('rail-workflows-count');
  const railNav           = document.getElementById('rail-nav');
  const railMoreBtn       = document.getElementById('rail-more-btn');
  const railMoreMenu      = document.getElementById('rail-more-menu');

  const hud               = document.getElementById('hud');
  const hudLastExitEl     = document.getElementById('hud-last-exit');
  const hudTabsEl         = document.getElementById('hud-tabs');
  const hudLatencyEl      = document.getElementById('hud-latency');
  const hudSessionEl      = document.getElementById('hud-session');
  const hudProjectCell    = document.getElementById('hud-project-cell');
  const hudProjectEl      = document.getElementById('hud-project');
  const hudUptimeEl       = document.getElementById('hud-uptime');
  const hudClockEl        = document.getElementById('hud-clock');
  const hudDbEl           = document.getElementById('hud-db');
  const hudRedisEl        = document.getElementById('hud-redis');
  const projectWorkspaceOverlay = document.getElementById('project-workspace-overlay');
  const projectWorkspaceModal = document.getElementById('project-workspace-modal');
  const projectWorkspaceBody = document.getElementById('project-workspace-body');
  const projectWorkspacePagination = document.getElementById('project-workspace-pagination');
  const projectExplorerBody = document.getElementById('project-explorer-body');
  const projectWorkspaceSubtitle = document.getElementById('project-workspace-subtitle');
  const projectWorkspaceCreateForm = document.getElementById('project-workspace-create-form');
  const projectWorkspaceNameInput = document.getElementById('project-workspace-name');
  const projectMobileRoot = document.getElementById('project-mobile-root');
  const projectMobileListView = document.getElementById('project-mobile-list-view');
  const projectMobileBody = document.getElementById('project-mobile-body');
  const projectMobilePagination = document.getElementById('project-mobile-pagination');
  const projectMobileSummary = document.getElementById('project-mobile-summary');
  const projectMobileCreateForm = document.getElementById('project-mobile-create-form');
  const projectMobileNameInput = document.getElementById('project-mobile-name');
  const projectMobileDetailView = document.getElementById('project-mobile-detail-view');
  const projectMobileDetailTopbar = document.getElementById('project-mobile-detail-topbar');
  const projectMobileTabs = document.getElementById('project-mobile-tabs');
  const projectMobileDetailBody = document.getElementById('project-mobile-detail-body');
  const projectTargetEditorOverlay = document.getElementById('project-target-editor-overlay');
  const projectTargetEditorTitle = document.getElementById('project-target-editor-title');
  const projectTargetCreateForm = document.getElementById('project-target-create-form');
  const projectTargetTypeSelect = document.getElementById('project-target-type');
  const projectTargetValueInput = document.getElementById('project-target-value');
  const projectTargetValueHelp = document.getElementById('project-target-value-help');
  const projectTargetValueError = document.getElementById('project-target-value-error');
  const projectTargetLabelInput = document.getElementById('project-target-label');
  const projectTargetNotesInput = document.getElementById('project-target-notes');
  const projectTargetSubmitButton = document.getElementById('project-target-submit');
  const projectPackageManifestOverlay = document.getElementById('project-package-manifest-overlay');
  const projectPackageManifestTitle = document.getElementById('project-package-manifest-title');
  const projectPackageManifestSummary = document.getElementById('project-package-manifest-summary');
  const projectPackageManifestJson = document.getElementById('project-package-manifest-json');
  const projectPackageWizardOverlay = document.getElementById('project-package-wizard-overlay');
  const projectPackageWizardBody = document.getElementById('project-package-wizard-body');
  const projectEntityEditorOverlay = document.getElementById('project-entity-editor-overlay');
  const projectEntityEditorTitle = document.getElementById('project-entity-editor-title');
  const projectEntityEditorSubtitle = document.getElementById('project-entity-editor-subtitle');
  const projectEntityEditorForm = document.getElementById('project-entity-editor-form');
  const projectEntityLabelsInput = document.getElementById('project-entity-labels');
  const projectEntityNoteInput = document.getElementById('project-entity-note');
  const projectEntityActivityRoot = document.getElementById('project-entity-activity');
  const projectEntitySubmitButton = document.getElementById('project-entity-submit');
  const projectNotesForm = document.getElementById('project-notes-form');
  const projectNotesInput = document.getElementById('project-notes-input');
  const projectLabelsForm = document.getElementById('project-labels-form');
  const projectLabelsInput = document.getElementById('project-labels-input');
  const projectLabelsSaveButton = document.getElementById('project-labels-save-btn');
  const projectWorkspaceMessage = document.getElementById('project-workspace-message');
  const EntityMetadataClient = (typeof importedEntityMetadata !== 'undefined' && importedEntityMetadata) || {};

  // ── Prefs (cookie-backed) ───────────────────────────────────────
  const PREF_COLLAPSED = 'pref_rail_collapsed';
  const PREF_WIDTH     = 'pref_rail_width';
  const PREF_RECENT    = 'pref_rail_recent_open';
  const PREF_WORKFLOWS = 'pref_rail_workflows_open';

  const MIN_W = 180, MAX_W = 360, DEFAULT_W = 214;
  const NARROW_BRAND_W = 200;
  const MIN_SECTION_H = 80;
  const PROJECT_TARGET_HELPERS = (typeof importedProjectTargetValidation !== 'undefined' && importedProjectTargetValidation) || null;
  if (!PROJECT_TARGET_HELPERS) throw new Error('ProjectTargetValidation is unavailable');
  const PROJECT_TARGET_TYPES = PROJECT_TARGET_HELPERS.TARGET_TYPES;
  const PROJECT_WORKSPACE_CONSTANTS = (
    typeof importedProjectWorkspaceConstants !== 'undefined'
    && importedProjectWorkspaceConstants
  ) || null;
  if (!PROJECT_WORKSPACE_CONSTANTS) throw new Error('DarklabProjectWorkspaceConstants is unavailable');

  const readBool = (name, dflt) => {
    const v = _shellGetPreference(name);
    if (v === '1' || v === 'true') return true;
    if (v === '0' || v === 'false') return false;
    return dflt;
  };
  const writePref = (name, value) => {
    _shellSetPreferenceCookie(name, String(value));
  };

  // ── State ────────────────────────────────────────────────────────
  const ui = {
    collapsed: readBool(PREF_COLLAPSED, false),
    railW: (() => {
      const raw = parseInt(_shellGetPreference(PREF_WIDTH), 10);
      return Number.isFinite(raw) ? Math.max(MIN_W, Math.min(MAX_W, raw)) : DEFAULT_W;
    })(),
    recentOpen: readBool(PREF_RECENT, true),
    workflowsOpen: readBool(PREF_WORKFLOWS, true),
    recentHeight: null, // null → auto-size next time Workflows opens
  };

  let allWorkflows = [];
  const projectWorkspaceStateFactory = importedProjectWorkspaceState
    && importedProjectWorkspaceState.createProjectWorkspaceState;
  if (typeof projectWorkspaceStateFactory !== 'function') throw new Error('DarklabProjectWorkspaceState is unavailable');
  const projectWorkspaceState = projectWorkspaceStateFactory();
  const PROJECT_WORKSPACE_LAZY_GLOBALS = [
    ['DarklabProjectDetails', 'createProjectDetailsController'],
    ['DarklabProjectList', 'createProjectListController'],
    ['DarklabProjectNavigation', 'createProjectNavigationController'],
    ['DarklabProjectEntityEditor', 'createProjectEntityEditorController'],
    ['DarklabProjectWorkspaceActions', 'createProjectWorkspaceActionsController'],
    ['DarklabProjectWorkspaceShell', 'createProjectWorkspaceShellController'],
    ['DarklabProjectWorkspaceLifecycle', 'createProjectWorkspaceLifecycleController'],
    ['DarklabProjectWorkspaceRenderer', 'createProjectWorkspaceRendererController'],
    ['DarklabProjectWorkspaceBootstrap', 'createProjectWorkspaceBootstrapController'],
    ['DarklabProjectNestedSheets', 'createProjectNestedSheetsController'],
    ['DarklabProjectWorkspaceEvents', 'createProjectWorkspaceEventsController'],
    ['DarklabProjectTargets', 'createProjectTargetsController'],
    ['DarklabProjectRuns', 'createProjectRunsController'],
    ['DarklabProjectMobileCompare', 'createProjectMobileCompareController'],
    ['DarklabProjectMobileShell', 'createProjectMobileShellController'],
    ['DarklabProjectMobileDetail', 'createProjectMobileDetailController'],
    ['DarklabProjectFindingsData', 'createProjectFindingsDataController'],
    ['DarklabProjectFilters', 'createProjectFiltersController'],
    ['DarklabProjectEntities', 'createProjectEntitiesController'],
    ['DarklabProjectFindings', 'createProjectFindingsController'],
    ['DarklabProjectFindingsBoard', 'createProjectFindingsBoardController'],
  ];
  let projectWorkspaceModulesPromise = null;
  let projectWorkspaceBootstrapped = false;

  function _projectWorkspaceModulesReady() {
    return PROJECT_WORKSPACE_LAZY_GLOBALS.every(([name, factory]) => (
      global[name] && typeof global[name][factory] === 'function'
    ));
  }

  function _projectWorkspaceOverlayOpenFallback() {
    return !!(projectWorkspaceOverlay && projectWorkspaceOverlay.classList.contains('open'));
  }

  function _bindProjectWorkspaceIfNeeded() {
    if (projectWorkspaceBootstrapped) return;
    _projectWorkspaceBootstrapController().bindAll();
    projectWorkspaceBootstrapped = true;
  }

  async function _ensureProjectWorkspaceModules() {
    if (_projectWorkspaceModulesReady()) {
      _bindProjectWorkspaceIfNeeded();
      return;
    }
    if (!projectWorkspaceModulesPromise) {
      const loader = global.loadProjectWorkspace;
      if (typeof loader !== 'function') throw new Error('Project workspace loader is unavailable');
      projectWorkspaceModulesPromise = loader()
        .then(() => {
          if (!_projectWorkspaceModulesReady()) throw new Error('Project workspace modules did not finish loading');
          _bindProjectWorkspaceIfNeeded();
        })
        .finally(() => {
          projectWorkspaceModulesPromise = null;
        });
    }
    await projectWorkspaceModulesPromise;
  }
  // ── Layout application ──────────────────────────────────────────
  function applyCollapsed() {
    rail.classList.toggle('rail-collapsed', ui.collapsed);
    rail.classList.toggle('rail-narrow-brand', !ui.collapsed && ui.railW <= NARROW_BRAND_W);
    rail.style.setProperty('--rail-w', ui.collapsed ? '44px' : `${ui.railW}px`);
    if (railCollapseBtn) {
      railCollapseBtn.textContent = ui.collapsed ? '»' : '«';
      const label = ui.collapsed ? 'Expand sidebar (Alt+\\)' : 'Collapse sidebar (Alt+\\)';
      railCollapseBtn.title = label;
      railCollapseBtn.setAttribute('aria-label', label);
    }
  }

  function applyWidth() {
    rail.classList.toggle('rail-narrow-brand', !ui.collapsed && ui.railW <= NARROW_BRAND_W);
    if (!ui.collapsed) rail.style.setProperty('--rail-w', `${ui.railW}px`);
  }

  function applySectionsState() {
    if (!railSplitArea) return;
    railSectionRecent?.classList.toggle('closed', !ui.recentOpen);
    railSectionWorkflows?.classList.toggle('closed', !ui.workflowsOpen);

    const bothOpen = ui.recentOpen && ui.workflowsOpen;
    railSplitArea.classList.toggle('both-open', bothOpen);
    railSplitArea.classList.toggle('workflows-closed', !ui.workflowsOpen);
    railSplitArea.classList.toggle('recent-fixed', bothOpen && ui.recentHeight != null);

    if (railSplitter) railSplitter.hidden = !bothOpen;

    if (bothOpen && ui.recentHeight != null) {
      railSplitArea.style.setProperty('--recent-h', `${ui.recentHeight}px`);
    } else {
      railSplitArea.style.removeProperty('--recent-h');
    }
  }

  // ── Collapse ─────────────────────────────────────────────────────
  function setCollapsed(next) {
    ui.collapsed = !!next;
    applyCollapsed();
    writePref(PREF_COLLAPSED, ui.collapsed ? '1' : '0');
  }
  function toggleRailCollapsed() {
    setCollapsed(!ui.collapsed);
  }
  railCollapseBtn?.addEventListener('click', () => setCollapsed(!ui.collapsed));

  // ── Horizontal drag ──────────────────────────────────────────────
  let railDrag = null;
  function beginRailDrag(clientX) {
    railDrag = { startX: clientX, startW: ui.railW };
    rail.classList.add('rail-dragging');
    document.body.style.cursor = 'ew-resize';
    document.body.style.userSelect = 'none';
  }
  railResizeHandle?.addEventListener('mousedown', e => {
    if (ui.collapsed) return;
    e.preventDefault();
    beginRailDrag(e.clientX);
  });

  // ── Splitter drag ────────────────────────────────────────────────
  let splitterDrag = null;
  function beginSplitterDrag(clientY) {
    if (!railSplitArea) return;
    splitterDrag = { rect: railSplitArea.getBoundingClientRect() };
    rail.classList.add('rail-dragging');
    document.body.style.cursor = 'ns-resize';
    document.body.style.userSelect = 'none';
  }
  railSplitter?.addEventListener('mousedown', e => {
    e.preventDefault();
    beginSplitterDrag(e.clientY);
  });

  function clampRecentHeight(pixels) {
    if (!railSplitArea) return pixels;
    const areaH = railSplitArea.getBoundingClientRect().height;
    return Math.max(MIN_SECTION_H, Math.min(areaH - MIN_SECTION_H - 6, pixels));
  }

  window.addEventListener('mousemove', e => {
    if (railDrag) {
      const next = Math.max(MIN_W, Math.min(MAX_W, railDrag.startW + (e.clientX - railDrag.startX)));
      ui.railW = next;
      applyWidth();
    } else if (splitterDrag) {
      const offsetY = e.clientY - splitterDrag.rect.top;
      ui.recentHeight = clampRecentHeight(offsetY);
      applySectionsState();
    }
  });

  window.addEventListener('mouseup', () => {
    if (railDrag) {
      railDrag = null;
      writePref(PREF_WIDTH, ui.railW);
    }
    if (splitterDrag) splitterDrag = null;
    rail.classList.remove('rail-dragging');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  });

  // ── Section toggles ──────────────────────────────────────────────
  // Rail section headers own their open/closed state via bindDisclosure.
  // `panel: null` + `openClass: null` lets applySectionsState stay the sole
  // writer of the `.closed` class on the section element (it has to
  // coordinate both sections plus the splitter and sizing vars, so letting
  // the helper also toggle classes would produce double-writes). The helper
  // still owns aria-expanded on the header and the post-activation focus
  // contract.
  function onRecentToggle(open) {
    ui.recentOpen = open;
    writePref(PREF_RECENT, open ? '1' : '0');
    applySectionsState();
  }
  function onWorkflowsToggle(open) {
    ui.workflowsOpen = open;
    writePref(PREF_WORKFLOWS, open ? '1' : '0');
    applySectionsState();
  }

  if (railRecentHeader) {
    _shellBindDisclosure(railRecentHeader, {
      panel: null,
      openClass: null,
      initialOpen: ui.recentOpen,
      onToggle: onRecentToggle,
    });
  }
  if (railWorkflowsHeader) {
    _shellBindDisclosure(railWorkflowsHeader, {
      panel: null,
      openClass: null,
      initialOpen: ui.workflowsOpen,
      onToggle: onWorkflowsToggle,
    });
  }

  // ── Recent list rendering ───────────────────────────────────────
  function renderRailRecent() {
    if (!railRecentBody) return;
    const recentPreviewHistory = _shellGetAppState().recentPreviewHistory;
    const items = Array.isArray(recentPreviewHistory) ? recentPreviewHistory : [];
    railRecentBody.replaceChildren();
    if (railRecentCount) railRecentCount.textContent = String(items.length);

    if (!items.length) {
      const empty = document.createElement('div');
      empty.className = 'rail-section-empty';
      empty.textContent = 'no commands yet';
      railRecentBody.appendChild(empty);
      return;
    }
    // Partition starred-first while preserving original recency order within
    // each group. The star toggle lives in the history drawer / mobile sheet
    // (one source of truth); the rail only reflects the state via ordering
    // and an amber left-edge stripe.
    const starred = typeof importedGetStarred === 'function' ? importedGetStarred() : new Set();
    const ordered = [
      ...items.filter(cmd => starred.has(cmd)),
      ...items.filter(cmd => !starred.has(cmd)),
    ];
    ordered.forEach(cmd => {
      const isStarred = starred.has(cmd);
      const row = document.createElement('button');
      row.type = 'button';
      row.className = 'rail-item' + (isStarred ? ' starred' : '');
      row.title = cmd;
      const text = document.createElement('span');
      text.className = 'rail-item-text';
      text.textContent = cmd;
      row.appendChild(text);
      row.addEventListener('click', () => {
        _shellSetComposerValue(cmd, cmd.length, cmd.length);
        _shellRefocusComposer({ preventScroll: true });
        _shellFn('resetCmdHistoryNav')?.();
      });
      railRecentBody.appendChild(row);
    });
  }

  // ── Workflows list rendering ────────────────────────────────────
  function renderRailWorkflows(items) {
    allWorkflows = Array.isArray(items) ? items.slice() : [];
    if (railWorkflowsCount) railWorkflowsCount.textContent = String(allWorkflows.length);
    if (!railWorkflowsBody) return;
    railWorkflowsBody.replaceChildren();
    if (!allWorkflows.length) {
      const empty = document.createElement('div');
      empty.className = 'rail-section-empty';
      empty.textContent = 'no workflows';
      railWorkflowsBody.appendChild(empty);
      return;
    }
    allWorkflows.forEach((wf, idx) => {
      const row = document.createElement('button');
      row.type = 'button';
      row.className = 'rail-item';
      const label = wf.title || wf.name || `workflow ${idx + 1}`;
      row.title = [label, wf.description].filter(Boolean).join('\n');
      const glyph = document.createElement('span');
      glyph.className = 'drill-chev';
      glyph.setAttribute('aria-hidden', 'true');
      glyph.textContent = '›';
      const text = document.createElement('span');
      text.className = 'rail-item-text';
      text.textContent = label;
      row.appendChild(glyph);
      row.appendChild(text);
      row.addEventListener('click', () => openScopedWorkflow(idx));
      railWorkflowsBody.appendChild(row);
    });
  }

  async function openScopedWorkflow(idx) {
    const item = allWorkflows[idx];
    if (!item) return;
    const loadWorkflowsFn = _shellFn('loadWorkflows');
    if (loadWorkflowsFn) {
      try { await loadWorkflowsFn(); } catch (_) { /* non-critical */ }
    }
    const openWorkflowsFn = _shellFn('openWorkflows', importedOpenWorkflows);
    if (openWorkflowsFn) {
      openWorkflowsFn({ items: [item], emitCatalogEvent: false });
    } else {
      _shellFn('showWorkflowsOverlay', importedShowWorkflowsOverlay)?.();
    }
  }

  // ── Nav menu ─────────────────────────────────────────────────────
  // The visible rail is the desktop source of truth. Route clicks directly
  // into the shared action layer.
  function positionRailMoreMenu() {
    if (!railMoreBtn || !railMoreMenu || railMoreMenu.classList.contains('u-hidden')) return;
    if (typeof railMoreBtn.getBoundingClientRect !== 'function') return;
    const triggerRect = railMoreBtn.getBoundingClientRect();
    const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 1024;
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 768;
    const gutter = 8;
    const menuWidth = Math.max(railMoreMenu.offsetWidth || 220, 180);
    const menuHeight = Math.max(railMoreMenu.offsetHeight || railMoreMenu.getBoundingClientRect?.().height || 1, 1);
    const maxMenuHeight = Math.max(120, viewportHeight - (gutter * 2));
    const effectiveMenuHeight = Math.min(menuHeight, maxMenuHeight);
    const desiredArrowFromBottom = 32;
    const triggerCenterY = triggerRect.top + (triggerRect.height / 2);
    const preferredTop = triggerCenterY - Math.max(28, effectiveMenuHeight - desiredArrowFromBottom);
    const top = Math.min(
      Math.max(gutter, preferredTop),
      Math.max(gutter, viewportHeight - effectiveMenuHeight - gutter),
    );
    const left = Math.min(
      Math.max(gutter, triggerRect.right + 8),
      Math.max(gutter, viewportWidth - menuWidth - gutter),
    );
    const arrowLimit = Math.max(18, effectiveMenuHeight - 18);
    const arrowY = Math.min(arrowLimit, Math.max(18, triggerCenterY - top - 4));
    railMoreMenu.style.position = 'fixed';
    railMoreMenu.style.left = `${left}px`;
    railMoreMenu.style.top = `${top}px`;
    railMoreMenu.style.right = 'auto';
    railMoreMenu.style.bottom = 'auto';
    railMoreMenu.style.maxHeight = `${maxMenuHeight}px`;
    railMoreMenu.style.overflowY = menuHeight > maxMenuHeight ? 'auto' : '';
    railMoreMenu.style.setProperty('--rail-more-arrow-y', `${arrowY}px`);
  }

  function closeRailMoreMenu() {
    if (!railMoreBtn || !railMoreMenu) return;
    railMoreBtn.setAttribute('aria-expanded', 'false');
    railMoreMenu.classList.add('u-hidden');
    railMoreMenu.style.position = '';
    railMoreMenu.style.left = '';
    railMoreMenu.style.top = '';
    railMoreMenu.style.right = '';
    railMoreMenu.style.bottom = '';
    railMoreMenu.style.maxHeight = '';
    railMoreMenu.style.overflowY = '';
    railMoreMenu.style.removeProperty('--rail-more-arrow-y');
  }

  function openRailMoreMenu() {
    if (!railMoreBtn || !railMoreMenu) return;
    railMoreBtn.setAttribute('aria-expanded', 'true');
    railMoreMenu.classList.remove('u-hidden');
    positionRailMoreMenu();
    railMoreMenu.querySelector('[data-action]:not(.u-hidden)')?.focus?.();
  }

  function toggleRailMoreMenu() {
    if (railMoreBtn?.getAttribute('aria-expanded') === 'true') {
      closeRailMoreMenu();
    } else {
      openRailMoreMenu();
    }
  }

  railNav?.addEventListener('click', e => {
    const item = e.target.closest?.('[data-action]');
    if (!item) return;
    const action = item.dataset.action;
    if (action === 'diag') {
      closeRailMoreMenu();
      return; // native <a> navigation
    }
    e.preventDefault();
    if (action === 'rail-more') {
      toggleRailMoreMenu();
      return;
    }
    closeRailMoreMenu();
    if (action === 'history' && typeof importedToggleHistoryPanelSurface === 'function') {
      importedToggleHistoryPanelSurface();
      return;
    }
    const openAtlas = _shellFn('openAtlas', importedOpenAtlas);
    const openFindingsBoard = _shellFn('openFindingsBoard', importedOpenFindingsBoard);
    const openStatusMonitor = _shellFn('openStatusMonitor', importedOpenStatusMonitor);
    const openCommandRegistry = _shellFn('openCommandRegistry', importedOpenCommandRegistry);
    const openSchedulesModal = _shellFn('openSchedulesModal', importedOpenSchedulesModal);
    const openWatchersModal = _shellFn('openWatchersModal', importedOpenWatchersModal);
    if (action === 'atlas' && typeof openAtlas === 'function') {
      void openAtlas({ source: 'rail' });
      return;
    }
    if (action === 'findings-board' && typeof openFindingsBoard === 'function') {
      void openFindingsBoard({ source: 'rail' });
      return;
    }
    if (action === 'status-monitor' && typeof openStatusMonitor === 'function') {
      void openStatusMonitor({ source: 'rail' });
      return;
    }
    if (action === 'command-registry' && typeof openCommandRegistry === 'function') {
      openCommandRegistry();
      return;
    }
    if (action === 'schedules' && typeof openSchedulesModal === 'function') {
      void openSchedulesModal();
      return;
    }
    if (action === 'watchers' && typeof openWatchersModal === 'function') {
      void openWatchersModal();
      return;
    }
    if (action === 'projects') {
      void openProjectWorkspace();
      return;
    }
    if (action === 'options' && typeof importedOpenOptions === 'function') {
      importedOpenOptions();
      return;
    }
    if (action === 'theme' && typeof importedOpenThemeSelector === 'function') {
      importedOpenThemeSelector();
      return;
    }
    if (action === 'workspace' && typeof importedOpenWorkspace === 'function') {
      importedOpenWorkspace();
      return;
    }
    if (action === 'faq' && typeof importedOpenFaq === 'function') {
      importedOpenFaq();
    }
  });

  document.addEventListener('click', event => {
    if (!railMoreMenu || railMoreMenu.classList.contains('u-hidden')) return;
    const target = event.target;
    if (target instanceof Node && railNav?.contains(target)) return;
    closeRailMoreMenu();
  });

  railNav?.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      closeRailMoreMenu();
      railMoreBtn?.focus?.();
    }
  });

  window.addEventListener('resize', positionRailMoreMenu);

  let hudProjectMenu = null;
  let hudProjectMenuSearchInput = null;
  let hudProjectMenuProjects = null;
  let hudProjectMenuNote = null;
  let hudProjectMenuSearchTimer = null;
  let hudProjectMenuRequestId = 0;

  function _isHudProjectMenuOpen() {
    return !!(hudProjectMenu && !hudProjectMenu.classList.contains('u-hidden'));
  }

  function _openProjectsFromHudMenu(event) {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    closeHudProjectMenu();
    void openProjectWorkspace();
  }

  function _canCreateProjectFromHud() {
    return _shellActiveTeamScopeCan('mutate_projects');
  }

  function _projectCreateDeniedTitle() {
    return _shellTeamScopeDeniedMessage('create team projects');
  }

  function _showHudProjectToast(message, tone = 'info') {
      _shellShowToast(message, tone);
  }

  async function _hudProjectResponseMessage(resp, fallback) {
    try {
      const data = await resp.json();
      return data?.error || data?.message || fallback;
    } catch (_) {
      return fallback;
    }
  }

  function _createHudProjectMenuButton({ label, action, title = '', disabled = false, selected = false, onActivate }) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'dropdown-item dropdown-item-compact';
    btn.dataset.action = action || '';
    btn.setAttribute('role', selected ? 'menuitemradio' : 'menuitem');
    if (selected) btn.setAttribute('aria-checked', 'true');
    btn.textContent = label;
    if (title) btn.title = title;
    if (disabled) {
      btn.disabled = true;
      btn.setAttribute('aria-disabled', 'true');
    }
    const pressable = _shellFn('bindPressable', importedBindPressable);
    if (pressable) {
      pressable(btn, {
        refocusComposer: false,
        onActivate,
      });
    } else if (typeof onActivate === 'function') {
      btn.addEventListener('click', onActivate);
    }
    return btn;
  }

  function _positionHudProjectMenu() {
    if (!hudProjectMenu || !hudProjectCell || !_isHudProjectMenuOpen()) return;
    const rect = hudProjectCell.getBoundingClientRect();
    const menuWidth = hudProjectMenu.offsetWidth || 260;
    const viewportWidth = global.innerWidth || document.documentElement.clientWidth || 0;
    const left = Math.max(8, Math.min(rect.left, Math.max(8, viewportWidth - menuWidth - 8)));
    hudProjectMenu.style.left = `${left}px`;
    hudProjectMenu.style.bottom = `${Math.max(8, (global.innerHeight || 0) - rect.top - 1)}px`;
  }

  function closeHudProjectMenu({ restoreFocus = false } = {}) {
    if (!hudProjectMenu) return;
    if (hudProjectMenuSearchTimer) {
      global.clearTimeout?.(hudProjectMenuSearchTimer);
      hudProjectMenuSearchTimer = null;
    }
    hudProjectMenuRequestId += 1;
    hudProjectMenu.classList.add('u-hidden');
    hudProjectCell?.classList.remove('open');
    hudProjectCell?.setAttribute('aria-expanded', 'false');
    if (restoreFocus && hudProjectCell && typeof hudProjectCell.focus === 'function') {
      hudProjectCell.focus({ preventScroll: true });
    }
  }

  function _focusHudProjectMenuItem(delta) {
    if (!hudProjectMenu) return;
    const items = Array.from(hudProjectMenu.querySelectorAll('.dropdown-item:not([disabled])'));
    if (!items.length) return;
    const currentIdx = items.indexOf(document.activeElement);
    const fallbackIdx = delta > 0 ? -1 : 0;
    const nextIdx = (currentIdx >= 0 ? currentIdx : fallbackIdx) + delta;
    items[(nextIdx + items.length) % items.length]?.focus({ preventScroll: true });
  }

  function _setHudProjectMenuNote(text) {
    if (!hudProjectMenuNote) return;
    hudProjectMenuNote.textContent = text || '';
    hudProjectMenuNote.classList.toggle('u-hidden', !text);
  }

  function _scheduleHudProjectMenuLoad(query) {
    if (hudProjectMenuSearchTimer) {
      global.clearTimeout?.(hudProjectMenuSearchTimer);
      hudProjectMenuSearchTimer = null;
    }
    hudProjectMenuSearchTimer = global.setTimeout?.(() => {
      hudProjectMenuSearchTimer = null;
      void _loadHudProjectMenu(query);
    }, 120) || null;
  }

  async function _selectHudProject(project, event) {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    if (!project || !project.id) return;
    try {
      const resp = await _shellApiFetch('/projects/active', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: project.id }),
      });
      if (!resp.ok) throw new Error(await _hudProjectResponseMessage(resp, 'Unable to set active project.'));
      const data = await resp.json();
      _setActiveProject(data?.project || project);
      closeHudProjectMenu();
      _showHudProjectToast('Active project updated.');
    } catch (err) {
      const message = err?.message || 'Unable to set active project.';
      _setHudProjectMenuNote(message);
      _shellLogClientError('failed to set active project from HUD switcher', err);
      _showHudProjectToast(message, 'error');
    }
  }

  async function _clearHudProject(event) {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    try {
      const resp = await _shellApiFetch('/projects/active', { method: 'DELETE' });
      if (!resp.ok) throw new Error(await _hudProjectResponseMessage(resp, 'Unable to clear active project.'));
      _setActiveProject(null);
      closeHudProjectMenu();
      _showHudProjectToast('Active project cleared.');
    } catch (err) {
      const message = err?.message || 'Unable to clear active project.';
      _setHudProjectMenuNote(message);
      _shellLogClientError('failed to clear active project from HUD switcher', err);
      _showHudProjectToast(message, 'error');
    }
  }

  function _openCreateProjectFromHudMenu(event) {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    if (!_canCreateProjectFromHud()) {
      const message = _projectCreateDeniedTitle();
      _setHudProjectMenuNote(message);
      _showHudProjectToast(message, 'error');
      return;
    }
    closeHudProjectMenu();
    void openProjectWorkspace();
  }

  function _renderHudProjectMenuProjects(projects, query = '') {
    if (!hudProjectMenuProjects) return;
    hudProjectMenuProjects.textContent = '';
    const activeProject = _activeProject();
    const activeProjectId = activeProject?.id ? String(activeProject.id) : '';
    const rows = Array.isArray(projects) ? projects : [];

    if (activeProjectId) {
      hudProjectMenuProjects.appendChild(_createHudProjectMenuButton({
        label: 'No project',
        action: 'clear-active-project',
        title: 'Clear active project',
        onActivate: _clearHudProject,
      }));
    }

    rows.forEach((project) => {
      if (!project || !project.id) return;
      const name = _projectDisplayName(project) || String(project.id);
      const selected = String(project.id) === activeProjectId;
      hudProjectMenuProjects.appendChild(_createHudProjectMenuButton({
        label: selected ? `${name} (active)` : name,
        action: 'select-project',
        title: selected ? `Active project: ${name}` : `Set active project: ${name}`,
        selected,
        onActivate: event => _selectHudProject(project, event),
      }));
    });

    if (!hudProjectMenuProjects.children.length) {
      _setHudProjectMenuNote(query ? 'No matching projects.' : 'No projects yet.');
    } else {
      _setHudProjectMenuNote('');
    }
    _positionHudProjectMenu();
  }

  async function _loadHudProjectMenu(query = '') {
    if (!hudProjectMenuProjects) return;
    const requestId = ++hudProjectMenuRequestId;
    const trimmedQuery = String(query || '').trim();
    const params = new URLSearchParams({ mode: 'switcher', limit: '8' });
    if (trimmedQuery) params.set('q', trimmedQuery);
    if (!hudProjectMenuProjects.children.length) {
      _setHudProjectMenuNote('Loading projects...');
    }
    try {
      const resp = await _shellApiFetch(`/projects?${params.toString()}`, { cache: 'no-store' });
      if (requestId !== hudProjectMenuRequestId) return;
      if (!resp.ok) throw new Error(await _hudProjectResponseMessage(resp, 'Unable to load projects.'));
      const data = await resp.json();
      if (requestId !== hudProjectMenuRequestId) return;
      _renderHudProjectMenuProjects(data?.projects || [], trimmedQuery);
    } catch (err) {
      if (requestId !== hudProjectMenuRequestId) return;
      const message = err?.message || 'Unable to load projects.';
      hudProjectMenuProjects.textContent = '';
      _setHudProjectMenuNote(message);
      _shellLogClientError('failed to load HUD project switcher', err);
    }
  }

  function _refreshHudProjectCreateAction() {
    const createBtn = hudProjectMenu?.querySelector('[data-action="create-project"]');
    if (!createBtn) return;
    const allowed = _canCreateProjectFromHud();
    createBtn.disabled = !allowed;
    createBtn.setAttribute('aria-disabled', allowed ? 'false' : 'true');
    createBtn.title = allowed ? 'Open Projects to create a project' : _projectCreateDeniedTitle();
  }

  function _ensureHudProjectMenu() {
    if (hudProjectMenu) return hudProjectMenu;
    const menu = document.createElement('div');
    menu.id = 'hud-project-menu';
    menu.className = 'hud-project-menu dropdown-surface dropdown-up u-hidden';
    menu.setAttribute('role', 'menu');
    menu.setAttribute('aria-label', 'Active project switcher');

    const search = document.createElement('input');
    search.type = 'search';
    search.className = 'hud-project-search';
    search.placeholder = 'search projects';
    search.setAttribute('aria-label', 'Search projects');
    search.autocomplete = 'off';
    search.spellcheck = false;
    search.addEventListener('click', event => event.stopPropagation());
    search.addEventListener('input', event => {
      event.stopPropagation();
      _scheduleHudProjectMenuLoad(search.value);
    });
    search.addEventListener('keydown', event => {
      event.stopPropagation();
      if (event.key === 'Escape') {
        event.preventDefault();
        closeHudProjectMenu({ restoreFocus: true });
      } else if (event.key === 'ArrowDown') {
        event.preventDefault();
        _focusHudProjectMenuItem(1);
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        _focusHudProjectMenuItem(-1);
      } else if (event.key === 'Tab') {
        closeHudProjectMenu();
      }
    });
    menu.appendChild(search);

    const projectsSection = document.createElement('div');
    projectsSection.className = 'hud-project-menu-section';
    menu.appendChild(projectsSection);

    const note = document.createElement('div');
    note.className = 'hud-project-menu-note u-hidden';
    menu.appendChild(note);

    const divider = document.createElement('div');
    divider.className = 'hud-project-menu-divider';
    menu.appendChild(divider);

    const createProject = _createHudProjectMenuButton({
      label: 'Create project',
      action: 'create-project',
      title: 'Open Projects to create a project',
      disabled: !_canCreateProjectFromHud(),
      onActivate: _openCreateProjectFromHudMenu,
    });
    menu.appendChild(createProject);

    const openProjects = _createHudProjectMenuButton({
      label: 'Open Projects',
      action: 'open-projects',
      onActivate: _openProjectsFromHudMenu,
    });
    menu.appendChild(openProjects);

    menu.addEventListener('click', event => event.stopPropagation());
    menu.addEventListener('keydown', event => {
      event.stopPropagation();
      if (event.key === 'Escape') {
        event.preventDefault();
        closeHudProjectMenu({ restoreFocus: true });
      } else if (event.key === 'ArrowDown') {
        event.preventDefault();
        _focusHudProjectMenuItem(1);
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        _focusHudProjectMenuItem(-1);
      } else if (event.key === 'Tab') {
        closeHudProjectMenu();
      }
    });

    document.body.appendChild(menu);
    hudProjectMenu = menu;
    hudProjectMenuSearchInput = search;
    hudProjectMenuProjects = projectsSection;
    hudProjectMenuNote = note;

    const bindOutsideClickClose = _shellFn('bindOutsideClickClose', importedBindOutsideClickClose);
    if (bindOutsideClickClose) {
      bindOutsideClickClose(menu, {
        capture: true,
        triggers: hudProjectCell,
        isOpen: _isHudProjectMenuOpen,
        onClose: () => closeHudProjectMenu(),
      });
    }
    return hudProjectMenu;
  }

  function toggleHudProjectMenu(event) {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    _closeHudSaveMenu();
    _ensureHudProjectMenu();
    if (_isHudProjectMenuOpen()) {
      closeHudProjectMenu({ restoreFocus: true });
      return;
    }
    hudProjectMenu.classList.remove('u-hidden');
    hudProjectCell?.classList.add('open');
    hudProjectCell?.setAttribute('aria-expanded', 'true');
    _refreshHudProjectCreateAction();
    if (hudProjectMenuSearchInput) hudProjectMenuSearchInput.value = '';
    _renderHudProjectMenuProjects([], '');
    void _loadHudProjectMenu('');
    _positionHudProjectMenu();
    requestAnimationFrame(_positionHudProjectMenu);
    hudProjectMenuSearchInput?.focus({ preventScroll: true });
  }

  if (hudProjectCell && _shellFn('bindPressable', importedBindPressable)) {
    _shellBindPressable(hudProjectCell, {
      refocusComposer: false,
      onActivate: toggleHudProjectMenu,
    });
  } else {
    hudProjectCell?.addEventListener('click', toggleHudProjectMenu);
    hudProjectCell?.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') toggleHudProjectMenu(event);
    });
  }
  global.addEventListener?.('resize', _positionHudProjectMenu);
  global.addEventListener?.('scroll', _positionHudProjectMenu, true);
  document.addEventListener?.('app:active-project-changed', () => {
    if (!_isHudProjectMenuOpen()) return;
    _refreshHudProjectCreateAction();
    void _loadHudProjectMenu(hudProjectMenuSearchInput?.value || '');
  });
  document.addEventListener?.('app:scope-changed', () => {
    closeHudProjectMenu();
    loadActiveProjectContext().catch(() => {});
  });
  document.addEventListener?.('app:scope-capabilities-changed', () => {
    _refreshHudProjectCreateAction();
  });

  // ── HUD action buttons ──────────────────────────────────────────
  // Desktop-only mirror of the per-tab `.terminal-actions` footer. Each
  // button resolves the active tab at click time so no per-tab wiring is
  // needed; the per-tab footer still exists in the DOM for mobile.
  const hudActions = document.getElementById('hud-actions');
  let hudKillBtn = null;
  let hudShareSnapshotBtn = null;

  function _currentTabId() {
    return _shellGetActiveTabId();
  }

  function _closeHudSaveMenu() {
    document.querySelectorAll('.hud-save-wrap.open').forEach(w => w.classList.remove('open'));
  }

  function _makeHudBtn(label, action, onClick, cls = 'btn btn-secondary btn-compact', title = '') {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = cls;
    btn.textContent = label;
    if (action) btn.dataset.action = action;
    if (title) btn.title = title;
    // save-menu is a disclosure trigger: suppress auto-refocus so the dropdown
    // retains user attention. Every other HUD button returns focus to the
    // composer after activation.
    const isDisclosure = action === 'save-menu';
    _shellBindPressable(btn, {
      refocusComposer: !isDisclosure,
      onActivate: e => {
        e.preventDefault();
        onClick(e, btn);
      },
    });
    return btn;
  }

  function _bindProjectRuntimePressable(el, options = {}) {
    if (el && _shellFn('bindPressable', importedBindPressable)) {
      _shellBindPressable(el, { onActivate: () => {}, refocusComposer: false, ...options });
    }
    return el;
  }

  function _canCreateHudShareSnapshot() {
    return _shellActiveTeamScopeCan('manage_history');
  }

  function _hudShareSnapshotDeniedTitle() {
    return _shellTeamScopeDeniedMessage('create team history snapshots');
  }

  function _refreshHudShareSnapshotState() {
    if (!hudShareSnapshotBtn) return;
    const allowed = _canCreateHudShareSnapshot();
    hudShareSnapshotBtn.disabled = !allowed;
    hudShareSnapshotBtn.title = allowed
      ? 'Share tab as permalink (Option+P / Alt+P)'
      : _hudShareSnapshotDeniedTitle();
  }

  function buildHudActions() {
    if (!hudActions) return;
    hudActions.replaceChildren();
    const copyCurrentTab = typeof importedCopyTab === 'function'
      ? importedCopyTab
      : _shellFn('copyTab');
    const permalinkCurrentTab = typeof importedPermalinkTab === 'function'
      ? importedPermalinkTab
      : _shellFn('permalinkTab');
    const saveCurrentTab = typeof importedSaveTab === 'function'
      ? importedSaveTab
      : _shellFn('saveTab');
    const exportCurrentTabHtml = typeof importedExportTabHtml === 'function'
      ? importedExportTabHtml
      : _shellFn('exportTabHtml');
    const exportCurrentTabPdf = typeof importedExportTabPdf === 'function'
      ? importedExportTabPdf
      : _shellFn('exportTabPdf');

    hudKillBtn = _makeHudBtn('\u25A0 Kill', 'kill', () => {
      const id = _currentTabId();
      const confirmKill = (typeof importedConfirmKill === 'function' && importedConfirmKill)
        || _shellFn('confirmKill');
      if (id) confirmKill?.(id);
    }, 'btn btn-destructive btn-compact u-hidden', 'Kill current run');
    hudActions.appendChild(hudKillBtn);

    hudShareSnapshotBtn = _makeHudBtn('share snapshot', 'permalink', () => {
      const id = _currentTabId();
      if (id && permalinkCurrentTab) permalinkCurrentTab(id);
    }, 'btn btn-secondary btn-compact', 'Share tab as permalink (Option+P / Alt+P)');
    hudActions.appendChild(hudShareSnapshotBtn);
    _refreshHudShareSnapshotState();

    hudActions.appendChild(_makeHudBtn('copy', 'copy', () => {
      const id = _currentTabId();
      if (id && copyCurrentTab) copyCurrentTab(id);
    }, 'btn btn-secondary btn-compact', 'Copy tab output (Option+Shift+C)'));

    // Save menu — shares .save-menu markup so existing CSS applies.
    const saveWrap = document.createElement('div');
    saveWrap.className = 'hud-save-wrap';
    const saveBtn = _makeHudBtn('save', 'save-menu', () => {
      closeHudProjectMenu();
      saveWrap.classList.toggle('open');
    }, 'btn btn-secondary btn-compact', 'Save tab output (txt / html / pdf)');
    const saveMenu = document.createElement('div');
    saveMenu.className = 'save-menu dropdown-surface dropdown-up';
    [
      ['Plain text (.txt)',   'save-txt',  () => { const id = _currentTabId(); if (id && saveCurrentTab) saveCurrentTab(id); }],
      ['Styled HTML (.html)', 'save-html', () => { const id = _currentTabId(); if (id && exportCurrentTabHtml) exportCurrentTabHtml(id); }],
      ['PDF document (.pdf)', 'save-pdf',  () => { const id = _currentTabId(); if (id && exportCurrentTabPdf) exportCurrentTabPdf(id); }],
    ].forEach(([label, action, fn]) => {
      const item = document.createElement('button');
      item.type = 'button';
      item.className = 'dropdown-item dropdown-item-compact';
      item.textContent = label;
      item.dataset.action = action;
      _shellBindPressable(item, {
        onActivate: e => {
          e.preventDefault();
          e.stopPropagation();
          saveWrap.classList.remove('open');
          fn();
        },
      });
      saveMenu.appendChild(item);
    });
    saveWrap.appendChild(saveBtn);
    saveWrap.appendChild(saveMenu);
    hudActions.appendChild(saveWrap);

    hudActions.appendChild(_makeHudBtn('clear', 'clear', () => {
      const id = _currentTabId();
      if (!id) return;
      const cancelWelcomeFn = _shellFn('cancelWelcome');
      if (typeof cancelWelcomeFn === 'function') cancelWelcomeFn(id);
      _shellFn('clearTab')?.(id, { preserveRunState: true });
    }, 'btn btn-secondary btn-compact', 'Clear active tab (Ctrl+L)'));

    _shellBindOutsideClickClose(saveWrap, {
      triggers: saveBtn,
      isOpen: () => saveWrap.classList.contains('open'),
      onClose: () => _closeHudSaveMenu(),
    });
  }

  function _setHudKillVisible(show) {
    if (!hudKillBtn) return;
    hudKillBtn.classList.toggle('u-hidden', !show);
  }

  function refreshHudActions(tabId) {
    const id = tabId || _currentTabId();
    const tab = _shellGetTab(id);
    _setHudKillVisible(!!(tab && tab.st === 'running'));
    _refreshHudShareSnapshotState();
  }

  buildHudActions();
  document.addEventListener('app:scope-changed', () => {
    _refreshHudShareSnapshotState();
  });
  document.addEventListener('app:scope-capabilities-changed', () => {
    _refreshHudShareSnapshotState();
  });

  // ── HUD metrics ─────────────────────────────────────────────────
  // Live-updating pills on the left side of the HUD. State is owned here;
  // setters are exposed on `global` so runner.js and session.js can push in.
  const STATUS_POLL_VISIBLE_MS = 3000;
  const STATUS_POLL_HIDDEN_MS  = 15000;
  const CLOCK_TICK_MS          = 1000;
  const LAT_WARN_MS            = 250;
  const LAT_BAD_MS             = 500;

  const hudState = {
    lastExit: null,     // number | 'killed' | null
    latencyMs: null,    // number | null
    serverUptime: null, // seconds as reported by /status
    serverUptimeAt: 0,  // performance.now() when serverUptime was recorded
    db: null,           // 'ok' | 'down' | null
    redis: null,        // 'ok' | 'down' | 'none' | null
  };
  let hudStatusPollTimer = null;

  function _setValueColor(el, variant) {
    if (!el) return;
    el.classList.remove('hud-value-green', 'hud-value-amber', 'hud-value-red', 'hud-muted');
    if (variant) el.classList.add(variant);
  }

  function _formatUptime(totalSeconds) {
    if (!Number.isFinite(totalSeconds) || totalSeconds < 0) return '—';
    const s = Math.floor(totalSeconds);
    if (s < 60) return `${s}s`;
    if (s < 3600) {
      const m = Math.floor(s / 60);
      const r = s % 60;
      return r ? `${m}m ${r}s` : `${m}m`;
    }
    if (s < 86400) {
      const h = Math.floor(s / 3600);
      const m = Math.floor((s % 3600) / 60);
      return m ? `${h}h ${m}m` : `${h}h`;
    }
    const d = Math.floor(s / 86400);
    const h = Math.floor((s % 86400) / 3600);
    return h ? `${d}d ${h}h` : `${d}d`;
  }

  function _formatUtcClock(ms) {
    const d = new Date(Number.isFinite(ms) ? ms : Date.now());
    const pad = n => String(n).padStart(2, '0');
    return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())} UTC`;
  }

  function _formatOffsetLabel(minutesEastOfUtc) {
    const totalMinutes = Number.isFinite(minutesEastOfUtc) ? minutesEastOfUtc : 0;
    if (totalMinutes === 0) return 'UTC';
    const sign = totalMinutes >= 0 ? '+' : '-';
    const absMinutes = Math.abs(totalMinutes);
    const hours = String(Math.floor(absMinutes / 60)).padStart(2, '0');
    const minutes = String(absMinutes % 60).padStart(2, '0');
    return `GMT${sign}${hours}:${minutes}`;
  }

  function _getLocalClockLabel(d) {
    try {
      const tzName = new Intl.DateTimeFormat([], { timeZoneName: 'short' })
        .formatToParts(d)
        .find(part => part.type === 'timeZoneName')
        ?.value
        ?.trim();
      if (tzName && !/^GMT(?:[+-]\d{1,2}(?::\d{2})?)?$/i.test(tzName) && !/^UTC(?:[+-]\d{1,2}(?::\d{2})?)?$/i.test(tzName)) {
        return tzName;
      }
    } catch (_) {
      // Fall through to the numeric offset label below.
    }
    return _formatOffsetLabel(-d.getTimezoneOffset());
  }

  function _formatLocalClock(ms) {
    const d = new Date(Number.isFinite(ms) ? ms : Date.now());
    const pad = n => String(n).padStart(2, '0');
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())} ${_getLocalClockLabel(d)}`;
  }

  function _renderLastExit() {
    if (!hudLastExitEl) return;
    const v = hudState.lastExit;
    const list = _shellTabs();
    const activeTabId = _shellGetActiveTabId();
    const activeRunning = list.some(t => t && t.id === activeTabId && t.st === 'running');
    if (v === null || v === undefined) {
      hudLastExitEl.textContent = '—';
      _setValueColor(hudLastExitEl, 'hud-muted');
    } else if (v === 'killed') {
      hudLastExitEl.textContent = 'KILLED';
      _setValueColor(hudLastExitEl, activeRunning ? 'hud-muted' : 'hud-value-red');
    } else if (v === 0) {
      hudLastExitEl.textContent = '0';
      _setValueColor(hudLastExitEl, activeRunning ? 'hud-muted' : 'hud-value-green');
    } else {
      hudLastExitEl.textContent = String(v);
      _setValueColor(hudLastExitEl, activeRunning ? 'hud-muted' : 'hud-value-red');
    }
  }

  function _renderLatency() {
    if (!hudLatencyEl) return;
    const ms = hudState.latencyMs;
    if (ms === null || ms === undefined) {
      hudLatencyEl.textContent = '— ms';
      _setValueColor(hudLatencyEl, 'hud-muted');
      return;
    }
    hudLatencyEl.textContent = `${Math.round(ms)} ms`;
    if (ms >= LAT_BAD_MS) _setValueColor(hudLatencyEl, 'hud-value-red');
    else if (ms >= LAT_WARN_MS) _setValueColor(hudLatencyEl, 'hud-value-amber');
    else _setValueColor(hudLatencyEl, 'hud-value-green');
  }

  function _renderTabs() {
    if (!hudTabsEl) return;
    const list = _shellTabs();
    const running = list.reduce((n, t) => n + (t && t.st === 'running' ? 1 : 0), 0);
    const total = list.length;
    if (!total) hudTabsEl.textContent = '0';
    else if (running > 0) hudTabsEl.textContent = `${total} · ${running} active`;
    else hudTabsEl.textContent = String(total);
    _setValueColor(hudTabsEl, running > 0 ? 'hud-value-amber' : 'hud-muted');
  }

  function _renderSession() {
    if (!hudSessionEl) return;
    // Read directly from window storage: SESSION_ID in session.js is declared
    // with `let` so it is not attached to window; localStorage is the
    // underlying source of truth and updates synchronously across all paths
    // that change the active session token.
    let token = '';
    try { token = global.localStorage?.getItem('session_token') || ''; } catch (_) {}
    if (token && token.startsWith('tok_')) {
      const masked = _shellMaskSessionToken(token);
      hudSessionEl.textContent = masked;
      hudSessionEl.title = `Active session token (${masked})`;
      _setValueColor(hudSessionEl, 'hud-value-green');
    } else {
      hudSessionEl.textContent = 'ANON';
      hudSessionEl.title = 'Anonymous UUID session — generate a token in Options to carry history across devices';
      _setValueColor(hudSessionEl, 'hud-muted');
    }
  }

  let projectSharedUiController = null;

  function _projectSharedUiController() {
    if (projectSharedUiController) return projectSharedUiController;
    const factory = importedProjectSharedUi && importedProjectSharedUi.createProjectSharedUiController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectSharedUi is unavailable');
    projectSharedUiController = factory({
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      downloadBlobAsAttachment: _shellDownloadBlobAsAttachment,
      downloadUrlAsAttachment: _shellDownloadUrlAsAttachment,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
    });
    return projectSharedUiController;
  }

  function _projectDisplayName(project) {
    return _projectSharedUiController().displayName(project);
  }

  let projectActiveContextController = null;

  function _projectActiveContextController() {
    if (projectActiveContextController) return projectActiveContextController;
    const factory = importedProjectActiveContext
      && importedProjectActiveContext.createProjectActiveContextController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectActiveContext is unavailable');
    projectActiveContextController = factory({
      apiFetch: _shellApiFetch,
      emitUiEvent: (eventName, detail) => {
        _shellEmitUiEvent(eventName, detail);
      },
      hudProjectCell,
      hudProjectEl,
      isProjectWorkspaceOpen,
      logClientError: (message, err, details) => {
        _shellLogClientError(message, err, details);
      },
      projectDisplayName: _projectDisplayName,
      railNav,
      refreshProjectWorkspace,
      setValueColor: _setValueColor,
      showToast: _shellFn('showToast', importedShowToast),
      syncProjectNotesForm: _syncProjectNotesForm,
    });
    return projectActiveContextController;
  }

  function _activeProject() {
    return _projectActiveContextController().project();
  }

  function _setActiveProject(project) {
    return _projectActiveContextController().setProject(project);
  }

  function _renderActiveProject() {
    _projectActiveContextController().render();
  }

  async function loadActiveProjectContext() {
    return _projectActiveContextController().load();
  }

  let projectWorkspaceShellController = null;

  function _projectWorkspaceShellController() {
    if (projectWorkspaceShellController) return projectWorkspaceShellController;
    const projectWorkspaceShell = _projectModule('DarklabProjectWorkspaceShell', importedProjectWorkspaceShell);
    const factory = projectWorkspaceShell && projectWorkspaceShell.createProjectWorkspaceShellController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectWorkspaceShell is unavailable');
    projectWorkspaceShellController = factory({
      EntityMetadataClient,
      blurVisibleComposerInputIfMobile: () => {
        _shellFn('blurVisibleComposerInputIfMobile', importedBlurVisibleComposerInputIfMobile)?.();
      },
      closeMajorOverlays: () => {
        if (typeof importedCloseMajorOverlays === 'function') importedCloseMajorOverlays();
      },
      closeProjectEntityEditor: _closeProjectEntityEditor,
      closeProjectMobileActionSheet: _closeProjectMobileActionSheet,
      closeProjectMobileCompareSheet: _closeProjectMobileCompareSheet,
      closeProjectPackageManifest: _closeProjectPackageManifest,
      closeProjectPackageWizard: _closeProjectPackageWizard,
      closeProjectTargetEditor: _closeProjectTargetEditor,
      emitUiEvent: (eventName, detail) => {
        _shellEmitUiEvent(eventName, detail);
      },
      flushProjectNotesAutosave: _flushProjectNotesAutosave,
      markInteractionSurfaceReady: (surfaceName, overlay, modal) => {
        _shellFn('markInteractionSurfaceReady', importedMarkInteractionSurfaceReady)?.(surfaceName, overlay, modal);
      },
      projectEntitiesController: _projectEntitiesController,
      projectWorkspaceBody,
      projectWorkspaceBroadcastKey: PROJECT_WORKSPACE_CONSTANTS.workspaceBroadcastKey,
      projectMobileCreateForm,
      projectMobileNameInput,
      projectWorkspaceCreateForm,
      projectWorkspaceMessage,
      projectWorkspaceModal,
      projectWorkspaceNameInput,
      projectWorkspaceOverlay,
      refocusComposerAfterAction: (options) => {
        _shellRefocusComposer(options);
      },
      refreshProjectWorkspace,
      selectedProjectId: () => projectWorkspaceState.selectedId(),
      setProjectMobileCreateOpen: _setProjectMobileCreateOpen,
      setProjectPaginationOffset: _setProjectPaginationOffset,
      setProjectWorkspaceTab: projectWorkspaceState.setTab,
      setSelectedProjectId: projectWorkspaceState.setSelectedId,
      showToast: _shellFn('showToast', importedShowToast),
    });
    return projectWorkspaceShellController;
  }

  let projectWorkspaceActionsController = null;

  function _projectWorkspaceActionsController() {
    if (projectWorkspaceActionsController) return projectWorkspaceActionsController;
    const projectWorkspaceActions = _projectModule('DarklabProjectWorkspaceActions', importedProjectWorkspaceActions);
    const factory = projectWorkspaceActions && projectWorkspaceActions.createProjectWorkspaceActionsController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectWorkspaceActions is unavailable');
    projectWorkspaceActionsController = factory({
      EntityMetadataClient,
      apiFetch: _shellApiFetch,
      projectRunItems: _projectRunItems,
      projectWorkspaceRequest: _projectWorkspaceRequest,
      refreshProjectWorkspace,
      selectedProjectId: () => projectWorkspaceState.selectedId(),
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      showConfirm: _shellFn('showConfirm', importedShowConfirm),
    });
    return projectWorkspaceActionsController;
  }

  function isProjectWorkspaceOpen() {
    if (!_projectWorkspaceModulesReady()) return _projectWorkspaceOverlayOpenFallback();
    return _projectWorkspaceShellController().isOpen();
  }

  function _setProjectWorkspaceMessage(text = '', { error = false, toast = true } = {}) {
    if (!_projectWorkspaceModulesReady()) {
      if (toast && text) _shellShowToast(text, error ? 'error' : 'info');
      return;
    }
    _projectWorkspaceShellController().setMessage(text, { error, toast });
  }

  async function _projectResponseError(resp, fallback) {
    return _projectWorkspaceShellController().responseError(resp, fallback);
  }

  function _selectedProject() {
    return _projectWorkspaceLifecycleController().selectedProject();
  }

  function _projectSummary(projectId = projectWorkspaceState.selectedId()) {
    return _projectWorkspaceLifecycleController().projectSummary(projectId);
  }

  function _ensureSelectedProject() {
    _projectWorkspaceLifecycleController().ensureSelectedProject();
  }

  function _projectCounts(summary) {
    return _projectSharedUiController().counts(summary);
  }

  function _projectCountEntries(summary) {
    return _projectSharedUiController().countEntries(summary);
  }

  function _projectTargetItems(summary) {
    return _projectSharedUiController().targetItems(summary);
  }

  let projectEntitiesController = null;

  function _projectEntitiesController() {
    if (projectEntitiesController) return projectEntitiesController;
    const projectEntities = _projectModule('DarklabProjectEntities', importedProjectEntities);
    const factory = projectEntities && projectEntities.createProjectEntitiesController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectEntities is unavailable');
    projectEntitiesController = factory({
      apiFetch: _shellApiFetch,
      getSummary: projectId => projectWorkspaceState.summary(projectId),
      getActiveTab: projectWorkspaceState.entityTab,
      setActiveTab: projectWorkspaceState.setEntityTab,
      getSelectMode: projectWorkspaceState.entitySelectMode,
      setSelectMode: projectWorkspaceState.setEntitySelectMode,
      getSelectedIds: projectWorkspaceState.selectedEntityIds,
      getPicker: projectWorkspaceState.entityPicker,
      setPicker: projectWorkspaceState.setEntityPicker,
      getSelectedProjectId: projectWorkspaceState.selectedId,
      projectRows: projectWorkspaceState.rows,
      projectIsArchived: _projectIsArchived,
      formatDate: _formatProjectDate,
      shortProjectRunId: _shortProjectRunId,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      projectMobileEmptyPanel: _projectMobileEmptyPanel,
      projectItemRow: _projectItemRow,
      projectMobileContentRow: _projectMobileContentRow,
      projectMobileActionMenu: _projectMobileActionMenu,
      entityMetadataChips: _entityMetadataChips,
      projectTargetItems: _projectTargetItems,
      projectTargetFilterSet: _projectTargetFilterSet,
      projectRunFilterSet: _projectRunFilterSet,
      projectResponseError: _projectResponseError,
      projectWorkspaceRequest: _projectWorkspaceRequest,
      refreshProjectWorkspace,
      renderProjectExplorer: _renderProjectExplorer,
      renderProjectMobileDetail: _renderProjectMobileDetail,
      mobileView: () => _projectMobileShellController().currentView(),
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      showConfirm: _shellFn('showConfirm', importedShowConfirm),
      logClientError: (message, err) => {
        _shellLogClientError(message, err);
      },
      downloadBlobAsAttachment: _downloadBlobAsAttachment,
      downloadUrlAsAttachment: _downloadUrlAsAttachment,
      closeProjectWorkspace,
      openAtlas: _shellFn('openAtlas', importedOpenAtlas),
      projectDisplayName: _projectDisplayName,
      setWorkspaceTab: projectWorkspaceState.setTab,
    });
    return projectEntitiesController;
  }

  let projectPackagesController = null;
  let projectPackagesControllerPromise = null;

  function _projectPackagesController() {
    if (projectPackagesController) return projectPackagesController;
    const projectPackages = _projectModule('DarklabProjectPackages', importedProjectPackages);
    const factory = projectPackages && projectPackages.createProjectPackagesController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectPackages is unavailable');
    projectPackagesController = factory({
      apiFetch: _shellApiFetch,
      EntityMetadataClient,
      manifestOverlay: projectPackageManifestOverlay,
      manifestTitle: projectPackageManifestTitle,
      manifestSummary: projectPackageManifestSummary,
      manifestJson: projectPackageManifestJson,
      wizardOverlay: projectPackageWizardOverlay,
      wizardBody: projectPackageWizardBody,
      getSelectedProjectId: projectWorkspaceState.selectedId,
      selectedProject: _selectedProject,
      projectSummary: _projectSummary,
      projectRunItems: _projectRunItems,
      projectArtifactItems: _projectArtifactItems,
      loadAllProjectArtifacts: _loadAllProjectArtifacts,
      projectTargetItems: _projectTargetItems,
      projectFindingItems: _projectFindingItems,
      projectFindingsLoaded: _projectFindingsLoaded,
      loadProjectFindings: _loadProjectFindings,
      projectFilesEnabled: _projectFilesEnabled,
      projectArtifactStatus: _projectArtifactStatus,
      projectArtifactDetail: _projectArtifactDetail,
      projectTargetFilterLabel: _projectTargetFilterLabel,
      entityLabelValues: _entityLabelValues,
      entityNoteBody: _entityNoteBody,
      entityMetadataChips: _entityMetadataChips,
      projectProvenanceSummary: _projectProvenanceSummary,
      projectProvenanceSummaryElement: _projectProvenanceSummaryElement,
      formatDate: _formatProjectDate,
      formatBytes: _formatProjectBytes,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      projectMobileEmptyPanel: _projectMobileEmptyPanel,
      projectMobileContentRow: _projectMobileContentRow,
      projectMobileActionMenu: _projectMobileActionMenu,
      projectItemRow: _projectItemRow,
      projectWorkspaceRequest: _projectWorkspaceRequest,
      refreshProjectWorkspace,
      renderProjectExplorer: _renderProjectExplorer,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      downloadBlobAsAttachment: _downloadBlobAsAttachment,
      downloadUrlAsAttachment: _downloadUrlAsAttachment,
      setWorkspaceTab: projectWorkspaceState.setTab,
      syncProjectWorkspaceNestedSuppression: _syncProjectWorkspaceNestedSuppression,
      focusProjectNestedSheet: _focusProjectNestedSheet,
      installProjectMobileKeyboardGuards: _installProjectMobileKeyboardGuards,
    });
    return projectPackagesController;
  }

  function _projectPackagesControllerIfReady() {
    return projectPackagesController || null;
  }

  function _loadProjectPackagesController() {
    if (projectPackagesController) return Promise.resolve(projectPackagesController);
    if (projectPackagesControllerPromise) return projectPackagesControllerPromise;
    const loader = global.loadProjectPackages;
    projectPackagesControllerPromise = (typeof loader === 'function' ? loader() : Promise.resolve())
      .then(() => _projectPackagesController())
      .finally(() => {
        projectPackagesControllerPromise = null;
      });
    return projectPackagesControllerPromise;
  }

  let projectReportController = null;
  let projectReportControllerPromise = null;

  let projectActivityController = null;
  let projectActivityControllerPromise = null;

  function _projectActivityController() {
    if (projectActivityController) return projectActivityController;
    const projectActivity = _projectModule('DarklabProjectActivity', importedProjectActivity);
    const factory = projectActivity && projectActivity.createProjectActivityController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectActivity is unavailable');
    projectActivityController = factory({
      projectWorkspaceRequest: _projectWorkspaceRequest,
      projectResponseError: _projectResponseError,
      formatDate: _formatProjectDate,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      renderProjectExplorer: _renderProjectExplorer,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      openProjectObject: _openProjectObject,
    });
    return projectActivityController;
  }

  function _projectActivityControllerIfReady() {
    return projectActivityController || null;
  }

  function _loadProjectActivityController() {
    if (projectActivityController) return Promise.resolve(projectActivityController);
    if (projectActivityControllerPromise) return projectActivityControllerPromise;
    const loader = global.loadProjectActivity;
    projectActivityControllerPromise = (typeof loader === 'function' ? loader() : Promise.resolve())
      .then((namespace) => {
        if (namespace) importedProjectActivity = namespace;
        return _projectActivityController();
      })
      .finally(() => {
        projectActivityControllerPromise = null;
      });
    return projectActivityControllerPromise;
  }

  function _projectReportController() {
    if (projectReportController) return projectReportController;
    const projectReport = _projectModule('DarklabProjectReport', importedProjectReport);
    const factory = projectReport && projectReport.createProjectReportController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectReport is unavailable');
    projectReportController = factory({
      apiFetch: _shellApiFetch,
      getSelectedProjectId: projectWorkspaceState.selectedId,
      selectedProject: _selectedProject,
      projectSummary: _projectSummary,
      projectRunItems: _projectRunItems,
      projectArtifactItems: _projectArtifactItems,
      loadAllProjectArtifacts: _loadAllProjectArtifacts,
      projectTargetItems: _projectTargetItems,
      projectFindingItems: _projectFindingItems,
      loadProjectFindings: _loadProjectFindings,
      projectArtifactDetail: _projectArtifactDetail,
      formatDate: _formatProjectDate,
      projectProvenanceSummaryElement: _projectProvenanceSummaryElement,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      renderProjectExplorer: _renderProjectExplorer,
      renderProjectMobileDetail: _renderProjectMobileDetail,
      mobileView: () => _projectMobileShellController().currentView(),
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      downloadUrlAsAttachment: _downloadUrlAsAttachment,
      showConfirm: _shellFn('showConfirm', importedShowConfirm),
      logClientError: (message, err) => {
        _shellLogClientError(message, err);
      },
    });
    return projectReportController;
  }

  function _projectReportControllerIfReady() {
    return projectReportController || null;
  }

  function _loadProjectReportController() {
    if (projectReportController) return Promise.resolve(projectReportController);
    if (projectReportControllerPromise) return projectReportControllerPromise;
    const loader = global.loadProjectReport;
    projectReportControllerPromise = (typeof loader === 'function' ? loader() : Promise.resolve())
      .then((namespace) => {
        if (namespace) importedProjectReport = namespace;
        return _projectReportController();
      })
      .finally(() => {
        projectReportControllerPromise = null;
      });
    return projectReportControllerPromise;
  }

  let projectFiltersController = null;

  function _projectFiltersController() {
    if (projectFiltersController) return projectFiltersController;
    const projectFilters = _projectModule('DarklabProjectFilters', importedProjectFilters);
    const factory = projectFilters && projectFilters.createProjectFiltersController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectFilters is unavailable');
    projectFiltersController = factory({
      getSelectedProjectId: projectWorkspaceState.selectedId,
      projectWorkspaceModal: () => projectWorkspaceModal,
      projectExplorerBody: () => projectExplorerBody,
      projectWorkspaceTab: projectWorkspaceState.tab,
      projectSummary: _projectSummary,
      findingReviewStates: PROJECT_WORKSPACE_CONSTANTS.findingReviewStates,
      findingSeverityRank: PROJECT_WORKSPACE_CONSTANTS.findingSeverityRank,
      findingReviewRank: PROJECT_WORKSPACE_CONSTANTS.findingReviewRank,
      projectFindingSortOptions: PROJECT_WORKSPACE_CONSTANTS.findingSortOptions,
      projectFindingNoteStateOptions: PROJECT_WORKSPACE_CONSTANTS.findingNoteStateOptions,
      projectFindingOrphanOptions: PROJECT_WORKSPACE_CONSTANTS.findingOrphanOptions,
      projectFindingScopeOptions: PROJECT_WORKSPACE_CONSTANTS.findingScopeOptions,
      projectFindingSeverityOptions: PROJECT_WORKSPACE_CONSTANTS.findingSeverityOptions,
      projectTargetItems: _projectTargetItems,
      projectTargetLabel: _projectTargetLabel,
      projectRunItems: _projectRunItems,
      projectRunById: _projectRunById,
      shortProjectRunId: _shortProjectRunId,
      projectFindingItems: _projectFindingItems,
      projectFilteredFindingItems: key => _projectFindingsDataController().filteredItems(key),
      hasProjectFilteredFindingsKey: key => _projectFindingsDataController().hasFilteredKey(key),
      projectArtifactItems: _projectArtifactItems,
      entityLabelValues: _entityLabelValues,
      entityNoteBody: _entityNoteBody,
      findingReviewStateLabel: _findingReviewStateLabel,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
    });
    return projectFiltersController;
  }

  let projectFindingsDataController = null;

  function _projectFindingsDataController() {
    if (projectFindingsDataController) return projectFindingsDataController;
    const projectFindingsData = _projectModule('DarklabProjectFindingsData', importedProjectFindingsData);
    const factory = projectFindingsData && projectFindingsData.createProjectFindingsDataController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectFindingsData is unavailable');
    projectFindingsDataController = factory({
      apiFetch: _shellApiFetch,
      selectedProjectId: projectWorkspaceState.selectedId,
      mobileView: () => _projectMobileShellController().currentView(),
      projectSummary: _projectSummary,
      findingFilteredKey: _projectFindingFilteredKey,
      findingServerFilterParams: _projectFindingServerFilterParams,
      collapsedFindingGroupLabels: _projectCollapsedFindingGroupLabels,
      filteredProjectFindings: _filteredProjectFindings,
      pageLimit: 50,
      projectResponseError: _projectResponseError,
      renderProjectExplorer: _renderProjectExplorer,
      renderProjectMobileDetail: _renderProjectMobileDetail,
      renderProjectPackageWizardModal: _renderProjectPackageWizardModal,
      projectPackageWizardActive: _projectPackageWizardActive,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      logClientError: (message, err) => {
        _shellLogClientError(message, err);
      },
    });
    return projectFindingsDataController;
  }

  let projectFindingsController = null;

  let projectFindingsBoardController = null;

  function _projectFindingsBoardController() {
    if (projectFindingsBoardController) return projectFindingsBoardController;
    const projectFindingsBoard = _projectModule('DarklabProjectFindingsBoard', importedProjectFindingsBoard);
    const factory = projectFindingsBoard && projectFindingsBoard.createProjectFindingsBoardController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectFindingsBoard is unavailable');
    projectFindingsBoardController = factory({
      entityMetadataChipClass: _entityMetadataChipClass,
      entityMetadataChips: _entityMetadataChips,
      projectFindingTargetText: _projectFindingTargetText,
      projectTargetLabel: _projectTargetLabel,
      makeProjectButton: _makeProjectButton,
      reviewControl: (finding, projectId) => _projectFindingsController().reviewControl(finding, projectId),
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      metaSeparator: ' · ',
    });
    return projectFindingsBoardController;
  }

  function _projectFindingsController() {
    if (projectFindingsController) return projectFindingsController;
    const projectFindings = _projectModule('DarklabProjectFindings', importedProjectFindings);
    const factory = projectFindings && projectFindings.createProjectFindingsController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectFindings is unavailable');
    projectFindingsController = factory({
      findingReviewStates: PROJECT_WORKSPACE_CONSTANTS.findingReviewStates,
      collapsedFindingGroups: projectWorkspaceState.collapsedFindingGroups,
      collapsedFindingGroupLabels: _projectCollapsedFindingGroupLabels,
      findingsLoadingId: () => _projectFindingsDataController().loadingId(),
      hasFindings: projectId => _projectFindingsDataController().loaded(projectId),
      findingViewMode: projectWorkspaceState.findingViewMode,
      findingSelectMode: projectWorkspaceState.findingSelectMode,
      selectedFindingIds: projectWorkspaceState.selectedFindingIds,
      projectFindingPagination: (projectId, summary) => _projectFindingsDataController().page(projectId, summary),
      projectFindingItems: _projectFindingItems,
      projectFindingBoard: (projectId, summary, options) => _projectFindingsDataController().board(projectId, summary, options),
      filteredProjectFindings: _filteredProjectFindings,
      projectFindingServerFiltersActive: _projectFindingServerFiltersActive,
      findingsBoardAvailable: () => !(document.body && document.body.classList.contains('mobile-terminal-mode')),
      projectFindingTargetText: _projectFindingTargetText,
      projectTargetLabel: _projectTargetLabel,
      entityMetadataChips: _entityMetadataChips,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      renderProjectFindingBoard: (container, projectId, summary, board) => (
        _projectFindingsBoardController().renderBoard(container, projectId, summary, board)
      ),
      setFindingSelectMode: projectWorkspaceState.setFindingSelectMode,
      projectItemRow: _projectItemRow,
      groupBy: _groupBy,
      metaSeparator: ' · ',
      groupCaret: '▾',
    });
    return projectFindingsController;
  }

  let projectArtifactsController = null;
  let projectArtifactsControllerPromise = null;

  function _projectArtifactsControllerIfReady() {
    return projectArtifactsController;
  }

  function _projectArtifactsFactoryReady() {
    return !!(
      _projectModule('DarklabProjectArtifacts', importedProjectArtifacts)
      && typeof _projectModule('DarklabProjectArtifacts', importedProjectArtifacts).createProjectArtifactsController === 'function'
    );
  }

  function _projectArtifactsController() {
    if (projectArtifactsController) return projectArtifactsController;
    const projectArtifacts = _projectModule('DarklabProjectArtifacts', importedProjectArtifacts);
    const factory = projectArtifacts && projectArtifacts.createProjectArtifactsController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectArtifacts is unavailable');
    projectArtifactsController = factory({
      apiFetch: _shellApiFetch,
      projectResponseError: _projectResponseError,
      collapsedArtifactGroups: projectWorkspaceState.collapsedArtifactGroups,
      filesEnabled: () => !!(_shellValue('APP_CONFIG') && _shellValue('APP_CONFIG').workspace_enabled === true),
      selectedProjectId: projectWorkspaceState.selectedId,
      projectTargetFilterActive: _projectTargetFilterActive,
      projectFindingsLoaded: _projectFindingsLoaded,
      filteredProjectArtifacts: _filteredProjectArtifacts,
      projectRunFilterSet: _projectRunFilterSet,
      projectTargetFilterSet: _projectTargetFilterSet,
      projectTargetItems: _projectTargetItems,
      projectRunById: _projectRunById,
      shortProjectRunId: _shortProjectRunId,
      entityMetadataChips: _entityMetadataChips,
      formatDate: _formatProjectDate,
      formatBytes: _formatProjectBytes,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      projectItemRow: _projectItemRow,
      renderProjectExplorer: _renderProjectExplorer,
      renderProjectMobileDetail: _renderProjectMobileDetail,
      mobileView: () => _projectMobileShellController().currentView(),
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      logClientError: (message, err) => {
        _shellLogClientError(message, err);
      },
      groupBy: _groupBy,
      downloadBlobAsAttachment: _downloadBlobAsAttachment,
      downloadUrlAsAttachment: _downloadUrlAsAttachment,
      metaSeparator: ' · ',
      groupCaret: '▾',
    });
    return projectArtifactsController;
  }

  function _loadProjectArtifactsController() {
    if (projectArtifactsController) return Promise.resolve(projectArtifactsController);
    if (projectArtifactsControllerPromise) return projectArtifactsControllerPromise;
    if (_projectArtifactsFactoryReady()) {
      return Promise.resolve(_projectArtifactsController());
    }
    const loader = global.loadProjectArtifacts;
    if (typeof loader !== 'function') {
      return Promise.reject(new Error('Project artifacts loader is unavailable'));
    }
    projectArtifactsControllerPromise = loader()
      .then((namespace) => {
        if (namespace) importedProjectArtifacts = namespace;
        return _projectArtifactsController();
      })
      .finally(() => {
        projectArtifactsControllerPromise = null;
      });
    return projectArtifactsControllerPromise;
  }

  let projectDetailsController = null;

  function _projectDetailsController() {
    if (projectDetailsController) return projectDetailsController;
    const projectDetails = _projectModule('DarklabProjectDetails', importedProjectDetails);
    const factory = projectDetails && projectDetails.createProjectDetailsController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectDetails is unavailable');
    projectDetailsController = factory({
      apiFetch: _shellApiFetch,
      entityMetadataClient: EntityMetadataClient,
      projectNotesForm,
      projectNotesInput,
      projectLabelsForm,
      projectLabelsInput,
      projectLabelsSaveButton,
      projectWorkspaceTab: projectWorkspaceState.tab,
      selectedProject: _selectedProject,
      selectedProjectId: projectWorkspaceState.selectedId,
      projectRows: projectWorkspaceState.rows,
      setProjectRows: projectWorkspaceState.setRows,
      projectSummary: _projectSummary,
      setProjectSummary: projectWorkspaceState.setSummary,
      activeProject: _activeProject,
      setActiveProject: _setActiveProject,
      projectDisplayName: _projectDisplayName,
      projectTargetItems: _projectTargetItems,
      entityLabelValues: _entityLabelValues,
      entityNoteBody: _entityNoteBody,
      entityMetadataChipClass: _entityMetadataChipClass,
      projectMetaRow: _projectMetaRow,
      formatDate: _formatProjectDate,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      renderProjectTargets: _renderProjectTargets,
      projectResponseError: _projectResponseError,
      syncEntityLabels: _syncEntityLabels,
      projectWorkspaceRequest: _projectWorkspaceRequest,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      renderProjectList: _renderProjectList,
      renderProjectExplorer: _renderProjectExplorer,
      renderActiveProject: _renderActiveProject,
      projectNotesAutosaveDelayMs: PROJECT_WORKSPACE_CONSTANTS.projectNotesAutosaveDelayMs,
    });
    return projectDetailsController;
  }

  let projectListController = null;

  function _projectListController() {
    if (projectListController) return projectListController;
    const projectList = _projectModule('DarklabProjectList', importedProjectList);
    const factory = projectList && projectList.createProjectListController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectList is unavailable');
    projectListController = factory({
      projectWorkspaceBody,
      projectWorkspaceLoading: projectWorkspaceState.loading,
      projectRows: projectWorkspaceState.rows,
      selectedProjectId: projectWorkspaceState.selectedId,
      activeProject: _activeProject,
      projectSummary: _projectSummary,
      projectCountEntries: _projectCountEntries,
      projectArtifactsVisible: _projectArtifactsVisible,
      projectDisplayName: _projectDisplayName,
      appendProjectLabelChips: _appendProjectLabelChips,
      appendProjectMobileLabelChips: _appendProjectMobileLabelChips,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      mobileMenuText: '☰',
      mobileChevronText: '›',
      projectPagination: projectWorkspaceState.pagination,
      projectWorkspacePagination,
    });
    return projectListController;
  }

  let projectNavigationController = null;

  function _projectNavigationController() {
    if (projectNavigationController) return projectNavigationController;
    const projectNavigation = _projectModule('DarklabProjectNavigation', importedProjectNavigation);
    const factory = projectNavigation && projectNavigation.createProjectNavigationController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectNavigation is unavailable');
    projectNavigationController = factory({
      projectWorkspaceModal,
      projectMobileDetailTopbar,
      projectMobileTabs,
      activeProject: _activeProject,
      projectWorkspaceTab: projectWorkspaceState.tab,
      setProjectWorkspaceTab: projectWorkspaceState.setTab,
      projectCounts: _projectCounts,
      projectDisplayName: _projectDisplayName,
      projectIsArchived: _projectIsArchived,
      projectArtifactsVisible: _projectArtifactsVisible,
      projectTargetFilterActive: _projectTargetFilterActive,
      projectRunFilterActive: _projectRunFilterActive,
      projectFindingsLoaded: _projectFindingsLoaded,
      projectEntityTabCountText: (projectId, summary, total) => (
        _projectEntitiesController().tabCountText(projectId, summary, total)
      ),
      projectFindingPagination: _projectFindingPagination,
      projectFindingServerFiltersActive: _projectFindingServerFiltersActive,
      filteredProjectFindings: _filteredProjectFindings,
      filteredProjectRuns: _filteredProjectRuns,
      filteredProjectArtifacts: _filteredProjectArtifacts,
      appendProjectLabelChips: _appendProjectLabelChips,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      metaSeparator: ' · ',
      mobileBackText: '‹ Back',
    });
    return projectNavigationController;
  }

  let projectNestedSheetsController = null;

  function _projectNestedSheetsController() {
    if (projectNestedSheetsController) return projectNestedSheetsController;
    const projectNestedSheets = _projectModule('DarklabProjectNestedSheets', importedProjectNestedSheets);
    const factory = projectNestedSheets && projectNestedSheets.createProjectNestedSheetsController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectNestedSheets is unavailable');
    projectNestedSheetsController = factory({
      projectWorkspaceModal,
      projectTargetEditorOverlay,
      projectEntityEditorOverlay,
      projectPackageManifestOverlay,
      projectPackageWizardOverlay,
      isProjectTargetEditorOpen: () => !!(projectTargetEditorOverlay && projectTargetEditorOverlay.classList.contains('open')),
      isProjectEntityEditorOpen: () => !!(projectEntityEditorOverlay && projectEntityEditorOverlay.classList.contains('open')),
      isProjectPackageManifestOpen: () => !!(projectPackageManifestOverlay && projectPackageManifestOverlay.classList.contains('open')),
      isProjectPackageWizardOpen: () => !!(projectPackageWizardOverlay && projectPackageWizardOverlay.classList.contains('open')),
    });
    return projectNestedSheetsController;
  }

  let projectWorkspaceRendererController = null;

  function _projectWorkspaceRendererController() {
    if (projectWorkspaceRendererController) return projectWorkspaceRendererController;
    const projectWorkspaceRenderer = _projectModule('DarklabProjectWorkspaceRenderer', importedProjectWorkspaceRenderer);
    const factory = projectWorkspaceRenderer && projectWorkspaceRenderer.createProjectWorkspaceRendererController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectWorkspaceRenderer is unavailable');
    projectWorkspaceRendererController = factory({
      closeProjectEntityEditor: _closeProjectEntityEditor,
      closeProjectTargetEditor: _closeProjectTargetEditor,
      emptyProjectPanel: _emptyProjectPanel,
      enhanceAppSelects: _shellEnhanceAppSelects(),
      ensureSelectedProject: _ensureSelectedProject,
      flushProjectNotesAutosave: _flushProjectNotesAutosave,
      focusProjectWorkspaceTab: _focusProjectWorkspaceTab,
      isProjectWorkspaceOpen,
      loadProjectFilteredFindings: _loadProjectFilteredFindings,
      loadProjectFindings: _loadProjectFindings,
      mobileView: () => _projectMobileShellController().currentView(),
      projectArtifactsVisible: _projectArtifactsVisible,
      projectExplorerBody,
      projectFindingServerFiltersActive: _projectFindingServerFiltersActive,
      projectFindingsLoaded: _projectFindingsLoaded,
      projectMobileDetailBody,
      projectMobileTabItems: _projectMobileTabItems,
      projectPackageWizardActive: _projectPackageWizardActive,
      projectPagination: projectWorkspaceState.pagination,
      projectRows: projectWorkspaceState.rows,
      projectSummary: _projectSummary,
      projectTargetFilterActive: _projectTargetFilterActive,
      projectWorkspaceLoading: projectWorkspaceState.loading,
      projectWorkspaceSubtitle,
      renderProjectArtifacts: _renderProjectArtifacts,
      renderProjectDetails: _renderProjectDetails,
      renderProjectEntities: _renderProjectEntities,
      renderProjectFilterBar: _renderProjectFilterBar,
      renderProjectFindings: _renderProjectFindings,
      renderProjectHeader: _renderProjectHeader,
      renderProjectList: _renderProjectList,
      renderProjectMobile: _renderProjectMobile,
      renderProjectActivity: _renderProjectActivity,
      renderProjectPackages: _renderProjectPackages,
      renderProjectPackageWizardModal: _renderProjectPackageWizardModal,
      renderProjectReport: _renderProjectReport,
      renderProjectRuns: _renderProjectRuns,
      scheduleProjectFilterSortDividerSync: _scheduleProjectFilterSortDividerSync,
      selectedProject: _selectedProject,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      setWorkspaceTab: projectWorkspaceState.setTab,
      syncProjectFilterSortDivider: _syncProjectFilterSortDivider,
      syncProjectForms: _syncProjectForms,
      workspaceTab: projectWorkspaceState.tab,
    });
    return projectWorkspaceRendererController;
  }

  let projectWorkspaceBootstrapController = null;

  function _projectWorkspaceBootstrapController() {
    if (projectWorkspaceBootstrapController) return projectWorkspaceBootstrapController;
    const projectWorkspaceBootstrap = _projectModule('DarklabProjectWorkspaceBootstrap', importedProjectWorkspaceBootstrap);
    const factory = projectWorkspaceBootstrap && projectWorkspaceBootstrap.createProjectWorkspaceBootstrapController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectWorkspaceBootstrap is unavailable');
    const bindDismissibleFn = _shellFn('bindDismissible', importedBindDismissible);
    const bindMobileSheetFn = _shellFn('bindMobileSheet', importedBindMobileSheet);
    projectWorkspaceBootstrapController = factory({
      bindDismissible: bindDismissibleFn,
      bindMobileSheet: bindMobileSheetFn,
      closeProjectEntityEditor: _closeProjectEntityEditor,
      closeProjectPackageManifest: _closeProjectPackageManifest,
      closeProjectPackageWizard: _closeProjectPackageWizard,
      closeProjectTargetEditor: _closeProjectTargetEditor,
      closeProjectWorkspace,
      isProjectEntityEditorOpen,
      isProjectPackageManifestOpen,
      isProjectPackageWizardOpen,
      isProjectWorkspaceOpen,
      isProjectTargetEditorOpen,
      projectDetailsController: _projectDetailsController,
      projectEntityEditorController: _projectEntityEditorController,
      projectEntityEditorOverlay,
      projectMobileTabs,
      projectPackageManifestOverlay,
      projectPackageWizardOverlay,
      projectActivityController: _projectActivityControllerIfReady,
      projectPackagesController: _projectPackagesControllerIfReady,
      projectTargetEditorOverlay,
      projectTargetsController: _projectTargetsController,
      projectWorkspaceEventsController: _projectWorkspaceEventsController,
      projectWorkspaceModal,
      projectWorkspaceOverlay,
      projectWorkspaceShellController: _projectWorkspaceShellController,
      syncProjectMobileTabEdges: _syncProjectMobileTabEdges,
    });
    return projectWorkspaceBootstrapController;
  }

  let projectTargetsController = null;

  function _projectTargetsController() {
    if (projectTargetsController) return projectTargetsController;
    const projectTargets = _projectModule('DarklabProjectTargets', importedProjectTargets);
    const factory = projectTargets && projectTargets.createProjectTargetsController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectTargets is unavailable');
    projectTargetsController = factory({
      EntityMetadataClient,
      targetHelpers: PROJECT_TARGET_HELPERS,
      overlay: projectTargetEditorOverlay,
      form: projectTargetCreateForm,
      typeSelect: projectTargetTypeSelect,
      valueInput: projectTargetValueInput,
      valueHelp: projectTargetValueHelp,
      valueError: projectTargetValueError,
      labelInput: projectTargetLabelInput,
      notesInput: projectTargetNotesInput,
      title: projectTargetEditorTitle,
      submitButton: projectTargetSubmitButton,
      getLastTargetType: projectWorkspaceState.lastTargetType,
      setLastTargetType: projectWorkspaceState.setLastTargetType,
      setEditingTargetId: projectWorkspaceState.setEditingTargetId,
      selectedProjectId: projectWorkspaceState.selectedId,
      activeProject: _activeProject,
      entityLabelValues: _entityLabelValues,
      entityNoteBody: _entityNoteBody,
      entityMetadataChips: _entityMetadataChips,
      entityMetadataChipClass: _entityMetadataChipClass,
      makeProjectButton: _makeProjectButton,
      emptyProjectPanel: _emptyProjectPanel,
      projectWorkspaceRequest: _projectWorkspaceRequest,
      syncEntityLabels: _syncEntityLabels,
      syncEntityNote: _syncEntityNote,
      refreshProjectWorkspace,
      renderProjectExplorer: _renderProjectExplorer,
      renderProjectWorkspace: _renderProjectWorkspace,
      invalidateProjectTargetPage: projectId => _projectDetailsController().invalidateTargetPage(projectId),
      loadProjectTargetPage: (projectId, options) => _projectDetailsController().loadTargetPage(projectId, options),
      renderProjectMobileDetail: _renderProjectMobileDetail,
      loadProjectAutocompleteTargets: () => {
        _shellFn('loadProjectAutocompleteTargets')?.().catch(() => {});
      },
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      syncProjectWorkspaceNestedSuppression: _syncProjectWorkspaceNestedSuppression,
      installProjectMobileKeyboardGuards: _installProjectMobileKeyboardGuards,
      focusProjectNestedSheet: _focusProjectNestedSheet,
    });
    return projectTargetsController;
  }

  let projectRunsController = null;

  function _projectRunsController() {
    if (projectRunsController) return projectRunsController;
    const projectRuns = _projectModule('DarklabProjectRuns', importedProjectRuns);
    const factory = projectRuns && projectRuns.createProjectRunsController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectRuns is unavailable');
    projectRunsController = factory({
      apiFetch: _shellApiFetch,
      projectResponseError: _projectResponseError,
      projectExplorerBody: () => projectExplorerBody,
      projectRunItems: _projectRunItems,
      projectComparableRuns: _projectComparableRuns,
      projectFindingItems: _projectFindingItems,
      projectFindingsLoaded: _projectFindingsLoaded,
      projectArtifactItems: _projectArtifactItems,
      projectArtifactsVisible: _projectArtifactsVisible,
      projectTargetFilterActive: _projectTargetFilterActive,
      projectRunFilterActive: _projectRunFilterActive,
      filteredProjectRuns: _filteredProjectRuns,
      entityLabelValues: _entityLabelValues,
      entityMetadataChips: _entityMetadataChips,
      formatDate: _formatProjectDate,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      projectItemRow: _projectItemRow,
      renderProjectExplorer: _renderProjectExplorer,
      renderProjectMobileDetail: _renderProjectMobileDetail,
      mobileView: () => _projectMobileShellController().currentView(),
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      logClientError: (message, err) => {
        _shellLogClientError(message, err);
      },
    });
    return projectRunsController;
  }

  let projectMobileCompareController = null;

  function _projectMobileCompareController() {
    if (projectMobileCompareController) return projectMobileCompareController;
    const projectMobileCompare = _projectModule('DarklabProjectMobileCompare', importedProjectMobileCompare);
    const factory = projectMobileCompare && projectMobileCompare.createProjectMobileCompareController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectMobileCompare is unavailable');
    projectMobileCompareController = factory({
      projectWorkspaceModal,
      projectSummary: projectWorkspaceState.summary,
      projectComparableRuns: _projectComparableRuns,
      projectRunBaselineLabelOptions: _projectRunBaselineLabelOptions,
      projectRunCompareOptionText: _projectRunCompareOptionText,
      entityLabelValues: _entityLabelValues,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      compareProjectRuns: _compareProjectRuns,
      closeProjectWorkspace,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
    });
    return projectMobileCompareController;
  }

  let projectMobileShellController = null;

  function _projectMobileShellController() {
    if (projectMobileShellController) return projectMobileShellController;
    const projectMobileShell = _projectModule('DarklabProjectMobileShell', importedProjectMobileShell);
    const factory = projectMobileShell && projectMobileShell.createProjectMobileShellController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectMobileShell is unavailable');
    projectMobileShellController = factory({
      activeProject: _activeProject,
      closeProjectEntityEditor: _closeProjectEntityEditor,
      closeProjectTargetEditor: _closeProjectTargetEditor,
      emptyProjectPanel: _emptyProjectPanel,
      mobileSection: _projectMobileSection,
      orderedProjectRows: _orderedProjectRows,
      projectIsArchived: _projectIsArchived,
      projectMobileBody,
      projectMobileCreateForm,
      projectMobileDetailView,
      projectMobileListView,
      projectMobileNameInput,
      projectMobilePagination,
      projectMobileRoot,
      projectMobileSummary,
      projectPagination: projectWorkspaceState.pagination,
      projectRows: projectWorkspaceState.rows,
      projectPagination: projectWorkspaceState.pagination,
      projectWorkspaceLoading: projectWorkspaceState.loading,
      renderMobileListRow: _renderProjectMobileListRow,
      renderProjectPagination: _renderProjectPagination,
      renderProjectMobileDetail: _renderProjectMobileDetail,
      renderProjectWorkspace: _renderProjectWorkspace,
      selectedProjectId: projectWorkspaceState.selectedId,
      ensureProjectSummary: _ensureProjectSummary,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      setSelectedProjectId: projectWorkspaceState.setSelectedId,
      setWorkspaceTab: projectWorkspaceState.setTab,
    });
    return projectMobileShellController;
  }

  let projectMobileDetailController = null;

  function _projectMobileDetailController() {
    if (projectMobileDetailController) return projectMobileDetailController;
    const projectMobileDetail = _projectModule('DarklabProjectMobileDetail', importedProjectMobileDetail);
    const factory = projectMobileDetail && projectMobileDetail.createProjectMobileDetailController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectMobileDetail is unavailable');
    projectMobileDetailController = factory({
      projectWorkspaceModal,
      projectMobileDetailView,
      projectMobileDetailBody,
      projectMobileTabs,
      notePreviewLimit: PROJECT_WORKSPACE_CONSTANTS.mobileNotePreviewLimit,
      selectedProjectId: projectWorkspaceState.selectedId,
      setSelectedProjectId: projectWorkspaceState.setSelectedId,
      projectWorkspaceTab: projectWorkspaceState.tab,
      projectWorkspaceLoading: projectWorkspaceState.loading,
      activeProject: _activeProject,
      projectRows: projectWorkspaceState.rows,
      projectSummary: _projectSummary,
      projectCounts: _projectCounts,
      projectDisplayName: _projectDisplayName,
      projectTargetItems: _projectTargetItems,
      projectRunItems: _projectRunItems,
      projectRunById: _projectRunById,
      projectComparableRuns: _projectComparableRuns,
      projectArtifactItems: _projectArtifactItems,
      pagedProjectArtifactItems: _pagedProjectArtifactItems,
      projectArtifactPagination: _projectArtifactPagination,
      projectArtifactServerFilterKey: _projectArtifactServerFilterKey,
      loadProjectArtifacts: _loadProjectArtifacts,
      projectFindingItems: _projectFindingItems,
      projectFindingsLoaded: _projectFindingsLoaded,
      projectFindingsLoadingId: () => _projectFindingsDataController().loadingId(),
      hasProjectFindings: (projectId) => _projectFindingsDataController().loaded(projectId),
      projectFindingPagination: (projectId, summary) => _projectFindingsDataController().page(projectId, summary),
      projectFindingServerFiltersActive: _projectFindingServerFiltersActive,
      projectFindingGroupCollapsed: _projectFindingGroupCollapsed,
      collapsedFindingGroupLabels: _projectCollapsedFindingGroupLabels,
      projectArtifactGroupCollapsed: _projectArtifactGroupCollapsed,
      projectTargetFilterActive: _projectTargetFilterActive,
      projectRunFilterActive: _projectRunFilterActive,
      projectRunPagination: _projectRunPagination,
      loadProjectRuns: _loadProjectRuns,
      projectArtifactsVisible: _projectArtifactsVisible,
      projectArtifactStatus: _projectArtifactStatus,
      projectArtifactStatusLabel: _projectArtifactStatusLabel,
      projectArtifactDetailLines: _projectArtifactDetailLines,
      projectFindingTargetText: _projectFindingTargetText,
      projectTargetLabel: _projectTargetLabel,
      projectRunFindingCount: _projectRunFindingCount,
      projectRunArtifactCount: _projectRunArtifactCount,
      filteredProjectRuns: _filteredProjectRuns,
      filteredProjectFindings: _filteredProjectFindings,
      filteredProjectArtifacts: _filteredProjectArtifacts,
      entityLabelValues: _entityLabelValues,
      entityNoteBody: _entityNoteBody,
      entityMetadataChips: _entityMetadataChips,
      entityMetadataChipClass: _entityMetadataChipClass,
      formatDate: _formatProjectDate,
      shortProjectRunId: _shortProjectRunId,
      makeProjectButton: _makeProjectButton,
      bindProjectRuntimePressable: _bindProjectRuntimePressable,
      emptyProjectPanel: _emptyProjectPanel,
      findingReviewControl: _findingReviewControl,
      renderProjectMobileDetailTopbar: _renderProjectMobileDetailTopbar,
      renderProjectMobileTabs: _renderProjectMobileTabs,
      renderProjectMobileEntitiesTab: (projectId, summary) => _projectEntitiesController().renderMobileEntitiesTab(projectId, summary),
      renderProjectMobilePackagesTab: _renderProjectMobilePackagesTab,
      renderProjectMobileReportTab: _renderProjectMobileReportTab,
      renderProjectMobileActivityTab: _renderProjectMobileActivityTab,
      setProjectMobileView: _setProjectMobileView,
      loadProjectFindings: _loadProjectFindings,
      loadProjectFilteredFindings: _loadProjectFilteredFindings,
      groupBy: _groupBy,
      mobileMenuText: '☰',
      caretText: '▾',
      metaSeparator: ' · ',
    });
    return projectMobileDetailController;
  }

  let projectEntityEditorController = null;

  function _projectEntityEditorController() {
    if (projectEntityEditorController) return projectEntityEditorController;
    const projectEntityEditor = _projectModule('DarklabProjectEntityEditor', importedProjectEntityEditor);
    const factory = projectEntityEditor && projectEntityEditor.createProjectEntityEditorController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectEntityEditor is unavailable');
    projectEntityEditorController = factory({
      overlay: projectEntityEditorOverlay,
      title: projectEntityEditorTitle,
      subtitle: projectEntityEditorSubtitle,
      form: projectEntityEditorForm,
      labelsInput: projectEntityLabelsInput,
      noteInput: projectEntityNoteInput,
      activityRoot: projectEntityActivityRoot,
      submitButton: projectEntitySubmitButton,
      parseLabelInput: EntityMetadataClient.parseLabelInput,
      entityTitleForEditor: _entityTitleForEditor,
      entityEditorLabelForType: _entityEditorLabelForType,
      entityLabelValues: _entityLabelValues,
      entityNoteBody: _entityNoteBody,
      syncEntityLabels: _syncEntityLabels,
      syncEntityNote: _syncEntityNote,
      projectResponseError: _projectResponseError,
      projectWorkspaceRequest: _projectWorkspaceRequest,
      openProjectActivity: _openProjectActivity,
      refreshProjectWorkspace,
      invalidateProjectFindings: _invalidateProjectFindings,
      invalidateProjectTargetPage: projectId => _projectDetailsController().invalidateTargetPage(projectId),
      loadProjectFindings: _loadProjectFindings,
      renderProjectExplorer: _renderProjectExplorer,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      syncProjectWorkspaceNestedSuppression: _syncProjectWorkspaceNestedSuppression,
      installProjectMobileKeyboardGuards: _installProjectMobileKeyboardGuards,
      focusProjectNestedSheet: _focusProjectNestedSheet,
    });
    return projectEntityEditorController;
  }

  let projectWorkspaceLifecycleController = null;

  function _projectWorkspaceLifecycleController() {
    if (projectWorkspaceLifecycleController) return projectWorkspaceLifecycleController;
    const projectWorkspaceLifecycle = _projectModule('DarklabProjectWorkspaceLifecycle', importedProjectWorkspaceLifecycle);
    const factory = projectWorkspaceLifecycle && projectWorkspaceLifecycle.createProjectWorkspaceLifecycleController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectWorkspaceLifecycle is unavailable');
    projectWorkspaceLifecycleController = factory({
      apiFetch: _shellApiFetch,
      projectWorkspaceBody,
      selectedProjectId: projectWorkspaceState.selectedId,
      setSelectedProjectId: projectWorkspaceState.setSelectedId,
      projectRows: projectWorkspaceState.rows,
      setProjectRows: projectWorkspaceState.setRows,
      projectPagination: projectWorkspaceState.pagination,
      setProjectPagination: projectWorkspaceState.setPagination,
      projectSummaries: projectWorkspaceState.summaries,
      setProjectSummary: projectWorkspaceState.setSummary,
      setProjectSummaries: projectWorkspaceState.setSummaries,
      projectWorkspaceLoading: projectWorkspaceState.loading,
      setProjectWorkspaceLoading: projectWorkspaceState.setLoading,
      workspaceTab: projectWorkspaceState.tab,
      activeProject: _activeProject,
      loadActiveProjectContext,
      invalidateProjectFindings: _invalidateProjectFindings,
      invalidateProjectRuns: _invalidateProjectRuns,
      invalidateProjectEntities: (projectId = '') => _projectEntitiesController().invalidate(projectId),
      invalidateProjectArtifacts: (projectId = '') => _projectArtifactsControllerIfReady()?.invalidate?.(projectId),
      renderProjectWorkspace: _renderProjectWorkspace,
      syncProjectNotesForm: _syncProjectNotesForm,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      logClientError: (message, err) => {
        _shellLogClientError(message, err);
      },
    });
    return projectWorkspaceLifecycleController;
  }

  let projectWorkspaceEventsController = null;

  function _projectWorkspaceEventsController() {
    if (projectWorkspaceEventsController) return projectWorkspaceEventsController;
    const projectWorkspaceEvents = _projectModule('DarklabProjectWorkspaceEvents', importedProjectWorkspaceEvents);
    const factory = projectWorkspaceEvents && projectWorkspaceEvents.createProjectWorkspaceEventsController;
    if (typeof factory !== 'function') throw new Error('DarklabProjectWorkspaceEvents is unavailable');
    projectWorkspaceEventsController = factory({
      activeProject: _activeProject,
      artifactGroupKey: _projectArtifactGroupKey,
      avoidProjectRunCompareLabelSelfTarget: _avoidProjectRunCompareLabelSelfTarget,
      clearEditingTargetIf: projectWorkspaceState.clearEditingTargetIf,
      closeProjectEntityEditor: _closeProjectEntityEditor,
      closeProjectFilterMenus: _closeProjectFilterMenus,
      closeProjectPackageManifest: _closeProjectPackageManifest,
      closeProjectTargetEditor: _closeProjectTargetEditor,
      closeProjectWorkspace,
      compareProjectRuns: _compareProjectRuns,
      confirmProjectDelete: _confirmProjectDelete,
      confirmProjectDestructive: _confirmProjectDestructive,
      confirmProjectPackageDelete: _confirmProjectPackageDelete,
      confirmProjectRunUnlink: _confirmProjectRunUnlink,
      confirmProjectTargetDelete: _confirmProjectTargetDelete,
      downloadProjectArtifact: _downloadProjectArtifact,
      downloadProjectPackage: _downloadProjectPackage,
      entitiesController: _projectEntitiesController,
      entitySelectMode: projectWorkspaceState.entitySelectMode,
      filteredProjectFindings: _filteredProjectFindings,
      filtersController: _projectFiltersController,
      findingGroupKey: _projectFindingGroupKey,
      findingSelectMode: projectWorkspaceState.findingSelectMode,
      findingTriageEditor: _shellValue('DarklabFindingTriageEditor'),
      flushProjectNotesAutosave: _flushProjectNotesAutosave,
      invalidateProjectFindings: _invalidateProjectFindings,
      isProjectWorkspaceOpen,
      linkLastRunToProject: _linkLastRunToProject,
      ensureProjectSummary: _ensureProjectSummary,
      loadProjectRuns: _loadProjectRuns,
      loadProjectAutocompleteTargets: () => {
        _shellFn('loadProjectAutocompleteTargets')?.().catch(() => {});
      },
      loadProjectFilteredFindings: _loadProjectFilteredFindings,
      loadProjectFindings: _loadProjectFindings,
      loadProjectTargetPage: (projectId, options) => _projectDetailsController().loadTargetPage(projectId, options),
      mobileView: () => _projectMobileShellController().currentView(),
      openProjectEntityEditor: _openProjectEntityEditor,
      openProjectEntityInAtlas: _openProjectEntityInAtlas,
      openFindingsBoard: _shellFn('openFindingsBoard'),
      openProjectEntityPicker: _openProjectEntityPicker,
      openProjectMobileActionSheet: _openProjectMobileActionSheet,
      openProjectMobileCompareSheet: _openProjectMobileCompareSheet,
      openProjectPackageManifest: _openProjectPackageManifest,
      openProjectPackageWizardFromPackage: _openProjectPackageWizardFromPackage,
      openProjectTargetEditor: _openProjectTargetEditor,
      packagesController: _projectPackagesControllerIfReady,
      previewProjectArtifact: _previewProjectArtifact,
      reportController: _projectReportControllerIfReady,
      activityController: _projectActivityControllerIfReady,
      projectArtifactItems: _projectArtifactItems,
      projectArtifactPagination: _projectArtifactPagination,
      projectDisplayName: _projectDisplayName,
      projectExplorerBody,
      projectFindingPagination: _projectFindingPagination,
      projectFindingItems: _projectFindingItems,
      projectFindingCommandFilterSet: _projectFindingCommandFilterSet,
      projectFindingLabelFilterSet: _projectFindingLabelFilterSet,
      projectFindingServerFiltersActive: _projectFindingServerFiltersActive,
      projectFindingSeverityFilterSet: _projectFindingSeverityFilterSet,
      projectFindingScopeFilterSet: _projectFindingScopeFilterSet,
      projectFindingStatusFilterSet: _projectFindingStatusFilterSet,
      projectMobileDetailBody,
      projectMobileListView,
      projectMobileProjectActions: _projectMobileProjectActions,
      projectPackageById: _projectPackageById,
      projectPagination: projectWorkspaceState.pagination,
      projectRows: projectWorkspaceState.rows,
      projectRunPagination: _projectRunPagination,
      projectRunFilterSet: _projectRunFilterSet,
      projectRunItems: _projectRunItems,
      projectSummary: _projectSummary,
      projectTargetFilterSet: _projectTargetFilterSet,
      projectTargetPage: projectId => _projectDetailsController().targetPage(projectId),
      projectTargetById: (projectId, targetId) => _projectDetailsController().targetById(projectId, targetId),
      removeCachedProjectTarget: (projectId, targetId) => _projectDetailsController().removeCachedTarget(projectId, targetId),
      updateCachedProjectTarget: (projectId, targetId, updates) => _projectDetailsController().updateCachedTarget(projectId, targetId, updates),
      projectTargetItems: _projectTargetItems,
      projectWorkspaceModal,
      projectWorkspaceRequest: _projectWorkspaceRequest,
      refreshProjectWorkspace,
      renderProjectExplorer: _renderProjectExplorer,
      renderProjectMobile: _renderProjectMobile,
      renderProjectMobileDetail: _renderProjectMobileDetail,
      renderProjectWorkspace: _renderProjectWorkspace,
      selectedEntityIds: projectWorkspaceState.selectedEntityIds,
      selectedFindingIds: projectWorkspaceState.selectedFindingIds,
      selectedProjectId: projectWorkspaceState.selectedId,
      selectProjectFromMobile: _selectProjectFromMobile,
      setFindingViewMode: projectWorkspaceState.setFindingViewMode,
      setProjectFindingPageOffset: _setProjectFindingPageOffset,
      setProjectArtifactPageOffset: _setProjectArtifactPageOffset,
      setProjectRunPageOffset: _setProjectRunPageOffset,
      setProjectPaginationOffset: _setProjectPaginationOffset,
      setCachedFindingReviewState: _setCachedFindingReviewState,
      updateCachedProjectFinding: _updateCachedProjectFinding,
      setFindingSelectMode: projectWorkspaceState.setFindingSelectMode,
      setProjectMobileCreateOpen: _setProjectMobileCreateOpen,
      setProjectMobileView: _setProjectMobileView,
      setProjectPackageDownloadBusy: _setProjectPackageDownloadBusy,
      setProjectWorkspaceMessage: _setProjectWorkspaceMessage,
      setProjectRunCompareMode: _setProjectRunCompareMode,
      setSelectedProjectId: projectWorkspaceState.setSelectedId,
      setWorkspaceTab: projectWorkspaceState.setTab,
      restoreHistoryRunIntoTab: _shellFn('restoreHistoryRunIntoTab'),
      syncProjectRunCompareMode: _syncProjectRunCompareMode,
      toggleArtifactGroup: projectWorkspaceState.toggleArtifactGroup,
      toggleFindingGroup: projectWorkspaceState.toggleFindingGroup,
      toggleMobileArchivedOpen: () => {
        _projectMobileShellController().setArchivedOpen(!_projectMobileShellController().isArchivedOpen());
      },
      workspaceTab: projectWorkspaceState.tab,
    });
    return projectWorkspaceEventsController;
  }

  function _projectTargetById(summary, targetId) {
    return _projectFiltersController().targetById(summary, targetId);
  }

  function _projectTargetFilterLabel(target) {
    return _projectFiltersController().targetFilterLabel(target);
  }

  function _targetFilterableProjectTab() {
    return _projectFiltersController().targetFilterableProjectTab(projectWorkspaceState.tab());
  }

  function _projectTargetFilterSet(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().targetFilterSet(projectId);
  }

  function _projectTargetFilterIds(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    return _projectFiltersController().targetFilterIds(projectId, summary);
  }

  function _projectTargetFilterActive(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    return _projectFiltersController().targetFilterActive(projectId, summary);
  }

  function _projectRunFilterSet(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().runFilterSet(projectId);
  }

  function _projectRunFilterIds(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    return _projectFiltersController().runFilterIds(projectId, summary);
  }

  function _projectRunFilterActive(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    return _projectFiltersController().runFilterActive(projectId, summary);
  }

  function _projectRunFilterLabel(run) {
    return _projectFiltersController().runFilterLabel(run);
  }

  function _projectRunFilterChipLabel(run) {
    return _projectFiltersController().runFilterChipLabel(run);
  }

  function _projectFindingStatusFilterSet(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingStatusFilterSet(projectId);
  }

  function _projectFindingCommandFilterSet(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingCommandFilterSet(projectId);
  }

  function _projectFindingSeverityFilterSet(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingSeverityFilterSet(projectId);
  }

  function _projectFindingScopeFilterSet(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingScopeFilterSet(projectId);
  }

  function _projectFindingStatusFilterValues(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingStatusFilterValues(projectId);
  }

  function _projectFindingStatusFilterActive(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingStatusFilterActive(projectId);
  }

  function _projectFindingLabelFilterSet(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingLabelFilterSet(projectId);
  }

  function _projectFindingLabelOptions(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingLabelOptions(projectId);
  }

  function _projectFindingLabelFilterValues(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingLabelFilterValues(projectId);
  }

  function _projectFindingLabelFilterActive(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingLabelFilterActive(projectId);
  }

  function _projectFindingNoteStateValue(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingNoteStateValue(projectId);
  }

  function _projectFindingNoteStateFilterActive(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingNoteStateFilterActive(projectId);
  }

  function _projectFindingOrphanFilterValue(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingOrphanFilterValue(projectId);
  }

  function _projectFindingOrphanFilterActive(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingOrphanFilterActive(projectId);
  }

  function _projectFindingSortValue(projectId = projectWorkspaceState.selectedId()) {
    return _projectFiltersController().findingSortValue(projectId);
  }

  function _projectFindingTargetText(summary, finding) {
    return _projectFiltersController().findingTargetText(summary, finding);
  }

  function _sortProjectFindings(findings, projectId, summary) {
    return _projectFiltersController().sortProjectFindings(findings, projectId, summary);
  }

  function _findingReviewStateLabel(value) {
    return _projectFindingsController().reviewStateLabel(value);
  }

  function _projectFindingGroupKey(projectId, runLabel) {
    return _projectFindingsController().groupKey(projectId, runLabel);
  }

  function _projectFindingGroupCollapsed(projectId, runLabel) {
    return _projectFindingsController().groupCollapsed(projectId, runLabel);
  }

  function _projectCollapsedFindingGroupLabels(projectId = projectWorkspaceState.selectedId()) {
    return _projectFindingsController().collapsedGroupLabels(projectId);
  }

  function _projectArtifactGroupKey(projectId, runId) {
    const controller = _projectArtifactsControllerIfReady();
    if (controller) return controller.groupKey(projectId, runId);
    return `${String(projectId || '')}\x1f${String(runId || '')}`;
  }

  function _projectArtifactGroupCollapsed(projectId, runId) {
    const controller = _projectArtifactsControllerIfReady();
    if (controller) return controller.groupCollapsed(projectId, runId);
    return projectWorkspaceState.collapsedArtifactGroups().has(_projectArtifactGroupKey(projectId, runId));
  }

  function _projectRunItems(summary) {
    return _projectSharedUiController().runItems(summary);
  }

  function _projectRunPagination(projectId = projectWorkspaceState.selectedId()) {
    return _projectRunsController().page(projectId);
  }

  function _setProjectRunPageOffset(projectId = projectWorkspaceState.selectedId(), offset = 0) {
    _projectRunsController().setPageOffset(projectId, offset);
  }

  async function _loadProjectRuns(projectId = projectWorkspaceState.selectedId(), options = {}) {
    await _projectRunsController().load(projectId, options);
  }

  function _invalidateProjectRuns(projectId = '') {
    _projectRunsController().invalidate(projectId);
  }

  function _projectRunById(summary, runId) {
    return _projectSharedUiController().runById(summary, runId);
  }

  function _projectComparableRuns(summary) {
    return _projectSharedUiController().comparableRuns(summary);
  }

  function _shortProjectRunId(runId) {
    return _projectSharedUiController().shortRunId(runId);
  }

  function _projectArtifactItems(summary) {
    const controller = _projectArtifactsControllerIfReady();
    if (controller) return controller.items(summary);
    return summary && Array.isArray(summary.artifacts) ? summary.artifacts : [];
  }

  function _projectArtifactPagination(projectId = projectWorkspaceState.selectedId()) {
    const controller = _projectArtifactsControllerIfReady() || (_projectArtifactsFactoryReady() ? _projectArtifactsController() : null);
    if (controller) return controller.page(projectId);
    return { artifacts: [], total: 0, runCounts: {}, limit: 50, offset: 0, loading: true, loaded: false, error: '' };
  }

  function _setProjectArtifactPageOffset(projectId = projectWorkspaceState.selectedId(), offset = 0) {
    const controller = _projectArtifactsControllerIfReady();
    if (controller) controller.setPageOffset(projectId, offset);
  }

  function _pagedProjectArtifactItems(projectId = projectWorkspaceState.selectedId(), artifacts = []) {
    const controller = _projectArtifactsControllerIfReady();
    if (controller) return controller.pagedItems(projectId, artifacts);
    const page = _projectArtifactPagination(projectId);
    const offset = Math.max(0, Number(page.offset || 0));
    const limit = Math.max(1, Number(page.limit || 50));
    return (Array.isArray(artifacts) ? artifacts : []).slice(offset, offset + limit);
  }

  async function _loadProjectArtifacts(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId), options = {}) {
    const controller = await _loadProjectArtifactsController();
    return controller.load(projectId, summary, options);
  }

  async function _loadAllProjectArtifacts(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    const controller = await _loadProjectArtifactsController();
    return controller.loadAll(projectId, summary);
  }

  function _projectFilesEnabled() {
    return !!(_shellValue('APP_CONFIG') && _shellValue('APP_CONFIG').workspace_enabled === true);
  }

  function _projectArtifactsVisible() {
    return _projectFilesEnabled();
  }

  function _projectArtifactStatus(artifact) {
    const controller = _projectArtifactsControllerIfReady();
    if (controller) return controller.status(artifact);
    const artifactStatus = String(artifact && artifact.file_status || '').trim();
    if (['available', 'missing', 'changed', 'disabled'].includes(artifactStatus)) return artifactStatus;
    return artifact && artifact.file_available === false ? 'missing' : 'available';
  }

  function _projectArtifactStatusLabel(artifact) {
    const controller = _projectArtifactsControllerIfReady();
    if (controller) return controller.statusLabel(artifact);
    const artifactStatus = _projectArtifactStatus(artifact);
    if (artifactStatus === 'disabled') return 'disabled';
    if (artifactStatus === 'changed') return 'changed';
    if (artifactStatus === 'missing') return 'missing';
    return 'available';
  }

  function _projectArtifactAccessory(projectId, artifact) {
    const controller = _projectArtifactsControllerIfReady();
    return controller ? controller.accessory(projectId, artifact) : null;
  }

  function _entityLabelValues(entity) {
    return _projectSharedUiController().entityLabelValues(entity);
  }

  function _entityNoteBody(entity) {
    return _projectSharedUiController().entityNoteBody(entity);
  }

  function _entityMetadataChips(entity) {
    return _projectSharedUiController().entityMetadataChips(entity);
  }

  function _entityMetadataChipClass(kind = 'label') {
    return _projectSharedUiController().entityMetadataChipClass(kind);
  }

  function _projectProvenanceSummary(manifest, options) {
    return _projectSharedUiController().projectProvenanceSummary(manifest, options);
  }

  function _projectProvenanceSummaryElement(manifest, options) {
    return _projectSharedUiController().projectProvenanceSummaryElement(manifest, options);
  }

  function _appendProjectLabelChips(parent, project, { className = 'project-label-chips' } = {}) {
    _projectDetailsController().appendLabelChips(parent, project, { className });
  }

  function _appendProjectMobileLabelChips(parent, project) {
    _projectDetailsController().appendMobileLabelChips(parent, project);
  }

  function _entityTitleForEditor(entityType, entity) {
    return _projectSharedUiController().entityTitleForEditor(entityType, entity);
  }

  function _entityEditorLabelForType(entityType) {
    return _projectSharedUiController().entityEditorLabelForType(entityType);
  }

  function _projectArtifactDetail(artifact) {
    const controller = _projectArtifactsControllerIfReady();
    if (controller) return controller.detail(artifact);
    const parts = [
      artifact && artifact.kind || 'file',
      artifact && artifact.content_type || 'unknown type',
      _formatProjectDate(artifact && artifact.created),
    ];
    const artifactStatus = _projectArtifactStatus(artifact);
    const statusDetail = String(artifact && artifact.file_status_detail || '').trim();
    if (artifactStatus === 'changed') {
      parts.push(`current ${_formatProjectBytes(artifact && artifact.current_byte_size)}`);
    } else if (artifactStatus === 'missing') {
      parts.push(statusDetail || 'workspace file is missing');
    } else if (artifactStatus === 'disabled') {
      parts.push(statusDetail || 'Files are disabled on this instance');
    }
    return parts.filter(Boolean).join(' · ');
  }

  function _projectArtifactDetailLines(artifact) {
    const controller = _projectArtifactsControllerIfReady();
    if (controller) return controller.detailLines(artifact);
    const artifactStatus = _projectArtifactStatus(artifact);
    const statusDetail = String(artifact && artifact.file_status_detail || '').trim();
    const lines = [
      [artifact && artifact.kind || 'file', artifact && artifact.content_type || 'unknown type'].filter(Boolean).join(' · '),
      _formatProjectDate(artifact && artifact.created),
    ].filter(Boolean);
    if (artifactStatus === 'changed') {
      lines.push(`current ${_formatProjectBytes(artifact && artifact.current_byte_size)}`);
    } else if (artifactStatus === 'missing') {
      lines.push(statusDetail || 'workspace file is missing');
    } else if (artifactStatus === 'disabled') {
      lines.push(statusDetail || 'Files are disabled on this instance');
    }
    return lines;
  }

  function _projectArtifactDownloadName(artifactPath = '', fallback = 'artifact') {
    const controller = _projectArtifactsControllerIfReady();
    if (controller) return controller.downloadName(artifactPath, fallback);
    const name = String(artifactPath || '').split('/').filter(Boolean).pop();
    return name || fallback;
  }

  function _downloadBlobAsAttachment(blob, filename, successMessage = '') {
    _projectSharedUiController().downloadBlobAsAttachment(blob, filename, successMessage);
  }

  function _downloadUrlAsAttachment(url, filename = '', successMessage = '') {
    _projectSharedUiController().downloadUrlAsAttachment(url, filename, successMessage);
  }

  function _syncProjectWorkspaceNestedSuppression() {
    _projectNestedSheetsController().syncWorkspaceSuppression();
  }

  function _focusProjectNestedSheet(overlay, preferred = null) {
    _projectNestedSheetsController().focusNestedSheet(overlay, preferred);
  }

  function _syncProjectMobileFocusedField() {
    _projectNestedSheetsController().syncMobileFocusedField();
  }

  function _installProjectMobileKeyboardGuards() {
    _projectNestedSheetsController().installKeyboardGuards();
  }

  function _closeProjectPackageManifest() {
    const controller = _projectPackagesControllerIfReady();
    if (controller) {
      controller.closeManifest();
      return;
    }
    if (!projectPackageManifestOverlay) return;
    projectPackageManifestOverlay.classList.add('u-hidden');
    projectPackageManifestOverlay.classList.remove('open');
    projectPackageManifestOverlay.setAttribute('aria-hidden', 'true');
  }

  function isProjectPackageManifestOpen() {
    const controller = _projectPackagesControllerIfReady();
    if (controller) return controller.isManifestOpen();
    return !!(projectPackageManifestOverlay && projectPackageManifestOverlay.classList.contains('open'));
  }

  function _openProjectPackageManifest(pkg) {
    _loadProjectPackagesController()
      .then(controller => controller.openManifest(pkg))
      .catch((err) => {
        _shellLogClientError('failed to load project package manifest', err);
        _setProjectWorkspaceMessage('Could not load package manifest.', { error: true });
      });
  }

  async function _previewProjectArtifact(projectId, artifactId) {
    const controller = await _loadProjectArtifactsController();
    await controller.preview(projectId, artifactId);
  }

  async function _downloadProjectArtifact(projectId, artifactId, artifactPath = '') {
    const controller = await _loadProjectArtifactsController();
    await controller.download(projectId, artifactId, artifactPath);
  }

  function _projectPackageItems(summary) {
    const controller = _projectPackagesControllerIfReady();
    if (controller) return controller.items(summary);
    return summary && Array.isArray(summary.packages) ? summary.packages : [];
  }

  function _projectPackageWizardActive(projectId = projectWorkspaceState.selectedId()) {
    const controller = _projectPackagesControllerIfReady();
    return controller ? controller.isWizardActive(projectId) : false;
  }

  function isProjectPackageWizardOpen() {
    const controller = _projectPackagesControllerIfReady();
    if (controller) return controller.isWizardOpen();
    return !!(projectPackageWizardOverlay && projectPackageWizardOverlay.classList.contains('open'));
  }

  function isProjectEntityEditorOpen() {
    if (!_projectWorkspaceModulesReady()) {
      return !!(projectEntityEditorOverlay && projectEntityEditorOverlay.classList.contains('open'));
    }
    return _projectEntityEditorController().isOpen();
  }

  function _closeProjectEntityEditor() {
    if (!_projectWorkspaceModulesReady()) {
      if (!projectEntityEditorOverlay) return;
      projectEntityEditorOverlay.classList.add('u-hidden');
      projectEntityEditorOverlay.classList.remove('open');
      projectEntityEditorOverlay.setAttribute('aria-hidden', 'true');
      return;
    }
    _projectEntityEditorController().close();
  }

  function _openProjectEntityEditor(projectId, entityType, entity, options = {}) {
    _projectEntityEditorController().open(projectId, entityType, entity, options);
  }

  function openEntityMetadataEditor(entityType, entity, options = {}) {
    const projectId = options && Object.prototype.hasOwnProperty.call(options, 'projectId')
      ? options.projectId
      : '';
    _ensureProjectWorkspaceModules()
      .then(() => _openProjectEntityEditor(projectId, entityType, entity, options))
      .catch((err) => {
        _shellLogClientError('failed to load project entity editor', err);
        _shellShowToast('Could not open the metadata editor.', 'error');
      });
  }

  function _renderProjectPackageWizardModal(options = {}) {
    const controller = _projectPackagesControllerIfReady();
    if (controller) controller.renderWizardModal(options);
  }

  function _openProjectPackageWizard(projectId, preset = 'evidence') {
    _loadProjectPackagesController()
      .then(controller => controller.openWizard(projectId, preset))
      .catch((err) => {
        _shellLogClientError('failed to load project package wizard', err);
        _setProjectWorkspaceMessage('Could not load package builder.', { error: true });
      });
  }

  function _openProjectPackageWizardFromPackage(projectId, pkg) {
    _loadProjectPackagesController()
      .then(controller => controller.openWizardFromPackage(projectId, pkg))
      .catch((err) => {
        _shellLogClientError('failed to load project package wizard', err);
        _setProjectWorkspaceMessage('Could not load package builder.', { error: true });
      });
  }

  function _closeProjectPackageWizard(options = {}) {
    const controller = _projectPackagesControllerIfReady();
    if (controller) controller.closeWizard(options);
    else if (projectPackageWizardOverlay) {
      projectPackageWizardOverlay.classList.add('u-hidden');
      projectPackageWizardOverlay.classList.remove('open');
      projectPackageWizardOverlay.setAttribute('aria-hidden', 'true');
    }
  }

  function _projectPackageById(summary, packageId) {
    const controller = _projectPackagesControllerIfReady();
    if (controller) return controller.byId(summary, packageId);
    const normalized = String(packageId || '').trim();
    if (!normalized || !summary || !Array.isArray(summary.packages)) return null;
    return summary.packages.find(item => String(item && item.id || '') === normalized) || null;
  }

  function _setProjectPackageDownloadBusy(button, busy) {
    const controller = _projectPackagesControllerIfReady();
    if (controller) {
      controller.setDownloadBusy(button, busy);
      return;
    }
    if (button) button.disabled = !!busy;
  }

  async function _downloadProjectPackage(projectId, pkg) {
    const controller = await _loadProjectPackagesController();
    await controller.downloadPackage(projectId, pkg);
  }

  function _projectFindingItems(projectId = projectWorkspaceState.selectedId()) {
    return _projectFindingsDataController().items(projectId);
  }

  function _projectFindingsLoaded(projectId = projectWorkspaceState.selectedId()) {
    return _projectFindingsDataController().loaded(projectId);
  }

  function _projectFindingPagination(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    return _projectFindingsDataController().page(projectId, summary);
  }

  function _setProjectFindingPageOffset(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId), offset = 0) {
    _projectFindingsDataController().setPageOffset(projectId, summary, offset);
  }

  function _projectFindingServerFilterParams(projectId, summary = _projectSummary(projectId)) {
    return _projectFiltersController().findingServerFilterParams(projectId, summary);
  }

  function _projectArtifactServerFilterParams(projectId, summary = _projectSummary(projectId)) {
    const controller = _projectArtifactsControllerIfReady();
    return controller ? controller.serverFilterParams(projectId, summary) : new URLSearchParams();
  }

  function _projectArtifactServerFilterKey(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    const controller = _projectArtifactsControllerIfReady();
    if (controller) return controller.serverFilterKey(projectId, summary);
    const params = _projectArtifactServerFilterParams(projectId, summary);
    params.sort?.();
    return params.toString();
  }

  function _projectFindingServerFiltersActive(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    return _projectFiltersController().findingServerFiltersActive(projectId, summary);
  }

  function _projectFindingFilteredKey(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    return _projectFiltersController().findingFilteredKey(projectId, summary);
  }

  function _projectFilteredFindingItems(projectId = projectWorkspaceState.selectedId(), summary = _projectSummary(projectId)) {
    return _projectFiltersController().filteredFindingItems(projectId, summary);
  }

  function _invalidateProjectFilteredFindings(projectId = '') {
    _projectFindingsDataController().invalidateFiltered(projectId);
  }

  function _invalidateProjectFindings(projectId = '') {
    _projectFindingsDataController().invalidate(projectId);
  }

  function _projectTargetLabel(summary, targetId) {
    return _projectSharedUiController().targetLabel(summary, targetId);
  }

  function _formatProjectDate(value) {
    return _projectSharedUiController().formatDate(value);
  }

  function _formatProjectBytes(value) {
    return _projectSharedUiController().formatBytes(value);
  }

  function _emptyProjectPanel(text) {
    return _projectSharedUiController().emptyPanel(text);
  }

  function _projectMetaRow(label, value) {
    return _projectSharedUiController().metaRow(label, value);
  }

  function _projectItemRow({ title, meta = '', detail = '', badge = '', chips = [], action = null, accessory = null, forceArticle = false }) {
    return _projectSharedUiController().itemRow({ title, meta, detail, badge, chips, action, accessory, forceArticle });
  }

  function _findingReviewControl(finding, projectId) {
    return _projectFindingsController().reviewControl(finding, projectId);
  }

  function _findingRowAccessory(finding, projectId) {
    return _projectFindingsController().rowAccessory(finding, projectId);
  }

  function _openProjectTargetEditor(projectId, target = null) {
    _projectTargetsController().openEditor(projectId, target);
  }

  function _closeProjectTargetEditor(options = {}) {
    if (!_projectWorkspaceModulesReady()) {
      if (!projectTargetEditorOverlay) return;
      projectTargetEditorOverlay.classList.add('u-hidden');
      projectTargetEditorOverlay.classList.remove('open');
      projectTargetEditorOverlay.setAttribute('aria-hidden', 'true');
      return;
    }
    _projectTargetsController().closeEditor(options);
  }

  function isProjectTargetEditorOpen() {
    if (!_projectWorkspaceModulesReady()) {
      return !!(projectTargetEditorOverlay && projectTargetEditorOverlay.classList.contains('open'));
    }
    return _projectTargetsController().isOpen();
  }

  function _projectTargetDisplayRow(projectId, target) {
    return _projectTargetsController().targetDisplayRow(projectId, target);
  }

  function _projectRunRemoveControl(projectId, run) {
    return _projectRunsController().runRemoveControl(projectId, run);
  }

  function _projectRunFindingCount(projectId, runId, run = null) {
    return _projectRunsController().runFindingCount(projectId, runId, run);
  }

  function _projectRunArtifactCount(summary, runId, run = null) {
    return _projectRunsController().runArtifactCount(summary, runId, run);
  }

  function _projectRunControls(projectId, run, summary) {
    return _projectRunsController().runControls(projectId, run, summary);
  }

  function _projectRunBaselineLabelOptions(runs) {
    return _projectRunsController().baselineLabelOptions(runs);
  }

  function _projectRunCompareOptionText(run) {
    return _projectRunsController().compareOptionText(run);
  }

  function _syncProjectRunCompareMode(wrap) {
    _projectRunsController().syncCompareMode(wrap);
  }

  function _setProjectRunCompareMode(modeButton, event = null) {
    _projectRunsController().setCompareMode(modeButton, event);
  }

  function _avoidProjectRunCompareLabelSelfTarget(container, label) {
    _projectRunsController().avoidCompareLabelSelfTarget(container, label);
  }

  function _compareProjectRuns(projectId, leftId, mode, targetValue, controls = null) {
    _projectRunsController().compareRuns(projectId, leftId, mode, targetValue, controls);
  }

  function _renderProjectRunCompareControls(runs) {
    return _projectRunsController().renderCompareControls(runs);
  }

  function _renderProjectTargets(projectId, targets) {
    return _projectTargetsController().renderTargets(projectId, targets);
  }

  function _setProjectFilterMenuOpen(menu, open) {
    _projectFiltersController().setFilterMenuOpen(menu, open);
  }

  function _closeProjectFilterMenus(exceptMenu = null) {
    _projectFiltersController().closeFilterMenus(exceptMenu);
  }

  function _renderProjectFilterBar(projectId, summary) {
    return _projectFiltersController().renderFilterBar(projectId, summary);
  }

  function _syncProjectFilterSortDivider(root) {
    _projectFiltersController().syncFilterSortDivider(root);
  }

  function _scheduleProjectFilterSortDividerSync(root) {
    if (!_projectWorkspaceModulesReady()) return;
    _projectFiltersController().scheduleFilterSortDividerSync(root);
  }

  function _projectRunDirectTargetIds(run) {
    return _projectFiltersController().runDirectTargetIds(run);
  }

  function _projectFindingTargetIds(finding) {
    return _projectFiltersController().findingTargetIds(finding);
  }

  function _projectRunIdsMatchingTargets(projectId, filterIds) {
    return _projectFiltersController().runIdsMatchingTargets(projectId, filterIds);
  }

  function _projectRunMatchesTargetFilters(run, projectId, filterIds, matchingRunIds) {
    return _projectFiltersController().runMatchesTargetFilters(run, projectId, filterIds, matchingRunIds);
  }

  function _filteredProjectRuns(projectId, summary) {
    return _projectFiltersController().filteredRuns(projectId, summary);
  }

  function _filteredProjectFindings(projectId, summary) {
    return _projectFiltersController().filteredFindings(projectId, summary);
  }

  function _filteredProjectArtifacts(projectId, summary) {
    return _projectFiltersController().filteredArtifacts(projectId, summary);
  }

  function _groupBy(items, keyFn) {
    return _projectSharedUiController().groupBy(items, keyFn);
  }

  async function _loadProjectFindings(projectId, options = {}) {
    return _projectFindingsDataController().load(projectId, options);
  }

  async function _loadProjectFilteredFindings(projectId, summary = _projectSummary(projectId), options = {}) {
    await _projectFindingsDataController().loadFiltered(projectId, summary, options);
  }

  function _syncProjectForms(project = _selectedProject()) {
    _projectDetailsController().syncForms(project);
  }

  function _syncProjectNotesForm() {
    if (!_projectWorkspaceModulesReady()) return;
    _projectDetailsController().syncNotesForm();
  }

  function _flushProjectNotesAutosave() {
    if (!_projectWorkspaceModulesReady()) return Promise.resolve();
    return _projectDetailsController().flushNotesAutosave();
  }

  function _makeProjectButton(label, action, projectId, role = 'secondary', tone = '') {
    return _projectSharedUiController().makeButton(label, action, projectId, role, tone);
  }

  function _projectIsArchived(project) {
    return _projectListController().isArchived(project);
  }

  function _orderedProjectRows(activeId, rows = projectWorkspaceState.rows()) {
    return _projectListController().orderedRows(activeId, rows);
  }

  function _renderProjectList() {
    _projectListController().renderList();
  }

  function _projectMobileTabItems(projectId, summary) {
    return _projectNavigationController().mobileTabItems(projectId, summary);
  }

  function _syncProjectMobileActiveTabScroll() {
    _projectNavigationController().syncMobileActiveTabScroll();
  }

  function _syncProjectMobileTabEdges() {
    _projectNavigationController().syncMobileTabEdges();
  }

  function _renderProjectMobileListRow(project, activeId) {
    return _projectListController().renderMobileListRow(project, activeId);
  }

  function _renderProjectPagination(host, options = {}) {
    return _projectListController().renderPagination(host, options);
  }

  function _projectMobileSection(label, count, { open = true } = {}) {
    return _projectListController().mobileSection(label, count, { open });
  }

  async function _setProjectMobileCreateOpen(open, { focus = false } = {}) {
    await _ensureProjectWorkspaceModules();
    _projectMobileShellController().setCreateOpen(open, { focus });
  }

  async function _setProjectMobileView(view) {
    await _ensureProjectWorkspaceModules();
    _projectMobileShellController().setView(view);
  }

  async function _selectProjectFromMobile(projectId, tab = '') {
    await _ensureProjectWorkspaceModules();
    _projectMobileShellController().selectProject(projectId, tab);
  }

  function _projectMobileProjectActions(project) {
    return _projectMobileShellController().projectActions(project);
  }

  function _renderProjectMobileDetailTopbar(project, activeId) {
    _projectNavigationController().renderMobileDetailTopbar(project, activeId);
  }

  function _renderProjectMobileTabs(projectId, summary) {
    _projectNavigationController().renderMobileTabs(projectId, summary);
  }

  function _projectMobileActionMenu(projectId, label, actions = []) {
    return _projectMobileDetailController().actionMenu(projectId, label, actions);
  }

  function _closeProjectMobileActionSheet({ restoreFocus = true } = {}) {
    if (!_projectWorkspaceModulesReady()) return;
    _projectMobileDetailController().closeActionSheet({ restoreFocus });
  }

  function _openProjectMobileActionSheet(projectId, label, actions = [], returnFocus = null) {
    _projectMobileDetailController().openActionSheet(projectId, label, actions, returnFocus);
  }

  function _closeProjectMobileCompareSheet({ restoreFocus = true } = {}) {
    if (!_projectWorkspaceModulesReady()) return;
    _projectMobileCompareController().close({ restoreFocus });
  }

  function _openProjectMobileCompareSheet(projectId, returnFocus = null) {
    _projectMobileCompareController().open(projectId, returnFocus);
  }

  function _projectMobileContentRow({
    title,
    meta = '',
    detail = '',
    badge = '',
    chips = [],
    action = null,
    accessory = null,
    className = '',
  }) {
    return _projectMobileDetailController().contentRow({
      title,
      meta,
      detail,
      badge,
      chips,
      action,
      accessory,
      className,
    });
  }

  function _projectMobileEmptyPanel(text, actions = []) {
    return _projectMobileDetailController().emptyPanel(text, actions);
  }

  function _renderProjectMobileDetail() {
    _projectMobileDetailController().renderDetail();
  }

  function _renderProjectMobile() {
    _projectMobileShellController().renderMobile();
  }

  function _renderProjectHeader(project, summary, options = {}) {
    return _projectNavigationController().renderProjectHeader(project, summary, options);
  }

  function _focusProjectWorkspaceTab(tabId) {
    _projectNavigationController().focusWorkspaceTab(tabId);
  }

  function cycleProjectWorkspaceTab(offset = 1) {
    if (!_projectWorkspaceModulesReady()) return false;
    return _projectWorkspaceRendererController().cycleTab(offset);
  }

  function _renderProjectDetails(container, project, summary) {
    _projectDetailsController().renderDetails(container, project, summary);
  }

  function _renderProjectRuns(container, projectId, summary) {
    _projectRunsController().renderRuns(container, projectId, summary);
  }

  function _openProjectEntityInAtlas(projectId, summary, entity) {
    _projectEntitiesController().openInAtlas(projectId, summary, entity);
  }

  function _openProjectEntityPicker(projectId) {
    _projectEntitiesController().openPicker(projectId);
  }

  function _renderProjectEntities(container, projectId, summary) {
    _projectEntitiesController().renderEntities(container, projectId, summary);
  }

  function _renderProjectFindings(container, projectId, summary) {
    _projectFindingsController().renderFindings(container, projectId, summary);
  }

  function _renderProjectArtifacts(container, projectId, summary) {
    if (projectArtifactsController) {
      projectArtifactsController.renderArtifacts(container, projectId, summary);
      return;
    }
    container.replaceChildren(_emptyProjectPanel('Loading project artifacts...'));
    _loadProjectArtifactsController()
      .then((controller) => {
        if (!container.isConnected || projectWorkspaceState.tab() !== 'artifacts') return;
        controller.renderArtifacts(container, projectId, summary);
      })
      .catch((err) => {
        _shellLogClientError('failed to load project artifacts', err);
        if (!container.isConnected) return;
        container.replaceChildren(_emptyProjectPanel('Could not load project artifacts.'));
      });
  }

  function _renderProjectPackages(container, projectId, summary) {
    if (projectPackagesController) {
      projectPackagesController.renderPackages(container, projectId, summary);
      return;
    }
    container.replaceChildren(_emptyProjectPanel('Loading evidence packages...'));
    _loadProjectPackagesController()
      .then((controller) => {
        if (!container.isConnected || projectWorkspaceState.tab() !== 'packages') return;
        controller.renderPackages(container, projectId, summary);
      })
      .catch((err) => {
        _shellLogClientError('failed to load project packages', err);
        if (!container.isConnected) return;
        container.replaceChildren(_emptyProjectPanel('Could not load evidence packages.'));
      });
  }

  function _renderProjectActivity(container, projectId, summary) {
    if (projectActivityController) {
      projectActivityController.renderActivity(container, projectId, summary);
      return;
    }
    container.replaceChildren(_emptyProjectPanel('Loading project activity...'));
    _loadProjectActivityController()
      .then((controller) => {
        if (!container.isConnected || projectWorkspaceState.tab() !== 'activity') return;
        controller.renderActivity(container, projectId, summary);
      })
      .catch((err) => {
        _shellLogClientError('failed to load project activity', err);
        if (!container.isConnected) return;
        container.replaceChildren(_emptyProjectPanel('Could not load project activity.'));
      });
  }

  function _openProjectObject(projectId, { tab = '', targetType = '', targetId = '' } = {}) {
    const normalizedProjectId = String(projectId || projectWorkspaceState.selectedId() || '').trim();
    const normalizedTab = String(tab || '').trim();
    if (!normalizedProjectId || !normalizedTab) return;
    if (normalizedTab === 'activity') {
      _openProjectActivity(normalizedProjectId, { targetType, targetId });
      return;
    }
    projectWorkspaceState.setTab(normalizedTab);
    _renderProjectExplorer();
  }

  function _openProjectActivity(projectId, { targetId = '', targetType = '' } = {}) {
    const normalizedProjectId = String(projectId || projectWorkspaceState.selectedId() || '').trim();
    if (!normalizedProjectId) return;
    _closeProjectEntityEditor();
    projectWorkspaceState.setTab('activity');
    _renderProjectExplorer();
    _loadProjectActivityController()
      .then((controller) => {
        const st = controller.stateFor(normalizedProjectId);
        st.filters.target_id = String(targetId || '').trim();
        st.filters.target_type = String(targetType || '').trim();
        st.offset = 0;
        st.loaded = false;
        if (projectWorkspaceState.tab() === 'activity') _renderProjectExplorer();
        return controller.load(normalizedProjectId);
      })
      .catch((err) => {
        _shellLogClientError('failed to open project activity', err);
      });
  }

  function _renderProjectReport(container, projectId, summary) {
    if (projectReportController) {
      projectReportController.renderReport(container, projectId, summary);
      return;
    }
    container.replaceChildren(_emptyProjectPanel('Loading report builder...'));
    _loadProjectReportController()
      .then((controller) => {
        if (!container.isConnected || projectWorkspaceState.tab() !== 'report') return;
        controller.renderReport(container, projectId, summary);
      })
      .catch((err) => {
        _shellLogClientError('failed to load project report builder', err);
        if (!container.isConnected) return;
        container.replaceChildren(_emptyProjectPanel('Could not load the report builder.'));
      });
  }

  function _renderProjectMobileReportTab(projectId, summary) {
    if (projectReportController) return projectReportController.renderMobileReportTab(projectId, summary);
    const panel = _emptyProjectPanel('Loading report builder...');
    _loadProjectReportController()
      .then(() => {
        if (projectWorkspaceState.tab() === 'report' && _projectMobileShellController().currentView() === 'detail') {
          _renderProjectMobileDetail();
        }
      })
      .catch((err) => {
        _shellLogClientError('failed to load mobile project report builder', err);
        if (panel.isConnected) panel.replaceChildren('Could not load the report builder.');
      });
    return panel;
  }

  function _renderProjectMobilePackagesTab(projectId, summary) {
    if (projectPackagesController) return projectPackagesController.renderMobilePackagesTab(projectId, summary);
    const panel = _emptyProjectPanel('Loading evidence packages...');
    _loadProjectPackagesController()
      .then(() => {
        if (projectWorkspaceState.tab() === 'packages' && _projectMobileShellController().currentView() === 'detail') {
          _renderProjectMobileDetail();
        }
      })
      .catch((err) => {
        _shellLogClientError('failed to load mobile project packages', err);
        if (panel.isConnected) panel.replaceChildren('Could not load evidence packages.');
      });
    return panel;
  }

  function _renderProjectMobileActivityTab(projectId, summary) {
    if (projectActivityController) return projectActivityController.renderMobileActivityTab(projectId, summary);
    const panel = _emptyProjectPanel('Loading project activity...');
    _loadProjectActivityController()
      .then(() => {
        if (projectWorkspaceState.tab() === 'activity' && _projectMobileShellController().currentView() === 'detail') {
          _renderProjectMobileDetail();
        }
      })
      .catch((err) => {
        _shellLogClientError('failed to load mobile project activity', err);
        if (panel.isConnected) panel.replaceChildren('Could not load project activity.');
      });
    return panel;
  }

  function _renderProjectExplorer() {
    _projectWorkspaceRendererController().renderExplorer();
  }

  function _renderProjectWorkspace() {
    _projectWorkspaceRendererController().renderWorkspace();
  }

  async function _loadProjectSummaries(projects) {
    await _projectWorkspaceLifecycleController().loadProjectSummaries(projects);
  }

  async function _ensureProjectSummary(projectId = projectWorkspaceState.selectedId()) {
    return _projectWorkspaceLifecycleController().ensureProjectSummary(projectId);
  }

  function _setProjectPaginationOffset(offset) {
    projectWorkspaceState.setPaginationOffset(offset);
  }

  async function refreshProjectWorkspace() {
    if (!_projectWorkspaceModulesReady()) {
      if (!_projectWorkspaceOverlayOpenFallback()) return;
      await _ensureProjectWorkspaceModules();
    }
    await _projectWorkspaceLifecycleController().refreshProjectWorkspace();
  }

  function _scheduleProjectWorkspaceExternalRefresh() {
    if (!_projectWorkspaceModulesReady()) {
      if (!_projectWorkspaceOverlayOpenFallback()) return;
      _ensureProjectWorkspaceModules()
        .then(() => _scheduleProjectWorkspaceExternalRefresh())
        .catch((err) => {
          _shellLogClientError('failed to load project workspace for external refresh', err);
        });
      return;
    }
    _projectWorkspaceShellController().scheduleExternalRefresh();
  }

  function _notifyProjectWorkspaceChanged(reason = 'updated', projectId = '', { local = true } = {}) {
    if (!_projectWorkspaceModulesReady()) return;
    _projectWorkspaceShellController().notifyChanged(reason, projectId, { local });
  }

  _projectActiveContextController().bindTargetDiscoveryEvent();

  async function openProjectWorkspace() {
    if (!_projectWorkspaceModulesReady() && projectWorkspaceOverlay) {
      projectWorkspaceOverlay.classList.remove('u-hidden');
      projectWorkspaceOverlay.classList.add('open');
      projectWorkspaceOverlay.setAttribute('aria-hidden', 'false');
      if (projectWorkspaceBody && !String(projectWorkspaceBody.textContent || '').trim()) {
        projectWorkspaceBody.textContent = 'Loading projects...';
      }
      if (projectMobileBody && !String(projectMobileBody.textContent || '').trim()) {
        projectMobileBody.textContent = 'Loading projects...';
      }
      _shellFn('markInteractionSurfaceReady', importedMarkInteractionSurfaceReady)?.('projects', projectWorkspaceOverlay, projectWorkspaceModal);
    }
    await _ensureProjectWorkspaceModules();
    await _projectWorkspaceShellController().open();
  }

  function _autoPromoteProjectPickerContent(projects, preferredProjectId = '') {
    const wrap = document.createElement('div');
    wrap.className = 'history-project-picker';
    const select = document.createElement('select');
    select.className = 'form-select form-control-compact';
    select.setAttribute('aria-label', 'Project');
    projects.forEach((project) => {
      const option = document.createElement('option');
      option.value = String(project.id || '');
      option.textContent = _projectDisplayName(project) || String(project.id || '');
      select.appendChild(option);
    });
    if (preferredProjectId && projects.some(project => String(project.id || '') === preferredProjectId)) {
      select.value = preferredProjectId;
    }
    const help = document.createElement('div');
    help.className = 'history-project-picker-help';
    help.textContent = 'Choose a project for the new auto-promote rule.';
    wrap.append(select, help);
    return { wrap, select };
  }

  async function _promptAutoPromoteRuleProject(preferredProjectId = '') {
    if (!_shellFn('showConfirm', importedShowConfirm)) return '';
    const resp = await _shellApiFetch('/projects?include_archived=1&include_counts=0&limit=100&offset=0', { cache: 'no-store' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    const projects = (Array.isArray(data.projects) ? data.projects : [])
      .filter(project => String(project && project.status || 'active') !== 'archived');
    if (!projects.length) {
      _shellShowToast('Create an active project before creating an auto-promote rule.', 'error');
      return '';
    }
    const activeProject = _activeProject();
    const preferredId = preferredProjectId
      || (activeProject && activeProject.id ? String(activeProject.id) : '');
    const ordered = _orderedProjectRows(preferredId, projects);
    const { wrap, select } = _autoPromoteProjectPickerContent(ordered, preferredId);
    const choicePromise = _shellShowConfirm({
      body: 'Create auto-promote rule from Atlas view',
      content: wrap,
      defaultFocus: select,
      actions: [
        { id: 'cancel', label: 'Cancel', role: 'cancel' },
        { id: 'create', label: 'Create rule', role: 'primary' },
      ],
      refocusOnResolve: false,
    });
    const enhanceAppSelects = _shellEnhanceAppSelects();
    if (typeof enhanceAppSelects === 'function') {
      enhanceAppSelects(wrap);
      if (_shellUseMobileTerminalViewportMode()) {
        wrap.querySelector('.app-select-menu')?.classList.add('dropdown-up');
      }
    }
    const choice = await choicePromise;
    return choice === 'create' ? String(select.value || '') : '';
  }

  async function openProjectAutoPromoteRuleFromAtlas(draft = {}) {
    const activeProject = _activeProject();
    let projectId = String(draft.project_id || '').trim();
    if (!projectId && activeProject && activeProject.id) projectId = String(activeProject.id);
    if (!projectId) projectId = await _promptAutoPromoteRuleProject();
    if (!projectId) return false;
    await openProjectWorkspace();
    projectWorkspaceState.setSelectedId(projectId);
    projectWorkspaceState.setTab('entities');
    await _ensureProjectSummary(projectId);
    _projectEntitiesController().openAutoPromoteRuleFromAtlas(projectId, draft);
    _renderProjectWorkspace();
    _renderProjectExplorer();
    return true;
  }

  function closeProjectWorkspace({ refocus = true } = {}) {
    if (!_projectWorkspaceModulesReady()) {
      if (!projectWorkspaceOverlay) return;
      projectWorkspaceOverlay.classList.add('u-hidden');
      projectWorkspaceOverlay.classList.remove('open');
      projectWorkspaceOverlay.setAttribute('aria-hidden', 'true');
      return;
    }
    _projectWorkspaceShellController().close({ refocus });
  }

  async function _projectWorkspaceRequest(url, options = {}) {
    return _projectWorkspaceShellController().request(url, options);
  }

  async function _syncEntityLabels(entityType, entityId, nextLabels) {
    await _projectWorkspaceActionsController().syncEntityLabels(entityType, entityId, nextLabels);
  }

  async function _syncEntityNote(entityType, entityId, body) {
    await _projectWorkspaceActionsController().syncEntityNote(entityType, entityId, body);
  }

  async function _linkLastRunToProject(projectId, summary) {
    await _projectWorkspaceActionsController().linkLastRunToProject(projectId, summary);
  }

  async function _confirmProjectDestructive({ body, actionLabel, actionId, note }) {
    return _projectWorkspaceActionsController().confirmDestructive({ body, actionLabel, actionId, note });
  }

  function _confirmProjectTargetDelete(targetValue) {
    return _projectWorkspaceActionsController().confirmTargetDelete(targetValue);
  }

  function _confirmProjectRunUnlink(runCommand) {
    return _projectWorkspaceActionsController().confirmRunUnlink(runCommand);
  }

  function _confirmProjectPackageDelete(packageName) {
    return _projectWorkspaceActionsController().confirmPackageDelete(packageName);
  }

  function _confirmProjectDelete(projectName) {
    return _projectWorkspaceActionsController().confirmProjectDelete(projectName);
  }

  function _setCachedFindingReviewState(projectId, findingId, reviewState) {
    _projectFindingsDataController().setCachedReviewState(projectId, findingId, reviewState);
  }

  function _updateCachedProjectFinding(projectId, findingId, updates) {
    _projectFindingsDataController().updateCachedFinding(projectId, findingId, updates);
  }

  function _renderUptime() {
    if (!hudUptimeEl) return;
    if (hudState.serverUptime === null) {
      hudUptimeEl.textContent = '—';
      _setValueColor(hudUptimeEl, 'hud-muted');
      return;
    }
    const deltaS = (performance.now() - hudState.serverUptimeAt) / 1000;
    hudUptimeEl.textContent = _formatUptime(hudState.serverUptime + deltaS);
    _setValueColor(hudUptimeEl, null);
  }

  function _renderClock() {
    if (!hudClockEl) return;
    const mode = typeof importedGetHudClockPreference === 'function'
      ? importedGetHudClockPreference()
      : 'utc';
    const now = Date.now();
    hudClockEl.textContent = mode === 'local' ? _formatLocalClock(now) : _formatUtcClock(now);
    if (mode === 'local') {
      try {
        const zone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'browser local time';
        hudClockEl.title = `Clock: local time (${zone}, ${_getLocalClockLabel(new Date(now))})`;
      } catch (_) {
        hudClockEl.title = 'Clock: local time';
      }
    } else {
      hudClockEl.title = 'Clock: UTC';
    }
    _setValueColor(hudClockEl, null);
  }

  function _renderDb() {
    if (!hudDbEl) return;
    if (hudState.db === 'ok') {
      hudDbEl.textContent = 'ONLINE';
      _setValueColor(hudDbEl, 'hud-value-green');
    } else if (hudState.db === 'down') {
      hudDbEl.textContent = 'OFFLINE';
      _setValueColor(hudDbEl, 'hud-value-red');
    } else {
      hudDbEl.textContent = '—';
      _setValueColor(hudDbEl, 'hud-muted');
    }
  }

  function _renderRedis() {
    if (!hudRedisEl) return;
    if (hudState.redis === 'ok') {
      hudRedisEl.textContent = 'ONLINE';
      _setValueColor(hudRedisEl, 'hud-value-green');
      hudRedisEl.title = 'Redis backend is reachable';
    } else if (hudState.redis === 'down') {
      hudRedisEl.textContent = 'OFFLINE';
      _setValueColor(hudRedisEl, 'hud-value-red');
      hudRedisEl.title = 'Redis configured but unreachable';
    } else if (hudState.redis === 'none') {
      hudRedisEl.textContent = 'N/A';
      _setValueColor(hudRedisEl, 'hud-muted');
      hudRedisEl.title = 'Redis not configured — rate limiting and process tracking run in-process';
    } else {
      hudRedisEl.textContent = '—';
      _setValueColor(hudRedisEl, 'hud-muted');
    }
  }

  async function pollHudStatus() {
    const t0 = performance.now();
    try {
      const resp = await fetch('/status', { cache: 'no-store', credentials: 'same-origin' });
      const t1 = performance.now();
      hudState.latencyMs = t1 - t0;
      if (resp.ok) {
        const data = await resp.json();
        if (typeof data.uptime === 'number') {
          hudState.serverUptime = data.uptime;
          hudState.serverUptimeAt = performance.now();
        }
        if (typeof data.db === 'string')    hudState.db = data.db;
        if (typeof data.redis === 'string') hudState.redis = data.redis;
      }
    } catch (_) {
      hudState.latencyMs = null;
      hudState.db = 'down';
      if (hudState.redis !== 'none') hudState.redis = 'down';
    }
    _renderLatency();
    _renderUptime();
    _renderDb();
    _renderRedis();
  }

  function _currentHudStatusPollMs() {
    return document.visibilityState === 'visible'
      ? STATUS_POLL_VISIBLE_MS
      : STATUS_POLL_HIDDEN_MS;
  }

  function _startHudStatusPoll({ pollNow = false } = {}) {
    if (hudStatusPollTimer) clearInterval(hudStatusPollTimer);
    hudStatusPollTimer = setInterval(pollHudStatus, _currentHudStatusPollMs());
    if (pollNow) pollHudStatus();
  }

  // Cross-tab SESSION_ID changes fire the 'storage' event, so refresh there
  // as well as on every poll (cheap) so token rotations reflect immediately.
  window.addEventListener('storage', e => {
    if (e.key === 'session_token') {
      _renderSession();
      loadActiveProjectContext().catch(() => {});
      return;
    }
    if (e.key === PROJECT_WORKSPACE_CONSTANTS.workspaceBroadcastKey && e.newValue) {
      _scheduleProjectWorkspaceExternalRefresh();
    }
  });
  document.addEventListener('visibilitychange', () => {
    _startHudStatusPoll({ pollNow: document.visibilityState === 'visible' });
  });
  window.addEventListener('resize', () => {
    _scheduleProjectFilterSortDividerSync(projectExplorerBody);
  });

  if (_shellFn('onUiEvent', importedOnUiEvent)) {
    _shellOnUiEvent('app:history-rendered', () => {
      try { renderRailRecent(); } catch (_) { /* non-critical */ }
    });
    _shellOnUiEvent('app:workflows-rendered', (e) => {
      try { renderRailWorkflows(e.detail && e.detail.items); } catch (_) { /* non-critical */ }
    });
    _shellOnUiEvent('app:workflows-closed', () => {
      try {
        const renderWorkflowItemsFn = (typeof importedHasWorkflowHandler === 'function' && importedHasWorkflowHandler('renderWorkflowItems'))
          ? importedRenderWorkflowItems
          : _shellFn('renderWorkflowItems');
        renderWorkflowItemsFn?.(allWorkflows);
      } catch (_) { /* non-critical */ }
    });
    _shellOnUiEvent('app:tab-status-changed', () => {
      try { _renderTabs(); } catch (_) { /* non-critical */ }
      try { _renderLastExit(); } catch (_) { /* non-critical */ }
      try { refreshHudActions(); } catch (_) { /* non-critical */ }
    });
    _shellOnUiEvent('app:tab-activated', () => {
      try { _renderLastExit(); } catch (_) { /* non-critical */ }
      try { refreshHudActions(); } catch (_) { /* non-critical */ }
    });
    _shellOnUiEvent('app:tab-created', () => {
      try { _renderTabs(); } catch (_) { /* non-critical */ }
      try { refreshHudActions(); } catch (_) { /* non-critical */ }
    });
    _shellOnUiEvent('app:tab-closed', () => {
      try { _renderTabs(); } catch (_) { /* non-critical */ }
      try { refreshHudActions(); } catch (_) { /* non-critical */ }
    });
    _shellOnUiEvent('app:last-exit-changed', (e) => {
      hudState.lastExit = e.detail ? e.detail.value : null;
      try { _renderLastExit(); } catch (_) { /* non-critical */ }
    });
    _shellOnUiEvent('app:tab-kill-visibility-changed', (e) => {
      const tabId = e.detail && e.detail.tabId;
      const activeId = _shellGetActiveTabId();
      if (tabId !== activeId) return;
      try { _setHudKillVisible(!!(e.detail && e.detail.visible)); } catch (_) { /* non-critical */ }
    });
  }

  // Initial render and pollers.
  _renderLastExit();
  _renderTabs();
  _renderSession();
  _renderClock();
  _renderLatency();
  _renderUptime();
  _renderDb();
  _renderRedis();
  _renderActiveProject();

  _startHudStatusPoll({ pollNow: true });
  setInterval(() => { _renderClock(); _renderUptime(); _renderSession(); }, CLOCK_TICK_MS);

  // ── Init ─────────────────────────────────────────────────────────
  applyCollapsed();
  applyWidth();
  applySectionsState();
  renderRailRecent();
  const ensureWorkflowCatalogLoadedFn = (
    typeof importedHasWorkflowHandler === 'function' && importedHasWorkflowHandler('ensureWorkflowCatalogLoaded')
  ) ? importedEnsureWorkflowCatalogLoaded : _shellFn('ensureWorkflowCatalogLoaded');
  if (ensureWorkflowCatalogLoadedFn) {
    ensureWorkflowCatalogLoadedFn()
      .then(items => renderRailWorkflows(items))
      .catch(() => {});
  }
  refreshHudActions();
  loadActiveProjectContext().catch(() => {});

  document.addEventListener('click', (event) => {
    if (event.target?.closest?.('#project-mobile-new-btn')) {
      event.preventDefault();
      event.stopPropagation();
      _setProjectWorkspaceMessage('');
      _setProjectMobileCreateOpen(true, { focus: true }).catch((err) => {
        _shellLogClientError('failed to open mobile project create form', err);
      });
      return;
    }
    if (event.target?.closest?.('#project-mobile-create-form [data-project-mobile-action="cancel-create"]')) {
      event.preventDefault();
      event.stopPropagation();
      _setProjectWorkspaceMessage('');
      _setProjectMobileCreateOpen(false).catch((err) => {
        _shellLogClientError('failed to close mobile project create form', err);
      });
    }
  }, true);

  // Expose the workflows renderer for controller.js to call after /workflows loads.
  if (typeof importedSetProjectHudHandlers === 'function') {
    importedSetProjectHudHandlers({ renderHudClock: _renderClock });
  }
  if (typeof importedSetProjectContextHandlers === 'function') {
    importedSetProjectContextHandlers({
      closeProjectWorkspace,
      cycleProjectWorkspaceTab,
      getActiveProjectContext: _activeProject,
      isProjectWorkspaceOpen,
      openEntityMetadataEditor,
      openProjectAutoPromoteRuleFromAtlas,
      openProjectWorkspace,
      refreshActiveProjectContext: loadActiveProjectContext,
      refreshProjectWorkspace,
    });
  }
  if (typeof importedSetControllerActionHandlers === 'function') {
    importedSetControllerActionHandlers({ toggleRailCollapsed });
  }

})(globalThis);
