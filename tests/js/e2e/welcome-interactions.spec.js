import { test, expect } from '@playwright/test'
import { setupWelcomePage } from './welcome.helpers.js'

test.describe('welcome interactions', () => {
  test.beforeEach(async ({ page }) => {
    await setupWelcomePage(page)
  })

  test('clicking a sampled welcome command text loads it into the prompt', async ({ page }) => {
    const sample = page
      .locator('.welcome-command')
      .nth(0)
      .locator('.welcome-command-text.welcome-command-loadable')
    await expect(sample).toContainText('echo ready', { timeout: 15_000 })

    await sample.click()

    await expect(page.locator('#cmd')).toHaveValue('echo ready')
    await expect(page.locator('#cmd')).toBeFocused()
  })

  test('pressing Enter on a sampled welcome command text loads it into the prompt', async ({
    page,
  }) => {
    const sample = page
      .locator('.welcome-command')
      .nth(0)
      .locator('.welcome-command-text.welcome-command-loadable')
    await expect(sample).toContainText('echo ready', { timeout: 15_000 })

    await sample.focus()
    await sample.evaluate((el) => {
      el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
    })

    await expect(page.locator('#cmd')).toHaveValue('echo ready')
    await expect(page.locator('#cmd')).toBeFocused()
  })

  test('clicking the try this first badge loads the featured command into the prompt', async ({
    page,
  }) => {
    const badge = page.locator('.welcome-command-badge')
    await expect(badge).toContainText('try this first', { timeout: 15_000 })

    await badge.click()

    await expect(page.locator('#cmd')).toHaveValue('echo ready')
    await expect(page.locator('#cmd')).toBeFocused()
  })

  test('pressing Space on the try this first badge loads the featured command into the prompt', async ({
    page,
  }) => {
    const badge = page.locator('.welcome-command-badge')
    await expect(badge).toContainText('try this first', { timeout: 15_000 })

    await badge.focus()
    await badge.evaluate((el) => {
      el.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', bubbles: true }))
    })

    await expect(page.locator('#cmd')).toHaveValue('echo ready')
    await expect(page.locator('#cmd')).toBeFocused()
  })

  test('pressing Ctrl+C while welcome is active settles the intro without opening kill confirmation', async ({
    page,
  }) => {
    await page.waitForFunction(() => {
      const text = document.querySelector('.wlc-command-text')?.textContent || ''
      return text.length >= 5
    })

    const beforePromptEchoCount = await page
      .locator('.tab-panel.active .output .line.prompt-echo')
      .count()
    await page.locator('#cmd').press('Control+C')

    await expect(page.locator('.welcome-status-loaded')).toHaveCount(5)
    await expect(page.locator('.welcome-command').nth(0)).toContainText('echo ready')
    await expect(page.locator('.welcome-command').nth(1)).toContainText('dig darklab.sh A')
    await expect(page.locator('#kill-overlay')).toBeHidden()
    await expect(page.locator('.tab-panel.active .output .line.prompt-echo')).toHaveCount(
      beforePromptEchoCount + 1,
    )
    await expect(page.locator('#cmd')).toHaveValue('')
    await expect(page.locator('#cmd')).toBeFocused()
  })
})
