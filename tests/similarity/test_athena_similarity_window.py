import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from endpoint.similarity_matcher import (
    load_reference_data_from_athena,
    _compute_sliding_window,
    _normalize_athena_columns,
)


def test_compute_window_uses_now_at_call():
    start1, end1 = _compute_sliding_window(window_months=6)
    # end is approximately now()
    assert (datetime.now(timezone.utc) - end1).total_seconds() < 5
    # start is exactly 6 months earlier
    from dateutil.relativedelta import relativedelta
    assert start1 == end1 - relativedelta(months=6)


def test_compute_window_changes_between_calls():
    """R1: window must be computed at each call, not memoized at module load."""
    start1, end1 = _compute_sliding_window()
    import time; time.sleep(1.1)
    start2, end2 = _compute_sliding_window()
    assert end2 > end1


def test_normalize_athena_columns_maps_lowercase_to_camelcase():
    df = pd.DataFrame({
        "idolbuser": [604150],
        "transactionid": [1],
        "createdat": ["2026-06-15"],
        "statuswarning": ["SAFE"],
        "metadata": ['{"decisionResult": {"num__amount": 1.0}}'],
    })
    out = _normalize_athena_columns(df)
    # Canonical mapping (matches DTYPE_MAP / predict_fn convention)
    assert "TransactionID" in out.columns  # uppercase D — canonical
    assert "idOLBUser" in out.columns
    assert "createdAt" in out.columns
    assert "statusWarning" in out.columns
    assert "metadata" in out.columns


@patch("endpoint.similarity_matcher.connect")
def test_load_from_athena_calls_connect_with_alpha_staging(mock_connect):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.description = [("idolbuser",), ("createdat",), ("statuswarning",), ("metadata",), ("transactionid",)]
    mock_cursor.fetchall.return_value = [
        (604150, pd.Timestamp("2026-06-15", tz="UTC"), "SAFE", '{"decisionResult": {"num__amount": 1.0, "cat__TransactionProcessingType_Intime": 1.0}}', "t1"),
    ]
    mock_conn.cursor.return_value = mock_cursor
    mock_connect.return_value = mock_conn
    load_reference_data_from_athena(idolbuser=604150)
    mock_connect.assert_called_once()
    call_kwargs = mock_connect.call_args.kwargs
    assert call_kwargs["s3_staging_dir"] == "s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/"
    assert call_kwargs["region_name"] == "us-east-2"


@patch("endpoint.similarity_matcher.connect")
def test_load_from_athena_uses_parameterized_query_F1(mock_connect):
    """F1 gate decision: PyAthena parameterized queries, NOT f-string."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.description = [("idolbuser",), ("createdat",), ("statuswarning",), ("metadata",), ("transactionid",)]
    mock_cursor.fetchall.return_value = []
    mock_conn.cursor.return_value = mock_cursor
    mock_connect.return_value = mock_conn

    load_reference_data_from_athena(idolbuser=604150)

    # Verify cursor.execute was called with SQL + dict of params (not just SQL string)
    assert mock_cursor.execute.called
    call_args = mock_cursor.execute.call_args
    sql = call_args[0][0]
    params = call_args[0][1]

    # Must use named param placeholders, not f-string interpolated values
    assert "%(user)s" in sql, "F1: SQL must use %(user)s param, not interpolated idolbuser"
    assert "%(window_start)s" in sql
    assert "%(window_end)s" in sql
    assert "604150" not in sql, "F1: idolbuser value MUST NOT appear in SQL string (parameterized)"

    # Params dict must contain int-cast user + datetime windows
    assert isinstance(params, dict)
    assert params["user"] == 604150
    assert isinstance(params["user"], int), "Defense-in-depth: int cast still applied"


@patch("endpoint.similarity_matcher.connect")
def test_load_from_athena_uses_explicit_column_list_F11(mock_connect):
    """F11 gate decision: explicit column list, NO SELECT *."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.description = [("idolbuser",), ("createdat",), ("statuswarning",), ("metadata",), ("transactionid",)]
    mock_cursor.fetchall.return_value = []
    mock_conn.cursor.return_value = mock_cursor
    mock_connect.return_value = mock_conn

    load_reference_data_from_athena(idolbuser=604150)

    sql = mock_cursor.execute.call_args[0][0]
    assert "SELECT *" not in sql.upper(), "F11: SELECT * forbidden"
    # Required explicit columns
    for col in ("idolbuser", "createdat", "statuswarning", "metadata", "transactionid"):
        assert col in sql.lower(), f"F11: explicit column {col} required in SELECT"


@patch("endpoint.similarity_matcher.connect")
def test_load_from_athena_returns_none_on_connection_error(mock_connect):
    mock_connect.side_effect = ConnectionError("VPC unreachable")
    result = load_reference_data_from_athena(idolbuser=604150)
    assert result == (None, None, None, None)


def test_load_from_athena_casts_idolbuser_to_int_defense_in_depth():
    """HLTC-9 + F1 defense-in-depth: int cast still applied even with parameterized queries."""
    with pytest.raises((ValueError, TypeError)):
        load_reference_data_from_athena(idolbuser="1; DROP TABLE x")


@patch("endpoint.similarity_matcher.connect")
def test_load_from_athena_empty_result_returns_none_tuple(mock_connect):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.description = [("idolbuser",), ("createdat",), ("statuswarning",), ("metadata",), ("transactionid",)]
    mock_cursor.fetchall.return_value = []
    mock_conn.cursor.return_value = mock_cursor
    mock_connect.return_value = mock_conn
    result = load_reference_data_from_athena(idolbuser=604150)
    # Empty result → no reference data → graceful degradation
    assert result[1] is None  # feature_vectors None
