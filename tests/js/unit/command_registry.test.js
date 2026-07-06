import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fromDomScripts } from './helpers/extract.js'

function setupCatalogDom() {
  document.body.innerHTML = `
    <div id="command-catalog-overlay"></div>
    <div id="command-catalog-body"></div>
    <div class="faq-body"></div>
    <input id="cmd" />
  `
}

function setupRegistryDom() {
  document.body.innerHTML = `
    <div id="command-registry-overlay"></div>
    <div id="command-registry-subtitle"></div>
    <input id="command-registry-search" />
    <button id="command-registry-categories-scroll-left" class="tabs-scroll-btn u-hidden"></button>
    <div id="command-registry-categories"></div>
    <button id="command-registry-categories-scroll-right" class="tabs-scroll-btn u-hidden"></button>
    <div id="command-registry-body"></div>
    <div id="command-catalog-overlay"></div>
    <div id="command-catalog-body"></div>
  `
}

// Returns the base globals shared across both test loaders.
// Called lazily inside each loader so `document` and `window` are available
// (they are injected by the jsdom environment only when tests actually run,
// not at module-load time).
function registryGlobals(extra = {}) {
  return {
    document,
    window,
    commandCatalogOverlay: null,
    faqBody: null,
    commandRegistryOverlay: null,
    commandRegistryBody: null,
    commandRegistrySearch: null,
    commandRegistryCategories: null,
    apiFetch: () => {},
    logClientError: () => {},
    setComposerValue: () => {},
    ...extra,
  }
}

function loadRegistryFns() {
  setupCatalogDom()
  // dom.js cannot be included in relPaths: its const declarations would create a
  // temporal dead zone conflict with ui_helpers.js's IIFE (which references searchBar
  // at module-evaluation time, before dom.js runs). Pass the handful of DOM
  // references needed by renderCommandCatalogModal as explicit globals instead.
  const commandCatalogBody = document.getElementById('command-catalog-body')
  return fromDomScripts(
    ['app/static/js/features/command-registry/command_registry.js'],
    registryGlobals({ commandCatalogBody }),
    '{ renderCommandCatalogModal }',
  )
}

function loadPipeFns() {
  document.body.innerHTML = ''
  return fromDomScripts(
    ['app/static/js/features/command-registry/command_registry.js'],
    registryGlobals({ commandCatalogBody: null }),
    '{ makeCommandRegistryPipeSection }',
  )
}

function loadRowFns(extra = {}) {
  setupCatalogDom()
  return fromDomScripts(
    ['app/static/js/features/command-registry/command_registry.js'],
    registryGlobals({
      commandCatalogBody: document.getElementById('command-catalog-body'),
      ...extra,
    }),
    '{ makeCommandRegistryRow }',
  )
}

function loadRegistryBrowserFns(extra = {}) {
  setupRegistryDom()
  return fromDomScripts(
    ['app/static/js/features/command-registry/command_registry.js'],
    registryGlobals({
      commandCatalogBody: document.getElementById('command-catalog-body'),
      commandRegistryBody: document.getElementById('command-registry-body'),
      commandRegistryCategories: document.getElementById('command-registry-categories'),
      commandRegistryOverlay: document.getElementById('command-registry-overlay'),
      commandRegistrySearch: document.getElementById('command-registry-search'),
      commandRegistrySubtitle: document.getElementById('command-registry-subtitle'),
      ...extra,
    }),
    '{ renderCommandRegistry }',
  )
}

describe('renderCommandCatalogModal — knowledge sections', () => {
  let renderCommandCatalogModal
  let body

  beforeEach(() => {
    ;({ renderCommandCatalogModal } = loadRegistryFns())
    body = document.getElementById('command-catalog-body')
  })

  function sectionTitles() {
    return [...body.querySelectorAll('.command-catalog-section-title')].map(el => el.textContent)
  }

  function tokenTexts() {
    return [...body.querySelectorAll('.command-catalog-token')].map(el => el.textContent)
  }

  it('renders Notes section when data.knowledge.notes is non-empty', () => {
    renderCommandCatalogModal({ root: 'nmap', knowledge: { notes: ['Check rate limits.'] } })
    expect(sectionTitles()).toContain('Notes')
    expect(tokenTexts()).toContain('Check rate limits.')
  })

  it('renders all four list knowledge sections with their items', () => {
    renderCommandCatalogModal({
      root: 'nmap',
      knowledge: {
        notes: ['Note one.'],
        gotchas: ['Gotcha one.'],
        safe_defaults: ['Default one.'],
        common_flags: ['Flag one.'],
      },
    })
    const titles = sectionTitles()
    expect(titles).toContain('Notes')
    expect(titles).toContain('Gotchas')
    expect(titles).toContain('Safe Defaults')
    expect(titles).toContain('Common Flags')
    const tokens = tokenTexts()
    expect(tokens).toContain('Note one.')
    expect(tokens).toContain('Gotcha one.')
    expect(tokens).toContain('Default one.')
    expect(tokens).toContain('Flag one.')
  })

  it('renders artifact_behavior as a single-item Artifact Behavior section', () => {
    renderCommandCatalogModal({
      root: 'nmap',
      knowledge: { artifact_behavior: 'Creates scan.json in the workspace.' },
    })
    expect(sectionTitles()).toContain('Artifact Behavior')
    expect(tokenTexts()).toContain('Creates scan.json in the workspace.')
  })

  it('omits all knowledge sections when knowledge is absent', () => {
    renderCommandCatalogModal({ root: 'nmap' })
    const titles = sectionTitles()
    expect(titles).not.toContain('Notes')
    expect(titles).not.toContain('Gotchas')
    expect(titles).not.toContain('Safe Defaults')
    expect(titles).not.toContain('Common Flags')
    expect(titles).not.toContain('Artifact Behavior')
  })

  it('omits list knowledge sections when all arrays are empty', () => {
    renderCommandCatalogModal({
      root: 'nmap',
      knowledge: { notes: [], gotchas: [], safe_defaults: [], common_flags: [] },
    })
    const titles = sectionTitles()
    expect(titles).not.toContain('Notes')
    expect(titles).not.toContain('Gotchas')
    expect(titles).not.toContain('Safe Defaults')
    expect(titles).not.toContain('Common Flags')
  })

  it('omits Artifact Behavior section when artifact_behavior is absent', () => {
    renderCommandCatalogModal({ root: 'nmap', knowledge: {} })
    expect(sectionTitles()).not.toContain('Artifact Behavior')
  })
})

describe('makeCommandRegistryPipeSection', () => {
  let makeCommandRegistryPipeSection

  beforeEach(() => {
    ;({ makeCommandRegistryPipeSection } = loadPipeFns())
  })

  it('renders pipe helpers section with title and pipe rows', () => {
    const pipes = [
      { root: 'grep', description: 'Filter lines by pattern' },
      { root: 'head', description: 'Show the first lines' },
    ]
    const section = makeCommandRegistryPipeSection(pipes)
    expect(section).not.toBeNull()
    const title = section.querySelector('.command-catalog-section-title')
    expect(title.textContent).toBe('App-native pipe helpers')
    const tokens = [...section.querySelectorAll('.command-catalog-token')].map(el => el.textContent)
    expect(tokens).toContain('grep')
    expect(tokens).toContain('head')
  })

  it('renders disclaimer text', () => {
    const section = makeCommandRegistryPipeSection([
      { root: 'grep', description: 'Filter lines by pattern' },
    ])
    expect(section).not.toBeNull()
    const disclaimer = section.querySelector('.command-catalog-note')
    expect(disclaimer.textContent).toContain('App-managed filters')
    expect(disclaimer.textContent).toContain('not arbitrary shell pipelines')
  })

  it('returns null when pipe_helpers is an empty array', () => {
    expect(makeCommandRegistryPipeSection([])).toBeNull()
  })

  it('returns null when pipe_helpers is absent', () => {
    expect(makeCommandRegistryPipeSection(null)).toBeNull()
    expect(makeCommandRegistryPipeSection(undefined)).toBeNull()
  })
})

describe('makeCommandRegistryRow', () => {
  it('binds generated command rows through the shared pressable primitive', () => {
    const bindPressable = vi.fn((el, options) => {
      el.dataset.boundByPressable = '1'
      el.addEventListener('click', options.onActivate)
    })
    const { makeCommandRegistryRow } = loadRowFns({ bindPressable })

    const row = makeCommandRegistryRow({
      root: 'nmap',
      category: 'Scanning',
      description: 'Scan hosts',
    })

    expect(row).not.toBeNull()
    expect(bindPressable).toHaveBeenCalledTimes(1)
    expect(bindPressable).toHaveBeenCalledWith(row, {
      onActivate: expect.any(Function),
      clearPressStyle: true,
    })
    expect(row.dataset.boundByPressable).toBe('1')
  })
})

describe('renderCommandRegistry — category scrollers', () => {
  it('shows arrow controls only when categories overflow and scrolls the chip strip', () => {
    window.commandRegistryData = {
      commands: [
        { root: 'nmap', category: 'Discovery', description: 'Scan hosts' },
        { root: 'nuclei', category: 'Templates', description: 'Run templates' },
        { root: 'httpx', category: 'HTTP', description: 'Probe HTTP services' },
        { root: 'subfinder', category: 'DNS', description: 'Find domains' },
      ],
    }
    const { renderCommandRegistry } = loadRegistryBrowserFns()
    const categories = document.getElementById('command-registry-categories')
    const left = document.getElementById('command-registry-categories-scroll-left')
    const right = document.getElementById('command-registry-categories-scroll-right')
    Object.defineProperty(categories, 'clientWidth', { configurable: true, value: 120 })
    Object.defineProperty(categories, 'scrollWidth', { configurable: true, value: 300 })
    categories.scrollBy = ({ left: delta }) => {
      categories.scrollLeft += delta
      categories.dispatchEvent(new Event('scroll'))
    }

    renderCommandRegistry()

    expect(left.classList.contains('u-hidden')).toBe(false)
    expect(right.classList.contains('u-hidden')).toBe(false)
    expect(left.disabled).toBe(true)
    expect(right.disabled).toBe(false)

    right.click()

    expect(categories.scrollLeft).toBeGreaterThan(0)
    expect(left.disabled).toBe(false)

    categories.scrollLeft = 180
    categories.dispatchEvent(new Event('scroll'))

    expect(right.disabled).toBe(true)
  })
})
