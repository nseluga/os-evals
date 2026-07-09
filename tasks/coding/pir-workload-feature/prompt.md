This is the Pitcher Injury Risk+ repo. `src/features/workload_features.py` computes
pitcher workload features at the game level from a DataFrame with columns
`pitcher`, `game_date`, and `pitch_count`.

Add an **acute:chronic workload ratio (ACWR)** feature — an industry-standard spike
detector for injury risk — to the workload feature pipeline.

Requirements:
- Expose it as `build_workload_features(game_df)` returning the input DataFrame with a
  new column named `acwr_7_28` (float), alongside the existing workload columns.
- Use a 7-day acute window and a 28-day chronic window, consistent with the rolling
  pitch-count conventions already used in this module.
- Follow the module's existing workload conventions for how rolling windows treat the
  current appearance and how first appearances / empty history are handled (look at the
  existing rolling-window helpers in the file before implementing).
- Handle the division safely so first appearances / zero chronic history do not produce
  inf or NaN blowups.

Match the surrounding code style (pandas, type hints, docstrings). Do not change the
signatures of existing functions.
