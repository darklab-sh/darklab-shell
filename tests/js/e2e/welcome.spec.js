import { test, expect } from '@playwright/test'
import { runCommand } from './helpers.js'

const CMD = 'curl http://localhost:5001/health'

test.describe('welcome animation', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/welcome', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            cmd: 'abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyz',
            out: 'welcome should disappear if the user starts typing',
          },
        ]),
      })
    })
    await page.route('**/run', route => {
      route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: [
          'data: {"type":"started","run_id":"welcome-test-run"}\n\n',
          'data: {"type":"output","text":"status\\n"}\n\n',
          'data: {"type":"exit","code":0,"elapsed":0.1}\n\n',
        ].join(''),
      })
    })
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('running a command cancels the welcome animation and clears partial output', async ({ page }) => {
    await page.waitForFunction(() => {
      const text = document.querySelector('.wlc-text')?.textContent || ''
      return text.length >= 5
    })

    await runCommand(page, CMD)

    const output = page.locator('.tab-panel.active .output')
    await expect(output).toContainText('status')
    await expect(output).not.toContainText('welcome should disappear')
    await expect(page.locator('.wlc-cursor')).toHaveCount(0)
  })
})
