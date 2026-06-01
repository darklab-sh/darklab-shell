// Shared Project UI/data helpers.
// Loaded before shell_chrome.js; shell chrome supplies runtime binding callbacks.

(function projectSharedUiModule(global) {
  'use strict';

  function createProjectSharedUiController(context) {
    const ctx = context || {};

    function displayName(project) {
      if (!project || typeof project !== 'object') return '';
      return String(project.name || project.slug || project.id || '').trim();
    }

    function counts(summary) {
      return summary && summary.counts && typeof summary.counts === 'object' ? summary.counts : {};
    }

    function countEntries(summary) {
      const currentCounts = counts(summary);
      return [
        { id: 'runs', label: 'runs', value: currentCounts.runs, tab: 'runs' },
        { id: 'entities', label: 'entities', value: currentCounts.entities, tab: 'entities' },
        { id: 'findings', label: 'findings', value: currentCounts.findings, tab: 'findings' },
        { id: 'artifacts', label: 'artifacts', value: currentCounts.artifacts, tab: 'artifacts' },
        { id: 'targets', label: 'targets', value: currentCounts.targets, tab: 'details' },
        { id: 'packages', label: 'packages', value: currentCounts.packages, tab: 'packages' },
        { id: 'notes', label: 'notes', value: currentCounts.notes, tab: 'details' },
      ].map(item => ({ ...item, value: Number(item.value || 0) }));
    }

    function targetItems(summary) {
      return summary && Array.isArray(summary.targets) ? summary.targets : [];
    }

    function targetLabel(summary, targetId) {
      const normalized = String(targetId || '').trim();
      if (!normalized) return '';
      const target = targetItems(summary).find(item => String(item && item.id || '') === normalized);
      if (!target) return '';
      const type = String(target.type || 'target').trim() || 'target';
      const value = String(target.value || '').trim();
      return value ? `target ${type}: ${value}` : `target ${type}`;
    }

    function runItems(summary) {
      return summary && Array.isArray(summary.runs) ? summary.runs : [];
    }

    function runById(summary, runId) {
      const normalized = String(runId || '');
      if (!normalized) return null;
      return runItems(summary).find(run => String(run.id || '') === normalized) || null;
    }

    function comparableRuns(summary) {
      return runItems(summary).filter(run => run && run.id);
    }

    function shortRunId(runId) {
      return String(runId || '').trim().slice(0, 8);
    }

    function entityLabelValues(entity) {
      const labels = entity && Array.isArray(entity.labels) ? entity.labels : [];
      return labels
        .map(label => String(label && typeof label === 'object' ? label.label : label || '').trim())
        .filter(Boolean);
    }

    function entityNoteBody(entity) {
      const note = entity && entity.note && typeof entity.note === 'object' ? entity.note : null;
      return note ? String(note.body || '').trim() : '';
    }

    function entityMetadataChips(entity) {
      const chips = entityLabelValues(entity).map(label => ({ label, kind: 'label' }));
      if (entityNoteBody(entity)) chips.push({ label: 'note', kind: 'note' });
      return chips;
    }

    function entityMetadataChipClass(kind = 'label') {
      const normalized = String(kind || '');
      const tone = normalized === 'note'
        ? 'badge-tone-cyan'
        : (normalized === 'success' ? 'badge-tone-green' : 'badge-tone-muted');
      return `project-explorer-metadata-chip badge ${tone}`;
    }

    function entityTitleForEditor(entityType, entity) {
      if (entityType === 'project') {
        return String(entity && (entity.name || entity.slug || entity.id) || 'Project');
      }
      if (entityType === 'finding') {
        return String(entity && (entity.title || entity.raw_line || entity.id) || 'Finding');
      }
      if (entityType === 'run') {
        return String(entity && (entity.command || entity.id) || 'Run');
      }
      if (entityType === 'snapshot') {
        return String(entity && (entity.label || entity.id) || 'Snapshot');
      }
      if (entityType === 'package') {
        return String(entity && (entity.name || entity.id) || 'Package');
      }
      if (entityType === 'run_file_artifact') {
        return String(entity && (entity.display_name || entity.workspace_path || entity.id) || 'Artifact');
      }
      return String(entity && entity.id || 'Entity');
    }

    function entityEditorLabelForType(entityType) {
      if (entityType === 'finding') return 'FINDING';
      if (entityType === 'run') return 'RUN';
      if (entityType === 'snapshot') return 'SNAPSHOT';
      if (entityType === 'run_file_artifact') return 'ARTIFACT';
      if (entityType === 'project') return 'PROJECT';
      if (entityType === 'package') return 'PACKAGE';
      if (entityType === 'workspace_file') return 'WORKSPACE FILE';
      if (entityType === 'target') return 'TARGET';
      return 'METADATA';
    }

    function formatDate(value) {
      if (!value) return '';
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return String(value);
      return date.toLocaleString();
    }

    function formatBytes(value) {
      const bytes = Number(value || 0);
      if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
      const units = ['B', 'KB', 'MB', 'GB'];
      let amount = bytes;
      let unitIndex = 0;
      while (amount >= 1024 && unitIndex < units.length - 1) {
        amount /= 1024;
        unitIndex += 1;
      }
      return `${amount >= 10 || unitIndex === 0 ? amount.toFixed(0) : amount.toFixed(1)} ${units[unitIndex]}`;
    }

    function emptyPanel(text) {
      const empty = document.createElement('div');
      empty.className = 'project-explorer-empty';
      empty.textContent = text;
      return empty;
    }

    function actionCapability(action) {
      const triageActions = new Set([
        'bulk-delete-project-findings',
        'edit-finding-metadata',
      ]);
      const mutateActions = new Set([
        'use',
        'clear',
        'archive',
        'unarchive',
        'delete',
        'edit-project-metadata',
        'bulk-unlink-project-entities',
        'unlink-project-entity',
        'open-entity-picker',
        'entity-picker-add',
        'new-target',
        'edit-target',
        'delete-target',
        'confirm-target',
        'dismiss-target',
        'edit-run-metadata',
        'edit-artifact-metadata',
        'link-last-run',
        'unlink-run',
        'package-edit',
        'package-repackage',
        'package-delete',
        'package-wizard-open',
        'package-wizard-next',
        'new-project-auto-promote-rule',
        'edit-project-auto-promote-rule',
        'save-project-auto-promote-rule',
        'apply-project-auto-promote-rule',
        'delete-project-auto-promote-rule',
      ]);
      const normalized = String(action || '');
      if (triageActions.has(normalized)) return 'triage_findings';
      if (mutateActions.has(normalized)) return 'mutate_projects';
      return '';
    }

    function activeTeamScopeCan(capability) {
      return typeof global.activeTeamScopeCan === 'function'
        ? global.activeTeamScopeCan(capability)
        : true;
    }

    function teamScopeDeniedMessage(capability) {
      const action = capability === 'triage_findings' ? 'triage team findings' : 'change team projects';
      return typeof global.teamScopeDeniedMessage === 'function'
        ? global.teamScopeDeniedMessage(action)
        : `View-only team members can't ${action}. Switch to Personal or ask for operator access.`;
    }

    function metaRow(label, value) {
      const row = document.createElement('div');
      row.className = 'project-explorer-meta-row panel-row';
      const key = document.createElement('span');
      key.textContent = label;
      const val = document.createElement('span');
      val.textContent = String(value || '—');
      row.append(key, val);
      return row;
    }

    function itemRow({ title, meta = '', detail = '', badge = '', chips = [], action = null, accessory = null, forceArticle = false }) {
      const clickableButton = action && !accessory && !forceArticle;
      const row = document.createElement(clickableButton ? 'button' : 'article');
      row.className = `project-explorer-item panel-row${clickableButton ? ' panel-row-clickable' : ''}`;
      let contentHost = row;
      if (action) {
        if (row.tagName === 'BUTTON') {
          row.type = 'button';
          row.classList.add('control-row');
        } else if (accessory || forceArticle) {
          contentHost = document.createElement('button');
          contentHost.type = 'button';
          contentHost.className = 'control-row project-explorer-item-click-target';
        }
        contentHost.dataset.projectAction = action.action;
        Object.entries(action.dataset || {}).forEach(([key, value]) => {
          contentHost.dataset[key] = value;
        });
        ctx.bindProjectRuntimePressable?.(contentHost);
      }
      const main = document.createElement('div');
      main.className = 'project-explorer-item-main';
      const heading = document.createElement('div');
      heading.className = 'project-explorer-item-title';
      heading.textContent = String(title || '');
      main.appendChild(heading);
      if (meta) {
        const metaEl = document.createElement('div');
        metaEl.className = 'project-explorer-item-meta';
        metaEl.textContent = meta;
        main.appendChild(metaEl);
      }
      if (detail) {
        const detailEl = document.createElement('div');
        detailEl.className = 'project-explorer-item-detail';
        detailEl.textContent = detail;
        main.appendChild(detailEl);
      }
      if (Array.isArray(chips) && chips.length) {
        const chipWrap = document.createElement('div');
        chipWrap.className = 'project-explorer-item-chips';
        chips.forEach((chip) => {
          const chipEl = document.createElement('span');
          chipEl.className = entityMetadataChipClass(chip.kind);
          chipEl.textContent = String(chip.label || '');
          chipWrap.appendChild(chipEl);
        });
        main.appendChild(chipWrap);
      }
      contentHost.appendChild(main);
      if (contentHost !== row) row.appendChild(contentHost);
      if (accessory) {
        row.appendChild(accessory);
      } else if (badge) {
        const badgeEl = document.createElement('span');
        badgeEl.className = 'project-explorer-item-badge';
        badgeEl.textContent = badge;
        row.appendChild(badgeEl);
      }
      return row;
    }

    function makeButton(label, action, projectId, role = 'secondary', tone = '') {
      const btn = document.createElement('button');
      btn.type = 'button';
      const classes = ['btn', `btn-${role || 'secondary'}`, 'btn-compact'];
      if (tone) classes.push(`btn-${tone}`);
      btn.className = classes.join(' ');
      btn.textContent = label;
      btn.dataset.projectAction = action;
      if (projectId) btn.dataset.projectId = projectId;
      const capability = actionCapability(action);
      if (capability && !activeTeamScopeCan(capability)) {
        btn.disabled = true;
        btn.title = teamScopeDeniedMessage(capability);
      }
      ctx.bindProjectRuntimePressable?.(btn);
      return btn;
    }

    function groupBy(items, keyFn) {
      const grouped = new Map();
      (Array.isArray(items) ? items : []).forEach((item) => {
        const key = String(keyFn(item) || 'Other');
        if (!grouped.has(key)) grouped.set(key, []);
        grouped.get(key).push(item);
      });
      return grouped;
    }

    function downloadBlobAsAttachment(blob, filename, successMessage = '') {
      ctx.downloadBlobAsAttachment?.(blob, filename);
      if (successMessage) ctx.setProjectWorkspaceMessage?.(successMessage);
    }

    return {
      comparableRuns,
      countEntries,
      counts,
      displayName,
      downloadBlobAsAttachment,
      emptyPanel,
      entityEditorLabelForType,
      entityLabelValues,
      entityMetadataChipClass,
      entityMetadataChips,
      entityNoteBody,
      entityTitleForEditor,
      formatBytes,
      formatDate,
      groupBy,
      itemRow,
      makeButton,
      metaRow,
      runById,
      runItems,
      shortRunId,
      targetItems,
      targetLabel,
    };
  }

  global.DarklabProjectSharedUi = {
    createProjectSharedUiController,
  };
})(globalThis);
