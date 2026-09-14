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

  test('keeps, manages, removes, and restores a workspace without retaining revealed secrets', async ({ page }) => {
    test.setTimeout(90_000)
    await openAccess(page)

    const tabs = await page.locator('[data-options-tab]').evaluateAll(items => items.map(item => item.textContent.trim()))
    expect(tabs.slice(0, 2)).toEqual(['Preferences', 'Access'])
    await expect(page.locator('#options-access-summary')).toHaveText('Anonymous workspace')
    await expectAccessActions(page, 'anonymous')

    await page.locator('#options-access-keep-btn').click()
    await page.locator('#options-access-editor input[type="text"]').fill('Primary browser')
    await page.locator('#options-access-editor').getByRole('button', { name: 'Keep workspace' }).click()
    const primarySecret = await saveCredentialReveal(page)

    const primaryRow = page.locator('.options-access-row', { hasText: 'Primary browser' })
    await expect(primaryRow).toContainText('Current')
    await expect(primaryRow).toContainText('Active')
    await expectAccessActions(page, 'kept')
    await expectCredentialSpacing(page)
    await expect(page.locator('#hud-session')).toContainText('crd_')

    const peer = await page.context().newPage()
    await peer.goto('/', { waitUntil: 'domcontentloaded' })
    await ensurePromptReady(peer)
    await expect(peer.locator('#hud-session')).toContainText('crd_')

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
    await page.locator('#options-access-editor input[type="datetime-local"]').fill('2027-01-15T12:00')
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

    await page.locator('#options-access-remove-btn').click()
    await chooseConfirmAction(page, 'remove')
    await expect(page.locator('#options-access-summary')).toHaveText('Anonymous workspace')
    await expectAccessActions(page, 'anonymous')
    await expect(page.locator('#hud-session')).toHaveText('ANON')
    await expect(peer.locator('#hud-session')).toHaveText('ANON')

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

    await page.locator('#options-access-use-btn').click()
    await page.locator('#options-access-redemption-input').fill(replacementSecret)
    await page.locator('#options-access-redemption-apply').click()
    await expect(page.locator('#options-access-summary')).toHaveText('Authenticated workspace')
    await expectAccessActions(page, 'kept')
    await expect(peer.locator('#hud-session')).toContainText('crd_')
    const replacementRow = page.locator(`[data-credential-id="${replacementId}"]`)
    await expect(replacementRow).toContainText('Current')

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
    await peer.close()
  })
})

test.describe('mobile workspace Access', () => {
  test.use({ viewport: { width: 375, height: 812 }, hasTouch: true, isMobile: true })

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
