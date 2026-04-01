import pandas as pd
from lib.constants import get_max_ltv, LTV_BRACKETS


def compute_customer_aggregates(df: pd.DataFrame) -> pd.DataFrame:
    agg = df.groupby("custid").agg(
        custname=("custname", "first"),
        primaryphone=("primaryphone_decrypted", "first"),
        alternatephone=("alternatephone_decrypted", "first"),
        loan_count=("loanid", "nunique"),
        total_rcpl_principal=("sanctionedamount", "sum"),
        total_principal_outstanding=("principalbalance", "sum"),
        total_interest_accrued=("interestamount", "sum"),
        total_rcpl_gold_wt=("rcpl_gold_wt", "sum"),
        total_rcpl_gold_value=("rcpl_gold_value", "sum"),
        total_expected_interest_maturity=("expected_interest_to_maturity", "sum"),
    ).reset_index()

    agg["total_current_outstanding"] = (
        agg["total_principal_outstanding"] + agg["total_interest_accrued"]
    )
    agg["current_ltv_pct"] = (
        agg["total_current_outstanding"]
        / agg["total_rcpl_gold_value"].replace(0, float("inf"))
        * 100
    )
    agg["maturity_outstanding"] = (
        agg["total_current_outstanding"] + agg["total_expected_interest_maturity"]
    )
    agg["maturity_ltv_pct"] = (
        agg["maturity_outstanding"]
        / agg["total_rcpl_gold_value"].replace(0, float("inf"))
        * 100
    )

    return agg


def get_customer_consumption_summary(df: pd.DataFrame, custid: str) -> dict:
    """Get consumption-only aggregates for a customer (used in eligibility)."""
    cust_df = df[(df["custid"] == custid) & (df["gl_type"] == "Consumption")]
    if cust_df.empty:
        return {
            "total_consumption_principal": 0,
            "total_principal_outstanding": 0,
            "total_interest_accrued": 0,
            "total_current_outstanding": 0,
            "total_expected_interest_maturity": 0,
            "maturity_outstanding": 0,
            "total_rcpl_gold_value": 0,
            "total_rcpl_gold_wt": 0,
            "loan_count": 0,
        }
    return {
        "total_consumption_principal": cust_df["sanctionedamount"].sum(),
        "total_principal_outstanding": cust_df["principalbalance"].sum(),
        "total_interest_accrued": cust_df["interestamount"].sum(),
        "total_current_outstanding": (
            cust_df["principalbalance"].sum() + cust_df["interestamount"].sum()
        ),
        "total_expected_interest_maturity": cust_df["expected_interest_to_maturity"].sum(),
        "maturity_outstanding": (
            cust_df["principalbalance"].sum()
            + cust_df["interestamount"].sum()
            + cust_df["expected_interest_to_maturity"].sum()
        ),
        "total_rcpl_gold_value": cust_df["rcpl_gold_value"].sum(),
        "total_rcpl_gold_wt": cust_df["rcpl_gold_wt"].sum(),
        "loan_count": cust_df["loanid"].nunique(),
    }


def _build_unified_result(
    summary: dict,
    new_amount: float,
    new_gold_wt: float,
    roi_annual_pct: float,
    tenor_months: int,
    gold_rate: float,
) -> dict:
    """Build a single unified result dict used by both Mode A and Mode B."""
    tenor_days = tenor_months * 30

    # --- New Loan ---
    new_interest = new_amount * (roi_annual_pct / 100) / 365 * tenor_days
    new_maturity_outstanding = new_amount + new_interest
    new_gold_value = gold_rate * new_gold_wt

    # New loan standalone LTV
    new_standalone_max_ltv = get_max_ltv(new_amount)
    new_origination_ltv = (
        new_amount / new_gold_value * 100 if new_gold_value > 0 else float("inf")
    )
    new_maturity_ltv = (
        new_maturity_outstanding / new_gold_value * 100
        if new_gold_value > 0
        else float("inf")
    )
    standalone_compliant = new_maturity_ltv <= new_standalone_max_ltv * 100

    # --- Existing ---
    existing_maturity_outstanding = summary["maturity_outstanding"]
    existing_gold_wt = summary["total_rcpl_gold_wt"]
    existing_gold_value = summary["total_rcpl_gold_value"]
    existing_maturity_ltv = (
        existing_maturity_outstanding / existing_gold_value * 100
        if existing_gold_value > 0
        else 0
    )

    # --- Combined ---
    aggregate_principal = summary["total_consumption_principal"] + new_amount
    max_allowed_ltv = get_max_ltv(aggregate_principal)

    combined_maturity_outstanding = existing_maturity_outstanding + new_maturity_outstanding
    combined_gold_wt = existing_gold_wt + new_gold_wt
    combined_gold_value = existing_gold_value + new_gold_value
    combined_maturity_ltv = (
        combined_maturity_outstanding / combined_gold_value * 100
        if combined_gold_value > 0
        else 0
    )
    combined_compliant = combined_maturity_ltv <= max_allowed_ltv * 100

    return {
        # Top-level
        "aggregate_principal": aggregate_principal,
        "max_allowed_ltv_pct": max_allowed_ltv * 100,
        "overall_compliant": combined_compliant and standalone_compliant,

        # New Loan
        "new_loan_amount": new_amount,
        "new_loan_interest": new_interest,
        "new_loan_maturity_outstanding": new_maturity_outstanding,
        "new_loan_gold_wt": new_gold_wt,
        "new_loan_gold_value": new_gold_value,
        "new_loan_origination_ltv_pct": new_origination_ltv,
        "new_loan_maturity_ltv_pct": new_maturity_ltv,
        "new_loan_standalone_max_ltv_pct": new_standalone_max_ltv * 100,
        "new_loan_standalone_compliant": standalone_compliant,

        # Existing
        "existing_maturity_outstanding": existing_maturity_outstanding,
        "existing_gold_wt": existing_gold_wt,
        "existing_gold_value": existing_gold_value,
        "existing_maturity_ltv_pct": existing_maturity_ltv,

        # Combined
        "combined_maturity_outstanding": combined_maturity_outstanding,
        "combined_gold_wt": combined_gold_wt,
        "combined_gold_value": combined_gold_value,
        "combined_maturity_ltv_pct": combined_maturity_ltv,
        "combined_compliant": combined_compliant,
    }


def eligibility_mode_a(
    summary: dict,
    new_amount: float,
    roi_annual_pct: float,
    tenor_months: int,
    gold_rate: float,
) -> dict:
    """Given requested amount, compute required gold weight to pledge."""
    tenor_days = tenor_months * 30
    new_interest = new_amount * (roi_annual_pct / 100) / 365 * tenor_days
    new_maturity = new_amount + new_interest

    # Aggregate bracket
    aggregate_principal = summary["total_consumption_principal"] + new_amount
    max_ltv = get_max_ltv(aggregate_principal)

    # Combined constraint: gold needed for combined portfolio
    total_maturity = summary["maturity_outstanding"] + new_maturity
    required_combined_gold_value = total_maturity / max_ltv
    existing_gold_value = summary["total_rcpl_gold_value"]
    additional_combined = max(0, required_combined_gold_value - existing_gold_value)
    gold_wt_combined = additional_combined / gold_rate if gold_rate > 0 else 0

    # Standalone constraint: new loan alone must comply
    standalone_max_ltv = get_max_ltv(new_amount)
    standalone_required_gold_value = new_maturity / standalone_max_ltv
    gold_wt_standalone = standalone_required_gold_value / gold_rate if gold_rate > 0 else 0

    # Take the stricter (larger gold wt)
    new_gold_wt = max(gold_wt_combined, gold_wt_standalone)

    return _build_unified_result(
        summary, new_amount, new_gold_wt, roi_annual_pct, tenor_months, gold_rate
    )


def eligibility_mode_b(
    summary: dict,
    gold_wt_to_pledge: float,
    roi_annual_pct: float,
    tenor_months: int,
    gold_rate: float,
) -> dict:
    """Given gold weight to pledge, compute max loan amount."""
    new_gold_value = gold_wt_to_pledge * gold_rate
    total_gold_value = summary["total_rcpl_gold_value"] + new_gold_value
    existing_maturity = summary["maturity_outstanding"]
    existing_principal = summary["total_consumption_principal"]
    tenor_days = tenor_months * 30
    interest_factor = 1 + (roi_annual_pct / 100) / 365 * tenor_days

    best_amount = 0

    for bracket_limit, ltv in LTV_BRACKETS:
        # Combined constraint
        headroom = total_gold_value * ltv - existing_maturity
        if headroom <= 0:
            continue
        max_amount_combined = headroom / interest_factor

        # Standalone constraint: iterate to consistent bracket
        max_amount_standalone = new_gold_value * get_max_ltv(max_amount_combined) / interest_factor
        max_amount = min(max_amount_combined, max_amount_standalone)

        for _ in range(5):
            new_standalone_ltv = get_max_ltv(max_amount)
            max_amount_standalone = new_gold_value * new_standalone_ltv / interest_factor
            max_amount = min(max_amount_combined, max_amount_standalone)
            if get_max_ltv(max_amount) == new_standalone_ltv:
                break

        aggregate = existing_principal + max_amount
        actual_ltv = get_max_ltv(aggregate)

        if actual_ltv == ltv or max_amount <= max_amount_standalone:
            if max_amount > best_amount:
                best_amount = max_amount

    new_amount = max(0, best_amount)

    return _build_unified_result(
        summary, new_amount, gold_wt_to_pledge, roi_annual_pct, tenor_months, gold_rate
    )
