#!/usr/bin/env node
/**
 * Build committed app CSS/JS bundles from assets.config.json.
 *
 * The build preserves configured CSS source order, minifies generated ESM
 * graphs with pinned esbuild settings, writes content-hashed filenames, and
 * records enough manifest metadata for Flask source/bundle rendering plus CI
 * drift checks.
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
import { basename, dirname, relative, resolve } from 'path';
import { fileURLToPath } from 'url';
import {
  brotliCompressSync,
  constants as zlibConstants,
  gzipSync,
} from 'zlib';
import { build as esbuild } from 'esbuild';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..');
const ESBUILD_WORKING_DIR = ROOT;
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
const PRECOMPRESSIBLE_EXTENSIONS = new Set(['css', 'js', 'json', 'svg']);

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

function sourceExtension(source) {
  const basename = source.split('/').pop() || 'asset';
  const index = basename.lastIndexOf('.');
  return index > 0 ? basename.slice(index + 1) : 'asset';
}

function hashedStaticAssetBasename(source, content) {
  const basename = source.split('/').pop() || 'asset';
  const extension = sourceExtension(source);
  const stem = basename.endsWith(`.${extension}`)
    ? basename.slice(0, -(extension.length + 1))
    : basename;
  const prefix = source.startsWith('/vendor/fonts/')
    ? 'font'
    : source.startsWith('/vendor/')
      ? 'vendor'
      : 'static';
  const safeStem = stem
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    || 'asset';
  return `${prefix}-${safeStem}.${sha256(content).slice(0, 12)}.${extension}`;
}

function hashedBundleBasename(name, extension, content) {
  return `${name}.${sha256(content).slice(0, 12)}.${extension}`;
}

function hashedEsmChunkBasename(outputPath, content) {
  const stem = basename(outputPath).replace(/\.js$/, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    || 'chunk';
  return `static-${stem}.${sha256(content).slice(0, 12)}.js`;
}

function outputExtension(type) {
  if (type === 'css') return 'css';
  if (type === 'esm') return 'js';
  throw new Error(`Unsupported bundle type: ${type}`);
}

function shouldPrecompress(filename) {
  return PRECOMPRESSIBLE_EXTENSIONS.has(sourceExtension(filename));
}

function precompressedVariants(content) {
  const buffer = Buffer.isBuffer(content) ? content : Buffer.from(content);
  return {
    br: brotliCompressSync(buffer, {
      params: {
        [zlibConstants.BROTLI_PARAM_QUALITY]: 11,
      },
    }),
    gz: gzipSync(buffer, { level: 9 }),
  };
}

function writeBuildAsset(filename, content) {
  const outputPath = resolve(outDir, filename);
  const buffer = Buffer.isBuffer(content) ? content : Buffer.from(content);
  writeFileSync(outputPath, content);
  if (!shouldPrecompress(filename)) return;
  for (const [suffix, compressed] of Object.entries(precompressedVariants(buffer))) {
    if (compressed.length >= buffer.length) continue;
    writeFileSync(`${outputPath}.${suffix}`, compressed);
  }
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
    if (type !== 'css' && type !== 'esm') {
      throw new Error(`Bundle ${name} has unsupported type ${type}`);
    }
    if (type === 'esm') {
      const entries = Array.isArray(bundle.entries) ? bundle.entries : [];
      if (entries.length !== 1) {
        throw new Error(`ESM bundle ${name} must list exactly one entry`);
      }
      return { name, type, entries, sources: entries };
    }
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

function fileToAppSource(file) {
  const absolute = resolve(file);
  const staticRoot = resolve(ROOT, 'app/static');
  const vendorRoot = resolve(ROOT, 'app/static/js/vendor');
  const relStatic = relative(staticRoot, absolute);
  if (relStatic && !relStatic.startsWith('..') && !relStatic.startsWith('/')) {
    if (relStatic.startsWith('js/vendor/')) {
      const relVendor = relative(vendorRoot, absolute);
      if (relVendor && !relVendor.startsWith('..') && !relVendor.startsWith('/')) {
        return `/vendor/${relVendor.split('\\').join('/')}`;
      }
    }
    return `/static/${relStatic.split('\\').join('/')}`;
  }
  throw new Error(`ESM bundle reached a file outside app/static: ${relative(ROOT, absolute)}`);
}

function sourceHashMap(sources) {
  const hashes = {};
  for (const source of sources) {
    const file = assertSourceExists(source);
    hashes[source] = sha256(readFileSync(file));
  }
  return hashes;
}

function appLazyEsmSources() {
  return (Array.isArray(config.lazy) ? config.lazy : [])
    .filter((source) => source.startsWith('/static/js/'))
    .sort();
}

function isAppLazyEsmSource(source) {
  return appLazyEsmSources().includes(source);
}

function configuredStandaloneSources() {
  const sources = new Set([
    ...((Array.isArray(config.lazy) ? config.lazy : [])),
    ...((Array.isArray(config.excluded) ? config.excluded : [])),
  ]);
  sources.add('/static/favicon.svg');
  const fontRoot = resolve(ROOT, 'app/static/fonts');
  for (const rel of collectStaticFiles(fontRoot)) {
    if (!rel.endsWith('.woff2')) continue;
    sources.add(`/vendor/fonts/${rel}`);
  }
  return Array.from(sources).sort();
}

function rewriteCssAssetUrls(css, staticAssets) {
  return css.replace(/url\((['"]?)(\/(?:vendor|static)\/[^'")]+)\1\)/g, (match, quote, source) => {
    const entry = staticAssets[source];
    if (!entry || !entry.path) return match;
    const nextQuote = quote || "'";
    return `url(${nextQuote}${entry.path}${nextQuote})`;
  });
}

async function buildEsmBundle(bundle) {
  const entry = bundle.entries[0];
  const entryFile = assertSourceExists(entry);
  let result;
  try {
    result = await esbuild({
      entryPoints: [entryFile],
      bundle: true,
      write: false,
      format: 'esm',
      target: 'es2022',
      charset: 'utf8',
      platform: 'browser',
      minify: true,
      sourcemap: false,
      legalComments: 'none',
      metafile: true,
      absWorkingDir: ESBUILD_WORKING_DIR,
      logLevel: 'silent',
    });
  } catch (err) {
    console.error('[assets] ESM bundle failed', {
      bundle: bundle.name,
      entry,
      out_dir: relative(ROOT, outDir),
      check_only: checkOnly,
      message: err && err.message ? err.message : String(err),
    });
    throw err;
  }
  if (!result.outputFiles || result.outputFiles.length !== 1) {
    throw new Error(`ESM bundle ${bundle.name} must produce exactly one output file`);
  }
  const reachedSources = Object.keys(result.metafile?.inputs || {})
    .map((input) => fileToAppSource(resolve(ESBUILD_WORKING_DIR, input)))
    .sort();
  return {
    output: `${result.outputFiles[0].text.replace(/\s*$/, '')}\n`,
    sourceHashes: sourceHashMap(reachedSources),
    sources: reachedSources,
  };
}

function outputKeyForFile(file) {
  return relative(ESBUILD_WORKING_DIR, file).split('\\').join('/');
}

function outputKeyToFile(outputKey) {
  return resolve(ESBUILD_WORKING_DIR, outputKey);
}

function relativeImportSpecifier(fromOutputKey, toOutputKey) {
  let specifier = relative(dirname(outputKeyToFile(fromOutputKey)), outputKeyToFile(toOutputKey))
    .split('\\')
    .join('/');
  if (!specifier.startsWith('.')) specifier = `./${specifier}`;
  return specifier;
}

function replaceAllLiteralImports(text, replacements) {
  let output = text;
  for (const [fromSpecifier, toSpecifier] of replacements) {
    output = output
      .replaceAll(`"${fromSpecifier}"`, `"${toSpecifier}"`)
      .replaceAll(`'${fromSpecifier}'`, `'${toSpecifier}'`);
  }
  return output;
}

function collectReachableOutputs(outputKey, outputs, seen = new Set()) {
  if (seen.has(outputKey)) return seen;
  seen.add(outputKey);
  const output = outputs[outputKey];
  for (const importRecord of output?.imports || []) {
    if (outputs[importRecord.path]) collectReachableOutputs(importRecord.path, outputs, seen);
  }
  return seen;
}

function collectReachableInputSources(outputKey, outputs) {
  const sources = new Set();
  for (const reachedOutputKey of collectReachableOutputs(outputKey, outputs)) {
    const inputs = outputs[reachedOutputKey]?.inputs || {};
    Object.keys(inputs).forEach((input) => {
      sources.add(fileToAppSource(resolve(ESBUILD_WORKING_DIR, input)));
    });
  }
  return Array.from(sources).sort();
}

async function buildAppEsmGraph(shellBundle, lazySources) {
  const entrySources = [...shellBundle.entries, ...lazySources];
  const entryPoints = entrySources.map((source) => assertSourceExists(source));
  let result;
  try {
    result = await esbuild({
      entryPoints,
      bundle: true,
      write: false,
      format: 'esm',
      splitting: true,
      outdir: outDir,
      outbase: resolve(ROOT, 'app/static/js'),
      entryNames: '[dir]/[name]',
      chunkNames: 'chunks/[name]-[hash]',
      target: 'es2022',
      charset: 'utf8',
      platform: 'browser',
      minify: true,
      sourcemap: false,
      legalComments: 'none',
      metafile: true,
      absWorkingDir: ESBUILD_WORKING_DIR,
      logLevel: 'silent',
    });
  } catch (err) {
    console.error('[assets] app ESM graph failed', {
      bundle: shellBundle.name,
      lazy_count: lazySources.length,
      out_dir: relative(ROOT, outDir),
      check_only: checkOnly,
      message: err && err.message ? err.message : String(err),
    });
    throw err;
  }
  const outputs = result.metafile?.outputs || {};
  const outputFilesByKey = new Map(result.outputFiles.map((file) => [
    outputKeyForFile(file.path),
    file,
  ]));
  const entryOutputBySource = new Map();
  for (const [outputKey, output] of Object.entries(outputs)) {
    if (!output.entryPoint) continue;
    entryOutputBySource.set(fileToAppSource(resolve(ESBUILD_WORKING_DIR, output.entryPoint)), outputKey);
  }
  for (const source of entrySources) {
    if (!entryOutputBySource.has(source)) {
      throw new Error(`App ESM graph did not produce an entry output for ${source}`);
    }
  }

  const finalBasenameByOutputKey = new Map();
  for (const outputKey of Object.keys(outputs).sort()) {
    const file = outputFilesByKey.get(outputKey);
    if (!file) throw new Error(`App ESM graph missing output file for ${outputKey}`);
    const source = Array.from(entryOutputBySource.entries())
      .find(([, entryOutputKey]) => entryOutputKey === outputKey)?.[0] || '';
    const content = `${file.text.replace(/\s*$/, '')}\n`;
    if (source === shellBundle.entries[0]) {
      finalBasenameByOutputKey.set(outputKey, hashedBundleBasename(shellBundle.name, 'js', content));
    } else if (source) {
      finalBasenameByOutputKey.set(outputKey, hashedStaticAssetBasename(source, content));
    } else {
      finalBasenameByOutputKey.set(outputKey, hashedEsmChunkBasename(outputKey, content));
    }
  }

  const builtFiles = [];
  for (const outputKey of Object.keys(outputs).sort()) {
    const file = outputFilesByKey.get(outputKey);
    const importReplacements = new Map();
    for (const importRecord of outputs[outputKey]?.imports || []) {
      const finalImportBasename = finalBasenameByOutputKey.get(importRecord.path);
      if (!finalImportBasename) continue;
      importReplacements.set(
        relativeImportSpecifier(outputKey, importRecord.path),
        `./${finalImportBasename}`,
      );
    }
    const content = `${replaceAllLiteralImports(
      file.text.replace(/\s*$/, ''),
      importReplacements,
    )}\n`;
    const finalBasename = finalBasenameByOutputKey.get(outputKey);
    builtFiles.push({
      outputKey,
      filename: finalBasename,
      content,
      hash: sha256(content),
    });
  }

  const shellOutputKey = entryOutputBySource.get(shellBundle.entries[0]);
  const shellSources = collectReachableInputSources(shellOutputKey, outputs);
  const lazyEntries = Object.fromEntries(lazySources.map((source) => {
    const outputKey = entryOutputBySource.get(source);
    const builtFile = builtFiles.find((file) => file.outputKey === outputKey);
    const inputSources = collectReachableInputSources(outputKey, outputs);
    console.info('[assets] standalone ESM asset built', {
      source,
      output: `/static/build/${builtFile.filename}`,
      input_count: inputSources.length,
      bytes: Buffer.byteLength(builtFile.content, 'utf8'),
      check_only: checkOnly,
    });
    if (process.env.DARKLAB_ASSET_BUILD_DEBUG === '1') {
      console.debug('[assets] standalone ESM asset branch', {
        source,
        should_bundle_standalone_esm: true,
        source_hash: sourceHashMap([source])[source] || '',
      });
    }
    return [source, {
      path: `/static/build/${builtFile.filename}`,
      hash: builtFile.hash,
    }];
  }));
  return {
    shell: {
      path: `/static/build/${finalBasenameByOutputKey.get(shellOutputKey)}`,
      hash: builtFiles.find((file) => file.outputKey === shellOutputKey).hash,
      sources: shellSources,
      sourceHashes: sourceHashMap(shellSources),
    },
    lazyEntries,
    files: builtFiles,
  };
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

function assertLazySourcesStayOutOfEsmBundle(bundleName, sources) {
  const lazySources = new Set(Array.isArray(config.lazy) ? config.lazy : []);
  const eagerLazySources = sources.filter((source) => lazySources.has(source));
  if (!eagerLazySources.length) return;
  throw new Error(
    `ESM bundle ${bundleName} eagerly includes lazy assets:\n${
      eagerLazySources.map((source) => `  ${source}`).join('\n')
    }\nRemove the eager import or remove the source from assets.config.json lazy.`,
  );
}

const bundles = normalizeBundles(config.bundles);
const bundlesByName = new Map(bundles.map((bundle) => [bundle.name, bundle]));
const configuredSources = bundles.flatMap((bundle) => bundle.sources);
assertCssCoverage(configuredSources);
assertOrderChecks(bundlesByName);

const buildEntries = {};
const staticAssetEntries = {};
rmSync(outDir, { recursive: true, force: true });
mkdirSync(outDir, { recursive: true });

const builtBundleRecords = [];
const shellEsmBundle = bundles.find((bundle) => bundle.name === 'shell-bootstrap' && bundle.type === 'esm');
if (!shellEsmBundle) {
  throw new Error('assets.config.json must define the shell-bootstrap ESM bundle');
}
const appEsmGraph = await buildAppEsmGraph(shellEsmBundle, appLazyEsmSources());
for (const file of appEsmGraph.files) {
  writeBuildAsset(file.filename, file.content);
}
Object.assign(staticAssetEntries, appEsmGraph.lazyEntries);

for (const source of configuredStandaloneSources()) {
  if (isAppLazyEsmSource(source)) continue;
  const file = assertSourceExists(source);
  const content = readFileSync(file);
  const filename = hashedStaticAssetBasename(source, content);
  writeBuildAsset(filename, content);
  staticAssetEntries[source] = {
    path: `/static/build/${filename}`,
    hash: sha256(content),
  };
}

for (const bundle of bundles) {
  let sourceHashes = {};
  let output = '';
  let manifestSources = bundle.sources;
  const parts = [];
  if (bundle.type === 'esm') {
    if (bundle.name === shellEsmBundle.name) {
      buildEntries[bundle.name] = {
        type: bundle.type,
        path: appEsmGraph.shell.path,
        hash: appEsmGraph.shell.hash,
        entries: bundle.entries,
        sources: appEsmGraph.shell.sources,
        source_hashes: appEsmGraph.shell.sourceHashes,
      };
      builtBundleRecords.push({
        name: bundle.name,
        sources: appEsmGraph.shell.sources,
      });
      assertLazySourcesStayOutOfEsmBundle(bundle.name, appEsmGraph.shell.sources);
      continue;
    }
    const builtEsm = await buildEsmBundle(bundle);
    output = builtEsm.output;
    sourceHashes = builtEsm.sourceHashes;
    manifestSources = builtEsm.sources;
    assertLazySourcesStayOutOfEsmBundle(bundle.name, manifestSources);
  } else {
    for (const source of bundle.sources) {
      const file = assertSourceExists(source);
      const content = readFileSync(file);
      sourceHashes[source] = sha256(content);
      parts.push(`/* ${source} */\n${content.toString('utf8')}\n`);
    }
    output = `${parts.join('\n')}\n`;
    output = rewriteCssAssetUrls(output, staticAssetEntries);
  }
  const hash = sha256(output);
  const ext = outputExtension(bundle.type);
  const filename = `${bundle.name}.${hash.slice(0, 12)}.${ext}`;
  writeBuildAsset(filename, output);
  const entry = {
    type: bundle.type,
    path: `/static/build/${filename}`,
    hash,
    sources: manifestSources,
    source_hashes: sourceHashes,
  };
  if (bundle.type === 'esm') {
    entry.entries = bundle.entries;
  }
  buildEntries[bundle.name] = entry;
  builtBundleRecords.push(entry);
}

assertJsCoverage(builtBundleRecords.flatMap((bundle) => bundle.sources));

const manifest = {
  version: 1,
  generated_by: 'scripts/build_assets.mjs',
  bundles: buildEntries,
  static_assets: staticAssetEntries,
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
