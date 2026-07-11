// Project-linking helpers for History rows and Run Details actions.
import { historyProjectFilter as importedHistoryProjectFilter } from '../../core/dom.js';
import { DarklabHistoryCore as importedHistoryCore } from '../../core/history_core.js';
import { showToast as importedShowToast } from '../../core/utils.js';
import { useMobileTerminalViewportMode as importedUseMobileTerminalViewportMode } from '../mobile/mobile_shell_layout.js';
import { showConfirm as importedShowConfirm } from '../../ui/ui_confirm.js';
import {
  applyProjectRunEntityUnlinkPreview,
  setCleanupNodeHidden,
} from '../../ui/cleanup_reasons.js';
import { bindDisclosure as importedBindDisclosure } from '../../ui/ui_disclosure.js';
import {
  enhanceAppSelects as importedEnhanceAppSelects,
  syncAppSelect as importedSyncAppSelect,
} from '../../ui/ui_helpers.js';
import {
  getHistoryProjectOptionsState as importedGetHistoryProjectOptionsState,
  refreshHistoryPanel as importedRefreshHistoryPanel,
  setHistoryProjectOptionsState as importedSetHistoryProjectOptionsState,
} from '../../history.js';
import { getHistoryRunModalState as importedGetHistoryRunModalState } from './history_run_modal_state_bridge.js';
import {
  apiFetch as importedRuntimeApiFetch,
  hasRuntimeHandler as importedHasRuntimeHandler,
  logClientError as importedRuntimeLogClientError,
} from '../../runtime_bridge.js';

const HISTORY_PROJECT_ACTIONS_GLOBAL = typeof window !== 'undefined' ? window : globalThis;
let fallbackHistoryProjectOptions = [];
let fallbackHistoryProjectOptionsLoaded = false;
let fallbackHistoryProjectOptionsLoading = null;

function _historyProjectCore() {
  return (typeof importedHistoryCore !== 'undefined' && importedHistoryCore)
    || null;
}

function _historyProjectNormalizeFilterValue(value) {
  const core = _historyProjectCore();
  if (core && typeof core.normalizeFilterValue === 'function') return core.normalizeFilterValue(value);
  if (typeof HISTORY_PROJECT_ACTIONS_GLOBAL._normalizeHistoryFilterValue === 'function') {
    return HISTORY_PROJECT_ACTIONS_GLOBAL._normalizeHistoryFilterValue(value);
  }
  return String(value || '').trim();
}

function _historyProjectFilterRef() {
  return (typeof importedHistoryProjectFilter !== 'undefined' && importedHistoryProjectFilter)
    || HISTORY_PROJECT_ACTIONS_GLOBAL.historyProjectFilter
    || null;
}

function _historyProjectShowToast(message, tone = 'success') {
  const toast = (typeof importedShowToast !== 'undefined' && importedShowToast)
    || HISTORY_PROJECT_ACTIONS_GLOBAL.showToast
    || null;
  if (typeof toast === 'function') toast(message, tone);
}

function _historyProjectShowConfirm(options) {
  const confirm = (typeof importedShowConfirm !== 'undefined' && importedShowConfirm)
    || HISTORY_PROJECT_ACTIONS_GLOBAL.showConfirm
    || null;
  return typeof confirm === 'function' ? confirm(options) : Promise.resolve(null);
}

function _historyProjectEnhanceAppSelects(root) {
  const enhance = (typeof importedEnhanceAppSelects !== 'undefined' && importedEnhanceAppSelects)
    || HISTORY_PROJECT_ACTIONS_GLOBAL.enhanceAppSelects
    || null;
  if (typeof enhance === 'function') enhance(root);
  return typeof enhance === 'function';
}

function _historyProjectSyncAppSelect(select) {
  const sync = (typeof importedSyncAppSelect !== 'undefined' && importedSyncAppSelect)
    || HISTORY_PROJECT_ACTIONS_GLOBAL.syncAppSelect
    || null;
  if (typeof sync === 'function') sync(select);
}

function _historyProjectUseMobileTerminalViewportMode() {
  const useMobile = (
    typeof importedUseMobileTerminalViewportMode !== 'undefined'
    && importedUseMobileTerminalViewportMode
  )
    || HISTORY_PROJECT_ACTIONS_GLOBAL.useMobileTerminalViewportMode;
  return typeof useMobile === 'function' ? useMobile() : false;
}

function _historyProjectRefreshHistoryPanel() {
  const refresh = (typeof importedRefreshHistoryPanel !== 'undefined' && importedRefreshHistoryPanel)
    || HISTORY_PROJECT_ACTIONS_GLOBAL.refreshHistoryPanel;
  return typeof refresh === 'function' ? refresh() : Promise.resolve();
}

function _historyProjectApiFetch(...args) {
  const fetcher = (
    typeof importedHasRuntimeHandler === 'function'
    && importedHasRuntimeHandler('apiFetch')
    && typeof importedRuntimeApiFetch === 'function'
      ? importedRuntimeApiFetch
      : null
  ) || HISTORY_PROJECT_ACTIONS_GLOBAL.apiFetch;
  return typeof fetcher === 'function' ? fetcher(...args) : Promise.reject(new Error('apiFetch unavailable'));
}

function _historyProjectLogClientError(...args) {
  const logger = (
    typeof importedHasRuntimeHandler === 'function'
    && importedHasRuntimeHandler('logClientError')
    && typeof importedRuntimeLogClientError === 'function'
      ? importedRuntimeLogClientError
      : null
  ) || HISTORY_PROJECT_ACTIONS_GLOBAL.logClientError;
  if (typeof logger === 'function') logger(...args);
}

function _historyProjectLogEvent(context, err, details = {}) {
  _historyProjectLogClientError(context, err, details);
}

function _historyProjectLogPayload(event, level, run, project, options = {}, extra = {}) {
  return {
    event,
    level,
    run_id: String(run?.id || ''),
    project_id: String(project?.id || ''),
    operation: String(options.operation || ''),
    include_entities: options.includeEntities === true,
    include_curated_entities: options.includeCuratedEntities === true,
    http_status: Number(extra.httpStatus || 0) || null,
  };
}

function _historyProjectRefreshProjectWorkspace() {
  const refresh = HISTORY_PROJECT_ACTIONS_GLOBAL.refreshProjectWorkspace;
  return typeof refresh === 'function' ? refresh() : Promise.resolve();
}

function _historyProjectOptionsState() {
  if (typeof importedGetHistoryProjectOptionsState === 'function') {
    return importedGetHistoryProjectOptionsState();
  }
  return {
    options: fallbackHistoryProjectOptions,
    loaded: fallbackHistoryProjectOptionsLoaded,
    loading: fallbackHistoryProjectOptionsLoading,
  };
}

function _setHistoryProjectOptionsState(updates = {}) {
  if (typeof importedSetHistoryProjectOptionsState === 'function') {
    return importedSetHistoryProjectOptionsState(updates);
  }
  if (Object.prototype.hasOwnProperty.call(updates, 'options')) {
    fallbackHistoryProjectOptions = Array.isArray(updates.options) ? updates.options : [];
  }
  if (Object.prototype.hasOwnProperty.call(updates, 'loaded')) {
    fallbackHistoryProjectOptionsLoaded = updates.loaded === true;
  }
  if (Object.prototype.hasOwnProperty.call(updates, 'loading')) {
    fallbackHistoryProjectOptionsLoading = updates.loading || null;
  }
  return _historyProjectOptionsState();
}

function _historyProjectDisplayName(project) {
  if (!project || typeof project !== 'object') return '';
  return String(project.name || project.slug || project.id || '').trim();
}

function _historyProjectLabelForId(projectId) {
  const normalized = _historyProjectNormalizeFilterValue(projectId);
  if (!normalized || normalized === 'all') return '';
  const project = _historyProjectOptionsState().options.find(item => String(item && item.id || '') === normalized);
  return _historyProjectDisplayName(project) || normalized;
}

function _syncHistoryProjectFilterOptions() {
  const projectFilter = _historyProjectFilterRef();
  if (!projectFilter) return;
  const selected = _historyProjectNormalizeFilterValue(window._historyFilters.projectId) || 'all';
  const projectOptions = _historyProjectOptionsState().options;
  projectFilter.replaceChildren();
  const allOption = document.createElement('option');
  allOption.value = 'all';
  allOption.textContent = 'project: all';
  projectFilter.appendChild(allOption);
  projectOptions.forEach((project) => {
    const projectId = String(project && project.id || '');
    if (!projectId) return;
    const option = document.createElement('option');
    option.value = projectId;
    option.textContent = `project: ${_historyProjectDisplayName(project) || projectId}`;
    projectFilter.appendChild(option);
  });
  if (selected !== 'all' && !projectOptions.some(project => String(project && project.id || '') === selected)) {
    const stale = document.createElement('option');
    stale.value = selected;
    stale.textContent = `project: ${selected}`;
    projectFilter.appendChild(stale);
  }
  projectFilter.value = selected;
  _historyProjectSyncAppSelect(projectFilter);
}

function _ensureHistoryProjectFilterOptions() {
  const state = _historyProjectOptionsState();
  if (state.loaded) return Promise.resolve(state.options);
  if (state.loading) return state.loading;
  const loading = _historyLoadProjectFilterOptions()
    .then(projects => {
      _setHistoryProjectOptionsState({ options: projects, loaded: true });
      _syncHistoryProjectFilterOptions();
      return projects;
    })
    .catch(err => {
      _historyProjectLogClientError('failed to load history project filter options', err);
      throw err;
    })
    .finally(() => {
      _setHistoryProjectOptionsState({ loading: null });
    });
  _setHistoryProjectOptionsState({ loading });
  return loading;
}

async function _historyLoadActiveProject() {
  if (typeof HISTORY_PROJECT_ACTIONS_GLOBAL.refreshActiveProjectContext === 'function') {
    try {
      const refreshed = await HISTORY_PROJECT_ACTIONS_GLOBAL.refreshActiveProjectContext();
      if (refreshed && refreshed.id) return refreshed;
    } catch (err) {
      _historyProjectLogEvent('history project active refresh failed', err, {
        event: 'HISTORY_PROJECT_ACTIVE_REFRESH_FAILED',
        level: 'warning',
        operation: 'refresh-active-project-context',
      });
    }
  }
  try {
    const resp = await _historyProjectApiFetch('/projects/active', { cache: 'no-store' });
    if (!resp.ok) {
      _historyProjectLogEvent('history project active refresh failed', new Error(`HTTP ${resp.status}`), {
        event: 'HISTORY_PROJECT_ACTIVE_REFRESH_FAILED',
        level: 'warning',
        operation: 'load-active-project',
        http_status: resp.status,
      });
      return null;
    }
    const data = await resp.json();
    return data && data.project && data.project.id ? data.project : null;
  } catch (err) {
    _historyProjectLogEvent('history project active refresh failed', err, {
      event: 'HISTORY_PROJECT_ACTIVE_REFRESH_FAILED',
      level: 'warning',
      operation: 'load-active-project',
    });
    return null;
  }
}

async function _historyLoadProjects() {
  const resp = await _historyProjectApiFetch('/projects', { cache: 'no-store' });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  return (Array.isArray(data.projects) ? data.projects : [])
    .filter(project => project && project.id && project.status !== 'archived')
    .sort((a, b) => _historyProjectDisplayName(a).localeCompare(_historyProjectDisplayName(b)));
}

async function _historyLoadProjectFilterOptions() {
  const resp = await _historyProjectApiFetch('/projects?include_archived=1', { cache: 'no-store' });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  return (Array.isArray(data.projects) ? data.projects : [])
    .filter(project => project && project.id && project.status !== 'archived')
    .sort((a, b) => _historyProjectDisplayName(a).localeCompare(_historyProjectDisplayName(b)));
}

function _historyOrderProjectsForPicker(projects, activeProject = null) {
  const activeId = activeProject && activeProject.id ? String(activeProject.id) : '';
  return (Array.isArray(projects) ? projects : []).slice().sort((a, b) => {
    const aIsActive = activeId && String(a?.id || '') === activeId;
    const bIsActive = activeId && String(b?.id || '') === activeId;
    if (aIsActive !== bIsActive) return aIsActive ? -1 : 1;
    return _historyProjectDisplayName(a).localeCompare(_historyProjectDisplayName(b));
  });
}

async function _historyLinkRunToProject(run, project, options = {}) {
  const includeEntities = !!options.includeEntities;
  if (!run || !run.id) throw new Error('Run is missing its identifier.');
  if (!project || !project.id) throw new Error('Project is missing its identifier.');
  const resp = await _historyProjectApiFetch(`/projects/${encodeURIComponent(project.id)}/links`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      entity_type: 'run',
      entity_id: run.id,
      source: 'manual',
      ...(includeEntities ? { include_entities: true } : {}),
    }),
  });
  if (!resp.ok) {
    let detail = '';
    try {
      const data = await resp.json();
      detail = data && data.error ? data.error : '';
    } catch (err) {
      _historyProjectLogEvent('history project link response parse failed', err, {
        event: 'HISTORY_PROJECT_LINK_FAILED',
        level: 'error',
        ..._historyProjectLogPayload('HISTORY_PROJECT_LINK_FAILED', 'error', run, project, {
          ...options,
          operation: 'link-run',
        }, { httpStatus: resp.status }),
      });
    }
    const err = new Error(detail || `HTTP ${resp.status}`);
    _historyProjectLogEvent('history project link failed', err, _historyProjectLogPayload(
      'HISTORY_PROJECT_LINK_FAILED',
      'error',
      run,
      project,
      { ...options, operation: 'link-run' },
      { httpStatus: resp.status },
    ));
    throw err;
  }
  let link = null;
  let entityStats = null;
  try {
    const data = await resp.json();
    link = data && data.link ? data.link : null;
    entityStats = data && data.linked_entities ? data.linked_entities : null;
  } catch (_) {}
  if (link) {
    run.project_links = (Array.isArray(run.project_links) ? run.project_links : [])
      .filter(item => String(item && item.project_id || '') !== String(project.id || ''));
    run.project_links.push({ ...link, project });
    run.project_link_count = run.project_links.length;
  }
  try {
    await _historyProjectRefreshProjectWorkspace();
  } catch (err) {
    _historyProjectLogEvent('history project refresh after link failed', err, _historyProjectLogPayload(
      'HISTORY_PROJECT_REFRESH_AFTER_LINK_FAILED',
      'warning',
      run,
      project,
      { ...options, operation: 'refresh-project-workspace-after-link' },
    ));
  }
  const name = _historyProjectDisplayName(project) || 'project';
  const addedEntities = includeEntities ? Number(entityStats && entityStats.added || 0) : 0;
  _historyProjectShowToast(addedEntities
    ? `Run and ${addedEntities.toLocaleString()} ${addedEntities === 1 ? 'entity' : 'entities'} added to ${name}`
    : `Run added to ${name}`);
  try {
    await _historyProjectRefreshHistoryPanel();
  } catch (err) {
    _historyProjectLogEvent('history project refresh after link failed', err, _historyProjectLogPayload(
      'HISTORY_PROJECT_REFRESH_AFTER_LINK_FAILED',
      'warning',
      run,
      project,
      { ...options, operation: 'refresh-history-panel-after-link' },
    ));
  }
}

async function _historyLoadProjectRunEntityPreview(project, runIds) {
  const projectId = String(project && project.id || '').trim();
  const ids = (Array.isArray(runIds) ? runIds : [runIds])
    .map(runId => String(runId || '').trim())
    .filter(Boolean);
  if (!projectId || !ids.length) return null;
  const resp = await _historyProjectApiFetch(`/projects/${encodeURIComponent(projectId)}/links/run-entities/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ run_ids: ids }),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  return data && data.preview ? data.preview : null;
}

async function _historyLoadProjectRunEntityRemovePreview(project, runIds) {
  const projectId = String(project && project.id || '').trim();
  const ids = (Array.isArray(runIds) ? runIds : [runIds])
    .map(runId => String(runId || '').trim())
    .filter(Boolean);
  if (!projectId || !ids.length) return null;
  const resp = await _historyProjectApiFetch(`/projects/${encodeURIComponent(projectId)}/links/run-entities/remove-preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ run_ids: ids }),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  return data && data.preview ? data.preview : null;
}

function _historyProjectRunEntityOptionLabel(count, runCount) {
  const entityLabel = count === 1 ? 'entity' : 'entities';
  if (runCount > 1) return `Also add ${count.toLocaleString()} Atlas ${entityLabel} found in these runs`;
  return `Also add ${count.toLocaleString()} Atlas ${entityLabel} found in this run`;
}

function _historyProjectRunEntityOptionContent({
  kind = 'add',
  labelForCount = _historyProjectRunEntityOptionLabel,
} = {}) {
  const wrap = document.createElement('div');
  wrap.className = 'history-project-run-entities-option u-hidden';
  wrap.dataset.historyProjectRunEntitiesOption = kind;
  const label = document.createElement('label');
  label.className = 'form-check';
  const checkbox = document.createElement('input');
  checkbox.type = 'checkbox';
  checkbox.checked = false;
  checkbox.dataset.historyProjectRunEntitiesScope = kind === 'remove' ? 'disposable' : 'all';
  const text = document.createElement('span');
  label.append(checkbox, text);
  wrap.append(label);
  const note = document.createElement('div');
  note.className = 'cleanup-reason-note history-project-run-entities-note u-hidden';
  wrap.appendChild(note);
  const curatedLabel = document.createElement('label');
  curatedLabel.className = 'form-check u-hidden';
  const curatedCheckbox = document.createElement('input');
  curatedCheckbox.type = 'checkbox';
  curatedCheckbox.checked = false;
  curatedCheckbox.dataset.historyProjectRunEntitiesScope = 'curated';
  const curatedText = document.createElement('span');
  curatedLabel.append(curatedCheckbox, curatedText);
  const curatedNote = document.createElement('div');
  curatedNote.className = 'cleanup-reason-note history-project-run-entities-note u-hidden';
  if (kind === 'remove') {
    wrap.append(curatedLabel, curatedNote);
  }
  const runFindingsNote = document.createElement('div');
  runFindingsNote.className = 'cleanup-reason-note history-project-run-entities-note u-hidden';
  if (kind === 'remove') {
    wrap.prepend(runFindingsNote);
  }
  const notEligibleNote = document.createElement('div');
  notEligibleNote.className = 'cleanup-reason-note history-project-run-entities-note u-hidden';
  if (kind === 'remove') {
    wrap.appendChild(notEligibleNote);
  }
  const sampleDetails = document.createElement('div');
  sampleDetails.className = 'cleanup-sample-slot u-hidden';
  if (kind === 'remove') {
    wrap.appendChild(sampleDetails);
  }
  return {
    wrap,
    label,
    checkbox,
    text,
    note,
    curatedLabel,
    curatedCheckbox,
    curatedText,
    curatedNote,
    runFindingsNote,
    notEligibleNote,
    sampleDetails,
    bindDisclosure: importedBindDisclosure,
    setNodeHidden: setCleanupNodeHidden,
    includeEntities() {
      return !!checkbox.checked && !checkbox.disabled;
    },
    includeCuratedEntities() {
      return !!curatedCheckbox.checked && !curatedCheckbox.disabled;
    },
    includeAnyEntities() {
      return this.includeEntities() || this.includeCuratedEntities();
    },
    setPreview(preview) {
      const runCount = Number(preview && preview.run_count || 0);
      if (kind === 'remove') {
        applyProjectRunEntityUnlinkPreview(this, preview);
        return;
      }
      const count = Number(preview && preview.linkable || 0);
      const keptCurated = Number(preview && preview.kept_curated || 0);
      checkbox.checked = false;
      checkbox.disabled = count <= 0;
      setCleanupNodeHidden(wrap, count <= 0);
      text.textContent = count > 0 ? labelForCount(count, runCount) : '';
      setCleanupNodeHidden(note, count <= 0 || keptCurated <= 0);
      note.textContent = keptCurated > 0
        ? `${keptCurated.toLocaleString()} curated ${keptCurated === 1 ? 'entity will' : 'entities will'} stay linked.`
        : '';
    },
  };
}

async function _historyRefreshProjectRunEntityOption(control, project, runIds) {
  if (!control) return null;
  try {
    const preview = await _historyLoadProjectRunEntityPreview(project, runIds);
    control.setPreview(preview);
    return preview;
  } catch (_) {
    control.setPreview(null);
    return null;
  }
}

async function _historyRefreshProjectRunEntityRemoveOption(control, project, runIds) {
  if (!control) return null;
  try {
    const preview = await _historyLoadProjectRunEntityRemovePreview(project, runIds);
    control.setPreview(preview);
    return preview;
  } catch (_) {
    control.setPreview(null);
    return null;
  }
}

async function _historyConfirmAddRunToProject(run, project) {
  const option = _historyProjectRunEntityOptionContent();
  await _historyRefreshProjectRunEntityOption(option, project, [run && run.id]);
  const content = option.wrap.classList.contains('u-hidden') ? null : option.wrap;
  const choice = await _historyProjectShowConfirm({
    body: `Add this run to ${_historyProjectDisplayName(project) || 'this project'}?`,
    content,
    tone: null,
    actions: [
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      { id: 'add', label: 'Add to project', role: 'primary' },
    ],
    refocusOnResolve: false,
  });
  if (choice !== 'add') return false;
  return { includeEntities: !!option.checkbox.checked && !option.checkbox.disabled };
}

function _historyProjectRunEntityRemoveOptionLabel(count, runCount) {
  const entityLabel = count === 1 ? 'entity' : 'entities';
  if (runCount > 1) return `Also remove ${count.toLocaleString()} Atlas ${entityLabel} found only in these runs from this project`;
  return `Also remove ${count.toLocaleString()} Atlas ${entityLabel} found only in this run from this project`;
}

function _historyProjectFromLink(link) {
  if (!link || typeof link !== 'object') return null;
  if (link.project && typeof link.project === 'object') return link.project;
  const projectId = String(link.project_id || '').trim();
  if (!projectId) return null;
  return {
    id: projectId,
    name: link.project_name || '',
    slug: link.project_slug || '',
    status: link.project_status || '',
  };
}

function _historyRunProjectLinks(run) {
  const links = Array.isArray(run?.project_links) ? run.project_links.slice() : [];
  try {
    const state = typeof importedGetHistoryRunModalState === 'function'
      ? importedGetHistoryRunModalState()
      : null;
    const projectState = state && state.projectState;
    const project = projectState && projectState.project;
    const runId = String(run && run.id || '');
    const modalRunId = String((state && (state.details || state.run) || {}).id || '');
    const hasActiveLink = !!(project && project.id)
      && projectState.attached
      && runId
      && (!modalRunId || modalRunId === runId)
      && !links.some(item => String(item && item.project_id || '') === String(project.id || ''));
    if (hasActiveLink) {
      links.push({
        project_id: project.id,
        entity_type: 'run',
        entity_id: runId,
        project,
      });
    }
  } catch (_) {}
  return links
    .map((link) => ({ link, project: _historyProjectFromLink(link) }))
    .filter((item) => item.project && item.project.id)
    .sort((a, b) => _historyProjectDisplayName(a.project).localeCompare(
      _historyProjectDisplayName(b.project),
      undefined,
      { sensitivity: 'base', numeric: true },
    ));
}

async function _historyUnlinkRunFromProject(run, project, options = {}) {
  const includeEntities = !!options.includeEntities;
  const includeCuratedEntities = !!options.includeCuratedEntities;
  if (!run || !run.id) throw new Error('Run is missing its identifier.');
  if (!project || !project.id) throw new Error('Project is missing its identifier.');
  const resp = await _historyProjectApiFetch(`/projects/${encodeURIComponent(project.id)}/links`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      entity_type: 'run',
      entity_id: run.id,
      ...(includeEntities ? { include_entities: true } : {}),
      ...(includeCuratedEntities ? { include_curated_entities: true } : {}),
    }),
  });
  if (!resp.ok) {
    let detail = '';
    try {
      const data = await resp.json();
      detail = data && data.error ? data.error : '';
    } catch (err) {
      _historyProjectLogEvent('history project unlink response parse failed', err, _historyProjectLogPayload(
        'HISTORY_PROJECT_UNLINK_FAILED',
        'error',
        run,
        project,
        { ...options, operation: 'unlink-run' },
        { httpStatus: resp.status },
      ));
    }
    const err = new Error(detail || `HTTP ${resp.status}`);
    _historyProjectLogEvent('history project unlink failed', err, _historyProjectLogPayload(
      'HISTORY_PROJECT_UNLINK_FAILED',
      'error',
      run,
      project,
      { ...options, operation: 'unlink-run' },
      { httpStatus: resp.status },
    ));
    throw err;
  }
  let entityStats = null;
  try {
    const data = await resp.json();
    entityStats = data && data.unlinked_entities ? data.unlinked_entities : null;
  } catch (_) {}
  try {
    await _historyProjectRefreshProjectWorkspace();
  } catch (err) {
    _historyProjectLogEvent('history project refresh after unlink failed', err, _historyProjectLogPayload(
      'HISTORY_PROJECT_REFRESH_AFTER_LINK_FAILED',
      'warning',
      run,
      project,
      { ...options, operation: 'refresh-project-workspace-after-unlink' },
    ));
  }
  if (Array.isArray(run.project_links)) {
    run.project_links = run.project_links.filter(item => String(item && item.project_id || '') !== String(project.id || ''));
    run.project_link_count = run.project_links.length;
  }
  const name = _historyProjectDisplayName(project) || 'project';
  const removedEntities = includeEntities ? Number(entityStats && entityStats.removed || 0) : 0;
  _historyProjectShowToast(removedEntities
    ? `Run and ${removedEntities.toLocaleString()} ${removedEntities === 1 ? 'entity' : 'entities'} removed from ${name}`
    : `Run removed from ${name}`);
  try {
    await _historyProjectRefreshHistoryPanel();
  } catch (err) {
    _historyProjectLogEvent('history project refresh after unlink failed', err, _historyProjectLogPayload(
      'HISTORY_PROJECT_REFRESH_AFTER_LINK_FAILED',
      'warning',
      run,
      project,
      { ...options, operation: 'refresh-history-panel-after-unlink' },
    ));
  }
}

async function _historyAddRunToActiveProject(run) {
  const project = await _historyLoadActiveProject();
  if (!project || !project.id) {
    _historyProjectShowToast('No active project selected', 'error');
    return;
  }
  const confirmed = await _historyConfirmAddRunToProject(run, project);
  if (!confirmed) return;
  await _historyLinkRunToProject(run, project, confirmed);
}

function _historyProjectPickerContentForLinks(links) {
  const projects = links.map(item => item.project).filter(Boolean);
  const { wrap, select } = _historyProjectPickerContent(projects);
  const help = wrap.querySelector('.history-project-picker-help');
  if (help) help.textContent = 'Choose the project link to remove.';
  return { wrap, select, projects };
}

async function _historyRemoveRunFromProject(run) {
  const links = _historyRunProjectLinks(run);
  if (!links.length) {
    _historyProjectShowToast('This run is not linked to a project', 'error');
    return;
  }
  let project = links[0].project;
  let content = null;
  let defaultFocus = null;
  const removeOption = _historyProjectRunEntityOptionContent({
    kind: 'remove',
    labelForCount: _historyProjectRunEntityRemoveOptionLabel,
  });
  if (links.length > 1) {
    const { wrap, select, projects } = _historyProjectPickerContentForLinks(links);
    content = wrap;
    defaultFocus = select;
    wrap.appendChild(removeOption.wrap);
    await _historyRefreshProjectRunEntityRemoveOption(removeOption, project, [run && run.id]);
    select.addEventListener('change', () => {
      const selectedProject = projects.find(item => String(item.id || '') === select.value);
      _historyRefreshProjectRunEntityRemoveOption(removeOption, selectedProject, [run && run.id]);
    });
    if (_historyProjectEnhanceAppSelects(wrap)) {
      if (_historyProjectUseMobileTerminalViewportMode()) {
        wrap.querySelector('.app-select-menu')?.classList.add('dropdown-up');
      }
    }
    project = () => projects.find(item => String(item.id || '') === select.value);
  } else {
    await _historyRefreshProjectRunEntityRemoveOption(removeOption, project, [run && run.id]);
    if (!removeOption.wrap.classList.contains('u-hidden')) {
      content = removeOption.wrap;
    }
  }
  const choice = await _historyProjectShowConfirm({
    body: links.length > 1
      ? 'Remove this run from a project'
      : `Remove this run from ${_historyProjectDisplayName(project) || 'this project'}?`,
    content,
    tone: 'warning',
    defaultFocus,
    actions: [
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      { id: 'remove', label: 'Remove from project', role: 'destructive', tone: 'warning' },
    ],
    refocusOnResolve: false,
  });
  if (choice !== 'remove') return;
  if (typeof project === 'function') project = project();
  try {
    await _historyUnlinkRunFromProject(run, project, {
      includeEntities: removeOption.includeAnyEntities(),
      includeCuratedEntities: removeOption.includeCuratedEntities(),
    });
  } catch (err) {
    _historyProjectLogEvent('history project unlink failed', err, _historyProjectLogPayload(
      'HISTORY_PROJECT_UNLINK_FAILED',
      'error',
      run,
      project,
      {
        includeEntities: removeOption.includeAnyEntities(),
        includeCuratedEntities: removeOption.includeCuratedEntities(),
        operation: 'remove-run-from-project',
      },
    ));
    _historyProjectShowToast('Failed to remove run from project', 'error');
  }
}

function _historyProjectPickerContent(projects) {
  const wrap = document.createElement('div');
  wrap.className = 'history-project-picker';
  const select = document.createElement('select');
  select.className = 'form-select form-control-compact';
  select.setAttribute('aria-label', 'Project');
  projects.forEach((project) => {
    const option = document.createElement('option');
    option.value = String(project.id || '');
    option.textContent = _historyProjectDisplayName(project) || String(project.id || '');
    select.appendChild(option);
  });
  wrap.appendChild(select);
  const help = document.createElement('div');
  help.className = 'history-project-picker-help';
  help.textContent = 'Choose a project to link this run.';
  wrap.appendChild(help);
  return { wrap, select };
}

async function _historyAddRunToProject(run) {
  let projects;
  try {
    const [loadedProjects, activeProject] = await Promise.all([
      _historyLoadProjects(),
      _historyLoadActiveProject().catch(() => null),
    ]);
    projects = _historyOrderProjectsForPicker(loadedProjects, activeProject);
  } catch (_) {
    _historyProjectShowToast('Failed to load projects', 'error');
    return;
  }
  if (!projects.length) {
    _historyProjectShowToast('No projects available', 'error');
    return;
  }
  const { wrap, select } = _historyProjectPickerContent(projects);
  const entityOption = _historyProjectRunEntityOptionContent();
  wrap.appendChild(entityOption.wrap);
  const selectedRunIds = [run && run.id];
  const updateEntityOption = () => {
    const selectedProject = projects.find(item => String(item.id || '') === select.value);
    _historyRefreshProjectRunEntityOption(entityOption, selectedProject, selectedRunIds);
  };
  select.addEventListener('change', updateEntityOption);
  updateEntityOption();
  const choicePromise = _historyProjectShowConfirm({
    body: 'Add this run to a project',
    content: wrap,
    tone: null,
    defaultFocus: select,
    actions: [
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      { id: 'add', label: 'Add to project', role: 'primary' },
    ],
    refocusOnResolve: false,
  });
  if (_historyProjectEnhanceAppSelects(wrap)) {
    if (_historyProjectUseMobileTerminalViewportMode()) {
      wrap.querySelector('.app-select-menu')?.classList.add('dropdown-up');
    }
  }
  const choice = await choicePromise;
  if (choice !== 'add') return;
  const project = projects.find(item => String(item.id || '') === select.value);
  try {
    await _historyLinkRunToProject(run, project, {
      includeEntities: !!entityOption.checkbox.checked && !entityOption.checkbox.disabled,
    });
  } catch (err) {
    _historyProjectLogEvent('history project link failed', err, _historyProjectLogPayload(
      'HISTORY_PROJECT_LINK_FAILED',
      'error',
      run,
      project,
      {
        includeEntities: !!entityOption.checkbox.checked && !entityOption.checkbox.disabled,
        operation: 'add-run-to-project',
      },
    ));
    _historyProjectShowToast('Failed to add run to project', 'error');
  }
}

if (typeof window !== 'undefined') {
}

export {
  _ensureHistoryProjectFilterOptions,
  _historyAddRunToActiveProject,
  _historyAddRunToProject,
  _historyConfirmAddRunToProject,
  _historyLinkRunToProject,
  _historyLoadActiveProject,
  _historyLoadProjects,
  _historyOrderProjectsForPicker,
  _historyProjectDisplayName,
  _historyProjectFromLink,
  _historyProjectLabelForId,
  _historyProjectPickerContent,
  _historyProjectRunEntityOptionContent,
  _historyRefreshProjectRunEntityOption,
  _historyRefreshProjectRunEntityRemoveOption,
  _historyRemoveRunFromProject,
  _historyRunProjectLinks,
  _historyUnlinkRunFromProject,
  _syncHistoryProjectFilterOptions,
};
