"""Builds a monthly workforce panel from the public IBM HR Analytics Employee
Attrition dataset (1,470 real employee records: department, role, tenure,
and attrition status).

The source dataset is a single snapshot -- each employee has a tenure
(`YearsAtCompany`) and an attrition flag, but no explicit hire/exit dates.
To analyze turnover *trends* (which the source data doesn't directly
support), this module derives a plausible monthly timeline for each real
employee record: a hire month implied by their actual tenure, and -- for
employees who left -- an exit month placed within the observation window.
Headcount and termination counts are then aggregated by month and
department from these derived events.

This keeps every employee's real department, role, and attrition status
intact (nothing about *who* leaves or from *where* is invented), while
manufacturing the monthly grain needed to demonstrate trailing-window
turnover analysis. This is disclosed plainly here and in the README --
it is not real historical HR data with real dates, and shouldn't be read
as one.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

RAW_PATH = "data/raw/hr_employee_attrition.csv"
WINDOW_MONTHS = 30  # observation window length for the derived timeline
SEED = 42


@dataclass
class PanelResult:
    roster: pd.DataFrame
    monthly_panel: pd.DataFrame
    months: list


def load_roster(path: str = RAW_PATH) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    return df


def _month_range(n: int, end: pd.Period) -> list:
    return [end - i for i in range(n - 1, -1, -1)]


def build_monthly_panel(roster: pd.DataFrame, window_months: int = WINDOW_MONTHS,
                         seed: int = SEED) -> PanelResult:
    rng = np.random.default_rng(seed)
    end_month = pd.Period("2025-12", freq="M")
    months = _month_range(window_months, end_month)
    window_start = months[0]

    roster = roster.copy()
    roster["employee_id"] = roster["EmployeeNumber"]

    # A real employee's tenure implies a hire month; anyone hired before the
    # window just shows up as already active at window start.
    tenure_months = (roster["YearsAtCompany"].clip(lower=0) * 12).round().astype(int)
    hire_month_idx = window_months - tenure_months  # index into `months`, may be negative
    roster["hire_month"] = [
        months[max(i, 0)] if i < window_months else window_start
        for i in hire_month_idx
    ]

    # For employees who left (Attrition == Yes), place their exit somewhere
    # in the window after they were hired -- weighted toward the second half
    # of the window so the panel shows a visible, analyzable trend rather
    # than uniform noise.
    is_leaver = (roster["Attrition"] == "Yes").values
    exit_month = np.array([pd.NaT] * len(roster), dtype=object)
    for idx in np.where(is_leaver)[0]:
        hire = roster.iloc[idx]["hire_month"]
        hire_pos = months.index(hire) if hire in months else 0
        available = window_months - hire_pos
        if available <= 0:
            exit_month[idx] = months[-1]
            continue
        # skew toward later months in the employee's own tenure-in-window
        weights = np.linspace(0.4, 1.6, available)
        weights /= weights.sum()
        offset = rng.choice(available, p=weights)
        exit_month[idx] = months[hire_pos + offset]
    roster["exit_month"] = exit_month

    rows = []
    for month in months:
        active = roster[
            (roster["hire_month"] <= month)
            & (roster["exit_month"].isna() | (roster["exit_month"] >= month))
        ]
        terms = roster[roster["exit_month"] == month]
        for dept, dept_active in active.groupby("Department"):
            dept_terms = terms[terms["Department"] == dept]
            rows.append({
                "month": month,
                "department": dept,
                "headcount": len(dept_active),
                "terminations": len(dept_terms),
            })

    monthly_panel = pd.DataFrame(rows).sort_values(["department", "month"]).reset_index(drop=True)
    return PanelResult(roster=roster, monthly_panel=monthly_panel, months=months)


if __name__ == "__main__":
    roster = load_roster()
    result = build_monthly_panel(roster)
    result.monthly_panel.to_parquet("data/monthly_panel.parquet", index=False)
    print(f"Built monthly panel: {len(result.monthly_panel)} department-month rows, "
          f"{result.monthly_panel['department'].nunique()} departments, "
          f"{len(result.months)} months ({result.months[0]} to {result.months[-1]})")
