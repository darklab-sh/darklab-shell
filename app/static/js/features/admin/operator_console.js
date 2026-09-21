// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { bindPressable } from '../../ui/ui_pressable.js';

import { enhanceAppSelects, syncAppSelect } from '../../ui/ui_helpers.js';
import { element, disclosure, settingCard } from './operator_settings_view.js';
import { operatorDestination } from './operator_access.js';
export { displayValue } from './operator_settings_view.js';

export function filterSettings(rows, { search = '', group = '', source = '', warnings = '' } = {}) {
  const query = search.trim().toLocaleLowerCase();
  return rows.filter(row => (!query || `${row.key} ${row.label} ${row.description}`.toLocaleLowerCase().includes(query))
    && (!group || row.group === group) && (!source || row.source.layer === source)
    && (!warnings || row.warnings.length > 0));
}

export function initializeConsole(root, { fetcher = fetch, navigate = path => window.location.assign(path) } = {}) {
  if (!root) return null;
  const query = selector => root.querySelector(selector);
  const search = query('#admin-search'), group = query('#admin-group'), source = query('#admin-source');
  const warnings = query('#admin-warnings'), results = query('#admin-results'), count = query('#admin-count');
  const status = query('#admin-status'), observation = query('#admin-observation'), refresh = query('#admin-refresh');
  const diagnostics = query('#admin-load-warnings');
  const categoryState = new Map(), filteredState = new Map(), settingState = new Map();
  let rows = [], requestId = 0, filtering = false, categoryHandles = [];
  const parameters = new URLSearchParams(window.location.search);
  search.value = (parameters.get('search') || '').slice(0, 256);
  let initialGroup = (parameters.get('group') || '').slice(0, 256);
  source.value = parameters.get('source') || (parameters.get('view') === 'host' ? 'host' : '');
  warnings.value = parameters.get('warnings') === 'yes' ? 'yes' : '';
  if (!source.value) source.value = '';
  const updateAddress = filters => {
    const url = new URL(window.location.href);
    url.searchParams.delete('view');
    for (const [key, value] of Object.entries(filters)) {
      if (value) url.searchParams.set(key, value.slice(0, 256));
      else url.searchParams.delete(key);
    }
    window.history.replaceState(window.history.state, '', url.pathname + url.search + url.hash);
  };
  enhanceAppSelects(root);
  for (const control of [source, warnings]) syncAppSelect(control);
  const option = (label, value) => { const node = element('option', label); node.value = value; return node; };
  const syncGroups = () => {
    const selected = initialGroup || group.value;
    initialGroup = '';
    const menu = group.nextElementSibling;
    const active = document.activeElement;
    const focusedOption = menu?.contains(active) && active.getAttribute('role') === 'option' ? active.dataset.value : null;
    const groups = [...new Set(rows.map(row => row.group))];
    group.replaceChildren(option('All groups', ''), ...groups.map(name => option(name, name)));
    group.value = groups.includes(selected) ? selected : '';
    syncAppSelect(group);
    if (focusedOption !== null && !active.isConnected) {
      const replacement = [...menu.querySelectorAll('[role="option"]')].find(node => node.dataset.value === focusedOption);
      (replacement || menu.querySelector('.app-select-trigger')).focus({ preventScroll: true });
    }
  };
  const clear = () => {
    rows = [];
    const lostFocus = results.contains(document.activeElement);
    results.replaceChildren();
    diagnostics.replaceChildren();
    count.textContent = '';
    observation.textContent = '';
    categoryState.clear(); filteredState.clear(); settingState.clear(); categoryHandles = [];
    syncGroups();
    if (lostFocus) search.focus();
  };
  const render = ({ filtersChanged = false } = {}) => {
    const filters = { search: search.value, group: group.value, source: source.value, warnings: warnings.value };
    updateAddress(filters);
    filtering = Object.values(filters).some(value => value.trim());
    if (filtersChanged) filteredState.clear();
    const visible = filterSettings(rows, filters);
    const active = document.activeElement;
    const focusKey = results.contains(active) ? active.dataset.browseKey : null;
    const scroll = { x: window.scrollX, y: window.scrollY };
    const panelScroll = new Map([...results.querySelectorAll('[data-scroll-key]')].map(node => [node.dataset.scrollKey, [node.scrollLeft, node.scrollTop]]));
    const fragment = document.createDocumentFragment();
    categoryHandles = [];
    for (const name of new Set(visible.map(row => row.group))) {
      const matches = visible.filter(row => row.group === name);
      const total = rows.filter(row => row.group === name).length;
      const label = `${name} · ${filtering ? `${matches.length} of ${total} settings match` : `${total} settings`}`;
      const category = disclosure(label, `group:${name}`, matches.map(row => settingCard(row, settingState)),
        filtering ? filteredState : categoryState, { initialOpen: filtering });
      const heading = element('h2', undefined, 'admin-group-title');
      heading.append(category.trigger);
      category.wrapper.prepend(heading);
      category.wrapper.classList.add('admin-category');
      category.wrapper.dataset.group = name;
      fragment.append(category.wrapper);
      categoryHandles.push(category.handle);
    }
    if (!visible.length) fragment.append(element('p', 'No settings match these filters.'));
    results.replaceChildren(fragment);
    count.textContent = `${visible.length} of ${rows.length} settings`;
    for (const node of results.querySelectorAll('[data-scroll-key]')) {
      const position = panelScroll.get(node.dataset.scrollKey);
      if (position) { node.scrollLeft = position[0]; node.scrollTop = position[1]; }
    }
    if (focusKey) {
      const target = [...results.querySelectorAll('[data-browse-key]')].find(node => node.dataset.browseKey === focusKey && !node.closest('.u-hidden'));
      if (target) target.focus({ preventScroll: true });
      else {
        search.focus();
        return;
      }
    }
    if (window.scrollX !== scroll.x || window.scrollY !== scroll.y) window.scrollTo(scroll.x, scroll.y);
  };
  async function load() {
    const current = ++requestId;
    const restoreRefreshFocus = document.activeElement === refresh;
    let focusMoved = false, navigating = false;
    const trackFocus = event => { if (event.target !== refresh && event.target !== document.body) focusMoved = true; };
    document.addEventListener('focusin', trackFocus);
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
        const destination = operatorDestination(data.destination);
        if (destination) {
          navigating = true;
          navigate(destination);
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
        effective: { mode: 'full', value: 'Not observed by this worker' }, default: { mode: 'unobserved' },
        source: { layer: 'host', name: item.status }, environment: [item.key], processes: ['Deployment'], warnings: [],
      }))].sort((a, b) => a.group.localeCompare(b.group) || a.key.localeCompare(b.key));
      syncGroups();
      const sample = data.observation;
      const date = new Date(sample.loaded_at);
      const loadedAt = Number.isNaN(date.getTime()) ? 'Unavailable' : new Intl.DateTimeFormat(undefined, {
        dateStyle: 'medium', timeStyle: 'long', timeZone: 'UTC',
      }).format(date);
      const loader = sample.load_pid && sample.load_pid !== sample.process_id
        ? `Configuration inherited from process ${sample.load_pid}` : 'Configuration loaded in this worker';
      observation.replaceChildren(...[sample.kind || "Serving web worker's loaded configuration", `Worker ${sample.process_id}`,
        loader, `Configuration loaded: ${loadedAt}`, `Application ${sample.app_version}`]
        .map(text => element('span', text)));
      diagnostics.replaceChildren(...data.warnings.map(item => element('p', `${item.key}: ${item.event} · ${item.reason}`, 'admin-warning')));
      if (data.warnings_truncated) diagnostics.append(element('p', 'Additional load warnings were omitted.', 'admin-warning'));
      status.textContent = 'Snapshot loaded. Settings are read only.';
      render();
    } catch {
      if (current !== requestId) return;
      clear();
      status.textContent = 'Settings could not be loaded. Try refreshing.';
    } finally {
      document.removeEventListener('focusin', trackFocus);
      if (current === requestId) {
        refresh.disabled = false;
        if (restoreRefreshFocus && !focusMoved && !navigating && document.activeElement === document.body) refresh.focus({ preventScroll: true });
      }
    }
  }
  search.addEventListener('input', () => render({ filtersChanged: true }));
  for (const control of [group, source, warnings]) control.addEventListener('change', () => {
    if (control === group) initialGroup = '';
    render({ filtersChanged: true });
  });
  root.querySelector('form').addEventListener('submit', event => event.preventDefault());
  bindPressable(refresh, { onActivate: load, refocusComposer: false });
  bindPressable(query('#admin-clear'), { onActivate: () => {
    search.value = '';
    initialGroup = '';
    for (const control of [group, source, warnings]) { control.value = ''; syncAppSelect(control); }
    render({ filtersChanged: true });
    search.focus({ preventScroll: true });
  }, refocusComposer: false });
  for (const [id, action] of [['#admin-expand', 'open'], ['#admin-collapse', 'close']]) {
    const button = query(id);
    bindPressable(button, { onActivate: () => categoryHandles.forEach(handle => handle[action]()), refocusComposer: false });
    button?.addEventListener('click', event => { if (event.detail === 0) button.focus({ preventScroll: true }); });
  }
  const hostExplanation = query('#admin-host-explanation');
  if (hostExplanation) {
    hostExplanation.replaceWith(disclosure('Host files and container snapshots', 'host-explanation', [...hostExplanation.childNodes], new Map()).wrapper);
  }
  const ready = load();
  return { refresh: load, ready };
}
