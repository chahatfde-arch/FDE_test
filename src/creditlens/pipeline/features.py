"""Clean transactions -> curated, one row of banking-conduct features per application.

Feature names match the loan history used to train the risk model in milestone 7.
"""
from __future__ import annotations

import pandas as pd

from creditlens.pipeline.contracts import statement_features


def build_features(tx: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for app_id, g in tx.groupby("application_id", sort=True):
        credits = g[g.amount > 0]
        debits = g[g.amount < 0]
        month = g.txn_date.dt.to_period("M")
        monthly_in = credits.groupby(month[credits.index]).amount.sum()
        months = int(month.nunique())
        # A returned cheque reverses an earlier credit, so it is netted out of inflow.
        returned = -g[g.is_bounce].amount.sum()
        real_credits = credits.amount.sum() - returned
        by_customer = credits[~credits.channel.isin(["CASH", "UNKNOWN"])].groupby("counterparty").amount.sum()
        rows.append({
            "application_id": app_id,
            "months_covered": months,
            "total_credits": round(float(credits.amount.sum()), 2),
            "total_debits": round(float(-debits.amount.sum()), 2),
            "avg_monthly_inflow": round(float(real_credits / months), 2),
            "inflow_volatility": round(float(monthly_in.std(ddof=0) / monthly_in.mean()), 4),
            "min_balance": round(float(g.balance.min()), 2),
            "avg_balance": round(float(g.balance.mean()), 2),
            "cheque_returns_12m": int(g.is_bounce.sum()),
            "cash_credit_share": round(float(credits[credits.channel == "CASH"].amount.sum()
                                             / credits.amount.sum()), 4),
            "monthly_emi_outflow": round(float(-g[g.channel == "ACH"].amount.sum() / months), 2),
            "top_customer_share": round(float(by_customer.max() / credits.amount.sum()), 4),
            "unknown_txn_share": round(float((g.channel == "UNKNOWN").mean()), 4),
        })
    return statement_features.validate(pd.DataFrame(rows))
