import {
  bucketTone,
  cssEscape,
  number
} from "./static-chunk-6sxirwn5.a08adec8fe31.js";
import {
  bindPressable
} from "./static-chunk-fik64llj.1291b1f4f79b.js";
import {
  emitUiEvent
} from "./static-chunk-sgyzdmxn.7d1842f12a94.js";

// app/static/js/features/run-comparison/history_compare_navigation.js
var HISTORY_COMPARE_NAV_GLOBAL = typeof window !== "undefined" ? window : globalThis;
function _historyCompareNavigationCssEscape(value) {
  const escape = typeof cssEscape !== "undefined" && cssEscape || (typeof HISTORY_COMPARE_NAV_GLOBAL._historyCompareCssEscape === "function" ? HISTORY_COMPARE_NAV_GLOBAL._historyCompareCssEscape : null);
  return typeof escape === "function" ? escape(value) : String(value);
}
function _historyCompareNavigationNumber(value, fallback = null) {
  const number2 = typeof number !== "undefined" && number || (typeof HISTORY_COMPARE_NAV_GLOBAL._historyCompareNumber === "function" ? HISTORY_COMPARE_NAV_GLOBAL._historyCompareNumber : null);
  if (typeof number2 === "function") return number2(value, fallback);
  if (value === null || typeof value === "undefined" || value === "") return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}
function _historyCompareNavigationBucketTone(bucket) {
  const tone = typeof bucketTone !== "undefined" && bucketTone || (typeof HISTORY_COMPARE_NAV_GLOBAL._historyCompareBucketTone === "function" ? HISTORY_COMPARE_NAV_GLOBAL._historyCompareBucketTone : null);
  return typeof tone === "function" ? tone(bucket) : "empty";
}
function _historyCompareNavigationEmitUiEvent(name, detail) {
  const emit = typeof emitUiEvent !== "undefined" && emitUiEvent || (typeof HISTORY_COMPARE_NAV_GLOBAL.emitUiEvent === "function" ? HISTORY_COMPARE_NAV_GLOBAL.emitUiEvent : null);
  if (typeof emit === "function") emit(name, detail);
}
function _historyCompareNavigationBindPressable(el) {
  const bind = typeof bindPressable !== "undefined" && bindPressable || (typeof HISTORY_COMPARE_NAV_GLOBAL.bindPressable === "function" ? HISTORY_COMPARE_NAV_GLOBAL.bindPressable : null);
  if (typeof bind === "function") bind(el);
}
function _historyCompareFindPaneRow(side, compareLineIndex) {
  const overlay = document.getElementById("history-compare-overlay");
  const pane = overlay?.querySelector(`.history-compare-pane[data-side="${side}"]`);
  const index = String(compareLineIndex);
  const row = pane?.querySelector(`.history-compare-row[data-compare-line-index="${_historyCompareNavigationCssEscape(index)}"]`);
  return { pane, row };
}
function _historyComparePulseRows(rows = []) {
  rows.filter(Boolean).forEach((row) => {
    row.classList.remove("history-compare-line-pulse");
    void row.offsetWidth;
    row.classList.add("history-compare-line-pulse");
    setTimeout(() => row.classList.remove("history-compare-line-pulse"), 900);
  });
}
function _historyCompareScrollPaneRowIntoView(pane, row) {
  if (!pane || !row) return;
  const paneRect = typeof pane.getBoundingClientRect === "function" ? pane.getBoundingClientRect() : null;
  const rowRect = typeof row.getBoundingClientRect === "function" ? row.getBoundingClientRect() : null;
  const paneHeight = Number(pane.clientHeight || paneRect?.height || 0);
  const rowHeight = Number(rowRect?.height || row.offsetHeight || 0);
  const relativeTop = Number(rowRect?.top || 0) - Number(paneRect?.top || 0);
  if (paneHeight > 0 && Number.isFinite(relativeTop)) {
    pane.scrollTop = Math.max(0, pane.scrollTop + relativeTop - Math.max(0, (paneHeight - rowHeight) / 2));
    return;
  }
  pane.scrollTop = Number(row.offsetTop || 0);
}
function _historyCompareScrollToLine(side, compareLineIndex, { emit = true } = {}) {
  const primary = _historyCompareFindPaneRow(side, compareLineIndex);
  if (!primary.row || !primary.pane) return false;
  const otherSide = side === "a" ? "b" : "a";
  const pair = primary.row.dataset.comparePair || "";
  const secondary = pair ? {
    pane: document.querySelector(`#history-compare-overlay .history-compare-pane[data-side="${otherSide}"]`),
    row: document.querySelector(
      `#history-compare-overlay .history-compare-pane[data-side="${otherSide}"] .history-compare-row[data-compare-pair="${_historyCompareNavigationCssEscape(pair)}"]`
    )
  } : _historyCompareFindPaneRow(otherSide, compareLineIndex);
  _historyCompareScrollPaneRowIntoView(primary.pane, primary.row);
  if (secondary.pane) secondary.pane.scrollTop = primary.pane.scrollTop;
  _historyComparePulseRows([primary.row, secondary.row]);
  if (emit) {
    _historyCompareNavigationEmitUiEvent("app:compare-anchor-scroll", {
      side,
      compare_line_index: compareLineIndex
    });
  }
  return true;
}
function _historyCompareScrollToRow(row, { emit = false } = {}) {
  if (!(row instanceof Element)) return false;
  const side = row.closest(".history-compare-pane")?.dataset.side || "a";
  const lineIndex = _historyCompareNavigationNumber(row.dataset.compareLineIndex);
  if (lineIndex !== null) return _historyCompareScrollToLine(side, lineIndex, { emit });
  const pair = row.dataset.comparePair || "";
  if (!pair) return false;
  const pairedChanged = document.querySelector(
    `#history-compare-overlay .history-compare-row[data-compare-pair="${_historyCompareNavigationCssEscape(pair)}"][data-compare-line-index]`
  );
  if (!pairedChanged) return false;
  const pairedSide = pairedChanged.closest(".history-compare-pane")?.dataset.side || side;
  return _historyCompareScrollToLine(
    pairedSide,
    _historyCompareNavigationNumber(pairedChanged.dataset.compareLineIndex, 0),
    { emit }
  );
}
function _historyCompareRenderedChangeTargets() {
  const changedTones = /* @__PURE__ */ new Set(["changed", "added", "removed"]);
  const byPair = /* @__PURE__ */ new Map();
  [...document.querySelectorAll("#history-compare-overlay .history-compare-row[data-compare-unit-index]")].map((row) => ({
    row,
    index: _historyCompareNavigationNumber(row.dataset.compareUnitIndex, 0),
    tone: row.dataset.compareUnitTone || "",
    isSpacer: row.classList.contains("history-compare-row-spacer")
  })).filter((item) => changedTones.has(item.tone)).forEach((item) => {
    const pair = item.row.dataset.comparePair || `unit-${item.index}`;
    const existing = byPair.get(pair);
    if (!existing || existing.isSpacer && !item.isSpacer) byPair.set(pair, item);
  });
  return [...byPair.values()].sort((a, b) => a.index - b.index || Number(a.isSpacer) - Number(b.isSpacer));
}
function _historyCompareScrollToBucket(bucket) {
  const start = _historyCompareNavigationNumber(bucket?.start, 0);
  const end = Math.max(start + 1, _historyCompareNavigationNumber(bucket?.end, start + 1));
  const rows = _historyCompareRenderedChangeTargets();
  const inBucket = rows.filter((item) => item.index >= start && item.index < end);
  const target = inBucket.find((item) => !item.isSpacer) || inBucket[0] || rows.find((item) => item.index >= start && !item.isSpacer) || rows.find((item) => item.index >= start) || rows.find((item) => !item.isSpacer) || rows[0];
  if (!target || !target.row) return false;
  return _historyCompareScrollToRow(target.row, { emit: false });
}
function _historyCompareChangeBucketIndexes(data = {}) {
  const buckets = Array.isArray(data.density_buckets) ? data.density_buckets : [];
  return buckets.map((bucket, index) => ({ bucket, index, tone: _historyCompareNavigationBucketTone(bucket) })).filter((item) => ["changed", "added", "removed"].includes(item.tone)).map((item) => item.index);
}
function _historyCompareGoToChangeBucket(data, direction) {
  const targets = _historyCompareRenderedChangeTargets();
  if (!targets.length) return false;
  const currentIndex = data._activeChangeTargetPair ? targets.findIndex((item) => (item.row.dataset.comparePair || "") === data._activeChangeTargetPair) : -1;
  const nextPosition = direction < 0 ? currentIndex <= 0 ? targets.length - 1 : currentIndex - 1 : currentIndex < 0 || currentIndex >= targets.length - 1 ? 0 : currentIndex + 1;
  const target = targets[nextPosition];
  data._activeChangeTargetPair = target.row.dataset.comparePair || "";
  data._activeChangeBucketIndex = Number(target.index);
  return _historyCompareScrollToRow(target.row, { emit: false });
}
function _renderHistoryCompareNav(data = {}) {
  const nav = document.createElement("div");
  nav.className = "history-compare-nav";
  const makeButton = (label, direction) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-secondary btn-compact history-compare-nav-btn";
    button.textContent = label;
    button.disabled = !_historyCompareChangeBucketIndexes(data).length;
    button.addEventListener("click", () => _historyCompareGoToChangeBucket(data, direction));
    _historyCompareNavigationBindPressable(button);
    return button;
  };
  nav.appendChild(makeButton("Prev change", -1));
  nav.appendChild(makeButton("Next change", 1));
  return nav;
}
function _renderHistoryCompareMinimap(buckets = []) {
  const rail = document.createElement("div");
  rail.className = "history-compare-minimap";
  rail.setAttribute("aria-hidden", "true");
  (Array.isArray(buckets) ? buckets : []).forEach((bucket, index) => {
    const segment = document.createElement("div");
    const tone = _historyCompareNavigationBucketTone(bucket);
    segment.className = `history-compare-minimap-segment is-${tone}`;
    segment.dataset.bucketIndex = String(index);
    segment.dataset.bucketStart = String(bucket.start ?? 0);
    segment.dataset.bucketEnd = String(bucket.end ?? 0);
    segment.addEventListener("click", () => _historyCompareScrollToBucket(bucket));
    rail.appendChild(segment);
  });
  return rail;
}

export {
  _historyCompareFindPaneRow,
  _historyComparePulseRows,
  _historyCompareScrollPaneRowIntoView,
  _historyCompareScrollToLine,
  _historyCompareScrollToRow,
  _historyCompareRenderedChangeTargets,
  _historyCompareScrollToBucket,
  _historyCompareChangeBucketIndexes,
  _historyCompareGoToChangeBucket,
  _renderHistoryCompareNav,
  _renderHistoryCompareMinimap
};
