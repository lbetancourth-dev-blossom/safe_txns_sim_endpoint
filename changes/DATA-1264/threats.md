# Threat Analysis — DATA-1264

**Overall risk level:** Medium (downgraded from High on 2026-06-17 after gate decisions: F1 mitigated by parameterized queries, F2 accepted with pre-merge platform action, F3 accepted with external owner, F5 redesigned without separate script, F5+ added structured logging)
**Date:** 2026-06-16 (initial analysis) · 2026-06-17 (gate decisions applied)
**Reviewer:** blossom-security (automated) · gate decisions: Luis Betancourth

---

## Summary

This change introduces a live Athena query path into a production SageMaker inference endpoint, using a credit union member identifier (`idOLBUserTxns`) sourced directly from the request payload to filter transaction history from a cross-account data lake.

**Initial analysis (2026-06-16):** overall risk was assessed as **High**, driven by three converging factors: (1) the query was built with f-string interpolation against a member-supplied integer value with only a runtime `int()` cast as the injection guard; (2) Athena result residue lands in a shared S3 staging prefix with no documented lifecycle policy; (3) member-data lookups through the new code path had no BSA/AML-grade audit trail. None of those gaps were individually Critical, but the combination of an unparameterized query against PII-keyed data with missing audit logging and uncontrolled result residue on shared S3 placed the overall risk at High.

**After gate decisions (2026-06-17):** overall risk drops to **Medium**:
- F1 is now **structurally mitigated** by adopting PyAthena parameterized queries (`cursor.execute(sql, {"user": ..., "window_start": ...})`). The f-string SQL pattern is forbidden by a grep-based unit test.
- F2 is **accepted with a pre-merge platform action** — the 7-day S3 lifecycle rule on `gold/athena-metadata/` is owned by the platform team and stamped as a PR DoD checkbox.
- F3 is **accepted with an external owner** — the per-lookup audit trail is owned by the audit/compliance team initiative at Blossom and is explicitly out of scope for DATA-1264.
- F5 (validation script PII leakage + bundling) is **mitigated by redesign** — the script is removed entirely. Validation moves to production code's `pyathena.connect()` call + 24h post-deploy alpha observation.
- F5+ (observability gap left by F5) is **mitigated** by mandatory structured logging that distinguishes `similarity.no_history` (INFO, normal Scenario 3) from `similarity.athena_failure` (WARNING, alertable, with classified `category`). `idOLBUser` is sha256-truncated in every new log path, never plaintext — this also closes the new-paths half of F4.

The cross-account IAM architecture remains a top-level risk, but it is now **observable post-deploy** via the `similarity.athena_failure` log with `category="permission"`. The graceful degradation design (D1/D4/R5) is sound; K-means + rules are independent of Athena. The residual gaps (F4 plaintext idolbuser in pre-existing timeout logs, F6 IAM policy template, F7 cache eviction, F8 workgroup cost cap, F11 SELECT *) are tracked under Mandatory Controls — F11 must be closed in the spec (explicit column list); F4/F6/F7/F8 are implementer attention items, NOT merge blockers.

---

## Findings

### F1 — f-string SQL interpolation without parameterized queries [High]

**Category:** PII / SQL Injection
**Risk:** The Athena query is constructed using Python f-string interpolation (`WHERE idolbuser = {idolbuser_int}`). The only injection defense is a prior `int(idolbuser)` cast. If that cast is bypassed, skipped during refactoring, or the field type widens in a future schema change, the entire SQL statement is injectable. Parameterized queries were explicitly available in PyAthena but ruled out in A10 because the notebook used f-strings. This is a defense-in-depth gap: a single line of guard code, not a structural control.

**Evidence:** `plan.md` A10: "PyAthena soporta parameterized pero el patrón validado usa f-string. idolbuser es int (DTYPE_MAP L87), no SQL injection risk." `spec.md` section "Athena query (closed)": `WHERE idolbuser = {idolbuser_int}`. HLTC-9: "f-string SQL con idolbuser interpolado. DTYPE_MAP L87 marca idOLBUserTxns int64. Defensa: int(idolbuser) hard cast."

**Mitigation:** Adopt PyAthena parameterized query syntax for the `idolbuser` bind parameter. PyAthena supports `%(name)s`-style params via `cursor.execute(sql, params)`. This eliminates the injection surface structurally rather than relying on a single cast. If the notebook-validated f-string pattern must be preserved for any operational reason, the spec must explicitly document it as a known accepted risk with the cast as the sole control, and the implementer must add a test that confirms `load_reference_data_from_athena(idolbuser="1; DROP TABLE x")` raises before any SQL is sent. The test `test_load_from_athena_casts_idolbuser_to_int_defense_in_depth` in spec.md covers this — confirm it is not skipped.

**Status:** Mitigated — Dev gate decision applied 2026-06-17: adopt PyAthena parameterized queries via `cursor.execute(sql, {"user": int(idolbuser), "window_start": window_start_ts})`. The `int()` cast remains as defense-in-depth, but structural protection now comes from PyAthena's parameter escaping. Spec task T_SIMILARITY updated to use this pattern. Test contract added that greps the source for f-string SQL — if found, fails.

---

### F2 — Athena result residue on shared S3 staging prefix — no lifecycle policy [High]

**Category:** PII / Persistence
**Risk:** Every Athena query triggered by an inference request writes its result set to `s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/`. This is a shared prefix used by all Athena workloads in the alpha account. Each result file contains rows from `safetransactionresults` filtered by a specific `idolbuser` — i.e., per-member transaction history. Result files are not deleted after being consumed by PyAthena. Without a lifecycle policy, these files accumulate indefinitely. Any IAM principal with `s3:GetObject` or `s3:ListBucket` on this prefix can read all historical query results, including the per-member data, without going through the endpoint or Athena access controls.

**Evidence:** `spec.md` section "Athena query (closed)": `s3_staging_dir='s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/'`. `plan.md` D5 and HLTC-8 both confirm this staging path. No lifecycle policy is mentioned anywhere in plan.md, spec.md, or refinement.md.

**Mitigation:** Two controls are required:
1. Add an S3 lifecycle rule on the `datalake/gold/athena-metadata/` prefix to delete objects after no more than 7 days (shorter is better — 24h is sufficient for Athena to consume results). This must be configured in the alpha account bucket policy, not in application code.
2. Document the lifecycle requirement in `docs/ATHENA_INTEGRATION.md` under the Cross-account IAM section. This is a platform/infra action, not a code action, but it must be a hard prerequisite before merge — the same way cross-account IAM is a hard prerequisite in the pre-execute checklist.

**Status:** Accepted with pre-merge action — Dev gate decision applied 2026-06-17: platform team owns the 7-day delete lifecycle rule on `s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/`. This is infra config, no application code change. Added to plan.md as a top-level pre-merge action and stamped as a checkbox in the PR DoD. Without this rule, Athena query results accumulate indefinitely as PII residue. Owner: platform team. Gate: pre-merge.

---

### F3 — No durable audit log for per-member transaction history lookups [High]

**Category:** Audit / BSA-AML
**Risk:** Every call to `load_reference_data_from_athena(idolbuser=X)` constitutes a lookup of a credit union member's transaction history. The plan specifies CloudWatch warnings only for timeout events (`[SIMILARITY][ATHENA][TIMEOUT] idolbuser={X}`). There is no `logger.audit(...)` or equivalent durable, immutable record of: which member's data was queried, when, by which IAM role, and how many rows were returned. For BSA/AML compliance, member financial data access events should be auditable — regulators and internal compliance may need to reconstruct who read what and when. The CloudWatch log stream is a warning stream, not an audit stream, and is not immutable.

**Evidence:** `plan.md` D4: "CloudWatch warning format: [SIMILARITY][ATHENA][TIMEOUT] idolbuser={X} window={start}->{end} elapsed_ms={N}" — this only logs on timeout, not on every successful query. `plan.md` A12: "Mantener prefijo [SIMILARITY] en logs nuevos y añadir [ATHENA] para llamadas Athena específicas — print() + logger.info()." Neither plan.md nor spec.md mentions an audit log for successful lookups.

**Mitigation:** Add a structured audit log entry for every Athena query that executes (success or failure), containing at minimum: `idolbuser`, `window_start`, `window_end`, `row_count_returned`, `query_elapsed_ms`, `iam_caller_arn` (from STS or from the ambient role), `timestamp_utc`. This entry must go to a durable, append-only sink (a dedicated CloudWatch log group with retention policy and no delete permissions for the endpoint role, or a separate audit table). It must be emitted before the result is used in inference, not just on timeout. Add this to `docs/ATHENA_INTEGRATION.md` and to the mandatory controls in this document.

**Status:** Accepted with external owner — Dev gate decision applied 2026-06-17 ("Esto lo maneja otro equipo"): the broader member-data lookup audit trail initiative is owned by the audit/compliance team at Blossom (team owner: TBD — confirm in PR description). Their initiative will cover this endpoint when delivered. For DATA-1264, no audit logging is added — accepted risk for the alpha-only deployment window. No follow-up ticket is created in this scope.

---

### F4 — `idOLBUserTxns` logged in plaintext on timeout events (PII in logs) [Medium]

**Category:** PII
**Risk:** The D4 timeout log format explicitly includes `idolbuser={X}` in the warning message: `[SIMILARITY][ATHENA][TIMEOUT] idolbuser={X} window={start}->{end} elapsed_ms={N}`. If CloudWatch log groups for this endpoint are accessible to a broad set of IAM principals (e.g., all engineers), this constitutes logging of member identifiers in plaintext on every timeout event. `idOLBUserTxns` is a credit union member ID — it is PII under NCUA member data protection expectations, even if it is not a name or SSN. The plan explicitly adopts this format, so the implementer will emit it.

**Evidence:** `plan.md` D4 closed_decision: "CloudWatch warning format: [SIMILARITY][ATHENA][TIMEOUT] idolbuser={X} window={start}->{end} elapsed_ms={N}."

**Mitigation:** Replace the raw `idolbuser` value in the timeout warning with a hash or truncated opaque token sufficient to correlate log events without exposing the raw member ID. E.g., `idolbuser_hash=sha256(str(idolbuser))[:12]`. Alternatively, restrict CloudWatch log group access to the minimum required principals via resource policy. The mitigation approach must be documented in `docs/ATHENA_INTEGRATION.md`. Note: if F3 is remediated with a separate audit log that records the raw `idolbuser`, the warning log should use the hash; the audit log (access-controlled separately) can hold the raw value.

**Status:** Mitigated for new log paths by F5+ (gate applied 2026-06-17) — the structured logs `similarity.no_history` and `similarity.athena_failure` use `idolbuser_hash` (sha256-truncated to 16 hex chars), NEVER plaintext. The previous D4 timeout log format `[SIMILARITY][ATHENA][TIMEOUT] idolbuser={X}` is REPLACED — timeout events now go through `similarity.athena_failure` with `category="timeout"` and `idolbuser_hash`. Any other pre-existing plaintext idolbuser log in the module (if any) is an implementer attention item but is not a merge blocker because the D4 timeout path is the only one that referenced idolbuser in plaintext per the original plan.

---

### F5 — `validate_athena_connection.py` logs real member data (`sample_rows`) and will be bundled in the production container [Medium]

**Category:** PII / Operational
**Risk:** The validation script (spec.md T_AC5) logs `sample_rows` — up to 3 rows from `safetransactionresults` for `sample_idolbuser=604150` — to stdout and includes them in the JSON report on stderr. If this output is attached to a PR (as required by V6/V8), it exposes real transaction rows for a real member (or a synthetic one that looks real) in the Git/Jira artifact trail. Additionally, the script is designed to live at `deploy/validate_athena_connection.py` and is included in the `source_dir='endpoint'` tarball deployed to SageMaker. A principal with the ability to invoke the endpoint or exec into the container could trigger this script against any valid `idolbuser` value passed as `sys.argv[1]`.

**Evidence:** `spec.md` T_AC5 implementation: `sample_rows = df.head(3).to_dict(orient="records")` included in `report["checks"]` written to stderr; `emit(f"     Sample row (3 cols): {sample_rows[0]}")` to stdout. `spec.md` file manifest: `deploy/validate_athena_connection.py` is in the repo alongside `deploy/deploy_with_sdk.py`. `spec.md` V8: "ambos outputs de V6 (Run #1 + Run #2) adjuntos al PR."

**Mitigation:** Two required actions:
1. **Scrub PR evidence:** The PR attachment must use a synthetic `idolbuser` that has no real member data, or the `sample_rows` output must be redacted before attaching. Add this requirement to the V6 verification step.
2. **Script bundling:** The validation script must NOT be bundled in the production container image. Move it outside `source_dir='endpoint/'` (e.g., a `scripts/` directory not included in the SKLearnModel tarball), or add a container entrypoint check that refuses to execute it unless a specific `VALIDATION_MODE` env var is set and the IAM caller is the platform team role. Document the chosen approach in `docs/ATHENA_INTEGRATION.md`.

**Status:** Mitigated by redesign — Dev gate decision applied 2026-06-17: the separate `deploy/validate_athena_connection.py` script is REMOVED entirely. Dev's words: "La validación de conexión se hace dentro del script con el connect() de pyathena, no es necesario un script aparte." Validation now happens via:
1. The production code's `pyathena.connect()` call inside `find_similar_transaction()` / the new Athena loader. If cross-account permissions are wrong, this fails on the first inference call after deploy.
2. Deploy to alpha first. CloudWatch observation for 24h confirms Athena queries succeed.
3. If queries fail consistently → rollback (trivial because K-means + rules still work).

AC5 satisfaction is now post-deploy-in-alpha, NOT pre-merge. The script bundling risk and PR PII leakage are both eliminated because no script exists. The visibility gap this leaves is closed by F5+ (structured logging) below.

---

### F5+ — Structured logging to distinguish Athena exception from 0 rows [High → Mitigated]

**Category:** Observability / Operational
**Risk (now mitigated):** Without F5's validation script, the only signal that cross-account IAM is broken comes from production inference calls failing. Without structured differentiation, an empty Athena result (a normal Scenario 3 outcome) looks identical in logs to an Athena exception (broken IAM, throttling, timeout). This blinds the operational monitoring story: the team cannot alert on "Athena is broken" without false positives from "user has no history in window."

**Mitigation (closed):** Two distinct log paths emitted from the Athena loader:

a. **Athena returned 0 rows** — INFO level, NOT alertable:
```python
logger.info("similarity.no_history", extra={
    "idolbuser_hash": sha256(str(idolbuser).encode()).hexdigest()[:16],
    "window_months": 6,
    "rows": 0,
})
```

b. **Athena raised an exception** — WARNING (or ERROR for non-throttling), alertable:
```python
logger.warning("similarity.athena_failure", extra={
    "idolbuser_hash": sha256(str(idolbuser).encode()).hexdigest()[:16],
    "exception_class": exc.__class__.__name__,
    "exception_message": str(exc)[:200],  # truncated to avoid log injection
    "category": classify_exception(exc),   # "permission" | "throttling" | "timeout" | "query_error" | "unknown"
})
```

CloudWatch alarm fires if `similarity.athena_failure` count > N per minute with `category=permission` → indicates cross-account broken or AWS-level issue. The `idolbuser` MUST be sha256-truncated, never plaintext (closes F4 too for these log paths).

The `classify_exception()` helper is a 4-5 line function written as part of T_LOGGING in the spec.

**Evidence:** Spec task T_LOGGING (new) implements both paths plus the helper. Test contracts verify: (a) Athena raises `PermissionError` → `similarity.athena_failure` log with `category="permission"`; (b) Athena returns empty → `similarity.no_history` log at INFO level.

**Status:** Mitigated — Dev gate decision applied 2026-06-17: structured logging is mandatory in T_LOGGING. Replaces what F5's validation script would have given as a pre-merge signal with a post-deploy observability signal.

---

### F6 — Cross-account IAM policy scope not enforced in spec — over-broad S3 grant possible [Medium]

**Category:** IAM / Trust Boundary
**Risk:** The plan (HLTC-8, D5) correctly lists the required IAM permissions at the prefix level. However, the spec does not include a concrete IAM policy document that the implementer or platform team must apply. Without a policy template, the path of least resistance for a platform engineer provisioning the cross-account access is to grant `s3:*` on the entire `blossom-analytics-datalake-alpha` bucket or `athena:*` in the alpha account. Either grants far more than the minimum: the endpoint would be able to read Gold layer data, other Silver tables, or overwrite data lake objects outside the SAFE prefix.

**Evidence:** `plan.md` HLTC-8 preview lists exact permissions required but notes "ADICIONALMENTE — el bucket policy de blossom-analytics-datalake-alpha debe permitir explícitamente al principal del rol SageMaker en cuenta development." No policy JSON template is in plan.md or spec.md. `plan.md` A16 and spec.md T6 require `docs/ATHENA_INTEGRATION.md` to include "Cross-account IAM policy (dev→alpha)" — but the implementer writes the doc, not the platform team applying the policy.

**Mitigation:** The spec's T6 doc requirement must be strengthened: `docs/ATHENA_INTEGRATION.md` must include a verbatim, copy-pasteable IAM policy JSON for both (a) the role policy on the development account SageMaker role and (b) the resource-based bucket policy on `blossom-analytics-datalake-alpha`. Both must be scoped to the exact prefixes in HLTC-8: `datalake/silver/SAFE/safetransactionresults/data/*` (read-only) and `datalake/gold/athena-metadata/*` (read/write). The policy must explicitly deny `s3:DeleteObject` on the Silver prefix.

**Status:** Open — policy template is required but not yet in scope.

---

### F7 — In-memory cache (`_ATHENA_CACHE`) keyed on raw `idolbuser` — cache poisoning and cross-request PII leakage [Medium]

**Category:** PII / Concurrency
**Risk:** The cache key is `f"athena:{idolbuser_int}:{end.strftime('%Y-%m-%d-%H-%M')}"` (A14, spec.md T2). The cache is a module-level dict (`_ATHENA_CACHE`) that persists across requests within the same container process. Two risks: (1) The cache stores a DataFrame containing transaction rows for a specific member. If the cache key is predictable or collides, a request for member A could return member B's data. A minute-truncated timestamp means all requests for the same user within the same minute share a cache entry — this is intentional, but a bug in key construction (e.g., missing `idolbuser_int` component) would cause cross-member data leakage. (2) The cache grows unboundedly — no eviction policy, TTL, or size cap is specified. Under sustained load with many unique `idolbuser` values, the container's memory will grow without bound.

**Evidence:** `plan.md` A14: "Cache key incluye (idolbuser, ventana_start_truncada_a_minuto)." `spec.md` T2 step 3: `f"athena:{idolbuser_int}:{end.strftime('%Y-%m-%d-%H-%M')}"`. No eviction or size cap mentioned in plan.md or spec.md.

**Mitigation:** (1) Add a test that asserts cache keys for different `idolbuser` values are always distinct — covering the key construction logic directly. (2) Add a maximum cache size (e.g., 100 entries via `functools.lru_cache` or a simple `if len(_ATHENA_CACHE) > MAX_SIZE: _ATHENA_CACHE.clear()` guard). (3) Document that the cache holds member-scoped transaction data and must never be persisted to disk (already implied by D3 on-demand connection, but make it explicit in the doc).

**Status:** Open — no eviction policy or size cap; cross-member isolation not tested.

---

### F8 — Athena cost amplification — no rate limit or workgroup query cost cap documented [Medium]

**Category:** DoS / Cost
**Risk:** Every unique `(idolbuser, minute)` tuple triggers a separate Athena query. The plan notes the alpha workgroup default concurrency is 5 queries/second (HLTC-10) but does not document whether a workgroup data scan limit (`BytesScannedCutoffPerQuery`) is configured. A caller sending a flood of requests with distinct `idolbuser` values — or a buggy upstream batch process — can generate O(N) Athena queries, each scanning the full Silver SAFE partition range. At Athena pricing ($5/TB scanned), this is a direct cost amplification vector. The endpoint has no documented per-IP or per-user rate limit.

**Evidence:** `plan.md` HLTC-10: "Riesgo elevado: requests con idolbusers distintos generan N queries Athena en paralelo → throttling alpha workgroup (DEFAULT_QUERY_CONCURRENCY=5)." No rate limit on the endpoint is mentioned in plan.md or spec.md. No Athena workgroup `BytesScannedCutoffPerQuery` is mentioned.

**Mitigation:** (1) Configure `BytesScannedCutoffPerQuery` on the alpha Athena workgroup (e.g., 1 GB per query — sufficient for a single user's 6-month window, which should be well under that). This is a platform action; add it to the pre-execute checklist. (2) Document the endpoint-level rate limiting story in `docs/ATHENA_INTEGRATION.md` — even if rate limiting lives upstream (API Gateway or SageMaker endpoint invocation limits), this must be referenced explicitly. (3) Note the `BytesScannedCutoffPerQuery` as a mandatory platform prerequisite in `docs/ATHENA_INTEGRATION.md`.

**Status:** Open.

---

### F9 — Cross-region Athena (us-east-2) from endpoint (us-east-1) — no egress cost control or latency SLO documented [Low]

**Category:** Operational / Cost
**Risk:** The endpoint runs in us-east-1; Athena runs in us-east-2. Cross-region data transfer incurs AWS egress charges on query result transfer from the alpha staging bucket (us-east-2) to the endpoint process (us-east-1). Under sustained load this cost is non-trivial. The plan acknowledges this (K3) but marks it as medium probability / medium severity without a concrete mitigation beyond "document it."

**Evidence:** `plan.md` K3: "Cross-region (Athena alpha en us-east-2 vs endpoint dev en us-east-1) añade latencia y egress." `plan.md` HLTC-8 preview: "Region: us-east-2 (Athena alpha) — el endpoint SageMaker está en us-east-1 según deploy_with_sdk.py. Cross-region adds latency + egress charges."

**Mitigation:** Document in `docs/ATHENA_INTEGRATION.md` the expected per-query egress cost (bytes per result set * $0.09/GB cross-region). Add a note to monitor via AWS Cost Explorer filtered to the staging bucket. Accepted risk at this stage given the cache (A14) reduces query frequency.

**Status:** Accepted risk — documented in plan; no code change required.

---

### F10 — No secrets introduced; env vars are configuration, not credentials [Low]

**Category:** Secrets
**Risk:** The new env vars (`SIMILARITY_ATHENA_DATABASE`, `SIMILARITY_ATHENA_TABLE`, `SIMILARITY_ATHENA_S3_STAGING`, `SIMILARITY_ATHENA_REGION`, `ATHENA_WINDOW_MONTHS`, `ATHENA_TIMEOUT_SECONDS`) are non-sensitive configuration values — database/table names and S3 paths. They are not credentials. The IAM access is mediated by the SageMaker execution role (ambient AWS credential chain), not by any long-lived key. PyAthena uses boto3 which uses the instance metadata service for credentials. No new secrets are introduced.

**Evidence:** `spec.md` env vars table: all values are strings (DB name, table name, S3 path, region, integers). No API keys, JWT signing keys, or DB passwords.

**Mitigation:** None required. Confirm in the implementation that PyAthena's `connect()` call does not accept an explicit `aws_access_key_id` / `aws_secret_access_key` argument — it must rely solely on the ambient boto3 credential chain (instance role). If any future version of the implementation adds explicit key parameters, flag immediately.

**Status:** Mitigated by design.

---

### F11 — `SELECT *` in production Athena query exposes all columns including potentially undocumented ones [Low]

**Category:** PII / Data minimization
**Risk:** The production Athena query uses `SELECT *` against `dlh_silver_safe_alpha.safetransactionresults`. The plan documents expected columns (`idolbuser`, `createdat`, `statuswarning`, `metadata`, `transactionid`) but does not enumerate all columns in the table. If the Silver table contains additional PII columns (member name, account number, raw transaction amounts not needed for similarity scoring), those are fetched, held in memory, and cached in the container — even if the inference code never reads them.

**Evidence:** `spec.md` "Athena query (closed)": `SELECT * FROM dlh_silver_safe_alpha.safetransactionresults WHERE ...`. `plan.md` A11 lists only 5 known columns. The actual Silver schema is not audited in the plan or spec.

**Mitigation:** Replace `SELECT *` with an explicit column list containing only the columns required by `_normalize_athena_columns()` and `_extract_vectors_from_df()`: at minimum `transactionid, idolbuser, createdat, statuswarning, metadata`. This eliminates the risk of accidentally caching undocumented PII columns. The validation script in T_AC5 already does this (`SELECT transactionid, idolbuser, createdat, statuswarning`) — apply the same discipline to the production query.

**Status:** Mitigated (closed in spec on 2026-06-17 alongside F1 gate) — Spec task T_SIMILARITY now uses an explicit column list: `SELECT idolbuser, createdat, statuswarning, metadata, transactionid FROM ...`. Test `test_load_from_athena_uses_explicit_column_list_F11` asserts no `SELECT *` and that all 5 expected columns are present. This eliminates the risk of accidentally fetching/caching undocumented PII columns.

---

### F12 — Downgrade attack via intentional Athena throttling — acknowledged, accepted [Low]

**Category:** Availability
**Risk:** A malicious caller can send concurrent requests with unique `idolbuser` values to exhaust the alpha Athena workgroup concurrency (5 queries/second default). Subsequent requests hit the timeout (D4, 10s) and degrade to `sim_*=null`. K-means still runs (R5), so the endpoint continues to function. This is a partial degradation of similarity scoring, not a denial of service to the endpoint itself. The plan acknowledges this (HLTC-10, K8).

**Evidence:** `plan.md` HLTC-10 and K8: throttling under concurrent load → D4 timeout + sim_*=null graceful.

**Mitigation:** Accepted. The K-means path is independent (R5) and the endpoint remains functional. Document the accepted risk explicitly in `docs/ATHENA_INTEGRATION.md`. Note in the operational runbook that a sustained spike in `sim_score_null_rate` may indicate either an Athena outage (K9) or an intentional throttle attack.

**Status:** Accepted.

---

## Top-level risks — final disposition (2026-06-17)

All high-severity findings that required human approval before `/execute` have been closed. Final state:

1. **F1 (was High) → MITIGATED 2026-06-17.** PyAthena parameterized queries adopted. `cursor.execute(sql, {"user": int(idolbuser), ...})`. Grep test `test_no_fstring_sql_in_module` enforces structural absence of f-string SQL.

2. **F2 (was High) → ACCEPTED with pre-merge platform action 2026-06-17.** Platform team owns the 7-day S3 lifecycle rule on `datalake/gold/athena-metadata/`. Tracked as PR DoD checkbox; PR description must link the platform team confirmation/ticket.

3. **F3 (was High) → ACCEPTED with external owner 2026-06-17.** Audit/compliance team initiative covers this endpoint when delivered. NOT scope of DATA-1264. No follow-up ticket created. Dev's exact words: "Esto lo maneja otro equipo."

4. **F5 (was Medium) → MITIGATED BY REDESIGN 2026-06-17.** Script removed. Validation via production `pyathena.connect()` + 24h post-deploy alpha observation of `similarity.athena_failure` count.

5. **F5+ (was High → mitigated same-day) → MITIGATED 2026-06-17.** Structured logging task T_LOGGING in spec implements `similarity.no_history` (INFO) and `similarity.athena_failure` (WARNING) with `classify_exception()` categories and sha256-truncated `idolbuser_hash`.

6. **F11 (was Low but easily fixed) → MITIGATED IN SPEC 2026-06-17.** T_SIMILARITY uses explicit column list (`idolbuser, createdat, statuswarning, metadata, transactionid`). Test `test_load_from_athena_uses_explicit_column_list_F11` enforces.

Remaining open items (NOT merge blockers, implementer attention):
- F4 (raw `idolbuser` in pre-existing logs): closed for new paths by F5+; implementer should audit pre-existing `[SIMILARITY]` log lines for stray plaintext `idolbuser` references during T_SIMILARITY.
- F6 (IAM policy template in `docs/ATHENA_INTEGRATION.md`): docs task T6 already requires the verbatim policy JSON.
- F7 (cache eviction): `_ATHENA_CACHE` should have a max size cap. Implementer to add as part of T_SIMILARITY (`if len(_ATHENA_CACHE) > 256: _ATHENA_CACHE.clear()` or similar).
- F8 (Athena workgroup cost cap, `BytesScannedCutoffPerQuery`): platform attention item, documented in `docs/ATHENA_INTEGRATION.md` per T6.

---

## Mitigations already in the plan/spec

The following security controls are correctly designed and should be preserved as-is:

- **HLTC-9 / `int()` cast defense:** `int(idolbuser)` before any SQL formatting is a correct defense-in-depth control. The test `test_load_from_athena_casts_idolbuser_to_int_defense_in_depth` must be retained and green.
- **D1 graceful degradation:** `_validate_similarity_input()` never raises; missing/invalid `idolbuser` sets `sim_*=null` without a 400. This prevents the similarity gate from becoming an availability vector.
- **D3 on-demand connection:** PyAthena connection opened and closed per-request via `try/finally`. Eliminates shared state, token leakage across requests, and accidental serialization of the connection object.
- **D4 timeout (10s):** Hard timeout on Athena queries prevents request-level blocking. Per the F5+ gate (2026-06-17), the previous `[ATHENA][TIMEOUT] idolbuser={X}` plaintext log format is REPLACED — timeout events now flow through `similarity.athena_failure` with `category="timeout"` and `idolbuser_hash` (sha256[:16]). F4 closed for this path.
- **R5 parallel independence:** K-means output is computed before the similarity block; Athena failure cannot corrupt K-means results.
- **Cross-account IAM blocker (K_CROSS_ACCOUNT / D5):** Per F5 gate (2026-06-17), validation moved from a pre-merge `sts.get_caller_identity()` script to a post-deploy 24h CloudWatch observation of `similarity.athena_failure` count with `category="permission"`. The gating is no longer pre-merge but pre-promotion (alpha → higher envs).
- **Window computed at call time (A9/R1):** `_compute_sliding_window()` called inside the loader, not at module load. Prevents stale window in hot containers.
- **Cache key isolation (A14):** Cache key includes `idolbuser_int`, preventing cross-member cache hits when implemented correctly. (Eviction gap flagged as F7.)
- **No secrets introduced (F10):** IAM mediated entirely by the ambient SageMaker execution role. No long-lived credentials in code or config.

---

## Mandatory controls for this change (updated 2026-06-17 after gate decisions)

The following controls are non-negotiable before merge:

- [ ] **F1 mitigation** — `load_reference_data_from_athena()` uses PyAthena parameterized queries (`cursor.execute(sql, {"user": int(idolbuser), "window_start": ..., "window_end": ...})`). NO f-string SQL. Test `test_no_fstring_sql_in_module` is green; test `test_load_from_athena_uses_parameterized_query_F1` is green.
- [ ] **F1 defense-in-depth** — `load_reference_data_from_athena()` calls `int(idolbuser)` before any SQL call; if the cast fails, the function returns `(None, None, None, None)`. Test `test_load_from_athena_casts_idolbuser_to_int_defense_in_depth` is present, green, and not marked `xfail`/`skip`.
- [ ] **F11 mitigation** — Production Athena query uses explicit column list (`idolbuser, createdat, statuswarning, metadata, transactionid`), NOT `SELECT *`. Test `test_load_from_athena_uses_explicit_column_list_F11` is green.
- [ ] **F2 mitigation (platform pre-merge action)** — S3 lifecycle rule on `datalake/gold/athena-metadata/` prefix (delete after <= 7 days) is confirmed provisioned in the alpha account before merge. PR description links the platform team ticket/confirmation. PR DoD checkbox in `spec.md` is checked.
- [ ] ~~`validate_athena_connection.py` bundling guard~~ — **N/A — script removed by F5 gate (2026-06-17).** No script to bundle.
- [ ] ~~PR attachments for V6 with scrubbed `idolbuser`~~ — **N/A — no V6 PR attachment per F5 gate.** Validation is post-deploy via CloudWatch.
- [ ] **F6 mitigation** — `docs/ATHENA_INTEGRATION.md` includes a concrete, copy-pasteable IAM policy JSON for both the development account role policy and the alpha bucket resource policy, scoped to exact prefixes (HLTC-8).
- [ ] **F8 platform attention item** — `docs/ATHENA_INTEGRATION.md` documents the Athena workgroup `BytesScannedCutoffPerQuery` limit as a recommended platform prerequisite (NOT a hard merge blocker — see Top-level risks).
- [ ] **F3 disposition documented** — PR description and `docs/ATHENA_INTEGRATION.md` explicitly state that per-lookup audit logging is owned by the audit/compliance team initiative and is NOT scope of DATA-1264 (no follow-up ticket created in this scope).
- [ ] **F5+ mitigation** — Structured logging `similarity.no_history` (INFO) and `similarity.athena_failure` (WARNING) emitted from `load_reference_data_from_athena()` with `idolbuser_hash` (sha256[:16]), NEVER plaintext `idolbuser`. `classify_exception()` helper present with 5 categories (permission/throttling/timeout/query_error/unknown). All F5+ tests in `test/test_athena_similarity_logging.py` green.
- [ ] **F4 mitigation (for new log paths)** — No new log line in `endpoint/similarity_matcher.py` contains plaintext `idolbuser`. Verified by the F5+ logging tests. Pre-existing log lines (if any) audited by the implementer during T_SIMILARITY.
- [ ] **F7 attention item** — `_ATHENA_CACHE` has a maximum entry count (recommended: 256 entries). Implementer to add a `if len(_ATHENA_CACHE) > 256: _ATHENA_CACHE.clear()` guard or use `functools.lru_cache`. A test confirms cache keys for two distinct `idolbuser` values are never equal regardless of timestamp alignment.

---

## Compliance considerations

### NCUA

Member financial data (transaction history filtered by `idOLBUserTxns`) is accessed through a new code path not previously audited. NCUA Examination expectations for member data access require that the credit union can reconstruct who accessed member data, when, and under what authorization.

Per the 2026-06-17 gate decision (F3 accepted with external owner), the durable per-lookup audit record is owned by the **audit/compliance team initiative** at Blossom and is explicitly out of scope for DATA-1264. The alpha-only deployment window is the accepted-risk container for this gap. Before this feature is promoted beyond alpha, the audit team initiative must cover this endpoint OR a follow-up ticket must be opened by the audit team owner. The data flow must still be documented — `docs/ATHENA_INTEGRATION.md` describes the full read path from request payload through Athena to inference output, including which IAM role accesses which data (per T6).

The new structured logs (`similarity.no_history`, `similarity.athena_failure`) are NOT a substitute for the audit trail — they use `idolbuser_hash` (NOT plaintext) and are operational logs, not append-only audit records. They are useful for ops but cannot answer "who accessed member X's data when" questions in raw form.

### BSA/AML

The similarity stage reads transaction history to inform risk scoring. Any new code path that touches transaction monitoring logic must be auditable. The current state (post-gate 2026-06-17):

- F3 (per-lookup audit log) is owned externally by the audit/compliance team — gap exists for the DATA-1264 alpha-only window.
- F2 (Athena result residue lifecycle) is closed via the platform team's 7-day S3 lifecycle rule — pre-merge.

If a SAR is filed during the alpha window and an examiner asks "which transactions were compared for this member on this date?", the current design cannot answer that question from logs alone. This is the accepted risk for the alpha window per gate decision F3.

### PCI DSS

This change does not handle PAN, CVV, or cardholder data directly. `safetransactionresults` contains `statuswarning` (SAFE/RISKY classification) and `metadata.decisionResult` (feature vectors). If `metadata` contains raw card numbers or CVV-equivalent fields, those would be fetched by `SELECT *` (F11) and cached. Replace `SELECT *` with explicit columns to eliminate this risk without needing to audit the full Silver schema in this ticket.

### State money transmission

No direct exposure. The change affects risk scoring only — it does not alter payment execution, transfer limits, or reportable thresholds.

---

## Gate decision

Overall risk level is **Medium** (downgraded from High on 2026-06-17 after gate decisions applied).

**HUMAN GATE CLOSED.** The application security reviewer (Luis Betancourth) reviewed this threats.md on 2026-06-17 and closed the disposition of F1 / F2 / F3 / F5 / F5+. See the approval line at the bottom of this file.

Resolution summary:
- F1 (f-string SQL) → **mitigated** via PyAthena parameterized queries (gate applied 2026-06-17).
- F2 (Athena result residue lifecycle) → **accepted with pre-merge platform action** — platform team owns the 7-day S3 lifecycle rule. Tracked as a checkbox in the PR DoD.
- F3 (audit log) → **accepted with external owner** — owned by the audit/compliance team initiative. NO follow-up ticket in this scope.
- F5 (validation script bundling) → **mitigated by redesign** — script removed entirely; validation via production code + 24h alpha observation.
- F5+ (observability gap) → **mitigated** by structured logging task T_LOGGING (`similarity.no_history` vs `similarity.athena_failure` with `classify_exception()` categories).

Open findings (lower severity, see Mandatory Controls section): F4 (PII in timeout logs — partially closed by F5+ for new paths), F6 (IAM policy template), F7 (cache eviction policy), F8 (Athena workgroup cost cap), F11 (SELECT * replaced by explicit column list — closed in spec). Implementer should address F11 mandatorily; F4/F6/F7/F8 carry over as implementer attention items but do NOT block merge.

---

## Approval (filled in by the human reviewer, not the agent)

For High risk, the human reviewer must append a line at the very bottom of this file:

```
Decision: approved by <name or email> — <YYYY-MM-DD>
```

The `/blossom-workflow:execute` command greps the bottom of this file for the literal string `Decision: approved` and refuses to run if it is missing.

---

**Decision: approved by Luis Betancourth — 2026-06-17**

Gate decisions:
- F1 → mitigated via PyAthena parameterized queries
- F2 → accepted with pre-merge platform action (S3 lifecycle 7d)
- F3 → accepted with external owner (audit team initiative)
- F5 → redesigned (no separate script; validation via prod code + alpha observation)
- F5+ → added structured logging requirement (Athena exception vs 0 rows)

Cross-account IAM risk now gated on post-deploy alpha observation (24h monitoring window).
Final overall risk: medium (down from high after F1 mitigation, F5 redesign, F3 externalization).
