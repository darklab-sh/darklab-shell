import { test, expect } from '@playwright/test'
import { ensurePromptReady, runCommand, makeTestIp, waitForActiveOutputSettled } from './helpers.js'

const CMD = 'hostname'

// Browser specs share the same backend rate limiter, so derive a stable test-
// scoped IP from the file/title instead of reusing one bucket for the suite.
function testScopedIp(testInfo, baseOffset = 0) {
  const key = `${testInfo.file}:${testInfo.title}`
  let sum = 0
  for (const ch of key) sum = (sum + ch.charCodeAt(0)) % 200
  return makeTestIp(baseOffset + sum)
}

async function pinActiveOutputToLiveBottom(page) {
  await page.evaluate(() => {
    const tab = typeof getActiveTab === 'function' ? getActiveTab() : null
    const out = document.querySelector('.tab-panel.active .output')
    if (!out) return
    if (tab) tab.followOutput = true
    if (typeof _stickOutputToBottom === 'function') _stickOutputToBottom(out, tab)
    else out.scrollTop = out.scrollHeight
  })
  await page.waitForFunction(() => new Promise((resolve) => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const out = document.querySelector('.tab-panel.active .output')
        if (!out) {
          resolve(false)
          return
        }
        const before = out.scrollHeight
        out.scrollTop = out.scrollHeight
        requestAnimationFrame(() => {
          resolve(
            out.scrollHeight === before &&
            out.scrollTop + out.clientHeight >= out.scrollHeight - 16
          )
        })
      })
    })
  }), { timeout: 10_000 })
}

test.describe('timestamp toggle', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': testScopedIp(testInfo, 67) })
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('clicking ts-btn cycles through elapsed → clock → off modes', async ({ page }) => {
    // Default state: no timestamp class on body
    await expect(page.locator('body')).not.toHaveClass(/ts-elapsed|ts-clock/)

    // First click → elapsed mode
    await page.locator('#ts-btn').click()
    await expect(page.locator('body')).toHaveClass(/ts-elapsed/)

    // Second click → clock mode
    await page.locator('#ts-btn').click()
    await expect(page.locator('body')).toHaveClass(/ts-clock/)

    // Third click → off (neither class present)
    await page.locator('#ts-btn').click()
    await expect(page.locator('body')).not.toHaveClass(/ts-elapsed|ts-clock/)
  })

  test('ts-btn has active class when timestamps are enabled', async ({ page }) => {
    await expect(page.locator('#ts-btn')).not.toHaveClass(/active/)

    await page.locator('#ts-btn').click()
    await expect(page.locator('#ts-btn')).toHaveClass(/active/)
  })

  test('output lines have timestamp data attributes after running a command', async ({ page }) => {
    await page.locator('#ts-btn').click() // enable timestamps
    await runCommand(page, CMD)

    // Every line gets data-ts-c (clock time).
    const firstLine = page.locator('.tab-panel.active .output .line').first()
    await expect(firstLine).toHaveAttribute('data-ts-c', /.+/)

    // data-ts-e (elapsed) is only set on lines appended while the run is active,
    // so the echoed command line won't have it. At least one server-output line
    // should carry the elapsed attribute.
    const elapsedLine = page.locator('.tab-panel.active .output .line[data-ts-e]')
    await expect(elapsedLine.first()).toBeVisible()
  })

  test('line numbers work with timestamps and typing continues after toggling display modes', async ({
    page,
  }) => {
    await ensurePromptReady(page)

    await page.locator('#ln-btn').click()
    await expect(page.locator('body')).toHaveClass(/ln-on/)

    await page.locator('#ts-btn').click()
    await expect(page.locator('body')).toHaveClass(/ts-elapsed/)
    await expect(page.locator('#cmd')).toBeFocused()

    await page.locator('#cmd').fill(CMD)
    await page.locator('#cmd').press('Enter')

    await expect(page.locator('#hud-last-exit')).toHaveText('0')
    await waitForActiveOutputSettled(page)

    const prefixedLine = page.locator('.tab-panel.active .output .line[data-prefix]').first()
    await expect(prefixedLine).toHaveAttribute('data-prefix', /^\+\d+\.\ds$/)
    await expect(page.locator('#shell-prompt-wrap')).toHaveAttribute(
      'data-prefix',
      /^\+0\.0s$/,
    )
  })

  test('toggling timestamps or line numbers keeps a long man page pinned to the live bottom', async ({
    page,
  }) => {
    test.setTimeout(90_000)
    await page.waitForFunction(() => {
      const text = document.querySelector('.wlc-command-text')?.textContent || ''
      return text.length >= 5
    })

    await runCommand(page, 'man curl', { timeout: 60_000 })
    await expect(page.locator('#hud-last-exit')).toHaveText('0', { timeout: 15_000 })

    const output = page.locator('.tab-panel.active .output')
    await pinActiveOutputToLiveBottom(page)

    const isAtBottom = async () =>
      output.evaluate((el) => el.scrollTop + el.clientHeight >= el.scrollHeight - 16)
    await expect.poll(isAtBottom).toBeTruthy()

    await page.locator('#ts-btn').click()
    await expect.poll(isAtBottom).toBeTruthy()

    await page.locator('#ln-btn').click()
    await expect.poll(isAtBottom).toBeTruthy()
  })
})
