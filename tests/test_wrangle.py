from datetime import date

import pytest

from creditlens.pipeline.wrangle import (normalize_counterparty, normalize_header, parse_amount,
                                         parse_date, parse_narration)

WINDOW = (date(2025, 10, 1), date(2026, 9, 30))


@pytest.mark.parametrize("text", ["05/03/2026", "05-Mar-2026", "2026-03-05", "05-03-26",
                                  "Mar 05, 2026", "05.03.2026"])
def test_every_date_format_means_5_march(text):
    assert parse_date(text, WINDOW)[0] == date(2026, 3, 5)


def test_out_of_window_date_is_rejected():
    with pytest.raises(ValueError):
        parse_date("05/03/2019", WINDOW)


@pytest.mark.parametrize("text,value", [("12,34,567.89", 1234567.89), ("₹1,200.50", 1200.5),
                                        ("INR 5,000.00", 5000.0), ("Rs. 99.00", 99.0),
                                        ("(3,400.00)", -3400.0), ("", None), (None, None)])
def test_parse_amount(text, value):
    assert parse_amount(text) == value


@pytest.mark.parametrize("raw", ["AMAZON SELLER SERVICES", "Amazon Seller Services",
                                 "AMAZON SELLER SERVICES PVT LTD", "Amazon Seller Services Private Limited",
                                 "AMZN SELLER SVCS", "amazon  seller  services."])
def test_counterparty_variants_collapse(raw):
    assert normalize_counterparty(raw) == "AMAZON SELLER SERVICES"


@pytest.mark.parametrize("text,expected", [
    ("UPI/TATA POWER/123456", ("UPI", "TATA POWER")),
    ("NEFT-amazon  seller services.-N123", ("NEFT", "amazon  seller services.")),
    ("CHQ RTN KAVERI RETAIL INSUFFICIENT FUNDS", ("CHQ_RTN", "KAVERI RETAIL")),
    ("CHQ DEP KAVERI RETAIL", ("CHQ", "KAVERI RETAIL")),
    ("ACH D- NORTHSTAR BANK EMI", ("ACH", "NORTHSTAR BANK")),
    ("CASH DEPOSIT", ("CASH", "CASH")), ("", ("UNKNOWN", "UNKNOWN")),
])
def test_parse_narration(text, expected):
    assert parse_narration(text) == expected


def test_messy_headers():
    assert normalize_header("  CLOSING BALANCE ") == "balance"
    assert normalize_header("txn date  ") == "txn_date"
