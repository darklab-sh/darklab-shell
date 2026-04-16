import { test, expect } from '@playwright/test'
import {
  runCommand,
  openHistory,
  openHistoryWithEntries,
  waitForHistoryRuns,
  closeHistory,
  makeTestIp,
} from './helpers.js'

// Use fake shell commands — they bypass the allowlist and complete instantly.
const CMD_A = 'hostname'
const CMD_B = 'date'

test.describe('history drawer', () => {
  test.beforeEach(async ({ page }) => {
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': makeTestIp(62) })
    await page.goto('/')
    // Clear any localStorage state left over from a previous test run and reload
    await page.evaluate(() => localStorage.clear())
    await page.reload()
    await page.locator('#cmd').waitFor()
  })

  test('loading a run from history opens output in a tab without repopulating command input', async ({
    page,
  }) => {
    await runCommand(page, CMD_A)

    // Navigate away by opening a new tab (clears the input)
    await page.locator('#new-tab-btn').click()
    await expect(page.locator('#cmd')).toHaveValue('')

    // Open history and click the entry
    await openHistoryWithEntries(page)
    await page.locator('.history-entry').first().click()

    // Command input remains neutral; loaded output appears in the active tab.
    await expect(page.locator('#cmd')).toHaveValue('')
    await expect(page.locator('.tab-panel.active .output')).toContainText(CMD_A)
  })

  test('clicking a history entry that is already open switches to that tab', async ({ page }) => {
    await runCommand(page, CMD_A)
    const initialTabCount = await page.locator('.tab').count()

    // Open history and click the same entry
    await openHistoryWithEntries(page)
    await page.locator('.history-entry').first().click()

    // No new tab should have been created
    await expect(page.locator('.tab')).toHaveCount(initialTabCount)
    // The existing tab should be active without repopulating the command input
    await expect(page.locator('#cmd')).toHaveValue('')
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

  test('toggling the history star keeps the desktop drawer open', async ({ page }) => {
    await runCommand(page, CMD_A)

    await openHistoryWithEntries(page)
    const firstEntry = page.locator('.history-entry').first()
    await firstEntry.locator('[data-action="star"]').click()

    await expect(page.locator('#history-panel')).toHaveClass(/open/)
    await expect(firstEntry).toHaveClass(/starred/)
  })

  test('clear all history removes all chips including starred ones', async ({ page }) => {
    await runCommand(page, CMD_A)
    await page.waitForTimeout(1200)
    await runCommand(page, CMD_B)
    await waitForHistoryRuns(page, 2)

    // Star both runs
    await openHistoryWithEntries(page)
    let entries = page.locator('.history-entry')
    await entries.nth(0).locator('[data-action="star"]').click()
    entries = page.locator('.history-entry')
    await entries.nth(1).locator('[data-action="star"]').click()
    await closeHistory(page)

    await expect(page.locator('.hist-chip')).toHaveCount(2)

    // Open the history panel to access the clear-all button (it lives inside the panel)
    await openHistory(page)
    await page.locator('#hist-clear-all-btn').click()
    await page.keyboard.press('Escape')
    await expect(page.locator('#hist-del-overlay')).toBeHidden()
    await page.locator('#hist-clear-all-btn').click()
    await page.locator('#hist-del-confirm').click()

    // All chips should be gone
    await expect(page.locator('.hist-chip')).toHaveCount(0)
  })

  test('clicking outside the drawer closes the history panel', async ({ page }) => {
    await runCommand(page, CMD_A)

    await openHistory(page)
    await expect(page.locator('#history-panel')).toHaveClass(/open/)

    await page.locator('.terminal-wrap').click({ position: { x: 12, y: 12 } })

    await expect(page.locator('#history-panel')).not.toHaveClass(/open/)
  })

  test('pressing Escape closes the history panel', async ({ page }) => {
    await runCommand(page, CMD_A)

    await openHistory(page)
    await expect(page.locator('#history-panel')).toHaveClass(/open/)

    await page.keyboard.press('Escape')

    await expect(page.locator('#history-panel')).not.toHaveClass(/open/)
  })

  test('Delete Non-Favorites keeps starred runs and removes the rest', async ({ page }) => {
    await runCommand(page, CMD_A)
    await page.waitForTimeout(1200)
    await runCommand(page, CMD_B)
    await waitForHistoryRuns(page, 2)

    await openHistoryWithEntries(page)
    const entries = page.locator('.history-entry')
    await entries.nth(0).locator('[data-action="star"]').click()
    await closeHistory(page)

    await openHistory(page)
    await page.locator('#hist-clear-all-btn').click()
    await expect(page.locator('#hist-del-nonfav')).toBeVisible()
    await page.locator('#hist-del-nonfav').click()

    await expect(page.locator('.hist-chip.starred')).toHaveCount(1)
    await expect(page.locator('.hist-chip')).toHaveCount(1)
    await expect(page.locator('.history-entry')).toHaveCount(1)
    await expect(page.locator('.history-entry.starred')).toHaveCount(1)
  })

  test('loading a synthetic tail run from history restores the filtered transcript', async ({
    page,
  }) => {
    await runCommand(page, 'help | tail -n 3')

    await page.locator('#new-tab-btn').click()
    await expect(page.locator('#cmd')).toHaveValue('')

    await openHistoryWithEntries(page)
    await page.locator('.history-entry').first().click()

    const output = page.locator('.tab-panel.active .output')
    await expect(output).toContainText('head')
    await expect(output).toContainText('command | head -n <count>')
    await expect(output).toContainText('tail')
    await expect(output).toContainText('command | tail -n <count>')
    await expect(output).toContainText('wc -l')
    await expect(output).not.toContainText('which <cmd>')
    await expect(output).not.toContainText('banner')
    await expect(page.locator('#cmd')).toHaveValue('')
  })
})
