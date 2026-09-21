// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

const mocks = vi.hoisted(() => ({
  identity: { kind: 'credential', credentialId: 'current', validFormat: true },
  config: { access_profile: 'open' },
  apiFetch: vi.fn(), clearAccessCredential: vi.fn(), redirectToSignIn: vi.fn(),
  showConfirm: vi.fn(), showToast: vi.fn(), focusElement: vi.fn(),
}))
vi.mock('../../../app/static/js/session.js', () => ({
  ...mocks, getBrowserIdentitySnapshot: () => ({ ...mocks.identity }),
}))
vi.mock('../../../app/static/js/core/config.js', () => ({ getAppConfig: () => mocks.config }))
vi.mock('../../../app/static/js/core/utils.js', () => ({ showToast: mocks.showToast }))
vi.mock('../../../app/static/js/ui/ui_confirm.js', () => ({ showConfirm: mocks.showConfirm }))
vi.mock('../../../app/static/js/ui/ui_helpers.js', () => ({ focusElement: mocks.focusElement }))

import { confirmBrowserLogOut, logOutCurrentBrowser } from '../../../app/static/js/features/preferences/browser_logout.js'

beforeEach(() => {
  vi.resetAllMocks()
  mocks.identity = { kind: 'credential', credentialId: 'current', validFormat: true }
  mocks.config = { access_profile: 'open' }
  mocks.showConfirm.mockResolvedValue('logout')
  mocks.apiFetch.mockResolvedValue({ ok: true, status: 204 })
})

it('removes only local credential access and confirms that the workspace is saved', async () => {
  await confirmBrowserLogOut()
  expect(mocks.clearAccessCredential).toHaveBeenCalledOnce()
  expect(mocks.apiFetch).not.toHaveBeenCalled()
  expect(mocks.redirectToSignIn).not.toHaveBeenCalled()
  expect(mocks.showConfirm.mock.calls[0][0].body).toContain('Keep your access credential')
  expect(mocks.showToast).toHaveBeenCalledWith('Logged out of this browser')
})

it('ends a managed session before redirecting and keeps provider logout separate', async () => {
  mocks.identity.kind = 'browser_session'
  mocks.config.access_profile = 'mixed'
  await confirmBrowserLogOut()
  expect(mocks.showConfirm.mock.calls[0][0].body).toContain('identity provider, it stays signed in')
  expect(mocks.apiFetch).toHaveBeenCalledExactlyOnceWith('/auth/logout', { method: 'POST', cache: 'no-store' })
  expect(mocks.redirectToSignIn).toHaveBeenCalledOnce()
  expect(mocks.clearAccessCredential).toHaveBeenCalledWith({ freshAnonymous: false })
})

it.each(['network', 'server'])('keeps failed %s logout retryable without exposing error details', async failure => {
  mocks.identity.kind = 'browser_session'
  if (failure === 'network') mocks.apiFetch.mockRejectedValueOnce(new Error('private failure canary'))
  else mocks.apiFetch.mockResolvedValueOnce({ ok: false, status: 503 })
  await confirmBrowserLogOut()
  expect(mocks.redirectToSignIn).not.toHaveBeenCalled()
  expect(mocks.showToast).toHaveBeenCalledExactlyOnceWith('Could not log out. Try again.')
  await confirmBrowserLogOut()
  expect(mocks.redirectToSignIn).toHaveBeenCalledOnce()
})

it('restores focus after cancellation without changing access', async () => {
  mocks.showConfirm.mockResolvedValue(null)
  const trigger = document.createElement('button')
  await confirmBrowserLogOut(trigger)
  expect(mocks.focusElement).toHaveBeenCalledWith(trigger, { preventScroll: true })
  expect(mocks.clearAccessCredential).not.toHaveBeenCalled()
  expect(mocks.apiFetch).not.toHaveBeenCalled()
})

it('ignores repeated activation until the current logout completes', async () => {
  mocks.identity.kind = 'browser_session'
  let finish
  mocks.apiFetch.mockImplementation(() => new Promise(resolve => { finish = resolve }))
  const first = confirmBrowserLogOut()
  await vi.waitFor(() => expect(mocks.apiFetch).toHaveBeenCalledOnce())
  await confirmBrowserLogOut()
  expect(mocks.showConfirm).toHaveBeenCalledOnce()
  finish({ ok: true })
  await first
  expect(mocks.redirectToSignIn).toHaveBeenCalledOnce()
})

it('leaves a changed identity alone while confirmation is open', async () => {
  mocks.showConfirm.mockImplementation(async () => {
    mocks.identity.credentialId = 'another-credential'
    return 'logout'
  })
  await confirmBrowserLogOut()
  expect(mocks.clearAccessCredential).not.toHaveBeenCalled()
  expect(mocks.apiFetch).not.toHaveBeenCalled()
  expect(mocks.showToast).toHaveBeenCalledWith('Your access changed. Open Log out again.')
})

it('leaves anonymous workspaces alone', async () => {
  mocks.identity.kind = 'anonymous'
  await confirmBrowserLogOut()
  await logOutCurrentBrowser()
  expect(mocks.showConfirm).not.toHaveBeenCalled()
  expect(mocks.clearAccessCredential).not.toHaveBeenCalled()
  expect(mocks.apiFetch).not.toHaveBeenCalled()
})
