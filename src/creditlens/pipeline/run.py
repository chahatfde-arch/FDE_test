"""Run the data pipeline: raw -> clean -> curated, then load the database.

Usage:
    python -m creditlens.pipeline            # write data/clean and data/curated
    python -m creditlens.pipeline --load     # also load the database in DATABASE_URL
"""
from __future__ import annotations

import argparse
import calendar
from datetime import date

import pandas as pd

from creditlens.config import Settings, settings as default_settings
from creditlens.pipeline.clean import clean_statement, reports_frame
from creditlens.pipeline.features import build_features
from creditlens.pipeline.load import load_all


def statement_window(s: Settings) -> tuple[date, date]:
    y, m = map(int, s.statement_end_month.split("-"))
    end = date(y, m, calendar.monthrange(y, m)[1])
    total = y * 12 + (m - 1) - (s.sizes.statement_months - 1)
    return date(total // 12, total % 12 + 1, 1), end


def run_pipeline(s: Settings = default_settings, load: bool = False, verbose: bool = True) -> dict:
    log = print if verbose else (lambda *a, **k: None)
    p = s.paths
    window = statement_window(s)
    cleaned, reports = [], []
    for path in sorted((p.raw / "statements").glob("*.csv")):
        df, q = clean_statement(path, window)
        cleaned.append(df)
        reports.append(q)
    tx = pd.concat(cleaned, ignore_index=True)
    quality = reports_frame(reports)
    features = build_features(tx)

    p.clean.mkdir(parents=True, exist_ok=True)
    p.curated.mkdir(parents=True, exist_ok=True)
    tx.to_csv(p.clean / "transactions.csv", index=False)
    quality.to_csv(p.clean / "quality_report.csv", index=False)
    features.to_csv(p.curated / "statement_features.csv", index=False)
    totals = quality.drop(columns=["source_file", "layout"]).sum(numeric_only=True)
    log(f"clean: {len(tx)} transactions from {len(reports)} files")
    log("fixed: " + ", ".join(f"{k}={int(v)}" for k, v in totals.items()
                               if k not in ("rows_in", "rows_out")))
    log(f"curated: {len(features)} feature rows")
    out = {"transactions": tx, "quality_report": quality, "statement_features": features}
    if load:
        tables = load_all(s.database_url, p.raw, out)
        log(f"loaded {len(tables)} tables into {s.database_url.split('@')[-1]}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--load", action="store_true", help="load tables into DATABASE_URL")
    run_pipeline(load=ap.parse_args().load)


if __name__ == "__main__":
    main()
