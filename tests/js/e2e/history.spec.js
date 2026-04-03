import { test, expect } from '@playwright/test'
import { runCommand, openHistory, openHistoryWithEntries, closeHistory } from './helpers.js'

// Use allowed commands that complete quickly and exit 0.
// curl against the local test server is ideal — always available and fast.
const CMD_A = 'curl http://localhost:5001/health'
const CMD_B = 'curl http://localhost:5001/config'

test.describe('history drawer', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.locator('#cmd').waitFor()
    // Clear any localStorage state left over from a previous test run
    await page.evaluate(() => localStorage.clear())
  })

  test('loading a run from history populates the command input', async ({ page }) => {
    await runCommand(page, CMD_A)

    // Navigate away by opening a new tab (clears the input)
    await page.locator('#new-tab-btn').click()
    await expect(page.locator('#cmd')).toHaveValue('')

    // Open history and click the entry
    await openHistoryWithEntries(page)
    await page.locator('.history-entry').first().click()

    // The input bar should now contain the command that was loaded
    await expect(page.locator('#cmd')).toHaveValue(CMD_A)
  })

  test('clicking a history entry that is already open switches to that tab', async ({ page }) => {
    await runCommand(page, CMD_A)
    const initialTabCount = await page.locator('.tab').count()

    // Open history and click the same entry
    await openHistoryWithEntries(page)
    await page.locator('.history-entry').first().click()

    // No new tab should have been created
    await expect(page.locator('.tab')).toHaveCount(initialTabCount)
    // The existing tab should be active and show the command in the input
    await expect(page.locator('#cmd')).toHaveValue(CMD_A)
  })

  test('deleting a starred entry removes it from the chip bar', async ({ page }) => {
    await runCommand(page, CMD_A)

    // Star the run from the history panel
    await openHistoryWithEntries(page)
    await page.locator('.history-entry').first().locator('[data-action="star"]').click()

    // Confirm the chip is now starred
    await closeHistory(page)
    await expect(page.locator('.hist-chip.starred')).toHaveCount(1)

    // Delete the run from the history panel
    await openHistory(page)
    await page.locator('.history-entry').first().locator('[data-action="delete"]').click()
    // Confirm deletion in the modal
    await page.locator('#hist-del-confirm').click()

    // The starred chip should be gone
    await expect(page.locator('.hist-chip.starred')).toHaveCount(0)
    await expect(page.locator('.hist-chip')).toHaveCount(0)
  })

  test('clear all history removes all chips including starred ones', async ({ page }) => {
    await runCommand(page, CMD_A)
    await runCommand(page, CMD_B)

    // Star both runs
    await openHistoryWithEntries(page)
    const entries = page.locator('.history-entry')
    await entries.nth(0).locator('[data-action="star"]').click()
    await entries.nth(1).locator('[data-action="star"]').click()
    await closeHistory(page)

    await expect(page.locator('.hist-chip')).toHaveCount(2)

    // Open the history panel to access the clear-all button (it lives inside the panel)
    await openHistory(page)
    await page.locator('#hist-clear-all-btn').click()
    await page.locator('#hist-del-confirm').click()

    // All chips should be gone
    await expect(page.locator('.hist-chip')).toHaveCount(0)
  })
})
