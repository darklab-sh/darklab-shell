import { MemoryStorage, fromDomScripts } from './extract.js'

export function loadSession({
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
    ['app/static/js/session_core.js', 'app/static/js/session.js'],
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
    _getClientId: () => CLIENT_ID,
  }`,
  )

  return { ...fns, storage, fetchCalls }
}
