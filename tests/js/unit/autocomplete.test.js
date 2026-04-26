import { fromDomScripts } from './helpers/extract.js'

function loadAutocompleteFns() {
  const cmdInput = document.getElementById('cmd')
  const acDropdown = document.getElementById('ac')
  const mobileComposerHost = document.getElementById('mobile-composer-host')
  const mobileCmdInput = document.getElementById('mobile-cmd')

  return fromDomScripts(
    ['app/static/js/utils.js', 'app/static/js/autocomplete.js'],
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
    },
    `{
    acShow,
    acHide,
    acAccept,
    acExpandSharedPrefix,
    getAutocompleteMatches,
    limitAutocompleteMatchesForDisplay,
    _getAutocompleteSharedPrefix,
    _setAcIndex: (value) => { acIndex = value; },
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
  })

  it('renders suggestions from the shared composer value accessor when present', () => {
    document.getElementById('cmd').value = ''
    const { acShow } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete.js'],
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
    expect(items[0].className).toBe('ac-item')
    expect(items[1].className).toBe('ac-item ac-active')
  })

  it('renders contextual suggestions with descriptions', () => {
    const { acShow } = loadAutocompleteFns()
    document.getElementById('cmd').value = 'nmap -'

    acShow([{ value: '-sV', description: 'Service detection', replaceStart: 5, replaceEnd: 6 }])

    const item = document.querySelector('.ac-item')
    expect(item?.querySelector('.ac-item-main')?.textContent).toBe('-sV')
    expect(item?.querySelector('.ac-item-desc')?.textContent).toBe('Service detection')
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

  it('acAccept suppresses one synthetic input cycle so the dropdown does not immediately reopen', () => {
    const { acAccept } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/utils.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/utils.js', 'app/static/js/autocomplete.js'],
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
              __positional__: [{ value: '<domain>', description: 'Domain name' }],
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

  it('prefers runtime autocomplete suggestions for client-side commands', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/utils.js', 'app/static/js/autocomplete.js'],
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
              __positional__: [{ value: '<url>', description: 'Target URL' }],
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
      ['app/static/js/utils.js', 'app/static/js/autocomplete.js'],
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

  it('keeps an exact single flag match visible so its description is still shown', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/utils.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/utils.js', 'app/static/js/autocomplete.js'],
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
              __positional__: [{ value: '<target>', description: 'Hostname, IP, or CIDR' }],
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
      ['app/static/js/utils.js', 'app/static/js/autocomplete.js'],
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
              __positional__: [{ value: '<target>', description: 'Hostname, IP, or CIDR' }],
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
      ['app/static/js/utils.js', 'app/static/js/autocomplete.js'],
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
              set: [{ value: '<token>', description: 'Paste a token' }],
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
      ['app/static/js/utils.js', 'app/static/js/autocomplete.js'],
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
              set: [{ value: '<token>', description: 'Paste a token' }],
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
      ['app/static/js/utils.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/utils.js', 'app/static/js/autocomplete.js'],
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
                { value: '<file>', description: 'Destination file path' },
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
      ['app/static/js/utils.js', 'app/static/js/autocomplete.js'],
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
              __positional__: [{ value: '<host>', description: 'Hostname or IP address to probe' }],
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
      ['app/static/js/utils.js', 'app/static/js/autocomplete.js'],
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
              __positional__: [{ value: '<host>', description: 'Hostname or IP address to probe' }],
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
      ['app/static/js/utils.js', 'app/static/js/autocomplete.js'],
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
                { value: '<url>', description: 'Target URL to request' },
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
      ['app/static/js/utils.js', 'app/static/js/autocomplete.js'],
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
                { value: '<command>', description: 'Manual page for any allowed command' },
              ],
            },
          },
          ping: {
            argument_limit: 1,
            flags: [{ value: '-c', description: 'Stop after count replies' }],
            arg_hints: {
              __positional__: [{ value: '<host>', description: 'Hostname or IP address to probe' }],
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
      ['app/static/js/utils.js', 'app/static/js/autocomplete.js'],
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

  it('returns pipe-stage flag hints for grep', () => {
    const { getAutocompleteMatches } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/autocomplete.js'],
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
              __positional__: [{ value: '<pattern>', description: 'Text or regex to match' }],
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
      ['app/static/js/utils.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/utils.js', 'app/static/js/autocomplete.js'],
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
      ['app/static/js/utils.js', 'app/static/js/autocomplete.js'],
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
              __positional__: [{ value: '<pattern>', description: 'Text or regex to match' }],
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
      ['app/static/js/utils.js', 'app/static/js/autocomplete.js'],
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
