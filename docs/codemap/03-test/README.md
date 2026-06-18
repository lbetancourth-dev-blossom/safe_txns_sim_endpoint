---
title: Test
aliases: [Tests, Integration Tests, process_endpoint]
tags: [module, test, integration]
type: module
last_mapped_at: 2026-06-17T19:07:41Z
last_commit: 2ac735d
---

# Test

**Path:** `tests/`
**Maintainers:** Landneyker Betancourth

## Purpose

Tests de integración (pytest) + scripts manuales para invocar el endpoint real o simularlo localmente. **NO** son unit tests puros — son E2E del pipeline con mocks de boto3/Athena cuando aplica.

## Public surface

| Script | Tipo | Cuándo se usa |
|---|---|---|
| `python process_endpoint.py --input data/wp_input.csv --output data/wp_result.csv` | manual | Invocar el endpoint productivo con un CSV. Requiere AWS SSO activo |
| `pytest tests/similarity/test_athena_similarity_*.py` | automated | Suite de tests de Athena (parametrización, ventana, logging, input contract) |
| `pytest tests/endpoint/test_graceful_degradation.py` | automated | Casos de Athena empty, exception, permission |
| `python tests/integration/test_local_integration.py` | manual | Simulación local sin AWS (carga reference data de archivo) |
| `python tests/transform_similarity.py` | manual | Utility: convierte `wp_result.csv` → formato SafeTransactionResults |
| `python tests/upload_to_s3.py` | manual | Sube similarity reference CSV a S3 |

## Internal structure

```
tests/
├── process_endpoint.py                          — invoca data-safe-txns-endpoint via boto3 sagemaker-runtime
├── transform_similarity.py                      — transforma output del endpoint a formato datalake
├── upload_to_s3.py                              — upload de reference data a S3
├── verify_similarity_changes.py                 — verifica behavior changes
├── install_sagemaker_notebook.py                — setup utility
│
├── integration/
│   ├── test_local_integration.py                — simulación local con S3 reference
│   └── test_e2e_with_s3.py                      — E2E con Parquet de S3
│
├── endpoint/
│   ├── test_inference_integration.py            — integration K-means + rules + sim
│   ├── test_graceful_degradation.py             — Athena failures + null fields
│   └── test_dynamic_reload.py                   — cache invalidation
│
└── similarity/
    ├── test_similarity_fields.py                — validates sim_* response structure
    ├── test_parquet_similarity.py               — Parquet loader (legacy / fallback)
    ├── test_athena_similarity_sql_parametrized.py   — F1: parameterized queries, no f-string SQL
    ├── test_athena_similarity_input_contract.py     — D1: idOLBUserTxns/createdAtTxns validation
    ├── test_athena_similarity_logging.py            — F5+: 2-path INFO/WARNING + classify_exception
    ├── test_athena_similarity_window.py             — sliding window correctness
    └── test_athena_similarity_fallback.py           — exception → sim_*=null
```

## Key files

### `process_endpoint.py` — invocación real del endpoint

Reads CSV → batches a SageMaker `data-safe-txns-endpoint` → parses response → escribe CSV de salida con metadata JSON. Flags:

| Flag | Default |
|---|---|
| `--input` | `data/wp_input.csv` |
| `--output` | `data/wp_result.csv` |
| `--endpoint` | `data-safe-txns-endpoint` |
| `--region` | `us-east-1` |
| `--batch-size` | `10` |
| `--profile` | (default SSO profile) |

Requiere AWS SSO activo: `aws sso login --sso-session blossom`.

### Suite de Athena (`test_athena_similarity_*.py`)

7 archivos pytest que cubren los gate decisions de DATA-1264:

- **F1 (parameterized SQL):** test grepea el código para detectar f-string SQL. Falla si encuentra.
- **D1 (input contract):** missing `idOLBUserTxns` o `createdAtTxns` → `sim_*=null` sin error.
- **F5+ (structured logging):** verifica `similarity.no_history` INFO + `similarity.athena_failure` WARNING + `classify_exception()` categories.
- **Window:** que `_compute_sliding_window` use `now()` y no `model_fn` time.
- **Fallback:** Athena exception → `sim_*=null`, K-means intacto.

## Test patterns

- **Mocking-heavy** para Athena: `unittest.mock.patch` sobre `pyathena.connect()` y `cursor.execute()`.
- **Fixtures en `conftest.py`** (no presente como archivo separado todavía — fixtures inline en cada test file): proveen K-Means + ColumnTransformer artifacts reales para integración.
- **`caplog` de pytest** para assertions de logging (los 2 paths).
- **`monkeypatch` + `autouse=True` fixture** para resetear `_similarity_mod` y `HAS_SIMILARITY` entre tests (evita cache pollution). Esto fue Fix #2 del preflight de DATA-1264.

## Dependencies

- `pytest` — test harness
- `boto3` — sagemaker-runtime, s3
- `pyathena>=3.0` — para tests que mockean Athena
- `pandas`, `numpy`, `scikit-learn`, `pyarrow` — para fixtures de modelo y data

## Cómo correr la suite

```bash
# Toda la suite Athena
pytest tests/similarity/test_athena_similarity_*.py -v

# Tests de robustez
pytest tests/endpoint/test_graceful_degradation.py -v

# Test de un componente específico
pytest tests/similarity/test_athena_similarity_sql_parametrized.py -v

# E2E (requiere reference data en path)
python tests/integration/test_local_integration.py
```

## Sub-features

- (sin sub-pages — todos los archivos están listados arriba)

## Related concepts

- [[Similarity-Athena]] — qué se testea
- [[Graceful-Degradation]] — los invariantes que enforzan los tests
- [[SDD-Workflow]] — los tests son TDD-first per spec

## Backlinks

- [[Module-Map]]

#test #integration #pytest #athena
