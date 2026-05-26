import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'fs'
import { resolve, dirname, join } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../..')

// Surface-scoped button class names that are no longer valid. Buttons compose
// the .btn role/tone/size/state primitives (see components.css) plus sibling
// primitives such as .nav-item, .tab-strip-item, .close-btn, and .toggle-btn;
// minting any of these names back is a regression.
const RETIRED_CLASSES = [
  'term-action-btn',
  'hud-kill-btn',
  'hud-action-btn',
  'tab-kill-btn-danger',
  'modal-primary',
  'modal-primary-danger',
  'modal-primary-warning',
  'modal-primary-accent',
  'modal-secondary',
  'modal-secondary-warning',
  'modal-secondary-neutral',
  // '.search-toggle' collides with '.search-toggles' (wrapper) and
  // '#search-toggle-btn' (chrome id); the token-boundary lookarounds below
  // treat those as distinct tokens and keep them valid.
  'search-toggle',
]

const SCAN_DIRS = [
  join(REPO_ROOT, 'app/static/css'),
  join(REPO_ROOT, 'app/static/js'),
  join(REPO_ROOT, 'app/templates'),
]

function walk(dir) {
  const out = []
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    const st = statSync(full)
    if (st.isDirectory()) out.push(...walk(full))
    else if (/\.(css|js|html)$/.test(name)) out.push(full)
  }
  return out
}

function escapeRegex(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function hasFormSelectClass(attrText) {
  const match = /\bclass\s*=\s*["']([^"']*)["']/.exec(attrText)
  return !!match && match[1].split(/\s+/).includes('form-select')
}

describe('button primitive regression guard', () => {
  const files = SCAN_DIRS.flatMap(d => walk(d))

  for (const cls of RETIRED_CLASSES) {
    it(`no source file references retired class '${cls}'`, () => {
      const re = new RegExp(`(?<![\\w-])${escapeRegex(cls)}(?![\\w-])`, 'g')
      const hits = []
      for (const f of files) {
        const src = readFileSync(f, 'utf8')
        const lines = src.split('\n')
        lines.forEach((line, i) => {
          if (re.test(line)) {
            hits.push(`${f.replace(REPO_ROOT + '/', '')}:${i + 1}: ${line.trim()}`)
          }
          re.lastIndex = 0
        })
      }
      expect(hits).toEqual([])
    })
  }

  it('native select elements compose the form-select primitive', () => {
    const hits = []
    for (const f of files.filter(file => /\.(js|html)$/.test(file))) {
      const src = readFileSync(f, 'utf8')
      const lines = src.split('\n')

      lines.forEach((line, i) => {
        const htmlSelectRe = /<select\b([^>]*)>/gi
        for (const match of line.matchAll(htmlSelectRe)) {
          if (!hasFormSelectClass(match[1])) {
            hits.push(`${f.replace(REPO_ROOT + '/', '')}:${i + 1}: ${line.trim()}`)
          }
        }

        const createRe = /\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*document\.createElement\(['"]select['"]\)/g
        for (const match of line.matchAll(createRe)) {
          const varName = match[1]
          const lookahead = lines.slice(i, i + 9).join('\n')
          const classNameRe = new RegExp(`${escapeRegex(varName)}\\.className\\s*=\\s*['"\`][^'"\`]*\\bform-select\\b`)
          const classListRe = new RegExp(`${escapeRegex(varName)}\\.classList\\.add\\([^)]*['"]form-select['"]`)
          if (!classNameRe.test(lookahead) && !classListRe.test(lookahead)) {
            hits.push(`${f.replace(REPO_ROOT + '/', '')}:${i + 1}: ${line.trim()}`)
          }
        }
      })
    }
    expect(hits).toEqual([])
  })

  it('notification rows use badge primitives for passive metadata', () => {
    const source = readFileSync(join(REPO_ROOT, 'app/static/js/features/preferences/notification_channels.js'), 'utf8')

    expect(source).not.toContain('metadata-chip options-secret-chip')
    expect(source).not.toContain('querySelector(\'[data-options-tab="notifications"]\')')
    expect(source).not.toContain('btn btn-secondary btn-danger btn-compact')
    expect(source).toContain('badge badge-tone-muted options-secret-chip')
    expect(source).toContain('badge-tone-green')
    expect(source).toContain('btn btn-destructive btn-compact')
    expect(source).toContain('form-control form-control-compact options-token-input')
  })
})
