import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'fs'
import { resolve, dirname, join } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../..')

// Surface-scoped button class names that are no longer valid. Buttons compose
// the .btn role/tone/size/state primitives (see components.css) plus the
// .nav-item / .close-btn / .toggle-btn / .kb-key siblings; minting any of
// these names back is a regression.
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
})
