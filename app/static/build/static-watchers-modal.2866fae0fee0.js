import {
  _compareMetricCell,
  fetchAndRenderHistoryComparison
} from "./static-chunk-k7lxp5uc.48bf8df34490.js";
import "./static-chunk-bdi6cdox.1b5c7ee8e1bb.js";
import "./static-chunk-w2kqlfx2.5de243990f3a.js";
import {
  openHistoryRunDetails
} from "./static-chunk-hrmcowre.5779819329ea.js";
import "./static-chunk-bnznujz3.950d8bac2972.js";
import "./static-chunk-xdnhi6ng.03705073697e.js";
import "./static-chunk-tda3zjlz.ba4d349f2998.js";
import "./static-chunk-gy5x3nam.408b87d8933a.js";
import "./static-chunk-su3zfblw.dfaa45e2b263.js";
import "./static-chunk-xbxp24ix.e021648f87bd.js";
import {
  closeMajorOverlays,
  loadWatcherAutocompleteHints
} from "./static-chunk-5i2t3zlu.acdd7b56baea.js";
import {
  showToast
} from "./static-chunk-poi5czx6.3f5c94749765.js";
import "./static-chunk-zpenfczu.1862ffb66041.js";
import {
  bindDismissible,
  bindPressable
} from "./static-chunk-4m44pm74.0a8001fa1d52.js";
import "./static-chunk-2bgb52uq.a327269283bb.js";
import {
  emitUiEvent,
  hasHistoryPanelHandler,
  refocusComposerAfterAction,
  refreshHistoryPanel,
  syncModalOverlayState
} from "./static-chunk-yo5cjr7d.b86e0c93eff0.js";
import {
  getAppConfig
} from "./static-chunk-gwztcp24.e58b5ff85d88.js";
import {
  apiFetch,
  hasRuntimeHandler,
  logClientError
} from "./static-chunk-2kxtimik.c9801087c7a7.js";
import "./static-chunk-b3etjcu4.ab70b0c41ed7.js";
import "./static-chunk-3ftojl3p.96e64f27bcbd.js";

// app/static/js/features/watchers/watchers_modal.js
var WATCHERS_DEFAULT_CRON = "0 * * * *";
var WATCHERS_FIRES_LIMIT = 20;
var WATCHERS_CADENCE_PRESETS = [
  ["hourly", "Every hour"],
  ["daily", "Daily"],
  ["weekly", "Weekly"]
];
var WATCHERS_COMMON_TIMEZONES = [
  "UTC",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Phoenix",
  "America/Anchorage",
  "Pacific/Honolulu",
  "Europe/London",
  "Europe/Berlin",
  "Europe/Paris",
  "Asia/Tokyo",
  "Asia/Singapore",
  "Australia/Sydney"
];
var WATCHERS_GLOBAL = typeof window !== "undefined" ? window : globalThis;
var _watchersState = {
  watchers: [],
  projects: [],
  selectedId: "",
  draft: null,
  mode: "view",
  fires: [],
  firesMeta: { limit: WATCHERS_FIRES_LIMIT, offset: 0, total: 0, has_more: false },
  loading: false,
  loadingFires: false,
  saving: false,
  missingWatcherId: "",
  preview: { loading: false, error: "", next_fires: [], cron_expr: WATCHERS_DEFAULT_CRON, timezone: _watcherDefaultTimezone() },
  previewTimer: null,
  previewController: null,
  cleanDraft: null,
  formDirty: false,
  discardPromptOpen: false
};
function _watcherAppConfig() {
  if (typeof getAppConfig === "function") return getAppConfig();
  return WATCHERS_GLOBAL.APP_CONFIG || null;
}
function _watcherApiFetch(...args) {
  const fetcher = (typeof hasRuntimeHandler === "function" && hasRuntimeHandler("apiFetch") && typeof apiFetch === "function" ? apiFetch : null) || (typeof WATCHERS_GLOBAL.apiFetch === "function" ? WATCHERS_GLOBAL.apiFetch : null);
  if (!fetcher) return Promise.reject(new Error("apiFetch is not available"));
  return fetcher(...args);
}
function _watcherRefocusComposerAfterAction(options) {
  const refocus = typeof refocusComposerAfterAction === "function" ? refocusComposerAfterAction : typeof WATCHERS_GLOBAL.refocusComposerAfterAction === "function" ? WATCHERS_GLOBAL.refocusComposerAfterAction : null;
  if (refocus) refocus(options);
}
function _watcherSyncModalOverlayState() {
  const sync = typeof syncModalOverlayState === "function" ? syncModalOverlayState : null;
  if (sync) sync();
}
function _watcherShowConfirm(options) {
  const confirm = typeof WATCHERS_GLOBAL.showConfirm === "function" ? WATCHERS_GLOBAL.showConfirm : null;
  return confirm ? confirm(options) : Promise.resolve(null);
}
function _watcherBindDismissible(overlay, options) {
  const bind = typeof bindDismissible === "function" ? bindDismissible : typeof WATCHERS_GLOBAL.bindDismissible === "function" ? WATCHERS_GLOBAL.bindDismissible : null;
  return bind ? bind(overlay, options) : null;
}
function _watcherEmitUiEvent(name, detail) {
  const emit = typeof emitUiEvent === "function" ? emitUiEvent : typeof WATCHERS_GLOBAL.emitUiEvent === "function" ? WATCHERS_GLOBAL.emitUiEvent : null;
  if (emit) emit(name, detail);
}
function _watcherOpenHistoryRunDetails(runId) {
  const open = typeof openHistoryRunDetails === "function" ? openHistoryRunDetails : typeof WATCHERS_GLOBAL.openHistoryRunDetails === "function" ? WATCHERS_GLOBAL.openHistoryRunDetails : null;
  if (open) open({ id: runId || "" });
}
function _watcherFetchAndRenderHistoryComparison(...args) {
  const compare = typeof fetchAndRenderHistoryComparison === "function" ? fetchAndRenderHistoryComparison : typeof WATCHERS_GLOBAL.fetchAndRenderHistoryComparison === "function" ? WATCHERS_GLOBAL.fetchAndRenderHistoryComparison : null;
  if (!compare) return Promise.reject(new Error("Run comparison is not available."));
  return compare(...args);
}
function _watcherCompareMetricCell(label, value, tone = "") {
  const render = typeof _compareMetricCell === "function" ? _compareMetricCell : typeof window !== "undefined" && typeof window._compareMetricCell === "function" ? window._compareMetricCell : null;
  return render ? render(label, value, tone) : null;
}
function _watcherLoadAutocompleteHints() {
  const load = typeof loadWatcherAutocompleteHints === "function" ? loadWatcherAutocompleteHints : typeof WATCHERS_GLOBAL.loadWatcherAutocompleteHints === "function" ? WATCHERS_GLOBAL.loadWatcherAutocompleteHints : null;
  return load ? load() : Promise.resolve();
}
function _watcherEls() {
  return {
    overlay: document.getElementById("watchers-overlay"),
    list: document.getElementById("watchers-list"),
    detail: document.getElementById("watchers-detail"),
    count: document.getElementById("watchers-count"),
    newBtn: document.getElementById("watchers-new-btn"),
    refreshBtn: document.getElementById("watchers-refresh-btn")
  };
}
function _watcherDefaultTimezone() {
  const configured = String(_watcherAppConfig()?.scheduler_default_timezone || "").trim();
  return configured || "UTC";
}
function _watcherTitle(watcher) {
  return String(watcher?.label || watcher?.command_text || watcher?.id || "Watcher").trim();
}
function _watcherSelected() {
  return _watchersState.watchers.find((item) => String(item.id || "") === String(_watchersState.selectedId || "")) || null;
}
function _watcherSchedule(watcher) {
  return watcher?.schedule || {};
}
function _watcherPresetFor(watcher) {
  const schedule = _watcherSchedule(watcher);
  const preset = String(schedule.cadence_preset || watcher?.cadence_preset || "").trim().toLowerCase();
  if (preset && WATCHERS_CADENCE_PRESETS.some(([value]) => value === preset)) return preset;
  return "custom";
}
function _watcherDraftFromWatcher(watcher = null, baselineRun = null) {
  const schedule = _watcherSchedule(watcher);
  const preset = watcher ? _watcherPresetFor(watcher) : "hourly";
  const baselineId = String(
    watcher?.baseline_run_id || baselineRun?.id || baselineRun?.run_id || ""
  ).trim();
  const command = String(watcher?.command_text || baselineRun?.command || "").trim();
  const baselineMode = baselineId ? "existing_run" : "first_run";
  const policy = watcher?.policy && typeof watcher.policy === "object" ? watcher.policy : {};
  return {
    id: watcher?.id || "",
    label: String(watcher?.label || "").trim(),
    project_id: String(watcher?.project_id || baselineRun?.project_id || "").trim(),
    baseline_mode: baselineMode,
    baseline_run_id: baselineId,
    command_text: command,
    cadence_preset: preset,
    cron_expr: String(schedule.cron_expr || watcher?.cron_expr || WATCHERS_DEFAULT_CRON).trim(),
    timezone: String(schedule.timezone || watcher?.timezone || _watcherDefaultTimezone()).trim(),
    enabled: watcher ? watcher.state !== "paused" && schedule.enabled !== false : true,
    suppress_removals: !!watcher?.options?.suppress_removals,
    notify_metadata_changes: !!watcher?.options?.notify_metadata_changes,
    ignore_line_patterns: Array.isArray(policy.ignore_line_patterns) ? policy.ignore_line_patterns.join("\n") : "",
    alert_after_repeated_changes: Math.max(1, Number(policy.alert_after_repeated_changes || 1) || 1),
    alert_signal_classes: Array.isArray(policy.alert_signal_classes) ? policy.alert_signal_classes.map((item) => String(item || "").trim()).filter(Boolean) : []
  };
}
function _normalizeWatcherPolicyDraft(data = {}) {
  const rawPolicy = data.policy && typeof data.policy === "object" ? data.policy : {};
  const rawPatterns = data.ignore_line_patterns ?? rawPolicy.ignore_line_patterns ?? [];
  const patternItems = Array.isArray(rawPatterns) ? rawPatterns : String(rawPatterns || "").split(/\r?\n/);
  const patterns = [];
  patternItems.forEach((item) => {
    const value = String(item || "").trim();
    if (value && !patterns.includes(value)) patterns.push(value);
  });
  const repeated = Math.min(10, Math.max(1, Number(
    data.alert_after_repeated_changes ?? rawPolicy.alert_after_repeated_changes ?? 1
  ) || 1));
  const rawClasses = data.alert_signal_classes ?? rawPolicy.alert_signal_classes ?? [];
  const classes = (Array.isArray(rawClasses) ? rawClasses : [rawClasses]).map((item) => String(item || "").trim()).filter(Boolean).filter((item, index, list) => list.indexOf(item) === index);
  return {
    ignore_line_patterns: patterns,
    alert_after_repeated_changes: repeated,
    alert_signal_classes: classes
  };
}
async function _watcherJson(url, options = {}) {
  const resp = await _watcherApiFetch(url, options);
  let data = {};
  try {
    data = await resp.json();
  } catch (err) {
    _watcherClientError(`failed to parse watcher response from ${url}`, err);
    data = {};
  }
  if (!resp.ok) {
    const message = data?.message || data?.error || `HTTP ${resp.status}`;
    throw new Error(message);
  }
  return data;
}
function _watcherToast(message, tone = "success") {
  const toast = typeof showToast === "function" ? showToast : typeof WATCHERS_GLOBAL.showToast === "function" ? WATCHERS_GLOBAL.showToast : null;
  if (toast) toast(message, tone);
}
function _watcherClientError(context, err) {
  const log = (typeof hasRuntimeHandler === "function" && hasRuntimeHandler("logClientError") && typeof logClientError === "function" ? logClientError : null) || (typeof WATCHERS_GLOBAL.logClientError === "function" ? WATCHERS_GLOBAL.logClientError : null);
  if (log) log(context, err);
}
function _watcherCloseMajorOverlays() {
  const close = typeof closeMajorOverlays === "function" && closeMajorOverlays || WATCHERS_GLOBAL._closeMajorOverlays;
  if (typeof close === "function") close();
}
function _watcherRefreshHistoryPanel() {
  if (typeof hasHistoryPanelHandler === "function" && hasHistoryPanelHandler("refreshHistoryPanel") && typeof refreshHistoryPanel === "function") {
    return refreshHistoryPanel();
  }
  if (typeof WATCHERS_GLOBAL.refreshHistoryPanel === "function") return WATCHERS_GLOBAL.refreshHistoryPanel();
  return null;
}
function _watcherDateLabel(value) {
  const raw = String(value || "").trim();
  if (!raw) return "never";
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  return date.toLocaleString();
}
function _watcherPreviewDateLabel(value, timezone) {
  const raw = String(value || "").trim();
  if (!raw) return "never";
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  try {
    return date.toLocaleString(void 0, {
      timeZone: timezone || "UTC",
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      timeZoneName: "short"
    });
  } catch (_) {
    return _watcherDateLabel(value);
  }
}
function _watcherBrowserTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  } catch (_) {
    return "";
  }
}
function _watcherTimezoneOptions(selected) {
  const preferred = /* @__PURE__ */ new Set(["UTC"]);
  const browserTimezone = _watcherBrowserTimezone();
  if (browserTimezone) preferred.add(browserTimezone);
  WATCHERS_COMMON_TIMEZONES.forEach((zone) => preferred.add(zone));
  if (selected) preferred.add(selected);
  let supported = [];
  try {
    supported = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];
  } catch (_) {
    supported = [];
  }
  supported.forEach((zone) => preferred.add(zone));
  return Array.from(preferred);
}
function _watcherStateLabel(watcher) {
  const state = String(watcher?.state || "").trim().toLowerCase();
  if (!String(watcher?.baseline_run_id || "").trim() && state !== "firing" && state !== "paused" && state !== "error") {
    return "pending baseline";
  }
  if (!state) return "ok";
  if (state === "firing") return "firing";
  if (state === "paused") return "paused";
  if (state === "changed") return "changed";
  if (state === "error") return "error";
  return state;
}
function _watcherStateTone(watcher) {
  const label = _watcherStateLabel(watcher);
  if (label === "ok") return "badge-tone-green";
  if (label === "changed" || label === "firing" || label === "pending baseline") return "badge-tone-amber";
  if (label === "error") return "badge-tone-red";
  return "badge-tone-muted";
}
function _watcherDiffTone(kind) {
  const normalized = String(kind || "").trim().toLowerCase();
  if (normalized === "signal" || normalized === "textual") return "badge-tone-amber";
  if (normalized === "none") return "badge-tone-muted";
  return "badge-tone-muted";
}
function _bindWatcherPressable(el, onActivate, options = {}) {
  if (!el || typeof onActivate !== "function") return;
  const bind = typeof bindPressable === "function" ? bindPressable : typeof WATCHERS_GLOBAL.bindPressable === "function" ? WATCHERS_GLOBAL.bindPressable : null;
  if (bind) {
    bind(el, { refocusComposer: false, ...options, onActivate });
    return;
  }
  el.addEventListener("click", onActivate);
  if (el.tagName?.toLowerCase() === "button") return;
  el.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    onActivate(event);
  });
}
function _setWatchersOpen(open) {
  const { overlay } = _watcherEls();
  if (!overlay) return;
  overlay.classList.toggle("u-hidden", !open);
  overlay.classList.toggle("open", !!open);
  overlay.setAttribute("aria-hidden", open ? "false" : "true");
  _watcherSyncModalOverlayState();
  if (open) _focusWatchersModal();
}
function isWatchersOverlayOpen() {
  const { overlay } = _watcherEls();
  return !!(overlay && overlay.classList.contains("open"));
}
function _focusWatchersModal() {
  const modal = document.getElementById("watchers-modal");
  if (!modal || typeof modal.focus !== "function" || !isWatchersOverlayOpen()) return;
  if (modal.contains(document.activeElement)) return;
  try {
    modal.focus({ preventScroll: true });
  } catch (_) {
    modal.focus();
  }
}
function _normalizeWatcherComparable(data = {}) {
  const preset = String(data.cadence_preset || "").trim();
  const options = data.options && typeof data.options === "object" ? data.options : {};
  const policy = _normalizeWatcherPolicyDraft(data);
  return {
    label: String(data.label || "").trim(),
    project_id: String(data.project_id || "").trim(),
    baseline_run_id: String(data.baseline_run_id || "").trim(),
    baseline_mode: String(data.baseline_mode || (data.baseline_run_id ? "existing_run" : "first_run")).trim(),
    command: String(data.command ?? data.command_text ?? "").trim(),
    cadence_preset: preset === "custom" ? "" : preset,
    cron_expr: String(data.cron_expr || WATCHERS_DEFAULT_CRON).trim(),
    timezone: String(data.timezone || _watcherDefaultTimezone()).trim(),
    enabled: data.enabled !== false,
    suppress_removals: !!(data.suppress_removals ?? options.suppress_removals),
    notify_metadata_changes: !!(data.notify_metadata_changes ?? options.notify_metadata_changes),
    ignore_line_patterns: policy.ignore_line_patterns,
    alert_after_repeated_changes: policy.alert_after_repeated_changes,
    alert_signal_classes: policy.alert_signal_classes
  };
}
function _markWatcherClean(draft = _watchersState.draft) {
  _watchersState.cleanDraft = draft ? _normalizeWatcherComparable(draft) : null;
  _watchersState.formDirty = false;
}
function _markWatcherDirty(event) {
  if (event?.target?.closest?.("#watchers-form")) {
    _watchersState.formDirty = true;
  }
}
function _watcherCurrentComparable() {
  const form = document.getElementById("watchers-form");
  return form ? _normalizeWatcherComparable(_collectWatcherDraft(form)) : _normalizeWatcherComparable(_watchersState.draft || {});
}
function _watcherNewDraftHasMeaningfulInput(draft) {
  const data = _normalizeWatcherComparable(draft);
  return !!(data.label || data.project_id || data.baseline_run_id || data.baseline_mode !== "first_run" || data.command || data.cadence_preset !== "hourly" || data.cron_expr !== WATCHERS_DEFAULT_CRON || data.timezone !== _watcherDefaultTimezone() || data.enabled === false || data.suppress_removals || data.notify_metadata_changes || data.ignore_line_patterns.length || data.alert_after_repeated_changes !== 1 || data.alert_signal_classes.length);
}
function _watcherHasUnsavedChanges() {
  if (!document.getElementById("watchers-form")) return false;
  const current = _watcherCurrentComparable();
  if (_watchersState.mode === "new") return _watcherNewDraftHasMeaningfulInput(current);
  if (!_watchersState.cleanDraft) return _watchersState.formDirty;
  return _watchersState.formDirty || JSON.stringify(current) !== JSON.stringify(_watchersState.cleanDraft);
}
async function _confirmWatcherDiscardChanges() {
  if (!_watcherHasUnsavedChanges()) return true;
  if (_watchersState.discardPromptOpen) return false;
  _watchersState.discardPromptOpen = true;
  try {
    const choice = await _watcherShowConfirm({
      body: "Discard unsaved watcher changes?",
      tone: "warning",
      actions: [
        { id: "cancel", label: "Cancel", role: "cancel" },
        { id: "discard", label: "Discard changes", role: "destructive" }
      ]
    });
    return choice === null ? true : choice === "discard";
  } finally {
    _watchersState.discardPromptOpen = false;
  }
}
async function closeWatchersModal({ refocus = true, force = false } = {}) {
  if (!force && !await _confirmWatcherDiscardChanges()) return false;
  _cancelWatcherPreview();
  _watchersState.cleanDraft = null;
  _watchersState.formDirty = false;
  _setWatchersOpen(false);
  if (refocus) _watcherRefocusComposerAfterAction({ preventScroll: true, defer: true });
  return true;
}
function _cancelWatcherPreview() {
  window.clearTimeout(_watchersState.previewTimer);
  _watchersState.previewTimer = null;
  try {
    _watchersState.previewController?.abort?.();
  } catch (_) {
  }
  _watchersState.previewController = null;
}
function _renderWatchersList() {
  const { list, count } = _watcherEls();
  if (!list) return;
  list.replaceChildren();
  if (count) count.textContent = String(_watchersState.watchers.length);
  if (_watchersState.loading) {
    const loading = document.createElement("div");
    loading.className = "watchers-empty";
    loading.textContent = "Loading watchers...";
    list.appendChild(loading);
    return;
  }
  if (!_watchersState.watchers.length) {
    const empty = document.createElement("div");
    empty.className = "watchers-empty";
    empty.textContent = "No watchers saved.";
    list.appendChild(empty);
    return;
  }
  _watchersState.watchers.forEach((watcher) => {
    const row = document.createElement("div");
    row.className = "watchers-list-row panel-row panel-row-clickable";
    row.dataset.watcherId = watcher.id || "";
    row.setAttribute("role", "button");
    row.tabIndex = 0;
    if (String(watcher.id || "") === String(_watchersState.selectedId || "")) row.classList.add("active");
    const title = document.createElement("span");
    title.className = "watchers-list-title";
    title.textContent = _watcherTitle(watcher);
    const meta = document.createElement("span");
    meta.className = "watchers-list-meta";
    const schedule = _watcherSchedule(watcher);
    const cadence = schedule.cadence_preset || schedule.cron_expr || "custom";
    meta.textContent = `${cadence} - baseline ${watcher.baseline_run_id || "pending"}`;
    const status = document.createElement("span");
    status.className = `badge ${_watcherStateTone(watcher)} watchers-list-status`;
    status.textContent = _watcherStateLabel(watcher);
    row.append(title, meta, status);
    _bindWatcherPressable(row, () => _selectWatcher(watcher.id || ""));
    list.appendChild(row);
  });
}
function _closeWatcherHelpCards(except = null) {
  document.querySelectorAll(".watchers-help-card:not(.u-hidden)").forEach((card) => {
    if (except && card === except) return;
    card.classList.add("u-hidden");
    const trigger = card.closest(".watchers-help-wrap")?.querySelector(".watchers-help-trigger");
    trigger?.setAttribute("aria-expanded", "false");
  });
}
function _watcherHelpControl({ text, label = "More about this field" } = {}) {
  const wrap = document.createElement("span");
  wrap.className = "watchers-help-wrap";
  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "watchers-help-trigger btn btn-ghost btn-icon-only btn-compact";
  trigger.textContent = "?";
  trigger.setAttribute("aria-label", label);
  trigger.setAttribute("aria-expanded", "false");
  const card = document.createElement("span");
  card.className = "watchers-help-card dropdown-surface u-hidden";
  card.textContent = text || "";
  const cardId = `watchers-help-${Math.random().toString(36).slice(2, 9)}`;
  card.id = cardId;
  trigger.setAttribute("aria-describedby", cardId);
  trigger.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    const opening = card.classList.contains("u-hidden");
    _closeWatcherHelpCards(opening ? card : null);
    card.classList.toggle("u-hidden", !opening);
    trigger.setAttribute("aria-expanded", opening ? "true" : "false");
  });
  wrap.append(trigger, card);
  return wrap;
}
function _watcherFormField(label, control, options = {}) {
  const field = document.createElement("label");
  field.className = "watchers-field";
  const text = document.createElement("span");
  text.className = "watchers-field-label";
  if (options.helpText) {
    const labelText = document.createElement("span");
    labelText.textContent = label;
    text.append(labelText, _watcherHelpControl({
      text: options.helpText,
      label: options.helpLabel || `More about ${label}`
    }));
  } else {
    text.textContent = label;
  }
  field.append(text, control);
  return field;
}
function _watcherInput(value, attrs = {}) {
  const input = document.createElement("input");
  input.className = "form-control watchers-input";
  input.value = value || "";
  Object.entries(attrs).forEach(([key, attrValue]) => {
    if (attrValue !== null && attrValue !== void 0) input.setAttribute(key, attrValue);
  });
  return input;
}
function _watcherTimezoneSelect(value) {
  const selectedValue = value || _watcherDefaultTimezone();
  const select = document.createElement("select");
  select.id = "watchers-timezone-input";
  select.className = "form-select watchers-select";
  _watcherTimezoneOptions(selectedValue).forEach((timezone) => {
    const option = document.createElement("option");
    option.value = timezone;
    option.textContent = timezone;
    if (timezone === selectedValue) option.selected = true;
    select.appendChild(option);
  });
  if (select.value !== selectedValue) select.value = _watcherDefaultTimezone();
  return select;
}
function _watcherProjectSelect(value) {
  const selectedValue = String(value || "").trim();
  const select = document.createElement("select");
  select.id = "watchers-project-input";
  select.className = "form-select watchers-select";
  const none = document.createElement("option");
  none.value = "";
  none.textContent = "No project";
  select.appendChild(none);
  (_watchersState.projects || []).forEach((project) => {
    const projectId = String(project?.id || "").trim();
    if (!projectId || String(project?.status || "active") === "archived") return;
    const option = document.createElement("option");
    option.value = projectId;
    option.textContent = String(project?.name || project?.slug || projectId);
    if (projectId === selectedValue) option.selected = true;
    select.appendChild(option);
  });
  select.value = selectedValue && [...select.options].some((option) => option.value === selectedValue) ? selectedValue : "";
  return select;
}
function _setWatcherCadencePreset(value) {
  document.querySelectorAll(".watchers-cadence-btn").forEach((btn) => {
    const active = btn.dataset.watcherPreset === value;
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-checked", active ? "true" : "false");
  });
}
function _setWatcherBaselineMode(value, root = document) {
  const mode = value === "existing_run" ? "existing_run" : "first_run";
  root.querySelectorAll(".watchers-baseline-mode-btn").forEach((btn) => {
    const active = btn.dataset.watcherBaselineMode === mode;
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-checked", active ? "true" : "false");
  });
  const baselineInput = root.querySelector("#watchers-baseline-input");
  const commandInput = root.querySelector("#watchers-command-input");
  if (baselineInput) {
    baselineInput.disabled = mode === "first_run";
    baselineInput.required = mode === "existing_run";
    baselineInput.placeholder = mode === "first_run" ? "Captured after the first successful run" : "Completed run id";
    if (mode === "first_run") baselineInput.value = "";
  }
  if (commandInput) {
    commandInput.required = mode === "first_run";
    commandInput.placeholder = mode === "first_run" ? "Command to run for the first baseline and future checks" : "Inherits the baseline command when left blank";
  }
}
function _watcherPreviewNode() {
  const wrap = document.createElement("div");
  wrap.className = "watchers-preview";
  const title = document.createElement("div");
  title.className = "watchers-section-kicker";
  const timezone = _watchersState.preview.timezone || _watchersState.draft?.timezone || _watcherDefaultTimezone();
  title.textContent = `Next checks (${timezone})`;
  wrap.appendChild(title);
  if (_watchersState.preview.loading) {
    const loading = document.createElement("div");
    loading.className = "watchers-muted";
    loading.textContent = "Checking...";
    wrap.appendChild(loading);
  } else if (_watchersState.preview.error) {
    const err = document.createElement("div");
    err.className = "watchers-error";
    err.textContent = _watchersState.preview.error;
    wrap.appendChild(err);
  } else {
    const list = document.createElement("div");
    list.className = "watchers-preview-list";
    (_watchersState.preview.next_fires || []).forEach((value) => {
      const item = document.createElement("span");
      item.textContent = _watcherPreviewDateLabel(value, timezone);
      list.appendChild(item);
    });
    if (!list.childElementCount) {
      const empty = document.createElement("span");
      empty.className = "watchers-muted";
      empty.textContent = "No preview available.";
      list.appendChild(empty);
    }
    wrap.appendChild(list);
  }
  return wrap;
}
function _updateWatcherPreviewView() {
  const current = document.querySelector(".watchers-preview");
  if (current) current.replaceWith(_watcherPreviewNode());
}
function _renderWatcherPreview(parent) {
  parent.appendChild(_watcherPreviewNode());
}
function _renderWatcherForm(parent, watcher) {
  const draft = _watchersState.draft || _watcherDraftFromWatcher(watcher);
  const form = document.createElement("form");
  form.className = "watchers-form";
  form.id = "watchers-form";
  const labelInput = _watcherInput(draft.label, {
    id: "watchers-label-input",
    autocomplete: "off",
    maxlength: "120"
  });
  const baselineInput = _watcherInput(draft.baseline_run_id, {
    id: "watchers-baseline-input",
    autocomplete: "off"
  });
  if (watcher) {
    baselineInput.readOnly = true;
  }
  const commandInput = document.createElement("textarea");
  commandInput.id = "watchers-command-input";
  commandInput.className = "form-control watchers-command-input";
  commandInput.value = draft.command_text;
  commandInput.rows = 3;
  commandInput.spellcheck = false;
  commandInput.placeholder = "Command to run for the first baseline and future checks";
  const timezoneInput = _watcherTimezoneSelect(draft.timezone || _watcherDefaultTimezone());
  const projectInput = _watcherProjectSelect(draft.project_id || "");
  const cronInput = _watcherInput(draft.cron_expr || WATCHERS_DEFAULT_CRON, {
    id: "watchers-cron-input",
    autocomplete: "off",
    required: "required"
  });
  form.append(
    _watcherFormField("Label", labelInput),
    _watcherFormField("Project", projectInput)
  );
  const baselineMode = document.createElement("div");
  baselineMode.className = "watchers-field watchers-cadence-field";
  const baselineModeLabel = document.createElement("span");
  baselineModeLabel.className = "watchers-field-label";
  baselineModeLabel.textContent = "Baseline";
  const baselineModeControls = document.createElement("div");
  baselineModeControls.className = "watchers-cadence-controls tab-strip";
  baselineModeControls.setAttribute("role", "radiogroup");
  baselineModeControls.setAttribute("aria-label", "Watcher baseline mode");
  [
    ["first_run", "First run"],
    ["existing_run", "Existing run"]
  ].forEach(([mode, label]) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "tab-strip-item watchers-baseline-mode-btn";
    btn.dataset.watcherBaselineMode = mode;
    btn.setAttribute("role", "radio");
    btn.setAttribute("aria-checked", draft.baseline_mode === mode ? "true" : "false");
    if (draft.baseline_mode === mode) btn.classList.add("is-active");
    btn.textContent = label;
    if (watcher) btn.disabled = true;
    _bindWatcherPressable(btn, () => {
      if (watcher) return;
      _watchersState.formDirty = true;
      _setWatcherBaselineMode(mode);
    });
    baselineModeControls.appendChild(btn);
  });
  baselineMode.append(baselineModeLabel, baselineModeControls);
  form.append(
    baselineMode,
    _watcherFormField("Baseline run", baselineInput, {
      helpLabel: "How to choose a watcher baseline run",
      helpText: [
        "Use First run to let the watcher capture its first successful check as the baseline.",
        "Use Existing run when you already have a completed run to compare future checks against.",
        "To fill it automatically, open a completed external run from History and choose Actions,",
        "then Create watcher from this baseline. You can also paste a run ID from Run Details",
        "after choosing Actions, then Copy run ID."
      ].join(" ")
    }),
    _watcherFormField("Command", commandInput)
  );
  const cadence = document.createElement("div");
  cadence.className = "watchers-field watchers-cadence-field";
  const cadenceLabel = document.createElement("span");
  cadenceLabel.className = "watchers-field-label";
  cadenceLabel.textContent = "Cadence";
  const cadenceControls = document.createElement("div");
  cadenceControls.className = "watchers-cadence-controls tab-strip";
  cadenceControls.setAttribute("role", "radiogroup");
  cadenceControls.setAttribute("aria-label", "Watcher cadence");
  [
    ...WATCHERS_CADENCE_PRESETS,
    ["custom", "Custom cron"]
  ].forEach(([preset, label]) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "tab-strip-item watchers-cadence-btn";
    btn.dataset.watcherPreset = preset;
    btn.setAttribute("role", "radio");
    btn.setAttribute("aria-checked", draft.cadence_preset === preset ? "true" : "false");
    if (draft.cadence_preset === preset) btn.classList.add("is-active");
    btn.textContent = label;
    _bindWatcherPressable(btn, () => {
      _watchersState.formDirty = true;
      _setWatcherCadencePreset(preset);
      _loadWatcherPreview({ immediate: true }).catch(() => {
      });
    });
    cadenceControls.appendChild(btn);
  });
  cadence.append(cadenceLabel, cadenceControls);
  form.appendChild(cadence);
  form.append(
    _watcherFormField("Cron", cronInput),
    _watcherFormField("Timezone", timezoneInput)
  );
  const options = document.createElement("div");
  options.className = "watchers-options";
  [
    ["watchers-enabled-input", "Enabled", draft.enabled !== false],
    ["watchers-suppress-removals-input", "Ignore removals", draft.suppress_removals],
    ["watchers-metadata-input", "Notify on metadata changes", draft.notify_metadata_changes]
  ].forEach(([id, label, checked]) => {
    const option = document.createElement("label");
    option.className = "watchers-check-row";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.id = id;
    input.checked = !!checked;
    const text = document.createElement("span");
    text.textContent = label;
    option.append(input, text);
    options.appendChild(option);
  });
  form.appendChild(options);
  const policy = document.createElement("div");
  policy.className = "watchers-policy";
  const repeatedInput = _watcherInput(String(draft.alert_after_repeated_changes || 1), {
    id: "watchers-repeated-input",
    min: "1",
    max: "10",
    type: "number"
  });
  const patternsInput = document.createElement("textarea");
  patternsInput.id = "watchers-ignore-patterns-input";
  patternsInput.className = "form-control watchers-command-input";
  patternsInput.rows = 3;
  patternsInput.spellcheck = false;
  patternsInput.placeholder = "One line pattern per row";
  patternsInput.value = draft.ignore_line_patterns || "";
  const signalControls = document.createElement("div");
  signalControls.className = "watchers-policy-signals";
  [
    ["findings", "Findings"],
    ["entities", "Entities"],
    ["ports", "Ports"]
  ].forEach(([value, label]) => {
    const row = document.createElement("label");
    row.className = "watchers-check-row";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.dataset.watcherSignalClass = value;
    input.checked = (draft.alert_signal_classes || []).includes(value);
    const text = document.createElement("span");
    text.textContent = label;
    row.append(input, text);
    signalControls.appendChild(row);
  });
  policy.append(
    _watcherFormField("Repeated changes", repeatedInput),
    _watcherFormField("Ignore lines", patternsInput),
    _watcherFormField("Alert signals", signalControls)
  );
  form.appendChild(policy);
  _renderWatcherPreview(form);
  const actions = document.createElement("div");
  actions.className = "watchers-detail-actions";
  const saveBtn = document.createElement("button");
  saveBtn.type = "submit";
  saveBtn.className = "btn btn-primary btn-compact";
  saveBtn.disabled = _watchersState.saving;
  saveBtn.textContent = watcher ? "Save" : "Create";
  actions.appendChild(saveBtn);
  if (watcher) {
    const toggleBtn = document.createElement("button");
    toggleBtn.type = "button";
    toggleBtn.className = "btn btn-secondary btn-compact";
    toggleBtn.dataset.watcherAction = watcher.state === "paused" ? "resume" : "pause";
    toggleBtn.textContent = watcher.state === "paused" ? "Resume" : "Pause";
    _bindWatcherPressable(toggleBtn, () => _activateWatcherAction(toggleBtn.dataset.watcherAction));
    const runBtn = document.createElement("button");
    runBtn.type = "button";
    runBtn.className = "btn btn-secondary btn-compact";
    runBtn.dataset.watcherAction = "run-now";
    runBtn.textContent = "Run now";
    _bindWatcherPressable(runBtn, () => _activateWatcherAction("run-now"));
    const acceptBtn = document.createElement("button");
    acceptBtn.type = "button";
    acceptBtn.className = "btn btn-secondary btn-compact";
    acceptBtn.dataset.watcherAction = "accept-baseline";
    acceptBtn.disabled = !watcher.last_run_id;
    acceptBtn.textContent = "Accept baseline";
    _bindWatcherPressable(acceptBtn, () => _activateWatcherAction("accept-baseline"));
    const deleteBtn = document.createElement("button");
    deleteBtn.type = "button";
    deleteBtn.className = "btn btn-ghost btn-compact";
    deleteBtn.dataset.watcherAction = "delete";
    deleteBtn.textContent = "Delete";
    _bindWatcherPressable(deleteBtn, () => _activateWatcherAction("delete"));
    actions.append(toggleBtn, runBtn, acceptBtn, deleteBtn);
  }
  form.appendChild(actions);
  parent.appendChild(form);
  _setWatcherBaselineMode(draft.baseline_mode || "first_run", form);
}
function _collectWatcherDraft(form = document.getElementById("watchers-form")) {
  const root = form || document;
  const preset = root.querySelector?.(".watchers-cadence-btn.is-active")?.dataset.watcherPreset || "hourly";
  const baselineMode = root.querySelector?.(".watchers-baseline-mode-btn.is-active")?.dataset.watcherBaselineMode || "first_run";
  return {
    label: String(root.querySelector?.("#watchers-label-input")?.value || "").trim(),
    project_id: String(root.querySelector?.("#watchers-project-input")?.value || "").trim(),
    baseline_mode: baselineMode,
    baseline_run_id: baselineMode === "existing_run" ? String(root.querySelector?.("#watchers-baseline-input")?.value || "").trim() : "",
    command: String(root.querySelector?.("#watchers-command-input")?.value || "").trim(),
    cadence_preset: preset === "custom" ? "" : preset,
    cron_expr: String(root.querySelector?.("#watchers-cron-input")?.value || WATCHERS_DEFAULT_CRON).trim() || WATCHERS_DEFAULT_CRON,
    timezone: String(root.querySelector?.("#watchers-timezone-input")?.value || _watcherDefaultTimezone()).trim(),
    enabled: !!root.querySelector?.("#watchers-enabled-input")?.checked,
    options: {
      suppress_removals: !!root.querySelector?.("#watchers-suppress-removals-input")?.checked,
      notify_metadata_changes: !!root.querySelector?.("#watchers-metadata-input")?.checked
    },
    policy: _normalizeWatcherPolicyDraft({
      ignore_line_patterns: String(root.querySelector?.("#watchers-ignore-patterns-input")?.value || ""),
      alert_after_repeated_changes: Number(root.querySelector?.("#watchers-repeated-input")?.value || 1),
      alert_signal_classes: [...root.querySelectorAll?.("[data-watcher-signal-class]:checked") || []].map((input) => input.dataset.watcherSignalClass)
    })
  };
}
function _syncWatcherDraftFromForm() {
  const data = _collectWatcherDraft();
  _watchersState.draft = {
    id: _watchersState.draft?.id || _watchersState.selectedId || "",
    label: data.label,
    project_id: data.project_id,
    baseline_mode: data.baseline_mode,
    baseline_run_id: data.baseline_run_id,
    command_text: data.command,
    cadence_preset: data.cadence_preset || "custom",
    cron_expr: data.cron_expr || WATCHERS_DEFAULT_CRON,
    timezone: data.timezone || _watcherDefaultTimezone(),
    enabled: data.enabled,
    suppress_removals: !!data.options.suppress_removals,
    notify_metadata_changes: !!data.options.notify_metadata_changes,
    ignore_line_patterns: data.policy.ignore_line_patterns.join("\n"),
    alert_after_repeated_changes: data.policy.alert_after_repeated_changes,
    alert_signal_classes: data.policy.alert_signal_classes
  };
}
async function _loadWatcherPreview({ immediate = false } = {}) {
  _cancelWatcherPreview();
  const run = async () => {
    const form = document.getElementById("watchers-form");
    if (!form) return;
    _syncWatcherDraftFromForm();
    const draft = _watchersState.draft || {};
    const params = new URLSearchParams();
    if (draft.cadence_preset && draft.cadence_preset !== "custom") params.set("cadence_preset", draft.cadence_preset);
    else params.set("cron", draft.cron_expr || WATCHERS_DEFAULT_CRON);
    params.set("tz", draft.timezone || _watcherDefaultTimezone());
    const controller = typeof AbortController === "function" ? new AbortController() : null;
    _watchersState.previewController = controller;
    _watchersState.preview = { ..._watchersState.preview, loading: true, error: "" };
    _updateWatcherPreviewView();
    try {
      const data = await _watcherJson(`/schedules/preview?${params.toString()}`, {
        cache: "no-store",
        signal: controller?.signal
      });
      const cronExpr = String(data.cron_expr || "").trim();
      if (cronExpr && draft.cadence_preset && draft.cadence_preset !== "custom") {
        const cronInput = form.querySelector?.("#watchers-cron-input");
        if (cronInput) cronInput.value = cronExpr;
        _watchersState.draft = { ...draft, cron_expr: cronExpr };
      }
      _watchersState.preview = {
        loading: false,
        error: "",
        next_fires: Array.isArray(data.next_fires) ? data.next_fires : [],
        cron_expr: cronExpr || draft.cron_expr || WATCHERS_DEFAULT_CRON,
        timezone: data.timezone || draft.timezone || _watcherDefaultTimezone()
      };
    } catch (err) {
      if (err?.name === "AbortError") return;
      _watcherClientError("failed to preview watcher cadence", err);
      _watchersState.preview = {
        ..._watchersState.preview,
        loading: false,
        error: err?.message || "Could not preview cadence",
        next_fires: []
      };
    } finally {
      if (_watchersState.previewController === controller) {
        _watchersState.previewController = null;
      }
    }
    _updateWatcherPreviewView();
  };
  if (immediate) await run();
  else _watchersState.previewTimer = window.setTimeout(run, 250);
}
function _watcherSummaryCounts(summary = {}) {
  const rows = [];
  Object.entries(summary || {}).forEach(([key, value]) => {
    if (key === "classifier" || key.endsWith("s") || typeof value === "object") return;
    if (!/_count$|^hunks_omitted$|^lines_omitted$/.test(key)) return;
    rows.push([key.replace(/_/g, " "), value]);
  });
  return rows;
}
function _watcherListItemText(item) {
  if (!item || typeof item !== "object") return String(item || "");
  return item.title || item.raw_line || item.key || item.host || item.field || item.id || JSON.stringify(item);
}
function _watcherListItemMeta(item) {
  if (!item || typeof item !== "object") return "";
  if (item.before || item.after) {
    const before = typeof item.before === "object" ? JSON.stringify(item.before) : String(item.before || "");
    const after = typeof item.after === "object" ? JSON.stringify(item.after) : String(item.after || "");
    return `${before} -> ${after}`;
  }
  return [
    item.service || "",
    item.state || "",
    item.severity || "",
    item.review_state || "",
    item.value || ""
  ].filter(Boolean).join(" - ");
}
function _renderWatcherSignalSection(title, items, sign) {
  const safeItems = Array.isArray(items) ? items : [];
  const section = document.createElement("details");
  section.className = "history-compare-lines history-compare-object-section";
  section.open = true;
  const summary = document.createElement("summary");
  summary.textContent = `${title} (${safeItems.length})`;
  section.appendChild(summary);
  safeItems.forEach((item) => {
    const row = document.createElement("div");
    row.className = "history-compare-line history-compare-object-row";
    const mark = document.createElement("span");
    mark.className = sign === "+" ? "history-compare-line-added" : "history-compare-line-removed";
    mark.textContent = sign;
    const content = document.createElement("div");
    content.className = "history-compare-object-content";
    const primary = document.createElement("code");
    primary.textContent = _watcherListItemText(item);
    content.appendChild(primary);
    const meta = _watcherListItemMeta(item);
    if (meta) {
      const metaEl = document.createElement("div");
      metaEl.className = "history-compare-object-meta";
      metaEl.textContent = meta;
      content.appendChild(metaEl);
    }
    row.append(mark, content);
    section.appendChild(row);
  });
  return section;
}
function _watcherInt(value) {
  const numeric = Number(value || 0);
  return Number.isFinite(numeric) ? numeric : 0;
}
function _watcherFireSummaryText(fire = {}) {
  const summary = fire.diff_summary && typeof fire.diff_summary === "object" ? fire.diff_summary : {};
  const classifier = String(summary.classifier || "").trim();
  if (classifier === "findings") {
    const added = _watcherInt(summary.added_finding_count);
    const removed = _watcherInt(summary.removed_finding_count) - _watcherInt(summary.suppressed_removed_finding_count);
    const unchanged = _watcherInt(summary.unchanged_finding_count);
    if (!added && !removed) return "No finding changes";
    return `Findings: +${added.toLocaleString()}, -${Math.max(0, removed).toLocaleString()}, unchanged ${unchanged.toLocaleString()}`;
  }
  if (classifier === "ports") {
    const added = _watcherInt(summary.added_port_count);
    const removed = Math.max(0, _watcherInt(summary.removed_port_count) - _watcherInt(summary.suppressed_removed_port_count));
    const changed = _watcherInt(summary.changed_port_count);
    if (!added && !removed && !changed) return "No port changes";
    return `Ports: +${added.toLocaleString()}, -${removed.toLocaleString()}, changed ${changed.toLocaleString()}`;
  }
  if (classifier === "hosts") {
    const added = _watcherInt(summary.added_host_count);
    const removed = Math.max(0, _watcherInt(summary.removed_host_count) - _watcherInt(summary.suppressed_removed_host_count));
    if (!added && !removed) return "No host changes";
    return `Hosts: +${added.toLocaleString()}, -${removed.toLocaleString()}`;
  }
  if (classifier === "tls") {
    const changed = _watcherInt(summary.changed_tls_field_count);
    return changed ? `TLS fields changed: ${changed.toLocaleString()}` : "No TLS field changes";
  }
  if (classifier === "baseline" || summary.baseline_created) return "Baseline captured from first run";
  const counts = _watcherSummaryCounts(summary).filter(([, value]) => Number(value || 0) > 0).slice(0, 3);
  if (counts.length) {
    const prefix = classifier ? `${classifier[0].toUpperCase()}${classifier.slice(1)}: ` : "";
    return prefix + counts.map(([label, value]) => `${label} ${Number(value || 0).toLocaleString()}`).join(", ");
  }
  if (fire.diff_kind === "none") return "No changes";
  return classifier ? `${classifier} diff` : "";
}
function _renderWatcherDiffSummary(summary = {}, { kind = "", truncated = false, titleText = "Last diff" } = {}) {
  const wrap = document.createElement("div");
  wrap.className = "watchers-diff history-compare-result";
  const header = document.createElement("div");
  header.className = "watchers-section-header";
  const title = document.createElement("h3");
  title.textContent = titleText;
  const badge = document.createElement("span");
  badge.className = `badge ${_watcherDiffTone(kind)}`;
  badge.textContent = kind || "none";
  header.append(title, badge);
  wrap.appendChild(header);
  if (!summary || !Object.keys(summary).length) {
    const empty = document.createElement("div");
    empty.className = "watchers-empty";
    empty.textContent = "No diff summary yet.";
    wrap.appendChild(empty);
    return wrap;
  }
  const metrics = document.createElement("div");
  metrics.className = "history-compare-metrics watchers-diff-metrics";
  const classifier = String(summary.classifier || "unknown");
  const classifierCell = _watcherCompareMetricCell("Classifier", classifier);
  if (classifierCell) {
    metrics.appendChild(classifierCell);
    _watcherSummaryCounts(summary).forEach(([label, value]) => {
      const metricCell = _watcherCompareMetricCell(label, Number(value || 0).toLocaleString(), Number(value || 0) ? "is-changed" : "");
      if (metricCell) metrics.appendChild(metricCell);
    });
  } else {
    const fallbackCell = document.createElement("div");
    fallbackCell.className = "history-compare-metric";
    fallbackCell.textContent = `Classifier: ${classifier}`;
    metrics.appendChild(fallbackCell);
  }
  wrap.appendChild(metrics);
  if (truncated || summary.truncated) {
    const note = document.createElement("div");
    note.className = "watchers-alert";
    note.textContent = "Some diff details were capped by compare limits.";
    wrap.appendChild(note);
  }
  [
    ["Added", summary.added_ports || summary.added_hosts || summary.added_findings || [], "+"],
    ["Removed", summary.removed_ports || summary.removed_hosts || summary.removed_findings || [], "-"],
    ["Changed", summary.changed_ports || summary.changed_tls_fields || summary.changed_findings || [], "+"]
  ].forEach(([titleText2, items, sign]) => {
    if (Array.isArray(items) && items.length) wrap.appendChild(_renderWatcherSignalSection(titleText2, items, sign));
  });
  return wrap;
}
function _renderWatcherFires(parent, watcher) {
  if (!watcher) return;
  const section = document.createElement("div");
  section.className = "watchers-fires";
  const header = document.createElement("div");
  header.className = "watchers-section-header";
  const title = document.createElement("h3");
  title.textContent = "Fire audit";
  const refresh = document.createElement("button");
  refresh.type = "button";
  refresh.className = "btn btn-ghost btn-compact";
  refresh.dataset.watcherAction = "refresh-fires";
  refresh.textContent = "Refresh";
  _bindWatcherPressable(refresh, () => _activateWatcherAction("refresh-fires"));
  header.append(title, refresh);
  section.appendChild(header);
  if (_watchersState.loadingFires) {
    const loading = document.createElement("div");
    loading.className = "watchers-empty";
    loading.textContent = "Loading fires...";
    section.appendChild(loading);
  } else if (!_watchersState.fires.length) {
    const empty = document.createElement("div");
    empty.className = "watchers-empty";
    empty.textContent = "No fire audit rows yet.";
    section.appendChild(empty);
  } else {
    const rows = document.createElement("div");
    rows.className = "watchers-fire-list";
    _watchersState.fires.forEach((fire) => {
      const row = document.createElement("div");
      row.className = "watchers-fire-row";
      const main = document.createElement("div");
      main.className = "watchers-fire-main";
      const kind = document.createElement("span");
      kind.className = `badge ${_watcherDiffTone(fire.diff_kind)} watchers-fire-kind`;
      kind.textContent = fire.diff_kind || "none";
      const date = document.createElement("span");
      date.className = "watchers-fire-date";
      date.textContent = _watcherDateLabel(fire.created);
      const state = document.createElement("span");
      state.className = "watchers-muted";
      state.textContent = fire.state_at_fire || "";
      main.append(kind, date, state);
      row.appendChild(main);
      const summary = document.createElement("div");
      summary.className = "watchers-fire-summary";
      summary.textContent = _watcherFireSummaryText(fire);
      row.appendChild(summary);
      if (fire.diff_summary && typeof fire.diff_summary === "object" && Object.keys(fire.diff_summary).length) {
        const details = document.createElement("details");
        details.className = "watchers-fire-details";
        const detailsSummary = document.createElement("summary");
        detailsSummary.textContent = "Diff details";
        details.appendChild(detailsSummary);
        details.appendChild(_renderWatcherDiffSummary(fire.diff_summary, {
          kind: fire.diff_kind,
          truncated: fire.truncated,
          titleText: "Fire diff"
        }));
        row.appendChild(details);
      }
      if (fire.run_id) {
        const actions = document.createElement("div");
        actions.className = "watchers-fire-actions";
        if (fire.baseline_run_id && fire.baseline_run_id !== fire.run_id) {
          const compare = document.createElement("button");
          compare.type = "button";
          compare.className = "btn btn-primary btn-compact";
          compare.textContent = "Compare";
          _bindWatcherPressable(compare, () => _compareWatcherFireToBaseline(fire));
          actions.appendChild(compare);
        }
        const open = document.createElement("button");
        open.type = "button";
        open.className = "btn btn-secondary btn-compact";
        open.dataset.watcherRunId = fire.run_id;
        open.textContent = "Open run";
        _bindWatcherPressable(open, () => _openWatcherRun(fire.run_id || ""));
        actions.appendChild(open);
        row.appendChild(actions);
      }
      rows.appendChild(row);
    });
    section.appendChild(rows);
  }
  const meta = _watchersState.firesMeta || {};
  if (Number(meta.total || 0) > Number(meta.limit || WATCHERS_FIRES_LIMIT)) {
    const pager = document.createElement("div");
    pager.className = "watchers-pager";
    const prev = document.createElement("button");
    prev.type = "button";
    prev.className = "btn btn-secondary btn-compact";
    prev.disabled = Number(meta.offset || 0) <= 0;
    prev.textContent = "Prev";
    _bindWatcherPressable(prev, () => _changeWatcherFiresPage("prev"));
    const label = document.createElement("span");
    label.className = "watchers-muted";
    const start = Number(meta.offset || 0) + 1;
    const end = Math.min(Number(meta.total || 0), Number(meta.offset || 0) + _watchersState.fires.length);
    label.textContent = `${start}-${end} / ${Number(meta.total || 0).toLocaleString()}`;
    const next = document.createElement("button");
    next.type = "button";
    next.className = "btn btn-secondary btn-compact";
    next.disabled = !meta.has_more;
    next.textContent = "Next";
    _bindWatcherPressable(next, () => _changeWatcherFiresPage("next"));
    pager.append(prev, label, next);
    section.appendChild(pager);
  }
  parent.appendChild(section);
}
function _renderWatchersDetail() {
  const { detail } = _watcherEls();
  if (!detail) return;
  detail.replaceChildren();
  const watcher = _watcherSelected();
  const isNew = _watchersState.mode === "new";
  const root = document.createElement("div");
  root.className = "watchers-detail-inner";
  if (_watchersState.mode === "missing") {
    const missing = document.createElement("div");
    missing.className = "watchers-empty watchers-detail-empty";
    missing.textContent = _watchersState.missingWatcherId ? `Watcher ${_watchersState.missingWatcherId} was not found. It may have been deleted.` : "Watcher was not found. It may have been deleted.";
    root.appendChild(missing);
    detail.appendChild(root);
    return;
  }
  if (!watcher && !isNew) {
    const empty = document.createElement("div");
    empty.className = "watchers-empty watchers-detail-empty";
    empty.textContent = "Select or create a watcher.";
    root.appendChild(empty);
    detail.appendChild(root);
    return;
  }
  const header = document.createElement("div");
  header.className = "watchers-detail-header";
  const title = document.createElement("div");
  title.className = "watchers-detail-title";
  title.textContent = isNew ? "New watcher" : _watcherTitle(watcher);
  header.appendChild(title);
  if (watcher) {
    const status = document.createElement("span");
    status.className = `badge ${_watcherStateTone(watcher)}`;
    status.textContent = _watcherStateLabel(watcher);
    header.appendChild(status);
  }
  root.appendChild(header);
  if (watcher?.state_reason || watcher?.last_error) {
    const alert = document.createElement("div");
    alert.className = "watchers-alert";
    alert.textContent = watcher.last_error || watcher.state_reason || "";
    root.appendChild(alert);
  }
  _renderWatcherForm(root, isNew ? null : watcher);
  if (watcher) {
    root.appendChild(_renderWatcherDiffSummary(watcher.last_diff_summary, {
      kind: watcher.state === "changed" ? "signal" : "",
      truncated: false
    }));
    _renderWatcherFires(root, watcher);
  }
  detail.appendChild(root);
}
function _renderWatchersModal() {
  _renderWatchersList();
  _renderWatchersDetail();
}
function _updateWatcherFiresView() {
  const watcher = _watcherSelected();
  if (!watcher) return;
  const current = document.querySelector(".watchers-fires");
  if (!current) return;
  const fragment = document.createElement("div");
  _renderWatcherFires(fragment, watcher);
  const next = fragment.firstElementChild;
  if (next) current.replaceWith(next);
}
async function _loadWatcherFires(watcherId, { offset = 0 } = {}) {
  if (!watcherId) return;
  _watchersState.loadingFires = true;
  _updateWatcherFiresView();
  try {
    const params = new URLSearchParams({
      limit: String(WATCHERS_FIRES_LIMIT),
      offset: String(Math.max(0, Number(offset || 0)))
    });
    const data = await _watcherJson(
      `/watchers/${encodeURIComponent(watcherId)}/fires?${params.toString()}`,
      { cache: "no-store" }
    );
    _watchersState.fires = Array.isArray(data.fires) ? data.fires : [];
    _watchersState.firesMeta = {
      limit: Number(data.limit || WATCHERS_FIRES_LIMIT),
      offset: Number(data.offset || 0),
      total: Number(data.total || 0),
      has_more: !!data.has_more
    };
  } catch (err) {
    _watchersState.fires = [];
    _watchersState.firesMeta = { limit: WATCHERS_FIRES_LIMIT, offset: 0, total: 0, has_more: false };
    _watcherClientError("failed to load watcher fires", err);
    _watcherToast(err?.message || "Could not load watcher fires", "error");
  } finally {
    _watchersState.loadingFires = false;
    _updateWatcherFiresView();
  }
}
async function _loadWatcherProjects() {
  try {
    const data = await _watcherJson("/projects?include_archived=1&include_counts=0&limit=100&offset=0", { cache: "no-store" });
    _watchersState.projects = Array.isArray(data.projects) ? data.projects : [];
  } catch (err) {
    _watchersState.projects = [];
    _watcherClientError("failed to load watcher project choices", err);
  }
}
async function refreshWatchersModal({ selectId = "", baselineRun = null, projectId = "", newWatcher = false } = {}) {
  _watchersState.loading = true;
  _renderWatchersModal();
  try {
    await _loadWatcherProjects();
    const data = await _watcherJson("/watchers", { cache: "no-store" });
    _watchersState.watchers = Array.isArray(data.watchers) ? data.watchers : [];
    _watcherEmitUiEvent("app:watchers-rendered", { items: _watchersState.watchers.slice() });
    _watchersState.missingWatcherId = "";
    const requestedId = String(selectId || "");
    const currentId = String(selectId || _watchersState.selectedId || "");
    const hasCurrent = _watchersState.watchers.some((item) => String(item.id || "") === currentId);
    if (requestedId && !hasCurrent) {
      _watchersState.mode = "missing";
      _watchersState.selectedId = "";
      _watchersState.missingWatcherId = requestedId;
      _watchersState.cleanDraft = null;
      _watchersState.formDirty = false;
    } else if (baselineRun || projectId || newWatcher) {
      _watchersState.mode = "new";
      _watchersState.selectedId = "";
      _watchersState.draft = _watcherDraftFromWatcher(null, baselineRun);
      _watchersState.draft.project_id = String(projectId || _watchersState.draft.project_id || "").trim();
      _watchersState.cleanDraft = null;
      _watchersState.formDirty = false;
    } else {
      const fallbackId = _watchersState.watchers[0]?.id || "";
      _watchersState.selectedId = hasCurrent ? currentId : fallbackId;
      _watchersState.mode = _watchersState.selectedId ? "view" : "view";
      _watchersState.draft = _watchersState.selectedId ? _watcherDraftFromWatcher(_watcherSelected()) : null;
      _markWatcherClean(_watchersState.draft);
    }
    _watchersState.fires = [];
  } catch (err) {
    _watcherClientError("failed to load watchers", err);
    _watcherToast(err?.message || "Could not load watchers", "error");
  } finally {
    _watchersState.loading = false;
    _renderWatchersModal();
    _focusWatchersModal();
    await _loadWatcherPreview({ immediate: true });
    if (_watchersState.selectedId) await _loadWatcherFires(_watchersState.selectedId);
  }
}
async function openWatchersModal(options = {}) {
  const { overlay } = _watcherEls();
  if (!overlay) return;
  _watcherCloseMajorOverlays();
  _setWatchersOpen(true);
  const baselineRun = options.baselineRun || (options.baselineRunId ? { id: options.baselineRunId, command: options.command || "" } : null);
  const projectId = String(options.projectId || options.project_id || "").trim();
  const newWatcher = !!options.newWatcher || !!projectId;
  _watchersState.mode = baselineRun || newWatcher ? "new" : "view";
  _watchersState.selectedId = String(options.watcherId || "");
  _watchersState.draft = baselineRun || newWatcher ? _watcherDraftFromWatcher(null, baselineRun) : null;
  if (_watchersState.draft && projectId) _watchersState.draft.project_id = projectId;
  _watchersState.formDirty = false;
  await refreshWatchersModal({
    selectId: options.watcherId || "",
    baselineRun,
    projectId,
    newWatcher
  });
}
async function _saveWatcherForm(event) {
  event?.preventDefault?.();
  const data = _collectWatcherDraft();
  const selected = _watcherSelected();
  const isNew = _watchersState.mode === "new" || !selected;
  if (isNew && data.baseline_mode === "existing_run" && !data.baseline_run_id) {
    _watcherToast("Baseline run is required", "error");
    return;
  }
  if (isNew && data.baseline_mode === "first_run" && !data.command) {
    _watcherToast("Command is required for first-run baselines", "error");
    return;
  }
  _watchersState.saving = true;
  _renderWatchersDetail();
  try {
    const url = isNew ? "/watchers" : `/watchers/${encodeURIComponent(selected.id)}`;
    const method = isNew ? "POST" : "PATCH";
    const payload = { ...data };
    if (!payload.command) delete payload.command;
    const response = await _watcherJson(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const watcher = response.watcher || {};
    _watcherToast(isNew ? "Watcher created" : "Watcher saved");
    _watchersState.mode = "view";
    await refreshWatchersModal({ selectId: watcher.id || selected?.id || "" });
    _watcherLoadAutocompleteHints().catch(() => {
    });
  } catch (err) {
    _watcherClientError(isNew ? "failed to create watcher" : "failed to update watcher", err);
    _watcherToast(err?.message || "Could not save watcher", "error");
  } finally {
    _watchersState.saving = false;
    _renderWatchersDetail();
  }
}
async function _deleteSelectedWatcher(watcher) {
  if (!watcher) return;
  let confirmed = true;
  const choice = await _watcherShowConfirm({
    body: `Delete watcher "${_watcherTitle(watcher)}"?`,
    tone: "danger",
    actions: [
      { id: "cancel", label: "Cancel", role: "cancel" },
      { id: "delete", label: "Delete", role: "destructive" }
    ]
  });
  if (choice !== null) confirmed = choice === "delete";
  if (!confirmed) return;
  try {
    await _watcherJson(`/watchers/${encodeURIComponent(watcher.id)}`, { method: "DELETE" });
    _watcherToast("Watcher deleted");
    _watchersState.selectedId = "";
    await refreshWatchersModal();
    _watcherLoadAutocompleteHints().catch(() => {
    });
  } catch (err) {
    _watcherClientError("failed to delete watcher", err);
    _watcherToast(err?.message || "Could not delete watcher", "error");
  }
}
async function _patchSelectedWatcher(watcher, updates, successMessage) {
  if (!watcher) return;
  try {
    const response = await _watcherJson(`/watchers/${encodeURIComponent(watcher.id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates)
    });
    _watcherToast(successMessage);
    await refreshWatchersModal({ selectId: response.watcher?.id || watcher.id });
    _watcherLoadAutocompleteHints().catch(() => {
    });
  } catch (err) {
    _watcherClientError("failed to update watcher", err);
    _watcherToast(err?.message || "Could not update watcher", "error");
  }
}
async function _runSelectedWatcher(watcher) {
  if (!watcher) return;
  try {
    const data = await _watcherJson(`/watchers/${encodeURIComponent(watcher.id)}/run-now`, { method: "POST" });
    _watcherToast(data.status === "fired" ? "Watcher fired" : "Watcher skipped");
    await refreshWatchersModal({ selectId: watcher.id });
    _watcherRefreshHistoryPanel();
  } catch (err) {
    _watcherClientError("failed to run watcher now", err);
    _watcherToast(err?.message || "Could not fire watcher", "error");
  }
}
async function _acceptSelectedWatcherBaseline(watcher) {
  if (!watcher) return;
  let confirmed = true;
  const choice = await _watcherShowConfirm({
    body: `Accept the latest watcher run as the new baseline for "${_watcherTitle(watcher)}"?`,
    tone: "warning",
    actions: [
      { id: "cancel", label: "Cancel", role: "cancel" },
      { id: "accept", label: "Accept baseline", role: "primary" }
    ]
  });
  if (choice !== null) confirmed = choice === "accept";
  if (!confirmed) return;
  try {
    const response = await _watcherJson(`/watchers/${encodeURIComponent(watcher.id)}/accept-baseline`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: watcher.last_run_id || "" })
    });
    _watcherToast("Baseline accepted");
    await refreshWatchersModal({ selectId: response.watcher?.id || watcher.id });
  } catch (err) {
    _watcherClientError("failed to accept watcher baseline", err);
    _watcherToast(err?.message || "Could not accept baseline", "error");
  }
}
function _activateWatcherAction(value) {
  const watcher = _watcherSelected();
  if (value === "delete") _deleteSelectedWatcher(watcher);
  if (value === "pause") _patchSelectedWatcher(watcher, { pause: true, reason: "operator paused" }, "Watcher paused");
  if (value === "resume") _patchSelectedWatcher(watcher, { resume: true }, "Watcher resumed");
  if (value === "run-now") _runSelectedWatcher(watcher);
  if (value === "accept-baseline") _acceptSelectedWatcherBaseline(watcher);
  if (value === "refresh-fires") _loadWatcherFires(watcher?.id || "").catch(() => {
  });
}
function _changeWatcherFiresPage(direction) {
  const meta = _watchersState.firesMeta || {};
  const nextOffset = direction === "next" ? Number(meta.offset || 0) + Number(meta.limit || WATCHERS_FIRES_LIMIT) : Math.max(0, Number(meta.offset || 0) - Number(meta.limit || WATCHERS_FIRES_LIMIT));
  _loadWatcherFires(_watchersState.selectedId, { offset: nextOffset }).catch(() => {
  });
}
async function _compareWatcherFireToBaseline(fire = {}) {
  const baselineRunId = String(fire?.baseline_run_id || "").trim();
  const runId = String(fire?.run_id || "").trim();
  if (!baselineRunId || !runId || baselineRunId === runId) {
    _watcherToast("Choose a watcher fire with a baseline and completed run to compare.", "error");
    return;
  }
  const closed = await closeWatchersModal({ refocus: false });
  if (!closed) return;
  try {
    await _watcherFetchAndRenderHistoryComparison(baselineRunId, runId);
  } catch (err) {
    _watcherClientError("failed to compare watcher fire to baseline", err);
    _watcherToast(err?.message || "Could not open run comparison", "error");
  }
}
async function _openWatcherRun(runId) {
  const closed = await closeWatchersModal({ refocus: false });
  if (!closed) return;
  _watcherOpenHistoryRunDetails(runId);
}
async function _selectWatcher(watcherId) {
  if (!await _confirmWatcherDiscardChanges()) return;
  _watchersState.mode = "view";
  _watchersState.selectedId = String(watcherId || "");
  _watchersState.draft = _watcherDraftFromWatcher(_watcherSelected());
  _markWatcherClean(_watchersState.draft);
  _watchersState.fires = [];
  _watchersState.missingWatcherId = "";
  _renderWatchersModal();
  _loadWatcherPreview({ immediate: true }).catch(() => {
  });
  _loadWatcherFires(_watchersState.selectedId).catch(() => {
  });
}
async function _newWatcher(baselineRun = null) {
  if (!await _confirmWatcherDiscardChanges()) return;
  _watchersState.mode = "new";
  _watchersState.selectedId = "";
  _watchersState.draft = _watcherDraftFromWatcher(null, baselineRun);
  _watchersState.cleanDraft = null;
  _watchersState.formDirty = false;
  _watchersState.fires = [];
  _watchersState.missingWatcherId = "";
  _renderWatchersModal();
  _loadWatcherPreview({ immediate: true }).catch(() => {
  });
}
function _bindWatchersModal() {
  const { overlay, newBtn, refreshBtn } = _watcherEls();
  if (!overlay) return;
  if (overlay.dataset.watchersModalBound === "1") return;
  overlay.dataset.watchersModalBound = "1";
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) {
      closeWatchersModal();
      return;
    }
    if (!event.target.closest?.(".watchers-help-wrap")) _closeWatcherHelpCards();
    const close = event.target.closest?.(".watchers-close");
    if (close) {
      closeWatchersModal();
      return;
    }
    const run = event.target.closest?.("[data-watcher-run-id]");
    if (run && run.dataset.pressableBound !== "1") {
      _openWatcherRun(run.dataset.watcherRunId || "");
    }
  });
  overlay.addEventListener("input", (event) => {
    _markWatcherDirty(event);
    if (event.target?.id !== "watchers-cron-input") return;
    _setWatcherCadencePreset("custom");
    _loadWatcherPreview().catch(() => {
    });
  });
  overlay.addEventListener("change", (event) => {
    _markWatcherDirty(event);
    if (event.target?.id !== "watchers-timezone-input") return;
    _loadWatcherPreview().catch(() => {
    });
  });
  overlay.addEventListener("submit", (event) => {
    if (event.target && event.target.id === "watchers-form") _saveWatcherForm(event);
  });
  newBtn?.addEventListener("click", () => _newWatcher());
  refreshBtn?.addEventListener("click", async () => {
    if (await _confirmWatcherDiscardChanges()) refreshWatchersModal({ selectId: _watchersState.selectedId });
  });
  _watcherBindDismissible(overlay, {
    level: "modal",
    isOpen: isWatchersOverlayOpen,
    onClose: closeWatchersModal,
    closeButtons: overlay.querySelectorAll(".watchers-close, .sheet-grab")
  });
}
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", _bindWatchersModal);
else _bindWatchersModal();
export {
  closeWatchersModal,
  isWatchersOverlayOpen,
  openWatchersModal
};
