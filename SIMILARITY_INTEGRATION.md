# Similarity Matching Integration

## Overview

This document describes the similarity matching integration with the SageMaker endpoint inference pipeline.

## Flow

```
1. Raw Transaction Input
   ↓
2. Preprocessing (inference_rules.py)
   ↓
3. K-Means Clustering
   - Generates: Cluster, Distance_to_Centroid, risk_score, risk_decision, is_outlier
   ↓
4. Similarity Matching (MANDATORY)
   - Compares ONLY features (num__ and cat__) with S3 reference data
   - S3 data location: metadata.decisionResult field
   - Validates schema: Only records with complete num__ and cat__ features are used
   ↓
5. Decision Override Logic:
   
   IF similarity_score >= threshold (default: 0.90):
     - risk_score = 70 (FIXED)
     - risk_decision = "Accept" if S3 status is "SAFE"
     - risk_decision = "Reject" if S3 status is "RISKY"
     - Add similarity_info to response
   
   ELSE (similarity_score < threshold):
     - Keep K-means risk_score and risk_decision
     - Add similarity_info to response (with lower score)
   ↓
6. Final Response with similarity_info
```

## Key Features

### 1. Feature-Only Comparison
- **Compares**: Only num__ (31 features) and cat__ (18 features) = 49 total features
- **Does NOT compare**: Post-processing fields (Cluster, Distance_to_Centroid, risk_score, risk_decision, is_outlier)
- **Rationale**: Post-processing fields are outputs from K-means and should not influence similarity

### 2. Automatic Schema Validation & Filtering
- Each S3 record is validated for complete num__ and cat__ features
- Records missing any required feature are **automatically skipped**
- Detailed skip statistics logged:
  - `parse_error`: JSON parsing failed
  - `missing_metadata`: No metadata field
  - `missing_decisionResult`: No decisionResult in metadata
  - `schema_invalid`: Missing num__ or cat__ features
  - `feature_extraction_failed`: Unable to extract feature vector

### 3. S3 Data Format

**Expected structure:**
```json
{
  "TransactionID": "1234567",
  "statusWarning": "SAFE",  // or "RISKY"
  "metadata": {
    "numericVariables": {...},
    "categoricalVariables": {...},
    "decisionResult": {
      "num__amount": -0.07262,
      "num__is_night": -0.22258,
      ... (31 num__ features total)
      "cat__TransactionProcessingType_Intime": 0,
      "cat__TransactionProcessingType_Intime_From_Recurrent": 0,
      ... (18 cat__ features total)
      // Post-processing fields are optional and NOT used for similarity
      "Cluster": 1,
      "Distance_to_Centroid": 11.008,
      "risk_score": 71,
      "risk_decision": "User Auth",
      "is_outlier": 1
    }
  }
}
```

## Configuration

### Environment Variables

```bash
# Similarity threshold (0.0 - 1.0)
export SIMILARITY_THRESHOLD=0.90

# S3 location of reference data
export SIMILARITY_S3_BUCKET=blossom-analytics-safe-dev-nv
export SIMILARITY_S3_KEY=safe_txns/data/similarity/SafeTransactionResults.csv

# Disable similarity matching (optional)
export DISABLE_SIMILARITY=1  # Set to 1 to disable
```

### Default Values
- **Threshold**: 0.90 (90% similarity required for match)
- **S3 Bucket**: blossom-analytics-safe-dev-nv
- **S3 Key**: safe_txns/data/similarity/SafeTransactionResults.csv

## Response Format

### Similarity Info Added to Each Transaction

```json
{
  "num__amount": -0.072,
  "num__is_night": -0.222,
  ... (all 49 features),
  "Cluster": 1,
  "Distance_to_Centroid": 11.008,
  "risk_score": 70,  // OVERRIDDEN if similarity >= threshold
  "risk_decision": "Reject",  // OVERRIDDEN if similarity >= threshold
  "is_outlier": 1,
  "similarity_info": {
    "matched": true,
    "similarity_score": 0.9542,
    "similarity_status": "RISKY",
    "top_matches": [
      {
        "TransactionID": "1234567",
        "similarity": 0.9542,
        "statusWarning": "RISKY"
      },
      {
        "TransactionID": "7654321",
        "similarity": 0.9123,
        "statusWarning": "RISKY"
      },
      ...
    ]
  }
}
```

## Schema Validation

### Required Features for Similarity Matching

**31 Numerical Features (num__)**:
- num__amount
- num__is_night
- num__hour_sin
- num__hour_cos
- num__day_of_week_cos
- num__count_all_txn_last_5m
- num__total_amount_all_txn_last_5m
- num__count_txn_to_recipient_account_last_5m
- num__total_amount_txn_to_recipient_account_last_5m
- num__count_txn_to_recipient_account_in_last_2_months
- num__is_first_txn_from_this_olb_user_to_this_recipient_account_q_6h
- num__amount_coef_var_lst6m
- num__pct_txns_under_100_lst6m
- num__pct_txns_over_1k_lst6m
- num__user_avg_amount_txn_per_active_day_last_6_months
- num__count_user_all_txn_in_last_6_months
- num__count_user_cancelled_txn_in_last_week
- num__count_user_cancelled_txn_in_last_month
- num__count_user_potential_fraud_txn_in_last_2_months
- num__recency_user_created_days
- num__count_suspected_actions_in_current_session
- num__total_actions_session
- num__is_auth_email_session
- num__is_auth_phone_session
- num__total_accounts
- num__user_age
- num__is_amount_greater_than_cu_p95_amount_ach_txn_in_last_6_months
- num__txn_amount_vs_cu_avg_amount_ach_txn_in_last_6_months
- num__is_batch
- num__amt_vs_user_ach_avg_day
- num__ach_count_share_6m

**18 Categorical Features (cat__)**:
- cat__TransactionProcessingType_Intime
- cat__TransactionProcessingType_Intime_From_Recurrent
- cat__TransactionProcessingType_Recurrent
- cat__TransactionProcessingType_Schedule
- cat__TransactionOrigin_External Internal
- cat__TransactionOrigin_Internal External
- cat__TransactionOrigin_M2m External
- cat__TransactionCategory_SEND_MONEY_ACH
- cat__TransactionCategory_SEND_MONEY_BATCH_PAYMENT_ACH
- cat__TransactionCategory_SEND_MONEY_PAYROLL_ACH
- cat__TransactionCategory_SINGLE_COLLECTION_ACH
- cat__TransactionCategory_TRANSFER_EXTERNAL_TO_LOAN_ACH
- cat__TransactionCategory_TRANSFER_INTERNAL_EXTERNAL_ACH
- cat__user_type_mixed
- cat__user_type_personal
- cat__access_DESKTOP
- cat__access_MOBILE
- cat__access_missing

**Total: 49 features** (31 num__ + 18 cat__)

## Files Modified

1. **endpoint/inference_rules.py**
   - Added lazy loading of similarity_matcher module
   - Added similarity matching after K-means clustering
   - Added decision override logic based on similarity threshold
   - Added similarity_info to response

2. **endpoint/similarity_matcher.py**
   - Modified `_extract_feature_vector()` to extract ONLY num__ and cat__ features
   - Updated `load_reference_data_from_s3()` to filter invalid S3 records
   - Added `_load_from_local_csv()` for testing with local files
   - Added support for `local_csv_path` parameter

3. **endpoint/schema_validator.py**
   - Added `validate_features_only()` function for feature-only validation
   - Updated `get_schema_info()` to return feature lists
   - Modified validation to skip post-processing fields

4. **test_similarity.py**
   - Updated to generate SAFE/RISKY status labels (not HIGH_RISK, MEDIUM_RISK, etc.)

## Testing

### Run Integration Test
```bash
python3 test_inference_integration.py
```

### Generate Test Reference Data
```bash
python3 test_similarity.py --num-samples 30
```

### End-to-End Test
```bash
python3 test_similarity_e2e.py --num-tests 5 --threshold 0.85
```

## Deployment

### 1. Upload Reference Data to S3
```bash
aws s3 cp data/reference_test.csv \
  s3://blossom-analytics-safe-dev-nv/safe_txns/data/similarity/SafeTransactionResults.csv
```

### 2. Deploy Updated Endpoint
The endpoint will automatically:
- Load similarity_matcher module on first request
- Cache S3 reference data for performance
- Validate and filter S3 records with incomplete schemas
- Apply similarity matching to all transactions

### 3. Configure Environment Variables (Optional)
Set environment variables in SageMaker endpoint configuration:
```python
env = {
    'SIMILARITY_THRESHOLD': '0.90',
    'SIMILARITY_S3_BUCKET': 'blossom-analytics-safe-dev-nv',
    'SIMILARITY_S3_KEY': 'safe_txns/data/similarity/SafeTransactionResults.csv'
}
```

## Monitoring

### Log Messages to Watch

**Successful similarity matching:**
```
[SIMILARITY] Checking similarity for 10 transactions (threshold: 0.90)
[SIMILARITY] Row 0: Match found (score: 0.9542, status: RISKY)
[SIMILARITY]   → Override: risk_score=70, risk_decision=Reject (S3 status: RISKY)
```

**Below threshold:**
```
[SIMILARITY] Row 1: Below threshold (score: 0.7834), keeping K-means decision
```

**Schema validation issues:**
```
[SIMILARITY] Skipped 5/100 records:
[SIMILARITY]   - schema_invalid: 3
[SIMILARITY]   - missing_decisionResult: 2
[SIMILARITY] Successfully loaded 95 valid records
```

## Troubleshooting

### Issue: All S3 records filtered out
**Cause**: S3 data missing required num__ or cat__ features
**Solution**: Ensure S3 data has complete feature schema (49 features)

### Issue: Similarity scores always 0
**Cause**: Feature extraction failing or dimension mismatch
**Solution**: Check logs for "feature extraction failed" messages

### Issue: No similarity matches found
**Cause**: Threshold too high or reference data doesn't have similar transactions
**Solution**: Lower threshold or add more reference data

## Performance

- **S3 Caching**: Reference data is cached in memory after first load
- **Feature Vector Size**: 49 dimensions (31 num__ + 18 cat__)
- **Similarity Calculation**: Cosine similarity (fast, O(n) per query)
- **Overhead**: ~10-50ms per transaction depending on reference data size

## Security

- S3 credentials managed by SageMaker execution role
- No sensitive data logged (only TransactionIDs and scores)
- Validation ensures only complete feature schemas are used
