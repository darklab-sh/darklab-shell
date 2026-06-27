import {
  DarklabHistoryCore,
  DarklabPreferenceCore,
  getCompareContextPreference,
  getCompareViewModePreference,
  getPreference
} from "./static-chunk-q4tud76d.13497a252739.js";
import {
  useMobileTerminalViewportMode
} from "./static-chunk-yu6ty7m2.96c3ee208a44.js";

// app/static/js/features/run-comparison/history_compare_core.js
var DarklabHistoryCompareCore = (function(global) {
  function historyCore() {
    return typeof DarklabHistoryCore !== "undefined" && DarklabHistoryCore || null;
  }
  function compareFormatDate2(value) {
    return historyCore().compareFormatDate(value);
  }
  function compareDateGroupLabel2(value) {
    return historyCore().compareDateGroupLabel(value);
  }
  function compareFormatDuration2(seconds) {
    return historyCore().compareFormatDuration(seconds);
  }
  function compareFormatDelta2(value, suffix = "") {
    return historyCore().compareFormatDelta(value, suffix);
  }
  function totalChangedLines2(totals = {}) {
    return Number(totals.changed_line_count || 0) + Number(totals.added_line_count || 0) + Number(totals.removed_line_count || 0);
  }
  function omittedTotal2(truncated = {}) {
    const lineOmitted = truncated && truncated.lines_omitted ? truncated.lines_omitted : {};
    return Number(truncated.hunks_omitted || 0) + Number(lineOmitted.total || 0);
  }
  function lineLimit2(limits = {}) {
    const limit = Number(limits.line_display_truncate || 0);
    return Number.isFinite(limit) && limit > 0 ? limit : 4e3;
  }
  function preferenceCore() {
    return typeof DarklabPreferenceCore !== "undefined" && DarklabPreferenceCore || null;
  }
  function coerceViewMode2(value) {
    const core = preferenceCore();
    if (core && typeof core.coerceCompareViewMode === "function") return core.coerceCompareViewMode(value);
    return ["auto", "side_by_side", "unified", "changes_only", "findings_only"].includes(value) ? value : "auto";
  }
  function coerceContext2(value) {
    const core = preferenceCore();
    if (core && typeof core.coerceCompareContextMode === "function") return core.coerceCompareContextMode(value);
    const normalized = String(value || "").trim().toLowerCase();
    return ["3", "10", "all"].includes(normalized) ? normalized : "3";
  }
  function storedViewMode2() {
    const getCompareViewModePreference2 = typeof getCompareViewModePreference === "function" ? getCompareViewModePreference : null;
    const getPreference2 = typeof getPreference === "function" ? getPreference : null;
    if (typeof getCompareViewModePreference2 === "function") {
      return coerceViewMode2(getCompareViewModePreference2());
    }
    if (typeof getPreference2 === "function") return coerceViewMode2(getPreference2("pref_compare_view_mode"));
    return "auto";
  }
  function storedContext2() {
    const getCompareContextPreference2 = typeof getCompareContextPreference === "function" ? getCompareContextPreference : null;
    const getPreference2 = typeof getPreference === "function" ? getPreference : null;
    if (typeof getCompareContextPreference2 === "function") {
      return coerceContext2(getCompareContextPreference2());
    }
    if (typeof getPreference2 === "function") return coerceContext2(getPreference2("pref_compare_context"));
    return "3";
  }
  function useMobileViewportMode() {
    const useMobile = typeof useMobileTerminalViewportMode !== "undefined" && useMobileTerminalViewportMode || null;
    return typeof useMobile === "function" ? useMobile() : false;
  }
  function viewportMode2() {
    if (useMobileViewportMode()) return "unified";
    if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
      try {
        if (window.matchMedia("(max-width: 760px)").matches) return "unified";
      } catch (_) {
      }
    }
    return "side_by_side";
  }
  function usesMobileLayout2() {
    return viewportMode2() === "unified";
  }
  function resolveViewMode2(value = null) {
    const mode = coerceViewMode2(value || storedViewMode2());
    const currentViewportMode = viewportMode2();
    if (mode === "auto") return currentViewportMode;
    if (mode === "side_by_side" && currentViewportMode === "unified") return "unified";
    return mode;
  }
  function viewModeOptions2() {
    const options = [
      ["side_by_side", "Side-by-side"],
      ["unified", "Unified"],
      ["changes_only", "Changes only"],
      ["findings_only", "Findings only"]
    ];
    if (viewportMode2() === "unified") {
      return options.filter(([value]) => value !== "side_by_side");
    }
    return options;
  }
  function contextLimit2(value = null) {
    const context = coerceContext2(value || storedContext2());
    if (context === "all") return null;
    return Number(context);
  }
  function number2(value, fallback = null) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }
  function cssEscape2(value) {
    const text = String(value);
    if (typeof CSS !== "undefined" && CSS && typeof CSS.escape === "function") return CSS.escape(text);
    return text.replace(/["\\]/g, "\\$&");
  }
  function bucketTone2(bucket = {}) {
    const changed = Number(bucket.changed || 0);
    const added = Number(bucket.added || 0);
    const removed = Number(bucket.removed || 0);
    const equal = Number(bucket.equal || 0);
    if (changed > 0) return "changed";
    if (added > 0 || removed > 0) return added > removed ? "added" : "removed";
    if (equal > 0) return "equal";
    return "empty";
  }
  function buildAnchorMap2(data = {}) {
    const map = { a: /* @__PURE__ */ new Map(), b: /* @__PURE__ */ new Map() };
    const findingObjects = data.objects?.findings || {};
    const addAnchor = (side, item) => {
      const index = number2(item?.compare_line_index);
      if (index === null) return;
      const existing = map[side].get(index) || [];
      existing.push(item);
      map[side].set(index, existing);
    };
    (Array.isArray(findingObjects.added) ? findingObjects.added : []).forEach((item) => addAnchor("b", item));
    (Array.isArray(findingObjects.removed) ? findingObjects.removed : []).forEach((item) => addAnchor("a", item));
    return map;
  }
  function anchorTone2(items = []) {
    const severities = items.map((item) => String(item?.severity || "").toLowerCase());
    if (severities.some((value) => value === "critical" || value === "high")) return "high";
    if (severities.some((value) => value === "medium")) return "medium";
    return "info";
  }
  const api = Object.freeze({
    anchorTone: anchorTone2,
    bucketTone: bucketTone2,
    buildAnchorMap: buildAnchorMap2,
    coerceContext: coerceContext2,
    coerceViewMode: coerceViewMode2,
    compareDateGroupLabel: compareDateGroupLabel2,
    compareFormatDate: compareFormatDate2,
    compareFormatDelta: compareFormatDelta2,
    compareFormatDuration: compareFormatDuration2,
    contextLimit: contextLimit2,
    cssEscape: cssEscape2,
    lineLimit: lineLimit2,
    number: number2,
    omittedTotal: omittedTotal2,
    resolveViewMode: resolveViewMode2,
    storedContext: storedContext2,
    storedViewMode: storedViewMode2,
    totalChangedLines: totalChangedLines2,
    usesMobileLayout: usesMobileLayout2,
    viewportMode: viewportMode2,
    viewModeOptions: viewModeOptions2
  });
  return api;
})(typeof window !== "undefined" ? window : globalThis);
var {
  anchorTone,
  bucketTone,
  buildAnchorMap,
  coerceContext,
  coerceViewMode,
  compareDateGroupLabel,
  compareFormatDate,
  compareFormatDelta,
  compareFormatDuration,
  contextLimit,
  cssEscape,
  lineLimit,
  number,
  omittedTotal,
  resolveViewMode,
  storedContext,
  storedViewMode,
  totalChangedLines,
  usesMobileLayout,
  viewportMode,
  viewModeOptions
} = DarklabHistoryCompareCore;

export {
  DarklabHistoryCompareCore,
  anchorTone,
  bucketTone,
  buildAnchorMap,
  coerceContext,
  coerceViewMode,
  compareDateGroupLabel,
  compareFormatDate,
  compareFormatDelta,
  compareFormatDuration,
  contextLimit,
  cssEscape,
  lineLimit,
  number,
  omittedTotal,
  resolveViewMode,
  storedContext,
  storedViewMode,
  totalChangedLines,
  usesMobileLayout,
  viewportMode,
  viewModeOptions
};
