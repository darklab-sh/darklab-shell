import { test, expect } from '@playwright/test'
import { runCommand } from './helpers.js'
import { CMD, setupWelcomePage } from './welcome.helpers.js'

test.describe('welcome animation', () => {
  test.beforeEach(async ({ page }) => {
    await setupWelcomePage(page)
  })

  test('running a command cancels the welcome animation and clears partial output', async ({
    page,
  }) => {
    await expect(page.locator('.welcome-ascii-art')).toContainText('/$$')
    await expect(page.locator('.welcome-status-loaded')).toHaveCount(5)
    await expect(page.locator('.welcome-command').first()).toContainText('echo ready')

    await page.waitForFunction(() => {
      const text = document.querySelector('.wlc-command-text')?.textContent || ''
      return text.length >= 5
    })

    await runCommand(page, CMD)

    const output = page.locator('.tab-panel.active .output')
    await expect(output).toContainText('status')
    await expect(output).not.toContainText('welcome should disappear')
    await expect(page.locator('.welcome-banner')).toHaveCount(0)
    await expect(page.locator('.welcome-command')).toHaveCount(0)
    await expect(page.locator('.wlc-cursor')).toHaveCount(0)
  })

  test('welcome finishes with a hint row after the intro and command blocks', async ({ page }) => {
    await expect(page.locator('.welcome-ascii-art')).toContainText('/$$')
    await expect(page.locator('.welcome-status-loaded')).toHaveCount(5)
    await expect(page.locator('.welcome-section-header').first()).toContainText(
      'Recommended commands',
    )
    await expect(page.locator('.welcome-command').nth(0)).toContainText('echo ready')
    await expect(page.locator('.welcome-command-featured')).toHaveCount(0)
    await expect(page.locator('.welcome-command-badge')).toContainText('try this first')
    await expect(page.locator('.welcome-tour-cta')).toContainText('Tour the app')
    await expect(page.locator('.welcome-tour-cta')).toHaveClass(/welcome-tour-cta-emphasis/)
    await expect(page.locator('.welcome-tour-cta-visual')).toBeVisible()
    await page.locator('.welcome-tour-cta-visual').click()
    const tourOverlay = page.locator('#tour-overlay')
    await expect(tourOverlay).toHaveClass(/open/)
    await expect(tourOverlay.locator('#tour-chapter-title')).toContainText('Running commands')
    const stepCount = await tourOverlay.locator('.tour-step-dot').count()
    expect(stepCount).toBeGreaterThan(1)
    for (let index = 1; index < stepCount; index += 1) {
      await tourOverlay.locator('#tour-next-btn').click()
    }
    await expect(tourOverlay.locator('#tour-next-btn')).toHaveText('Done')
    await page.keyboard.press('Escape')
    await expect(tourOverlay).not.toHaveClass(/open/)
    await expect(page.locator('.welcome-section-header').nth(1)).toContainText('Helpful hints')
    await expect(page.locator('.line.welcome-hint')).toContainText(
      'Use the history panel to reopen saved runs.',
    )
  })

  test('typing into the prompt settles the remaining welcome intro immediately', async ({
    page,
  }) => {
    await page.waitForFunction(() => {
      const text = document.querySelector('.wlc-command-text')?.textContent || ''
      return text.length >= 5
    })

    await page.locator('#cmd').fill('dig ')

    await expect(page.locator('.welcome-status-loaded')).toHaveCount(5)
    await expect(page.locator('.welcome-command').nth(0)).toContainText('echo ready')
    await expect(page.locator('.welcome-command').nth(1)).toContainText('dig darklab.sh A')
    await expect(page.locator('.line.welcome-hint')).toContainText(
      'Use the history panel to reopen saved runs.',
    )
    await expect(page.locator('#cmd')).toHaveValue('dig ')
  })

  test('pressing Space in the prompt settles the remaining welcome intro immediately', async ({
    page,
  }) => {
    await page.waitForFunction(() => {
      const text = document.querySelector('.wlc-command-text')?.textContent || ''
      return text.length >= 5
    })

    await page.locator('#cmd').press(' ')

    await expect(page.locator('.welcome-status-loaded')).toHaveCount(5)
    await expect(page.locator('.welcome-command').nth(0)).toContainText('echo ready')
    await expect(page.locator('.welcome-command').nth(1)).toContainText('dig darklab.sh A')
    await expect(page.locator('.line.welcome-hint')).toContainText(
      'Use the history panel to reopen saved runs.',
    )
    await expect(page.locator('#cmd')).toHaveValue('')
  })

  test('pressing Escape in the prompt settles welcome without changing input text', async ({
    page,
  }) => {
    await page.waitForFunction(() => {
      const text = document.querySelector('.wlc-command-text')?.textContent || ''
      return text.length >= 5
    })

    await page.locator('#cmd').press('Escape')

    await expect(page.locator('.welcome-status-loaded')).toHaveCount(5)
    await expect(page.locator('.welcome-command').nth(0)).toContainText('echo ready')
    await expect(page.locator('.welcome-command').nth(1)).toContainText('dig darklab.sh A')
    await expect(page.locator('.line.welcome-hint')).toContainText(
      'Use the history panel to reopen saved runs.',
    )
    await expect(page.locator('#cmd')).toHaveValue('')
    await expect(page.locator('#cmd')).toBeFocused()
  })
})
