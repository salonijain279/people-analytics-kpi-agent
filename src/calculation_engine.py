"""Deterministic calculations over the monthly workforce panel.

Every number here is plain arithmetic over `data/monthly_panel.parquet` --
no model touches these values. The Query Plan only decides *which*
calculation runs and over *what scope*; the actual math is ordinary
pandas, which is what makes the results checkable against the raw panel
by hand.

Voluntary turnover rate (a month, trailing window) is defined as:
    sum(terminations over the window) / average(headcount over the window)

TTM = trailing twelve months, T3M = trailing three months. Showing both
side by side matters: TTM is the slower, more stable annual view; T3M
reacts faster to a recent spike or dip, at the cost of more noise.
"""
import pandas as pd

from query_plan import QueryPlan


def _scope(panel: pd.DataFrame, department: str | None) -> pd.DataFrame:
    if department is None:
        agg = panel.groupby("month", as_index=False)[["headcount", "terminations"]].sum()
        return agg
    return panel[panel["department"] == department].copy()


def trailing_turnover_rate(panel: pd.DataFrame, department: str | None, window: int,
                            as_of_month) -> dict:
    scoped = _scope(panel, department)
    scoped = scoped[scoped["month"] <= as_of_month].sort_values("month")
    trailing = scoped.tail(window)
    if trailing.empty or trailing["headcount"].mean() == 0:
        return {"rate": None, "terminations": 0, "avg_headcount": 0, "months_available": 0}
    rate = trailing["terminations"].sum() / trailing["headcount"].mean()
    return {
        "rate": round(rate, 4),
        "terminations": int(trailing["terminations"].sum()),
        "avg_headcount": round(trailing["headcount"].mean(), 1),
        "months_available": len(trailing),
    }


def snapshot(panel: pd.DataFrame, plan: QueryPlan, months: list) -> dict:
    as_of = months[-1 - plan.current_offset]
    result = {"as_of_month": str(as_of), "department": plan.department or "Company-wide"}
    if plan.window in ("TTM", "BOTH"):
        result["TTM"] = trailing_turnover_rate(panel, plan.department, 12, as_of)
    if plan.window in ("T3M", "BOTH"):
        result["T3M"] = trailing_turnover_rate(panel, plan.department, 3, as_of)
    return result


def comparison(panel: pd.DataFrame, plan: QueryPlan, months: list) -> dict:
    current_index = len(months) - 1 - plan.current_offset
    baseline_index = current_index + (plan.baseline_offset or -1)
    current_month = months[current_index]
    baseline_month = months[baseline_index]
    window = 12 if plan.window != "T3M" else 3
    current = trailing_turnover_rate(panel, plan.department, window, current_month)
    baseline = trailing_turnover_rate(panel, plan.department, window, baseline_month)
    delta = None
    if current["rate"] is not None and baseline["rate"] is not None:
        delta = round(current["rate"] - baseline["rate"], 4)
    return {
        "department": plan.department or "Company-wide",
        "window": window,
        "current_month": str(current_month), "current": current,
        "baseline_month": str(baseline_month), "baseline": baseline,
        "change_in_rate": delta,
    }


def change_driver(panel: pd.DataFrame, months: list, window: int = 12) -> pd.DataFrame:
    """For each department, decompose the company-wide rate movement into
    (a) how much that department's own rate moved, and (b) how much that
    movement contributed to the overall change -- these are different
    questions. A small department can swing wildly on its own rate while
    barely moving the company number; a large department can move the
    company number a lot with only a modest rate change of its own.
    """
    current_month, baseline_month = months[-1], months[-2]
    rows = []
    total_headcount_current = panel[panel["month"] == current_month]["headcount"].sum()

    for dept in sorted(panel["department"].unique()):
        current = trailing_turnover_rate(panel, dept, window, current_month)
        baseline = trailing_turnover_rate(panel, dept, window, baseline_month)
        dept_headcount = panel[(panel["department"] == dept) & (panel["month"] == current_month)]["headcount"].sum()
        weight = dept_headcount / total_headcount_current if total_headcount_current else 0
        own_rate_change = (
            (current["rate"] - baseline["rate"])
            if current["rate"] is not None and baseline["rate"] is not None
            else None
        )
        contribution = own_rate_change * weight if own_rate_change is not None else None
        rows.append({
            "department": dept,
            "headcount_weight": round(weight, 3),
            "own_rate_change": round(own_rate_change, 4) if own_rate_change is not None else None,
            "contribution_to_company_change": round(contribution, 4) if contribution is not None else None,
        })

    df = pd.DataFrame(rows).sort_values("contribution_to_company_change", ascending=False, key=abs)
    return df.reset_index(drop=True)


def trend(panel: pd.DataFrame, plan: QueryPlan, months: list, lookback: int = 12) -> pd.DataFrame:
    window = 12 if plan.window != "T3M" else 3
    rows = []
    for m in months[-lookback:]:
        r = trailing_turnover_rate(panel, plan.department, window, m)
        rows.append({"month": str(m), "rate": r["rate"], "avg_headcount": r["avg_headcount"]})
    return pd.DataFrame(rows)
