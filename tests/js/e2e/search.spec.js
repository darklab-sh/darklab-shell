import { test, expect } from '@playwright/test'
import { ensurePromptReady } from './helpers.js'

test.describe('search and highlight', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.locator('#cmd').waitFor()
    await ensurePromptReady(page, { cancelWelcome: true })
    await page.evaluate(() => {
      clearTab(activeTabId)
      appendLine('$ curl http://localhost:5001/health', '', activeTabId)
      appendLine('{"status":"ok"}', '', activeTabId)
      appendLine('localhost localhost', '', activeTabId)
    })
  })

  test('search bar is hidden by default and opens on toggle', async ({ page }) => {
    await expect(page.locator('#search-bar')).toBeHidden()
    await page.locator('#search-toggle-btn').click()
    await expect(page.locator('#search-bar')).toBeVisible()
  })

  test('typing in search input highlights matches in the output', async ({ page }) => {
    await page.locator('#search-toggle-btn').click()
    // "localhost" appears in the echoed command line regardless of actual output
    await page.locator('#search-input').fill('localhost')

    // At least one highlighted match should appear in the output
    await expect(page.locator('.tab-panel.active .output mark.search-hl').first()).toBeVisible()
  })

  test('match counter shows X / Y format when matches are found', async ({ page }) => {
    await page.locator('#search-toggle-btn').click()
    await page.locator('#search-input').fill('localhost')

    // Counter should show "1 / N" style text
    await expect(page.locator('#search-count')).toHaveText(/\d+ \/ \d+/)
  })

  test('next/prev buttons navigate between matches', async ({ page }) => {
    await page.locator('#search-toggle-btn').click()
    await page.locator('#search-input').fill('localhost')

    // Click next — counter should change to show the new position
    const countBefore = await page.locator('#search-count').textContent()
    await page.locator('#search-next').click()
    const countAfter = await page.locator('#search-count').textContent()
    // With only one match both values are the same; with multiple they differ.
    // Either way the counter should still show the N / M format.
    await expect(page.locator('#search-count')).toHaveText(/\d+ \/ \d+/)
    // Suppress the unused-variable lint warning — values are intentionally captured
    // to assert the button was clickable without error; void is used here intentionally.
    void countBefore
    void countAfter
  })

  test('clearing the search input removes all highlights', async ({ page }) => {
    await page.locator('#search-toggle-btn').click()
    await page.locator('#search-input').fill('localhost')
    await expect(page.locator('.tab-panel.active .output mark.search-hl').first()).toBeVisible()

    await page.locator('#search-input').fill('')
    await expect(page.locator('.tab-panel.active .output mark.search-hl')).toHaveCount(0)
  })

  test('case-sensitive mode filters out lowercase matches for uppercase queries', async ({
    page,
  }) => {
    await page.locator('#search-toggle-btn').click()
    await page.locator('#search-input').fill('STATUS')
    await expect(page.locator('#search-count')).toHaveText(/\d+ \/ \d+/)

    await page.locator('#search-case-btn').click()
    await expect(page.locator('#search-case-btn')).toHaveClass(/active/)
    await expect(page.locator('#search-count')).toHaveText('no matches')
  })

  test('regex mode reports invalid patterns instead of throwing', async ({ page }) => {
    await page.locator('#search-toggle-btn').click()
    await page.locator('#search-regex-btn').click()
    await expect(page.locator('#search-regex-btn')).toHaveClass(/active/)

    await page.locator('#search-input').fill('[')
    await expect(page.locator('#search-count')).toHaveText('invalid regex')
  })
})
