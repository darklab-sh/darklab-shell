import { test, devices } from '@playwright/test'
import { resolve } from 'path'

const README_MOBILE_SCREENSHOT_PATH = resolve(process.cwd(), 'docs/readme-app-mobile.png')

test.describe('README mobile screenshot', () => {
  test('captures the mobile shell UI for the README hero image', async ({ browser }) => {
    // Use a real mobile device profile so the server's is_mobile detection fires
    // and serves the mobile template, not just a viewport-resized desktop view.
    test.setTimeout(75_000)
    const context = await browser.newContext({
      ...devices['iPhone 14'],
    })
    const page = await context.newPage()

    await page.goto('/', { waitUntil: 'domcontentloaded' })

    // Mobile welcome skips the status-block sequence (includeBlocks: false) so
    // there are no .welcome-status-loaded nodes to count. Wait for _welcomeDone
    // plus the same two settling signals used by the desktop: no live-typing
    // span and at least one hint line visible.
    await page.waitForFunction(() => {
      const liveTypingLine = document.querySelector('.wlc-live')
      const welcomeHintVisible = !!document.querySelector('.line.welcome-hint')
      return window._welcomeDone === true && !liveTypingLine && welcomeHintVisible
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
      path: README_MOBILE_SCREENSHOT_PATH,
      fullPage: false,
    })

    await context.close()
  })
})
