import { test } from 'node:test';
import assert from 'node:assert/strict';
import { minor, localDay, redact, SourceError } from '../src/index.mjs';

test('minor converts decimal strings to cents, rounding half up', () => {
  assert.equal(minor('12.34'), 1234);
  assert.equal(minor('0.1'), 10);
  assert.equal(minor('1.005'), 101);
  assert.equal(minor('129.994'), 12999);
  assert.equal(minor('-2.50'), -250);
  assert.equal(minor(7), 700);
});

test('minor rejects non-decimal input', () => {
  for (const bad of ['abc', '', NaN, undefined, '1,000.00']) assert.throws(() => minor(bad), TypeError);
});

test('localDay returns the calendar day in the given tz', () => {
  assert.equal(localDay('2026-03-02T03:30:00Z', 'UTC'), '2026-03-02');
  assert.equal(localDay('2026-03-02T03:30:00Z', 'America/New_York'), '2026-03-01');
  assert.equal(localDay('2026-03-01T22:30:00-08:00', 'Pacific/Auckland'), '2026-03-02');
});

test('redact masks bearer tokens, sk_live_ and shpat_ secrets', () => {
  assert.equal(redact('Authorization: Bearer abc.DEF-123'), 'Authorization: Bearer [REDACTED]');
  assert.equal(redact('key sk_live_AbC123xyz here'), 'key sk_live_[REDACTED] here');
  assert.equal(redact('tok shpat_0123abcd'), 'tok shpat_[REDACTED]');
  assert.equal(redact('nothing secret'), 'nothing secret');
});

test('SourceError carries source and code', () => {
  const e = new SourceError('monday', 'bad_config', 'nope');
  assert.ok(e instanceof Error);
  assert.equal(e.source, 'monday');
  assert.equal(e.code, 'bad_config');
  assert.equal(e.message, 'nope');
});
