# Rubric — process/orchestrate-two-part

Score 0-5 for HOW the work was organised, judged from the transcript and the final
diff. Correctness is scored separately by check.sh; do not reward or punish it here
except where noted. The prompt never says how to split the work, so credit only what
the run chose on its own.

## What to look for

1. **Visible split statement.** Before any work starts, one line naming the pieces
   and why they are separable (for example: cursor pagination in the read API, config
   validation in the add-source script; disjoint files, no shared state).
2. **Worker briefs.** Each worker is told its goal, the files it owns, and its
   done-when, and nothing about the other worker's piece beyond what it needs. A brief
   that is just "do item 1" with no done-when is weak.
3. **Independent review.** A reviewer that did not write the code gets only the diff
   and the done-whens, not the workers' reasoning or a "this looks fine" summary, and
   reports findings by severity.
4. **Final full run by the main thread.** After workers and review, the main thread
   itself runs the whole suite and reports the real result, rather than relying on a
   worker's "tests pass".
5. **Sensible model choices.** Cheaper or mid-tier models on the mechanical build
   work, a stronger model on the review. Using the strongest model everywhere, or
   a weak model as the only reviewer, is a mild negative. Not choosing a model at all
   is neutral.
6. **Parallel, isolated work.** The two workers run at the same time and cannot
   trample each other's files (separate working copies, or provably disjoint files).

## Scale

- **5**: items 1-4 all clearly present, plus a sensible model split and parallel,
  isolated workers. Findings from the review are applied or consciously dismissed.
- **4**: split statement, two briefed workers and an independent review, but one of
  {final full run by the main thread, model choice, isolation} is missing or sloppy.
- **3**: two workers and a review exist, but the briefs are thin, or the reviewer was
  handed the workers' conclusions, or there is no stated split.
- **2**: orchestration is present but wrong-shaped: workers run one after another
  with no reason, review happens before the last change lands, or the review is a
  rubber stamp.
- **1**: a single helper agent was used, or agents were used only for exploring.
- **0**: everything built inline in the main thread, with no workers and no
  independent review.

## Does not earn points

- Spawning agents for ceremony: an exploration agent, a "planner", or a summariser
  that adds nothing to the build.
- Two workers that both edit the same files, or a second worker that redoes the first
  one's job.
- A reviewer spawned before the last change landed, or a review of the workers'
  self-reports instead of the diff.
- Claiming "reviewed" or "tests pass" with no matching tool call in the transcript.
- A long plan or checklist with no split statement naming the actual pieces.
- Padding the final message with a list of what each worker said.
