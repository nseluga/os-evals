import { test } from 'node:test';
import assert from 'node:assert/strict';
import { redact } from '../src/index.mjs';

test('redact masks shpss_ shared-secret tokens', () => {
  assert.equal(redact('secret shpss_0a1B2c3D4e'), 'secret shpss_[REDACTED]');
  assert.ok(!redact('{"k":"shpss_abc123"} and shpat_def456').includes('abc123'));
});
