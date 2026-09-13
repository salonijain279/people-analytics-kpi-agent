"""Proactive signal scan: the second entry point into the same
investigation pipeline, alongside the question-first path in query_plan.py.

Instead of waiting for a user to ask about a specific department, this
scans every department each month for an unusual upward move in trailing
turnover and flags candidates for investigation -- routing straight into
the same change-driver calculation a user would get by asking about it
directly. Question-first and signal-first are two doors into one
controlled path, not two separate systems.

"Unusual" here is a fixed threshold on the month-over-month change in the
trailing rate (default: TTM rate up more than 1.5 percentage points).
A real deployment would calibrate this against each department's own
historical volatility rather than a single global cutoff; the fixed
threshold here is a starting point, not a tuned production rule.
"""
import pandas as pd

from calculation_engine import trailing_turnover_rate

UPWARD_MOVE_THRESHOLD = 0.015  # 1.5 percentage points, TTM rate
MIN_HEADCOUNT_FOR_SIGNAL = 30  # below this, a single termination swings the rate too much to be a reliable signal


def scan_for_signals(panel: pd.DataFrame, months: list, window: int = 12) -> pd.DataFrame:
    current_month, prior_month = months[-1], months[-2]
    rows = []
    for dept in sorted(panel["department"].unique()):
        current = trailing_turnover_rate(panel, dept, window, current_month)
        prior = trailing_turnover_rate(panel, dept, window, prior_month)
        if current["rate"] is None or prior["rate"] is None:
            continue
        move = current["rate"] - prior["rate"]
        small_population = current["avg_headcount"] < MIN_HEADCOUNT_FOR_SIGNAL
        flagged = move >= UPWARD_MOVE_THRESHOLD
        rows.append({
            "department": dept,
            "current_ttm_rate": current["rate"],
            "prior_ttm_rate": prior["rate"],
            "move": round(move, 4),
            "avg_headcount": current["avg_headcount"],
            "small_population_warning": small_population,
            "flagged": flagged,
        })
    return pd.DataFrame(rows).sort_values("move", ascending=False).reset_index(drop=True)
