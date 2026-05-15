// Session Entity Atlas detail rendering helpers.

(function initAtlasEntityDetail(global) {
  function text(value, fallback = '') {
    return String(value ?? '').trim() || fallback;
  }

  function formatCount(value, noun) {
    const count = Number(value || 0);
    return `${count.toLocaleString()} ${noun}${count === 1 ? '' : 's'}`;
  }

  function formatDate(value) {
    const raw = text(value);
    if (!raw) return '—';
    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) return raw;
    return date.toLocaleString();
  }

  function clear(parent) {
    if (parent) parent.replaceChildren();
  }

  function node(tag, className = '', content = '') {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (content !== '') el.textContent = String(content);
    return el;
  }

  function metaRow(label, value) {
    const row = node('div', 'atlas-detail-meta-row');
    row.append(node('span', 'atlas-detail-meta-label', label), node('span', 'atlas-detail-meta-value', value || '—'));
    return row;
  }

  function renderLabels(labels) {
    const wrap = node('div', 'atlas-label-list');
    const values = (Array.isArray(labels) ? labels : [])
      .map(label => text(label && typeof label === 'object' ? label.label : label))
      .filter(Boolean);
    if (!values.length) {
      wrap.appendChild(node('span', 'atlas-muted', 'No labels'));
      return wrap;
    }
    values.forEach(value => wrap.appendChild(node('span', 'badge badge-tone-green', value)));
    return wrap;
  }

  function renderProjectLinks(links, onRemove) {
    const wrap = node('div', 'atlas-project-links');
    const rows = Array.isArray(links) ? links : [];
    if (!rows.length) {
      wrap.appendChild(node('div', 'atlas-muted', 'No project links'));
      return wrap;
    }
    rows.forEach(link => {
      const row = node('div', 'atlas-project-link-row');
      const name = node('span', 'atlas-project-link-name', text(link.project_name, link.project_id || 'project'));
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'btn btn-ghost btn-compact';
      remove.textContent = 'Remove';
      remove.addEventListener('click', () => onRemove?.(link));
      row.append(name, remove);
      wrap.appendChild(row);
    });
    return wrap;
  }

  function renderIntelSnapshots(snapshots) {
    const wrap = node('div', 'atlas-intel-list');
    const rows = Array.isArray(snapshots) ? snapshots : [];
    if (!rows.length) {
      wrap.appendChild(node('div', 'atlas-empty-inline', 'No intel snapshots'));
      return wrap;
    }
    rows.forEach(snapshot => {
      const card = node('div', 'atlas-intel-card');
      const top = node('div', 'atlas-intel-card-top');
      top.append(
        node('span', 'atlas-intel-provider', text(snapshot.provider, 'provider')),
        node('span', 'badge badge-tone-muted', text(snapshot.status, 'unknown')),
      );
      const summary = node('div', 'atlas-intel-summary', text(snapshot.summary, 'No summary'));
      const meta = node('div', 'atlas-muted', `Fetched ${formatDate(snapshot.fetched_at)}`);
      card.append(top, summary, meta);
      wrap.appendChild(card);
    });
    return wrap;
  }

  function renderRuns(runs, onSeeRun) {
    const wrap = node('div', 'atlas-source-list');
    const rows = Array.isArray(runs) ? runs : [];
    if (!rows.length) {
      wrap.appendChild(node('div', 'atlas-empty-inline', 'No linked runs'));
      return wrap;
    }
    rows.forEach(run => {
      const row = node('div', 'panel-row atlas-source-row');
      const title = node('div', 'atlas-source-command', text(run.command, run.run_id));
      const meta = node(
        'div',
        'atlas-muted',
        `${formatCount(run.occurrence_count, 'hit')} · ${formatDate(run.last_seen_at || run.started)}`,
      );
      row.append(title, meta);
      if (typeof onSeeRun === 'function') {
        const action = document.createElement('button');
        action.type = 'button';
        action.className = 'btn btn-ghost btn-compact atlas-source-action';
        action.textContent = 'See in run';
        action.addEventListener('click', () => onSeeRun(run));
        row.appendChild(action);
      }
      wrap.appendChild(row);
    });
    return wrap;
  }

  function renderFindings(findings) {
    const wrap = node('div', 'atlas-finding-list');
    const rows = Array.isArray(findings) ? findings : [];
    if (!rows.length) {
      wrap.appendChild(node('div', 'atlas-empty-inline', 'No findings for this entity'));
      return wrap;
    }
    rows.forEach(finding => {
      const row = node('div', 'panel-row atlas-finding-row');
      const title = node('div', 'atlas-finding-title', text(finding.title || finding.raw_line, finding.id));
      const meta = node(
        'div',
        'atlas-muted',
        [text(finding.status), text(finding.severity), text(finding.tool_root)].filter(Boolean).join(' · '),
      );
      row.append(title, meta);
      wrap.appendChild(row);
    });
    return wrap;
  }

  function reviewStateSelect(value, onChange) {
    const select = document.createElement('select');
    select.className = 'form-select form-control-compact atlas-finding-review';
    select.setAttribute('aria-label', 'Finding review state');
    [
      ['new', 'New'],
      ['reviewed', 'Reviewed'],
      ['important', 'Important'],
      ['false_positive', 'False positive'],
      ['needs_followup', 'Follow-up'],
    ].forEach(([optionValue, label]) => {
      const option = document.createElement('option');
      option.value = optionValue;
      option.textContent = label;
      select.appendChild(option);
    });
    select.value = text(value, 'new');
    select.addEventListener('change', () => onChange?.(select.value));
    return select;
  }

  function renderFindingDetail(container, finding, handlers = {}) {
    clear(container);
    if (!container) return;
    if (!finding || !finding.id) {
      container.appendChild(node('div', 'atlas-empty-inline', 'Select a finding'));
      return;
    }
    const header = node('div', 'atlas-detail-identity');
    header.append(
      node('div', 'atlas-detail-type', text(finding.kind, 'FINDING').toUpperCase()),
      node('div', 'atlas-detail-value', text(finding.title || finding.raw_line, finding.id)),
    );
    const actions = node('div', 'atlas-detail-actions');
    actions.appendChild(reviewStateSelect(finding.review_state || finding.status, (reviewState) => {
      handlers.onReviewState?.(finding, reviewState);
    }));
    if (finding.run_id) {
      const run = document.createElement('button');
      run.type = 'button';
      run.className = 'btn btn-secondary btn-compact';
      run.textContent = 'See in run';
      run.addEventListener('click', () => handlers.onSeeRun?.(finding));
      actions.appendChild(run);
    }
    if (finding.entity_id) {
      const entity = document.createElement('button');
      entity.type = 'button';
      entity.className = 'btn btn-secondary btn-compact';
      entity.textContent = 'Open entity';
      entity.addEventListener('click', () => handlers.onOpenEntity?.(finding));
      actions.appendChild(entity);
    }
    const meta = node('div', 'atlas-detail-meta');
    meta.append(
      metaRow('Status', text(finding.review_state || finding.status, 'new')),
      metaRow('Severity', text(finding.severity, '—')),
      metaRow('Tool', text(finding.tool_root, '—')),
      metaRow('Entity', text(finding.entity_value, finding.subject_key || '—')),
      metaRow('Occurrences', Number(finding.occurrence_count || 0).toLocaleString()),
      metaRow('Last seen', formatDate(finding.last_seen_at)),
    );
    const raw = node('code', 'atlas-finding-raw', text(finding.raw_line, finding.title || finding.id));
    container.append(header, actions, meta, section('Evidence', raw));
  }

  function renderMetadataEditor(entity, handlers = {}) {
    const wrap = node('div', 'atlas-metadata-editor');
    const labelInput = document.createElement('input');
    labelInput.className = 'form-control form-control-compact';
    labelInput.type = 'text';
    labelInput.autocomplete = 'off';
    labelInput.placeholder = 'labels';
    labelInput.setAttribute('aria-label', 'Atlas entity labels');
    labelInput.value = (Array.isArray(entity.labels) ? entity.labels : [])
      .map(label => text(label && typeof label === 'object' ? label.label : label))
      .filter(Boolean)
      .join(', ');

    const noteInput = document.createElement('textarea');
    noteInput.className = 'form-control atlas-note-input nice-scroll';
    noteInput.rows = 3;
    noteInput.placeholder = 'note';
    noteInput.setAttribute('aria-label', 'Atlas entity note');
    noteInput.value = text(entity.note && entity.note.body);

    const save = document.createElement('button');
    save.type = 'button';
    save.className = 'btn btn-secondary btn-compact';
    save.textContent = 'Save metadata';
    save.addEventListener('click', () => handlers.onSaveMetadata?.({
      labels: labelInput.value,
      note: noteInput.value,
    }));

    wrap.append(labelInput, noteInput, save);
    return wrap;
  }

  function renderDetail(container, detail, handlers = {}) {
    clear(container);
    if (!container) return;
    if (!detail || !detail.entity) {
      container.appendChild(node('div', 'atlas-empty-inline', 'Select an entity'));
      return;
    }
    const entity = detail.entity;
    const header = node('div', 'atlas-detail-identity');
    header.append(
      node('div', 'atlas-detail-type', text(entity.type).toUpperCase()),
      node('div', 'atlas-detail-value', text(entity.canonical_value, entity.id)),
    );

    const actions = node('div', 'atlas-detail-actions');
    const refresh = document.createElement('button');
    refresh.type = 'button';
    refresh.className = 'btn btn-secondary btn-compact';
    refresh.textContent = 'Refresh intel';
    refresh.addEventListener('click', () => handlers.onRefreshIntel?.(entity));
    actions.appendChild(refresh);
    if (handlers.activeProject && !handlers.isLinkedToActiveProject?.(entity)) {
      const promote = document.createElement('button');
      promote.type = 'button';
      promote.className = 'btn btn-secondary btn-compact';
      promote.textContent = 'Add to active project';
      promote.addEventListener('click', () => handlers.onAddToActiveProject?.(entity));
      actions.appendChild(promote);
    }

    const meta = node('div', 'atlas-detail-meta');
    meta.append(
      metaRow('Occurrences', Number(entity.occurrence_count || 0).toLocaleString()),
      metaRow('First seen', formatDate(entity.first_seen_at)),
      metaRow('Last seen', formatDate(entity.last_seen_at)),
    );

    container.append(header, actions, meta);
    container.append(section('Projects', renderProjectLinks(entity.project_links, handlers.onRemoveProjectLink)));
    container.append(section('Labels', renderLabels(entity.labels)));
    container.append(section('Metadata', renderMetadataEditor(entity, handlers)));
    container.append(section('Intel', renderIntelSnapshots(detail.intel_snapshots)));
    container.append(section('Source runs', renderRuns(detail.runs, handlers.onSeeRun)));
    container.append(section('Findings', renderFindings(detail.findings)));
  }

  function section(title, content) {
    const wrap = node('section', 'atlas-detail-section');
    wrap.append(node('div', 'atlas-detail-section-title', title), content);
    return wrap;
  }

  global.DarklabAtlasDetail = {
    renderDetail,
    renderFindingDetail,
    formatCount,
    formatDate,
    text,
    node,
  };
})(typeof window !== 'undefined' ? window : globalThis);
