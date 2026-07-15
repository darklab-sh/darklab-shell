// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

var DarklabRunOutputModel = (function (global) {
  'use strict';

  const LINE_EVENT_SCHEMA_VERSION = 1;
  const LINE_KIND_VALUES = Object.freeze(['info', 'notice', 'warn', 'error']);
  const LINE_ROLE_VALUES = Object.freeze([
    'body',
    'prompt-echo',
    'section-header',
    'kv',
    'help-row',
    'pty-marker',
    'progress',
    'status-line',
    'success',
    'denied',
    'exit-ok',
    'exit-fail',
  ]);
  const LINE_SIGNAL_VALUES = Object.freeze(['findings', 'warnings', 'errors', 'summaries']);
  const LINE_NOISE_KIND_VALUES = Object.freeze(['progress', 'status', 'boilerplate']);

  const LineKind = Object.freeze({
    INFO: 'info',
    NOTICE: 'notice',
    WARN: 'warn',
    ERROR: 'error',
  });

  const LineRole = Object.freeze({
    BODY: 'body',
    PROMPT_ECHO: 'prompt-echo',
    SECTION_HEADER: 'section-header',
    KV: 'kv',
    HELP_ROW: 'help-row',
    PTY_MARKER: 'pty-marker',
    PROGRESS: 'progress',
    STATUS_LINE: 'status-line',
    SUCCESS: 'success',
    DENIED: 'denied',
    EXIT_OK: 'exit-ok',
    EXIT_FAIL: 'exit-fail',
  });

  const LineSignal = Object.freeze({
    FINDINGS: 'findings',
    WARNINGS: 'warnings',
    ERRORS: 'errors',
    SUMMARIES: 'summaries',
  });

  const LineNoiseKind = Object.freeze({
    PROGRESS: 'progress',
    STATUS: 'status',
    BOILERPLATE: 'boilerplate',
  });

  const LEGACY_KIND_BY_CLS = Object.freeze({
    '': LineKind.INFO,
    output: LineKind.INFO,
    out: LineKind.INFO,
    cmd: LineKind.INFO,
    notice: LineKind.NOTICE,
    'builtin-note': LineKind.NOTICE,
    'welcome-output': LineKind.NOTICE,
    warn: LineKind.WARN,
    warning: LineKind.WARN,
    error: LineKind.ERROR,
  });

  const LEGACY_ROLE_BY_CLS = Object.freeze({
    '': LineRole.BODY,
    output: LineRole.BODY,
    out: LineRole.BODY,
    notice: LineRole.BODY,
    warn: LineRole.BODY,
    warning: LineRole.BODY,
    error: LineRole.BODY,
    'builtin-note': LineRole.BODY,
    'builtin-spacer': LineRole.BODY,
    'welcome-output': LineRole.BODY,
    cmd: LineRole.PROMPT_ECHO,
    'prompt-echo': LineRole.PROMPT_ECHO,
    'builtin-section': LineRole.SECTION_HEADER,
    'builtin-kv': LineRole.KV,
    'builtin-help-row': LineRole.HELP_ROW,
    'builtin-faq-q': LineRole.HELP_ROW,
    'builtin-faq-a': LineRole.HELP_ROW,
    'pty-marker': LineRole.PTY_MARKER,
    progress: LineRole.PROGRESS,
    'status-line': LineRole.STATUS_LINE,
    'builtin-success': LineRole.SUCCESS,
    denied: LineRole.DENIED,
    'exit-ok': LineRole.EXIT_OK,
    'exit-fail': LineRole.EXIT_FAIL,
  });

  const KIND_LEGACY_CLS = Object.freeze({
    info: '',
    notice: 'notice',
    warn: 'warn',
    error: 'error',
  });

  const ROLE_LEGACY_CLS = Object.freeze({
    body: '',
    'prompt-echo': 'prompt-echo',
    'section-header': 'builtin-section',
    kv: 'builtin-kv',
    'help-row': 'builtin-help-row',
    'pty-marker': 'pty-marker',
    progress: 'progress',
    'status-line': 'status-line',
    success: 'builtin-success',
    denied: 'denied',
    'exit-ok': 'exit-ok',
    'exit-fail': 'exit-fail',
  });

  const NOISE_KIND_BY_ROLE = Object.freeze({
    progress: LineNoiseKind.PROGRESS,
    'status-line': LineNoiseKind.STATUS,
  });

  function legacyClsTokens(value) {
    const text = String(value || '').trim();
    if (!text) return [''];
    return text.split(/\s+/).filter(Boolean);
  }

  function legacyClsToKind(value) {
    const tokens = legacyClsTokens(value);
    for (const token of tokens) {
      if (Object.prototype.hasOwnProperty.call(LEGACY_KIND_BY_CLS, token)) return LEGACY_KIND_BY_CLS[token];
    }
    return LineKind.INFO;
  }

  function legacyClsToRole(value) {
    const tokens = legacyClsTokens(value);
    for (const token of tokens) {
      if (Object.prototype.hasOwnProperty.call(LEGACY_ROLE_BY_CLS, token)) return LEGACY_ROLE_BY_CLS[token];
    }
    return LineRole.BODY;
  }

  function collectUnknown(unknownCollector, family, value) {
    if (typeof unknownCollector === 'function') unknownCollector(family, String(value));
  }

  function enumValue(values, value, fallback, family, unknownCollector) {
    if (value === undefined || value === null || value === '') return fallback;
    const stringValue = String(value);
    if (values.includes(stringValue)) return stringValue;
    collectUnknown(unknownCollector, family, stringValue);
    return fallback;
  }

  function optionalInt(value) {
    if (value === undefined || value === null || typeof value === 'boolean') return null;
    const parsed = Number.parseInt(String(value), 10);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function entityFromWire(payload) {
    if (!payload || typeof payload !== 'object') return null;
    const type = String(payload.type || '').trim();
    const canonicalValue = String(payload.canonical_value || '').trim();
    if (!type || !canonicalValue) return null;
    let start = optionalInt(payload.start);
    let end = optionalInt(payload.end);
    if (start === null || end === null) {
      start = null;
      end = null;
    }
    return {
      type,
      value: String(payload.value || '').trim() || canonicalValue,
      canonical_value: canonicalValue,
      confidence: String(payload.confidence || '').trim() || 'medium',
      source_line: optionalInt(payload.source_line),
      start,
      end,
    };
  }

  function entityToWire(entity) {
    const payload = {
      type: entity.type,
      value: entity.value,
      canonical_value: entity.canonical_value,
      confidence: entity.confidence,
    };
    if (entity.source_line !== null && entity.source_line !== undefined) payload.source_line = entity.source_line;
    if (entity.start !== null && entity.start !== undefined) payload.start = entity.start;
    if (entity.end !== null && entity.end !== undefined) payload.end = entity.end;
    return payload;
  }

  function signalsFromWire(value, unknownCollector) {
    if (!Array.isArray(value)) return [];
    const signals = [];
    value.forEach((item) => {
      const signal = String(item);
      if (LINE_SIGNAL_VALUES.includes(signal)) {
        signals.push(signal);
      } else {
        collectUnknown(unknownCollector, 'signal', signal);
      }
    });
    return signals;
  }

  function entitiesFromWire(value) {
    if (!Array.isArray(value)) return [];
    return value.map(entityFromWire).filter(Boolean);
  }

  function legacyClsForEvent(event) {
    if (event.legacy_cls) return String(event.legacy_cls);
    const role = event.role || LineRole.BODY;
    if (role !== LineRole.BODY) return ROLE_LEGACY_CLS[role] || '';
    return KIND_LEGACY_CLS[event.kind || LineKind.INFO] || '';
  }

  function noiseKindForRole(role) {
    return NOISE_KIND_BY_ROLE[role] || null;
  }

  function noiseKindForEvent(event) {
    if (!event || (Array.isArray(event.signals) && event.signals.length)) return null;
    if (event.kind === LineKind.WARN || event.kind === LineKind.ERROR) return null;
    if (event.noise_kind) return event.noise_kind;
    return noiseKindForRole(event.role || LineRole.BODY);
  }

  function isNoiseLineEvent(event) {
    return noiseKindForEvent(event) !== null;
  }

  function legacyPayload(event) {
    const payload = {
      text: String(event.text || ''),
      cls: legacyClsForEvent(event),
      tsC: String(event.ts_clock || event.tsC || ''),
      tsE: String(event.ts_elapsed || event.tsE || ''),
    };
    if (Array.isArray(event.signals) && event.signals.length) payload.signals = event.signals.slice();
    if (event.line_index !== null && event.line_index !== undefined) payload.line_index = event.line_index;
    if (event.command_root) payload.command_root = String(event.command_root);
    if (event.target) payload.target = String(event.target);
    if (Array.isArray(event.entities) && event.entities.length) payload.entities = event.entities.map(entityToWire);
    const noiseKind = noiseKindForEvent(event);
    if (noiseKind) {
      payload.noise_kind = noiseKind;
      if (event.noise_reason) payload.noise_reason = String(event.noise_reason);
    }
    return payload;
  }

  function fromWireLineEvent(payload, unknownCollector) {
    const item = payload && typeof payload === 'object' ? payload : {};
    const clsValue = item.cls || '';
    const kind = enumValue(LINE_KIND_VALUES, item.kind, legacyClsToKind(clsValue), 'kind', unknownCollector);
    const role = enumValue(LINE_ROLE_VALUES, item.role, legacyClsToRole(clsValue), 'role', unknownCollector);
    const noiseKind = enumValue(
      LINE_NOISE_KIND_VALUES,
      item.noise_kind,
      noiseKindForRole(role),
      'noise_kind',
      unknownCollector,
    );
    return {
      text: String(item.text || ''),
      kind,
      role,
      legacy_cls: String(clsValue || ''),
      ts_clock: String(item.tsC || ''),
      ts_elapsed: String(item.tsE || ''),
      signals: signalsFromWire(item.signals, unknownCollector),
      line_index: optionalInt(item.line_index),
      command_root: String(item.command_root || ''),
      target: String(item.target || ''),
      entities: entitiesFromWire(item.entities),
      noise_kind: noiseKind,
      noise_reason: noiseKind ? String(item.noise_reason || '') : '',
    };
  }

  function toLegacyWireLineEvent(event) {
    return legacyPayload(event || {});
  }

  function toWireLineEvent(event) {
    const payload = legacyPayload(event || {});
    payload.v = LINE_EVENT_SCHEMA_VERSION;
    payload.kind = (event && event.kind) || LineKind.INFO;
    payload.role = (event && event.role) || LineRole.BODY;
    return payload;
  }

  function eventSearchText(event) {
    return String((event && event.text) || '');
  }

  const api = Object.freeze({
    LINE_EVENT_SCHEMA_VERSION,
    LINE_KIND_VALUES,
    LINE_NOISE_KIND_VALUES,
    LINE_ROLE_VALUES,
    LINE_SIGNAL_VALUES,
    LineKind,
    LineNoiseKind,
    LineRole,
    LineSignal,
    eventSearchText,
    fromWireLineEvent,
    isNoiseLineEvent,
    legacyClsToKind,
    legacyClsToRole,
    noiseKindForEvent,
    noiseKindForRole,
    toLegacyWireLineEvent,
    toWireLineEvent,
  });

  return api;
})(typeof window !== 'undefined' ? window : globalThis);

const {
  LINE_EVENT_SCHEMA_VERSION,
  LINE_KIND_VALUES,
  LINE_NOISE_KIND_VALUES,
  LINE_ROLE_VALUES,
  LINE_SIGNAL_VALUES,
  LineKind,
  LineNoiseKind,
  LineRole,
  LineSignal,
  eventSearchText,
  fromWireLineEvent,
  isNoiseLineEvent,
  legacyClsToKind,
  legacyClsToRole,
  noiseKindForEvent,
  noiseKindForRole,
  toLegacyWireLineEvent,
  toWireLineEvent,
} = DarklabRunOutputModel;

export {
  DarklabRunOutputModel,
  LINE_EVENT_SCHEMA_VERSION,
  LINE_KIND_VALUES,
  LINE_NOISE_KIND_VALUES,
  LINE_ROLE_VALUES,
  LINE_SIGNAL_VALUES,
  LineKind,
  LineNoiseKind,
  LineRole,
  LineSignal,
  eventSearchText,
  fromWireLineEvent,
  isNoiseLineEvent,
  legacyClsToKind,
  legacyClsToRole,
  noiseKindForEvent,
  noiseKindForRole,
  toLegacyWireLineEvent,
  toWireLineEvent,
};
