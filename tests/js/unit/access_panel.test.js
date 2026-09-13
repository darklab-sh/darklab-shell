// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

vi.mock('../../../app/static/js/session.js', () => ({
  activateAccessCredential: vi.fn((secret) => {
    const id = String(secret).match(/(crd_[0-9a-f]{32})/)?.[1] || ''
    globalThis.__accessPanelTest.identity = {
      kind: 'credential', anonymousId: '', credentialId: id, validFormat: true,
    }
  }),
  redirectToSignIn: vi.fn(),
  apiFetch: (...args) => globalThis.__accessPanelTest.apiFetch(...args),
  clearAccessCredential: vi.fn(() => {
    globalThis.__accessPanelTest.identity = {
      kind: 'anonymous', anonymousId: '00000000-0000-4000-8000-000000000001', credentialId: '', validFormat: true,
    }
  }),
  getBrowserIdentitySnapshot: () => globalThis.__accessPanelTest.identity,
}))

vi.mock('../../../app/static/js/ui/ui_confirm.js', () => ({
  showConfirm: (...args) => globalThis.__accessPanelTest.showConfirm(...args),
}))

vi.mock('../../../app/static/js/core/utils.js', () => ({
  copyTextToClipboard: (...args) => globalThis.__accessPanelTest.copy(...args),
  showToast: (...args) => globalThis.__accessPanelTest.toast(...args),
}))

vi.mock('../../../app/static/js/ui/ui_helpers.js', () => ({
  applyMobileTextInputDefaults: vi.fn(),
}))

vi.mock('../../../app/static/js/core/config.js', () => ({
  getAppConfig: () => globalThis.__accessPanelTest.appConfig || {},
}))

const SECRET = `dlc_v1_crd_${'a'.repeat(32)}_${'b'.repeat(43)}`
const CURRENT_ID = `crd_${'a'.repeat(32)}`
const REPLACEMENT_SECRET = `dlc_v1_crd_${'c'.repeat(32)}_${'d'.repeat(43)}`

function response(payload, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(payload),
  })
}

function credential(overrides = {}) {
  return {
    id: CURRENT_ID,
    public_prefix: CURRENT_ID.slice(0, 12),
    credential_type: 'portable',
    label: 'This browser',
    created_at: '2026-09-10T12:00:00Z',
    last_used_at: '2026-09-10T12:05:00Z',
    expires_at: null,
    revoked_at: null,
    revocation_reason: '',
    scopes: [],
    ...overrides,
  }
}

function renderMarkup() {
  document.body.innerHTML = `
    <div id="options-panel-access" data-options-panel="access" aria-busy="true">
      <div id="options-access-summary"></div>
      <div id="options-access-summary-detail"></div>
      <div id="options-access-msg"></div>
      <div id="options-access-affected-work" hidden></div>
      <div id="options-access-anonymous-actions">
        <button id="options-access-keep-btn" disabled></button>
        <button id="options-access-use-btn" disabled></button>
        <button id="options-access-discard-invalid-btn" disabled hidden></button>
      </div>
      <div id="options-access-authenticated-actions" hidden>
        <button id="options-access-add-btn" disabled></button>
        <button id="options-access-remove-btn" disabled></button>
        <button id="options-access-remove-all-btn" disabled hidden></button>
        <a id="options-access-session-reauth" href="/auth/sign-in?next=%2F%3Foptions%3Daccess" hidden>Sign in again</a>
      </div>
      <button id="options-access-refresh-btn" disabled></button>
      <div id="options-access-credentials-section" hidden>
        <div id="options-access-credentials"></div>
      </div>
      <div id="options-access-editor" hidden></div>
      <div id="options-access-redemption" hidden>
        <input id="options-access-redemption-input">
        <button id="options-access-redemption-apply"></button>
        <button id="options-access-redemption-cancel"></button>
      </div>
      <div id="options-access-reveal" hidden></div>
      <div id="options-access-oidc-section" hidden>
        <div id="options-access-oidc-status"></div>
        <button id="options-access-oidc-link" hidden></button>
        <button id="options-access-oidc-unlink" hidden></button>
        <a id="options-access-oidc-reauth" href="/auth/sign-in?force=credential&amp;next=%2F%3Foptions%3Daccess" hidden></a>
      </div>
    </div>
  `
}

describe('Access panel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.resetModules()
    renderMarkup()
    globalThis.__accessPanelTest = {
      identity: {
        kind: 'anonymous', anonymousId: '00000000-0000-4000-8000-000000000001', credentialId: '', validFormat: true,
      },
      apiFetch: vi.fn(),
      showConfirm: vi.fn().mockResolvedValue('cancel'),
      copy: vi.fn().mockResolvedValue(undefined),
      toast: vi.fn(),
      appConfig: {},
    }
  })

  afterEach(() => {
    delete globalThis.__accessPanelTest
  })

  it('keeps an anonymous workspace and removes the one-time secret from the DOM on close', async () => {
    globalThis.__accessPanelTest.apiFetch.mockImplementation((url) => {
      if (url === '/auth/principals') return response({ secret: SECRET })
      if (url === '/auth/principal') return response({ authentication: { credential_id: CURRENT_ID } })
      if (url === '/auth/credentials') return response({ credentials: [credential()] })
      return response({})
    })
    await import('../../../app/static/js/features/preferences/access_panel.js')

    expect(document.getElementById('options-panel-access').dataset.accessPanelBound).toBe('1')
    expect(document.getElementById('options-panel-access').hasAttribute('aria-busy')).toBe(false)
    expect(document.getElementById('options-access-use-btn').disabled).toBe(false)

    document.getElementById('options-access-keep-btn').click()
    document.querySelector('#options-access-editor .btn-primary').click()

    await vi.waitFor(() => expect(document.getElementById('options-access-reveal').hidden).toBe(false))
    const reveal = document.getElementById('options-access-reveal')
    expect(reveal.textContent).not.toContain(SECRET)
    ;[...reveal.querySelectorAll('button')].find(button => button.textContent === 'Copy').click()
    await vi.waitFor(() => expect(globalThis.__accessPanelTest.copy).toHaveBeenCalledWith(SECRET))
    ;[...reveal.querySelectorAll('button')].find(button => button.textContent === 'Reveal').click()
    expect(reveal.textContent).toContain(SECRET)
    ;[...reveal.querySelectorAll('button')].find(button => button.textContent === 'Close').click()
    expect(reveal.hidden).toBe(true)
    expect(reveal.textContent).not.toContain(SECRET)
    expect(document.body.innerHTML).not.toContain(SECRET)
  })

  it('does not switch identity when credential redemption fails', async () => {
    globalThis.__accessPanelTest.apiFetch.mockImplementation((url) => (
      url === '/auth/credentials/redeem'
        ? response({ error: 'unknown_credential', message: 'Credential was not accepted' }, 401)
        : response({})
    ))
    const session = await import('../../../app/static/js/session.js')
    await import('../../../app/static/js/features/preferences/access_panel.js')

    document.getElementById('options-access-use-btn').click()
    document.getElementById('options-access-redemption-input').value = SECRET
    document.getElementById('options-access-redemption-apply').click()

    await vi.waitFor(() => expect(document.getElementById('options-access-msg').textContent).toContain('not accepted'))
    expect(session.activateAccessCredential).not.toHaveBeenCalled()
    expect(document.getElementById('options-access-redemption-input').value).toBe('')
  })

  it('lets the user remove an invalid credential instead of trapping the browser in a failed identity', async () => {
    globalThis.__accessPanelTest.identity = {
      kind: 'credential', anonymousId: '', credentialId: '', validFormat: false,
    }
    globalThis.__accessPanelTest.showConfirm.mockResolvedValue('remove')
    const session = await import('../../../app/static/js/session.js')
    const { refreshAccessPanel } = await import('../../../app/static/js/features/preferences/access_panel.js')

    await refreshAccessPanel()
    const remove = document.getElementById('options-access-discard-invalid-btn')
    expect(remove.hidden).toBe(false)
    remove.click()

    await vi.waitFor(() => expect(session.clearAccessCredential).toHaveBeenCalled())
    expect(document.getElementById('options-access-summary').textContent).toBe('Anonymous workspace')
  })

  it('renders safe credential metadata and marks the current credential', async () => {
    globalThis.__accessPanelTest.identity = {
      kind: 'credential', anonymousId: '', credentialId: CURRENT_ID, validFormat: true,
    }
    globalThis.__accessPanelTest.apiFetch.mockImplementation((url) => {
      if (url === '/auth/principal') return response({ authentication: { credential_id: CURRENT_ID } })
      if (url === '/auth/credentials') return response({ credentials: [credential()] })
      return response({})
    })
    const { refreshAccessPanel } = await import('../../../app/static/js/features/preferences/access_panel.js')

    await refreshAccessPanel()

    const row = document.querySelector(`[data-credential-id="${CURRENT_ID}"]`)
    expect(row.textContent).toContain('This browser')
    expect(row.textContent).toContain(CURRENT_ID.slice(0, 12))
    expect(row.textContent).toContain('Current')
    expect(row.textContent).toContain('No expiry')
    expect(row.textContent).not.toContain(SECRET)
  })

  it('renders active, expired, and revoked rows without lifecycle actions on inactive credentials', async () => {
    globalThis.__accessPanelTest.identity = {
      kind: 'credential', anonymousId: '', credentialId: CURRENT_ID, validFormat: true,
    }
    const expiredId = `crd_${'e'.repeat(32)}`
    const revokedId = `crd_${'f'.repeat(32)}`
    globalThis.__accessPanelTest.apiFetch.mockImplementation((url) => {
      if (url === '/auth/principal') return response({ authentication: { credential_id: CURRENT_ID } })
      if (url === '/auth/credentials') {
        return response({ credentials: [
          credential(),
          credential({ id: expiredId, public_prefix: expiredId.slice(0, 12), label: 'Expired device', expires_at: '2020-01-01T00:00:00Z' }),
          credential({ id: revokedId, public_prefix: revokedId.slice(0, 12), label: 'Lost device', revoked_at: '2026-09-10T13:00:00Z' }),
        ] })
      }
      return response({})
    })
    const { refreshAccessPanel } = await import('../../../app/static/js/features/preferences/access_panel.js')

    await refreshAccessPanel()

    expect(document.querySelector(`[data-credential-id="${expiredId}"]`).textContent).toContain('Expired')
    expect(document.querySelector(`[data-credential-id="${revokedId}"]`).textContent).toContain('Revoked')
    expect(document.querySelector(`[data-credential-id="${expiredId}"] [data-credential-action]`)).toBeNull()
    expect(document.querySelector(`[data-credential-id="${revokedId}"] [data-credential-action]`)).toBeNull()
  })

  it('does not let an older refresh replace newer credential state', async () => {
    globalThis.__accessPanelTest.identity = {
      kind: 'credential', anonymousId: '', credentialId: CURRENT_ID, validFormat: true,
    }
    let releaseFirstPrincipal
    let principalCalls = 0
    let credentialCalls = 0
    globalThis.__accessPanelTest.apiFetch.mockImplementation((url) => {
      if (url === '/auth/principal') {
        principalCalls += 1
        if (principalCalls === 1) {
          return new Promise(resolve => { releaseFirstPrincipal = () => resolve(response({}).then(value => value)) })
        }
        return response({})
      }
      if (url === '/auth/credentials') {
        credentialCalls += 1
        return response({ credentials: [credential({ label: credentialCalls === 1 ? 'New state' : 'Old state' })] })
      }
      return response({})
    })
    const { refreshAccessPanel } = await import('../../../app/static/js/features/preferences/access_panel.js')

    const older = refreshAccessPanel()
    const newer = refreshAccessPanel()
    await newer
    releaseFirstPrincipal()
    await older

    expect(document.getElementById('options-access-credentials').textContent).toContain('New state')
    expect(document.getElementById('options-access-credentials').textContent).not.toContain('Old state')
  })

  it('previews durable work before revoking the current credential', async () => {
    globalThis.__accessPanelTest.identity = {
      kind: 'credential', anonymousId: '', credentialId: CURRENT_ID, validFormat: true,
    }
    globalThis.__accessPanelTest.showConfirm.mockImplementation(async (options) => {
      expect(options.content.textContent).toContain('Nightly scan')
      return 'revoke'
    })
    globalThis.__accessPanelTest.apiFetch.mockImplementation((url) => {
      if (url === '/auth/principal') return response({ authentication: { credential_id: CURRENT_ID } })
      if (url === '/auth/credentials') return response({ credentials: [credential()] })
      if (url.endsWith('/durable-work')) {
        return response({ durable_work: { affected: [{ kind: 'schedule', id: 'sch_1', label: 'Nightly scan', state: 'active', pausable: true }] } })
      }
      if (url.endsWith('/revoke')) return response({
        durable_work: {
          affected: [{ kind: 'schedule', id: 'sch_1', label: 'Nightly scan', state: 'active', pausable: true }],
          paused_count: 0,
        },
      })
      return response({})
    })
    const session = await import('../../../app/static/js/session.js')
    const { refreshAccessPanel } = await import('../../../app/static/js/features/preferences/access_panel.js')
    await refreshAccessPanel()

    document.querySelector('[data-credential-action="revoke"]').click()

    await vi.waitFor(() => expect(session.clearAccessCredential).toHaveBeenCalled())
    const urls = globalThis.__accessPanelTest.apiFetch.mock.calls.map(([url]) => url)
    expect(urls.indexOf(`/auth/credentials/${CURRENT_ID}/durable-work`)).toBeLessThan(
      urls.indexOf(`/auth/credentials/${CURRENT_ID}/revoke`),
    )
    expect(document.getElementById('options-access-affected-work').textContent).toContain('Nightly scan')
  })

  it('keeps the old credential active until the one-time rotation replacement is saved', async () => {
    globalThis.__accessPanelTest.identity = {
      kind: 'credential', anonymousId: '', credentialId: CURRENT_ID, validFormat: true,
    }
    globalThis.__accessPanelTest.showConfirm
      .mockResolvedValueOnce('continue')
      .mockResolvedValueOnce('revoke')
    globalThis.__accessPanelTest.apiFetch.mockImplementation((url, options = {}) => {
      if (url === '/auth/principal') return response({ authentication: { credential_id: CURRENT_ID } })
      if (url.endsWith('/rotate') && options.method === 'POST') return response({ secret: REPLACEMENT_SECRET }, 201)
      if (url === '/auth/credentials') return response({ credentials: [credential()] })
      if (url.endsWith('/durable-work')) return response({ durable_work: { affected: [] } })
      if (url.endsWith('/revoke')) return response({ durable_work: { paused_count: 0 } })
      return response({})
    })
    const session = await import('../../../app/static/js/session.js')
    const { refreshAccessPanel } = await import('../../../app/static/js/features/preferences/access_panel.js')
    await refreshAccessPanel()

    document.querySelector('[data-credential-action="rotate"]').click()
    await vi.waitFor(() => expect(document.getElementById('options-access-reveal').hidden).toBe(false))
    expect(globalThis.__accessPanelTest.apiFetch.mock.calls.some(([url]) => url.endsWith('/revoke'))).toBe(false)

    ;[...document.querySelectorAll('#options-access-reveal button')]
      .find(button => button.textContent === 'I saved it').click()

    await vi.waitFor(() => expect(session.activateAccessCredential).toHaveBeenCalledWith(REPLACEMENT_SECRET))
    const urls = globalThis.__accessPanelTest.apiFetch.mock.calls.map(([url]) => url)
    expect(globalThis.__accessPanelTest.apiFetch).toHaveBeenCalledWith(`/auth/credentials/${CURRENT_ID}/rotate`, expect.objectContaining({
      method: 'POST', body: JSON.stringify({ defer_revocation: true }),
    }))
    expect(urls.indexOf('/auth/credentials')).toBeLessThan(urls.indexOf(`/auth/credentials/${CURRENT_ID}/revoke`))
  })

  it.each(['revoke', 'rotate'])('signs out a restricted browser after current credential %s', async action => {
    globalThis.__accessPanelTest.appConfig = { access_profile: 'token_required' }
    globalThis.__accessPanelTest.identity = {
      kind: 'browser_session', anonymousId: '', credentialId: '', validFormat: true,
    }
    if (action === 'rotate') globalThis.__accessPanelTest.showConfirm.mockResolvedValueOnce('continue')
    globalThis.__accessPanelTest.showConfirm.mockResolvedValueOnce('revoke')
    globalThis.__accessPanelTest.apiFetch.mockImplementation((url, options = {}) => {
      if (url === '/auth/principal') return response({ authentication: { credential_id: CURRENT_ID, credential_type: 'portable' } })
      if (url.endsWith('/rotate') && options.method === 'POST') return response({ secret: REPLACEMENT_SECRET }, 201)
      if (url === '/auth/credentials') return response({ credentials: [credential()] })
      if (url.endsWith('/durable-work')) return response({ durable_work: { affected: [] } })
      if (url.endsWith('/revoke')) return response({ durable_work: {} })
      return response({})
    })
    const session = await import('../../../app/static/js/session.js')
    const { refreshAccessPanel } = await import('../../../app/static/js/features/preferences/access_panel.js')
    await refreshAccessPanel()
    document.querySelector(`[data-credential-action="${action}"]`).click()
    if (action === 'rotate') {
      await vi.waitFor(() => expect(document.getElementById('options-access-reveal').hidden).toBe(false))
      expect(session.redirectToSignIn).not.toHaveBeenCalled()
      expect(globalThis.__accessPanelTest.apiFetch.mock.calls.some(([url]) => url.endsWith('/revoke'))).toBe(false)
      ;[...document.querySelectorAll('#options-access-reveal button')].find(button => button.textContent === 'I saved it').click()
    }
    await vi.waitFor(() => expect(session.redirectToSignIn).toHaveBeenCalledOnce())
    expect(globalThis.__accessPanelTest.showConfirm.mock.calls.at(-1)[0].body).toContain('sign out this browser')
    expect(session.activateAccessCredential).not.toHaveBeenCalled()
    expect(document.getElementById('options-access-reveal').textContent).not.toContain(REPLACEMENT_SECRET)
  })

  it('shows a failed logout in the Access panel and permits retry', async () => {
    globalThis.__accessPanelTest.identity = {
      kind: 'browser_session', anonymousId: '', credentialId: '', validFormat: true,
    }
    globalThis.__accessPanelTest.showConfirm.mockResolvedValue('remove')
    globalThis.__accessPanelTest.apiFetch.mockRejectedValueOnce(new Error('Connection lost'))
      .mockImplementation(() => response({}, 204))
    const session = await import('../../../app/static/js/session.js')
    await import('../../../app/static/js/features/preferences/access_panel.js')
    document.getElementById('options-access-remove-btn').click()
    await vi.waitFor(() => expect(document.getElementById('options-access-msg').textContent).toContain('Connection lost'))
    expect(session.redirectToSignIn).not.toHaveBeenCalled()
    document.getElementById('options-access-remove-btn').click()
    await vi.waitFor(() => expect(session.redirectToSignIn).toHaveBeenCalledOnce())
  })

  it('creates an API token with chosen scopes and lifetime through Add credential', async () => {
    const scopes = ['identity:read', 'history:read', 'runs:execute', 'projects:read']
    const token = `dlp_v1_pat_${'e'.repeat(32)}_${'f'.repeat(43)}`
    globalThis.__accessPanelTest.identity = {
      kind: 'credential', anonymousId: '', credentialId: CURRENT_ID, validFormat: true,
    }
    globalThis.__accessPanelTest.apiFetch.mockImplementation((url, options = {}) => {
      if (url === '/auth/principal') return response({ authentication: { credential_id: CURRENT_ID } })
      if (url === '/auth/credentials' && options.method === 'POST') return response({ secret: token }, 201)
      if (url === '/auth/credentials') return response({ credentials: [credential()], pat_policy: {
        scopes, default_scopes: scopes.slice(0, 3), default_expiry_days: 90, min_expiry_days: 1, max_expiry_days: 365,
      } })
      return response({})
    })
    const session = await import('../../../app/static/js/session.js')
    const { refreshAccessPanel } = await import('../../../app/static/js/features/preferences/access_panel.js')
    await refreshAccessPanel()
    document.getElementById('options-access-add-btn').click()
    const editor = document.getElementById('options-access-editor')
    const type = editor.querySelector('select')
    type.value = 'pat'
    type.dispatchEvent(new Event('change'))
    expect(editor.querySelector('input[type="datetime-local"]').closest('label').hidden).toBe(true)
    expect([...editor.querySelectorAll('[name="pat_scope"]:checked')].map(node => node.value)).toEqual(scopes.slice(0, 3))
    editor.querySelector('input[type="text"]').value = 'CLI work'
    const days = editor.querySelector('input[type="number"]')
    days.value = '366'
    editor.querySelector('.btn-primary').click()
    await vi.waitFor(() => expect(editor.textContent).toContain('between 1 and 365'))
    expect(globalThis.__accessPanelTest.apiFetch.mock.calls.some(([url, opts]) => url === '/auth/credentials' && opts?.method === 'POST')).toBe(false)
    days.value = '1'
    editor.querySelector('[value="projects:read"]').checked = true
    editor.querySelector('.btn-primary').click()
    await vi.waitFor(() => expect(document.getElementById('options-access-reveal').hidden).toBe(false))
    const [, options] = globalThis.__accessPanelTest.apiFetch.mock.calls.find(([url, opts]) => url === '/auth/credentials' && opts?.method === 'POST')
    expect(JSON.parse(options.body)).toEqual({ type: 'pat', label: 'CLI work', expires_in_days: 1, scopes })
    expect(session.activateAccessCredential).not.toHaveBeenCalled()
    expect(document.getElementById('options-access-reveal').textContent).not.toContain(token)
  })

  it.each(['portable', 'oidc'])('shows session sign-out wording for %s browsers', async kind => {
    globalThis.__accessPanelTest.identity = { kind: 'browser_session', credentialId: '', validFormat: true }
    globalThis.__accessPanelTest.apiFetch.mockImplementation(url => response(url === '/auth/principal'
      ? { authentication: { credential_id: kind === 'portable' ? CURRENT_ID : '', credential_type: kind } }
      : { credentials: [] }))
    const { refreshAccessPanel } = await import('../../../app/static/js/features/preferences/access_panel.js')
    await refreshAccessPanel()
    expect(document.getElementById('options-access-remove-btn').textContent).toBe('Sign out')
    expect(document.getElementById('options-access-remove-all-btn').hidden).toBe(false)
    document.getElementById('options-access-remove-btn').click()
    expect(globalThis.__accessPanelTest.showConfirm.mock.calls[0][0].body).toContain('Your workspace stays saved')
    expect(globalThis.__accessPanelTest.showConfirm.mock.calls[0][0].body.includes('identity provider')).toBe(kind === 'oidc')
    globalThis.__accessPanelTest.identity = { kind: 'credential', credentialId: CURRENT_ID, validFormat: true }
    await refreshAccessPanel()
    expect(document.getElementById('options-access-remove-btn').textContent).toBe('Remove from browser')
    expect(document.getElementById('options-access-remove-all-btn').hidden).toBe(true)
  })

  it.each([false, true])('signs out everywhere or offers recent sign-in when required: %s', async needsReauth => {
    globalThis.__accessPanelTest.identity = { kind: 'browser_session', credentialId: '', validFormat: true }
    globalThis.__accessPanelTest.showConfirm.mockResolvedValue('sign-out-all')
    globalThis.__accessPanelTest.apiFetch.mockImplementation(url => url === '/auth/sessions/revoke-all'
      ? response(needsReauth ? { error: 'recent_authentication_required', message: 'Sign in again first.' } : { revoked_sessions: 2 }, needsReauth ? 403 : 200)
      : response(url === '/auth/principal' ? { authentication: { credential_type: 'oidc' } } : { credentials: [] }))
    const session = await import('../../../app/static/js/session.js')
    const { refreshAccessPanel } = await import('../../../app/static/js/features/preferences/access_panel.js')
    await refreshAccessPanel()
    document.getElementById('options-access-remove-all-btn').click()
    await vi.waitFor(() => expect(globalThis.__accessPanelTest.apiFetch).toHaveBeenCalledWith('/auth/sessions/revoke-all', expect.objectContaining({ method: 'POST' })))
    if (needsReauth) {
      await vi.waitFor(() => expect(document.getElementById('options-access-session-reauth').hidden).toBe(false))
      expect(document.getElementById('options-access-session-reauth').getAttribute('href')).toBe('/auth/sign-in?next=%2F%3Foptions%3Daccess')
      expect(document.activeElement).toBe(document.getElementById('options-access-session-reauth'))
      expect(session.redirectToSignIn).not.toHaveBeenCalled()
    } else {
      await vi.waitFor(() => expect(session.redirectToSignIn).toHaveBeenCalledOnce())
    }
  })

  it.each([false, true])('offers credential sign-in for an older session, linked: %s', async linked => {
    globalThis.__accessPanelTest.appConfig = { access_profile: 'mixed' }
    globalThis.__accessPanelTest.identity = { kind: 'browser_session', validFormat: true }
    globalThis.__accessPanelTest.apiFetch.mockImplementation(url => response(url === '/auth/principal'
      ? { authentication: { credential_type: 'portable', recent_credential_session: false } }
      : url === '/auth/oidc/identity' ? { linked } : { credentials: [] }))
    const { refreshAccessPanel } = await import('../../../app/static/js/features/preferences/access_panel.js')
    await refreshAccessPanel()
    expect(document.getElementById('options-access-oidc-link').hidden).toBe(true)
    expect(document.getElementById('options-access-oidc-unlink').hidden).toBe(true)
    expect(document.getElementById('options-access-oidc-reauth').hidden).toBe(false)
    globalThis.__accessPanelTest.appConfig.access_profile = 'oidc_required'
    await refreshAccessPanel()
    expect(document.getElementById('options-access-oidc-reauth').hidden).toBe(true)
  })

  it.each(['link', 'unlink'])('offers reauthentication when recency expires before %s', async action => {
    globalThis.__accessPanelTest.appConfig = { access_profile: 'mixed' }
    globalThis.__accessPanelTest.identity = { kind: 'browser_session', validFormat: true }
    globalThis.__accessPanelTest.showConfirm.mockResolvedValue('unlink')
    globalThis.__accessPanelTest.apiFetch.mockImplementation(url => {
      if (url === '/auth/principal') return response({ authentication: { credential_type: 'portable', recent_credential_session: true } })
      if (url === '/auth/oidc/identity') return response({ linked: action === 'unlink' })
      if (url === `/auth/oidc/${action}`) return response({ error: 'recent_credential_required', message: 'Sign in again with your credential.' }, 403)
      return response({ credentials: [] })
    })
    const { refreshAccessPanel } = await import('../../../app/static/js/features/preferences/access_panel.js')
    await refreshAccessPanel()
    const button = document.getElementById(`options-access-oidc-${action}`)
    expect(button.hidden).toBe(false)
    button.click()
    await vi.waitFor(() => expect(document.getElementById('options-access-oidc-reauth').hidden).toBe(false))
    expect(button.hidden).toBe(true)
    expect(document.activeElement).toBe(document.getElementById('options-access-oidc-reauth'))
    expect(document.getElementById('options-access-msg').textContent).toContain('Sign in again')
  })

  it('shows safe provider-link actions only for a credential-backed browser session', async () => {
    globalThis.__accessPanelTest.appConfig = { access_profile: 'mixed' }
    globalThis.__accessPanelTest.identity = {
      kind: 'browser_session', anonymousId: '', credentialId: '', validFormat: true,
    }
    globalThis.__accessPanelTest.apiFetch.mockImplementation((url) => {
      if (url === '/auth/principal') return response({ authentication: { credential_id: CURRENT_ID, credential_type: 'portable', recent_credential_session: true } })
      if (url === '/auth/credentials') return response({ credentials: [credential()] })
      if (url === '/auth/oidc/identity') return response({ linked: false, issuer: 'https://idp.example' })
      if (url === '/auth/oidc/link') return response({ authorization_url: 'http://unsafe.example/authorize' })
      return response({})
    })
    const { refreshAccessPanel } = await import('../../../app/static/js/features/preferences/access_panel.js')
    await refreshAccessPanel()
    expect(document.getElementById('options-access-oidc-section').hidden).toBe(false)
    expect(document.getElementById('options-access-oidc-link').hidden).toBe(false)
    expect(document.getElementById('options-access-oidc-unlink').hidden).toBe(true)
    document.getElementById('options-access-oidc-link').click()
    await vi.waitFor(() => expect(document.getElementById('options-access-msg').textContent).toContain('invalid'))
    expect(globalThis.__accessPanelTest.apiFetch).toHaveBeenCalledWith('/auth/oidc/link', expect.objectContaining({ method: 'POST' }))

    globalThis.__accessPanelTest.apiFetch.mockImplementation((url) => {
      if (url === '/auth/principal') return response({ authentication: { credential_id: '', credential_type: 'oidc' } })
      if (url === '/auth/credentials') return response({ credentials: [] })
      if (url === '/auth/oidc/identity') return response({ linked: true, issuer: 'https://idp.example' })
      return response({})
    })
    await refreshAccessPanel()
    expect(document.getElementById('options-access-oidc-link').hidden).toBe(true)
    expect(document.getElementById('options-access-oidc-unlink').hidden).toBe(true)
    expect(document.getElementById('options-access-oidc-reauth').hidden).toBe(false)
  })
})
