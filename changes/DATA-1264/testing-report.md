# Testing Report — DATA-1264

**Branch:** feat/DATA-1264
**Date:** 2026-06-17
**Implementer:** blossom-implementer (claude-sonnet-4-6[1m])

---

## Task Status

| Task | Tests Written | Tests Passing | Status |
|------|--------------|---------------|--------|
| T1 — `_validate_similarity_input` | 8 | 8/8 | DONE |
| T_SIMILARITY — `load_reference_data_from_athena` F1+F11 | 11 | 11/11 | DONE |
| T3 — `predict_fn` Athena integration D1+D2+D4+R5 | 7 | 7/7 | DONE |
| T4 — requirements.txt + deploy Athena env vars | 1 | 1/1 | DONE |
| T_LOGGING — structured logging two-path F5+ | 8 | 8/8 | DONE |
| T6 — Docs (glue-only) | N/A | N/A | DONE |

**Total: 34 new tests written, 34/34 passing**

---

## V1 — New Athena Tests

**Command:** `pytest test/test_athena_similarity_*.py -v`

```
test/test_athena_similarity_input_contract.py::test_validate_all_present_returns_ok PASSED
test/test_athena_similarity_input_contract.py::test_validate_missing_idolbuser_marks_row PASSED
test/test_athena_similarity_input_contract.py::test_validate_missing_idolbuser_column_marks_all PASSED
test/test_athena_similarity_input_contract.py::test_validate_idolbuser_non_int_marks_row PASSED
test/test_athena_similarity_input_contract.py::test_validate_does_not_raise_when_all_missing PASSED
test/test_athena_similarity_input_contract.py::test_validate_missing_createdat_marks_row_d1_graceful PASSED
test/test_athena_similarity_input_contract.py::test_validate_both_missing_marks_row_d1_graceful PASSED
test/test_athena_similarity_input_contract.py::test_endpoint_requirements_has_pyathena PASSED
test/test_athena_similarity_window.py::test_compute_window_uses_now_at_call PASSED
test/test_athena_similarity_window.py::test_compute_window_changes_between_calls PASSED
test/test_athena_similarity_window.py::test_normalize_athena_columns_maps_lowercase_to_camelcase PASSED
test/test_athena_similarity_window.py::test_load_from_athena_calls_connect_with_alpha_staging PASSED
test/test_athena_similarity_window.py::test_load_from_athena_uses_parameterized_query_F1 PASSED
test/test_athena_similarity_window.py::test_load_from_athena_uses_explicit_column_list_F11 PASSED
test/test_athena_similarity_window.py::test_load_from_athena_returns_none_on_connection_error PASSED
test/test_athena_similarity_window.py::test_load_from_athena_casts_idolbuser_to_int_defense_in_depth PASSED
test/test_athena_similarity_window.py::test_load_from_athena_empty_result_returns_none_tuple PASSED
test/test_athena_similarity_sql_parametrized.py::test_no_fstring_sql_in_module PASSED
test/test_athena_similarity_sql_parametrized.py::test_cursor_execute_uses_dict_params PASSED
test/test_athena_similarity_fallback.py::test_predict_fn_always_calls_athena PASSED
test/test_athena_similarity_fallback.py::test_predict_fn_never_calls_parquet_loader_d2 PASSED
test/test_athena_similarity_fallback.py::test_predict_fn_kmeans_intact_when_idolbuser_missing PASSED
test/test_athena_similarity_fallback.py::test_predict_fn_kmeans_intact_when_createdat_missing PASSED
test/test_athena_similarity_fallback.py::test_predict_fn_kmeans_intact_on_athena_exception PASSED
test/test_athena_similarity_fallback.py::test_predict_fn_kmeans_intact_on_athena_timeout_d4 PASSED
test/test_athena_similarity_fallback.py::test_predict_fn_succeeds_when_athena_returns_rows PASSED
test/test_athena_similarity_logging.py::test_athena_zero_rows_emits_no_history_log PASSED
test/test_athena_similarity_logging.py::test_athena_permission_error_emits_failure_log_with_category PASSED
test/test_athena_similarity_logging.py::test_athena_timeout_emits_failure_log_with_category_timeout PASSED
test/test_athena_similarity_logging.py::test_classify_exception_maps_permission_error PASSED
test/test_athena_similarity_logging.py::test_classify_exception_maps_timeout_error PASSED
test/test_athena_similarity_logging.py::test_classify_exception_maps_throttling_string_match PASSED
test/test_athena_similarity_logging.py::test_classify_exception_unknown_fallback PASSED
test/test_athena_similarity_logging.py::test_exception_message_truncated_to_200_chars PASSED

34 passed in 1.48s
```

**Result: PASS**

---

## V2 — Existing Tests Not Broken

**Command:** `pytest test/test_graceful_degradation.py test/test_parquet_similarity.py test/test_similarity_fields.py -v --tb=no`

```
test/test_graceful_degradation.py::test_no_parquet_files_in_s3 PASSED
test/test_graceful_degradation.py::test_all_records_pending PASSED
test/test_graceful_degradation.py::test_find_similar_with_no_reference_data PASSED
test/test_graceful_degradation.py::test_s3_connection_error PASSED
test/test_graceful_degradation.py::test_corrupted_parquet_files PASSED
test/test_parquet_similarity.py::test_parquet_loading PASSED
test/test_parquet_similarity.py::test_similarity_matching PASSED
test/test_similarity_fields.py::test_similarity_fields PASSED

8 passed
```

**Note:** `test_inference_integration.py` and `test_e2e_with_s3.py` are script-style
tests that require real S3 data and model artifacts — they are not runnable in local CI.
`test_parquet_similarity.py` covers the legacy Parquet path (still functional in
`load_reference_data_from_s3` which is not removed per D2 scope).

**Result: PASS**

---

## V3 — Linting

**Command:** `flake8 endpoint/similarity_matcher.py endpoint/inference_rules.py --max-line-length=120 --extend-ignore=E501,W503,W504`

No new violations introduced by DATA-1264 changes. Pre-existing E302/E305/E231 style
issues exist in the legacy code and are out of scope for this ticket.

Critical issues introduced: **0**
- F821 (undefined `_extract_vectors_from_df`) fixed by adding the helper function
- F1-no-fstring-sql waivers added to legacy S3 logging lines (not SQL)

**Result: PASS (no new violations)**

---

## V4 — Local Smoke Test: Athena Mocked (Parameterized Query F1)

Covered by `test_load_from_athena_uses_parameterized_query_F1` in
`test/test_athena_similarity_window.py`. Verifies:
- `cursor.execute()` called with dict params (not f-string SQL)
- `%(user)s`, `%(window_start)s`, `%(window_end)s` placeholders present
- `604150` (raw idolbuser) NOT in SQL string
- `params["user"]` is `int(604150)`

**Result: PASS**

---

## V5 — Graceful Degradation Smoke Tests (D1 + D4)

All covered by `test/test_athena_similarity_fallback.py`:

- (a) `test_predict_fn_kmeans_intact_when_idolbuser_missing` — K-means OK, sim_*=null, no exception
- (b) `test_predict_fn_kmeans_intact_when_createdat_missing` — K-means OK, sim_*=null, no exception
- (c) `test_predict_fn_kmeans_intact_on_athena_timeout_d4` — K-means OK, sim_*=null, `[ATHENA]` warning logged

And by `test/test_athena_similarity_logging.py`:
- `test_athena_timeout_emits_failure_log_with_category_timeout` — `category="timeout"` confirmed
- `test_athena_zero_rows_emits_no_history_log` — `similarity.no_history` INFO, `idolbuser_hash` present, plaintext absent

**Result: PASS**

---

## V6 — AC5 Post-Deploy Alpha Observation

Not applicable pre-merge (F5 gate applied 2026-06-17). Validation is done post-deploy
by observing `similarity.athena_failure` count in CloudWatch for 24h after alpha deploy.
See `docs/ATHENA_INTEGRATION.md` section "Post-Deploy Alpha Observation" for runbook.

**Result: N/A (post-deploy gate)**

---

## V7 — Docs Review

`docs/ATHENA_INTEGRATION.md` created with all required sections:
- Cross-account architecture (dev → alpha)
- Env vars table (no USE_ATHENA)
- IAM policy JSON (cross-account dev→alpha)
- F1 query format (parameterized, explicit column list)
- F5+ alerting playbook (similarity.no_history vs similarity.athena_failure)
- F2 platform action (S3 lifecycle 7d — platform team pre-merge action)
- F3 external owner (audit trail owned by audit/compliance team)
- Operational risk HLTC-12 (single point of failure, sim_score_null_rate suggestion)
- Troubleshooting table

`docs/ENDPOINT_FLOW_SEQUENCE.md` updated: paso 5 now references Athena single-source,
cross-account note, D1/D4 graceful degradation, updated env vars section.

**Result: PASS**

---

## V8 — PR Auto-Checklist

- [x] `changes/DATA-1264/spec.md`, `plan.md` present
- [x] File manifest matches `git diff --stat` (see below)
- [x] No TODO without closure
- [x] F1: `test_no_fstring_sql_in_module` GREEN
- [ ] F2: Platform team S3 lifecycle rule confirmation (pre-merge, platform action)
- [x] F3: `docs/ATHENA_INTEGRATION.md` documents audit trail as external owner scope
- [x] F5+: structured logs tested and passing

---

## TDD Iteration History

| Task | RED cycles | Notes |
|------|-----------|-------|
| T1 | 1 | Tests RED (import error), impl added, GREEN |
| T_SIMILARITY | 1 | Tests RED on missing impl, GREEN first attempt |
| T_SIMILARITY F1 | 1 extra | noqa waivers needed for legacy log lines matching FROM pattern |
| T3 | 3 | conftest fixture iterations (sparse→sparse_output, transformer names, return type list vs df) |
| T4 | 1 | requirements.txt created, test immediate GREEN |
| T_LOGGING | 0 | impl already present from prior session, tests GREEN immediately |
| T6 | N/A | glue-only, no tests |

---

## Structural Audit

- Stubs: **0**
- Unwired functions: **0** (`_extract_vectors_from_df` called from `load_reference_data_from_athena`)
- Deprecated env vars removed from deploy scripts: `SIMILARITY_S3_BUCKET`, `SIMILARITY_S3_KEY`
- `USE_ATHENA` toggle: **never added** (D2 compliance)

---

## Proposal Updates

None.
