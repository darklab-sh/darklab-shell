// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Project Details tab controller.
// Loaded before shell_chrome.js; shell chrome supplies the surrounding Projects state.

let exportedDarklabProjectDetails = null;

(function projectDetailsModule(global) {
  'use strict';

  function createProjectDetailsController(context) {
    const ctx = context || {};
    let notesSaveTimer = null;
    let notesSaveSeq = 0;
    const targetPageState = new Map();
    const targetSearchTimers = new Map();
    const targetTypes = [
      { id: '', label: 'All' },
      { id: 'domain', label: 'Domains' },
      { id: 'ip', label: 'IPs' },
      { id: 'url', label: 'URLs' },
    ];

    function targetState(projectId) {
      const normalizedProjectId = String(projectId || '');
      if (!targetPageState.has(normalizedProjectId)) {
        targetPageState.set(normalizedProjectId, {
          type: '',
          query: '',
          autoDiscovered: false,
          limit: 50,
          offset: 0,
          page: null,
          countsByType: null,
          loading: false,
          error: '',
          seq: 0,
        });
      }
      return targetPageState.get(normalizedProjectId);
    }

    function labelChips(project) {
      return ctx.entityLabelValues(project).map(label => ({ label, kind: 'label' }));
    }

    function appendLabelChips(parent, project, { className = 'project-label-chips' } = {}) {
      const chips = labelChips(project);
      if (!parent || !chips.length) return;
      const wrap = document.createElement('div');
      wrap.className = className;
      for (const chip of chips) {
        const node = document.createElement('span');
        node.className = ctx.entityMetadataChipClass(chip.kind);
        node.textContent = chip.label;
        wrap.appendChild(node);
      }
      parent.appendChild(wrap);
    }

    function appendMobileLabelChips(parent, project) {
      const chips = labelChips(project);
      if (!parent || !chips.length) return;
      const wrap = document.createElement('span');
      wrap.className = 'project-mobile-label-chips';
      chips.slice(0, 3).forEach((chip) => {
        const node = document.createElement('span');
        node.className = ctx.entityMetadataChipClass(chip.kind);
        node.textContent = chip.label;
        wrap.appendChild(node);
      });
      if (chips.length > 3) {
        const overflow = document.createElement('span');
        overflow.className = ctx.entityMetadataChipClass('label');
        overflow.textContent = `+${chips.length - 3}`;
        wrap.appendChild(overflow);
      }
      parent.appendChild(wrap);
    }

    function syncForms(project = ctx.selectedProject()) {
      const hasProject = !!(project && project.id);
      const showingDetails = ctx.projectWorkspaceTab() === 'details';
      const nextProjectId = hasProject ? String(project.id || '') : '';
      if (ctx.projectNotesForm) ctx.projectNotesForm.classList.toggle('u-hidden', !hasProject || !showingDetails);
      if (ctx.projectLabelsForm) ctx.projectLabelsForm.classList.toggle('u-hidden', !hasProject || !showingDetails);
      if (ctx.projectLabelsInput && document.activeElement !== ctx.projectLabelsInput) {
        ctx.projectLabelsInput.value = hasProject ? ctx.entityLabelValues(project).join(', ') : '';
        ctx.projectLabelsInput.dataset.projectId = nextProjectId;
        ctx.projectLabelsInput.dataset.savedLabels = ctx.projectLabelsInput.value;
        ctx.projectLabelsInput.placeholder = hasProject
          ? `Labels for ${ctx.projectDisplayName(project)}`
          : 'Select a project to edit labels';
      }
      const notesProjectId = String(ctx.projectNotesInput?.dataset.projectId || '');
      const hasPendingNotesEdit = !!notesSaveTimer && notesProjectId === nextProjectId;
      if (ctx.projectNotesInput && document.activeElement !== ctx.projectNotesInput && !hasPendingNotesEdit) {
        ctx.projectNotesInput.value = hasProject ? ctx.entityNoteBody(project) : '';
        ctx.projectNotesInput.dataset.projectId = hasProject ? String(project.id || '') : '';
        ctx.projectNotesInput.dataset.savedNotes = ctx.projectNotesInput.value;
        ctx.projectNotesInput.placeholder = hasProject
          ? `Notes for ${ctx.projectDisplayName(project)}`
          : 'Select a project to edit notes';
      }
    }

    function syncNotesForm() {
      syncForms();
    }

    function hideNotesSavedIndicator() {
      return undefined;
    }

    function showNotesSavedIndicator() {
      ctx.setProjectWorkspaceMessage?.('Project notes saved.');
    }

    function hideLabelsSavedIndicator() {
      return undefined;
    }

    function showLabelsSavedIndicator(projectId) {
      const normalizedProjectId = String(projectId || '');
      if (normalizedProjectId && String(ctx.projectLabelsInput?.dataset.projectId || '') !== normalizedProjectId) return;
      ctx.setProjectWorkspaceMessage?.('Project labels saved.');
    }

    function cacheNotes(projectId, notes, updatedProject = null) {
      const normalizedProjectId = String(projectId || '');
      if (!normalizedProjectId) return;
      const replacement = updatedProject && typeof updatedProject === 'object'
        ? updatedProject
        : null;
      ctx.setProjectRows(ctx.projectRows().map(project => {
        if (String(project && project.id || '') !== normalizedProjectId) return project;
        return replacement || { ...project, notes };
      }));
      const activeProject = ctx.activeProject();
      if (activeProject && String(activeProject.id || '') === normalizedProjectId) {
        ctx.setActiveProject(replacement || { ...activeProject, notes });
      }
    }

    function cacheLabels(projectId, labels) {
      const normalizedProjectId = String(projectId || '');
      const labelItems = (Array.isArray(labels) ? labels : []).map(label => ({ label: String(label || '').trim() })).filter(item => item.label);
      if (!normalizedProjectId) return;
      const update = project => (
        String(project && project.id || '') === normalizedProjectId
          ? { ...project, labels: labelItems }
          : project
      );
      ctx.setProjectRows(ctx.projectRows().map(update));
      const summary = ctx.projectSummary(normalizedProjectId);
      if (summary && summary.project) {
        ctx.setProjectSummary(normalizedProjectId, {
          ...summary,
          project: update(summary.project),
        });
      }
      const activeProject = ctx.activeProject();
      if (activeProject && String(activeProject.id || '') === normalizedProjectId) {
        ctx.setActiveProject(update(activeProject));
      }
    }

    async function saveLabelsNow() {
      if (!ctx.projectLabelsInput) return;
      const projectId = String(ctx.projectLabelsInput.dataset.projectId || ctx.selectedProjectId() || '');
      if (!projectId) return;
      const labels = ctx.entityMetadataClient.parseLabelInput(ctx.projectLabelsInput.value);
      const labelText = labels.join(', ');
      if (labelText === String(ctx.projectLabelsInput.dataset.savedLabels || '')) return;
      if (ctx.projectLabelsSaveButton) ctx.projectLabelsSaveButton.disabled = true;
      ctx.projectLabelsInput.value = labelText;
      hideLabelsSavedIndicator();
      try {
        await ctx.syncEntityLabels('project', projectId, labels);
        ctx.projectLabelsInput.dataset.savedLabels = labelText;
        cacheLabels(projectId, labels);
        ctx.renderProjectList();
        ctx.renderProjectExplorer();
        showLabelsSavedIndicator(projectId);
      } catch (err) {
        ctx.setProjectWorkspaceMessage(err.message || 'Could not save project labels.', { error: true });
      } finally {
        if (ctx.projectLabelsSaveButton) ctx.projectLabelsSaveButton.disabled = false;
      }
    }

    async function saveNotesNow({ force = false } = {}) {
      if (!ctx.projectNotesInput) return;
      const projectId = String(ctx.projectNotesInput.dataset.projectId || ctx.selectedProjectId() || '');
      if (!projectId) return;
      const notes = String(ctx.projectNotesInput.value || '');
      if (!force && notes === String(ctx.projectNotesInput.dataset.savedNotes || '')) return;
      const seq = ++notesSaveSeq;
      try {
        const resp = await ctx.projectWorkspaceRequest(`/projects/${encodeURIComponent(projectId)}`, {
          method: 'PUT',
          body: JSON.stringify({ notes }),
        });
        const data = await resp.json();
        const updatedProject = data && data.project && typeof data.project === 'object' ? data.project : null;
        if (seq === notesSaveSeq) {
          ctx.projectNotesInput.dataset.savedNotes = notes;
          showNotesSavedIndicator();
        }
        cacheNotes(projectId, notes, updatedProject);
        ctx.renderActiveProject();
      } catch (err) {
        ctx.setProjectWorkspaceMessage(err.message || 'Could not save project notes.', { error: true });
      }
    }

    function scheduleNotesAutosave() {
      if (notesSaveTimer) {
        clearTimeout(notesSaveTimer);
        notesSaveTimer = null;
      }
      notesSaveTimer = setTimeout(() => {
        notesSaveTimer = null;
        saveNotesNow().catch(() => {});
      }, ctx.projectNotesAutosaveDelayMs);
    }

    function flushNotesAutosave() {
      if (notesSaveTimer) {
        clearTimeout(notesSaveTimer);
        notesSaveTimer = null;
      }
      return saveNotesNow();
    }

    function bindFormEvents() {
      ctx.projectNotesInput?.addEventListener('input', () => {
        hideNotesSavedIndicator();
        scheduleNotesAutosave();
      });
      ctx.projectNotesInput?.addEventListener('change', () => {
        flushNotesAutosave().catch(() => {});
      });
      ctx.projectNotesInput?.addEventListener('blur', () => {
        flushNotesAutosave().catch(() => {});
      });
      ctx.projectNotesForm?.addEventListener('submit', (event) => {
        event.preventDefault();
        flushNotesAutosave().catch(() => {});
      });
      ctx.projectLabelsInput?.addEventListener('input', () => {
        hideLabelsSavedIndicator();
      });
      ctx.projectLabelsInput?.addEventListener('change', () => {
        saveLabelsNow().catch(() => {});
      });
      ctx.projectLabelsForm?.addEventListener('submit', (event) => {
        event.preventDefault();
        saveLabelsNow().catch(() => {});
      });
      ctx.projectLabelsSaveButton?.addEventListener('click', (event) => {
        event.preventDefault();
        saveLabelsNow().catch(() => {});
      });
    }

    function targetPageUrl(projectId, state) {
      const params = new URLSearchParams();
      params.set('limit', String(state.limit || 50));
      params.set('offset', String(state.offset || 0));
      if (state.type) params.set('type', state.type);
      if (state.query) params.set('q', state.query);
      if (state.autoDiscovered) params.set('auto_discovered', '1');
      return `/projects/${encodeURIComponent(projectId)}/targets?${params.toString()}`;
    }

    function normalizeTargetCountsByType(counts) {
      if (!counts || typeof counts !== 'object') return null;
      return Object.fromEntries(
        Object.entries(counts)
          .map(([key, value]) => [String(key || ''), Math.max(0, Number(value || 0))])
          .filter(([key]) => !!key),
      );
    }

    function targetCountsByType(summary, state) {
      const pageCounts = normalizeTargetCountsByType(state.page?.counts_by_type);
      if (pageCounts) return pageCounts;
      if (state.countsByType) return state.countsByType;
      const summaryCounts = summary && summary.counts && typeof summary.counts === 'object' ? summary.counts : {};
      const total = Number(summaryCounts.targets || 0) + Number(summaryCounts.pending_targets || 0);
      return total > 0 ? { all: total } : {};
    }

    function targetPage(projectId) {
      const state = targetState(projectId);
      const page = state.page && typeof state.page === 'object' ? state.page : {};
      return {
        ...page,
        limit: Number(page.limit || state.limit || 50),
        offset: Number(page.offset || state.offset || 0),
        total: Number(page.total || 0),
        loading: !!state.loading,
        error: state.error || '',
      };
    }

    async function loadTargetPage(projectId, { offset = null, skipFinalRender = false } = {}) {
      const normalizedProjectId = String(projectId || '');
      if (!normalizedProjectId || typeof ctx.apiFetch !== 'function') return;
      const state = targetState(normalizedProjectId);
      if (offset !== null) state.offset = Math.max(0, Number(offset || 0));
      const seq = state.seq + 1;
      state.seq = seq;
      state.loading = true;
      state.error = '';
      try {
        const resp = await ctx.apiFetch(targetPageUrl(normalizedProjectId, state), { cache: 'no-store' });
        if (!resp || !resp.ok) {
          if (typeof ctx.projectResponseError === 'function') {
            throw await ctx.projectResponseError(resp, 'Could not load project targets.');
          }
          throw new Error('Could not load project targets.');
        }
        const data = await resp.json();
        if (state.seq !== seq) return;
        const nextOffset = Number(data && data.offset || state.offset || 0);
        const nextLimit = Math.max(1, Number(data && data.limit || state.limit || 50));
        const nextTotal = Math.max(0, Number(data && data.total || 0));
        if (nextTotal > 0 && nextOffset >= nextTotal) {
          state.loading = false;
          state.offset = Math.max(0, Math.floor((nextTotal - 1) / nextLimit) * nextLimit);
          return loadTargetPage(normalizedProjectId, { offset: state.offset, skipFinalRender });
        }
        state.page = data && typeof data === 'object' ? data : { targets: [] };
        state.countsByType = normalizeTargetCountsByType(state.page.counts_by_type) || state.countsByType;
        state.offset = Number(state.page.offset || 0);
      } catch (err) {
        if (state.seq !== seq) return;
        state.error = err.message || 'Could not load project targets.';
      } finally {
        if (state.seq === seq) {
          state.loading = false;
          if (!skipFinalRender) ctx.renderProjectExplorer?.();
        }
      }
    }

    function ensureTargetPage(projectId) {
      const state = targetState(projectId);
      if (state.page || state.loading || state.error) return;
      loadTargetPage(projectId).catch(() => {});
    }

    function seedTargetPageFromSummary(summary, state) {
      const existingEmptyPage = state.page
        && Array.isArray(state.page.targets)
        && state.page.targets.length === 0
        && Number(state.page.total || 0) === 0;
      if ((state.page && !existingEmptyPage) || state.loading || state.error || state.type || state.query || state.autoDiscovered) return;
      const targets = ctx.projectTargetItems(summary);
      const counts = summary && summary.counts && typeof summary.counts === 'object' ? summary.counts : {};
      const hasExplicitTargetCounts = Object.prototype.hasOwnProperty.call(counts, 'targets')
        || Object.prototype.hasOwnProperty.call(counts, 'pending_targets');
      const total = Number(counts.targets || 0) + Number(counts.pending_targets || 0);
      if (!targets.length && hasExplicitTargetCounts && total <= 0) {
        state.page = {
          targets: [],
          total: 0,
          limit: state.limit,
          offset: 0,
          has_more: false,
          counts_by_type: {},
        };
        state.countsByType = {};
        return;
      }
      if (!targets.length) return;
      if (total > targets.length) return;
      const countsByType = {};
      targets.forEach((target) => {
        const type = String(target && target.type || '');
        if (!type) return;
        countsByType[type] = Number(countsByType[type] || 0) + 1;
      });
      state.page = {
        targets,
        total: targets.length,
        limit: state.limit,
        offset: 0,
        has_more: false,
        counts_by_type: countsByType,
      };
      state.countsByType = countsByType;
    }

    function invalidateTargetPage(projectId = '') {
      const normalizedProjectId = String(projectId || ctx.selectedProjectId?.() || '');
      if (normalizedProjectId) {
        targetPageState.delete(normalizedProjectId);
        return;
      }
      targetPageState.clear();
    }

    function targetById(projectId, targetId) {
      const normalizedTargetId = String(targetId || '');
      if (!normalizedTargetId) return null;
      const state = targetPageState.get(String(projectId || ''));
      const pageTargets = state && state.page && Array.isArray(state.page.targets) ? state.page.targets : [];
      return pageTargets.find(item => String(item && item.id || '') === normalizedTargetId) || null;
    }

    function removeCachedTarget(projectId, targetId) {
      const normalizedProjectId = String(projectId || '');
      const normalizedTargetId = String(targetId || '');
      if (!normalizedProjectId || !normalizedTargetId) return;
      const state = targetPageState.get(normalizedProjectId);
      let removedTarget = null;
      if (state && state.page && Array.isArray(state.page.targets)) {
        state.page.targets = state.page.targets.filter((target) => {
          if (String(target && target.id || '') !== normalizedTargetId) return true;
          removedTarget = target;
          return false;
        });
        state.page.total = Math.max(0, Number(state.page.total || 0) - (removedTarget ? 1 : 0));
        const type = String(removedTarget && removedTarget.type || '');
        if (type && state.page.counts_by_type && typeof state.page.counts_by_type === 'object') {
          state.page.counts_by_type[type] = Math.max(0, Number(state.page.counts_by_type[type] || 0) - 1);
        }
        if (type && state.countsByType && typeof state.countsByType === 'object') {
          state.countsByType[type] = Math.max(0, Number(state.countsByType[type] || 0) - 1);
        }
      }
      const summary = ctx.projectSummary?.(normalizedProjectId);
      if (!summary || !Array.isArray(summary.targets)) return;
      const summaryTargets = summary.targets.filter((target) => {
        if (String(target && target.id || '') !== normalizedTargetId) return true;
        removedTarget = removedTarget || target;
        return false;
      });
      if (summaryTargets.length === summary.targets.length) return;
      const counts = summary.counts && typeof summary.counts === 'object' ? { ...summary.counts } : {};
      const countKey = String(removedTarget && removedTarget.review_state || '') === 'pending' ? 'pending_targets' : 'targets';
      counts[countKey] = Math.max(0, Number(counts[countKey] || 0) - 1);
      ctx.setProjectSummary?.(normalizedProjectId, { ...summary, targets: summaryTargets, counts });
    }

    function updateCachedTarget(projectId, targetId, updates = {}) {
      const normalizedProjectId = String(projectId || '');
      const normalizedTargetId = String(targetId || '');
      if (!normalizedProjectId || !normalizedTargetId || !updates || typeof updates !== 'object') return;
      const state = targetPageState.get(normalizedProjectId);
      let previous = null;
      let next = null;
      const applyUpdate = target => {
        if (String(target && target.id || '') !== normalizedTargetId) return target;
        previous = previous || target;
        next = { ...target, ...updates };
        return next;
      };
      if (state && state.page && Array.isArray(state.page.targets)) {
        state.page.targets = state.page.targets.map(applyUpdate);
      }
      const summary = ctx.projectSummary?.(normalizedProjectId);
      if (summary && Array.isArray(summary.targets)) {
        const summaryTargets = summary.targets.map(applyUpdate);
        const counts = summary.counts && typeof summary.counts === 'object' ? { ...summary.counts } : {};
        const previousState = String(previous && previous.review_state || '');
        const nextState = String((next || updates).review_state || previousState);
        if (previousState && nextState && previousState !== nextState) {
          const fromKey = previousState === 'pending' ? 'pending_targets' : 'targets';
          const toKey = nextState === 'pending' ? 'pending_targets' : 'targets';
          counts[fromKey] = Math.max(0, Number(counts[fromKey] || 0) - 1);
          counts[toKey] = Math.max(0, Number(counts[toKey] || 0) + 1);
        }
        ctx.setProjectSummary?.(normalizedProjectId, { ...summary, targets: summaryTargets, counts });
      }
    }

    function renderTargetTypeTabs(projectId, summary, state) {
      const counts = targetCountsByType(summary, state);
      const tabs = document.createElement('div');
      tabs.className = 'project-target-type-tabs tab-strip';
      tabs.setAttribute('role', 'tablist');
      tabs.setAttribute('aria-label', 'Project target types');
      targetTypes.forEach((item) => {
        const button = document.createElement('button');
        button.type = 'button';
        const active = String(state.type || '') === item.id;
        button.className = 'tab-strip-item project-target-type-tab' + (active ? ' is-active' : '');
        button.dataset.projectTargetType = item.id;
        button.setAttribute('role', 'tab');
        button.setAttribute('aria-selected', active ? 'true' : 'false');
        button.setAttribute('aria-pressed', active ? 'true' : 'false');
        const count = item.id ? Number(counts[item.id] || 0) : (
          Object.prototype.hasOwnProperty.call(counts, 'all')
            ? Number(counts.all || 0)
            : Object.values(counts).reduce((sum, value) => sum + Number(value || 0), 0)
        );
        const label = document.createElement('span');
        label.className = 'project-target-type-tab-label';
        label.textContent = item.label;
        const countEl = document.createElement('span');
        countEl.className = 'project-target-type-tab-count';
        countEl.textContent = String(count);
        button.append(label, countEl);
        button.addEventListener('click', () => {
          if (state.type === item.id) return;
          state.type = item.id;
          state.offset = 0;
          state.page = null;
          ctx.renderProjectExplorer?.();
          loadTargetPage(projectId).catch(() => {});
        });
        ctx.bindProjectRuntimePressable?.(button);
        tabs.appendChild(button);
      });
      return tabs;
    }

    function renderTargetToolbar(projectId, summary, state) {
      const toolbar = document.createElement('div');
      toolbar.className = 'project-target-browser-toolbar';
      toolbar.appendChild(renderTargetTypeTabs(projectId, summary, state));

      const search = document.createElement('input');
      search.className = 'form-control form-control-compact project-target-search';
      search.type = 'search';
      search.placeholder = 'Search targets';
      search.autocomplete = 'off';
      search.spellcheck = false;
      search.value = state.query || '';
      search.setAttribute('aria-label', 'Search project targets');
      search.addEventListener('input', () => {
        state.query = String(search.value || '').trim();
        state.offset = 0;
        state.page = null;
        const existing = targetSearchTimers.get(projectId);
        if (existing) clearTimeout(existing);
        targetSearchTimers.set(projectId, setTimeout(() => {
          targetSearchTimers.delete(projectId);
          loadTargetPage(projectId).catch(() => {});
        }, 250));
      });

      const autoLabel = document.createElement('label');
      autoLabel.className = 'project-target-auto-toggle control-row';
      const autoInput = document.createElement('input');
      autoInput.type = 'checkbox';
      autoInput.checked = !!state.autoDiscovered;
      autoInput.addEventListener('change', () => {
        state.autoDiscovered = !!autoInput.checked;
        state.offset = 0;
        state.page = null;
        ctx.renderProjectExplorer?.();
        loadTargetPage(projectId).catch(() => {});
      });
      const autoText = document.createElement('span');
      autoText.textContent = 'Auto-discovered';
      autoLabel.append(autoInput, autoText);

      const controls = document.createElement('div');
      controls.className = 'project-target-browser-controls';
      controls.append(search, autoLabel);
      toolbar.appendChild(controls);
      return toolbar;
    }

    function renderTargetPagination(projectId, state, position = 'bottom') {
      const page = state.page && typeof state.page === 'object' ? state.page : {};
      const total = Number(page.total || 0);
      const limit = Math.max(1, Number(page.limit || state.limit || 50));
      const offset = Math.max(0, Number(page.offset || state.offset || 0));
      const targets = Array.isArray(page.targets) ? page.targets : [];
      if (total <= limit) return null;
      const wrap = document.createElement('div');
      wrap.className = 'project-workspace-pagination project-target-pagination';
      wrap.dataset.projectTargetsPagerPosition = position;
      const start = total && targets.length ? offset + 1 : 0;
      const end = total && targets.length ? Math.min(total, offset + targets.length) : 0;
      const summary = document.createElement('div');
      summary.className = 'project-workspace-pagination-summary';
      summary.textContent = `${start.toLocaleString()}-${end.toLocaleString()} of ${total.toLocaleString()} targets`;
      const controls = document.createElement('div');
      controls.className = 'project-workspace-pagination-controls';
      const prev = ctx.makeProjectButton('Previous', 'noop', projectId);
      prev.dataset.projectTargetsPage = 'prev';
      prev.dataset.projectTargetsPagerPosition = position;
      prev.disabled = state.loading || offset <= 0;
      const status = document.createElement('span');
      status.className = 'project-workspace-pagination-status';
      status.textContent = state.loading ? 'Loading...' : `Page ${Math.floor(offset / limit) + 1}`;
      const next = ctx.makeProjectButton('Next', 'noop', projectId);
      next.dataset.projectTargetsPage = 'next';
      next.dataset.projectTargetsPagerPosition = position;
      next.disabled = state.loading || offset + targets.length >= total;
      controls.append(prev, status, next);
      wrap.append(summary, controls);
      return wrap;
    }

    function renderTargetBrowser(projectId, summary) {
      const state = targetState(projectId);
      seedTargetPageFromSummary(summary, state);
      ensureTargetPage(projectId);
      const panel = document.createElement('div');
      panel.className = 'project-target-browser';
      panel.appendChild(renderTargetToolbar(projectId, summary, state));
      const targets = state.page && Array.isArray(state.page.targets) ? state.page.targets : [];
      const topPagination = renderTargetPagination(projectId, state, 'top');
      if (topPagination) panel.appendChild(topPagination);
      if (state.loading && !targets.length) {
        panel.appendChild(ctx.emptyProjectPanel('Loading targets...'));
      } else if (state.error) {
        panel.appendChild(ctx.emptyProjectPanel(state.error));
      } else if (!targets.length) {
        const filtered = !!(state.type || state.query || state.autoDiscovered);
        panel.appendChild(ctx.emptyProjectPanel(filtered ? 'No targets match these filters.' : 'No targets yet.'));
      } else {
        panel.appendChild(ctx.renderProjectTargets(projectId, targets));
      }
      const pagination = renderTargetPagination(projectId, state, 'bottom');
      if (pagination) panel.appendChild(pagination);
      return panel;
    }

    function renderDetails(container, project, summary) {
      const meta = document.createElement('div');
      meta.className = 'project-explorer-meta-grid';
      meta.append(
        ctx.projectMetaRow('status', project.status || 'active'),
        ctx.projectMetaRow('created', ctx.formatDate(project.created)),
        ctx.projectMetaRow('updated', ctx.formatDate(project.updated)),
      );
      container.appendChild(meta);

      const labelsSection = document.createElement('section');
      labelsSection.className = 'project-explorer-section project-explorer-labels-section';
      const labelsHeading = document.createElement('div');
      labelsHeading.className = 'project-explorer-section-heading project-labels-heading';
      const labelsTitle = document.createElement('h3');
      labelsTitle.textContent = 'Labels';
      labelsHeading.appendChild(labelsTitle);
      labelsSection.appendChild(labelsHeading);
      if (ctx.projectLabelsForm) labelsSection.appendChild(ctx.projectLabelsForm);
      container.appendChild(labelsSection);

      const projectId = String(project.id || '');
      const targetSection = document.createElement('section');
      targetSection.className = 'project-explorer-section';
      const targetHeading = document.createElement('div');
      targetHeading.className = 'project-explorer-section-heading';
      const targetTitle = document.createElement('h3');
      targetTitle.textContent = 'Targets';
      const targetNew = ctx.makeProjectButton('New', 'new-target', projectId, 'primary');
      targetNew.setAttribute('aria-label', 'Add project target');
      targetHeading.append(targetTitle, targetNew);
      targetSection.appendChild(targetHeading);
      targetSection.appendChild(renderTargetBrowser(projectId, summary));
      container.appendChild(targetSection);

      const notesSection = document.createElement('section');
      notesSection.className = 'project-explorer-section project-explorer-notes-section';
      const notesTitle = document.createElement('h3');
      notesTitle.textContent = 'Notes';
      notesSection.appendChild(notesTitle);
      if (ctx.projectNotesForm) notesSection.appendChild(ctx.projectNotesForm);
      container.appendChild(notesSection);
    }

    return {
      labelChips,
      appendLabelChips,
      appendMobileLabelChips,
      syncForms,
      syncNotesForm,
      hideNotesSavedIndicator,
      showNotesSavedIndicator,
      hideLabelsSavedIndicator,
      showLabelsSavedIndicator,
      cacheNotes,
      cacheLabels,
      saveLabelsNow,
      saveNotesNow,
      scheduleNotesAutosave,
      flushNotesAutosave,
      bindFormEvents,
      invalidateTargetPage,
      loadTargetPage,
      targetPage,
      removeCachedTarget,
      updateCachedTarget,
      targetById,
      renderDetails,
    };
  }

  const DarklabProjectDetails = {
    createProjectDetailsController,
  };
  exportedDarklabProjectDetails = DarklabProjectDetails;
})(globalThis);

export {
  exportedDarklabProjectDetails as DarklabProjectDetails,};
