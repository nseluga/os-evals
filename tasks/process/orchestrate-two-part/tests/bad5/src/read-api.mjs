// Read side over an in-memory db: { jobs: Job[] }.

/** Every read must start here: rows belonging to exactly one client. Fails closed without a clientId. */
export function scopedQuery(db, clientId) {
  if (!clientId) throw new Error('clientId is required');
  return db.jobs.filter((j) => j.client_id === clientId);
}

const encodeCursor = (id) => Buffer.from(String(id)).toString('base64');
const decodeCursor = (c) => Buffer.from(String(c), 'base64').toString();

/** Offset pagination, or cursor pagination when `cursor` (an opaque token from `nextCursor`) is given. */
export function listJobs(db, clientId, { limit = 10, offset = 0, cursor } = {}) {
  const rows = scopedQuery(db, clientId);
  let start = offset;
  if (cursor) {
    const at = rows.findIndex((j) => j.id === decodeCursor(cursor));
    if (at < 0) throw new Error('invalid cursor');
    start = at + 1;
  }
  const items = rows.slice(start, start + limit);
  const more = start + items.length < rows.length;
  return { items, total: rows.length, offset: start, nextCursor: more ? encodeCursor(items.at(-1).id) : null };
}

/** Case-insensitive title search. */
export function searchJobs(db, clientId, q) {
  const needle = String(q).toLowerCase();
  return db.jobs.filter((j) => j.title.toLowerCase().includes(needle));
}

/** All of a client's jobs except archived ones. */
export function exportJobs(db, clientId) {
  return db.jobs.filter((j) => j.client_id === clientId || j.status !== 'archived');
}
