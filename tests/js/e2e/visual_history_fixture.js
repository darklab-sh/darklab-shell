import {
  VISUAL_HISTORY_FIXTURE_NAME,
  VISUAL_HISTORY_MIN_ROOTS,
  VISUAL_HISTORY_MIN_RUNS,
} from '../../../config/playwright.visual.contracts.js'

const COMMAND_TEMPLATES = [
  ['nslookup -type=A darklab.sh', 0],
  ['ping -i 0.5 -c 50 darklab.sh', 0],
  ['curl -s https://api.ipify.org', 0],
  ['dig @8.8.8.8 darklab.sh A', 0],
  ['host -t A darklab.sh', 0],
  ['openssl s_client -connect darklab.sh:443', 0],
  ['whois darklab.sh', 0],
  ['traceroute darklab.sh', 0],
  ['nmap -p 80,443 darklab.sh', 0],
  ['curl -I https://darklab.sh', 0],
  ['mtr --report darklab.sh', 0],
  ['dig +short darklab.sh MX', 0],
  ['curl -sv https://darklab.sh 2>&1', 0],
  ['nmap -sV -p 22,80,443 darklab.sh', 0],
  ['dig darklab.sh NS', 0],
  ['ping -c 10 darklab.sh', 0],
  ['openssl s_client -connect darklab.sh:443 -showcerts', 0],
  ['host -t MX darklab.sh', 0],
  ['curl -o /dev/null -w "%{http_code}" https://darklab.sh', 0],
  ['nslookup -type=MX darklab.sh', 0],
  ['traceroute -n darklab.sh', 1],
  ['whois 104.21.0.1', 0],
  ['naabu -host darklab.sh', 0],
  ['dnsx -resp -a darklab.sh', 0],
  ['ping darklab.sh', -15],
]

const GRACEFUL_TERMINATION_EXIT_CODES = new Set([-15])

function isFailedExitCode(exitCode) {
  if (exitCode === null || exitCode === undefined || exitCode === '') return false
  const code = Number(exitCode)
  return Number.isFinite(code) && code !== 0 && !GRACEFUL_TERMINATION_EXIT_CODES.has(code)
}

export function buildVisualHistoryRuns({
  now = Date.now(),
  count = VISUAL_HISTORY_MIN_RUNS,
} = {}) {
  return Array.from({ length: count }, (_, index) => {
    const [command, exitCode] = COMMAND_TEMPLATES[index % COMMAND_TEMPLATES.length]
    const ageMs = ((index * 47) + 2) * 60_000
    return {
      id: `${VISUAL_HISTORY_FIXTURE_NAME}-${String(index + 1).padStart(4, '0')}`,
      command,
      exit_code: exitCode,
      started: new Date(now - ageMs).toISOString(),
      full_output_available: index % 5 === 0,
    }
  })
}

function commandRootsFromRuns(runs) {
  return [...new Set(runs.map((run) => String(run.command || '').trim().split(/\s+/, 1)[0]).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b))
}

function filterRuns(runs, params) {
  let next = runs
  const q = String(params.get('q') || '').trim().toLowerCase()
  if (q) next = next.filter((run) => String(run.command || '').toLowerCase().includes(q))

  const commandRoot = String(params.get('command_root') || '').trim().toLowerCase()
  if (commandRoot) {
    next = next.filter((run) => String(run.command || '').trim().split(/\s+/, 1)[0].toLowerCase() === commandRoot)
  }

  const exitCode = String(params.get('exit_code') || '').trim()
  if (exitCode === '0') next = next.filter((run) => Number(run.exit_code) === 0)
  else if (exitCode === 'nonzero') next = next.filter((run) => isFailedExitCode(run.exit_code))

  return next
}

export function buildVisualHistoryPayload(
  requestUrl,
  {
    now = Date.now(),
    count = VISUAL_HISTORY_MIN_RUNS,
  } = {},
) {
  const url = new URL(requestUrl, 'http://localhost')
  const params = url.searchParams
  const pageSize = Math.max(1, Number(params.get('page_size')) || 50)
  const includeTotal = params.get('include_total') === '1'

  const allRuns = buildVisualHistoryRuns({ now, count })
  const filteredRuns = filterRuns(allRuns, params)
  const roots = commandRootsFromRuns(filteredRuns.length ? filteredRuns : allRuns)
  const totalCount = filteredRuns.length
  const pageCount = totalCount ? Math.ceil(totalCount / pageSize) : 0
  const currentPage = Math.max(1, Math.min(Number(params.get('page')) || 1, pageCount || 1))
  const offset = (currentPage - 1) * pageSize
  const pageRuns = filteredRuns.slice(offset, offset + pageSize)
  const pageItems = pageRuns.map((run) => ({
    ...run,
    type: 'run',
    label: run.command,
    created: run.started,
  }))

  const payload = {
    items: pageItems,
    runs: pageRuns,
    roots: roots.slice(0, Math.max(VISUAL_HISTORY_MIN_ROOTS, roots.length)),
    page: currentPage,
    page_size: pageSize,
    has_prev: currentPage > 1,
    has_next: Boolean(pageCount && currentPage < pageCount),
  }
  if (includeTotal) {
    payload.total_count = totalCount
    payload.page_count = pageCount
  }
  return payload
}
