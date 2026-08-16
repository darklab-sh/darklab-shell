// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { defineConfig } from 'vitest/config'
import { fileURLToPath } from 'url'
import { dirname, resolve } from 'path'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

export default defineConfig({
  test: {
    environment: 'jsdom',
    environmentOptions: {
      jsdom: {
        url: 'http://localhost/',
      },
    },
    globals: true,
    root: rootDir,
    include: ['tests/js/unit/**/*.test.js'],
    // Large jsdom suites contend heavily when every host CPU becomes a worker.
    // Keep file-level parallelism bounded and leave enough wall-clock headroom
    // for a ready worker to resume on constrained development and CI hosts.
    maxWorkers: 2,
    testTimeout: 20_000,
  },
})
