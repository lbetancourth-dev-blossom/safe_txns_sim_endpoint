# Safe Transactions Endpoint — Technical Reference

## 1. Endpoint

| Property | Value |
|---|---|
| **Name** | `SAFE_TXNS_ENDPOINT_DEV` |
| **Type** | SageMaker SKLearn 1.2-1 |
| **Instance** | ml.m5.large |
| **Region** | us-east-1 (endpoint) · us-east-2 (Athena data) |
| **AWS Account** | 436631265256 (development) |
| **Entry point** | `inference_rules.py` |
| **Model tarball** | `s3://blossom-analytics-safe-dev-nv/safe_txns/similarity/endpoint/v2/model.tar.gz` |

---

## 2. What it does — 3-phase pipeline

**Phase 1 — K-Means Clustering:** The preprocessing pipeline (`ColumnTransformer` + `OneHotEncoder`) transforms the 61 raw input columns into scaled numerical and one-hot encoded categorical features. These are passed to the K-Means model, which assigns a cluster (0–9) and computes the Euclidean distance to the centroid. Each cluster has a trained scaler that maps distance to a `kmeans_risk_score` (0–100) and `kmeans_risk_decision` (Accept / User Auth / Admin Review / Reject). K-Means always produces a decision — it never fails silently.

**Phase 2 — Statistical Rules v8 (R1–R12):** Twelve piecewise-scoring rules run on the raw input features in parallel with K-Means. Rules fire on signals like large-batch transactions, first-time recipients, high amount vs. user average, cancelled/fraud history, and session anomalies. The rule scores are combined with the K-Means score to produce the final `risk_score` and `risk_decision`. Rules can be disabled via `DISABLE_RULES=1` (score defaults to 0).

**Phase 3 — Similarity Matching (optional):** For each transaction, the endpoint queries Amazon Athena (`dlh_silver_safe_alpha.safetransactionresults`) for the same user's transaction history over a 6-month sliding window. It compares 49 preprocessed features (31 `num__` + 18 `cat__`) using cosine similarity. If `sim_score >= 0.90`, it writes a `sim_decision` (Accept if the matched transaction was SAFE, Reject if RISKY). If Athena is unavailable or `idOLBUserTxns` is absent, all `sim_*` fields are `null` and K-Means + rules continue normally — no downtime.

---

## 3. Input format

The endpoint accepts `text/csv` with a header row and the following **61 columns** (in any order):

| Column | Type | Nullable | Description |
|---|---|---|---|
| `TransactionID` | int64 | no | Unique transaction identifier |
| `idOLBUserTxns` | int64 | no (null → sim_*=null) | OLB user ID. Required for similarity |
| `createdAtTxns` | string | no (null → sim_*=null) | Transaction timestamp: `YYYY-MM-DD HH:MM:SS.mmm` |
| `idFi` | int64 | no | Credit union ID (e.g., 52) |
| `recipient_key` | string | no | Destination account identifier |
| `amount` | float64 | no | Transaction amount (USD) |
| `is_night` | int (0/1) | no | 1 if transaction occurred at night |
| `hour_sin` | float64 | no | Sine encoding of hour-of-day |
| `hour_cos` | float64 | no | Cosine encoding of hour-of-day |
| `day_of_week_cos` | float64 | no | Cosine encoding of day-of-week |
| `month_cos` | float64 | no | Cosine encoding of month |
| `weekend` | int (0/1) | no | 1 if transaction is on a weekend |
| `count_all_txn_last_5m` | int64 | no | User transactions in last 5 minutes |
| `total_amount_all_txn_last_5m` | float64 | yes (69%) | Total amount in last 5 minutes |
| `count_txn_to_recipient_account_last_5m` | int64 | no | Transactions to same recipient in last 5 min |
| `total_amount_txn_to_recipient_account_last_5m` | float64 | yes (94%) | Amount to same recipient in last 5 min |
| `count_txn_to_recipient_account_in_last_2_months` | int64 | no | Transactions to this recipient in last 2 months |
| `count_txn_to_recipient_account_in_last_week` | int64 | no | Transactions to this recipient in last week |
| `count_all_txn_after_recipient_account_creation` | float64 | yes (70%) | Total transactions since recipient account was created |
| `is_first_txn_from_this_olb_user_to_this_recipient_account_q_6h` | int (0/1) | no | 1 if first transaction to recipient in last 6h |
| `is_first_txn_from_this_account_to_recipient_account_q_72h` | int (0/1) | no | 1 if first transaction to recipient in last 72h |
| `amount_coef_var_lst6m` | float64 | yes (40%) | Coefficient of variation of amount over 6 months |
| `pct_txns_under_100_lst6m` | float64 | yes (40%) | % of transactions under $100 in last 6 months |
| `pct_txns_over_1k_lst6m` | float64 | yes (40%) | % of transactions over $1000 in last 6 months |
| `user_avg_count_txn_per_active_day_last_6_months` | float64 | no | Avg transactions per active day over 6 months |
| `user_avg_amount_txn_per_active_day_last_6_months` | float64 | no | Avg amount per active day over 6 months |
| `count_user_all_txn_in_last_6_months` | int64 | no | Total user transactions in last 6 months |
| `count_user_cancelled_txn_in_last_week` | float64 | yes (54%) | Cancelled transactions in last week |
| `count_user_cancelled_txn_in_last_month` | float64 | yes (40%) | Cancelled transactions in last month |
| `count_user_potential_fraud_txn_in_last_2_months` | float64 | yes (40%) | Potential fraud-flagged transactions in last 2 months |
| `recency_user_created_days` | int64 | no | Days since user account was created |
| `is_access_from_remembered_device` | int (0/1) | no | 1 if access from a remembered device |
| `count_suspected_actions_in_current_session` | float64 | yes (38%) | Suspected actions in current session |
| `total_actions_session` | float64 | yes (38%) | Total actions in current session |
| `is_auth_email_session` | float64 (0/1) | yes (38%) | 1 if session authenticated via email |
| `is_auth_phone_session` | float64 (0/1) | yes (38%) | 1 if session authenticated via phone |
| `is_any_auth_session` | float64 (0/1) | yes (38%) | 1 if any additional authentication in session |
| `count_failed_actions_in_current_session` | float64 | yes (38%) | Failed actions in current session |
| `days_since_phone_update` | float64 | yes (26%) | Days since last phone update |
| `days_since_email_update` | float64 | yes (62%) | Days since last email update |
| `is_personal_user_phone_primary_updated_last_week` | int (0/1) | no | 1 if primary phone updated in last week |
| `is_personal_user_email_primary_updated_last_week` | int (0/1) | no | 1 if primary email updated in last week |
| `total_accounts` | int64 | no | Total accounts for this user |
| `checking_ratio` | float64 | no | Proportion of checking accounts |
| `savings_ratio` | float64 | no | Proportion of savings accounts |
| `credit_loan_ratio` | float64 | no | Proportion of credit/loan accounts |
| `user_age` | float64 | yes (28%) | User age in years |
| `user_type` | string | no | `personal` or `mixed` |
| `access` | string | yes (38%) | Access channel: `DESKTOP` or `MOBILE` |
| `TransactionProcessingType` | string | no | `Intime`, `Intime_From_Recurrent`, `Recurrent`, `Schedule` |
| `TransactionOrigin` | string | no | `Blossom Pay`, `External Internal`, `Internal External`, `M2m External` |
| `TransactionCategory` | string | no | ACH category (e.g., `SEND_MONEY_ACH`, `SEND_MONEY_BATCH_PAYMENT_ACH`) |
| `cu_avg_amount_ach_txn_in_last_6_months` | float64 | no | CU average ACH amount over 6 months |
| `is_amount_greater_than_cu_p95_amount_ach_txn_in_last_6_months` | int (0/1) | no | 1 if amount exceeds CU 95th percentile |
| `txn_amount_vs_cu_avg_amount_ach_txn_in_last_6_months` | float64 | no | Ratio of amount to CU average |
| `is_batch` | int (0/1) | no | 1 if transaction is part of a batch |
| `num_recipients_batch` | float64 | yes (76%) | Number of recipients in batch |
| `amount_share_in_batch` | float64 | no | Proportion of this transaction's amount in the batch total |
| `amt_vs_user_ach_avg_day` | float64 | yes (4%) | Ratio of amount vs. user's daily ACH average |
| `ach_amount_share_6m` | float64 | yes (4%) | Proportion of ACH amount in user total (6 months) |
| `ach_count_share_6m` | float64 | yes (2%) | Proportion of ACH transactions in user total (6 months) |

---

## 4. Data collection query (PostgreSQL)

This is the production query used to generate the inference input from the OLB database:

```sql
WITH params AS (
    SELECT
        52 AS id_fi,
        NOW() - INTERVAL '90 days' AS start_date,
        NOW() AS end_date
),
base_txns AS (
    SELECT
        t.id AS "TransactionID",
        t.id_olb_user AS "idOLBUserTxns",
        t.created_at AS "createdAtTxns",
        t.id_fi AS "idFi",
        COALESCE(t.recipient_account_id::text, t.recipient_key) AS "recipient_key",
        t.amount,
        EXTRACT(HOUR FROM t.created_at) AS hour_raw,
        CASE WHEN EXTRACT(HOUR FROM t.created_at) BETWEEN 22 AND 24
                  OR EXTRACT(HOUR FROM t.created_at) BETWEEN 0 AND 6
             THEN 1 ELSE 0 END AS is_night,
        SIN(2 * PI() * EXTRACT(HOUR FROM t.created_at) / 24.0) AS hour_sin,
        COS(2 * PI() * EXTRACT(HOUR FROM t.created_at) / 24.0) AS hour_cos,
        COS(2 * PI() * EXTRACT(DOW FROM t.created_at) / 7.0) AS day_of_week_cos,
        COS(2 * PI() * EXTRACT(MONTH FROM t.created_at) / 12.0) AS month_cos,
        CASE WHEN EXTRACT(DOW FROM t.created_at) IN (0, 6) THEN 1 ELSE 0 END AS weekend,
        t.processing_type AS "TransactionProcessingType",
        t.origin AS "TransactionOrigin",
        t.category AS "TransactionCategory",
        t.is_batch,
        t.num_recipients_batch,
        t.amount_share_in_batch
    FROM transactions t
    JOIN params p ON t.id_fi = p.id_fi
    WHERE t.created_at BETWEEN p.start_date AND p.end_date
      AND t.status NOT IN ('CANCELLED', 'FAILED')
      AND t.category LIKE '%ACH%'
),
user_6m_stats AS (
    SELECT
        t.id_olb_user,
        COUNT(*) AS count_user_all_txn_in_last_6_months,
        STDDEV(t.amount) / NULLIF(AVG(t.amount), 0) AS amount_coef_var_lst6m,
        AVG(CASE WHEN t.amount < 100 THEN 1.0 ELSE 0.0 END) AS pct_txns_under_100_lst6m,
        AVG(CASE WHEN t.amount > 1000 THEN 1.0 ELSE 0.0 END) AS pct_txns_over_1k_lst6m,
        COUNT(DISTINCT DATE(t.created_at)) AS active_days_6m,
        COUNT(*) / NULLIF(COUNT(DISTINCT DATE(t.created_at)), 0)::float AS user_avg_count_txn_per_active_day_last_6_months,
        SUM(t.amount) / NULLIF(COUNT(DISTINCT DATE(t.created_at)), 0) AS user_avg_amount_txn_per_active_day_last_6_months,
        SUM(CASE WHEN t.category LIKE '%ACH%' THEN t.amount ELSE 0 END) / NULLIF(SUM(t.amount), 0) AS ach_amount_share_6m,
        SUM(CASE WHEN t.category LIKE '%ACH%' THEN 1 ELSE 0 END)::float / COUNT(*) AS ach_count_share_6m,
        AVG(t.amount) AS user_avg_ach_amount_day
    FROM transactions t
    JOIN params p ON t.id_fi = p.id_fi
    WHERE t.created_at >= NOW() - INTERVAL '6 months'
      AND t.status NOT IN ('CANCELLED', 'FAILED')
    GROUP BY t.id_olb_user
),
user_cancelled AS (
    SELECT
        id_olb_user,
        SUM(CASE WHEN created_at >= NOW() - INTERVAL '7 days' THEN 1 ELSE 0 END) AS count_user_cancelled_txn_in_last_week,
        SUM(CASE WHEN created_at >= NOW() - INTERVAL '30 days' THEN 1 ELSE 0 END) AS count_user_cancelled_txn_in_last_month
    FROM transactions
    WHERE status = 'CANCELLED'
    GROUP BY id_olb_user
),
cu_stats AS (
    SELECT
        id_fi,
        AVG(amount) AS cu_avg_amount_ach_txn_in_last_6_months,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY amount) AS cu_p95_amount
    FROM transactions
    WHERE created_at >= NOW() - INTERVAL '6 months'
      AND status NOT IN ('CANCELLED', 'FAILED')
      AND category LIKE '%ACH%'
    GROUP BY id_fi
),
recipient_history AS (
    SELECT
        t.id_olb_user,
        COALESCE(t.recipient_account_id::text, t.recipient_key) AS recipient_key,
        COUNT(*) FILTER (WHERE t.created_at >= NOW() - INTERVAL '5 minutes') AS count_txn_to_recipient_account_last_5m,
        SUM(t.amount) FILTER (WHERE t.created_at >= NOW() - INTERVAL '5 minutes') AS total_amount_txn_to_recipient_account_last_5m,
        COUNT(*) FILTER (WHERE t.created_at >= NOW() - INTERVAL '2 months') AS count_txn_to_recipient_account_in_last_2_months,
        COUNT(*) FILTER (WHERE t.created_at >= NOW() - INTERVAL '7 days') AS count_txn_to_recipient_account_in_last_week
    FROM transactions t
    JOIN params p ON t.id_fi = p.id_fi
    GROUP BY t.id_olb_user, recipient_key
),
session_stats AS (
    SELECT
        s.id_olb_user,
        s.session_id,
        COUNT(*) FILTER (WHERE sa.action_type = 'SUSPECTED') AS count_suspected_actions_in_current_session,
        COUNT(*) AS total_actions_session,
        MAX(CASE WHEN sa.action_type = 'AUTH_EMAIL' THEN 1 ELSE 0 END) AS is_auth_email_session,
        MAX(CASE WHEN sa.action_type = 'AUTH_PHONE' THEN 1 ELSE 0 END) AS is_auth_phone_session,
        MAX(CASE WHEN sa.action_type IN ('AUTH_EMAIL', 'AUTH_PHONE', 'AUTH_MFA') THEN 1 ELSE 0 END) AS is_any_auth_session,
        COUNT(*) FILTER (WHERE sa.action_result = 'FAILED') AS count_failed_actions_in_current_session,
        MAX(s.access_channel) AS access
    FROM sessions s
    JOIN session_actions sa ON sa.session_id = s.session_id
    GROUP BY s.id_olb_user, s.session_id
),
user_profile AS (
    SELECT
        u.id AS id_olb_user,
        u.user_type,
        u.age AS user_age,
        EXTRACT(DAY FROM NOW() - u.created_at) AS recency_user_created_days,
        COUNT(a.id) AS total_accounts,
        AVG(CASE WHEN a.account_type = 'CHECKING' THEN 1.0 ELSE 0.0 END) AS checking_ratio,
        AVG(CASE WHEN a.account_type = 'SAVINGS' THEN 1.0 ELSE 0.0 END) AS savings_ratio,
        AVG(CASE WHEN a.account_type IN ('CREDIT', 'LOAN') THEN 1.0 ELSE 0.0 END) AS credit_loan_ratio,
        MAX(d.is_remembered::int) AS is_access_from_remembered_device,
        EXTRACT(DAY FROM NOW() - u.phone_updated_at) AS days_since_phone_update,
        EXTRACT(DAY FROM NOW() - u.email_updated_at) AS days_since_email_update,
        CASE WHEN u.phone_updated_at >= NOW() - INTERVAL '7 days' THEN 1 ELSE 0 END AS is_personal_user_phone_primary_updated_last_week,
        CASE WHEN u.email_updated_at >= NOW() - INTERVAL '7 days' THEN 1 ELSE 0 END AS is_personal_user_email_primary_updated_last_week
    FROM olb_users u
    LEFT JOIN accounts a ON a.id_olb_user = u.id
    LEFT JOIN devices d ON d.id_olb_user = u.id AND d.last_seen_at >= NOW() - INTERVAL '30 days'
    GROUP BY u.id, u.user_type, u.age, u.created_at, u.phone_updated_at, u.email_updated_at
),
last_5m_all AS (
    SELECT
        id_olb_user,
        COUNT(*) AS count_all_txn_last_5m,
        SUM(amount) AS total_amount_all_txn_last_5m
    FROM transactions
    WHERE created_at >= NOW() - INTERVAL '5 minutes'
      AND status NOT IN ('CANCELLED', 'FAILED')
    GROUP BY id_olb_user
)
SELECT
    b."TransactionID",
    b."idOLBUserTxns",
    b."createdAtTxns",
    b."idFi",
    b."recipient_key",
    b.amount,
    b.is_night,
    b.hour_sin,
    b.hour_cos,
    b.day_of_week_cos,
    b.month_cos,
    b.weekend,
    COALESCE(l5.count_all_txn_last_5m, 0) AS count_all_txn_last_5m,
    l5.total_amount_all_txn_last_5m,
    COALESCE(rh.count_txn_to_recipient_account_last_5m, 0) AS count_txn_to_recipient_account_last_5m,
    rh.total_amount_txn_to_recipient_account_last_5m,
    COALESCE(rh.count_txn_to_recipient_account_in_last_2_months, 0) AS count_txn_to_recipient_account_in_last_2_months,
    COALESCE(rh.count_txn_to_recipient_account_in_last_week, 0) AS count_txn_to_recipient_account_in_last_week,
    NULL AS count_all_txn_after_recipient_account_creation,
    CASE WHEN rh.count_txn_to_recipient_account_last_5m = 0 OR rh.count_txn_to_recipient_account_last_5m IS NULL THEN 1 ELSE 0 END AS is_first_txn_from_this_olb_user_to_this_recipient_account_q_6h,
    NULL AS is_first_txn_from_this_account_to_recipient_account_q_72h,
    u6.amount_coef_var_lst6m,
    u6.pct_txns_under_100_lst6m,
    u6.pct_txns_over_1k_lst6m,
    u6.user_avg_count_txn_per_active_day_last_6_months,
    u6.user_avg_amount_txn_per_active_day_last_6_months,
    COALESCE(u6.count_user_all_txn_in_last_6_months, 0) AS count_user_all_txn_in_last_6_months,
    uc.count_user_cancelled_txn_in_last_week,
    uc.count_user_cancelled_txn_in_last_month,
    NULL AS count_user_potential_fraud_txn_in_last_2_months,
    COALESCE(up.recency_user_created_days, 0) AS recency_user_created_days,
    COALESCE(up.is_access_from_remembered_device, 0) AS is_access_from_remembered_device,
    ss.count_suspected_actions_in_current_session,
    ss.total_actions_session,
    ss.is_auth_email_session,
    ss.is_auth_phone_session,
    ss.is_any_auth_session,
    ss.count_failed_actions_in_current_session,
    ss.access,
    up.days_since_phone_update,
    up.days_since_email_update,
    COALESCE(up.is_personal_user_phone_primary_updated_last_week, 0) AS is_personal_user_phone_primary_updated_last_week,
    COALESCE(up.is_personal_user_email_primary_updated_last_week, 0) AS is_personal_user_email_primary_updated_last_week,
    COALESCE(up.total_accounts, 0) AS total_accounts,
    up.checking_ratio,
    up.savings_ratio,
    up.credit_loan_ratio,
    up.user_age,
    up.user_type,
    cu.cu_avg_amount_ach_txn_in_last_6_months,
    CASE WHEN b.amount > cu.cu_p95_amount THEN 1 ELSE 0 END AS is_amount_greater_than_cu_p95_amount_ach_txn_in_last_6_months,
    b.amount / NULLIF(cu.cu_avg_amount_ach_txn_in_last_6_months, 0) AS txn_amount_vs_cu_avg_amount_ach_txn_in_last_6_months,
    b.is_batch,
    b.num_recipients_batch,
    b.amount_share_in_batch,
    b.amount / NULLIF(u6.user_avg_ach_amount_day, 0) AS amt_vs_user_ach_avg_day,
    u6.ach_amount_share_6m,
    u6.ach_count_share_6m,
    b."TransactionProcessingType",
    b."TransactionOrigin",
    b."TransactionCategory"
FROM base_txns b
LEFT JOIN user_6m_stats u6 ON u6.id_olb_user = b."idOLBUserTxns"
LEFT JOIN user_cancelled uc ON uc.id_olb_user = b."idOLBUserTxns"
LEFT JOIN cu_stats cu ON cu.id_fi = b."idFi"
LEFT JOIN recipient_history rh ON rh.id_olb_user = b."idOLBUserTxns" AND rh.recipient_key = b."recipient_key"
LEFT JOIN session_stats ss ON ss.id_olb_user = b."idOLBUserTxns"
LEFT JOIN user_profile up ON up.id_olb_user = b."idOLBUserTxns"
LEFT JOIN last_5m_all l5 ON l5.id_olb_user = b."idOLBUserTxns"
ORDER BY b."createdAtTxns";
```

---

## 5. Output format

Response is `application/json` — an array of objects, one per input row.

| Field | Type | Always present | Description |
|---|---|---|---|
| `TransactionID` | int64 | yes | Echo of input |
| `Cluster` | int | yes | K-Means cluster assigned (0–9) |
| `Distance_to_Centroid` | float | yes | Euclidean distance to cluster centroid |
| `is_outlier` | bool | yes | Distance > cluster threshold |
| `kmeans_risk_score` | int 0–100 | yes | Score from K-Means alone |
| `kmeans_risk_decision` | str | yes | K-Means decision: Accept / User Auth / Admin Review / Reject |
| `risk_score` | int 0–100 | yes | Combined K-Means + rules score |
| `risk_decision` | str | yes | Final decision: Accept / User Auth / Admin Review / Reject |
| `sim_match_txn_id` | int or null | null if Athena fail / no history / D1 skip | TransactionID of best historical match |
| `sim_score` | float 0–1 or null | null if Athena fail | Cosine similarity score |
| `sim_status` | SAFE/RISKY or null | null if Athena fail | Status of the matched historical transaction |
| `sim_decision` | Accept/Reject or null | null if sim_score < 0.90 or Athena fail | Similarity-based recommendation |
| `audit_category` | str | yes | Auditable decision category |
| `audit_explanation` | str | yes | Natural language reason |
| `ux_copy` | str | yes | User-facing message |
| `num__*` (31 fields) | float | yes | Scaled numerical features post-preprocessing |
| `cat__*` (18 fields) | float (0/1) | yes | One-hot categorical features |

Total: ~70 columns.

---

## 6. How to invoke

```python
import boto3
import json
import pandas as pd
from io import StringIO

ENDPOINT_NAME = "SAFE_TXNS_ENDPOINT_DEV"
REGION = "us-east-1"

session = boto3.Session(profile_name="blossom-dev", region_name=REGION)
runtime = session.client("sagemaker-runtime")

# Load input CSV (61 columns, see section 3)
df = pd.read_csv("data/test_escenarios.csv")
csv_body = df.to_csv(index=False)

response = runtime.invoke_endpoint(
    EndpointName=ENDPOINT_NAME,
    ContentType="text/csv",
    Accept="application/json",
    Body=csv_body.encode("utf-8"),
)

results = json.loads(response["Body"].read().decode("utf-8"))
results_df = pd.DataFrame(results)
print(results_df[["TransactionID", "risk_score", "risk_decision", "sim_score", "sim_decision"]])
```

For bulk processing with batching, use `tests/process_endpoint.py`:

```bash
python tests/process_endpoint.py \
  --input data/test_escenarios.csv \
  --output data/test_escenarios_results.csv \
  --batch-size 10 \
  --profile blossom-dev
```

---

## 7. Environment variables

| Variable | Default | Description |
|---|---|---|
| `SIMILARITY_THRESHOLD` | `0.90` | Minimum cosine similarity score to trigger a `sim_decision` |
| `SIMILARITY_ATHENA_DATABASE` | `dlh_silver_safe_alpha` | Athena/Glue database name in the alpha account |
| `SIMILARITY_ATHENA_TABLE` | `safetransactionresults` | Athena table with historical transactions |
| `SIMILARITY_ATHENA_S3_STAGING` | `s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/` | S3 path for Athena query result staging |
| `SIMILARITY_ATHENA_REGION` | `us-east-2` | AWS region of the Athena/data lake resources |
| `ATHENA_WINDOW_MONTHS` | `6` | Lookback window (months) for historical transaction query |
| `ATHENA_TIMEOUT_SECONDS` | `10` | Athena query timeout. Exceeded → `sim_*=null`, K-Means continues |
| `DISABLE_SIMILARITY` | unset | Set to `1` to skip similarity matching entirely |
| `DISABLE_RULES` | unset | Set to `1` to skip statistical rules (score defaults to 0) |

---

## 8. Graceful degradation

K-Means, statistical rules, and similarity are **three independent parallel stages**. None depends on the others succeeding:

- If Athena is unavailable (timeout, permission error, network): `sim_*=null`, K-Means + rules still produce a decision.
- If `idOLBUserTxns` or `createdAtTxns` is absent/null in a row: that row's `sim_*=null` (D1 contract). No 400 error.
- If Athena returns 0 rows (user has no history): `sim_*=null`, logged as `INFO similarity.no_history`.
- If `DISABLE_SIMILARITY=1`: `sim_*=null` for all rows.

**Invariant:** `kmeans_risk_score` and `kmeans_risk_decision` are always populated. Any consumer can make a decision from them alone.

Log patterns:
- Normal with similarity: `[SIMILARITY] Checking similarity for N transactions (threshold: 0.90)`
- Degraded: `[SIMILARITY] similarity.athena_failure` (WARNING, alertable) or `similarity.no_history` (INFO, not alertable)

---

## 9. Deploy

See `docs/guides/DEPLOYMENT_GUIDE.md` for full steps. Deploy **must** be done from a SageMaker Notebook (local CLI deploy fails due to IAM trust policy).

**Tarball S3 path:**
```
s3://blossom-analytics-safe-dev-nv/safe_txns/similarity/endpoint/v2/model.tar.gz
```

**Minimal notebook deploy cell:**
```python
from sagemaker.sklearn.model import SKLearnModel
from sagemaker import get_execution_role, Session

role = get_execution_role()
sk_model = SKLearnModel(
    model_data="s3://blossom-analytics-safe-dev-nv/safe_txns/similarity/endpoint/v2/model.tar.gz",
    role=role,
    entry_point="inference_rules.py",
    framework_version="1.2-1",
    sagemaker_session=Session()
)
predictor = sk_model.deploy(
    initial_instance_count=1,
    instance_type="ml.m5.large",
    endpoint_name="SAFE_TXNS_ENDPOINT_DEV",
)
```
