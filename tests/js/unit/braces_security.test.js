// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only
// @vitest-environment node

import { describe, expect, it } from 'vitest'
import { createRequire } from 'node:module'
import { realpathSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const braces = require('braces')
const micromatch = require('micromatch')
const vendorEntry = fileURLToPath(new URL('../../../tools/vendor/braces/index.js', import.meta.url))
const nestedPattern = (depth, left = '{', right = '}') => left.repeat(depth) + 'a,b' + right.repeat(depth)

function nestedAst(depth) {
  let ast = { type: 'text', value: 'a' }
  for (let index = 0; index < depth; index += 1) ast = { type: 'brace', nodes: [ast] }
  return { type: 'root', nodes: [ast] }
}

describe('vendored braces security boundary', () => {
  it('uses the reviewed local package throughout the lint dependency chain', () => {
    expect(require('braces/package.json').version).toBe('3.0.3-darklab.1')
    expect(realpathSync(require.resolve('braces'))).toBe(realpathSync(vendorEntry))
    for (const consumer of ['markdownlint-cli2', 'stylelint', 'globby', 'fast-glob']) {
      const consumerRequire = createRequire(require.resolve(consumer))
      const matcherRequire = createRequire(consumerRequire.resolve('micromatch'))
      expect(realpathSync(matcherRequire.resolve('braces'))).toBe(realpathSync(vendorEntry))
    }
  })

  it.each(['parse', 'compile', 'expand', 'stringify'])('%s rejects deeply nested brace and parenthesis input', method => {
    for (const [left, right] of [['{', '}'], ['(', ')']]) {
      const pattern = nestedPattern(4000, left, right)
      expect(() => braces[method](pattern)).toThrow(/Input depth \(101\), exceeds max depth \(100\)/)
    }
  })

  it.each(['compile', 'expand', 'stringify'])('%s rejects a deeply nested caller-supplied AST', method => {
    expect(() => braces[method](nestedAst(4000))).toThrow(/AST depth \(101\), exceeds max depth \(100\)/)
  })

  it('enforces the depth limit through micromatch compile and expansion', () => {
    expect(() => micromatch.braces(nestedPattern(4000))).toThrow(/exceeds max depth/)
    expect(() => micromatch.braceExpand(nestedPattern(4000))).toThrow(/exceeds max depth/)
  })

  it.each([1000, Infinity, NaN, '1000'])('cannot raise the safety limit with maxDepth=%s', maxDepth => {
    expect(() => braces(nestedPattern(101), { maxDepth })).toThrow(/exceeds max depth \(100\)/)
    for (const method of ['compile', 'expand', 'stringify']) {
      expect(() => braces[method](nestedAst(101), { maxDepth })).toThrow(/exceeds max depth \(100\)/)
    }
  })

  it('accepts the depth boundary and enforces a stricter caller limit', () => {
    for (const method of ['parse', 'compile', 'expand', 'stringify']) {
      expect(() => braces[method](nestedPattern(100))).not.toThrow()
      expect(() => braces[method]('{{a,b},c}', { maxDepth: 1 })).toThrow(/exceeds max depth \(1\)/)
      expect(() => braces[method]('{{a,b},c}', { maxDepth: 2 })).not.toThrow()
    }
  })

  it('preserves nested alternatives, ranges, escapes, and glob matching', () => {
    expect(braces('src/{a,{b,c}}.js')).toEqual(['src/(a|(b|c)).js'])
    expect(braces.expand('src/{a,{b,c}}.js')).toEqual(['src/a.js', 'src/b.js', 'src/c.js'])
    expect(braces.expand('file{1..3}.css')).toEqual(['file1.css', 'file2.css', 'file3.css'])
    expect(braces.expand('file\\{a,b\\}.md')).toEqual(['file{a,b}.md'])
    expect(micromatch(['src/a.js', 'src/b.css', 'src/c.md', '.hidden.js'], '**/*.{js,css}'))
      .toEqual(['src/a.js', 'src/b.css'])
  })
})
