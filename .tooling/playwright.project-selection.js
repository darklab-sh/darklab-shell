// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

export function selectedProjectNames(report) {
  const names = new Set()
  function visit(suites) {
    for (const suite of suites || []) {
      for (const spec of suite.specs || []) {
        for (const test of spec.tests || []) names.add(test.projectName)
      }
      visit(suite.suites)
    }
  }
  visit(report.suites)
  if ([...names].some((name) => typeof name !== 'string' || !name)) {
    throw new Error('Playwright listing contains an unnamed project')
  }
  return [...names].sort()
}

export function selectedWebServers(entries, selection = process.env.PW_SELECTED_PROJECTS) {
  if (!selection) return entries.map(([, server]) => server)
  let names
  try { names = JSON.parse(selection) } catch { throw new Error('Invalid Playwright project selection') }
  if (!Array.isArray(names) || names.some((name) => !entries.some(([known]) => known === name))) {
    throw new Error('Unknown Playwright project in server selection')
  }
  return entries.filter(([name]) => names.includes(name)).map(([, server]) => server)
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const report = JSON.parse(readFileSync(process.argv[2], 'utf8'))
  process.stdout.write(JSON.stringify(selectedProjectNames(report)))
}
