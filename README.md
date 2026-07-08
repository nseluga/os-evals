# os-evals

Optimization loop to measure which layers of the ~/os setup earn their keep via ablation across 4 rungs: bare Claude → + global CLAUDE.md → + memory → + skills.

See [SPEC.md](SPEC.md) for full design.

## Running an iteration

```bash
./run.sh
```

Runs the full 72-run matrix (12 tasks × 4 rungs on Sonnet 4.6, plus 12 tasks × 2 rungs on Opus-tier for a bare-vs-full spot check). Outputs scorecard to `scorecards/` and transcript JSONs to `runs/`.
