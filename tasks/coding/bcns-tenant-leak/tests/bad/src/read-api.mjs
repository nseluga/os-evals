// Read side over an in-memory db: { jobs: Job[] }.

/** Every read must start here: rows belonging to exactly one client. Fails closed without a clientId. */
export function scopedQuery(db, clientId) {
  if (!clientId) throw new Error('clientId is required');
  return db.jobs.filter((j) => j.client_id === clientId);
}

/** Offset pagination. */
export function listJobs(db, clientId, { limit = 10, offset = 0 } = {}) {
  const rows = scopedQuery(db, clientId);
  return { items: rows.slice(offset, offset + limit), total: rows.length, offset };
}

/** Case-insensitive title search. */
export function searchJobs(db, clientId, q) {
  const needle = String(q).toLowerCase();
  return db.jobs.filter((j) => j.title.toLowerCase().includes(needle));
}

/** All of a client's jobs except archived ones. */
export function exportJobs(db, clientId) {
  return db.jobs.filter((j) => j.client_id === clientId && j.status !== 'archived');
}
