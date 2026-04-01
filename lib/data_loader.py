import os
import pandas as pd
import streamlit as st
from lib.constants import CSV_PATH


def _process_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Apply type coercion, derived columns to raw CSV data."""
    numeric_cols = [
        "sanctionedamount", "principalbalance", "interestamount",
        "interestrate", "core_net_wt", "gold_rate_22k",
        "clm_bankloanamount", "clm_outstanding_amt", "clm_interestrate",
        "netweight", "grossweight", "outstandingbalance",
        "accuredpenalinterest", "dpd", "overdueamount",
        "clm_appraisedamount", "clm_netweight", "clm_grossweight",
        "core_gross_wt", "core_stone_wt", "core_adjusted_wt",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    date_cols = ["sanctiondate", "expirydate", "misfilerecorddate"]
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    df["tenure"] = pd.to_numeric(df["tenure"], errors="coerce").fillna(0).astype(int)
    df["clm_bank"] = df["clm_bank"].fillna("").str.strip()
    df["gl_type"] = df["gl_type"].fillna("").str.strip()
    df["custid"] = df["custid"].astype(str).str.strip()
    df["custname"] = df["custname"].fillna("").str.strip()
    df["primaryphone_decrypted"] = df["primaryphone_decrypted"].fillna("").astype(str).str.strip()
    df["alternatephone_decrypted"] = df["alternatephone_decrypted"].fillna("").astype(str).str.strip()
    df["loanid"] = df["loanid"].astype(str).str.strip()

    # Derived columns
    df["is_colending"] = df["clm_bank"] != ""
    df["total_loan_amount"] = df["sanctionedamount"] + df["clm_bankloanamount"]
    df["rcpl_share"] = df["sanctionedamount"] / df["total_loan_amount"].replace(0, 1)
    df["rcpl_gold_wt"] = df["rcpl_share"] * df["core_net_wt"]
    df["rcpl_gold_value"] = df["gold_rate_22k"] * df["rcpl_gold_wt"]

    # Expected interest to maturity (daily basis)
    days_remaining = (df["expirydate"] - df["misfilerecorddate"]).dt.days.clip(lower=0)
    df["days_remaining"] = days_remaining
    df["expected_interest_to_maturity"] = (
        df["principalbalance"] * (df["interestrate"] / 100) / 365 * days_remaining
    )

    return df


@st.cache_data
def _load_from_file(path: str) -> pd.DataFrame:
    return _process_dataframe(pd.read_csv(path))


@st.cache_data
def _load_from_bytes(data: bytes) -> pd.DataFrame:
    import io
    return _process_dataframe(pd.read_csv(io.BytesIO(data)))


def load_data() -> pd.DataFrame:
    """Load data from local CSV or uploaded file."""
    # Try local file first
    if os.path.exists(CSV_PATH):
        return _load_from_file(CSV_PATH)

    # Also check a data/ directory in the app root
    app_data_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "rcpl_all_loans.csv"
    )
    if os.path.exists(app_data_path):
        return _load_from_file(app_data_path)

    # Fall back to file upload
    if "uploaded_data" in st.session_state:
        return _load_from_bytes(st.session_state["uploaded_data"])

    st.warning("No data file found. Please upload the loan data CSV.")
    uploaded = st.file_uploader(
        "Upload rcpl_all_loans.csv",
        type=["csv"],
        help="Upload the RCPL loan data CSV file",
    )
    if uploaded is not None:
        st.session_state["uploaded_data"] = uploaded.getvalue()
        st.rerun()

    st.stop()
