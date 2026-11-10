"""Generate every synthetic dataset from one seed.

Usage:
    python -m creditlens.generators            # writes into data/
    python -m creditlens.generators --skip-pdfs  # fast run, CSV and JSON only
"""
from __future__ import annotations

import argparse
import shutil
import time
from dataclasses import replace
from pathlib import Path

from creditlens.config import Settings, settings as default_settings
from creditlens.generators.applications import generate_applications
from creditlens.generators.bank_statements import generate_bank_statements
from creditlens.generators.common import write_json
from creditlens.generators.financials import generate_financials, write_financial_pdfs
from creditlens.generators.loan_history import generate_loan_history
from creditlens.generators.policy import expected_flags, write_policy
from creditlens.generators.registry import generate_registry


def generate_all(s: Settings = default_settings, skip_pdfs: bool = False, verbose: bool = True) -> Path:
    p = s.paths
    for folder in (p.raw, p.answer_key):
        if folder.exists():
            shutil.rmtree(folder)
    log = print if verbose else (lambda *a, **k: None)
    t0 = time.time()

    reg = generate_registry(s)
    reg_dir = p.raw / "registry"
    reg_dir.mkdir(parents=True)
    for name in ("companies", "directors", "company_directors", "users", "existing_loans"):
        reg[name].to_csv(reg_dir / f"{name}.csv", index=False)
    write_json(p.answer_key / "related_party_groups.json", reg["related_party_groups"])
    log(f"registry: {len(reg['companies'])} companies, {len(reg['directors'])} directors, "
        f"{len(reg['related_party_groups'])} hidden groups")

    apps = generate_applications(reg, s)
    (p.raw / "applications").mkdir(parents=True)
    apps.to_csv(p.raw / "applications" / "applications.csv", index=False)
    log(f"applications: {len(apps)}")

    fin = generate_financials(sorted(apps.company_id.unique()), s)
    write_json(p.answer_key / "financials_truth.json", fin)
    if not skip_pdfs:
        kinds = write_financial_pdfs(fin, reg["companies"], p.raw / "financials", s)
        write_json(p.answer_key / "financial_doc_kinds.json", kinds)
        log(f"financial statements: {len(kinds)} PDFs, "
            f"{sum(v != 'text' for v in kinds.values())} scanned")

    s_no_pdf = replace(s, sizes=replace(s.sizes, statement_pdfs=0)) if skip_pdfs else s
    txn_truth, manifest = generate_bank_statements(apps, fin, reg["companies"], p.raw / "statements", s_no_pdf)
    txn_truth.to_csv(p.answer_key / "transactions_truth.csv", index=False)
    write_json(p.answer_key / "statement_issues.json", manifest)
    log(f"bank statements: {len(manifest)} files, {len(txn_truth)} true transactions")

    write_policy(p.raw / "policy") if not skip_pdfs else (p.raw / "policy").mkdir(parents=True)
    flags = expected_flags(apps, reg["companies"], fin, txn_truth, reg["related_party_groups"],
                           reg["existing_loans"])
    write_json(p.answer_key / "expected_policy_flags.json", flags)
    log(f"policy: {sum(bool(v['flags']) for v in flags.values())} applications with exceptions")

    hist = generate_loan_history(s)
    (p.raw / "history").mkdir(parents=True)
    hist.to_csv(p.raw / "history" / "loan_history.csv", index=False)
    log(f"loan history: {len(hist)} loans, {hist.defaulted.sum()} defaults")
    log(f"done in {time.time() - t0:.1f}s -> {p.data}")
    return p.data


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", type=Path, help="write somewhere other than data/")
    ap.add_argument("--seed", type=int, default=default_settings.seed)
    ap.add_argument("--skip-pdfs", action="store_true")
    a = ap.parse_args()
    s = replace(default_settings, seed=a.seed)
    if a.data_root:
        s = replace(s, paths=s.paths.with_data_root(a.data_root))
    generate_all(s, skip_pdfs=a.skip_pdfs)


if __name__ == "__main__":
    main()
