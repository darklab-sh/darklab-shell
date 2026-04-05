/**
 * Extract named pure functions from a browser JS source file for unit testing.
 *
 * Strategy: wrap the file contents in `new Function(...)` so that
 * DOM-referencing functions are defined but never called.  Only the
 * explicitly requested names are returned.  Functions that close over
 * `localStorage` receive a self-contained MemoryStorage instance so that
 * tests stay isolated from any jsdom quirks and don't need a real browser.
 *
 * Usage:
 *   import { fromScript } from './helpers/extract.js'
 *   const { escapeHtml } = fromScript('app/static/js/utils.js', 'escapeHtml')
 *
 *   // For functions that use localStorage, access the store via _storage:
 *   const { _getStarred, _saveStarred, _storage } =
 *     fromScript('app/static/js/history.js', '_getStarred', '_saveStarred')
 *   _storage.setItem('starred', JSON.stringify(['cmd1']))
 */

import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../../../')

/** Minimal but complete in-memory Storage implementation. */
export class MemoryStorage {
  constructor() { this._data = Object.create(null) }
  getItem(k) { return Object.prototype.hasOwnProperty.call(this._data, k) ? this._data[k] : null }
  setItem(k, v) { this._data[k] = String(v) }
  removeItem(k) { delete this._data[k] }
  clear() { this._data = Object.create(null) }
  get length() { return Object.keys(this._data).length }
  key(n) { return Object.keys(this._data)[n] ?? null }
}

/**
 * Load a browser JS file and return the requested named functions together with
 * the MemoryStorage instance they operate on.
 *
 * Returned object: { [name]: fn, ..., _storage: MemoryStorage }
 */
export function fromScript(relPath, ...names) {
  const src = readFileSync(resolve(REPO_ROOT, relPath), 'utf8')
  const returnExpr = `\nreturn { ${names.join(', ')} };`
  const storage = new MemoryStorage()
  // Pass a minimal APP_CONFIG stub so references inside function bodies don't
  // throw a ReferenceError if those functions are ever called in the tests.
  const fns = new Function('localStorage', 'APP_CONFIG', src + returnExpr)(
    storage,
    { recent_commands_limit: 20 },
  )
  return { ...fns, _storage: storage }
}

/**
 * Load a browser JS file into a custom execution context and return the
 * requested named bindings.
 */
export function fromDomScript(relPath, globals, ...names) {
  const src = readFileSync(resolve(REPO_ROOT, relPath), 'utf8')
  const globalNames = Object.keys(globals)
  const globalValues = Object.values(globals)
  const returnExpr = `\nreturn { ${names.join(', ')} };`
  const fns = new Function(...globalNames, src + returnExpr)(...globalValues)
  return fns
}

/**
 * Load one or more browser JS files into a custom execution context and return
 * a custom object literal expression.
 */
export function fromDomScripts(relPaths, globals, returnExpr) {
  const src = relPaths
    .map(relPath => readFileSync(resolve(REPO_ROOT, relPath), 'utf8'))
    .join('\n')
  const globalNames = Object.keys(globals)
  const globalValues = Object.values(globals)
  return new Function(...globalNames, `${src}\nreturn ${returnExpr};`)(...globalValues)
}
