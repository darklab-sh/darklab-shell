// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only
// @vitest-environment node

import { afterEach, describe, expect, it } from 'vitest'
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { brotliCompressSync, gzipSync } from 'node:zlib'
import { checkAssetFreshness, createFreshnessMetadata } from '../../../scripts/frontend/asset_freshness.mjs'

const roots = []
afterEach(() => roots.splice(0).forEach(root => rmSync(root, { recursive: true, force: true })))

function fixture() {
  const root = mkdtempSync(join(tmpdir(), 'darklab-asset-freshness-'))
  roots.push(root)
  const output = join(root, 'app/static/build')
  mkdirSync(output, { recursive: true })
  mkdirSync(join(root, 'scripts/frontend'), { recursive: true })
  for (const file of ['assets.config.json', 'package.json', 'package-lock.json']) writeFileSync(join(root, file), '{}')
  writeFileSync(join(root, 'scripts/frontend/build_assets.mjs'), '// build')
  writeFileSync(join(root, 'app/static/input.js'), 'export const value = 1;')
  const bytes = Buffer.from('generated output'.repeat(20))
  writeFileSync(join(output, 'app.js'), bytes)
  writeFileSync(join(output, 'app.js.br'), brotliCompressSync(bytes))
  writeFileSync(join(output, 'app.js.gz'), gzipSync(bytes))
  const manifest = { version: 1, bundles: {}, static_assets: {} }
  manifest.freshness = createFreshnessMetadata(root, output, manifest)
  writeFileSync(join(output, 'manifest.json'), JSON.stringify(manifest))
  return { root, output, bytes }
}

describe('asset freshness gate', () => {
  it('accepts current outputs and equivalent sidecars from a different compressor setting', () => {
    const { root, output, bytes } = fixture()
    expect(checkAssetFreshness(root)).toMatchObject({ input_count: 5, output_count: 3 })
    writeFileSync(join(output, 'app.js.gz'), gzipSync(bytes, { level: 1 }))
    expect(() => checkAssetFreshness(root)).not.toThrow()
  })

  it.each(['app/static/input.js', 'app/static/added.js', 'assets.config.json', 'package.json', 'package-lock.json', 'scripts/frontend/build_assets.mjs'])(
    'rejects changed or newly added input %s', file => {
      const { root } = fixture()
      writeFileSync(join(root, file), 'changed')
      expect(() => checkAssetFreshness(root)).toThrow('inputs changed')
    },
  )

  it.each(['app.js', 'app.js.gz', 'app.js.br'])('rejects corrupted output %s', file => {
    const { root, output } = fixture()
    writeFileSync(join(output, file), 'corrupt')
    expect(() => checkAssetFreshness(root)).toThrow()
  })

  it('rejects deleted sources, missing sidecars, and unexpected output files', () => {
    for (const change of ['source', 'sidecar', 'extra']) {
      const { root, output } = fixture()
      if (change === 'source') rmSync(join(root, 'app/static/input.js'))
      if (change === 'sidecar') rmSync(join(output, 'app.js.br'))
      if (change === 'extra') writeFileSync(join(output, 'stale.js'), 'stale')
      expect(() => checkAssetFreshness(root)).toThrow(/inputs changed|outputs changed/)
    }
  })

  it.each(['missing', 'node', 'esbuild', 'manifest'])('rejects %s metadata drift', change => {
    const { root, output } = fixture()
    const file = join(output, 'manifest.json')
    const manifest = JSON.parse(readFileSync(file))
    if (change === 'missing') delete manifest.freshness
    if (change === 'node') manifest.freshness.toolchain.node_major += 1
    if (change === 'esbuild') manifest.freshness.toolchain.esbuild = 'different'
    if (change === 'manifest') manifest.bundles = { altered: {} }
    writeFileSync(file, JSON.stringify(manifest))
    expect(() => checkAssetFreshness(root)).toThrow()
  })
})
