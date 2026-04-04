import { MemoryStorage, fromDomScripts } from './helpers/extract.js'

function loadSession({ storageData = {}, fetchImpl, randomUUID = () => 'generated-session-id' } = {}) {
  const storage = new MemoryStorage()
  for (const [key, value] of Object.entries(storageData)) {
    storage.setItem(key, value)
  }

  const fetchCalls = []
  const fetchFn = fetchImpl || ((url, options) => {
    fetchCalls.push([url, options])
    return Promise.resolve({ ok: true })
  })

  const fns = fromDomScripts([
    'app/static/js/session.js',
  ], {
    localStorage: storage,
    crypto: { randomUUID },
    fetch: fetchFn,
  }, `{
    apiFetch,
    _getSessionId: () => SESSION_ID,
  }`)

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
})
