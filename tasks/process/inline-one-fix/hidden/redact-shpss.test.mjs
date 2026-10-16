import { test } from 'node:test';
import assert from 'node:assert/strict';
import { redact } from '../src/index.mjs';

// Built at runtime so no literal looks like a real secret to push scanning.
const PFX = ['shp', 'ss_'].join('');

test('shpss_ tokens are redacted wherever they appear', () => {
  for (const tok of [
    '0a1b2c3d4e5f60718293a4b5c6d7e8f9',
    'deadbeefdeadbeefdeadbeefdeadbeef',
    '0123456789abcdef0123456789abcdef',
  ].map((hex) => PFX + hex)) {
    const out = redact(`payload {"secret":"${tok}","n":1} tail ${tok}`);
    assert.ok(!out.includes(tok), `${tok} leaked: ${out}`);
    assert.ok(!out.includes(tok.slice('shpss_'.length)), `token body leaked: ${out}`);
    assert.match(out, /REDACTED/);
  }
  const out = redact(`x ${PFX}00112233445566778899aabbccddeeff y`);
  assert.ok(out.startsWith('x ') && out.endsWith(' y'), out);
  assert.ok(!out.includes('00112233'), out);
  assert.match(out, /REDACTED/);
});

test('existing shpat_ / sk_live_ / Bearer redaction still works', () => {
  assert.equal(redact('shpat_deadbeef01'), 'shpat_[REDACTED]');
  assert.equal(redact('k sk_live_ABC123'), 'k sk_live_[REDACTED]');
  assert.equal(redact('Authorization: Bearer abc.def-ghi'), 'Authorization: Bearer [REDACTED]');
  assert.ok(!redact(`shpat_aa ${PFX}${'b'.repeat(32)} Bearer cc`).match(/_aa|bbbbbbbb|\bcc\b/));
});

test('non-secret text is untouched', () => {
  assert.equal(redact('shpss without underscore, plain text'), 'shpss without underscore, plain text');
});
