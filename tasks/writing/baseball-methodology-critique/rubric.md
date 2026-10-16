# Rubric: skeptical peer review of an injury-risk model evaluation

The author was asked to act as a skeptical analytics peer reviewer of this description: a model predicting MLB pitcher injury risk for the upcoming season from workload and biomechanics data; each row is a pitcher-season (2015-2023); all rows were shuffled and split randomly 80/20; the headline is 94% accuracy on the held-out set although injuries occur in about 6% of seasons; the most predictive features are the pitcher's total innings and days on the injured list in the season being predicted, plus career workload to date; the teammate says it is ready to deploy. The reviewer should call out the most serious problems and explain why each undermines the result, specifically.

Judge only the artifact.

## Scale
- 5: Identifies all three core flaws and explains each: (a) random split of time-ordered pitcher-seasons leaks future information, and the fix is a time-based or forward-chaining split (also notes repeated pitchers across train and test); (b) same-season innings and injured-list days are outcomes or near-outcomes that leak the label, so they cannot be predictors of the season being predicted; (c) 94% accuracy on a 6%-positive problem is near the always-negative baseline, so precision/recall, PR-AUC or similar are needed. Ranks them by severity, concludes the result does not support deployment, and may add a valid further point (calibration, no confidence interval, no baseline).
- 4: Identifies all three with correct but brief reasoning, or two with full reasoning plus a valid extra point.
- 3: Identifies two of the three correctly; or all three named without explaining why they matter.
- 2: Identifies one of the three; or names the right topics only in passing while mostly giving generic ML advice.
- 1: Generic remarks ("needs more data", "check for overfitting") with none of the core flaws.
- 0: Endorses the methodology, is empty, or is off-topic.

## Does not earn points
- Terms used without explanation ("there is leakage" with no mechanism).
- Generic best-practice lists not tied to the described setup.
- Claims that are incorrect for this setup (for example that class imbalance makes accuracy higher-is-worse without the baseline argument).
- Tone alone: confident phrasing is not evidence of correct reasoning.
