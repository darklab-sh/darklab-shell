import { test, expect } from '@playwright/test'

import {
  browserSessionId,
  createShareSnapshot,
  seedProjectActivityFixture,
  seedProjectMonitoringFixture,
  setComposerValueForTest,
  waitForHistoryRuns,
} from './helpers.js'
import {
  FAST_RUN_CMD,
  LONG_RUN_CMD,
  WORKSPACE_CAPTURE_CMD,
  activeHistoryRunId,
  createManifest,
  createCaptureProjectFixture,
  freshHome,
  installCommonCaptureMocks,
  openCaptureRunComparison,
  resolveCaptureThemes,
  saveCapture,
  seedOutput,
  themeLabel,
  writeManifest,
} from './ui_capture_shared.js'

const freshCaptureHome = (page, opts = {}) => freshHome(page, {
  ...opts,
  guardrailMode: 'mobile',
})

async function runCommandMobile(page, cmd) {
  await setComposerValueForTest(page, cmd, { mobile: true })
  await page.locator('#mobile-run-btn').click()
  await page.waitForFunction(
    (expectedCmd) => {
      const tab = typeof getActiveTab === 'function' ? getActiveTab() : null
      return !!tab && tab.command === expectedCmd && tab.st !== 'running'
    },
    cmd,
    { timeout: 15_000 },
  )
}

async function runCommandMobileAndGetRunId(page, cmd) {
  await runCommandMobile(page, cmd)
  await waitForHistoryRuns(page, 1)
  return activeHistoryRunId(page, cmd)
}

async function runLongCaptureCommandMobile(page) {
  await setComposerValueForTest(page, LONG_RUN_CMD, { mobile: true })
  await page.locator('#mobile-run-btn').click()
  await expect(page.locator('.status-pill')).toHaveText('RUNNING', { timeout: 10_000 })
}

async function runFastCaptureCommandMobile(page) {
  await setComposerValueForTest(page, FAST_RUN_CMD, { mobile: true })
  await page.locator('#mobile-run-btn').click()
  await page.waitForFunction(
    (expectedCmd) => {
      const tab = typeof getActiveTab === 'function' ? getActiveTab() : null
      return !!tab && tab.command === expectedCmd && tab.st !== 'running'
    },
    FAST_RUN_CMD,
    { timeout: 10_000 },
  )
}

async function openMenu(page) {
  await page.locator('#hamburger-btn').click()
  await expect(page.locator('#mobile-menu-sheet')).toBeVisible()
}

async function openRecentsSheet(page) {
  await openMenu(page)
  await page.locator('#mobile-menu-sheet [data-menu-action="history"]').click()
  await expect(page.locator('#history-panel')).toHaveClass(/\bopen\b/)
}

async function createAndOpenWorkspaceResponseFileMobile(page) {
  await runCommandMobile(page, WORKSPACE_CAPTURE_CMD)
  await openMenu(page)
  await page.locator('#mobile-menu-sheet [data-menu-action="workspace"]').click()
  await expect(page.locator('#workspace-modal')).toBeVisible()
  const row = page.locator('.workspace-file-row', { hasText: 'response.html' }).first()
  await expect(row).toBeVisible()
  await row.locator('[data-workspace-action="view"]').click()
  await expect(page.locator('#workspace-viewer')).toBeVisible()
  await expect(page.locator('#workspace-viewer-title')).toHaveText('response.html')
}

async function openMobileProjectsWithCaptureProject(page, themeName) {
  const runId = await runCommandMobileAndGetRunId(page, 'hostname')
  const project = await createCaptureProjectFixture(page, {
    name: `Mobile Capture ${themeLabel(themeName)}`,
    runIds: [runId],
    target: 'mobile.capture.darklab.sh',
  })
  await openMenu(page)
  await page.locator('#mobile-menu-sheet [data-menu-action="projects"]').click()
  await expect(page.locator('#project-workspace-overlay')).toHaveClass(/\bopen\b/)
  await expect(page.locator('#project-mobile-root')).toBeVisible()
  const row = page.locator('.project-mobile-row').filter({ hasText: `Mobile Capture ${themeLabel(themeName)}` }).first()
  await expect(row).toBeVisible()
  await row.click()
  await expect(page.locator('#project-mobile-detail-view')).toBeVisible()
  await page.locator('[data-project-mobile-detail-tab="details"]').click()
  await expect(page.locator('#project-mobile-detail-body')).toContainText('mobile.capture.darklab.sh')
  return project
}

async function openMobileProjectTabCaptureScene(page, themeName, tabId, testInfo) {
  const project = await openMobileProjectsWithCaptureProject(page, themeName)
  const sessionId = await browserSessionId(page)
  if (tabId === 'monitoring') {
    seedProjectMonitoringFixture(testInfo, {
      sessionId,
      projectId: project.id,
    })
  } else if (tabId === 'activity') {
    seedProjectActivityFixture(testInfo, {
      sessionId,
      projectId: project.id,
    })
    await page.route('**/projects/**/activity**', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        events: [{
          id: 'aud_capture_mobile',
          created: '2026-06-06T12:00:00+00:00',
          event_type: 'finding.review_change',
          actor: { display_name: 'Capture Reviewer', member_id: '', role: 'owner' },
          target: { type: 'finding', id: 'finding_capture', href: '' },
          details: { source: 'capture', review_state: 'confirmed', target: 'mobile.capture.darklab.sh' },
        }],
        limit: 25,
        offset: 0,
        has_more: false,
        retention_days: 90,
      }),
    }))
  }
  if (tabId === 'monitoring' || tabId === 'activity') {
    await page.evaluate(async () => {
      if (typeof refreshProjectWorkspace === 'function') await refreshProjectWorkspace()
    })
  }
  await page.locator(`[data-project-mobile-detail-tab="${tabId}"]`).click()
  await expect(page.locator(`[data-project-mobile-detail-tab="${tabId}"]`)).toHaveClass(/\bis-active\b/)
  const detailBody = page.locator('#project-mobile-detail-body')
  if (tabId === 'monitoring') {
    const root = detailBody.locator(`[data-project-monitoring-root="${project.id}"].is-mobile`)
    await expect(root).toBeVisible({ timeout: 15_000 })
    await expect(root).toContainText('Ports Browser Watch')
    await expect(root).toContainText('New open port 443/tcp https')
    await expect(root.locator('[data-project-monitoring-action="new-monitor"]')).toBeVisible()
  } else if (tabId === 'activity') {
    const root = detailBody.locator('[data-project-activity-root]')
    await expect(root).toBeVisible({ timeout: 15_000 })
    await expect(root.locator('[data-project-activity-filter="event_type"]')).toBeVisible()
    await expect(root.locator('[data-project-activity-action="apply"]')).toBeVisible()
  } else if (tabId === 'report') {
    const root = detailBody.locator('.project-report-root').first()
    await expect(root.locator('[data-project-report-metadata="engagement_name"]')).toBeVisible({ timeout: 15_000 })
    await root.locator('[data-project-report-metadata="engagement_name"]').fill(`Mobile Capture Report ${themeLabel(themeName)}`)
    await root.locator('[data-project-report-metadata="date_range"]').fill('2026-06-01 to 2026-06-05')
    await root.locator('[data-project-report-metadata="executive_summary"]').fill('Capture summary for the v2.2 mobile project workspace.')
    await root.locator('[data-project-report-action="preview"]').click()
    await expect(root.frameLocator('.project-report-preview-frame').locator('body')).toContainText('Mobile Capture Report', {
      timeout: 15_000,
    })
  }
}

async function openMobileAtlasWithCaptureData(page) {
  await openMenu(page)
  await page.locator('#mobile-menu-sheet [data-menu-action="atlas"]').click()
  await expect(page.locator('#atlas-overlay')).toHaveClass(/\bopen\b/)
  await expect(page.locator('#atlas-mobile-root')).toBeVisible()

  await page.locator('#atlas-mobile-filters-panel').waitFor({ state: 'attached' })
  await page.locator('.atlas-mobile-filters-toggle').click()
  await expect(page.locator('#atlas-mobile-filters-panel')).toBeVisible()

  await page.locator('.atlas-mobile-overflow-btn').click()
  await expect(page.locator('#action-sheet-overlay')).toHaveClass(/\bopen\b/)
  await expect(page.locator('#action-sheet')).toContainText('Select mode')
  await page.locator('#action-sheet-overlay').click({ position: { x: 10, y: 10 } })
  await expect(page.locator('#action-sheet-overlay')).not.toHaveClass(/\bopen\b/)

  await page.locator('#atlas-mobile-tabs [data-atlas-mobile-tab="ip"]').click()
  const hostRow = page.locator('#atlas-mobile-list .atlas-mobile-row').filter({ hasText: '107.178.109.44' }).first()
  await expect(hostRow).toBeVisible()
  await hostRow.click()
  await expect(page.locator('#atlas-mobile-entity-view')).toBeVisible()
  await expect(page.locator('#atlas-mobile-entity-body')).toContainText('Shodan')
  await page.locator('#atlas-mobile-entity-body .atlas-intel-card-toggle').filter({ hasText: 'Shodan' }).click()
  await expect(page.locator('#atlas-mobile-entity-body .atlas-intel-card.is-open')).toContainText(/ports/i)
}

const scenes = [
  {
    slug: 'main-welcome-settled',
    title: 'Main UI - welcome animation completed',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName, cancelWelcome: false, hydrateHistory: false })
    },
  },
  {
    slug: 'main-multiple-tabs',
    title: 'Main UI - multiple tabs open',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runCommandMobile(page, 'hostname')
      await page.locator('#new-tab-btn').click()
      await runCommandMobile(page, 'date')
      await page.locator('#new-tab-btn').click()
      await expect(page.locator('.tab')).toHaveCount(3)
    },
  },
  {
    slug: 'main-running-active-tab',
    title: 'Main UI - active tab running',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runCommandMobile(page, 'hostname')
      await page.locator('#new-tab-btn').click()
      await runLongCaptureCommandMobile(page)
    },
  },
  {
    slug: 'main-running-inactive-tab',
    title: 'Main UI - inactive tab running',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runLongCaptureCommandMobile(page)
      await page.locator('#new-tab-btn').click()
      await runFastCaptureCommandMobile(page)
      await expect(page.locator('.tab').first().locator('.tab-status.running')).toBeVisible()
    },
  },
  {
    slug: 'main-running-indicator-chip',
    title: 'Main UI - running-indicator chip with two inactive running tabs',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runLongCaptureCommandMobile(page)
      await page.locator('#new-tab-btn').click()
      await runLongCaptureCommandMobile(page)
      await page.locator('#new-tab-btn').click()
      await expect(page.locator('#mobile-running-chip')).toBeVisible()
      await expect(page.locator('#mobile-running-chip .mobile-running-count')).toHaveText('2')
    },
  },
  {
    slug: 'kill-confirmation-modal',
    title: 'Main UI - kill confirmation modal',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runLongCaptureCommandMobile(page)
      await page.locator('#mobile-kill-btn').click()
      await expect(page.locator('#confirm-host [data-confirm-card]')).toBeVisible()
    },
  },
  {
    slug: 'save-menu-open',
    title: 'Main UI - save menu open',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runCommandMobile(page, 'hostname')
      await page.locator('.tab-panel.active [data-action="save-menu"]').click()
      await expect(page.locator('.tab-panel.active .save-menu-wrap.open .save-menu')).toBeVisible()
    },
  },
  {
    slug: 'search-open-active-match',
    title: 'Main UI - search open with active matches',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await seedOutput(page, [
        { text: '$ curl http://localhost:5001/health' },
        { text: '{"status":"ok"}' },
        { text: 'localhost localhost localhost' },
      ])
      await openMenu(page)
      await page.locator('#mobile-menu-sheet [data-menu-action="search"]').click()
      await page.evaluate(() => {
        if (typeof window.showSearchBar === 'function' && !document.getElementById('search-input')?.offsetParent) {
          window.showSearchBar()
        }
      })
      await expect(page.locator('#search-input')).toBeVisible({ timeout: 10_000 })
      await page.locator('#search-input').fill('localhost')
      await expect(page.locator('.tab-panel.active .output mark.search-hl').first()).toBeVisible()
    },
  },
  {
    slug: 'files-panel-response-file',
    title: 'Main UI - Files panel with captured response file',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await createAndOpenWorkspaceResponseFileMobile(page)
    },
  },
  {
    slug: 'projects-modal',
    title: 'Projects modal with active project',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await openMobileProjectsWithCaptureProject(page, themeName)
    },
  },
  {
    slug: 'project-monitoring-tab',
    title: 'Projects modal Monitoring tab',
    route: '/',
    run: async (page, themeName, testInfo) => {
      await freshCaptureHome(page, { themeName })
      await openMobileProjectTabCaptureScene(page, themeName, 'monitoring', testInfo)
    },
  },
  {
    slug: 'project-activity-tab',
    title: 'Projects modal Activity tab',
    route: '/',
    run: async (page, themeName, testInfo) => {
      await freshCaptureHome(page, { themeName })
      await openMobileProjectTabCaptureScene(page, themeName, 'activity', testInfo)
    },
  },
  {
    slug: 'project-report-tab',
    title: 'Projects modal Report tab',
    route: '/',
    run: async (page, themeName, testInfo) => {
      await freshCaptureHome(page, { themeName })
      await openMobileProjectTabCaptureScene(page, themeName, 'report', testInfo)
    },
  },
  {
    slug: 'atlas-modal',
    title: 'Session Entity Atlas modal',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await openMobileAtlasWithCaptureData(page)
    },
  },
  {
    slug: 'run-comparison-modal',
    title: 'Run comparison modal',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await openCaptureRunComparison(page)
      await expect(page.locator('#history-compare-overlay')).toHaveClass(/\bopen\b/)
      await expect(page.locator('.history-compare-split')).toContainText('443/tcp open https')
    },
  },
  {
    slug: 'line-numbers-enabled',
    title: 'Main UI - line numbers enabled',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await seedOutput(page, [
        { text: '$ hostname' },
        { text: 'darklab_shell' },
        { text: '[process exited with code 0]', cls: 'exit-ok' },
      ])
      await page.evaluate(() => {
        if (typeof applyLineNumberPreference === 'function') applyLineNumberPreference('on')
      })
      await expect(page.locator('body')).toHaveClass(/ln-on/)
    },
  },
  {
    slug: 'timestamps-enabled',
    title: 'Main UI - timestamps enabled',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runCommandMobile(page, 'ping -c 4 darklab.sh')
      await page.evaluate(() => {
        if (typeof applyTimestampPreference === 'function') applyTimestampPreference('elapsed')
      })
      await expect(page.locator('body')).toHaveClass(/ts-elapsed/)
    },
  },
  {
    slug: 'line-numbers-and-timestamps-enabled',
    title: 'Main UI - line numbers and timestamps enabled',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runCommandMobile(page, 'ping -c 4 darklab.sh')
      await page.evaluate(() => {
        if (typeof applyLineNumberPreference === 'function') applyLineNumberPreference('on')
        if (typeof applyTimestampPreference === 'function') applyTimestampPreference('elapsed')
      })
      await expect(page.locator('body')).toHaveClass(/ln-on/)
      await expect(page.locator('body')).toHaveClass(/ts-elapsed/)
    },
  },
  {
    slug: 'history-panel',
    title: 'History panel',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runCommandMobile(page, 'hostname')
      await runCommandMobile(page, 'date')
      await waitForHistoryRuns(page, 2)
      await openRecentsSheet(page)
    },
  },
  {
    slug: 'history-panel-snapshot-row',
    title: 'History panel - snapshot row',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runCommandMobile(page, 'hostname')
      await createShareSnapshot(page)
      await openRecentsSheet(page)
      const snapshotItem = page.locator('#history-list .history-entry-snapshot').first()
      await expect(snapshotItem).toBeVisible()
      await expect(snapshotItem.locator('[data-action="open"]')).toBeVisible()
      await expect(snapshotItem.locator('[data-action="link"]')).toBeVisible()
      await expect(snapshotItem.locator('[data-action="delete"]')).toBeVisible()
    },
  },
  {
    slug: 'history-panel-search-filters-expanded',
    title: 'History panel - command search with filters expanded',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runCommandMobile(page, 'hostname')
      await runCommandMobile(page, 'date')
      await waitForHistoryRuns(page, 2)
      await openRecentsSheet(page)
      await page.locator('#history-mobile-filters-toggle').click()
      await page.locator('#history-search-input').fill('host')
      await expect(page.locator('#history-advanced-filters')).toBeVisible()
      await page.locator('#history-root-input').fill('host')
    },
  },
  {
    slug: 'history-panel-search-chip',
    title: 'History panel - command search with chip shown',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runCommandMobile(page, 'hostname')
      await runCommandMobile(page, 'date')
      await waitForHistoryRuns(page, 2)
      await openRecentsSheet(page)
      await page.locator('#history-mobile-filters-toggle').click()
      await page.locator('#history-search-input').fill('host')
      await page.waitForTimeout(300)
      await expect(page.locator('#history-active-filters')).not.toHaveClass(/u-hidden/)
    },
  },
  {
    slug: 'history-panel-delete-all-confirmation',
    title: 'History panel - delete-all confirmation modal',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runCommandMobile(page, 'hostname')
      await runCommandMobile(page, 'date')
      await waitForHistoryRuns(page, 2)
      await openRecentsSheet(page)
      await page.locator('#hist-clear-all-btn').click()
      await expect(page.locator('#confirm-host')).toBeVisible()
    },
  },
  {
    slug: 'history-panel-delete-confirmation',
    title: 'History panel - delete confirmation modal',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runCommandMobile(page, 'hostname')
      await waitForHistoryRuns(page, 1)
      await openRecentsSheet(page)
      await page.locator('#history-list .history-entry').first().locator('[data-action="delete"]').click()
      await expect(page.locator('#confirm-host')).toBeVisible()
    },
  },
  {
    slug: 'menu-modal',
    title: 'Menu modal',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await openMenu(page)
    },
  },
  {
    slug: 'workflows-modal',
    title: 'Workflows modal',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await openMenu(page)
      await page.locator('#mobile-menu-sheet [data-menu-action="workflows"]').click()
      await expect(page.locator('#workflows-modal')).toBeVisible()
    },
  },
  {
    slug: 'options-modal',
    title: 'Options modal',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await openMenu(page)
      await page.locator('#mobile-menu-sheet [data-menu-action="options"]').click()
      await expect(page.locator('#options-modal')).toBeVisible()
    },
  },
  {
    slug: 'session-token-clear-confirmation',
    title: 'Session-token clear confirmation modal',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await openMenu(page)
      await page.locator('#mobile-menu-sheet [data-menu-action="options"]').click()
      await expect(page.locator('#options-modal')).toBeVisible()
      await expect(page.locator('#options-session-token-clear-btn')).toBeVisible()
      await page.locator('#options-session-token-clear-btn').click()
      await expect(page.locator('#confirm-host [data-confirm-card]')).toBeVisible()
      await expect(page.locator('#confirm-host')).toContainText('Clear the current session token')
      await expect(page.locator('#confirm-host [data-confirm-action-id="copy"]')).toBeVisible()
      await expect(page.locator('#confirm-host [data-confirm-action-id="clear"]')).toBeVisible()
    },
  },
  {
    slug: 'theme-modal',
    title: 'Theme modal',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await openMenu(page)
      await page.locator('#mobile-menu-sheet [data-menu-action="theme"]').click()
      await expect(page.locator('#theme-modal')).toBeVisible()
    },
  },
  {
    slug: 'faq-modal',
    title: 'FAQ modal',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await openMenu(page)
      await page.locator('#mobile-menu-sheet [data-menu-action="faq"]').click()
      await expect(page.locator('#faq-modal')).toBeVisible()
    },
  },
  {
    slug: 'snapshot-page',
    title: 'Snapshot page',
    route: '/share/:id',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runCommandMobile(page, 'hostname')
      const shareResp = await createShareSnapshot(page)
      const data = await shareResp.json()
      await page.goto(data.url, { waitUntil: 'domcontentloaded' })
      await expect(page.locator('body.permalink-page')).toBeVisible()
    },
  },
  {
    slug: 'permalink-page',
    title: 'Permalink page',
    route: '/history/:id',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runCommandMobile(page, 'hostname')
      await waitForHistoryRuns(page, 1)
      await openRecentsSheet(page)
      const runItem = page
        .locator('#history-list .history-entry')
        .filter({
          has: page.locator('[data-action="history-menu"]'),
        })
        .first()
      await runItem.locator('[data-action="history-menu"]').click()
      await runItem.locator('.history-action-menu .dropdown-item', { hasText: 'permalink' }).click()
      const copied = await page.evaluate(() => window.__clipboardText || '')
      await page.goto(copied, { waitUntil: 'domcontentloaded' })
      await expect(page.locator('body.permalink-page')).toBeVisible()
    },
  },
  {
    slug: 'diag-page',
    title: 'Diag page',
    route: '/diag',
    run: async (page) => {
      await page.context().clearCookies()
      await page.goto('/diag', { waitUntil: 'domcontentloaded' })
      await expect(page.locator('body.diag-page')).toBeVisible()
    },
  },
]

test('mobile screenshot capture pack', async ({ page }, testInfo) => {
  test.skip(!process.env.RUN_CAPTURE, 'set RUN_CAPTURE=1 to run the UI screenshot capture pack')
  test.setTimeout(3_600_000)

  await installCommonCaptureMocks(page)

  const themes = resolveCaptureThemes()
  const manifest = createManifest('mobile')

  for (const themeName of themes) {
    for (const [index, scene] of scenes.entries()) {
      await test.step(`${themeLabel(themeName)} :: ${scene.title}`, async () => {
        await scene.run(page, themeName, testInfo)
        await saveCapture(page, manifest, {
          ui: 'mobile',
          themeName,
          order: index + 1,
          slug: scene.slug,
          title: scene.title,
          route: scene.route,
        })
      })
    }
  }

  writeManifest('mobile', manifest)
})
