import streamlit as st
import pandas as pd
from lib.data_loader import load_data
from lib.computations import compute_customer_aggregates
from lib.constants import TICKET_SIZE_RANGES

st.set_page_config(page_title="Customer Detail", layout="wide")
st.title("Customer Detail")

df = load_data()

# --- Sidebar Filters ---
st.sidebar.header("Filters")

gl_filter = st.sidebar.selectbox("GL Type", ["All", "Consumption", "IG"])
loan_mode = st.sidebar.selectbox("Loan Mode", ["All", "Solo RCPL", "Co-lending"])

# --- Customer Search / Selection ---
search = st.text_input(
    "Search Customer (ID, Name, or Phone)",
    placeholder="Enter custid, name, or phone...",
)

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
    selected = st.selectbox(
        "Select customer",
        matches,
        format_func=lambda x: f"{x} — {df[df['custid'] == x]['custname'].values[0]}",
    )
    st.session_state["selected_custid"] = selected
elif "selected_custid" in st.session_state:
    selected = st.session_state["selected_custid"]
else:
    st.info("Search for a customer or select one from the Customer Overview page.")
    st.stop()

# --- Customer Data (with filters applied) ---
cust_df = df[df["custid"] == selected].copy()
if cust_df.empty:
    st.error(f"No data found for customer {selected}")
    st.stop()

cust_name = cust_df["custname"].values[0]
phone = cust_df["primaryphone_decrypted"].values[0]
alt_phone = cust_df["alternatephone_decrypted"].values[0]

# --- Check Eligibility button at the TOP ---
st.header(f"{cust_name} ({selected})")
st.caption(f"Phone: {phone} | Alt Phone: {alt_phone}")

if st.button("Check Loan Eligibility →", type="primary"):
    st.session_state["selected_custid"] = selected
    st.switch_page("pages/3_Eligibility_Calculator.py")

st.divider()

# --- Apply filters to loan display ---
filtered_cust_df = cust_df.copy()
if gl_filter != "All":
    filtered_cust_df = filtered_cust_df[filtered_cust_df["gl_type"] == gl_filter]
if loan_mode == "Solo RCPL":
    filtered_cust_df = filtered_cust_df[~filtered_cust_df["is_colending"]]
elif loan_mode == "Co-lending":
    filtered_cust_df = filtered_cust_df[filtered_cust_df["is_colending"]]

if filtered_cust_df.empty:
    st.warning("No loans match the selected filters for this customer.")
    st.stop()

# --- Summary Cards (based on filtered loans) ---
agg = compute_customer_aggregates(filtered_cust_df)
row = agg.iloc[0]

col1, col2, col3 = st.columns(3)
col1.metric("Total RCPL Principal", f"₹{row['total_rcpl_principal']:,.0f}")
col2.metric("Principal Outstanding", f"₹{row['total_principal_outstanding']:,.0f}")
col3.metric("Interest Accrued", f"₹{row['total_interest_accrued']:,.0f}")

col4, col5, col6 = st.columns(3)
col4.metric("Current Outstanding", f"₹{row['total_current_outstanding']:,.0f}")
col5.metric("RCPL Gold Wt", f"{row['total_rcpl_gold_wt']:.2f} g")
col6.metric("Gold Value", f"₹{row['total_rcpl_gold_value']:,.0f}")

col7, col8, col9 = st.columns(3)
col7.metric("Current LTV", f"{row['current_ltv_pct']:.1f}%")
col8.metric("Maturity LTV", f"{row['maturity_ltv_pct']:.1f}%")
col9.metric("Active Loans", int(row["loan_count"]))

# --- Loan Level Table ---
st.divider()
st.subheader("Loan Details")

loan_cols = [
    "loanid", "sanctiondate", "sanctionedamount", "principalbalance",
    "interestamount", "interestrate", "tenure", "expirydate",
    "gl_type", "loantype", "core_net_wt", "rcpl_gold_wt", "rcpl_gold_value",
    "gold_rate_22k", "dpd", "days_remaining", "expected_interest_to_maturity",
    "schemename",
]

loan_display = filtered_cust_df[loan_cols].copy()
loan_display["sanctiondate"] = loan_display["sanctiondate"].dt.strftime("%Y-%m-%d")
loan_display["expirydate"] = loan_display["expirydate"].dt.strftime("%Y-%m-%d")

loan_display = loan_display.rename(columns={
    "loanid": "Loan ID",
    "sanctiondate": "Sanction Date",
    "sanctionedamount": "Sanctioned Amt",
    "principalbalance": "Principal O/S",
    "interestamount": "Interest",
    "interestrate": "Rate %",
    "tenure": "Tenure (M)",
    "expirydate": "Expiry",
    "gl_type": "GL Type",
    "loantype": "Loan Type",
    "core_net_wt": "Total Net Wt (g)",
    "rcpl_gold_wt": "RCPL Gold Wt (g)",
    "rcpl_gold_value": "RCPL Gold Value",
    "gold_rate_22k": "Gold Rate",
    "dpd": "DPD",
    "days_remaining": "Days to Maturity",
    "expected_interest_to_maturity": "Exp Interest to Maturity",
    "schemename": "Scheme",
})

st.dataframe(loan_display, use_container_width=True, hide_index=True)

# --- CLM Details ---
clm_loans = filtered_cust_df[filtered_cust_df["is_colending"]].copy()
if not clm_loans.empty:
    st.divider()
    st.subheader("Co-Lending (CLM) Details")

    clm_cols = [
        "loanid", "clm_bank", "clm_bankloanamount", "clm_outstanding_amt",
        "clm_interestrate", "clm_netweight", "clm_grossweight",
        "clm_appraisedamount",
    ]
    clm_display = clm_loans[clm_cols].rename(columns={
        "loanid": "Loan ID",
        "clm_bank": "Bank",
        "clm_bankloanamount": "Bank Loan Amt",
        "clm_outstanding_amt": "Bank O/S",
        "clm_interestrate": "Bank Rate %",
        "clm_netweight": "CLM Net Wt (g)",
        "clm_grossweight": "CLM Gross Wt (g)",
        "clm_appraisedamount": "Appraised Amt",
    })
    st.dataframe(clm_display, use_container_width=True, hide_index=True)
