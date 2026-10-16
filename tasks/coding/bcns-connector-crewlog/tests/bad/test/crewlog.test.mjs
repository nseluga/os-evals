import { test } from 'node:test';
import assert from 'node:assert/strict';
import crewlog from '../src/crewlog.mjs';
import { SOURCES, SourceError } from '../src/index.mjs';

const cfg = { crewId: 'c-9', tz: 'America/Los_Angeles' };

test('crewlog is registered', () => {
  assert.equal(SOURCES.crewlog, crewlog);
});

test('crewlog normalizes numeric ref, null status, rounded total and local day', async () => {
  const [a, b] = (await crewlog.fetchJobs(cfg)).map((r) => crewlog.normalize(r));
  assert.equal(a.id, '7001');
  assert.equal(a.source, 'crewlog');
  assert.equal(a.status, 'on_site');
  assert.equal(a.amount_cents, 123457); // 1234.565 rounds half up
  assert.equal(a.day, '2026-03-01'); // 06:30Z on the 2nd is still the 1st in Los Angeles
  assert.equal(b.status, 'unknown');
  assert.equal(b.amount_cents, 8000);
});

test('crewlog redacts the bearer token in raw', async () => {
  const [row] = await crewlog.fetchJobs(cfg);
  const job = crewlog.normalize(row);
  assert.match(job.raw.authHeader, /Bearer \[REDACTED\]/);
  assert.ok(!JSON.stringify(job).includes('crw_9f8e'));
  assert.equal(job.raw.jobRef, 7001); // other raw fields are kept
});

test('crewlog fetchJobs honours since and requires crewId', async () => {
  const recent = await crewlog.fetchJobs(cfg, '2026-03-03T00:00:00Z');
  assert.deepEqual(recent.map((r) => r.jobRef), [7002]);
  await assert.rejects(() => crewlog.fetchJobs({}), (e) => e instanceof SourceError && e.source === 'crewlog');
});
