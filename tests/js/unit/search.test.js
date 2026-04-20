import { fromDomScripts } from './helpers/extract.js'

const originalScrollIntoView = Element.prototype.scrollIntoView

function loadSearchFns() {
  return fromDomScripts(
    ['app/static/js/utils.js', 'app/static/js/search.js'],
    {
      document,
      activeTabId: 'tab-1',
      getOutput: () => document.getElementById('out'),
      searchInput: document.getElementById('searchInput'),
      searchCount: document.getElementById('searchCount'),
    },
    `{
    runSearch,
    navigateSearch,
    clearHighlights,
    clearSearch,
    _setRegexMode: (value) => { searchRegexMode = value; },
  }`,
  )
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

  it('runSearch leaves the UI unchanged when the query is blank', () => {
    const { runSearch } = loadSearchFns()
    const count = document.getElementById('searchCount')
    count.textContent = 'stale'
    document.getElementById('searchInput').value = ''

    runSearch()

    expect(count.textContent).toBe('')
    expect(document.querySelectorAll('mark.search-hl').length).toBe(0)
  })

  it('runSearch is a no-op when the active tab has no output', () => {
    const { runSearch } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/search.js'],
      {
        document,
        activeTabId: 'tab-1',
        getOutput: () => null,
        searchInput: document.getElementById('searchInput'),
        searchCount: document.getElementById('searchCount'),
      },
      `{
      runSearch,
    }`,
    )

    document.getElementById('searchInput').value = 'hello'
    runSearch()

    expect(document.getElementById('searchCount').textContent).toBe('')
  })

  it('navigateSearch is a no-op when there are no matches', () => {
    const { navigateSearch } = loadSearchFns()
    document.getElementById('searchInput').value = 'missing'

    navigateSearch(1)

    expect(document.getElementById('searchCount').textContent).toBe('')
  })

  it('clearHighlights is safe when no output has been rendered', () => {
    const { clearHighlights } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/search.js'],
      {
        document,
        activeTabId: 'tab-1',
        getOutput: () => null,
        searchInput: document.getElementById('searchInput'),
        searchCount: document.getElementById('searchCount'),
      },
      `{
      clearHighlights,
    }`,
    )

    expect(() => clearHighlights()).not.toThrow()
  })

  it('highlights mixed-content lines without flattening helper markup', () => {
    const { runSearch, clearHighlights } = loadSearchFns()
    document.getElementById('searchInput').value = 'curl localhost'
    document.getElementById('out').innerHTML =
      '<span class="line"><span class="line-prefix">$</span>curl <span class="line-host">localhost</span></span>'

    runSearch()

    const line = document.querySelector('.line')
    const marks = document.querySelectorAll('mark.search-hl')
    // A match that crosses an inline-element boundary produces one `<mark>`
    // per text-node segment (DOM limitation), but the two marks share a
    // `data-search-match` index so nav treats them as a single logical match.
    expect(marks.length).toBe(2)
    expect(marks[0].dataset.searchMatch).toBe(marks[1].dataset.searchMatch)
    expect(document.getElementById('searchCount').textContent).toBe('1 / 1')
    expect(line?.querySelector('.line-prefix')).not.toBeNull()
    expect(line?.querySelector('.line-host')).not.toBeNull()

    clearHighlights()

    expect(document.querySelectorAll('mark.search-hl').length).toBe(0)
    expect(document.querySelector('.line')?.querySelector('.line-prefix')).not.toBeNull()
    expect(document.querySelector('.line')?.querySelector('.line-host')).not.toBeNull()
  })

  it('merges adjacent text nodes between searches so a fragmented line is not re-split per fragment', () => {
    const { runSearch, clearHighlights } = loadSearchFns()
    const input = document.getElementById('searchInput')
    document.getElementById('out').innerHTML = '<span class="line">--- darklab.sh ping statistics ---</span>'

    // First search leaves the DOM fragmented: the "p" mark gets replaced with
    // a text node but the sibling text nodes do not auto-merge. A second
    // search for "ping" should produce one `<mark>` wrapping the whole word,
    // not multiple marks with visible pill gaps.
    input.value = 'p'
    runSearch()
    expect(document.querySelectorAll('mark.search-hl').length).toBeGreaterThan(0)
    clearHighlights()

    input.value = 'ping'
    runSearch()

    // Single plain-text match → single `<mark>`, not one-per-character.
    const marks = document.querySelectorAll('mark.search-hl')
    expect(marks.length).toBe(1)
    expect(marks[0].textContent).toBe('ping')
  })

  it('navigates by logical match across inline-element boundaries', () => {
    const { runSearch, navigateSearch } = loadSearchFns()
    document.getElementById('searchInput').value = 'curl localhost'
    document.getElementById('out').innerHTML =
      '<span class="line"><span class="line-prefix">$</span>curl <span class="line-host">localhost</span></span>' +
      '<span class="line"><span class="line-prefix">$</span>curl <span class="line-host">localhost</span> again</span>'

    runSearch()

    // Two logical matches, four DOM marks (two per match). Counter reads 1/2,
    // not 1/4; Enter/arrow advances to match 2, not to the second segment of
    // match 1.
    expect(document.querySelectorAll('mark.search-hl').length).toBe(4)
    expect(document.getElementById('searchCount').textContent).toBe('1 / 2')

    navigateSearch(1)
    expect(document.getElementById('searchCount').textContent).toBe('2 / 2')

    navigateSearch(1)
    expect(document.getElementById('searchCount').textContent).toBe('1 / 2')

    navigateSearch(-1)
    expect(document.getElementById('searchCount').textContent).toBe('2 / 2')
  })
})
