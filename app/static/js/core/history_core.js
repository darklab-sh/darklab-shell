// ── History pure helpers ─────────────────────────────────────────────────
// Loaded before history.js. DOM, route calls, and modal wiring stay in
// history.js; deterministic filter, label, and formatting helpers live here.
var DarklabHistoryCore = (function (global) {
  const GRACEFUL_TERMINATION_EXIT_CODES = new Set([-15]);

  function normalizeFilterValue(value) {
    return typeof value === 'string' ? value.trim() : '';
  }

  function hasActiveServerFilters(filters) {
    const state = filters || {};
    const type = state.type || 'all';
    const exitCode = state.exitCode || 'all';
    const dateRange = state.dateRange || 'all';
    return Boolean(
      type !== 'all'
      || state.q
      || state.commandRoot
      || (state.signal && state.signal !== 'all')
      || (state.kind && state.kind !== 'all')
      || state.entity
      || (state.entityType && state.entityType !== 'all')
      || exitCode !== 'all'
      || dateRange !== 'all'
      || (state.projectId && state.projectId !== 'all')
    );
  }

  function hasAnyFilters(filters) {
    return hasActiveServerFilters(filters) || !!(filters && filters.starredOnly);
  }

  function resetRunOnlyFilters(filters) {
    return {
      ...(filters || {}),
      commandRoot: '',
      signal: 'all',
      kind: 'all',
      entity: '',
      entityType: 'all',
      exitCode: 'all',
      starredOnly: false,
    };
  }

  function labelForType(type = 'all') {
    if (type === 'runs') return 'runs';
    if (type === 'runs_builtin') return 'built-in runs';
    if (type === 'runs_external') return 'external runs';
    if (type === 'snapshots') return 'snapshots';
    return 'history items';
  }

  function summaryLabel(type = 'all', totalCount = 0) {
    const singular = totalCount === 1;
    if (type === 'runs') return singular ? 'stored run' : 'stored runs';
    if (type === 'runs_builtin') return singular ? 'built-in run' : 'built-in runs';
    if (type === 'runs_external') return singular ? 'external run' : 'external runs';
    if (type === 'snapshots') return singular ? 'stored snapshot' : 'stored snapshots';
    return singular ? 'stored item' : 'stored items';
  }

  function commandRootsFromRuns(runs) {
    const roots = new Set();
    for (const run of Array.isArray(runs) ? runs : []) {
      const root = typeof run === 'string'
        ? run.trim()
        : (run && typeof run.command === 'string' ? run.command.trim().split(/\s+/, 1)[0] : '');
      if (root) roots.add(root);
    }
    return [...roots].sort((a, b) => a.localeCompare(b));
  }

  function rootMatches(suggestions, query, limit = 12) {
    const value = normalizeFilterValue(query).toLowerCase();
    if (!value) return [];
    return (Array.isArray(suggestions) ? suggestions : [])
      .filter(root => String(root || '').toLowerCase().startsWith(value))
      .slice(0, Math.max(0, Number(limit) || 0));
  }

  function activeFilterItems(filters) {
    const state = filters || {};
    const items = [];
    const type = state.type || 'all';
    const exitCode = state.exitCode || 'all';
    const dateRange = state.dateRange || 'all';
    if (type !== 'all') items.push({ key: 'type', label: `type: ${labelForType(type)}` });
    if (state.q) items.push({ key: 'q', label: `search: ${state.q}` });
    if (state.commandRoot) items.push({ key: 'commandRoot', label: `command: ${state.commandRoot}` });
    if (state.signal && state.signal !== 'all') items.push({ key: 'signal', label: `signal: ${state.signal}` });
    if (state.kind && state.kind !== 'all') items.push({ key: 'kind', label: `kind: ${state.kind}` });
    if (state.entity) items.push({ key: 'entity', label: `entity: ${state.entity}` });
    if (state.entityType && state.entityType !== 'all') {
      items.push({ key: 'entityType', label: `entity_type: ${state.entityType}` });
    }
    if (exitCode === '0') items.push({ key: 'exitCode', label: 'exit: 0' });
    else if (exitCode === 'nonzero') items.push({ key: 'exitCode', label: 'exit: failed' });
    else if (exitCode === '-15') items.push({ key: 'exitCode', label: 'exit: terminated' });
    else if (exitCode === 'incomplete') items.push({ key: 'exitCode', label: 'exit: incomplete' });
    if (dateRange !== 'all') items.push({ key: 'dateRange', label: `date: ${dateRange}` });
    if (state.projectId && state.projectId !== 'all') {
      items.push({ key: 'projectId', label: `project: ${state.projectLabel || state.projectId}` });
    }
    if (state.starredOnly) items.push({ key: 'starredOnly', label: 'starred' });
    return items;
  }

  function buildRequestUrl(filters, paging) {
    const state = filters || {};
    const pageState = paging || {};
    const params = new URLSearchParams();
    const type = state.type || 'all';
    const exitCode = state.exitCode || 'all';
    const dateRange = state.dateRange || 'all';
    params.set('page', String(pageState.page || 1));
    params.set('page_size', String(pageState.pageSize || 1));
    params.set('include_total', '1');
    if (type !== 'all') params.set('type', type);
    if (state.q) params.set('q', state.q);
    if (state.commandRoot) params.set('command_root', state.commandRoot);
    if (state.signal && state.signal !== 'all') params.set('signal', state.signal);
    if (state.kind && state.kind !== 'all') params.set('kind', state.kind);
    if (state.entity) params.set('entity', state.entity);
    if (state.entityType && state.entityType !== 'all') params.set('entity_type', state.entityType);
    if (exitCode !== 'all') params.set('exit_code', exitCode);
    if (dateRange !== 'all') params.set('date_range', dateRange);
    if (state.projectId && state.projectId !== 'all') params.set('project_id', state.projectId);
    if (state.starredOnly) params.set('starred_only', '1');
    const query = params.toString();
    return query ? `/history?${query}` : '/history';
  }

  function historyLimit(appConfig) {
    return Math.max(1, Number(appConfig && appConfig.recent_commands_limit) || 50);
  }

  function commandRecallHistory(tab, globalHistory, limit) {
    const seen = new Set();
    const local = tab && Array.isArray(tab.commandHistory) ? tab.commandHistory : [];
    return [...local, ...(Array.isArray(globalHistory) ? globalHistory : [])]
      .map(cmd => String(cmd || ''))
      .filter(cmd => {
        if (!cmd || seen.has(cmd)) return false;
        seen.add(cmd);
        return true;
      })
      .slice(0, Math.max(1, Number(limit) || 50));
  }

  function relativeTime(startedAt, now = new Date()) {
    if (!(startedAt instanceof Date) || Number.isNaN(startedAt.getTime())) return '';
    const diffSec = Math.round((now.getTime() - startedAt.getTime()) / 1000);
    if (diffSec < 45) return 'just now';
    if (diffSec < 60 * 60) return `${Math.round(diffSec / 60)}m ago`;
    if (diffSec < 60 * 60 * 24) return `${Math.round(diffSec / 3600)}h ago`;
    if (diffSec < 60 * 60 * 24 * 7) return `${Math.round(diffSec / 86400)}d ago`;
    return startedAt.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  }

  function exitCodeNumber(exitCode) {
    if (exitCode === null || exitCode === undefined || exitCode === '') return null;
    const number = Number(exitCode);
    return Number.isFinite(number) ? number : null;
  }

  function isGracefulTerminationExitCode(exitCode) {
    const code = exitCodeNumber(exitCode);
    return code !== null && GRACEFUL_TERMINATION_EXIT_CODES.has(code);
  }

  function isFailedExitCode(exitCode) {
    const code = exitCodeNumber(exitCode);
    return code !== null && code !== 0 && !GRACEFUL_TERMINATION_EXIT_CODES.has(code);
  }

  function exitLabel(exitCode) {
    const code = exitCodeNumber(exitCode);
    if (code === null) return 'exit —';
    return isGracefulTerminationExitCode(code) ? 'terminated' : `exit ${code}`;
  }

  function exitClass(exitCode) {
    const code = exitCodeNumber(exitCode);
    if (code === 0) return 'exit-ok';
    if (isFailedExitCode(code)) return 'exit-fail';
    return 'exit-neutral';
  }

  function elapsedSeconds(run) {
    const explicit = Number(run?.elapsed_seconds ?? run?.duration_seconds);
    if (Number.isFinite(explicit) && explicit >= 0) return explicit;
    const started = new Date(run?.started);
    const finished = new Date(run?.finished);
    if (Number.isNaN(started.getTime()) || Number.isNaN(finished.getTime())) return null;
    return Math.max(0, (finished.getTime() - started.getTime()) / 1000);
  }

  function elapsedLabel(run) {
    const total = elapsedSeconds(run);
    if (total === null) return '';
    if (total >= 3600) {
      const hours = Math.floor(total / 3600);
      const minutes = Math.floor((total % 3600) / 60);
      return minutes ? `${hours}h ${minutes}m` : `${hours}h`;
    }
    if (total >= 60) {
      const minutes = Math.floor(total / 60);
      const seconds = Math.round(total % 60);
      return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`;
    }
    return `${total.toFixed(total >= 10 ? 0 : 1)}s`;
  }

  function compareFormatDate(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleString();
  }

  function compareDateGroupLabel(value, now = new Date()) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return 'Undated';
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const dateStart = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const ageDays = Math.round((todayStart.getTime() - dateStart.getTime()) / 86400000);
    if (ageDays === 0) return 'Today';
    if (ageDays === 1) return 'Yesterday';
    return date.toLocaleDateString(undefined, {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      year: date.getFullYear() === now.getFullYear() ? undefined : 'numeric',
    });
  }

  function compareFormatDuration(seconds) {
    if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return 'n/a';
    const value = Number(seconds);
    if (value < 1) return `${Math.round(value * 1000)}ms`;
    if (value < 60) return `${value.toFixed(value < 10 ? 1 : 0)}s`;
    return `${Math.floor(value / 60)}m ${Math.round(value % 60)}s`;
  }

  function compareFormatDelta(value, suffix = '') {
    const number = Number(value);
    if (!Number.isFinite(number) || number === 0) return `0${suffix}`;
    return `${number > 0 ? '+' : ''}${number}${suffix}`;
  }

  const api = Object.freeze({
    activeFilterItems,
    buildRequestUrl,
    commandRecallHistory,
    commandRootsFromRuns,
    compareDateGroupLabel,
    compareFormatDate,
    compareFormatDelta,
    compareFormatDuration,
    elapsedLabel,
    elapsedSeconds,
    exitClass,
    exitCodeNumber,
    exitLabel,
    hasActiveServerFilters,
    hasAnyFilters,
    historyLimit,
    isFailedExitCode,
    isGracefulTerminationExitCode,
    labelForType,
    normalizeFilterValue,
    relativeTime,
    resetRunOnlyFilters,
    rootMatches,
    summaryLabel,
  });
  global.DarklabHistoryCore = api;
  return api;
})(typeof window !== 'undefined' ? window : globalThis);
