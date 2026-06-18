"""
T_LOGGING — Structured logging two-path (F5+ gate decision).

Verifies:
  - similarity.no_history emitted at INFO when Athena returns 0 rows (Scenario 3)
  - similarity.athena_failure emitted at WARNING with classified category on exception
  - idOLBUser NEVER appears in plaintext in any log record
  - classify_exception() maps exception types to observable categories
  - exception_message truncated to 200 chars (log injection defense)
"""

import hashlib
import logging
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest


def _expected_hash(idolbuser: int) -> str:
    return hashlib.sha256(str(idolbuser).encode()).hexdigest()[:16]


@patch("endpoint.similarity_matcher.connect")
def test_athena_zero_rows_emits_no_history_log(mock_connect, caplog):
    """F5+ gate: when Athena returns 0 rows (Scenario 3 — normal), emit INFO similarity.no_history."""
    from endpoint.similarity_matcher import load_reference_data_from_athena
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.description = [("idolbuser",), ("createdat",), ("statuswarning",), ("metadata",), ("transactionid",)]
    mock_cursor.fetchall.return_value = []  # 0 rows
    mock_conn.cursor.return_value = mock_cursor
    mock_connect.return_value = mock_conn

    with caplog.at_level(logging.INFO, logger="endpoint.similarity_matcher"):
        result = load_reference_data_from_athena(idolbuser=604150, force_reload=True)

    assert result == (None, None, None, None)

    rec = next((r for r in caplog.records if "similarity.no_history" in r.message or r.message == "similarity.no_history"), None)
    assert rec is not None, "Expected similarity.no_history log entry"
    assert rec.levelno == logging.INFO
    # idolbuser must be HASHED, never plaintext
    assert "604150" not in rec.getMessage(), "PII: idolbuser must NEVER appear in plaintext"
    # The hash must be present in the extra fields
    assert getattr(rec, "idolbuser_hash", None) == _expected_hash(604150)
    assert getattr(rec, "rows", None) == 0


@patch("endpoint.similarity_matcher.connect")
def test_athena_permission_error_emits_failure_log_with_category(mock_connect, caplog):
    """F5+ gate: when Athena raises PermissionError, emit WARNING similarity.athena_failure with category='permission'."""
    from endpoint.similarity_matcher import load_reference_data_from_athena
    mock_connect.side_effect = PermissionError("AccessDeniedException: cross-account denied")

    with caplog.at_level(logging.WARNING, logger="endpoint.similarity_matcher"):
        result = load_reference_data_from_athena(idolbuser=604150, force_reload=True)

    assert result == (None, None, None, None)
    rec = next((r for r in caplog.records if "similarity.athena_failure" in r.message or r.message == "similarity.athena_failure"), None)
    assert rec is not None, "Expected similarity.athena_failure log entry"
    assert rec.levelno in (logging.WARNING, logging.ERROR)
    assert "604150" not in rec.getMessage(), "PII: idolbuser must NEVER appear in plaintext"
    assert getattr(rec, "idolbuser_hash", None) == _expected_hash(604150)
    assert getattr(rec, "exception_class", None) == "PermissionError"
    assert getattr(rec, "category", None) == "permission"


@patch("endpoint.similarity_matcher.connect")
def test_athena_timeout_emits_failure_log_with_category_timeout(mock_connect, caplog):
    from endpoint.similarity_matcher import load_reference_data_from_athena
    mock_connect.side_effect = TimeoutError("query exceeded 10s")
    with caplog.at_level(logging.WARNING, logger="endpoint.similarity_matcher"):
        load_reference_data_from_athena(idolbuser=604150, force_reload=True)
    rec = next((r for r in caplog.records if "similarity.athena_failure" in r.message), None)
    assert rec is not None
    assert getattr(rec, "category", None) == "timeout"


def test_classify_exception_maps_permission_error():
    from endpoint.similarity_matcher import classify_exception
    assert classify_exception(PermissionError("AccessDenied")) == "permission"


def test_classify_exception_maps_timeout_error():
    from endpoint.similarity_matcher import classify_exception
    assert classify_exception(TimeoutError("query timed out")) == "timeout"


def test_classify_exception_maps_throttling_string_match():
    """Throttling exceptions from boto3 contain 'Throttling' in the message."""
    from endpoint.similarity_matcher import classify_exception
    class FakeThrottle(Exception):
        pass
    exc = FakeThrottle("ThrottlingException: rate exceeded")
    assert classify_exception(exc) == "throttling"


def test_classify_exception_unknown_fallback():
    from endpoint.similarity_matcher import classify_exception
    assert classify_exception(RuntimeError("oh no")) == "unknown"


def test_exception_message_truncated_to_200_chars():
    """F5+ defense against log injection: exception_message truncated to 200 chars."""
    from endpoint.similarity_matcher import load_reference_data_from_athena
    long_msg = "X" * 5000
    records = []

    class Cap(logging.Handler):
        def emit(self, r):
            records.append(r)

    h = Cap()
    logger = logging.getLogger("endpoint.similarity_matcher")
    logger.addHandler(h)
    try:
        with patch("endpoint.similarity_matcher.connect", side_effect=RuntimeError(long_msg)):
            load_reference_data_from_athena(idolbuser=604150, force_reload=True)
    finally:
        logger.removeHandler(h)

    failure_recs = [r for r in records if "similarity.athena_failure" in r.message]
    assert failure_recs, "Expected athena_failure log"
    assert len(getattr(failure_recs[0], "exception_message", "")) <= 200
