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

for (const width of [1280, 375]) {
  test.describe(`viewport ${width}`, () => {
    test.use({ viewport: { width, height: 900 }, hasTouch: width < 600, isMobile: width < 600 });
  test(`operator console at ${width}px`, async ({ page }, testInfo) => {
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
        await page.locator('[data-action="admin"]').click();
      }
      await expect(page.locator('#admin-status')).toHaveText('Snapshot loaded. Settings are read only.');
      const inventory = (await browserRead(page, '/admin/settings')).body;
      expect(inventory.observation.kind).toBe("serving web worker's loaded configuration");
      expect(inventory.settings.find(row => row.key === 'oidc_client_secret').effective.mode).toBe('withheld');
      expect(JSON.stringify(inventory)).not.toContain('playwright-only-secret');
      await page.getByLabel('Search settings').fill('ai_base_url');
      await expect(page.locator('[data-key="ai_base_url"]')).toContainText('Not configured');
      await page.locator('#admin-source').selectOption('host');
      await expect(page.locator('#admin-results')).toContainText('No settings match');
      await page.locator('#admin-source').selectOption('');
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
