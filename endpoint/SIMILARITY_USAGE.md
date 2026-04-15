# Similarity Matcher - Usage Examples

## Overview
The similarity matcher now supports flexible S3 path configuration through multiple methods:
- Default hardcoded values
- Environment variables
- Function parameters
- Full S3 URI

## Methods to Configure S3 Path

### 1. Use Defaults (Hardcoded)
```python
from similarity_matcher import find_similar_transaction

result = find_similar_transaction(query_result)
# Uses: s3://blossom-analytics-safe-dev-nv/safe_txns/data/similarity/SafeTransactionResults.csv
```

### 2. Environment Variables
```bash
export SIMILARITY_S3_BUCKET="my-custom-bucket"
export SIMILARITY_S3_KEY="my/custom/path/data.csv"
export SIMILARITY_THRESHOLD="0.85"
```

```python
result = find_similar_transaction(query_result)
# Uses environment variables
```

### 3. Function Parameters (Bucket + Key)
```python
result = find_similar_transaction(
    query_result,
    s3_bucket="my-custom-bucket",
    s3_key="my/custom/path/data.csv",
    threshold=0.85
)
```

### 4. Full S3 URI
```python
result = find_similar_transaction(
    query_result,
    s3_uri="s3://my-bucket/path/to/data.csv",
    threshold=0.90
)
```

## Complete Example

```python
from similarity_matcher import find_similar_transaction

# Your transaction decision result
query_result = {
    "Cluster": 2,
    "Distance_to_Centroid": 45.3,
    "risk_score": 75,
    "is_outlier": 1,
    "num__amount": 1500.0,
    "num__is_night": 1,
    # ... other features
}

# Option 1: Use custom S3 URI
result = find_similar_transaction(
    query_result,
    s3_uri="s3://blossom-analytics-safe-dev-nv/safe_txns/data/similarity/SafeTransactionResults.csv",
    threshold=0.90,
    metric="cosine",
    top_k=3
)

# Option 2: Use bucket and key separately
result = find_similar_transaction(
    query_result,
    s3_bucket="blossom-analytics-safe-dev-nv",
    s3_key="safe_txns/data/similarity/SafeTransactionResults.csv",
    threshold=0.85
)

# Check result
if result["matched"]:
    print(f"✓ Match found!")
    print(f"  Label: {result['status_warning']}")
    print(f"  Similarity: {result['similarity_score']:.4f}")
    print(f"  Source: {result['s3_source']}")
    print(f"\n  Top 3 matches:")
    for i, match in enumerate(result['top_matches'], 1):
        print(f"    {i}. TxnID: {match['TransactionID']}, "
              f"Score: {match['similarity_score']:.4f}, "
              f"Label: {match['status_warning']}")
else:
    print(f"✗ No match (best score: {result['similarity_score']:.4f})")
```

## Batch Processing

```python
from similarity_matcher import find_similar_transactions_batch

query_results = [result1, result2, result3, ...]

results = find_similar_transactions_batch(
    query_results,
    s3_uri="s3://my-bucket/path/data.csv",
    threshold=0.90,
    metric="cosine"
)

for i, result in enumerate(results):
    print(f"Transaction {i}: {result['status_warning']} (score: {result['similarity_score']:.4f})")
```

## Cache Management

```python
from similarity_matcher import get_cache_info, clear_cache

# View cache info
cache_info = get_cache_info()
print(f"Cached sources: {cache_info['num_cached_sources']}")
print(f"Sources: {cache_info['cached_sources']}")

# Clear specific cache
clear_cache(s3_uri="s3://bucket/path/file.csv")

# Clear all cache
clear_cache()
```

## CLI Usage

```bash
# Use default S3 path
python similarity_matcher.py --threshold 0.90

# Custom S3 URI
python similarity_matcher.py \
    --s3-uri "s3://my-bucket/path/data.csv" \
    --threshold 0.85 \
    --metric cosine

# Custom bucket and key
python similarity_matcher.py \
    --s3-bucket "my-bucket" \
    --s3-key "path/to/data.csv" \
    --threshold 0.90 \
    --force-reload

# Environment variables
export SIMILARITY_S3_BUCKET="my-bucket"
export SIMILARITY_S3_KEY="path/data.csv"
export SIMILARITY_THRESHOLD="0.85"
python similarity_matcher.py
```

## Integration with SageMaker Endpoint

When integrating with `inference_rules.py`:

```python
# In inference_rules.py
from similarity_matcher import find_similar_transaction

def predict_fn(input_data, model):
    # ... existing preprocessing and clustering code ...
    
    # Get S3 config from environment or use defaults
    s3_uri = os.getenv("SIMILARITY_S3_URI")  # Optional
    
    for row in output_data:
        decision_result = {
            "Cluster": row["Cluster"],
            "Distance_to_Centroid": row["Distance_to_Centroid"],
            # ... all features
        }
        
        # Find similar transaction
        similarity_result = find_similar_transaction(
            decision_result,
            s3_uri=s3_uri,  # Will use default if None
            threshold=0.90
        )
        
        # Add to output
        row["similarity_matched"] = similarity_result["matched"]
        row["similarity_score"] = similarity_result["similarity_score"]
        row["similarity_label"] = similarity_result["status_warning"]
        row["similarity_top_matches"] = similarity_result["top_matches"]
    
    return output_data
```

## Response Format

```json
{
    "matched": true,
    "similarity_score": 0.95,
    "status_warning": "HIGH_RISK",
    "top_matches": [
        {
            "TransactionID": "78901",
            "similarity_score": 0.95,
            "status_warning": "HIGH_RISK",
            "index": 42
        },
        {
            "TransactionID": "78902",
            "similarity_score": 0.88,
            "status_warning": "MEDIUM_RISK",
            "index": 15
        },
        {
            "TransactionID": "78903",
            "similarity_score": 0.82,
            "status_warning": "HIGH_RISK",
            "index": 99
        }
    ],
    "threshold_used": 0.90,
    "metric_used": "cosine",
    "reference_count": 1500,
    "s3_source": "s3://blossom-analytics-safe-dev-nv/safe_txns/data/similarity/SafeTransactionResults.csv"
}
```

## Configuration Priority

The S3 path is determined in this order (highest to lowest priority):

1. **s3_uri parameter** (if provided)
2. **s3_bucket + s3_key parameters** (if provided)
3. **Environment variables** (SIMILARITY_S3_BUCKET, SIMILARITY_S3_KEY)
4. **Default values** (hardcoded in the module)

## Environment Variables Reference

- `SIMILARITY_S3_BUCKET`: S3 bucket name
- `SIMILARITY_S3_KEY`: S3 object key path
- `SIMILARITY_THRESHOLD`: Similarity threshold (0.0-1.0)
- `DISABLE_SIMILARITY`: Set to "1" to disable similarity matching
