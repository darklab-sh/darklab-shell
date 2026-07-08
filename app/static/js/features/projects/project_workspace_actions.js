import { showConfirm as importedShowConfirm } from '../../ui/ui_confirm.js';

let exportedDarklabProjectWorkspaceActions = null;

(function projectWorkspaceActionsModule(global) {
  'use strict';

  function createProjectWorkspaceActionsController(context) {
    const ctx = context || {};

    function projectShowConfirm() {
      return typeof ctx.showConfirm === 'function'
        ? ctx.showConfirm
        : ((typeof importedShowConfirm !== 'undefined' && importedShowConfirm) || null);
    }

    async function syncEntityLabels(entityType, entityId, nextLabels) {
      await ctx.EntityMetadataClient.syncEntityLabels(entityType, entityId, nextLabels, {
        request: ctx.projectWorkspaceRequest,
      });
    }

    async function syncEntityNote(entityType, entityId, body) {
      await ctx.EntityMetadataClient.syncEntityNote(entityType, entityId, body, {
        request: ctx.projectWorkspaceRequest,
      });
    }

    async function previewRunEntitiesForLink(projectId, runIds) {
      const normalizedProjectId = String(projectId || '').trim();
      const ids = (Array.isArray(runIds) ? runIds : [runIds])
        .map(runId => String(runId || '').trim())
        .filter(Boolean);
      if (!normalizedProjectId || !ids.length) return null;
      const resp = await ctx.apiFetch(`/projects/${encodeURIComponent(normalizedProjectId)}/links/run-entities/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_ids: ids }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      return data && data.preview ? data.preview : null;
    }

    async function previewRunEntitiesForUnlink(projectId, runIds) {
      const normalizedProjectId = String(projectId || '').trim();
      const ids = (Array.isArray(runIds) ? runIds : [runIds])
        .map(runId => String(runId || '').trim())
        .filter(Boolean);
      if (!normalizedProjectId || !ids.length) return null;
      const resp = await ctx.apiFetch(`/projects/${encodeURIComponent(normalizedProjectId)}/links/run-entities/remove-preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_ids: ids }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      return data && data.preview ? data.preview : null;
    }

    function runEntityLinkOption(preview) {
      const count = Number(preview && preview.linkable || 0);
      if (count <= 0) return null;
      const wrap = document.createElement('div');
      wrap.className = 'project-run-entities-option';
      const label = document.createElement('label');
      label.className = 'form-check';
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.checked = false;
      const text = document.createElement('span');
      const runCount = Number(preview && preview.run_count || 0);
      text.textContent = runCount > 1
        ? `Also add ${count.toLocaleString()} Atlas ${count === 1 ? 'entity' : 'entities'} found in these runs`
        : `Also add ${count.toLocaleString()} Atlas ${count === 1 ? 'entity' : 'entities'} found in this run`;
      label.append(checkbox, text);
      wrap.appendChild(label);
      return { wrap, checkbox };
    }

    function setNodeHidden(node, hidden) {
      if (!node) return;
      node.classList.toggle('u-hidden', hidden);
      node.hidden = hidden;
    }

    function runEntityUnlinkOption() {
      const wrap = document.createElement('div');
      wrap.className = 'project-run-entities-option u-hidden';

      const runFindingsNote = document.createElement('div');
      runFindingsNote.className = 'project-run-entities-note u-hidden';
      wrap.appendChild(runFindingsNote);

      const label = document.createElement('label');
      label.className = 'form-check u-hidden';
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.checked = false;
      const text = document.createElement('span');
      label.append(checkbox, text);
      wrap.appendChild(label);

      const note = document.createElement('div');
      note.className = 'project-run-entities-note u-hidden';
      wrap.appendChild(note);

      const curatedLabel = document.createElement('label');
      curatedLabel.className = 'form-check u-hidden';
      const curatedCheckbox = document.createElement('input');
      curatedCheckbox.type = 'checkbox';
      curatedCheckbox.checked = false;
      const curatedText = document.createElement('span');
      curatedLabel.append(curatedCheckbox, curatedText);
      wrap.appendChild(curatedLabel);

      const curatedNote = document.createElement('div');
      curatedNote.className = 'project-run-entities-note u-hidden';
      wrap.appendChild(curatedNote);

      return {
        wrap,
        checkbox,
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

          setNodeHidden(wrap, removable <= 0 && curated <= 0 && runFindings <= 0);
          setNodeHidden(runFindingsNote, runFindings <= 0);
          runFindingsNote.textContent = runFindings > 0
            ? `Removing the run link will remove ${runFindings.toLocaleString()} ${runFindingLabel} from this project's Findings tab.`
            : '';

          setNodeHidden(label, removable <= 0);
          text.textContent = removable > 0
            ? 'Also remove disposable same-run Atlas entities from this project'
            : '';
          setNodeHidden(note, removable <= 0);
          note.textContent = removable > 0
            ? [
              `This will unlink ${removable.toLocaleString()} ${entityLabel} found only in ${runCount > 1 ? 'these runs' : 'this run'}.`,
              removableFindings > 0
                ? `${removableFindings.toLocaleString()} related ${removableFindingLabel} will no longer appear in this project.`
                : '',
            ].filter(Boolean).join(' ')
            : '';

          setNodeHidden(curatedLabel, curated <= 0);
          curatedText.textContent = curated > 0
            ? `${removable > 0 ? 'Also remove' : 'Remove'} curated same-run Atlas entities from this project`
            : '';
          setNodeHidden(curatedNote, curated <= 0);
          curatedNote.textContent = curated > 0
            ? [
              `${curated.toLocaleString()} curated ${curatedEntityLabel}`,
              curatedFindings > 0 ? `and ${curatedFindings.toLocaleString()} related ${curatedFindingLabel}` : '',
              `will stay in this project unless this is checked. Curated means project-linked elsewhere, labeled, noted, reviewed, or carrying project target metadata.`,
            ].filter(Boolean).join(' ')
            : '';
        },
      };
    }

    async function confirmRunLink(projectId, runIds, label) {
      const confirmFn = projectShowConfirm();
      if (!confirmFn) return { includeEntities: false };
      let option = null;
      try {
        option = runEntityLinkOption(await previewRunEntitiesForLink(projectId, runIds));
      } catch (_) {
        option = null;
      }
      const choice = await confirmFn({
        body: label,
        content: option ? option.wrap : null,
        tone: null,
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'add', label: 'Add to project', role: 'primary' },
        ],
      });
      if (choice !== 'add') return null;
      return { includeEntities: !!(option && option.checkbox.checked) };
    }

    async function linkLastRunToProject(projectId, summary) {
      const normalizedProjectId = String(projectId || ctx.selectedProjectId?.() || '').trim();
      if (!normalizedProjectId) throw new Error('Select or create a project before linking runs.');
      const linkedRunIds = new Set(ctx.projectRunItems(summary).map(run => String(run && run.id || '')).filter(Boolean));
      const resp = await ctx.apiFetch('/history?type=runs&page_size=25', { cache: 'no-store' });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      const candidates = Array.isArray(data.runs) ? data.runs : (Array.isArray(data.items) ? data.items : []);
      const run = candidates.find(item => {
        const runId = String(item && item.id || '');
        return runId && !linkedRunIds.has(runId) && (!item.type || item.type === 'run');
      });
      if (!run) throw new Error('No unlinked recent run found.');
      const confirmed = await confirmRunLink(normalizedProjectId, [String(run.id || '')], 'Add the last run to this project?');
      if (!confirmed) return;
      const linkResp = await ctx.projectWorkspaceRequest(`/projects/${encodeURIComponent(normalizedProjectId)}/links`, {
        method: 'POST',
        body: JSON.stringify({
          entity_type: 'run',
          entity_id: String(run.id || ''),
          source: 'manual',
          ...(confirmed.includeEntities ? { include_entities: true } : {}),
        }),
      });
      await ctx.refreshProjectWorkspace();
      const addedEntities = Number(linkResp && linkResp.linked_entities && linkResp.linked_entities.added || 0);
      ctx.setProjectWorkspaceMessage(addedEntities
        ? `Last run and ${addedEntities.toLocaleString()} ${addedEntities === 1 ? 'entity' : 'entities'} linked to this project.`
        : 'Last run linked to this project.');
    }

    async function confirmDestructive({ body, actionLabel, actionId, note }) {
      const confirmFn = projectShowConfirm();
      if (!confirmFn) {
        throw new Error('Project destructive confirmations require showConfirm.');
      }
      const choice = await confirmFn({
        body: note ? { text: body, note } : body,
        tone: 'danger',
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: actionId, label: actionLabel, role: 'destructive' },
        ],
      });
      return choice === actionId;
    }

    function confirmTargetDelete(targetValue) {
      const label = String(targetValue || 'this target');
      return confirmDestructive({
        body: `Remove target ${label}?`,
        actionLabel: 'Remove',
        actionId: 'remove',
      });
    }

    async function confirmRunUnlink(projectId, runId, runCommand) {
      const confirmFn = projectShowConfirm();
      if (!confirmFn) {
        throw new Error('Project destructive confirmations require showConfirm.');
      }
      const label = String(runCommand || 'this run');
      const option = runEntityUnlinkOption();
      try {
        option.setPreview(await previewRunEntitiesForUnlink(projectId, [runId]));
      } catch (_) {
        option.setPreview(null);
      }
      const choice = await confirmFn({
        body: `Remove run from project: ${label}?`,
        content: option.wrap.classList.contains('u-hidden') ? null : option.wrap,
        tone: 'danger',
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'remove', label: 'Remove', role: 'destructive' },
        ],
      });
      if (choice !== 'remove') return null;
      return {
        includeEntities: option.includeEntities(),
        includeCuratedEntities: option.includeCuratedEntities(),
      };
    }

    function confirmPackageDelete(packageName) {
      const label = String(packageName || 'this package');
      return confirmDestructive({
        body: `Delete package: ${label}?`,
        actionLabel: 'Delete',
        actionId: 'delete',
      });
    }

    function confirmProjectDelete(projectName) {
      const label = String(projectName || 'this project');
      return confirmDestructive({
        body: `Delete project: ${label}?`,
        note: 'This removes the project, its targets, packages, and project links. Source runs and saved history remain.',
        actionLabel: 'Delete',
        actionId: 'delete',
      });
    }

    return {
      confirmDestructive,
      confirmPackageDelete,
      confirmProjectDelete,
      confirmRunLink,
      confirmRunUnlink,
      confirmTargetDelete,
      linkLastRunToProject,
      previewRunEntitiesForUnlink,
      previewRunEntitiesForLink,
      syncEntityLabels,
      syncEntityNote,
    };
  }

  const DarklabProjectWorkspaceActions = { createProjectWorkspaceActionsController };
  exportedDarklabProjectWorkspaceActions = DarklabProjectWorkspaceActions;
})(globalThis);

export {
  exportedDarklabProjectWorkspaceActions as DarklabProjectWorkspaceActions,};
