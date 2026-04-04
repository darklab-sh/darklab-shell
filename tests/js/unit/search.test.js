import { fromDomScripts } from './helpers/extract.js'

const originalScrollIntoView = Element.prototype.scrollIntoView

function loadSearchFns() {
  return fromDomScripts([
    'app/static/js/utils.js',
    'app/static/js/search.js',
  ], {
    document,
    activeTabId: 'tab-1',
    getOutput: () => document.getElementById('out'),
    searchInput: document.getElementById('searchInput'),
    searchCount: document.getElementById('searchCount'),
  }, `{
    runSearch,
    navigateSearch,
    clearHighlights,
    clearSearch,
    _setRegexMode: (value) => { searchRegexMode = value; },
  }`)
}

describe('search helpers', () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = () => {}
    document.body.innerHTML = `
      <input id="searchInput" />
      <span id="searchCount"></span>
      <div id="out">
        <span class="line">hello world</span>
        <span class="line">HELLO again</span>
        <span class="line">goodbye</span>
      </div>
    `
  })

  afterEach(() => {
    Element.prototype.scrollIntoView = originalScrollIntoView
  })

  it('finds matches and updates count', () => {
    const { runSearch } = loadSearchFns()
    document.getElementById('searchInput').value = 'hello'

    runSearch()

    const marks = document.querySelectorAll('mark.search-hl')
    expect(marks.length).toBe(2)
    expect(document.getElementById('searchCount').textContent).toBe('1 / 2')
  })

  it('clearHighlights removes highlight marks', () => {
    const { runSearch, clearHighlights } = loadSearchFns()
    document.getElementById('searchInput').value = 'hello'

    runSearch()
    expect(document.querySelectorAll('mark.search-hl').length).toBe(2)

    clearHighlights()
    expect(document.querySelectorAll('mark.search-hl').length).toBe(0)
  })

  it('invalid regex is handled cleanly', () => {
    const { runSearch, _setRegexMode } = loadSearchFns()
    document.getElementById('searchInput').value = '('
    _setRegexMode(true)

    runSearch()

    expect(document.getElementById('searchCount').textContent).toBe('invalid regex')
  })

  it('clearSearch resets count and input', () => {
    const { runSearch, clearSearch } = loadSearchFns()
    const input = document.getElementById('searchInput')
    input.value = 'hello'

    runSearch()
    clearSearch()

    expect(document.getElementById('searchCount').textContent).toBe('')
    expect(input.value).toBe('')
    expect(document.querySelectorAll('mark.search-hl').length).toBe(0)
  })
})
