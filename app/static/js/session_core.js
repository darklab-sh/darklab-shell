// ── Session identity pure helpers ─────────────────────────────────────────
// Loaded before session.js. Kept in a small namespace so unit tests and the
// classic browser bundle can share the same pure transforms without extracting
// them from the full session script.
(function (global) {
  function _cryptoApi(preferred) {
    if (preferred && typeof preferred === 'object') return preferred;
    if (global && global.crypto) return global.crypto;
    if (typeof crypto !== 'undefined') return crypto;
    return null;
  }

  function generateUUID(preferredCrypto) {
    const primary = _cryptoApi(preferredCrypto);
    if (primary && typeof primary.randomUUID === 'function') {
      try { return primary.randomUUID(); } catch (_) {}
    }
    const fallback = primary && typeof primary.getRandomValues === 'function'
      ? primary
      : _cryptoApi(null);
    if (!fallback || typeof fallback.getRandomValues !== 'function') {
      throw new Error('crypto.getRandomValues is unavailable');
    }
    const bytes = new Uint8Array(16);
    fallback.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, value => value.toString(16).padStart(2, '0'));
    return `${hex.slice(0, 4).join('')}-${hex.slice(4, 6).join('')}-${hex.slice(6, 8).join('')}-${hex.slice(8, 10).join('')}-${hex.slice(10).join('')}`;
  }

  function getOrCreateStorageValue(storage, key, createValue) {
    let value = storage.getItem(key);
    if (!value) {
      value = createValue();
      storage.setItem(key, value);
    }
    return value;
  }

  function resolveSessionId(storage, sessionUuid) {
    return storage.getItem('session_token') || sessionUuid;
  }

  function maskSessionToken(token) {
    if (typeof token !== 'string' || !token) return '(none)';
    if (token.startsWith('tok_')) return 'tok_' + token.slice(4, 8) + '••••';
    return token.slice(0, 8) + '••••••••';
  }

  function describeFetchError(err, context = 'server') {
    const offlineMessage = `Unable to contact the ${context} right now. Please try again in a moment. If this keeps happening, contact the shell operator.`;
    const message = (err && typeof err.message === 'string') ? err.message.trim() : '';
    if (!message) return offlineMessage;
    const lower = message.toLowerCase();
    if (
      lower.includes('networkerror')
      || lower.includes('failed to fetch')
      || lower.includes('network down')
      || lower.includes('load failed')
    ) {
      return offlineMessage;
    }
    return `Request to the ${context} failed: ${message}`;
  }

  function withSessionHeaders(options = {}, sessionId, clientId) {
    return {
      ...options,
      headers: Object.assign({}, options.headers || {}, {
        'X-Session-ID': sessionId,
        'X-Client-ID': clientId,
      }),
    };
  }

  global.DarklabSessionCore = Object.freeze({
    generateUUID,
    getOrCreateStorageValue,
    resolveSessionId,
    maskSessionToken,
    describeFetchError,
    withSessionHeaders,
  });
})(typeof window !== 'undefined' ? window : globalThis);
