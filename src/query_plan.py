"""Structured Query Plan: the contract between "what a user asked" and
"what gets calculated."

The core design idea (common to production text-to-analytics systems, not
specific to any one implementation): never let a language model compute a
number. Instead, the model's job is to turn a natural-language question
into a small, structured, *validated* plan -- a metric, a time window, an
analysis mode, and a scope. A separate, deterministic calculation layer
reads that plan and does the arithmetic. This makes the system testable
(the plan can be checked before anything runs) and auditable (every answer
traces back to an explicit plan, not an opaque model computation).

`parse_question` below is a small rule-based NL parser -- deliberately
dependency-free so this repository runs with no API key. Swapping in an
LLM here (e.g. having Claude or GPT emit the same QueryPlan JSON schema
from the question) is a drop-in replacement; the rest of the pipeline
(registry validation, calculation, narration) doesn't change.
"""
import re
from dataclasses import dataclass, field
from typing import Literal, Optional

AnalysisMode = Literal["snapshot", "trend", "comparison", "change_driver"]
Window = Literal["TTM", "T3M", "BOTH"]


@dataclass
class QueryPlan:
    metric: str = "voluntary_turnover"
    window: Window = "BOTH"
    analysis_mode: AnalysisMode = "snapshot"
    department: Optional[str] = None
    group_by: Optional[str] = None
    current_offset: int = 0
    baseline_offset: Optional[int] = None
    raw_question: str = ""
    warnings: list = field(default_factory=list)


def parse_question(question: str, known_departments: list) -> QueryPlan:
    """Rule-based NL -> QueryPlan parser.

    Recognizes window keywords (TTM/T3M), analysis-mode keywords (trend,
    compare/vs, driving/driver), and department names against the
    registered department list -- this last check is the same principle
    the registry re-validates later: never let free text stand in for a
    real dimension value without checking it against what's actually in
    the data.
    """
    q = question.lower()
    plan = QueryPlan(raw_question=question)

    if "t3m" in q or "three-month" in q or "3-month" in q or "3 month" in q:
        plan.window = "T3M"
    elif "ttm" in q or "twelve-month" in q or "trailing year" in q or "annual" in q:
        plan.window = "TTM"
    else:
        plan.window = "BOTH"

    if re.search(r"\bdriv(e|ing|er)\b", q) or "contribut" in q:
        plan.analysis_mode = "change_driver"
        plan.current_offset, plan.baseline_offset = 0, -1
    elif re.search(r"\bvs\b|\bcompar|versus", q):
        plan.analysis_mode = "comparison"
        plan.current_offset, plan.baseline_offset = 0, -1
    elif "trend" in q or "over time" in q or "last few months" in q:
        plan.analysis_mode = "trend"
    else:
        plan.analysis_mode = "snapshot"

    if re.search(r"which department|what department|by department", q):
        plan.group_by = "department"
    else:
        for dept in known_departments:
            if dept.lower() in q:
                plan.department = dept
                break
        else:
            plan.warnings.append(
                "No specific department recognized in the question -- "
                "defaulting to a company-wide view. Ask about a specific "
                "department by name for a scoped answer."
            )

    return plan
