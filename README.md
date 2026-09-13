# People Analytics KPI Investigation Agent

**Python, Streamlit, Plotly**

A conversational analytics agent for investigating workforce turnover: ask a
question in plain language, get a structured, auditable answer — never a
number a language model made up on its own.

## Problem

Turnover analysis usually means someone manually rebuilding the same cut of
data over and over: pick a department, pick a time window, filter, compute
a rate, compare it to last month, repeat for the next question. This
project standardizes that workflow into one governed pipeline with two
entry points — a user asking a question, or the system proactively
flagging a department worth investigating — that both route through the
same validated calculation path.

## Architecture

The core design decision: **a language model never computes a number.**
Its only job is to translate a question into a small, structured **Query
Plan** — a metric, a time window, an analysis mode, and a scope. A
separate, deterministic layer validates that plan against a registry of
known metrics and dimensions, then does the arithmetic in plain pandas.
This makes every answer traceable back to an explicit, inspectable plan
rather than an opaque model computation, and makes the validation layer
testable independent of any specific model.

```
Question ("Which department is driving the           Proactive scan (every department,
change in company-wide turnover?")                    every month, checking for an
        |                                              unusual upward move)
        v                                                      |
  NL -> Query Plan                                             v
  (rule-based parser here;                            Flagged department routed into
   swap in an LLM call for the                        the same change-driver plan
   same structured output)                                     |
        |                                                       |
        v                                                       v
  Registry validation  <---------------------------------------+
  (metric/window/dimension checks --
   fails closed with a clear reason,
   never guesses)
        |
        v
  Deterministic calculation (pandas)
  (TTM / T3M turnover rate, comparison, change-driver decomposition)
        |
        v
  Narrated result (plain-language summary of the
  calculated numbers -- narration never changes a value)
```

**Analysis modes:** snapshot, comparison (current vs. a prior period),
change-driver (which department's own rate movement contributed most to a
company-wide shift), and trend (a metric over a trailing lookback window).

**Guardrails:** an unrecognized department name triggers a clarification
warning rather than a silent guess; a small-headcount department is flagged
so a single termination isn't read as a meaningful trend; the registry
rejects a plan missing a required comparison period before any calculation
runs.

## Data

A public employee attrition dataset (1,470 real employee records:
department, job role, tenure, and whether each employee left). This is a
single snapshot, not a time series, so
`src/data_layer.py` derives a plausible monthly timeline from each
employee's real tenure and attrition status — a hire month implied by
tenure, and an exit month within a 30-month window for anyone who left.
**Every employee's real department, role, and attrition outcome is
preserved exactly; only the month each event falls in is constructed.**
`notebooks/01_data_layer.ipynb` verifies the derived panel accounts for
all 237 real leavers in the source data, exactly once each.

## Repo structure

```
people-analytics-kpi-agent/
├── data/raw/hr_employee_attrition.csv
├── notebooks/
│   ├── 01_data_layer.ipynb    builds and verifies the monthly panel
│   └── 02_agent_demo.ipynb    end-to-end pipeline demo, all analysis modes
├── src/
│   ├── data_layer.py          source data -> monthly workforce panel
│   ├── query_plan.py          Query Plan schema + rule-based NL parser
│   ├── registry.py            validates a plan before calculation runs
│   ├── calculation_engine.py  TTM/T3M turnover, comparison, change-driver
│   ├── signal_scan.py         proactive cross-department anomaly scan
│   └── agent.py                orchestrates parse -> validate -> calculate -> narrate
├── dashboard/app.py            Streamlit conversational UI (2 pages)
└── requirements.txt
```

## Setup

```bash
pip install -r requirements.txt
python src/data_layer.py        # builds data/monthly_panel.parquet
python src/agent.py             # runs example questions end to end
streamlit run dashboard/app.py  # interactive conversational UI
```

## Design notes

- The NL parser is intentionally rule-based rather than LLM-backed, so this
  repo runs with zero API keys or external dependencies. Swapping in an
  LLM call that emits the same `QueryPlan` fields is a drop-in replacement
  for `parse_question()` — nothing downstream (registry, calculation,
  narration) needs to change, which is the point of separating "understand
  the question" from "do the math."
- Change-driver decomposition distinguishes a department's **own rate
  movement** from its **contribution to the company-wide movement** — a
  small department can swing wildly on its own rate while barely moving
  the overall number, and a large department can move the overall number
  with only a modest rate change of its own. Conflating these is a common
  mistake in turnover reporting.

## Limitations

- The monthly panel is derived, not historically real — see the Data
  section above. Absolute turnover rates should be read as illustrative,
  not as real historical company figures.
- The rule-based NL parser handles the question patterns demonstrated here;
  it isn't a general-purpose language understanding system, and more
  varied phrasing would need either more parsing rules or the LLM swap
  described above.
- The proactive signal-scan threshold (1.5 percentage points month-over-
  month) is a fixed, illustrative cutoff, not calibrated against real
  historical volatility per department.
- This is a decision-support tool: it identifies rates, movements, and
  contributing populations. It does not infer *why* turnover changed —
  that interpretation still requires an analyst.
