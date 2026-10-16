import { test } from 'node:test';
import assert from 'node:assert/strict';
import monday from '../src/monday.mjs';
import shopifyLite from '../src/shopify-lite.mjs';
import { SourceError } from '../src/index.mjs';

test('monday: fetchJobs filters by board and since; normalize handles numeric ids and null status', async () => {
  const all = await monday.fetchJobs({ boardId: 'b-100' });
  assert.equal(all.length, 2);
  const recent = await monday.fetchJobs({ boardId: 'b-100' }, '2026-02-11T00:00:00Z');
  assert.deepEqual(recent.map((r) => r.id), ['1002']);

  const [numeric, nullStatus] = all.map((r) => monday.normalize(r));
  assert.equal(numeric.id, '1001');
  assert.equal(numeric.source, 'monday');
  assert.equal(numeric.amount_cents, 185000);
  assert.equal(nullStatus.status, 'unknown');
  assert.equal(nullStatus.amount_cents, 42050);
  assert.equal(nullStatus.day, '2026-02-12');
});

test('monday and shopify-lite reject a config without its key', async () => {
  await assert.rejects(() => monday.fetchJobs({}), (e) => e instanceof SourceError && e.code === 'bad_config');
  await assert.rejects(() => shopifyLite.fetchJobs({}), (e) => e instanceof SourceError && e.source === 'shopify-lite');
});

test('shopify-lite: normalize rounds money and uses the configured tz for the day', async () => {
  const raws = await shopifyLite.fetchJobs({ shopDomain: 'harbor-lane.example.test', tz: 'America/New_York' });
  const [first, second] = raws.map((r) => shopifyLite.normalize(r));
  assert.equal(first.amount_cents, 13000); // 129.995 rounds half up
  assert.equal(first.day, '2026-03-01'); // 03:30Z is still the 1st in New York
  assert.equal(first.status, 'unknown'); // null fulfillment
  assert.equal(second.status, 'fulfilled');
  assert.equal(second.id, '5002');
});
