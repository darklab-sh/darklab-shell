import { test, expect } from '@playwright/test'
import { runCommand } from './helpers.js'
import { CMD, setupWelcomePage } from './welcome.helpers.js'

test.describe('welcome context', () => {
  test.beforeEach(async ({ page }) => {
    await setupWelcomePage(page)
  })

  test('running a command in another tab does not tear down the original welcome tab', async ({
    page,
  }) => {
    await expect(page.locator('.line.welcome-hint')).toContainText(
      'Use the history panel to reopen saved runs.',
      { timeout: 15_000 },
    )

    const originalTab = page.locator('.tab').first()
    await page.locator('#new-tab-btn').click()
    await runCommand(page, CMD)

    const activeOutput = page.locator('.tab-panel.active .output')
    await expect(activeOutput).toContainText('status')

    await originalTab.click()
    await expect(page.locator('.tab-panel.active .welcome-banner')).toHaveCount(1)
    await expect(page.locator('.tab-panel.active .line.welcome-hint')).toContainText(
      'Use the history panel to reopen saved runs.',
    )
  })

  test('clearing a non-welcome tab does not remove the original welcome UI', async ({ page }) => {
    await expect(page.locator('.line.welcome-hint')).toContainText(
      'Use the history panel to reopen saved runs.',
      { timeout: 15_000 },
    )

    const originalTab = page.locator('.tab').first()
    await page.locator('#new-tab-btn').click()
    await page.locator('.tab-panel.active [data-action="clear"]').click()

    await originalTab.click()
    await expect(page.locator('.tab-panel.active .welcome-banner')).toHaveCount(1)
    await expect(page.locator('.tab-panel.active .line.welcome-hint')).toContainText(
      'Use the history panel to reopen saved runs.',
    )
  })

  test.describe('mobile view', () => {
    test.use({ hasTouch: true })

    test('switches to the mobile welcome path with the mobile banner', async ({ page }) => {
      await page.setViewportSize({ width: 390, height: 844 })
      await page.addInitScript(() => {
        sessionStorage.clear()
      })
      await page.reload()
      await page.locator('#mobile-cmd').waitFor()

      await expect(page.locator('.welcome-ascii-art')).toContainText('mobile console')
      await expect(page.locator('.welcome-status-loaded')).toHaveCount(5, { timeout: 15_000 })
      await expect(page.locator('.welcome-command')).toHaveCount(0)
      await expect(page.locator('.welcome-section-header')).toContainText('Helpful hints')
      await expect(page.locator('.line.welcome-hint')).toContainText(
        /Tap the prompt|Use the mobile menu|helper row|Rotate the device|Long runs/,
      )
      await expect(page.locator('#mobile-run-btn')).toBeVisible()
    })
  })
})
