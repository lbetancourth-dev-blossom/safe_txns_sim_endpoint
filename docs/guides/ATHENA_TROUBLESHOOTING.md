# Athena Similarity Matching Troubleshooting

## Problem: sim_* Fields Return None

When the endpoint returns `sim_match_txn_id: None, sim_score: None, sim_status: None, sim_decision: None`, it means the Athena query is not finding any matching historical transactions.

```json
{
  "TransactionID": 1032495,
  "idOLBUserTxns": 597178,
  "sim_match_txn_id": null,  // ← Problem
  "sim_score": null,         // ← Problem
  "sim_status": null,        // ← Problem
  "sim_decision": null       // ← Problem
}
```

## Root Causes

### 1. No Historical Data in Athena

**Symptom**: Athena query returns 0 rows for the user

**Check**:
```sql
-- Run in Athena console
SELECT COUNT(*) as transaction_count
FROM dlh_silver_safe_alpha.safetransactionresults
WHERE idolbuser = 597178
  AND statuswarning IN ('SAFE', 'RISKY');
```

**Expected**: COUNT > 0  
**Actual**: COUNT = 0 → No data for this user

**Solution**:
- Verify user ID is correct
- Check if data exists in the Silver layer
- Verify table name: `dlh_silver_safe_alpha.safetransactionresults`
- Check date range: is data between 2024-12-18 and 2026-06-18?

---

### 2. Athena Configuration Issues

**Check the environment variables** in the SageMaker endpoint:

```
SIMILARITY_ATHENA_DATABASE=dlh_silver_safe_alpha
SIMILARITY_ATHENA_TABLE=safetransactionresults
SIMILARITY_ATHENA_S3_STAGING=s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/
SIMILARITY_ATHENA_REGION=us-east-2
```

**Verify each**:

```bash
# 1. Database exists
aws athena list-databases \
  --region us-east-2 \
  --catalog AwsDataCatalog | grep dlh_silver_safe_alpha

# 2. Table exists
aws athena start-query-execution \
  --query-string "SELECT 1 FROM dlh_silver_safe_alpha.safetransactionresults LIMIT 1" \
  --query-execution-context Database=dlh_silver_safe_alpha \
  --result-configuration OutputLocation=s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/ \
  --region us-east-2

# 3. S3 staging directory is accessible
aws s3 ls s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/ \
  --region us-east-2
```

---

### 3. IAM Permissions

**Required permissions for the SageMaker endpoint role**:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "athena:StartQueryExecution",
        "athena:GetQueryExecution",
        "athena:GetQueryResults",
        "athena:StopQueryExecution"
      ],
      "Resource": "arn:aws:athena:us-east-2:*:workgroup/primary"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::blossom-analytics-datalake-alpha",
        "arn:aws:s3:::blossom-analytics-datalake-alpha/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "glue:GetDatabase",
        "glue:GetTable",
        "glue:GetPartitions"
      ],
      "Resource": "*"
    }
  ]
}
```

---

### 4. Date Range Issues

The query uses a **sliding window**: `[transaction_date - 6 months, transaction_date]`

For transaction on **2026-06-18**, the window is **[2025-12-18, 2026-06-18]**

**Check if data exists in this range**:

```sql
SELECT 
  COUNT(*) as count,
  MIN(CAST(createdat AS DATE)) as earliest,
  MAX(CAST(createdat AS DATE)) as latest
FROM dlh_silver_safe_alpha.safetransactionresults
WHERE idolbuser = 597178
  AND statuswarning IN ('SAFE', 'RISKY')
  AND CAST(createdat AS DATE) >= '2025-12-18'
  AND CAST(createdat AS DATE) <= '2026-06-18';
```

Expected: count > 0, and min/max within range

---

## Debugging Steps

### Step 1: Verify Athena Data
```bash
# In SageMaker Notebook or local environment (if you have Athena access)
import boto3
import pandas as pd
from pyathena import connect

# Connect to Athena
conn = connect(s3_staging_dir='s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/', region_name='us-east-2')
cursor = conn.cursor()

# Query
cursor.execute("""
    SELECT COUNT(*) as count
    FROM dlh_silver_safe_alpha.safetransactionresults
    WHERE idolbuser = 597178
    AND statuswarning IN ('SAFE', 'RISKY')
    LIMIT 10
""")

df = pd.read_sql(cursor)
print(df)
```

### Step 2: Check CloudWatch Logs
```bash
# See what the endpoint is logging
aws logs tail /aws/sagemaker/Endpoints/data-safe-txns-endpoint --follow

# Look for:
# [SIMILARITY] Loading from Athena for idolbuser=597178
# [SIMILARITY] No Athena data for idolbuser=597178  ← This means query returned 0 rows
```

### Step 3: Run Debug Script
```bash
# From the repo
python3 tests/debug_similarity.py

# This will show:
# 1. If exact fields are extracted ✓
# 2. If Athena query executes
# 3. How many rows are returned
# 4. If matching works
```

---

## Common Solutions

### Solution 1: Add Test Data to Athena

If there's no historical data, insert test transactions:

```sql
-- Create test transactions for user 597178
INSERT INTO dlh_silver_safe_alpha.safetransactionresults
  (idolbuser, createdat, statuswarning, metadata, transactionid)
VALUES
  (597178, '2026-06-15 10:00:00+00:00', 'SAFE', '{"decisionResult": {...}}', 1001),
  (597178, '2026-06-10 14:30:00+00:00', 'RISKY', '{"decisionResult": {...}}', 1002);
```

### Solution 2: Verify Configuration Variables

In SageMaker endpoint environment, verify variables are set:

```python
import os

print("Athena Configuration:")
print(f"  Database: {os.getenv('SIMILARITY_ATHENA_DATABASE')}")
print(f"  Table: {os.getenv('SIMILARITY_ATHENA_TABLE')}")
print(f"  S3 Staging: {os.getenv('SIMILARITY_ATHENA_S3_STAGING')}")
print(f"  Region: {os.getenv('SIMILARITY_ATHENA_REGION')}")
```

### Solution 3: Update Table/Database Names

If using different names, update in `inference_rules.py`:

```python
# Line ~1123 in inference_rules.py
database = os.getenv("SIMILARITY_ATHENA_DATABASE", "dlh_silver_safe_alpha")
table = os.getenv("SIMILARITY_ATHENA_TABLE", "safetransactionresults")
```

---

## Expected Behavior

### When Athena Has Data ✅

```python
# Logs show:
# [SIMILARITY] Loading from Athena for idolbuser=597178
# [SIMILARITY] Exact field match: checked 5 reference rows, best match score=0.8234 (41/49 fields matched)

# Response:
{
  "sim_match_txn_id": 1816246,
  "sim_score": 0.8234,
  "sim_status": "SAFE",
  "sim_decision": "match"
}
```

### When Athena Has NO Data ❌

```python
# Logs show:
# [SIMILARITY] Loading from Athena for idolbuser=597178
# [SIMILARITY] No Athena data for idolbuser=597178

# Response:
{
  "sim_match_txn_id": None,
  "sim_score": None,
  "sim_status": None,
  "sim_decision": None
}
```

This is **graceful degradation** — the endpoint still works, but without similarity data.

---

## Testing Locally

To test similarity matching without deploying to SageMaker:

```bash
# 1. Have AWS credentials configured
aws configure

# 2. Run debug script
python3 tests/debug_similarity.py

# 3. Check output for:
# - "No data from Athena" → Check data existence
# - "Best match score=X" → Matching works!
# - NoCredentialsError → Configure AWS credentials
```

---

## Quick Checklist

- [ ] User ID (597178) has transactions in Athena table
- [ ] Transactions are within the 6-month window (2025-12-18 to 2026-06-18)
- [ ] statuswarning is 'SAFE' or 'RISKY'
- [ ] Table name is correct: `dlh_silver_safe_alpha.safetransactionresults`
- [ ] S3 staging directory exists and is accessible
- [ ] SageMaker role has Athena + S3 permissions
- [ ] Environment variables are set correctly in endpoint
- [ ] No Athena network/VPC issues blocking the connection

---

## References

- [Athena SQL Reference](https://docs.aws.amazon.com/athena/latest/ug/functions-operators-reference.html)
- [PyAthena Documentation](https://pyathena.readthedocs.io/)
- [SageMaker Execution Role Permissions](https://docs.aws.amazon.com/sagemaker/latest/dg/sagemaker-roles.html)
