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
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from sklearn.metrics.pairwise import cosine_similarity
import boto3
from io import StringIO
import logging

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# =========================
# Configuration
# =========================

DEFAULT_THRESHOLD = 0.90
DEFAULT_S3_BUCKET = "blossom-analytics-safe-dev-nv"
DEFAULT_S3_KEY = "safe_txns/data/similarity/SafeTransactionResults.csv"

# Global cache for reference data (keyed by s3_uri)
_REFERENCE_CACHE = {}  # {s3_uri: (df, vectors, labels, ids)}


# =========================
# Data Loading
# =========================

def load_reference_data_from_s3(
    bucket: Optional[str] = None,
    key: Optional[str] = None,
    s3_uri: Optional[str] = None,
    force_reload: bool = False
) -> Tuple[pd.DataFrame, np.ndarray, List[str], List[str]]:
    """
    Load reference transaction data from S3 and extract feature vectors.
    
    Args:
        bucket: S3 bucket name (overrides default)
        key: S3 object key (overrides default)
        s3_uri: Full S3 URI like 's3://bucket/path/file.csv' (takes precedence)
        force_reload: If True, bypass cache and reload from S3
    
    Returns:
        Tuple of (dataframe, feature_vectors, status_labels, transaction_ids)
    
    Examples:
        # Use defaults
        load_reference_data_from_s3()
        
        # Specify bucket and key
        load_reference_data_from_s3(bucket="my-bucket", key="data/file.csv")
        
        # Use S3 URI
        load_reference_data_from_s3(s3_uri="s3://my-bucket/data/file.csv")
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
        return _REFERENCE_CACHE[cache_key]
    
    try:
        logger.info(f"[SIMILARITY] Loading reference data from s3://{bucket}/{key}")
        
        s3_client = boto3.client("s3")
        response = s3_client.get_object(Bucket=bucket, Key=key)
        csv_content = response["Body"].read().decode("utf-8")
        
        df = pd.read_csv(StringIO(csv_content))
        logger.info(f"[SIMILARITY] Loaded {len(df)} reference transactions")
        
        # Validate required columns
        required_cols = ["metadata", "statusWarning"]
        missing_cols = [c for c in required_cols if c not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")
        
        # Parse metadata.decisionResult (JSON)
        vectors = []
        labels = []
        transaction_ids = []
        valid_indices = []
        
        for idx, row in df.iterrows():
            try:
                # Parse metadata JSON
                metadata = row.get("metadata", "{}")
                if isinstance(metadata, str):
                    metadata_dict = json.loads(metadata)
                else:
                    metadata_dict = metadata
                
                # Extract decisionResult
                decision_result = metadata_dict.get("decisionResult", {})
                
                # Convert to feature vector
                feature_vector = _extract_feature_vector(decision_result)
                
                if feature_vector is not None and len(feature_vector) > 0:
                    vectors.append(feature_vector)
                    labels.append(str(row.get("statusWarning", "UNKNOWN")))
                    # Extract TransactionID (try multiple possible column names)
                    txn_id = row.get("TransactionID") or row.get("transactionId") or row.get("transaction_id") or str(idx)
                    transaction_ids.append(str(txn_id))
                    valid_indices.append(idx)
            
            except Exception as e:
                logger.warning(f"[SIMILARITY] Failed to parse row {idx}: {e}")
                continue
        
        if len(vectors) == 0:
            raise ValueError("No valid feature vectors extracted from reference data")
        
        # Convert to numpy array
        reference_vectors = np.array(vectors)
        logger.info(f"[SIMILARITY] Extracted {len(reference_vectors)} valid feature vectors, shape: {reference_vectors.shape}")
        
        # Store in cache
        ref_df = df.iloc[valid_indices].reset_index(drop=True)
        cache_data = (ref_df, reference_vectors, labels, transaction_ids)
        _REFERENCE_CACHE[cache_key] = cache_data
        
        logger.info(f"[SIMILARITY] Cached reference data for {cache_key}")
        return cache_data
    
    except Exception as e:
        logger.error(f"[SIMILARITY] Error loading reference data: {e}")
        raise


def _extract_feature_vector(decision_result: Dict[str, Any]) -> Optional[np.ndarray]:
    """
    Extract a numerical feature vector from decisionResult JSON.
    
    The decisionResult typically contains fields like:
    - Cluster, Distance_to_Centroid, risk_score, is_outlier
    - num__* features (numerical features)
    - cat__* features (categorical features)
    
    Args:
        decision_result: Dictionary from metadata.decisionResult
    
    Returns:
        Numpy array of features, or None if extraction fails
    """
    try:
        features = []
        
        # Extract key numerical fields in consistent order
        key_fields = [
            "Cluster",
            "Distance_to_Centroid",
            "risk_score",
            "is_outlier",
        ]
        
        for field in key_fields:
            val = decision_result.get(field, 0)
            try:
                features.append(float(val))
            except (ValueError, TypeError):
                features.append(0.0)
        
        # Extract num__* features (numerical)
        num_features = sorted([k for k in decision_result.keys() if k.startswith("num__")])
        for field in num_features:
            val = decision_result.get(field, 0)
            try:
                features.append(float(val))
            except (ValueError, TypeError):
                features.append(0.0)
        
        # Extract cat__* features (categorical/binary)
        cat_features = sorted([k for k in decision_result.keys() if k.startswith("cat__")])
        for field in cat_features:
            val = decision_result.get(field, 0)
            try:
                features.append(float(val))
            except (ValueError, TypeError):
                features.append(0.0)
        
        if len(features) == 0:
            return None
        
        return np.array(features)
    
    except Exception as e:
        logger.warning(f"[SIMILARITY] Feature extraction failed: {e}")
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
        ref_df, ref_vectors, ref_labels, ref_ids = load_reference_data_from_s3(
            bucket=s3_bucket,
            key=s3_key,
            s3_uri=s3_uri,
            force_reload=force_reload
        )
        
        # Determine source URI for logging
        if s3_uri:
            source_uri = s3_uri
        else:
            bucket = s3_bucket or os.getenv("SIMILARITY_S3_BUCKET", DEFAULT_S3_BUCKET)
            key = s3_key or os.getenv("SIMILARITY_S3_KEY", DEFAULT_S3_KEY)
            source_uri = f"s3://{bucket}/{key}"
        
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
        
        # Build top matches list
        top_matches = []
        for idx, score in zip(top_indices, top_scores):
            top_matches.append({
                "TransactionID": ref_ids[idx],
                "similarity_score": float(score),
                "status_warning": ref_labels[idx],
                "index": int(idx)
            })
        
        # Get best match
        best_idx = top_indices[0]
        best_score = float(similarities[best_idx])
        best_label = ref_labels[best_idx]
        
        # Check if above threshold
        matched = best_score >= threshold
        
        result = {
            "matched": matched,
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
