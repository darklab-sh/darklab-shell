// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { loadSession } from './helpers/session_harness.js'

describe('session.js', () => {
  it('reuses an existing anonymous id from localStorage', () => {
    const { _getSessionId, storage } = loadSession({
      storageData: { anonymous_id: 'existing-session' },
      randomUUID: () => 'new-session',
    })

    expect(_getSessionId()).toBe('existing-session')
    expect(storage.getItem('anonymous_id')).toBe('existing-session')
  })

  it('generates and persists an anonymous id when one does not exist', () => {
    const { _getSessionId, storage } = loadSession({
      randomUUID: () => 'generated-session',
    })

    expect(_getSessionId()).toBe('generated-session')
    expect(storage.getItem('anonymous_id')).toBe('generated-session')
  })

  it('treats a blank stored anonymous id as missing and generates a new one', () => {
    const { _getSessionId, storage } = loadSession({
      storageData: { anonymous_id: '' },
      randomUUID: () => 'generated-from-blank',
    })

    expect(_getSessionId()).toBe('generated-from-blank')
    expect(storage.getItem('anonymous_id')).toBe('generated-from-blank')
  })

  it('falls back to getRandomValues UUID generation when randomUUID throws (insecure HTTP context)', () => {
    // Simulates Safari iOS on http://192.168.x.x where randomUUID() throws
    // because it requires a secure context (HTTPS/localhost).
    const { _getSessionId, storage } = loadSession({
      randomUUID: () => { throw new Error('randomUUID not available in insecure context') },
    })

    const sessionId = _getSessionId()
    // Must be a valid UUID v4
    expect(sessionId).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
    expect(storage.getItem('anonymous_id')).toBe(sessionId)
  })

  it('apiFetch injects anonymous identity and client headers', async () => {
    const { apiFetch, fetchCalls } = loadSession({
      storageData: { anonymous_id: 'session-123', client_id: 'client-123' },
    })

    await apiFetch('/config')

    expect(fetchCalls).toHaveLength(1)
    expect(fetchCalls[0][0]).toBe('/config')
    expect(fetchCalls[0][1].headers['X-Darklab-Anonymous-ID']).toBe('session-123')
    expect(fetchCalls[0][1].headers['X-Darklab-Credential']).toBeUndefined()
    expect(fetchCalls[0][1].headers['X-Client-ID']).toBe('client-123')
  })

  it('apiFetch preserves existing headers while adding the anonymous identity header', async () => {
    const { apiFetch, fetchCalls } = loadSession({
      storageData: { anonymous_id: 'session-abc', client_id: 'client-abc' },
    })

    await apiFetch('/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    })

    expect(fetchCalls[0][1].headers).toEqual({
      'Content-Type': 'application/json',
      'X-Darklab-Anonymous-ID': 'session-abc',
      'X-Client-ID': 'client-abc',
    })
  })

  it('logClientError forwards safe event and level fields to the client log endpoint', async () => {
    const { logClientError, fetchCalls } = loadSession({
      storageData: { anonymous_id: 'session-log', client_id: 'client-log' },
    })
    const err = new Error('lazy module failed /static/build/project-report.123456789abc.js?v=abc123&token=secret')

    logClientError('lazy asset load failed', err, {
      event: 'LAZY_ASSET_LOAD_FAILED',
      level: 'error',
      asset_name: 'project_report',
    })
    await Promise.resolve()

    expect(fetchCalls).toHaveLength(1)
    expect(fetchCalls[0][0]).toBe('/log')
    expect(JSON.parse(fetchCalls[0][1].body)).toEqual({
      context: 'lazy asset load failed',
      message: 'lazy module failed /static/build/project-report.123456789abc.js?v=abc123',
      event: 'LAZY_ASSET_LOAD_FAILED',
      level: 'error',
      details: {
        event: 'LAZY_ASSET_LOAD_FAILED',
        level: 'error',
        asset_name: 'project_report',
        error_name: 'Error',
      },
    })
    expect(fetchCalls[0][1].body).not.toContain('secret')
  })

  it('describeFetchError returns a friendly offline message for network failures', () => {
    const { describeFetchError } = loadSession()

    expect(describeFetchError(new Error('Failed to fetch'))).toBe(
      'Unable to contact the server right now. Please try again in a moment. If this keeps happening, contact the shell operator.',
    )
  })

  it('describeFetchError preserves non-network error details', () => {
    const { describeFetchError } = loadSession()

    expect(describeFetchError(new Error('TLS handshake failed'))).toBe(
      'Request to the server failed: TLS handshake failed',
    )
  })

  it('uses a credential public id for local scope while keeping the secret out of UI state', () => {
    const secret = `dlc_v1_crd_${'a'.repeat(32)}_${'b'.repeat(43)}`
    const { _getSessionId, getBrowserIdentitySnapshot } = loadSession({
      storageData: {
        anonymous_id: 'uuid-session',
        access_credential: secret,
      },
    })

    expect(_getSessionId()).toBe(`crd_${'a'.repeat(32)}`)
    expect(getBrowserIdentitySnapshot()).toEqual({
      kind: 'credential',
      anonymousId: '',
      credentialId: `crd_${'a'.repeat(32)}`,
      validFormat: true,
    })
  })

  it('uses the anonymous UUID when no access credential is present', () => {
    const { _getSessionId, storage } = loadSession({
      storageData: { anonymous_id: 'uuid-fallback' },
    })

    expect(_getSessionId()).toBe('uuid-fallback')
  })

  it('activateAccessCredential switches the local identity at runtime', () => {
    const secret = `dlc_v1_crd_${'c'.repeat(32)}_${'d'.repeat(43)}`
    const { _getSessionId, activateAccessCredential } = loadSession({
      storageData: { anonymous_id: 'original-uuid' },
    })

    expect(_getSessionId()).toBe('original-uuid')
    activateAccessCredential(secret)
    expect(_getSessionId()).toBe(`crd_${'c'.repeat(32)}`)
  })

  it('rejects browser credentials that do not match the portable server format', () => {
    const { activateAccessCredential } = loadSession({
      storageData: { anonymous_id: 'original-uuid' },
    })

    for (const value of [
      `dlc_v1_crd_${'c'.repeat(32)}_${'d'.repeat(42)}`,
      `dlp_v1_pat_${'c'.repeat(32)}_${'d'.repeat(43)}`,
      `DLC_v1_crd_${'c'.repeat(32)}_${'d'.repeat(43)}`,
    ]) {
      expect(() => activateAccessCredential(value)).toThrow('Invalid access credential format')
    }
  })

  it('apiFetch sends the stored credential after activation', async () => {
    const secret = `dlc_v1_crd_${'e'.repeat(32)}_${'f'.repeat(43)}`
    const { apiFetch, fetchCalls, activateAccessCredential } = loadSession({
      storageData: { anonymous_id: 'original-uuid' },
    })

    activateAccessCredential(secret)
    await apiFetch('/history')

    expect(fetchCalls[0][1].headers['X-Darklab-Credential']).toBe(secret)
    expect(fetchCalls[0][1].headers['X-Darklab-Anonymous-ID']).toBeUndefined()
  })

  it('credential activation reloads identity-bound preferences', () => {
    const loadSessionPreferences = vi.fn(() => Promise.resolve())
    const { activateAccessCredential } = loadSession({
      storageData: { anonymous_id: 'original-uuid' },
    })
    window.loadSessionPreferences = loadSessionPreferences

    activateAccessCredential(`dlc_v1_crd_${'1'.repeat(32)}_${'2'.repeat(43)}`)

    expect(loadSessionPreferences).toHaveBeenCalled()
    delete window.loadSessionPreferences
  })

  it('storage event from another tab updates the active credential identity', () => {
    const { _getSessionId, storage } = loadSession({
      storageData: { anonymous_id: 'uuid-original' },
    })

    expect(_getSessionId()).toBe('uuid-original')

    storage.setItem('access_credential', `dlc_v1_crd_${'3'.repeat(32)}_${'4'.repeat(43)}`)
    window.dispatchEvent(new StorageEvent('storage', {
      key: 'access_credential',
      newValue: `dlc_v1_crd_${'3'.repeat(32)}_${'4'.repeat(43)}`,
    }))
    expect(_getSessionId()).toBe(`crd_${'3'.repeat(32)}`)
  })

  it('storage event from another tab reverts to the anonymous UUID when access is removed', () => {
    const secret = `dlc_v1_crd_${'5'.repeat(32)}_${'6'.repeat(43)}`
    const { _getSessionId, storage } = loadSession({
      storageData: {
        anonymous_id: 'uuid-base',
        access_credential: secret,
      },
    })

    expect(_getSessionId()).toBe(`crd_${'5'.repeat(32)}`)

    storage.removeItem('access_credential')
    window.dispatchEvent(new StorageEvent('storage', { key: 'access_credential', newValue: null }))

    expect(_getSessionId()).toBe('uuid-base')
  })

  it('storage event for an unrelated key does not change SESSION_ID', () => {
    const { _getSessionId } = loadSession({
      storageData: { anonymous_id: 'uuid-stable' },
    })

    window.dispatchEvent(
      new StorageEvent('storage', { key: 'some_other_key', newValue: 'irrelevant' }),
    )

    expect(_getSessionId()).toBe('uuid-stable')
  })

  it('storage event calls reloadSessionHistory when available to refresh passive tab UI', () => {
    const reloadSessionHistory = vi.fn(() => Promise.resolve())
    loadSession({ storageData: { anonymous_id: 'uuid-a' } })
    // Inject the global that session.js checks with typeof
    window.reloadSessionHistory = reloadSessionHistory

    window.dispatchEvent(
      new StorageEvent('storage', {
        key: 'access_credential',
        newValue: `dlc_v1_crd_${'7'.repeat(32)}_${'8'.repeat(43)}`,
      }),
    )

    expect(reloadSessionHistory).toHaveBeenCalled()
    delete window.reloadSessionHistory
  })

  it('storage event calls loadSessionPreferences when available', () => {
    const loadSessionPreferences = vi.fn(() => Promise.resolve())
    loadSession({ storageData: { anonymous_id: 'uuid-a' } })
    window.loadSessionPreferences = loadSessionPreferences

    window.dispatchEvent(
      new StorageEvent('storage', {
        key: 'access_credential',
        newValue: `dlc_v1_crd_${'9'.repeat(32)}_${'a'.repeat(43)}`,
      }),
    )

    expect(loadSessionPreferences).toHaveBeenCalled()
    delete window.loadSessionPreferences
  })

  it('storage event announces the changed browser identity', () => {
    loadSession({ storageData: { anonymous_id: 'uuid-b' } })
    const listener = vi.fn()
    window.addEventListener('app:identity-changed', listener)
    window.dispatchEvent(new StorageEvent('storage', { key: 'access_credential' }))
    expect(listener).toHaveBeenCalled()
  })

  it('storage event does not throw when optional refresh handlers are absent', () => {
    loadSession({ storageData: { anonymous_id: 'uuid-c' } })
    delete window.reloadSessionHistory

    expect(() => {
      window.dispatchEvent(
        new StorageEvent('storage', { key: 'access_credential', newValue: null }),
      )
    }).not.toThrow()
  })
})
