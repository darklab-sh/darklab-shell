import { test, expect } from '@playwright/test'
import { runCommand, openHistoryWithEntries, makeTestIp } from './helpers.js'

const CMD = 'hostname'
const TEST_IP = makeTestIp(42)

test.describe('failure paths', () => {
  test.beforeEach(async ({ page }) => {
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': TEST_IP })
    await page.addInitScript(() => {
      Object.defineProperty(navigator, 'clipboard', {
        value: {
          writeText: text => {
            window.__clipboardText = text
            return Promise.resolve()
          },
        },
        configurable: true,
      })
    })
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('a 403 /run response renders a denied command message', async ({ page }) => {
    await page.route('**/run', route => {
      route.fulfill({
        status: 403,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Command not allowed.' }),
      })
    })

    await runCommand(page, CMD)

    await expect(page.locator('.status-pill')).toHaveText('ERROR')
    await expect(page.locator('.tab-panel.active .output')).toContainText('[denied] Command not allowed.')
  })

  test('a 429 /run response renders a rate limit message', async ({ page }) => {
    await page.route('**/run', route => {
      route.fulfill({
        status: 429,
        contentType: 'text/plain',
        body: 'rate limited',
      })
    })

    await runCommand(page, CMD)

    await expect(page.locator('.status-pill')).toHaveText('ERROR')
    await expect(page.locator('.tab-panel.active .output')).toContainText('[rate limited] Too many requests. Please wait a moment.')
  })

  test('a rejected /run request renders a friendly offline message', async ({ page }) => {
    await page.route('**/run', route => {
      route.abort('failed')
    })

    await runCommand(page, CMD)

    await expect(page.locator('.status-pill')).toHaveText('ERROR')
    await expect(page.locator('.tab-panel.active .output')).toContainText('[connection error] Unable to reach the server. Check that it is running and try again.')
  })

  test('permalink shows a failure toast when /share returns invalid JSON', async ({ page }) => {
    await page.route('**/share', route => {
      route.fulfill({
        status: 500,
        contentType: 'text/plain',
        body: 'share failed',
      })
    })

    await runCommand(page, CMD)
    await page.locator('[data-action="permalink"]').click()
    await page.locator('#share-redaction-confirm').click()

    await expect(page.locator('#permalink-toast')).toContainText('Failed to create permalink')
  })

  test('deleting a history entry shows a failure toast when the delete request fails', async ({ page }) => {
    await page.route('**/history/**', route => {
      if (route.request().method() === 'DELETE') {
        route.abort('failed')
        return
      }
      route.continue()
    })

    await runCommand(page, CMD)
    await openHistoryWithEntries(page)

    const entry = page.locator('.history-entry').first()
    await entry.locator('[data-action="delete"]').click()
    await page.locator('#hist-del-confirm').click()

    await expect(page.locator('#permalink-toast')).toContainText('Failed to delete run')
    await expect(page.locator('.history-entry')).toHaveCount(1)
  })

  test('clearing history shows a failure toast when the delete request fails', async ({ page }) => {
    await page.route('**/history', route => {
      if (route.request().method() === 'DELETE') {
        route.abort('failed')
        return
      }
      route.continue()
    })

    await runCommand(page, CMD)
    await page.waitForTimeout(1200)
    await runCommand(page, 'date')
    await page.locator('#hist-btn').click()
    await page.locator('#history-list > *').first().waitFor({ state: 'visible' })
    await page.locator('#hist-clear-all-btn').click()
    await page.locator('#hist-del-confirm').click()

    await expect(page.locator('#permalink-toast')).toContainText('Failed to clear history')
    await expect(page.locator('.hist-chip')).toHaveCount(2)
  })
})
