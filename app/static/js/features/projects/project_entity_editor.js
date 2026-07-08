// Project metadata editor controller.
// Loaded before shell_chrome.js; shell chrome supplies save and refresh callbacks.

let exportedDarklabProjectEntityEditor = null;

(function projectEntityEditorModule(global) {
  'use strict';

  function createProjectEntityEditorController(context) {
    const ctx = context || {};
    let editingEntity = null;
    let activityRequestId = 0;
    let formEventsBound = false;

    function titleize(value) {
      return String(value || 'Activity')
        .replace(/[._-]+/g, ' ')
        .replace(/\b\w/g, char => char.toLocaleUpperCase());
    }

    function formatDate(value) {
      if (!value) return '';
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return String(value);
      return date.toLocaleString();
    }

    function actorLabel(event) {
      const actor = event && event.actor && typeof event.actor === 'object' ? event.actor : {};
      const name = String(actor.display_name || actor.member_id || '').trim();
      const role = String(actor.role || '').trim();
      if (name && role) return `${name} · ${role}`;
      return name || role || 'System';
    }

    function activitySummary(details) {
      const value = details && typeof details === 'object' ? details : {};
      const parts = [];
      Object.entries(value).some(([key, item]) => {
        if (item && typeof item === 'object') return false;
        if (item === undefined || item === null || item === '') return false;
        parts.push(`${key.replaceAll('_', ' ')}: ${String(item)}`);
        return parts.length >= 2;
      });
      return parts.join(' · ') || 'Recorded activity';
    }

    function auditTargetTypeForEntity(entityType) {
      const normalized = String(entityType || '').trim();
      if (normalized === 'run_file_artifact' || normalized === 'workspace_file') return 'file';
      if (normalized === 'atlas_entity') return 'entity';
      return normalized;
    }

    function logActivityFailure(error) {
      if (typeof ctx.logClientError !== 'function' || !editingEntity) return;
      const payload = {
        project_id: String(editingEntity.projectId || ''),
        target_type: auditTargetTypeForEntity(editingEntity.entityType),
        target_id: String(editingEntity.entityId || ''),
      };
      ctx.logClientError(`failed to load project recent activity ${JSON.stringify(payload)}`, error);
    }

    function renderActivityState({ loading = false, error = '', events = [], hasMore = false } = {}) {
      if (!ctx.activityRoot) return;
      ctx.activityRoot.replaceChildren();
      const header = document.createElement('div');
      header.className = 'project-entity-activity-header';
      const title = document.createElement('span');
      title.textContent = 'Recent activity';
      header.appendChild(title);
      if (editingEntity?.projectId) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn btn-secondary btn-compact';
        button.dataset.projectEntityActivityAction = 'open-project-activity';
        button.textContent = hasMore ? 'View all' : 'Activity';
        header.appendChild(button);
      }
      ctx.activityRoot.appendChild(header);

      if (loading) {
        ctx.activityRoot.appendChild(document.createElement('div')).textContent = 'Loading activity...';
        ctx.activityRoot.lastChild.className = 'project-entity-activity-empty';
        return;
      }
      if (error) {
        ctx.activityRoot.appendChild(document.createElement('div')).textContent = error;
        ctx.activityRoot.lastChild.className = 'project-entity-activity-empty';
        return;
      }
      if (!events.length) {
        ctx.activityRoot.appendChild(document.createElement('div')).textContent = 'No recent activity for this item.';
        ctx.activityRoot.lastChild.className = 'project-entity-activity-empty';
        return;
      }

      const list = document.createElement('div');
      list.className = 'project-entity-activity-list';
      events.slice(0, 5).forEach((event) => {
        const row = document.createElement('div');
        row.className = 'project-entity-activity-row panel-row';
        const main = document.createElement('div');
        main.className = 'project-entity-activity-main';
        const action = document.createElement('strong');
        action.textContent = titleize(event.event_type);
        const summary = document.createElement('span');
        summary.textContent = activitySummary(event.details);
        main.append(action, summary);
        const meta = document.createElement('div');
        meta.className = 'project-entity-activity-meta';
        meta.textContent = [formatDate(event.created), actorLabel(event)].filter(Boolean).join(' · ');
        row.append(main, meta);
        list.appendChild(row);
      });
      ctx.activityRoot.appendChild(list);
    }

    async function loadActivity() {
      if (!ctx.activityRoot || !editingEntity?.projectId || !editingEntity?.entityId || !ctx.projectWorkspaceRequest) {
        return;
      }
      const requestId = ++activityRequestId;
      renderActivityState({ loading: true });
      const params = new URLSearchParams({
        target_type: auditTargetTypeForEntity(editingEntity.entityType),
        target_id: editingEntity.entityId,
        limit: '5',
        offset: '0',
      });
      try {
        const resp = await ctx.projectWorkspaceRequest(
          `/projects/${encodeURIComponent(editingEntity.projectId)}/activity?${params.toString()}`,
          { cache: 'no-store' },
        );
        if (!resp.ok) {
          const err = typeof ctx.projectResponseError === 'function'
            ? await ctx.projectResponseError(resp, 'Could not load recent activity.')
            : new Error('Could not load recent activity.');
          throw err;
        }
        const payload = await resp.json();
        if (requestId !== activityRequestId || !editingEntity) return;
        renderActivityState({
          events: Array.isArray(payload.events) ? payload.events : [],
          hasMore: !!payload.has_more,
        });
      } catch (err) {
        if (requestId !== activityRequestId || !editingEntity) return;
        renderActivityState({ error: err && err.message ? err.message : 'Could not load recent activity.' });
        logActivityFailure(err);
      }
    }

    function isOpen() {
      return !!(ctx.overlay && ctx.overlay.classList.contains('open'));
    }

    function close() {
      if (!ctx.overlay) return;
      ctx.overlay.classList.add('u-hidden');
      ctx.overlay.classList.remove('open');
      ctx.overlay.setAttribute('aria-hidden', 'true');
      editingEntity = null;
      activityRequestId += 1;
      ctx.activityRoot?.replaceChildren();
      if (ctx.form) {
        ctx.form.dataset.projectId = '';
        ctx.form.dataset.entityType = '';
        ctx.form.dataset.entityId = '';
      }
      ctx.syncProjectWorkspaceNestedSuppression();
    }

    function open(projectId, entityType, entity, options = {}) {
      if (!ctx.overlay || !ctx.form || !ctx.labelsInput || !ctx.noteInput) {
        throw new Error('Metadata editor is not available.');
      }
      const entityId = String(entity && entity.id || '');
      if (!entityType || !entityId) throw new Error('Entity is missing its identifier.');
      const title = ctx.entityTitleForEditor(entityType, entity);
      editingEntity = {
        projectId: String(projectId || ''),
        entityType: String(entityType),
        entityId,
        entity,
        onSaved: typeof options.onSaved === 'function' ? options.onSaved : null,
      };
      ctx.form.dataset.projectId = String(projectId || '');
      ctx.form.dataset.entityType = String(entityType);
      ctx.form.dataset.entityId = entityId;
      if (ctx.title) {
        ctx.title.textContent = `EDIT ${ctx.entityEditorLabelForType(entityType)}`;
      }
      if (ctx.subtitle) ctx.subtitle.textContent = title;
      ctx.labelsInput.value = ctx.entityLabelValues(entity).join(', ');
      ctx.noteInput.value = ctx.entityNoteBody(entity);
      if (ctx.submitButton) ctx.submitButton.textContent = 'Save';
      ctx.overlay.classList.remove('u-hidden');
      ctx.overlay.classList.add('open');
      ctx.overlay.setAttribute('aria-hidden', 'false');
      loadActivity().catch(() => {});
      ctx.syncProjectWorkspaceNestedSuppression();
      ctx.installProjectMobileKeyboardGuards();
      ctx.focusProjectNestedSheet(ctx.overlay, ctx.labelsInput);
    }

    async function save() {
      if (!editingEntity || !ctx.labelsInput || !ctx.noteInput) return;
      const { projectId, entityType, entityId, onSaved } = editingEntity;
      const labels = ctx.parseLabelInput(ctx.labelsInput.value);
      const noteBody = String(ctx.noteInput.value || '').trim();
      if (ctx.submitButton) ctx.submitButton.disabled = true;
      try {
        await ctx.syncEntityLabels(entityType, entityId, labels);
        await ctx.syncEntityNote(entityType, entityId, noteBody);
        close();
        if (typeof onSaved === 'function') {
          await onSaved({ entityType, entityId, labels, noteBody });
        } else {
          await ctx.refreshProjectWorkspace();
          if (entityType === 'finding' && projectId) {
            ctx.invalidateProjectFindings(projectId);
            await ctx.loadProjectFindings(projectId);
          }
          ctx.renderProjectExplorer();
          const label = ctx.entityEditorLabelForType(entityType).toLocaleLowerCase();
          ctx.setProjectWorkspaceMessage(`${label.charAt(0).toLocaleUpperCase()}${label.slice(1)} metadata saved.`);
        }
      } finally {
        if (ctx.submitButton) ctx.submitButton.disabled = false;
      }
    }

    function bindFormEvents() {
      if (formEventsBound) return;
      formEventsBound = true;
      ctx.form?.addEventListener('submit', async (event) => {
        event.preventDefault();
        try {
          await save();
        } catch (err) {
          ctx.setProjectWorkspaceMessage(err.message || 'Could not save metadata.', { error: true });
        }
      });
      ctx.activityRoot?.addEventListener('click', (event) => {
        const action = event.target.closest?.('[data-project-entity-activity-action]');
        if (!action || action.dataset.projectEntityActivityAction !== 'open-project-activity') return;
        event.preventDefault();
        if (editingEntity && typeof ctx.openProjectActivity === 'function') {
          ctx.openProjectActivity(editingEntity.projectId, {
            targetType: auditTargetTypeForEntity(editingEntity.entityType),
            targetId: editingEntity.entityId,
          });
        }
      });
    }

    return {
      bindFormEvents,
      close,
      isOpen,
      open,
      save,
    };
  }

  const DarklabProjectEntityEditor = {
    createProjectEntityEditorController,
  };
  exportedDarklabProjectEntityEditor = DarklabProjectEntityEditor;
})(globalThis);

export {
  exportedDarklabProjectEntityEditor as DarklabProjectEntityEditor,};
