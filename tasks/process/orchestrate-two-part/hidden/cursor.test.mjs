// Hidden acceptance tests for item 1, written against the done-whens only.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { listJobs } from '../src/read-api.mjs';

const db = { jobs: JSON.parse(readFileSync(new URL('../data/jobs.json', import.meta.url), 'utf8')) };
const all = (c) => db.jobs.filter((j) => j.client_id === c).map((j) => j.id);

function walk(client, limit) {
  const seen = [];
  const nexts = [];
  let cursor;
  for (let i = 0; i < 50; i++) {
    const page = listJobs(db, client, cursor === undefined ? { limit } : { limit, cursor });
    assert.ok(Array.isArray(page.items), 'items is an array');
    assert.ok('nextCursor' in page, 'result has nextCursor');
    assert.ok(page.items.length <= limit);
    seen.push(...page.items.map((j) => j.id));
    nexts.push(page.nextCursor);
    if (page.nextCursor === null) return { seen, nexts };
    assert.equal(typeof page.nextCursor, 'string');
    cursor = page.nextCursor;
  }
  assert.fail('cursor chain did not terminate');
}

test('following nextCursor visits every job once, in order, for several page sizes', () => {
  for (const client of ['kestrel-ridge', 'harbor-lane', 'northfield']) {
    for (const limit of [1, 2, 3]) {
      const { seen } = walk(client, limit);
      assert.deepEqual(seen, all(client), `${client} limit ${limit}`);
    }
  }
});

test('nextCursor is null on the last page and non-null before it', () => {
  const { nexts } = walk('kestrel-ridge', 3);
  assert.equal(nexts.length, 2);
  assert.notEqual(nexts[0], null);
  assert.equal(nexts.at(-1), null);
  const n = all('kestrel-ridge').length;
  assert.equal(listJobs(db, 'kestrel-ridge', { limit: n }).nextCursor, null);
  assert.equal(listJobs(db, 'kestrel-ridge', { limit: n + 10 }).nextCursor, null);
  assert.notEqual(listJobs(db, 'kestrel-ridge', { limit: n - 1 }).nextCursor, null);
});

test('cursor pages stay inside the requested client', () => {
  const { seen } = walk('harbor-lane', 1);
  assert.ok(seen.every((id) => all('harbor-lane').includes(id)));
});

test('offset callers keep working', () => {
  const ids = all('kestrel-ridge');
  const p1 = listJobs(db, 'kestrel-ridge', { limit: 2 });
  const p2 = listJobs(db, 'kestrel-ridge', { limit: 2, offset: 2 });
  assert.deepEqual(p1.items.map((j) => j.id), ids.slice(0, 2));
  assert.deepEqual(p2.items.map((j) => j.id), ids.slice(2, 4));
  assert.equal(p1.total, ids.length);
  assert.equal(listJobs(db, 'kestrel-ridge').items.length, Math.min(10, ids.length));
  assert.throws(() => listJobs(db, ''), /clientId/);
});
