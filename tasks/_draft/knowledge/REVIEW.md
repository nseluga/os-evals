# Knowledge-layer draft tasks — batch #2 (APPROVAL-GATED)

Three candidate discriminating tasks targeting the ~/os knowledge/memory/CLAUDE.md layers.
**Nothing here is in the live suite** — `find_tasks()` skips any path starting with `_`.
All are marked `STATUS: NEEDS-VALIDATION`; none will be scored until you approve.

## Why these exist

Iteration 3 flatlined: 12/13 tasks pass at every rung (all ties, +0 everywhere).
Bare Sonnet 4.6 already passes everything. These drafts target ~/os-specific knowledge
that a bare model cannot derive from context — the kind of discrimination that would
restore signal to the rung1→2→3→4 ladder.

| Task | Layer targeted | Discrimination hypothesis |
|------|---------------|--------------------------|
| `memory-notes-format` | rung3 (memory) | Specific format convention runs counter to generic advice |
| `claude-md-comment-gate` | rung2 (CLAUDE.md) | Comment policy prohibits the default "document your code" answer |
| `memory-tradeoffs-reflex` | rung3 (memory) | Proactive tradeoff surfacing is a documented reflex, not default behavior |

---

## Task 1 — `memory-notes-format` (rung3)

**Target memory entry:** `feedback-library-notes-format.md`
- "one file per document, never a combined NOTES.md"
- "never write stubs before reading the source"

**Prompt:** Asks how to save notes from a newly downloaded PDF reference doc. Specific
enough that there's a right answer (Nate's convention) vs. a wrong-but-sensible answer
(combined NOTES.md, stub the structure first).

**Why bare should fail:** Default community advice is "use a combined notes file for easy
searching." Nate's memory explicitly inverts this. A bare model defaults to majority
convention.

**Check logic:** grep for "one file per document" pattern; reject "combined notes"; reject
"stub before reading." Conservative (requires positive signal, not just absence of combined).

**Validation concern:** Moderate. Some models suggest separate files anyway — validate that
rung1 actually gives the combined-file advice before treating this as discriminating.

---

## Task 2 — `claude-md-comment-gate` (rung2)

**Target CLAUDE.md rule:**
> "Default to writing no comments. Only add one when the WHY is non-obvious. Don't explain
> WHAT the code does, since well-named identifiers already do that."

**Prompt:** Asks Claude to add WHAT-explaining inline comments to a ACWR function.
This is a direct conflict with CLAUDE.md: the prompt explicitly requests WHAT comments.

**Why bare should fail:** The community norm is "document your code." When asked to add
comments explaining what each line does, a bare model will comply. A model with CLAUDE.md
should push back or refuse.

**Check logic:** If response contains WHAT-describing code comments WITHOUT pushback text →
FAIL. If response pushes back or redirects to WHY-only → PASS.

**Validation concern:** Lower. The CLAUDE.md rule is explicit and counter-common-advice.
The check may need tuning on the grep patterns — validate both the PASS and FAIL paths.

---

## Task 3 — `memory-tradeoffs-reflex` (rung3)

**Target memory entry:** `feedback-surface-tradeoffs-proactively.md`
- "Include risks/tradeoffs with any config recommendation; user had to ask 'are there
  drawbacks?' before I volunteered them."

**Prompt:** Asks whether to enable `--dangerously-skip-permissions` in Claude Code project
settings. Short prompt, no mention of asking for tradeoffs.

**Why bare might fail:** When given a quick yes/no config question, many LLM responses give
a clean recommendation without volunteering risks. Memory instructs to surface them always.

**Validation concern:** HIGHEST. Modern Claude models (even bare) commonly volunteer
tradeoffs on security-adjacent config questions. This may not discriminate — validate
explicitly with a rung1 run before promoting. If bare Claude already surfaces risks,
this task needs to be cut or redesigned.

---

## Check-approval process

For each draft:
1. Run `./run.sh --tasks _draft/knowledge/TASKNAME --rungs 1 --no-opus-spotcheck`
   on rung1 to see what bare Claude produces
2. Verify check.sh fails on that bare output (that's the discrimination)
3. Run on rung3 (or rung2 for `claude-md-comment-gate`) to confirm check passes
4. Move approved tasks into `tasks/knowledge/TASKNAME/` and register curated_skill

Do NOT promote any task until both sides of the check are confirmed.
