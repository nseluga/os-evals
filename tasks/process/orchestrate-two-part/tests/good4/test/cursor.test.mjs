import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { listJobs, scopedQuery } from '../src/read-api.mjs';

const db = { jobs: JSON.parse(readFileSync(new URL('../data/jobs.json', import.meta.url), 'utf8')) };

test('listJobs returns an opaque base64 nextCursor of the last id', () => {
  const page = listJobs(db, 'kestrel-ridge', { limit: 2 });
  assert.equal(Buffer.from(page.nextCursor, 'base64').toString(), page.items.at(-1).id);
  assert.notEqual(page.nextCursor, page.items.at(-1).id);
});

test('following nextCursor walks the whole client set once, then nextCursor is null', () => {
  const seen = [];
  let cursor;
  let pages = 0;
  do {
    const page = listJobs(db, 'kestrel-ridge', { limit: 3, cursor });
    seen.push(...page.items.map((j) => j.id));
    cursor = page.nextCursor;
    pages += 1;
  } while (cursor);
  assert.equal(pages, 2);
  assert.deepEqual(seen, scopedQuery(db, 'kestrel-ridge').map((j) => j.id));
  assert.equal(listJobs(db, 'northfield', { limit: 100 }).nextCursor, null);
});

test('a cursor from another client or garbage is rejected; offset paging still works', () => {
  const other = listJobs(db, 'harbor-lane', { limit: 1 }).nextCursor;
  assert.throws(() => listJobs(db, 'kestrel-ridge', { cursor: other }), /invalid cursor/);
  assert.throws(() => listJobs(db, 'kestrel-ridge', { cursor: '%%%' }), /invalid cursor/);
  assert.equal(listJobs(db, 'kestrel-ridge', { limit: 2, offset: 2 }).items.length, 2);
});
