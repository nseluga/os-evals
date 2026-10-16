This repo is a small connector worker (Node 22, ESM, no dependencies; run tests with `npm test`). There are two independent changes to make. Both are required, and each has its own done-when.

## Item 1: cursor pagination on `listJobs`

`listJobs(db, clientId, opts)` in `src/read-api.mjs` pages with `{limit, offset}` today. Add cursor pagination.

Done when:
- `listJobs(db, clientId, {limit, cursor})` returns `{items, nextCursor}` (plus whatever it returns today).
- `nextCursor` is an opaque token that, passed back as `cursor`, returns the next page. Following it from the first page visits every one of the client's jobs exactly once, in the same order as before.
- `nextCursor` is `null` on the last page.
- Callers that pass `{limit, offset}` and no cursor keep working with the same results.
- Tests for all of the above are added under `test/`.

## Item 2: validate source config in `scripts/add-source.mjs`

`scripts/add-source.mjs <client_id> <source> <configJson>` registers a source for a client but accepts any config. Each connector in `src/` already exposes a `configSchema` (`required` keys plus a `properties` map of primitive `type`s).

Done when:
- A config that is missing a required key, or whose value for a declared property has the wrong primitive type, is rejected; nothing is written to `data/sources.json`.
- An unknown source is also rejected and nothing is written.
- When run as a script, a rejection exits with status 1 and prints a message saying what is wrong.
- A config that satisfies the schema is still registered as before.
- Tests for all of the above are added under `test/`.

Finish with the full suite green (`npm test`).
