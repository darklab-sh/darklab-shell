#!/usr/bin/env node
/**
 * Build committed app CSS/JS bundles from assets.config.json.
 *
 * The build is deliberately dependency-free and unminified: preserve source
 * order, keep each classic script as its own execution unit, write
 * content-hashed filenames, and record enough manifest metadata for Flask
 * source/bundle rendering plus CI drift checks.
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
    const vendorPath = source.slice('/vendor/'.length);
    if (vendorPath.startsWith('fonts/')) {
      return resolve(ROOT, 'app/static', vendorPath);
    }
    return resolve(ROOT, 'app/static/js/vendor', vendorPath);
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

function classicScriptBundleText(source, content) {
  if (!source.endsWith('.js')) return content;
  const sourceUrl = `\n//# sourceURL=${source}`;
  return `_runBundledClassicScript(${JSON.stringify(source)}, ${JSON.stringify(`${content}${sourceUrl}`)});`;
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

function coveredSources(configuredSources) {
  const covered = new Set([
    ...configuredSources,
    ...((Array.isArray(config.excluded) ? config.excluded : [])),
    ...((Array.isArray(config.lazy) ? config.lazy : [])),
  ]);
  for (const source of Array.from(covered)) {
    if (source.startsWith('/vendor/')) {
      const vendorPath = source.slice('/vendor/'.length);
      if (!vendorPath.startsWith('fonts/')) {
        covered.add(`/static/js/vendor/${vendorPath}`);
      }
    }
  }
  return covered;
}

function assertJsCoverage(configuredSources) {
  const jsRoot = resolve(ROOT, 'app/static/js');
  const expected = collectStaticFiles(jsRoot)
    .filter((rel) => rel.endsWith('.js'))
    .map((rel) => `/static/js/${rel}`);
  const covered = coveredSources(configuredSources);
  const missing = expected.filter((source) => !covered.has(source));
  if (missing.length) {
    throw new Error(`JS assets missing from assets.config.json:\n${missing.map((item) => `  ${item}`).join('\n')}`);
  }
}

function assertOrderChecks(bundlesByName) {
  const rawChecks = config.order_checks || {};
  if (!rawChecks || typeof rawChecks !== 'object' || Array.isArray(rawChecks)) {
    throw new Error('assets.config.json order_checks must be an object');
  }
  for (const [name, check] of Object.entries(rawChecks)) {
    if (!check || typeof check !== 'object' || Array.isArray(check)) {
      throw new Error(`Order check ${name} must be an object`);
    }
    const checkBundles = Array.isArray(check.bundles) ? check.bundles : [];
    const expected = Array.isArray(check.sources) ? check.sources : [];
    if (!checkBundles.length || !expected.length) {
      throw new Error(`Order check ${name} must list bundles and sources`);
    }
    const actual = [];
    for (const bundleName of checkBundles) {
      const bundle = bundlesByName.get(bundleName);
      if (!bundle) {
        throw new Error(`Order check ${name} references unknown bundle ${bundleName}`);
      }
      actual.push(...bundle.sources);
    }
    const mismatches = [];
    const maxLength = Math.max(actual.length, expected.length);
    for (let index = 0; index < maxLength; index += 1) {
      if (actual[index] !== expected[index]) {
        mismatches.push(`  position ${index + 1}: bundle=${actual[index] || '<missing>'}, expected=${expected[index] || '<missing>'}`);
      }
    }
    if (mismatches.length) {
      throw new Error(`Asset order check ${name} does not match configured source order:\n${mismatches.join('\n')}`);
    }
  }
}

const bundles = normalizeBundles(config.bundles);
const bundlesByName = new Map(bundles.map((bundle) => [bundle.name, bundle]));
const allSources = bundles.flatMap((bundle) => bundle.sources);
assertCssCoverage(allSources);
assertJsCoverage(allSources);
assertOrderChecks(bundlesByName);

const buildEntries = {};
rmSync(outDir, { recursive: true, force: true });
mkdirSync(outDir, { recursive: true });

for (const bundle of bundles) {
  const sourceHashes = {};
  const parts = [];
  if (bundle.type === 'js') {
    parts.push(`;(function () {
  var _bundleAnchorScript = document.currentScript;
  var _bundleScriptParent = (_bundleAnchorScript && _bundleAnchorScript.parentNode)
    || document.head
    || document.documentElement;
  function _runBundledClassicScript(source, body) {
    var script = document.createElement('script');
    script.text = body;
    script.setAttribute('data-bundled-source', source);
    try {
      _bundleScriptParent.insertBefore(script, _bundleAnchorScript ? _bundleAnchorScript.nextSibling : null);
    } catch (err) {
      setTimeout(function () { throw err; }, 0);
    } finally {
      if (script.parentNode) script.parentNode.removeChild(script);
    }
  }`);
  }
  for (const source of bundle.sources) {
    const file = assertSourceExists(source);
    const content = readFileSync(file);
    sourceHashes[source] = sha256(content);
    const body = classicScriptBundleText(source, content.toString('utf8')).replace(/\s*$/, '');
    if (bundle.type === 'js') {
      parts.push(`;\n/* ${source} */\n${body}\n;`);
    } else {
      parts.push(`/* ${source} */\n${body}\n`);
    }
  }
  if (bundle.type === 'js') {
    parts.push('}());');
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
  const committedManifestPath = resolve(committedDir, 'manifest.json');
  const staleSources = [];
  if (existsSync(committedManifestPath)) {
    const committedManifest = JSON.parse(readFileSync(committedManifestPath, 'utf8'));
    const committedBundles = committedManifest && committedManifest.bundles && typeof committedManifest.bundles === 'object'
      ? committedManifest.bundles
      : {};
    for (const [bundleName, bundleEntry] of Object.entries(committedBundles)) {
      const sourceHashes = bundleEntry && bundleEntry.source_hashes && typeof bundleEntry.source_hashes === 'object'
        ? bundleEntry.source_hashes
        : {};
      for (const [source, expectedHash] of Object.entries(sourceHashes)) {
        const file = assertSourceExists(source);
        const actualHash = sha256(readFileSync(file));
        if (actualHash !== expectedHash) {
          staleSources.push(`${bundleName}: ${source}`);
        }
      }
    }
  }
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
  if (staleSources.length || missing.length || extra.length || changed.length) {
    const details = [
      ...staleSources.map((source) => `stale source hash: ${source}`),
      ...missing.map((file) => `missing committed asset: ${file}`),
      ...extra.map((file) => `extra committed asset: ${file}`),
      ...changed.map((file) => `changed committed asset: ${file}`),
    ];
    throw new Error(`Asset bundles are stale. Run assets:sync.\n${details.map((line) => `  ${line}`).join('\n')}`);
  }
}

console.log(`Built ${bundles.length} asset bundle${bundles.length === 1 ? '' : 's'} into ${relative(ROOT, outDir)}`);
