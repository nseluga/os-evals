import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, copyFileSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { addSource, validateConfig } from '../scripts/add-source.mjs';
import { SOURCES } from '../src/index.mjs';

function tmpSources() {
  const f = join(mkdtempSync(join(tmpdir(), 'bcns-mini-')), 'sources.json');
  copyFileSync(new URL('../data/sources.json', import.meta.url), f);
  return f;
}
const count = (f) => JSON.parse(readFileSync(f, 'utf8')).length;

test('validateConfig checks required keys and types from the connector configSchema', () => {
  const schema = SOURCES.monday.configSchema;
  assert.deepEqual(validateConfig(schema, { boardId: 'b-1', pageSize: 5 }), []);
  assert.match(validateConfig(schema, {})[0], /missing required key "boardId"/);
  assert.match(validateConfig(schema, { boardId: 7 })[0], /"boardId" must be a string/);
  assert.match(validateConfig(schema, { boardId: 'b-1', pageSize: '5' })[0], /"pageSize" must be a number/);
  assert.match(validateConfig(schema, [])[0], /JSON object/);
});

test('addSource refuses an invalid config and writes nothing', () => {
  const f = tmpSources();
  assert.throws(() => addSource(f, 'northfield', 'monday', '{}'), /invalid config for monday/);
  assert.throws(() => addSource(f, 'harbor-lane', 'shopify-lite', '{"shopDomain":42}'), /must be a string/);
  assert.equal(count(f), 2);
});

test('addSource accepts a config that satisfies the schema', () => {
  const f = tmpSources();
  addSource(f, 'northfield', 'shopify-lite', '{"shopDomain":"northfield.example.test","tz":"America/Chicago"}');
  assert.equal(count(f), 3);
});
