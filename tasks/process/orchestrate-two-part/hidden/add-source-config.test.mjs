// Hidden acceptance tests for item 2, written against the done-whens only.
// Runs the script in a scratch copy of the repo so data/sources.json is never touched.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, realpathSync, cpSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';

const root = new URL('..', import.meta.url).pathname;

function scratch() {
  // realpath: the script's main-guard compares import.meta.url (resolved) with argv[1]; a symlinked tmp dir makes it a silent no-op.
  const d = realpathSync(mkdtempSync(join(tmpdir(), 'bcns-hidden-')));
  for (const p of ['src', 'scripts', 'data', 'package.json']) cpSync(join(root, p), join(d, p), { recursive: true });
  const file = join(d, 'data', 'sources.json');
  const before = readFileSync(file, 'utf8');
  const run = (...args) => spawnSync(process.execPath, [join(d, 'scripts', 'add-source.mjs'), ...args], { encoding: 'utf8' });
  return { file, before, run };
}

function rejected(args) {
  const s = scratch();
  const r = s.run(...args);
  assert.equal(r.status, 1, `expected exit 1 for ${JSON.stringify(args)}, got ${r.status}; stderr=${r.stderr}`);
  assert.ok((r.stderr + r.stdout).trim().length > 0, 'a message is printed');
  assert.equal(readFileSync(s.file, 'utf8'), s.before, 'nothing written');
  return r;
}

test('missing required key is rejected with exit 1 and a message', () => {
  const r = rejected(['northfield', 'monday', '{}']);
  assert.match(r.stderr + r.stdout, /boardId/);
  rejected(['northfield', 'monday', '{"pageSize":5}']);
  rejected(['northfield', 'shopify-lite', '{"tz":"UTC"}']);
});

test('wrong primitive type is rejected with exit 1 and a message', () => {
  const r = rejected(['northfield', 'monday', '{"boardId":7}']);
  assert.match(r.stderr + r.stdout, /boardId/);
  rejected(['northfield', 'monday', '{"boardId":"b-1","pageSize":"5"}']);
  rejected(['northfield', 'shopify-lite', '{"shopDomain":true}']);
  rejected(['northfield', 'shopify-lite', '{"shopDomain":"x.example.test","tz":9}']);
});

test('unknown source is rejected with exit 1 and nothing written', () => {
  rejected(['northfield', 'nope', '{"boardId":"b-1"}']);
});

test('a config that satisfies the schema is still registered', () => {
  const s = scratch();
  const r = s.run('northfield', 'monday', '{"boardId":"b-200"}');
  assert.equal(r.status, 0, r.stderr);
  const saved = JSON.parse(readFileSync(s.file, 'utf8'));
  assert.deepEqual(saved.at(-1), { client_id: 'northfield', source: 'monday', config: { boardId: 'b-200' } });
  const r2 = s.run('northfield', 'shopify-lite', '{"shopDomain":"n.example.test","tz":"UTC"}');
  assert.equal(r2.status, 0, r2.stderr);
  assert.equal(JSON.parse(readFileSync(s.file, 'utf8')).length, saved.length + 1);
});
