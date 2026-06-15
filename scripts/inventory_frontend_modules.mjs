#!/usr/bin/env node
/**
 * Inventory frontend global compatibility contracts in the ESM runtime.
 *
 * The report focuses on app-level coupling: top-level names a file defines,
 * explicit window properties it publishes, and bare identifier reads that
 * rely on another app file publishing a browser global.
 */

import { existsSync, readFileSync, readdirSync } from 'fs';
import { dirname, relative, resolve } from 'path';
import { fileURLToPath } from 'url';
import { Linter } from 'eslint';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..');
const args = process.argv.slice(2);
const jsonOutput = args.includes('--json');
const checkOnly = args.includes('--check');
const help = args.includes('--help') || args.includes('-h');
const ALLOWLIST_PATH = resolve(ROOT, process.env.FRONTEND_GLOBALS_ALLOWLIST || 'frontend-globals.allowlist.json');
const ALLOWLIST_PURPOSES = new Set([
  'intentional_bootstrap',
  'vendor_global',
  'lazy_placeholder',
  'module_api_bridge',
  'test_hook',
  'compatibility_export',
  'compatibility_read',
]);
const LAZY_ASSETS_SOURCE = '/static/js/core/lazy_assets.js';

if (help) {
  console.log(`Usage: node scripts/inventory_frontend_modules.mjs [--json] [--check]

Prints a per-file inventory of frontend compatibility-global coupling:
  - top-level function/var/let/const/class names
  - explicit window.* properties published by the file, including helper publishers
  - explicit window.* property reads for app/vendor globals tracked by the allowlist
  - bare identifier reads that resolve to names published by another app file
  - a purpose classification for known browser globals and compatibility bridges
  - a coarse migration classification: pure leaf, consumer-only, tangled, or isolated

With --check, fails if an app-level bare read has no matching publish path.
It also fails when a tracked app window publish/read is not covered by the
frontend globals allowlist, or when an allowlist entry no longer matches any
current publish/read boundary. Set FRONTEND_GLOBALS_ALLOWLIST to test another
allowlist file.
`);
  process.exit(0);
}

const unknownArgs = args.filter((arg) => !['--json', '--check'].includes(arg));
if (unknownArgs.length) {
  throw new Error(`Unknown argument: ${unknownArgs.join(', ')}`);
}

function loadAllowlist() {
  if (!existsSync(ALLOWLIST_PATH)) {
    return {
      version: 1,
      globals: [],
    };
  }
  const raw = JSON.parse(readFileSync(ALLOWLIST_PATH, 'utf8'));
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new Error('frontend-globals.allowlist.json must be a JSON object');
  }
  if (raw.version !== 1) {
    throw new Error('frontend-globals.allowlist.json must have version: 1');
  }
  if (!Array.isArray(raw.globals)) {
    throw new Error('frontend-globals.allowlist.json must contain a globals array');
  }
  const seen = new Set();
  const globals = raw.globals.map((entry, index) => {
    if (!entry || typeof entry !== 'object' || Array.isArray(entry)) {
      throw new Error(`Allowlist entry ${index + 1} must be an object`);
    }
    const name = String(entry.name || '').trim();
    const purpose = String(entry.purpose || '').trim();
    const owner = String(entry.owner || '').trim();
    const reason = String(entry.reason || '').trim();
    const removalTarget = String(entry.removal_target || '').trim();
    const sources = Array.isArray(entry.sources)
      ? entry.sources.map((source) => String(source || '').trim()).filter(Boolean)
      : ['*'];
    if (!name) throw new Error(`Allowlist entry ${index + 1} must include name`);
    if (!ALLOWLIST_PURPOSES.has(purpose)) {
      throw new Error(`Allowlist entry ${name} has unsupported purpose ${purpose}`);
    }
    if (!owner) throw new Error(`Allowlist entry ${name} must include owner`);
    if (!reason) throw new Error(`Allowlist entry ${name} must include reason`);
    if (!removalTarget) throw new Error(`Allowlist entry ${name} must include removal_target`);
    if (!sources.length) throw new Error(`Allowlist entry ${name} must include at least one source`);
    const key = `${name}:${purpose}:${sources.slice().sort().join(',')}`;
    if (seen.has(key)) throw new Error(`Duplicate allowlist entry for ${name}`);
    seen.add(key);
    return {
      name,
      purpose,
      owner,
      reason,
      removal_target: removalTarget,
      sources,
    };
  });
  return {
    version: raw.version,
    globals,
  };
}

function allowlistMatchesSource(entry, source) {
  return entry.sources.includes('*') || entry.sources.includes(source);
}

function findAllowlistEntry(allowlist, name, source) {
  return allowlist.globals.find((entry) => (
    entry.name === name && allowlistMatchesSource(entry, source)
  )) || null;
}

function findAllowlistEntryForRead(allowlist, name, source, providers = []) {
  return allowlist.globals.find((entry) => {
    if (entry.name !== name) return false;
    return allowlistMatchesSource(entry, source)
      || providers.some((provider) => allowlistMatchesSource(entry, provider));
  }) || null;
}

function collectFiles(dir, prefix = '') {
  if (!existsSync(dir)) return [];
  const files = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const rel = prefix ? `${prefix}/${entry.name}` : entry.name;
    const full = resolve(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...collectFiles(full, rel));
    } else if (entry.isFile() && rel.endsWith('.js') && !rel.startsWith('vendor/')) {
      files.push(rel);
    }
  }
  return files.sort();
}

function nodeLine(node) {
  return node && node.loc && node.loc.start ? node.loc.start.line : null;
}

function definitionKind(definition) {
  if (definition.type === 'FunctionName') return 'function';
  if (definition.type === 'ClassName') return 'class';
  if (definition.type === 'Variable') {
    return definition.parent && definition.parent.kind
      ? definition.parent.kind
      : 'var';
  }
  return definition.type;
}

function memberPropertyName(member) {
  if (!member || member.type !== 'MemberExpression') return '';
  if (!member.computed && member.property && member.property.type === 'Identifier') {
    return member.property.name;
  }
  if (member.computed && member.property && member.property.type === 'Literal') {
    return typeof member.property.value === 'string' ? member.property.value : '';
  }
  return '';
}

function isWindowMember(member) {
  return !!(
    member
    && member.type === 'MemberExpression'
    && member.object
    && member.object.type === 'Identifier'
    && ['global', 'globalThis', 'window'].includes(member.object.name)
  );
}

function walkAst(node, visitor, parent = null) {
  if (!node || typeof node.type !== 'string') return;
  visitor(node, parent);
  for (const [key, value] of Object.entries(node)) {
    if (
      key === 'parent'
      || key === 'loc'
      || key === 'range'
      || key === 'tokens'
      || key === 'comments'
    ) {
      continue;
    }
    if (Array.isArray(value)) {
      for (const child of value) walkAst(child, visitor, node);
    } else if (value && typeof value.type === 'string') {
      walkAst(value, visitor, node);
    }
  }
}

function dedupeByNameAndLine(items) {
  const seen = new Set();
  const deduped = [];
  for (const item of items) {
    const key = `${item.name}:${item.line || ''}`;
    if (seen.has(key)) continue;
    seen.add(key);
    deduped.push(item);
  }
  return deduped;
}

function dedupeReads(reads) {
  const seen = new Set();
  const deduped = [];
  for (const read of reads) {
    const key = `${read.name}:${read.line || ''}`;
    if (seen.has(key)) continue;
    seen.add(key);
    deduped.push(read);
  }
  return deduped;
}

function literalStringValue(node) {
  return node && node.type === 'Literal' && typeof node.value === 'string'
    ? node.value
    : '';
}

function objectPropertyKeyName(property) {
  if (!property || property.type !== 'Property') return '';
  if (property.key.type === 'Identifier') return property.key.name;
  if (property.key.type === 'Literal' && typeof property.key.value === 'string') return property.key.value;
  return '';
}

function isObjectMethodCall(node, methodName) {
  return !!(
    node
    && node.type === 'CallExpression'
    && node.callee
    && node.callee.type === 'MemberExpression'
    && node.callee.object
    && node.callee.object.type === 'Identifier'
    && node.callee.object.name === 'Object'
    && memberPropertyName(node.callee) === methodName
  );
}

function collectWindowPublishes(ast) {
  const publishes = [];
  walkAst(ast, (node) => {
    if (node.type === 'AssignmentExpression' && isWindowMember(node.left)) {
      const name = memberPropertyName(node.left);
      if (name) publishes.push({ name, line: nodeLine(node.left), via: 'assignment' });
      return;
    }
    if (
      isObjectMethodCall(node, 'assign')
      && node.arguments.length >= 2
      && node.arguments[0].type === 'Identifier'
      && ['global', 'globalThis', 'window'].includes(node.arguments[0].name)
      && node.arguments[1].type === 'ObjectExpression'
    ) {
      for (const property of node.arguments[1].properties) {
        const name = objectPropertyKeyName(property);
        if (name) publishes.push({ name, line: nodeLine(property.key), via: 'object-assign' });
      }
      return;
    }
    if (
      isObjectMethodCall(node, 'defineProperty')
      && node.arguments.length >= 2
      && node.arguments[0].type === 'Identifier'
      && ['global', 'globalThis', 'window'].includes(node.arguments[0].name)
    ) {
      const name = literalStringValue(node.arguments[1]);
      if (name) publishes.push({ name, line: nodeLine(node.arguments[1]), via: 'define-property' });
      return;
    }
    if (
      node.type === 'CallExpression'
      && node.callee
      && node.callee.type === 'Identifier'
      && node.callee.name === '_publishDomRefs'
      && node.arguments[0]
      && node.arguments[0].type === 'ObjectExpression'
    ) {
      for (const property of node.arguments[0].properties) {
        const name = objectPropertyKeyName(property);
        if (name) publishes.push({ name, line: nodeLine(property.key), via: '_publishDomRefs' });
      }
      return;
    }
    if (
      node.type === 'VariableDeclarator'
      && node.id
      && node.id.type === 'Identifier'
      && node.id.name === 'bindings'
      && node.init
      && node.init.type === 'ArrayExpression'
    ) {
      for (const item of node.init.elements) {
        const name = literalStringValue(item);
        if (name) publishes.push({ name, line: nodeLine(item), via: 'state-bindings' });
      }
    }
  });
  return dedupeByNameAndLine(publishes);
}

function collectWindowReads(ast) {
  const reads = [];
  walkAst(ast, (node, parent) => {
    if (!isWindowMember(node)) return;
    if (parent && parent.type === 'AssignmentExpression' && parent.left === node) return;
    const name = memberPropertyName(node);
    if (name) reads.push({ name, line: nodeLine(node), via: 'member-read' });
  });
  return dedupeByNameAndLine(reads);
}

function analyzeSource(source, file) {
  const content = readFileSync(file, 'utf8');
  const linter = new Linter({ configType: 'flat' });

  function verifyWithSourceType(sourceType) {
    let ast = null;
    let scopeManager = null;
    const captureRule = {
      create(context) {
        return {
          Program(node) {
            ast = node;
            scopeManager = context.sourceCode.scopeManager;
          },
        };
      },
    };
    const messages = linter.verify(
      content,
      {
        languageOptions: {
          ecmaVersion: 'latest',
          sourceType,
        },
        plugins: {
          inventory: {
            rules: {
              capture: captureRule,
            },
          },
        },
        rules: {
          'inventory/capture': 'error',
        },
      },
      { filename: file },
    );
    return {
      messages,
      ast,
      scopeManager,
    };
  }

  let result = verifyWithSourceType('module');
  let fatal = result.messages.find((message) => message.fatal);
  if (fatal) {
    result = verifyWithSourceType('script');
    fatal = result.messages.find((message) => message.fatal);
  }
  if (fatal) {
    throw new Error(`${source}:${fatal.line}:${fatal.column} ${fatal.message}`);
  }
  const { ast, scopeManager } = result;
  if (!ast || !scopeManager || !scopeManager.globalScope) {
    throw new Error(`Unable to read ESLint scope for ${source}`);
  }
  const topScopes = (scopeManager.scopes || [])
    .filter((scope) => scope.type === 'global' || scope.type === 'module');
  const topLevelDefinitions = topScopes
    .flatMap((scope) => scope.variables)
    .filter((variable) => variable.defs.length)
    .flatMap((variable) => variable.defs.map((definition) => ({
      name: variable.name,
      kind: definitionKind(definition),
      line: nodeLine(definition.name || definition.node),
    })))
    .sort((left, right) => (left.line || 0) - (right.line || 0) || left.name.localeCompare(right.name));
  const bareReads = dedupeReads(topScopes
    .flatMap((scope) => scope.through || [])
    .map((reference) => ({
      name: reference.identifier.name,
      line: nodeLine(reference.identifier),
    }))
    .sort((left, right) => (left.line || 0) - (right.line || 0) || left.name.localeCompare(right.name)));
  return {
    source,
    file: relative(ROOT, file),
    top_level_definitions: topLevelDefinitions,
    window_publishes: collectWindowPublishes(ast),
    window_reads: collectWindowReads(ast),
    bare_reads: bareReads,
  };
}

function summarizeReads(reads, providerMap, ownNames) {
  const byName = new Map();
  for (const read of reads) {
    if (!providerMap.has(read.name) || ownNames.has(read.name)) continue;
    const current = byName.get(read.name) || {
      name: read.name,
      count: 0,
      lines: [],
      providers: Array.from(providerMap.get(read.name)).sort(),
    };
    current.count += 1;
    if (read.line && !current.lines.includes(read.line)) current.lines.push(read.line);
    byName.set(read.name, current);
  }
  return Array.from(byName.values()).sort((left, right) => left.name.localeCompare(right.name));
}

function summarizeUnresolvedAppReads(reads, definitionMap, publishMap, ownNames) {
  const byName = new Map();
  for (const read of reads) {
    if (!definitionMap.has(read.name) || publishMap.has(read.name) || ownNames.has(read.name)) continue;
    const current = byName.get(read.name) || {
      name: read.name,
      count: 0,
      lines: [],
      definitions: Array.from(definitionMap.get(read.name)).sort(),
    };
    current.count += 1;
    if (read.line && !current.lines.includes(read.line)) current.lines.push(read.line);
    byName.set(read.name, current);
  }
  return Array.from(byName.values()).sort((left, right) => left.name.localeCompare(right.name));
}

function classifyPublish(publish, source, allowlist) {
  const allowed = findAllowlistEntry(allowlist, publish.name, source);
  if (allowed) {
    return {
      ...publish,
      purpose: allowed.purpose,
      owner: allowed.owner,
      reason: allowed.reason,
      removal_target: allowed.removal_target,
    };
  }
  return {
    ...publish,
    purpose: source === LAZY_ASSETS_SOURCE ? 'lazy_placeholder' : 'compatibility_export',
  };
}

function classifyRead(read, source, providers, allowlist) {
  const providerList = Array.isArray(providers) ? providers : [];
  const allowed = findAllowlistEntryForRead(allowlist, read.name, source, providerList);
  if (allowed) {
    return {
      ...read,
      purpose: allowed.purpose,
      owner: allowed.owner,
      reason: allowed.reason,
      removal_target: allowed.removal_target,
    };
  }
  return {
    ...read,
    purpose: providerList.length && providerList.every((provider) => provider === LAZY_ASSETS_SOURCE)
      ? 'lazy_placeholder'
      : 'compatibility_read',
  };
}

function summarizeWindowReads(reads, publishMap, ownNames, source, allowlist) {
  const byName = new Map();
  for (const read of reads) {
    const providers = publishMap.has(read.name)
      ? Array.from(publishMap.get(read.name)).sort()
      : [];
    const allowed = findAllowlistEntryForRead(allowlist, read.name, source, providers);
    if (!allowed && !providers.length) continue;
    if (ownNames.has(read.name)) continue;
    const current = byName.get(read.name) || {
      name: read.name,
      count: 0,
      lines: [],
      providers,
    };
    current.count += 1;
    if (read.line && !current.lines.includes(read.line)) current.lines.push(read.line);
    byName.set(read.name, current);
  }
  return Array.from(byName.values())
    .map((read) => classifyRead(read, source, read.providers, allowlist))
    .sort((left, right) => left.name.localeCompare(right.name));
}

function classifyModule(module) {
  const defines = module.top_level_definitions.length > 0 || module.window_publishes.length > 0;
  const consumes = module.foreign_bare_reads.length > 0 || module.unresolved_app_bare_reads.length > 0;
  if (defines && consumes) return 'tangled';
  if (consumes) return 'consumer-only';
  if (defines) return 'pure leaf';
  return 'isolated';
}

function markdownList(items, limit = 8) {
  if (!items.length) return '-';
  const names = items.slice(0, limit).map((item) => item.name);
  const suffix = items.length > limit ? `, +${items.length - limit} more` : '';
  return `${names.join(', ')}${suffix}`;
}

function countByPurpose(modules, key) {
  const counts = {};
  for (const module of modules) {
    for (const item of module[key] || []) {
      const purpose = item.purpose || 'unclassified';
      counts[purpose] = (counts[purpose] || 0) + 1;
    }
  }
  return Object.fromEntries(Object.entries(counts).sort(([left], [right]) => left.localeCompare(right)));
}

function nonAllowlistedItems(modules, key, purpose) {
  return modules
    .flatMap((module) => (module[key] || [])
      .filter((item) => item.purpose === purpose)
      .map((item) => ({ module, item })));
}

function formatInventoryItem({ module, item }) {
  const lines = Array.isArray(item.lines) && item.lines.length
    ? item.lines.join(', ')
    : item.line || '?';
  const providers = Array.isArray(item.providers) && item.providers.length
    ? ` providers: ${item.providers.join(', ')}`
    : '';
  return `${module.source}: window.${item.name} lines ${lines}${providers}`;
}

function allowlistEntryMatchesInventoryItem(entry, source, item) {
  if (!item || item.name !== entry.name || item.purpose !== entry.purpose) return false;
  if (allowlistMatchesSource(entry, source)) return true;
  return Array.isArray(item.providers)
    && item.providers.some((provider) => allowlistMatchesSource(entry, provider));
}

function unusedAllowlistEntries(allowlist, modules) {
  return allowlist.globals
    .filter((entry) => !modules.some((module) => (
      (module.window_publishes || []).some((item) => (
        allowlistEntryMatchesInventoryItem(entry, module.source, item)
      ))
      || (module.foreign_bare_reads || []).some((item) => (
        allowlistEntryMatchesInventoryItem(entry, module.source, item)
      ))
      || (module.window_property_reads || []).some((item) => (
        allowlistEntryMatchesInventoryItem(entry, module.source, item)
      ))
    )))
    .map((entry) => ({
      name: entry.name,
      purpose: entry.purpose,
      owner: entry.owner,
      sources: entry.sources,
      removal_target: entry.removal_target,
    }));
}

function formatAllowlistEntry(entry) {
  return `${entry.name} (${entry.purpose}) sources: ${entry.sources.join(', ')} owner: ${entry.owner}`;
}

function printMarkdown(report) {
  console.log('# Frontend Module Inventory');
  console.log('');
  console.log(`Generated from ${report.module_count} app JS files. Vendored JS is excluded.`);
  console.log('');
  console.log('| Classification | Count |');
  console.log('| --- | ---: |');
  for (const [classification, count] of Object.entries(report.summary.classifications)) {
    console.log(`| ${classification} | ${count} |`);
  }
  console.log('');
  console.log(`Unresolved app bare reads: ${report.summary.unresolved_app_bare_read_count}`);
  console.log('');
  console.log('| Global purpose | Publishes | Bare reads | Window reads |');
  console.log('| --- | ---: | ---: | ---: |');
  for (const purpose of ALLOWLIST_PURPOSES) {
    console.log([
      purpose,
      report.summary.window_publish_purposes[purpose] || 0,
      report.summary.foreign_bare_read_purposes[purpose] || 0,
      report.summary.window_property_read_purposes[purpose] || 0,
    ].join(' | ').replace(/^/, '| ').replace(/$/, ' |'));
  }
  console.log('');
  console.log('| Source | Classification | Defines / publishes | Foreign bare reads | Window property reads |');
  console.log('| --- | --- | --- | --- | --- |');
  for (const module of report.modules) {
    const definitions = [
      ...module.top_level_definitions,
      ...module.window_publishes.map((item) => ({ ...item, name: `window.${item.name}` })),
    ];
    const reads = module.unresolved_app_bare_reads.length
      ? [
          ...module.foreign_bare_reads,
          ...module.unresolved_app_bare_reads.map((item) => ({ ...item, name: `${item.name} (unresolved)` })),
        ].sort((left, right) => left.name.localeCompare(right.name))
      : module.foreign_bare_reads;
    console.log([
      `\`${module.source}\``,
      module.classification,
      markdownList(definitions),
      markdownList(reads),
      markdownList(module.window_property_reads),
    ].join(' | ').replace(/^/, '| ').replace(/$/, ' |'));
  }
}

const allowlist = loadAllowlist();
const jsRoot = resolve(ROOT, 'app/static/js');
const sources = collectFiles(jsRoot).map((rel) => ({
  source: `/static/js/${rel}`,
  file: resolve(jsRoot, rel),
}));
const modules = sources.map(({ source, file }) => analyzeSource(source, file));
const definitionMap = new Map();
const publishMap = new Map();
for (const module of modules) {
  for (const definition of module.top_level_definitions) {
    if (!definitionMap.has(definition.name)) definitionMap.set(definition.name, new Set());
    definitionMap.get(definition.name).add(module.source);
  }
  for (const publish of module.window_publishes) {
    if (!publishMap.has(publish.name)) publishMap.set(publish.name, new Set());
    publishMap.get(publish.name).add(module.source);
  }
}

for (const module of modules) {
  const ownNames = new Set([
    ...module.top_level_definitions.map((definition) => definition.name),
    ...module.window_publishes.map((publish) => publish.name),
  ]);
  module.window_publishes = module.window_publishes.map((publish) => (
    classifyPublish(publish, module.source, allowlist)
  ));
  module.foreign_bare_reads = summarizeReads(module.bare_reads, publishMap, ownNames);
  module.foreign_bare_reads = module.foreign_bare_reads.map((read) => (
    classifyRead(read, module.source, read.providers, allowlist)
  ));
  module.unresolved_app_bare_reads = summarizeUnresolvedAppReads(module.bare_reads, definitionMap, publishMap, ownNames);
  module.window_property_reads = summarizeWindowReads(
    module.window_reads,
    publishMap,
    ownNames,
    module.source,
    allowlist,
  );
  delete module.bare_reads;
  delete module.window_reads;
  module.classification = classifyModule(module);
}

const classifications = {};
for (const module of modules) {
  classifications[module.classification] = (classifications[module.classification] || 0) + 1;
}

const report = {
  generated_by: 'scripts/inventory_frontend_modules.mjs',
  allowlist: {
    path: relative(ROOT, ALLOWLIST_PATH),
    entry_count: allowlist.globals.length,
    purposes: Object.fromEntries(
      Array.from(ALLOWLIST_PURPOSES).map((purpose) => [
        purpose,
        allowlist.globals.filter((entry) => entry.purpose === purpose).length,
      ]),
    ),
    unused_entries: unusedAllowlistEntries(allowlist, modules),
  },
  module_count: modules.length,
  summary: {
    classifications,
    unresolved_app_bare_read_count: modules.reduce((total, module) => total + module.unresolved_app_bare_reads.length, 0),
    unused_allowlist_entry_count: unusedAllowlistEntries(allowlist, modules).length,
    window_publish_purposes: countByPurpose(modules, 'window_publishes'),
    foreign_bare_read_purposes: countByPurpose(modules, 'foreign_bare_reads'),
    window_property_read_purposes: countByPurpose(modules, 'window_property_reads'),
  },
  modules,
};

if (checkOnly && report.summary.unresolved_app_bare_read_count > 0) {
  const details = modules
    .filter((module) => module.unresolved_app_bare_reads.length)
    .flatMap((module) => module.unresolved_app_bare_reads.map((read) => (
      `${module.source}: ${read.name} lines ${read.lines.join(', ')} defined by ${read.definitions.join(', ')} but not published`
    )));
  console.error(`Frontend inventory found unresolved app bare reads:\n${details.map((line) => `  ${line}`).join('\n')}`);
  process.exit(1);
}

if (checkOnly) {
  const nonAllowlistedPublishes = nonAllowlistedItems(modules, 'window_publishes', 'compatibility_export');
  const nonAllowlistedReads = nonAllowlistedItems(modules, 'window_property_reads', 'compatibility_read');
  if (nonAllowlistedPublishes.length || nonAllowlistedReads.length) {
    const sections = [];
    if (nonAllowlistedPublishes.length) {
      sections.push(`Non-allowlisted window publishes:\n${nonAllowlistedPublishes.map((entry) => `  ${formatInventoryItem(entry)}`).join('\n')}`);
    }
    if (nonAllowlistedReads.length) {
      sections.push(`Non-allowlisted window reads:\n${nonAllowlistedReads.map((entry) => `  ${formatInventoryItem(entry)}`).join('\n')}`);
    }
    console.error(`Frontend inventory found browser globals missing from frontend-globals.allowlist.json:\n${sections.join('\n')}`);
    process.exit(1);
  }
}

if (checkOnly && report.allowlist.unused_entries.length) {
  console.error(
    'Frontend inventory found unused frontend-globals.allowlist.json entries:\n'
    + report.allowlist.unused_entries.map((entry) => `  ${formatAllowlistEntry(entry)}`).join('\n'),
  );
  process.exit(1);
}

if (jsonOutput) {
  console.log(JSON.stringify(report, null, 2));
} else if (checkOnly) {
  console.log('Frontend inventory check passed: all app bare reads have publish paths and the allowlist is current.');
} else {
  printMarkdown(report);
}
