(function projectRunsModule(global) {
  'use strict';

  function createProjectRunsController(context) {
    const ctx = context || {};

    function runRemoveControl(projectId, run) {
      const btn = ctx.makeProjectButton('Remove', 'unlink-run', projectId);
      btn.dataset.runId = String(run.id || '');
      btn.dataset.runCommand = String(run.command || '');
      return btn;
    }

    function runFindingCount(projectId, runId) {
      const normalizedRunId = String(runId || '');
      if (!normalizedRunId || !ctx.projectFindingsLoaded(projectId)) return 0;
      return ctx.projectFindingItems(projectId)
        .filter(finding => String(finding && finding.run_id || '') === normalizedRunId).length;
    }

    function runArtifactCount(summary, runId) {
      const normalizedRunId = String(runId || '');
      if (!normalizedRunId) return 0;
      return ctx.projectArtifactItems(summary)
        .filter(artifact => String(artifact && artifact.run_id || '') === normalizedRunId).length;
    }

    function runControls(projectId, run, summary) {
      const runId = String(run && run.id || '');
      const wrap = document.createElement('div');
      wrap.className = 'project-run-row-actions';
      const counts = document.createElement('div');
      counts.className = 'project-run-row-counts';
      const countConfigs = [
        ['finding', runFindingCount(projectId, runId), 'filter-run-findings'],
      ];
      if (ctx.projectArtifactsVisible()) {
        countConfigs.push(['artifact', runArtifactCount(summary, runId), 'filter-run-artifacts']);
      }
      countConfigs.forEach(([label, count, action]) => {
        const chip = ctx.makeProjectButton(`${count} ${label}${count === 1 ? '' : 's'}`, action, projectId, count ? 'secondary' : 'ghost');
        chip.classList.add('project-run-count-chip');
        chip.disabled = !count;
        chip.dataset.runId = runId;
        chip.dataset.runCommand = String(run.command || '');
        counts.appendChild(chip);
      });
      const actions = document.createElement('div');
      actions.className = 'project-run-row-buttons';
      const edit = ctx.makeProjectButton('Edit', 'edit-run-metadata', projectId);
      edit.dataset.runId = runId;
      edit.dataset.runCommand = String(run.command || '');
      const restore = ctx.makeProjectButton('Restore', 'open-run', projectId);
      restore.dataset.runId = runId;
      restore.dataset.runCommand = String(run.command || '');
      actions.appendChild(edit);
      actions.appendChild(restore);
      actions.appendChild(runRemoveControl(projectId, run));
      wrap.append(counts, actions);
      return wrap;
    }

    function baselineLabelOptions(runs) {
      const labels = new Set();
      (Array.isArray(runs) ? runs : []).forEach((run) => {
        ctx.entityLabelValues(run).forEach(label => labels.add(label));
      });
      return [...labels].sort((left, right) => {
        if (left === 'baseline') return -1;
        if (right === 'baseline') return 1;
        return left.localeCompare(right, undefined, { sensitivity: 'base' });
      });
    }

    function compareOptionText(run) {
      const command = String(run && (run.command || run.id) || 'run');
      const labels = ctx.entityLabelValues(run);
      return labels.length ? `${command} · ${labels.join(', ')}` : command;
    }

    function compareDatasetOptions(container, key) {
      try {
        const parsed = JSON.parse(String(container?.dataset?.[key] || '[]'));
        return Array.isArray(parsed) ? parsed : [];
      } catch (_) {
        return [];
      }
    }

    function replaceCompareOptions(select, options, selectedValue = '') {
      if (!select) return;
      select.replaceChildren();
      (Array.isArray(options) ? options : []).forEach((item) => {
        const option = document.createElement('option');
        option.value = String(item && item.value || '');
        option.textContent = String(item && item.label || item && item.value || '');
        select.appendChild(option);
      });
      const normalizedSelected = String(selectedValue || '');
      if (normalizedSelected && [...select.options].some(option => option.value === normalizedSelected)) {
        select.value = normalizedSelected;
      } else if (select.options.length) {
        select.value = select.options[0].value;
      }
    }

    function compareOptionLabels(option) {
      return Array.isArray(option && option.labels)
        ? option.labels.map(label => String(label || '').trim()).filter(Boolean)
        : [];
    }

    function avoidCompareLabelSelfTarget(container, label) {
      const leftSelect = container?.querySelector?.('[data-project-compare-run="left"]');
      if (!leftSelect || !label) return;
      const runOptions = compareDatasetOptions(container, 'projectCompareRunOptions');
      const selected = runOptions.find(option => String(option && option.value || '') === String(leftSelect.value || ''));
      if (!selected || !compareOptionLabels(selected).includes(label)) return;
      const fallback = runOptions.find(option => !compareOptionLabels(option).includes(label));
      if (!fallback) return;
      leftSelect.value = String(fallback.value || '');
      if (typeof global.syncAppSelect === 'function') {
        global.syncAppSelect(leftSelect);
      }
    }

    function syncCompareMode(wrap) {
      const container = wrap || ctx.projectExplorerBody()?.querySelector('.project-run-compare-controls');
      if (!container) return;
      const mode = String(container.querySelector('[data-project-compare-mode]')?.value || 'run');
      const targetSelect = container.querySelector('[data-project-compare-target]');
      if (!targetSelect) return;
      const previousMode = String(targetSelect.dataset.projectCompareTargetMode || '');
      if (previousMode === 'run') targetSelect.dataset.projectCompareRunValue = targetSelect.value;
      if (previousMode === 'baseline') targetSelect.dataset.projectCompareBaselineValue = targetSelect.value;
      const options = mode === 'baseline'
        ? compareDatasetOptions(container, 'projectCompareLabelOptions')
        : compareDatasetOptions(container, 'projectCompareRunOptions');
      const savedValue = mode === 'baseline'
        ? targetSelect.dataset.projectCompareBaselineValue
        : targetSelect.dataset.projectCompareRunValue;
      replaceCompareOptions(targetSelect, options, savedValue);
      targetSelect.dataset.projectCompareTargetMode = mode;
      targetSelect.setAttribute('aria-label', mode === 'baseline' ? 'Baseline label' : 'Run baseline');
      if (mode === 'baseline') {
        avoidCompareLabelSelfTarget(container, String(targetSelect.value || ''));
      }
      if (typeof global.syncAppSelect === 'function') {
        global.syncAppSelect(targetSelect);
      }
      container.querySelectorAll('[data-project-compare-mode-value]').forEach((btn) => {
        const active = String(btn.dataset.projectCompareModeValue || '') === mode;
        btn.classList.toggle('is-active', active);
        btn.setAttribute('aria-pressed', active ? 'true' : 'false');
      });
    }

    function setCompareMode(modeButton, event = null) {
      event?.preventDefault?.();
      event?.stopPropagation?.();
      const controls = modeButton?.closest?.('.project-run-compare-controls');
      const modeInput = controls?.querySelector('[data-project-compare-mode]');
      if (!controls || !modeInput) return;
      modeInput.value = String(modeButton.dataset.projectCompareModeValue || 'run');
      syncCompareMode(controls);
    }

    function compareRuns(projectId, leftId, mode, targetValue, controls = null) {
      const normalizedProjectId = String(projectId || '').trim();
      const normalizedLeftId = String(leftId || '').trim();
      const normalizedMode = String(mode || 'run') === 'baseline' ? 'baseline' : 'run';
      const normalizedTarget = String(targetValue || '').trim();
      if (normalizedMode === 'baseline') {
        avoidCompareLabelSelfTarget(controls, normalizedTarget);
      }
      if (!normalizedProjectId || !normalizedLeftId) throw new Error('Choose a project run to compare.');
      if (normalizedMode === 'run' && !normalizedTarget) throw new Error('Choose two project runs to compare.');
      if (normalizedMode === 'run' && normalizedLeftId === normalizedTarget) throw new Error('Choose two different project runs to compare.');
      if (normalizedMode === 'baseline' && !normalizedTarget) throw new Error('Choose a baseline label to compare.');
      const compareFn = global && typeof global.fetchAndRenderHistoryComparison === 'function'
        ? global.fetchAndRenderHistoryComparison
        : (typeof window !== 'undefined' && typeof window.fetchAndRenderHistoryComparison === 'function'
          ? window.fetchAndRenderHistoryComparison
          : null);
      if (!compareFn) throw new Error('Run comparison is not available.');
      const params = new URLSearchParams({
        left: normalizedLeftId,
        project_id: normalizedProjectId,
      });
      if (normalizedMode === 'baseline') params.set('baseline_label', normalizedTarget);
      else params.set('right', normalizedTarget);
      compareFn(normalizedLeftId, normalizedMode === 'baseline' ? `baseline:${normalizedTarget}` : normalizedTarget, {
        url: `/history/compare?${params.toString()}`,
      });
    }

    function renderCompareControls(runs) {
      const wrap = document.createElement('div');
      wrap.className = 'project-run-compare-controls';
      const leftSelect = document.createElement('select');
      leftSelect.className = 'form-select form-control-compact project-run-compare-select';
      leftSelect.dataset.projectCompareRun = 'left';
      leftSelect.setAttribute('aria-label', 'Run to compare');
      const modeInput = document.createElement('input');
      modeInput.type = 'hidden';
      modeInput.dataset.projectCompareMode = '1';
      modeInput.value = 'run';
      const targetSelect = document.createElement('select');
      targetSelect.className = 'form-select form-control-compact project-run-compare-select';
      targetSelect.dataset.projectCompareTarget = '1';
      targetSelect.setAttribute('aria-label', 'Run baseline');
      const runOptions = [];
      runs.forEach((run, index) => {
        [leftSelect].forEach((select) => {
          const option = document.createElement('option');
          option.value = String(run.id || '');
          option.textContent = compareOptionText(run);
          select.appendChild(option);
        });
        runOptions.push({
          value: String(run.id || ''),
          label: compareOptionText(run),
          labels: ctx.entityLabelValues(run),
        });
        if (index === 0) leftSelect.value = String(run.id || '');
        if (index === 1) targetSelect.dataset.projectCompareRunValue = String(run.id || '');
      });
      const baselineLabels = baselineLabelOptions(runs);
      const baselineOptions = baselineLabels.map(label => ({ value: label, label }));
      targetSelect.dataset.projectCompareBaselineValue = baselineLabels.includes('baseline') ? 'baseline' : (baselineLabels[0] || '');
      wrap.dataset.projectCompareRunOptions = JSON.stringify(runOptions);
      wrap.dataset.projectCompareLabelOptions = JSON.stringify(baselineOptions);
      const modeGroup = document.createElement('div');
      modeGroup.className = 'project-run-compare-mode-group';
      modeGroup.setAttribute('role', 'group');
      modeGroup.setAttribute('aria-label', 'Compare against');
      modeGroup.hidden = !baselineLabels.length;
      [
        ['run', 'Run'],
        ['baseline', 'Label'],
      ].forEach(([value, label]) => {
        if (value === 'baseline' && !baselineLabels.length) return;
        const modeBtn = document.createElement('button');
        modeBtn.type = 'button';
        modeBtn.className = 'toggle-btn project-run-compare-mode-button';
        modeBtn.dataset.projectCompareModeValue = value;
        modeBtn.setAttribute('aria-pressed', value === modeInput.value ? 'true' : 'false');
        modeBtn.textContent = label;
        modeBtn.addEventListener('click', event => setCompareMode(modeBtn, event));
        ctx.bindProjectRuntimePressable(modeBtn);
        modeGroup.appendChild(modeBtn);
      });
      wrap.append(leftSelect, modeInput, modeGroup, targetSelect);
      syncCompareMode(wrap);
      return wrap;
    }

    function renderRuns(container, projectId, summary) {
      const allRuns = ctx.projectRunItems(summary);
      const comparableRuns = ctx.projectComparableRuns(summary);
      const filterActive = ctx.projectTargetFilterActive(projectId, summary);
      const toolbar = document.createElement('div');
      toolbar.className = 'project-runs-toolbar';
      toolbar.appendChild(renderCompareControls(comparableRuns));
      const toolbarActions = document.createElement('div');
      toolbarActions.className = 'project-runs-toolbar-actions';
      const compare = ctx.makeProjectButton('Compare runs', 'compare-runs', projectId, comparableRuns.length >= 2 ? 'secondary' : 'ghost');
      compare.disabled = comparableRuns.length < 2;
      if (compare.disabled) {
        compare.title = 'Link two runs to compare.';
        compare.setAttribute('aria-disabled', 'true');
      } else {
        compare.title = 'Compare selected project runs.';
        compare.removeAttribute('aria-disabled');
      }
      const actionDivider = document.createElement('span');
      actionDivider.className = 'project-runs-toolbar-divider';
      actionDivider.setAttribute('aria-hidden', 'true');
      toolbarActions.append(compare, actionDivider, ctx.makeProjectButton('Link last run', 'link-last-run', projectId));
      toolbar.appendChild(toolbarActions);
      container.appendChild(toolbar);
      if (filterActive && !ctx.projectFindingsLoaded(projectId)) {
        container.appendChild(ctx.emptyProjectPanel('Loading target associations...'));
        return;
      }
      const runs = ctx.filteredProjectRuns(projectId, summary);
      if (!allRuns.length) {
        container.appendChild(ctx.emptyProjectPanel('No linked runs yet.'));
        return;
      }
      if (!runs.length) {
        container.appendChild(ctx.emptyProjectPanel('No linked runs match the selected filters.'));
        return;
      }
      runs.forEach((run) => {
        const exit = run.exit_code === null || run.exit_code === undefined ? 'running' : `exit ${run.exit_code}`;
        container.appendChild(ctx.projectItemRow({
          title: run.command,
          meta: ctx.formatDate(run.started),
          detail: `${exit} · ${Number(run.output_line_count || 0)} output lines · linked ${ctx.formatDate(run.created)}`,
          chips: ctx.entityMetadataChips(run),
          badge: run.id ? '' : exit,
          accessory: run.id ? runControls(projectId, run, summary) : null,
          action: run.id ? {
            action: 'filter-run',
            dataset: {
              projectId,
              runId: String(run.id || ''),
              runCommand: String(run.command || ''),
            },
          } : null,
        }));
      });
    }

    return {
      runRemoveControl,
      runFindingCount,
      runArtifactCount,
      runControls,
      baselineLabelOptions,
      compareOptionText,
      syncCompareMode,
      setCompareMode,
      avoidCompareLabelSelfTarget,
      compareRuns,
      renderCompareControls,
      renderRuns,
    };
  }

  global.DarklabProjectRuns = {
    createProjectRunsController,
  };
})(globalThis);
