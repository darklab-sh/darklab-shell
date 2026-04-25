import { MemoryStorage, fromDomScripts } from './helpers/extract.js'

function loadSession({
  storageData = {},
  fetchImpl,
  randomUUID = () => 'generated-session-id',
} = {}) {
  const storage = new MemoryStorage()
  for (const [key, value] of Object.entries(storageData)) {
    storage.setItem(key, value)
  }

  const fetchCalls = []
  const fetchFn =
    fetchImpl ||
    ((url, options) => {
      fetchCalls.push([url, options])
      return Promise.resolve({ ok: true })
    })

  const fns = fromDomScripts(
    ['app/static/js/session.js'],
    {
      localStorage: storage,
      crypto: { randomUUID },
      fetch: fetchFn,
    },
    `{
    apiFetch,
    describeFetchError,
    logClientError,
    maskSessionToken,
    updateSessionId,
    _getSessionId: () => SESSION_ID,
  }`,
  )

  return { ...fns, storage, fetchCalls }
}

describe('session.js', () => {
  it('reuses an existing session id from localStorage', () => {
    const { _getSessionId, storage } = loadSession({
      storageData: { session_id: 'existing-session' },
      randomUUID: () => 'new-session',
    })

    expect(_getSessionId()).toBe('existing-session')
    expect(storage.getItem('session_id')).toBe('existing-session')
  })

  it('generates and persists a session id when one does not exist', () => {
    const { _getSessionId, storage } = loadSession({
      randomUUID: () => 'generated-session',
    })

    expect(_getSessionId()).toBe('generated-session')
    expect(storage.getItem('session_id')).toBe('generated-session')
  })

  it('treats a blank stored session id as missing and generates a new one', () => {
    const { _getSessionId, storage } = loadSession({
      storageData: { session_id: '' },
      randomUUID: () => 'generated-from-blank',
    })

    expect(_getSessionId()).toBe('generated-from-blank')
    expect(storage.getItem('session_id')).toBe('generated-from-blank')
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
    expect(storage.getItem('session_id')).toBe(sessionId)
  })

  it('apiFetch injects the X-Session-ID header', async () => {
    const { apiFetch, fetchCalls } = loadSession({
      storageData: { session_id: 'session-123' },
    })

    await apiFetch('/config')

    expect(fetchCalls).toHaveLength(1)
    expect(fetchCalls[0][0]).toBe('/config')
    expect(fetchCalls[0][1].headers['X-Session-ID']).toBe('session-123')
  })

  it('apiFetch preserves existing headers while adding the session header', async () => {
    const { apiFetch, fetchCalls } = loadSession({
      storageData: { session_id: 'session-abc' },
    })

    await apiFetch('/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    })

    expect(fetchCalls[0][1].headers).toEqual({
      'Content-Type': 'application/json',
      'X-Session-ID': 'session-abc',
    })
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

  it('prefers session_token over session_id when both are in localStorage', () => {
    const { _getSessionId } = loadSession({
      storageData: {
        session_id: 'uuid-session',
        session_token: 'tok_abcd1234efgh5678ijkl9012mnop3456',
      },
    })

    expect(_getSessionId()).toBe('tok_abcd1234efgh5678ijkl9012mnop3456')
  })

  it('falls back to session_id UUID when session_token is absent', () => {
    const { _getSessionId } = loadSession({
      storageData: { session_id: 'uuid-fallback' },
    })

    expect(_getSessionId()).toBe('uuid-fallback')
  })

  it('updateSessionId switches SESSION_ID at runtime', () => {
    const { _getSessionId, updateSessionId } = loadSession({
      storageData: { session_id: 'original-uuid' },
    })

    expect(_getSessionId()).toBe('original-uuid')
    updateSessionId('tok_newtoken1234567890abcdef12345678')
    expect(_getSessionId()).toBe('tok_newtoken1234567890abcdef12345678')
  })

  it('apiFetch sends updated session token after updateSessionId', async () => {
    const { apiFetch, fetchCalls, updateSessionId } = loadSession({
      storageData: { session_id: 'original-uuid' },
    })

    updateSessionId('tok_newtoken1234567890abcdef12345678')
    await apiFetch('/history')

    expect(fetchCalls[0][1].headers['X-Session-ID']).toBe('tok_newtoken1234567890abcdef12345678')
  })

  it('updateSessionId reloads session preferences when the helper is available', () => {
    const loadSessionPreferences = vi.fn(() => Promise.resolve())
    const { updateSessionId } = loadSession({
      storageData: { session_id: 'original-uuid' },
    })
    window.loadSessionPreferences = loadSessionPreferences

    updateSessionId('tok_newtoken1234567890abcdef12345678')

    expect(loadSessionPreferences).toHaveBeenCalled()
    delete window.loadSessionPreferences
  })

  it('maskSessionToken masks a tok_ token showing only the first 4 hex chars', () => {
    const { maskSessionToken } = loadSession()

    expect(maskSessionToken('tok_abcd1234efgh5678ijkl9012mnop3456')).toBe('tok_abcd••••')
  })

  it('maskSessionToken masks a UUID session showing the first 8 chars', () => {
    const { maskSessionToken } = loadSession()

    expect(maskSessionToken('abcdef12-1234-1234-1234-abcdef123456')).toBe('abcdef12••••••••')
  })

  it('maskSessionToken returns (none) for empty input', () => {
    const { maskSessionToken } = loadSession()

    expect(maskSessionToken('')).toBe('(none)')
    expect(maskSessionToken(null)).toBe('(none)')
  })

  it('storage event from another tab updates SESSION_ID to the new token', () => {
    const { _getSessionId } = loadSession({
      storageData: { session_id: 'uuid-original' },
    })

    expect(_getSessionId()).toBe('uuid-original')

    window.dispatchEvent(
      new StorageEvent('storage', {
        key: 'session_token',
        newValue: 'tok_newtoken1234567890abcdef12345678',
      }),
    )

    expect(_getSessionId()).toBe('tok_newtoken1234567890abcdef12345678')
  })

  it('storage event from another tab reverts SESSION_ID to UUID when token is cleared', () => {
    const { _getSessionId } = loadSession({
      storageData: {
        session_id: 'uuid-base',
        session_token: 'tok_existingtoken234567890abcdef12',
      },
    })

    expect(_getSessionId()).toBe('tok_existingtoken234567890abcdef12')

    window.dispatchEvent(new StorageEvent('storage', { key: 'session_token', newValue: null }))

    expect(_getSessionId()).toBe('uuid-base')
  })

  it('storage event for an unrelated key does not change SESSION_ID', () => {
    const { _getSessionId } = loadSession({
      storageData: { session_id: 'uuid-stable' },
    })

    window.dispatchEvent(
      new StorageEvent('storage', { key: 'some_other_key', newValue: 'irrelevant' }),
    )

    expect(_getSessionId()).toBe('uuid-stable')
  })

  it('storage event calls reloadSessionHistory when available to refresh passive tab UI', () => {
    const reloadSessionHistory = vi.fn(() => Promise.resolve())
    loadSession({ storageData: { session_id: 'uuid-a' } })
    // Inject the global that session.js checks with typeof
    window.reloadSessionHistory = reloadSessionHistory

    window.dispatchEvent(
      new StorageEvent('storage', {
        key: 'session_token',
        newValue: 'tok_newtoken1234567890abcdef12345678',
      }),
    )

    expect(reloadSessionHistory).toHaveBeenCalled()
    delete window.reloadSessionHistory
  })

  it('storage event calls loadSessionPreferences when available', () => {
    const loadSessionPreferences = vi.fn(() => Promise.resolve())
    loadSession({ storageData: { session_id: 'uuid-a' } })
    window.loadSessionPreferences = loadSessionPreferences

    window.dispatchEvent(
      new StorageEvent('storage', {
        key: 'session_token',
        newValue: 'tok_newtoken1234567890abcdef12345678',
      }),
    )

    expect(loadSessionPreferences).toHaveBeenCalled()
    delete window.loadSessionPreferences
  })

  it('storage event calls _updateOptionsSessionTokenStatus when available', () => {
    const _updateOptionsSessionTokenStatus = vi.fn()
    loadSession({ storageData: { session_id: 'uuid-b' } })
    window._updateOptionsSessionTokenStatus = _updateOptionsSessionTokenStatus

    window.dispatchEvent(
      new StorageEvent('storage', {
        key: 'session_token',
        newValue: 'tok_newtoken1234567890abcdef12345678',
      }),
    )

    expect(_updateOptionsSessionTokenStatus).toHaveBeenCalled()
    delete window._updateOptionsSessionTokenStatus
  })

  it('storage event does not throw when reloadSessionHistory and _updateOptionsSessionTokenStatus are absent', () => {
    loadSession({ storageData: { session_id: 'uuid-c' } })
    // Confirm neither global is defined
    delete window.reloadSessionHistory
    delete window._updateOptionsSessionTokenStatus

    expect(() => {
      window.dispatchEvent(
        new StorageEvent('storage', { key: 'session_token', newValue: 'tok_abc' }),
      )
    }).not.toThrow()
  })
})
