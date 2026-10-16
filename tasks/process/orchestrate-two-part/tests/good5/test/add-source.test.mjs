import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, copyFileSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { addSource, ALLOWED_SOURCES } from '../scripts/add-source.mjs';
import { SOURCES } from '../src/index.mjs';
import contract from '../api/contract.json' with { type: 'json' };

function tmpSources() {
  const f = join(mkdtempSync(join(tmpdir(), 'bcns-mini-')), 'sources.json');
  copyFileSync(new URL('../data/sources.json', import.meta.url), f);
  return f;
}

test('addSource appends a valid registration and rejects unknown sources', () => {
  const f = tmpSources();
  addSource(f, 'northfield', 'monday', '{"boardId":"b-200"}');
  const saved = JSON.parse(readFileSync(f, 'utf8'));
  assert.equal(saved.length, 3);
  assert.deepEqual(saved.at(-1), { client_id: 'northfield', source: 'monday', config: { boardId: 'b-200' } });
  assert.throws(() => addSource(f, 'northfield', 'nope', '{}'), /unknown source/);
  assert.equal(JSON.parse(readFileSync(f, 'utf8')).length, 3);
});

test('the three source lists agree: SOURCES, ALLOWED_SOURCES, api/contract.json', () => {
  const fromContract = contract.definitions.Job.properties.source.enum;
  assert.deepEqual([...ALLOWED_SOURCES].sort(), Object.keys(SOURCES).sort());
  assert.deepEqual([...fromContract].sort(), Object.keys(SOURCES).sort());
});
