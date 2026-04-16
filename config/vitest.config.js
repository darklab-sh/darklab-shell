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
  },
})
