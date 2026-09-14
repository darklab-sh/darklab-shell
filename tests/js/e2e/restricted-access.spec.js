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

    const logoutResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/auth/logout')
    await page.getByRole('button', { name: 'Sign out', exact: true }).click()
    await expect(page.locator('#confirm-host')).toContainText('Your workspace stays saved')
    await page.locator('#confirm-host [data-confirm-action-id="remove"]').click()
    expect((await logoutResponse).status()).toBe(204)
    await expect(page).toHaveURL(/\/auth\/sign-in\?next=/)
  })

  test('keeps invalid credentials off the page and signs out every browser through Access', async ({ page, browser }) => {
    await openSignIn(page)
    await page.getByLabel('Access credential').fill('not-a-credential')
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page.getByRole('alert')).toContainText("isn't valid")
    await expect(page.getByLabel('Access credential')).toHaveValue('')

    await signIn(page)
    const peerContext = await browser.newContext({ baseURL: new URL(page.url()).origin })
    const peer = await peerContext.newPage()
    try {
      await openSignIn(peer)
      await signIn(peer)
      await openRailAction(page, 'options')
      await page.locator('#options-tab-access').click()
      const revoked = page.waitForResponse(response => new URL(response.url()).pathname === '/auth/sessions/revoke-all')
      await page.getByRole('button', { name: 'Sign out everywhere', exact: true }).click()
      await page.locator('#confirm-host [data-confirm-action-id="sign-out-all"]').click()
      expect((await revoked).status()).toBe(200)
      await expect(page).toHaveURL(/\/auth\/sign-in\?next=/)
      // Raw fetch observes the other browser's denial without navigating it.
      expect(await peer.evaluate(async () => (await fetch('/projects')).status)).toBe(401)
    } finally {
      await peerContext.close()
    }
  })

  for (const width of [1280, 375]) test.describe(`private sharing at ${width}px`, () => {
    test.use({ viewport: { width, height: 900 }, hasTouch: width < 600, isMobile: width < 600 })
    test('disables public snapshot controls and explains keyboard denial', async ({ page }) => {
      await openSignIn(page)
      await signIn(page)
      const selector = width < 600
        ? '.tab-panel.active .terminal-actions [data-action="permalink"]'
        : '.hud-actions [data-action="permalink"]'
      const button = page.locator(selector)
      await expect(button).toBeVisible()
      await expect(button).toBeDisabled()
      await expect(button).toHaveAttribute('title', 'Public share links are disabled for this deployment.')
      const requests = []
      page.on('request', request => {
        if (new URL(request.url()).pathname === '/share' && request.method() === 'POST') requests.push(request)
      })
      await page.keyboard.press('Alt+Shift+p')
      await expect(page.locator('#permalink-toast')).toContainText('Public share links are disabled for this deployment.')
      expect(requests).toEqual([])
    })
  })

  test('returns a revoked open tab to sign-in and clears stale cookies on logout', async ({ page, context }) => {
    await openSignIn(page)
    await signIn(page)
    const cookies = await context.cookies()
    const session = cookies.find(cookie => cookie.name === 'darklab_browser_session')
    const csrf = cookies.find(cookie => cookie.name === 'darklab_csrf')
    const revoked = await page.evaluate(async () => (await apiFetch('/auth/sessions/revoke-all', { method: 'POST' })).status)
    expect(revoked).toBe(200)
    await context.addCookies([session, csrf])

    // The still-open app meets a real revoked-session response, with no reload.
    const denied = page.waitForResponse(response => new URL(response.url()).pathname === '/projects' && response.status() === 401)
    await openRailAction(page, 'projects')
    expect((await denied).status()).toBe(401)
    await expect(page).toHaveURL(/\/auth\/sign-in\?next=/)
    await expect(page.getByLabel('Access credential')).toBeVisible()
    const logout = await page.evaluate(async () => (await fetch('/auth/logout', { method: 'POST' })).status)
    expect(logout).toBe(204)
    expect((await context.cookies()).filter(cookie => ['darklab_browser_session', 'darklab_csrf'].includes(cookie.name))).toEqual([])
    await signIn(page)
    expect(await page.evaluate(async () => (await apiFetch('/projects')).status)).toBe(200)
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
