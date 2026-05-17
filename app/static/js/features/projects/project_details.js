// Project Details tab controller.
// Loaded before shell_chrome.js; shell chrome supplies the surrounding Projects state.

(function projectDetailsModule(global) {
  'use strict';

  function createProjectDetailsController(context) {
    const ctx = context || {};
    let notesSaveTimer = null;
    let notesSaveSeq = 0;
    let notesSavedDelayTimer = null;
    let notesSavedHideTimer = null;
    let labelsSavedHideTimer = null;

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
      if (!showingDetails || String(ctx.projectLabelsInput?.dataset.projectId || '') !== nextProjectId) {
        hideLabelsSavedIndicator();
      }
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

    function setNotesSavedIndicator(visible) {
      if (!ctx.projectNotesSaveStatus) return;
      ctx.projectNotesSaveStatus.classList.toggle('u-hidden', !visible);
    }

    function hideNotesSavedIndicator() {
      if (notesSavedDelayTimer) {
        clearTimeout(notesSavedDelayTimer);
        notesSavedDelayTimer = null;
      }
      if (notesSavedHideTimer) {
        clearTimeout(notesSavedHideTimer);
        notesSavedHideTimer = null;
      }
      setNotesSavedIndicator(false);
    }

    function showNotesSavedIndicator() {
      hideNotesSavedIndicator();
      notesSavedDelayTimer = setTimeout(() => {
        notesSavedDelayTimer = null;
        setNotesSavedIndicator(true);
        notesSavedHideTimer = setTimeout(() => {
          notesSavedHideTimer = null;
          setNotesSavedIndicator(false);
        }, ctx.fieldSavedIndicatorVisibleMs);
      }, ctx.fieldSavedIndicatorDelayMs);
    }

    function setLabelsSavedIndicator(visible) {
      if (!ctx.projectLabelsSaveStatus) return;
      ctx.projectLabelsSaveStatus.classList.toggle('u-hidden', !visible);
    }

    function hideLabelsSavedIndicator() {
      if (labelsSavedHideTimer) {
        clearTimeout(labelsSavedHideTimer);
        labelsSavedHideTimer = null;
      }
      setLabelsSavedIndicator(false);
    }

    function showLabelsSavedIndicator(projectId) {
      const normalizedProjectId = String(projectId || '');
      hideLabelsSavedIndicator();
      if (normalizedProjectId && String(ctx.projectLabelsInput?.dataset.projectId || '') !== normalizedProjectId) return;
      setLabelsSavedIndicator(true);
      labelsSavedHideTimer = setTimeout(() => {
        labelsSavedHideTimer = null;
        setLabelsSavedIndicator(false);
      }, ctx.projectLabelsSavedVisibleMs);
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
      hideLabelsSavedIndicator();
      try {
        await ctx.syncEntityLabels('project', projectId, labels);
        ctx.projectLabelsInput.value = labelText;
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
      ctx.projectLabelsForm?.addEventListener('submit', (event) => {
        event.preventDefault();
        saveLabelsNow().catch(() => {});
      });
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
      if (ctx.projectLabelsSaveStatus) labelsHeading.appendChild(ctx.projectLabelsSaveStatus);
      labelsSection.appendChild(labelsHeading);
      if (ctx.projectLabelsForm) labelsSection.appendChild(ctx.projectLabelsForm);
      container.appendChild(labelsSection);

      const targets = ctx.projectTargetItems(summary);
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
      targetSection.appendChild(ctx.renderProjectTargets(projectId, targets));
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
      setNotesSavedIndicator,
      hideNotesSavedIndicator,
      showNotesSavedIndicator,
      setLabelsSavedIndicator,
      hideLabelsSavedIndicator,
      showLabelsSavedIndicator,
      cacheNotes,
      cacheLabels,
      saveLabelsNow,
      saveNotesNow,
      scheduleNotesAutosave,
      flushNotesAutosave,
      bindFormEvents,
      renderDetails,
    };
  }

  global.DarklabProjectDetails = {
    createProjectDetailsController,
  };
})(globalThis);
