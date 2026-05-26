// Project-linking helpers for History rows and Run Details actions.
function _historyProjectDisplayName(project) {
  if (!project || typeof project !== 'object') return '';
  return String(project.name || project.slug || project.id || '').trim();
}

function _historyProjectLabelForId(projectId) {
  const normalized = _normalizeHistoryFilterValue(projectId);
  if (!normalized || normalized === 'all') return '';
  const project = _historyProjectOptions.find(item => String(item && item.id || '') === normalized);
  return _historyProjectDisplayName(project) || normalized;
}

function _syncHistoryProjectFilterOptions() {
  if (typeof historyProjectFilter === 'undefined' || !historyProjectFilter) return;
  const selected = _normalizeHistoryFilterValue(_historyFilters.projectId) || 'all';
  historyProjectFilter.replaceChildren();
  const allOption = document.createElement('option');
  allOption.value = 'all';
  allOption.textContent = 'project: all';
  historyProjectFilter.appendChild(allOption);
  _historyProjectOptions.forEach((project) => {
    const projectId = String(project && project.id || '');
    if (!projectId) return;
    const option = document.createElement('option');
    option.value = projectId;
    option.textContent = `project: ${_historyProjectDisplayName(project) || projectId}`;
    historyProjectFilter.appendChild(option);
  });
  if (selected !== 'all' && !_historyProjectOptions.some(project => String(project && project.id || '') === selected)) {
    const stale = document.createElement('option');
    stale.value = selected;
    stale.textContent = `project: ${selected}`;
    historyProjectFilter.appendChild(stale);
  }
  historyProjectFilter.value = selected;
  if (typeof syncAppSelect === 'function') syncAppSelect(historyProjectFilter);
}

function _ensureHistoryProjectFilterOptions() {
  if (_historyProjectOptionsLoaded) return Promise.resolve(_historyProjectOptions);
  if (_historyProjectOptionsLoading) return _historyProjectOptionsLoading;
  _historyProjectOptionsLoading = apiFetch('/projects?include_archived=1', { cache: 'no-store' })
    .then((resp) => {
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return resp.json();
    })
    .then((data) => {
      _historyProjectOptions = (Array.isArray(data.projects) ? data.projects : [])
        .filter(project => project && project.id)
        .sort((a, b) => _historyProjectDisplayName(a).localeCompare(
          _historyProjectDisplayName(b),
          undefined,
          { sensitivity: 'base', numeric: true },
        ));
      _historyProjectOptionsLoaded = true;
      _syncHistoryProjectFilterOptions();
      return _historyProjectOptions;
    })
    .catch((err) => {
      if (typeof logClientError === 'function') logClientError('failed to load /projects for history filter', err);
      return _historyProjectOptions;
    })
    .finally(() => {
      _historyProjectOptionsLoading = null;
    });
  return _historyProjectOptionsLoading;
}

async function _historyLoadActiveProject() {
  if (typeof getActiveProjectContext === 'function') {
    const current = getActiveProjectContext();
    if (current && current.id) return current;
  }
  if (typeof refreshActiveProjectContext === 'function') {
    try {
      const refreshed = await refreshActiveProjectContext();
      if (refreshed && refreshed.id) return refreshed;
    } catch (_) {}
  }
  try {
    const resp = await apiFetch('/projects/active', { cache: 'no-store' });
    if (!resp.ok) return null;
    const data = await resp.json();
    return data && data.project && data.project.id ? data.project : null;
  } catch (_) {
    return null;
  }
}

async function _historyLoadProjects() {
  const resp = await apiFetch('/projects', { cache: 'no-store' });
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
  const resp = await apiFetch(`/projects/${encodeURIComponent(project.id)}/links`, {
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
    } catch (_) {}
    throw new Error(detail || `HTTP ${resp.status}`);
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
  if (typeof refreshProjectWorkspace === 'function') {
    try { await refreshProjectWorkspace(); } catch (_) {}
  }
  const name = _historyProjectDisplayName(project) || 'project';
  const addedEntities = includeEntities ? Number(entityStats && entityStats.added || 0) : 0;
  showToast(addedEntities
    ? `Run and ${addedEntities.toLocaleString()} ${addedEntities === 1 ? 'entity' : 'entities'} added to ${name}`
    : `Run added to ${name}`);
  if (typeof refreshHistoryPanel === 'function') {
    try { await refreshHistoryPanel(); } catch (_) {}
  }
}

async function _historyLoadProjectRunEntityPreview(project, runIds) {
  const projectId = String(project && project.id || '').trim();
  const ids = (Array.isArray(runIds) ? runIds : [runIds])
    .map(runId => String(runId || '').trim())
    .filter(Boolean);
  if (!projectId || !ids.length) return null;
  const resp = await apiFetch(`/projects/${encodeURIComponent(projectId)}/links/run-entities/preview`, {
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
  const resp = await apiFetch(`/projects/${encodeURIComponent(projectId)}/links/run-entities/remove-preview`, {
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
  note.className = 'history-project-run-entities-note u-hidden';
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
  curatedNote.className = 'history-project-run-entities-note u-hidden';
  if (kind === 'remove') {
    wrap.append(curatedLabel, curatedNote);
  }
  const runFindingsNote = document.createElement('div');
  runFindingsNote.className = 'history-project-run-entities-note u-hidden';
  if (kind === 'remove') {
    wrap.prepend(runFindingsNote);
  }
  return {
    wrap,
    checkbox,
    text,
    note,
    curatedCheckbox,
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
        const removable = Number(preview && preview.removable || 0);
        const curated = Number(preview && (preview.curated ?? preview.kept_curated) || 0);
        const runFindings = Number(preview && preview.run_findings || 0);
        const removableFindings = Number(preview && preview.removable_findings || 0);
        const curatedFindings = Number(preview && (preview.curated_findings ?? preview.kept_curated_findings) || 0);
        const entityLabel = removable === 1 ? 'entity' : 'entities';
        const curatedEntityLabel = curated === 1 ? 'entity' : 'entities';
        const runFindingLabel = runFindings === 1 ? 'finding' : 'findings';
        const removableFindingLabel = removableFindings === 1 ? 'finding' : 'findings';
        const curatedFindingLabel = curatedFindings === 1 ? 'finding' : 'findings';
        checkbox.checked = false;
        checkbox.disabled = removable <= 0;
        curatedCheckbox.checked = false;
        curatedCheckbox.disabled = curated <= 0;
        wrap.classList.toggle('u-hidden', removable <= 0 && curated <= 0 && runFindings <= 0);
        runFindingsNote.classList.toggle('u-hidden', runFindings <= 0);
        runFindingsNote.textContent = runFindings > 0
          ? `Removing the run link will remove ${runFindings.toLocaleString()} ${runFindingLabel} from this project's Findings tab.`
          : '';
        label.classList.toggle('u-hidden', removable <= 0);
        curatedLabel.classList.toggle('u-hidden', curated <= 0);
        text.textContent = removable > 0
          ? 'Also remove disposable same-run Atlas entities from this project'
          : '';
        note.classList.toggle('u-hidden', removable <= 0);
        note.textContent = removable > 0
          ? [
            `This will unlink ${removable.toLocaleString()} ${entityLabel} found only in ${runCount > 1 ? 'these runs' : 'this run'}.`,
            removableFindings > 0
              ? `${removableFindings.toLocaleString()} related ${removableFindingLabel} will no longer appear in this project.`
              : '',
          ].filter(Boolean).join(' ')
          : '';
        curatedText.textContent = curated > 0
          ? 'Also remove curated same-run Atlas entities from this project'
          : '';
        curatedNote.classList.toggle('u-hidden', curated <= 0);
        curatedNote.textContent = curated > 0
          ? [
            `${curated.toLocaleString()} curated ${curatedEntityLabel}`,
            curatedFindings > 0 ? `and ${curatedFindings.toLocaleString()} related ${curatedFindingLabel}` : '',
            `will stay in this project unless this is checked. Curated means project-linked elsewhere, labeled, noted, reviewed, or carrying project target metadata.`,
          ].filter(Boolean).join(' ')
          : '';
        return;
      }
      const count = Number(preview && preview.linkable || 0);
      const keptCurated = Number(preview && preview.kept_curated || 0);
      checkbox.checked = false;
      checkbox.disabled = count <= 0;
      wrap.classList.toggle('u-hidden', count <= 0);
      text.textContent = count > 0 ? labelForCount(count, runCount) : '';
      note.classList.toggle('u-hidden', count <= 0 || keptCurated <= 0);
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
  const choice = await showConfirm({
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
    const state = typeof _historyRunModalState !== 'undefined' ? _historyRunModalState : null;
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
  const resp = await apiFetch(`/projects/${encodeURIComponent(project.id)}/links`, {
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
    } catch (_) {}
    throw new Error(detail || `HTTP ${resp.status}`);
  }
  let entityStats = null;
  try {
    const data = await resp.json();
    entityStats = data && data.unlinked_entities ? data.unlinked_entities : null;
  } catch (_) {}
  if (typeof refreshProjectWorkspace === 'function') {
    try { await refreshProjectWorkspace(); } catch (_) {}
  }
  if (Array.isArray(run.project_links)) {
    run.project_links = run.project_links.filter(item => String(item && item.project_id || '') !== String(project.id || ''));
    run.project_link_count = run.project_links.length;
  }
  const name = _historyProjectDisplayName(project) || 'project';
  const removedEntities = includeEntities ? Number(entityStats && entityStats.removed || 0) : 0;
  showToast(removedEntities
    ? `Run and ${removedEntities.toLocaleString()} ${removedEntities === 1 ? 'entity' : 'entities'} removed from ${name}`
    : `Run removed from ${name}`);
  if (typeof refreshHistoryPanel === 'function') {
    try { await refreshHistoryPanel(); } catch (_) {}
  }
}

async function _historyAddRunToActiveProject(run) {
  const project = await _historyLoadActiveProject();
  if (!project || !project.id) {
    showToast('No active project selected', 'error');
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
    showToast('This run is not linked to a project', 'error');
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
    if (typeof enhanceAppSelects === 'function') {
      enhanceAppSelects(wrap);
      if (typeof useMobileTerminalViewportMode === 'function' && useMobileTerminalViewportMode()) {
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
  const choice = await showConfirm({
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
  } catch (_) {
    showToast('Failed to remove run from project', 'error');
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
    showToast('Failed to load projects', 'error');
    return;
  }
  if (!projects.length) {
    showToast('No projects available', 'error');
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
  const choicePromise = showConfirm({
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
  if (typeof enhanceAppSelects === 'function') {
    enhanceAppSelects(wrap);
    if (typeof useMobileTerminalViewportMode === 'function' && useMobileTerminalViewportMode()) {
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
  } catch (_) {
    showToast('Failed to add run to project', 'error');
  }
}
