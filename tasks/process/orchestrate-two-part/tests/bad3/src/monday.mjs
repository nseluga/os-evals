import { SourceError, minor, localDay } from './helpers.mjs';

// In-memory stand-in for a board API. No HTTP.
const FIXTURE = [
  { id: 1001, boardId: 'b-100', client_id: 'kestrel-ridge', name: 'Spring mulch install', state: 'Working on it', amount: '1850.00', updated_at: '2026-02-10T15:00:00Z' },
  { id: '1002', boardId: 'b-100', client_id: 'kestrel-ridge', name: 'Irrigation estimate', state: null, amount: '420.5', updated_at: '2026-02-12T09:30:00Z' },
  { id: 2001, boardId: 'b-200', client_id: 'northfield', name: 'Brake service estimate', state: 'Done', amount: null, updated_at: '2026-02-11T18:00:00Z' },
];

/** @type {import('./index.mjs').Connector} */
export default {
  name: 'monday',
  configSchema: { required: ['boardId'], properties: { boardId: { type: 'string' }, pageSize: { type: 'number' } } },

  async fetchJobs(cfg, since) {
    if (!cfg?.boardId) throw new SourceError('monday', 'bad_config', 'monday: boardId is required');
    const cutoff = since ? new Date(since) : null;
    return FIXTURE.filter((r) => r.boardId === cfg.boardId && (!cutoff || new Date(r.updated_at) > cutoff));
  },

  normalize(raw) {
    return {
      id: String(raw.id),
      client_id: raw.client_id,
      source: 'monday',
      title: raw.name,
      status: raw.state ?? 'unknown',
      amount_cents: raw.amount == null ? 0 : minor(raw.amount),
      day: localDay(raw.updated_at, 'UTC'),
      raw,
    };
  },
};
