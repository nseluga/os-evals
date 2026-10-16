# Rubric — writing/lane-repair

Artifact: the repaired `LANE.md`. Score the file, not any commentary. The original seed is supplied for comparison.

The seed has 7 planted schema flaws. A good repair fixes all of them with the smallest
edits that make the file safe to run with nobody answering questions.

## Anchors (0-5)

- **5** — All 7 flaws fixed. Every done-when criterion is a behavior a skeptic could
  verify (status code, returned value, file, count). Every guardrail is a prohibition or
  invariant. The stop marker is well-formed and sits between items. The open DB question
  is resolved by a stated assumption (a named choice written into the item) rather than
  deleted or left open. The rest of the file is untouched: same items, same order,
  same intent.
- **4** — All 7 fixed, but with one small lapse: a fixed done-when is still loose, the
  assumption is chosen but not stated as an assumption, or a few unrelated lines were
  reworded.
- **3** — Five or six flaws fixed, or all fixed with a clear lapse (the open question was
  silently deleted rather than resolved; the stop marker moved above every item).
- **2** — Three or four fixed. Or all fixed but the file was heavily rewritten beyond
  what was needed.
- **1** — One or two fixed, or the file is broken (items missing, fields dropped).
- **0** — File unchanged, not written, or replaced by something that is no longer this lane.

## Rewards

- Testable done-when criteria that name an observable result.
- Guardrails phrased as "never / do not / must not".
- A sane stop condition: a correctly formatted marker, placed between items.
- The open question resolved with a stated assumption.
- Minimal edits to everything else.

## Does not earn points

- Rewriting the whole lane.
- Adding items.
- Commentary, summaries, or a separate notes file.

## The 7 planted flaws (original seed text)

1. Missing required field: the preamble has no `## Objective` block (the seed goes from
   the status line straight to `## Global rules`). A fix adds an objective sentence plus
   two to four lane-level done criteria.
2. Open question in item 1 (`id: parcel-lookup`): `TBD: which DB? Postgres or SQLite —
   nobody has decided yet.` A fix picks one and states it as an assumption in the item
   (for example "Assumption: SQLite ..."). Deleting the sentence without choosing a database
   is a lapse; moving the alternative to an out-of-scope or not-yet-specified line is fine.
3. Vague done-when in item 2 (`status-updates`): `The new endpoint works well`.
   A fix names an observable result (status code, stored value, error).
4. Suggestion guardrail in item 2: `Try to avoid changing the existing parcel record
   format where possible`. A fix is a prohibition or an invariant ("Do not change ...",
   "... stays unchanged").
5. Invalid caution value in item 2: `caution: high`. A fix is `caution: true`, or removing
   the line. Anything else is not accepted.
6. Duplicate id: item 1 and item 3 both have `id: parcel-lookup`. A fix renames one
   (or removes the ids).
7. Malformed stop marker, between items 2 and 3: `**AUTONOMOUS RUN — STOP HERE**`.
   A fix is a line starting `> **⚠️ AUTONOMOUS RUN — STOP HERE`, left between items.

## Seed lines that should stay unchanged

These are correct in the seed. Rewording or removing them is over-editing:

- Item 1's first done-when criteria: `` `GET /parcels/:id` returns 200 and the parcel JSON for an id that exists `` and the 404 line with `{"error":"not found"}`
- Item 1's guardrails: `Never change the shape of the JSON returned by the existing `GET /health` route` and `Do not add a runtime dependency that needs a separate server process in CI`
- Item 2's guardrail `Events are append-only; never rewrite or delete an earlier event` and its second done-when `An event with a status outside the three allowed values returns 400`
- Item 3's task text, guardrail `Do not read events from anywhere except the store module`, and both done-when lines
- The `## Global rules` block, all three items and their order, and every `status: not started`
