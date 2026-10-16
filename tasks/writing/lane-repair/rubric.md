# Rubric — writing/lane-repair

Artifact: the repaired `LANE.md`. Score the file, not any commentary.

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
