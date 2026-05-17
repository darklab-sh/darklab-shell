// Project metadata editor controller.
// Loaded before shell_chrome.js; shell chrome supplies save and refresh callbacks.

(function projectEntityEditorModule(global) {
  'use strict';

  function createProjectEntityEditorController(context) {
    const ctx = context || {};
    let editingEntity = null;

    function isOpen() {
      return !!(ctx.overlay && ctx.overlay.classList.contains('open'));
    }

    function close() {
      if (!ctx.overlay) return;
      ctx.overlay.classList.add('u-hidden');
      ctx.overlay.classList.remove('open');
      ctx.overlay.setAttribute('aria-hidden', 'true');
      editingEntity = null;
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
      ctx.form?.addEventListener('submit', async (event) => {
        event.preventDefault();
        try {
          await save();
        } catch (err) {
          ctx.setProjectWorkspaceMessage(err.message || 'Could not save metadata.', { error: true });
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

  global.DarklabProjectEntityEditor = {
    createProjectEntityEditorController,
  };
})(globalThis);
