#!/usr/bin/env node
/**
 * Build committed app CSS/JS bundles from assets.config.json.
 *
 * Phase 1 is deliberately dependency-free and concat-only: preserve source
 * order, write content-hashed filenames, and record enough manifest metadata
 * for Flask source/bundle rendering plus CI drift checks.
 */

import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  writeFileSync,
} from 'fs';
import { createHash } from 'crypto';
import { dirname, relative, resolve } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..');
const args = process.argv.slice(2);
let outDir = resolve(ROOT, 'app/static/build');
let checkOnly = false;

for (let i = 0; i < args.length; i += 1) {
  const arg = args[i];
  if (arg === '--out-dir' && typeof args[i + 1] === 'string') {
    outDir = resolve(ROOT, args[i + 1]);
    i += 1;
  } else if (arg === '--check') {
    checkOnly = true;
  } else {
    throw new Error(`Unknown argument: ${arg}`);
  }
}

const configPath = resolve(ROOT, 'assets.config.json');
const config = JSON.parse(readFileSync(configPath, 'utf8'));

function sha256(bufferOrText) {
  return createHash('sha256').update(bufferOrText).digest('hex');
}

function sourceToFile(source) {
  if (typeof source !== 'string' || !source.startsWith('/')) {
    throw new Error(`Asset source must be an absolute app URL path: ${source}`);
  }
  if (source.startsWith('/static/')) {
    return resolve(ROOT, 'app/static', source.slice('/static/'.length));
  }
  if (source.startsWith('/vendor/')) {
    return resolve(ROOT, 'app/static', source.slice('/vendor/'.length));
  }
  throw new Error(`Unsupported asset source prefix: ${source}`);
}

function assertSourceExists(source) {
  const file = sourceToFile(source);
  if (!existsSync(file)) {
    throw new Error(`Missing asset source ${source} (${relative(ROOT, file)})`);
  }
  return file;
}

function outputExtension(type) {
  if (type === 'css') return 'css';
  if (type === 'js') return 'js';
  throw new Error(`Unsupported bundle type: ${type}`);
}

function normalizeBundles(rawBundles) {
  if (!rawBundles || typeof rawBundles !== 'object' || Array.isArray(rawBundles)) {
    throw new Error('assets.config.json must contain a bundles object');
  }
  return Object.entries(rawBundles).map(([name, bundle]) => {
    if (!bundle || typeof bundle !== 'object' || Array.isArray(bundle)) {
      throw new Error(`Bundle ${name} must be an object`);
    }
    const type = String(bundle.type || '');
    const sources = Array.isArray(bundle.sources) ? bundle.sources : [];
    if (!sources.length) {
      throw new Error(`Bundle ${name} must list at least one source`);
    }
    return { name, type, sources };
  });
}

function collectStaticFiles(dir, prefix = '') {
  if (!existsSync(dir)) return [];
  const files = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const rel = prefix ? `${prefix}/${entry.name}` : entry.name;
    const full = resolve(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...collectStaticFiles(full, rel));
    } else if (entry.isFile()) {
      files.push(rel);
    }
  }
  return files.sort();
}

function assertCssCoverage(configuredSources) {
  const cssRoot = resolve(ROOT, 'app/static/css');
  const expected = collectStaticFiles(cssRoot)
    .filter((rel) => rel.endsWith('.css'))
    .map((rel) => `/static/css/${rel}`);
  const covered = new Set([
    ...configuredSources,
    ...((Array.isArray(config.excluded) ? config.excluded : [])),
    ...((Array.isArray(config.lazy) ? config.lazy : [])),
  ]);
  const missing = expected.filter((source) => !covered.has(source));
  if (missing.length) {
    throw new Error(`CSS assets missing from assets.config.json:\n${missing.map((item) => `  ${item}`).join('\n')}`);
  }
}

const bundles = normalizeBundles(config.bundles);
const allSources = bundles.flatMap((bundle) => bundle.sources);
assertCssCoverage(allSources);

const buildEntries = {};
rmSync(outDir, { recursive: true, force: true });
mkdirSync(outDir, { recursive: true });

for (const bundle of bundles) {
  const sourceHashes = {};
  const parts = [];
  for (const source of bundle.sources) {
    const file = assertSourceExists(source);
    const content = readFileSync(file);
    sourceHashes[source] = sha256(content);
    parts.push(`/* ${source} */\n${content.toString('utf8').replace(/\s*$/, '')}\n`);
  }
  const output = `${parts.join('\n')}\n`;
  const hash = sha256(output);
  const ext = outputExtension(bundle.type);
  const filename = `${bundle.name}.${hash.slice(0, 12)}.${ext}`;
  writeFileSync(resolve(outDir, filename), output);
  buildEntries[bundle.name] = {
    type: bundle.type,
    path: `/static/build/${filename}`,
    hash,
    sources: bundle.sources,
    source_hashes: sourceHashes,
  };
}

const manifest = {
  version: 1,
  generated_by: 'scripts/build_assets.mjs',
  bundles: buildEntries,
};
writeFileSync(resolve(outDir, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`);

if (checkOnly) {
  const committedDir = resolve(ROOT, 'app/static/build');
  const expectedFiles = collectStaticFiles(outDir);
  const committedFiles = collectStaticFiles(committedDir);
  const missing = expectedFiles.filter((file) => !committedFiles.includes(file));
  const extra = committedFiles.filter((file) => !expectedFiles.includes(file));
  const changed = expectedFiles.filter((file) => {
    const expectedPath = resolve(outDir, file);
    const committedPath = resolve(committedDir, file);
    return existsSync(committedPath)
      && statSync(expectedPath).isFile()
      && sha256(readFileSync(expectedPath)) !== sha256(readFileSync(committedPath));
  });
  if (missing.length || extra.length || changed.length) {
    const details = [
      ...missing.map((file) => `missing committed asset: ${file}`),
      ...extra.map((file) => `extra committed asset: ${file}`),
      ...changed.map((file) => `changed committed asset: ${file}`),
    ];
    throw new Error(`Asset bundles are stale. Run assets:sync.\n${details.map((line) => `  ${line}`).join('\n')}`);
  }
}

console.log(`Built ${bundles.length} asset bundle${bundles.length === 1 ? '' : 's'} into ${relative(ROOT, outDir)}`);
