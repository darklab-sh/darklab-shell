import {
  coerceContext,
  coerceViewMode,
  compareFormatDelta,
  resolveViewMode,
  storedContext,
  storedViewMode,
  viewModeOptions,
  viewportMode
} from "./static-chunk-6sxirwn5.a08adec8fe31.js";
import {
  closeHistoryCompareOverlay
} from "./static-chunk-dil5yyjg.6d28df9092db.js";
import {
  restoreHistoryRunIntoTab
} from "./static-chunk-raa54zvl.6edf423cfb6c.js";
import {
  copyTextToClipboard,
  showToast
} from "./static-chunk-poi5czx6.3f5c94749765.js";
import {
  bindPressable
} from "./static-chunk-fik64llj.1291b1f4f79b.js";
import {
  enhanceAppSelects,
  portalDropdownMenu,
  unportalDropdownMenu
} from "./static-chunk-sgyzdmxn.7d1842f12a94.js";

// app/static/js/features/run-comparison/history_compare_controls.js
var HISTORY_COMPARE_CONTROLS_GLOBAL = typeof window !== "undefined" ? window : globalThis;
function _historyCompareControlsCoerceViewMode(mode) {
  const coerce = typeof coerceViewMode !== "undefined" && coerceViewMode || HISTORY_COMPARE_CONTROLS_GLOBAL._historyCompareCoerceViewMode;
  return typeof coerce === "function" ? coerce(mode) : mode;
}
function _historyCompareControlsCoerceContext(mode) {
  const coerce = typeof coerceContext !== "undefined" && coerceContext || HISTORY_COMPARE_CONTROLS_GLOBAL._historyCompareCoerceContext;
  return typeof coerce === "function" ? coerce(mode) : mode;
}
function _historyCompareControlsStoredViewMode() {
  const stored = typeof storedViewMode !== "undefined" && storedViewMode || HISTORY_COMPARE_CONTROLS_GLOBAL._historyCompareStoredViewMode;
  return typeof stored === "function" ? stored() : "auto";
}
function _historyCompareControlsStoredContext() {
  const stored = typeof storedContext !== "undefined" && storedContext || HISTORY_COMPARE_CONTROLS_GLOBAL._historyCompareStoredContext;
  return typeof stored === "function" ? stored() : "3";
}
function _historyCompareControlsResolveViewMode(mode) {
  const resolve = typeof resolveViewMode !== "undefined" && resolveViewMode || HISTORY_COMPARE_CONTROLS_GLOBAL._historyCompareResolveViewMode;
  return typeof resolve === "function" ? resolve(mode) : mode;
}
function _historyCompareControlsViewportMode() {
  const viewport = typeof viewportMode !== "undefined" && viewportMode || HISTORY_COMPARE_CONTROLS_GLOBAL._historyCompareViewportMode;
  return typeof viewport === "function" ? viewport() : "side_by_side";
}
function _historyCompareControlsViewModeOptions() {
  const options = typeof viewModeOptions !== "undefined" && viewModeOptions || HISTORY_COMPARE_CONTROLS_GLOBAL._historyCompareViewModeOptions;
  return typeof options === "function" ? options() : [];
}
function _historyCompareControlsFormatDelta(value) {
  const format = typeof compareFormatDelta !== "undefined" && compareFormatDelta || HISTORY_COMPARE_CONTROLS_GLOBAL._compareFormatDelta;
  return typeof format === "function" ? format(value) : String(value);
}
function _historyCompareControlsEnhanceAppSelects(root) {
  const enhance = typeof enhanceAppSelects !== "undefined" && enhanceAppSelects || HISTORY_COMPARE_CONTROLS_GLOBAL.enhanceAppSelects;
  if (typeof enhance === "function") enhance(root);
}
function _historyCompareControlsUnportalDropdownMenu(menu) {
  const unportal = typeof unportalDropdownMenu !== "undefined" && unportalDropdownMenu || HISTORY_COMPARE_CONTROLS_GLOBAL.unportalDropdownMenu;
  if (typeof unportal === "function") unportal(menu);
}
function _historyCompareControlsPortalDropdownMenu(wrap, trigger, menu) {
  const portal = typeof portalDropdownMenu !== "undefined" && portalDropdownMenu || HISTORY_COMPARE_CONTROLS_GLOBAL.portalDropdownMenu;
  if (typeof portal === "function") portal(wrap, trigger, menu);
}
function _historyCompareControlsBindPressable(el) {
  const bind = typeof bindPressable !== "undefined" && bindPressable || HISTORY_COMPARE_CONTROLS_GLOBAL.bindPressable;
  if (typeof bind === "function") bind(el);
}
function _historyCompareControlsRestoreRun(run, options) {
  const restore = typeof restoreHistoryRunIntoTab !== "undefined" && restoreHistoryRunIntoTab || HISTORY_COMPARE_CONTROLS_GLOBAL.restoreHistoryRunIntoTab || null;
  return typeof restore === "function" ? restore(run, options) : Promise.reject(new Error("history restore unavailable"));
}
function _historyCompareControlsCloseOverlay() {
  const close = typeof closeHistoryCompareOverlay !== "undefined" && closeHistoryCompareOverlay || HISTORY_COMPARE_CONTROLS_GLOBAL.closeHistoryCompareOverlay;
  if (typeof close === "function") close();
}
function _historyCompareControlsCopyText(text) {
  const copy = typeof copyTextToClipboard !== "undefined" && copyTextToClipboard || HISTORY_COMPARE_CONTROLS_GLOBAL.copyTextToClipboard;
  return typeof copy === "function" ? copy(text) : Promise.reject(new Error("clipboard unavailable"));
}
function _historyCompareControlsShowToast(message, tone = "success") {
  const toast = typeof showToast !== "undefined" && showToast || HISTORY_COMPARE_CONTROLS_GLOBAL.showToast;
  if (typeof toast === "function") toast(message, tone);
}
function _historyCompareApplyViewMode(mode, data) {
  const nextMode = _historyCompareControlsCoerceViewMode(mode);
  data._compareViewModeRaw = nextMode;
  window._renderHistoryComparison(data);
}
function _historyCompareApplyContext(mode, data) {
  const nextMode = _historyCompareControlsCoerceContext(mode);
  data._compareContext = nextMode;
  window._renderHistoryComparison(data);
}
function _closeHistoryCompareActionMenus(except = null) {
  document.querySelectorAll(".history-compare-actions-menu-wrap.open").forEach((wrap) => {
    if (except && wrap === except) return;
    wrap.classList.remove("open");
    wrap.querySelector(".history-compare-actions-trigger")?.setAttribute("aria-expanded", "false");
    const menu = wrap._portaledMenu;
    if (menu) _historyCompareControlsUnportalDropdownMenu(menu);
    wrap._portaledMenu = null;
  });
}
function _renderHistoryCompareDisplayControls(data, viewMode) {
  const controls = document.createElement("div");
  controls.className = "history-compare-controls";
  const defaultMode = _historyCompareControlsCoerceViewMode(data._compareViewModeDefault || _historyCompareControlsStoredViewMode());
  const rawMode = _historyCompareControlsCoerceViewMode(data._compareViewModeRaw || defaultMode);
  const resolvedMode = _historyCompareControlsResolveViewMode(rawMode);
  const viewSelect = document.createElement("select");
  viewSelect.className = "form-select history-compare-view-select";
  viewSelect.setAttribute("aria-label", "Run comparison view mode");
  viewSelect.dataset.portalMenu = "true";
  _historyCompareControlsViewModeOptions().forEach(([value, label]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    viewSelect.appendChild(option);
  });
  viewSelect.value = resolvedMode;
  viewSelect.addEventListener("change", () => _historyCompareApplyViewMode(viewSelect.value, data));
  controls.appendChild(viewSelect);
  const resetHidden = rawMode === defaultMode || defaultMode === "auto" && rawMode === _historyCompareControlsViewportMode();
  const reset = document.createElement("button");
  reset.type = "button";
  reset.className = "btn btn-ghost btn-icon-only history-compare-reset-view";
  reset.setAttribute("aria-label", "Reset comparison view to default");
  reset.title = "Reset comparison view to default";
  const resetIcon = document.createElement("span");
  resetIcon.className = "history-compare-reset-icon";
  resetIcon.setAttribute("aria-hidden", "true");
  resetIcon.textContent = "↻";
  reset.appendChild(resetIcon);
  reset.hidden = resetHidden;
  reset.classList.toggle("u-hidden", resetHidden);
  reset.addEventListener("click", () => _historyCompareApplyViewMode(defaultMode, data));
  controls.appendChild(reset);
  const contextControls = _renderHistoryCompareContextControls(data, viewMode);
  if (contextControls) controls.appendChild(contextControls);
  _historyCompareControlsEnhanceAppSelects(controls);
  return controls;
}
function _renderHistoryCompareContextControls(data, viewMode) {
  if (viewMode === "changes_only" || viewMode === "findings_only") return null;
  const selected = _historyCompareControlsCoerceContext(data._compareContext || _historyCompareControlsStoredContext());
  const contextSelect = document.createElement("select");
  contextSelect.className = "form-select history-compare-context-select";
  contextSelect.setAttribute("aria-label", "Run comparison context");
  contextSelect.dataset.portalMenu = "true";
  [
    ["3", "Context: ±3"],
    ["10", "Context: ±10"],
    ["all", "Context: All"]
  ].forEach(([value, label]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    contextSelect.appendChild(option);
  });
  contextSelect.value = selected;
  contextSelect.addEventListener("change", () => _historyCompareApplyContext(contextSelect.value, data));
  return contextSelect;
}
function _historyCompareSummaryText(data, deltas = {}) {
  const totalsForCopy = data.totals || {};
  return [
    `Compare: ${data.left.command} -> ${data.right.command}`,
    `Exit: ${deltas.exit_code?.left ?? "n/a"} -> ${deltas.exit_code?.right ?? "n/a"}`,
    `Lines: ${_historyCompareControlsFormatDelta(deltas.output_lines?.delta || 0)}`,
    `Findings: ${_historyCompareControlsFormatDelta(deltas.findings?.delta || 0)}`,
    `Changed: ${Number(totalsForCopy.changed_line_count || 0)}`,
    `Added: ${Number(totalsForCopy.added_line_count || 0)}`,
    `Removed: ${Number(totalsForCopy.removed_line_count || 0)}`,
    `Unchanged: ${Number(totalsForCopy.equal_line_count || 0)}`
  ].join("\n");
}
function _renderHistoryCompareActionsMenu(data, deltas = {}) {
  const wrap = document.createElement("div");
  wrap.className = "history-compare-actions-menu-wrap save-menu-wrap save-menu-down";
  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "btn btn-secondary btn-compact history-compare-actions-trigger";
  trigger.textContent = "Actions";
  trigger.setAttribute("aria-haspopup", "menu");
  trigger.setAttribute("aria-expanded", "false");
  const menu = document.createElement("div");
  menu.className = "history-compare-actions-menu save-menu dropdown-surface";
  menu.setAttribute("role", "menu");
  const addItem = (label, onClick) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "dropdown-item dropdown-item-compact";
    item.setAttribute("role", "menuitem");
    item.textContent = label;
    item.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      _closeHistoryCompareActionMenus();
      onClick(item);
    });
    menu.appendChild(item);
    return item;
  };
  addItem("Restore A", () => {
    _historyCompareControlsRestoreRun(data.left, { hidePanelOnSuccess: false }).then(() => _historyCompareControlsCloseOverlay()).catch(() => _historyCompareControlsShowToast("Failed to restore run", "error"));
  });
  addItem("Restore B", () => {
    _historyCompareControlsRestoreRun(data.right, { hidePanelOnSuccess: false }).then(() => _historyCompareControlsCloseOverlay()).catch(() => _historyCompareControlsShowToast("Failed to restore run", "error"));
  });
  addItem("Restore Both", (item) => {
    item.disabled = true;
    window._restoreBothHistoryCompareRuns(data.left, data.right).then(() => _historyCompareControlsCloseOverlay()).catch((err) => {
      item.disabled = false;
      if (err && err.message === "not enough tab capacity") return;
      _historyCompareControlsShowToast("Failed to restore both runs", "error");
    });
  });
  addItem("Copy summary", () => {
    _historyCompareControlsCopyText(_historyCompareSummaryText(data, deltas)).then(() => _historyCompareControlsShowToast("Comparison summary copied")).catch(() => _historyCompareControlsShowToast("Failed to copy summary", "error"));
  });
  wrap.dataset.portalMenu = "true";
  trigger.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    const open = !wrap.classList.contains("open");
    _closeHistoryCompareActionMenus(open ? wrap : null);
    wrap.classList.toggle("open", open);
    trigger.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) {
      _historyCompareControlsPortalDropdownMenu(wrap, trigger, menu);
      wrap._portaledMenu = menu;
    } else {
      _historyCompareControlsUnportalDropdownMenu(menu);
      wrap._portaledMenu = null;
    }
  });
  _historyCompareControlsBindPressable(trigger);
  wrap.append(trigger, menu);
  return wrap;
}

export {
  _historyCompareApplyViewMode,
  _historyCompareApplyContext,
  _closeHistoryCompareActionMenus,
  _renderHistoryCompareDisplayControls,
  _renderHistoryCompareContextControls,
  _historyCompareSummaryText,
  _renderHistoryCompareActionsMenu
};
