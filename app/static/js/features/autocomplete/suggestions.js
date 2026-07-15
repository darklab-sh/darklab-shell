// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// ── Shared autocomplete logic ──
import { DarklabAutocompleteCore as importedAutocompleteCore } from '../../core/autocomplete_core.js';
import { APP_STATE_API as importedAppStateApi, onUiEvent as importedOnUiEvent } from '../../core/state.js';
import { hasPendingTerminalConfirm as importedHasPendingTerminalConfirm } from '../../runner_bridge.js';
import { isActiveTabRunning as importedIsActiveTabRunning } from '../../ui/ui_helpers.js';
import {
  apiFetch as importedApiFetch,
  getSessionId as importedGetSessionId,
  logClientError as importedLogClientError,
} from '../../runtime_bridge.js';
import {
  getGrepOutputSuggestions as importedGetGrepOutputSuggestions,
  getRuntimeAutocompleteContext as importedGetRuntimeAutocompleteContext,
  getRuntimeAutocompleteItems as importedGetRuntimeAutocompleteItems,
  getWorkspaceAutocompleteFlagFileHints as importedGetWorkspaceAutocompleteFlagFileHints,
  getWorkspaceAutocompletePathHints as importedGetWorkspaceAutocompletePathHints,
} from './runtime_context.js';
import {
  getWorkspaceAutocompleteDirectoryHints as importedGetWorkspaceAutocompleteDirectoryHints,
  getWorkspaceAutocompleteFileHints as importedGetWorkspaceAutocompleteFileHints,
} from '../workspace/workspace_autocomplete_cache.js';

const AUTOCOMPLETE_SUGGESTIONS_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

function _autocompleteGlobalFunction(name) {
  const fn = AUTOCOMPLETE_SUGGESTIONS_GLOBAL && AUTOCOMPLETE_SUGGESTIONS_GLOBAL[name];
  return typeof fn === 'function' ? fn : null;
}

const autocompleteCore = typeof importedAutocompleteCore !== 'undefined' && importedAutocompleteCore
  ? importedAutocompleteCore
  : AUTOCOMPLETE_SUGGESTIONS_GLOBAL.DarklabAutocompleteCore;

function _autocompleteState() {
  const api = importedAppStateApi || AUTOCOMPLETE_SUGGESTIONS_GLOBAL.APP_STATE_API || null;
  if (api && typeof api.getState === 'function') return api.getState();
  return AUTOCOMPLETE_SUGGESTIONS_GLOBAL.APP_STATE || {};
}

function _autocompleteApiFetch(url, options) {
  const api = (typeof importedApiFetch === 'function' && importedApiFetch)
    || _autocompleteGlobalFunction('apiFetch');
  if (typeof api !== 'function') return Promise.reject(new Error('apiFetch unavailable'));
  return options === undefined ? api(url) : api(url, options);
}

function _autocompleteLogClientError(context, err) {
  const log = (typeof importedLogClientError === 'function' && importedLogClientError)
    || _autocompleteGlobalFunction('logClientError');
  if (typeof log === 'function') log(context, err);
}

function _autocompleteSessionId() {
  if (typeof importedGetSessionId === 'function') return String(importedGetSessionId() || '');
  return String(AUTOCOMPLETE_SUGGESTIONS_GLOBAL.SESSION_ID || '');
}

function _isAutocompleteBlockedByTerminalConfirm() {
  const hasPending = (typeof importedHasPendingTerminalConfirm !== 'undefined' && importedHasPendingTerminalConfirm)
    || _autocompleteGlobalFunction('hasPendingTerminalConfirm');
  return typeof hasPending === 'function' && hasPending();
}

function _isAutocompleteBlockedByActiveRun() {
  const isRunning = (typeof importedIsActiveTabRunning === 'function' && importedIsActiveTabRunning)
    || _autocompleteGlobalFunction('isActiveTabRunning');
  return typeof isRunning === 'function' && isRunning();
}

function _autocompleteWorkspaceCacheApi() {
  return {
    getDirectoryHints: (typeof importedGetWorkspaceAutocompleteDirectoryHints !== 'undefined' && importedGetWorkspaceAutocompleteDirectoryHints)
      || _autocompleteGlobalFunction('getWorkspaceAutocompleteDirectoryHints'),
    getFileHints: (typeof importedGetWorkspaceAutocompleteFileHints !== 'undefined' && importedGetWorkspaceAutocompleteFileHints)
      || _autocompleteGlobalFunction('getWorkspaceAutocompleteFileHints'),
  };
}

function _autocompleteOnUiEvent(name, handler) {
  const onEvent = (typeof importedOnUiEvent !== 'undefined' && importedOnUiEvent)
    || _autocompleteGlobalFunction('onUiEvent');
  if (typeof onEvent === 'function') onEvent(name, handler);
}

function _autocompleteWorkspacePathHints(kind, token) {
  const readHints = (
    typeof importedGetWorkspaceAutocompletePathHints !== 'undefined'
    && importedGetWorkspaceAutocompletePathHints
  ) || _autocompleteGlobalFunction('getWorkspaceAutocompletePathHints');
  return typeof readHints === 'function' ? readHints(kind, token) : [];
}

function _autocompleteWorkspaceFlagFileHints(token) {
  const readHints = (
    typeof importedGetWorkspaceAutocompleteFlagFileHints !== 'undefined'
    && importedGetWorkspaceAutocompleteFlagFileHints
  )
    || _autocompleteGlobalFunction('getWorkspaceAutocompleteFlagFileHints');
  if (typeof readHints === 'function') return readHints(token);
  const getFileHints = _autocompleteWorkspaceCacheApi().getFileHints;
  return typeof getFileHints === 'function' ? getFileHints() : [];
}

function _autocompleteRuntimeContext(registry) {
  const readContext = (
    typeof importedGetRuntimeAutocompleteContext !== 'undefined'
    && importedGetRuntimeAutocompleteContext
  ) || _autocompleteGlobalFunction('getRuntimeAutocompleteContext');
  return typeof readContext === 'function' ? readContext(registry) : {};
}

function _autocompleteRuntimeItems(ctx) {
  const readItems = (
    typeof importedGetRuntimeAutocompleteItems !== 'undefined'
    && importedGetRuntimeAutocompleteItems
  ) || _autocompleteGlobalFunction('getRuntimeAutocompleteItems');
  return typeof readItems === 'function'
    ? readItems(ctx, autocompleteCore.buildItem, autocompleteCore.filterItems)
    : [];
}

function _autocompleteGrepOutputSuggestions(ctx) {
  const readItems = (
    typeof importedGetGrepOutputSuggestions !== 'undefined'
    && importedGetGrepOutputSuggestions
  ) || _autocompleteGlobalFunction('getGrepOutputSuggestions');
  return typeof readItems === 'function'
    ? readItems(ctx, autocompleteCore.buildItem, autocompleteCore.filterItems)
    : [];
}

function _autocompleteTokenContext(value, cursorPos) {
  return autocompleteCore.tokenContextFromText(value, cursorPos, 0);
}

function _autocompletePipeContext(value, cursorPos) {
  const text = String(value || '');
  const cursor = Math.max(0, Math.min(typeof cursorPos === 'number' ? cursorPos : text.length, text.length));
  const firstPipeIndex = text.indexOf('|');
  if (firstPipeIndex < 0 || cursor <= firstPipeIndex) return null;

  const baseCommand = text.slice(0, firstPipeIndex).trim();
  if (!baseCommand) return null;

  const shellControlRe = /(^|[\s|])(?:&&|\|\||;|;;|>>?|<|&)(?=$|\s)/;
  if (shellControlRe.test(baseCommand)) return null;

  const stageSection = text.slice(firstPipeIndex + 1, cursor);
  const fullStageSection = text.slice(firstPipeIndex + 1);
  const rawStages = fullStageSection.split('|');
  const completedStageCount = stageSection.split('|').length - 1;
  const priorStages = rawStages.slice(0, completedStageCount);
  const invalidPriorStage = priorStages.some((stage) => {
    const stageText = String(stage || '').trim();
    if (!stageText || shellControlRe.test(stageText)) return true;
    const stageRoot = stageText.split(/\s+/, 1)[0].toLowerCase();
    const registry = _getAutocompleteRegistry();
    const spec = registry[stageRoot];
    return !spec || !spec.pipe_command;
  });
  if (invalidPriorStage) return null;

  const pipeIndex = text.lastIndexOf('|', cursor - 1);
  if (pipeIndex < 0) return null;
  const stageOffset = pipeIndex + 1;
  const stageText = text.slice(stageOffset);
  const stageCursor = Math.max(0, cursor - stageOffset);
  return autocompleteCore.tokenContextFromText(stageText, stageCursor, stageOffset);
}

function _hintsToItems(hints, ctx, options = {}) {
  const replaceStart = typeof options.replaceStart === 'number' ? options.replaceStart : ctx.tokenStart;
  const replaceEnd = typeof options.replaceEnd === 'number' ? options.replaceEnd : ctx.tokenEnd;
  const matchQuery = typeof options.matchQuery === 'string' ? options.matchQuery : null;
  return (Array.isArray(hints) ? hints : []).map((item) => {
    const isObject = item && typeof item === 'object';
    const value = isObject ? item.value : item;
    const hintOnly = isObject && item.hintOnly != null
      ? item.hintOnly
      : (isObject && item.hint_only != null ? item.hint_only : null);
    const built = autocompleteCore.buildItem({
      value,
      label: isObject && item.label != null ? item.label : value,
      description: isObject ? (item.description || '') : '',
      replaceStart,
      replaceEnd,
      insertValue: isObject && item.insertValue != null ? item.insertValue : null,
      hintOnly,
    });
    if (matchQuery !== null) built.matchQuery = matchQuery;
    return built;
  });
}

const RECENT_VALUE_LIMIT = autocompleteCore.RECENT_VALUE_LIMIT;
const RECENT_VALUE_KINDS = ['domain', 'ip', 'url', 'port_set'];
const RECENT_VALUE_CAPTURE_TYPES = ['domain', 'host', 'target', 'ip', 'url', 'port_set'];
let acRecentValues = {
  domain: [],
  ip: [],
  url: [],
  port_set: [],
};
const acRecentValuePersistPromises = new Set();
const acPendingRecentValueCommands = [];
let acProjectTargets = [];
let acProjects = [];
let acSchedules = [];
let acWatchers = [];

function _readRecentValues(kind = '') {
  const normalizedKind = String(kind || '').trim().toLowerCase();
  if (normalizedKind) return (acRecentValues[normalizedKind] || []).slice(0, RECENT_VALUE_LIMIT);
  return Object.assign({}, ...RECENT_VALUE_KINDS.map(itemKind => ({
    [itemKind]: (acRecentValues[itemKind] || []).slice(0, RECENT_VALUE_LIMIT),
  })));
}

function _readProjectTargets() {
  return acProjectTargets.slice(0, 200);
}

function _readAutocompleteProjects() {
  return acProjects.slice(0, 200);
}

function _readAutocompleteSchedules() {
  return acSchedules.slice(0, 200);
}

function _readAutocompleteWatchers() {
  return acWatchers.slice(0, 200);
}

function _setRecentValuesByKind(valuesByKind) {
  const next = {
    domain: [],
    ip: [],
    url: [],
    port_set: [],
  };
  RECENT_VALUE_KINDS.forEach((kind) => {
    const items = valuesByKind && Array.isArray(valuesByKind[kind]) ? valuesByKind[kind] : [];
    const normalized = autocompleteCore.normalizeRecentValueList(items.map(value => ({ kind, value })));
    next[kind] = normalized.map(item => item.value).slice(0, RECENT_VALUE_LIMIT);
  });
  acRecentValues = next;
  return _readRecentValues();
}

function setRecentValues(items) {
  const grouped = {
    domain: [],
    ip: [],
    url: [],
    port_set: [],
  };
  autocompleteCore.normalizeRecentValueList(items).forEach((item) => {
    if (grouped[item.kind]) grouped[item.kind].push(item.value);
  });
  return _setRecentValuesByKind(grouped);
}

function setProjectAutocompleteTargets(items) {
  const seen = new Set();
  acProjectTargets = (Array.isArray(items) ? items : [])
    .map((item) => {
      if (typeof item === 'string') return { value: item, type: 'target', label: '' };
      if (!item || typeof item !== 'object') return null;
      return {
        value: String(item.value || '').trim(),
        type: String(item.type || 'target').trim().toLowerCase(),
        label: String(item.label || '').trim(),
      };
    })
    .filter((item) => {
      if (!item || !item.value) return false;
      const key = `${item.type}\x1f${item.value.toLowerCase()}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 200);
  return _readProjectTargets();
}

function setProjectAutocompleteProjects(items) {
  const seen = new Set();
  acProjects = (Array.isArray(items) ? items : [])
    .map((item) => {
      if (!item || typeof item !== 'object') return null;
      const slug = String(item.slug || '').trim();
      const name = String(item.name || '').trim();
      const id = String(item.id || '').trim();
      const value = slug || name || id;
      if (!value) return null;
      return {
        value,
        slug,
        name,
        id,
        status: String(item.status || '').trim().toLowerCase(),
      };
    })
    .filter((item) => {
      if (!item || !item.value) return false;
      const key = item.value.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 200);
  return _readAutocompleteProjects();
}

function setScheduleAutocompleteSchedules(items) {
  const seen = new Set();
  acSchedules = (Array.isArray(items) ? items : [])
    .map((item) => {
      if (!item || typeof item !== 'object') return null;
      const id = String(item.id || '').trim();
      if (!id) return null;
      const label = String(item.label || item.command_text || id).trim();
      const enabled = item.enabled !== false;
      return { id, label, enabled };
    })
    .filter((item) => {
      if (!item || !item.id || seen.has(item.id)) return false;
      seen.add(item.id);
      return true;
    })
    .slice(0, 200);
  return _readAutocompleteSchedules();
}

function setWatcherAutocompleteWatchers(items) {
  const seen = new Set();
  acWatchers = (Array.isArray(items) ? items : [])
    .map((item) => {
      if (!item || typeof item !== 'object') return null;
      const id = String(item.id || '').trim();
      if (!id) return null;
      const label = String(item.label || item.command_text || id).trim();
      const state = String(item.state || '').trim().toLowerCase() || 'ok';
      return { id, label, state };
    })
    .filter((item) => {
      if (!item || !item.id || seen.has(item.id)) return false;
      seen.add(item.id);
      return true;
    })
    .slice(0, 200);
  return _readAutocompleteWatchers();
}

function loadProjectAutocompleteTargets() {
  const projectListRequest = _autocompleteApiFetch('/projects?include_archived=1', { cache: 'no-store' })
    .then(resp => (resp && resp.ok && typeof resp.json === 'function' ? resp.json() : { projects: [] }))
    .then(data => setProjectAutocompleteProjects(data && data.projects));
  const activeTargetRequest = _autocompleteApiFetch('/projects/active', { cache: 'no-store' })
    .then(resp => (resp && resp.ok && typeof resp.json === 'function' ? resp.json() : { project: null }))
    .then((data) => {
      const project = data && data.project && typeof data.project === 'object' ? data.project : null;
      const projectId = project && project.id ? String(project.id) : '';
      if (!projectId) return setProjectAutocompleteTargets([]);
      return _autocompleteApiFetch(`/projects/${encodeURIComponent(projectId)}/targets?limit=200`, { cache: 'no-store' })
        .then(resp => (resp && resp.ok && typeof resp.json === 'function' ? resp.json() : { targets: [] }))
        .then(targetData => setProjectAutocompleteTargets(targetData && targetData.targets));
    })
  return Promise.all([projectListRequest, activeTargetRequest])
    .then(() => _readProjectTargets())
    .catch((err) => {
      setProjectAutocompleteProjects([]);
      setProjectAutocompleteTargets([]);
      _autocompleteLogClientError('failed to load project autocomplete targets', err);
      return _readProjectTargets();
    });
}

function loadScheduleAutocompleteHints() {
  return _autocompleteApiFetch('/schedules', { cache: 'no-store' })
    .then(resp => (resp && resp.ok && typeof resp.json === 'function' ? resp.json() : { schedules: [] }))
    .then(data => setScheduleAutocompleteSchedules(data && data.schedules))
    .catch((err) => {
      setScheduleAutocompleteSchedules([]);
      _autocompleteLogClientError('failed to load schedule autocomplete hints', err);
      return _readAutocompleteSchedules();
    });
}

function loadWatcherAutocompleteHints() {
  return _autocompleteApiFetch('/watchers', { cache: 'no-store' })
    .then(resp => (resp && resp.ok && typeof resp.json === 'function' ? resp.json() : { watchers: [] }))
    .then(data => setWatcherAutocompleteWatchers(data && data.watchers))
    .catch((err) => {
      setWatcherAutocompleteWatchers([]);
      _autocompleteLogClientError('failed to load watcher autocomplete hints', err);
      return _readAutocompleteWatchers();
    });
}

function _autocompleteProjectWorkspaceSyncStorageKey() {
  return 'darklab_project_workspace_changed';
}

function _autocompleteReloadProjectTargets() {
  loadProjectAutocompleteTargets().catch(() => {});
}

_autocompleteOnUiEvent('app:active-project-changed', _autocompleteReloadProjectTargets);
_autocompleteOnUiEvent('app:project-workspace-changed', _autocompleteReloadProjectTargets);

if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
  window.addEventListener('storage', (event) => {
    if (!event || event.key !== _autocompleteProjectWorkspaceSyncStorageKey()) return;
    let payload = {};
    try {
      payload = JSON.parse(event.newValue || '{}');
    } catch (_) {
      payload = {};
    }
    const payloadSession = payload && typeof payload.session_id === 'string' ? payload.session_id : '';
    const sessionId = _autocompleteSessionId();
    if (payloadSession && sessionId && payloadSession !== sessionId) return;
    _autocompleteReloadProjectTargets();
  });
}

function loadRecentValues() {
  return _autocompleteApiFetch('/session/recent-values')
    .then(resp => (resp && typeof resp.json === 'function' ? resp.json() : {}))
    .then((data) => {
      if (data && data.values && typeof data.values === 'object') _setRecentValuesByKind(data.values);
      processPendingRecentValueCommands();
      return _readRecentValues();
    })
    .catch((err) => {
      _autocompleteLogClientError('failed to load recent values', err);
      return _readRecentValues();
    });
}

function _persistRecentValues(items) {
  const values = autocompleteCore.normalizeRecentValueList(items);
  if (!values.length) return Promise.resolve(null);
  const request = _autocompleteApiFetch('/session/recent-values', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ values }),
  })
    .then(resp => (resp && typeof resp.json === 'function' ? resp.json() : null))
    .then((data) => {
      if (data && data.values && typeof data.values === 'object') _setRecentValuesByKind(data.values);
      return data;
    })
    .catch((err) => {
      _autocompleteLogClientError('failed to save recent values', err);
      return null;
    });
  const tracked = request.finally(() => {
    acRecentValuePersistPromises.delete(tracked);
  });
  acRecentValuePersistPromises.add(tracked);
  return tracked;
}

function flushRecentValues() {
  processPendingRecentValueCommands();
  if (!acRecentValuePersistPromises.size) return Promise.resolve([]);
  return Promise.all(Array.from(acRecentValuePersistPromises)).catch(() => []);
}

function _itemValueTypeIs(item, type) {
  return String(item && item.value_type || '').trim().toLowerCase() === String(type || '').trim().toLowerCase();
}

function _hintsContainValueType(hints, type) {
  return (Array.isArray(hints) ? hints : []).some(hint => _itemValueTypeIs(hint, type));
}

function _wordlistCategoriesFromHints(hints) {
  const categories = [];
  (Array.isArray(hints) ? hints : []).forEach((hint) => {
    autocompleteCore.normalizeWordlistCategories(hint && hint.wordlist_category).forEach((category) => {
      if (!categories.includes(category)) categories.push(category);
    });
  });
  return categories;
}

const AUTOCOMPLETE_VALUE_TYPE_HANDLERS = {
  domain: {
    emptySlot: false,
    slotFromHints: hints => _hintsContainValueType(hints, 'domain'),
    applySuggestions: (ctx, baseItems) => _withProjectTargetSuggestions(
      ctx,
      _withRecentValueSuggestions(ctx, baseItems, ['domain']),
      ['domain'],
    ),
  },
  host: {
    emptySlot: false,
    slotFromHints: hints => _hintsContainValueType(hints, 'host'),
    applySuggestions: (ctx, baseItems) => _withProjectTargetSuggestions(
      ctx,
      _withRecentValueSuggestions(ctx, baseItems, ['domain', 'ip']),
      ['host', 'domain', 'ip'],
    ),
  },
  ip: {
    emptySlot: false,
    slotFromHints: hints => _hintsContainValueType(hints, 'ip'),
    applySuggestions: (ctx, baseItems) => _withProjectTargetSuggestions(
      ctx,
      _withRecentValueSuggestions(ctx, baseItems, ['ip']),
      ['ip'],
    ),
  },
  cidr: {
    emptySlot: false,
    slotFromHints: hints => _hintsContainValueType(hints, 'cidr'),
    applySuggestions: (ctx, baseItems) => _withProjectTargetSuggestions(ctx, baseItems, ['cidr']),
  },
  port_set: {
    emptySlot: false,
    slotFromHints: hints => _hintsContainValueType(hints, 'port_set'),
    applySuggestions: (ctx, baseItems) => _withProjectTargetSuggestions(
      ctx,
      _withRecentValueSuggestions(ctx, baseItems, ['port_set']),
      ['port_set'],
    ),
  },
  url: {
    emptySlot: false,
    slotFromHints: hints => _hintsContainValueType(hints, 'url'),
    applySuggestions: (ctx, baseItems) => _withProjectTargetSuggestions(
      ctx,
      _withRecentValueSuggestions(ctx, baseItems, ['url']),
      ['url'],
    ),
  },
  wordlist: {
    emptySlot: { active: false, categories: [] },
    slotFromHints: (hints) => {
      const list = Array.isArray(hints) ? hints : [];
      if (!list.some(hint => _itemValueTypeIs(hint, 'wordlist'))) return { active: false, categories: [] };
      return { active: true, categories: _wordlistCategoriesFromHints(list) };
    },
    applySuggestions: (ctx, baseItems, slot) => (
      slot && slot.active ? _withWordlistSuggestions(ctx, baseItems, slot.categories) : baseItems
    ),
  },
  workspace_path: {
    emptySlot: false,
    slotFromHints: hints => _hintsContainValueType(hints, 'workspace_path'),
    applySuggestions: (ctx, baseItems) => baseItems,
    sourceHints: (_spec, hints) => {
      if (!(Array.isArray(hints) && hints.some(hint => _itemValueTypeIs(hint, 'workspace_path')))) return null;
      return _workspaceAutocompleteEntryHints();
    },
  },
  target: {
    emptySlot: false,
    slotFromHints: hints => _hintsContainValueType(hints, 'target'),
    applySuggestions: (ctx, baseItems) => _withProjectTargetSuggestions(
      ctx,
      _withRecentValueSuggestions(ctx, baseItems, ['domain', 'ip', 'url', 'port_set']),
      ['domain', 'host', 'ip', 'cidr', 'url', 'port_set', 'target'],
    ),
  },
};

function _valueTypeHandler(type) {
  return AUTOCOMPLETE_VALUE_TYPE_HANDLERS[String(type || '').trim().toLowerCase()] || null;
}

function _emptyValueTypeSlot(type) {
  const handler = _valueTypeHandler(type);
  const empty = handler && Object.prototype.hasOwnProperty.call(handler, 'emptySlot') ? handler.emptySlot : false;
  if (empty && typeof empty === 'object') return Array.isArray(empty) ? empty.slice() : Object.assign({}, empty);
  return empty;
}

function _valueTypeSlotFromHints(type, hints) {
  const handler = _valueTypeHandler(type);
  return handler && typeof handler.slotFromHints === 'function'
    ? handler.slotFromHints(hints)
    : _emptyValueTypeSlot(type);
}

function _valueTypeSourceHints(type, spec, hints) {
  const handler = _valueTypeHandler(type);
  return handler && typeof handler.sourceHints === 'function'
    ? handler.sourceHints(spec, hints)
    : null;
}

function _argHintsForTrigger(argHints, trigger) {
  if (Object.prototype.hasOwnProperty.call(argHints, trigger)) return argHints[trigger];
  return [];
}

function _argHintTriggersForValueType(spec, type) {
  const argHints = spec && spec.arg_hints && typeof spec.arg_hints === 'object' ? spec.arg_hints : {};
  return Object.entries(argHints)
    .filter(([trigger, hints]) => (
      trigger !== '__positional__'
      && Array.isArray(hints)
      && hints.some(hint => _itemValueTypeIs(hint, type))
    ))
    .map(([trigger]) => String(trigger || ''));
}

function _autocompletePreviousTokenExpectsValue(spec, previous) {
  if (!previous) return false;
  const expectsValue = Array.isArray(spec && spec.expects_value) ? spec.expects_value : [];
  return expectsValue.some(token => String(token || '') === previous);
}

function _concreteAutocompleteTokens(spec) {
  return new Set((spec && Array.isArray(spec.flags) ? spec.flags : [])
    .map(flag => String(flag && flag.value || '').toLowerCase())
    .filter(value => value && !value.startsWith('-') && !value.startsWith('+')));
}

function _filterFlagItems(items, query) {
  const q = String(query || '');
  if (!q) return (Array.isArray(items) ? items : []).slice();
  return (Array.isArray(items) ? items : []).filter((item) => (
    autocompleteCore.itemInsertValue(item).startsWith(q)
  ));
}

function _positionalHintPosition(hint) {
  const position = Number(hint && hint.position);
  return Number.isInteger(position) && position > 0 ? position : 0;
}

function _positionalHintsForSlot(spec, slotIndex) {
  const hints = spec && spec.arg_hints && Array.isArray(spec.arg_hints.__positional__)
    ? spec.arg_hints.__positional__
    : [];
  if (!hints.some(hint => _positionalHintPosition(hint) > 0)) return hints;
  const position = slotIndex + 1;
  return hints.filter(hint => {
    const hintPosition = _positionalHintPosition(hint);
    return !hintPosition || hintPosition === position;
  });
}

function _positionalHintSlotsForValueType(spec, type) {
  const hints = spec && spec.arg_hints && Array.isArray(spec.arg_hints.__positional__)
    ? spec.arg_hints.__positional__
    : [];
  const maxPosition = hints.reduce(
    (max, hint) => Math.max(max, _positionalHintPosition(hint)),
    0,
  );
  if (!maxPosition) return hints.map(hint => _valueTypeSlotFromHints(type, [hint]));
  return Array.from({ length: maxPosition }, (_, index) => (
    _valueTypeSlotFromHints(type, _positionalHintsForSlot(spec, index))
  ));
}

function _walkAutocompletePositionalValues(ctx, spec, contextSpec = {}, visitor = () => {}, options = {}) {
  const expectsValue = Array.isArray(spec && spec.expects_value) ? spec.expects_value : [];
  const expectsExact = new Set(expectsValue.map(token => String(token || '')));
  const concreteTokens = options.skipConcreteTokens ? _concreteAutocompleteTokens(spec) : new Set();
  const subTokens = contextSpec && Array.isArray(contextSpec.subcommandTokens)
    ? contextSpec.subcommandTokens
    : (contextSpec && contextSpec.subcommandToken ? [contextSpec.subcommandToken] : []);
  const tokens = Array.isArray(options.tokens)
    ? options.tokens
    : ctx.tokens.filter(token => token.end <= ctx.tokenStart);
  const triggerExact = new Set((options.triggers || []).map(trigger => String(trigger || '')));
  let skipNext = false;
  let positionalIndex = 0;
  for (let index = 1; index < tokens.length; index += 1) {
    const token = tokens[index];
    const tokenValue = String(token.value || '');
    const lower = tokenValue.toLowerCase();
    const previous = index > 0 ? String(tokens[index - 1].value || '') : '';
    const previousLower = previous.toLowerCase();
    if (!tokenValue) continue;
    if (subTokens.some(subToken => subToken && token.start === subToken.start && token.end === subToken.end)) continue;
    if (triggerExact.has(previous)) {
      visitor({
        triggered: true,
        token,
        tokenValue,
        lower,
        previous,
        previousLower,
        positionalIndex,
      });
      skipNext = false;
      continue;
    }
    if (skipNext) {
      skipNext = false;
      continue;
    }
    if (expectsExact.has(tokenValue)) {
      skipNext = true;
      continue;
    }
    if (tokenValue.startsWith('-') || tokenValue.startsWith('+') || concreteTokens.has(lower)) continue;
    visitor({
      triggered: false,
      token,
      tokenValue,
      lower,
      previous,
      previousLower,
      positionalIndex,
    });
    positionalIndex += 1;
  }
}

function _countCompletedPositionalValues(ctx, spec, contextSpec = {}) {
  let count = 0;
  _walkAutocompletePositionalValues(ctx, spec, contextSpec, () => {
    count += 1;
  }, {
    skipConcreteTokens: true,
  });
  return count;
}

function _countCompletedPositionalArgs(ctx, spec) {
  let count = 0;
  _walkAutocompletePositionalValues(ctx, spec, {}, () => {
    count += 1;
  });
  return count;
}

function _recentValueKindForToken(type, tokenValue) {
  const normalizedType = String(type || '').trim().toLowerCase();
  const candidates = normalizedType === 'host'
    ? ['domain', 'ip']
    : (normalizedType === 'target' ? ['domain', 'ip', 'url', 'port_set'] : [normalizedType]);
  for (const kind of candidates) {
    const normalized = autocompleteCore.normalizeRecentValue(kind, tokenValue);
    if (normalized.kind && normalized.value) return normalized;
  }
  return { kind: '', value: '' };
}

function _hintRecentValueTypes(hints) {
  const found = [];
  (Array.isArray(hints) ? hints : []).forEach((hint) => {
    RECENT_VALUE_CAPTURE_TYPES.forEach((type) => {
      if (_itemValueTypeIs(hint, type) && !found.includes(type)) found.push(type);
    });
  });
  return found;
}

function _positionalHintSlotsForRecentValues(spec) {
  const perTypeSlots = RECENT_VALUE_CAPTURE_TYPES.map(type => (
    _positionalHintSlotsForValueType(spec, type).map((slot, index) => (
      slot && _recentValuePositionalSlotCapturable(spec, index)
    ))
  ));
  const maxLength = perTypeSlots.reduce((max, slots) => Math.max(max, slots.length), 0);
  return Array.from({ length: maxLength }, (_, index) => perTypeSlots.some(slots => !!slots[index]));
}

function _hintLooksLikeFileInput(hint) {
  if (!hint || typeof hint !== 'object') return false;
  const text = [
    hint.value,
    hint.label,
    hint.placeholder,
    hint.description,
  ].map(value => String(value || '').trim().toLowerCase()).filter(Boolean).join(' ');
  if (!text) return false;
  return /(^|[\s_-])(file|files|wordlist|path|paths)([\s_-]|$)/.test(text)
    || /\bone [\w/-]+ per line\b/.test(text)
    || /<[^>]*(?:file|list|path|wordlist)[^>]*>/.test(text);
}

function _recentValueHintsCapturable(hints) {
  const list = Array.isArray(hints) ? hints : [];
  return list.some(hint => RECENT_VALUE_CAPTURE_TYPES.some(type => _itemValueTypeIs(hint, type)))
    && !list.some(_hintLooksLikeFileInput);
}

function _recentValueTriggerCapturable(spec, trigger) {
  const key = String(trigger || '');
  if (!key) return false;
  const workspaceFlags = new Set((Array.isArray(spec && spec.workspace_file_flags) ? spec.workspace_file_flags : [])
    .map(flag => String(flag || ''))
    .filter(Boolean));
  if (workspaceFlags.has(key)) return false;
  const hints = spec && spec.arg_hints && Object.prototype.hasOwnProperty.call(spec.arg_hints, key)
    ? spec.arg_hints[key]
    : [];
  return _recentValueHintsCapturable(hints);
}

function _recentValuePositionalSlotCapturable(spec, slotIndex) {
  const hints = _positionalHintsForSlot(spec, slotIndex);
  return _recentValueHintsCapturable(hints);
}

function _argHintTriggersForRecentValues(spec) {
  const seen = new Set();
  const triggers = [];
  RECENT_VALUE_CAPTURE_TYPES.forEach((type) => {
    _argHintTriggersForValueType(spec, type).forEach((trigger) => {
      const key = String(trigger || '');
      if (!key || seen.has(key) || !_recentValueTriggerCapturable(spec, key)) return;
      seen.add(key);
      triggers.push(trigger);
    });
  });
  return triggers;
}

function _collectRecentValuesFromPositionalValues(ctx, spec, contextSpec, triggers) {
  const positionalSlots = _positionalHintSlotsForRecentValues(spec);
  const found = [];
  _walkAutocompletePositionalValues(ctx, spec, contextSpec, ({ triggered, tokenValue, positionalIndex, previous }) => {
    if (triggered || positionalSlots[positionalIndex]) {
      const hints = triggered ? _argHintsForTrigger(spec.arg_hints || {}, previous) : _positionalHintsForSlot(spec, positionalIndex);
      for (const type of _hintRecentValueTypes(hints)) {
        const value = _recentValueKindForToken(type, tokenValue);
        if (value.kind && value.value) {
          found.push(value);
          break;
        }
      }
    }
  }, {
    tokens: ctx.tokens,
    triggers,
    skipConcreteTokens: true,
  });
  return found;
}

function _storeRecentValues(found) {
  if (!found.length) return [];
  const next = [];
  found.concat(RECENT_VALUE_KINDS.flatMap(kind => (
    _readRecentValues(kind).map(value => ({ kind, value }))
  ))).forEach((item) => {
    const normalized = autocompleteCore.normalizeRecentValue(item.kind, item.value);
    if (!normalized.kind || !normalized.value) return;
    if (next.some(existing => existing.kind === normalized.kind && existing.value === normalized.value)) return;
    if (next.filter(existing => existing.kind === normalized.kind).length >= RECENT_VALUE_LIMIT) return;
    next.push(normalized);
  });
  setRecentValues(next);
  _persistRecentValues(found);
  return found;
}

function _autocompleteValueTypeSlot(ctx, spec, contextSpec = {}, type = '') {
  if (!spec) return _emptyValueTypeSlot(type);
  const previous = String(ctx.previousToken || '');
  const argHints = spec.arg_hints || {};
  const triggers = _argHintTriggersForValueType(spec, type);
  for (const trigger of triggers) {
    if (trigger === previous) {
      return _valueTypeSlotFromHints(type, _argHintsForTrigger(argHints, trigger));
    }
  }
  if (_autocompletePreviousTokenExpectsValue(spec, previous)) return _emptyValueTypeSlot(type);
  if (ctx.currentToken.startsWith('-') || ctx.currentToken.startsWith('+')) return _emptyValueTypeSlot(type);
  const slots = _positionalHintSlotsForValueType(spec, type);
  if (!slots.length) return _emptyValueTypeSlot(type);
  const index = _countCompletedPositionalValues(ctx, spec, contextSpec);
  return slots[index] || _emptyValueTypeSlot(type);
}

function _autocompleteValueTypeSlots(ctx, spec, contextSpec = {}) {
  return {
    target: _autocompleteValueTypeSlot(ctx, spec, contextSpec, 'target'),
    url: _autocompleteValueTypeSlot(ctx, spec, contextSpec, 'url'),
    host: _autocompleteValueTypeSlot(ctx, spec, contextSpec, 'host'),
    ip: _autocompleteValueTypeSlot(ctx, spec, contextSpec, 'ip'),
    cidr: _autocompleteValueTypeSlot(ctx, spec, contextSpec, 'cidr'),
    port_set: _autocompleteValueTypeSlot(ctx, spec, contextSpec, 'port_set'),
    domain: _autocompleteValueTypeSlot(ctx, spec, contextSpec, 'domain'),
    wordlist: _autocompleteValueTypeSlot(ctx, spec, contextSpec, 'wordlist'),
  };
}

function _recentValueAutocompleteItems(ctx, kinds = []) {
  return (Array.isArray(kinds) ? kinds : [])
    .flatMap(kind => _readRecentValues(kind).map(value => ({ kind, value })))
    .map(item => autocompleteCore.buildItem({
      value: item.value,
      description: 'Recent target',
      replaceStart: ctx.tokenStart,
      replaceEnd: ctx.tokenEnd,
    }));
}

function _projectTargetAutocompleteItems(ctx, allowedTypes = []) {
  const allowed = new Set((Array.isArray(allowedTypes) ? allowedTypes : [])
    .map(type => String(type || '').trim().toLowerCase())
    .filter(Boolean));
  return _readProjectTargets()
    .filter(target => !allowed.size || allowed.has(target.type))
    .map(target => autocompleteCore.buildItem({
      value: target.value,
      description: [
        'Project target',
        target.type,
        ...(Array.isArray(target.labels) ? target.labels.map(label => label && label.label).filter(Boolean) : []),
      ].filter(Boolean).join(' · '),
      replaceStart: ctx.tokenStart,
      replaceEnd: ctx.tokenEnd,
    }));
}

function _wordlistAutocompleteItems(ctx, categories = []) {
  const categorySet = new Set(autocompleteCore.normalizeWordlistCategories(categories));
  const state = _autocompleteState();
  const source = Array.isArray(state.acWordlists) ? state.acWordlists : [];
  const filtered = source.filter((item) => {
    if (!categorySet.size) return true;
    const itemCategories = autocompleteCore.normalizeWordlistCategories(item && (item.wordlist_category || item.category));
    return itemCategories.some(category => categorySet.has(category));
  });
  const items = filtered.map(item => autocompleteCore.buildItem({
    value: String(item && item.value || ''),
    label: String(item && (item.label || item.value) || ''),
    description: String(item && item.description || 'Installed wordlist'),
    replaceStart: ctx.tokenStart,
    replaceEnd: ctx.tokenEnd,
  })).filter(item => item.value);
  return autocompleteCore.filterItems(items, ctx && ctx.currentToken);
}

function _prependDedupedItems(specialItems, baseItems) {
  if (!Array.isArray(specialItems) || !specialItems.length) return baseItems;
  const seen = new Set(specialItems.map(item => autocompleteCore.itemInsertValue(item).toLowerCase()));
  const rest = (Array.isArray(baseItems) ? baseItems : []).filter(item => {
    const key = autocompleteCore.itemInsertValue(item).toLowerCase();
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  return specialItems.concat(rest);
}

function _withRecentValueSuggestions(ctx, baseItems, kinds = []) {
  const recentItems = autocompleteCore.filterItems(_recentValueAutocompleteItems(ctx, kinds), ctx.currentToken);
  return _prependDedupedItems(recentItems, baseItems);
}

function _withProjectTargetSuggestions(ctx, baseItems, allowedTypes = []) {
  const targetItems = autocompleteCore.filterItems(
    _projectTargetAutocompleteItems(ctx, allowedTypes),
    ctx.currentToken,
  );
  return _prependDedupedItems(targetItems, baseItems);
}

function _withWordlistSuggestions(ctx, baseItems, categories = []) {
  const wordlistItems = _wordlistAutocompleteItems(ctx, categories);
  return _prependDedupedItems(wordlistItems, baseItems);
}

// True when the hint source reported any workspace signal: a workspace file
// flag (e.g. `-iL`), a slash-path context, or a typed workspace-path slot. In
// all of these the base items are already workspace entries, so scan-target or
// recent-value injection does not belong.
function _resolvedWorkspaceContext(resolved) {
  return !!(resolved && (
    resolved.workspaceFlagActive
    || resolved.workspacePathActive
    || resolved.workspaceValueActive
  ));
}

function _withTypedValueSlotSuggestions(ctx, baseItems, valueSlots = {}, options = {}) {
  const wordlistHandler = _valueTypeHandler('wordlist');
  if (wordlistHandler && valueSlots.wordlist && valueSlots.wordlist.active) {
    return wordlistHandler.applySuggestions(ctx, baseItems, valueSlots.wordlist);
  }
  if (options.workspaceContext) {
    // Workspace-file context: baseItems are already workspace entries, so do
    // not prepend project targets or recent scan values.
    return baseItems;
  }
  for (const type of ['target', 'url', 'host', 'ip', 'cidr', 'port_set', 'domain']) {
    const handler = _valueTypeHandler(type);
    if (handler && valueSlots[type]) {
      return handler.applySuggestions(ctx, baseItems, valueSlots[type]);
    }
  }
  return baseItems;
}

function rememberRecentValuesFromCommand(command, options = {}) {
  const text = String(command || '').trim();
  if (!text) return [];
  const registry = _getAutocompleteRegistry();
  const ctx = _autocompleteTokenContext(text, text.length);
  const rootSpec = ctx.commandRoot ? registry[ctx.commandRoot] : null;
  if (!rootSpec) {
    if (!options.skipQueue && !_autocompleteRegistryHasEntries()) _queueRecentValueCommand(text);
    return [];
  }
  const contextSpec = _autocompleteSpecForContext(ctx, rootSpec);
  const spec = contextSpec.spec;
  if (!spec) return [];

  return _storeRecentValues(
    _collectRecentValuesFromPositionalValues(ctx, spec, contextSpec, _argHintTriggersForRecentValues(spec)),
  );
}

function _mergeAutocompleteRegistry(base, overlay) {
  return Object.assign({}, base || {}, overlay || {});
}

function _workspaceAutocompleteHintsForFlag(spec, trigger, ctx = null) {
  const flags = Array.isArray(spec && spec.workspace_file_flags) ? spec.workspace_file_flags : [];
  const normalizedTrigger = String(trigger || '');
  if (!flags.some(flag => String(flag || '') === normalizedTrigger)) return null;
  if (ctx) {
    const hints = _autocompleteWorkspaceFlagFileHints(ctx.currentToken);
    return Array.isArray(hints) ? hints : [];
  }
  const getFileHints = _autocompleteWorkspaceCacheApi().getFileHints;
  if (typeof getFileHints !== 'function') return [];
  const hints = getFileHints();
  return Array.isArray(hints) ? hints : [];
}

function _workspaceAutocompleteEntryHints() {
  const workspaceCache = _autocompleteWorkspaceCacheApi();
  const fileHints = typeof workspaceCache.getFileHints === 'function'
    ? workspaceCache.getFileHints()
    : [];
  const directoryHints = typeof workspaceCache.getDirectoryHints === 'function'
    ? workspaceCache.getDirectoryHints()
    : [];
  return [
    ...(Array.isArray(fileHints) ? fileHints : []),
    ...(Array.isArray(directoryHints) ? directoryHints : []),
  ];
}

function _workspaceAutocompleteHintsForTypedSlot(spec, hints) {
  const list = Array.isArray(hints) ? hints : [];
  for (const hint of list) {
    const valueType = String(hint && hint.value_type || '').trim().toLowerCase();
    if (!valueType) continue;
    const sourceHints = _valueTypeSourceHints(valueType, spec, list);
    if (sourceHints !== null) return sourceHints;
  }
  return null;
}

function _autocompleteWorkspacePathKindFromArray(kinds, index) {
  if (!Array.isArray(kinds) || index < 0 || index >= kinds.length) return '';
  const kind = String(kinds[index] || '').trim().toLowerCase();
  return ['file', 'directory', 'any'].includes(kind) ? kind : '';
}

function _autocompleteWorkspacePathKind(ctx, spec) {
  const pathKinds = spec && spec.workspace_path_arg_kinds;
  if (!pathKinds || typeof pathKinds !== 'object') return '';
  const completedTokens = ctx.tokens.filter(token => token.end <= ctx.tokenStart);
  for (let index = 1; index < completedTokens.length; index += 1) {
    const trigger = String(completedTokens[index].value || '').toLowerCase();
    const kinds = pathKinds[trigger];
    if (!Array.isArray(kinds)) continue;
    const argIndex = completedTokens
      .slice(index + 1)
      .filter(token => {
        const value = String(token && token.value || '');
        return value && !value.startsWith('-') && !value.startsWith('+');
      })
      .length;
    return _autocompleteWorkspacePathKindFromArray(kinds, argIndex);
  }
  return _autocompleteWorkspacePathKindFromArray(
    pathKinds.__positional__,
    _countCompletedPositionalArgs(ctx, spec),
  );
}

function _workspaceAutocompletePathHintsForContext(ctx, spec) {
  if (!String(ctx.currentToken || '').includes('/')) return null;
  const kind = _autocompleteWorkspacePathKind(ctx, spec);
  if (!kind) return null;
  const hints = _autocompleteWorkspacePathHints(kind, ctx.currentToken);
  return Array.isArray(hints) ? hints : [];
}

function _workspaceAutocompletePathFilterQuery(ctx) {
  const token = String(ctx && ctx.currentToken || '');
  const slashIndex = token.lastIndexOf('/');
  return slashIndex >= 0 ? token.slice(slashIndex + 1) : token;
}

function _autocompleteSpecHasWorkspacePathKinds(spec) {
  return !!(spec && spec.workspace_path_arg_kinds && typeof spec.workspace_path_arg_kinds === 'object');
}

function _resolveAutocompleteHintSource(ctx, spec, baseHints, options = {}) {
  const workspaceFlag = Object.prototype.hasOwnProperty.call(options, 'workspaceFlag')
    ? options.workspaceFlag
    : null;
  const workspaceHints = workspaceFlag != null
    ? _workspaceAutocompleteHintsForFlag(spec, workspaceFlag, ctx)
    : null;
  if (workspaceHints !== null) {
    return {
      hints: workspaceHints,
      filterQuery: ctx.currentToken,
      workspaceFlagActive: true,
      workspacePathActive: false,
    };
  }

  const workspacePathHints = _workspaceAutocompletePathHintsForContext(ctx, spec);
  if (workspacePathHints !== null) {
    return {
      hints: workspacePathHints,
      filterQuery: _workspaceAutocompletePathFilterQuery(ctx),
      workspacePathActive: true,
    };
  }

  const allowWorkspaceValue = options.allowWorkspaceValue !== false;
  const workspaceValueHints = allowWorkspaceValue && !_autocompleteSpecHasWorkspacePathKinds(spec)
    ? _workspaceAutocompleteHintsForTypedSlot(spec, baseHints)
    : null;
  return {
    hints: workspaceValueHints !== null ? workspaceValueHints : baseHints,
    filterQuery: ctx.currentToken,
    workspaceFlagActive: false,
    workspacePathActive: false,
    workspaceValueActive: workspaceValueHints !== null,
  };
}

function _getAutocompleteRegistry() {
  const state = _autocompleteState();
  const yamlRegistry = state.acContextRegistry || {};
  const runtimeRegistry = _autocompleteRuntimeContext(yamlRegistry);
  return _mergeAutocompleteRegistry(yamlRegistry, runtimeRegistry);
}

function _autocompleteRegistryHasEntries() {
  return Object.keys(_getAutocompleteRegistry()).length > 0;
}

function _queueRecentValueCommand(command) {
  const text = String(command || '').trim();
  if (!text) return;
  if (acPendingRecentValueCommands.includes(text)) return;
  acPendingRecentValueCommands.push(text);
  if (acPendingRecentValueCommands.length > 25) acPendingRecentValueCommands.shift();
}

function processPendingRecentValueCommands() {
  if (!acPendingRecentValueCommands.length || !_autocompleteRegistryHasEntries()) return [];
  const pending = acPendingRecentValueCommands.splice(0, acPendingRecentValueCommands.length);
  return pending.flatMap(command => rememberRecentValuesFromCommand(command, { skipQueue: true }));
}

function setAutocompleteCatalog(data = {}) {
  const next = {
    acSuggestions: Array.isArray(data.suggestions) ? data.suggestions : [],
    acContextRegistry: data.context && typeof data.context === 'object' ? data.context : {},
    acWordlists: Array.isArray(data.wordlists) ? data.wordlists : [],
    acSpecialCommands: data.special_commands || [],
    acBuiltinCommandRoots: data.builtin_command_roots || [],
  };
  const api = importedAppStateApi || AUTOCOMPLETE_SUGGESTIONS_GLOBAL.APP_STATE_API || null;
  if (api && typeof api.getState === 'function') Object.assign(api.getState(), next);
  if (AUTOCOMPLETE_SUGGESTIONS_GLOBAL) {
    AUTOCOMPLETE_SUGGESTIONS_GLOBAL.acSuggestions = next.acSuggestions;
    AUTOCOMPLETE_SUGGESTIONS_GLOBAL.acContextRegistry = next.acContextRegistry;
    AUTOCOMPLETE_SUGGESTIONS_GLOBAL.acWordlists = next.acWordlists;
    AUTOCOMPLETE_SUGGESTIONS_GLOBAL.acSpecialCommands = next.acSpecialCommands;
    AUTOCOMPLETE_SUGGESTIONS_GLOBAL.acBuiltinCommandRoots = next.acBuiltinCommandRoots;
  }
  processPendingRecentValueCommands();
  return next;
}

function _contextClosedByTokenArity(ctx, spec) {
  const closeAfter = spec && spec.close_after && typeof spec.close_after === 'object'
    ? spec.close_after
    : {};
  const entries = Object.entries(closeAfter);
  if (!entries.length || !ctx.atWhitespace) return false;
  const completedTokens = ctx.tokens.filter(token => token.end <= ctx.tokenStart);
  for (let index = 1; index < completedTokens.length; index += 1) {
    const token = String(completedTokens[index].value || '').toLowerCase();
    if (!Object.prototype.hasOwnProperty.call(closeAfter, token)) continue;
    const rawLimit = Number(closeAfter[token]);
    const limit = Number.isFinite(rawLimit) && rawLimit >= 0 ? rawLimit : 0;
    const following = completedTokens.slice(index + 1).filter(item => String(item.value || '').trim());
    if (following.length >= limit) return true;
  }
  return false;
}

function _mergeAutocompleteSpecForSubcommand(baseSpec, subSpec) {
  const merged = Object.assign({}, baseSpec || {}, subSpec || {});
  const flags = [];
  const seenFlags = new Set();
  [...((baseSpec && baseSpec.flags) || []), ...((subSpec && subSpec.flags) || [])].forEach(flag => {
    const key = String(flag && flag.value || '');
    if (!key || seenFlags.has(key)) return;
    seenFlags.add(key);
    flags.push(flag);
  });
  const expectsValue = [];
  const seenValueTokens = new Set();
  [...((baseSpec && baseSpec.expects_value) || []), ...((subSpec && subSpec.expects_value) || [])].forEach(token => {
    const key = String(token || '');
    if (!key || seenValueTokens.has(key)) return;
    seenValueTokens.add(key);
    expectsValue.push(token);
  });
  const argHints = Object.assign({}, (baseSpec && baseSpec.arg_hints) || {}, (subSpec && subSpec.arg_hints) || {});
  if (subSpec && Object.prototype.hasOwnProperty.call(subSpec.arg_hints || {}, '__positional__')) {
    argHints.__positional__ = subSpec.arg_hints.__positional__;
  } else {
    argHints.__positional__ = [];
  }
  return Object.assign(merged, {
    flags,
    expects_value: expectsValue,
    arg_hints: argHints,
    subcommands: (subSpec && subSpec.subcommands) || {},
    examples: (subSpec && subSpec.examples) || [],
  });
}

function _autocompleteSpecForContext(ctx, spec) {
  let activeSpec = spec;
  const activeSubcommands = [];
  const subcommandTokens = [];
  for (let index = 1; index < ctx.tokens.length; index += 1) {
    const subcommands = activeSpec && activeSpec.subcommands && typeof activeSpec.subcommands === 'object'
      ? activeSpec.subcommands
      : {};
    if (!Object.keys(subcommands).length) break;
    const token = ctx.tokens[index];
    if (!token) continue;
    const isCurrentToken = token.start === ctx.tokenStart && token.end === ctx.tokenEnd;
    if (token.end > ctx.tokenStart && !isCurrentToken) continue;
    const value = String(token.value || '').toLowerCase();
    if (Object.prototype.hasOwnProperty.call(subcommands, value)) {
      activeSpec = _mergeAutocompleteSpecForSubcommand(activeSpec, subcommands[value]);
      activeSubcommands.push(value);
      subcommandTokens.push(token);
    }
  }
  return {
    spec: activeSpec,
    activeSubcommand: activeSubcommands.join(' '),
    subcommandToken: subcommandTokens[subcommandTokens.length - 1] || null,
    subcommandTokens,
  };
}

function _buildExampleAutocompleteItems(examples, { replaceStart, replaceEnd, completionPrefix }) {
  return (examples || []).map(ex => Object.assign(autocompleteCore.buildItem({
    value: ex.value,
    description: ex.description || '',
    replaceStart,
    replaceEnd,
    insertValue: ex.value,
  }), { isExample: true, completionPrefix }));
}

function _collectAutocompleteExamples(spec) {
  const examples = [];
  const seen = new Set();

  function appendExample(example) {
    if (!example || typeof example !== 'object') return;
    const value = String(example.value || '').trim();
    if (!value) return;
    const key = value.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    examples.push(example);
  }

  ((spec && spec.examples) || []).forEach(appendExample);
  Object.values((spec && spec.subcommands) || {}).forEach(subSpec => {
    ((subSpec && subSpec.examples) || []).forEach(appendExample);
  });
  return examples;
}

function _filterExampleAutocompleteItems(items, typedPrefix) {
  const filtered = autocompleteCore.filterItems(items, typedPrefix);
  // Keep YAML-author order for examples while reusing the normal matcher to
  // decide which examples are visible.
  const matched = new Set(filtered);
  return items.filter(item => matched.has(item));
}

function _buildUniqueSubcommandExampleAutocomplete(ctx, rootSpec) {
  const subcommands = rootSpec && rootSpec.subcommands && typeof rootSpec.subcommands === 'object'
    ? rootSpec.subcommands
    : {};
  if (!Object.keys(subcommands).length) return [];
  if (ctx.atWhitespace || ctx.tokens.length !== 2 || !ctx.currentToken || ctx.currentToken.startsWith('-')) return [];
  const secondToken = ctx.tokens[1];
  if (!secondToken || secondToken.start !== ctx.tokenStart || secondToken.end !== ctx.tokenEnd) return [];

  const matches = autocompleteCore.filterItems(Object.keys(subcommands), ctx.currentToken);
  if (matches.length !== 1) return [];

  const subcommand = matches[0];
  const subSpec = subcommands[subcommand];
  if (!subSpec || !Array.isArray(subSpec.examples) || !subSpec.examples.length) return [];

  const typedPrefix = ctx.text.slice(0, ctx.tokenEnd);
  return _filterExampleAutocompleteItems(
    _buildExampleAutocompleteItems(subSpec.examples, {
      replaceStart: 0,
      replaceEnd: ctx.tokenEnd,
      completionPrefix: `${ctx.commandRoot} ${subcommand}`,
    }),
    typedPrefix,
  );
}

function _buildContextAutocomplete(ctx) {
  const registry = _getAutocompleteRegistry();
  const rootSpec = ctx.commandRoot ? registry[ctx.commandRoot] : null;
  const contextSpec = rootSpec ? _autocompleteSpecForContext(ctx, rootSpec) : { spec: null, activeSubcommand: '', subcommandToken: null };
  const spec = contextSpec.spec;

  if (!spec) {
    // Unknown command root — suggest matching command roots from the registry
    // while the user is still typing the first token (no trailing space yet).
    if (ctx.tokens.length <= 1 && !ctx.atWhitespace && ctx.commandRoot) {
      const matchingRoots = autocompleteCore.filterItems(Object.keys(registry), ctx.commandRoot);
      // If exactly one command matches and it has examples, show those directly
      // so the user sees full invocation patterns while still typing the root.
      if (matchingRoots.length === 1) {
        const matchedSpec = registry[matchingRoots[0]];
        const examples = _collectAutocompleteExamples(matchedSpec);
        if (examples.length) {
          return _filterExampleAutocompleteItems(
            _buildExampleAutocompleteItems(examples, {
              replaceStart: ctx.tokenStart,
              replaceEnd: ctx.tokenEnd,
              completionPrefix: matchingRoots[0],
            }),
            ctx.currentToken,
          );
        }
      }
      return matchingRoots.map(root => autocompleteCore.buildItem({
        value: root,
        description: '',
        replaceStart: ctx.tokenStart,
        replaceEnd: ctx.tokenEnd,
      }));
    }
    return [];
  }

  // Known command root being typed (no trailing space yet) — show examples so
  // users can discover full invocation patterns before they start adding flags.
  if (ctx.tokens.length === 1 && !ctx.atWhitespace) {
    const examples = _collectAutocompleteExamples(spec);
    if (!examples.length) return [];
    return _filterExampleAutocompleteItems(
      _buildExampleAutocompleteItems(examples, {
        replaceStart: ctx.tokenStart,
        replaceEnd: ctx.tokenEnd,
        completionPrefix: ctx.commandRoot,
      }),
      ctx.currentToken,
    );
  }

  const uniqueSubcommandExamples = _buildUniqueSubcommandExampleAutocomplete(ctx, rootSpec);
  if (uniqueSubcommandExamples.length) return uniqueSubcommandExamples;

  if (_contextClosedByTokenArity(ctx, spec)) return [];

  if (contextSpec.activeSubcommand && spec.examples && spec.examples.length) {
    const prefixEnd = ctx.atWhitespace ? ctx.cursor : ctx.tokenEnd;
    const typedPrefix = ctx.text.slice(0, prefixEnd);
    const subcommandIsCurrentToken = contextSpec.subcommandToken
      && ctx.tokenStart === contextSpec.subcommandToken.start
      && ctx.tokenEnd === contextSpec.subcommandToken.end;
    if (subcommandIsCurrentToken) {
      const examples = _filterExampleAutocompleteItems(
        _buildExampleAutocompleteItems(spec.examples, {
          replaceStart: 0,
          replaceEnd: prefixEnd,
          completionPrefix: `${ctx.commandRoot} ${contextSpec.activeSubcommand}`,
        }),
        typedPrefix,
      );
      if (examples.length) return examples;
    }
  }

  const currentIsFlag = ctx.currentToken.startsWith('-') || ctx.currentToken.startsWith('+');
  const argHints = spec.arg_hints || {};
  const argumentLimit = Number.isInteger(spec.argument_limit) && spec.argument_limit > 0
    ? spec.argument_limit
    : null;
  const allowPositionalHints = !argumentLimit
    || _countCompletedPositionalArgs(ctx, spec) < argumentLimit;

  const directHints = Object.prototype.hasOwnProperty.call(argHints, ctx.previousToken || '')
    ? argHints[ctx.previousToken || '']
    : null;
  const completedTokens = ctx.tokens.filter(token => token.end <= ctx.tokenStart);
  const sequenceArgHints = spec.sequence_arg_hints || {};
  const priorToken = completedTokens.length >= 2
    ? String(completedTokens[completedTokens.length - 2].value || '').toLowerCase()
    : '';
  const previousLower = String(ctx.previousToken || '').toLowerCase();
  const sequenceKey = `${priorToken} ${previousLower}`.trim();
  const sequenceHints = Object.prototype.hasOwnProperty.call(sequenceArgHints, sequenceKey)
    ? sequenceArgHints[sequenceKey]
    : null;
  const valueSlots = _autocompleteValueTypeSlots(ctx, spec, contextSpec);
  if (sequenceHints !== null) {
    const resolved = _resolveAutocompleteHintSource(ctx, spec, sequenceHints, {
      allowWorkspaceValue: false,
    });
    const sequenceItems = autocompleteCore.filterItems(
      _hintsToItems(resolved.hints, ctx, { matchQuery: resolved.filterQuery }),
      resolved.filterQuery,
    );
    return _withTypedValueSlotSuggestions(ctx, sequenceItems, valueSlots, {
      workspaceContext: _resolvedWorkspaceContext(resolved),
    });
  }
  if (directHints !== null) {
    const resolved = _resolveAutocompleteHintSource(ctx, spec, directHints, {
      workspaceFlag: ctx.previousToken || '',
    });
    const directItems = autocompleteCore.filterItems(
      _hintsToItems(resolved.hints, ctx, { matchQuery: resolved.filterQuery }),
      resolved.filterQuery,
    );
    return _withTypedValueSlotSuggestions(ctx, directItems, valueSlots, {
      workspaceContext: _resolvedWorkspaceContext(resolved),
    });
  }

  if (allowPositionalHints) {
    const concreteCommandTokens = (spec.flags || [])
      .filter(flag => {
        const value = String(flag.value || '');
        return value && !value.startsWith('-') && !value.startsWith('+');
      })
      .map(flag => autocompleteCore.buildItem({
        value: flag.value,
        description: flag.description || '',
        replaceStart: ctx.tokenStart,
        replaceEnd: ctx.tokenEnd,
        insertValue: flag.value,
      }));
    const matchingCommandTokens = autocompleteCore.filterItems(concreteCommandTokens, ctx.currentToken);
    if (matchingCommandTokens.length) return matchingCommandTokens;
  }

  const positionalHints = Object.prototype.hasOwnProperty.call(argHints, '__positional__')
    ? _positionalHintsForSlot(
      spec,
      _countCompletedPositionalValues(ctx, spec, contextSpec),
    )
    : [];

  if (!ctx.currentToken || currentIsFlag) {
    const usedFlags = new Set(
      ctx.tokens
        .filter(token => token.start !== ctx.tokenStart)
        .map(token => String(token.value || ''))
        .filter(token => token.startsWith('-') || token.startsWith('+'))
    );
    const flags = (spec.flags || [])
      .filter(flag => !usedFlags.has(String(flag.value || '')))
      .map(flag => autocompleteCore.buildItem({
        value: flag.value,
        description: flag.description || '',
        replaceStart: ctx.tokenStart,
        replaceEnd: ctx.tokenEnd,
        insertValue: flag.value,
      }));
    const filteredFlags = _filterFlagItems(flags, ctx.currentToken);
    if (!ctx.currentToken && ctx.atWhitespace && positionalHints.length && allowPositionalHints) {
      const resolved = _resolveAutocompleteHintSource(ctx, spec, positionalHints);
      const positionalItems = _hintsToItems(resolved.hints, ctx, { matchQuery: resolved.filterQuery });
      return _withTypedValueSlotSuggestions(
        ctx,
        filteredFlags.concat(positionalItems),
        valueSlots,
        { workspaceContext: _resolvedWorkspaceContext(resolved) },
      );
    }
    return filteredFlags;
  }

  if (positionalHints.length && allowPositionalHints) {
    const resolved = _resolveAutocompleteHintSource(ctx, spec, positionalHints);
    const positionalItems = autocompleteCore.filterItems(
      _hintsToItems(resolved.hints, ctx, { matchQuery: resolved.filterQuery }),
      resolved.filterQuery,
    );
    return _withTypedValueSlotSuggestions(ctx, positionalItems, valueSlots, {
      workspaceContext: _resolvedWorkspaceContext(resolved),
    });
  }
  const resolvedWorkspacePathHints = allowPositionalHints
    ? _resolveAutocompleteHintSource(ctx, spec, [], { allowWorkspaceValue: false })
    : null;
  if (resolvedWorkspacePathHints && resolvedWorkspacePathHints.workspacePathActive) {
    const pathItems = autocompleteCore.filterItems(
      _hintsToItems(resolvedWorkspacePathHints.hints, ctx, { matchQuery: resolvedWorkspacePathHints.filterQuery }),
      resolvedWorkspacePathHints.filterQuery,
    );
    return _withTypedValueSlotSuggestions(ctx, pathItems, valueSlots, {
      workspaceContext: _resolvedWorkspaceContext(resolvedWorkspacePathHints),
    });
  }
  return [];
}

function _buildPipeCommandAutocomplete(ctx, registry) {
  const items = Object.entries(registry)
    .filter(([, spec]) => spec && spec.pipe_command)
    .map(([root, spec]) => autocompleteCore.buildItem({
      value: spec.pipe_insert_value || root,
      label: spec.pipe_label || spec.pipe_insert_value || root,
      description: spec.pipe_description || '',
      replaceStart: ctx.tokenStart,
      replaceEnd: ctx.tokenEnd,
      insertValue: spec.pipe_insert_value || root,
    }));
  return autocompleteCore.filterItems(items, ctx.currentToken);
}

// Append output-token suggestions after the pipe stage's own context items,
// de-duplicating on insert value so a flag or hint is never repeated.
function _mergePipeItems(primary, extra) {
  if (!Array.isArray(extra) || !extra.length) return primary;
  const seen = new Set(primary.map((item) => autocompleteCore.itemInsertValue(item).toLowerCase()));
  const merged = primary.slice();
  extra.forEach((item) => {
    const key = autocompleteCore.itemInsertValue(item).toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    merged.push(item);
  });
  return merged;
}

function _buildPipeAutocomplete(ctx) {
  const registry = _getAutocompleteRegistry();
  if (!ctx.commandRoot) return _buildPipeCommandAutocomplete(ctx, registry);

  const spec = registry[ctx.commandRoot];
  if (!spec || !spec.pipe_command) return [];
  const contextItems = _buildContextAutocomplete(ctx);
  // Only grep takes a free-text pattern, so it is the only pipe helper that
  // benefits from output-derived token suggestions.
  if (ctx.commandRoot === 'grep') {
    const outputItems = _autocompleteGrepOutputSuggestions(ctx);
    return _mergePipeItems(contextItems, outputItems);
  }
  return contextItems;
}

function _buildFlatAutocomplete(value) {
  const q = String(value || '').trim();
  if (!q) return [];
  const state = _autocompleteState();
  const suggestions = Array.isArray(state.acSuggestions) ? state.acSuggestions : [];
  return autocompleteCore.filterItems(suggestions, q).slice(0, 24);
}

function getAutocompleteMatches(value, cursorPos) {
  if (_isAutocompleteBlockedByActiveRun()) return [];
  const text = String(value || '');
  const ctx = _autocompleteTokenContext(text, cursorPos);
  const pipeCtx = _autocompletePipeContext(text, cursorPos);
  const runtimeItems = !pipeCtx ? _autocompleteRuntimeItems(ctx) : [];
  let items = runtimeItems.length ? runtimeItems : (pipeCtx ? _buildPipeAutocomplete(pipeCtx) : _buildContextAutocomplete(ctx));
  if (!items.length && !pipeCtx) items = _buildFlatAutocomplete(text);

  if (!items.length) return [];
  if (typeof items[0] === 'string') {
    const q = text.trim().toLowerCase();
    if (items.some(item => String(item).toLowerCase() === q)) return [];
    return items;
  }

  // Hide the dropdown once the current token already equals the only suggestion.
  // Keep hint-only placeholders visible so the user still sees what argument
  // the command expects next, and keep exact flag matches visible so their
  // descriptions remain discoverable until the user types a trailing space.
  const singleItem = items[0];
  const singleItemIsFlag = String(singleItem && singleItem.value || '').startsWith('-')
    || String(singleItem && singleItem.value || '').startsWith('+');
  if (items.length === 1
      && !singleItem.hintOnly
      && !singleItemIsFlag
      && autocompleteCore.itemInsertValue(singleItem).toLowerCase() === ctx.currentToken.toLowerCase()) {
    return [];
  }
  return items;
}

function limitAutocompleteMatchesForDisplay(items, maxItems = 12) {
  return autocompleteCore.limitItemsForDisplay(items, maxItems);
}

if (typeof window !== 'undefined') {
  Object.assign(window, {
    getAutocompleteMatches,
    limitAutocompleteMatchesForDisplay,
  });
}

export {
  _readRecentValues,
  _readProjectTargets,
  _readAutocompleteProjects,
  _readAutocompleteSchedules,
  _readAutocompleteWatchers,
  _autocompleteTokenContext,
  flushRecentValues,
  getAutocompleteMatches,
  limitAutocompleteMatchesForDisplay,
  loadProjectAutocompleteTargets,
  loadScheduleAutocompleteHints,
  loadRecentValues,
  loadWatcherAutocompleteHints,
  rememberRecentValuesFromCommand,
  setAutocompleteCatalog,
};
