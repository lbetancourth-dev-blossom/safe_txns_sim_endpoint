# test/

> Per-module AI agent context. Companion to `docs/codemap/03-test/README.md`.

## Purpose

Tests de integración (pytest) + scripts manuales para invocar el endpoint productivo o simularlo localmente.

## Where things live

```
test/
├── process_endpoint.py                 — invocar data-safe-txns-endpoint via boto3 sagemaker-runtime
├── transform_similarity.py             — convertir output del endpoint a formato datalake
├── upload_to_s3.py                     — subir reference data a S3
├── verify_similarity_changes.py        — verifica behavior changes
├── install_sagemaker_notebook.py       — setup
│
├── test_local_integration.py           — E2E local (sin AWS, con S3 reference cargada de archivo)
├── test_e2e_with_s3.py                 — E2E con Parquet de S3
├── test_inference_integration.py       — K-Means + reglas + similarity integration
├── test_similarity_fields.py           — schema de sim_* responses
├── test_parquet_similarity.py          — Parquet loader (legacy)
├── test_dynamic_reload.py              — cache invalidation
├── test_graceful_degradation.py        — Athena failures + null fields
│
├── test_athena_similarity*.py          — 7 archivos cubriendo F1, D1, F5+, window, fallback
```

## Key files

- `process_endpoint.py` — script manual para llamar el endpoint productivo. Útil para smoke test después del deploy. Flags: `--input`, `--output`, `--endpoint`, `--region`, `--batch-size`, `--profile`.
- `test_athena_similarity_*.py` — los 7 son críticos. Enforzan: parameterized SQL (F1), input contract D1, two-path logging (F5+), sliding window, fallback semantics.
- `test_graceful_degradation.py` — los casos extremos. Si rompés alguno, probablemente rompiste invariantes.

## Conventions

- **Mocking pyathena.** `unittest.mock.patch('pyathena.connect')`. NO testees contra Athena real en pytest — usa el script manual `process_endpoint.py` para eso.
- **`monkeypatch` autouse fixture** para resetear `_similarity_mod` y `HAS_SIMILARITY` entre tests. Sin esto, los tests son order-dependent.
- **`caplog`** para assertions de logging — los 2 paths (`similarity.no_history` INFO, `similarity.athena_failure` WARNING).
- **No fixtures externos** (sin `conftest.py` separado por ahora). Fixtures inline en cada test file.
- **Test names** descriptivos: `test_predict_missing_idOLBUserTxns_returns_kmeans_with_sim_null`.

## Dependencies

- `pytest`
- `boto3`, `pyathena>=3.0`, `pandas`, `numpy`, `scikit-learn`, `pyarrow`

## Cómo correr

```bash
# Suite Athena
pytest test/test_athena_similarity_*.py -v

# Robustez
pytest test/test_graceful_degradation.py -v

# Test específico
pytest test/test_athena_similarity_sql_parametrized.py::test_query_uses_pyathena_dbapi -v

# E2E (requiere reference data en path)
python test/test_local_integration.py

# Smoke test endpoint real (requiere AWS SSO)
python test/process_endpoint.py --input data/wp_input.csv --output data/wp_result.csv
```

## Gotchas

- **AWS SSO expirado** hace que `process_endpoint.py` falle con `ProfileNotFound` o `ExpiredToken`. Renová con `aws sso login --sso-session blossom`.
- **Tests cachean `_similarity_mod`** — sin el `autouse` reset fixture, el test order cambia los resultados. Mirá `test_athena_similarity_logging.py` para el patrón correcto.
- **`endpoint_test/` fue eliminado** en DATA-1264 (era una copia divergente). Los únicos tests viven en `test/`.
- **`process_endpoint.py` espera CSV exacto.** 61 columnas en el orden de `docs/ENDPOINT_INPUT_FORMAT.md`. Cualquier desviación → SageMaker rechaza con 4xx.
- **No `--no-verify`** en commits de tests. Los hooks pueden detectar PII o credentials en fixtures.

## See also

- [Module overview](../docs/codemap/03-test/README.md)
- [Endpoint module](../docs/codemap/01-endpoint/README.md)
- [Similarity Athena concept](../docs/codemap/00-overview/Similarity-Athena.md)
- [Root project context](../CLAUDE.md)
