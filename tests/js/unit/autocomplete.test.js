import { fromDomScripts } from './helpers/extract.js'

function loadAutocompleteFns() {
  const cmdInput = document.getElementById('cmd')
  const acDropdown = document.getElementById('ac')

  return fromDomScripts([
    'app/static/js/utils.js',
    'app/static/js/autocomplete.js',
  ], {
    document,
    cmdInput,
    acDropdown,
  }, `{
    acShow,
    acHide,
    acAccept,
    _setAcIndex: (value) => { acIndex = value; },
  }`)
}

describe('autocomplete helpers', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <input id="cmd" />
      <div id="ac"></div>
    `
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

  it('mousedown on a suggestion accepts it without blurring the input', () => {
    const { acShow } = loadAutocompleteFns()
    const input = document.getElementById('cmd')
    const focusSpy = vi.spyOn(input, 'focus')

    acShow(['whois example.com'])
    document.querySelector('.ac-item').dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))

    expect(input.value).toBe('whois example.com')
    expect(document.getElementById('ac').style.display).toBe('none')
    expect(focusSpy).toHaveBeenCalled()
  })

  it('positions dropdown above and renders reverse order when space below is tight', () => {
    const { acShow } = loadAutocompleteFns()
    const input = document.getElementById('cmd')
    input.value = 'n'
    const wrap = document.createElement('div')
    wrap.className = 'shell-prompt-wrap'
    wrap.appendChild(document.getElementById('ac'))
    document.body.appendChild(wrap)

    const prefix = document.createElement('span')
    prefix.className = 'prompt-prefix'
    prefix.textContent = 'anon@shell.darklab.sh:~$'
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

    acShow(['nmap -sV', 'nslookup example.com'])

    expect(document.getElementById('ac').classList.contains('ac-up')).toBe(true)
    const items = [...document.querySelectorAll('.ac-item')].map(el => el.textContent.trim())
    expect(items[0]).toBe('nslookup example.com')
    expect(items[1]).toBe('nmap -sV')
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
    prefix.textContent = 'anon@shell.darklab.sh:~$'
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

  it('defaults the highlighted item to the bottom-most option when the menu opens above', () => {
    const { acShow } = loadAutocompleteFns()
    const input = document.getElementById('cmd')
    input.value = 'n'
    const wrap = document.createElement('div')
    wrap.className = 'shell-prompt-wrap'
    wrap.appendChild(document.getElementById('ac'))
    document.body.appendChild(wrap)

    const prefix = document.createElement('span')
    prefix.className = 'prompt-prefix'
    prefix.textContent = 'anon@shell.darklab.sh:~$'
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

    acShow(['nmap -sV', 'nslookup example.com', 'netstat -an'])

    const items = [...document.querySelectorAll('.ac-item')]
    expect(document.getElementById('ac').classList.contains('ac-up')).toBe(true)
    expect(items[items.length - 1].className).toBe('ac-item ac-active')
    expect(items[items.length - 1].textContent.trim()).toBe('nmap -sV')
  })

  it('scrolls to the bottom when the menu opens above so the active item stays visible', () => {
    const { acShow } = loadAutocompleteFns()
    const input = document.getElementById('cmd')
    input.value = 'n'
    const wrap = document.createElement('div')
    wrap.className = 'shell-prompt-wrap'
    wrap.appendChild(document.getElementById('ac'))
    document.body.appendChild(wrap)

    const prefix = document.createElement('span')
    prefix.className = 'prompt-prefix'
    prefix.textContent = 'anon@shell.darklab.sh:~$'
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

    acShow(['nmap -sV', 'nslookup example.com', 'netstat -an', 'nc -lvnp 4444'])

    const dropdown = document.getElementById('ac')
    expect(dropdown.classList.contains('ac-up')).toBe(true)
    expect(dropdown.scrollTop).toBe(dropdown.scrollHeight)
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
    prefix.textContent = 'anon@shell.darklab.sh:~$'
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
      ['cat /etc/hosts', 0],
      ['curl http://localhost:5001/config', 22],
      ['curl http://localhost:5001/health', 44],
      ['clear', 66],
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
      acShow(['clear', 'curl http://localhost:5001/health', 'curl http://localhost:5001/config', 'cat /etc/hosts'])
      expect(dropdown.scrollTop).toBe(44)
      expect(document.querySelector('.ac-item.ac-active')?.textContent.trim()).toBe('clear')

      _setAcIndex(2)
      acShow(['clear', 'curl http://localhost:5001/health', 'curl http://localhost:5001/config', 'cat /etc/hosts'])
      expect(document.querySelector('.ac-item.ac-active')?.textContent.trim()).toBe('curl http://localhost:5001/config')
      expect(dropdown.scrollTop).toBe(18)
    } finally {
      if (originalOffsetTop) Object.defineProperty(HTMLElement.prototype, 'offsetTop', originalOffsetTop)
      if (originalOffsetHeight) Object.defineProperty(HTMLElement.prototype, 'offsetHeight', originalOffsetHeight)
    }
  })
})
