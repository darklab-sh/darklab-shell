import { test, expect } from '@playwright/test'
import { runCommand, openHistoryWithEntries, openRailAction, waitForHistoryRuns } from './helpers.js'

const CMD = 'hostname'

test.describe('failure paths', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      Object.defineProperty(navigator, 'clipboard', {
        value: {
          writeText: (text) => {
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

  test('a 403 /runs response renders a denied command message', async ({ page }) => {
    await page.route('**/runs', (route) => {
      route.fulfill({
        status: 403,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Command not allowed.' }),
      })
    })

    await runCommand(page, CMD)

    await expect(page.locator('.status-pill')).toHaveText('IDLE')
    await expect(page.locator('.tab-panel.active .output')).toContainText(
      '[denied] Command not allowed.',
    )
  })

  test('a 429 /runs response renders a rate limit message', async ({ page }) => {
    await page.route('**/runs', (route) => {
      route.fulfill({
        status: 429,
        contentType: 'text/plain',
        body: 'rate limited',
      })
    })

    await runCommand(page, CMD)

    await expect(page.locator('.status-pill')).toHaveText('IDLE')
    await expect(page.locator('.tab-panel.active .output')).toContainText(
      '[rate limited] Too many requests. Please wait a moment.',
    )
  })

  test('a rejected /runs request renders a friendly offline message', async ({ page }) => {
    await page.route('**/runs', (route) => {
      route.abort('failed')
    })

    await runCommand(page, CMD)

    await expect(page.locator('.status-pill')).toHaveText('IDLE')
    await expect(page.locator('.tab-panel.active .output')).toContainText(
      '[connection error] Unable to contact the server right now. Please try again in a moment. If this keeps happening, contact the shell operator.',
    )
  })

  test('permalink shows a failure toast when /share returns invalid JSON', async ({ page }) => {
    await page.route('**/share', (route) => {
      route.fulfill({
        status: 500,
        contentType: 'text/plain',
        body: 'share failed',
      })
    })

    await runCommand(page, CMD)
    await page.locator('.hud-actions [data-action="permalink"]').click()
    await page.locator('#confirm-host [data-confirm-action-id="redacted"]').click()

    await expect(page.locator('#permalink-toast')).toContainText('Failed to create permalink')
  })

  test('deleting a history entry shows a failure toast when the delete request fails', async ({
    page,
  }) => {
    await page.route('**/history/**', (route) => {
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
    await page.locator('#confirm-host [data-confirm-action-id="one"]').click()

    await expect(page.locator('#permalink-toast')).toContainText('Failed to delete run')
    await expect(page.locator('.history-entry')).toHaveCount(1)
  })

  test('clearing history shows a failure toast when the delete request fails', async ({ page }) => {
    await page.route('**/history', (route) => {
      if (route.request().method() === 'DELETE') {
        route.abort('failed')
        return
      }
      route.continue()
    })

    await runCommand(page, CMD)
    await waitForHistoryRuns(page, 1)
    await runCommand(page, 'date')
    await page.locator('.rail-nav [data-action="history"]').click()
    await page.locator('#history-list > *').first().waitFor({ state: 'visible' })
    await page.locator('#hist-clear-all-btn').click()
    await page.locator('#confirm-host [data-confirm-action-id="all"]').click()

    await expect(page.locator('#permalink-toast')).toContainText('Failed to clear history')
    await expect(page.locator('.hist-chip')).toHaveCount(2)
  })

  test('lazy modal fragments show a failure toast and retry on the next open', async ({ page }) => {
    const pageErrors = []
    const clientLogs = []
    page.on('pageerror', (err) => pageErrors.push(err.message))
    await page.route('**/log', (route) => {
      try {
        clientLogs.push(JSON.parse(route.request().postData() || '{}'))
      } catch (_) {}
      route.fulfill({ status: 204, body: '' })
    })

    let projectFragmentAttempts = 0
    await page.route('**/static/fragments/project_workspace.html', (route) => {
      projectFragmentAttempts += 1
      if (projectFragmentAttempts === 1) {
        route.fulfill({ status: 404, contentType: 'text/html', body: 'missing project fragment' })
        return
      }
      route.continue()
    })

    await openRailAction(page, 'projects')
    await expect(page.locator('#permalink-toast')).toContainText('Failed to open Projects')
    await expect(page.locator('#project-workspace-overlay')).toHaveCount(0)
    await expect.poll(() => clientLogs.map((entry) => entry.event)).toContain('PROJECT_WORKSPACE_OPEN_FAILED')

    await openRailAction(page, 'projects')
    await expect(page.locator('#project-workspace-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#project-workspace-body')).not.toContainText('Loading projects...')
    await page.locator('.project-workspace-close').click()
    await expect(page.locator('#project-workspace-overlay')).not.toHaveClass(/\bopen\b/)

    let atlasFragmentAttempts = 0
    await page.route('**/static/fragments/atlas_overlay.html', (route) => {
      atlasFragmentAttempts += 1
      if (atlasFragmentAttempts === 1) {
        route.fulfill({ status: 404, contentType: 'text/html', body: 'missing atlas fragment' })
        return
      }
      route.continue()
    })

    await openRailAction(page, 'atlas')
    await expect(page.locator('#permalink-toast')).toContainText('Failed to open Atlas')
    await expect(page.locator('#atlas-overlay')).toHaveCount(0)
    await expect.poll(() => clientLogs.map((entry) => entry.event)).toContain('ATLAS_OPEN_FAILED')
    expect(clientLogs).toContainEqual(expect.objectContaining({
      event: 'LAZY_DOM_FRAGMENT_LOAD_FAILED',
      details: expect.objectContaining({ fragment_name: 'atlas_overlay' }),
    }))

    await openRailAction(page, 'atlas')
    await expect(page.locator('#atlas-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#atlas-overlay')).toContainText(/ATLAS|No findings queued/i)
    expect(pageErrors).toEqual([])
  })
})
