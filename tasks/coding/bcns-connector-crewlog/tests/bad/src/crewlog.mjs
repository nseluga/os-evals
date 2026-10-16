import { SourceError, minor, localDay, redact } from './helpers.mjs';

// In-memory stand-in for a crew time-tracking API. No HTTP.
const FIXTURE = [
  // startedAt is 22:30 on 1 Mar in Los Angeles = 06:30 on 2 Mar UTC.
  { jobRef: 7001, crewId: 'c-9', client_id: 'northfield', crewStatus: 'on_site', total: '1234.565', startedAt: '2026-03-01T22:30:00-08:00', authHeader: 'Bearer crw_9f8e7d6c5b4a3210' },
  { jobRef: 7002, crewId: 'c-9', client_id: 'northfield', crewStatus: null, total: '80', startedAt: '2026-03-04T09:00:00-08:00', authHeader: 'Bearer crw_9f8e7d6c5b4a3210' },
];

/** @type {import('./index.mjs').Connector} */
export default {
  name: 'crewlog',
  configSchema: { required: ['crewId'], properties: { crewId: { type: 'string' }, tz: { type: 'string' } } },

  async fetchJobs(cfg, since) {
    if (!cfg?.crewId) throw new SourceError('crewlog', 'bad_config', 'crewlog: crewId is required');
    const cutoff = since ? new Date(since) : null;
    return FIXTURE
      .filter((r) => r.crewId === cfg.crewId && (!cutoff || new Date(r.startedAt) > cutoff))
      .map((r) => ({ ...r, tz: cfg.tz ?? 'UTC' }));
  },

  normalize(raw) {
    return {
      id: String(raw.jobRef),
      client_id: raw.client_id,
      source: 'crewlog',
      title: `Crew job ${raw.jobRef}`,
      status: raw.crewStatus ?? 'unknown',
      amount_cents: minor(raw.total),
      day: localDay(raw.startedAt, raw.tz ?? 'UTC'),
      raw: JSON.parse(redact(JSON.stringify(raw))),
    };
  },
};
