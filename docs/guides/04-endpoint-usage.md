# Endpoint Usage Guide

## Prerequisites

- AWS profile `blossom-dev` configured and SSO logged in
- Region `us-east-1`
- Python 3.10+, `boto3`, `pandas` installed

```bash
aws sso login --sso-session blossom
```

---

## Deploy

Deployment must be run from a **SageMaker Studio notebook** — not from a local CLI. The IAM trust policy requires the SageMaker service principal to access the model tarball in S3; local machines cannot assume that role.

1. Open SageMaker Studio in the dev account (us-east-1)
2. Open `safe-txn-enpoint.ipynb`
3. Run the cells in order:
   - **Step 1**: Downloads artifacts from S3, packages them into `model.tar.gz`
   - **Step 2**: Uploads `model.tar.gz` to `s3://blossom-analytics-safe-dev-nv/safe_txns/similarity/endpoint/v2/`
   - **Step 3**: Deploys the endpoint (takes 5–10 minutes)

Full deployment details: [`docs/guides/05-deploy-guide.md`](05-deploy-guide.md)

---

## Invoke via boto3

```python
import boto3
import io
import json
import pandas as pd

# Load input
df = pd.read_csv("transactions.csv")

# Serialize to CSV
buf = io.StringIO()
df.to_csv(buf, header=True, index=False)
payload = buf.getvalue()

# Invoke endpoint
runtime = boto3.client(
    "sagemaker-runtime",
    region_name="us-east-1",
)
response = runtime.invoke_endpoint(
    EndpointName="SAFE_TXNS_ENDPOINT_DEV",
    ContentType="text/csv",
    Body=payload,
)

# Parse response
predictions = json.loads(response["Body"].read().decode("utf-8"))
df_result = pd.DataFrame(predictions)
print(df_result[["TransactionID", "decision", "risk_score", "sim_status"]])
```

---

## Input Format

- **Format**: CSV with header row
- **Columns**: 61 (exact names and order required — see [`docs/references/ENDPOINT_INPUT_FORMAT.md`](../references/ENDPOINT_INPUT_FORMAT.md))
- **Encoding**: UTF-8
- **Timestamps**: `createdAtTxns` must be parseable (ISO 8601 or `YYYY-MM-DD HH:MM:SS`)

Key column types:

| Column | Type | Notes |
|---|---|---|
| `TransactionID` | string | Required for output correlation |
| `amount` | float | USD, must be > 0 |
| `createdAtTxns` | timestamp | Local timezone of the FI |
| `is_batch` | int | 0 or 1 |
| `user_type` | string | `personal`, `business`, or `mixed` |
| All `count_*` columns | int | 0 if no history |
| All `pct_*` columns | float | 0.0–1.0 |
| All `is_*` columns | int | 0 or 1 |

Missing columns default to `0` (coerce mode). Rows with unparseable timestamps are dropped (filter mode).

---

## Output Format

JSON array. One object per input row. Fields:

| Field | Type | Description |
|---|---|---|
| `TransactionID` | string | Echoed from input |
| `decision` | string | Final decision: Accept / User Auth / Admin Review / Reject |
| `risk_score` | int | Normalized rules score (0–100) |
| `risk_decision` | string | Decision from rules phase |
| `risk_score_raw` | int | Raw rules score before normalization |
| `explanation` | string | Which rules fired and their points |
| `kmeans_cluster` | int | K-Means cluster assignment (0–7) |
| `Distance_to_Centroid` | float | Euclidean distance to cluster centroid |
| `is_outlier` | int | 1 if anomalous within cluster |
| `sim_match_txn_id` | string \| null | ID of best historical match |
| `sim_score` | float \| null | Similarity score (0.0–1.0) |
| `sim_status` | string \| null | HIGH_SIM / LOW_SIM / NO_HISTORY |
| `sim_decision` | string \| null | Accept (HIGH_SIM) or Reject |
| `rule_1` … `rule_12` | int | Points from each individual rule |
| `top_contributors` | string | Top 3 features driving K-Means assignment |
| `audit_category` | string | Risk category label |
| `audit_explanation` | string | Technical audit string |
| `ux_copy` | string | User-facing message |

---

## Test Scenarios

The file `data/test_escenarios.csv` contains 16 rows covering the main scenarios:

| Scenario | Description |
|---|---|
| HIGH_SIM | Transaction closely matching a historical one (sim_score ≥ 0.90) |
| LOW_SIM | Transaction with a historical match but low similarity |
| NO_HISTORY | No historical transactions found in the 6-month window |
| NIGHT_BURST | Nighttime + burst (R2 + R7 active) |
| NEW_USER | Account created < 30 days ago (R12 active) |
| HIGH_CU_RATIO | Amount > 5× CU average (R11 max points) |
| FIRST_RECIPIENT | First time to this recipient in 6h (R3 active) |
| WEEKEND | Weekend transaction (R10 active) |
| CANCELLED | Multiple cancellations in prior week (R4 active) |
| SUSPECTED_SESSION | Suspected actions in session (R5 active) |
| BATCH | Batch transaction (R7 skipped, is_batch=1) |
| HIGH_AMOUNT_LOW_HIST | Amount > $1000 but < 10% of historical txns over $1k (R6 active) |
| EDGE_ZERO_AMOUNT | amount = 0 (filtered at extraction, endpoint should handle gracefully) |
| EDGE_NULL_HISTORY | All historical count columns = 0 |
| ACCEPT_CLEAN | Normal low-risk transaction (all rules = 0) |
| REJECT_MULTI | Multiple rules fire simultaneously |

To invoke with test scenarios:

```bash
python tests/utils/process_endpoint.py \
  --input data/test_escenarios.csv \
  --output data/test_escenarios_result.csv
```

---

## Monitor

CloudWatch log group: `/aws/sagemaker/Endpoints/SAFE_TXNS_ENDPOINT_DEV`

```python
import boto3

logs = boto3.client("logs", region_name="us-east-1")
response = logs.filter_log_events(
    logGroupName="/aws/sagemaker/Endpoints/SAFE_TXNS_ENDPOINT_DEV",
    limit=50,
)
for event in response["events"]:
    print(event["message"])
```

Check endpoint health:

```python
sm = boto3.client("sagemaker", region_name="us-east-1")
r = sm.describe_endpoint(EndpointName="SAFE_TXNS_ENDPOINT_DEV")
print(r["EndpointStatus"])  # InService = healthy
```

---

## Troubleshoot

| Symptom | Cause | Fix |
|---|---|---|
| `sim_*` all `null` | Athena permissions or data missing | Check IAM cross-account role; verify `dlh_silver_safe_alpha.safetransactionresults` exists |
| Athena timeout | Query taking > `ATHENA_TIMEOUT_SECONDS` | Increase env var at deploy time; check Athena workgroup |
| `ValidationError` | Mismatched column names or types | Verify CSV headers match exactly the 61 expected names |
| `EndpointStatus: Failed` | Bad tarball or wrong sklearn version | Check `FailureReason` in `describe_endpoint`; verify `model.tar.gz` structure |
| All `risk_score = 0` | `DISABLE_RULES=1` set | Remove env var or check endpoint config |
| Slow response (> 10s) | Large batch or cold start | Split batches > 1000 rows; first invocation after idle may be 10–15s |
