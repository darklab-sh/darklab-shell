// Project mobile run comparison sheet controller.
// Loaded before shell_chrome.js; shell chrome supplies the surrounding Projects state.

(function projectMobileCompareModule(global) {
  'use strict';

  function createProjectMobileCompareController(context) {
    const ctx = context || {};
    let overlay = null;
    let sheet = null;
    let title = null;
    let body = null;
    let footer = null;
    let returnFocus = null;
    let state = null;

    function compareRuns(projectId) {
      const summary = ctx.projectSummary(projectId);
      return ctx.projectComparableRuns(summary);
    }

    function targetOptions(compareState, runs) {
      if (compareState.mode === 'baseline') {
        return ctx.projectRunBaselineLabelOptions(runs).map(label => ({ value: label, label }));
      }
      return runs.map(run => ({
        value: String(run.id || ''),
        label: ctx.projectRunCompareOptionText(run),
      }));
    }

    function ensureTarget(compareState, runs) {
      const options = targetOptions(compareState, runs);
      const hasSelectedTarget = options.some(item => item.value === compareState.targetValue);
      if (!hasSelectedTarget || (compareState.mode === 'run' && compareState.targetValue === compareState.leftRunId)) {
        const fallback = options.find(item => compareState.mode === 'baseline' || item.value !== compareState.leftRunId) || options[0] || null;
        compareState.targetValue = fallback ? fallback.value : '';
      }
      if (compareState.mode === 'baseline' && compareState.targetValue) {
        const left = runs.find(run => String(run.id || '') === compareState.leftRunId);
        if (left && ctx.entityLabelValues(left).includes(compareState.targetValue)) {
          const leftFallback = runs.find(run => !ctx.entityLabelValues(run).includes(compareState.targetValue));
          if (leftFallback) compareState.leftRunId = String(leftFallback.id || '');
        }
      }
    }

    function selectionList(label, options, selectedValue, onSelect) {
      const wrap = document.createElement('div');
      wrap.className = 'project-mobile-compare-options';
      const heading = document.createElement('h3');
      heading.textContent = label;
      wrap.appendChild(heading);
      options.forEach((item) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn btn-ghost project-mobile-compare-option';
        btn.classList.toggle('is-active', String(item.value || '') === String(selectedValue || ''));
        btn.setAttribute('aria-pressed', String(item.value || '') === String(selectedValue || '') ? 'true' : 'false');
        btn.textContent = item.label || item.value;
        btn.addEventListener('click', () => onSelect(String(item.value || '')));
        ctx.bindProjectRuntimePressable(btn);
        wrap.appendChild(btn);
      });
      return wrap;
    }

    function ensureSheet() {
      if (overlay && sheet && body && footer) return overlay;
      overlay = document.createElement('div');
      overlay.id = 'project-mobile-compare-overlay';
      overlay.className = 'modal-overlay mobile-sheet-overlay project-mobile-compare-overlay u-hidden';
      overlay.setAttribute('aria-hidden', 'true');
      sheet = document.createElement('section');
      sheet.id = 'project-mobile-compare-sheet';
      sheet.className = 'modal-card mobile-sheet-surface project-mobile-compare-sheet';
      sheet.setAttribute('role', 'dialog');
      sheet.setAttribute('aria-modal', 'true');
      sheet.setAttribute('aria-labelledby', 'project-mobile-compare-title');
      const grab = document.createElement('div');
      grab.className = 'sheet-grab gesture-handle';
      grab.setAttribute('role', 'button');
      grab.tabIndex = 0;
      grab.setAttribute('aria-label', 'Close run comparison');
      const header = document.createElement('div');
      header.className = 'project-mobile-compare-header';
      title = document.createElement('h2');
      title.id = 'project-mobile-compare-title';
      title.textContent = 'Compare runs';
      header.appendChild(title);
      body = document.createElement('div');
      body.className = 'project-mobile-compare-body nice-scroll';
      footer = document.createElement('div');
      footer.className = 'project-mobile-compare-footer';
      sheet.append(grab, header, body, footer);
      overlay.appendChild(sheet);
      (ctx.projectWorkspaceModal || document.body).appendChild(overlay);

      overlay.addEventListener('click', (event) => {
        if (event.target === overlay) close();
      });
      const bindDismissibleFn = global && typeof global.bindDismissible === 'function'
        ? global.bindDismissible
        : null;
      if (bindDismissibleFn) {
        bindDismissibleFn(overlay, {
          level: 'sheet',
          isOpen: () => !!(overlay && overlay.classList.contains('open')),
          onClose: () => close(),
          backdropEl: overlay,
        });
      }
      const bindMobileSheetFn = global && typeof global.bindMobileSheet === 'function'
        ? global.bindMobileSheet
        : null;
      if (bindMobileSheetFn) bindMobileSheetFn(sheet, { onClose: () => close() });
      return overlay;
    }

    function close({ restoreFocus = true } = {}) {
      if (!overlay) return;
      overlay.classList.add('u-hidden');
      overlay.classList.remove('open');
      overlay.setAttribute('aria-hidden', 'true');
      state = null;
      if (body) body.replaceChildren();
      if (footer) footer.replaceChildren();
      if (
        restoreFocus
        && returnFocus
        && returnFocus.isConnected
        && typeof returnFocus.focus === 'function'
      ) {
        const focusTarget = returnFocus;
        window.setTimeout(() => focusTarget.focus(), 0);
      }
      returnFocus = null;
    }

    function render() {
      if (!state || !body || !footer) return;
      const runs = compareRuns(state.projectId);
      ensureTarget(state, runs);
      const stepLabels = ['Left run', 'Mode', state.mode === 'baseline' ? 'Label' : 'Right run'];
      if (title) title.textContent = `Compare runs: ${stepLabels[state.step]}`;
      body.replaceChildren();
      footer.replaceChildren();
      const stepper = document.createElement('div');
      stepper.className = 'project-mobile-compare-stepper';
      stepLabels.forEach((label, index) => {
        const item = document.createElement('span');
        item.className = 'project-mobile-compare-step';
        item.classList.toggle('is-active', index === state.step);
        item.textContent = label;
        stepper.appendChild(item);
      });
      body.appendChild(stepper);
      if (state.step === 0) {
        body.appendChild(selectionList(
          'Choose the run to compare',
          runs.map(run => ({ value: String(run.id || ''), label: ctx.projectRunCompareOptionText(run) })),
          state.leftRunId,
          (value) => {
            state.leftRunId = value;
            if (state.mode === 'run' && state.targetValue === value) ensureTarget(state, runs);
            render();
          },
        ));
      } else if (state.step === 1) {
        const modeOptions = [
          { value: 'run', label: 'Against run' },
          ...(ctx.projectRunBaselineLabelOptions(runs).length ? [{ value: 'baseline', label: 'Against label' }] : []),
        ];
        body.appendChild(selectionList(
          'Compare against',
          modeOptions,
          state.mode,
          (value) => {
            state.mode = value === 'baseline' ? 'baseline' : 'run';
            state.targetValue = '';
            ensureTarget(state, runs);
            render();
          },
        ));
      } else {
        body.appendChild(selectionList(
          state.mode === 'baseline' ? 'Choose a baseline label' : 'Choose the baseline run',
          targetOptions(state, runs),
          state.targetValue,
          (value) => {
            state.targetValue = value;
            render();
          },
        ));
      }
      const back = document.createElement('button');
      back.type = 'button';
      back.className = 'btn btn-ghost btn-compact';
      back.textContent = state.step === 0 ? 'Cancel' : 'Back';
      back.addEventListener('click', () => {
        if (state.step === 0) close();
        else {
          state.step -= 1;
          render();
        }
      });
      ctx.bindProjectRuntimePressable(back);
      const next = document.createElement('button');
      next.type = 'button';
      next.className = 'btn btn-primary btn-compact';
      next.textContent = state.step >= 2 ? 'Compare' : 'Next';
      next.addEventListener('click', () => {
        if (state.step < 2) {
          state.step += 1;
          render();
          return;
        }
        ctx.compareProjectRuns(state.projectId, state.leftRunId, state.mode, state.targetValue);
        ctx.closeProjectWorkspace({ refocus: false });
      });
      ctx.bindProjectRuntimePressable(next);
      footer.append(back, next);
    }

    function open(projectId, focusTarget = null) {
      const runs = compareRuns(projectId);
      if (runs.length < 2) {
        ctx.setProjectWorkspaceMessage('Link two runs to compare.');
        return;
      }
      state = {
        projectId: String(projectId || ''),
        step: 0,
        leftRunId: String(runs[0]?.id || ''),
        mode: 'run',
        targetValue: '',
      };
      ensureTarget(state, runs);
      ensureSheet();
      if (!overlay) return;
      returnFocus = focusTarget || document.activeElement || null;
      render();
      overlay.classList.remove('u-hidden');
      overlay.classList.add('open');
      overlay.setAttribute('aria-hidden', 'false');
      window.setTimeout(() => {
        body?.querySelector('button, select, input, textarea')?.focus();
      }, 0);
    }

    return {
      close,
      open,
    };
  }

  global.DarklabProjectMobileCompare = {
    createProjectMobileCompareController,
  };
})(globalThis);
