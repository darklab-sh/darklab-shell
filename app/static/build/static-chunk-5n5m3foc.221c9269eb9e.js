import {
  _renderHistoryCompareActionsMenu,
  _renderHistoryCompareDisplayControls
} from "./static-chunk-qfj2t5ty.adab2fb8d150.js";
import {
  _historyCompareScrollToLine,
  _renderHistoryCompareMinimap,
  _renderHistoryCompareNav
} from "./static-chunk-q73lj3nt.7281eb4df962.js";
import {
  _historyCompareRunCard,
  _renderHistoryCompareLauncher
} from "./static-chunk-j2zotilo.3a34007ff999.js";
import {
  anchorTone,
  buildAnchorMap,
  coerceContext,
  coerceViewMode,
  compareFormatDelta,
  contextLimit,
  cssEscape,
  lineLimit,
  number,
  omittedTotal,
  resolveViewMode,
  storedContext,
  storedViewMode,
  totalChangedLines
} from "./static-chunk-ojljtymm.2193d9be0037.js";
import {
  _ensureHistoryCompareOverlay,
  _openHistoryCompareOverlay
} from "./static-chunk-dil5yyjg.6d28df9092db.js";
import {
  restoreHistoryRunIntoTab
} from "./static-chunk-w26p2d54.313c0b69fdbf.js";
import {
  setHistoryCompareHandlers
} from "./static-chunk-ylgcpl7n.752d37b456dc.js";
import {
  activateTab,
  createTab
} from "./static-chunk-rhx4oneb.a213558b0b82.js";
import {
  showToast
} from "./static-chunk-poi5czx6.3f5c94749765.js";
import {
  bindPressable
} from "./static-chunk-fik64llj.1291b1f4f79b.js";
import {
  useMobileTerminalViewportMode
} from "./static-chunk-yu6ty7m2.96c3ee208a44.js";
import {
  getTabs
} from "./static-chunk-sgyzdmxn.7d1842f12a94.js";
import {
  APP_CONFIG
} from "./static-chunk-tym5o2af.a748583ae389.js";
import {
  apiFetch,
  hasRuntimeHandler,
  logClientError
} from "./static-chunk-i34eiczq.4bb950c346dc.js";

// app/static/js/features/run-comparison/history_compare_renderer.js
var HISTORY_COMPARE_RENDERER_GLOBAL = typeof window !== "undefined" ? window : globalThis;
var _historyCompareRendererRowHeightFrame = null;
var _historyCompareRendererRowResizeObserver = null;
var _historyCompareRendererRowPairSequence = 0;
var _historyCompareRendererUnitSequence = 0;
var _historyCompareApiFetchFallbackLogged = false;
function _historyCompareRendererGlobalFunction(name) {
  const fn = HISTORY_COMPARE_RENDERER_GLOBAL && HISTORY_COMPARE_RENDERER_GLOBAL[name];
  return typeof fn === "function" ? fn : null;
}
function _historyCompareRendererCoreFunction(name) {
  const core = HISTORY_COMPARE_RENDERER_GLOBAL.DarklabHistoryCompareCore || null;
  return core && typeof core[name] === "function" ? core[name] : null;
}
function _historyCompareRendererApiFetch(url, options, details = {}) {
  const api = typeof apiFetch === "function" && typeof hasRuntimeHandler === "function" && hasRuntimeHandler("apiFetch") ? apiFetch : _historyCompareRendererGlobalFunction("apiFetch");
  if (typeof api === "function") return api(url, options);
  if (!_historyCompareApiFetchFallbackLogged) {
    _historyCompareApiFetchFallbackLogged = true;
    _historyCompareRendererLogClientError("history compare apiFetch fallback", null, {
      event: "HISTORY_COMPARE_API_FETCH_FALLBACK",
      level: "warning",
      left_id: String(details.leftId || ""),
      right_id: String(details.rightId || ""),
      url_path: _historyCompareRendererUrlPath(url)
    });
  }
  return fetch(url, options);
}
function _historyCompareRendererUrlPath(url) {
  try {
    const parsed = new URL(String(url || ""), "http://localhost/");
    return `${parsed.pathname}${parsed.search}`;
  } catch (_) {
    return String(url || "").split("#", 1)[0].slice(0, 300);
  }
}
function _historyCompareRendererLogClientError(context, err, details = {}) {
  const logger = typeof logClientError === "function" && typeof hasRuntimeHandler === "function" && hasRuntimeHandler("logClientError") ? logClientError : _historyCompareRendererGlobalFunction("logClientError");
  if (typeof logger === "function") logger(context, err, details);
}
function _historyCompareRendererLineLimit(limits) {
  const lineLimit2 = typeof lineLimit !== "undefined" && lineLimit || _historyCompareRendererCoreFunction("lineLimit");
  if (typeof lineLimit2 === "function") return lineLimit2(limits);
  const limit = Number(limits?.line_display_truncate || 0);
  return Number.isFinite(limit) && limit > 0 ? limit : 4e3;
}
function _historyCompareRendererAnchorTone(items) {
  const tone = typeof anchorTone !== "undefined" && anchorTone || _historyCompareRendererCoreFunction("anchorTone");
  return typeof tone === "function" ? tone(items) : "info";
}
function _historyCompareRendererCssEscape(value) {
  const escape = typeof cssEscape !== "undefined" && cssEscape || _historyCompareRendererCoreFunction("cssEscape");
  return typeof escape === "function" ? escape(value) : String(value);
}
function _historyCompareRendererNumber(value, fallback = null) {
  const number2 = typeof number !== "undefined" && number || _historyCompareRendererCoreFunction("number");
  if (typeof number2 === "function") return number2(value, fallback);
  if (value === null || typeof value === "undefined" || value === "") return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}
function _historyCompareRendererUseMobile() {
  const useMobile = typeof useMobileTerminalViewportMode !== "undefined" && useMobileTerminalViewportMode || _historyCompareRendererGlobalFunction("useMobileTerminalViewportMode");
  return typeof useMobile === "function" ? useMobile() : false;
}
function _historyCompareRendererShowToast(message, tone = "success") {
  const toast = typeof showToast !== "undefined" && showToast || _historyCompareRendererGlobalFunction("showToast");
  if (typeof toast === "function") toast(message, tone);
}
function _historyCompareRendererBindPressable(el) {
  const bind = typeof bindPressable !== "undefined" && bindPressable || _historyCompareRendererGlobalFunction("bindPressable");
  if (typeof bind === "function") bind(el);
}
function _historyCompareRendererBuildAnchorMap(data) {
  const build = typeof buildAnchorMap !== "undefined" && buildAnchorMap || _historyCompareRendererCoreFunction("buildAnchorMap");
  const built = typeof build === "function" ? build(data) : null;
  if (built && built.a instanceof Map && built.b instanceof Map && (built.a.size || built.b.size)) return built;
  const map = { a: /* @__PURE__ */ new Map(), b: /* @__PURE__ */ new Map() };
  const findingObjects = data?.objects?.findings || {};
  const addAnchor = (side, item) => {
    const index = _historyCompareRendererNumber(item?.compare_line_index);
    if (index === null) return;
    const existing = map[side].get(index) || [];
    existing.push(item);
    map[side].set(index, existing);
  };
  (Array.isArray(findingObjects.added) ? findingObjects.added : []).forEach((item) => addAnchor("b", item));
  (Array.isArray(findingObjects.removed) ? findingObjects.removed : []).forEach((item) => addAnchor("a", item));
  return map;
}
function _historyCompareRendererOmittedTotal(truncated) {
  const omitted = typeof omittedTotal !== "undefined" && omittedTotal || _historyCompareRendererCoreFunction("omittedTotal");
  return typeof omitted === "function" ? omitted(truncated) : 0;
}
function _historyCompareRendererStoredViewMode() {
  const stored = typeof storedViewMode !== "undefined" && storedViewMode || _historyCompareRendererCoreFunction("storedViewMode");
  return typeof stored === "function" ? stored() : "auto";
}
function _historyCompareRendererStoredContext() {
  const stored = typeof storedContext !== "undefined" && storedContext || _historyCompareRendererCoreFunction("storedContext");
  return typeof stored === "function" ? stored() : "3";
}
function _historyCompareRendererCoerceViewMode(value) {
  const coerce = typeof coerceViewMode !== "undefined" && coerceViewMode || _historyCompareRendererCoreFunction("coerceViewMode");
  return typeof coerce === "function" ? coerce(value) : value;
}
function _historyCompareRendererCoerceContext(value) {
  const coerce = typeof coerceContext !== "undefined" && coerceContext || _historyCompareRendererCoreFunction("coerceContext");
  return typeof coerce === "function" ? coerce(value) : value;
}
function _historyCompareRendererResolveViewMode(value) {
  const resolve = typeof resolveViewMode !== "undefined" && resolveViewMode || _historyCompareRendererCoreFunction("resolveViewMode");
  return typeof resolve === "function" ? resolve(value) : value;
}
function _historyCompareRendererTotalChangedLines(totals) {
  const total = typeof totalChangedLines !== "undefined" && totalChangedLines || _historyCompareRendererCoreFunction("totalChangedLines");
  return typeof total === "function" ? total(totals) : 0;
}
function _historyCompareRendererContextLimit(contextMode) {
  const limit = typeof contextLimit !== "undefined" && contextLimit || _historyCompareRendererCoreFunction("contextLimit");
  if (typeof limit === "function") return limit(contextMode);
  if (contextMode === "all") return null;
  const parsed = Number(contextMode);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 3;
}
function _historyCompareRendererFormatDelta(value, suffix = "") {
  const format = typeof compareFormatDelta !== "undefined" && compareFormatDelta || _historyCompareRendererCoreFunction("compareFormatDelta");
  return typeof format === "function" ? format(value, suffix) : String(value);
}
function _historyCompareRendererScrollToLine(side, index, options) {
  const scroll = typeof _historyCompareScrollToLine !== "undefined" && _historyCompareScrollToLine || _historyCompareRendererGlobalFunction("_historyCompareScrollToLine");
  return typeof scroll === "function" ? scroll(side, index, options) : false;
}
function _historyCompareRendererNav(data) {
  const render = typeof _renderHistoryCompareNav !== "undefined" && _renderHistoryCompareNav || _historyCompareRendererGlobalFunction("_renderHistoryCompareNav");
  return typeof render === "function" ? render(data) : document.createDocumentFragment();
}
function _historyCompareRendererMinimap(buckets) {
  const render = typeof _renderHistoryCompareMinimap !== "undefined" && _renderHistoryCompareMinimap || _historyCompareRendererGlobalFunction("_renderHistoryCompareMinimap");
  return typeof render === "function" ? render(buckets) : document.createDocumentFragment();
}
function _historyCompareRendererDisplayControls(data, viewMode) {
  const render = typeof _renderHistoryCompareDisplayControls !== "undefined" && _renderHistoryCompareDisplayControls || _historyCompareRendererGlobalFunction("_renderHistoryCompareDisplayControls");
  return typeof render === "function" ? render(data, viewMode) : document.createDocumentFragment();
}
function _historyCompareRendererActionsMenu(data, deltas) {
  const render = typeof _renderHistoryCompareActionsMenu !== "undefined" && _renderHistoryCompareActionsMenu || _historyCompareRendererGlobalFunction("_renderHistoryCompareActionsMenu");
  return typeof render === "function" ? render(data, deltas) : document.createDocumentFragment();
}
function _historyCompareRendererRunCard(run, label) {
  const render = typeof _historyCompareRunCard !== "undefined" && _historyCompareRunCard || _historyCompareRendererGlobalFunction("_historyCompareRunCard");
  return typeof render === "function" ? render(run, label) : document.createDocumentFragment();
}
function _historyCompareRendererMaybeLauncher() {
  const render = typeof _renderHistoryCompareLauncher !== "undefined" && _renderHistoryCompareLauncher || _historyCompareRendererGlobalFunction("_renderHistoryCompareLauncher");
  if (typeof render === "function") render();
}
function _historyCompareRendererTabs() {
  const getTabsFn = _historyCompareRendererGlobalFunction("getTabs");
  if (typeof getTabsFn === "function") return getTabsFn();
  if (typeof getTabs === "function") return getTabs();
  const stateTabs = HISTORY_COMPARE_RENDERER_GLOBAL.tabs;
  if (Array.isArray(stateTabs)) return stateTabs;
  return [];
}
function _historyCompareRendererCreateTab(label) {
  const create = _historyCompareRendererGlobalFunction("createTab") || typeof createTab !== "undefined" && createTab;
  return typeof create === "function" ? create(label) : null;
}
function _historyCompareRendererActivateTab(tabId, options) {
  const activate = _historyCompareRendererGlobalFunction("activateTab") || typeof activateTab !== "undefined" && activateTab;
  if (typeof activate === "function") activate(tabId, options);
}
function _historyCompareRendererRestoreRun(run, options) {
  const restore = _historyCompareRendererGlobalFunction("restoreHistoryRunIntoTab") || typeof restoreHistoryRunIntoTab !== "undefined" && restoreHistoryRunIntoTab;
  return typeof restore === "function" ? restore(run, options) : Promise.reject(new Error("history restore unavailable"));
}
function _historyCompareRendererEnsureOverlay() {
  const ensure = typeof _ensureHistoryCompareOverlay !== "undefined" && _ensureHistoryCompareOverlay || _historyCompareRendererGlobalFunction("_ensureHistoryCompareOverlay");
  return typeof ensure === "function" ? ensure() : null;
}
function _historyCompareRendererOpenOverlay() {
  const open = typeof _openHistoryCompareOverlay !== "undefined" && _openHistoryCompareOverlay || _historyCompareRendererGlobalFunction("_openHistoryCompareOverlay");
  if (typeof open === "function") open();
}
function _compareMetricCell(label, value, tone = "") {
  const cell = document.createElement("div");
  cell.className = `history-compare-metric${tone ? ` ${tone}` : ""}`;
  const labelEl = document.createElement("div");
  labelEl.className = "history-compare-metric-label";
  labelEl.textContent = label;
  const valueEl = document.createElement("div");
  valueEl.className = "history-compare-metric-value";
  valueEl.textContent = value;
  cell.appendChild(labelEl);
  cell.appendChild(valueEl);
  return cell;
}
function _appendHistoryCompareSegments(parent, segments, fallbackText) {
  const safeSegments = Array.isArray(segments) ? segments : [];
  if (!safeSegments.length) {
    parent.textContent = fallbackText || "";
    return;
  }
  safeSegments.forEach((segment) => {
    const span = document.createElement("span");
    span.textContent = segment && typeof segment.text === "string" ? segment.text : "";
    if (segment && segment.changed) span.className = "history-compare-line-delta";
    parent.appendChild(span);
  });
}
function _renderHistoryCompareLineText(line, segments = null, limits = {}) {
  const code = document.createElement("code");
  const rawText = String(line && line.text || "");
  const limit = _historyCompareRendererLineLimit(limits);
  const truncated = rawText.length > limit;
  const visibleText = truncated ? rawText.slice(0, limit) : rawText;
  const safeSegments = Array.isArray(segments) ? segments : [];
  if (safeSegments.length && !truncated) {
    _appendHistoryCompareSegments(code, safeSegments, rawText);
  } else {
    code.textContent = visibleText;
  }
  if (truncated) {
    const expander = document.createElement("button");
    expander.type = "button";
    expander.className = "chip chip-action history-compare-line-expander";
    expander.textContent = `... +${(rawText.length - limit).toLocaleString()} chars`;
    expander.addEventListener("click", (event) => {
      event.stopPropagation();
      const split = expander.closest?.(".history-compare-split");
      code.textContent = rawText;
      expander.remove();
      _scheduleHistoryCompareRowPairHeightSync(split);
    });
    const wrap = document.createElement("span");
    wrap.className = "history-compare-line-text-wrap";
    wrap.appendChild(code);
    wrap.appendChild(expander);
    return wrap;
  }
  return code;
}
function _renderHistoryComparePaneRow(line, {
  sideLabel = "",
  signClass = "",
  rowClass = "",
  segments = null,
  limits = {},
  side = "",
  compareLineIndex = null,
  anchorItems = []
} = {}) {
  const row = document.createElement("div");
  row.className = `history-compare-row${rowClass ? ` ${rowClass}` : ""}`;
  if (side) row.dataset.side = side;
  if (Number.isFinite(compareLineIndex)) row.dataset.compareLineIndex = String(compareLineIndex);
  if (line && line.kind) row.dataset.compareKind = String(line.kind);
  if (line && line.role) row.dataset.compareRole = String(line.role);
  const mark = document.createElement("span");
  mark.className = `history-compare-line-mark${signClass ? ` ${signClass}` : ""}`;
  mark.textContent = sideLabel;
  row.appendChild(mark);
  const anchorSlot = document.createElement("span");
  anchorSlot.className = "history-compare-line-anchor-slot";
  const safeAnchors = Array.isArray(anchorItems) ? anchorItems : [];
  if (safeAnchors.length && Number.isFinite(compareLineIndex)) {
    const marker = document.createElement("button");
    marker.type = "button";
    marker.className = `btn btn-ghost history-compare-finding-marker is-${_historyCompareRendererAnchorTone(safeAnchors)}`;
    marker.setAttribute("aria-label", "Jump to linked finding");
    marker.addEventListener("click", (event) => {
      event.stopPropagation();
      const findingRow = document.querySelector(
        `.history-compare-object-row[data-object-kind="finding"][data-compare-side="${side}"][data-compare-line-index="${_historyCompareRendererCssEscape(compareLineIndex)}"]`
      );
      if (typeof findingRow?.scrollIntoView === "function") {
        findingRow.scrollIntoView({ block: "center", inline: "nearest" });
      }
      if (findingRow) {
        findingRow.classList.remove("history-compare-line-pulse");
        void findingRow.offsetWidth;
        findingRow.classList.add("history-compare-line-pulse");
        setTimeout(() => findingRow.classList.remove("history-compare-line-pulse"), 900);
      }
    });
    anchorSlot.appendChild(marker);
  }
  row.appendChild(anchorSlot);
  row.appendChild(_renderHistoryCompareLineText(line, segments, limits));
  return row;
}
function _historyCompareAttachFindingMarker(row, side, compareLineIndex, anchors) {
  if (!row || row.querySelector(".history-compare-finding-marker")) return;
  const safeAnchors = Array.isArray(anchors) ? anchors : [];
  if (!safeAnchors.length) return;
  const marker = document.createElement("button");
  marker.type = "button";
  marker.className = `btn btn-ghost history-compare-finding-marker is-${_historyCompareRendererAnchorTone(safeAnchors)}`;
  marker.setAttribute("aria-label", "Jump to linked finding");
  marker.addEventListener("click", (event) => {
    event.stopPropagation();
    const findingRow = document.querySelector(
      `.history-compare-object-row[data-object-kind="finding"][data-compare-side="${side}"][data-compare-line-index="${_historyCompareRendererCssEscape(compareLineIndex)}"]`
    );
    if (typeof findingRow?.scrollIntoView === "function") {
      findingRow.scrollIntoView({ block: "center", inline: "nearest" });
    }
    if (findingRow) {
      findingRow.classList.remove("history-compare-line-pulse");
      void findingRow.offsetWidth;
      findingRow.classList.add("history-compare-line-pulse");
      setTimeout(() => findingRow.classList.remove("history-compare-line-pulse"), 900);
    }
  });
  const slot = row.querySelector(".history-compare-line-anchor-slot");
  if (slot) slot.appendChild(marker);
}
function _syncHistoryCompareFindingMarkers(data) {
  const anchorMap = _historyCompareRendererBuildAnchorMap(data);
  ["a", "b"].forEach((side) => {
    anchorMap[side].forEach((anchors, compareLineIndex) => {
      const row = document.querySelector(
        `.history-compare-pane[data-side="${side}"] .history-compare-row[data-compare-line-index="${_historyCompareRendererCssEscape(compareLineIndex)}"]`
      );
      _historyCompareAttachFindingMarker(row, side, compareLineIndex, anchors);
    });
  });
}
function _renderHistoryCompareSpacer(label = "") {
  const row = document.createElement("div");
  row.className = "history-compare-row history-compare-row-spacer";
  row.setAttribute("aria-hidden", "true");
  const mark = document.createElement("span");
  mark.textContent = label;
  row.appendChild(mark);
  row.appendChild(document.createElement("span"));
  row.appendChild(document.createElement("span"));
  return row;
}
function _historyCompareRowHeight(row) {
  if (!row) return 0;
  const rect = typeof row.getBoundingClientRect === "function" ? row.getBoundingClientRect() : null;
  return Math.ceil(Math.max(Number(rect?.height || 0), Number(row.offsetHeight || 0)));
}
function _historyCompareUsesStackedMobilePanes(wrap) {
  const mobile = _historyCompareRendererUseMobile();
  const stacked = wrap?.classList?.contains("is-unified") || wrap?.classList?.contains("is-changes-only");
  return Boolean(mobile && stacked);
}
function _clearHistoryCompareRowPairHeights(wrap) {
  wrap?.querySelectorAll?.(".history-compare-row[data-compare-pair]").forEach((row) => {
    row.style.minHeight = "";
  });
}
function _syncHistoryCompareRowPairHeights(wrap) {
  if (!wrap || !wrap.isConnected) return;
  if (_historyCompareUsesStackedMobilePanes(wrap)) {
    _clearHistoryCompareRowPairHeights(wrap);
    return;
  }
  const pairs = /* @__PURE__ */ new Map();
  wrap.querySelectorAll(".history-compare-row[data-compare-pair]").forEach((row) => {
    row.style.minHeight = "";
    const key = row.dataset.comparePair || "";
    if (!key) return;
    const rows = pairs.get(key) || [];
    rows.push(row);
    pairs.set(key, rows);
  });
  pairs.forEach((rows) => {
    if (rows.length < 2) return;
    const height = Math.max(...rows.map(_historyCompareRowHeight));
    if (!height) return;
    rows.forEach((row) => {
      row.style.minHeight = `${height}px`;
    });
  });
}
function _scheduleHistoryCompareRowPairHeightSync(wrap) {
  if (!wrap) return;
  if (_historyCompareRendererRowHeightFrame !== null) {
    const cancel = typeof cancelAnimationFrame === "function" ? cancelAnimationFrame : clearTimeout;
    cancel(_historyCompareRendererRowHeightFrame);
  }
  const raf = typeof requestAnimationFrame === "function" ? requestAnimationFrame : (callback) => setTimeout(callback, 0);
  _historyCompareRendererRowHeightFrame = raf(() => {
    _historyCompareRendererRowHeightFrame = null;
    _syncHistoryCompareRowPairHeights(wrap);
  });
}
function _observeHistoryCompareRowPairHeights(wrap) {
  if (_historyCompareRendererRowResizeObserver) {
    _historyCompareRendererRowResizeObserver.disconnect();
  }
  if (typeof ResizeObserver === "function" && wrap) {
    _historyCompareRendererRowResizeObserver = new ResizeObserver(() => {
      _scheduleHistoryCompareRowPairHeightSync(wrap);
    });
    _historyCompareRendererRowResizeObserver.observe(wrap);
  } else {
    _historyCompareRendererRowResizeObserver = null;
  }
  _scheduleHistoryCompareRowPairHeightSync(wrap);
}
function _appendHistoryCompareRowPair(leftPane, rightPane, leftRow, rightRow, unitTone = "") {
  const pair = String(_historyCompareRendererRowPairSequence);
  _historyCompareRendererRowPairSequence += 1;
  leftRow.dataset.comparePair = pair;
  rightRow.dataset.comparePair = pair;
  if (unitTone) {
    const unit = String(_historyCompareRendererUnitSequence);
    _historyCompareRendererUnitSequence += 1;
    leftRow.dataset.compareUnitIndex = unit;
    rightRow.dataset.compareUnitIndex = unit;
    leftRow.dataset.compareUnitTone = unitTone;
    rightRow.dataset.compareUnitTone = unitTone;
  }
  leftPane.appendChild(leftRow);
  rightPane.appendChild(rightRow);
}
function _advanceHistoryCompareUnits(count) {
  _historyCompareRendererUnitSequence += Math.max(0, Number(count || 0));
}
function _historyCompareReplaceRenderEvents(hunk) {
  const events = [];
  (hunk.changed_pairs || []).forEach((pair) => {
    events.push({
      type: "pair",
      leftIndex: Number(pair.left_index),
      rightIndex: Number(pair.right_index),
      pair
    });
  });
  (hunk.left_unpaired || []).forEach((index) => {
    events.push({ type: "left", leftIndex: Number(index), rightIndex: null });
  });
  (hunk.right_unpaired || []).forEach((index) => {
    events.push({ type: "right", leftIndex: null, rightIndex: Number(index) });
  });
  const pending = events.filter((event) => (event.leftIndex === null || Number.isFinite(event.leftIndex)) && (event.rightIndex === null || Number.isFinite(event.rightIndex)));
  const ordered = [];
  const nextSideIndex = (side) => {
    const key = side === "left" ? "leftIndex" : "rightIndex";
    const indexes = pending.map((event) => event[key]).filter((index) => Number.isFinite(index));
    return indexes.length ? Math.min(...indexes) : null;
  };
  while (pending.length) {
    const nextLeft = nextSideIndex("left");
    const nextRight = nextSideIndex("right");
    let index = pending.findIndex((event) => (event.leftIndex === null || event.leftIndex === nextLeft) && (event.rightIndex === null || event.rightIndex === nextRight));
    if (index < 0) {
      index = pending.map((event, eventIndex) => ({
        eventIndex,
        order: Math.max(
          Number.isFinite(event.leftIndex) ? event.leftIndex : -1,
          Number.isFinite(event.rightIndex) ? event.rightIndex : -1
        )
      })).sort((a, b) => a.order - b.order || a.eventIndex - b.eventIndex)[0].eventIndex;
    }
    ordered.push(pending.splice(index, 1)[0]);
  }
  return ordered;
}
function _historyCompareFoldRange(hunk, side) {
  const context = hunk && hunk.context ? hunk.context : {};
  const leading = context.leading && Array.isArray(context.leading[side]) ? context.leading[side] : [];
  const trailing = context.trailing && Array.isArray(context.trailing[side]) ? context.trailing[side] : [];
  const bounds = hunk && hunk[side] ? hunk[side] : {};
  return {
    start: Number(bounds.start || 0) + leading.length,
    end: Math.max(Number(bounds.start || 0) + leading.length, Number(bounds.end || 0) - trailing.length)
  };
}
function _historyCompareLineUrl(data, side, start, end) {
  const params = new URLSearchParams();
  params.set("left", data.left_run_id || data.left?.id || "");
  params.set("right", data.right_run_id || data.right?.id || "");
  params.set("side", side === "left" ? "a" : "b");
  params.set("start", String(start));
  params.set("end", String(end));
  if (data.project_id) params.set("project_id", data.project_id);
  if (data.baseline_label) params.set("baseline_label", data.baseline_label);
  return `/history/compare/lines?${params.toString()}`;
}
function _fetchHistoryCompareFoldSide(data, hunk, side) {
  const range = _historyCompareFoldRange(hunk, side);
  if (range.start >= range.end) return Promise.resolve([]);
  const collected = [];
  const loadPage = (start) => _historyCompareRendererApiFetch(_historyCompareLineUrl(data, side, start, range.end)).then((resp) => resp.json()).then((payload) => {
    if (payload.error) throw new Error(payload.error);
    const lines = Array.isArray(payload.lines) ? payload.lines : [];
    collected.push(...lines);
    const nextStart = Number(payload.end);
    if (payload.truncated && !payload.range_clamped && Number.isFinite(nextStart) && nextStart > start && nextStart < range.end) {
      return loadPage(nextStart);
    }
    return collected;
  });
  return loadPage(range.start);
}
function _historyCompareSliceContextLines(lines, edge, contextLimit2) {
  const safeLines = Array.isArray(lines) ? lines : [];
  if (contextLimit2 === null) return safeLines;
  const limit = Math.max(0, Number(contextLimit2 || 0));
  if (!limit) return [];
  return edge === "leading" ? safeLines.slice(-limit) : safeLines.slice(0, limit);
}
function _appendHistoryCompareEqualHunk(leftPane, rightPane, hunk, data, rerender, anchorMap, options = {}) {
  const limits = data.limits || {};
  const contextLimit2 = Object.prototype.hasOwnProperty.call(options, "contextLimit") ? options.contextLimit : 3;
  const changesOnly = !!options.changesOnly;
  const context = hunk.context || {};
  const appendLines = (leftLines, rightLines, leftStart2 = 0, rightStart2 = 0) => {
    const count = Math.max(leftLines.length, rightLines.length);
    for (let index = 0; index < count; index += 1) {
      const leftCompareIndex = Number(leftStart2) + index;
      const rightCompareIndex = Number(rightStart2) + index;
      _appendHistoryCompareRowPair(
        leftPane,
        rightPane,
        leftLines[index] ? _renderHistoryComparePaneRow(leftLines[index], {
          sideLabel: "A",
          rowClass: "is-equal",
          limits,
          side: "a",
          compareLineIndex: leftCompareIndex,
          anchorItems: anchorMap?.a?.get(leftCompareIndex) || []
        }) : _renderHistoryCompareSpacer("A"),
        rightLines[index] ? _renderHistoryComparePaneRow(rightLines[index], {
          sideLabel: "B",
          rowClass: "is-equal",
          limits,
          side: "b",
          compareLineIndex: rightCompareIndex,
          anchorItems: anchorMap?.b?.get(rightCompareIndex) || []
        }) : _renderHistoryCompareSpacer("B"),
        "equal"
      );
    }
  };
  const makeFoldRow = (button) => {
    const row = document.createElement("div");
    row.className = "history-compare-row history-compare-row-fold";
    row.appendChild(document.createElement("span"));
    row.appendChild(document.createElement("span"));
    row.appendChild(button);
    return row;
  };
  const makeFoldButtonPair = (label, expand) => {
    const foldButtons = [];
    const setFoldButtons = (disabled, text) => {
      foldButtons.forEach((button) => {
        button.disabled = disabled;
        button.textContent = text;
      });
    };
    const makeFoldButton = () => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "btn btn-secondary btn-compact history-compare-fold";
      button.textContent = label;
      button.addEventListener("click", () => expand(setFoldButtons));
      foldButtons.push(button);
      return button;
    };
    _appendHistoryCompareRowPair(leftPane, rightPane, makeFoldRow(makeFoldButton()), makeFoldRow(makeFoldButton()));
  };
  if (Array.isArray(hunk.left?.lines) || Array.isArray(hunk.right?.lines)) {
    const leftLines = hunk.left?.lines || [];
    const rightLines = hunk.right?.lines || [];
    const leftStart2 = _historyCompareRendererNumber(hunk.left?.start, 0);
    const rightStart2 = _historyCompareRendererNumber(hunk.right?.start, 0);
    const total = Math.max(leftLines.length, rightLines.length);
    if (changesOnly) {
      _advanceHistoryCompareUnits(total);
    } else if (contextLimit2 === null || total <= contextLimit2 * 2) {
      appendLines(leftLines, rightLines, leftStart2, rightStart2);
    } else {
      const leadingCount = Math.max(0, contextLimit2);
      const trailingCount = Math.max(0, contextLimit2);
      appendLines(leftLines.slice(0, leadingCount), rightLines.slice(0, leadingCount), leftStart2, rightStart2);
      const omitted = Math.max(0, total - leadingCount - trailingCount);
      if (omitted > 0) {
        if (hunk._expanded) {
          makeFoldButtonPair("▾ Hide unchanged lines", () => {
            hunk._expanded = false;
            rerender();
          });
          appendLines(
            leftLines.slice(leadingCount, total - trailingCount),
            rightLines.slice(leadingCount, total - trailingCount),
            leftStart2 + leadingCount,
            rightStart2 + leadingCount
          );
        } else {
          makeFoldButtonPair(`▸ Show ${omitted.toLocaleString()} unchanged line(s)`, () => {
            hunk._expanded = true;
            rerender();
          });
          _advanceHistoryCompareUnits(omitted);
        }
      }
      appendLines(
        leftLines.slice(total - trailingCount),
        rightLines.slice(total - trailingCount),
        leftStart2 + Math.max(leadingCount, total - trailingCount),
        rightStart2 + Math.max(leadingCount, total - trailingCount)
      );
    }
    return;
  }
  const leftStart = _historyCompareRendererNumber(hunk.left?.start, 0);
  const rightStart = _historyCompareRendererNumber(hunk.right?.start, 0);
  const rawLeadingLeft = context.leading?.left || [];
  const rawLeadingRight = context.leading?.right || [];
  const rawTrailingLeft = context.trailing?.left || [];
  const rawTrailingRight = context.trailing?.right || [];
  const leadingLeft = changesOnly ? [] : _historyCompareSliceContextLines(rawLeadingLeft, "leading", contextLimit2);
  const leadingRight = changesOnly ? [] : _historyCompareSliceContextLines(rawLeadingRight, "leading", contextLimit2);
  const trailingLeft = changesOnly ? [] : _historyCompareSliceContextLines(rawTrailingLeft, "trailing", contextLimit2);
  const trailingRight = changesOnly ? [] : _historyCompareSliceContextLines(rawTrailingRight, "trailing", contextLimit2);
  appendLines(
    leadingLeft,
    leadingRight,
    leftStart + Math.max(0, rawLeadingLeft.length - leadingLeft.length),
    rightStart + Math.max(0, rawLeadingRight.length - leadingRight.length)
  );
  if (hunk._expanded) {
    const collapse = () => {
      hunk._expanded = false;
      rerender();
    };
    const makeCollapseButton = () => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "btn btn-secondary btn-compact history-compare-fold";
      button.textContent = "▾ Hide unchanged lines";
      button.addEventListener("click", collapse);
      return button;
    };
    _appendHistoryCompareRowPair(leftPane, rightPane, makeFoldRow(makeCollapseButton()), makeFoldRow(makeCollapseButton()));
    appendLines(
      hunk._expandedLeft || [],
      hunk._expandedRight || [],
      leftStart + leadingLeft.length,
      rightStart + leadingRight.length
    );
    _advanceHistoryCompareUnits(
      Number(context.omitted || 0) - Math.max(
        Array.isArray(hunk._expandedLeft) ? hunk._expandedLeft.length : 0,
        Array.isArray(hunk._expandedRight) ? hunk._expandedRight.length : 0
      )
    );
  } else if (Number(context.omitted || 0) > 0) {
    const label = `▸ Show ${Number(context.omitted).toLocaleString()} unchanged line(s)`;
    const expand = (setFoldButtons) => {
      if (hunk._loading) return;
      hunk._loading = true;
      setFoldButtons(true, "Loading unchanged lines...");
      const leftPromise = hunk._expandedLeft ? Promise.resolve(hunk._expandedLeft) : _fetchHistoryCompareFoldSide(data, hunk, "left");
      const rightPromise = hunk._expandedRight ? Promise.resolve(hunk._expandedRight) : _fetchHistoryCompareFoldSide(data, hunk, "right");
      Promise.all([leftPromise, rightPromise]).then(([leftLines, rightLines]) => {
        hunk._expandedLeft = leftLines;
        hunk._expandedRight = rightLines;
        hunk._expanded = true;
        hunk._loading = false;
        rerender();
      }).catch(() => {
        hunk._loading = false;
        setFoldButtons(false, label);
        _historyCompareRendererShowToast("Failed to load unchanged lines", "error");
      });
    };
    makeFoldButtonPair(label, expand);
    _advanceHistoryCompareUnits(context.omitted);
  }
  appendLines(
    trailingLeft,
    trailingRight,
    _historyCompareRendererNumber(hunk.left?.end, leftStart) - trailingLeft.length,
    _historyCompareRendererNumber(hunk.right?.end, rightStart) - trailingRight.length
  );
}
function _appendHistoryCompareReplaceHunk(leftPane, rightPane, hunk, data, anchorMap) {
  const limits = data.limits || {};
  const leftLines = hunk.left?.lines || [];
  const rightLines = hunk.right?.lines || [];
  const leftStart = _historyCompareRendererNumber(hunk.left?.start, 0);
  const rightStart = _historyCompareRendererNumber(hunk.right?.start, 0);
  _historyCompareReplaceRenderEvents(hunk).forEach((event) => {
    if (event.type === "pair") {
      const pair = event.pair || {};
      const leftLine = leftLines[pair.left_index] || {};
      const rightLine = rightLines[pair.right_index] || {};
      const segments = pair.segments || {};
      const leftCompareIndex = leftStart + Number(pair.left_index || 0);
      const rightCompareIndex = rightStart + Number(pair.right_index || 0);
      _appendHistoryCompareRowPair(
        leftPane,
        rightPane,
        _renderHistoryComparePaneRow(leftLine, {
          sideLabel: "A",
          signClass: "history-compare-line-removed",
          rowClass: `is-replace${pair.structural_change ? " is-structural-change" : ""}`,
          segments: segments.left,
          limits,
          side: "a",
          compareLineIndex: leftCompareIndex,
          anchorItems: anchorMap?.a?.get(leftCompareIndex) || []
        }),
        _renderHistoryComparePaneRow(rightLine, {
          sideLabel: "B",
          signClass: "history-compare-line-added",
          rowClass: `is-replace${pair.structural_change ? " is-structural-change" : ""}`,
          segments: segments.right,
          limits,
          side: "b",
          compareLineIndex: rightCompareIndex,
          anchorItems: anchorMap?.b?.get(rightCompareIndex) || []
        }),
        "changed"
      );
    } else if (event.type === "left") {
      const leftCompareIndex = leftStart + Number(event.leftIndex || 0);
      _appendHistoryCompareRowPair(
        leftPane,
        rightPane,
        _renderHistoryComparePaneRow(leftLines[event.leftIndex] || {}, {
          sideLabel: "-",
          signClass: "history-compare-line-removed",
          rowClass: "is-delete",
          limits,
          side: "a",
          compareLineIndex: leftCompareIndex,
          anchorItems: anchorMap?.a?.get(leftCompareIndex) || []
        }),
        _renderHistoryCompareSpacer(),
        "removed"
      );
    } else if (event.type === "right") {
      const rightCompareIndex = rightStart + Number(event.rightIndex || 0);
      _appendHistoryCompareRowPair(
        leftPane,
        rightPane,
        _renderHistoryCompareSpacer(),
        _renderHistoryComparePaneRow(rightLines[event.rightIndex] || {}, {
          sideLabel: "+",
          signClass: "history-compare-line-added",
          rowClass: "is-insert",
          limits,
          side: "b",
          compareLineIndex: rightCompareIndex,
          anchorItems: anchorMap?.b?.get(rightCompareIndex) || []
        }),
        "added"
      );
    }
  });
}
function _appendHistoryCompareOneSidedHunk(leftPane, rightPane, hunk, data, anchorMap) {
  const limits = data.limits || {};
  const op = hunk.op;
  const lines = op === "insert" ? hunk.right?.lines || [] : hunk.left?.lines || [];
  const leftStart = _historyCompareRendererNumber(hunk.left?.start, 0);
  const rightStart = _historyCompareRendererNumber(hunk.right?.start, 0);
  lines.forEach((line, index) => {
    const leftCompareIndex = leftStart + index;
    const rightCompareIndex = rightStart + index;
    _appendHistoryCompareRowPair(
      leftPane,
      rightPane,
      op === "delete" ? _renderHistoryComparePaneRow(line, {
        sideLabel: "-",
        signClass: "history-compare-line-removed",
        rowClass: "is-delete",
        limits,
        side: "a",
        compareLineIndex: leftCompareIndex,
        anchorItems: anchorMap?.a?.get(leftCompareIndex) || []
      }) : _renderHistoryCompareSpacer(),
      op === "insert" ? _renderHistoryComparePaneRow(line, {
        sideLabel: "+",
        signClass: "history-compare-line-added",
        rowClass: "is-insert",
        limits,
        side: "b",
        compareLineIndex: rightCompareIndex,
        anchorItems: anchorMap?.b?.get(rightCompareIndex) || []
      }) : _renderHistoryCompareSpacer(),
      op === "insert" ? "added" : "removed"
    );
  });
}
function _appendHistoryCompareOmittedRows(leftPane, rightPane, hunk) {
  const omitted = hunk.lines_omitted || {};
  if (!Number(omitted.total || 0)) return;
  const row = document.createElement("div");
  row.className = "history-compare-row history-compare-row-omitted";
  row.textContent = `${Number(omitted.total).toLocaleString()} changed line(s) omitted in this block.`;
  _appendHistoryCompareRowPair(leftPane, rightPane, row.cloneNode(true), row);
}
function _renderHistoryCompareSplitPane(data, options = {}) {
  const viewMode = options.viewMode || "side_by_side";
  const wrap = document.createElement("div");
  wrap.className = `history-compare-split is-${viewMode.replace(/_/g, "-")}`;
  wrap.dataset.compareViewMode = viewMode;
  const anchorMap = _historyCompareRendererBuildAnchorMap(data);
  const leftPane = document.createElement("div");
  leftPane.className = "history-compare-pane nice-scroll";
  leftPane.dataset.side = "a";
  const rightPane = document.createElement("div");
  rightPane.className = "history-compare-pane nice-scroll";
  rightPane.dataset.side = "b";
  const renderPanes = () => {
    leftPane.replaceChildren();
    rightPane.replaceChildren();
    _historyCompareRendererRowPairSequence = 0;
    _historyCompareRendererUnitSequence = 0;
    const leftTitle = document.createElement("div");
    leftTitle.className = "history-compare-pane-title";
    leftTitle.textContent = "Run A";
    const rightTitle = document.createElement("div");
    rightTitle.className = "history-compare-pane-title";
    rightTitle.textContent = "Run B";
    leftPane.appendChild(leftTitle);
    rightPane.appendChild(rightTitle);
    (Array.isArray(data.hunks) ? data.hunks : []).forEach((hunk) => {
      if (!hunk || !hunk.op) return;
      if (hunk.op === "equal") {
        _appendHistoryCompareEqualHunk(leftPane, rightPane, hunk, data, renderPanes, anchorMap, {
          contextLimit: options.contextLimit,
          changesOnly: viewMode === "changes_only"
        });
      } else if (hunk.op === "replace") _appendHistoryCompareReplaceHunk(leftPane, rightPane, hunk, data, anchorMap);
      else if (hunk.op === "insert" || hunk.op === "delete") _appendHistoryCompareOneSidedHunk(leftPane, rightPane, hunk, data, anchorMap);
      _appendHistoryCompareOmittedRows(leftPane, rightPane, hunk);
    });
    if (Number(data.truncated?.hunks_omitted || 0) > 0) {
      const placeholder = document.createElement("div");
      placeholder.className = "history-compare-row history-compare-row-omitted history-compare-surplus";
      placeholder.textContent = `${Number(data.truncated.hunks_omitted).toLocaleString()} additional changed hunk(s) omitted.`;
      _appendHistoryCompareRowPair(leftPane, rightPane, placeholder.cloneNode(true), placeholder);
    }
    _scheduleHistoryCompareRowPairHeightSync(wrap);
  };
  renderPanes();
  if (!_historyCompareRendererUseMobile()) {
    let syncing = false;
    const sync = (source, target) => {
      if (syncing || !source || !target) return;
      syncing = true;
      const raf = typeof requestAnimationFrame === "function" ? requestAnimationFrame : (callback) => setTimeout(callback, 0);
      raf(() => {
        target.scrollTop = source.scrollTop;
        syncing = false;
      });
    };
    leftPane.addEventListener("scroll", () => sync(leftPane, rightPane));
    rightPane.addEventListener("scroll", () => sync(rightPane, leftPane));
  }
  wrap.appendChild(leftPane);
  wrap.appendChild(rightPane);
  wrap.appendChild(_historyCompareRendererMinimap(data.density_buckets || []));
  _observeHistoryCompareRowPairHeights(wrap);
  return wrap;
}
function _historyCompareCountsSubtitle(totals = {}) {
  const total = Number(totals.left_total_lines || 0);
  const unchanged = Number(totals.equal_line_count || 0);
  const changed = Number(totals.changed_line_count || 0);
  const added = Number(totals.added_line_count || 0);
  const removed = Number(totals.removed_line_count || 0);
  return `${total.toLocaleString()} lines · ${unchanged.toLocaleString()} unchanged · ${changed.toLocaleString()} changed · ${added.toLocaleString()} added · ${removed.toLocaleString()} removed`;
}
function _renderHistoryCompareOmittedNote(truncated = {}) {
  const omitted = _historyCompareRendererOmittedTotal(truncated);
  if (!omitted) return null;
  const note = document.createElement("div");
  note.className = "history-compare-counts-note";
  note.textContent = `${omitted.toLocaleString()} changed line(s) or hunk(s) omitted by compare limits.`;
  return note;
}
function _historyCompareNoiseOmittedTotal(data = {}) {
  const left = Number(data.left?.output_source?.noise_lines_omitted || 0);
  const right = Number(data.right?.output_source?.noise_lines_omitted || 0);
  return Math.max(0, left) + Math.max(0, right);
}
function _renderHistoryCompareNoiseNote(data = {}) {
  const omitted = _historyCompareNoiseOmittedTotal(data);
  if (!omitted) return null;
  const note = document.createElement("div");
  note.className = "history-compare-counts-note";
  note.textContent = `${omitted.toLocaleString()} noisy transcript line(s) folded out of this comparison.`;
  return note;
}
function _historyCompareObjectText(item, kind) {
  if (!item || typeof item !== "object") return "";
  if (kind === "artifact") {
    return item.workspace_path || item.display_name || item.id || "";
  }
  if (kind === "entity") {
    return item.canonical_value || item.value || item.id || "";
  }
  return item.title || item.raw_line || item.id || "";
}
function _historyCompareObjectMeta(item, kind) {
  if (!item || typeof item !== "object") return "";
  if (kind === "artifact") {
    return [
      item.kind || "file",
      item.byte_size !== void 0 && item.byte_size !== null ? `${Number(item.byte_size).toLocaleString()} bytes` : "",
      item.detected_by || ""
    ].filter(Boolean).join(" · ");
  }
  if (kind === "entity") {
    return [
      item.type || "",
      item.confidence || "",
      item.value && item.value !== item.canonical_value ? item.value : ""
    ].filter(Boolean).join(" · ");
  }
  return [
    item.severity || "",
    item.review_state || "",
    item.line_number !== void 0 && item.line_number !== null ? `line ${item.line_number}` : ""
  ].filter(Boolean).join(" · ");
}
function _renderHistoryCompareObjectSection(title, items, kind, sign) {
  const safeItems = Array.isArray(items) ? items : [];
  const section = document.createElement("details");
  section.className = "history-compare-lines history-compare-object-section";
  section.open = true;
  const summary = document.createElement("summary");
  summary.textContent = `${title} (${safeItems.length})`;
  section.appendChild(summary);
  if (!safeItems.length) {
    const empty = document.createElement("div");
    empty.className = "history-compare-empty";
    empty.textContent = `No ${title.toLowerCase()}.`;
    section.appendChild(empty);
    return section;
  }
  const list = document.createElement("div");
  list.className = "history-compare-line-list";
  safeItems.forEach((item) => {
    const compareLineIndex = _historyCompareRendererNumber(item?.compare_line_index);
    const compareSide = sign === "+" ? "b" : "a";
    const row = compareLineIndex === null ? document.createElement("div") : document.createElement("button");
    if (row.tagName === "BUTTON") {
      row.type = "button";
      row.addEventListener("click", () => {
        _historyCompareRendererScrollToLine(compareSide, compareLineIndex, { emit: true });
      });
      _historyCompareRendererBindPressable(row);
    }
    row.className = `history-compare-line history-compare-object-row${compareLineIndex === null ? "" : " control-row"}`;
    row.dataset.objectKind = kind;
    row.dataset.compareSide = compareSide;
    if (compareLineIndex !== null) {
      row.dataset.compareLineIndex = String(compareLineIndex);
      row.classList.add("is-anchorable");
    }
    const mark = document.createElement("span");
    mark.className = sign === "+" ? "history-compare-line-added" : "history-compare-line-removed";
    mark.textContent = sign;
    row.appendChild(mark);
    const content = document.createElement("div");
    content.className = "history-compare-object-content";
    const primary = document.createElement("code");
    primary.textContent = _historyCompareObjectText(item, kind);
    content.appendChild(primary);
    const meta = _historyCompareObjectMeta(item, kind);
    if (meta) {
      const metaEl = document.createElement("div");
      metaEl.className = "history-compare-object-meta";
      metaEl.textContent = meta;
      content.appendChild(metaEl);
    }
    row.appendChild(content);
    list.appendChild(row);
  });
  section.appendChild(list);
  return section;
}
function _historyCompareDerivedSide(side) {
  const normalized = String(side || "").toLowerCase();
  if (normalized === "right" || normalized === "b" || normalized === "+") return "b";
  if (normalized === "left" || normalized === "a" || normalized === "-") return "a";
  return "";
}
function _historyCompareDerivedPointer(item) {
  if (!item || typeof item !== "object") return null;
  const compareLineIndex = _historyCompareRendererNumber(item.compare_line_index);
  const compareSide = _historyCompareDerivedSide(item.compare_side);
  if (compareLineIndex === null || !compareSide) return null;
  return { compareLineIndex, compareSide };
}
function _historyCompareDerivedChangedPointer(item) {
  return _historyCompareDerivedPointer(item?.after) || _historyCompareDerivedPointer(item?.before);
}
function _historyCompareDerivedRecordLabel(item, kind) {
  if (!item || typeof item !== "object") return "";
  if (kind === "ports") {
    const key = item.key || (item.port && item.proto ? `${item.port}/${item.proto}` : "");
    return [
      key,
      item.state || "",
      item.service_text || item.service || ""
    ].filter(Boolean).join(" ");
  }
  if (kind === "urls") {
    return item.canonical_url || item.url || item.key || "";
  }
  return item.label || item.key || item.line || "";
}
function _historyCompareDerivedRecordMeta(item, kind) {
  if (!item || typeof item !== "object") return "";
  if (kind === "ports") {
    return [
      item.host || "",
      item.line && item.line !== _historyCompareDerivedRecordLabel(item, kind) ? item.line : ""
    ].filter(Boolean).join(" · ");
  }
  if (kind === "urls") {
    const status = item.status_code !== void 0 && item.status_code !== null ? String(item.status_code) : "";
    return [
      status,
      item.title || "",
      item.redirect_url ? `redirect ${item.redirect_url}` : ""
    ].filter(Boolean).join(" · ");
  }
  return item.detail || item.value || "";
}
function _historyCompareDerivedRecordSummary(item, kind) {
  const label = _historyCompareDerivedRecordLabel(item, kind);
  const meta = _historyCompareDerivedRecordMeta(item, kind);
  return [label, meta].filter(Boolean).join(" · ");
}
function _historyCompareDerivedChangedLabel(item, kind) {
  if (!item || typeof item !== "object") return "";
  return item.key || _historyCompareDerivedRecordLabel(item.after, kind) || _historyCompareDerivedRecordLabel(item.before, kind);
}
function _historyCompareDerivedChangedMeta(item, kind) {
  if (!item || typeof item !== "object") return "";
  const before = _historyCompareDerivedRecordSummary(item.before, kind);
  const after = _historyCompareDerivedRecordSummary(item.after, kind);
  if (before && after && before !== after) return `${before} -> ${after}`;
  return after || before || "";
}
function _historyCompareDerivedCount(group, key, listKey) {
  const explicit = _historyCompareRendererNumber(group?.[key]);
  if (explicit !== null) return explicit;
  const values = group && Array.isArray(group[listKey]) ? group[listKey] : [];
  return values.length;
}
function _historyCompareDerivedGroupCounts(group) {
  const added = _historyCompareDerivedCount(group, "added_count", "added");
  const removed = _historyCompareDerivedCount(group, "removed_count", "removed");
  const changed = _historyCompareDerivedCount(group, "changed_count", "changed");
  return {
    added,
    removed,
    changed,
    total: added + removed + changed
  };
}
function _historyCompareDerivedCountsText(counts) {
  return [
    counts.added ? `${counts.added.toLocaleString()} added` : "",
    counts.removed ? `${counts.removed.toLocaleString()} removed` : "",
    counts.changed ? `${counts.changed.toLocaleString()} changed` : ""
  ].filter(Boolean).join(" · ");
}
function _historyCompareDerivedNoResultText(group) {
  if (!group || typeof group !== "object") return "";
  if (group.note) return String(group.note);
  if (group.unavailable_reason) {
    const title = group.title || group.id || "Tool-aware changes";
    return `${title} did not produce a confident summary (${group.unavailable_reason}).`;
  }
  if (group.applicable) {
    const title = group.title || group.id || "Tool-aware changes";
    return `${title} did not produce a confident summary.`;
  }
  return "";
}
function _historyCompareAppendDerivedRow(list, item, kind, sign, pointer, options = {}) {
  const row = pointer ? document.createElement("button") : document.createElement("div");
  if (row.tagName === "BUTTON") {
    row.type = "button";
    row.addEventListener("click", () => {
      _historyCompareRendererScrollToLine(pointer.compareSide, pointer.compareLineIndex, { emit: true });
    });
    _historyCompareRendererBindPressable(row);
  }
  row.className = "history-compare-line history-compare-object-row history-compare-derived-row" + (pointer ? " control-row is-anchorable" : "");
  row.dataset.objectKind = `derived-${kind || "change"}`;
  row.dataset.derivedKind = kind || "change";
  if (pointer) {
    row.dataset.compareSide = pointer.compareSide;
    row.dataset.compareLineIndex = String(pointer.compareLineIndex);
  }
  const mark = document.createElement("span");
  if (sign === "+") mark.className = "history-compare-line-added";
  else if (sign === "-") mark.className = "history-compare-line-removed";
  else mark.className = "history-compare-derived-change-mark";
  mark.textContent = sign;
  row.appendChild(mark);
  const content = document.createElement("div");
  content.className = "history-compare-object-content";
  const primary = document.createElement("code");
  primary.textContent = options.label || _historyCompareDerivedRecordLabel(item, kind);
  content.appendChild(primary);
  const meta = options.meta || _historyCompareDerivedRecordMeta(item, kind);
  if (meta) {
    const metaEl = document.createElement("div");
    metaEl.className = "history-compare-object-meta";
    metaEl.textContent = meta;
    content.appendChild(metaEl);
  }
  row.appendChild(content);
  list.appendChild(row);
}
function _renderHistoryCompareDerivedChanges(derivedChanges = {}) {
  const groups = Array.isArray(derivedChanges.groups) ? derivedChanges.groups : [];
  const visibleGroups = groups.map((group) => ({ group, counts: _historyCompareDerivedGroupCounts(group) })).filter((entry) => entry.counts.total > 0);
  const notes = groups.map(_historyCompareDerivedNoResultText).filter(Boolean);
  if (!visibleGroups.length && !notes.length) return null;
  if (!visibleGroups.length) {
    const note = document.createElement("div");
    note.className = "history-compare-counts-note";
    note.textContent = notes.join(" ");
    return note;
  }
  const total = visibleGroups.reduce((sum, entry) => sum + entry.counts.total, 0);
  const section = document.createElement("details");
  section.className = "history-compare-lines history-compare-object-section history-compare-derived-section";
  section.open = true;
  const summary = document.createElement("summary");
  summary.textContent = `Detected changes (${total.toLocaleString()})`;
  section.appendChild(summary);
  const wrap = document.createElement("div");
  wrap.className = "history-compare-derived-groups";
  visibleGroups.forEach(({ group, counts }) => {
    const kind = group.kind || group.id || "change";
    const groupEl = document.createElement("div");
    groupEl.className = "history-compare-derived-group";
    const title = document.createElement("div");
    title.className = "history-compare-derived-group-title";
    title.textContent = [
      group.title || group.id || "Derived changes",
      group.display_target || "",
      _historyCompareDerivedCountsText(counts)
    ].filter(Boolean).join(" · ");
    groupEl.appendChild(title);
    const list = document.createElement("div");
    list.className = "history-compare-line-list";
    (Array.isArray(group.added) ? group.added : []).forEach((item) => {
      _historyCompareAppendDerivedRow(list, item, kind, "+", _historyCompareDerivedPointer(item));
    });
    (Array.isArray(group.removed) ? group.removed : []).forEach((item) => {
      _historyCompareAppendDerivedRow(list, item, kind, "-", _historyCompareDerivedPointer(item));
    });
    (Array.isArray(group.changed) ? group.changed : []).forEach((item) => {
      _historyCompareAppendDerivedRow(
        list,
        item,
        kind,
        "~",
        _historyCompareDerivedChangedPointer(item),
        {
          label: _historyCompareDerivedChangedLabel(item, kind),
          meta: _historyCompareDerivedChangedMeta(item, kind)
        }
      );
    });
    groupEl.appendChild(list);
    wrap.appendChild(groupEl);
  });
  section.appendChild(wrap);
  if (notes.length) {
    const note = document.createElement("div");
    note.className = "history-compare-counts-note";
    note.textContent = notes.join(" ");
    section.appendChild(note);
  }
  if (derivedChanges.truncated) {
    const note = document.createElement("div");
    note.className = "history-compare-counts-note";
    note.textContent = "Some detected changes were omitted by compare limits.";
    section.appendChild(note);
  }
  return section;
}
function _historyCompareHasTabCapacity(count) {
  const appConfig = typeof APP_CONFIG !== "undefined" ? APP_CONFIG : null;
  const runtimeConfig = appConfig || HISTORY_COMPARE_RENDERER_GLOBAL.APP_CONFIG || {};
  const maxTabs = Number(runtimeConfig.max_tabs || 0);
  const currentTabs = _historyCompareRendererTabs();
  if (!maxTabs || maxTabs <= 0 || !Array.isArray(currentTabs)) return true;
  return currentTabs.length + Number(count || 0) <= maxTabs;
}
function _restoreBothHistoryCompareRuns(left, right) {
  if (!left || !right) return Promise.reject(new Error("missing comparison runs"));
  if (!_historyCompareHasTabCapacity(2)) {
    _historyCompareRendererShowToast("Not enough tab capacity to restore both runs", "error");
    return Promise.reject(new Error("not enough tab capacity"));
  }
  const leftTabId = _historyCompareRendererCreateTab(`A: ${left.command || "run"}`);
  if (!leftTabId) return Promise.reject(new Error("failed to create Run A tab"));
  const rightTabId = _historyCompareRendererCreateTab(`B: ${right.command || "run"}`);
  if (!rightTabId) return Promise.reject(new Error("failed to create Run B tab"));
  return Promise.all([
    _historyCompareRendererRestoreRun(left, { targetTabId: leftTabId, hidePanelOnSuccess: false }),
    _historyCompareRendererRestoreRun(right, { targetTabId: rightTabId, hidePanelOnSuccess: false })
  ]).then(() => {
    _historyCompareRendererActivateTab(rightTabId, { focusComposer: false });
    return [leftTabId, rightTabId];
  });
}
function _renderHistoryComparison(data) {
  const overlay = _historyCompareRendererEnsureOverlay();
  if (!overlay) return;
  const body = overlay.querySelector("#history-compare-body");
  const subtitle = overlay.querySelector("#history-compare-subtitle");
  if (!body) return;
  body.replaceChildren();
  if (!data._compareViewModeDefault) data._compareViewModeDefault = _historyCompareRendererStoredViewMode();
  if (!data._compareContextDefault) data._compareContextDefault = _historyCompareRendererStoredContext();
  const rawViewMode = _historyCompareRendererCoerceViewMode(data._compareViewModeRaw || data._compareViewModeDefault);
  const viewMode = _historyCompareRendererResolveViewMode(rawViewMode);
  const contextMode = _historyCompareRendererCoerceContext(data._compareContext || data._compareContextDefault);
  data._compareViewModeRaw = rawViewMode;
  data._compareContext = contextMode;
  const totals = data.totals || {};
  const changedOutputCount = _historyCompareRendererTotalChangedLines(totals);
  subtitle.textContent = viewMode === "findings_only" ? "Changed findings and artifacts" : changedOutputCount ? _historyCompareCountsSubtitle(totals) : "Changed findings and artifacts";
  const runs = document.createElement("div");
  runs.className = "history-compare-run-grid";
  runs.appendChild(_historyCompareRendererRunCard(data.left, "Run A"));
  runs.appendChild(_historyCompareRendererRunCard(data.right, "Run B"));
  body.appendChild(runs);
  const deltas = data.deltas || {};
  const metrics = document.createElement("div");
  metrics.className = "history-compare-metrics";
  if (deltas.exit_code) {
    metrics.appendChild(_compareMetricCell(
      "Exit",
      deltas.exit_code_changed ? `${deltas.exit_code.left} -> ${deltas.exit_code.right}` : `unchanged · ${deltas.exit_code?.right ?? "n/a"}`,
      deltas.exit_code_changed ? "is-changed" : ""
    ));
  }
  if (deltas.duration_seconds) {
    metrics.appendChild(_compareMetricCell("Duration", _historyCompareRendererFormatDelta(deltas.duration_seconds.delta || 0, "s")));
  }
  if (deltas.output_lines) {
    metrics.appendChild(_compareMetricCell("Lines", _historyCompareRendererFormatDelta(deltas.output_lines.delta || 0)));
  }
  if (deltas.findings) {
    metrics.appendChild(_compareMetricCell("Findings", _historyCompareRendererFormatDelta(deltas.findings.delta || 0)));
  }
  if (data.left && data.right && (Number.isFinite(Number(data.left.persisted_finding_count)) || Number.isFinite(Number(data.right.persisted_finding_count)))) {
    metrics.appendChild(_compareMetricCell(
      "Stored findings",
      _historyCompareRendererFormatDelta(Number(data.right.persisted_finding_count || 0) - Number(data.left.persisted_finding_count || 0))
    ));
  }
  if (data.left && data.right && (Number.isFinite(Number(data.left.artifact_count)) || Number.isFinite(Number(data.right.artifact_count)))) {
    metrics.appendChild(_compareMetricCell(
      "Artifacts",
      _historyCompareRendererFormatDelta(Number(data.right.artifact_count || 0) - Number(data.left.artifact_count || 0))
    ));
  }
  body.appendChild(metrics);
  const omittedNote = _renderHistoryCompareOmittedNote(data.truncated || {});
  if (omittedNote) body.appendChild(omittedNote);
  const noiseNote = _renderHistoryCompareNoiseNote(data);
  if (noiseNote) body.appendChild(noiseNote);
  const findingsTruncated = !!(data.truncated && data.truncated.findings && (data.truncated.findings.left || data.truncated.findings.right));
  const artifactsTruncated = !!(data.truncated && data.truncated.artifacts && (data.truncated.artifacts.left || data.truncated.artifacts.right));
  if (data.truncated && (data.truncated.left || data.truncated.right || data.truncated.changed_lines || findingsTruncated || artifactsTruncated)) {
    const note = document.createElement("div");
    note.className = "history-compare-truncation";
    const limit = Number(data.truncated.item_limit || 0);
    note.textContent = findingsTruncated || artifactsTruncated ? `Comparison is partial because project findings or artifacts exceeded the per-run compare limit${limit ? ` of ${limit.toLocaleString()} items` : ""}.` : "Comparison is partial because one or both outputs were truncated or the changed-line list hit its display limit.";
    body.appendChild(note);
  }
  const derivedChangesSection = _renderHistoryCompareDerivedChanges(data.derived_changes || {});
  if (derivedChangesSection) body.appendChild(derivedChangesSection);
  const toolbar = document.createElement("div");
  toolbar.className = "history-compare-toolbar";
  toolbar.appendChild(_historyCompareRendererDisplayControls(data, viewMode));
  toolbar.appendChild(_historyCompareRendererActionsMenu(data, deltas));
  toolbar.appendChild(_historyCompareRendererNav(data));
  body.appendChild(toolbar);
  if (viewMode !== "findings_only") {
    body.appendChild(_renderHistoryCompareSplitPane(data, {
      viewMode,
      contextLimit: _historyCompareRendererContextLimit(contextMode)
    }));
  }
  const objects = data.objects || {};
  const findingObjects = objects.findings || {};
  const artifactObjects = objects.artifacts || {};
  const entityObjects = objects.entities || {};
  const addedFindings = Array.isArray(findingObjects.added) ? findingObjects.added : [];
  const removedFindings = Array.isArray(findingObjects.removed) ? findingObjects.removed : [];
  const addedArtifacts = Array.isArray(artifactObjects.added) ? artifactObjects.added : [];
  const removedArtifacts = Array.isArray(artifactObjects.removed) ? artifactObjects.removed : [];
  const addedEntities = Array.isArray(entityObjects.added) ? entityObjects.added : [];
  const removedEntities = Array.isArray(entityObjects.removed) ? entityObjects.removed : [];
  const hasDerivedChanges = !!derivedChangesSection;
  if (addedFindings.length) body.appendChild(_renderHistoryCompareObjectSection("Added findings", addedFindings, "finding", "+"));
  if (removedFindings.length) body.appendChild(_renderHistoryCompareObjectSection("Removed findings", removedFindings, "finding", "-"));
  if (addedEntities.length) body.appendChild(_renderHistoryCompareObjectSection("Added entities", addedEntities, "entity", "+"));
  if (removedEntities.length) body.appendChild(_renderHistoryCompareObjectSection("Removed entities", removedEntities, "entity", "-"));
  if (addedArtifacts.length) body.appendChild(_renderHistoryCompareObjectSection("Added artifacts", addedArtifacts, "artifact", "+"));
  if (removedArtifacts.length) body.appendChild(_renderHistoryCompareObjectSection("Removed artifacts", removedArtifacts, "artifact", "-"));
  _syncHistoryCompareFindingMarkers(data);
  if (!changedOutputCount && !hasDerivedChanges && !addedFindings.length && !removedFindings.length && !addedEntities.length && !removedEntities.length && !addedArtifacts.length && !removedArtifacts.length) {
    const empty = document.createElement("div");
    empty.className = "history-compare-empty";
    empty.textContent = "No changed output, findings, entities, or artifacts.";
    body.appendChild(empty);
  }
}
function fetchAndRenderHistoryComparison(leftId, rightId, options = {}) {
  if (!leftId || !rightId) return;
  _historyCompareRendererOpenOverlay();
  const body = document.querySelector("#history-compare-body");
  if (body) {
    body.replaceChildren();
    const loading = document.createElement("div");
    loading.className = "history-compare-empty";
    loading.textContent = "Comparing runs...";
    body.appendChild(loading);
  }
  const url = options.url || `/history/compare?left=${encodeURIComponent(leftId)}&right=${encodeURIComponent(rightId)}`;
  _historyCompareRendererApiFetch(url, void 0, { leftId, rightId }).then((resp) => resp.json().catch(() => ({})).then((data) => {
    if (!resp.ok || data.error) {
      const err = new Error(data.error || `Compare request failed (${resp.status || "unknown"})`);
      err.compareRequestError = true;
      err.httpStatus = resp.status || null;
      throw err;
    }
    return data;
  })).then((data) => {
    _renderHistoryComparison(data);
  }).catch((err) => {
    if (typeof console !== "undefined" && typeof console.error === "function") {
      console.error("[history compare] failed", err);
    }
    _historyCompareRendererLogClientError("history compare fetch failed", err, {
      event: "HISTORY_COMPARE_FETCH_FAILED",
      level: "error",
      left_id: String(leftId || ""),
      right_id: String(rightId || ""),
      url_path: _historyCompareRendererUrlPath(url),
      status: Number(err && err.httpStatus || 0) || null,
      compare_request_error: err?.compareRequestError === true
    });
    const compareState = HISTORY_COMPARE_RENDERER_GLOBAL._historyCompareState;
    if (compareState && compareState.source) _historyCompareRendererMaybeLauncher();
    const detail = err && err.compareRequestError && err.message ? `: ${err.message}` : "";
    _historyCompareRendererShowToast(`Failed to compare runs${detail}`, "error");
  });
}
HISTORY_COMPARE_RENDERER_GLOBAL._compareMetricCell = _compareMetricCell;
HISTORY_COMPARE_RENDERER_GLOBAL._restoreBothHistoryCompareRuns = _restoreBothHistoryCompareRuns;
HISTORY_COMPARE_RENDERER_GLOBAL._renderHistoryComparison = _renderHistoryComparison;
HISTORY_COMPARE_RENDERER_GLOBAL.fetchAndRenderHistoryComparison = fetchAndRenderHistoryComparison;
if (typeof setHistoryCompareHandlers === "function") {
  setHistoryCompareHandlers({ fetchAndRenderHistoryComparison });
}

export {
  _compareMetricCell,
  _restoreBothHistoryCompareRuns,
  _renderHistoryComparison,
  fetchAndRenderHistoryComparison
};
