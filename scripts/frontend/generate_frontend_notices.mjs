#!/usr/bin/env node
// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

export function frontendNotices(root) {
  return ['@xterm/xterm', '@xterm/addon-fit', 'ansi_up', 'jspdf'].map(name => {
    const license = readFileSync(resolve(root, 'node_modules', name, 'LICENSE'), 'utf8').trim()
    if (!license) throw new Error(`Missing license text: ${name}`)
    return `${name}\n${'-'.repeat(name.length)}\n\n${license}\n`
  }).join('\n')
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
  const target = resolve(root, 'deploy/third-party-licenses/frontend-runtime.txt')
  const content = frontendNotices(root)
  if (process.argv.includes('--check')) {
    if (readFileSync(target, 'utf8') !== content) throw new Error('Frontend notices are stale; run npm run notices:sync')
  } else {
    writeFileSync(target, content)
  }
}
