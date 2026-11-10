import hashlib
import json
from dataclasses import replace

import pandas as pd

from creditlens.config import settings
from creditlens.generators.generate_all import generate_all


def _digest(root):
    files = sorted(p for p in root.rglob("*") if p.suffix in {".csv", ".json", ".md"})
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def test_same_seed_same_data(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    for root in (a, b):
        generate_all(replace(settings, paths=settings.paths.with_data_root(root)), skip_pdfs=True,
                     verbose=False)
    assert _digest(a) == _digest(b)


def test_financial_identities_hold(s):
    truth = json.loads((s.paths.answer_key / "financials_truth.json").read_text())
    for company in truth.values():
        for y in company["years"].values():
            assert y["gross_profit"] == y["revenue"] - y["cogs"]
            assert y["ebitda"] == y["gross_profit"] - y["opex"]
            assert y["pbt"] == y["ebitda"] - y["depreciation"] - y["interest"]
            assert y["total_assets"] == y["total_liabilities_and_equity"]
            assert y["equity"] > 0


def test_related_party_groups_are_really_linked(s):
    links = pd.read_csv(s.paths.raw / "registry" / "company_directors.csv")
    companies = pd.read_csv(s.paths.raw / "registry" / "companies.csv").set_index("company_id")
    groups = json.loads((s.paths.answer_key / "related_party_groups.json").read_text())
    for g in groups:
        for e in g["links"]:
            if e["via"] == "shared_director":
                holders = set(links[links.director_id == e["detail"]].company_id)
                assert {e["from"], e["to"]} <= holders
            else:
                assert companies.loc[e["from"], "registered_address"] == companies.loc[e["to"], "registered_address"]


def test_every_issue_is_planted_somewhere(s):
    manifest = json.loads((s.paths.answer_key / "statement_issues.json").read_text())
    planted = {i for v in manifest.values() for i in v["issues"]}
    assert len(planted) == 7


def test_scanned_and_rotated_pdfs_exist(s):
    kinds = json.loads((s.paths.answer_key / "financial_doc_kinds.json").read_text())
    assert "scan_rotated" in kinds.values() and list(kinds.values()).count("scan") >= 2
    assert len(list((s.paths.raw / "financials").glob("*.pdf"))) == len(kinds)
