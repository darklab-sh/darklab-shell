import { fromDomScripts } from './helpers/extract.js'

function loadWelcomeFns({ welcomeData = [], appendLine = () => {} } = {}) {
  document.body.innerHTML = `<div id="out"></div>`
  const out = document.getElementById('out')
  const apiFetch = vi.fn(() => Promise.resolve({
    json: () => Promise.resolve(welcomeData),
  }))

  return {
    ...fromDomScripts([
      'app/static/js/welcome.js',
    ], {
      document,
      apiFetch,
      activeTabId: 'tab-1',
      APP_CONFIG: {
        welcome_char_ms: 0,
        welcome_jitter_ms: 0,
        welcome_post_cmd_ms: 0,
        welcome_inter_block_ms: 0,
      },
      getOutput: () => out,
      appendLine,
      Math: { ...Math, random: () => 0 },
      setTimeout: (fn) => {
        fn()
        return 0
      },
    }, `{
      cancelWelcome,
      runWelcome,
      _isWelcomeActive: () => _welcomeActive,
      _isWelcomeDone: () => _welcomeDone,
    }`),
    apiFetch,
    out,
  }
}

describe('welcome helpers', () => {
  it('cancelWelcome clears active and done flags', () => {
    const fns = loadWelcomeFns()

    fns.cancelWelcome()

    expect(fns._isWelcomeActive()).toBe(false)
    expect(fns._isWelcomeDone()).toBe(false)
  })

  it('runWelcome stops cleanly when the server returns no blocks', async () => {
    const { runWelcome, _isWelcomeActive, _isWelcomeDone, apiFetch, out } = loadWelcomeFns()

    await runWelcome()

    expect(apiFetch).toHaveBeenCalledWith('/welcome')
    expect(_isWelcomeActive()).toBe(false)
    expect(_isWelcomeDone()).toBe(false)
    expect(out.children).toHaveLength(0)
  })

  it('runWelcome appends command and notice lines and marks completion', async () => {
    const appended = []
    const { runWelcome, _isWelcomeActive, _isWelcomeDone } = loadWelcomeFns({
      welcomeData: [{ cmd: 'ping example.com', out: 'line one\nline two' }],
      appendLine: (...args) => appended.push(args),
    })

    await runWelcome()

    expect(appended).toEqual([
      ['$ ping example.com', '', 'tab-1'],
      ['line one', 'notice', 'tab-1'],
      ['line two', 'notice', 'tab-1'],
    ])
    expect(_isWelcomeActive()).toBe(false)
    expect(_isWelcomeDone()).toBe(true)
  })
})
