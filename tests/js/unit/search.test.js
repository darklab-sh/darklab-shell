import { fromDomScripts } from './helpers/extract.js'

const originalScrollIntoView = Element.prototype.scrollIntoView

function loadSearchFns({ tab = { id: 'tab-1', command: 'nmap -sV ip.darklab.sh' } } = {}) {
  const appendLine = (text, cls = '') => {
    const out = document.getElementById('out')
    if (!out) return
    const line = document.createElement('span')
    line.className = `line${cls ? ` ${cls}` : ''}`
    line.textContent = text
    out.appendChild(line)
  }
  return fromDomScripts(
    ['app/static/js/utils.js', 'app/static/js/search.js'],
    {
      document,
      activeTabId: 'tab-1',
      getOutput: () => document.getElementById('out'),
      getTab: () => tab,
      isSearchBarOpen: () => false,
      searchInput: document.getElementById('searchInput'),
      searchCount: document.getElementById('searchCount'),
      searchToggleBtn: document.getElementById('searchToggleBtn'),
      searchSignalSummary: document.getElementById('searchSignalSummary'),
      searchSummaryBtn: document.getElementById('searchSummaryBtn'),
      openSearchFromSignal: (scope) => { window.__openedSearchScope = scope },
      searchCaseBtn: document.getElementById('searchCaseBtn'),
      searchRegexBtn: document.getElementById('searchRegexBtn'),
      searchScopeButtons: Array.from(document.querySelectorAll('[data-search-scope]')),
      searchScope: 'text',
      searchDiscoverabilityPrompted: false,
      acBuiltinCommandRoots: ['commands', 'status'],
      appendLine,
    },
    `{
    runSearch,
    navigateSearch,
    clearHighlights,
    clearSearch,
    setSearchScope,
    prepareSearchBarForOpen,
    refreshSearchDiscoverabilityUi,
    summarizeCurrentOutputSignals,
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
      <button id="searchToggleBtn"></button>
      <span id="searchSignalSummary"></span>
      <button id="searchSummaryBtn"></button>
      <button id="searchCaseBtn"></button>
      <button id="searchRegexBtn"></button>
      <button data-search-scope="text"></button>
      <button data-search-scope="findings"></button>
      <button data-search-scope="warnings"></button>
      <button data-search-scope="errors"></button>
      <button data-search-scope="summaries"></button>
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
        getTab: () => ({ id: 'tab-1', command: '' }),
        isSearchBarOpen: () => false,
        searchInput: document.getElementById('searchInput'),
        searchCount: document.getElementById('searchCount'),
        searchToggleBtn: document.getElementById('searchToggleBtn'),
        searchSignalSummary: document.getElementById('searchSignalSummary'),
        openSearchFromSignal: (scope) => { window.__openedSearchScope = scope },
        searchCaseBtn: document.getElementById('searchCaseBtn'),
        searchRegexBtn: document.getElementById('searchRegexBtn'),
        searchScopeButtons: Array.from(document.querySelectorAll('[data-search-scope]')),
        searchScope: 'text',
        searchDiscoverabilityPrompted: false,
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
        getTab: () => ({ id: 'tab-1', command: '' }),
        isSearchBarOpen: () => false,
        searchInput: document.getElementById('searchInput'),
        searchCount: document.getElementById('searchCount'),
        searchToggleBtn: document.getElementById('searchToggleBtn'),
        searchSignalSummary: document.getElementById('searchSignalSummary'),
        openSearchFromSignal: (scope) => { window.__openedSearchScope = scope },
        searchCaseBtn: document.getElementById('searchCaseBtn'),
        searchRegexBtn: document.getElementById('searchRegexBtn'),
        searchScopeButtons: Array.from(document.querySelectorAll('[data-search-scope]')),
        searchScope: 'text',
        searchDiscoverabilityPrompted: false,
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

  it('scopes to warning lines and navigates between them', () => {
    const { setSearchScope, navigateSearch } = loadSearchFns()
    document.getElementById('out').innerHTML = [
      '<span class="line">normal line</span>',
      '<span class="line notice" data-signals="warnings">warning: API returned a retry-after header</span>',
      '<span class="line">another normal line</span>',
      '<span class="line" data-signals="warnings">Note: Host seems down. If it is really up, but blocking our ping probes...</span>',
    ].join('')

    setSearchScope('warnings')

    const matches = document.querySelectorAll('.line.search-signal-hl')
    expect(matches.length).toBe(2)
    expect(matches[0].classList.contains('current')).toBe(true)
    expect(document.getElementById('searchCount').textContent).toBe('1 / 2')
    expect(document.getElementById('searchInput').disabled).toBe(true)

    navigateSearch(1)

    expect(document.getElementById('searchCount').textContent).toBe('2 / 2')
    expect(matches[1].classList.contains('current')).toBe(true)
  })

  it('scopes to finding lines using server-provided signal metadata', () => {
    const { setSearchScope } = loadSearchFns()
    document.getElementById('out').innerHTML = [
      '<span class="line">Starting Nmap 7.95 ( https://nmap.org )</span>',
      '<span class="line">:: Progress: [10/100] ::</span>',
      '<span class="line">; <<>> DiG 9.18 <<>> darklab.sh MX</span>',
      '<span class="line">noise</span>',
      '<span class="line" data-signals="findings">443/tcp open https</span>',
      '<span class="line" data-signals="findings">ip.darklab.sh [107.178.109.44] 80 (http) open</span>',
      '<span class="line" data-signals="findings">/admin [Status: 200, Size: 420]</span>',
      '<span class="line" data-signals="findings">darklab.sh. 300 IN MX 10 aspmx.l.google.com.</span>',
      '<span class="line" data-signals="findings">104.21.4.35</span>',
      '<span class="line" data-signals="findings">172.67.131.156</span>',
      '<span class="line" data-signals="findings">darklab.sh has address 104.21.4.35</span>',
      '<span class="line" data-signals="findings">darklab.sh mail is handled by 10 aspmx.l.google.com.</span>',
      '<span class="line" data-signals="findings">[medium] [http] [exposed-panel] https://target</span>',
      '<span class="line" data-signals="findings">verify return code: 0 (ok)</span>',
    ].join('')

    setSearchScope('findings')

    const matches = Array.from(document.querySelectorAll('.line.search-signal-hl')).map((el) => el.textContent)
    expect(matches).toEqual([
      '443/tcp open https',
      'ip.darklab.sh [107.178.109.44] 80 (http) open',
      '/admin [Status: 200, Size: 420]',
      'darklab.sh. 300 IN MX 10 aspmx.l.google.com.',
      '104.21.4.35',
      '172.67.131.156',
      'darklab.sh has address 104.21.4.35',
      'darklab.sh mail is handled by 10 aspmx.l.google.com.',
      '[medium] [http] [exposed-panel] https://target',
      'verify return code: 0 (ok)',
    ])
    expect(document.getElementById('searchCount').textContent).toBe('1 / 10')
  })

  it('treats nslookup answer rows as findings when the server marks them', () => {
    const { setSearchScope } = loadSearchFns()
    document.getElementById('out').innerHTML = [
      '<span class="line">Server:  10.0.0.1</span>',
      '<span class="line">Address: 10.0.0.1#53</span>',
      '<span class="line">Non-authoritative answer:</span>',
      '<span class="line">Name: darklab.sh</span>',
      '<span class="line" data-signals="findings">Address: 104.21.4.35</span>',
      '<span class="line" data-signals="findings">darklab.sh mail exchanger = 10 aspmx.l.google.com.</span>',
      '<span class="line" data-signals="findings">darklab.sh text = "v=spf1 include:_spf.google.com ~all"</span>',
    ].join('')

    setSearchScope('findings')

    const matches = Array.from(document.querySelectorAll('.line.search-signal-hl')).map((el) => el.textContent)
    expect(matches).toEqual([
      'Address: 104.21.4.35',
      'darklab.sh mail exchanger = 10 aspmx.l.google.com.',
      'darklab.sh text = "v=spf1 include:_spf.google.com ~all"',
    ])
    expect(document.getElementById('searchCount').textContent).toBe('1 / 3')
  })

  it('clearSearch resets scoped search back to text mode', () => {
    const { setSearchScope, clearSearch } = loadSearchFns()
    document.getElementById('out').innerHTML =
      '<span class="line exit-fail" data-signals="errors">connection timed out</span>'

    setSearchScope('errors')
    clearSearch()

    expect(document.querySelectorAll('.line.search-signal-hl').length).toBe(0)
    expect(document.getElementById('searchInput').disabled).toBe(false)
  })

  it('updates the search button and scope labels with scoped counts', () => {
    const { refreshSearchDiscoverabilityUi } = loadSearchFns()
    document.getElementById('out').innerHTML = [
      '<span class="line notice" data-signals="warnings">warning: retrying after rate limit</span>',
      '<span class="line" data-signals="findings">443/tcp open https</span>',
      '<span class="line exit-fail" data-signals="errors">connection timed out</span>',
    ].join('')

    refreshSearchDiscoverabilityUi()

    expect(document.getElementById('searchToggleBtn').textContent).toBe('⌕ search • 1 finding')
    expect(document.querySelector('[data-search-scope="findings"]').textContent).toBe('findings (1)')
    expect(document.querySelector('[data-search-scope="warnings"]').textContent).toBe('warnings (1)')
    expect(document.querySelector('[data-search-scope="errors"]').textContent).toBe('errors (1)')
    expect(document.querySelector('[data-search-scope="summaries"]').textContent).toBe('summaries (0)')
    expect(document.getElementById('searchSummaryBtn').disabled).toBe(false)
    expect(document.getElementById('searchSignalSummary').textContent).toContain('1F')
    expect(document.getElementById('searchSignalSummary').textContent).toContain('1W')
    expect(document.getElementById('searchSignalSummary').textContent).toContain('1E')
    expect(document.querySelector('[data-search-signal-scope="findings"]').className)
      .toContain('btn btn-ghost btn-compact search-signal-chip')
  })

  it('clears the discoverability pulse when the active output has no findings', () => {
    const { refreshSearchDiscoverabilityUi } = loadSearchFns()
    const searchBtn = document.getElementById('searchToggleBtn')
    document.getElementById('out').innerHTML =
      '<span class="line" data-signals="findings">443/tcp open https</span>'

    refreshSearchDiscoverabilityUi()

    expect(searchBtn.classList.contains('search-discover-pulse')).toBe(true)

    document.getElementById('out').innerHTML = '<span class="line">plain output</span>'
    refreshSearchDiscoverabilityUi()

    expect(searchBtn.classList.contains('search-discover-pulse')).toBe(false)
    expect(searchBtn.textContent).toBe('⌕ search')
  })

  it('signal chips are clickable and route to the matching scope', () => {
    const { refreshSearchDiscoverabilityUi } = loadSearchFns()
    document.getElementById('out').innerHTML = [
      '<span class="line" data-signals="findings">443/tcp open https</span>',
      '<span class="line notice" data-signals="warnings">warning: retrying after rate limit</span>',
      '<span class="line exit-fail" data-signals="errors">connection timed out</span>',
      '<span class="line" data-signals="summaries">Nmap done: 1 IP address (1 host up) scanned in 2.31 seconds</span>',
    ].join('')

    refreshSearchDiscoverabilityUi()
    document.querySelector('[data-search-signal-scope="warnings"]').click()

    expect(window.__openedSearchScope).toBe('warnings')
  })

  it('disables summarize when there are no signals', () => {
    const { refreshSearchDiscoverabilityUi } = loadSearchFns()
    document.getElementById('out').innerHTML = [
      '<span class="line">plain output</span>',
      '<span class="line">still plain output</span>',
    ].join('')

    refreshSearchDiscoverabilityUi()

    expect(document.getElementById('searchSummaryBtn').disabled).toBe(true)
  })

  it('uses server-provided signal metadata for scoped counts and highlights', () => {
    const { refreshSearchDiscoverabilityUi, setSearchScope, runSearch } = loadSearchFns()
    document.getElementById('out').innerHTML = [
      '<span class="line" data-signals="findings">plain server finding</span>',
      '<span class="line">443/tcp open https</span>',
    ].join('')

    refreshSearchDiscoverabilityUi()

    expect(document.querySelector('[data-search-scope="findings"]').textContent).toBe('findings (1)')

    setSearchScope('findings')
    runSearch()

    expect(document.querySelectorAll('.search-signal-hl')).toHaveLength(1)
  })

  it('does not classify plain text without server-provided signal metadata', () => {
    const { refreshSearchDiscoverabilityUi, setSearchScope, runSearch } = loadSearchFns()
    document.getElementById('out').innerHTML = [
      '<span class="line" data-line-index="0" data-command-root="nmap">443/tcp open https</span>',
      '<span class="line">80/tcp open http</span>',
    ].join('')

    refreshSearchDiscoverabilityUi()

    expect(document.querySelector('[data-search-scope="findings"]').textContent).toBe('findings (0)')

    setSearchScope('findings')
    runSearch()

    expect(document.querySelectorAll('.search-signal-hl')).toHaveLength(0)
  })

  it('opens normal search in text mode even when findings are available', () => {
    const { prepareSearchBarForOpen } = loadSearchFns()
    document.getElementById('out').innerHTML = '<span class="line" data-signals="findings">443/tcp open https</span>'

    prepareSearchBarForOpen()

    expect(document.querySelector('[data-search-scope="text"]').getAttribute('aria-pressed')).toBe('true')
    expect(document.querySelector('[data-search-scope="findings"]').textContent).toBe('findings (1)')
    expect(document.getElementById('searchInput').disabled).toBe(false)
  })

  it('scopes to summary lines and ignores detail rows', () => {
    const { setSearchScope } = loadSearchFns()
    document.getElementById('out').innerHTML = [
      '<span class="line" data-signals="findings">443/tcp open https</span>',
      '<span class="line" data-signals="summaries">Nmap done: 1 IP address (1 host up) scanned in 2.31 seconds</span>',
      '<span class="line" data-signals="summaries">3 packets transmitted, 3 received, 0% packet loss</span>',
      '<span class="line" data-signals="summaries">Errors: 12</span>',
    ].join('')

    setSearchScope('summaries')

    const matches = Array.from(document.querySelectorAll('.line.search-signal-hl')).map((el) => el.textContent)
    expect(matches).toEqual([
      'Nmap done: 1 IP address (1 host up) scanned in 2.31 seconds',
      '3 packets transmitted, 3 received, 0% packet loss',
      'Errors: 12',
    ])
    expect(document.getElementById('searchCount').textContent).toBe('1 / 3')
  })

  it('does not count user-killed runs as errors', () => {
    const { refreshSearchDiscoverabilityUi, setSearchScope } = loadSearchFns()
    document.getElementById('out').innerHTML = [
      '<span class="line exit-fail">[killed by user after 54.3s]</span>',
      '<span class="line exit-fail" data-signals="errors">connection timed out</span>',
    ].join('')

    refreshSearchDiscoverabilityUi()
    expect(document.getElementById('searchSignalSummary').textContent).not.toContain('2E')
    expect(document.getElementById('searchSignalSummary').textContent).toContain('1E')

    setSearchScope('errors')
    const matches = Array.from(document.querySelectorAll('.line.search-signal-hl')).map((el) => el.textContent)
    expect(matches).toEqual(['connection timed out'])
  })

  it('appends a synthetic signal summary without inflating scoped counts', () => {
    const { summarizeCurrentOutputSignals, refreshSearchDiscoverabilityUi } = loadSearchFns()
    document.getElementById('out').innerHTML = [
      '<span class="line" data-signals="findings">443/tcp open https</span>',
      '<span class="line notice" data-signals="warnings">warning: retrying request</span>',
      '<span class="line exit-fail" data-signals="errors">connection timeout reached</span>',
      '<span class="line" data-signals="summaries">Nmap done: 1 IP address (1 host up) scanned in 1.23 seconds</span>',
    ].join('')

    summarizeCurrentOutputSignals()

    const lines = Array.from(document.querySelectorAll('#out .line')).map((line) => line.textContent)
    expect(lines).toContain('Command Findings:')
    expect(lines).not.toContain('')
    expect(lines).toContain('findings (1)')
    expect(lines).toContain('- 443/tcp open https')
    expect(lines).toContain('warnings (1)')
    expect(lines).toContain('errors (1)')
    expect(lines).toContain('summaries (1)')

    const counts = refreshSearchDiscoverabilityUi()
    expect(counts).toEqual({ findings: 1, warnings: 1, errors: 1, summaries: 1 })
  })

  it('summarizes each command block in a reused tab', () => {
    const { summarizeCurrentOutputSignals } = loadSearchFns({
      tab: {
        id: 'tab-1',
        command: 'nmap -sV ip.darklab.sh',
      },
    })
    document.getElementById('out').innerHTML = [
      '<span class="line prompt-echo">$ curl old.example</span>',
      '<span class="line" data-signals="findings" data-command-root="curl" data-signal-target="old.example">HTTP/1.1 200 OK</span>',
      '<span class="line notice" data-signals="warnings" data-command-root="curl" data-signal-target="old.example">warning: old warning</span>',
      '<span class="line exit-fail" data-signals="errors" data-command-root="curl" data-signal-target="old.example">old error</span>',
      '<span class="line prompt-echo">$ nmap -sV ip.darklab.sh</span>',
      '<span class="line" data-signals="findings" data-command-root="nmap" data-signal-target="ip.darklab.sh">443/tcp open https</span>',
      '<span class="line notice" data-signals="warnings" data-command-root="nmap" data-signal-target="ip.darklab.sh">warning: fresh warning</span>',
      '<span class="line exit-fail" data-signals="errors" data-command-root="nmap" data-signal-target="ip.darklab.sh">fresh error</span>',
      '<span class="line" data-signals="summaries" data-command-root="nmap" data-signal-target="ip.darklab.sh">Nmap done: 1 IP address (1 host up) scanned in 1.23 seconds</span>',
    ].join('')

    summarizeCurrentOutputSignals()

    const lines = Array.from(document.querySelectorAll('#out .line')).map((line) => line.textContent)
    expect(lines).toContain('full command        curl old.example')
    expect(lines).toContain('full command        nmap -sV ip.darklab.sh')
    expect(lines).toContain('------------')
    expect(lines).toContain('- HTTP/1.1 200 OK')
    expect(lines).toContain('- warning: old warning')
    expect(lines).toContain('- old error')
    expect(lines).toContain('- 443/tcp open https')
    expect(lines).toContain('- warning: fresh warning')
    expect(lines).toContain('- fresh error')
  })

  it('groups summary output by server-provided command and target metadata', () => {
    const { summarizeCurrentOutputSignals } = loadSearchFns({
      tab: {
        id: 'tab-1',
        command: 'nmap --top-ports 20 ip.darklab.sh',
      },
    })
    document.getElementById('out').innerHTML = [
      '<span class="line prompt-echo">$ nmap -sV ip.darklab.sh</span>',
      '<span class="line" data-signals="findings" data-command-root="nmap" data-signal-target="ip.darklab.sh">80/tcp open http</span>',
      '<span class="line" data-signals="summaries" data-command-root="nmap" data-signal-target="ip.darklab.sh">Nmap done: 1 IP address (1 host up) scanned in 2.11 seconds</span>',
      '<span class="line prompt-echo">$ nmap --top-ports 20 ip.darklab.sh</span>',
      '<span class="line" data-signals="findings" data-command-root="nmap" data-signal-target="ip.darklab.sh">443/tcp open https</span>',
      '<span class="line notice" data-signals="warnings" data-command-root="nmap" data-signal-target="ip.darklab.sh">warning: timing results may be unreliable</span>',
    ].join('')

    summarizeCurrentOutputSignals()

    const lines = Array.from(document.querySelectorAll('#out .line')).map((line) => line.textContent)
    expect(lines).toContain('command             nmap')
    expect(lines).toContain('target              ip.darklab.sh')
    expect(lines).toContain('full commands (2)')
    expect(lines).toContain('- nmap -sV ip.darklab.sh')
    expect(lines).toContain('- nmap --top-ports 20 ip.darklab.sh')
    expect(lines).toContain('findings (2)')
    expect(lines).toContain('- 80/tcp open http')
    expect(lines).toContain('- 443/tcp open https')
    expect(lines).toContain('warnings (1)')
    expect(lines).toContain('summaries (1)')
  })

  it('deduplicates repeated full commands in grouped summary output', () => {
    const { summarizeCurrentOutputSignals } = loadSearchFns({
      tab: {
        id: 'tab-1',
        command: 'nmap -sT ip.darklab.sh',
      },
    })
    document.getElementById('out').innerHTML = [
      '<span class="line prompt-echo">$ nmap -sT ip.darklab.sh</span>',
      '<span class="line" data-signals="findings" data-command-root="nmap" data-signal-target="ip.darklab.sh">80/tcp open http</span>',
      '<span class="line prompt-echo">$ nmap -sT ip.darklab.sh</span>',
      '<span class="line" data-signals="findings" data-command-root="nmap" data-signal-target="ip.darklab.sh">443/tcp open https</span>',
      '<span class="line prompt-echo">$ nmap -sV ip.darklab.sh</span>',
      '<span class="line" data-signals="findings" data-command-root="nmap" data-signal-target="ip.darklab.sh">22/tcp open ssh</span>',
    ].join('')

    summarizeCurrentOutputSignals()

    const lines = Array.from(document.querySelectorAll('#out .line')).map((line) => line.textContent)
    expect(lines).toContain('full commands (2)')
    expect(lines).toContain('- nmap -sT ip.darklab.sh (2)')
    expect(lines).toContain('- nmap -sV ip.darklab.sh')
    expect(lines.filter((line) => line === '- nmap -sT ip.darklab.sh')).toHaveLength(0)
    expect(lines).toContain('findings (3)')
  })

  it('deduplicates repeated findings in grouped summary output', () => {
    const { summarizeCurrentOutputSignals } = loadSearchFns({
      tab: {
        id: 'tab-1',
        command: 'dig darklab.sh +short',
      },
    })
    document.getElementById('out').innerHTML = [
      '<span class="line prompt-echo">$ dig darklab.sh +short</span>',
      '<span class="line" data-signals="findings" data-command-root="dig" data-signal-target="darklab.sh">104.21.4.35</span>',
      '<span class="line" data-signals="findings" data-command-root="dig" data-signal-target="darklab.sh">172.67.131.156</span>',
      '<span class="line prompt-echo">$ dig darklab.sh +short</span>',
      '<span class="line" data-signals="findings" data-command-root="dig" data-signal-target="darklab.sh">104.21.4.35</span>',
      '<span class="line" data-signals="findings" data-command-root="dig" data-signal-target="darklab.sh">172.67.131.156</span>',
    ].join('')

    summarizeCurrentOutputSignals()

    const lines = Array.from(document.querySelectorAll('#out .line')).map((line) => line.textContent)
    expect(lines).toContain('command             dig')
    expect(lines).toContain('target              darklab.sh')
    expect(lines).toContain('full commands (1)')
    expect(lines).toContain('- dig darklab.sh +short (2)')
    expect(lines).toContain('findings (2)')
    expect(lines).toContain('- 104.21.4.35 (2)')
    expect(lines).toContain('- 172.67.131.156 (2)')
    expect(lines.filter((line) => line === '- 104.21.4.35')).toHaveLength(0)
    expect(lines.filter((line) => line === '- 172.67.131.156')).toHaveLength(0)
  })

  it('groups summary output by server-provided command metadata for opaque command text', () => {
    const { summarizeCurrentOutputSignals } = loadSearchFns({
      tab: {
        id: 'tab-1',
        command: 'scanner --opaque',
      },
    })
    document.getElementById('out').innerHTML = [
      '<span class="line prompt-echo">$ scanner --opaque</span>',
      '<span class="line" data-signals="findings" data-command-root="nmap" data-signal-target="ip.darklab.sh">plain server finding</span>',
    ].join('')

    summarizeCurrentOutputSignals()

    const lines = Array.from(document.querySelectorAll('#out .line')).map((line) => line.textContent)
    expect(lines).toContain('command             nmap')
    expect(lines).toContain('target              ip.darklab.sh')
    expect(lines).toContain('full command        scanner --opaque')
    expect(lines).toContain('findings (1)')
    expect(lines).toContain('- plain server finding')
  })

  it('groups nc summary output by host instead of positional ports', () => {
    const { summarizeCurrentOutputSignals } = loadSearchFns({
      tab: {
        id: 'tab-1',
        command: 'nc -zv ip.darklab.sh 443 80',
      },
    })
    document.getElementById('out').innerHTML = [
      '<span class="line prompt-echo">$ nc -zv ip.darklab.sh 80</span>',
      '<span class="line" data-signals="findings" data-command-root="nc" data-signal-target="ip.darklab.sh">ip.darklab.sh [107.178.109.44] 80 (http) open</span>',
      '<span class="line prompt-echo">$ nc -zv ip.darklab.sh 443 80</span>',
      '<span class="line" data-signals="findings" data-command-root="nc" data-signal-target="ip.darklab.sh">ip.darklab.sh [107.178.109.44] 443 (https) open</span>',
      '<span class="line" data-signals="findings" data-command-root="nc" data-signal-target="ip.darklab.sh">ip.darklab.sh [107.178.109.44] 80 (http) open</span>',
    ].join('')

    summarizeCurrentOutputSignals()

    const lines = Array.from(document.querySelectorAll('#out .line')).map((line) => line.textContent)
    expect(lines).toContain('command             nc')
    expect(lines).toContain('target              ip.darklab.sh')
    expect(lines).toContain('full commands (2)')
    expect(lines).toContain('- nc -zv ip.darklab.sh 80')
    expect(lines).toContain('- nc -zv ip.darklab.sh 443 80')
    expect(lines).toContain('findings (2)')
    expect(lines).toContain('- ip.darklab.sh [107.178.109.44] 80 (http) open (2)')
    expect(lines).toContain('- ip.darklab.sh [107.178.109.44] 443 (https) open')
    expect(lines).not.toContain('full command        nc -zv ip.darklab.sh 80')
    expect(lines).not.toContain('target              ip.darklab.sh, 80')
  })

  it('splits one command block by server-provided per-line targets', () => {
    const { summarizeCurrentOutputSignals } = loadSearchFns({
      tab: {
        id: 'tab-1',
        command: 'nmap -iL darklab_inputs.txt -sT',
      },
    })
    document.getElementById('out').innerHTML = [
      '<span class="line prompt-echo">$ nmap -iL darklab_inputs.txt -sT</span>',
      '<span class="line" data-command-root="nmap" data-signal-target="ip.darklab.sh">Nmap scan report for ip.darklab.sh (192.168.20.5)</span>',
      '<span class="line" data-signals="findings" data-command-root="nmap" data-signal-target="ip.darklab.sh">80/tcp   open  http</span>',
      '<span class="line" data-signals="findings" data-command-root="nmap" data-signal-target="ip.darklab.sh">443/tcp  open  https</span>',
      '<span class="line" data-command-root="nmap" data-signal-target="h.darklab.sh">Nmap scan report for h.darklab.sh (108.79.194.246)</span>',
      '<span class="line" data-signals="findings" data-command-root="nmap" data-signal-target="h.darklab.sh">80/tcp   open   http</span>',
      '<span class="line" data-signals="findings" data-command-root="nmap" data-signal-target="h.darklab.sh">443/tcp  open   https</span>',
    ].join('')

    summarizeCurrentOutputSignals()

    const lines = Array.from(document.querySelectorAll('#out .line')).map((line) => line.textContent)
    expect(lines).toContain('command             nmap')
    expect(lines).toContain('target              ip.darklab.sh')
    expect(lines).toContain('target              h.darklab.sh')
    expect(lines.filter((line) => line === 'full command        nmap -iL darklab_inputs.txt -sT')).toHaveLength(2)
    expect(lines).toContain('- 80/tcp   open  http')
    expect(lines).toContain('- 443/tcp  open  https')
    expect(lines).toContain('- 80/tcp   open   http')
    expect(lines).toContain('- 443/tcp  open   https')
  })

  it('falls back to command summaries when a target cannot be extracted', () => {
    const { summarizeCurrentOutputSignals } = loadSearchFns({
      tab: {
        id: 'tab-1',
        command: 'customscan --latest',
      },
    })
    document.getElementById('out').innerHTML = [
      '<span class="line prompt-echo">$ customscan --latest</span>',
      '<span class="line" data-signals="warnings" data-command-root="customscan">warning: custom scanner found something</span>',
      '<span class="line" data-signals="summaries" data-command-root="customscan">summary: 1 issue</span>',
    ].join('')

    summarizeCurrentOutputSignals()

    const lines = Array.from(document.querySelectorAll('#out .line')).map((line) => line.textContent)
    expect(lines).toContain('full command        customscan --latest')
    expect(lines).not.toContain('command             customscan')
    expect(lines).not.toContain('target              --latest')
    expect(lines).toContain('warnings (1)')
    expect(lines).toContain('summaries (1)')
  })

  it('ignores built-in command output for signals and summaries', () => {
    const { summarizeCurrentOutputSignals, refreshSearchDiscoverabilityUi, setSearchScope } = loadSearchFns({
      tab: {
        id: 'tab-1',
        command: 'status',
      },
    })
    document.getElementById('out').innerHTML = [
      '<span class="line prompt-echo">$ status</span>',
      '<span class="line">database online</span>',
      '<span class="line notice">warning: built-in note</span>',
      '<span class="line exit-fail">built-in timeout</span>',
      '<span class="line">summary: built-in summary</span>',
      '<span class="line prompt-echo">$ host darklab.sh</span>',
      '<span class="line" data-signals="findings" data-command-root="host" data-signal-target="darklab.sh">darklab.sh has address 104.21.4.35</span>',
    ].join('')

    const counts = refreshSearchDiscoverabilityUi()
    expect(counts).toEqual({ findings: 1, warnings: 0, errors: 0, summaries: 0 })

    setSearchScope('warnings')
    expect(Array.from(document.querySelectorAll('.line.search-signal-hl')).map((el) => el.textContent)).toEqual([])

    summarizeCurrentOutputSignals()

    const lines = Array.from(document.querySelectorAll('#out .line')).map((line) => line.textContent)
    expect(lines).toContain('command             host')
    expect(lines).toContain('target              darklab.sh')
    expect(lines).toContain('- darklab.sh has address 104.21.4.35')
    expect(lines).not.toContain('full command        status')
    expect(lines).not.toContain('- warning: built-in note')
    expect(lines).not.toContain('- built-in timeout')
    expect(lines).not.toContain('- summary: built-in summary')
  })

  it('omits command blocks that have no signals', () => {
    const { summarizeCurrentOutputSignals } = loadSearchFns({
      tab: {
        id: 'tab-1',
        command: 'whois darklab.sh',
      },
    })
    document.getElementById('out').innerHTML = [
      '<span class="line prompt-echo">$ commands --external</span>',
      '<span class="line">curl</span>',
      '<span class="line">host</span>',
      '<span class="line">whois</span>',
      '<span class="line prompt-echo">$ host darklab.sh</span>',
      '<span class="line" data-signals="findings" data-command-root="host" data-signal-target="darklab.sh">darklab.sh has address 104.21.4.35</span>',
      '<span class="line" data-signals="findings" data-command-root="host" data-signal-target="darklab.sh">darklab.sh mail is handled by 1 aspmx.l.google.com.</span>',
      '<span class="line prompt-echo">$ whois darklab.sh</span>',
      '<span class="line">Domain Name: DARKLAB.SH</span>',
      '<span class="line">Registry Expiry Date: 2027-04-01T00:00:00Z</span>',
    ].join('')

    summarizeCurrentOutputSignals()

    const lines = Array.from(document.querySelectorAll('#out .line')).map((line) => line.textContent)
    expect(lines).toContain('command             host')
    expect(lines).not.toContain('full command        commands --external')
    expect(lines).not.toContain('full command        whois darklab.sh')
    expect(lines).not.toContain('No findings, warnings, errors, or summary lines detected for this command.')
  })
})
