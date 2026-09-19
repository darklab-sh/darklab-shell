// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, it, expect, vi } from 'vitest';
import { displayValue, filterSettings, initializeConsole } from '../../../app/static/js/features/admin/operator_console.js';

import { acceptedValues, loadedSource } from '../../../app/static/js/features/admin/operator_settings_view.js';

const row = (key, extra = {}) => ({ key, label: key, description: 'Description', group: 'Network',
  source: { layer: 'local', name: 'Local YAML' }, effective: { mode: 'full', value: '<script>literal</script>' },
  default: { mode: 'full', value: 'default' }, environment: [], processes: [], warnings: [], apply: 'Recreate container', ...extra });
const payload = (name = 'setting') => ({ schema_version: 1, settings: [row(name)], host_settings: [], warnings: [],
  observation: { process_id: 12, loaded_at: '2026-09-19', app_version: 'test' } });
const response = (body = payload(), status = 200) => ({ ok: status === 200, status, json: async () => body });
function fixture() {
  document.body.innerHTML = `<main><form><input id="admin-search"><select class="form-select" id="admin-group"><option value="">All</option></select>
  <select class="form-select" id="admin-source"><option value="">All</option><option value="local">Local</option><option value="host">Host</option><option value="default">Default</option></select><select class="form-select" id="admin-warnings"><option value="">All</option><option value="yes">Warnings</option></select></form>
  <div id="admin-results"></div><p id="admin-count"></p><p id="admin-status"></p><p id="admin-observation"></p>
  <div id="admin-load-warnings"></div><button id="admin-refresh">Refresh</button><button id="admin-clear">Clear</button><button id="admin-expand">Expand</button><button id="admin-collapse">Collapse</button></main>`;
  return document.querySelector('main');
}
function deferred() { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; }

describe('operator console', () => {
  it('distinguishes zero/absent summaries from withheld without revealing a value', () => {
    expect(displayValue({ mode: 'summary', summary: 'count', value: 0 })).toBe('0 entries configured');
    expect(displayValue({ mode: 'summary', summary: 'presence', value: false })).toBe('Not configured');
    expect(displayValue({ mode: 'withheld', value: 'never display' })).toBe('Value withheld');
    expect(displayValue({ mode: 'summary', summary: 'unsupported', value: 'never display' })).toBe('Value withheld');
  });
  it('combines search, group, source and warnings without searching hidden values', () => {
    const rows = [row('alpha'), row('beta', { warnings: [{ event: 'clamped' }] })];
    expect(filterSettings(rows, { search: 'BETA', source: 'local', group: 'Network', warnings: 'yes' })).toEqual([rows[1]]);
    expect(filterSettings(rows, { search: '<script>' })).toEqual([]);
  });
  it('renders literal untrusted text and keeps search focus through filtering', async () => {
    const root = fixture();
    await initializeConsole(root, { fetcher: async () => response() }).ready;
    expect(root.querySelector('script')).toBeNull();
    const search = root.querySelector('input');
    search.focus(); search.value = 'missing'; search.dispatchEvent(new Event('input'));
    expect(root.textContent).toContain('No settings match');
    expect(document.activeElement).toBe(search);
  });
  it.each([401, 404, 500])('clears every inventory surface on refresh status %s', async status => {
    const root = fixture(), navigate = vi.fn();
    const fetcher = vi.fn().mockResolvedValueOnce(response()).mockResolvedValueOnce(response({ destination: '/admin/reauth?next=%2Fadmin%2F' }, status));
    const console = initializeConsole(root, { fetcher, navigate });
    await console.ready;
    await console.refresh();
    expect(root.querySelector('#admin-results').textContent).toBe('');
    expect(root.querySelector('#admin-observation').textContent).toBe('');
    expect(root.querySelector('#admin-group').options.length).toBe(1);
    expect(root.querySelector('#admin-group').nextElementSibling.textContent).not.toContain('Network');
    expect(navigate).toHaveBeenCalledTimes(status === 401 ? 1 : 0);
  });
  it.each([401, 200])('ignores an old response after newer response status %s', async status => {
    const root = fixture(), older = deferred(), navigate = vi.fn();
    const fetcher = vi.fn().mockReturnValueOnce(older.promise).mockResolvedValueOnce(
      response(status === 200 ? payload('newer') : { destination: '/admin/reauth' }, status));
    const console = initializeConsole(root, { fetcher, navigate });
    await console.refresh();
    older.resolve(response(payload('obsolete')));
    await console.ready;
    expect(root.textContent).not.toContain('obsolete');
    if (status === 200) expect(root.textContent).toContain('newer');
    else expect(root.querySelector('#admin-results').textContent).toBe('');
  });
  it('synchronizes asynchronous menus, keeps valid groups and drops missing selections', async () => {
    const root = fixture(), pending = deferred();
    const data = payload();
    data.host_settings = [{ key: 'APP_PORT', status: 'Not observed', description: 'Port' }];
    const fetcher = vi.fn().mockReturnValueOnce(pending.promise).mockResolvedValueOnce(response(data)).mockResolvedValueOnce(response({ ...payload(), settings: [] }));
    const controller = initializeConsole(root, { fetcher });
    const group = root.querySelector('#admin-group');
    pending.resolve(response(data)); await controller.ready;
    const menu = group.nextElementSibling;
    expect(menu.textContent).toContain('Host deployment');
    menu.querySelector('[data-value="Network"]').click();
    expect(root.querySelector('#admin-count').textContent).toBe('1 of 2 settings');
    await controller.refresh();
    expect(group.value).toBe('Network');
    await controller.refresh();
    expect(group.value).toBe('');
    expect(menu.querySelector('.app-select-value').textContent).toBe('All groups');
  });
  it('filters on each styled select change and clears every visible control', async () => {
    const root = fixture(), data = payload();
    data.settings = [row('alpha'), row('beta', { group: 'Browser', source: { layer: 'default' }, warnings: [{ event: 'clamped' }] })];
    await initializeConsole(root, { fetcher: async () => response(data) }).ready;
    const choose = (id, value) => root.querySelector(id).nextElementSibling.querySelector(`[data-value="${value}"]`).click();
    choose('#admin-source', 'default');
    expect(root.querySelector('#admin-count').textContent).toBe('1 of 2 settings');
    choose('#admin-group', 'Browser'); choose('#admin-warnings', 'yes');
    expect(root.querySelector('#admin-count').textContent).toBe('1 of 2 settings');
    const search = root.querySelector('input');
    search.value = 'alpha'; search.dispatchEvent(new Event('input'));
    expect(root.querySelector('#admin-results').textContent).toContain('No settings match');
    root.querySelector('#admin-clear').click();
    expect(root.querySelector('#admin-count').textContent).toBe('2 of 2 settings');
    expect(search.value).toBe('');
    for (const select of root.querySelectorAll('select')) {
      expect(select.value).toBe('');
      expect(select.nextElementSibling.querySelector('.app-select-value').textContent).toContain('All');
    }
  });
  it('restores unfiltered categories, counts matches, and preserves nested disclosures and current focus during delayed refresh', async () => {
    const root = fixture(), data = payload(), pending = deferred();
    data.settings = [row('alpha', { effective: { mode: 'full', value: 'long '.repeat(90) }, rules: { type: 'string' } }), row('beta')];
    const controller = initializeConsole(root, { fetcher: vi.fn().mockResolvedValueOnce(response(data)).mockReturnValueOnce(pending.promise) });
    await controller.ready;
    const find = key => [...root.querySelectorAll('[data-browse-key]')].find(node => node.dataset.browseKey === key);
    expect(find('group:Network').getAttribute('aria-expanded')).toBe('false');
    find('group:Network').click();
    const refresh = controller.refresh();
    find('alpha:guidance').click(); find('alpha:value').click(); find('alpha:schema').click();
    const longValue = root.querySelector('[data-scroll-key="alpha:value"]');
    longValue.scrollTop = 32;
    find('alpha:value').focus();
    pending.resolve(response(data)); await refresh;
    expect(document.activeElement).toBe(find('alpha:value'));
    expect(root.querySelector('[data-scroll-key="alpha:value"]').scrollTop).toBe(32);
    for (const key of ['alpha:guidance', 'alpha:value', 'alpha:schema']) expect(find(key).getAttribute('aria-expanded')).toBe('true');
    const search = root.querySelector('input');
    search.value = 'alpha'; search.dispatchEvent(new Event('input'));
    expect(find('group:Network').textContent).toContain('1 of 2 settings match');
    find('group:Network').click();
    expect(find('group:Network').getAttribute('aria-expanded')).toBe('false');
    root.querySelector('#admin-clear').click();
    expect(find('group:Network').getAttribute('aria-expanded')).toBe('true');
    expect(find('alpha:value').getAttribute('aria-expanded')).toBe('true');
    root.querySelector('#admin-collapse').click();
    expect(find('group:Network').getAttribute('aria-expanded')).toBe('false');
    root.querySelector('#admin-expand').click();
    expect(find('group:Network').getAttribute('aria-expanded')).toBe('true');
  });
  it.each([200, 500])('returns keyboard focus to refresh after status %s', async status => {
    const root = fixture(), pending = deferred();
    const controller = initializeConsole(root, { fetcher: vi.fn().mockResolvedValueOnce(response()).mockReturnValueOnce(pending.promise) });
    await controller.ready;
    const refresh = root.querySelector('#admin-refresh');
    refresh.focus(); refresh.click();
    // jsdom keeps disabled-button focus; mirror the browser's native blur.
    refresh.disabled = false; refresh.blur(); refresh.disabled = true;
    expect(document.activeElement).toBe(document.body);
    pending.resolve(response(payload(), status));
    await vi.waitFor(() => expect(refresh.disabled).toBe(false));
    expect(document.activeElement).toBe(refresh);
  });
  it('falls back to search when refreshed inventory removes a focused setting', async () => {
    const root = fixture();
    const controller = initializeConsole(root, { fetcher: vi.fn().mockResolvedValueOnce(response()).mockResolvedValueOnce(response(payload('replacement'))) });
    await controller.ready;
    root.querySelector('#admin-expand').click();
    root.querySelector('[data-browse-key="setting:guidance"]').focus();
    await controller.refresh();
    expect(document.activeElement).toBe(root.querySelector('#admin-search'));
  });
  it('explains declared input rules without inventing coercion for strict booleans or default file sources', () => {
    expect(acceptedValues({ type: 'boolean' }).join(' ')).toBe('Boolean: true or false');
    expect(acceptedValues({ type: 'boolean', input: 'boolean or 1/0, true/false, yes/no, on/off; invalid values default' }).join(' ')).toContain('yes/no, on/off');
    expect(acceptedValues({ type: 'integer', minimum: 1, maximum: 10, unit: 'minutes', fallback: 2 }).join(' ')).toContain('From 1 to 10, inclusive Unit: minutes Invalid input uses 2');
    expect(loadedSource(row('default', { source: { layer: 'default' } }))).toBe('Built-in default');
    expect(loadedSource(row('local', { source: { layer: 'local' } }))).toBe('Local config.local.yaml');
  });
  it('rejects an external reauthentication destination', async () => {
    const navigate = vi.fn();
    await initializeConsole(fixture(), { navigate, fetcher: async () => response({ destination: '//outside.test/admin/reauth' }, 401) }).ready;
    expect(navigate).not.toHaveBeenCalled();
  });
});
