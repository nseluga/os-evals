A teammate describes how they evaluated a machine-learning model that predicts **MLB
pitcher injury risk for the upcoming season** from workload and biomechanics data. Act
as a skeptical analytics peer reviewer: critique the methodology and call out the most
serious problems, explaining why each undermines the result. Be specific.

> "Each row is one pitcher-season (2015–2023). I shuffled all pitcher-seasons and did a
> random 80/20 train/test split. The model hit 94% accuracy on the held-out set, which I
> report as the headline number — injuries are rare (about 6% of seasons) but 94% is
> strong. My most predictive features were the pitcher's total innings and days on the
> injured list **in the season we're predicting**, plus career workload to date. I'm
> confident it's ready to deploy."
