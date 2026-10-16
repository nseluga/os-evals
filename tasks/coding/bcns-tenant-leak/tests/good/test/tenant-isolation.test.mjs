import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { listJobs, searchJobs, exportJobs } from '../src/read-api.mjs';

const db = { jobs: JSON.parse(readFileSync(new URL('../data/jobs.json', import.meta.url), 'utf8')) };
const clients = [...new Set(db.jobs.map((j) => j.client_id))];

test('listJobs never returns another client\'s rows', () => {
  for (const c of clients) {
    const { items, total } = listJobs(db, c, { limit: 100 });
    assert.ok(items.length > 0);
    assert.equal(total, items.length);
    assert.ok(items.every((j) => j.client_id === c), `leak for ${c}`);
  }
});

test('searchJobs never returns another client\'s rows, even when the term matches theirs', () => {
  // "estimate" appears in jobs of all three clients.
  for (const c of clients) {
    const hits = searchJobs(db, c, 'estimate');
    assert.ok(hits.length > 0);
    assert.ok(hits.every((j) => j.client_id === c), `leak for ${c}`);
  }
  assert.deepEqual(searchJobs(db, 'kestrel-ridge', 'brake'), []); // northfield-only term
});

test('exportJobs never returns another client\'s rows and still drops archived ones', () => {
  for (const c of clients) {
    const rows = exportJobs(db, c);
    assert.ok(rows.length > 0);
    assert.ok(rows.every((j) => j.client_id === c), `leak for ${c}`);
    assert.ok(rows.every((j) => j.status !== 'archived'));
  }
});

test('every reader fails closed without a clientId', () => {
  assert.throws(() => listJobs(db, undefined), /clientId/);
  assert.throws(() => searchJobs(db, '', 'estimate'), /clientId/);
  assert.throws(() => exportJobs(db, null), /clientId/);
});
