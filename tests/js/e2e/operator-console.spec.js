// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { readFileSync, existsSync } from 'fs';
import { resolve } from 'path';
import { execFileSync } from 'child_process';
import { test, expect } from '@playwright/test';
import { ensurePromptReady } from './helpers.js';

test.setTimeout(120_000);
function fixtureInfo(project) {
  const pg = Boolean(process.env.PW_E2E_POSTGRES_DSN);
  if (project.includes('restricted')) return { slot: pg ? 'pg-restricted' : 'restricted-qualification', provider: false };
  if (project.includes('oidc-required')) return { slot: pg ? 'pg-oidc-required' : 'oidc-required', provider: true };
  if (project.includes('oidc')) return { slot: pg ? 'pg-mixed' : 'oidc-qualification', provider: true };
  return { slot: '', provider: false };
}
function control(action, slot, principal) {
  const python = existsSync('.venv/bin/python') ? resolve('.venv/bin/python') : 'python3';
  execFileSync(python, [resolve('scripts/test-support/playwright/operator_fixture.py'), action,
    resolve(process.env.PW_E2E_SECRET_DIR, `${slot}.runtime.json`), principal], { stdio: 'pipe' });
}
async function browserRead(page, path) {
  return page.evaluate(async url => {
    const response = await fetch(url, { credentials: 'same-origin' });
    return { status: response.status, body: response.headers.get('content-type')?.includes('application/json') ? await response.json() : null };
  }, path);
}
async function verify(page, provider, credential) {
  if (provider) await page.getByRole('button', { name: /identity provider/i }).click();
  else {
    await page.getByLabel('Access credential').fill(credential);
    await page.getByRole('button', { name: 'Verify access', exact: true }).click();
  }
  await page.waitForURL(url => url.pathname === '/admin/', { waitUntil: 'domcontentloaded', timeout: 30_000 });
  await expect(page.locator('#admin-status')).toHaveText('Snapshot loaded. Settings are read only.');
}

async function choose(page, label, option) {
  await page.getByRole('button', { name: label, exact: true }).click();
  await page.getByRole('listbox').getByRole('option', { name: option, exact: true }).click();
}

async function browseOperatorPages(page, appName, width, testInfo) {
  const pages = [
    { path: '/admin/', subtitle: 'operator settings · read only', next: 'diagnostics' },
    { path: '/diag', subtitle: 'operator diagnostics', next: 'audit log' },
    { path: '/diag/audit', subtitle: 'audit log', next: 'operator settings' },
  ];
  for (const current of pages) {
    await page.waitForURL(url => url.pathname === current.path, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.diag-header-title')).toHaveText(appName);
    await expect(page.locator('.diag-header-meta')).toHaveText(current.subtitle);
    const navigation = page.getByRole('navigation', { name: 'Operator pages' });
    expect(await navigation.locator('.diag-nav-btn').evaluateAll(links => links.map(link => link.getAttribute('href')).sort()))
      .toEqual(pages.filter(other => other.path !== current.path).map(other => other.path).sort());
    for (const link of await navigation.locator('.diag-nav-btn').all()) {
      await expect(link).toBeVisible();
      if (width < 600) expect((await link.boundingBox()).height).toBeGreaterThanOrEqual(44);
    }
    if (width < 600) await expect(navigation.getByRole('link', { name: 'back to shell' })).toBeVisible();
    else await expect(navigation.getByRole('link', { name: 'back to shell' })).toBeHidden();
    if (current.path !== '/admin/') await expect(page.locator('.diag-refreshed-at time')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.locator('.diag-topbar').screenshot({ path: testInfo.outputPath(`operator-header-${width}-${current.path.split('/').filter(Boolean).join('-')}.png`) });
    await navigation.getByRole('link', { name: current.next, exact: true }).click();
  }
  await expect(page.locator('#admin-status')).toHaveText('Snapshot loaded. Settings are read only.');
}

async function browseInventory(page, inventory, width, testInfo) {
  const base = inventory.settings.find(row => row.key === 'ai_allow_full_output');
  const data = { ...inventory, warnings: [], host_settings: inventory.host_settings.slice(0, 1), settings: [
    { ...base, key: 'alpha', label: 'Alpha value', group: 'Alpha group', description: 'Permitted long value',
      effective: { mode: 'full', value: 'Permitted text '.repeat(70) }, source: { layer: 'local', name: 'Local YAML' }, warnings: [] },
    { ...base, key: 'beta', label: 'Beta warning', group: 'Alpha group', source: { layer: 'default', name: 'Built-in default' },
      warnings: [{ event: 'CONFIG_VALUE_CLAMPED', reason: 'below_minimum' }] },
    { ...base, key: 'gamma', label: 'Gamma value', group: 'Gamma group', source: { layer: 'environment', name: 'EXAMPLE' }, warnings: [] },
  ] };
  let release;
  let pending = new Promise(done => { release = done; });
  await page.route('**/admin/settings', async route => { await pending; await route.fulfill({ json: data }); });
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.locator('#admin-status')).toContainText('Loading');
  await page.getByRole('button', { name: 'Group', exact: true }).click();
  await expect(page.getByRole('listbox').getByRole('option', { name: 'All groups', exact: true })).toBeVisible();
  release();
  await expect(page.getByRole('listbox').getByRole('option', { name: 'Host deployment · not observed', exact: true })).toBeVisible();
  await page.getByRole('listbox').getByRole('option', { name: 'Alpha group', exact: true }).click();
  await expect(page.locator('#admin-count')).toHaveText('2 of 4 settings');
  const group = page.getByRole('button', { name: 'Group', exact: true });
  await group.press('ArrowDown');
  await expect(page.locator('#admin-count')).toHaveText('1 of 4 settings');
  await expect(group).toContainText('Gamma group');
  await group.press('ArrowDown');
  await expect(group).toContainText('Host deployment');
  await expect(page.locator('[data-key="APP_PORT"]')).toBeVisible();
  await page.getByRole('button', { name: 'Clear filters', exact: true }).click();
  const alphaGroup = page.getByRole('button', { name: 'Alpha group · 2 settings', exact: true });
  await expect(alphaGroup).toHaveAttribute('aria-expanded', 'false');
  await alphaGroup.focus(); await alphaGroup.press('Enter');
  await expect(alphaGroup).toBeFocused();
  await alphaGroup.press('Space');
  await expect(alphaGroup).toHaveAttribute('aria-expanded', 'false');
  await alphaGroup.press('Enter');
  const card = page.locator('[data-key="alpha"]');
  const guidance = card.getByRole('button', { name: 'Defaults and host configuration', exact: true });
  const longValue = card.getByRole('button', { name: 'Expand permitted value', exact: true });
  for (const control of [guidance, longValue]) {
    await control.focus(); await control.press('Enter');
    await expect(control).toBeFocused();
    await control.press('Space');
    await expect(control).toHaveAttribute('aria-expanded', 'false');
    await control.press('Enter');
  }
  await card.getByRole('button', { name: 'Raw schema', exact: true }).click();
  await page.getByLabel('Search settings').fill('alpha');
  await expect(page.getByRole('button', { name: 'Alpha group · 1 of 2 settings match', exact: true })).toHaveAttribute('aria-expanded', 'true');
  await expect(longValue).toHaveAttribute('aria-expanded', 'true');
  await page.getByRole('button', { name: 'Collapse all', exact: true }).click();
  await page.getByRole('button', { name: 'Clear filters', exact: true }).click();
  await expect(alphaGroup).toHaveAttribute('aria-expanded', 'true');
  await expect(guidance).toHaveAttribute('aria-expanded', 'true');
  for (const [label, option, key] of [['Source', 'Built-in default', 'beta'], ['Warnings', 'With warnings', 'beta'], ['Group', 'Gamma group', 'gamma']]) {
    await choose(page, label, option);
    await expect(page.locator('#admin-count')).toHaveText('1 of 4 settings');
    await page.getByLabel('Search settings').fill(key);
    await expect(page.locator('#admin-count')).toHaveText('1 of 4 settings');
    await page.getByLabel('Search settings').fill('missing');
    await expect(page.locator('#admin-results')).toContainText('No settings match');
    await page.getByRole('button', { name: 'Clear filters', exact: true }).click();
  }
  await choose(page, 'Group', 'Alpha group');
  await choose(page, 'Source', 'Built-in default');
  await choose(page, 'Warnings', 'With warnings');
  await page.getByLabel('Search settings').fill('beta');
  await expect(page.locator('#admin-count')).toHaveText('1 of 4 settings');
  await page.getByRole('button', { name: 'Clear filters', exact: true }).click();
  const refreshButton = page.getByRole('button', { name: 'Refresh snapshot', exact: true });
  await refreshButton.focus();
  await refreshButton.press('Enter');
  await expect(page.locator('#admin-status')).toContainText('Snapshot loaded');
  await expect(refreshButton).toBeFocused();
  pending = new Promise(done => { release = done; });
  await page.getByRole('button', { name: 'Refresh snapshot', exact: true }).click();
  await longValue.evaluate(node => node.scrollIntoView({ block: 'center' }));
  await longValue.focus();
  const before = await page.evaluate(() => window.scrollY);
  expect(before).toBeGreaterThan(0);
  release();
  await expect(page.locator('#admin-status')).toContainText('Snapshot loaded');
  await expect(longValue).toBeFocused();
  expect(await page.evaluate(() => window.scrollY)).toBe(before);
  await expect(guidance).toHaveAttribute('aria-expanded', 'true');
  await expect(card.getByRole('button', { name: 'Raw schema', exact: true })).toHaveAttribute('aria-expanded', 'true');
  if (width > 760) {
    const bar = await page.locator('.admin-filter-bar').boundingBox();
    expect((await longValue.boundingBox()).y).toBeGreaterThanOrEqual(bar.y + bar.height);
  }
  for (const theme of ['darklab_obsidian.yaml', 'newsprint.yaml']) {
    await page.context().addCookies([{ name: 'pref_theme_name', value: theme, url: new URL(page.url()).origin }]);
    await page.reload({ waitUntil: 'domcontentloaded' });
    await expect(page.locator('#admin-status')).toContainText('Snapshot loaded');
    await page.getByLabel('Search settings').fill('alpha');
    await guidance.click();
    await guidance.focus();
    await guidance.press('Space');
    await guidance.press('Enter');
    await expect(guidance).toBeFocused();
    expect(await guidance.evaluate(node => node.matches(':focus-visible'))).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    const heights = await page.locator('#admin-search, .admin-filters .app-select-trigger').evaluateAll(nodes => nodes.map(node => node.getBoundingClientRect().height));
    expect(new Set(heights).size).toBe(1);
    expect(heights[0]).toBeGreaterThanOrEqual(44);
    await page.screenshot({ path: testInfo.outputPath(`operator-console-${width}-${theme}-focused.png`) });
    await page.screenshot({ path: testInfo.outputPath(`operator-console-${width}-${theme}.png`), fullPage: true });
  }
  await page.unroute('**/admin/settings');
  await page.getByRole('button', { name: 'Clear filters', exact: true }).click();
}

for (const width of [1280, 375]) {
  test.describe(`viewport ${width}`, () => {
    test.use({ viewport: { width, height: 900 }, hasTouch: width < 600, isMobile: width < 600 });
  test(`operator console at ${width}px`, async ({ page: shellPage }, testInfo) => {
    let page = shellPage;
    const { slot, provider } = fixtureInfo(testInfo.project.name);
    if (!slot) {
      expect((await page.request.get('/admin/')).status()).toBe(404);
      expect((await page.request.get('/admin/settings')).status()).toBe(404);
      return;
    }
    const credential = provider ? '' : readFileSync(resolve(process.env.PW_E2E_SECRET_DIR, `${slot}.credential`), 'utf8').trim();
    await page.goto('/admin/');
    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
    if (provider) await page.getByRole('link', { name: /identity provider/i }).click();
    else {
      await page.getByLabel('Access credential').fill(credential);
      await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    }
    await page.waitForURL(url => url.pathname === '/admin/', { waitUntil: 'domcontentloaded', timeout: 30_000 });
    const identity = await browserRead(page, '/auth/principal');
    expect(identity.status).toBe(200);
    const principal = identity.body.principal.id;
    expect((await browserRead(page, '/admin/settings')).status).toBe(404);
    control('grant', slot, principal);
    try {
      await page.goto('/');
      await ensurePromptReady(page);
      if (width === 375) {
        await page.locator('#hamburger-btn').click();
        await page.locator('[data-menu-action="admin"]').click();
      } else {
        await page.locator('#rail-more-btn').click();
        const opened = page.context().waitForEvent('page');
        await page.locator('[data-action="admin"]').click();
        page = await opened;
        await page.waitForLoadState('domcontentloaded');
        expect(await page.evaluate(() => window.opener)).toBeNull();
        expect(new URL(shellPage.url()).pathname).toBe('/');
        await ensurePromptReady(shellPage);
      }
      await expect(page.locator('#admin-status')).toHaveText('Snapshot loaded. Settings are read only.');
      const inventory = (await browserRead(page, '/admin/settings')).body;
      expect(inventory.observation.kind).toBe("serving web worker's loaded configuration");
      expect(inventory.settings.find(row => row.key === 'oidc_client_secret').effective.mode).toBe('withheld');
      expect(JSON.stringify(inventory)).not.toContain('playwright-only-secret');
      await browseOperatorPages(page, inventory.settings.find(row => row.key === 'app_name').effective.value, width, testInfo);
      await page.getByLabel('Search settings').fill('ai_base_url');
      await expect(page.locator('[data-key="ai_base_url"]')).toContainText('Not configured');
      await choose(page, 'Source', 'Host · not observed');
      await expect(page.locator('#admin-results')).toContainText('No settings match');
      await choose(page, 'Source', 'All sources');
      await page.getByLabel('Search settings').fill('browser_session');
      await expect(page.locator('#admin-count')).toContainText('2 of');
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      if (width === 375) {
        for (const control of await page.locator('#admin-refresh, .admin-filters .app-select-trigger').all()) {
          expect((await control.boundingBox()).height).toBeGreaterThanOrEqual(44);
        }
      }
      await page.getByLabel('Search settings').focus();
      await expect(page.getByLabel('Search settings')).toBeFocused();
      await page.screenshot({ path: testInfo.outputPath(`operator-console-${width}.png`), fullPage: true });
      await browseInventory(page, inventory, width, testInfo);
      await page.route('**/admin/settings', route => route.fulfill({ status: 503, body: '{}' }), { times: 1 });
      await page.getByRole('button', { name: 'Refresh snapshot' }).click();
      await expect(page.locator('#admin-results')).toBeEmpty();
      await expect(page.locator('#admin-status')).toContainText('Try refreshing');
      await page.getByRole('button', { name: 'Refresh snapshot' }).click();
      await expect(page.locator('#admin-status')).toContainText('Snapshot loaded');
      control('stale', slot, principal);
      await page.getByRole('button', { name: 'Refresh snapshot' }).click();
      await expect(page.getByRole('heading', { name: 'Verify operator access' })).toBeVisible();
      await verify(page, provider, credential);
      expect(await page.evaluate(() => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }))).not.toContain('playwright-only-secret');
      control('revoke', slot, principal);
      await page.getByRole('button', { name: 'Refresh snapshot' }).click();
      await expect(page.locator('#admin-results')).toBeEmpty();
      await expect(page.locator('#admin-status')).toHaveText('Operator access is unavailable.');
    } finally {
      control('revoke', slot, principal);
    }
  });
  });
}
