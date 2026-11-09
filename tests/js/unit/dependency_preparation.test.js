// @vitest-environment node
// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { createHash } from 'node:crypto'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, expect, test } from 'vitest'
import { frontendNotices } from '../../../scripts/frontend/generate_frontend_notices.mjs'
import { installHadolint } from '../../../scripts/release/install_hadolint.mjs'

const folders = []
function folder() {
  const dir = mkdtempSync(join(tmpdir(), 'dependency-preparation-test-'))
  folders.push(dir)
  return dir
}
afterEach(() => folders.splice(0).forEach(dir => rmSync(dir, { recursive: true, force: true })))

test('browser notices retain the complete installed upstream license texts', () => {
  const root = folder()
  for (const name of ['@xterm/xterm', '@xterm/addon-fit', 'ansi_up', 'jspdf']) {
    const path = join(root, 'node_modules', name)
    mkdirSync(path, { recursive: true })
    writeFileSync(join(path, 'LICENSE'), `Copyright ${name}\nTerms for ${name}\n`)
  }
  const content = frontendNotices(root)
  expect(content).toContain('Copyright jspdf\nTerms for jspdf\n')
  writeFileSync(join(root, 'node_modules/jspdf/LICENSE'), 'Changed upstream terms\n')
  expect(frontendNotices(root)).toContain('Changed upstream terms')
  rmSync(join(root, 'node_modules/jspdf/LICENSE'))
  expect(() => frontendNotices(root)).toThrow()
})

test('Hadolint is installed only after both checksum and executable version pass', () => {
  const root = folder(), manifest = join(root, 'pin.json'), destination = join(root, 'installed')
  const binary = 'fixture executable', digest = createHash('sha256').update(binary).digest('hex')
  const pin = { depName: 'hadolint/hadolint', version: '2.99.0', asset: 'hadolint-linux-x86_64', sha256: digest }
  writeFileSync(manifest, JSON.stringify(pin))
  let output = 'Haskell Dockerfile Linter 2.99.0\n'
  const run = (command, argv) => {
    if (command === 'curl') {
      expect(argv).toContain('https://github.com/hadolint/hadolint/releases/download/v2.99.0/hadolint-linux-x86_64')
      writeFileSync(argv.at(-1), binary)
      return { status: 0 }
    }
    return { status: 0, stdout: output }
  }
  output = 'old 2.1.0'
  expect(() => installHadolint(destination, { manifest, run })).toThrow('version mismatch')
  expect(existsSync(destination)).toBe(false)
  output = 'Haskell Dockerfile Linter 2.99.0\n'
  installHadolint(destination, { manifest, run })
  expect(readFileSync(destination, 'utf8')).toBe(binary)
  rmSync(destination)
  writeFileSync(manifest, JSON.stringify({ ...pin, sha256: '0'.repeat(64) }))
  expect(() => installHadolint(destination, { manifest, run })).toThrow('checksum mismatch')
  expect(existsSync(destination)).toBe(false)
})
