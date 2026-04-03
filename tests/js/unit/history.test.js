import { fromScript } from './helpers/extract.js'

// Re-extract before each test so each test gets a fresh MemoryStorage instance.
// Extraction is cheap (one file read + new Function call).
let _getStarred, _saveStarred, _toggleStar, store

beforeEach(() => {
  ;({ _getStarred, _saveStarred, _toggleStar, _storage: store } = fromScript(
    'app/static/js/history.js',
    '_getStarred',
    '_saveStarred',
    '_toggleStar',
  ))
})

// ── _getStarred ───────────────────────────────────────────────────────────────

describe('_getStarred', () => {
  it('returns an empty Set when no starred key exists', () => {
    expect(_getStarred()).toEqual(new Set())
  })

  it('returns a Set of the stored command strings', () => {
    store.setItem('starred', JSON.stringify(['foo', 'bar']))
    expect(_getStarred()).toEqual(new Set(['foo', 'bar']))
  })

  it('returns an empty Set when the stored value is invalid JSON', () => {
    store.setItem('starred', 'not-json{{{')
    expect(_getStarred()).toEqual(new Set())
  })

  it('returns an empty Set when the stored value is an empty array', () => {
    store.setItem('starred', '[]')
    expect(_getStarred()).toEqual(new Set())
  })
})

// ── _saveStarred ──────────────────────────────────────────────────────────────

describe('_saveStarred', () => {
  it('persists a Set to localStorage as a JSON array', () => {
    _saveStarred(new Set(['alpha', 'beta']))
    const stored = JSON.parse(store.getItem('starred'))
    expect(stored).toHaveLength(2)
    expect(stored).toEqual(expect.arrayContaining(['alpha', 'beta']))
  })

  it('persists an empty Set as an empty JSON array', () => {
    _saveStarred(new Set())
    expect(store.getItem('starred')).toBe('[]')
  })

  it('round-trips correctly through _getStarred', () => {
    _saveStarred(new Set(['cmd1', 'cmd2']))
    expect(_getStarred()).toEqual(new Set(['cmd1', 'cmd2']))
  })
})

// ── _toggleStar ───────────────────────────────────────────────────────────────

describe('_toggleStar', () => {
  it('adds a command that is not yet starred', () => {
    _toggleStar('ls -la')
    expect(_getStarred().has('ls -la')).toBe(true)
  })

  it('removes a command that is already starred', () => {
    _saveStarred(new Set(['ls -la']))
    _toggleStar('ls -la')
    expect(_getStarred().has('ls -la')).toBe(false)
  })

  it('does not affect other starred commands when removing one', () => {
    _saveStarred(new Set(['cmd1', 'cmd2']))
    _toggleStar('cmd1')
    const s = _getStarred()
    expect(s.has('cmd1')).toBe(false)
    expect(s.has('cmd2')).toBe(true)
  })

  it('toggling the same command twice returns it to its original state', () => {
    _saveStarred(new Set(['cmd1']))
    _toggleStar('cmd1')
    _toggleStar('cmd1')
    expect(_getStarred().has('cmd1')).toBe(true)
  })
})
