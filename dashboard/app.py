"""People Analytics Conversational KPI Agent -- Streamlit demo.

Two pages, matching the two entry points into the same investigation
pipeline: Ask a Question (question-first) and Signal Scan (proactive,
signal-first). Both route through the same parse -> validate -> calculate
-> narrate pipeline in src/agent.py.
"""
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from data_layer import load_roster, build_monthly_panel  # noqa: E402
from agent import answer_question  # noqa: E402
from signal_scan import scan_for_signals  # noqa: E402
import calculation_engine as calc  # noqa: E402

st.set_page_config(page_title="People Analytics KPI Agent", layout="wide")


@st.cache_resource
def load_panel():
    roster = load_roster(str(ROOT / "data" / "raw" / "hr_employee_attrition.csv"))
    result = build_monthly_panel(roster)
    return result.monthly_panel, result.months


def page_ask(panel, months):
    st.title("Ask a Question")
    st.caption(
        "Question-first workflow: a plain-language question is turned into a structured, "
        "validated Query Plan before any number is calculated."
    )

    examples = [
        "What is the TTM voluntary turnover rate for Sales?",
        "How does Research & Development's turnover compare TTM vs last month?",
        "Which department is driving the change in company-wide turnover?",
        "Show me the T3M turnover trend for Human Resources",
    ]
    question = st.selectbox("Try an example, or type your own below", ["(type your own)"] + examples)
    if question == "(type your own)":
        question = st.text_input("Your question", "What is the TTM voluntary turnover rate for Sales?")

    if st.button("Ask") or question:
        out = answer_question(question, panel, months)

        with st.expander("Query Plan (what the question was parsed into)", expanded=True):
            st.json({k: v for k, v in vars(out["plan"]).items()})

        if not out["valid"]:
            st.error("Plan failed validation:")
            for e in out["errors"]:
                st.write(f"- {e}")
            return

        if out["plan"].warnings:
            for w in out["plan"].warnings:
                st.warning(w)

        st.success(out["narration"])

        result = out["result"]
        if isinstance(result, pd.DataFrame):
            st.dataframe(result, use_container_width=True)
            if out["plan"].analysis_mode == "trend":
                fig = px.line(result, x="month", y="rate", title="Turnover rate trend", markers=True)
                fig.update_layout(yaxis_tickformat=".1%")
                st.plotly_chart(fig, use_container_width=True)
            elif out["plan"].analysis_mode == "change_driver":
                fig = px.bar(result, x="department", y="contribution_to_company_change",
                             title="Contribution to company-wide turnover change")
                st.plotly_chart(fig, use_container_width=True)
        elif isinstance(result, dict):
            st.json(result)


def page_signal_scan(panel, months):
    st.title("Proactive Signal Scan")
    st.caption(
        "Signal-first workflow: scans every department for an unusual month-over-month "
        "increase in trailing turnover, and routes flagged departments into the same "
        "change-driver investigation a user would reach by asking about them directly."
    )

    signals = scan_for_signals(panel, months)
    st.dataframe(
        signals.style.format({"current_ttm_rate": "{:.1%}", "prior_ttm_rate": "{:.1%}", "move": "{:+.1%}"}),
        use_container_width=True,
    )

    flagged = signals[signals["flagged"]]
    if len(flagged):
        st.subheader("Flagged departments -> auto-routed into change-driver view")
        drivers = calc.change_driver(panel, months)
        st.dataframe(drivers, use_container_width=True)
    else:
        st.info("No departments crossed the upward-move threshold this month.")


def main():
    panel, months = load_panel()
    st.sidebar.title("People Analytics KPI Agent")
    page = st.sidebar.radio("Page", ["Ask a Question", "Proactive Signal Scan"])
    st.sidebar.divider()
    st.sidebar.caption(
        "Data: a public employee attrition dataset (1,470 employees). "
        "Monthly headcount/termination panel is derived from each employee's real "
        "tenure and attrition status -- see the README for exactly how."
    )

    if page == "Ask a Question":
        page_ask(panel, months)
    else:
        page_signal_scan(panel, months)


if __name__ == "__main__":
    main()
