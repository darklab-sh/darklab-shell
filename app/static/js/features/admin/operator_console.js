// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { bindPressable } from '../../ui/ui_pressable.js';

export function displayValue(value) {
  if (value?.mode === 'summary') {
    if (value.summary === 'count') return `${value.value} entries configured`;
    if (value.summary === 'presence') return value.value ? 'Configured' : 'Not configured';
  }
  if (value?.mode !== 'full') return 'Value withheld';
  if (value.value === null) return 'Not set';
  if (value.value === '') return '(empty)';
  return typeof value.value === 'string' ? value.value : JSON.stringify(value.value, null, 2);
}

export function filterSettings(rows, { search = '', group = '', source = '', warnings = '' } = {}) {
  const query = search.trim().toLocaleLowerCase();
  return rows.filter(row => (!query || `${row.key} ${row.label} ${row.description}`.toLocaleLowerCase().includes(query))
    && (!group || row.group === group) && (!source || row.source.layer === source)
    && (!warnings || row.warnings.length > 0));
}

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function settingCard(row) {
  const card = element('article', undefined, 'admin-setting');
  card.dataset.key = row.key;
  card.append(element('h3', row.label || row.key), element('code', row.key), element('p', row.description));
  card.append(element('p', `Source: ${row.source.name}`, 'diag-muted'));
  const mode = row.effective?.mode;
  const text = displayValue(row.effective);
  card.append(element('pre', text.length > 240 && mode === 'full' ? `${text.slice(0, 240)}…` : text,
    `admin-value admin-${mode || 'withheld'}`));
  if (mode === 'full' && text.length > 240) {
    const details = element('details');
    details.append(element('summary', 'Expand permitted value'), element('pre', text));
    card.append(details);
  }
  if (row.effective?.truncated) card.append(element('p', 'Truncated by the display limit; this is not the complete value.', 'admin-warning'));
  for (const warning of row.warnings) card.append(element('p', `${warning.event}: ${warning.reason}`, 'admin-warning'));
  const guidance = element('details');
  guidance.append(element('summary', 'Defaults and host configuration'));
  guidance.append(element('p', `Default: ${displayValue(row.default)}${row.default?.truncated ? ' (truncated)' : ''}`));
  guidance.append(element('p', `YAML: ${row.yaml || 'Not an application YAML setting'}`));
  guidance.append(element('p', `Environment: ${row.environment?.join(', ') || 'No supported override'}`));
  guidance.append(element('p', `Affected processes: ${row.processes?.join(', ') || 'Deployment'}`));
  if (row.rules && Object.keys(row.rules).length) guidance.append(element('pre', JSON.stringify(row.rules, null, 2)));
  guidance.append(element('p', row.apply));
  card.append(guidance);
  return card;
}

export function initializeConsole(root, { fetcher = fetch, navigate = path => window.location.assign(path) } = {}) {
  if (!root) return null;
  const query = selector => root.querySelector(selector);
  const search = query('#admin-search'), group = query('#admin-group'), source = query('#admin-source');
  const warnings = query('#admin-warnings'), results = query('#admin-results'), count = query('#admin-count');
  const status = query('#admin-status'), observation = query('#admin-observation'), refresh = query('#admin-refresh');
  const diagnostics = query('#admin-load-warnings');
  let rows = [], requestId = 0;
  const clear = () => {
    rows = [];
    results.replaceChildren();
    diagnostics.replaceChildren();
    count.textContent = '';
    observation.textContent = '';
  };
  const render = () => {
    const visible = filterSettings(rows, { search: search.value, group: group.value, source: source.value, warnings: warnings.value });
    const fragment = document.createDocumentFragment();
    let previousGroup;
    for (const row of visible) {
      if (row.group !== previousGroup) fragment.append(element('h2', row.group, 'admin-group-title'));
      previousGroup = row.group;
      fragment.append(settingCard(row));
    }
    if (!visible.length) fragment.append(element('p', 'No settings match these filters.'));
    results.replaceChildren(fragment);
    count.textContent = `${visible.length} of ${rows.length} settings`;
  };
  async function load() {
    const current = ++requestId;
    refresh.disabled = true;
    status.textContent = 'Loading settings…';
    try {
      const response = await fetcher('/admin/settings', { credentials: 'same-origin', cache: 'no-store', redirect: 'error' });
      if (current !== requestId) return;
      if (response.status === 401) {
        clear();
        status.textContent = 'Sign-in or verification is required.';
        const data = await response.json();
        if (current !== requestId) return;
        const destination = new URL(data.destination, window.location.origin);
        if (destination.origin === window.location.origin && ['/auth/sign-in', '/admin/reauth'].includes(destination.pathname)) {
          navigate(destination.pathname + destination.search);
        }
        return;
      }
      if (!response.ok) {
        clear();
        status.textContent = response.status === 404 ? 'Operator access is unavailable.' : 'Settings could not be loaded. Try refreshing.';
        return;
      }
      const data = await response.json();
      if (current !== requestId) return;
      if (data.schema_version !== 1 || !Array.isArray(data.settings) || !Array.isArray(data.host_settings)) throw new Error('Invalid inventory');
      rows = [...data.settings, ...data.host_settings.map(item => ({
        ...item, label: item.key, group: 'Host deployment · not observed',
        effective: { mode: 'full', value: 'Not observed by this worker' }, default: { mode: 'withheld' },
        source: { layer: 'host', name: item.status }, environment: [item.key], processes: ['Deployment'], warnings: [],
      }))].sort((a, b) => a.group.localeCompare(b.group) || a.key.localeCompare(b.key));
      const selected = group.value;
      const option = (label, value) => { const node = element('option', label); node.value = value; return node; };
      group.replaceChildren(option('All groups', ''), ...[...new Set(rows.map(row => row.group))].map(name => option(name, name)));
      group.value = selected;
      const sample = data.observation;
      observation.textContent = `Worker ${sample.process_id} · loaded ${sample.loaded_at} · application ${sample.app_version}`;
      diagnostics.replaceChildren(...data.warnings.map(item => element('p', `${item.key}: ${item.event} · ${item.reason}`, 'admin-warning')));
      if (data.warnings_truncated) diagnostics.append(element('p', 'Additional load warnings were omitted.', 'admin-warning'));
      status.textContent = 'Snapshot loaded. Settings are read only.';
      render();
    } catch {
      if (current !== requestId) return;
      clear();
      status.textContent = 'Settings could not be loaded. Try refreshing.';
    } finally {
      if (current === requestId) refresh.disabled = false;
    }
  }
  for (const control of [search, group, source, warnings]) control.addEventListener('input', render);
  root.querySelector('form').addEventListener('submit', event => event.preventDefault());
  bindPressable(refresh, { onActivate: load, refocusComposer: false });
  const ready = load();
  return { refresh: load, ready };
}
