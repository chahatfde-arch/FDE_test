"""Kestrel Finance credit policy manual (fictional) and the expected policy flags.

The thresholds below are invented for training. The same constants drive the
policy text and the expected flags, so the answer key can never drift from the
manual that pods retrieve from on Day 3.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

RULES = {
    "MIN_YEARS_IN_BUSINESS": 2,
    "EXCLUDED_SECTORS": ["Online Betting", "Speculative Real Estate", "Tobacco"],
    "MIN_DSCR": 1.25,
    "MAX_DEBT_TO_EBITDA": 3.5,
    "MIN_CURRENT_RATIO": 1.1,
    "MAX_CHEQUE_RETURNS_12M": 2,
    "MAX_CASH_CREDIT_SHARE": 0.30,
    "MAX_GROUP_EXPOSURE_INR_000": 120000,
    "MAX_TENURE_MONTHS": {"Working Capital": 24, "Equipment Finance": 48, "Term Loan": 60},
}


def policy_markdown() -> str:
    r = RULES
    tenure = "; ".join(f"{k}: up to {v} months" for k, v in r["MAX_TENURE_MONTHS"].items())
    return f"""# Kestrel Finance Credit Policy Manual

Version 3.2, effective 1 April 2026. Fictional policy written for the CreditLens AI training project.

## 1. Purpose and scope

This manual sets the minimum standards for lending to small and mid-sized businesses. It applies to every term loan, working capital facility and equipment finance facility. Credit analysts prepare the credit memo, and an underwriter makes the final decision. No automated system may approve or decline an application on its own.

## 2. Eligibility

2.1 The applicant must have completed at least {r['MIN_YEARS_IN_BUSINESS']} full years since incorporation on the date the application is submitted.

2.2 Kestrel Finance does not lend to businesses in these sectors: {', '.join(r['EXCLUDED_SECTORS'])}. No exception is possible under rule 2.2.

## 3. Financial thresholds

All ratios use the latest audited fiscal year.

3.1 Debt service coverage ratio (DSCR) must be at least {r['MIN_DSCR']}x. DSCR is EBITDA divided by the sum of finance costs and scheduled principal repayment for the year.

3.2 Total borrowings divided by EBITDA must not exceed {r['MAX_DEBT_TO_EBITDA']}x.

3.3 Current ratio must be at least {r['MIN_CURRENT_RATIO']}x. Current ratio is total current assets divided by trade payables and other current liabilities.

## 4. Banking conduct

Banking conduct is assessed on the last 12 months of statements from the applicant's main operating account.

4.1 Cheques returned for insufficient funds must not exceed {r['MAX_CHEQUE_RETURNS_12M']} in the 12 months.

4.2 Cash deposits must not exceed {int(r['MAX_CASH_CREDIT_SHARE'] * 100)} percent of total credits by value. A higher share needs an explanation from the applicant and a field visit.

## 5. Related parties and group exposure

5.1 A group is any set of companies linked by a common director or a common registered address, directly or through a chain of such links.

5.2 Total exposure to a group, meaning existing outstanding loans plus all pending requests from group members, must not exceed INR {r['MAX_GROUP_EXPOSURE_INR_000']:,} thousand.

5.3 The credit memo must list every group member and its exposure, even when the limit is not breached.

## 6. Product rules

6.1 Maximum tenure by product: {tenure}.

6.2 Personal guarantees from the managing director are required for every facility.

## 7. Exceptions

7.1 Any breach of sections 3 to 6 is a policy exception.

7.2 Every exception must be raised as a ticket in the Jira project CREDIT before the memo goes to the underwriter. The ticket names the rule, the measured value and the analyst's justification.

7.3 Only the Head of Credit can approve an exception. Analysts cannot approve exceptions on their own applications.

## 8. Data handling

8.1 Borrower personal data, including PAN, phone numbers, email addresses and residential addresses, must be masked before it is sent to any external system, including AI models.

8.2 Analysts may access applications from their own region only. The Head of Credit may access all regions. Auditors have read-only access to all regions.

## 9. Credit memo structure

Every memo has these sections in order: applicant summary; facility requested; financial analysis with DSCR, leverage and current ratio; banking conduct; related parties and group exposure; risk score with its main drivers; policy exceptions; recommendation for the underwriter.
"""


def write_policy(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    md = policy_markdown()
    (out_dir / "credit_policy_manual.md").write_text(md)
    styles = getSampleStyleSheet()
    story = []
    for block in md.strip().split("\n\n"):
        if block.startswith("# "):
            story.append(Paragraph(block[2:], styles["Title"]))
        elif block.startswith("## "):
            story.append(Paragraph(block[3:], styles["Heading2"]))
        else:
            story.append(Paragraph(block, styles["Normal"]))
        story.append(Spacer(1, 6))
    SimpleDocTemplate(str(out_dir / "credit_policy_manual.pdf"), pagesize=A4,
                      title="Kestrel Finance Credit Policy Manual").build(story)


def expected_flags(applications: pd.DataFrame, companies: pd.DataFrame, fin_truth: dict,
                   txn_truth: pd.DataFrame, groups: list, existing: pd.DataFrame) -> dict:
    """Which rules each application breaches, computed from the truth."""
    r = RULES
    comp = companies.set_index("company_id")
    outstanding = existing.set_index("company_id")["outstanding_inr_000"].to_dict() if len(existing) else {}
    requested = applications.groupby("company_id")["requested_inr_000"].sum().to_dict()
    group_of = {cid: g for g in groups for cid in g["company_ids"]}
    out = {}
    for a in applications.to_dict("records"):
        cid, flags, measured = a["company_id"], [], {}
        inc = date.fromisoformat(comp.loc[cid, "incorporated_on"])
        sub = date.fromisoformat(a["submitted_on"])
        years = (sub - inc).days / 365.25
        measured["years_in_business"] = round(years, 2)
        if years < r["MIN_YEARS_IN_BUSINESS"]:
            flags.append("2.1")
        if comp.loc[cid, "sector"] in r["EXCLUDED_SECTORS"]:
            flags.append("2.2")
        fy = fin_truth[cid]["years"]["FY2026"]
        dscr = fy["ebitda"] / (fy["interest"] + fy["principal_repayment"])
        lev = fy["total_debt"] / fy["ebitda"] if fy["ebitda"] > 0 else float("inf")
        cr = fy["current_assets"] / fy["current_liabilities"]
        measured.update(dscr=round(dscr, 3), debt_to_ebitda=round(lev, 3), current_ratio=round(cr, 3))
        if dscr < r["MIN_DSCR"]:
            flags.append("3.1")
        if lev > r["MAX_DEBT_TO_EBITDA"]:
            flags.append("3.2")
        if cr < r["MIN_CURRENT_RATIO"]:
            flags.append("3.3")
        t = txn_truth[txn_truth.application_id == a["application_id"]]
        bounces = int(t.is_bounce.sum())
        credits = t[t.amount > 0]
        cash_share = credits[credits.channel == "CASH"].amount.sum() / credits.amount.sum()
        measured.update(cheque_returns_12m=bounces, cash_credit_share=round(float(cash_share), 4))
        if bounces > r["MAX_CHEQUE_RETURNS_12M"]:
            flags.append("4.1")
        if cash_share > r["MAX_CASH_CREDIT_SHARE"]:
            flags.append("4.2")
        if cid in group_of:
            members = group_of[cid]["company_ids"]
            exposure = sum(outstanding.get(m, 0) + requested.get(m, 0) for m in members)
            measured.update(group_id=group_of[cid]["group_id"], group_exposure_inr_000=int(exposure))
            if exposure > r["MAX_GROUP_EXPOSURE_INR_000"]:
                flags.append("5.2")
        if a["tenure_months"] > r["MAX_TENURE_MONTHS"][a["product"]]:
            flags.append("6.1")
        out[a["application_id"]] = {"company_id": cid, "flags": flags, "measured": measured}
    return out


def policy_sections(md: str | None = None) -> list[tuple[str, str]]:
    """Split the manual into (section heading, text) pairs. Handy for chunking checks later."""
    md = md or policy_markdown()
    parts = re.split(r"^## ", md, flags=re.M)[1:]
    return [(p.split("\n", 1)[0].strip(), p.split("\n", 1)[1].strip()) for p in parts]
