// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Project evidence package controller.
// Loaded before shell_chrome.js; shell chrome supplies Projects state and shared UI helpers.

import { enhanceAppSelects as importedEnhanceAppSelects } from '../../ui/ui_helpers.js';
import { getAppConfig as importedGetAppConfig } from '../../core/config.js';

let exportedDarklabProjectPackages = null;

(function initProjectPackages(global) {
  if (typeof document === 'undefined') return;

  function createProjectPackagesController(context) {
    const ctx = context || {};
    let wizard = null;
    const downloadTimers = new WeakMap();
    const packageJobPollMs = 750;
    const appConfig = typeof importedGetAppConfig === 'function' ? importedGetAppConfig : () => ({});
    const defaultPackagePresets = Object.freeze([
      Object.freeze({
        id: 'evidence',
        label: 'Evidence',
        description: 'Reviewed findings, related transcripts, targets, and selected raw artifacts.',
        name_suffix: 'evidence',
        redaction_mode: 'raw',
        include_artifacts: true,
        include_private_notes: false,
        labels: Object.freeze([]),
        notes: '',
        selection: Object.freeze({
          runs: 'all',
          transcripts: 'with_findings',
          findings: 'non_false_positive',
          artifacts: 'selectable',
          targets: 'all',
        }),
      }),
      Object.freeze({
        id: 'summary',
        label: 'Summary',
        description: 'Findings, targets, and metadata without transcript HTML or raw artifacts.',
        name_suffix: 'summary',
        redaction_mode: 'raw',
        include_artifacts: false,
        include_private_notes: false,
        labels: Object.freeze([]),
        notes: '',
        selection: Object.freeze({
          runs: 'all',
          transcripts: 'none',
          findings: 'non_false_positive',
          artifacts: 'none',
          targets: 'all',
        }),
      }),
      Object.freeze({
        id: 'full',
        label: 'Full Archive',
        description: 'All linked runs, findings, targets, and available raw artifacts.',
        name_suffix: 'full',
        redaction_mode: 'raw',
        include_artifacts: true,
        include_private_notes: false,
        labels: Object.freeze([]),
        notes: '',
        selection: Object.freeze({
          runs: 'all',
          transcripts: 'all',
          findings: 'all',
          artifacts: 'selectable',
          targets: 'all',
        }),
      }),
      Object.freeze({
        id: 'redacted',
        label: 'Redacted',
        description: 'Metadata, findings, targets, and transcripts with sensitive fields redacted.',
        name_suffix: 'redacted',
        redaction_mode: 'redacted',
        include_artifacts: true,
        include_private_notes: false,
        labels: Object.freeze([]),
        notes: '',
        selection: Object.freeze({
          runs: 'all',
          transcripts: 'with_findings',
          findings: 'non_false_positive',
          artifacts: 'selectable',
          targets: 'all',
        }),
      }),
    ]);
    const packagePresetSelectionDefaults = Object.freeze({
      runs: 'none',
      transcripts: 'none',
      findings: 'none',
      artifacts: 'none',
      targets: 'none',
    });
    let packagePresetCatalog = defaultPackagePresets.map(preset => ({ ...preset, selection: { ...preset.selection } }));
    let packagePresetCatalogPromise = null;
    let packagePresetCatalogLoaded = false;
    let packagePresetCatalogError = '';

    function selectedProjectId() {
      return String(ctx.getSelectedProjectId?.() || '');
    }

    function summaryFor(projectId = selectedProjectId()) {
      return ctx.projectSummary?.(projectId) || null;
    }

    function items(summary) {
      return summary && Array.isArray(summary.packages) ? summary.packages : [];
    }

    function mergePackageIntoSummary(projectId, pkg) {
      const packageId = String(pkg && pkg.id || '');
      const summary = summaryFor(projectId);
      if (!packageId || !summary || !Array.isArray(summary.packages)) return;
      let replaced = false;
      summary.packages = summary.packages.map((item) => {
        if (String(item && item.id || '') !== packageId) return item;
        replaced = true;
        return { ...item, ...pkg };
      });
      if (!replaced) summary.packages = [
        { ...pkg },
        ...summary.packages,
      ];
    }

    function selectableArtifactItems(summary) {
      return ctx.projectArtifactItems(summary).filter(artifact => ctx.projectArtifactStatus(artifact) === 'available');
    }

    function safePackagePresetText(value, fallback = '') {
      return String(value || fallback || '').trim();
    }

    function normalizePackagePresetEntry(entry) {
      if (!entry || typeof entry !== 'object') return null;
      const id = safePackagePresetText(entry.id).toLowerCase();
      if (!/^[a-z0-9][a-z0-9_-]{0,31}$/.test(id)) return null;
      const selection = entry.selection && typeof entry.selection === 'object' ? entry.selection : {};
      return {
        id,
        label: safePackagePresetText(entry.label, id.replace(/_/g, ' ')) || id,
        description: safePackagePresetText(entry.description),
        name_suffix: safePackagePresetText(entry.name_suffix, id),
        redaction_mode: safePackagePresetText(entry.redaction_mode) === 'redacted' ? 'redacted' : 'raw',
        include_artifacts: !!entry.include_artifacts,
        include_private_notes: !!entry.include_private_notes,
        labels: Array.isArray(entry.labels)
          ? entry.labels.map(label => safePackagePresetText(label)).filter(Boolean)
          : [],
        notes: safePackagePresetText(entry.notes),
        selection: {
          ...packagePresetSelectionDefaults,
          ...Object.fromEntries(
            Object.entries(selection)
              .map(([key, value]) => [key, safePackagePresetText(value).toLowerCase()])
              .filter(([key, value]) => key in packagePresetSelectionDefaults && value),
          ),
        },
      };
    }

    function normalizePackagePresetCatalog(data) {
      const rawPresets = Array.isArray(data?.presets) ? data.presets : [];
      const presets = [];
      const seen = new Set();
      rawPresets.forEach((entry) => {
        const preset = normalizePackagePresetEntry(entry);
        if (!preset || seen.has(preset.id)) return;
        seen.add(preset.id);
        presets.push(preset);
      });
      return presets.length ? presets : defaultPackagePresets.map(preset => ({ ...preset, selection: { ...preset.selection } }));
    }

    function packagePresets() {
      return packagePresetCatalog.length
        ? packagePresetCatalog
        : defaultPackagePresets.map(preset => ({ ...preset, selection: { ...preset.selection } }));
    }

    function packagePresetById(preset, { fallback = true } = {}) {
      const presetId = safePackagePresetText(preset).toLowerCase();
      const found = packagePresets().find(item => item.id === presetId) || null;
      if (found || !fallback) return found;
      return packagePresets()[0] || defaultPackagePresets[0];
    }

    async function ensurePackagePresetCatalog() {
      if (packagePresetCatalogLoaded) return packagePresets();
      if (packagePresetCatalogPromise) return packagePresetCatalogPromise;
      if (typeof ctx.apiFetch !== 'function') return packagePresets();
      packagePresetCatalogPromise = ctx.apiFetch('/projects/package-presets', { cache: 'no-store' })
        .then(resp => readJsonResponse(resp, 'Unable to load package presets.'))
        .then((data) => {
          packagePresetCatalog = normalizePackagePresetCatalog(data);
          packagePresetCatalogError = '';
          return packagePresetCatalog;
        })
        .catch((err) => {
          packagePresetCatalog = defaultPackagePresets.map(preset => ({ ...preset, selection: { ...preset.selection } }));
          packagePresetCatalogError = err?.message || 'Package presets could not be loaded.';
          return packagePresetCatalog;
        })
        .finally(() => {
          packagePresetCatalogLoaded = true;
          packagePresetCatalogPromise = null;
        });
      return packagePresetCatalogPromise;
    }

    function packageDownloadName(pkg) {
      const raw = String(pkg && pkg.name || 'evidence-package').trim().toLowerCase();
      const safe = raw.replace(/[^a-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '');
      return `${safe || 'evidence-package'}.zip`;
    }

    function byId(summary, packageId) {
      const normalized = String(packageId || '').trim();
      if (!normalized) return null;
      return items(summary).find(item => String(item && item.id || '') === normalized) || null;
    }

    function manifestFor(pkg) {
      return pkg && pkg.manifest && typeof pkg.manifest === 'object' ? pkg.manifest : {};
    }

    function countsText(pkg) {
      const counts = manifestFor(pkg).counts || {};
      return [
        ['run', counts.runs],
        ['finding', counts.findings],
        ['artifact', counts.artifacts],
        ['target', counts.targets],
      ].map(([label, value]) => {
        const count = Math.max(0, Number(value || 0));
        return `${count} ${label}${count === 1 ? '' : 's'}`;
      }).join(' · ');
    }

    function metaText(pkg) {
      const manifest = manifestFor(pkg);
      const preset = String(pkg && pkg.preset || manifest.preset || 'custom');
      const redaction = String(pkg && pkg.redaction_mode || manifest.redaction_mode || 'raw');
      const estimate = manifest.estimated_archive && typeof manifest.estimated_archive === 'object'
        ? Number(manifest.estimated_archive.estimated_uncompressed_bytes || 0)
        : 0;
      const includeArtifacts = pkg && Object.prototype.hasOwnProperty.call(pkg, 'include_artifacts')
        ? !!pkg.include_artifacts
        : !!manifest.options?.raw_artifacts;
      const parts = [preset, redaction === 'redacted' ? 'redacted' : 'raw'];
      if (estimate > 0) parts.push(`~${ctx.formatBytes(estimate)}`);
      parts.push(includeArtifacts ? 'includes artifacts' : 'metadata only');
      return parts.filter(Boolean).join(' · ');
    }

    function packageChips(pkg) {
      const chips = ctx.entityMetadataChips(pkg);
      const summary = ctx.projectProvenanceSummary?.(manifestFor(pkg), { fallbackKind: 'evidence_package' });
      if (summary?.chips?.length) {
        const provenanceChip = summary.chips.find(chip => String(chip.label || '').startsWith('source:'))
          || summary.chips[0];
        if (provenanceChip) chips.push(provenanceChip);
      }
      return chips;
    }

    function openManifest(pkg) {
      if (!ctx.manifestOverlay || !ctx.manifestJson) {
        throw new Error('Manifest preview is not available.');
      }
      const name = String(pkg && pkg.name || 'package').trim() || 'package';
      const manifest = manifestFor(pkg);
      if (ctx.manifestTitle) ctx.manifestTitle.textContent = `${name} manifest`;
      if (ctx.manifestSummary) {
        ctx.manifestSummary.replaceChildren();
        ctx.manifestSummary.appendChild(
          ctx.projectProvenanceSummaryElement?.(manifest, { fallbackKind: 'evidence_package' })
            || document.createElement('div'),
        );
      }
      ctx.manifestJson.textContent = JSON.stringify(manifest, null, 2);
      ctx.manifestOverlay.classList.remove('u-hidden');
      ctx.manifestOverlay.classList.add('open');
      ctx.manifestOverlay.setAttribute('aria-hidden', 'false');
      ctx.focusProjectNestedSheet?.(
        ctx.manifestOverlay,
        ctx.manifestOverlay.querySelector('.project-package-manifest-close'),
      );
    }

    function closeManifest() {
      if (!ctx.manifestOverlay) return;
      ctx.manifestOverlay.classList.add('u-hidden');
      ctx.manifestOverlay.classList.remove('open');
      ctx.manifestOverlay.setAttribute('aria-hidden', 'true');
      if (ctx.manifestSummary) ctx.manifestSummary.replaceChildren();
      if (ctx.manifestJson) ctx.manifestJson.textContent = '';
      ctx.syncProjectWorkspaceNestedSuppression?.();
    }

    function isManifestOpen() {
      return !!(ctx.manifestOverlay && ctx.manifestOverlay.classList.contains('open'));
    }

    function selectionPolicy(presetConfig, key) {
      const policy = safePackagePresetText(presetConfig?.selection?.[key]).toLowerCase();
      return policy || packagePresetSelectionDefaults[key] || 'none';
    }

    function presetDefaults(preset, summary, findings) {
      const presetConfig = packagePresetById(preset);
      const normalizedPreset = presetConfig.id;
      const runs = ctx.projectRunItems(summary);
      const artifacts = ctx.projectArtifactItems(summary);
      const targets = ctx.projectTargetItems(summary);
      const findingItems = Array.isArray(findings) ? findings : [];
      const runIds = runs.map(run => String(run.id || '')).filter(Boolean);
      const findingRunIds = new Set(findingItems.map(finding => String(finding.run_id || '')).filter(Boolean));
      const redactionMode = presetConfig.redaction_mode === 'redacted' ? 'redacted' : 'raw';
      const includeArtifacts = !!presetConfig.include_artifacts && ctx.projectFilesEnabled();
      let selectedFindings = [];
      const findingPolicy = selectionPolicy(presetConfig, 'findings');
      if (findingPolicy === 'all') {
        selectedFindings = findingItems;
      } else if (findingPolicy === 'non_false_positive') {
        selectedFindings = findingItems.filter(finding => String(finding.review_state || 'new') !== 'false_positive');
      }
      let selectedTranscriptRunIds = [];
      const transcriptPolicy = selectionPolicy(presetConfig, 'transcripts');
      if (transcriptPolicy === 'all') {
        selectedTranscriptRunIds = runIds;
      } else if (transcriptPolicy === 'with_findings') {
        selectedTranscriptRunIds = runIds.filter(runId => findingRunIds.has(runId));
      }
      let selectedArtifactIds = [];
      const artifactPolicy = selectionPolicy(presetConfig, 'artifacts');
      if (includeArtifacts && artifactPolicy === 'all') {
        selectedArtifactIds = artifacts.map(artifact => String(artifact.id || '')).filter(Boolean);
      } else if (includeArtifacts && artifactPolicy === 'selectable') {
        selectedArtifactIds = selectableArtifactItems(summary).map(artifact => String(artifact.id || '')).filter(Boolean);
      }
      return {
        preset: normalizedPreset,
        step: 1,
        includeArtifacts,
        redactionMode,
        includePrivateNotes: !!presetConfig.include_private_notes,
        name: '',
        description: '',
        labels: Array.isArray(presetConfig.labels) ? presetConfig.labels.join(', ') : '',
        notes: safePackagePresetText(presetConfig.notes),
        collapsedRunIds: new Set(),
        selection: {
          runIds: new Set(selectionPolicy(presetConfig, 'runs') === 'all' ? runIds : []),
          transcriptRunIds: new Set(selectedTranscriptRunIds),
          findingIds: new Set(selectedFindings.map(finding => String(finding.id || '')).filter(Boolean)),
          artifactIds: new Set(selectedArtifactIds),
          targetIds: new Set(
            selectionPolicy(presetConfig, 'targets') === 'all'
              ? targets.map(target => String(target.id || '')).filter(Boolean)
              : [],
          ),
        },
      };
    }

    function isWizardActive(projectId = selectedProjectId()) {
      return !!(wizard && String(wizard.projectId || '') === String(projectId || ''));
    }

    function isWizardOpen() {
      return !!(ctx.wizardOverlay && ctx.wizardOverlay.classList.contains('open'));
    }

    function updateWizardField(field, value) {
      if (!wizard) return false;
      if (field === 'name') {
        wizard.name = String(value || '');
        wizard.nameTouched = true;
        return true;
      }
      if (field === 'description') {
        wizard.description = String(value || '');
        wizard.descriptionTouched = true;
        return true;
      }
      if (field === 'labels') {
        wizard.labels = String(value || '');
        wizard.labelsTouched = true;
        return true;
      }
      if (field === 'notes') {
        wizard.notes = String(value || '');
        wizard.notesTouched = true;
        return true;
      }
      return false;
    }

    function syncVisibleWizardFields() {
      if (!wizard || !ctx.wizardBody) return;
      ctx.wizardBody.querySelectorAll('[data-project-package-field]').forEach((fieldEl) => {
        const field = String(fieldEl.dataset.projectPackageField || '');
        if (field === 'redaction_mode') {
          const mode = String(fieldEl.value || 'raw') === 'redacted' ? 'redacted' : 'raw';
          wizard.redactionMode = mode;
          wizard.redactionTouched = true;
          return;
        }
        updateWizardField(field, fieldEl.value);
      });
    }

    function hideWizardOverlay() {
      if (!ctx.wizardOverlay) return;
      ctx.wizardOverlay.classList.add('u-hidden');
      ctx.wizardOverlay.classList.remove('open');
      ctx.wizardOverlay.setAttribute('aria-hidden', 'true');
      if (ctx.wizardBody) ctx.wizardBody.replaceChildren();
      ctx.syncProjectWorkspaceNestedSuppression?.();
    }

    function renderWizardModal({ focus = false, scrollTop = null } = {}) {
      if (!wizard || !ctx.wizardOverlay || !ctx.wizardBody) {
        hideWizardOverlay();
        return;
      }
      const projectId = String(wizard.projectId || selectedProjectId() || '');
      if (!projectId) {
        hideWizardOverlay();
        return;
      }
      ctx.wizardBody.replaceChildren();
      renderWizard(ctx.wizardBody, projectId, summaryFor(projectId));
      ctx.wizardOverlay.classList.remove('u-hidden');
      ctx.wizardOverlay.classList.add('open');
      ctx.wizardOverlay.setAttribute('aria-hidden', 'false');
      ctx.installProjectMobileKeyboardGuards?.();
      const enhanceAppSelects = (typeof importedEnhanceAppSelects !== 'undefined' && importedEnhanceAppSelects)
        || null;
      if (typeof enhanceAppSelects === 'function') {
        enhanceAppSelects(ctx.wizardBody);
      }
      if (Number.isFinite(scrollTop)) {
        const scrollBody = ctx.wizardBody.querySelector('.project-package-wizard-body');
        if (scrollBody) scrollBody.scrollTop = Number(scrollTop);
      }
      if (focus) {
        ctx.focusProjectNestedSheet?.(
          ctx.wizardOverlay,
          ctx.wizardBody.querySelector('[data-project-action="package-wizard-cancel"]'),
        );
      } else {
        ctx.syncProjectWorkspaceNestedSuppression?.();
      }
    }

    function suggestedName(project, preset) {
      const slug = String(project && (project.slug || project.name) || 'project').trim().toLowerCase()
        .replace(/[^a-z0-9._-]+/g, '-')
        .replace(/^-+|-+$/g, '') || 'project';
      const today = new Date().toISOString().slice(0, 10);
      const presetConfig = packagePresetById(preset, { fallback: false });
      const suffix = safePackagePresetText(presetConfig?.name_suffix, preset || 'evidence') || 'evidence';
      return `${slug}-${today}-${suffix}`;
    }

    function reapplyPresetDefaults(projectId, { preserveTouched = true } = {}) {
      if (!wizard || !isWizardActive(projectId)) return;
      syncVisibleWizardFields();
      const previous = wizard;
      const refreshed = presetDefaults(previous.preset, summaryFor(projectId), ctx.projectFindingItems(projectId));
      refreshed.step = previous.step || refreshed.step;
      refreshed.collapsedRunIds = previous.collapsedRunIds || new Set();
      refreshed.notice = previous.notice || '';
      refreshed.noticeError = !!previous.noticeError;
      refreshed.nameTouched = !!previous.nameTouched;
      refreshed.descriptionTouched = !!previous.descriptionTouched;
      refreshed.labelsTouched = !!previous.labelsTouched;
      refreshed.notesTouched = !!previous.notesTouched;
      refreshed.redactionTouched = !!previous.redactionTouched;
      refreshed.includeArtifactsTouched = !!previous.includeArtifactsTouched;
      refreshed.privateNotesTouched = !!previous.privateNotesTouched;
      if (preserveTouched && previous.nameTouched) {
        refreshed.name = previous.name || '';
      } else {
        refreshed.name = suggestedName(ctx.selectedProject?.(), refreshed.preset);
      }
      if (preserveTouched && previous.descriptionTouched) refreshed.description = previous.description || '';
      if (preserveTouched && previous.labelsTouched) refreshed.labels = previous.labels || '';
      if (preserveTouched && previous.notesTouched) refreshed.notes = previous.notes || '';
      if (preserveTouched && previous.redactionTouched) refreshed.redactionMode = previous.redactionMode || refreshed.redactionMode;
      if (preserveTouched && previous.includeArtifactsTouched) refreshed.includeArtifacts = !!previous.includeArtifacts;
      if (preserveTouched && previous.privateNotesTouched) refreshed.includePrivateNotes = !!previous.includePrivateNotes;
      wizard = { projectId: String(projectId || ''), ...refreshed };
    }

    function refreshWizardAfterAsyncLoad(projectId) {
      if (!isWizardActive(projectId)) return;
      reapplyPresetDefaults(projectId);
      ctx.renderProjectExplorer?.();
      renderWizardModal();
    }

    function openWizard(projectId, preset = 'evidence') {
      const summary = summaryFor(projectId);
      const findings = ctx.projectFindingItems(projectId);
      wizard = {
        projectId: String(projectId || ''),
        ...presetDefaults(preset, summary, findings),
        nameTouched: false,
        descriptionTouched: false,
        labelsTouched: false,
        notesTouched: false,
        redactionTouched: false,
        includeArtifactsTouched: false,
        privateNotesTouched: false,
      };
      wizard.name = suggestedName(ctx.selectedProject?.(), wizard.preset);
      ctx.setProjectWorkspaceMessage?.('');
      ensurePackagePresetCatalog().then(() => {
        refreshWizardAfterAsyncLoad(projectId);
      });
      if (!ctx.projectFindingsLoaded(projectId)) {
        ctx.loadProjectFindings(projectId).then(() => {
          refreshWizardAfterAsyncLoad(projectId);
        }).catch(() => {});
      }
      if (typeof ctx.loadAllProjectArtifacts === 'function' && Number(summary?.counts?.artifacts || 0) > 0) {
        ctx.loadAllProjectArtifacts(projectId, summary).then(() => {
          refreshWizardAfterAsyncLoad(projectId);
        }).catch(() => {});
      }
      ctx.renderProjectExplorer?.();
      renderWizardModal({ focus: true });
    }

    function manifestIds(manifest, key, fallbackItems = []) {
      const selected = manifest && typeof manifest === 'object' ? manifest.selected_entity_ids : null;
      if (selected && typeof selected === 'object' && Array.isArray(selected[key])) {
        return new Set(selected[key].map(value => String(value || '')).filter(Boolean));
      }
      return new Set(fallbackItems.map(item => String(item && item.id || '')).filter(Boolean));
    }

    function openWizardFromPackage(projectId, pkg) {
      const summary = summaryFor(projectId);
      const manifest = pkg && typeof pkg.manifest === 'object' && pkg.manifest ? pkg.manifest : {};
      const preset = String(manifest.preset || pkg?.preset || 'custom') || 'custom';
      const redactionMode = String(pkg?.redaction_mode || manifest.redaction_mode || 'raw') === 'redacted'
        ? 'redacted'
        : 'raw';
      const options = manifest.options && typeof manifest.options === 'object' ? manifest.options : {};
      const includeArtifacts = !ctx.projectFilesEnabled()
        ? false
        : Boolean(pkg?.include_artifacts ?? options.raw_artifacts ?? options.redacted_artifact_derivatives);
      const selectedRunIds = manifestIds(manifest, 'run_ids', ctx.projectRunItems(summary));
      wizard = {
        projectId: String(projectId || ''),
        preset,
        step: 2,
        includeArtifacts,
        redactionMode,
        includePrivateNotes: !!manifest.include_private_notes,
        name: String(pkg?.name || suggestedName(ctx.selectedProject?.(), preset)),
        description: String(pkg?.description || ''),
        labels: ctx.entityLabelValues(pkg).join(', '),
        notes: ctx.entityNoteBody(pkg),
        collapsedRunIds: new Set(),
        selection: {
          runIds: selectedRunIds,
          transcriptRunIds: manifestIds(
            manifest,
            'transcript_run_ids',
            [...selectedRunIds].map(id => ({ id })),
          ),
          findingIds: manifestIds(manifest, 'finding_ids', ctx.projectFindingItems(projectId)),
          artifactIds: manifestIds(manifest, 'artifact_ids', ctx.projectArtifactItems(summary)),
          targetIds: manifestIds(manifest, 'target_ids', ctx.projectTargetItems(summary)),
        },
      };
      ctx.setProjectWorkspaceMessage?.('');
      if (!ctx.projectFindingsLoaded(projectId)) {
        ctx.loadProjectFindings(projectId).then(() => {
          if (isWizardActive(projectId)) {
            ctx.renderProjectExplorer?.();
            renderWizardModal();
          }
        }).catch(() => {});
      }
      if (typeof ctx.loadAllProjectArtifacts === 'function' && Number(summary?.counts?.artifacts || 0) > 0) {
        ctx.loadAllProjectArtifacts(projectId, summary).then(() => {
          if (isWizardActive(projectId)) {
            ctx.renderProjectExplorer?.();
            renderWizardModal();
          }
        }).catch(() => {});
      }
      ctx.setWorkspaceTab?.('packages');
      ctx.renderProjectExplorer?.();
      renderWizardModal({ focus: true });
    }

    function closeWizard({ render = true } = {}) {
      wizard = null;
      hideWizardOverlay();
      ctx.setProjectWorkspaceMessage?.('');
      if (render) ctx.renderProjectExplorer?.();
    }

    function accessory(projectId, pkg) {
      const packageId = String(pkg && pkg.id || '');
      const wrap = document.createElement('div');
      wrap.className = 'project-package-accessory';
      const actions = document.createElement('div');
      actions.className = 'project-package-actions';
      [
        ['Edit', 'package-edit'],
        ['Download', 'package-download'],
        ['Re-package', 'package-repackage'],
        ['Manifest', 'package-manifest'],
        ['Delete', 'package-delete', 'danger'],
      ].forEach(([label, action, tone]) => {
        const btn = ctx.makeProjectButton(label, action, projectId, 'secondary', tone || '');
        btn.classList.add('project-package-action');
        btn.dataset.packageId = packageId;
        ctx.bindProjectRuntimePressable?.(btn);
        actions.appendChild(btn);
      });
      wrap.appendChild(actions);
      return wrap;
    }

    function selectionCheckbox({ kind, id, label, detail = '', checked = true, disabled = false, dataset = {} }) {
      const wrap = document.createElement('label');
      wrap.className = 'project-package-selection-row' + (disabled ? ' is-disabled' : '');
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.checked = checked;
      input.disabled = disabled;
      input.value = String(id || '');
      input.dataset.projectPackageSelection = kind;
      Object.entries(dataset || {}).forEach(([key, value]) => {
        input.dataset[key] = String(value || '');
      });
      const text = document.createElement('span');
      text.className = 'project-package-selection-text';
      const strong = document.createElement('strong');
      strong.textContent = label || String(id || '');
      const small = document.createElement('small');
      small.textContent = detail || String(id || '');
      text.append(strong, small);
      wrap.append(input, text);
      return wrap;
    }

    function bulkSelectionMenu(label, mode, projectId) {
      const details = document.createElement('details');
      details.className = 'project-package-bulk-menu';
      const summary = document.createElement('summary');
      summary.className = 'btn btn-secondary btn-compact project-package-bulk-menu-trigger';
      summary.textContent = label;
      summary.setAttribute('role', 'button');
      details.appendChild(summary);
      const menu = document.createElement('div');
      menu.className = 'project-package-bulk-menu-list dropdown-surface';
      menu.setAttribute('role', 'menu');
      [
        ['transcript', 'Transcripts'],
        ['finding', 'Findings'],
        ['target', 'Targets'],
      ].forEach(([kind, itemLabel]) => {
        const item = document.createElement('button');
        item.type = 'button';
        item.className = 'dropdown-item dropdown-item-compact';
        item.dataset.projectAction = 'package-wizard-bulk-selection';
        item.dataset.projectId = projectId;
        item.dataset.bulkMode = mode;
        item.dataset.bulkKind = kind;
        item.textContent = itemLabel;
        menu.appendChild(item);
      });
      details.appendChild(menu);
      details.addEventListener('focusout', (event) => {
        const nextFocus = event.relatedTarget;
        if (!nextFocus || !details.contains(nextFocus)) details.open = false;
      });
      return details;
    }

    function runChildIds(runId, projectId, summary) {
      const normalizedRunId = String(runId || '');
      const findings = ctx.projectFindingItems(projectId)
        .filter(finding => String(finding && finding.run_id || '') === normalizedRunId);
      const artifacts = ctx.projectArtifactItems(summary)
        .filter(artifact => String(artifact && artifact.run_id || '') === normalizedRunId);
      return {
        findingIds: findings.map(finding => String(finding.id || '')).filter(Boolean),
        artifactIds: artifacts.map(artifact => String(artifact.id || '')).filter(Boolean),
        selectableArtifactIds: artifacts
          .filter(artifact => ctx.projectArtifactStatus(artifact) === 'available')
          .map(artifact => String(artifact.id || '')).filter(Boolean),
      };
    }

    function appendRunChildSelections(body, title, childItems, kind, runId, labelFn, detailFn) {
      if (!childItems.length) return;
      const group = document.createElement('div');
      group.className = 'project-package-run-child-group';
      const heading = document.createElement('h4');
      heading.textContent = `${title} (${childItems.length})`;
      group.appendChild(heading);
      const selected = setFor(kind);
      childItems.forEach((item) => {
        const id = String(item.id || '');
        const row = selectionCheckbox({
          kind,
          id,
          label: labelFn(item),
          detail: detailFn(item),
          checked: selected.has(id),
          disabled: kind === 'transcript' && !setFor('run').has(id),
          dataset: { runId },
        });
        row.classList.add('project-package-selection-row-nested');
        group.appendChild(row);
      });
      body.appendChild(group);
    }

    function renderRunSelections(section, projectId, summary) {
      const runs = ctx.projectRunItems(summary);
      const selectedRuns = setFor('run');
      const selectedTranscripts = setFor('transcript');
      runs.forEach((run) => {
        const runId = String(run.id || '');
        const runWrap = document.createElement('div');
        runWrap.className = 'project-package-run-selection';
        const collapsed = !!(wizard?.collapsedRunIds?.has(runId));
        runWrap.classList.toggle('is-collapsed', collapsed);
        const header = document.createElement('div');
        header.className = 'project-package-run-header';
        header.appendChild(selectionCheckbox({
          kind: 'run',
          id: runId,
          label: run.command || runId,
          detail: `${ctx.formatDate(run.started)} · ${Number(run.output_line_count || 0).toLocaleString()} output lines`,
          checked: selectedRuns.has(runId),
        }));
        const toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'toggle-btn project-package-run-toggle';
        toggle.dataset.projectPackageRunToggle = runId;
        toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
        toggle.setAttribute('aria-label', collapsed ? 'Show selections' : 'Hide selections');
        toggle.title = collapsed ? 'Show selections' : 'Hide selections';
        toggle.textContent = '▾';
        ctx.bindProjectRuntimePressable?.(toggle);
        header.appendChild(toggle);
        runWrap.appendChild(header);
        const body = document.createElement('div');
        body.className = 'project-package-run-body';
        body.hidden = collapsed;
        body.appendChild(selectionCheckbox({
          kind: 'transcript',
          id: runId,
          label: 'Include transcript HTML',
          detail: `${run.command || runId}`,
          checked: selectedTranscripts.has(runId),
          disabled: !selectedRuns.has(runId),
          dataset: { runId },
        }));
        appendRunChildSelections(
          body,
          'Findings',
          ctx.projectFindingItems(projectId).filter(finding => String(finding.run_id || '') === runId),
          'finding',
          runId,
          finding => finding.title || finding.raw_line || finding.id,
          finding => finding.raw_line || `line ${finding.line_number || 0}`,
        );
        appendRunChildSelections(
          body,
          'Artifacts',
          ctx.projectArtifactItems(summary).filter(artifact => String(artifact.run_id || '') === runId),
          'artifact',
          runId,
          artifact => artifact.display_name || artifact.workspace_path || artifact.id,
          artifact => ctx.projectArtifactDetail(artifact),
        );
        runWrap.appendChild(body);
        section.appendChild(runWrap);
      });
    }

    function selectionKind(kind, config) {
      return {
        ...config,
        missing(projectId, summary) {
          const current = new Set((config.items(projectId, summary) || [])
            .map(item => String(item && item.id || '')).filter(Boolean));
          return Array.from(setFor(kind)).filter(id => !current.has(String(id || '')));
        },
      };
    }

    const kindConfigs = {
      run: selectionKind('run', {
        label: 'run',
        items: (projectId, summary) => ctx.projectRunItems(summary),
        set: state => state.selection.runIds,
      }),
      transcript: selectionKind('transcript', {
        label: 'transcript',
        items: (projectId, summary) => ctx.projectRunItems(summary),
        set: state => state.selection.transcriptRunIds,
      }),
      finding: selectionKind('finding', {
        label: 'finding',
        items: projectId => ctx.projectFindingItems(projectId),
        set: state => state.selection.findingIds,
      }),
      artifact: selectionKind('artifact', {
        label: 'artifact',
        items: (projectId, summary) => ctx.projectArtifactItems(summary),
        set: state => state.selection.artifactIds,
      }),
      target: selectionKind('target', {
        label: 'target',
        items: (projectId, summary) => ctx.projectTargetItems(summary),
        set: state => state.selection.targetIds,
      }),
    };

    function kindConfig(kind) {
      return kindConfigs[String(kind || '')] || null;
    }

    function setFor(kind) {
      const config = kindConfig(kind);
      if (!wizard || !config) return new Set();
      return config.set(wizard) || new Set();
    }

    function missingIds(kind, projectId, summary) {
      const config = kindConfig(kind);
      return config ? config.missing(projectId, summary) : [];
    }

    function pruneUnavailableSelections(selectionItems) {
      if (!wizard || !Array.isArray(selectionItems)) return 0;
      let removed = 0;
      selectionItems.forEach((item) => {
        const kind = String(item.kind || '');
        const selected = setFor(kind);
        if (selected.delete(String(item.id || ''))) removed += 1;
      });
      return removed;
    }

    function skippedPreview(projectId, summary) {
      const skipped = [];
      ['run', 'finding', 'target'].forEach((kind) => {
        const config = kindConfig(kind);
        missingIds(kind, projectId, summary).forEach((id) => {
          skipped.push({
            kind,
            id,
            label: `${config.label} ${id}`,
            reason: 'No longer linked to this project.',
          });
        });
      });
      const transcriptConfig = kindConfig('transcript');
      missingIds('transcript', projectId, summary).forEach((id) => {
        skipped.push({
          kind: 'transcript',
          id,
          label: `${transcriptConfig.label} ${id}`,
          reason: 'Transcript run is no longer linked to this project.',
        });
      });
      if (wizard?.includeArtifacts) {
        ctx.projectArtifactItems(summary)
          .filter(artifact => wizard.selection.artifactIds.has(String(artifact.id || '')))
          .filter(artifact => ctx.projectArtifactStatus(artifact) !== 'available')
          .forEach((artifact) => {
            skipped.push({
              kind: 'artifact',
              id: String(artifact.id || ''),
              label: artifact.display_name || artifact.workspace_path || artifact.id,
              reason: artifact.file_status_detail || 'Artifact is unavailable or changed.',
            });
          });
        if (wizard.redactionMode === 'redacted') {
          ctx.projectArtifactItems(summary)
            .filter(artifact => wizard.selection.artifactIds.has(String(artifact.id || '')))
            .filter(artifact => ctx.projectArtifactStatus(artifact) === 'available')
            .map(artifact => ({ artifact, reason: redactedArtifactWarning(artifact) }))
            .filter(item => item.reason)
            .forEach(({ artifact, reason }) => {
              skipped.push({
                kind: 'artifact',
                id: String(artifact.id || ''),
                label: artifact.display_name || artifact.workspace_path || artifact.id,
                reason,
              });
            });
        }
        missingIds('artifact', projectId, summary).forEach((id) => {
          const config = kindConfig('artifact');
          skipped.push({
            kind: 'artifact',
            id,
            label: `${config.label} ${id}`,
            reason: 'No longer linked to this project.',
          });
        });
      }
      return skipped;
    }

    function redactedArtifactWarning(artifact) {
      const previewType = String(artifact && artifact.preview_type || '').trim().toLowerCase();
      if (['text', 'json', 'markdown', 'csv', 'log', 'xml', 'yaml', 'yml'].includes(previewType)) return '';
      const contentType = String(artifact && artifact.content_type || '').trim().toLowerCase();
      const contentMarkers = [
        'text/',
        'application/json',
        'application/ld+json',
        'application/xml',
        'application/x-ndjson',
        'application/yaml',
        'application/x-yaml',
      ];
      if (contentType && contentMarkers.some(marker => contentType.includes(marker))) return '';
      const path = String(artifact && (artifact.workspace_path || artifact.display_name) || '').toLowerCase();
      if (/\.(csv|html?|jsonl?|log|md|ndjson|txt|xml|ya?ml)$/.test(path)) return '';
      return 'Artifact is not a text or JSON type that can be safely redacted.';
    }

    function renderMissingSelection(section, kind, projectId, summary) {
      missingIds(kind, projectId, summary).forEach((id) => {
        section.appendChild(selectionCheckbox({
          kind,
          id,
          label: `Unavailable ${kind}`,
          detail: `${id} is no longer linked to this project. Uncheck it before creating the package.`,
          checked: true,
        }));
      });
    }

    function renderStepHeader(wrap) {
      const steps = ['Preset', 'Include', 'Metadata', 'Preview'];
      const stepper = document.createElement('ol');
      stepper.className = 'project-package-stepper';
      steps.forEach((label, index) => {
        const item = document.createElement('li');
        item.className = 'project-package-step' + (wizard.step === index + 1 ? ' is-active' : '');
        const number = document.createElement('span');
        number.className = 'project-package-step-number';
        number.textContent = String(index + 1);
        const text = document.createElement('span');
        text.className = 'project-package-step-label';
        text.textContent = label;
        item.append(number, text);
        stepper.appendChild(item);
      });
      wrap.appendChild(stepper);
    }

    function renderPreset(wrap, projectId, summary) {
      const list = document.createElement('div');
      list.className = 'project-package-preset-list';
      packagePresets().forEach((preset) => {
        const id = String(preset.id || '');
        const row = document.createElement('label');
        row.className = 'project-package-preset';
        row.classList.toggle('is-active', wizard.preset === id);
        const input = document.createElement('input');
        input.type = 'radio';
        input.name = 'project-package-preset';
        input.value = id;
        input.checked = wizard.preset === id;
        input.dataset.projectPackagePreset = '1';
        input.dataset.projectId = projectId;
        const text = document.createElement('span');
        text.className = 'project-package-preset-text';
        const titleEl = document.createElement('span');
        titleEl.textContent = preset.label || id;
        const detailEl = document.createElement('small');
        detailEl.textContent = preset.description || '';
        text.append(titleEl, detailEl);
        row.append(input, text);
        list.appendChild(row);
      });
      wrap.appendChild(list);
      if (packagePresetCatalogError) {
        const fallbackNote = document.createElement('p');
        fallbackNote.className = 'project-package-wizard-note is-warning';
        fallbackNote.textContent = 'Configured package presets could not be loaded; using shipped defaults.';
        wrap.appendChild(fallbackNote);
      }
      const metadata = document.createElement('div');
      metadata.className = 'project-package-preset-metadata';
      const labelsLabel = document.createElement('label');
      labelsLabel.textContent = 'Labels';
      const labelsInput = document.createElement('input');
      labelsInput.className = 'form-control form-control-compact';
      labelsInput.dataset.projectPackageField = 'labels';
      labelsInput.value = wizard.labels || '';
      labelsInput.placeholder = 'handoff, retest';
      labelsInput.autocomplete = 'off';
      labelsLabel.appendChild(labelsInput);
      const notesLabel = document.createElement('label');
      notesLabel.textContent = 'Notes';
      const notesInput = document.createElement('textarea');
      notesInput.className = 'form-control form-control-compact';
      notesInput.dataset.projectPackageField = 'notes';
      notesInput.rows = 3;
      notesInput.value = wizard.notes || '';
      notesInput.placeholder = 'Private package notes';
      notesLabel.appendChild(notesInput);
      metadata.append(labelsLabel, notesLabel);
      wrap.appendChild(metadata);
      const note = document.createElement('p');
      note.className = 'project-package-wizard-note';
      note.textContent = `${ctx.projectRunItems(summary).length} runs, ${ctx.projectFindingItems(projectId).length} findings, `
        + `${ctx.projectArtifactItems(summary).length} artifacts, and ${ctx.projectTargetItems(summary).length} targets are available.`;
      wrap.appendChild(note);
    }

    function renderSelections(wrap, projectId, summary) {
      if (!ctx.projectFindingsLoaded(projectId)) {
        wrap.appendChild(ctx.emptyProjectPanel('Loading findings for package selection...'));
        return;
      }
      const sections = [
        ['Targets', 'target', ctx.projectTargetItems(summary), item => ctx.projectTargetFilterLabel(item), item => ctx.entityNoteBody(item)],
      ];
      const runSection = document.createElement('section');
      runSection.className = 'project-package-selection-section';
      const runCount = ctx.projectRunItems(summary).length;
      const runHeadingRow = document.createElement('div');
      runHeadingRow.className = 'project-package-selection-heading';
      const runHeading = document.createElement('h3');
      runHeading.textContent = `Runs (${runCount})`;
      runHeadingRow.appendChild(runHeading);
      if (runCount) {
        const controls = document.createElement('div');
        controls.className = 'project-package-selection-actions';
        controls.append(
          bulkSelectionMenu('Select all', 'select', projectId),
          bulkSelectionMenu('Clear', 'clear', projectId),
        );
        runHeadingRow.appendChild(controls);
      }
      runSection.appendChild(runHeadingRow);
      const runMissingIds = missingIds('run', projectId, summary);
      const transcriptMissingIds = missingIds('transcript', projectId, summary);
      const findingMissingIds = missingIds('finding', projectId, summary);
      const artifactMissingIds = missingIds('artifact', projectId, summary);
      if (!runCount && !runMissingIds.length && !transcriptMissingIds.length && !findingMissingIds.length && !artifactMissingIds.length) {
        runSection.appendChild(ctx.emptyProjectPanel('No runs available.'));
      } else {
        renderRunSelections(runSection, projectId, summary);
        renderMissingSelection(runSection, 'run', projectId, summary);
        renderMissingSelection(runSection, 'transcript', projectId, summary);
        renderMissingSelection(runSection, 'finding', projectId, summary);
        renderMissingSelection(runSection, 'artifact', projectId, summary);
      }
      wrap.appendChild(runSection);
      sections.forEach(([title, kind, sectionItems, labelFn, detailFn]) => {
        const section = document.createElement('section');
        section.className = 'project-package-selection-section';
        const heading = document.createElement('h3');
        heading.textContent = `${title} (${sectionItems.length})`;
        section.appendChild(heading);
        const unavailableIds = missingIds(kind, projectId, summary);
        if (!sectionItems.length && !unavailableIds.length) {
          section.appendChild(ctx.emptyProjectPanel(`No ${title.toLowerCase()} available.`));
        } else {
          const selected = setFor(kind);
          sectionItems.forEach((item) => {
            section.appendChild(selectionCheckbox({
              kind,
              id: item.id,
              label: labelFn(item),
              detail: detailFn(item),
              checked: selected.has(String(item.id || '')),
            }));
          });
          renderMissingSelection(section, kind, projectId, summary);
        }
        wrap.appendChild(section);
      });
      const privateLabel = document.createElement('label');
      privateLabel.className = 'project-package-selection-row';
      const privateInput = document.createElement('input');
      privateInput.type = 'checkbox';
      privateInput.checked = !!wizard.includePrivateNotes;
      privateInput.dataset.projectPackagePrivateNotes = '1';
      const privateText = document.createElement('span');
      privateText.className = 'project-package-selection-text';
      const strong = document.createElement('strong');
      strong.textContent = 'Include private notes';
      const small = document.createElement('small');
      small.textContent = 'Private metadata stays excluded unless this is checked.';
      privateText.append(strong, small);
      privateLabel.append(privateInput, privateText);
      wrap.appendChild(privateLabel);
    }

    function renderMetadata(wrap) {
      const form = document.createElement('div');
      form.className = 'project-package-metadata-form';
      const nameLabel = document.createElement('label');
      nameLabel.textContent = 'Name';
      const nameInput = document.createElement('input');
      nameInput.className = 'form-control form-control-compact';
      nameInput.dataset.projectPackageField = 'name';
      nameInput.value = wizard.name;
      nameLabel.appendChild(nameInput);
      const descLabel = document.createElement('label');
      descLabel.textContent = 'Description';
      const descInput = document.createElement('textarea');
      descInput.className = 'form-control form-control-compact';
      descInput.dataset.projectPackageField = 'description';
      descInput.rows = 3;
      descInput.value = wizard.description;
      descLabel.appendChild(descInput);
      const artifactsLabel = document.createElement('label');
      artifactsLabel.className = 'project-package-selection-row';
      const artifactsInput = document.createElement('input');
      artifactsInput.type = 'checkbox';
      artifactsInput.checked = !!wizard.includeArtifacts;
      artifactsInput.disabled = !ctx.projectFilesEnabled();
      artifactsInput.dataset.projectPackageIncludeArtifacts = '1';
      const artifactsText = document.createElement('span');
      artifactsText.className = 'project-package-selection-text';
      const artifactsStrong = document.createElement('strong');
      artifactsStrong.textContent = wizard.redactionMode === 'redacted'
        ? 'Include selected artifact derivatives'
        : 'Include selected raw artifacts';
      const artifactsSmall = document.createElement('small');
      artifactsSmall.textContent = !ctx.projectFilesEnabled()
        ? 'Raw artifact files are unavailable because Files are disabled on this instance.'
        : (wizard.redactionMode === 'redacted'
          ? 'Text and JSON artifacts are sanitized into derivative files; binary or unknown types are skipped.'
          : 'Static HTML, Markdown, and selected raw artifacts are included in the archive.');
      artifactsText.append(artifactsStrong, artifactsSmall);
      artifactsLabel.append(artifactsInput, artifactsText);
      const redactionLabel = document.createElement('label');
      redactionLabel.textContent = 'Redaction';
      const redactionSelect = document.createElement('select');
      redactionSelect.className = 'form-select';
      redactionSelect.dataset.projectPackageField = 'redaction_mode';
      [
        ['raw', 'Raw package'],
        ['redacted', 'Redacted package'],
      ].forEach(([value, label]) => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = label;
        option.selected = wizard.redactionMode === value;
        redactionSelect.appendChild(option);
      });
      redactionLabel.appendChild(redactionSelect);
      form.append(nameLabel, descLabel, redactionLabel, artifactsLabel);
      wrap.appendChild(form);
    }

    function manifestPreview(projectId, summary) {
      const estimate = estimatePackage(summary);
      const skipped = skippedPreview(projectId, summary);
      const projectPreview = {
        id: projectId,
        name: summary?.project?.name || '',
      };
      if (wizard.includePrivateNotes && summary?.project?.note) {
        projectPreview.note = summary.project.note;
      }
      const selectedEntityIds = {
        run_ids: Array.from(wizard.selection.runIds),
        transcript_run_ids: Array.from(wizard.selection.transcriptRunIds)
          .filter(runId => wizard.selection.runIds.has(String(runId || ''))),
        finding_ids: Array.from(wizard.selection.findingIds),
        artifact_ids: Array.from(wizard.selection.artifactIds),
        target_ids: Array.from(wizard.selection.targetIds),
      };
      const counts = {
        runs: wizard.selection.runIds.size,
        findings: wizard.selection.findingIds.size,
        artifacts: wizard.selection.artifactIds.size,
        targets: wizard.selection.targetIds.size,
      };
      const options = {
        manifest_json: true,
        raw_artifacts: !!wizard.includeArtifacts && wizard.redactionMode !== 'redacted',
        redacted_artifact_derivatives: !!wizard.includeArtifacts && wizard.redactionMode === 'redacted',
        index_html: true,
        transcripts_html: wizard.selection.transcriptRunIds.size > 0,
      };
      return {
        package_format_version: 2,
        preset: wizard.preset,
        options,
        redaction_mode: wizard.redactionMode || 'raw',
        include_private_notes: !!wizard.includePrivateNotes,
        counts,
        selected_entity_ids: selectedEntityIds,
        provenance: {
          schema_version: 1,
          kind: 'evidence_package',
          build: {
            redaction_mode: wizard.redactionMode || 'raw',
            include_private_notes: !!wizard.includePrivateNotes,
            include_artifacts: !!wizard.includeArtifacts,
            preset: wizard.preset,
            options,
            selected_entity_ids: selectedEntityIds,
            selected_entity_counts: Object.fromEntries(
              Object.entries(selectedEntityIds).map(([key, value]) => [key, value.length]),
            ),
            included_entity_counts: counts,
          },
          sources: {
            project: projectPreview,
            project_links: {
              origin_sources: [],
              note: 'Project-link origin details are added when provenance fields are requested.',
            },
          },
          privacy: {
            redaction_mode: wizard.redactionMode || 'raw',
            private_notes_included: !!wizard.includePrivateNotes,
          },
        },
        estimated_archive: estimate,
        skipped_preview: skipped,
        project: projectPreview,
      };
    }

    function estimatePackage(summary) {
      const selectedRuns = ctx.projectRunItems(summary)
        .filter(run => wizard.selection.runIds.has(String(run.id || '')));
      const selectedTranscriptRuns = selectedRuns
        .filter(run => wizard.selection.transcriptRunIds.has(String(run.id || '')));
      const selectedArtifacts = ctx.projectArtifactItems(summary)
        .filter(artifact => wizard.selection.artifactIds.has(String(artifact.id || '')));
      const selectedFindings = ctx.projectFindingItems(wizard.projectId)
        .filter(finding => wizard.selection.findingIds.has(String(finding.id || '')));
      const selectedTargets = ctx.projectTargetItems(summary)
        .filter(target => wizard.selection.targetIds.has(String(target.id || '')));
      const rawArtifactBytes = wizard.includeArtifacts && wizard.redactionMode !== 'redacted'
        ? selectedArtifacts
          .filter(artifact => ctx.projectArtifactStatus(artifact) === 'available')
          .reduce((total, artifact) => total + Math.max(0, Number(artifact.byte_size || 0)), 0)
        : 0;
      const redactedArtifactItems = wizard.includeArtifacts && wizard.redactionMode === 'redacted'
        ? selectedArtifacts
          .filter(artifact => ctx.projectArtifactStatus(artifact) === 'available')
          .filter(artifact => !redactedArtifactWarning(artifact))
        : [];
      const redactedArtifactBytes = redactedArtifactItems
        .reduce((total, artifact) => total + Math.max(0, Number(artifact.byte_size || 0)), 0);
      const skippedArtifactCountEstimate = wizard.includeArtifacts
        ? selectedArtifacts.filter(artifact => (
          ctx.projectArtifactStatus(artifact) !== 'available'
          || (wizard.redactionMode === 'redacted' && !!redactedArtifactWarning(artifact))
        )).length
        : 0;
      const config = appConfig() || {};
      const maxLines = Math.max(1, Number(config.max_output_lines || 5000));
      const transcriptHtmlBytes = selectedTranscriptRuns.reduce((total, run) => {
        const lineCount = Math.max(0, Number(run.output_line_count || 0));
        return total + estimateTranscriptHtmlBytes(lineCount, maxLines);
      }, 0);
      const transcriptTextCompanionBytes = selectedTranscriptRuns.reduce((total, run) => {
        const lineCount = Math.max(0, Number(run.output_line_count || 0));
        return total + (lineCount > maxLines ? estimateTranscriptTextCompanionBytes(run, lineCount) : 0);
      }, 0);
      const metadataBytes = Math.max(
        16 * 1024,
        JSON.stringify({
          runs: selectedRuns.length,
          findings: selectedFindings.length,
          artifacts: selectedArtifacts.length,
          targets: selectedTargets.length,
        }).length + 16 * 1024,
      );
      const requiredArchiveBytes = rawArtifactBytes
        + redactedArtifactBytes
        + transcriptHtmlBytes
        + metadataBytes;
      const estimatedUncompressedBytes = requiredArchiveBytes + transcriptTextCompanionBytes;
      const maxArchiveBytes = Math.max(0, Number(config.evidence_package_max_mb || 0)) * 1024 * 1024;
      const maxUncompressedArchiveBytes = Math.max(
        0,
        Number(config.evidence_package_max_uncompressed_mb || 0),
      ) * 1024 * 1024;
      const estimatedCompressedArchiveBytes = rawArtifactBytes
        + estimateTextZipBytes(redactedArtifactBytes)
        + estimateTextZipBytes(transcriptHtmlBytes)
        + estimateTextZipBytes(metadataBytes);
      const estimatedCompressedArchiveBytesWithOptionalCompanions = estimatedCompressedArchiveBytes
        + estimateTextZipBytes(transcriptTextCompanionBytes);
      return {
        estimated_uncompressed_bytes: requiredArchiveBytes,
        estimated_archive_bytes: requiredArchiveBytes,
        estimated_uncompressed_bytes_with_optional_companions: estimatedUncompressedBytes,
        estimated_compressed_archive_bytes: estimatedCompressedArchiveBytes,
        estimated_compressed_archive_bytes_with_optional_companions: estimatedCompressedArchiveBytesWithOptionalCompanions,
        max_archive_bytes: maxArchiveBytes,
        max_compressed_archive_bytes: maxArchiveBytes,
        max_uncompressed_archive_bytes: maxUncompressedArchiveBytes,
        raw_artifact_bytes: rawArtifactBytes,
        redacted_artifact_bytes: redactedArtifactBytes,
        redacted_artifact_count_estimate: redactedArtifactItems.length,
        transcript_html_bytes: transcriptHtmlBytes,
        transcript_text_companion_bytes: transcriptTextCompanionBytes,
        metadata_bytes: metadataBytes,
        selected_run_count: selectedRuns.length,
        selected_transcript_count: selectedTranscriptRuns.length,
        selected_artifact_count: selectedArtifacts.length,
        skipped_artifact_count_estimate: skippedArtifactCountEstimate,
        note: 'Best-guess pre-build estimate before ZIP compression; final download enforces ZIP, expanded-content, and drift checks.',
      };
    }

    function renderPreview(wrap, projectId, summary) {
      const preview = manifestPreview(projectId, summary);
      const estimate = preview.estimated_archive || {};
      const note = document.createElement('p');
      note.className = 'project-package-wizard-note';
      const zipCapText = Number(estimate.max_compressed_archive_bytes || estimate.max_archive_bytes || 0) > 0
        ? ` ZIP cap: ${ctx.formatBytes(estimate.max_compressed_archive_bytes || estimate.max_archive_bytes)}.`
        : '';
      const expandedCapText = Number(estimate.max_uncompressed_archive_bytes || 0) > 0
        ? ` Expanded cap: ${ctx.formatBytes(estimate.max_uncompressed_archive_bytes)}.`
        : '';
      note.textContent = `Best-guess ZIP size: ${ctx.formatBytes(estimate.estimated_compressed_archive_bytes || 0)}. `
        + `Expanded content: ${ctx.formatBytes(estimate.estimated_uncompressed_bytes || 0)}.`
        + `${zipCapText}${expandedCapText}`;
      wrap.appendChild(note);
      if (Number(estimate.transcript_html_bytes || 0) > 0 || Number(estimate.transcript_text_companion_bytes || 0) > 0) {
        const transcriptEstimate = document.createElement('p');
        transcriptEstimate.className = 'project-package-wizard-note';
        transcriptEstimate.textContent = `Transcript HTML estimate: ${ctx.formatBytes(estimate.transcript_html_bytes || 0)}`
          + (Number(estimate.transcript_text_companion_bytes || 0) > 0
            ? ` Some capped transcripts can also produce full-text fallback files, up to ${ctx.formatBytes(estimate.transcript_text_companion_bytes || 0)} total; those fallback files are added only when they fit.`
            : '.');
        wrap.appendChild(transcriptEstimate);
      }
      if (Number(estimate.transcript_text_companion_bytes || 0) > 0) {
        const optionalEstimate = document.createElement('p');
        optionalEstimate.className = 'project-package-wizard-note';
        optionalEstimate.textContent = `Worst-case with every fallback text file: about ${ctx.formatBytes(estimate.estimated_compressed_archive_bytes_with_optional_companions || 0)} zipped, ${ctx.formatBytes(estimate.estimated_uncompressed_bytes_with_optional_companions || 0)} expanded.`;
        wrap.appendChild(optionalEstimate);
      }
      if (Number(estimate.max_compressed_archive_bytes || estimate.max_archive_bytes || 0) > 0
        && Number(estimate.estimated_compressed_archive_bytes || 0) > Number(estimate.max_compressed_archive_bytes || estimate.max_archive_bytes || 0)) {
        const overLimit = document.createElement('p');
        overLimit.className = 'project-package-wizard-note is-warning';
        overLimit.textContent = 'This selection may exceed the configured ZIP cap. Clear some transcripts or artifacts before creating the package.';
        wrap.appendChild(overLimit);
      }
      if (Number(estimate.max_uncompressed_archive_bytes || 0) > 0
        && Number(estimate.estimated_archive_bytes || 0) > Number(estimate.max_uncompressed_archive_bytes || 0)) {
        const overLimit = document.createElement('p');
        overLimit.className = 'project-package-wizard-note is-warning';
        overLimit.textContent = 'This selection exceeds the expanded-content cap. Clear some transcripts or artifacts before creating the package.';
        wrap.appendChild(overLimit);
      }
      if (Number(estimate.skipped_artifact_count_estimate || 0) > 0) {
        const skipped = document.createElement('p');
        skipped.className = 'project-package-wizard-note';
        skipped.textContent = `${estimate.skipped_artifact_count_estimate} selected artifact(s) are unavailable, changed, or not safe to redact and may be skipped.`;
        wrap.appendChild(skipped);
      }
      if (wizard.includeArtifacts && wizard.redactionMode === 'redacted') {
        const derivatives = document.createElement('p');
        derivatives.className = 'project-package-wizard-note';
        derivatives.textContent = `${estimate.redacted_artifact_count_estimate || 0} selected text/JSON artifact(s) will be exported as redacted derivatives.`;
        wrap.appendChild(derivatives);
      }
      if (Array.isArray(preview.skipped_preview) && preview.skipped_preview.length) {
        const skippedWrap = document.createElement('div');
        skippedWrap.className = 'project-package-preview-skipped';
        const heading = document.createElement('h3');
        heading.textContent = 'Items needing attention';
        skippedWrap.appendChild(heading);
        const list = document.createElement('ul');
        preview.skipped_preview.forEach((item) => {
          const row = document.createElement('li');
          row.textContent = `${item.label || item.id}: ${item.reason || 'May be skipped.'}`;
          list.appendChild(row);
        });
        skippedWrap.appendChild(list);
        wrap.appendChild(skippedWrap);
      }
      if (typeof ctx.projectProvenanceSummaryElement === 'function') {
        wrap.appendChild(ctx.projectProvenanceSummaryElement(preview, {
          fallbackKind: 'evidence_package',
          title: 'Provenance summary',
        }));
      }
      const pre = document.createElement('pre');
      pre.className = 'project-package-manifest-json project-package-preview-json nice-scroll';
      pre.textContent = JSON.stringify(preview, null, 2);
      wrap.appendChild(pre);
    }

    function renderWizard(container, projectId, summary) {
      const wizardEl = document.createElement('section');
      wizardEl.className = 'project-package-wizard';
      const header = document.createElement('div');
      header.className = 'project-package-wizard-header';
      const title = document.createElement('h2');
      title.id = 'project-package-wizard-title';
      title.textContent = 'New evidence package';
      const cancel = ctx.makeProjectButton('Cancel', 'package-wizard-cancel', projectId);
      header.append(title, cancel);
      wizardEl.appendChild(header);
      renderStepHeader(wizardEl);
      if (wizard.notice) {
        const message = document.createElement('p');
        message.className = 'project-workspace-message project-package-wizard-message'
          + (wizard.noticeError ? ' is-error' : '');
        message.textContent = wizard.notice;
        wizardEl.appendChild(message);
      }
      const body = document.createElement('div');
      body.className = 'project-package-wizard-body nice-scroll';
      if (wizard.step === 1) renderPreset(body, projectId, summary);
      else if (wizard.step === 2) renderSelections(body, projectId, summary);
      else if (wizard.step === 3) renderMetadata(body);
      else renderPreview(body, projectId, summary);
      wizardEl.appendChild(body);
      const footer = document.createElement('div');
      footer.className = 'project-package-wizard-footer';
      if (wizard.step > 1) footer.appendChild(ctx.makeProjectButton('Back', 'package-wizard-back', projectId));
      const next = ctx.makeProjectButton(wizard.step === 4 ? 'Create package' : 'Next', 'package-wizard-next', projectId);
      footer.appendChild(next);
      wizardEl.appendChild(footer);
      container.appendChild(wizardEl);
    }

    function payload() {
      return {
        name: String(wizard.name || '').trim(),
        description: String(wizard.description || '').trim(),
        preset: String(wizard.preset || 'custom'),
        redaction_mode: String(wizard.redactionMode || 'raw'),
        include_artifacts: !!wizard.includeArtifacts,
        include_private_notes: !!wizard.includePrivateNotes,
        labels: ctx.EntityMetadataClient.parseLabelInput(wizard.labels || ''),
        notes: String(wizard.notes || '').trim(),
        options: {
          manifest_json: true,
          index_html: true,
          transcripts_html: wizard.selection.transcriptRunIds.size > 0,
          raw_artifacts: !!wizard.includeArtifacts && wizard.redactionMode !== 'redacted',
          redacted_artifact_derivatives: !!wizard.includeArtifacts && wizard.redactionMode === 'redacted',
        },
        selection: {
          run_ids: Array.from(wizard.selection.runIds),
          transcript_run_ids: Array.from(wizard.selection.transcriptRunIds)
            .filter(runId => wizard.selection.runIds.has(String(runId || ''))),
          finding_ids: Array.from(wizard.selection.findingIds),
          artifact_ids: Array.from(wizard.selection.artifactIds),
          target_ids: Array.from(wizard.selection.targetIds),
        },
      };
    }

    async function createFromWizard(projectId) {
      if (!wizard) return;
      syncVisibleWizardFields();
      const body = payload();
      if (!body.name) {
        ctx.setProjectWorkspaceMessage?.('Package name is required.', { error: true });
        wizard.notice = 'Package name is required.';
        wizard.noticeError = true;
        wizard.step = 3;
        renderWizardModal();
        return;
      }
      const summary = summaryFor(projectId);
      const missingSelections = skippedPreview(projectId, summary)
        .filter(item => item.kind !== 'artifact' || String(item.reason || '').includes('No longer linked'));
      if (missingSelections.length) {
        const removedCount = pruneUnavailableSelections(missingSelections);
        const noun = removedCount === 1 ? 'item' : 'items';
        ctx.setProjectWorkspaceMessage?.(`${removedCount} unavailable ${noun} removed; review your selection before continuing.`);
        wizard.notice = `${removedCount} unavailable ${noun} removed; review your selection before continuing.`;
        wizard.noticeError = false;
        wizard.step = 2;
        renderWizardModal();
        return;
      }
      const createResp = await ctx.projectWorkspaceRequest(`/projects/${encodeURIComponent(projectId)}/packages`, {
        method: 'POST',
        body: JSON.stringify(body),
      });
      const created = await readJsonResponse(createResp, 'Unable to create package.');
      wizard = null;
      hideWizardOverlay();
      await ctx.refreshProjectWorkspace();
      mergePackageIntoSummary(projectId, created.package);
      ctx.setWorkspaceTab?.('packages');
      ctx.setProjectWorkspaceMessage?.('Package created.');
      ctx.renderProjectExplorer?.();
    }

    function waitForPackageJobPoll() {
      return new Promise(resolve => setTimeout(resolve, packageJobPollMs));
    }

    async function readJsonResponse(resp, fallbackMessage) {
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(data.error || fallbackMessage);
      }
      return data;
    }

    function packageJobMessage(job) {
      const message = String(job && job.message || '').trim();
      if (!message) return 'Preparing package archive.';
      return message.endsWith('.') ? message : `${message}.`;
    }

    function estimateTextZipBytes(value) {
      const safeValue = Math.max(0, Number(value || 0));
      if (!safeValue) return 0;
      return Math.max(1024, Math.round(safeValue * 0.4));
    }

    function estimateRunFullOutputBytes(run) {
      const keys = ['full_output_byte_size', 'full_output_bytes', 'output_artifact_byte_size'];
      for (const key of keys) {
        const value = Math.max(0, Number(run?.[key] || 0));
        if (value > 0) return value;
      }
      return 0;
    }

    function estimateTranscriptHtmlBytes(lineCount, maxLines) {
      const cappedLines = Math.min(Math.max(0, Number(lineCount || 0)), Math.max(1, Number(maxLines || 1)));
      return 8192 + cappedLines * 240;
    }

    function estimateTranscriptTextCompanionBytes(run, lineCount) {
      const safeLineCount = Math.max(0, Number(lineCount || 0));
      if (!safeLineCount) return 0;
      const fullOutputBytes = estimateRunFullOutputBytes(run);
      if (fullOutputBytes > 0) return Math.max(safeLineCount, Math.round(fullOutputBytes * 0.65));
      return safeLineCount * 48;
    }

    async function waitForPackageJob(projectId, packageId, job) {
      let current = job && typeof job === 'object' ? job : {};
      while (String(current.status || '') !== 'complete') {
        if (String(current.status || '') === 'failed') {
          throw new Error(current.error || 'Unable to build package archive.');
        }
        ctx.setProjectWorkspaceMessage?.(`Preparing package archive: ${packageJobMessage(current)}`, { toast: false });
        await waitForPackageJobPoll();
        const resp = await ctx.apiFetch(
          `/projects/${encodeURIComponent(projectId)}/packages/${encodeURIComponent(packageId)}/download-jobs/${encodeURIComponent(current.id || '')}`,
          { cache: 'no-store' },
        );
        const data = await readJsonResponse(resp, 'Unable to check package archive status.');
        current = data.job || {};
      }
      return current;
    }

    async function downloadPackage(projectId, pkg) {
      const packageId = String(pkg && pkg.id || '').trim();
      const startResp = await ctx.apiFetch(
        `/projects/${encodeURIComponent(projectId)}/packages/${encodeURIComponent(packageId)}/download-jobs`,
        { method: 'POST', cache: 'no-store' },
      );
      const startData = await readJsonResponse(startResp, 'Unable to start package archive build.');
      const job = await waitForPackageJob(projectId, packageId, startData.job || {});
      const downloadResp = await ctx.apiFetch(
        `/projects/${encodeURIComponent(projectId)}/packages/${encodeURIComponent(packageId)}/download-jobs/${encodeURIComponent(job.id || '')}/download-ticket`,
        { method: 'POST', cache: 'no-store' },
      );
      if (!downloadResp.ok) {
        const data = await downloadResp.json().catch(() => ({}));
        throw new Error(data.error || 'Unable to download package.');
      }
      const data = await downloadResp.json().catch(() => ({}));
      ctx.downloadUrlAsAttachment(data.url, packageDownloadName(pkg), 'Package download started.');
    }

    function packageBuildStatusText(elapsedSeconds) {
      const elapsed = Math.max(0, Number(elapsedSeconds || 0));
      if (elapsed < 1) return 'Preparing archive...';
      if (elapsed < 15) return `Preparing archive... ${elapsed}s`;
      return `Still building archive... ${elapsed}s`;
    }

    function clearDownloadTimer(button) {
      const timer = downloadTimers.get(button);
      if (timer) clearInterval(timer);
      downloadTimers.delete(button);
    }

    function setDownloadBusy(button, busy) {
      if (!button) return;
      clearDownloadTimer(button);
      button.disabled = !!busy;
      button.classList.toggle('is-preparing', !!busy);
      button.setAttribute('aria-busy', busy ? 'true' : 'false');
      if (!busy) {
        button.textContent = 'Download';
        button.removeAttribute('aria-busy');
        return;
      }
      const started = Date.now();
      const update = () => {
        button.textContent = packageBuildStatusText(Math.floor((Date.now() - started) / 1000));
      };
      update();
      downloadTimers.set(button, setInterval(update, 1000));
      ctx.setProjectWorkspaceMessage?.(
        'Preparing package archive. Large Full Archive exports can take a little while.',
        { toast: false },
      );
    }

    function renderMobilePackagesTab(projectId, summary) {
      const fragment = document.createDocumentFragment();
      const newPackage = ctx.makeProjectButton('Build Package', 'package-wizard-open', projectId, 'primary');
      const toolbar = document.createElement('div');
      toolbar.className = 'project-mobile-tab-toolbar';
      toolbar.appendChild(newPackage);
      fragment.appendChild(toolbar);
      const packageItems = items(summary);
      if (!packageItems.length) {
        fragment.appendChild(ctx.projectMobileEmptyPanel('No evidence packages yet.', [
          ctx.makeProjectButton('Build Package', 'package-wizard-open', projectId, 'primary'),
        ]));
        return fragment;
      }
      const list = document.createElement('div');
      list.className = 'project-mobile-content-list';
      packageItems.forEach((pkg) => {
        const packageId = String(pkg.id || '');
        const counts = countsText(pkg);
        const updated = ctx.formatDate(pkg.updated);
        const countLine = [pkg.description || '', counts].filter(Boolean).join(' · ');
        const detail = [countLine, updated ? `Updated ${updated}` : ''].filter(Boolean);
        list.appendChild(ctx.projectMobileContentRow({
          title: pkg.name || packageId || 'Package',
          meta: metaText(pkg),
          detail,
          chips: ctx.entityMetadataChips(pkg),
          accessory: packageId ? ctx.projectMobileActionMenu(projectId, `Package actions for ${pkg.name || packageId}`, [
            { label: 'Edit metadata', action: 'package-edit', dataset: { packageId } },
            { label: 'Download', action: 'package-download', dataset: { packageId } },
            { label: 'Re-package', action: 'package-repackage', dataset: { packageId } },
            { label: 'View manifest', action: 'package-manifest', dataset: { packageId } },
            { label: 'Delete', action: 'package-delete', tone: 'danger', dataset: { packageId } },
          ]) : null,
        }));
      });
      fragment.appendChild(list);
      return fragment;
    }

    function renderPackages(container, projectId, summary) {
      const toolbar = document.createElement('div');
      toolbar.className = 'project-package-toolbar';
      const newBtn = ctx.makeProjectButton('New package', 'package-wizard-open', projectId);
      toolbar.appendChild(newBtn);
      container.appendChild(toolbar);
      const packageItems = items(summary);
      if (!packageItems.length) {
        container.appendChild(ctx.emptyProjectPanel('No evidence packages yet.'));
        return;
      }
      packageItems.forEach((pkg) => {
        const counts = countsText(pkg);
        const updated = ctx.formatDate(pkg.updated);
        const detail = [pkg.description || '', counts, updated ? `Updated ${updated}` : '']
          .filter(Boolean)
          .join(' · ');
        container.appendChild(ctx.projectItemRow({
          title: pkg.name,
          meta: metaText(pkg),
          detail,
          chips: packageChips(pkg),
          accessory: accessory(projectId, pkg),
        }));
      });
    }

    function handleInput(event) {
      const packageField = event.target.closest?.('[data-project-package-field]');
      if (!packageField || !wizard) return false;
      const field = String(packageField.dataset.projectPackageField || '');
      updateWizardField(field, packageField.value);
      if (field === 'redaction_mode') {
        const mode = String(packageField.value || 'raw') === 'redacted' ? 'redacted' : 'raw';
        wizard.redactionMode = mode;
        wizard.redactionTouched = true;
        if (!ctx.projectFilesEnabled()) wizard.includeArtifacts = false;
        wizard.notice = '';
        renderWizardModal();
      }
      return true;
    }

    function wizardScrollTop() {
      return ctx.wizardBody?.querySelector('.project-package-wizard-body')?.scrollTop ?? null;
    }

    function handleChange(event) {
      if (handleInput(event)) return true;
      const packagePreset = event.target.closest?.('[data-project-package-preset]');
      if (packagePreset && wizard) {
        event.stopPropagation();
        const projectId = String(packagePreset.dataset.projectId || wizard.projectId || '');
        const preset = String(packagePreset.value || 'evidence');
        openWizard(projectId, preset);
        return true;
      }
      const packageSelection = event.target.closest?.('[data-project-package-selection]');
      if (packageSelection && wizard) {
        event.stopPropagation();
        const scrollTop = wizardScrollTop();
        const kind = String(packageSelection.dataset.projectPackageSelection || '');
        const selected = setFor(kind);
        const value = String(packageSelection.value || '');
        if (packageSelection.checked) selected.add(value);
        else selected.delete(value);
        if (kind === 'run') {
          const transcriptRuns = setFor('transcript');
          const childIds = runChildIds(value, wizard.projectId, summaryFor(wizard.projectId));
          const findingIds = setFor('finding');
          const artifactIds = setFor('artifact');
          if (packageSelection.checked) {
            transcriptRuns.add(value);
            childIds.findingIds.forEach(id => findingIds.add(id));
            childIds.selectableArtifactIds.forEach(id => artifactIds.add(id));
          } else {
            transcriptRuns.delete(value);
            childIds.findingIds.forEach(id => findingIds.delete(id));
            childIds.artifactIds.forEach(id => artifactIds.delete(id));
          }
        } else if (packageSelection.checked && ['transcript', 'finding', 'artifact'].includes(kind)) {
          const runId = String(packageSelection.dataset.runId || (kind === 'transcript' ? value : ''));
          if (runId) setFor('run').add(runId);
        }
        wizard.notice = '';
        renderWizardModal({ scrollTop });
        return true;
      }
      const packagePrivateNotes = event.target.closest?.('[data-project-package-private-notes]');
      if (packagePrivateNotes && wizard) {
        event.stopPropagation();
        wizard.includePrivateNotes = !!packagePrivateNotes.checked;
        wizard.privateNotesTouched = true;
        wizard.notice = '';
        renderWizardModal({ scrollTop: wizardScrollTop() });
        return true;
      }
      const packageIncludeArtifacts = event.target.closest?.('[data-project-package-include-artifacts]');
      if (packageIncludeArtifacts && wizard) {
        event.stopPropagation();
        wizard.includeArtifacts = ctx.projectFilesEnabled() && !!packageIncludeArtifacts.checked;
        wizard.includeArtifactsTouched = true;
        wizard.notice = '';
        renderWizardModal({ scrollTop: wizardScrollTop() });
        return true;
      }
      return false;
    }

    async function handleAction(btn) {
      if (!btn) return false;
      const action = String(btn.dataset.projectAction || '');
      if (!action.startsWith('package-wizard-')) return false;
      const projectId = String(btn.dataset.projectId || wizard?.projectId || '');
      if (action === 'package-wizard-open') {
        openWizard(projectId, 'evidence');
        return true;
      }
      if (action === 'package-wizard-cancel') {
        closeWizard();
        return true;
      }
      if (action === 'package-wizard-preset') {
        const preset = String(btn.dataset.preset || 'evidence');
        openWizard(projectId, preset);
        return true;
      }
      if (action === 'package-wizard-back') {
        if (wizard) {
          syncVisibleWizardFields();
          wizard.step = Math.max(1, wizard.step - 1);
          wizard.notice = '';
        }
        renderWizardModal();
        return true;
      }
      if (
        action === 'package-wizard-transcripts-all'
        || action === 'package-wizard-transcripts-clear'
        || action === 'package-wizard-bulk-selection'
      ) {
        if (wizard) {
          const mode = action === 'package-wizard-transcripts-clear' ? 'clear' : String(btn.dataset.bulkMode || 'select');
          const kind = action.startsWith('package-wizard-transcripts') ? 'transcript' : String(btn.dataset.bulkKind || '');
          const selected = setFor(kind);
          if (mode === 'select') {
            const summary = summaryFor(projectId);
            if (kind === 'transcript') {
              setFor('run').forEach(runId => selected.add(String(runId || '')));
            } else if (kind === 'finding') {
              ctx.projectFindingItems(projectId).forEach(finding => {
                const id = String(finding?.id || '');
                if (id) selected.add(id);
              });
            } else if (kind === 'target') {
              ctx.projectTargetItems(summary).forEach(target => {
                const id = String(target?.id || '');
                if (id) selected.add(id);
              });
            }
          } else {
            selected.clear();
          }
          wizard.notice = '';
        }
        renderWizardModal({ scrollTop: wizardScrollTop() });
        return true;
      }
      if (action === 'package-wizard-next') {
        if (!wizard) return true;
        syncVisibleWizardFields();
        if (wizard.step >= 4) {
          await createFromWizard(projectId);
          return true;
        }
        wizard.step = Math.min(4, wizard.step + 1);
        wizard.notice = '';
        ctx.setProjectWorkspaceMessage?.('');
        renderWizardModal();
        return true;
      }
      return false;
    }

    async function handleWizardOverlayClick(event) {
      const runToggle = event.target.closest?.('[data-project-package-run-toggle]');
      if (runToggle && wizard) {
        event.preventDefault();
        const scrollTop = wizardScrollTop();
        const runId = String(runToggle.dataset.projectPackageRunToggle || '');
        if (runId) {
          if (!wizard.collapsedRunIds) wizard.collapsedRunIds = new Set();
          if (wizard.collapsedRunIds.has(runId)) wizard.collapsedRunIds.delete(runId);
          else wizard.collapsedRunIds.add(runId);
        }
        renderWizardModal({ scrollTop });
        return true;
      }
      const btn = event.target.closest?.('[data-project-action]');
      if (!btn) return false;
      event.preventDefault();
      try {
        await handleAction(btn);
      } catch (err) {
        ctx.setProjectWorkspaceMessage?.(err.message || 'Package action failed.', { error: true });
        if (wizard) {
          wizard.notice = err.message || 'Package action failed.';
          wizard.noticeError = true;
          renderWizardModal();
        }
      }
      return true;
    }

    function setNotice(message, error = false) {
      if (!wizard) return;
      wizard.notice = message || '';
      wizard.noticeError = !!error;
      renderWizardModal();
    }

    return {
      items,
      byId,
      countsText,
      metaText,
      renderPackages,
      renderMobilePackagesTab,
      openManifest,
      closeManifest,
      isManifestOpen,
      isWizardActive,
      isWizardOpen,
      openWizard,
      openWizardFromPackage,
      closeWizard,
      renderWizardModal,
      handleInput,
      handleChange,
      handleAction,
      handleWizardOverlayClick,
      downloadPackage,
      setDownloadBusy,
      setNotice,
    };
  }

  const DarklabProjectPackages = {
    createProjectPackagesController,
  };
  exportedDarklabProjectPackages = DarklabProjectPackages;
})(globalThis);

export {
  exportedDarklabProjectPackages as DarklabProjectPackages,};
