import os

DATA_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CSV_PATH = os.path.join(DATA_DIR, "rcpl_all_loans.csv")

LTV_BRACKETS = [
    (250_000, 0.85),
    (500_000, 0.80),
    (float("inf"), 0.75),
]

TICKET_SIZE_RANGES = [
    ("All", 0, float("inf")),
    ("< 50K", 0, 50_000),
    ("50K - 1L", 50_000, 100_000),
    ("1L - 2.5L", 100_000, 250_000),
    ("2.5L - 5L", 250_000, 500_000),
    ("5L - 10L", 500_000, 1_000_000),
    ("> 10L", 1_000_000, float("inf")),
]


def get_max_ltv(aggregate_principal: float) -> float:
    for limit, ltv in LTV_BRACKETS:
        if aggregate_principal < limit:
            return ltv
    return LTV_BRACKETS[-1][1]


def get_ltv_bracket_label(aggregate_principal: float) -> str:
    if aggregate_principal < 250_000:
        return "< 2.5L (85%)"
    elif aggregate_principal <= 500_000:
        return "2.5L - 5L (80%)"
    else:
        return "> 5L (75%)"
