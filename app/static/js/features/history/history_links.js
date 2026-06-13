// History permalink and snapshot link helpers.

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
  return shareUrl(_snapshotUrl(snapshot));
}

function copyHistoryRunPermalink(run) {
  return shareUrl(_historyRunPermalinkUrl(run));
}

if (typeof window !== 'undefined') {
  Object.assign(window, {
    openSnapshotLink,
    copySnapshotLink,
    copyHistoryRunPermalink,
  });
}
