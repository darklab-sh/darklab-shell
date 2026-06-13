// Session Entity Atlas detail rendering helpers.

const _darklabGlobal = window;

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

  function providerPayload(snapshot) {
    const data = snapshot?.data && typeof snapshot.data === 'object' ? snapshot.data : null;
    const providers = data?.providers && typeof data.providers === 'object' ? data.providers : null;
    if (!providers) return data;
    const label = text(snapshot.provider).toLowerCase();
    const normalizedLabel = label.replace(/[\s-]+/g, '_');
    const entries = Object.entries(providers);
    const match = entries.find(([key]) => {
      const normalizedKey = text(key).toLowerCase().replace(/[\s-]+/g, '_');
      return normalizedKey === label || normalizedKey === normalizedLabel;
    });
    if (match) return match[1];
    if (entries.length === 1) return entries[0][1];
    return providers;
  }

  function formatIntelKey(key) {
    const normalized = text(key)
      .replace(/_/g, ' ')
      .replace(/([a-z])([A-Z])/g, '$1 $2')
      .trim();
    const upper = normalized.toUpperCase();
    if (['ASN', 'AS', 'CVE', 'CVES', 'DNS', 'HTTP', 'IP', 'ISP', 'RPKI', 'TLS', 'URL'].includes(upper)) return upper;
    return normalized || 'value';
  }

  function isRecord(value) {
    return value && typeof value === 'object' && !Array.isArray(value);
  }

  function primitiveValue(value) {
    if (value === null || value === undefined || value === '') return '—';
    if (typeof value === 'boolean') return value ? 'yes' : 'no';
    if (typeof value === 'number') return value.toLocaleString();
    return String(value);
  }

  function compactJson(value) {
    try {
      const raw = JSON.stringify(value);
      if (!raw) return '—';
      return raw.length > 220 ? `${raw.slice(0, 217)}...` : raw;
    } catch (_err) {
      return primitiveValue(value);
    }
  }

  function renderIntelDataValue(value, depth = 0) {
    if (Array.isArray(value)) {
      if (!value.length) return node('span', 'atlas-intel-data-value', '—');
      const primitives = value.every(item => !isRecord(item) && !Array.isArray(item));
      if (primitives) {
        const shown = value.slice(0, 8).map(primitiveValue).join(', ');
        const suffix = value.length > 8 ? `, +${value.length - 8} more` : '';
        return node('span', 'atlas-intel-data-value', `${shown}${suffix}`);
      }
      const list = node('div', 'atlas-intel-data-list');
      value.slice(0, 4).forEach((item, index) => {
        const itemWrap = node('div', 'atlas-intel-data-item');
        itemWrap.append(
          node('div', 'atlas-intel-data-item-title', `Item ${index + 1}`),
          depth >= 2 ? node('span', 'atlas-intel-data-value', compactJson(item)) : renderIntelDataValue(item, depth + 1),
        );
        list.appendChild(itemWrap);
      });
      if (value.length > 4) list.appendChild(node('div', 'atlas-muted', `+${value.length - 4} more items`));
      return list;
    }
    if (isRecord(value)) {
      const entries = Object.entries(value)
        .filter(([, entryValue]) => entryValue !== undefined && entryValue !== null && entryValue !== '');
      if (!entries.length) return node('span', 'atlas-intel-data-value', '—');
      if (depth >= 3) return node('span', 'atlas-intel-data-value', compactJson(value));
      const wrap = node('div', `atlas-intel-data-object${depth ? ' is-nested' : ''}`);
      entries.slice(0, 12).forEach(([key, entryValue]) => {
        wrap.appendChild(renderIntelDataRow(key, entryValue, depth + 1));
      });
      if (entries.length > 12) wrap.appendChild(node('div', 'atlas-muted', `+${entries.length - 12} more fields`));
      return wrap;
    }
    return node('span', 'atlas-intel-data-value', primitiveValue(value));
  }

  function renderIntelDataRow(label, value, depth = 0) {
    const row = node('div', `atlas-intel-data-row${depth ? ' is-nested' : ''}`);
    row.append(
      node('span', 'atlas-intel-data-label', formatIntelKey(label)),
      renderIntelDataValue(value, depth),
    );
    return row;
  }

  function renderIntelPayload(snapshot) {
    const payload = providerPayload(snapshot);
    const wrap = node('div', 'atlas-intel-data');
    if (!isRecord(payload) && !Array.isArray(payload)) {
      wrap.appendChild(node('div', 'atlas-empty-inline', 'No structured provider data stored for this snapshot'));
      return wrap;
    }
    wrap.appendChild(renderIntelDataValue(payload));
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
      const body = node('div', 'atlas-intel-card-body u-hidden');
      let payloadRendered = false;
      const renderPayloadOnce = () => {
        if (payloadRendered) return;
        body.appendChild(renderIntelPayload(snapshot));
        payloadRendered = true;
      };
      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'btn btn-ghost btn-compact atlas-intel-card-toggle';
      toggle.setAttribute('aria-expanded', 'false');
      toggle.append(
        node('span', 'atlas-intel-card-caret', '›'),
        node('span', 'atlas-intel-provider', text(snapshot.provider, 'provider')),
        node('span', 'badge badge-tone-muted', text(snapshot.status, 'unknown')),
      );
      const summary = node('div', 'atlas-intel-summary', text(snapshot.summary, 'No summary'));
      const meta = node('div', 'atlas-muted', `Fetched ${formatDate(snapshot.fetched_at)}`);
      const disclosure = _darklabGlobal.bindDisclosure?.(toggle, {
        panel: body,
        openClass: null,
        hiddenClass: 'u-hidden',
        onToggle: (open) => {
          if (open) renderPayloadOnce();
          card.classList.toggle('is-open', open);
        },
      });
      if (!disclosure) {
        toggle.addEventListener('click', () => {
          const expanded = toggle.getAttribute('aria-expanded') === 'true';
          if (!expanded) renderPayloadOnce();
          toggle.setAttribute('aria-expanded', expanded ? 'false' : 'true');
          body.classList.toggle('u-hidden', expanded);
          card.classList.toggle('is-open', !expanded);
        });
      }
      card.append(toggle, summary, meta, body);
      wrap.appendChild(card);
    });
    return wrap;
  }

  function renderIntelSummary(summary) {
    const highlights = Array.isArray(summary?.highlights) ? summary.highlights : [];
    if (!highlights.length) return null;
    const wrap = node('div', 'atlas-intel-highlights');
    const groups = new Map();
    highlights.forEach(item => {
      const providerId = text(item.provider, 'provider');
      if (!groups.has(providerId)) {
        groups.set(providerId, {
          label: text(item.provider_label, providerId),
          items: [],
        });
      }
      groups.get(providerId).items.push(item);
    });
    groups.forEach(group => {
      const providerBlock = node('div', 'atlas-intel-highlight-provider');
      providerBlock.appendChild(node('div', 'atlas-intel-highlight-provider-title', group.label));
      const itemList = node('div', 'atlas-intel-highlight-items');
      group.items.forEach(item => {
        const row = node('div', 'atlas-intel-highlight-row');
        row.append(
          node('span', 'atlas-intel-highlight-label', text(item.label, 'Intel')),
          node(
            'span',
            `atlas-intel-highlight-value${item.tone === 'warning' ? ' is-warning' : ''}`,
            text(item.value, '—'),
          ),
        );
        itemList.appendChild(row);
      });
      providerBlock.appendChild(itemList);
      wrap.appendChild(providerBlock);
    });
    return wrap;
  }

  function renderCollectionPager(meta, noun, onPage) {
    if (!meta) return null;
    const limit = Math.max(1, Number(meta.limit || meta.shown || 50));
    const offset = Math.max(0, Number(meta.offset || 0));
    const shown = Math.max(0, Number(meta.shown || 0));
    const total = Math.max(0, Number(meta.total || 0));
    const hasPager = total > limit || offset > 0 || !!meta.has_more;
    if (!hasPager) return null;
    const wrap = node('div', 'atlas-detail-pager');
    const start = total && shown ? offset + 1 : 0;
    const end = total ? Math.min(offset + shown, total) : offset + shown;
    wrap.appendChild(node(
      'span',
      'atlas-muted',
      total ? `${start.toLocaleString()}-${end.toLocaleString()} of ${total.toLocaleString()} ${noun}` : `Showing ${shown.toLocaleString()} ${noun}`,
    ));
    if (typeof onPage === 'function') {
      const prev = document.createElement('button');
      prev.type = 'button';
      prev.className = 'btn btn-ghost btn-compact';
      prev.textContent = 'Previous';
      prev.disabled = offset <= 0;
      prev.addEventListener('click', () => onPage(Math.max(0, offset - limit)));
      const next = document.createElement('button');
      next.type = 'button';
      next.className = 'btn btn-ghost btn-compact';
      next.textContent = 'Next';
      next.disabled = !meta.has_more;
      next.addEventListener('click', () => onPage(offset + limit));
      wrap.append(prev, next);
    }
    return wrap;
  }

  function renderRuns(runs, onSeeRun, meta = null, onPage = null, onCleanRunAtlas = null) {
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
      const actions = node('div', 'atlas-source-actions');
      if (typeof onSeeRun === 'function') {
        const action = document.createElement('button');
        action.type = 'button';
        action.className = 'btn btn-ghost btn-compact atlas-source-action';
        action.textContent = 'See in run';
        action.addEventListener('click', () => onSeeRun(run));
        actions.appendChild(action);
      }
      if (typeof onCleanRunAtlas === 'function') {
        const cleanup = document.createElement('button');
        cleanup.type = 'button';
        cleanup.className = 'btn btn-ghost btn-compact atlas-source-action';
        cleanup.textContent = 'Clean Atlas';
        cleanup.addEventListener('click', () => onCleanRunAtlas(run));
        actions.appendChild(cleanup);
      }
      if (actions.childElementCount) row.appendChild(actions);
      wrap.appendChild(row);
    });
    const pager = renderCollectionPager(meta, 'source runs', onPage);
    if (pager) wrap.appendChild(pager);
    return wrap;
  }

  function importSourceTitle(source) {
    return text(source.import_name, text(source.source_tool, 'Import'));
  }

  function importSourceLabel(source) {
    const tool = text(source.source_tool, text(source.format_id, 'external tool'));
    return source.created_record ? `Created by ${tool} import` : `Also seen in ${tool} import`;
  }

  function renderImportSources(sources) {
    const wrap = node('div', 'atlas-source-list atlas-import-source-list');
    const rows = Array.isArray(sources) ? sources : [];
    if (!rows.length) {
      wrap.appendChild(node('div', 'atlas-empty-inline', 'No import sources'));
      return wrap;
    }
    rows.forEach(source => {
      const row = node('div', 'panel-row atlas-source-row atlas-import-source-row');
      row.append(
        node('div', 'atlas-source-command', importSourceTitle(source)),
        node(
          'div',
          'atlas-muted',
          [
            importSourceLabel(source),
            formatCount(source.occurrence_count, 'row'),
            formatDate(source.last_observed_at || source.applied_at),
          ].filter(Boolean).join(' · '),
        ),
      );
      wrap.appendChild(row);
    });
    return wrap;
  }

  function verificationStatusLabel(value) {
    const normalized = text(value, 'not_started');
    if (_darklabGlobal.DarklabFindingTriageEditor && typeof _darklabGlobal.DarklabFindingTriageEditor.verificationStatusLabel === 'function') {
      return _darklabGlobal.DarklabFindingTriageEditor.verificationStatusLabel(normalized);
    }
    return normalized.replace(/_/g, ' ');
  }

  function renderTriageSummary(finding) {
    const triage = finding && finding.triage && typeof finding.triage === 'object' ? finding.triage : null;
    const wrap = node('div', 'atlas-triage-summary');
    if (!triage) {
      wrap.appendChild(node('div', 'atlas-muted', 'No remediation or verification details yet.'));
      return wrap;
    }
    wrap.appendChild(metaRow('Verification', verificationStatusLabel(triage.verification_status || finding.verification_status)));
    const remediation = text(triage.remediation_preview || triage.remediation);
    const steps = text(triage.verification_steps_preview || triage.verification_steps);
    if (remediation) wrap.appendChild(metaRow('Remediation', remediation));
    if (steps) wrap.appendChild(metaRow('Steps', steps));
    if (!remediation && !steps && !triage.has_verification_notes) {
      wrap.appendChild(node('div', 'atlas-muted', 'No remediation or verification text yet.'));
    }
    return wrap;
  }

  function renderFindings(findings, meta = null, onPage = null) {
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
    const pager = renderCollectionPager(meta, 'findings', onPage);
    if (pager) wrap.appendChild(pager);
    return wrap;
  }

  function reviewStateSelect(value, onChange, options = {}) {
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
    select.disabled = !!options.disabled;
    if (options.disabledReason) select.title = options.disabledReason;
    select.addEventListener('change', () => onChange?.(select.value));
    return select;
  }

  function detailActionMenu(items = []) {
    const activeItems = items.filter(item => item && item.label && typeof item.onSelect === 'function');
    if (!activeItems.length) return null;
    const wrap = node('div', 'atlas-detail-action-menu save-menu-wrap save-menu-down');
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'btn btn-secondary btn-compact atlas-detail-action-menu-trigger';
    trigger.textContent = 'Actions';
    trigger.setAttribute('aria-haspopup', 'menu');
    trigger.setAttribute('aria-expanded', 'false');
    const menu = node('div', 'atlas-detail-action-menu-list save-menu dropdown-surface');
    menu.setAttribute('role', 'menu');
    activeItems.forEach(item => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = `dropdown-item dropdown-item-compact${item.destructive ? ' is-destructive' : ''}`;
      button.setAttribute('role', 'menuitem');
      button.textContent = item.label;
      button.disabled = !!item.disabled;
      if (item.disabled) {
        button.setAttribute('aria-disabled', 'true');
        if (item.disabledReason) button.title = item.disabledReason;
      }
      button.addEventListener('click', () => {
        if (item.disabled) return;
        wrap.classList.remove('open');
        trigger.setAttribute('aria-expanded', 'false');
        item.onSelect();
      });
      menu.appendChild(button);
    });
    trigger.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      const open = !wrap.classList.contains('open');
      wrap.classList.toggle('open', open);
      trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    wrap.append(trigger, menu);
    return wrap;
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
    const meta = node('div', 'atlas-detail-meta');
    meta.append(
      metaRow('Status', text(finding.review_state || finding.status, 'new')),
      metaRow('Suppression', finding.suppressed ? text(finding.suppressed_reason, 'suppressed') : 'visible'),
      metaRow('Severity', text(finding.severity, '—')),
      metaRow('Tool', text(finding.tool_root, '—')),
      metaRow('Entity', text(finding.entity_value, finding.subject_key || '—')),
      metaRow('Occurrences', Number(finding.occurrence_count || 0).toLocaleString()),
      metaRow('Last seen', formatDate(finding.last_seen_at)),
    );
    const raw = node('code', 'atlas-finding-raw', text(finding.raw_line, finding.title || finding.id));
    container.append(header);
    if (!handlers.hideInlineActions) {
      const actions = node('div', 'atlas-detail-actions');
      actions.appendChild(reviewStateSelect(
        finding.review_state || finding.status,
        (reviewState) => handlers.onReviewState?.(finding, reviewState),
        {
          disabled: handlers.canTriageAtlasRows === false,
          disabledReason: handlers.triageDisabledReason || '',
        },
      ));
      const triage = document.createElement('button');
      triage.type = 'button';
      triage.className = 'btn btn-secondary btn-compact';
      triage.textContent = 'Triage';
      triage.addEventListener('click', () => handlers.onEditTriage?.(finding));
      actions.appendChild(triage);
      if (finding.run_id) {
        const run = document.createElement('button');
        run.type = 'button';
        run.className = 'btn btn-secondary btn-compact';
        run.textContent = 'See in run';
        run.addEventListener('click', () => handlers.onSeeRun?.(finding));
        actions.appendChild(run);
      }
      const menuItems = [];
      if (finding.entity_id) {
        menuItems.push({
          label: 'Open entity',
          onSelect: () => handlers.onOpenEntity?.(finding),
        });
      }
      menuItems.push(
        {
          label: finding.suppressed ? 'Restore finding' : 'Suppress finding',
          disabled: handlers.canTriageAtlasRows === false,
          disabledReason: handlers.triageDisabledReason || '',
          onSelect: () => handlers.onSuppressFinding?.(finding),
        },
        {
          label: 'Delete finding',
          destructive: true,
          disabled: handlers.canDeleteAtlasRows === false,
          disabledReason: handlers.deleteDisabledReason || '',
          onSelect: () => handlers.onDeleteFinding?.(finding),
        },
      );
      const menu = detailActionMenu(menuItems);
      if (menu) actions.appendChild(menu);
      container.append(actions);
      if (typeof _darklabGlobal.enhanceAppSelects === 'function') {
        _darklabGlobal.enhanceAppSelects(actions);
      }
    }
    container.append(meta);
    container.append(section('Remediation and verification', renderTriageSummary(finding)));
    container.append(section('Import sources', renderImportSources(finding.import_sources)));
    container.append(section('Evidence', raw));
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

    const meta = node('div', 'atlas-detail-meta');
    meta.append(
      metaRow('Suppression', entity.suppressed ? text(entity.suppressed_reason, 'suppressed') : 'visible'),
      metaRow('Occurrences', Number(entity.occurrence_count || 0).toLocaleString()),
      metaRow('First seen', formatDate(entity.first_seen_at)),
      metaRow('Last seen', formatDate(entity.last_seen_at)),
    );

    container.append(header);
    if (!handlers.hideInlineActions) {
      const actions = node('div', 'atlas-detail-actions');
      const refresh = document.createElement('button');
      refresh.type = 'button';
      refresh.className = 'btn btn-secondary btn-compact';
      refresh.disabled = !!handlers.intelRefreshing;
      refresh.setAttribute('aria-busy', handlers.intelRefreshing ? 'true' : 'false');
      refresh.textContent = handlers.intelRefreshing ? 'Refreshing...' : 'Refresh intel';
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
      const menu = detailActionMenu([
        {
          label: entity.suppressed ? 'Restore entity' : 'Suppress entity',
          disabled: handlers.canTriageAtlasRows === false,
          disabledReason: handlers.triageDisabledReason || '',
          onSelect: () => handlers.onSuppressEntity?.(entity),
        },
        {
          label: 'Delete entity',
          destructive: true,
          disabled: handlers.canDeleteAtlasRows === false,
          disabledReason: handlers.deleteDisabledReason || '',
          onSelect: () => handlers.onDeleteEntity?.(entity),
        },
      ]);
      if (menu) actions.appendChild(menu);
      container.append(actions);
    }
    container.append(meta);
    const intelSummary = renderIntelSummary(detail.intel_summary);
    if (intelSummary) container.append(section('Intel summary', intelSummary));
    container.append(section('Projects', renderProjectLinks(entity.project_links, handlers.onRemoveProjectLink)));
    container.append(section('Labels', renderLabels(entity.labels)));
    container.append(section('Metadata', renderMetadataEditor(entity, handlers)));
    container.append(section('Intel', renderIntelSnapshots(detail.intel_snapshots)));
    container.append(section('Import sources', renderImportSources(detail.import_sources)));
    container.append(section('Source runs', renderRuns(
      detail.runs,
      handlers.onSeeRun,
      detail.detail_limits?.runs,
      handlers.onPageRuns,
      handlers.onCleanRunAtlas,
    )));
    container.append(section('Findings', renderFindings(
      detail.findings,
      detail.detail_limits?.findings,
      handlers.onPageFindings,
    )));
  }

  function section(title, content) {
    const wrap = node('section', 'atlas-detail-section');
    wrap.append(node('div', 'atlas-detail-section-title', title), content);
    return wrap;
  }

  window.DarklabAtlasDetail = {
    renderDetail,
    renderFindingDetail,
    reviewStateSelect,
    formatCount,
    formatDate,
    text,
    node,
  };
