import monday from './monday.mjs';
import shopifyLite from './shopify-lite.mjs';

export { SourceError, minor, localDay, redact } from './helpers.mjs';

/**
 * @typedef {Object} Job
 * @property {string} id
 * @property {string} client_id
 * @property {string} source
 * @property {string} title
 * @property {string} status
 * @property {number} amount_cents
 * @property {string} day        YYYY-MM-DD
 * @property {object} raw
 */

/**
 * @typedef {Object} Connector
 * @property {string} name                                   registry key, e.g. "monday"
 * @property {{required: string[], properties: Object<string, {type: string}>}} configSchema
 * @property {(cfg: object, since?: string|Date) => Promise<object[]>} fetchJobs   raw rows updated after `since`
 * @property {(raw: object) => Job} normalize
 */

/** @type {Record<string, Connector>} */
export const SOURCES = {
  [monday.name]: monday,
  [shopifyLite.name]: shopifyLite,
};
