# endpoint/

> Per-module AI agent context. Companion to `docs/codemap/01-endpoint/README.md`.

## Purpose

Code that lives in the SageMaker container. Orchestrates K-Means + rules + Athena similarity.

## Where things live

```
endpoint/
├── inference_rules.py    — orchestrator (model_fn, predict_fn, DTYPE_MAP, _validate_similarity_input)
├── similarity_matcher.py — Athena loader (find_similar_transaction, classify_exception, _hash_idolbuser)
├── statistical_rules.py  — Rules v8 (score_transaction_v8, classify_risk)
├── schema_validator.py   — Schema validation (58 expected num__+cat__ features)
├── validate_s3_data.py   — Offline CLI to validate reference data
└── requirements.txt      — pyathena, python-dateutil, pyarrow, boto3
```

## Key files

- `inference_rules.py` — ~1285 lines. Critical function: `predict_fn`. **Do not modify the stage order** (K-means before rules before similarity).
- `similarity_matcher.py` — ~1100 lines. The Athena query lives here. **Do not use f-string SQL** (F1 test enforces this).
- `statistical_rules.py` — 12 v8 rules. Weight or threshold changes go here.
- `schema_validator.py` — If you add features, update the expected list.

## Conventions

- **Lazy imports** of `similarity_matcher` and `statistical_rules` via `importlib`. Disabled via env vars.
- **DTYPE_MAP cast** in `input_fn`. If you add a column, add it to the map.
- **`_hash_idolbuser(value)`** for logs — NEVER log `idOLBUser` in plaintext.
- **`classify_exception(exc)`** to categorize Athena errors. 5 categories.
- **`_compute_sliding_window(months=6)`** inside each `find_similar_transaction` call. NOT in `model_fn()`.
- **PyAthena parameterized queries** (`cursor.execute(sql, params)`). No f-string.
- **On-demand Athena connection** — open/close per call. No singleton.

## Dependencies

- **Internal imports:** none cross-file (all modules are lazy-loaded)
- **External:** pyathena, python-dateutil, pyarrow, boto3
- **Imported by:** scripts in `deploy/` (they package these 4 .py files into the tarball)
- **Tested by:** `tests/test_*.py` (suite in `tests/` module) + `endpoint/test_csv_loading.py`

## Tests

- Embedded test: `endpoint/test_csv_loading.py`
- External suite: `pytest tests/similarity/test_athena_similarity_*.py tests/endpoint/test_graceful_degradation.py`
- Coverage: ~10 test files, ~30+ test cases

## Gotchas

- **K-means ALWAYS runs.** If you think "I'll wrap the whole predict_fn in a try/catch" — don't. K-means + rules + similarity are independent parallel branches. See `docs/codemap/00-overview/Graceful-Degradation.md`.
- **D1 graceful (idOLBUserTxns/createdAtTxns null):** Do NOT return 400. Mark the row as `sim_skip`, `sim_*=null`; K-means still produces a score.
- **The container stays warm for days.** Anything that depends on `now()` must be computed in `predict_fn`, NEVER in `model_fn()`.
- **`idolbuser` (lowercase) in Athena, `idOLBUser` (CamelCase) in Python code.** `_normalize_athena_columns` maps between the two.
- **`SELECT` with explicit columns** (not `*`) in production queries. Includes `metadata`.
- **Casting `idOLBUserTxns` to int:** the payload may carry floats (`83772.0`). The `int()` cast + `pd.isnull()` check before it handles both cases.
- **Tests cache `_similarity_mod` and `HAS_SIMILARITY`.** You need an `autouse` monkeypatch fixture that resets them, otherwise tests are order-dependent.

## See also

- [Module overview](../docs/codemap/01-endpoint/README.md)
- [Public API](../docs/codemap/01-endpoint/Public-API.md)
- [Similarity Athena concept](../docs/codemap/00-overview/Similarity-Athena.md)
- [Graceful degradation](../docs/codemap/00-overview/Graceful-Degradation.md)
- [Root project context](../CLAUDE.md)
