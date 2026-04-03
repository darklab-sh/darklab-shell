import { test, expect } from '@playwright/test'
import { runCommand } from './helpers.js'

// Use allowed commands that complete quickly.
const CMD   = 'curl http://localhost:5001/health'
const CMD_B = 'curl http://localhost:5001/config'

test.describe('tab command recall', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    // Wait for the app to be fully initialised
    await page.locator('#cmd').waitFor()
  })

  test('input is empty on the initial tab', async ({ page }) => {
    await expect(page.locator('#cmd')).toHaveValue('')
  })

  test('switching to a tab restores its last-run command', async ({ page }) => {
    // Run a command on tab 1
    await runCommand(page, CMD)

    // Open a second tab
    await page.locator('#new-tab-btn').click()
    await expect(page.locator('#cmd')).toHaveValue('')

    // Run a different command on tab 2
    await runCommand(page, CMD_B)

    // Switch back to tab 1 (first tab in the bar)
    await page.locator('.tab').first().click()

    // The input should be restored to the command run on tab 1
    await expect(page.locator('#cmd')).toHaveValue(CMD)
  })

  test('a freshly created tab starts with an empty input', async ({ page }) => {
    await runCommand(page, CMD)
    await page.locator('#new-tab-btn').click()
    await expect(page.locator('#cmd')).toHaveValue('')
  })
})
