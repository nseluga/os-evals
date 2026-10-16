# Rubric: audit of an AI-tooling setup and a model-tier recommendation

The author was given a snapshot: a list of installed skills (a coordinated multi-agent build/test/review toolset, an analytics-review skill, an audit skill), two behaviour preferences (surface tradeoffs; cheap model for mechanical work, Sonnet or better for reasoning roles), and a usage log of 20 sessions (16 of them multi-file builds, refactors or bug fixes handled in a single ad-hoc chat, with the multi-agent toolset invoked 0 times). They were asked, in plain English: (1) which subsystem is most under-used relative to the work and what should change, with evidence; (2) which model tier (Opus / Sonnet / Haiku) to use for a large multi-file refactor that needs reasoning across modules, and why.

Judge only the artifact.

## Scale
- 5: Names the multi-agent build/test/review toolset (the first skill bullet) as the under-used subsystem, cites the evidence (0 invocations against 16 of 20 sessions of the kind it exists for), says concretely what to change (route that work through it); recommends Opus for the cross-module refactor, ruling out Haiku, with a reason tied to reasoning difficulty and the stated preference; mentions a tradeoff (cost, latency, overhead) of its recommendation.
- 4: Correct subsystem with the key evidence and a clear change; recommends Opus (or Sonnet as an explicitly reasoned floor) and rejects Haiku; no tradeoff discussion or thin reasoning.
- 3: Correct subsystem but evidence is vague or the fix is not actionable, or a defensible model pick with weak reasoning.
- 2: Picks a different subsystem as the main finding, or recommends a model that contradicts the stated preferences, with some correct observation elsewhere.
- 1: Both answers wrong or unsupported by the data.
- 0: Empty, off-topic, or recommends Haiku for the refactor with no other correct finding.

## Does not earn points
- Generic advice about AI tooling not drawn from the snapshot's numbers.
- Re-describing the snapshot without drawing a conclusion.
- Hedging across all three model tiers without choosing one.
- Numbers or facts that are not in the snapshot.
