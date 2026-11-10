"""Small, testable wrangling functions. Each one fixes one kind of data problem."""
from __future__ import annotations

import re
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

import yaml

ALIASES_FILE = Path(__file__).with_name("aliases.yaml")

HEADER_MAP = {
    "date": "txn_date", "txn date": "txn_date", "ref no": "ref_no", "description": "narration",
    "narration": "narration", "debit": "debit", "credit": "credit", "balance": "balance",
    "closing balance": "balance", "amount": "amount", "dr/cr": "drcr",
}
LAYOUT_A = {"txn_date", "ref_no", "narration", "debit", "credit", "balance"}
LAYOUT_B = {"txn_date", "narration", "amount", "drcr", "balance"}

# Formats are tried in order. Each statement layout's own format comes first.
DATE_FORMATS = ["%d/%m/%Y", "%d-%b-%Y", "%Y-%m-%d", "%d-%m-%y", "%b %d, %Y", "%d.%m.%Y"]
CURRENCY_TOKENS = ("₹", "INR", "Rs.")

NARRATION_PATTERNS = [
    ("UPI", re.compile(r"^UPI/(?P<cp>.+)/\w+$")),
    ("NEFT", re.compile(r"^NEFT-(?P<cp>.+)-\w+$")),
    ("RTGS", re.compile(r"^RTGS/(?P<cp>.+)/\w+$")),
    ("IMPS", re.compile(r"^IMPS-(?P<cp>.+)-\w+$")),
    ("CHQ_RTN", re.compile(r"^CHQ RTN (?P<cp>.+) INSUFFICIENT FUNDS$")),
    ("CHQ", re.compile(r"^CHQ DEP (?P<cp>.+)$")),
    ("ACH", re.compile(r"^ACH D- (?P<cp>.+) EMI$")),
]
FIXED_NARRATIONS = {"CASH DEPOSIT": ("CASH", "CASH"), "CHGS CHQ RTN": ("CHARGES", "BANK CHARGES")}


def normalize_header(h: str) -> str:
    key = re.sub(r"\s+", " ", h.strip().lower())
    return HEADER_MAP.get(key, key)


def detect_layout(columns: list[str]) -> str:
    cols = set(columns)
    if cols == LAYOUT_A:
        return "A"
    if cols == LAYOUT_B:
        return "B"
    raise ValueError(f"Unknown statement layout with columns {sorted(cols)}")


def parse_date(text: str, window: tuple[date, date]) -> tuple[date, str]:
    """Return (date, format used). Only accept dates inside the statement window,
    which resolves ambiguous strings such as '05-03-26'."""
    text = text.strip()
    for fmt in DATE_FORMATS:
        try:
            d = datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        if window[0] <= d <= window[1]:
            return d, fmt
    raise ValueError(f"Unparseable or out-of-window date: {text!r}")


def has_currency_text(text: str) -> bool:
    return any(tok in text for tok in CURRENCY_TOKENS)


def parse_amount(text: str | None) -> float | None:
    """'₹1,23,456.00' -> 123456.0, '(3,400.00)' -> -3400.0, '' -> None."""
    if text is None:
        return None
    t = str(text).strip()
    if not t:
        return None
    for tok in CURRENCY_TOKENS:
        t = t.replace(tok, "")
    t = t.replace(",", "").replace(" ", "")
    negative = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    value = float(t)
    return -value if negative else value


def parse_narration(text: str) -> tuple[str, str]:
    """Split a narration into (channel, raw counterparty)."""
    t = (text or "").strip()
    if not t:
        return "UNKNOWN", "UNKNOWN"
    if t.upper() in FIXED_NARRATIONS:
        return FIXED_NARRATIONS[t.upper()]
    for channel, pattern in NARRATION_PATTERNS:
        m = pattern.match(t)
        if m:
            return channel, m.group("cp")
    return "OTHER", t


@lru_cache(maxsize=1)
def _alias_config() -> tuple[dict, tuple]:
    cfg = yaml.safe_load(ALIASES_FILE.read_text())
    return cfg["abbreviations"], tuple(cfg["strip_suffixes"])


def normalize_counterparty(raw: str) -> str:
    """'Amzn Seller Svcs Pvt Ltd.' -> 'AMAZON SELLER SERVICES'."""
    abbreviations, suffixes = _alias_config()
    name = re.sub(r"[.,]", " ", raw.upper())
    name = re.sub(r"\s+", " ", name).strip()
    changed = True
    while changed:
        changed = False
        for suf in suffixes:
            if name.endswith(" " + suf):
                name = name[: -len(suf) - 1].strip()
                changed = True
    return " ".join(abbreviations.get(w, w) for w in name.split())
