// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// A cheap local prerequisite; CI still rebuilds and checks CWD independence.
import { createHash } from 'node:crypto';
import { readFileSync, readdirSync } from 'node:fs';
import { relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { brotliDecompressSync, gunzipSync } from 'node:zlib';
import { version as esbuildVersion } from 'esbuild';

const sha256 = value => createHash('sha256').update(value).digest('hex');
const toolchain = () => ({ node_major: Number(process.versions.node.split('.')[0]), esbuild: esbuildVersion });

function filesUnder(directory, excluded = new Set()) {
  return readdirSync(directory, { withFileTypes: true }).sort((a, b) => a.name < b.name ? -1 : a.name > b.name ? 1 : 0).flatMap(entry => {
    const path = resolve(directory, entry.name);
    if (excluded.has(path) || entry.name === '.DS_Store') return [];
    if (entry.isSymbolicLink()) throw new Error(`Asset fingerprint cannot follow a symbolic link: ${entry.name}`);
    return entry.isDirectory() ? filesUnder(path, excluded) : entry.isFile() ? [path] : [];
  });
}

function inputHashes(root, outputDir) {
  const inputs = [
    ...['assets.config.json', 'package.json', 'package-lock.json'].map(path => resolve(root, path)),
    ...filesUnder(resolve(root, 'scripts/frontend')).filter(path => path.endsWith('.mjs')),
    ...filesUnder(resolve(root, 'app/static'), new Set([resolve(root, 'app/static/build'), resolve(outputDir)])),
  ];
  return Object.fromEntries(inputs.sort().map(path => [relative(root, path).split('\\').join('/'), sha256(readFileSync(path))]));
}

function outputHashes(outputDir) {
  return Object.fromEntries(filesUnder(outputDir).filter(path => relative(outputDir, path) !== 'manifest.json').map(path => {
    const name = relative(outputDir, path).split('\\').join('/');
    const decompress = path.endsWith('.br') ? brotliDecompressSync : path.endsWith('.gz') ? gunzipSync : null;
    let content = readFileSync(path);
    if (decompress) {
      const original = readFileSync(path.slice(0, -3));
      content = decompress(content, { maxOutputLength: original.length + 1 });
      if (!content.equals(original)) throw new Error(`Compressed sidecar does not match ${name}`);
    }
    // Compressor patch versions may differ; decoded bytes must be identical.
    return [name, sha256(content)];
  }));
}

export function createFreshnessMetadata(root, outputDir, manifest) {
  return {
    version: 1,
    toolchain: toolchain(),
    inputs: inputHashes(root, outputDir),
    outputs: outputHashes(outputDir),
    manifest_hash: sha256(JSON.stringify(manifest)),
  };
}

export function checkAssetFreshness(root) {
  const outputDir = resolve(root, 'app/static/build');
  const { freshness, ...manifest } = JSON.parse(readFileSync(resolve(outputDir, 'manifest.json'), 'utf8'));
  if (!freshness || freshness.version !== 1) throw new Error('Asset freshness metadata is missing or unsupported');
  const current = createFreshnessMetadata(root, outputDir, manifest);
  for (const key of ['toolchain', 'inputs', 'outputs', 'manifest_hash']) {
    if (JSON.stringify(current[key]) !== JSON.stringify(freshness[key])) {
      throw new Error(`Asset ${key} changed since the last build`);
    }
  }
  return { input_count: Object.keys(current.inputs).length, output_count: Object.keys(current.outputs).length };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const started = performance.now();
  try {
    const counts = checkAssetFreshness(fileURLToPath(new URL('../../', import.meta.url)));
    console.info('[assets] freshness verified', { ...counts, duration_ms: Math.round(performance.now() - started) });
  } catch (error) {
    console.error(`[assets] ${error.message}. Run npm run assets:sync.`);
    process.exitCode = 1;
  }
}
