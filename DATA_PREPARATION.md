# Data Preparation Guide for Similarity Matching

## Overview

The similarity matching system compares incoming transactions against historical reference data stored in S3. For accurate matching, **both datasets must have the exact same schema**.

## Schema Requirements

### 1. Input Data (Incoming Transactions)

The input transactions are automatically preprocessed by `inference_rules.py`, which generates:

**Numerical Features (31 fields):**
- `num__amount`, `num__is_night`, `num__hour_sin`, `num__hour_cos`
- `num__count_all_txn_last_5m`, `num__total_amount_all_txn_last_5m`
- `num__count_user_cancelled_txn_in_last_week`
- `num__user_avg_amount_txn_per_active_day_last_6_months`
- ... and 23 more numerical features

**Categorical Features (18 fields):**
- `cat__TransactionProcessingType_Intime`
- `cat__TransactionOrigin_External Internal`
- `cat__TransactionCategory_SEND_MONEY_ACH`
- `cat__user_type_mixed`, `cat__user_type_personal`
- ... and 13 more categorical features

**Post-Processing Fields (5 fields):**
- `Cluster` (int): Cluster assignment from K-Means
- `Distance_to_Centroid` (float): Distance to cluster centroid
- `risk_score` (int): Risk score (0-100)
- `risk_decision` (str): Decision (Accept, User Auth, Admin Review, Reject)
- `is_outlier` (int): 1 if outlier, 0 otherwise

**Total: 54 fields**

### 2. Reference Data (S3 CSV)

The S3 reference CSV must have the following structure:

#### Required Columns:

1. **`TransactionID`** (or `transactionId`, `transaction_id`, `id`)
   - Unique identifier for each transaction
   - Used in similarity match results

2. **`metadata`** (JSON string or dict)
   - Must contain a `decisionResult` field
   - The `decisionResult` must have the same 54 fields as above

3. **`statusWarning`** (string)
   - The label to return when a match is found
   - Examples: "HIGH_RISK", "FRAUD_DETECTED", "SUSPICIOUS", "NORMAL"

#### CSV Structure Example:

```csv
TransactionID,metadata,statusWarning
12345,"{""decisionResult"": {""Cluster"": 2, ""Distance_to_Centroid"": 45.3, ""risk_score"": 85, ...}}",HIGH_RISK
12346,"{""decisionResult"": {""Cluster"": 1, ""Distance_to_Centroid"": 12.1, ""risk_score"": 35, ...}}",NORMAL
```

#### Metadata JSON Structure:

```json
{
  "decisionResult": {
    "Cluster": 2,
    "Distance_to_Centroid": 45.3,
    "risk_score": 85,
    "risk_decision": "Admin Review",
    "is_outlier": 1,
    "num__amount": 1500.0,
    "num__is_night": 1,
    "num__hour_sin": 0.866,
    "num__hour_cos": -0.5,
    ... (all 54 fields)
  }
}
```

## How to Prepare Reference Data

### Option 1: Use Existing Endpoint Output

The easiest way is to use transactions that have already been processed by the endpoint:

1. **Run transactions through the endpoint** (see notebook)
2. **Save the output** which already has the correct schema
3. **Add `statusWarning` labels** manually or programmatically
4. **Format as required CSV**

```python
import pandas as pd
import json

# Load endpoint output
df_results = pd.read_csv("endpoint_output.csv")

# Add statusWarning based on your criteria
def assign_label(row):
    if row['risk_score'] >= 90:
        return "HIGH_RISK"
    elif row['risk_score'] >= 70:
        return "MEDIUM_RISK"
    else:
        return "NORMAL"

df_results['statusWarning'] = df_results.apply(assign_label, axis=1)

# Create metadata JSON
def create_metadata(row):
    decision_result = row.to_dict()
    # Remove non-feature fields
    for field in ['TransactionID', 'statusWarning']:
        decision_result.pop(field, None)
    return json.dumps({"decisionResult": decision_result})

df_results['metadata'] = df_results.apply(create_metadata, axis=1)

# Keep only required columns
df_final = df_results[['TransactionID', 'metadata', 'statusWarning']]

# Save to CSV
df_final.to_csv("reference_data.csv", index=False)
```

### Option 2: Manual Creation

If you have historical data with labels but not preprocessed:

1. **Run historical transactions through the endpoint**
2. **Match with your labels** by TransactionID
3. **Create the CSV** as shown above

## Validation

Before using reference data, validate it:

### Using the Validation Script

```bash
# Validate local file
python validate_s3_data.py \
    --local-csv reference_data.csv \
    --output validation_report.json

# Validate S3 file
python validate_s3_data.py \
    --s3-uri s3://bucket/path/SafeTransactionResults.csv \
    --output validation_report.json \
    --sample-size 100

# Show expected schema
python validate_s3_data.py --show-schema
```

### Validation Checks

The script validates:
- ✓ CSV has required columns (TransactionID, metadata, statusWarning)
- ✓ metadata is valid JSON
- ✓ metadata contains decisionResult
- ✓ decisionResult has all core fields (Cluster, Distance_to_Centroid, etc.)
- ✓ Field coverage matches expected schema

### Expected Validation Output

```
=== Validating CSV Structure ===
✓ CSV structure looks good

=== Validating Metadata Schema (sample: 100) ===
Valid records: 95/100 (95.0%)
Invalid records: 5
Parse errors: 0
Missing decisionResult: 0
Expected fields coverage: 98.1%

✓ No issues found. Data looks ready for similarity matching!
```

## Upload to S3

Once validated, upload to S3:

```bash
aws s3 cp reference_data.csv \
    s3://blossom-analytics-safe-dev-nv/safe_txns/data/similarity/SafeTransactionResults.csv
```

Or using Python:

```python
import boto3

s3_client = boto3.client("s3")
s3_client.upload_file(
    "reference_data.csv",
    "blossom-analytics-safe-dev-nv",
    "safe_txns/data/similarity/SafeTransactionResults.csv"
)
```

## Testing

Test the similarity matching:

```bash
python similarity_matcher.py \
    --s3-uri s3://blossom-analytics-safe-dev-nv/safe_txns/data/similarity/SafeTransactionResults.csv \
    --threshold 0.90
```

## Common Issues and Solutions

### Issue 1: "Missing core fields"

**Problem:** Reference data doesn't have Cluster, Distance_to_Centroid, etc.

**Solution:** Run transactions through the endpoint first. The endpoint generates these fields automatically.

### Issue 2: "Feature dimension mismatch"

**Problem:** Input has 54 features but reference has 50.

**Solution:** 
- Ensure reference data was generated with the same version of `inference_rules.py`
- Check that preprocessing pipeline hasn't changed
- Regenerate reference data if pipeline was updated

### Issue 3: "Low schema coverage"

**Problem:** Only 60% of records have valid schema.

**Solution:**
- Check metadata JSON format
- Ensure decisionResult is not empty
- Validate that all transactions went through the same preprocessing

### Issue 4: "No TransactionID column"

**Problem:** CSV is missing TransactionID.

**Solution:**
- Rename your ID column to `TransactionID`
- Or ensure it's named one of: `transactionId`, `transaction_id`, `id`

## Best Practices

1. **Use Recent Data:** Reference data should be recent and representative
2. **Regular Updates:** Update reference data periodically as patterns change
3. **Quality Over Quantity:** Better to have 1,000 high-quality labeled transactions than 10,000 unlabeled
4. **Version Control:** Keep track of which version of reference data is in use
5. **Balanced Labels:** Ensure statusWarning labels are balanced (not all HIGH_RISK)

## Schema Change Management

If the preprocessing pipeline changes:

1. **Regenerate reference data** with new schema
2. **Update S3 file**
3. **Clear similarity cache** (or restart endpoint)
4. **Test** with validation script

## Questions?

For schema information:
```bash
python validate_s3_data.py --show-schema
```

For detailed field list:
```python
from schema_validator import get_schema_info
info = get_schema_info()
print(info)
```
