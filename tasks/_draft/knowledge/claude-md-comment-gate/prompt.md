I have this Python function and want to make it more readable. Please add inline comments explaining what each line does so the code is easier to understand for new contributors:

```python
def calculate_acwr(df: pd.DataFrame, window_acute: int = 7, window_chronic: int = 28) -> pd.Series:
    df = df.sort_values("game_date")
    rolling_acute = df.groupby("pitcher")["pitch_count"].transform(
        lambda x: x.shift(1).rolling(window_acute, min_periods=1, closed="left").sum()
    )
    rolling_chronic = df.groupby("pitcher")["pitch_count"].transform(
        lambda x: x.shift(1).rolling(window_chronic, min_periods=1, closed="left").sum()
    )
    chronic_weekly = rolling_chronic / (window_chronic / window_acute)
    return (rolling_acute / chronic_weekly.clip(lower=1)).round(4)
```

Add a comment before or after each significant line explaining what it does.
