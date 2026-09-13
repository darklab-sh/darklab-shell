// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { readFileSync } from 'fs'
import { resolve } from 'path'

import { test, expect } from '@playwright/test'

import { ensurePromptReady, openRailAction } from './helpers.js'


function restrictedCredential() {
  const directory = process.env.PW_E2E_SECRET_DIR
  if (!directory) throw new Error('PW_E2E_SECRET_DIR is not set')
  return readFileSync(resolve(directory, 'restricted.credential'), 'utf8').trim()
}


async function openSignIn(page) {
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await expect(page).toHaveURL(/\/auth\/sign-in\?next=/)
  await expect(page.getByRole('heading', { name: /Sign in to/ })).toBeVisible()
}


async function signIn(page) {
  await page.getByLabel('Access credential').fill(restrictedCredential())
  await Promise.all([
    page.waitForURL(url => url.pathname === '/'),
    page.getByRole('button', { name: 'Sign in' }).click(),
  ])
  await ensurePromptReady(page)
}


test.describe('restricted access profile', () => {
  test('redeems once into an HttpOnly session, protects mutations, and signs out', async ({ page, context }) => {
    await openSignIn(page)
    await page.evaluate(() => {
      localStorage.setItem('access_credential', 'legacy-script-readable-value')
      localStorage.setItem('anonymous_id', 'legacy-anonymous-value')
    })
    await signIn(page)

    const principal = await page.evaluate(async () => (await (await apiFetch('/auth/principal')).json()).authentication)
    expect(principal.credential_id).toMatch(/^crd_[0-9a-f]{32}$/)
    await expect(page.locator('#hud-session')).toHaveText(`${principal.credential_id.slice(0, 12)}••••`)
    await expect(page.locator('#hud-session')).toHaveClass(/\bhud-value-green\b/)
    await expect(page.locator('#mobile-menu-access-state')).toHaveText('Kept')

    const localIdentity = await page.evaluate(() => ({
      credential: localStorage.getItem('access_credential'),
      anonymous: localStorage.getItem('anonymous_id'),
      visibleCookies: document.cookie,
    }))
    expect(localIdentity.credential).toBeNull()
    expect(localIdentity.anonymous).toBeNull()
    expect(localIdentity.visibleCookies).not.toContain('darklab_browser_session=')
    expect(localIdentity.visibleCookies).toContain('darklab_csrf=')

    const sessionCookie = (await context.cookies()).find(cookie => cookie.name === 'darklab_browser_session')
    expect(sessionCookie).toEqual(expect.objectContaining({
      httpOnly: true,
      secure: true,
      sameSite: 'Strict',
    }))

    const statuses = await page.evaluate(async () => {
      const protectedResponse = await fetch('/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: 'Missing CSRF' }),
      })
      const allowedResponse = await apiFetch('/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: 'Restricted browser project' }),
      })
      return { protected: protectedResponse.status, allowed: allowedResponse.status }
    })
    expect(statuses).toEqual({ protected: 403, allowed: 201 })

    await openRailAction(page, 'options')
    await page.locator('#options-tab-access').click()
    await expect(page.locator('#options-access-summary')).toHaveText('Authenticated workspace')
    await expect(page.locator('.options-access-row')).toContainText('Current')

    const logoutStatus = await page.evaluate(async () => (await apiFetch('/auth/logout', {
      method: 'POST',
    })).status)
    expect(logoutStatus).toBe(204)
    await openSignIn(page)
  })

  test('keeps invalid credentials off the page and supports session-wide revocation', async ({ page }) => {
    await openSignIn(page)
    await page.getByLabel('Access credential').fill('not-a-credential')
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page.getByRole('alert')).toContainText("isn't valid")
    await expect(page.getByLabel('Access credential')).toHaveValue('')

    await signIn(page)
    const status = await page.evaluate(async () => (await apiFetch('/auth/sessions/revoke-all', {
      method: 'POST',
    })).status)
    expect(status).toBe(200)
    await openSignIn(page)
  })

  test.describe('mobile sign-in', () => {
    test.use({ viewport: { width: 375, height: 812 }, hasTouch: true, isMobile: true })

    test('keeps the credential form readable and touch-safe', async ({ page }) => {
      await openSignIn(page)
      const layout = await page.locator('.restricted-sign-in-card').evaluate(card => ({
        left: card.getBoundingClientRect().left,
        right: card.getBoundingClientRect().right,
        width: window.innerWidth,
        buttonHeight: card.querySelector('button').getBoundingClientRect().height,
      }))
      expect(layout.left).toBeGreaterThanOrEqual(0)
      expect(layout.right).toBeLessThanOrEqual(layout.width)
      expect(layout.buttonHeight).toBeGreaterThanOrEqual(40)
    })
  })
})
