import { test, expect } from '@playwright/test'

import {
  createShareSnapshot,
  openHistory,
  openHistoryWithEntries,
  runCommand,
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
  waitForWorkflowsReady,
  writeManifest,
} from './ui_capture_shared.js'

const freshCaptureHome = (page, opts = {}) => freshHome(page, {
  ...opts,
  guardrailMode: 'desktop',
})

async function runLongCaptureCommand(page) {
  await page.locator('#cmd').fill(LONG_RUN_CMD)
  await page.keyboard.press('Enter')
  await expect(page.locator('.status-pill')).toHaveText('RUNNING', { timeout: 10_000 })
}

async function runFastCaptureCommand(page) {
  await page.locator('#cmd').fill(FAST_RUN_CMD)
  await page.keyboard.press('Enter')
  await page.waitForFunction(
    (expectedCmd) => {
      const tab = typeof getActiveTab === 'function' ? getActiveTab() : null
      return !!tab && tab.command === expectedCmd && tab.st !== 'running'
    },
    FAST_RUN_CMD,
    { timeout: 10_000 },
  )
}

async function openScopedWorkflow(page) {
  await waitForWorkflowsReady(page)
  const workflowsClosed = await page.locator('#rail-section-workflows').evaluate((node) =>
    node.classList.contains('closed'),
  )
  if (workflowsClosed) await page.locator('#rail-workflows-header').click()
  await page.locator('#rail-workflows-list .rail-item').first().click()
  await expect(page.locator('#workflows-modal')).toBeVisible()
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
    slug: 'main-autocomplete',
    title: 'Main UI - autocomplete menu open',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await setComposerValueForTest(page, 'curl -')
      await expect(page.locator('#ac-dropdown')).not.toHaveClass(/u-hidden/)
    },
  },
  {
    slug: 'main-reverse-history-search',
    title: 'Main UI - reverse history search open',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runCommand(page, 'hostname')
      await runCommand(page, 'date')
      await page.locator('#cmd').press('Control+r')
      await page.locator('#cmd').type('host')
      await expect(page.locator('#hist-search-dropdown')).not.toHaveClass(/u-hidden/)
    },
  },
  {
    slug: 'main-multiple-tabs',
    title: 'Main UI - multiple tabs open',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runCommand(page, 'hostname')
      await page.locator('#new-tab-btn').click()
      await runCommand(page, 'date')
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
      await runCommand(page, 'hostname')
      await page.locator('#new-tab-btn').click()
      await runLongCaptureCommand(page)
    },
  },
  {
    slug: 'main-running-inactive-tab',
    title: 'Main UI - inactive tab running',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runLongCaptureCommand(page)
      await page.locator('#new-tab-btn').click()
      await runFastCaptureCommand(page)
      await expect(page.locator('.tab').first().locator('.tab-status.running')).toBeVisible()
    },
  },
  {
    slug: 'kill-confirmation-modal',
    title: 'Main UI - kill confirmation modal',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runLongCaptureCommand(page)
      await page.locator('#hud-actions [data-action="kill"]').click()
      await expect(page.locator('#confirm-host [data-confirm-card]')).toBeVisible()
    },
  },
  {
    slug: 'confirm-modal-three-actions-stacked',
    title: 'Main UI - confirmation modal with three stacked actions',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await page.evaluate(() => {
        window.showConfirm({
          title: 'Unsaved changes',
          body: 'Keep editing, save, or discard the current transcript?',
          actions: [
            { id: 'save', role: 'primary', label: 'Save and close' },
            { id: 'discard', role: 'destructive', label: 'Discard' },
            { id: 'cancel', role: 'cancel', label: 'Keep editing' },
          ],
        })
      })
      await expect(page.locator('#confirm-host [data-confirm-card]')).toBeVisible()
      await expect(page.locator('#confirm-host [data-confirm-actions].modal-actions-stacked')).toBeVisible()
    },
  },
  {
    slug: 'save-menu-open',
    title: 'Main UI - save menu open',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runCommand(page, 'hostname')
      await page.locator('.hud-save-wrap [data-action="save-menu"]').click()
      await expect(page.locator('.hud-save-wrap.open .save-menu')).toBeVisible()
    },
  },
  {
    slug: 'rail-open-both-expanded',
    title: 'Main UI - rail open with Recents and Workflows expanded',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runCommand(page, 'hostname')
      await runCommand(page, 'date')
      await waitForWorkflowsReady(page)
      const workflowsClosed = await page.locator('#rail-section-workflows').evaluate((node) =>
        node.classList.contains('closed'),
      )
      if (workflowsClosed) await page.locator('#rail-workflows-header').click()
      await expect(page.locator('#rail-section-recent')).not.toHaveClass(/closed/)
      await expect(page.locator('#rail-section-workflows')).not.toHaveClass(/closed/)
    },
  },
  {
    slug: 'rail-open-recents-only',
    title: 'Main UI - rail open with Recents expanded and Workflows collapsed',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runCommand(page, 'hostname')
      await waitForWorkflowsReady(page)
      const workflowsOpen = !(await page.locator('#rail-section-workflows').evaluate((node) =>
        node.classList.contains('closed'),
      ))
      if (workflowsOpen) await page.locator('#rail-workflows-header').click()
      await expect(page.locator('#rail-section-recent')).not.toHaveClass(/closed/)
      await expect(page.locator('#rail-section-workflows')).toHaveClass(/closed/)
    },
  },
  {
    slug: 'rail-open-both-collapsed',
    title: 'Main UI - rail open with Recents and Workflows collapsed',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await waitForWorkflowsReady(page)
      const recentOpen = !(await page.locator('#rail-section-recent').evaluate((node) =>
        node.classList.contains('closed'),
      ))
      if (recentOpen) await page.locator('#rail-recent-header').click()
      const workflowsOpen = !(await page.locator('#rail-section-workflows').evaluate((node) =>
        node.classList.contains('closed'),
      ))
      if (workflowsOpen) await page.locator('#rail-workflows-header').click()
      await expect(page.locator('#rail-section-recent')).toHaveClass(/closed/)
      await expect(page.locator('#rail-section-workflows')).toHaveClass(/closed/)
    },
  },
  {
    slug: 'rail-closed',
    title: 'Main UI - rail collapsed',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await page.locator('#rail-collapse-btn').click()
      await expect(page.locator('#rail')).toHaveClass(/rail-collapsed/)
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
      await page.locator('#search-toggle-btn').click()
      await page.locator('#search-input').fill('localhost')
      await expect(page.locator('.tab-panel.active .output mark.search-hl').first()).toBeVisible()
    },
  },
  {
    slug: 'workflow-modal-example',
    title: 'Main UI - workflow modal example',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await openScopedWorkflow(page)
    },
  },
  {
    slug: 'history-drawer',
    title: 'Main UI - history drawer',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runCommand(page, 'hostname')
      await openHistoryWithEntries(page)
    },
  },
  {
    slug: 'history-drawer-snapshot-row',
    title: 'Main UI - history drawer with snapshot row',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runCommand(page, 'hostname')
      await createShareSnapshot(page)
      await openHistory(page)
      const snapshotEntry = page.locator('#history-list .history-entry-snapshot').first()
      await expect(snapshotEntry).toBeVisible()
      await expect(snapshotEntry.locator('.history-entry-kind-snapshot')).toHaveText('SNAPSHOT')
      await expect(snapshotEntry.locator('[data-action="open"]')).toBeVisible()
      await expect(snapshotEntry.locator('[data-action="link"]')).toBeVisible()
      await expect(snapshotEntry.locator('[data-action="delete"]')).toBeVisible()
    },
  },
  {
    slug: 'history-drawer-search-chip',
    title: 'Main UI - history drawer command search with chip',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runCommand(page, 'hostname')
      await runCommand(page, 'date')
      await openHistoryWithEntries(page)
      await page.locator('#history-search-input').fill('host')
      await page.waitForTimeout(300)
      await expect(page.locator('#history-active-filters')).not.toHaveClass(/u-hidden/)
    },
  },
  {
    slug: 'history-drawer-delete-all-confirmation',
    title: 'Main UI - history drawer delete-all confirmation modal',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runCommand(page, 'hostname')
      await runCommand(page, 'date')
      await openHistoryWithEntries(page)
      await page.locator('#hist-clear-all-btn').click()
      await expect(page.locator('#confirm-host')).toBeVisible()
    },
  },
  {
    slug: 'history-drawer-delete-confirmation',
    title: 'Main UI - history drawer delete confirmation modal',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runCommand(page, 'hostname')
      await openHistoryWithEntries(page)
      await page.locator('.history-entry').first().locator('[data-action="delete"]').click()
      await expect(page.locator('#confirm-host')).toBeVisible()
    },
  },
  {
    slug: 'options-modal',
    title: 'Main UI - options modal',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await page.locator('.rail-nav [data-action="options"]').click()
      await expect(page.locator('#options-modal')).toBeVisible()
    },
  },
  {
    slug: 'session-token-clear-confirmation',
    title: 'Main UI - session-token clear confirmation modal',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await page.locator('.rail-nav [data-action="options"]').click()
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
    title: 'Main UI - theme modal',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await page.locator('.rail-nav [data-action="theme"]').click()
      await expect(page.locator('#theme-modal')).toBeVisible()
    },
  },
  {
    slug: 'faq-modal',
    title: 'Main UI - FAQ modal',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await page.locator('.rail-nav [data-action="faq"]').click()
      await expect(page.locator('#faq-modal')).toBeVisible()
    },
  },
  {
    slug: 'shortcuts-overlay',
    title: 'Main UI - keyboard shortcuts overlay',
    route: '/',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await page.evaluate(() => window.showShortcutsOverlay && window.showShortcutsOverlay())
      await expect(page.locator('#shortcuts-overlay.open')).toBeVisible()
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
        if (typeof applyLineNumberPreference === 'function') applyLineNumberPreference('on', false)
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
      await runCommand(page, 'ping -c 4 darklab.sh')
      await page.evaluate(() => {
        if (typeof applyTimestampPreference === 'function') applyTimestampPreference('elapsed', false)
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
      await runCommand(page, 'ping -c 4 darklab.sh')
      await page.evaluate(() => {
        if (typeof applyLineNumberPreference === 'function') applyLineNumberPreference('on', false)
        if (typeof applyTimestampPreference === 'function') applyTimestampPreference('elapsed', false)
      })
      await expect(page.locator('body')).toHaveClass(/ln-on/)
      await expect(page.locator('body')).toHaveClass(/ts-elapsed/)
    },
  },
  {
    slug: 'snapshot-page',
    title: 'Snapshot page',
    route: '/share/:id',
    run: async (page, themeName) => {
      await freshCaptureHome(page, { themeName })
      await runCommand(page, 'hostname')
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
      await runCommand(page, 'hostname')
      await openHistoryWithEntries(page)
      await page
        .locator('#history-list .history-entry:not(.history-entry-snapshot)')
        .first()
        .locator('[data-action="permalink"]')
        .click()
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

test('desktop screenshot capture pack', async ({ page }) => {
  test.skip(!process.env.RUN_CAPTURE, 'set RUN_CAPTURE=1 to run the UI screenshot capture pack')
  test.setTimeout(3_600_000)

  await installCommonCaptureMocks(page)

  const themes = resolveCaptureThemes()
  const manifest = createManifest('desktop')

  for (const themeName of themes) {
    for (const [index, scene] of scenes.entries()) {
      await test.step(`${themeLabel(themeName)} :: ${scene.title}`, async () => {
        await scene.run(page, themeName)
        await saveCapture(page, manifest, {
          ui: 'desktop',
          themeName,
          order: index + 1,
          slug: scene.slug,
          title: scene.title,
          route: scene.route,
        })
      })
    }
  }

  writeManifest('desktop', manifest)
})
