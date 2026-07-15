// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// History permalink and snapshot link helpers.
import { shareUrl as importedShareUrl } from '../../core/utils.js';

const HISTORY_LINKS_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

function _historyShareUrl() {
  return (typeof importedShareUrl !== 'undefined' && importedShareUrl)
    || (typeof HISTORY_LINKS_GLOBAL?.shareUrl === 'function' ? HISTORY_LINKS_GLOBAL.shareUrl : null);
}

function _snapshotUrl(snapshot) {
  return `${location.origin}/share/${snapshot.id}`;
}

function _historyRunPermalinkUrl(run) {
  return `${location.origin}/history/${run.id}`;
}

function openSnapshotLink(snapshot) {
  if (!snapshot || !snapshot.id) return;
  const url = _snapshotUrl(snapshot);
  if (typeof window !== 'undefined' && window && typeof window.open === 'function') {
    window.open(url, '_blank', 'noopener,noreferrer');
  }
}

function copySnapshotLink(snapshot) {
  const share = _historyShareUrl();
  return typeof share === 'function' ? share(_snapshotUrl(snapshot)) : Promise.resolve(false);
}

function copyHistoryRunPermalink(run) {
  const share = _historyShareUrl();
  return typeof share === 'function' ? share(_historyRunPermalinkUrl(run)) : Promise.resolve(false);
}

if (typeof window !== 'undefined') {
}

export {
  _historyRunPermalinkUrl,
  _snapshotUrl,
  copyHistoryRunPermalink,
  copySnapshotLink,
  openSnapshotLink,
};
