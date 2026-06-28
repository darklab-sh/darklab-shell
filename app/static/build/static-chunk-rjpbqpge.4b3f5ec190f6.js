import {
  getHistoryRunModalState
} from "./static-chunk-su3zfblw.dfaa45e2b263.js";
import {
  closeHistoryCompareActionMenus,
  hasHistoryCompareHandler,
  openHistoryCompareLauncher
} from "./static-chunk-xbxp24ix.e021648f87bd.js";
import {
  DarklabHistoryCore,
  _closeHistoryActionMenus,
  _closeHistoryRunActionMenus,
  _getStarred,
  _positionHistoryActionMenu,
  _resetHistoryActionMenuPosition,
  _saveStarred,
  _toggleStar,
  activateTab,
  activeTeamScopeCan,
  apiFetch as apiFetch2,
  appendLine2 as appendLine,
  clearTab2 as clearTab,
  createTab,
  getActiveProjectContext,
  getOutput,
  hasPendingOutputBatch,
  openAtlas,
  openEntityMetadataEditor,
  refreshProjectWorkspace,
  renderCommandOutcomeSummary,
  resetCmdHistoryNav,
  setHistoryRestoreHandlers,
  setTabStatus,
  teamScopeDeniedMessage
} from "./static-chunk-uwev63xf.c0c06adb18e0.js";
import {
  copyTextToClipboard,
  downloadBlobAsAttachment,
  escapeHtml,
  shareUrl,
  showToast
} from "./static-chunk-poi5czx6.3f5c94749765.js";
import {
  bindPressable,
  showConfirm
} from "./static-chunk-4m44pm74.0a8001fa1d52.js";
import {
  useMobileTerminalViewportMode
} from "./static-chunk-2bgb52uq.a327269283bb.js";
import {
  appendCommandEcho,
  blurActiveElement,
  emitUiEvent,
  enhanceAppSelects,
  exportedHideHistoryRow,
  exportedShowHistoryPanel,
  exportedShowHistoryRow,
  focusElement,
  getAppState,
  getTab,
  getTabs,
  hasRunnerHandler,
  hideHistoryPanel,
  hideTabKillBtn,
  histClearAllBtn,
  histRow,
  historyActiveFilters,
  historyBulkToolbar,
  historyClearFiltersBtn,
  historyDateFilter,
  historyEntityInput,
  historyEntityTypeFilter,
  historyExitFilter,
  historyKindFilter,
  historyList,
  historyLoadOverlay,
  historyMobileFiltersToggle,
  historyPagination,
  historyPaginationControls,
  historyPaginationSummary,
  historyPanel,
  historyProjectFilter,
  historyRootDropdown,
  historyRootInput,
  historySearchInput,
  historySignalFilter,
  historyStarredToggle,
  historyTypeFilter,
  refocusComposerAfterAction,
  refreshHistoryPanel,
  setComposerValue,
  setHistoryPanelHandlers,
  syncAppSelect
} from "./static-chunk-yo5cjr7d.b86e0c93eff0.js";
import {
  apiFetch,
  hasRuntimeHandler,
  logClientError
} from "./static-chunk-2kxtimik.c9801087c7a7.js";

// app/static/js/controller_action_bridge.js
var CONTROLLER_ACTION_BRIDGE_GLOBAL = typeof window !== "undefined" ? window : globalThis;
var warnedMissingControllerActionHandlers = /* @__PURE__ */ new Set();
var controllerActionHandlers = {
  closeFaq: null,
  closeWorkflows: null,
  openFaq: null,
  openWorkflows: null,
  toggleHistoryPanelSurface: null,
  toggleRailCollapsed: null
};
function setControllerActionHandlers(handlers = {}) {
  const registered = [];
  Object.keys(controllerActionHandlers).forEach((name) => {
    if (typeof handlers[name] === "function") {
      controllerActionHandlers[name] = handlers[name];
      registered.push(name);
    }
  });
  _logControllerActionBridgeDiagnostic("debug", "CONTROLLER_ACTION_HANDLER_REGISTERED", {
    registered_handlers: registered
  });
}
function _bridgeWarningsEnabled() {
  const config = CONTROLLER_ACTION_BRIDGE_GLOBAL?.APP_CONFIG && typeof CONTROLLER_ACTION_BRIDGE_GLOBAL.APP_CONFIG === "object" && !Array.isArray(CONTROLLER_ACTION_BRIDGE_GLOBAL.APP_CONFIG) ? CONTROLLER_ACTION_BRIDGE_GLOBAL.APP_CONFIG : {};
  return config.frontend_bridge_warnings === true || config.debug === true || config.dev_mode === true || config.environment === "development" || config.env === "development";
}
function _logControllerActionBridgeDiagnostic(level, event, details = {}) {
  if (!_bridgeWarningsEnabled()) return;
  const consoleApi = CONTROLLER_ACTION_BRIDGE_GLOBAL?.console || globalThis?.console;
  const log = consoleApi && ((level === "debug" ? consoleApi.debug : consoleApi.warn) || consoleApi.log);
  if (typeof log !== "function") return;
  log.call(consoleApi, `[darklab] ${event}`, {
    event,
    level,
    ...details
  });
}
function _callControllerActionHandler(name, args) {
  if (typeof controllerActionHandlers[name] === "function") {
    return controllerActionHandlers[name](...args);
  }
  if (!warnedMissingControllerActionHandlers.has(name)) {
    warnedMissingControllerActionHandlers.add(name);
    _logControllerActionBridgeDiagnostic("warning", "CONTROLLER_ACTION_HANDLER_MISSING", {
      handler: name,
      surface: name.includes("Workflows") ? "workflows" : name.includes("Faq") ? "faq" : "shell"
    });
  }
  return void 0;
}
function openFaq(...args) {
  return _callControllerActionHandler("openFaq", args);
}
function closeFaq(...args) {
  return _callControllerActionHandler("closeFaq", args);
}
function openWorkflows(...args) {
  return _callControllerActionHandler("openWorkflows", args);
}
function closeWorkflows(...args) {
  return _callControllerActionHandler("closeWorkflows", args);
}
function toggleHistoryPanelSurface(...args) {
  return _callControllerActionHandler("toggleHistoryPanelSurface", args);
}
function toggleRailCollapsed(...args) {
  return _callControllerActionHandler("toggleRailCollapsed", args);
}

// app/static/js/features/history/history_links.js
var HISTORY_LINKS_GLOBAL = typeof window !== "undefined" ? window : globalThis;
function _historyShareUrl() {
  return typeof shareUrl !== "undefined" && shareUrl || (typeof HISTORY_LINKS_GLOBAL?.shareUrl === "function" ? HISTORY_LINKS_GLOBAL.shareUrl : null);
}
function _snapshotUrl(snapshot) {
  return `${location.origin}/share/${snapshot.id}`;
}
function _historyRunPermalinkUrl(run) {
  return `${location.origin}/history/${run.id}`;
}
function openSnapshotLink(snapshot) {
  if (!snapshot || !snapshot.id) return;
  const url = _snapshotUrl(snapshot);
  if (typeof window !== "undefined" && window && typeof window.open === "function") {
    window.open(url, "_blank", "noopener,noreferrer");
  }
}
function copySnapshotLink(snapshot) {
  const share = _historyShareUrl();
  return typeof share === "function" ? share(_snapshotUrl(snapshot)) : Promise.resolve(false);
}
function copyHistoryRunPermalink(run) {
  const share = _historyShareUrl();
  return typeof share === "function" ? share(_historyRunPermalinkUrl(run)) : Promise.resolve(false);
}
if (typeof window !== "undefined") {
}

// app/static/js/features/history/history_project_actions.js
var HISTORY_PROJECT_ACTIONS_GLOBAL = typeof window !== "undefined" ? window : globalThis;
var fallbackHistoryProjectOptions = [];
var fallbackHistoryProjectOptionsLoaded = false;
var fallbackHistoryProjectOptionsLoading = null;
function _historyProjectCore() {
  return typeof DarklabHistoryCore !== "undefined" && DarklabHistoryCore || null;
}
function _historyProjectNormalizeFilterValue(value) {
  const core = _historyProjectCore();
  if (core && typeof core.normalizeFilterValue === "function") return core.normalizeFilterValue(value);
  if (typeof HISTORY_PROJECT_ACTIONS_GLOBAL._normalizeHistoryFilterValue === "function") {
    return HISTORY_PROJECT_ACTIONS_GLOBAL._normalizeHistoryFilterValue(value);
  }
  return String(value || "").trim();
}
function _historyProjectFilterRef() {
  return typeof historyProjectFilter !== "undefined" && historyProjectFilter || HISTORY_PROJECT_ACTIONS_GLOBAL.historyProjectFilter || null;
}
function _historyProjectShowToast(message, tone = "success") {
  const toast = typeof showToast !== "undefined" && showToast || HISTORY_PROJECT_ACTIONS_GLOBAL.showToast || null;
  if (typeof toast === "function") toast(message, tone);
}
function _historyProjectShowConfirm(options) {
  const confirm = typeof showConfirm !== "undefined" && showConfirm || HISTORY_PROJECT_ACTIONS_GLOBAL.showConfirm || null;
  return typeof confirm === "function" ? confirm(options) : Promise.resolve(null);
}
function _historyProjectEnhanceAppSelects(root) {
  const enhance = typeof enhanceAppSelects !== "undefined" && enhanceAppSelects || HISTORY_PROJECT_ACTIONS_GLOBAL.enhanceAppSelects || null;
  if (typeof enhance === "function") enhance(root);
  return typeof enhance === "function";
}
function _historyProjectSyncAppSelect(select) {
  const sync = typeof syncAppSelect !== "undefined" && syncAppSelect || HISTORY_PROJECT_ACTIONS_GLOBAL.syncAppSelect || null;
  if (typeof sync === "function") sync(select);
}
function _historyProjectUseMobileTerminalViewportMode() {
  const useMobile = typeof useMobileTerminalViewportMode !== "undefined" && useMobileTerminalViewportMode || HISTORY_PROJECT_ACTIONS_GLOBAL.useMobileTerminalViewportMode;
  return typeof useMobile === "function" ? useMobile() : false;
}
function _historyProjectRefreshHistoryPanel() {
  const refresh = typeof refreshHistoryPanel2 !== "undefined" && refreshHistoryPanel2 || HISTORY_PROJECT_ACTIONS_GLOBAL.refreshHistoryPanel;
  return typeof refresh === "function" ? refresh() : Promise.resolve();
}
function _historyProjectApiFetch(...args) {
  const fetcher = (typeof hasRuntimeHandler === "function" && hasRuntimeHandler("apiFetch") && typeof apiFetch === "function" ? apiFetch : null) || HISTORY_PROJECT_ACTIONS_GLOBAL.apiFetch;
  return typeof fetcher === "function" ? fetcher(...args) : Promise.reject(new Error("apiFetch unavailable"));
}
function _historyProjectLogClientError(...args) {
  const logger = (typeof hasRuntimeHandler === "function" && hasRuntimeHandler("logClientError") && typeof logClientError === "function" ? logClientError : null) || HISTORY_PROJECT_ACTIONS_GLOBAL.logClientError;
  if (typeof logger === "function") logger(...args);
}
function _historyProjectLogEvent(context, err, details = {}) {
  _historyProjectLogClientError(context, err, details);
}
function _historyProjectLogPayload(event, level, run, project, options = {}, extra = {}) {
  return {
    event,
    level,
    run_id: String(run?.id || ""),
    project_id: String(project?.id || ""),
    operation: String(options.operation || ""),
    include_entities: options.includeEntities === true,
    include_curated_entities: options.includeCuratedEntities === true,
    http_status: Number(extra.httpStatus || 0) || null
  };
}
function _historyProjectRefreshProjectWorkspace() {
  const refresh = HISTORY_PROJECT_ACTIONS_GLOBAL.refreshProjectWorkspace;
  return typeof refresh === "function" ? refresh() : Promise.resolve();
}
function _historyProjectOptionsState() {
  if (typeof getHistoryProjectOptionsState === "function") {
    return getHistoryProjectOptionsState();
  }
  return {
    options: fallbackHistoryProjectOptions,
    loaded: fallbackHistoryProjectOptionsLoaded,
    loading: fallbackHistoryProjectOptionsLoading
  };
}
function _setHistoryProjectOptionsState(updates = {}) {
  if (typeof setHistoryProjectOptionsState === "function") {
    return setHistoryProjectOptionsState(updates);
  }
  if (Object.prototype.hasOwnProperty.call(updates, "options")) {
    fallbackHistoryProjectOptions = Array.isArray(updates.options) ? updates.options : [];
  }
  if (Object.prototype.hasOwnProperty.call(updates, "loaded")) {
    fallbackHistoryProjectOptionsLoaded = updates.loaded === true;
  }
  if (Object.prototype.hasOwnProperty.call(updates, "loading")) {
    fallbackHistoryProjectOptionsLoading = updates.loading || null;
  }
  return _historyProjectOptionsState();
}
function _historyProjectDisplayName(project) {
  if (!project || typeof project !== "object") return "";
  return String(project.name || project.slug || project.id || "").trim();
}
function _historyProjectLabelForId(projectId) {
  const normalized = _historyProjectNormalizeFilterValue(projectId);
  if (!normalized || normalized === "all") return "";
  const project = _historyProjectOptionsState().options.find((item) => String(item && item.id || "") === normalized);
  return _historyProjectDisplayName(project) || normalized;
}
function _syncHistoryProjectFilterOptions() {
  const projectFilter = _historyProjectFilterRef();
  if (!projectFilter) return;
  const selected = _historyProjectNormalizeFilterValue(window._historyFilters.projectId) || "all";
  const projectOptions = _historyProjectOptionsState().options;
  projectFilter.replaceChildren();
  const allOption = document.createElement("option");
  allOption.value = "all";
  allOption.textContent = "project: all";
  projectFilter.appendChild(allOption);
  projectOptions.forEach((project) => {
    const projectId = String(project && project.id || "");
    if (!projectId) return;
    const option = document.createElement("option");
    option.value = projectId;
    option.textContent = `project: ${_historyProjectDisplayName(project) || projectId}`;
    projectFilter.appendChild(option);
  });
  if (selected !== "all" && !projectOptions.some((project) => String(project && project.id || "") === selected)) {
    const stale = document.createElement("option");
    stale.value = selected;
    stale.textContent = `project: ${selected}`;
    projectFilter.appendChild(stale);
  }
  projectFilter.value = selected;
  _historyProjectSyncAppSelect(projectFilter);
}
function _ensureHistoryProjectFilterOptions() {
  const state = _historyProjectOptionsState();
  if (state.loaded) return Promise.resolve(state.options);
  if (state.loading) return state.loading;
  const loading = _historyLoadProjectFilterOptions().then((projects) => {
    _setHistoryProjectOptionsState({ options: projects, loaded: true });
    _syncHistoryProjectFilterOptions();
    return projects;
  }).catch((err) => {
    _historyProjectLogClientError("failed to load history project filter options", err);
    throw err;
  }).finally(() => {
    _setHistoryProjectOptionsState({ loading: null });
  });
  _setHistoryProjectOptionsState({ loading });
  return loading;
}
async function _historyLoadActiveProject() {
  if (typeof HISTORY_PROJECT_ACTIONS_GLOBAL.refreshActiveProjectContext === "function") {
    try {
      const refreshed = await HISTORY_PROJECT_ACTIONS_GLOBAL.refreshActiveProjectContext();
      if (refreshed && refreshed.id) return refreshed;
    } catch (err) {
      _historyProjectLogEvent("history project active refresh failed", err, {
        event: "HISTORY_PROJECT_ACTIVE_REFRESH_FAILED",
        level: "warning",
        operation: "refresh-active-project-context"
      });
    }
  }
  try {
    const resp = await _historyProjectApiFetch("/projects/active", { cache: "no-store" });
    if (!resp.ok) {
      _historyProjectLogEvent("history project active refresh failed", new Error(`HTTP ${resp.status}`), {
        event: "HISTORY_PROJECT_ACTIVE_REFRESH_FAILED",
        level: "warning",
        operation: "load-active-project",
        http_status: resp.status
      });
      return null;
    }
    const data = await resp.json();
    return data && data.project && data.project.id ? data.project : null;
  } catch (err) {
    _historyProjectLogEvent("history project active refresh failed", err, {
      event: "HISTORY_PROJECT_ACTIVE_REFRESH_FAILED",
      level: "warning",
      operation: "load-active-project"
    });
    return null;
  }
}
async function _historyLoadProjects() {
  const resp = await _historyProjectApiFetch("/projects", { cache: "no-store" });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  return (Array.isArray(data.projects) ? data.projects : []).filter((project) => project && project.id && project.status !== "archived").sort((a, b) => _historyProjectDisplayName(a).localeCompare(_historyProjectDisplayName(b)));
}
async function _historyLoadProjectFilterOptions() {
  const resp = await _historyProjectApiFetch("/projects?include_archived=1", { cache: "no-store" });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  return (Array.isArray(data.projects) ? data.projects : []).filter((project) => project && project.id && project.status !== "archived").sort((a, b) => _historyProjectDisplayName(a).localeCompare(_historyProjectDisplayName(b)));
}
function _historyOrderProjectsForPicker(projects, activeProject = null) {
  const activeId = activeProject && activeProject.id ? String(activeProject.id) : "";
  return (Array.isArray(projects) ? projects : []).slice().sort((a, b) => {
    const aIsActive = activeId && String(a?.id || "") === activeId;
    const bIsActive = activeId && String(b?.id || "") === activeId;
    if (aIsActive !== bIsActive) return aIsActive ? -1 : 1;
    return _historyProjectDisplayName(a).localeCompare(_historyProjectDisplayName(b));
  });
}
async function _historyLinkRunToProject(run, project, options = {}) {
  const includeEntities = !!options.includeEntities;
  if (!run || !run.id) throw new Error("Run is missing its identifier.");
  if (!project || !project.id) throw new Error("Project is missing its identifier.");
  const resp = await _historyProjectApiFetch(`/projects/${encodeURIComponent(project.id)}/links`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      entity_type: "run",
      entity_id: run.id,
      source: "manual",
      ...includeEntities ? { include_entities: true } : {}
    })
  });
  if (!resp.ok) {
    let detail = "";
    try {
      const data = await resp.json();
      detail = data && data.error ? data.error : "";
    } catch (err2) {
      _historyProjectLogEvent("history project link response parse failed", err2, {
        event: "HISTORY_PROJECT_LINK_FAILED",
        level: "error",
        ..._historyProjectLogPayload("HISTORY_PROJECT_LINK_FAILED", "error", run, project, {
          ...options,
          operation: "link-run"
        }, { httpStatus: resp.status })
      });
    }
    const err = new Error(detail || `HTTP ${resp.status}`);
    _historyProjectLogEvent("history project link failed", err, _historyProjectLogPayload(
      "HISTORY_PROJECT_LINK_FAILED",
      "error",
      run,
      project,
      { ...options, operation: "link-run" },
      { httpStatus: resp.status }
    ));
    throw err;
  }
  let link = null;
  let entityStats = null;
  try {
    const data = await resp.json();
    link = data && data.link ? data.link : null;
    entityStats = data && data.linked_entities ? data.linked_entities : null;
  } catch (_) {
  }
  if (link) {
    run.project_links = (Array.isArray(run.project_links) ? run.project_links : []).filter((item) => String(item && item.project_id || "") !== String(project.id || ""));
    run.project_links.push({ ...link, project });
    run.project_link_count = run.project_links.length;
  }
  try {
    await _historyProjectRefreshProjectWorkspace();
  } catch (err) {
    _historyProjectLogEvent("history project refresh after link failed", err, _historyProjectLogPayload(
      "HISTORY_PROJECT_REFRESH_AFTER_LINK_FAILED",
      "warning",
      run,
      project,
      { ...options, operation: "refresh-project-workspace-after-link" }
    ));
  }
  const name = _historyProjectDisplayName(project) || "project";
  const addedEntities = includeEntities ? Number(entityStats && entityStats.added || 0) : 0;
  _historyProjectShowToast(addedEntities ? `Run and ${addedEntities.toLocaleString()} ${addedEntities === 1 ? "entity" : "entities"} added to ${name}` : `Run added to ${name}`);
  try {
    await _historyProjectRefreshHistoryPanel();
  } catch (err) {
    _historyProjectLogEvent("history project refresh after link failed", err, _historyProjectLogPayload(
      "HISTORY_PROJECT_REFRESH_AFTER_LINK_FAILED",
      "warning",
      run,
      project,
      { ...options, operation: "refresh-history-panel-after-link" }
    ));
  }
}
async function _historyLoadProjectRunEntityPreview(project, runIds) {
  const projectId = String(project && project.id || "").trim();
  const ids = (Array.isArray(runIds) ? runIds : [runIds]).map((runId) => String(runId || "").trim()).filter(Boolean);
  if (!projectId || !ids.length) return null;
  const resp = await _historyProjectApiFetch(`/projects/${encodeURIComponent(projectId)}/links/run-entities/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_ids: ids })
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  return data && data.preview ? data.preview : null;
}
async function _historyLoadProjectRunEntityRemovePreview(project, runIds) {
  const projectId = String(project && project.id || "").trim();
  const ids = (Array.isArray(runIds) ? runIds : [runIds]).map((runId) => String(runId || "").trim()).filter(Boolean);
  if (!projectId || !ids.length) return null;
  const resp = await _historyProjectApiFetch(`/projects/${encodeURIComponent(projectId)}/links/run-entities/remove-preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_ids: ids })
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  return data && data.preview ? data.preview : null;
}
function _historyProjectRunEntityOptionLabel(count, runCount) {
  const entityLabel = count === 1 ? "entity" : "entities";
  if (runCount > 1) return `Also add ${count.toLocaleString()} Atlas ${entityLabel} found in these runs`;
  return `Also add ${count.toLocaleString()} Atlas ${entityLabel} found in this run`;
}
function _historyProjectRunEntityOptionContent({
  kind = "add",
  labelForCount = _historyProjectRunEntityOptionLabel
} = {}) {
  const wrap = document.createElement("div");
  wrap.className = "history-project-run-entities-option u-hidden";
  wrap.dataset.historyProjectRunEntitiesOption = kind;
  const label = document.createElement("label");
  label.className = "form-check";
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = false;
  checkbox.dataset.historyProjectRunEntitiesScope = kind === "remove" ? "disposable" : "all";
  const text = document.createElement("span");
  label.append(checkbox, text);
  wrap.append(label);
  const note = document.createElement("div");
  note.className = "history-project-run-entities-note u-hidden";
  wrap.appendChild(note);
  const curatedLabel = document.createElement("label");
  curatedLabel.className = "form-check u-hidden";
  const curatedCheckbox = document.createElement("input");
  curatedCheckbox.type = "checkbox";
  curatedCheckbox.checked = false;
  curatedCheckbox.dataset.historyProjectRunEntitiesScope = "curated";
  const curatedText = document.createElement("span");
  curatedLabel.append(curatedCheckbox, curatedText);
  const curatedNote = document.createElement("div");
  curatedNote.className = "history-project-run-entities-note u-hidden";
  if (kind === "remove") {
    wrap.append(curatedLabel, curatedNote);
  }
  const runFindingsNote = document.createElement("div");
  runFindingsNote.className = "history-project-run-entities-note u-hidden";
  if (kind === "remove") {
    wrap.prepend(runFindingsNote);
  }
  return {
    wrap,
    checkbox,
    text,
    note,
    curatedCheckbox,
    includeEntities() {
      return !!checkbox.checked && !checkbox.disabled;
    },
    includeCuratedEntities() {
      return !!curatedCheckbox.checked && !curatedCheckbox.disabled;
    },
    includeAnyEntities() {
      return this.includeEntities() || this.includeCuratedEntities();
    },
    setPreview(preview) {
      const runCount = Number(preview && preview.run_count || 0);
      if (kind === "remove") {
        const removable = Number(preview && preview.removable || 0);
        const curated = Number(preview && (preview.curated ?? preview.kept_curated) || 0);
        const runFindings = Number(preview && preview.run_findings || 0);
        const removableFindings = Number(preview && preview.removable_findings || 0);
        const curatedFindings = Number(preview && (preview.curated_findings ?? preview.kept_curated_findings) || 0);
        const entityLabel = removable === 1 ? "entity" : "entities";
        const curatedEntityLabel = curated === 1 ? "entity" : "entities";
        const runFindingLabel = runFindings === 1 ? "finding" : "findings";
        const removableFindingLabel = removableFindings === 1 ? "finding" : "findings";
        const curatedFindingLabel = curatedFindings === 1 ? "finding" : "findings";
        checkbox.checked = false;
        checkbox.disabled = removable <= 0;
        curatedCheckbox.checked = false;
        curatedCheckbox.disabled = curated <= 0;
        wrap.classList.toggle("u-hidden", removable <= 0 && curated <= 0 && runFindings <= 0);
        runFindingsNote.classList.toggle("u-hidden", runFindings <= 0);
        runFindingsNote.textContent = runFindings > 0 ? `Removing the run link will remove ${runFindings.toLocaleString()} ${runFindingLabel} from this project's Findings tab.` : "";
        label.classList.toggle("u-hidden", removable <= 0);
        curatedLabel.classList.toggle("u-hidden", curated <= 0);
        text.textContent = removable > 0 ? "Also remove disposable same-run Atlas entities from this project" : "";
        note.classList.toggle("u-hidden", removable <= 0);
        note.textContent = removable > 0 ? [
          `This will unlink ${removable.toLocaleString()} ${entityLabel} found only in ${runCount > 1 ? "these runs" : "this run"}.`,
          removableFindings > 0 ? `${removableFindings.toLocaleString()} related ${removableFindingLabel} will no longer appear in this project.` : ""
        ].filter(Boolean).join(" ") : "";
        curatedText.textContent = curated > 0 ? "Also remove curated same-run Atlas entities from this project" : "";
        curatedNote.classList.toggle("u-hidden", curated <= 0);
        curatedNote.textContent = curated > 0 ? [
          `${curated.toLocaleString()} curated ${curatedEntityLabel}`,
          curatedFindings > 0 ? `and ${curatedFindings.toLocaleString()} related ${curatedFindingLabel}` : "",
          `will stay in this project unless this is checked. Curated means project-linked elsewhere, labeled, noted, reviewed, or carrying project target metadata.`
        ].filter(Boolean).join(" ") : "";
        return;
      }
      const count = Number(preview && preview.linkable || 0);
      const keptCurated = Number(preview && preview.kept_curated || 0);
      checkbox.checked = false;
      checkbox.disabled = count <= 0;
      wrap.classList.toggle("u-hidden", count <= 0);
      text.textContent = count > 0 ? labelForCount(count, runCount) : "";
      note.classList.toggle("u-hidden", count <= 0 || keptCurated <= 0);
      note.textContent = keptCurated > 0 ? `${keptCurated.toLocaleString()} curated ${keptCurated === 1 ? "entity will" : "entities will"} stay linked.` : "";
    }
  };
}
async function _historyRefreshProjectRunEntityOption(control, project, runIds) {
  if (!control) return null;
  try {
    const preview = await _historyLoadProjectRunEntityPreview(project, runIds);
    control.setPreview(preview);
    return preview;
  } catch (_) {
    control.setPreview(null);
    return null;
  }
}
async function _historyRefreshProjectRunEntityRemoveOption(control, project, runIds) {
  if (!control) return null;
  try {
    const preview = await _historyLoadProjectRunEntityRemovePreview(project, runIds);
    control.setPreview(preview);
    return preview;
  } catch (_) {
    control.setPreview(null);
    return null;
  }
}
async function _historyConfirmAddRunToProject(run, project) {
  const option = _historyProjectRunEntityOptionContent();
  await _historyRefreshProjectRunEntityOption(option, project, [run && run.id]);
  const content = option.wrap.classList.contains("u-hidden") ? null : option.wrap;
  const choice = await _historyProjectShowConfirm({
    body: `Add this run to ${_historyProjectDisplayName(project) || "this project"}?`,
    content,
    tone: null,
    actions: [
      { id: "cancel", label: "Cancel", role: "cancel" },
      { id: "add", label: "Add to project", role: "primary" }
    ],
    refocusOnResolve: false
  });
  if (choice !== "add") return false;
  return { includeEntities: !!option.checkbox.checked && !option.checkbox.disabled };
}
function _historyProjectRunEntityRemoveOptionLabel(count, runCount) {
  const entityLabel = count === 1 ? "entity" : "entities";
  if (runCount > 1) return `Also remove ${count.toLocaleString()} Atlas ${entityLabel} found only in these runs from this project`;
  return `Also remove ${count.toLocaleString()} Atlas ${entityLabel} found only in this run from this project`;
}
function _historyProjectFromLink(link) {
  if (!link || typeof link !== "object") return null;
  if (link.project && typeof link.project === "object") return link.project;
  const projectId = String(link.project_id || "").trim();
  if (!projectId) return null;
  return {
    id: projectId,
    name: link.project_name || "",
    slug: link.project_slug || "",
    status: link.project_status || ""
  };
}
function _historyRunProjectLinks(run) {
  const links = Array.isArray(run?.project_links) ? run.project_links.slice() : [];
  try {
    const state = typeof getHistoryRunModalState === "function" ? getHistoryRunModalState() : null;
    const projectState = state && state.projectState;
    const project = projectState && projectState.project;
    const runId = String(run && run.id || "");
    const modalRunId = String((state && (state.details || state.run) || {}).id || "");
    const hasActiveLink = !!(project && project.id) && projectState.attached && runId && (!modalRunId || modalRunId === runId) && !links.some((item) => String(item && item.project_id || "") === String(project.id || ""));
    if (hasActiveLink) {
      links.push({
        project_id: project.id,
        entity_type: "run",
        entity_id: runId,
        project
      });
    }
  } catch (_) {
  }
  return links.map((link) => ({ link, project: _historyProjectFromLink(link) })).filter((item) => item.project && item.project.id).sort((a, b) => _historyProjectDisplayName(a.project).localeCompare(
    _historyProjectDisplayName(b.project),
    void 0,
    { sensitivity: "base", numeric: true }
  ));
}
async function _historyUnlinkRunFromProject(run, project, options = {}) {
  const includeEntities = !!options.includeEntities;
  const includeCuratedEntities = !!options.includeCuratedEntities;
  if (!run || !run.id) throw new Error("Run is missing its identifier.");
  if (!project || !project.id) throw new Error("Project is missing its identifier.");
  const resp = await _historyProjectApiFetch(`/projects/${encodeURIComponent(project.id)}/links`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      entity_type: "run",
      entity_id: run.id,
      ...includeEntities ? { include_entities: true } : {},
      ...includeCuratedEntities ? { include_curated_entities: true } : {}
    })
  });
  if (!resp.ok) {
    let detail = "";
    try {
      const data = await resp.json();
      detail = data && data.error ? data.error : "";
    } catch (err2) {
      _historyProjectLogEvent("history project unlink response parse failed", err2, _historyProjectLogPayload(
        "HISTORY_PROJECT_UNLINK_FAILED",
        "error",
        run,
        project,
        { ...options, operation: "unlink-run" },
        { httpStatus: resp.status }
      ));
    }
    const err = new Error(detail || `HTTP ${resp.status}`);
    _historyProjectLogEvent("history project unlink failed", err, _historyProjectLogPayload(
      "HISTORY_PROJECT_UNLINK_FAILED",
      "error",
      run,
      project,
      { ...options, operation: "unlink-run" },
      { httpStatus: resp.status }
    ));
    throw err;
  }
  let entityStats = null;
  try {
    const data = await resp.json();
    entityStats = data && data.unlinked_entities ? data.unlinked_entities : null;
  } catch (_) {
  }
  try {
    await _historyProjectRefreshProjectWorkspace();
  } catch (err) {
    _historyProjectLogEvent("history project refresh after unlink failed", err, _historyProjectLogPayload(
      "HISTORY_PROJECT_REFRESH_AFTER_LINK_FAILED",
      "warning",
      run,
      project,
      { ...options, operation: "refresh-project-workspace-after-unlink" }
    ));
  }
  if (Array.isArray(run.project_links)) {
    run.project_links = run.project_links.filter((item) => String(item && item.project_id || "") !== String(project.id || ""));
    run.project_link_count = run.project_links.length;
  }
  const name = _historyProjectDisplayName(project) || "project";
  const removedEntities = includeEntities ? Number(entityStats && entityStats.removed || 0) : 0;
  _historyProjectShowToast(removedEntities ? `Run and ${removedEntities.toLocaleString()} ${removedEntities === 1 ? "entity" : "entities"} removed from ${name}` : `Run removed from ${name}`);
  try {
    await _historyProjectRefreshHistoryPanel();
  } catch (err) {
    _historyProjectLogEvent("history project refresh after unlink failed", err, _historyProjectLogPayload(
      "HISTORY_PROJECT_REFRESH_AFTER_LINK_FAILED",
      "warning",
      run,
      project,
      { ...options, operation: "refresh-history-panel-after-unlink" }
    ));
  }
}
async function _historyAddRunToActiveProject(run) {
  const project = await _historyLoadActiveProject();
  if (!project || !project.id) {
    _historyProjectShowToast("No active project selected", "error");
    return;
  }
  const confirmed = await _historyConfirmAddRunToProject(run, project);
  if (!confirmed) return;
  await _historyLinkRunToProject(run, project, confirmed);
}
function _historyProjectPickerContentForLinks(links) {
  const projects = links.map((item) => item.project).filter(Boolean);
  const { wrap, select } = _historyProjectPickerContent(projects);
  const help = wrap.querySelector(".history-project-picker-help");
  if (help) help.textContent = "Choose the project link to remove.";
  return { wrap, select, projects };
}
async function _historyRemoveRunFromProject(run) {
  const links = _historyRunProjectLinks(run);
  if (!links.length) {
    _historyProjectShowToast("This run is not linked to a project", "error");
    return;
  }
  let project = links[0].project;
  let content = null;
  let defaultFocus = null;
  const removeOption = _historyProjectRunEntityOptionContent({
    kind: "remove",
    labelForCount: _historyProjectRunEntityRemoveOptionLabel
  });
  if (links.length > 1) {
    const { wrap, select, projects } = _historyProjectPickerContentForLinks(links);
    content = wrap;
    defaultFocus = select;
    wrap.appendChild(removeOption.wrap);
    await _historyRefreshProjectRunEntityRemoveOption(removeOption, project, [run && run.id]);
    select.addEventListener("change", () => {
      const selectedProject = projects.find((item) => String(item.id || "") === select.value);
      _historyRefreshProjectRunEntityRemoveOption(removeOption, selectedProject, [run && run.id]);
    });
    if (_historyProjectEnhanceAppSelects(wrap)) {
      if (_historyProjectUseMobileTerminalViewportMode()) {
        wrap.querySelector(".app-select-menu")?.classList.add("dropdown-up");
      }
    }
    project = () => projects.find((item) => String(item.id || "") === select.value);
  } else {
    await _historyRefreshProjectRunEntityRemoveOption(removeOption, project, [run && run.id]);
    if (!removeOption.wrap.classList.contains("u-hidden")) {
      content = removeOption.wrap;
    }
  }
  const choice = await _historyProjectShowConfirm({
    body: links.length > 1 ? "Remove this run from a project" : `Remove this run from ${_historyProjectDisplayName(project) || "this project"}?`,
    content,
    tone: "warning",
    defaultFocus,
    actions: [
      { id: "cancel", label: "Cancel", role: "cancel" },
      { id: "remove", label: "Remove from project", role: "destructive", tone: "warning" }
    ],
    refocusOnResolve: false
  });
  if (choice !== "remove") return;
  if (typeof project === "function") project = project();
  try {
    await _historyUnlinkRunFromProject(run, project, {
      includeEntities: removeOption.includeAnyEntities(),
      includeCuratedEntities: removeOption.includeCuratedEntities()
    });
  } catch (err) {
    _historyProjectLogEvent("history project unlink failed", err, _historyProjectLogPayload(
      "HISTORY_PROJECT_UNLINK_FAILED",
      "error",
      run,
      project,
      {
        includeEntities: removeOption.includeAnyEntities(),
        includeCuratedEntities: removeOption.includeCuratedEntities(),
        operation: "remove-run-from-project"
      }
    ));
    _historyProjectShowToast("Failed to remove run from project", "error");
  }
}
function _historyProjectPickerContent(projects) {
  const wrap = document.createElement("div");
  wrap.className = "history-project-picker";
  const select = document.createElement("select");
  select.className = "form-select form-control-compact";
  select.setAttribute("aria-label", "Project");
  projects.forEach((project) => {
    const option = document.createElement("option");
    option.value = String(project.id || "");
    option.textContent = _historyProjectDisplayName(project) || String(project.id || "");
    select.appendChild(option);
  });
  wrap.appendChild(select);
  const help = document.createElement("div");
  help.className = "history-project-picker-help";
  help.textContent = "Choose a project to link this run.";
  wrap.appendChild(help);
  return { wrap, select };
}
async function _historyAddRunToProject(run) {
  let projects;
  try {
    const [loadedProjects, activeProject] = await Promise.all([
      _historyLoadProjects(),
      _historyLoadActiveProject().catch(() => null)
    ]);
    projects = _historyOrderProjectsForPicker(loadedProjects, activeProject);
  } catch (_) {
    _historyProjectShowToast("Failed to load projects", "error");
    return;
  }
  if (!projects.length) {
    _historyProjectShowToast("No projects available", "error");
    return;
  }
  const { wrap, select } = _historyProjectPickerContent(projects);
  const entityOption = _historyProjectRunEntityOptionContent();
  wrap.appendChild(entityOption.wrap);
  const selectedRunIds = [run && run.id];
  const updateEntityOption = () => {
    const selectedProject = projects.find((item) => String(item.id || "") === select.value);
    _historyRefreshProjectRunEntityOption(entityOption, selectedProject, selectedRunIds);
  };
  select.addEventListener("change", updateEntityOption);
  updateEntityOption();
  const choicePromise = _historyProjectShowConfirm({
    body: "Add this run to a project",
    content: wrap,
    tone: null,
    defaultFocus: select,
    actions: [
      { id: "cancel", label: "Cancel", role: "cancel" },
      { id: "add", label: "Add to project", role: "primary" }
    ],
    refocusOnResolve: false
  });
  if (_historyProjectEnhanceAppSelects(wrap)) {
    if (_historyProjectUseMobileTerminalViewportMode()) {
      wrap.querySelector(".app-select-menu")?.classList.add("dropdown-up");
    }
  }
  const choice = await choicePromise;
  if (choice !== "add") return;
  const project = projects.find((item) => String(item.id || "") === select.value);
  try {
    await _historyLinkRunToProject(run, project, {
      includeEntities: !!entityOption.checkbox.checked && !entityOption.checkbox.disabled
    });
  } catch (err) {
    _historyProjectLogEvent("history project link failed", err, _historyProjectLogPayload(
      "HISTORY_PROJECT_LINK_FAILED",
      "error",
      run,
      project,
      {
        includeEntities: !!entityOption.checkbox.checked && !entityOption.checkbox.disabled,
        operation: "add-run-to-project"
      }
    ));
    _historyProjectShowToast("Failed to add run to project", "error");
  }
}
if (typeof window !== "undefined") {
}

// app/static/js/features/history/history_rows.js
var HISTORY_ROWS_GLOBAL = typeof window !== "undefined" ? window : globalThis;
function _historyRowsGlobalFunction(name) {
  const fn = HISTORY_ROWS_GLOBAL?.[name];
  return typeof fn === "function" ? fn : null;
}
function _historyRowsCore() {
  return typeof DarklabHistoryCore !== "undefined" && DarklabHistoryCore || null;
}
function _historyRowsShowToast(message, tone = "success") {
  const toast = typeof showToast !== "undefined" && showToast || _historyRowsGlobalFunction("showToast");
  if (typeof toast === "function") toast(message, tone);
}
function _historyRowsActiveTeamScopeCan(capability) {
  const can = typeof activeTeamScopeCan !== "undefined" && activeTeamScopeCan || null;
  return typeof can === "function" ? can(capability) : true;
}
function _historyRowsCanManageHistory() {
  const canManage = typeof _historyCanManageHistory !== "undefined" && _historyCanManageHistory || _historyRowsGlobalFunction("_historyCanManageHistory");
  return typeof canManage === "function" ? canManage() : _historyRowsActiveTeamScopeCan("manage_history");
}
function _historyRowsUseMobileTerminalViewportMode() {
  const useMobile = typeof useMobileTerminalViewportMode !== "undefined" && useMobileTerminalViewportMode || null;
  return typeof useMobile === "function" ? useMobile() : false;
}
function _historyRelativeTime(startedAt, now = /* @__PURE__ */ new Date()) {
  return _historyRowsCore().relativeTime(startedAt, now);
}
function _historyMetaKindBadge(kind, label = kind.toUpperCase()) {
  const badge = document.createElement("span");
  const tone = kind === "run" ? "badge-tone-green" : "badge-tone-muted";
  badge.className = `history-entry-kind history-entry-kind-${kind} badge ${tone}`;
  badge.textContent = label;
  return badge;
}
function _historyEntityLabelValues(entity) {
  const labels = entity && Array.isArray(entity.labels) ? entity.labels : [];
  return labels.map((label) => String(label && typeof label === "object" ? label.label : label || "").trim()).filter(Boolean);
}
function _historyEntityNoteBody(entity) {
  const note = entity && entity.note && typeof entity.note === "object" ? entity.note : null;
  return note ? String(note.body || "").trim() : "";
}
function _appendHistoryMetadataBadges(parent, entity) {
  if (!parent) return;
  const labels = _historyEntityLabelValues(entity);
  const visibleLabels = labels.slice(0, 3);
  visibleLabels.forEach((label) => {
    const badge = document.createElement("span");
    badge.className = "history-entry-label-badge badge badge-tone-muted";
    badge.textContent = label;
    badge.title = `label: ${label}`;
    parent.appendChild(badge);
  });
  if (labels.length > visibleLabels.length) {
    const overflow = document.createElement("span");
    overflow.className = "history-entry-label-badge badge badge-tone-muted";
    overflow.textContent = `+${labels.length - visibleLabels.length}`;
    overflow.title = `${labels.length - visibleLabels.length} more labels`;
    parent.appendChild(overflow);
  }
  if (_historyEntityNoteBody(entity)) {
    const note = document.createElement("span");
    note.className = "history-entry-note-badge badge badge-tone-cyan";
    note.textContent = "note";
    note.title = "note saved";
    parent.appendChild(note);
  }
}
function _historyExitLabel(exitCode) {
  return _historyRowsCore().exitLabel(exitCode);
}
function _historyExitClass(exitCode) {
  return _historyRowsCore().exitClass(exitCode);
}
function _historyCountLabel(count, singular, plural) {
  const numeric = Math.max(0, Number(count || 0));
  return `${numeric.toLocaleString()} ${numeric === 1 ? singular : plural}`;
}
function _historyElapsedLabel(run) {
  return _historyRowsCore().elapsedLabel(run);
}
function _historyCanEditMetadata() {
  return _historyRowsCanManageHistory();
}
function _historyCanDeleteItems() {
  return _historyRowsCanManageHistory();
}
function _createHistoryActionMenu(run, { includeDelete = false } = {}) {
  const wrap = document.createElement("div");
  wrap.className = "history-action-menu-wrap save-menu-wrap save-menu-down";
  const trigger = document.createElement("button");
  trigger.className = "history-action-btn btn btn-secondary btn-compact";
  trigger.type = "button";
  trigger.dataset.action = "history-menu";
  trigger.textContent = "more";
  trigger.setAttribute("aria-label", "More history actions");
  trigger.setAttribute("aria-expanded", "false");
  const menu = document.createElement("div");
  menu.className = "history-action-menu save-menu dropdown-surface";
  const projectLinks = Array.isArray(run?.project_links) ? run.project_links : [];
  const isProjectLinkableRun = String(run?.run_kind || "external") !== "builtin";
  const items = [];
  if (_historyCanEditMetadata()) items.push(["edit-metadata", "edit"]);
  if (isProjectLinkableRun) items.push(["open-atlas", "open in atlas"]);
  items.push(
    ...isProjectLinkableRun ? [["watch-command", "create watcher from this baseline"]] : [],
    ["permalink", "permalink"],
    ["compare", "compare"]
  );
  if (isProjectLinkableRun && projectLinks.length) {
    items.push(["remove-project", "remove from project"]);
  } else if (isProjectLinkableRun) {
    items.push(["add-active-project", "add to active project"]);
    items.push(["add-project", "add to project"]);
  }
  items.push(["copy-run-id", "copy run id"]);
  if (includeDelete && _historyCanDeleteItems()) items.push(["delete", "delete"]);
  items.forEach(([action, label]) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "dropdown-item dropdown-item-compact";
    item.dataset.action = action;
    item.dataset.runId = String(run.id || "");
    item.textContent = label;
    menu.appendChild(item);
  });
  wrap.append(trigger, menu);
  return wrap;
}
function _createHistoryEntry(run, isStarred, options = {}) {
  const entry = document.createElement("div");
  const selectMode = !!options.selectMode;
  const selectable = options.selectable !== false;
  const selected = !!options.selected;
  entry.className = "history-entry chrome-row chrome-row-clickable" + (isStarred ? " starred row-accent-amber" : "") + (selectMode ? " history-entry-selecting" : "");
  const exitCls = _historyExitClass(run.exit_code);
  const startedAt = new Date(run.started);
  const now = /* @__PURE__ */ new Date();
  const validDate = !Number.isNaN(startedAt.getTime());
  const time = startedAt.toLocaleTimeString();
  const showDate = validDate && (startedAt.getFullYear() !== now.getFullYear() || startedAt.getMonth() !== now.getMonth() || startedAt.getDate() !== now.getDate());
  const header = document.createElement("div");
  header.className = "history-entry-header";
  if (selectMode) {
    const selectionBusy = !!options.selectionBusy;
    const selectLabel = document.createElement("label");
    selectLabel.className = "history-entry-select-row" + (selectable && !selectionBusy ? "" : " history-entry-select-disabled");
    if (!selectable) {
      selectLabel.title = "This run cannot be selected until it has finished.";
    } else if (selectionBusy) {
      selectLabel.title = "Bulk action is finishing.";
    }
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.dataset.action = "select-run";
    checkbox.dataset.historySelectItemId = `run:${String(run.id || "")}`;
    checkbox.checked = selected;
    checkbox.disabled = !selectable || selectionBusy;
    checkbox.setAttribute("aria-label", `Select run: ${run.command || run.id || "run"}`);
    selectLabel.appendChild(checkbox);
    header.appendChild(selectLabel);
  }
  const starBtn = document.createElement("button");
  starBtn.className = "history-entry-star" + (isStarred ? " starred" : "");
  starBtn.dataset.action = "star";
  starBtn.type = "button";
  const starLabel = isStarred ? "Unstar — stop pinning this command to the top of history" : "Star — keep this command pinned at the top of history";
  starBtn.setAttribute("aria-label", starLabel);
  starBtn.title = starLabel;
  starBtn.textContent = isStarred ? "★" : "☆";
  header.appendChild(starBtn);
  const cmd = document.createElement("div");
  cmd.className = "history-entry-cmd";
  cmd.textContent = run.command || "";
  header.appendChild(cmd);
  entry.appendChild(header);
  const meta = document.createElement("div");
  meta.className = "history-entry-meta";
  meta.appendChild(_historyMetaKindBadge("run"));
  if (run.scheduled || run.schedule_id) {
    const scheduleOwnerKind = String(run.schedule_owner_kind || "");
    const scheduleOwnerId = String(run.schedule_owner_id || run.watcher_id || "");
    const isWatcherRun = scheduleOwnerKind === "watcher" && scheduleOwnerId;
    const scheduledBadge = _historyMetaKindBadge("schedule", "scheduled");
    scheduledBadge.title = isWatcherRun ? `Watcher ${scheduleOwnerId}` : run.schedule_id ? `Schedule ${run.schedule_id}` : "Scheduled run";
    if (run.schedule_id || isWatcherRun) {
      scheduledBadge.classList.add("chip-action");
      scheduledBadge.dataset.action = "open-schedule";
      scheduledBadge.dataset.scheduleId = run.schedule_id;
      scheduledBadge.dataset.scheduleOwnerKind = scheduleOwnerKind;
      scheduledBadge.dataset.scheduleOwnerId = scheduleOwnerId;
      scheduledBadge.setAttribute("role", "button");
      scheduledBadge.tabIndex = 0;
      scheduledBadge.setAttribute(
        "aria-label",
        isWatcherRun ? `Open watcher ${scheduleOwnerId}` : `Open schedule ${run.schedule_id}`
      );
    }
    meta.appendChild(scheduledBadge);
  }
  _appendHistoryMetadataBadges(meta, run);
  const timeEl = document.createElement("span");
  timeEl.textContent = time;
  if (validDate) timeEl.title = startedAt.toLocaleString();
  meta.appendChild(timeEl);
  if (showDate) {
    const dateEl = document.createElement("span");
    dateEl.className = "history-entry-date";
    dateEl.textContent = startedAt.toLocaleDateString();
    meta.appendChild(dateEl);
  }
  const elapsedLabel = _historyElapsedLabel(run);
  if (elapsedLabel) {
    const elapsedEl = document.createElement("span");
    elapsedEl.className = "history-entry-elapsed";
    elapsedEl.textContent = elapsedLabel;
    meta.appendChild(elapsedEl);
  }
  const artifactCount = Number(run.artifact_count || (Array.isArray(run.artifacts) ? run.artifacts.length : 0));
  if (Number.isFinite(artifactCount) && artifactCount > 0) {
    const artifactEl = document.createElement("span");
    artifactEl.className = "history-entry-artifacts";
    artifactEl.textContent = artifactCount === 1 ? "1 artifact" : `${artifactCount} artifacts`;
    meta.appendChild(artifactEl);
  }
  const exitEl = document.createElement("span");
  exitEl.className = exitCls;
  exitEl.textContent = _historyExitLabel(run.exit_code);
  meta.appendChild(exitEl);
  entry.appendChild(meta);
  const isExternalRun = String(run.run_kind || "external") !== "builtin";
  if (isExternalRun) {
    const atlasEntityCount = Number(run.atlas_entity_count || 0);
    const atlasFindingCount = Number(run.atlas_finding_count || 0);
    if (atlasEntityCount > 0 || atlasFindingCount > 0) {
      const atlasMeta = document.createElement("div");
      atlasMeta.className = "history-entry-atlas";
      atlasMeta.textContent = `Atlas: ${_historyCountLabel(atlasEntityCount, "entity", "entities")} · ${_historyCountLabel(atlasFindingCount, "finding", "findings")}`;
      entry.appendChild(atlasMeta);
    }
  }
  const actions = document.createElement("div");
  actions.className = "history-actions";
  const isMobile = _historyRowsUseMobileTerminalViewportMode();
  const copyCommandBtn = document.createElement("button");
  copyCommandBtn.className = "history-action-btn btn btn-secondary btn-compact";
  copyCommandBtn.type = "button";
  copyCommandBtn.dataset.action = "copy-command";
  copyCommandBtn.textContent = "copy command";
  actions.appendChild(copyCommandBtn);
  const restoreBtn = document.createElement("button");
  restoreBtn.className = "history-action-btn btn btn-secondary btn-compact";
  restoreBtn.type = "button";
  restoreBtn.dataset.action = "restore";
  restoreBtn.textContent = "restore";
  actions.appendChild(restoreBtn);
  if (!isMobile && _historyCanDeleteItems()) {
    const deleteBtn = document.createElement("button");
    deleteBtn.className = "history-action-btn btn btn-secondary btn-compact";
    deleteBtn.type = "button";
    deleteBtn.dataset.action = "delete";
    deleteBtn.textContent = "delete";
    actions.appendChild(deleteBtn);
  }
  actions.appendChild(_createHistoryActionMenu(run, { includeDelete: isMobile }));
  entry.appendChild(actions);
  return entry;
}
function _createSnapshotHistoryEntry(snapshot, options = {}) {
  const entry = document.createElement("div");
  const selectMode = !!options.selectMode;
  const selectable = options.selectable !== false;
  const selected = !!options.selected;
  entry.className = "history-entry history-entry-snapshot chrome-row chrome-row-clickable" + (selectMode ? " history-entry-selecting" : "");
  const header = document.createElement("div");
  header.className = "history-entry-header";
  if (selectMode) {
    const selectionBusy = !!options.selectionBusy;
    const selectLabel = document.createElement("label");
    selectLabel.className = "history-entry-select-row" + (selectable && !selectionBusy ? "" : " history-entry-select-disabled");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.dataset.action = "select-run";
    checkbox.dataset.historySelectItemId = `snapshot:${String(snapshot.id || "")}`;
    checkbox.checked = selected;
    checkbox.disabled = !selectable || selectionBusy;
    checkbox.setAttribute("aria-label", `Select snapshot: ${snapshot.label || snapshot.id || "snapshot"}`);
    selectLabel.appendChild(checkbox);
    header.appendChild(selectLabel);
  }
  const title = document.createElement("div");
  title.className = "history-entry-cmd";
  title.textContent = snapshot.label || "snapshot";
  header.appendChild(title);
  entry.appendChild(header);
  const meta = document.createElement("div");
  meta.className = "history-entry-meta";
  meta.appendChild(_historyMetaKindBadge("snapshot"));
  _appendHistoryMetadataBadges(meta, snapshot);
  const createdAt = new Date(snapshot.created);
  const timeEl = document.createElement("span");
  timeEl.textContent = Number.isNaN(createdAt.getTime()) ? "" : _historyRelativeTime(createdAt);
  if (!Number.isNaN(createdAt.getTime())) timeEl.title = createdAt.toLocaleString();
  meta.appendChild(timeEl);
  entry.appendChild(meta);
  const actions = document.createElement("div");
  actions.className = "history-actions";
  const openBtn = document.createElement("button");
  openBtn.className = "history-action-btn btn btn-secondary btn-compact";
  openBtn.type = "button";
  openBtn.dataset.action = "open";
  openBtn.textContent = "open";
  actions.appendChild(openBtn);
  const linkBtn = document.createElement("button");
  linkBtn.className = "history-action-btn btn btn-secondary btn-compact";
  linkBtn.type = "button";
  linkBtn.dataset.action = "link";
  linkBtn.textContent = "copy link";
  actions.appendChild(linkBtn);
  if (_historyCanEditMetadata()) {
    const editBtn = document.createElement("button");
    editBtn.className = "history-action-btn btn btn-secondary btn-compact";
    editBtn.type = "button";
    editBtn.dataset.action = "edit-metadata";
    editBtn.textContent = "edit";
    actions.appendChild(editBtn);
  }
  if (_historyCanDeleteItems()) {
    const deleteBtn = document.createElement("button");
    deleteBtn.className = "history-action-btn btn btn-secondary btn-compact";
    deleteBtn.type = "button";
    deleteBtn.dataset.action = "delete";
    deleteBtn.textContent = "delete";
    actions.appendChild(deleteBtn);
  }
  entry.appendChild(actions);
  return entry;
}
function _historyActionKeepsPanelOpen(action) {
  if (action === "star") return true;
  if (action === "compare") return true;
  if (action === "edit-metadata") return true;
  const mobileMode = _historyRowsUseMobileTerminalViewportMode();
  if (!mobileMode) return false;
  return action === "permalink";
}
function _historyEditEntityMetadata(entityType, entity) {
  const editor = typeof openEntityMetadataEditor === "function" ? openEntityMetadataEditor : null;
  if (typeof editor !== "function") {
    _historyRowsShowToast("Metadata editor is not available", "error");
    return;
  }
  editor(entityType, entity, {
    onSaved: async () => {
      const refreshHistoryPanel3 = typeof refreshHistoryPanel === "function" && refreshHistoryPanel || _historyRowsGlobalFunction("refreshHistoryPanel");
      if (refreshHistoryPanel3) refreshHistoryPanel3();
      _historyRowsShowToast("Metadata saved");
    }
  });
}
if (typeof window !== "undefined") {
}

// app/static/js/features/history/history_restore.js
var HISTORY_RESTORE_GLOBAL = typeof window !== "undefined" ? window : globalThis;
function _historyRestoreGlobalFunction(name) {
  const fn = HISTORY_RESTORE_GLOBAL && HISTORY_RESTORE_GLOBAL[name];
  return typeof fn === "function" ? fn : null;
}
function _historyRestoreTabs() {
  const getTabsFn = typeof getTabs !== "undefined" && getTabs || _historyRestoreGlobalFunction("getTabs");
  if (typeof getTabsFn === "function") return getTabsFn();
  const stateTabs = HISTORY_RESTORE_GLOBAL.tabs;
  return Array.isArray(stateTabs) ? stateTabs : [];
}
function _historyRestoreGetTab(tabId) {
  const getTabFn = typeof getTab !== "undefined" && getTab || _historyRestoreGlobalFunction("getTab");
  return typeof getTabFn === "function" ? getTabFn(tabId) : null;
}
function _historyRestoreGetOutput(tabId) {
  const getOutputForTab = typeof getOutput !== "undefined" && getOutput || _historyRestoreGlobalFunction("getOutput");
  return typeof getOutputForTab === "function" ? getOutputForTab(tabId) : null;
}
function _historyRestoreCreateTab(label) {
  const create = typeof createTab !== "undefined" && createTab || _historyRestoreGlobalFunction("createTab");
  return typeof create === "function" ? create(label) : null;
}
function _historyRestoreClearTab(tabId) {
  const clear = typeof clearTab !== "undefined" && clearTab || _historyRestoreGlobalFunction("clearTab");
  if (typeof clear === "function") clear(tabId);
}
function _historyRestoreAppendLine(text, cls, tabId, metadata = null) {
  const append = typeof appendLine !== "undefined" && appendLine || _historyRestoreGlobalFunction("appendLine");
  if (typeof append !== "function") return;
  if (metadata) append(text, cls, tabId, metadata);
  else append(text, cls, tabId);
}
function _historyRestoreSetTabStatus(tabId, status) {
  const setStatus = typeof setTabStatus !== "undefined" && setTabStatus || _historyRestoreGlobalFunction("setTabStatus");
  if (typeof setStatus === "function") setStatus(tabId, status);
}
function _historyRestoreApiFetch(url, options) {
  const api = typeof apiFetch === "function" && typeof hasRuntimeHandler === "function" && hasRuntimeHandler("apiFetch") ? apiFetch : _historyRestoreGlobalFunction("apiFetch");
  if (typeof api === "function") return options === void 0 ? api(url) : api(url, options);
  return options === void 0 ? fetch(url) : fetch(url, options);
}
function _historyRestoreAppendCommandEcho(tabId, command) {
  if (typeof appendCommandEcho === "function" && typeof hasRunnerHandler === "function" && hasRunnerHandler("appendCommandEcho")) {
    appendCommandEcho(command, tabId);
    return;
  }
  const legacyAppendCommandEcho = HISTORY_RESTORE_GLOBAL && HISTORY_RESTORE_GLOBAL.appendCommandEcho;
  if (typeof legacyAppendCommandEcho === "function") {
    legacyAppendCommandEcho(command, tabId);
    return;
  }
  _historyRestoreAppendLine(command, "prompt-echo", tabId);
}
function _historyRestoreOutputLineMetadata(entry) {
  if (!entry || typeof entry !== "object") return null;
  const metadata = {};
  if (Array.isArray(entry.signals) && entry.signals.length) metadata.signals = entry.signals;
  if (typeof entry.kind === "string" && entry.kind) metadata.kind = entry.kind;
  if (typeof entry.role === "string" && entry.role) metadata.role = entry.role;
  if (Number.isInteger(entry.line_index)) metadata.line_index = entry.line_index;
  if (Number.isInteger(entry.line_number)) metadata.line_number = entry.line_number;
  if (typeof entry.command_root === "string" && entry.command_root) metadata.command_root = entry.command_root;
  if (typeof entry.target === "string" && entry.target) metadata.target = entry.target;
  if (entry.template_provenance && typeof entry.template_provenance === "object") {
    metadata.template_provenance = entry.template_provenance;
  }
  if (entry.source_detail && typeof entry.source_detail === "object") {
    metadata.source_detail = entry.source_detail;
  }
  return Object.keys(metadata).length ? metadata : null;
}
function _historyRestoreAppendOutputLine(entry, tabId) {
  if (entry && typeof entry === "object") {
    const text = String(entry.text || "");
    const cls = String(entry.cls || "");
    const metadata = _historyRestoreOutputLineMetadata(entry);
    _historyRestoreAppendLine(text, cls, tabId, metadata);
    return;
  }
  _historyRestoreAppendLine(String(entry || ""), "", tabId);
}
function _historyRestoreExitLabel(exitCode) {
  const label = typeof _historyExitLabel !== "undefined" && _historyExitLabel || _historyRestoreGlobalFunction("_historyExitLabel");
  return typeof label === "function" ? label(exitCode) : `exit ${exitCode ?? "unknown"}`;
}
function _historyRestoreExitClass(exitCode) {
  const cls = typeof _historyExitClass !== "undefined" && _historyExitClass || _historyRestoreGlobalFunction("_historyExitClass");
  return typeof cls === "function" ? cls(exitCode) : "";
}
function _historyRestoreRenderCommandOutcomeSummary(tabId, outcome) {
  const render = typeof renderCommandOutcomeSummary !== "undefined" && renderCommandOutcomeSummary || _historyRestoreGlobalFunction("renderCommandOutcomeSummary");
  if (typeof render === "function") render(tabId, outcome);
}
function _historyRunIdentity(run) {
  return String(run?.id || run?.run_id || "").trim();
}
function _tabForHistoryRun(run) {
  const runId = _historyRunIdentity(run);
  if (!runId) return null;
  return _historyRestoreTabs().find((t) => t && (String(t.historyRunId || "") === runId || String(t.runId || "") === runId)) || null;
}
function _scrollHistoryHighlightIntoView(out, line) {
  if (!out || !line || typeof out.contains !== "function" || !out.contains(line)) return false;
  if (typeof out.getBoundingClientRect !== "function" || typeof line.getBoundingClientRect !== "function") return false;
  const outRect = out.getBoundingClientRect();
  const lineRect = line.getBoundingClientRect();
  const targetTop = Number(lineRect.top) - Number(outRect.top);
  const lineHeight = Number(lineRect.height) || Number(line.offsetHeight) || 0;
  const outHeight = Number(out.clientHeight) || Number(outRect.height) || 0;
  if (!Number.isFinite(targetTop) || outHeight <= 0) return false;
  out.scrollTop += targetTop - outHeight / 2 + lineHeight / 2;
  return true;
}
function _highlightRestoredHistoryLine(tabId, { lineNumber = null, lineIndex = null } = {}) {
  const out = _historyRestoreGetOutput(tabId);
  if (!out) return false;
  const cssEscape = (value) => typeof CSS !== "undefined" && CSS && typeof CSS.escape === "function" ? CSS.escape(String(value)) : String(value).replace(/"/g, '\\"');
  const normalizedLineNumber = Number(lineNumber || 0);
  const normalizedLineIndex = Number(lineIndex);
  const selector = normalizedLineNumber > 0 ? `.line[data-line-number="${cssEscape(normalizedLineNumber)}"]` : Number.isInteger(normalizedLineIndex) ? `.line[data-line-index="${cssEscape(normalizedLineIndex)}"]` : "";
  if (!selector) return false;
  const line = out.querySelector(selector);
  if (!line) return false;
  out.querySelectorAll(".line.history-source-highlight").forEach((node) => {
    node.classList.remove("history-source-highlight");
  });
  line.classList.add("history-source-highlight");
  const tab = _historyRestoreGetTab(tabId);
  if (tab) {
    tab.followOutput = false;
  }
  if (!_scrollHistoryHighlightIntoView(out, line) && typeof line.scrollIntoView === "function") {
    line.scrollIntoView({ block: "center" });
  }
  return true;
}
function _historyHasPendingOutput(tabId) {
  const hasPending = typeof hasPendingOutputBatch !== "undefined" && hasPendingOutputBatch || _historyRestoreGlobalFunction("hasPendingOutputBatch");
  return typeof hasPending === "function" && hasPending(tabId);
}
function _scheduleRestoredHistoryLineHighlight(tabId, options) {
  const startedAt = Date.now();
  const runFinalLayoutPasses = () => {
    const run = () => _highlightRestoredHistoryLine(tabId, options);
    if (typeof window.requestAnimationFrame === "function") {
      window.requestAnimationFrame(() => window.requestAnimationFrame(run));
    }
    window.setTimeout(run, 48);
    window.setTimeout(run, 120);
    window.setTimeout(run, 300);
  };
  const retryUntilOutputSettles = () => {
    const highlighted = _highlightRestoredHistoryLine(tabId, options);
    const pending = _historyHasPendingOutput(tabId);
    if ((!highlighted || pending) && Date.now() - startedAt < 2e3) {
      window.setTimeout(retryUntilOutputSettles, pending ? 32 : 50);
      return;
    }
    runFinalLayoutPasses();
  };
  window.setTimeout(retryUntilOutputSettles, 0);
}
function _suppressHistoryRestoreStatusPeek(tabId) {
  const tab = _historyRestoreGetTab(tabId);
  if (!tab) return;
  tab.suppressStatusMonitorPeekHold = true;
  const setTimer = typeof window !== "undefined" && typeof window.setTimeout === "function" ? window.setTimeout.bind(window) : typeof setTimeout === "function" ? setTimeout : null;
  if (!setTimer) return;
  setTimer(() => {
    const live = _historyRestoreGetTab(tabId);
    if (live) delete live.suppressStatusMonitorPeekHold;
  }, 0);
}
function restoreHistoryRunIntoTab(run, {
  targetTabId = null,
  hidePanelOnSuccess = true,
  highlightLineNumber = null,
  highlightLineIndex = null
} = {}) {
  if (!run || !run.id) return Promise.reject(new Error("missing run id"));
  const existing = targetTabId ? _historyRestoreGetTab(targetTabId) : _tabForHistoryRun(run);
  const canUpgradeExisting = !!(existing && run.full_output_available && existing.previewTruncated);
  const restoreUrl = run.full_output_available ? `/history/${run.id}?json` : `/history/${run.id}?json&preview=1`;
  return _historyRestoreApiFetch(restoreUrl).then((r) => r.json()).then((fullRun) => {
    const previewNotice = fullRun.preview_notice || null;
    const tabId = targetTabId || (canUpgradeExisting ? existing.id : _historyRestoreCreateTab(fullRun.command));
    if (!tabId) throw new Error("failed to create restore tab");
    _historyRestoreClearTab(tabId);
    const t = _historyRestoreGetTab(tabId);
    if (t) {
      t.command = fullRun.command;
      t.runId = null;
      t.historyRunId = fullRun.id || run.id;
      t.exitCode = fullRun.exit_code;
      t.previewTruncated = !!previewNotice;
      t.fullOutputAvailable = !!fullRun.full_output_available;
      t.fullOutputLoaded = !!fullRun.full_output_available && !previewNotice;
      t.reconnectedRun = false;
      t.commandOutcomeSummary = fullRun.command_outcome_summary || fullRun.output_outcome_summary || null;
    }
    _historyRestoreAppendCommandEcho(tabId, fullRun.command);
    const outputLines = Array.isArray(fullRun.output_entries) ? fullRun.output_entries : fullRun.output || [];
    outputLines.forEach((line) => _historyRestoreAppendOutputLine(line, tabId));
    if (previewNotice) _historyRestoreAppendLine(previewNotice, "notice", tabId);
    _historyRestoreAppendLine(
      `[history — ${_historyRestoreExitLabel(fullRun.exit_code)}]`,
      _historyRestoreExitClass(fullRun.exit_code),
      tabId
    );
    _historyRestoreRenderCommandOutcomeSummary(tabId, t && t.commandOutcomeSummary);
    _suppressHistoryRestoreStatusPeek(tabId);
    _historyRestoreSetTabStatus(tabId, fullRun.exit_code === 0 ? "ok" : "fail");
    const hideKill = typeof hideTabKillBtn === "function" && hideTabKillBtn || _historyRestoreGlobalFunction("hideTabKillBtn");
    if (hideKill) hideKill(tabId);
    const hidePanel = typeof hideHistoryPanel === "function" && hideHistoryPanel || _historyRestoreGlobalFunction("hideHistoryPanel");
    if (hidePanelOnSuccess && hidePanel) hidePanel();
    if (highlightLineNumber || Number.isInteger(highlightLineIndex)) {
      _scheduleRestoredHistoryLineHighlight(tabId, {
        lineNumber: highlightLineNumber,
        lineIndex: highlightLineIndex
      });
    }
    return tabId;
  });
}
function restoreHistoryRun(runOrId, options = {}) {
  const run = typeof runOrId === "object" && runOrId !== null ? runOrId : { id: String(runOrId || ""), full_output_available: true };
  return restoreHistoryRunIntoTab(run, {
    hidePanelOnSuccess: false,
    ...options
  });
}
if (typeof setHistoryRestoreHandlers === "function") {
  setHistoryRestoreHandlers({
    restoreHistoryRun,
    restoreHistoryRunIntoTab
  });
}

// app/static/js/history.js
function _historyCore() {
  return typeof DarklabHistoryCore !== "undefined" && DarklabHistoryCore || null;
}
var HISTORY_GLOBAL = typeof window !== "undefined" ? window : globalThis;
function _historyFn(name, imported = null) {
  if (typeof imported === "function") return imported;
  const fn = HISTORY_GLOBAL && HISTORY_GLOBAL[name];
  return typeof fn === "function" ? fn : null;
}
function _historyValue(name, imported = void 0) {
  if (imported !== void 0) return imported;
  if (HISTORY_GLOBAL && HISTORY_GLOBAL[name] !== void 0) return HISTORY_GLOBAL[name];
  if (typeof __darklabExtractGlobals !== "undefined" && __darklabExtractGlobals && __darklabExtractGlobals[name] !== void 0) {
    return __darklabExtractGlobals[name];
  }
  return void 0;
}
function _historyEl(name, imported = void 0) {
  return _historyValue(name, imported) || null;
}
function _historyAppConfig() {
  return _historyValue("APP_CONFIG") || {};
}
function _historyState() {
  const state = _historyFn("getAppState", getAppState)?.();
  return state || _historyValue("APP_STATE") || {};
}
var _historyApiFetch = (...args) => _historyFn("apiFetch", apiFetch2)?.(...args);
var _historyShowToast = (...args) => _historyFn("showToast", showToast)?.(...args);
var _historyBindPressable = (...args) => _historyFn("bindPressable", bindPressable)?.(...args);
var _historyShowConfirm = (...args) => _historyFn("showConfirm", showConfirm)?.(...args);
var _historyEmitUiEvent = (...args) => _historyFn("emitUiEvent", emitUiEvent)?.(...args);
var _historyEscapeHtml = (text) => _historyFn("escapeHtml", escapeHtml)?.(text) ?? String(text ?? "");
var _historyCopyTextToClipboard = (...args) => _historyFn("copyTextToClipboard", copyTextToClipboard)?.(...args);
var _historyDownloadBlobAsAttachment = (...args) => {
  const globalDownloader = _historyFn("downloadBlobAsAttachment");
  const downloader = globalDownloader || _historyFn("downloadBlobAsAttachment", downloadBlobAsAttachment);
  return downloader?.(...args);
};
var _historyEnhanceAppSelects = (...args) => _historyFn("enhanceAppSelects", enhanceAppSelects)?.(...args);
var _historySyncAppSelect = (...args) => _historyFn("syncAppSelect", syncAppSelect)?.(...args);
var _historyUseMobileTerminalViewportMode = () => !!_historyFn("useMobileTerminalViewportMode", useMobileTerminalViewportMode)?.();
var histClearAllBtn2 = _historyEl("histClearAllBtn", histClearAllBtn);
var histRow2 = _historyEl("histRow", histRow);
var historyActiveFilters2 = _historyEl("historyActiveFilters", historyActiveFilters);
var historyBulkToolbar2 = _historyEl("historyBulkToolbar", historyBulkToolbar);
var historyClearFiltersBtn2 = _historyEl("historyClearFiltersBtn", historyClearFiltersBtn);
var historyDateFilter2 = _historyEl("historyDateFilter", historyDateFilter);
var historyEntityInput2 = _historyEl("historyEntityInput", historyEntityInput);
var historyEntityTypeFilter2 = _historyEl("historyEntityTypeFilter", historyEntityTypeFilter);
var historyExitFilter2 = _historyEl("historyExitFilter", historyExitFilter);
var historyKindFilter2 = _historyEl("historyKindFilter", historyKindFilter);
var historyList2 = _historyEl("historyList", historyList);
var historyLoadOverlay2 = _historyEl("historyLoadOverlay", historyLoadOverlay);
var historyMobileFiltersToggle2 = _historyEl("historyMobileFiltersToggle", historyMobileFiltersToggle);
var historyPagination2 = _historyEl("historyPagination", historyPagination);
var historyPaginationControls2 = _historyEl("historyPaginationControls", historyPaginationControls);
var historyPaginationSummary2 = _historyEl("historyPaginationSummary", historyPaginationSummary);
var historyPanel2 = _historyEl("historyPanel", historyPanel);
var historyProjectFilter2 = _historyEl("historyProjectFilter", historyProjectFilter);
var historyRootDropdown2 = _historyEl("historyRootDropdown", historyRootDropdown);
var historyRootInput2 = _historyEl("historyRootInput", historyRootInput);
var historySearchInput2 = _historyEl("historySearchInput", historySearchInput);
var historySignalFilter2 = _historyEl("historySignalFilter", historySignalFilter);
var historyStarredToggle2 = _historyEl("historyStarredToggle", historyStarredToggle);
var historyTypeFilter2 = _historyEl("historyTypeFilter", historyTypeFilter);
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
var _historyBlurActiveElementAdapter = (...args) => _historyFn("blurActiveElement", blurActiveElement)?.(...args);
var _historyFocusElementAdapter = (...args) => _historyFn("focusElement", focusElement)?.(...args);
var _historyHidePanelAdapter = (...args) => _historyFn("hideHistoryPanel", hideHistoryPanel)?.(...args);
var _historyHideRowAdapter = (...args) => _historyFn("hideHistoryRow", exportedHideHistoryRow)?.(...args);
var _historyRefocusComposerAdapter = (...args) => _historyFn("refocusComposerAfterAction", refocusComposerAfterAction)?.(...args);
var _historySetComposerValueAdapter = (...args) => _historyFn("setComposerValue", setComposerValue)?.(...args);
var _historyShowPanelAdapter = (...args) => _historyFn("showHistoryPanel", exportedShowHistoryPanel)?.(...args);
var _historyShowRowAdapter = (...args) => _historyFn("showHistoryRow", exportedShowHistoryRow)?.(...args);
var _historyResetCmdNavAdapter = (...args) => _historyFn("resetCmdHistoryNav", resetCmdHistoryNav)?.(...args);
var _historyTogglePanelSurfaceAdapter = (...args) => _historyFn("toggleHistoryPanelSurface", toggleHistoryPanelSurface)?.(...args);
var _historyActivateTabAdapter = (...args) => _historyFn("activateTab", activateTab)?.(...args);
var _historyCloseActionMenusAdapter = (...args) => _historyFn("_closeHistoryActionMenus", _closeHistoryActionMenus)?.(...args);
var _historyCloseCompareActionMenusAdapter = (...args) => typeof hasHistoryCompareHandler === "function" && hasHistoryCompareHandler("closeHistoryCompareActionMenus") && typeof closeHistoryCompareActionMenus === "function" ? closeHistoryCompareActionMenus(...args) : void 0;
var _historyCloseRunActionMenusAdapter = (...args) => _historyFn("_closeHistoryRunActionMenus", _closeHistoryRunActionMenus)?.(...args);
var _historyCreateEntryAdapter = (...args) => _historyFn("_createHistoryEntry", _createHistoryEntry)?.(...args);
var _historyCreateSnapshotEntryAdapter = (...args) => _historyFn("_createSnapshotHistoryEntry", _createSnapshotHistoryEntry)?.(...args);
var _historyEnsureProjectFilterOptionsAdapter = (...args) => _ensureHistoryProjectFilterOptions?.(...args);
var _historyGetStarredAdapter = (...args) => _historyFn("_getStarred", _getStarred)?.(...args);
var _historyActionKeepsPanelOpenAdapter = (...args) => _historyFn("_historyActionKeepsPanelOpen", _historyActionKeepsPanelOpen)?.(...args);
var _historyEditEntityMetadataAdapter = (...args) => _historyFn("_historyEditEntityMetadata", _historyEditEntityMetadata)?.(...args);
var _historyProjectFromLinkAdapter = (...args) => _historyProjectFromLink?.(...args);
var _historyProjectDisplayNameAdapter = (...args) => _historyProjectDisplayName?.(...args);
var _historyProjectLabelForIdAdapter = (...args) => _historyProjectLabelForId?.(...args);
var _historyLoadActiveProjectAdapter = (...args) => _historyLoadActiveProject?.(...args);
var _historyLoadProjectsAdapter = (...args) => _historyLoadProjects?.(...args);
var _historyOrderProjectsForPickerAdapter = (...args) => _historyOrderProjectsForPicker?.(...args);
var _historyProjectPickerContentAdapter = (...args) => _historyProjectPickerContent?.(...args);
var _historyProjectRunEntityOptionContentAdapter = (...args) => _historyProjectRunEntityOptionContent?.(...args);
var _historyRefreshProjectRunEntityOptionAdapter = (...args) => _historyRefreshProjectRunEntityOption?.(...args);
var _historyAddRunToActiveProjectAdapter = (...args) => _historyAddRunToActiveProject?.(...args);
var _historyAddRunToProjectAdapter = (...args) => _historyAddRunToProject?.(...args);
var _historyRemoveRunFromProjectAdapter = (...args) => _historyRemoveRunFromProject?.(...args);
var _historyRestoreRunIntoTabAdapter = (...args) => restoreHistoryRunIntoTab?.(...args);
var _historyPositionActionMenuAdapter = (...args) => _historyFn("_positionHistoryActionMenu", _positionHistoryActionMenu)?.(...args);
var _historyResetActionMenuPositionAdapter = (...args) => _historyFn("_resetHistoryActionMenuPosition", _resetHistoryActionMenuPosition)?.(...args);
var _historyTabForRunAdapter = (...args) => _historyFn("_tabForHistoryRun", _tabForHistoryRun)?.(...args);
var _historyToggleStarAdapter = (...args) => _historyFn("_toggleStar", _toggleStar)?.(...args);
var _historyCopyRunPermalinkAdapter = (...args) => _historyFn("copyHistoryRunPermalink", copyHistoryRunPermalink)?.(...args);
var _historyCopySnapshotLinkAdapter = (...args) => _historyFn("copySnapshotLink", copySnapshotLink)?.(...args);
var _historyOpenSnapshotLinkAdapter = (...args) => _historyFn("openSnapshotLink", openSnapshotLink)?.(...args);
var _historyGetActiveProjectContextAdapter = (...args) => _historyFn("getActiveProjectContext", getActiveProjectContext)?.(...args);
var _historyOpenAtlasAdapter = (...args) => _historyFn("openAtlas", openAtlas)?.(...args);
function _historyOpenCompareLauncherAdapter(...args) {
  const importedReady = typeof openHistoryCompareLauncher === "function" && (typeof openHistoryCompareLauncher.hasHandler !== "function" || openHistoryCompareLauncher.hasHandler());
  const launcher = importedReady ? openHistoryCompareLauncher : _historyFn("openHistoryCompareLauncher");
  if (typeof launcher !== "function") return false;
  if (typeof launcher.hasHandler === "function" && !launcher.hasHandler()) return false;
  try {
    const result = launcher(...args);
    return result !== false;
  } catch (_) {
    return false;
  }
}
var _historyOpenRunDetailsAdapter = (...args) => _historyFn("openHistoryRunDetails")?.(...args);
var _historyOpenSchedulesModalAdapter = (...args) => _historyFn("openSchedulesModal")?.(...args);
var _historyOpenWatchersModalAdapter = (...args) => _historyFn("openWatchersModal")?.(...args);
var _historyRefreshProjectWorkspaceAdapter = (...args) => _historyFn("refreshProjectWorkspace", refreshProjectWorkspace)?.(...args);
var _historyCanManageHistoryAdapter = (...args) => _historyFn("_historyCanManageHistory", _historyCanManageHistory)?.(...args);
var _historyMutationErrorAdapter = (...args) => _historyFn("_historyMutationError", _historyMutationError)?.(...args);
var _historyScopeDeniedMessageAdapter = (...args) => _historyFn("_historyScopeDeniedMessage", _historyScopeDeniedMessage)?.(...args);
var _historyShowPermissionDeniedAdapter = (...args) => _historyFn("_historyShowPermissionDenied", _historyShowPermissionDenied)?.(...args);
var _historySetLoadStateAdapter = (...args) => _historyFn("_setHistoryLoadState", _setHistoryLoadState)?.(...args);
var _historyConfirmActionAdapter = (...args) => _historyFn("confirmHistAction", confirmHistAction)?.(...args);
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
var _historyFilterRefreshTimer = null;
var _historyFilters = {
  type: "all",
  q: "",
  commandRoot: "",
  signal: "all",
  kind: "all",
  entity: "",
  entityType: "all",
  exitCode: "all",
  dateRange: "all",
  projectId: "all",
  starredOnly: false
};
var _historyMobileAdvancedOpen = false;
var _historyProjectOptions = [];
var _historyProjectOptionsLoaded = false;
var _historyProjectOptionsLoading = null;
function getHistoryProjectOptionsState() {
  return {
    options: _historyProjectOptions,
    loaded: _historyProjectOptionsLoaded,
    loading: _historyProjectOptionsLoading
  };
}
function setHistoryProjectOptionsState(updates = {}) {
  if (Object.prototype.hasOwnProperty.call(updates, "options")) {
    _historyProjectOptions = Array.isArray(updates.options) ? updates.options : [];
  }
  if (Object.prototype.hasOwnProperty.call(updates, "loaded")) {
    _historyProjectOptionsLoaded = updates.loaded === true;
  }
  if (Object.prototype.hasOwnProperty.call(updates, "loading")) {
    _historyProjectOptionsLoading = updates.loading || null;
  }
  return getHistoryProjectOptionsState();
}
var _historySelection = {
  selectMode: false,
  selected: /* @__PURE__ */ new Map(),
  visibleItems: [],
  bulkInFlight: false
};
var _historyLatestPanelData = null;
var _historyRootSuggestions = [];
var _historyRootFiltered = [];
var _historyRootIndex = -1;
var _historyRootSuppressInputOnce = false;
var _historyRootInputFocused = false;
var _historyPaging = {
  page: 1,
  pageSize: _historyAppConfig() && _historyAppConfig().history_panel_limit ? Math.max(1, Number(_historyAppConfig().history_panel_limit) || 50) : 50,
  totalCount: 0,
  pageCount: 0,
  hasPrev: false,
  hasNext: false
};
var _historyCompareState = {
  source: null,
  candidates: [],
  manualCandidates: [],
  manualLoaded: false,
  manualRequestId: 0,
  manualPage: 1,
  manualHasNext: false,
  manualLoading: false,
  manualCollapsedGroups: /* @__PURE__ */ new Set(),
  selected: null,
  manualQuery: ""
};
var _historyCompareRowPairSequence = 0;
var _historyCompareUnitSequence = 0;
var _historyCompareRowHeightFrame = null;
var _historyCompareRowResizeObserver = null;
var _historyTextFilterKeys = /* @__PURE__ */ new Set(["q", "commandRoot", "entity"]);
var _historyRunOnlyFilterKeys = /* @__PURE__ */ new Set([
  "commandRoot",
  "signal",
  "kind",
  "entity",
  "entityType",
  "exitCode",
  "starredOnly"
]);
var _historyStructuredFilterKeys = /* @__PURE__ */ new Set(["signal", "kind", "entity", "entityType"]);
function _historyGlobal() {
  return typeof window !== "undefined" ? window : globalThis;
}
function _publishHistoryState() {
  const global = _historyGlobal();
  if (!global || global.DarklabHistoryState) return;
  Object.defineProperties(global, {
    DarklabHistoryState: {
      configurable: true,
      value: {}
    },
    _historyFilters: {
      configurable: true,
      get: () => _historyFilters,
      set: (value) => {
        _historyFilters = value && typeof value === "object" ? value : _historyFilters;
      }
    },
    _historyProjectOptions: {
      configurable: true,
      get: () => _historyProjectOptions,
      set: (value) => {
        _historyProjectOptions = Array.isArray(value) ? value : [];
      }
    },
    _historyProjectOptionsLoaded: {
      configurable: true,
      get: () => _historyProjectOptionsLoaded,
      set: (value) => {
        _historyProjectOptionsLoaded = value === true;
      }
    },
    _historyProjectOptionsLoading: {
      configurable: true,
      get: () => _historyProjectOptionsLoading,
      set: (value) => {
        _historyProjectOptionsLoading = value || null;
      }
    },
    _historyCompareState: {
      configurable: true,
      get: () => _historyCompareState,
      set: (value) => {
        _historyCompareState = value && typeof value === "object" ? value : _historyCompareState;
      }
    },
    _historyCompareRowPairSequence: {
      configurable: true,
      get: () => _historyCompareRowPairSequence,
      set: (value) => {
        _historyCompareRowPairSequence = Number(value) || 0;
      }
    },
    _historyCompareUnitSequence: {
      configurable: true,
      get: () => _historyCompareUnitSequence,
      set: (value) => {
        _historyCompareUnitSequence = Number(value) || 0;
      }
    },
    _historyCompareRowHeightFrame: {
      configurable: true,
      get: () => _historyCompareRowHeightFrame,
      set: (value) => {
        _historyCompareRowHeightFrame = value;
      }
    },
    _historyCompareRowResizeObserver: {
      configurable: true,
      get: () => _historyCompareRowResizeObserver,
      set: (value) => {
        _historyCompareRowResizeObserver = value || null;
      }
    },
    _historyPaging: {
      configurable: true,
      get: () => _historyPaging,
      set: (value) => {
        _historyPaging = value && typeof value === "object" ? value : _historyPaging;
      }
    }
  });
}
_publishHistoryState();
function _closeHistoryCompareActionMenusIfLoaded() {
  if (typeof _historyCloseCompareActionMenusAdapter === "function") _historyCloseCompareActionMenusAdapter();
}
function _normalizeHistoryFilterValue(value) {
  return _historyCore().normalizeFilterValue(value);
}
function _historyDefaultFilterValue(key) {
  return _historyTextFilterKeys.has(key) ? "" : "all";
}
function _historyRunOnlyFilterIsActive(key, filters = _historyFilters) {
  if (!_historyRunOnlyFilterKeys.has(key)) return false;
  if (key === "starredOnly") return !!filters.starredOnly;
  return _normalizeHistoryFilterValue(filters[key]) !== _historyDefaultFilterValue(key);
}
function _historyHasActiveRunOnlyFilters(filters = _historyFilters) {
  return [..._historyRunOnlyFilterKeys].some((key) => _historyRunOnlyFilterIsActive(key, filters));
}
function _syncHistoryFilterControls() {
  if (typeof historySearchInput2 !== "undefined" && historySearchInput2) historySearchInput2.value = _historyFilters.q;
  if (typeof historyMobileFiltersToggle2 !== "undefined" && historyMobileFiltersToggle2) {
    const activeCount = _historyActiveFilterItems().length;
    const selectedCount = _historySelection?.selected?.size || 0;
    const status = [];
    if (activeCount > 0) status.push(`${activeCount} ${activeCount === 1 ? "filter" : "filters"}`);
    if (selectedCount > 0) status.push(`${selectedCount} selected`);
    const baseLabel = _historyMobileAdvancedOpen ? "hide history tools" : "history tools";
    historyMobileFiltersToggle2.textContent = status.length ? `${baseLabel} (${status.join(" · ")})` : baseLabel;
    historyMobileFiltersToggle2.setAttribute("aria-expanded", _historyMobileAdvancedOpen ? "true" : "false");
  }
  if (typeof historyPanel2 !== "undefined" && historyPanel2) {
    historyPanel2.classList.toggle("mobile-history-filters-open", !!_historyMobileAdvancedOpen);
    historyPanel2.classList.toggle("mobile-history-tools-open", !!_historyMobileAdvancedOpen);
  }
  if (typeof historyTypeFilter2 !== "undefined" && historyTypeFilter2) historyTypeFilter2.value = _historyFilters.type;
  if (typeof historyRootInput2 !== "undefined" && historyRootInput2) historyRootInput2.value = _historyFilters.commandRoot;
  if (typeof historySignalFilter2 !== "undefined" && historySignalFilter2) historySignalFilter2.value = _historyFilters.signal;
  if (typeof historyKindFilter2 !== "undefined" && historyKindFilter2) historyKindFilter2.value = _historyFilters.kind;
  if (typeof historyEntityInput2 !== "undefined" && historyEntityInput2) historyEntityInput2.value = _historyFilters.entity;
  if (typeof historyEntityTypeFilter2 !== "undefined" && historyEntityTypeFilter2) {
    historyEntityTypeFilter2.value = _historyFilters.entityType;
  }
  if (typeof historyExitFilter2 !== "undefined" && historyExitFilter2) historyExitFilter2.value = _historyFilters.exitCode;
  if (typeof historyDateFilter2 !== "undefined" && historyDateFilter2) historyDateFilter2.value = _historyFilters.dateRange;
  if (typeof _syncHistoryProjectFilterOptions === "function") _syncHistoryProjectFilterOptions();
  if (typeof historyStarredToggle2 !== "undefined" && historyStarredToggle2) historyStarredToggle2.checked = !!_historyFilters.starredOnly;
  const runOnlyEnabled = _historyFilters.type !== "snapshots";
  if (typeof historyRootInput2 !== "undefined" && historyRootInput2) historyRootInput2.disabled = !runOnlyEnabled;
  if (typeof historySignalFilter2 !== "undefined" && historySignalFilter2) historySignalFilter2.disabled = !runOnlyEnabled;
  if (typeof historyKindFilter2 !== "undefined" && historyKindFilter2) historyKindFilter2.disabled = !runOnlyEnabled;
  if (typeof historyEntityInput2 !== "undefined" && historyEntityInput2) historyEntityInput2.disabled = !runOnlyEnabled;
  if (typeof historyEntityTypeFilter2 !== "undefined" && historyEntityTypeFilter2) {
    historyEntityTypeFilter2.disabled = !runOnlyEnabled;
  }
  if (typeof historyExitFilter2 !== "undefined" && historyExitFilter2) historyExitFilter2.disabled = !runOnlyEnabled;
  if (typeof historyStarredToggle2 !== "undefined" && historyStarredToggle2) historyStarredToggle2.disabled = !runOnlyEnabled;
  if (typeof _historySyncAppSelectAdapter === "function") {
    if (typeof historyTypeFilter2 !== "undefined") _historySyncAppSelectAdapter(historyTypeFilter2);
    if (typeof historySignalFilter2 !== "undefined") _historySyncAppSelectAdapter(historySignalFilter2);
    if (typeof historyKindFilter2 !== "undefined") _historySyncAppSelectAdapter(historyKindFilter2);
    if (typeof historyEntityTypeFilter2 !== "undefined") _historySyncAppSelectAdapter(historyEntityTypeFilter2);
    if (typeof historyExitFilter2 !== "undefined") _historySyncAppSelectAdapter(historyExitFilter2);
    if (typeof historyDateFilter2 !== "undefined") _historySyncAppSelectAdapter(historyDateFilter2);
    if (typeof historyProjectFilter2 !== "undefined") _historySyncAppSelectAdapter(historyProjectFilter2);
  }
  if (typeof histClearAllBtn2 !== "undefined" && histClearAllBtn2) {
    histClearAllBtn2.classList.toggle("u-hidden", _historyFilters.type === "snapshots");
  }
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
  const currentQuery = typeof historyRootInput2 !== "undefined" && historyRootInput2 ? _normalizeHistoryFilterValue(historyRootInput2.value) : _historyFilters.commandRoot;
  if (currentQuery) {
    const merged = /* @__PURE__ */ new Set([..._historyRootSuggestions, ...nextSuggestions]);
    _historyRootSuggestions = [...merged].sort((a, b) => a.localeCompare(b));
  } else {
    _historyRootSuggestions = nextSuggestions;
  }
  _historyRefreshRootDropdown();
}
function _historyProjectLabel(projectId) {
  const normalized = _normalizeHistoryFilterValue(projectId);
  if (!normalized || normalized === "all") return "";
  const project = _historyProjectOptions.find((item) => String(item && item.id || "") === normalized);
  const localLabel = project && String(project.name || project.slug || project.id || "").trim();
  return localLabel || _historyProjectLabelForIdAdapter(normalized) || normalized;
}
function _hideHistoryRootDropdown() {
  if (typeof historyRootDropdown2 === "undefined" || !historyRootDropdown2) return;
  historyRootDropdown2.replaceChildren();
  historyRootDropdown2.classList.add("u-hidden");
  _historyRootFiltered = [];
  _historyRootIndex = -1;
}
function _historyRootMatches(query) {
  return _historyCore().rootMatches(_historyRootSuggestions, query, 12);
}
function _acceptHistoryRootSuggestion(root) {
  _historyRootSuppressInputOnce = true;
  if (typeof historyRootInput2 !== "undefined" && historyRootInput2) historyRootInput2.value = root;
  _hideHistoryRootDropdown();
  _setHistoryFilter("commandRoot", root);
  if (typeof historyRootInput2 !== "undefined" && historyRootInput2) {
    setTimeout(() => _historyFocusElementAdapter(historyRootInput2, { preventScroll: true }), 0);
  }
}
function _renderHistoryRootDropdown(items, query) {
  if (typeof historyRootDropdown2 === "undefined" || !historyRootDropdown2) return;
  historyRootDropdown2.replaceChildren();
  if (!items.length) {
    _hideHistoryRootDropdown();
    return;
  }
  const normalizedQuery = _normalizeHistoryFilterValue(query).toLowerCase();
  if (items.length === 1 && normalizedQuery && items[0].toLowerCase() === normalizedQuery) {
    _hideHistoryRootDropdown();
    return;
  }
  const mobileMode = typeof _historyUseMobileTerminalViewportModeAdapter === "function" && _historyUseMobileTerminalViewportModeAdapter();
  historyRootDropdown2.classList.toggle("ac-mobile", mobileMode);
  items.forEach((root, index) => {
    const item = document.createElement("div");
    item.className = "ac-item dropdown-item dropdown-item-dense" + (index === _historyRootIndex ? " ac-active dropdown-item-active" : "");
    const matchIndex = normalizedQuery ? root.toLowerCase().indexOf(normalizedQuery) : -1;
    if (matchIndex >= 0 && normalizedQuery) {
      item.innerHTML = _historyEscapeHtmlAdapter(root.slice(0, matchIndex)) + '<span class="ac-match">' + _historyEscapeHtmlAdapter(root.slice(matchIndex, matchIndex + normalizedQuery.length)) + "</span>" + _historyEscapeHtmlAdapter(root.slice(matchIndex + normalizedQuery.length));
    } else {
      item.textContent = root;
    }
    item.addEventListener("mousedown", (e) => {
      e.preventDefault();
      e.stopPropagation();
      _acceptHistoryRootSuggestion(root);
    });
    item.addEventListener("touchstart", (e) => {
      e.preventDefault();
      e.stopPropagation();
      _acceptHistoryRootSuggestion(root);
    }, { passive: false });
    historyRootDropdown2.appendChild(item);
  });
  historyRootDropdown2.classList.remove("u-hidden");
}
function _historyRefreshRootDropdown() {
  const query = typeof historyRootInput2 !== "undefined" && historyRootInput2 ? historyRootInput2.value : _historyFilters.commandRoot;
  _historyRootFiltered = _historyRootMatches(query);
  if (_historyRootIndex >= _historyRootFiltered.length) _historyRootIndex = _historyRootFiltered.length - 1;
  _renderHistoryRootDropdown(_historyRootFiltered, query);
}
function _historyActiveFilterItems() {
  const projectLabel = _historyProjectLabel(_historyFilters.projectId);
  return _historyCore().activeFilterItems({
    ..._historyFilters,
    projectLabel
  });
}
function _historySetPage(nextPage, { refresh = true } = {}) {
  const page = Math.max(1, Number(nextPage) || 1);
  if (_historyPaging.page !== page) {
    _historyPaging.page = page;
    _historyClearSelection({ render: false });
  }
  if (refresh) refreshHistoryPanel2();
}
function _historyRenderPagination(visibleCount = 0) {
  if (typeof historyPagination2 === "undefined" || !historyPagination2) return;
  if (typeof historyPaginationSummary2 === "undefined" || !historyPaginationSummary2) return;
  if (typeof historyPaginationControls2 === "undefined" || !historyPaginationControls2) return;
  const { page, pageSize, totalCount, pageCount } = _historyPaging;
  const totalLabel = _historySummaryLabel(totalCount);
  if (totalCount > 0) {
    const start = (page - 1) * pageSize + 1;
    const count = Math.max(0, Number(visibleCount) || 0);
    const end = count > 0 ? Math.min(totalCount, start + count - 1) : start;
    historyPaginationSummary2.textContent = `Showing ${start}-${end} of ${totalCount} ${totalLabel}`;
  } else {
    historyPaginationSummary2.textContent = `Showing 0 of 0 ${_historySummaryLabel(0)}`;
  }
  historyPaginationControls2.replaceChildren();
  const prevPage = page > 1 ? page - 1 : 1;
  const prevBtn = document.createElement("button");
  prevBtn.type = "button";
  prevBtn.className = "btn btn-secondary btn-compact history-pagination-chevron";
  prevBtn.textContent = "‹ Prev";
  prevBtn.disabled = page <= 1;
  prevBtn.setAttribute("aria-label", "Previous page");
  prevBtn.addEventListener("click", () => _historySetPage(prevPage));
  historyPaginationControls2.appendChild(prevBtn);
  const pageLabel = document.createElement("span");
  pageLabel.className = "history-pagination-status";
  pageLabel.textContent = `Page ${pageCount > 0 ? page : 0} of ${pageCount}`;
  pageLabel.setAttribute("aria-live", "polite");
  historyPaginationControls2.appendChild(pageLabel);
  const nextPage = pageCount > page ? page + 1 : page;
  const nextBtn = document.createElement("button");
  nextBtn.type = "button";
  nextBtn.className = "btn btn-secondary btn-compact history-pagination-chevron";
  nextBtn.textContent = "Next ›";
  nextBtn.disabled = page >= pageCount;
  nextBtn.setAttribute("aria-label", "Next page");
  nextBtn.addEventListener("click", () => _historySetPage(nextPage));
  historyPaginationControls2.appendChild(nextBtn);
  historyPagination2.classList.remove("u-hidden");
}
function _renderHistoryActiveFilters() {
  if (typeof historyActiveFilters2 === "undefined" || !historyActiveFilters2) return;
  historyActiveFilters2.replaceChildren();
  const items = _historyActiveFilterItems();
  historyActiveFilters2.classList.toggle("u-hidden", !items.length);
  items.forEach((item) => {
    const chip = document.createElement("div");
    chip.className = "history-active-filter-chip chip chip-removable";
    chip.dataset.filterKey = item.key;
    const label = document.createElement("span");
    label.textContent = item.label;
    chip.appendChild(label);
    const removeBtn = document.createElement("button");
    removeBtn.className = "history-active-filter-remove";
    removeBtn.type = "button";
    removeBtn.setAttribute("aria-label", `Remove ${item.label} filter`);
    removeBtn.textContent = "✕";
    removeBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const resetValue = item.key === "starredOnly" ? false : _historyDefaultFilterValue(item.key);
      _setHistoryFilter(item.key, resetValue);
    });
    chip.appendChild(removeBtn);
    historyActiveFilters2.appendChild(chip);
  });
}
function _historyItemType(item) {
  return String(item?.type || "run");
}
function _historyIsSelectableItem(item) {
  if (!item || !item.id) return false;
  const type = _historyItemType(item);
  if (type === "snapshot") return true;
  if (type !== "run") return false;
  return !!item.finished || item.exit_code != null;
}
function _historyIsSelectableRun(run) {
  return _historyItemType(run) === "run" && _historyIsSelectableItem(run);
}
function _historySelectionKey(item) {
  return `${_historyItemType(item)}:${String(item?.id || "")}`;
}
function _historySelectedRuns() {
  return Array.from(_historySelection.selected.values()).filter((item) => _historyItemType(item) === "run");
}
function _historySelectedSnapshots() {
  return Array.from(_historySelection.selected.values()).filter((item) => _historyItemType(item) === "snapshot");
}
function _historyCssEscape(value) {
  if (typeof CSS !== "undefined" && CSS && typeof CSS.escape === "function") {
    return CSS.escape(String(value));
  }
  return String(value).replace(/["\\]/g, "\\$&");
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
  const checkbox = historyList2?.querySelector?.(`[data-history-select-item-id="${_historyCssEscape(itemKey)}"]`);
  if (checkbox) checkbox.checked = _historySelection.selected.has(itemKey);
}
function _historyToggleRunSelection(run, checked = null) {
  _historyToggleItemSelection(run, checked);
}
function _historySelectAllVisibleItems() {
  if (_historySelection.bulkInFlight) return;
  const visibleSelectable = _historySelection.visibleItems.filter(_historyIsSelectableItem);
  const allSelected = visibleSelectable.length > 0 && visibleSelectable.every((item) => _historySelection.selected.has(_historySelectionKey(item)));
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
  if (historyList2) {
    historyList2.querySelectorAll("[data-action], .history-entry-select-row input").forEach((el) => {
      if ("disabled" in el) el.disabled = !!busy;
    });
  }
}
function _historyBulkCountsFromResponse(data) {
  return data && typeof data === "object" && data.counts && typeof data.counts === "object" ? data.counts : {};
}
function _historyBulkToast(message, counts = {}) {
  const hasPartial = Number(counts.rejected || 0) > 0 || Number(counts.not_found || 0) > 0 || Number(counts.not_linked || 0) > 0;
  if (hasPartial) _historyShowToastAdapter(message, "success", { label: "dismiss", onClick: () => {
  } });
  else _historyShowToastAdapter(message);
}
function _historyBulkReasonSummary(results = []) {
  if (!Array.isArray(results)) return "";
  const rejected = results.filter((item) => item && item.status === "rejected");
  if (!rejected.length) return "";
  const reasons = rejected.reduce((acc, item) => {
    const reason = String(item.reason || "").trim();
    acc.set(reason, (acc.get(reason) || 0) + 1);
    return acc;
  }, /* @__PURE__ */ new Map());
  const labels = {
    running: "still running",
    not_owned: "not available in this session",
    policy_blocked: "blocked by policy",
    builtin: "built-in command"
  };
  return Array.from(reasons.entries()).map(([reason, count]) => {
    const label = labels[reason] || "skipped";
    return `${count} ${label}`;
  }).join(" - ");
}
function _historyBulkResultText(action, projectName, counts = {}) {
  if (action === "add") {
    const added = Number(counts.added || 0);
    const already = Number(counts.already_linked || 0);
    const rejected2 = Number(counts.rejected || 0) + Number(counts.not_found || 0);
    const pieces2 = [`Added ${added} ${added === 1 ? "run" : "runs"} to ${projectName}`];
    if (already) pieces2.push(`${already} already linked`);
    if (rejected2) pieces2.push(`${rejected2} skipped`);
    return pieces2.join(" - ");
  }
  if (action === "remove") {
    const removed = Number(counts.removed || 0);
    const notLinked = Number(counts.not_linked || 0);
    const rejected2 = Number(counts.rejected || 0) + Number(counts.not_found || 0);
    const pieces2 = [`Removed ${removed} ${removed === 1 ? "run" : "runs"} from ${projectName}`];
    if (notLinked) pieces2.push(`${notLinked} not linked`);
    if (rejected2) pieces2.push(`${rejected2} skipped`);
    return pieces2.join(" - ");
  }
  const deleted = Number(counts.deleted || 0);
  const rejected = Number(counts.rejected || 0) + Number(counts.not_found || 0);
  const pieces = [`Deleted ${deleted} ${deleted === 1 ? "run" : "runs"}`];
  if (rejected) pieces.push(`${rejected} skipped`);
  return pieces.join(" - ");
}
function _historySelectedRunIds() {
  return _historySelectedRuns().map((run) => String(run.id || "")).filter(Boolean);
}
function _historySelectedSnapshotIds() {
  return _historySelectedSnapshots().map((snapshot) => String(snapshot.id || "")).filter(Boolean);
}
async function _historyRefreshAfterBulk() {
  try {
    await refreshHistoryPanel2();
  } catch (_) {
    _historyShowToastAdapter("Bulk action finished, but history could not refresh. Refresh to see the latest state.", "error");
  }
}
function _closeHistoryBulkActionMenu() {
  const toolbar = typeof historyBulkToolbar2 !== "undefined" ? historyBulkToolbar2 : null;
  const wrap = toolbar?.querySelector?.(".history-bulk-actions-wrap.open");
  if (!wrap) return;
  wrap.classList.remove("open");
  wrap.querySelector('[data-action="history-bulk-menu"]')?.setAttribute("aria-expanded", "false");
}
function _historyProjectsForSelectedLinks() {
  const projectsById = /* @__PURE__ */ new Map();
  _historySelectedRuns().forEach((run) => {
    const runId = String(run && run.id || "");
    if (!runId) return;
    const links = Array.isArray(run.project_links) ? run.project_links : [];
    links.forEach((link) => {
      const project = typeof _historyProjectFromLinkAdapter === "function" ? _historyProjectFromLinkAdapter(link) : null;
      if (!project || !project.id) return;
      const projectId = String(project.id);
      if (!projectsById.has(projectId)) projectsById.set(projectId, { project, runIds: /* @__PURE__ */ new Set() });
      projectsById.get(projectId).runIds.add(runId);
    });
  });
  return Array.from(projectsById.values()).map((item) => ({ project: item.project, runIds: Array.from(item.runIds) })).filter((item) => item.project && item.project.id && item.runIds.length);
}
function _historyMergeBulkProjectResponses(responses) {
  return responses.reduce((acc, data) => {
    const counts = _historyBulkCountsFromResponse(data);
    ["added", "already_linked", "removed", "not_linked", "not_found", "rejected"].forEach((key) => {
      acc.counts[key] = Number(acc.counts[key] || 0) + Number(counts[key] || 0);
    });
    if (Array.isArray(data?.results)) acc.results.push(...data.results);
    return acc;
  }, {
    counts: { added: 0, already_linked: 0, removed: 0, not_linked: 0, not_found: 0, rejected: 0 },
    results: []
  });
}
async function _historyBulkPostProject(project, action, options = {}) {
  const runIds = _historySelectedRunIds();
  if (!project || !project.id || !runIds.length) return;
  _historySetBulkBusy(true);
  try {
    const resp = await _historyApiFetchAdapter(`/projects/${encodeURIComponent(project.id)}/links`, {
      method: action === "remove" ? "DELETE" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        entity_type: "run",
        entity_ids: runIds,
        source: "manual",
        ...options.includeEntities ? { include_entities: true } : {}
      })
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    const counts = _historyBulkCountsFromResponse(data);
    const projectName = _historyProjectDisplayNameAdapter(project) || "project";
    _historySelection.selected.clear();
    const reasonSummary = _historyBulkReasonSummary(data.results);
    const entityAdded = Number(data && data.linked_entities && data.linked_entities.added || 0);
    const entitySummary = action === "add" && entityAdded ? `${entityAdded.toLocaleString()} ${entityAdded === 1 ? "entity" : "entities"} added` : "";
    const message = [_historyBulkResultText(action, projectName, counts), entitySummary, reasonSummary].filter(Boolean).join(" - ");
    _historyBulkToast(message, counts);
    if (typeof _historyRefreshProjectWorkspaceAdapter === "function") {
      try {
        await _historyRefreshProjectWorkspaceAdapter();
      } catch (_) {
      }
    }
    await _historyRefreshAfterBulk();
  } catch (_) {
    _historyShowToastAdapter(action === "remove" ? "Failed to remove selected runs from project" : "Failed to add selected runs to project", "error");
  } finally {
    _historySetBulkBusy(false);
  }
}
async function _historyBulkRemoveFromAllProjects() {
  const projectGroups = _historyProjectsForSelectedLinks();
  if (!projectGroups.length) {
    _historyShowToastAdapter("Selected runs are not linked to any project", "error");
    return;
  }
  const selectedCount = _historySelectedRunIds().length;
  const linkCount = projectGroups.reduce((total, item) => total + item.runIds.length, 0);
  const choice = await _historyShowConfirmAdapter({
    body: {
      text: `Remove ${selectedCount} selected ${selectedCount === 1 ? "run" : "runs"} from all linked projects?`,
      note: `This removes ${linkCount} project ${linkCount === 1 ? "link" : "links"} and leaves the run history intact.`
    },
    tone: "warning",
    actions: [
      { id: "cancel", label: "Cancel", role: "cancel" },
      { id: "remove", label: "Remove from projects", role: "destructive", tone: "warning" }
    ],
    refocusOnResolve: false
  });
  if (choice !== "remove") return;
  _historySetBulkBusy(true);
  try {
    const responses = await Promise.all(projectGroups.map(async ({ project, runIds }) => {
      const resp = await _historyApiFetchAdapter(`/projects/${encodeURIComponent(project.id)}/links`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entity_type: "run", entity_ids: runIds, source: "manual" })
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
    const pieces = [`Removed ${removed} project ${removed === 1 ? "link" : "links"}`];
    if (notLinked) pieces.push(`${notLinked} not linked`);
    if (rejected) pieces.push(`${rejected} skipped`);
    const message = [pieces.join(" - "), reasonSummary].filter(Boolean).join(" - ");
    _historyBulkToast(message, counts);
    if (typeof _historyRefreshProjectWorkspaceAdapter === "function") {
      try {
        await _historyRefreshProjectWorkspaceAdapter();
      } catch (_) {
      }
    }
    await _historyRefreshAfterBulk();
  } catch (_) {
    _historyShowToastAdapter("Failed to remove selected runs from projects", "error");
  } finally {
    _historySetBulkBusy(false);
  }
}
async function _historyBulkAddToActiveProject() {
  const project = await _historyLoadActiveProjectAdapter();
  if (!project || !project.id) {
    _historyShowToastAdapter("No active project selected", "error");
    return;
  }
  const runIds = _historySelectedRunIds();
  const entityOption = _historyProjectRunEntityOptionContentAdapter();
  await _historyRefreshProjectRunEntityOptionAdapter(entityOption, project, runIds);
  const choice = await _historyShowConfirmAdapter({
    body: `Add ${runIds.length} selected ${runIds.length === 1 ? "run" : "runs"} to ${_historyProjectDisplayNameAdapter(project) || "the active project"}?`,
    content: entityOption.wrap.classList.contains("u-hidden") ? null : entityOption.wrap,
    tone: null,
    actions: [
      { id: "cancel", label: "Cancel", role: "cancel" },
      { id: "add", label: "Add to project", role: "primary" }
    ],
    refocusOnResolve: false
  });
  if (choice !== "add") return;
  await _historyBulkPostProject(project, "add", {
    includeEntities: !!entityOption.checkbox.checked && !entityOption.checkbox.disabled
  });
}
async function _historyBulkChooseProject(action) {
  const selectedCount = _historySelection.selected.size;
  let projects;
  try {
    const [loadedProjects, activeProject] = await Promise.all([
      _historyLoadProjectsAdapter(),
      _historyLoadActiveProjectAdapter().catch(() => null)
    ]);
    projects = _historyOrderProjectsForPickerAdapter(loadedProjects, activeProject);
  } catch (_) {
    _historyShowToastAdapter("Failed to load projects", "error");
    return;
  }
  if (!projects.length) {
    _historyShowToastAdapter("No projects available", "error");
    return;
  }
  const { wrap, select } = _historyProjectPickerContentAdapter(projects);
  const entityOption = _historyProjectRunEntityOptionContentAdapter();
  wrap.appendChild(entityOption.wrap);
  const runIds = _historySelectedRunIds();
  const updateEntityOption = () => {
    const selectedProject = projects.find((item) => String(item.id || "") === select.value);
    _historyRefreshProjectRunEntityOptionAdapter(entityOption, selectedProject, runIds);
  };
  select.addEventListener("change", updateEntityOption);
  updateEntityOption();
  const help = wrap.querySelector(".history-project-picker-help");
  if (help) {
    help.textContent = "Choose a project to link selected runs.";
  }
  const choicePromise = _historyShowConfirmAdapter({
    body: `Add ${selectedCount} selected ${selectedCount === 1 ? "run" : "runs"} to project`,
    content: wrap,
    tone: null,
    defaultFocus: select,
    actions: [
      { id: "cancel", label: "Cancel", role: "cancel" },
      { id: action, label: "Add to project", role: "primary" }
    ],
    refocusOnResolve: false
  });
  if (typeof _historyEnhanceAppSelectsAdapter === "function") {
    _historyEnhanceAppSelectsAdapter(wrap);
    if (typeof _historyUseMobileTerminalViewportModeAdapter === "function" && _historyUseMobileTerminalViewportModeAdapter()) {
      wrap.querySelector(".app-select-menu")?.classList.add("dropdown-up");
    }
  }
  const choice = await choicePromise;
  if (choice !== action) return;
  const project = projects.find((item) => String(item.id || "") === select.value);
  await _historyBulkPostProject(project, action, {
    includeEntities: !!entityOption.checkbox.checked && !entityOption.checkbox.disabled
  });
}
function _historyBulkDeleteLabel(runCount, snapshotCount) {
  if (runCount && snapshotCount) return `${runCount + snapshotCount} selected history items`;
  if (snapshotCount) return `${snapshotCount} selected ${snapshotCount === 1 ? "snapshot" : "snapshots"}`;
  return `${runCount} selected ${runCount === 1 ? "run" : "runs"}`;
}
function _historyBulkDeletedNoun(runCount, snapshotCount, deletedCount) {
  if (runCount && !snapshotCount) return deletedCount === 1 ? "run" : "runs";
  if (snapshotCount && !runCount) return deletedCount === 1 ? "snapshot" : "snapshots";
  return deletedCount === 1 ? "item" : "items";
}
function _historyMergeBulkDeleteResponses(responses) {
  return responses.reduce((acc, data) => {
    const counts = _historyBulkCountsFromResponse(data);
    ["deleted", "not_found", "rejected"].forEach((key) => {
      acc.counts[key] = Number(acc.counts[key] || 0) + Number(counts[key] || 0);
    });
    if (Array.isArray(data?.results)) acc.results.push(...data.results);
    return acc;
  }, { counts: { deleted: 0, not_found: 0, rejected: 0 }, results: [] });
}
async function _historyPostBulkDelete(url, payload) {
  const resp = await _historyApiFetchAdapter(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!resp.ok) {
    if (typeof _historyMutationErrorAdapter === "function") {
      throw await _historyMutationErrorAdapter(resp, "Failed to delete selected history items");
    }
    throw new Error(`HTTP ${resp.status}`);
  }
  return resp.json();
}
function _historyBulkExportFilename(format) {
  const suffix = format === "jsonl" ? "jsonl" : "txt";
  return `darklab-history-${(/* @__PURE__ */ new Date()).toISOString().replace(/[:.]/g, "-")}.${suffix}`;
}
function _historyFilenameFromDisposition(value) {
  const match = /filename\*?=(?:UTF-8''|")?([^";]+)/i.exec(String(value || ""));
  if (!match) return "";
  try {
    return decodeURIComponent(match[1].replace(/"$/u, ""));
  } catch (_) {
    return match[1].replace(/"$/u, "");
  }
}
async function _historyBulkExportSelectedItems(format) {
  const runIds = _historySelectedRunIds();
  const snapshotIds = _historySelectedSnapshotIds();
  if (!runIds.length && !snapshotIds.length) return;
  const downloader = _historyDownloadBlobAsAttachmentAdapter;
  if (typeof downloader !== "function") {
    _historyShowToastAdapter("Downloads are not available", "error");
    return;
  }
  const exportFormat = format === "jsonl" ? "jsonl" : "txt";
  _historySetBulkBusy(true);
  try {
    const resp = await _historyApiFetchAdapter("/history/bulk-export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        run_ids: runIds,
        snapshot_ids: snapshotIds,
        format: exportFormat
      })
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const blob = await resp.blob();
    const filename = _historyFilenameFromDisposition(resp.headers?.get?.("content-disposition")) || _historyBulkExportFilename(exportFormat);
    downloader(blob, filename, { container: historyPanel2 });
    _historyShowToastAdapter(`History ${exportFormat.toUpperCase()} export started`);
  } catch (_) {
    _historyShowToastAdapter("Failed to export selected history items", "error");
  } finally {
    _historySetBulkBusy(false);
  }
}
async function _historyBulkDeleteSelectedItems() {
  const runIds = _historySelectedRunIds();
  const snapshotIds = _historySelectedSnapshotIds();
  if (!runIds.length && !snapshotIds.length) return;
  if (typeof _historyCanManageHistoryAdapter === "function" && !_historyCanManageHistoryAdapter()) {
    if (typeof _historyShowPermissionDeniedAdapter === "function") _historyShowPermissionDeniedAdapter("delete team history");
    return;
  }
  const label = _historyBulkDeleteLabel(runIds.length, snapshotIds.length);
  const choice = await _historyShowConfirmAdapter({
    body: {
      text: `Delete ${label}?`,
      note: runIds.length && snapshotIds.length ? "This removes the selected run history and snapshots and cannot be undone." : snapshotIds.length ? "This removes the selected snapshots and cannot be undone." : "This removes the selected run history and cannot be undone."
    },
    tone: "warning",
    actions: [
      { id: "cancel", label: "Cancel", role: "cancel" },
      { id: "delete", label: "Delete", role: "destructive", tone: "warning" }
    ],
    refocusOnResolve: false
  });
  if (choice !== "delete") return;
  _historySetBulkBusy(true);
  try {
    const requests = [];
    if (runIds.length) requests.push(_historyPostBulkDelete("/history/bulk-delete", { run_ids: runIds }));
    if (snapshotIds.length) requests.push(_historyPostBulkDelete("/share/bulk-delete", { snapshot_ids: snapshotIds }));
    const data = _historyMergeBulkDeleteResponses(await Promise.all(requests));
    const counts = _historyBulkCountsFromResponse(data);
    _historySelection.selected.clear();
    const reasonSummary = _historyBulkReasonSummary(data.results);
    const deleted = Number(counts.deleted || 0);
    const rejected = Number(counts.rejected || 0) + Number(counts.not_found || 0);
    const pieces = [`Deleted ${deleted} ${_historyBulkDeletedNoun(runIds.length, snapshotIds.length, deleted)}`];
    if (rejected) pieces.push(`${rejected} skipped`);
    const message = [pieces.join(" - "), reasonSummary].filter(Boolean).join(" - ");
    _historyBulkToast(message, counts);
    await _historyRefreshAfterBulk();
  } catch (err) {
    _historyShowToastAdapter(err.userFacing ? err.message : "Failed to delete selected history items", "error");
  } finally {
    _historySetBulkBusy(false);
  }
}
function _historyBuildBulkActionMenu(disabled) {
  const wrap = document.createElement("div");
  wrap.className = "history-bulk-actions-wrap save-menu-wrap save-menu-down";
  const trigger = document.createElement("button");
  trigger.className = "history-action-btn btn btn-secondary btn-compact";
  trigger.type = "button";
  trigger.dataset.action = "history-bulk-menu";
  trigger.textContent = "Actions";
  trigger.setAttribute("aria-expanded", "false");
  trigger.disabled = disabled;
  const menu = document.createElement("div");
  menu.className = "history-bulk-actions-menu save-menu dropdown-surface";
  const activeProject = typeof _historyGetActiveProjectContextAdapter === "function" ? _historyGetActiveProjectContextAdapter() : null;
  const selectedTypes = new Set(Array.from(_historySelection.selected.values()).map(_historyItemType));
  const hasOnlyRuns = selectedTypes.size === 1 && selectedTypes.has("run");
  const selectedRuns = _historySelectedRuns();
  const hasOnlyProjectLinkableRuns = hasOnlyRuns && selectedRuns.every((run) => String(run?.run_kind || "external") !== "builtin");
  [
    ["bulk-add-active-project", "add to active project"],
    ["bulk-add-project", "add to project"],
    ["bulk-remove-project", "remove from project"],
    ["bulk-export-txt", "export text"],
    ["bulk-export-jsonl", "export JSONL"],
    ["bulk-delete", "delete"]
  ].forEach(([action, label]) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "dropdown-item dropdown-item-compact";
    item.dataset.action = action;
    item.textContent = label;
    const projectActionDisabled = !["bulk-delete", "bulk-export-txt", "bulk-export-jsonl"].includes(action) && !hasOnlyProjectLinkableRuns;
    const historyDeleteDisabled = action === "bulk-delete" && typeof _historyCanManageHistoryAdapter === "function" && !_historyCanManageHistoryAdapter();
    item.disabled = disabled || projectActionDisabled || historyDeleteDisabled || action === "bulk-add-active-project" && !(activeProject && activeProject.id);
    if (action === "bulk-add-active-project" && !(activeProject && activeProject.id)) {
      item.title = "Select an active project first.";
    } else if (historyDeleteDisabled) {
      item.title = typeof _historyScopeDeniedMessageAdapter === "function" ? _historyScopeDeniedMessageAdapter("delete team history") : "View-only team members cannot delete team history.";
    } else if (projectActionDisabled) {
      item.title = "Project actions apply to selected external runs.";
    }
    menu.appendChild(item);
  });
  wrap.append(trigger, menu);
  return wrap;
}
function _renderHistoryBulkToolbar() {
  if (typeof historyBulkToolbar2 === "undefined" || !historyBulkToolbar2) return;
  historyBulkToolbar2.replaceChildren();
  const visibleSelectable = _historySelection.visibleItems.filter(_historyIsSelectableItem);
  const shouldShow = _historySelection.selectMode || visibleSelectable.length > 0;
  historyBulkToolbar2.classList.toggle("u-hidden", !shouldShow);
  _syncHistoryFilterControls();
  if (!shouldShow) return;
  const selectRow = document.createElement("div");
  selectRow.className = "history-bulk-select-row";
  const toggleLabel = document.createElement("label");
  toggleLabel.className = "history-bulk-toggle control-row";
  const toggle = document.createElement("input");
  toggle.type = "checkbox";
  toggle.checked = !!_historySelection.selectMode;
  toggle.disabled = _historySelection.bulkInFlight;
  const toggleText = document.createElement("span");
  toggleText.textContent = "select";
  toggleLabel.append(toggle, toggleText);
  toggle.addEventListener("change", () => _historySetSelectMode(toggle.checked));
  selectRow.appendChild(toggleLabel);
  historyBulkToolbar2.appendChild(selectRow);
  const count = document.createElement("span");
  count.className = "history-bulk-count";
  const selectedCount = _historySelection.selected.size;
  count.textContent = `${selectedCount} selected`;
  count.setAttribute("aria-live", "polite");
  selectRow.appendChild(count);
  const actionRow = document.createElement("div");
  actionRow.className = "history-bulk-action-row";
  const allSelected = visibleSelectable.length > 0 && visibleSelectable.every((item) => _historySelection.selected.has(_historySelectionKey(item)));
  const someSelected = visibleSelectable.some((item) => _historySelection.selected.has(_historySelectionKey(item)));
  const selectAll = document.createElement("button");
  selectAll.className = "history-action-btn btn btn-secondary btn-compact";
  selectAll.type = "button";
  selectAll.textContent = allSelected && someSelected ? "Deselect all" : "Select all";
  selectAll.disabled = !_historySelection.selectMode || !visibleSelectable.length || _historySelection.bulkInFlight;
  selectAll.setAttribute("aria-pressed", allSelected && someSelected ? "true" : someSelected ? "mixed" : "false");
  selectAll.addEventListener("click", (event) => {
    event.stopPropagation();
    _historySelectAllVisibleItems();
  });
  actionRow.appendChild(selectAll);
  const clear = document.createElement("button");
  clear.className = "history-action-btn btn btn-secondary btn-compact";
  clear.type = "button";
  clear.textContent = "Clear";
  clear.disabled = selectedCount === 0 || _historySelection.bulkInFlight;
  clear.addEventListener("click", (event) => {
    event.stopPropagation();
    _historyClearSelection({ render: false });
    _historyRenderCurrentPanel();
  });
  actionRow.appendChild(clear);
  const actions = _historyBuildBulkActionMenu(selectedCount === 0 || _historySelection.bulkInFlight);
  actionRow.appendChild(actions);
  historyBulkToolbar2.appendChild(actionRow);
  _historyBindPressableAdapter(actions.querySelector('[data-action="history-bulk-menu"]'), {
    refocusComposer: false,
    onActivate: (event) => {
      event.preventDefault();
      event.stopPropagation();
      const open = !actions.classList.contains("open");
      actions.classList.toggle("open", open);
      actions.querySelector('[data-action="history-bulk-menu"]')?.setAttribute("aria-expanded", open ? "true" : "false");
    }
  });
  _historyBindPressableAdapter(actions.querySelector('[data-action="bulk-add-active-project"]'), {
    refocusComposer: false,
    onActivate: (event) => {
      event.preventDefault();
      event.stopPropagation();
      _closeHistoryBulkActionMenu();
      _historyBulkAddToActiveProject();
    }
  });
  _historyBindPressableAdapter(actions.querySelector('[data-action="bulk-add-project"]'), {
    refocusComposer: false,
    onActivate: (event) => {
      event.preventDefault();
      event.stopPropagation();
      _closeHistoryBulkActionMenu();
      _historyBulkChooseProject("add");
    }
  });
  _historyBindPressableAdapter(actions.querySelector('[data-action="bulk-remove-project"]'), {
    refocusComposer: false,
    onActivate: (event) => {
      event.preventDefault();
      event.stopPropagation();
      _closeHistoryBulkActionMenu();
      _historyBulkRemoveFromAllProjects();
    }
  });
  _historyBindPressableAdapter(actions.querySelector('[data-action="bulk-export-txt"]'), {
    refocusComposer: false,
    onActivate: (event) => {
      event.preventDefault();
      event.stopPropagation();
      _closeHistoryBulkActionMenu();
      _historyBulkExportSelectedItems("txt");
    }
  });
  _historyBindPressableAdapter(actions.querySelector('[data-action="bulk-export-jsonl"]'), {
    refocusComposer: false,
    onActivate: (event) => {
      event.preventDefault();
      event.stopPropagation();
      _closeHistoryBulkActionMenu();
      _historyBulkExportSelectedItems("jsonl");
    }
  });
  _historyBindPressableAdapter(actions.querySelector('[data-action="bulk-delete"]'), {
    refocusComposer: false,
    onActivate: (event) => {
      event.preventDefault();
      event.stopPropagation();
      _closeHistoryBulkActionMenu();
      _historyBulkDeleteSelectedItems();
    }
  });
}
function _buildHistoryRequestUrl() {
  return _historyCore().buildRequestUrl(_historyFilters, _historyPaging);
}
function _applyHistoryClientFilters(runs) {
  return Array.isArray(runs) ? runs.slice() : [];
}
function _renderHistoryEmptyState() {
  if (typeof historyList2 === "undefined" || !historyList2) return;
  const empty = document.createElement("div");
  empty.className = "history-empty-state";
  const title = document.createElement("div");
  title.className = "history-empty-state-title";
  const typeLabel = _historyLabelForType();
  title.textContent = _historyHasAnyFilters() ? `No matching ${typeLabel}.` : _historyFilters.type === "snapshots" ? "No snapshots yet." : _historyFilters.type === "runs" ? "No runs yet." : "No history yet.";
  empty.appendChild(title);
  const detail = document.createElement("div");
  detail.className = "history-empty-state-detail";
  detail.textContent = _historyHasAnyFilters() ? "Adjust or clear the current filters to widen the history results." : _historyFilters.type === "snapshots" ? "Saved snapshots will appear here for this browser session." : _historyFilters.type === "runs" ? "Completed commands will appear here for this browser session." : "Completed commands and saved snapshots will appear here for this browser session.";
  empty.appendChild(detail);
  historyList2.appendChild(empty);
  if (typeof historyPagination2 !== "undefined" && historyPagination2) {
    historyPagination2.classList.remove("u-hidden");
  }
}
function _scheduleHistoryPanelRefresh() {
  if (_historyFilterRefreshTimer) clearTimeout(_historyFilterRefreshTimer);
  _historyFilterRefreshTimer = setTimeout(() => {
    _historyFilterRefreshTimer = null;
    refreshHistoryPanel2();
  }, 120);
}
function _setHistoryFilter(key, value, { debounce = false } = {}) {
  if (key === "starredOnly") _historyFilters.starredOnly = !!value;
  else _historyFilters[key] = _normalizeHistoryFilterValue(value) || _historyDefaultFilterValue(key);
  if (key === "type" && _historyFilters.type === "snapshots") _historyResetRunOnlyFilters();
  if (_historyStructuredFilterKeys.has(key) && _historyRunOnlyFilterIsActive(key) && _historyFilters.type === "all") {
    _historyFilters.type = "runs";
  }
  _historyPaging.page = 1;
  _historyClearSelection({ render: false });
  if (debounce) _scheduleHistoryPanelRefresh();
  else refreshHistoryPanel2();
}
function openHistoryWithFilters(filters = {}) {
  const selection = window.getSelection?.();
  if (selection && typeof selection.removeAllRanges === "function") {
    selection.removeAllRanges();
  }
  const nextFilters = {
    ..._historyFilters,
    ...filters
  };
  if (Object.prototype.hasOwnProperty.call(filters, "commandRoot")) {
    nextFilters.commandRoot = _normalizeHistoryFilterValue(filters.commandRoot);
  }
  _historyFilters = {
    type: _normalizeHistoryFilterValue(nextFilters.type) || "all",
    q: _normalizeHistoryFilterValue(nextFilters.q),
    commandRoot: _normalizeHistoryFilterValue(nextFilters.commandRoot),
    signal: _normalizeHistoryFilterValue(nextFilters.signal) || "all",
    kind: _normalizeHistoryFilterValue(nextFilters.kind) || "all",
    entity: _normalizeHistoryFilterValue(nextFilters.entity),
    entityType: _normalizeHistoryFilterValue(nextFilters.entityType) || "all",
    exitCode: _normalizeHistoryFilterValue(nextFilters.exitCode) || "all",
    dateRange: _normalizeHistoryFilterValue(nextFilters.dateRange) || "all",
    projectId: _normalizeHistoryFilterValue(nextFilters.projectId) || "all",
    starredOnly: !!nextFilters.starredOnly
  };
  if (_historyFilters.type === "snapshots") _historyResetRunOnlyFilters();
  else if (_historyFilters.type === "all" && _historyHasActiveRunOnlyFilters()) _historyFilters.type = "runs";
  _historyPaging.page = 1;
  _historyClearSelection({ render: false });
  _syncHistoryFilterControls();
  _renderHistoryActiveFilters();
  _hideHistoryRootDropdown();
  if (typeof _historyTogglePanelSurfaceAdapter === "function") {
    _historyTogglePanelSurfaceAdapter(true);
  } else {
    if (typeof _historyShowPanelAdapter === "function") _historyShowPanelAdapter();
    refreshHistoryPanel2();
  }
  return true;
}
function clearHistoryFilters() {
  _historyFilters = {
    type: "all",
    q: "",
    commandRoot: "",
    signal: "all",
    kind: "all",
    entity: "",
    entityType: "all",
    exitCode: "all",
    dateRange: "all",
    projectId: "all",
    starredOnly: false
  };
  _historyPaging.page = 1;
  _historyClearSelection({ render: false });
  _syncHistoryFilterControls();
  _renderHistoryActiveFilters();
  _hideHistoryRootDropdown();
  refreshHistoryPanel2();
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
  const chip = document.createElement("button");
  chip.className = "hist-chip hist-chip-overflow chip chip-action";
  chip.textContent = "+ more";
  chip.title = "Open history panel";
  chip.addEventListener("click", () => {
    if (!historyPanel2) return;
    if (typeof resetHistoryMobileFilters === "function") resetHistoryMobileFilters();
    _historyShowPanelAdapter();
    if (typeof refreshHistoryPanel2 === "function") refreshHistoryPanel2();
  });
  return chip;
}
function _applyDesktopChipOverflow() {
  const chips = Array.from(histRow2.querySelectorAll(".hist-chip:not(.hist-chip-overflow)"));
  if (!chips.length) return;
  const firstTop = chips[0].getBoundingClientRect().top;
  let overflowIdx = chips.length;
  for (let i = 1; i < chips.length; i++) {
    if (chips[i].getBoundingClientRect().top > firstTop + 2) {
      overflowIdx = i;
      break;
    }
  }
  if (overflowIdx === chips.length) return;
  for (let i = chips.length - 1; i >= overflowIdx; i--) {
    histRow2.removeChild(chips[i]);
  }
  const overflowChip = _makeOverflowChip();
  histRow2.appendChild(overflowChip);
  while (overflowChip.getBoundingClientRect().top > firstTop + 2) {
    const regularChips = Array.from(histRow2.querySelectorAll(".hist-chip:not(.hist-chip-overflow)"));
    const lastRegularChip = regularChips[regularChips.length - 1];
    if (!lastRegularChip) break;
    histRow2.removeChild(lastRegularChip);
  }
}
function _emitHistoryRendered() {
  if (typeof _historyEmitUiEventAdapter === "function") {
    _historyEmitUiEventAdapter("app:history-rendered", {
      cmdHistory: _historyCmdHistory().slice(),
      recentPreviewHistory: _historyRecentPreviewHistory().slice()
    });
  }
}
function renderHistory() {
  while (histRow2.children.length > 1) histRow2.removeChild(histRow2.lastChild);
  const commands = _historyCmdHistory();
  if (!commands.length) {
    _historyHideRowAdapter();
    _emitHistoryRendered();
    return;
  }
  _historyShowRowAdapter();
  const starred = _historyGetStarredAdapter();
  const sorted = [
    ...commands.filter((c) => starred.has(c)),
    ...commands.filter((c) => !starred.has(c))
  ];
  const isMobile = typeof _historyUseMobileTerminalViewportModeAdapter === "function" && _historyUseMobileTerminalViewportModeAdapter();
  const visible = isMobile ? sorted.slice(0, 3) : sorted;
  visible.forEach((cmd) => {
    const isStarred = starred.has(cmd);
    const chip = document.createElement("button");
    chip.className = "hist-chip chip chip-action" + (isStarred ? " starred" : "");
    chip.title = cmd;
    const textEl = document.createElement("span");
    textEl.textContent = cmd;
    if (!isMobile) {
      const starEl = document.createElement("span");
      starEl.className = "chip-star";
      starEl.textContent = isStarred ? "★" : "☆";
      starEl.title = isStarred ? "Unstar" : "Star";
      starEl.addEventListener("click", (e) => {
        e.stopPropagation();
        _historyToggleStarAdapter(cmd);
        renderHistory();
      });
      chip.appendChild(starEl);
    }
    chip.appendChild(textEl);
    chip.addEventListener("click", () => {
      _historyBlurActiveElementAdapter();
      _historySetComposerValueAdapter(cmd, cmd.length, cmd.length);
      if (_historyRefocusComposerAdapter({ preventScroll: true })) return;
      _historyResetCmdNavAdapter();
    });
    histRow2.appendChild(chip);
  });
  if (isMobile && visible.length < sorted.length) {
    histRow2.appendChild(_makeOverflowChip());
  } else if (!isMobile) {
    _applyDesktopChipOverflow();
  }
  _emitHistoryRendered();
}
if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
  window.addEventListener("resize", () => {
    if (typeof _historyUseMobileTerminalViewportModeAdapter === "function" && !_historyUseMobileTerminalViewportModeAdapter()) {
      renderHistory();
    }
  });
}
function _historyRenderPanelData(data) {
  historyList2.replaceChildren();
  _historyPaging.page = Math.max(1, Number(data.page) || _historyPaging.page || 1);
  _historyPaging.pageSize = Math.max(1, Number(data.page_size) || _historyPaging.pageSize || 1);
  _historyPaging.totalCount = Math.max(0, Number(data.total_count ?? data.items?.length ?? data.runs?.length ?? 0) || 0);
  _historyPaging.pageCount = Math.max(0, Number(data.page_count) || 0);
  _historyPaging.hasPrev = !!data.has_prev;
  _historyPaging.hasNext = !!data.has_next;
  const visibleItems = _applyHistoryClientFilters(Array.isArray(data.items) ? data.items : data.runs);
  _historySelection.visibleItems = visibleItems.filter(_historyIsSelectableItem);
  _renderHistoryBulkToolbar();
  _renderHistoryRootSuggestions(_historyFilters.type === "snapshots" ? [] : Array.isArray(data.roots) ? data.roots : data.runs);
  if (!visibleItems.length) {
    _historyRenderPagination(0);
    _renderHistoryEmptyState();
    if (typeof _historyEmitUiEventAdapter === "function") {
      _historyEmitUiEventAdapter("app:history-panel-refreshed", {
        items: [],
        runs: [],
        roots: Array.isArray(data.roots) ? data.roots.slice() : [],
        paging: { ..._historyPaging },
        filters: { ..._historyFilters }
      });
    }
    return;
  }
  const starred = _historyGetStarredAdapter();
  visibleItems.forEach((item) => {
    if (item.type === "snapshot") {
      const selectable2 = _historyIsSelectableItem(item);
      const selected2 = _historySelection.selected.has(_historySelectionKey(item));
      const entry2 = _historyCreateSnapshotEntryAdapter(item, {
        selectMode: _historySelection.selectMode,
        selectable: selectable2,
        selected: selected2,
        selectionBusy: _historySelection.bulkInFlight
      });
      entry2.addEventListener("click", (e) => {
        if (e.target.closest("[data-action]")) return;
        const renderedForSelection = entry2.classList.contains("history-entry-selecting") || !!entry2.querySelector('[data-action="select-run"]');
        if (_historySelection.selectMode || renderedForSelection) {
          e.preventDefault();
          e.stopPropagation();
          _historyToggleItemSelection(item);
          return;
        }
        _historyOpenSnapshotLinkAdapter(item);
        _historyHidePanelAdapter();
      });
      const selectionBox2 = entry2.querySelector('[data-action="select-run"]');
      if (selectionBox2) {
        selectionBox2.addEventListener("change", (e) => {
          e.stopPropagation();
          _historyToggleItemSelection(item, e.target.checked);
        });
      }
      _historyBindPressableAdapter(entry2.querySelector('[data-action="open"]'), {
        onActivate: () => {
          _historyOpenSnapshotLinkAdapter(item);
          _historyHidePanelAdapter();
        }
      });
      _historyBindPressableAdapter(entry2.querySelector('[data-action="link"]'), {
        onActivate: () => {
          _historyCopySnapshotLinkAdapter(item).catch(() => _historyShowToastAdapter("Failed to copy link", "error"));
          if (!_historyActionKeepsPanelOpenAdapter("permalink")) _historyHidePanelAdapter();
        }
      });
      _historyBindPressableAdapter(entry2.querySelector('[data-action="edit-metadata"]'), {
        refocusComposer: false,
        onActivate: () => {
          _historyEditEntityMetadataAdapter("snapshot", item);
        }
      });
      _historyBindPressableAdapter(entry2.querySelector('[data-action="delete"]'), {
        onActivate: () => {
          _historyConfirmActionAdapter("delete", item.id, item.label || "snapshot", "snapshot");
        }
      });
      historyList2.appendChild(entry2);
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
      selectionBusy: _historySelection.bulkInFlight
    });
    entry.addEventListener("click", (e) => {
      if (e.target.closest("[data-action]")) return;
      const renderedForSelection = entry.classList.contains("history-entry-selecting") || !!entry.querySelector('[data-action="select-run"]');
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
      selectionBox.addEventListener("change", (e) => {
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
        if (!_historyActionKeepsPanelOpenAdapter("star")) _historyHidePanelAdapter();
        refreshHistoryPanel2();
        renderHistory();
      }
    });
    _historyBindPressableAdapter(entry.querySelector('[data-action="open-schedule"]'), {
      refocusComposer: false,
      onActivate: (event) => {
        event.preventDefault();
        event.stopPropagation();
        const target = event.currentTarget;
        const ownerKind = target?.dataset?.scheduleOwnerKind || run.schedule_owner_kind || "";
        const watcherId = target?.dataset?.scheduleOwnerId || run.schedule_owner_id || run.watcher_id || "";
        const scheduleId = target?.dataset?.scheduleId || run.schedule_id || "";
        if (ownerKind === "watcher" && watcherId && typeof _historyOpenWatchersModalAdapter === "function") {
          void _historyOpenWatchersModalAdapter({ watcherId });
        } else if (scheduleId && typeof _historyOpenSchedulesModalAdapter === "function") {
          void _historyOpenSchedulesModalAdapter({ scheduleId });
        }
      }
    });
    _historyBindPressableAdapter(entry.querySelector('[data-action="copy-command"]'), {
      onActivate: () => {
        _historyCloseActionMenusAdapter();
        _historyCopyTextToClipboardAdapter(run.command).then(() => _historyShowToastAdapter("Command copied")).catch(() => _historyShowToastAdapter("Failed to copy command", "error"));
      }
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
        const cmdEl = entry.querySelector(".history-entry-cmd");
        cmdEl.textContent = "loading…";
        if (historyLoadOverlay2) {
          historyLoadOverlay2.classList.add("open");
          historyLoadOverlay2.setAttribute("aria-hidden", "false");
        }
        _historySetLoadStateAdapter(true);
        _historyRestoreRunIntoTabAdapter(run, {
          targetTabId: canUpgradeExisting ? existing.id : null,
          hidePanelOnSuccess: true
        }).catch(() => {
          entry.querySelector(".history-entry-cmd").textContent = run.command;
          _historyShowToastAdapter("Failed to load run");
        }).finally(() => {
          if (historyLoadOverlay2) {
            historyLoadOverlay2.classList.remove("open");
            historyLoadOverlay2.setAttribute("aria-hidden", "true");
          }
          _historySetLoadStateAdapter(false);
        });
      }
    });
    _historyBindPressableAdapter(entry.querySelector('[data-action="history-menu"]'), {
      refocusComposer: false,
      onActivate: (event) => {
        event.preventDefault();
        event.stopPropagation();
        const wrap = entry.querySelector(".history-action-menu-wrap");
        if (!wrap) return;
        const open = !wrap.classList.contains("open");
        _historyCloseActionMenusAdapter(open ? wrap : null);
        wrap.classList.toggle("open", open);
        entry.querySelector('[data-action="history-menu"]')?.setAttribute("aria-expanded", open ? "true" : "false");
        if (open) _historyPositionActionMenuAdapter(wrap);
        else _historyResetActionMenuPositionAdapter(wrap);
      }
    });
    _historyBindPressableAdapter(entry.querySelector('[data-action="permalink"]'), {
      onActivate: () => {
        _historyCloseActionMenusAdapter();
        _historyCopyRunPermalinkAdapter(run).catch(() => _historyShowToastAdapter("Failed to copy link", "error"));
        if (!_historyActionKeepsPanelOpenAdapter("permalink")) _historyHidePanelAdapter();
      }
    });
    _historyBindPressableAdapter(entry.querySelector('[data-action="edit-metadata"]'), {
      refocusComposer: false,
      onActivate: () => {
        _historyCloseActionMenusAdapter();
        _historyEditEntityMetadataAdapter("run", run);
      }
    });
    _historyBindPressableAdapter(entry.querySelector('[data-action="open-atlas"]'), {
      refocusComposer: false,
      onActivate: (event) => {
        event.preventDefault();
        event.stopPropagation();
        _historyCloseActionMenusAdapter();
        if (typeof _historyOpenAtlasAdapter === "function") void _historyOpenAtlasAdapter({ source: "history-run" });
      }
    });
    _historyBindPressableAdapter(entry.querySelector('[data-action="watch-command"]'), {
      refocusComposer: false,
      onActivate: (event) => {
        event.preventDefault();
        event.stopPropagation();
        _historyCloseActionMenusAdapter();
        if (typeof _historyOpenWatchersModalAdapter === "function") void _historyOpenWatchersModalAdapter({ baselineRun: run });
      }
    });
    _historyBindPressableAdapter(entry.querySelector('[data-action="compare"]'), {
      refocusComposer: false,
      onActivate: () => {
        _historyCloseActionMenusAdapter();
        const opened = _historyOpenCompareLauncherAdapter(run);
        if (!opened) {
          _historyShowToastAdapter("Run comparison is not available.", "error");
          return;
        }
        if (!_historyActionKeepsPanelOpenAdapter("compare")) _historyHidePanelAdapter();
      }
    });
    _historyBindPressableAdapter(entry.querySelector('[data-action="add-active-project"]'), {
      refocusComposer: false,
      onActivate: (event) => {
        event.preventDefault();
        event.stopPropagation();
        _historyCloseActionMenusAdapter();
        _historyAddRunToActiveProjectAdapter(run).catch(() => _historyShowToastAdapter("Failed to add run to active project", "error"));
      }
    });
    _historyBindPressableAdapter(entry.querySelector('[data-action="add-project"]'), {
      refocusComposer: false,
      onActivate: (event) => {
        event.preventDefault();
        event.stopPropagation();
        _historyCloseActionMenusAdapter();
        _historyAddRunToProjectAdapter(run).catch(() => _historyShowToastAdapter("Failed to add run to project", "error"));
      }
    });
    _historyBindPressableAdapter(entry.querySelector('[data-action="remove-project"]'), {
      refocusComposer: false,
      onActivate: (event) => {
        event.preventDefault();
        event.stopPropagation();
        _historyCloseActionMenusAdapter();
        _historyRemoveRunFromProjectAdapter(run).catch(() => _historyShowToastAdapter("Failed to remove run from project", "error"));
      }
    });
    _historyBindPressableAdapter(entry.querySelector('[data-action="copy-run-id"]'), {
      onActivate: () => {
        _historyCloseActionMenusAdapter();
        _historyCopyTextToClipboardAdapter(run.id).then(() => _historyShowToastAdapter("Run ID copied")).catch(() => _historyShowToastAdapter("Failed to copy run ID", "error"));
      }
    });
    _historyBindPressableAdapter(entry.querySelector('[data-action="delete"]'), {
      onActivate: () => {
        _historyCloseActionMenusAdapter();
        _historyConfirmActionAdapter("delete", run.id, run.command);
      }
    });
    historyList2.appendChild(entry);
  });
  _historyRenderPagination(visibleItems.length);
  if (typeof _historyEmitUiEventAdapter === "function") {
    _historyEmitUiEventAdapter("app:history-panel-refreshed", {
      items: visibleItems.slice(),
      runs: visibleItems.filter((item) => item.type === "run").slice(),
      roots: Array.isArray(data.roots) ? data.roots.slice() : [],
      paging: { ..._historyPaging },
      filters: { ..._historyFilters }
    });
  }
}
function _historyRenderCurrentPanel() {
  if (!_historyLatestPanelData) {
    _renderHistoryBulkToolbar();
    return refreshHistoryPanel2();
  }
  _historyRenderPanelData(_historyLatestPanelData);
  return Promise.resolve();
}
function refreshHistoryPanel2() {
  return Promise.resolve(_historyEnsureProjectFilterOptionsAdapter()).catch(() => []).then(() => {
    _syncHistoryFilterControls();
    _renderHistoryActiveFilters();
    return _historyApiFetchAdapter(_buildHistoryRequestUrl());
  }).then((r) => r.json()).then((data) => {
    _historyLatestPanelData = data;
    _historyRenderPanelData(data);
  });
}
if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
  document.addEventListener("click", (event) => {
    if (event.target && event.target.closest && event.target.closest(".history-action-menu-wrap")) return;
    if (event.target && event.target.closest && event.target.closest(".history-bulk-actions-wrap")) return;
    if (event.target && event.target.closest && event.target.closest(".history-compare-actions-menu-wrap")) return;
    if (event.target && event.target.closest && event.target.closest(".history-run-action-menu-wrap")) return;
    _historyCloseActionMenusAdapter();
    _closeHistoryBulkActionMenu();
    _closeHistoryCompareActionMenusIfLoaded();
    _historyCloseRunActionMenusAdapter();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      _historyCloseActionMenusAdapter();
      _closeHistoryBulkActionMenu();
      _closeHistoryCompareActionMenusIfLoaded();
      _historyCloseRunActionMenusAdapter();
    }
  });
}
if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
  window.addEventListener("resize", () => {
    _historyCloseActionMenusAdapter();
    _closeHistoryBulkActionMenu();
    _closeHistoryCompareActionMenusIfLoaded();
    _historyCloseRunActionMenusAdapter();
  });
  window.addEventListener("scroll", () => {
    _historyCloseActionMenusAdapter();
    _closeHistoryBulkActionMenu();
    _closeHistoryCompareActionMenusIfLoaded();
    _historyCloseRunActionMenusAdapter();
  }, true);
}
if (typeof historySearchInput2 !== "undefined" && historySearchInput2) {
  historySearchInput2.addEventListener("input", (e) => {
    _setHistoryFilter("q", e.target.value, { debounce: true });
  });
}
if (typeof historyMobileFiltersToggle2 !== "undefined" && historyMobileFiltersToggle2) {
  historyMobileFiltersToggle2.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    toggleHistoryMobileFilters();
  });
}
if (typeof historyRootInput2 !== "undefined" && historyRootInput2) {
  historyRootInput2.addEventListener("input", (e) => {
    if (_historyRootSuppressInputOnce) {
      _historyRootSuppressInputOnce = false;
      return;
    }
    _historyRootIndex = -1;
    _historyRefreshRootDropdown();
    _setHistoryFilter("commandRoot", e.target.value, { debounce: true });
  });
  historyRootInput2.addEventListener("focus", () => {
    _historyRootInputFocused = true;
    _historyRootIndex = -1;
    _historyRefreshRootDropdown();
  });
  historyRootInput2.addEventListener("blur", () => {
    setTimeout(() => {
      _historyRootInputFocused = false;
      _hideHistoryRootDropdown();
    }, 0);
  });
  historyRootInput2.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      _hideHistoryRootDropdown();
      return;
    }
    if (e.key === "ArrowDown") {
      if (!_historyRootFiltered.length) return;
      e.preventDefault();
      _historyRootIndex = (_historyRootIndex + 1) % _historyRootFiltered.length;
      _renderHistoryRootDropdown(_historyRootFiltered, historyRootInput2.value);
      return;
    }
    if (e.key === "ArrowUp") {
      if (!_historyRootFiltered.length) return;
      e.preventDefault();
      _historyRootIndex = _historyRootIndex <= 0 ? _historyRootFiltered.length - 1 : _historyRootIndex - 1;
      _renderHistoryRootDropdown(_historyRootFiltered, historyRootInput2.value);
      return;
    }
    if (e.key === "Enter" && _historyRootIndex >= 0 && _historyRootFiltered[_historyRootIndex]) {
      e.preventDefault();
      _acceptHistoryRootSuggestion(_historyRootFiltered[_historyRootIndex]);
    }
  });
}
if (typeof historyTypeFilter2 !== "undefined" && historyTypeFilter2) {
  historyTypeFilter2.addEventListener("change", (e) => {
    _setHistoryFilter("type", e.target.value);
  });
}
if (typeof historyExitFilter2 !== "undefined" && historyExitFilter2) {
  historyExitFilter2.addEventListener("change", (e) => {
    _setHistoryFilter("exitCode", e.target.value);
  });
}
if (typeof historySignalFilter2 !== "undefined" && historySignalFilter2) {
  historySignalFilter2.addEventListener("change", (e) => {
    _setHistoryFilter("signal", e.target.value);
  });
}
if (typeof historyKindFilter2 !== "undefined" && historyKindFilter2) {
  historyKindFilter2.addEventListener("change", (e) => {
    _setHistoryFilter("kind", e.target.value);
  });
}
if (typeof historyEntityInput2 !== "undefined" && historyEntityInput2) {
  historyEntityInput2.addEventListener("input", (e) => {
    _setHistoryFilter("entity", e.target.value, { debounce: true });
  });
}
if (typeof historyEntityTypeFilter2 !== "undefined" && historyEntityTypeFilter2) {
  historyEntityTypeFilter2.addEventListener("change", (e) => {
    _setHistoryFilter("entityType", e.target.value);
  });
}
if (typeof historyDateFilter2 !== "undefined" && historyDateFilter2) {
  historyDateFilter2.addEventListener("change", (e) => {
    _setHistoryFilter("dateRange", e.target.value);
  });
}
if (typeof historyProjectFilter2 !== "undefined" && historyProjectFilter2) {
  historyProjectFilter2.addEventListener("focus", () => {
    _historyEnsureProjectFilterOptionsAdapter().catch(() => {
    });
  });
  historyProjectFilter2.addEventListener("change", (e) => {
    _setHistoryFilter("projectId", e.target.value);
  });
}
if (typeof historyStarredToggle2 !== "undefined" && historyStarredToggle2) {
  historyStarredToggle2.addEventListener("change", (e) => {
    _setHistoryFilter("starredOnly", e.target.checked);
  });
}
if (typeof historyClearFiltersBtn2 !== "undefined" && historyClearFiltersBtn2) {
  historyClearFiltersBtn2.addEventListener("click", () => clearHistoryFilters());
}
_syncHistoryFilterControls();
if (typeof setHistoryPanelHandlers === "function") {
  setHistoryPanelHandlers({
    openHistoryWithFilters,
    refreshHistoryPanel: refreshHistoryPanel2,
    renderHistory,
    resetHistoryMobileFilters,
    resetHistorySelectionOnClose: _historyResetSelectionOnClose
  });
}

// app/static/js/features/history/history_mutations.js
var _pendingHistActionFallback = null;
var HISTORY_MUTATIONS_GLOBAL = typeof window !== "undefined" ? window : globalThis;
function _historyMutationState() {
  if (typeof getAppState === "function") return getAppState();
  if (typeof HISTORY_MUTATIONS_GLOBAL.APP_STATE_API?.getState === "function") return HISTORY_MUTATIONS_GLOBAL.APP_STATE_API.getState();
  return HISTORY_MUTATIONS_GLOBAL.APP_STATE || null;
}
function _historyPendingAction() {
  const state = _historyMutationState();
  if (state) return state.pendingHistAction || null;
  return _pendingHistActionFallback;
}
function _historySetPendingAction(action) {
  const state = _historyMutationState();
  if (state) state.pendingHistAction = action || null;
  _pendingHistActionFallback = action || null;
  return action || null;
}
function _historyMutationCmdHistory() {
  const state = _historyMutationState();
  if (state && Array.isArray(state.cmdHistory)) return state.cmdHistory;
  return [];
}
function _historyMutationSetCmdHistory(next) {
  const value = Array.isArray(next) ? next : [];
  const state = _historyMutationState();
  if (state) state.cmdHistory = value;
  return value;
}
function _historyMutationRecentPreviewHistory() {
  const state = _historyMutationState();
  if (state && Array.isArray(state.recentPreviewHistory)) return state.recentPreviewHistory;
  return [];
}
function _historyMutationSetRecentPreviewHistory(next) {
  const value = Array.isArray(next) ? next : [];
  const state = _historyMutationState();
  if (state) state.recentPreviewHistory = value;
  return value;
}
function _historyMutationGetStarred() {
  const getStarred = typeof _getStarred !== "undefined" && _getStarred || HISTORY_MUTATIONS_GLOBAL._getStarred;
  return typeof getStarred === "function" ? getStarred() : /* @__PURE__ */ new Set();
}
function _historyMutationSaveStarred(starred) {
  const saveStarred = typeof _saveStarred !== "undefined" && _saveStarred || HISTORY_MUTATIONS_GLOBAL._saveStarred;
  if (typeof saveStarred === "function") saveStarred(starred);
}
function _historyMutationLoadOverlay() {
  return typeof historyLoadOverlay !== "undefined" && historyLoadOverlay || HISTORY_MUTATIONS_GLOBAL.historyLoadOverlay || null;
}
function _historyActiveScopeCan(capability) {
  const can = typeof activeTeamScopeCan !== "undefined" && activeTeamScopeCan || null;
  return typeof can === "function" ? can(capability) : true;
}
function _historyScopeDeniedMessage(action) {
  const denied = typeof teamScopeDeniedMessage !== "undefined" && teamScopeDeniedMessage || null;
  return typeof denied === "function" ? denied(action) : `View-only team members can't ${action}. Switch to Personal or ask for operator access.`;
}
function _historyMutationShowToast(message, tone = "success") {
  const toast = typeof showToast !== "undefined" && showToast || HISTORY_MUTATIONS_GLOBAL.showToast || null;
  if (typeof toast === "function") toast(message, tone);
}
function _historyMutationShowConfirm(options) {
  const confirm = typeof showConfirm !== "undefined" && showConfirm || HISTORY_MUTATIONS_GLOBAL.showConfirm || null;
  return typeof confirm === "function" ? confirm(options) : Promise.resolve(null);
}
function _historyMutationRenderHistory() {
  const render = typeof renderHistory !== "undefined" && renderHistory || HISTORY_MUTATIONS_GLOBAL.renderHistory;
  if (typeof render === "function") render();
}
function _historyMutationRefreshHistoryPanel() {
  const refresh = typeof refreshHistoryPanel2 !== "undefined" && refreshHistoryPanel2 || HISTORY_MUTATIONS_GLOBAL.refreshHistoryPanel;
  if (typeof refresh === "function") refresh();
}
function _historyMutationApiFetch(...args) {
  const fetcher = (typeof hasRuntimeHandler === "function" && hasRuntimeHandler("apiFetch") && typeof apiFetch === "function" ? apiFetch : null) || HISTORY_MUTATIONS_GLOBAL.apiFetch;
  return typeof fetcher === "function" ? fetcher(...args) : Promise.reject(new Error("apiFetch unavailable"));
}
function _historyCanManageHistory() {
  return _historyActiveScopeCan("manage_history");
}
function _historyShowPermissionDenied(action = "delete team history") {
  _historyMutationShowToast(_historyScopeDeniedMessage(action), "error");
}
async function _historyMutationError(resp, fallback) {
  let message = fallback;
  try {
    const data = typeof resp.json === "function" ? await resp.json() : {};
    if (data && data.error === "team_forbidden") {
      message = _historyScopeDeniedMessage("delete team history");
    } else if (data && typeof data.message === "string" && data.message.trim()) {
      message = data.message.trim();
    } else if (data && typeof data.error === "string" && data.error.trim()) {
      message = data.error.trim();
    }
  } catch (_) {
  }
  const err = new Error(message || fallback);
  err.userFacing = true;
  return err;
}
function _historyCleanupLabel(cleanup) {
  const entities = Number(cleanup?.entities || 0);
  const findings = Number(cleanup?.findings || 0);
  return `${findings.toLocaleString()} ${findings === 1 ? "finding" : "findings"} and ${entities.toLocaleString()} ${entities === 1 ? "entity" : "entities"}`;
}
function _historyCuratedCleanupLabel(cleanup) {
  const entities = Number(cleanup?.curated_entities || 0);
  const findings = Number(cleanup?.curated_findings || 0);
  return `${findings.toLocaleString()} curated ${findings === 1 ? "finding" : "findings"} and ${entities.toLocaleString()} curated ${entities === 1 ? "entity" : "entities"}`;
}
function _buildHistoryAtlasCleanupContent(cleanup) {
  const curated = Number(cleanup?.curated_total || 0);
  if (!cleanup?.has_cleanup && curated <= 0) return null;
  const wrap = document.createElement("div");
  wrap.className = "modal-inline-field";
  const fieldset = document.createElement("div");
  fieldset.className = "form-fieldset";
  if (cleanup?.has_cleanup) {
    const label = document.createElement("label");
    label.className = "form-check";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = true;
    checkbox.dataset.historyAtlasCleanup = "1";
    const text = document.createElement("span");
    text.textContent = `Also remove ${_historyCleanupLabel(cleanup)} from Atlas`;
    label.append(checkbox, text);
    const note = document.createElement("div");
    note.className = "history-bulk-note";
    note.textContent = "These are disposable Atlas items only sourced by this run.";
    fieldset.append(label, note);
  }
  if (curated > 0) {
    const curatedLabel = document.createElement("label");
    curatedLabel.className = "form-check";
    const curatedCheckbox = document.createElement("input");
    curatedCheckbox.type = "checkbox";
    curatedCheckbox.checked = false;
    curatedCheckbox.dataset.historyAtlasCleanupCurated = "1";
    const curatedText = document.createElement("span");
    curatedText.textContent = "Also delete curated single-source Atlas items";
    curatedLabel.append(curatedCheckbox, curatedText);
    const curatedNote = document.createElement("div");
    curatedNote.className = "history-bulk-note";
    curatedNote.textContent = `${_historyCuratedCleanupLabel(cleanup)} will be kept unless this is checked. Curated means project-linked, project-visible, reviewed, labeled, or noted.`;
    fieldset.append(curatedLabel, curatedNote);
  }
  wrap.appendChild(fieldset);
  return wrap;
}
async function _loadHistoryAtlasCleanup(runId) {
  try {
    const resp = await _historyMutationApiFetch(`/history/${encodeURIComponent(runId)}/atlas-cleanup-preview`, { cache: "no-store" });
    if (!resp.ok) return null;
    const data = await resp.json().catch(() => ({}));
    return data.cleanup || null;
  } catch (_) {
    return null;
  }
}
function confirmHistAction(type, id, command, itemType = "run") {
  if ((type === "delete" || type === "clear") && !_historyCanManageHistory()) {
    _historyShowPermissionDenied("delete team history");
    return;
  }
  _historySetPendingAction({ type, id, command, itemType });
  const runDelete = type === "delete" && itemType !== "snapshot" && id;
  const isBulk = type === "clear";
  const buildBody = (cleanup) => isBulk ? { text: "Delete all runs and snapshots?", note: "This cannot be undone." } : itemType === "snapshot" ? { text: "Remove this snapshot from history?", note: "This cannot be undone." } : {
    text: "Remove this run from history?",
    note: cleanup?.has_cleanup ? "The run transcript will be removed. Atlas cleanup is optional." : "This cannot be undone."
  };
  const actions = isBulk ? [
    { id: "cancel", label: "Cancel", role: "cancel" },
    { id: "nonfav", label: "Delete Non-Favorites", role: "secondary", tone: "warning" },
    { id: "all", label: "Delete all", role: "destructive", tone: "warning" }
  ] : [
    { id: "cancel", label: "Cancel", role: "cancel" },
    { id: "one", label: "Delete", role: "destructive", tone: "warning" }
  ];
  const showDeleteConfirm = (cleanup) => {
    const content = runDelete ? _buildHistoryAtlasCleanupContent(cleanup) : null;
    return _historyMutationShowConfirm({
      body: buildBody(cleanup),
      content,
      tone: "warning",
      actions,
      refocusOnResolve: false
    }).then((choice) => {
      if (!choice || choice === "cancel") {
        _historySetPendingAction(null);
        return;
      }
      const pending = _historyPendingAction();
      if (pending && content) {
        pending.pruneCuratedAtlas = !!content.querySelector("[data-history-atlas-cleanup-curated]")?.checked;
        pending.pruneAtlas = !!content.querySelector("[data-history-atlas-cleanup]")?.checked || pending.pruneCuratedAtlas;
        _historySetPendingAction(pending);
      }
      if (choice === "nonfav") executeHistAction("clear-nonfav");
      else if (choice === "all") executeHistAction();
      else if (choice === "one") executeHistAction("delete");
    });
  };
  if (runDelete) {
    _loadHistoryAtlasCleanup(id).then(showDeleteConfirm);
  } else {
    showDeleteConfirm(null);
  }
}
function executeHistAction(type) {
  const pending = _historyPendingAction();
  const action = type || pending && pending.type;
  const id = pending && pending.id;
  const command = pending && pending.command;
  const itemType = pending && pending.itemType;
  const pruneAtlas = !!(pending && pending.pruneAtlas);
  const pruneCuratedAtlas = !!(pending && pending.pruneCuratedAtlas);
  _historySetPendingAction(null);
  if (action === "delete") {
    const params = new URLSearchParams();
    if (pruneAtlas) params.set("prune_atlas", "1");
    if (pruneCuratedAtlas) params.set("prune_curated_atlas", "1");
    const query = params.toString();
    const deleteUrl = itemType === "snapshot" ? `/share/${id}` : `/history/${id}${query ? `?${query}` : ""}`;
    _historyMutationApiFetch(deleteUrl, { method: "DELETE" }).then(async (resp) => {
      if (!resp.ok) throw await _historyMutationError(resp, "Failed to delete run");
      if (itemType === "snapshot") {
        _historyMutationRefreshHistoryPanel();
        return;
      }
      const s = _historyMutationGetStarred();
      if (s.has(command)) {
        s.delete(command);
        _historyMutationSaveStarred(s);
        _historyMutationApiFetch("/session/starred", {
          method: "DELETE",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ command })
        }).catch(() => {
        });
      }
      _historyMutationSetCmdHistory(_historyMutationCmdHistory().filter((c) => c !== command));
      _historyMutationSetRecentPreviewHistory(
        _historyMutationRecentPreviewHistory().filter((c) => c !== command)
      );
      _historyMutationRenderHistory();
      _historyMutationRefreshHistoryPanel();
    }).catch((err) => _historyMutationShowToast(err.userFacing ? err.message : "Failed to delete run", "error"));
  } else if (action === "clear-nonfav") {
    _historyMutationApiFetch("/history?type=runs").then((r) => r.json()).then((data) => {
      const starred = _historyMutationGetStarred();
      const toDelete = data.runs.filter((r) => !starred.has(r.command));
      const deleteCmds = new Set(toDelete.map((r) => r.command));
      _historyMutationSetCmdHistory(_historyMutationCmdHistory().filter((c) => !deleteCmds.has(c)));
      _historyMutationSetRecentPreviewHistory(
        _historyMutationRecentPreviewHistory().filter((c) => !deleteCmds.has(c))
      );
      _historyMutationRenderHistory();
      return Promise.all(toDelete.map(async (r) => {
        const resp = await _historyMutationApiFetch(`/history/${r.id}`, { method: "DELETE" });
        if (!resp.ok) throw await _historyMutationError(resp, "Failed to clear history");
        return resp;
      }));
    }).then(() => _historyMutationRefreshHistoryPanel()).catch((err) => _historyMutationShowToast(err.userFacing ? err.message : "Failed to clear history", "error"));
  } else {
    _historyMutationApiFetch("/history", { method: "DELETE" }).then(async (resp) => {
      if (!resp.ok) throw await _historyMutationError(resp, "Failed to clear history");
      _historyMutationSaveStarred(/* @__PURE__ */ new Set());
      _historyMutationApiFetch("/session/starred", { method: "DELETE" }).catch(() => {
      });
      _historyMutationSetCmdHistory([]);
      _historyMutationSetRecentPreviewHistory([]);
      _historyMutationRenderHistory();
      _historyMutationRefreshHistoryPanel();
    }).catch((err) => _historyMutationShowToast(err.userFacing ? err.message : "Failed to clear history", "error"));
  }
}
function _setHistoryLoadState(loading) {
  if (!_historyMutationLoadOverlay()) return;
  if (loading && typeof HISTORY_MUTATIONS_GLOBAL.showHistoryLoadOverlay === "function") {
    HISTORY_MUTATIONS_GLOBAL.showHistoryLoadOverlay();
  } else if (!loading && typeof HISTORY_MUTATIONS_GLOBAL.hideHistoryLoadOverlay === "function") {
    HISTORY_MUTATIONS_GLOBAL.hideHistoryLoadOverlay();
  }
}
if (typeof window !== "undefined") {
}

export {
  setControllerActionHandlers,
  openFaq,
  closeFaq,
  openWorkflows,
  closeWorkflows,
  toggleHistoryPanelSurface,
  toggleRailCollapsed,
  copyHistoryRunPermalink,
  _historyScopeDeniedMessage,
  _historyCanManageHistory,
  confirmHistAction,
  _setHistoryLoadState,
  _historyProjectDisplayName,
  _historyLoadActiveProject,
  _historyLinkRunToProject,
  _historyConfirmAddRunToProject,
  _historyRunProjectLinks,
  _historyAddRunToActiveProject,
  _historyRemoveRunFromProject,
  _historyAddRunToProject,
  _historyRelativeTime,
  _historyEntityLabelValues,
  _historyEntityNoteBody,
  _historyExitLabel,
  _historyElapsedLabel,
  _historyEditEntityMetadata,
  _tabForHistoryRun,
  restoreHistoryRunIntoTab,
  _historyResetSelectionOnClose,
  openHistoryWithFilters,
  resetHistoryMobileFilters,
  refreshHistoryPanel2 as refreshHistoryPanel
};
