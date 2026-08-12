// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Shared Project UI/data helpers.
// Loaded before shell_chrome.js; shell chrome supplies runtime binding callbacks.

import {
  activeTeamScopeCan as importedActiveTeamScopeCan,
  teamScopeDeniedMessage as importedTeamScopeDeniedMessage,
} from '../team_scope.js';
import {
  verificationStatusLabel as importedVerificationStatusLabel,
  verificationStatusTone as importedVerificationStatusTone,
} from '../findings/finding_triage_bridge.js';

let exportedDarklabProjectSharedUi = null;

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
      const triage = entity && entity.triage && typeof entity.triage === 'object' ? entity.triage : null;
      if (triage) {
        const status = String(triage.verification_status || entity.verification_status || 'not_started');
        if (status && status !== 'not_started') {
          const label = typeof importedVerificationStatusLabel === 'function'
            ? importedVerificationStatusLabel(status)
            : status.replace(/_/g, ' ');
          const tone = typeof importedVerificationStatusTone === 'function'
            ? importedVerificationStatusTone(status)
            : 'muted';
          const kind = tone === 'green' ? 'success' : (tone === 'amber' ? 'warning' : 'label');
          chips.push({ label, kind });
        }
        if (triage.has_remediation) chips.push({ label: 'remediation', kind: 'note' });
        if (triage.has_verification_steps) chips.push({ label: 'verification steps', kind: 'label' });
      }
      return chips;
    }

    function entityMetadataChipClass(kind = 'label') {
      const normalized = String(kind || '');
      const tone = normalized === 'note'
        ? 'badge-tone-cyan'
        : (
            normalized === 'success'
              ? 'badge-tone-green'
              : (normalized === 'warning' ? 'badge-tone-amber' : 'badge-tone-muted')
          );
      return `project-explorer-metadata-chip badge ${tone}`;
    }

    function readableToken(value) {
      return String(value || '')
        .trim()
        .replace(/[_-]+/g, ' ')
        .replace(/\s+/g, ' ');
    }

    function pluralize(label, count) {
      return `${count} ${label}${count === 1 ? '' : 's'}`;
    }

    function selectedEntityCountParts(counts) {
      const source = counts && typeof counts === 'object' ? counts : {};
      const entries = [
        ['run', source.run_ids ?? source.runs],
        ['finding', source.finding_ids ?? source.findings],
        ['artifact', source.artifact_ids ?? source.artifacts],
        ['target', source.target_ids ?? source.targets],
      ];
      return entries
        .map(([label, value]) => pluralize(label, Math.max(0, Number(value || 0))))
        .join(', ');
    }

    function selectedCountsFromIds(selectedEntityIds) {
      const source = selectedEntityIds && typeof selectedEntityIds === 'object' ? selectedEntityIds : {};
      return Object.fromEntries(
        Object.entries(source).map(([key, value]) => [key, Array.isArray(value) ? value.length : 0]),
      );
    }

    function provenanceOrigins(projectLinks) {
      if (!projectLinks || typeof projectLinks !== 'object') return '';
      const counts = projectLinks.counts_by_origin && typeof projectLinks.counts_by_origin === 'object'
        ? projectLinks.counts_by_origin
        : {};
      const origins = Array.isArray(projectLinks.origin_sources) ? projectLinks.origin_sources : Object.keys(counts);
      return { counts, origins };
    }

    function provenanceOriginSummary(projectLinks) {
      const linkOrigins = provenanceOrigins(projectLinks);
      if (!linkOrigins) return '';
      const { counts, origins } = linkOrigins;
      const parts = origins
        .map((origin) => {
          const normalized = String(origin || '').trim();
          if (!normalized) return '';
          const count = Number(counts[normalized] || 0);
          return count > 0 ? `${readableToken(normalized)} (${count})` : readableToken(normalized);
        })
        .filter(Boolean);
      if (parts.length) return parts.join(', ');
      return projectLinks.note ? String(projectLinks.note) : '';
    }

    function provenanceOriginChip(projectLinks) {
      const linkOrigins = provenanceOrigins(projectLinks);
      const detail = provenanceOriginSummary(projectLinks);
      if (!linkOrigins) {
        return {
          label: 'source: not recorded',
          title: 'Project-link origin details were not recorded.',
        };
      }
      const { counts, origins } = linkOrigins;
      const recordedOrigins = origins.map(origin => String(origin || '').trim()).filter(Boolean);
      if (!recordedOrigins.length) {
        return {
          label: 'source: not recorded',
          title: detail || 'Project-link origin details were not recorded.',
        };
      }
      if (recordedOrigins.length === 1) {
        const origin = recordedOrigins[0];
        const count = Number(counts[origin] || 0);
        return {
          label: `source: ${readableToken(origin)}`,
          title: detail || (count > 0 ? `${readableToken(origin)} (${count})` : readableToken(origin)),
        };
      }
      return {
        label: `source: ${recordedOrigins.length} types`,
        title: detail || recordedOrigins.map(readableToken).join(', '),
      };
    }

    function packageImportWarningSummary(importHints) {
      const warnings = importHints && Array.isArray(importHints.warnings) ? importHints.warnings : [];
      if (!warnings.length) return 'none';
      const counts = new Map();
      warnings.forEach((warning) => {
        const code = readableToken(warning && warning.code || 'warning') || 'warning';
        counts.set(code, (counts.get(code) || 0) + 1);
      });
      return Array.from(counts.entries())
        .map(([code, count]) => count > 1 ? `${code} (${count})` : code)
        .join(', ');
    }

    function projectProvenanceSummary(manifest, { fallbackKind = 'export' } = {}) {
      const source = manifest && typeof manifest === 'object' ? manifest : {};
      const provenance = source.provenance && typeof source.provenance === 'object' ? source.provenance : {};
      const build = provenance.build && typeof provenance.build === 'object' ? provenance.build : {};
      const privacy = provenance.privacy && typeof provenance.privacy === 'object' ? provenance.privacy : {};
      const sources = provenance.sources && typeof provenance.sources === 'object' ? provenance.sources : {};
      const importHints = source.import_hints && typeof source.import_hints === 'object' ? source.import_hints : null;
      const rows = [];
      const schema = provenance.schema_version
        ? `v${provenance.schema_version} ${readableToken(provenance.kind || fallbackKind)}`
        : 'not recorded';
      rows.push({ label: 'Schema', value: schema });
      const redaction = build.redaction_mode || privacy.redaction_mode || source.redaction_mode;
      const preset = build.preset || source.preset || build.template_id || source.template_id;
      const privateNotes = Object.prototype.hasOwnProperty.call(privacy, 'private_notes_included')
        ? privacy.private_notes_included
        : source.include_private_notes;
      rows.push({
        label: 'Build',
        value: [
          preset ? readableToken(preset) : '',
          redaction ? readableToken(redaction) : '',
          privateNotes === undefined ? '' : (privateNotes ? 'private notes included' : 'private notes excluded'),
        ].filter(Boolean).join(', ') || 'not recorded',
      });
      const selectedCounts = build.selected_entity_counts && typeof build.selected_entity_counts === 'object'
        ? build.selected_entity_counts
        : selectedCountsFromIds(build.selected_entity_ids || source.selected_entity_ids);
      rows.push({ label: 'Selected', value: selectedEntityCountParts(selectedCounts) || 'not recorded' });
      rows.push({
        label: 'Source links',
        value: provenanceOriginSummary(sources.project_links) || 'not recorded',
      });
      if (importHints) {
        rows.push({
          label: 'Import hints',
          value: `${readableToken(importHints.mode || 'preview only')}; warnings: ${packageImportWarningSummary(importHints)}`,
        });
      }
      const hasRecordedProvenance = schema !== 'not recorded'
        || rows.some(row => row.label !== 'Schema' && row.value && row.value !== 'not recorded');
      const chips = [];
      chips.push({
        label: 'provenance',
        kind: hasRecordedProvenance ? 'success' : 'label',
        title: hasRecordedProvenance ? schema : 'Provenance was not recorded in this package format.',
      });
      const origin = provenanceOriginChip(sources.project_links);
      if (origin) chips.push({ ...origin, kind: 'label' });
      return { rows, chips, hasRecordedProvenance };
    }

    function projectProvenanceSummaryElement(manifest, options = {}) {
      const summary = projectProvenanceSummary(manifest, options);
      const section = document.createElement('section');
      section.className = 'project-provenance-summary';
      const heading = document.createElement('h3');
      heading.textContent = options.title || 'Provenance summary';
      section.appendChild(heading);
      const rows = document.createElement('div');
      rows.className = 'project-provenance-summary-rows';
      summary.rows.forEach((item) => {
        const row = document.createElement('div');
        row.className = 'project-provenance-summary-row';
        const label = document.createElement('span');
        label.textContent = item.label;
        const value = document.createElement('strong');
        value.textContent = item.value || 'not recorded';
        row.append(label, value);
        rows.appendChild(row);
      });
      section.appendChild(rows);
      return section;
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
        'create-manual-finding',
        'edit-manual-finding',
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
      const can = typeof importedActiveTeamScopeCan === 'function' ? importedActiveTeamScopeCan : null;
      return typeof can === 'function' ? can(capability) : true;
    }

    function teamScopeDeniedMessage(capability) {
      const action = capability === 'triage_findings' ? 'triage team findings' : 'change team projects';
      const denied = typeof importedTeamScopeDeniedMessage === 'function' ? importedTeamScopeDeniedMessage : null;
      return typeof denied === 'function'
        ? denied(action)
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
          if (chip.title) chipEl.title = String(chip.title);
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

    function downloadUrlAsAttachment(url, filename = '', successMessage = '') {
      ctx.downloadUrlAsAttachment?.(url, filename ? { filename } : {});
      if (successMessage) ctx.setProjectWorkspaceMessage?.(successMessage);
    }

    return {
      comparableRuns,
      countEntries,
      counts,
      displayName,
      downloadBlobAsAttachment,
      downloadUrlAsAttachment,
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
      projectProvenanceSummary,
      projectProvenanceSummaryElement,
      runById,
      runItems,
      shortRunId,
      targetItems,
      targetLabel,
    };
  }

  const DarklabProjectSharedUi = {
    createProjectSharedUiController,
  };
  exportedDarklabProjectSharedUi = DarklabProjectSharedUi;
})(globalThis);

export {
  exportedDarklabProjectSharedUi as DarklabProjectSharedUi,};
