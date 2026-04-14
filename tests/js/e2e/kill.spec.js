import { test, expect } from '@playwright/test'
import { ensurePromptReady, makeTestIp } from './helpers.js'

// A long-running command that is in the allowlist and won't exit on its own.
const LONG_CMD = 'ping -c 1000 127.0.0.1'
const TEST_IP = makeTestIp(63)

test.describe('kill running command', () => {
  test.beforeEach(async ({ page }) => {
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': TEST_IP })
    await page.addInitScript(() => {
      const originalFetch = window.fetch.bind(window)
      const encoder = new TextEncoder()
      let longRunController = null

      const finishLongRun = () => {
        if (!longRunController) return
        longRunController.enqueue(encoder.encode(
          'data: {"type":"exit","code":143,"elapsed":0.0}\n\n',
        ))
        longRunController.close()
        longRunController = null
      }

      window.fetch = async (input, init) => {
        const url = typeof input === 'string' ? input : input.url
        const rawBody = typeof init?.body === 'string' ? init.body : ''

        if (url.endsWith('/run') && init?.method === 'POST' && rawBody.includes('ping -c 1000 127.0.0.1')) {
          const body = new ReadableStream({
            start(controller) {
              longRunController = controller
              controller.enqueue(encoder.encode(
                'data: {"type":"started","run_id":"kill-spec-long-run"}\n\n',
              ))
              controller.enqueue(encoder.encode(
                'data: {"type":"output","text":"long run started\\n"}\n\n',
              ))
              // Leave the stream open so the command stays in RUNNING state.
            },
          })

          return new Response(body, {
            status: 200,
            headers: { 'Content-Type': 'text/event-stream' },
          })
        }

        if (url.endsWith('/kill') && init?.method === 'POST' && rawBody.includes('kill-spec-long-run')) {
          finishLongRun()
          return new Response('{}', {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        }

        return originalFetch(input, init)
      }
    })
    await page.goto('/')
    await page.locator('#cmd').waitFor()
    await ensurePromptReady(page)
  })

  test('kill button stops a running command and status becomes KILLED', async ({ page }) => {
    // Start a long-running command (don't use runCommand — we don't want to wait for it to finish)
    await page.locator('#cmd').fill(LONG_CMD)
    await page.keyboard.press('Enter')

    // Wait for the status pill to show RUNNING
    await expect(page.locator('.status-pill')).toHaveText('RUNNING', { timeout: 10_000 })

    // Kill button should be visible while the command is running
    const killBtn = page.locator('.tab-kill-btn')
    await killBtn.waitFor({ state: 'visible', timeout: 5_000 })
    await killBtn.click()

    // Confirm the kill in the modal
    await page.locator('#kill-confirm').waitFor({ state: 'visible' })
    await page.locator('#kill-confirm').click()

    // Status should transition to KILLED
    await expect(page.locator('.status-pill')).toHaveText('KILLED', { timeout: 10_000 })
  })

  test('kill button disappears after the command is killed', async ({ page }) => {
    await page.locator('#cmd').fill(LONG_CMD)
    await page.keyboard.press('Enter')
    await expect(page.locator('.status-pill')).toHaveText('RUNNING', { timeout: 10_000 })

    await page.locator('.tab-kill-btn').waitFor({ state: 'visible' })
    await page.locator('.tab-kill-btn').click()
    await page.locator('#kill-confirm').waitFor({ state: 'visible' })
    await page.locator('#kill-confirm').click()

    await expect(page.locator('.status-pill')).toHaveText('KILLED', { timeout: 10_000 })
    // Kill button should no longer be visible once the command has ended
    await expect(page.locator('.tab-kill-btn')).toBeHidden()
  })

  test('Ctrl+C opens the kill confirmation modal while a command is running', async ({ page }) => {
    await page.locator('#cmd').fill(LONG_CMD)
    await page.keyboard.press('Enter')
    await expect(page.locator('.status-pill')).toHaveText('RUNNING', { timeout: 10_000 })

    await page.locator('#cmd').press('Control+c')

    await expect(page.locator('#kill-overlay')).toBeVisible()
    await expect(page.locator('#kill-confirm')).toBeVisible()

    await page.locator('#kill-cancel').click()
    await expect(page.locator('#kill-overlay')).toBeHidden()
  })

  test('closing the only running tab kills the command and resets the shell', async ({ page }) => {
    await page.locator('#cmd').fill(LONG_CMD)
    await page.keyboard.press('Enter')
    await expect(page.locator('.status-pill')).toHaveText('RUNNING', { timeout: 10_000 })

    await page.locator('.tab .tab-close').click()

    await expect(page.locator('.status-pill')).toHaveText('IDLE', { timeout: 10_000 })
    await expect(page.locator('.tab .tab-label')).toHaveText('tab 1')
    await expect(page.locator('.tab-panel .output .line')).toHaveCount(0)
    await expect(page.locator('.tab-kill-btn')).toBeHidden()
  })

  test('Enter confirms kill while the kill confirmation modal is open', async ({ page }) => {
    await page.locator('#cmd').fill(LONG_CMD)
    await page.keyboard.press('Enter')
    await expect(page.locator('.status-pill')).toHaveText('RUNNING', { timeout: 10_000 })

    await page.locator('#cmd').press('Control+c')
    await expect(page.locator('#kill-overlay')).toBeVisible()

    await page.keyboard.press('Enter')

    await expect(page.locator('.status-pill')).toHaveText('KILLED', { timeout: 10_000 })
    await expect(page.locator('#kill-overlay')).toBeHidden()
  })

  test('Escape cancels kill while the kill confirmation modal is open', async ({ page }) => {
    await page.locator('#cmd').fill(LONG_CMD)
    await page.keyboard.press('Enter')
    await expect(page.locator('.status-pill')).toHaveText('RUNNING', { timeout: 10_000 })

    await page.locator('#cmd').press('Control+c')
    await expect(page.locator('#kill-overlay')).toBeVisible()

    await page.keyboard.press('Escape')

    await expect(page.locator('#kill-overlay')).toBeHidden()
    await expect(page.locator('.status-pill')).toHaveText('RUNNING')

    // Clean up the still-running command so the next test starts from a blank session.
    await page.locator('#cmd').press('Control+c')
    await page.locator('#kill-confirm').click()
    await expect(page.locator('.status-pill')).toHaveText('KILLED', { timeout: 10_000 })
  })

  test('Ctrl+C on an idle prompt appends a new prompt line instead of opening kill confirmation', async ({ page }) => {
    await expect(page.locator('.status-pill')).toHaveText('IDLE')

    await page.locator('#cmd').press('Control+c')

    await expect(page.locator('.tab-panel.active .output .line.prompt-echo')).toHaveCount(1)
    await expect(page.locator('#kill-overlay')).toBeHidden()
    await expect(page.locator('#cmd')).toBeFocused()
  })
})
