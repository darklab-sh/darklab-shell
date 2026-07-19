// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { fromDomScripts } from './helpers/extract.js'

function loadAutocompleteFns({ isActiveTabRunning = () => false } = {}) {
  const cmdInput = document.getElementById('cmd')
  const acDropdown = document.getElementById('ac')
  const mobileComposerHost = document.getElementById('mobile-composer-host')
  const mobileCmdInput = document.getElementById('mobile-cmd')

  return fromDomScripts(
    ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
    rememberRecentValuesFromCommand,
    _readRecentValues,
    _getAutocompleteSharedPrefix: autocompleteCore.sharedPrefix,
    _setAcIndex: (value) => {
      acIndex = value;
      if (typeof setAutocompleteState === 'function') setAutocompleteState({ index: value });
    },
    _setAcFiltered: (value) => {
      acFiltered = value;
      if (typeof setAutocompleteState === 'function') setAutocompleteState({ filtered: value });
    },
    _getAcFiltered: () => (typeof getAutocompleteState === 'function' ? getAutocompleteState().filtered : acFiltered),
  }`,
  )
}

describe('autocomplete helpers', () => {
  beforeEach(() => {
    ;[
      '_runtimeHint',
      '_runtimePlaceholderHint',
      '_runtimeContextSpec',
      'isWorkspaceFeatureEnabled',
      'isTourFeatureEnabled',
      'getWorkspaceAutocompletePathHints',
      'getRuntimeAutocompleteContext',
      'getRuntimeAutocompleteItems',
      'extractGrepOutputTokens',
      'getGrepOutputSuggestions',
      'loadSessionVariables',
      'openAutocompleteForVisibleComposer',
      'allowedCommandsFaqData',
      'getWorkspaceAutocompleteFlagFileHints',
      '_runtimeWorkflowContext',
    ].forEach((name) => {
      delete window[name]
    })
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      const refreshed = vi.fn()
      const { acAccept } = fromDomScripts(
        ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      input.addEventListener('input', refreshed)
      input.value = 'cd naa'
      input.setSelectionRange(6, 6)

      acAccept({ value: 'naabu/', replaceStart: 3, replaceEnd: 6 })
      vi.runOnlyPendingTimers()

      expect(input.value).toBe('cd naabu/')
      expect(refreshed).toHaveBeenCalledTimes(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('acAccept refreshes autocomplete after accepting a command root suggestion', () => {
    vi.useFakeTimers()
    try {
      const { acAccept, handleComposerInputChange } = fromDomScripts(
        ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
        {
          document,
          cmdInput: document.getElementById('cmd'),
          acDropdown: document.getElementById('ac'),
          mobileComposerHost: document.getElementById('mobile-composer-host'),
          mobileCmdInput: document.getElementById('mobile-cmd'),
          acSuggestions: ['ping'],
          acContextRegistry: {
            ping: {
              examples: [
                { value: 'ping -h', description: 'Show help and usage' },
                { value: 'ping -c 4 darklab.sh', description: 'Send 4 pings to a host' },
              ],
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
        acAccept,
        handleComposerInputChange,
      }`,
      )
      const input = document.getElementById('cmd')
      input.addEventListener('input', () => handleComposerInputChange(input))
      input.value = 'pin'
      input.setSelectionRange(3, 3)

      acAccept('ping')
      expect(document.getElementById('ac').style.display).toBe('none')

      vi.runOnlyPendingTimers()

      expect(input.value).toBe('ping')
      expect(document.getElementById('ac').style.display).toBe('block')
      expect([...document.querySelectorAll('.ac-item')].map(item => item.textContent)).toEqual([
        'ping -hShow help and usage',
        'ping -c 4 darklab.shSend 4 pings to a host',
      ])
    } finally {
      vi.useRealTimers()
    }
  })

  it('acAccept suppresses one synthetic input cycle so the dropdown does not immediately reopen', () => {
    const { acAccept } = fromDomScripts(
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
            document.getElementById('ac').style.display = 'none'
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
          shodan: {
            flags: [],
            expects_value: [],
            arg_hints: {
              __positional__: [
                { value: 'scan', insertValue: 'scan ', description: 'Manage on-demand scans' },
              ],
            },
            subcommands: {
              scan: {
                flags: [],
                expects_value: [],
                arg_hints: {
                  __positional__: [
                    { value: 'internet', insertValue: 'internet ', description: 'Scan internet by port/protocol' },
                    { value: 'list', insertValue: 'list ', description: 'Show scans' },
                    { value: 'protocols', insertValue: 'protocols ', description: 'List protocols' },
                    { value: 'status', insertValue: 'status ', description: 'Check scan status' },
                    { value: 'submit', insertValue: 'submit ', description: 'Submit a scan' },
                  ],
                },
                subcommands: {
                  submit: {
                    flags: [],
                    expects_value: [],
                    arg_hints: {
                      __positional__: [
                        { value: '<ip-or-cidr>', hintOnly: true, value_type: 'target', description: 'Public IP or CIDR' },
                      ],
                    },
                    subcommands: {},
                  },
                },
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

    expect(getAutocompleteMatches('amass ', 6).map(item => item.value)).toEqual(['-h', 'enum', 'subs'])
    expect(getAutocompleteMatches('amass nm', 8).map(item => item.value)).toEqual(['enum'])
    expect(getAutocompleteMatches('shodan scan ', 12).map(item => item.value)).toEqual([
      'internet',
      'list',
      'protocols',
      'status',
      'submit',
    ])
    expect(getAutocompleteMatches('shodan scan submit ', 19).map(item => item.value)).toEqual(['<ip-or-cidr>'])
  })

  it('shows root and subcommand examples while a unique command root is being typed', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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

  it('walks nested subcommands before suggesting the next project argument', () => {
    const { getAutocompleteMatches, setProjectAutocompleteProjects } = fromDomScripts(
      [
        'app/static/js/core/utils.js',
        'app/static/js/core/autocomplete_core.js',
        'app/static/js/features/autocomplete/suggestions.js',
        'app/static/js/features/autocomplete/runtime_context.js',
        'app/static/js/autocomplete.js',
      ],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => '',
        allowedCommandsFaqData: { commands: [] },
        _cliThemeEntries: () => [],
        _cliConfigEntries: () => [],
        sessionVariables: [],
        acSuggestions: [],
        acContextRegistry: {
          project: {
            flags: [],
            expects_value: [],
            arg_hints: {
              __positional__: [
                { value: 'link', insertValue: 'link ', description: 'Link source record' },
                { value: 'target', insertValue: 'target ', description: 'Manage targets' },
              ],
            },
            subcommands: {
              use: {
                flags: [],
                expects_value: [],
                arg_hints: { __positional__: [{ value: '<name-or-id>', hintOnly: true, description: 'Project name, slug, or id' }] },
                subcommands: {},
              },
              archive: {
                flags: [],
                expects_value: [],
                arg_hints: { __positional__: [{ value: '<name-or-id>', hintOnly: true, description: 'Project name, slug, or id' }] },
                subcommands: {},
              },
              unarchive: {
                flags: [],
                expects_value: [],
                arg_hints: { __positional__: [{ value: '<name-or-id>', hintOnly: true, description: 'Project name, slug, or id' }] },
                subcommands: {},
              },
              delete: {
                flags: [],
                expects_value: [],
                arg_hints: { __positional__: [{ value: '<name-or-id>', hintOnly: true, description: 'Project name, slug, or id' }] },
                subcommands: {},
              },
              link: {
                flags: [],
                expects_value: [],
                arg_hints: {
                  __positional__: [
                    { value: 'run', insertValue: 'run ', description: 'Link a run' },
                  ],
                },
                subcommands: {
                  run: {
                    flags: [],
                    expects_value: [],
                    arg_hints: {
                      __positional__: [
                        { value: 'last', description: 'Link the latest run in this tab' },
                        { value: '<run-id>', hintOnly: true, description: 'Run id' },
                      ],
                    },
                    close_after: { run: 1 },
                    subcommands: {},
                  },
                },
              },
              target: {
                flags: [],
                expects_value: [],
                arg_hints: { __positional__: [{ value: 'add', insertValue: 'add ', description: 'Add target' }] },
                subcommands: {
                  add: {
                    flags: [],
                    expects_value: [],
                    arg_hints: {
                      __positional__: [
                        { value: 'domain', insertValue: 'domain ', description: 'Add a domain target' },
                        { value: 'url', insertValue: 'url ', description: 'Add a URL target' },
                      ],
                    },
                    subcommands: {
                      domain: {
                        flags: [],
                        expects_value: [],
                        arg_hints: {
                          __positional__: [
                            { value: '<domain>', hintOnly: true, value_type: 'domain', description: 'Domain value' },
                          ],
                        },
                        close_after: { domain: 1 },
                        subcommands: {},
                      },
                    },
                  },
                },
              },
            },
          },
          ping: { flags: [], expects_value: [], arg_hints: {} },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
      setProjectAutocompleteProjects,
    }`,
    )

    setProjectAutocompleteProjects([
      { id: 'prj_active', slug: 'active-case', name: 'Active Case', status: 'active' },
      { id: 'prj_archived', slug: 'archived-case', name: 'Archived Case', status: 'archived' },
    ])
    expect(getAutocompleteMatches('project target add ', 19).map(item => item.value)).toEqual(['domain', 'url'])
    expect(getAutocompleteMatches('project target add domain ', 26).map(item => item.value)).toEqual(['<domain>'])
    expect(getAutocompleteMatches('project target add domain darklab.sh ', 37)).toEqual([])
    expect(getAutocompleteMatches('project link run ', 17).map(item => item.value)).toEqual(['last', '<run-id>'])
    expect(getAutocompleteMatches('project link run run-1 ', 23)).toEqual([])
    expect(getAutocompleteMatches('project use ', 12).map(item => item.value)).toEqual(['active-case'])
    expect(getAutocompleteMatches('project rename ', 15).map(item => item.value)).toEqual(['active-case', 'archived-case'])
    expect(getAutocompleteMatches('project archive ', 16).map(item => item.value)).toEqual(['active-case'])
    expect(getAutocompleteMatches('project unarchive ', 18).map(item => item.value)).toEqual(['archived-case'])
    expect(getAutocompleteMatches('project delete ', 15).map(item => item.value)).toEqual(['active-case', 'archived-case'])
  })

  it('suggests schedule ids for terminal schedule actions', () => {
    const { getAutocompleteMatches, setScheduleAutocompleteSchedules } = fromDomScripts(
      [
        'app/static/js/core/utils.js',
        'app/static/js/core/autocomplete_core.js',
        'app/static/js/features/autocomplete/suggestions.js',
        'app/static/js/features/autocomplete/runtime_context.js',
        'app/static/js/autocomplete.js',
      ],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => '',
        allowedCommandsFaqData: { commands: [] },
        _cliThemeEntries: () => [],
        _cliConfigEntries: () => [],
        sessionVariables: [],
        acSuggestions: [],
        acContextRegistry: {
          schedule: {
            flags: [],
            expects_value: [],
            arg_hints: {
              __positional__: [
                { value: 'list', insertValue: 'list ', description: 'List schedules' },
                { value: 'pause', insertValue: 'pause ', description: 'Pause a schedule' },
              ],
            },
            subcommands: {
              pause: { flags: [], arg_hints: { __positional__: [{ value: '<schedule-id>', hintOnly: true }] } },
              info: { flags: [], arg_hints: { __positional__: [{ value: '<schedule-id>', hintOnly: true }] } },
            },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
      setScheduleAutocompleteSchedules,
    }`,
    )

    setScheduleAutocompleteSchedules([
      { id: 'sch_hourly', label: 'Hourly ping', enabled: true },
      { id: 'sch_paused', command_text: 'nmap -sV ip.darklab.sh', enabled: false },
    ])

    expect(getAutocompleteMatches('schedule pause ', 15).map(item => item.value)).toEqual(['sch_hourly', 'sch_paused'])
    expect(getAutocompleteMatches('schedule info sch_p', 19).map(item => item.value)).toEqual(['sch_paused'])
  })

  it('suggests watcher ids for terminal watch actions', () => {
    const { getAutocompleteMatches, setWatcherAutocompleteWatchers } = fromDomScripts(
      [
        'app/static/js/core/utils.js',
        'app/static/js/core/autocomplete_core.js',
        'app/static/js/features/autocomplete/suggestions.js',
        'app/static/js/features/autocomplete/runtime_context.js',
        'app/static/js/autocomplete.js',
      ],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => '',
        allowedCommandsFaqData: { commands: [] },
        _cliThemeEntries: () => [],
        _cliConfigEntries: () => [],
        sessionVariables: [],
        acSuggestions: [],
        acContextRegistry: {
          watch: {
            flags: [],
            expects_value: [],
            arg_hints: {
              __positional__: [
                { value: 'list', insertValue: 'list ', description: 'List watchers' },
                { value: 'pause', insertValue: 'pause ', description: 'Pause a watcher' },
              ],
            },
            subcommands: {
              pause: { flags: [], arg_hints: { __positional__: [{ value: '<watcher-id>', hintOnly: true }] } },
              accept: { flags: [], arg_hints: { __positional__: [{ value: '<watcher-id>', hintOnly: true }] } },
              info: { flags: [], arg_hints: { __positional__: [{ value: '<watcher-id>', hintOnly: true }] } },
            },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
      setWatcherAutocompleteWatchers,
    }`,
    )

    setWatcherAutocompleteWatchers([
      { id: 'wtr_nmap', label: 'Nmap drift', state: 'ok' },
      { id: 'wtr_paused', command_text: 'katana -u darklab.sh', state: 'paused' },
    ])

    expect(getAutocompleteMatches('watch pause ', 12).map(item => item.value)).toEqual(['wtr_nmap', 'wtr_paused'])
    expect(getAutocompleteMatches('watch accept wtr_p', 18).map(item => item.value)).toEqual(['wtr_paused'])
  })

  it('tracks recent values from structured flag and positional slots, capped per kind in memory', () => {
    const { rememberRecentValuesFromCommand, _readRecentValues } = fromDomScripts(
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
          nmap: {
            flags: [],
            expects_value: [],
            arg_hints: { __positional__: [{ value: '<target>', hintOnly: true, value_type: 'target', description: 'Hostname, IP, or CIDR' }] },
          },
          nuclei: {
            flags: [{ value: '-l', description: 'File with targets' }],
            expects_value: ['-l'],
            workspace_file_flags: ['-l'],
            arg_hints: { '-l': [{ value: '<target-file>', hintOnly: true, value_type: 'target', description: 'Session file containing one URL or host per line' }] },
          },
          dnsx: {
            flags: [{ value: '-l', description: 'Read hostnames from a session file' }],
            expects_value: ['-l'],
            arg_hints: { '-l': [{ value: '<host-file>', hintOnly: true, value_type: 'host', description: 'Session file containing one hostname per line' }] },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      rememberRecentValuesFromCommand,
      _readRecentValues,
    }`,
    )

    rememberRecentValuesFromCommand('subfinder -d Alpha.example.com -silent')
    rememberRecentValuesFromCommand('dig MX beta.example.org +short')
    rememberRecentValuesFromCommand('dig @8.8.8.8 gamma.example.net')
    rememberRecentValuesFromCommand('curl https://not-a-domain-slot.example')
    rememberRecentValuesFromCommand('nuclei -l subs.txt -o nuclei-findings.txt')
    rememberRecentValuesFromCommand('dnsx -l hosts.txt -resp')
    for (let i = 0; i < 10; i += 1) {
      rememberRecentValuesFromCommand(`subfinder -d d${i}.example.com`)
    }
    rememberRecentValuesFromCommand('nmap target.example.dev')
    rememberRecentValuesFromCommand('nmap 192.0.2.10')
    rememberRecentValuesFromCommand('subfinder -d beta.example.org')

    expect(_readRecentValues('domain')).toEqual([
      'beta.example.org',
      'target.example.dev',
      'd9.example.com',
      'd8.example.com',
      'd7.example.com',
      'd6.example.com',
      'd5.example.com',
      'd4.example.com',
      'd3.example.com',
      'd2.example.com',
    ])
    expect(_readRecentValues('ip')).toEqual(['192.0.2.10'])
    expect(sessionStorage.getItem('recent_values:session-a')).toBeNull()
  })

  it('stores complete IPv4 values from host slots without keeping partial numeric hosts', () => {
    const { rememberRecentValuesFromCommand, _readRecentValues } = fromDomScripts(
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        SESSION_ID: 'session-a',
        acSuggestions: [],
        acContextRegistry: {
          ping: {
            flags: [],
            expects_value: [],
            arg_hints: { __positional__: [{ value: '<host>', hintOnly: true, value_type: 'host', description: 'Hostname or IP address to probe' }] },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      rememberRecentValuesFromCommand,
      _readRecentValues,
    }`,
    )

    rememberRecentValuesFromCommand('ping 192.168.1.5')
    rememberRecentValuesFromCommand('ping 192.168.1')

    expect(_readRecentValues('ip')).toEqual(['192.168.1.5'])
    expect(_readRecentValues('domain')).toEqual([])
  })

  it('loads recent values from the session endpoint', async () => {
    const apiFetch = vi.fn(() => Promise.resolve({
      json: () => Promise.resolve({
        values: {
          domain: ['Alpha.example.com.', 'https://ignored.example', 'beta.example.org'],
          ip: ['192.0.2.10'],
          url: ['https://Example.com/path?token=ignored#frag'],
          port_set: ['80, 443'],
        },
      }),
    }))
    const { loadRecentValues, _readRecentValues } = fromDomScripts(
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      loadRecentValues,
      _readRecentValues,
    }`,
    )

    await loadRecentValues()

    expect(apiFetch).toHaveBeenCalledWith('/session/recent-values')
    expect(_readRecentValues('domain')).toEqual(['alpha.example.com', 'beta.example.org'])
    expect(_readRecentValues('ip')).toEqual(['192.0.2.10'])
    expect(_readRecentValues('url')).toEqual(['https://example.com/path'])
    expect(_readRecentValues('port_set')).toEqual(['80,443'])
  })

  it('replays recent-value captures submitted before autocomplete context loads', async () => {
    const apiFetch = vi.fn((url, options = {}) => {
      if (url === '/session/recent-values' && options.method === 'POST') {
        return Promise.resolve({
          json: () => Promise.resolve({
            values: {
              domain: ['alpha.example.com'],
              ip: [],
              url: [],
              port_set: [],
            },
          }),
        })
      }
      return Promise.resolve({
        json: () => Promise.resolve({
          values: {
            domain: [],
            ip: [],
            url: [],
            port_set: [],
          },
        }),
      })
    })
    const { loadRecentValues, rememberRecentValuesFromCommand, _readRecentValues, _setContextRegistry } = fromDomScripts(
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      loadRecentValues,
      rememberRecentValuesFromCommand,
      _readRecentValues,
      _setContextRegistry: (value) => {
        acContextRegistry = value;
        if (typeof APP_STATE_API !== 'undefined') APP_STATE_API.getState().acContextRegistry = value;
      },
    }`,
    )

    expect(rememberRecentValuesFromCommand('dig alpha.example.com')).toEqual([])
    _setContextRegistry({
      dig: {
        flags: [],
        expects_value: [],
        arg_hints: { __positional__: [{ value: '<domain>', hintOnly: true, value_type: 'domain' }] },
      },
    })
    await loadRecentValues()

    expect(_readRecentValues('domain')).toEqual(['alpha.example.com'])
    expect(apiFetch).toHaveBeenCalledWith('/session/recent-values', expect.objectContaining({
      method: 'POST',
    }))
  })

  it('reloads active project targets after a same-session project workspace storage signal', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/projects?include_archived=1') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ projects: [] }),
        })
      }
      if (url === '/projects/active') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ project: { id: 'prj_abc123' } }),
        })
      }
      if (url === '/projects/prj_abc123/targets?limit=200') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            targets: [{ type: 'domain', value: 'new-target.example.com', label: 'CLI add' }],
          }),
        })
      }
      return Promise.reject(new Error(`Unexpected URL: ${url}`))
    })
    const { _readProjectTargets } = fromDomScripts(
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      _readProjectTargets,
    }`,
    )

    window.dispatchEvent(new StorageEvent('storage', {
      key: 'darklab_project_workspace_changed',
      newValue: JSON.stringify({ session_id: 'session-a', changed_at: Date.now() }),
    }))
    for (let i = 0; i < 8; i += 1) await Promise.resolve()

    expect(apiFetch).toHaveBeenCalledWith('/projects/active', { cache: 'no-store' })
    expect(apiFetch).toHaveBeenCalledWith('/projects/prj_abc123/targets?limit=200', { cache: 'no-store' })
    expect(_readProjectTargets()).toEqual([
      { type: 'domain', value: 'new-target.example.com', label: 'CLI add' },
    ])
  })

  it('persists captured recent values without requiring browser storage', async () => {
    const apiFetch = vi.fn(() => Promise.resolve({
      json: () => Promise.resolve({ values: { domain: ['alpha.example.com'] } }),
    }))
    const { rememberRecentValuesFromCommand, _readRecentValues } = fromDomScripts(
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      rememberRecentValuesFromCommand,
      _readRecentValues,
    }`,
    )

    rememberRecentValuesFromCommand('dig Alpha.example.com')
    await Promise.resolve()
    await Promise.resolve()

    expect(apiFetch).toHaveBeenCalledWith('/session/recent-values', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ values: [{ kind: 'domain', value: 'alpha.example.com' }] }),
    }))
    expect(_readRecentValues('domain')).toEqual(['alpha.example.com'])
    expect(sessionStorage.getItem('recent_values:session-a')).toBeNull()
  })

  it('suggests recent targets only inside compatible known value slots', () => {
    const { getAutocompleteMatches, rememberRecentValuesFromCommand, setProjectAutocompleteTargets } = fromDomScripts(
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
              __positional__: [{ value: '<host>', hintOnly: true, value_type: 'host', description: 'Hostname or IP address to probe' }],
            },
          },
          nmap: {
            flags: [
              { value: '-p', description: 'Ports to scan' },
            ],
            expects_value: ['-p'],
            arg_hints: {
              '-p': [
                { value: '<ports>', hintOnly: true, value_type: 'port_set', description: 'Comma-separated ports or ranges' },
                { value: '80,443', description: 'Common web ports' },
              ],
              __positional__: [{ value: '<target>', hintOnly: true, value_type: 'target', description: 'Hostname, IP, or CIDR' }],
            },
          },
          curl: {
            flags: [],
            expects_value: [],
            arg_hints: {
              __positional__: [{ value: '<url>', hintOnly: true, value_type: 'url', description: 'URL to request' }],
            },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
      rememberRecentValuesFromCommand,
      setProjectAutocompleteTargets,
    }`,
    )

    rememberRecentValuesFromCommand('subfinder -d alpha.example.com')
    rememberRecentValuesFromCommand('dig beta.example.org')
    rememberRecentValuesFromCommand('subfinder -d darklab.sh')
    rememberRecentValuesFromCommand('ping 198.51.100.10')
    rememberRecentValuesFromCommand('nmap -p 8080-8081 recent.example.net')
    rememberRecentValuesFromCommand('curl https://recent.example.net/login?token=secret#frag')
    setProjectAutocompleteTargets([
      { type: 'domain', value: 'project.example.com', label: 'Primary' },
      { type: 'ip', value: '192.0.2.10' },
      { type: 'url', value: 'https://project.example.com/login' },
      { type: 'port_set', value: '22,80' },
    ])

    expect(getAutocompleteMatches('subfinder -d ', 13).map(item => item.value)).toEqual([
      'project.example.com',
      'recent.example.net',
      'darklab.sh',
      'beta.example.org',
      'alpha.example.com',
      '<domain>',
    ])
    expect(getAutocompleteMatches('dig MX be', 9).map(item => item.value)).toEqual(['beta.example.org', '<domain>'])
    expect(getAutocompleteMatches('ping ', 5).map(item => item.value)).toEqual([
      'project.example.com',
      '192.0.2.10',
      'recent.example.net',
      'darklab.sh',
      'beta.example.org',
      'alpha.example.com',
      '198.51.100.10',
      '-c',
      '-i',
      '<host>',
    ])
    expect(getAutocompleteMatches('nmap -p ', 8).map(item => item.value)).toEqual([
      '22,80',
      '8080-8081',
      '<ports>',
      '80,443',
    ])
    expect(getAutocompleteMatches('curl https://', 13).map(item => item.value)).toEqual([
      'https://project.example.com/login',
      'https://recent.example.net/login',
      '<url>',
    ])
    expect(getAutocompleteMatches('subfinder -o ', 13).map(item => item.value)).toEqual(['subdomains.txt'])
  })

  it('does not infer recent-value slots from placeholder text without value_type metadata', () => {
    const { getAutocompleteMatches, rememberRecentValuesFromCommand, _readRecentValues } = fromDomScripts(
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      rememberRecentValuesFromCommand,
      _readRecentValues,
    }`,
    )

    rememberRecentValuesFromCommand('legacydig ignored.example.com')
    rememberRecentValuesFromCommand('dig alpha.example.com')

    expect(_readRecentValues('domain')).toEqual(['alpha.example.com'])
    expect(getAutocompleteMatches('legacydig a', 11).map(item => item.value)).toEqual(['<domain>'])
    expect(getAutocompleteMatches('dig a', 5).map(item => item.value)).toEqual(['alpha.example.com', '<domain>'])
  })

  it('keeps case-sensitive dnsrecon -d domain and -D wordlist slots separate', () => {
    const { getAutocompleteMatches, rememberRecentValuesFromCommand, _readRecentValues } = fromDomScripts(
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        SESSION_ID: 'session-a',
        acSuggestions: [],
        acWordlists: [
          {
            value: '/usr/share/wordlists/seclists/Discovery/DNS/subdomains-top1million-5000.txt',
            label: 'Discovery/DNS/subdomains-top1million-5000.txt',
            description: 'DNS wordlist',
            wordlist_category: 'dns',
          },
        ],
        acContextRegistry: {
          dnsrecon: {
            flags: [
              { value: '-d', description: 'Target domain' },
              { value: '-D', description: 'Wordlist' },
              { value: '--xml', description: 'XML output' },
            ],
            expects_value: ['-d', '-D', '--xml'],
            arg_hints: {
              '-d': [{ value: '<domain>', hintOnly: true, value_type: 'domain', description: 'Target domain' }],
              '-D': [{ value: '<wordlist>', hintOnly: true, value_type: 'wordlist', wordlist_category: 'dns' }],
              '--xml': [{ value: 'dnsrecon-results.xml', description: 'Save XML DNS results' }],
            },
          },
          subfinder: {
            flags: [{ value: '-d', description: 'Target domain' }],
            expects_value: ['-d'],
            arg_hints: {
              '-d': [{ value: '<domain>', hintOnly: true, value_type: 'domain', description: 'Target domain' }],
            },
          },
        },
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
      rememberRecentValuesFromCommand,
      _readRecentValues,
    }`,
    )

    expect(rememberRecentValuesFromCommand('dnsrecon -d delta.example.io --xml dnsrecon-results.xml')).toEqual([
      { kind: 'domain', value: 'delta.example.io' },
    ])
    expect(rememberRecentValuesFromCommand('dnsrecon -D subdomains.txt')).toEqual([])
    rememberRecentValuesFromCommand('subfinder -d alpha.example.com')

    expect(_readRecentValues('domain')).toEqual(['alpha.example.com', 'delta.example.io'])
    const rootFlags = getAutocompleteMatches('dnsrecon ', 9).map(item => item.value)
    expect(rootFlags).toContain('-d')
    expect(rootFlags).toContain('-D')
    expect(getAutocompleteMatches('dnsrecon -D', 11).map(item => item.value)).toEqual(['-D'])
    expect(getAutocompleteMatches('dnsrecon -d', 11).map(item => item.value)).toEqual(['-d'])
    expect(getAutocompleteMatches('dnsrecon -d ', 12).map(item => item.value)).toEqual([
      'alpha.example.com',
      'delta.example.io',
      '<domain>',
    ])
    expect(getAutocompleteMatches('dnsrecon -D ', 12).map(item => item.value)).toEqual([
      '/usr/share/wordlists/seclists/Discovery/DNS/subdomains-top1million-5000.txt',
      '<wordlist>',
    ])
  })

  it('suggests installed wordlists only inside marked wordlist slots', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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

  it('honors ordered positional hints one argument slot at a time', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'tcptraceroute ',
        acSuggestions: [],
        acContextRegistry: {
          tcptraceroute: {
            flags: [{ value: '-n', description: 'Do not resolve hop addresses' }],
            expects_value: [],
            arg_hints: {
              __positional__: [
                {
                  value: '<host>',
                  position: 1,
                  hintOnly: true,
                  value_type: 'domain',
                  description: 'Hostname or IP to trace',
                },
                {
                  value: '<port>',
                  position: 2,
                  hintOnly: true,
                  value_type: 'port_set',
                  description: 'TCP port to probe',
                },
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

    expect(getAutocompleteMatches('tcptraceroute ', 14).map((item) => item.value)).toEqual(['-n', '<host>'])
    expect(getAutocompleteMatches('tcptraceroute dark', 18).map((item) => item.value)).toEqual(['<host>'])
    expect(getAutocompleteMatches('tcptraceroute darklab.sh ', 25).map((item) => item.value)).toEqual([
      '-n',
      '<port>',
    ])
    expect(getAutocompleteMatches('tcptraceroute darklab.sh 4', 26).map((item) => item.value)).toEqual(['<port>'])
  })

  it('stops suggesting more positional arguments after reaching argument_limit, but still allows flags', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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

  it('uses bridged allowed-command FAQ data for command lookup suggestions', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      [
        'app/static/js/core/utils.js',
        'app/static/js/core/autocomplete_core.js',
        'app/static/js/features/command-registry/command_registry_bridge.js',
        'app/static/js/features/autocomplete/runtime_context.js',
        'app/static/js/features/autocomplete/suggestions.js',
        'app/static/js/autocomplete.js',
      ],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'man subfinder',
        acSuggestions: [],
        acContextRegistry: {
          man: {
            argument_limit: 1,
            arg_hints: {
              __positional__: [
                { value: '<command>', hintOnly: true, description: 'Manual page for any allowed command' },
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
      setAllowedCommandsFaqData,
    }`,
    )
    delete window.getAllowedCommandsFaqData

    setAllowedCommandsFaqData({ commands: ['subfinder -d example.com'] })

    const items = getAutocompleteMatches('man sub', 7)
    expect(items.map(item => item.value)).toContain('subfinder')
  })

  it('suggests built-in pipe commands after a supported command pipe', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
          tee: {
            pipe_command: true,
            pipe_description: 'Write output to a session file and keep showing it',
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
    expect(items.map((item) => item.value)).toEqual(['grep', 'head', 'tail', 'wc -l', 'tee'])
    expect(items.find(item => item.value === 'wc -l').description).toBe('Count lines')
    expect(items.find(item => item.value === 'tee').description).toContain('session file')
  })

  it('uses live workspace file hints for workspace read flags instead of static examples', () => {
    const { getAutocompleteMatches, setProjectAutocompleteTargets } = fromDomScripts(
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
              '-iL': [{ value: 'targets.txt', description: 'Static registry example', value_type: 'target' }],
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
      setProjectAutocompleteTargets,
    }`,
    )
    setProjectAutocompleteTargets([
      { type: 'domain', value: 'darklab.sh' },
      { type: 'ip', value: '192.0.2.10' },
    ])

    const items = getAutocompleteMatches('nmap -iL ', 10)

    expect(items.map(item => item.value)).toEqual(['inputs.txt'])
    expect(items[0].description).toBe('session file · 42 B')
  })

  it('keeps workspace file-move positional args scoped to session entries, not scan targets', () => {
    const { getAutocompleteMatches, setProjectAutocompleteTargets } = fromDomScripts(
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'mv ',
        acSuggestions: [],
        acContextRegistry: {
          mv: {
            argument_limit: 2,
            arg_hints: {
              __positional__: [
                { value: '<source> <destination>', hintOnly: true, value_type: 'workspace_path', description: 'Session file or folder path' },
              ],
            },
          },
        },
        getWorkspaceAutocompleteFileHints: () => [
          { value: 'notes.txt', description: 'session file · 12 B' },
        ],
        getWorkspaceAutocompleteDirectoryHints: () => [
          { value: 'scans/', description: 'session folder' },
        ],
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
      setProjectAutocompleteTargets,
    }`,
    )
    setProjectAutocompleteTargets([
      { type: 'domain', value: 'darklab.sh' },
      { type: 'ip', value: '192.0.2.10' },
    ])

    // Whitespace after the command: positional slot, no partial token typed.
    const emptyToken = getAutocompleteMatches('mv ', 3)
    expect(emptyToken.map(item => item.value)).toEqual(['notes.txt', 'scans/'])
    expect(emptyToken.some(item => /Project target|Recent target/.test(item.description || ''))).toBe(false)

    // Partial token: the value-type slot must still not inject scan targets.
    const partialToken = getAutocompleteMatches('mv no', 5)
    expect(partialToken.map(item => item.value)).toEqual(['notes.txt'])
  })

  it('keeps the `file move` subcommand scoped to session entries, not scan targets', () => {
    const { getAutocompleteMatches, setProjectAutocompleteTargets } = fromDomScripts(
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
      {
        document,
        cmdInput: document.getElementById('cmd'),
        acDropdown: document.getElementById('ac'),
        mobileComposerHost: document.getElementById('mobile-composer-host'),
        mobileCmdInput: document.getElementById('mobile-cmd'),
        getComposerValue: () => 'file move ',
        acSuggestions: [],
        acContextRegistry: {
          file: {
            flags: [],
            expects_value: [],
            arg_hints: {
              __positional__: [
                { value: 'move', insertValue: 'move ', description: 'Move or rename a session file or folder' },
              ],
            },
            subcommands: {
              move: {
                flags: [],
                expects_value: [],
                arg_hints: {
                  __positional__: [
                    { value: '<source> <destination>', hintOnly: true, value_type: 'workspace_path', description: 'Session file or folder path' },
                  ],
                },
                subcommands: {},
              },
            },
          },
        },
        getWorkspaceAutocompleteFileHints: () => [
          { value: 'notes.txt', description: 'session file · 12 B' },
        ],
        getWorkspaceAutocompleteDirectoryHints: () => [
          { value: 'scans/', description: 'session folder' },
        ],
        acFiltered: [],
        acIndex: -1,
        acSuppressInputOnce: false,
      },
      `{
      getAutocompleteMatches,
      setProjectAutocompleteTargets,
    }`,
    )
    setProjectAutocompleteTargets([
      { type: 'domain', value: 'darklab.sh' },
      { type: 'ip', value: '192.0.2.10' },
    ])

    const items = getAutocompleteMatches('file move ', 10)
    expect(items.map(item => item.value)).toEqual(['notes.txt', 'scans/'])
    expect(items.some(item => /Project target|Recent target/.test(item.description || ''))).toBe(false)
  })

  it('uses cwd-relative workspace file hints for external workspace read flags', () => {
    window.getWorkspaceAutocompleteFlagFileHints = token => (
      String(token || '').includes('/')
        ? [{ value: 'nested/targets.txt', description: 'session file · 24 B' }]
        : [
            { value: 'targets.txt', description: 'session file · 42 B' },
            { value: 'nested/', description: 'session folder' },
          ]
    )
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
                { value: '<source> <destination>', hintOnly: true, value_type: 'workspace_path', description: 'Session file or folder path' },
                { value: 'root.txt', description: 'session file · 1 B' },
              ],
            },
            workspace_path_arg_kinds: { __positional__: ['any', 'directory'] },
          },
          cp: {
            argument_limit: 2,
            arg_hints: {
              __positional__: [
                { value: 'root.txt', description: 'session file · 1 B' },
              ],
            },
            workspace_path_arg_kinds: { __positional__: ['file', 'directory'] },
          },
          touch: {
            argument_limit: 1,
            arg_hints: {
              __positional__: [
                { value: 'root.txt', description: 'session file · 1 B' },
              ],
            },
            workspace_path_arg_kinds: { __positional__: ['file'] },
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
    expect(getAutocompleteMatches('cp darklab/', 11).map(item => item.value)).toEqual(['darklab/targets.txt'])
    expect(getAutocompleteMatches('cp root.txt ../', 14).map(item => item.value)).toEqual(['../archive/'])
    expect(getAutocompleteMatches('touch darklab/', 14).map(item => item.value)).toEqual(['darklab/targets.txt'])
    expect(getAutocompleteMatches('file show darklab/', 18).map(item => item.value)).toEqual(['darklab/targets.txt'])
    expect(getAutocompleteMatches('file move root.txt ../', 22).map(item => item.value)).toEqual(['../archive/'])
  })

  it('returns pipe-stage flag hints for grep', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/core/utils.js', 'app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/suggestions.js', 'app/static/js/autocomplete.js'],
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
