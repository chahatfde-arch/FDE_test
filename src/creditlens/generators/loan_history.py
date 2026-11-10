"""Historical loans with outcomes, used to train the default-risk model in milestone 7.

Feature names match what the pipeline and extraction produce for new
applications, so the trained model can score them directly. Region has no
effect on the true default probability, which makes the Day 5 fairness check
meaningful: a model that leans on region has learned something false.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from creditlens.config import Settings
from creditlens.generators.common import rng_for
from creditlens.generators.registry import SECTORS

SECTOR_RISK = {"Manufacturing": 0.0, "Trading": 0.15, "Logistics": 0.1, "Food Processing": -0.05,
               "Textiles": 0.25, "IT Services": -0.2, "Construction": 0.35, "Healthcare": -0.15}


def generate_loan_history(s: Settings) -> pd.DataFrame:
    rng = rng_for(s.seed, "loan_history")
    n = s.sizes.loan_history_rows
    sector = rng.choice(SECTORS, n)
    region = rng.choice(list(s.regions), n)
    years = np.clip(rng.gamma(3, 3, n), 0.5, 40)
    dscr = np.clip(rng.normal(1.6, 0.5, n), 0.2, 4.5)
    lev = np.clip(rng.lognormal(np.log(2.2), 0.5, n), 0.2, 12)
    cr = np.clip(rng.normal(1.45, 0.4, n), 0.4, 4)
    bounces = rng.poisson(0.6, n)
    cash = np.clip(rng.beta(1.2, 12, n), 0, 0.9)
    inflow = rng.lognormal(np.log(4e6), 0.7, n)
    volatility = np.clip(rng.normal(0.22, 0.08, n), 0.03, 0.8)
    requested = (rng.integers(20, 600, n) * 100).astype(int)
    tenure = rng.choice([12, 24, 36, 48, 60], n)

    z = (-2.3 - 1.6 * (dscr - 1.5) + 0.35 * (lev - 2.2) - 0.9 * (cr - 1.4) + 0.45 * bounces
         + 2.0 * cash + 1.5 * (volatility - 0.22) - 0.05 * (years - 8)
         + np.vectorize(SECTOR_RISK.get)(sector) + rng.normal(0, 0.5, n))
    defaulted = (rng.random(n) < 1 / (1 + np.exp(-z))).astype(int)
    start = date(2019, 4, 1)
    return pd.DataFrame({
        "loan_id": [f"L{i + 1:05d}" for i in range(n)],
        "disbursed_on": [(start + timedelta(days=int(d))).isoformat() for d in rng.integers(0, 2200, n)],
        "sector": sector, "region": region,
        "years_in_business": years.round(2), "dscr": dscr.round(3), "debt_to_ebitda": lev.round(3),
        "current_ratio": cr.round(3), "cheque_returns_12m": bounces, "cash_credit_share": cash.round(4),
        "avg_monthly_inflow": inflow.round(2), "inflow_volatility": volatility.round(4),
        "requested_inr_000": requested, "tenure_months": tenure, "defaulted": defaulted,
    })
