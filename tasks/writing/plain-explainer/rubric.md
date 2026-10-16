# Rubric: plain-language explanation plus a decision

The author was a coding assistant answering a learner: "Explain what a Claude Code hook is, and tell me whether I should set one up to auto-format my code on every save. Keep it short and practical; I want to actually make a decision." The asker is still learning the tooling.

Judge only the artifact.

## Scale
- 5: Opens with a plain-English definition a newcomer can follow (a hook is a command or script that runs automatically when a particular event happens, ideally with a concrete example), before any jargon. Gives a clear recommendation. Volunteers concrete tradeoffs of auto-formatting on save without being asked (for example slower saves, silent failures, surprising diffs when the formatter config differs, conflicts with an existing formatter) and says when the recommendation would change. Short and practical; every sentence helps the decision.
- 4: Plain definition early, a recommendation (clear or clearly implied) and at least one concrete tradeoff. May be missing the "when this would change" condition or a concrete example; wording is still accessible.
- 3: Definition is correct but jargon-heavy or buried, or tradeoffs are only generic ("it depends"), or the recommendation is unclear. The reader could still partly decide.
- 2: Mostly jargon or marketing language; no real tradeoff; a flat "yes, set it up".
- 1: Little useful content; does not define the term or does not address the decision.
- 0: Empty, off-topic, or factually wrong about what a hook is.

## Does not earn points
- Length: a long answer is worse than a short one with the same content, because the asker wanted short.
- Enthusiasm or praise for the idea ("powerful", "great practice") instead of reasons.
- Naming internal event names or settings schema without first saying what they mean in plain words.
- Hedged non-answers that avoid recommending anything.
