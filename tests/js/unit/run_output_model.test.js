import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { fromDomScripts } from './helpers/extract.js'

const model = fromDomScripts(
  ['app/static/js/core/run_output_model.js'],
  { window: {} },
  'window.DarklabRunOutputModel',
);
const legacyClassRows = JSON.parse(readFileSync('tests/py/fixtures/run_output_legacy_cls.json', 'utf8'));

describe('run output model', () => {
  it('round trips v1 payloads losslessly', () => {
    const payload = {
      text: '443/tcp open https',
      cls: 'notice',
      tsC: '12:00:00',
      tsE: '+0.1s',
      signals: ['findings'],
      line_index: 7,
      command_root: 'nmap',
      target: 'darklab.sh',
      entities: [{
        type: 'domain',
        value: 'darklab.sh',
        canonical_value: 'darklab.sh',
        confidence: 'high',
        source_line: 7,
        start: 14,
        end: 24,
      }],
      v: 1,
      kind: 'notice',
      role: 'body',
    };

    expect(model.toWireLineEvent(model.fromWireLineEvent(payload))).toEqual(payload);
  });

  it('decodes legacy class strings into separate kind and role values', () => {
    const event = model.fromWireLineEvent({
      text: '$ nmap darklab.sh',
      cls: 'prompt-echo',
      tsC: '12:00:00',
      tsE: '+0.0s',
      line_index: 0,
    });

    expect(event.kind).toBe('info');
    expect(event.role).toBe('prompt-echo');
    expect(model.toWireLineEvent(event)).toEqual({
      text: '$ nmap darklab.sh',
      cls: 'prompt-echo',
      tsC: '12:00:00',
      tsE: '+0.0s',
      line_index: 0,
      v: 1,
      kind: 'info',
      role: 'prompt-echo',
    });
  });

  it('preserves unknown legacy class strings through compatibility writes', () => {
    const event = model.fromWireLineEvent({
      text: 'sample row',
      cls: 'builtin-help-row builtin-tour-sample',
      tsC: '',
      tsE: '',
    });

    expect(event.kind).toBe('info');
    expect(event.role).toBe('help-row');
    expect(model.toWireLineEvent(event)).toEqual({
      text: 'sample row',
      cls: 'builtin-help-row builtin-tour-sample',
      tsC: '',
      tsE: '',
      v: 1,
      kind: 'info',
      role: 'help-row',
    });
  });

  it('preserves legacy wire key order', () => {
    const legacy = model.toLegacyWireLineEvent({
      text: 'line',
      kind: 'notice',
      role: 'body',
      ts_clock: '12:00:00',
      ts_elapsed: '+0.1s',
      signals: ['findings'],
      line_index: 2,
      command_root: 'nmap',
      target: 'darklab.sh',
      entities: [{
        type: 'domain',
        value: 'darklab.sh',
        canonical_value: 'darklab.sh',
        confidence: 'high',
        source_line: 2,
        start: 0,
        end: 10,
      }],
    });

    expect(Object.keys(legacy)).toEqual([
      'text',
      'cls',
      'tsC',
      'tsE',
      'signals',
      'line_index',
      'command_root',
      'target',
      'entities',
    ]);
    expect(legacy.cls).toBe('notice');
  });

  it('reports unknown values and falls back safely', () => {
    const unknowns = [];
    const event = model.fromWireLineEvent(
      {
        text: 'line',
        cls: 'notice',
        tsC: '',
        tsE: '',
        kind: 'fatal',
        role: 'sparkle',
        signals: ['findings', 'future-signal'],
      },
      (family, value) => unknowns.push([family, value]),
    );

    expect(event.kind).toBe('notice');
    expect(event.role).toBe('body');
    expect(event.signals).toEqual(['findings']);
    expect(unknowns).toEqual([
      ['kind', 'fatal'],
      ['role', 'sparkle'],
      ['signal', 'future-signal'],
    ]);
  });

  it('keeps role cls compatibility when both axes are non-default', () => {
    const payload = model.toWireLineEvent({ text: 'prompt failed', kind: 'error', role: 'prompt-echo' });

    expect(payload.cls).toBe('prompt-echo');
    expect(payload.kind).toBe('error');
  });

  it('exports enum value lists for Python parity tests', () => {
    expect(model.LINE_KIND_VALUES).toEqual(['info', 'notice', 'warn', 'error']);
    expect(model.LINE_SIGNAL_VALUES).toEqual(['findings', 'warnings', 'errors', 'summaries']);
    expect(model.LINE_ROLE_VALUES).toContain('prompt-echo');
  });

  it('matches the shared legacy class fixture', () => {
    legacyClassRows.forEach(row => {
      const event = model.fromWireLineEvent({
        text: 'sample',
        cls: row.cls,
        tsC: '',
        tsE: '',
      });
      expect(event.kind).toBe(row.kind);
      expect(event.role).toBe(row.role);
    });
  });
});
