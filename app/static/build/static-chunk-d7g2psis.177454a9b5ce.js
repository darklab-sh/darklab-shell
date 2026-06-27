import {
  openHistoryCompareLauncher
} from "./static-chunk-72q6vfly.735cac1f206e.js";
import {
  _historyAddRunToProject,
  _historyCanManageHistory,
  _historyConfirmAddRunToProject,
  _historyEditEntityMetadata,
  _historyElapsedLabel,
  _historyEntityLabelValues,
  _historyEntityNoteBody,
  _historyExitLabel,
  _historyLinkRunToProject,
  _historyLoadActiveProject,
  _historyProjectDisplayName,
  _historyRemoveRunFromProject,
  _historyRunProjectLinks,
  _historyScopeDeniedMessage,
  _setHistoryLoadState,
  _tabForHistoryRun,
  confirmHistAction,
  copyHistoryRunPermalink,
  restoreHistoryRunIntoTab
} from "./static-chunk-a6bkphb3.e0b720762ce2.js";
import {
  setHistoryRunModalStateHandlers
} from "./static-chunk-iimv3vvo.e054c6ada14d.js";
import {
  DarklabOutputCore,
  _closeHistoryRunActionMenus,
  _renderAnsiWithEntityTokens,
  activateTab,
  activeTeamScopeCan,
  apiFetch,
  createAnsiUpRenderer,
  getCommandOutcomeSummariesPreference,
  openAtlas,
  resetCmdHistoryNav,
  submitComposerCommand,
  submitComposerCommand2
} from "./static-chunk-q4tud76d.13497a252739.js";
import {
  copyTextToClipboard,
  downloadBlobAsAttachment,
  escapeHtml,
  omitRawOnlyLineEntries,
  showToast
} from "./static-chunk-poi5czx6.3f5c94749765.js";
import {
  bindDismissible
} from "./static-chunk-fik64llj.1291b1f4f79b.js";
import {
  hideHistoryPanel,
  refocusComposerAfterAction,
  setComposerValue,
  syncModalOverlayState
} from "./static-chunk-sgyzdmxn.7d1842f12a94.js";
import {
  getAppConfig
} from "./static-chunk-tym5o2af.a748583ae389.js";
import {
  DarklabAtlasEntityRow
} from "./static-chunk-m4e6ivjw.074a5c89d41e.js";
import {
  DarklabAtlasTabs
} from "./static-chunk-y6zchygr.f5ddd7fe938a.js";

// app/static/js/features/history/history_run_details.js
var HISTORY_RUN_GLOBAL = typeof window !== "undefined" ? window : globalThis;
function _historyRunGlobalFunction(name) {
  const fn = HISTORY_RUN_GLOBAL && HISTORY_RUN_GLOBAL[name];
  return typeof fn === "function" ? fn : null;
}
function _historyRunGlobalValue(name) {
  return HISTORY_RUN_GLOBAL ? HISTORY_RUN_GLOBAL[name] : void 0;
}
var DarklabAtlasEntityRow2 = typeof DarklabAtlasEntityRow !== "undefined" && DarklabAtlasEntityRow || _historyRunGlobalValue("DarklabAtlasEntityRow");
var DarklabAtlasTabs2 = typeof DarklabAtlasTabs !== "undefined" && DarklabAtlasTabs || _historyRunGlobalValue("DarklabAtlasTabs");
var ExportHtmlUtils = _historyRunGlobalValue("ExportHtmlUtils");
function _historyRunAppConfig() {
  if (typeof getAppConfig === "function") return getAppConfig();
  return _historyRunGlobalValue("APP_CONFIG") || {};
}
function _historyRunShowToast(message, tone = "success", options) {
  const toast = typeof showToast !== "undefined" && showToast || _historyRunGlobalFunction("showToast") || null;
  if (typeof toast === "function") toast(message, tone, options);
}
function _historyRunCopyTextToClipboard(value) {
  const copy = typeof copyTextToClipboard !== "undefined" && copyTextToClipboard || _historyRunGlobalFunction("copyTextToClipboard") || null;
  return typeof copy === "function" ? copy(value) : Promise.reject(new Error("Clipboard is not available."));
}
function _historyRunDownloadBlobAsAttachment(blob, filename) {
  const download = typeof downloadBlobAsAttachment !== "undefined" && downloadBlobAsAttachment || _historyRunGlobalFunction("downloadBlobAsAttachment");
  if (typeof download !== "function") return false;
  download(blob, filename);
  return true;
}
function _historyRunActiveTeamScopeCan(capability) {
  const can = typeof activeTeamScopeCan !== "undefined" && activeTeamScopeCan || null;
  return typeof can === "function" ? can(capability) : true;
}
function _historyRunCanManageHistory() {
  const canManage = typeof _historyCanManageHistory !== "undefined" && _historyCanManageHistory || _historyRunGlobalFunction("_historyCanManageHistory");
  return typeof canManage === "function" ? canManage() : _historyRunActiveTeamScopeCan("manage_history");
}
function _historyRunScopeDeniedMessage(action) {
  const denied = typeof _historyScopeDeniedMessage !== "undefined" && _historyScopeDeniedMessage || _historyRunGlobalFunction("_historyScopeDeniedMessage");
  return typeof denied === "function" ? denied(action) : `View-only team members can't ${action}. Switch to Personal or ask for operator access.`;
}
function _historyRunSetComposerValue(value, start = null, end = null, options) {
  const setValue = typeof setComposerValue !== "undefined" && setComposerValue || _historyRunGlobalFunction("setComposerValue");
  if (typeof setValue === "function") setValue(value, start, end, options);
}
function _historyRunHideHistoryPanel() {
  const hide = typeof hideHistoryPanel !== "undefined" && hideHistoryPanel || _historyRunGlobalFunction("hideHistoryPanel");
  if (typeof hide === "function") hide();
}
function _historyRunRefocusComposerAfterAction(options = { preventScroll: true }) {
  const refocus = typeof refocusComposerAfterAction !== "undefined" && refocusComposerAfterAction || _historyRunGlobalFunction("refocusComposerAfterAction");
  if (typeof refocus === "function") refocus(options);
}
function _historyRunTabForRun(run) {
  const tabForRun = typeof _tabForHistoryRun !== "undefined" && _tabForHistoryRun || _historyRunGlobalFunction("_tabForHistoryRun");
  return typeof tabForRun === "function" ? tabForRun(run) : null;
}
function _historyRunActivateTab(tabId) {
  const activate = typeof activateTab !== "undefined" && activateTab || _historyRunGlobalFunction("activateTab");
  if (typeof activate === "function") activate(tabId);
}
function _historyRunSetLoadState(loading) {
  const setState = typeof _setHistoryLoadState !== "undefined" && _setHistoryLoadState || _historyRunGlobalFunction("_setHistoryLoadState");
  if (typeof setState === "function") setState(loading);
}
function _historyRunRestoreIntoTab(run, options) {
  const restore = typeof restoreHistoryRunIntoTab !== "undefined" && restoreHistoryRunIntoTab || _historyRunGlobalFunction("restoreHistoryRunIntoTab");
  return typeof restore === "function" ? restore(run, options) : Promise.reject(new Error("history restore unavailable"));
}
function _historyRunCopyPermalink(run) {
  const copy = typeof copyHistoryRunPermalink !== "undefined" && copyHistoryRunPermalink || _historyRunGlobalFunction("copyHistoryRunPermalink");
  return typeof copy === "function" ? copy(run) : Promise.reject(new Error("permalink unavailable"));
}
function _historyRunOpenCompare(run) {
  const open = typeof openHistoryCompareLauncher !== "undefined" && openHistoryCompareLauncher || _historyRunGlobalFunction("openHistoryCompareLauncher");
  if (typeof open === "function") open(run);
}
function _historyRunConfirmDelete(run) {
  const confirm = typeof confirmHistAction !== "undefined" && confirmHistAction || _historyRunGlobalFunction("confirmHistAction");
  if (typeof confirm === "function") confirm("delete", run.id, run.command);
}
function _historyRunEditMetadata(entityType, entity) {
  const edit = typeof _historyEditEntityMetadata !== "undefined" && _historyEditEntityMetadata || _historyRunGlobalFunction("_historyEditEntityMetadata");
  if (typeof edit === "function") edit(entityType, entity);
}
function _historyRunProjectDisplayName(project) {
  const display = typeof _historyProjectDisplayName !== "undefined" && _historyProjectDisplayName || _historyRunGlobalFunction("_historyProjectDisplayName");
  return typeof display === "function" ? display(project) : "";
}
function _historyRunProjectLinksForRun(run) {
  const links = typeof _historyRunProjectLinks !== "undefined" && _historyRunProjectLinks || _historyRunGlobalFunction("_historyRunProjectLinks");
  return typeof links === "function" ? links(run) : [];
}
function _historyRunLoadActiveProject() {
  const load = typeof _historyLoadActiveProject !== "undefined" && _historyLoadActiveProject || _historyRunGlobalFunction("_historyLoadActiveProject");
  return typeof load === "function" ? load() : Promise.resolve(null);
}
function _historyRunConfirmAddRunToProject(run, project) {
  const confirm = typeof _historyConfirmAddRunToProject !== "undefined" && _historyConfirmAddRunToProject || _historyRunGlobalFunction("_historyConfirmAddRunToProject");
  return typeof confirm === "function" ? confirm(run, project) : Promise.resolve(false);
}
function _historyRunLinkRunToProject(run, project, options) {
  const link = typeof _historyLinkRunToProject !== "undefined" && _historyLinkRunToProject || _historyRunGlobalFunction("_historyLinkRunToProject");
  return typeof link === "function" ? link(run, project, options) : Promise.reject(new Error("project link unavailable"));
}
function _historyRunAddRunToProject(run) {
  const add = typeof _historyAddRunToProject !== "undefined" && _historyAddRunToProject || _historyRunGlobalFunction("_historyAddRunToProject");
  return typeof add === "function" ? add(run) : Promise.reject(new Error("project add unavailable"));
}
function _historyRunRemoveRunFromProject(run) {
  const remove = typeof _historyRemoveRunFromProject !== "undefined" && _historyRemoveRunFromProject || _historyRunGlobalFunction("_historyRemoveRunFromProject");
  return typeof remove === "function" ? remove(run) : Promise.reject(new Error("project remove unavailable"));
}
function _historyRunExitLabel(exitCode) {
  const label = typeof _historyExitLabel !== "undefined" && _historyExitLabel || _historyRunGlobalFunction("_historyExitLabel");
  return typeof label === "function" ? label(exitCode) : `exit ${exitCode ?? "unknown"}`;
}
function _historyRunElapsedLabel(run) {
  const label = typeof _historyElapsedLabel !== "undefined" && _historyElapsedLabel || _historyRunGlobalFunction("_historyElapsedLabel");
  return typeof label === "function" ? label(run) : "";
}
function _historyRunEntityLabelValues(entity) {
  const labels = typeof _historyEntityLabelValues !== "undefined" && _historyEntityLabelValues || _historyRunGlobalFunction("_historyEntityLabelValues");
  return typeof labels === "function" ? labels(entity) : [];
}
function _historyRunEntityNoteBody(entity) {
  const note = typeof _historyEntityNoteBody !== "undefined" && _historyEntityNoteBody || _historyRunGlobalFunction("_historyEntityNoteBody");
  return typeof note === "function" ? note(entity) : "";
}
function _historyRunApiFetch(...args) {
  const fetcher = typeof apiFetch === "function" && apiFetch || _historyRunGlobalFunction("apiFetch");
  if (!fetcher) throw new Error("apiFetch is unavailable");
  return fetcher(...args);
}
function _historyRunSyncModalOverlayState() {
  const sync = typeof syncModalOverlayState !== "undefined" && syncModalOverlayState || _historyRunGlobalFunction("syncModalOverlayState");
  if (typeof sync === "function") sync();
}
function _historyRunBindDismissible(el, opts) {
  const bind = typeof bindDismissible !== "undefined" && bindDismissible || _historyRunGlobalFunction("bindDismissible");
  return typeof bind === "function" ? bind(el, opts) : null;
}
function _historyRunCommandOutcomePreference() {
  const read = typeof getCommandOutcomeSummariesPreference !== "undefined" && getCommandOutcomeSummariesPreference || _historyRunGlobalFunction("getCommandOutcomeSummariesPreference");
  return typeof read === "function" ? read() : null;
}
function _historyRunOutputCore() {
  return typeof DarklabOutputCore !== "undefined" && DarklabOutputCore || _historyRunGlobalValue("DarklabOutputCore") || null;
}
function _historyRunRenderAnsiWithEntityTokens(content, text, entities, tabId) {
  const render = typeof _renderAnsiWithEntityTokens !== "undefined" && _renderAnsiWithEntityTokens || _historyRunGlobalFunction("_renderAnsiWithEntityTokens");
  if (typeof render !== "function") return false;
  render(content, text, entities, tabId);
  return true;
}
function _historyRunSubmitComposerCommand(command, options) {
  const submit = _historyRunGlobalFunction("submitComposerCommand") || typeof submitComposerCommand !== "undefined" && submitComposerCommand || typeof submitComposerCommand2 !== "undefined" && submitComposerCommand2;
  return typeof submit === "function" ? submit(command, options) : null;
}
function _historyRunCreateAnsiUpRenderer() {
  const create = typeof createAnsiUpRenderer !== "undefined" && createAnsiUpRenderer || _historyRunGlobalFunction("createAnsiUpRenderer");
  return typeof create === "function" ? create() : null;
}
function _historyRunEscapeHtml(value) {
  const escape = typeof escapeHtml !== "undefined" && escapeHtml || _historyRunGlobalFunction("escapeHtml");
  return typeof escape === "function" ? escape(value) : String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[ch] || ch);
}
function _historyRunOmitRawOnlyLineEntries(lines) {
  const omit = typeof omitRawOnlyLineEntries !== "undefined" && omitRawOnlyLineEntries || _historyRunGlobalFunction("omitRawOnlyLineEntries");
  return typeof omit === "function" ? omit(lines) : lines;
}
function _historyRunLoadExportPdfUtils() {
  const load = _historyRunGlobalFunction("loadExportPdfUtils");
  return typeof load === "function" ? load() : null;
}
function _historyRunLoadJsPdf(pdfUtils) {
  const load = _historyRunGlobalFunction("loadJsPdf");
  if (typeof load === "function") return load();
  return pdfUtils && typeof pdfUtils.loadJsPdf === "function" ? pdfUtils.loadJsPdf() : null;
}
function _historyRunOpenAtlas(options) {
  const open = typeof openAtlas === "function" && openAtlas || _historyRunGlobalFunction("openAtlas");
  return typeof open === "function" ? open(options) : false;
}
function _historyRunOpenSchedulesModal(options) {
  const open = _historyRunGlobalFunction("openSchedulesModal");
  return typeof open === "function" ? open(options) : false;
}
function _historyRunOpenWatchersModal(options) {
  const open = _historyRunGlobalFunction("openWatchersModal");
  return typeof open === "function" ? open(options) : false;
}
function _historyRunRefreshHistoryPanel() {
  const refresh = _historyRunGlobalFunction("refreshHistoryPanel");
  if (typeof refresh === "function") refresh();
}
function _historyRunResetCmdHistoryNav() {
  const reset = typeof resetCmdHistoryNav !== "undefined" && resetCmdHistoryNav || _historyRunGlobalFunction("resetCmdHistoryNav");
  if (typeof reset === "function") reset();
}
var _historyRunModalState = {
  run: null,
  details: null,
  findings: null,
  findingsPagination: null,
  entitySummary: null,
  entitySummaryLoaded: false,
  entities: null,
  entitiesPagination: null,
  activeEntityTab: "ip",
  projectState: null,
  aiAssists: [],
  aiAssistsLoaded: false,
  loadingAiAssists: false,
  aiSummarySubmitting: false,
  aiNextSubmitting: false,
  aiSummaryError: "",
  aiNextError: "",
  aiAssistPollTimer: null,
  aiThinkingStartedAt: 0,
  activeTab: "summary",
  loadingDetails: false,
  loadingFindings: false,
  loadingEntitySummary: false,
  loadingEntities: false,
  loadingProject: false,
  error: ""
};
var _historyRunModalToken = 0;
var HISTORY_RUN_FINDINGS_PAGE_LIMIT = 50;
var HISTORY_RUN_ENTITIES_PAGE_LIMIT = 50;
var HISTORY_RUN_OUTPUT_OUTLINE_LIMIT = 16;
var HISTORY_RUN_AI_ASSIST_POLL_MS = 2e3;
var HISTORY_RUN_AI_THINKING_PHRASES = [
  "Reading the signal map",
  "Checking the noisy bits",
  "Weighing the findings",
  "Tracing tool signals",
  "Sorting the evidence",
  "Checking command context",
  "Looking for contradictions",
  "Compressing the highlights",
  "Cross-checking findings",
  "Normalizing the odd bits",
  "Preparing the summary",
  "Tightening the summary"
];
function _historyRunCountLabel(count, singular, plural) {
  const numeric = Math.max(0, Number(count || 0));
  return `${numeric.toLocaleString()} ${numeric === 1 ? singular : plural}`;
}
function _historyRunSelectorValue(value) {
  if (typeof CSS !== "undefined" && CSS && typeof CSS.escape === "function") {
    return CSS.escape(String(value));
  }
  return String(value || "").replace(/["\\]/g, "\\$&");
}
function _ensureHistoryRunOverlay() {
  let overlay = document.getElementById("history-run-overlay");
  if (overlay) return overlay;
  overlay = document.createElement("div");
  overlay.id = "history-run-overlay";
  overlay.className = "modal-overlay mobile-sheet-overlay u-hidden history-run-overlay";
  overlay.innerHTML = `
    <section id="history-run-modal" class="history-run-modal mobile-sheet-surface" role="dialog" aria-modal="true" aria-labelledby="history-run-title" tabindex="-1">
      <div class="sheet-grab gesture-handle" role="button" tabindex="0" aria-label="Close run details"></div>
      <div class="history-run-header surface-header">
        <div class="history-run-heading">
          <div id="history-run-title" class="history-run-title">RUN DETAILS</div>
          <div id="history-run-subtitle" class="history-run-subtitle"></div>
        </div>
        <div class="history-run-header-actions">
          <div id="history-run-header-export"></div>
          <button type="button" class="close-btn history-run-close" aria-label="Close run details">✕</button>
        </div>
      </div>
      <div class="history-run-tabs tab-strip" role="tablist" aria-label="Run details sections">
        <button type="button" class="tab-strip-item history-run-tab" data-history-run-tab="summary" role="tab">Summary</button>
        <button type="button" class="tab-strip-item history-run-tab" data-history-run-tab="output" role="tab">Output</button>
        <button type="button" class="tab-strip-item history-run-tab" data-history-run-tab="findings" role="tab">Findings</button>
        <button type="button" class="tab-strip-item history-run-tab" data-history-run-tab="entities" role="tab">Entities</button>
        <button type="button" class="tab-strip-item history-run-tab" data-history-run-tab="artifacts" role="tab">Artifacts</button>
      </div>
      <div id="history-run-body" class="history-run-body surface-body nice-scroll"></div>
    </section>
  `;
  document.body.appendChild(overlay);
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) closeHistoryRunOverlay();
    const exportTrigger = e.target.closest?.(".history-run-export-menu-trigger");
    if (exportTrigger) {
      e.preventDefault();
      e.stopPropagation();
      const wrap = exportTrigger.closest(".history-run-export-menu-wrap");
      if (!wrap) return;
      const open = !wrap.classList.contains("open");
      _closeHistoryRunActionMenus(open ? wrap : null);
      wrap.classList.toggle("open", open);
      exportTrigger.setAttribute("aria-expanded", open ? "true" : "false");
      return;
    }
    const menuTrigger = e.target.closest?.(".history-run-action-menu-trigger");
    if (menuTrigger) {
      e.preventDefault();
      e.stopPropagation();
      const wrap = menuTrigger.closest(".history-run-action-menu-wrap");
      if (!wrap) return;
      const open = !wrap.classList.contains("open");
      _closeHistoryRunActionMenus(open ? wrap : null);
      wrap.classList.toggle("open", open);
      menuTrigger.setAttribute("aria-expanded", open ? "true" : "false");
      return;
    }
    const tab = e.target.closest?.("[data-history-run-tab]");
    if (tab) {
      _setHistoryRunOverlayTab(tab.dataset.historyRunTab || "summary");
      return;
    }
    const findingsPage = e.target.closest?.("[data-history-run-findings-page]");
    if (findingsPage) {
      e.preventDefault();
      _setHistoryRunFindingsPage(findingsPage.dataset.historyRunFindingsPage || "");
      return;
    }
    const entityTab = e.target.closest?.("[data-history-run-entity-tab]");
    if (entityTab) {
      e.preventDefault();
      _setHistoryRunEntityTab(entityTab.dataset.historyRunEntityTab || "");
      return;
    }
    const entityPage = e.target.closest?.("[data-history-run-entities-page]");
    if (entityPage) {
      e.preventDefault();
      _setHistoryRunEntitiesPage(entityPage.dataset.historyRunEntitiesPage || "");
      return;
    }
    const entityRow = e.target.closest?.("[data-history-run-entity-id]");
    if (entityRow) {
      e.preventDefault();
      _openHistoryRunEntityInAtlas(entityRow.dataset.historyRunEntityId || "");
      return;
    }
    const exportAction = e.target.closest?.("[data-history-run-export]");
    if (exportAction) {
      e.preventDefault();
      _closeHistoryRunActionMenus();
      void _handleHistoryRunExport(String(exportAction.dataset.historyRunExport || ""));
      return;
    }
    const suggestionCopy = e.target.closest?.("[data-history-run-copy-suggestion]");
    if (suggestionCopy) {
      e.preventDefault();
      e.stopPropagation();
      if (suggestionCopy.disabled) return;
      const command = String(suggestionCopy.dataset.historyRunCopySuggestion || "");
      if (!command) return;
      _historyRunCopyTextToClipboard(command).then(() => _historyRunShowToast("Suggested command copied")).catch(() => _historyRunShowToast("Failed to copy suggestion", "error"));
      return;
    }
    const suggestionRun = e.target.closest?.("[data-history-run-run-suggestion]");
    if (suggestionRun) {
      e.preventDefault();
      e.stopPropagation();
      if (suggestionRun.disabled) return;
      _runHistoryRunSuggestedCommand(String(suggestionRun.dataset.historyRunRunSuggestion || ""));
      return;
    }
    const action = e.target.closest?.("[data-history-run-action]");
    if (action) {
      e.preventDefault();
      e.stopPropagation();
      _closeHistoryRunActionMenus();
      _handleHistoryRunModalAction(String(action.dataset.historyRunAction || ""));
    }
  });
  overlay.querySelectorAll(".history-run-close, .sheet-grab").forEach((el) => {
    el.addEventListener("click", () => closeHistoryRunOverlay());
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        closeHistoryRunOverlay();
      }
    });
  });
  _historyRunBindDismissible(overlay, {
    level: "modal",
    isOpen: () => overlay.classList.contains("open"),
    onClose: closeHistoryRunOverlay,
    closeButtons: overlay.querySelectorAll(".history-run-close, .sheet-grab")
  });
  return overlay;
}
function closeHistoryRunOverlay() {
  const overlay = document.getElementById("history-run-overlay");
  if (!overlay) return;
  overlay.classList.remove("open");
  overlay.classList.add("u-hidden");
  overlay.setAttribute("aria-hidden", "true");
  _historyRunSyncModalOverlayState();
  _historyRunModalToken += 1;
  _stopHistoryRunAiAssistPolling();
  _closeHistoryRunActionMenus();
}
function _openHistoryRunOverlay() {
  const overlay = _ensureHistoryRunOverlay();
  overlay.classList.remove("u-hidden");
  overlay.classList.add("open");
  overlay.setAttribute("aria-hidden", "false");
  _historyRunSyncModalOverlayState();
  setTimeout(() => {
    overlay.querySelector("#history-run-modal")?.focus({ preventScroll: true });
  }, 0);
}
function isHistoryRunOverlayOpen() {
  const overlay = document.getElementById("history-run-overlay");
  return !!(overlay && overlay.classList.contains("open"));
}
function _setHistoryRunOverlayTab(tabId, { focus = false } = {}) {
  const overlay = _ensureHistoryRunOverlay();
  const nextTab = String(tabId || "summary");
  const tabSelector = `[data-history-run-tab="${_historyRunSelectorValue(nextTab)}"]`;
  if (!overlay.querySelector(tabSelector)) return false;
  _closeHistoryRunActionMenus();
  _historyRunModalState.activeTab = nextTab;
  _renderHistoryRunModal();
  if (focus) {
    setTimeout(() => {
      overlay.querySelector(tabSelector)?.focus({ preventScroll: true });
    }, 0);
  }
  return true;
}
function cycleHistoryRunOverlayTab(offset = 1) {
  const overlay = document.getElementById("history-run-overlay");
  if (!isHistoryRunOverlayOpen() || !overlay) return false;
  const tabs = Array.from(overlay.querySelectorAll("[data-history-run-tab]")).filter((tab) => !tab.disabled);
  if (tabs.length < 2) return false;
  const currentId = String(_historyRunModalState.activeTab || "summary");
  const currentIndex = Math.max(0, tabs.findIndex((tab) => String(tab.dataset.historyRunTab || "") === currentId));
  const nextIndex = (currentIndex + Number(offset || 1) + tabs.length) % tabs.length;
  return _setHistoryRunOverlayTab(tabs[nextIndex].dataset.historyRunTab || "summary");
}
function _historyRunDisplay(run = _historyRunModalState.run) {
  return run && run.command ? String(run.command) : "run";
}
function _historyRunPrimary() {
  return _historyRunModalState.details || _historyRunModalState.run || {};
}
function _historyRunOutputEntries(run) {
  if (Array.isArray(run.output_entries)) {
    return run.output_entries.map((entry) => ({
      text: String(entry && typeof entry === "object" ? entry.text || "" : entry || ""),
      cls: String(entry && typeof entry === "object" ? entry.cls || "" : ""),
      kind: String(entry && typeof entry === "object" ? entry.kind || "" : ""),
      role: String(entry && typeof entry === "object" ? entry.role || "" : ""),
      tsC: String(entry && typeof entry === "object" ? entry.tsC || entry.ts_clock || "" : ""),
      tsE: String(entry && typeof entry === "object" ? entry.tsE || entry.ts_elapsed || "" : ""),
      line_number: Number.isInteger(entry && entry.line_number) ? entry.line_number : void 0,
      signals: Array.isArray(entry && entry.signals) ? entry.signals.map((signal) => String(signal || "")).filter(Boolean) : [],
      entities: Array.isArray(entry && entry.entities) ? entry.entities : []
    }));
  }
  if (Array.isArray(run.output)) {
    return run.output.map((line) => ({ text: String(line || ""), cls: "" }));
  }
  if (run.output_preview) {
    return String(run.output_preview).split(/\r?\n/).map((line) => ({ text: line, cls: "" }));
  }
  return [];
}
function _historyCommandOutcomeSummariesEnabled() {
  const preference = _historyRunCommandOutcomePreference();
  return preference == null ? true : preference !== "off";
}
function _historyNormalizeCommandOutcomeSummary(raw) {
  const outputCore = _historyRunOutputCore();
  const normalizer = outputCore && typeof outputCore.normalizeCommandOutcomeSummary === "function" ? outputCore.normalizeCommandOutcomeSummary : null;
  if (normalizer) return normalizer(raw);
  if (!raw || typeof raw !== "object") return null;
  const title = String(raw.title || raw.heading || "Command outcome").trim() || "Command outcome";
  const sourceItems = Array.isArray(raw.items) ? raw.items : Array.isArray(raw.lines) ? raw.lines : [];
  const items = sourceItems.map((item) => {
    if (item == null) return null;
    if (typeof item !== "object") {
      const value2 = String(item).trim();
      return value2 ? { value: value2 } : null;
    }
    const label = String(item.label || item.key || "").trim();
    const value = String(item.value || item.text || item.summary || "").trim();
    return label || value ? { ...label ? { label } : {}, value } : null;
  }).filter(Boolean);
  return items.length ? { kind: "command_outcome", title, items } : null;
}
function _historyRunCommandOutcomeSummary(run) {
  const explicit = _historyNormalizeCommandOutcomeSummary(
    run && (run.command_outcome_summary || run.output_outcome_summary || run.commandOutcomeSummary)
  );
  if (explicit) return explicit;
  const outputCore = _historyRunOutputCore();
  const builder = outputCore && typeof outputCore.buildCommandOutcomeSummary === "function" ? outputCore.buildCommandOutcomeSummary : null;
  if (!builder) return null;
  return builder(run && run.command || "", _historyRunOutputEntries(run));
}
function _historyCommandOutcomeSummaryToLines(summary) {
  if (ExportHtmlUtils && typeof ExportHtmlUtils.commandOutcomeSummaryToLines === "function") {
    return ExportHtmlUtils.commandOutcomeSummaryToLines(summary);
  }
  if (!summary || !Array.isArray(summary.items) || !summary.items.length) return [];
  const lines = [{
    text: summary.title || "Command outcome",
    cls: "command-outcome-summary command-outcome-summary-title",
    command_outcome_summary: true
  }];
  summary.items.forEach((item) => {
    if (!item || typeof item !== "object") return;
    const label = String(item.label || "").trim();
    const value = String(item.value || "").trim();
    const text = label && value ? `${label}: ${value}` : value || label;
    if (!text) return;
    lines.push({
      text,
      cls: "command-outcome-summary command-outcome-summary-row",
      command_outcome_summary: true
    });
  });
  return lines;
}
function _historyRunMetaRow(label, value) {
  const row = document.createElement("div");
  row.className = "history-run-meta-row";
  const key = document.createElement("span");
  key.textContent = label;
  const val = document.createElement("strong");
  if (value && typeof value === "object" && value.nodeType) {
    val.appendChild(value);
  } else {
    val.textContent = value == null || value === "" ? "—" : String(value);
  }
  row.append(key, val);
  return row;
}
function _historyRunScheduleSummary(run) {
  const scheduleId = String(run?.schedule_id || "").trim();
  const ownerKind = String(run?.schedule_owner_kind || "").trim();
  const ownerId = String(run?.schedule_owner_id || run?.watcher_id || "").trim();
  const isWatcherRun = ownerKind === "watcher" && ownerId;
  const wrap = document.createElement("div");
  wrap.className = "history-run-schedule-summary";
  const label = document.createElement("span");
  label.className = "history-run-schedule-label";
  const ownerLabel = String(run?.schedule_label || run?.schedule_name || "").trim();
  label.textContent = ownerLabel || (isWatcherRun ? "Watcher run" : "Scheduled run");
  wrap.appendChild(label);
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "btn btn-secondary btn-compact history-run-schedule-link";
  btn.dataset.historyRunAction = "open-schedule";
  btn.textContent = isWatcherRun ? "View watcher" : "View schedule";
  if (isWatcherRun) {
    btn.title = `Open watcher ${ownerId}`;
    btn.setAttribute("aria-label", `Open watcher ${ownerId}`);
  } else if (scheduleId) {
    btn.title = `Open schedule ${scheduleId}`;
    btn.setAttribute("aria-label", `Open schedule ${scheduleId}`);
  }
  wrap.appendChild(btn);
  return wrap;
}
function _historyRunActionButton(label, action, { disabled = false, tone = "secondary" } = {}) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = `btn btn-${tone} btn-compact`;
  btn.dataset.historyRunAction = action;
  btn.textContent = label;
  btn.disabled = !!disabled;
  return btn;
}
function _historyRunCanEditMetadata() {
  return _historyRunCanManageHistory();
}
function _historyRunAiSummaryEnabled() {
  const config = _historyRunAppConfig();
  return !!(config && config.ai_enabled && config.ai_feature_summary);
}
function _historyRunAiNextCommandsEnabled() {
  const config = _historyRunAppConfig();
  return !!(config && config.ai_enabled && config.ai_feature_next_commands);
}
function _historyRunAiRunSuggestionsEnabled() {
  const config = _historyRunAppConfig();
  return !!(config && config.ai_enabled && config.ai_feature_next_commands && config.ai_feature_run_suggestions);
}
function _historyRunAiEnabled() {
  return _historyRunAiSummaryEnabled() || _historyRunAiNextCommandsEnabled();
}
function _historyRunLatestSummaryAssist() {
  const assists = Array.isArray(_historyRunModalState.aiAssists) ? _historyRunModalState.aiAssists : [];
  return assists.find((item) => item && String(item.variant || "") === "summary") || null;
}
function _historyRunLatestNextCommandsAssist() {
  const assists = Array.isArray(_historyRunModalState.aiAssists) ? _historyRunModalState.aiAssists : [];
  return assists.find((item) => item && String(item.variant || "") === "next_commands") || null;
}
function _historyRunAssistPending(assist) {
  const status = String(assist?.status || "").toLowerCase();
  return status === "queued" || status === "in_progress";
}
function _historyRunAnyAiAssistPending() {
  const assists = Array.isArray(_historyRunModalState.aiAssists) ? _historyRunModalState.aiAssists : [];
  return assists.some((assist) => {
    return _historyRunAssistPending(assist);
  });
}
function _historyRunAssistStatusLabel(status) {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "in_progress") return "Working";
  if (normalized === "queued") return "Queued";
  if (normalized === "completed") return "Ready";
  if (normalized === "failed") return "Failed";
  return normalized || "Unknown";
}
function _historyRunAiThinkingPhrase(now = Date.now()) {
  if (!_historyRunModalState.aiThinkingStartedAt) {
    _historyRunModalState.aiThinkingStartedAt = now;
  }
  const elapsed = Math.max(0, now - Number(_historyRunModalState.aiThinkingStartedAt || now));
  const index = Math.floor(elapsed / HISTORY_RUN_AI_ASSIST_POLL_MS) % HISTORY_RUN_AI_THINKING_PHRASES.length;
  return HISTORY_RUN_AI_THINKING_PHRASES[index] || HISTORY_RUN_AI_THINKING_PHRASES[0];
}
function _historyRunAiThinkingNode() {
  const wrap = document.createElement("span");
  wrap.className = "history-run-ai-thinking";
  wrap.setAttribute("aria-label", "AI assist is processing");
  const phrase = document.createElement("span");
  phrase.className = "history-run-ai-thinking-phrase";
  phrase.textContent = _historyRunAiThinkingPhrase();
  wrap.appendChild(phrase);
  const dots = document.createElement("span");
  dots.className = "history-run-ai-thinking-dots";
  dots.setAttribute("aria-hidden", "true");
  dots.textContent = "...";
  wrap.appendChild(dots);
  return wrap;
}
function _historyRunAiProgressText(assist, fallbackText) {
  const progress = assist && assist.progress && typeof assist.progress === "object" ? assist.progress : {};
  const parts = [];
  const phase = String(progress.phase || "").replace(/_/g, " ").trim();
  parts.push(phase ? phase.charAt(0).toUpperCase() + phase.slice(1) : fallbackText);
  const elapsedMs = Number(progress.elapsed_ms || 0);
  if (elapsedMs > 0) parts.push(`${Math.max(1, Math.round(elapsedMs / 1e3))}s elapsed`);
  const tokens = Number(progress.tokens_seen || 0);
  if (tokens > 0) {
    parts.push(`${tokens.toLocaleString()} tokens`);
  } else {
    const chars = Number(progress.output_chars_seen || 0);
    if (chars > 0) parts.push(`${chars.toLocaleString()} chars`);
  }
  return parts.join(" · ");
}
function _historyRunCanOpenAtlas(run = _historyRunPrimary()) {
  return String(run?.run_kind || "external") !== "builtin";
}
function _historyRunCanUseAi(run = _historyRunPrimary()) {
  return String(run?.run_kind || "external") !== "builtin";
}
function _historyRunEntityTabs() {
  const atlasTabs = DarklabAtlasTabs2 && Array.isArray(DarklabAtlasTabs2.tabs) ? DarklabAtlasTabs2.tabs : [
    { id: "ip", label: "Hosts/IPs", type: "ip", countKey: "ip" },
    { id: "domain", label: "Domains", type: "domain", countKey: "domain" },
    { id: "hash", label: "Hashes", type: "hash", countKey: "hash" },
    { id: "cve", label: "CVEs", type: "cve", countKey: "cve" },
    { id: "url", label: "URLs", type: "url", countKey: "url" }
  ];
  return atlasTabs.filter((tab) => tab && tab.id !== "findings" && tab.type);
}
function _historyRunActiveEntityTab() {
  const tabs = _historyRunEntityTabs();
  const activeId = String(_historyRunModalState.activeEntityTab || "");
  return tabs.find((tab) => tab.id === activeId) || tabs[0] || { id: "ip", label: "Hosts/IPs", type: "ip", countKey: "ip" };
}
function _historyRunEntityCount(type) {
  const summary = _historyRunModalState.entitySummary || {};
  const counts = summary.counts && typeof summary.counts === "object" ? summary.counts : {};
  return Math.max(0, Number(counts[String(type || "")] || 0));
}
function _historyRunEntityTotal(run = _historyRunPrimary()) {
  const summary = _historyRunModalState.entitySummary || {};
  if (_historyRunModalState.entitySummaryLoaded) return Math.max(0, Number(summary.total || 0));
  return Math.max(0, Number(run.atlas_entity_count || 0));
}
function _historyRunEntityLabel(type) {
  if (DarklabAtlasTabs2 && typeof DarklabAtlasTabs2.labelForType === "function") {
    return DarklabAtlasTabs2.labelForType(type);
  }
  const found = _historyRunEntityTabs().find((tab) => tab.type === String(type || ""));
  return found ? found.label : "Entities";
}
function _historyRunEntityPage() {
  return _historyRunModalState.entitiesPagination || {
    limit: HISTORY_RUN_ENTITIES_PAGE_LIMIT,
    offset: 0,
    total: 0,
    has_more: false,
    loaded: false
  };
}
function _historyRunEntityRow(entity) {
  const rowApi = DarklabAtlasEntityRow2 || {};
  const tab = _historyRunActiveEntityTab();
  if (typeof rowApi.renderAtlasEntityRow === "function") {
    const row2 = rowApi.renderAtlasEntityRow({
      entity,
      text: (value) => String(value ?? "").trim(),
      countLabel: _historyRunCountLabel
    });
    row2.dataset.historyRunEntityId = String(entity && entity.id || "");
    row2.title = "Open this entity in Atlas";
    return row2;
  }
  const row = document.createElement("button");
  row.type = "button";
  row.className = "chrome-row chrome-row-clickable history-run-entity-row";
  row.dataset.historyRunEntityId = String(entity && entity.id || "");
  const title = document.createElement("div");
  title.className = "history-run-list-title";
  title.textContent = entity.canonical_value || entity.id || _historyRunEntityLabel(tab.type);
  const meta = document.createElement("div");
  meta.className = "history-run-list-meta";
  meta.textContent = `${_historyRunCountLabel(entity.occurrence_count || 0, "hit", "hits")} · ${_historyRunCountLabel(entity.run_count || 0, "run", "runs")}`;
  row.append(title, meta);
  return row;
}
function _historyRunActionMenu() {
  const wrap = document.createElement("div");
  wrap.className = "history-run-action-menu-wrap save-menu-wrap";
  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "btn btn-secondary btn-compact history-run-action-menu-trigger";
  trigger.textContent = "Actions";
  trigger.setAttribute("aria-haspopup", "menu");
  trigger.setAttribute("aria-expanded", "false");
  const menu = document.createElement("div");
  menu.className = "history-run-action-menu save-menu dropdown-surface";
  menu.setAttribute("role", "menu");
  const items = [
    ["copy-command", "Copy command"],
    ["schedule-command", "Schedule this command"],
    ["watch-command", "Create watcher from this baseline"]
  ];
  if (_historyRunCanEditMetadata()) items.push(["edit-metadata", "Edit metadata"]);
  if (_historyRunCanOpenAtlas()) items.push(["open-atlas", "Open in Atlas"]);
  const projectLinks = _historyRunProjectLinksForRun(_historyRunPrimary());
  if (projectLinks.length) {
    items.push(["remove-project", "Remove from project"]);
  } else {
    items.push(
      ["add-active-project", "Add to active project"],
      ["add-project", "Add to project"]
    );
  }
  items.push(["copy-run-id", "Copy run ID"]);
  items.forEach(([action, label]) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "dropdown-item dropdown-item-compact";
    item.dataset.historyRunAction = action;
    item.setAttribute("role", "menuitem");
    item.textContent = label;
    menu.appendChild(item);
  });
  wrap.append(trigger, menu);
  return wrap;
}
function _historyRunExportMenu() {
  const wrap = document.createElement("div");
  wrap.className = "history-run-export-menu-wrap save-menu-wrap save-menu-down";
  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "btn btn-secondary btn-compact history-run-export-menu-trigger";
  trigger.textContent = "Export";
  trigger.setAttribute("aria-haspopup", "menu");
  trigger.setAttribute("aria-expanded", "false");
  const menu = document.createElement("div");
  menu.className = "history-run-export-menu save-menu dropdown-surface";
  menu.setAttribute("role", "menu");
  [
    ["txt", "Plain text (.txt)"],
    ["html", "Styled HTML (.html)"],
    ["pdf", "PDF document (.pdf)"]
  ].forEach(([format, label]) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "dropdown-item dropdown-item-compact";
    item.dataset.historyRunExport = format;
    item.setAttribute("role", "menuitem");
    item.textContent = label;
    menu.appendChild(item);
  });
  wrap.append(trigger, menu);
  return wrap;
}
function _historyRunSectionHeader(title, action = null) {
  const header = document.createElement("div");
  header.className = "history-run-section-header";
  const heading = document.createElement("h3");
  heading.textContent = title;
  header.appendChild(heading);
  if (action) header.appendChild(action);
  return header;
}
function _historyRunField(label, content, options = {}) {
  const row = document.createElement("div");
  row.className = `history-run-field${options.className ? ` ${options.className}` : ""}`;
  const key = document.createElement("span");
  key.className = "history-run-field-label";
  key.textContent = label;
  const value = document.createElement("div");
  value.className = "history-run-field-value";
  if (typeof content === "string") {
    value.textContent = content;
  } else if (content) {
    value.appendChild(content);
  }
  row.append(key, value);
  return row;
}
function _renderHistoryRunAiSummary(body) {
  if (!_historyRunAiSummaryEnabled()) return;
  const run = _historyRunPrimary();
  if (!run || !run.id || !run.finished || !_historyRunCanUseAi(run)) return;
  const assist = _historyRunLatestSummaryAssist();
  const status = String(assist?.status || "").toLowerCase();
  const busy = !!_historyRunModalState.loadingAiAssists || !!_historyRunModalState.aiSummarySubmitting || !!_historyRunModalState.aiNextSubmitting || _historyRunAnyAiAssistPending();
  const canRequest = !busy && status !== "queued" && status !== "in_progress";
  const action = _historyRunActionButton(
    status === "failed" ? "Retry" : assist ? "Refresh" : "Summarize",
    "ai-summary",
    { disabled: !canRequest }
  );
  const section = document.createElement("div");
  section.className = "history-run-section history-run-ai-summary";
  section.appendChild(_historyRunSectionHeader("AI summary", action));
  const fields = document.createElement("div");
  fields.className = "history-run-field-list";
  const statusBadge = document.createElement("span");
  statusBadge.className = status === "completed" ? "badge badge-tone-green" : status === "failed" ? "badge badge-tone-red" : "badge badge-tone-muted";
  statusBadge.textContent = busy && !assist ? "Loading" : _historyRunAssistStatusLabel(status);
  fields.appendChild(_historyRunField("Status", statusBadge));
  if (_historyRunModalState.aiSummaryError) {
    const error = document.createElement("div");
    error.className = "history-run-notice is-error";
    error.textContent = _historyRunModalState.aiSummaryError;
    fields.appendChild(_historyRunField("Message", error));
  }
  if (status === "completed") {
    const payload = assist && assist.payload && typeof assist.payload === "object" ? assist.payload : {};
    const summaryText = String(payload.summary || "").trim();
    if (summaryText) {
      const summaryNode = document.createElement("p");
      summaryNode.className = "history-run-ai-summary-copy";
      summaryNode.textContent = summaryText;
      fields.appendChild(_historyRunField("Summary", summaryNode));
    }
    const keyFindings = Array.isArray(payload.key_findings) ? payload.key_findings : [];
    if (keyFindings.length) {
      const list = document.createElement("ul");
      list.className = "history-run-ai-list";
      keyFindings.slice(0, 6).forEach((item) => {
        const li = document.createElement("li");
        li.textContent = String(item || "");
        list.appendChild(li);
      });
      fields.appendChild(_historyRunField("Signals", list));
    }
    const hint = String(payload.next_steps_hint || "").trim();
    if (hint) fields.appendChild(_historyRunField("Next", hint));
    if (!summaryText && !keyFindings.length && !hint) {
      const empty = document.createElement("span");
      empty.className = "history-run-muted";
      empty.textContent = "No summary text was returned.";
      fields.appendChild(_historyRunField("Summary", empty));
    }
  } else if (status === "queued" || status === "in_progress") {
    const pending = document.createElement("span");
    pending.className = "history-run-muted";
    pending.textContent = status === "queued" ? "The AI worker has this run queued." : _historyRunAiProgressText(assist, "The AI worker is summarizing this run.");
    fields.appendChild(_historyRunField("Progress", pending));
    fields.appendChild(_historyRunField("Thinking", _historyRunAiThinkingNode()));
  } else if (status === "failed") {
    const message = document.createElement("div");
    message.className = "history-run-notice is-error";
    message.textContent = assist.error_message || assist.error_code || "The summary could not be generated.";
    fields.appendChild(_historyRunField("Message", message));
  } else if (_historyRunModalState.loadingAiAssists) {
    const loading = document.createElement("span");
    loading.className = "history-run-muted";
    loading.textContent = "Checking cached assists...";
    fields.appendChild(_historyRunField("Summary", loading));
  } else {
    const empty = document.createElement("span");
    empty.className = "history-run-muted";
    empty.textContent = "No AI summary has been generated for this run.";
    fields.appendChild(_historyRunField("Summary", empty));
  }
  section.appendChild(fields);
  body.appendChild(section);
}
function _renderHistoryRunAiNextCommands(body) {
  if (!_historyRunAiNextCommandsEnabled()) return;
  const run = _historyRunPrimary();
  if (!run || !run.id || !run.finished || !_historyRunCanUseAi(run)) return;
  const assist = _historyRunLatestNextCommandsAssist();
  const status = String(assist?.status || "").toLowerCase();
  const busy = !!_historyRunModalState.loadingAiAssists || !!_historyRunModalState.aiSummarySubmitting || !!_historyRunModalState.aiNextSubmitting || _historyRunAnyAiAssistPending();
  const canRequest = !busy && status !== "queued" && status !== "in_progress";
  const action = _historyRunActionButton(
    status === "failed" ? "Retry" : assist ? "Refresh" : "Suggest",
    "ai-next-commands",
    { disabled: !canRequest }
  );
  const section = document.createElement("div");
  section.className = "history-run-section history-run-ai-next-commands";
  section.appendChild(_historyRunSectionHeader("AI next commands", action));
  const fields = document.createElement("div");
  fields.className = "history-run-field-list";
  const statusBadge = document.createElement("span");
  statusBadge.className = status === "completed" ? "badge badge-tone-green" : status === "failed" ? "badge badge-tone-red" : "badge badge-tone-muted";
  statusBadge.textContent = busy && !assist ? "Loading" : _historyRunAssistStatusLabel(status);
  fields.appendChild(_historyRunField("Status", statusBadge));
  if (_historyRunModalState.aiNextError) {
    const error = document.createElement("div");
    error.className = "history-run-notice is-error";
    error.textContent = _historyRunModalState.aiNextError;
    fields.appendChild(_historyRunField("Message", error));
  }
  if (status === "completed") {
    const payload = assist && assist.payload && typeof assist.payload === "object" ? assist.payload : {};
    const suggestions = Array.isArray(payload.suggestions) ? payload.suggestions : [];
    const accepted = suggestions.filter((item) => String(item?.validation_result || "") === "accepted");
    const blocked = suggestions.filter((item) => String(item?.validation_result || "") !== "accepted");
    if (accepted.length) {
      const list = document.createElement("div");
      list.className = "history-run-ai-suggestion-list";
      accepted.forEach((suggestion) => list.appendChild(_historyRunAiSuggestionCard(suggestion)));
      fields.appendChild(_historyRunField("Suggestions", list, { className: "history-run-ai-suggestion-field" }));
    } else if (blocked.length) {
      const empty = document.createElement("span");
      empty.className = "history-run-muted";
      empty.textContent = "No safe command suggestions passed validation.";
      fields.appendChild(_historyRunField("Suggestions", empty));
    } else {
      const empty = document.createElement("span");
      empty.className = "history-run-muted";
      empty.textContent = "No command suggestions were returned.";
      fields.appendChild(_historyRunField("Suggestions", empty));
    }
    if (blocked.length) {
      const blockedList = document.createElement("div");
      blockedList.className = "history-run-ai-suggestion-list";
      blocked.forEach((suggestion) => blockedList.appendChild(_historyRunAiSuggestionCard(suggestion)));
      fields.appendChild(_historyRunField("Blocked", blockedList, { className: "history-run-ai-suggestion-field" }));
    }
  } else if (status === "queued" || status === "in_progress") {
    const pending = document.createElement("span");
    pending.className = "history-run-muted";
    pending.textContent = status === "queued" ? "The AI worker has next-command suggestions queued." : _historyRunAiProgressText(assist, "The AI worker is drafting next commands.");
    fields.appendChild(_historyRunField("Progress", pending));
    fields.appendChild(_historyRunField("Thinking", _historyRunAiThinkingNode()));
  } else if (status === "failed") {
    const message = document.createElement("div");
    message.className = "history-run-notice is-error";
    message.textContent = assist.error_message || assist.error_code || "Suggestions could not be generated.";
    fields.appendChild(_historyRunField("Message", message));
  } else if (_historyRunModalState.loadingAiAssists) {
    const loading = document.createElement("span");
    loading.className = "history-run-muted";
    loading.textContent = "Checking cached assists...";
    fields.appendChild(_historyRunField("Suggestions", loading));
  } else {
    const empty = document.createElement("span");
    empty.className = "history-run-muted";
    empty.textContent = "No AI next-command suggestions have been generated for this run.";
    fields.appendChild(_historyRunField("Suggestions", empty));
  }
  section.appendChild(fields);
  body.appendChild(section);
}
function _historyRunAiSuggestionCard(suggestion) {
  const card = document.createElement("div");
  card.className = "history-run-ai-suggestion-card";
  const command = String(suggestion && suggestion.command || "").trim();
  const valid = String(suggestion && suggestion.validation_result || "") === "accepted";
  const head = document.createElement("div");
  head.className = "history-run-ai-suggestion-head";
  const risk = document.createElement("span");
  risk.className = `badge ${valid ? "badge-tone-green" : "badge-tone-red"}`;
  risk.textContent = valid ? String(suggestion.risk_label || "unknown") : "Blocked";
  const copy = document.createElement("button");
  copy.type = "button";
  copy.className = "btn btn-secondary btn-compact";
  copy.textContent = "Copy";
  copy.dataset.historyRunCopySuggestion = command;
  const run = document.createElement("button");
  run.type = "button";
  run.className = "btn btn-primary btn-compact";
  run.textContent = "Run";
  run.dataset.historyRunRunSuggestion = command;
  const actions = document.createElement("div");
  actions.className = "history-run-ai-suggestion-actions";
  head.appendChild(risk);
  if (valid && command) {
    if (_historyRunAiRunSuggestionsEnabled()) actions.appendChild(run);
    actions.appendChild(copy);
    head.appendChild(actions);
  }
  const code = document.createElement("code");
  code.className = "history-run-ai-suggestion-command";
  code.textContent = command || "(empty command)";
  const reason = document.createElement("p");
  reason.className = "history-run-ai-suggestion-reason";
  reason.textContent = valid ? String(suggestion.reason || "Suggested follow-up command.") : `Rejected: ${String(suggestion.rejection_reason || "policy_rejected")}`;
  card.append(head, code, reason);
  return card;
}
function _runHistoryRunSuggestedCommand(command) {
  const cmd = String(command || "").trim();
  if (!cmd) return;
  const result = _historyRunSubmitComposerCommand(cmd, { dismissKeyboard: true, focusAfterSubmit: true });
  if (result == null) {
    _historyRunSetComposerValue(cmd, cmd.length, cmd.length);
    _historyRunShowToast("Suggested command loaded");
    closeHistoryRunOverlay();
    _historyRunHideHistoryPanel();
    return;
  }
  if (result === true || result === "settle") {
    closeHistoryRunOverlay();
    _historyRunHideHistoryPanel();
  } else {
    _historyRunShowToast("Could not run suggested command", "error");
  }
}
function _renderHistoryRunSummary(body, run) {
  const findingItems = Array.isArray(_historyRunModalState.findings) ? _historyRunModalState.findings : null;
  const findingPagination = _historyRunModalState.findingsPagination || {};
  const uniqueFindingCount = findingPagination.loaded ? Number(findingPagination.total || 0) : findingItems ? findingItems.length : null;
  const occurrenceCount = findingPagination.loaded ? Number(findingPagination.occurrence_total || 0) : Number(run.finding_count || 0);
  const uniqueFindingLabel = uniqueFindingCount == null ? _historyRunModalState.loadingFindings ? "Loading..." : "0" : uniqueFindingCount.toLocaleString();
  const occurrenceLabel = Number.isFinite(occurrenceCount) ? occurrenceCount.toLocaleString() : "0";
  const summary = document.createElement("div");
  summary.className = "history-run-summary-grid";
  const summaryRows = [
    _historyRunMetaRow("Status", _historyRunExitLabel(run.exit_code)),
    _historyRunMetaRow("Started", run.started ? new Date(run.started).toLocaleString() : ""),
    _historyRunMetaRow("Finished", run.finished ? new Date(run.finished).toLocaleString() : ""),
    _historyRunMetaRow("Duration", _historyRunElapsedLabel(run)),
    _historyRunMetaRow("Lines", run.output_line_count ? Number(run.output_line_count).toLocaleString() : ""),
    _historyRunMetaRow("Findings / Occurrences", `${uniqueFindingLabel} / ${occurrenceLabel}`),
    _historyRunMetaRow("Entities", _historyRunEntityTotal(run).toLocaleString()),
    _historyRunMetaRow(
      "Artifacts",
      Number(run.artifact_count || (Array.isArray(run.artifacts) ? run.artifacts.length : 0) || 0).toLocaleString()
    )
  ];
  if (run.schedule_id) {
    summaryRows.splice(1, 0, _historyRunMetaRow("Schedule", _historyRunScheduleSummary(run)));
  }
  summary.append(...summaryRows);
  body.appendChild(summary);
  _renderHistoryRunAiSummary(body);
  _renderHistoryRunAiNextCommands(body);
  const context = document.createElement("div");
  context.className = "history-run-context-grid";
  const metadata = document.createElement("div");
  metadata.className = "history-run-section";
  metadata.appendChild(_historyRunSectionHeader(
    "Metadata",
    _historyRunCanEditMetadata() ? _historyRunActionButton("Edit", "edit-metadata") : null
  ));
  const metadataFields = document.createElement("div");
  metadataFields.className = "history-run-field-list";
  const chips = document.createElement("div");
  chips.className = "history-run-chip-row";
  _historyRunEntityLabelValues(run).forEach((label) => {
    const chip = document.createElement("span");
    chip.className = "badge badge-tone-muted";
    chip.textContent = label;
    chips.appendChild(chip);
  });
  if (!chips.childElementCount) {
    const empty = document.createElement("span");
    empty.className = "history-run-muted";
    empty.textContent = "No labels saved.";
    chips.appendChild(empty);
  }
  metadataFields.appendChild(_historyRunField("Labels", chips));
  const noteText = document.createElement("p");
  noteText.className = "history-run-muted history-run-note-preview";
  noteText.textContent = _historyRunEntityNoteBody(run) || "No notes saved.";
  metadataFields.appendChild(_historyRunField("Notes", noteText));
  metadata.appendChild(metadataFields);
  context.appendChild(metadata);
  const project = document.createElement("div");
  project.className = "history-run-section";
  const projectState = _historyRunModalState.projectState;
  const canAddToProject = !!(projectState && projectState.project && !projectState.attached && !_historyRunModalState.loadingProject);
  project.appendChild(_historyRunSectionHeader(
    "Current project",
    canAddToProject ? _historyRunActionButton("Add", "add-active-project") : null
  ));
  const projectFields = document.createElement("div");
  projectFields.className = "history-run-field-list";
  const projectStatus = document.createElement("span");
  projectStatus.className = "badge badge-tone-muted";
  let projectName = "—";
  if (_historyRunModalState.loadingProject) {
    projectStatus.textContent = "Checking";
  } else if (!projectState || !projectState.project) {
    projectStatus.textContent = "No active project";
  } else if (projectState.attached) {
    projectStatus.className = "badge badge-tone-cyan";
    projectStatus.textContent = "Attached";
    projectName = _historyRunProjectDisplayName(projectState.project);
  } else {
    projectStatus.textContent = "Not attached";
    projectName = _historyRunProjectDisplayName(projectState.project);
  }
  projectFields.appendChild(_historyRunField("Status", projectStatus));
  projectFields.appendChild(_historyRunField("Project", projectName));
  project.appendChild(projectFields);
  context.appendChild(project);
  body.appendChild(context);
  const actions = document.createElement("div");
  actions.className = "history-run-actions history-run-primary-actions";
  const deleteDisabled = !_historyRunCanManageHistory();
  const deleteButton = _historyRunActionButton("Delete", "delete", { disabled: deleteDisabled });
  if (deleteDisabled) {
    deleteButton.title = _historyRunScopeDeniedMessage("delete team history");
  }
  actions.append(
    _historyRunActionButton("Restore", "restore"),
    deleteButton,
    _historyRunActionButton("Permalink", "permalink"),
    _historyRunActionButton("Compare", "compare")
  );
  if (_historyRunCanOpenAtlas(run)) actions.appendChild(_historyRunActionButton("Atlas", "open-atlas"));
  actions.appendChild(_historyRunActionMenu());
  body.appendChild(actions);
}
function _historyOutputSummaryChips(values, emptyLabel) {
  const wrap = document.createElement("div");
  wrap.className = "history-run-chip-row";
  const entries = Object.entries(values && typeof values === "object" ? values : {}).filter(([, count]) => Number(count || 0) > 0).sort((a, b) => String(a[0]).localeCompare(String(b[0])));
  entries.forEach(([key, count]) => {
    const chip = document.createElement("span");
    chip.className = "badge badge-tone-muted";
    chip.textContent = `${key} ${Number(count || 0).toLocaleString()}`;
    wrap.appendChild(chip);
  });
  if (!entries.length) {
    const empty = document.createElement("span");
    empty.className = "history-run-muted";
    empty.textContent = emptyLabel;
    wrap.appendChild(empty);
  }
  return wrap;
}
function _renderHistoryOutputSummary(body, run) {
  const summary = run && run.output_summary && typeof run.output_summary === "object" ? run.output_summary : null;
  if (!summary) return;
  const section = document.createElement("div");
  section.className = "history-run-output-summary";
  const counts = document.createElement("div");
  counts.className = "history-run-section history-run-output-summary-card";
  counts.appendChild(_historyRunSectionHeader("Output summary"));
  const fields = document.createElement("div");
  fields.className = "history-run-field-list history-run-output-summary-fields";
  fields.appendChild(_historyRunField("Kinds", _historyOutputSummaryChips(summary.kinds, "No typed output rows.")));
  fields.appendChild(_historyRunField("Signals", _historyOutputSummaryChips(summary.signals, "No structured signals.")));
  fields.appendChild(_historyRunField("Entities", _historyOutputSummaryChips(summary.entity_types, "No entity tokens.")));
  counts.appendChild(fields);
  section.appendChild(counts);
  const outlineItems = Array.isArray(summary.outline) ? summary.outline : [];
  const signalItems = Array.isArray(summary.signal_toc) ? summary.signal_toc : [];
  if (outlineItems.length || signalItems.length) {
    const outline = document.createElement("div");
    outline.className = "history-run-section history-run-output-outline-card";
    outline.appendChild(_historyRunSectionHeader("Output outline"));
    const list = document.createElement("div");
    list.className = "history-run-field-list history-run-output-outline-list";
    [...outlineItems, ...signalItems].slice(0, HISTORY_RUN_OUTPUT_OUTLINE_LIMIT).forEach((item) => {
      const label = `L${Number(item.line_number || 0).toLocaleString()} · ${item.signal || item.role || "line"}`;
      list.appendChild(_historyRunField(label, String(item.text || "")));
    });
    outline.appendChild(list);
    section.appendChild(outline);
  }
  body.appendChild(section);
}
function _renderHistoryCommandOutcomeSummary(body, run) {
  if (!_historyCommandOutcomeSummariesEnabled()) return;
  const summary = _historyRunCommandOutcomeSummary(run);
  if (!summary) return;
  const section = document.createElement("div");
  section.className = "history-run-section history-run-command-outcome-summary command-outcome-summary";
  section.appendChild(_historyRunSectionHeader(summary.title || "Command outcome"));
  const list = document.createElement("div");
  list.className = "history-run-command-outcome-list";
  summary.items.forEach((item) => {
    const row = document.createElement("div");
    row.className = "history-run-command-outcome-row";
    const label = String(item && item.label || "").trim();
    const value = String(item && item.value || "").trim();
    if (label) {
      const key = document.createElement("span");
      key.className = "history-run-command-outcome-label";
      key.textContent = label;
      row.appendChild(key);
    }
    const text = document.createElement("span");
    text.className = "history-run-command-outcome-value";
    text.textContent = value || label;
    row.appendChild(text);
    list.appendChild(row);
  });
  section.appendChild(list);
  body.appendChild(section);
}
function _renderHistoryRunOutput(body, run) {
  const output = _historyRunOutputEntries(run);
  const outcomeSummary = _historyRunCommandOutcomeSummary(run);
  if (!output.length && _historyRunModalState.loadingDetails) {
    const loading = document.createElement("div");
    loading.className = "history-run-empty";
    loading.textContent = "Loading output preview...";
    body.appendChild(loading);
    return;
  }
  if (!output.length) {
    const empty = document.createElement("div");
    empty.className = "history-run-empty";
    empty.textContent = "No saved output preview is available.";
    body.appendChild(empty);
    if (outcomeSummary) _renderHistoryCommandOutcomeSummary(body, run);
    return;
  }
  _renderHistoryOutputSummary(body, run);
  const pre = document.createElement("pre");
  pre.className = "history-run-output";
  output.forEach((entry, index) => {
    const line = document.createElement("span");
    line.className = "history-run-output-line";
    const text = String(entry.text || "");
    if (!_historyRunRenderAnsiWithEntityTokens(line, text, Array.isArray(entry.entities) ? entry.entities : [], "")) {
      line.textContent = text;
    }
    pre.appendChild(line);
    if (index < output.length - 1) pre.appendChild(document.createTextNode("\n"));
  });
  body.appendChild(pre);
  _renderHistoryCommandOutcomeSummary(body, run);
  if (run.preview_notice) {
    const notice = document.createElement("div");
    notice.className = "history-run-notice";
    notice.textContent = run.preview_notice;
    body.appendChild(notice);
  }
}
function _renderHistoryRunFindings(body) {
  if (_historyRunModalState.loadingFindings && _historyRunModalState.findings == null) {
    const loading = document.createElement("div");
    loading.className = "history-run-empty";
    loading.textContent = "Loading findings...";
    body.appendChild(loading);
    return;
  }
  const findings = Array.isArray(_historyRunModalState.findings) ? _historyRunModalState.findings : [];
  const pager = _renderHistoryRunFindingsPagination(findings);
  if (!findings.length) {
    const empty = document.createElement("div");
    empty.className = "history-run-empty";
    empty.textContent = "No structured findings recorded for this run.";
    body.appendChild(empty);
    if (pager) body.appendChild(pager);
    return;
  }
  if (pager) body.appendChild(pager);
  const list = document.createElement("div");
  list.className = "history-run-list";
  findings.forEach((finding) => {
    const item = document.createElement("div");
    item.className = "history-run-list-item";
    const title = document.createElement("div");
    title.className = "history-run-list-title";
    title.textContent = finding.title || finding.raw_line || "Finding";
    const meta = document.createElement("div");
    meta.className = "history-run-list-meta";
    const parts = [
      finding.severity ? `severity: ${finding.severity}` : "",
      finding.review_state ? `review: ${finding.review_state}` : "",
      Number.isFinite(Number(finding.line_number)) ? `line ${Number(finding.line_number) + 1}` : "",
      Number(finding.run_occurrence_count || 0) > 1 ? `${Number(finding.run_occurrence_count).toLocaleString()} occurrences` : "",
      finding.scope ? `scope: ${finding.scope}` : ""
    ].filter(Boolean);
    meta.textContent = parts.join(" · ");
    item.append(title, meta);
    if (finding.raw_line && finding.raw_line !== finding.title) {
      const raw = document.createElement("code");
      raw.className = "history-run-finding-raw";
      raw.textContent = finding.raw_line;
      item.appendChild(raw);
    }
    list.appendChild(item);
  });
  body.appendChild(list);
  if (pager) body.appendChild(_renderHistoryRunFindingsPagination(findings));
}
function _renderHistoryRunFindingsPagination(findings) {
  const pagination = _historyRunModalState.findingsPagination || {};
  const limit = Math.max(1, Number(pagination.limit || HISTORY_RUN_FINDINGS_PAGE_LIMIT));
  const offset = Math.max(0, Number(pagination.offset || 0));
  const total = Math.max(0, Number(pagination.total || findings.length || 0));
  if (total <= limit && offset === 0) return null;
  const start = total && findings.length ? offset + 1 : 0;
  const end = total && findings.length ? Math.min(total, offset + findings.length) : 0;
  const wrap = document.createElement("div");
  wrap.className = "history-run-findings-pagination history-pagination";
  const summary = document.createElement("div");
  summary.className = "history-pagination-summary";
  summary.textContent = `${start}-${end} of ${total.toLocaleString()} findings`;
  const controls = document.createElement("div");
  controls.className = "history-pagination-controls";
  const prev = document.createElement("button");
  prev.type = "button";
  prev.className = "btn btn-secondary btn-compact";
  prev.dataset.historyRunFindingsPage = "prev";
  prev.disabled = offset <= 0 || _historyRunModalState.loadingFindings;
  prev.textContent = "Previous";
  const status = document.createElement("span");
  status.className = "history-pagination-status";
  status.textContent = `Page ${Math.floor(offset / limit) + 1}`;
  const next = document.createElement("button");
  next.type = "button";
  next.className = "btn btn-secondary btn-compact";
  next.dataset.historyRunFindingsPage = "next";
  next.disabled = offset + findings.length >= total || _historyRunModalState.loadingFindings;
  next.textContent = "Next";
  controls.append(prev, status, next);
  wrap.append(summary, controls);
  return wrap;
}
function _renderHistoryRunEntityTabs(body) {
  const tabs = _historyRunEntityTabs();
  if (!tabs.length) return;
  const strip = document.createElement("div");
  strip.className = "history-run-entity-tabs tab-strip";
  strip.setAttribute("role", "tablist");
  strip.setAttribute("aria-label", "Run Atlas entity types");
  const activeId = _historyRunActiveEntityTab().id;
  tabs.forEach((tab) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "tab-strip-item history-run-entity-tab";
    button.classList.toggle("is-active", tab.id === activeId);
    button.dataset.historyRunEntityTab = tab.id;
    button.setAttribute("role", "tab");
    button.setAttribute("aria-selected", tab.id === activeId ? "true" : "false");
    button.textContent = `${tab.label} (${_historyRunEntityCount(tab.type).toLocaleString()})`;
    strip.appendChild(button);
  });
  body.appendChild(strip);
}
function _renderHistoryRunEntities(body) {
  _renderHistoryRunEntityTabs(body);
  const panel = document.createElement("div");
  panel.className = "history-run-entity-panel";
  body.appendChild(panel);
  if (_historyRunModalState.loadingEntities && _historyRunModalState.entities == null) {
    const loading = document.createElement("div");
    loading.className = "history-run-empty";
    loading.textContent = "Loading Atlas entities...";
    panel.appendChild(loading);
    return;
  }
  const entities = Array.isArray(_historyRunModalState.entities) ? _historyRunModalState.entities : [];
  const pager = _renderHistoryRunEntitiesPagination(entities);
  if (!entities.length) {
    const empty = document.createElement("div");
    empty.className = "history-run-empty";
    const tab = _historyRunActiveEntityTab();
    empty.textContent = `No ${_historyRunEntityLabel(tab.type).toLowerCase()} recorded for this run.`;
    panel.appendChild(empty);
    if (pager) panel.appendChild(pager);
    return;
  }
  if (pager) panel.appendChild(pager);
  const list = document.createElement("div");
  list.className = "history-run-entity-list nice-scroll";
  entities.forEach((entity) => list.appendChild(_historyRunEntityRow(entity)));
  panel.appendChild(list);
  if (pager) panel.appendChild(_renderHistoryRunEntitiesPagination(entities));
}
function _renderHistoryRunEntitiesPagination(entities) {
  const pagination = _historyRunEntityPage();
  const limit = Math.max(1, Number(pagination.limit || HISTORY_RUN_ENTITIES_PAGE_LIMIT));
  const offset = Math.max(0, Number(pagination.offset || 0));
  const total = Math.max(0, Number(pagination.total || entities.length || 0));
  if (total <= limit && offset === 0) return null;
  const start = total && entities.length ? offset + 1 : 0;
  const end = total && entities.length ? Math.min(total, offset + entities.length) : 0;
  const wrap = document.createElement("div");
  wrap.className = "history-run-entities-pagination history-pagination";
  const summary = document.createElement("div");
  summary.className = "history-pagination-summary";
  summary.textContent = `${start}-${end} of ${total.toLocaleString()} entities`;
  const controls = document.createElement("div");
  controls.className = "history-pagination-controls";
  const prev = document.createElement("button");
  prev.type = "button";
  prev.className = "btn btn-secondary btn-compact";
  prev.dataset.historyRunEntitiesPage = "prev";
  prev.disabled = offset <= 0 || _historyRunModalState.loadingEntities;
  prev.textContent = "Previous";
  const status = document.createElement("span");
  status.className = "history-pagination-status";
  status.textContent = `Page ${Math.floor(offset / limit) + 1}`;
  const next = document.createElement("button");
  next.type = "button";
  next.className = "btn btn-secondary btn-compact";
  next.dataset.historyRunEntitiesPage = "next";
  next.disabled = offset + entities.length >= total || _historyRunModalState.loadingEntities;
  next.textContent = "Next";
  controls.append(prev, status, next);
  wrap.append(summary, controls);
  return wrap;
}
function _renderHistoryRunArtifacts(body, run) {
  const artifacts = Array.isArray(run.artifacts) ? run.artifacts : [];
  if (_historyRunModalState.loadingDetails && !artifacts.length) {
    const loading = document.createElement("div");
    loading.className = "history-run-empty";
    loading.textContent = "Loading artifacts...";
    body.appendChild(loading);
    return;
  }
  if (!artifacts.length) {
    const empty = document.createElement("div");
    empty.className = "history-run-empty";
    empty.textContent = "No workspace artifacts recorded for this run.";
    body.appendChild(empty);
    return;
  }
  const list = document.createElement("div");
  list.className = "history-run-list";
  artifacts.forEach((artifact) => {
    const item = document.createElement("div");
    item.className = "history-run-list-item";
    const title = document.createElement("div");
    title.className = "history-run-list-title";
    title.textContent = artifact.display_name || artifact.workspace_path || "artifact";
    const meta = document.createElement("div");
    meta.className = "history-run-list-meta";
    meta.textContent = [
      artifact.kind || "",
      artifact.workspace_path || "",
      artifact.byte_size ? `${Number(artifact.byte_size).toLocaleString()} bytes` : ""
    ].filter(Boolean).join(" · ");
    item.append(title, meta);
    list.appendChild(item);
  });
  body.appendChild(list);
}
function _renderHistoryRunModal() {
  const overlay = _ensureHistoryRunOverlay();
  const run = _historyRunPrimary();
  const subtitle = overlay.querySelector("#history-run-subtitle");
  if (subtitle) subtitle.textContent = _historyRunDisplay(run);
  const headerExport = overlay.querySelector("#history-run-header-export");
  if (headerExport && !headerExport.childElementCount) {
    headerExport.replaceChildren(_historyRunExportMenu());
  }
  overlay.querySelectorAll("[data-history-run-tab]").forEach((tab) => {
    const active = String(tab.dataset.historyRunTab || "") === _historyRunModalState.activeTab;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", active ? "true" : "false");
    tab.setAttribute("aria-pressed", active ? "true" : "false");
  });
  const findingsTab = overlay.querySelector('[data-history-run-tab="findings"]');
  if (findingsTab) {
    const pagination = _historyRunModalState.findingsPagination || {};
    const count = pagination.loaded ? Number(pagination.total || 0) : Array.isArray(_historyRunModalState.findings) ? _historyRunModalState.findings.length : 0;
    findingsTab.textContent = count ? `Findings (${count})` : "Findings";
  }
  const entitiesTab = overlay.querySelector('[data-history-run-tab="entities"]');
  if (entitiesTab) {
    const count = _historyRunEntityTotal(run);
    entitiesTab.textContent = count ? `Entities (${count})` : "Entities";
  }
  const artifactsTab = overlay.querySelector('[data-history-run-tab="artifacts"]');
  if (artifactsTab) {
    const count = Number(run.artifact_count || (Array.isArray(run.artifacts) ? run.artifacts.length : 0) || 0);
    artifactsTab.textContent = count ? `Artifacts (${count})` : "Artifacts";
  }
  const body = overlay.querySelector("#history-run-body");
  if (!body) return;
  body.classList.toggle("history-run-body-entities", _historyRunModalState.activeTab === "entities");
  body.replaceChildren();
  if (_historyRunModalState.error) {
    const error = document.createElement("div");
    error.className = "history-run-notice is-error";
    error.textContent = _historyRunModalState.error;
    body.appendChild(error);
  }
  if (_historyRunModalState.activeTab === "output") _renderHistoryRunOutput(body, run);
  else if (_historyRunModalState.activeTab === "findings") _renderHistoryRunFindings(body);
  else if (_historyRunModalState.activeTab === "entities") _renderHistoryRunEntities(body);
  else if (_historyRunModalState.activeTab === "artifacts") _renderHistoryRunArtifacts(body, run);
  else _renderHistoryRunSummary(body, run);
}
function _stopHistoryRunAiAssistPolling() {
  const timer = _historyRunModalState.aiAssistPollTimer;
  if (timer) {
    clearTimeout(timer);
    _historyRunModalState.aiAssistPollTimer = null;
  }
}
function _scheduleHistoryRunAiAssistPolling(runId, token) {
  if (!_historyRunAiEnabled() || !_historyRunCanUseAi() || !_historyRunAnyAiAssistPending()) {
    _stopHistoryRunAiAssistPolling();
    return;
  }
  if (_historyRunModalState.aiAssistPollTimer) return;
  const timer = setTimeout(() => {
    _historyRunModalState.aiAssistPollTimer = null;
    void _loadHistoryRunAIAssists(runId, token, { showLoading: false });
  }, HISTORY_RUN_AI_ASSIST_POLL_MS);
  if (timer && typeof timer.unref === "function") timer.unref();
  _historyRunModalState.aiAssistPollTimer = timer;
}
async function _loadHistoryRunDetails(runId, token) {
  _historyRunModalState.loadingDetails = true;
  _renderHistoryRunModal();
  try {
    const resp = await _historyRunApiFetch(`/history/${encodeURIComponent(runId)}?json&preview=1`, { cache: "no-store" });
    if (resp.ok === false) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (token !== _historyRunModalToken) return;
    _historyRunModalState.details = { ..._historyRunModalState.run || {}, ...data || {} };
  } catch (_) {
    if (token === _historyRunModalToken) _historyRunModalState.error = "Could not load run details.";
  } finally {
    if (token === _historyRunModalToken) {
      _historyRunModalState.loadingDetails = false;
      _renderHistoryRunModal();
    }
  }
}
async function _loadHistoryRunFindings(runId, token, { offset = 0 } = {}) {
  _historyRunModalState.loadingFindings = true;
  _renderHistoryRunModal();
  const limit = HISTORY_RUN_FINDINGS_PAGE_LIMIT;
  const query = new URLSearchParams({
    limit: String(limit),
    offset: String(Math.max(0, Number(offset || 0)))
  });
  try {
    const resp = await _historyRunApiFetch(`/entities/run/${encodeURIComponent(runId)}/findings?${query}`, { cache: "no-store" });
    if (resp.ok === false) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (token !== _historyRunModalToken) return;
    const payload = data && typeof data === "object" ? data : {};
    _historyRunModalState.findings = Array.isArray(payload.findings) ? payload.findings : [];
    _historyRunModalState.findingsPagination = {
      limit: Math.max(1, Number(payload.limit || limit)),
      offset: Math.max(0, Number(payload.offset || offset || 0)),
      total: Math.max(0, Number(payload.total || _historyRunModalState.findings.length || 0)),
      has_more: !!payload.has_more,
      occurrence_total: Math.max(0, Number(payload.occurrence_total || 0)),
      loaded: true
    };
  } catch (_) {
    if (token === _historyRunModalToken) {
      _historyRunModalState.findings = [];
      _historyRunModalState.findingsPagination = {
        limit,
        offset: 0,
        total: 0,
        has_more: false,
        occurrence_total: 0,
        loaded: true
      };
      _historyRunModalState.error = "Could not load run findings.";
    }
  } finally {
    if (token === _historyRunModalToken) {
      _historyRunModalState.loadingFindings = false;
      _renderHistoryRunModal();
    }
  }
}
function _setHistoryRunFindingsPage(direction) {
  const run = _historyRunPrimary();
  if (!run || !run.id || _historyRunModalState.loadingFindings) return;
  const pagination = _historyRunModalState.findingsPagination || {};
  const findings = Array.isArray(_historyRunModalState.findings) ? _historyRunModalState.findings : [];
  const limit = Math.max(1, Number(pagination.limit || HISTORY_RUN_FINDINGS_PAGE_LIMIT));
  const currentOffset = Math.max(0, Number(pagination.offset || 0));
  const total = Math.max(0, Number(pagination.total || findings.length || 0));
  const maxOffset = Math.max(0, Math.floor(Math.max(0, total - 1) / limit) * limit);
  const nextOffset = direction === "prev" ? Math.max(0, currentOffset - limit) : Math.min(maxOffset, currentOffset + limit);
  if (nextOffset === currentOffset) return;
  _loadHistoryRunFindings(run.id, _historyRunModalToken, { offset: nextOffset });
}
async function _loadHistoryRunEntitySummary(runId, token) {
  _historyRunModalState.loadingEntitySummary = true;
  _renderHistoryRunModal();
  const query = new URLSearchParams({
    run_id: String(runId || ""),
    orphan_filter: "hide",
    suppression_filter: "hide"
  });
  try {
    const resp = await _historyRunApiFetch(`/atlas?${query}`, { cache: "no-store" });
    if (resp.ok === false) throw new Error(`HTTP ${resp.status}`);
    const payload = await resp.json();
    if (token !== _historyRunModalToken) return;
    _historyRunModalState.entitySummary = payload && typeof payload === "object" ? payload : { total: 0, counts: {} };
    _historyRunModalState.entitySummaryLoaded = true;
  } catch (_) {
    if (token === _historyRunModalToken) {
      _historyRunModalState.entitySummary = { total: 0, counts: {} };
      _historyRunModalState.entitySummaryLoaded = true;
      _historyRunModalState.error = "Could not load run Atlas entity counts.";
    }
  } finally {
    if (token === _historyRunModalToken) {
      _historyRunModalState.loadingEntitySummary = false;
      _renderHistoryRunModal();
    }
  }
}
async function _loadHistoryRunEntities(runId, token, { offset = 0 } = {}) {
  _historyRunModalState.loadingEntities = true;
  _renderHistoryRunModal();
  const tab = _historyRunActiveEntityTab();
  const limit = HISTORY_RUN_ENTITIES_PAGE_LIMIT;
  const query = new URLSearchParams({
    run_id: String(runId || ""),
    type: String(tab.type || ""),
    limit: String(limit),
    offset: String(Math.max(0, Number(offset || 0))),
    orphan_filter: "hide",
    suppression_filter: "hide"
  });
  try {
    const resp = await _historyRunApiFetch(`/atlas/entities?${query}`, { cache: "no-store" });
    if (resp.ok === false) throw new Error(`HTTP ${resp.status}`);
    const payload = await resp.json();
    if (token !== _historyRunModalToken) return;
    _historyRunModalState.entities = Array.isArray(payload.entities) ? payload.entities : [];
    _historyRunModalState.entitiesPagination = {
      limit: Math.max(1, Number(payload.limit || limit)),
      offset: Math.max(0, Number(payload.offset || offset || 0)),
      total: Math.max(0, Number(payload.total || _historyRunModalState.entities.length || 0)),
      has_more: !!payload.has_more,
      loaded: true
    };
  } catch (_) {
    if (token === _historyRunModalToken) {
      _historyRunModalState.entities = [];
      _historyRunModalState.entitiesPagination = {
        limit,
        offset: 0,
        total: 0,
        has_more: false,
        loaded: true
      };
      _historyRunModalState.error = "Could not load run Atlas entities.";
    }
  } finally {
    if (token === _historyRunModalToken) {
      _historyRunModalState.loadingEntities = false;
      _renderHistoryRunModal();
    }
  }
}
function _setHistoryRunEntityTab(tabId) {
  const run = _historyRunPrimary();
  if (!run || !run.id || _historyRunModalState.loadingEntities) return;
  const tabs = _historyRunEntityTabs();
  const next = tabs.find((tab) => tab.id === String(tabId || ""));
  if (!next || next.id === _historyRunActiveEntityTab().id) return;
  _historyRunModalState.activeEntityTab = next.id;
  _historyRunModalState.entities = null;
  _historyRunModalState.entitiesPagination = {
    limit: HISTORY_RUN_ENTITIES_PAGE_LIMIT,
    offset: 0,
    total: 0,
    has_more: false,
    loaded: false
  };
  _renderHistoryRunModal();
  _loadHistoryRunEntities(run.id, _historyRunModalToken);
}
function _setHistoryRunEntitiesPage(direction) {
  const run = _historyRunPrimary();
  if (!run || !run.id || _historyRunModalState.loadingEntities) return;
  const pagination = _historyRunEntityPage();
  const entities = Array.isArray(_historyRunModalState.entities) ? _historyRunModalState.entities : [];
  const limit = Math.max(1, Number(pagination.limit || HISTORY_RUN_ENTITIES_PAGE_LIMIT));
  const currentOffset = Math.max(0, Number(pagination.offset || 0));
  const total = Math.max(0, Number(pagination.total || entities.length || 0));
  const maxOffset = Math.max(0, Math.floor(Math.max(0, total - 1) / limit) * limit);
  const nextOffset = direction === "prev" ? Math.max(0, currentOffset - limit) : Math.min(maxOffset, currentOffset + limit);
  if (nextOffset === currentOffset) return;
  _loadHistoryRunEntities(run.id, _historyRunModalToken, { offset: nextOffset });
}
function _historyRunExportTimestamp() {
  if (ExportHtmlUtils && typeof ExportHtmlUtils.exportTimestamp === "function") {
    return ExportHtmlUtils.exportTimestamp();
  }
  return (/* @__PURE__ */ new Date()).toISOString().replace(/[:.]/g, "-").slice(0, 19);
}
function _historyRunExportFilename(format) {
  const appName = String(_historyRunAppConfig().app_name || "darklab_shell");
  return `${appName}-${_historyRunExportTimestamp()}.${format}`;
}
function _historyRunExportCreatedText(run) {
  return String(run && (run.started || run.created) || "");
}
function _historyRunExportLines(run) {
  const lines = _historyRunOutputEntries(run);
  if (run && run.preview_notice) {
    lines.push({
      text: String(run.preview_notice || ""),
      kind: "notice",
      role: "body",
      cls: "notice"
    });
  }
  return lines.filter((line) => line && typeof line.text === "string");
}
function _historyRunExportLinesWithOutcome(run) {
  const rawLines = _historyRunExportLines(run);
  if (!_historyCommandOutcomeSummariesEnabled()) {
    return rawLines;
  }
  const summary = _historyRunCommandOutcomeSummary(run);
  if (!summary) return rawLines;
  return rawLines.concat(_historyCommandOutcomeSummaryToLines(summary));
}
async function _historyRunLoadExportRun() {
  const run = _historyRunPrimary();
  if (!run || !run.id) return run || {};
  const resp = await _historyRunApiFetch(`/history/${encodeURIComponent(run.id)}?json`, { cache: "no-store" });
  if (resp.ok === false) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  return { ...run, ...data || {} };
}
function _historyRunBuildExportModel(run) {
  const exportLines = _historyRunExportLines(run);
  const rawLines = _historyRunOmitRawOnlyLineEntries(exportLines);
  const visibleLines = _historyRunExportLinesWithOutcome({
    ...run || {},
    output_entries: rawLines,
    preview_notice: null
  });
  const config = _historyRunAppConfig();
  if (ExportHtmlUtils && typeof ExportHtmlUtils.buildExportDocumentModel === "function") {
    return ExportHtmlUtils.buildExportDocumentModel({
      appName: config.app_name || "darklab_shell",
      title: String(run && (run.command || run.label || run.id) || ""),
      label: run && (run.command || run.label || run.id),
      createdText: _historyRunExportCreatedText(run),
      runMeta: {
        exitCode: run ? run.exit_code : null,
        duration: null,
        lines: `${rawLines.length.toLocaleString()} lines`,
        version: config.version || null
      },
      rawLines: visibleLines
    });
  }
  return {
    appName: config.app_name || "darklab_shell",
    title: String(run && (run.command || run.label || run.id) || ""),
    metaLine: `${run && (run.command || run.label || run.id) || ""} · ${_historyRunExportCreatedText(run)}`,
    runMeta: {
      exitCode: run ? run.exit_code : null,
      duration: null,
      lines: `${rawLines.length.toLocaleString()} lines`,
      version: config.version || null
    },
    rawLines: visibleLines
  };
}
function _historyRunPlainExportText(run) {
  return _historyRunExportLinesWithOutcome(run).map((line) => String(line.text || "").replace(/\x1b\[[0-9;]*[A-Za-z]/g, "")).join("\n");
}
function _historyRunDownloadBlob(blob, filename) {
  if (!_historyRunDownloadBlobAsAttachment(blob, filename)) throw new Error("download unavailable");
}
async function _exportHistoryRunTxt() {
  const run = await _historyRunLoadExportRun();
  const text = _historyRunPlainExportText(run);
  if (!text.trim()) {
    _historyRunShowToast("No output to export");
    return;
  }
  _historyRunDownloadBlob(new Blob([text], { type: "text/plain" }), _historyRunExportFilename("txt"));
}
async function _exportHistoryRunHtml() {
  if (!ExportHtmlUtils) throw new Error("ExportHtmlUtils unavailable");
  const run = await _historyRunLoadExportRun();
  const exportModel = _historyRunBuildExportModel(run);
  if (!exportModel.rawLines.length) {
    _historyRunShowToast("No output to export");
    return;
  }
  const ansiRenderer = _historyRunCreateAnsiUpRenderer();
  const { linesHtml, prefixWidth, summaryHtml } = ExportHtmlUtils.buildExportLinesHtml(exportModel.rawLines, {
    getPrefix: () => "",
    ansiToHtml: (text) => ansiRenderer ? ansiRenderer.ansi_to_html(text) : _historyRunEscapeHtml(String(text ?? ""))
  });
  const [fontFacesCss, exportCss] = await Promise.all([
    ExportHtmlUtils.fetchVendorFontFacesCss().catch(() => ""),
    ExportHtmlUtils.fetchTerminalExportCss().catch(() => "")
  ]);
  const html = ExportHtmlUtils.buildTerminalExportHtml({
    appName: exportModel.appName,
    title: exportModel.title,
    metaLine: exportModel.metaLine,
    runMeta: exportModel.runMeta,
    linesHtml,
    summaryHtml,
    prefixWidth,
    fontFacesCss,
    exportCss
  });
  _historyRunDownloadBlob(new Blob([html], { type: "text/html" }), _historyRunExportFilename("html"));
}
async function _exportHistoryRunPdf() {
  const loadPdfUtils = _historyRunLoadExportPdfUtils();
  if (!loadPdfUtils) {
    throw new Error("PDF library not loaded");
  }
  const pdfUtils = await loadPdfUtils;
  const run = await _historyRunLoadExportRun();
  const exportModel = _historyRunBuildExportModel(run);
  if (!exportModel.rawLines.length) {
    _historyRunShowToast("No output to export");
    return;
  }
  const ansiRenderer = _historyRunCreateAnsiUpRenderer();
  const jsPDF = await _historyRunLoadJsPdf(pdfUtils);
  const doc = await pdfUtils.buildTerminalExportPdf({
    jsPDF,
    appName: exportModel.appName,
    metaLine: exportModel.metaLine,
    runMeta: exportModel.runMeta,
    rawLines: exportModel.rawLines,
    getPrefix: () => "",
    ansiToHtml: (text) => ansiRenderer ? ansiRenderer.ansi_to_html(text) : _historyRunEscapeHtml(String(text ?? ""))
  });
  doc.save(_historyRunExportFilename("pdf"));
}
async function _handleHistoryRunExport(format) {
  try {
    if (format === "txt") await _exportHistoryRunTxt();
    else if (format === "html") await _exportHistoryRunHtml();
    else if (format === "pdf") await _exportHistoryRunPdf();
  } catch (_) {
    const label = format === "pdf" ? "pdf" : format === "html" ? "html" : "text";
    _historyRunShowToast(`Failed to export ${label}`, "error");
  }
}
function _openHistoryRunEntityInAtlas(entityId) {
  const run = _historyRunPrimary();
  const entity = (Array.isArray(_historyRunModalState.entities) ? _historyRunModalState.entities : []).find((item) => String(item && item.id || "") === String(entityId || ""));
  if (!run || !run.id || !entity) return;
  closeHistoryRunOverlay();
  void _historyRunOpenAtlas({
    source: "run-details",
    tab: _historyRunActiveEntityTab().id,
    runId: run.id,
    runLabel: run.command || run.label || run.id,
    entityValue: entity.canonical_value || "",
    forceView: "detail"
  });
}
async function _loadHistoryRunProjectState(runId, token) {
  _historyRunModalState.loadingProject = true;
  _renderHistoryRunModal();
  try {
    const project = await _historyRunLoadActiveProject();
    if (token !== _historyRunModalToken) return;
    if (!project || !project.id) {
      _historyRunModalState.projectState = { project: null, attached: false };
      return;
    }
    const resp = await _historyRunApiFetch(`/projects/${encodeURIComponent(project.id)}/summary`, { cache: "no-store" });
    if (resp.ok === false) throw new Error(`HTTP ${resp.status}`);
    const summary = await resp.json();
    const runs = Array.isArray(summary.runs) ? summary.runs : [];
    _historyRunModalState.projectState = {
      project,
      attached: runs.some((item) => String(item && item.id || "") === String(runId || ""))
    };
  } catch (_) {
    if (token === _historyRunModalToken) _historyRunModalState.projectState = { project: null, attached: false };
  } finally {
    if (token === _historyRunModalToken) {
      _historyRunModalState.loadingProject = false;
      _renderHistoryRunModal();
    }
  }
}
async function _loadHistoryRunAIAssists(runId, token, { showLoading = true } = {}) {
  if (!_historyRunAiEnabled() || !_historyRunCanUseAi()) return;
  if (showLoading) _historyRunModalState.loadingAiAssists = true;
  _historyRunModalState.aiSummaryError = "";
  _historyRunModalState.aiNextError = "";
  if (showLoading) _renderHistoryRunModal();
  try {
    const resp = await _historyRunApiFetch(`/runs/${encodeURIComponent(runId)}/ai-assists`, { cache: "no-store" });
    if (resp.ok === false) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (token !== _historyRunModalToken) return;
    _historyRunModalState.aiAssists = Array.isArray(data.assists) ? data.assists : [];
    _historyRunModalState.aiAssistsLoaded = true;
  } catch (_) {
    if (token === _historyRunModalToken) {
      _historyRunModalState.aiAssists = [];
      _historyRunModalState.aiAssistsLoaded = false;
      _historyRunModalState.aiSummaryError = "Could not load AI assists.";
      _historyRunModalState.aiNextError = "Could not load AI assists.";
    }
  } finally {
    if (token === _historyRunModalToken) {
      if (showLoading) _historyRunModalState.loadingAiAssists = false;
      _renderHistoryRunModal();
      _scheduleHistoryRunAiAssistPolling(runId, token);
    }
  }
}
async function _requestHistoryRunAiSummary() {
  const run = _historyRunPrimary();
  if (!run || !run.id || !_historyRunAiSummaryEnabled() || !_historyRunCanUseAi(run) || _historyRunModalState.aiSummarySubmitting) return;
  const currentAssist = _historyRunLatestSummaryAssist();
  const currentStatus = String(currentAssist?.status || "").toLowerCase();
  const force = !!currentAssist && currentStatus !== "queued" && currentStatus !== "in_progress";
  const token = _historyRunModalToken;
  _historyRunModalState.aiSummarySubmitting = true;
  _historyRunModalState.aiSummaryError = "";
  _renderHistoryRunModal();
  document.getElementById("history-run-modal")?.focus({ preventScroll: true });
  try {
    const resp = await _historyRunApiFetch(`/runs/${encodeURIComponent(run.id)}/ai-summary`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(force ? { force: true } : {})
    });
    const data = await resp.json().catch(() => ({}));
    if (resp.ok === false) {
      throw new Error(_historyRunAiResponseMessage(data, `HTTP ${resp.status}`));
    }
    if (token !== _historyRunModalToken) return;
    const assist = data && data.assist && typeof data.assist === "object" ? data.assist : null;
    if (assist) {
      const existing = Array.isArray(_historyRunModalState.aiAssists) ? _historyRunModalState.aiAssists : [];
      _historyRunModalState.aiAssists = [
        assist,
        ...existing.filter((item) => String(item && item.id || "") !== String(assist.id || ""))
      ];
      _historyRunModalState.aiAssistsLoaded = true;
    }
  } catch (error) {
    if (token === _historyRunModalToken) {
      _historyRunModalState.aiSummaryError = _historyRunAiErrorMessage(error, "Could not start AI summary.");
    }
  } finally {
    if (token === _historyRunModalToken) {
      _historyRunModalState.aiSummarySubmitting = false;
      _renderHistoryRunModal();
      _scheduleHistoryRunAiAssistPolling(run.id, token);
      document.getElementById("history-run-modal")?.focus({ preventScroll: true });
    }
  }
}
async function _requestHistoryRunAiNextCommands() {
  const run = _historyRunPrimary();
  if (!run || !run.id || !_historyRunAiNextCommandsEnabled() || !_historyRunCanUseAi(run) || _historyRunModalState.aiNextSubmitting) return;
  const currentAssist = _historyRunLatestNextCommandsAssist();
  const currentStatus = String(currentAssist?.status || "").toLowerCase();
  const force = !!currentAssist && currentStatus !== "queued" && currentStatus !== "in_progress";
  const token = _historyRunModalToken;
  _historyRunModalState.aiNextSubmitting = true;
  _historyRunModalState.aiNextError = "";
  _renderHistoryRunModal();
  document.getElementById("history-run-modal")?.focus({ preventScroll: true });
  try {
    const resp = await _historyRunApiFetch(`/runs/${encodeURIComponent(run.id)}/ai-next-commands`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(force ? { force: true } : {})
    });
    const data = await resp.json().catch(() => ({}));
    if (resp.ok === false) {
      throw new Error(_historyRunAiResponseMessage(data, `HTTP ${resp.status}`));
    }
    if (token !== _historyRunModalToken) return;
    const assist = data && data.assist && typeof data.assist === "object" ? data.assist : null;
    if (assist) {
      const existing = Array.isArray(_historyRunModalState.aiAssists) ? _historyRunModalState.aiAssists : [];
      _historyRunModalState.aiAssists = [
        assist,
        ...existing.filter((item) => String(item && item.id || "") !== String(assist.id || ""))
      ];
      _historyRunModalState.aiAssistsLoaded = true;
    }
  } catch (error) {
    if (token === _historyRunModalToken) {
      _historyRunModalState.aiNextError = _historyRunAiErrorMessage(error, "Could not start AI suggestions.");
    }
  } finally {
    if (token === _historyRunModalToken) {
      _historyRunModalState.aiNextSubmitting = false;
      _renderHistoryRunModal();
      _scheduleHistoryRunAiAssistPolling(run.id, token);
      document.getElementById("history-run-modal")?.focus({ preventScroll: true });
    }
  }
}
function _historyRunAiResponseMessage(data, fallback) {
  if (data && typeof data === "object") {
    const message = String(data.message || "").trim();
    if (message) return message;
    const code = String(data.error || data.code || "").trim();
    if (code) return code;
  }
  return String(fallback || "").trim() || "AI request failed.";
}
function _historyRunAiErrorMessage(error, fallback) {
  const message = String(error && error.message || "").trim();
  if (message) return message;
  return fallback;
}
function openHistoryRunDetails(run) {
  if (!run || !run.id) return;
  _historyRunModalToken += 1;
  const token = _historyRunModalToken;
  _historyRunModalState = {
    run,
    details: null,
    findings: null,
    findingsPagination: {
      limit: HISTORY_RUN_FINDINGS_PAGE_LIMIT,
      offset: 0,
      total: 0,
      has_more: false,
      occurrence_total: 0,
      loaded: false
    },
    entitySummary: null,
    entitySummaryLoaded: false,
    entities: null,
    entitiesPagination: {
      limit: HISTORY_RUN_ENTITIES_PAGE_LIMIT,
      offset: 0,
      total: 0,
      has_more: false,
      loaded: false
    },
    activeEntityTab: _historyRunEntityTabs()[0]?.id || "ip",
    projectState: null,
    aiAssists: [],
    aiAssistsLoaded: false,
    loadingAiAssists: false,
    aiSummarySubmitting: false,
    aiNextSubmitting: false,
    aiSummaryError: "",
    aiNextError: "",
    aiThinkingStartedAt: 0,
    activeTab: "summary",
    loadingDetails: false,
    loadingFindings: false,
    loadingEntitySummary: false,
    loadingEntities: false,
    loadingProject: false,
    error: ""
  };
  _openHistoryRunOverlay();
  _renderHistoryRunModal();
  _loadHistoryRunDetails(run.id, token);
  _loadHistoryRunFindings(run.id, token);
  _loadHistoryRunEntitySummary(run.id, token);
  _loadHistoryRunEntities(run.id, token);
  _loadHistoryRunProjectState(run.id, token);
  if (_historyRunCanUseAi(run)) _loadHistoryRunAIAssists(run.id, token);
}
async function _handleHistoryRunModalAction(action) {
  const run = _historyRunPrimary();
  if (!run || !run.id) return;
  if (action === "use-command") {
    const cmd = run.command || "";
    _historyRunSetComposerValue(cmd, cmd.length, cmd.length);
    closeHistoryRunOverlay();
    _historyRunHideHistoryPanel();
    _historyRunRefocusComposerAfterAction({ preventScroll: true });
    _historyRunResetCmdHistoryNav();
  } else if (action === "restore") {
    closeHistoryRunOverlay();
    const existing = _historyRunTabForRun(run);
    const canUpgradeExisting = !!(existing && run.full_output_available && existing.previewTruncated);
    if (existing && !canUpgradeExisting) {
      _historyRunActivateTab(existing.id);
      _historyRunHideHistoryPanel();
      return;
    }
    _historyRunSetLoadState(true);
    _historyRunRestoreIntoTab(run, {
      targetTabId: canUpgradeExisting ? existing.id : null,
      hidePanelOnSuccess: true
    }).catch(() => _historyRunShowToast("Failed to load run")).finally(() => _historyRunSetLoadState(false));
  } else if (action === "copy-command") {
    _historyRunCopyTextToClipboard(run.command || "").then(() => _historyRunShowToast("Command copied")).catch(() => _historyRunShowToast("Failed to copy command", "error"));
  } else if (action === "schedule-command") {
    closeHistoryRunOverlay();
    void _historyRunOpenSchedulesModal({ command: run.command || "" });
  } else if (action === "watch-command") {
    closeHistoryRunOverlay();
    void _historyRunOpenWatchersModal({ baselineRun: run });
  } else if (action === "open-schedule") {
    closeHistoryRunOverlay();
    const ownerKind = String(run.schedule_owner_kind || "");
    const watcherId = String(run.schedule_owner_id || run.watcher_id || "");
    if (ownerKind === "watcher" && watcherId) {
      void _historyRunOpenWatchersModal({ watcherId });
    } else if (run.schedule_id) {
      void _historyRunOpenSchedulesModal({ scheduleId: run.schedule_id });
    }
  } else if (action === "permalink") {
    _historyRunCopyPermalink(run).catch(() => _historyRunShowToast("Failed to copy link", "error"));
  } else if (action === "compare") {
    closeHistoryRunOverlay();
    _historyRunOpenCompare(run);
  } else if (action === "delete") {
    closeHistoryRunOverlay();
    _historyRunConfirmDelete(run);
  } else if (action === "edit-metadata") {
    _historyRunEditMetadata("run", run);
  } else if (action === "open-atlas") {
    closeHistoryRunOverlay();
    void _historyRunOpenAtlas({
      source: "run-details",
      tab: "findings",
      runId: run.id,
      runLabel: run.command || run.label || run.id
    });
  } else if (action === "ai-summary") {
    await _requestHistoryRunAiSummary();
  } else if (action === "ai-next-commands") {
    await _requestHistoryRunAiNextCommands();
  } else if (action === "add-active-project") {
    const projectState = _historyRunModalState.projectState;
    const project = projectState && projectState.project;
    if (!project || projectState.attached) return;
    try {
      const confirmed = await _historyRunConfirmAddRunToProject(run, project);
      if (!confirmed) return;
      await _historyRunLinkRunToProject(run, project, confirmed);
      _historyRunModalState.projectState = { project, attached: true };
      _renderHistoryRunModal();
      _historyRunRefreshHistoryPanel();
    } catch (_) {
      _historyRunShowToast("Failed to add run to active project", "error");
    }
  } else if (action === "add-project") {
    try {
      await _historyRunAddRunToProject(run);
      const projectState = _historyRunModalState.projectState;
      if (projectState && projectState.project) {
        const activeProjectId = String(projectState.project.id || "");
        const attached = (Array.isArray(run.project_links) ? run.project_links : []).some((item) => String(item && item.project_id || "") === activeProjectId);
        _historyRunModalState.projectState = { ...projectState, attached };
      }
      _renderHistoryRunModal();
      _historyRunRefreshHistoryPanel();
    } catch (_) {
      _historyRunShowToast("Failed to add run to project", "error");
    }
  } else if (action === "remove-project") {
    try {
      await _historyRunRemoveRunFromProject(run);
      const projectState = _historyRunModalState.projectState;
      if (projectState && projectState.project) {
        const activeProjectId = String(projectState.project.id || "");
        const attached = (Array.isArray(run.project_links) ? run.project_links : []).some((item) => String(item && item.project_id || "") === activeProjectId);
        _historyRunModalState.projectState = { ...projectState, attached };
      }
      _renderHistoryRunModal();
      _historyRunRefreshHistoryPanel();
    } catch (_) {
      _historyRunShowToast("Failed to remove run from project", "error");
    }
  } else if (action === "copy-run-id") {
    _historyRunCopyTextToClipboard(run.id).then(() => _historyRunShowToast("Run ID copied")).catch(() => _historyRunShowToast("Failed to copy run ID", "error"));
  }
}
if (typeof window !== "undefined") {
  if (typeof setHistoryRunModalStateHandlers === "function") {
    setHistoryRunModalStateHandlers({
      getHistoryRunModalState: () => _historyRunModalState,
      closeHistoryRunOverlay,
      cycleHistoryRunOverlayTab,
      isHistoryRunOverlayOpen,
      openHistoryRunDetails
    });
  }
}

export {
  closeHistoryRunOverlay,
  isHistoryRunOverlayOpen,
  cycleHistoryRunOverlayTab,
  openHistoryRunDetails
};
