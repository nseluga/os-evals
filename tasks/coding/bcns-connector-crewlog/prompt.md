This is the bcns-mini repo. It pulls job data from third-party tools through small
connectors (see `src/monday.mjs` and `src/shopify-lite.mjs`), and every connector
normalizes its rows into the same record shape.

A client runs their crews on **Crewlog**, a crew time-tracking SaaS. Add a Crewlog
connector so it shows up as a source in the product the same way Monday and Shopify do.

A Crewlog job row looks like this:

```json
{
  "jobRef": 7001,
  "crewId": "c-9",
  "client_id": "northfield",
  "crewStatus": null,
  "total": "1234.565",
  "startedAt": "2026-03-01T22:30:00-08:00",
  "tz": "America/Los_Angeles",
  "authHeader": "Bearer crw_9f8e7d6c5b4a3210"
}
```

- `jobRef` is a number, `crewStatus` can be `null`, and `total` is a decimal string
  in dollars.
- `startedAt` is an ISO timestamp with a UTC offset; `tz` is the crew's IANA timezone.
- `authHeader` is the credential the sync used for that row.
- The connector is configured per client with a `crewId`; it fetches that crew's rows
  (use an hard-coded fixture like the other connectors, no real HTTP).

Each connector's `normalize(raw)` returns the job record the rest of the product
consumes: `id`, `client_id`, `source`, `title`, `status`, `amount_cents`, `day`
(YYYY-MM-DD) and `raw` (the original row). Crewlog rows have to come out in that same
shape.

Add tests for the new connector alongside the existing ones, and make sure the whole
suite passes with `npm test`.
