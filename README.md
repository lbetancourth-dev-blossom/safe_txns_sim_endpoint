# SAFE ML Transactions Endpoint

Risk scoring and fraud detection endpoint for credit union ACH transactions. Combines K-Means clustering, statistical rules (v8), and Athena-based similarity matching to classify each transaction as **Accept / User Auth / Admin Review / Reject**.

---

## Architecture

Three phases run in sequence for every transaction batch:

| Phase | Component | Input | Output |
|---|---|---|---|
| 1 | K-Means clustering | 49 features (47 numeric + 5 categorical) | `kmeans_cluster` (0–7), `risk_score` (0–1) |
| 2 | Statistical rules v8 | 12 rule conditions on raw features | `risk_score_normalized` (0–100), `risk_decision` |
| 3 | Similarity matching | 49 fields vs. Athena 6-month window | `sim_score`, `sim_status`, `sim_decision`, `sim_match_txn_id` |

Final `decision` = combination of all three phases. If similarity is unavailable the endpoint degrades gracefully to rules-only.

**Endpoint name**: `SAFE_TXNS_ENDPOINT_DEV`  
**Region**: `us-east-1` (dev account)  
**Instance**: `ml.m5.large`, framework `SKLearn 1.2-1`

---

## Input

CSV payload with header. 61 columns required. Key fields:

| Field | Type | Description |
|---|---|---|
| `TransactionID` | string | Unique transaction identifier |
| `amount` | float | Transaction amount (USD) |
| `createdAtTxns` | timestamp | Transaction creation time (local TZ) |
| `user_type` | string | `personal`, `business`, or `mixed` |
| `count_user_cancelled_txn_in_last_week` | int | Recent cancellations |
| `count_suspected_actions_in_current_session` | int | Suspected session actions |
| `count_all_txn_last_5m` | int | Burst in last 5 minutes |
| `is_first_txn_from_this_olb_user_to_this_recipient_account_q_6h` | int | First time to recipient (6h) |
| `txn_amount_vs_cu_avg_amount_ach_txn_in_last_6_months` | float | Ratio vs CU average |
| `recency_user_created_days` | int | User account age in days |

Full column reference: [`docs/references/ENDPOINT_INPUT_FORMAT.md`](docs/references/ENDPOINT_INPUT_FORMAT.md)

---

## Output

JSON array, one object per input row:

| Field | Type | Description |
|---|---|---|
| `decision` | string | Final decision: Accept / User Auth / Admin Review / Reject |
| `risk_score` | int | Normalized risk score (0–100) |
| `kmeans_cluster` | int | Assigned K-Means cluster (0–7) |
| `sim_match_txn_id` | string \| null | ID of best-matching historical transaction |
| `sim_score` | float \| null | Similarity score (0.0–1.0) |
| `sim_status` | string \| null | `HIGH_SIM`, `LOW_SIM`, or `NO_HISTORY` |
| `sim_decision` | string \| null | `Accept` if sim_score ≥ 0.90, `Reject` otherwise; null if no history |

---

## Quick Start

**1. Deploy from SageMaker notebook** (must be run from SageMaker Studio — not local CLI):

```python
# Open safe-txn-enpoint.ipynb in SageMaker Studio
# Run cells: Step 1 (package artifacts) → Step 2 (upload tarball) → Step 3 (deploy)
# Takes 5–10 minutes. Endpoint: SAFE_TXNS_ENDPOINT_DEV
```

**2. Invoke via boto3**:

```python
import boto3, io, json, pandas as pd

df = pd.read_csv("transactions.csv")
buf = io.StringIO()
df.to_csv(buf, header=True, index=False)

runtime = boto3.client("sagemaker-runtime", region_name="us-east-1")
response = runtime.invoke_endpoint(
    EndpointName="SAFE_TXNS_ENDPOINT_DEV",
    ContentType="text/csv",
    Body=buf.getvalue(),
)
predictions = json.loads(response["Body"].read().decode("utf-8"))
df_result = pd.DataFrame(predictions)
```

**3. Check endpoint status**:

```python
import boto3
sm = boto3.client("sagemaker", region_name="us-east-1")
r = sm.describe_endpoint(EndpointName="SAFE_TXNS_ENDPOINT_DEV")
print(r["EndpointStatus"])  # InService
```

---

## Documentation

| Document | Description |
|---|---|
| [`docs/guides/01-data-extraction.md`](docs/guides/01-data-extraction.md) | SQL query, feature groups, filtering rules, 61 columns |
| [`docs/guides/02-model-architecture.md`](docs/guides/02-model-architecture.md) | K-Means, rules v8, similarity, decision logic |
| [`docs/guides/03-statistical-rules.md`](docs/guides/03-statistical-rules.md) | Rules R1–R12 with thresholds and scoring |
| [`docs/guides/04-endpoint-usage.md`](docs/guides/04-endpoint-usage.md) | Invoke, input/output format, test scenarios, monitoring |
| [`docs/guides/05-deploy-guide.md`](docs/guides/05-deploy-guide.md) | Build tarball, deploy from notebook, env vars, cross-account Athena |
| [`docs/ENDPOINT_TECHNICAL_REFERENCE.md`](docs/ENDPOINT_TECHNICAL_REFERENCE.md) | Full technical reference including complete SQL query |
| [`docs/references/ENDPOINT_INPUT_FORMAT.md`](docs/references/ENDPOINT_INPUT_FORMAT.md) | Full 61-column input specification |
| [`docs/guides/ATHENA_TROUBLESHOOTING.md`](docs/guides/ATHENA_TROUBLESHOOTING.md) | Athena connectivity and query troubleshooting |

---

## Repository Layout

```
safe_txns_sim_endpoint/
├── README.md                        # This file
├── CLAUDE.md                        # Project context for AI agents
├── safe-txn-enpoint.ipynb           # SageMaker deploy & test notebook
│
├── endpoint/                        # SageMaker container code
│   ├── inference_rules.py           # Main inference entry point
│   ├── similarity_matcher.py        # Athena similarity matching
│   ├── schema_validator.py          # Feature schema validation
│   ├── statistical_rules.py         # Statistical rules v8 (R1–R12)
│   └── requirements.txt
│
├── deploy/                          # Deployment scripts
│   └── deploy_similarity_endpoint.py
│
├── tests/                           # pytest suite + utilities
│   ├── similarity/                  # Athena similarity tests
│   ├── endpoint/                    # Endpoint integration tests
│   └── utils/                      # process_endpoint.py, etc.
│
├── data/
│   └── test_escenarios.csv          # 16 test scenarios
│
└── docs/
    ├── guides/                      # 5 structured user guides
    ├── references/                  # Input format, troubleshooting
    ├── codemap/                     # Auto-generated architecture vault
    ├── ENDPOINT_TECHNICAL_REFERENCE.md
    └── PERFORMANCE_OPTIMIZATION_PLAN.md
```

---

**Last updated**: June 2026 | **Endpoint version**: V3 (`SAFE_TXNS_ENDPOINT_DEV`) | **Rules version**: v8
