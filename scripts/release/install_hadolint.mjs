#!/usr/bin/env node
// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { createHash } from 'node:crypto'
import { chmodSync, copyFileSync, mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, resolve } from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath, pathToFileURL } from 'node:url'

export function installHadolint(destination, {
  manifest = resolve(dirname(fileURLToPath(import.meta.url)), '../../.tooling/hadolint.json'),
  run = spawnSync,
} = {}) {
  const pin = JSON.parse(readFileSync(manifest, 'utf8'))
  if (pin.depName !== 'hadolint/hadolint' || !/^\d+\.\d+\.\d+$/.test(pin.version)
      || pin.asset !== 'hadolint-linux-x86_64' || !/^[a-f0-9]{64}$/.test(pin.sha256)) {
    throw new Error('Invalid Hadolint integrity pin')
  }
  const dir = mkdtempSync(resolve(tmpdir(), 'darklab-hadolint-'))
  try {
    const binary = resolve(dir, 'hadolint')
    const download = run('curl', ['--fail', '--show-error', '--location', '--retry', '3',
      `https://github.com/hadolint/hadolint/releases/download/v${pin.version}/${pin.asset}`, '-o', binary], { stdio: 'inherit' })
    if (download.error || download.status !== 0) throw new Error('Hadolint download failed')
    if (createHash('sha256').update(readFileSync(binary)).digest('hex') !== pin.sha256) throw new Error('Hadolint checksum mismatch')
    chmodSync(binary, 0o755)
    const version = run(binary, ['--version'], { encoding: 'utf8' })
    if (version.error || version.status !== 0 || !version.stdout?.trim().endsWith(` ${pin.version}`)) {
      throw new Error('Hadolint version mismatch')
    }
    copyFileSync(binary, destination)
    chmodSync(destination, 0o755)
    console.log(version.stdout.trim())
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  installHadolint(resolve(process.argv[2] || '/usr/local/bin/hadolint'))
}
