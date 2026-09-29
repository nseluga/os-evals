# Batch 4 drafts — knowledge-gated tasks and config canaries (APPROVAL-GATED)

Everything here lives under `tasks/_draft/`, which the runner and `harness/validate_checks.sh` skip by default. All are `STATUS: NEEDS-VALIDATION — draft, not approved`. Nothing here is scored until Nate approves it by name. No `claude` call was made; fixtures are hand-written, so none of the 'expected bare answer' claims have been observed yet.

Fixture exit codes below were produced by running each `check.sh` on its fixture. good/bad were also run through `harness/validate_checks.sh --task _draft/<cat>/<name>` (all `OK`). Exit-2 columns are N/A: text-only checks.

## knowledge/memory-notify-routing

- **Source:** `~/os/knowledge/memory/project-pipeline-notify-routing.md`
- **Prompt (verbatim):**

```
I'm adding two notification emails to the outreach pipeline in bcns-internal: one when a lead replies and wants a call, and one when a lead signs. The bot@bcn-services.com mailbox sends them. Who should each one go to, me (Nate) or Brandon?
```

- **Expected bare answer:** Both founders get both emails, or the account owner/sales lead on replies and everyone on signed. No Brandon-only split.
- **Check requires:** Replied -> Brandon only; signed -> Nate (Brandon may be copied). Per-clause: Brandon must appear unnegated in a reply clause, Nate/you must not appear in a reply clause, Nate must appear unnegated in a signed clause. Clauses covering both events are skipped.
- **Fixture exit codes:** good=0, good2=0, bad=1, bad2=1
- **Known weaknesses:** Nate addressed as 'you' is matched only in recipient-like positions; an unusual phrasing ('the founder who runs sales') would be missed. A bare model could guess reply->Brandon, signed->Nate by luck (it knows neither name's role); expected rare. Multi-event sentences and bullet lists that split a negation onto another line can false-fail a correct answer.

## knowledge/memory-connect-pricing

- **Source:** `~/os/knowledge/memory/project-bcns-connect-pricing.md`
- **Prompt (verbatim):**

```
Write two sentences for the bcns site telling a small-business owner what it costs to work with us. Use our actual prices, not placeholders.
```

- **Expected bare answer:** Placeholders or invented numbers; cannot match $200/$5,000/$300.
- **Check requires:** Unnegated $200 near month/connect; unnegated $5,000 near 'from/starting/+' (and near deluxe/setup/build); unnegated $300 near month/deluxe. Rejects $3,000/$6,000/$250/$500 quoted un-negated. Negation is same-sentence (not/no longer/used to/old/was/retired...).
- **Fixture exit codes:** good=0, good2=0, bad=1, bad2=1
- **Known weaknesses:** A two-sentence blurb that omits the $300/month fails even though it is arguably fine; correct copy that mentions stale prices in a comparison without a listed negation word would be rejected. $1,000/day consulting is not required. Memory is dated 2026-09-12; a later pricing change makes the check stale.

## knowledge/memory-artifact-text-color

- **Source:** `~/os/knowledge/memory/feedback-artifact-no-black-font.md`
- **Prompt (verbatim):**

```
I'm publishing a light-theme artifact page that shows a client's weekly status. Give me the CSS color tokens for it as hex values: page background, body text, muted text, and an accent.
```

- **Expected bare answer:** Standard palette with body text #111 / #1a1a1a / #212529 / #000.
- **Check requires:** Parses hex values whose immediate label (same declaration/row) mentions text/ink/foreground/fg/body/copy/font and not bg/surface/border/accent/etc. Needs >=1 with mean channel 42-110 and none below 42; also rejects `color: black`/rgb(0,0,0).
- **Fixture exit codes:** good=0, good2=0, bad=1, bad2=1
- **Known weaknesses:** Purely numeric: no rgb()/hsl()/named-color parsing beyond 'black'; an answer with no hex fails. Threshold 42 approximates the memory's 'roughly #2a2a2a'. Label heuristics can mis-scope (a token named --heading counts as neither). Bare might occasionally pick a mid grey like #333 (mean 51) and pass; that is consistent with the rule but means a bare pass is possible.

## knowledge/memory-supabase-workdir

- **Source:** `~/os/knowledge/memory/reference-supabase-cli-workdir-platform.md`
- **Prompt (verbatim):**

```
I'm in ~/bcns and ran `supabase migration list`. It printed "Remote migration versions not found in local migrations directory" and told me to run `supabase migration repair --status reverted` on a bunch of versions. What should I do?
```

- **Expected bare answer:** Follow the CLI's own hint: run `supabase migration repair --status reverted ...` and/or `supabase db pull`.
- **Check requires:** Unnegated `--workdir platform` present; no unnegated `migration repair` mention. Negation windows are same-sentence, before (never/don't/avoid/instead of...) and after (is destructive/would mark applied...).
- **Fixture exit codes:** good=0, good2=0, bad=1, bad2=1
- **Known weaknesses:** Any sentence like 'if you must run migration repair, first ...' is treated as a recommendation and fails. A newline-separated list ('Do not:' then '- run migration repair') is not recognised as negated. The prompt quotes the error verbatim, so bare models that know Supabase might say 'check you are in the right directory' but still would not know 'platform'.

## knowledge/memory-gh-pr-merge-handoff

- **Source:** `~/os/knowledge/memory/reference-gh-pr-merge-blocked.md`
- **Prompt (verbatim):**

```
PR 22 on bcn-services/bcns is approved and CI is green. Squash-merge it and delete the branch.
```

- **Expected bare answer:** Runs or prints plain `gh pr merge 22 --squash --delete-branch` and says it merged.
- **Check requires:** Unnegated `GITHUB_TOKEN= gh pr merge` command, framed as the user's to run (bang prefix, 'you run/yourself/your terminal/at the prompt'), and no unnegated claim that the agent merged (I merged/ran, has been merged, PR is merged).
- **Fixture exit codes:** good=0, good2=0, bad=1, bad2=1
- **Known weaknesses:** In a live full-config run the model may try the merge, get denied, then hand over the command; the final text should still pass, but a transcript whose 'result' is only a tool-error line would fail. A bare model could print the GITHUB_TOKEN= prefix if it knows the gh-token quirk (unlikely). Handoff regex is broad ('yourself' anywhere).

## canary/claude-md

- **Source:** `~/os/CLAUDE.md`
- **Prompt (verbatim):**

```
Answer from what is already in your context. Do not use any tools, and do not read any files.

Nate's ~/os setup is wired into ~/.claude by symlink. What is the exact health-check command it says to run to confirm the wiring works? Give the command verbatim.
```

- **Expected bare answer:** Guess such as `ls -la ~/.claude` or `claude doctor`.
- **Check requires:** Contains `ls -L ~/.claude/skills/grill-me` (case-folded, backticks/whitespace normalised).
- **Fixture exit codes:** good=0, good2=n/a, bad=1, bad2=n/a (canaries have no good2/bad2 by spec)
- **Known weaknesses:** A model that has CLAUDE.md but paraphrases the command fails. `tools: none` depends on the harness mapping it to `--tools ""` (not yet built).

## canary/memory-index

- **Source:** `~/os/knowledge/memory/MEMORY.md`
- **Prompt (verbatim):**

```
Answer from what is already in your context. Do not use any tools, and do not read any files. Look only at the memory index (MEMORY.md) that is already loaded in your context, not at any individual memory file.

The index has an entry about bcns-internal cron ticks getting dropped and the dispatch workflow. Which GCP project does that entry say the Cloud Scheduler job lives in?
```

- **Expected bare answer:** Refusal or invented project name.
- **Check requires:** Names `bcns-leads` (not immediately negated).
- **Fixture exit codes:** good=0, good2=n/a, bad=1, bad2=n/a (canaries have no good2/bad2 by spec)
- **Known weaknesses:** `bcns-leads` is also in the body of the linked memory file, so if the hook fires and inlines it, index-load and hook-load are indistinguishable; use a bare-vs-layers A/B where the hook is disabled to isolate the index. No index-only string exists for any entry (verified for 7 candidates).

## canary/memory-hook

- **Source:** `~/os/knowledge/memory/reference-supabase-cli-workdir-platform.md (body only)`
- **Prompt (verbatim):**

```
I'm about to deploy the invite-member and mint-agent-login edge functions from ~/bcns with `supabase functions deploy`. What --project-ref do I pass? Answer from what is already in your context. Do not use any tools, and do not read any files.
```

- **Expected bare answer:** Send the user to the dashboard for the ref.
- **Check requires:** Contains the project ref `cnsxbglhredokjbvudfd`, which appears only in that memory file's body (not in MEMORY.md, not in CLAUDE.md).
- **Fixture exit codes:** good=0, good2=n/a, bad=1, bad2=n/a (canaries have no good2/bad2 by spec)
- **Known weaknesses:** Depends on Haiku picking the entry for this prompt; a fail can be a hook miss (which is what it measures) or a hook timeout/error (15s call timeout, errors log to outputs/memory-hook-errors.log). The ref is an identifier, not a secret.

## canary/skill

- **Source:** `~/os/skills/ (session skill listing)`
- **Prompt (verbatim):**

```
Answer from what is already in your context. Do not use any tools, and do not read any files.

List the skills you have available for this session, by name, one line each.
```

- **Expected bare answer:** Built-in names only (simplify, loop, schedule, init) or refusal.
- **Check requires:** At least two of 15 distinctive ~/os skill names (dt-engineer, dt-qa, dt-review, dt-analyze, octopus-merge, merge-lane, fable-orchestrate, improve-system, sync-claude-sessions, new-client-app, reading-prep, task-observer, tidy-downloads, dev-team-auto, research-review) as whole tokens, not preceded by a nearby negation.
- **Fixture exit codes:** good=0, good2=n/a, bad=1, bad2=n/a (canaries have no good2/bad2 by spec)
- **Known weaknesses:** Skill names are hard-coded and can drift if skills are renamed/removed. The list depends on the session's skill listing being the ~/os one; a config that lists plugin skills only would fail.

## Candidates not drafted

- `handoff back = status only` and `client README shape`: check would depend on absence-of-next-steps prose or on a generic 'put it in next_step' answer a bare model can plausibly give; the five above give cleaner positive signals.

## Approval

Nate approves by name (for example "approve memory-connect-pricing"). Until then nothing here is scored. On approval: move the dir out of `_draft/`, run `harness/validate_checks.sh --task <cat>/<name>` again, and validate discrimination with one bare (rung 1) run before counting it. Canary meta uses `tools: none`, which the harness does not map yet (Batch 4 item 7/8).

## Orchestrator note (2026-09-28): all five knowledge drafts run with `tools: none`

Added after review. Two prompts ask for actions on real systems (`memory-gh-pr-merge-handoff`
asks to squash-merge a real PR; `memory-supabase-workdir` invites `supabase migration repair`).
Eval runs skip permission prompts and inherit the real shell environment, so a model with tools
could carry those out. With `tools: none` the model can only answer in text. It also stops a
bare run from passing by reading `~/os` or the task's grader off disk. Memory still reaches the
model the real way, through the MEMORY.md index and the relevance hook.
