import { test } from 'node:test';
import assert from 'node:assert/strict';
import { redact } from '../src/index.mjs';

test('shpss_ tokens are redacted wherever they appear', () => {
  for (const tok of ['shpss_0a1b2c3d4e5f', 'shpss_deadbeef01', 'shpss_9f8e7d']) {
    const out = redact(`payload {"secret":"${tok}","n":1} tail ${tok}`);
    assert.ok(!out.includes(tok), `${tok} leaked: ${out}`);
    assert.ok(!out.includes(tok.slice('shpss_'.length)), `token body leaked: ${out}`);
    assert.match(out, /REDACTED/);
  }
  const out = redact('x shpss_0a1b2c y');
  assert.ok(out.startsWith('x ') && out.endsWith(' y'), out);
  assert.ok(!out.includes('0a1b2c'), out);
  assert.match(out, /REDACTED/);
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
