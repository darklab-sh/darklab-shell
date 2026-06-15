// ── Shared entity metadata client ──
import { apiFetch as importedApiFetch } from '../session.js';

let DarklabEntityMetadata = null;

(function initEntityMetadataClient(global) {
  function parseLabelInput(value) {
    const seen = new Set();
    return String(value || '')
      .split(',')
      .map(item => item.trim())
      .filter(Boolean)
      .filter((item) => {
        const key = item.toLocaleLowerCase();
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
  }

  function entityMetadataUrl(entityType, entityId, suffix = '') {
    return `/entities/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}/${suffix}`;
  }

  function _metadataFetch(apiFetchImpl) {
    if (typeof apiFetchImpl === 'function') return apiFetchImpl;
    if (typeof importedApiFetch === 'function') return importedApiFetch;
    throw new Error('Entity metadata requests are unavailable');
  }

  async function entityMetadataRequest(url, options = {}, { apiFetchImpl = null, onWrite = null } = {}) {
    const method = String(options.method || 'GET').toUpperCase();
    const resp = await _metadataFetch(apiFetchImpl)(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
      },
    });
    if (!resp.ok) {
      let message = `HTTP ${resp.status}`;
      try {
        const data = await resp.json();
        if (data && data.error) message = data.error;
      } catch (_) {}
      throw new Error(message);
    }
    if (method !== 'GET' && method !== 'HEAD' && typeof onWrite === 'function') {
      onWrite(resp);
    }
    return resp;
  }

  function _requestForOptions(options = {}) {
    if (typeof options.request === 'function') return options.request;
    return (url, requestOptions = {}) => entityMetadataRequest(url, requestOptions, options);
  }

  function _labelValues(labels) {
    return (Array.isArray(labels) ? labels : [])
      .map(label => String(label && typeof label === 'object' ? label.label : label || '').trim())
      .filter(Boolean);
  }

  async function syncEntityLabels(entityType, entityId, nextLabels, options = {}) {
    const request = _requestForOptions(options);
    const labelsUrl = entityMetadataUrl(entityType, entityId, 'labels');
    const resp = await request(labelsUrl, { cache: 'no-store' });
    const data = await resp.json().catch(() => ({}));
    const currentValues = _labelValues(data.labels);
    const nextValues = _labelValues(nextLabels);
    const nextSet = new Set(nextValues);
    const currentSet = new Set(currentValues);
    for (const label of currentValues) {
      if (!nextSet.has(label)) {
        await request(labelsUrl, {
          method: 'DELETE',
          body: JSON.stringify({ label }),
        });
      }
    }
    for (const label of nextValues) {
      if (!currentSet.has(label)) {
        await request(labelsUrl, {
          method: 'POST',
          body: JSON.stringify({ label }),
        });
      }
    }
  }

  async function syncEntityNote(entityType, entityId, body, options = {}) {
    const request = _requestForOptions(options);
    const noteUrl = entityMetadataUrl(entityType, entityId, 'note');
    const value = String(body || '').trim();
    if (value) {
      await request(noteUrl, {
        method: 'PUT',
        body: JSON.stringify({ body: value }),
      });
      return;
    }
    try {
      await request(noteUrl, { method: 'DELETE' });
    } catch (err) {
      if (!String(err && err.message || '').includes('not found')) throw err;
    }
  }

  DarklabEntityMetadata = {
    parseLabelInput,
    entityMetadataUrl,
    entityMetadataRequest,
    syncEntityLabels,
    syncEntityNote,
  };
})(typeof window !== 'undefined' ? window : globalThis);

const {
  entityMetadataRequest,
  entityMetadataUrl,
  parseLabelInput,
  syncEntityLabels,
  syncEntityNote,
} = DarklabEntityMetadata;

export {
  DarklabEntityMetadata,
  entityMetadataRequest,
  entityMetadataUrl,
  parseLabelInput,
  syncEntityLabels,
  syncEntityNote,
};
