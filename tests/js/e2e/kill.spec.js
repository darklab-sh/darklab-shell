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

  test('Ctrl+C opens the kill confirmation modal while a command is running', async ({ page }) => {
    await page.locator('#cmd').fill(LONG_CMD)
    await page.keyboard.press('Enter')
    await expect(page.locator('.status-pill')).toHaveText('RUNNING', { timeout: 10_000 })

    await page.locator('#cmd').press('Control+c')

    await expect(page.locator('#kill-overlay')).toBeVisible()
    await expect(page.locator('#kill-confirm')).toBeVisible()

    await page.locator('#kill-cancel').click()
    await expect(page.locator('#kill-overlay')).toBeHidden()
  })

  test('Enter confirms kill while the kill confirmation modal is open', async ({ page }) => {
    await page.locator('#cmd').fill(LONG_CMD)
    await page.keyboard.press('Enter')
    await expect(page.locator('.status-pill')).toHaveText('RUNNING', { timeout: 10_000 })

    await page.locator('#cmd').press('Control+c')
    await expect(page.locator('#kill-overlay')).toBeVisible()

    await page.keyboard.press('Enter')

    await expect(page.locator('.status-pill')).toHaveText('KILLED', { timeout: 10_000 })
    await expect(page.locator('#kill-overlay')).toBeHidden()
  })

  test('Escape cancels kill while the kill confirmation modal is open', async ({ page }) => {
    await page.locator('#cmd').fill(LONG_CMD)
    await page.keyboard.press('Enter')
    await expect(page.locator('.status-pill')).toHaveText('RUNNING', { timeout: 10_000 })

    await page.locator('#cmd').press('Control+c')
    await expect(page.locator('#kill-overlay')).toBeVisible()

    await page.keyboard.press('Escape')

    await expect(page.locator('#kill-overlay')).toBeHidden()
    await expect(page.locator('.status-pill')).toHaveText('RUNNING')
  })

  test('Ctrl+C on an idle prompt appends a new prompt line instead of opening kill confirmation', async ({ page }) => {
    await expect(page.locator('.status-pill')).toHaveText('IDLE')

    await page.locator('#cmd').press('Control+c')

    await expect(page.locator('.tab-panel.active .output .line.prompt-echo')).toHaveCount(1)
    await expect(page.locator('#kill-overlay')).toBeHidden()
    await expect(page.locator('#cmd')).toBeFocused()
  })
})
