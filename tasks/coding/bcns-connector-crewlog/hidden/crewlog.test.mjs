// Hidden acceptance test. Reaches the connector only through the SOURCES registry,
// so the model's file name for the connector is free.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { SOURCES } from '../src/index.mjs';

const row = (over = {}) => ({
  jobRef: 7001,
  crewId: 'c-9',
  client_id: 'northfield',
  crewStatus: 'on_site',
  total: '1234.565',
  startedAt: '2026-03-01T22:30:00-08:00',
  tz: 'America/Los_Angeles',
  authHeader: 'Bearer crw_9f8e7d6c5b4a3210',
  ...over,
});

const norm = (over) => SOURCES.crewlog.normalize(row(over));

test('crewlog is registered in SOURCES with the connector interface', () => {
  const c = SOURCES.crewlog;
  assert.ok(c, 'SOURCES.crewlog missing');
  assert.equal(c.name, 'crewlog');
  assert.equal(typeof c.fetchJobs, 'function');
  assert.equal(typeof c.normalize, 'function');
  assert.ok(c.configSchema && Array.isArray(c.configSchema.required));
});

test('normalized record has the Job contract shape', () => {
  const j = norm();
  for (const k of ['id', 'client_id', 'source', 'title', 'status', 'day']) {
    assert.equal(typeof j[k], 'string', `${k} must be a string`);
  }
  assert.ok(j.title.length > 0);
  assert.equal(j.source, 'crewlog');
  assert.equal(j.client_id, 'northfield');
  assert.equal(j.status, 'on_site');
  assert.ok(Number.isInteger(j.amount_cents));
  assert.match(j.day, /^\d{4}-\d{2}-\d{2}$/);
  assert.ok(j.raw && typeof j.raw === 'object');
});

test('numeric jobRef becomes a string id', () => {
  assert.strictEqual(norm({ jobRef: 7001 }).id, '7001');
});

test('decimal string total rounds half up to integer cents', () => {
  assert.strictEqual(norm({ total: '1234.565' }).amount_cents, 123457);
  assert.strictEqual(norm({ total: '80' }).amount_cents, 8000);
  assert.strictEqual(norm({ total: '420.5' }).amount_cents, 42050);
  assert.strictEqual(norm({ total: '1.005' }).amount_cents, 101); // float math gives 100
  assert.strictEqual(norm({ total: '0.004' }).amount_cents, 0);
});

test('null status falls back to "unknown" like the other connectors', () => {
  assert.strictEqual(norm({ crewStatus: null }).status, 'unknown');
});

test('day is the calendar day in the row timezone, not UTC', () => {
  // 22:30 on 1 Mar in Los Angeles is 06:30 on 2 Mar UTC.
  assert.strictEqual(norm().day, '2026-03-01');
  // 01:30 on 2 Mar in Tokyo is 16:30 on 1 Mar UTC.
  assert.strictEqual(
    norm({ startedAt: '2026-03-02T01:30:00+09:00', tz: 'Asia/Tokyo' }).day,
    '2026-03-02',
  );
  // Same instant as the first case, viewed from Tokyo, is the 2nd.
  assert.strictEqual(norm({ tz: 'Asia/Tokyo' }).day, '2026-03-02');
});

test('Bearer token is redacted everywhere in the record', () => {
  const j = norm();
  const s = JSON.stringify(j);
  assert.ok(!s.includes('crw_9f8e7d6c5b4a3210'), 'bearer token leaked');
  assert.ok(!s.includes('9f8e7d6c'), 'bearer token fragment leaked');
  // raw keeps the other original fields
  assert.equal(j.raw.jobRef, 7001);
  assert.equal(j.raw.crewId, 'c-9');
});

test('normalize does not mutate the input row', () => {
  const r = row();
  const before = JSON.stringify(r);
  SOURCES.crewlog.normalize(r);
  assert.equal(JSON.stringify(r), before);
});
