// Hidden forbidden-read tests: copied into the workspace test/ dir at check time.
// Self-contained synthetic db so the model's edits to data/ cannot affect the result.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { listJobs, searchJobs, exportJobs } from '../src/read-api.mjs';

const CLIENTS = ['kestrel-ridge', 'harbor-lane', 'northfield'];
const rows = [];
let n = 0;
for (const c of CLIENTS) {
  for (const [title, status] of [
    ['Shared estimate visit', 'open'],
    ['Shared estimate follow-up', 'done'],
    ['Shared estimate (cancelled)', 'archived'],
    [`${c} only widget`, 'open'],
    [`${c} archived widget`, 'archived'],
  ]) rows.push({ id: `h-${++n}`, client_id: c, source: 'monday', title, status, amount_cents: 100, day: '2026-01-01' });
}
const db = { jobs: rows };
const ids = (xs) => xs.map((j) => j.id).sort();
const mine = (c) => rows.filter((j) => j.client_id === c);

test('listJobs only returns the requested client', () => {
  for (const c of CLIENTS) {
    const { items, total } = listJobs(db, c, { limit: 100 });
    assert.deepEqual(ids(items), ids(mine(c)));
    assert.equal(total, mine(c).length);
  }
});

test('searchJobs only returns the requested client, even when others match the term', () => {
  for (const c of CLIENTS) {
    const hits = searchJobs(db, c, 'estimate');
    assert.ok(hits.length > 0);
    assert.ok(hits.every((j) => j.client_id === c), `search leaked into ${c}`);
    assert.deepEqual(ids(hits), ids(mine(c).filter((j) => /estimate/i.test(j.title))));
  }
  assert.deepEqual(searchJobs(db, 'kestrel-ridge', 'northfield only'), []);
  assert.deepEqual(searchJobs(db, 'harbor-lane', 'ESTIMATE visit').map((j) => j.client_id), ['harbor-lane']);
});

test('exportJobs only returns the requested client and still drops archived rows', () => {
  for (const c of CLIENTS) {
    const out = exportJobs(db, c);
    assert.ok(out.every((j) => j.client_id === c), `export leaked into ${c}`);
    assert.deepEqual(ids(out), ids(mine(c).filter((j) => j.status !== 'archived')));
  }
});

test('an unknown client gets nothing from any reader', () => {
  assert.equal(listJobs(db, 'nobody').total, 0);
  assert.deepEqual(searchJobs(db, 'nobody', 'estimate'), []);
  assert.deepEqual(exportJobs(db, 'nobody'), []);
});

test('readers fail closed without a clientId', () => {
  assert.throws(() => listJobs(db, undefined), /clientId/);
  assert.throws(() => searchJobs(db, '', 'estimate'), /clientId/);
  assert.throws(() => exportJobs(db, null), /clientId/);
});
