// ── Run comparison controls ──────────────────────────────────────────────
// View/context controls and actions menu for the compare result viewer.

function _historyCompareApplyViewMode(mode, data) {
  const nextMode = _historyCompareCoerceViewMode(mode);
  data._compareViewModeRaw = nextMode;
  _renderHistoryComparison(data);
}

function _historyCompareApplyContext(mode, data) {
  const nextMode = _historyCompareCoerceContext(mode);
  data._compareContext = nextMode;
  _renderHistoryComparison(data);
}

function _closeHistoryCompareActionMenus(except = null) {
  document.querySelectorAll('.history-compare-actions-menu-wrap.open').forEach((wrap) => {
    if (except && wrap === except) return;
    wrap.classList.remove('open');
    wrap.querySelector('.history-compare-actions-trigger')?.setAttribute('aria-expanded', 'false');
    const menu = wrap._portaledMenu;
    if (menu && typeof unportalDropdownMenu === 'function') unportalDropdownMenu(menu);
    wrap._portaledMenu = null;
  });
}

function _renderHistoryCompareDisplayControls(data, viewMode) {
  const controls = document.createElement('div');
  controls.className = 'history-compare-controls';

  const defaultMode = _historyCompareCoerceViewMode(data._compareViewModeDefault || _historyCompareStoredViewMode());
  const rawMode = _historyCompareCoerceViewMode(data._compareViewModeRaw || defaultMode);
  const resolvedMode = _historyCompareResolveViewMode(rawMode);
  const viewSelect = document.createElement('select');
  viewSelect.className = 'form-select history-compare-view-select';
  viewSelect.setAttribute('aria-label', 'Run comparison view mode');
  viewSelect.dataset.portalMenu = 'true';
  _historyCompareViewModeOptions().forEach(([value, label]) => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = label;
    viewSelect.appendChild(option);
  });
  viewSelect.value = resolvedMode;
  viewSelect.addEventListener('change', () => _historyCompareApplyViewMode(viewSelect.value, data));
  controls.appendChild(viewSelect);

  const resetHidden = rawMode === defaultMode || (defaultMode === 'auto' && rawMode === _historyCompareViewportMode());
  const reset = document.createElement('button');
  reset.type = 'button';
  reset.className = 'btn btn-ghost btn-icon-only history-compare-reset-view';
  reset.setAttribute('aria-label', 'Reset comparison view to default');
  reset.title = 'Reset comparison view to default';
  const resetIcon = document.createElement('span');
  resetIcon.className = 'history-compare-reset-icon';
  resetIcon.setAttribute('aria-hidden', 'true');
  resetIcon.textContent = '↻';
  reset.appendChild(resetIcon);
  reset.hidden = resetHidden;
  reset.classList.toggle('u-hidden', resetHidden);
  reset.addEventListener('click', () => _historyCompareApplyViewMode(defaultMode, data));
  controls.appendChild(reset);

  const contextControls = _renderHistoryCompareContextControls(data, viewMode);
  if (contextControls) controls.appendChild(contextControls);

  if (typeof enhanceAppSelects === 'function') {
    enhanceAppSelects(controls);
  }
  return controls;
}

function _renderHistoryCompareContextControls(data, viewMode) {
  if (viewMode === 'changes_only' || viewMode === 'findings_only') return null;
  const selected = _historyCompareCoerceContext(data._compareContext || _historyCompareStoredContext());
  const contextSelect = document.createElement('select');
  contextSelect.className = 'form-select history-compare-context-select';
  contextSelect.setAttribute('aria-label', 'Run comparison context');
  contextSelect.dataset.portalMenu = 'true';
  [
    ['3', 'Context: ±3'],
    ['10', 'Context: ±10'],
    ['all', 'Context: All'],
  ].forEach(([value, label]) => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = label;
    contextSelect.appendChild(option);
  });
  contextSelect.value = selected;
  contextSelect.addEventListener('change', () => _historyCompareApplyContext(contextSelect.value, data));
  return contextSelect;
}

function _historyCompareSummaryText(data, deltas = {}) {
  const totalsForCopy = data.totals || {};
  return [
    `Compare: ${data.left.command} -> ${data.right.command}`,
    `Exit: ${deltas.exit_code?.left ?? 'n/a'} -> ${deltas.exit_code?.right ?? 'n/a'}`,
    `Lines: ${_compareFormatDelta(deltas.output_lines?.delta || 0)}`,
    `Findings: ${_compareFormatDelta(deltas.findings?.delta || 0)}`,
    `Changed: ${Number(totalsForCopy.changed_line_count || 0)}`,
    `Added: ${Number(totalsForCopy.added_line_count || 0)}`,
    `Removed: ${Number(totalsForCopy.removed_line_count || 0)}`,
    `Unchanged: ${Number(totalsForCopy.equal_line_count || 0)}`,
  ].join('\n');
}

function _renderHistoryCompareActionsMenu(data, deltas = {}) {
  const wrap = document.createElement('div');
  wrap.className = 'history-compare-actions-menu-wrap save-menu-wrap save-menu-down';
  const trigger = document.createElement('button');
  trigger.type = 'button';
  trigger.className = 'btn btn-secondary btn-compact history-compare-actions-trigger';
  trigger.textContent = 'Actions';
  trigger.setAttribute('aria-haspopup', 'menu');
  trigger.setAttribute('aria-expanded', 'false');
  const menu = document.createElement('div');
  menu.className = 'history-compare-actions-menu save-menu dropdown-surface';
  menu.setAttribute('role', 'menu');
  const addItem = (label, onClick) => {
    const item = document.createElement('button');
    item.type = 'button';
    item.className = 'dropdown-item dropdown-item-compact';
    item.setAttribute('role', 'menuitem');
    item.textContent = label;
    item.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      _closeHistoryCompareActionMenus();
      onClick(item);
    });
    menu.appendChild(item);
    return item;
  };
  addItem('Restore A', () => {
    restoreHistoryRunIntoTab(data.left, { hidePanelOnSuccess: false })
      .then(() => closeHistoryCompareOverlay())
      .catch(() => showToast('Failed to restore run', 'error'));
  });
  addItem('Restore B', () => {
    restoreHistoryRunIntoTab(data.right, { hidePanelOnSuccess: false })
      .then(() => closeHistoryCompareOverlay())
      .catch(() => showToast('Failed to restore run', 'error'));
  });
  addItem('Restore Both', (item) => {
    item.disabled = true;
    _restoreBothHistoryCompareRuns(data.left, data.right)
      .then(() => closeHistoryCompareOverlay())
      .catch(err => {
        item.disabled = false;
        if (err && err.message === 'not enough tab capacity') return;
        showToast('Failed to restore both runs', 'error');
      });
  });
  addItem('Copy summary', () => {
    copyTextToClipboard(_historyCompareSummaryText(data, deltas))
      .then(() => showToast('Comparison summary copied'))
      .catch(() => showToast('Failed to copy summary', 'error'));
  });
  wrap.dataset.portalMenu = 'true';
  trigger.addEventListener('click', (event) => {
    event.preventDefault();
    event.stopPropagation();
    const open = !wrap.classList.contains('open');
    _closeHistoryCompareActionMenus(open ? wrap : null);
    wrap.classList.toggle('open', open);
    trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open && typeof portalDropdownMenu === 'function') {
      portalDropdownMenu(wrap, trigger, menu);
      wrap._portaledMenu = menu;
    } else if (!open && typeof unportalDropdownMenu === 'function') {
      unportalDropdownMenu(menu);
      wrap._portaledMenu = null;
    }
  });
  if (typeof bindPressable === 'function') bindPressable(trigger);
  wrap.append(trigger, menu);
  return wrap;
}
