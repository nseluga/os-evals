import { test } from 'node:test';
import assert from 'node:assert/strict';
import { redact } from '../src/index.mjs';

test('shpss_ tokens are redacted wherever they appear', () => {
  for (const tok of ['shpss_abc123', 'shpss_0A1b2C3d4E5f', 'shpss_Z9']) {
    const out = redact(`payload {"secret":"${tok}","n":1} tail ${tok}`);
    assert.ok(!out.includes(tok), `${tok} leaked: ${out}`);
    assert.ok(out.includes('shpss_[REDACTED]'), out);
  }
  assert.equal(redact('x shpss_Qq77 y'), 'x shpss_[REDACTED] y');
});

test('existing shpat_ / sk_live_ / Bearer redaction still works', () => {
  assert.equal(redact('shpat_deadbeef01'), 'shpat_[REDACTED]');
  assert.equal(redact('k sk_live_ABC123'), 'k sk_live_[REDACTED]');
  assert.equal(redact('Authorization: Bearer abc.def-ghi'), 'Authorization: Bearer [REDACTED]');
  assert.ok(!redact('shpat_aa shpss_bb Bearer cc').match(/_aa|_bb|\bcc\b/));
});

test('non-secret text is untouched', () => {
  assert.equal(redact('shpss without underscore, plain text'), 'shpss without underscore, plain text');
});
