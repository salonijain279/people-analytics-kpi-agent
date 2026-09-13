"""Registry validation: the gate a Query Plan must pass before any
calculation runs.

A plan can be syntactically well-formed and still be wrong -- it might
reference a department that doesn't exist, ask for a change-driver
analysis without the two time periods that comparison requires, or combine
an analysis mode with an unsupported window. The registry is where those
checks live, kept separate from both the NL parser (which only guesses
intent) and the calculation engine (which assumes it's been handed
something valid). A failed check returns a clear reason instead of running
a calculation that might quietly produce a wrong or meaningless number.
"""
from dataclasses import dataclass

from query_plan import QueryPlan

REQUIRED_OFFSETS_BY_MODE = {
    "change_driver": True,
    "comparison": True,
    "trend": False,
    "snapshot": False,
}


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list


def validate_plan(plan: QueryPlan, known_departments: list) -> ValidationResult:
    errors = []

    if plan.department is not None and plan.department not in known_departments:
        errors.append(
            f"'{plan.department}' is not a recognized department. "
            f"Known departments: {', '.join(known_departments)}."
        )

    if plan.group_by is not None and plan.group_by != "department":
        errors.append(f"'{plan.group_by}' is not a supported group-by dimension.")

    if REQUIRED_OFFSETS_BY_MODE.get(plan.analysis_mode, False):
        if plan.baseline_offset is None:
            errors.append(
                f"Analysis mode '{plan.analysis_mode}' requires a comparison "
                f"period (baseline_offset), but none was resolved from the question."
            )

    if plan.window not in ("TTM", "T3M", "BOTH"):
        errors.append(f"'{plan.window}' is not a supported time window.")

    return ValidationResult(is_valid=not errors, errors=errors)
