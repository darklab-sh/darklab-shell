// Shared Atlas entity row renderer used by Atlas and Project entity lists.

(function atlasEntityRowModule(global) {
  'use strict';

  function text(value, fallback = '') {
    return String(value ?? '').trim() || fallback;
  }

  function defaultCountLabel(count, singular, plural) {
    const numeric = Number(count || 0);
    return `${numeric.toLocaleString()} ${numeric === 1 ? singular : plural}`;
  }

  function defaultBadge(label, tone = 'muted') {
    const el = document.createElement('span');
    el.className = `badge ${tone === 'green' ? 'badge-tone-green' : 'badge-tone-muted'}`;
    el.textContent = String(label || '');
    return el;
  }

  function entityLabelText(label, textFn) {
    return textFn(label && typeof label === 'object' ? label.label : label);
  }

  function appendDataset(el, dataset = {}) {
    Object.entries(dataset || {}).forEach(([key, value]) => {
      el.dataset[key] = value;
    });
  }

  function atlasBadges(entity, { badge = defaultBadge, text: textFn = text } = {}) {
    const badges = document.createElement('span');
    badges.className = 'atlas-entity-badges';
    if (entity.project_link_count) badges.appendChild(badge(`${entity.project_link_count} projects`, 'green'));
    const labels = Array.isArray(entity.labels) ? entity.labels : [];
    labels.slice(0, 2).forEach(label => badges.appendChild(badge(entityLabelText(label, textFn), 'muted')));
    return badges;
  }

  function renderAtlasEntityRow({
    entity,
    selected = false,
    selecting = false,
    selectMode = false,
    mobile = false,
    text: textFn = text,
    countLabel = defaultCountLabel,
    badge = defaultBadge,
    appendSelectionControl = null,
    rowAction = null,
    onActivate = null,
  }) {
    const entityId = String(entity && entity.id || '');
    const valueText = textFn(entity && entity.canonical_value, entityId);
    const row = document.createElement('div');
    row.className = `chrome-row chrome-row-clickable atlas-entity-row${mobile ? ' atlas-mobile-row' : ''}`;
    row.classList.toggle('is-selecting', !!selecting);
    row.classList.toggle('is-selected', !!selected);
    row.classList.toggle('is-suppressed', !!(entity && entity.suppressed));
    row.classList.toggle('has-row-action', !!rowAction);
    row.dataset[mobile ? 'atlasMobileEntityId' : 'entityId'] = entityId;
    row.tabIndex = 0;
    row.setAttribute('role', selectMode ? 'checkbox' : 'button');
    if (selectMode) row.setAttribute('aria-checked', String(!!selected));
    row.setAttribute('aria-label', `Open ${valueText || entityId}`);

    if (typeof appendSelectionControl === 'function') {
      appendSelectionControl(row, entity);
    }

    const main = document.createElement('span');
    main.className = 'atlas-entity-main';
    const value = document.createElement('span');
    value.className = 'atlas-entity-value';
    value.textContent = valueText;
    const meta = document.createElement('span');
    meta.className = 'atlas-muted';
    const runCount = Number(entity && entity.run_count || 0);
    const occurrenceCount = Number(entity && entity.occurrence_count || 0);
    meta.textContent = `${countLabel(occurrenceCount, 'hit', 'hits')} · ${countLabel(runCount, 'run', 'runs')}`;
    main.append(value, meta);

    const badges = atlasBadges(entity || {}, { badge, text: textFn });
    if (entity && entity.suppressed) badges.prepend(badge('suppressed', 'muted'));
    row.append(main, badges);
    if (rowAction) row.appendChild(rowAction);
    if (mobile) {
      const chev = document.createElement('span');
      chev.className = 'atlas-mobile-row-chev drill-chev';
      chev.setAttribute('aria-hidden', 'true');
      chev.textContent = '›';
      row.appendChild(chev);
    }

    if (typeof onActivate === 'function') {
      row.addEventListener('click', onActivate);
      row.addEventListener('keydown', (event) => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
        onActivate(event);
      });
    }
    return row;
  }

  function renderProjectEntityRow({
    entity,
    projectId = '',
    title = '',
    meta = '',
    detail = '',
    chips = [],
    accessory = null,
    action = null,
    selected = false,
    checkbox = null,
    chipClass = () => 'badge badge-tone-muted',
    bindPressable = null,
  }) {
    const row = document.createElement('article');
    row.className = 'project-explorer-item panel-row project-entity-row';
    row.classList.toggle('is-selected', !!selected);
    if (checkbox) row.appendChild(checkbox);

    let contentHost = row;
    if (action) {
      contentHost = document.createElement('button');
      contentHost.type = 'button';
      contentHost.className = 'control-row project-explorer-item-click-target';
      contentHost.dataset.projectAction = action.action;
      appendDataset(contentHost, action.dataset || {});
      if (projectId && !contentHost.dataset.projectId) contentHost.dataset.projectId = projectId;
      if (typeof bindPressable === 'function') bindPressable(contentHost);
    }

    const main = document.createElement('div');
    main.className = 'project-explorer-item-main';
    const heading = document.createElement('div');
    heading.className = 'project-explorer-item-title';
    heading.textContent = title || text(entity && (entity.canonical_value || entity.value), entity && entity.id || '');
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
        chipEl.className = chipClass(chip.kind);
        chipEl.textContent = String(chip.label || '');
        chipWrap.appendChild(chipEl);
      });
      main.appendChild(chipWrap);
    }
    contentHost.appendChild(main);
    if (contentHost !== row) row.appendChild(contentHost);
    if (accessory) row.appendChild(accessory);
    return row;
  }

  global.DarklabAtlasEntityRow = {
    renderAtlasEntityRow,
    renderProjectEntityRow,
  };
})(globalThis);
