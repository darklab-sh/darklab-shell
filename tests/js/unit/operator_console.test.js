// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, it, expect, vi } from 'vitest';
import { displayValue, filterSettings, initializeConsole } from '../../../app/static/js/features/admin/operator_console.js';

const row = (key, extra = {}) => ({ key, label: key, description: 'Description', group: 'Network',
  source: { layer: 'local', name: 'Local YAML' }, effective: { mode: 'full', value: '<script>literal</script>' },
  default: { mode: 'full', value: 'default' }, environment: [], processes: [], warnings: [], apply: 'Recreate container', ...extra });
const payload = (name = 'setting') => ({ schema_version: 1, settings: [row(name)], host_settings: [], warnings: [],
  observation: { process_id: 12, loaded_at: '2026-09-19', app_version: 'test' } });
const response = (body = payload(), status = 200) => ({ ok: status === 200, status, json: async () => body });
function fixture() {
  document.body.innerHTML = `<main><form><input id="admin-search"><select id="admin-group"><option value="">All</option></select>
  <select id="admin-source"><option value="">All</option></select><select id="admin-warnings"><option value="">All</option></select></form>
  <div id="admin-results"></div><p id="admin-count"></p><p id="admin-status"></p><p id="admin-observation"></p>
  <div id="admin-load-warnings"></div><button id="admin-refresh">Refresh</button></main>`;
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
  it('rejects an external reauthentication destination', async () => {
    const navigate = vi.fn();
    await initializeConsole(fixture(), { navigate, fetcher: async () => response({ destination: '//outside.test/admin/reauth' }, 401) }).ready;
    expect(navigate).not.toHaveBeenCalled();
  });
});
