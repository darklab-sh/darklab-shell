// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { beforeEach, describe, expect, it } from 'vitest'
import { fromDomScripts } from './helpers/extract.js'

// ── extractGrepOutputTokens + getGrepOutputSuggestions (runtime_context.js) ──

function loadRuntimeFns(globals = {}) {
  return fromDomScripts(
    ['app/static/js/core/autocomplete_core.js', 'app/static/js/features/autocomplete/runtime_context.js'],
    {
      document,
      window,
      APP_CONFIG: { workspace_enabled: false },
      ...globals,
    },
    `{
      extractGrepOutputTokens,
      getGrepOutputSuggestions,
      _buildItem: DarklabAutocompleteCore.buildItem,
      _filterItems: DarklabAutocompleteCore.filterItems,
    }`,
  )
}

describe('extractGrepOutputTokens', () => {
  let extractGrepOutputTokens

  beforeEach(() => {
    ;({ extractGrepOutputTokens } = loadRuntimeFns())
  })

  it('returns an empty array for blank input', () => {
    expect(extractGrepOutputTokens('')).toEqual([])
    expect(extractGrepOutputTokens('   \n  ')).toEqual([])
  })

  it('extracts IPv4 addresses and rejects out-of-range octets', () => {
    expect(extractGrepOutputTokens('host 192.168.1.10 up')).toContain('192.168.1.10')
    expect(extractGrepOutputTokens('bogus 999.999.999.999 here')).toEqual([])
  })

  it('extracts compressed and full IPv6 but not clock timestamps', () => {
    expect(extractGrepOutputTokens('addr 2001:db8::1 reachable')).toContain('2001:db8::1')
    expect(extractGrepOutputTokens('started at 12:34:56 today')).not.toContain('12:34:56')
  })

  it('extracts hostnames', () => {
    expect(extractGrepOutputTokens('resolved scan.example.com fine')).toContain('scan.example.com')
  })

  it('extracts CVE identifiers case-insensitively', () => {
    expect(extractGrepOutputTokens('found CVE-2021-44228 in log')).toContain('CVE-2021-44228')
  })

  it('does not also surface a CVE id as a bare word', () => {
    const tokens = extractGrepOutputTokens('CVE-2021-44228 CVE-2021-44228 CVE-2021-44228')
    expect(tokens).toContain('CVE-2021-44228')
    expect(tokens.filter(t => t.toLowerCase().includes('cve-2021-44228'))).toHaveLength(1)
  })

  it('extracts HTTP status codes meeting the minimum occurrence', () => {
    const tokens = extractGrepOutputTokens('GET a 404\nGET b 404\nGET c 200')
    expect(tokens).toContain('404') // appears twice → meets minCount
    expect(tokens).not.toContain('200') // appears once → below minCount
  })

  it('does not surface IP octets as HTTP status codes', () => {
    expect(extractGrepOutputTokens('1.2.3.4 1.2.3.4 1.2.3.4')).not.toContain('200')
    expect(extractGrepOutputTokens('1.2.3.4 1.2.3.4 1.2.3.4')).not.toContain('123')
  })

  it('extracts frequently repeated words above the threshold and ranks by frequency', () => {
    const tokens = extractGrepOutputTokens('alpha alpha alpha beta beta gamma')
    expect(tokens).toContain('alpha') // 3 occurrences → meets minCount
    expect(tokens).not.toContain('beta') // 2 occurrences → below word minCount
    expect(tokens).not.toContain('gamma')
  })

  it('orders structured tokens (IP, CVE) ahead of frequent words', () => {
    const text = 'noise noise noise noise 10.0.0.1 10.0.0.1'
    const tokens = extractGrepOutputTokens(text)
    expect(tokens.indexOf('10.0.0.1')).toBeLessThan(tokens.indexOf('noise'))
  })

  it('caps the number of returned tokens', () => {
    const words = Array.from({ length: 40 }, (_, i) => `word${i} word${i} word${i}`).join(' ')
    expect(extractGrepOutputTokens(words, 5)).toHaveLength(5)
  })
})

describe('getGrepOutputSuggestions', () => {
  function buildHarness(outputHtml, { activeTabId = 'tab1' } = {}) {
    document.body.innerHTML = `<div id="output-tab1">${outputHtml}</div><div id="output-tab2"></div>`
    const getOutput = (id) => document.getElementById(`output-${id}`)
    return loadRuntimeFns({ getOutput, activeTabId })
  }

  const ctx = { tokenStart: 12, tokenEnd: 12, currentToken: '' }

  it('builds suggestions from the active tab output lines', () => {
    const { getGrepOutputSuggestions, _buildItem, _filterItems } = buildHarness(
      `<div class="line">host 192.168.1.10 is up</div>
       <div class="line">found CVE-2021-44228</div>`,
    )
    const items = getGrepOutputSuggestions(ctx, _buildItem, _filterItems)
    const values = items.map(i => i.value)
    expect(values).toContain('192.168.1.10')
    expect(values).toContain('CVE-2021-44228')
  })

  it('excludes echoed command (prompt-echo) lines', () => {
    const { getGrepOutputSuggestions, _buildItem, _filterItems } = buildHarness(
      `<div class="line prompt-echo">nmap 10.9.9.9</div>
       <div class="line">scanme.example.org open</div>`,
    )
    const values = getGrepOutputSuggestions(ctx, _buildItem, _filterItems).map(i => i.value)
    expect(values).toContain('scanme.example.org')
    expect(values).not.toContain('10.9.9.9') // came from the echoed command, not output
  })

  it('reads only the active tab, not other tabs', () => {
    const { getGrepOutputSuggestions, _buildItem, _filterItems } = buildHarness(
      `<div class="line">active.example.com</div>`,
    )
    // Seed a different tab with its own tokens; they must not appear.
    document.getElementById('output-tab2').innerHTML = '<div class="line">other.example.net</div>'
    const values = getGrepOutputSuggestions(ctx, _buildItem, _filterItems).map(i => i.value)
    expect(values).toContain('active.example.com')
    expect(values).not.toContain('other.example.net')
  })

  it('returns an empty array when there is no active tab output', () => {
    const { getGrepOutputSuggestions, _buildItem, _filterItems } = buildHarness('')
    expect(getGrepOutputSuggestions(ctx, _buildItem, _filterItems)).toEqual([])
  })

  it('returns an empty array when getOutput is unavailable', () => {
    const { getGrepOutputSuggestions, _buildItem, _filterItems } = loadRuntimeFns({ activeTabId: 'tab1' })
    expect(getGrepOutputSuggestions(ctx, _buildItem, _filterItems)).toEqual([])
  })

  it('filters suggestions by the current token prefix', () => {
    const { getGrepOutputSuggestions, _buildItem, _filterItems } = buildHarness(
      `<div class="line">192.168.1.10 and 10.0.0.5</div>
       <div class="line">192.168.1.10 again</div>`,
    )
    const values = getGrepOutputSuggestions({ tokenStart: 12, tokenEnd: 15, currentToken: '192' }, _buildItem, _filterItems)
      .map(i => i.value)
    expect(values).toContain('192.168.1.10')
    expect(values).not.toContain('10.0.0.5')
  })
})

// ── _buildPipeAutocomplete wiring (suggestions.js) ──
// runtime_context.js is intentionally NOT loaded here (its registry machinery
// pulls in many app globals). Instead getGrepOutputSuggestions is injected as a
// stub so we can verify the grep-only gating and merge behavior in isolation.

function loadSuggestionsWithStub(stub, { acContextRegistry = {} } = {}) {
  document.body.innerHTML = `<input id="cmd" /><div id="ac"></div>`
  return fromDomScripts(
    [
      'app/static/js/core/utils.js',
      'app/static/js/core/autocomplete_core.js',
      'app/static/js/features/autocomplete/suggestions.js',
    ],
    {
      document,
      window,
      acSuggestions: [],
      acContextRegistry,
      acFiltered: [],
      acIndex: -1,
      isActiveTabRunning: () => false,
      getGrepOutputSuggestions: stub,
    },
    '{ getAutocompleteMatches }',
  )
}

describe('_buildPipeAutocomplete grep output wiring', () => {
  const GREP_SPEC = { pipe_command: true, pipe_insert_value: 'grep', pipe_description: 'Filter lines', flags: ['-i', '-v', '-E'] }
  const SORT_SPEC = { pipe_command: true, pipe_insert_value: 'sort', pipe_description: 'Sort lines', flags: ['-r', '-n'] }

  it('appends output-token suggestions inside a grep pipe stage', () => {
    const stub = (ctx, buildItem) => [buildItem({ value: '10.0.0.1', replaceStart: ctx.tokenStart, replaceEnd: ctx.tokenEnd })]
    const { getAutocompleteMatches } = loadSuggestionsWithStub(stub, { acContextRegistry: { grep: GREP_SPEC } })
    const value = 'nmap 1.1.1.1 | grep '
    const values = getAutocompleteMatches(value, value.length).map(i => i.value)
    expect(values).toContain('10.0.0.1')
  })

  it('does not append output tokens for non-grep pipe helpers', () => {
    const stub = (ctx, buildItem) => [buildItem({ value: '10.0.0.1', replaceStart: ctx.tokenStart, replaceEnd: ctx.tokenEnd })]
    const { getAutocompleteMatches } = loadSuggestionsWithStub(stub, { acContextRegistry: { sort: SORT_SPEC } })
    const value = 'nmap 1.1.1.1 | sort '
    const values = getAutocompleteMatches(value, value.length).map(i => i.value)
    expect(values).not.toContain('10.0.0.1')
  })

  it('never suggests command roots — only the injected output tokens and grep flags', () => {
    const stub = (ctx, buildItem) => [buildItem({ value: 'opentoken', replaceStart: ctx.tokenStart, replaceEnd: ctx.tokenEnd })]
    const { getAutocompleteMatches } = loadSuggestionsWithStub(stub, { acContextRegistry: { grep: GREP_SPEC, nmap: { flags: ['-Pn'] } } })
    const value = 'nmap 1.1.1.1 | grep '
    const values = getAutocompleteMatches(value, value.length).map(i => i.value)
    expect(values).not.toContain('nmap')
    expect(values).toContain('opentoken')
  })

  it('de-duplicates an output token that collides with a grep flag', () => {
    const stub = (ctx, buildItem) => [buildItem({ value: '-i', replaceStart: ctx.tokenStart, replaceEnd: ctx.tokenEnd })]
    const { getAutocompleteMatches } = loadSuggestionsWithStub(stub, { acContextRegistry: { grep: GREP_SPEC } })
    const value = 'nmap 1.1.1.1 | grep '
    const values = getAutocompleteMatches(value, value.length).map(i => i.value)
    expect(values.filter(v => v === '-i')).toHaveLength(1)
  })
})
