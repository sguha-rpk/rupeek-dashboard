import streamlit as st

st.set_page_config(
    page_title="Rupeek Capital Dashboard",
    page_icon=":coin:",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Rupeek Capital Gold Loan Dashboard")
st.markdown(
    """
    Navigate using the sidebar:
    - **Customer Overview** — Aggregate view with filters and search
    - **Customer Detail** — Loan-level drill-down
    - **Eligibility Calculator** — Scenario analysis for new consumption loans
    """
)

# Preload data
from lib.data_loader import load_data

df = load_data()
st.metric("Total Active Loans", f"{len(df):,}")
st.metric("Unique Customers", f"{df['custid'].nunique():,}")
