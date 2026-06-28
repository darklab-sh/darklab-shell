#!/usr/bin/env node
/**
 * Inventory intentional frontend browser-global boundaries.
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
  'bridge_internal',
  'test_hook',
  'compatibility_export',
  'compatibility_read',
]);
// Browser-global names that are recognized bridge-internal plumbing (handler
// stores, bridge persistence, e2e/test hooks) rather than a cross-module API.
// They are auto-classified as `bridge_internal` and, like lazy placeholders, do
// not require an explicit allowlist entry.
const BRIDGE_INTERNAL_NAME_PATTERN = /^__darklab/;
const LAZY_ASSETS_SOURCE = '/static/js/core/lazy_assets.js';
const RESOLVER_HELPER_REGISTRY = Object.freeze({
  _appEl: { class: 'import_first', name_arg: 0, fallback_arg: 1 },
  _appFn: { class: 'import_first', name_arg: 0, fallback_arg: 1 },
  _appValue: { class: 'import_first', name_arg: 0, fallback_arg: 1 },
  _autocompleteGlobalFunction: { class: 'global_only', name_arg: 0 },
  _callControllerActionHandler: { class: 'bridge_dispatch', name_arg: 0 },
  _callOutputHandler: { class: 'bridge_dispatch', name_arg: 0 },
  _callRunnerHandler: { class: 'bridge_dispatch', name_arg: 0 },
  _callTabHandler: { class: 'bridge_dispatch', name_arg: 0 },
  _callWorkflowHandler: { class: 'bridge_dispatch', name_arg: 0 },
  _callTabGlobal: { class: 'global_only', name_arg: 0 },
  _cliGlobalFunction: { class: 'global_only', name_arg: 0 },
  _composerEditingGlobalFunction: { class: 'global_only', name_arg: 0 },
  _composerFn: { class: 'import_first', name_arg: 0, fallback_arg: 1 },
  _composerValue: { class: 'global_only', name_arg: 0 },
  _controllerFn: { class: 'import_first', name_arg: 0, fallback_arg: 1 },
  _faqGlobalFunction: { class: 'global_only', name_arg: 0 },
  hasOutputHandler: { class: 'bridge_dispatch', name_arg: 0 },
  hasRunnerHandler: { class: 'bridge_dispatch', name_arg: 0 },
  hasTabHandler: { class: 'bridge_dispatch', name_arg: 0 },
  hasWorkflowHandler: { class: 'bridge_dispatch', name_arg: 0 },
  _historyCompareRendererGlobalFunction: { class: 'global_only', name_arg: 0 },
  _historyEl: { class: 'import_first', name_arg: 0, fallback_arg: 1 },
  _historyFn: { class: 'import_first', name_arg: 0, fallback_arg: 1 },
  _historyRestoreGlobalFunction: { class: 'global_only', name_arg: 0 },
  _historyRowsGlobalFunction: { class: 'global_only', name_arg: 0 },
  _historyRunGlobalFunction: { class: 'global_only', name_arg: 0 },
  _historyRunGlobalValue: { class: 'global_only', name_arg: 0 },
  _historyValue: { class: 'import_first', name_arg: 0, fallback_arg: 1 },
  _mobileKeyboardGlobalFunction: { class: 'global_only', name_arg: 0 },
  _mobileMenuCall: { class: 'global_only', name_arg: 0 },
  _mobileMenuGlobalFunction: { class: 'global_only', name_arg: 0 },
  _optionsSecretsGlobalFunction: { class: 'global_only', name_arg: 0 },
  _outputGlobalFunction: { class: 'global_only', name_arg: 0 },
  _outputGlobalValue: { class: 'global_only', name_arg: 0 },
  _preferenceGlobalFunction: { class: 'global_only', name_arg: 0 },
  _projectModule: { class: 'import_first', name_arg: 0, fallback_arg: 1 },
  _ptyCall: { class: 'import_first', name_arg: 0, fallback_arg: 1 },
  _ptyGlobalFunction: { class: 'global_only', name_arg: 0 },
  _ptyGlobalValue: { class: 'global_only', name_arg: 0 },
  _runtimeGlobalFunction: { class: 'global_only', name_arg: 0 },
  _runnerEl: { class: 'import_first', name_arg: 0, fallback_arg: 1 },
  _runnerFn: { class: 'import_first', name_arg: 0, fallback_arg: 1 },
  _runnerValue: { class: 'import_first', name_arg: 0, fallback_arg: 1 },
  _searchGlobalFunction: { class: 'global_only', name_arg: 0 },
  _searchGlobalValue: { class: 'global_only', name_arg: 0 },
  _sessionTokenGlobalFunction: { class: 'global_only', name_arg: 0 },
  _shellFn: { class: 'import_first', name_arg: 0, fallback_arg: 1 },
  _shellValue: { class: 'import_first', name_arg: 0, fallback_arg: 1 },
  _statusMonitorGlobalFunction: { class: 'global_only', name_arg: 0 },
  _statusMonitorGlobalValue: { class: 'global_only', name_arg: 0 },
  _tabCloseGlobalFunction: { class: 'global_only', name_arg: 0 },
  _tabEl: { class: 'import_first', name_arg: 0, fallback_arg: 1 },
  _tabExportGlobalFunction: { class: 'global_only', name_arg: 0 },
  _tabGlobalFn: { class: 'import_first', name_arg: 0, fallback_arg: 1 },
  _tabGlobalValue: { class: 'import_first', name_arg: 0, fallback_arg: 1 },
  _tabOutputFn: { class: 'import_first', name_arg: 0, fallback_arg: 1 },
  _tabSearchFn: { class: 'import_first', name_arg: 0, fallback_arg: 1 },
  _tabSessionGlobalFunction: { class: 'global_only', name_arg: 0 },
  _tabWelcomeApi: { class: 'global_only', name_arg: 0 },
  _tourGlobalFunction: { class: 'global_only', name_arg: 0 },
  _welcomeApi: { class: 'global_only', name_arg: 0 },
  _welcomeGlobalFunction: { class: 'global_only', name_arg: 0 },
  _welcomeGlobalValue: { class: 'global_only', name_arg: 0 },
  _workflowGlobalFunction: { class: 'global_only', name_arg: 0 },
  shortcutCall: { class: 'global_only', name_arg: 0 },
  shortcutFunction: { class: 'global_only', name_arg: 0 },
  shortcutGlobalFunction: { class: 'global_only', name_arg: 0 },
  shortcutSurfaceFunction: { class: 'global_only', name_arg: 0 },
  shortcutIsOpen: { class: 'global_only', name_arg: 0 },
  uiFn: { class: 'import_first', name_arg: 0, fallback_arg: 1 },
  uiValue: { class: 'global_only', name_arg: 0 },
});
const RESOLVER_HELPER_NAMES = new Set(Object.keys(RESOLVER_HELPER_REGISTRY));
// Functions structural discovery flags as resolver-shaped but that are not
// tracked string-keyed resolvers (discovery errs toward over-detection; this is
// the audited escape hatch). Each entry must still be discovered, or the
// completeness meta-test reports it as a dead ignore entry.
const RESOLVER_HELPER_IGNORE = Object.freeze({
  _sessionCallAsync: 'Dispatches a session-refresh task name against a local imported-function map, falling back to a SESSION_GLOBAL aliased lookup the literal-publish scanner cannot resolve.',
  _stateValue: 'Reads APP_STATE / search-state slots by key; the keys are internal state slots, not module-API global names.',
});
const RESOLVER_HELPER_IGNORE_NAMES = new Set(Object.keys(RESOLVER_HELPER_IGNORE));
const BRIDGE_DISPATCH_REGISTRY = Object.freeze({
  _callControllerActionHandler: {
    bridge: 'controller_action',
    handler_store: 'controllerActionHandlers',
    setter: 'setControllerActionHandlers',
  },
  _callOutputHandler: {
    bridge: 'output',
    handler_store: 'outputHandlers',
    setter: 'setOutputHandlers',
  },
  _callRunnerHandler: {
    bridge: 'runner',
    handler_store: 'runnerHandlers',
    setter: 'setRunnerHandlers',
  },
  _callTabHandler: {
    bridge: 'tabs',
    handler_store: 'tabHandlers',
    setter: 'setTabHandlers',
  },
  _callWorkflowHandler: {
    bridge: 'workflows',
    handler_store: 'workflowHandlers',
    setter: 'setWorkflowHandlers',
  },
  hasOutputHandler: {
    bridge: 'output',
    handler_store: 'outputHandlers',
    setter: 'setOutputHandlers',
  },
  hasRunnerHandler: {
    bridge: 'runner',
    handler_store: 'runnerHandlers',
    setter: 'setRunnerHandlers',
  },
  hasTabHandler: {
    bridge: 'tabs',
    handler_store: 'tabHandlers',
    setter: 'setTabHandlers',
  },
  hasWorkflowHandler: {
    bridge: 'workflows',
    handler_store: 'workflowHandlers',
    setter: 'setWorkflowHandlers',
  },
});
const BRIDGE_SETTER_NAMES = new Set(Object.values(BRIDGE_DISPATCH_REGISTRY).map((entry) => entry.setter));
const BRIDGE_HANDLER_STORES = new Set(Object.values(BRIDGE_DISPATCH_REGISTRY).map((entry) => entry.handler_store));
// Helpers that publish a browser global under a name passed as a string-literal
// argument (computed-key publishes the direct window.* matcher cannot see). Each
// helper's name-arg call sites are recorded as publishes so the consuming
// resolver lookups resolve as global_publish honestly rather than via allowlist.
const PUBLISHER_HELPER_REGISTRY = Object.freeze({
  loadProjectNamespace: { name_arg: 1 },
  _setStateValue: { name_arg: 0 },
});
const PUBLISHER_HELPER_NAMES = new Set(Object.keys(PUBLISHER_HELPER_REGISTRY));

if (help) {
  console.log(`Usage: node scripts/inventory_frontend_modules.mjs [--json] [--check]

Prints a per-file inventory of frontend browser-global boundaries:
  - top-level function/var/let/const/class names
  - explicit window.* properties published by the file, including helper publishers
  - explicit window.* property reads for app/vendor globals tracked by the allowlist
  - bare identifier reads that resolve to names published by another app file
  - a purpose classification for known browser globals and intentional bridges
  - a coarse coupling classification: pure leaf, consumer-only, tangled, or isolated

With --check, fails if an app-level bare read has no matching publish path.
It also fails if a string-keyed ESM resolver helper has no import, bridge,
publish, or allowlist-backed resolution path.
It also fails if an explicit bridge dispatch key is not declared and
registered by its bridge.
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

function calleeIdentifierName(callee) {
  return callee && callee.type === 'Identifier' ? callee.name : '';
}

function collectImportSourceNames(ast) {
  const imports = new Map();
  walkAst(ast, (node) => {
    if (node.type !== 'ImportDeclaration') return;
    for (const specifier of node.specifiers || []) {
      if (!specifier.local || specifier.local.type !== 'Identifier') continue;
      const local = specifier.local.name;
      let imported = local;
      if (specifier.type === 'ImportSpecifier' && specifier.imported) {
        imported = specifier.imported.type === 'Identifier'
          ? specifier.imported.name
          : String(specifier.imported.value || '');
      } else if (specifier.type === 'ImportNamespaceSpecifier') {
        imported = '*';
      } else if (specifier.type === 'ImportDefaultSpecifier') {
        imported = 'default';
      }
      imports.set(local, {
        local,
        imported,
        source: literalStringValue(node.source),
      });
    }
  });
  return imports;
}

function importedSourceName(importBindings, localName) {
  const binding = importBindings.get(localName);
  return binding ? binding.imported : '';
}

function collectDeclaredBindings(ast) {
  // A binding assigned anywhere in the module (e.g. a `let` populated by a lazy
  // loader before reuse) can hold a value, so it counts as a real resolution
  // path. Only a binding that is declared and NEVER assigned is the dead
  // `let importedX;` shape that masked the pass-1 openStatusMonitor/openAtlas
  // bugs — that stays unresolved and falls through to the global rule.
  const assignedNames = new Set();
  walkAst(ast, (node) => {
    if (
      node.type === 'AssignmentExpression'
      && node.left
      && node.left.type === 'Identifier'
    ) {
      assignedNames.add(node.left.name);
    }
  });
  const bindings = new Map();
  walkAst(ast, (node) => {
    if (
      (node.type === 'FunctionDeclaration' || node.type === 'ClassDeclaration')
      && node.id
      && node.id.type === 'Identifier'
    ) {
      bindings.set(node.id.name, {
        kind: node.type === 'FunctionDeclaration' ? 'function' : 'class',
        initialized: true,
      });
      return;
    }
    if (node.type !== 'VariableDeclarator' || !node.id || node.id.type !== 'Identifier') return;
    bindings.set(node.id.name, {
      kind: node.parent && node.parent.kind ? node.parent.kind : 'var',
      initialized: !!node.init || assignedNames.has(node.id.name),
    });
  });
  return bindings;
}

function bridgeConfigForSetterName(name) {
  return Object.values(BRIDGE_DISPATCH_REGISTRY).find((entry) => entry.setter === name) || null;
}

function collectBridgeHandlerDeclarations(ast) {
  const declarations = [];
  walkAst(ast, (node) => {
    if (node.type !== 'VariableDeclarator' || !node.id || node.id.type !== 'Identifier') return;
    if (!BRIDGE_HANDLER_STORES.has(node.id.name)) return;
    const config = Object.values(BRIDGE_DISPATCH_REGISTRY).find((entry) => entry.handler_store === node.id.name);
    if (!config) return;
    const init = node.init && node.init.type === 'LogicalExpression' ? node.init.right : node.init;
    if (!init || init.type !== 'ObjectExpression') {
      declarations.push({
        bridge: config.bridge,
        store: node.id.name,
        key: '',
        line: nodeLine(node),
        dynamic: true,
        reason: init ? init.type : 'missing_initializer',
      });
      return;
    }
    for (const property of init.properties || []) {
      if (property.type === 'SpreadElement' || property.computed) {
        declarations.push({
          bridge: config.bridge,
          store: node.id.name,
          key: '',
          line: nodeLine(property),
          dynamic: true,
          reason: property.type === 'SpreadElement' ? 'spread' : 'computed_key',
        });
        continue;
      }
      const key = objectPropertyKeyName(property);
      if (!key) continue;
      declarations.push({
        bridge: config.bridge,
        store: node.id.name,
        key,
        line: nodeLine(property),
        dynamic: false,
      });
    }
  });
  return declarations.sort((left, right) => (
    left.bridge.localeCompare(right.bridge)
    || String(left.key).localeCompare(String(right.key))
    || (left.line || 0) - (right.line || 0)
  ));
}

function collectBridgeHandlerRegistrations(ast, importBindings) {
  const registrations = [];
  walkAst(ast, (node) => {
    if (node.type !== 'CallExpression') return;
    const localName = calleeIdentifierName(node.callee);
    if (!localName) return;
    const importedName = importedSourceName(importBindings, localName);
    const setterName = BRIDGE_SETTER_NAMES.has(localName)
      ? localName
      : BRIDGE_SETTER_NAMES.has(importedName)
        ? importedName
        : '';
    if (!setterName) return;
    const config = bridgeConfigForSetterName(setterName);
    if (!config) return;
    const arg = node.arguments[0];
    if (!arg || arg.type !== 'ObjectExpression') {
      registrations.push({
        bridge: config.bridge,
        setter: setterName,
        key: '',
        line: nodeLine(node),
        dynamic: true,
        reason: arg ? arg.type : 'missing_argument',
      });
      return;
    }
    for (const property of arg.properties || []) {
      if (property.type === 'SpreadElement' || property.computed) {
        registrations.push({
          bridge: config.bridge,
          setter: setterName,
          key: '',
          line: nodeLine(property),
          dynamic: true,
          reason: property.type === 'SpreadElement' ? 'spread' : 'computed_key',
        });
        continue;
      }
      const key = objectPropertyKeyName(property);
      if (!key) continue;
      registrations.push({
        bridge: config.bridge,
        setter: setterName,
        key,
        line: nodeLine(property),
        dynamic: false,
      });
    }
  });
  return registrations.sort((left, right) => (
    left.bridge.localeCompare(right.bridge)
    || String(left.key).localeCompare(String(right.key))
    || (left.line || 0) - (right.line || 0)
  ));
}

function resolverFallbackStatus(argument, importBindings, declaredBindings) {
  if (!argument) return { status: 'missing' };
  if (
    argument.type === 'Literal'
    && (argument.value === null || argument.value === undefined)
  ) {
    return { status: 'nullish_literal' };
  }
  if (argument.type === 'Identifier') {
    const name = argument.name;
    if (name === 'undefined') return { status: 'nullish_literal', local: name };
    if (importBindings.has(name)) {
      const binding = importBindings.get(name);
      return {
        status: 'imported_binding',
        local: name,
        imported: binding.imported,
        source: binding.source,
      };
    }
    if (declaredBindings.has(name)) {
      const binding = declaredBindings.get(name);
      return {
        status: binding.initialized || binding.kind === 'function' || binding.kind === 'class'
          ? 'local_binding'
          : 'unassigned_local',
        local: name,
        kind: binding.kind,
      };
    }
    return { status: 'unknown_identifier', local: name };
  }
  return { status: 'opaque_expression', expression_type: argument.type };
}

function expressionHasResolvedBinding(node, importBindings, declaredBindings) {
  let found = false;
  walkAst(node, (child) => {
    if (found || child.type !== 'Identifier') return;
    const name = child.name;
    if (importBindings.has(name)) {
      found = true;
      return;
    }
    const binding = declaredBindings.get(name);
    if (binding && (binding.initialized || binding.kind === 'function' || binding.kind === 'class')) {
      found = true;
    }
  });
  return found;
}

function resolverGuardStatus(node, parentOf, importBindings, declaredBindings) {
  // Climb out of wrapper expressions so a compatibility fallback stays detected
  // even when the resolver call is nested, e.g. `test ? imported() : (X || null)`
  // or `readId ? readId() : (X?.activeTabId || null)`. The guard requires a
  // *different* resolved binding in a `||`/`??` sibling or a conditional test.
  let current = node;
  let parent = parentOf.get(current);
  while (parent) {
    if (parent.type === 'LogicalExpression' && ['||', '??'].includes(parent.operator)) {
      const sibling = parent.left === current ? parent.right : parent.left;
      if (expressionHasResolvedBinding(sibling, importBindings, declaredBindings)) {
        return { status: 'guarded_by_resolved_sibling' };
      }
    } else if (
      parent.type === 'ConditionalExpression'
      && (parent.consequent === current || parent.alternate === current)
    ) {
      if (expressionHasResolvedBinding(parent.test, importBindings, declaredBindings)) {
        return { status: 'guarded_by_resolved_condition' };
      }
      return null;
    } else if (parent.type !== 'MemberExpression' && parent.type !== 'ChainExpression') {
      // Only climb through `||`/`??` chains and member/optional-chain wrappers;
      // stop at calls, statements, assignments, etc. to avoid over-resolving.
      return null;
    }
    current = parent;
    parent = parentOf.get(current);
  }
  return null;
}

function isGlobalishExpression(node) {
  if (!node) return false;
  if (node.type === 'Identifier') {
    return ['window', 'globalThis', 'global'].includes(node.name) || /_GLOBAL$/.test(node.name);
  }
  if (node.type === 'ConditionalExpression') {
    return isGlobalishExpression(node.consequent) || isGlobalishExpression(node.alternate);
  }
  if (node.type === 'LogicalExpression') {
    return isGlobalishExpression(node.left) || isGlobalishExpression(node.right);
  }
  return false;
}

function functionReturnsGlobalish(fnNode) {
  if (!fnNode) return false;
  if (fnNode.type === 'ArrowFunctionExpression' && fnNode.body && fnNode.body.type !== 'BlockStatement') {
    return isGlobalishExpression(fnNode.body);
  }
  let returns = false;
  walkAst(fnNode.body, (child) => {
    if (returns) return;
    if (child.type === 'ReturnStatement' && isGlobalishExpression(child.argument)) returns = true;
  });
  return returns;
}

function functionNodesWithNames(ast) {
  const fns = [];
  walkAst(ast, (node) => {
    if (node.type === 'FunctionDeclaration' && node.id && node.id.type === 'Identifier') {
      fns.push({ name: node.id.name, fn: node });
    } else if (
      node.type === 'VariableDeclarator'
      && node.id && node.id.type === 'Identifier'
      && node.init
      && (node.init.type === 'FunctionExpression' || node.init.type === 'ArrowFunctionExpression')
    ) {
      fns.push({ name: node.id.name, fn: node.init });
    }
  });
  return fns;
}

// Identifier names in a module that refer to the browser-global object:
// window/globalThis/global, bridge handler stores, `*_GLOBAL` aliases, and locals
// assigned from a global value or a window/globalThis getter (e.g.
// `const global = _outputGlobal()`).
function collectGlobalAliasNames(ast) {
  const names = new Set(['window', 'globalThis', 'global']);
  for (const store of BRIDGE_HANDLER_STORES) names.add(store);
  const getterNames = new Set();
  for (const { name, fn } of functionNodesWithNames(ast)) {
    if (functionReturnsGlobalish(fn)) getterNames.add(name);
  }
  walkAst(ast, (node) => {
    if (node.type !== 'VariableDeclarator' || !node.id || node.id.type !== 'Identifier' || !node.init) return;
    if (isGlobalishExpression(node.init)) {
      names.add(node.id.name);
      return;
    }
    if (
      node.init.type === 'CallExpression'
      && node.init.callee && node.init.callee.type === 'Identifier'
      && getterNames.has(node.init.callee.name)
    ) {
      names.add(node.id.name);
    }
  });
  return names;
}

function isGlobalAliasIdentifier(name, aliasNames) {
  return aliasNames.has(name) || /_GLOBAL$/.test(name);
}

// Structural discovery of resolver-shaped helpers: a function whose first
// parameter is used to index a browser-global alias object (directly, or via a
// local bound to a window/globalThis getter), or that forwards its first
// parameter as the key to an already-discovered/registered resolver helper.
// Discovery only enumerates names; classification stays explicit in the
// committed registry, and the completeness meta-test reconciles the two.
function discoverResolverHelpers(ast) {
  const fns = functionNodesWithNames(ast);
  const getterNames = new Set();
  for (const { name, fn } of fns) {
    if (functionReturnsGlobalish(fn)) getterNames.add(name);
  }
  const aliasLocals = new Set();
  walkAst(ast, (node) => {
    if (node.type !== 'VariableDeclarator' || !node.id || node.id.type !== 'Identifier' || !node.init) return;
    if (isGlobalishExpression(node.init)) {
      aliasLocals.add(node.id.name);
      return;
    }
    if (
      node.init.type === 'CallExpression'
      && node.init.callee && node.init.callee.type === 'Identifier'
      && getterNames.has(node.init.callee.name)
    ) {
      aliasLocals.add(node.id.name);
    }
  });
  const isAlias = (objName) => (
    ['window', 'globalThis', 'global'].includes(objName)
    || /_GLOBAL$/.test(objName)
    || BRIDGE_HANDLER_STORES.has(objName)
    || aliasLocals.has(objName)
  );
  const candidates = [];
  const discovered = new Set();
  for (const { name, fn } of fns) {
    const param0 = (fn.params && fn.params[0] && fn.params[0].type === 'Identifier') ? fn.params[0].name : '';
    if (!param0) continue;
    candidates.push({ name, fn, param0 });
    let direct = false;
    walkAst(fn.body, (child, parent) => {
      if (direct) return;
      // Only a *read* of `OBJ[param0]` marks a resolver; a write (`OBJ[param0] = …`)
      // is a publisher, handled by the publish-side check instead.
      if (parent && parent.type === 'AssignmentExpression' && parent.left === child) return;
      if (
        child.type === 'MemberExpression'
        && child.computed
        && child.object && child.object.type === 'Identifier' && isAlias(child.object.name)
        && child.property && child.property.type === 'Identifier' && child.property.name === param0
      ) {
        direct = true;
      }
    });
    if (direct) discovered.add(name);
  }
  // Delegation fixpoint: a helper that forwards its first param as the key to a
  // known resolver is itself resolver-shaped (covers _projectModule -> _shellValue,
  // _appEl -> _appValue, shortcutFunction -> shortcutGlobalFunction).
  const known = new Set([...discovered, ...RESOLVER_HELPER_NAMES]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const { name, fn, param0 } of candidates) {
      if (discovered.has(name)) continue;
      let delegates = false;
      walkAst(fn.body, (child) => {
        if (delegates) return;
        if (
          child.type === 'CallExpression'
          && child.callee && child.callee.type === 'Identifier' && known.has(child.callee.name)
          && child.arguments && child.arguments[0]
          && child.arguments[0].type === 'Identifier' && child.arguments[0].name === param0
        ) {
          delegates = true;
        }
      });
      if (delegates) {
        discovered.add(name);
        known.add(name);
        changed = true;
      }
    }
  }
  return Array.from(discovered).sort();
}

function collectResolverHelperCalls(ast) {
  const importBindings = collectImportSourceNames(ast);
  const declaredBindings = collectDeclaredBindings(ast);
  const parentOf = new Map();
  walkAst(ast, (node, parent) => {
    if (parent) parentOf.set(node, parent);
  });
  const calls = [];
  walkAst(ast, (node) => {
    if (node.type !== 'CallExpression') return;
    const calleeName = calleeIdentifierName(node.callee);
    // Resolve an aliased import of a resolver helper to its canonical name, e.g.
    // `importedHasRunnerHandler` -> `hasRunnerHandler`, so calls through bridge
    // imports are validated too.
    let helper = calleeName;
    if (!RESOLVER_HELPER_NAMES.has(helper)) {
      const binding = importBindings.get(calleeName);
      if (binding && RESOLVER_HELPER_NAMES.has(binding.imported)) helper = binding.imported;
    }
    if (!RESOLVER_HELPER_NAMES.has(helper)) return;
    const entry = RESOLVER_HELPER_REGISTRY[helper];
    const nameArg = node.arguments[entry.name_arg || 0];
    const name = literalStringValue(nameArg);
    if (!name) {
      calls.push({
        helper,
        class: entry.class,
        line: nodeLine(node),
        name: '',
        name_resolution: 'dynamic_or_non_literal',
      });
      return;
    }
    const call = {
      helper,
      class: entry.class,
      line: nodeLine(node),
      name,
      name_resolution: 'literal',
    };
    const guard = resolverGuardStatus(node, parentOf, importBindings, declaredBindings);
    if (guard) call.guard = guard;
    if (entry.class === 'import_first') {
      call.fallback = resolverFallbackStatus(
        node.arguments[entry.fallback_arg],
        importBindings,
        declaredBindings,
      );
    }
    calls.push(call);
  });
  return calls.sort((left, right) => (left.line || 0) - (right.line || 0) || left.helper.localeCompare(right.helper));
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

function collectWindowPublishes(ast, activePublisherNames = PUBLISHER_HELPER_NAMES) {
  const aliasNames = collectGlobalAliasNames(ast);
  const publishes = [];
  walkAst(ast, (node) => {
    if (node.type === 'AssignmentExpression' && isWindowMember(node.left)) {
      const name = memberPropertyName(node.left);
      if (name) publishes.push({ name, line: nodeLine(node.left), via: 'assignment' });
      return;
    }
    if (
      node.type === 'AssignmentExpression'
      && node.left
      && node.left.type === 'MemberExpression'
      && node.left.object
      && node.left.object.type === 'Identifier'
      && !['global', 'globalThis', 'window'].includes(node.left.object.name)
      && !BRIDGE_HANDLER_STORES.has(node.left.object.name)
      && isGlobalAliasIdentifier(node.left.object.name, aliasNames)
    ) {
      // Aliased browser-global write, e.g. `SOME_GLOBAL.x = …` or
      // `SOME_GLOBAL['x'] = …`. Computed non-literal keys (`SOME_GLOBAL[v] = …`)
      // are handled by the registered publisher helpers instead. Bridge handler
      // stores are excluded — their key writes are registration, validated by the
      // bridge-dispatch reconciliation, not browser-global publishing.
      const name = memberPropertyName(node.left);
      if (name) publishes.push({ name, line: nodeLine(node.left), via: 'alias-assignment' });
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
      node.type === 'CallExpression'
      && node.callee
      && node.callee.type === 'Identifier'
      && activePublisherNames.has(node.callee.name)
    ) {
      const entry = PUBLISHER_HELPER_REGISTRY[node.callee.name];
      const name = literalStringValue(node.arguments[entry.name_arg || 0]);
      if (name) publishes.push({ name, line: nodeLine(node), via: `publisher:${node.callee.name}` });
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

function collectPublisherHelperCalls(ast, activePublisherNames = PUBLISHER_HELPER_NAMES) {
  const calls = [];
  walkAst(ast, (node) => {
    if (
      node.type !== 'CallExpression'
      || !node.callee
      || node.callee.type !== 'Identifier'
      || !activePublisherNames.has(node.callee.name)
    ) {
      return;
    }
    const helper = node.callee.name;
    const entry = PUBLISHER_HELPER_REGISTRY[helper];
    const name = literalStringValue(node.arguments[entry.name_arg || 0]);
    calls.push({
      helper,
      line: nodeLine(node),
      name,
      name_resolution: name ? 'literal' : 'dynamic_or_non_literal',
    });
  });
  return calls.sort((left, right) => (left.line || 0) - (right.line || 0) || left.helper.localeCompare(right.helper));
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

// Publish-side completeness check (symmetric to resolver discovery): a computed
// browser-global write with a non-literal key, e.g. `SOME_GLOBAL[name] = …`,
// publishes under a name the static collector cannot read. Such a write must
// live inside a registered PUBLISHER_HELPER_REGISTRY helper (whose string-literal
// call sites are recorded as publishes); otherwise it is an untracked publisher.
function collectComputedPublisherWrites(ast) {
  const aliasNames = collectGlobalAliasNames(ast);
  const parentOf = new Map();
  walkAst(ast, (node, parent) => {
    if (parent) parentOf.set(node, parent);
  });
  const untracked = [];
  const discovered = new Set();
  walkAst(ast, (node) => {
    if (node.type !== 'AssignmentExpression') return;
    const left = node.left;
    if (
      !left || left.type !== 'MemberExpression' || !left.computed
      || !left.object || left.object.type !== 'Identifier'
      || !isGlobalAliasIdentifier(left.object.name, aliasNames)
    ) {
      return;
    }
    // Bridge handler stores are filled by registration writes (`store[name] = …`),
    // validated by the bridge-dispatch reconciliation rather than this publish check.
    if (BRIDGE_HANDLER_STORES.has(left.object.name)) return;
    if (left.property && left.property.type === 'Literal') return; // literal key is a normal publish
    let cursor = node;
    let enclosing = '';
    while (cursor) {
      const parent = parentOf.get(cursor);
      if (!parent) break;
      if (parent.type === 'FunctionDeclaration' && parent.id && parent.id.type === 'Identifier') {
        enclosing = parent.id.name;
        break;
      }
      if (
        parent.type === 'VariableDeclarator' && parent.id && parent.id.type === 'Identifier'
        && parent.init === cursor
      ) {
        enclosing = parent.id.name;
        break;
      }
      cursor = parent;
    }
    if (PUBLISHER_HELPER_NAMES.has(enclosing)) {
      discovered.add(enclosing);
    } else {
      untracked.push({ object: left.object.name, line: nodeLine(node), enclosing: enclosing || '<module-scope>' });
    }
  });
  return {
    discovered: Array.from(discovered).sort(),
    untracked,
  };
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
  const importBindings = collectImportSourceNames(ast);
  const computedPublisherWrites = collectComputedPublisherWrites(ast);
  const activePublisherNames = new Set(computedPublisherWrites.discovered);
  return {
    source,
    file: relative(ROOT, file),
    import_source_names: Array.from(new Set(Array.from(importBindings.values())
      .map((binding) => binding.imported)
      .filter((name) => name && name !== 'default' && name !== '*'))).sort(),
    bridge_handler_declarations: collectBridgeHandlerDeclarations(ast),
    bridge_handler_registrations: collectBridgeHandlerRegistrations(ast, importBindings),
    top_level_definitions: topLevelDefinitions,
    window_publishes: collectWindowPublishes(ast, activePublisherNames),
    window_reads: collectWindowReads(ast),
    publisher_helper_calls: collectPublisherHelperCalls(ast, activePublisherNames),
    resolver_helper_calls: collectResolverHelperCalls(ast),
    resolver_helpers_discovered: discoverResolverHelpers(ast),
    computed_publisher_writes: computedPublisherWrites,
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
  if (BRIDGE_INTERNAL_NAME_PATTERN.test(publish.name)) {
    return { ...publish, purpose: 'bridge_internal' };
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

function countResolverCallsByClass(modules) {
  const counts = {};
  for (const module of modules) {
    for (const call of module.resolver_helper_calls || []) {
      const key = call.class || 'unclassified';
      counts[key] = (counts[key] || 0) + 1;
    }
  }
  return Object.fromEntries(Object.entries(counts).sort(([left], [right]) => left.localeCompare(right)));
}

function countResolverCallsByResolution(modules) {
  const counts = {};
  for (const module of modules) {
    for (const call of module.resolver_helper_calls || []) {
      const key = call.name_resolution || 'unknown';
      counts[key] = (counts[key] || 0) + 1;
      if (call.fallback) {
        const fallbackKey = `fallback:${call.fallback.status || 'unknown'}`;
        counts[fallbackKey] = (counts[fallbackKey] || 0) + 1;
      }
    }
  }
  return Object.fromEntries(Object.entries(counts).sort(([left], [right]) => left.localeCompare(right)));
}

function resolveResolverHelperCalls(module, publishMap, allowlist) {
  const importSourceNames = new Set(module.import_source_names || []);
  return (module.resolver_helper_calls || []).map((call) => {
    if (call.name_resolution !== 'literal') {
      return { ...call, resolution: 'dynamic_or_non_literal' };
    }
    if (call.class === 'bridge_dispatch') {
      return { ...call, resolution: 'bridge_dispatch_report_only' };
    }
    if (call.guard && String(call.guard.status || '').startsWith('guarded_by_resolved_')) {
      return { ...call, resolution: 'guarded_compatibility_fallback' };
    }
    if (
      call.class === 'import_first'
      && ['imported_binding', 'local_binding'].includes(call.fallback?.status)
    ) {
      return { ...call, resolution: `fallback_${call.fallback.status}` };
    }
    const providers = publishMap.has(call.name)
      ? Array.from(publishMap.get(call.name)).sort()
      : [];
    const allowed = findAllowlistEntryForRead(allowlist, call.name, module.source, providers);
    if (allowed) {
      return {
        ...call,
        resolution: 'allowlisted_global',
        purpose: allowed.purpose,
        providers,
      };
    }
    if (providers.length) {
      return { ...call, resolution: 'global_publish', providers };
    }
    if (importSourceNames.has(call.name)) {
      return { ...call, resolution: 'same_file_import_source' };
    }
    return { ...call, resolution: 'unresolved_report_only' };
  });
}

function countResolverCallsByFinalResolution(modules) {
  const counts = {};
  for (const module of modules) {
    for (const call of module.resolver_helper_calls || []) {
      const key = call.resolution || 'unknown';
      counts[key] = (counts[key] || 0) + 1;
    }
  }
  return Object.fromEntries(Object.entries(counts).sort(([left], [right]) => left.localeCompare(right)));
}

function bridgeKeysByBridge(entries) {
  const byBridge = new Map();
  for (const entry of entries) {
    if (!entry.bridge || !entry.key || entry.dynamic) continue;
    if (!byBridge.has(entry.bridge)) byBridge.set(entry.bridge, new Set());
    byBridge.get(entry.bridge).add(entry.key);
  }
  return byBridge;
}

function bridgeDynamicCountByBridge(entries) {
  const counts = {};
  for (const entry of entries) {
    if (!entry.bridge || !entry.dynamic) continue;
    counts[entry.bridge] = (counts[entry.bridge] || 0) + 1;
  }
  return Object.fromEntries(Object.entries(counts).sort(([left], [right]) => left.localeCompare(right)));
}

function bridgeDispatchEntries(modules) {
  return modules.flatMap((module) => (module.resolver_helper_calls || [])
    .filter((call) => call.class === 'bridge_dispatch' && call.name_resolution === 'literal')
    .map((call) => ({
      bridge: BRIDGE_DISPATCH_REGISTRY[call.helper]?.bridge || call.helper,
      helper: call.helper,
      key: call.name,
      line: call.line,
      source: module.source,
    })));
}

function bridgeKeyRecords(modules, key) {
  return modules.flatMap((module) => (module[key] || []).map((entry) => ({
    ...entry,
    source: module.source,
  })));
}

function formatBridgeKeyIssue(issue) {
  const line = issue.line || '?';
  return `${issue.bridge}.${issue.key} via ${issue.source}:${line}`;
}

function summarizeBridgeDispatch(modules) {
  const declarations = bridgeKeyRecords(modules, 'bridge_handler_declarations');
  const registrations = bridgeKeyRecords(modules, 'bridge_handler_registrations');
  const dispatches = bridgeDispatchEntries(modules);
  const declaredByBridge = bridgeKeysByBridge(declarations);
  const registeredByBridge = bridgeKeysByBridge(registrations);
  const dispatchedByBridge = bridgeKeysByBridge(dispatches);
  const bridgeNames = Array.from(new Set([
    ...Object.values(BRIDGE_DISPATCH_REGISTRY).map((entry) => entry.bridge),
    ...Array.from(declaredByBridge.keys()),
    ...Array.from(registeredByBridge.keys()),
    ...Array.from(dispatchedByBridge.keys()),
  ])).sort();
  const byBridge = {};
  const dispatched_missing_declarations = [];
  const dispatched_missing_registrations = [];
  const declared_not_dispatched = [];
  const registered_not_declared = [];
  for (const bridge of bridgeNames) {
    const declared = declaredByBridge.get(bridge) || new Set();
    const registered = registeredByBridge.get(bridge) || new Set();
    const dispatched = dispatchedByBridge.get(bridge) || new Set();
    const declaredKeys = Array.from(declared).sort();
    const registeredKeys = Array.from(registered).sort();
    const dispatchedKeys = Array.from(dispatched).sort();
    byBridge[bridge] = {
      declared_count: declaredKeys.length,
      registered_count: registeredKeys.length,
      dispatched_count: dispatchedKeys.length,
      declared_keys: declaredKeys,
      registered_keys: registeredKeys,
      dispatched_keys: dispatchedKeys,
    };
    for (const item of dispatches.filter((entry) => entry.bridge === bridge && !declared.has(entry.key))) {
      dispatched_missing_declarations.push(item);
    }
    for (const item of dispatches.filter((entry) => entry.bridge === bridge && !registered.has(entry.key))) {
      dispatched_missing_registrations.push(item);
    }
    for (const key of declaredKeys.filter((entry) => !dispatched.has(entry))) {
      declared_not_dispatched.push({ bridge, key });
    }
    for (const item of registrations.filter((entry) => (
      entry.bridge === bridge && entry.key && !entry.dynamic && !declared.has(entry.key)
    ))) {
      registered_not_declared.push(item);
    }
  }
  return {
    by_bridge: byBridge,
    declaration_count: declarations.filter((entry) => !entry.dynamic).length,
    registration_count: registrations.filter((entry) => !entry.dynamic).length,
    dispatch_count: dispatches.length,
    dynamic_declaration_counts: bridgeDynamicCountByBridge(declarations),
    dynamic_registration_counts: bridgeDynamicCountByBridge(registrations),
    dispatched_missing_declarations,
    dispatched_missing_declaration_count: dispatched_missing_declarations.length,
    dispatched_missing_registrations,
    dispatched_missing_registration_count: dispatched_missing_registrations.length,
    declared_not_dispatched,
    declared_not_dispatched_count: declared_not_dispatched.length,
    registered_not_declared,
    registered_not_declared_count: registered_not_declared.length,
  };
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

function unresolvedResolverHelperCalls(modules) {
  return modules
    .flatMap((module) => (module.resolver_helper_calls || [])
      .filter((call) => call.resolution === 'unresolved_report_only')
      .map((call) => ({ module, call })));
}

function formatResolverHelperCall({ module, call }) {
  const line = call.line || '?';
  const name = call.name_resolution === 'literal' ? `'${call.name}'` : call.name || '<dynamic>';
  return `${module.source}: ${call.helper}(${name}) line ${line}`;
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
      || (module.resolver_helper_calls || []).some((call) => (
        call.resolution === 'allowlisted_global'
        && allowlistEntryMatchesInventoryItem(entry, module.source, call)
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
  console.log(`Resolver helper calls: ${report.summary.resolver_helper_call_count}`);
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
  console.log('| Resolver final resolution | Count |');
  console.log('| --- | ---: |');
  for (const [resolution, count] of Object.entries(report.summary.resolver_helper_calls_by_final_resolution)) {
    console.log(`| ${resolution} | ${count} |`);
  }
  console.log('');
  console.log('| Bridge dispatch contract | Count |');
  console.log('| --- | ---: |');
  console.log(`| declared handler keys | ${report.summary.bridge_dispatch.declaration_count} |`);
  console.log(`| registered handler keys | ${report.summary.bridge_dispatch.registration_count} |`);
  console.log(`| dispatched handler keys | ${report.summary.bridge_dispatch.dispatch_count} |`);
  console.log(`| dispatched but not declared | ${report.summary.bridge_dispatch.dispatched_missing_declaration_count} |`);
  console.log(`| dispatched but not registered | ${report.summary.bridge_dispatch.dispatched_missing_registration_count} |`);
  console.log(`| declared but not dispatched | ${report.summary.bridge_dispatch.declared_not_dispatched_count} |`);
  console.log(`| registered but not declared | ${report.summary.bridge_dispatch.registered_not_declared_count} |`);
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
  module.resolver_helper_calls = resolveResolverHelperCalls(module, publishMap, allowlist);
  delete module.import_source_names;
  delete module.bare_reads;
  delete module.window_reads;
  module.classification = classifyModule(module);
}

const classifications = {};
for (const module of modules) {
  classifications[module.classification] = (classifications[module.classification] || 0) + 1;
}
const bridgeDispatchSummary = summarizeBridgeDispatch(modules);

function reconcileResolverDiscovery(allModules) {
  const discovered = new Set();
  for (const module of allModules) {
    for (const name of module.resolver_helpers_discovered || []) discovered.add(name);
  }
  return {
    discovered_count: discovered.size,
    discovered: Array.from(discovered).sort(),
    uncovered: Array.from(discovered)
      .filter((name) => !RESOLVER_HELPER_NAMES.has(name) && !RESOLVER_HELPER_IGNORE_NAMES.has(name))
      .sort(),
    dead_registry_entries: Array.from(RESOLVER_HELPER_NAMES)
      .filter((name) => !discovered.has(name))
      .sort(),
    dead_ignore_entries: Array.from(RESOLVER_HELPER_IGNORE_NAMES)
      .filter((name) => !discovered.has(name))
      .sort(),
  };
}

function reconcilePublisherDiscovery(allModules) {
  const discovered = new Set();
  const dynamicOrNonLiteralCalls = [];
  for (const module of allModules) {
    const writes = module.computed_publisher_writes || {};
    for (const name of writes.discovered || []) discovered.add(name);
    for (const call of module.publisher_helper_calls || []) {
      if (call.name_resolution === 'dynamic_or_non_literal') {
        dynamicOrNonLiteralCalls.push({ ...call, source: module.source });
      }
    }
  }
  return {
    registered_count: PUBLISHER_HELPER_NAMES.size,
    discovered_count: discovered.size,
    discovered: Array.from(discovered).sort(),
    dead_registry_entries: Array.from(PUBLISHER_HELPER_NAMES)
      .filter((name) => !discovered.has(name))
      .sort(),
    dynamic_or_non_literal_call_count: dynamicOrNonLiteralCalls.length,
    dynamic_or_non_literal_calls: dynamicOrNonLiteralCalls,
  };
}

const resolverDiscovery = reconcileResolverDiscovery(modules);
const publisherDiscovery = reconcilePublisherDiscovery(modules);
const untrackedComputedPublishers = modules.flatMap((module) => (
  ((module.computed_publisher_writes || {}).untracked || []).map((entry) => ({ ...entry, source: module.source }))
));
for (const module of modules) delete module.computed_publisher_writes;

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
    resolver_helper_call_count: modules.reduce((total, module) => total + module.resolver_helper_calls.length, 0),
    resolver_helper_calls_by_class: countResolverCallsByClass(modules),
    resolver_helper_calls_by_final_resolution: countResolverCallsByFinalResolution(modules),
    resolver_helper_discovery: resolverDiscovery,
    publisher_helper_discovery: publisherDiscovery,
    untracked_computed_publisher_count: untrackedComputedPublishers.length,
    resolver_helper_calls_by_resolution: countResolverCallsByResolution(modules),
    bridge_dispatch: bridgeDispatchSummary,
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
  const unresolvedResolverCalls = unresolvedResolverHelperCalls(modules);
  if (unresolvedResolverCalls.length) {
    console.error(
      'Frontend inventory found unresolved ESM resolver helper calls:\n'
      + unresolvedResolverCalls.map((entry) => `  ${formatResolverHelperCall(entry)}`).join('\n'),
    );
    process.exit(1);
  }
}

if (checkOnly) {
  const issues = [];
  if (resolverDiscovery.uncovered.length) {
    issues.push(
      'Resolver-shaped helpers missing a RESOLVER_HELPER_REGISTRY classification (add a registry entry or an audited RESOLVER_HELPER_IGNORE entry):\n'
      + resolverDiscovery.uncovered.map((name) => `  ${name}`).join('\n'),
    );
  }
  if (resolverDiscovery.dead_registry_entries.length) {
    issues.push(
      'RESOLVER_HELPER_REGISTRY entries that structural discovery no longer finds (remove the dead classification):\n'
      + resolverDiscovery.dead_registry_entries.map((name) => `  ${name}`).join('\n'),
    );
  }
  if (resolverDiscovery.dead_ignore_entries.length) {
    issues.push(
      'RESOLVER_HELPER_IGNORE entries that structural discovery no longer finds (remove the dead ignore):\n'
      + resolverDiscovery.dead_ignore_entries.map((name) => `  ${name}`).join('\n'),
    );
  }
  if (issues.length) {
    console.error(`Frontend inventory found resolver-helper registry drift:\n${issues.join('\n')}`);
    process.exit(1);
  }
}

if (checkOnly && untrackedComputedPublishers.length) {
  console.error(
    'Frontend inventory found computed browser-global publishers not registered in PUBLISHER_HELPER_REGISTRY '
    + '(their published names are invisible to the read-side check):\n'
    + untrackedComputedPublishers
      .map((entry) => `  ${entry.source}: ${entry.object}[…] = … in ${entry.enclosing} (line ${entry.line})`)
      .join('\n'),
  );
  process.exit(1);
}

if (checkOnly) {
  const issues = [];
  if (publisherDiscovery.dead_registry_entries.length) {
    issues.push(
      'PUBLISHER_HELPER_REGISTRY entries that no longer wrap a computed browser-global write (remove the dead classification):\n'
      + publisherDiscovery.dead_registry_entries.map((name) => `  ${name}`).join('\n'),
    );
  }
  if (publisherDiscovery.dynamic_or_non_literal_calls.length) {
    issues.push(
      'Registered publisher helper calls whose published name is dynamic or non-literal (the publish is invisible to static consumers):\n'
      + publisherDiscovery.dynamic_or_non_literal_calls
        .map((entry) => `  ${entry.source}: ${entry.helper}(…) line ${entry.line}`)
        .join('\n'),
    );
  }
  if (issues.length) {
    console.error(`Frontend inventory found publisher-helper registry drift:\n${issues.join('\n')}`);
    process.exit(1);
  }
}

if (checkOnly) {
  const bridgeIssues = [];
  if (bridgeDispatchSummary.dispatched_missing_declarations.length) {
    bridgeIssues.push(
      'Dispatched bridge keys missing declared handler slots:\n'
      + bridgeDispatchSummary.dispatched_missing_declarations
        .map((entry) => `  ${formatBridgeKeyIssue(entry)}`)
        .join('\n'),
    );
  }
  if (bridgeDispatchSummary.dispatched_missing_registrations.length) {
    bridgeIssues.push(
      'Dispatched bridge keys missing handler registration:\n'
      + bridgeDispatchSummary.dispatched_missing_registrations
        .map((entry) => `  ${formatBridgeKeyIssue(entry)}`)
        .join('\n'),
    );
  }
  if (bridgeDispatchSummary.registered_not_declared.length) {
    bridgeIssues.push(
      'Registered bridge keys missing declared handler slots:\n'
      + bridgeDispatchSummary.registered_not_declared
        .map((entry) => `  ${formatBridgeKeyIssue(entry)}`)
        .join('\n'),
    );
  }
  if (bridgeIssues.length) {
    console.error(`Frontend inventory found invalid bridge-dispatch contracts:\n${bridgeIssues.join('\n')}`);
    process.exit(1);
  }
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
  console.log(
    'Frontend inventory check passed: all app bare reads, ESM resolver helper calls, '
    + 'and bridge-dispatch contracts have resolution paths, and the browser-boundary allowlist is current.',
  );
} else {
  printMarkdown(report);
}
