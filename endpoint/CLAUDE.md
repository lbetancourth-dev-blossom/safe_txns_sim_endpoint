# endpoint/

> Per-module AI agent context. Companion to `docs/codemap/01-endpoint/README.md`.

## Purpose

Código que vive en el contenedor SageMaker. Orquesta K-Means + reglas + similitud Athena.

## Where things live

```
endpoint/
├── inference_rules.py    — orquestador (model_fn, predict_fn, DTYPE_MAP, _validate_similarity_input)
├── similarity_matcher.py — Athena loader (find_similar_transaction, classify_exception, _hash_idolbuser)
├── statistical_rules.py  — Reglas v8 (score_transaction_v8, classify_risk)
├── schema_validator.py   — Validación schema (58 num__+cat__ features esperadas)
├── validate_s3_data.py   — CLI offline para validar reference data
└── requirements.txt      — pyathena, python-dateutil, pyarrow, boto3
```

## Key files

- `inference_rules.py` — ~1285 líneas. Función crítica: `predict_fn`. **No modificar el orden de stages** (K-means antes de reglas antes de similitud).
- `similarity_matcher.py` — ~1100 líneas. La query Athena vive acá. **No usar f-string SQL** (test F1 lo enforza).
- `statistical_rules.py` — 12 reglas v8. Cambios de peso o thresholds van acá.
- `schema_validator.py` — Si agregás features, actualizá la lista esperada.

## Conventions

- **Lazy imports** de `similarity_matcher` y `statistical_rules` via `importlib`. Disabled vía env vars.
- **DTYPE_MAP cast** en `input_fn`. Si agregás columna, agregala al map.
- **`_hash_idolbuser(value)`** para logs — NUNCA loguear `idOLBUser` en plaintext.
- **`classify_exception(exc)`** para categorizar errores Athena. 5 categories.
- **`_compute_sliding_window(months=6)`** dentro de cada `find_similar_transaction` call. NO en `model_fn()`.
- **PyAthena parameterized queries** (`cursor.execute(sql, params)`). No f-string.
- **On-demand Athena connection** — abrir/cerrar por call. No singleton.

## Dependencies

- **Imports internos:** ninguno cross-file (todos los módulos son lazy-loaded)
- **External:** pyathena, python-dateutil, pyarrow, boto3
- **Imported by:** scripts en `deploy/` (empaquetan estos 4 .py al tarball)
- **Tested by:** `test/test_*.py` (suite en módulo `test/`) + `endpoint/test_csv_loading.py`

## Tests

- Test embebido: `endpoint/test_csv_loading.py`
- Suite externa: `pytest test/test_athena_similarity_*.py test/test_graceful_degradation.py`
- Cobertura: ~10 archivos de test, ~30+ test cases

## Gotchas

- **K-means SIEMPRE corre.** Si pensás "le pongo un try/catch a todo el predict_fn", no — K-means + reglas + similitud son ramas paralelas independientes. Ver `docs/codemap/00-overview/Graceful-Degradation.md`.
- **D1 graceful (idOLBUserTxns/createdAtTxns null):** NO retornar 400. Marcar row como `sim_skip`, `sim_*=null`, K-means igual produce score.
- **El contenedor queda caliente días.** Cualquier cosa que dependa de `now()` debe calcularse en `predict_fn`, NUNCA en `model_fn()`.
- **`idolbuser` (lowercase) en Athena, `idOLBUser` (CamelCase) en código Python.** `_normalize_athena_columns` mapea entre los dos.
- **`SELECT` con columnas explícitas** (no `*`) en queries productivas. Incluye `metadata`.
- **Casting de `idOLBUserTxns` a int:** el payload puede traer floats (`83772.0`). El `int()` cast + `pd.isnull()` antes maneja ambos casos.
- **Tests cachean `_similarity_mod` y `HAS_SIMILARITY`.** Necesitás un `autouse` monkeypatch fixture que los resetee, sino los tests son order-dependent.

## See also

- [Module overview](../docs/codemap/01-endpoint/README.md)
- [Public API](../docs/codemap/01-endpoint/Public-API.md)
- [Similarity Athena concept](../docs/codemap/00-overview/Similarity-Athena.md)
- [Graceful degradation](../docs/codemap/00-overview/Graceful-Degradation.md)
- [Root project context](../CLAUDE.md)
