"""
Similarity Matcher for Safe Transactions
==========================================

This module provides similarity-based matching against historical transactions
stored in S3. It compares incoming transactions with a reference dataset and
returns matching labels when similarity exceeds a configurable threshold.

Key features:
- Loads reference data from S3 (with caching)
- Parses JSON metadata.decisionResult fields
- Calculates cosine similarity between transaction vectors
- Returns statusWarning label + similarity score when match found
- Configurable similarity threshold (default: 0.90)

Integration:
- Called after preprocessing/validation in inference_rules.py
- Uses transformed feature vectors for comparison
- Can be disabled via environment variable DISABLE_SIMILARITY=1
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
from io import StringIO, BytesIO
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

# Try to import pyarrow for parquet support
try:
    import pyarrow.parquet as pq
    HAS_PARQUET = True
except ImportError:
    HAS_PARQUET = False
    logger.warning("[SIMILARITY] pyarrow not available. Parquet support disabled.")

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
DEFAULT_S3_BUCKET = "blossom-analytics-datalake-alpha"
DEFAULT_S3_KEY = "datalake/silver/SAFE/safetransactionresults/data/"  # Parquet directory

# Global cache for reference data (keyed by s3_uri or local path)
# Cache structure: {cache_key: {'data': (df, vectors, labels, ids), 'file_count': int}}
_REFERENCE_CACHE = {}

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

def _compute_sliding_window(window_months: int = 6) -> Tuple[datetime, datetime]:
    """
    Compute (start, end) for the sliding window. End = now() UTC,
    start = end - relativedelta(months=window_months).

    Returns datetime objects in UTC. Formatting to Athena TIMESTAMP literal
    happens in load_reference_data_from_athena().
    """
    end = datetime.now(timezone.utc)
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
) -> Tuple[Optional[pd.DataFrame], Optional[np.ndarray], Optional[np.ndarray], Optional[np.ndarray]]:
    """
    Load reference transaction data from Athena, filtered by idolbuser and
    sliding window [now() - window_months, now()].

    Window is computed AT CALL TIME, not at module load. Critical because the
    SageMaker container stays warm for days; computing at load would freeze
    the window.

    Returns (df, feature_vectors, labels, txn_ids) — same shape as
    load_reference_data_from_s3(). Returns (None, None, None, None) on any
    failure (graceful degradation, follows the L527-528 pattern).
    """
    global _ATHENA_CACHE

    # Defense-in-depth: int cast raises ValueError/TypeError for non-numeric input
    idolbuser_int = int(idolbuser)

    # Compute sliding window at call time (never at module load)
    start, end = _compute_sliding_window(window_months)
    cache_key = f"athena:{idolbuser_int}:{end.strftime('%Y-%m-%d-%H-%M')}"

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
        sql = """
            SELECT idolbuser, createdat, statuswarning, metadata, transactionid
            FROM dlh_silver_safe_alpha.safetransactionresults
            WHERE idolbuser = %(user)s
              AND createdat >= %(window_start)s
              AND createdat <= %(window_end)s
              AND statuswarning IN ('SAFE', 'RISKY')
        """
        params = {
            "user": idolbuser_int,          # int cast as defense-in-depth
            "window_start": start,           # datetime object
            "window_end": end,               # datetime object
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


def _count_parquet_files_in_s3(s3_client, bucket: str, prefix: str) -> int:
    """Count number of parquet files in S3 directory"""
    if not prefix.endswith('/'):
        prefix = prefix + '/'
    
    try:
        response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        if 'Contents' not in response:
            return 0
        
        count = sum(1 for obj in response['Contents'] if obj['Key'].endswith('.parquet'))
        return count
    except Exception as e:
        logger.warning(f"[SIMILARITY] Failed to count S3 files: {e}")
        return 0


# =========================
# Helper Functions
# =========================

def _load_csv_from_s3(s3_client, bucket: str, key: str) -> pd.DataFrame:
    """Load CSV file from S3"""
    response = s3_client.get_object(Bucket=bucket, Key=key)
    csv_content = response["Body"].read().decode("utf-8")
    return pd.read_csv(StringIO(csv_content))


def _load_parquet_from_s3(s3_client, bucket: str, key: str) -> pd.DataFrame:
    """Load single parquet file from S3"""
    if not HAS_PARQUET:
        raise ImportError("pyarrow is required for parquet support. Install with: pip install pyarrow")
    
    response = s3_client.get_object(Bucket=bucket, Key=key)
    parquet_data = response["Body"].read()
    table = pq.read_table(BytesIO(parquet_data))
    return table.to_pandas()


def _load_parquet_directory_from_s3(s3_client, bucket: str, prefix: str) -> pd.DataFrame:
    """Load all parquet files from an S3 directory/prefix"""
    if not HAS_PARQUET:
        raise ImportError("pyarrow is required for parquet support. Install with: pip install pyarrow")
    
    # Ensure prefix ends with /
    if not prefix.endswith('/'):
        prefix = prefix + '/'
    
    # List all parquet files in the directory
    logger.info(f"[SIMILARITY] Listing parquet files in s3://{bucket}/{prefix}")
    response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    
    if 'Contents' not in response:
        raise FileNotFoundError(f"No files found in s3://{bucket}/{prefix}")
    
    parquet_files = [
        obj['Key'] for obj in response['Contents'] 
        if obj['Key'].endswith('.parquet')
    ]
    
    if not parquet_files:
        raise FileNotFoundError(f"No .parquet files found in s3://{bucket}/{prefix}")
    
    logger.info(f"[SIMILARITY] Found {len(parquet_files)} parquet files")
    
    # Read all parquet files and concatenate
    dfs = []
    for i, key in enumerate(parquet_files):
        try:
            logger.debug(f"[SIMILARITY] Reading file {i+1}/{len(parquet_files)}: {key}")
            response = s3_client.get_object(Bucket=bucket, Key=key)
            parquet_data = response["Body"].read()
            table = pq.read_table(BytesIO(parquet_data))
            df_temp = table.to_pandas()
            dfs.append(df_temp)
        except Exception as e:
            logger.warning(f"[SIMILARITY] Failed to read {key}: {e}")
            continue
    
    if not dfs:
        raise ValueError(f"Failed to read any parquet files from s3://{bucket}/{prefix}")  # noqa: F1-no-fstring-sql
    
    # Concatenate all dataframes
    df_combined = pd.concat(dfs, ignore_index=True)
    logger.info(f"[SIMILARITY] Combined {len(dfs)} files into {len(df_combined)} records")
    
    # Normalize column names (parquet files use lowercase, we need camelCase)
    column_mapping = {
        'uuid': 'uuid',
        'transactionid': 'transactionId',
        'idfi': 'idFi',
        'statuswarning': 'statusWarning',
        'metadata': 'metadata',
        'createdat': 'createdAt',
        'updatedat': 'updatedAt'
    }
    df_combined.columns = [column_mapping.get(col.lower(), col) for col in df_combined.columns]
    
    # Remove CDC metadata columns
    cdc_columns = ['_last_cdc_timestamp']
    for col in cdc_columns:
        if col in df_combined.columns:
            df_combined = df_combined.drop(columns=[col])
            logger.debug(f"[SIMILARITY] Removed CDC column: {col}")
    
    logger.info(f"[SIMILARITY] Normalized column names: {list(df_combined.columns)}")
    
    return df_combined


# =========================
# Data Loading
# =========================

def _load_from_local_csv(csv_path: str) -> Tuple[pd.DataFrame, np.ndarray, np.ndarray, np.ndarray]:
    """
    Load reference data from local CSV file (for testing).
    
    Args:
        csv_path: Path to local CSV file
    
    Returns:
        Tuple of (DataFrame, feature_vectors, labels, transaction_ids)
    """
    global _REFERENCE_CACHE
    
    # Check cache
    if csv_path in _REFERENCE_CACHE:
        logger.info(f"[SIMILARITY] Using cached data from {csv_path}")  # noqa: F1-no-fstring-sql
        return _REFERENCE_CACHE[csv_path]['data']
    
    logger.info(f"[SIMILARITY] Loading reference data from local file: {csv_path}")  # noqa: F1-no-fstring-sql
    
    # Load CSV
    df = pd.read_csv(csv_path)
    logger.info(f"[SIMILARITY] Loaded {len(df)} records from local file")  # noqa: F1-no-fstring-sql
    
    # Process same as S3 version
    feature_vectors = []
    labels = []
    transaction_ids = []
    
    skip_reasons = {
        "parse_error": 0,
        "missing_metadata": 0,
        "missing_decisionResult": 0,
        "schema_invalid": 0,
        "feature_extraction_failed": 0
    }
    
    for idx, row in df.iterrows():
        # Extract metadata
        metadata_str = row.get("metadata", "{}")
        if pd.isna(metadata_str):
            skip_reasons["missing_metadata"] += 1
            continue
        
        try:
            metadata = json.loads(metadata_str) if isinstance(metadata_str, str) else metadata_str
        except (json.JSONDecodeError, TypeError) as e:
            skip_reasons["parse_error"] += 1
            continue
        
        # Extract decisionResult
        decision_result = metadata.get("decisionResult")
        if not decision_result:
            skip_reasons["missing_decisionResult"] += 1
            continue
        
        # Validate schema - ONLY check num__ and cat__ features
        # Use flexible validation to allow partial schema matches
        if HAS_SCHEMA_VALIDATOR:
            is_valid = validate_features_only(decision_result, require_all=False)
            if not is_valid:
                skip_reasons["schema_invalid"] += 1
                continue
        
        # Extract feature vector
        feature_vector = _extract_feature_vector(decision_result)
        if feature_vector is None:
            skip_reasons["feature_extraction_failed"] += 1
            continue
        
        # Extract label and transaction ID
        label = row.get("statusWarning", "NONE")
        txn_id = row.get("TransactionID") or row.get("transactionId") or row.get("transaction_id") or row.get("id") or f"txn_{idx}"
        
        feature_vectors.append(feature_vector)
        labels.append(label)
        transaction_ids.append(txn_id)
    
    # Log skip statistics
    total_skipped = sum(skip_reasons.values())
    if total_skipped > 0:
        logger.warning(f"[SIMILARITY] Skipped {total_skipped}/{len(df)} records:")
        for reason, count in skip_reasons.items():
            if count > 0:
                logger.warning(f"[SIMILARITY]   - {reason}: {count}")
    
    if len(feature_vectors) == 0:
        raise ValueError("No valid reference data found in local CSV")
    
    # Convert to numpy arrays
    feature_matrix = np.array(feature_vectors)
    label_array = np.array(labels)
    id_array = np.array(transaction_ids)
    
    logger.info(f"[SIMILARITY] Successfully loaded {len(feature_vectors)} valid records")
    logger.info(f"[SIMILARITY] Feature vector shape: {feature_matrix.shape}")
    
    # Cache the result (CSV files don't track file count)
    _REFERENCE_CACHE[csv_path] = {
        'data': (df, feature_matrix, label_array, id_array),
        'file_count': 0
    }
    
    return df, feature_matrix, label_array, id_array


def load_reference_data_from_s3(
    bucket: Optional[str] = None,
    key: Optional[str] = None,
    s3_uri: Optional[str] = None,
    force_reload: bool = False
) -> Tuple[pd.DataFrame, np.ndarray, List[str], List[str]]:
    """
    Load reference transaction data from S3 and extract feature vectors.
    
    Supports both CSV files and Parquet directories:
    - If key ends with .csv: reads single CSV file
    - If key is a directory (ends with /): reads all .parquet files in directory
    - If key ends with .parquet: reads single parquet file
    
    Args:
        bucket: S3 bucket name (overrides default)
        key: S3 object key or prefix (overrides default)
        s3_uri: Full S3 URI like 's3://bucket/path/' (takes precedence)
        force_reload: If True, bypass cache and reload from S3
    
    Returns:
        Tuple of (dataframe, feature_vectors, status_labels, transaction_ids)
    
    Examples:
        # Use defaults (parquet directory)
        load_reference_data_from_s3()
        
        # Specify bucket and key
        load_reference_data_from_s3(bucket="my-bucket", key="data/parquet/")
        
        # Use S3 URI
        load_reference_data_from_s3(s3_uri="s3://my-bucket/data/parquet/")
    """
    global _REFERENCE_CACHE
    
    # Parse S3 URI if provided
    if s3_uri:
        if not s3_uri.startswith("s3://"):
            raise ValueError(f"Invalid S3 URI: {s3_uri}. Must start with 's3://'")
        parts = s3_uri[5:].split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid S3 URI format: {s3_uri}")
        bucket, key = parts
    else:
        # Use provided bucket/key or environment variables or defaults
        bucket = bucket or os.getenv("SIMILARITY_S3_BUCKET", DEFAULT_S3_BUCKET)
        key = key or os.getenv("SIMILARITY_S3_KEY", DEFAULT_S3_KEY)
    
    # Create cache key
    cache_key = f"s3://{bucket}/{key}"
    
    # Return cached data if available
    if not force_reload and cache_key in _REFERENCE_CACHE:
        logger.info(f"[SIMILARITY] Using cached reference data for {cache_key}")
        return _REFERENCE_CACHE[cache_key]['data']  # Return the tuple, not the dict
    
    try:
        s3_client = boto3.client("s3")
        
        # Create cache key
        cache_key = f"s3://{bucket}/{key}"
        
        # Check if we need to reload:
        # 1. If force_reload is True
        # 2. If cache doesn't exist
        # 3. If it's a parquet directory and file count has changed
        need_reload = force_reload or cache_key not in _REFERENCE_CACHE
        
        if not need_reload and key.endswith('/'):
            # It's a parquet directory - check if file count changed
            current_count = _count_parquet_files_in_s3(s3_client, bucket, key)
            cached_count = _REFERENCE_CACHE[cache_key].get('file_count', 0)
            
            if current_count != cached_count:
                logger.info(
                    f"[SIMILARITY] S3 data changed: {cached_count} -> {current_count} files. "
                    f"Reloading..."
                )
                need_reload = True
            else:
                logger.debug(
                    f"[SIMILARITY] S3 file count unchanged ({current_count} files). Using cache."
                )
        
        # Return cached data if no reload needed
        if not need_reload:
            logger.info(f"[SIMILARITY] Using cached reference data for {cache_key}")
            cached_data = _REFERENCE_CACHE[cache_key]['data']
            return cached_data  # Returns tuple of (df, vectors, labels, ids)
        
        # Reload data from S3
        logger.info(f"[SIMILARITY] Loading reference data from s3://{bucket}/{key}")  # noqa: F1-no-fstring-sql
        if key.endswith('.csv'):
            # CSV file
            logger.info(f"[SIMILARITY] Loading CSV from s3://{bucket}/{key}")  # noqa: F1-no-fstring-sql
            df = _load_csv_from_s3(s3_client, bucket, key)
            
        elif key.endswith('.parquet'):
            # Single parquet file
            logger.info(f"[SIMILARITY] Loading single parquet from s3://{bucket}/{key}")  # noqa: F1-no-fstring-sql
            df = _load_parquet_from_s3(s3_client, bucket, key)
            
        elif key.endswith('/'):
            # Parquet directory - read all parquet files
            logger.info(f"[SIMILARITY] Loading parquet directory from s3://{bucket}/{key}")  # noqa: F1-no-fstring-sql
            df = _load_parquet_directory_from_s3(s3_client, bucket, key)
            
        else:
            # Try to detect format
            logger.warning(f"[SIMILARITY] Ambiguous key format: {key}. Trying parquet directory...")
            df = _load_parquet_directory_from_s3(s3_client, bucket, key)
        
        logger.info(f"[SIMILARITY] Loaded {len(df)} reference transactions")
        
        # Validate required columns
        required_cols = ["metadata", "statusWarning"]
        missing_cols = [c for c in required_cols if c not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")
        
        # Parse metadata.decisionResult (JSON) and filter invalid records
        vectors = []
        labels = []
        transaction_ids = []
        valid_indices = []
        skipped_count = 0
        skip_reasons = {
            "parse_error": 0,
            "missing_metadata": 0,
            "missing_decisionResult": 0,
            "schema_invalid": 0,
            "feature_extraction_failed": 0
        }
        
        for idx, row in df.iterrows():
            try:
                # Check for metadata field
                if "metadata" not in row or pd.isna(row.get("metadata")):
                    skip_reasons["missing_metadata"] += 1
                    skipped_count += 1
                    logger.debug(f"[SIMILARITY] Skipping row {idx}: missing metadata")
                    continue
                
                # Parse metadata JSON
                metadata = row.get("metadata", "{}")
                if isinstance(metadata, str):
                    try:
                        metadata_dict = json.loads(metadata)
                    except json.JSONDecodeError as e:
                        skip_reasons["parse_error"] += 1
                        skipped_count += 1
                        logger.debug(f"[SIMILARITY] Skipping row {idx}: JSON parse error - {e}")
                        continue
                else:
                    metadata_dict = metadata
                
                # Extract decisionResult
                if "decisionResult" not in metadata_dict:
                    skip_reasons["missing_decisionResult"] += 1
                    skipped_count += 1
                    logger.debug(f"[SIMILARITY] Skipping row {idx}: missing decisionResult")
                    continue
                
                decision_result = metadata_dict.get("decisionResult", {})
                
                # Validate schema - ONLY check num__ and cat__ features
                # Use flexible validation to allow partial schema matches
                if HAS_SCHEMA_VALIDATOR:
                    is_valid = validate_features_only(decision_result, require_all=False)
                    
                    if not is_valid:
                        skip_reasons["schema_invalid"] += 1
                        skipped_count += 1
                        logger.debug(
                            f"[SIMILARITY] Skipping row {idx}: invalid schema - "
                            f"insufficient num__ or cat__ features coverage"
                        )
                        continue
                
                # Convert to feature vector
                feature_vector = _extract_feature_vector(decision_result)
                
                if feature_vector is None or len(feature_vector) == 0:
                    skip_reasons["feature_extraction_failed"] += 1
                    skipped_count += 1
                    logger.debug(f"[SIMILARITY] Skipping row {idx}: feature extraction failed")
                    continue
                
                # Filter by statusWarning - ONLY accept SAFE or RISKY
                status_warning = str(row.get("statusWarning", "")).strip().upper()
                if status_warning not in ["SAFE", "RISKY"]:
                    skip_reasons["schema_invalid"] += 1
                    skipped_count += 1
                    logger.debug(
                        f"[SIMILARITY] Skipping row {idx}: invalid statusWarning '{status_warning}' "
                        f"(must be SAFE or RISKY)"
                    )
                    continue
                
                # Record is valid - add to reference dataset
                vectors.append(feature_vector)
                labels.append(status_warning)
                # Extract TransactionID (try multiple possible column names)
                txn_id = row.get("TransactionID") or row.get("transactionId") or row.get("transaction_id") or str(idx)
                transaction_ids.append(str(txn_id))
                valid_indices.append(idx)
            
            except Exception as e:
                skip_reasons["parse_error"] += 1
                skipped_count += 1
                logger.warning(f"[SIMILARITY] Skipping row {idx}: unexpected error - {type(e).__name__}: {e}")
                continue
        
        # Log filtering summary
        total_rows = len(df)
        valid_rows = len(vectors)
        logger.info(
            f"[SIMILARITY] Filtered reference data: {valid_rows}/{total_rows} records valid "
            f"({valid_rows/total_rows*100:.1f}%), {skipped_count} skipped"
        )
        
        if skipped_count > 0:
            logger.info(f"[SIMILARITY] Skip reasons: {skip_reasons}")
        
        if len(vectors) == 0:
            logger.warning(
                f"[SIMILARITY] No valid feature vectors extracted from reference data. "  # noqa: F1-no-fstring-sql
                f"Total rows: {total_rows}, all records were skipped. "  # noqa: F1-no-fstring-sql
                f"Reasons: {skip_reasons}. "
                f"Similarity matching will be DISABLED."
            )
            # Return empty data to signal no similarity matching available
            return None, None, None, None
        
        # Convert to numpy arrays
        reference_vectors = np.array(vectors)
        labels_array = np.array(labels)
        ids_array = np.array(transaction_ids)
        
        logger.info(
            f"[SIMILARITY] Successfully loaded {len(reference_vectors)} valid reference vectors, "
            f"shape: {reference_vectors.shape}"
        )
        
        # Store in cache (only valid records)
        ref_df = df.iloc[valid_indices].reset_index(drop=True)
        
        # Cache the result with file count for parquet directories
        cache_data = {
            'data': (ref_df, reference_vectors, labels_array, ids_array),
            'file_count': 0  # Default for CSV or single parquet
        }
        
        # If it's a parquet directory, store the file count
        if key.endswith('/'):
            cache_data['file_count'] = _count_parquet_files_in_s3(s3_client, bucket, key)
            logger.info(f"[SIMILARITY] Cached {cache_data['file_count']} parquet files")
        
        _REFERENCE_CACHE[cache_key] = cache_data
        
        # Log cache summary with filtering stats
        logger.info(
            f"[SIMILARITY] Cached {len(reference_vectors)} valid records for {cache_key} "
            f"(filtered out {skipped_count} invalid records)"
        )
        
        return ref_df, reference_vectors, labels_array, ids_array
    
    except Exception as e:
        logger.error(
            f"[SIMILARITY] Error loading reference data from {bucket}/{key}: {e}. "  # noqa: F1-no-fstring-sql
            f"Similarity matching will be DISABLED. Endpoint will continue processing with K-means only."
        )
        # Return None to signal graceful degradation
        return None, None, None, None


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
# Main Matching Logic
# =========================

def find_similar_transaction(
    query_result: Dict[str, Any],
    threshold: float = DEFAULT_THRESHOLD,
    metric: str = "cosine",
    top_k: int = 1,
    s3_bucket: Optional[str] = None,
    s3_key: Optional[str] = None,
    s3_uri: Optional[str] = None,
    local_csv_path: Optional[str] = None,
    force_reload: bool = False
) -> Dict[str, Any]:
    """
    Find similar historical transaction and return matching label.
    
    Args:
        query_result: Dictionary containing transaction decisionResult fields
        threshold: Minimum similarity score to consider a match (0.0-1.0)
        metric: Similarity metric to use ("cosine" or "euclidean")
        top_k: Number of top matches to consider
        s3_bucket: S3 bucket name (optional, overrides default)
        s3_key: S3 key path (optional, overrides default)
        s3_uri: Full S3 URI (optional, takes precedence over bucket/key)
        local_csv_path: Path to local CSV file for testing (bypasses S3)
        force_reload: Force reload reference data from S3
    
    Returns:
        Dictionary with keys:
        - matched: bool, whether a match was found above threshold
        - similarity_score: float, similarity score of best match
        - status_warning: str, label from matched transaction or "NONE"
        - top_matches: list of top k matches with scores and labels
        - s3_source: str, S3 URI used for reference data
    """
    try:
        # Load reference data
        if local_csv_path:
            # Load from local file for testing
            logger.info(f"[SIMILARITY] Loading reference data from local file: {local_csv_path}")  # noqa: F1-no-fstring-sql
            ref_df, ref_vectors, ref_labels, ref_ids = _load_from_local_csv(local_csv_path)
            source_uri = f"file://{local_csv_path}"
        else:
            # Load from S3
            ref_df, ref_vectors, ref_labels, ref_ids = load_reference_data_from_s3(
                bucket=s3_bucket,
                key=s3_key,
                s3_uri=s3_uri,
                force_reload=force_reload
            )
            
            # Check if data loading failed (returns None values)
            if ref_vectors is None or ref_labels is None:
                logger.warning("[SIMILARITY] No reference data available - similarity matching disabled")
                return {
                    "matched": False,
                    "similarity_score": 0.0,
                    "status_warning": "NONE",
                    "top_matches": [],
                    "error": "No reference data available"
                }
            
            # Determine source URI for logging
            if s3_uri:
                source_uri = s3_uri
            else:
                bucket_name = s3_bucket or os.getenv("SIMILARITY_S3_BUCKET", DEFAULT_S3_BUCKET)
                key_name = s3_key or os.getenv("SIMILARITY_S3_KEY", DEFAULT_S3_KEY)
                source_uri = f"s3://{bucket_name}/{key_name}"
        
        # Extract query feature vector
        query_vector = _extract_feature_vector(query_result)
        
        if query_vector is None:
            logger.warning("[SIMILARITY] Failed to extract query feature vector")
            return {
                "matched": False,
                "similarity_score": 0.0,
                "status_warning": "NONE",
                "top_matches": [],
                "error": "Failed to extract query features"
            }
        
        # Handle dimension mismatch
        if query_vector.shape[0] != ref_vectors.shape[1]:
            logger.warning(
                f"[SIMILARITY] Dimension mismatch: query={query_vector.shape[0]}, "
                f"reference={ref_vectors.shape[1]}"
            )
            
            # Pad or truncate to match
            target_dim = ref_vectors.shape[1]
            if query_vector.shape[0] < target_dim:
                # Pad with zeros
                query_vector = np.pad(query_vector, (0, target_dim - query_vector.shape[0]))
            else:
                # Truncate
                query_vector = query_vector[:target_dim]
        
        # Calculate similarities
        similarities = calculate_similarity(query_vector, ref_vectors, metric=metric)
        
        if len(similarities) == 0:
            return {
                "matched": False,
                "similarity_score": 0.0,
                "status_warning": "NONE",
                "top_matches": [],
                "error": "No similarities calculated"
            }
        
        # Get top k matches
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
        best_idx = top_indices[0]
        best_score = float(similarities[best_idx])
        best_label = ref_labels[best_idx]
        best_txn_id = ref_ids[best_idx]
        
        # Check if above threshold
        matched = best_score >= threshold
        
        result = {
            "matched": matched,
            "matched_transaction_id": best_txn_id if matched else None,
            "similarity_score": best_score,
            "status_warning": best_label if matched else "NONE",
            "top_matches": top_matches,
            "threshold_used": threshold,
            "metric_used": metric,
            "reference_count": len(ref_vectors),
            "s3_source": source_uri
        }
        
        if matched:
            logger.info(
                f"[SIMILARITY] MATCH FOUND: score={best_score:.4f}, "
                f"label={best_label}, threshold={threshold}"
            )
        else:
            logger.info(
                f"[SIMILARITY] No match: best_score={best_score:.4f} < threshold={threshold}"
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
# Batch Processing
# =========================

def find_similar_transactions_batch(
    query_results: List[Dict[str, Any]],
    threshold: float = DEFAULT_THRESHOLD,
    metric: str = "cosine",
    s3_bucket: Optional[str] = None,
    s3_key: Optional[str] = None,
    s3_uri: Optional[str] = None,
    force_reload: bool = False
) -> List[Dict[str, Any]]:
    """
    Process multiple transactions in batch.
    
    Args:
        query_results: List of transaction decisionResult dictionaries
        threshold: Minimum similarity score to consider a match
        metric: Similarity metric to use
        s3_bucket: S3 bucket name (optional, overrides default)
        s3_key: S3 key path (optional, overrides default)
        s3_uri: Full S3 URI (optional, takes precedence over bucket/key)
        force_reload: Force reload reference data from S3
    
    Returns:
        List of match results, one per input transaction
    """
    try:
        # Load reference data once
        ref_df, ref_vectors, ref_labels, ref_ids = load_reference_data_from_s3(
            bucket=s3_bucket,
            key=s3_key,
            s3_uri=s3_uri,
            force_reload=force_reload
        )
        
        results = []
        for i, query_result in enumerate(query_results):
            try:
                result = find_similar_transaction(
                    query_result,
                    threshold=threshold,
                    metric=metric,
                    s3_bucket=s3_bucket,
                    s3_key=s3_key,
                    s3_uri=s3_uri,
                    force_reload=False  # Already loaded
                )
                results.append(result)
            except Exception as e:
                logger.error(f"[SIMILARITY] Error processing transaction {i}: {e}")
                results.append({
                    "matched": False,
                    "similarity_score": 0.0,
                    "status_warning": "NONE",
                    "error": str(e)
                })
        
        logger.info(f"[SIMILARITY] Processed {len(results)} transactions in batch")
        return results
    
    except Exception as e:
        logger.error(f"[SIMILARITY] Batch processing failed: {e}")
        # Return error result for all
        return [{
            "matched": False,
            "similarity_score": 0.0,
            "status_warning": "NONE",
            "error": str(e)
        }] * len(query_results)


# =========================
# Cache Management
# =========================

def clear_cache(s3_uri: Optional[str] = None):
    """
    Clear the cached reference data.
    
    Args:
        s3_uri: Specific S3 URI to clear from cache. If None, clears all cache.
    """
    global _REFERENCE_CACHE
    
    if s3_uri:
        if s3_uri in _REFERENCE_CACHE:
            del _REFERENCE_CACHE[s3_uri]
            logger.info(f"[SIMILARITY] Cache cleared for {s3_uri}")
        else:
            logger.info(f"[SIMILARITY] No cache found for {s3_uri}")
    else:
        _REFERENCE_CACHE.clear()
        logger.info("[SIMILARITY] All cache cleared")


def get_cache_info() -> Dict[str, Any]:
    """Get information about the current cache state."""
    cache_details = {}
    for uri, (df, vectors, labels, ids) in _REFERENCE_CACHE.items():
        cache_details[uri] = {
            "num_references": len(df),
            "vector_shape": vectors.shape,
            "num_labels": len(set(labels))
        }
    
    return {
        "num_cached_sources": len(_REFERENCE_CACHE),
        "cached_sources": list(_REFERENCE_CACHE.keys()),
        "details": cache_details
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


def get_s3_config_from_env() -> Tuple[str, str]:
    """Get S3 bucket and key from environment variables or defaults."""
    bucket = os.getenv("SIMILARITY_S3_BUCKET", DEFAULT_S3_BUCKET)
    key = os.getenv("SIMILARITY_S3_KEY", DEFAULT_S3_KEY)
    return bucket, key


# =========================
# Standalone Testing
# =========================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test similarity matching")
    parser.add_argument("--threshold", type=float, default=0.90, help="Similarity threshold")
    parser.add_argument("--metric", type=str, default="cosine", choices=["cosine", "euclidean"])
    parser.add_argument("--s3-bucket", type=str, help="S3 bucket name (overrides default)")
    parser.add_argument("--s3-key", type=str, help="S3 key path (overrides default)")
    parser.add_argument("--s3-uri", type=str, help="Full S3 URI like s3://bucket/path/file.csv")
    parser.add_argument("--force-reload", action="store_true", help="Force reload from S3")
    args = parser.parse_args()
    
    # Test loading reference data
    print("\n=== Loading Reference Data ===")
    
    # Determine S3 source
    if args.s3_uri:
        print(f"Using S3 URI: {args.s3_uri}")
    elif args.s3_bucket or args.s3_key:
        bucket = args.s3_bucket or DEFAULT_S3_BUCKET
        key = args.s3_key or DEFAULT_S3_KEY
        print(f"Using S3: s3://{bucket}/{key}")
    else:
        print(f"Using default: s3://{DEFAULT_S3_BUCKET}/{DEFAULT_S3_KEY}")
    
    try:
        df, vectors, labels, txn_ids = load_reference_data_from_s3(
            bucket=args.s3_bucket,
            key=args.s3_key,
            s3_uri=args.s3_uri,
            force_reload=args.force_reload
        )
        print(f"✓ Loaded {len(df)} transactions")
        print(f"✓ Feature vector shape: {vectors.shape}")
        print(f"✓ Unique labels: {set(labels)}")
        
        # Show cache info
        cache_info = get_cache_info()
        print(f"\nCache Info: {cache_info}")
        
        # Test with a sample from the reference data
        if len(df) > 0:
            print("\n=== Testing Similarity Matching ===")
            
            # Get first transaction as test query
            sample_metadata = json.loads(df.iloc[0]["metadata"])
            sample_result = sample_metadata.get("decisionResult", {})
            
            print(f"Query transaction: {df.iloc[0].get('TransactionID', 'N/A')}")
            print(f"True label: {df.iloc[0]['statusWarning']}")
            
            # Find similar
            match_result = find_similar_transaction(
                sample_result,
                threshold=args.threshold,
                metric=args.metric,
                s3_bucket=args.s3_bucket,
                s3_key=args.s3_key,
                s3_uri=args.s3_uri
            )
            
            print(f"\nMatch Result:")
            print(f"  Matched: {match_result['matched']}")
            print(f"  Similarity Score: {match_result['similarity_score']:.4f}")
            print(f"  Status Warning: {match_result['status_warning']}")
            print(f"  Top 3 matches:")
            for i, m in enumerate(match_result.get('top_matches', [])[:3], 1):
                print(f"    {i}. TxnID: {m['TransactionID']}, Score: {m['similarity_score']:.4f}, Label: {m['status_warning']}")
        
        print("\n✓ Test completed successfully")
    
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
