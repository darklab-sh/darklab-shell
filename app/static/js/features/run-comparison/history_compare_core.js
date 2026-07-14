// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// ── Run comparison pure helpers ──────────────────────────────────────────
// Loaded before history.js. DOM rendering and route calls stay in history.js;
// comparison formatting, preferences, and deterministic summary helpers live here.
import { DarklabPreferenceCore as importedPreferenceCore } from '../../core/app_preferences_core.js';
import { DarklabHistoryCore as importedHistoryCore } from '../../core/history_core.js';
import {
  getCompareContextPreference as importedGetCompareContextPreference,
  getCompareViewModePreference as importedGetCompareViewModePreference,
  getPreference as importedGetPreference,
} from '../preferences/preferences.js';
import { useMobileTerminalViewportMode as importedUseMobileTerminalViewportMode } from '../mobile/mobile_shell_layout.js';

var DarklabHistoryCompareCore = (function (global) {
  function historyCore() {
    return (typeof importedHistoryCore !== 'undefined' && importedHistoryCore)
      || null;
  }

  function compareFormatDate(value) {
    return historyCore().compareFormatDate(value);
  }

  function compareDateGroupLabel(value) {
    return historyCore().compareDateGroupLabel(value);
  }

  function orderedRunIds(current, candidate) {
    const currentId = String(current?.id || current?.value || '');
    const candidateId = String(candidate?.id || candidate?.value || '');
    const currentStarted = Date.parse(String(current?.started || current?.created || ''));
    const candidateStarted = Date.parse(String(candidate?.started || candidate?.created || ''));
    if (Number.isFinite(currentStarted) && Number.isFinite(candidateStarted) && currentStarted <= candidateStarted) {
      return [currentId, candidateId];
    }
    return [candidateId, currentId];
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
    return (typeof importedPreferenceCore !== 'undefined' && importedPreferenceCore)
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
    const getCompareViewModePreference = typeof importedGetCompareViewModePreference === 'function'
      ? importedGetCompareViewModePreference
      : null;
    const getPreference = typeof importedGetPreference === 'function'
      ? importedGetPreference
      : null;
    if (typeof getCompareViewModePreference === 'function') {
      return coerceViewMode(getCompareViewModePreference());
    }
    if (typeof getPreference === 'function') return coerceViewMode(getPreference('pref_compare_view_mode'));
    return 'auto';
  }

  function storedContext() {
    const getCompareContextPreference = typeof importedGetCompareContextPreference === 'function'
      ? importedGetCompareContextPreference
      : null;
    const getPreference = typeof importedGetPreference === 'function'
      ? importedGetPreference
      : null;
    if (typeof getCompareContextPreference === 'function') {
      return coerceContext(getCompareContextPreference());
    }
    if (typeof getPreference === 'function') return coerceContext(getPreference('pref_compare_context'));
    return '3';
  }

  function useMobileViewportMode() {
    const useMobile = (
      typeof importedUseMobileTerminalViewportMode !== 'undefined'
      && importedUseMobileTerminalViewportMode
    )
      || null;
    return typeof useMobile === 'function' ? useMobile() : false;
  }

  function viewportMode() {
    if (useMobileViewportMode()) return 'unified';
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
    (Array.isArray(findingObjects.changed) ? findingObjects.changed : []).forEach(item => {
      addAnchor('a', item?.before);
      addAnchor('b', item?.after);
    });
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
    orderedRunIds,
    resolveViewMode,
    storedContext,
    storedViewMode,
    totalChangedLines,
    usesMobileLayout,
    viewportMode,
    viewModeOptions,
  });
  return api;
})(typeof window !== 'undefined' ? window : globalThis);

const {
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
  orderedRunIds,
  resolveViewMode,
  storedContext,
  storedViewMode,
  totalChangedLines,
  usesMobileLayout,
  viewportMode,
  viewModeOptions,
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
  orderedRunIds,
  resolveViewMode,
  storedContext,
  storedViewMode,
  totalChangedLines,
  usesMobileLayout,
  viewportMode,
  viewModeOptions,
};
