import {
  fetchAndRenderHistoryComparison
} from "./static-chunk-b3r3gqnm.090991bf6295.js";
import "./static-chunk-bckya4ml.45b6bfbd3abb.js";
import "./static-chunk-pmsn6ig7.f463bc01feed.js";
import {
  openHistoryRunDetails
} from "./static-chunk-d5lmyrso.0e0f134758a0.js";
import "./static-chunk-5ypwzub3.51f0198495c1.js";
import "./static-chunk-6sxirwn5.a08adec8fe31.js";
import "./static-chunk-dil5yyjg.6d28df9092db.js";
import "./static-chunk-raa54zvl.6edf423cfb6c.js";
import "./static-chunk-3jpzlov4.47e7ebc68e55.js";
import "./static-chunk-ylgcpl7n.752d37b456dc.js";
import {
  closeMajorOverlays,
  loadScheduleAutocompleteHints
} from "./static-chunk-n2vpqjbs.2f664fbfac6b.js";
import {
  showToast
} from "./static-chunk-poi5czx6.3f5c94749765.js";
import "./static-chunk-lxs2zdd2.87dc9e4c1317.js";
import {
  bindDismissible,
  bindPressable
} from "./static-chunk-fik64llj.1291b1f4f79b.js";
import "./static-chunk-yu6ty7m2.96c3ee208a44.js";
import {
  emitUiEvent,
  hasHistoryPanelHandler,
  refocusComposerAfterAction,
  refreshHistoryPanel,
  syncModalOverlayState
} from "./static-chunk-sgyzdmxn.7d1842f12a94.js";
import {
  getAppConfig
} from "./static-chunk-tym5o2af.a748583ae389.js";
import {
  apiFetch,
  hasRuntimeHandler,
  logClientError
} from "./static-chunk-i34eiczq.4bb950c346dc.js";
import "./static-chunk-m4e6ivjw.074a5c89d41e.js";
import "./static-chunk-y6zchygr.f5ddd7fe938a.js";

// app/static/js/features/schedules/schedules_modal.js
var SCHEDULES_DEFAULT_CRON = "0 * * * *";
var SCHEDULES_FIRES_LIMIT = 20;
var SCHEDULES_CADENCE_PRESETS = [
  ["hourly", "Every hour"],
  ["daily", "Daily"],
  ["weekly", "Weekly"]
];
var SCHEDULES_COMMON_TIMEZONES = [
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
var SCHEDULES_GLOBAL = typeof window !== "undefined" ? window : globalThis;
var _schedulesState = {
  schedules: [],
  selectedId: "",
  draft: null,
  mode: "view",
  fires: [],
  firesMeta: { limit: SCHEDULES_FIRES_LIMIT, offset: 0, total: 0, has_more: false },
  loading: false,
  loadingFires: false,
  saving: false,
  preview: { loading: false, error: "", next_fires: [], cron_expr: SCHEDULES_DEFAULT_CRON, timezone: _scheduleDefaultTimezone() },
  previewTimer: null,
  previewController: null,
  missingScheduleId: "",
  cleanDraft: null,
  formDirty: false,
  discardPromptOpen: false
};
function _scheduleAppConfig() {
  if (typeof getAppConfig === "function") return getAppConfig();
  return SCHEDULES_GLOBAL.APP_CONFIG || null;
}
function _scheduleApiFetch(...args) {
  const fetcher = (typeof hasRuntimeHandler === "function" && hasRuntimeHandler("apiFetch") && typeof apiFetch === "function" ? apiFetch : null) || (typeof SCHEDULES_GLOBAL.apiFetch === "function" ? SCHEDULES_GLOBAL.apiFetch : null);
  if (!fetcher) return Promise.reject(new Error("apiFetch is not available"));
  return fetcher(...args);
}
function _scheduleRefocusComposerAfterAction(options) {
  const refocus = typeof refocusComposerAfterAction === "function" ? refocusComposerAfterAction : typeof SCHEDULES_GLOBAL.refocusComposerAfterAction === "function" ? SCHEDULES_GLOBAL.refocusComposerAfterAction : null;
  if (refocus) refocus(options);
}
function _scheduleSyncModalOverlayState() {
  const sync = typeof syncModalOverlayState === "function" ? syncModalOverlayState : null;
  if (sync) sync();
}
function _scheduleShowConfirm(options) {
  const confirm = typeof SCHEDULES_GLOBAL.showConfirm === "function" ? SCHEDULES_GLOBAL.showConfirm : null;
  return confirm ? confirm(options) : Promise.resolve(null);
}
function _scheduleBindDismissible(overlay, options) {
  const bind = typeof bindDismissible === "function" ? bindDismissible : typeof SCHEDULES_GLOBAL.bindDismissible === "function" ? SCHEDULES_GLOBAL.bindDismissible : null;
  return bind ? bind(overlay, options) : null;
}
function _scheduleEmitUiEvent(name, detail) {
  const emit = typeof emitUiEvent === "function" ? emitUiEvent : typeof SCHEDULES_GLOBAL.emitUiEvent === "function" ? SCHEDULES_GLOBAL.emitUiEvent : null;
  if (emit) emit(name, detail);
}
function _scheduleOpenHistoryRunDetails(runId) {
  const open = typeof openHistoryRunDetails === "function" ? openHistoryRunDetails : typeof SCHEDULES_GLOBAL.openHistoryRunDetails === "function" ? SCHEDULES_GLOBAL.openHistoryRunDetails : null;
  if (open) open({ id: runId || "" });
}
function _scheduleFetchAndRenderHistoryComparison(...args) {
  const compare = typeof fetchAndRenderHistoryComparison === "function" ? fetchAndRenderHistoryComparison : typeof SCHEDULES_GLOBAL.fetchAndRenderHistoryComparison === "function" ? SCHEDULES_GLOBAL.fetchAndRenderHistoryComparison : null;
  if (!compare) return Promise.reject(new Error("Run comparison is not available."));
  return compare(...args);
}
function _scheduleLoadAutocompleteHints() {
  const load = typeof loadScheduleAutocompleteHints === "function" ? loadScheduleAutocompleteHints : typeof SCHEDULES_GLOBAL.loadScheduleAutocompleteHints === "function" ? SCHEDULES_GLOBAL.loadScheduleAutocompleteHints : null;
  return load ? load() : Promise.resolve();
}
function _scheduleEls() {
  return {
    overlay: document.getElementById("schedules-overlay"),
    list: document.getElementById("schedules-list"),
    detail: document.getElementById("schedules-detail"),
    count: document.getElementById("schedules-count"),
    newBtn: document.getElementById("schedules-new-btn"),
    refreshBtn: document.getElementById("schedules-refresh-btn")
  };
}
function _scheduleTitle(schedule) {
  return String(schedule?.label || schedule?.command_text || schedule?.id || "Schedule").trim();
}
function _schedulePresetFor(schedule) {
  const preset = String(schedule?.cadence_preset || "").trim().toLowerCase();
  if (preset && SCHEDULES_CADENCE_PRESETS.some(([value]) => value === preset)) return preset;
  return "custom";
}
function _scheduleDefaultTimezone() {
  const configured = String(_scheduleAppConfig()?.scheduler_default_timezone || "").trim();
  return configured || "UTC";
}
function _scheduleDraftFromSchedule(schedule = null, command = "") {
  const preset = schedule ? _schedulePresetFor(schedule) : "hourly";
  return {
    id: schedule?.id || "",
    label: String(schedule?.label || "").trim(),
    command_text: String(schedule?.command_text || command || "").trim(),
    cadence_preset: preset,
    cron_expr: String(schedule?.cron_expr || SCHEDULES_DEFAULT_CRON).trim(),
    timezone: String(schedule?.timezone || _scheduleDefaultTimezone()).trim(),
    enabled: schedule ? schedule.enabled !== false : true
  };
}
function _selectedSchedule() {
  return _schedulesState.schedules.find((item) => String(item.id || "") === String(_schedulesState.selectedId || "")) || null;
}
async function _scheduleJson(url, options = {}) {
  const resp = await _scheduleApiFetch(url, options);
  let data = {};
  try {
    data = await resp.json();
  } catch (err) {
    _scheduleClientError(`failed to parse schedule response from ${url}`, err);
    data = {};
  }
  if (!resp.ok) {
    const message = data?.message || data?.error || `HTTP ${resp.status}`;
    throw new Error(message);
  }
  return data;
}
function _scheduleToast(message, tone = "success") {
  const toast = typeof showToast === "function" ? showToast : typeof SCHEDULES_GLOBAL.showToast === "function" ? SCHEDULES_GLOBAL.showToast : null;
  if (toast) toast(message, tone);
}
function _scheduleClientError(context, err) {
  const log = (typeof hasRuntimeHandler === "function" && hasRuntimeHandler("logClientError") && typeof logClientError === "function" ? logClientError : null) || (typeof SCHEDULES_GLOBAL.logClientError === "function" ? SCHEDULES_GLOBAL.logClientError : null);
  if (log) log(context, err);
}
function _scheduleCloseMajorOverlays() {
  const close = typeof closeMajorOverlays === "function" && closeMajorOverlays || SCHEDULES_GLOBAL._closeMajorOverlays;
  if (typeof close === "function") close();
}
function _scheduleRefreshHistoryPanel() {
  if (typeof hasHistoryPanelHandler === "function" && hasHistoryPanelHandler("refreshHistoryPanel") && typeof refreshHistoryPanel === "function") {
    return refreshHistoryPanel();
  }
  if (typeof SCHEDULES_GLOBAL.refreshHistoryPanel === "function") return SCHEDULES_GLOBAL.refreshHistoryPanel();
  return null;
}
function _scheduleDateLabel(value) {
  const raw = String(value || "").trim();
  if (!raw) return "never";
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  return date.toLocaleString();
}
function _schedulePreviewDateLabel(value, timezone) {
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
    return _scheduleDateLabel(value);
  }
}
function _scheduleBrowserTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  } catch (_) {
    return "";
  }
}
function _scheduleTimezoneOptions(selected) {
  const preferred = /* @__PURE__ */ new Set(["UTC"]);
  const browserTimezone = _scheduleBrowserTimezone();
  if (browserTimezone) preferred.add(browserTimezone);
  SCHEDULES_COMMON_TIMEZONES.forEach((zone) => preferred.add(zone));
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
function _scheduleStatusLabel(schedule) {
  if (!schedule) return "";
  const reason = String(schedule.paused_reason || "").trim();
  if (schedule.enabled === false) {
    return /revok/i.test(reason) ? "token revoked" : "paused";
  }
  if (schedule.last_error) return "needs attention";
  return "active";
}
function _scheduleStatusTone(schedule) {
  const label = _scheduleStatusLabel(schedule);
  if (label === "active") return "badge-tone-green";
  if (label === "token revoked" || label === "needs attention") return "badge-tone-red";
  return "badge-tone-muted";
}
function _scheduleFireStatusTone(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "fired") return "badge-tone-green";
  if (normalized === "fire_failed") return "badge-tone-red";
  if (normalized.startsWith("skipped_")) return "badge-tone-amber";
  return "badge-tone-muted";
}
function _bindSchedulePressable(el, onActivate, options = {}) {
  if (!el || typeof onActivate !== "function") return;
  const bind = typeof bindPressable === "function" ? bindPressable : typeof SCHEDULES_GLOBAL.bindPressable === "function" ? SCHEDULES_GLOBAL.bindPressable : null;
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
function _activateScheduleAction(value) {
  const schedule = _selectedSchedule();
  if (value === "delete") _deleteSelectedSchedule(schedule);
  if (value === "pause") _patchSelectedSchedule(schedule, { enabled: false, paused_reason: "paused" }, "Schedule paused");
  if (value === "resume") {
    _patchSelectedSchedule(schedule, {
      enabled: true,
      paused_reason: "",
      last_error: "",
      consecutive_failures: 0
    }, "Schedule resumed");
  }
  if (value === "run-now") _runSelectedSchedule(schedule);
  if (value === "refresh-fires") _loadScheduleFires(schedule?.id || "").catch(() => {
  });
}
function _changeScheduleFiresPage(direction) {
  const meta = _schedulesState.firesMeta || {};
  const nextOffset = direction === "next" ? Number(meta.offset || 0) + Number(meta.limit || SCHEDULES_FIRES_LIMIT) : Math.max(0, Number(meta.offset || 0) - Number(meta.limit || SCHEDULES_FIRES_LIMIT));
  _loadScheduleFires(_schedulesState.selectedId, { offset: nextOffset }).catch(() => {
  });
}
async function _openScheduleRun(runId) {
  const closed = await closeSchedulesModal({ refocus: false });
  if (!closed) return;
  _scheduleOpenHistoryRunDetails(runId);
}
async function _compareScheduleFireToPrevious(fire = {}, previousFire = {}) {
  const runId = String(fire?.run_id || "").trim();
  const previousRunId = String(previousFire?.run_id || "").trim();
  if (!runId || !previousRunId || runId === previousRunId) {
    _scheduleToast("Choose two completed schedule fires to compare.", "error");
    return;
  }
  const closed = await closeSchedulesModal({ refocus: false });
  if (!closed) return;
  try {
    await _scheduleFetchAndRenderHistoryComparison(previousRunId, runId);
  } catch (err) {
    _scheduleClientError("failed to compare schedule fire to previous fire", err);
    _scheduleToast(err?.message || "Could not open run comparison", "error");
  }
}
function _setSchedulesOpen(open) {
  const { overlay } = _scheduleEls();
  if (!overlay) return;
  overlay.classList.toggle("u-hidden", !open);
  overlay.classList.toggle("open", !!open);
  overlay.setAttribute("aria-hidden", open ? "false" : "true");
  _scheduleSyncModalOverlayState();
  if (open) _focusSchedulesModal();
}
function isSchedulesOverlayOpen() {
  const { overlay } = _scheduleEls();
  return !!(overlay && overlay.classList.contains("open"));
}
function _focusSchedulesModal() {
  const modal = document.getElementById("schedules-modal");
  if (!modal || typeof modal.focus !== "function" || !isSchedulesOverlayOpen()) return;
  if (modal.contains(document.activeElement)) return;
  try {
    modal.focus({ preventScroll: true });
  } catch (_) {
    modal.focus();
  }
}
function _normalizeScheduleComparable(data = {}) {
  const preset = String(data.cadence_preset || "").trim();
  return {
    label: String(data.label || "").trim(),
    command: String(data.command ?? data.command_text ?? "").trim(),
    cadence_preset: preset === "custom" ? "" : preset,
    cron_expr: String(data.cron_expr || SCHEDULES_DEFAULT_CRON).trim(),
    timezone: String(data.timezone || _scheduleDefaultTimezone()).trim(),
    enabled: data.enabled !== false
  };
}
function _markScheduleClean(draft = _schedulesState.draft) {
  _schedulesState.cleanDraft = draft ? _normalizeScheduleComparable(draft) : null;
  _schedulesState.formDirty = false;
}
function _markScheduleDirty(event) {
  if (event?.target?.closest?.("#schedules-form")) {
    _schedulesState.formDirty = true;
  }
}
function _scheduleCurrentComparable() {
  const form = document.getElementById("schedules-form");
  return form ? _normalizeScheduleComparable(_collectScheduleDraft(form)) : _normalizeScheduleComparable(_schedulesState.draft || {});
}
function _scheduleNewDraftHasMeaningfulInput(draft) {
  const data = _normalizeScheduleComparable(draft);
  return !!(data.label || data.command || data.cadence_preset !== "hourly" || data.cron_expr !== SCHEDULES_DEFAULT_CRON || data.timezone !== _scheduleDefaultTimezone() || data.enabled === false);
}
function _scheduleHasUnsavedChanges() {
  if (!document.getElementById("schedules-form")) return false;
  const current = _scheduleCurrentComparable();
  if (_schedulesState.mode === "new") return _scheduleNewDraftHasMeaningfulInput(current);
  if (!_schedulesState.cleanDraft) return _schedulesState.formDirty;
  return _schedulesState.formDirty || JSON.stringify(current) !== JSON.stringify(_schedulesState.cleanDraft);
}
async function _confirmScheduleDiscardChanges() {
  if (!_scheduleHasUnsavedChanges()) return true;
  if (_schedulesState.discardPromptOpen) return false;
  _schedulesState.discardPromptOpen = true;
  try {
    const choice = await _scheduleShowConfirm({
      body: "Discard unsaved schedule changes?",
      tone: "warning",
      actions: [
        { id: "cancel", label: "Cancel", role: "cancel" },
        { id: "discard", label: "Discard changes", role: "destructive" }
      ]
    });
    return choice === null ? true : choice === "discard";
  } finally {
    _schedulesState.discardPromptOpen = false;
  }
}
async function closeSchedulesModal({ refocus = true, force = false } = {}) {
  if (!force && !await _confirmScheduleDiscardChanges()) return false;
  _cancelSchedulePreview();
  _schedulesState.cleanDraft = null;
  _schedulesState.formDirty = false;
  _setSchedulesOpen(false);
  if (refocus) _scheduleRefocusComposerAfterAction({ preventScroll: true, defer: true });
  return true;
}
function _cancelSchedulePreview() {
  window.clearTimeout(_schedulesState.previewTimer);
  _schedulesState.previewTimer = null;
  try {
    _schedulesState.previewController?.abort?.();
  } catch (_) {
  }
  _schedulesState.previewController = null;
}
function _renderSchedulesList() {
  const { list, count } = _scheduleEls();
  if (!list) return;
  list.replaceChildren();
  if (count) count.textContent = String(_schedulesState.schedules.length);
  if (_schedulesState.loading) {
    const loading = document.createElement("div");
    loading.className = "schedules-empty";
    loading.textContent = "Loading schedules...";
    list.appendChild(loading);
    return;
  }
  if (!_schedulesState.schedules.length) {
    const empty = document.createElement("div");
    empty.className = "schedules-empty";
    empty.textContent = "No schedules saved.";
    list.appendChild(empty);
    return;
  }
  _schedulesState.schedules.forEach((schedule) => {
    const row = document.createElement("div");
    row.className = "schedules-list-row panel-row panel-row-clickable";
    row.dataset.scheduleId = schedule.id || "";
    row.setAttribute("role", "button");
    row.tabIndex = 0;
    if (String(schedule.id || "") === String(_schedulesState.selectedId || "")) row.classList.add("active");
    const title = document.createElement("span");
    title.className = "schedules-list-title";
    title.textContent = _scheduleTitle(schedule);
    const meta = document.createElement("span");
    meta.className = "schedules-list-meta";
    const cadence = schedule.cadence_preset || schedule.cron_expr || "custom";
    meta.textContent = `${cadence} - ${_scheduleDateLabel(schedule.next_run_at)}`;
    const status = document.createElement("span");
    status.className = `badge ${_scheduleStatusTone(schedule)} schedules-list-status`;
    status.textContent = _scheduleStatusLabel(schedule);
    row.append(title, meta, status);
    _bindSchedulePressable(row, () => _selectSchedule(schedule.id || ""));
    list.appendChild(row);
  });
}
function _schedulePreviewNode() {
  const wrap = document.createElement("div");
  wrap.className = "schedules-preview";
  const title = document.createElement("div");
  title.className = "schedules-section-kicker";
  const timezone = _schedulesState.preview.timezone || _schedulesState.draft?.timezone || _scheduleDefaultTimezone();
  title.textContent = `Next runs (${timezone})`;
  wrap.appendChild(title);
  if (_schedulesState.preview.loading) {
    const loading = document.createElement("div");
    loading.className = "schedules-muted";
    loading.textContent = "Checking...";
    wrap.appendChild(loading);
  } else if (_schedulesState.preview.error) {
    const err = document.createElement("div");
    err.className = "schedules-error";
    err.textContent = _schedulesState.preview.error;
    wrap.appendChild(err);
  } else {
    const list = document.createElement("div");
    list.className = "schedules-preview-list";
    (_schedulesState.preview.next_fires || []).forEach((value) => {
      const item = document.createElement("span");
      item.textContent = _schedulePreviewDateLabel(value, timezone);
      list.appendChild(item);
    });
    if (!list.childElementCount) {
      const empty = document.createElement("span");
      empty.className = "schedules-muted";
      empty.textContent = "No preview available.";
      list.appendChild(empty);
    }
    wrap.appendChild(list);
  }
  return wrap;
}
function _renderSchedulePreview(parent) {
  parent.appendChild(_schedulePreviewNode());
}
function _updateSchedulePreviewView() {
  const current = document.querySelector(".schedules-preview");
  if (current) current.replaceWith(_schedulePreviewNode());
}
function _scheduleFormField(label, control) {
  const field = document.createElement("label");
  field.className = "schedules-field";
  const text = document.createElement("span");
  text.className = "schedules-field-label";
  text.textContent = label;
  field.append(text, control);
  return field;
}
function _scheduleInput(value, attrs = {}) {
  const input = document.createElement("input");
  input.className = "form-control schedules-input";
  input.value = value || "";
  Object.entries(attrs).forEach(([key, attrValue]) => {
    if (attrValue !== null && attrValue !== void 0) input.setAttribute(key, attrValue);
  });
  return input;
}
function _scheduleTimezoneSelect(value) {
  const selectedValue = value || _scheduleDefaultTimezone();
  const select = document.createElement("select");
  select.id = "schedules-timezone-input";
  select.className = "form-select schedules-select";
  _scheduleTimezoneOptions(selectedValue).forEach((timezone) => {
    const option = document.createElement("option");
    option.value = timezone;
    option.textContent = timezone;
    if (timezone === selectedValue) option.selected = true;
    select.appendChild(option);
  });
  if (select.value !== selectedValue) select.value = _scheduleDefaultTimezone();
  return select;
}
function _setScheduleCadencePreset(value) {
  document.querySelectorAll(".schedules-cadence-btn").forEach((btn) => {
    const active = btn.dataset.schedulePreset === value;
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-checked", active ? "true" : "false");
  });
}
function _renderScheduleForm(parent, schedule) {
  const draft = _schedulesState.draft || _scheduleDraftFromSchedule(schedule);
  const form = document.createElement("form");
  form.className = "schedules-form";
  form.id = "schedules-form";
  const labelInput = _scheduleInput(draft.label, {
    id: "schedules-label-input",
    autocomplete: "off",
    maxlength: "120"
  });
  const commandInput = document.createElement("textarea");
  commandInput.id = "schedules-command-input";
  commandInput.className = "form-control schedules-command-input";
  commandInput.value = draft.command_text;
  commandInput.rows = 3;
  commandInput.spellcheck = false;
  commandInput.setAttribute("required", "required");
  const timezoneInput = _scheduleTimezoneSelect(draft.timezone || _scheduleDefaultTimezone());
  const cronInput = _scheduleInput(draft.cron_expr || SCHEDULES_DEFAULT_CRON, {
    id: "schedules-cron-input",
    autocomplete: "off",
    required: "required"
  });
  form.append(
    _scheduleFormField("Label", labelInput),
    _scheduleFormField("Command", commandInput)
  );
  const cadence = document.createElement("div");
  cadence.className = "schedules-field schedules-cadence-field";
  const cadenceLabel = document.createElement("span");
  cadenceLabel.className = "schedules-field-label";
  cadenceLabel.textContent = "Cadence";
  const cadenceControls = document.createElement("div");
  cadenceControls.className = "schedules-cadence-controls tab-strip";
  cadenceControls.setAttribute("role", "radiogroup");
  cadenceControls.setAttribute("aria-label", "Cadence");
  [
    ...SCHEDULES_CADENCE_PRESETS,
    ["custom", "Custom cron"]
  ].forEach(([preset, label]) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "tab-strip-item schedules-cadence-btn";
    btn.dataset.schedulePreset = preset;
    btn.setAttribute("role", "radio");
    btn.setAttribute("aria-checked", draft.cadence_preset === preset ? "true" : "false");
    if (draft.cadence_preset === preset) btn.classList.add("is-active");
    btn.textContent = label;
    _bindSchedulePressable(btn, () => {
      _schedulesState.formDirty = true;
      _setScheduleCadencePreset(preset);
      _loadSchedulePreview({ immediate: true }).catch(() => {
      });
    });
    cadenceControls.appendChild(btn);
  });
  cadence.append(cadenceLabel, cadenceControls);
  form.appendChild(cadence);
  form.append(
    _scheduleFormField("Cron", cronInput),
    _scheduleFormField("Timezone", timezoneInput)
  );
  const enabledLabel = document.createElement("label");
  enabledLabel.className = "schedules-check-row";
  const enabled = document.createElement("input");
  enabled.type = "checkbox";
  enabled.id = "schedules-enabled-input";
  enabled.checked = draft.enabled !== false;
  const enabledText = document.createElement("span");
  enabledText.textContent = "Enabled";
  enabledLabel.append(enabled, enabledText);
  form.appendChild(enabledLabel);
  _renderSchedulePreview(form);
  const actions = document.createElement("div");
  actions.className = "schedules-detail-actions";
  const saveBtn = document.createElement("button");
  saveBtn.type = "submit";
  saveBtn.className = "btn btn-primary btn-compact";
  saveBtn.disabled = _schedulesState.saving;
  saveBtn.textContent = schedule ? "Save" : "Create";
  actions.appendChild(saveBtn);
  if (schedule) {
    const toggleBtn = document.createElement("button");
    toggleBtn.type = "button";
    toggleBtn.className = "btn btn-secondary btn-compact";
    toggleBtn.dataset.scheduleAction = schedule.enabled === false ? "resume" : "pause";
    toggleBtn.textContent = schedule.enabled === false ? "Resume" : "Pause";
    _bindSchedulePressable(toggleBtn, () => _activateScheduleAction(toggleBtn.dataset.scheduleAction));
    const runBtn = document.createElement("button");
    runBtn.type = "button";
    runBtn.className = "btn btn-secondary btn-compact";
    runBtn.dataset.scheduleAction = "run-now";
    runBtn.textContent = "Run now";
    _bindSchedulePressable(runBtn, () => _activateScheduleAction("run-now"));
    const deleteBtn = document.createElement("button");
    deleteBtn.type = "button";
    deleteBtn.className = "btn btn-ghost btn-compact";
    deleteBtn.dataset.scheduleAction = "delete";
    deleteBtn.textContent = "Delete";
    _bindSchedulePressable(deleteBtn, () => _activateScheduleAction("delete"));
    actions.append(toggleBtn, runBtn, deleteBtn);
  }
  form.appendChild(actions);
  parent.appendChild(form);
}
function _renderScheduleFires(parent, schedule) {
  if (!schedule) return;
  const section = document.createElement("div");
  section.className = "schedules-fires";
  const header = document.createElement("div");
  header.className = "schedules-section-header";
  const title = document.createElement("h3");
  title.textContent = "Past fires";
  const refresh = document.createElement("button");
  refresh.type = "button";
  refresh.className = "btn btn-ghost btn-compact";
  refresh.dataset.scheduleAction = "refresh-fires";
  refresh.textContent = "Refresh";
  _bindSchedulePressable(refresh, () => _activateScheduleAction("refresh-fires"));
  header.append(title, refresh);
  section.appendChild(header);
  if (_schedulesState.loadingFires) {
    const loading = document.createElement("div");
    loading.className = "schedules-empty";
    loading.textContent = "Loading fires...";
    section.appendChild(loading);
  } else if (!_schedulesState.fires.length) {
    const empty = document.createElement("div");
    empty.className = "schedules-empty";
    empty.textContent = "No fires yet.";
    section.appendChild(empty);
  } else {
    const rows = document.createElement("div");
    rows.className = "schedules-fire-list";
    _schedulesState.fires.forEach((fire, index) => {
      const row = document.createElement("div");
      row.className = "schedules-fire-row";
      const main = document.createElement("div");
      main.className = "schedules-fire-main";
      const status = document.createElement("span");
      status.className = `badge ${_scheduleFireStatusTone(fire.status)} schedules-fire-status`;
      status.textContent = fire.status || "fire";
      const date = document.createElement("span");
      date.className = "schedules-fire-date";
      date.textContent = _scheduleDateLabel(fire.fired_at);
      main.append(status, date);
      const reason = document.createElement("div");
      reason.className = "schedules-fire-reason";
      reason.textContent = fire.reason || "";
      row.append(main, reason);
      if (fire.run_id) {
        const actions = document.createElement("div");
        actions.className = "schedules-fire-actions";
        const previousFire = _schedulesState.fires.slice(index + 1).find((item) => String(item?.run_id || "").trim());
        if (previousFire?.run_id && previousFire.run_id !== fire.run_id) {
          const compare = document.createElement("button");
          compare.type = "button";
          compare.className = "btn btn-primary btn-compact";
          compare.textContent = "Compare previous";
          _bindSchedulePressable(compare, () => _compareScheduleFireToPrevious(fire, previousFire));
          actions.appendChild(compare);
        }
        const open = document.createElement("button");
        open.type = "button";
        open.className = "btn btn-secondary btn-compact";
        open.dataset.scheduleRunId = fire.run_id;
        open.textContent = "Open run";
        _bindSchedulePressable(open, () => _openScheduleRun(fire.run_id || ""));
        actions.appendChild(open);
        row.appendChild(actions);
      }
      rows.appendChild(row);
    });
    section.appendChild(rows);
  }
  const meta = _schedulesState.firesMeta || {};
  if (Number(meta.total || 0) > Number(meta.limit || SCHEDULES_FIRES_LIMIT)) {
    const pager = document.createElement("div");
    pager.className = "schedules-pager";
    const prev = document.createElement("button");
    prev.type = "button";
    prev.className = "btn btn-secondary btn-compact";
    prev.dataset.scheduleFiresPage = "prev";
    prev.disabled = Number(meta.offset || 0) <= 0;
    prev.textContent = "Prev";
    _bindSchedulePressable(prev, () => _changeScheduleFiresPage("prev"));
    const label = document.createElement("span");
    label.className = "schedules-muted";
    const start = Number(meta.offset || 0) + 1;
    const end = Math.min(Number(meta.total || 0), Number(meta.offset || 0) + _schedulesState.fires.length);
    label.textContent = `${start}-${end} / ${Number(meta.total || 0).toLocaleString()}`;
    const next = document.createElement("button");
    next.type = "button";
    next.className = "btn btn-secondary btn-compact";
    next.dataset.scheduleFiresPage = "next";
    next.disabled = !meta.has_more;
    next.textContent = "Next";
    _bindSchedulePressable(next, () => _changeScheduleFiresPage("next"));
    pager.append(prev, label, next);
    section.appendChild(pager);
  }
  parent.appendChild(section);
}
function _renderSchedulesDetail() {
  const { detail } = _scheduleEls();
  if (!detail) return;
  detail.replaceChildren();
  const schedule = _selectedSchedule();
  const isNew = _schedulesState.mode === "new";
  const root = document.createElement("div");
  root.className = "schedules-detail-inner";
  if (_schedulesState.mode === "missing") {
    const missing = document.createElement("div");
    missing.className = "schedules-empty schedules-detail-empty";
    missing.textContent = _schedulesState.missingScheduleId ? `Schedule ${_schedulesState.missingScheduleId} was not found. It may have been deleted.` : "Schedule was not found. It may have been deleted.";
    root.appendChild(missing);
    detail.appendChild(root);
    return;
  }
  if (!schedule && !isNew) {
    const empty = document.createElement("div");
    empty.className = "schedules-empty schedules-detail-empty";
    empty.textContent = "Select or create a schedule.";
    root.appendChild(empty);
    detail.appendChild(root);
    return;
  }
  const header = document.createElement("div");
  header.className = "schedules-detail-header";
  const title = document.createElement("div");
  title.className = "schedules-detail-title";
  title.textContent = isNew ? "New schedule" : _scheduleTitle(schedule);
  header.appendChild(title);
  if (schedule) {
    const status = document.createElement("span");
    status.className = `badge ${_scheduleStatusTone(schedule)}`;
    status.textContent = _scheduleStatusLabel(schedule);
    header.appendChild(status);
  }
  root.appendChild(header);
  if (schedule?.paused_reason && /revok/i.test(schedule.paused_reason)) {
    const revoked = document.createElement("div");
    revoked.className = "schedules-alert";
    revoked.textContent = "Paused because the session token was revoked.";
    root.appendChild(revoked);
  } else if (schedule?.last_error) {
    const err = document.createElement("div");
    err.className = "schedules-alert";
    const failures = Number(schedule.consecutive_failures || 0);
    const failureText = failures > 1 ? ` (${failures} failed runs in a row)` : "";
    err.textContent = `${schedule.last_error}${failureText}`;
    root.appendChild(err);
  }
  _renderScheduleForm(root, isNew ? null : schedule);
  if (schedule) _renderScheduleFires(root, schedule);
  detail.appendChild(root);
}
function _updateScheduleFiresView() {
  const schedule = _selectedSchedule();
  if (!schedule) return;
  const current = document.querySelector(".schedules-fires");
  if (!current) return;
  const fragment = document.createElement("div");
  _renderScheduleFires(fragment, schedule);
  const next = fragment.firstElementChild;
  if (next) current.replaceWith(next);
}
function _renderSchedulesModal() {
  _renderSchedulesList();
  _renderSchedulesDetail();
}
function _collectScheduleDraft(form = document.getElementById("schedules-form")) {
  const root = form || document;
  const preset = root.querySelector?.(".schedules-cadence-btn.is-active")?.dataset.schedulePreset || "hourly";
  const cronExpr = String(root.querySelector?.("#schedules-cron-input")?.value || "").trim();
  return {
    label: String(root.querySelector?.("#schedules-label-input")?.value || "").trim(),
    command: String(root.querySelector?.("#schedules-command-input")?.value || "").trim(),
    cadence_preset: preset === "custom" ? "" : preset,
    cron_expr: cronExpr || SCHEDULES_DEFAULT_CRON,
    timezone: String(root.querySelector?.("#schedules-timezone-input")?.value || _scheduleDefaultTimezone()).trim(),
    enabled: !!root.querySelector?.("#schedules-enabled-input")?.checked
  };
}
function _syncScheduleDraftFromForm() {
  const data = _collectScheduleDraft();
  _schedulesState.draft = {
    id: _schedulesState.draft?.id || _schedulesState.selectedId || "",
    label: data.label,
    command_text: data.command,
    cadence_preset: data.cadence_preset || "custom",
    cron_expr: data.cron_expr || SCHEDULES_DEFAULT_CRON,
    timezone: data.timezone || _scheduleDefaultTimezone(),
    enabled: data.enabled
  };
}
async function _loadSchedulePreview({ immediate = false } = {}) {
  _cancelSchedulePreview();
  const run = async () => {
    const form = document.getElementById("schedules-form");
    if (!form) return;
    _syncScheduleDraftFromForm();
    const draft = _schedulesState.draft || {};
    const params = new URLSearchParams();
    if (draft.cadence_preset && draft.cadence_preset !== "custom") params.set("cadence_preset", draft.cadence_preset);
    else params.set("cron", draft.cron_expr || SCHEDULES_DEFAULT_CRON);
    params.set("tz", draft.timezone || _scheduleDefaultTimezone());
    const controller = typeof AbortController === "function" ? new AbortController() : null;
    _schedulesState.previewController = controller;
    _schedulesState.preview = { ..._schedulesState.preview, loading: true, error: "" };
    _updateSchedulePreviewView();
    try {
      const data = await _scheduleJson(`/schedules/preview?${params.toString()}`, {
        cache: "no-store",
        signal: controller?.signal
      });
      const cronExpr = String(data.cron_expr || "").trim();
      if (cronExpr && draft.cadence_preset && draft.cadence_preset !== "custom") {
        const cronInput = form.querySelector?.("#schedules-cron-input");
        if (cronInput) cronInput.value = cronExpr;
        _schedulesState.draft = { ...draft, cron_expr: cronExpr };
      }
      _schedulesState.preview = {
        loading: false,
        error: "",
        next_fires: Array.isArray(data.next_fires) ? data.next_fires : [],
        cron_expr: cronExpr || draft.cron_expr || SCHEDULES_DEFAULT_CRON,
        timezone: data.timezone || draft.timezone || _scheduleDefaultTimezone()
      };
    } catch (err) {
      if (err?.name === "AbortError") return;
      _scheduleClientError("failed to preview schedule cadence", err);
      _schedulesState.preview = {
        ..._schedulesState.preview,
        loading: false,
        error: err?.message || "Could not preview cadence",
        next_fires: []
      };
    } finally {
      if (_schedulesState.previewController === controller) {
        _schedulesState.previewController = null;
      }
    }
    _updateSchedulePreviewView();
  };
  if (immediate) {
    await run();
  } else {
    _schedulesState.previewTimer = window.setTimeout(run, 250);
  }
}
async function _loadScheduleFires(scheduleId, { offset = 0 } = {}) {
  if (!scheduleId) return;
  _schedulesState.loadingFires = true;
  _updateScheduleFiresView();
  try {
    const params = new URLSearchParams({
      limit: String(SCHEDULES_FIRES_LIMIT),
      offset: String(Math.max(0, Number(offset || 0)))
    });
    const data = await _scheduleJson(
      `/schedules/${encodeURIComponent(scheduleId)}/fires?${params.toString()}`,
      { cache: "no-store" }
    );
    _schedulesState.fires = Array.isArray(data.fires) ? data.fires : [];
    _schedulesState.firesMeta = {
      limit: Number(data.limit || SCHEDULES_FIRES_LIMIT),
      offset: Number(data.offset || 0),
      total: Number(data.total || 0),
      has_more: !!data.has_more
    };
  } catch (err) {
    _schedulesState.fires = [];
    _schedulesState.firesMeta = { limit: SCHEDULES_FIRES_LIMIT, offset: 0, total: 0, has_more: false };
    _scheduleClientError("failed to load schedule fires", err);
    _scheduleToast(err?.message || "Could not load schedule fires", "error");
  } finally {
    _schedulesState.loadingFires = false;
    _updateScheduleFiresView();
  }
}
async function refreshSchedulesModal({ selectId = "", command = "" } = {}) {
  _schedulesState.loading = true;
  _renderSchedulesModal();
  try {
    const data = await _scheduleJson("/schedules", { cache: "no-store" });
    _schedulesState.schedules = Array.isArray(data.schedules) ? data.schedules : [];
    _scheduleEmitUiEvent("app:schedules-rendered", { items: _schedulesState.schedules.slice() });
    _schedulesState.missingScheduleId = "";
    const requestedId = String(selectId || "");
    const currentId = String(selectId || _schedulesState.selectedId || "");
    const hasCurrent = _schedulesState.schedules.some((item) => String(item.id || "") === currentId);
    if (requestedId && !hasCurrent) {
      _schedulesState.mode = "missing";
      _schedulesState.selectedId = "";
      _schedulesState.missingScheduleId = requestedId;
      _schedulesState.cleanDraft = null;
      _schedulesState.formDirty = false;
    } else {
      const fallbackId = _schedulesState.schedules[0]?.id || "";
      _schedulesState.selectedId = hasCurrent ? currentId : fallbackId;
    }
    if (command) {
      _schedulesState.mode = "new";
      _schedulesState.selectedId = "";
      _schedulesState.missingScheduleId = "";
      _schedulesState.draft = _scheduleDraftFromSchedule(null, command);
      _schedulesState.cleanDraft = null;
      _schedulesState.formDirty = false;
    } else if (_schedulesState.selectedId) {
      _schedulesState.mode = "view";
      _schedulesState.draft = _scheduleDraftFromSchedule(_selectedSchedule());
      _markScheduleClean(_schedulesState.draft);
    } else {
      _schedulesState.cleanDraft = null;
      _schedulesState.formDirty = false;
    }
    _schedulesState.fires = [];
  } catch (err) {
    _scheduleClientError("failed to load schedules", err);
    _scheduleToast(err?.message || "Could not load schedules", "error");
  } finally {
    _schedulesState.loading = false;
    _renderSchedulesModal();
    _focusSchedulesModal();
    await _loadSchedulePreview({ immediate: true });
    if (_schedulesState.selectedId) await _loadScheduleFires(_schedulesState.selectedId);
  }
}
async function openSchedulesModal(options = {}) {
  const { overlay } = _scheduleEls();
  if (!overlay) return;
  _scheduleCloseMajorOverlays();
  _setSchedulesOpen(true);
  _schedulesState.mode = options.command ? "new" : "view";
  _schedulesState.selectedId = String(options.scheduleId || "");
  _schedulesState.draft = options.command ? _scheduleDraftFromSchedule(null, options.command) : null;
  _schedulesState.formDirty = false;
  await refreshSchedulesModal({
    selectId: options.scheduleId || "",
    command: options.command || ""
  });
}
async function _saveScheduleForm(event) {
  event?.preventDefault?.();
  const data = _collectScheduleDraft();
  if (!data.command) {
    _scheduleToast("Command is required", "error");
    return;
  }
  _schedulesState.saving = true;
  _renderSchedulesDetail();
  const selected = _selectedSchedule();
  const isNew = _schedulesState.mode === "new" || !selected;
  try {
    const url = isNew ? "/schedules" : `/schedules/${encodeURIComponent(selected.id)}`;
    const method = isNew ? "POST" : "PATCH";
    const payload = { ...data };
    const response = await _scheduleJson(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const schedule = response.schedule || {};
    _scheduleToast(isNew ? "Schedule created" : "Schedule saved");
    _schedulesState.mode = "view";
    await refreshSchedulesModal({ selectId: schedule.id || selected?.id || "" });
    _scheduleLoadAutocompleteHints().catch(() => {
    });
    _scheduleRefreshHistoryPanel();
  } catch (err) {
    _scheduleClientError(isNew ? "failed to create schedule" : "failed to update schedule", err);
    _scheduleToast(err?.message || "Could not save schedule", "error");
  } finally {
    _schedulesState.saving = false;
    _renderSchedulesDetail();
  }
}
async function _deleteSelectedSchedule(schedule) {
  if (!schedule) return;
  let confirmed = true;
  const choice = await _scheduleShowConfirm({
    body: `Delete schedule "${_scheduleTitle(schedule)}"?`,
    tone: "danger",
    actions: [
      { id: "cancel", label: "Cancel", role: "cancel" },
      { id: "delete", label: "Delete", role: "destructive" }
    ]
  });
  if (choice !== null) confirmed = choice === "delete";
  if (!confirmed) return;
  try {
    await _scheduleJson(`/schedules/${encodeURIComponent(schedule.id)}`, { method: "DELETE" });
    _scheduleToast("Schedule deleted");
    _schedulesState.selectedId = "";
    await refreshSchedulesModal();
    _scheduleLoadAutocompleteHints().catch(() => {
    });
    _scheduleRefreshHistoryPanel();
  } catch (err) {
    _scheduleClientError("failed to delete schedule", err);
    _scheduleToast(err?.message || "Could not delete schedule", "error");
  }
}
async function _patchSelectedSchedule(schedule, updates, successMessage) {
  if (!schedule) return;
  try {
    const response = await _scheduleJson(`/schedules/${encodeURIComponent(schedule.id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates)
    });
    _scheduleToast(successMessage);
    await refreshSchedulesModal({ selectId: response.schedule?.id || schedule.id });
    _scheduleLoadAutocompleteHints().catch(() => {
    });
    _scheduleRefreshHistoryPanel();
  } catch (err) {
    _scheduleClientError("failed to update schedule", err);
    _scheduleToast(err?.message || "Could not update schedule", "error");
  }
}
async function _runSelectedSchedule(schedule) {
  if (!schedule) return;
  try {
    const data = await _scheduleJson(`/schedules/${encodeURIComponent(schedule.id)}/run-now`, { method: "POST" });
    _scheduleToast(data.status === "fired" ? "Schedule fired" : "Schedule skipped");
    await refreshSchedulesModal({ selectId: schedule.id });
    _scheduleRefreshHistoryPanel();
  } catch (err) {
    _scheduleClientError("failed to run schedule now", err);
    _scheduleToast(err?.message || "Could not fire schedule", "error");
  }
}
async function _selectSchedule(scheduleId) {
  if (!await _confirmScheduleDiscardChanges()) return;
  _schedulesState.mode = "view";
  _schedulesState.selectedId = String(scheduleId || "");
  _schedulesState.draft = _scheduleDraftFromSchedule(_selectedSchedule());
  _markScheduleClean(_schedulesState.draft);
  _schedulesState.fires = [];
  _schedulesState.missingScheduleId = "";
  _renderSchedulesModal();
  _loadSchedulePreview({ immediate: true }).catch(() => {
  });
  _loadScheduleFires(_schedulesState.selectedId).catch(() => {
  });
}
async function _newSchedule(command = "") {
  if (!await _confirmScheduleDiscardChanges()) return;
  _schedulesState.mode = "new";
  _schedulesState.selectedId = "";
  _schedulesState.draft = _scheduleDraftFromSchedule(null, command);
  _schedulesState.cleanDraft = null;
  _schedulesState.formDirty = false;
  _schedulesState.fires = [];
  _schedulesState.missingScheduleId = "";
  _renderSchedulesModal();
  _loadSchedulePreview({ immediate: true }).catch(() => {
  });
}
function _bindSchedulesModal() {
  const { overlay, newBtn, refreshBtn } = _scheduleEls();
  if (!overlay) return;
  if (overlay.dataset.schedulesModalBound === "1") return;
  overlay.dataset.schedulesModalBound = "1";
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) {
      closeSchedulesModal();
      return;
    }
    const close = event.target.closest?.(".schedules-close");
    if (close) {
      closeSchedulesModal();
      return;
    }
    const run = event.target.closest?.("[data-schedule-run-id]");
    if (run && run.dataset.pressableBound !== "1") {
      _openScheduleRun(run.dataset.scheduleRunId || "");
    }
  });
  overlay.addEventListener("input", (event) => {
    _markScheduleDirty(event);
    if (event.target?.id !== "schedules-cron-input") return;
    _setScheduleCadencePreset("custom");
    _loadSchedulePreview().catch(() => {
    });
  });
  overlay.addEventListener("change", (event) => {
    _markScheduleDirty(event);
    if (event.target?.id !== "schedules-timezone-input") return;
    _loadSchedulePreview().catch(() => {
    });
  });
  overlay.addEventListener("submit", (event) => {
    if (event.target && event.target.id === "schedules-form") _saveScheduleForm(event);
  });
  newBtn?.addEventListener("click", () => _newSchedule());
  refreshBtn?.addEventListener("click", async () => {
    if (await _confirmScheduleDiscardChanges()) refreshSchedulesModal({ selectId: _schedulesState.selectedId });
  });
  _scheduleBindDismissible(overlay, {
    level: "modal",
    isOpen: isSchedulesOverlayOpen,
    onClose: closeSchedulesModal,
    closeButtons: overlay.querySelectorAll(".schedules-close, .sheet-grab")
  });
}
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", _bindSchedulesModal);
else _bindSchedulesModal();
export {
  closeSchedulesModal,
  isSchedulesOverlayOpen,
  openSchedulesModal
};
