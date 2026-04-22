import { test, expect } from '@playwright/test'

import {
  createShareSnapshot,
  setComposerValueForTest,
  waitForHistoryRuns,
} from './helpers.js'
import {
  FAST_RUN_CMD,
  LONG_RUN_CMD,
  createManifest,
  freshHome,
  installCommonCaptureMocks,
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
  await expect(page.locator('#mobile-recents-sheet')).toBeVisible()
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
      await page.locator('#search-input').fill('localhost')
      await expect(page.locator('.tab-panel.active .output mark.search-hl').first()).toBeVisible()
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
        { text: 'darklab-shell' },
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
    slug: 'history-sheet',
    title: 'History sheet',
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
    slug: 'history-sheet-search-filters-expanded',
    title: 'History sheet - command search with filters expanded',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runCommandMobile(page, 'hostname')
      await runCommandMobile(page, 'date')
      await waitForHistoryRuns(page, 2)
      await openRecentsSheet(page)
      await page.locator('#mobile-recents-search').fill('host')
      await page.locator('#mobile-recents-filters-toggle').click()
      await expect(page.locator('#mobile-recents-filters-expanded')).toBeVisible()
      await page.locator('#mobile-recents-filter-root').fill('host')
    },
  },
  {
    slug: 'history-sheet-search-filters-collapsed-chip',
    title: 'History sheet - command search with filters collapsed and chip shown',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runCommandMobile(page, 'hostname')
      await runCommandMobile(page, 'date')
      await waitForHistoryRuns(page, 2)
      await openRecentsSheet(page)
      await page.locator('#mobile-recents-search').fill('host')
      await page.locator('#mobile-recents-filters-toggle').click()
      await page.locator('#mobile-recents-filter-root').fill('host')
      await page.locator('#mobile-recents-filters-toggle').click()
      await expect(page.locator('#mobile-recents-chips > *').first()).toBeVisible()
    },
  },
  {
    slug: 'history-sheet-delete-all-confirmation',
    title: 'History sheet - delete-all confirmation modal',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runCommandMobile(page, 'hostname')
      await runCommandMobile(page, 'date')
      await waitForHistoryRuns(page, 2)
      await openRecentsSheet(page)
      await page.locator('#mobile-recents-clear').click()
      await expect(page.locator('#confirm-host')).toBeVisible()
    },
  },
  {
    slug: 'history-sheet-delete-confirmation',
    title: 'History sheet - delete confirmation modal',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runCommandMobile(page, 'hostname')
      await waitForHistoryRuns(page, 1)
      await openRecentsSheet(page)
      await page.locator('#mobile-recents-list .sheet-item').first().locator('.sheet-item-action', { hasText: 'delete' }).click()
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
      await page.locator('#mobile-recents-list .sheet-item').first().locator('.sheet-item-action', { hasText: 'permalink' }).click()
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

test('mobile screenshot capture pack', async ({ page }) => {
  test.skip(!process.env.RUN_CAPTURE, 'set RUN_CAPTURE=1 to run the UI screenshot capture pack')
  test.setTimeout(3_600_000)

  await installCommonCaptureMocks(page)

  const themes = resolveCaptureThemes()
  const manifest = createManifest('mobile')

  for (const themeName of themes) {
    for (const [index, scene] of scenes.entries()) {
      await test.step(`${themeLabel(themeName)} :: ${scene.title}`, async () => {
        await scene.run(page, themeName)
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
