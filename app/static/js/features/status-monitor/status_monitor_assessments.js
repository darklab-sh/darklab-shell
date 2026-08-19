// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Durable Assessment-plan progress for the shared Status Monitor.

const DarklabStatusMonitorAssessments = (() => {
  const STATUS_LABELS = Object.freeze({
    queued: 'Queued',
    launching: 'Launching',
    running: 'Running',
    canceling: 'Canceling',
  });

  function _element(tag, className = '', text = '') {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== '') node.textContent = String(text);
    return node;
  }

  function _batches(state) {
    return Array.isArray(state?.batches) ? state.batches : [];
  }

  function _count(state, key) {
    return _batches(state).reduce(
      (total, batch) => total + Number(batch?.progress?.[key] || 0),
      0,
    );
  }

  function _summary(state) {
    if (state?.unavailable) return 'Progress unavailable';
    const batches = _batches(state);
    const active = _count(state, 'launching') + _count(state, 'running');
    const pending = _count(state, 'pending');
    const parts = [`${batches.length} active ${batches.length === 1 ? 'batch' : 'batches'}`];
    if (active) parts.push(`${active} running`);
    if (pending) parts.push(`${pending} queued`);
    if (state?.truncated) parts.push('more not shown');
    return parts.join(' · ');
  }

  function _sectionHeader(state) {
    const header = _element('div', 'status-monitor-section-header');
    header.append(
      _element('div', 'status-monitor-section-title', 'Assessment plans'),
      _element('div', 'status-monitor-section-meta', _summary(state)),
    );
    return header;
  }

  function _progressText(batch) {
    const progress = batch?.progress || {};
    const settled = Number(progress.settled || 0);
    const total = Number(progress.total || 0);
    const active = Number(progress.launching || 0) + Number(progress.running || 0);
    const pending = Number(progress.pending || 0);
    return `${settled} / ${total} settled · ${active} active · ${pending} pending`;
  }

  function _batchSignature(batch) {
    return JSON.stringify({
      status: batch?.status || '',
      progress: batch?.progress || {},
      active_commands: batch?.active_commands || [],
    });
  }

  function _commandRow(command) {
    const row = _element('div', 'status-monitor-assessment-command');
    const copy = _element('div', 'status-monitor-assessment-command-copy');
    copy.append(
      _element('code', '', command?.display_command || '(command unavailable)'),
      _element(
        'small',
        '',
        [command?.action_id, command?.target?.value].filter(Boolean).join(' · '),
      ),
    );
    const status = String(command?.status || 'launching');
    row.append(copy, _element(
      'span',
      'badge badge-tone-amber',
      STATUS_LABELS[status] || status,
    ));
    return row;
  }

  function _renderBatchRow(batch, onOpenBatch) {
    const row = _element(
      'article',
      'status-monitor-assessment-batch chrome-row row-accent-amber',
    );
    row.dataset.batchId = String(batch?.batch_id || '');
    row.dataset.batchSignature = _batchSignature(batch);

    const heading = _element('div', 'status-monitor-assessment-heading');
    const identity = _element('div');
    identity.append(
      _element('strong', '', batch?.project_name || 'Project assessment'),
      _element('small', '', _progressText(batch)),
    );
    const status = String(batch?.status || 'queued');
    heading.append(identity, _element(
      'span',
      'badge badge-tone-amber',
      STATUS_LABELS[status] || status,
    ));
    row.appendChild(heading);

    const commands = _element('div', 'status-monitor-assessment-commands');
    const activeCommands = Array.isArray(batch?.active_commands) ? batch.active_commands : [];
    activeCommands.forEach(command => commands.appendChild(_commandRow(command)));
    if (!activeCommands.length) {
      commands.appendChild(_element(
        'div',
        'status-monitor-assessment-waiting',
        status === 'canceling'
          ? 'No commands are still running; cancellation is settling.'
          : 'Waiting to launch the next command.',
      ));
    }
    row.appendChild(commands);

    if (typeof onOpenBatch === 'function') {
      const actions = _element('div', 'status-monitor-assessment-actions');
      const open = _element('button', 'btn btn-secondary btn-compact', 'View batch');
      open.type = 'button';
      open.addEventListener('click', () => onOpenBatch(batch));
      actions.appendChild(open);
      row.appendChild(actions);
    }
    return row;
  }

  function renderSection(state, { onOpenBatch } = {}) {
    const section = _element('section', 'status-monitor-section status-monitor-assessment-section');
    section.appendChild(_sectionHeader(state));
    const list = _element('div', 'status-monitor-assessment-list');
    _batches(state).forEach(batch => list.appendChild(_renderBatchRow(batch, onOpenBatch)));
    if (!_batches(state).length && state?.unavailable) {
      list.appendChild(_element(
        'div',
        'status-monitor-empty status-monitor-assessment-empty',
        'Assessment-plan progress is temporarily unavailable.',
      ));
    }
    section.appendChild(list);
    return section;
  }

  function updateSection(section, state, { onOpenBatch } = {}) {
    const nextMeta = _summary(state);
    const meta = section.querySelector(':scope > .status-monitor-section-header .status-monitor-section-meta');
    if (meta && meta.textContent !== nextMeta) meta.textContent = nextMeta;
    const list = section.querySelector(':scope > .status-monitor-assessment-list');
    if (!list) return;
    const empty = list.querySelector(':scope > .status-monitor-assessment-empty');
    if (_batches(state).length || !state?.unavailable) empty?.remove();
    else if (!empty) {
      list.appendChild(_element(
        'div',
        'status-monitor-empty status-monitor-assessment-empty',
        'Assessment-plan progress is temporarily unavailable.',
      ));
    }
    const existing = new Map();
    list.querySelectorAll(':scope > .status-monitor-assessment-batch').forEach(row => {
      if (row.dataset.batchId) existing.set(row.dataset.batchId, row);
    });
    const seen = new Set();
    let cursor = null;
    _batches(state).forEach((batch) => {
      const batchId = String(batch?.batch_id || '');
      if (!batchId) return;
      seen.add(batchId);
      const signature = _batchSignature(batch);
      let row = existing.get(batchId);
      if (!row || row.dataset.batchSignature !== signature) {
        const replacement = _renderBatchRow(batch, onOpenBatch);
        if (row) row.replaceWith(replacement);
        row = replacement;
      }
      if (cursor) {
        if (cursor.nextSibling !== row) cursor.after(row);
      } else if (list.firstChild !== row) {
        list.insertBefore(row, list.firstChild || null);
      }
      cursor = row;
    });
    existing.forEach((row, batchId) => {
      if (!seen.has(batchId)) row.remove();
    });
  }

  return { renderSection, updateSection };
})();

export { DarklabStatusMonitorAssessments };
