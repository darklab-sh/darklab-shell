// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { test, expect } from '@playwright/test'
import {
  clickHistoryRunMenuAction,
  ensurePromptReady,
  openHistoryWithEntries,
  openRailAction,
  runCommand,
} from './helpers.js'

function trackSourceJsRequests(page) {
  const requests = []
  page.on('request', (request) => {
    try {
      const url = new URL(request.url())
      if (
        !url.pathname.endsWith('.js')
        || (!url.pathname.startsWith('/static/js/') && !url.pathname.startsWith('/static/build/'))
      ) return
      requests.push({ path: url.pathname, versioned: url.searchParams.has('v') })
    } catch (_) {}
  })
  return requests
}

function duplicateSourceModuleIdentities(requests) {
  const byPath = new Map()
  requests.forEach(({ path, versioned }) => {
    if (!byPath.has(path)) byPath.set(path, new Set())
    byPath.get(path).add(versioned ? 'versioned' : 'plain')
  })
  return Array.from(byPath.entries())
    .filter(([, variants]) => variants.has('versioned') && variants.has('plain'))
    .map(([path]) => path)
    .sort()
}

function hasWorkspaceModuleRequest(requests) {
  return requests.some(({ path }) => (
    path.endsWith('/workspace.js')
    || /\/static-workspace\.[a-f0-9]+\.js$/.test(path)
  ))
}

test.describe('source-mode lazy ESM surfaces', () => {
  test.setTimeout(90_000)

  test.beforeEach(async ({ page }, testInfo) => {
    testInfo.sourceJsRequests = trackSourceJsRequests(page)
    await page.goto('/')
    await ensurePromptReady(page)
  })

  test('loads existing Files for the first terminal listing', async ({ page }, testInfo) => {
    expect(hasWorkspaceModuleRequest(testInfo.sourceJsRequests)).toBe(false)
    await page.route('**/workspace/files', route => route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        directories: [{ name: 'reports', path: 'reports' }],
        files: [{ name: 'targets.txt', path: 'targets.txt', size: 12, mtime: 'now' }],
        usage: { bytes_used: 12, file_count: 1 },
        limits: { quota_bytes: 4096, max_files: 100 },
      }),
    }))

    await runCommand(page, 'ls')

    await expect(page.locator('.tab-panel.active .output')).toContainText('reports/ targets.txt')
    expect(hasWorkspaceModuleRequest(testInfo.sourceJsRequests)).toBe(true)
    await expect(page.locator('#workspace-overlay')).not.toHaveClass(/\bopen\b/)
  })

  test('opens high-risk lazy app surfaces through user controls', async ({ page }, testInfo) => {
    const overviewProjectId = await page.evaluate(async () => {
      const resp = await apiFetch('/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: `Source Overview ${Date.now()}` }),
      })
      if (!resp.ok) throw new Error(`project create failed: ${resp.status}`)
      const project = (await resp.json()).project
      const activeResp = await apiFetch('/projects/active', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: project.id }),
      })
      if (!activeResp.ok) throw new Error(`active project failed: ${activeResp.status}`)
      return project.id
    })

    await openRailAction(page, 'projects')
    await expect(page.locator('#project-workspace-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#project-workspace-body')).not.toContainText('Loading projects...')
    await page.locator('[data-project-tab="overview"]').click()
    await expect(page.locator('[data-project-tab="overview"]')).toHaveClass(/\bis-active\b/)
    await expect(page.locator(`.project-overview-root[data-project-overview-root="${overviewProjectId}"]`))
      .toBeVisible()
    await expect(page.locator('.project-overview-root')).toContainText('No project targets yet.')
    await page.locator('.project-workspace-close').click()
    await expect(page.locator('#project-workspace-overlay')).not.toHaveClass(/\bopen\b/)

    await openRailAction(page, 'options')
    await expect(page.locator('#options-overlay')).toHaveClass(/\bopen\b/)
    await page.locator('[data-options-tab="secrets"]').click()
    await expect(page.locator('#options-panel-secrets')).toBeVisible()
    await expect(page.locator('#options-secrets-refresh-btn')).toBeEnabled()
    await expect(page.locator('#options-secrets-list')).toContainText(/No secrets stored|API_KEY|secret/i)
    await expect(page.locator('#permalink-toast')).not.toContainText('apiFetch unavailable')
    await page.locator('[data-options-tab="teams"]').click()
    await expect(page.locator('#options-panel-teams')).toBeVisible()
    await expect(page.locator('#options-team-create-btn')).toBeEnabled()
    await page.keyboard.press('Escape')
    await expect(page.locator('#options-overlay')).not.toHaveClass(/\bopen\b/)

    await openRailAction(page, 'command-registry')
    await expect(page.locator('#command-registry-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#command-registry-body')).toContainText('curl', { timeout: 30_000 })
    await page.keyboard.press('Escape')
    await expect(page.locator('#command-registry-overlay')).not.toHaveClass(/\bopen\b/)

    await page.locator('#rail-workflows-list .rail-item').first().click()
    await expect(page.locator('#workflows-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#workflows-overlay .workflow-card').first()).toBeVisible()
    await page.locator('.workflows-close').click()
    await expect(page.locator('#workflows-overlay')).not.toHaveClass(/\bopen\b/)

    await openRailAction(page, 'atlas')
    await expect(page.locator('#atlas-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#atlas-overlay')).toContainText(/ATLAS|No findings queued/i)
    await page.keyboard.press('Escape')
    await expect(page.locator('#atlas-overlay')).not.toHaveClass(/\bopen\b/)

    await openRailAction(page, 'status-monitor')
    await expect(page.locator('#status-monitor')).toBeVisible()
    await expect(page.locator('#status-monitor-title')).toHaveText('Status Monitor')
    await page.keyboard.press('Escape')
    await expect(page.locator('#status-monitor')).toBeHidden()

    await runCommand(page, 'hostname')
    await openHistoryWithEntries(page)
    const firstHistoryEntry = page.locator('#history-list .history-entry').first()
    await firstHistoryEntry.click()
    await expect(page.locator('#history-run-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#history-run-overlay')).toContainText('hostname')
    await page.keyboard.press('Escape')
    await expect(page.locator('#history-run-overlay')).not.toHaveClass(/\bopen\b/)

    await clickHistoryRunMenuAction(firstHistoryEntry, 'compare')
    await expect(page.locator('#history-compare-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#history-compare-overlay')).toContainText(/Compare|Select/i)
    await page.keyboard.press('Escape')
    await expect(page.locator('#history-compare-overlay')).not.toHaveClass(/\bopen\b/)
    await page.locator('#history-close').click()
    await expect(page.locator('#history-panel')).not.toHaveClass(/\bopen\b/)

    const saveWrap = page.locator('.hud-actions .hud-save-wrap')
    await saveWrap.locator('[data-action="save-menu"]').click()
    await expect(saveWrap.locator('[data-action="save-pdf"]')).toBeVisible()
    const download = page.waitForEvent('download')
    await saveWrap.locator('[data-action="save-pdf"]').click()
    const pdfDownload = await download
    expect(pdfDownload.suggestedFilename()).toMatch(/\.pdf$/)
    await pdfDownload.delete().catch(() => {})
    expect(duplicateSourceModuleIdentities(testInfo.sourceJsRequests)).toEqual([])
  })

  test('does not publish Playwright-only hooks when webdriver is unavailable', async ({ browser }) => {
    const context = await browser.newContext()
    try {
      await context.addInitScript(() => {
        Object.defineProperty(Navigator.prototype, 'webdriver', {
          configurable: true,
          get: () => false,
        })
      })
      const page = await context.newPage()
      await page.goto('/')
      await page.locator('#cmd').waitFor()

      await expect.poll(
        () => page.evaluate(() => ({
          webdriver: navigator.webdriver,
          hasHooks: Object.prototype.hasOwnProperty.call(window, '__darklabE2E'),
          hasOpenOptions: Object.prototype.hasOwnProperty.call(window, 'openOptions'),
        })),
      ).toEqual({
        webdriver: false,
        hasHooks: false,
        hasOpenOptions: false,
      })
    } finally {
      await context.close()
    }
  })
})
