"""
T3 — predict_fn integration: D1 + D2 + D4 + R5 graceful degradation contracts.

Patch strategy: target endpoint.inference_rules._similarity_mod DIRECTLY with
a MagicMock to bypass _ensure_similarity_loaded() caching entirely.
autouse fixture resets _similarity_mod + HAS_SIMILARITY between tests.
"""

import os
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
import numpy as np


# Why autouse reset: `_similarity_mod` is module-cached; without reset, test order changes test outcomes.
@pytest.fixture(autouse=True)
def reset_similarity_module_state(monkeypatch):
    """Reset _similarity_mod and HAS_SIMILARITY between tests to avoid cache pollution."""
    import endpoint.inference_rules as ir
    monkeypatch.setattr(ir, "_similarity_mod", None, raising=False)
    monkeypatch.setattr(ir, "HAS_SIMILARITY", None, raising=False)
    # Also disable rules to keep tests focused on similarity path
    monkeypatch.setenv("DISABLE_RULES", "1")
    yield


def _make_sim_mock(athena_return=(None, None, None, None), find_return=None):
    """Build a MagicMock that mimics the `endpoint.similarity_matcher` module surface
    used by `predict_fn`. Patch `_similarity_mod` directly with this — bypasses
    `_ensure_similarity_loaded` entirely so cached state cannot interfere."""
    mock_sim = MagicMock()
    mock_sim.load_reference_data_from_athena.return_value = athena_return
    mock_sim.find_similar_transaction.return_value = find_return or {
        "sim_match_txn_id": None,
        "sim_score": None,
        "sim_status": None,
        "sim_decision": None,
    }
    return mock_sim


def test_predict_fn_always_calls_athena(monkeypatch, model_artifacts, sample_input):
    """D2 CLOSED: similarity loop SIEMPRE llama al Athena loader (sin condicional)."""
    mock_sim = _make_sim_mock(athena_return=(None, None, None, None))
    monkeypatch.setattr("endpoint.inference_rules._similarity_mod", mock_sim)
    monkeypatch.setattr("endpoint.inference_rules.HAS_SIMILARITY", True)

    from endpoint.inference_rules import predict_fn
    out = pd.DataFrame(predict_fn(sample_input, model_artifacts))

    assert mock_sim.load_reference_data_from_athena.called or mock_sim.find_similar_transaction.called
    # K-means columns intact (R5)
    assert "kmeans_risk_score" in out.columns
    assert out["kmeans_risk_score"].notna().all()
    # sim_* null because no Athena data
    assert out["sim_score"].isna().all()


def test_predict_fn_never_calls_parquet_loader_d2(monkeypatch, model_artifacts, sample_input):
    """D2 CLOSED: load_reference_data_from_s3 NEVER se llama en el path de similarity."""
    mock_sim = _make_sim_mock(athena_return=(None, None, None, None))
    # Add the parquet-loader attr to the mock so we can assert it is never called
    mock_sim.load_reference_data_from_s3 = MagicMock()
    monkeypatch.setattr("endpoint.inference_rules._similarity_mod", mock_sim)
    monkeypatch.setattr("endpoint.inference_rules.HAS_SIMILARITY", True)

    from endpoint.inference_rules import predict_fn
    pd.DataFrame(predict_fn(sample_input, model_artifacts))

    assert not mock_sim.load_reference_data_from_s3.called, "D2: Parquet path eliminado de similarity"


def test_predict_fn_kmeans_intact_when_idolbuser_missing(monkeypatch, model_artifacts, sample_input_no_idolbuser):
    """D1 CLOSED: K-means runs normally, sim_* are null when idOLBUserTxns missing."""
    mock_sim = _make_sim_mock()
    monkeypatch.setattr("endpoint.inference_rules._similarity_mod", mock_sim)
    monkeypatch.setattr("endpoint.inference_rules.HAS_SIMILARITY", True)

    from endpoint.inference_rules import predict_fn
    out = pd.DataFrame(predict_fn(sample_input_no_idolbuser, model_artifacts))
    # K-means OK
    assert out["kmeans_risk_decision"].notna().all()
    # Similarity skipped → null
    assert out["sim_score"].isna().all()
    assert out["sim_decision"].isna().all()


def test_predict_fn_kmeans_intact_when_createdat_missing(monkeypatch, model_artifacts, sample_input_no_createdat):
    """D1 CLOSED: createdAtTxns missing → sim_*=null, NO 400, K-means OK."""
    mock_sim = _make_sim_mock()
    monkeypatch.setattr("endpoint.inference_rules._similarity_mod", mock_sim)
    monkeypatch.setattr("endpoint.inference_rules.HAS_SIMILARITY", True)

    from endpoint.inference_rules import predict_fn
    out = pd.DataFrame(predict_fn(sample_input_no_createdat, model_artifacts))
    assert out["kmeans_risk_score"].notna().all()
    assert out["sim_score"].isna().all()


def test_predict_fn_kmeans_intact_on_athena_exception(monkeypatch, model_artifacts, sample_input):
    """R5 + D4: K-means columns are not corrupted by Athena failures."""
    mock_sim = MagicMock()
    mock_sim.load_reference_data_from_athena.side_effect = Exception("Athena timeout")
    mock_sim.find_similar_transaction.side_effect = Exception("Athena timeout")
    monkeypatch.setattr("endpoint.inference_rules._similarity_mod", mock_sim)
    monkeypatch.setattr("endpoint.inference_rules.HAS_SIMILARITY", True)

    from endpoint.inference_rules import predict_fn
    out = pd.DataFrame(predict_fn(sample_input, model_artifacts))
    assert out["kmeans_risk_score"].notna().all()
    assert out["sim_score"].isna().all()


def test_predict_fn_kmeans_intact_on_athena_timeout_d4(monkeypatch, model_artifacts, sample_input, caplog):
    """D4 CLOSED: timeout 10s → log warning, sim_*=null, K-means OK."""
    mock_sim = MagicMock()
    mock_sim.load_reference_data_from_athena.side_effect = TimeoutError("query exceeded 10s")
    mock_sim.find_similar_transaction.side_effect = TimeoutError("query exceeded 10s")
    monkeypatch.setattr("endpoint.inference_rules._similarity_mod", mock_sim)
    monkeypatch.setattr("endpoint.inference_rules.HAS_SIMILARITY", True)

    from endpoint.inference_rules import predict_fn
    out = pd.DataFrame(predict_fn(sample_input, model_artifacts))
    assert out["kmeans_risk_score"].notna().all()
    assert out["sim_score"].isna().all()
    # Warning is logged
    assert any("[ATHENA]" in rec.message or "timeout" in rec.message.lower() for rec in caplog.records)


def test_predict_fn_succeeds_when_athena_returns_rows(monkeypatch, model_artifacts, sample_input):
    """Happy path: Athena returns rows → find_similar_transaction returns a match."""
    fixture_df = pd.DataFrame({
        "TransactionID": ["txn-A"],
        "idOLBUser": [604150],
        "createdAt": [pd.Timestamp("2026-06-15", tz="UTC")],
        "statusWarning": ["SAFE"],
        "metadata": ['{"decisionResult": {"num__amount": 1.0, "cat__TransactionProcessingType_Intime": 1.0}}'],
    })
    mock_sim = _make_sim_mock(
        athena_return=(fixture_df, np.array([[1.0, 1.0]]), np.array(["SAFE"]), np.array(["txn-A"])),
        find_return={
            "sim_match_txn_id": "txn-A",
            "sim_score": 0.97,
            "sim_status": "SAFE",
            "sim_decision": "Accept",
        },
    )
    monkeypatch.setattr("endpoint.inference_rules._similarity_mod", mock_sim)
    monkeypatch.setattr("endpoint.inference_rules.HAS_SIMILARITY", True)

    from endpoint.inference_rules import predict_fn
    out = pd.DataFrame(predict_fn(sample_input, model_artifacts))
    # K-means intact AND sim_* populated
    assert out["kmeans_risk_score"].notna().all()
    assert (out["sim_score"] == 0.97).all()
    assert (out["sim_match_txn_id"] == "txn-A").all()
