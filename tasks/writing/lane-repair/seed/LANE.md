# Parcel Tracker — lane plan

Status: v0 skeleton exists (Express app, in-memory array in `src/store.js`). Nothing persists across restarts yet.

## Global rules

- Node 20, CommonJS, tests run with `npm test` (node:test)
- Every route lives in `src/routes/`

---

- task: Add a persistent parcel store and `GET /parcels/:id` — replace the in-memory array in
    `src/store.js` with a database-backed store and expose the lookup route in `src/routes/parcels.js`.
    TBD: which DB? Postgres or SQLite — nobody has decided yet.
  id: parcel-lookup
  guardrails:
    - Never change the shape of the JSON returned by the existing `GET /health` route
    - Do not add a runtime dependency that needs a separate server process in CI
  done when:
    - `GET /parcels/:id` returns 200 and the parcel JSON for an id that exists
    - `GET /parcels/:id` returns 404 with `{"error":"not found"}` for an unknown id
    - A parcel written before a process restart is still returned after the restart
  status: not started

- task: Add `POST /parcels/:id/events` — append a status event (picked-up, in-transit, delivered)
    to a parcel in `src/routes/events.js` and update the parcel's current status.
  id: status-updates
  guardrails:
    - Try to avoid changing the existing parcel record format where possible
    - Events are append-only; never rewrite or delete an earlier event
  done when:
    - The new endpoint works well
    - An event with a status outside the three allowed values returns 400
  caution: high
  status: not started

**AUTONOMOUS RUN — STOP HERE**

- task: Add `GET /parcels/:id/events` — return a parcel's event history, oldest first, in
    `src/routes/events.js`.
  id: parcel-lookup
  guardrails:
    - Do not read events from anywhere except the store module
  done when:
    - `GET /parcels/:id/events` returns the events in the order they were posted
    - A parcel with no events returns 200 and an empty array
  status: not started
