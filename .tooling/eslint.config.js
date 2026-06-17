import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { Linter } from 'eslint'

const frontendModuleFiles = [
  'app/static/js/**/*.js',
]

const __dirname = dirname(fileURLToPath(import.meta.url))
const ROOT = resolve(__dirname, '..')

const browserGlobals = {
  AbortController: 'readonly',
  Blob: 'readonly',
  CSS: 'readonly',
  CustomEvent: 'readonly',
  DOMParser: 'readonly',
  DataTransfer: 'readonly',
  Element: 'readonly',
  Event: 'readonly',
  File: 'readonly',
  FileReader: 'readonly',
  FormData: 'readonly',
  Headers: 'readonly',
  HTMLElement: 'readonly',
  HTMLInputElement: 'readonly',
  HTMLSelectElement: 'readonly',
  HTMLTextAreaElement: 'readonly',
  IntersectionObserver: 'readonly',
  KeyboardEvent: 'readonly',
  MouseEvent: 'readonly',
  MutationObserver: 'readonly',
  Node: 'readonly',
  NodeFilter: 'readonly',
  Notification: 'readonly',
  PointerEvent: 'readonly',
  ResizeObserver: 'readonly',
  Response: 'readonly',
  TextDecoder: 'readonly',
  TextEncoder: 'readonly',
  URL: 'readonly',
  URLSearchParams: 'readonly',
  WebSocket: 'readonly',
  alert: 'readonly',
  atob: 'readonly',
  btoa: 'readonly',
  cancelAnimationFrame: 'readonly',
  cancelIdleCallback: 'readonly',
  clearInterval: 'readonly',
  clearTimeout: 'readonly',
  console: 'readonly',
  crypto: 'readonly',
  document: 'readonly',
  fetch: 'readonly',
  getComputedStyle: 'readonly',
  history: 'readonly',
  localStorage: 'readonly',
  location: 'readonly',
  navigator: 'readonly',
  performance: 'readonly',
  queueMicrotask: 'readonly',
  requestAnimationFrame: 'readonly',
  requestIdleCallback: 'readonly',
  sessionStorage: 'readonly',
  setInterval: 'readonly',
  setTimeout: 'readonly',
  window: 'readonly',
  AnsiUp: 'readonly',
  __darklabExtractGlobals: 'readonly',
}

function collectFiles(dir) {
  if (!existsSync(dir)) return []
  const files = []
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = resolve(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name === 'vendor') continue
      files.push(...collectFiles(full))
    } else if (entry.isFile() && entry.name.endsWith('.js')) {
      files.push(full)
    }
  }
  return files
}

function collectObjectLiteralKeys(source, callName) {
  const names = []
  const start = source.indexOf(`${callName}({`)
  if (start === -1) return names
  let depth = 0
  let bodyStart = -1
  for (let index = start; index < source.length; index += 1) {
    const char = source[index]
    if (char === '{') {
      depth += 1
      if (depth === 1) bodyStart = index + 1
    } else if (char === '}') {
      depth -= 1
      if (depth === 0 && bodyStart !== -1) {
        const body = source.slice(bodyStart, index)
        for (const match of body.matchAll(/^\s*([A-Za-z_$][\w$]*)\s*(?:,|:)/gm)) {
          names.push(match[1])
        }
        break
      }
    }
  }
  return names
}

function collectStringArrayValues(source, name) {
  const values = []
  const match = source.match(new RegExp(`const\\s+${name}\\s*=\\s*\\[([\\s\\S]*?)\\]`))
  if (!match) return values
  for (const item of match[1].matchAll(/['"]([A-Za-z_$][\w$]*)['"]/g)) {
    values.push(item[1])
  }
  return values
}

function memberPropertyName(member) {
  if (!member || member.type !== 'MemberExpression') return ''
  if (!member.computed && member.property && member.property.type === 'Identifier') return member.property.name
  if (member.computed && member.property && member.property.type === 'Literal') {
    return typeof member.property.value === 'string' ? member.property.value : ''
  }
  return ''
}

function isWindowMember(member) {
  return !!(
    member
    && member.type === 'MemberExpression'
    && member.object
    && member.object.type === 'Identifier'
    && ['global', 'globalThis', 'window'].includes(member.object.name)
  )
}

function walkAst(node, visitor) {
  if (!node || typeof node.type !== 'string') return
  visitor(node)
  for (const [key, value] of Object.entries(node)) {
    if (['parent', 'loc', 'range', 'tokens', 'comments'].includes(key)) continue
    if (Array.isArray(value)) {
      value.forEach(child => walkAst(child, visitor))
    } else if (value && typeof value.type === 'string') {
      walkAst(value, visitor)
    }
  }
}

function collectTopLevelAndPublishedNames(source, file) {
  const names = []
  let ast = null
  let scopeManager = null
  const linter = new Linter({ configType: 'flat' })
  const captureRule = {
    create(context) {
      return {
        Program(node) {
          ast = node
          scopeManager = context.sourceCode.scopeManager
        },
      }
    },
  }
  linter.verify(
    source,
    {
      languageOptions: {
        ecmaVersion: 'latest',
        sourceType: 'module',
      },
      plugins: {
        configInventory: {
          rules: {
            capture: captureRule,
          },
        },
      },
      rules: {
        'configInventory/capture': 'error',
      },
    },
    { filename: file },
  )
  const topScopes = (scopeManager && scopeManager.scopes || [])
    .filter(scope => scope.type === 'global' || scope.type === 'module')
  topScopes.forEach(scope => {
    scope.variables.forEach(variable => {
      if (variable.defs && variable.defs.length) names.push(variable.name)
    })
  })
  walkAst(ast, (node) => {
    if (node.type === 'AssignmentExpression' && isWindowMember(node.left)) {
      const name = memberPropertyName(node.left)
      if (name) names.push(name)
    }
    if (
      node.type === 'CallExpression'
      && node.callee
      && node.callee.type === 'MemberExpression'
      && node.callee.object
      && node.callee.object.type === 'Identifier'
      && node.callee.object.name === 'Object'
      && memberPropertyName(node.callee) === 'defineProperty'
      && node.arguments[0]
      && node.arguments[0].type === 'Identifier'
      && ['global', 'globalThis', 'window'].includes(node.arguments[0].name)
      && node.arguments[1]
      && node.arguments[1].type === 'Literal'
      && typeof node.arguments[1].value === 'string'
    ) {
      names.push(node.arguments[1].value)
    }
    if (
      node.type === 'CallExpression'
      && node.callee
      && node.callee.type === 'MemberExpression'
      && node.callee.object
      && node.callee.object.type === 'Identifier'
      && node.callee.object.name === 'Object'
      && memberPropertyName(node.callee) === 'assign'
      && node.arguments[0]
      && node.arguments[0].type === 'Identifier'
      && ['global', 'globalThis', 'window'].includes(node.arguments[0].name)
      && node.arguments[1]
      && node.arguments[1].type === 'ObjectExpression'
    ) {
      node.arguments[1].properties.forEach((property) => {
        if (property.type !== 'Property') return
        if (property.key.type === 'Identifier') names.push(property.key.name)
        else if (property.key.type === 'Literal' && typeof property.key.value === 'string') names.push(property.key.value)
      })
    }
  })
  return names
}

function collectAppGlobals() {
  const names = new Set()
  for (const file of collectFiles(resolve(ROOT, 'app/static/js'))) {
    const source = readFileSync(file, 'utf8')
    collectTopLevelAndPublishedNames(source, file).forEach(name => names.add(name))
    collectObjectLiteralKeys(source, '_publishDomRefs').forEach(name => names.add(name))
    collectStringArrayValues(source, 'bindings').forEach(name => names.add(name))
  }
  return Object.fromEntries(Array.from(names).sort().map(name => [name, 'readonly']))
}

const appGlobals = collectAppGlobals()

export default [
  {
    ignores: [
      'app/static/build/**',
      'app/static/js/vendor/**',
    ],
  },
  {
    files: frontendModuleFiles,
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        ...browserGlobals,
        ...appGlobals,
      },
    },
    rules: {
      'no-undef': 'error',
    },
  },
  {
    files: ['playwright*.js', '.tooling/playwright*.js'],
    rules: {
      indent: ['error', 2],
      quotes: ['error', 'single', { avoidEscape: true }],
      semi: ['error', 'never'],
    },
  },
]
