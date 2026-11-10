"""Loan applications. Each applicant company files one application."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from creditlens.config import Settings
from creditlens.generators.common import rng_for

PRODUCTS = ["Term Loan", "Working Capital", "Equipment Finance"]
TENURES = {"Term Loan": [36, 48, 60], "Working Capital": [12, 24], "Equipment Finance": [24, 36, 48]}
TENURE_BREACHES = {4: 36, 11: 60, 19: 36}  # application index -> tenure above the product maximum
PURPOSES = {
    "Term Loan": ["Factory expansion", "New warehouse", "Fleet expansion"],
    "Working Capital": ["Inventory build-up", "Receivables funding", "Seasonal demand"],
    "Equipment Finance": ["CNC machines", "Cold-storage units", "Packaging line"],
}


def choose_applicants(registry: dict, s: Settings) -> list[str]:
    """Pick applicant companies, making sure every planted test case is included."""
    rng = rng_for(s.seed, "applicants")
    companies = registry["companies"]["company_id"].tolist()
    must = {"C004", "C008"}  # excluded sector, too young
    for g in registry["related_party_groups"]:
        must.update(g["company_ids"][:2])  # at least two members of every group apply
    rest = [c for c in companies if c not in must]
    rng.shuffle(rest)
    chosen = sorted(must) + rest[: max(0, s.sizes.applications - len(must))]
    return sorted(chosen)


def generate_applications(registry: dict, s: Settings) -> pd.DataFrame:
    rng = rng_for(s.seed, "applications")
    companies = registry["companies"].set_index("company_id")
    links = registry["company_directors"]
    users = registry["users"]
    analyst_by_region = users[users.role == "analyst"].set_index("region")["user_id"].to_dict()

    rows = []
    for i, cid in enumerate(choose_applicants(registry, s)):
        product = PRODUCTS[rng.integers(len(PRODUCTS))]
        region = companies.loc[cid, "region"]
        md = links[(links.company_id == cid) & (links.role == "Managing Director")]["director_id"].iloc[0]
        rows.append({
            "application_id": f"A{i + 1:03d}",
            "company_id": cid,
            "region": region,
            "product": product,
            "purpose": PURPOSES[product][rng.integers(3)],
            "requested_inr_000": int(rng.integers(20, 600)) * 100,
            "tenure_months": int(rng.choice(TENURES[product])),
            "submitted_on": (date(2026, 10, 1) + timedelta(days=int(rng.integers(0, 30)))).isoformat(),
            "analyst_id": analyst_by_region[region],
            "guarantor_director_id": md,
        })
    df = pd.DataFrame(rows)
    for idx, tenure in TENURE_BREACHES.items():  # planted rule 6.1 breaches
        df.loc[idx, ["product", "tenure_months"]] = ["Working Capital", tenure]
        df.loc[idx, "purpose"] = PURPOSES["Working Capital"][0]
    return df
