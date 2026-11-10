"""Twelve months of bank transactions per application, written as messy raw CSVs.

The generator first builds the TRUE clean transactions, then renders each file in
one of two bank layouts and plants data problems on top. The truth and a manifest
of every planted problem go to the answer key, so tests can prove the pipeline
recovers the truth exactly.
"""
from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from creditlens.config import Settings
from creditlens.generators.common import counterparty_variant, format_inr, load_aliases, rng_for

ISSUES = ["mixed_date_formats", "currency_text_amounts", "duplicate_rows", "counterparty_variants",
          "missing_balance", "missing_description", "messy_headers"]
ALT_DATE_FORMATS = ["%Y-%m-%d", "%d-%m-%y", "%b %d, %Y", "%d.%m.%Y"]
CUSTOMERS = ["ARVIND TRADERS", "SHAKTI ENTERPRISES", "MERU DISTRIBUTORS", "KAVERI RETAIL",
             "SAGAR INDUSTRIES", "TAPTI LOGISTICS", "NIRMAL SERVICES", "AMAZON SELLER SERVICES",
             "RELIANCE RETAIL", "GANGA MANUFACTURING", "INDUS EXPORTS", "KONARK TRADERS"]
SUPPLIERS = ["VINDHYA STEEL", "MALABAR PACKAGING", "NILGIRI CHEMICALS", "HAMPI POLYMERS",
             "AJANTA FREIGHT", "GODAVARI MANUFACTURING", "BHARAT LOGISTICS", "SAHYADRI ENTERPRISES"]
FIXED_DEBITS = [("SALARY PAYROLL", "NEFT"), ("PREMISES RENT", "NEFT"), ("TATA POWER", "UPI"),
                ("GST PAYMENT", "NEFT")]
LENDER = "NORTHSTAR BANK"


def _month_starts(end_month: str, n: int) -> list[date]:
    y, m = map(int, end_month.split("-"))
    out = []
    for _ in range(n):
        out.insert(0, date(y, m, 1))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def _ref(rng) -> str:
    return f"N{rng.integers(10**9, 10**10 - 1)}"


def build_truth(app: dict, latest_revenue_000: int, weak: bool, s: Settings, rng) -> pd.DataFrame:
    months = _month_starts(s.statement_end_month, s.sizes.statement_months)
    customers = list(rng.choice(CUSTOMERS, int(rng.integers(4, 8)), replace=False))
    suppliers = list(rng.choice(SUPPLIERS, int(rng.integers(3, 6)), replace=False))
    monthly_inflow = latest_revenue_000 * 1000 / 12 * rng.uniform(0.55, 0.85)
    cash_share = rng.uniform(0.15, 0.35) if rng.random() < 0.25 else rng.uniform(0.0, 0.05)
    bounce_months = set(rng.choice(len(months), min(len(months), rng.poisson(2.5 if weak else 0.3)),
                                   replace=False).tolist())
    emi = round(monthly_inflow * rng.uniform(0.04, 0.09), 2)
    events = []  # (date, channel, counterparty, amount, is_bounce)

    def paise(x: float) -> float:
        return round(x + rng.integers(0, 100) / 100, 2)

    for mi, start in enumerate(months):
        days = 28
        inflow = monthly_inflow * rng.uniform(0.8, 1.2)
        cash = inflow * cash_share
        n_credits = int(rng.integers(6, 14))
        weights = rng.dirichlet(np.ones(n_credits))
        for w in weights:
            channel = str(rng.choice(["NEFT", "RTGS", "IMPS", "UPI", "CHQ"], p=[.4, .15, .15, .2, .1]))
            events.append((start + timedelta(days=int(rng.integers(0, days))), channel,
                           str(rng.choice(customers)), paise((inflow - cash) * w), False))
        for _ in range(int(rng.integers(1, 4)) if cash > 0 else 0):
            events.append((start + timedelta(days=int(rng.integers(0, days))), "CASH", "CASH",
                           paise(cash / 2), False))
        outflow = inflow * rng.uniform(0.86, 1.0)
        fixed_total = 0.0
        for cp, ch in FIXED_DEBITS:
            amt = paise(outflow * {"SALARY PAYROLL": .22, "PREMISES RENT": .05, "TATA POWER": .02,
                                   "GST PAYMENT": .06}[cp] * rng.uniform(.9, 1.1))
            fixed_total += amt
            events.append((start + timedelta(days=int(rng.integers(0, 6))), ch, cp, -amt, False))
        events.append((start + timedelta(days=4), "ACH", LENDER, -emi, False))
        n_debits = int(rng.integers(4, 10))
        for w in rng.dirichlet(np.ones(n_debits)):
            events.append((start + timedelta(days=int(rng.integers(0, days))),
                           str(rng.choice(["NEFT", "RTGS", "UPI"])), str(rng.choice(suppliers)),
                           -paise(max(outflow - fixed_total - emi, 1000) * w), False))
        if mi in bounce_months:
            d = start + timedelta(days=int(rng.integers(5, 20)))
            cp = str(rng.choice(customers))
            amt = paise(monthly_inflow * rng.uniform(0.03, 0.08))
            events.append((d, "CHQ", cp, amt, False))
            events.append((d + timedelta(days=2), "CHQ_RTN", cp, -amt, True))
            events.append((d + timedelta(days=2), "CHARGES", "BANK CHARGES", -590.0, False))

    events.sort(key=lambda e: (e[0], e[3] < 0))  # credits before debits on the same day
    balance = round(float(rng.uniform(2e5, 5e6)), 2)
    rows = []
    for seq, (d, ch, cp, amt, bounce) in enumerate(events):
        balance = round(balance + amt, 2)
        rows.append({"application_id": app["application_id"], "seq": seq, "txn_date": d.isoformat(),
                     "channel": ch, "counterparty": cp, "amount": round(amt, 2), "balance": balance,
                     "is_bounce": bounce, "ref_no": _ref(rng)})
    return pd.DataFrame(rows)


def _narration(channel: str, cp_text: str, ref: str) -> str:
    return {
        "UPI": f"UPI/{cp_text}/{ref[-6:]}",
        "NEFT": f"NEFT-{cp_text}-{ref}",
        "RTGS": f"RTGS/{cp_text}/{ref}",
        "IMPS": f"IMPS-{cp_text}-{ref[-6:]}",
        "CHQ": f"CHQ DEP {cp_text}",
        "CHQ_RTN": f"CHQ RTN {cp_text} INSUFFICIENT FUNDS",
        "ACH": f"ACH D- {cp_text} EMI",
        "CASH": "CASH DEPOSIT",
        "CHARGES": "CHGS CHQ RTN",
    }[channel]


def render_raw(truth: pd.DataFrame, issues: set[str], layout: str, rng, aliases) -> tuple[list[list[str]], dict]:
    """Render truth into raw rows for one bank layout, planting the chosen issues."""
    stats = {"alt_dates": 0, "currency_text": 0, "duplicates": 0, "missing_balance": 0,
             "missing_description": 0}
    blank_desc_seqs = set()
    body = []
    for i, r in truth.iterrows():
        d = date.fromisoformat(r.txn_date)
        fmt = "%d/%m/%Y" if layout == "A" else "%d-%b-%Y"
        if "mixed_date_formats" in issues and rng.random() < 0.3:
            fmt = str(rng.choice(ALT_DATE_FORMATS))
            stats["alt_dates"] += 1
        date_text = d.strftime(fmt)

        cp_text = r.counterparty
        if "counterparty_variants" in issues and r.channel not in ("CASH", "CHARGES"):
            cp_text = counterparty_variant(r.counterparty, rng, aliases)
        desc = _narration(r.channel, cp_text, r.ref_no)
        if ("missing_description" in issues and i > 0 and not r.is_bounce
                and r.channel not in ("CHQ", "CHARGES") and rng.random() < 0.04):
            desc = ""
            blank_desc_seqs.add(int(r.seq))
            stats["missing_description"] += 1

        def money(x: float) -> str:
            text = format_inr(abs(x))
            if "currency_text_amounts" in issues and rng.random() < 0.4:
                text = str(rng.choice(["₹", "INR ", "Rs. "])) + text
                stats["currency_text"] += 1
            return text

        bal = format_inr(r.balance)
        if "missing_balance" in issues and i > 0 and rng.random() < 0.08:
            bal = ""
            stats["missing_balance"] += 1
        if layout == "A":
            row = [date_text, r.ref_no, desc, money(r.amount) if r.amount < 0 else "",
                   money(r.amount) if r.amount > 0 else "", bal]
        else:
            row = [date_text, desc, money(r.amount), "Dr" if r.amount < 0 else "Cr", bal]
        body.append(row)

    if "duplicate_rows" in issues:
        n = int(rng.integers(1, 5))
        for idx in sorted(rng.choice(len(body), n, replace=False).tolist(), reverse=True):
            body.insert(idx + 1, list(body[idx]))
        stats["duplicates"] = n

    header = (["Date", "Ref No", "Description", "Debit", "Credit", "Balance"] if layout == "A"
              else ["Txn Date", "Narration", "Amount", "Dr/Cr", "Closing Balance"])
    if "messy_headers" in issues:
        header = [f"  {h.upper()} " if k % 2 else f"{h.lower()}  " for k, h in enumerate(header)]
    stats["blank_description_seqs"] = sorted(blank_desc_seqs)
    return [header] + body, stats


def render_statement_pdf(path: Path, company_name: str, truth: pd.DataFrame) -> None:
    styles = getSampleStyleSheet()
    rows = [["Date", "Narration", "Debit", "Credit", "Balance"]]
    for _, r in truth.iterrows():
        rows.append([date.fromisoformat(r.txn_date).strftime("%d/%m/%Y"),
                     _narration(r.channel, r.counterparty, r.ref_no)[:44],
                     format_inr(-r.amount) if r.amount < 0 else "",
                     format_inr(r.amount) if r.amount > 0 else "", format_inr(r.balance)])
    t = Table(rows, repeatRows=1, colWidths=[60, 210, 75, 75, 85])
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7.5),
                           ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                           ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
                           ("ALIGN", (2, 0), (-1, -1), "RIGHT")]))
    SimpleDocTemplate(str(path), pagesize=A4, title=f"{company_name} statement").build([
        Paragraph(f"Northstar Bank: account statement for {company_name}", styles["Heading2"]),
        Paragraph("Synthetic document generated for training.", styles["Italic"]),
        Spacer(1, 8), t])


def generate_bank_statements(applications: pd.DataFrame, fin_truth: dict, companies: pd.DataFrame,
                             out_dir: Path, s: Settings):
    """Write raw CSVs (and a few PDFs). Returns (truth DataFrame, issues manifest)."""
    rng = rng_for(s.seed, "bank_statements")
    aliases = load_aliases()
    names = companies.set_index("company_id")["legal_name"].to_dict()
    out_dir.mkdir(parents=True, exist_ok=True)
    apps = applications.to_dict("records")

    # Issue assignment: random 2-4 per file, then force coverage so every issue appears.
    assigned = [set(rng.choice(ISSUES, int(rng.integers(2, 5)), replace=False).tolist()) for _ in apps]
    for k, issue in enumerate(ISSUES):
        assigned[k % len(apps)].add(issue)
        assigned[(k + 9) % len(apps)].add(issue)
        assigned[(k + 18) % len(apps)].add(issue)

    all_truth, manifest = [], {}
    pdf_apps = {a["application_id"] for a in apps[: s.sizes.statement_pdfs]}
    for app, issues in zip(apps, assigned):
        if app["application_id"] in pdf_apps:
            issues.discard("missing_description")  # PDF statements always carry full narration
        fin = fin_truth[app["company_id"]]
        truth = build_truth(app, fin["years"]["FY2026"]["revenue"], fin["weak"], s, rng)
        layout = "A" if rng.random() < 0.5 else "B"
        rows, stats = render_raw(truth, issues, layout, rng, aliases)
        for seq in stats["blank_description_seqs"]:
            truth.loc[truth.seq == seq, ["channel", "counterparty"]] = "UNKNOWN"
        fname = f"{app['application_id']}_statement.csv"
        with open(out_dir / fname, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rows)
        if app["application_id"] in pdf_apps:
            render_statement_pdf(out_dir / f"{app['application_id']}_statement.pdf",
                                 names[app["company_id"]], truth)
        manifest[fname] = {"layout": layout, "issues": sorted(issues),
                           **{k: v for k, v in stats.items() if k != "blank_description_seqs"}}
        all_truth.append(truth)
    return pd.concat(all_truth, ignore_index=True), manifest
