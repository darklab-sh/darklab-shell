// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { syncAppSelect as importedSyncAppSelect } from '../../ui/ui_helpers.js';

let exportedDarklabProjectTargets = null;

(function projectTargetsModule(global) {
  'use strict';

  function createProjectTargetsController(context) {
    const ctx = context || {};

    function setTypeValue(value) {
      const select = ctx.typeSelect;
      if (!select) return;
      const normalized = String(value || 'domain');
      if (![...select.options].some(option => option.value === normalized)) {
        const option = document.createElement('option');
        option.value = normalized;
        option.textContent = normalized;
        select.appendChild(option);
      }
      select.value = normalized;
      if (typeof importedSyncAppSelect === 'function') {
        importedSyncAppSelect(select);
      }
      syncValueHelp(normalized);
    }

    function syncValueHelp(type = '') {
      const normalized = String(type || ctx.typeSelect?.value || 'domain').trim();
      const copy = ctx.targetHelpers.helpForType(normalized);
      if (ctx.valueInput) {
        ctx.valueInput.placeholder = copy.placeholder;
      }
      if (ctx.valueHelp) {
        ctx.valueHelp.textContent = copy.help;
      }
    }

    function setValueError(message = '', { target = 'value' } = {}) {
      const hasError = !!message;
      if (ctx.valueInput) {
        ctx.valueInput.setAttribute('aria-invalid', hasError && target === 'value' ? 'true' : 'false');
      }
      if (ctx.notesInput) {
        ctx.notesInput.setAttribute('aria-invalid', hasError && target === 'notes' ? 'true' : 'false');
      }
      if (ctx.valueError) {
        ctx.valueError.textContent = message;
        ctx.valueError.classList.toggle('u-hidden', !hasError);
      }
    }

    function valueValidationError(type, value) {
      return ctx.targetHelpers.valueValidationError(type, value);
    }

    function notesValidationError(notes) {
      return ctx.targetHelpers.notesValidationError(notes);
    }

    function editorPayload() {
      return {
        type: String(ctx.typeSelect?.value || 'domain').trim() || 'domain',
        value: String(ctx.valueInput?.value || '').trim(),
      };
    }

    function editorMetadata() {
      return {
        labels: ctx.EntityMetadataClient.parseLabelInput(ctx.labelInput?.value || ''),
        noteBody: String(ctx.notesInput?.value || '').trim(),
      };
    }

    function openEditor(projectId, target = null) {
      const normalizedProjectId = String(projectId || '');
      if (!normalizedProjectId || !ctx.overlay || !ctx.form) {
        ctx.setProjectWorkspaceMessage('Select or create a project before adding targets.', { error: true });
        return;
      }
      const isEdit = !!(target && target.id);
      const targetId = isEdit ? String(target.id || '') : '';
      ctx.setEditingTargetId(targetId);
      ctx.form.dataset.projectId = normalizedProjectId;
      ctx.form.dataset.targetId = targetId;
      setTypeValue(isEdit ? target.type : ctx.getLastTargetType());
      if (ctx.valueInput) ctx.valueInput.value = isEdit ? String(target.value || '') : '';
      if (ctx.labelInput) ctx.labelInput.value = isEdit ? ctx.entityLabelValues(target).join(', ') : '';
      if (ctx.notesInput) {
        ctx.notesInput.value = isEdit ? ctx.entityNoteBody(target) : '';
        ctx.notesInput.setAttribute('aria-invalid', 'false');
      }
      if (ctx.title) ctx.title.textContent = isEdit ? 'EDIT TARGET' : 'NEW TARGET';
      if (ctx.submitButton) ctx.submitButton.textContent = isEdit ? 'Save Target' : 'Add Target';
      setValueError('');
      ctx.overlay.classList.remove('u-hidden');
      ctx.overlay.classList.add('open');
      ctx.overlay.setAttribute('aria-hidden', 'false');
      ctx.installProjectMobileKeyboardGuards();
      ctx.focusProjectNestedSheet(ctx.overlay, ctx.valueInput);
    }

    function closeEditor({ clear = true } = {}) {
      if (ctx.overlay) {
        ctx.overlay.classList.add('u-hidden');
        ctx.overlay.classList.remove('open');
        ctx.overlay.setAttribute('aria-hidden', 'true');
      }
      ctx.syncProjectWorkspaceNestedSuppression();
      if (clear) {
        ctx.setEditingTargetId('');
        if (ctx.form) {
          delete ctx.form.dataset.projectId;
          delete ctx.form.dataset.targetId;
        }
        setTypeValue('domain');
        if (ctx.valueInput) ctx.valueInput.value = '';
        if (ctx.labelInput) ctx.labelInput.value = '';
        if (ctx.notesInput) ctx.notesInput.value = '';
        setValueError('');
      }
    }

    function isOpen() {
      return !!(ctx.overlay && ctx.overlay.classList.contains('open'));
    }

    async function saveEditor() {
      const projectId = String(ctx.form?.dataset.projectId || ctx.selectedProjectId?.() || (ctx.activeProject?.() && ctx.activeProject().id ? ctx.activeProject().id : ''));
      const targetId = String(ctx.form?.dataset.targetId || '');
      const payload = editorPayload();
      if (!projectId) {
        ctx.setProjectWorkspaceMessage('Select or create a project before adding targets.', { error: true });
        return;
      }
      const validationError = valueValidationError(payload.type, payload.value);
      if (validationError) {
        setValueError(validationError);
        ctx.valueInput?.focus();
        return;
      }
      const notesError = notesValidationError(payload.notes);
      if (notesError) {
        setValueError(notesError, { target: 'notes' });
        ctx.notesInput?.focus();
        return;
      }
      try {
        const metadata = editorMetadata();
        const url = targetId
          ? `/projects/${encodeURIComponent(projectId)}/targets/${encodeURIComponent(targetId)}`
          : `/projects/${encodeURIComponent(projectId)}/targets`;
        const resp = await ctx.projectWorkspaceRequest(url, {
          method: targetId ? 'PUT' : 'POST',
          body: JSON.stringify(payload),
        });
        const data = await resp.json().catch(() => ({}));
        const savedTargetId = targetId || String(data && data.target && data.target.id || '');
        if (!savedTargetId) {
          throw new Error('Target saved without an identifier.');
        }
        await ctx.syncEntityLabels('target', savedTargetId, metadata.labels);
        await ctx.syncEntityNote('target', savedTargetId, metadata.noteBody);
        ctx.setLastTargetType(payload.type || ctx.getLastTargetType());
        closeEditor();
        ctx.invalidateProjectOverview?.(projectId);
        await ctx.loadProjectTargetPage?.(projectId, { skipFinalRender: true });
        ctx.renderProjectExplorer?.();
        ctx.renderProjectMobileDetail?.();
        ctx.loadProjectAutocompleteTargets?.();
        ctx.setProjectWorkspaceMessage(targetId ? 'Target updated.' : 'Target added to selected project.');
      } catch (err) {
        ctx.setProjectWorkspaceMessage(err.message || 'Could not save target.', { error: true });
      }
    }

    function bindEditorEvents() {
      ctx.typeSelect?.addEventListener('change', () => {
        syncValueHelp(ctx.typeSelect.value);
        setValueError('');
      });
      ctx.valueInput?.addEventListener('input', () => {
        setValueError('');
      });
      ctx.notesInput?.addEventListener('input', () => {
        setValueError('');
      });
      ctx.form?.addEventListener('submit', async (event) => {
        event.preventDefault();
        await saveEditor();
      });
    }

    function targetDisplayRow(projectId, target) {
      const row = document.createElement('article');
      row.className = 'project-target-row';
      const main = document.createElement('div');
      main.className = 'project-target-main';

      const heading = document.createElement('div');
      heading.className = 'project-target-heading';
      const type = document.createElement('span');
      type.className = 'project-target-type';
      type.textContent = String(target.type || 'target');
      const value = document.createElement('span');
      value.className = 'project-target-value';
      value.textContent = String(target.value || '');
      heading.append(type, value);
      if (String(target.review_state || '') === 'pending') {
        const badge = document.createElement('span');
        badge.className = 'project-target-auto-badge';
        badge.textContent = 'auto';
        badge.title = 'Discovered from command input';
        heading.appendChild(badge);
      }
      main.appendChild(heading);

      const chips = ctx.entityMetadataChips(target);
      if (chips.length) {
        const chipWrap = document.createElement('div');
        chipWrap.className = 'project-explorer-item-chips project-target-metadata-chips';
        chips.forEach((chip) => {
          const chipEl = document.createElement('span');
          chipEl.className = ctx.entityMetadataChipClass(chip.kind);
          chipEl.textContent = String(chip.label || '');
          chipWrap.appendChild(chipEl);
        });
        main.appendChild(chipWrap);
      }

      const actions = document.createElement('div');
      actions.className = 'project-target-actions';
      const open = ctx.makeProjectButton('Atlas', 'open-project-entity', projectId);
      const edit = ctx.makeProjectButton('Edit', 'edit-target', projectId);
      const remove = ctx.makeProjectButton('Remove', 'delete-target', projectId);
      const targetId = String(target.id || '');
      open.dataset.entityId = targetId;
      open.dataset.entityValue = String(target.value || '');
      open.dataset.entityType = String(target.type || '');
      const buttons = [open];
      if (String(target.review_state || '') === 'pending') {
        buttons.push(ctx.makeProjectButton('Confirm', 'confirm-target', projectId, 'secondary'));
        buttons.push(ctx.makeProjectButton('Dismiss', 'dismiss-target', projectId));
      }
      buttons.push(edit, remove);
      buttons.forEach((btn) => {
        btn.dataset.targetId = targetId;
        btn.dataset.targetValue = String(target.value || '');
      });
      actions.append(...buttons);
      row.append(main, actions);
      return row;
    }

    function renderTargets(projectId, targets) {
      if (!targets.length) return ctx.emptyProjectPanel('No targets yet.');
      const list = document.createElement('div');
      list.className = 'project-target-list';
      targets.forEach((target) => {
        list.appendChild(targetDisplayRow(projectId, target));
      });
      return list;
    }

    return {
      setTypeValue,
      syncValueHelp,
      setValueError,
      valueValidationError,
      notesValidationError,
      editorPayload,
      editorMetadata,
      openEditor,
      closeEditor,
      isOpen,
      bindEditorEvents,
      saveEditor,
      targetDisplayRow,
      renderTargets,
    };
  }

  const DarklabProjectTargets = {
    createProjectTargetsController,
  };
  exportedDarklabProjectTargets = DarklabProjectTargets;
})(globalThis);

export {
  exportedDarklabProjectTargets as DarklabProjectTargets,};
