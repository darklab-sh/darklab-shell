(function projectFiltersModule(global) {
  'use strict';

  function createProjectFiltersController(context) {
    const ctx = context || {};
    const targetFilters = new Map();
    const runFilters = new Map();
    const commandFilters = new Map();
    const severityFilters = new Map();
    const scopeFilters = new Map();
    const statusFilters = new Map();
    const labelFilters = new Map();
    const noteStateFilters = new Map();
    const orphanFilters = new Map();
    const findingSort = new Map();

    function normalizedProjectId(projectId = '') {
      return String(projectId || ctx.getSelectedProjectId?.() || '');
    }

    function targetById(summary, targetId) {
      const normalized = String(targetId || '').trim();
      if (!normalized) return null;
      return ctx.projectTargetItems(summary).find(item => String(item && item.id || '') === normalized) || null;
    }

    function targetFilterLabel(target) {
      if (!target) return 'target';
      const type = String(target.type || 'target').trim() || 'target';
      const value = String(target.value || '').trim();
      return value ? `${type}: ${value}` : type;
    }

    function targetFilterSet(projectId = '') {
      const normalized = normalizedProjectId(projectId);
      if (!normalized) return new Set();
      let filters = targetFilters.get(normalized);
      if (!filters) {
        filters = new Set();
        targetFilters.set(normalized, filters);
      }
      return filters;
    }

    function targetFilterIds(projectId = '', summary = ctx.projectSummary?.(projectId)) {
      const available = new Set(ctx.projectTargetItems(summary).map(target => String(target && target.id || '')).filter(Boolean));
      const filters = targetFilterSet(projectId);
      [...filters].forEach((targetId) => {
        if (!available.has(targetId)) filters.delete(targetId);
      });
      return [...filters];
    }

    function targetFilterActive(projectId = '', summary = ctx.projectSummary?.(projectId)) {
      return targetFilterIds(projectId, summary).length > 0;
    }

    function runFilterSet(projectId = '') {
      const normalized = normalizedProjectId(projectId);
      if (!normalized) return new Set();
      let filters = runFilters.get(normalized);
      if (!filters) {
        filters = new Set();
        runFilters.set(normalized, filters);
      }
      return filters;
    }

    function runFilterIds(projectId = '', summary = ctx.projectSummary?.(projectId)) {
      const available = new Set(ctx.projectRunItems(summary).map(run => String(run && run.id || '')).filter(Boolean));
      const filters = runFilterSet(projectId);
      [...filters].forEach((runId) => {
        if (!available.has(runId)) filters.delete(runId);
      });
      return [...filters];
    }

    function runFilterActive(projectId = '', summary = ctx.projectSummary?.(projectId)) {
      return runFilterIds(projectId, summary).length > 0;
    }

    function runFilterLabel(run) {
      if (!run) return 'run';
      const command = String(run.command || '').trim();
      const shortId = ctx.shortProjectRunId?.(run.id) || '';
      return `${command || 'Run'}${shortId ? ` (${shortId})` : ''}`;
    }

    function runFilterChipLabel(run) {
      if (!run) return 'run';
      const command = String(run.command || '').trim() || 'Run';
      if (command.length <= 16) return command;
      return `${command.slice(0, 14).trimEnd()} ...`;
    }

    function findingCommandRoot(value) {
      const root = String(value || '').trim().split(/\s+/, 1)[0] || '';
      return root.toLowerCase();
    }

    function findingCommandFilterSet(projectId = '') {
      const normalized = normalizedProjectId(projectId);
      if (!normalized) return new Set();
      if (!commandFilters.has(normalized)) {
        commandFilters.set(normalized, new Set());
      }
      return commandFilters.get(normalized);
    }

    function findingCommandOptions(projectId = '', summary = ctx.projectSummary?.(projectId)) {
      const roots = new Set();
      ctx.projectRunItems(summary).forEach(run => {
        const root = findingCommandRoot(run && run.command);
        if (root) roots.add(root);
      });
      ctx.projectFindingItems(projectId).forEach(finding => {
        const root = String(finding && finding.command_root || '').trim().toLowerCase()
          || findingCommandRoot(finding && finding.run_command);
        if (root) roots.add(root);
      });
      return [...roots].sort((left, right) => left.localeCompare(right, undefined, { sensitivity: 'base' }));
    }

    function findingCommandFilterValues(projectId = '', summary = ctx.projectSummary?.(projectId)) {
      const available = new Set(findingCommandOptions(projectId, summary));
      const filters = findingCommandFilterSet(projectId);
      [...filters].forEach((commandRoot) => {
        if (!available.has(commandRoot)) filters.delete(commandRoot);
      });
      return [...filters];
    }

    function findingCommandFilterActive(projectId = '', summary = ctx.projectSummary?.(projectId)) {
      return findingCommandFilterValues(projectId, summary).length > 0;
    }

    function findingSeverityFilterSet(projectId = '') {
      const normalized = normalizedProjectId(projectId);
      if (!normalized) return new Set();
      if (!severityFilters.has(normalized)) {
        severityFilters.set(normalized, new Set());
      }
      return severityFilters.get(normalized);
    }

    function findingSeverityOptions(projectId = '') {
      const configured = Array.isArray(ctx.projectFindingSeverityOptions) ? ctx.projectFindingSeverityOptions : [];
      const seen = new Set();
      const options = [];
      configured.forEach((option) => {
        const value = String(option && option.value || '').trim().toLowerCase();
        if (!value || seen.has(value)) return;
        seen.add(value);
        options.push({ value, label: String(option.label || value) });
      });
      ctx.projectFindingItems(projectId).forEach((finding) => {
        const value = String(finding && finding.severity || '').trim().toLowerCase();
        if (!value || seen.has(value)) return;
        seen.add(value);
        options.push({ value, label: value });
      });
      return options;
    }

    function findingSeverityFilterValues(projectId = '') {
      const available = new Set(findingSeverityOptions(projectId).map(option => option.value));
      const filters = findingSeverityFilterSet(projectId);
      [...filters].forEach((severity) => {
        if (!available.has(severity)) filters.delete(severity);
      });
      return [...filters];
    }

    function findingSeverityFilterActive(projectId = '') {
      return findingSeverityFilterValues(projectId).length > 0;
    }

    function findingScopeFilterSet(projectId = '') {
      const normalized = normalizedProjectId(projectId);
      if (!normalized) return new Set();
      if (!scopeFilters.has(normalized)) {
        scopeFilters.set(normalized, new Set());
      }
      return scopeFilters.get(normalized);
    }

    function findingScopeOptions(projectId = '') {
      const configured = Array.isArray(ctx.projectFindingScopeOptions) ? ctx.projectFindingScopeOptions : [];
      const seen = new Set();
      const options = [];
      configured.forEach((option) => {
        const value = String(option && option.value || '').trim().toLowerCase();
        if (!value || seen.has(value)) return;
        seen.add(value);
        options.push({ value, label: String(option.label || value) });
      });
      ctx.projectFindingItems(projectId).forEach((finding) => {
        const value = String(finding && (finding.scope || finding.kind) || '').trim().toLowerCase();
        if (!value || seen.has(value)) return;
        seen.add(value);
        options.push({ value, label: value });
      });
      return options;
    }

    function findingScopeFilterValues(projectId = '') {
      const available = new Set(findingScopeOptions(projectId).map(option => option.value));
      const filters = findingScopeFilterSet(projectId);
      [...filters].forEach((scope) => {
        if (!available.has(scope)) filters.delete(scope);
      });
      return [...filters];
    }

    function findingScopeFilterActive(projectId = '') {
      return findingScopeFilterValues(projectId).length > 0;
    }

    function findingStatusFilterSet(projectId = '') {
      const normalized = normalizedProjectId(projectId);
      if (!normalized) return new Set();
      if (!statusFilters.has(normalized)) {
        statusFilters.set(normalized, new Set());
      }
      return statusFilters.get(normalized);
    }

    function findingStatusFilterValues(projectId = '') {
      const valid = new Set(ctx.findingReviewStates.map(state => state.value));
      return [...findingStatusFilterSet(projectId)].filter(value => valid.has(value));
    }

    function findingStatusFilterActive(projectId = '') {
      return findingStatusFilterValues(projectId).length > 0;
    }

    function findingLabelFilterSet(projectId = '') {
      const normalized = normalizedProjectId(projectId);
      if (!normalized) return new Set();
      if (!labelFilters.has(normalized)) {
        labelFilters.set(normalized, new Set());
      }
      return labelFilters.get(normalized);
    }

    function findingLabelOptions(projectId = '') {
      const labels = new Set();
      ctx.projectFindingItems(projectId).forEach((finding) => {
        ctx.entityLabelValues(finding).forEach(label => labels.add(label));
      });
      return [...labels].sort((left, right) => left.localeCompare(right, undefined, { sensitivity: 'base' }));
    }

    function findingLabelFilterValues(projectId = '') {
      const available = new Set(findingLabelOptions(projectId));
      const filters = findingLabelFilterSet(projectId);
      [...filters].forEach((label) => {
        if (!available.has(label)) filters.delete(label);
      });
      return [...filters];
    }

    function findingLabelFilterActive(projectId = '') {
      return findingLabelFilterValues(projectId).length > 0;
    }

    function findingNoteStateValue(projectId = '') {
      const value = String(noteStateFilters.get(normalizedProjectId(projectId)) || 'all');
      return ctx.projectFindingNoteStateOptions.some(option => option.value === value) ? value : 'all';
    }

    function setFindingNoteState(projectId = '', value = 'all') {
      const normalized = normalizedProjectId(projectId);
      if (!normalized) return;
      const next = String(value || 'all');
      if (next === 'all') noteStateFilters.delete(normalized);
      else noteStateFilters.set(normalized, next);
    }

    function findingNoteStateFilterActive(projectId = '') {
      return findingNoteStateValue(projectId) !== 'all';
    }

    function findingOrphanFilterValue(projectId = '') {
      const value = String(orphanFilters.get(normalizedProjectId(projectId)) || 'hide');
      return ctx.projectFindingOrphanOptions.some(option => option.value === value) ? value : 'hide';
    }

    function setFindingOrphanFilter(projectId = '', value = 'hide') {
      const normalized = normalizedProjectId(projectId);
      if (!normalized) return;
      const next = String(value || 'hide');
      if (next === 'hide') orphanFilters.delete(normalized);
      else orphanFilters.set(normalized, next);
    }

    function findingOrphanFilterActive(projectId = '') {
      return findingOrphanFilterValue(projectId) !== 'hide';
    }

    function findingSortValue(projectId = '') {
      const value = String(findingSort.get(normalizedProjectId(projectId)) || 'source');
      return ctx.projectFindingSortOptions.some(option => option.value === value) ? value : 'source';
    }

    function setFindingSort(projectId = '', value = 'source') {
      const normalized = normalizedProjectId(projectId);
      if (!normalized) return;
      findingSort.set(normalized, String(value || 'source'));
    }

    function findingTargetIds(finding) {
      const ids = new Set();
      const add = value => {
        const normalized = String(value || '').trim();
        if (normalized) ids.add(normalized);
      };
      add(finding && finding.target_id);
      if (Array.isArray(finding && finding.target_ids)) finding.target_ids.forEach(add);
      if (Array.isArray(finding && finding.targets)) {
        finding.targets.forEach(target => add(target && typeof target === 'object' ? target.id : target));
      }
      return ids;
    }

    function runDirectTargetIds(run) {
      const ids = new Set();
      const add = value => {
        const normalized = String(value || '').trim();
        if (normalized) ids.add(normalized);
      };
      add(run && run.target_id);
      if (Array.isArray(run && run.target_ids)) run.target_ids.forEach(add);
      if (Array.isArray(run && run.targets)) {
        run.targets.forEach(target => add(target && typeof target === 'object' ? target.id : target));
      }
      return ids;
    }

    function runIdsMatchingTargets(projectId, filterIds) {
      const filters = new Set(filterIds);
      const runIds = new Set();
      if (!filters.size) return runIds;
      ctx.projectFindingItems(projectId).forEach((finding) => {
        const targetIds = findingTargetIds(finding);
        const runId = String(finding && finding.run_id || '');
        if (runId && [...targetIds].some(targetId => filters.has(targetId))) runIds.add(runId);
      });
      return runIds;
    }

    function runMatchesTargetFilters(run, projectId, filterIds, matchingRunIds) {
      if (!filterIds.length) return true;
      const runId = String(run && run.id || '');
      if (runId && matchingRunIds.has(runId)) return true;
      const directIds = runDirectTargetIds(run);
      return filterIds.some(targetId => directIds.has(targetId));
    }

    function findingServerFilterParams(projectId, summary = ctx.projectSummary?.(projectId)) {
      const params = new URLSearchParams();
      targetFilterIds(projectId, summary).forEach(targetId => params.append('target_id', targetId));
      runFilterIds(projectId, summary).forEach(runId => params.append('run_id', runId));
      findingCommandFilterValues(projectId, summary).forEach(commandRoot => params.append('command_root', commandRoot));
      findingSeverityFilterValues(projectId).forEach(severity => params.append('severity', severity));
      findingScopeFilterValues(projectId).forEach(scope => params.append('scope', scope));
      findingStatusFilterValues(projectId).forEach(status => params.append('review_state', status));
      findingLabelFilterValues(projectId).forEach(label => params.append('label', label));
      const noteState = findingNoteStateValue(projectId);
      if (noteState !== 'all') params.set('note_state', noteState);
      const orphanFilter = findingOrphanFilterValue(projectId);
      if (orphanFilter !== 'hide') params.set('orphan_filter', orphanFilter);
      return params;
    }

    function findingServerFiltersActive(projectId = '', summary = ctx.projectSummary?.(projectId)) {
      return findingServerFilterParams(projectId, summary).toString() !== '';
    }

    function findingFilteredKey(projectId = '', summary = ctx.projectSummary?.(projectId)) {
      const normalized = normalizedProjectId(projectId);
      const query = findingServerFilterParams(normalized, summary).toString();
      return query ? `${normalized}::${query}` : '';
    }

    function filteredFindingItems(projectId = '', summary = ctx.projectSummary?.(projectId)) {
      const key = findingFilteredKey(projectId, summary);
      return key && ctx.hasProjectFilteredFindingsKey?.(key)
        ? ctx.projectFilteredFindingItems(key)
        : ctx.projectFindingItems(projectId);
    }

    function findingTargetText(summary, finding) {
      const targetIds = [...findingTargetIds(finding)];
      if (!targetIds.length) return '';
      return targetIds
        .map(targetId => ctx.projectTargetLabel(summary, targetId))
        .filter(Boolean)
        .join(', ');
    }

    function findingRunStarted(summary, finding) {
      const run = ctx.projectRunById(summary, finding && finding.run_id);
      const timestamp = Date.parse(String(run && run.started || finding && finding.created || ''));
      return Number.isFinite(timestamp) ? timestamp : 0;
    }

    function compareProjectFindingText(left, right) {
      return String(left || '').localeCompare(String(right || ''), undefined, { sensitivity: 'base', numeric: true });
    }

    function sortProjectFindings(findings, projectId, summary) {
      const sortValue = findingSortValue(projectId);
      if (sortValue === 'source') return findings;
      return findings.slice().sort((left, right) => {
        if (sortValue === 'severity') {
          const leftRank = ctx.findingSeverityRank[String(left && left.severity || '').toLowerCase()] ?? 99;
          const rightRank = ctx.findingSeverityRank[String(right && right.severity || '').toLowerCase()] ?? 99;
          if (leftRank !== rightRank) return leftRank - rightRank;
        } else if (sortValue === 'review') {
          const leftRank = ctx.findingReviewRank[String(left && left.review_state || 'new')] ?? 99;
          const rightRank = ctx.findingReviewRank[String(right && right.review_state || 'new')] ?? 99;
          if (leftRank !== rightRank) return leftRank - rightRank;
        } else if (sortValue === 'target') {
          const targetCompare = compareProjectFindingText(
            findingTargetText(summary, left),
            findingTargetText(summary, right),
          );
          if (targetCompare) return targetCompare;
        } else if (sortValue === 'newest') {
          const timeCompare = findingRunStarted(summary, right) - findingRunStarted(summary, left);
          if (timeCompare) return timeCompare;
        }
        const runCompare = compareProjectFindingText(
          left && (left.run_command || left.run_id),
          right && (right.run_command || right.run_id),
        );
        if (runCompare) return runCompare;
        const leftLine = Number(left && left.line_number);
        const rightLine = Number(right && right.line_number);
        if (Number.isFinite(leftLine) && Number.isFinite(rightLine) && leftLine !== rightLine) return leftLine - rightLine;
        return compareProjectFindingText(left && (left.title || left.raw_line), right && (right.title || right.raw_line));
      });
    }

    function filteredRuns(projectId, summary) {
      let runs = ctx.projectRunItems(summary);
      const runIds = new Set(runFilterIds(projectId, summary));
      if (runIds.size) {
        runs = runs.filter(run => runIds.has(String(run && run.id || '')));
      }
      const filterIds = targetFilterIds(projectId, summary);
      if (!filterIds.length) return runs;
      const matchingRunIds = runIdsMatchingTargets(projectId, filterIds);
      return runs.filter(run => runMatchesTargetFilters(run, projectId, filterIds, matchingRunIds));
    }

    function filteredFindings(projectId, summary) {
      let findings = filteredFindingItems(projectId, summary);
      if (!ctx.hasProjectFilteredFindingsKey?.(findingFilteredKey(projectId, summary))) {
        const filterIds = new Set(targetFilterIds(projectId, summary));
        if (filterIds.size) {
          findings = findings.filter(finding => [...findingTargetIds(finding)].some(targetId => filterIds.has(targetId)));
        }
        const runFilters = new Set(runFilterIds(projectId, summary));
        if (runFilters.size) {
          findings = findings.filter(finding => runFilters.has(String(finding && finding.run_id || '')));
        }
        const commandFilterValues = new Set(findingCommandFilterValues(projectId, summary));
        if (commandFilterValues.size) {
          findings = findings.filter((finding) => {
            const root = String(finding && finding.command_root || '').trim().toLowerCase()
              || findingCommandRoot(finding && finding.run_command);
            return commandFilterValues.has(root);
          });
        }
        const severityFilterValues = new Set(findingSeverityFilterValues(projectId));
        if (severityFilterValues.size) {
          findings = findings.filter(finding => severityFilterValues.has(String(finding && finding.severity || '').toLowerCase()));
        }
        const scopeFilterValues = new Set(findingScopeFilterValues(projectId));
        if (scopeFilterValues.size) {
          findings = findings.filter(finding => scopeFilterValues.has(String(finding && (finding.scope || finding.kind) || '').toLowerCase()));
        }
        const statusFilterValues = new Set(findingStatusFilterValues(projectId));
        if (statusFilterValues.size) {
          findings = findings.filter(finding => statusFilterValues.has(String(finding && finding.review_state || 'new')));
        }
        const labelFilterValues = new Set(findingLabelFilterValues(projectId));
        if (labelFilterValues.size) {
          findings = findings.filter(finding => ctx.entityLabelValues(finding).some(label => labelFilterValues.has(label)));
        }
        const noteState = findingNoteStateValue(projectId);
        if (noteState === 'noted') findings = findings.filter(finding => !!ctx.entityNoteBody(finding));
        else if (noteState === 'unnoted') findings = findings.filter(finding => !ctx.entityNoteBody(finding));
        const orphanState = findingOrphanFilterValue(projectId);
        if (orphanState === 'hide') findings = findings.filter(finding => !finding.orphan_source);
        else if (orphanState === 'only') findings = findings.filter(finding => finding.orphan_source);
      }
      return sortProjectFindings(findings, projectId, summary);
    }

    function filteredArtifacts(projectId, summary) {
      let artifacts = ctx.projectArtifactItems(summary);
      const runFilters = new Set(runFilterIds(projectId, summary));
      if (runFilters.size) {
        artifacts = artifacts.filter(artifact => runFilters.has(String(artifact && artifact.run_id || '')));
      }
      const filterIds = targetFilterIds(projectId, summary);
      if (!filterIds.length) return artifacts;
      const matchingRunIds = runIdsMatchingTargets(projectId, filterIds);
      const matchingDirectRunIds = new Set();
      ctx.projectRunItems(summary).forEach((run) => {
        if (runMatchesTargetFilters(run, projectId, filterIds, matchingRunIds)) {
          const runId = String(run && run.id || '');
          if (runId) matchingDirectRunIds.add(runId);
        }
      });
      return artifacts.filter(artifact => matchingDirectRunIds.has(String(artifact && artifact.run_id || '')));
    }

    function targetFilterableProjectTab(tab = ctx.projectWorkspaceTab?.()) {
      return ['runs', 'entities', 'findings', 'artifacts'].includes(tab);
    }

    function clearAllFilters(projectId = '') {
      const normalized = normalizedProjectId(projectId);
      targetFilterSet(normalized).clear();
      runFilterSet(normalized).clear();
      findingCommandFilterSet(normalized).clear();
      findingSeverityFilterSet(normalized).clear();
      findingScopeFilterSet(normalized).clear();
      findingStatusFilterSet(normalized).clear();
      findingLabelFilterSet(normalized).clear();
      noteStateFilters.delete(normalized);
      orphanFilters.delete(normalized);
    }

    function filterDropdown(label, count, optionNodes) {
      const dropdown = document.createElement('div');
      dropdown.className = 'project-target-filter-menu project-shared-filter-menu';
      const trigger = document.createElement('button');
      trigger.type = 'button';
      trigger.className = 'control-row form-control-compact project-target-filter-trigger';
      trigger.setAttribute('aria-haspopup', 'menu');
      trigger.setAttribute('aria-expanded', 'false');
      trigger.textContent = count ? `${label} (${count})` : label;
      dropdown.appendChild(trigger);

      const menu = document.createElement('div');
      menu.className = 'project-target-filter-options dropdown-surface';
      menu.setAttribute('role', 'menu');
      menu.hidden = true;
      if (optionNodes.length) {
        optionNodes.forEach(node => menu.appendChild(node));
      } else {
        const empty = document.createElement('div');
        empty.className = 'project-target-filter-empty';
        empty.textContent = 'No options available';
        menu.appendChild(empty);
      }
      dropdown.appendChild(menu);
      ctx.bindProjectRuntimePressable(trigger, {
        onActivate: (event) => {
          event?.preventDefault?.();
          event?.stopPropagation?.();
          const open = !dropdown.classList.contains('is-open');
          closeFilterMenus(open ? dropdown : null);
          setFilterMenuOpen(dropdown, open);
        },
      });
      return dropdown;
    }

    function setFilterMenuOpen(menu, open) {
      if (!menu) return;
      menu.classList.toggle('is-open', !!open);
      const trigger = menu.querySelector('.project-target-filter-trigger');
      if (trigger) trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
      const panel = menu.querySelector('.project-target-filter-options');
      if (panel) panel.hidden = !open;
    }

    function closeFilterMenus(exceptMenu = null) {
      const modal = ctx.projectWorkspaceModal?.();
      if (!modal) return;
      modal.querySelectorAll('.project-target-filter-menu.is-open').forEach((menu) => {
        if (exceptMenu && menu === exceptMenu) return;
        setFilterMenuOpen(menu, false);
      });
    }

    function filterOption({ labelText, value, checked, dataset }) {
      const label = document.createElement('label');
      label.className = 'project-target-filter-option dropdown-item dropdown-item-compact';
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.value = value;
      input.checked = checked;
      Object.entries(dataset || {}).forEach(([key, dataValue]) => {
        input.dataset[key] = dataValue;
      });
      const mark = document.createElement('span');
      mark.className = 'project-target-filter-check';
      mark.setAttribute('aria-hidden', 'true');
      mark.textContent = '✓';
      const text = document.createElement('span');
      text.className = 'project-target-filter-option-label';
      text.textContent = labelText;
      label.append(input, mark, text);
      return label;
    }

    function filterChip({ projectId, label, value, clearAttr }) {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'chip chip-removable project-target-filter-chip';
      chip.dataset.projectId = projectId;
      chip.dataset[clearAttr] = value;
      chip.textContent = `${label} ×`;
      ctx.bindProjectRuntimePressable(chip);
      return chip;
    }

    function renderFilterBar(projectId, summary) {
      const wrap = document.createElement('div');
      wrap.className = 'project-explorer-filter-panel';

      const controls = document.createElement('div');
      controls.className = 'project-explorer-filter-controls';

      const selectedTargets = new Set(targetFilterIds(projectId, summary));
      const targetOptions = ctx.projectTargetItems(summary).map(target => {
        const targetId = String(target && target.id || '');
        return filterOption({
          labelText: targetFilterLabel(target),
          value: targetId,
          checked: selectedTargets.has(targetId),
          dataset: { projectTargetFilterOption: '1', projectId },
        });
      });
      controls.appendChild(filterDropdown('Filter by target', selectedTargets.size, targetOptions));

      const selectedRuns = new Set(runFilterIds(projectId, summary));
      const runOptions = ctx.projectRunItems(summary).map(run => {
        const runId = String(run && run.id || '');
        return filterOption({
          labelText: runFilterLabel(run),
          value: runId,
          checked: selectedRuns.has(runId),
          dataset: { projectRunFilterOption: '1', projectId },
        });
      });
      controls.appendChild(filterDropdown('Filter by run', selectedRuns.size, runOptions));

      const selectedStatuses = new Set(findingStatusFilterValues(projectId));
      const selectedCommands = new Set(findingCommandFilterValues(projectId, summary));
      const selectedSeverities = new Set(findingSeverityFilterValues(projectId));
      const selectedScopes = new Set(findingScopeFilterValues(projectId));
      const selectedLabels = new Set(findingLabelFilterValues(projectId));
      let sortControl = null;
      if (ctx.projectWorkspaceTab() === 'findings') {
        const commandOptions = findingCommandOptions(projectId, summary).map(commandRoot => filterOption({
          labelText: commandRoot,
          value: commandRoot,
          checked: selectedCommands.has(commandRoot),
          dataset: { projectFindingCommandFilterOption: '1', projectId },
        }));
        controls.appendChild(filterDropdown('Filter by command', selectedCommands.size, commandOptions));

        const severityOptions = findingSeverityOptions(projectId).map(({ value, label: labelText }) => filterOption({
          labelText,
          value,
          checked: selectedSeverities.has(value),
          dataset: { projectFindingSeverityFilterOption: '1', projectId },
        }));
        controls.appendChild(filterDropdown('Filter by severity', selectedSeverities.size, severityOptions));

        const scopeOptions = findingScopeOptions(projectId).map(({ value, label: labelText }) => filterOption({
          labelText,
          value,
          checked: selectedScopes.has(value),
          dataset: { projectFindingScopeFilterOption: '1', projectId },
        }));
        controls.appendChild(filterDropdown('Filter by scope', selectedScopes.size, scopeOptions));

        const statusOptions = ctx.findingReviewStates.map(({ value, label: labelText }) => filterOption({
          labelText,
          value,
          checked: selectedStatuses.has(value),
          dataset: { projectFindingStatusFilterOption: '1', projectId },
        }));
        controls.appendChild(filterDropdown('Filter by status', selectedStatuses.size, statusOptions));

        const orphanWrap = document.createElement('label');
        orphanWrap.className = 'project-finding-sort-control project-finding-orphan-control';
        const orphanSelect = document.createElement('select');
        orphanSelect.className = 'form-select project-finding-orphan-select';
        orphanSelect.dataset.projectFindingOrphan = '1';
        orphanSelect.dataset.projectId = projectId;
        orphanSelect.setAttribute('aria-label', 'Filter findings by source runs');
        const currentOrphan = findingOrphanFilterValue(projectId);
        ctx.projectFindingOrphanOptions.forEach(({ value, label: labelText }) => {
          const option = document.createElement('option');
          option.value = value;
          option.textContent = labelText;
          option.selected = value === currentOrphan;
          orphanSelect.appendChild(option);
        });
        orphanWrap.appendChild(orphanSelect);
        controls.appendChild(orphanWrap);

        const sortWrap = document.createElement('label');
        sortWrap.className = 'project-finding-sort-control project-finding-source-order-control';
        const sortSelect = document.createElement('select');
        sortSelect.className = 'form-select project-finding-sort-select';
        sortSelect.dataset.projectFindingSort = '1';
        sortSelect.dataset.projectId = projectId;
        sortSelect.setAttribute('aria-label', 'Sort findings');
        const currentSort = findingSortValue(projectId);
        ctx.projectFindingSortOptions.forEach(({ value, label: labelText }) => {
          const option = document.createElement('option');
          option.value = value;
          option.textContent = labelText;
          option.selected = value === currentSort;
          sortSelect.appendChild(option);
        });
        sortWrap.appendChild(sortSelect);
        sortControl = sortWrap;
      }

      const activeProjectTab = ctx.projectWorkspaceTab();
      const showMetadataFilters = activeProjectTab !== 'entities';
      if (showMetadataFilters) {
        const labelOptions = findingLabelOptions(projectId).map(labelText => filterOption({
          labelText,
          value: labelText,
          checked: selectedLabels.has(labelText),
          dataset: { projectFindingLabelFilterOption: '1', projectId },
        }));
        controls.appendChild(filterDropdown('Filter by label', selectedLabels.size, labelOptions));

        const noteWrap = document.createElement('label');
        noteWrap.className = 'project-finding-sort-control project-finding-note-state-control';
        const noteSelect = document.createElement('select');
        noteSelect.className = 'form-select project-finding-note-state-select';
        noteSelect.dataset.projectFindingNoteState = '1';
        noteSelect.dataset.projectId = projectId;
        noteSelect.setAttribute('aria-label', 'Filter findings by notes');
        const currentNoteState = findingNoteStateValue(projectId);
        ctx.projectFindingNoteStateOptions.forEach(({ value, label: labelText }) => {
          const option = document.createElement('option');
          option.value = value;
          option.textContent = labelText;
          option.selected = value === currentNoteState;
          noteSelect.appendChild(option);
        });
        noteWrap.appendChild(noteSelect);
        controls.appendChild(noteWrap);
      }
      if (sortControl) controls.appendChild(sortControl);
      wrap.appendChild(controls);

      const chips = document.createElement('div');
      chips.className = 'project-target-filter-chips project-explorer-filter-chips';
      selectedTargets.forEach((targetId) => {
        const target = targetById(summary, targetId);
        chips.appendChild(filterChip({
          projectId,
          label: `target: ${targetFilterLabel(target)}`,
          value: targetId,
          clearAttr: 'projectTargetFilterClear',
        }));
      });
      selectedRuns.forEach((runId) => {
        chips.appendChild(filterChip({
          projectId,
          label: `run: ${runFilterChipLabel(ctx.projectRunById(summary, runId))}`,
          value: runId,
          clearAttr: 'projectRunFilterClear',
        }));
      });
      selectedStatuses.forEach((status) => {
        chips.appendChild(filterChip({
          projectId,
          label: `status: ${ctx.findingReviewStateLabel(status)}`,
          value: status,
          clearAttr: 'projectFindingStatusFilterClear',
        }));
      });
      selectedCommands.forEach((commandRoot) => {
        chips.appendChild(filterChip({
          projectId,
          label: `command: ${commandRoot}`,
          value: commandRoot,
          clearAttr: 'projectFindingCommandFilterClear',
        }));
      });
      selectedSeverities.forEach((severity) => {
        const option = findingSeverityOptions(projectId).find(item => item.value === severity);
        chips.appendChild(filterChip({
          projectId,
          label: `severity: ${option ? option.label : severity}`,
          value: severity,
          clearAttr: 'projectFindingSeverityFilterClear',
        }));
      });
      selectedScopes.forEach((scope) => {
        const option = findingScopeOptions(projectId).find(item => item.value === scope);
        chips.appendChild(filterChip({
          projectId,
          label: `scope: ${option ? option.label : scope}`,
          value: scope,
          clearAttr: 'projectFindingScopeFilterClear',
        }));
      });
      if (showMetadataFilters) {
        selectedLabels.forEach((labelValue) => {
          chips.appendChild(filterChip({
            projectId,
            label: `label: ${labelValue}`,
            value: labelValue,
            clearAttr: 'projectFindingLabelFilterClear',
          }));
        });
      }
      const noteState = findingNoteStateValue(projectId);
      if (showMetadataFilters && noteState !== 'all') {
        const option = ctx.projectFindingNoteStateOptions.find(item => item.value === noteState);
        chips.appendChild(filterChip({
          projectId,
          label: `notes: ${option ? option.label : noteState}`,
          value: noteState,
          clearAttr: 'projectFindingNoteStateClear',
        }));
      }
      const orphanState = findingOrphanFilterValue(projectId);
      if (orphanState !== 'hide') {
        const option = ctx.projectFindingOrphanOptions.find(item => item.value === orphanState);
        chips.appendChild(filterChip({
          projectId,
          label: `sources: ${option ? option.label : orphanState}`,
          value: orphanState,
          clearAttr: 'projectFindingOrphanClear',
        }));
      }
      const hasFilters = selectedTargets.size || selectedRuns.size || selectedStatuses.size
        || selectedCommands.size || selectedSeverities.size || selectedScopes.size
        || (showMetadataFilters && (selectedLabels.size || noteState !== 'all'))
        || orphanState !== 'hide';
      if (hasFilters) {
        const clearAll = document.createElement('button');
        clearAll.type = 'button';
        clearAll.className = 'btn btn-ghost btn-compact project-target-filter-clear';
        clearAll.dataset.projectFilterClearAll = '1';
        clearAll.dataset.projectId = projectId;
        clearAll.textContent = 'Clear filters';
        ctx.bindProjectRuntimePressable(clearAll);
        chips.appendChild(clearAll);
      } else {
        const empty = document.createElement('span');
        empty.className = 'project-explorer-filter-empty';
        empty.textContent = 'No filters applied';
        chips.appendChild(empty);
      }
      wrap.appendChild(chips);
      return wrap;
    }

    function filterControlsRoot(root) {
      if (!root) return null;
      if (root.matches?.('.project-explorer-filter-controls')) return root;
      return root.querySelector?.('.project-explorer-filter-controls') || null;
    }

    function filterControlsShareRow(left, right) {
      if (!left || !right) return false;
      const leftRect = left.getBoundingClientRect();
      const rightRect = right.getBoundingClientRect();
      const tolerance = Math.max(2, Math.min(leftRect.height || 0, rightRect.height || 0) * 0.25);
      return Math.abs(leftRect.top - rightRect.top) <= tolerance;
    }

    function syncFilterSortDivider(root) {
      const controls = filterControlsRoot(root || ctx.projectExplorerBody?.());
      if (!controls) return;
      const noteControl = controls.querySelector('.project-finding-note-state-control');
      const sortControl = controls.querySelector('.project-finding-source-order-control');
      if (!sortControl) return;
      sortControl.classList.remove('has-sort-divider');
      if (!noteControl) return;
      if (filterControlsShareRow(noteControl, sortControl)) {
        sortControl.classList.add('has-sort-divider');
        if (!filterControlsShareRow(noteControl, sortControl)) {
          sortControl.classList.remove('has-sort-divider');
        }
      }
    }

    function scheduleFilterSortDividerSync(root) {
      const schedule = typeof global.requestAnimationFrame === 'function'
        ? global.requestAnimationFrame.bind(global)
        : (typeof window.requestAnimationFrame === 'function'
          ? window.requestAnimationFrame.bind(window)
          : window.setTimeout.bind(window));
      schedule(() => syncFilterSortDivider(root || ctx.projectExplorerBody?.()));
    }

    return {
      clearAllFilters,
      filteredArtifacts,
      filteredFindingItems,
      filteredFindings,
      filteredRuns,
      findingFilteredKey,
      findingCommandFilterActive,
      findingCommandFilterSet,
      findingCommandFilterValues,
      findingCommandOptions,
      findingLabelFilterActive,
      findingLabelFilterSet,
      findingLabelFilterValues,
      findingLabelOptions,
      findingNoteStateFilterActive,
      findingNoteStateValue,
      findingOrphanFilterActive,
      findingOrphanFilterValue,
      findingServerFilterParams,
      findingServerFiltersActive,
      findingSeverityFilterActive,
      findingSeverityFilterSet,
      findingSeverityFilterValues,
      findingSeverityOptions,
      findingSortValue,
      findingStatusFilterActive,
      findingStatusFilterSet,
      findingStatusFilterValues,
      findingScopeFilterActive,
      findingScopeFilterSet,
      findingScopeFilterValues,
      findingScopeOptions,
      runDirectTargetIds,
      runFilterActive,
      runFilterChipLabel,
      runFilterIds,
      runFilterLabel,
      runFilterSet,
      runIdsMatchingTargets,
      runMatchesTargetFilters,
      renderFilterBar,
      setFilterMenuOpen,
      setFindingNoteState,
      setFindingOrphanFilter,
      setFindingSort,
      sortProjectFindings,
      targetById,
      targetFilterActive,
      targetFilterIds,
      targetFilterLabel,
      targetFilterSet,
      targetFilterableProjectTab,
      findingTargetIds,
      findingTargetText,
      closeFilterMenus,
      syncFilterSortDivider,
      scheduleFilterSortDividerSync,
    };
  }

  global.DarklabProjectFilters = {
    createProjectFiltersController,
  };
})(globalThis);
