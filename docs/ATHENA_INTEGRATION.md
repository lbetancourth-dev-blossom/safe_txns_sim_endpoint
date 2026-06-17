# Athena Integration — Similarity Matching (DATA-1264)

## Overview

`similarity_matcher.py` queries historical safe-transaction data from Amazon Athena
to find similar past transactions for each incoming request. This is the **single
source** of truth for similarity matching (D2 decision, closed 2026-06-16).

The Parquet/S3 path was removed as part of D2. There is no `USE_ATHENA` toggle —
Athena is always the source. If Athena is unavailable, similarity degrades gracefully
to `sim_*=null` while K-means + rules continue normally.

---

## Cross-Account Architecture

```
AWS account: development (SageMaker endpoint)
     │
     │  cross-account assume-role
     ▼
AWS account: alpha (data lake)
  s3://blossom-analytics-datalake-alpha/
    datalake/silver/SAFE/safetransactionresults/  ← Glue table data
    datalake/gold/athena-metadata/                ← Athena query results staging
```

The SageMaker execution role in **development** must have a cross-account trust policy
allowing it to assume a role (or be directly granted) in the **alpha** account to:
- Read from `dlh_silver_safe_alpha.safetransactionresults` (Glue/Athena)
- Write Athena query results to `s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/`

**Pre-deploy check (informational, non-blocking for merge after F5 gate 2026-06-17):**
Verify `aws sts get-caller-identity` for the SageMaker role shows access to the alpha
data lake. If not provisioned, escalate to the platform team before deploy. Validation
is done post-deploy by observing `similarity.athena_failure` for 24h (see V6).

---

## Window Decision (R3)

The sliding window is **6 months** (configurable via `ATHENA_WINDOW_MONTHS`). This value
was set by product decision. The window is computed **at each call** using
`_compute_sliding_window()`, not at module load. This is critical because SageMaker
containers stay warm for days — computing at load would freeze the window and gradually
exclude recent data.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SIMILARITY_ATHENA_DATABASE` | `dlh_silver_safe_alpha` | Glue database name (alpha) |
| `SIMILARITY_ATHENA_TABLE` | `safetransactionresults` | Glue table name (alpha) |
| `SIMILARITY_ATHENA_S3_STAGING` | `s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/` | Athena query results staging (cross-account to alpha) |
| `SIMILARITY_ATHENA_REGION` | `us-east-2` | Athena region (alpha; cross-region from dev endpoint in us-east-1) |
| `ATHENA_WINDOW_MONTHS` | `6` | Sliding window size in months |
| `ATHENA_TIMEOUT_SECONDS` | `10` | Query timeout in seconds (D4) |
| `SIMILARITY_THRESHOLD` | `0.90` | Cosine similarity threshold for a match |
| `DISABLE_SIMILARITY` | `0` | Set to `1` to skip similarity matching entirely |
| ~~`USE_ATHENA`~~ | removed | **REMOVED by D2** — Athena is now the only source |
| ~~`SIMILARITY_S3_BUCKET`~~ | removed | **DEPRECATED by D2** — no longer used in similarity |
| ~~`SIMILARITY_S3_KEY`~~ | removed | **DEPRECATED by D2** — no longer used in similarity |

---

## Cross-Account IAM Permissions Required

The SageMaker execution role in the **development** account needs the following permissions
to access the **alpha** data lake:

### Inline policy on the SageMaker role (development account)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AthenaQueryExecution",
      "Effect": "Allow",
      "Action": [
        "athena:StartQueryExecution",
        "athena:GetQueryExecution",
        "athena:GetQueryResults",
        "athena:StopQueryExecution"
      ],
      "Resource": "arn:aws:athena:us-east-2:<ALPHA_ACCOUNT_ID>:workgroup/primary"
    },
    {
      "Sid": "GlueCatalogAccess",
      "Effect": "Allow",
      "Action": [
        "glue:GetDatabase",
        "glue:GetTable",
        "glue:GetPartitions"
      ],
      "Resource": [
        "arn:aws:glue:us-east-2:<ALPHA_ACCOUNT_ID>:catalog",
        "arn:aws:glue:us-east-2:<ALPHA_ACCOUNT_ID>:database/dlh_silver_safe_alpha",
        "arn:aws:glue:us-east-2:<ALPHA_ACCOUNT_ID>:table/dlh_silver_safe_alpha/safetransactionresults"
      ]
    },
    {
      "Sid": "S3StagingReadWrite",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::blossom-analytics-datalake-alpha",
        "arn:aws:s3:::blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/*"
      ]
    },
    {
      "Sid": "S3DataRead",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::blossom-analytics-datalake-alpha",
        "arn:aws:s3:::blossom-analytics-datalake-alpha/datalake/silver/SAFE/safetransactionresults/*"
      ]
    }
  ]
}
```

### Bucket policy on the alpha data lake (alpha account)

The alpha bucket policy must explicitly allow the development SageMaker principal:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowDevSageMakerReadStagingWrite",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::<DEV_ACCOUNT_ID>:role/service-role/<SAGEMAKER_EXECUTION_ROLE>"
      },
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::blossom-analytics-datalake-alpha",
        "arn:aws:s3:::blossom-analytics-datalake-alpha/*"
      ]
    }
  ]
}
```

Replace `<ALPHA_ACCOUNT_ID>`, `<DEV_ACCOUNT_ID>`, and `<SAGEMAKER_EXECUTION_ROLE>` with
the actual values. The platform team is responsible for provisioning this policy
**before merge** (F2 pre-merge gate).

---

## Connection Pattern (F1 — Parameterized Queries)

PyAthena `connect()` is opened **on-demand** inside `load_reference_data_from_athena()`
(D3 decision). No singleton, no connection pool. The connection is closed after
`fetchall()` via `conn.close()`.

**Query pattern — F1 gate (applied 2026-06-17):** NO f-string SQL. PyAthena DB-API
named parameters (`%(name)s` style) are the primary SQL injection control.

### Query format (F1 + F11)

```python
sql = """
    SELECT idolbuser, createdat, statuswarning, metadata, transactionid
    FROM dlh_silver_safe_alpha.safetransactionresults
    WHERE idolbuser = %(user)s
      AND createdat >= %(window_start)s
      AND createdat <= %(window_end)s
      AND statuswarning IN ('SAFE', 'RISKY')
"""
cursor.execute(sql, {
    "user": int(idolbuser),       # int cast as defense-in-depth (F1 parameterized is primary)
    "window_start": start,         # datetime object (UTC)
    "window_end": end,             # datetime object (UTC)
})
```

Key constraints:
- **NO f-string SQL** (F1 gate). The grep test `test_no_fstring_sql_in_module` enforces this.
- **Explicit column list** (F11 gate). NO `SELECT *` — avoids fetching undocumented PII columns.
- **`int(idolbuser)` cast** — defense-in-depth; raises `ValueError`/`TypeError` for non-numeric input.

### Timeout wrapper (D4)

The `cursor.execute()` + `fetchall()` block runs inside a `concurrent.futures.ThreadPoolExecutor`
with a `future.result(timeout=timeout_seconds)` call. On `TimeoutError`:
- Raises `TimeoutError` which is caught by the outer `except Exception as exc` block
- Logs `similarity.athena_failure` with `category="timeout"`
- Returns `(None, None, None, None)` — K-means continues normally

---

## Cache Strategy (A14)

Athena results are cached in `_ATHENA_CACHE` (module-level dict) keyed by:

```
"athena:{idolbuser_int}:{end.strftime('%Y-%m-%d-%H-%M')}"
```

The cache key is truncated to the minute. This means a warm container will re-use
results for the same user within the same minute but will re-query Athena after
the minute boundary — keeping the sliding window approximately current.

To bypass the cache (e.g., in tests), pass `force_reload=True` to
`load_reference_data_from_athena()`.

---

## Graceful Degradation (D1 + D4)

| Failure mode | Behavior |
|---|---|
| `idOLBUserTxns` missing or null | `sim_*=null`, K-means OK (D1) |
| `createdAtTxns` missing or null | `sim_*=null`, K-means OK (D1) |
| Athena connection error | `sim_*=null`, K-means OK, log `similarity.athena_failure category=permission` |
| Athena timeout (>10s) | `sim_*=null`, K-means OK, log `similarity.athena_failure category=timeout` |
| 0 rows returned (no history) | `sim_*=null`, K-means OK, log `similarity.no_history` (INFO — NORMAL, do NOT alert) |
| Throttling | `sim_*=null`, K-means OK, log `similarity.athena_failure category=throttling` |
| SQL / schema error | `sim_*=null`, K-means OK, log `similarity.athena_failure category=query_error` |

The endpoint NEVER returns HTTP 400 due to missing similarity fields (D1 closed).

---

## F5+ Structured Logging and Alerting Playbook

Two distinct log paths are emitted by `load_reference_data_from_athena()`:

### Path A — `similarity.no_history` (INFO)

Emitted when Athena returns **0 rows** for the user+window combination. This is a
**normal outcome** (Scenario 3 — new user with no transaction history in the window).
**Do NOT alert on this event.**

```json
{
  "message": "similarity.no_history",
  "level": "INFO",
  "idolbuser_hash": "<sha256[:16]>",
  "window_months": 6,
  "rows": 0
}
```

### Path B — `similarity.athena_failure` (WARNING)

Emitted when any exception occurs during the Athena query. This event is **alertable**.
The `category` field identifies the root cause:

| category | Root cause | Action |
|---|---|---|
| `permission` | Cross-account IAM denied | Escalate to platform/infra team to fix assume-role policy |
| `throttling` | Athena/AWS rate limit exceeded | Check Athena workgroup concurrency limits |
| `timeout` | Query exceeded `ATHENA_TIMEOUT_SECONDS` | Check query performance or increase timeout |
| `query_error` | SQL syntax or Glue schema drift | Check table schema in Glue catalog |
| `unknown` | Other exception | Inspect `exception_class` and `exception_message` |

```json
{
  "message": "similarity.athena_failure",
  "level": "WARNING",
  "idolbuser_hash": "<sha256[:16]>",
  "exception_class": "PermissionError",
  "exception_message": "<truncated to 200 chars>",
  "category": "permission"
}
```

**`idOLBUser` MUST NEVER appear in plaintext in any log record.** Always use
`idolbuser_hash` (sha256 truncated to 16 hex chars). This is a PII compliance
requirement (F5+ gate, F4 partial closure).

### Suggested CloudWatch Alarm

```
Metric filter: { $.message = "similarity.athena_failure" }
Alarm: count > 5 per minute → notify on-call
Refined filter: { $.message = "similarity.athena_failure" && $.category = "permission" }
  → fires immediately if cross-account IAM is broken
```

### Post-Deploy Alpha Observation (V6 — AC5)

After deploying to the alpha environment:
1. Monitor CloudWatch for **24 hours**
2. Expected: `count(similarity.athena_failure WHERE category=permission)` = 0
3. If count > 0 with `category=permission` → cross-account IAM is broken.
   Rollback or escalate to platform/infra team. This is **not a code fix**.
4. Attach CloudWatch dashboard snapshot as PR comment **before promoting to higher envs**.
5. For merge to `dev` branch this evidence is NOT required — only for promotion.

This replaces the removed `deploy/validate_athena_connection.py` script (F5 gate applied
2026-06-17). The production code (`pyathena.connect()`) validates the connection on the
first invocation post-deploy; structured logs surface any failures immediately.

---

## F2 — Platform Pre-Merge Action

The S3 lifecycle rule deleting Athena staging results after 7 days on
`s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/`
is **owned by the platform team** and must be provisioned **before the PR is merged**.

Include a link to the platform ticket or an AWS Console screenshot showing the rule
active in the PR description.

---

## F3 — Audit Trail (External Owner)

The per-lookup audit trail (which user queried similarity for which transaction, when)
is **not in scope for DATA-1264**. It is owned by the audit/compliance team at Blossom.
Their initiative will cover this endpoint when delivered.

---

## Operational Risk (HLTC-12)

With D2 (Athena single-source), similarity matching has a **single point of failure**.
If Athena is unavailable for an extended period, all similarity results will be null.
K-means + rules still run normally, so the endpoint continues to function.

Suggested follow-up (separate ticket): add a `sim_score_null_rate` metric to CloudWatch
to detect sustained Athena outages and alert the on-call team.

---

## Troubleshooting

| Symptom | `category` in log | Root cause | Fix |
|---|---|---|---|
| All requests have `sim_*=null` | `permission` | Cross-account IAM not provisioned | Escalate to platform team |
| Intermittent `sim_*=null` | `timeout` | Cold Athena partition or slow query | Check Glue partition stats; consider increasing `ATHENA_TIMEOUT_SECONDS` |
| Burst of `sim_*=null` | `throttling` | Athena workgroup concurrency exceeded | Increase workgroup DPU limit or add retry logic in a future ticket |
| `sim_*=null` on first deploy only | `permission` | IAM provisioned after first request | No action needed if subsequent requests succeed |
| `sim_*=null` for specific users | `query_error` | Schema drift or missing column | Check Glue table schema matches the SELECT column list |
| `sim_*=null` for new users | (no failure log) | User has no history in window (0 rows) | Normal — `similarity.no_history` INFO is expected |
| Container cold start latency | `timeout` | Athena cold start + 10s timeout too tight | Increase `ATHENA_TIMEOUT_SECONDS` to 20s for first request |
| Cross-region latency | `timeout` | Endpoint in us-east-1, Athena in us-east-2 | Expected ~50ms overhead; rarely causes timeouts at 10s |
