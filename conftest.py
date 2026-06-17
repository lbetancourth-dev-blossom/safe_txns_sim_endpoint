"""
Root conftest.py — shared fixtures for DATA-1264 test suite.

Provides minimal but real sklearn/numpy model_artifacts and sample_input
fixtures for predict_fn integration tests (test_athena_similarity_fallback.py).

Design: use 2 features (num__amount, cat__TransactionProcessingType) to keep
the fixture fast while satisfying all of predict_fn's ColumnTransformer + KMeans
contract requirements.
"""

import os
import sys
import numpy as np
import pandas as pd
import pytest

# Make endpoint importable without install
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "endpoint"))

from sklearn.cluster import KMeans
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MinMaxScaler, OneHotEncoder


def _build_model_artifacts():
    """Build minimal but real sklearn artifacts that satisfy predict_fn's contract."""
    num_col = "amount"
    cat_col = "TransactionProcessingType"

    # ColumnTransformer — mimics the production preprocessor
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", MinMaxScaler(), [num_col]),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), [cat_col]),
        ],
        remainder="drop",
    )

    # Fit on minimal synthetic data
    rng = np.random.default_rng(42)
    n = 20
    X_fit = pd.DataFrame({
        num_col: rng.uniform(10, 1000, n),
        cat_col: rng.choice(["Intime", "SameDay"], n),
    })
    preprocessor.fit(X_fit)

    pipeline = Pipeline(steps=[("preprocessor", preprocessor)])
    X_transformed = preprocessor.transform(X_fit)

    # selected_features = output feature names from ColumnTransformer
    selected_features = list(preprocessor.get_feature_names_out())

    # KMeans on transformed data
    kmeans = KMeans(n_clusters=2, random_state=42, n_init=10)
    kmeans.fit(X_transformed)

    # Centroids dataframe
    centroids_df = pd.DataFrame(
        kmeans.cluster_centers_,
        columns=selected_features,
    )
    centroids_df.index = list(range(len(centroids_df)))

    # Scalers: MinMaxScaler per cluster (below and above threshold)
    thresholds = {}
    scalers_below = {}
    scalers_above = {}
    distances = kmeans.transform(X_transformed)

    for cluster_id in range(2):
        mask = kmeans.labels_ == cluster_id
        cluster_dists = distances[mask, cluster_id]
        if len(cluster_dists) == 0:
            thresholds[cluster_id] = 1.0
            scalers_below[cluster_id] = _flat_scaler(0.0, 1.0)
            scalers_above[cluster_id] = _flat_scaler(0.0, 1.0)
            continue

        thresh = float(np.percentile(cluster_dists, 75))
        thresholds[cluster_id] = thresh

        below = cluster_dists[cluster_dists <= thresh]
        above = cluster_dists[cluster_dists > thresh]

        scalers_below[cluster_id] = _fit_scaler(below if len(below) >= 2 else np.array([0.0, thresh]))
        scalers_above[cluster_id] = _fit_scaler(above if len(above) >= 2 else np.array([thresh, thresh * 2 + 0.01]))

    return {
        "model": kmeans,
        "pipeline": pipeline,
        "selected": selected_features,
        "centroids": centroids_df,
        "scalers_below": scalers_below,
        "scalers_above": scalers_above,
        "thresholds": thresholds,
    }


def _fit_scaler(values: np.ndarray) -> MinMaxScaler:
    scaler = MinMaxScaler(feature_range=(0, 100))
    scaler.fit(values.reshape(-1, 1))
    return scaler


def _flat_scaler(lo: float, hi: float) -> MinMaxScaler:
    scaler = MinMaxScaler(feature_range=(0, 100))
    scaler.fit(np.array([[lo], [hi if hi > lo else lo + 0.01]]))
    return scaler


@pytest.fixture(scope="session")
def model_artifacts():
    """Real sklearn KMeans + Pipeline artifacts. Built once per test session."""
    return _build_model_artifacts()


def _base_row() -> dict:
    """Minimal valid row for predict_fn with all required fields."""
    return {
        "TransactionID": 1001,
        "idOLBUserTxns": 604150,
        "amount": 250.0,
        "TransactionProcessingType": "Intime",
        "TransactionOrigin": "OLB",
        "TransactionCategory": "ACH",
        "createdAtTxns": "2026-06-15T20:03:08",
        "blossomUserCreatedAt": "2023-01-01T00:00:00",
        "idFi": "FI001",
        # Numeric features — safe zeros
        "is_batch": 0.0,
        "total_amount_batch": 0.0,
        "num_recipients_batch": 0.0,
        "count_user_cancelled_txn_in_last_week": 0,
        "count_user_cancelled_txn_in_last_month": 0,
        "count_user_cancelled_txn_in_last_2_months": 0,
        "count_user_potential_fraud_txn_in_last_week": 0,
        "count_user_potential_fraud_txn_in_last_month": 0,
        "count_user_potential_fraud_txn_in_last_2_months": 0,
        "count_txn_to_recipient_account_in_last_week": 0,
        "count_txn_to_recipient_account_in_last_month": 0,
        "count_txn_to_recipient_account_in_last_2_months": 0,
        "is_first_txn_from_this_olb_user_to_this_recipient_account_q_6h": 0,
        "is_first_txn_from_this_account_to_recipient_account_q_72h": 0,
        "count_all_txn_after_recipient_account_creation": 0.0,
        "count_user_all_txn_in_last_6_months": 0,
        "user_total_active_days_last_6_months": 0,
        "total_amount_user_all_txn_in_last_6_months": 0.0,
        "user_cancel_txn_rate_last_6_months": 0.0,
        "user_avg_count_txn_per_active_day_last_6_months": 0.0,
        "user_avg_amount_txn_per_active_day_last_6_months": 0.0,
        "count_user_ach_txn_in_last_6_months": 0,
        "user_total_ach_active_days_last_6_months": 0,
        "total_amount_user_ach_txn_in_last_6_months": 0.0,
        "user_cancel_ach_txn_rate_last_6_months": 0.0,
        "user_avg_count_ach_txn_per_active_day_last_6_months": 0.0,
        "user_avg_amount_ach_txn_per_active_day_last_6_months": 0.0,
        "amount_coef_var_lst6m": 0.0,
        "pct_txns_under_100_lst6m": 0.0,
        "pct_txns_over_1k_lst6m": 0.0,
        "is_personal_user_phone_primary_updated_last_week": 0.0,
        "is_personal_user_phone_primary_updated_last_month": 0.0,
        "is_personal_user_email_primary_updated_last_week": 0.0,
        "is_personal_user_email_primary_updated_last_month": 0.0,
        "user_type": "personal",
        "user_age": 35.0,
        "count_failed_actions_in_current_session": 0.0,
        "count_suspected_actions_in_current_session": 0.0,
        "total_actions_session": 1.0,
        "is_auth_email_session": 0.0,
        "is_auth_phone_session": 0.0,
        "num_checking_accounts": 1,
        "num_savings_accounts": 0,
        "num_loan_accounts": 0,
        "num_credit_card_accounts": 0,
        "num_certificate_accounts": 0,
        "num_open_ended_loans_accounts": 0,
        "num_other_account": 0,
        "total_accounts": 1,
        "recency_user_created_days": 365.0,
        "is_access_from_remembered_device": 1.0,
        "count_all_txn_last_5m": 0,
        "total_amount_all_txn_last_5m": 0.0,
        "count_txn_to_recipient_account_last_5m": 0,
        "total_amount_txn_to_recipient_account_last_5m": 0.0,
        "count_all_txn_last_30m": 0,
        "total_amount_all_txn_last_30m": 0.0,
        "count_txn_to_recipient_account_last_30m": 0,
        "day_of_week_cos": 0.5,
        "month_sin": 0.5,
        "cu_avg_amount_ach_txn_in_last_6_months": 200.0,
        "is_amount_greater_than_cu_p95_amount_ach_txn_in_last_6_months": 0,
        "txn_amount_vs_cu_avg_amount_ach_txn_in_last_6_months": 1.25,
        "amt_vs_user_ach_avg_day": 1.0,
        "ach_count_share_6m": 0.5,
    }


@pytest.fixture(scope="session")
def sample_input():
    """Single-row DataFrame with all required fields including idOLBUserTxns + createdAtTxns."""
    return pd.DataFrame([_base_row()])


@pytest.fixture(scope="session")
def sample_input_no_idolbuser():
    """Single-row DataFrame missing idOLBUserTxns (D1 graceful degradation)."""
    row = _base_row()
    row.pop("idOLBUserTxns")
    return pd.DataFrame([row])


@pytest.fixture(scope="session")
def sample_input_no_createdat():
    """Single-row DataFrame missing createdAtTxns (D1 graceful degradation)."""
    row = _base_row()
    row["createdAtTxns"] = None
    return pd.DataFrame([row])
