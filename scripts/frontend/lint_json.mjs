#!/usr/bin/env node
// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { existsSync, readdirSync, readFileSync } from 'fs';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';

function findRepoRoot(startDir) {
  let current = resolve(startDir);
  while (true) {
    if (existsSync(resolve(current, 'package.json')) && existsSync(resolve(current, 'app'))) {
      return current;
    }
    const parent = dirname(current);
    if (parent === current) throw new Error('could not locate the darklab_shell repository root');
    current = parent;
  }
}

const ROOT = findRepoRoot(dirname(fileURLToPath(import.meta.url)));

function isIgnored(path) {
  return path.includes('/.git/') || path.includes('/node_modules/');
}

function collectJsonFiles(dir) {
  const entries = [];
  const stack = [dir];
  while (stack.length) {
    const current = stack.pop();
    for (const name of readdirSync(current, { withFileTypes: true })) {
      const full = resolve(current, name.name);
      if (isIgnored(full)) continue;
      if (name.isDirectory()) {
        stack.push(full);
      } else if (name.isFile() && name.name.endsWith('.json')) {
        entries.push(full);
      }
    }
  }
  return entries;
}

let hadError = false;
const files = collectJsonFiles(ROOT);
for (const file of files) {
  try {
    JSON.parse(readFileSync(file, 'utf8'));
  } catch (err) {
    hadError = true;
    console.error(`${file}: ${err.message}`);
  }
}

if (hadError) process.exit(1);
if (!files.length) {
  console.error('No JSON files found');
  process.exit(1);
}
