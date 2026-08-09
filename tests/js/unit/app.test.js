// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { readFileSync, readdirSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'
import { load as loadYaml } from 'js-yaml'
import { loadAppFns } from './helpers/app_harness.js'
import { fromDomScripts } from './helpers/extract.js'
import {
  applySyntheticPostFilterLines,
  isSyntheticJqCommand,
  parseSyntheticPostFilterCommand,
} from '../../../app/static/js/core/runner_core.js'
import {
  createCommandExecution,
} from '../../../app/static/js/features/runner/command_lifecycle.js'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../..')
const APP_SRC = readFileSync(resolve(REPO_ROOT, 'app/static/js/app.js'), 'utf8')
const THEME_META_KEYS = new Set(['label', 'group', 'sort'])
const THEME_BASE_KEYS = new Set([
  'bg',
  'surface',
  'border',
  'border_bright',
  'border_soft',
  'text',
  'muted',
  'green',
  'green_dim',
  'green_glow',
  'amber',
  'red',
  'blue',
  'terminal_font_size',
  'terminal_line_height',
])

function createBrowserCommandExecution(command, tabId = 'tab-1') {
  return createCommandExecution({
    command,
    safeCommand: command,
    tabId,
    persistence: 'client',
    recordRecent: false,
  })
}

function commandExecutionText(execution) {
  return execution.state.lines.map(line => line.text).join('\n')
}

function loadSchedulesModalTestFns({
  apiFetch = vi.fn(async () => ({ ok: true, json: async () => ({}) })),
  showConfirm = vi.fn(async () => null),
  showToast = vi.fn(),
  openHistoryRunDetails = vi.fn(),
  fetchAndRenderHistoryComparison = vi.fn(),
} = {}) {
  document.body.innerHTML = `
    <div id="schedules-overlay" class="u-hidden">
      <div id="schedules-modal" tabindex="-1">
        <button class="schedules-close" type="button"></button>
        <button id="schedules-new-btn" type="button"></button>
        <button id="schedules-refresh-btn" type="button"></button>
        <span id="schedules-count"></span>
        <div id="schedules-list"></div>
        <div id="schedules-detail"></div>
      </div>
    </div>
  `
  const bindDismissible = vi.fn()
  const fns = fromDomScripts(
    ['app/static/js/features/schedules/schedules_modal.js'],
    {
      document,
      window,
      apiFetch,
      showConfirm,
      showToast,
      openHistoryRunDetails,
      fetchAndRenderHistoryComparison,
      _closeMajorOverlays: vi.fn(),
      bindDismissible,
      refocusComposerAfterAction: vi.fn(),
    },
    '({ _bindSchedulesModal, _deleteSelectedSchedule, refreshSchedulesModal, _newSchedule, openSchedulesModal, closeSchedulesModal })',
    `window.apiFetch = apiFetch;
     window.showConfirm = showConfirm;
     window.showToast = showToast;
     window.openHistoryRunDetails = openHistoryRunDetails;
     window.fetchAndRenderHistoryComparison = fetchAndRenderHistoryComparison;
     window._closeMajorOverlays = _closeMajorOverlays;
     window.bindDismissible = bindDismissible;
     window.refocusComposerAfterAction = refocusComposerAfterAction;`,
  )
  return {
    ...fns,
    apiFetch,
    bindDismissible,
    showConfirm,
    showToast,
    openHistoryRunDetails,
    fetchAndRenderHistoryComparison,
    list: document.getElementById('schedules-list'),
    detail: document.getElementById('schedules-detail'),
  }
}

function loadWatchersModalTestFns({
  apiFetch = vi.fn(async () => ({ ok: true, json: async () => ({}) })),
  showConfirm = vi.fn(async () => null),
  showToast = vi.fn(),
  openHistoryRunDetails = vi.fn(),
  fetchAndRenderHistoryComparison = vi.fn(),
} = {}) {
  document.body.innerHTML = `
    <div id="watchers-overlay" class="u-hidden">
      <div id="watchers-modal" tabindex="-1">
        <button class="watchers-close" type="button"></button>
        <button id="watchers-new-btn" type="button"></button>
        <button id="watchers-refresh-btn" type="button"></button>
        <span id="watchers-count"></span>
        <div id="watchers-list"></div>
        <div id="watchers-detail"></div>
      </div>
    </div>
  `
  const bindDismissible = vi.fn()
  const compareMetricCell = (label, value, tone = '') => {
    const cell = document.createElement('div')
    cell.className = `history-compare-metric${tone ? ` ${tone}` : ''}`
    cell.textContent = `${label}${value}`
    return cell
  }
  const fns = fromDomScripts(
    ['app/static/js/features/watchers/watchers_modal.js'],
    {
      document,
      window,
      apiFetch,
      showConfirm,
      showToast,
      openHistoryRunDetails,
      fetchAndRenderHistoryComparison,
      _compareMetricCell: compareMetricCell,
      _closeMajorOverlays: vi.fn(),
      bindDismissible,
      refocusComposerAfterAction: vi.fn(),
    },
    '({ _bindWatchersModal, _deleteSelectedWatcher, refreshWatchersModal, _newWatcher, openWatchersModal, closeWatchersModal })',
    `window.apiFetch = apiFetch;
     window.showConfirm = showConfirm;
     window.showToast = showToast;
     window.openHistoryRunDetails = openHistoryRunDetails;
     window.fetchAndRenderHistoryComparison = fetchAndRenderHistoryComparison;
     window._compareMetricCell = _compareMetricCell;
     window._closeMajorOverlays = _closeMajorOverlays;
     window.bindDismissible = bindDismissible;
     window.refocusComposerAfterAction = refocusComposerAfterAction;`,
  )
  return {
    ...fns,
    apiFetch,
    bindDismissible,
    showConfirm,
    showToast,
    openHistoryRunDetails,
    fetchAndRenderHistoryComparison,
    list: document.getElementById('watchers-list'),
    detail: document.getElementById('watchers-detail'),
  }
}

function builtInAutocompleteBase() {
  const hint = (value, description = '', insertValue = undefined) => {
    const item = { value, description }
    if (insertValue !== undefined) item.insertValue = insertValue
    return item
  }
  const emptyBuiltIn = description => ({
    description,
    flags: [],
    expects_value: [],
    arg_hints: { __positional__: [] },
    sequence_arg_hints: {},
    close_after: {},
    examples: [],
    subcommands: {},
    argument_limit: null,
  })
  return {
    commands: {
      ...emptyBuiltIn('built-in: list built-in and allowed external commands'),
      flags: [hint('--built-in', 'Show only built-in shell commands'), hint('--external', 'Show only allowed external commands')],
      expects_value: ['info'],
      arg_hints: {
        info: [],
        __positional__: [hint('info', 'Show details for one supported command', 'info ')],
      },
    },
    config: {
      ...emptyBuiltIn('built-in: show or update user options'),
      expects_value: ['get', 'set'],
      arg_hints: {
        list: [],
        get: [],
        set: [],
        __positional__: [hint('list', 'Show all current user config'), hint('get', 'Show one user config value', 'get '), hint('set', 'Set one user config value', 'set ')],
      },
    },
    theme: {
      ...emptyBuiltIn('built-in: show or apply the active shell theme'),
      expects_value: ['set'],
      arg_hints: {
        list: [],
        current: [],
        set: [],
        __positional__: [hint('list', 'Show available themes'), hint('current', 'Show the active theme'), hint('set', 'Apply a theme', 'set ')],
      },
    },
    var: {
      ...emptyBuiltIn('built-in: set, list, or unset session command variables'),
      expects_value: ['set', 'unset'],
      close_after: { list: 0, set: 2, unset: 1 },
      arg_hints: {
        list: [],
        set: [],
        unset: [],
        __positional__: [hint('list', 'Show session variables'), hint('set', 'Set a session variable', 'set '), hint('unset', 'Remove a session variable', 'unset ')],
      },
    },
    runs: {
      ...emptyBuiltIn('built-in: show active runs; use -v for details or --json for automation'),
      flags: [hint('-v'), hint('--verbose'), hint('--json')],
    },
    jobs: {
      ...emptyBuiltIn('built-in: alias for runs'),
      flags: [hint('-v'), hint('--verbose'), hint('--json')],
    },
    'session-token': {
      ...emptyBuiltIn('built-in: show or manage persistent session tokens'),
      expects_value: ['set', 'revoke'],
      arg_hints: {
        generate: [],
        copy: [],
        clear: [],
        rotate: [],
        list: [],
        set: [hint('<token>', 'Paste a tok_... token or UUID from another device')],
        revoke: [hint('<token>', 'tok_ token to permanently invalidate on the server')],
        __positional__: [
          hint('generate', 'Generate a new session token and save it to this browser'),
          hint('set <token>', 'Activate an existing session token from another device', 'set '),
          hint('copy', 'Copy the active session token to the clipboard'),
          hint('clear', 'Confirm before removing the active session token'),
          hint('rotate', 'Generate a new token and migrate all history to it'),
          hint('list', 'Show the active session token and its creation date'),
          hint('revoke <token>', 'Permanently invalidate a tok_ token on this server', 'revoke '),
        ],
      },
    },
    workflow: {
      ...emptyBuiltIn('built-in: list, inspect, and run guided workflows'),
      expects_value: ['show', 'run'],
      arg_hints: {
        list: [],
        show: [],
        run: [],
        __positional__: [
          hint('list', 'List workflows'),
          hint('show', 'Show workflow steps', 'show '),
          hint('run', 'Run a workflow', 'run '),
        ],
      },
    },
    tour: {
      ...emptyBuiltIn('built-in: print the onboarding tour inside the terminal'),
      feature_required: 'tour',
      arg_hints: {
        help: [],
        __positional__: [hint('help', 'Show tour command usage')],
      },
    },
    file: {
      ...emptyBuiltIn('built-in: list, view, compare, create, edit, download, move, or remove session files'),
      feature_required: 'workspace',
      expects_value: ['show', 'diff', 'add', 'add-dir', 'edit', 'download', 'move', 'rm', 'delete', 'ls'],
      arg_hints: {
        list: [],
        ls: [],
        help: [],
        show: [],
        diff: [],
        add: [hint('<file>', 'New session file name')],
        'add-dir': [hint('<folder>', 'New session folder')],
        edit: [],
        download: [],
        move: [],
        rm: [],
        delete: [],
        __positional__: [
          hint('list <folder>', 'List current session files', 'list '),
          hint('ls <folder>', 'List current session files', 'ls '),
          hint('show <file>', 'Print a session file in the terminal', 'show '),
          hint('diff <source1> <source2>', 'Compare files or completed run output', 'diff '),
          hint('add <file>', 'Open the Files editor for a new session file', 'add '),
          hint('add-dir <folder>', 'Create a session folder', 'add-dir '),
          hint('edit <file>', 'Open the Files editor for an existing session file', 'edit '),
          hint('download <file>', 'Download a session file through the browser', 'download '),
          hint('move <source> <destination>', 'Move or rename a session file or folder', 'move '),
          hint('delete <file>', 'Remove a session file from this session', 'delete '),
          hint('help', 'Show file command usage'),
        ],
      },
    },
    cat: { ...emptyBuiltIn('built-in: show a session file'), feature_required: 'workspace', argument_limit: 1 },
    cd: { ...emptyBuiltIn('built-in: change the current workspace folder'), feature_required: 'workspace', argument_limit: 1 },
    diff: {
      ...emptyBuiltIn('built-in: compare session files or completed run output'),
      flags: [
        hint('--last'),
        hint('-q'),
        hint('--brief'),
        hint('-u'),
        hint('--unified'),
        hint('-y'),
        hint('--side-by-side'),
      ],
      argument_limit: 2,
    },
    grep: { ...emptyBuiltIn('built-in: filter a session file'), feature_required: 'workspace', argument_limit: 2 },
    head: { ...emptyBuiltIn('built-in: print the first lines of a session file'), feature_required: 'workspace', argument_limit: 1 },
    ll: { ...emptyBuiltIn('built-in: long-list session files'), feature_required: 'workspace', argument_limit: 1 },
    ls: { ...emptyBuiltIn('built-in: list session files'), feature_required: 'workspace', argument_limit: 1 },
    mkdir: { ...emptyBuiltIn('built-in: create a session folder'), feature_required: 'workspace', argument_limit: 1 },
    mv: { ...emptyBuiltIn('built-in: move or rename a session file or folder'), feature_required: 'workspace', argument_limit: 2 },
    rm: {
      ...emptyBuiltIn('built-in: remove a session file after confirmation'),
      feature_required: 'workspace',
      argument_limit: 1,
    },
    sort: { ...emptyBuiltIn('built-in: sort a session file'), feature_required: 'workspace', argument_limit: 1 },
    tail: { ...emptyBuiltIn('built-in: print the last lines of a session file'), feature_required: 'workspace', argument_limit: 1 },
    uniq: { ...emptyBuiltIn('built-in: collapse adjacent duplicate lines in a session file'), feature_required: 'workspace', argument_limit: 1 },
    wc: { ...emptyBuiltIn('built-in: count lines in a session file'), feature_required: 'workspace', argument_limit: 1 },
    man: { ...emptyBuiltIn('built-in: show a real or built-in manual page'), argument_limit: 1 },
    which: { ...emptyBuiltIn('built-in: locate a built-in command or allowed runtime command'), argument_limit: 1 },
    type: { ...emptyBuiltIn('built-in: describe whether a command is built-in, installed, or missing'), argument_limit: 1 },
    status: emptyBuiltIn('built-in: show the current session summary, limits, and backend health'),
    whoami: emptyBuiltIn('built-in: describe this shell and link to the project README'),
  }
}

function shippedThemeRegistry() {
  const themeDir = resolve(REPO_ROOT, 'app/conf/themes')
  const themes = readdirSync(themeDir)
    .filter(name => name.endsWith('.yaml') && !name.endsWith('.local.yaml'))
    .sort()
    .map(filename => {
      const raw = loadYaml(readFileSync(resolve(themeDir, filename), 'utf8')) || {}
      const name = filename.replace(/\.yaml$/, '')
      const vars = {}
      Object.entries(raw).forEach(([key, value]) => {
        if (THEME_META_KEYS.has(key) || key === 'color_scheme') return
        const cssKey = String(key).replaceAll('_', '-')
        const cssValue = String(value)
        if (THEME_BASE_KEYS.has(key)) vars[`--${cssKey}`] = cssValue
        vars[`--theme-${cssKey}`] = cssValue
      })
      return {
        name,
        filename,
        label: raw.label || name,
        group: raw.group || 'Other',
        sort: Number.isInteger(raw.sort) ? raw.sort : null,
        color_scheme: raw.color_scheme === 'light' ? 'only light' : 'only dark',
        source: 'variant',
        vars,
      }
    })
  return { current: themes[0], themes }
}

describe('app helpers', () => {
  it('keeps app function resolution import-first while APP_CONFIG remains global-backed', () => {
    expect(APP_SRC).toContain(`function _appFn(name, imported = null) {
  if (typeof imported === 'function') return imported;
  const fn = APP_GLOBAL && APP_GLOBAL[name];
  if (typeof fn === 'function') return fn;
  return null;
}`)
    expect(APP_SRC).toContain("const globalConfig = _appValue('APP_CONFIG');")
    expect(APP_SRC).toContain("const config = _appFn('getAppConfig', importedGetAppConfig)?.();")
  })

  it('selects JSON object fields and array values with the app-native jq pipe helper', () => {
    const fieldSpec = parseSyntheticPostFilterCommand('cat ffuf.json | jq -r .host')
    expect(fieldSpec.kind).toBe('jq')
    expect(isSyntheticJqCommand('cat ffuf.json | jq -r .host')).toBe(true)
    expect(applySyntheticPostFilterLines([{ text: '{"host":"example.test","port":443}' }], fieldSpec)).toEqual([
      { text: 'example.test', cls: '' },
    ])

    const identitySpec = parseSyntheticPostFilterCommand('cat ffuf.json | jq .')
    expect(applySyntheticPostFilterLines([
      { text: '{"host":"example.test","ports":[80,443]}' },
    ], identitySpec)).toEqual([
      { text: '{', cls: '' },
      { text: '  "host": "example.test",', cls: '' },
      { text: '  "ports": [', cls: '' },
      { text: '    80,', cls: '' },
      { text: '    443', cls: '' },
      { text: '  ]', cls: '' },
      { text: '}', cls: '' },
    ])

    const arraySpec = parseSyntheticPostFilterCommand('cat ffuf.json | jq -c .results[]')
    expect(applySyntheticPostFilterLines([
      { text: '{"results":[{"url":"https://example.test/"},{"url":"https://api.example.test/"}]}' },
    ], arraySpec)).toEqual([
      { text: '{"url":"https://example.test/"}', cls: '' },
      { text: '{"url":"https://api.example.test/"}', cls: '' },
    ])
  })

  it('filters JSONL rows by key existence, equality, and contains selectors', () => {
    const rows = [
      { text: '{"host":"one.test","status":"ok","title":"admin login"}' },
      { text: '{"host":"two.test","status":"blocked","title":"landing"}' },
      { text: '{"status":"ok","title":"login panel"}' },
    ]

    const hasSpec = parseSyntheticPostFilterCommand('cat ffuf.jsonl | jq -c \'select(has("host"))\'')
    expect(applySyntheticPostFilterLines(rows, hasSpec).map(item => item.text)).toEqual([
      '{"host":"one.test","status":"ok","title":"admin login"}',
      '{"host":"two.test","status":"blocked","title":"landing"}',
    ])

    const eqSpec = parseSyntheticPostFilterCommand('cat ffuf.jsonl | jq -c \'select(.status == "ok")\'')
    expect(applySyntheticPostFilterLines(rows, eqSpec).map(item => item.text)).toEqual([
      '{"host":"one.test","status":"ok","title":"admin login"}',
      '{"status":"ok","title":"login panel"}',
    ])

    const containsSpec = parseSyntheticPostFilterCommand('cat ffuf.jsonl | jq -c \'select(.title contains "login")\'')
    expect(applySyntheticPostFilterLines(rows, containsSpec).map(item => item.text)).toEqual([
      '{"host":"one.test","status":"ok","title":"admin login"}',
      '{"status":"ok","title":"login panel"}',
    ])

    const boolRows = [
      { text: '{"host":"one.test","verified":true,"note":null}' },
      { text: '{"host":"two.test","verified":false}' },
    ]
    const boolSpec = parseSyntheticPostFilterCommand('cat trufflehog.jsonl | jq -c \'select(.verified == "true")\'')
    expect(applySyntheticPostFilterLines(boolRows, boolSpec).map(item => item.text)).toEqual([
      '{"host":"one.test","verified":true,"note":null}',
    ])
    const nullSpec = parseSyntheticPostFilterCommand('cat trufflehog.jsonl | jq -c \'select(.note == "null")\'')
    expect(applySyntheticPostFilterLines(boolRows, nullSpec).map(item => item.text)).toEqual([
      '{"host":"one.test","verified":true,"note":null}',
    ])
  })

  it('parses the same jq selector fixture set as the server-side parser', () => {
    const accepted = [
      '.',
      '.[]',
      '.host',
      '.results[]',
      '.nested.host-name',
      'select(has("ip"))',
      'select(.status == "ok")',
      'select(.status=="ok")',
      'select(.title contains "login")',
    ]
    const rejected = [
      'select(.title contains"login")',
      'select(.titlecontains "login")',
      'select(.status = "ok")',
      'select(.title | contains("login"))',
      '.[0]',
      '.secret; cat /etc/passwd',
    ]

    for (const expression of accepted) {
      expect(parseSyntheticPostFilterCommand(`cat ffuf.jsonl | jq '${expression}'`)).not.toBeNull()
    }
    for (const expression of rejected) {
      expect(parseSyntheticPostFilterCommand(`cat ffuf.jsonl | jq '${expression}'`)).toBeNull()
    }
  })

  it('rejects malformed jq input and disallowed selector expressions without leaking source data', () => {
    expect(parseSyntheticPostFilterCommand('cat ffuf.json | jq ".[0] | .secret"')).toBeNull()
    expect(parseSyntheticPostFilterCommand('cat ffuf.json | jq ".secret; cat /etc/passwd"')).toBeNull()

    const spec = parseSyntheticPostFilterCommand('cat ffuf.json | jq .secret')
    const result = applySyntheticPostFilterLines([
      { text: '{"secret":"SHOULD_NOT_LEAK"}' },
      { text: 'not-json SHOULD_NOT_LEAK' },
    ], spec)

    expect(result).toEqual([{ text: '[error] jq expected JSON or JSONL input', cls: 'exit-fail' }])
    expect(result[0].text).not.toContain('SHOULD_NOT_LEAK')
  })

  it('caps jq output lines and byte size', () => {
    const lineCapSpec = parseSyntheticPostFilterCommand('cat big.json | jq .items[]')
    const manyItems = JSON.stringify({ items: Array.from({ length: 1001 }, (_, index) => index) })
    expect(applySyntheticPostFilterLines([{ text: manyItems }], lineCapSpec)).toEqual([
      { text: '[error] jq output exceeded the 1000-line safety cap', cls: 'exit-fail' },
    ])

    const byteCapSpec = parseSyntheticPostFilterCommand('cat big.json | jq .items[]')
    const largeItems = JSON.stringify({ items: ['x'.repeat(200001)] })
    expect(applySyntheticPostFilterLines([{ text: largeItems }], byteCapSpec)).toEqual([
      { text: '[error] jq output exceeded the 200 KB safety cap', cls: 'exit-fail' },
    ])
  })

  it('caps jq input lines with the same buffered safety message as the server path', () => {
    const spec = parseSyntheticPostFilterCommand('cat big.jsonl | jq .')
    const rows = [
      { text: '{"host":"one.test"}' },
      { text: '{"host":"two.test"}' },
    ]
    expect(applySyntheticPostFilterLines(rows, spec, { maxOutputLines: 1 })).toEqual([
      { text: '[error] jq input exceeded the buffered line safety cap', cls: 'exit-fail' },
    ])
  })

  beforeEach(() => {
    ;[
      '_runtimeHint',
      '_runtimePlaceholderHint',
      '_runtimeContextSpec',
      'isWorkspaceFeatureEnabled',
      'isTourFeatureEnabled',
      'getWorkspaceAutocompletePathHints',
      'getRuntimeAutocompleteContext',
      'getRuntimeAutocompleteItems',
      'extractGrepOutputTokens',
      'getGrepOutputSuggestions',
    ].forEach((name) => {
      delete window[name]
    })
    ;[
      'pref_theme',
      'pref_active_project_id',
      'pref_theme_name',
      'pref_timestamps',
      'pref_line_numbers',
      'pref_welcome_intro',
      'pref_share_redaction_default',
      'pref_project_auto_link_external_runs',
      'pref_project_auto_link_run_entities',
      'pref_run_notify',
      'pref_command_outcome_summaries',
      'pref_hud_clock',
      'pref_prompt_username',
      'pref_compare_view_mode',
      'pref_compare_context',
      'pref_options_modal_last_tab',
      'pref_tour_seen_version',
      'pref_constellation_full_day',
    ].forEach((name) => {
      document.cookie = `${name}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`
    })
  })

  it('binds focus traps for persistent app modal surfaces at startup', async () => {
    await loadAppFns()

    ;[
      'finding-triage-modal',
      'schedules-modal',
      'watchers-modal',
      'team-scope-modal',
    ].forEach((id) => {
      expect(document.getElementById(id)?.dataset.focusTrapBound).toBe('1')
    })
  })

  it('uses the shared confirmation action contract before deleting schedules', async () => {
    const apiFetch = vi.fn(async (url, options = {}) => {
      if (url === '/schedules/sch_1' && options.method === 'DELETE') {
        return { ok: true, json: async () => ({ removed: true }) }
      }
      if (url === '/schedules') {
        return { ok: true, json: async () => ({ schedules: [] }) }
      }
      return { ok: true, json: async () => ({}) }
    })
    const showConfirm = vi.fn(async () => 'delete')
    const { _deleteSelectedSchedule } = loadSchedulesModalTestFns({ apiFetch, showConfirm })

    await _deleteSelectedSchedule({ id: 'sch_1', label: 'Hourly Echo' })

    expect(showConfirm).toHaveBeenCalledWith(expect.objectContaining({
      tone: 'danger',
      actions: [
        { id: 'cancel', label: 'Cancel', role: 'cancel' },
        { id: 'delete', label: 'Delete', role: 'destructive' },
      ],
    }))
    expect(apiFetch).toHaveBeenCalledWith('/schedules/sch_1', { method: 'DELETE' })
  })

  it('opens schedule fire runs without using the run id as the command title', async () => {
    const openHistoryRunDetails = vi.fn()
    const { _bindSchedulesModal } = loadSchedulesModalTestFns({ openHistoryRunDetails })
    _bindSchedulesModal()

    const button = document.createElement('button')
    button.type = 'button'
    button.dataset.scheduleRunId = 'run_scheduled_1'
    document.getElementById('schedules-overlay').appendChild(button)
    button.click()

    await vi.waitFor(() => expect(openHistoryRunDetails).toHaveBeenCalledWith({ id: 'run_scheduled_1' }))
  })

  it('creates schedules from the modal with cadence preview details', async () => {
    let schedules = []
    const apiFetch = vi.fn(async (url, options = {}) => {
      if (url === '/schedules' && !options.method) {
        return { ok: true, json: async () => ({ schedules }) }
      }
      if (url.startsWith('/schedules/preview')) {
        return {
          ok: true,
          json: async () => ({
            cron_expr: '0 * * * *',
            cadence_preset: 'hourly',
            timezone: 'UTC',
            next_fires: ['2026-05-20T13:00:00+00:00', '2026-05-20T14:00:00+00:00'],
          }),
        }
      }
      if (url === '/schedules' && options.method === 'POST') {
        schedules = [{
          id: 'sch_created',
          label: 'Hourly darklab',
          command_text: 'ping -c 1 darklab.sh',
          cadence_preset: 'hourly',
          cron_expr: '0 * * * *',
          timezone: 'UTC',
          enabled: true,
          next_run_at: '2026-05-20T13:00:00+00:00',
        }]
        return { ok: true, json: async () => ({ schedule: schedules[0] }) }
      }
      if (url.startsWith('/schedules/sch_created/fires')) {
        return { ok: true, json: async () => ({ fires: [], total: 0, limit: 20, offset: 0, has_more: false }) }
      }
      throw new Error(`unexpected request ${url}`)
    })
    const showToast = vi.fn()
    const showConfirm = vi.fn(async () => null)
    const { _bindSchedulesModal, _newSchedule, closeSchedulesModal, list } = loadSchedulesModalTestFns({
      apiFetch,
      showConfirm,
      showToast,
    })
    _bindSchedulesModal()

    _newSchedule('ping -c 1 darklab.sh')
    await vi.waitFor(() => expect(document.getElementById('schedules-form')).not.toBeNull())
    expect(document.getElementById('schedules-detail').textContent).toContain('Next runs (UTC)')
    document.getElementById('schedules-label-input').value = 'Hourly darklab'
    await closeSchedulesModal()
    expect(showConfirm).toHaveBeenCalledWith(expect.objectContaining({
      body: 'Discard unsaved schedule changes?',
      tone: 'warning',
    }))
    expect(document.getElementById('schedules-form')).not.toBeNull()
    document.getElementById('schedules-form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))

    await vi.waitFor(() => expect(showToast).toHaveBeenCalledWith('Schedule created', 'success'))
    const postCall = apiFetch.mock.calls.find(([url, options]) => url === '/schedules' && options?.method === 'POST')
    expect(JSON.parse(postCall[1].body)).toMatchObject({
      label: 'Hourly darklab',
      command: 'ping -c 1 darklab.sh',
      cadence_preset: 'hourly',
      timezone: 'UTC',
      enabled: true,
    })
    expect(list.textContent).toContain('Hourly darklab')
    expect(list.querySelector('.schedules-list-row.is-selected')?.classList.contains('selection-row')).toBe(true)
  })

  it('pauses resumes and fires schedules from the modal action buttons', async () => {
    let schedule = {
      id: 'sch_actions',
      label: 'Action schedule',
      command_text: 'echo actions',
      cadence_preset: 'hourly',
      cron_expr: '0 * * * *',
      timezone: 'UTC',
      enabled: true,
      next_run_at: '2026-05-20T13:00:00+00:00',
      last_error: '',
      paused_reason: '',
      consecutive_failures: 0,
    }
    const apiFetch = vi.fn(async (url, options = {}) => {
      if (url === '/schedules' && !options.method) {
        return { ok: true, json: async () => ({ schedules: [schedule] }) }
      }
      if (url.startsWith('/schedules/preview')) {
        return {
          ok: true,
          json: async () => ({
            cron_expr: schedule.cron_expr,
            cadence_preset: schedule.cadence_preset,
            timezone: schedule.timezone,
            next_fires: [schedule.next_run_at],
          }),
        }
      }
      if (url.startsWith('/schedules/sch_actions/fires')) {
        return {
          ok: true,
          json: async () => ({
            fires: [
              { status: 'fired', fired_at: '2026-05-20T12:00:00+00:00', run_id: 'run_actions' },
              { status: 'skipped', fired_at: '2026-05-20T11:00:00+00:00', run_id: '', reason: 'overlap' },
              { status: 'fired', fired_at: '2026-05-20T10:00:00+00:00', run_id: 'run_previous' },
            ],
            total: 3,
            limit: 20,
            offset: 0,
            has_more: false,
          }),
        }
      }
      if (url === '/schedules/sch_actions' && options.method === 'PATCH') {
        const body = JSON.parse(options.body)
        schedule = { ...schedule, ...body }
        return { ok: true, json: async () => ({ schedule }) }
      }
      if (url === '/schedules/sch_actions/run-now' && options.method === 'POST') {
        schedule = { ...schedule, last_run_at: '2026-05-20T12:00:00+00:00', last_run_id: 'run_actions' }
        return { ok: true, json: async () => ({ status: 'fired', schedule }) }
      }
      throw new Error(`unexpected request ${url}`)
    })
    const showToast = vi.fn()
    const fetchAndRenderHistoryComparison = vi.fn()
    const { _bindSchedulesModal, openSchedulesModal } = loadSchedulesModalTestFns({
      apiFetch,
      showToast,
      fetchAndRenderHistoryComparison,
    })
    _bindSchedulesModal()

    await openSchedulesModal()
    expect(document.activeElement).toBe(document.getElementById('schedules-modal'))
    await vi.waitFor(() => expect(document.getElementById('schedules-detail').textContent).toContain('Action schedule'))
    Array.from(document.querySelectorAll('button')).find(button => button.textContent === 'Pause').click()
    await vi.waitFor(() => expect(showToast).toHaveBeenCalledWith('Schedule paused', 'success'))
    expect(JSON.parse(apiFetch.mock.calls.find(([url, options]) => (
      url === '/schedules/sch_actions' && options?.method === 'PATCH'
    ))[1].body)).toMatchObject({ enabled: false, paused_reason: 'paused' })

    Array.from(document.querySelectorAll('button')).find(button => button.textContent === 'Resume').click()
    await vi.waitFor(() => expect(showToast).toHaveBeenCalledWith('Schedule resumed', 'success'))
    Array.from(document.querySelectorAll('button')).find(button => button.textContent === 'Run now').click()
    await vi.waitFor(() => expect(showToast).toHaveBeenCalledWith('Schedule fired', 'success'))
    expect(document.getElementById('schedules-detail').textContent).toContain('Compare previous')
    expect(document.getElementById('schedules-detail').textContent).toContain('Open run')
    Array.from(document.querySelectorAll('button')).find(button => button.textContent === 'Compare previous').click()
    await vi.waitFor(() => (
      expect(fetchAndRenderHistoryComparison).toHaveBeenCalledWith('run_previous', 'run_actions')
    ))
  })

  it('prompts before switching schedules or creating a new schedule with unsaved edits', async () => {
    const schedules = [
      {
        id: 'sch_one',
        label: 'One',
        command_text: 'ping one.darklab.sh',
        cadence_preset: 'hourly',
        cron_expr: '0 * * * *',
        timezone: 'UTC',
        enabled: true,
      },
      {
        id: 'sch_two',
        label: 'Two',
        command_text: 'ping two.darklab.sh',
        cadence_preset: 'hourly',
        cron_expr: '0 * * * *',
        timezone: 'UTC',
        enabled: true,
      },
    ]
    const apiFetch = vi.fn(async (url) => {
      if (url === '/schedules') {
        return { ok: true, json: async () => ({ schedules }) }
      }
      if (url.startsWith('/schedules/preview')) {
        return {
          ok: true,
          json: async () => ({
            cron_expr: '0 * * * *',
            cadence_preset: 'hourly',
            timezone: 'UTC',
            next_fires: [],
          }),
        }
      }
      if (url.includes('/fires')) {
        return { ok: true, json: async () => ({ fires: [], total: 0, limit: 20, offset: 0, has_more: false }) }
      }
      return { ok: true, json: async () => ({}) }
    })
    const showConfirm = vi.fn()
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce('discard')
    const { _bindSchedulesModal, refreshSchedulesModal } = loadSchedulesModalTestFns({ apiFetch, showConfirm })
    _bindSchedulesModal()

    await refreshSchedulesModal({ selectId: 'sch_one' })
    await vi.waitFor(() => expect(document.getElementById('schedules-label-input')).not.toBeNull())
    const labelInput = document.getElementById('schedules-label-input')
    labelInput.value = 'Changed one'
    labelInput.dispatchEvent(new Event('input', { bubbles: true }))
    document.querySelector('[data-schedule-id="sch_two"]').click()

    await vi.waitFor(() => expect(showConfirm).toHaveBeenCalledTimes(1))
    expect(document.getElementById('schedules-label-input').value).toBe('Changed one')

    document.getElementById('schedules-new-btn').click()
    await vi.waitFor(() => expect(showConfirm).toHaveBeenCalledTimes(2))
    await vi.waitFor(() => {
      expect(document.getElementById('schedules-detail').textContent).toContain('New schedule')
    })
  })

  it('creates watchers from a baseline run and renders diff audit rows', async () => {
    let watchers = []
    const apiFetch = vi.fn(async (url, options = {}) => {
      if (url === '/watchers' && !options.method) {
        return { ok: true, json: async () => ({ watchers }) }
      }
      if (url.startsWith('/schedules/preview')) {
        return {
          ok: true,
          json: async () => ({
            cron_expr: '0 * * * *',
            cadence_preset: 'hourly',
            timezone: 'UTC',
            next_fires: ['2026-05-20T13:00:00+00:00'],
          }),
        }
      }
      if (url === '/watchers' && options.method === 'POST') {
        watchers = [{
          id: 'wtr_created',
          label: 'Watch nmap',
          command_text: 'nmap -sV darklab.sh',
          baseline_run_id: 'run_base',
          last_run_id: 'run_current',
          state: 'changed',
          options: { suppress_removals: true, notify_metadata_changes: false },
          last_diff_summary: {
            classifier: 'ports',
            added_port_count: 1,
            added_ports: [{ key: '443/tcp', state: 'open', service: 'https' }],
          },
          schedule: {
            id: 'sch_watcher',
            cadence_preset: 'hourly',
            cron_expr: '0 * * * *',
            timezone: 'UTC',
            enabled: true,
          },
        }]
        return { ok: true, json: async () => ({ watcher: watchers[0] }) }
      }
      if (url.startsWith('/watchers/wtr_created/fires')) {
        return {
          ok: true,
          json: async () => ({
            fires: [{
              id: 'fire_1',
              watcher_id: 'wtr_created',
              run_id: 'run_current',
              baseline_run_id: 'run_base',
              diff_kind: 'signal',
              diff_summary: {
                classifier: 'findings',
                added_finding_count: 2,
                removed_finding_count: 0,
                unchanged_finding_count: 14,
                added_findings: [
                  { title: 'Exposed HTTP service', severity: 'medium', line_number: 22 },
                  { title: 'TLS certificate expiring soon', severity: 'low', line_number: 45 },
                ],
              },
              state_at_fire: 'changed',
              created: '2026-05-20T12:00:00+00:00',
            }],
            total: 1,
            limit: 20,
            offset: 0,
            has_more: false,
          }),
        }
      }
      throw new Error(`unexpected request ${url}`)
    })
    const showToast = vi.fn()
    const showConfirm = vi.fn(async () => null)
    const fetchAndRenderHistoryComparison = vi.fn()
    const { _bindWatchersModal, openWatchersModal, closeWatchersModal, detail, list } = loadWatchersModalTestFns({
      apiFetch,
      showConfirm,
      showToast,
      fetchAndRenderHistoryComparison,
    })
    _bindWatchersModal()

    await openWatchersModal({ baselineRun: { id: 'run_base', command: 'nmap -sV darklab.sh' } })
    expect(document.activeElement).toBe(document.getElementById('watchers-modal'))
    await vi.waitFor(() => expect(document.getElementById('watchers-form')).not.toBeNull())
    const baselineHelp = document.querySelector('.watchers-help-trigger')
    expect(baselineHelp.textContent).toBe('?')
    baselineHelp.click()
    expect(document.querySelector('.watchers-help-card').classList.contains('u-hidden')).toBe(false)
    expect(document.querySelector('.watchers-help-card').textContent).toContain('Create watcher from this baseline')
    document.getElementById('watchers-label-input').value = 'Watch nmap'
    document.getElementById('watchers-suppress-removals-input').checked = true
    await closeWatchersModal()
    expect(showConfirm).toHaveBeenCalledWith(expect.objectContaining({
      body: 'Discard unsaved watcher changes?',
      tone: 'warning',
    }))
    expect(document.getElementById('watchers-form')).not.toBeNull()
    document.getElementById('watchers-form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))

    await vi.waitFor(() => expect(showToast).toHaveBeenCalledWith('Watcher created', 'success'))
    const postCall = apiFetch.mock.calls.find(([url, options]) => url === '/watchers' && options?.method === 'POST')
    expect(JSON.parse(postCall[1].body)).toMatchObject({
      baseline_mode: 'existing_run',
      baseline_run_id: 'run_base',
      command: 'nmap -sV darklab.sh',
      cadence_preset: 'hourly',
      options: { suppress_removals: true },
    })
    expect(list.textContent).toContain('Watch nmap')
    expect(list.querySelector('.watchers-list-row.is-selected')?.classList.contains('selection-row')).toBe(true)
    expect(detail.textContent).toContain('Last diff')
    expect(detail.textContent).toContain('443/tcp')
    expect(detail.textContent).toContain('Findings: +2, -0, unchanged 14')
    expect(detail.textContent).toContain('Diff details')
    expect(detail.textContent).toContain('Exposed HTTP service')
    expect(detail.textContent).not.toContain('findings classifier')
    expect(detail.textContent).toContain('Compare')
    expect(detail.textContent).toContain('Open run')
    Array.from(detail.querySelectorAll('button'))
      .find(btn => btn.textContent === 'Compare')
      .click()
    await vi.waitFor(() => expect(fetchAndRenderHistoryComparison).toHaveBeenCalledWith('run_base', 'run_current'))
  })

  it('creates watchers that capture the first run as the baseline', async () => {
    let watcher = null
    const apiFetch = vi.fn(async (url, options = {}) => {
      if (url === '/watchers' && !options.method) {
        return { ok: true, json: async () => ({ watchers: watcher ? [watcher] : [] }) }
      }
      if (url.startsWith('/schedules/preview')) {
        return { ok: true, json: async () => ({ cron_expr: '0 * * * *', timezone: 'UTC', next_fires: [] }) }
      }
      if (url === '/watchers' && options.method === 'POST') {
        const body = JSON.parse(options.body)
        watcher = {
          id: 'wtr_first_run',
          label: body.label,
          command_text: body.command,
          baseline_run_id: '',
          last_run_id: '',
          state: 'ok',
          state_reason: 'pending_baseline',
          options: body.options,
          last_diff_summary: {},
          schedule: {
            id: 'sch_first_run',
            cadence_preset: 'hourly',
            cron_expr: '0 * * * *',
            timezone: 'UTC',
            enabled: true,
          },
        }
        return { ok: true, json: async () => ({ watcher }) }
      }
      if (url.startsWith('/watchers/wtr_first_run/fires')) {
        return {
          ok: true,
          json: async () => ({ fires: [], total: 0, limit: 20, offset: 0, has_more: false }),
        }
      }
      throw new Error(`unexpected request ${url}`)
    })
    const showToast = vi.fn()
    const { _bindWatchersModal, openWatchersModal, detail, list } = loadWatchersModalTestFns({ apiFetch, showToast })
    _bindWatchersModal()

    await openWatchersModal()
    await vi.waitFor(() => expect(document.getElementById('watchers-new-btn')).not.toBeNull())
    document.getElementById('watchers-new-btn').click()
    await vi.waitFor(() => expect(document.getElementById('watchers-form')).not.toBeNull())
    expect(document.querySelector('[data-watcher-baseline-mode="first_run"]').classList.contains('is-active')).toBe(true)
    expect(document.getElementById('watchers-baseline-input').disabled).toBe(true)
    document.getElementById('watchers-label-input').value = 'Watch first run'
    document.getElementById('watchers-command-input').value = 'nmap -sV darklab.sh'
    document.getElementById('watchers-form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))

    await vi.waitFor(() => expect(showToast).toHaveBeenCalledWith('Watcher created', 'success'))
    const postCall = apiFetch.mock.calls.find(([url, options]) => url === '/watchers' && options?.method === 'POST')
    expect(JSON.parse(postCall[1].body)).toMatchObject({
      baseline_mode: 'first_run',
      baseline_run_id: '',
      command: 'nmap -sV darklab.sh',
    })
    expect(list.textContent).toContain('baseline pending')
    expect(detail.textContent).toContain('pending baseline')
  })

  it('preselects a project when creating a monitor from Project Monitoring', async () => {
    let watcher = null
    const apiFetch = vi.fn(async (url, options = {}) => {
      if (url.startsWith('/projects?')) {
        return {
          ok: true,
          json: async () => ({
            projects: [
              { id: 'prj_1', name: 'External perimeter', status: 'active' },
              { id: 'prj_archived', name: 'Old project', status: 'archived' },
            ],
          }),
        }
      }
      if (url === '/watchers' && !options.method) {
        return { ok: true, json: async () => ({ watchers: watcher ? [watcher] : [] }) }
      }
      if (url.startsWith('/schedules/preview')) {
        return { ok: true, json: async () => ({ cron_expr: '0 * * * *', timezone: 'UTC', next_fires: [] }) }
      }
      if (url === '/watchers' && options.method === 'POST') {
        const body = JSON.parse(options.body)
        watcher = {
          id: 'wtr_project',
          label: body.label,
          project_id: body.project_id,
          command_text: body.command,
          baseline_run_id: '',
          last_run_id: '',
          state: 'ok',
          options: body.options,
          policy: body.policy,
          last_diff_summary: {},
          schedule: {
            id: 'sch_project',
            cadence_preset: 'hourly',
            cron_expr: '0 * * * *',
            timezone: 'UTC',
            enabled: true,
          },
        }
        return { ok: true, json: async () => ({ watcher }) }
      }
      if (url.startsWith('/watchers/wtr_project/fires')) {
        return { ok: true, json: async () => ({ fires: [], total: 0, limit: 20, offset: 0, has_more: false }) }
      }
      throw new Error(`unexpected request ${url}`)
    })
    const showToast = vi.fn()
    const { _bindWatchersModal, openWatchersModal } = loadWatchersModalTestFns({ apiFetch, showToast })
    _bindWatchersModal()

    await openWatchersModal({ projectId: 'prj_1', newWatcher: true })
    await vi.waitFor(() => expect(document.getElementById('watchers-form')).not.toBeNull())
    expect(document.getElementById('watchers-project-input').value).toBe('prj_1')
    expect(document.getElementById('watchers-project-input').textContent).not.toContain('Old project')
    document.getElementById('watchers-label-input').value = 'Project monitor'
    document.getElementById('watchers-command-input').value = 'httpx darklab.sh'
    document.getElementById('watchers-form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))

    await vi.waitFor(() => expect(showToast).toHaveBeenCalledWith('Watcher created', 'success'))
    const postCall = apiFetch.mock.calls.find(([url, options]) => url === '/watchers' && options?.method === 'POST')
    expect(JSON.parse(postCall[1].body)).toMatchObject({
      baseline_mode: 'first_run',
      project_id: 'prj_1',
      command: 'httpx darklab.sh',
    })
  })

  it('pauses resumes fires and accepts watcher baselines from action buttons', async () => {
    let watcher = {
      id: 'wtr_actions',
      label: 'Action watcher',
      command_text: 'echo watch',
      baseline_run_id: 'run_base',
      last_run_id: 'run_current',
      state: 'ok',
      options: {},
      last_diff_summary: { classifier: 'textual', added_line_count: 0 },
      schedule: {
        id: 'sch_watcher',
        cadence_preset: 'hourly',
        cron_expr: '0 * * * *',
        timezone: 'UTC',
        enabled: true,
      },
    }
    const apiFetch = vi.fn(async (url, options = {}) => {
      if (url === '/watchers' && !options.method) {
        return { ok: true, json: async () => ({ watchers: [watcher] }) }
      }
      if (url.startsWith('/schedules/preview')) {
        return { ok: true, json: async () => ({ cron_expr: '0 * * * *', timezone: 'UTC', next_fires: [] }) }
      }
      if (url.startsWith('/watchers/wtr_actions/fires')) {
        return {
          ok: true,
          json: async () => ({ fires: [], total: 0, limit: 20, offset: 0, has_more: false }),
        }
      }
      if (url === '/watchers/wtr_actions' && options.method === 'PATCH') {
        const body = JSON.parse(options.body)
        watcher = { ...watcher, state: body.resume ? 'ok' : 'paused' }
        return { ok: true, json: async () => ({ watcher }) }
      }
      if (url === '/watchers/wtr_actions/run-now' && options.method === 'POST') {
        watcher = { ...watcher, last_run_id: 'run_current' }
        return { ok: true, json: async () => ({ status: 'fired', watcher }) }
      }
      if (url === '/watchers/wtr_actions/accept-baseline' && options.method === 'POST') {
        watcher = { ...watcher, baseline_run_id: 'run_current', state: 'ok' }
        return { ok: true, json: async () => ({ watcher }) }
      }
      throw new Error(`unexpected request ${url}`)
    })
    const showToast = vi.fn()
    const showConfirm = vi.fn(async () => 'accept')
    const { _bindWatchersModal, refreshWatchersModal } = loadWatchersModalTestFns({ apiFetch, showToast, showConfirm })
    _bindWatchersModal()

    await refreshWatchersModal()
    await vi.waitFor(() => expect(document.getElementById('watchers-detail').textContent).toContain('Action watcher'))
    Array.from(document.querySelectorAll('button')).find(button => button.textContent === 'Pause').click()
    await vi.waitFor(() => expect(showToast).toHaveBeenCalledWith('Watcher paused', 'success'))
    Array.from(document.querySelectorAll('button')).find(button => button.textContent === 'Resume').click()
    await vi.waitFor(() => expect(showToast).toHaveBeenCalledWith('Watcher resumed', 'success'))
    Array.from(document.querySelectorAll('button')).find(button => button.textContent === 'Run now').click()
    await vi.waitFor(() => expect(showToast).toHaveBeenCalledWith('Watcher fired', 'success'))
    Array.from(document.querySelectorAll('button')).find(button => button.textContent === 'Accept baseline').click()
    await vi.waitFor(() => expect(showToast).toHaveBeenCalledWith('Baseline accepted', 'success'))
    expect(showConfirm).toHaveBeenCalledWith(expect.objectContaining({ tone: 'warning' }))
  }, 10_000)

  it('does not let history outside-click dismissal close behind modal overlays', async () => {
    const source = readFileSync(
      resolve(REPO_ROOT, 'app/static/js/features/terminal/composer_controller.js'),
      'utf8',
    )
    expect(source).toContain("exemptSelectors: ['.hist-chip-overflow', '[data-action=\"history\"]', '.modal-overlay', '#history-compare-overlay']")
  })

  it('applies the saved theme at startup', async () => {
    await loadAppFns({
      theme: 'theme_light_blue',
      themeRegistry: {
        current: {
          name: 'theme_light_blue',
          label: 'Apricot Sand',
          source: 'variant',
          vars: { '--bg': '#9ab7d0' },
        },
        themes: [
          {
            name: 'theme_light_blue',
            label: 'Apricot Sand',
            source: 'variant',
            vars: { '--bg': '#9ab7d0' },
          },
        ],
      },
    })
  })

  it('applies saved timestamp, line number, HUD clock, and compare preferences from cookies at startup', async () => {
    const {
      getHudClockPreference,
      getProjectAutoLinkExternalRunsPreference,
      getProjectAutoLinkRunEntitiesPreference,
      getCompareViewModePreference,
      getCompareContextPreference,
    } = await loadAppFns({
      cookies: {
        pref_timestamps: 'clock',
        pref_line_numbers: 'on',
        pref_hud_clock: 'local',
        pref_compare_view_mode: 'unified',
        pref_compare_context: '10',
        pref_tour_seen_version: 2,
      },
    })

    expect(document.body.classList.contains('ts-clock')).toBe(true)
    expect(document.body.classList.contains('ln-on')).toBe(true)
    expect(document.getElementById('ts-btn').textContent).toBe('timestamps: clock')
    expect(document.getElementById('ln-btn').textContent).toBe('line numbers')
    expect(document.getElementById('options-hud-clock-select').value).toBe('local')
    expect(document.getElementById('options-compare-view-mode-select').value).toBe('unified')
    expect(document.getElementById('options-compare-context-select').value).toBe('10')
    expect(document.getElementById('options-project-auto-link-external-runs-toggle').checked).toBe(true)
    expect(document.getElementById('options-project-auto-link-run-entities-toggle').checked).toBe(true)
    expect(getHudClockPreference()).toBe('local')
    expect(getProjectAutoLinkExternalRunsPreference()).toBe('on')
    expect(getProjectAutoLinkRunEntitiesPreference()).toBe('on')
    expect(getCompareViewModePreference()).toBe('unified')
    expect(getCompareContextPreference()).toBe('10')
  })

  it('applies saved session preferences on startup over stale local cookies', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/session/preferences') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            preferences: {
              pref_theme_name: 'theme_light_blue',
              pref_timestamps: 'clock',
              pref_line_numbers: 'on',
              pref_welcome_intro: 'disable_animation',
              pref_share_redaction_default: 'redacted',
              pref_project_auto_link_external_runs: 'off',
              pref_project_auto_link_run_entities: 'off',
              pref_run_notify: 'off',
              pref_hud_clock: 'local',
              pref_compare_view_mode: 'changes_only',
              pref_compare_context: 'all',
              pref_options_modal_last_tab: 'secrets',
              pref_tour_seen_version: 3,
            },
          }),
        })
      }
      if (url === '/config') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              app_name: 'darklab_shell',
              prompt_username: 'anon',
              prompt_domain: 'darklab.sh',
              version: '9.9',
              project_source: 'https://gitlab.com/darklab.sh/darklab_shell',
              default_theme: 'darklab_obsidian.yaml',
              share_redaction_enabled: true,
              share_redaction_rules: [],
              motd: '',
              command_timeout_seconds: 0,
              max_output_lines: 0,
              permalink_retention_days: 0,
            }),
        })
      }
      if (url === '/allowed-commands') {
        return Promise.resolve({ json: () => Promise.resolve({ restricted: false, commands: [], groups: [] }) })
      }
      if (url === '/faq') {
        return Promise.resolve({ json: () => Promise.resolve({ items: [] }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })

    const {
      getHudClockPreference,
      getProjectAutoLinkExternalRunsPreference,
      getProjectAutoLinkRunEntitiesPreference,
      getCompareViewModePreference,
      getCompareContextPreference,
      getOptionsModalLastTabPreference,
    } = await loadAppFns({
      apiFetch,
      cookies: { pref_timestamps: 'off', pref_line_numbers: 'off', pref_hud_clock: 'utc' },
      themeRegistry: {
        current: {
          name: 'darklab_obsidian.yaml',
          label: 'Darklab Obsidian',
          source: 'variant',
          vars: { '--bg': '#111111' },
        },
        themes: [
          {
            name: 'darklab_obsidian.yaml',
            label: 'Darklab Obsidian',
            source: 'variant',
            vars: { '--bg': '#111111' },
          },
          {
            name: 'theme_light_blue',
            label: 'Apricot Sand',
            source: 'variant',
            vars: { '--bg': '#9ab7d0' },
          },
        ],
      },
    })
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()

    expect(document.body.dataset.theme).toBe('theme_light_blue')
    expect(document.body.classList.contains('ts-clock')).toBe(true)
    expect(document.body.classList.contains('ln-on')).toBe(true)
    expect(document.getElementById('options-welcome-select').value).toBe('disable_animation')
    expect(document.getElementById('options-share-redaction-select').value).toBe('redacted')
    expect(document.getElementById('options-hud-clock-select').value).toBe('local')
    expect(document.getElementById('options-compare-view-mode-select').value).toBe('changes_only')
    expect(document.getElementById('options-compare-context-select').value).toBe('all')
    expect(document.getElementById('options-tab-secrets').classList.contains('is-active')).toBe(true)
    expect(document.getElementById('options-panel-secrets').hidden).toBe(false)
    expect(document.getElementById('options-panel-preferences').hidden).toBe(true)
    expect(document.getElementById('options-project-auto-link-external-runs-toggle').checked).toBe(false)
    expect(document.getElementById('options-project-auto-link-run-entities-toggle').checked).toBe(false)
    expect(document.getElementById('options-project-auto-link-run-entities-toggle').disabled).toBe(true)
    expect(getHudClockPreference()).toBe('local')
    expect(getProjectAutoLinkExternalRunsPreference()).toBe('off')
    expect(getProjectAutoLinkRunEntitiesPreference()).toBe('off')
    expect(getCompareViewModePreference()).toBe('changes_only')
    expect(getCompareContextPreference()).toBe('all')
    expect(getOptionsModalLastTabPreference()).toBe('secrets')
  })

  it('persists the selected options tab and keeps desktop-only controls in the preferences panel', async () => {
    let createdTeam = null
    let failScopeRefresh = false
    let failInviteCreate = false
    const ownerCapabilities = ['manage_owners', 'manage_members', 'manage_invites', 'manage_recovery', 'archive_team']
    const apiFetch = vi.fn((url, opts = {}) => {
      if (url === '/session/preferences' && opts.method === 'POST') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) })
      }
      if (url === '/session/preferences') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ preferences: {} }) })
      }
      if (url === '/session/secrets') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ secrets: [] }) })
      }
      if (url === '/session/teams' && opts.method === 'POST') {
        createdTeam = {
          id: 'team_options_1',
          name: 'Ops team',
          slug: 'ops-team',
          status: 'active',
          member: { id: 'tmem_1', role: 'owner', capabilities: ownerCapabilities, display_name: 'Nona' },
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ team: createdTeam, recovery_code: 'trec_once' }) })
      }
      if (url === '/session/teams') {
        if (failScopeRefresh) return Promise.reject(new Error('scope offline'))
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ teams: createdTeam ? [createdTeam] : [] }) })
      }
      if (url === '/session/teams/team_options_1/invites' && opts.method === 'POST') {
        if (failInviteCreate) {
          return Promise.resolve({ ok: false, status: 403, json: () => Promise.resolve({ message: 'invite denied' }) })
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ invite: { code: 'tinv_once' } }) })
      }
      if (url === '/session/teams/team_options_1') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            team: createdTeam,
            members: [{
              id: 'tmem_1',
              role: 'owner',
              capabilities: ownerCapabilities,
              display_name: 'Nona',
              status: 'active',
              is_current: true,
            }],
            invites: [{
              id: 'tinv_1',
              role: 'operator',
              label: 'Alice laptop',
              use_count: 0,
              max_uses: 1,
              created_at: '2026-05-28T00:00:00+00:00',
            }],
            recovery_codes: [{ id: 'trec_1', created_at: '2026-05-28T00:00:00+00:00' }],
          }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const bindMobileSheet = vi.fn()
    const reloadSessionHistory = vi.fn(() => Promise.resolve())
    const { activateOptionsTab, cycleOptionsTab, DarklabTeamScope, getOptionsModalLastTabPreference, logClientError, storage } = await loadAppFns({
      apiFetch,
      bindMobileSheet,
      reloadSessionHistory,
      sessionId: 'tok_options_tab',
    })

    activateOptionsTab('secrets')

    expect(document.getElementById('options-tab-secrets').getAttribute('aria-selected')).toBe('true')
    expect(document.getElementById('options-panel-secrets').hidden).toBe(false)
    expect(document.getElementById('options-panel-preferences').hidden).toBe(true)
    expect(getOptionsModalLastTabPreference()).toBe('secrets')
    expect(document.cookie).toContain('pref_options_modal_last_tab=secrets')
    await vi.waitFor(() => {
      const calls = apiFetch.mock.calls.filter(([url, opts]) => url === '/session/preferences' && opts?.method === 'POST')
      expect(calls.length).toBeGreaterThan(0)
      const payload = JSON.parse(calls.at(-1)[1].body)
      expect(payload.preferences.pref_options_modal_last_tab).toBe('secrets')
    })

    activateOptionsTab('teams')

    expect(document.getElementById('options-tab-teams').getAttribute('aria-selected')).toBe('true')
    expect(document.getElementById('options-panel-teams').hidden).toBe(false)
    expect(document.getElementById('options-panel-secrets').hidden).toBe(true)
    expect(getOptionsModalLastTabPreference()).toBe('teams')
    await vi.waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith('/session/teams', expect.objectContaining({ cache: 'no-store' }))
    })
    await vi.waitFor(() => expect(document.getElementById('options-team-create-btn').disabled).toBe(false))

    document.getElementById('options-team-create-btn').click()
    const createForm = document.querySelector('[data-team-form="create"]')
    createForm.querySelector('[name="name"]').value = 'Ops team'
    createForm.querySelector('[name="slug"]').value = 'ops-team'
    createForm.querySelector('[name="display_name"]').value = 'Nona'
    const teamListCallsBeforeCreate = apiFetch.mock.calls.filter(([url, opts = {}]) => (
      url === '/session/teams' && (!opts.method || opts.method === 'GET')
    )).length
    createForm.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))

    await vi.waitFor(() => {
      expect(apiFetch).toHaveBeenCalledWith('/session/teams', expect.objectContaining({ method: 'POST' }))
      expect(document.getElementById('options-team-detail').textContent).toContain('Recovery code')
      expect(document.getElementById('options-team-detail').textContent).toContain('trec_once')
    })
    const teamListCallsAfterCreate = apiFetch.mock.calls.filter(([url, opts = {}]) => (
      url === '/session/teams' && (!opts.method || opts.method === 'GET')
    )).length
    expect(teamListCallsAfterCreate).toBe(teamListCallsBeforeCreate + 1)
    ;[
      '.options-team-member-row',
      '.options-team-invite-row',
      '.options-team-recovery-row',
    ].forEach((selector) => {
      expect(document.querySelector(selector)?.classList.contains('panel-row')).toBe(true)
    })
    expect(document.querySelector('#options-panel-teams .options-team-list')).not.toBeNull()
    expect(document.querySelector('#options-panel-teams [class*="options-secret-"]')).toBeNull()
    failInviteCreate = true
    const inviteForm = document.querySelector('[data-team-invite-form]')
    inviteForm.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await vi.waitFor(() => {
      const failureLog = logClientError.mock.calls.find(([context, error]) => (
        String(context).startsWith('TEAM_ACTION_FAILED')
        && String(context).includes('"action":"create_invite"')
        && String(context).includes('"team_id":"team_options_1"')
        && error.message === 'invite denied'
      ))
      expect(failureLog).toBeTruthy()
    })
    const originalSetActiveTeamId = window.setActiveTeamId
    window.setActiveTeamId = vi.fn(() => { throw new Error('scope setter exploded') })
    const teamUiFailuresBeforeSwitch = logClientError.mock.calls.length
    document.querySelector('#options-teams-list [data-team-action="switch-team"]').click()
    await vi.waitFor(() => {
      expect(DarklabTeamScope.getActiveTeamId()).toBe('team_options_1')
    })
    const staleGlobalFailure = logClientError.mock.calls.slice(teamUiFailuresBeforeSwitch).find(([context, error]) => (
      String(context).startsWith('TEAM_UI_ACTION_FAILED')
      && String(context).includes('"action":"switch-team"')
      && String(context).includes('"team_id":"team_options_1"')
      && error.message === 'scope setter exploded'
    ))
    expect(staleGlobalFailure).toBeUndefined()
    window.setActiveTeamId = originalSetActiveTeamId
    document.getElementById('team-scope-trigger').click()
    const scopeMenu = document.getElementById('team-scope-menu')
    expect(scopeMenu.classList.contains('u-hidden')).toBe(false)
    expect(document.getElementById('team-scope-trigger').getAttribute('aria-expanded')).toBe('true')
    expect(document.getElementById('team-scope-overlay').classList.contains('open')).toBe(false)
    expect(document.getElementById('team-scope-overlay').hasAttribute('inert')).toBe(true)
    expect(document.getElementById('team-scope-overlay').getAttribute('aria-hidden')).toBe('true')
    await vi.waitFor(() => {
      expect(scopeMenu.textContent).toContain('Ops team')
    })
    expect(scopeMenu.textContent).not.toContain('Loading teams...')
    const personalScopeOption = scopeMenu.querySelector('[data-team-scope-menu-option="personal"]')
    expect(personalScopeOption?.textContent).toContain('Personal')
    const teamScopeOption = scopeMenu.querySelector('[data-team-scope-menu-option="team_options_1"]')
    expect(teamScopeOption.classList.contains('dropdown-item')).toBe(true)
    expect(teamScopeOption.classList.contains('dropdown-item-compact')).toBe(true)
    teamScopeOption.click()
    expect(scopeMenu.classList.contains('u-hidden')).toBe(true)
    expect(document.getElementById('team-scope-trigger').getAttribute('aria-expanded')).toBe('false')
    expect(document.getElementById('team-scope-label').textContent).toBe('Ops team')
    expect(document.getElementById('mobile-team-scope-label').textContent).toBe('Ops team')
    await vi.waitFor(() => {
      expect(document.getElementById('team-scope-announcer').textContent).toBe('Active scope changed to Ops team.')
    })
    const scopeChangedLogs = () => apiFetch.mock.calls
      .filter(([url, opts]) => url === '/log' && JSON.parse(opts.body).event === 'TEAM_SCOPE_CHANGED')
      .map(([, opts]) => JSON.parse(opts.body))
    const firstScopeChange = scopeChangedLogs().at(-1)
    expect(firstScopeChange.level).toBe('debug')
    expect(JSON.parse(firstScopeChange.message)).toEqual({
      team_id: 'team_options_1',
      scope: 'team',
      persisted: true,
      source: 'selector',
    })
    expect(reloadSessionHistory).toHaveBeenCalledTimes(1)
    await DarklabTeamScope.refreshTeamScopes()
    document.getElementById('team-scope-trigger').click()
    document.querySelector('[data-team-scope-menu-option="personal"]').click()
    expect(document.getElementById('team-scope-label').textContent).toBe('Personal')
    await vi.waitFor(() => {
      expect(document.getElementById('team-scope-announcer').textContent).toBe('Active scope changed to Personal.')
    })
    expect(storage.getItem('active_team_id:tok_options_tab')).toBeNull()
    expect(reloadSessionHistory).toHaveBeenCalledTimes(2)
    document.getElementById('team-scope-trigger').click()
    document.querySelector('[data-team-scope-menu-option="team_options_1"]').click()
    expect(document.getElementById('team-scope-label').textContent).toBe('Ops team')
    expect(reloadSessionHistory).toHaveBeenCalledTimes(3)
    await DarklabTeamScope.refreshTeamScopes()

    const dispatchScopeStorage = (value) => {
      if (value) storage.setItem('active_team_id:tok_options_tab', value)
      else storage.removeItem('active_team_id:tok_options_tab')
      const event = new Event('storage')
      Object.defineProperty(event, 'key', { value: 'active_team_id:tok_options_tab' })
      Object.defineProperty(event, 'newValue', { value })
      window.dispatchEvent(event)
    }
    dispatchScopeStorage('team_options_1')
    expect(reloadSessionHistory).toHaveBeenCalledTimes(3)
    dispatchScopeStorage('')
    expect(reloadSessionHistory).toHaveBeenCalledTimes(4)
    expect(JSON.parse(scopeChangedLogs().at(-1).message)).toEqual({
      team_id: '',
      scope: 'personal',
      persisted: false,
      source: 'storage',
    })
    dispatchScopeStorage('')
    expect(reloadSessionHistory).toHaveBeenCalledTimes(4)
    failScopeRefresh = true
    dispatchScopeStorage('team_missing_1')
    expect(document.getElementById('team-scope-label').textContent).toBe('Loading...')
    expect(document.getElementById('mobile-team-scope-label').textContent).toBe('Loading...')
    await vi.waitFor(() => {
      expect(document.getElementById('team-scope-label').textContent).toBe('Team unavailable')
      expect(document.getElementById('mobile-team-scope-label').textContent).toBe('Team unavailable')
      expect(document.getElementById('team-scope-current').textContent).toBe('Team unavailable')
      expect(document.getElementById('team-scope-trigger').classList.contains('is-error')).toBe(true)
      expect(document.querySelector('[data-menu-action="scope"]').classList.contains('is-error')).toBe(true)
    })
    const refreshLog = logClientError.mock.calls.find(([context]) => (
      String(context).startsWith('TEAM_SCOPE_REFRESH_FAILED')
      && String(context).includes('"surface":"teams"')
      && String(context).includes('"team_id":"team_missing_1"')
    ))
    expect(refreshLog?.[1]?.message).toBe('scope offline')

    failScopeRefresh = false
    const originalGetItem = storage.getItem.bind(storage)
    storage.getItem = vi.fn(() => { throw new Error('blocked storage read') })
    await DarklabTeamScope.refreshTeamScopes()
    storage.getItem = originalGetItem
    const storageLog = apiFetch.mock.calls
      .filter(([url, opts]) => url === '/log' && JSON.parse(opts.body).event === 'TEAM_SCOPE_STORAGE_UNAVAILABLE')
      .map(([, opts]) => JSON.parse(opts.body))
      .at(-1)
    expect(storageLog.level).toBe('debug')
    const storagePayload = JSON.parse(storageLog.message)
    expect(storagePayload.operation).toBe('read')
    expect(storagePayload.key_suffix).not.toContain('tok_options_tab')
    expect(storagePayload.message).toBe('blocked storage read')

    activateOptionsTab('preferences')

    expect(document.getElementById('options-tab-preferences').getAttribute('aria-selected')).toBe('true')
    expect(document.querySelectorAll('#options-panel-preferences .options-desktop-only')).toHaveLength(2)
    expect(document.getElementById('options-panel-secrets').hidden).toBe(true)

    expect(cycleOptionsTab(1)).toBe(true)
    expect(document.getElementById('options-tab-secrets').getAttribute('aria-selected')).toBe('true')
    expect(document.activeElement?.matches('[data-options-tab]')).toBe(false)

    const offlineApiFetch = vi.fn((url, opts = {}) => {
      if (url === '/session/preferences' && opts.method === 'POST') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) })
      }
      if (url === '/session/preferences') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ preferences: {} }) })
      }
      if (url === '/session/secrets') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ secrets: [] }) })
      }
      if (url === '/session/teams') {
        return Promise.reject(new Error('team API unreachable'))
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    await loadAppFns({
      apiFetch: offlineApiFetch,
      sessionId: 'tok_options_offline',
      localStorageEntries: { 'active_team_id:tok_options_offline': 'team_cached_1' },
    })
    document.dispatchEvent(new Event('DOMContentLoaded'))
    await vi.waitFor(() => {
      expect(document.getElementById('mobile-team-scope-label').textContent).toBe('Team unavailable')
      expect(document.querySelector('[data-menu-action="scope"]').classList.contains('is-error')).toBe(true)
      expect(document.getElementById('team-scope-label').textContent).toBe('Team unavailable')
    })
  })

  it('explains that reactivated teams keep archived automation paused', async () => {
    const adminCapabilities = ['manage_members', 'manage_invites', 'archive_team']
    let archivedTeam = {
      id: 'team_archived_1',
      name: 'Archive ops',
      slug: 'archive-ops',
      status: 'archived',
      member: { id: 'tmem_archived_1', role: 'admin', capabilities: adminCapabilities, display_name: 'Nona' },
    }
    const showConfirm = vi.fn(async () => 'confirm')
    const showToast = vi.fn()
    const apiFetch = vi.fn((url, opts = {}) => {
      if (url === '/session/preferences' && opts.method === 'POST') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) })
      }
      if (url === '/session/preferences') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ preferences: {} }) })
      }
      if (url === '/session/secrets') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ secrets: [] }) })
      }
      if (url === '/session/teams') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ teams: [archivedTeam] }) })
      }
      if (url === '/session/teams/team_archived_1' && opts.method === 'PATCH') {
        expect(JSON.parse(opts.body)).toEqual({ status: 'active' })
        archivedTeam = { ...archivedTeam, status: 'active' }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ team: archivedTeam }) })
      }
      if (url === '/session/teams/team_archived_1') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            team: archivedTeam,
            members: [{
              id: 'tmem_archived_1',
              role: 'admin',
              capabilities: adminCapabilities,
              display_name: 'Nona',
              status: 'active',
              is_current: true,
            }],
            invites: [],
            recovery_codes: [{
              id: 'trec_archived_1',
              created_at: '2026-05-28T00:00:00+00:00',
            }],
          }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const { activateOptionsTab } = await loadAppFns({
      apiFetch,
      sessionId: 'tok_options_team_reactivate',
      showConfirm,
      showToast,
    })

    activateOptionsTab('teams')
    await vi.waitFor(() => expect(document.getElementById('options-teams-list').textContent).toContain('Archive ops'))
    document.querySelector('[data-team-action="select-team"]').click()
    await vi.waitFor(() => {
      expect(document.getElementById('options-team-detail').textContent).toContain('automation stays paused')
    })

    document.querySelector('[data-team-action="reactivate-team"]').click()

    await vi.waitFor(() => {
      expect(showConfirm).toHaveBeenCalled()
      expect(showConfirm.mock.calls[0][0].body.note)
        .toContain('schedules and watchers paused by archival stay paused')
      expect(showToast).toHaveBeenCalledWith('Team reactivated; schedules and watchers remain paused', 'success')
    })
    expect(apiFetch).toHaveBeenCalledWith(
      '/session/teams/team_archived_1',
      expect.objectContaining({ method: 'PATCH' })
    )
  })

  it('switches the visible prompt into confirmation mode when requested', async () => {
    const { setComposerPromptMode, syncShellPrompt } = await loadAppFns()
    const shellPromptWrap = document.getElementById('shell-prompt-wrap')
    const promptPrefix = shellPromptWrap.querySelector('.prompt-prefix')
    const mobilePromptLabel = document.querySelector('#mobile-composer-row .mobile-prompt-label')

    expect(promptPrefix.textContent).toBe('anon@darklab.sh:/ $')
    expect(mobilePromptLabel.textContent).toBe('')
    expect(mobilePromptLabel.hidden).toBe(true)
    expect(document.getElementById('mobile-cmd').placeholder).toBe('/ · type command')

    setComposerPromptMode('confirm')
    expect(promptPrefix.textContent).toBe('[yes/no]:')
    expect(mobilePromptLabel.textContent).toBe('[yes/no]:')
    expect(mobilePromptLabel.hidden).toBe(false)
    expect(document.getElementById('mobile-cmd').placeholder).toBe('')
    expect(shellPromptWrap.classList.contains('shell-prompt-confirm')).toBe(true)

    setComposerPromptMode('secret')
    document.getElementById('cmd').value = 'private-value'
    syncShellPrompt()
    expect(promptPrefix.textContent).toBe('[hidden]:')
    expect(document.getElementById('cmd').type).toBe('password')
    expect(document.getElementById('mobile-cmd').type).toBe('password')
    expect(document.getElementById('shell-prompt-text').textContent).not.toContain('private-value')

    setComposerPromptMode(null)
    expect(promptPrefix.textContent).toBe('anon@darklab.sh:/ $')
    expect(mobilePromptLabel.textContent).toBe('')
    expect(mobilePromptLabel.hidden).toBe(true)
    expect(document.getElementById('mobile-cmd').placeholder).toBe('/ · type command')
    expect(shellPromptWrap.classList.contains('shell-prompt-confirm')).toBe(false)
    expect(document.getElementById('cmd').type).toBe('text')
  })

  it('applies the saved prompt username preference to the live prompt', async () => {
    const showToast = vi.fn()
    await loadAppFns({
      cookies: { pref_prompt_username: 'nona' },
      setTimeout: globalThis.setTimeout,
      clearTimeout: globalThis.clearTimeout,
      showToast,
    })
    const promptPrefix = document.querySelector('#shell-prompt-wrap .prompt-prefix')
    const input = document.getElementById('options-prompt-username-input')
    expect(promptPrefix.textContent).toBe('nona@darklab.sh:/ $')
    expect(input.value).toBe('nona')
    expect(input.getAttribute('aria-label')).toBe('Prompt name')
    expect(input.getAttribute('data-bwignore')).toBe('true')
    expect(input.getAttribute('data-1p-ignore')).toBe('true')
    expect(input.getAttribute('data-lpignore')).toBe('true')

    input.value = 'ops-user'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await new Promise(resolve => setTimeout(resolve, 550))

    expect(promptPrefix.textContent).toContain('ops-user@darklab.sh:')
    expect(document.cookie).toContain('pref_prompt_username=ops-user')
    expect(showToast).toHaveBeenCalledWith('Prompt name saved', 'success')
  })

  it('shows live validation for invalid prompt username input without saving it', async () => {
    await loadAppFns({
      cookies: { pref_prompt_username: 'nona' },
    })
    const input = document.getElementById('options-prompt-username-input')
    const error = document.getElementById('options-prompt-username-error')

    input.value = 'bad/path'
    input.dispatchEvent(new Event('input', { bubbles: true }))

    expect(input.getAttribute('aria-invalid')).toBe('true')
    expect(error.classList.contains('u-hidden')).toBe(false)

    input.dispatchEvent(new Event('change', { bubbles: true }))

    expect(document.querySelector('#shell-prompt-wrap .prompt-prefix').textContent).toBe('nona@darklab.sh:/ $')
    expect(document.cookie).toContain('pref_prompt_username=nona')

    input.value = 'good_user'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    input.dispatchEvent(new Event('change', { bubbles: true }))

    expect(input.getAttribute('aria-invalid')).toBe('false')
    expect(error.classList.contains('u-hidden')).toBe(true)
    expect(document.querySelector('#shell-prompt-wrap .prompt-prefix').textContent).toBe('good_user@darklab.sh:/ $')
    expect(document.cookie).toContain('pref_prompt_username=good_user')
  })

  it('uses a compact cwd placeholder instead of the mobile prompt label', async () => {
    const { setComposerPromptMode } = await loadAppFns({
      workspaceCwd: 'very/deep/reports/nuclei-output',
    })
    const mobilePromptLabel = document.querySelector('#mobile-composer-row .mobile-prompt-label')
    const mobileCmd = document.getElementById('mobile-cmd')

    expect(mobilePromptLabel.textContent).toBe('')
    expect(mobilePromptLabel.hidden).toBe(true)
    expect(mobileCmd.placeholder).toBe('.../nuclei-output · type command')

    setComposerPromptMode('confirm')
    setComposerPromptMode(null)

    expect(mobileCmd.placeholder).toBe('.../nuclei-output · type command')
  })

  it('refreshes the visible prompt path when workspace cwd changes', async () => {
    let workspaceCwd = ''
    const { syncShellPrompt } = await loadAppFns({
      workspaceCwd: () => workspaceCwd,
    })
    const promptPrefix = document.querySelector('#shell-prompt-wrap .prompt-prefix')
    const mobileCmd = document.getElementById('mobile-cmd')

    expect(promptPrefix.textContent).toBe('anon@darklab.sh:/ $')
    expect(mobileCmd.placeholder).toBe('/ · type command')

    workspaceCwd = 'reports/nuclei'
    syncShellPrompt()

    expect(promptPrefix.textContent).toBe('anon@darklab.sh:/reports/nuclei $')
    expect(mobileCmd.placeholder).toBe('/reports/nuclei · type command')
  })

  it('_setTsMode updates body classes and button labels', async () => {
    const { _setTsMode } = await loadAppFns()

    _setTsMode('elapsed')

    expect(document.body.classList.contains('ts-elapsed')).toBe(true)
    expect(document.body.classList.contains('ts-clock')).toBe(false)
    expect(document.getElementById('ts-btn').textContent).toBe('timestamps: elapsed')
    expect(document.getElementById('ln-btn').textContent).toBe('line numbers')
  })

  it('_setLnMode updates body classes and button labels', async () => {
    const { _setLnMode } = await loadAppFns()

    _setLnMode('on')

    expect(document.body.classList.contains('ln-on')).toBe(true)
    expect(document.getElementById('ln-btn').textContent).toBe('line numbers')

    _setLnMode('off')

    expect(document.body.classList.contains('ln-on')).toBe(false)
    expect(document.getElementById('ln-btn').textContent).toBe('line numbers')
  })

  it('allows timestamps and line numbers to be enabled at the same time', async () => {
    const { _setLnMode, _setTsMode } = await loadAppFns()

    _setLnMode('on')
    _setTsMode('elapsed')

    expect(document.body.classList.contains('ln-on')).toBe(true)
    expect(document.body.classList.contains('ts-elapsed')).toBe(true)
    expect(document.getElementById('ln-btn').textContent).toBe('line numbers')
    expect(document.getElementById('ts-btn').textContent).toBe('timestamps: elapsed')
  })

  it('refocuses the terminal input after toggling timestamps and line numbers', async () => {
    const { cmdInput } = await loadAppFns()

    document.getElementById('ts-btn').click()
    expect(cmdInput.focus).toHaveBeenCalled()

    cmdInput.focus.mockClear()
    document.getElementById('ln-btn').click()
    expect(cmdInput.focus).toHaveBeenCalled()

    cmdInput.focus.mockClear()
    document.querySelector('#mobile-menu-sheet [data-menu-action="ts-set"][data-ts-mode="elapsed"]').click()
    expect(cmdInput.focus).toHaveBeenCalled()

    cmdInput.focus.mockClear()
    document.querySelector('#mobile-menu-sheet [data-menu-action="ln"]').click()
    expect(cmdInput.focus).toHaveBeenCalled()
  })

  it('ts-toggle does not close the mobile sheet (disclosure in mobile_chrome.js owns the submenu toggle)', async () => {
    await loadAppFns()
    const sheet = document.getElementById('mobile-menu-sheet')
    const toggle = sheet.querySelector('[data-menu-action="ts-toggle"]')

    sheet.classList.remove('u-hidden')
    // Controller dispatch is a no-op for ts-toggle and skips hideMobileMenu
    // in the real button click path; the inline submenu's aria-expanded /
    // u-hidden lifecycle moved to bindDisclosure in mobile_chrome.js (covered
    // in ui_disclosure.test.js). What this test still guarantees is that the
    // ts-toggle click does not cascade into closing the parent sheet.
    toggle.click()
    expect(sheet.classList.contains('u-hidden')).toBe(false)
  })

  it('ts-set applies the selected mode and closes the sheet', async () => {
    const { _setTsMode } = await loadAppFns()
    _setTsMode('off')
    const sheet = document.getElementById('mobile-menu-sheet')
    sheet.classList.remove('u-hidden')

    document
      .querySelector('#mobile-menu-sheet [data-menu-action="ts-set"][data-ts-mode="clock"]')
      .click()

    expect(document.body.classList.contains('ts-clock')).toBe(true)
    expect(sheet.classList.contains('u-hidden')).toBe(true)
  })

  it('clear cancels welcome, clears the active tab preserving run state, and closes the sheet', async () => {
    const clearTabSpy = vi.fn()
    const cancelWelcomeSpy = vi.fn()
    await loadAppFns({
      clearTab: clearTabSpy,
      cancelWelcome: cancelWelcomeSpy,
      activeTabId: 'tab-1',
    })
    const sheet = document.getElementById('mobile-menu-sheet')
    sheet.classList.remove('u-hidden')

    document.querySelector('#mobile-menu-sheet [data-menu-action="clear"]').click()

    expect(cancelWelcomeSpy).toHaveBeenCalledWith('tab-1')
    expect(clearTabSpy).toHaveBeenCalledWith('tab-1', { preserveRunState: true })
    expect(sheet.classList.contains('u-hidden')).toBe(true)
  })

  it('opens Atlas surfaces and Status Monitor from the mobile menu and closes the sheet', async () => {
    const openStatusMonitor = vi.fn(() => Promise.resolve(true))
    const openAtlas = vi.fn(() => Promise.resolve(true))
    const openAtlasQuickLookup = vi.fn(() => Promise.resolve(true))
    await loadAppFns({ openStatusMonitor, openAtlas, openAtlasQuickLookup })
    const sheet = document.getElementById('mobile-menu-sheet')
    sheet.classList.remove('u-hidden')

    document.querySelector('#mobile-menu-sheet [data-menu-action="atlas"]').click()
    expect(openAtlas).toHaveBeenCalledWith({ source: 'mobile-menu' })

    sheet.classList.remove('u-hidden')
    document.querySelector('#mobile-menu-sheet [data-menu-action="quick-lookup"]').click()
    expect(openAtlasQuickLookup).toHaveBeenCalledWith({ source: 'mobile-menu', toggle: true })

    sheet.classList.remove('u-hidden')
    document.querySelector('#mobile-menu-sheet [data-menu-action="status-monitor"]').click()

    expect(openStatusMonitor).toHaveBeenCalledWith({ source: 'mobile-menu' })
    expect(sheet.classList.contains('u-hidden')).toBe(true)
  })

  it('opens the theme selector from the theme button', async () => {
    const { openThemeSelector } = await loadAppFns({
      themeRegistry: {
        current: {
          name: 'theme_light_blue',
          label: 'Apricot Sand',
          source: 'variant',
          vars: { '--bg': '#9ab7d0' },
        },
        themes: [
          {
            name: 'theme_light_blue',
            label: 'Apricot Sand',
            source: 'variant',
            vars: { '--bg': '#9ab7d0' },
          },
          {
            name: 'theme_light_olive',
            label: 'Olive Parchment',
            source: 'variant',
            vars: { '--bg': '#c0c0a8' },
          },
        ],
      },
    })

    openThemeSelector()
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(document.getElementById('theme-overlay').classList.contains('open')).toBe(true)
    expect(document.querySelector('#theme-select .theme-card-active')).toBe(document.activeElement)
  })

  it('populates the theme select from the registry and applies the selected theme', async () => {
    const themeRegistry = {
      current: {
        name: 'theme_light_blue',
        label: 'Apricot Sand',
        source: 'variant',
        vars: { '--bg': '#9ab7d0' },
      },
      themes: [
        {
          name: 'theme_light_blue',
          label: 'Apricot Sand',
          source: 'variant',
          vars: { '--bg': '#9ab7d0' },
        },
        {
          name: 'theme_light_olive',
          label: 'Olive Parchment',
          source: 'variant',
          vars: { '--bg': '#c0c0a8' },
        },
      ],
    }

    await loadAppFns({ themeRegistry })

    const themeSelect = document.getElementById('theme-select')
    expect(themeSelect).not.toBeNull()
    const themeCards = Array.from(themeSelect.querySelectorAll('[data-theme-name]'))
    expect(themeCards.map((card) => card.dataset.themeName)).toEqual([
      'theme_light_blue',
      'theme_light_olive',
    ])
    expect(themeCards.map((card) => card.querySelector('.theme-card-label')?.textContent)).toEqual([
      'Apricot Sand',
      'Olive Parchment',
    ])

    themeSelect.querySelector('[data-theme-name="theme_light_blue"]').click()

    expect(document.body.dataset.theme).toBe('theme_light_blue')
    expect(document.cookie).toContain('pref_theme_name=theme_light_blue')

    themeSelect.querySelector('[data-theme-name="theme_light_olive"]').click()

    expect(document.body.dataset.theme).toBe('theme_light_olive')
    expect(document.cookie).toContain('pref_theme_name=theme_light_olive')
  })

  it('renders theme preview cards with the current desktop shell structure', async () => {
    await loadAppFns({
      themeRegistry: {
        current: {
          name: 'darklab_obsidian',
          label: 'Darklab Obsidian',
          source: 'variant',
          vars: {
            '--theme-chrome-bg': '#050505',
            '--theme-panel-bg': '#111111',
            '--theme-tab-active-bg': '#1a1a1a',
          },
        },
        themes: [
          {
            name: 'darklab_obsidian',
            label: 'Darklab Obsidian',
            source: 'variant',
            vars: {
              '--theme-chrome-bg': '#050505',
              '--theme-panel-bg': '#111111',
              '--theme-tab-active-bg': '#1a1a1a',
            },
          },
        ],
      },
    })

    const card = document.querySelector('#theme-select .theme-card')
    expect(card?.style.getPropertyValue('--theme-chrome-bg')).toBe('#050505')
    expect(card?.querySelector('.theme-card-preview-rail')).not.toBeNull()
    expect(card?.querySelector('.theme-card-preview-tab-active')).not.toBeNull()
    expect(card?.querySelector('.theme-card-preview-content')).not.toBeNull()
    expect(card?.querySelector('.theme-card-preview-hud')).not.toBeNull()
    expect(card?.querySelectorAll('.theme-card-preview-rail-section')).toHaveLength(3)
    expect(card?.querySelector('.theme-card-preview-modal')).not.toBeNull()
    expect(card?.querySelectorAll('.theme-card-preview-modal-button')).toHaveLength(2)
    expect(card?.querySelectorAll('.theme-card-preview-line')).toHaveLength(4)
    expect(card?.querySelector('.theme-card-preview-bar')).toBeNull()
    expect(card?.querySelector('.theme-card-preview-pill')).toBeNull()
    expect(card?.querySelector('.theme-card-preview-chip')).toBeNull()
    expect(card?.querySelector('.theme-card-preview-drawer')).toBeNull()
  })

  it('renders shipped theme preview cards with populated core surface tokens', async () => {
    const registry = shippedThemeRegistry()
    await loadAppFns({ themeRegistry: registry })

    const cards = Array.from(document.querySelectorAll('#theme-select .theme-card'))
    expect(cards).toHaveLength(registry.themes.length)

    cards.forEach(card => {
      const theme = registry.themes.find(item => item.name === card.dataset.themeName)
      expect(theme, `missing registry theme for ${card.dataset.themeName}`).toBeTruthy()
      ;[
        '--bg',
        '--surface',
        '--theme-panel-bg',
        '--theme-chrome-bg',
        '--theme-modal-bg',
        '--theme-tab-active-bg',
        '--theme-button-secondary-bg',
        '--theme-button-secondary-border',
        '--theme-dropdown-bg',
        '--theme-dropdown-border',
      ].forEach(token => {
        expect(card.style.getPropertyValue(token), `${theme.name} missing ${token}`).not.toBe('')
      })
      expect(card.querySelector('.theme-card-preview-rail')).not.toBeNull()
      expect(card.querySelector('.theme-card-preview-hud')).not.toBeNull()
      expect(card.querySelector('.theme-card-preview-content')).not.toBeNull()
      expect(card.querySelector('.theme-card-preview-modal')).not.toBeNull()
    })
  })

  it('applies a theme from the terminal theme command', async () => {
    const { handleThemeCommand } =
      await loadAppFns({
        themeRegistry: {
          current: {
            name: 'theme_light_blue',
            label: 'Apricot Sand',
            source: 'variant',
            vars: { '--bg': '#9ab7d0' },
          },
          themes: [
            {
              name: 'theme_light_blue',
              label: 'Apricot Sand',
              source: 'variant',
              vars: { '--bg': '#9ab7d0' },
            },
            {
              name: 'theme_light_olive',
              label: 'Olive Parchment',
              source: 'variant',
              vars: { '--bg': '#c0c0a8' },
            },
          ],
        },
      })
    const execution = createBrowserCommandExecution('theme set theme_light_olive')

    await handleThemeCommand('theme set theme_light_olive', 'tab-1', execution)

    expect(document.body.dataset.theme).toBe('theme_light_olive')
    expect(document.cookie).toContain('pref_theme_name=theme_light_olive')
    expect(execution.state.recordRecent).toBe(true)
    expect(execution.state.status).toBe('ok')
  })

  it('groups terminal theme list output by color scheme', async () => {
    const { handleThemeCommand } =
      await loadAppFns({
        themeRegistry: {
          current: {
            name: 'darklab_obsidian',
            label: 'Darklab Obsidian',
            color_scheme: 'only dark',
            source: 'variant',
            vars: { '--bg': '#111111' },
          },
          themes: [
            {
              name: 'darklab_obsidian',
              label: 'Darklab Obsidian',
              color_scheme: 'only dark',
              source: 'variant',
              vars: { '--bg': '#111111' },
            },
            {
              name: 'theme_light_blue',
              label: 'Apricot Sand',
              color_scheme: 'only light',
              source: 'variant',
              vars: { '--bg': '#9ab7d0' },
            },
            {
              name: 'theme_unknown',
              label: 'Unknown Scheme',
              source: 'variant',
              vars: { '--bg': '#999999' },
            },
          ],
        },
      })
    const execution = createBrowserCommandExecution('theme list')

    await handleThemeCommand('theme list', 'tab-1', execution)

    const output = execution.state.lines.map(line => line.text)
    expect(output).toEqual([
      'current theme       Darklab Obsidian (current)',
      '',
      'Available themes:',
      'Dark themes:',
      '  * darklab_obsidian          Darklab Obsidian',
      'Light themes:',
      '    theme_light_blue          Apricot Sand',
      'Other themes:',
      '    theme_unknown             Unknown Scheme',
    ])
    expect(execution.state.recordRecent).toBe(true)
    expect(execution.state.status).toBe('ok')
  })

  it('requires explicit set before applying a theme from the terminal theme command', async () => {
    const { handleThemeCommand } =
      await loadAppFns({
        themeRegistry: {
          current: {
            name: 'theme_light_blue',
            label: 'Apricot Sand',
            source: 'variant',
            vars: { '--bg': '#9ab7d0' },
          },
          themes: [
            {
              name: 'theme_light_blue',
              label: 'Apricot Sand',
              source: 'variant',
              vars: { '--bg': '#9ab7d0' },
            },
            {
              name: 'theme_light_olive',
              label: 'Olive Parchment',
              source: 'variant',
              vars: { '--bg': '#c0c0a8' },
            },
          ],
        },
      })
    const execution = createBrowserCommandExecution('theme theme_light_olive')

    await handleThemeCommand('theme theme_light_olive', 'tab-1', execution)

    expect(document.body.dataset.theme).toBe('theme_light_blue')
    expect(execution.state.recordRecent).toBe(false)
    expect(execution.state.status).toBe('fail')
  })

  it('updates user options from the terminal config command', async () => {
    const { handleConfigCommand } =
      await loadAppFns({
        cookies: {
          pref_line_numbers: 'off',
          pref_timestamps: 'off',
          pref_welcome_intro: 'animated',
          pref_project_auto_link_external_runs: 'on',
          pref_project_auto_link_run_entities: 'on',
          pref_command_outcome_summaries: 'on',
          pref_prompt_username: '',
          pref_compare_view_mode: 'auto',
          pref_compare_context: '3',
          pref_tour_seen_version: '',
        },
      })
    const commands = [
      'config set line-numbers on',
      'config set welcome static',
      'config set project-auto-link-runs off',
      'config set project-auto-link-run-entities off',
      'config set command-outcome-summaries off',
      'config set prompt-username nona',
      'config set compare-view changes-only',
      'config set compare-context all',
      'config get project-auto-link-run-entities',
      'config get command-outcome-summaries',
      'config get prompt-username',
      'config list',
    ]
    const executions = []
    for (const command of commands) {
      const execution = createBrowserCommandExecution(command)
      executions.push(execution)
      await handleConfigCommand(command, 'tab-1', execution)
    }

    expect(document.body.classList.contains('ln-on')).toBe(true)
    expect(document.cookie).toContain('pref_line_numbers=on')
    expect(document.cookie).toContain('pref_welcome_intro=disable_animation')
    expect(document.cookie).toContain('pref_project_auto_link_external_runs=off')
    expect(document.cookie).toContain('pref_project_auto_link_run_entities=off')
    expect(document.cookie).toContain('pref_command_outcome_summaries=off')
    expect(document.cookie).toContain('pref_prompt_username=nona')
    expect(document.cookie).toContain('pref_compare_view_mode=changes_only')
    expect(document.cookie).toContain('pref_compare_context=all')
    expect(document.querySelector('#shell-prompt-wrap .prompt-prefix').textContent).toBe('nona@darklab.sh:~ $')
    expect(executions.every(execution => execution.state.recordRecent)).toBe(true)
    expect(executions.every(execution => execution.state.status === 'ok')).toBe(true)
    const configLines = executions.at(-1).state.lines
    const configHeader = configLines.find(line => line.cls === 'builtin-table-header')
    const configRows = configLines
      .filter(line => line.cls === 'builtin-table-row')
      .map(line => line.text)
    expect(configHeader?.text).toMatch(/^option\s+value$/)
    expect(configRows).toEqual(expect.arrayContaining([
      expect.stringMatching(/^project-auto-link-run-entities\s+off$/),
      expect.stringMatching(/^command-outcome-summaries\s+off$/),
    ]))
  })

  it('requires explicit set before updating user options from the terminal config command', async () => {
    const { handleConfigCommand } =
      await loadAppFns({
        cookies: {
          pref_line_numbers: 'off',
        },
      })
    const missingSetExecution = createBrowserCommandExecution('config line-numbers on')
    const invalidValueExecution = createBrowserCommandExecution('config set prompt-username bad/path')

    await handleConfigCommand('config line-numbers on', 'tab-1', missingSetExecution)
    await handleConfigCommand('config set prompt-username bad/path', 'tab-1', invalidValueExecution)

    expect(document.body.classList.contains('ln-on')).toBe(false)
    expect(document.cookie).not.toContain('pref_line_numbers=on')
    expect(document.cookie).not.toContain('pref_prompt_username=bad')
    expect(missingSetExecution.state.recordRecent).toBe(false)
    expect(invalidValueExecution.state.recordRecent).toBe(false)
    expect(missingSetExecution.state.status).toBe('fail')
    expect(invalidValueExecution.state.status).toBe('fail')
  })

  it('keeps config command output pinned to the tail when the tab is already following', async () => {
    const output = document.createElement('div')
    let scrollTop = 0
    Object.defineProperty(output, 'scrollHeight', { configurable: true, get: () => 500 })
    Object.defineProperty(output, 'scrollTop', {
      configurable: true,
      get: () => scrollTop,
      set: (value) => {
        scrollTop = value
      },
    })
    const tab = { id: 'tab-1', followOutput: true, rawLines: [] }
    const { handleConfigCommand } = await loadAppFns({
      tabs: [tab],
      getOutput: () => output,
      cookies: {
        pref_welcome_intro: 'animated',
        pref_hud_clock: 'utc',
      },
    })

    await handleConfigCommand(
      'config set welcome static',
      'tab-1',
      createBrowserCommandExecution('config set welcome static'),
    )
    scrollTop = 0
    await handleConfigCommand(
      'config set hud-clock local',
      'tab-1',
      createBrowserCommandExecution('config set hud-clock local'),
    )

    expect(tab.followOutput).toBe(true)
    expect(scrollTop).toBe(500)
  })

  async function advanceTerminalTour(output, pendingTour, chapterCount) {
    const promptCount = output.querySelectorAll('.builtin-tour-prompt').length
    for (let index = 0; index < chapterCount; index += 1) {
      await vi.waitFor(() => {
        expect(output.querySelectorAll('.builtin-tour-prompt')).toHaveLength(promptCount + index + 1)
      })
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }))
    }
    await pendingTour
  }

  it('renders the guided terminal tour, records it once, and opens sample chips in a new tab', async () => {
    const output = document.createElement('div')
    const tourConfig = {
      workspace_enabled: true,
      tour_enabled: true,
      tour_version: 3,
      tour_chapters: [
        {
          id: 'running_commands',
          title: 'Running commands',
          summary: 'Run something useful.\nCapture the output.',
          sample: 'dig darklab.sh A',
        },
        {
          id: 'interactive_pty',
          title: 'Interactive tools',
          summary: 'Open supported interactive tools.',
          sample: 'mtr --interactive darklab.sh',
        },
      ],
    }
    const apiFetch = vi.fn((url, opts = {}) => {
      if (url === '/config') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(tourConfig) })
      }
      if (url === '/session/tour-seen') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            ok: true,
            tour_version: 3,
            preferences: { pref_tour_seen_version: 3 },
          }),
        })
      }
      if (url === '/session/preferences' && (!opts.method || opts.method === 'GET')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ preferences: {} }) })
      }
      if (url === '/session/preferences' && opts.method === 'POST') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const submitVisibleComposerCommand = vi.fn()
    const createTab = vi.fn(() => 'tab-tour-sample')
    const activateTab = vi.fn()
    const {
      handleTourCommand,
      getTourSeenVersionPreference,
    } = await loadAppFns({
      apiFetch,
      getOutput: () => output,
      submitVisibleComposerCommand,
      createTab,
      activateTab,
      appConfig: tourConfig,
    })

    const firstExecution = createBrowserCommandExecution('tour')
    const secondExecution = createBrowserCommandExecution('tour')
    await advanceTerminalTour(output, handleTourCommand('tour', 'tab-1', firstExecution), 2)
    await advanceTerminalTour(output, handleTourCommand('tour', 'tab-1', secondExecution), 2)

    expect(output.textContent).toContain('Running commands')
    expect(output.textContent).toContain('Capture the output.')
    expect(output.textContent).toContain('Interactive tools')
    expect(output.textContent).toContain('Press any key to continue, or press q to quit the tour.')
    const chips = output.querySelectorAll('.faq-chip[data-faq-command]')
    expect(chips).toHaveLength(4)
    chips[0].dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(createTab).toHaveBeenCalled()
    expect(activateTab).toHaveBeenCalledWith('tab-tour-sample')
    expect(document.getElementById('cmd').value).toBe('dig darklab.sh A')
    expect(submitVisibleComposerCommand).not.toHaveBeenCalled()
    expect(getTourSeenVersionPreference()).toBe(3)
    expect(apiFetch.mock.calls.filter(([url]) => url === '/session/tour-seen')).toHaveLength(1)
    expect(firstExecution.state.status).toBe('ok')
    expect(secondExecution.state.status).toBe('ok')
    expect(firstExecution.state.recordRecent).toBe(true)
    expect(secondExecution.state.recordRecent).toBe(true)
  })

  it('omits the interactive tools chapter from the terminal tour on mobile', async () => {
    const output = document.createElement('div')
    const tourConfig = {
      workspace_enabled: true,
      tour_enabled: true,
      tour_version: 1,
      tour_chapters: [
        {
          id: 'running_commands',
          title: 'Running commands',
          summary: 'Run something useful.',
          sample: 'dig darklab.sh A',
        },
        {
          id: 'interactive_pty',
          title: 'Interactive tools',
          summary: 'Open supported interactive tools.',
          sample: 'mtr --interactive darklab.sh',
        },
      ],
    }
    const { handleTourCommand, restoreViewport } = await loadAppFns({
      apiFetch: (url) => {
        if (url === '/config') return Promise.resolve({ ok: true, json: () => Promise.resolve(tourConfig) })
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
      },
      getOutput: () => output,
      mobileViewport: { width: 390, height: 844 },
      appConfig: tourConfig,
    })
    try {
      const execution = createBrowserCommandExecution('tour')
      await advanceTerminalTour(output, handleTourCommand('tour', 'tab-1', execution), 1)
      expect(output.textContent).toContain('Running commands')
      expect(output.textContent).not.toContain('Interactive tools')
      expect(execution.state.status).toBe('ok')
    } finally {
      restoreViewport()
    }
  })

  it('serves runtime autocomplete context for theme and config values', async () => {
    const { getRuntimeAutocompleteContext } = await loadAppFns({
      themeRegistry: {
        current: {
          name: 'theme_light_blue',
          label: 'Apricot Sand',
          source: 'variant',
          vars: { '--bg': '#9ab7d0' },
        },
        themes: [
          {
            name: 'theme_light_blue',
            label: 'Apricot Sand',
            source: 'variant',
            vars: { '--bg': '#9ab7d0' },
          },
          {
            name: 'theme_light_olive',
            label: 'Olive Parchment',
            source: 'variant',
            vars: { '--bg': '#c0c0a8' },
          },
        ],
      },
      sessionVariables: [
        { name: 'HOST', value: 'ip.darklab.sh' },
      ],
    })
    const context = getRuntimeAutocompleteContext(builtInAutocompleteBase())

    expect(context.theme.arg_hints.__positional__.map(item => item.value)).toEqual(['list', 'current', 'set'])
    expect(context.theme.arg_hints.set.map(item => item.value)).toContain('theme_light_olive')
    expect(context.theme.arg_hints.set.find(item => item.value === 'theme_light_blue')?.description)
      .toContain('(current)')
    expect(context.config.arg_hints.__positional__.map(item => item.value)).toEqual(['list', 'get', 'set'])
    expect(context.config.arg_hints.set.map(item => item.value)).toContain('prompt-username')
    expect(context.config.arg_hints.set.map(item => item.value)).toContain('compare-view')
    expect(context.config.arg_hints.set.map(item => item.value)).toContain('command-outcome-summaries')
    expect(context.config.sequence_arg_hints['set line-numbers'].map(item => item.value)).toEqual(['on', 'off'])
    expect(context.config.sequence_arg_hints['set command-outcome-summaries'].map(item => item.value)).toEqual(['on', 'off'])
    expect(context.config.sequence_arg_hints['set compare-view'].map(item => item.value)).toEqual([
      'auto',
      'side-by-side',
      'unified',
      'changes-only',
      'findings-only',
    ])
    expect(context.config.sequence_arg_hints['set compare-context'].map(item => item.value)).toEqual(['3', '10', 'all'])
    expect(context.config.sequence_arg_hints['set prompt-username'].map(item => item.value)).toEqual(['<username> | default'])
    expect(context.var.arg_hints.__positional__.map(item => item.value)).toEqual(['list', 'set', 'unset'])
    expect(context.var.arg_hints.set.filter(item => item.value === 'HOST')).toEqual([
      { value: 'HOST', description: 'Current value: ip.darklab.sh' },
    ])
    expect(context.var.arg_hints.set.map(item => item.value)).toEqual(['HOST', 'PORT', 'IP_ADDR'])
    expect(context.var.sequence_arg_hints['set host'].map(item => item.value)).toEqual(['<value>'])
    expect(context.var.sequence_arg_hints['unset host']).toEqual([])
    expect(context.var.close_after).toEqual({ list: 0, set: 2, unset: 1 })
  })

  it('serves workflow names and variable flags in runtime autocomplete context', async () => {
    const { getRuntimeAutocompleteContext, renderWorkflowItems } = await loadAppFns()
    renderWorkflowItems([
      {
        id: 'usr_abcd',
        source: 'user',
        title: 'DNS Check',
        description: 'Custom DNS workflow',
        inputs: [
          { id: 'domain', label: 'Domain', type: 'domain', required: true, placeholder: 'example.com', default: '', help: '' },
          { id: 'ports', label: 'Ports', type: 'port_set', required: false, placeholder: '', default: '80,443', help: '' },
          { id: 'wordlist', label: 'Wordlist', type: 'wordlist', required: false, placeholder: '', default: '', help: '' },
          { id: 'input_file', label: 'Input file', type: 'workspace_path', required: false, placeholder: '', default: '', help: '' },
        ],
        steps: [{ cmd: 'dig {{domain}} A -p {{ports}} {{wordlist}} {{input_file}}', note: '' }],
      },
    ], { emitCatalogEvent: false })

    const context = getRuntimeAutocompleteContext(builtInAutocompleteBase())

    expect(context.workflow.arg_hints.__positional__.map(item => item.value)).toEqual([
      'list', 'show', 'run', 'runs', 'status', 'cancel',
    ])
    expect(context.workflow.arg_hints.run.map(item => item.value)).toEqual(['dns-check'])
    expect(context.workflow.sequence_arg_hints['run dns-check'].map(item => item.value)).toEqual([
      '--domain', '--ports', '--wordlist', '--input-file',
    ])
    expect(context.workflow.arg_hints['--domain'][0].value_type).toBe('domain')
    expect(context.workflow.arg_hints['--ports'][0].value_type).toBe('port_set')
    expect(context.workflow.arg_hints['--wordlist'][0].value_type).toBe('wordlist')
    expect(context.workflow.arg_hints['--input-file'][0].value_type).toBe('workspace_path')
  })

  it('offers project, recent, Files, and packaged wordlist values for workflow parameters', async () => {
    const refreshWorkspaceFileCache = vi.fn(() => Promise.resolve())
    const { renderWorkflowItems, workflowInputSourceOptions } = await loadAppFns({
      refreshWorkspaceFileCache,
      readProjectTargets: () => [
        { type: 'domain', value: 'project.darklab.sh' },
        { type: 'cidr', value: '192.0.2.0/24' },
      ],
      readRecentValues: () => ({
        domain: ['recent.darklab.sh'],
        ip: ['192.0.2.10'],
        url: [],
        port_set: [],
      }),
      getWorkspaceAutocompleteFileHints: () => [{ value: 'lists/hosts.txt' }],
    })
    window.APP_STATE_API.getState().acWordlists = [{
      value: '/usr/share/wordlists/seclists/Discovery/DNS/subdomains-top1million-5000.txt',
      description: 'Installed wordlist',
    }]
    expect(workflowInputSourceOptions({ type: 'target' }).map(item => item.value)).toEqual([
      'project.darklab.sh', '192.0.2.0/24', 'recent.darklab.sh', '192.0.2.10',
    ])
    document.getElementById('workflows-overlay').innerHTML = '<div class="workflows-body"></div>'
    renderWorkflowItems([{
      id: 'usr_parameter_sources',
      source: 'user',
      version: 2,
      title: 'Parameter sources',
      description: '',
      inputs: [
        { id: 'target', label: 'Target', type: 'target', required: true },
        { id: 'wordlist', label: 'Wordlist', type: 'wordlist', required: true },
      ],
      steps: [{
        id: 'scan',
        cmd: 'dnsx -d {{target}} -w {{wordlist}}',
        next: { success: 'complete', failure: 'stop' },
      }],
    }], { emitCatalogEvent: false })

    await vi.waitFor(() => {
      expect(document.querySelector('[data-workflow-input-id="target"]')
        .closest('.workflow-input-field').querySelector('.workflow-input-source-picker')).toBeTruthy()
    })
    await vi.waitFor(() => {
      expect(document.querySelector('[data-workflow-input-id="wordlist"]')
        .closest('.workflow-input-field').querySelector('.workflow-input-source-picker')).toBeTruthy()
    })
    expect(refreshWorkspaceFileCache).toHaveBeenCalled()
    const pickers = document.querySelectorAll('.workflow-input-source-picker')
    expect([...pickers[0].options].map(option => option.value)).toEqual([
      '', 'project.darklab.sh', '192.0.2.0/24', 'recent.darklab.sh', '192.0.2.10',
    ])
    expect([...pickers[1].options].map(option => option.value)).toEqual([
      '',
      'lists/hosts.txt',
      '/usr/share/wordlists/seclists/Discovery/DNS/subdomains-top1million-5000.txt',
    ])

    pickers[0].value = 'project.darklab.sh'
    pickers[0].dispatchEvent(new Event('change', { bubbles: true }))
    expect(document.querySelector('[data-workflow-input-id="target"]').value).toBe('project.darklab.sh')
  })

  it('scopes remembered workflow values and never stores sensitive parameters', async () => {
    const { DarklabTeamScope, renderWorkflowItems, storage } = await loadAppFns()
    const workflow = {
      id: 'usr_remembered_values',
      source: 'user',
      version: 2,
      title: 'Remembered values',
      description: '',
      inputs: [
        { id: 'target', label: 'Target', type: 'target', required: true, sensitive: true },
        { id: 'port', label: 'Port', type: 'port', required: true, default: '80' },
      ],
      steps: [{
        id: 'scan',
        cmd: 'nmap -p {{port}} {{target}}',
        next: { success: 'complete', failure: 'stop' },
      }],
    }
    const render = (item = workflow) => {
      document.getElementById('workflows-overlay').innerHTML = '<div class="workflows-body"></div>'
      renderWorkflowItems([item], { emitCatalogEvent: false })
    }

    storage.setItem('workflow_input_state_v1', JSON.stringify({ stale: { target: 'old.example' } }))
    render()
    const target = document.querySelector('[data-workflow-input-id="target"]')
    const port = document.querySelector('[data-workflow-input-id="port"]')
    expect(target.type).toBe('password')
    expect(port.type).toBe('text')
    target.value = 'private.example'
    target.dispatchEvent(new Event('input', { bubbles: true }))
    port.value = '443'
    port.dispatchEvent(new Event('input', { bubbles: true }))

    const preview = document.querySelector('.workflow-step-cmd')
    const stepRun = document.querySelector('.workflow-step-run')
    expect(preview.textContent).toBe('nmap -p 443 [hidden]')
    expect(preview.textContent).not.toContain('private.example')
    expect(preview.dataset.faqCommand).toBeUndefined()
    expect(stepRun.disabled).toBe(true)
    expect(stepRun.title).toBe('Sensitive values run only with Run all')

    expect(storage.getItem('workflow_input_state_v1')).toBeNull()
    expect(JSON.parse(storage.getItem('workflow_input_state_v2'))).toEqual({
      'personal:session-old::usr_remembered_values': { port: '443' },
    })

    DarklabTeamScope.setActiveTeamId('team_test', {
      persist: false,
      emit: false,
      allowPending: true,
    })
    render()
    expect(document.querySelector('[data-workflow-input-id="target"]').value).toBe('')
    expect(document.querySelector('[data-workflow-input-id="port"]').value).toBe('80')

    DarklabTeamScope.setActiveTeamId('', { persist: false, emit: false })
    render()
    expect(document.querySelector('[data-workflow-input-id="target"]').value).toBe('')
    expect(document.querySelector('[data-workflow-input-id="port"]').value).toBe('443')

    render({ ...workflow, inputs: workflow.inputs.slice(0, 1) })
    expect(JSON.parse(storage.getItem('workflow_input_state_v2'))).toEqual({})
  })

  it('deduplicates workflow subcommands that share runtime insert text', async () => {
    const { getRuntimeAutocompleteContext, renderWorkflowItems } = await loadAppFns()
    renderWorkflowItems([
      {
        id: 'usr_abcd',
        source: 'user',
        title: 'DNS Check',
        description: 'Custom DNS workflow',
        inputs: [],
        steps: [{ cmd: 'dig darklab.sh A', note: '' }],
      },
    ], { emitCatalogEvent: false })
    const registry = builtInAutocompleteBase()
    registry.workflow.arg_hints.__positional__ = [
      { value: 'list', description: 'List workflows' },
      { value: 'show <workflow>', description: 'Show workflow steps', insertValue: 'show ' },
      { value: 'run <workflow>', description: 'Run a workflow', insertValue: 'run ' },
    ]

    const context = getRuntimeAutocompleteContext(registry)

    expect(context.workflow.arg_hints.__positional__.map(item => item.value)).toEqual([
      'list', 'show', 'run', 'runs', 'status', 'cancel',
    ])
    expect(context.workflow.arg_hints.run.map(item => item.value)).toEqual(['dns-check'])
  })

  it('renders saved workflows above built-ins and keeps the workspace open after deletion', async () => {
    let deleted = false
    const showConfirm = vi.fn(async () => 'delete')
    const showToast = vi.fn()
    const builtIns = [
      {
        id: 'builtin:dns',
        source: 'builtin',
        title: 'DNS Troubleshooting',
        description: '',
        inputs: [],
        steps: [{ cmd: 'dig darklab.sh A', note: '' }],
      },
      {
        id: 'builtin:http',
        source: 'builtin',
        title: 'HTTP Triage',
        description: '',
        inputs: [],
        steps: [{ cmd: 'curl -I https://darklab.sh', note: '' }],
      },
    ]
    const apiFetch = vi.fn((url) => {
      if (url === '/workflows') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ items: builtIns }),
        })
      }
      if (url === '/session/workflows/usr_saved') {
        deleted = true
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ deleted: true }) })
      }
      if (url.startsWith('/workflow-executions?')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ executions: [] }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const { renderWorkflowItems, ensureWorkflowCatalogLoaded } = await loadAppFns({
      apiFetch,
      showConfirm,
      showToast,
    })
    document.getElementById('workflows-overlay').innerHTML = '<div class="workflows-body"></div>'

    renderWorkflowItems([
      {
        id: 'usr_saved',
        source: 'user',
        title: 'Saved Recon',
        description: '',
        inputs: [],
        steps: [{ cmd: 'whois darklab.sh', note: '' }],
      },
      ...builtIns,
    ], { emitCatalogEvent: false })

    const labels = [...document.querySelectorAll('.workflow-section-label')].map(el => el.textContent)
    const titles = [...document.querySelectorAll('.workflow-catalog-item-title')].map(el => el.textContent)
    expect(labels).toEqual(['My workflows', 'Built-ins'])
    expect(titles).toEqual(['Saved Recon', 'DNS Troubleshooting', 'HTTP Triage'])
    expect(document.querySelector('.workflow-catalog-item.is-selected')?.classList.contains('selection-row')).toBe(true)
    expect(document.querySelector('.is-user-workflow .workflow-edit-btn')).toBeTruthy()
    const workflowFetchesBefore = apiFetch.mock.calls.filter(([url]) => url === '/workflows').length
    await ensureWorkflowCatalogLoaded()
    const workflowFetchesAfter = apiFetch.mock.calls.filter(([url]) => url === '/workflows').length
    expect(workflowFetchesAfter).toBe(workflowFetchesBefore)

    const overlay = document.getElementById('workflows-overlay')
    overlay.classList.add('open')
    overlay.classList.remove('u-hidden')
    const renderedItems = []
    document.addEventListener('app:workflows-rendered', event => {
      renderedItems.push(event.detail.items)
    }, { once: true })
    document.querySelector('.workflow-delete-btn').click()

    await vi.waitFor(() => expect(deleted).toBe(true))
    await vi.waitFor(() => expect(renderedItems).toHaveLength(1))
    expect(renderedItems[0].map(item => item.id)).toEqual(['builtin:dns', 'builtin:http'])
    expect(overlay.classList.contains('open')).toBe(true)
    expect(document.querySelector('.workflow-title').textContent).toBe('DNS Troubleshooting')
    expect(document.querySelector('[data-workflow-id="usr_saved"]')).toBeNull()
    expect(showConfirm).toHaveBeenCalledOnce()
    expect(showToast).toHaveBeenCalledWith('Workflow deleted')
  })

  it('authors explicit typed parameters and stable step transitions in the workflow editor', async () => {
    const { openWorkflowEditor, payloadFromEditor } = await loadAppFns()
    openWorkflowEditor()

    document.getElementById('workflow-editor-title-input').value = 'Resolve and scan'
    document.getElementById('workflow-editor-add-parameter').click()
    const parameter = document.querySelector('[data-workflow-editor-parameter]')
    parameter.querySelector('.workflow-editor-parameter-id').value = 'target'
    parameter.querySelector('.workflow-editor-parameter-label').value = 'Target'
    parameter.querySelector('.workflow-editor-parameter-type').value = 'target'
    parameter.querySelector('.workflow-editor-parameter-required').checked = true
    parameter.querySelector('.workflow-editor-parameter-sensitive').checked = true
    parameter.querySelector('.workflow-editor-parameter-help').value = 'Domain or IP address'

    const firstStep = document.querySelector('[data-workflow-editor-step]')
    firstStep.querySelector('.workflow-editor-step-id').value = 'resolve'
    firstStep.querySelector('.workflow-editor-step-id').dispatchEvent(new Event('input', { bubbles: true }))
    firstStep.querySelector('.workflow-editor-step-command').value = 'dig +short A {{target}}'
    firstStep.querySelector('.workflow-editor-add-capture').click()
    const capture = firstStep.querySelector('[data-workflow-editor-capture]')
    capture.querySelector('.workflow-editor-capture-name').value = 'resolved_ip'
    capture.querySelector('.workflow-editor-capture-required-input').checked = true
    document.getElementById('workflow-editor-add-step').click()
    const secondStep = document.querySelectorAll('[data-workflow-editor-step]')[1]
    secondStep.querySelector('.workflow-editor-step-id').value = 'scan'
    secondStep.querySelector('.workflow-editor-step-id').dispatchEvent(new Event('input', { bubbles: true }))
    secondStep.querySelector('.workflow-editor-step-command').value = 'nmap -sV {{resolved_ip}}'
    firstStep.querySelector('.workflow-editor-add-exit-code').click()
    const exactRoute = firstStep.querySelector('[data-workflow-editor-exit-code]')
    exactRoute.querySelector('.workflow-editor-exit-code').value = '2'
    exactRoute.querySelector('.workflow-editor-exit-code-destination').value = 'scan'

    const payload = payloadFromEditor()
    expect(payload.version).toBe(2)
    expect(payload.inputs).toEqual([{
      id: 'target',
      label: 'Target',
      type: 'target',
      required: true,
      sensitive: true,
      default: '',
      placeholder: '',
      help: 'Domain or IP address',
    }])
    expect(payload.steps.map(step => step.id)).toEqual(['resolve', 'scan'])
    expect(payload.steps[0].captures).toEqual([{
      name: 'resolved_ip',
      source: 'first_nonempty_line',
      required: true,
    }])
    expect(payload.steps[0].next).toEqual({
      success: 'scan',
      failure: 'stop',
      codes: { 2: 'scan' },
    })
    expect(payload.steps[1].next).toEqual({ success: 'complete', failure: 'stop' })

    openWorkflowEditor({
      id: 'usr_collection_probe',
      source: 'user',
      version: 3,
      title: 'Collect and probe',
      description: 'Probe each captured host.',
      inputs: [],
      steps: [
        {
          id: 'collect',
          cmd: 'discover --json',
          captures: [{
            name: 'hosts',
            kind: 'collection',
            source: 'json_pointer',
            pointer: '/hosts',
            item_limit: 12,
          }],
          next: { success: 'probe', failure: 'stop' },
        },
        {
          id: 'probe',
          cmd: 'httpx -u {{hosts}} -silent',
          for_each: {
            collection: 'hosts',
            failure_mode: 'continue',
            retries: 2,
            max_parallel: 4,
            max_failures: 5,
          },
          next: { success: 'complete', failure: 'stop' },
        },
      ],
    })

    const collectionSteps = document.querySelectorAll('[data-workflow-editor-step]')
    const collectionCapture = collectionSteps[0].querySelector('[data-workflow-editor-capture]')
    expect(collectionCapture.querySelector('.workflow-editor-capture-kind').value).toBe('collection')
    expect(collectionCapture.querySelector('.workflow-editor-capture-item-limit').value).toBe('12')
    expect(collectionCapture.querySelector('.workflow-editor-capture-limit-field').hidden).toBe(false)
    expect(collectionSteps[1].querySelector('.workflow-editor-fanout-enabled').checked).toBe(true)
    expect(collectionSteps[1].querySelector('.workflow-editor-fanout-collection').value).toBe('hosts')
    expect(payloadFromEditor()).toMatchObject({
      version: 3,
      steps: [
        { captures: [{ name: 'hosts', kind: 'collection', item_limit: 12 }] },
        {
          for_each: {
            collection: 'hosts',
            failure_mode: 'continue',
            retries: 2,
            max_parallel: 4,
            max_failures: 5,
          },
        },
      ],
    })
  })

  it('keeps exact exit-code routes visible through step edits and validates route fields', async () => {
    const apiFetch = vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ items: [] }),
    }))
    const { openWorkflowEditor, payloadFromEditor } = await loadAppFns({ apiFetch })
    const initialApiCallCount = apiFetch.mock.calls.length
    openWorkflowEditor({
      id: 'usr_exact_routes',
      source: 'user',
      version: 2,
      title: 'Exact routes',
      description: '',
      inputs: [],
      steps: [
        {
          id: 'probe',
          cmd: 'intel unsupported value',
          next: { codes: { 1: 'inspect', 7: 'stop' }, success: 'complete', failure: 'stop' },
        },
        { id: 'inspect', cmd: 'help', next: { success: 'complete', failure: 'stop' } },
        { id: 'archive', cmd: 'status', next: { success: 'complete', failure: 'stop' } },
      ],
    })

    const probe = document.querySelectorAll('[data-workflow-editor-step]')[0]
    const routes = probe.querySelectorAll('[data-workflow-editor-exit-code]')
    expect([...routes].map(row => row.querySelector('.workflow-editor-exit-code').value))
      .toEqual(['1', '7'])
    expect(routes[0].querySelector('.workflow-editor-exit-code-destination').value).toBe('inspect')

    const inspect = document.querySelectorAll('[data-workflow-editor-step]')[1]
    inspect.querySelector('.workflow-editor-step-id').value = 'analyze'
    inspect.querySelector('.workflow-editor-step-id').dispatchEvent(new Event('input', { bubbles: true }))
    expect(routes[0].querySelector('.workflow-editor-exit-code-destination').value).toBe('analyze')
    inspect.querySelector('.workflow-editor-move-down').click()
    expect(payloadFromEditor().steps.map(step => step.id)).toEqual(['probe', 'archive', 'analyze'])
    expect(payloadFromEditor().steps[0].next.codes).toEqual({ 1: 'analyze', 7: 'stop' })
    routes[1].querySelector('.workflow-editor-exit-code').value = '9'
    routes[1].querySelector('.workflow-editor-exit-code-destination').value = 'archive'
    expect(payloadFromEditor().steps[0].next.codes).toEqual({ 1: 'analyze', 9: 'archive' })
    routes[1].querySelector('.workflow-editor-exit-code').value = '7'
    routes[1].querySelector('.workflow-editor-exit-code-destination').value = 'stop'

    inspect.querySelector('.workflow-editor-remove-step').click()
    const missingDestination = routes[0].querySelector('.workflow-editor-exit-code-destination')
    expect(missingDestination.value).toBe('analyze')
    expect(missingDestination.selectedOptions[0].textContent).toBe('Missing step (analyze)')
    document.getElementById('workflow-editor-form').dispatchEvent(new Event('submit', {
      bubbles: true,
      cancelable: true,
    }))
    expect(apiFetch).toHaveBeenCalledTimes(initialApiCallCount)
    expect(missingDestination.getAttribute('aria-invalid')).toBe('true')
    expect(routes[0].querySelector('[data-workflow-field$="destination"] .form-error').textContent)
      .toBe('Choose an available destination or remove this route.')

    routes[0].querySelector('.workflow-editor-remove-exit-code').click()
    probe.querySelector('.workflow-editor-add-exit-code').click()
    const duplicate = probe.querySelectorAll('[data-workflow-editor-exit-code]')[1]
    duplicate.querySelector('.workflow-editor-exit-code').value = '+07'
    document.getElementById('workflow-editor-form').dispatchEvent(new Event('submit', {
      bubbles: true,
      cancelable: true,
    }))
    expect(apiFetch).toHaveBeenCalledTimes(initialApiCallCount)
    expect(duplicate.querySelector('[data-workflow-field$="code"] .form-error').textContent)
      .toBe('Exit codes must be unique within a step.')

    duplicate.querySelector('.workflow-editor-exit-code').value = 'not-a-code'
    document.getElementById('workflow-editor-form').dispatchEvent(new Event('submit', {
      bubbles: true,
      cancelable: true,
    }))
    expect(duplicate.querySelector('[data-workflow-field$="code"] .form-error').textContent)
      .toBe('Enter a whole-number exit code.')
    duplicate.querySelector('.workflow-editor-remove-exit-code').click()
    expect(payloadFromEditor().steps[0].next.codes).toEqual({ 7: 'stop' })

    openWorkflowEditor({
      id: 'usr_invalid_collection_limits',
      source: 'user',
      version: 3,
      title: 'Invalid collection limits',
      inputs: [],
      steps: [
        {
          id: 'collect',
          cmd: 'discover --json',
          captures: [{
            name: 'hosts', kind: 'collection', source: 'json_pointer',
            pointer: '/hosts', item_limit: 12,
          }],
          next: { success: 'probe', failure: 'stop' },
        },
        {
          id: 'probe',
          cmd: 'httpx -u {{hosts}}',
          for_each: { collection: 'hosts', max_parallel: 2 },
          next: { success: 'complete', failure: 'stop' },
        },
      ],
    })
    const collectionSteps = document.querySelectorAll('[data-workflow-editor-step]')
    collectionSteps[0].querySelector('.workflow-editor-capture-item-limit').value = '33'
    collectionSteps[1].querySelector('.workflow-editor-fanout-max-parallel').value = '9'
    document.getElementById('workflow-editor-form').dispatchEvent(new Event('submit', {
      bubbles: true,
      cancelable: true,
    }))
    expect(apiFetch).toHaveBeenCalledTimes(initialApiCallCount)
    expect(collectionSteps[0].querySelector(
      '[data-workflow-field$="item_limit"] .form-error',
    ).textContent).toBe('Item limit must be between 1 and 32.')
    expect(collectionSteps[1].querySelector(
      '[data-workflow-field$="max_parallel"] .form-error',
    ).textContent).toBe('Parallel runs must be between 1 and 8.')
  }, 10000)

  it('marks workflow capture-fed command previews as available only during the playbook', async () => {
    const { renderWorkflowItems } = await loadAppFns()
    document.getElementById('workflows-overlay').innerHTML = '<div class="workflows-body"></div>'
    renderWorkflowItems([{
      id: 'usr_capture_preview',
      source: 'user',
      version: 2,
      title: 'Resolve and scan',
      description: '',
      inputs: [],
      steps: [
        {
          id: 'resolve',
          cmd: 'dig +short A darklab.sh',
          note: '',
          captures: [{ name: 'resolved_ip', source: 'first_nonempty_line', required: true }],
          next: { success: 'scan', failure: 'stop' },
        },
        {
          id: 'scan',
          cmd: 'nmap -sV {{resolved_ip}}',
          note: '',
          next: { success: 'complete', failure: 'stop' },
        },
      ],
    }], { emitCatalogEvent: false })

    const steps = document.querySelectorAll('.workflow-step')
    expect(steps[0].querySelector('.workflow-step-preview-state').textContent).toBe('Inputs known')
    expect(steps[1].querySelector('.workflow-step-cmd').textContent).toBe('nmap -sV {{resolved_ip}}')
    expect(steps[1].querySelector('.workflow-step-preview-state').textContent)
      .toBe('During playbook: {{resolved_ip}}')
    expect(steps[1].querySelector('.workflow-step-run').disabled).toBe(true)
  })

  it('places structured workflow save errors beside the matching editor field', async () => {
    const apiFetch = vi.fn(() => Promise.resolve({
      ok: false,
      status: 400,
      json: () => Promise.resolve({
        error: 'parameter ID is invalid',
        errors: [
          { field: 'inputs.0.id', message: 'Use lowercase letters and underscores.' },
          { field: 'steps.0.next.codes', message: 'Exit-code routes are invalid.' },
        ],
      }),
    }))
    const { openWorkflowEditor } = await loadAppFns({ apiFetch })
    openWorkflowEditor()
    document.getElementById('workflow-editor-title-input').value = 'Invalid workflow'
    document.querySelector('.workflow-editor-step-command').value = 'dig darklab.sh'
    document.getElementById('workflow-editor-add-parameter').click()
    document.querySelector('.workflow-editor-parameter-id').value = 'Bad ID'
    document.querySelector('.workflow-editor-add-exit-code').click()
    document.querySelector('.workflow-editor-exit-code').value = '1'

    document.getElementById('workflow-editor-form').dispatchEvent(new Event('submit', {
      bubbles: true,
      cancelable: true,
    }))

    await vi.waitFor(() => expect(apiFetch).toHaveBeenCalled())
    await vi.waitFor(() => {
      expect(document.querySelector('.workflow-editor-parameter-id').getAttribute('aria-invalid')).toBe('true')
    })
    expect(document.querySelector('[data-workflow-field="inputs.0.id"] .form-error').textContent)
      .toBe('Use lowercase letters and underscores.')
    expect(document.querySelector('[data-workflow-field="steps.0.next.codes"] > .form-error').textContent)
      .toBe('Exit-code routes are invalid.')
  })

  it('renders recent workflow execution progress, branches, captures, and linked runs', async () => {
    const { renderWorkflowExecutionsSection, formatWorkflowExecutionElapsed } = await loadAppFns()
    const body = document.createElement('div')
    body.className = 'workflows-body'
    document.body.appendChild(body)
    const finished = Date.UTC(2026, 6, 12, 10, 1, 5)

    renderWorkflowExecutionsSection(body, {
      executions: [{
        id: 'wfx_recent_1',
        title: 'Resolve and scan',
        status: 'completed',
        current_step_id: '',
        created: '2026-07-12 10:00:00',
        finished: '2026-07-12 10:01:05',
        steps: [{
          step_id: 'resolve',
          status: 'succeeded',
          run_id: 'run-resolve-1',
          selected_transition: 'scan',
          transition_reason: 'success',
          capture_names: ['resolved_ip'],
          fanout_summary: {
            total: 6, succeeded: 2, failed: 1, skipped: 1, pending: 1, running: 1,
            failure_samples: ['scope_rejected'],
          },
        }],
      }],
    }, { nowMs: finished })

    expect(formatWorkflowExecutionElapsed({
      created: '2026-07-12 10:00:00',
      finished: '2026-07-12 10:01:05',
    }, finished)).toBe('1m 05s')
    expect(body.querySelector('.workflow-execution-row').dataset.workflowExecutionId).toBe('wfx_recent_1')
    expect(body.querySelector('.workflow-execution-row').tabIndex).toBe(-1)
    expect(body.textContent).toContain('Resolve and scan')
    expect(body.textContent).toContain('Elapsed: 1m 05s')
    expect(body.textContent).toContain('to scan (success)')
    expect(body.textContent).toContain('Captured: resolved_ip')
    expect(body.textContent).toContain(
      'Fan-out: 4/6 finished · 1 pending · 1 active · 2 succeeded · 1 failed · 1 skipped',
    )
    expect(body.textContent).toContain('Failure codes: scope_rejected')
    expect(body.textContent).toContain('run-resolve-1')
  })

  it('shows playbook ancestry on history rows and links sibling step runs', () => {
    const { _createHistoryEntry, _historyRunWorkflowSummary } = fromDomScripts(
      [
        'app/static/js/core/history_core.js',
        'app/static/js/features/history/history_rows.js',
        'app/static/js/features/history/history_run_details.js',
      ],
      { document, window },
      '({ _createHistoryEntry, _historyRunWorkflowSummary })',
    )
    const run = {
      id: 'run-resolve',
      command: 'dig example.com',
      started: '2026-07-12T10:00:00Z',
      finished: '2026-07-12T10:00:01Z',
      exit_code: 0,
      workflow_execution_id: 'wfx_history_1',
      workflow_step_id: 'resolve',
      workflow_execution: {
        execution_id: 'wfx_history_1',
        title: 'Resolve and scan',
        step: { step_id: 'resolve', run_id: 'run-resolve' },
        steps: [
          { step_id: 'resolve', run_id: 'run-resolve' },
          { step_id: 'scan', run_id: 'run-scan' },
        ],
      },
    }

    const entry = _createHistoryEntry(run, false)
    const summary = _historyRunWorkflowSummary(run)

    expect(entry.querySelector('.history-entry-kind-workflow').textContent).toBe('playbook')
    expect(entry.querySelector('.history-entry-kind-workflow').title).toContain('step resolve')
    expect(summary.textContent).toContain('Resolve and scan · resolve')
    expect(summary.querySelector('[data-history-run-action="open-workflow-execution"]')).not.toBeNull()
    expect(summary.querySelector('[data-history-run-action="open-workflow-run:run-scan"]').textContent).toBe('scan')
  })

  it('wires workflow execution attach, open, cancel, and refresh actions', async () => {
    const { renderWorkflowExecutionsSection } = await loadAppFns()
    const body = document.createElement('div')
    body.className = 'workflows-body'
    document.body.appendChild(body)
    const onAttachRun = vi.fn()
    const onOpenRun = vi.fn()
    const onCancel = vi.fn()
    const onRefresh = vi.fn()

    renderWorkflowExecutionsSection(body, {
      executions: [
        {
          id: 'wfx_running',
          title: 'Running workflow',
          status: 'running',
          current_step_id: 'scan',
          created: '2026-07-12 10:00:00',
          steps: [{ step_id: 'scan', status: 'running', run_id: 'run-active' }],
        },
        {
          id: 'wfx_done',
          title: 'Finished workflow',
          status: 'completed',
          created: '2026-07-12 09:00:00',
          finished: '2026-07-12 09:00:10',
          steps: [{ step_id: 'resolve', status: 'succeeded', run_id: 'run-finished' }],
        },
      ],
    }, { onAttachRun, onOpenRun, onCancel, onRefresh })

    const button = label => [...body.querySelectorAll('button')].find(item => item.textContent === label)
    button('Attach').click()
    button('Open').click()
    button('Cancel').click()
    body.querySelector('.workflow-executions-refresh').click()
    await Promise.resolve()

    expect(onAttachRun).toHaveBeenCalledWith('run-active')
    expect(onOpenRun).toHaveBeenCalledWith('run-finished')
    expect(onCancel).toHaveBeenCalledWith(expect.objectContaining({ id: 'wfx_running' }))
    expect(onRefresh).toHaveBeenCalledOnce()
  })

  it('coordinates active workflow attachment and confirmed server cancellation', async () => {
    let listReads = 0
    const apiFetch = vi.fn((url) => {
      if (url.startsWith('/workflow-executions?')) {
        listReads += 1
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            executions: listReads === 1 ? [{
              id: 'wfx_active',
              title: 'Active workflow',
              status: 'running',
              current_step_id: 'scan',
              created: '2026-07-12 10:00:00',
              steps: [{ step_id: 'scan', status: 'running', run_id: 'run-active' }],
            }] : [],
          }),
        })
      }
      if (url === '/history/active') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ runs: [{ run_id: 'run-active', command: 'nmap example.com' }] }),
        })
      }
      if (url === '/workflow-executions/wfx_active/cancel') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ execution: { status: 'canceled' } }) })
      }
      return Promise.resolve({ ok: false, json: () => Promise.resolve({ error: 'unexpected request' }) })
    })
    const attachActiveRun = vi.fn(async () => true)
    const closeOverlays = vi.fn()
    const showConfirm = vi.fn(async () => 'cancel-execution')
    const showToast = vi.fn()
    const { createWorkflowExecutionController } = await loadAppFns()
    const overlay = document.getElementById('workflows-overlay')
    overlay.classList.add('open')
    overlay.innerHTML = '<div class="workflows-body"></div>'
    const controller = createWorkflowExecutionController({
      apiFetch,
      attachActiveRun,
      closeOverlays,
      showConfirm,
      showToast,
      setTimer: vi.fn(() => 1),
      clearTimer: vi.fn(),
    })

    await controller.refresh()
    const button = label => [...overlay.querySelectorAll('button')].find(item => item.textContent === label)
    button('Attach').click()
    await vi.waitFor(() => expect(attachActiveRun).toHaveBeenCalledWith(
      expect.objectContaining({ run_id: 'run-active' }),
    ))
    button('Cancel').click()
    await vi.waitFor(() => expect(apiFetch).toHaveBeenCalledWith(
      '/workflow-executions/wfx_active/cancel',
      { method: 'POST' },
    ))

    expect(showConfirm).toHaveBeenCalledOnce()
    expect(closeOverlays).toHaveBeenCalledOnce()
    expect(showToast).toHaveBeenCalledWith('Workflow execution canceled', '')
  })

  it('keeps recent execution history global when workflow selection changes', async () => {
    const apiFetch = vi.fn((url) => {
      if (url.startsWith('/workflow-executions?')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            executions: [{
              id: 'wfx_all',
              workflow_id: 'workflow_a',
              title: 'Workflow A',
              status: 'completed',
              created: '2026-07-12 10:00:00',
              finished: '2026-07-12 10:00:01',
              steps: [],
            }],
          }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const {
      getRuntimeAutocompleteContext,
      renderWorkflowItems,
      refreshWorkflowExecutions,
    } = await loadAppFns({ apiFetch })
    const overlay = document.getElementById('workflows-overlay')
    overlay.classList.add('open')
    overlay.dataset.workflowView = 'executions'
    overlay.dataset.workflowId = 'workflow_a'
    overlay.innerHTML = '<div class="workflows-body"></div>'

    renderWorkflowItems([], { emitCatalogEvent: false })
    await refreshWorkflowExecutions()
    await vi.waitFor(() => expect(overlay.textContent).toContain('Workflow A'))
    overlay.dataset.workflowId = 'workflow_b'
    await refreshWorkflowExecutions()

    expect(overlay.textContent).toContain('Workflow A')
    const executionReads = apiFetch.mock.calls
      .map(([url]) => url)
      .filter(url => url.startsWith('/workflow-executions?'))
    expect(executionReads).toEqual([
      '/workflow-executions?limit=10',
      '/workflow-executions?limit=10',
    ])
    const context = getRuntimeAutocompleteContext(builtInAutocompleteBase())
    expect(context.workflow.arg_hints.status.map(item => item.value)).toEqual(['wfx_all'])
  })

  it('keeps panel launches out of the terminal and handles workflow run inputs', async () => {
    const submitComposerCommand = vi.fn()
    const workflow = {
      id: 'builtin:dns',
      source: 'builtin',
      title: 'DNS Troubleshooting',
      description: '',
      inputs: [{ id: 'domain', label: 'Domain', type: 'domain', required: true, placeholder: 'example.com', default: '', help: '' }],
      steps: [{ cmd: 'dig {{domain}} A', note: '' }],
    }
    const apiFetch = vi.fn((url) => {
      if (url === '/workflows') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [workflow] }) })
      }
      if (url === '/workflow-executions') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            execution: {
              id: 'wfx_terminal_test',
              current_step_id: 'step_1',
              status: 'running',
            },
          }),
        })
      }
      if (url.startsWith('/workflow-executions?')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ executions: [] }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const {
      renderWorkflowItems,
      handleWorkflowTerminalCommand,
    } = await loadAppFns({
      submitComposerCommand,
      apiFetch,
    })
    renderWorkflowItems([workflow], { emitCatalogEvent: false })

    const legacyExecution = createBrowserCommandExecution(
      'workflow run dns-troubleshooting --domain darklab.sh',
    )
    await handleWorkflowTerminalCommand(
      'workflow run dns-troubleshooting --domain darklab.sh',
      'tab-1',
      legacyExecution,
    )

    expect(commandExecutionText(legacyExecution)).toContain(
      '[workflow] DNS Troubleshooting: 1 step(s) queued.',
    )
    expect(legacyExecution.state.delegated).toBe(true)
    expect(legacyExecution.state.status).toBe('idle')
    expect(legacyExecution.state.persistence).toBe('none')
    expect(legacyExecution.state.recordRecent).toBe(false)

    const durableWorkflow = {
      ...workflow,
      id: 'bounded_subdomain_assessment',
      version: 3,
      title: 'Bounded Subdomain Assessment',
      inputs: [{ ...workflow.inputs[0], default: 'darklab.sh' }],
      steps: [
        {
          id: 'discover',
          cmd: 'subfinder -d {{domain}} -silent',
          captures: [{
            name: 'hosts', source: 'entity', entity_type: 'domain',
            kind: 'collection', item_limit: 4, required: true,
          }],
          next: { success: 'probe', failure: 'stop' },
        },
        {
          id: 'probe',
          cmd: 'httpx -u {{hosts}} -silent',
          for_each: {
            collection: 'hosts', failure_mode: 'continue', retries: 0,
            max_parallel: 2, max_failures: 4,
          },
          next: { success: 'complete', failure: 'stop' },
        },
      ],
    }
    document.getElementById('workflows-overlay').innerHTML = '<div class="workflows-body"></div>'
    document.getElementById('workflows-overlay').classList.add('open')
    renderWorkflowItems([durableWorkflow], { emitCatalogEvent: false })
    document.querySelector('.workflow-run-all').click()
    await vi.waitFor(() => expect(apiFetch).toHaveBeenCalledWith(
      '/workflow-executions',
      expect.objectContaining({ method: 'POST' }),
    ))
    await vi.waitFor(() => {
      expect(document.getElementById('workflows-overlay').dataset.workflowView).toBe('executions')
    })
    expect(document.body.textContent).not.toContain('wfx_terminal_test')

    const durableExecution = createBrowserCommandExecution(
      'workflow run bounded-subdomain-assessment --domain darklab.sh',
    )
    await handleWorkflowTerminalCommand(
      'workflow run bounded-subdomain-assessment --domain darklab.sh',
      'tab-1',
      durableExecution,
    )
    await vi.waitFor(() => expect(commandExecutionText(durableExecution)).toContain(
      '[workflow] Bounded Subdomain Assessment: execution wfx_terminal_test started with 1 input. '
        + 'Check progress with workflow status wfx_terminal_test.',
    ))
    expect(commandExecutionText(durableExecution)).not.toContain('step_1')
    expect(durableExecution.state.status).toBe('ok')
    expect(durableExecution.state.persistence).toBe('none')
    expect(durableExecution.state.recordRecent).toBe(false)

    const sensitiveWorkflow = {
      ...workflow,
      id: 'builtin:authenticated-dns',
      title: 'Authenticated DNS',
      inputs: [{ id: 'token', label: 'Token', type: 'text', required: true, sensitive: true }],
      steps: [{ cmd: 'echo {{token}}', note: '' }],
    }
    renderWorkflowItems([sensitiveWorkflow], { emitCatalogEvent: false })
    const sensitiveExecution = createBrowserCommandExecution(
      'workflow run authenticated-dns --token super-secret-value',
    )
    await handleWorkflowTerminalCommand(
      'workflow run authenticated-dns --token super-secret-value',
      'tab-1',
      sensitiveExecution,
    )

    expect(sensitiveExecution.state.safeCommand).toBe(
      'workflow run authenticated-dns --token [redacted]',
    )
    expect(commandExecutionText(sensitiveExecution)).not.toContain('super-secret-value')
    expect(commandExecutionText(sensitiveExecution)).toContain(
      "Sensitive parameters can't be supplied inline",
    )
    expect(sensitiveExecution.state.status).toBe('fail')
  })

  it('handles workflow runs, status, and cancel terminal commands without exposing inputs', async () => {
    const privateValue = 'terminal-private-value'
    const execution = {
      id: 'wfx_cli_test',
      title: 'CLI playbook',
      status: 'running',
      current_step_id: 'inspect',
      input_values: { token: privateValue },
      variables: { token: privateValue, captured: privateValue },
      steps: [{
        step_id: 'inspect',
        status: 'running',
        run_id: 'run-cli-test',
        selected_transition: 'complete',
        transition_reason: 'success',
        capture_names: ['captured'],
      }],
    }
    const apiFetch = vi.fn((url, options) => {
      if (url.startsWith('/workflow-executions?')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ executions: [execution] }),
        })
      }
      if (url === '/workflow-executions/wfx_cli_test' && !options) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ execution }),
        })
      }
      if (url === '/workflow-executions/wfx_cli_test/cancel' && options?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ execution: { ...execution, status: 'canceled' } }),
        })
      }
      if (url === '/workflow-executions/not-visible') {
        return Promise.resolve({
          ok: false,
          json: () => Promise.resolve({ error: 'workflow execution not found' }),
        })
      }
      return Promise.resolve({ ok: false, json: () => Promise.resolve({ error: 'unexpected request' }) })
    })
    const workflow = {
      id: 'builtin:cli-playbook',
      source: 'builtin',
      title: 'CLI playbook',
      inputs: [],
      steps: [{ cmd: 'echo ready' }],
    }
    const { renderWorkflowItems, handleWorkflowTerminalCommand } = await loadAppFns({ apiFetch })
    renderWorkflowItems([workflow], { emitCatalogEvent: false })

    const commands = [
      'workflow runs',
      'workflow status wfx_cli_test',
      'workflow cancel wfx_cli_test',
      'workflow status',
      'workflow status not-visible',
    ]
    const executions = commands.map(command => createBrowserCommandExecution(command))
    for (const [index, command] of commands.entries()) {
      await handleWorkflowTerminalCommand(command, 'tab-1', executions[index])
    }
    const terminalText = executions.map(commandExecutionText).join('\n')

    expect(terminalText).toContain('Recent workflow executions:')
    expect(terminalText).toContain('wfx_cli_test')
    expect(terminalText).toContain('CLI playbook (running, step inspect)')
    expect(terminalText).toContain('inspect: running, run run-cli-test, next complete (success), captures captured')
    expect(terminalText).toContain('[workflow] wfx_cli_test canceled.')
    expect(terminalText).toContain('[workflow] execution id is required')
    expect(terminalText).toContain('[workflow] workflow execution not found')
    expect(terminalText).not.toContain(privateValue)
    expect(executions.map(item => item.state.status)).toEqual([
      'ok',
      'ok',
      'ok',
      'fail',
      'fail',
    ])
    expect(executions.map(item => item.state.recordRecent)).toEqual([
      true,
      true,
      true,
      false,
      false,
    ])
    expect(apiFetch).toHaveBeenCalledWith(
      '/workflow-executions/wfx_cli_test/cancel',
      { method: 'POST' },
    )
  })

  it('serves runtime autocomplete context for built-in command lookup helpers', async () => {
    const { getRuntimeAutocompleteContext } = await loadAppFns()

    const context = getRuntimeAutocompleteContext({
      ...builtInAutocompleteBase(),
      curl: {},
      nmap: {},
    })

    expect(context.commands.flags.map(item => item.value)).toEqual(['--built-in', '--external'])
    expect(context.commands.arg_hints.__positional__.map(item => item.value)).toContain('info')
    expect(context.commands.arg_hints.info.map(item => item.value)).toEqual(
      expect.arrayContaining(['curl', 'nmap', 'commands', 'man']),
    )
    expect(context.runs.flags.map(item => item.value)).toEqual(['-v', '--verbose', '--json'])
    expect(context.jobs.flags.map(item => item.value)).toEqual(['-v', '--verbose', '--json'])
    expect(context['session-token'].arg_hints.__positional__.map(item => item.value)).toContain('set <token>')
    expect(context['session-token'].arg_hints.set[0].value).toBe('<token>')
    expect(context.file.arg_hints.__positional__.map(item => item.value)).toEqual([
      'list <folder>',
      'ls <folder>',
      'show <file>',
      'diff <source1> <source2>',
      'add <file>',
      'add-dir <folder>',
      'edit <file>',
      'download <file>',
      'move <source> <destination>',
      'delete <file>',
      'help',
      'diff --last',
    ])
    expect(context.status).toBeTruthy()
    expect(context.whoami).toBeTruthy()
    expect(context.man.arg_hints.__positional__.map(item => item.value)).toEqual(
      expect.arrayContaining(['commands', 'curl', 'nmap', 'status', 'whoami']),
    )
    expect(context.which.arg_hints.__positional__.map(item => item.value)).toEqual(
      expect.arrayContaining(['commands', 'curl', 'status']),
    )
    expect(context.type.arg_hints.__positional__.map(item => item.value)).toEqual(
      expect.arrayContaining(['commands', 'nmap', 'whoami']),
    )
  })

  it('serves loaded workspace files as file command autocomplete values', async () => {
    const { getRuntimeAutocompleteContext } = await loadAppFns({
      getWorkspaceAutocompleteFileHints: () => [
        { value: 'targets.txt', description: 'session file · 11 B' },
        { value: 'ffuf.json', description: 'session file · 2 KB' },
      ],
      getWorkspaceAutocompleteDirectoryHints: () => [
        { value: 'reports', description: 'session folder' },
      ],
    })

    const context = getRuntimeAutocompleteContext(builtInAutocompleteBase())

    expect(context.file.arg_hints.show.map(item => item.value)).toEqual(['targets.txt', 'ffuf.json', 'reports/'])
    expect(context.file.arg_hints.diff.map(item => item.value)).toEqual([
      '--last', '-q', '--brief', '-u', '--unified', '-y', '--side-by-side',
      'run:<run-id>', 'file:<path>', 'targets.txt', 'ffuf.json', 'reports/',
    ])
    expect(context.file.arg_hints.edit.map(item => item.value)).toEqual(['targets.txt', 'ffuf.json', 'reports/'])
    expect(context.file.arg_hints.download.map(item => item.value)).toEqual(['targets.txt', 'ffuf.json', 'reports/'])
    expect(context.file.arg_hints.move.map(item => item.value)).toEqual(['targets.txt', 'ffuf.json', 'reports/'])
    expect(context.file.sequence_arg_hints['move targets.txt'].map(item => item.value)).toEqual(['reports/', '/'])
    expect(context.file.sequence_arg_hints['move reports/'].map(item => item.value)).toEqual(['/'])
    expect(context.mv.arg_hints.__positional__.map(item => item.value)).toEqual(['targets.txt', 'ffuf.json', 'reports/'])
    expect(context.mv.sequence_arg_hints['mv targets.txt'].map(item => item.value)).toEqual(['reports/', '/'])
    expect(context.mv.sequence_arg_hints['mv reports/'].map(item => item.value)).toEqual(['/'])
    expect(context.file.arg_hints.rm.map(item => item.description)).toEqual([
      'Remove folders recursively',
      'Remove folders recursively',
      'session file · 11 B',
      'session file · 2 KB',
      'session folder',
    ])
    expect(context.cat.arg_hints.__positional__.map(item => item.value)).toEqual(['targets.txt', 'ffuf.json', 'reports/'])
    expect(context.diff.arg_hints.__positional__.map(item => item.value)).toEqual([
      '--last', '-q', '--brief', '-u', '--unified', '-y', '--side-by-side',
      'run:<run-id>', 'file:<path>', 'targets.txt', 'ffuf.json', 'reports/',
    ])
    expect(context.cd.arg_hints.__positional__.map(item => item.value)).toEqual(['reports/', '/'])
    expect(context.ll.arg_hints.__positional__.map(item => item.value)).toEqual(['-R', 'reports/', '/'])
    expect(context.ls.arg_hints.__positional__.map(item => item.value)).toEqual(['-l', '-R', 'reports/', '/'])
    expect(context.mkdir.arg_hints.__positional__.map(item => item.value)).toEqual(['reports/', '<folder>'])
    expect(context.grep.arg_hints.__positional__.map(item => item.value)).toEqual(['targets.txt', 'ffuf.json', 'reports/'])
    expect(context.head.arg_hints.__positional__.map(item => item.value)).toEqual(['targets.txt', 'ffuf.json', 'reports/'])
    expect(context.rm.arg_hints.__positional__.map(item => item.value)).toEqual(['-r', '-rf', 'targets.txt', 'ffuf.json', 'reports/'])
  })

  it('serves workspace autocomplete values relative to the active workspace folder', async () => {
    const { getRuntimeAutocompleteContext } = await loadAppFns({
      workspaceCwd: 'reports',
      getWorkspaceAutocompleteFileHints: () => [
        { value: 'reports/summary.txt', description: 'session file · 11 B' },
        { value: 'reports/nested/deep.txt', description: 'session file · 2 KB' },
        { value: 'root.txt', description: 'session file · 1 B' },
      ],
      getWorkspaceAutocompleteDirectoryHints: () => [
        { value: 'reports', description: 'session folder' },
        { value: 'reports/nested', description: 'session folder' },
      ],
      getWorkspaceDirectoryEntries: () => ({
        folders: [{ name: 'nested', path: 'reports/nested' }],
        files: [{ name: 'summary.txt', path: 'reports/summary.txt' }],
      }),
    })

    const context = getRuntimeAutocompleteContext(builtInAutocompleteBase())

    expect(context.cd.arg_hints.__positional__.map(item => item.value)).toEqual(['../', 'nested/', '/'])
    expect(context.ll.arg_hints.__positional__.map(item => item.value)).toEqual(['-R', '../', 'nested/', '/'])
    expect(context.ls.arg_hints.__positional__.map(item => item.value)).toEqual(['-l', '-R', '../', 'nested/', '/'])
    expect(context.cat.arg_hints.__positional__.map(item => item.value)).toEqual(['summary.txt', 'nested/'])
    expect(context.grep.arg_hints.__positional__.map(item => item.value)).toEqual(['summary.txt', 'nested/'])
    expect(context.file.arg_hints.show.map(item => item.value)).toEqual(['summary.txt', 'nested/'])
    expect(context.file.arg_hints.diff.map(item => item.value)).toEqual([
      '--last', '-q', '--brief', '-u', '--unified', '-y', '--side-by-side',
      'run:<run-id>', 'file:<path>', 'summary.txt', 'nested/',
    ])
    expect(context.file.arg_hints.list.map(item => item.value)).toEqual(['-l', '-R', 'nested/', '/'])
    expect(context.file.arg_hints.ls.map(item => item.value)).toEqual(['-l', '-R', 'nested/', '/'])
    expect(context.file.arg_hints.move.map(item => item.value)).toEqual(['summary.txt', 'nested/'])
    expect(context.file.sequence_arg_hints['move summary.txt'].map(item => item.value)).toEqual(['nested/', '/'])
    expect(context.file.sequence_arg_hints['move nested/'].map(item => item.value)).toEqual(['/'])
    expect(context.mv.arg_hints.__positional__.map(item => item.value)).toEqual(['summary.txt', 'nested/'])
    expect(context.mv.sequence_arg_hints['mv summary.txt'].map(item => item.value)).toEqual(['nested/', '/'])
    expect(context.mv.sequence_arg_hints['mv nested/'].map(item => item.value)).toEqual(['/'])
  })

  it('serves directory-aware workspace autocomplete hints while preserving typed prefixes', async () => {
    const entriesByDirectory = {
      '': {
        folders: [{ name: 'darklab', path: 'darklab' }, { name: 'reports', path: 'reports' }],
        files: [{ name: 'root.txt', path: 'root.txt' }],
      },
      darklab: {
        folders: [{ name: 'nested', path: 'darklab/nested' }],
        files: [{ name: 'targets.txt', path: 'darklab/targets.txt' }],
      },
      'reports/darklab': {
        folders: [{ name: 'child', path: 'reports/darklab/child' }],
        files: [{ name: 'summary.txt', path: 'reports/darklab/summary.txt' }],
      },
    }
    const { getRuntimeAutocompleteContext, getWorkspaceAutocompletePathHints } = await loadAppFns({
      workspaceCwd: 'reports',
      getWorkspaceAutocompleteFileHints: () => [
        { value: 'root.txt', description: 'session file · 1 B' },
        { value: 'darklab/targets.txt', description: 'session file · 11 B' },
        { value: 'reports/darklab/summary.txt', description: 'session file · 42 B' },
      ],
      getWorkspaceAutocompleteDirectoryHints: () => [
        { value: 'darklab', description: 'session folder' },
        { value: 'reports', description: 'session folder' },
        { value: 'darklab/nested', description: 'session folder' },
        { value: 'reports/darklab/child', description: 'session folder' },
      ],
      getWorkspaceDirectoryEntries: path => entriesByDirectory[path] || { folders: [], files: [] },
    })

    const context = getRuntimeAutocompleteContext(builtInAutocompleteBase())

    expect(context.cat.workspace_path_arg_kinds.__positional__).toEqual(['file'])
    expect(context.diff.workspace_path_arg_kinds).toEqual({})
    expect(context.ls.workspace_path_arg_kinds.__positional__).toEqual(['directory'])
    expect(context.mv.workspace_path_arg_kinds.__positional__).toEqual(['any', 'directory'])
    expect(context.file.workspace_path_arg_kinds.move).toEqual(['any', 'directory'])
    expect(context.file.workspace_path_arg_kinds.diff).toBeUndefined()
    expect(getWorkspaceAutocompletePathHints('file', 'darklab/').map(item => item.value)).toEqual(['darklab/summary.txt', 'darklab/child/'])
    expect(getWorkspaceAutocompletePathHints('directory', '../').map(item => item.value)).toEqual(['../darklab/', '../reports/'])
    expect(getWorkspaceAutocompletePathHints('file', '../darklab/').map(item => item.value)).toEqual(['../darklab/targets.txt', '../darklab/nested/'])
    expect(getWorkspaceAutocompletePathHints('any', '../darklab/').map(item => item.value)).toEqual(['../darklab/targets.txt', '../darklab/nested/'])
    expect(getWorkspaceAutocompletePathHints('file', '../../')).toEqual([])
  })

  it('hides workspace built-ins from runtime autocomplete when Files are disabled', async () => {
    const { getRuntimeAutocompleteContext } = await loadAppFns({
      appConfig: { workspace_enabled: false },
    })

    const context = getRuntimeAutocompleteContext({ ...builtInAutocompleteBase(), curl: {} })

    expect(context.file).toBeUndefined()
    expect(context.cat).toBeUndefined()
    expect(context.cd).toBeUndefined()
    expect(context.diff.arg_hints.__positional__.map(item => item.value)).toEqual([
      '--last', '-q', '--brief', '-u', '--unified', '-y', '--side-by-side', 'run:<run-id>',
    ])
    expect(context.grep).toBeUndefined()
    expect(context.ll).toBeUndefined()
    expect(context.ls).toBeUndefined()
    expect(context.mkdir).toBeUndefined()
    expect(context.mv).toBeUndefined()
    expect(context.rm).toBeUndefined()
    expect(context.man.arg_hints.__positional__.map(item => item.value)).not.toContain('file')
  })

  it('hides the tour built-in from runtime autocomplete when the feature is disabled', async () => {
    const { getRuntimeAutocompleteContext } = await loadAppFns({
      appConfig: { workspace_enabled: true, tour_enabled: false },
    })

    const context = getRuntimeAutocompleteContext(builtInAutocompleteBase())

    expect(context.tour).toBeUndefined()
  })

  it('keeps code-owned built-ins out of commands.yaml', () => {
    const commandsYaml = readFileSync(resolve(REPO_ROOT, 'app/conf/commands.yaml'), 'utf8')
    const yamlRoots = new Set(
      [...commandsYaml.matchAll(/^- root: ([a-z0-9_-]+)/gm)].map(match => match[1]),
    )
    const runtimeRoots = [
      'banner', 'cat', 'cd', 'clear', 'commands', 'config', 'date', 'df', 'diff', 'env', 'exit', 'faq', 'fortune', 'free',
      'file', 'grep', 'groups', 'head', 'help', 'history', 'hostname', 'id', 'ip', 'jobs', 'last', 'limits', 'll', 'ls', 'man',
      'mkdir', 'ps', 'pwd', 'quit', 'retention', 'rm', 'route', 'runs', 'session-token', 'shortcuts', 'sort', 'stats', 'status',
      'tail', 'theme', 'tour', 'tty', 'type', 'uname', 'uniq', 'uptime', 'version', 'wc', 'which', 'who', 'whoami',
    ]

    expect(runtimeRoots.filter(root => yamlRoots.has(root))).toEqual([])
  })

  it('groups theme cards into labeled sections in the preview modal', async () => {
    await loadAppFns({
      themeRegistry: {
        current: {
          name: 'apricot_sand',
          label: 'Apricot Sand',
          group: 'Warm Light',
          sort: 50,
          source: 'variant',
          vars: { '--bg': '#9ab7d0' },
        },
        themes: [
          {
            name: 'apricot_sand',
            label: 'Apricot Sand',
            group: 'Warm Light',
            sort: 50,
            source: 'variant',
            vars: { '--bg': '#9ab7d0' },
          },
          {
            name: 'olive_grove',
            label: 'Olive Grove',
            group: 'Warm Light',
            sort: 20,
            source: 'variant',
            vars: { '--bg': '#c0c0a8' },
          },
          {
            name: 'rose_quartz',
            label: 'Rose Quartz',
            group: 'Warm Light',
            sort: 30,
            source: 'variant',
            vars: { '--bg': '#e6d7dc' },
          },
          {
            name: 'graphite',
            label: 'Graphite',
            group: 'Neutral Light',
            sort: 90,
            source: 'variant',
            vars: { '--bg': '#d0d0d0' },
          },
        ],
      },
    })

    const groupTitles = Array.from(
      document.querySelectorAll('#theme-select .theme-picker-group-title'),
    ).map((node) => node.textContent)
    expect(groupTitles).toEqual(['Warm Light', 'Neutral Light'])
    const sectionGroups = Array.from(
      document.querySelectorAll('#theme-select .theme-picker-group'),
    ).map((node) => node.dataset.themeGroup)
    expect(sectionGroups).toEqual(['Warm Light', 'Neutral Light'])
    expect(
      document.getElementById('theme-select')?.style.getPropertyValue('--theme-picker-columns'),
    ).toBe('2')
    expect(document.querySelectorAll('#theme-select [data-theme-name]').length).toBe(4)
  })

  it('falls back to the current/default theme when localStorage references a missing theme', async () => {
    await loadAppFns({
      theme: 'theme_missing',
      themeRegistry: {
        current: {
          name: 'theme_light_blue',
          label: 'Apricot Sand',
          source: 'variant',
          vars: { '--bg': '#9ab7d0' },
        },
        themes: [
          {
            name: 'theme_light_blue',
            label: 'Apricot Sand',
            source: 'variant',
            vars: { '--bg': '#9ab7d0' },
          },
          {
            name: 'theme_light_olive',
            label: 'Olive Parchment',
            source: 'variant',
            vars: { '--bg': '#c0c0a8' },
          },
        ],
      },
    })

    expect(document.body.dataset.theme).toBe('theme_light_blue')
    expect(document.querySelector('#theme-select .theme-card-active')?.dataset.themeName).toBe(
      'theme_light_blue',
    )
  })

  it('falls back to the baked-in dark palette when the configured default theme is missing', async () => {
    await loadAppFns({
      themeRegistry: {
        current: null,
        themes: [
          {
            name: 'theme_light_blue',
            label: 'Apricot Sand',
            source: 'variant',
            vars: { '--bg': '#9ab7d0' },
          },
          {
            name: 'theme_light_olive',
            label: 'Olive Parchment',
            source: 'variant',
            vars: { '--bg': '#c0c0a8' },
          },
        ],
      },
      apiFetch: vi.fn((url) => {
        if (url === '/config') {
          return Promise.resolve({
            json: () =>
              Promise.resolve({
                app_name: 'darklab_shell',
                prompt_username: 'anon',
              prompt_domain: 'darklab.sh',
                version: '9.9',
                default_theme: 'theme_missing.yaml',
                motd: '',
                command_timeout_seconds: 0,
                max_output_lines: 0,
                permalink_retention_days: 0,
              }),
          })
        }
        if (url === '/allowed-commands') {
          return Promise.resolve({
            json: () => Promise.resolve({ restricted: false, commands: [], groups: [] }),
          })
        }
        if (url === '/faq') {
          return Promise.resolve({ json: () => Promise.resolve({ items: [] }) })
        }
        return Promise.resolve({ json: () => Promise.resolve({}) })
      }),
    })

    expect(document.body.dataset.theme).toBe('dark')
    expect(document.querySelector('#theme-select .theme-card-active')).toBeNull()
  })

  it('shows an empty state when no themes are registered and falls back to the baked-in dark palette', async () => {
    const { openThemeSelector } = await loadAppFns({
      themeRegistry: {
        current: null,
        themes: [],
      },
    })

    expect(document.body.dataset.theme).toBe('dark')

    openThemeSelector()
    expect(document.getElementById('theme-overlay').classList.contains('open')).toBe(true)
    expect(document.getElementById('theme-select').textContent).toContain('No themes available')
  })

  it('renders a single theme card and applies it when only one theme is available', async () => {
    await loadAppFns({
      themeRegistry: {
        current: {
          name: 'only_theme',
          label: 'Only Theme',
          filename: 'only_theme.yaml',
          source: 'variant',
          vars: { '--bg': '#ccd9e6' },
        },
        themes: [
          {
            name: 'only_theme',
            label: 'Only Theme',
            filename: 'only_theme.yaml',
            source: 'variant',
            vars: { '--bg': '#ccd9e6' },
          },
        ],
      },
    })

    const themeSelect = document.getElementById('theme-select')
    const themeCards = Array.from(themeSelect.querySelectorAll('[data-theme-name]'))
    expect(themeCards).toHaveLength(1)
    expect(themeCards[0].dataset.themeName).toBe('only_theme')
    expect(themeCards[0].querySelector('.theme-card-label')?.textContent).toBe('Only Theme')

    themeCards[0].click()
    expect(document.body.dataset.theme).toBe('only_theme')
    expect(document.cookie).toContain('pref_theme_name=only_theme')
  })

  it('refocuses the terminal input after closing the FAQ modal', async () => {
    const { cmdInput, openFaq } = await loadAppFns()
    const faqOverlay = document.getElementById('faq-overlay')

    openFaq()
    expect(faqOverlay.classList.contains('open')).toBe(true)

    document.querySelector('.faq-close').click()
    expect(faqOverlay.classList.contains('open')).toBe(false)
    expect(cmdInput.focus).toHaveBeenCalled()

    cmdInput.focus.mockClear()
    openFaq()
    faqOverlay.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(faqOverlay.classList.contains('open')).toBe(false)
    expect(cmdInput.focus).toHaveBeenCalled()
  })

  it('_setTsMode marks the timestamps button inactive in off mode', async () => {
    const { _setTsMode } = await loadAppFns()
    const tsBtn = document.getElementById('ts-btn')

    _setTsMode('off')

    expect(tsBtn.classList.contains('active')).toBe(false)
    expect(tsBtn.textContent).toBe('timestamps')
    expect(tsBtn.getAttribute('aria-pressed')).toBe('false')
  })

  it('bootstraps cleanly when config and allowed-commands fetches fail', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/config' || url === '/allowed-commands' || url === '/autocomplete') {
        return Promise.reject(new Error('network down'))
      }
      if (url === '/faq') {
        return Promise.resolve({ json: () => Promise.resolve({ items: [] }) })
      }
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })

    document.body.innerHTML = `
      <header><h1></h1></header>
      <button id="ts-btn"></button>
      <button id="hamburger-btn"></button>
      <button id="new-tab-btn"></button>
      <button id="search-toggle-btn"></button>
      <button id="run-btn"></button>
      <button id="search-prev"></button>
      <button id="search-next"></button>
      <button id="ln-btn"></button>
      <button id="history-close"></button>
      <button id="hist-clear-all-btn"></button>
      <nav class="rail-nav" id="rail-nav">
        <button class="rail-nav-item" data-action="history" type="button"></button>
        <button class="rail-nav-item" data-action="theme" type="button"></button>
        <button class="rail-nav-item" data-action="faq" type="button"></button>
      </nav>
      <div id="faq-limits-text"></div>
      <div id="faq-allowed-text"></div>
      <div id="mobile-menu-sheet" class="menu-sheet u-hidden">
        <button data-menu-action="ln"></button>
        <button data-menu-action="ts-toggle" aria-expanded="false" aria-controls="mobile-menu-ts-submenu"></button>
        <div id="mobile-menu-ts-submenu" class="menu-submenu u-hidden">
          <button data-menu-action="ts-set" data-ts-mode="off"></button>
          <button data-menu-action="ts-set" data-ts-mode="elapsed"></button>
          <button data-menu-action="ts-set" data-ts-mode="clock"></button>
        </div>
        <button data-menu-action="search"></button>
        <button data-menu-action="history"></button>
        <button data-menu-action="status-monitor"></button>
        <button data-menu-action="theme"></button>
        <button data-menu-action="faq"></button>
      </div>
      <div id="faq-overlay"></div>
      <button class="faq-close"></button>
      <div class="faq-body"></div>
      <div id="workflows-overlay"></div>
      <input id="cmd" />
      <div id="history-panel"></div>
      <div id="history-list"></div>
      <div id="search-bar"></div>
      <input id="search-input" autocomplete="off" autocapitalize="none" autocorrect="off" spellcheck="false" inputmode="text" />
      <span id="search-count"></span>
      <button id="search-case-btn"></button>
      <button id="search-regex-btn"></button>
      <div class="prompt-wrap"></div>
    `

    const { storage, logClientError } = await loadAppFns({ apiFetch, theme: 'only_theme' })
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()

    expect(apiFetch).toHaveBeenCalledWith('/config')
    expect(apiFetch).toHaveBeenCalledWith('/allowed-commands')
    expect(apiFetch).toHaveBeenCalledWith('/commands/catalog')
    expect(apiFetch).toHaveBeenCalledWith('/autocomplete')
    expect(logClientError).toHaveBeenCalledWith('failed to load /config', expect.any(Error))
    expect(logClientError).toHaveBeenCalledWith(
      'failed to load /allowed-commands',
      expect.any(Error),
    )
    expect(logClientError).toHaveBeenCalledWith('failed to load /autocomplete', expect.any(Error))
    expect(storage.getItem('theme')).toBe('only_theme')
  })

  it('settles the welcome intro immediately when the user types into the active welcome tab', async () => {
    const requestWelcomeSettle = vi.fn()
    const { cmdInput } = await loadAppFns({ requestWelcomeSettle })

    cmdInput.value = 'dig '
    cmdInput.dispatchEvent(new Event('input', { bubbles: true }))

    expect(requestWelcomeSettle).toHaveBeenCalledWith('tab-1')
  })

  it('keeps macOS double-space substitution out of the command composer', async () => {
    const { cmdInput, getComposerState, setComposerState } = await loadAppFns()

    setComposerState({
      value: 'echo ',
      selectionStart: 5,
      selectionEnd: 5,
      activeInput: 'desktop',
    })
    cmdInput.value = 'echo. '
    cmdInput.setSelectionRange(6, 6)
    cmdInput.dispatchEvent(new Event('input', { bubbles: true }))

    expect(cmdInput.value).toBe('echo  ')
    expect(getComposerState()).toMatchObject({
      value: 'echo  ',
      selectionStart: 6,
      selectionEnd: 6,
      activeInput: 'desktop',
    })
  })

  it('settles welcome immediately when Enter is pressed during welcome playback', async () => {
    const requestWelcomeSettle = vi.fn()
    const welcomeOwnsTab = vi.fn(() => true)
    const { cmdInput } = await loadAppFns({
      requestWelcomeSettle,
      welcomeActive: true,
      welcomeOwnsTab,
    })

    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))

    expect(welcomeOwnsTab).toHaveBeenCalledWith('tab-1')
    expect(requestWelcomeSettle).toHaveBeenCalledWith('tab-1')
    expect(cmdInput.focus).toHaveBeenCalled()
  })

  it('does not run command when Enter is pressed in cmd input during welcome playback', async () => {
    const requestWelcomeSettle = vi.fn()
    const welcomeOwnsTab = vi.fn(() => true)
    const runCommand = vi.fn()
    const { cmdInput } = await loadAppFns({
      requestWelcomeSettle,
      welcomeActive: true,
      welcomeOwnsTab,
      runCommand,
    })

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))

    expect(requestWelcomeSettle).toHaveBeenCalledWith('tab-1')
    expect(runCommand).not.toHaveBeenCalled()
  })

  it('lets blank Enter append a prompt after the welcome intro is done', async () => {
    const requestWelcomeSettle = vi.fn()
    const welcomeOwnsTab = vi.fn(() => true)
    const submitComposerCommand = vi.fn()
    const { cmdInput } = await loadAppFns({
      requestWelcomeSettle,
      welcomeActive: true,
      welcomeDone: true,
      welcomeOwnsTab,
      submitComposerCommand,
    })

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))

    expect(requestWelcomeSettle).not.toHaveBeenCalled()
    expect(submitComposerCommand).toHaveBeenCalledWith('', { dismissKeyboard: true })
  })

  it('does not let welcome playback steal Space from schedules form fields', async () => {
    const requestWelcomeSettle = vi.fn()
    const welcomeOwnsTab = vi.fn(() => true)
    await loadAppFns({
      requestWelcomeSettle,
      welcomeActive: true,
      welcomeOwnsTab,
      isSchedulesOverlayOpen: () => true,
    })
    const labelInput = document.createElement('input')
    labelInput.id = 'schedules-label-input'
    document.body.appendChild(labelInput)
    labelInput.focus()

    const event = new KeyboardEvent('keydown', { key: ' ', code: 'Space', bubbles: true, cancelable: true })
    labelInput.dispatchEvent(event)

    expect(requestWelcomeSettle).not.toHaveBeenCalled()
  })

  it('renders the shell prompt line from composer state instead of the stale hidden input', async () => {
    const { cmdInput, setComposerState, syncShellPrompt } = await loadAppFns()
    const shellPromptText = document.getElementById('shell-prompt-text')
    const shellPromptWrap = document.getElementById('shell-prompt-wrap')

    expect(shellPromptText.textContent).toBe('')
    expect(shellPromptWrap.classList.contains('shell-prompt-empty')).toBe(true)

    cmdInput.value = 'stale prompt'
    cmdInput.setSelectionRange(0, 0)
    setComposerState({
      value: 'ping darklab.sh',
      selectionStart: 'ping darklab.sh'.length,
      selectionEnd: 'ping darklab.sh'.length,
      activeInput: 'desktop',
    })
    syncShellPrompt()

    expect(shellPromptText.textContent).toBe('ping darklab.sh')
    expect(shellPromptWrap.classList.contains('shell-prompt-empty')).toBe(false)
  })

  it('persists only non-running tabs for session restore', async () => {
    const tabs = [
      {
        id: 'tab-1',
        label: 'tab 1',
        command: 'dig darklab.sh',
        renamed: false,
        draftInput: 'dig darklab.sh',
        st: 'idle',
        exitCode: null,
        historyRunId: '',
        historyRunKind: '',
        previewTruncated: false,
        fullOutputAvailable: false,
        fullOutputLoaded: false,
        rawLines: [{ text: '$ dig darklab.sh', cls: 'prompt-echo', tsC: '', tsE: '' }],
        closing: false,
      },
      {
        id: 'tab-2',
        label: 'ping',
        command: 'ping darklab.sh',
        renamed: true,
        draftInput: '',
        st: 'running',
        exitCode: null,
        historyRunId: 'run-1',
        historyRunKind: 'external',
        previewTruncated: false,
        fullOutputAvailable: false,
        fullOutputLoaded: false,
        rawLines: [{ text: '$ ping darklab.sh', cls: 'prompt-echo', tsC: '', tsE: '' }],
        closing: false,
      },
    ]
    const { persistTabSessionStateNow, sessionStorage, _getTabSessionStateKey } = await loadAppFns({
      tabs,
      activeTabId: 'tab-1',
    })

    persistTabSessionStateNow()

    const saved = JSON.parse(sessionStorage.getItem(_getTabSessionStateKey()))
    expect(saved.tabs).toHaveLength(2)
    expect(saved.tabs[0].label).toBe('tab 1')
    expect(saved.tabs[0].draftInput).toBe('')
    expect(saved.tabs[1]).toMatchObject({
      label: 'ping',
      command: 'ping darklab.sh',
      st: 'running',
      runId: '',
      historyRunId: 'run-1',
      historyRunKind: 'external',
    })
  })

  it('uses one accessor-backed tab restore flag for window and module guards', async () => {
    const tabs = [
      {
        id: 'tab-1',
        label: 'tab 1',
        command: '',
        renamed: false,
        draftInput: 'nuclei -u https://darklab.sh',
        st: 'idle',
        exitCode: null,
        historyRunId: '',
        previewTruncated: false,
        fullOutputAvailable: false,
        fullOutputLoaded: false,
        rawLines: [],
        closing: false,
      },
    ]
    const {
      persistTabSessionStateNow,
      sessionStorage,
      _getTabSessionStateKey,
      _getTabSessionRestoreInProgress,
      setTabSessionRestoreInProgress,
    } = await loadAppFns({
      tabs,
      activeTabId: 'tab-1',
    })

    expect(_getTabSessionRestoreInProgress()).toBe(false)
    setTabSessionRestoreInProgress(true)
    expect(_getTabSessionRestoreInProgress()).toBe(true)

    persistTabSessionStateNow()
    expect(sessionStorage.getItem(_getTabSessionStateKey())).toBe(null)

    setTabSessionRestoreInProgress(false)
    expect(_getTabSessionRestoreInProgress()).toBe(false)
    persistTabSessionStateNow()
    expect(JSON.parse(sessionStorage.getItem(_getTabSessionStateKey())).tabs).toHaveLength(1)
  })

  it('persists output signal metadata for session restore', async () => {
    const tabs = [
      {
        id: 'tab-1',
        label: 'tab 1',
        command: 'host darklab.sh',
        renamed: false,
        draftInput: '',
        st: 'idle',
        exitCode: 0,
        historyRunId: 'run-1',
        previewTruncated: false,
        fullOutputAvailable: true,
        fullOutputLoaded: true,
        rawLines: [
          {
            text: 'darklab.sh has address 104.21.4.35',
            cls: '',
            tsC: '12:00:00',
            tsE: '+0.1s',
            signals: ['findings'],
            line_index: 0,
            command_root: 'host',
            target: 'darklab.sh',
          },
        ],
        closing: false,
      },
    ]
    const { persistTabSessionStateNow, sessionStorage, _getTabSessionStateKey } = await loadAppFns({
      tabs,
      activeTabId: 'tab-1',
    })

    persistTabSessionStateNow()

    const saved = JSON.parse(sessionStorage.getItem(_getTabSessionStateKey()))
    expect(saved.tabs[0].rawLines[0]).toMatchObject({
      text: 'darklab.sh has address 104.21.4.35',
      signals: ['findings'],
      line_index: 0,
      command_root: 'host',
      target: 'darklab.sh',
    })
  })

  it('restores saved non-running tabs and active draft state from session storage', async () => {
    const tabs = []
    let seq = 0
    const createTab = vi.fn((label) => {
      const id = `tab-${++seq}`
      tabs.push({
        id,
        label,
        command: '',
        renamed: false,
        draftInput: '',
        st: 'idle',
        exitCode: null,
        historyRunId: null,
        previewTruncated: false,
        fullOutputAvailable: false,
        fullOutputLoaded: false,
        rawLines: [],
        closing: false,
      })
      return id
    })
    const activateTab = vi.fn((id) => {
      tabs.forEach((tab) => {
        tab.active = tab.id === id
      })
    })
    const {
      restoreTabSessionState,
      sessionStorage,
      _getTabSessionStateKey,
      _getWelcomeBootPending,
      tabs: restoredTabs,
      getTab,
    } = await loadAppFns({
      tabs,
      createTab,
      activateTab,
      activeTabId: null,
    })

    sessionStorage.setItem(
      _getTabSessionStateKey(),
      JSON.stringify({
        version: 1,
        activeIndex: 1,
        tabs: [
          {
            label: 'tab 1',
            command: 'dig darklab.sh',
            renamed: false,
            draftInput: 'dig darklab.sh',
            st: 'idle',
            exitCode: null,
            historyRunId: '',
            historyRunKind: '',
            previewTruncated: false,
            fullOutputAvailable: false,
            fullOutputLoaded: false,
            rawLines: [{ text: '$ dig darklab.sh', cls: 'prompt-echo', tsC: '', tsE: '' }],
          },
          {
            label: 'notes',
            command: '',
            renamed: true,
            draftInput: 'ffuf -u https://target/FUZZ',
            st: 'fail',
            exitCode: 1,
            historyRunId: 'run-2',
            historyRunKind: 'external',
            previewTruncated: false,
            fullOutputAvailable: true,
            fullOutputLoaded: true,
            rawLines: [{ text: '[connection error]', cls: 'exit-fail', tsC: '', tsE: '' }],
          },
        ],
      }),
    )

    expect(restoreTabSessionState()).toBe(true)
    expect(_getWelcomeBootPending()).toBe(false)
    expect(restoredTabs).toHaveLength(2)
    expect(createTab).toHaveBeenCalledTimes(2)
    expect(getTab('tab-2')?.draftInput).toBe('ffuf -u https://target/FUZZ')
    expect(getTab('tab-2')?.renamed).toBe(true)
    expect(getTab('tab-2')?.historyRunId).toBe('run-2')
    expect(getTab('tab-2')?.historyRunKind).toBe('external')
    expect(activateTab).toHaveBeenCalledWith('tab-2', { focusComposer: false })
  })

  it('preserves a non-active tab draft even when createTab activation would overwrite it during restore', async () => {
    const tabs = []
    let seq = 0
    let activeId = null
    const createTab = vi.fn((label) => {
      const id = `tab-${++seq}`
      tabs.push({
        id,
        label,
        command: '',
        renamed: false,
        draftInput: '',
        st: 'idle',
        exitCode: null,
        historyRunId: null,
        previewTruncated: false,
        fullOutputAvailable: false,
        fullOutputLoaded: false,
        rawLines: [],
        closing: false,
      })
      if (activeId) {
        const prev = tabs.find((tab) => tab.id === activeId)
        if (prev) prev.draftInput = ''
      }
      activeId = id
      return id
    })
    const activateTab = vi.fn((id) => {
      activeId = id
      tabs.forEach((tab) => {
        tab.active = tab.id === id
      })
    })
    const { restoreTabSessionState, sessionStorage, _getTabSessionStateKey, getTab } =
      await loadAppFns({
        tabs,
        createTab,
        activateTab,
        activeTabId: null,
      })

    sessionStorage.setItem(
      _getTabSessionStateKey(),
      JSON.stringify({
        version: 1,
        activeIndex: 1,
        tabs: [
          {
            label: 'tab 1',
            command: '',
            renamed: false,
            workspaceCwd: 'shell',
            draftInput: 'dig darklab.sh',
            st: 'idle',
            exitCode: null,
            historyRunId: '',
            previewTruncated: false,
            fullOutputAvailable: false,
            fullOutputLoaded: false,
            rawLines: [],
          },
          {
            label: 'tab 2',
            command: '',
            renamed: false,
            workspaceCwd: 'shell/reports',
            draftInput: 'hostname',
            st: 'idle',
            exitCode: null,
            historyRunId: '',
            previewTruncated: false,
            fullOutputAvailable: false,
            fullOutputLoaded: false,
            rawLines: [],
          },
        ],
      }),
    )

    expect(restoreTabSessionState()).toBe(true)
    expect(getTab('tab-1')?.draftInput).toBe('dig darklab.sh')
    expect(getTab('tab-2')?.draftInput).toBe('hostname')
    expect(getTab('tab-1')?.workspaceCwd).toBe('shell')
    expect(getTab('tab-2')?.workspaceCwd).toBe('shell/reports')
  })

  it('preserves the last created non-active tab draft when the final restored active tab is different', async () => {
    const tabs = []
    let seq = 0
    const createTab = vi.fn((label) => {
      const id = `tab-${++seq}`
      tabs.push({
        id,
        label,
        command: '',
        renamed: false,
        draftInput: '',
        st: 'idle',
        exitCode: null,
        historyRunId: null,
        previewTruncated: false,
        fullOutputAvailable: false,
        fullOutputLoaded: false,
        rawLines: [],
        closing: false,
      })
      return id
    })
    const { restoreTabSessionState, sessionStorage, _getTabSessionStateKey, getTab } =
      await loadAppFns({
        tabs,
        createTab,
        activeTabId: null,
      })

    sessionStorage.setItem(
      _getTabSessionStateKey(),
      JSON.stringify({
        version: 1,
        activeIndex: 0,
        tabs: [
          {
            label: 'tab 1',
            command: '',
            renamed: false,
            draftInput: 'alpha',
            st: 'idle',
            exitCode: null,
            historyRunId: '',
            previewTruncated: false,
            fullOutputAvailable: false,
            fullOutputLoaded: false,
            rawLines: [],
          },
          {
            label: 'tab 2',
            command: '',
            renamed: false,
            draftInput: 'beta',
            st: 'idle',
            exitCode: null,
            historyRunId: '',
            previewTruncated: false,
            fullOutputAvailable: false,
            fullOutputLoaded: false,
            rawLines: [],
          },
        ],
      }),
    )

    expect(restoreTabSessionState()).toBe(true)
    expect(getTab('tab-1')?.draftInput).toBe('alpha')
    expect(getTab('tab-2')?.draftInput).toBe('beta')
  })

  it('manually inserts printable desktop keydown input once', async () => {
    const { cmdInput, setComposerState } = await loadAppFns()

    cmdInput.value = 'ab'
    cmdInput.setSelectionRange(2, 2)
    setComposerState({ value: 'ab', selectionStart: 2, selectionEnd: 2, activeInput: 'desktop' })
    Object.defineProperty(document, 'activeElement', {
      configurable: true,
      get: () => cmdInput,
    })
    const ev = new KeyboardEvent('keydown', { key: 'c', bubbles: true, cancelable: true })
    cmdInput.dispatchEvent(ev)

    expect(ev.defaultPrevented).toBe(true)
    expect(cmdInput.value).toBe('abc')
    expect(cmdInput.selectionStart).toBe(3)
    expect(cmdInput.selectionEnd).toBe(3)
  })

  it('ignores command history and autocomplete while a terminal confirmation is pending', async () => {
    const navigateCmdHistory = vi.fn(() => true)
    const acHide = vi.fn()
    const acShow = vi.fn()
    const hasPendingTerminalConfirm = vi.fn(() => true)
    const { cmdInput, _getAcIndex, _replayPromptShortcutAfterSelection } = await loadAppFns({
      navigateCmdHistory,
      acHide,
      acShow,
      acSuggestions: ['curl http://localhost:5001/health'],
      acFiltered: ['curl http://localhost:5001/health'],
      hasPendingTerminalConfirm,
    })

    Object.defineProperty(document, 'activeElement', {
      configurable: true,
      get: () => cmdInput,
    })

    cmdInput.value = 'cur'
    cmdInput.setSelectionRange(3, 3)
    cmdInput.dispatchEvent(new Event('input', { bubbles: true }))
    expect(acShow).not.toHaveBeenCalled()
    expect(_getAcIndex()).toBe(-1)

    const tabEv = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true })
    cmdInput.dispatchEvent(tabEv)
    expect(tabEv.defaultPrevented).toBe(true)
    expect(cmdInput.value).toBe('cur')
    expect(_getAcIndex()).toBe(-1)

    for (const key of ['ArrowUp', 'ArrowDown']) {
      const ev = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true })
      cmdInput.dispatchEvent(ev)
      expect(ev.defaultPrevented).toBe(true)
    }

    const originalGetSelection = window.getSelection
    Object.defineProperty(document, 'activeElement', {
      configurable: true,
      get: () => document.body,
    })
    Object.defineProperty(window, 'getSelection', {
      configurable: true,
      value: () => ({ toString: () => 'selected output' }),
    })

    try {
      const replayEv = new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true, cancelable: true })
      expect(_replayPromptShortcutAfterSelection(replayEv)).toBe(true)
      expect(replayEv.defaultPrevented).toBe(true)
    } finally {
      Object.defineProperty(window, 'getSelection', {
        configurable: true,
        value: originalGetSelection,
      })
    }

    expect(hasPendingTerminalConfirm).toHaveBeenCalled()
    expect(acHide).toHaveBeenCalled()
    expect(acShow).not.toHaveBeenCalled()
    expect(navigateCmdHistory).not.toHaveBeenCalled()
  })

  it.each([
    {
      key: 'ArrowDown',
      keydown: { key: 'ArrowDown' },
      expectAction: (helpers) => expect(helpers.navigateCmdHistory).toHaveBeenCalledWith(-1),
    },
    {
      key: 'Enter',
      keydown: { key: 'Enter' },
      expectAction: (helpers) =>
        expect(helpers.submitComposerCommand).toHaveBeenCalledWith('ping darklab.sh', {
          dismissKeyboard: true,
        }),
    },
    {
      key: 'Ctrl+R',
      keydown: { key: 'r', ctrlKey: true },
      expectAction: (helpers) => expect(helpers.enterHistSearch).toHaveBeenCalled(),
    },
  ])('replays %s after desktop output text is selected', async ({ keydown, expectAction }) => {
    const navigateCmdHistory = vi.fn(() => false)
    const enterHistSearch = vi.fn()
    const submitComposerCommand = vi.fn()
    const { cmdInput, _replayPromptShortcutAfterSelection, setComposerState } = await loadAppFns({
      navigateCmdHistory,
      enterHistSearch,
      submitComposerCommand,
    })

    const originalGetSelection = window.getSelection
    let activeElement = document.body
    const focusSpy = vi.fn(() => {
      activeElement = cmdInput
    })
    cmdInput.focus = focusSpy
    Object.defineProperty(document, 'activeElement', {
      configurable: true,
      get: () => activeElement,
    })
    Object.defineProperty(window, 'getSelection', {
      configurable: true,
      value: () => ({ toString: () => 'highlighted output' }),
    })

    try {
      cmdInput.value = 'ping darklab.sh'
      setComposerState({
        value: 'ping darklab.sh',
        selectionStart: 'ping darklab.sh'.length,
        selectionEnd: 'ping darklab.sh'.length,
        activeInput: 'desktop',
      })
      const ev = new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...keydown })
      const handled = _replayPromptShortcutAfterSelection(ev)

      expect(handled).toBe(true)
      expect(ev.defaultPrevented).toBe(true)
      expect(focusSpy).toHaveBeenCalled()
      expectAction({ navigateCmdHistory, enterHistSearch, submitComposerCommand })
    } finally {
      Object.defineProperty(window, 'getSelection', {
        configurable: true,
        value: originalGetSelection,
      })
    }
  })

  it('updates the visible cursor when the selection changes without typing', async () => {
    const { cmdInput } = await loadAppFns()
    const shellPromptText = document.getElementById('shell-prompt-text')

    cmdInput.value = 'curl darklab.sh'
    cmdInput.setSelectionRange(4, 4)
    Object.defineProperty(document, 'activeElement', {
      configurable: true,
      get: () => cmdInput,
    })
    document.dispatchEvent(new Event('selectionchange'))

    expect(shellPromptText.textContent).toContain('curl')
    expect(shellPromptText.textContent).toContain('darklab.sh')
    expect(shellPromptText.querySelector('.shell-caret-char')?.textContent || '').toBe(' ')
  })

  it('moves the cursor from composer state instead of stale DOM selection', async () => {
    const { moveCmdCaret, setComposerState } = await loadAppFns()
    const cmdInput = document.getElementById('cmd')

    cmdInput.value = 'abc'
    cmdInput.setSelectionRange(3, 3)
    setComposerState({ value: 'abc', selectionStart: 1, selectionEnd: 1, activeInput: 'desktop' })

    moveCmdCaret(1)

    expect(cmdInput.selectionStart).toBe(2)
    expect(cmdInput.selectionEnd).toBe(2)
    expect(cmdInput.value).toBe('abc')
  })

  it('tracks mobile keyboard state and keeps the prompt visible while typing', async () => {
    const { shellPromptWrap, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 768, offsetTop: 0 },
    })
    const header = document.querySelector('header')
    const status = document.getElementById('status')
    const runBtn = document.getElementById('run-btn')
    const terminalWrap = document.querySelector('.terminal-wrap')
    const mobileShell = document.getElementById('mobile-shell')
    const mobileShellChrome = document.getElementById('mobile-shell-chrome')
    const mobileShellTranscript = document.getElementById('mobile-shell-transcript')
    const mobileShellComposer = document.getElementById('mobile-shell-composer')
    const mobileShellOverlays = document.getElementById('mobile-shell-overlays')
    const mobileComposerHost = document.getElementById('mobile-composer-host')
    const mobileComposerRow = document.getElementById('mobile-composer-row')
    const shellInputRow = document.getElementById('shell-input-row')
    const mobileCmdInput = document.getElementById('mobile-cmd')
    const mobileRunBtn = document.getElementById('mobile-run-btn')
    const histRow = document.getElementById('history-row')
    const terminalBar = document.querySelector('.terminal-bar')
    const searchBar = document.getElementById('search-bar')
    const tabPanels = document.getElementById('tab-panels')
    const historyPanel = document.getElementById('history-panel')
    const faqOverlay = document.getElementById('faq-overlay')
    const optionsOverlay = document.getElementById('options-overlay')

    expect(mobileCmdInput.getAttribute('autocomplete')).toBe('off')
    expect(mobileCmdInput.getAttribute('autocapitalize')).toBe('none')
    expect(mobileCmdInput.getAttribute('autocorrect')).toBe('off')
    expect(mobileCmdInput.getAttribute('spellcheck')).toBe('false')
    expect(mobileCmdInput.getAttribute('inputmode')).toBe('text')

    document.body.classList.add('mobile-terminal-mode')
    Object.defineProperty(document, 'activeElement', {
      configurable: true,
      get: () => mobileCmdInput,
    })
    window.visualViewport.height = 500
    mobileCmdInput.dispatchEvent(new Event('focus'))
    mobileCmdInput.value = 'curl'
    mobileCmdInput.dispatchEvent(new Event('input'))
    window.dispatchEvent(new Event('resize'))
    await new Promise((resolve) => setTimeout(resolve, 10))

    expect(document.body.classList.contains('mobile-terminal-mode')).toBe(true)
    expect(document.body.classList.contains('mobile-keyboard-open')).toBe(true)
    expect(document.documentElement.style.getPropertyValue('--mobile-keyboard-offset')).toBe(
      '268px',
    )
    expect(terminalWrap.hidden).toBe(true)
    expect(mobileShell.hidden).toBe(false)
    expect(runBtn.hidden).toBe(true)
    expect(mobileComposerHost.getAttribute('aria-hidden')).toBe('false')
    expect(shellPromptWrap.getAttribute('aria-hidden')).toBe('true')
    expect(mobileComposerRow.hidden).toBe(false)
    expect(mobileShell.contains(histRow)).toBe(true)
    expect(mobileShell.contains(terminalBar)).toBe(true)
    expect(mobileShell.contains(searchBar)).toBe(true)
    expect(mobileShell.contains(tabPanels)).toBe(true)
    expect(mobileShell.contains(mobileComposerHost)).toBe(true)
    expect(mobileShell.contains(mobileShellChrome)).toBe(true)
    expect(mobileShell.contains(mobileShellTranscript)).toBe(true)
    expect(mobileShell.contains(mobileShellComposer)).toBe(true)
    expect(mobileShell.contains(mobileShellOverlays)).toBe(true)
    expect(header.contains(status)).toBe(true)
    expect(header.contains(document.getElementById('run-timer'))).toBe(true)
    expect(mobileShellChrome.contains(histRow)).toBe(true)
    expect(mobileShellChrome.contains(terminalBar)).toBe(true)
    expect(mobileShellChrome.contains(searchBar)).toBe(true)
    expect(mobileShellTranscript.contains(tabPanels)).toBe(true)
    expect(mobileShellComposer.contains(mobileComposerHost)).toBe(true)
    expect(mobileShellOverlays.contains(historyPanel)).toBe(true)
    expect(mobileShellOverlays.contains(faqOverlay)).toBe(true)
    expect(mobileShellOverlays.contains(optionsOverlay)).toBe(true)
    expect(mobileComposerRow.contains(mobileCmdInput)).toBe(true)
    expect(mobileComposerRow.contains(mobileRunBtn)).toBe(true)
    expect(mobileComposerRow.contains(shellInputRow)).toBe(false)
    expect(runBtn.hidden).toBe(true)
    expect(shellInputRow.hidden).toBe(true)
    expect(shellInputRow.getAttribute('aria-hidden')).toBe('true')
    expect(mobileComposerRow.querySelector('.mobile-prompt-label')?.textContent).toBe('')
    expect(mobileCmdInput.placeholder).toBe('/ · type command')
    expect(shellPromptWrap.scrollIntoView).not.toHaveBeenCalled()

    restoreViewport()
  })

  it('keeps the simplified mobile shell node structure intact while the keyboard is open', async () => {
    const { restoreViewport } = await loadAppFns({
      mobileViewport: { height: 768, offsetTop: 0 },
    })
    try {
      const header = document.querySelector('header')
      const status = document.getElementById('status')
      const runTimer = document.getElementById('run-timer')
      const histRow = document.getElementById('history-row')
      const terminalBar = document.querySelector('.terminal-bar')
      const searchBar = document.getElementById('search-bar')
      const tabPanels = document.getElementById('tab-panels')
      const historyPanel = document.getElementById('history-panel')
      const faqOverlay = document.getElementById('faq-overlay')
      const optionsOverlay = document.getElementById('options-overlay')
      const mobileShell = document.getElementById('mobile-shell')
      const mobileShellChrome = document.getElementById('mobile-shell-chrome')
      const mobileShellTranscript = document.getElementById('mobile-shell-transcript')
      const mobileShellComposer = document.getElementById('mobile-shell-composer')
      const mobileShellOverlays = document.getElementById('mobile-shell-overlays')
      const mobileComposerHost = document.getElementById('mobile-composer-host')
      const mobileCmdInput = document.getElementById('mobile-cmd')

      document.body.classList.add('mobile-terminal-mode')
      Object.defineProperty(document, 'activeElement', {
        configurable: true,
        get: () => mobileCmdInput,
      })
      window.visualViewport.height = 500
      mobileCmdInput.dispatchEvent(new Event('focus'))

      expect(header.contains(status)).toBe(true)
      expect(header.contains(runTimer)).toBe(true)
      expect(mobileShell.contains(mobileShellChrome)).toBe(true)
      expect(mobileShell.contains(mobileShellTranscript)).toBe(true)
      expect(mobileShell.contains(mobileShellComposer)).toBe(true)
      expect(mobileShell.contains(mobileShellOverlays)).toBe(true)
      expect(mobileShellChrome.contains(histRow)).toBe(true)
      expect(mobileShellChrome.contains(terminalBar)).toBe(true)
      expect(mobileShellChrome.contains(searchBar)).toBe(true)
      expect(mobileShellTranscript.contains(tabPanels)).toBe(true)
      expect(mobileShellComposer.contains(mobileComposerHost)).toBe(true)
      expect(mobileShellOverlays.contains(historyPanel)).toBe(true)
      expect(mobileShellOverlays.contains(faqOverlay)).toBe(true)
      expect(mobileShellOverlays.contains(optionsOverlay)).toBe(true)
    } finally {
      restoreViewport()
    }
  })

  it('keeps the active output pinned to the bottom when the mobile keyboard opens', async () => {
    const output = document.createElement('div')
    let scrollTop = 0
    Object.defineProperty(output, 'scrollTop', {
      configurable: true,
      get: () => scrollTop,
      set: (value) => {
        scrollTop = value
      },
    })
    Object.defineProperty(output, 'scrollHeight', {
      configurable: true,
      get: () => 300,
    })
    const { restoreViewport } = await loadAppFns({
      mobileViewport: { height: 768, offsetTop: 0 },
      tabs: [
        {
          id: 'tab-1',
          followOutput: true,
          suppressOutputScrollTracking: false,
          _outputFollowToken: 0,
        },
      ],
      getOutput: () => output,
    })
    try {
      const mobileCmdInput = document.getElementById('mobile-cmd')
      document.body.classList.add('mobile-terminal-mode')
      Object.defineProperty(document, 'activeElement', {
        configurable: true,
        get: () => mobileCmdInput,
      })

      scrollTop = 12
      window.visualViewport.height = 500
      mobileCmdInput.dispatchEvent(new Event('focus'))

      expect(scrollTop).toBe(300)
    } finally {
      restoreViewport()
    }
  })

  it('keeps the active output pinned to the bottom when the mobile keyboard closes', async () => {
    const output = document.createElement('div')
    let scrollTop = 0
    Object.defineProperty(output, 'scrollTop', {
      configurable: true,
      get: () => scrollTop,
      set: (value) => {
        scrollTop = value
      },
    })
    Object.defineProperty(output, 'scrollHeight', {
      configurable: true,
      get: () => 300,
    })
    const { restoreViewport } = await loadAppFns({
      mobileViewport: { height: 768, offsetTop: 0 },
      tabs: [
        {
          id: 'tab-1',
          followOutput: true,
          suppressOutputScrollTracking: false,
          _outputFollowToken: 0,
        },
      ],
      getOutput: () => output,
    })
    try {
      const mobileCmdInput = document.getElementById('mobile-cmd')
      let activeElement = mobileCmdInput
      document.body.classList.add('mobile-terminal-mode')
      Object.defineProperty(document, 'activeElement', {
        configurable: true,
        get: () => activeElement,
      })

      window.visualViewport.height = 500
      mobileCmdInput.dispatchEvent(new Event('focus'))
      expect(scrollTop).toBe(300)

      scrollTop = 12
      activeElement = document.body
      window.visualViewport.height = 768
      mobileCmdInput.dispatchEvent(new Event('blur'))

      expect(scrollTop).toBe(300)
    } finally {
      restoreViewport()
    }
  })

  it('keeps the mobile keyboard helper row visible when the viewport resize lands before focus', async () => {
    const { syncMobileComposerKeyboardState, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 768, offsetTop: 0 },
    })
    const mobileCmdInput = document.getElementById('mobile-cmd')

    document.body.classList.add('mobile-terminal-mode')
    Object.defineProperty(document, 'activeElement', {
      configurable: true,
      get: () => mobileCmdInput,
    })

    syncMobileComposerKeyboardState(0, { active: true })
    syncMobileComposerKeyboardState(268, { active: true })
    expect(document.body.classList.contains('mobile-keyboard-open')).toBe(false)
    expect(document.documentElement.style.getPropertyValue('--mobile-keyboard-offset')).toBe(
      '268px',
    )
    mobileCmdInput.dispatchEvent(new Event('focus'))
    expect(document.body.classList.contains('mobile-keyboard-open')).toBe(true)
    restoreViewport()
  })

  it('does not programmatically focus the mobile composer', async () => {
    const { refocusComposerAfterAction, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    const cmdInput = document.getElementById('cmd')
    const mobileCmdInput = document.getElementById('mobile-cmd')
    document.body.classList.add('mobile-terminal-mode')

    expect(refocusComposerAfterAction({ defer: true })).toBeUndefined()

    expect(mobileCmdInput.focus).not.toHaveBeenCalled()
    expect(cmdInput.focus).not.toHaveBeenCalled()

    restoreViewport()
  })

  it('does not programmatically refocus the mobile composer when the user taps the input', async () => {
    const { getVisibleComposerInput, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    try {
      const visibleInput = getVisibleComposerInput()
      document.body.classList.add('mobile-terminal-mode')

      const ev = new Event('pointerdown', { bubbles: true, cancelable: true })
      Object.assign(ev, { pointerType: 'touch' })
      visibleInput.dispatchEvent(ev)

      expect(visibleInput.focus).not.toHaveBeenCalled()
    } finally {
      restoreViewport()
    }
  })

  it('does not programmatically focus the mobile composer when the user taps the lower composer area', async () => {
    const { restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    try {
      const mobileComposerHost = document.getElementById('mobile-composer-host')
      const mobileCmdInput = document.getElementById('mobile-cmd')
      document.body.classList.add('mobile-terminal-mode')

      const ev = new Event('pointerdown', { bubbles: true, cancelable: true })
      Object.assign(ev, { pointerType: 'touch' })
      mobileComposerHost.dispatchEvent(ev)

      expect(mobileCmdInput.focus).not.toHaveBeenCalled()
    } finally {
      restoreViewport()
    }
  })

  it('prefers the mobile composer as the visible input while mobile mode is active', async () => {
    const { getVisibleComposerInput, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    const mobileCmdInput = document.getElementById('mobile-cmd')
    const cmdInput = document.getElementById('cmd')
    document.body.classList.add('mobile-terminal-mode')

    expect(getVisibleComposerInput()).toBe(mobileCmdInput)
    expect(getVisibleComposerInput()).not.toBe(cmdInput)

    restoreViewport()
  })

  it('does not focus the mobile composer through the shared focus helper', async () => {
    const { focusVisibleComposerInput, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    const mobileCmdInput = document.getElementById('mobile-cmd')
    const cmdInput = document.getElementById('cmd')
    document.body.classList.add('mobile-terminal-mode')

    expect(focusVisibleComposerInput({ preventScroll: true })).toBe(false)
    expect(mobileCmdInput.focus).not.toHaveBeenCalled()
    expect(cmdInput.focus).not.toHaveBeenCalled()

    restoreViewport()
  })

  it('focuses the desktop composer through the shared visible helper', async () => {
    const { focusVisibleComposerInput } = await loadAppFns()
    const cmdInput = document.getElementById('cmd')
    document.body.classList.remove('mobile-terminal-mode')

    expect(focusVisibleComposerInput({ preventScroll: true })).toBe(true)
    expect(cmdInput.focus).toHaveBeenCalled()
  })

  it('blurs the visible mobile composer through the shared blur helper', async () => {
    const { blurVisibleComposerInput, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    const mobileCmdInput = document.getElementById('mobile-cmd')
    document.body.classList.add('mobile-terminal-mode')

    expect(blurVisibleComposerInput()).toBe(true)
    expect(mobileCmdInput.blur).toHaveBeenCalled()

    restoreViewport()
  })

  it('blurs the mobile composer through the shared mobile blur helper', async () => {
    const { blurVisibleComposerInputIfMobile, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    const mobileCmdInput = document.getElementById('mobile-cmd')
    document.body.classList.add('mobile-terminal-mode')

    expect(blurVisibleComposerInputIfMobile()).toBe(true)
    expect(mobileCmdInput.blur).toHaveBeenCalled()

    restoreViewport()
  })

  it('reads the visible mobile composer value through the shared accessor', async () => {
    const { getComposerValue, setComposerState, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    const mobileCmdInput = document.getElementById('mobile-cmd')
    document.body.classList.add('mobile-terminal-mode')

    mobileCmdInput.value = 'curl darklab.sh'
    setComposerState({
      value: 'curl darklab.sh',
      selectionStart: 15,
      selectionEnd: 15,
      activeInput: 'mobile',
    })

    expect(getComposerValue()).toBe('curl darklab.sh')

    restoreViewport()
  })

  it('syncs mobile composer input through the shared input handler', async () => {
    const acShow = vi.fn()
    const { restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
      acShow,
      acSuggestions: ['curl http://localhost:5001/health'],
    })
    const mobileCmdInput = document.getElementById('mobile-cmd')
    const cmdInput = document.getElementById('cmd')
    document.body.classList.add('mobile-terminal-mode')

    mobileCmdInput.value = 'curl'
    mobileCmdInput.dispatchEvent(new Event('input', { bubbles: true }))

    expect(mobileCmdInput.value).toBe('curl')
    expect(cmdInput.value).toBe('')
    expect(acShow).toHaveBeenCalledWith(['curl http://localhost:5001/health'])

    restoreViewport()
  })

  it('exposes the shared composer input handler for visible mobile input changes', async () => {
    const acShow = vi.fn()
    const { handleComposerInputChange, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
      acShow,
      acSuggestions: ['curl http://localhost:5001/health'],
    })
    const mobileCmdInput = document.getElementById('mobile-cmd')
    const cmdInput = document.getElementById('cmd')
    document.body.classList.add('mobile-terminal-mode')

    mobileCmdInput.value = 'curl'
    handleComposerInputChange(mobileCmdInput)

    expect(mobileCmdInput.value).toBe('curl')
    expect(cmdInput.value).toBe('')
    expect(acShow).toHaveBeenCalledWith(['curl http://localhost:5001/health'])

    restoreViewport()
  })

  it('blocks composer input and autocomplete while the active tab is running', async () => {
    const acHide = vi.fn()
    const acShow = vi.fn()
    const { cmdInput, handleComposerInputChange, setComposerValue, getComposerValue } = await loadAppFns({
      tabs: [{ id: 'tab-1', st: 'running' }],
      acHide,
      acShow,
      acSuggestions: ['curl http://localhost:5001/health'],
    })

    expect(setComposerValue('curl', 4, 4)).toBe('')
    expect(getComposerValue()).toBe('')

    cmdInput.value = 'curl'
    cmdInput.setSelectionRange(4, 4)
    handleComposerInputChange(cmdInput)

    expect(cmdInput.value).toBe('')
    expect(getComposerValue()).toBe('')
    expect(acHide).toHaveBeenCalled()
    expect(acShow).not.toHaveBeenCalled()
  })

  it('publishes mobile focus and selection changes into composer state without mirroring the hidden input', async () => {
    const { getComposerState, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    try {
      const mobileCmdInput = document.getElementById('mobile-cmd')
      const cmdInput = document.getElementById('cmd')
      document.body.classList.add('mobile-terminal-mode')

      mobileCmdInput.value = 'curl'
      mobileCmdInput.setSelectionRange(4, 4)
      Object.defineProperty(document, 'activeElement', {
        configurable: true,
        get: () => mobileCmdInput,
      })

      mobileCmdInput.dispatchEvent(new Event('focus'))
      document.dispatchEvent(new Event('selectionchange'))

      expect(getComposerState()).toEqual({
        value: 'curl',
        selectionStart: 4,
        selectionEnd: 4,
        activeInput: 'mobile',
      })
      expect(cmdInput.value).toBe('')
    } finally {
      restoreViewport()
    }
  })

  it('does not enter mobile mode on a narrow desktop viewport without touch support', async () => {
    const { cmdInput, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
      mobileTouch: false,
    })

    cmdInput.dispatchEvent(new Event('focus'))

    expect(document.body.classList.contains('mobile-terminal-mode')).toBe(false)
    expect(document.body.classList.contains('mobile-keyboard-open')).toBe(false)

    restoreViewport()
  })

  it('sets the document title from the server config', async () => {
    await loadAppFns()
    await Promise.resolve()
    await Promise.resolve()

    expect(document.title).toBe('darklab_shell')
  })

  it('keeps the mobile run button visible after the keyboard closes', async () => {
    const { restoreViewport } = await loadAppFns({
      mobileViewport: { height: 768, offsetTop: 0 },
    })
    const runBtn = document.getElementById('run-btn')
    const mobileCmdInput = document.getElementById('mobile-cmd')

    Object.defineProperty(document, 'activeElement', {
      configurable: true,
      get: () => mobileCmdInput,
    })
    window.visualViewport.height = 500
    mobileCmdInput.dispatchEvent(new Event('focus'))
    expect(runBtn.hidden).toBe(true)

    Object.defineProperty(window, 'visualViewport', {
      configurable: true,
      value: {
        height: 768,
        offsetTop: 0,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      },
    })
    Object.defineProperty(document, 'activeElement', {
      configurable: true,
      get: () => document.body,
    })
    mobileCmdInput.dispatchEvent(new Event('blur'))

    expect(document.body.classList.contains('mobile-terminal-mode')).toBe(true)
    expect(document.body.classList.contains('mobile-keyboard-open')).toBe(false)
    expect(runBtn.hidden).toBe(true)

    restoreViewport()
  })

  it('submits the visible mobile composer through the shared submit helper', async () => {
    const submitVisibleComposerCommand = vi.fn(() => true)
    const runCommand = vi.fn()
    const { restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
      submitVisibleComposerCommand,
      runCommand,
    })
    const mobileCmdInput = document.getElementById('mobile-cmd')
    const mobileRunBtn = document.getElementById('mobile-run-btn')

    mobileCmdInput.dispatchEvent(new Event('focus'))
    mobileCmdInput.value = 'curl darklab.sh'
    mobileCmdInput.dispatchEvent(new Event('input'))
    mobileRunBtn.click()

    expect(submitVisibleComposerCommand).toHaveBeenCalledWith({
      dismissKeyboard: true,
      focusAfterSubmit: false,
    })
    expect(runCommand).not.toHaveBeenCalled()

    restoreViewport()
  })

  it('keeps the desktop and mobile run buttons in sync when disabled', async () => {
    const { setRunButtonDisabled } = await loadAppFns()
    const runBtn = document.getElementById('run-btn')
    const mobileRunBtn = document.getElementById('mobile-run-btn')

    setRunButtonDisabled(true)
    expect(runBtn.disabled).toBe(true)
    expect(mobileRunBtn.disabled).toBe(true)

    setRunButtonDisabled(false)
    expect(runBtn.disabled).toBe(false)
    expect(mobileRunBtn.disabled).toBe(false)
  })

  it('keeps the mobile composer host free of keyboard-height spacing in the simplified shell', () => {
    const css = readFileSync(resolve(REPO_ROOT, 'app/static/css/mobile.css'), 'utf8')
    const match = css.match(/body\.mobile-terminal-mode #mobile-composer-host\s*\{([\s\S]*?)\}/)

    expect(match).not.toBeNull()
    expect(match[1]).not.toMatch(/margin-bottom\s*:/)
  })

  it('keeps the themed mobile composer surfaces free of hard-coded dark colors', () => {
    const css = readFileSync(resolve(REPO_ROOT, 'app/static/css/mobile.css'), 'utf8')
    const shellMatch = css.match(
      /body\.mobile-terminal-mode #mobile-shell-composer\s*\{([\s\S]*?)\}/,
    )
    const composerMatch = css.match(
      /body\.mobile-terminal-mode #mobile-shell-composer #mobile-composer\s*\{([\s\S]*?)\}/,
    )

    expect(shellMatch).not.toBeNull()
    expect(shellMatch[1]).toMatch(/background:\s*transparent/)
    expect(shellMatch[1]).not.toMatch(/rgba\(13,13,13/)

    expect(composerMatch).not.toBeNull()
    expect(composerMatch[1]).toMatch(/background:\s*var\(--theme-panel-bg\)/)
    expect(composerMatch[1]).toMatch(/border:\s*1px solid var\(--theme-panel-border\)/)
    expect(composerMatch[1]).toMatch(/box-shadow:\s*0 10px 30px var\(--theme-panel-shadow\)/)
    expect(composerMatch[1]).not.toMatch(/rgba\(13,13,13/)
  })

  it('disables both run buttons for an empty command and enables them once input is present', async () => {
    const { handleComposerInputChange, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    try {
      const runBtn = document.getElementById('run-btn')
      const mobileRunBtn = document.getElementById('mobile-run-btn')
      const mobileCmdInput = document.getElementById('mobile-cmd')
      document.body.classList.add('mobile-terminal-mode')

      expect(runBtn.disabled).toBe(true)
      expect(mobileRunBtn.disabled).toBe(true)

      mobileCmdInput.value = 'ping darklab.sh'
      mobileCmdInput.setSelectionRange(mobileCmdInput.value.length, mobileCmdInput.value.length)
      handleComposerInputChange(mobileCmdInput)

      expect(runBtn.disabled).toBe(false)
      expect(mobileRunBtn.disabled).toBe(false)

      mobileCmdInput.value = '   '
      mobileCmdInput.setSelectionRange(mobileCmdInput.value.length, mobileCmdInput.value.length)
      handleComposerInputChange(mobileCmdInput)

      expect(runBtn.disabled).toBe(true)
      expect(mobileRunBtn.disabled).toBe(true)
    } finally {
      restoreViewport()
    }
  })

  it('keeps both run buttons in sync for programmatic composer value changes', async () => {
    const { setComposerValue } = await loadAppFns()
    const runBtn = document.getElementById('run-btn')
    const mobileRunBtn = document.getElementById('mobile-run-btn')

    expect(runBtn.disabled).toBe(true)
    expect(mobileRunBtn.disabled).toBe(true)

    setComposerValue('ping darklab.sh', 15, 15, { dispatch: false })
    expect(runBtn.disabled).toBe(false)
    expect(mobileRunBtn.disabled).toBe(false)

    setComposerValue('   ', 3, 3, { dispatch: false })
    expect(runBtn.disabled).toBe(true)
    expect(mobileRunBtn.disabled).toBe(true)
  })

  it('closes transient ui while the mobile keyboard is open', async () => {
    const { restoreViewport } = await loadAppFns({
      mobileViewport: { height: 768, offsetTop: 0 },
    })
    const mobileCmdInput = document.getElementById('mobile-cmd')

    const menuSheet = document.getElementById('mobile-menu-sheet')
    menuSheet.classList.remove('u-hidden')
    document.getElementById('history-panel').classList.add('open')

    Object.defineProperty(document, 'activeElement', {
      configurable: true,
      get: () => mobileCmdInput,
    })
    window.visualViewport.height = 500
    mobileCmdInput.dispatchEvent(new Event('focus'))
    mobileCmdInput.value = 'curl'
    mobileCmdInput.dispatchEvent(new Event('input'))

    expect(menuSheet.classList.contains('u-hidden')).toBe(true)
    expect(document.getElementById('history-panel').classList.contains('open')).toBe(false)

    restoreViewport()
  })

  it('matches autocomplete suggestions from the beginning of each command only', async () => {
    const acShow = vi.fn()
    const apiFetch = vi.fn((url) => {
      if (url === '/autocomplete') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              suggestions: ['curl http://localhost:5001/health', 'man curl', 'cat /etc/hosts'],
            }),
        })
      }
      if (url === '/config') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              app_name: 'darklab_shell',
              prompt_username: 'anon',
              prompt_domain: 'darklab.sh',
              version: '9.9',
              default_theme: 'darklab_obsidian.yaml',
              motd: '',
              command_timeout_seconds: 0,
              max_output_lines: 0,
              permalink_retention_days: 0,
            }),
        })
      }
      if (url === '/allowed-commands' || url === '/faq') {
        return Promise.resolve({
          json: () => Promise.resolve({ restricted: false, commands: [], groups: [], items: [] }),
        })
      }
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })
    const { cmdInput } = await loadAppFns({
      acShow,
      apiFetch,
    })
    await Promise.resolve()
    await Promise.resolve()

    cmdInput.value = 'cur'
    cmdInput.dispatchEvent(new Event('input'))

    expect(acShow).toHaveBeenCalledWith(['curl http://localhost:5001/health'])

    acShow.mockClear()
    cmdInput.value = 'man'
    cmdInput.dispatchEvent(new Event('input'))

    expect(acShow).toHaveBeenCalledWith(['man curl'])
  })

  it('hides autocomplete when the typed command exactly matches a suggestion', async () => {
    const acHide = vi.fn()
    const { cmdInput } = await loadAppFns({
      acSuggestions: ['man curl', 'curl http://localhost:5001/health'],
      acHide,
    })

    cmdInput.value = 'man curl'
    cmdInput.dispatchEvent(new Event('input'))

    expect(acHide).toHaveBeenCalled()
    expect(document.getElementById('ac-dropdown').style.display).toBe('none')
  })

  it('prefers contextual autocomplete suggestions after the command root', async () => {
    const acShow = vi.fn()
    const { cmdInput } = await loadAppFns({
      getAutocompleteMatches: () => [
        { value: '-sV', description: 'Service detection', replaceStart: 5, replaceEnd: 6 },
        { value: '-Pn', description: 'Skip host discovery', replaceStart: 5, replaceEnd: 6 },
      ],
      acShow,
    })

    cmdInput.value = 'nmap -'
    cmdInput.setSelectionRange(6, 6)
    cmdInput.dispatchEvent(new Event('input'))

    expect(acShow).toHaveBeenCalled()
    const [items] = acShow.mock.calls.at(-1)
    expect(items.map((item) => item.value)).toEqual(['-sV', '-Pn'])
  })

  it('suppresses duplicate contextual flags that were already used in the command', async () => {
    const acShow = vi.fn()
    const { cmdInput } = await loadAppFns({
      getAutocompleteMatches: () => [
        { value: '-sV', description: 'Service detection', replaceStart: 9, replaceEnd: 10 },
      ],
      acShow,
    })

    cmdInput.value = 'nmap -Pn -'
    cmdInput.setSelectionRange(10, 10)
    cmdInput.dispatchEvent(new Event('input'))

    const [items] = acShow.mock.calls.at(-1)
    expect(items.map((item) => item.value)).toEqual(['-sV'])
  })

  it('renders cursor and selection state from composer state', async () => {
    const { cmdInput, setComposerState, syncShellPrompt } = await loadAppFns()
    const shellPromptText = document.getElementById('shell-prompt-text')
    const shellPromptWrap = document.getElementById('shell-prompt-wrap')

    cmdInput.value = 'stale'
    cmdInput.setSelectionRange(0, 0)
    setComposerState({
      value: 'nothing',
      selectionStart: 3,
      selectionEnd: 3,
      activeInput: 'desktop',
    })
    syncShellPrompt()
    expect(shellPromptText.querySelector('.shell-caret-char')?.textContent).toBe('h')
    expect(shellPromptWrap.classList.contains('shell-prompt-has-selection')).toBe(false)

    setComposerState({
      selectionStart: 1,
      selectionEnd: 4,
    })
    syncShellPrompt()
    expect(shellPromptText.querySelector('.shell-prompt-selection')?.textContent).toBe('oth')
    expect(shellPromptWrap.classList.contains('shell-prompt-has-selection')).toBe(true)
  })

  it('refreshes prompt rendering from the focused input before drawing the caret', async () => {
    const { cmdInput, setComposerState, syncShellPrompt } = await loadAppFns()
    const shellPromptText = document.getElementById('shell-prompt-text')
    const shellPromptWrap = document.getElementById('shell-prompt-wrap')

    setComposerState({
      value: 'stale text',
      selectionStart: 10,
      selectionEnd: 10,
      activeInput: 'desktop',
    })
    cmdInput.value = ''
    cmdInput.setSelectionRange(0, 0)
    const activeElementSpy = vi.spyOn(document, 'activeElement', 'get').mockReturnValue(cmdInput)

    syncShellPrompt()

    expect(shellPromptText.textContent).toBe('')
    expect(shellPromptWrap.classList.contains('shell-prompt-empty')).toBe(true)
    expect(shellPromptWrap.classList.contains('shell-prompt-has-value')).toBe(false)
    activeElementSpy.mockRestore()
  })

  it('supports ctrl+w to delete one word to the left', async () => {
    const { cmdInput, setComposerState } = await loadAppFns()

    cmdInput.value = 'dig darklab.sh A'
    cmdInput.focus()
    cmdInput.setSelectionRange(cmdInput.value.length, cmdInput.value.length)
    setComposerState({
      value: 'dig darklab.sh A',
      selectionStart: cmdInput.value.length,
      selectionEnd: cmdInput.value.length,
      activeInput: 'desktop',
    })
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'w', ctrlKey: true, bubbles: true }))

    expect(cmdInput.value).toBe('dig darklab.sh ')
  })

  it('supports ctrl+w with punctuation-delimited terminal words', async () => {
    const { cmdInput, setComposerState } = await loadAppFns()

    cmdInput.value = 'cat /tmp/darklab_findings(1).txt'
    cmdInput.focus()
    cmdInput.setSelectionRange(cmdInput.value.length, cmdInput.value.length)
    setComposerState({
      value: cmdInput.value,
      selectionStart: cmdInput.value.length,
      selectionEnd: cmdInput.value.length,
      activeInput: 'desktop',
    })
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'w', ctrlKey: true, bubbles: true }))

    expect(cmdInput.value).toBe('cat /tmp/darklab_findings(1).')
  })

  it('supports ctrl+u to delete to the beginning of the line', async () => {
    const { cmdInput, setComposerState } = await loadAppFns()

    cmdInput.value = 'dig darklab.sh A'
    cmdInput.setSelectionRange(12, 12)
    setComposerState({
      value: 'dig darklab.sh A',
      selectionStart: 12,
      selectionEnd: 12,
      activeInput: 'desktop',
    })
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'u', ctrlKey: true, bubbles: true }))

    expect(cmdInput.value).toBe('sh A')
    expect(cmdInput.selectionStart).toBe(0)
    expect(cmdInput.selectionEnd).toBe(0)
  })

  it('supports ctrl+a to move to the beginning of the line', async () => {
    const { cmdInput } = await loadAppFns()

    cmdInput.value = 'dig darklab.sh A'
    cmdInput.setSelectionRange(9, 9)
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'a', ctrlKey: true, bubbles: true }))

    expect(cmdInput.selectionStart).toBe(0)
    expect(cmdInput.selectionEnd).toBe(0)
  })

  it('supports ctrl+k to delete to the end of the line', async () => {
    const { cmdInput, setComposerState } = await loadAppFns()

    cmdInput.value = 'dig darklab.sh A'
    cmdInput.setSelectionRange(4, 4)
    setComposerState({
      value: 'dig darklab.sh A',
      selectionStart: 4,
      selectionEnd: 4,
      activeInput: 'desktop',
    })
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true, bubbles: true }))

    expect(cmdInput.value).toBe('dig ')
    expect(cmdInput.selectionStart).toBe(4)
    expect(cmdInput.selectionEnd).toBe(4)
  })

  it('supports ctrl+e to move to the end of the line', async () => {
    const { cmdInput, setComposerState } = await loadAppFns()

    cmdInput.value = 'dig darklab.sh A'
    cmdInput.setSelectionRange(4, 4)
    setComposerState({
      value: 'dig darklab.sh A',
      selectionStart: 4,
      selectionEnd: 4,
      activeInput: 'desktop',
    })
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'e', ctrlKey: true, bubbles: true }))

    expect(cmdInput.selectionStart).toBe(cmdInput.value.length)
    expect(cmdInput.selectionEnd).toBe(cmdInput.value.length)
  })

  it('supports Alt+B and Alt+F to move by word', async () => {
    const { cmdInput, setComposerState } = await loadAppFns()

    cmdInput.value = 'dig darklab.sh A'
    cmdInput.setSelectionRange(cmdInput.value.length, cmdInput.value.length)
    setComposerState({
      value: 'dig darklab.sh A',
      selectionStart: cmdInput.value.length,
      selectionEnd: cmdInput.value.length,
      activeInput: 'desktop',
    })
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'b', altKey: true, bubbles: true }))
    expect(cmdInput.selectionStart).toBe(15)
    expect(cmdInput.selectionEnd).toBe(15)

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'b', altKey: true, bubbles: true }))
    expect(cmdInput.selectionStart).toBe(12)
    expect(cmdInput.selectionEnd).toBe(12)

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'f', altKey: true, bubbles: true }))
    expect(cmdInput.selectionStart).toBe(14)
    expect(cmdInput.selectionEnd).toBe(14)
  })

  it('treats punctuation as word boundaries for terminal word movement', async () => {
    const { cmdInput, setComposerState } = await loadAppFns()
    const value = 'cat /tmp/darklab_findings(1).txt'

    cmdInput.value = value
    cmdInput.setSelectionRange(value.length, value.length)
    setComposerState({
      value,
      selectionStart: value.length,
      selectionEnd: value.length,
      activeInput: 'desktop',
    })

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'b', altKey: true, bubbles: true }))
    expect(cmdInput.selectionStart).toBe(29)

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'b', altKey: true, bubbles: true }))
    expect(cmdInput.selectionStart).toBe(26)

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'b', altKey: true, bubbles: true }))
    expect(cmdInput.selectionStart).toBe(17)

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'f', altKey: true, bubbles: true }))
    expect(cmdInput.selectionStart).toBe(25)
  })

  it('supports macOS Option+B and Option+F word movement via physical key codes', async () => {
    const { cmdInput, setComposerState } = await loadAppFns()

    cmdInput.value = 'dig darklab.sh A'
    cmdInput.setSelectionRange(cmdInput.value.length, cmdInput.value.length)
    setComposerState({
      value: 'dig darklab.sh A',
      selectionStart: cmdInput.value.length,
      selectionEnd: cmdInput.value.length,
      activeInput: 'desktop',
    })
    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: '∫',
        code: 'KeyB',
        altKey: true,
        bubbles: true,
      }),
    )
    expect(cmdInput.selectionStart).toBe(15)

    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'ƒ',
        code: 'KeyF',
        altKey: true,
        bubbles: true,
      }),
    )
    expect(cmdInput.selectionStart).toBe(16)
  })

  it('supports the mobile keyboard helper edit actions', async () => {
    const { getVisibleComposerInput, performMobileEditAction, setComposerState } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })

    document.body.classList.add('mobile-terminal-mode')
    const cmdInput = document.getElementById('cmd')
    const mobileCmdInput = document.getElementById('mobile-cmd')
    cmdInput.value = 'ping -c 4 example.com'
    mobileCmdInput.value = 'ping -c 4 example.com'
    cmdInput.setSelectionRange(cmdInput.value.length, cmdInput.value.length)
    mobileCmdInput.setSelectionRange(mobileCmdInput.value.length, mobileCmdInput.value.length)
    setComposerState({
      value: mobileCmdInput.value,
      selectionStart: mobileCmdInput.value.length,
      selectionEnd: mobileCmdInput.value.length,
      activeInput: 'mobile',
    })
    const visibleInput = getVisibleComposerInput()

    performMobileEditAction('left')
    expect(visibleInput.selectionStart).toBe(visibleInput.value.length - 1)

    performMobileEditAction('home')
    expect(visibleInput.selectionStart).toBe(0)

    performMobileEditAction('word-right')
    expect(visibleInput.selectionStart).toBe(4)

    performMobileEditAction('right')
    expect(visibleInput.selectionStart).toBe(5)

    performMobileEditAction('word-left')
    expect(visibleInput.selectionStart).toBe(0)

    performMobileEditAction('end')
    expect(visibleInput.selectionStart).toBe(visibleInput.value.length)

    performMobileEditAction('delete-word')
    expect(visibleInput.value).toBe('ping -c 4 example.')

    performMobileEditAction('delete-line')
    expect(visibleInput.value).toBe('')
    expect(visibleInput.selectionStart).toBe(0)
  })

  it('keeps the mobile composer scrolled to the caret when helper navigation moves through long input', async () => {
    const { getVisibleComposerInput, performMobileEditAction, setComposerState } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })

    document.body.classList.add('mobile-terminal-mode')
    const mobileCmdInput = document.getElementById('mobile-cmd')
    const longValue =
      'curl https://example.com/healthcheck/with/a/very/long/path?token=abcdef1234567890'
    mobileCmdInput.value = longValue
    mobileCmdInput.setSelectionRange(0, 0)
    mobileCmdInput.scrollLeft = 0
    Object.defineProperty(mobileCmdInput, 'clientWidth', { value: 140, configurable: true })
    setComposerState({
      value: longValue,
      selectionStart: 0,
      selectionEnd: 0,
      activeInput: 'mobile',
    })
    const visibleInput = getVisibleComposerInput()

    performMobileEditAction('end')
    expect(visibleInput.selectionStart).toBe(longValue.length)
    expect(visibleInput.scrollLeft).toBeGreaterThan(0)

    performMobileEditAction('home')
    expect(visibleInput.selectionStart).toBe(0)
    expect(visibleInput.scrollLeft).toBe(0)
  })

  it('uses Ctrl+C to open kill confirm when active tab is running', async () => {
    const confirmKill = vi.fn()
    const { cmdInput, interruptPromptLine } = await loadAppFns({
      tabs: [{ id: 'tab-1', st: 'running' }],
      confirmKill,
    })

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'c', ctrlKey: true, bubbles: true }))

    expect(confirmKill).toHaveBeenCalledWith('tab-1')
    expect(interruptPromptLine).not.toHaveBeenCalled()
  })

  it('swallows composer keydown while the active tab is running', async () => {
    const acHide = vi.fn()
    const createTab = vi.fn(() => 'tab-2')
    const openProjectWorkspace = vi.fn(() => Promise.resolve(true))
    const clearTab = vi.fn()
    const closeTab = vi.fn()
    const { cmdInput } = await loadAppFns({
      tabs: [{ id: 'tab-1', st: 'running' }],
      acHide,
      createTab,
      openProjectWorkspace,
      clearTab,
      closeTab,
    })

    const ev = new KeyboardEvent('keydown', { key: 'a', bubbles: true, cancelable: true })
    cmdInput.dispatchEvent(ev)

    expect(ev.defaultPrevented).toBe(true)
    expect(acHide).toHaveBeenCalled()

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 't', altKey: true, bubbles: true }))
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'p', altKey: true, bubbles: true }))
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'l', ctrlKey: true, bubbles: true }))
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'd', ctrlKey: true, bubbles: true }))

    expect(createTab).toHaveBeenCalledTimes(1)
    expect(createTab).toHaveBeenCalledWith('shell 2')
    expect(openProjectWorkspace).toHaveBeenCalledTimes(1)
    expect(clearTab).toHaveBeenCalledTimes(1)
    expect(clearTab).toHaveBeenCalledWith('tab-1', { preserveRunState: true })
    expect(closeTab).not.toHaveBeenCalled()
  })

  it('uses Ctrl+C to jump to a new prompt line when no command is running', async () => {
    const interruptPromptLine = vi.fn()
    const { cmdInput, confirmKill } = await loadAppFns({
      tabs: [{ id: 'tab-1', st: 'idle' }],
      interruptPromptLine,
    })

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'c', ctrlKey: true, bubbles: true }))

    expect(interruptPromptLine).toHaveBeenCalledWith('tab-1')
    expect(confirmKill).not.toHaveBeenCalled()
  })

  it('uses Ctrl+C to cancel a pending terminal confirmation before opening a fresh prompt', async () => {
    const interruptPromptLine = vi.fn()
    const cancelPendingTerminalConfirm = vi.fn(() => true)
    const hasPendingTerminalConfirm = vi.fn(() => true)
    const { cmdInput, confirmKill } = await loadAppFns({
      tabs: [{ id: 'tab-1', st: 'idle' }],
      interruptPromptLine,
      hasPendingTerminalConfirm,
      cancelPendingTerminalConfirm,
    })

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'c', ctrlKey: true, bubbles: true }))

    expect(hasPendingTerminalConfirm).toHaveBeenCalled()
    expect(cancelPendingTerminalConfirm).toHaveBeenCalledWith('tab-1')
    expect(interruptPromptLine).not.toHaveBeenCalled()
    expect(confirmKill).not.toHaveBeenCalled()
  })

  it('supports Alt+T to create a new tab from the terminal prompt', async () => {
    const createTab = vi.fn(() => 'tab-2')
    const { cmdInput } = await loadAppFns({
      createTab,
      tabs: [{ id: 'tab-1', st: 'idle' }],
    })
    createTab.mockClear()

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 't', altKey: true, bubbles: true }))

    expect(createTab).toHaveBeenCalledWith('shell 2')
  })

  it('supports macOS Option+T to create a new tab via physical key code', async () => {
    const createTab = vi.fn(() => 'tab-2')
    const { cmdInput } = await loadAppFns({
      createTab,
      tabs: [{ id: 'tab-1', st: 'idle' }],
    })
    createTab.mockClear()

    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: '†',
        code: 'KeyT',
        altKey: true,
        bubbles: true,
      }),
    )

    expect(createTab).toHaveBeenCalledWith('shell 2')
  })

  it('opens Atlas Quick Lookup with Alt+Q and the macOS Option+Q glyph fallback', async () => {
    const openAtlasQuickLookup = vi.fn(() => Promise.resolve(true))
    const { cmdInput } = await loadAppFns({
      openAtlasQuickLookup,
      tabs: [{ id: 'tab-1', st: 'idle' }],
    })

    const altEvent = new KeyboardEvent('keydown', {
      key: 'q',
      code: 'KeyQ',
      altKey: true,
      bubbles: true,
      cancelable: true,
    })
    cmdInput.dispatchEvent(altEvent)
    expect(altEvent.defaultPrevented).toBe(true)

    const optionGlyphEvent = new KeyboardEvent('keydown', {
      key: 'œ',
      altKey: true,
      bubbles: true,
      cancelable: true,
    })
    cmdInput.dispatchEvent(optionGlyphEvent)

    expect(optionGlyphEvent.defaultPrevented).toBe(true)
    expect(openAtlasQuickLookup).toHaveBeenCalledTimes(2)
    expect(openAtlasQuickLookup).toHaveBeenNthCalledWith(1, { source: 'shortcut', toggle: true })
    expect(openAtlasQuickLookup).toHaveBeenNthCalledWith(2, { source: 'shortcut', toggle: true })
    expect(cmdInput.value).toBe('')
  })

  it('supports Alt+W and Ctrl+D to close the active tab', async () => {
    const closeTab = vi.fn()
    const { cmdInput } = await loadAppFns({
      closeTab,
      tabs: [{ id: 'tab-1', st: 'idle' }],
    })

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'w', altKey: true, bubbles: true }))
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'd', ctrlKey: true, bubbles: true }))

    expect(closeTab).toHaveBeenCalledTimes(2)
    expect(closeTab).toHaveBeenNthCalledWith(1, 'tab-1')
    expect(closeTab).toHaveBeenNthCalledWith(2, 'tab-1')
  })

  it('supports macOS Option+W to close the active tab via physical key code', async () => {
    const closeTab = vi.fn()
    const { cmdInput } = await loadAppFns({
      closeTab,
      tabs: [{ id: 'tab-1', st: 'idle' }],
    })

    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: '∑',
        code: 'KeyW',
        altKey: true,
        bubbles: true,
      }),
    )

    expect(closeTab).toHaveBeenCalledWith('tab-1')
  })

  it('supports Alt+ArrowLeft and Alt+ArrowRight to move by word', async () => {
    const activateTab = vi.fn()
    const { cmdInput, getComposerState, handleComposerWordArrowShortcut, setComposerValue } = await loadAppFns({
      activateTab,
      activeTabId: 'tab-2',
      tabs: [
        { id: 'tab-1', st: 'idle' },
        { id: 'tab-2', st: 'idle' },
        { id: 'tab-3', st: 'idle' },
      ],
    })

    setComposerValue('dig darklab.sh A', 16, 16, { dispatch: false })
    cmdInput.focus()

    expect(handleComposerWordArrowShortcut({
      key: 'ArrowLeft',
      code: 'ArrowLeft',
      altKey: true,
      ctrlKey: false,
      metaKey: false,
      shiftKey: false,
      preventDefault: vi.fn(),
      stopPropagation: vi.fn(),
    })).toBe(true)
    expect(getComposerState().selectionStart).toBe(15)
    expect(getComposerState().selectionEnd).toBe(15)

    handleComposerWordArrowShortcut({
      key: 'ArrowLeft',
      code: 'ArrowLeft',
      altKey: true,
      ctrlKey: false,
      metaKey: false,
      shiftKey: false,
      preventDefault: vi.fn(),
      stopPropagation: vi.fn(),
    })
    expect(getComposerState().selectionStart).toBe(12)
    expect(getComposerState().selectionEnd).toBe(12)

    handleComposerWordArrowShortcut({
      key: 'ArrowRight',
      code: 'ArrowRight',
      altKey: true,
      ctrlKey: false,
      metaKey: false,
      shiftKey: false,
      preventDefault: vi.fn(),
      stopPropagation: vi.fn(),
    })
    expect(getComposerState().selectionStart).toBe(14)
    expect(getComposerState().selectionEnd).toBe(14)
    expect(activateTab).not.toHaveBeenCalled()
  })

  it('supports Shift+Alt+ArrowLeft and Shift+Alt+ArrowRight to cycle between tabs', async () => {
    const activateTab = vi.fn()
    const { cmdInput } = await loadAppFns({
      activateTab,
      activeTabId: 'tab-2',
      tabs: [
        { id: 'tab-1', st: 'idle' },
        { id: 'tab-2', st: 'idle' },
        { id: 'tab-3', st: 'idle' },
      ],
    })

    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'ArrowRight', code: 'ArrowRight', altKey: true, shiftKey: true, bubbles: true }),
    )
    expect(activateTab).toHaveBeenCalledWith('tab-3')

    activateTab.mockClear()
    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'ArrowLeft', code: 'ArrowLeft', altKey: true, shiftKey: true, bubbles: true }),
    )
    expect(activateTab).toHaveBeenCalledWith('tab-1')
  })

  it('routes Option+Tab through open modal tab sets before terminal tabs', async () => {
    const activateTab = vi.fn()
    const cycleAtlasTab = vi.fn(() => true)
    const { handleTabShortcut, cmdInput } = await loadAppFns({
      activateTab,
      isAtlasOverlayOpen: () => true,
      cycleAtlasTab,
      activeTabId: 'tab-1',
      tabs: [
        { id: 'tab-1', st: 'idle' },
        { id: 'tab-2', st: 'idle' },
      ],
    })

    handleTabShortcut({
      key: 'Tab',
      altKey: true,
      ctrlKey: false,
      metaKey: false,
      shiftKey: false,
      target: cmdInput,
      preventDefault: vi.fn(),
    })
    handleTabShortcut({
      key: 'Tab',
      altKey: true,
      ctrlKey: false,
      metaKey: false,
      shiftKey: true,
      target: cmdInput,
      preventDefault: vi.fn(),
    })

    expect(cycleAtlasTab).toHaveBeenNthCalledWith(1, 1)
    expect(cycleAtlasTab).toHaveBeenNthCalledWith(2, -1)
    expect(activateTab).not.toHaveBeenCalled()
  })

  it('cycles modal tabs from non-terminal inputs', async () => {
    const activateTab = vi.fn()
    const cycleProjectWorkspaceTab = vi.fn(() => true)
    const { handleTabShortcut } = await loadAppFns({
      activateTab,
      isProjectWorkspaceOpen: () => true,
      cycleProjectWorkspaceTab,
      activeTabId: 'tab-1',
      tabs: [
        { id: 'tab-1', st: 'idle' },
        { id: 'tab-2', st: 'idle' },
      ],
    })
    const modalInput = document.createElement('input')

    handleTabShortcut({
      key: 'Tab',
      altKey: true,
      ctrlKey: false,
      metaKey: false,
      shiftKey: false,
      target: modalInput,
      preventDefault: vi.fn(),
    })

    expect(cycleProjectWorkspaceTab).toHaveBeenCalledWith(1)
    expect(activateTab).not.toHaveBeenCalled()

    const activateTabForOptions = vi.fn()
    const { activateOptionsTab, handleTabShortcut: handleOptionsTabShortcut } = await loadAppFns({
      activateTab: activateTabForOptions,
      activeTabId: 'tab-1',
      tabs: [
        { id: 'tab-1', st: 'idle' },
        { id: 'tab-2', st: 'idle' },
      ],
    })
    activateOptionsTab('teams', { persist: false })
    document.getElementById('options-overlay').classList.add('open')
    const preventDefault = vi.fn()

    handleOptionsTabShortcut({
      key: 'Tab',
      altKey: true,
      ctrlKey: false,
      metaKey: false,
      shiftKey: true,
      target: modalInput,
      preventDefault,
    })

    expect(document.getElementById('options-tab-secrets').getAttribute('aria-selected')).toBe('true')
    expect(preventDefault).toHaveBeenCalled()
    expect(activateTabForOptions).not.toHaveBeenCalled()
  })

  it('uses the top open modal tab set when multiple tabbed surfaces are present', async () => {
    const activateTab = vi.fn()
    const cycleHistoryRunOverlayTab = vi.fn(() => true)
    const cycleAtlasTab = vi.fn(() => true)
    const cycleProjectWorkspaceTab = vi.fn(() => true)
    const { handleTabShortcut, cmdInput } = await loadAppFns({
      activateTab,
      isHistoryRunOverlayOpen: () => true,
      cycleHistoryRunOverlayTab,
      isAtlasOverlayOpen: () => true,
      cycleAtlasTab,
      isProjectWorkspaceOpen: () => true,
      cycleProjectWorkspaceTab,
      activeTabId: 'tab-1',
      tabs: [
        { id: 'tab-1', st: 'idle' },
        { id: 'tab-2', st: 'idle' },
      ],
    })

    handleTabShortcut({
      key: 'Tab',
      altKey: true,
      ctrlKey: false,
      metaKey: false,
      shiftKey: false,
      target: cmdInput,
      preventDefault: vi.fn(),
    })

    expect(cycleHistoryRunOverlayTab).toHaveBeenCalledWith(1)
    expect(cycleAtlasTab).not.toHaveBeenCalled()
    expect(cycleProjectWorkspaceTab).not.toHaveBeenCalled()
    expect(activateTab).not.toHaveBeenCalled()
  })

  it('supports Alt+digit to jump directly to a tab', async () => {
    const activateTab = vi.fn()
    const { cmdInput } = await loadAppFns({
      activateTab,
      tabs: [
        { id: 'tab-1', st: 'idle' },
        { id: 'tab-2', st: 'idle' },
        { id: 'tab-3', st: 'idle' },
      ],
    })

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: '3', altKey: true, bubbles: true }))

    expect(activateTab).toHaveBeenCalledWith('tab-3')
  })

  it('supports macOS Option+digit tab jumps via physical key code', async () => {
    const activateTab = vi.fn()
    const { cmdInput } = await loadAppFns({
      activateTab,
      tabs: [
        { id: 'tab-1', st: 'idle' },
        { id: 'tab-2', st: 'idle' },
        { id: 'tab-3', st: 'idle' },
      ],
    })

    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: '£',
        code: 'Digit3',
        altKey: true,
        bubbles: true,
      }),
    )

    expect(activateTab).toHaveBeenCalledWith('tab-3')
  })

  it('supports Alt+Shift+P to create a permalink for the active tab', async () => {
    const permalinkTab = vi.fn()
    const { cmdInput } = await loadAppFns({
      permalinkTab,
      tabs: [{ id: 'tab-1', st: 'idle' }],
    })

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'P', altKey: true, shiftKey: true, bubbles: true }))

    expect(permalinkTab).toHaveBeenCalledWith('tab-1')
  })

  it('supports macOS Option+Shift+P to create a permalink via physical key code', async () => {
    const permalinkTab = vi.fn()
    const { cmdInput } = await loadAppFns({
      permalinkTab,
      tabs: [{ id: 'tab-1', st: 'idle' }],
    })

    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'π',
        code: 'KeyP',
        altKey: true,
        shiftKey: true,
        bubbles: true,
        cancelable: true,
      }),
    )

    expect(permalinkTab).toHaveBeenCalledWith('tab-1')
  })

  it('supports Alt+P to toggle the projects modal from the terminal prompt', async () => {
    const openProjectWorkspace = vi.fn(() => Promise.resolve(true))
    const closeProjectWorkspace = vi.fn()
    let projectWorkspaceOpen = false
    const { cmdInput } = await loadAppFns({
      openProjectWorkspace,
      closeProjectWorkspace,
      isProjectWorkspaceOpen: () => projectWorkspaceOpen,
      tabs: [{ id: 'tab-1', st: 'idle' }],
    })

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'p', altKey: true, bubbles: true }))
    projectWorkspaceOpen = true
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'p', altKey: true, bubbles: true }))

    expect(openProjectWorkspace).toHaveBeenCalledTimes(1)
    expect(closeProjectWorkspace).toHaveBeenCalledTimes(1)
  })

  it('supports Alt+C to toggle the command registry from the terminal prompt', async () => {
    const { cmdInput } = await loadAppFns({
      tabs: [{ id: 'tab-1', st: 'idle' }],
    })
    const overlay = document.getElementById('command-registry-overlay')

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'c', altKey: true, bubbles: true }))
    expect(overlay.classList.contains('open')).toBe(true)
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'c', altKey: true, bubbles: true }))
    expect(overlay.classList.contains('open')).toBe(false)
  })

  it('supports Alt+Shift+C to copy output for the active tab', async () => {
    const copyTab = vi.fn()
    const { cmdInput } = await loadAppFns({
      copyTab,
      tabs: [{ id: 'tab-1', st: 'idle' }],
    })

    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'C',
        altKey: true,
        shiftKey: true,
        bubbles: true,
        cancelable: true,
      }),
    )

    expect(copyTab).toHaveBeenCalledWith('tab-1')
  })

  it('supports macOS Option+Shift+C to copy output via physical key code', async () => {
    const copyTab = vi.fn()
    const { cmdInput } = await loadAppFns({
      copyTab,
      tabs: [{ id: 'tab-1', st: 'idle' }],
    })

    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'Ç',
        code: 'KeyC',
        altKey: true,
        shiftKey: true,
        bubbles: true,
      }),
    )

    expect(copyTab).toHaveBeenCalledWith('tab-1')
  })

  it('supports Alt+M to toggle the status monitor from the terminal prompt', async () => {
    const openStatusMonitor = vi.fn(() => Promise.resolve(true))
    const closeStatusMonitor = vi.fn()
    let statusMonitorOpen = false
    const { cmdInput } = await loadAppFns({
      openStatusMonitor,
      closeStatusMonitor,
      isStatusMonitorOpen: () => statusMonitorOpen,
      tabs: [{ id: 'tab-1', st: 'idle' }],
    })

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'm', altKey: true, bubbles: true }))
    statusMonitorOpen = true
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'm', altKey: true, bubbles: true }))

    expect(openStatusMonitor).toHaveBeenCalledWith({ source: 'shortcut' })
    expect(openStatusMonitor).toHaveBeenCalledTimes(1)
    expect(closeStatusMonitor).toHaveBeenCalledTimes(1)
  })

  it('supports Alt+Shift+F to toggle the Files modal from the terminal prompt', async () => {
    const openWorkspace = vi.fn()
    const closeWorkspace = vi.fn()
    let workspaceOpen = false
    const { cmdInput } = await loadAppFns({
      openWorkspace,
      closeWorkspace,
      isWorkspaceOverlayOpen: vi.fn(() => workspaceOpen),
      tabs: [{ id: 'tab-1', st: 'idle' }],
    })

    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'ƒ',
        altKey: true,
        shiftKey: true,
        bubbles: true,
      }),
    )

    expect(openWorkspace).toHaveBeenCalled()

    workspaceOpen = true
    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'F',
        code: 'KeyF',
        altKey: true,
        shiftKey: true,
        bubbles: true,
      }),
    )

    expect(closeWorkspace).toHaveBeenCalled()
  })

  it('supports Alt+Shift+S and Alt+Shift+W to toggle Schedules and Watchers from the terminal prompt', async () => {
    const openSchedulesModal = vi.fn()
    const closeSchedulesModal = vi.fn()
    const openWatchersModal = vi.fn()
    const closeWatchersModal = vi.fn()
    let schedulesOpen = false
    let watchersOpen = false
    const { cmdInput } = await loadAppFns({
      openSchedulesModal,
      closeSchedulesModal,
      isSchedulesOverlayOpen: vi.fn(() => schedulesOpen),
      openWatchersModal,
      closeWatchersModal,
      isWatchersOverlayOpen: vi.fn(() => watchersOpen),
      tabs: [{ id: 'tab-1', st: 'idle' }],
    })

    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'S',
        code: 'KeyS',
        altKey: true,
        shiftKey: true,
        bubbles: true,
      }),
    )
    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'W',
        code: 'KeyW',
        altKey: true,
        shiftKey: true,
        bubbles: true,
      }),
    )

    expect(openSchedulesModal).toHaveBeenCalledTimes(1)
    expect(openWatchersModal).toHaveBeenCalledTimes(1)

    schedulesOpen = true
    watchersOpen = true
    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'ß',
        code: 'KeyS',
        altKey: true,
        shiftKey: true,
        bubbles: true,
      }),
    )
    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: '„',
        code: 'KeyW',
        altKey: true,
        shiftKey: true,
        bubbles: true,
      }),
    )

    expect(closeSchedulesModal).toHaveBeenCalledTimes(1)
    expect(closeWatchersModal).toHaveBeenCalledTimes(1)
  })

  it('supports Ctrl+L to clear the active tab without dropping a running command', async () => {
    const clearTab = vi.fn()
    const cancelWelcome = vi.fn()
    const { cmdInput } = await loadAppFns({
      clearTab,
      cancelWelcome,
      tabs: [{ id: 'tab-1', st: 'running' }],
      activeTabId: 'tab-1',
    })

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'l', ctrlKey: true, bubbles: true }))

    expect(cancelWelcome).toHaveBeenCalledWith('tab-1')
    expect(clearTab).toHaveBeenCalledWith('tab-1', { preserveRunState: true })
  })

  it('does not apply Alt-based tab shortcuts while typing in non-terminal inputs', async () => {
    const createTab = vi.fn(() => 'tab-2')
    const activateTab = vi.fn()
    await loadAppFns({
      createTab,
      activateTab,
      tabs: [
        { id: 'tab-1', st: 'idle' },
        { id: 'tab-2', st: 'idle' },
      ],
    })
    createTab.mockClear()
    activateTab.mockClear()
    const searchInput = document.getElementById('search-input')

    searchInput.dispatchEvent(
      new KeyboardEvent('keydown', { key: 't', altKey: true, bubbles: true }),
    )
    searchInput.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'ArrowRight', altKey: true, bubbles: true }),
    )

    expect(createTab).not.toHaveBeenCalled()
    expect(activateTab).not.toHaveBeenCalled()
  })

  it('does not apply action shortcuts while typing in non-terminal inputs', async () => {
    const permalinkTab = vi.fn()
    const copyTab = vi.fn()
    const clearTab = vi.fn()
    await loadAppFns({
      permalinkTab,
      copyTab,
      clearTab,
      tabs: [
        { id: 'tab-1', st: 'idle' },
        { id: 'tab-2', st: 'idle' },
      ],
    })
    const searchInput = document.getElementById('search-input')

    searchInput.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'P', altKey: true, shiftKey: true, bubbles: true }),
    )
    searchInput.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'C',
        altKey: true,
        shiftKey: true,
        bubbles: true,
      }),
    )
    searchInput.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'l', ctrlKey: true, bubbles: true }),
    )

    expect(permalinkTab).not.toHaveBeenCalled()
    expect(copyTab).not.toHaveBeenCalled()
    expect(clearTab).not.toHaveBeenCalled()
  })

  it('ArrowDown/Up wrap around and navigate the same direction regardless of whether the list is above or below the prompt', async () => {
    const acFiltered = ['alpha', 'bravo', 'charlie']
    const { cmdInput, _getAcIndex, acDropdown } = await loadAppFns({
      acFiltered,
      acIndex: -1,
    })

    acDropdown.style.display = 'block'
    acDropdown.classList.add('ac-up')

    // ArrowUp from no selection (-1) wraps to the last item
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true }))
    expect(_getAcIndex()).toBe(2)

    // ArrowUp from last wraps to first... actually moves up
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true }))
    expect(_getAcIndex()).toBe(1)

    // ArrowDown always moves toward higher index (toward 'charlie'), regardless of ac-up
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }))
    expect(_getAcIndex()).toBe(2)

    // ArrowDown at the last item wraps to the first
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }))
    expect(_getAcIndex()).toBe(0)

    // ArrowUp at the first item wraps to the last
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true }))
    expect(_getAcIndex()).toBe(2)
  })

  it('Tab expands the typed value to the longest shared autocomplete prefix before cycling', async () => {
    const { cmdInput, _getAcIndex } = await loadAppFns({
      acSuggestions: ['ping', 'ping -c 4', 'ping google.com'],
      acFiltered: ['ping', 'ping -c 4', 'ping google.com'],
      acIndex: -1,
      acExpandSharedPrefix: (items) => {
        if (items.join('|') !== 'ping|ping -c 4|ping google.com') return false
        document.getElementById('cmd').value = 'ping'
        return true
      },
    })

    cmdInput.value = 'pi'
    cmdInput.setSelectionRange(2, 2)
    cmdInput.dispatchEvent(new Event('input'))
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }))

    expect(cmdInput.value).toBe('ping')
    expect(_getAcIndex()).toBe(-1)
  })

  it('Tab cycles autocomplete suggestions once the shared prefix is exhausted', async () => {
    const { cmdInput, _getAcIndex, acDropdown } = await loadAppFns({
      acSuggestions: ['ping -c 4', 'ping google.com', 'ping localhost'],
      acFiltered: ['ping -c 4', 'ping google.com', 'ping localhost'],
      acIndex: -1,
      acShow: () => {
        acDropdown.style.display = 'block'
      },
    })

    cmdInput.value = 'ping '
    cmdInput.setSelectionRange(5, 5)
    cmdInput.dispatchEvent(new Event('input'))

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }))
    expect(_getAcIndex()).toBe(0)
    expect(acDropdown.style.display).toBe('block')

    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }))
    expect(_getAcIndex()).toBe(1)

    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true }),
    )
    expect(_getAcIndex()).toBe(0)
  })

  it('Tab accepts a single concrete autocomplete item while leaving hint-only guidance visible', async () => {
    const realItem = { value: 'targets.txt', replaceStart: 4, replaceEnd: 6 }
    const hintItem = { value: '<file>', hintOnly: true, description: 'Session file path' }
    const acAccept = vi.fn()
    const { cmdInput, acDropdown } = await loadAppFns({
      acFiltered: [realItem, hintItem],
      acIndex: -1,
      acAccept,
    })

    acDropdown.style.display = 'block'
    cmdInput.value = 'cat ta'
    cmdInput.setSelectionRange(6, 6)
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }))

    expect(acAccept).toHaveBeenCalledWith(realItem)
  })

  it('ArrowDown skips hint-only autocomplete guidance while cycling menu items', async () => {
    const realA = { value: 'alpha.txt' }
    const hintItem = { value: '<file>', hintOnly: true, description: 'Session file path' }
    const realB = { value: 'bravo.txt' }
    const acShow = vi.fn()
    const { cmdInput, _getAcIndex, acDropdown } = await loadAppFns({
      acFiltered: [realA, hintItem, realB],
      acIndex: 0,
      acShow,
    })

    acDropdown.style.display = 'block'
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }))

    expect(_getAcIndex()).toBe(2)
    expect(acShow).toHaveBeenCalledWith([realA, hintItem, realB])
  })

  it('Tab key with a modifier does not trigger autocomplete accept or selection', async () => {
    const { cmdInput, _getAcIndex } = await loadAppFns({
      acFiltered: ['alpha', 'bravo'],
      acIndex: -1,
    })

    // Alt+Tab (the app tab-cycle shortcut) must not trigger autocomplete
    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Tab', altKey: true, bubbles: true }),
    )
    expect(_getAcIndex()).toBe(-1)

    // Ctrl+Tab must not trigger autocomplete
    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Tab', ctrlKey: true, bubbles: true }),
    )
    expect(_getAcIndex()).toBe(-1)

    // Meta+Tab must not trigger autocomplete
    cmdInput.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Tab', metaKey: true, bubbles: true }),
    )
    expect(_getAcIndex()).toBe(-1)

    // Plain Tab (no modifier) still triggers autocomplete selection
    cmdInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }))
    expect(_getAcIndex()).toBe(0)
  })

  it('routes hist-clear-all through confirmHistAction', async () => {
    // Modal wiring itself is covered by ui_confirm.test.js (the primitive)
    // and history.test.js (confirmHistAction's call to showConfirm). Here
    // we just verify the app bootstrap still connects the clear-all button.
    const { confirmHistAction } = await loadAppFns()
    confirmHistAction.mockClear()
    document.getElementById('hist-clear-all-btn').click()
    expect(confirmHistAction).toHaveBeenCalledWith(
      'clear',
      null,
      null,
      'run',
      {
        deleteUrl: '/history',
        previewUrl: '/history/delete-preview',
        filtered: false,
      },
    )
  })

  it('uses the persistent share redaction default before showing the modal prompt', async () => {
    const {
      confirmPermalinkRedactionChoice,
      getShareRedactionDefaultPreference,
    } = await loadAppFns({
      cookies: { pref_share_redaction_default: 'raw' },
    })

    // showConfirm is stubbed to resolve null (cancel) by loadAppFns; if the
    // preference short-circuit failed, this would resolve null instead of
    // 'raw'. The assertion implicitly verifies the modal was skipped.
    await expect(confirmPermalinkRedactionChoice()).resolves.toBe('raw')
    expect(getShareRedactionDefaultPreference()).toBe('raw')
  })

  it('wires search controls and Escape dismissal correctly', async () => {
    const { runSearch, clearSearch, navigateSearch, cmdInput } = await loadAppFns()
    const searchBar = document.getElementById('search-bar')
    const searchInput = document.getElementById('search-input')

    cmdInput.focus.mockClear()
    searchBar.style.display = 'none'
    document.getElementById('search-toggle-btn').click()
    expect(searchBar.style.display).toBe('flex')
    expect(runSearch).toHaveBeenCalledTimes(1)

    document.getElementById('search-prev').click()
    document.getElementById('search-next').click()
    expect(navigateSearch).toHaveBeenCalledWith(-1)
    expect(navigateSearch).toHaveBeenCalledWith(1)

    searchBar.style.display = 'flex'
    searchInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await new Promise((resolve) => setTimeout(resolve, 10))
    expect(searchBar.style.display).toBe('none')
    expect(clearSearch).toHaveBeenCalled()

    searchBar.style.display = 'none'
    cmdInput.focus.mockClear()
    document.getElementById('search-toggle-btn').click()
    document.getElementById('search-toggle-btn').click()
    expect(clearSearch).toHaveBeenCalledTimes(3)
    expect(searchBar.style.display).toBe('none')
  })

  it('refocuses the visible mobile composer after closing search with Escape', async () => {
    const { getVisibleComposerInput, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    const searchBar = document.getElementById('search-bar')
    const searchInput = document.getElementById('search-input')
    const visibleInput = getVisibleComposerInput()

    document.getElementById('search-toggle-btn').click()
    expect(searchBar.style.display).toBe('flex')

    searchInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))

    expect(searchBar.style.display).toBe('none')
    expect(visibleInput.focus).not.toHaveBeenCalled()

    restoreViewport()
  })

  it('opens and closes the FAQ overlay through the wired controls', async () => {
    const { openFaq } = await loadAppFns()
    const faqOverlay = document.getElementById('faq-overlay')

    openFaq()
    expect(faqOverlay.classList.contains('open')).toBe(true)

    faqOverlay.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(faqOverlay.classList.contains('open')).toBe(false)

    openFaq()
    document.querySelector('.faq-close').click()
    expect(faqOverlay.classList.contains('open')).toBe(false)
  })

  it('closes the theme overlay and refocuses the terminal on Escape', async () => {
    const { openThemeSelector } = await loadAppFns({
      mobileTouch: false,
      themeRegistry: {
        current: {
          name: 'theme_light_blue',
          label: 'Apricot Sand',
          source: 'variant',
          vars: { '--bg': '#9ab7d0' },
        },
        themes: [
          {
            name: 'theme_light_blue',
            label: 'Apricot Sand',
            source: 'variant',
            vars: { '--bg': '#9ab7d0' },
          },
        ],
      },
    })
    const themeOverlay = document.getElementById('theme-overlay')

    openThemeSelector()
    expect(themeOverlay.classList.contains('open')).toBe(true)

    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(themeOverlay.classList.contains('open')).toBe(false)
  })

  it('does not refocus the mobile composer when closing options', async () => {
    const { getVisibleComposerInput, openOptions } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    const overlay = document.getElementById('options-overlay')
    const visibleInput = getVisibleComposerInput()
    visibleInput.focus.mockClear()

    openOptions()
    expect(overlay.classList.contains('open')).toBe(true)

    document.querySelector('.options-close').click()
    expect(overlay.classList.contains('open')).toBe(false)
    expect(visibleInput.focus).not.toHaveBeenCalled()

    document.querySelector('#mobile-menu-sheet [data-menu-action="options"]').click()
    expect(overlay.classList.contains('open')).toBe(true)

    overlay.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(overlay.classList.contains('open')).toBe(false)
  })

  it('blurs the visible mobile composer when opening options', async () => {
    const { getVisibleComposerInput, openOptions, restoreViewport } = await loadAppFns({
      mobileViewport: { height: 500, offsetTop: 0 },
    })
    const overlay = document.getElementById('options-overlay')
    const visibleInput = getVisibleComposerInput()
    document.body.classList.add('mobile-terminal-mode')

    openOptions()

    expect(overlay.classList.contains('open')).toBe(true)
    expect(visibleInput.blur).toHaveBeenCalled()

    restoreViewport()
  })

  it('hides rotate/clear/copy session token buttons when no token is set — desktop open', async () => {
    const { openOptions } = await loadAppFns()  // no session_token in localStorage

    openOptions()

    expect(document.getElementById('options-session-token-rotate-btn').style.display).toBe('none')
    expect(document.getElementById('options-session-token-clear-btn').style.display).toBe('none')
    expect(document.getElementById('options-session-token-copy-btn').style.display).toBe('none')
  })

  it('hides rotate/clear/copy session token buttons when no token is set — mobile menu open', async () => {
    await loadAppFns()  // no session_token in localStorage

    document.querySelector('#mobile-menu-sheet [data-menu-action="options"]').click()

    expect(document.getElementById('options-session-token-rotate-btn').style.display).toBe('none')
    expect(document.getElementById('options-session-token-clear-btn').style.display).toBe('none')
    expect(document.getElementById('options-session-token-copy-btn').style.display).toBe('none')
  })

  it('shows rotate/clear/copy session token buttons when a token is active — mobile menu open', async () => {
    const { storage } = await loadAppFns()
    storage.setItem('session_token', 'tok_abcd1234efgh5678ijkl9012mnop3456')

    document.querySelector('#mobile-menu-sheet [data-menu-action="options"]').click()

    expect(document.getElementById('options-session-token-rotate-btn').style.display).toBe('')
    expect(document.getElementById('options-session-token-clear-btn').style.display).toBe('')
    expect(document.getElementById('options-session-token-copy-btn').style.display).toBe('')
  })

  it('aborts session-token set when the migration prompt is dismissed instead of applying the token', async () => {
    const updateSessionId = vi.fn()
    const showToast = vi.fn()
    const apiFetch = vi.fn((url, opts = {}) => {
      if (url === '/session/token/verify') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ exists: true }),
        })
      }
      if (url === '/session/run-count') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ count: 3 }),
        })
      }
      if (url === '/config') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              app_name: 'darklab_shell',
              prompt_username: 'anon',
              prompt_domain: 'darklab.sh',
              version: '9.9',
              project_source: 'https://gitlab.com/darklab.sh/darklab_shell',
              default_theme: 'darklab_obsidian.yaml',
              share_redaction_enabled: true,
              share_redaction_rules: [],
              motd: '',
              command_timeout_seconds: 0,
              max_output_lines: 0,
              permalink_retention_days: 0,
            }),
        })
      }
      if (url === '/allowed-commands') {
        return Promise.resolve({
          json: () => Promise.resolve({ restricted: false, commands: [], groups: [] }),
        })
      }
      if (url === '/faq') {
        return Promise.resolve({ json: () => Promise.resolve({ items: [] }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const showConfirm = vi
      .fn()
      .mockImplementationOnce(async (opts) => {
        const input = opts.content.find((node) => node?.id === 'session-token-set-input')
        input.value = 'tok_existing1234567890abcdef1234567890'
        const apply = opts.actions.find((action) => action.id === 'apply')
        const ok = await apply.onActivate()
        return ok ? 'apply' : null
      })
      .mockResolvedValueOnce(null)

    const { storage } = await loadAppFns({
      apiFetch,
      showConfirm,
      showToast,
      updateSessionId,
      sessionId: 'session-old',
    })

    document.getElementById('options-session-token-set-btn').click()
    await vi.waitFor(() => expect(showConfirm).toHaveBeenCalledTimes(2))
    expect(showConfirm.mock.calls[1][0].actions.map((action) => action.id)).toEqual([
      'cancel',
      'skip',
      'yes',
    ])
    expect(storage.getItem('session_token')).toBeNull()
    expect(updateSessionId).not.toHaveBeenCalled()
    expect(showToast).not.toHaveBeenCalledWith('Session token applied')
  })

  it('applies session-token set on explicit skip without running migration', async () => {
    const updateSessionId = vi.fn()
    const showToast = vi.fn()
    const fetchSpy = vi.fn()
    const apiFetch = vi.fn((url, opts = {}) => {
      if (url === '/session/token/verify') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ exists: true }),
        })
      }
      if (url === '/session/run-count') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ count: 2 }),
        })
      }
      if (url === '/config') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              app_name: 'darklab_shell',
              prompt_username: 'anon',
              prompt_domain: 'darklab.sh',
              version: '9.9',
              project_source: 'https://gitlab.com/darklab.sh/darklab_shell',
              default_theme: 'darklab_obsidian.yaml',
              share_redaction_enabled: true,
              share_redaction_rules: [],
              motd: '',
              command_timeout_seconds: 0,
              max_output_lines: 0,
              permalink_retention_days: 0,
            }),
        })
      }
      if (url === '/allowed-commands') {
        return Promise.resolve({
          json: () => Promise.resolve({ restricted: false, commands: [], groups: [] }),
        })
      }
      if (url === '/faq') {
        return Promise.resolve({ json: () => Promise.resolve({ items: [] }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const showConfirm = vi
      .fn()
      .mockImplementationOnce(async (opts) => {
        const input = opts.content.find((node) => node?.id === 'session-token-set-input')
        input.value = 'tok_existing1234567890abcdef1234567890'
        const apply = opts.actions.find((action) => action.id === 'apply')
        const ok = await apply.onActivate()
        return ok ? 'apply' : null
      })
      .mockResolvedValueOnce('skip')
    const originalFetch = global.fetch
    global.fetch = fetchSpy

    try {
      const { storage } = await loadAppFns({
        apiFetch,
        showConfirm,
        showToast,
        updateSessionId,
        sessionId: 'session-old',
      })

      document.getElementById('options-session-token-set-btn').click()
      await vi.waitFor(() =>
        expect(storage.getItem('session_token')).toBe('tok_existing1234567890abcdef1234567890'),
      )
      expect(updateSessionId).toHaveBeenCalledWith('tok_existing1234567890abcdef1234567890')
      expect(fetchSpy).not.toHaveBeenCalled()
      expect(showToast).toHaveBeenCalledWith('Session token applied')
    } finally {
      global.fetch = originalFetch
    }
  })

  it('opens the session-token set confirm without relying on a Node global binding', async () => {
    const showConfirm = vi.fn().mockResolvedValue(null)
    const originalGlobal = globalThis.global

    try {
      globalThis.global = undefined
      await loadAppFns({ showConfirm })
      document.getElementById('options-session-token-set-btn').click()
      await vi.waitFor(() => expect(showConfirm).toHaveBeenCalledTimes(1))
    } finally {
      globalThis.global = originalGlobal
    }
  })

  it('aborts generated-token activation when the migration prompt is dismissed', async () => {
    const updateSessionId = vi.fn()
    const showToast = vi.fn()
    const copyTextToClipboard = vi.fn(() => Promise.resolve())
    const apiFetch = vi.fn((url) => {
      if (url === '/session/token/generate') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ session_token: 'tok_generated1234567890abcdef1234567' }),
        })
      }
      if (url === '/session/run-count') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ count: 4 }),
        })
      }
      if (url === '/config') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              app_name: 'darklab_shell',
              prompt_username: 'anon',
              prompt_domain: 'darklab.sh',
              version: '9.9',
              project_source: 'https://gitlab.com/darklab.sh/darklab_shell',
              default_theme: 'darklab_obsidian.yaml',
              share_redaction_enabled: true,
              share_redaction_rules: [],
              motd: '',
              command_timeout_seconds: 0,
              max_output_lines: 0,
              permalink_retention_days: 0,
            }),
        })
      }
      if (url === '/allowed-commands') {
        return Promise.resolve({
          json: () => Promise.resolve({ restricted: false, commands: [], groups: [] }),
        })
      }
      if (url === '/faq') {
        return Promise.resolve({ json: () => Promise.resolve({ items: [] }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const showConfirm = vi.fn().mockResolvedValue(null)

    const { storage } = await loadAppFns({
      apiFetch,
      showConfirm,
      showToast,
      updateSessionId,
      copyTextToClipboard,
      sessionId: 'session-old',
    })

    document.getElementById('options-session-token-generate-btn').click()
    await vi.waitFor(() => expect(showConfirm).toHaveBeenCalledTimes(1))
    expect(showConfirm.mock.calls[0][0].actions.map((action) => action.id)).toEqual([
      'cancel',
      'skip',
      'yes',
    ])
    expect(storage.getItem('session_token')).toBeNull()
    expect(updateSessionId).not.toHaveBeenCalled()
    expect(copyTextToClipboard).not.toHaveBeenCalled()
    expect(showToast).not.toHaveBeenCalledWith('Session token applied')
  })

  it('opens a destructive confirm before clearing the active session token', async () => {
    const showConfirm = vi.fn().mockResolvedValue(null)
    const { storage } = await loadAppFns({ showConfirm })
    storage.setItem('session_token', 'tok_abcd1234efgh5678ijkl9012mnop3456')

    document.getElementById('options-session-token-clear-btn').click()
    await vi.waitFor(() => expect(showConfirm).toHaveBeenCalledTimes(1))

    const confirmOpts = showConfirm.mock.calls[0][0]
    expect(confirmOpts.tone).toBe('danger')
    expect(confirmOpts.body.text).toBe('Clear the current session token from this browser?')
    expect(confirmOpts.body.note).toContain('will not be able to recover it from the app')
    expect(confirmOpts.actions.map((action) => action.id)).toEqual(['copy', 'cancel', 'clear'])
    expect(confirmOpts.actions.find((action) => action.id === 'cancel')).toMatchObject({ role: 'cancel' })
    expect(confirmOpts.actions.find((action) => action.id === 'clear')).toMatchObject({
      role: 'destructive',
      label: 'Clear token',
    })
  })

  it('lets the user copy the session token from the clear confirm without clearing it', async () => {
    const copyTextToClipboard = vi.fn(() => Promise.resolve())
    const showToast = vi.fn()
    const updateSessionId = vi.fn()
    const showConfirm = vi.fn().mockImplementation(async (opts) => {
      const copy = opts.actions.find((action) => action.id === 'copy')
      const keepOpen = await copy.onActivate()
      expect(keepOpen).toBe(false)
      return 'cancel'
    })
    const { storage } = await loadAppFns({
      showConfirm,
      copyTextToClipboard,
      showToast,
      updateSessionId,
    })
    storage.setItem('session_token', 'tok_abcd1234efgh5678ijkl9012mnop3456')

    document.getElementById('options-session-token-clear-btn').click()
    await vi.waitFor(() => expect(showConfirm).toHaveBeenCalledTimes(1))

    expect(copyTextToClipboard).toHaveBeenCalledWith('tok_abcd1234efgh5678ijkl9012mnop3456')
    expect(showToast).toHaveBeenCalledWith('Token copied to clipboard')
    expect(storage.getItem('session_token')).toBe('tok_abcd1234efgh5678ijkl9012mnop3456')
    expect(updateSessionId).not.toHaveBeenCalled()
  })

  it('clears the session token only after confirming the destructive action', async () => {
    const showConfirm = vi.fn().mockResolvedValue('clear')
    const showToast = vi.fn()
    const updateSessionId = vi.fn()
    const reloadSessionHistory = vi.fn(() => Promise.resolve())
    const hydrateCmdHistory = vi.fn()
    const { storage } = await loadAppFns({
      showConfirm,
      showToast,
      updateSessionId,
      reloadSessionHistory,
      hydrateCmdHistory,
      sessionId: 'session-old',
    })
    storage.setItem('session_token', 'tok_abcd1234efgh5678ijkl9012mnop3456')

    document.getElementById('options-session-token-clear-btn').click()
    await vi.waitFor(() => expect(storage.getItem('session_token')).toBeNull())

    expect(updateSessionId).toHaveBeenCalledWith('session-old')
    expect(hydrateCmdHistory).toHaveBeenCalledWith([])
    expect(reloadSessionHistory).toHaveBeenCalled()
    expect(document.getElementById('options-session-token-status').textContent).toBe(
      'No session token — anonymous session',
    )
    expect(showToast).toHaveBeenCalledWith('Session token cleared')
  })

  it('loads encrypted secrets metadata in options without revealing values', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/session/secrets') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            secrets: [{
              name: 'SHODAN_API_KEY',
              consumer_envs: ['SHODAN_API_KEY'],
              updated_at: '2026-05-14T10:00:00+00:00',
            }],
          }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const { openOptions } = await loadAppFns({ apiFetch })

    openOptions()
    await vi.waitFor(() => expect(document.getElementById('options-secrets-list').textContent).toContain('SHODAN_API_KEY'))

    expect(document.getElementById('options-secrets-list').textContent).not.toContain('super-secret-value')
    expect(apiFetch).toHaveBeenCalledWith('/session/secrets', { cache: 'no-store' })
  })

  it('adds encrypted secrets through the replace-only options prompt', async () => {
    let secrets = []
    const apiFetch = vi.fn((url, opts = {}) => {
      if (url === '/commands/catalog') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            restricted: true,
            commands: [{
              root: 'vt',
              category: 'External Intelligence',
              description: 'VirusTotal lookups',
              requires_secrets: [{
                env: 'VT_API_KEY',
                inject_env: 'VTCLI_APIKEY',
                fallback_envs: ['VTCLI_APIKEY'],
                optional: false,
              }],
            }],
            groups: [],
          }),
        })
      }
      if (url === '/session/secrets' && opts.method === 'POST') {
        const body = JSON.parse(opts.body)
        secrets = [{
          name: body.name,
          consumer_envs: body.consumer_envs,
          updated_at: '2026-05-14T10:00:00+00:00',
        }]
        return Promise.resolve({ ok: true, json: () => Promise.resolve(secrets[0]) })
      }
      if (url === '/session/secrets') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ secrets }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const showConfirm = vi.fn().mockImplementation(async (opts) => {
      const select = opts.content[0].querySelector('select')
      const inputs = opts.content.flatMap(node => Array.from(node.querySelectorAll('input')))
      expect(opts.content.map(node => node.querySelector('.options-secret-field-label')?.textContent).filter(Boolean)).toEqual([
        'Secret',
        'Custom secret name',
        'API key or token',
        'Consumer envs',
      ])
      expect([...select.options].map(option => option.value)).toContain('VT_API_KEY')
      expect([...select.options].map(option => option.value)).not.toContain('VTCLI_APIKEY')
      select.value = 'VT_API_KEY'
      select.dispatchEvent(new Event('change'))
      expect(inputs[0].getAttribute('data-bwignore')).toBe('true')
      expect(inputs[1].autocomplete).toBe('off')
      expect(inputs[1].placeholder).toBe('Paste API key or token')
      expect(inputs[1].getAttribute('data-bwignore')).toBe('true')
      expect(inputs[2].getAttribute('data-bwignore')).toBe('true')
      inputs[1].value = 'value-that-must-not-render'
      const ok = await opts.actions.find(action => action.id === 'save').onActivate()
      return ok ? 'save' : null
    })
    const showToast = vi.fn()
    await loadAppFns({ apiFetch, showConfirm, showToast })

    document.getElementById('options-secret-new-btn').click()
    await vi.waitFor(() => expect(apiFetch).toHaveBeenCalledWith('/session/secrets', expect.objectContaining({
      method: 'POST',
    })))

    const postBody = JSON.parse(apiFetch.mock.calls.find(([url, opts]) => url === '/session/secrets' && opts?.method === 'POST')[1].body)
    expect(postBody).toEqual({
      name: 'VT_API_KEY',
      value: 'value-that-must-not-render',
      consumer_envs: undefined,
    })
    await vi.waitFor(() => expect(document.getElementById('options-secrets-list').textContent).toContain('VT_API_KEY'))
    expect(document.getElementById('options-secrets-list').textContent).not.toContain('value-that-must-not-render')
  })

  it('keeps a custom secret escape hatch with an unused-secret warning', async () => {
    let secrets = []
    const apiFetch = vi.fn((url, opts = {}) => {
      if (url === '/commands/catalog') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ restricted: true, commands: [], groups: [] }),
        })
      }
      if (url === '/session/secrets' && opts.method === 'POST') {
        const body = JSON.parse(opts.body)
        secrets = [{ name: body.name, consumer_envs: body.consumer_envs, updated_at: '2026-05-14T10:00:00+00:00' }]
        return Promise.resolve({ ok: true, json: () => Promise.resolve(secrets[0]) })
      }
      if (url === '/session/secrets') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ secrets }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const showConfirm = vi.fn().mockImplementation(async (opts) => {
      const select = opts.content[0].querySelector('select')
      const inputs = opts.content.flatMap(node => Array.from(node.querySelectorAll('input')))
      expect(opts.content.map(node => node.textContent).join(' ')).toContain('Custom secrets are stored')
      select.value = '__custom__'
      select.dispatchEvent(new Event('change'))
      inputs[0].value = 'future_api_key'
      inputs[1].value = 'custom-secret-value'
      inputs[2].value = 'FUTURE_API_KEY'
      const ok = await opts.actions.find(action => action.id === 'save').onActivate()
      return ok ? 'save' : null
    })
    const showToast = vi.fn()
    await loadAppFns({ apiFetch, showConfirm, showToast })

    document.getElementById('options-secret-new-btn').click()
    await vi.waitFor(() => expect(apiFetch).toHaveBeenCalledWith('/session/secrets', expect.objectContaining({
      method: 'POST',
    })))

    const postBody = JSON.parse(apiFetch.mock.calls.find(([url, opts]) => url === '/session/secrets' && opts?.method === 'POST')[1].body)
    expect(postBody).toEqual({
      name: 'FUTURE_API_KEY',
      value: 'custom-secret-value',
      consumer_envs: ['FUTURE_API_KEY'],
    })
    expect(showToast).toHaveBeenCalledWith(expect.stringContaining('not currently used'), 'success')
  })

  it('suggests app-native intel secret consumers in the options prompt', async () => {
    let secrets = []
    const apiFetch = vi.fn((url, opts = {}) => {
      if (url === '/commands/catalog') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            restricted: true,
            commands: [],
            groups: [],
            secret_consumers: [
              {
                source: 'app_native_intel',
                consumer: 'intel Shodan',
                provider: 'shodan',
                env: 'SHODAN_API_KEY',
                fallback_envs: [],
                optional: false,
              },
            ],
            intel_providers: [
              {
                id: 'shodan',
                label: 'Shodan',
                entity_types: ['ip'],
                secret_env: 'SHODAN_API_KEY',
                secret_env_aliases: [],
                secret_env_names: ['SHODAN_API_KEY'],
                requires_secret: true,
                access_note: 'Free signup; paid tiers',
                app_native: true,
              },
              {
                id: 'teamcymru',
                label: 'Team Cymru',
                entity_types: ['ip'],
                uses: ['intel ip'],
                secret_env: '',
                secret_env_aliases: [],
                secret_env_names: [],
                requires_secret: false,
                access_note: 'Free public lookup',
                app_native: true,
              },
              {
                id: 'ipinfo',
                label: 'IPinfo',
                entity_types: ['ip'],
                uses: ['intel ip', 'ipinfo CLI'],
                secret_env: 'IPINFO_TOKEN',
                secret_env_aliases: [],
                secret_env_names: ['IPINFO_TOKEN'],
                requires_secret: true,
                optional_secret: true,
                access_note: 'Free public basics; optional account token',
                app_native: true,
              },
              {
                id: 'virustotal',
                label: 'VirusTotal',
                entity_types: ['domain', 'hash'],
                secret_env: 'VT_API_KEY',
                secret_env_aliases: ['VTCLI_APIKEY'],
                secret_env_names: ['VT_API_KEY', 'VTCLI_APIKEY'],
                requires_secret: true,
                access_note: 'Free signup; paid tiers',
                app_native: true,
              },
              {
                id: 'chaos',
                label: 'ProjectDiscovery Chaos',
                entity_types: ['domain'],
                uses: ['chaos CLI'],
                secret_env: 'PDCP_API_KEY',
                secret_env_aliases: [],
                secret_env_names: ['PDCP_API_KEY'],
                requires_secret: true,
                access_note: 'ProjectDiscovery Cloud account key',
                app_native: false,
              },
            ],
          }),
        })
      }
      if (url === '/session/secrets' && opts.method === 'POST') {
        const body = JSON.parse(opts.body)
        secrets = [{ name: body.name, consumer_envs: body.consumer_envs, updated_at: '2026-05-14T10:00:00+00:00' }]
        return Promise.resolve({ ok: true, json: () => Promise.resolve(secrets[0]) })
      }
      if (url === '/session/secrets') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ secrets }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const showConfirm = vi.fn().mockImplementation(async (opts) => {
      const select = opts.content[0].querySelector('select')
      const valueInput = opts.content.flatMap(node => Array.from(node.querySelectorAll('input')))[1]
      const replacing = String(opts.body?.text || '').startsWith('Replace ')
      expect([...select.options].map(option => option.value)).toContain('SHODAN_API_KEY')
      expect(select.value).toBe('SHODAN_API_KEY')
      expect(select.disabled).toBe(replacing)
      select.value = 'SHODAN_API_KEY'
      select.dispatchEvent(new Event('change'))
      expect(opts.content.map(node => node.textContent).join(' ')).toContain('Used by intel Shodan')
      expect(valueInput.placeholder).toBe(replacing ? 'Paste replacement API key or token' : 'Paste API key or token')
      valueInput.value = replacing ? 'replacement-shodan-secret-value' : 'shodan-secret-value'
      const ok = await opts.actions.find(action => action.id === 'save').onActivate()
      return ok ? 'save' : null
    })
    await loadAppFns({ apiFetch, showConfirm })

    document.getElementById('options-provider-status-btn').click()
    const providerOverlay = document.getElementById('provider-status-overlay')
    await vi.waitFor(() => expect(providerOverlay.classList.contains('u-hidden')).toBe(false))
    const providerText = document.getElementById('provider-status-body').textContent
    expect(providerText).toContain('2 usable · 3 not configured')
    expect(providerText).toContain('Team Cymru')
    expect(providerText).toContain('No secret needed')
    expect(providerText).toContain('IPinfo')
    expect(providerText).toContain('ipinfo CLI')
    expect(providerText).toContain('Shodan')
    expect(providerText).toContain('Not configured')
    expect(providerText).toContain('SHODAN_API_KEY')
    expect(providerText).toContain('VirusTotal')
    expect(providerText).toContain('VT_API_KEY')
    expect(providerText).toContain('ProjectDiscovery Chaos')
    expect(providerText).toContain('PDCP_API_KEY')
    expect(providerText).not.toContain('VTCLI_APIKEY')

    document.querySelector('.provider-status-close').click()
    await vi.waitFor(() => expect(providerOverlay.classList.contains('u-hidden')).toBe(true))
    document.getElementById('options-provider-status-btn').click()
    await vi.waitFor(() => expect(providerOverlay.classList.contains('u-hidden')).toBe(false))

    const shodanLink = Array.from(document.querySelectorAll('.options-secret-link'))
      .find((button) => button.textContent === 'SHODAN_API_KEY')
    expect(shodanLink.classList.contains('chip')).toBe(true)
    shodanLink.click()
    await vi.waitFor(() => expect(providerOverlay.classList.contains('u-hidden')).toBe(true))
    await vi.waitFor(() => expect(apiFetch).toHaveBeenCalledWith('/session/secrets', expect.objectContaining({
      method: 'POST',
    })))

    const postBody = JSON.parse(apiFetch.mock.calls.find(([url, opts]) => url === '/session/secrets' && opts?.method === 'POST')[1].body)
    expect(postBody).toEqual({
      name: 'SHODAN_API_KEY',
      value: 'shodan-secret-value',
      consumer_envs: undefined,
    })

    document.getElementById('options-provider-status-btn').click()
    await vi.waitFor(() => expect(providerOverlay.classList.contains('u-hidden')).toBe(false))
    const configuredShodanLink = Array.from(document.querySelectorAll('.options-secret-link'))
      .find((button) => button.textContent === 'SHODAN_API_KEY')
    expect(configuredShodanLink.classList.contains('chip')).toBe(true)
    expect(configuredShodanLink.title).toBe('Replace SHODAN_API_KEY')
    configuredShodanLink.click()
    await vi.waitFor(() => expect(showConfirm).toHaveBeenCalledWith(expect.objectContaining({
      body: expect.objectContaining({ text: 'Replace SHODAN_API_KEY?' }),
    })))
    await vi.waitFor(() => expect(apiFetch.mock.calls.filter(([url, opts]) => (
      url === '/session/secrets' && opts?.method === 'POST'
    ))).toHaveLength(2))

    const replaceBody = JSON.parse(apiFetch.mock.calls.filter(([url, opts]) => (
      url === '/session/secrets' && opts?.method === 'POST'
    ))[1][1].body)
    expect(replaceBody).toEqual({
      name: 'SHODAN_API_KEY',
      value: 'replacement-shodan-secret-value',
      consumer_envs: undefined,
    })
  })

  it('opens the encrypted secret prompt for terminal secret set without echoing the value', async () => {
    const apiFetch = vi.fn((url, opts = {}) => {
      if (url === '/session/secrets' && opts.method === 'POST') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ name: 'SHODAN_API_KEY', consumer_envs: ['SHODAN_API_KEY'] }) })
      }
      if (url === '/session/secrets') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            secrets: [{ name: 'SHODAN_API_KEY', consumer_envs: ['SHODAN_API_KEY'], updated_at: '2026-05-14T10:00:00+00:00' }],
          }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const showConfirm = vi.fn().mockImplementation(async (opts) => {
      const inputs = opts.content.flatMap(node => Array.from(node.querySelectorAll('input')))
      expect(inputs[0].value).toBe('SHODAN_API_KEY')
      inputs[1].value = 'terminal-secret-value'
      const ok = await opts.actions.find(action => action.id === 'save').onActivate()
      return ok ? 'save' : null
    })
    const { handleSecretCommand } = await loadAppFns({ apiFetch, showConfirm })

    const execution = createBrowserCommandExecution('secret set shodan_api_key')
    await handleSecretCommand('secret set shodan_api_key', 'tab-1', execution)

    expect(showConfirm).toHaveBeenCalledWith(expect.objectContaining({
      body: expect.objectContaining({
        note: expect.stringContaining('never shown here again'),
      }),
    }))
    const postBody = JSON.parse(apiFetch.mock.calls.find(([url, opts]) => url === '/session/secrets' && opts?.method === 'POST')[1].body)
    expect(postBody).toEqual({
      name: 'SHODAN_API_KEY',
      value: 'terminal-secret-value',
      consumer_envs: undefined,
    })
    expect(JSON.stringify(apiFetch.mock.calls)).toContain('terminal-secret-value')
    expect(document.body.textContent).not.toContain('terminal-secret-value')
    expect(execution.state.status).toBe('ok')
    expect(execution.state.recordRecent).toBe(true)
  })

  it('deletes encrypted secrets from the options panel only after confirming', async () => {
    let secrets = [{ name: 'VT_API_KEY', consumer_envs: ['VT_API_KEY'], updated_at: '2026-05-14T10:00:00+00:00' }]
    const apiFetch = vi.fn((url, opts = {}) => {
      if (url === '/session/secrets/VT_API_KEY' && opts.method === 'DELETE') {
        secrets = []
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ removed: true }) })
      }
      if (url === '/session/secrets') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ secrets }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const showConfirm = vi.fn().mockResolvedValue('delete')
    const { openOptions } = await loadAppFns({ apiFetch, showConfirm })
    openOptions()
    await vi.waitFor(() => expect(document.getElementById('options-secrets-list').textContent).toContain('VT_API_KEY'))

    document.querySelector('#options-secrets-list .options-secret-actions button:last-child').click()
    await vi.waitFor(() => expect(apiFetch).toHaveBeenCalledWith('/session/secrets/VT_API_KEY', {
      method: 'DELETE',
    }))

    expect(showConfirm).toHaveBeenCalledWith(expect.objectContaining({
      tone: 'danger',
    }))
    await vi.waitFor(() => expect(document.getElementById('options-secrets-list').textContent).toContain('No secrets stored'))
  })

  it('persists options changes through cookies and syncs quick-toggle state', async () => {
    const apiFetch = vi.fn((url, opts = {}) => {
      if (url === '/config') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              app_name: 'darklab_shell',
              prompt_username: 'anon',
              prompt_domain: 'darklab.sh',
              version: '9.9',
              project_source: 'https://gitlab.com/darklab.sh/darklab_shell',
              default_theme: 'darklab_obsidian.yaml',
              share_redaction_enabled: true,
              share_redaction_rules: [],
              motd: '',
              command_timeout_seconds: 0,
              max_output_lines: 0,
              permalink_retention_days: 0,
            }),
        })
      }
      if (url === '/allowed-commands') {
        return Promise.resolve({ json: () => Promise.resolve({ restricted: false, commands: [], groups: [] }) })
      }
      if (url === '/faq') {
        return Promise.resolve({ json: () => Promise.resolve({ items: [] }) })
      }
      if (url === '/session/preferences' && (!opts.method || opts.method === 'GET')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ preferences: {} }) })
      }
      if (url === '/session/preferences' && opts.method === 'POST') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) })
      }
      if (url === '/session/tour-seen') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            ok: true,
            tour_version: 4,
            preferences: { pref_tour_seen_version: 4 },
          }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const {
      getWelcomeIntroPreference,
      getShareRedactionDefaultPreference,
      getProjectAutoLinkExternalRunsPreference,
      getProjectAutoLinkRunEntitiesPreference,
      getCommandOutcomeSummariesPreference,
      getHudClockPreference,
      getCompareViewModePreference,
      getCompareContextPreference,
      getTourSeenVersionPreference,
      recordTourOpened,
    } = await loadAppFns({
      apiFetch,
      themeRegistry: {
        current: {
          name: 'theme_light_blue',
          label: 'Apricot Sand',
          source: 'variant',
          vars: { '--bg': '#9ab7d0' },
        },
        themes: [
          {
            name: 'theme_light_blue',
            label: 'Apricot Sand',
            source: 'variant',
            vars: { '--bg': '#9ab7d0' },
          },
          {
            name: 'theme_light_olive',
            label: 'Olive Parchment',
            source: 'variant',
            vars: { '--bg': '#c0c0a8' },
          },
        ],
      },
    })

    document.querySelector('.rail-nav [data-action="theme"]').click()
    document
      .getElementById('theme-select')
      .querySelector('[data-theme-name="theme_light_olive"]')
      .click()
    document
      .getElementById('theme-overlay')
      .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    document.querySelector('.rail-nav [data-action="options"]').click()
    document.getElementById('options-ts-select').value = 'elapsed'
    document
      .getElementById('options-ts-select')
      .dispatchEvent(new Event('change', { bubbles: true }))
    document.getElementById('options-ln-toggle').checked = true
    document
      .getElementById('options-ln-toggle')
      .dispatchEvent(new Event('change', { bubbles: true }))
    document.getElementById('options-welcome-select').value = 'disable_animation'
    document
      .getElementById('options-welcome-select')
      .dispatchEvent(new Event('change', { bubbles: true }))
    document.getElementById('options-share-redaction-select').value = 'redacted'
    document
      .getElementById('options-share-redaction-select')
      .dispatchEvent(new Event('change', { bubbles: true }))
    document.getElementById('options-hud-clock-select').value = 'local'
    document
      .getElementById('options-hud-clock-select')
      .dispatchEvent(new Event('change', { bubbles: true }))
    document.getElementById('options-compare-view-mode-select').value = 'side_by_side'
    document
      .getElementById('options-compare-view-mode-select')
      .dispatchEvent(new Event('change', { bubbles: true }))
    document.getElementById('options-compare-context-select').value = '10'
    document
      .getElementById('options-compare-context-select')
      .dispatchEvent(new Event('change', { bubbles: true }))
    document.getElementById('options-project-auto-link-external-runs-toggle').checked = false
    document
      .getElementById('options-project-auto-link-external-runs-toggle')
      .dispatchEvent(new Event('change', { bubbles: true }))
    document.getElementById('options-project-auto-link-run-entities-toggle').checked = false
    document
      .getElementById('options-project-auto-link-run-entities-toggle')
      .dispatchEvent(new Event('change', { bubbles: true }))
    document.getElementById('options-command-outcome-summaries-toggle').checked = false
    document
      .getElementById('options-command-outcome-summaries-toggle')
      .dispatchEvent(new Event('change', { bubbles: true }))

    expect(document.body.classList.contains('ts-elapsed')).toBe(true)
    expect(document.body.classList.contains('ln-on')).toBe(true)
    expect(document.getElementById('ts-btn').textContent).toBe('timestamps: elapsed')
    expect(document.getElementById('ln-btn').textContent).toBe('line numbers')
    expect(document.cookie).toContain('pref_theme_name=theme_light_olive')
    expect(document.cookie).toContain('pref_timestamps=elapsed')
    expect(document.cookie).toContain('pref_line_numbers=on')
    expect(document.cookie).toContain('pref_welcome_intro=disable_animation')
    expect(document.cookie).toContain('pref_share_redaction_default=redacted')
    expect(document.cookie).toContain('pref_project_auto_link_external_runs=off')
    expect(document.cookie).toContain('pref_project_auto_link_run_entities=off')
    expect(document.cookie).toContain('pref_command_outcome_summaries=off')
    expect(document.cookie).toContain('pref_hud_clock=local')
    expect(document.cookie).toContain('pref_compare_view_mode=side_by_side')
    expect(document.cookie).toContain('pref_compare_context=10')
    expect(getWelcomeIntroPreference()).toBe('disable_animation')
    expect(getShareRedactionDefaultPreference()).toBe('redacted')
    expect(getProjectAutoLinkExternalRunsPreference()).toBe('off')
    expect(getProjectAutoLinkRunEntitiesPreference()).toBe('off')
    expect(getCommandOutcomeSummariesPreference()).toBe('off')
    expect(getHudClockPreference()).toBe('local')
    expect(getCompareViewModePreference()).toBe('side_by_side')
    expect(getCompareContextPreference()).toBe('10')
    await recordTourOpened()
    expect(getTourSeenVersionPreference()).toBe(4)
    expect(document.cookie).toContain('pref_tour_seen_version=4')
    await vi.waitFor(() => {
      const postCalls = apiFetch.mock.calls.filter(([url, opts]) => url === '/session/preferences' && opts?.method === 'POST')
      expect(postCalls.length).toBeGreaterThan(0)
      const lastPayload = JSON.parse(postCalls.at(-1)[1].body)
      expect(lastPayload.preferences).toMatchObject({
        pref_theme_name: 'theme_light_olive',
        pref_timestamps: 'elapsed',
        pref_line_numbers: 'on',
        pref_welcome_intro: 'disable_animation',
        pref_share_redaction_default: 'redacted',
        pref_project_auto_link_external_runs: 'off',
        pref_project_auto_link_run_entities: 'off',
        pref_command_outcome_summaries: 'off',
        pref_hud_clock: 'local',
        pref_compare_view_mode: 'side_by_side',
        pref_compare_context: '10',
      })
    })
  })

  it('renders backend-driven FAQ items with HTML answers and dynamic sections', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/config') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              app_name: 'darklab_shell',
              prompt_username: 'anon',
              prompt_domain: 'darklab.sh',
              version: '9.9',
              default_theme: 'darklab_obsidian.yaml',
              motd: '',
              command_timeout_seconds: 120,
              max_output_lines: 5000,
              permalink_retention_days: 365,
            }),
        })
      }
      if (url === '/allowed-commands') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              restricted: true,
              commands: ['ping', 'curl'],
              groups: [{ name: 'Network', commands: ['ping', 'curl'] }],
            }),
        })
      }
      if (url === '/faq') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              items: [
                {
                  question: 'What is this?',
                  category: 'Getting started',
                  answer: 'plain',
                  answer_html: 'Rich <strong>HTML</strong>',
                },
                { question: 'Allowed?', category: 'Getting started', answer: 'allowlist', ui_kind: 'allowed_commands' },
                { question: 'Limits?', category: 'Limits & retention', answer: 'limits', ui_kind: 'limits' },
                { question: 'Custom?', category: 'Mystery bucket', answer: 'Other answer' },
              ],
            }),
        })
      }
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })

    const { openFaq } = await loadAppFns({ apiFetch })
    await new Promise((resolve) => setImmediate(resolve))

    const questions = [...document.querySelectorAll('.faq-q')].map((el) => el.textContent)
    expect(questions).toContain('What is this?')
    expect([...document.querySelectorAll('.faq-section-header')].map((el) => el.textContent)).toEqual([
      'Getting started',
      'Limits & retention',
      'Other',
    ])
    expect([...document.querySelectorAll('.faq-section')].map((section) => (
      [...section.querySelectorAll('.faq-q')].map((el) => el.textContent)
    ))).toEqual([
      ['What is this?', 'Allowed?'],
      ['Limits?'],
      ['Custom?'],
    ])
    expect(document.querySelector('.faq-a strong')?.textContent).toBe('HTML')
    expect(document.getElementById('faq-allowed-text')?.textContent).toContain('Open the Command Registry')
    expect(document.getElementById('faq-limits-text')?.innerHTML).toContain('Command timeout')
    expect(document.querySelectorAll('#faq-allowed-text .allowed-chip')).toHaveLength(0)
    window.history.replaceState(null, '', '/#faq=limits')
    openFaq()
    expect(document.querySelector('[data-faq-question="limits"]')?.classList.contains('faq-open')).toBe(true)
    document.querySelector('[data-faq-question="custom"] .faq-q')?.click()
    expect(window.location.hash).toBe('#faq=custom')
    window.history.replaceState(null, '', '/')
  })

  it('renders the FAQ visual tour re-entry link and opens the tour modal', async () => {
    const openTourModal = vi.fn(() => true)
    const { openFaq } = await loadAppFns({
      openTourModal,
      mobileViewport: { height: 700, offsetTop: 0 },
      mobileTouch: false,
      appConfig: {
        tour_enabled: true,
        tour_version: 1,
        tour_chapters: [{ id: 'running_commands', title: 'Running commands' }],
      },
      apiFetch: vi.fn((url) => {
        if (url === '/config') {
          return Promise.resolve({
            json: () =>
              Promise.resolve({
                app_name: 'darklab_shell',
                prompt_username: 'anon',
                prompt_domain: 'darklab.sh',
                version: '9.9',
                default_theme: 'darklab_obsidian.yaml',
                motd: '',
                tour_enabled: true,
                tour_version: 1,
                tour_chapters: [{ id: 'running_commands', title: 'Running commands' }],
              }),
          })
        }
        if (url === '/allowed-commands') {
          return Promise.resolve({ json: () => Promise.resolve({ commands: [], groups: [] }) })
        }
        if (url === '/faq') {
          return Promise.resolve({
            json: () => Promise.resolve({ items: [{ question: 'What is this?', answer: 'plain' }] }),
          })
        }
        return Promise.resolve({ json: () => Promise.resolve({}) })
      }),
    })
    await new Promise((resolve) => setImmediate(resolve))

    const faqOverlay = document.getElementById('faq-overlay')
    openFaq()
    expect(faqOverlay.classList.contains('open')).toBe(true)
    const button = document.querySelector('.faq-tour-open')
    expect(button).not.toBeNull()
    delete window.hideFaqOverlay
    delete globalThis.hideFaqOverlay
    button.click()

    expect(openTourModal).toHaveBeenCalledWith({
      source: 'faq',
    })
    expect(faqOverlay.classList.contains('open')).toBe(false)
  })

  it('suppresses the FAQ visual tour re-entry link when the tour is disabled', async () => {
    await loadAppFns({
      mobileViewport: { height: 700, offsetTop: 0 },
      mobileTouch: false,
      appConfig: {
        tour_enabled: false,
        tour_chapters: [{ id: 'running_commands', title: 'Running commands' }],
      },
      apiFetch: vi.fn((url) => {
        if (url === '/config') {
          return Promise.resolve({
            json: () =>
              Promise.resolve({
                app_name: 'darklab_shell',
                prompt_username: 'anon',
                prompt_domain: 'darklab.sh',
                version: '9.9',
                default_theme: 'darklab_obsidian.yaml',
                motd: '',
                tour_enabled: false,
                tour_chapters: [{ id: 'running_commands', title: 'Running commands' }],
              }),
          })
        }
        if (url === '/allowed-commands') {
          return Promise.resolve({ json: () => Promise.resolve({ commands: [], groups: [] }) })
        }
        if (url === '/faq') {
          return Promise.resolve({
            json: () => Promise.resolve({ items: [{ question: 'What is this?', answer: 'plain' }] }),
          })
        }
        return Promise.resolve({ json: () => Promise.resolve({}) })
      }),
    })
    await new Promise((resolve) => setImmediate(resolve))

    expect(document.querySelector('.faq-tour-open')).toBeNull()
  })

  it('opens command catalog details from the command registry browser', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/config') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              app_name: 'darklab_shell',
              prompt_username: 'anon',
              prompt_domain: 'darklab.sh',
              version: '9.9',
              default_theme: 'darklab_obsidian.yaml',
              motd: '',
              command_timeout_seconds: 120,
              max_output_lines: 5000,
              permalink_retention_days: 365,
            }),
        })
      }
      if (url === '/allowed-commands') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              restricted: true,
              commands: ['curl'],
              groups: [{ name: 'Network', commands: ['curl'] }],
            }),
        })
      }
      if (url === '/commands/catalog') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              restricted: true,
              commands: [
                {
                  root: 'curl',
                  category: 'Network',
                  description: 'Transfer data from URLs.',
                  example_count: 1,
                  subcommand_count: 1,
                  flag_count: 1,
                },
              ],
              groups: [
                {
                  name: 'Network',
                  commands: [
                    {
                      root: 'curl',
                      category: 'Network',
                      description: 'Transfer data from URLs.',
                      example_count: 1,
                      subcommand_count: 1,
                      flag_count: 1,
                    },
                  ],
                },
              ],
            }),
        })
      }
      if (url === '/faq') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              items: [{ question: 'Allowed?', answer: 'allowlist', ui_kind: 'allowed_commands' }],
            }),
        })
      }
      if (url === '/commands/catalog/curl') {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              root: 'curl',
              category: 'Network',
              description: 'Transfer data from URLs.',
              examples: [{ value: 'curl https://darklab.sh', description: 'Fetch a URL' }],
              arguments: [{ value: '<url>', description: 'Target URL', value_type: 'url' }],
              subcommands: [
                {
                  name: 'trace',
                  description: 'Show request timing details.',
                  examples: [{ value: 'curl trace https://darklab.sh', description: 'Trace a URL' }],
                  arguments: [{ value: '<url>', description: 'URL to trace', value_type: 'url' }],
                  flags: [
                    {
                      value: '--format',
                      description: 'Output format',
                      takes_value: true,
                      value_hints: [{ value: 'json' }, { value: 'text' }],
                    },
                  ],
                },
              ],
              flags: [{ value: '-L', description: 'Follow redirects' }],
              workspace_flags: [],
              runtime_notes: [],
            }),
        })
      }
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })

    const { openFaq, openCommandRegistry } = await loadAppFns({ apiFetch, mobileViewport: { height: 500, offsetTop: 0 } })
    await new Promise((resolve) => setImmediate(resolve))

    const mobileCmdInput = document.getElementById('mobile-cmd')
    openFaq()
    expect(mobileCmdInput.blur).toHaveBeenCalled()

    openCommandRegistry()
    expect(document.getElementById('command-registry-overlay').classList.contains('open')).toBe(true)
    expect(document.getElementById('command-registry-body').textContent).toContain('curl')

    document.querySelector('[data-command-registry-root="curl"]').click()
    await Promise.resolve()
    await Promise.resolve()

    expect(document.getElementById('command-catalog-overlay').classList.contains('open')).toBe(true)
    expect(document.getElementById('command-catalog-body').textContent).toContain('Transfer data from URLs.')
    expect(document.getElementById('command-catalog-body').textContent).toContain('Arguments')
    expect(document.getElementById('command-catalog-body').textContent).toContain('<url>')
    expect(document.getElementById('command-catalog-body').textContent).toContain('Subcommand: curl trace')
    expect(document.getElementById('command-catalog-body').textContent).toContain('Show request timing details.')
    expect(document.getElementById('command-catalog-body').textContent).toContain('curl trace https://darklab.sh')
    expect(document.getElementById('command-catalog-body').textContent).toContain('--format json, text')
    expect(document.getElementById('command-catalog-body').textContent).not.toContain('App Handling')
    expect(mobileCmdInput.value).toBe('')
    expect(mobileCmdInput.focus).not.toHaveBeenCalled()
  })

  it('opens autocomplete after loading a command catalog example chip', async () => {
    const acShow = vi.fn()
    const apiFetch = vi.fn((url) => {
      if (url === '/config') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              app_name: 'darklab_shell',
              prompt_username: 'anon',
              prompt_domain: 'darklab.sh',
              version: '9.9',
              default_theme: 'darklab_obsidian.yaml',
              motd: '',
              command_timeout_seconds: 120,
              max_output_lines: 5000,
              permalink_retention_days: 365,
            }),
        })
      }
      if (url === '/allowed-commands') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              restricted: true,
              commands: ['nc'],
              groups: [{ name: 'Network', commands: ['nc'] }],
            }),
        })
      }
      if (url === '/commands/catalog') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              restricted: true,
              commands: [
                {
                  root: 'nc',
                  category: 'Network',
                  description: 'Open TCP connections.',
                  example_count: 1,
                  subcommand_count: 0,
                  flag_count: 1,
                },
              ],
              groups: [],
            }),
        })
      }
      if (url === '/faq') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              items: [{ question: 'Allowed?', answer: 'allowlist', ui_kind: 'allowed_commands' }],
            }),
        })
      }
      if (url === '/commands/catalog/nc') {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              root: 'nc',
              category: 'Network',
              description: 'Open TCP connections.',
              examples: [{ value: 'nc', description: 'Check port' }],
              subcommands: [],
              flags: [{ value: '-z', description: 'Zero-I/O mode' }],
              workspace_flags: [],
              runtime_notes: [],
            }),
        })
      }
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })

    const { openCommandRegistry } = await loadAppFns({
      apiFetch,
      getAutocompleteMatches: (value, cursor) => (
        value === 'nc ' && cursor === 3
          ? [{ value: '-z', description: 'Zero-I/O mode', replaceStart: 3, replaceEnd: 3 }]
          : []
      ),
      acShow,
    })
    await new Promise((resolve) => setImmediate(resolve))

    openCommandRegistry()
    document.querySelector('[data-command-registry-root="nc"]').click()
    await Promise.resolve()
    await Promise.resolve()

    expect(document.getElementById('command-catalog-overlay').classList.contains('open')).toBe(true)
    expect(document.getElementById('command-catalog-body').textContent).toContain('Open TCP connections.')
    document.querySelector('[data-command-example]').click()

    expect(document.getElementById('mobile-cmd').value).toBe('nc ')
    expect(acShow).toHaveBeenCalledWith([
      { value: '-z', description: 'Zero-I/O mode', replaceStart: 3, replaceEnd: 3 },
    ])
  })

  it('loads custom FAQ chips into the prompt with the same command-chip behavior', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/config') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              app_name: 'darklab_shell',
              prompt_username: 'anon',
              prompt_domain: 'darklab.sh',
              version: '9.9',
              default_theme: 'darklab_obsidian.yaml',
              motd: '',
              command_timeout_seconds: 120,
              max_output_lines: 5000,
              permalink_retention_days: 365,
            }),
        })
      }
      if (url === '/allowed-commands') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              restricted: true,
              commands: ['curl'],
              groups: [{ name: 'Network', commands: ['curl'] }],
            }),
        })
      }
      if (url === '/faq') {
        return Promise.resolve({
          json: () =>
            Promise.resolve({
              items: [
                {
                  question: 'Styled custom FAQ?',
                  answer: 'Use [[cmd:ping -c 1 127.0.0.1|ping chip]] and **bold**.',
                  answer_html:
                    'Use <span class="allowed-chip faq-chip" data-faq-command="ping -c 1 127.0.0.1" role="button" tabindex="0">ping chip</span> and <strong>bold</strong>.',
                },
              ],
            }),
        })
      }
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })

    await loadAppFns({ apiFetch, mobileViewport: { height: 500, offsetTop: 0 } })
    await new Promise((resolve) => setImmediate(resolve))

    const chip = document.querySelector(
      '.faq-item .faq-chip[data-faq-command="ping -c 1 127.0.0.1"]',
    )
    expect(chip).not.toBeNull()

    chip.click()

    expect(document.getElementById('mobile-cmd').value).toBe('ping -c 1 127.0.0.1 ')
    expect(document.getElementById('faq-overlay').classList.contains('open')).toBe(false)
  })
})

// ── Run notification preference ───────────────────────────────────────────────

describe('getRunNotifyPreference', () => {
  it('returns off when no cookie is set', async () => {
    const { getRunNotifyPreference } = await loadAppFns({})
    expect(getRunNotifyPreference()).toBe('off')
  })

  it('returns on when cookie is set to on', async () => {
    const { getRunNotifyPreference } = await loadAppFns({
      cookies: { pref_run_notify: 'on' },
    })
    expect(getRunNotifyPreference()).toBe('on')
  })

  it('returns off for any value other than on', async () => {
    const { getRunNotifyPreference } = await loadAppFns({
      cookies: { pref_run_notify: 'yes' },
    })
    expect(getRunNotifyPreference()).toBe('off')
  })
})

describe('applyRunNotifyPreference', () => {
  it('saves on and syncs toggle when permission is already granted', async () => {
    class MockNotification {}
    MockNotification.permission = 'granted'
    const { applyRunNotifyPreference, getRunNotifyPreference } = await loadAppFns({
      Notification: MockNotification,
    })
    await applyRunNotifyPreference('on')
    expect(getRunNotifyPreference()).toBe('on')
    expect(document.getElementById('options-notify-toggle').checked).toBe(true)
  })

  it('requests permission when it is default and saves on if granted', async () => {
    class MockNotification {}
    MockNotification.permission = 'default'
    MockNotification.requestPermission = vi.fn().mockResolvedValue('granted')
    const { applyRunNotifyPreference, getRunNotifyPreference } = await loadAppFns({
      Notification: MockNotification,
    })
    await applyRunNotifyPreference('on')
    expect(MockNotification.requestPermission).toHaveBeenCalledOnce()
    expect(getRunNotifyPreference()).toBe('on')
  })

  it('falls back to off and unchecks toggle when permission request is denied', async () => {
    class MockNotification {}
    MockNotification.permission = 'default'
    MockNotification.requestPermission = vi.fn().mockResolvedValue('denied')
    const { applyRunNotifyPreference, getRunNotifyPreference } = await loadAppFns({
      Notification: MockNotification,
    })
    await applyRunNotifyPreference('on')
    expect(getRunNotifyPreference()).toBe('off')
    expect(document.getElementById('options-notify-toggle').checked).toBe(false)
  })

  it('falls back to off and shows toast when permission is already denied by browser', async () => {
    const showToast = vi.fn()
    class MockNotification {}
    MockNotification.permission = 'denied'
    const { applyRunNotifyPreference, getRunNotifyPreference } = await loadAppFns({
      Notification: MockNotification,
      showToast,
    })
    await applyRunNotifyPreference('on')
    expect(getRunNotifyPreference()).toBe('off')
    expect(showToast).toHaveBeenCalledWith(expect.stringContaining('blocked'))
  })

  it('saves off and unchecks toggle when mode is off', async () => {
    const { applyRunNotifyPreference, getRunNotifyPreference } = await loadAppFns({
      cookies: { pref_run_notify: 'on' },
    })
    await applyRunNotifyPreference('off')
    expect(getRunNotifyPreference()).toBe('off')
    expect(document.getElementById('options-notify-toggle').checked).toBe(false)
  })
})

describe('syncOptionsControls notify toggle', () => {
  it('reflects off preference as unchecked toggle', async () => {
    const { syncOptionsControls } = await loadAppFns({})
    syncOptionsControls()
    expect(document.getElementById('options-notify-toggle').checked).toBe(false)
    expect(document.getElementById('options-command-outcome-summaries-toggle').checked).toBe(true)
  })

  it('reflects on preference as checked toggle', async () => {
    const { syncOptionsControls } = await loadAppFns({
      cookies: { pref_run_notify: 'on', pref_command_outcome_summaries: 'off' },
    })
    syncOptionsControls()
    expect(document.getElementById('options-notify-toggle').checked).toBe(true)
    expect(document.getElementById('options-command-outcome-summaries-toggle').checked).toBe(false)
  })
})
