"""Three years of financial statements per applicant, as PDFs.

All amounts are whole numbers in INR thousands ("INR '000"), which is what the
PDF shows too. A share of the PDFs are turned into noisy, slightly rotated
"scans" so Day 2 extraction has to go through OCR. One scan has its page 2
rotated 90 degrees: that is the Day 2 curveball.
"""
from __future__ import annotations

import io
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageFilter
from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (Image as RLImage, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

from creditlens.config import Settings
from creditlens.generators.common import format_inr, rng_for

rl_config.invariant = 1  # byte-identical PDFs for the same seed

FISCAL_YEARS = ["FY2024", "FY2025", "FY2026"]  # FY2026 = Apr 2025 to Mar 2026

PNL_LINES = [("revenue", "Revenue from operations"), ("cogs", "Cost of goods sold"),
             ("gross_profit", "Gross profit"), ("opex", "Operating expenses"),
             ("ebitda", "EBITDA"), ("depreciation", "Depreciation"),
             ("interest", "Finance costs"), ("pbt", "Profit before tax"),
             ("tax", "Tax expense"), ("pat", "Profit after tax")]
BS_LINES = [("cash", "Cash and bank"), ("receivables", "Trade receivables"),
            ("inventory", "Inventory"), ("current_assets", "Total current assets"),
            ("fixed_assets", "Net fixed assets"), ("total_assets", "Total assets"),
            ("current_liabilities", "Trade payables and other current liabilities"),
            ("total_debt", "Total borrowings"), ("equity", "Shareholders' equity"),
            ("total_liabilities_and_equity", "Total liabilities and equity")]


def _one_year(revenue: int, rng, weak: bool) -> dict[str, int]:
    gm = rng.uniform(0.22, 0.30) if weak else rng.uniform(0.25, 0.42)
    opex_share = rng.uniform(0.10, 0.15) if weak else rng.uniform(0.07, 0.14)
    cogs = int(round(revenue * (1 - gm)))
    gross_profit = revenue - cogs
    opex = int(round(revenue * opex_share))
    ebitda = gross_profit - opex
    depreciation = int(round(revenue * rng.uniform(0.02, 0.04)))
    total_debt = int(round(revenue * (rng.uniform(0.35, 0.55) if weak else rng.uniform(0.1, 0.35))))
    interest = int(round(total_debt * rng.uniform(0.09, 0.13)))
    principal = int(round(total_debt * rng.uniform(0.12, 0.22)))
    pbt = ebitda - depreciation - interest
    tax = max(0, int(round(pbt * 0.25)))
    pat = pbt - tax

    cash = int(round(revenue * rng.uniform(0.02, 0.08)))
    receivables = int(round(revenue * rng.uniform(0.08, 0.2)))
    inventory = int(round(revenue * rng.uniform(0.05, 0.15)))
    current_assets = cash + receivables + inventory
    current_liabilities = int(round(revenue * rng.uniform(0.06, 0.16)))
    fixed_assets = int(round(revenue * rng.uniform(0.2, 0.6)))
    equity = current_assets + fixed_assets - current_liabilities - total_debt
    if equity <= 0:  # keep the balance sheet plausible
        fixed_assets += -equity + int(revenue * 0.05)
        equity = current_assets + fixed_assets - current_liabilities - total_debt
    total_assets = current_assets + fixed_assets
    return {
        "revenue": revenue, "cogs": cogs, "gross_profit": gross_profit, "opex": opex,
        "ebitda": ebitda, "depreciation": depreciation, "interest": interest, "pbt": pbt,
        "tax": tax, "pat": pat, "principal_repayment": principal,
        "cash": cash, "receivables": receivables, "inventory": inventory,
        "current_assets": current_assets, "fixed_assets": fixed_assets,
        "total_assets": total_assets, "current_liabilities": current_liabilities,
        "total_debt": total_debt, "equity": equity,
        "total_liabilities_and_equity": current_liabilities + total_debt + equity,
    }


def generate_financials(applicant_ids: list[str], s: Settings) -> dict[str, dict]:
    """Return truth: {company_id: {"unit": "INR '000", "years": {FY: {...}}, "weak": bool}}."""
    rng = rng_for(s.seed, "financials")
    truth = {}
    for cid in applicant_ids:
        weak = bool(rng.random() < 0.3)
        revenue = int(rng.lognormal(np.log(60000), 0.7))
        years = {}
        for fy in FISCAL_YEARS:
            years[fy] = _one_year(revenue, rng, weak)
            revenue = int(revenue * (1 + rng.normal(0.08, 0.12)))
        truth[cid] = {"unit": "INR '000", "weak": weak, "years": years}
    return truth


def _chart_png(company: str, years: dict) -> bytes:
    fig, ax = plt.subplots(figsize=(6, 2.6), dpi=110)
    rev = [years[fy]["revenue"] for fy in FISCAL_YEARS]
    ebitda = [years[fy]["ebitda"] for fy in FISCAL_YEARS]
    x = np.arange(len(FISCAL_YEARS))
    ax.bar(x - 0.2, rev, 0.4, label="Revenue")
    ax.bar(x + 0.2, ebitda, 0.4, label="EBITDA")
    ax.set_xticks(x, FISCAL_YEARS)
    ax.set_ylabel("INR '000")
    ax.set_title(f"{company}: revenue and EBITDA")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", metadata={"Software": None})
    plt.close(fig)
    return buf.getvalue()


def _table(rows, header):
    t = Table([header] + rows, colWidths=[8 * cm] + [3 * cm] * len(FISCAL_YEARS))
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
    ]))
    return t


def render_financials_pdf(path: Path, company_name: str, data: dict) -> None:
    styles = getSampleStyleSheet()
    years = data["years"]
    header = ["(INR '000)"] + FISCAL_YEARS
    story = [
        Paragraph(f"{company_name}", styles["Title"]),
        Paragraph("Audited financial statements, fiscal years ending 31 March", styles["Normal"]),
        Paragraph("Synthetic document generated for training. Not a real company.", styles["Italic"]),
        Spacer(1, 10),
        Paragraph("Statement of profit and loss", styles["Heading2"]),
        _table([[label] + [format_inr(years[fy][k], 0) for fy in FISCAL_YEARS] for k, label in PNL_LINES],
               header),
        Spacer(1, 12),
        RLImage(io.BytesIO(_chart_png(company_name, years)), width=15 * cm, height=6.5 * cm),
        PageBreak(),
        Paragraph("Balance sheet as at 31 March", styles["Heading2"]),
        _table([[label] + [format_inr(years[fy][k], 0) for fy in FISCAL_YEARS] for k, label in BS_LINES],
               header),
        Spacer(1, 12),
        Paragraph("Note 14: Borrowings", styles["Heading3"]),
        Paragraph(
            "Scheduled principal repayment of borrowings during the year (INR '000): "
            + "; ".join(f"{fy}: {format_inr(years[fy]['principal_repayment'], 0)}" for fy in FISCAL_YEARS)
            + ".", styles["Normal"]),
    ]
    SimpleDocTemplate(str(path), pagesize=A4, title=company_name, author="Kestrel Finance (synthetic)",
                      creator="CreditLens generator").build(story)


def scanify(pdf_path: Path, out_path: Path, rng, rotate_page2: bool = False) -> None:
    """Turn a clean PDF into a noisy, slightly skewed image-only PDF."""
    from pdf2image import convert_from_path

    pages = convert_from_path(str(pdf_path), dpi=110, grayscale=True)
    scanned = []
    for i, page in enumerate(pages):
        img = page.rotate(float(rng.uniform(-1.8, 1.8)), expand=True, fillcolor=255)
        if rotate_page2 and i == 1:
            img = img.rotate(90, expand=True, fillcolor=255)
        arr = np.asarray(img, dtype=np.int16)
        arr = arr + rng.normal(0, 14, arr.shape).astype(np.int16)
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))
        scanned.append(img.convert("L"))
    scanned[0].save(out_path, save_all=True, append_images=scanned[1:], format="PDF", resolution=110)


def write_financial_pdfs(truth: dict, companies, out_dir: Path, s: Settings) -> dict[str, str]:
    """Write one PDF per company. Returns {company_id: 'text' | 'scan' | 'scan_rotated'}."""
    rng = rng_for(s.seed, "scans")
    out_dir.mkdir(parents=True, exist_ok=True)
    names = companies.set_index("company_id")["legal_name"].to_dict()
    ids = sorted(truth)
    n_scan = max(1, round(len(ids) * s.sizes.scanned_financials_share))
    scan_ids = set(rng.choice(ids, n_scan, replace=False).tolist())
    rotated_id = sorted(scan_ids)[0]
    kinds = {}
    for cid in ids:
        final = out_dir / f"{cid}_financials.pdf"
        if cid in scan_ids:
            tmp = out_dir / f".{cid}_tmp.pdf"
            render_financials_pdf(tmp, names[cid], truth[cid])
            scanify(tmp, final, rng, rotate_page2=(cid == rotated_id))
            tmp.unlink()
            kinds[cid] = "scan_rotated" if cid == rotated_id else "scan"
        else:
            render_financials_pdf(final, names[cid], truth[cid])
            kinds[cid] = "text"
    return kinds
