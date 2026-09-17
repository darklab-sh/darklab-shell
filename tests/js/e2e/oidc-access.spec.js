// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { readFileSync } from 'fs'
import { resolve } from 'path'

import { test, expect } from '@playwright/test'

import { ensurePromptReady, openRailAction } from './helpers.js'


function operatorCredential() {
  const directory = process.env.PW_E2E_SECRET_DIR
  if (!directory) throw new Error('PW_E2E_SECRET_DIR is not set')
  return readFileSync(resolve(directory, 'oidc.credential'), 'utf8').trim()
}


async function openAccess(page) {
  await openRailAction(page, 'options')
  await page.locator('#options-tab-access').click()
  await expect(page.locator('#options-access-oidc-section')).toBeVisible()
}


async function resetOperatorProviderLink(request) {
  // A timed-out attempt can leave the shared operator linked. Reset it through
  // a separate cookie jar before the browser starts its sign-in journey.
  const redeemed = await request.post('/auth/credentials/redeem', { data: { secret: operatorCredential() } })
  expect(redeemed.status()).toBe(200)
  const csrf = (await request.storageState()).cookies.find(cookie => cookie.name === 'darklab_csrf')
  expect(csrf).toBeTruthy()
  const headers = { 'X-Darklab-CSRF': csrf.value }
  const unlinked = await request.post('/auth/oidc/unlink', { headers })
  expect(unlinked.status()).toBe(200)
  if (!(await unlinked.json()).unlinked) {
    expect((await request.post('/auth/logout', { headers })).status()).toBe(204)
  }
}


test.describe('managed sign-in with a local HTTPS provider', () => {
  test('keeps provider load failures visible and recovers with Refresh', async ({ page }) => {
    // Four failure/recovery cycles each refresh the full Access panel.
    test.setTimeout(60_000)
    await page.goto('/')
    await page.getByLabel('Access credential').fill(operatorCredential())
    await Promise.all([
      page.waitForURL(url => url.pathname === '/'),
      page.getByRole('button', { name: 'Sign in', exact: true }).click(),
    ])
    await ensurePromptReady(page)
    await openAccess(page)
    await expect(page.locator('#options-access-oidc-link')).toBeVisible()
    const diagnostics = []
    page.on('request', request => {
      if (new URL(request.url()).pathname !== '/log' || request.method() !== 'POST') return
      const body = request.postDataJSON()
      if (body?.event === 'ACCESS_OIDC_IDENTITY_LOAD_FAILED') diagnostics.push(body)
    })
    let outcome = 'server'
    await page.route('**/auth/oidc/identity', route => {
      if (outcome === 'network') return route.abort('failed')
      if (outcome === 'json') return route.fulfill({ status: 200, contentType: 'text/html', body: 'private-provider-response' })
      if (outcome === 'shape') return route.fulfill({ json: { issuer: 'https://private.example', subject: 'private-user' } })
      if (outcome === 'disabled') return route.fulfill({ status: 404, json: { error: 'oidc_disabled' } })
      if (outcome === 'server') return route.fulfill({ status: 503, json: { error: 'private-provider-response' } })
      return route.continue()
    })
    const refresh = page.locator('#options-access-refresh-btn')
    const status = page.locator('#options-access-oidc-status')
    for (const [kind, level, stage, code, reason] of [
      ['server', 'error', 'response', 503, 'server_failed'],
      ['json', 'error', 'parse', 200, 'invalid_json'],
      ['shape', 'error', 'response', 200, 'invalid_payload'],
      ['network', 'warning', 'request', 0, 'network_unavailable'],
    ]) {
      outcome = kind
      if (kind === 'network') await page.setViewportSize({ width: 390, height: 844 })
      const delivery = page.waitForResponse(response => new URL(response.url()).pathname === '/log'
        && response.request().postDataJSON()?.event === 'ACCESS_OIDC_IDENTITY_LOAD_FAILED')
      await refresh.click()
      await expect(status).toHaveText("Provider sign-in details couldn't be loaded. Select Refresh to try again.")
      await expect(page.locator('#options-access-oidc-link')).toBeHidden()
      await expect(page.locator('#options-access-oidc-unlink')).toBeHidden()
      await expect(page.locator('#options-access-credentials-section')).toBeVisible()
      expect((await delivery).ok()).toBe(true)
      expect(diagnostics.at(-1)).toEqual({
        context: 'ACCESS_OIDC_IDENTITY_LOAD_FAILED', message: '', event: 'ACCESS_OIDC_IDENTITY_LOAD_FAILED', level,
        details: { event: 'ACCESS_OIDC_IDENTITY_LOAD_FAILED', level, action: 'load_identity', stage, status: code, reason },
      })
      expect(JSON.stringify(diagnostics)).not.toContain('private')
      outcome = 'success'
      await refresh.click()
      await expect(page.locator('#options-access-oidc-link')).toBeVisible()
      await expect(page.locator('#options-access-msg')).toHaveText('Access is up to date.')
    }
    outcome = 'disabled'
    await refresh.click()
    await expect(page.locator('#options-access-oidc-section')).toBeHidden()
    await expect(page.locator('#options-access-msg')).toHaveText('Access is up to date.')
    expect(diagnostics).toHaveLength(4)
  })

  test('links after both proofs, unlinks with revocation, then signs in through the provider', async ({ page, context, request }) => {
    // Credential sign-in, reauthentication, linking, and provider sign-in each load the app.
    test.setTimeout(90_000)
    await resetOperatorProviderLink(request)
    await page.goto('/')
    await expect(page).toHaveURL(/\/auth\/sign-in\?next=/)
    const providerGap = await page.locator('.restricted-sign-in-card').evaluate(card => {
      const details = card.querySelector('p')
      const provider = card.querySelector('.restricted-sign-in-provider')
      return provider.getBoundingClientRect().top - details.getBoundingClientRect().bottom
    })
    expect(providerGap).toBeGreaterThanOrEqual(16)
    await page.getByLabel('Access credential').fill(operatorCredential())
    await Promise.all([
      page.waitForURL(url => url.pathname === '/'),
      page.getByRole('button', { name: 'Sign in', exact: true }).click(),
    ])
    await ensurePromptReady(page)
    const original = await page.evaluate(async () => (await (await apiFetch('/auth/principal')).json()).principal.id)

    // Simulate an older principal response; Python request tests cover the real
    // clock boundary. The rest of this journey uses real credential sign-in.
    await page.route('**/auth/principal', async route => {
      const response = await route.fetch()
      const data = await response.json()
      data.authentication.recent_credential_session = false
      await route.fulfill({ response, json: data })
    })
    await openAccess(page)
    await expect(page.locator('#options-access-oidc-link')).toBeHidden()
    await page.locator('#options-access-oidc-reauth').click()
    await expect(page).toHaveURL(/force=credential/)
    await expect(page.getByRole('link', { name: 'Continue with identity provider' })).toHaveCount(0)
    await page.unroute('**/auth/principal')
    await page.getByLabel('Access credential').fill(operatorCredential())
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()
    await expect(page.locator('#options-panel-access')).toBeVisible()
    await expect(page.locator('#options-tab-access')).toHaveAttribute('aria-selected', 'true')
    await expect(page).toHaveURL(url => url.pathname === '/' && !url.searchParams.has('options'))
    await expect(page.locator('#options-access-oidc-link')).toBeVisible()
    const [callback] = await Promise.all([
      page.waitForResponse(response => new URL(response.url()).pathname === '/auth/oidc/callback'),
      page.waitForEvent('domcontentloaded'),
      page.locator('#options-access-oidc-link').click(),
    ])
    expect(new URL(callback.headers().location, callback.url()).pathname).toBe('/')
    await expect(page).toHaveURL(url => url.pathname === '/')
    await ensurePromptReady(page)
    await expect.poll(async () => {
      const response = await page.request.get('/auth/oidc/identity')
      return response.ok() && (await response.json()).linked
    }).toBe(true)
    await expect(page.locator('#options-panel-access')).toBeVisible()
    await expect(page.locator('#options-access-oidc-unlink')).toBeVisible()
    await page.locator('#options-access-oidc-unlink').click()
    await page.locator('#confirm-host [data-confirm-action-id="unlink"]').click()
    await expect(page).toHaveURL(/\/auth\/sign-in/)

    await page.getByRole('link', { name: 'Continue with identity provider' }).click()
    await page.waitForURL(url => url.pathname === '/')
    await ensurePromptReady(page)
    const authentication = await page.evaluate(async () => (await (await apiFetch('/auth/principal')).json()).authentication)
    expect(authentication.credential_type).toBe('oidc')
    expect(authentication.credential_id).toBe('')
    await expect(page.locator('#hud-session')).toHaveText('OIDC')
    await openAccess(page)
    await expect(page.locator('#options-access-summary')).toHaveText('Authenticated workspace')
    expect(await page.evaluate(() => document.cookie)).not.toContain('darklab_browser_session=')
    const cookie = (await context.cookies()).find(item => item.name === 'darklab_browser_session')
    expect(cookie).toEqual(expect.objectContaining({ httpOnly: true, secure: true, sameSite: 'Strict' }))
    const providerPrincipal = await page.evaluate(async () => (await (await apiFetch('/auth/principal')).json()).principal.id)
    expect(providerPrincipal).not.toBe(original)
  })

  test('shows a safe error when the provider declines authorization', async ({ page }) => {
    let intercepted = 0
    await page.route(url => url.pathname === '/auth/oidc/start', async route => {
      intercepted += 1
      const response = await route.fetch({ maxRedirects: 0 })
      const state = new URL(response.headers().location).searchParams.get('state')
      const redirect = new URL('/auth/oidc/callback', route.request().url())
      redirect.searchParams.set('state', state)
      redirect.searchParams.set('error', 'access_denied')
      return route.fulfill({ response, status: 302, headers: { ...response.headers(), location: redirect.href } })
    })
    await page.goto('/')
    await page.getByRole('link', { name: 'Continue with identity provider' }).click()
    expect(intercepted).toBe(1)
    await expect(page.getByRole('alert')).toContainText("Provider sign-in couldn't be completed")
    await expect(page).toHaveURL(/\/auth\/sign-in\?oidc_error=1/)
  })
})
