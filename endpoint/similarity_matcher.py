"""
Similarity Matcher for Safe Transactions
=========================================
Finds the most similar historical transaction for each incoming transaction
by querying Athena (dlh_silver_safe_alpha.safetransactionresults) with a
6-month sliding window per transaction date, then scoring 49 fields using
exact-match comparison with float tolerance (1e-9).

Output fields: sim_match_txn_id, sim_score, sim_status, sim_decision.
sim_decision = 'Accept'/'Reject' only when sim_score >= threshold (default 0.90).

Graceful degradation: if Athena is unavailable, all sim_* fields return None.
The endpoint continues with K-Means + statistical rules.
"""

import os
import json
import hashlib
import concurrent.futures
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timezone
from sklearn.metrics.pairwise import cosine_similarity
import boto3

import logging

# Configure logging (must be before any use of logger)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Athena connect (imported at module level so tests can patch endpoint.similarity_matcher.connect)
try:
    from pyathena import connect
    HAS_PYATHENA = True
except ImportError:
    HAS_PYATHENA = False
    logger.warning("[SIMILARITY] pyathena not available. Athena support disabled.")
    connect = None  # type: ignore[assignment]

try:
    from dateutil.relativedelta import relativedelta
    HAS_DATEUTIL = True
except ImportError:
    HAS_DATEUTIL = False
    logger.warning("[SIMILARITY] python-dateutil not available.")

# Try to import schema validator
try:
    from schema_validator import (
        EXPECTED_NUM_FEATURES,
        EXPECTED_CAT_FEATURES,
        validate_decision_result_schema,
        validate_features_only,
        validate_s3_reference_data,
        get_schema_info
    )
    HAS_SCHEMA_VALIDATOR = True
    logger.info("[SIMILARITY] Schema validator loaded successfully")
except ImportError as e:
    logger.warning(f"[SIMILARITY] schema_validator not found: {e}")
    HAS_SCHEMA_VALIDATOR = False
    EXPECTED_NUM_FEATURES = []
    EXPECTED_CAT_FEATURES = []
    validate_features_only = None

# =========================
# Configuration
# =========================

DEFAULT_THRESHOLD = 0.90

# Single source of truth: field list lives in schema_validator.py
# EXACT_MATCH_FIELDS is derived at import time — no duplication
EXACT_MATCH_FIELDS = EXPECTED_NUM_FEATURES + EXPECTED_CAT_FEATURES

# Athena cache: keyed by "athena:{idolbuser_int}:{end_minute_str}"
_ATHENA_CACHE: Dict[str, Any] = {}


# =========================
# F5+ Logging helpers
# =========================

def classify_exception(exc: BaseException) -> str:
    """Map an exception to an observable category for structured logging.

    Categories:
      - "permission":  IAM denied (cross-account broken)
      - "throttling":  Athena/AWS throttled the request
      - "timeout":     query exceeded ATHENA_TIMEOUT_SECONDS
      - "query_error": SQL syntax or schema drift
      - "unknown":     anything else
    """
    msg = str(exc).lower()
    if isinstance(exc, PermissionError) or "accessdenied" in msg or "access denied" in msg:
        return "permission"
    if "throttl" in msg or "ratelimit" in msg or "rate exceeded" in msg:
        return "throttling"
    if isinstance(exc, TimeoutError) or "timeout" in msg or "timed out" in msg:
        return "timeout"
    if "syntaxerror" in msg or "table not found" in msg or "column" in msg:
        return "query_error"
    return "unknown"


def _hash_idolbuser(idolbuser) -> str:
    """sha256-truncated hash for use as observability dimension. NEVER log raw idolbuser."""
    return hashlib.sha256(str(idolbuser).encode()).hexdigest()[:16]


# =========================
# Athena: window + column normalisation
# =========================

def _compute_sliding_window(window_months: int = 6, reference_dt: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    """
    Compute (start, end) for the sliding window relative to a transaction date.

    Args:
        window_months: Look back period in months (typically 6)
        reference_dt: Transaction date to use as the window end. If None, uses now() UTC.

    Returns:
        (start, end) datetime objects in UTC where:
        - end = reference_dt (the transaction being evaluated)
        - start = end - window_months (lookback period)

    For similarity matching, we want historical transactions BEFORE the current one:
    - If evaluating transaction at 2026-04-15, search window is [2025-10-15, 2026-04-15)
    """
    if reference_dt is None:
        end = datetime.now(timezone.utc)
    else:
        # Ensure reference_dt is timezone-aware (UTC)
        if reference_dt.tzinfo is None:
            end = reference_dt.replace(tzinfo=timezone.utc)
        else:
            end = reference_dt.astimezone(timezone.utc)

    start = end - relativedelta(months=window_months)
    return start, end


def _normalize_athena_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize Athena column names (all lowercase from Glue) to the canonical
    camelCase names used by DTYPE_MAP in endpoint/inference_rules.py,
    _load_from_local_csv, and predict_fn.

    Canonical column mapping (self-contained):
      transactionid  -> TransactionID   (uppercase D — matches DTYPE_MAP)
      idolbuser      -> idOLBUser
      createdat      -> createdAt
      statuswarning  -> statusWarning
      metadata       -> metadata (unchanged)
    """
    column_mapping = {
        "transactionid": "TransactionID",
        "idolbuser": "idOLBUser",
        "createdat": "createdAt",
        "statuswarning": "statusWarning",
        "metadata": "metadata",
    }
    df = df.rename(columns={c: column_mapping.get(c.lower(), c) for c in df.columns})
    return df


# =========================
# Athena Data Loading
# =========================

def load_reference_data_from_athena(
    idolbuser: int,
    window_months: int = 6,
    force_reload: bool = False,
    timeout_seconds: int = 10,
    transaction_datetime: Optional[datetime] = None,
) -> Tuple[Optional[pd.DataFrame], Optional[np.ndarray], Optional[np.ndarray], Optional[np.ndarray]]:
    """
    Load reference transaction data from Athena, filtered by idolbuser and
    sliding window [transaction_datetime - window_months, transaction_datetime).

    Window is computed AT CALL TIME relative to the transaction being evaluated.
    This enables historical similarity matching: find transactions BEFORE the
    current transaction within the lookback period.

    Args:
        idolbuser: User ID to filter
        window_months: Lookback period in months (typically 6)
        force_reload: Skip cache
        timeout_seconds: Athena query timeout
        transaction_datetime: Date of transaction being evaluated (window end).
                            If None, uses now() UTC.

    Returns (df, feature_vectors, labels, txn_ids) — same shape as
    load_reference_data_from_s3(). Returns (None, None, None, None) on any
    failure (graceful degradation, follows the L527-528 pattern).
    """
    global _ATHENA_CACHE

    # Defense-in-depth: int cast raises ValueError/TypeError for non-numeric input
    idolbuser_int = int(idolbuser)

    # Compute sliding window relative to transaction date
    start, end = _compute_sliding_window(window_months, reference_dt=transaction_datetime)
    # Key by (user, date) — not minute. All txns for the same user on the same day
    # share a single Athena query (6-month window shifts < 1 day between same-day txns).
    cache_key = f"athena:{idolbuser_int}:{end.strftime('%Y-%m-%d')}"

    if not force_reload and cache_key in _ATHENA_CACHE:
        logger.info(f"[SIMILARITY][ATHENA] Cache hit for {cache_key}")
        return _ATHENA_CACHE[cache_key]

    try:
        s3_staging = os.getenv(
            "SIMILARITY_ATHENA_S3_STAGING",
            "s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/",
        )
        region = os.getenv("SIMILARITY_ATHENA_REGION", "us-east-2")

        # F1 + F11: parameterized query with explicit column list (NO f-string, NO SELECT *)
        # Filter by date only (YYYY-MM-DD), not time, to capture all transactions on matching days
        sql = """
            SELECT idolbuser, createdat, statuswarning, metadata, transactionid
            FROM dlh_silver_safe_alpha.safetransactionresults
            WHERE idolbuser = %(user)s
              AND CAST(createdat AS DATE) >= CAST(%(window_start_date)s AS DATE)
              AND CAST(createdat AS DATE) <= CAST(%(window_end_date)s AS DATE)
              AND statuswarning IN ('SAFE', 'RISKY')
        """
        params = {
            "user": idolbuser_int,
            "window_start_date": start.date().isoformat(),  # YYYY-MM-DD string
            "window_end_date": end.date().isoformat(),      # YYYY-MM-DD string
        }

        def _run_query():
            conn = connect(s3_staging_dir=s3_staging, region_name=region)
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            desc = cursor.description
            conn.close()
            return rows, desc

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_query)
            try:
                rows, desc = future.result(timeout=timeout_seconds)
            except concurrent.futures.TimeoutError:
                raise TimeoutError(f"Athena query exceeded {timeout_seconds}s timeout")

        df = pd.DataFrame(rows, columns=[d[0] for d in desc])
        df = _normalize_athena_columns(df)

        # F5+ zero-rows path (normal Scenario 3 — user has no history)
        if len(df) == 0:
            logger.info(
                "similarity.no_history",
                extra={
                    "idolbuser_hash": _hash_idolbuser(idolbuser_int),
                    "window_months": window_months,
                    "rows": 0,
                },
            )
            return (None, None, None, None)

        # Extract feature vectors (reuse same loop as load_reference_data_from_s3)
        result = _extract_vectors_from_df(df)
        if result[1] is None:
            return (None, None, None, None)

        _ATHENA_CACHE[cache_key] = result
        return result

    except Exception as exc:
        logger.warning(
            "similarity.athena_failure",
            extra={
                "idolbuser_hash": _hash_idolbuser(idolbuser_int) if "idolbuser_int" in dir() else _hash_idolbuser(idolbuser),
                "exception_class": exc.__class__.__name__,
                "exception_message": str(exc)[:200],
                "category": classify_exception(exc),
            },
        )
        return (None, None, None, None)


def _extract_vectors_from_df(
    df: pd.DataFrame,
) -> Tuple[Optional[pd.DataFrame], Optional[np.ndarray], Optional[np.ndarray], Optional[np.ndarray]]:
    """
    Extract feature vectors, labels, and transaction IDs from a normalized DataFrame.

    Used by both load_reference_data_from_athena() and load_reference_data_from_s3()
    to avoid duplicating the metadata/decisionResult parsing loop.

    Returns (df_valid, feature_matrix, labels_array, ids_array), or
    (None, None, None, None) if no valid records are found.
    """
    required_cols = ["metadata", "statusWarning"]
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        logger.warning("[SIMILARITY] _extract_vectors_from_df: missing columns %s", missing_cols)
        return (None, None, None, None)

    vectors: list = []
    labels: list = []
    transaction_ids: list = []
    valid_indices: list = []

    # Logging: track filtering stages
    input_count = len(df)
    metadata_count = 0
    decision_count = 0
    vector_count = 0
    status_count = 0

    for idx, row in df.iterrows():
        try:
            metadata_raw = row.get("metadata")
            if pd.isna(metadata_raw):
                logger.debug(f"[SIMILARITY] Row {idx}: metadata is NaN")
                continue
            metadata_count += 1

            metadata = json.loads(metadata_raw) if isinstance(metadata_raw, str) else metadata_raw
            decision_result = metadata.get("decisionResult")
            if not decision_result:
                logger.debug(f"[SIMILARITY] Row {idx}: no decisionResult in metadata")
                continue
            decision_count += 1

            if HAS_SCHEMA_VALIDATOR and validate_features_only is not None:
                is_valid = validate_features_only(decision_result, require_all=False)
                if not is_valid:
                    logger.debug(f"[SIMILARITY] Row {idx}: schema validation failed")
                    continue

            feature_vector = _extract_feature_vector(decision_result)
            if feature_vector is None or len(feature_vector) == 0:
                logger.debug(f"[SIMILARITY] Row {idx}: failed to extract feature vector")
                continue
            vector_count += 1

            status = str(row.get("statusWarning", "")).strip().upper()
            if status not in ("SAFE", "RISKY"):
                logger.debug(f"[SIMILARITY] Row {idx}: statusWarning={status} not in ('SAFE', 'RISKY')")
                continue
            status_count += 1

            txn_id = (
                row.get("TransactionID")
                or row.get("transactionId")
                or row.get("transaction_id")
                or str(idx)
            )
            vectors.append(feature_vector)
            labels.append(status)
            transaction_ids.append(str(txn_id))
            valid_indices.append(idx)
        except Exception as e:
            logger.warning("[SIMILARITY] _extract_vectors_from_df row %s: %s", idx, e)
            continue

    # Log filtering summary
    logger.info(
        "[SIMILARITY] Vector extraction: input=%d, has_metadata=%d, has_decision=%d, "
        "has_vector=%d, valid_status=%d, final=%d",
        input_count, metadata_count, decision_count, vector_count, status_count, len(vectors)
    )

    if not vectors:
        logger.warning(
            "[SIMILARITY] No valid vectors extracted from %d rows. "
            "Check metadata structure and decisionResult fields.",
            input_count
        )
        return (None, None, None, None)

    df_valid = df.iloc[valid_indices].reset_index(drop=True)
    return (
        df_valid,
        np.array(vectors),
        np.array(labels),
        np.array(transaction_ids),
    )


# =========================
# Data Loading
# =========================



def _extract_feature_vector(decision_result: Dict[str, Any]) -> Optional[np.ndarray]:
    """
    Extract feature vector from decisionResult for similarity comparison.
    
    ONLY extracts num__ and cat__ features (NOT post-processing fields like Cluster, risk_score, etc.)
    
    Args:
        decision_result: Dictionary with num__, cat__ features
    
    Returns:
        Numpy array with feature values in sorted order, or None if extraction fails
    """
    try:
        # Validate schema first (only num__ and cat__ fields required)
        # Use flexible validation for partial schema matches
        if HAS_SCHEMA_VALIDATOR and validate_features_only is not None:
            is_valid = validate_features_only(decision_result, require_all=False)
            if not is_valid:
                logger.warning("[SIMILARITY] Feature validation failed - insufficient feature coverage")
                # Continue anyway - we'll extract whatever features are available
        
        # Get schema info
        schema_info = get_schema_info()
        num_features = schema_info["numerical_features"]
        cat_features = schema_info["categorical_features"]
        
        # Extract values - ONLY num__ and cat__ fields
        feature_values = []
        
        # Add numerical features in sorted order
        for feat in sorted(num_features):
            val = decision_result.get(feat, 0.0)
            feature_values.append(float(val) if val is not None else 0.0)
        
        # Add categorical features in sorted order
        for feat in sorted(cat_features):
            val = decision_result.get(feat, 0.0)
            feature_values.append(float(val) if val is not None else 0.0)
        
        # NOTE: We do NOT include post-processing fields (Cluster, Distance_to_Centroid, 
        # risk_score, risk_decision, is_outlier) in the feature vector for similarity matching
        
        if len(feature_values) == 0:
            logger.error("[SIMILARITY] No features extracted")
            return None
        
        logger.debug(f"[SIMILARITY] Extracted {len(feature_values)} features ({len(num_features)} num + {len(cat_features)} cat)")
        
        return np.array(feature_values, dtype=np.float64)
    
    except Exception as e:
        logger.error(f"[SIMILARITY] Error extracting feature vector: {e}")
        import traceback
        traceback.print_exc()
        return None


# =========================
# Similarity Calculation
# =========================

def calculate_similarity(
    query_vector: np.ndarray,
    reference_vectors: np.ndarray,
    metric: str = "cosine"
) -> np.ndarray:
    """
    Calculate similarity between query vector and all reference vectors.
    
    Args:
        query_vector: 1D array of query features
        reference_vectors: 2D array of reference features (n_samples, n_features)
        metric: Similarity metric ("cosine" or "euclidean")
    
    Returns:
        Array of similarity scores (higher = more similar)
    """
    try:
        # Ensure query is 2D for sklearn
        if query_vector.ndim == 1:
            query_vector = query_vector.reshape(1, -1)
        
        if metric == "cosine":
            # Cosine similarity: range [-1, 1], higher is more similar
            similarities = cosine_similarity(query_vector, reference_vectors)[0]
            return similarities
        
        elif metric == "euclidean":
            # Convert euclidean distance to similarity score
            # similarity = 1 / (1 + distance)
            from sklearn.metrics.pairwise import euclidean_distances
            distances = euclidean_distances(query_vector, reference_vectors)[0]
            similarities = 1.0 / (1.0 + distances)
            return similarities
        
        else:
            raise ValueError(f"Unsupported metric: {metric}")
    
    except Exception as e:
        logger.error(f"[SIMILARITY] Error calculating similarity: {e}")
        return np.array([])


# =========================
# Exact Field Matching (56 fields, no transformation)
# =========================

def _extract_exact_fields(decision_result: Dict[str, Any], field_list: List[str]) -> Dict[str, Any]:
    """
    Extract exact field values from decision_result without any transformation.

    Args:
        decision_result: Dictionary containing field values
        field_list: List of field names to extract

    Returns:
        Dictionary with field names and values, or empty dict if fields missing
    """
    extracted = {}
    for field in field_list:
        if field in decision_result:
            extracted[field] = decision_result[field]
    return extracted


def _calculate_exact_field_match(
    query_fields: Dict[str, Any],
    ref_rows: pd.DataFrame,
    field_list: List[str]
) -> Tuple[np.ndarray, int]:
    """
    Calculate exact field match scores comparing 56 specific fields.

    For each reference row, count how many fields match exactly with the query.
    Score = number_of_exact_matches / total_fields (0.0 to 1.0).

    Args:
        query_fields: Dict of query fields to match
        ref_rows: DataFrame of reference rows (from Athena)
        field_list: List of field names to compare

    Returns:
        Tuple of (scores array, best_match_index)
        - scores: float array, one score per reference row (0.0-1.0)
        - best_match_index: index of highest score
    """
    if len(ref_rows) == 0:
        return np.array([]), -1

    scores = []

    for idx, row in ref_rows.iterrows():
        matches = 0
        total = 0

        # Extract ref fields from metadata.decisionResult (where they actually live in Athena rows)
        ref_fields: Dict[str, Any] = {}
        metadata_raw = row.get("metadata")
        if metadata_raw is not None and not (isinstance(metadata_raw, float) and pd.isna(metadata_raw)):
            try:
                meta = json.loads(metadata_raw) if isinstance(metadata_raw, str) else metadata_raw
                ref_fields = meta.get("decisionResult", {}) or {}
            except Exception:
                ref_fields = {}

        for field in field_list:
            total += 1
            query_val = query_fields.get(field)
            ref_val = ref_fields.get(field)

            # None vs 0/0.0: field absent from query (not in SELECTED) is equivalent to 0
            if query_val is None and ref_val is not None:
                try:
                    if float(ref_val) == 0.0:
                        matches += 1
                        continue
                except (TypeError, ValueError):
                    pass

            # Float near-equality (1e-9 tolerance) handles round-trip precision loss
            if query_val is not None and ref_val is not None:
                try:
                    if abs(float(query_val) - float(ref_val)) <= 1e-9:
                        matches += 1
                        continue
                except (TypeError, ValueError):
                    pass

            if query_val == ref_val:
                matches += 1

        # Score: percentage of fields that match exactly (0.0-1.0)
        score = matches / total if total > 0 else 0.0
        scores.append(score)

    scores_array = np.array(scores, dtype=np.float64)
    best_idx = int(np.argmax(scores_array)) if len(scores_array) > 0 else -1

    if best_idx >= 0:
        logger.info(
            f"[SIMILARITY] Exact field match: checked {len(ref_rows)} reference rows, "
            f"best match score={scores_array[best_idx]:.4f} ({int(scores_array[best_idx]*len(field_list))}/{len(field_list)} fields matched)"
        )

    return scores_array, best_idx


# =========================
# Main Matching Logic
# =========================

def find_similar_transaction(
    query_result: Dict[str, Any],
    threshold: float = DEFAULT_THRESHOLD,
    top_k: int = 1,
    idolbuser: Optional[int] = None,
    window_months: int = 6,
    timeout_seconds: int = 10,
    transaction_datetime: Optional[datetime] = None,
    force_reload: bool = False
) -> Dict[str, Any]:
    """
    Find similar historical transaction and return matching label.

    Args:
        query_result: Dictionary containing transaction decisionResult fields
        threshold: Minimum similarity score to consider a match (0.0-1.0)
        top_k: Number of top matches to consider
        idolbuser: Athena query filter — transaction user ID (required)
        window_months: Sliding window size in months (default 6)
        timeout_seconds: Athena query timeout (default 10)
        transaction_datetime: Reference datetime for sliding window (defaults to now)
        force_reload: Force reload reference data from Athena

    Returns:
        Dictionary with keys:
        - sim_match_txn_id: transaction ID of best match (or None)
        - sim_score: float, similarity score of best match (or None)
        - sim_status: label from matched transaction (or None)
        - sim_decision: "Accept" / "Reject" when above threshold, else None
    """
    try:
        # Load reference data
        if idolbuser is not None:
            # D2 CLOSED: Use Athena as the sole source when idolbuser provided
            logger.info(f"[SIMILARITY] Loading from Athena for idolbuser={idolbuser}")
            print(f"[SIMILARITY] Loading from Athena for idolbuser={idolbuser}")
            try:
                ref_df, ref_vectors, ref_labels, ref_ids = load_reference_data_from_athena(
                    idolbuser=idolbuser,
                    window_months=window_months,
                    timeout_seconds=timeout_seconds,
                    transaction_datetime=transaction_datetime,
                    force_reload=force_reload
                )
                source_uri = f"athena:idolbuser={idolbuser}:window={window_months}m"
            except TimeoutError as e:
                logger.error(f"[SIMILARITY] Athena timeout for idolbuser={idolbuser}: {e}")
                print(f"[SIMILARITY] Athena timeout for idolbuser={idolbuser}: {e}")
                return {
                    "sim_match_txn_id": None,
                    "sim_score": None,
                    "sim_status": None,
                    "sim_decision": None,
                    "error": f"Athena timeout: {str(e)}"
                }

            # Check if data loading failed
            if ref_vectors is None or ref_labels is None:
                logger.warning(f"[SIMILARITY] No Athena data for idolbuser={idolbuser}")
                print(f"[SIMILARITY] No Athena data for idolbuser={idolbuser}")
                return {
                    "sim_match_txn_id": None,
                    "sim_score": None,
                    "sim_status": None,
                    "sim_decision": None
                }
        else:
            logger.warning("[SIMILARITY] idolbuser is required for Athena lookup — no data source available")
            return {
                "sim_match_txn_id": None,
                "sim_score": None,
                "sim_status": None,
                "sim_decision": None,
                "error": "idolbuser required"
            }
        
        # Extract exact 56 fields (no transformation, no normalization)
        query_fields = _extract_exact_fields(query_result, EXACT_MATCH_FIELDS)

        if not query_fields:
            logger.warning("[SIMILARITY] Failed to extract exact fields from query")
            return {
                "matched": False,
                "similarity_score": 0.0,
                "status_warning": "NONE",
                "top_matches": [],
                "error": "Failed to extract exact fields"
            }

        # Calculate exact field match scores
        similarities, best_idx = _calculate_exact_field_match(
            query_fields=query_fields,
            ref_rows=ref_df,
            field_list=EXACT_MATCH_FIELDS
        )

        if len(similarities) == 0 or best_idx < 0:
            logger.warning("[SIMILARITY] No exact field matches calculated")
            return {
                "matched": False,
                "similarity_score": 0.0,
                "status_warning": "NONE",
                "top_matches": [],
                "error": "No matches found"
            }

        # Get top k matches (sorted by similarity score descending)
        top_indices = np.argsort(similarities)[::-1][:top_k]
        top_scores = similarities[top_indices]

        # Build top matches list with transaction_id
        top_matches = []
        for idx, score in zip(top_indices, top_scores):
            top_matches.append({
                "transaction_id": ref_ids[idx],
                "similarity_score": float(score),
                "status_warning": ref_labels[idx]
            })

        # Get best match
        best_idx = int(top_indices[0])
        best_score = float(similarities[best_idx])
        best_label = ref_labels[best_idx]
        best_txn_id = ref_ids[best_idx]

        # Check if above threshold
        matched = best_score >= threshold

        # Athena source: always return best match info; sim_decision only when above threshold
        if matched and best_label in ("SAFE", "RISKY"):
            sim_decision = "Accept" if best_label == "SAFE" else "Reject"
        else:
            sim_decision = None
        result = {
            "sim_match_txn_id": best_txn_id,
            "sim_score": best_score,
            "sim_status": best_label,
            "sim_decision": sim_decision,
        }
        logger.info(
            f"[SIMILARITY] ATHENA: txn={best_txn_id}, score={best_score:.4f}, "
            f"status={best_label}, decision={sim_decision or 'below_threshold'}, "
            f"idolbuser={idolbuser}"
        )

        return result
    
    except Exception as e:
        logger.error(f"[SIMILARITY] Error in find_similar_transaction: {e}")
        return {
            "matched": False,
            "similarity_score": 0.0,
            "status_warning": "NONE",
            "top_matches": [],
            "error": str(e)
        }


# =========================
# Cache Management
# =========================

def clear_cache():
    """Clear the Athena cache."""
    _ATHENA_CACHE.clear()
    logger.info("[SIMILARITY] Athena cache cleared")


def get_cache_info() -> Dict[str, Any]:
    """Get information about the current Athena cache state."""
    return {
        "num_cached_sources": len(_ATHENA_CACHE),
        "cached_sources": list(_ATHENA_CACHE.keys()),
    }


# =========================
# Utility Functions
# =========================

def is_enabled() -> bool:
    """Check if similarity matching is enabled via environment variable."""
    return os.getenv("DISABLE_SIMILARITY", "0") != "1"


def get_threshold_from_env(default: float = DEFAULT_THRESHOLD) -> float:
    """Get similarity threshold from environment variable."""
    try:
        threshold = float(os.getenv("SIMILARITY_THRESHOLD", str(default)))
        # Clamp to valid range
        return max(0.0, min(1.0, threshold))
    except ValueError:
        logger.warning(f"[SIMILARITY] Invalid SIMILARITY_THRESHOLD, using default: {default}")
        return default


# =========================
# Standalone Testing
# =========================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test similarity matching (Athena)")
    parser.add_argument("--threshold", type=float, default=0.90, help="Similarity threshold")
    parser.add_argument("--idolbuser", type=int, required=True, help="OLB user ID to query")
    parser.add_argument("--force-reload", action="store_true", help="Force reload from Athena")
    args = parser.parse_args()

    print(f"\n=== Athena Similarity Test for idolbuser={args.idolbuser} ===")

    try:
        df, vectors, labels, txn_ids = load_reference_data_from_athena(
            idolbuser=args.idolbuser,
            force_reload=args.force_reload
        )
        if vectors is not None:
            print(f"Loaded {len(df)} transactions from Athena")
            print(f"Unique labels: {set(labels)}")
        else:
            print("No data returned from Athena.")

        print("\nCache Info:", get_cache_info())
        print("\nTest completed successfully")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
