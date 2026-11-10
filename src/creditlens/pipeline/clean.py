"""Raw bank statement CSV -> clean, validated transactions plus a quality report."""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from creditlens.pipeline.contracts import clean_transactions
from creditlens.pipeline.wrangle import (detect_layout, has_currency_text, normalize_counterparty,
                                         normalize_header, parse_amount, parse_date, parse_narration)

CANONICAL_HEADERS = {"A": ["Date", "Ref No", "Description", "Debit", "Credit", "Balance"],
                     "B": ["Txn Date", "Narration", "Amount", "Dr/Cr", "Closing Balance"]}
BASE_DATE_FORMAT = {"A": "%d/%m/%Y", "B": "%d-%b-%Y"}


@dataclass
class QualityReport:
    source_file: str
    layout: str
    rows_in: int = 0
    duplicates_removed: int = 0
    rows_out: int = 0
    messy_headers: bool = False
    alt_date_rows: int = 0
    currency_text_cells: int = 0
    balances_filled: int = 0
    missing_descriptions: int = 0
    unrecognized_narrations: int = 0


def read_raw(path: Path) -> tuple[list[str], list[list[str]]]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    return rows[0], rows[1:]


def clean_statement(path: Path, window: tuple[date, date]) -> tuple[pd.DataFrame, QualityReport]:
    path = Path(path)
    raw_header, body = read_raw(path)
    columns = [normalize_header(h) for h in raw_header]
    layout = detect_layout(columns)
    q = QualityReport(source_file=path.name, layout=layout, rows_in=len(body))
    q.messy_headers = raw_header != CANONICAL_HEADERS[layout]

    # 1. Exact duplicate rows. Real repeats differ at least in balance or reference.
    seen, unique_rows = set(), []
    for row in body:
        key = tuple(row)
        if key in seen:
            q.duplicates_removed += 1
            continue
        seen.add(key)
        unique_rows.append(row)
    df = pd.DataFrame(unique_rows, columns=columns)

    records = []
    for r in df.to_dict("records"):
        # 2. Dates in mixed formats.
        d, fmt = parse_date(r["txn_date"], window)
        q.alt_date_rows += fmt != BASE_DATE_FORMAT[layout]
        # 3. Amounts stored as text with currency symbols.
        money_cols = ["debit", "credit"] if layout == "A" else ["amount"]
        q.currency_text_cells += sum(has_currency_text(r[c]) for c in money_cols)
        if layout == "A":
            amount = (parse_amount(r["credit"]) or 0.0) - (parse_amount(r["debit"]) or 0.0)
        else:
            sign = -1.0 if r["drcr"].strip().lower() == "dr" else 1.0
            amount = sign * parse_amount(r["amount"])
        # 4. Narration -> channel + normalized counterparty.
        channel, cp_raw = parse_narration(r["narration"])
        q.missing_descriptions += channel == "UNKNOWN"
        q.unrecognized_narrations += channel == "OTHER"
        records.append({
            "txn_date": pd.Timestamp(d), "channel": channel,
            "counterparty": normalize_counterparty(cp_raw) if channel != "UNKNOWN" else "UNKNOWN",
            "amount": round(amount, 2), "balance": parse_amount(r["balance"]),
            "ref_no": (r.get("ref_no") or None),
        })

    # 5. Missing balances, rebuilt from the running total.
    for i, rec in enumerate(records):
        if rec["balance"] is None:
            q.balances_filled += 1
            if i > 0:
                rec["balance"] = round(records[i - 1]["balance"] + rec["amount"], 2)
    if records and records[0]["balance"] is None:  # first row: work back from the next known balance
        nxt = next(j for j, rec in enumerate(records) if rec["balance"] is not None)
        bal = records[nxt]["balance"]
        for j in range(nxt, 0, -1):
            bal = round(bal - records[j]["amount"], 2)
            records[j - 1]["balance"] = bal

    clean = pd.DataFrame(records)
    clean.insert(0, "application_id", path.name.split("_")[0])
    clean.insert(1, "seq", range(len(clean)))
    clean["is_bounce"] = clean["channel"] == "CHQ_RTN"
    clean["source_file"] = path.name
    clean = clean[["application_id", "seq", "txn_date", "channel", "counterparty", "amount", "balance",
                   "is_bounce", "ref_no", "source_file"]]
    q.rows_out = len(clean)
    return clean_transactions.validate(clean), q


def reports_frame(reports: list[QualityReport]) -> pd.DataFrame:
    return pd.DataFrame([asdict(r) for r in reports])
