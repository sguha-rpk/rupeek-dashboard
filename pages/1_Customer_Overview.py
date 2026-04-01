import streamlit as st
import pandas as pd
from lib.data_loader import load_data
from lib.computations import compute_customer_aggregates
from lib.constants import TICKET_SIZE_RANGES

st.set_page_config(page_title="Customer Overview", layout="wide")
st.title("Customer Overview")

df = load_data()

# --- Sidebar Filters ---
st.sidebar.header("Filters")

gl_filter = st.sidebar.selectbox("GL Type", ["All", "Consumption", "IG"])
loan_mode = st.sidebar.selectbox("Loan Mode", ["All", "Solo RCPL", "Co-lending"])
ticket_labels = [t[0] for t in TICKET_SIZE_RANGES]
ticket_filter = st.sidebar.selectbox("Ticket Size (Total Principal)", ticket_labels)

# Apply loan-level filters
filtered = df.copy()
if gl_filter != "All":
    filtered = filtered[filtered["gl_type"] == gl_filter]
if loan_mode == "Solo RCPL":
    filtered = filtered[~filtered["is_colending"]]
elif loan_mode == "Co-lending":
    filtered = filtered[filtered["is_colending"]]

# --- Search ---
search = st.text_input(
    "Search by Customer ID, Name, or Phone",
    placeholder="Enter custid, name, or phone number...",
)

# Compute aggregates
if filtered.empty:
    st.warning("No loans match the selected filters.")
    st.stop()

agg = compute_customer_aggregates(filtered)

# Apply ticket size filter
ticket_range = next(t for t in TICKET_SIZE_RANGES if t[0] == ticket_filter)
agg = agg[
    (agg["total_rcpl_principal"] >= ticket_range[1])
    & (agg["total_rcpl_principal"] < ticket_range[2])
]

# Apply search
if search:
    search_lower = search.lower().strip()
    mask = (
        agg["custid"].str.lower().str.contains(search_lower, na=False)
        | agg["custname"].str.lower().str.contains(search_lower, na=False)
        | agg["primaryphone"].str.contains(search_lower, na=False)
        | agg["alternatephone"].str.contains(search_lower, na=False)
    )
    agg = agg[mask]

if agg.empty:
    st.info("No customers match your search/filters.")
    st.stop()

# --- Summary metrics ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("Customers", f"{len(agg):,}")
col2.metric("Total Principal", f"₹{agg['total_rcpl_principal'].sum():,.0f}")
col3.metric("Total Outstanding", f"₹{agg['total_current_outstanding'].sum():,.0f}")
col4.metric(
    "Avg Current LTV",
    f"{agg['current_ltv_pct'].mean():.1f}%",
)

# --- Build display table with clickable links ---
display_df = agg[[
    "custid", "custname", "primaryphone", "loan_count",
    "total_rcpl_principal", "total_principal_outstanding",
    "total_interest_accrued", "total_current_outstanding",
    "total_rcpl_gold_wt", "current_ltv_pct", "maturity_ltv_pct",
]].copy()

# Format for display
display_df = display_df.rename(columns={
    "custid": "Customer ID",
    "custname": "Name",
    "primaryphone": "Phone",
    "loan_count": "Loans",
    "total_rcpl_principal": "Total Principal",
    "total_principal_outstanding": "Principal O/S",
    "total_interest_accrued": "Interest Accrued",
    "total_current_outstanding": "Current O/S",
    "total_rcpl_gold_wt": "Gold Wt (g)",
    "current_ltv_pct": "Current LTV %",
    "maturity_ltv_pct": "Maturity LTV %",
})

currency_cols = ["Total Principal", "Principal O/S", "Interest Accrued", "Current O/S"]
for col in currency_cols:
    display_df[col] = display_df[col].apply(lambda x: f"₹{x:,.0f}")

display_df["Gold Wt (g)"] = display_df["Gold Wt (g)"].apply(lambda x: f"{x:.2f}")
display_df["Current LTV %"] = display_df["Current LTV %"].apply(lambda x: f"{x:.1f}%")
display_df["Maturity LTV %"] = display_df["Maturity LTV %"].apply(lambda x: f"{x:.1f}%")

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    height=600,
    on_select="rerun",
    selection_mode="single-row",
    key="customer_table",
)

# --- Handle row selection for direct navigation ---
selection = st.session_state.get("customer_table", {})
selected_rows = selection.get("selection", {}).get("rows", [])

if selected_rows:
    row_idx = selected_rows[0]
    selected_custid = agg.iloc[row_idx]["custid"]
    selected_name = agg.iloc[row_idx]["custname"]
    st.session_state["selected_custid"] = selected_custid

    col_a, col_b = st.columns(2)
    with col_a:
        st.success(f"Selected: **{selected_name}** ({selected_custid})")
        st.page_link("pages/2_Customer_Detail.py", label="Go to Customer Detail →", icon="👤")
    with col_b:
        st.page_link("pages/3_Eligibility_Calculator.py", label="Check Eligibility →", icon="📊")
