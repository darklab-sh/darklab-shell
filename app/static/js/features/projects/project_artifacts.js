// Project Artifacts tab controller.
// Loaded before shell_chrome.js; shell chrome supplies the surrounding Projects state.

(function projectArtifactsModule(global) {
  'use strict';

  function createProjectArtifactsController(context) {
    const ctx = context || {};

    function groupKey(projectId, runId) {
      return `${String(projectId || '')}\x1f${String(runId || '')}`;
    }

    function groupCollapsed(projectId, runId) {
      return ctx.collapsedArtifactGroups().has(groupKey(projectId, runId));
    }

    function items(summary) {
      return summary && Array.isArray(summary.artifacts) ? summary.artifacts : [];
    }

    function filesEnabled() {
      return !!ctx.filesEnabled();
    }

    function artifactsVisible() {
      return filesEnabled();
    }

    function status(artifact) {
      const artifactStatus = String(artifact && artifact.file_status || '').trim();
      if (
        artifactStatus === 'available'
        || artifactStatus === 'missing'
        || artifactStatus === 'changed'
        || artifactStatus === 'disabled'
      ) {
        return artifactStatus;
      }
      return artifact && artifact.file_available === false ? 'missing' : 'available';
    }

    function statusLabel(artifact) {
      const artifactStatus = status(artifact);
      if (artifactStatus === 'disabled') return 'disabled';
      if (artifactStatus === 'changed') return 'changed';
      if (artifactStatus === 'missing') return 'missing';
      return 'available';
    }

    function accessory(projectId, artifact) {
      const wrap = document.createElement('div');
      wrap.className = 'project-artifact-badges';
      const size = document.createElement('span');
      size.className = 'project-explorer-item-badge';
      size.textContent = ctx.formatBytes(artifact.byte_size);
      const statusNode = document.createElement('span');
      statusNode.className = `project-artifact-status is-${status(artifact)}`;
      statusNode.textContent = statusLabel(artifact);
      wrap.append(size, statusNode);
      const actions = document.createElement('div');
      actions.className = 'project-artifact-actions';
      const edit = document.createElement('button');
      edit.type = 'button';
      edit.className = 'btn btn-secondary btn-compact project-artifact-action';
      edit.dataset.projectAction = 'edit-artifact-metadata';
      edit.dataset.projectId = String(projectId || '');
      edit.dataset.artifactId = String(artifact.id || '');
      edit.textContent = 'Edit';
      ctx.bindProjectRuntimePressable(edit);
      actions.appendChild(edit);
      const artifactStatus = status(artifact);
      const available = artifactStatus !== 'missing' && artifactStatus !== 'disabled';
      [
        ['preview', 'Preview'],
        ['download', 'Download'],
      ].forEach(([actionName, label]) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn btn-secondary btn-compact project-artifact-action';
        btn.dataset.projectAction = `artifact-${actionName}`;
        btn.dataset.projectId = String(projectId || '');
        btn.dataset.artifactId = String(artifact.id || '');
        btn.dataset.artifactPath = String(artifact.workspace_path || '');
        btn.disabled = !available;
        btn.title = available ? label : (artifact.file_status_detail || 'Workspace file is unavailable');
        btn.textContent = label;
        ctx.bindProjectRuntimePressable(btn);
        actions.appendChild(btn);
      });
      wrap.appendChild(actions);
      return wrap;
    }

    function detail(artifact) {
      const parts = [
        artifact.kind || 'file',
        artifact.content_type || 'unknown type',
        ctx.formatDate(artifact.created),
      ];
      const artifactStatus = status(artifact);
      const statusDetail = String(artifact.file_status_detail || '').trim();
      if (artifactStatus === 'changed') {
        parts.push(`current ${ctx.formatBytes(artifact.current_byte_size)}`);
      } else if (artifactStatus === 'missing') {
        parts.push(statusDetail || 'workspace file is missing');
      } else if (artifactStatus === 'disabled') {
        parts.push(statusDetail || 'Files are disabled on this instance');
      }
      return parts.filter(Boolean).join(ctx.metaSeparator || ' - ');
    }

    function detailLines(artifact) {
      const artifactStatus = status(artifact);
      const statusDetail = String(artifact && artifact.file_status_detail || '').trim();
      const firstLine = [
        artifact && artifact.kind || 'file',
        artifact && artifact.content_type || 'unknown type',
      ].filter(Boolean).join(ctx.metaSeparator || ' - ');
      const lines = [
        firstLine,
        ctx.formatDate(artifact && artifact.created),
      ].filter(Boolean);
      if (artifactStatus === 'changed') {
        lines.push(`current ${ctx.formatBytes(artifact.current_byte_size)}`);
      } else if (artifactStatus === 'missing') {
        lines.push(statusDetail || 'workspace file is missing');
      } else if (artifactStatus === 'disabled') {
        lines.push(statusDetail || 'Files are disabled on this instance');
      }
      return lines;
    }

    function downloadName(artifactPath = '', fallback = 'artifact') {
      const name = String(artifactPath || '').split('/').filter(Boolean).pop();
      return name || fallback;
    }

    async function preview(projectId, artifactId) {
      const resp = await ctx.apiFetch(
        `/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(artifactId)}/preview`,
        { cache: 'no-store' },
      );
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.error || 'Unable to preview artifact.');
      const artifact = data.artifact || {};
      const showViewer = global && typeof global.showWorkspaceViewer === 'function'
        ? global.showWorkspaceViewer
        : (typeof window !== 'undefined' && typeof window.showWorkspaceViewer === 'function'
            ? window.showWorkspaceViewer
            : null);
      if (!showViewer) throw new Error('File preview is not available.');
      showViewer(
        artifact.workspace_path || 'artifact',
        data.text || '',
        { size: artifact.current_byte_size ?? artifact.byte_size ?? null, elevated: true },
      );
    }

    async function download(projectId, artifactId, artifactPath = '') {
      const resp = await ctx.apiFetch(
        `/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(artifactId)}/download`,
        { cache: 'no-store' },
      );
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.error || 'Unable to download artifact.');
      }
      const blob = await resp.blob();
      ctx.downloadBlobAsAttachment(
        blob,
        downloadName(artifactPath, artifactId || 'artifact'),
        'Artifact download started.',
      );
    }

    function renderArtifacts(container, projectId, summary) {
      const allArtifacts = items(summary);
      const filterActive = ctx.projectTargetFilterActive(projectId, summary);
      if (filterActive && !ctx.projectFindingsLoaded(projectId)) {
        container.appendChild(ctx.emptyProjectPanel('Loading target associations...'));
        return;
      }
      const visibleArtifacts = ctx.filteredProjectArtifacts(projectId, summary);
      if (!allArtifacts.length) {
        container.appendChild(ctx.emptyProjectPanel('No run artifacts have been captured for this project yet.'));
        return;
      }
      if (!visibleArtifacts.length) {
        container.appendChild(ctx.emptyProjectPanel('No artifacts match the selected targets.'));
        return;
      }
      ctx.groupBy(visibleArtifacts, artifact => artifact.run_id).forEach((groupItems, runId) => {
        const group = document.createElement('section');
        group.className = 'project-explorer-group project-artifacts-group';
        const run = ctx.projectRunById(summary, runId);
        const command = String(run?.command || '').trim();
        const shortId = ctx.shortProjectRunId(runId);
        const collapsed = groupCollapsed(projectId, runId);
        group.classList.toggle('is-collapsed', collapsed);
        const title = document.createElement('button');
        title.type = 'button';
        title.className = 'toggle-btn project-explorer-group-toggle';
        title.dataset.projectArtifactGroupToggle = '1';
        title.dataset.projectId = projectId;
        title.dataset.projectArtifactGroup = String(runId || '');
        title.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
        ctx.bindProjectRuntimePressable(title);
        const caret = document.createElement('span');
        caret.className = 'project-explorer-group-caret';
        caret.setAttribute('aria-hidden', 'true');
        caret.textContent = ctx.groupCaret || '';
        const label = document.createElement('span');
        label.className = 'project-explorer-group-title';
        label.textContent = `${command || 'Run'}${shortId ? ` (${shortId})` : ''}`;
        const count = document.createElement('span');
        count.className = 'project-explorer-group-count';
        count.textContent = `${groupItems.length} artifact${groupItems.length === 1 ? '' : 's'}`;
        title.append(caret, label, count);
        group.appendChild(title);
        const body = document.createElement('div');
        body.className = 'project-explorer-group-body';
        body.hidden = collapsed;
        groupItems.forEach((artifact) => {
          body.appendChild(ctx.projectItemRow({
            title: artifact.display_name || artifact.workspace_path,
            meta: artifact.workspace_path,
            detail: detail(artifact),
            chips: ctx.entityMetadataChips(artifact),
            accessory: accessory(projectId, artifact),
          }));
        });
        group.appendChild(body);
        container.appendChild(group);
      });
    }

    return {
      groupKey,
      groupCollapsed,
      items,
      filesEnabled,
      artifactsVisible,
      status,
      statusLabel,
      accessory,
      detail,
      detailLines,
      downloadName,
      preview,
      download,
      renderArtifacts,
    };
  }

  global.DarklabProjectArtifacts = {
    createProjectArtifactsController,
  };
})(globalThis);
