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

async function _historyLinkRunToProject(run, project) {
  if (!run || !run.id) throw new Error('Run is missing its identifier.');
  if (!project || !project.id) throw new Error('Project is missing its identifier.');
  const resp = await apiFetch(`/projects/${encodeURIComponent(project.id)}/links`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ entity_type: 'run', entity_id: run.id, source: 'manual' }),
  });
  if (!resp.ok) {
    let detail = '';
    try {
      const data = await resp.json();
      detail = data && data.error ? data.error : '';
    } catch (_) {}
    throw new Error(detail || `HTTP ${resp.status}`);
  }
  if (typeof refreshProjectWorkspace === 'function') {
    try { await refreshProjectWorkspace(); } catch (_) {}
  }
  const name = _historyProjectDisplayName(project) || 'project';
  showToast(`Run added to ${name}`);
}

async function _historyAddRunToActiveProject(run) {
  const project = await _historyLoadActiveProject();
  if (!project || !project.id) {
    showToast('No active project selected', 'error');
    return;
  }
  await _historyLinkRunToProject(run, project);
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
  const choicePromise = showConfirm({
    body: 'Add this run to a project',
    content: wrap,
    tone: null,
    defaultFocus: select,
    actions: [
      { id: 'cancel', label: 'Cancel', role: 'cancel' },
      { id: 'add', label: 'Add to project', role: 'primary' },
    ],
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
    await _historyLinkRunToProject(run, project);
  } catch (_) {
    showToast('Failed to add run to project', 'error');
  }
}
