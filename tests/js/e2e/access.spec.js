// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { test, expect } from '@playwright/test'
import { ensurePromptReady, openRailAction } from './helpers.js'

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
    await expect(page.locator('.options-access-row', { hasText: 'Travel device replacement' })).toContainText('Active')

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
    await expect(page.locator('#options-access-summary')).toHaveText('Kept workspace')
    await expectAccessActions(page, 'kept')
    await expect(peer.locator('#hud-session')).toContainText('crd_')
    const replacementRow = page.locator('.options-access-row', { hasText: 'Travel device replacement' })
    await expect(replacementRow).toContainText('Current')

    await replacementRow.getByRole('button', { name: 'Revoke' }).click()
    await expect(page.locator('#confirm-host')).toContainText('This credential is active in this browser')
    await chooseConfirmAction(page, 'revoke')
    await expect(page.locator('#options-access-summary')).toHaveText('Anonymous workspace')
    await expect(page.locator('body')).not.toContainText(replacementSecret)

    await page.locator('#options-access-use-btn').click()
    await page.locator('#options-access-redemption-input').fill(primarySecret)
    await page.locator('#options-access-redemption-apply').click()
    await expect(page.locator('#options-access-summary')).toHaveText('Kept workspace')

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
