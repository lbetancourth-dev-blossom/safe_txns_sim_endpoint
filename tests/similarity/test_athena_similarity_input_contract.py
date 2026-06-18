import pathlib

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# T1 — _validate_similarity_input
# ---------------------------------------------------------------------------
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'endpoint'))

from endpoint.inference_rules import _validate_similarity_input


def test_validate_all_present_returns_ok():
    df = pd.DataFrame({"idOLBUserTxns": [604150, 604151], "createdAtTxns": ["2026-06-15T20:03:08", "2026-06-15T20:03:09"]})
    ok, missing = _validate_similarity_input(df)
    assert ok is True
    assert missing == []


def test_validate_missing_idolbuser_marks_row():
    df = pd.DataFrame({"idOLBUserTxns": [604150, None], "createdAtTxns": ["2026-06-15T20:03:08", "2026-06-15T20:03:09"]})
    ok, missing = _validate_similarity_input(df)
    assert ok is False
    assert missing == [1]  # row index 1


def test_validate_missing_idolbuser_column_marks_all():
    df = pd.DataFrame({"createdAtTxns": ["2026-06-15T20:03:08"]})
    ok, missing = _validate_similarity_input(df)
    assert ok is False
    assert missing == [0]


def test_validate_idolbuser_non_int_marks_row():
    df = pd.DataFrame({"idOLBUserTxns": [604150, "not_an_int"], "createdAtTxns": ["2026-06-15T20:03:08", "2026-06-15T20:03:09"]})
    ok, missing = _validate_similarity_input(df)
    assert ok is False
    assert 1 in missing


def test_validate_does_not_raise_when_all_missing():
    # D1 closed: graceful degradation, never raise
    df = pd.DataFrame({"foo": [1]})
    ok, missing = _validate_similarity_input(df)
    assert ok is False
    # No exception


def test_validate_missing_createdat_marks_row_d1_graceful():
    """D1 CLOSED: createdAtTxns missing → sim_*=null, NOT 400."""
    df = pd.DataFrame({"idOLBUserTxns": [604150, 604151], "createdAtTxns": [None, "2026-06-15T20:03:09"]})
    ok, missing = _validate_similarity_input(df)
    assert ok is False
    assert 0 in missing  # row 0 marked
    # Crucially: no exception raised


def test_validate_both_missing_marks_row_d1_graceful():
    """D1 CLOSED: both idOLBUserTxns AND createdAtTxns null → sim_*=null per row."""
    df = pd.DataFrame({"idOLBUserTxns": [None], "createdAtTxns": [None]})
    ok, missing = _validate_similarity_input(df)
    assert ok is False
    assert missing == [0]
    # Once again: no exception, K-means path will still run for that row


# ---------------------------------------------------------------------------
# T4 — requirements.txt presence
# ---------------------------------------------------------------------------

def test_endpoint_requirements_has_pyathena():
    req = pathlib.Path("endpoint/requirements.txt").read_text()
    assert "pyathena" in req
    assert "python-dateutil" in req
