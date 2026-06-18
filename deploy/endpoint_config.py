"""
Centralized configuration for SAFE_TXNS_ENDPOINT_DEV.
All endpoint env vars and AWS resources are defined here.
Update this file when the Athena table, database, or S3 paths change.
"""

# ── Endpoint identity ──────────────────────────────────────────────────────────
ENDPOINT_NAME  = "SAFE_TXNS_ENDPOINT_DEV"
INSTANCE_TYPE  = "ml.m5.large"
FRAMEWORK      = "1.2-1"

# ── Model artifacts (S3) ───────────────────────────────────────────────────────
BUCKET         = "blossom-analytics-safe-dev-nv"
MODEL_S3_KEY   = "safe_txns/similarity/endpoint/v2/model.tar.gz"
MODEL_S3_URI   = f"s3://{BUCKET}/{MODEL_S3_KEY}"

ARTIFACT_S3_PATHS = {
    "kmeans_model.joblib":           "safe_txns/kmeans/kmeans_analysis/V2/artifact/kmeans_model.joblib",
    "kmeans_artifacts.json":         "safe_txns/kmeans/kmeans_analysis/V2/artifact/kmeans_artifacts.json",
    "centroids.csv":                 "safe_txns/kmeans/centroids/V2/centroids.csv",
    "preprocessing_pipeline.joblib": "safe_txns/preprocessing/NOVEMBER/preprocessing_pipeline.joblib",
    "selected_features.csv":         "safe_txns/feature_selection/NOVEMBER/selected_features.csv",
}

# ── Athena (similarity matching) ──────────────────────────────────────────────
# Update here when the Silver layer table or database changes.
ATHENA_DATABASE  = "dlh_silver_safe_alpha"
ATHENA_TABLE     = "safetransactionresults"
ATHENA_S3_STAGING = "s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/"
ATHENA_REGION    = "us-east-2"

# ── Similarity matching tuning ─────────────────────────────────────────────────
SIMILARITY_THRESHOLD    = "0.90"
ATHENA_WINDOW_MONTHS    = "6"
ATHENA_TIMEOUT_SECONDS  = "10"

# ── Endpoint environment variables (passed to SageMaker at deploy time) ────────
ENDPOINT_ENV = {
    "SAGEMAKER_PROGRAM":            "inference_rules.py",
    "SIMILARITY_THRESHOLD":         SIMILARITY_THRESHOLD,
    "SIMILARITY_ATHENA_DATABASE":   ATHENA_DATABASE,
    "SIMILARITY_ATHENA_TABLE":      ATHENA_TABLE,
    "SIMILARITY_ATHENA_S3_STAGING": ATHENA_S3_STAGING,
    "SIMILARITY_ATHENA_REGION":     ATHENA_REGION,
    "ATHENA_WINDOW_MONTHS":         ATHENA_WINDOW_MONTHS,
    "ATHENA_TIMEOUT_SECONDS":       ATHENA_TIMEOUT_SECONDS,
}
