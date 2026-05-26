// ── Run comparison pure helpers ──────────────────────────────────────────
// Loaded before history.js. DOM rendering and route calls stay in history.js;
// comparison formatting, preferences, and deterministic summary helpers live here.
var DarklabHistoryCompareCore = (function (global) {
  function historyCore() {
    return global.DarklabHistoryCore
      || (typeof DarklabHistoryCore !== 'undefined' ? DarklabHistoryCore : null);
  }

  function compareFormatDate(value) {
    return historyCore().compareFormatDate(value);
  }

  function compareDateGroupLabel(value) {
    return historyCore().compareDateGroupLabel(value);
  }

  function compareFormatDuration(seconds) {
    return historyCore().compareFormatDuration(seconds);
  }

  function compareFormatDelta(value, suffix = '') {
    return historyCore().compareFormatDelta(value, suffix);
  }

  function totalChangedLines(totals = {}) {
    return Number(totals.changed_line_count || 0)
      + Number(totals.added_line_count || 0)
      + Number(totals.removed_line_count || 0);
  }

  function omittedTotal(truncated = {}) {
    const lineOmitted = truncated && truncated.lines_omitted ? truncated.lines_omitted : {};
    return Number(truncated.hunks_omitted || 0) + Number(lineOmitted.total || 0);
  }

  function lineLimit(limits = {}) {
    const limit = Number(limits.line_display_truncate || 0);
    return Number.isFinite(limit) && limit > 0 ? limit : 4000;
  }

  function preferenceCore() {
    return (typeof PreferenceCore !== 'undefined' && PreferenceCore)
      || (typeof DarklabPreferenceCore !== 'undefined' && DarklabPreferenceCore)
      || global.DarklabPreferenceCore
      || null;
  }

  function coerceViewMode(value) {
    const core = preferenceCore();
    if (core && typeof core.coerceCompareViewMode === 'function') return core.coerceCompareViewMode(value);
    return ['auto', 'side_by_side', 'unified', 'changes_only', 'findings_only'].includes(value) ? value : 'auto';
  }

  function coerceContext(value) {
    const core = preferenceCore();
    if (core && typeof core.coerceCompareContextMode === 'function') return core.coerceCompareContextMode(value);
    const normalized = String(value || '').trim().toLowerCase();
    return ['3', '10', 'all'].includes(normalized) ? normalized : '3';
  }

  function storedViewMode() {
    if (typeof getCompareViewModePreference === 'function') return coerceViewMode(getCompareViewModePreference());
    if (typeof getPreference === 'function') return coerceViewMode(getPreference('pref_compare_view_mode'));
    return 'auto';
  }

  function storedContext() {
    if (typeof getCompareContextPreference === 'function') return coerceContext(getCompareContextPreference());
    if (typeof getPreference === 'function') return coerceContext(getPreference('pref_compare_context'));
    return '3';
  }

  function viewportMode() {
    if (typeof useMobileTerminalViewportMode === 'function' && useMobileTerminalViewportMode()) return 'unified';
    if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
      try {
        if (window.matchMedia('(max-width: 760px)').matches) return 'unified';
      } catch (_) {}
    }
    return 'side_by_side';
  }

  function usesMobileLayout() {
    return viewportMode() === 'unified';
  }

  function resolveViewMode(value = null) {
    const mode = coerceViewMode(value || storedViewMode());
    const currentViewportMode = viewportMode();
    if (mode === 'auto') return currentViewportMode;
    if (mode === 'side_by_side' && currentViewportMode === 'unified') return 'unified';
    return mode;
  }

  function viewModeOptions() {
    const options = [
      ['side_by_side', 'Side-by-side'],
      ['unified', 'Unified'],
      ['changes_only', 'Changes only'],
      ['findings_only', 'Findings only'],
    ];
    if (viewportMode() === 'unified') {
      return options.filter(([value]) => value !== 'side_by_side');
    }
    return options;
  }

  function contextLimit(value = null) {
    const context = coerceContext(value || storedContext());
    if (context === 'all') return null;
    return Number(context);
  }

  function number(value, fallback = null) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function cssEscape(value) {
    const text = String(value);
    if (typeof CSS !== 'undefined' && CSS && typeof CSS.escape === 'function') return CSS.escape(text);
    return text.replace(/["\\]/g, '\\$&');
  }

  function bucketTone(bucket = {}) {
    const changed = Number(bucket.changed || 0);
    const added = Number(bucket.added || 0);
    const removed = Number(bucket.removed || 0);
    const equal = Number(bucket.equal || 0);
    if (changed > 0) return 'changed';
    if (added > 0 || removed > 0) return added > removed ? 'added' : 'removed';
    if (equal > 0) return 'equal';
    return 'empty';
  }

  function buildAnchorMap(data = {}) {
    const map = { a: new Map(), b: new Map() };
    const findingObjects = data.objects?.findings || {};
    const addAnchor = (side, item) => {
      const index = number(item?.compare_line_index);
      if (index === null) return;
      const existing = map[side].get(index) || [];
      existing.push(item);
      map[side].set(index, existing);
    };
    (Array.isArray(findingObjects.added) ? findingObjects.added : []).forEach(item => addAnchor('b', item));
    (Array.isArray(findingObjects.removed) ? findingObjects.removed : []).forEach(item => addAnchor('a', item));
    return map;
  }

  function anchorTone(items = []) {
    const severities = items.map(item => String(item?.severity || '').toLowerCase());
    if (severities.some(value => value === 'critical' || value === 'high')) return 'high';
    if (severities.some(value => value === 'medium')) return 'medium';
    return 'info';
  }

  const api = Object.freeze({
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
    viewModeOptions,
  });
  global.DarklabHistoryCompareCore = api;
  return api;
})(typeof window !== 'undefined' ? window : globalThis);
