import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { listJobs, searchJobs, exportJobs, scopedQuery } from '../src/read-api.mjs';

const db = { jobs: JSON.parse(readFileSync(new URL('../data/jobs.json', import.meta.url), 'utf8')) };

test('listJobs pages through one client with offset/limit', () => {
  const page1 = listJobs(db, 'kestrel-ridge', { limit: 2 });
  assert.equal(page1.total, 4);
  assert.equal(page1.items.length, 2);
  assert.ok(page1.items.every((j) => j.client_id === 'kestrel-ridge'));
  const page2 = listJobs(db, 'kestrel-ridge', { limit: 2, offset: 2 });
  assert.deepEqual([...page1.items, ...page2.items].map((j) => j.id), scopedQuery(db, 'kestrel-ridge').map((j) => j.id));
  assert.throws(() => listJobs(db, ''), /clientId/);
});

test('searchJobs finds the client\'s own matching jobs', () => {
  const hits = searchJobs(db, 'northfield', 'TIRE');
  assert.ok(hits.some((j) => j.id === 'j-010'));
});

test('exportJobs includes the client\'s open and done jobs', () => {
  const ids = exportJobs(db, 'harbor-lane').map((j) => j.id);
  for (const id of ['j-003', 'j-006', 'j-011']) assert.ok(ids.includes(id));
});
