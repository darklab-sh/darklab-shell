// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { test, expect } from '@playwright/test'
import { ensurePromptReady, keepBrowserWorkspace, makeTestIp, openRailAction } from './helpers.js'

let accessTestIpOffset = 200
test.beforeEach(async ({ page }) => {
  // Each journey is a separate client; keeping several test workspaces must
  // not consume another journey's hourly anonymous-issuance allowance.
  await page.setExtraHTTPHeaders({ 'X-Forwarded-For': makeTestIp(accessTestIpOffset++) })
})

async function resetAnonymousBrowser(page) {
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await page.evaluate(() => localStorage.clear())
  await page.reload({ waitUntil: 'domcontentloaded' })
  await ensurePromptReady(page)
}

async function openAccess(page) {
  await openRailAction(page, 'options')
  await expect(page.locator('#options-overlay')).toHaveClass(/\bopen\b/)
  await page.locator('#options-tab-access').click()
  await expect(page.locator('#options-tab-access')).toHaveAttribute('aria-selected', 'true')
  const panel = page.locator('#options-panel-access')
  await expect(panel).toBeVisible()
  await expect(panel).toHaveAttribute('data-access-panel-bound', '1')
}

async function saveCredentialReveal(page) {
  const reveal = page.locator('#options-access-reveal')
  await expect(reveal).toBeVisible()
  await expect(reveal.locator('.options-access-reveal-value')).toHaveAttribute('aria-label', 'Credential hidden')
  await reveal.getByRole('button', { name: 'Reveal' }).click()
  const secret = (await reveal.locator('.options-access-reveal-value').textContent())?.trim() || ''
  expect(secret).toMatch(/^dlc_v1_crd_[0-9a-f]{32}_[A-Za-z0-9_-]{43}$/)
  await reveal.getByRole('button', { name: 'Close' }).click()
  await expect(reveal).toBeHidden()
  await expect(page.locator('body')).not.toContainText(secret)
  return secret
}

async function chooseConfirmAction(page, actionId) {
  const host = page.locator('#confirm-host')
  const action = host.locator(`[data-confirm-action-id="${actionId}"]`)
  await expect(action).toBeEnabled()
  await action.click()
}

async function expectAccessActions(page, state) {
  const expected = {
    anonymous: ['keep', 'use'],
    invalid: ['discard-invalid'],
    kept: ['add', 'remove'],
  }[state]
  expect(expected).toBeDefined()
  for (const action of ['keep', 'use', 'discard-invalid', 'add', 'remove']) {
    const button = page.locator(`#options-access-${action}-btn`)
    if (expected.includes(action)) await expect(button).toBeVisible()
    else await expect(button).toBeHidden()
  }
}

async function expectCredentialSpacing(page) {
  const spacing = await page.locator('#options-panel-access').evaluate((panel) => {
    const actions = panel.querySelector('#options-access-authenticated-actions')
    const heading = panel.querySelector('#options-access-credentials-section .faq-q')
    const row = panel.querySelector('.options-access-row')
    const style = window.getComputedStyle(row)
    return {
      sectionGap: heading.getBoundingClientRect().top - actions.getBoundingClientRect().bottom,
      rowInsets: [style.paddingTop, style.paddingRight, style.paddingBottom, style.paddingLeft]
        .map(value => Number.parseFloat(value)),
    }
  })
  expect(spacing.sectionGap).toBeGreaterThanOrEqual(15)
  expect(Math.min(...spacing.rowInsets)).toBeGreaterThanOrEqual(10)
}

async function expectRedemptionSpacing(page) {
  const gap = await page.locator('#options-access-redemption').evaluate((form) => {
    const input = form.querySelector('#options-access-redemption-input')
    const actions = form.querySelector('.options-access-actions')
    return actions.getBoundingClientRect().top - input.getBoundingClientRect().bottom
  })
  expect(gap).toBeGreaterThanOrEqual(10)
}

test.describe('workspace Access', () => {
  test.beforeEach(async ({ page }) => resetAnonymousBrowser(page))

  test('restores a kept workspace from a browser holding its retired anonymous identity', async ({ page }) => {
    // Allow the complete keep/reload/restore journey to finish on a busy runner.
    test.setTimeout(60_000)
    const anonymousId = await page.evaluate(() => localStorage.getItem('anonymous_id'))
    const credentialId = await keepBrowserWorkspace(page, { label: 'Restored browser' })
    const savedCredential = await page.evaluate(() => localStorage.getItem('access_credential'))
    await page.evaluate((retiredId) => {
      localStorage.removeItem('access_credential')
      localStorage.setItem('anonymous_id', retiredId)
    }, anonymousId)
    await page.reload({ waitUntil: 'domcontentloaded' })
    await ensurePromptReady(page)
    expect(await page.evaluate(async () => (await apiFetch('/projects')).status)).toBe(401)
    await openAccess(page)
    await page.locator('#options-access-use-btn').click()
    await page.locator('#options-access-redemption-input').fill(savedCredential)
    await page.locator('#options-access-redemption-apply').click()
    await expect(page.locator('#options-access-summary')).toHaveText('Authenticated workspace')
    await expect(page.locator(`[data-credential-id="${credentialId}"]`)).toContainText('Current')
    expect(await page.evaluate(async () => (await apiFetch('/projects')).status)).toBe(200)
  })

  for (const width of [1280, 375]) test.describe(`API tokens at ${width}px`, () => {
    test.use({ viewport: { width, height: 900 }, hasTouch: width < 600, isMobile: width < 600 })

    test('creates a scoped API token from Access', async ({ page }) => {
      // Keeping the workspace reloads the app before the token-creation journey.
      test.setTimeout(60_000)
      await keepBrowserWorkspace(page, { label: 'PAT issuer' })
      if (width < 600) {
        await page.locator('#hamburger-btn').click()
        await page.locator('#mobile-menu-sheet [data-menu-action="access"]').click()
        await expect(page.locator('#options-panel-access')).toHaveAttribute('data-access-panel-bound', '1')
      } else {
        await openAccess(page)
      }
      await expect(page.locator('#options-access-summary')).toHaveText('Authenticated workspace')
      await page.locator('#options-access-add-btn').click()
      const editor = page.locator('#options-access-editor')
      await editor.getByLabel('Credential type').selectOption('pat')
      await expect(editor.getByLabel('Expires in days')).toHaveValue('90')
      const chosen = await editor.locator('[name="pat_scope"]:checked').evaluateAll(nodes => nodes.map(node => node.value).sort())
      expect(chosen).toEqual(['history:read', 'identity:read', 'runs:execute'])
      await editor.getByText('Read run history and output', { exact: true }).click()
      await expect(editor.locator('[value="history:read"]')).not.toBeChecked()
      await editor.getByText('Start and cancel commands', { exact: true }).click()
      await expect(editor.locator('[value="runs:execute"]')).not.toBeChecked()
      await editor.getByLabel('Label', { exact: true }).fill('CLI identity')
      await editor.getByLabel('Expires in days').fill('1')
      const issuedResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/auth/credentials' && response.request().method() === 'POST')
      await editor.getByRole('button', { name: 'Save', exact: true }).click()
      const issued = await issuedResponse
      expect(issued.status()).toBe(201)
      const data = await issued.json()
      expect(data.credential.scopes).toEqual(['identity:read'])
      expect(Date.parse(data.credential.expires_at) - Date.parse(data.credential.created_at)).toBe(24 * 60 * 60 * 1000)
      const reveal = page.locator('#options-access-reveal')
      await expect(reveal).toBeVisible()
      await expect(reveal).not.toContainText(data.secret)
      await reveal.getByRole('button', { name: 'I saved it' }).click()
      await expect(reveal).toBeHidden()
      const statuses = await page.evaluate(async secret => {
        const headers = { Authorization: `Bearer ${secret}` }
        return [
          (await fetch('/api/v1/whoami', { headers })).status,
          (await fetch('/api/v1/projects', { headers })).status,
          (await fetch('/projects', { headers })).status,
        ]
      }, data.secret)
      expect(statuses).toEqual([200, 403, 403])
      const row = page.locator(`[data-credential-id="${data.credential.id}"]`)
      await expect(row).toContainText('CLI identity')
      await expect(row).toContainText('identity:read')
      await expect(page.locator('body')).not.toContainText(data.secret)
    })
  })

  test('keeps and manages workspace credentials without retaining revealed secrets', async ({ page }) => {
    test.setTimeout(90_000)
    await openAccess(page)

    const tabs = await page.locator('[data-options-tab]').evaluateAll(items => items.map(item => item.textContent.trim()))
    expect(tabs.slice(0, 2)).toEqual(['Preferences', 'Access'])
    await expect(page.locator('#options-access-summary')).toHaveText('Anonymous workspace')
    await expectAccessActions(page, 'anonymous')

    await page.locator('#options-access-keep-btn').click()
    await page.locator('#options-access-editor input[type="text"]').fill('Primary browser')
    await page.locator('#options-access-editor').getByRole('button', { name: 'Keep workspace' }).click()
    await saveCredentialReveal(page)

    const primaryRow = page.locator('.options-access-row', { hasText: 'Primary browser' })
    await expect(primaryRow).toContainText('Current')
    await expect(primaryRow).toContainText('Active')
    await expectAccessActions(page, 'kept')
    await expectCredentialSpacing(page)
    await expect(page.locator('#hud-session')).toContainText('crd_')

    await page.locator('#options-access-add-btn').click()
    await page.locator('#options-access-editor input[type="text"]').fill('Spare device')
    await page.locator('#options-access-editor').getByRole('button', { name: 'Save' }).click()
    await saveCredentialReveal(page)

    const spareRow = page.locator('.options-access-row', { hasText: 'Spare device' })
    await spareRow.getByRole('button', { name: 'Rename' }).click()
    await page.locator('#options-access-editor input[type="text"]').fill('Travel device')
    await page.locator('#options-access-editor').getByRole('button', { name: 'Save' }).click()
    const travelRow = page.locator('.options-access-row', { hasText: 'Travel device' })
    await expect(travelRow).toBeVisible()
    const travelCredentialId = await travelRow.getAttribute('data-credential-id')
    expect(travelCredentialId).toMatch(/^crd_[0-9a-f]{32}$/)

    await travelRow.getByRole('button', { name: 'Expiry' }).click()
    // Use the runner's current clock with ample margin for server and timezone differences.
    const futureExpiry = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString().slice(0, 16)
    await page.locator('#options-access-editor input[type="datetime-local"]').fill(futureExpiry)
    await page.locator('#options-access-editor').getByRole('button', { name: 'Save' }).click()
    await expect(travelRow).toContainText('Expires')

    await travelRow.getByRole('button', { name: 'Rotate' }).click()
    await expect(page.locator('#confirm-host')).toContainText('old credential stays active')
    await chooseConfirmAction(page, 'continue')
    const rotationReveal = page.locator('#options-access-reveal')
    await expect(rotationReveal).toBeVisible()
    await rotationReveal.getByRole('button', { name: 'Reveal' }).click()
    const replacementSecret = (await rotationReveal.locator('.options-access-reveal-value').textContent())?.trim() || ''
    expect(replacementSecret).toMatch(/^dlc_v1_crd_[0-9a-f]{32}_[A-Za-z0-9_-]{43}$/)
    await rotationReveal.getByRole('button', { name: 'I saved it' }).click()
    await expect(page.locator('#confirm-host')).toContainText('Revocation cannot be undone')
    await chooseConfirmAction(page, 'revoke')
    await expect(page.locator(`[data-credential-id="${travelCredentialId}"]`)).toContainText('Revoked')
    const replacementId = replacementSecret.match(/crd_[0-9a-f]{32}/)[0]
    const rotatedRow = page.locator(`[data-credential-id="${replacementId}"]`)
    await expect(rotatedRow).toContainText('Travel device')
    await expect(rotatedRow).toContainText('Active')

    await expect(page.locator('body')).not.toContainText(replacementSecret)
  })

  test('removes and restores a rotated credential across tabs without restarting Access', async ({ page }) => {
    test.setTimeout(90_000)
    // Creation and rotation have their own UI journey. Seed this journey through
    // the real API so its budget covers removal, restoration, and revocation.
    await keepBrowserWorkspace(page, { label: 'Primary browser' })
    const primarySecret = await page.evaluate(() => localStorage.getItem('access_credential'))
    const replacement = await page.evaluate(async () => {
      const options = { method: 'POST', headers: { 'Content-Type': 'application/json' } }
      const created = await apiFetch('/auth/credentials', {
        ...options, body: JSON.stringify({ label: 'Travel device' }),
      })
      if (created.status !== 201) throw new Error(`credential setup failed: ${created.status}`)
      const original = await created.json()
      const rotated = await apiFetch(`/auth/credentials/${original.credential.id}/rotate`, { ...options, body: '{}' })
      if (rotated.status !== 201) throw new Error(`rotation setup failed: ${rotated.status}`)
      return rotated.json()
    })
    const replacementSecret = replacement.secret
    const replacementId = replacement.credential.id
    await openAccess(page)
    const primaryRow = page.locator('.options-access-row', { hasText: 'Primary browser' })
    await expect(primaryRow).toContainText('Current')
    const peer = await page.context().newPage()
    try {
      await peer.goto('/', { waitUntil: 'domcontentloaded' })
      await ensurePromptReady(peer)
      await expect(peer.locator('#hud-session')).toContainText('crd_')
      await page.locator('#options-access-remove-btn').click()
      await chooseConfirmAction(page, 'remove')
      await expect(page.locator('#options-access-summary')).toHaveText('Anonymous workspace')
      await expectAccessActions(page, 'anonymous')
      await expect(page.locator('#hud-session')).toHaveText('ANON')
      await expect(peer.locator('#hud-session')).toHaveText('ANON')

      // Make the CI race deterministic: restoring preferences with Access saved
      // as the last tab must not restart its in-flight credential-list refresh.
      await page.route('**/session/preferences', async (route) => {
        if (route.request().method() !== 'GET') return route.continue()
        const response = await route.fetch()
        const data = await response.json()
        await route.fulfill({ response, json: {
          ...data,
          preferences: { ...data.preferences, pref_options_modal_last_tab: 'access', pref_prompt_username: 'restored-operator' },
        } })
      })
      let credentialReads = 0
      const countCredentialReads = request => {
        if (request.method() === 'GET' && new URL(request.url()).pathname === '/auth/credentials') credentialReads += 1
      }
      page.on('request', countCredentialReads)
      await page.locator('#options-access-use-btn').click()
      await page.locator('#options-access-redemption-input').fill(replacementSecret)
      await page.locator('#options-access-redemption-apply').click()
      await expect(page.locator('#options-prompt-username-input')).toHaveValue('restored-operator')
      await expect(page.locator('#options-access-summary')).toHaveText('Authenticated workspace')
      await expectAccessActions(page, 'kept')
      await expect(peer.locator('#hud-session')).toContainText('crd_')
      const replacementRow = page.locator(`[data-credential-id="${replacementId}"]`)
      await expect(replacementRow).toContainText('Current')
      // Identity change and successful redemption each request a refresh.
      expect(credentialReads).toBeLessThanOrEqual(2)
      page.off('request', countCredentialReads)
      await page.unroute('**/session/preferences')

      await replacementRow.getByRole('button', { name: 'Revoke' }).click()
      await expect(page.locator('#confirm-host')).toContainText('This credential is active in this browser')
      await chooseConfirmAction(page, 'revoke')
      await expect(page.locator('#options-access-summary')).toHaveText('Anonymous workspace')
      await expect(page.locator('body')).not.toContainText(replacementSecret)

      await page.locator('#options-access-use-btn').click()
      await page.locator('#options-access-redemption-input').fill(primarySecret)
      await page.locator('#options-access-redemption-apply').click()
      await expect(page.locator('#options-access-summary')).toHaveText('Authenticated workspace')

      await primaryRow.getByRole('button', { name: 'Revoke' }).click()
      await expect(page.locator('#confirm-host')).toContainText('last active access credential')
      await chooseConfirmAction(page, 'cancel')
      await expect(primaryRow).toContainText('Current')
    } finally {
      await peer.close()
    }
  })

  test('rejects invalid credentials from storage and the redemption form', async ({ page }) => {
    await openAccess(page)
    await page.evaluate(() => {
      localStorage.setItem('access_credential', 'not-a-valid-credential')
      window.dispatchEvent(new StorageEvent('storage', { key: 'access_credential', newValue: 'not-a-valid-credential' }))
    })
    await expect(page.locator('#options-access-summary')).toHaveText('Credential needs attention')
    await expectAccessActions(page, 'invalid')
    await page.locator('#options-access-discard-invalid-btn').click()
    await chooseConfirmAction(page, 'remove')
    await expect(page.locator('#options-access-summary')).toHaveText('Anonymous workspace')
    await expectAccessActions(page, 'anonymous')

    await page.locator('#options-access-use-btn').click()
    await expectRedemptionSpacing(page)
    await page.locator('#options-access-redemption-input').fill('not-a-credential')
    await page.locator('#options-access-redemption-apply').click()
    await expect(page.locator('#options-access-msg')).toHaveAttribute('role', 'alert')
    await expect(page.locator('#options-access-summary')).toHaveText('Anonymous workspace')
  })
})

test.describe('mobile workspace Access', () => {
  test.use({ viewport: { width: 375, height: 812 }, hasTouch: true, isMobile: true })

  test('keeps the focused credential visible as the keyboard viewport changes', async ({ page }) => {
    // Hold the lazy module until the test reaches the disabled control. This
    // reproduces a slow first load without depending on runner speed or sleeps.
    const accessModule = /\/static\/(?:js\/features\/preferences\/access_panel\.js|build\/static-access-panel\.[a-f0-9]+\.js)(?:\?|$)/
    let releaseModule
    let moduleRequested
    const pendingModule = new Promise(resolve => { releaseModule = resolve })
    const requestedModule = new Promise(resolve => { moduleRequested = resolve })
    await page.route(accessModule, async route => {
      moduleRequested()
      await pendingModule
      await route.continue()
    })
    try {
      await resetAnonymousBrowser(page)
      await page.locator('#hamburger-btn').click()
      await page.locator('#mobile-menu-sheet [data-menu-action="access"]').click()
      await requestedModule
      const useCredential = page.locator('#options-access-use-btn')
      await expect(useCredential).toBeDisabled()
      const opened = useCredential.click()
      releaseModule()
      await opened
      await expect(page.locator('#options-panel-access')).toHaveAttribute('data-access-panel-bound', '1')
    } finally {
      releaseModule()
      await page.unrouteAll({ behavior: 'wait' })
    }
    const input = page.locator('#options-access-redemption-input')
    await expect(input).toBeFocused()

    // Desktop emulation does not open an iOS keyboard. Shrink only the visual
    // viewport, leaving the layout viewport unchanged as iOS does.
    async function setVisualViewport(height, offsetTop) {
      await page.evaluate(({ height, offsetTop }) => {
        Object.defineProperties(window.visualViewport, {
          height: { configurable: true, value: height },
          offsetTop: { configurable: true, value: offsetTop },
        })
        window.visualViewport.dispatchEvent(new Event('resize'))
        window.visualViewport.dispatchEvent(new Event('scroll'))
      }, { height, offsetTop })
    }

    for (const [height, offsetTop] of [[360, 0], [300, 45]]) {
      await setVisualViewport(height, offsetTop)
      await expect.poll(() => input.evaluate((field) => {
        const rect = field.getBoundingClientRect()
        const body = field.closest('.options-body').getBoundingClientRect()
        const sheet = document.querySelector('#options-modal').getBoundingClientRect()
        const viewport = window.visualViewport
        return rect.top >= body.top && rect.bottom <= body.bottom
          && sheet.top >= viewport.offsetTop - 1
          && sheet.bottom <= viewport.offsetTop + viewport.height + 1
      })).toBe(true)
      await expect(input).toBeFocused()
      await expect.poll(() => page.evaluate(() =>
        document.elementFromPoint(5, 5)?.closest('#options-overlay')?.id)).toBe('options-overlay')
    }

    await page.locator('#options-access-redemption-apply').scrollIntoViewIfNeeded()
    await expect(page.locator('#options-access-redemption-apply')).toBeInViewport()
    await setVisualViewport(await page.evaluate(() => window.innerHeight), 0)
    await expect(page.locator('#options-overlay')).toHaveCSS('padding-bottom', '0px')
    await page.keyboard.press('Escape')
    await expect(page.locator('#options-overlay')).not.toHaveClass(/options-viewport-tracked/)
    await page.locator('#hamburger-btn').click()
    await page.locator('#mobile-menu-sheet [data-menu-action="access"]').click()
    await expect(page.locator('#options-overlay')).toHaveClass(/options-viewport-tracked/)
  })

  test('opens from the mobile identity summary and keeps actions touch-safe', async ({ page }) => {
    await resetAnonymousBrowser(page)
    await page.locator('#hamburger-btn').click()
    const accessItem = page.locator('#mobile-menu-sheet [data-menu-action="access"]')
    await expect(accessItem.locator('#mobile-menu-access-state')).toHaveText('Anonymous')
    await accessItem.click()

    const accessPanel = page.locator('#options-panel-access')
    await expect(accessPanel).toBeVisible()
    await expect(accessPanel).toHaveAttribute('data-access-panel-bound', '1')
    await expectAccessActions(page, 'anonymous')
    await page.locator('#options-access-use-btn').click()
    await expectRedemptionSpacing(page)
    const input = page.locator('#options-access-redemption-input')
    await expect(input).toHaveCSS('font-size', '16px')
    await input.fill('not-a-credential')
    await expect(input).toBeFocused()

    const layout = await page.locator('#options-panel-access').evaluate((panel) => ({
      panelRight: panel.getBoundingClientRect().right,
      viewportWidth: window.innerWidth,
      actionHeights: [...panel.querySelectorAll('.options-access-actions button, .options-access-row-actions button')]
        .filter(button => !button.hidden && button.getClientRects().length)
        .map(button => button.getBoundingClientRect().height),
    }))
    expect(layout.panelRight).toBeLessThanOrEqual(layout.viewportWidth + 1)
    expect(Math.min(...layout.actionHeights)).toBeGreaterThanOrEqual(40)

    await page.locator('#options-access-redemption-cancel').click()
    await expect(page.locator('#options-access-redemption')).toBeHidden()
    await expect(page.locator('#options-access-use-btn')).toBeFocused()

    await page.locator('#options-access-keep-btn').click()
    await page.locator('#options-access-editor input[type="text"]').fill('Phone')
    await page.locator('#options-access-editor').getByRole('button', { name: 'Keep workspace' }).click()
    await expect(page.locator('#options-access-reveal')).toBeVisible()
    await page.locator('#options-access-reveal').getByRole('button', { name: 'Close' }).click()
    await expect(page.locator('.options-access-row', { hasText: 'Phone' })).toContainText('Current')
    await expectAccessActions(page, 'kept')
    await expectCredentialSpacing(page)
  })
})
