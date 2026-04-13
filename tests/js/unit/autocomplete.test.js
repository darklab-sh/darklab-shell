import { fromDomScripts } from './helpers/extract.js'

function loadAutocompleteFns() {
  const cmdInput = document.getElementById('cmd')
  const acDropdown = document.getElementById('ac')
  const mobileComposerHost = document.getElementById('mobile-composer-host')
  const mobileCmdInput = document.getElementById('mobile-cmd')

  return fromDomScripts([
    'app/static/js/utils.js',
    'app/static/js/autocomplete.js',
  ], {
    document,
    cmdInput,
    acDropdown,
    mobileComposerHost,
    mobileCmdInput,
    getComposerValue: () => cmdInput.value,
    acSuggestions: [],
    acFiltered: [],
    acIndex: -1,
    acSuppressInputOnce: false,
  }, `{
    acShow,
    acHide,
    acAccept,
    acExpandSharedPrefix,
    _getAutocompleteSharedPrefix,
    _setAcIndex: (value) => { acIndex = value; },
  }`)
}

describe('autocomplete helpers', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <input id="cmd" />
      <div id="ac"></div>
      <div id="mobile-composer-host"></div>
      <input id="mobile-cmd" />
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
    const { acShow } = fromDomScripts([
      'app/static/js/utils.js',
      'app/static/js/autocomplete.js',
    ], {
      document,
      cmdInput: document.getElementById('cmd'),
      acDropdown: document.getElementById('ac'),
      mobileComposerHost: document.getElementById('mobile-composer-host'),
      mobileCmdInput: document.getElementById('mobile-cmd'),
      getComposerValue: () => 'pi',
      acSuggestions: [],
      acFiltered: [],
      acIndex: -1,
      acSuppressInputOnce: false,
    }, `{
      acShow,
    }`)

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
    const items = [...document.querySelectorAll('.ac-item')].map(el => el.textContent.trim())
    expect(items[0]).toBe('nmap -sV')
    expect(items[1]).toBe('nslookup darklab.sh')
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

    acShow(['clear', 'curl http://localhost:5001/health', 'curl http://localhost:5001/config', 'cat /etc/hosts'])

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
    const originalOffsetHeight = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetHeight')
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
      acShow(['clear', 'curl http://localhost:5001/health', 'curl http://localhost:5001/config', 'cat /etc/hosts'])
      expect(dropdown.scrollTop).toBe(0)
      expect(document.querySelector('.ac-item.ac-active')).toBeNull()

      // After selecting index 2 ('curl config' at offsetTop 44), scroll brings it into view
      _setAcIndex(2)
      acShow(['clear', 'curl http://localhost:5001/health', 'curl http://localhost:5001/config', 'cat /etc/hosts'])
      expect(document.querySelector('.ac-item.ac-active')?.textContent.trim()).toBe('curl http://localhost:5001/config')
      expect(dropdown.scrollTop).toBe(26)
    } finally {
      if (originalOffsetTop) Object.defineProperty(HTMLElement.prototype, 'offsetTop', originalOffsetTop)
      if (originalOffsetHeight) Object.defineProperty(HTMLElement.prototype, 'offsetHeight', originalOffsetHeight)
    }
  })
})
