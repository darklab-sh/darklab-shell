// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Session Entity Atlas overlay controller.
import {
  copyTextToClipboard as importedCopyTextToClipboard,
  downloadBlobAsAttachment as importedDownloadBlobAsAttachment,
  showToast as importedShowToast,
} from '../../core/utils.js';
import { closeMajorOverlays as importedCloseMajorOverlays } from '../../ui/overlay_actions_bridge.js';
import { bindMobileSheet as importedBindMobileSheet } from '../../ui/mobile_sheet.js';
import { bindDismissible as importedBindDismissible } from '../../ui/ui_dismissible.js';
import { bindFocusTrap as importedBindFocusTrap } from '../../ui/ui_focus_trap.js';
import {
  blurVisibleComposerInputIfMobile as importedBlurVisibleComposerInputIfMobile,
  markInteractionSurfaceReady as importedMarkInteractionSurfaceReady,
  portalDropdownMenu as importedPortalDropdownMenu,
  refocusComposerAfterAction as importedRefocusComposerAfterAction,
  setComposerValue as importedSetComposerValue,
  syncAppSelect as importedSyncAppSelect,
  syncModalOverlayState as importedSyncModalOverlayState,
  unportalDropdownMenu as importedUnportalDropdownMenu,
} from '../../ui/ui_helpers.js';
import { DarklabEntityMetadata as importedEntityMetadata } from '../../ui/ui_entity_metadata.js';
import { bindOutsideClickClose as importedBindOutsideClickClose } from '../../ui/ui_outside_click.js';
import { showConfirm as importedShowConfirm } from '../../ui/ui_confirm.js';
import { bindDisclosure as importedBindDisclosure } from '../../ui/ui_disclosure.js';
import {
  atlasRunCleanupCopy as importedAtlasRunCleanupCopy,
  cleanupSampleDetails as importedCleanupSampleDetails,
} from '../../ui/cleanup_reasons.js';
import { emitUiEvent as importedEmitUiEvent } from '../../core/state.js';
import { apiFetch as importedApiFetch, logClientError as importedLogClientError } from '../../session.js';
import { openFindingsBoard as importedOpenFindingsBoard } from '../findings/findings_board_bridge.js';
import { openHistoryRunDetails as importedOpenHistoryRunDetails } from '../history/history_run_modal_state_bridge.js';
import { DarklabFindingTriageEditor as importedFindingTriageEditor } from '../findings/finding_triage_bridge.js';
import { openContextualFindingRecord as importedOpenContextualFindingRecord } from '../findings/finding_record_context.js';
import { findingRiskSummary as importedFindingRiskSummary } from '../findings/finding_risk.js';
import {
  DarklabTeamScope as importedTeamScope,
  activeTeamScopeCan as importedActiveTeamScopeCan,
  teamScopeDeniedMessage as importedTeamScopeDeniedMessage,
} from '../team_scope.js';
import { DarklabAtlasEntityRow as importedAtlasEntityRow } from './atlas_entity_row.js';
import {
  createAtlasQuickLookupMode as importedCreateAtlasQuickLookupMode,
  quickLookupElements as importedQuickLookupElements,
  quickLookupScope as importedQuickLookupScope,
} from './atlas_quick_lookup_mode.js';
import { DarklabAtlasTabs as importedAtlasTabs } from './atlas_tabs.js';
import {
  loadAtlasMobile as importedLoadAtlasMobile,
  resetAtlasMobileTransientState as importedResetAtlasMobileTransientState,
} from './atlas_mobile_bridge.js';
import {
  getActiveProjectContext as importedGetActiveProjectContext,
  openProjectAutoPromoteRuleFromAtlas as importedOpenProjectAutoPromoteRuleFromAtlas,
  openProjectWorkspaceById as importedOpenProjectWorkspaceById,
  refreshActiveProjectContext as importedRefreshActiveProjectContext,
} from '../projects/project_context_bridge.js';

import {
  getAtlasDetailController as importedGetAtlasDetailController,
  loadAtlasDetail as importedLoadAtlasDetail,
  setAtlasHandlers as importedSetAtlasHandlers,
} from './atlas_bridge.js';

let exportedDarklabAtlasOverlay = null;
let exportedOpenAtlas = null;
let exportedOpenAtlasQuickLookup = null;
let exportedCloseAtlas = null;
let exportedIsAtlasOverlayOpen = null;
let exportedRefreshAtlasOverlay = null;
let exportedCycleAtlasTab = null;

(function initAtlasOverlay(global) {
  const tabsApi = (typeof importedAtlasTabs !== 'undefined' && importedAtlasTabs) || {};
  const fallbackAtlasTabs = [
    { id: 'findings', type: '', label: 'Findings' },
    { id: 'ip', type: 'ip', label: 'IPs' },
    { id: 'domain', type: 'domain', label: 'Domains' },
    { id: 'hash', type: 'hash', label: 'Hashes' },
    { id: 'cve', type: 'cve', label: 'CVEs' },
    { id: 'url', type: 'url', label: 'URLs' },
  ];
  const detailApi = {};
  const entityRowApi = (typeof importedAtlasEntityRow !== 'undefined' && importedAtlasEntityRow) || {};
  const findingTriageEditor = (typeof importedFindingTriageEditor !== 'undefined' && importedFindingTriageEditor) || null;
  const metadataApi = (typeof importedEntityMetadata !== 'undefined' && importedEntityMetadata) || {};
  const summarizeFindingRisk = typeof importedFindingRiskSummary === 'function'
    ? importedFindingRiskSummary
    : () => '';
  const teamScope = (typeof importedTeamScope !== 'undefined' && importedTeamScope)
    || {
      activeTeamScopeCan: (typeof importedActiveTeamScopeCan !== 'undefined' && importedActiveTeamScopeCan)
        || null,
      deniedMessage: (typeof importedTeamScopeDeniedMessage !== 'undefined' && importedTeamScopeDeniedMessage)
        || null,
    };
  const bindDismissible = (typeof importedBindDismissible !== 'undefined' && importedBindDismissible) || null;
  const bindFocusTrap = (typeof importedBindFocusTrap !== 'undefined' && importedBindFocusTrap) || null;
  const bindMobileSheet = (typeof importedBindMobileSheet !== 'undefined' && importedBindMobileSheet) || null;
  const bindOutsideClickClose = (typeof importedBindOutsideClickClose !== 'undefined' && importedBindOutsideClickClose) || null;
  const atlasRunCleanupCopy = (typeof importedAtlasRunCleanupCopy !== 'undefined' && importedAtlasRunCleanupCopy) || null;
  const cleanupSampleDetails = (typeof importedCleanupSampleDetails !== 'undefined' && importedCleanupSampleDetails) || null;
  const bindDisclosure = (typeof importedBindDisclosure !== 'undefined' && importedBindDisclosure) || null;
  const blurVisibleComposerInputIfMobile = (typeof importedBlurVisibleComposerInputIfMobile !== 'undefined' && importedBlurVisibleComposerInputIfMobile) || null;
  const copyTextToClipboard = (typeof importedCopyTextToClipboard !== 'undefined' && importedCopyTextToClipboard) || null;
  const downloadBlobAsAttachment = (typeof importedDownloadBlobAsAttachment !== 'undefined' && importedDownloadBlobAsAttachment) || null;
  const markInteractionSurfaceReady = (typeof importedMarkInteractionSurfaceReady !== 'undefined' && importedMarkInteractionSurfaceReady) || null;
  const openContextualFindingRecord = (
    typeof importedOpenContextualFindingRecord !== 'undefined'
    && importedOpenContextualFindingRecord
  ) || null;
  const portalDropdownMenu = (typeof importedPortalDropdownMenu !== 'undefined' && importedPortalDropdownMenu) || null;
  const refocusComposerAfterAction = (typeof importedRefocusComposerAfterAction !== 'undefined' && importedRefocusComposerAfterAction) || null;
  const setComposerValue = (typeof importedSetComposerValue !== 'undefined' && importedSetComposerValue) || null;
  const showConfirm = (typeof importedShowConfirm !== 'undefined' && importedShowConfirm) || null;
  const showToast = (typeof importedShowToast !== 'undefined' && importedShowToast) || null;
  const syncAppSelect = (typeof importedSyncAppSelect !== 'undefined' && importedSyncAppSelect) || null;
  const syncModalOverlayState = (typeof importedSyncModalOverlayState !== 'undefined' && importedSyncModalOverlayState) || null;
  const unportalDropdownMenu = (typeof importedUnportalDropdownMenu !== 'undefined' && importedUnportalDropdownMenu) || null;

  const overlay = document.getElementById('atlas-overlay');
  const surface = document.getElementById('atlas-surface');
  const shell = surface?.querySelector?.('.atlas-shell') || document.querySelector('.atlas-shell');
  const closeBtn = document.querySelector('.atlas-close');
  const tabsHost = document.getElementById('atlas-tabs');
  const subtitle = document.getElementById('atlas-subtitle');
  const lookupElements = importedQuickLookupElements?.(document) || {};
  const searchInput = document.getElementById('atlas-search');
  const runFilterSearch = document.getElementById('atlas-run-filter-search');
  const runFilterSelect = document.getElementById('atlas-run-filter-select');
  const runFilterChip = document.getElementById('atlas-run-filter-chip');
  const projectFilterSelect = document.getElementById('atlas-project-filter-select');
  const projectFilterChip = document.getElementById('atlas-project-filter-chip');
  const findingStatusFilter = document.getElementById('atlas-finding-status-filter');
  const orphanFilter = document.getElementById('atlas-orphan-filter');
  const suppressionFilter = document.getElementById('atlas-suppression-filter');
  const savedViewSelect = document.getElementById('atlas-saved-view-select');
  const savedViewSaveBtn = document.getElementById('atlas-saved-view-save');
  const savedViewUpdateBtn = document.getElementById('atlas-saved-view-update');
  const savedViewDeleteBtn = document.getElementById('atlas-saved-view-delete');
  const savedViewCreateRuleBtn = document.getElementById('atlas-saved-view-create-rule');
  const exportWrap = document.getElementById('atlas-export-wrap');
  const exportMenuBtn = document.getElementById('atlas-export-menu-btn');
  const exportMenu = document.getElementById('atlas-export-menu');
  const exportCsvBtn = document.getElementById('atlas-export-csv-btn');
  const exportJsonlBtn = document.getElementById('atlas-export-jsonl-btn');
  const importBtn = document.getElementById('atlas-import-btn');
  const importOverlay = document.getElementById('atlas-import-overlay');
  const importModal = document.getElementById('atlas-import-modal');
  const importCloseBtn = document.getElementById('atlas-import-close');
  const importCancelBtn = document.getElementById('atlas-import-cancel');
  const importFormatSelect = document.getElementById('atlas-import-format');
  const importNameInput = document.getElementById('atlas-import-name');
  const importFileInput = document.getElementById('atlas-import-file');
  const importPreviewBtn = document.getElementById('atlas-import-preview-btn');
  const importStatus = document.getElementById('atlas-import-status');
  const importPreviewHost = document.getElementById('atlas-import-preview');
  const importApplyBtn = document.getElementById('atlas-import-apply');
  const refreshBtn = document.getElementById('atlas-refresh-btn');
  const findingsBoardBtn = document.getElementById('atlas-findings-board-btn');
  const clearFiltersBtn = document.getElementById('atlas-clear-filters-btn');
  const findingBulkRow = document.getElementById('atlas-finding-bulk-row');
  const selectToggle = document.getElementById('atlas-select-toggle');
  const findingSelectionSummary = document.getElementById('atlas-finding-selection-summary');
  const findingSelectAllBtn = document.getElementById('atlas-finding-select-all');
  const findingClearSelectionBtn = document.getElementById('atlas-finding-clear-selection');
  const findingBulkStatus = document.getElementById('atlas-finding-bulk-status');
  const findingBulkApplyBtn = document.getElementById('atlas-finding-bulk-apply');
  const bulkSuppressionBtn = document.getElementById('atlas-bulk-suppression');
  const bulkDeleteBtn = document.getElementById('atlas-bulk-delete');
  const listHost = document.getElementById('atlas-list');
  const detailHost = document.getElementById('atlas-detail');
  const pagination = document.getElementById('atlas-pagination');
  const paginationSummary = document.getElementById('atlas-pagination-summary');
  const prevBtn = document.getElementById('atlas-prev-btn');
  const nextBtn = document.getElementById('atlas-next-btn');
  const importAcceptByFormat = {
    burp_xml: '.xml,application/xml,text/xml',
    generic_csv: '.csv,text/csv',
    generic_jsonl: '.jsonl,application/x-ndjson,application/jsonl,application/json',
    nessus_xml: '.nessus,.xml,application/xml,text/xml',
    nuclei_jsonl: '.jsonl,application/x-ndjson,application/jsonl,application/json',
    zap_json: '.json,application/json',
    zap_xml: '.xml,application/xml,text/xml',
  };

  function ensureBulkActionLayout() {
    const row = findingBulkRow?.querySelector?.('.atlas-bulk-action-row');
    if (!row) return;
    let selectionControls = row.querySelector('.atlas-bulk-selection-controls');
    if (!selectionControls) {
      selectionControls = document.createElement('div');
      selectionControls.className = 'atlas-bulk-selection-controls';
      row.prepend(selectionControls);
    }
    let mutationControls = row.querySelector('.atlas-bulk-mutation-controls');
    if (!mutationControls) {
      mutationControls = document.createElement('div');
      mutationControls.className = 'atlas-bulk-mutation-controls';
      row.appendChild(mutationControls);
    }
    const selectControl = selectToggle?.closest?.('label') || selectToggle;
    [
      selectControl,
      findingSelectAllBtn,
      findingClearSelectionBtn,
      findingSelectionSummary,
    ].forEach((el) => {
      if (el && el.parentElement !== selectionControls) selectionControls.appendChild(el);
    });
    [
      findingBulkStatus,
      findingBulkApplyBtn,
      bulkSuppressionBtn,
      bulkDeleteBtn,
    ].forEach((el) => {
      if (el && el.parentElement !== mutationControls) mutationControls.appendChild(el);
    });
  }

  const state = {
    activeTab: 'findings',
    summary: null,
    baseSummary: null,
    entities: [],
    findings: [],
    findingCounts: {},
    selectedFindingId: '',
    selectedFindingIds: new Set(),
    selectedEntityIds: new Set(),
    selectMode: false,
    bulkInFlight: false,
    findingStatus: '',
    orphanFilter: 'hide',
    suppressionFilter: 'hide',
    total: 0,
    totalExact: true,
    hasMore: false,
    limit: 50,
    offset: 0,
    query: '',
    projectId: '',
    projectName: '',
    launchProjectId: '',
    launchProjectName: '',
    projectOptions: [],
    projectOptionsLoaded: false,
    projectOptionsLoading: false,
    runId: '',
    runLabel: '',
    runOptions: [],
    runOptionsLoaded: false,
    runOptionsLoading: false,
    runOptionsQuery: '',
    runSearchTimer: null,
    savedViews: [],
    selectedSavedViewId: '',
    savedViewsLoaded: false,
    savedViewsLoading: false,
    loading: false,
    selectedId: '',
    requestedEntityValue: '',
    requestedFindingId: '',
    requestedView: '',
    requestedViewStarted: 0,
    refreshIntelOnSelect: false,
    addActiveProjectOnSelect: false,
    detail: null,
    detailFinding: null,
    detailFindingReturnScroll: { profile: 0, findingId: '' },
    entityProfileMode: false,
    entityProfileView: 'overview',
    entityProfileFindingBucket: 'direct',
    entityProfileStack: [],
    entityProfileReturnScroll: { list: 0, detail: 0 },
    detailLoading: false,
    intelRefreshing: false,
    intelRefreshingEntityId: '',
    intelRefreshingLabel: '',
    detailOffsets: { runs: 0, findings: 0, related_urls: 0, related_ports: 0 },
    importFlow: {
      open: false,
      previewLoading: false,
      applyLoading: false,
      draftId: '',
      rowSetDigest: '',
      preview: null,
      result: null,
    },
    searchTimer: null,
    refreshSeq: 0,
    lookupMode: false,
  };

  function api() {
    if (typeof importedApiFetch === 'function') return importedApiFetch;
    return fetch;
  }

  let atlasLoadController = null;
  let detailLoadController = null;
  let quickLookupController = null;
  let detailApiPromise = null;
  let detailApiErrorLogged = false;
  let mobileApiPromise = null;

  function isAbortError(err) {
    return err && (err.name === 'AbortError' || err.code === 20);
  }

  function newAbortController() {
    if (typeof global.AbortController !== 'function') return null;
    return new global.AbortController();
  }

  function requestOptions(controller, extra = {}) {
    if (controller && controller.signal) return { ...extra, signal: controller.signal };
    return extra;
  }

  function mergeDetailApi(api) {
    const next = (api && api.DarklabAtlasDetail) || api || null;
    if (!next || typeof next !== 'object') return detailApi;
    Object.keys(next).forEach((key) => {
      detailApi[key] = next[key];
    });
    return detailApi;
  }

  function currentDetailApi() {
    if (typeof importedGetAtlasDetailController === 'function') {
      mergeDetailApi(importedGetAtlasDetailController());
    }
    return detailApi;
  }

  function ensureDetailApi({ renderOnReady = true } = {}) {
    if (currentDetailApi().renderDetail && currentDetailApi().renderFindingDetail) {
      return Promise.resolve(detailApi);
    }
    if (!detailApiPromise) {
      detailApiPromise = Promise.resolve()
        .then(() => (typeof importedLoadAtlasDetail === 'function' ? importedLoadAtlasDetail() : null))
        .then((api) => mergeDetailApi(api))
        .catch((err) => {
          if (!detailApiErrorLogged) {
            detailApiErrorLogged = true;
            logImportClientError('failed to load atlas detail renderer', err);
          }
          throw err;
        })
        .finally(() => {
          detailApiPromise = null;
        });
    }
    if (renderOnReady) {
      detailApiPromise
        .then(() => {
          if (isOpen()) {
            if (state.lookupMode) render();
            else renderDetail();
          }
        })
        .catch(() => {});
    }
    return detailApiPromise;
  }

  function renderDetailMessage(message) {
    if (!detailHost) return;
    const empty = document.createElement('div');
    empty.className = 'atlas-empty-inline';
    empty.textContent = message;
    detailHost.replaceChildren(empty);
  }

  function isAtlasMobileMode() {
    return !!(document.body && document.body.classList.contains('mobile-terminal-mode'));
  }

  function activeEntityDetailHost() {
    if (state.lookupMode && quickLookupController?.profileHost) {
      return quickLookupController.profileHost;
    }
    if (isAtlasMobileMode()) {
      return document.getElementById('atlas-mobile-entity-body');
    }
    return detailHost;
  }

  function activeEntityProfileBackControl() {
    if (!state.lookupMode && isAtlasMobileMode()) {
      return document.querySelector?.('#atlas-mobile-entity-topbar .atlas-mobile-back-btn') || null;
    }
    return activeEntityDetailHost()?.querySelector?.('.atlas-profile-back') || null;
  }

  function focusActiveEntityProfileBackControl() {
    window.setTimeout(() => {
      activeEntityProfileBackControl()?.focus?.({ preventScroll: true });
    }, 0);
  }

  function ensureMobileAtlasIfNeeded() {
    if (state.lookupMode || !isOpen() || !isAtlasMobileMode() || typeof importedLoadAtlasMobile !== 'function') return;
    if (!mobileApiPromise) {
      mobileApiPromise = importedLoadAtlasMobile()
        .catch((err) => {
          logImportClientError('failed to load atlas mobile controller', err);
          throw err;
        })
        .finally(() => {
          mobileApiPromise = null;
        });
    }
  }

  function abortAtlasLoad() {
    if (atlasLoadController) atlasLoadController.abort();
    atlasLoadController = null;
  }

  function abortDetailLoad() {
    if (detailLoadController) detailLoadController.abort();
    detailLoadController = null;
  }

  function abortReadRequests() {
    abortAtlasLoad();
    abortDetailLoad();
  }

  function showToastSafe(message, tone = 'info') {
    if (typeof showToast === 'function') showToast(message, tone);
  }

  function activeTeamScopeCan(capability) {
    return teamScope && typeof teamScope.activeTeamScopeCan === 'function'
      ? teamScope.activeTeamScopeCan(capability)
      : true;
  }

  function teamScopeDeniedMessage(action) {
    return teamScope && typeof teamScope.deniedMessage === 'function'
      ? teamScope.deniedMessage(action)
      : `View-only team members can't ${action}. Switch to Personal or ask for operator access.`;
  }

  function canTriageAtlasRows() {
    return activeTeamScopeCan('triage_findings');
  }

  function canDeleteAtlasRows() {
    return canTriageAtlasRows();
  }

  function showAtlasPermissionDenied(action = 'delete Atlas rows') {
    showToastSafe(teamScopeDeniedMessage(action), 'error');
  }

  async function atlasMutationError(resp, fallback, action = 'delete Atlas rows') {
    let message = fallback;
    try {
      const data = typeof resp.json === 'function' ? await resp.json() : {};
      if (data && data.error === 'team_forbidden') message = teamScopeDeniedMessage(action);
      else if (data && typeof data.message === 'string' && data.message.trim()) message = data.message.trim();
      else if (data && typeof data.error === 'string' && data.error.trim()) message = data.error.trim();
    } catch (_) {}
    const err = new Error(message || fallback);
    err.atlasHandledClientHttpError = Number(resp?.status || 0) >= 400 && Number(resp?.status || 0) < 500;
    return err;
  }

  function logImportClientError(message, err, details) {
    if (err && err.atlasHandledClientHttpError) return;
    if (typeof importedLogClientError !== 'function') return;
    if (details === undefined) importedLogClientError(message, err);
    else importedLogClientError(message, err, details);
  }

  let intelRefreshOverlay = null;

  function entityLabelForId(entityId) {
    const id = String(entityId || '');
    const detailEntity = state.detail?.entity || null;
    if (id && detailEntity && String(detailEntity.id || '') === id) {
      return text(detailEntity.canonical_value, detailEntity.value || detailEntity.id);
    }
    const listed = (state.entities || []).find(entity => String(entity.id || '') === id);
    if (listed) return text(listed.canonical_value, listed.value || listed.id);
    return '';
  }

  function ensureIntelRefreshOverlay() {
    if (intelRefreshOverlay || !overlay) return intelRefreshOverlay;
    const host = document.createElement('div');
    host.className = 'atlas-intel-refresh-overlay u-hidden';
    host.setAttribute('role', 'status');
    host.setAttribute('aria-live', 'polite');
    host.setAttribute('aria-hidden', 'true');
    const card = document.createElement('div');
    card.className = 'atlas-intel-refresh-card';
    const spinner = document.createElement('div');
    spinner.className = 'atlas-intel-refresh-spinner';
    spinner.setAttribute('aria-hidden', 'true');
    const copy = document.createElement('div');
    const title = document.createElement('div');
    title.className = 'atlas-intel-refresh-title';
    title.textContent = 'Refreshing intel';
    const body = document.createElement('div');
    body.className = 'atlas-intel-refresh-body';
    body.dataset.atlasIntelRefreshBody = 'true';
    body.textContent = 'Querying configured intel providers. This can take a little while.';
    copy.append(title, body);
    card.append(spinner, copy);
    host.appendChild(card);
    overlay.appendChild(host);
    intelRefreshOverlay = host;
    return intelRefreshOverlay;
  }

  function renderIntelRefreshOverlay() {
    const host = ensureIntelRefreshOverlay();
    if (!host) return;
    surface?.setAttribute('aria-busy', state.intelRefreshing ? 'true' : 'false');
    host.classList.toggle('u-hidden', !state.intelRefreshing);
    host.setAttribute('aria-hidden', state.intelRefreshing ? 'false' : 'true');
    if (!state.intelRefreshing) return;
    const body = host.querySelector('[data-atlas-intel-refresh-body]');
    if (body) {
      const label = String(state.intelRefreshingLabel || '').trim();
      body.textContent = label
        ? `Querying configured intel providers for ${label}. This can take a little while.`
        : 'Querying configured intel providers. This can take a little while.';
    }
  }

  function broadcastProjectWorkspaceChange(reason, projectId) {
    const payload = {
      reason: String(reason || 'updated'),
      project_id: String(projectId || ''),
      changed_at: Date.now(),
    };
    if (typeof importedEmitUiEvent === 'function') {
      importedEmitUiEvent('app:project-workspace-changed', payload);
      importedEmitUiEvent('app:project-workspace-mutated', payload);
    }
    try {
      if (typeof localStorage !== 'undefined' && localStorage && typeof localStorage.setItem === 'function') {
        localStorage.setItem('darklab_project_workspace_changed', JSON.stringify(payload));
      }
    } catch (_) {
      // Cross-tab refresh is best-effort; the local Atlas refresh still completes.
    }
  }

  function text(value, fallback = '') {
    return detailApi.text ? detailApi.text(value, fallback) : (String(value ?? '').trim() || fallback);
  }

  function selectorValue(value) {
    if (typeof CSS !== 'undefined' && CSS && typeof CSS.escape === 'function') {
      return CSS.escape(String(value));
    }
    return String(value || '').replace(/["\\]/g, '\\$&');
  }

  function countLabel(count, singular, plural) {
    const numeric = Number(count || 0);
    return `${numeric.toLocaleString()} ${numeric === 1 ? singular : plural}`;
  }

  function node(tag, className = '', content = '') {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (content !== '') el.textContent = String(content);
    return el;
  }

  const findingStates = [
    ['new', 'New'],
    ['reviewed', 'Reviewed'],
    ['important', 'Important'],
    ['false_positive', 'False positive'],
    ['needs_followup', 'Follow-up'],
  ];

  function isOpen() {
    return !!(overlay && overlay.classList.contains('open'));
  }

  function show() {
    if (!overlay) return;
    overlay.classList.remove('u-hidden');
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
    if (typeof syncModalOverlayState === 'function') syncModalOverlayState();
  }

  function hide({ refocus = true } = {}) {
    if (!overlay) return;
    abortReadRequests();
    setExportMenuOpen(false);
    if (state.importFlow.open) setImportModalOpen(false);
    resetSelection({ selectMode: false, render: false });
    overlay.classList.add('u-hidden');
    overlay.classList.remove('open');
    overlay.setAttribute('aria-hidden', 'true');
    if (typeof syncModalOverlayState === 'function') syncModalOverlayState();
    if (refocus && typeof refocusComposerAfterAction === 'function') {
      refocusComposerAfterAction({ defer: true });
    }
  }

  function currentLookupScope(options = {}) {
    return importedQuickLookupScope?.({ options, teamScope })
      || { kind: 'personal', id: '', projectId: '', label: 'Personal' };
  }

  function cloneEntityProfileSnapshot(snapshot = {}) {
    return {
      ...snapshot,
      selectedFindingIds: new Set(snapshot.selectedFindingIds || []),
      selectedEntityIds: new Set(snapshot.selectedEntityIds || []),
      detailOffsets: { ...(snapshot.detailOffsets || {}) },
      entityProfileReturnScroll: { ...(snapshot.entityProfileReturnScroll || {}) },
      scroll: { ...(snapshot.scroll || {}) },
    };
  }

  function captureQuickLookupReturnState() {
    const lookupState = quickLookupController?.state || {};
    return {
      lookup: {
        root: String(lookupState.root || 'form'),
        rawDraft: String(lookupState.rawDraft || ''),
        selectedMode: String(lookupState.selectedMode || 'auto'),
        submittedRawValue: String(lookupState.submittedRawValue || ''),
        submittedMode: String(lookupState.submittedMode || 'auto'),
        submittedCanonicalValue: String(lookupState.submittedCanonicalValue || ''),
        result: lookupState.result || null,
        launchScope: { ...(lookupState.launchScope || {}) },
      },
      atlas: {
        activeTab: state.activeTab,
        projectId: state.projectId,
        projectName: state.projectName,
        selectedId: state.selectedId,
        selectedFindingId: state.selectedFindingId,
        detail: state.detail,
        detailFinding: state.detailFinding,
        detailFindingReturnScroll: { ...(state.detailFindingReturnScroll || {}) },
        detailOffsets: { ...(state.detailOffsets || {}) },
        entityProfileView: state.entityProfileView,
        entityProfileFindingBucket: state.entityProfileFindingBucket,
        entityProfileReturnScroll: { ...(state.entityProfileReturnScroll || {}) },
        entityProfileStack: state.entityProfileStack.map(cloneEntityProfileSnapshot),
      },
    };
  }

  async function restoreQuickLookupReturnState(snapshot = {}) {
    const lookupSnapshot = snapshot.lookup && typeof snapshot.lookup === 'object'
      ? snapshot.lookup
      : null;
    const atlasSnapshot = snapshot.atlas && typeof snapshot.atlas === 'object'
      ? snapshot.atlas
      : null;
    if (!lookupSnapshot || !atlasSnapshot || typeof quickLookupController?.restore !== 'function') return false;
    quickLookupController.restore(lookupSnapshot);
    const detail = atlasSnapshot.detail || lookupSnapshot.result?.detail || null;
    state.activeTab = String(atlasSnapshot.activeTab || detail?.entity?.type || state.activeTab);
    state.projectId = String(atlasSnapshot.projectId || '');
    state.projectName = String(atlasSnapshot.projectName || '').trim();
    state.launchProjectId = state.projectId;
    state.launchProjectName = state.projectName;
    state.selectedId = String(atlasSnapshot.selectedId || detail?.entity?.id || '');
    state.selectedFindingId = String(atlasSnapshot.selectedFindingId || '');
    state.detail = detail;
    state.detailFinding = atlasSnapshot.detailFinding || null;
    state.detailFindingReturnScroll = { ...(atlasSnapshot.detailFindingReturnScroll || {}) };
    state.detailOffsets = { ...(atlasSnapshot.detailOffsets || state.detailOffsets) };
    state.entityProfileMode = String(lookupSnapshot.root || '') === 'profile' && !!detail;
    state.entityProfileView = ['overview', 'evidence', 'findings', 'intel']
      .includes(String(atlasSnapshot.entityProfileView || ''))
      ? String(atlasSnapshot.entityProfileView)
      : 'overview';
    state.entityProfileFindingBucket = ['direct', 'related_urls', 'related_ports', 'combined']
      .includes(String(atlasSnapshot.entityProfileFindingBucket || ''))
      ? String(atlasSnapshot.entityProfileFindingBucket)
      : 'direct';
    state.entityProfileReturnScroll = { ...(atlasSnapshot.entityProfileReturnScroll || {}) };
    state.entityProfileStack = Array.isArray(atlasSnapshot.entityProfileStack)
      ? atlasSnapshot.entityProfileStack.map(cloneEntityProfileSnapshot)
      : [];
    if (detail) quickLookupController.syncProfileDetail?.(detail);
    await ensureDetailApi({ renderOnReady: false }).catch(() => null);
    render();
    return true;
  }

  function resetAtlasDetailState() {
    state.selectedId = '';
    state.selectedFindingId = '';
    state.detailOffsets = { runs: 0, findings: 0, related_urls: 0, related_ports: 0 };
    resetSelection({ selectMode: false, render: false });
    state.detail = null;
    state.detailFinding = null;
    state.entityProfileStack = [];
    state.entityProfileReturnScroll = { list: 0, detail: 0 };
  }

  async function openAtlasQuickLookup(options = {}) {
    if (!quickLookupController) return false;
    if (options.toggle && state.lookupMode && isOpen()) {
      closeAtlas();
      return false;
    }
    if (typeof importedCloseMajorOverlays === 'function') importedCloseMajorOverlays({ skipAtlas: true });
    if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
    abortReadRequests();
    state.lookupMode = true;
    state.projectId = String(options.projectId || '');
    state.projectName = String(options.projectName || '').trim();
    state.launchProjectId = state.projectId;
    state.launchProjectName = state.projectName;
    state.runId = '';
    state.runLabel = '';
    state.query = '';
    state.requestedEntityValue = '';
    state.requestedFindingId = '';
    state.requestedView = '';
    state.requestedViewStarted = 0;
    state.entityProfileMode = false;
    state.entityProfileView = 'overview';
    state.entityProfileFindingBucket = 'direct';
    state.refreshIntelOnSelect = false;
    state.addActiveProjectOnSelect = false;
    resetAtlasDetailState();
    if (typeof importedResetAtlasMobileTransientState === 'function') importedResetAtlasMobileTransientState();
    show();
    if (typeof markInteractionSurfaceReady === 'function') {
      markInteractionSurfaceReady('atlas', overlay, surface);
    }
    render();
    if (options.lookupReturnState && typeof options.lookupReturnState === 'object') {
      return restoreQuickLookupReturnState(options.lookupReturnState);
    }
    return quickLookupController.activate({
      value: String(options.value || options.entityValue || ''),
      mode: String(options.mode || 'auto'),
      scope: currentLookupScope(options),
      submit: !!options.submit,
    });
  }

  async function openAtlas(options = {}) {
    if (options && (options.launchMode === 'lookup' || options.quickLookup === true)) {
      return openAtlasQuickLookup(options);
    }
    if (typeof importedCloseMajorOverlays === 'function') importedCloseMajorOverlays({ skipAtlas: true });
    if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
    quickLookupController?.deactivate?.();
    state.lookupMode = false;
    if (options && options.tab) state.activeTab = tabsApi.tabById?.(options.tab)?.id || state.activeTab;
    state.projectId = String(options && options.projectId || '');
    state.projectName = String(options && options.projectName || '').trim();
    if (['hide', 'all', 'only'].includes(String(options && options.orphanFilter || ''))) {
      state.orphanFilter = String(options.orphanFilter);
    }
    if (['hide', 'all', 'only'].includes(String(options && options.suppressionFilter || ''))) {
      state.suppressionFilter = String(options.suppressionFilter);
    }
    state.launchProjectId = state.projectId;
    state.launchProjectName = state.projectName;
    state.runId = String(options && options.runId || '').trim();
    state.runLabel = String(options && options.runLabel || '').trim();
    state.runOptionsQuery = '';
    state.requestedEntityValue = String(options && options.entityValue || '').trim();
    state.requestedFindingId = String(options && options.findingId || '').trim();
    state.requestedView = ['detail', 'list', 'profile'].includes(String(options && options.forceView || ''))
      ? String(options.forceView)
      : 'list';
    state.requestedViewStarted = ['detail', 'profile'].includes(state.requestedView) ? Date.now() : 0;
    state.entityProfileMode = state.requestedView === 'profile';
    state.entityProfileView = ['overview', 'evidence', 'findings', 'intel'].includes(String(options && options.profileView || ''))
      ? String(options.profileView)
      : 'overview';
    state.entityProfileFindingBucket = ['direct', 'related_urls', 'related_ports', 'combined']
      .includes(String(options && options.findingBucket || ''))
      ? String(options.findingBucket)
      : 'direct';
    state.entityProfileStack = [];
    state.entityProfileReturnScroll = { list: 0, detail: 0 };
    state.refreshIntelOnSelect = !!(options && options.refreshIntel);
    state.addActiveProjectOnSelect = !!(options && options.addActiveProject);
    if (state.requestedEntityValue) {
      state.query = state.requestedEntityValue;
      if (searchInput) searchInput.value = state.query;
    } else {
      state.query = '';
      if (searchInput) searchInput.value = '';
    }
    state.selectedId = String(options && options.entityId || '').trim();
    state.selectedFindingId = '';
    state.detailOffsets = { runs: 0, findings: 0, related_urls: 0, related_ports: 0 };
    resetSelection({ selectMode: false, render: false });
    state.detail = null;
    state.detailFinding = null;
    if (typeof importedResetAtlasMobileTransientState === 'function') importedResetAtlasMobileTransientState();
    show();
    if (typeof markInteractionSurfaceReady === 'function') {
      markInteractionSurfaceReady('atlas', overlay, surface);
    }
    ensureMobileAtlasIfNeeded();
    render();
    loadSavedViews().catch((err) => {
      logImportClientError('failed to load atlas saved views', err);
    });
    loadRunOptions().catch((err) => {
      logImportClientError('failed to load atlas run filters', err);
    });
    loadProjectOptions().catch((err) => {
      logImportClientError('failed to load atlas project filters', err);
    });
    await refreshAtlas({ resetOffset: true, initialLoad: options.initialLoad });
  }

  function closeAtlas(options = {}) {
    state.requestedView = '';
    state.requestedViewStarted = 0;
    quickLookupController?.deactivate?.();
    state.lookupMode = false;
    hide(options);
  }

  function currentTab() {
    if (tabsApi.tabById) return tabsApi.tabById(state.activeTab);
    const tabs = Array.isArray(tabsApi.tabs) && tabsApi.tabs.length ? tabsApi.tabs : fallbackAtlasTabs;
    return tabs.find(tab => String(tab.id || '') === String(state.activeTab || '')) || tabs[0];
  }

  function visibleActiveTab() {
    const activeTabId = tabsHost
      ?.querySelector('[data-atlas-tab].is-active, [data-atlas-tab][aria-selected="true"]')
      ?.dataset
      ?.atlasTab;
    if (activeTabId && tabsApi.tabById) return tabsApi.tabById(activeTabId);
    return currentTab();
  }

  function activeSelectionSet(tab = currentTab()) {
    return tab.id === 'findings' ? state.selectedFindingIds : state.selectedEntityIds;
  }

  function visibleSelectableItems(tab = currentTab()) {
    return tab.id === 'findings' ? state.findings : state.entities;
  }

  function resetSelection({ selectMode = state.selectMode, render = true } = {}) {
    state.selectMode = !!selectMode;
    state.bulkInFlight = false;
    state.selectedFindingIds.clear();
    state.selectedEntityIds.clear();
    if (render) render();
  }

  function resetEntityProfileNavigation({ view = 'overview' } = {}) {
    state.entityProfileView = view;
    state.entityProfileFindingBucket = 'direct';
    state.entityProfileStack = [];
  }

  function captureEntityProfileSnapshot() {
    const mobileDetailHost = document.getElementById('atlas-mobile-entity-body');
    const activeDetailHost = activeEntityDetailHost();
    return {
      activeTab: state.activeTab,
      summary: state.summary,
      baseSummary: state.baseSummary,
      entities: state.entities,
      findings: state.findings,
      findingCounts: state.findingCounts,
      selectedFindingId: state.selectedFindingId,
      selectedFindingIds: new Set(state.selectedFindingIds),
      selectedEntityIds: new Set(state.selectedEntityIds),
      selectMode: state.selectMode,
      total: state.total,
      totalExact: state.totalExact,
      hasMore: state.hasMore,
      limit: state.limit,
      offset: state.offset,
      query: state.query,
      selectedId: state.selectedId,
      detail: state.detail,
      detailFinding: state.detailFinding,
      detailOffsets: { ...state.detailOffsets },
      entityProfileView: state.entityProfileView,
      entityProfileFindingBucket: state.entityProfileFindingBucket,
      entityProfileReturnScroll: { ...state.entityProfileReturnScroll },
      scroll: {
        list: Number(listHost?.scrollTop || 0),
        profile: Number(activeDetailHost?.scrollTop || 0),
        detail: Number(detailHost?.scrollTop || 0),
        mobile: Number(mobileDetailHost?.scrollTop || 0),
      },
    };
  }

  function restorePreviousEntityProfile() {
    const snapshot = state.entityProfileStack.pop();
    if (!snapshot) return false;
    Object.assign(state, {
      ...snapshot,
      entityProfileMode: true,
      entityProfileStack: state.entityProfileStack,
      detailLoading: false,
    });
    state.selectedFindingIds = new Set(snapshot.selectedFindingIds || []);
    state.selectedEntityIds = new Set(snapshot.selectedEntityIds || []);
    if (searchInput) searchInput.value = state.query;
    render();
    if (listHost) listHost.scrollTop = Math.max(0, Number(snapshot.scroll?.list || 0));
    const activeDetailHost = activeEntityDetailHost();
    const fallbackScroll = isAtlasMobileMode()
      ? snapshot.scroll?.mobile
      : snapshot.scroll?.detail;
    if (activeDetailHost) {
      activeDetailHost.scrollTop = Math.max(0, Number(snapshot.scroll?.profile ?? fallbackScroll ?? 0));
    }
    focusActiveEntityProfileBackControl();
    return true;
  }

  function setSelectMode(enabled) {
    state.selectMode = !!enabled;
    if (!state.selectMode) {
      state.selectedFindingIds.clear();
      state.selectedEntityIds.clear();
    }
    render();
  }

  function toggleItemSelection(item, checked = null) {
    if (!item || !item.id || state.bulkInFlight) return;
    const selected = activeSelectionSet();
    const id = String(item.id);
    const shouldSelect = checked === null ? !selected.has(id) : !!checked;
    if (shouldSelect) selected.add(id);
    else selected.delete(id);
    render();
  }

  function selectAllVisibleItems() {
    if (!state.selectMode || state.bulkInFlight) return;
    const selected = activeSelectionSet();
    const items = visibleSelectableItems().filter(item => item && item.id);
    const allSelected = items.length > 0 && items.every(item => selected.has(String(item.id)));
    items.forEach((item) => {
      const id = String(item.id);
      if (allSelected) selected.delete(id);
      else selected.add(id);
    });
    render();
  }

  function setActiveAtlasTab(tabId, { focus = false } = {}) {
    const nextTab = String(tabId || '');
    if (!nextTab) return false;
    if (state.activeTab === nextTab) {
      if (focus) tabsHost?.querySelector(`[data-atlas-tab="${selectorValue(nextTab)}"]`)?.focus({ preventScroll: true });
      return true;
    }
    const exists = (tabsApi.tabs || []).some(tab => String(tab.id || '') === nextTab);
    if (!exists) return false;
    state.activeTab = nextTab;
    state.offset = 0;
    state.selectedId = '';
    state.selectedFindingId = '';
    state.detailOffsets = { runs: 0, findings: 0, related_urls: 0, related_ports: 0 };
    resetSelection({ selectMode: state.selectMode, render: false });
    state.requestedEntityValue = '';
    state.requestedView = '';
    state.requestedViewStarted = 0;
    state.refreshIntelOnSelect = false;
    state.addActiveProjectOnSelect = false;
    state.detail = null;
    state.detailFinding = null;
    state.entityProfileMode = false;
    resetEntityProfileNavigation();
    render();
    if (focus) {
      window.setTimeout(() => {
        tabsHost?.querySelector(`[data-atlas-tab="${selectorValue(nextTab)}"]`)?.focus({ preventScroll: true });
      }, 0);
    }
    refreshAtlas({ resetOffset: true, force: true });
    return true;
  }

  function cycleAtlasTab(offset = 1) {
    if (!isOpen()) return false;
    const tabs = (tabsApi.tabs || []).filter(tab => tab && tab.id);
    if (tabs.length < 2) return false;
    const currentIndex = Math.max(0, tabs.findIndex(tab => String(tab.id || '') === String(state.activeTab || '')));
    const nextIndex = (currentIndex + Number(offset || 1) + tabs.length) % tabs.length;
    return setActiveAtlasTab(tabs[nextIndex].id);
  }

  function renderTabs() {
    if (!tabsHost) return;
    tabsHost.replaceChildren();
    (tabsApi.tabs || []).forEach(tab => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'tab-strip-item atlas-tab';
      button.dataset.atlasTab = tab.id;
      button.setAttribute('role', 'tab');
      button.setAttribute('aria-selected', tab.id === state.activeTab ? 'true' : 'false');
      button.setAttribute('aria-pressed', tab.id === state.activeTab ? 'true' : 'false');
      button.classList.toggle('active', tab.id === state.activeTab);
      button.classList.toggle('is-active', tab.id === state.activeTab);
      const label = document.createElement('span');
      label.textContent = tab.label;
      const count = document.createElement('span');
      count.className = 'atlas-tab-count';
      count.textContent = `(${tabCountText(tab)})`;
      button.append(label, count);
      button.addEventListener('click', () => {
        setActiveAtlasTab(tab.id);
      });
      tabsHost.appendChild(button);
    });
  }

  function renderSubtitle() {
    if (!subtitle) return;
    const total = tabsApi.totalEntityCount ? tabsApi.totalEntityCount(state.summary) : Number(state.summary?.total || 0);
    const base = `${total.toLocaleString()} ${total === 1 ? 'entity' : 'entities'}`;
    const findingCount = Number(state.summary?.findings || 0);
    const summary = `${base} · ${findingCount.toLocaleString()} ${findingCount === 1 ? 'finding' : 'findings'}`;
    subtitle.textContent = state.projectId && state.projectName ? `${summary} · ${state.projectName}` : summary;
  }

  function populateFindingControls() {
    const option = (label, value) => {
      const item = document.createElement('option');
      item.value = value;
      item.textContent = label;
      return item;
    };
    if (findingStatusFilter && !findingStatusFilter.dataset.populated) {
      findingStatusFilter.appendChild(option('All findings', ''));
      findingStates.forEach(([value, label]) => findingStatusFilter.appendChild(option(label, value)));
      findingStatusFilter.dataset.populated = '1';
    }
    if (findingBulkStatus && !findingBulkStatus.dataset.populated) {
      findingStates.forEach(([value, label]) => findingBulkStatus.appendChild(option(label, value)));
      findingBulkStatus.value = 'reviewed';
      findingBulkStatus.dataset.populated = '1';
    }
    if (orphanFilter && !orphanFilter.dataset.populated) {
      orphanFilter.appendChild(option('Hide orphaned', 'hide'));
      orphanFilter.appendChild(option('Show all', 'all'));
      orphanFilter.appendChild(option('Only orphaned', 'only'));
      orphanFilter.value = state.orphanFilter;
      orphanFilter.dataset.populated = '1';
    }
    if (suppressionFilter && !suppressionFilter.dataset.populated) {
      suppressionFilter.appendChild(option('Visible rows', 'hide'));
      suppressionFilter.appendChild(option('Show all', 'all'));
      suppressionFilter.appendChild(option('Only suppressed', 'only'));
      suppressionFilter.value = state.suppressionFilter;
      suppressionFilter.dataset.populated = '1';
    }
    if (savedViewSelect && !savedViewSelect.dataset.populated) {
      savedViewSelect.appendChild(option('Saved views', ''));
      savedViewSelect.dataset.populated = '1';
    }
    if (runFilterSelect && !runFilterSelect.dataset.populated) {
      runFilterSelect.appendChild(option('Filter by run', ''));
      runFilterSelect.dataset.populated = '1';
    }
    if (projectFilterSelect && !projectFilterSelect.dataset.populated) {
      projectFilterSelect.appendChild(option('Filter by project', ''));
      projectFilterSelect.dataset.populated = '1';
    }
    syncSelectDisplay(findingStatusFilter);
    if (findingBulkStatus) {
      findingBulkStatus.disabled = state.loading || state.bulkInFlight || !canTriageAtlasRows();
      findingBulkStatus.title = canTriageAtlasRows() ? '' : teamScopeDeniedMessage('triage Atlas findings');
      syncSelectDisplay(findingBulkStatus);
    }
    syncSelectDisplay(runFilterSelect);
    syncSelectDisplay(projectFilterSelect);
    syncSelectDisplay(orphanFilter);
    syncSelectDisplay(suppressionFilter);
    syncSelectDisplay(savedViewSelect);
  }

  function syncSelectDisplay(select) {
    if (!select) return;
    if (typeof syncAppSelect === 'function') {
      syncAppSelect(select);
    }
  }

  function setSelectVisibility(select, hidden) {
    if (!select) return;
    select.classList.toggle('u-hidden', hidden);
    const enhancedWrap = select.nextElementSibling;
    if (enhancedWrap && enhancedWrap.classList?.contains('app-select')) {
      enhancedWrap.classList.toggle('u-hidden', hidden);
    }
  }

  function renderFindingControls() {
    populateFindingControls();
    const tab = currentTab();
    const findingsActive = tab.id === 'findings';
    const visibleItems = visibleSelectableItems(tab).filter(item => item && item.id);
    const selected = activeSelectionSet(tab);
    const selectedCount = selected.size;
    const allSelected = visibleItems.length > 0 && visibleItems.every(item => selected.has(String(item.id)));
    const someSelected = visibleItems.some(item => selected.has(String(item.id)));
    setSelectVisibility(findingStatusFilter, !findingsActive);
    setSelectVisibility(findingBulkStatus, !findingsActive || !state.selectMode);
    findingBulkApplyBtn?.classList.toggle('u-hidden', !findingsActive || !state.selectMode);
    exportWrap?.classList.toggle('u-hidden', findingsActive);
    if (findingsActive) setExportMenuOpen(false);
    findingBulkRow?.classList.toggle('u-hidden', !state.selectMode && !visibleItems.length);
    if (selectToggle) {
      selectToggle.checked = !!state.selectMode;
      selectToggle.disabled = state.bulkInFlight;
    }
    if (findingStatusFilter) {
      findingStatusFilter.value = state.findingStatus;
      syncSelectDisplay(findingStatusFilter);
    }
    syncSelectDisplay(findingBulkStatus);
    if (orphanFilter) {
      orphanFilter.value = state.orphanFilter;
      syncSelectDisplay(orphanFilter);
    }
    if (suppressionFilter) {
      suppressionFilter.value = state.suppressionFilter;
      syncSelectDisplay(suppressionFilter);
    }
    renderSavedViewControls();
    if (findingSelectionSummary) {
      findingSelectionSummary.textContent = `${selectedCount.toLocaleString()} selected`;
      findingSelectionSummary.setAttribute('aria-live', 'polite');
    }
    if (findingSelectAllBtn) {
      findingSelectAllBtn.classList.toggle('u-hidden', !state.selectMode);
      findingSelectAllBtn.textContent = allSelected && someSelected ? 'Deselect all' : 'Select all';
      findingSelectAllBtn.disabled = !state.selectMode || !visibleItems.length || state.loading || state.bulkInFlight;
      findingSelectAllBtn.setAttribute('aria-pressed', allSelected && someSelected ? 'true' : someSelected ? 'mixed' : 'false');
    }
    if (findingClearSelectionBtn) {
      findingClearSelectionBtn.classList.toggle('u-hidden', !state.selectMode);
      findingClearSelectionBtn.disabled = !selectedCount || state.loading || state.bulkInFlight;
    }
    if (findingBulkApplyBtn) {
      findingBulkApplyBtn.disabled = !selectedCount || state.loading || state.bulkInFlight || !canTriageAtlasRows();
      findingBulkApplyBtn.title = canTriageAtlasRows() ? '' : teamScopeDeniedMessage('triage Atlas findings');
    }
    if (bulkSuppressionBtn) {
      bulkSuppressionBtn.classList.toggle('u-hidden', !state.selectMode);
      bulkSuppressionBtn.textContent = state.suppressionFilter === 'only' ? 'Restore' : 'Suppress';
      bulkSuppressionBtn.disabled = !selectedCount || state.loading || state.bulkInFlight || !canTriageAtlasRows();
      bulkSuppressionBtn.title = canTriageAtlasRows() ? '' : teamScopeDeniedMessage('suppress Atlas rows');
    }
    if (bulkDeleteBtn) {
      bulkDeleteBtn.classList.toggle('u-hidden', !state.selectMode);
      bulkDeleteBtn.disabled = !selectedCount || state.loading || state.bulkInFlight || !canDeleteAtlasRows();
      bulkDeleteBtn.title = canDeleteAtlasRows() ? '' : teamScopeDeniedMessage('delete Atlas rows');
    }
  }

  function normalizeSavedViews(value) {
    return Array.isArray(value) ? value.filter(item => item && item.id && item.name) : [];
  }

  function normalizeRunOptions(value) {
    return Array.isArray(value)
      ? value.map(item => ({
        id: String(item && (item.id || item.run_id) || '').trim(),
        run_id: String(item && (item.run_id || item.id) || '').trim(),
        command: String(item && item.command || '').trim(),
        started: String(item && item.started || '').trim(),
        entity_count: Number(item && item.entity_count || 0),
        finding_count: Number(item && item.finding_count || 0),
      })).filter(item => item.id)
      : [];
  }

  function normalizeProjectOptions(value) {
    return Array.isArray(value)
      ? value.map(item => ({
        id: String(item && item.id || '').trim(),
        name: String(item && (item.name || item.slug || item.id) || '').trim(),
        slug: String(item && item.slug || '').trim(),
        status: String(item && item.status || '').trim(),
      })).filter(item => item.id)
      : [];
  }

  function projectOptionLabel(project) {
    const name = String(project && project.name || project && project.id || '').trim() || 'Project';
    const status = String(project && project.status || '').trim();
    return status === 'archived' ? `${name} (archived)` : name;
  }

  function selectedProjectOption() {
    const selectedId = String(state.projectId || '');
    return state.projectOptions.find(project => String(project.id || '') === selectedId) || null;
  }

  function runOptionLabel(run) {
    const command = String(run && run.command || '').trim() || 'Run';
    const entityCount = Number(run && run.entity_count || 0);
    const findingCount = Number(run && run.finding_count || 0);
    const counts = [];
    if (entityCount) counts.push(`${entityCount.toLocaleString()} ent`);
    if (findingCount) counts.push(`${findingCount.toLocaleString()} fnd`);
    return counts.length ? `${command} (${counts.join(', ')})` : command;
  }

  function selectedRunOption() {
    const selectedId = String(state.runId || '');
    return state.runOptions.find(run => String(run.id || '') === selectedId) || null;
  }

  function renderRunFilterControls() {
    if (runFilterSearch && runFilterSearch.value !== state.runOptionsQuery) {
      runFilterSearch.value = state.runOptionsQuery || '';
    }
    if (!runFilterSelect) return;
    const optionRows = [...state.runOptions];
    if (state.runId && !optionRows.some(run => String(run.id || '') === state.runId)) {
      optionRows.unshift({
        id: state.runId,
        run_id: state.runId,
        command: state.runLabel || state.runId,
        entity_count: 0,
        finding_count: 0,
      });
    }
    const nextValues = ['', ...optionRows.map(run => String(run.id || ''))].join('\n');
    const currentValues = Array.from(runFilterSelect.options || []).map(option => option.value).join('\n');
    if (nextValues !== currentValues) {
      runFilterSelect.replaceChildren();
      const placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = state.runOptionsLoading ? 'Loading runs...' : 'Filter by run';
      runFilterSelect.appendChild(placeholder);
      optionRows.forEach((run) => {
        const option = document.createElement('option');
        option.value = String(run.id || '');
        option.textContent = runOptionLabel(run);
        option.dataset.runCommand = String(run.command || '');
        runFilterSelect.appendChild(option);
      });
    } else if (runFilterSelect.options[0]) {
      runFilterSelect.options[0].textContent = state.runOptionsLoading ? 'Loading runs...' : 'Filter by run';
    }
    runFilterSelect.value = state.runId || '';
    runFilterSelect.disabled = state.runOptionsLoading;
    syncSelectDisplay(runFilterSelect);
  }

  function renderProjectFilterControls() {
    if (!projectFilterSelect) return;
    const optionRows = [...state.projectOptions];
    if (state.projectId && !optionRows.some(project => String(project.id || '') === state.projectId)) {
      optionRows.unshift({
        id: state.projectId,
        name: state.projectName || state.projectId,
        slug: '',
        status: '',
      });
    }
    const nextValues = ['', ...optionRows.map(project => String(project.id || ''))].join('\n');
    const currentValues = Array.from(projectFilterSelect.options || []).map(option => option.value).join('\n');
    if (nextValues !== currentValues) {
      projectFilterSelect.replaceChildren();
      const placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = state.projectOptionsLoading ? 'Loading projects...' : 'Filter by project';
      projectFilterSelect.appendChild(placeholder);
      optionRows.forEach((project) => {
        const option = document.createElement('option');
        option.value = String(project.id || '');
        option.textContent = projectOptionLabel(project);
        option.dataset.projectName = String(project.name || project.id || '');
        projectFilterSelect.appendChild(option);
      });
    } else if (projectFilterSelect.options[0]) {
      projectFilterSelect.options[0].textContent = state.projectOptionsLoading ? 'Loading projects...' : 'Filter by project';
    }
    projectFilterSelect.value = state.projectId || '';
    projectFilterSelect.disabled = state.projectOptionsLoading;
    syncSelectDisplay(projectFilterSelect);
  }

  function currentSavedViewState(name = '') {
    const tab = visibleActiveTab();
    return {
      name: String(name || '').trim(),
      tab: tab.id || 'findings',
      filters: {
        query: String(state.query || '').trim(),
        orphan_filter: String(state.orphanFilter || 'hide'),
        suppression_filter: String(state.suppressionFilter || 'hide'),
        finding_status: String(state.findingStatus || ''),
        project_id: String(state.projectId || ''),
        project_name: String(state.projectName || ''),
        run_id: String(state.runId || ''),
        run_label: String(state.runLabel || ''),
        sort: '',
      },
    };
  }

  function selectedSavedView() {
    const selectedId = String(state.selectedSavedViewId || '');
    return state.savedViews.find(view => String(view.id || '') === selectedId) || null;
  }

  function renderSavedViewControls() {
    if (!savedViewSelect) return;
    const selectedId = selectedSavedView() ? state.selectedSavedViewId : '';
    if (selectedId !== state.selectedSavedViewId) state.selectedSavedViewId = '';
    const currentOptions = Array.from(savedViewSelect.options || []).map(option => option.value).join('\n');
    const nextValues = ['', ...state.savedViews.map(view => String(view.id || ''))].join('\n');
    if (currentOptions !== nextValues) {
      savedViewSelect.replaceChildren();
      const placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = state.savedViewsLoading ? 'Loading views...' : 'Saved views';
      savedViewSelect.appendChild(placeholder);
      state.savedViews.forEach((view) => {
        const option = document.createElement('option');
        option.value = String(view.id || '');
        option.textContent = String(view.name || 'Saved view');
        savedViewSelect.appendChild(option);
      });
    } else if (savedViewSelect.options[0]) {
      savedViewSelect.options[0].textContent = state.savedViewsLoading ? 'Loading views...' : 'Saved views';
    }
    savedViewSelect.value = state.selectedSavedViewId || '';
    savedViewSelect.disabled = state.savedViewsLoading;
    syncSelectDisplay(savedViewSelect);
    if (savedViewSaveBtn) savedViewSaveBtn.disabled = state.savedViewsLoading;
    if (savedViewUpdateBtn) savedViewUpdateBtn.disabled = !state.selectedSavedViewId || state.savedViewsLoading;
    if (savedViewDeleteBtn) savedViewDeleteBtn.disabled = !state.selectedSavedViewId || state.savedViewsLoading;
    if (savedViewCreateRuleBtn) savedViewCreateRuleBtn.disabled = state.savedViewsLoading;
  }

  function savedViewNameContent(defaultValue = '') {
    const wrap = document.createElement('div');
    wrap.className = 'atlas-saved-view-prompt';
    const label = document.createElement('label');
    label.className = 'form-field';
    const labelText = document.createElement('span');
    labelText.textContent = 'Name';
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'form-control form-control-compact';
    input.maxLength = 60;
    input.value = defaultValue;
    input.setAttribute('aria-label', 'Saved view name');
    label.append(labelText, input);
    wrap.appendChild(label);
    window.setTimeout(() => {
      input.focus({ preventScroll: true });
      input.select();
    }, 0);
    return { content: wrap, input };
  }

  async function promptSavedViewName(defaultName = '', title = 'Save Atlas view') {
    if (typeof showConfirm !== 'function') return '';
    const { content, input } = savedViewNameContent(defaultName);
    const choice = await showConfirm({
      title,
      body: {
        text: title,
        note: 'Saved views remember search, filters, review state, source run, and project scope.',
      },
      content,
      actions: [
        { id: 'cancel', label: 'Cancel', role: 'cancel' },
        { id: 'save', label: 'Save', role: 'primary' },
      ],
      refocusOnResolve: false,
    });
    if (choice !== 'save') return '';
    return String(input.value || '').trim();
  }

  async function loadSavedViews({ force = false } = {}) {
    if (state.savedViewsLoaded && !force) return state.savedViews;
    state.savedViewsLoading = true;
    renderSavedViewControls();
    try {
      const resp = await api()('/atlas/views', { cache: 'no-store' });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      state.savedViews = normalizeSavedViews(data.views);
      state.savedViewsLoaded = true;
      if (state.selectedSavedViewId && !selectedSavedView()) state.selectedSavedViewId = '';
      return state.savedViews;
    } catch (err) {
      logImportClientError('failed to load atlas saved views', err);
      showToastSafe('Failed to load saved Atlas views', 'error');
      return state.savedViews;
    } finally {
      state.savedViewsLoading = false;
      renderSavedViewControls();
    }
  }

  async function loadRunOptions({ query = state.runOptionsQuery, force = false } = {}) {
    const normalizedQuery = String(query || '').trim();
    if (
      !force
      && state.runOptionsLoaded
      && normalizedQuery === state.runOptionsQuery
      && (!state.runId || state.runOptions.some(run => String(run.id || '') === String(state.runId || '')))
    ) {
      return state.runOptions;
    }
    state.runOptionsQuery = normalizedQuery;
    state.runOptionsLoading = true;
    renderRunFilterControls();
    try {
      const params = new URLSearchParams({ limit: '30' });
      if (normalizedQuery) params.set('q', normalizedQuery);
      if (state.runId) params.set('run_id', state.runId);
      const resp = await api()(`/atlas/runs?${params.toString()}`, { cache: 'no-store' });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      state.runOptions = normalizeRunOptions(data.runs);
      state.runOptionsLoaded = true;
      const selected = selectedRunOption();
      if (selected && selected.command && !state.runLabel) state.runLabel = selected.command;
      return state.runOptions;
    } catch (err) {
      logImportClientError('failed to load atlas run filters', err);
      return state.runOptions;
    } finally {
      state.runOptionsLoading = false;
      renderRunFilterControls();
    }
  }

  async function loadProjectOptions({ force = false } = {}) {
    if (
      !force
      && state.projectOptionsLoaded
      && (!state.projectId || state.projectOptions.some(project => String(project.id || '') === String(state.projectId || '')))
    ) {
      return state.projectOptions;
    }
    state.projectOptionsLoading = true;
    renderProjectFilterControls();
    try {
      const params = new URLSearchParams({ mode: 'switcher', limit: '30' });
      const resp = await api()(`/projects?${params.toString()}`, { cache: 'no-store' });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      state.projectOptions = normalizeProjectOptions(data.projects);
      state.projectOptionsLoaded = true;
      const selected = selectedProjectOption();
      if (selected && selected.name && !state.projectName) state.projectName = selected.name;
      return state.projectOptions;
    } catch (err) {
      logImportClientError('failed to load atlas project filters', err);
      return state.projectOptions;
    } finally {
      state.projectOptionsLoading = false;
      renderProjectFilterControls();
    }
  }

  function updateSavedViewsFromResponse(data) {
    state.savedViews = normalizeSavedViews(data?.views);
    if (data?.view?.id) state.selectedSavedViewId = String(data.view.id || '');
    if (state.selectedSavedViewId && !selectedSavedView()) state.selectedSavedViewId = '';
    state.savedViewsLoaded = true;
    render();
  }

  async function saveCurrentView() {
    const name = await promptSavedViewName('', 'Save Atlas view');
    if (!name) return;
    try {
      const resp = await api()('/atlas/views', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(currentSavedViewState(name)),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      updateSavedViewsFromResponse(data);
      showToastSafe('Atlas view saved', 'success');
    } catch (err) {
      logImportClientError('failed to save atlas view', err);
      showToastSafe('Failed to save Atlas view', 'error');
    }
  }

  async function updateCurrentSavedView() {
    const current = selectedSavedView();
    if (!current) return;
    const name = await promptSavedViewName(current.name || '', 'Update Atlas view');
    if (!name) return;
    try {
      const resp = await api()(`/atlas/views/${encodeURIComponent(current.id)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(currentSavedViewState(name)),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      updateSavedViewsFromResponse(data);
      showToastSafe('Atlas view updated', 'success');
    } catch (err) {
      logImportClientError('failed to update atlas view', err);
      showToastSafe('Failed to update Atlas view', 'error');
    }
  }

  async function deleteCurrentSavedView() {
    const current = selectedSavedView();
    if (!current || typeof showConfirm !== 'function') return;
    try {
      const choice = await showConfirm({
        body: { text: `Delete "${current.name}"?`, note: 'This only removes the saved view. Atlas data is unchanged.' },
        tone: 'warning',
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'delete', label: 'Delete', role: 'destructive', tone: 'warning' },
        ],
        refocusOnResolve: false,
      });
      if (choice !== 'delete') return;
      const resp = await api()(`/atlas/views/${encodeURIComponent(current.id)}`, { method: 'DELETE' });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      state.selectedSavedViewId = '';
      updateSavedViewsFromResponse(data);
      showToastSafe('Atlas view deleted', 'success');
    } catch (err) {
      logImportClientError('failed to delete atlas view', err);
      showToastSafe('Failed to delete Atlas view', 'error');
    }
  }

  function setExportMenuOpen(open) {
    if (!exportWrap || !exportMenuBtn) return;
    exportWrap.classList.toggle('open', !!open);
    exportMenuBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open && exportMenu && typeof portalDropdownMenu === 'function') {
      exportWrap.dataset.portalMenu = 'true';
      portalDropdownMenu(exportWrap, exportMenuBtn, exportMenu);
    } else if (!open && exportMenu && typeof unportalDropdownMenu === 'function') {
      unportalDropdownMenu(exportMenu);
    }
  }

  function currentAutoPromoteRuleDraft() {
    const tab = visibleActiveTab();
    const targetKind = String(tab && tab.type || 'any') || 'any';
    const query = String(state.query || '').trim();
    const projectId = String(state.projectId || '').trim();
    const projectName = String(state.projectName || '').trim();
    const filters = {
      source_command_roots: [],
      source_run_ids: state.runId ? [String(state.runId)] : [],
      include_suppressed: state.suppressionFilter !== 'hide',
      first_seen_after_rule_created: false,
    };
    return {
      name: query ? `Atlas view: ${query.slice(0, 48)}` : 'Atlas view rule',
      project_id: projectId,
      project_name: projectName,
      target_entity_kind: targetKind,
      match_mode: query ? 'contains' : (targetKind === 'domain' ? 'domain_suffix' : 'exact'),
      pattern: query,
      filters,
      atlas_view: currentSavedViewState('Atlas view rule'),
    };
  }

  async function createRuleFromCurrentView() {
    if (typeof importedOpenProjectAutoPromoteRuleFromAtlas !== 'function') {
      showToastSafe('Projects are not ready yet', 'error');
      return;
    }
    try {
      const opened = await importedOpenProjectAutoPromoteRuleFromAtlas(currentAutoPromoteRuleDraft());
      if (opened) closeAtlas({ refocus: false });
    } catch (err) {
      logImportClientError('failed to create auto-promote rule from atlas view', err);
      showToastSafe(err && err.message ? err.message : 'Failed to create rule from Atlas view', 'error');
    }
  }

  function selectedImportFormatLabel() {
    const option = importFormatSelect?.selectedOptions?.[0] || null;
    return String(option?.textContent || importFormatSelect?.value || 'Atlas import').trim();
  }

  function syncImportFileAcceptHint() {
    if (!importFileInput || !importFormatSelect) return;
    importFileInput.setAttribute('accept', importAcceptByFormat[importFormatSelect.value] || '');
  }

  function resetImportFlow() {
    state.importFlow.previewLoading = false;
    state.importFlow.applyLoading = false;
    state.importFlow.draftId = '';
    state.importFlow.rowSetDigest = '';
    state.importFlow.preview = null;
    state.importFlow.result = null;
    if (importStatus) importStatus.textContent = '';
    if (importPreviewHost) {
      importPreviewHost.replaceChildren();
      importPreviewHost.classList.add('u-hidden');
    }
    if (importApplyBtn) importApplyBtn.disabled = true;
  }

  function setImportModalOpen(open) {
    if (!importOverlay) return;
    state.importFlow.open = !!open;
    importOverlay.classList.toggle('u-hidden', !open);
    importOverlay.classList.toggle('open', !!open);
    importOverlay.setAttribute('aria-hidden', open ? 'false' : 'true');
    if (!open) {
      resetImportFlow();
      if (importFileInput) importFileInput.value = '';
      if (importNameInput) importNameInput.value = '';
      if (typeof syncModalOverlayState === 'function') syncModalOverlayState();
      return;
    }
    if (importNameInput && !importNameInput.value) importNameInput.value = selectedImportFormatLabel();
    syncImportFileAcceptHint();
    renderImportPreview();
    if (typeof syncModalOverlayState === 'function') syncModalOverlayState();
    window.setTimeout(() => {
      const focusTarget = importFormatSelect || importModal;
      focusTarget?.focus?.({ preventScroll: true });
    }, 0);
  }

  function openImportModal() {
    setExportMenuOpen(false);
    setImportModalOpen(true);
  }

  function closeImportModal() {
    setImportModalOpen(false);
  }

  function importCountGrid(counts = {}) {
    const grid = document.createElement('div');
    grid.className = 'atlas-import-count-grid';
    [
      ['Rows', counts.rows],
      ['Entities', counts.entity_valid],
      ['Findings', counts.finding_valid],
      ['New', counts.new],
      ['Updated', counts.updated],
      ['Warnings', counts.warnings],
    ].forEach(([label, value]) => {
      const item = document.createElement('div');
      item.className = 'atlas-import-count';
      item.append(
        node('span', 'atlas-import-count-value', Number(value || 0).toLocaleString()),
        node('span', 'atlas-import-count-label', label),
      );
      grid.appendChild(item);
    });
    return grid;
  }

  function importSampleRows(title, rows, formatter) {
    const sectionEl = document.createElement('div');
    sectionEl.className = 'atlas-import-sample';
    sectionEl.appendChild(node('div', 'atlas-import-sample-title', title));
    const list = document.createElement('div');
    list.className = 'atlas-import-sample-list nice-scroll';
    const values = Array.isArray(rows) ? rows : [];
    if (!values.length) {
      list.appendChild(node('div', 'atlas-empty-inline', 'No rows'));
    } else {
      values.slice(0, 6).forEach((row) => list.appendChild(node('div', 'panel-row atlas-import-sample-row', formatter(row))));
    }
    sectionEl.appendChild(list);
    return sectionEl;
  }

  function importWarningRows(warnings) {
    const sectionEl = document.createElement('div');
    sectionEl.className = 'atlas-import-sample';
    sectionEl.appendChild(node('div', 'atlas-import-sample-title', 'Warnings'));
    const list = document.createElement('div');
    list.className = 'atlas-import-warning-list nice-scroll';
    const values = Array.isArray(warnings) ? warnings : [];
    if (!values.length) {
      list.appendChild(node('div', 'atlas-empty-inline', 'No warnings'));
    } else {
      values.slice(0, 8).forEach((warning) => {
        const label = warning && typeof warning === 'object'
          ? `Row ${warning.row_number || '?'} · ${text(warning.message, warning.code || 'warning')}`
          : text(warning, 'warning');
        list.appendChild(node('div', 'panel-row atlas-import-warning-row', label));
      });
    }
    sectionEl.appendChild(list);
    return sectionEl;
  }

  function importOptionAvailable(options, key) {
    const option = options && typeof options === 'object' ? options[key] : null;
    return !!(option && option.available);
  }

  function importOptionControl(key, label, note, options, { checked = true, disabled = false } = {}) {
    const wrap = document.createElement('label');
    wrap.className = 'form-check atlas-import-option';
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.dataset.atlasImportOption = key;
    checkbox.checked = checked && !disabled;
    checkbox.disabled = !!disabled;
    const copy = document.createElement('span');
    copy.append(node('span', 'atlas-import-option-label', label));
    if (note) copy.append(node('span', 'atlas-muted atlas-import-option-note', note));
    wrap.append(checkbox, copy);
    return wrap;
  }

  function renderImportPreview() {
    if (!importPreviewHost) return;
    importPreviewHost.replaceChildren();
    const flow = state.importFlow;
    const preview = flow.preview;
    const result = flow.result;
    if (!preview && !result) {
      importPreviewHost.classList.add('u-hidden');
      if (importApplyBtn) importApplyBtn.disabled = true;
      return;
    }
    importPreviewHost.classList.remove('u-hidden');
    if (preview) {
      const counts = preview.counts || {};
      importPreviewHost.append(
        node('div', 'atlas-detail-section-title', 'Preview'),
        importCountGrid(counts),
      );
      const options = preview.apply_options || {};
      const optionWrap = document.createElement('div');
      optionWrap.className = 'atlas-import-options';
      const hasProject = !!String(state.projectId || '').trim();
      optionWrap.append(
        importOptionControl('import_entities', 'Import entities', 'Add or update normalized Atlas entities.', options, {
          checked: importOptionAvailable(options, 'import_entities'),
          disabled: !importOptionAvailable(options, 'import_entities'),
        }),
        importOptionControl('import_findings', 'Import findings', 'Add findings and their import occurrence sources.', options, {
          checked: importOptionAvailable(options, 'import_findings'),
          disabled: !importOptionAvailable(options, 'import_findings'),
        }),
        importOptionControl('link_to_project', 'Link imported entities to this project', hasProject ? state.projectName || 'Project context' : 'Open Atlas from a project to link rows.', options, {
          checked: false,
          disabled: !hasProject || !importOptionAvailable(options, 'link_to_project'),
        }),
        importOptionControl('create_project_targets', 'Create project targets', `${Number(counts.project_target_candidates || 0).toLocaleString()} target candidates; creates or reuses Atlas entities`, options, {
          checked: false,
          disabled: !hasProject || !importOptionAvailable(options, 'create_project_targets'),
        }),
      );
      importPreviewHost.append(optionWrap);
      const samples = preview.samples || {};
      const sampleGrid = document.createElement('div');
      sampleGrid.className = 'atlas-import-samples';
      sampleGrid.append(
        importSampleRows('Entity sample', samples.entities, row => [
          text(row.kind, 'entity'),
          text(row.canonical_value, row.value || ''),
        ].filter(Boolean).join(' · ')),
        importSampleRows('Finding sample', samples.findings, row => [
          text(row.severity),
          text(row.title, row.signature_hash || 'finding'),
        ].filter(Boolean).join(' · ')),
        importWarningRows(preview.warnings),
      );
      importPreviewHost.append(sampleGrid);
    }
    if (result) {
      const counts = result.counts || {};
      const resultBox = document.createElement('div');
      resultBox.className = 'atlas-import-result';
      resultBox.append(
        node('div', 'atlas-detail-section-title', 'Applied'),
        node('div', 'atlas-muted', [
          countLabel(counts.entities_created, 'entity created', 'entities created'),
          countLabel(counts.entities_updated, 'entity updated', 'entities updated'),
          countLabel(counts.findings_created, 'finding created', 'findings created'),
          countLabel(counts.findings_updated, 'finding updated', 'findings updated'),
          countLabel(counts.project_links_added, 'project link added', 'project links added'),
          countLabel(counts.project_links_existing, 'project link already existed', 'project links already existed'),
          countLabel(counts.project_targets_created, 'project target created', 'project targets created'),
          countLabel(counts.project_targets_existing, 'project target already existed', 'project targets already existed'),
        ].join(' · ')),
      );
      importPreviewHost.append(resultBox);
    }
    syncImportApplyState();
  }

  function selectedImportOptions() {
    const options = {};
    importPreviewHost?.querySelectorAll?.('[data-atlas-import-option]').forEach((checkbox) => {
      options[checkbox.dataset.atlasImportOption] = !!checkbox.checked && !checkbox.disabled;
    });
    return options;
  }

  function syncImportApplyState() {
    const options = selectedImportOptions();
    const hasOption = Object.values(options).some(Boolean);
    if (importApplyBtn) {
      importApplyBtn.disabled = !state.importFlow.preview || !state.importFlow.draftId || !hasOption
        || state.importFlow.previewLoading || state.importFlow.applyLoading;
      importApplyBtn.textContent = state.importFlow.applyLoading ? 'Applying...' : 'Apply import';
    }
    if (importPreviewBtn) {
      importPreviewBtn.disabled = state.importFlow.previewLoading || state.importFlow.applyLoading;
      importPreviewBtn.textContent = state.importFlow.previewLoading ? 'Previewing...' : 'Preview';
    }
  }

  async function previewImportFile() {
    if (!importFileInput || !importFormatSelect) return;
    const file = importFileInput.files && importFileInput.files[0] ? importFileInput.files[0] : null;
    if (!file) {
      showToastSafe('Choose a file to import', 'error');
      return;
    }
    state.importFlow.previewLoading = true;
    state.importFlow.result = null;
    state.importFlow.preview = null;
    if (importStatus) importStatus.textContent = 'Parsing file...';
    renderImportPreview();
    syncImportApplyState();
    try {
      const body = new FormData();
      body.append('file', file);
      body.append('format_id', String(importFormatSelect.value || ''));
      body.append('source_tool', selectedImportFormatLabel());
      body.append('import_name', String(importNameInput?.value || '').trim() || selectedImportFormatLabel());
      const resp = await api()('/atlas/imports/preview', { method: 'POST', body });
      if (!resp.ok) throw await atlasMutationError(resp, 'Failed to preview import');
      const data = await resp.json();
      state.importFlow.draftId = String(data.draft_id || '');
      state.importFlow.rowSetDigest = String(data.row_set_digest || '');
      state.importFlow.preview = data;
      if (importStatus) importStatus.textContent = 'Preview ready';
      renderImportPreview();
    } catch (err) {
      logImportClientError('failed to preview atlas import', err);
      if (importStatus) importStatus.textContent = '';
      showToastSafe(err && err.message ? err.message : 'Failed to preview import', 'error');
    } finally {
      state.importFlow.previewLoading = false;
      syncImportApplyState();
    }
  }

  async function applyImportPreview() {
    if (!state.importFlow.preview || !state.importFlow.draftId || !state.importFlow.rowSetDigest) return;
    const options = selectedImportOptions();
    if (!Object.values(options).some(Boolean)) {
      showToastSafe('Choose what to import first', 'error');
      return;
    }
    state.importFlow.applyLoading = true;
    if (importStatus) importStatus.textContent = 'Applying import...';
    syncImportApplyState();
    try {
      const body = {
        draft_id: state.importFlow.draftId,
        row_set_digest: state.importFlow.rowSetDigest,
        options,
      };
      if (state.projectId) body.project_id = state.projectId;
      const resp = await api()('/atlas/imports/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.ok) throw await atlasMutationError(resp, 'Failed to apply import');
      const data = await resp.json();
      state.importFlow.result = data;
      state.importFlow.draftId = '';
      state.importFlow.rowSetDigest = '';
      if (importStatus) importStatus.textContent = 'Import applied';
      showToastSafe('Atlas import applied', 'success');
      if (state.projectId) broadcastProjectWorkspaceChange('atlas_import_applied', state.projectId);
      await refreshAtlas({ resetOffset: true });
      renderImportPreview();
    } catch (err) {
      logImportClientError('failed to apply atlas import', err);
      showToastSafe(err && err.message ? err.message : 'Failed to apply import', 'error');
    } finally {
      state.importFlow.applyLoading = false;
      syncImportApplyState();
    }
  }

  function applySavedView(viewId) {
    const view = state.savedViews.find(item => String(item.id || '') === String(viewId || ''));
    if (!view) {
      state.selectedSavedViewId = '';
      renderSavedViewControls();
      return;
    }
    const filters = view.filters && typeof view.filters === 'object' ? view.filters : {};
    state.selectedSavedViewId = String(view.id || '');
    const savedTab = tabsApi.tabById?.(String(view.tab || ''));
    state.activeTab = filters.finding_status ? 'findings' : (savedTab?.id || state.activeTab);
    state.query = String(filters.query || '').trim();
    state.orphanFilter = String(filters.orphan_filter || 'hide') || 'hide';
    state.suppressionFilter = String(filters.suppression_filter || 'hide') || 'hide';
    state.findingStatus = String(filters.finding_status || '');
    state.projectId = String(filters.project_id || '');
    state.projectName = String(filters.project_name || '');
    state.runId = String(filters.run_id || '').trim();
    state.runLabel = String(filters.run_label || '').trim();
    state.runOptionsQuery = '';
    if (searchInput) searchInput.value = state.query;
    state.selectedId = '';
    state.selectedFindingId = '';
    state.detailOffsets = { runs: 0, findings: 0, related_urls: 0, related_ports: 0 };
    resetSelection({ selectMode: state.selectMode, render: false });
    state.detail = null;
    state.detailFinding = null;
    state.entityProfileMode = false;
    resetEntityProfileNavigation();
    state.requestedEntityValue = '';
    state.requestedView = '';
    state.requestedViewStarted = 0;
    state.refreshIntelOnSelect = false;
    state.addActiveProjectOnSelect = false;
    render();
    loadRunOptions({ force: true }).catch((err) => {
      logImportClientError('failed to load atlas run filters', err);
    });
    loadProjectOptions({ force: true }).catch((err) => {
      logImportClientError('failed to load atlas project filters', err);
    });
    refreshAtlas({ resetOffset: true, force: true });
  }

  function findingStatusLabel(value) {
    const found = findingStates.find(([stateValue]) => stateValue === String(value || ''));
    return found ? found[1] : text(value, 'New');
  }

  function activateRowOnKeyboard(row, handler) {
    row.setAttribute('role', 'button');
    row.tabIndex = 0;
    row.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      handler();
    });
  }

  function appendSelectionCheckbox(row, item, selectedIds, label, className = 'atlas-row-select') {
    const selectLabel = document.createElement('label');
    selectLabel.className = 'atlas-row-select-label';
    selectLabel.addEventListener('click', event => event.stopPropagation());
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.className = className;
    checkbox.checked = selectedIds.has(String(item.id || ''));
    checkbox.setAttribute('aria-label', label);
    checkbox.addEventListener('change', () => {
      toggleItemSelection(item, checkbox.checked);
    });
    selectLabel.appendChild(checkbox);
    row.appendChild(selectLabel);
  }

  function suppressionIconLabel(item, noun = 'row') {
    return item && item.suppressed ? `Restore ${noun}` : `Suppress ${noun}`;
  }

  function createSuppressionIconButton(item, noun, handler) {
    const btn = document.createElement('button');
    const label = suppressionIconLabel(item, noun);
    const allowed = canTriageAtlasRows();
    btn.type = 'button';
    btn.className = 'btn btn-ghost btn-icon-only btn-compact atlas-row-suppression-action';
    btn.title = allowed ? label : teamScopeDeniedMessage(`suppress Atlas ${noun}s`);
    btn.setAttribute('aria-label', label);
    btn.disabled = !allowed;
    btn.textContent = item && item.suppressed ? '↺' : '⊘';
    btn.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (!canTriageAtlasRows()) {
        showAtlasPermissionDenied(`suppress Atlas ${noun}s`);
        return;
      }
      handler?.();
    });
    return btn;
  }

  function findingRow(finding) {
    const row = document.createElement('div');
    row.className = 'chrome-row chrome-row-clickable selection-row atlas-finding-queue-row';
    row.classList.toggle('is-suppressed', !!finding.suppressed);
    row.classList.toggle('is-selecting', state.selectMode);
    const selected = state.selectMode
      ? state.selectedFindingIds.has(String(finding.id || ''))
      : finding.id === state.selectedFindingId;
    row.classList.toggle('is-selected', selected);
    if (!state.selectMode && selected) row.setAttribute('aria-current', 'true');
    row.classList.toggle('has-row-action', !state.selectMode);
    row.dataset.findingId = finding.id;

    const main = document.createElement('span');
    main.className = 'atlas-entity-main';
    const title = document.createElement('span');
    title.className = 'atlas-finding-title';
    title.textContent = text(finding.title || finding.raw_line, finding.id);
    const meta = document.createElement('span');
    meta.className = 'atlas-muted';
    meta.textContent = [
      findingStatusLabel(finding.review_state || finding.status),
      text(finding.severity),
      text(finding.tool_root),
      text(finding.entity_value || finding.subject_key),
      summarizeFindingRisk(finding),
    ].filter(Boolean).join(' · ');
    main.append(title, meta);

    const badges = document.createElement('span');
    badges.className = 'atlas-entity-badges';
    if (finding.suppressed) badges.appendChild(badge('suppressed', 'muted'));
    badges.appendChild(badge(findingStatusLabel(finding.review_state || finding.status), 'green'));
    triageBadges(finding).forEach(item => badges.appendChild(item));
    if (finding.occurrence_count) badges.appendChild(badge(countLabel(finding.occurrence_count, 'hit', 'hits'), 'muted'));
    if (state.selectMode) {
      appendSelectionCheckbox(
        row,
        finding,
        state.selectedFindingIds,
        `Select finding: ${finding.title || finding.id}`,
        'atlas-finding-select atlas-row-select',
      );
    }
    row.append(main, badges);
    if (!state.selectMode) {
      row.appendChild(createSuppressionIconButton(
        finding,
        'finding',
        () => updateSuppression(finding, !finding.suppressed),
      ));
    }
    const handleActivation = () => {
      if (state.selectMode) {
        toggleItemSelection(finding);
        return;
      }
      selectFinding(finding.id);
    };
    row.addEventListener('click', handleActivation);
    if (!state.selectMode) activateRowOnKeyboard(row, handleActivation);
    return row;
  }

  function renderList() {
    if (!listHost) return;
    listHost.replaceChildren();
    const tab = currentTab();
    if (state.loading) {
      listHost.appendChild(rowMessage('Loading Atlas...'));
      return;
    }
    if (tab.id === 'findings') {
      if (!state.findings.length) {
        listHost.appendChild(rowMessage(state.query || state.findingStatus ? 'No matching findings' : 'No findings queued'));
        return;
      }
      state.findings.forEach(finding => listHost.appendChild(findingRow(finding)));
      return;
    }
    if (!state.entities.length) {
      listHost.appendChild(rowMessage(state.query ? 'No matching entities' : 'No entities yet'));
      return;
    }
    state.entities.forEach(entity => {
      const handleActivation = () => {
        if (state.selectMode) {
          toggleItemSelection(entity);
          return;
        }
        selectEntity(entity.id);
      };
      const row = entityRowApi.renderAtlasEntityRow({
        entity,
        selected: state.selectMode
          ? state.selectedEntityIds.has(String(entity.id || ''))
          : entity.id === state.selectedId,
        selecting: state.selectMode,
        selectMode: state.selectMode,
        text,
        countLabel,
        badge,
        appendSelectionControl: state.selectMode
          ? (targetRow) => appendSelectionCheckbox(
              targetRow,
              entity,
              state.selectedEntityIds,
              `Select entity: ${entity.canonical_value || entity.id}`,
            )
          : null,
        rowAction: state.selectMode
          ? null
          : createSuppressionIconButton(
              entity,
              'entity',
              () => updateSuppression(entity, !entity.suppressed),
            ),
        onActivate: handleActivation,
      });
      listHost.appendChild(row);
    });
  }

  function badge(label, tone) {
    const el = document.createElement('span');
    const toneClass = {
      amber: 'badge-tone-amber',
      green: 'badge-tone-green',
      red: 'badge-tone-red',
    }[tone] || 'badge-tone-muted';
    el.className = `badge ${toneClass}`;
    el.textContent = label;
    return el;
  }

  function triageBadges(finding) {
    const result = [];
    const triage = finding && finding.triage && typeof finding.triage === 'object' ? finding.triage : null;
    if (!triage) return result;
    const status = String(triage.verification_status || finding.verification_status || 'not_started');
    if (status && status !== 'not_started') {
      const label = findingTriageEditor?.verificationStatusLabel?.(status) || status.replace(/_/g, ' ');
      const tone = findingTriageEditor?.verificationStatusTone?.(status) || 'muted';
      result.push(badge(label, tone));
    }
    if (triage.has_remediation) result.push(badge('remediation', 'muted'));
    if (triage.has_verification_steps) result.push(badge('verification steps', 'muted'));
    return result;
  }

  function rowMessage(message) {
    const row = document.createElement('div');
    row.className = 'atlas-empty';
    row.textContent = message;
    return row;
  }

  function renderPagination() {
    if (!pagination || !paginationSummary || !prevBtn || !nextBtn) return;
    const items = currentTab().id === 'findings' ? state.findings : state.entities;
    const shown = Array.isArray(items) ? items.length : 0;
    const hasMore = !!state.hasMore;
    const showPager = state.total > state.limit || state.offset > 0 || hasMore;
    pagination.classList.toggle('u-hidden', !showPager);
    if (!showPager) {
      paginationSummary.textContent = '';
      prevBtn.disabled = true;
      nextBtn.disabled = true;
      return;
    }
    const start = state.total || shown ? state.offset + 1 : 0;
    const end = state.totalExact
      ? Math.min(state.offset + state.limit, Math.max(Number(state.total || 0), shown))
      : (shown ? state.offset + shown : 0);
    const total = Math.max(Number(state.total || 0), end);
    const totalText = state.totalExact ? total.toLocaleString() : `${total.toLocaleString()}+`;
    paginationSummary.textContent = `${start}-${end} of ${totalText}`;
    prevBtn.disabled = state.offset <= 0 || state.loading;
    nextBtn.disabled = !hasMore || state.loading;
  }

  function entityDetailRenderOptions({
    profileBackLabel = state.entityProfileStack.length ? 'Back to previous entity' : 'Back to results',
    onExitProfile = () => exitEntityProfile(),
  } = {}) {
    const activeProject = typeof importedGetActiveProjectContext === 'function'
      ? importedGetActiveProjectContext()
      : null;
    return {
      activeProject,
      canTriageAtlasRows: canTriageAtlasRows(),
      triageDisabledReason: teamScopeDeniedMessage('triage Atlas rows'),
      canDeleteAtlasRows: canDeleteAtlasRows(),
      deleteDisabledReason: teamScopeDeniedMessage('delete Atlas rows'),
      canCreateFinding: !!(
        state.projectId
        && ['domain', 'ip', 'url'].includes(String(state.detail?.entity?.type || ''))
      ),
      findingDisabledReason: teamScopeDeniedMessage('create Atlas findings'),
      isLinkedToActiveProject: (entity) => {
        const activeId = activeProject && activeProject.id ? String(activeProject.id) : '';
        return !!activeId && (Array.isArray(entity.project_links) ? entity.project_links : [])
          .some(link => String(link.project_id || '') === activeId);
      },
      intelRefreshing: state.intelRefreshing,
      onCopyValue: (entity) => copyEntityValue(entity),
      onRefreshIntel: () => refreshIntel(),
      onAddToActiveProject: () => addToActiveProject(),
      onOpenProject: (link) => openLinkedProject(link),
      onRemoveProjectLink: (link) => removeProjectLink(link),
      onSaveMetadata: (payload) => saveMetadata(payload),
      onSeeRun: (run) => openSourceRun(run),
      onOpenEntity: (entity) => openEntityFromRelatedEntity(entity),
      onCleanRunAtlas: (run) => confirmCleanRunAtlas(run),
      onDeleteEntity: () => confirmDeleteEntity(),
      onCreateFinding: (entity) => createFindingForAtlasEntity(entity),
      onSuppressEntity: (entity) => updateSuppression(entity, !entity.suppressed),
      onPageRuns: (offset) => pageEntityDetail('runs', offset),
      onPageFindings: (offset) => pageEntityDetail('findings', offset),
      onPageRelatedUrls: (offset) => pageEntityDetail('related_urls', offset),
      onPageRelatedPorts: (offset) => pageEntityDetail('related_ports', offset),
      onOpenFinding: (finding) => openEntityFindingDetail(finding),
      onOpenFindingBucket: (bucket) => openEntityFindingBucket(bucket),
      onOpenEvidence: () => openEntityProfileView('evidence'),
      onOpenIntel: () => openEntityProfileView('intel'),
      profileMode: state.entityProfileMode,
      profileView: state.entityProfileView,
      profileBackLabel,
      onViewProfile: (view) => enterEntityProfile(view),
      onExitProfile,
      onProfileViewChange: (view, options) => setEntityProfileView(view, options),
    };
  }

  function renderEntityDetailHost(host, options = {}) {
    if (!host) return;
    if (state.detailLoading) {
      host.replaceChildren(rowMessage('Loading entity...'));
      return;
    }
    if (!state.selectedId || !state.detail) {
      const message = rowMessage('Select an entity');
      host.replaceChildren(message);
      return;
    }
    if (state.detailFinding) {
      if (typeof currentDetailApi().renderFindingDetail !== 'function') {
        host.replaceChildren(rowMessage('Loading finding...'));
        ensureDetailApi();
        return;
      }
      detailApi.renderFindingDetail?.(
        host,
        state.detailFinding,
        findingDetailHandlers({ onBack: closeEntityFindingDetail }),
      );
      return;
    }
    if (typeof currentDetailApi().renderDetail !== 'function') {
      host.replaceChildren(rowMessage('Loading entity...'));
      ensureDetailApi();
      return;
    }
    detailApi.renderDetail?.(host, state.detail, entityDetailRenderOptions(options));
  }

  function renderDetail() {
    if (!detailHost) return;
    if (state.detailLoading) {
      detailHost.replaceChildren(rowMessage('Loading entity...'));
      return;
    }
    if (currentTab().id === 'findings') {
      const finding = state.findings.find(item => String(item.id || '') === state.selectedFindingId);
      if (!finding || !finding.id) {
        renderDetailMessage('Select a finding');
        return;
      }
      if (typeof currentDetailApi().renderFindingDetail !== 'function') {
        renderDetailMessage('Loading finding...');
        ensureDetailApi();
        return;
      }
      detailApi.renderFindingDetail?.(detailHost, finding, findingDetailHandlers());
      return;
    }
    renderEntityDetailHost(detailHost);
  }

  function enterEntityProfile(view = 'overview') {
    if (!state.selectedId || !state.detail) return false;
    if (!state.entityProfileMode) {
      state.entityProfileReturnScroll = {
        list: Number(listHost?.scrollTop || 0),
        detail: Number(detailHost?.scrollTop || 0),
      };
      state.entityProfileFindingBucket = 'direct';
      state.entityProfileStack = [];
    }
    state.entityProfileMode = true;
    state.entityProfileView = ['overview', 'evidence', 'findings', 'intel'].includes(String(view || ''))
      ? String(view)
      : 'overview';
    state.detailFinding = null;
    render();
    const activeDetailHost = activeEntityDetailHost();
    if (activeDetailHost) activeDetailHost.scrollTop = 0;
    activeEntityProfileBackControl()?.focus?.({ preventScroll: true });
    return true;
  }

  function exitEntityProfile({ focusResult = true } = {}) {
    if (!state.entityProfileMode) return false;
    if (restorePreviousEntityProfile()) return true;
    if (state.lookupMode) {
      state.entityProfileMode = false;
      state.entityProfileFindingBucket = 'direct';
      state.detailFinding = null;
      quickLookupController?.showForm?.({ focus: focusResult });
      render();
      return true;
    }
    const returnScroll = state.entityProfileReturnScroll || {};
    state.entityProfileMode = false;
    state.entityProfileFindingBucket = 'direct';
    render();
    if (listHost) listHost.scrollTop = Math.max(0, Number(returnScroll.list || 0));
    if (detailHost) detailHost.scrollTop = Math.max(0, Number(returnScroll.detail || 0));
    if (focusResult && state.selectedId) {
      window.setTimeout(() => {
        listHost
          ?.querySelector?.(`[data-entity-id="${selectorValue(state.selectedId)}"]`)
          ?.focus?.({ preventScroll: true });
      }, 0);
    }
    return true;
  }

  function setEntityProfileView(view, { focus = false } = {}) {
    const next = String(view || '');
    if (!state.entityProfileMode || !['overview', 'evidence', 'findings', 'intel'].includes(next)) return false;
    state.entityProfileView = next;
    if (state.lookupMode) {
      render();
    } else {
      renderDetail();
      for (const fn of mobileRenderers) {
        try { fn(state, atlasController); } catch (err) {
          logImportClientError('atlas mobile render failed', err);
        }
      }
    }
    const profileHost = activeEntityDetailHost();
    if (profileHost) profileHost.scrollTop = 0;
    if (focus) {
      profileHost
        ?.querySelector?.(`[data-atlas-profile-view="${selectorValue(next)}"]`)
        ?.focus?.({ preventScroll: true });
    }
    return true;
  }

  function openEntityProfileView(view) {
    if (state.entityProfileMode) return setEntityProfileView(view, { focus: true });
    return enterEntityProfile(view);
  }

  async function openEntityFindingBucket(bucket) {
    const next = String(bucket || '').trim().toLowerCase();
    if (!state.selectedId || !['direct', 'related_urls', 'related_ports', 'combined'].includes(next)) return false;
    if (!state.entityProfileMode) enterEntityProfile('findings');
    state.entityProfileView = 'findings';
    state.entityProfileFindingBucket = next;
    state.detailOffsets = { ...state.detailOffsets, findings: 0 };
    await loadDetail(state.selectedId);
    return true;
  }

  function findingDetailHandlers({ onBack = null, hideInlineActions = false, hideBackAction = false } = {}) {
    return {
      canTriageAtlasRows: canTriageAtlasRows(),
      triageDisabledReason: teamScopeDeniedMessage('triage Atlas findings'),
      canDeleteAtlasRows: canDeleteAtlasRows(),
      deleteDisabledReason: teamScopeDeniedMessage('delete Atlas rows'),
      hideInlineActions,
      hideBackAction,
      onBack,
      onReviewState: (item, reviewState) => updateFindingReviewState(item, reviewState),
      onSeeRun: (item) => openSourceRun({
        id: item.run_id,
        run_id: item.run_id,
        command: item.run_command,
        run_kind: item.run_kind,
      }),
      onOpenEntity: (item) => openEntityFromFinding(item),
      onDeleteFinding: (item) => confirmDeleteFinding(item),
      onEditTriage: (item) => openFindingTriageEditor(item),
      onEditFinding: (item) => editAtlasManualFinding(item),
      onSuppressFinding: (item) => updateSuppression(item, !item.suppressed),
    };
  }

  const mobileRenderers = [];

  function registerMobileRenderer(fn) {
    if (typeof fn !== 'function') return;
    if (!mobileRenderers.includes(fn)) mobileRenderers.push(fn);
    try { fn(state, atlasController); } catch (err) {
      logImportClientError('atlas mobile render failed', err);
    }
  }

  function renderQuickLookup() {
    if (!state.lookupMode || !quickLookupController) return;
    const scopeText = quickLookupController.state.launchScope?.label || 'Personal';
    if (subtitle) subtitle.textContent = `Quick lookup · ${scopeText}`;
    if (lookupElements.profileScope) {
      lookupElements.profileScope.textContent = quickLookupController.profileContextLabel?.() || scopeText;
    }
    if (!quickLookupController.isProfileVisible()) return;
    quickLookupController.syncProfileDetail?.(state.detail);
    renderEntityDetailHost(quickLookupController.profileHost, {
      profileBackLabel: state.entityProfileStack.length ? 'Back to previous entity' : 'Back to lookup',
      onExitProfile: () => exitEntityProfile(),
    });
  }

  function render() {
    ensureMobileAtlasIfNeeded();
    renderShellMode();
    if (state.lookupMode) {
      renderQuickLookup();
      renderIntelRefreshOverlay();
      return;
    }
    renderSubtitle();
    renderFindingControls();
    renderRunFilterControls();
    renderRunFilterChip();
    renderProjectFilterControls();
    renderProjectFilterChip();
    renderTabs();
    renderList();
    renderPagination();
    renderDetail();
    for (const fn of mobileRenderers) {
      try { fn(state, atlasController); } catch (err) {
        logImportClientError('atlas mobile render failed', err);
      }
    }
    renderIntelRefreshOverlay();
  }

  function renderShellMode() {
    surface?.classList.toggle('is-atlas-lookup', !!state.lookupMode);
    if (state.lookupMode) {
      shell?.setAttribute('data-atlas-mode', 'lookup');
      return;
    }
    const mode = state.entityProfileMode
      ? 'profile'
      : (currentTab().id === 'findings' ? 'findings' : 'entity');
    shell?.setAttribute('data-atlas-mode', mode);
  }

  function clearRunFilter() {
    applyRunFilter('', '');
  }

  function clearProjectFilter() {
    applyProjectFilter('', '');
  }

  function clearAtlasFilters() {
    clearTimeout(state.searchTimer);
    clearTimeout(state.runSearchTimer);
    state.query = '';
    state.runId = '';
    state.runLabel = '';
    state.runOptionsQuery = '';
    state.findingStatus = '';
    state.orphanFilter = 'hide';
    state.suppressionFilter = 'hide';
    state.projectId = '';
    state.projectName = '';
    state.selectedSavedViewId = '';
    state.selectedId = '';
    state.selectedFindingId = '';
    state.offset = 0;
    state.requestedEntityValue = '';
    state.requestedView = '';
    state.requestedViewStarted = 0;
    state.refreshIntelOnSelect = false;
    state.addActiveProjectOnSelect = false;
    state.detailOffsets = { runs: 0, findings: 0, related_urls: 0, related_ports: 0 };
    state.detail = null;
    state.detailFinding = null;
    state.entityProfileMode = false;
    resetEntityProfileNavigation();
    resetSelection({ selectMode: false, render: false });
    if (searchInput) searchInput.value = '';
    if (runFilterSearch) runFilterSearch.value = '';
    render();
    loadRunOptions({ query: '', force: true }).catch((err) => {
      logImportClientError('failed to load atlas run filters', err);
    });
    loadProjectOptions({ force: true }).catch((err) => {
      logImportClientError('failed to load atlas project filters', err);
    });
    refreshAtlas({ resetOffset: true, force: true });
  }

  function applyRunFilter(runId, runLabel = '') {
    state.runId = '';
    state.runLabel = '';
    const normalizedRunId = String(runId || '').trim();
    if (normalizedRunId) {
      const matched = state.runOptions.find(run => String(run.id || '') === normalizedRunId);
      state.runId = normalizedRunId;
      state.runLabel = String(runLabel || matched?.command || normalizedRunId).trim();
    }
    state.runOptionsQuery = '';
    state.selectedFindingId = '';
    state.selectedFindingIds.clear();
    state.selectedId = '';
    state.selectedEntityIds.clear();
    state.detailOffsets = { runs: 0, findings: 0, related_urls: 0, related_ports: 0 };
    state.detail = null;
    state.detailFinding = null;
    state.entityProfileMode = false;
    resetEntityProfileNavigation();
    state.requestedEntityValue = '';
    state.requestedView = '';
    state.requestedViewStarted = 0;
    state.refreshIntelOnSelect = false;
    state.addActiveProjectOnSelect = false;
    renderRunFilterControls();
    refreshAtlas({ resetOffset: true });
  }

  function applyProjectFilter(projectId, projectName = '') {
    state.projectId = '';
    state.projectName = '';
    const normalizedProjectId = String(projectId || '').trim();
    if (normalizedProjectId) {
      const matched = state.projectOptions.find(project => String(project.id || '') === normalizedProjectId);
      state.projectId = normalizedProjectId;
      state.projectName = String(projectName || matched?.name || normalizedProjectId).trim();
    }
    state.selectedFindingId = '';
    state.selectedFindingIds.clear();
    state.selectedId = '';
    state.selectedEntityIds.clear();
    state.detailOffsets = { runs: 0, findings: 0, related_urls: 0, related_ports: 0 };
    state.detail = null;
    state.detailFinding = null;
    state.entityProfileMode = false;
    resetEntityProfileNavigation();
    state.requestedEntityValue = '';
    state.requestedView = '';
    state.requestedViewStarted = 0;
    state.refreshIntelOnSelect = false;
    state.addActiveProjectOnSelect = false;
    renderProjectFilterControls();
    refreshAtlas({ resetOffset: true });
  }

  function truncateRunFilterLabel(value) {
    const text = String(value || '').trim() || 'run';
    if (text.length <= 17) return text;
    return `${text.slice(0, 14).trimEnd()}...`;
  }

  function formatTabCount(value) {
    return Math.max(0, Number(value || 0)).toLocaleString();
  }

  function tabCountText(tab) {
    const filtered = tabsApi.countForTab ? tabsApi.countForTab(tab, state.summary) : 0;
    const total = tabsApi.countForTab ? tabsApi.countForTab(tab, state.baseSummary || state.summary) : filtered;
    if (state.runId) return `${formatTabCount(filtered)}/${formatTabCount(total)}`;
    return formatTabCount(filtered);
  }

  function pageHasMore(data, itemCount) {
    if (data && Object.prototype.hasOwnProperty.call(data, 'has_more')) return !!data.has_more;
    const total = Math.max(0, Number(data?.total || 0));
    const limit = Math.max(1, Number(data?.limit || state.limit || 50));
    const offset = Math.max(0, Number(data?.offset || state.offset || 0));
    return offset + limit < total;
  }

  function renderRunFilterChip() {
    if (!runFilterChip) return;
    runFilterChip.replaceChildren();
    const hasRunFilter = !!state.runId;
    runFilterChip.classList.toggle('u-hidden', !hasRunFilter);
    if (!hasRunFilter) return;
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'chip chip-removable';
    chip.textContent = `Run: ${truncateRunFilterLabel(state.runLabel || state.runId)} ×`;
    chip.title = state.runLabel ? `${state.runLabel} (${state.runId})` : state.runId;
    chip.addEventListener('click', clearRunFilter);
    runFilterChip.appendChild(chip);
  }

  function renderProjectFilterChip() {
    if (!projectFilterChip) return;
    projectFilterChip.replaceChildren();
    const hasProjectFilter = !!state.projectId;
    projectFilterChip.classList.toggle('u-hidden', !hasProjectFilter);
    if (!hasProjectFilter) return;
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'chip chip-removable';
    chip.textContent = `Project: ${truncateRunFilterLabel(state.projectName || state.projectId)} ×`;
    chip.title = state.projectName ? `${state.projectName} (${state.projectId})` : state.projectId;
    chip.addEventListener('click', clearProjectFilter);
    projectFilterChip.appendChild(chip);
  }

  async function refreshAtlas({ resetOffset = false, force = false, initialLoad = null } = {}) {
    if (!overlay || (!force && !isOpen())) return;
    if (state.lookupMode) {
      if (state.selectedId) return loadDetail(state.selectedId, { renderLoading: false });
      return null;
    }
    if (resetOffset) state.offset = 0;
    const requestId = state.refreshSeq + 1;
    state.refreshSeq = requestId;
    abortReadRequests();
    const controller = newAbortController();
    atlasLoadController = controller;
    const requestedTab = currentTab();
    const isStale = () => (
      requestId !== state.refreshSeq
      || (!force && !isOpen())
      || (!force && currentTab().id !== requestedTab.id)
    );
    state.loading = true;
    render();
    try {
      const summaryParams = new URLSearchParams({
        orphan_filter: state.orphanFilter,
        suppression_filter: state.suppressionFilter,
      });
      if (state.runId) summaryParams.set('run_id', state.runId);
      if (state.projectId) summaryParams.set('project_id', state.projectId);
      const tab = requestedTab;
      const initial = initialLoad && typeof initialLoad === 'object' ? initialLoad : null;
      const canUseInitialLoad = !!(
        initial
        && initial.tabId === tab.id
        && String(initial.projectId || '') === String(state.projectId || '')
        && String(initial.runId || '') === String(state.runId || '')
        && String(initial.query || '') === String(state.query || '')
        && String(initial.findingStatus || '') === String(state.findingStatus || '')
        && String(initial.orphanFilter || '') === String(state.orphanFilter || '')
        && String(initial.suppressionFilter || '') === String(state.suppressionFilter || '')
        && Number(initial.limit) === Number(state.limit)
        && Number(initial.offset) === Number(state.offset)
        && initial.summaryResp
        && initial.listResp
      );
      const summaryRequest = canUseInitialLoad
        ? initial.summaryResp
        : api()(
            `/atlas?${summaryParams.toString()}`,
            requestOptions(controller, { cache: 'no-store' }),
          );
      let baseSummaryRequest = null;
      if (state.runId) {
        const baseSummaryParams = new URLSearchParams({
          orphan_filter: state.orphanFilter,
          suppression_filter: state.suppressionFilter,
        });
        if (state.projectId) baseSummaryParams.set('project_id', state.projectId);
        baseSummaryRequest = canUseInitialLoad && initial.baseSummaryResp
          ? initial.baseSummaryResp
          : api()(
              `/atlas?${baseSummaryParams.toString()}`,
              requestOptions(controller, { cache: 'no-store' }),
            );
      }
      let listRequest = null;
      if (tab.id === 'findings') {
        const params = new URLSearchParams({
          limit: String(state.limit),
          offset: String(state.offset),
        });
        if (state.query) params.set('q', state.query);
        if (state.projectId) params.set('project_id', state.projectId);
        if (state.runId) params.set('run_id', state.runId);
        if (state.findingStatus) params.append('review_state', state.findingStatus);
        params.set('orphan_filter', state.orphanFilter);
        params.set('suppression_filter', state.suppressionFilter);
        listRequest = canUseInitialLoad
          ? initial.listResp
          : api()(
              `/atlas/findings?${params.toString()}`,
              requestOptions(controller, { cache: 'no-store' }),
            );
      } else {
        const params = new URLSearchParams({
          type: tab.type,
          limit: String(state.limit),
          offset: String(state.offset),
        });
        if (state.query) params.set('q', state.query);
        if (state.projectId) params.set('project_id', state.projectId);
        if (state.runId) params.set('run_id', state.runId);
        params.set('orphan_filter', state.orphanFilter);
        params.set('suppression_filter', state.suppressionFilter);
        listRequest = canUseInitialLoad
          ? initial.listResp
          : api()(
              `/atlas/entities?${params.toString()}`,
              requestOptions(controller, { cache: 'no-store' }),
            );
      }
      const [summaryResp, baseSummaryResp, listResp] = await Promise.all([
        summaryRequest,
        baseSummaryRequest,
        listRequest,
      ]);
      if (!summaryResp.ok) throw new Error(`HTTP ${summaryResp.status}`);
      if (baseSummaryResp && !baseSummaryResp.ok) throw new Error(`HTTP ${baseSummaryResp.status}`);
      if (!listResp.ok) throw new Error(`HTTP ${listResp.status}`);
      if (isStale()) return;
      const [summaryData, baseSummaryData, listData] = await Promise.all([
        summaryResp.json(),
        baseSummaryResp ? baseSummaryResp.json() : Promise.resolve(null),
        listResp.json(),
      ]);
      if (isStale()) return;
      state.summary = summaryData;
      state.baseSummary = baseSummaryData || state.summary;
      if (tab.id === 'findings') {
        const data = listData;
        state.entities = [];
        state.findings = Array.isArray(data.findings) ? data.findings : [];
        state.findingCounts = data.counts && typeof data.counts === 'object' ? data.counts : {};
        state.total = Number(data.total || 0);
        state.totalExact = data.total_exact !== false;
        state.hasMore = pageHasMore(data, state.findings.length);
        state.selectedFindingIds.forEach((findingId) => {
          if (!state.findings.some(finding => String(finding.id || '') === findingId)) {
            state.selectedFindingIds.delete(findingId);
          }
        });
        state.selectedEntityIds.clear();
        if (state.requestedFindingId) {
          const requested = state.findings.find(item => String(item.id || '') === state.requestedFindingId);
          state.selectedFindingId = requested ? String(requested.id || '') : '';
          state.requestedFindingId = '';
        }
        if (!state.selectedFindingId && state.findings[0]) state.selectedFindingId = state.findings[0].id;
        if (state.selectedFindingId && !state.findings.some(item => String(item.id || '') === state.selectedFindingId)) {
          state.selectedFindingId = state.findings[0]?.id || '';
        }
        if (state.selectedFindingId) ensureDetailApi({ renderOnReady: false }).catch(() => {});
        state.detail = null;
      } else {
        state.findings = [];
        state.selectedFindingId = '';
        state.selectedFindingIds.clear();
        const data = listData;
        state.entities = Array.isArray(data.entities) ? data.entities : [];
        state.total = Number(data.total || 0);
        state.totalExact = data.total_exact !== false;
        state.hasMore = pageHasMore(data, state.entities.length);
        if (!state.selectedId && state.requestedEntityValue) {
          const requested = state.requestedEntityValue.toLowerCase();
          const match = state.entities.find(entity => (
            String(entity.canonical_value || entity.value || '').toLowerCase() === requested
          ));
          if (match) {
            state.selectedId = match.id;
            state.detailOffsets = { runs: 0, findings: 0, related_urls: 0, related_ports: 0 };
          }
          else {
            state.refreshIntelOnSelect = false;
            state.addActiveProjectOnSelect = false;
          }
        }
        if (!state.selectedId && !state.requestedEntityValue && state.entities[0]) {
          state.selectedId = state.entities[0].id;
          state.detailOffsets = { runs: 0, findings: 0, related_urls: 0, related_ports: 0 };
        }
        if (!state.selectedId && state.entityProfileMode) {
          state.entityProfileMode = false;
          resetEntityProfileNavigation();
        }
        state.selectedEntityIds.forEach((entityId) => {
          if (!state.entities.some(entity => String(entity.id || '') === entityId)) {
            state.selectedEntityIds.delete(entityId);
          }
        });
      }
      if (isStale()) return;
      state.loading = false;
      render();
      if (state.selectedId) await loadDetail(state.selectedId, { renderLoading: false });
      else state.detail = null;
      if (state.selectedId && state.refreshIntelOnSelect) {
        state.refreshIntelOnSelect = false;
        await refreshIntel();
      }
      if (state.selectedId && state.addActiveProjectOnSelect) {
        state.addActiveProjectOnSelect = false;
        await addToActiveProject();
      }
    } catch (err) {
      if (isAbortError(err)) return;
      logImportClientError('failed to load /atlas', err);
      showToastSafe('Failed to load Atlas', 'error');
    } finally {
      if (atlasLoadController === controller) atlasLoadController = null;
      if (!isStale()) {
        state.loading = false;
        render();
      }
    }
  }

  async function selectEntity(entityId) {
    state.selectedId = String(entityId || '');
    state.detailFinding = null;
    state.detailOffsets = { runs: 0, findings: 0, related_urls: 0, related_ports: 0 };
    state.entityProfileFindingBucket = 'direct';
    state.entityProfileStack = [];
    renderList();
    await loadDetail(state.selectedId);
  }

  async function pageEntityDetail(kind, offset) {
    if (!state.selectedId || !['runs', 'findings', 'related_urls', 'related_ports'].includes(String(kind || ''))) {
      return;
    }
    const returnScrollTop = Number(activeEntityDetailHost()?.scrollTop || 0);
    state.detailOffsets = {
      runs: Math.max(0, Number(state.detailOffsets?.runs || 0)),
      findings: Math.max(0, Number(state.detailOffsets?.findings || 0)),
      related_urls: Math.max(0, Number(state.detailOffsets?.related_urls || 0)),
      related_ports: Math.max(0, Number(state.detailOffsets?.related_ports || 0)),
      [kind]: Math.max(0, Number(offset || 0)),
    };
    await loadDetail(state.selectedId);
    const activeDetailHost = activeEntityDetailHost();
    if (activeDetailHost) activeDetailHost.scrollTop = returnScrollTop;
  }

  function openEntityFindingDetail(finding) {
    if (!finding || !finding.id || !state.selectedId) return;
    state.detailFindingReturnScroll = {
      profile: Number(activeEntityDetailHost()?.scrollTop || 0),
      findingId: String(finding.id),
    };
    state.detailFinding = finding;
    render();
    const activeDetailHost = activeEntityDetailHost();
    if (activeDetailHost) activeDetailHost.scrollTop = 0;
  }

  function closeEntityFindingDetail() {
    if (!state.detailFinding) return;
    const returnScroll = state.detailFindingReturnScroll || {};
    const findingId = String(returnScroll.findingId || state.detailFinding.id || '');
    state.detailFinding = null;
    render();
    const activeDetailHost = activeEntityDetailHost();
    if (activeDetailHost) activeDetailHost.scrollTop = Math.max(0, Number(returnScroll.profile || 0));
    window.setTimeout(() => {
      activeDetailHost
        ?.querySelector?.(`[data-finding-id="${selectorValue(findingId)}"]`)
        ?.focus?.({ preventScroll: true });
    }, 0);
  }

  async function openLinkedProject(link) {
    const projectId = String(link && link.project_id || '').trim();
    if (!projectId || typeof importedOpenProjectWorkspaceById !== 'function') return;
    try {
      await importedOpenProjectWorkspaceById(projectId, {
        returnToAtlas: state.lookupMode ? {
          source: 'project-return',
          launchMode: 'lookup',
          lookupReturnState: captureQuickLookupReturnState(),
        } : {
          source: 'project-return',
          tab: state.activeTab,
          projectId: state.projectId,
          projectName: state.projectName,
          runId: state.runId,
          runLabel: state.runLabel,
          entityValue: String(state.detail?.entity?.canonical_value || ''),
          forceView: state.entityProfileMode ? 'profile' : 'detail',
          profileView: state.entityProfileView,
          findingBucket: state.entityProfileFindingBucket,
        },
      });
    } catch (err) {
      logImportClientError('failed to open linked Atlas project', err);
      showToastSafe('Failed to open Project', 'error');
    }
  }

  function selectFinding(findingId) {
    state.selectedFindingId = String(findingId || '');
    renderList();
    renderDetail();
  }

  async function refreshAfterFindingMutation(findingId, fallbackPatch = {}) {
    if (currentTab().id === 'findings' || !state.selectedId) {
      await refreshAtlas();
      return;
    }
    const previousDetailFinding = String(state.detailFinding?.id || '') === String(findingId || '')
      ? state.detailFinding
      : null;
    const detail = await loadDetail(state.selectedId, { renderLoading: false });
    if (previousDetailFinding && !state.detailFinding) {
      const refreshed = (detail?.findings || [])
        .find(item => String(item?.id || '') === String(findingId || ''));
      state.detailFinding = refreshed || { ...previousDetailFinding, ...fallbackPatch };
      render();
    }
  }

  async function openFindingTriageEditor(finding) {
    const findingId = String(finding && finding.id || state.selectedFindingId || '');
    const current = state.findings.find(item => String(item.id || '') === findingId) || finding;
    if (!current || !findingId) return;
    if (!findingTriageEditor || typeof findingTriageEditor.open !== 'function') {
      throw new Error('Finding triage editor is not available.');
    }
    await findingTriageEditor.open(current, {
      projectId: state.projectId,
      canEdit: canTriageAtlasRows(),
      onSaved: async (triage) => {
        const compact = findingTriageEditor.compactTriage(triage);
        if (currentTab().id !== 'findings' && state.selectedId) {
          await refreshAfterFindingMutation(findingId, {
            triage: compact,
            verification_status: compact.verification_status,
          });
          return;
        }
        state.findings = state.findings.map(item => (
          String(item && item.id || '') === findingId
            ? { ...item, triage: compact, verification_status: compact.verification_status }
            : item
        ));
        renderList();
        renderDetail();
      },
    });
  }

  async function refreshAfterManualFindingSave(action = 'created') {
    if (currentTab().id === 'findings') await refreshAtlas();
    else if (state.selectedId) await loadDetail(state.selectedId, { renderLoading: false });
    broadcastProjectWorkspaceChange('atlas_manual_finding_saved', state.projectId);
    showToastSafe(action === 'updated' ? 'Finding updated' : 'Finding created', 'success');
  }

  async function createFindingForAtlasEntity(entity) {
    const target = entity && typeof entity === 'object' ? entity : state.detail?.entity;
    const targetId = String(target?.id || '');
    if (!state.projectId || !targetId || !['domain', 'ip', 'url'].includes(String(target?.type || ''))) return;
    if (!canTriageAtlasRows()) {
      showAtlasPermissionDenied('create Atlas findings');
      return;
    }
    try {
      if (typeof openContextualFindingRecord !== 'function') throw new Error('Finding editor is unavailable.');
      await openContextualFindingRecord({
        projectId: state.projectId,
        targetId,
        canEdit: true,
        evidence: [{
          evidence_type: 'atlas_entity',
          evidence_id: targetId,
          label: String(target.canonical_value || targetId),
        }],
        onSaved: async () => refreshAfterManualFindingSave('created'),
      });
    } catch (err) {
      logImportClientError('failed to open Atlas finding editor', err);
      showToastSafe(err?.message || 'Failed to open finding editor', 'error');
    }
  }

  async function editAtlasManualFinding(finding) {
    const targetId = String(finding?.entity_id || '');
    if (!state.projectId || !targetId || String(finding?.origin || '') !== 'manual') return;
    if (!canTriageAtlasRows()) {
      showAtlasPermissionDenied('edit Atlas findings');
      return;
    }
    try {
      if (typeof openContextualFindingRecord !== 'function') throw new Error('Finding editor is unavailable.');
      await openContextualFindingRecord({
        projectId: state.projectId,
        targetId,
        finding,
        canEdit: true,
        onSaved: async () => refreshAfterManualFindingSave('updated'),
        onConflict: async () => refreshAfterFindingMutation(finding.id),
      });
    } catch (err) {
      logImportClientError('failed to open Atlas manual finding editor', err);
      showToastSafe(err?.message || 'Failed to open finding editor', 'error');
    }
  }

  async function updateFindingReviewState(finding, reviewState) {
    const findingId = String(finding && finding.id || '');
    if (!findingId || !reviewState) return;
    if (!canTriageAtlasRows()) {
      showAtlasPermissionDenied('triage Atlas findings');
      renderDetail();
      return;
    }
    try {
      const resp = await api()(`/findings/${encodeURIComponent(findingId)}/review`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ review_state: reviewState }),
      });
      if (!resp.ok) throw await atlasMutationError(resp, 'Failed to update finding', 'triage Atlas findings');
      showToastSafe('Finding updated', 'success');
      await refreshAfterFindingMutation(findingId, {
        review_state: reviewState,
        status: reviewState,
      });
    } catch (err) {
      logImportClientError('failed to update atlas finding', err);
      showToastSafe(err && err.message ? err.message : 'Failed to update finding', 'error');
    }
  }

  function openFindingsBoardFromAtlas() {
    if (typeof importedOpenFindingsBoard !== 'function') return;
    void importedOpenFindingsBoard({
      source: 'atlas',
      query: state.query,
      projectId: state.projectId,
      projectName: state.projectName,
      runId: state.runId,
      runLabel: state.runLabel,
      reviewState: state.findingStatus,
      orphanFilter: state.orphanFilter,
      suppressionFilter: state.suppressionFilter,
    }).catch((err) => {
      logImportClientError('failed to open atlas findings board', err);
      showToastSafe('Failed to open Findings Board', 'error');
    });
  }

  async function bulkUpdateFindings(reviewStateOverride = '') {
    const reviewState = String(reviewStateOverride || findingBulkStatus?.value || '').trim();
    const findingIds = [...state.selectedFindingIds];
    if (!findingIds.length || !reviewState) return;
    if (!canTriageAtlasRows()) {
      showAtlasPermissionDenied('triage Atlas findings');
      return;
    }
    try {
      const resp = await api()('/atlas/findings/review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ finding_ids: findingIds, review_state: reviewState }),
      });
      if (!resp.ok) throw await atlasMutationError(resp, 'Failed to update findings', 'triage Atlas findings');
      const data = await resp.json().catch(() => ({}));
      const updated = Number(data?.counts?.updated || 0);
      const notFound = Number(data?.counts?.not_found || 0);
      showToastSafe(
        notFound ? `Updated ${updated} findings · ${notFound} not found` : `Updated ${updated} findings`,
        notFound ? 'warning' : 'success',
      );
      state.selectedFindingIds.clear();
      await refreshAtlas();
    } catch (err) {
      logImportClientError('failed to bulk update atlas findings', err);
      showToastSafe(err && err.message ? err.message : 'Failed to update findings', 'error');
    }
  }

  async function updateSuppression(item, suppressed) {
    const tab = currentTab();
    const isFindings = tab.id === 'findings'
      || (!!item?.entity_id && !item?.canonical_value);
    const itemId = String(item && item.id || '');
    if (!itemId) return;
    if (!canTriageAtlasRows()) {
      showAtlasPermissionDenied('suppress Atlas rows');
      return;
    }
    const url = isFindings
      ? `/atlas/findings/${encodeURIComponent(itemId)}/suppression`
      : `/atlas/entities/${encodeURIComponent(itemId)}/suppression`;
    try {
      const resp = await api()(url, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ suppressed: !!suppressed }),
      });
      if (!resp.ok) throw await atlasMutationError(resp, 'Failed to update Atlas row', 'suppress Atlas rows');
      showToastSafe(suppressed ? 'Atlas row suppressed' : 'Atlas row restored', 'success');
      if (isFindings) {
        await refreshAfterFindingMutation(itemId, { suppressed: !!suppressed });
      } else {
        await refreshAtlas();
      }
    } catch (err) {
      logImportClientError('failed to update atlas suppression', err);
      showToastSafe(err && err.message ? err.message : 'Failed to update Atlas row', 'error');
    }
  }

  async function bulkUpdateSuppression(suppressed) {
    if (state.bulkInFlight) return;
    const tab = currentTab();
    const isFindings = tab.id === 'findings';
    const selected = activeSelectionSet(tab);
    const ids = [...selected];
    if (!ids.length) return;
    if (!canTriageAtlasRows()) {
      showAtlasPermissionDenied('suppress Atlas rows');
      return;
    }
    setBulkBusy(true);
    try {
      const url = isFindings ? '/atlas/findings/suppression' : '/atlas/entities/suppression';
      const body = isFindings
        ? { finding_ids: ids, suppressed: !!suppressed }
        : { entity_ids: ids, suppressed: !!suppressed };
      const resp = await api()(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.ok) throw await atlasMutationError(resp, 'Failed to update selected Atlas rows', 'update Atlas rows');
      const data = await resp.json().catch(() => ({}));
      selected.clear();
      const updated = Number(data?.counts?.updated || 0);
      const notFound = Number(data?.counts?.not_found || 0);
      const verb = suppressed ? 'Suppressed' : 'Restored';
      showToastSafe(
        notFound ? `${verb} ${updated} rows - ${notFound} not found` : `${verb} ${updated} rows`,
        notFound ? 'warning' : 'success',
      );
      await refreshAtlas({ resetOffset: suppressed && state.suppressionFilter === 'hide' });
    } catch (err) {
      logImportClientError('failed to bulk update atlas suppression', err);
      showToastSafe('Failed to update selected Atlas rows', 'error');
    } finally {
      setBulkBusy(false);
    }
  }

  function bulkDeleteNoun(tab, count) {
    if (tab.id === 'findings') return count === 1 ? 'finding' : 'findings';
    return count === 1 ? 'entity' : 'entities';
  }

  function bulkDeleteMessage(tab, counts = {}) {
    const deleted = Number(counts.deleted || 0);
    const notFound = Number(counts.not_found || 0);
    const findingsDeleted = Number(counts.findings_deleted || 0);
    const parts = [`Deleted ${deleted.toLocaleString()} ${bulkDeleteNoun(tab, deleted)}`];
    if (findingsDeleted) {
      parts.push(`${findingsDeleted.toLocaleString()} attached ${findingsDeleted === 1 ? 'finding' : 'findings'} removed`);
    }
    if (notFound) parts.push(`${notFound.toLocaleString()} not found`);
    return parts.join(' - ');
  }

  function setBulkBusy(busy) {
    state.bulkInFlight = !!busy;
    render();
  }

  async function bulkDeleteSelectedItems() {
    if (state.bulkInFlight) return;
    if (!canDeleteAtlasRows()) {
      showAtlasPermissionDenied('delete Atlas rows');
      return;
    }
    const tab = currentTab();
    const isFindings = tab.id === 'findings';
    const selected = activeSelectionSet(tab);
    const ids = [...selected];
    if (!ids.length || typeof showConfirm !== 'function') return;
    setBulkBusy(true);
    const noun = bulkDeleteNoun(tab, ids.length);
    const note = isFindings
      ? 'This removes the selected findings and cannot be undone.'
      : 'This removes the selected entities and any findings attached to them. This cannot be undone.';
    try {
      const choice = await showConfirm({
        body: {
          text: `Delete ${ids.length.toLocaleString()} Atlas ${noun}?`,
          note,
        },
        tone: 'warning',
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'delete', label: 'Delete', role: 'destructive', tone: 'warning' },
        ],
        refocusOnResolve: false,
      });
      if (choice !== 'delete') return;
      const url = isFindings ? '/atlas/findings/bulk-delete' : '/atlas/entities/bulk-delete';
      const body = isFindings ? { finding_ids: ids } : { entity_ids: ids };
      const resp = await api()(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json().catch(() => ({}));
      selected.clear();
      const counts = data && typeof data === 'object' && data.counts ? data.counts : {};
      showToastSafe(bulkDeleteMessage(tab, counts), Number(counts.not_found || 0) ? 'warning' : 'success');
      state.selectedId = '';
      state.selectedFindingId = '';
      state.detail = null;
      state.entityProfileMode = false;
      resetEntityProfileNavigation();
      await refreshAtlas({ resetOffset: state.offset >= state.total - ids.length });
    } catch (err) {
      logImportClientError('failed to bulk delete atlas rows', err);
      showToastSafe(err.message || 'Failed to delete selected Atlas rows', 'error');
    } finally {
      setBulkBusy(false);
    }
  }

  function openEntityFromFinding(finding) {
    const entityId = String(finding && finding.entity_id || '');
    const entityType = String(finding && finding.entity_type || '');
    if (!entityId || !entityType) return;
    if (state.lookupMode && state.entityProfileMode && state.detail) {
      state.entityProfileStack.push(captureEntityProfileSnapshot());
    }
    state.activeTab = entityType;
    state.selectedId = entityId;
    state.selectedFindingId = '';
    state.detailFinding = null;
    state.entityProfileMode = true;
    state.entityProfileView = 'overview';
    state.entityProfileFindingBucket = 'direct';
    if (!state.lookupMode) state.entityProfileStack = [];
    state.detailOffsets = { runs: 0, findings: 0, related_urls: 0, related_ports: 0 };
    resetSelection({ selectMode: state.selectMode, render: false });
    state.query = '';
    if (searchInput) searchInput.value = '';
    if (state.lookupMode) {
      state.entityProfileMode = true;
      render();
      loadDetail(entityId);
      return;
    }
    refreshAtlas({ resetOffset: true });
  }

  function openEntityFromRelatedEntity(entity) {
    const entityId = String(entity && entity.id || '');
    const entityType = String(entity && entity.type || '');
    if (!entityId || !entityType) return;
    if (state.entityProfileMode && state.detail) {
      state.entityProfileStack.push(captureEntityProfileSnapshot());
    }
    state.activeTab = entityType;
    state.selectedId = entityId;
    state.selectedFindingId = '';
    state.detailFinding = null;
    state.detailOffsets = { runs: 0, findings: 0, related_urls: 0, related_ports: 0 };
    state.entityProfileFindingBucket = 'direct';
    resetSelection({ selectMode: state.selectMode, render: false });
    state.query = '';
    if (searchInput) searchInput.value = '';
    if (state.lookupMode) {
      state.entityProfileMode = true;
      render();
      loadDetail(entityId);
      return;
    }
    refreshAtlas({ resetOffset: true });
  }

  async function loadDetail(entityId, { renderLoading = true } = {}) {
    if (!entityId) return;
    abortDetailLoad();
    ensureDetailApi({ renderOnReady: false }).catch(() => {});
    const controller = newAbortController();
    detailLoadController = controller;
    state.detailLoading = !!renderLoading;
    if (renderLoading) {
      if (state.lookupMode) render();
      else renderDetail();
    }
    try {
      const params = new URLSearchParams();
      const runsOffset = Math.max(0, Number(state.detailOffsets?.runs || 0));
      const findingsOffset = Math.max(0, Number(state.detailOffsets?.findings || 0));
      const relatedUrlsOffset = Math.max(0, Number(state.detailOffsets?.related_urls || 0));
      const relatedPortsOffset = Math.max(0, Number(state.detailOffsets?.related_ports || 0));
      if (state.projectId) params.set('project_id', state.projectId);
      if (runsOffset) params.set('runs_offset', String(runsOffset));
      if (findingsOffset) params.set('findings_offset', String(findingsOffset));
      if (state.entityProfileFindingBucket !== 'direct') {
        params.set('finding_bucket', state.entityProfileFindingBucket);
      }
      if (relatedUrlsOffset) params.set('related_urls_offset', String(relatedUrlsOffset));
      if (relatedPortsOffset) params.set('related_ports_offset', String(relatedPortsOffset));
      const query = params.toString();
      const resp = await api()(
        `/atlas/entities/${encodeURIComponent(entityId)}${query ? `?${query}` : ''}`,
        requestOptions(controller, { cache: 'no-store' }),
      );
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const detail = await resp.json();
      if (String(state.selectedId || '') !== String(entityId || '') || currentTab().id === 'findings') return;
      state.detail = detail;
      state.entityProfileFindingBucket = String(detail.detail_limits?.findings?.bucket || 'direct');
      if (state.detailFinding) {
        const findingId = String(state.detailFinding.id || '');
        state.detailFinding = (detail.findings || [])
          .find(finding => String(finding?.id || '') === findingId) || null;
      }
      return detail;
    } catch (err) {
      if (isAbortError(err)) return;
      if (String(state.selectedId || '') !== String(entityId || '')) return;
      state.detail = null;
      state.detailFinding = null;
      logImportClientError('failed to load atlas entity', err);
      showToastSafe('Failed to load entity', 'error');
      return null;
    } finally {
      if (detailLoadController === controller) detailLoadController = null;
      if (String(state.selectedId || '') === String(entityId || '')) {
        state.detailLoading = false;
        render();
      }
    }
  }

  async function refreshIntel() {
    if (!state.selectedId || state.intelRefreshing) return;
    const entityId = String(state.selectedId || '');
    state.intelRefreshing = true;
    state.intelRefreshingEntityId = entityId;
    state.intelRefreshingLabel = entityLabelForId(entityId);
    render();
    try {
      const resp = await api()(`/atlas/entities/${encodeURIComponent(entityId)}/refresh_intel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const payload = typeof resp.json === 'function' ? await resp.json().catch(() => ({})) : {};
      const refresh = payload?.refresh || {};
      const configured = Number(refresh.configured_count || 0);
      const success = Number(refresh.success_count || 0);
      if (configured <= 0) {
        showToastSafe('No intel providers configured', 'warning');
      } else if (success <= 0) {
        showToastSafe('No intel results refreshed', 'warning');
      } else {
        const noun = success === 1 ? 'provider' : 'providers';
        showToastSafe(`Intel refreshed from ${success} ${noun}`, 'success');
      }
      await loadDetail(entityId);
    } catch (err) {
      logImportClientError('failed to refresh atlas intel', err);
      showToastSafe('Failed to refresh intel', 'error');
    } finally {
      state.intelRefreshing = false;
      state.intelRefreshingEntityId = '';
      state.intelRefreshingLabel = '';
      render();
    }
  }

  function cleanupFallbackLabel(cleanup) {
    const entities = Number(cleanup?.entities || 0);
    const findings = Number(cleanup?.findings || 0);
    return `${entities.toLocaleString()} ${entities === 1 ? 'entity' : 'entities'} and `
      + `${findings.toLocaleString()} ${findings === 1 ? 'finding' : 'findings'}`;
  }

  function appendCleanupNote(container, text) {
    if (!text) return;
    const note = document.createElement('div');
    note.className = 'cleanup-reason-note atlas-muted';
    note.textContent = text;
    container.appendChild(note);
  }

  function appendCleanupCheckbox(container, { datasetName, labelText, noteText, checked = false, id = '' }) {
    const label = document.createElement('label');
    label.className = 'form-check';
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = checked;
    if (id) checkbox.id = id;
    checkbox.dataset[datasetName] = '1';
    const textNode = document.createElement('span');
    textNode.textContent = labelText;
    label.append(checkbox, textNode);
    container.appendChild(label);
    appendCleanupNote(container, noteText);
  }

  function deleteCleanupContent(preview, checkboxId) {
    const cleanup = preview?.sibling_cleanup || {};
    const copy = atlasRunCleanupCopy ? atlasRunCleanupCopy(cleanup) : null;
    const hasDisposable = copy ? copy.hasDisposable : !!cleanup.has_cleanup;
    const hasKept = copy ? copy.hasKept : Number(cleanup.curated_total || 0) > 0;
    const notEligibleNote = copy?.notEligibleNote || '';
    if (!preview?.source_run_id || (!hasDisposable && !hasKept && !notEligibleNote)) return null;
    const wrap = document.createElement('div');
    wrap.className = 'atlas-delete-cleanup-option';
    if (hasDisposable) {
      appendCleanupCheckbox(wrap, {
        datasetName: 'atlasDeleteCleanup',
        id: checkboxId,
        labelText: copy?.disposableLabel || 'Also remove disposable Atlas items only sourced by the same run',
        noteText: copy?.disposableNote || `This will remove ${cleanupFallbackLabel(cleanup)}.`,
      });
    }
    if (hasKept) {
      appendCleanupCheckbox(wrap, {
        datasetName: 'atlasDeleteCuratedCleanup',
        labelText: copy?.keptLabel || 'Also delete single-source Atlas items kept by default',
        noteText: copy?.keptNote || 'Single-source Atlas items kept by default will stay unless this is checked.',
      });
    }
    appendCleanupNote(wrap, notEligibleNote);
    const samples = typeof cleanupSampleDetails === 'function'
      ? cleanupSampleDetails(cleanup.cleanup_reasons, { bindDisclosure })
      : null;
    if (samples) wrap.appendChild(samples);
    return wrap;
  }

  async function confirmDeleteEntity() {
    const entityId = String(state.selectedId || '');
    if (!entityId || typeof showConfirm !== 'function') return;
    if (!canDeleteAtlasRows()) {
      showAtlasPermissionDenied('delete Atlas rows');
      return;
    }
    try {
      const previewResp = await api()(`/atlas/entities/${encodeURIComponent(entityId)}/delete-preview`, { cache: 'no-store' });
      if (!previewResp.ok) throw new Error(`HTTP ${previewResp.status}`);
      const preview = (await previewResp.json()).preview || {};
      const checkboxId = `atlas-delete-cleanup-${Date.now()}`;
      const content = deleteCleanupContent(preview, checkboxId);
      const attachedFindings = Number((preview.attached_finding_ids || []).length || 0);
      const note = attachedFindings
        ? `This also removes ${attachedFindings.toLocaleString()} ${attachedFindings === 1 ? 'finding' : 'findings'} attached to this entity.`
        : 'This cannot be undone.';
      const choice = await showConfirm({
        body: { text: 'Delete this Atlas entity?', note },
        content,
        tone: 'danger',
        refocusOnResolve: false,
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'delete', label: 'Delete', role: 'destructive' },
        ],
      });
      if (choice !== 'delete') return;
      const prune = !!content?.querySelector?.('[data-atlas-delete-cleanup]')?.checked
        || !!content?.querySelector?.('[data-atlas-delete-curated-cleanup]')?.checked;
      const pruneCurated = !!content?.querySelector?.('[data-atlas-delete-curated-cleanup]')?.checked;
      const resp = await api()(`/atlas/entities/${encodeURIComponent(entityId)}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prune_source_run: prune, prune_curated_source_run: pruneCurated }),
      });
      if (!resp.ok) throw await atlasMutationError(resp, 'Failed to delete Atlas entity');
      showToastSafe(prune ? 'Entity and related Atlas items deleted' : 'Entity deleted', 'success');
      state.selectedId = '';
      state.detail = null;
      state.detailFinding = null;
      state.entityProfileMode = false;
      resetEntityProfileNavigation();
      await refreshAtlas({ resetOffset: state.offset >= state.total - 1 });
    } catch (err) {
      logImportClientError('failed to delete atlas entity', err);
      showToastSafe(err.message || 'Failed to delete Atlas entity', 'error');
    }
  }

  async function confirmDeleteFinding(finding) {
    const findingId = String(finding?.id || state.selectedFindingId || '');
    if (!findingId || typeof showConfirm !== 'function') return;
    if (!canDeleteAtlasRows()) {
      showAtlasPermissionDenied('delete Atlas rows');
      return;
    }
    try {
      const previewResp = await api()(`/atlas/findings/${encodeURIComponent(findingId)}/delete-preview`, { cache: 'no-store' });
      if (!previewResp.ok) throw new Error(`HTTP ${previewResp.status}`);
      const preview = (await previewResp.json()).preview || {};
      const checkboxId = `atlas-delete-cleanup-${Date.now()}`;
      const content = deleteCleanupContent(preview, checkboxId);
      const choice = await showConfirm({
        body: { text: 'Delete this Atlas finding?', note: 'This cannot be undone.' },
        content,
        tone: 'danger',
        refocusOnResolve: false,
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'delete', label: 'Delete', role: 'destructive' },
        ],
      });
      if (choice !== 'delete') return;
      const prune = !!content?.querySelector?.('[data-atlas-delete-cleanup]')?.checked
        || !!content?.querySelector?.('[data-atlas-delete-curated-cleanup]')?.checked;
      const pruneCurated = !!content?.querySelector?.('[data-atlas-delete-curated-cleanup]')?.checked;
      const resp = await api()(`/atlas/findings/${encodeURIComponent(findingId)}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prune_source_run: prune, prune_curated_source_run: pruneCurated }),
      });
      if (!resp.ok) throw await atlasMutationError(resp, 'Failed to delete Atlas finding');
      showToastSafe(prune ? 'Finding and related Atlas items deleted' : 'Finding deleted', 'success');
      state.selectedFindingId = '';
      state.selectedFindingIds.delete(findingId);
      if (String(state.detailFinding?.id || '') === findingId) state.detailFinding = null;
      await refreshAtlas({ resetOffset: state.offset >= state.total - 1 });
    } catch (err) {
      logImportClientError('failed to delete atlas finding', err);
      showToastSafe(err.message || 'Failed to delete Atlas finding', 'error');
    }
  }

  function openSourceRun(run) {
    const runId = String(run && (run.id || run.run_id) || '');
    if (!runId || typeof importedOpenHistoryRunDetails !== 'function') return;
    importedOpenHistoryRunDetails({ ...run, id: runId });
  }

  async function confirmCleanRunAtlas(run) {
    const runId = String(run && (run.id || run.run_id) || '');
    if (!runId || typeof showConfirm !== 'function') return;
    try {
      const previewResp = await api()(`/atlas/runs/${encodeURIComponent(runId)}/cleanup-preview`, { cache: 'no-store' });
      if (!previewResp.ok) throw new Error(`HTTP ${previewResp.status}`);
      const cleanup = (await previewResp.json()).cleanup || {};
      const copy = atlasRunCleanupCopy ? atlasRunCleanupCopy(cleanup) : null;
      const hasDisposable = copy ? copy.hasDisposable : !!cleanup.has_cleanup;
      const hasKept = copy ? copy.hasKept : Number(cleanup.curated_total || 0) > 0;
      const removalNote = hasDisposable
        ? [
          copy?.disposableLabel
            ? `${copy.disposableLabel.replace(/^Also remove /, 'This will remove ')}.`
            : `This will remove ${cleanupFallbackLabel(cleanup)} that only came from this run.`,
          copy?.disposableNote || '',
        ].filter(Boolean).join(' ')
        : 'No disposable same-run Atlas items were found.';
      const content = document.createElement('div');
      content.className = 'atlas-delete-cleanup-option';
      appendCleanupNote(content, removalNote);
      if (hasKept) {
        appendCleanupCheckbox(content, {
          datasetName: 'atlasCleanCurated',
          labelText: copy?.keptLabel || 'Also delete single-source Atlas items kept by default',
          noteText: copy?.keptNote || 'Single-source Atlas items kept by default will stay unless this is checked.',
        });
      } else {
        appendCleanupNote(content, copy?.notEligibleNote || 'Rows that still have other sources will stay in Atlas.');
      }
      if (hasKept) appendCleanupNote(content, copy?.notEligibleNote || '');
      const choice = await showConfirm({
        body: {
          text: 'Clean this run from Atlas?',
          note: 'The run transcript stays in History. Atlas source links from this run will be removed.',
        },
        content,
        tone: 'danger',
        refocusOnResolve: false,
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'clean', label: 'Clean Atlas', role: 'destructive' },
        ],
      });
      if (choice !== 'clean') return;
      const includeCurated = !!content.querySelector('[data-atlas-clean-curated]')?.checked;
      const resp = await api()(`/atlas/runs/${encodeURIComponent(runId)}/cleanup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ include_curated: includeCurated }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const result = (await resp.json()).cleanup || {};
      showToastSafe('Atlas cleaned for run', 'success');
      if (Number(result.deleted_entities || 0) > 0) {
        state.selectedId = '';
        state.detail = null;
        state.detailFinding = null;
        state.entityProfileMode = false;
        resetEntityProfileNavigation();
      }
      await refreshAtlas({ resetOffset: false });
      if (state.selectedId) await loadDetail(state.selectedId, { renderLoading: false });
    } catch (err) {
      logImportClientError('failed to clean atlas run sources', err);
      showToastSafe('Failed to clean Atlas for run', 'error');
    }
  }

  function exportDownloadName(format) {
    const tab = currentTab();
    const type = tab && tab.type ? String(tab.type) : 'entities';
    const suffix = new Date().toISOString().replace(/[:.]/g, '-');
    return `darklab-atlas-${type}-${suffix}.${format}`;
  }

  function filenameFromDisposition(value) {
    const match = /filename\*?=(?:UTF-8''|")?([^";]+)/i.exec(String(value || ''));
    if (!match) return '';
    try {
      return decodeURIComponent(match[1].replace(/"$/u, ''));
    } catch (_) {
      return match[1].replace(/"$/u, '');
    }
  }

  async function exportEntities(format) {
    if (currentTab().id === 'findings') {
      showToastSafe('Switch to an entity tab before exporting', 'error');
      return;
    }
    if (typeof downloadBlobAsAttachment !== 'function') {
      showToastSafe('Downloads are not available', 'error');
      return;
    }
    const params = new URLSearchParams();
    params.set('format', format);
    const tab = currentTab();
    if (tab.type) params.set('type', tab.type);
    if (state.query) params.set('q', state.query);
    if (state.projectId) params.set('project_id', state.projectId);
    if (state.runId) params.set('run_id', state.runId);
    params.set('orphan_filter', state.orphanFilter);
    params.set('suppression_filter', state.suppressionFilter);
    try {
      const resp = await api()(`/atlas/entities/export?${params.toString()}`, { cache: 'no-store' });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const blob = await resp.blob();
      const filename = filenameFromDisposition(resp.headers?.get?.('content-disposition')) || exportDownloadName(format);
      downloadBlobAsAttachment(blob, filename);
      showToastSafe(`Atlas ${format.toUpperCase()} export started`, 'success');
    } catch (err) {
      logImportClientError('failed to export atlas entities', err);
      showToastSafe('Failed to export Atlas entities', 'error');
    }
  }

  async function addToActiveProject() {
    const activeProject = typeof importedGetActiveProjectContext === 'function'
      ? importedGetActiveProjectContext()
      : null;
    const projectId = activeProject && activeProject.id ? String(activeProject.id) : '';
    if (!projectId || !state.selectedId) {
      showToastSafe('No active project', 'error');
      return;
    }
    try {
      const resp = await api()(`/atlas/entities/${encodeURIComponent(state.selectedId)}/project_links`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      showToastSafe('Added to active project', 'success');
      broadcastProjectWorkspaceChange('atlas_entity_linked', projectId);
      if (typeof importedRefreshActiveProjectContext === 'function') {
        await importedRefreshActiveProjectContext().catch(() => null);
      }
      await refreshAtlas();
    } catch (err) {
      logImportClientError('failed to link atlas entity', err);
      showToastSafe('Failed to add entity to project', 'error');
    }
  }

  async function removeProjectLink(link) {
    const projectId = String(link && link.project_id || '');
    if (!projectId || !state.selectedId) return;
    try {
      const resp = await api()(
        `/atlas/entities/${encodeURIComponent(state.selectedId)}/project_links/${encodeURIComponent(projectId)}`,
        { method: 'DELETE' },
      );
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      showToastSafe('Removed from project', 'success');
      broadcastProjectWorkspaceChange('atlas_entity_unlinked', projectId);
      await refreshAtlas();
    } catch (err) {
      logImportClientError('failed to unlink atlas entity', err);
      showToastSafe('Failed to remove project link', 'error');
    }
  }

  function copyEntityValue(entity) {
    const value = String(entity?.canonical_value || entity?.value || '').trim();
    if (!value || typeof copyTextToClipboard !== 'function') return false;
    return Promise.resolve(copyTextToClipboard(value))
      .then(() => {
        showToastSafe('Entity copied', 'success');
        return true;
      })
      .catch((err) => {
        logImportClientError('failed to copy Atlas entity value', err);
        showToastSafe('Copy failed', 'error');
        return false;
      });
  }

  async function saveMetadata(payload) {
    if (!state.selectedId || !metadataApi.syncEntityLabels || !metadataApi.syncEntityNote) return;
    try {
      const labels = metadataApi.parseLabelInput
        ? metadataApi.parseLabelInput(payload.labels)
        : String(payload.labels || '').split(',').map(item => item.trim()).filter(Boolean);
      await metadataApi.syncEntityLabels('atlas_entity', state.selectedId, labels);
      await metadataApi.syncEntityNote('atlas_entity', state.selectedId, payload.note || '');
      showToastSafe('Metadata saved', 'success');
      await refreshAtlas();
    } catch (err) {
      logImportClientError('failed to save atlas metadata', err);
      showToastSafe('Failed to save metadata', 'error');
    }
  }

  async function applyQuickLookupResult(result) {
    const detail = result && result.detail && typeof result.detail === 'object' ? result.detail : null;
    const entity = detail?.entity || null;
    if (!entity?.id || !entity?.type) return false;
    abortDetailLoad();
    state.activeTab = String(entity.type);
    state.selectedId = String(entity.id);
    state.selectedFindingId = '';
    state.detail = detail;
    state.detailFinding = null;
    state.detailLoading = false;
    state.entityProfileMode = true;
    state.entityProfileView = 'overview';
    state.entityProfileFindingBucket = String(detail.detail_limits?.findings?.bucket || 'direct');
    state.entityProfileStack = [];
    state.detailOffsets = {
      runs: Number(detail.detail_limits?.runs?.offset || 0),
      findings: Number(detail.detail_limits?.findings?.offset || 0),
      related_urls: Number(detail.detail_limits?.related_urls?.offset || 0),
      related_ports: Number(detail.detail_limits?.related_ports?.offset || 0),
    };
    await ensureDetailApi({ renderOnReady: false }).catch(() => null);
    render();
    return true;
  }

  async function resolveQuickLookupCandidate(candidate) {
    const entityId = String(candidate?.entity_id || '');
    const entityType = String(candidate?.type || '');
    if (!entityId || !entityType) return null;
    state.activeTab = entityType;
    state.selectedId = entityId;
    state.selectedFindingId = '';
    state.detail = null;
    state.detailFinding = null;
    state.detailOffsets = { runs: 0, findings: 0, related_urls: 0, related_ports: 0 };
    state.entityProfileFindingBucket = 'direct';
    const detail = await loadDetail(entityId);
    if (!detail) throw new Error('Saved Atlas entity is no longer available in this scope');
    return {
      detected_type: entityType,
      canonical_value: String(candidate.canonical_value || detail.entity?.canonical_value || ''),
      detail,
    };
  }

  async function openQuickLookupResultInAtlas(result, options = {}) {
    const detail = result && result.detail && typeof result.detail === 'object' ? result.detail : null;
    const entity = detail?.entity || null;
    if (!entity?.id || !entity?.type) {
      const detectedType = String(result?.detected_type || '');
      const canonicalValue = String(result?.canonical_value || '').trim();
      if (!canonicalValue || !['domain', 'ip', 'url'].includes(detectedType)) return false;
      return openAtlas({
        source: options.search ? 'quick-lookup-search' : 'quick-lookup',
        tab: detectedType,
        projectId: state.projectId,
        projectName: state.projectName,
        entityValue: canonicalValue,
        forceView: 'list',
        orphanFilter: 'all',
        suppressionFilter: 'all',
      });
    }
    return openAtlas({
      source: 'quick-lookup',
      tab: String(entity.type),
      projectId: state.projectId,
      projectName: state.projectName,
      entityId: String(entity.id),
      entityValue: String(entity.canonical_value || result.canonical_value || ''),
      forceView: 'profile',
      profileView: state.entityProfileView,
      findingBucket: state.entityProfileFindingBucket,
      orphanFilter: Number(detail.detail_limits?.runs?.total) === 0 ? 'all' : 'hide',
      suppressionFilter: entity.suppressed ? 'all' : 'hide',
    });
  }

  function openQuickLookupScopeSelector() {
    if (typeof teamScope?.open === 'function') return teamScope.open();
    showToastSafe('Scope selector is unavailable', 'error');
    return false;
  }

  function prefillQuickLookupCommand(command) {
    const value = String(command || '').trim();
    if (!value || typeof setComposerValue !== 'function') return false;
    closeAtlas({ refocus: false });
    setComposerValue(value, value.length, value.length);
    if (typeof refocusComposerAfterAction === 'function') {
      refocusComposerAfterAction({ defer: true, preventScroll: true });
    }
    return true;
  }

  function handleQuickLookupScopeChange() {
    if (!state.lookupMode || !quickLookupController?.isActive?.()) return;
    abortDetailLoad();
    state.projectId = '';
    state.projectName = '';
    state.launchProjectId = '';
    state.launchProjectName = '';
    state.selectedId = '';
    state.detail = null;
    state.detailFinding = null;
    state.entityProfileMode = false;
    state.entityProfileStack = [];
    quickLookupController.updateScope(currentLookupScope()).catch((err) => {
      logImportClientError('failed to refresh Atlas Quick Lookup after scope change', err);
    });
  }

  function bindEvents() {
    const grab = surface?.querySelector?.(':scope > .sheet-grab') || null;
    const closeControls = surface?.querySelectorAll?.(':scope > .sheet-grab, .atlas-close') || (closeBtn ? [closeBtn] : []);

    closeBtn?.addEventListener('click', () => closeAtlas());
    grab?.addEventListener('click', () => closeAtlas());
    grab?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        closeAtlas();
      }
    });
    refreshBtn?.addEventListener('click', () => refreshAtlas());
    importBtn?.addEventListener('click', () => openImportModal());
    findingsBoardBtn?.addEventListener('click', openFindingsBoardFromAtlas);
    clearFiltersBtn?.addEventListener('click', () => clearAtlasFilters());
    prevBtn?.addEventListener('click', () => {
      state.offset = Math.max(0, state.offset - state.limit);
      refreshAtlas();
    });
    nextBtn?.addEventListener('click', () => {
      state.offset += state.limit;
      refreshAtlas();
    });
    searchInput?.addEventListener('input', () => {
      state.query = String(searchInput.value || '').trim();
      state.requestedEntityValue = '';
      state.refreshIntelOnSelect = false;
      state.addActiveProjectOnSelect = false;
      state.selectedFindingIds.clear();
      state.selectedEntityIds.clear();
      clearTimeout(state.searchTimer);
      state.searchTimer = setTimeout(() => refreshAtlas({ resetOffset: true }), 180);
    });
    runFilterSearch?.addEventListener('input', () => {
      state.runOptionsQuery = String(runFilterSearch.value || '').trim();
      clearTimeout(state.runSearchTimer);
      state.runSearchTimer = setTimeout(() => {
        loadRunOptions({ query: state.runOptionsQuery, force: true });
      }, 180);
    });
    runFilterSearch?.addEventListener('focus', () => {
      loadRunOptions({ query: state.runOptionsQuery, force: !state.runOptionsLoaded });
    });
    runFilterSelect?.addEventListener('change', () => {
      const selected = runFilterSelect.selectedOptions?.[0] || null;
      applyRunFilter(
        runFilterSelect.value,
        selected?.dataset?.runCommand || selected?.textContent || '',
      );
    });
    projectFilterSelect?.addEventListener('focus', () => {
      loadProjectOptions({ force: !state.projectOptionsLoaded });
    });
    projectFilterSelect?.addEventListener('change', () => {
      const selected = projectFilterSelect.selectedOptions?.[0] || null;
      applyProjectFilter(
        projectFilterSelect.value,
        selected?.dataset?.projectName || selected?.textContent || '',
      );
    });
    findingStatusFilter?.addEventListener('change', () => {
      state.findingStatus = String(findingStatusFilter.value || '');
      state.selectedFindingId = '';
      state.selectedFindingIds.clear();
      state.selectedEntityIds.clear();
      refreshAtlas({ resetOffset: true });
    });
    orphanFilter?.addEventListener('change', () => {
      state.orphanFilter = String(orphanFilter.value || 'hide') || 'hide';
      state.selectedId = '';
      state.selectedFindingId = '';
      state.detailOffsets = { runs: 0, findings: 0, related_urls: 0, related_ports: 0 };
      state.selectedFindingIds.clear();
      state.selectedEntityIds.clear();
      state.detail = null;
      state.detailFinding = null;
      state.entityProfileMode = false;
      resetEntityProfileNavigation();
      refreshAtlas({ resetOffset: true });
    });
    suppressionFilter?.addEventListener('change', () => {
      state.suppressionFilter = String(suppressionFilter.value || 'hide') || 'hide';
      state.selectedId = '';
      state.selectedFindingId = '';
      state.detailOffsets = { runs: 0, findings: 0, related_urls: 0, related_ports: 0 };
      state.selectedFindingIds.clear();
      state.selectedEntityIds.clear();
      state.detail = null;
      state.detailFinding = null;
      state.entityProfileMode = false;
      resetEntityProfileNavigation();
      refreshAtlas({ resetOffset: true });
    });
    savedViewSelect?.addEventListener('change', () => {
      applySavedView(savedViewSelect.value);
    });
    savedViewSaveBtn?.addEventListener('click', () => {
      saveCurrentView();
    });
    savedViewUpdateBtn?.addEventListener('click', () => {
      updateCurrentSavedView();
    });
    savedViewDeleteBtn?.addEventListener('click', () => {
      deleteCurrentSavedView();
    });
    savedViewCreateRuleBtn?.addEventListener('click', () => {
      createRuleFromCurrentView();
    });
    selectToggle?.addEventListener('change', () => {
      setSelectMode(!!selectToggle.checked);
    });
    findingSelectAllBtn?.addEventListener('click', () => {
      selectAllVisibleItems();
    });
    findingClearSelectionBtn?.addEventListener('click', () => {
      activeSelectionSet().clear();
      render();
    });
    findingBulkApplyBtn?.addEventListener('click', () => {
      bulkUpdateFindings();
    });
    bulkSuppressionBtn?.addEventListener('click', () => {
      bulkUpdateSuppression(state.suppressionFilter === 'only' ? false : true);
    });
    bulkDeleteBtn?.addEventListener('click', () => {
      bulkDeleteSelectedItems();
    });
    exportMenuBtn?.addEventListener('click', (event) => {
      event.stopPropagation();
      const open = !exportWrap?.classList.contains('open');
      setExportMenuOpen(open);
    });
    exportCsvBtn?.addEventListener('click', () => {
      setExportMenuOpen(false);
      exportEntities('csv');
    });
    exportJsonlBtn?.addEventListener('click', () => {
      setExportMenuOpen(false);
      exportEntities('jsonl');
    });
    importModal?.addEventListener('submit', (event) => {
      event.preventDefault();
      previewImportFile();
    });
    importApplyBtn?.addEventListener('click', () => {
      applyImportPreview();
    });
    importCloseBtn?.addEventListener('click', () => closeImportModal());
    importCancelBtn?.addEventListener('click', () => closeImportModal());
    importFormatSelect?.addEventListener('change', () => {
      syncImportFileAcceptHint();
      if (importNameInput && (!importNameInput.value || state.importFlow.preview)) {
        importNameInput.value = selectedImportFormatLabel();
      }
      resetImportFlow();
      syncSelectDisplay(importFormatSelect);
    });
    importFileInput?.addEventListener('change', () => {
      resetImportFlow();
    });
    importPreviewHost?.addEventListener('change', (event) => {
      if (event.target?.matches?.('[data-atlas-import-option]')) syncImportApplyState();
    });
    syncImportFileAcceptHint();
    ['keydown', 'keyup', 'keypress'].forEach((eventName) => {
      importOverlay?.addEventListener(eventName, event => event.stopPropagation(), true);
    });
    surface?.addEventListener('keydown', (event) => {
      if (!event || event.key !== 'Tab' || !event.altKey || event.ctrlKey || event.metaKey) return;
      if (!cycleAtlasTab(event.shiftKey ? -1 : 1)) return;
      event.preventDefault();
      event.stopPropagation();
    });
    document.addEventListener?.('app:scope-changed', handleQuickLookupScopeChange);
    if (typeof bindOutsideClickClose === 'function' && exportWrap) {
      bindOutsideClickClose(exportWrap, {
        triggers: exportMenuBtn,
        isOpen: () => exportWrap.classList.contains('open'),
        onClose: () => {
          setExportMenuOpen(false);
        },
      });
    }
    if (typeof bindDismissible === 'function' && overlay) {
      bindDismissible(overlay, {
        level: 'panel',
        isOpen,
        onClose: () => closeAtlas(),
        closeButtons: closeControls,
        closeOnBackdrop: true,
      });
    }
    if (typeof bindDismissible === 'function' && importOverlay) {
      bindDismissible(importOverlay, {
        level: 'modal',
        isOpen: () => state.importFlow.open,
        onClose: () => closeImportModal(),
        closeButtons: [importCloseBtn, importCancelBtn].filter(Boolean),
        closeOnBackdrop: true,
      });
    }
    if (typeof bindMobileSheet === 'function' && surface) {
      bindMobileSheet(surface, { onClose: () => closeAtlas() });
    }
    if (typeof bindMobileSheet === 'function' && importModal) {
      bindMobileSheet(importModal, { onClose: () => closeImportModal() });
    }
    if (typeof bindFocusTrap === 'function') {
      if (surface) bindFocusTrap(surface);
      if (importModal) bindFocusTrap(importModal);
    }
  }

  if (typeof importedCreateAtlasQuickLookupMode === 'function' && lookupElements.root) {
    quickLookupController = importedCreateAtlasQuickLookupMode({
      global,
      elements: lookupElements,
      apiFetch: (...args) => api()(...args),
      onFound: applyQuickLookupResult,
      onOpenInAtlas: openQuickLookupResultInAtlas,
      onSelectCandidate: resolveQuickLookupCandidate,
      onSwitchScope: openQuickLookupScopeSelector,
      onPrefillCommand: prefillQuickLookupCommand,
      onReset: abortDetailLoad,
      onStateChange: (lookupState) => {
        const scopeText = lookupState.launchScope?.label || 'Personal';
        if (lookupElements.profileScope) {
          lookupElements.profileScope.textContent = quickLookupController?.profileContextLabel?.() || scopeText;
        }
        if (state.lookupMode) {
          state.entityProfileMode = lookupState.root === 'profile';
          if (subtitle) subtitle.textContent = `Quick lookup · ${scopeText}`;
        }
      },
      onLogEvent: (event, details) => logImportClientError(event, null, {
        event,
        level: 'debug',
        ...details,
      }),
      onError: (err) => logImportClientError('failed to run Atlas Quick Lookup', err),
    });
  }

  ensureBulkActionLayout();
  bindEvents();

  // Controller surface exposed to companion modules (atlas_mobile.js).
  // The surface intentionally hides DOM-binding helpers and keeps the
  // mutation API around state, navigation, actions, and re-render hooks.
  const atlasController = {
    state,
    tabsApi,
    detailApi,
    metadataApi,
    findingStates,
    isOpen,
    currentTab,
    openAtlasQuickLookup,
    setActiveAtlasTab,
    cycleAtlasTab,
    selectEntity,
    enterEntityProfile,
    exitEntityProfile,
    setEntityProfileView,
    openEntityProfileView,
    openEntityFindingBucket,
    pageEntityDetail,
    selectFinding,
    refreshAtlas,
    clearAtlasFilters,
    refreshIntel,
    addToActiveProject,
    openLinkedProject,
    openEntityFindingDetail,
    closeEntityFindingDetail,
    removeProjectLink,
    saveMetadata,
    confirmDeleteEntity,
    confirmDeleteFinding,
    confirmCleanRunAtlas,
    openFindingTriageEditor,
    updateFindingReviewState,
    updateSuppression,
    canTriageAtlasRows,
    openEntityFromFinding,
    openEntityFromRelatedEntity,
    openSourceRun,
    exportEntities,
    loadRunOptions,
    applyRunFilter,
    loadProjectOptions,
    applyProjectFilter,
    loadSavedViews,
    applySavedView,
    saveCurrentView,
    updateCurrentSavedView,
    deleteCurrentSavedView,
    currentAutoPromoteRuleDraft,
    createRuleFromCurrentView,
    setSelectMode,
    selectAllVisibleItems,
    bulkUpdateFindings,
    bulkUpdateSuppression,
    bulkDeleteSelectedItems,
    activeSelectionSet,
    visibleSelectableItems,
    toggleItemSelection,
    rowMessage,
    badge,
    text,
    countLabel,
    registerMobileRenderer,
  };

  exportedDarklabAtlasOverlay = atlasController;
  exportedOpenAtlas = openAtlas;
  exportedOpenAtlasQuickLookup = openAtlasQuickLookup;
  exportedCloseAtlas = closeAtlas;
  exportedIsAtlasOverlayOpen = isOpen;
  exportedRefreshAtlasOverlay = refreshAtlas;
  exportedCycleAtlasTab = cycleAtlasTab;
  if (typeof importedSetAtlasHandlers === 'function') {
    importedSetAtlasHandlers({
      DarklabAtlasOverlay: atlasController,
      openAtlas,
      openAtlasQuickLookup,
      closeAtlas,
      isAtlasOverlayOpen: isOpen,
      refreshAtlasOverlay: refreshAtlas,
      cycleAtlasTab,
    });
  }
})(typeof window !== 'undefined' ? window : globalThis);

export {
  exportedDarklabAtlasOverlay as DarklabAtlasOverlay,
  exportedCloseAtlas as closeAtlas,
  exportedCycleAtlasTab as cycleAtlasTab,
  exportedIsAtlasOverlayOpen as isAtlasOverlayOpen,
  exportedOpenAtlas as openAtlas,
  exportedOpenAtlasQuickLookup as openAtlasQuickLookup,
  exportedRefreshAtlasOverlay as refreshAtlasOverlay,
};
