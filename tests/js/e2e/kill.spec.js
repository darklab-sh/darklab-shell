import { test, expect } from '@playwright/test'

// A long-running command that is in the allowlist and won't exit on its own.
const LONG_CMD = 'ping -c 1000 127.0.0.1'

test.describe('kill running command', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('kill button stops a running command and status becomes KILLED', async ({ page }) => {
    // Start a long-running command (don't use runCommand — we don't want to wait for it to finish)
    await page.locator('#cmd').fill(LONG_CMD)
    await page.keyboard.press('Enter')

    // Wait for the status pill to show RUNNING
    await expect(page.locator('.status-pill')).toHaveText('RUNNING', { timeout: 10_000 })

    // Kill button should be visible while the command is running
    const killBtn = page.locator('.tab-kill-btn')
    await killBtn.waitFor({ state: 'visible', timeout: 5_000 })
    await killBtn.click()

    // Confirm the kill in the modal
    await page.locator('#kill-confirm').waitFor({ state: 'visible' })
    await page.locator('#kill-confirm').click()

    // Status should transition to KILLED
    await expect(page.locator('.status-pill')).toHaveText('KILLED', { timeout: 10_000 })
  })

  test('kill button disappears after the command is killed', async ({ page }) => {
    await page.locator('#cmd').fill(LONG_CMD)
    await page.keyboard.press('Enter')
    await expect(page.locator('.status-pill')).toHaveText('RUNNING', { timeout: 10_000 })

    await page.locator('.tab-kill-btn').waitFor({ state: 'visible' })
    await page.locator('.tab-kill-btn').click()
    await page.locator('#kill-confirm').waitFor({ state: 'visible' })
    await page.locator('#kill-confirm').click()

    await expect(page.locator('.status-pill')).toHaveText('KILLED', { timeout: 10_000 })
    // Kill button should no longer be visible once the command has ended
    await expect(page.locator('.tab-kill-btn')).toBeHidden()
  })
})
