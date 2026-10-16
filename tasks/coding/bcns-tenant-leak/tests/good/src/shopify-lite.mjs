import { SourceError, minor, localDay } from './helpers.mjs';

// In-memory stand-in for a storefront orders API. No HTTP.
const FIXTURE = [
  { order_id: 5001, store: 'harbor-lane.example.test', client_id: 'harbor-lane', label: 'Whitening kit order', fulfillment_state: null, total_price: '129.995', placed_at: '2026-03-02T03:30:00Z' },
  { order_id: 5002, store: 'harbor-lane.example.test', client_id: 'harbor-lane', label: 'Electric brush order', fulfillment_state: 'fulfilled', total_price: '89.00', placed_at: '2026-03-03T17:10:00Z' },
];

/** @type {import('./index.mjs').Connector} */
export default {
  name: 'shopify-lite',
  configSchema: { required: ['shopDomain'], properties: { shopDomain: { type: 'string' }, tz: { type: 'string' } } },

  async fetchJobs(cfg, since) {
    if (!cfg?.shopDomain) throw new SourceError('shopify-lite', 'bad_config', 'shopify-lite: shopDomain is required');
    const cutoff = since ? new Date(since) : null;
    return FIXTURE
      .filter((r) => r.store === cfg.shopDomain && (!cutoff || new Date(r.placed_at) > cutoff))
      .map((r) => ({ ...r, tz: cfg.tz ?? 'UTC' }));
  },

  normalize(raw) {
    return {
      id: String(raw.order_id),
      client_id: raw.client_id,
      source: 'shopify-lite',
      title: raw.label,
      status: raw.fulfillment_state ?? 'unknown',
      amount_cents: minor(raw.total_price),
      day: localDay(raw.placed_at, raw.tz ?? 'UTC'),
      raw,
    };
  },
};
