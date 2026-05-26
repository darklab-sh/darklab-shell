// ── Search pure helpers ──────────────────────────────────────────────────
// Loaded before search.js. DOM traversal and highlighting stay in search.js;
// label, count, and summary transforms live here for unit-testable reuse.
var DarklabSearchCore = (function (global) {
  const SEARCH_SCOPE_LABELS = Object.freeze({
    text: 'text',
    findings: 'findings',
    warnings: 'warnings',
    errors: 'errors',
    summaries: 'summaries',
  });
  const SEARCH_SUMMARY_LIMIT = 25;

  function searchScopeButtonLabel(scope, count) {
    if (scope === 'text') return 'text';
    return `${SEARCH_SCOPE_LABELS[scope]} (${count})`;
  }

  function searchScopeUnitLabel(scope, count) {
    if (scope === 'summaries') return count === 1 ? 'summary' : 'summaries';
    const base = SEARCH_SCOPE_LABELS[scope] || 'matches';
    return count === 1 ? base.replace(/s$/, '') : base;
  }

  function formatFindingSummary(counts) {
    const state = counts || {};
    const parts = [];
    if (state.findings > 0) parts.push(`${state.findings} finding${state.findings === 1 ? '' : 's'}`);
    if (state.warnings > 0) parts.push(`${state.warnings} warning${state.warnings === 1 ? '' : 's'}`);
    if (state.errors > 0) parts.push(`${state.errors} error${state.errors === 1 ? '' : 's'}`);
    if (state.summaries > 0) parts.push(`${state.summaries} summar${state.summaries === 1 ? 'y' : 'ies'}`);
    return parts.join(' • ');
  }

  function searchNoMatchesLabel(scope) {
    return scope === 'text' ? 'no matches' : `no ${SEARCH_SCOPE_LABELS[scope] || 'matches'}`;
  }

  function searchInputPlaceholder(scope) {
    if (scope === 'text') return 'Search output…';
    if (scope === 'summaries') return 'Jump between summary lines…';
    return `Jump between ${SEARCH_SCOPE_LABELS[scope] || 'matches'}…`;
  }

  function normalizeSignalCounts(counts) {
    return {
      findings: Math.max(0, Number(counts?.findings || 0)),
      warnings: Math.max(0, Number(counts?.warnings || 0)),
      errors: Math.max(0, Number(counts?.errors || 0)),
      summaries: Math.max(0, Number(counts?.summaries || 0)),
    };
  }

  function summaryCommandRoot(command) {
    return String(command || '').trim().split(/\s+/, 1)[0]?.toLowerCase() || '';
  }

  function summarySectionsTotal(sections) {
    return (Array.isArray(sections) ? sections : [])
      .reduce((sum, [, lines]) => sum + (Array.isArray(lines) ? lines.length : 0), 0);
  }

  function summaryCompactLines(lines) {
    const counts = new Map();
    const ordered = [];
    (Array.isArray(lines) ? lines : []).forEach((line) => {
      const text = String(line || '').trim();
      if (!text) return;
      if (!counts.has(text)) {
        ordered.push(text);
        counts.set(text, 0);
      }
      counts.set(text, counts.get(text) + 1);
    });
    return ordered.map((line) => {
      const count = counts.get(line) || 0;
      return count > 1 ? `${line} (${count})` : line;
    });
  }

  function summaryMergeSections(items) {
    return ['findings', 'warnings', 'errors', 'summaries'].map((scope) => {
      const lines = [];
      (Array.isArray(items) ? items : []).forEach((item) => {
        const section = Array.isArray(item?.sections)
          ? item.sections.find(([candidate]) => candidate === scope)
          : null;
        if (section && Array.isArray(section[1])) lines.push(...section[1]);
      });
      return [scope, lines];
    });
  }

  function summaryGroupedItems(items) {
    const groups = [];
    (Array.isArray(items) ? items : []).forEach((item) => {
      if (!item?.root || !item?.target) return;
      let rootGroup = groups.find((group) => group.root === item.root);
      if (!rootGroup) {
        rootGroup = { root: item.root, targets: [] };
        groups.push(rootGroup);
      }
      let targetGroup = rootGroup.targets.find((group) => group.target === item.target);
      if (!targetGroup) {
        targetGroup = { target: item.target, items: [] };
        rootGroup.targets.push(targetGroup);
      }
      targetGroup.items.push(item);
    });
    return groups;
  }

  function summaryCommandLabels(items) {
    const counts = new Map();
    const ordered = [];
    (Array.isArray(items) ? items : []).forEach((item) => {
      const command = String(item?.command || '').trim();
      if (!command) return;
      if (!counts.has(command)) {
        ordered.push(command);
        counts.set(command, 0);
      }
      counts.set(command, counts.get(command) + 1);
    });
    return ordered.map((command) => {
      const count = counts.get(command) || 0;
      return count > 1 ? `${command} (${count})` : command;
    });
  }

  const api = Object.freeze({
    SEARCH_SCOPE_LABELS,
    SEARCH_SUMMARY_LIMIT,
    formatFindingSummary,
    normalizeSignalCounts,
    searchInputPlaceholder,
    searchNoMatchesLabel,
    searchScopeButtonLabel,
    searchScopeUnitLabel,
    summaryCommandLabels,
    summaryCommandRoot,
    summaryCompactLines,
    summaryGroupedItems,
    summaryMergeSections,
    summarySectionsTotal,
  });
  global.DarklabSearchCore = api;
  return api;
})(typeof window !== 'undefined' ? window : globalThis);
