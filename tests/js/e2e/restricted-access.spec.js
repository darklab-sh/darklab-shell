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

  test('retries a failed rail logout and leaves another browser signed in', async ({ page, browser, context, request }) => {
    // Three complete sign-ins share this budget, including the peer browser.
    test.setTimeout(60_000)
    await openSignIn(page)
    await signIn(page)
    const peerContext = await browser.newContext({ baseURL: new URL(page.url()).origin })
    const peer = await peerContext.newPage()
    try {
      await openSignIn(peer)
      await signIn(peer)
      const session = (await context.cookies()).find(cookie => cookie.name === 'darklab_browser_session')
      expect(session).toBeTruthy()
      await page.route('**/auth/logout', route => route.fulfill({ status: 503 }), { times: 1 })
      await openRailAction(page, 'logout')
      await page.locator('#confirm-host').getByRole('button', { name: 'Log out', exact: true }).click()
      await expect(page.locator('#permalink-toast')).toHaveText('Could not log out. Try again.')
      await expect(page.locator('#rail-more-btn')).toBeFocused()
      expect(await page.evaluate(async () => (await apiFetch('/projects')).status)).toBe(200)
      await openRailAction(page, 'logout')
      await page.locator('#confirm-host').getByRole('button', { name: 'Log out', exact: true }).click()
      await expect(page).toHaveURL(/\/auth\/sign-in\?next=/)
      expect((await context.cookies()).some(cookie => cookie.name === 'darklab_browser_session')).toBe(false)
      const replay = await request.get(new URL('/projects', page.url()).href, {
        headers: { Cookie: `darklab_browser_session=${session.value}` },
      })
      expect(replay.status()).toBe(401)
      expect(await peer.evaluate(async () => (await apiFetch('/projects')).status)).toBe(200)
      await signIn(page)
      expect(await page.evaluate(async () => (await apiFetch('/projects')).status)).toBe(200)
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

  test('returns a revoked open tab to sign-in and clears stale cookies on logout', async ({ page, context, request }) => {
    await openSignIn(page)
    await signIn(page)
    const cookies = await context.cookies()
    const session = cookies.find(cookie => cookie.name === 'darklab_browser_session')
    const csrf = cookies.find(cookie => cookie.name === 'darklab_csrf')
    expect(session).toBeTruthy()
    expect(csrf).toBeTruthy()
    const origin = new URL(page.url()).origin
    let revocationStatus
    // Start a protected read while the app is still mounted. Revoke through an
    // independent cookie jar before that request reaches the application.
    await page.route('**/projects', async route => {
      const revoked = await request.post(`${origin}/auth/sessions/revoke-all`, {
        ignoreHTTPSErrors: true,
        headers: {
          Cookie: `darklab_browser_session=${session.value}; darklab_csrf=${csrf.value}`,
          'X-Darklab-CSRF': csrf.value,
        },
      })
      revocationStatus = revoked.status()
      await route.continue()
    }, { times: 1 })
    // A background protected request may observe revocation before Projects.
    const denied = page.waitForResponse(response => new URL(response.url()).origin === origin && response.status() === 401)
    await page.evaluate(() => { void apiFetch('/projects').catch(() => {}) })
    await expect.poll(() => revocationStatus).toBe(200)
    expect((await denied).status()).toBe(401)
    await expect(page).toHaveURL(/\/auth\/sign-in\?next=/)
    await expect(page.getByLabel('Access credential')).toBeVisible()
    await context.addCookies([session, csrf])
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
