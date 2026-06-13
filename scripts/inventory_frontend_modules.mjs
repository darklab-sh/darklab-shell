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

if (help) {
  console.log(`Usage: node scripts/inventory_frontend_modules.mjs [--json] [--check]

Prints a per-file inventory of frontend compatibility-global coupling:
  - top-level function/var/let/const/class names
  - explicit window.* properties published by the file, including helper publishers
  - bare identifier reads that resolve to names published by another app file
  - a coarse migration classification: pure leaf, consumer-only, tangled, or isolated

With --check, fails if an app-level bare read has no matching publish path.
`);
  process.exit(0);
}

const unknownArgs = args.filter((arg) => !['--json', '--check'].includes(arg));
if (unknownArgs.length) {
  throw new Error(`Unknown argument: ${unknownArgs.join(', ')}`);
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

function walkAst(node, visitor) {
  if (!node || typeof node.type !== 'string') return;
  visitor(node);
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
      for (const child of value) walkAst(child, visitor);
    } else if (value && typeof value.type === 'string') {
      walkAst(value, visitor);
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
  console.log('| Source | Classification | Defines / publishes | Foreign bare reads |');
  console.log('| --- | --- | --- | --- |');
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
    ].join(' | ').replace(/^/, '| ').replace(/$/, ' |'));
  }
}

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
  module.foreign_bare_reads = summarizeReads(module.bare_reads, publishMap, ownNames);
  module.unresolved_app_bare_reads = summarizeUnresolvedAppReads(module.bare_reads, definitionMap, publishMap, ownNames);
  delete module.bare_reads;
  module.classification = classifyModule(module);
}

const classifications = {};
for (const module of modules) {
  classifications[module.classification] = (classifications[module.classification] || 0) + 1;
}

const report = {
  generated_by: 'scripts/inventory_frontend_modules.mjs',
  module_count: modules.length,
  summary: {
    classifications,
    unresolved_app_bare_read_count: modules.reduce((total, module) => total + module.unresolved_app_bare_reads.length, 0),
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

if (jsonOutput) {
  console.log(JSON.stringify(report, null, 2));
} else if (checkOnly) {
  console.log('Frontend inventory check passed: all app bare reads have publish paths.');
} else {
  printMarkdown(report);
}
