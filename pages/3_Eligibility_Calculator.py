import streamlit as st
import pandas as pd
from lib.data_loader import load_data
from lib.computations import (
    get_customer_consumption_summary,
    eligibility_mode_a,
    eligibility_mode_b,
)
from lib.constants import get_ltv_bracket_label

st.set_page_config(page_title="Eligibility Calculator", layout="wide")
st.title("Consumption Loan Eligibility Calculator")

df = load_data()

# --- Customer Selection ---
search = st.text_input(
    "Search Customer (ID, Name, or Phone)",
    value=st.session_state.get("selected_custid", ""),
    placeholder="Enter custid, name, or phone...",
)

selected_custid = None
if search:
    search_lower = search.lower().strip()
    mask = (
        df["custid"].str.lower().str.contains(search_lower, na=False)
        | df["custname"].str.lower().str.contains(search_lower, na=False)
        | df["primaryphone_decrypted"].str.contains(search_lower, na=False)
        | df["alternatephone_decrypted"].str.contains(search_lower, na=False)
    )
    matches = df[mask]["custid"].unique()
    if len(matches) == 0:
        st.warning("No customers found.")
        st.stop()
    selected_custid = st.selectbox(
        "Select customer",
        matches,
        format_func=lambda x: f"{x} — {df[df['custid'] == x]['custname'].values[0]}",
    )

if not selected_custid:
    st.info("Search and select a customer to begin eligibility analysis.")
    st.stop()

# --- Current Customer Consumption Summary ---
summary = get_customer_consumption_summary(df, selected_custid)
cust_name = df[df["custid"] == selected_custid]["custname"].values[0]

st.header(f"{cust_name} ({selected_custid})")
st.subheader("Current Consumption Loan Position")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Consumption Loans", summary["loan_count"])
col2.metric("Total Consumption Principal", f"₹{summary['total_consumption_principal']:,.0f}")
col3.metric("Current Outstanding", f"₹{summary['total_current_outstanding']:,.0f}")
col4.metric("Maturity Outstanding", f"₹{summary['maturity_outstanding']:,.0f}")

col5, col6, col7 = st.columns(3)
col5.metric("RCPL Gold Wt (Consumption)", f"{summary['total_rcpl_gold_wt']:.2f} g")
col6.metric("Gold Value (Consumption)", f"₹{summary['total_rcpl_gold_value']:,.0f}")
current_ltv = (
    summary["maturity_outstanding"] / summary["total_rcpl_gold_value"] * 100
    if summary["total_rcpl_gold_value"] > 0
    else 0
)
col7.metric("Current Maturity LTV", f"{current_ltv:.1f}%")

st.divider()

# --- Scenario Analysis ---
st.subheader("Scenario Analysis")

# Gold rate input
latest_gold_rate = df[df["custid"] == selected_custid]["gold_rate_22k"].max()
gold_rate = st.number_input(
    "Gold Rate (₹/gram, 22K)",
    value=float(latest_gold_rate),
    min_value=1000.0,
    step=100.0,
)

# --- Scenario management ---
if "scenarios" not in st.session_state:
    st.session_state["scenarios"] = [0]
if "next_scenario_id" not in st.session_state:
    st.session_state["next_scenario_id"] = 1


def add_scenario():
    if len(st.session_state["scenarios"]) < 4:
        st.session_state["scenarios"].append(st.session_state["next_scenario_id"])
        st.session_state["next_scenario_id"] += 1


def remove_scenario(scenario_id):
    if len(st.session_state["scenarios"]) > 1:
        st.session_state["scenarios"] = [
            s for s in st.session_state["scenarios"] if s != scenario_id
        ]


st.button(
    "+ Add Scenario",
    on_click=add_scenario,
    disabled=len(st.session_state["scenarios"]) >= 4,
)

scenarios = st.session_state["scenarios"]
scenario_cols = st.columns(len(scenarios))

for idx, (sid, col) in enumerate(zip(scenarios, scenario_cols)):
    with col:
        # --- Header with remove button ---
        header_cols = st.columns([5, 1])
        with header_cols[0]:
            st.markdown(f"#### Scenario {idx + 1}")
        with header_cols[1]:
            if len(scenarios) > 1:
                st.button(
                    "✕",
                    key=f"remove_{sid}",
                    on_click=remove_scenario,
                    args=(sid,),
                    help="Remove this scenario",
                )

        # --- Inputs ---
        mode = st.radio(
            "Mode",
            ["Amount → Gold Wt", "Gold Wt → Amount"],
            key=f"mode_{sid}",
            horizontal=True,
        )

        roi = st.number_input(
            "RoI (Annual %)",
            value=26.5,
            min_value=0.1,
            max_value=100.0,
            step=0.1,
            key=f"roi_{sid}",
        )

        tenor = st.selectbox(
            "Tenor (Months)",
            [3, 6, 9, 12, 18, 24, 36],
            index=1,
            key=f"tenor_{sid}",
        )

        if mode == "Amount → Gold Wt":
            amount = st.number_input(
                "Requested Loan Amount (₹)",
                value=100000.0,
                min_value=1000.0,
                step=5000.0,
                key=f"amount_{sid}",
            )
            r = eligibility_mode_a(summary, amount, roi, tenor, gold_rate)
        else:
            gold_wt = st.number_input(
                "Gold Wt to Pledge (grams)",
                value=10.0,
                min_value=0.1,
                step=1.0,
                key=f"gold_wt_{sid}",
            )
            r = eligibility_mode_b(summary, gold_wt, roi, tenor, gold_rate)

        # --- Unified Results Display ---
        st.markdown("---")

        # Compliance banner
        if r["overall_compliant"]:
            st.success("COMPLIANT (Combined + Standalone)")
        elif r["combined_compliant"] and not r["new_loan_standalone_compliant"]:
            st.error("NOT COMPLIANT — New loan fails standalone check")
        elif not r["combined_compliant"] and r["new_loan_standalone_compliant"]:
            st.error("NOT COMPLIANT — Combined portfolio exceeds LTV")
        else:
            st.error("NOT COMPLIANT — Both combined and standalone fail")

        # Aggregate
        st.markdown(
            f"**Aggregate Outstanding:** ₹{r['aggregate_outstanding']:,.0f}  \n"
            f"**Max Allowed LTV:** {r['max_allowed_ltv_pct']:.0f}% "
            f"({get_ltv_bracket_label(r['aggregate_outstanding'])})"
        )

        st.markdown("---")

        # --- New Loan Details ---
        st.markdown("##### New Loan Details")
        st.markdown(
            f"| | |\n"
            f"|---|---|\n"
            f"| **Loan Amount** | ₹{r['new_loan_amount']:,.0f} |\n"
            f"| **Interest at Maturity** | ₹{r['new_loan_interest']:,.0f} |\n"
            f"| **Outstanding at Maturity** | ₹{r['new_loan_maturity_outstanding']:,.0f} |\n"
            f"| **Gold Wt** | {r['new_loan_gold_wt']:.2f} g |\n"
            f"| **Origination LTV %** | {r['new_loan_origination_ltv_pct']:.1f}% |\n"
            f"| **Maturity LTV %** | {r['new_loan_maturity_ltv_pct']:.1f}% |"
        )
        if r["new_loan_standalone_compliant"]:
            st.caption("Standalone: PASS")
        else:
            st.caption("Standalone: FAIL")

        st.markdown("---")

        # --- Aggregate Portfolio Details ---
        st.markdown("##### Aggregate Portfolio")
        st.markdown(
            f"| | Existing | Combined |\n"
            f"|---|---|---|\n"
            f"| **Maturity Outstanding** | ₹{r['existing_maturity_outstanding']:,.0f} "
            f"| ₹{r['combined_maturity_outstanding']:,.0f} |\n"
            f"| **Gold Wt** | {r['existing_gold_wt']:.2f} g "
            f"| {r['combined_gold_wt']:.2f} g |\n"
            f"| **Maturity LTV %** | {r['existing_maturity_ltv_pct']:.1f}% "
            f"| {r['combined_maturity_ltv_pct']:.1f}% |"
        )
