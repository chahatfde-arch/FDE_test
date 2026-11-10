"""Milestone 2 done-when: every planted data problem is caught or fixed, proven against the truth."""
import json

import pandas as pd
import pytest

from creditlens.generators.policy import RULES

COMPARE = ["application_id", "seq", "txn_date", "channel", "counterparty", "amount", "balance", "is_bounce"]


@pytest.fixture(scope="module")
def truth(s):
    t = pd.read_csv(s.paths.answer_key / "transactions_truth.csv", parse_dates=["txn_date"])
    return t[COMPARE].sort_values(["application_id", "seq"]).reset_index(drop=True)


def test_clean_equals_truth_exactly(outputs, truth):
    clean = outputs["transactions"][COMPARE].sort_values(["application_id", "seq"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(clean, truth, check_dtype=False, atol=0.005)


def test_quality_report_matches_planted_issues(s, outputs):
    manifest = json.loads((s.paths.answer_key / "statement_issues.json").read_text())
    q = outputs["quality_report"].set_index("source_file")
    for fname, m in manifest.items():
        r = q.loc[fname]
        assert r.duplicates_removed == m["duplicates"], fname
        assert r.balances_filled == m["missing_balance"], fname
        assert r.missing_descriptions == m["missing_description"], fname
        assert r.currency_text_cells == m["currency_text"], fname
        assert r.alt_date_rows == m["alt_dates"], fname
        assert bool(r.messy_headers) == ("messy_headers" in m["issues"]), fname
        assert r.unrecognized_narrations == 0, fname


def test_banking_conduct_flags_match_answer_key(s, outputs):
    """Rules 4.1 and 4.2 computed from curated features agree with the answer key."""
    expected = json.loads((s.paths.answer_key / "expected_policy_flags.json").read_text())
    f = outputs["statement_features"].set_index("application_id")
    for app_id, e in expected.items():
        assert (f.loc[app_id, "cheque_returns_12m"] > RULES["MAX_CHEQUE_RETURNS_12M"]) == ("4.1" in e["flags"])
        assert (f.loc[app_id, "cash_credit_share"] > RULES["MAX_CASH_CREDIT_SHARE"]) == ("4.2" in e["flags"])


def test_database_load_round_trip(s, outputs, tmp_path):
    from sqlalchemy import create_engine

    from creditlens.pipeline.load import load_all
    url = f"sqlite:///{tmp_path / 'test.db'}"
    tables = load_all(url, s.paths.raw, outputs)
    assert {"applications", "transactions", "statement_features", "directors"} <= set(tables)
    n = pd.read_sql("select count(*) n from transactions", create_engine(url)).n[0]
    assert n == len(outputs["transactions"])
