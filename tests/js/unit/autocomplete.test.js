import { fromDomScripts } from './helpers/extract.js'

function loadAutocompleteFns({ isActiveTabRunning = () => false } = {}) {
  const cmdInput = document.getElementById('cmd')
  const acDropdown = document.getElementById('ac')
  const mobileComposerHost = document.getElementById('mobile-composer-host')
  const mobileCmdInput = document.getElementById('mobile-cmd')

  return fromDomScripts(
    ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
    {
      document,
      cmdInput,
      acDropdown,
      mobileComposerHost,
      mobileCmdInput,
      getComposerValue: () => cmdInput.value,
      acSuggestions: [],
      acContextRegistry: {},
      acFiltered: [],
      acIndex: -1,
      acSuppressInputOnce: false,
      isActiveTabRunning,
    },
    `{
    acShow,
    acHide,
    acAccept,
    acExpandSharedPrefix,
    getAutocompleteMatches,
    limitAutocompleteMatchesForDisplay,
    rememberRecentDomainsFromCommand,
    _readRecentDomains,
    _getAutocompleteSharedPrefix: autocompleteCore.sharedPrefix,
    _setAcIndex: (value) => { acIndex = value; },
    _setAcFiltered: (value) => { acFiltered = value; },
    _getAcFiltered: () => acFiltered,
  }`,
  )
}

describe('autocomplete helpers', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <input id="cmd" />
      <div id="ac"></div>
      <div id="mobile-composer-host"></div>
      <input id="mobile-cmd" autocomplete="off" autocapitalize="none" autocorrect="off" spellcheck="false" inputmode="text" />
    `
    document.body.className = ''
    sessionStorage.clear()
  })

  it('hides the dropdown when there are no suggestions', () => {
    const { acShow } = loadAutocompleteFns()

    acShow([])

    expect(document.getElementById('ac').style.display).toBe('none')
    expect(document.getElementById('ac').children).toHaveLength(0)
  })

  it('renders suggestions and highlights the matched substring', () => {
    const { acShow } = loadAutocompleteFns()
    document.getElementById('cmd').value = 'pi'

    acShow(['ping google.com'])

    const item = document.querySelector('.ac-item')
    expect(item).not.toBeNull()
    expect(item.innerHTML).toContain('<span class="ac-match">pi</span>')
    expect(document.getElementById('ac').style.display).toBe('block')

    document.getElementById('cmd').value = 'nmp'
    acShow(['nmap'])
    expect(document.querySelector('.ac-item')?.innerHTML).toContain('<span class="ac-match">n</span>')
    expect(document.querySelector('.ac-item')?.innerHTML).toContain('<span class="ac-match">m</span>')
    expect(document.querySelector('.ac-item')?.innerHTML).toContain('<span class="ac-match">p</span>')

    document.getElementById('cmd').value = 'pign'
    acShow(['ping'])
    expect(document.querySelector('.ac-item')?.innerHTML).toContain('<span class="ac-match">p</span>')
    expect(document.querySelector('.ac-item')?.innerHTML).toContain('<span class="ac-match">i</span>')
    expect(document.querySelector('.ac-item')?.innerHTML).toContain('<span class="ac-match">n</span>')
    expect(document.querySelector('.ac-item')?.innerHTML).toContain('<span class="ac-match">g</span>')
  })

  it('renders suggestions from the shared composer value accessor when present', () => {
    document.getElementById('cmd').value = ''
    const { acShow } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'pi',
        acSuggestions: [],
        acContextRegistry: {},
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      acShow,
    }`,
    )

    acShow(['ping google.com'])

    const item = document.querySelector('.ac-item')
    expect(item.innerHTML).toContain('<span class="ac-match">pi</span>')
  })

  it('applies the active class to the indexed suggestion', () => {
    const { acShow, _setAcIndex } = loadAutocompleteFns()
    _setAcIndex(1)

    acShow(['ping', 'curl'])

    const items = document.querySelectorAll('.ac-item')
    expect(items[0].classList.contains('ac-active')).toBe(false)
    expect(items[0].classList.contains('dropdown-item')).toBe(true)
    expect(items[1].classList.contains('ac-active')).toBe(true)
    expect(items[1].classList.contains('dropdown-item-active')).toBe(true)
  })

  it('renders contextual suggestions with descriptions', () => {
    const { acShow } = loadAutocompleteFns()
    document.getElementById('cmd').value = 'nmap -'

    acShow([{ value: '-sV', description: 'Service detection', replaceStart: 5, replaceEnd: 6 }])

    const item = document.querySelector('.ac-item')
    expect(item?.querySelector('.ac-item-main')?.textContent).toBe('-sV')
    expect(item?.querySelector('.ac-item-desc')?.textContent).toBe('Service detection')
  })

  it('highlights contextual suggestions with an item-specific match query', () => {
    const { acShow } = loadAutocompleteFns()
    document.getElementById('cmd').value = 'cat darklab/find'

    acShow([{
      value: 'darklab/darklab_findings.txt',
      description: 'session file',
      replaceStart: 4,
      replaceEnd: 16,
      matchQuery: 'find',
    }])

    const item = document.querySelector('.ac-item')
    expect(item?.querySelector('.ac-item-main')?.textContent).toBe('darklab/darklab_findings.txt')
    expect(item?.innerHTML).toContain('<span class="ac-match">find</span>')
  })

  it('does not highlight typed text inside hint-only placeholders', () => {
    const input = document.getElementById('cmd')
    input.value = 'workflow run work'
    input.selectionStart = input.selectionEnd = input.value.length
    const { acShow } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: input,
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => input.value,
        getComposerState: () => ({ selectionStart: input.selectionStart }),
        acSuggestions: [],
        acContextRegistry: {},
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      acShow,
    }`,
    )

    acShow([
      { value: 'workflow-network-check', description: 'Network workflow' },
      { value: '<workflow>', description: 'Workflow name', hintOnly: true },
    ])

    const items = [...document.querySelectorAll('.ac-item')]
    expect(items[0].innerHTML).toContain('<span class="ac-match">work</span>')
    expect(items[1].querySelector('.ac-item-main')?.textContent).toBe('<workflow>')
    expect(items[1].innerHTML).not.toContain('ac-match')
    expect(items[1].classList.contains('ac-hint-only')).toBe(true)
    expect(items[1].classList.contains('ac-hint-separated')).toBe(true)
    expect(items[1].getAttribute('aria-disabled')).toBe('true')
  })

  it('honors explicit snake_case hint_only hints without placeholder autodetect', () => {
    const { getAutocompleteMatches, acAccept } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => document.getElementById('cmd').value,
        setComposerValue: (value, start, end) => {
          const input = document.getElementById('cmd')
          input.value = value
          input.selectionStart = start
          input.selectionEnd = end == null ? start : end
        },
        acSuggestions: [],
        acContextRegistry: {
          tokenctl: {
            expects_value: ['set'],
            arg_hints: {
              set: [{ value: 'token value', description: 'Paste a token', hint_only: true }],
            },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
      acAccept,
    }`,
    )

    const items = getAutocompleteMatches('tokenctl set ', 13)
    expect(items).toHaveLength(1)
    expect(items[0].value).toBe('token value')
    expect(items[0].hintOnly).toBe(true)
    expect(items[0].insertValue).toBe('')

    const input = document.getElementById('cmd')
    input.value = 'tokenctl set '
    input.selectionStart = input.selectionEnd = 13
    acAccept(items[0])
    expect(input.value).toBe('tokenctl set ')
  })

  it('acAccept updates the input, hides the dropdown, and refocuses the input', () => {
    const { acAccept } = loadAutocompleteFns()
    const input = document.getElementById('cmd')
    const focusSpy = vi.spyOn(input, 'focus')
    document.getElementById('ac').style.display = 'block'

    acAccept('nmap -sV')

    expect(input.value).toBe('nmap -sV')
    expect(document.getElementById('ac').style.display).toBe('none')
    expect(focusSpy).toHaveBeenCalledTimes(1)
  })

  it('acAccept keeps focus on the visible mobile composer when mobile mode is active', () => {
    const { acAccept } = loadAutocompleteFns()
    const desktopInput = document.getElementById('cmd')
    const mobileInput = document.getElementById('mobile-cmd')
    const mobileFocusSpy = vi.spyOn(mobileInput, 'focus')
    const desktopFocusSpy = vi.spyOn(desktopInput, 'focus')
    document.body.classList.add('mobile-terminal-mode')
    document.getElementById('ac').style.display = 'block'

    acAccept('nmap -sV')

    expect(mobileInput.value).toBe('nmap -sV')
    expect(desktopInput.value).toBe('')
    expect(document.getElementById('ac').style.display).toBe('none')
    expect(mobileFocusSpy).toHaveBeenCalledTimes(1)
    expect(desktopFocusSpy).not.toHaveBeenCalled()
  })

  it('acAccept replaces only the current token for contextual suggestions', () => {
    const { acAccept } = loadAutocompleteFns()
    const input = document.getElementById('cmd')
    input.value = 'nmap -'
    input.setSelectionRange(6, 6)

    acAccept({ value: '-sV', replaceStart: 5, replaceEnd: 6 })

    expect(input.value).toBe('nmap -sV')
  })

  it('acAccept clears stale suggestions after accepting a single contextual match', () => {
    const { acAccept, _getAcFiltered, _setAcFiltered } = loadAutocompleteFns()
    const input = document.getElementById('cmd')
    const suggestion = { value: 'naabu/', replaceStart: 3, replaceEnd: 6 }
    input.value = 'cd naa'
    input.setSelectionRange(6, 6)
    _setAcFiltered([suggestion])

    acAccept(suggestion)

    expect(input.value).toBe('cd naabu/')
    expect(_getAcFiltered()).toEqual([])
  })

  it('acAccept refreshes autocomplete after accepting a slash-terminated folder', () => {
    vi.useFakeTimers()
    try {
      const openAutocompleteForVisibleComposer = vi.fn(() => true)
      const { acAccept } = fromDomScripts(
        ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
        {
          document,
          cmdInput: document.getElementById('cmd'),
          acDropdown: document.getElementById('ac'),
          mobileComposerHost: document.getElementById('mobile-composer-host'),
          mobileCmdInput: document.getElementById('mobile-cmd'),
          getComposerValue: () => document.getElementById('cmd').value,
          setComposerValue: (value, start, end) => {
            const input = document.getElementById('cmd')
            input.value = value
            input.selectionStart = start
            input.selectionEnd = end == null ? start : end
          },
          openAutocompleteForVisibleComposer,
          acSuggestions: [],
          acContextRegistry: {},
          acFiltered: [],
          acIndex: -1,
          acSuppressInputOnce: false,
        },
        `{
        acAccept,
      }`,
      )
      const input = document.getElementById('cmd')
      input.value = 'cd naa'
      input.setSelectionRange(6, 6)

      acAccept({ value: 'naabu/', replaceStart: 3, replaceEnd: 6 })
      vi.runOnlyPendingTimers()

      expect(input.value).toBe('cd naabu/')
      expect(openAutocompleteForVisibleComposer).toHaveBeenCalledTimes(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('acAccept suppresses one synthetic input cycle so the dropdown does not immediately reopen', () => {
    const { acAccept } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => document.getElementById('cmd').value,
        setComposerValue: (value, start, end) => {
          const input = document.getElementById('cmd')
          input.value = value
          input.selectionStart = start
          input.selectionEnd = end == null ? start : end
          if (typeof acSuppressInputOnce !== 'undefined' && acSuppressInputOnce) {
            acSuppressInputOnce = false
            acHide()
          }
        },
        acSuggestions: [],
        acContextRegistry: {},
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      acAccept,
    }`,
    )

    document.getElementById('ac').style.display = 'block'
    acAccept({ value: '-sT', replaceStart: 5, replaceEnd: 6 })

    expect(document.getElementById('cmd').value).toBe('-sT')
    expect(document.getElementById('ac').style.display).toBe('none')
  })

  it('computes the shared prefix across multiple suggestions', () => {
    const { _getAutocompleteSharedPrefix } = loadAutocompleteFns()

    expect(_getAutocompleteSharedPrefix(['ping', 'ping -c 4', 'ping google.com'])).toBe('ping')
    expect(_getAutocompleteSharedPrefix(['curl', 'dig'])).toBe('')
  })

  it('expands the composer value to the longest shared prefix when one exists', () => {
    const { acExpandSharedPrefix } = loadAutocompleteFns()
    const input = document.getElementById('cmd')
    input.value = 'pi'

    const expanded = acExpandSharedPrefix(['ping', 'ping -c 4', 'ping google.com'])

    expect(expanded).toBe(true)
    expect(input.value).toBe('ping')
  })

  it('expands through the shared trailing space when suggestions only diverge after the command root', () => {
    const { acExpandSharedPrefix } = loadAutocompleteFns()
    const input = document.getElementById('cmd')
    input.value = 'ping'

    const expanded = acExpandSharedPrefix(['ping -c 4', 'ping google.com'])

    expect(expanded).toBe(true)
    expect(input.value).toBe('ping ')
  })

  it('expands example suggestions to the command root before cycling examples', () => {
    const { acExpandSharedPrefix } = loadAutocompleteFns()
    const input = document.getElementById('cmd')
    input.value = 'nsl'
    input.setSelectionRange(3, 3)

    const expanded = acExpandSharedPrefix([
      {
        value: 'nslookup darklab.sh',
        insertValue: 'nslookup darklab.sh',
        replaceStart: 0,
        replaceEnd: 3,
        isExample: true,
        completionPrefix: 'nslookup',
      },
      {
        value: 'nslookup -type=MX darklab.sh',
        insertValue: 'nslookup -type=MX darklab.sh',
        replaceStart: 0,
        replaceEnd: 3,
        isExample: true,
        completionPrefix: 'nslookup',
      },
    ])

    expect(expanded).toBe(true)
    expect(input.value).toBe('nslookup')
    expect(input.selectionStart).toBe('nslookup'.length)
  })

  it('expands the shared prefix for contextual token suggestions in place', () => {
    const { acExpandSharedPrefix } = loadAutocompleteFns()
    const input = document.getElementById('cmd')
    input.value = 'nmap -'
    input.setSelectionRange(6, 6)

    const expanded = acExpandSharedPrefix([
      { value: '-sS', replaceStart: 5, replaceEnd: 6 },
      { value: '-sV', replaceStart: 5, replaceEnd: 6 },
      { value: '-sn', replaceStart: 5, replaceEnd: 6 },
    ])

    expect(expanded).toBe(true)
    expect(input.value).toBe('nmap -s')
  })

  it('returns root-aware contextual matches and suppresses already-used flags', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'nmap -Pn -',
        acSuggestions: ['nmap -h'],
        acContextRegistry: {
          nmap: {
            flags: [
              { value: '-Pn', description: 'Skip host discovery' },
              { value: '-sV', description: 'Service detection' },
            ],
            expects_value: [],
            arg_hints: {},
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    const items = getAutocompleteMatches('nmap -Pn -', 10)
    expect(items).toHaveLength(1)
    expect(items[0].value).toBe('-sV')
  })

  it('prefers matching subcommand tokens over positional placeholders while typing', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'amass en',
        acSuggestions: [],
        acContextRegistry: {
          amass: {
            flags: [
              { value: 'enum', description: 'Enumerate attack surface assets' },
              { value: 'subs', description: 'Read discovered subdomains' },
              { value: '-d', description: 'Target domain' },
            ],
            expects_value: ['-d'],
            arg_hints: {
              __positional__: [{ value: '<domain>', hintOnly: true, description: 'Domain name' }],
            },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    const items = getAutocompleteMatches('amass en', 8)
    expect(items.map(item => item.value)).toEqual(['enum'])
    expect(items[0].hintOnly).toBe(false)
  })

  it('shows nested subcommands and root flags after a command root', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'amass ',
        acSuggestions: [],
        acContextRegistry: {
          amass: {
            flags: [{ value: '-h', description: 'Show help' }],
            expects_value: [],
            arg_hints: {
              __positional__: [
                { value: 'enum', insertValue: 'enum ', description: 'Enumerate assets' },
                { value: 'subs', insertValue: 'subs ', description: 'Read subdomains' },
              ],
            },
            subcommands: {
              enum: { flags: [{ value: '-passive', description: 'Passive mode' }] },
              subs: { flags: [{ value: '-names', description: 'Print names' }] },
            },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    expect(getAutocompleteMatches('amass ', 6).map(item => item.value)).toEqual(['-h', 'enum', 'subs'])
    expect(getAutocompleteMatches('amass nm', 8).map(item => item.value)).toEqual(['enum'])
  })

  it('shows root and subcommand examples while a unique command root is being typed', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'openssl',
        acSuggestions: [],
        acContextRegistry: {
          openssl: {
            examples: [{ value: 'openssl version', description: 'Show version' }],
            flags: [{ value: '-help', description: 'Show help' }],
            expects_value: [],
            arg_hints: { __positional__: [] },
            subcommands: {
              s_client: {
                examples: [{ value: 'openssl s_client -connect ip.darklab.sh:443', description: 'Inspect TLS' }],
                flags: [{ value: '-connect', description: 'Connect target' }],
              },
              ciphers: {
                examples: [{ value: 'openssl ciphers -v', description: 'List ciphers' }],
                flags: [{ value: '-v', description: 'Verbose' }],
              },
            },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    expect(getAutocompleteMatches('openssl', 7).map(item => item.value)).toEqual([
      'openssl version',
      'openssl s_client -connect ip.darklab.sh:443',
      'openssl ciphers -v',
    ])
  })

  it('shows scoped examples while typing a unique command root prefix', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'open',
        acSuggestions: [],
        acContextRegistry: {
          openssl: {
            examples: [],
            flags: [{ value: '-help', description: 'Show help' }],
            expects_value: [],
            arg_hints: { __positional__: [] },
            subcommands: {
              s_client: {
                examples: [{ value: 'openssl s_client -connect ip.darklab.sh:443', description: 'Inspect TLS' }],
                flags: [{ value: '-connect', description: 'Connect target' }],
              },
              ciphers: {
                examples: [{ value: 'openssl ciphers -v', description: 'List ciphers' }],
                flags: [{ value: '-v', description: 'Verbose' }],
              },
            },
          },
          oping: {
            examples: [{ value: 'oping darklab.sh', description: 'Ping host' }],
            flags: [],
            expects_value: [],
            arg_hints: {},
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    expect(getAutocompleteMatches('open', 4).map(item => item.value)).toEqual([
      'openssl s_client -connect ip.darklab.sh:443',
      'openssl ciphers -v',
    ])
    expect(getAutocompleteMatches('ssl', 3).map(item => item.value)).toEqual([
      'openssl s_client -connect ip.darklab.sh:443',
      'openssl ciphers -v',
    ])
    expect(getAutocompleteMatches('op', 2).map(item => item.value)).toEqual(['openssl', 'oping'])
  })

  it('keeps fuzzy root matches tight, supports adjacent swaps, and preserves substring matches', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        acSuggestions: [],
        acContextRegistry: {
          ping: { flags: [], expects_value: [], arg_hints: {} },
          fping: { flags: [], expects_value: [], arg_hints: {} },
          subfinder: { flags: [], expects_value: [], arg_hints: {} },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    expect(getAutocompleteMatches('png', 3).map(item => item.value)).toEqual(['ping', 'fping'])
    expect(getAutocompleteMatches('pign', 4).map(item => item.value)).toEqual(['ping', 'fping'])
    expect(getAutocompleteMatches('pngi', 4).map(item => item.value)).toEqual([])
    expect(getAutocompleteMatches('sind', 4).map(item => item.value)).toEqual([])
    expect(getAutocompleteMatches('find', 4).map(item => item.value)).toEqual(['subfinder'])
  })

  it('uses subcommand-scoped flags without leaking sibling flags', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'amass subs ',
        acSuggestions: [],
        acContextRegistry: {
          amass: {
            flags: [{ value: '-h', description: 'Show help' }],
            expects_value: [],
            arg_hints: {
              __positional__: [
                { value: 'enum', insertValue: 'enum ', description: 'Enumerate assets' },
                { value: 'subs', insertValue: 'subs ', description: 'Read subdomains' },
                { value: 'viz', insertValue: 'viz ', description: 'Visualize assets' },
              ],
            },
            subcommands: {
              enum: { flags: [{ value: '-passive', description: 'Passive mode' }] },
              subs: {
                flags: [
                  { value: '-names', description: 'Print names' },
                  { value: '-ip', description: 'Show IPs' },
                  { value: '-summary', description: 'Show summary' },
                ],
              },
              viz: { flags: [{ value: '-d3', description: 'Generate D3' }] },
            },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    const values = getAutocompleteMatches('amass subs ', 11).map(item => item.value)
    expect(values).toEqual(['-h', '-names', '-ip', '-summary'])
    expect(values).not.toContain('-passive')
    expect(values).not.toContain('-d3')
    expect(values).not.toContain('enum')
  })

  it('shows subcommand-scoped examples when a subcommand token is complete', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'amass subs',
        acSuggestions: [],
        acContextRegistry: {
          amass: {
            flags: [{ value: '-h', description: 'Show help' }],
            expects_value: [],
            arg_hints: {
              __positional__: [
                { value: 'enum', insertValue: 'enum ', description: 'Enumerate assets' },
                { value: 'subs', insertValue: 'subs ', description: 'Read subdomains' },
              ],
            },
            subcommands: {
              enum: {
                examples: [{ value: 'amass enum -d darklab.sh', description: 'Enumerate domain' }],
                flags: [{ value: '-passive', description: 'Passive mode' }],
              },
              subs: {
                examples: [
                  { value: 'amass subs -d darklab.sh -names', description: 'Print names' },
                  { value: 'amass subs -d darklab.sh -show', description: 'Show ASN data' },
                ],
                flags: [{ value: '-names', description: 'Print names' }],
              },
            },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    const items = getAutocompleteMatches('amass subs', 10)
    expect(items.map(item => item.value)).toEqual([
      'amass subs -d darklab.sh -names',
      'amass subs -d darklab.sh -show',
    ])
    expect(items.every(item => item.isExample)).toBe(true)
    expect(items[0].replaceStart).toBe(0)
    expect(items[0].replaceEnd).toBe(10)
  })

  it('shows subcommand-scoped examples when a partial subcommand uniquely matches', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'amass s',
        acSuggestions: [],
        acContextRegistry: {
          amass: {
            flags: [{ value: '-h', description: 'Show help' }],
            expects_value: [],
            arg_hints: {
              __positional__: [
                { value: 'enum', insertValue: 'enum ', description: 'Enumerate assets' },
                { value: 'subs', insertValue: 'subs ', description: 'Read subdomains' },
              ],
            },
            subcommands: {
              enum: {
                examples: [{ value: 'amass enum -d darklab.sh', description: 'Enumerate domain' }],
                flags: [{ value: '-passive', description: 'Passive mode' }],
              },
              subs: {
                examples: [
                  { value: 'amass subs -d darklab.sh -names', description: 'Print names' },
                  { value: 'amass subs -d darklab.sh -show', description: 'Show ASN data' },
                ],
                flags: [{ value: '-names', description: 'Print names' }],
              },
            },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    const items = getAutocompleteMatches('amass s', 7)
    expect(items.map(item => item.value)).toEqual([
      'amass subs -d darklab.sh -names',
      'amass subs -d darklab.sh -show',
    ])
    expect(items.every(item => item.isExample)).toBe(true)
    expect(items[0].replaceStart).toBe(0)
    expect(items[0].replaceEnd).toBe(7)
  })

  it('keeps ambiguous partial subcommands as token suggestions instead of examples', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'gobuster d',
        acSuggestions: [],
        acContextRegistry: {
          gobuster: {
            flags: [{ value: '-h', description: 'Show help' }],
            expects_value: [],
            arg_hints: {
              __positional__: [
                { value: 'dir', insertValue: 'dir ', description: 'Directory mode' },
                { value: 'dns', insertValue: 'dns ', description: 'DNS mode' },
                { value: 'vhost', insertValue: 'vhost ', description: 'Vhost mode' },
              ],
            },
            subcommands: {
              dir: {
                examples: [{ value: 'gobuster dir -u https://ip.darklab.sh -w wordlist.txt' }],
                flags: [{ value: '-u', description: 'URL' }],
              },
              dns: {
                examples: [{ value: 'gobuster dns -d darklab.sh -w subdomains.txt' }],
                flags: [{ value: '-d', description: 'Domain' }],
              },
            },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    const items = getAutocompleteMatches('gobuster d', 10)
    expect(items.map(item => item.value)).toEqual(['dir', 'dns'])
    expect(items.some(item => item.isExample)).toBe(false)
  })

  it('uses subcommand-scoped value hints', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'amass viz -o ',
        acSuggestions: [],
        acContextRegistry: {
          amass: {
            flags: [],
            expects_value: [],
            arg_hints: { __positional__: [{ value: 'viz', insertValue: 'viz ' }] },
            subcommands: {
              subs: {
                flags: [{ value: '-o', description: 'Write subs output' }],
                expects_value: ['-o'],
                arg_hints: { '-o': [{ value: 'amass-subdomains.txt', description: 'Text output' }] },
              },
              viz: {
                flags: [{ value: '-o', description: 'Write viz output' }],
                expects_value: ['-o'],
                arg_hints: { '-o': [{ value: 'amass-viz', description: 'Viz output directory' }] },
              },
            },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    expect(getAutocompleteMatches('amass viz -o ', 13).map(item => item.value)).toEqual(['amass-viz'])
  })

  it('tracks recent domains from structured flag and positional slots, capped in memory', () => {
    const { rememberRecentDomainsFromCommand, _readRecentDomains } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        SESSION_ID: 'session-a',
        acSuggestions: [],
        acContextRegistry: {
          dig: {
            flags: [
              { value: 'MX', description: 'Mail exchanger lookup' },
              { value: '@8.8.8.8', description: 'Resolver' },
            ],
            expects_value: [],
            arg_hints: { __positional__: [{ value: '<domain>', hintOnly: true, value_type: 'domain', description: 'Domain name to query' }] },
          },
          subfinder: {
            flags: [{ value: '-d', description: 'Target domain' }],
            expects_value: ['-d'],
            arg_hints: { '-d': [{ value: '<domain>', hintOnly: true, value_type: 'domain', description: 'Target domain to enumerate' }] },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      rememberRecentDomainsFromCommand,
      _readRecentDomains,
    }`,
    )

    rememberRecentDomainsFromCommand('subfinder -d Alpha.example.com -silent')
    rememberRecentDomainsFromCommand('dig MX beta.example.org +short')
    rememberRecentDomainsFromCommand('dig @8.8.8.8 gamma.example.net')
    rememberRecentDomainsFromCommand('curl https://not-a-domain-slot.example')
    for (let i = 0; i < 10; i += 1) {
      rememberRecentDomainsFromCommand(`subfinder -d d${i}.example.com`)
    }
    rememberRecentDomainsFromCommand('subfinder -d beta.example.org')

    expect(_readRecentDomains()).toEqual([
      'beta.example.org',
      'd9.example.com',
      'd8.example.com',
      'd7.example.com',
      'd6.example.com',
      'd5.example.com',
      'd4.example.com',
      'd3.example.com',
      'd2.example.com',
      'd1.example.com',
    ])
    expect(sessionStorage.getItem('recent_domains:session-a')).toBeNull()
  })

  it('loads recent domains from the session endpoint', async () => {
    const apiFetch = vi.fn(() => Promise.resolve({
      json: () => Promise.resolve({
        domains: ['Alpha.example.com.', 'https://ignored.example', 'beta.example.org'],
      }),
    }))
    const { loadRecentDomains, _readRecentDomains } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        SESSION_ID: 'session-a',
        apiFetch,
        acSuggestions: [],
        acContextRegistry: {},
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      loadRecentDomains,
      _readRecentDomains,
    }`,
    )

    await loadRecentDomains()

    expect(apiFetch).toHaveBeenCalledWith('/session/recent-domains')
    expect(_readRecentDomains()).toEqual(['alpha.example.com', 'beta.example.org'])
  })

  it('persists captured recent domains without requiring browser storage', async () => {
    const apiFetch = vi.fn(() => Promise.resolve({
      json: () => Promise.resolve({ domains: ['alpha.example.com'] }),
    }))
    const { rememberRecentDomainsFromCommand, _readRecentDomains } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        SESSION_ID: 'session-a',
        apiFetch,
        acSuggestions: [],
        acContextRegistry: {
          dig: {
            flags: [],
            expects_value: [],
            arg_hints: { __positional__: [{ value: '<domain>', hintOnly: true, value_type: 'domain', description: 'Domain name to query' }] },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      rememberRecentDomainsFromCommand,
      _readRecentDomains,
    }`,
    )

    rememberRecentDomainsFromCommand('dig Alpha.example.com')
    await Promise.resolve()
    await Promise.resolve()

    expect(apiFetch).toHaveBeenCalledWith('/session/recent-domains', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ domains: ['alpha.example.com'] }),
    }))
    expect(_readRecentDomains()).toEqual(['alpha.example.com'])
    expect(sessionStorage.getItem('recent_domains:session-a')).toBeNull()
  })

  it('suggests recent domains only inside known domain value slots', () => {
    const { getAutocompleteMatches, rememberRecentDomainsFromCommand } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        SESSION_ID: 'session-a',
        acSuggestions: [],
        acContextRegistry: {
          subfinder: {
            flags: [
              { value: '-d', description: 'Target domain' },
              { value: '-o', description: 'Output file' },
            ],
            expects_value: ['-d', '-o'],
            arg_hints: {
              '-d': [{ value: '<domain>', hintOnly: true, value_type: 'domain', description: 'Target domain to enumerate' }],
              '-o': [{ value: 'subdomains.txt', description: 'Save results' }],
            },
          },
          dig: {
            flags: [{ value: 'MX', description: 'Mail exchanger lookup' }],
            expects_value: [],
            arg_hints: { __positional__: [{ value: '<domain>', hintOnly: true, value_type: 'domain', description: 'Domain name to query' }] },
          },
          ping: {
            flags: [
              { value: '-c', description: 'Stop after count replies' },
              { value: '-i', description: 'Wait interval seconds between probes' },
            ],
            expects_value: ['-c', '-i'],
            arg_hints: {
              '-c': [{ value: '4', description: 'Send four probes' }],
              '-i': [{ value: '0.5', description: 'Half-second probe interval' }],
              __positional__: [{ value: '<host>', hintOnly: true, value_type: 'domain', description: 'Hostname or IP address to probe' }],
            },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
      rememberRecentDomainsFromCommand,
    }`,
    )

    rememberRecentDomainsFromCommand('subfinder -d alpha.example.com')
    rememberRecentDomainsFromCommand('dig beta.example.org')
    rememberRecentDomainsFromCommand('ping darklab.sh')

    expect(getAutocompleteMatches('subfinder -d ', 13).map(item => item.value)).toEqual([
      'darklab.sh',
      'beta.example.org',
      'alpha.example.com',
      '<domain>',
    ])
    expect(getAutocompleteMatches('dig MX be', 9).map(item => item.value)).toEqual(['beta.example.org', '<domain>'])
    expect(getAutocompleteMatches('ping ', 5).map(item => item.value)).toEqual([
      'darklab.sh',
      'beta.example.org',
      'alpha.example.com',
      '-c',
      '-i',
      '<host>',
    ])
    expect(getAutocompleteMatches('subfinder -o ', 13).map(item => item.value)).toEqual(['subdomains.txt'])
  })

  it('does not infer recent-domain slots from placeholder text without value_type metadata', () => {
    const { getAutocompleteMatches, rememberRecentDomainsFromCommand, _readRecentDomains } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        SESSION_ID: 'session-a',
        acSuggestions: [],
        acContextRegistry: {
          legacydig: {
            flags: [],
            expects_value: [],
            arg_hints: { __positional__: [{ value: '<domain>', hintOnly: true, description: 'Domain name to query' }] },
          },
          dig: {
            flags: [],
            expects_value: [],
            arg_hints: { __positional__: [{ value: '<domain>', hintOnly: true, value_type: 'domain', description: 'Domain name to query' }] },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
      rememberRecentDomainsFromCommand,
      _readRecentDomains,
    }`,
    )

    rememberRecentDomainsFromCommand('legacydig ignored.example.com')
    rememberRecentDomainsFromCommand('dig alpha.example.com')

    expect(_readRecentDomains()).toEqual(['alpha.example.com'])
    expect(getAutocompleteMatches('legacydig a', 11).map(item => item.value)).toEqual(['<domain>'])
    expect(getAutocompleteMatches('dig a', 5).map(item => item.value)).toEqual(['alpha.example.com', '<domain>'])
  })

  it('suggests installed wordlists only inside marked wordlist slots', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        acSuggestions: [],
        acWordlists: [
          {
            value: '/usr/share/wordlists/seclists/Discovery/DNS/subdomains-top1million-5000.txt',
            label: 'Discovery/DNS/subdomains-top1million-5000.txt',
            description: 'DNS wordlist',
            wordlist_category: 'dns',
          },
          {
            value: '/usr/share/wordlists/seclists/Discovery/Web-Content/common.txt',
            label: 'Discovery/Web-Content/common.txt',
            description: 'Web Content wordlist',
            wordlist_category: 'web-content',
          },
        ],
        acContextRegistry: {
          dnsx: {
            flags: [{ value: '-w', description: 'Wordlist' }],
            expects_value: ['-w'],
            arg_hints: {
              '-w': [{ value: '<wordlist>', hintOnly: true, value_type: 'wordlist', wordlist_category: 'dns' }],
            },
          },
          legacy: {
            flags: [{ value: '-w', description: 'Wordlist' }],
            expects_value: ['-w'],
            arg_hints: { '-w': [{ value: '<wordlist>', hintOnly: true, description: 'Wordlist path' }] },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    expect(getAutocompleteMatches('dnsx -w sub', 11).map(item => item.value)).toEqual([
      '/usr/share/wordlists/seclists/Discovery/DNS/subdomains-top1million-5000.txt',
      '<wordlist>',
    ])
    expect(getAutocompleteMatches('dnsx -w sdm', 11).map(item => item.value)).toEqual([
      '<wordlist>',
    ])
    expect(getAutocompleteMatches('legacy -w sub', 13).map(item => item.value)).toEqual(['<wordlist>'])
  })

  it('keeps workspace file hints while adding installed wordlists for wordlist slots', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getWorkspaceAutocompleteFileHints: () => [{ value: 'wordlist.txt', description: 'Session file' }],
        acSuggestions: [],
        acWordlists: [
          {
            value: '/usr/share/wordlists/seclists/Discovery/Web-Content/common.txt',
            label: 'Discovery/Web-Content/common.txt',
            description: 'Web Content wordlist',
            wordlist_category: 'web-content',
          },
        ],
        acContextRegistry: {
          gobuster: {
            flags: [{ value: '-w', description: 'Wordlist' }],
            workspace_file_flags: ['-w'],
            expects_value: ['-w'],
            arg_hints: {
              '-w': [{ value: '<wordlist>', hintOnly: true, value_type: 'wordlist', wordlist_category: 'web-content' }],
            },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    expect(getAutocompleteMatches('gobuster -w ', 12).map(item => item.value)).toEqual([
      '/usr/share/wordlists/seclists/Discovery/Web-Content/common.txt',
      'wordlist.txt',
    ])
    expect(getAutocompleteMatches('gobuster -w txt', 15).map(item => item.value)).toEqual([
      '/usr/share/wordlists/seclists/Discovery/Web-Content/common.txt',
      'wordlist.txt',
    ])
  })

  it('prefers runtime autocomplete suggestions for client-side commands', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'theme ',
        acSuggestions: [],
        acContextRegistry: {
          theme: {},
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
        getRuntimeAutocompleteItems: (ctx, buildItem) => {
          if (ctx.commandRoot !== 'theme') return []
          return [
            buildItem({
              value: 'apricot_sand',
              description: 'Apricot Sand (current)',
              replaceStart: ctx.tokenStart,
              replaceEnd: ctx.tokenEnd,
            }),
          ]
        },
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    const items = getAutocompleteMatches('theme ', 6)

    expect(items).toEqual([
      expect.objectContaining({
        value: 'apricot_sand',
        description: 'Apricot Sand (current)',
      }),
    ])
  })

  it('merges runtime autocomplete context with the YAML-loaded context registry', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'man ',
        acSuggestions: [],
        acContextRegistry: {
          curl: {
            arg_hints: {
              __positional__: [{ value: '<url>', hintOnly: true, description: 'Target URL' }],
            },
          },
        },
        getRuntimeAutocompleteContext: (baseRegistry) => ({
          status: {
            flags: [],
            expects_value: [],
            arg_hints: {},
            argument_limit: null,
            pipe_command: false,
            pipe_insert_value: '',
            pipe_label: '',
            pipe_description: '',
            examples: [],
          },
          man: {
            flags: [],
            expects_value: [],
            arg_hints: {
              __positional__: [
                { value: 'status', description: 'built-in: show status' },
                { value: Object.keys(baseRegistry)[0], description: 'curl manual page' },
              ],
            },
            argument_limit: 1,
            pipe_command: false,
            pipe_insert_value: '',
            pipe_label: '',
            pipe_description: '',
            examples: [],
          },
        }),
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    expect(getAutocompleteMatches('sta', 3).map(item => item.value)).toContain('status')
    expect(getAutocompleteMatches('curl ', 5)[0].value).toBe('<url>')
    expect(getAutocompleteMatches('man ', 4).map(item => item.value)).toEqual(['status', 'curl'])
  })

  it('uses sequence-specific runtime value hints without leaking them to sibling subcommands', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'config set line-numbers ',
        acSuggestions: [],
        acContextRegistry: {},
        getRuntimeAutocompleteContext: () => ({
          config: {
            flags: [],
            expects_value: ['get', 'set'],
            arg_hints: {
              get: [{ value: 'line-numbers', description: 'Line number mode' }],
              set: [{ value: 'line-numbers', description: 'Line number mode' }],
              __positional__: [
                { value: 'get', insertValue: 'get ', description: 'Show one value' },
                { value: 'set', insertValue: 'set ', description: 'Set one value' },
              ],
            },
            sequence_arg_hints: {
              'get line-numbers': [],
              'set line-numbers': [
                { value: 'on', description: 'Line number mode' },
                { value: 'off', description: 'Line number mode' },
              ],
            },
            argument_limit: null,
            pipe_command: false,
            pipe_insert_value: '',
            pipe_label: '',
            pipe_description: '',
            examples: [],
          },
        }),
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    expect(getAutocompleteMatches('config set line-numbers ', 24).map(item => item.value)).toEqual(['on', 'off'])
    expect(getAutocompleteMatches('config get line-numbers ', 24)).toEqual([])
  })

  it('stops suggesting var subcommands after a complete var command shape', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => '',
        acSuggestions: [],
        acContextRegistry: {},
        getRuntimeAutocompleteContext: () => ({
          var: {
            flags: [],
            expects_value: ['set', 'unset'],
            arg_hints: {
              list: [],
              set: [
                { value: 'HOST', description: 'Common target host' },
                { value: 'PORT', description: 'Common target port' },
              ],
              unset: [
                { value: 'HOST', description: 'Current value: ip.darklab.sh' },
              ],
              __positional__: [
                { value: 'list', insertValue: 'list', description: 'Show session variables' },
                { value: 'set', insertValue: 'set ', description: 'Set a session variable' },
                { value: 'unset', insertValue: 'unset ', description: 'Remove a session variable' },
              ],
            },
            sequence_arg_hints: {
              'set host': [{ value: '<value>', hintOnly: true, description: 'Value for HOST' }],
              'unset host': [],
            },
            close_after: { list: 0, set: 2, unset: 1 },
            argument_limit: null,
            pipe_command: false,
            pipe_insert_value: '',
            pipe_label: '',
            pipe_description: '',
            examples: [],
          },
        }),
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    expect(getAutocompleteMatches('var ', 4).map(item => item.value)).toEqual(['list', 'set', 'unset'])
    expect(getAutocompleteMatches('var set ', 8).map(item => item.value)).toEqual(['HOST', 'PORT'])
    expect(getAutocompleteMatches('var set HOST ', 13).map(item => item.value)).toEqual(['<value>'])
    expect(getAutocompleteMatches('var set HOST ip.darklab.sh ', 27)).toEqual([])
    expect(getAutocompleteMatches('var list ', 9)).toEqual([])
    expect(getAutocompleteMatches('var unset HOST ', 15)).toEqual([])
  })

  it('keeps an exact single flag match visible so its description is still shown', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'curl -w',
        acSuggestions: [],
        acContextRegistry: {
          curl: {
            flags: [
              { value: '-w', description: 'Write selected metadata after the transfer' },
            ],
            expects_value: ['-w'],
            arg_hints: {
              '-w': [{ value: '"%{http_code}"', description: 'Print the final HTTP status code' }],
            },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    const items = getAutocompleteMatches('curl -w', 7)
    expect(items).toHaveLength(1)
    expect(items[0].value).toBe('-w')
    expect(items[0].description).toBe('Write selected metadata after the transfer')
  })

  it('still collapses an exact single non-flag match', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'ping',
        acSuggestions: ['ping'],
        acContextRegistry: {},
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    expect(getAutocompleteMatches('ping', 4)).toEqual([])
  })

  it('shows positional hints alongside flag hints at command-root whitespace', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'nmap ',
        acSuggestions: ['nmap -h'],
        acContextRegistry: {
          nmap: {
            flags: [
              { value: '-sV', description: 'Service detection' },
              { value: '-Pn', description: 'Skip host discovery' },
            ],
            expects_value: [],
            arg_hints: {
              __positional__: [{ value: '<target>', hintOnly: true, description: 'Hostname, IP, or CIDR' }],
            },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    const items = getAutocompleteMatches('nmap ', 5)
    expect(items.map((item) => item.value)).toEqual(['-sV', '-Pn', '<target>'])
    expect(items[2].description).toBe('Hostname, IP, or CIDR')
    // <target> is a display-only placeholder — it has no real insertValue and
    // is flagged hintOnly so Tab cannot drop the literal "<target>" into the
    // prompt.
    expect(items[2].hintOnly).toBe(true)
    expect(items[2].insertValue).toBe('')
  })

  it('keeps positional hints visible when the displayed autocomplete list is capped', () => {
    const { getAutocompleteMatches, limitAutocompleteMatchesForDisplay } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'nmap ',
        acSuggestions: [],
        acContextRegistry: {
          nmap: {
            flags: Array.from({ length: 12 }, (_, index) => ({
              value: `-f${index}`,
              description: `Flag ${index}`,
            })),
            expects_value: [],
            arg_hints: {
              __positional__: [{ value: '<target>', hintOnly: true, description: 'Hostname, IP, or CIDR' }],
            },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
      limitAutocompleteMatchesForDisplay,
    }`,
    )

    const items = getAutocompleteMatches('nmap ', 5)
    expect(items.map((item) => item.value)).toContain('<target>')

    const visible = limitAutocompleteMatchesForDisplay(items, 12)
    expect(visible).toHaveLength(12)
    expect(visible.map((item) => item.value)).toContain('<target>')
    expect(visible[11].value).toBe('<target>')
    expect(visible[11].hintOnly).toBe(true)
  })

  it('marks <placeholder> arg_hints as hintOnly and preserves insertValue whitespace', () => {
    const { getAutocompleteMatches, acAccept } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => document.getElementById('cmd').value,
        setComposerValue: (v, s, e) => {
          const i = document.getElementById('cmd')
          i.value = v
          i.selectionStart = s
          i.selectionEnd = e == null ? s : e
        },
        acSuggestions: [],
        acContextRegistry: {
          'session-token': {
            expects_value: ['set'],
            arg_hints: {
              set: [{ value: '<token>', hintOnly: true, description: 'Paste a token' }],
              __positional__: [
                { value: 'generate' },
                { value: 'set <token>', insertValue: 'set ' },
                { value: 'copy' },
                { value: 'clear' },
              ],
            },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
      acAccept,
    }`,
    )

    // After "session-token se", the single positional match has
    // insertValue: "set " — the trailing space must survive insertion so the
    // cursor lands after the space, ready for the token argument.
    const seMatches = getAutocompleteMatches('session-token se', 16)
    expect(seMatches).toHaveLength(1)
    expect(seMatches[0].value).toBe('set <token>')
    expect(seMatches[0].insertValue).toBe('set ')
    expect(seMatches[0].hintOnly).toBe(false)

    // After "session-token set ", the <token> arg_hint is shown as a display-only
    // hint — hintOnly:true, insertValue:'' — so Tab cannot insert the literal
    // "<token>" text.
    const afterSet = getAutocompleteMatches('session-token set ', 18)
    expect(afterSet).toHaveLength(1)
    expect(afterSet[0].value).toBe('<token>')
    expect(afterSet[0].hintOnly).toBe(true)
    expect(afterSet[0].insertValue).toBe('')

    // acAccept on a hintOnly item must leave the input unchanged.
    const cmd = document.getElementById('cmd')
    cmd.value = 'session-token set '
    cmd.selectionStart = cmd.selectionEnd = 18
    acAccept(afterSet[0])
    expect(cmd.value).toBe('session-token set ')
  })

  it('keeps direct placeholder hints visible while typing the argument value', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'session-token set abc',
        acSuggestions: [],
        acContextRegistry: {
          'session-token': {
            expects_value: ['set'],
            arg_hints: {
              set: [{ value: '<token>', hintOnly: true, description: 'Paste a token' }],
              __positional__: [{ value: 'set <token>', insertValue: 'set ' }],
            },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    const items = getAutocompleteMatches('session-token set abc', 21)
    expect(items).toHaveLength(1)
    expect(items[0].value).toBe('<token>')
    expect(items[0].hintOnly).toBe(true)
  })

  it('returns value hints after a value-taking flag and trailing space', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'curl -o ',
        acSuggestions: ['curl -I https://darklab.sh'],
        acContextRegistry: {
          curl: {
            flags: [{ value: '-o', description: 'Write output to file' }],
            expects_value: ['-o'],
            arg_hints: {
              '-o': [{ value: '/dev/null', description: 'Discard body output' }],
            },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    const items = getAutocompleteMatches('curl -o ', 8)
    expect(items.map((item) => item.value)).toEqual(['/dev/null'])
    expect(items[0].description).toBe('Discard body output')
  })

  it('keeps placeholder guidance after concrete value hints and preserves ordering', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'curl -o ',
        acSuggestions: [],
        acContextRegistry: {
          curl: {
            flags: [{ value: '-o', description: 'Write output to file' }],
            expects_value: ['-o'],
            arg_hints: {
              '-o': [
                { value: '/dev/null', description: 'Discard body output' },
                { value: '<file>', hintOnly: true, description: 'Destination file path' },
              ],
            },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    const items = getAutocompleteMatches('curl -o ', 8)
    expect(items.map((item) => item.value)).toEqual(['/dev/null', '<file>'])
    expect(items[0].hintOnly).toBe(false)
    expect(items[1].hintOnly).toBe(true)
  })

  it('keeps positional placeholder hints visible while typing the argument value', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'ping -c 4 darklab.sh',
        acSuggestions: [],
        acContextRegistry: {
          ping: {
            flags: [
              { value: '-c', description: 'Stop after count replies' },
              { value: '-i', description: 'Wait interval seconds between probes' },
            ],
            expects_value: ['-c', '-i'],
            arg_hints: {
              '-c': [{ value: '4', description: 'Send four probes' }],
              __positional__: [{ value: '<host>', hintOnly: true, description: 'Hostname or IP address to probe' }],
            },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    const items = getAutocompleteMatches('ping -c 4 darklab.sh', 20)
    expect(items).toHaveLength(1)
    expect(items[0].value).toBe('<host>')
    expect(items[0].hintOnly).toBe(true)
  })

  it('drops positional placeholder guidance once the token context changes to a new flag slot', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'ping -c 4 -',
        acSuggestions: [],
        acContextRegistry: {
          ping: {
            flags: [
              { value: '-c', description: 'Stop after count replies' },
              { value: '-i', description: 'Wait interval seconds between probes' },
            ],
            expects_value: ['-c', '-i'],
            arg_hints: {
              '-c': [{ value: '4', description: 'Send four probes' }],
              __positional__: [{ value: '<host>', hintOnly: true, description: 'Hostname or IP address to probe' }],
            },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    const items = getAutocompleteMatches('ping -c 4 -', 11)
    expect(items.map((item) => item.value)).toEqual(['-i'])
  })

  it('shows starter values together with placeholders and then leaves only the placeholder while typing', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'curl ',
        acSuggestions: [],
        acContextRegistry: {
          curl: {
            arg_hints: {
              __positional__: [
                { value: 'https://', description: 'Start an HTTP or HTTPS URL' },
                { value: '<url>', hintOnly: true, description: 'Target URL to request' },
              ],
            },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    const rootItems = getAutocompleteMatches('curl ', 5)
    expect(rootItems.map((item) => item.value)).toEqual(['https://', '<url>'])

    const typingItems = getAutocompleteMatches('curl https://ex', 15)
    expect(typingItems).toHaveLength(1)
    expect(typingItems[0].value).toBe('<url>')
    expect(typingItems[0].hintOnly).toBe(true)
  })

  it('stops suggesting more positional arguments after reaching argument_limit, but still allows flags', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'man curl ',
        acSuggestions: [],
        acContextRegistry: {
          man: {
            argument_limit: 1,
            arg_hints: {
              __positional__: [
                { value: 'curl', description: 'curl manual page' },
                { value: '<command>', hintOnly: true, description: 'Manual page for any allowed command' },
              ],
            },
          },
          ping: {
            argument_limit: 1,
            flags: [{ value: '-c', description: 'Stop after count replies' }],
            arg_hints: {
              __positional__: [{ value: '<host>', hintOnly: true, description: 'Hostname or IP address to probe' }],
            },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    expect(getAutocompleteMatches('man curl ', 9)).toEqual([])

    const flagItems = getAutocompleteMatches('ping darklab.sh -', 16)
    expect(flagItems).toHaveLength(1)
    expect(flagItems[0].value).toBe('-c')
  })

  it('suggests built-in pipe commands after a supported command pipe', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'help | ',
        acSuggestions: [],
        acContextRegistry: {
          grep: { pipe_command: true, pipe_description: 'Filter lines by pattern' },
          head: { pipe_command: true, pipe_description: 'Show the first lines' },
          tail: { pipe_command: true, pipe_description: 'Show the last lines' },
          wc: {
            pipe_command: true,
            pipe_insert_value: 'wc -l',
            pipe_label: 'wc -l',
            pipe_description: 'Count lines',
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    const items = getAutocompleteMatches('help | ', 7)
    expect(items.map((item) => item.value)).toEqual(['grep', 'head', 'tail', 'wc -l'])
    expect(items[3].description).toBe('Count lines')
  })

  it('uses live workspace file hints for workspace read flags instead of static examples', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'nmap -iL ',
        acSuggestions: [],
        acContextRegistry: {
          nmap: {
            flags: [{ value: '-iL', description: 'Read targets from a session file' }],
            expects_value: ['-iL'],
            workspace_file_flags: ['-iL'],
            arg_hints: {
              '-iL': [{ value: 'targets.txt', description: 'Static registry example' }],
            },
          },
        },
        getWorkspaceAutocompleteFileHints: () => [
          { value: 'inputs.txt', description: 'session file · 42 B' },
        ],
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    const items = getAutocompleteMatches('nmap -iL ', 10)

    expect(items.map(item => item.value)).toEqual(['inputs.txt'])
    expect(items[0].description).toBe('session file · 42 B')
  })

  it('uses cwd-relative workspace file hints for external workspace read flags', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'nmap -iL ',
        acSuggestions: [],
        acContextRegistry: {
          nmap: {
            flags: [{ value: '-iL', description: 'Read targets from a session file' }],
            expects_value: ['-iL'],
            workspace_file_flags: ['-iL'],
            arg_hints: {
              '-iL': [{ value: 'root-targets.txt', description: 'Static registry example' }],
            },
          },
        },
        getWorkspaceAutocompleteFlagFileHints: token => (
          String(token || '').includes('/')
            ? [{ value: 'nested/targets.txt', description: 'session file · 24 B' }]
            : [
                { value: 'targets.txt', description: 'session file · 42 B' },
                { value: 'nested/', description: 'session folder' },
              ]
        ),
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    expect(getAutocompleteMatches('nmap -iL ', 10).map(item => item.value)).toEqual(['targets.txt', 'nested/'])
    expect(getAutocompleteMatches('nmap -iL nested/', 17).map(item => item.value)).toEqual(['nested/targets.txt'])
  })

  it('uses directory-aware workspace path hints for typed file-command prefixes', () => {
    const pathHints = {
      'file:darklab/': [
        { value: 'darklab/targets.txt', description: 'session file · 11 B' },
      ],
      'file:../': [
        { value: '../root.txt', description: 'session file · 1 B' },
      ],
      'file:../darklab/': [
        { value: '../darklab/targets.txt', description: 'session file · 11 B' },
        { value: '../darklab/nested/', description: 'session folder' },
      ],
      'file:darklab/find': [
        { value: 'darklab/darklab_findings.txt', description: 'session file · 42 B' },
        { value: 'darklab/targets.txt', description: 'session file · 11 B' },
      ],
      'directory:darklab/': [
        { value: 'darklab/nested/', description: 'session folder' },
      ],
      'any:darklab/': [
        { value: 'darklab/targets.txt', description: 'session file · 11 B' },
        { value: 'darklab/nested/', description: 'session folder' },
      ],
      'directory:../': [
        { value: '../archive/', description: 'session folder' },
      ],
    }
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => '',
        acSuggestions: [],
        acContextRegistry: {
          cat: {
            argument_limit: 1,
            arg_hints: { __positional__: [{ value: 'root.txt', description: 'session file · 1 B' }] },
            workspace_path_arg_kinds: { __positional__: ['file'] },
          },
          ls: {
            argument_limit: 1,
            arg_hints: { __positional__: [{ value: 'darklab', description: 'session folder' }] },
            workspace_path_arg_kinds: { __positional__: ['directory'] },
          },
          mv: {
            argument_limit: 2,
            arg_hints: {
              __positional__: [
                { value: '<source> <destination>', hintOnly: true, value_type: 'target', description: 'Session file or folder path' },
                { value: 'root.txt', description: 'session file · 1 B' },
              ],
            },
            workspace_path_arg_kinds: { __positional__: ['any', 'directory'] },
          },
          file: {
            expects_value: ['show', 'move'],
            arg_hints: {
              show: [{ value: 'root.txt', description: 'session file · 1 B' }],
              move: [{ value: 'root.txt', description: 'session file · 1 B' }],
            },
            workspace_path_arg_kinds: {
              show: ['file'],
              move: ['any', 'directory'],
            },
          },
        },
        getWorkspaceAutocompletePathHints: (kind, token) => pathHints[`${kind}:${token}`] || [],
        getWorkspaceAutocompleteFileHints: () => [
          { value: 'deep/from-root.txt', description: 'session file · 99 B' },
        ],
        getWorkspaceAutocompleteDirectoryHints: () => [
          { value: 'deep', description: 'session folder' },
        ],
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    expect(getAutocompleteMatches('cat darklab/', 12).map(item => item.value)).toEqual(['darklab/targets.txt'])
    expect(getAutocompleteMatches('cat darklab/find', 16).map(item => item.value)).toEqual(['darklab/darklab_findings.txt'])
    expect(getAutocompleteMatches('cat ../', 7).map(item => item.value)).toEqual(['../root.txt'])
    expect(getAutocompleteMatches('cat ../darklab/', 16).map(item => item.value)).toEqual(['../darklab/targets.txt', '../darklab/nested/'])
    expect(getAutocompleteMatches('ls darklab/', 11).map(item => item.value)).toEqual(['darklab/nested/'])
    expect(getAutocompleteMatches('mv ', 3).map(item => item.value)).toContain('root.txt')
    expect(getAutocompleteMatches('mv ', 3).map(item => item.value)).not.toContain('deep/from-root.txt')
    expect(getAutocompleteMatches('mv darklab/', 11).map(item => item.value)).toEqual(['darklab/targets.txt', 'darklab/nested/'])
    expect(getAutocompleteMatches('mv root.txt ../', 14).map(item => item.value)).toEqual(['../archive/'])
    expect(getAutocompleteMatches('file show darklab/', 18).map(item => item.value)).toEqual(['darklab/targets.txt'])
    expect(getAutocompleteMatches('file move root.txt ../', 22).map(item => item.value)).toEqual(['../archive/'])
  })

  it('returns pipe-stage flag hints for grep', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'help | grep -',
        acSuggestions: [],
        acContextRegistry: {
          grep: {
            pipe_command: true,
            flags: [
              { value: '-i', description: 'Ignore case' },
              { value: '-v', description: 'Invert match' },
              { value: '-E', description: 'Extended regex' },
            ],
            arg_hints: {
              __positional__: [{ value: '<pattern>', hintOnly: true, description: 'Text or regex to match' }],
            },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    const items = getAutocompleteMatches('help | grep -', 13)
    expect(items.map((item) => item.value)).toEqual(['-i', '-v', '-E'])
  })

  it('returns pipe-stage count hints after head -n and wc flag hints after wc space', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'help | head -n ',
        acSuggestions: [],
        acContextRegistry: {
          head: {
            pipe_command: true,
            flags: [{ value: '-n', description: 'Show the first N lines' }],
            expects_value: ['-n'],
            arg_hints: {
              '-n': [
                { value: '5', description: 'Show the first 5 lines' },
                { value: '10', description: 'Show the first 10 lines' },
              ],
            },
          },
          wc: {
            pipe_command: true,
            pipe_insert_value: 'wc -l',
            pipe_label: 'wc -l',
            pipe_description: 'Count lines',
            flags: [{ value: '-l', description: 'Count lines' }],
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    const headItems = getAutocompleteMatches('help | head -n ', 16)
    expect(headItems.map((item) => item.value)).toEqual(['5', '10'])

    const wcItems = getAutocompleteMatches('help | wc ', 10)
    expect(wcItems.map((item) => item.value)).toEqual(['-l'])
  })

  it('suggests additional pipe helpers after an earlier helper stage', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'help | grep ttl | ',
        acSuggestions: [],
        acContextRegistry: {
          grep: { pipe_command: true, pipe_description: 'Filter lines by pattern' },
          head: { pipe_command: true, pipe_description: 'Show the first lines' },
          tail: { pipe_command: true, pipe_description: 'Show the last lines' },
          wc: {
            pipe_command: true,
            pipe_insert_value: 'wc -l',
            pipe_label: 'wc -l',
            pipe_description: 'Count lines',
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    const items = getAutocompleteMatches('help | grep ttl | ', 18)
    expect(items.map((item) => item.value)).toEqual(['grep', 'head', 'tail', 'wc -l'])
  })

  it('returns chained pipe-stage flag and value hints from the last helper stage', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'help | grep ttl | head -n ',
        acSuggestions: [],
        acContextRegistry: {
          grep: {
            pipe_command: true,
            arg_hints: {
              __positional__: [{ value: '<pattern>', hintOnly: true, description: 'Text or regex to match' }],
            },
          },
          head: {
            pipe_command: true,
            flags: [{ value: '-n', description: 'Show the first N lines' }],
            expects_value: ['-n'],
            arg_hints: {
              '-n': [
                { value: '5', description: 'Show the first 5 lines' },
                { value: '10', description: 'Show the first 10 lines' },
              ],
            },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    const flagItems = getAutocompleteMatches('help | grep ttl | head -', 25)
    expect(flagItems.map((item) => item.value)).toEqual(['-n'])

    const valueItems = getAutocompleteMatches('help | grep ttl | head -n ', 27)
    expect(valueItems.map((item) => item.value)).toEqual(['5', '10'])
  })

  it('does not offer chained pipe autocomplete after an invalid earlier stage', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete_core.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'help | cat | ',
        acSuggestions: [],
        acContextRegistry: {
          grep: { pipe_command: true, pipe_description: 'Filter lines by pattern' },
          head: { pipe_command: true, pipe_description: 'Show the first lines' },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
    }`,
    )

    expect(getAutocompleteMatches('help | cat | ', 13)).toEqual([])
  })

  it('mousedown on a suggestion accepts it without blurring the input', () => {
    const { acShow } = loadAutocompleteFns()
    const input = document.getElementById('cmd')
    const focusSpy = vi.spyOn(input, 'focus')

    acShow(['whois darklab.sh'])
    document.querySelector('.ac-item').dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))

    expect(input.value).toBe('whois darklab.sh')
    expect(document.getElementById('ac').style.display).toBe('none')
    expect(focusSpy).toHaveBeenCalled()
  })

  it('mousedown on a hint-only item keeps the guidance visible without accepting it', () => {
    const { acShow } = loadAutocompleteFns()
    const input = document.getElementById('cmd')
    input.value = 'curl -o '
    input.setSelectionRange(input.value.length, input.value.length)

    acShow([
      { value: '/dev/null', description: 'Discard body output' },
      { value: '<file>', hintOnly: true, description: 'Destination file path' },
    ])

    const hint = [...document.querySelectorAll('.ac-item')].find(
      item => item.textContent.includes('<file>'),
    )
    hint.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }))

    expect(input.value).toBe('curl -o ')
    expect(document.getElementById('ac').style.display).toBe('block')
  })

  it('does not render suggestions while the active tab is running', () => {
    const { acShow } = loadAutocompleteFns({ isActiveTabRunning: () => true })

    acShow(['whois darklab.sh'])

    expect(document.getElementById('ac').style.display).toBe('none')
    expect(document.querySelector('.ac-item')).toBeNull()
  })

  it('positions dropdown above when space below is tight and preserves item order', () => {
    const { acShow } = loadAutocompleteFns()
    const input = document.getElementById('cmd')
    input.value = 'n'
    const wrap = document.createElement('div')
    wrap.className = 'shell-prompt-wrap'
    wrap.appendChild(document.getElementById('ac'))
    document.body.appendChild(wrap)

    const prefix = document.createElement('span')
    prefix.className = 'prompt-prefix'
    prefix.textContent = 'anon@darklab:~$'
    wrap.insertBefore(prefix, document.getElementById('ac'))

    vi.spyOn(prefix, 'getBoundingClientRect').mockReturnValue({ width: 100 })
    vi.spyOn(wrap, 'getBoundingClientRect').mockReturnValue({
      top: 260,
      bottom: 295,
      left: 0,
      right: 0,
      width: 0,
      height: 0,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    })
    Object.defineProperty(window, 'innerHeight', { value: 300, configurable: true })

    acShow(['nmap -sV', 'nslookup darklab.sh'])

    expect(document.getElementById('ac').classList.contains('ac-up')).toBe(true)
    expect(document.getElementById('ac').style.top).toBe('auto')
    expect(document.getElementById('ac').style.bottom).toBe('42px')
    const items = [...document.querySelectorAll('.ac-item')].map((el) => el.textContent.trim())
    expect(items[0]).toBe('nmap -sV')
    expect(items[1]).toBe('nslookup darklab.sh')
  })

  it('keeps the above-mode dropdown pinned to the prompt as the item count shrinks', () => {
    const { acShow } = loadAutocompleteFns()
    const input = document.getElementById('cmd')
    input.value = 'n'
    const wrap = document.createElement('div')
    wrap.className = 'shell-prompt-wrap'
    wrap.appendChild(document.getElementById('ac'))
    document.body.appendChild(wrap)

    const prefix = document.createElement('span')
    prefix.className = 'prompt-prefix'
    prefix.textContent = 'anon@darklab:~$'
    wrap.insertBefore(prefix, document.getElementById('ac'))

    vi.spyOn(prefix, 'getBoundingClientRect').mockReturnValue({ width: 100 })
    vi.spyOn(wrap, 'getBoundingClientRect').mockReturnValue({
      top: 260,
      bottom: 295,
      left: 0,
      right: 0,
      width: 0,
      height: 0,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    })
    Object.defineProperty(window, 'innerHeight', { value: 300, configurable: true })

    acShow(['nmap -sV', 'nslookup darklab.sh', 'netstat -an'])
    const dropdown = document.getElementById('ac')
    expect(dropdown.style.bottom).toBe('42px')

    acShow(['nmap -sV'])
    expect(dropdown.classList.contains('ac-up')).toBe(true)
    expect(dropdown.style.top).toBe('auto')
    expect(dropdown.style.bottom).toBe('42px')
  })

  it('clamps the below-mode dropdown height so it does not extend past the viewport edge', () => {
    const { acShow } = loadAutocompleteFns()
    const input = document.getElementById('cmd')
    input.value = 'c'
    const wrap = document.createElement('div')
    wrap.className = 'shell-prompt-wrap'
    wrap.appendChild(document.getElementById('ac'))
    document.body.appendChild(wrap)

    const prefix = document.createElement('span')
    prefix.className = 'prompt-prefix'
    prefix.textContent = 'anon@darklab:~$'
    wrap.insertBefore(prefix, document.getElementById('ac'))

    vi.spyOn(prefix, 'getBoundingClientRect').mockReturnValue({ width: 100 })
    vi.spyOn(wrap, 'getBoundingClientRect').mockReturnValue({
      top: 12,
      bottom: 40,
      left: 0,
      right: 0,
      width: 0,
      height: 0,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    })
    Object.defineProperty(window, 'innerHeight', { value: 180, configurable: true })

    acShow([
      'clear',
      'curl http://localhost:5001/health',
      'curl http://localhost:5001/config',
      'cat /etc/hosts',
    ])

    const dropdown = document.getElementById('ac')
    expect(dropdown.style.position).toBe('fixed')
    expect(dropdown.classList.contains('ac-up')).toBe(false)
    expect(Number.parseInt(dropdown.style.top, 10)).toBe(42)
    expect(Number.parseInt(dropdown.style.maxHeight, 10)).toBeLessThanOrEqual(120)
  })

  it('does not auto-highlight any item when the menu opens above (same as below)', () => {
    const { acShow } = loadAutocompleteFns()
    const input = document.getElementById('cmd')
    input.value = 'n'
    const wrap = document.createElement('div')
    wrap.className = 'shell-prompt-wrap'
    wrap.appendChild(document.getElementById('ac'))
    document.body.appendChild(wrap)

    const prefix = document.createElement('span')
    prefix.className = 'prompt-prefix'
    prefix.textContent = 'anon@darklab:~$'
    wrap.insertBefore(prefix, document.getElementById('ac'))

    vi.spyOn(prefix, 'getBoundingClientRect').mockReturnValue({ width: 100 })
    vi.spyOn(wrap, 'getBoundingClientRect').mockReturnValue({
      top: 240,
      bottom: 280,
      left: 0,
      right: 0,
      width: 0,
      height: 0,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    })
    Object.defineProperty(window, 'innerHeight', { value: 300, configurable: true })

    acShow(['nmap -sV', 'nslookup darklab.sh', 'netstat -an'])

    expect(document.getElementById('ac').classList.contains('ac-up')).toBe(true)
    // No item should be highlighted on open — same behavior as below-the-prompt mode
    expect(document.querySelectorAll('.ac-item.ac-active')).toHaveLength(0)
    // First item in the original list is at the top
    const items = [...document.querySelectorAll('.ac-item')]
    expect(items[0].textContent.trim()).toBe('nmap -sV')
  })

  it('forces the dropdown above the detached mobile composer and aligns it to the composer width', () => {
    const { acShow } = loadAutocompleteFns()
    const input = document.getElementById('cmd')
    input.value = 'c'
    document.body.classList.add('mobile-terminal-mode', 'mobile-keyboard-open')
    const composerHost = document.createElement('div')
    composerHost.id = 'mobile-composer-host'
    document.body.appendChild(composerHost)
    const wrap = document.createElement('div')
    wrap.className = 'shell-prompt-wrap'
    wrap.appendChild(document.getElementById('ac'))
    composerHost.appendChild(wrap)

    const prefix = document.createElement('span')
    prefix.className = 'prompt-prefix'
    prefix.textContent = '$'
    wrap.insertBefore(prefix, document.getElementById('ac'))

    vi.spyOn(composerHost, 'getBoundingClientRect').mockReturnValue({
      top: 560,
      bottom: 612,
      left: 14,
      right: 361,
      width: 347,
      height: 56,
      x: 14,
      y: 560,
      toJSON: () => ({}),
    })
    Object.defineProperty(window, 'innerHeight', { value: 812, configurable: true })

    acShow(['curl http://localhost:5001/health', 'curl http://localhost:5001/config'])

    const dropdown = document.getElementById('ac')
    expect(dropdown.classList.contains('ac-up')).toBe(true)
    expect(dropdown.classList.contains('ac-mobile')).toBe(true)
    expect(dropdown.style.position).toBe('absolute')
    expect(dropdown.style.left).toBe('0px')
    expect(dropdown.style.right).toBe('0px')
    expect(dropdown.style.bottom).toBe('calc(100% + 4px)')
  })

  it('keeps the active autocomplete item in view as the highlighted option moves', () => {
    const { acShow, _setAcIndex } = loadAutocompleteFns()
    const input = document.getElementById('cmd')
    input.value = 'c'
    const wrap = document.createElement('div')
    wrap.className = 'shell-prompt-wrap'
    wrap.appendChild(document.getElementById('ac'))
    document.body.appendChild(wrap)

    const prefix = document.createElement('span')
    prefix.className = 'prompt-prefix'
    prefix.textContent = 'anon@darklab:~$'
    wrap.insertBefore(prefix, document.getElementById('ac'))

    vi.spyOn(prefix, 'getBoundingClientRect').mockReturnValue({ width: 100 })
    vi.spyOn(wrap, 'getBoundingClientRect').mockReturnValue({
      top: 220,
      bottom: 270,
      left: 0,
      right: 0,
      width: 0,
      height: 0,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    })
    Object.defineProperty(window, 'innerHeight', { value: 300, configurable: true })

    const dropdown = document.getElementById('ac')
    Object.defineProperty(dropdown, 'clientHeight', { configurable: true, get: () => 44 })
    Object.defineProperty(dropdown, 'scrollHeight', { configurable: true, get: () => 88 })

    const offsetMap = new Map([
      ['clear', 0],
      ['curl http://localhost:5001/health', 22],
      ['curl http://localhost:5001/config', 44],
      ['cat /etc/hosts', 66],
    ])
    const originalOffsetTop = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetTop')
    const originalOffsetHeight = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      'offsetHeight',
    )
    Object.defineProperty(HTMLElement.prototype, 'offsetTop', {
      configurable: true,
      get() {
        return offsetMap.get(this.textContent.trim()) ?? 0
      },
    })
    Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
      configurable: true,
      get() {
        return 22
      },
    })

    try {
      // No active item on first open — no scroll
      acShow([
        'clear',
        'curl http://localhost:5001/health',
        'curl http://localhost:5001/config',
        'cat /etc/hosts',
      ])
      expect(dropdown.scrollTop).toBe(0)
      expect(document.querySelector('.ac-item.ac-active')).toBeNull()

      // After selecting index 2 ('curl config' at offsetTop 44), scroll brings it into view
      _setAcIndex(2)
      acShow([
        'clear',
        'curl http://localhost:5001/health',
        'curl http://localhost:5001/config',
        'cat /etc/hosts',
      ])
      expect(document.querySelector('.ac-item.ac-active')?.textContent.trim()).toBe(
        'curl http://localhost:5001/config',
      )
      expect(dropdown.scrollTop).toBe(26)
    } finally {
      if (originalOffsetTop)
        Object.defineProperty(HTMLElement.prototype, 'offsetTop', originalOffsetTop)
      if (originalOffsetHeight)
        Object.defineProperty(HTMLElement.prototype, 'offsetHeight', originalOffsetHeight)
    }
  })
})
