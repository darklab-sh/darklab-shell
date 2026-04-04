import { fromDomScripts } from './helpers/extract.js'

function loadWelcomeFns({
  welcomeData = [],
  asciiArt = 'ASCII ART',
  hintItems = [],
  failAscii = false,
  failHints = false,
  config = {},
  appendLine = () => {},
} = {}) {
  document.body.innerHTML = `<div id="out"></div><input id="cmd" /><div class="prompt-wrap"></div>`
  const out = document.getElementById('out')
  const cmdInput = document.getElementById('cmd')
  const apiFetch = vi.fn(url => {
    if (url === '/welcome') {
      return Promise.resolve({ json: () => Promise.resolve(welcomeData) })
    }
    if (url === '/welcome/ascii') {
      if (failAscii) return Promise.reject(new Error('ascii down'))
      return Promise.resolve({ text: () => Promise.resolve(asciiArt) })
    }
    if (url === '/welcome/hints') {
      if (failHints) return Promise.reject(new Error('hints down'))
      return Promise.resolve({ json: () => Promise.resolve({ items: hintItems }) })
    }
    throw new Error(`Unexpected url: ${url}`)
  })

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
        welcome_sample_count: 5,
        welcome_hint_interval_ms: 0,
        welcome_hint_rotations: 2,
        welcome_status_labels: ['CONFIG', 'RUNNER', 'HISTORY', 'LIMITS', 'AUTOCOMPLETE'],
        ...config,
      },
      getOutput: () => out,
      cmdInput,
      appendLine,
      Math: Object.create(Math, {
        random: { value: () => 0 },
      }),
      setTimeout: (fn) => {
        fn()
        return 0
      },
    }, `{
      cancelWelcome,
      runWelcome,
      _isWelcomeActive: () => _welcomeActive,
      _isWelcomeDone: () => _welcomeDone,
      _sampleWelcomeBlocks,
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
    const { runWelcome, _isWelcomeActive, _isWelcomeDone, out } = loadWelcomeFns({
      welcomeData: [{ cmd: 'ping example.com', out: 'line one\nline two' }],
    })

    await runWelcome()

    expect(out.querySelector('.welcome-ascii-art')?.textContent).toContain('ASCII ART')
    expect(out.querySelectorAll('.welcome-status-loaded')).toHaveLength(5)
    expect(out.querySelector('.welcome-command')?.textContent).toContain('anon@shell.darklab.sh:~$')
    expect(out.querySelectorAll('.welcome-command')[1]?.textContent).toContain('ping example.com')
    expect(out.querySelector('.welcome-command-badge')?.textContent).toContain('try this first')
    expect(out.querySelectorAll('.welcome-hint')).toHaveLength(1)
    expect(out.querySelector('.welcome-hint')?.textContent).toContain('Enter runs the command')
    expect(_isWelcomeActive()).toBe(false)
    expect(_isWelcomeDone()).toBe(true)
  })

  it('runWelcome falls back to shell.darklab.sh banner text when /welcome/ascii fails', async () => {
    const { runWelcome, out } = loadWelcomeFns({
      welcomeData: [{ cmd: 'ping example.com', out: 'line one' }],
      failAscii: true,
    })

    await runWelcome()

    expect(out.querySelector('.welcome-ascii-art')?.textContent).toContain('shell.darklab.sh')
  })

  it('runWelcome falls back to the static hint when /welcome/hints fails', async () => {
    const { runWelcome, out } = loadWelcomeFns({
      welcomeData: [{ cmd: 'ping example.com', out: 'line one' }],
      failHints: true,
    })

    await runWelcome()

    expect(out.querySelector('.welcome-hint')?.textContent).toContain('Enter runs the command')
  })

  it('runWelcome respects welcome_sample_count of 0', async () => {
    const { runWelcome, out } = loadWelcomeFns({
      welcomeData: [
        { cmd: 'ping example.com', out: 'line one' },
        { cmd: 'dig example.com A', out: 'line two' },
      ],
      hintItems: ['Use the history panel to reopen saved runs.'],
      config: { welcome_sample_count: 0, welcome_hint_rotations: 0 },
    })

    await runWelcome()

    expect(out.querySelector('.welcome-ascii-art')?.textContent).toContain('ASCII ART')
    expect(out.querySelectorAll('.welcome-command')).toHaveLength(1)
    expect(out.querySelector('.welcome-command')?.textContent).toContain('cat ~/.ascii-art.txt')
    expect(out.querySelector('.welcome-hint')?.textContent).toContain('Use the history panel')
  })

  it('runWelcome respects welcome_hint_rotations of 0', async () => {
    const { runWelcome, out } = loadWelcomeFns({
      welcomeData: [{ cmd: 'ping example.com', out: 'line one' }],
      hintItems: ['Hint one', 'Hint two'],
      config: { welcome_hint_rotations: 0, welcome_hint_interval_ms: 0 },
    })

    await runWelcome()

    expect(out.querySelectorAll('.welcome-hint')).toHaveLength(1)
    expect(out.querySelector('.welcome-hint')?.textContent).toContain('Hint one')
  })

  it('_sampleWelcomeBlocks prefers a featured basics command first and avoids duplicates', () => {
    const { _sampleWelcomeBlocks } = loadWelcomeFns()

    const sampled = _sampleWelcomeBlocks([
      { cmd: 'dig example.com A', group: 'dns', featured: false },
      { cmd: 'ping example.com', group: 'basics', featured: true },
      { cmd: 'curl -I https://example.com', group: 'web', featured: false },
      { cmd: 'ping example.com', group: 'basics', featured: true },
    ], 3)

    expect(sampled[0].cmd).toBe('ping example.com')
    expect(sampled.map(item => item.cmd)).toEqual([
      'ping example.com',
      'dig example.com A',
      'curl -I https://example.com',
    ])
  })
})
