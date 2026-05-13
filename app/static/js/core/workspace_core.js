// ── Workspace pure helpers ────────────────────────────────────────────────
// Loaded before workspace.js. Keep DOM/API behavior in workspace.js and share
// small path/format transforms here.
(function (global) {
  function formatBytes(bytes) {
    const value = Number(bytes) || 0;
    if (value < 1024) return `${value} B`;
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(1).replace(/\.0$/, '')} KB`;
    return `${(value / (1024 * 1024)).toFixed(1).replace(/\.0$/, '')} MB`;
  }

  function normalizeDir(path = '') {
    const parts = String(path || '').split('/').map(part => part.trim()).filter(Boolean);
    return parts.join('/');
  }

  function normalizeCommandPath(path = '', cwd = '') {
    const raw = String(path ?? '').trim();
    const baseParts = raw.startsWith('/') ? [] : normalizeDir(cwd).split('/').filter(Boolean);
    const rawParts = raw.split('/').filter(part => part !== '');
    for (const part of rawParts) {
      const trimmed = String(part || '').trim();
      if (!trimmed || trimmed === '.') continue;
      if (trimmed === '..') {
        if (baseParts.length) {
          baseParts.pop();
          continue;
        }
        throw new Error('path escapes the session workspace');
      }
      if (trimmed.includes('\\') || trimmed.includes('\x00')) {
        throw new Error('file name contains unsupported characters');
      }
      baseParts.push(trimmed);
    }
    return baseParts.join('/');
  }

  function displayPath(path = '') {
    const normalized = normalizeDir(path);
    return normalized ? `/${normalized}` : '/';
  }

  function parentDir(path = '') {
    const parts = normalizeDir(path).split('/').filter(Boolean);
    parts.pop();
    return parts.join('/');
  }

  function basename(path = '') {
    const parts = String(path || '').split('/').filter(Boolean);
    return parts[parts.length - 1] || String(path || '');
  }

  global.DarklabWorkspaceCore = Object.freeze({
    formatBytes,
    normalizeDir,
    normalizeCommandPath,
    displayPath,
    parentDir,
    basename,
  });
})(typeof window !== 'undefined' ? window : globalThis);
