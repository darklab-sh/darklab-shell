import { vi } from 'vitest'
import { fromDomScripts } from './helpers/extract.js'

function loadWelcomeFns({
  welcomeData = [],
  asciiArt = 'ASCII ART',
  mobileAsciiArt = 'MOBILE ASCII ART',
  hintItems = [],
  mobileHintItems = null,
  failAscii = false,
  failMobileAscii = false,
  failHints = false,
  failMobileHints = false,
  config = {},
  appendLine = () => {},
  setTimeoutImpl = null,
  mobile = false,
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
    if (url === '/welcome/ascii-mobile') {
      if (failMobileAscii) return Promise.reject(new Error('mobile ascii down'))
      return Promise.resolve({ text: () => Promise.resolve(mobileAsciiArt) })
    }
    if (url === '/welcome/hints') {
      if (failHints) return Promise.reject(new Error('hints down'))
      return Promise.resolve({ json: () => Promise.resolve({ items: hintItems }) })
    }
    if (url === '/welcome/hints-mobile') {
      if (failMobileHints) return Promise.reject(new Error('mobile hints down'))
      return Promise.resolve({ json: () => Promise.resolve({ items: mobileHintItems ?? hintItems }) })
    }
    throw new Error(`Unexpected url: ${url}`)
  })
  const mountShellPrompt = vi.fn()

  return {
    ...fromDomScripts([
      'app/static/js/welcome.js',
    ], {
      document,
      apiFetch,
      activeTabId: 'tab-1',
      _welcomeActive: false,
      _welcomeDone: false,
      _welcomeTabId: null,
      _welcomeBanner: null,
      _welcomeLiveLine: null,
      _welcomeHintNode: null,
      _welcomeStatusNodes: [],
      _welcomePlan: null,
      _welcomeNextBlockIndex: 0,
      _welcomeSettleRequested: false,
      _welcomeBootPending: true,
      APP_CONFIG: {
        welcome_char_ms: 0,
        welcome_jitter_ms: 0,
        welcome_post_cmd_ms: 0,
        welcome_inter_block_ms: 0,
        welcome_sample_count: 5,
        welcome_hint_interval_ms: 0,
        welcome_hint_rotations: 0,
        welcome_status_labels: ['CONFIG', 'RUNNER', 'HISTORY', 'LIMITS', 'AUTOCOMPLETE'],
        ...config,
      },
      getOutput: () => out,
      cmdInput,
      appendLine,
      mountShellPrompt,
      unmountShellPrompt: vi.fn(),
      logClientError: () => {},
      useMobileTerminalViewportMode: () => mobile,
      requestAnimationFrame: (fn) => fn(),
      Math: Object.create(Math, {
        random: { value: () => 0 },
      }),
      setTimeout: setTimeoutImpl || ((fn) => {
        fn()
        return 0
      }),
    }, `{
      cancelWelcome,
      requestWelcomeSettle,
      runWelcome,
      settleWelcome,
      welcomeOwnsTab,
      _coerceWelcomeHintRotationLimit,
      _welcomeHintRotationBudget,
      _isWelcomeActive: () => _welcomeActive,
      _isWelcomeDone: () => _welcomeDone,
      _sampleWelcomeBlocks,
    }`),
    apiFetch,
    out,
    mountShellPrompt,
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
      welcomeData: [{ cmd: 'ping darklab.sh', out: 'line one\nline two' }],
    })

    await runWelcome()

    expect(out.querySelector('.welcome-ascii-art')?.textContent).toMatch(/ASCII ART|darklab shell/)
    expect(out.querySelectorAll('.welcome-status-loaded')).toHaveLength(5)
    expect(out.querySelector('.welcome-command')?.textContent).toContain('anon@darklab:~$')
    expect(out.querySelectorAll('.welcome-command')[0]?.textContent).toContain('ping darklab.sh')
    expect(out.querySelector('.welcome-command-badge')?.textContent).toContain('try this first')
    expect(out.querySelectorAll('.welcome-hint')).toHaveLength(1)
    expect(out.querySelector('.welcome-hint')?.textContent).toContain('Enter runs the command')
    expect(_isWelcomeActive()).toBe(false)
    expect(_isWelcomeDone()).toBe(true)
  })

  it('runWelcome falls back to darklab shell banner text when /welcome/ascii fails', async () => {
    const { runWelcome, out } = loadWelcomeFns({
      welcomeData: [{ cmd: 'ping darklab.sh', out: 'line one' }],
      failAscii: true,
    })

    await runWelcome()

    expect(out.querySelector('.welcome-ascii-art')?.textContent).toContain('darklab shell')
  })

  it('runWelcome falls back to the static hint when /welcome/hints fails', async () => {
    const { runWelcome, out } = loadWelcomeFns({
      welcomeData: [{ cmd: 'ping darklab.sh', out: 'line one' }],
      failHints: true,
    })

    await runWelcome()

    expect(out.querySelector('.welcome-hint')?.textContent).toContain('Enter runs the command')
  })

  it('runWelcome respects welcome_sample_count of 0', async () => {
    const { runWelcome, out } = loadWelcomeFns({
      welcomeData: [
        { cmd: 'ping darklab.sh', out: 'line one' },
        { cmd: 'dig darklab.sh A', out: 'line two' },
      ],
      hintItems: ['Use the history panel to reopen saved runs.'],
      config: { welcome_sample_count: 0, welcome_hint_rotations: 0 },
    })

    await runWelcome()

    expect(out.querySelector('.welcome-ascii-art')?.textContent).toMatch(/ASCII ART|darklab shell/)
    expect(out.querySelectorAll('.welcome-command')).toHaveLength(0)
    expect(out.querySelector('.welcome-hint')?.textContent).toContain('Use the history panel')
  })

  it('runWelcome treats welcome_hint_rotations of 0 as infinite and 1 as static', async () => {
    const { _welcomeHintRotationBudget } = loadWelcomeFns()

    expect(_welcomeHintRotationBudget(0)).toBe(Infinity)
    expect(_welcomeHintRotationBudget(1)).toBe(0)
    expect(_welcomeHintRotationBudget(2)).toBe(1)

    const staticScenario = loadWelcomeFns({
      welcomeData: [{ cmd: 'ping darklab.sh', out: 'line one' }],
      hintItems: ['Hint one', 'Hint two'],
      config: {
        welcome_hint_rotations: 1,
        welcome_hint_interval_ms: 1,
        welcome_sample_count: 0,
        welcome_status_labels: ['READY'],
      },
    })

    await staticScenario.runWelcome()

    expect(staticScenario.out.querySelectorAll('.welcome-hint')).toHaveLength(1)
    expect(staticScenario.out.querySelector('.welcome-hint')?.textContent).toContain('Hint one')
  })

  it('settleWelcome renders the remaining intro immediately', async () => {
    const { runWelcome, settleWelcome, out } = loadWelcomeFns({
      welcomeData: [
        { cmd: 'ping darklab.sh', out: 'line one', group: 'basics', featured: true },
        { cmd: 'dig darklab.sh A', out: 'line two', group: 'dns' },
      ],
      hintItems: ['Hint one', 'Hint two'],
      config: {
        welcome_char_ms: 5,
        welcome_jitter_ms: 0,
        welcome_post_cmd_ms: 20,
        welcome_inter_block_ms: 80,
      },
      setTimeoutImpl: globalThis.setTimeout,
    })

    const pending = runWelcome()
    await Promise.resolve()
    expect(settleWelcome('tab-1')).toBe(true)
    await pending

    expect(out.querySelectorAll('.wlc-cursor')).toHaveLength(0)
    expect(out.querySelector('.welcome-ascii-art')?.textContent).toMatch(/ASCII ART|darklab shell/)
    expect(out.querySelectorAll('.welcome-status-loaded')).toHaveLength(5)
    expect(out.querySelector('.welcome-hint')?.textContent).toBeTruthy()
  })

  it('requestWelcomeSettle fast-forwards the intro even before the welcome plan is built', async () => {
    const { runWelcome, requestWelcomeSettle, out } = loadWelcomeFns({
      welcomeData: [
        { cmd: 'ping darklab.sh', out: 'line one', group: 'basics', featured: true },
        { cmd: 'dig darklab.sh A', out: 'line two', group: 'dns' },
      ],
      hintItems: ['Hint one'],
      config: {
        welcome_char_ms: 5,
        welcome_jitter_ms: 0,
        welcome_post_cmd_ms: 20,
        welcome_inter_block_ms: 80,
      },
      setTimeoutImpl: globalThis.setTimeout,
    })

    const pending = runWelcome()
    expect(requestWelcomeSettle('tab-1')).toBe(true)
    await pending

    expect(out.querySelectorAll('.wlc-cursor')).toHaveLength(0)
    expect(out.querySelectorAll('.welcome-status-loaded')).toHaveLength(5)
    expect(out.querySelector('.welcome-hint')?.textContent).toBeTruthy()
  })

  it('requestWelcomeSettle ignores non-owner tabs', async () => {
    const { runWelcome, requestWelcomeSettle, out } = loadWelcomeFns({
      welcomeData: [
        { cmd: 'ping darklab.sh', out: 'line one', group: 'basics', featured: true },
      ],
      hintItems: ['Hint one'],
      config: {
        welcome_char_ms: 5,
        welcome_jitter_ms: 0,
        welcome_post_cmd_ms: 20,
        welcome_inter_block_ms: 80,
      },
      setTimeoutImpl: globalThis.setTimeout,
    })

    const pending = runWelcome()

    expect(requestWelcomeSettle('tab-2')).toBe(false)

    await pending

    expect(out.querySelectorAll('.welcome-command')).toHaveLength(1)
    expect(out.querySelector('.welcome-hint')?.textContent).toBeTruthy()
  })

  it('runWelcome uses welcome_first_prompt_idle_ms for the first sampled command and welcome_inter_block_ms for later commands', async () => {
    const delays = []
    const { runWelcome } = loadWelcomeFns({
      welcomeData: [
        { cmd: 'ping darklab.sh', out: 'line one', group: 'basics', featured: true },
        { cmd: 'dig darklab.sh A', out: 'line two', group: 'dns' },
      ],
      hintItems: ['Hint one'],
      config: {
        welcome_char_ms: 0,
        welcome_jitter_ms: 0,
        welcome_post_cmd_ms: 0,
        welcome_inter_block_ms: 300,
        welcome_first_prompt_idle_ms: 1234,
        welcome_sample_count: 2,
        welcome_hint_rotations: 0,
        welcome_status_labels: ['READY'],
      },
      setTimeoutImpl: (fn, ms = 0) => {
        delays.push(ms)
        fn()
        return 0
      },
    })

    await runWelcome()

    expect(delays).toContain(1234)
    expect(delays).toContain(300)
  })

  it('runWelcome uses welcome_post_status_pause_ms between the status phase and first prompt', async () => {
    const delays = []
    const { runWelcome } = loadWelcomeFns({
      welcomeData: [
        { cmd: 'ping darklab.sh', out: 'line one', group: 'basics', featured: true },
      ],
      hintItems: ['Hint one'],
      config: {
        welcome_char_ms: 0,
        welcome_jitter_ms: 0,
        welcome_post_cmd_ms: 0,
        welcome_inter_block_ms: 300,
        welcome_first_prompt_idle_ms: 100,
        welcome_post_status_pause_ms: 777,
        welcome_sample_count: 1,
        welcome_hint_rotations: 0,
        welcome_status_labels: ['READY'],
      },
      setTimeoutImpl: (fn, ms = 0) => {
        delays.push(ms)
        fn()
        return 0
      },
    })

    await runWelcome()

    expect(delays).toContain(777)
  })

  it('runWelcome finalizes the typed command in place without leaving a transient live line', async () => {
    const { runWelcome, out } = loadWelcomeFns({
      welcomeData: [{ cmd: 'ping darklab.sh', out: 'line one', group: 'basics', featured: true }],
      hintItems: ['Hint one'],
    })

    await runWelcome()

    expect(out.querySelectorAll('.welcome-command')).toHaveLength(1)
    expect(out.querySelectorAll('.wlc-live')).toHaveLength(0)
    expect(out.querySelectorAll('.wlc-cursor')).toHaveLength(0)
    expect(out.querySelector('.welcome-command-comment')?.textContent).toContain('line one')
  })

  it('_sampleWelcomeBlocks prefers a featured basics command first and avoids duplicates', () => {
    const { _sampleWelcomeBlocks } = loadWelcomeFns()

    const sampled = _sampleWelcomeBlocks([
      { cmd: 'dig darklab.sh A', group: 'dns', featured: false },
      { cmd: 'ping darklab.sh', group: 'basics', featured: true },
      { cmd: 'curl -I https://darklab.sh', group: 'web', featured: false },
      { cmd: 'ping darklab.sh', group: 'basics', featured: true },
    ], 3)

    expect(sampled[0].cmd).toBe('ping darklab.sh')
    expect(sampled.map(item => item.cmd)).toEqual([
      'ping darklab.sh',
      'dig darklab.sh A',
      'curl -I https://darklab.sh',
    ])
  })

  it('uses the mobile welcome path with the mobile banner and no sample commands', async () => {
    const { runWelcome, out, apiFetch, mountShellPrompt } = loadWelcomeFns({
      mobile: true,
      mobileHintItems: ['Tap the prompt to open the mobile keyboard quickly.'],
    })

    await runWelcome()

    expect(apiFetch).toHaveBeenCalledWith('/welcome/ascii-mobile')
    expect(apiFetch).toHaveBeenCalledWith('/welcome/hints-mobile')
    expect(apiFetch).not.toHaveBeenCalledWith('/welcome')
    expect(out.querySelector('.welcome-ascii-art')?.textContent).toContain('MOBILE ASCII ART')
    expect(out.querySelectorAll('.welcome-status-loaded')).toHaveLength(5)
    expect(out.querySelectorAll('.welcome-command')).toHaveLength(0)
    expect(out.querySelector('.welcome-section-header')?.textContent).toContain('Helpful hints')
    expect(out.querySelector('.welcome-hint')?.textContent).toContain('Tap the prompt')
    expect(mountShellPrompt).toHaveBeenCalledWith('tab-1', true)
  })
})
