/**
 * Tests for Item 3.2 — Quick-capture inbox UI.
 *
 * Gate mode: tests+behavioral
 *
 * Covers:
 *   1. POST /api/inbox persists item; it appears in the page HTML on next render
 *   2. DELETE /api/inbox removes item; it is absent from the page HTML on next render
 *   3. Empty state renders "No items." when inbox is empty
 *   4. Page renders without errors when inbox is empty
 *
 * Strategy:
 *   - API layer: import real route handlers; let them hit data/manual.json for real.
 *     Snapshot/restore manual.json around every test so the file is always left clean.
 *   - HTML rendering: call GET http://localhost:4399/ and inspect the response body.
 *     The dev server must be running before these tests execute (started by the QA
 *     runner via `npm run dev -- --port 4399`).
 */

import { describe, it, expect, beforeEach, afterEach, beforeAll } from 'vitest';
import { readFileSync, writeFileSync } from 'fs';
import { join } from 'path';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MANUAL_PATH = join(process.cwd(), 'data', 'manual.json');
const DEV_SERVER = 'http://localhost:4399';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function readManualFile() {
  return JSON.parse(readFileSync(MANUAL_PATH, 'utf-8'));
}

/** Fetch the dashboard HTML from the running dev server. */
async function fetchDashboardHTML(): Promise<string> {
  const res = await fetch(`${DEV_SERVER}/`);
  if (!res.ok) throw new Error(`Dashboard returned ${res.status}`);
  return res.text();
}

/** Helper to call POST /api/inbox on the dev server. */
async function serverPost(body: Record<string, unknown>) {
  return fetch(`${DEV_SERVER}/api/inbox`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

/** Helper to call DELETE /api/inbox on the dev server. */
async function serverDelete(body: Record<string, unknown>) {
  return fetch(`${DEV_SERVER}/api/inbox`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// Snapshot / restore manual.json around every test
// ---------------------------------------------------------------------------

let snapshot: string;

beforeEach(() => {
  snapshot = readFileSync(MANUAL_PATH, 'utf-8');
});

afterEach(() => {
  writeFileSync(MANUAL_PATH, snapshot, 'utf-8');
});

// ---------------------------------------------------------------------------
// Sanity check: dev server must be reachable
// ---------------------------------------------------------------------------

beforeAll(async () => {
  try {
    const res = await fetch(`${DEV_SERVER}/`);
    if (!res.ok) throw new Error(`status ${res.status}`);
  } catch (e) {
    throw new Error(
      `Dev server is not reachable at ${DEV_SERVER}. ` +
        `Start it with 'npm run dev -- --port 4399' before running these tests. ` +
        `Original error: ${(e as Error).message}`,
    );
  }
}, 10_000);

// ---------------------------------------------------------------------------
// 1. POST /api/inbox persists item and it appears in page HTML
// ---------------------------------------------------------------------------

describe('POST /api/inbox — persistence and HTML appearance (criterion 1)', () => {
  it('returns 200 { ok: true }', async () => {
    const res = await serverPost({ text: 'inbox-ui-test-add', project: null });
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json).toEqual({ ok: true });
  });

  it('writes the new item to manual.json', async () => {
    const before = readManualFile();
    const initialCount: number = before.inbox.length;

    await serverPost({ text: 'inbox-ui-persist-check', project: null });

    const after = readManualFile();
    expect(after.inbox).toHaveLength(initialCount + 1);
    const added = after.inbox.find((i: { text: string }) => i.text === 'inbox-ui-persist-check');
    expect(added).toBeDefined();
    expect(added.done).toBe(false);
    expect(typeof added.id).toBe('string');
    expect(typeof added.created).toBe('string');
  });

  it('added item appears in the rendered page HTML (simulates reload)', async () => {
    const res = await serverPost({ text: 'inbox-ui-html-check-unique', project: null });
    expect(res.status).toBe(200);

    // After POST the server has written to manual.json; next page render reads it.
    const html = await fetchDashboardHTML();
    expect(html).toContain('inbox-ui-html-check-unique');
  });

  it('added item appears inside the inbox section (not just anywhere in the DOM)', async () => {
    await serverPost({ text: 'inbox-ui-section-check', project: null });

    const html = await fetchDashboardHTML();

    // The inbox section has aria-label="Quick-capture inbox"
    const inboxSectionStart = html.indexOf('aria-label="Quick-capture inbox"');
    expect(inboxSectionStart).toBeGreaterThan(-1);

    // The item text must appear after the inbox section opening tag
    const itemPosition = html.indexOf('inbox-ui-section-check', inboxSectionStart);
    expect(itemPosition).toBeGreaterThan(-1);
  });

  it('item with a project tag renders the project badge', async () => {
    await serverPost({ text: 'inbox-ui-with-project', project: 'my-project' });

    const html = await fetchDashboardHTML();
    expect(html).toContain('inbox-ui-with-project');
    expect(html).toContain('my-project');
  });
});

// ---------------------------------------------------------------------------
// 2. DELETE /api/inbox removes item and it disappears from page HTML
// ---------------------------------------------------------------------------

describe('DELETE /api/inbox — removal and HTML absence (criterion 2)', () => {
  it('returns 200 { ok: true } when deleting an existing item', async () => {
    // First add an item so we have a known id to delete
    const addRes = await serverPost({ text: 'inbox-to-delete', project: null });
    expect(addRes.status).toBe(200);
    const afterAdd = readManualFile();
    const item = afterAdd.inbox.find((i: { text: string }) => i.text === 'inbox-to-delete');
    expect(item).toBeDefined();

    const delRes = await serverDelete({ id: item.id });
    expect(delRes.status).toBe(200);
    const json = await delRes.json();
    expect(json).toEqual({ ok: true });
  });

  it('deleted item is absent from manual.json', async () => {
    const addRes = await serverPost({ text: 'inbox-delete-persist', project: null });
    expect(addRes.status).toBe(200);
    const afterAdd = readManualFile();
    const item = afterAdd.inbox.find((i: { text: string }) => i.text === 'inbox-delete-persist');

    await serverDelete({ id: item.id });

    const afterDelete = readManualFile();
    expect(afterDelete.inbox.find((i: { id: string }) => i.id === item.id)).toBeUndefined();
  });

  it('deleted item disappears from the rendered page HTML (simulates reload)', async () => {
    // Add item
    await serverPost({ text: 'inbox-delete-html-check', project: null });
    const afterAdd = readManualFile();
    const item = afterAdd.inbox.find((i: { text: string }) => i.text === 'inbox-delete-html-check');

    // Confirm it's visible before delete
    const htmlBefore = await fetchDashboardHTML();
    expect(htmlBefore).toContain('inbox-delete-html-check');

    // Delete it
    const delRes = await serverDelete({ id: item.id });
    expect(delRes.status).toBe(200);

    // Confirm it's gone after delete
    const htmlAfter = await fetchDashboardHTML();
    expect(htmlAfter).not.toContain('inbox-delete-html-check');
  });

  it('returns 404 when deleting an unknown id', async () => {
    const res = await serverDelete({ id: 'does-not-exist-3-2' });
    expect(res.status).toBe(404);
    const json = await res.json();
    expect(json.ok).toBe(false);
    expect(typeof json.error).toBe('string');
  });
});

// ---------------------------------------------------------------------------
// 3. Empty state shows "No items." when inbox is empty (criterion 3)
// ---------------------------------------------------------------------------

describe('Empty state renders "No items." (criterion 3)', () => {
  it('page shows "No items." text when the inbox array is empty', async () => {
    // Drain all inbox items from manual.json
    const manual = readManualFile();
    // Remove all items (will be restored by afterEach snapshot)
    writeFileSync(
      MANUAL_PATH,
      JSON.stringify({ ...manual, inbox: [] }, null, 2) + '\n',
      'utf-8',
    );

    const html = await fetchDashboardHTML();
    expect(html).toContain('No items.');
  });

  it('"No items." is inside the Quick-capture inbox section', async () => {
    const manual = readManualFile();
    writeFileSync(
      MANUAL_PATH,
      JSON.stringify({ ...manual, inbox: [] }, null, 2) + '\n',
      'utf-8',
    );

    const html = await fetchDashboardHTML();

    const inboxSectionStart = html.indexOf('aria-label="Quick-capture inbox"');
    expect(inboxSectionStart).toBeGreaterThan(-1);

    const noItemsPosition = html.indexOf('No items.', inboxSectionStart);
    expect(noItemsPosition).toBeGreaterThan(-1);
  });

  it('the inbox list is NOT rendered when empty (no <ul aria-label="Inbox items">)', async () => {
    const manual = readManualFile();
    writeFileSync(
      MANUAL_PATH,
      JSON.stringify({ ...manual, inbox: [] }, null, 2) + '\n',
      'utf-8',
    );

    const html = await fetchDashboardHTML();
    // The <ul aria-label="Inbox items"> should not appear when list is empty
    expect(html).not.toContain('aria-label="Inbox items"');
  });
});

// ---------------------------------------------------------------------------
// 4. Page renders correctly with no items — no HTTP errors (criterion 4)
// ---------------------------------------------------------------------------

describe('Page renders without errors when inbox is empty (criterion 4)', () => {
  it('GET / returns 200 when inbox is empty', async () => {
    const manual = readManualFile();
    writeFileSync(
      MANUAL_PATH,
      JSON.stringify({ ...manual, inbox: [] }, null, 2) + '\n',
      'utf-8',
    );

    const res = await fetch(`${DEV_SERVER}/`);
    expect(res.status).toBe(200);
  });

  it('rendered HTML contains the inbox section (not omitted when empty)', async () => {
    const manual = readManualFile();
    writeFileSync(
      MANUAL_PATH,
      JSON.stringify({ ...manual, inbox: [] }, null, 2) + '\n',
      'utf-8',
    );

    const html = await fetchDashboardHTML();
    expect(html).toContain('aria-label="Quick-capture inbox"');
    expect(html).toContain('Quick note...');  // Add-form placeholder is present
  });

  it('rendered HTML includes the Add button when inbox is empty', async () => {
    const manual = readManualFile();
    writeFileSync(
      MANUAL_PATH,
      JSON.stringify({ ...manual, inbox: [] }, null, 2) + '\n',
      'utf-8',
    );

    const html = await fetchDashboardHTML();
    // The submit button for adding items must always appear
    expect(html).toContain('aria-label="Add inbox item"');
  });

  it('page title is present (full page structure intact when inbox is empty)', async () => {
    const manual = readManualFile();
    writeFileSync(
      MANUAL_PATH,
      JSON.stringify({ ...manual, inbox: [] }, null, 2) + '\n',
      'utf-8',
    );

    const html = await fetchDashboardHTML();
    expect(html).toContain('<title>Project Dashboard</title>');
    // Error banner must NOT appear
    expect(html).not.toContain('Failed to load projects');
  });
});
