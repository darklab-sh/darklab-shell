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
})
