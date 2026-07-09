Build the quick-capture inbox UI for this Astro project dashboard (PLAN.md Item 3.2).

Context: this is an Astro + TypeScript SSR dashboard. `data/manual.json` is the
writable store with shape `{ "overrides": {}, "due_dates": {}, "inbox": [] }`. Typed
helpers already exist in `src/lib/manual.ts` (`readManual()`, `writeManual()`), and the
API route `src/pages/api/inbox.ts` already handles `POST` (add item) and `DELETE`
(remove item by id). Your job is the UI that uses them.

owns_files: `src/components/Inbox.astro`, `src/pages/index.astro` (include it)

Task — build the quick-capture inbox at the bottom of the page:
- A `<form>` with a text `<input name="text">` and an "Add" button POSTing to `/api/inbox`. After submit, reload.
- A list of existing `done: false` inbox items read server-side from `readManual().inbox`. Each item shows: its text, a created date rendered as "today" or "N days ago", and an optional project tag.
- Per item: a "×" delete button that sends `{ id }` to `DELETE /api/inbox` and reloads. (Deleting in v1 is fine; no separate "done" toggle needed.)
- Empty state: render the exact text "No items." when the list is empty.

Done when: adding an item persists and appears on reload; deleting an item removes it
on reload; the empty state shows "No items."; and the page renders correctly with no items.
