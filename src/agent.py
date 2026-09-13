"""Orchestrator: question -> Query Plan -> registry validation -> deterministic
calculation -> narrated result. This is the whole pipeline in one function,
matching the architecture described in the README.
"""
import pandas as pd

from query_plan import parse_question
from registry import validate_plan
import calculation_engine as calc


def narrate(plan, result: dict) -> str:
    """Turns a calculation result into a plain-language summary. This never
    changes a number -- it only describes what's already in `result`."""
    dept = plan.department or "the company overall"
    if plan.analysis_mode == "snapshot":
        parts = []
        if "TTM" in result and result["TTM"]["rate"] is not None:
            parts.append(f"TTM voluntary turnover for {dept} is {result['TTM']['rate']:.1%}")
        if "T3M" in result and result["T3M"]["rate"] is not None:
            parts.append(f"T3M is {result['T3M']['rate']:.1%}")
        return " and ".join(parts) + f" as of {result['as_of_month']}."
    if plan.analysis_mode == "comparison":
        c, b = result["current"], result["baseline"]
        direction = "up" if (result["change_in_rate"] or 0) > 0 else "down"
        return (
            f"{dept} turnover moved {direction} from {b['rate']:.1%} in {result['baseline_month']} "
            f"to {c['rate']:.1%} in {result['current_month']} "
            f"({result['change_in_rate']:+.1%} pts)."
        )
    if plan.analysis_mode == "change_driver":
        top = result.iloc[0]
        return (
            f"{top['department']} contributed the most to the company-wide change "
            f"({top['contribution_to_company_change']:+.2%} pts), "
            f"with its own TTM rate moving {top['own_rate_change']:+.2%} pts."
        )
    return "See the result table for details."


def answer_question(question: str, panel: pd.DataFrame, months: list) -> dict:
    known_departments = sorted(panel["department"].unique())
    plan = parse_question(question, known_departments)
    validation = validate_plan(plan, known_departments)

    if not validation.is_valid:
        return {"plan": plan, "valid": False, "errors": validation.errors, "result": None, "narration": None}

    if plan.analysis_mode == "snapshot":
        result = calc.snapshot(panel, plan, months)
    elif plan.analysis_mode == "comparison":
        result = calc.comparison(panel, plan, months)
    elif plan.analysis_mode == "change_driver":
        result = calc.change_driver(panel, months)
    elif plan.analysis_mode == "trend":
        result = calc.trend(panel, plan, months)
    else:
        result = None

    narration = narrate(plan, result) if plan.analysis_mode != "trend" else "See the trend table."
    return {"plan": plan, "valid": True, "errors": [], "result": result, "narration": narration}


if __name__ == "__main__":
    from data_layer import load_roster, build_monthly_panel

    roster = load_roster()
    panel_result = build_monthly_panel(roster)
    panel, months = panel_result.monthly_panel, panel_result.months

    questions = [
        "What is the TTM voluntary turnover rate for Sales?",
        "How does Research & Development's turnover compare TTM vs last month?",
        "Which department is driving the change in company-wide turnover?",
        "What's the turnover rate for Marketing?",  # unknown department -> should error
    ]
    for q in questions:
        print(f"\nQ: {q}")
        out = answer_question(q, panel, months)
        if not out["valid"]:
            print("  INVALID:", out["errors"])
        else:
            print("  Plan:", out["plan"])
            print("  Narration:", out["narration"])
