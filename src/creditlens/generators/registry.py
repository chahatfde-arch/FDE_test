"""Company and director registry with hidden related-party groups.

Most companies have their own directors. A few groups of companies are secretly
linked through a shared director or a shared registered address, sometimes over
two or three hops. Pods find these on Day 3 with Cypher; the answer key lists them.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from creditlens.config import Settings
from creditlens.generators.common import faker_for, rng_for

SECTORS = [
    "Manufacturing", "Trading", "Logistics", "Food Processing", "Textiles",
    "IT Services", "Construction", "Healthcare",
]
EXCLUDED_SECTOR = "Online Betting"  # excluded by the fictional credit policy
NAME_STEMS = [
    "Arvind", "Shakti", "Nirmal", "Sagar", "Vikram", "Kaveri", "Meru", "Tapti",
    "Ganga", "Indus", "Sahyadri", "Narmada", "Aravali", "Konark", "Ajanta", "Hampi",
    "Vindhya", "Godavari", "Malabar", "Nilgiri",
]
NAME_ENDINGS = ["Industries", "Traders", "Logistics", "Foods", "Textiles", "Tech",
                "Builders", "Healthcare", "Enterprises", "Exports"]


def _pan(rng) -> str:
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    head = "".join(letters[i] for i in rng.integers(0, 26, 3)) + "P" + letters[rng.integers(0, 26)]
    return f"{head}{rng.integers(1000, 9999)}{letters[rng.integers(0, 26)]}"


def generate_registry(s: Settings) -> dict[str, pd.DataFrame | list]:
    rng = rng_for(s.seed, "registry")
    fake = faker_for(s.seed, "registry")
    n = s.sizes.companies

    # --- companies -------------------------------------------------------
    names_seen: set[str] = set()
    companies = []
    for i in range(n):
        while True:
            name = f"{NAME_STEMS[rng.integers(len(NAME_STEMS))]} {NAME_ENDINGS[rng.integers(len(NAME_ENDINGS))]}"
            if name not in names_seen:
                names_seen.add(name)
                break
        sector = SECTORS[rng.integers(len(SECTORS))]
        year = int(rng.integers(2005, 2025))
        companies.append({
            "company_id": f"C{i + 1:03d}",
            "legal_name": f"{name} Pvt Ltd",
            "sector": sector,
            "incorporated_on": date(year, int(rng.integers(1, 13)), int(rng.integers(1, 28))).isoformat(),
            "registered_address": fake.street_address().replace("\n", ", "),
            "city": fake.city(),
            "region": s.regions[rng.integers(len(s.regions))],
            "employees": int(rng.integers(8, 400)),
        })
    # One applicant in an excluded sector, one very young company: both trigger policy flags.
    companies[3]["sector"] = EXCLUDED_SECTOR
    companies[7]["incorporated_on"] = "2025-08-14"

    # --- directors: 1 to 3 unique directors per company ------------------
    directors, links = [], []
    def new_director() -> str:
        did = f"D{len(directors) + 1:03d}"
        directors.append({
            "director_id": did,
            "full_name": fake.name(),
            "pan": _pan(rng),
            "phone": f"+91 {rng.integers(70000, 99999)} {rng.integers(10000, 99999)}",
            "email": fake.free_email(),
            "residential_address": fake.address().replace("\n", ", "),
        })
        return did

    for c in companies:
        for k in range(int(rng.integers(1, 4))):
            links.append({
                "company_id": c["company_id"],
                "director_id": new_director(),
                "role": "Managing Director" if k == 0 else "Director",
                "appointed_on": c["incorporated_on"],
            })

    # --- hidden related-party groups -------------------------------------
    # Groups use companies from index 10 upward so companies 0-9 stay independent.
    pool = list(range(10, n))
    rng.shuffle(pool)
    groups = []
    for g in range(s.sizes.related_party_groups):
        size = int(rng.integers(2, 5))
        members = [companies[pool.pop()] for _ in range(size)]
        edges = []
        for a, b in zip(members, members[1:]):
            if rng.random() < 0.7:
                shared = next(l["director_id"] for l in links if l["company_id"] == a["company_id"])
                links.append({"company_id": b["company_id"], "director_id": shared,
                              "role": "Director", "appointed_on": b["incorporated_on"]})
                edges.append({"from": a["company_id"], "to": b["company_id"], "via": "shared_director",
                              "detail": shared})
            else:
                b["registered_address"] = a["registered_address"]
                edges.append({"from": a["company_id"], "to": b["company_id"], "via": "shared_address",
                              "detail": a["registered_address"]})
        groups.append({"group_id": f"G{g + 1}", "company_ids": [m["company_id"] for m in members],
                       "links": edges})

    # --- users for RBAC ----------------------------------------------------
    users = [{"user_id": f"U{i + 1:02d}", "full_name": fake.name(), "role": "analyst", "region": r}
             for i, r in enumerate(s.regions)]
    users.append({"user_id": "U05", "full_name": fake.name(), "role": "head_of_credit", "region": "ALL"})
    users.append({"user_id": "U06", "full_name": fake.name(), "role": "auditor", "region": "ALL"})

    # --- existing Kestrel exposure (needed for group exposure checks) -----
    existing = []
    for c in companies:
        if rng.random() < 0.35:
            existing.append({"company_id": c["company_id"],
                             "outstanding_inr_000": int(rng.integers(500, 12000)) * 10})

    return {
        "companies": pd.DataFrame(companies),
        "directors": pd.DataFrame(directors),
        "company_directors": pd.DataFrame(links),
        "users": pd.DataFrame(users),
        "existing_loans": pd.DataFrame(existing),
        "related_party_groups": groups,
    }
