// darklab_shell History Run Details modal.
// Loaded after history.js so it can reuse History drawer, restore, metadata,
// project-link, and compare helpers without keeping the modal in the drawer file.

let _historyRunModalState = {
  run: null,
  details: null,
  findings: null,
  findingsPagination: null,
  entitySummary: null,
  entitySummaryLoaded: false,
  entities: null,
  entitiesPagination: null,
  activeEntityTab: 'ip',
  projectState: null,
  activeTab: 'summary',
  loadingDetails: false,
  loadingFindings: false,
  loadingEntitySummary: false,
  loadingEntities: false,
  loadingProject: false,
  error: '',
};
let _historyRunModalToken = 0;
const HISTORY_RUN_FINDINGS_PAGE_LIMIT = 50;
const HISTORY_RUN_ENTITIES_PAGE_LIMIT = 50;

function _historyRunCountLabel(count, singular, plural) {
  const numeric = Math.max(0, Number(count || 0));
  return `${numeric.toLocaleString()} ${numeric === 1 ? singular : plural}`;
}

function _historyRunSelectorValue(value) {
  if (typeof CSS !== 'undefined' && CSS && typeof CSS.escape === 'function') {
    return CSS.escape(String(value));
  }
  return String(value || '').replace(/["\\]/g, '\\$&');
}

function _ensureHistoryRunOverlay() {
  let overlay = document.getElementById('history-run-overlay');
  if (overlay) return overlay;

  overlay = document.createElement('div');
  overlay.id = 'history-run-overlay';
  overlay.className = 'modal-overlay mobile-sheet-overlay u-hidden history-run-overlay';
  overlay.innerHTML = `
    <section id="history-run-modal" class="history-run-modal mobile-sheet-surface" role="dialog" aria-modal="true" aria-labelledby="history-run-title">
      <div class="sheet-grab gesture-handle" role="button" tabindex="0" aria-label="Close run details"></div>
      <div class="history-run-header surface-header">
        <div class="history-run-heading">
          <div id="history-run-title" class="history-run-title">RUN DETAILS</div>
          <div id="history-run-subtitle" class="history-run-subtitle"></div>
        </div>
        <button type="button" class="close-btn history-run-close" aria-label="Close run details">✕</button>
      </div>
      <div class="history-run-tabs tab-strip" role="tablist" aria-label="Run details sections">
        <button type="button" class="tab-strip-item history-run-tab" data-history-run-tab="summary" role="tab">Summary</button>
        <button type="button" class="tab-strip-item history-run-tab" data-history-run-tab="output" role="tab">Output</button>
        <button type="button" class="tab-strip-item history-run-tab" data-history-run-tab="findings" role="tab">Findings</button>
        <button type="button" class="tab-strip-item history-run-tab" data-history-run-tab="entities" role="tab">Entities</button>
        <button type="button" class="tab-strip-item history-run-tab" data-history-run-tab="artifacts" role="tab">Artifacts</button>
      </div>
      <div id="history-run-body" class="history-run-body surface-body nice-scroll"></div>
    </section>
  `;
  document.body.appendChild(overlay);
  overlay.addEventListener('click', e => {
    if (e.target === overlay) closeHistoryRunOverlay();
    const menuTrigger = e.target.closest?.('.history-run-action-menu-trigger');
    if (menuTrigger) {
      e.preventDefault();
      e.stopPropagation();
      const wrap = menuTrigger.closest('.history-run-action-menu-wrap');
      if (!wrap) return;
      const open = !wrap.classList.contains('open');
      _closeHistoryRunActionMenus(open ? wrap : null);
      wrap.classList.toggle('open', open);
      menuTrigger.setAttribute('aria-expanded', open ? 'true' : 'false');
      return;
    }
    const tab = e.target.closest?.('[data-history-run-tab]');
    if (tab) {
      _setHistoryRunOverlayTab(tab.dataset.historyRunTab || 'summary');
      return;
    }
    const findingsPage = e.target.closest?.('[data-history-run-findings-page]');
    if (findingsPage) {
      e.preventDefault();
      _setHistoryRunFindingsPage(findingsPage.dataset.historyRunFindingsPage || '');
      return;
    }
    const entityTab = e.target.closest?.('[data-history-run-entity-tab]');
    if (entityTab) {
      e.preventDefault();
      _setHistoryRunEntityTab(entityTab.dataset.historyRunEntityTab || '');
      return;
    }
    const entityPage = e.target.closest?.('[data-history-run-entities-page]');
    if (entityPage) {
      e.preventDefault();
      _setHistoryRunEntitiesPage(entityPage.dataset.historyRunEntitiesPage || '');
      return;
    }
    const entityRow = e.target.closest?.('[data-history-run-entity-id]');
    if (entityRow) {
      e.preventDefault();
      _openHistoryRunEntityInAtlas(entityRow.dataset.historyRunEntityId || '');
      return;
    }
    const action = e.target.closest?.('[data-history-run-action]');
    if (action) {
      _closeHistoryRunActionMenus();
      _handleHistoryRunModalAction(String(action.dataset.historyRunAction || ''));
    }
  });
  overlay.querySelectorAll('.history-run-close, .sheet-grab').forEach(el => {
    el.addEventListener('click', () => closeHistoryRunOverlay());
    el.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        closeHistoryRunOverlay();
      }
    });
  });
  if (typeof bindDismissible === 'function') {
    bindDismissible(overlay, {
      level: 'modal',
      isOpen: () => overlay.classList.contains('open'),
      onClose: closeHistoryRunOverlay,
      closeButtons: overlay.querySelectorAll('.history-run-close, .sheet-grab'),
    });
  }
  return overlay;
}

function closeHistoryRunOverlay() {
  const overlay = document.getElementById('history-run-overlay');
  if (!overlay) return;
  overlay.classList.remove('open');
  overlay.classList.add('u-hidden');
  overlay.setAttribute('aria-hidden', 'true');
  window.syncModalOverlayState?.();
  _historyRunModalToken += 1;
  _closeHistoryRunActionMenus();
}

function _openHistoryRunOverlay() {
  const overlay = _ensureHistoryRunOverlay();
  overlay.classList.remove('u-hidden');
  overlay.classList.add('open');
  overlay.setAttribute('aria-hidden', 'false');
  window.syncModalOverlayState?.();
}

function isHistoryRunOverlayOpen() {
  const overlay = document.getElementById('history-run-overlay');
  return !!(overlay && overlay.classList.contains('open'));
}

function _setHistoryRunOverlayTab(tabId, { focus = false } = {}) {
  const overlay = _ensureHistoryRunOverlay();
  const nextTab = String(tabId || 'summary');
  const tabSelector = `[data-history-run-tab="${_historyRunSelectorValue(nextTab)}"]`;
  if (!overlay.querySelector(tabSelector)) return false;
  _closeHistoryRunActionMenus();
  _historyRunModalState.activeTab = nextTab;
  _renderHistoryRunModal();
  if (focus) {
    window.setTimeout(() => {
      overlay.querySelector(tabSelector)?.focus({ preventScroll: true });
    }, 0);
  }
  return true;
}

function cycleHistoryRunOverlayTab(offset = 1) {
  const overlay = document.getElementById('history-run-overlay');
  if (!isHistoryRunOverlayOpen() || !overlay) return false;
  const tabs = Array.from(overlay.querySelectorAll('[data-history-run-tab]'))
    .filter(tab => !tab.disabled);
  if (tabs.length < 2) return false;
  const currentId = String(_historyRunModalState.activeTab || 'summary');
  const currentIndex = Math.max(0, tabs.findIndex(tab => String(tab.dataset.historyRunTab || '') === currentId));
  const nextIndex = (currentIndex + Number(offset || 1) + tabs.length) % tabs.length;
  return _setHistoryRunOverlayTab(tabs[nextIndex].dataset.historyRunTab || 'summary');
}

function _historyRunDisplay(run = _historyRunModalState.run) {
  return run && run.command ? String(run.command) : 'run';
}

function _historyRunPrimary() {
  return _historyRunModalState.details || _historyRunModalState.run || {};
}

function _historyRunOutputEntries(run) {
  if (Array.isArray(run.output_entries)) {
    return run.output_entries.map(entry => ({
      text: String(entry && typeof entry === 'object' ? entry.text || '' : entry || ''),
      cls: String(entry && typeof entry === 'object' ? entry.cls || '' : ''),
    }));
  }
  if (Array.isArray(run.output)) {
    return run.output.map(line => ({ text: String(line || ''), cls: '' }));
  }
  if (run.output_preview) {
    return String(run.output_preview).split(/\r?\n/).map(line => ({ text: line, cls: '' }));
  }
  return [];
}

function _historyRunMetaRow(label, value) {
  const row = document.createElement('div');
  row.className = 'history-run-meta-row';
  const key = document.createElement('span');
  key.textContent = label;
  const val = document.createElement('strong');
  val.textContent = value == null || value === '' ? '—' : String(value);
  row.append(key, val);
  return row;
}

function _historyRunActionButton(label, action, { disabled = false, tone = 'secondary' } = {}) {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = `btn btn-${tone} btn-compact`;
  btn.dataset.historyRunAction = action;
  btn.textContent = label;
  btn.disabled = !!disabled;
  return btn;
}

function _historyRunCanOpenAtlas(run = _historyRunPrimary()) {
  return String(run?.run_kind || 'external') !== 'builtin';
}

function _historyRunEntityTabs() {
  const atlasTabs = window.DarklabAtlasTabs && Array.isArray(window.DarklabAtlasTabs.tabs)
    ? window.DarklabAtlasTabs.tabs
    : [
        { id: 'ip', label: 'Hosts/IPs', type: 'ip', countKey: 'ip' },
        { id: 'domain', label: 'Domains', type: 'domain', countKey: 'domain' },
        { id: 'hash', label: 'Hashes', type: 'hash', countKey: 'hash' },
        { id: 'cve', label: 'CVEs', type: 'cve', countKey: 'cve' },
        { id: 'url', label: 'URLs', type: 'url', countKey: 'url' },
      ];
  return atlasTabs.filter(tab => tab && tab.id !== 'findings' && tab.type);
}

function _historyRunActiveEntityTab() {
  const tabs = _historyRunEntityTabs();
  const activeId = String(_historyRunModalState.activeEntityTab || '');
  return tabs.find(tab => tab.id === activeId) || tabs[0] || { id: 'ip', label: 'Hosts/IPs', type: 'ip', countKey: 'ip' };
}

function _historyRunEntityCount(type) {
  const summary = _historyRunModalState.entitySummary || {};
  const counts = summary.counts && typeof summary.counts === 'object' ? summary.counts : {};
  return Math.max(0, Number(counts[String(type || '')] || 0));
}

function _historyRunEntityTotal(run = _historyRunPrimary()) {
  const summary = _historyRunModalState.entitySummary || {};
  if (_historyRunModalState.entitySummaryLoaded) return Math.max(0, Number(summary.total || 0));
  return Math.max(0, Number(run.atlas_entity_count || 0));
}

function _historyRunEntityLabel(type) {
  if (window.DarklabAtlasTabs && typeof window.DarklabAtlasTabs.labelForType === 'function') {
    return window.DarklabAtlasTabs.labelForType(type);
  }
  const found = _historyRunEntityTabs().find(tab => tab.type === String(type || ''));
  return found ? found.label : 'Entities';
}

function _historyRunEntityPage() {
  return _historyRunModalState.entitiesPagination || {
    limit: HISTORY_RUN_ENTITIES_PAGE_LIMIT,
    offset: 0,
    total: 0,
    has_more: false,
    loaded: false,
  };
}

function _historyRunEntityRow(entity) {
  const rowApi = window.DarklabAtlasEntityRow || {};
  const tab = _historyRunActiveEntityTab();
  if (typeof rowApi.renderAtlasEntityRow === 'function') {
    const row = rowApi.renderAtlasEntityRow({
      entity,
      text: value => String(value ?? '').trim(),
      countLabel: _historyRunCountLabel,
    });
    row.dataset.historyRunEntityId = String(entity && entity.id || '');
    row.title = 'Open this entity in Atlas';
    return row;
  }
  const row = document.createElement('button');
  row.type = 'button';
  row.className = 'chrome-row chrome-row-clickable history-run-entity-row';
  row.dataset.historyRunEntityId = String(entity && entity.id || '');
  const title = document.createElement('div');
  title.className = 'history-run-list-title';
  title.textContent = entity.canonical_value || entity.id || _historyRunEntityLabel(tab.type);
  const meta = document.createElement('div');
  meta.className = 'history-run-list-meta';
  meta.textContent = `${_historyRunCountLabel(entity.occurrence_count || 0, 'hit', 'hits')} · ${_historyRunCountLabel(entity.run_count || 0, 'run', 'runs')}`;
  row.append(title, meta);
  return row;
}

function _historyRunActionMenu() {
  const wrap = document.createElement('div');
  wrap.className = 'history-run-action-menu-wrap save-menu-wrap';
  const trigger = document.createElement('button');
  trigger.type = 'button';
  trigger.className = 'btn btn-secondary btn-compact history-run-action-menu-trigger';
  trigger.textContent = 'Actions';
  trigger.setAttribute('aria-haspopup', 'menu');
  trigger.setAttribute('aria-expanded', 'false');
  const menu = document.createElement('div');
  menu.className = 'history-run-action-menu save-menu dropdown-surface';
  menu.setAttribute('role', 'menu');
  const items = [
    ['copy-command', 'Copy command'],
    ['edit-metadata', 'Edit metadata'],
  ];
  if (_historyRunCanOpenAtlas()) items.push(['open-atlas', 'Open in Atlas']);
  const projectLinks = typeof _historyRunProjectLinks === 'function'
    ? _historyRunProjectLinks(_historyRunPrimary())
    : [];
  if (projectLinks.length) {
    items.push(['remove-project', 'Remove from project']);
  } else {
    items.push(
      ['add-active-project', 'Add to active project'],
      ['add-project', 'Add to project'],
    );
  }
  items.push(['copy-run-id', 'Copy run ID']);
  items.forEach(([action, label]) => {
    const item = document.createElement('button');
    item.type = 'button';
    item.className = 'dropdown-item dropdown-item-compact';
    item.dataset.historyRunAction = action;
    item.setAttribute('role', 'menuitem');
    item.textContent = label;
    menu.appendChild(item);
  });
  wrap.append(trigger, menu);
  return wrap;
}

function _historyRunSectionHeader(title, action = null) {
  const header = document.createElement('div');
  header.className = 'history-run-section-header';
  const heading = document.createElement('h3');
  heading.textContent = title;
  header.appendChild(heading);
  if (action) header.appendChild(action);
  return header;
}

function _historyRunField(label, content) {
  const row = document.createElement('div');
  row.className = 'history-run-field';
  const key = document.createElement('span');
  key.className = 'history-run-field-label';
  key.textContent = label;
  const value = document.createElement('div');
  value.className = 'history-run-field-value';
  if (typeof content === 'string') {
    value.textContent = content;
  } else if (content) {
    value.appendChild(content);
  }
  row.append(key, value);
  return row;
}

function _renderHistoryRunSummary(body, run) {
  const findingItems = Array.isArray(_historyRunModalState.findings) ? _historyRunModalState.findings : null;
  const findingPagination = _historyRunModalState.findingsPagination || {};
  const uniqueFindingCount = findingPagination.loaded
    ? Number(findingPagination.total || 0)
    : (findingItems ? findingItems.length : null);
  const occurrenceCount = findingPagination.loaded
    ? Number(findingPagination.occurrence_total || 0)
    : Number(run.finding_count || 0);
  const uniqueFindingLabel = uniqueFindingCount == null
    ? (_historyRunModalState.loadingFindings ? 'Loading...' : '0')
    : uniqueFindingCount.toLocaleString();
  const occurrenceLabel = Number.isFinite(occurrenceCount) ? occurrenceCount.toLocaleString() : '0';
  const summary = document.createElement('div');
  summary.className = 'history-run-summary-grid';
  const summaryRows = [
    _historyRunMetaRow('Status', _historyExitLabel(run.exit_code)),
    _historyRunMetaRow('Started', run.started ? new Date(run.started).toLocaleString() : ''),
    _historyRunMetaRow('Finished', run.finished ? new Date(run.finished).toLocaleString() : ''),
    _historyRunMetaRow('Duration', _historyElapsedLabel(run)),
    _historyRunMetaRow('Lines', run.output_line_count ? Number(run.output_line_count).toLocaleString() : ''),
    _historyRunMetaRow('Findings / Occurrences', `${uniqueFindingLabel} / ${occurrenceLabel}`),
    _historyRunMetaRow('Entities', _historyRunEntityTotal(run).toLocaleString()),
    _historyRunMetaRow(
      'Artifacts',
      Number(run.artifact_count || (Array.isArray(run.artifacts) ? run.artifacts.length : 0) || 0).toLocaleString(),
    ),
  ];
  if (run.schedule_id) {
    summaryRows.splice(1, 0, _historyRunMetaRow('Schedule', `scheduled · ${run.schedule_id}`));
  }
  summary.append(...summaryRows);
  body.appendChild(summary);

  const context = document.createElement('div');
  context.className = 'history-run-context-grid';

  const metadata = document.createElement('div');
  metadata.className = 'history-run-section';
  metadata.appendChild(_historyRunSectionHeader(
    'Metadata',
    _historyRunActionButton('Edit', 'edit-metadata'),
  ));

  const metadataFields = document.createElement('div');
  metadataFields.className = 'history-run-field-list';
  const chips = document.createElement('div');
  chips.className = 'history-run-chip-row';
  _historyEntityLabelValues(run).forEach((label) => {
    const chip = document.createElement('span');
    chip.className = 'badge badge-tone-muted';
    chip.textContent = label;
    chips.appendChild(chip);
  });
  if (!chips.childElementCount) {
    const empty = document.createElement('span');
    empty.className = 'history-run-muted';
    empty.textContent = 'No labels saved.';
    chips.appendChild(empty);
  }
  metadataFields.appendChild(_historyRunField('Labels', chips));
  const noteText = document.createElement('p');
  noteText.className = 'history-run-muted history-run-note-preview';
  noteText.textContent = _historyEntityNoteBody(run) || 'No notes saved.';
  metadataFields.appendChild(_historyRunField('Notes', noteText));
  metadata.appendChild(metadataFields);
  context.appendChild(metadata);

  const project = document.createElement('div');
  project.className = 'history-run-section';
  const projectState = _historyRunModalState.projectState;
  const canAddToProject = !!(
    projectState
    && projectState.project
    && !projectState.attached
    && !_historyRunModalState.loadingProject
  );
  project.appendChild(_historyRunSectionHeader(
    'Current project',
    canAddToProject ? _historyRunActionButton('Add', 'add-active-project') : null,
  ));
  const projectFields = document.createElement('div');
  projectFields.className = 'history-run-field-list';
  const projectStatus = document.createElement('span');
  projectStatus.className = 'badge badge-tone-muted';
  let projectName = '—';
  if (_historyRunModalState.loadingProject) {
    projectStatus.textContent = 'Checking';
  } else if (!projectState || !projectState.project) {
    projectStatus.textContent = 'No active project';
  } else if (projectState.attached) {
    projectStatus.className = 'badge badge-tone-cyan';
    projectStatus.textContent = 'Attached';
    projectName = _historyProjectDisplayName(projectState.project);
  } else {
    projectStatus.textContent = 'Not attached';
    projectName = _historyProjectDisplayName(projectState.project);
  }
  projectFields.appendChild(_historyRunField('Status', projectStatus));
  projectFields.appendChild(_historyRunField('Project', projectName));
  project.appendChild(projectFields);
  context.appendChild(project);
  body.appendChild(context);

  const actions = document.createElement('div');
  actions.className = 'history-run-actions history-run-primary-actions';
  actions.append(
    _historyRunActionButton('Restore', 'restore'),
    _historyRunActionButton('Delete', 'delete'),
    _historyRunActionButton('Permalink', 'permalink'),
    _historyRunActionButton('Compare', 'compare'),
  );
  if (_historyRunCanOpenAtlas(run)) actions.appendChild(_historyRunActionButton('Atlas', 'open-atlas'));
  actions.appendChild(_historyRunActionMenu());
  body.appendChild(actions);
}

function _renderHistoryRunOutput(body, run) {
  const output = _historyRunOutputEntries(run);
  if (!output.length && _historyRunModalState.loadingDetails) {
    const loading = document.createElement('div');
    loading.className = 'history-run-empty';
    loading.textContent = 'Loading output preview...';
    body.appendChild(loading);
    return;
  }
  if (!output.length) {
    const empty = document.createElement('div');
    empty.className = 'history-run-empty';
    empty.textContent = 'No saved output preview is available.';
    body.appendChild(empty);
    return;
  }
  const pre = document.createElement('pre');
  pre.className = 'history-run-output';
  pre.textContent = output.map(entry => entry.text).join('\n');
  body.appendChild(pre);
  if (run.preview_notice) {
    const notice = document.createElement('div');
    notice.className = 'history-run-notice';
    notice.textContent = run.preview_notice;
    body.appendChild(notice);
  }
}

function _renderHistoryRunFindings(body) {
  if (_historyRunModalState.loadingFindings && _historyRunModalState.findings == null) {
    const loading = document.createElement('div');
    loading.className = 'history-run-empty';
    loading.textContent = 'Loading findings...';
    body.appendChild(loading);
    return;
  }
  const findings = Array.isArray(_historyRunModalState.findings) ? _historyRunModalState.findings : [];
  const pager = _renderHistoryRunFindingsPagination(findings);
  if (!findings.length) {
    const empty = document.createElement('div');
    empty.className = 'history-run-empty';
    empty.textContent = 'No structured findings recorded for this run.';
    body.appendChild(empty);
    if (pager) body.appendChild(pager);
    return;
  }
  if (pager) body.appendChild(pager);
  const list = document.createElement('div');
  list.className = 'history-run-list';
  findings.forEach((finding) => {
    const item = document.createElement('div');
    item.className = 'history-run-list-item';
    const title = document.createElement('div');
    title.className = 'history-run-list-title';
    title.textContent = finding.title || finding.raw_line || 'Finding';
    const meta = document.createElement('div');
    meta.className = 'history-run-list-meta';
    const parts = [
      finding.severity ? `severity: ${finding.severity}` : '',
      finding.review_state ? `review: ${finding.review_state}` : '',
      Number.isFinite(Number(finding.line_number)) ? `line ${Number(finding.line_number) + 1}` : '',
      Number(finding.run_occurrence_count || 0) > 1
        ? `${Number(finding.run_occurrence_count).toLocaleString()} occurrences`
        : '',
      finding.scope ? `scope: ${finding.scope}` : '',
    ].filter(Boolean);
    meta.textContent = parts.join(' · ');
    item.append(title, meta);
    if (finding.raw_line && finding.raw_line !== finding.title) {
      const raw = document.createElement('code');
      raw.className = 'history-run-finding-raw';
      raw.textContent = finding.raw_line;
      item.appendChild(raw);
    }
    list.appendChild(item);
  });
  body.appendChild(list);
  if (pager) body.appendChild(_renderHistoryRunFindingsPagination(findings));
}

function _renderHistoryRunFindingsPagination(findings) {
  const pagination = _historyRunModalState.findingsPagination || {};
  const limit = Math.max(1, Number(pagination.limit || HISTORY_RUN_FINDINGS_PAGE_LIMIT));
  const offset = Math.max(0, Number(pagination.offset || 0));
  const total = Math.max(0, Number(pagination.total || findings.length || 0));
  if (total <= limit && offset === 0) return null;
  const start = total && findings.length ? offset + 1 : 0;
  const end = total && findings.length ? Math.min(total, offset + findings.length) : 0;
  const wrap = document.createElement('div');
  wrap.className = 'history-run-findings-pagination history-pagination';
  const summary = document.createElement('div');
  summary.className = 'history-pagination-summary';
  summary.textContent = `${start}-${end} of ${total.toLocaleString()} findings`;
  const controls = document.createElement('div');
  controls.className = 'history-pagination-controls';
  const prev = document.createElement('button');
  prev.type = 'button';
  prev.className = 'btn btn-secondary btn-compact';
  prev.dataset.historyRunFindingsPage = 'prev';
  prev.disabled = offset <= 0 || _historyRunModalState.loadingFindings;
  prev.textContent = 'Previous';
  const status = document.createElement('span');
  status.className = 'history-pagination-status';
  status.textContent = `Page ${Math.floor(offset / limit) + 1}`;
  const next = document.createElement('button');
  next.type = 'button';
  next.className = 'btn btn-secondary btn-compact';
  next.dataset.historyRunFindingsPage = 'next';
  next.disabled = offset + findings.length >= total || _historyRunModalState.loadingFindings;
  next.textContent = 'Next';
  controls.append(prev, status, next);
  wrap.append(summary, controls);
  return wrap;
}

function _renderHistoryRunEntityTabs(body) {
  const tabs = _historyRunEntityTabs();
  if (!tabs.length) return;
  const strip = document.createElement('div');
  strip.className = 'history-run-entity-tabs tab-strip';
  strip.setAttribute('role', 'tablist');
  strip.setAttribute('aria-label', 'Run Atlas entity types');
  const activeId = _historyRunActiveEntityTab().id;
  tabs.forEach((tab) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'tab-strip-item history-run-entity-tab';
    button.classList.toggle('is-active', tab.id === activeId);
    button.dataset.historyRunEntityTab = tab.id;
    button.setAttribute('role', 'tab');
    button.setAttribute('aria-selected', tab.id === activeId ? 'true' : 'false');
    button.textContent = `${tab.label} (${_historyRunEntityCount(tab.type).toLocaleString()})`;
    strip.appendChild(button);
  });
  body.appendChild(strip);
}

function _renderHistoryRunEntities(body) {
  _renderHistoryRunEntityTabs(body);
  if (_historyRunModalState.loadingEntities && _historyRunModalState.entities == null) {
    const loading = document.createElement('div');
    loading.className = 'history-run-empty';
    loading.textContent = 'Loading Atlas entities...';
    body.appendChild(loading);
    return;
  }
  const entities = Array.isArray(_historyRunModalState.entities) ? _historyRunModalState.entities : [];
  const pager = _renderHistoryRunEntitiesPagination(entities);
  if (!entities.length) {
    const empty = document.createElement('div');
    empty.className = 'history-run-empty';
    const tab = _historyRunActiveEntityTab();
    empty.textContent = `No ${_historyRunEntityLabel(tab.type).toLowerCase()} recorded for this run.`;
    body.appendChild(empty);
    if (pager) body.appendChild(pager);
    return;
  }
  if (pager) body.appendChild(pager);
  const list = document.createElement('div');
  list.className = 'history-run-entity-list';
  entities.forEach(entity => list.appendChild(_historyRunEntityRow(entity)));
  body.appendChild(list);
  if (pager) body.appendChild(_renderHistoryRunEntitiesPagination(entities));
}

function _renderHistoryRunEntitiesPagination(entities) {
  const pagination = _historyRunEntityPage();
  const limit = Math.max(1, Number(pagination.limit || HISTORY_RUN_ENTITIES_PAGE_LIMIT));
  const offset = Math.max(0, Number(pagination.offset || 0));
  const total = Math.max(0, Number(pagination.total || entities.length || 0));
  if (total <= limit && offset === 0) return null;
  const start = total && entities.length ? offset + 1 : 0;
  const end = total && entities.length ? Math.min(total, offset + entities.length) : 0;
  const wrap = document.createElement('div');
  wrap.className = 'history-run-entities-pagination history-pagination';
  const summary = document.createElement('div');
  summary.className = 'history-pagination-summary';
  summary.textContent = `${start}-${end} of ${total.toLocaleString()} entities`;
  const controls = document.createElement('div');
  controls.className = 'history-pagination-controls';
  const prev = document.createElement('button');
  prev.type = 'button';
  prev.className = 'btn btn-secondary btn-compact';
  prev.dataset.historyRunEntitiesPage = 'prev';
  prev.disabled = offset <= 0 || _historyRunModalState.loadingEntities;
  prev.textContent = 'Previous';
  const status = document.createElement('span');
  status.className = 'history-pagination-status';
  status.textContent = `Page ${Math.floor(offset / limit) + 1}`;
  const next = document.createElement('button');
  next.type = 'button';
  next.className = 'btn btn-secondary btn-compact';
  next.dataset.historyRunEntitiesPage = 'next';
  next.disabled = offset + entities.length >= total || _historyRunModalState.loadingEntities;
  next.textContent = 'Next';
  controls.append(prev, status, next);
  wrap.append(summary, controls);
  return wrap;
}

function _renderHistoryRunArtifacts(body, run) {
  const artifacts = Array.isArray(run.artifacts) ? run.artifacts : [];
  if (_historyRunModalState.loadingDetails && !artifacts.length) {
    const loading = document.createElement('div');
    loading.className = 'history-run-empty';
    loading.textContent = 'Loading artifacts...';
    body.appendChild(loading);
    return;
  }
  if (!artifacts.length) {
    const empty = document.createElement('div');
    empty.className = 'history-run-empty';
    empty.textContent = 'No workspace artifacts recorded for this run.';
    body.appendChild(empty);
    return;
  }
  const list = document.createElement('div');
  list.className = 'history-run-list';
  artifacts.forEach((artifact) => {
    const item = document.createElement('div');
    item.className = 'history-run-list-item';
    const title = document.createElement('div');
    title.className = 'history-run-list-title';
    title.textContent = artifact.display_name || artifact.workspace_path || 'artifact';
    const meta = document.createElement('div');
    meta.className = 'history-run-list-meta';
    meta.textContent = [
      artifact.kind || '',
      artifact.workspace_path || '',
      artifact.byte_size ? `${Number(artifact.byte_size).toLocaleString()} bytes` : '',
    ].filter(Boolean).join(' · ');
    item.append(title, meta);
    list.appendChild(item);
  });
  body.appendChild(list);
}

function _renderHistoryRunModal() {
  const overlay = _ensureHistoryRunOverlay();
  const run = _historyRunPrimary();
  const subtitle = overlay.querySelector('#history-run-subtitle');
  if (subtitle) subtitle.textContent = _historyRunDisplay(run);
  overlay.querySelectorAll('[data-history-run-tab]').forEach((tab) => {
    const active = String(tab.dataset.historyRunTab || '') === _historyRunModalState.activeTab;
    tab.classList.toggle('is-active', active);
    tab.setAttribute('aria-selected', active ? 'true' : 'false');
    tab.setAttribute('aria-pressed', active ? 'true' : 'false');
  });
  const findingsTab = overlay.querySelector('[data-history-run-tab="findings"]');
  if (findingsTab) {
    const pagination = _historyRunModalState.findingsPagination || {};
    const count = pagination.loaded
      ? Number(pagination.total || 0)
      : Array.isArray(_historyRunModalState.findings)
      ? _historyRunModalState.findings.length
      : 0;
    findingsTab.textContent = count ? `Findings (${count})` : 'Findings';
  }
  const entitiesTab = overlay.querySelector('[data-history-run-tab="entities"]');
  if (entitiesTab) {
    const count = _historyRunEntityTotal(run);
    entitiesTab.textContent = count ? `Entities (${count})` : 'Entities';
  }
  const artifactsTab = overlay.querySelector('[data-history-run-tab="artifacts"]');
  if (artifactsTab) {
    const count = Number(run.artifact_count || (Array.isArray(run.artifacts) ? run.artifacts.length : 0) || 0);
    artifactsTab.textContent = count ? `Artifacts (${count})` : 'Artifacts';
  }
  const body = overlay.querySelector('#history-run-body');
  if (!body) return;
  body.replaceChildren();
  if (_historyRunModalState.error) {
    const error = document.createElement('div');
    error.className = 'history-run-notice is-error';
    error.textContent = _historyRunModalState.error;
    body.appendChild(error);
  }
  if (_historyRunModalState.activeTab === 'output') _renderHistoryRunOutput(body, run);
  else if (_historyRunModalState.activeTab === 'findings') _renderHistoryRunFindings(body);
  else if (_historyRunModalState.activeTab === 'entities') _renderHistoryRunEntities(body);
  else if (_historyRunModalState.activeTab === 'artifacts') _renderHistoryRunArtifacts(body, run);
  else _renderHistoryRunSummary(body, run);
}

async function _loadHistoryRunDetails(runId, token) {
  _historyRunModalState.loadingDetails = true;
  _renderHistoryRunModal();
  try {
    const resp = await apiFetch(`/history/${encodeURIComponent(runId)}?json&preview=1`, { cache: 'no-store' });
    if (resp.ok === false) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (token !== _historyRunModalToken) return;
    _historyRunModalState.details = { ...(_historyRunModalState.run || {}), ...(data || {}) };
  } catch (_) {
    if (token === _historyRunModalToken) _historyRunModalState.error = 'Could not load run details.';
  } finally {
    if (token === _historyRunModalToken) {
      _historyRunModalState.loadingDetails = false;
      _renderHistoryRunModal();
    }
  }
}

async function _loadHistoryRunFindings(runId, token, { offset = 0 } = {}) {
  _historyRunModalState.loadingFindings = true;
  _renderHistoryRunModal();
  const limit = HISTORY_RUN_FINDINGS_PAGE_LIMIT;
  const query = new URLSearchParams({
    limit: String(limit),
    offset: String(Math.max(0, Number(offset || 0))),
  });
  try {
    const resp = await apiFetch(`/entities/run/${encodeURIComponent(runId)}/findings?${query}`, { cache: 'no-store' });
    if (resp.ok === false) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (token !== _historyRunModalToken) return;
    const payload = data && typeof data === 'object' ? data : {};
    _historyRunModalState.findings = Array.isArray(payload.findings) ? payload.findings : [];
    _historyRunModalState.findingsPagination = {
      limit: Math.max(1, Number(payload.limit || limit)),
      offset: Math.max(0, Number(payload.offset || offset || 0)),
      total: Math.max(0, Number(payload.total || _historyRunModalState.findings.length || 0)),
      has_more: !!payload.has_more,
      occurrence_total: Math.max(0, Number(payload.occurrence_total || 0)),
      loaded: true,
    };
  } catch (_) {
    if (token === _historyRunModalToken) {
      _historyRunModalState.findings = [];
      _historyRunModalState.findingsPagination = {
        limit,
        offset: 0,
        total: 0,
        has_more: false,
        occurrence_total: 0,
        loaded: true,
      };
      _historyRunModalState.error = 'Could not load run findings.';
    }
  } finally {
    if (token === _historyRunModalToken) {
      _historyRunModalState.loadingFindings = false;
      _renderHistoryRunModal();
    }
  }
}

function _setHistoryRunFindingsPage(direction) {
  const run = _historyRunPrimary();
  if (!run || !run.id || _historyRunModalState.loadingFindings) return;
  const pagination = _historyRunModalState.findingsPagination || {};
  const findings = Array.isArray(_historyRunModalState.findings) ? _historyRunModalState.findings : [];
  const limit = Math.max(1, Number(pagination.limit || HISTORY_RUN_FINDINGS_PAGE_LIMIT));
  const currentOffset = Math.max(0, Number(pagination.offset || 0));
  const total = Math.max(0, Number(pagination.total || findings.length || 0));
  const maxOffset = Math.max(0, Math.floor(Math.max(0, total - 1) / limit) * limit);
  const nextOffset = direction === 'prev'
    ? Math.max(0, currentOffset - limit)
    : Math.min(maxOffset, currentOffset + limit);
  if (nextOffset === currentOffset) return;
  _loadHistoryRunFindings(run.id, _historyRunModalToken, { offset: nextOffset });
}

async function _loadHistoryRunEntitySummary(runId, token) {
  _historyRunModalState.loadingEntitySummary = true;
  _renderHistoryRunModal();
  const query = new URLSearchParams({
    run_id: String(runId || ''),
    orphan_filter: 'hide',
    suppression_filter: 'hide',
  });
  try {
    const resp = await apiFetch(`/atlas?${query}`, { cache: 'no-store' });
    if (resp.ok === false) throw new Error(`HTTP ${resp.status}`);
    const payload = await resp.json();
    if (token !== _historyRunModalToken) return;
    _historyRunModalState.entitySummary = payload && typeof payload === 'object' ? payload : { total: 0, counts: {} };
    _historyRunModalState.entitySummaryLoaded = true;
  } catch (_) {
    if (token === _historyRunModalToken) {
      _historyRunModalState.entitySummary = { total: 0, counts: {} };
      _historyRunModalState.entitySummaryLoaded = true;
      _historyRunModalState.error = 'Could not load run Atlas entity counts.';
    }
  } finally {
    if (token === _historyRunModalToken) {
      _historyRunModalState.loadingEntitySummary = false;
      _renderHistoryRunModal();
    }
  }
}

async function _loadHistoryRunEntities(runId, token, { offset = 0 } = {}) {
  _historyRunModalState.loadingEntities = true;
  _renderHistoryRunModal();
  const tab = _historyRunActiveEntityTab();
  const limit = HISTORY_RUN_ENTITIES_PAGE_LIMIT;
  const query = new URLSearchParams({
    run_id: String(runId || ''),
    type: String(tab.type || ''),
    limit: String(limit),
    offset: String(Math.max(0, Number(offset || 0))),
    orphan_filter: 'hide',
    suppression_filter: 'hide',
  });
  try {
    const resp = await apiFetch(`/atlas/entities?${query}`, { cache: 'no-store' });
    if (resp.ok === false) throw new Error(`HTTP ${resp.status}`);
    const payload = await resp.json();
    if (token !== _historyRunModalToken) return;
    _historyRunModalState.entities = Array.isArray(payload.entities) ? payload.entities : [];
    _historyRunModalState.entitiesPagination = {
      limit: Math.max(1, Number(payload.limit || limit)),
      offset: Math.max(0, Number(payload.offset || offset || 0)),
      total: Math.max(0, Number(payload.total || _historyRunModalState.entities.length || 0)),
      has_more: !!payload.has_more,
      loaded: true,
    };
  } catch (_) {
    if (token === _historyRunModalToken) {
      _historyRunModalState.entities = [];
      _historyRunModalState.entitiesPagination = {
        limit,
        offset: 0,
        total: 0,
        has_more: false,
        loaded: true,
      };
      _historyRunModalState.error = 'Could not load run Atlas entities.';
    }
  } finally {
    if (token === _historyRunModalToken) {
      _historyRunModalState.loadingEntities = false;
      _renderHistoryRunModal();
    }
  }
}

function _setHistoryRunEntityTab(tabId) {
  const run = _historyRunPrimary();
  if (!run || !run.id || _historyRunModalState.loadingEntities) return;
  const tabs = _historyRunEntityTabs();
  const next = tabs.find(tab => tab.id === String(tabId || ''));
  if (!next || next.id === _historyRunActiveEntityTab().id) return;
  _historyRunModalState.activeEntityTab = next.id;
  _historyRunModalState.entities = null;
  _historyRunModalState.entitiesPagination = {
    limit: HISTORY_RUN_ENTITIES_PAGE_LIMIT,
    offset: 0,
    total: 0,
    has_more: false,
    loaded: false,
  };
  _renderHistoryRunModal();
  _loadHistoryRunEntities(run.id, _historyRunModalToken);
}

function _setHistoryRunEntitiesPage(direction) {
  const run = _historyRunPrimary();
  if (!run || !run.id || _historyRunModalState.loadingEntities) return;
  const pagination = _historyRunEntityPage();
  const entities = Array.isArray(_historyRunModalState.entities) ? _historyRunModalState.entities : [];
  const limit = Math.max(1, Number(pagination.limit || HISTORY_RUN_ENTITIES_PAGE_LIMIT));
  const currentOffset = Math.max(0, Number(pagination.offset || 0));
  const total = Math.max(0, Number(pagination.total || entities.length || 0));
  const maxOffset = Math.max(0, Math.floor(Math.max(0, total - 1) / limit) * limit);
  const nextOffset = direction === 'prev'
    ? Math.max(0, currentOffset - limit)
    : Math.min(maxOffset, currentOffset + limit);
  if (nextOffset === currentOffset) return;
  _loadHistoryRunEntities(run.id, _historyRunModalToken, { offset: nextOffset });
}

function _openHistoryRunEntityInAtlas(entityId) {
  const run = _historyRunPrimary();
  const entity = (Array.isArray(_historyRunModalState.entities) ? _historyRunModalState.entities : [])
    .find(item => String(item && item.id || '') === String(entityId || ''));
  if (!run || !run.id || !entity || typeof openAtlas !== 'function') return;
  closeHistoryRunOverlay();
  void openAtlas({
    source: 'run-details',
    tab: _historyRunActiveEntityTab().id,
    runId: run.id,
    runLabel: run.command || run.label || run.id,
    entityValue: entity.canonical_value || '',
    forceView: 'detail',
  });
}

async function _loadHistoryRunProjectState(runId, token) {
  _historyRunModalState.loadingProject = true;
  _renderHistoryRunModal();
  try {
    const project = await _historyLoadActiveProject();
    if (token !== _historyRunModalToken) return;
    if (!project || !project.id) {
      _historyRunModalState.projectState = { project: null, attached: false };
      return;
    }
    const resp = await apiFetch(`/projects/${encodeURIComponent(project.id)}/summary`, { cache: 'no-store' });
    if (resp.ok === false) throw new Error(`HTTP ${resp.status}`);
    const summary = await resp.json();
    const runs = Array.isArray(summary.runs) ? summary.runs : [];
    _historyRunModalState.projectState = {
      project,
      attached: runs.some(item => String(item && item.id || '') === String(runId || '')),
    };
  } catch (_) {
    if (token === _historyRunModalToken) _historyRunModalState.projectState = { project: null, attached: false };
  } finally {
    if (token === _historyRunModalToken) {
      _historyRunModalState.loadingProject = false;
      _renderHistoryRunModal();
    }
  }
}

function openHistoryRunDetails(run) {
  if (!run || !run.id) return;
  _historyRunModalToken += 1;
  const token = _historyRunModalToken;
  _historyRunModalState = {
    run,
    details: null,
    findings: null,
    findingsPagination: {
      limit: HISTORY_RUN_FINDINGS_PAGE_LIMIT,
      offset: 0,
      total: 0,
      has_more: false,
      occurrence_total: 0,
      loaded: false,
    },
    entitySummary: null,
    entitySummaryLoaded: false,
    entities: null,
    entitiesPagination: {
      limit: HISTORY_RUN_ENTITIES_PAGE_LIMIT,
      offset: 0,
      total: 0,
      has_more: false,
      loaded: false,
    },
    activeEntityTab: _historyRunEntityTabs()[0]?.id || 'ip',
    projectState: null,
    activeTab: 'summary',
    loadingDetails: false,
    loadingFindings: false,
    loadingEntitySummary: false,
    loadingEntities: false,
    loadingProject: false,
    error: '',
  };
  _openHistoryRunOverlay();
  _renderHistoryRunModal();
  _loadHistoryRunDetails(run.id, token);
  _loadHistoryRunFindings(run.id, token);
  _loadHistoryRunEntitySummary(run.id, token);
  _loadHistoryRunEntities(run.id, token);
  _loadHistoryRunProjectState(run.id, token);
}

async function _handleHistoryRunModalAction(action) {
  const run = _historyRunPrimary();
  if (!run || !run.id) return;
  if (action === 'use-command') {
    const cmd = run.command || '';
    if (typeof setComposerValue === 'function') setComposerValue(cmd, cmd.length, cmd.length);
    closeHistoryRunOverlay();
    if (typeof hideHistoryPanel === 'function') hideHistoryPanel();
    if (typeof refocusComposerAfterAction === 'function') refocusComposerAfterAction({ preventScroll: true });
    resetCmdHistoryNav();
  } else if (action === 'restore') {
    closeHistoryRunOverlay();
    const existing = _tabForHistoryRun(run);
    const canUpgradeExisting = !!(existing && run.full_output_available && existing.previewTruncated);
    if (existing && !canUpgradeExisting) {
      activateTab(existing.id);
      if (typeof hideHistoryPanel === 'function') hideHistoryPanel();
      return;
    }
    _setHistoryLoadState(true);
    restoreHistoryRunIntoTab(run, {
      targetTabId: canUpgradeExisting ? existing.id : null,
      hidePanelOnSuccess: true,
    })
      .catch(() => showToast('Failed to load run'))
      .finally(() => _setHistoryLoadState(false));
  } else if (action === 'copy-command') {
    copyTextToClipboard(run.command || '')
      .then(() => showToast('Command copied'))
      .catch(() => showToast('Failed to copy command', 'error'));
  } else if (action === 'permalink') {
    copyHistoryRunPermalink(run).catch(() => showToast('Failed to copy link', 'error'));
  } else if (action === 'compare') {
    closeHistoryRunOverlay();
    openHistoryCompareLauncher(run);
  } else if (action === 'delete') {
    closeHistoryRunOverlay();
    confirmHistAction('delete', run.id, run.command);
  } else if (action === 'edit-metadata') {
    _historyEditEntityMetadata('run', run);
  } else if (action === 'open-atlas') {
    closeHistoryRunOverlay();
    if (typeof openAtlas === 'function') {
      void openAtlas({
        source: 'run-details',
        tab: 'findings',
        runId: run.id,
        runLabel: run.command || run.label || run.id,
      });
    }
  } else if (action === 'add-active-project') {
    const projectState = _historyRunModalState.projectState;
    const project = projectState && projectState.project;
    if (!project || projectState.attached) return;
    try {
      const confirmed = await _historyConfirmAddRunToProject(run, project);
      if (!confirmed) return;
      await _historyLinkRunToProject(run, project, confirmed);
      _historyRunModalState.projectState = { project, attached: true };
      _renderHistoryRunModal();
      refreshHistoryPanel();
    } catch (_) {
      showToast('Failed to add run to active project', 'error');
    }
  } else if (action === 'add-project') {
    try {
      await _historyAddRunToProject(run);
      const projectState = _historyRunModalState.projectState;
      if (projectState && projectState.project) {
        const activeProjectId = String(projectState.project.id || '');
        const attached = (Array.isArray(run.project_links) ? run.project_links : [])
          .some(item => String(item && item.project_id || '') === activeProjectId);
        _historyRunModalState.projectState = { ...projectState, attached };
      }
      _renderHistoryRunModal();
      refreshHistoryPanel();
    } catch (_) {
      showToast('Failed to add run to project', 'error');
    }
  } else if (action === 'remove-project') {
    try {
      await _historyRemoveRunFromProject(run);
      const projectState = _historyRunModalState.projectState;
      if (projectState && projectState.project) {
        const activeProjectId = String(projectState.project.id || '');
        const attached = (Array.isArray(run.project_links) ? run.project_links : [])
          .some(item => String(item && item.project_id || '') === activeProjectId);
        _historyRunModalState.projectState = { ...projectState, attached };
      }
      _renderHistoryRunModal();
      refreshHistoryPanel();
    } catch (_) {
      showToast('Failed to remove run from project', 'error');
    }
  } else if (action === 'copy-run-id') {
    copyTextToClipboard(run.id)
      .then(() => showToast('Run ID copied'))
      .catch(() => showToast('Failed to copy run ID', 'error'));
  }
}

window.openHistoryRunDetails = openHistoryRunDetails;
window.closeHistoryRunOverlay = closeHistoryRunOverlay;
window.isHistoryRunOverlayOpen = isHistoryRunOverlayOpen;
window.cycleHistoryRunOverlayTab = cycleHistoryRunOverlayTab;
