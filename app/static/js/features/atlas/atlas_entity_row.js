// Shared Atlas entity row renderer used by Atlas and Project entity lists.

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

function _portProtocol(canonicalValue) {
  const match = /\/([a-z0-9_-]+)$/i.exec(text(canonicalValue));
  return match ? match[1].toLowerCase() : '';
}

function _portNumber(entity) {
  const direct = Number(entity && entity.port || 0);
  if (direct > 0) return direct;
  const match = /:(\d+)\/[a-z0-9_-]+$/i.exec(text(entity && (entity.canonical_value || entity.value)));
  return match ? Number(match[1] || 0) : 0;
}

function formatCompactPortLabel(entity) {
  const attributes = entity && entity.attributes && typeof entity.attributes === 'object'
    ? entity.attributes
    : {};
  const port = _portNumber(entity);
  if (!port) return '';
  const proto = text(entity && entity.proto || attributes.proto || attributes.protocol || _portProtocol(entity && (entity.canonical_value || entity.value)));
  const base = `${port}${proto ? `/${proto}` : ''}`;
  const service = text(entity && entity.service || attributes.service);
  const version = text(entity && entity.version || attributes.version);
  if (service && version) return `${base} ${service} (${version})`;
  if (service) return `${base} ${service}`;
  if (version) return `${base} (${version})`;
  return base;
}

function formatPortEntityMetadata(entity, { includeHost = false } = {}) {
  if (String(entity && entity.type || '').toLowerCase() !== 'port') return [];
  const attributes = entity && entity.attributes && typeof entity.attributes === 'object'
    ? entity.attributes
    : {};
  const proto = text(attributes.proto || attributes.protocol || _portProtocol(entity && (entity.canonical_value || entity.value)));
  const service = text(attributes.service);
  const version = text(attributes.version);
  const banner = text(attributes.banner);
  const hostEntityId = text(entity && entity.host_entity_id);
  return [
    proto ? `proto ${proto}` : '',
    service ? `service ${service}` : '',
    version ? `version ${version}` : '',
    banner ? `banner ${banner}` : '',
    includeHost && hostEntityId ? `host ${hostEntityId}` : '',
  ].filter(Boolean);
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
  meta.textContent = [
    `${countLabel(occurrenceCount, 'hit', 'hits')} · ${countLabel(runCount, 'run', 'runs')}`,
    ...formatPortEntityMetadata(entity),
  ].join(' · ');
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

const DarklabAtlasEntityRow = {
  formatCompactPortLabel,
  formatPortEntityMetadata,
  renderAtlasEntityRow,
  renderProjectEntityRow,
};


export {
  DarklabAtlasEntityRow,
  formatCompactPortLabel,
  formatPortEntityMetadata,
  renderAtlasEntityRow,
  renderProjectEntityRow,
};
