#!/usr/bin/env node
// Usage: node scripts/add-source.mjs <client_id> <source> <configJson>
import { readFileSync, writeFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { SOURCES } from '../src/index.mjs';

export const ALLOWED_SOURCES = ['monday', 'shopify-lite'];

const DEFAULT_FILE = new URL('../data/sources.json', import.meta.url);

/** Check `cfg` against a connector configSchema (required keys + primitive types). Returns a list of problems. */
export function validateConfig(schema, cfg) {
  if (cfg === null || typeof cfg !== 'object' || Array.isArray(cfg)) return ['config must be a JSON object'];
  const problems = schema.required.filter((k) => !(k in cfg)).map((k) => `missing required key "${k}"`);
  for (const [k, { type }] of Object.entries(schema.properties)) {
    if (k in cfg && typeof cfg[k] !== type) problems.push(`"${k}" must be a ${type}`);
  }
  return problems;
}

/** Append a source registration to `file`. Throws on an unknown source or unparseable config. */
export function addSource(file, clientId, source, configJson) {
  if (!clientId) throw new Error('client_id is required');
  if (!ALLOWED_SOURCES.includes(source)) {
    throw new Error(`unknown source "${source}" (allowed: ${ALLOWED_SOURCES.join(', ')})`);
  }
  let config;
  try {
    config = JSON.parse(configJson);
  } catch {
    throw new Error('configJson is not valid JSON');
  }
  const problems = validateConfig(SOURCES[source].configSchema, config);
  if (problems.length) throw new Error(`invalid config for ${source}: ${problems.join('; ')}`);
  const entries = JSON.parse(readFileSync(file, 'utf8'));
  const entry = { client_id: clientId, source, config };
  entries.push(entry);
  writeFileSync(file, JSON.stringify(entries, null, 2) + '\n');
  return entry;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const [clientId, source, configJson] = process.argv.slice(2);
  try {
    console.log(JSON.stringify(addSource(DEFAULT_FILE, clientId, source, configJson ?? '{}')));
  } catch (err) {
    console.error(`add-source: ${err.message}`);
    process.exit(1);
  }
}
