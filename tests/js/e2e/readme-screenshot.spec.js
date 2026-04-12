import { test, expect } from '@playwright/test'
import { resolve } from 'path'

const README_SCREENSHOT_PATH = resolve(process.cwd(), 'docs/readme-app.png')

test.describe('README screenshot', () => {
  test('captures the current shell UI for the README hero image', async ({ page }) => {
    // This artifact is committed into the repo, so wait for the welcome screen
    // to reach its stable post-animation state before taking the screenshot.
    test.setTimeout(75_000)
    await page.setViewportSize({ width: 1600, height: 1180 })
    await page.goto('/', { waitUntil: 'domcontentloaded' })
    await expect(page.locator('.terminal-wrap')).toBeVisible()
    await expect(page.locator('header')).toBeVisible()
    await page.waitForFunction(() => {
      const loadedStatuses = document.querySelectorAll('.welcome-status-loaded').length
      const loadingStatuses = document.querySelectorAll('.welcome-status-loading').length
      const liveTypingLine = document.querySelector('.wlc-live')
      const welcomeHintVisible = !!document.querySelector('.line.welcome-hint')
      return loadedStatuses >= 5 && loadingStatuses === 0 && !liveTypingLine && welcomeHintVisible
    }, { timeout: 70_000 })

    await page.addStyleTag({
      content: `
        *, *::before, *::after {
          animation: none !important;
          transition: none !important;
          caret-color: transparent !important;
        }
        .shell-prompt-caret,
        .output-follow-btn {
          display: none !important;
        }
      `,
    })

    await page.screenshot({
      path: README_SCREENSHOT_PATH,
      fullPage: false,
    })
  })
})
