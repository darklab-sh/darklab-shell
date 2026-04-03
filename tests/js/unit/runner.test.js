import { fromScript } from './helpers/extract.js'

const { _formatElapsed } = fromScript(
  'app/static/js/runner.js',
  '_formatElapsed',
)

// ── _formatElapsed ────────────────────────────────────────────────────────────

describe('_formatElapsed', () => {
  it('formats zero seconds', () => {
    expect(_formatElapsed(0)).toBe('0.0s')
  })

  it('formats sub-minute durations with one decimal place', () => {
    expect(_formatElapsed(32.6)).toBe('32.6s')
    expect(_formatElapsed(59.9)).toBe('59.9s')
  })

  it('formats exactly 60 seconds as minutes', () => {
    expect(_formatElapsed(60)).toBe('1m 0.0s')
  })

  it('formats multi-minute durations without hours', () => {
    expect(_formatElapsed(125)).toBe('2m 5.0s')
  })

  it('formats exactly one hour', () => {
    expect(_formatElapsed(3600)).toBe('1h 0m 0.0s')
  })

  it('formats hour + minutes + seconds', () => {
    expect(_formatElapsed(3812.3)).toBe('1h 3m 32.3s')
  })
})
