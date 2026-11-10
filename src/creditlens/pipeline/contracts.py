"""Data contracts. A dataframe that fails a contract never moves to the next layer."""
from __future__ import annotations

import pandera.pandas as pa
from pandera.pandas import Check, Column, DataFrameSchema

CHANNELS = ["UPI", "NEFT", "RTGS", "IMPS", "CHQ", "CHQ_RTN", "ACH", "CASH", "CHARGES", "UNKNOWN"]


def _balance_is_continuous(df) -> bool:
    """Every balance equals the previous balance plus this row's amount (to the paisa)."""
    ok = True
    for _, g in df.groupby("application_id", sort=False):
        diff = (g["balance"].diff() - g["amount"]).iloc[1:].abs()
        ok &= bool((diff < 0.011).all())
    return ok


clean_transactions = DataFrameSchema(
    {
        "application_id": Column(str, Check.str_matches(r"^A\d{3}$")),
        "seq": Column(int, Check.ge(0)),
        "txn_date": Column("datetime64[ns]"),
        "channel": Column(str, Check.isin(CHANNELS)),
        "counterparty": Column(str, [Check.str_length(min_value=1),
                                     Check(lambda s: (s == s.str.upper()).all(), error="not upper case")]),
        "amount": Column(float, Check.ne(0)),
        "balance": Column(float, nullable=False),
        "is_bounce": Column(bool),
        "ref_no": Column(str, nullable=True),
        "source_file": Column(str),
    },
    checks=[
        Check(lambda df: not df.duplicated(["application_id", "seq"]).any(), error="duplicate seq"),
        Check(_balance_is_continuous, error="balance does not follow from amounts"),
        Check(lambda df: (df["is_bounce"] == (df["channel"] == "CHQ_RTN")).all(),
              error="is_bounce must match CHQ_RTN channel"),
    ],
    strict=True,
    coerce=True,
)

statement_features = DataFrameSchema(
    {
        "application_id": Column(str, unique=True),
        "months_covered": Column(int, Check.in_range(1, 24)),
        "total_credits": Column(float, Check.gt(0)),
        "total_debits": Column(float, Check.gt(0)),
        "avg_monthly_inflow": Column(float, Check.gt(0)),
        "inflow_volatility": Column(float, Check.ge(0)),
        "min_balance": Column(float),
        "avg_balance": Column(float),
        "cheque_returns_12m": Column(int, Check.ge(0)),
        "cash_credit_share": Column(float, Check.in_range(0, 1)),
        "monthly_emi_outflow": Column(float, Check.ge(0)),
        "top_customer_share": Column(float, Check.in_range(0, 1)),
        "unknown_txn_share": Column(float, Check.in_range(0, 1)),
    },
    strict=True,
    coerce=True,
)
