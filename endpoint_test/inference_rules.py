# new-inference-final.py
# -------------------------------------------------------------------
# Endpoint inference script:
# - K-Means scoring
# - Optional: statistical rules (v8) with safe defaults (0) for missing fields
# - weekend se deriva SOLO para rules; NO entra al pipeline del modelo
# - Hybrid policy KMeans + Rules (Excel-style)
# - OUTPUT: todas las columnas preprocesadas solicitadas +
#           Cluster, Distance_to_Centroid, risk_score, risk_decision,
#           is_outlier(>=70), top_contributors, audit_category, audit_explanation, ux_copy
# - Parche: detección robusta de ColumnTransformer y tolerancia a feature mismatch
# -------------------------------------------------------------------

import os
import json
import re
import joblib
import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler
from scipy import sparse
from typing import Optional, Set, List, Tuple

# ---- Lazy import para reglas (opcionalmente desactivables con env DISABLE_RULES=1) ----
HAS_RULES = None
_rules_mod = None

def _ensure_rules_loaded() -> bool:
    global HAS_RULES, _rules_mod
    if HAS_RULES is not None:
        return HAS_RULES
    if os.getenv("DISABLE_RULES", "0") == "1":
        print("[RULES] Disabled by env var.")
        HAS_RULES = False
        return HAS_RULES
    try:
        print("[RULES] Attempting to import statistical_rules ...")
        import importlib
        _rules_mod = importlib.import_module("statistical_rules")
        assert hasattr(_rules_mod, "score_dataframe_v8"), "score_dataframe_v8 missing in statistical_rules"
        HAS_RULES = True
        print("[RULES] Loaded OK.")
    except Exception as e:
        HAS_RULES = False
        _rules_mod = None
        print(f"[RULES] Disabled. Reason: {repr(e)}")
    return HAS_RULES

# ---- Lazy import para similarity (opcionalmente desactivable con env DISABLE_SIMILARITY=1) ----
HAS_SIMILARITY = None
_similarity_mod = None

def _ensure_similarity_loaded() -> bool:
    global HAS_SIMILARITY, _similarity_mod
    if HAS_SIMILARITY is not None:
        return HAS_SIMILARITY
    if os.getenv("DISABLE_SIMILARITY", "0") == "1":
        print("[SIMILARITY] Disabled by env var.")
        HAS_SIMILARITY = False
        return HAS_SIMILARITY
    try:
        print("[SIMILARITY] Attempting to import similarity_matcher ...")
        import importlib
        _similarity_mod = importlib.import_module("similarity_matcher")
        assert hasattr(_similarity_mod, "find_similar_transaction"), "find_similar_transaction missing in similarity_matcher"
        HAS_SIMILARITY = True
        print("[SIMILARITY] Loaded OK.")
    except Exception as e:
        HAS_SIMILARITY = False
        _similarity_mod = None
        print(f"[SIMILARITY] Disabled. Reason: {repr(e)}")
    return HAS_SIMILARITY

# =========================
# Config & Validation
# =========================

TIME_FEATS = [
    "hour_sin", "hour_cos", "weekend", "is_night",
    "day_of_week_sin", "day_of_week_cos",
    "month_sin", "month_cos",
]

DTYPE_MAP = {
    # Identifiers
    "TransactionID": "int64",
    "idOLBUserTxns": "int64",
    "idFi": "object",

    # Core
    "amount": "float64",
    "TransactionProcessingType": "object",
    "TransactionOrigin": "object",
    "TransactionCategory": "object",

    # Batch
    "is_batch": "float64",
    "total_amount_batch": "float64",
    "num_recipients_batch": "float64",

    # Hist behavior windows
    "count_user_cancelled_txn_in_last_week": "int64",
    "count_user_cancelled_txn_in_last_month": "int64",
    "count_user_cancelled_txn_in_last_2_months": "int64",
    "count_user_potential_fraud_txn_in_last_week": "int64",
    "count_user_potential_fraud_txn_in_last_month": "int64",
    "count_user_potential_fraud_txn_in_last_2_months": "int64",
    "count_txn_to_recipient_account_in_last_week": "int64",
    "count_txn_to_recipient_account_in_last_month": "int64",
    "count_txn_to_recipient_account_in_last_2_months": "int64",
    "is_first_txn_from_this_olb_user_to_this_recipient_account_q_6h": "int64",
    "is_first_txn_from_this_account_to_recipient_account_q_72h": "int64",
    "count_all_txn_after_recipient_account_creation": "float64",

    # User ALL 6m
    "count_user_all_txn_in_last_6_months": "int64",
    "user_total_active_days_last_6_months": "int64",
    "total_amount_user_all_txn_in_last_6_months": "float64",
    "user_cancel_txn_rate_last_6_months": "float64",
    "user_avg_count_txn_per_active_day_last_6_months": "float64",
    "user_avg_amount_txn_per_active_day_last_6_months": "float64",

    # User ACH 6m
    "count_user_ach_txn_in_last_6_months": "int64",
    "user_total_ach_active_days_last_6_months": "int64",
    "total_amount_user_ach_txn_in_last_6_months": "float64",
    "user_cancel_ach_txn_rate_last_6_months": "float64",
    "user_avg_count_ach_txn_per_active_day_last_6_months": "float64",
    "user_avg_amount_ach_txn_per_active_day_last_6_months": "float64",

    # Amount patterns (6m)
    "amount_coef_var_lst6m": "float64",
    "pct_txns_under_100_lst6m": "float64",
    "pct_txns_over_1k_lst6m": "float64",

    # Profile / updates
    "is_personal_user_phone_primary_updated_last_week": "float64",
    "is_personal_user_phone_primary_updated_last_month": "float64",
    "is_personal_user_email_primary_updated_last_week": "float64",
    "is_personal_user_email_primary_updated_last_month": "float64",
    "user_type": "object",
    "user_age": "float64",

    # Session
    "count_failed_actions_in_current_session": "float64",
    "count_suspected_actions_in_current_session": "float64",
    "total_actions_session": "float64",
    "is_auth_email_session": "float64",
    "is_auth_phone_session": "float64",

    # Portfolio
    "num_checking_accounts": "int64",
    "num_savings_accounts": "int64",
    "num_loan_accounts": "int64",
    "num_credit_card_accounts": "int64",
    "num_certificate_accounts": "int64",
    "num_open_ended_loans_accounts": "int64",
    "num_other_account": "int64",
    "total_accounts": "int64",

    # Recency
    "recency_user_created_days": "float64",
    "is_access_from_remembered_device": "float64",

    # Short-horizon
    "count_all_txn_last_5m": "int64",
    "total_amount_all_txn_last_5m": "float64",
    "count_txn_to_recipient_account_last_5m": "int64",
    "total_amount_txn_to_recipient_account_last_5m": "float64",
    "count_all_txn_last_30m": "int64",
    "total_amount_all_txn_last_30m": "float64",
    "count_txn_to_recipient_account_last_30m": "int64",

    # Extra cyclic
    "day_of_week_cos": "float64",
    "month_sin": "float64",

    # CU-level
    "cu_avg_amount_ach_txn_in_last_6_months": "float64",
    "is_amount_greater_than_cu_p95_amount_ach_txn_in_last_6_months": "int64",
    "txn_amount_vs_cu_avg_amount_ach_txn_in_last_6_months": "float64",

    # New selected
    "amt_vs_user_ach_avg_day": "float64",
    "ach_count_share_6m": "float64",

    # Raw timestamps (opcionales)
    "createdAtTxns": "object",
    "blossomUserCreatedAt": "object",
}

class ValidationError(Exception):
    pass

_ALLOWED_TS_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}(?:[ T](?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):?[0-5]\d)?)?$"
)
_DOTTED_TS_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}(?:\s+\d{2}\.\d{2}\.\d{2})?$")

def _clean_suffix(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.replace(r"\s+-\s+.*$", "", regex=True)

def _parse_created_strict(s: pd.Series):
    raw = _clean_suffix(s)
    is_empty = raw.eq("") | raw.isna()
    is_dotted = raw.str.match(_DOTTED_TS_RE, na=False)
    is_allowed = raw.str.match(_ALLOWED_TS_RE, na=False)
    is_disallowed_nonempty = (~is_empty) & (~is_allowed)
    to_parse = raw.where(is_allowed, None)
    parsed = pd.to_datetime(to_parse, errors="coerce", format=None)
    return parsed, is_dotted, is_disallowed_nonempty

def _coerce_numeric_strings_inplace(df: pd.DataFrame, cols: List[str]) -> None:
    for c in cols:
        if c not in df.columns:
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            continue
        s = df[c].astype(str)
        s = s.str.replace(r'^\s*\((.*)\)\s*$', r'-\1', regex=True)
        s = (s.str.replace('$', '', regex=False)
               .str.replace('%', '', regex=False)
               .str.replace(',', '', regex=False)
               .str.replace(' ', '', regex=False))
        df[c] = pd.to_numeric(s, errors='coerce')

def _txid_of(df: pd.DataFrame, i) -> str:
    if "TransactionID" in df.columns:
        v = df.at[i, "TransactionID"]
        try:
            return str(int(v))
        except Exception:
            return str(v)
    return "N/A"

def _print_err(df, row_idx, column, error, value):
    txid = _txid_of(df, row_idx)
    print(f"[VALIDATION][row={row_idx}][TransactionID={txid}] column='{column}' error='{error}' value={repr(value)}")

def validate_gate(df: pd.DataFrame,
                  mode: str = "filter",
                  columns_whitelist: Optional[Set[str]] = None,
                  enforce_time_rules: bool = True) -> pd.DataFrame:
    out = df.copy()
    errors_found = False
    row_bad = pd.Series(False, index=out.index, dtype=bool)

    # Cast/coerce (solo whitelist)
    for c, t in DTYPE_MAP.items():
        if c not in out.columns:
            continue
        if columns_whitelist is not None and c not in columns_whitelist:
            continue
        try:
            if t in ("float64", "int64"):
                s_raw = out[c]
                s = s_raw.astype(str)
                s = s.str.replace(r'^\s*\((.*)\)\s*$', r'-\1', regex=True)\
                     .str.replace('$', '', regex=False)\
                     .str.replace('%', '', regex=False)\
                     .str.replace(',', '', regex=False)\
                     .str.replace(' ', '', regex=False)
                coerced = pd.to_numeric(s, errors="coerce")
                nonempty = ~s_raw.astype(str).str.strip().eq("") & ~s_raw.isna()
                bad_mask = nonempty & coerced.isna()
                if bad_mask.any():
                    errors_found = True
                    for i in out.index[bad_mask]:
                        _print_err(out, i, c, "invalid_numeric", out.at[i, c])
                        row_bad.at[i] = True
                out[c] = coerced
            elif t == "object":
                out[c] = out[c].astype("string")
            else:
                out[c] = out[c].astype(t)
        except Exception as e:
            print(f"[VALIDATION][column='{c}'] cast_error='{e}'")
            errors_found = True
            row_bad[:] = True

    # Timestamps
    has_created_col = ("createdAtTxns" in out.columns) and out["createdAtTxns"].notna().any()
    if enforce_time_rules:
        has_all_time_feats = all(f in out.columns for f in TIME_FEATS)
        if not has_all_time_feats:
            if not has_created_col:
                raise ValidationError("Temporal rule not satisfied: provide 'createdAtTxns' or all time-derived features.")
            ts, dotted, disallowed = _parse_created_strict(out["createdAtTxns"])
            if dotted.any():
                errors_found = True
                for i in out.index[dotted]:
                    _print_err(out, i, "createdAtTxns", "dot_format_not_allowed", out.at[i, "createdAtTxns"])
                    row_bad.at[i] = True
            bad = disallowed | ts.isna()
            if bad.any():
                errors_found = True
                for i in out.index[bad]:
                    _print_err(out, i, "createdAtTxns", "invalid_datetime_or_empty", out.at[i, "createdAtTxns"])
                    row_bad.at[i] = True
            out["__createdAtTxns_dt"] = ts
        else:
            if has_created_col:
                ts, dotted, disallowed = _parse_created_strict(out["createdAtTxns"])
                if dotted.any():
                    for i in out.index[dotted]:
                        _print_err(out, i, "createdAtTxns", "dot_format_not_allowed", out.at[i, "createdAtTxns"])
                if disallowed.any():
                    for i in out.index[disallowed]:
                        _print_err(out, i, "createdAtTxns", "invalid_datetime_format", out.at[i, "createdAtTxns"])
                out["__createdAtTxns_dt"] = ts
    else:
        if "createdAtTxns" in out.columns:
            ts, _, _ = _parse_created_strict(out["createdAtTxns"])
            out["__createdAtTxns_dt"] = ts

    if errors_found:
        if mode == "strict":
            raise ValidationError("Validation errors found. See logs above.")
        elif mode == "filter":
            kept = out.loc[~row_bad].copy()
            dropped_n = int(row_bad.sum())
            kept_n = len(kept)
            print(f"[VALIDATION][FILTER] Dropping {dropped_n} bad rows, keeping {kept_n} good rows.")
            if kept_n == 0:
                raise ValidationError("All rows invalid after filtering.")
            for aux_col in ["__createdAtTxns_dt", "__blossomUserCreatedAt_dt"]:
                if aux_col in out.columns:
                    kept[aux_col] = out.loc[~row_bad, aux_col]
            return kept

    return out

# =========================
# Feature Engineering (solo si el modelo lo necesita)
# =========================

def _derive_time_features_if_needed_strict(df: pd.DataFrame, ts_col="__createdAtTxns_dt") -> None:
    if ts_col not in df.columns:
        return
    needed = ["is_night", "hour_sin", "hour_cos", "day_of_week_cos"]
    if not any(col not in df.columns for col in needed):
        return
    ts = df[ts_col]
    valid = ts.notna()
    if valid.sum() == 0:
        print("[TIME] Skipped deriving features: all timestamps are empty/NaT.")
        return
    hour = ts.dt.hour
    dow = ts.dt.dayofweek
    if "is_night" not in df.columns:
        isn = pd.Series(np.nan, index=df.index, dtype=float)
        isn[valid] = ((hour[valid] < 6) | (hour[valid] > 22)).astype(float)
        df["is_night"] = isn
    ang_hour = pd.Series(np.nan, index=df.index, dtype=float)
    ang_dow = pd.Series(np.nan, index=df.index, dtype=float)
    ang_hour[valid] = 2 * np.pi * (hour[valid].astype(float) / 24.0)
    ang_dow[valid] = 2 * np.pi * (dow[valid].astype(float) / 7.0)
    if "hour_sin" not in df.columns: df["hour_sin"] = np.sin(ang_hour)
    if "hour_cos" not in df.columns: df["hour_cos"] = np.cos(ang_hour)
    if "day_of_week_cos" not in df.columns: df["day_of_week_cos"] = np.cos(ang_dow)

def _derive_recency_user_created_if_needed_strict(df: pd.DataFrame, tx_col="__createdAtTxns_dt", uc_col="__blossomUserCreatedAt_dt") -> None:
    target_col = "recency_user_created_days"
    if target_col in df.columns and df[target_col].notna().any():
        return
    if tx_col not in df.columns or uc_col not in df.columns:
        return
    tx = df[tx_col]; uc = df[uc_col]
    valid = tx.notna() & uc.notna()
    if valid.sum() == 0:
        print("[RECENCY] Skipped recency_user_created_days: empty/NaT dates.")
        return
    delta_days = (tx[valid] - uc[valid]).dt.total_seconds() / 86400.0
    out = pd.Series(np.nan, index=df.index, dtype=float)
    out[valid] = pd.to_numeric(delta_days, errors="coerce").clip(lower=0)
    df[target_col] = out

def _derive_is_batch_if_needed(df: pd.DataFrame) -> None:
    if "is_batch" in df.columns or "TransactionCategory" not in df.columns:
        return
    batch_set = {"SEND_MONEY_PAYROLL_ACH", "SEND_MONEY_BATCH_PAYMENT_ACH"}
    df["is_batch"] = df["TransactionCategory"].astype(str).isin(batch_set).astype(float)

# =========================
# Model / Artifacts
# =========================

def build_scaler(params):
    scaler = MinMaxScaler(feature_range=tuple(params['feature_range']))
    scaler.min_ = np.array(params['min_'])
    scaler.scale_ = np.array(params['scale_'])
    scaler.data_min_ = np.array(params['data_min'])
    scaler.data_max_ = np.array(params['data_max'])
    scaler.feature_range = tuple(params['feature_range'])
    return scaler

def classify_risk(score: int) -> str:
    if score >= 90:
        return "Reject"
    elif score >= 80:
        return "Admin Review"
    elif score >= 70:
        return "User Auth"
    else:
        return "Accept"

def map_decision_to_status(decision: str) -> str:
    """Map internal risk_decision to SAFE/RISKY status for similarity matching."""
    if decision in ["Reject", "Admin Review", "User Auth"]:
        return "RISKY"
    else:  # Accept
        return "SAFE"

def classify_outlier(score: int) -> int:
    return 1 if (score is not None and int(score) >= 70) else 0

def get_top_contributors(row, centroid, excluded=None, top_n=3):
    abs_diff = np.abs(row[centroid.index] - centroid)
    return abs_diff.sort_values(ascending=False).head(top_n).index.tolist()

# =========================
# Audit helpers (por top_contributors)
# =========================

def classify_outlier_reason(top_variables):
    if any(f in top_variables for f in ['num__amount']):
        return 'High-Amount Transaction'
    if any(f in top_variables for f in [
        'num__is_first_txn_from_this_olb_user_to_this_recipient_account_q_6h'
    ]):
        return 'First-Time Recipient Behavior'
    if any(f in top_variables for f in [
        'num__count_txn_to_recipient_account_last_5m',
        'num__count_txn_to_recipient_account_in_last_2_months'
    ]):
        return 'Recipient Velocity Spike'
    if any(f in top_variables for f in [
        'num__is_night', 'num__hour_sin', 'num__hour_cos', 'num__day_of_week_cos'
    ]):
        return 'Unusual Time of Access'
    if any(f in top_variables for f in [
        'cat__TransactionProcessingType_Schedule',
        'cat__TransactionProcessingType_Recurrent',
        'cat__TransactionProcessingType_Intime_From_Recurrent',
        'cat__TransactionProcessingType_Intime',
        'cat__TransactionOrigin_M2m External',
        'cat__TransactionOrigin_Internal External',
        'cat__TransactionOrigin_External Internal',
        'cat__TransactionCategory_SEND_MONEY_ACH',
        'cat__TransactionCategory_SEND_MONEY_BATCH_PAYMENT_ACH',
        'cat__TransactionCategory_SEND_MONEY_PAYROLL_ACH',
        'cat__TransactionCategory_SINGLE_COLLECTION_ACH',
        'cat__TransactionCategory_TRANSFER_EXTERNAL_TO_LOAN_ACH',
        'cat__TransactionCategory_TRANSFER_INTERNAL_EXTERNAL_ACH',
    ]):
        return 'Transaction Type/Origin Irregularity'
    if any(f in top_variables for f in ["num__is_batch"]):
        return 'Batch Payment Anomaly'
    if any(f in top_variables for f in [
        "num__count_user_cancelled_txn_in_last_week",
        "num__count_user_cancelled_txn_in_last_month",
        "num__count_user_potential_fraud_txn_in_last_2_months",
    ]):
        return 'Risk History Anomaly'
    if any(f in top_variables for f in [
        "num__is_amount_greater_than_cu_p95_amount_ach_txn_in_last_6_months",
        "num__txn_amount_vs_cu_avg_amount_ach_txn_in_last_6_months",
        "num__amt_vs_user_ach_avg_day",
    ]):
        return "Benchmark/Peer Deviation"
    if any(f in top_variables for f in [
        "num__count_user_all_txn_in_last_6_months",
        "num__user_avg_amount_txn_per_active_day_last_6_months",
        "num__ach_count_share_6m",
    ]):
        return "Activity Intensity Shift"
    if any(f in top_variables for f in [
        "num__pct_txns_under_100_lst6m",
        "num__pct_txns_over_1k_lst6m",
        "num__amount_coef_var_lst6m",
    ]):
        return "Amount Pattern Irregularity"
    if any(f in top_variables for f in [
        "num__recency_user_created_days",
        "num__is_auth_phone_session",
        "num__is_auth_email_session",
        "num__count_suspected_actions_in_current_session",
        "num__total_actions_session",
    ]):
        return "Identity / Session Signals"
    if any(f in top_variables for f in ['cat__access_DESKTOP', 'cat__access_MOBILE', 'cat__access_missing']):
        return 'Unusual Access Pattern'
    if any(f in top_variables for f in ['num__total_accounts', 'num__user_age', 'cat__user_type_mixed', 'cat__user_type_personal']):
        return 'Portfolio / Tenure Shift'
    return 'Other / Mixed Anomaly'

def create_explanation_text(category, top_vars):
    if not top_vars:
        return "Outlier detected, but no contributing variables found."
    return f"Outlier due to {category.lower()} (Top variables: {', '.join(top_vars)})"

def build_ux_copy(audit_category: str, top_vars: List[str]) -> List[str]:
    CATEGORY_MAP = {
        "High-Amount Transaction": {
            "exact": {"num__amount": "High transaction amount"},
            "prefix": {}
        },
        "First-Time Recipient Behavior": {
            "exact": {
                "num__is_first_txn_from_this_olb_user_to_this_recipient_account_q_6h":
                    "Member's first transaction to the recipient",
            },
            "prefix": {}
        },
        "Recipient Velocity Spike": {
            "exact": {
                "num__count_txn_to_recipient_account_last_5m":
                    "Number of transactions made to the recipient in the last 5 minutes",
                "num__count_txn_to_recipient_account_in_last_2_months":
                    "Transactions made to the recipient account in the last 2 months",
                "num__total_amount_txn_to_recipient_account_last_5m":
                    "Total amount sent to the recipient account in the last 5 minutes",
            },
            "prefix": {}
        },
        "Transaction Velocity Spike": {
            "exact": {
                "num__count_all_txn_last_5m": "Unusual number of transactions made in 5 minutes",
                "num__total_amount_all_txn_last_5m": "Total amount sent in the 5 minutes",
            },
            "prefix": {}
        },
        "Unusual Time of Access": {
            "exact": {
                "num__is_night": "Activity at unusual day and hours",
                "num__hour_sin": "Activity at unusual day and hours",
                "num__hour_cos": "Activity at unusual day and hours",
                "num__day_of_week_cos": "Activity at unusual day and hours",
            },
            "prefix": {}
        },
        "Transaction Type/Origin Irregularity": {
            "exact": {
                "cat__TransactionProcessingType_Schedule": "Unusual scheduled transaction type",
                "cat__TransactionProcessingType_Recurrent": "Unusual recurrent transaction type",
                "cat__TransactionProcessingType_Intime_From_Recurrent": "Unusual In-time transaction from a recurrent type",
                "cat__TransactionProcessingType_Intime": "Unusual In-time transaction type",
                "cat__TransactionOrigin_M2m External": "Unusual member to member external transaction origin",
                "cat__TransactionOrigin_Internal External": "Unusual internal to external transaction origin",
                "cat__TransactionOrigin_External Internal": "Unusual external to internal transaction origin",
                "cat__TransactionCategory_SEND_MONEY_ACH": "Unusual send money transaction via ACH",
                "cat__TransactionCategory_SEND_MONEY_BATCH_PAYMENT_ACH": "Unusual batch transaction type via ACH",
                "cat__TransactionCategory_SEND_MONEY_PAYROLL_ACH": "Unusual payroll transaction via ACH",
                "cat__TransactionCategory_SINGLE_COLLECTION_ACH": "Unusual single collection transaction via ACH",
                "cat__TransactionCategory_TRANSFER_EXTERNAL_TO_LOAN_ACH": "Unusual transaction from external account to loan via ACH",
                "cat__TransactionCategory_TRANSFER_INTERNAL_EXTERNAL_ACH": "Unusual transaction from internal to external account via ACH",
            },
            "prefix": {
                "cat__TransactionProcessingType_": "Unusual transaction processing type",
                "cat__TransactionOrigin_": "Unusual transaction origin",
                "cat__TransactionCategory_": "Unusual transaction category",
            }
        },
        "Batch Payment Anomaly": {
            "exact": {"num__is_batch": "Unusual batch transaction"},
            "prefix": {}
        },
        "Risk History Anomaly": {
            "exact": {
                "num__count_user_cancelled_txn_in_last_week": "Cancelled transactions by the member in the week",
                "num__count_user_cancelled_txn_in_last_month": "Cancelled transactions by the member in the month",
                "num__count_user_potential_fraud_txn_in_last_2_months": "Potential fraud transactions by the member in the last 2 months",
            },
            "prefix": {}
        },
        "Benchmark/Peer Deviation": {
            "exact": {
                "num__is_amount_greater_than_cu_p95_amount_ach_txn_in_last_6_months": "Amount greater than the CU benchmark of ACH transactions in 6 months",
                "num__txn_amount_vs_cu_avg_amount_ach_txn_in_last_6_months": "ACH transaction amount deviates from 6-month CU benchmark average",
                "num__amt_vs_user_ach_avg_day": "ACH transaction amount deviates from user overall ACH daily average amount",
            },
            "prefix": {}
        },
        "Activity Intensity Shift": {
            "exact": {
                "num__count_user_all_txn_in_last_6_months": "Unusual frequency transactions in last 6 months",
                "num__user_avg_amount_txn_per_active_day_last_6_months": "Transaction amount deviates from the last 6 months daily average across all rails",
                "num__ach_count_share_6m": "Unusual ACH transaction share in the last 6 months",
            },
            "prefix": {}
        },
        "Amount Pattern Irregularity": {
            "exact": {
                "num__pct_txns_under_100_lst6m": "Percentage of transactions under $100 in the last 6 months",
                "num__pct_txns_over_1k_lst6m": "Percentage of transactions over $1,000 in the last 6 months",
                "num__amount_coef_var_lst6m": "Transaction amount coefficient of variation in the last 6 months",
            },
            "prefix": {}
        },
        "Identity / Session Signals": {
            "exact": {
                "num__recency_user_created_days": "Suspicious transaction day due to recent account creation",
                "num__is_auth_phone_session": "Unusual session authenticated with phone",
                "num__is_auth_email_session": "Unusual session authenticated with email",
                "num__count_suspected_actions_in_current_session": "Suspected actions in the current session",
                "num__total_actions_session": "Unusual number of actions in the current session",
            },
            "prefix": {}
        },
        "Unusual Access Pattern": {
            "exact": {
                "cat__access_DESKTOP": "Unusual desktop access",
                "cat__access_MOBILE": "Unusual mobile access",
                "cat__access_missing": "Unusual missing access type",
            },
            "prefix": {"cat__access_": "Unusual access pattern"}
        },
        "Portfolio / Tenure Shift": {
            "exact": {
                "num__total_accounts": "Unusual total number of accounts",
                "cat__user_type_mixed": "Unusual member business behavior",
                "cat__user_type_personal": "Unusual member personal behavior",
                "num__user_age": "Unusual age behavior",
            },
            "prefix": {}
        },
        "Other / Mixed Anomaly": {
            "exact": {},
            "prefix": {}
        },
    }
    FALLBACK = {
        "High-Amount Transaction": ["High transaction amount"],
        "First-Time Recipient Behavior": ["First-time recipient behavior"],
        "Recipient Velocity Spike": ["Recipient-related velocity anomaly"],
        "Transaction Velocity Spike": ["Overall transaction velocity anomaly"],
        "Unusual Time of Access": ["Activity at unusual day and hours"],
        "Transaction Type/Origin Irregularity": ["Unusual transaction type/origin/category"],
        "Batch Payment Anomaly": ["Unusual batch transaction"],
        "Risk History Anomaly": ["Risk-related history anomaly"],
        "Benchmark/Peer Deviation": ["Benchmark/peer deviation"],
        "Activity Intensity Shift": ["Activity intensity shift"],
        "Amount Pattern Irregularity": ["Amount pattern irregularity"],
        "Identity / Session Signals": ["Identity/session-related signals"],
        "Unusual Access Pattern": ["Unusual access pattern"],
        "Portfolio / Tenure Shift": ["Portfolio/tenure shift"],
        "Other / Mixed Anomaly": ["Mixed pattern anomaly"],
    }

    cat_cfg = CATEGORY_MAP.get(audit_category, {"exact": {}, "prefix": {}})
    texts = []

    for v in top_vars or []:
        if v in cat_cfg["exact"]:
            texts.append(cat_cfg["exact"][v])

    if cat_cfg["prefix"]:
        for v in top_vars or []:
            for pref, msg in cat_cfg["prefix"].items():
                if v.startswith(pref):
                    texts.append(msg)

    # Dedup
    seen, uniq = set(), []
    for t in texts:
        if t not in seen:
            uniq.append(t)
            seen.add(t)

    if not uniq:
        uniq = FALLBACK.get(audit_category, ["Mixed pattern anomaly"])
    return uniq

# =========================
# Hybrid helpers
# =========================

_BANDS = {
    "Accept": (0, 69),
    "User Auth": (70, 79),
    "Admin Review": (80, 89),
    "Reject": (90, 100),
}

def _clamp_to_band(score: int, decision: str) -> int:
    lo, hi = _BANDS.get(decision, (0, 100))
    s = 0 if pd.isna(score) else int(round(score))
    return max(lo, min(hi, s))

def _step_up(decision: str) -> str:
    order = ["Accept", "User Auth", "Admin Review", "Reject"]
    i = order.index(decision) if decision in order else 0
    return order[min(i + 1, len(order) - 1)]

def combine_kmeans_and_rules(k_score: int, k_dec: str, r_score: int, r_dec: str) -> str:
    if r_dec == "Reject" and r_score >= 90:
        return "Reject"
    if r_dec == "Admin Review":
        if k_dec == "Accept":
            return "User Auth"
        if k_dec == "User Auth":
            return "Admin Review"
        if k_dec == "Admin Review":
            return "Reject"
        return "Reject"
    if r_dec == "User Auth" and k_dec == "Accept" and r_score >= 80:
        return "User Auth"
    return k_dec

# =========================
# SageMaker entrypoints
# =========================

def model_fn(model_dir):
    print("[BOOT] Starting model_fn. model_dir:", model_dir)
    try:
        print("[BOOT] Files in model_dir:", os.listdir(model_dir))
    except Exception as e:
        print("[BOOT] Could not list model_dir:", e)
    model = joblib.load(os.path.join(model_dir, "kmeans_model.joblib"))
    pipeline = joblib.load(os.path.join(model_dir, "preprocessing_pipeline.joblib"))
    selected = pd.read_csv(os.path.join(model_dir, "selected_features.csv"))
    if 'Unnamed: 0' in selected.columns:
        selected = selected.drop(columns=['Unnamed: 0'])
    selected = selected[selected["selected_features"] != "Unnamed: 0"]
    selected_features = selected["selected_features"].dropna().tolist()

    centroids_df = pd.read_csv(os.path.join(model_dir, "centroids.csv"))
    centroids_df.index = centroids_df.index.astype(int)

    with open(os.path.join(model_dir, "kmeans_artifacts.json")) as f:
        artifacts = json.load(f)

    scalers_below = {int(k): build_scaler(v) for k, v in artifacts['scalers_below'].items()}
    scalers_above = {int(k): build_scaler(v) for k, v in artifacts['scalers_above'].items()}
    thresholds = {int(k): v for k, v in artifacts['thresholds_by_cluster'].items()}

    print("[BOOT] pipeline steps:", list(getattr(pipeline, "named_steps", {}).keys()))
    print("[BOOT] selected_features (n):", len(selected_features))
    print("[BOOT] sample selected_features:", selected_features[:10])
    print("[BOOT] centroids shape:", centroids_df.shape)
    print("[BOOT] scalers_below keys:", list(scalers_below.keys()))
    print("[BOOT] scalers_above keys:", list(scalers_above.keys()))
    print("[BOOT] thresholds keys:", list(thresholds.keys()))

    return {
        "model": model,
        "pipeline": pipeline,
        "selected": selected_features,
        "centroids": centroids_df,
        "scalers_below": scalers_below,
        "scalers_above": scalers_above,
        "thresholds": thresholds
    }

def input_fn(request_body, content_type='text/csv'):
    print("[IN] content_type:", content_type)
    if content_type == 'text/csv':
        from io import StringIO
        return pd.read_csv(StringIO(request_body))
    else:
        raise ValueError(f"Unsupported content type: {content_type}")

def predict_fn(input_data, model_artifacts):
    print("[PRED] start")
    # 0) Load artifacts
    model = model_artifacts["model"]
    pipeline = model_artifacts["pipeline"]
    selected_features = model_artifacts["selected"]
    centroids_df = model_artifacts["centroids"]
    scalers_below = model_artifacts["scalers_below"]
    scalers_above = model_artifacts["scalers_above"]
    thresholds = model_artifacts["thresholds"]

    # --- Column whitelist desde selected (bases num/cat)
    selected_num_bases = {c.replace("num__", "") for c in selected_features if c.startswith("num__")}
    selected_cat_bases = set()
    for c in selected_features:
        if c.startswith("cat__"):
            tail = c.replace("cat__", "")
            base = tail.split("_", 1)[0]
            selected_cat_bases.add(base)
    columns_whitelist = set(selected_num_bases) | set(selected_cat_bases)

    # Derivaciones necesarias
    TIME_BASES = {"weekend","is_night","hour_sin","hour_cos","day_of_week_sin","day_of_week_cos","month_sin","month_cos"}
    need_time = any(b in TIME_BASES for b in selected_num_bases)
    need_recency = "recency_user_created_days" in selected_num_bases
    need_is_batch = "is_batch" in selected_num_bases

    if need_time or need_recency:
        columns_whitelist.add("createdAtTxns")
    if need_recency:
        columns_whitelist.add("blossomUserCreatedAt")
    if need_is_batch:
        columns_whitelist.add("TransactionCategory")

    # 1) Validación y preservar TransactionID
    df = validate_gate(input_data, mode="filter", columns_whitelist=columns_whitelist, enforce_time_rules=(need_time or need_recency))
    
    # Preserve TransactionID from input for later use
    transaction_ids = []
    if "TransactionID" in input_data.columns:
        transaction_ids = input_data["TransactionID"].tolist()
    else:
        transaction_ids = list(range(len(df)))

    # 2) Derivar SOLO lo que el modelo necesita
    if need_time:
        _derive_time_features_if_needed_strict(df, ts_col="__createdAtTxns_dt")
    if need_recency:
        _derive_recency_user_created_if_needed_strict(df, tx_col="__createdAtTxns_dt", uc_col="__blossomUserCreatedAt_dt")
    if need_is_batch:
        _derive_is_batch_if_needed(df)

    # 3) Obtener ColumnTransformer robustamente
    preprocessor = None
    if hasattr(pipeline, "named_steps") and "preprocessor" in pipeline.named_steps:
        preprocessor = pipeline.named_steps["preprocessor"]
    else:
        for name, step in getattr(pipeline, "named_steps", {}).items():
            if hasattr(step, "get_feature_names_out"):
                preprocessor = step
                print(f"[PRED] using ColumnTransformer step: {name}")
                break
    if preprocessor is None:
        raise ValueError("No ColumnTransformer with get_feature_names_out found in pipeline.")

    num_cols_all = preprocessor.transformers_[0][2]
    cat_cols_all = preprocessor.transformers_[1][2]
    num_base_cols = [col.replace("num__", "") for col in num_cols_all]
    cat_base_cols = [col.replace("cat__", "") for col in cat_cols_all]
    all_base_needed = num_base_cols + cat_base_cols

    # 4) Asegurar existencia de columnas base
    for col in num_base_cols:
        if col not in df.columns:
            df[col] = np.nan
    for col in cat_base_cols:
        if col not in df.columns:
            df[col] = ''
        else:
            df[col] = df[col].astype(str)

    _coerce_numeric_strings_inplace(df, num_base_cols)

    # 5) Transform y tolerancia al mismatch
    df_ordered = df[all_base_needed]
    X = pipeline.transform(df_ordered)
    if sparse.issparse(X):
        X = X.toarray()

    feature_names = list(preprocessor.get_feature_names_out())
    if X.shape[1] != len(feature_names):
        print(f"[PRED][WARN] Feature mismatch: X={X.shape[1]} vs names={len(feature_names)}. Will align.")
        m = min(X.shape[1], len(feature_names))
        df_transformed = pd.DataFrame(X[:, :m], columns=feature_names[:m])
        if len(feature_names) > m:
            for extra in feature_names[m:]:
                df_transformed[extra] = 0.0
    else:
        df_transformed = pd.DataFrame(X, columns=feature_names)

    # 6) Asegurar selected_features (dummies no vistos)
    for c in selected_features:
        if c not in df_transformed.columns:
            df_transformed[c] = 0.0

    # 7) K-Means
    df_selected = df_transformed[selected_features].copy()
    df_selected["Cluster"] = model.predict(df_selected)
    distances = model.transform(df_selected[selected_features])
    df_selected["Distance_to_Centroid"] = [dist[int(cl)] for dist, cl in zip(distances, df_selected["Cluster"])]

    # 8) Scoring por clúster
    df_selected["risk_score"] = np.nan
    for cluster in df_selected["Cluster"].unique():
        mask = df_selected["Cluster"] == cluster
        threshold = thresholds.get(int(cluster), np.inf)
        below = mask & (df_selected["Distance_to_Centroid"] <= threshold)
        above = mask & (df_selected["Distance_to_Centroid"] > threshold)
        if below.any() and int(cluster) in scalers_below:
            vals = df_selected.loc[below, ["Distance_to_Centroid"]].astype(float)
            df_selected.loc[below, "risk_score"] = scalers_below[int(cluster)].transform(vals).ravel()
        if above.any() and int(cluster) in scalers_above:
            vals = df_selected.loc[above, ["Distance_to_Centroid"]].astype(float)
            df_selected.loc[above, "risk_score"] = scalers_above[int(cluster)].transform(vals).ravel()

    df_selected["risk_score"] = df_selected["risk_score"].clip(0, 100).round().astype("Int64")
    df_selected["risk_decision"] = df_selected["risk_score"].apply(classify_risk)

    # 9) Explainability (top contributors)
    results = []
    try:
        dtype_target = df_selected[selected_features].dtypes.iloc[0]
        centroids_aligned = centroids_df[selected_features].astype(dtype_target)
    except Exception:
        centroids_aligned = centroids_df.reindex(columns=selected_features)

    for idx, row in df_selected.iterrows():
        row_dict = row.to_dict()
        cluster = int(row_dict["Cluster"])
        if cluster in centroids_aligned.index:
            centroid = centroids_aligned.loc[cluster]
            row_feats = row[selected_features]
            top_vars = get_top_contributors(row_feats, centroid, top_n=3)
        else:
            top_vars = []
        # defaults por top contributors (se ajustarán si rules cambian la decisión)
        reason = classify_outlier_reason(top_vars)
        row_dict.update({
            "top_contributors": top_vars,
            #"audit_category": reason if pd.notna(row_dict.get("risk_score")) and int(row_dict.get("risk_score")) >= 70 else "No anomaly",
            #"audit_explanation": create_explanation_text(reason, top_vars) if pd.notna(row_dict.get("risk_score")) and int(row_dict.get("risk_score")) >= 70 else "Within  normal behavioral range.",
            #"ux_copy": build_ux_copy(reason, top_vars) if pd.notna(row_dict.get("risk_score")) and int(row_dict.get("risk_score")) >= 70 else []
            "audit_category": reason,  # Se recalculará basándose en el risk_score final
            "audit_explanation": create_explanation_text(reason, top_vars),  # Se recalculará basándose en el risk_score final  
            "ux_copy": build_ux_copy(reason, top_vars)  # Se recalculará basándose en el risk_score final
        })
        results.append(row_dict)

    out_df = pd.DataFrame(results)
    out_df.index = df.index

    # ===== Reglas (opcional) =====
    rules_df = None
    if _ensure_rules_loaded():
        df_rules = df.copy()
        # defaults seguros para cols opcionales de reglas
        for c in ["is_personal_user_phone_primary_updated_last_week",
                  "is_personal_user_email_primary_updated_last_week"]:
            if c not in df_rules.columns:
                df_rules[c] = 0
            df_rules[c] = pd.to_numeric(df_rules[c], errors="coerce").fillna(0).astype(int)

        if "__createdAtTxns_dt" not in df_rules.columns and "createdAtTxns" in df_rules.columns:
            ts, _, _ = _parse_created_strict(df_rules["createdAtTxns"])
            df_rules["__createdAtTxns_dt"] = ts

        # weekend solo para rules
        if "weekend" not in df_rules.columns:
            df_rules["weekend"] = 0
        if "__createdAtTxns_dt" in df_rules.columns and df_rules["__createdAtTxns_dt"].notna().any():
            wd = df_rules["__createdAtTxns_dt"].dt.weekday
            df_rules.loc[wd >= 5, "weekend"] = 1
            df_rules.loc[wd < 5, "weekend"] = 0

        try:
            scored_rules = _rules_mod.score_dataframe_v8(df_rules)
            rule_cols = [f"rule_{i}" for i in range(1, 13)]
            keep_cols = (["TransactionID", "amount"] + rule_cols +
                         ["risk_score_raw", "risk_score_clipped", "risk_score_normalized",
                          "risk_decision", "explanation"])
            keep_cols = [c for c in keep_cols if c in scored_rules.columns]
            rules_df = scored_rules[keep_cols].copy()
            rename_map = {c: f"rules_{c}" for c in rules_df.columns if c != "TransactionID"}
            rules_df.rename(columns=rename_map, inplace=True)
            if "rules_risk_score_normalized" in rules_df.columns:
                rules_df.rename(columns={"rules_risk_score_normalized": "rules_risk_score"}, inplace=True)
            for c in rules_df.columns:
                if c.startswith("rules_rule_") or c in {"rules_risk_score_raw", "rules_risk_score_clipped", "rules_risk_score"}:
                    rules_df[c] = pd.to_numeric(rules_df[c], errors="coerce")
        except Exception as e:
            print(f"[RULES] Skipped rules scoring due to error: {repr(e)}")
            rules_df = None

    # ===== Hybrid =====
    if rules_df is not None:
        if "TransactionID" in out_df.columns and "TransactionID" in rules_df.columns:
            merged = out_df.merge(rules_df, on="TransactionID", how="left")
        else:
            out_df = out_df.reset_index(drop=False).rename(columns={"index": "__row_id"})
            rules_df = rules_df.reset_index(drop=False).rename(columns={"index": "__row_id"})
            merged = out_df.merge(rules_df, on="__row_id", how="left")
        def _hyb(r):
            k_score = int(r.get("risk_score", 0)) if pd.notna(r.get("risk_score", np.nan)) else 0
            k_dec = str(r.get("risk_decision", "Accept") or "Accept")
            r_score = int(r.get("rules_risk_score", 0)) if pd.notna(r.get("rules_risk_score", np.nan)) else 0
            r_dec = str(r.get("rules_risk_decision", "Accept") or "Accept")
            return combine_kmeans_and_rules(k_score, k_dec, r_score, r_dec)
        merged["hybrid_decision"] = merged.apply(_hyb, axis=1)
        out_df = merged

    # --- Hacer oficial hybrid + score numérico alineado ---
    out_df["kmeans_risk_score"] = out_df["risk_score"]
    out_df["kmeans_risk_decision"] = out_df["risk_decision"]
    if "hybrid_decision" in out_df.columns:
        out_df["risk_decision"] = out_df["hybrid_decision"]

    def _hyb_score_row(r):
        k_score = int(r.get("kmeans_risk_score", 0)) if pd.notna(r.get("kmeans_risk_score", np.nan)) else 0
        k_dec   = str(r.get("kmeans_risk_decision", "Accept") or "Accept")
        r_score = int(r.get("rules_risk_score", 0)) if pd.notna(r.get("rules_risk_score", np.nan)) else 0
        r_dec   = str(r.get("rules_risk_decision", "Accept") or "Accept")
        if r_dec == "Reject" and r_score >= 90:
            return max(k_score, _clamp_to_band(r_score, "Reject"))
        if r_dec == "Admin Review":
            target = _step_up(k_dec)
            return max(k_score, _clamp_to_band(r_score, target))
        if r_dec == "User Auth" and k_dec == "Accept" and r_score >= 80:
            return max(k_score, _clamp_to_band(r_score, "User Auth"))
        return k_score

    out_df["risk_score"] = out_df.apply(_hyb_score_row, axis=1).astype(int)
    out_df["is_outlier"] = out_df["risk_score"].apply(classify_outlier)

    # ===== Ajuste de audit y ux_copy: por defecto por top_contributors; SOLO Mixed si cambió por rules =====
    #changed_by_rules = (out_df["risk_decision"] != out_df["kmeans_risk_decision"]) if "kmeans_risk_decision" in out_df.columns else pd.Series(False, index=out_df.index)

    # Para filas cambiadas por rules → Mixed
    #mask_rules = changed_by_rules.fillna(False)
    #out_df.loc[mask_rules, "audit_category"] = "Other / Mixed Anomaly"
    #out_df.loc[mask_rules, "audit_explanation"] = "Decision elevated by statistical rules."
    #out_df.loc[mask_rules, "ux_copy"] = [["Mixed pattern anomaly"]] * int(mask_rules.sum())

    # Para el resto, respetar lo que venía de top_contributors;
    # si score<70, asegurar "No anomaly" y ux vacío (ya se seteó arriba).
    #mask_not_rules = ~mask_rules
    #mask_risky = mask_not_rules & (out_df["risk_score"] >= 70)
    # Recalcular por si el score final cambió de <70 a >=70 sin cambiar por rules
    #def _rebuild_when_needed(r):
    #    if r["risk_score"] < 70:
    #        return ("No anomaly", "Within normal behavioral range.", [])
    #    # score >= 70: usar top contributors
    #    tops = r.get("top_contributors", []) or []
    #    cat = classify_outlier_reason(tops)
    #    expl = create_explanation_text(cat, tops)
    #    ux = build_ux_copy(cat, tops)
    #    return (cat, expl, ux)
    #out_df.loc[mask_not_rules, ["audit_category","audit_explanation","ux_copy"]] = out_df.loc[mask_not_rules].apply(
    #    lambda r: pd.Series(_rebuild_when_needed(r)), axis=1
    #)

    def _rebuild_audit_columns(r):
        # SIEMPRE usar top contributors (mantener lógica original del K-means)
        # independientemente del score final (tanto < 70 como >= 70)
        tops = r.get("top_contributors", []) or []
        cat = classify_outlier_reason(tops)
        expl = create_explanation_text(cat, tops)
        ux = build_ux_copy(cat, tops)
        return (cat, expl, ux)

    # Aplicar a TODAS las filas para garantizar que no queden vacías
    # y que mantengan la consistencia con new-inference-last.py
    out_df[["audit_category","audit_explanation","ux_copy"]] = out_df.apply(
        lambda r: pd.Series(_rebuild_audit_columns(r)), axis=1
    )

    # ===== Similarity Matching (MANDATORY) =====
    similarity_results = []
    similarity_threshold = float(os.getenv("SIMILARITY_THRESHOLD", "0.90"))
    s3_bucket = os.getenv("SIMILARITY_S3_BUCKET", "blossom-analytics-safe-dev-nv")
    s3_key = os.getenv("SIMILARITY_S3_KEY", "safe_txns/similarity/data/wp_similarity.csv")  # CSV file
    
    if _ensure_similarity_loaded():
        print(f"[SIMILARITY] Checking similarity for {len(out_df)} transactions (threshold: {similarity_threshold})")
        
        for idx, row in out_df.iterrows():
            # Prepare query with ONLY features (num__ and cat__), NOT post-processing fields
            query_features = {}
            
            # Add all num__ and cat__ features from df_transformed
            for col in df_transformed.columns:
                if col.startswith("num__") or col.startswith("cat__"):
                    val = df_transformed.loc[idx, col]
                    query_features[col] = float(val) if pd.notna(val) else 0.0
            
            # DO NOT add post-processing fields (Cluster, Distance_to_Centroid, risk_score, etc.)
            # These are generated by K-means and should not affect similarity matching
            
            # Call similarity matcher
            try:
                result = _similarity_mod.find_similar_transaction(
                    query_result=query_features,
                    threshold=similarity_threshold,
                    s3_bucket=s3_bucket,
                    s3_key=s3_key,
                    top_k=5
                )
                
                # Extract results from dictionary
                matched = result.get("matched", False)
                similarity_score = result.get("similarity_score", 0.0)
                status_warning = result.get("status_warning", "NONE")
                matched_txn_id = result.get("matched_transaction_id", None)
                top_matches = result.get("top_matches", [])
                
                # Log match if found
                if matched:
                    print(f"[SIMILARITY] Row {idx}: Match found (score: {similarity_score:.4f}, matched_id: {matched_txn_id})")
                
                # Store only 3 fields: TransactionID, matched_transaction_id, similarity_score
                similarity_result = {
                    "TransactionID": transaction_ids[idx] if idx < len(transaction_ids) else None,
                    "matched_transaction_id": matched_txn_id,
                    "similarity_score": float(similarity_score) if similarity_score is not None else 0.0
                }
                
            except Exception as e:
                print(f"[SIMILARITY] Error processing row {idx}: {repr(e)}")
                similarity_result = {
                    "TransactionID": transaction_ids[idx] if idx < len(transaction_ids) else None,
                    "matched_transaction_id": None,
                    "similarity_score": 0.0
                }
            
            similarity_results.append(similarity_result)
    else:
        print("[SIMILARITY] Module not available, skipping similarity matching")
        # Add empty similarity results
        for idx in range(len(out_df)):
            similarity_results.append({
                "TransactionID": transaction_ids[idx] if idx < len(transaction_ids) else None,
                "matched_transaction_id": None,
                "similarity_score": 0.0
            })
    
    # Similarity matching completed (results used internally for decision override)
    # similarity_info is NOT included in final output

    # ===== Construcción del payload final solicitado =====
    requested_cols = [
        # NUM
        "num__amount","num__is_night","num__hour_sin","num__hour_cos","num__day_of_week_cos",
        "num__count_all_txn_last_5m","num__total_amount_all_txn_last_5m",
        "num__count_txn_to_recipient_account_last_5m","num__total_amount_txn_to_recipient_account_last_5m",
        "num__count_txn_to_recipient_account_in_last_2_months",
        "num__is_first_txn_from_this_olb_user_to_this_recipient_account_q_6h",
        "num__amount_coef_var_lst6m","num__pct_txns_under_100_lst6m","num__pct_txns_over_1k_lst6m",
        "num__user_avg_amount_txn_per_active_day_last_6_months","num__count_user_all_txn_in_last_6_months",
        "num__count_user_cancelled_txn_in_last_week","num__count_user_cancelled_txn_in_last_month",
        "num__count_user_potential_fraud_txn_in_last_2_months","num__recency_user_created_days",
        "num__count_suspected_actions_in_current_session","num__total_actions_session",
        "num__is_auth_email_session","num__is_auth_phone_session","num__total_accounts","num__user_age",
        "num__is_amount_greater_than_cu_p95_amount_ach_txn_in_last_6_months",
        "num__txn_amount_vs_cu_avg_amount_ach_txn_in_last_6_months","num__is_batch",
        "num__amt_vs_user_ach_avg_day","num__ach_count_share_6m",
        # CAT
        "cat__TransactionProcessingType_Intime","cat__TransactionProcessingType_Intime_From_Recurrent",
        "cat__TransactionProcessingType_Recurrent","cat__TransactionProcessingType_Schedule",
        "cat__TransactionOrigin_External Internal","cat__TransactionOrigin_Internal External",
        "cat__TransactionOrigin_M2m External","cat__TransactionCategory_SEND_MONEY_ACH",
        "cat__TransactionCategory_SEND_MONEY_BATCH_PAYMENT_ACH","cat__TransactionCategory_SEND_MONEY_PAYROLL_ACH",
        "cat__TransactionCategory_SINGLE_COLLECTION_ACH","cat__TransactionCategory_TRANSFER_EXTERNAL_TO_LOAN_ACH",
        "cat__TransactionCategory_TRANSFER_INTERNAL_EXTERNAL_ACH","cat__user_type_mixed","cat__user_type_personal",
        "cat__access_DESKTOP","cat__access_MOBILE","cat__access_missing",
        # Post
        "Cluster","Distance_to_Centroid","risk_score","risk_decision","is_outlier",
        "top_contributors","audit_category","audit_explanation","ux_copy"
    ]

    # Garantizar existencia de todas las num__/cat__ (si falta, 0.0)
    for c in requested_cols:
        if c.startswith("num__") or c.startswith("cat__"):
            if c not in df_transformed.columns:
                df_transformed[c] = 0.0

    final_df = pd.DataFrame(index=out_df.index)
    for c in requested_cols:
        if c.startswith("num__") or c.startswith("cat__"):
            final_df[c] = df_transformed[c]

    final_df["Cluster"] = out_df["Cluster"].astype(int)
    final_df["Distance_to_Centroid"] = out_df["Distance_to_Centroid"].astype(float)
    final_df["risk_score"] = out_df["risk_score"].astype(int)
    final_df["risk_decision"] = out_df["risk_decision"].astype(str)
    final_df["is_outlier"] = out_df["is_outlier"].astype(int)
    final_df["top_contributors"] = out_df["top_contributors"]
    final_df["audit_category"] = out_df["audit_category"]
    final_df["audit_explanation"] = out_df["audit_explanation"]
    final_df["ux_copy"] = out_df["ux_copy"]
    
    # Add similarity results to output (only 3 fields)
    if similarity_results:
        final_df["similarity_TransactionID"] = [sr.get("TransactionID", None) for sr in similarity_results]
        final_df["similarity_matched_transaction_id"] = [sr.get("matched_transaction_id", None) for sr in similarity_results]
        final_df["similarity_score"] = [sr.get("similarity_score", 0.0) for sr in similarity_results]

    # Reorden final exacto
    output_cols = requested_cols.copy()
    if similarity_results:
        output_cols.extend(["similarity_TransactionID", "similarity_matched_transaction_id", "similarity_score"])
    
    final_df = final_df[output_cols]

    print("[PRED] done, rows:", len(final_df))
    return final_df.to_dict(orient="records")

def output_fn(prediction, accept='application/json'):
    import json
    return json.dumps(prediction), accept
