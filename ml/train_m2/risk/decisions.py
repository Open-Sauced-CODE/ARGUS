"""One decision per cluster (Shaurya-owned): the candidate the PIPELINE WOULD APPLY = first gate-passing fix draft in
sample order (v3 section 9.4). Calibration uses exactly this row per cluster; clusters with no passing draft are
counted separately and never as accepted."""
from __future__ import annotations

import pandas as pd


def select_decisions(frame: pd.DataFrame) -> pd.DataFrame:
    """frame needs input_key, sample_idx and any other columns (score, y, ...); every row is already gate-passing."""
    if frame.empty:
        return frame.copy()
    return frame.sort_values(["input_key", "sample_idx"], kind="stable").groupby("input_key", sort=True).head(1).reset_index(drop=True)
