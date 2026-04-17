#!/usr/bin/env node

import { readdirSync, readFileSync } from 'fs';
import { resolve } from 'path';

const ROOT = resolve(process.cwd());

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
