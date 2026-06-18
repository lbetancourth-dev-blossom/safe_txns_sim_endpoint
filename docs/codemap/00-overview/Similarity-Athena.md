---
title: Similarity Athena
aliases: [Athena Similarity, Sliding Window Query, similarity_matcher]
tags: [concept, athena, similarity, ml-endpoint]
type: concept
last_mapped_at: 2026-06-17T19:07:41Z
last_commit: 2ac735d
---

# Similarity Athena

Cómo el endpoint consulta Athena en cada inferencia para encontrar transacciones similares dentro de una ventana sliding de 6 meses.

## Decisión arquitectónica

- **Athena = única fuente de datos para similitud** (decisión DATA-1264). No hay fallback a Parquet. No hay env var `USE_ATHENA`. El loader Parquet legacy fue removido.
- **Ventana sliding `now() − 6 meses`** computada en cada call dentro de `find_similar_transaction()`. **No** anclada a `createdAtTxns` del payload, **no** computada en `model_fn()` (el contenedor SageMaker queda caliente días).
- **Parameterized queries (PyAthena DB-API)** — defensa estructural contra SQL injection. El `int()` cast de `idolbuser` queda como defensa-in-depth pero no es la única.

## La query

```sql
SELECT idolbuser, createdat, statuswarning, metadata, <columnas explícitas>
FROM dlh_silver_safe_alpha.safetransactionresults
WHERE idolbuser = %(user)s
  AND createdat >= %(window_start)s
  AND createdat <= %(window_end)s
  AND statuswarning IN ('SAFE','RISKY')
```

El predicate `createdat >= TIMESTAMP '...'` activa **partition pruning** sobre `createdat_month=YYYY-MM` automáticamente.

## Connection lifecycle

- **On-demand por call.** `pyathena.connect(...)` se abre al inicio de cada `find_similar_transaction()` y se cierra al final.
- **No singleton.** Evita conexiones stale tras horas de idle en el contenedor.
- **No pool.** PyAthena no tiene soporte nativo; el throughput esperado no lo justifica.

## Timeout policy

- **10s timeout.** Cubre cold-start observado en notebook (2–10s).
- Al excederse → log estructurado WARNING `similarity.athena_failure` con categoría → `sim_*=null` → endpoint sigue respondiendo con K-means+reglas.

## Two-path observability

Ver [[Graceful-Degradation]] para el detalle completo. En corto:

```python
# Path A — 0 rows (usuario sin historial en ventana)
logger.info("similarity.no_history", extra={
    "idolbuser_hash": _hash_idolbuser(idolbuser),
    "window_months": 6,
    "rows": 0
})

# Path B — exception (cross-account roto, throttle, timeout, etc.)
logger.warning("similarity.athena_failure", extra={
    "idolbuser_hash": _hash_idolbuser(idolbuser),
    "exception_class": exc.__class__.__name__,
    "category": classify_exception(exc),  # permission | throttling | timeout | query_error | unknown
})
```

CloudWatch alarm debería disparar sobre Path B (especialmente `category=permission`). Path A es ruido normal — usuarios nuevos sin historial caen ahí.

## `classify_exception`

Helper de 4–5 líneas que clasifica excepciones de Athena/AWS en 5 categorías:

- **`permission`** — `AccessDeniedException`, `UnauthorizedException` → cross-account broken
- **`throttling`** — `ThrottlingException`, `TooManyRequestsException`
- **`timeout`** — query excedió `ATHENA_TIMEOUT_SECONDS`
- **`query_error`** — SQL syntax error, schema drift en Glue
- **`unknown`** — fallback

## Cache strategy

- Cache en memoria del contenedor, key = `(idolbuser_int, end_minute_str)`.
- Limita queries Athena cuando un mismo usuario aparece en múltiples transacciones del mismo minuto (común en batch).
- Se invalida automáticamente al cambiar el minuto (la sliding window se mueve).

## Cross-account constraint

El endpoint corre en cuenta **development**; Athena/Glue/S3 viven en cuenta **alpha** (`blossom-analytics-datalake-alpha`). Permisos requeridos del rol de ejecución:

- `athena:StartQueryExecution`, `athena:GetQueryExecution`, `athena:GetQueryResults` en `us-east-2`
- `s3:GetObject`, `s3:PutObject`, `s3:ListBucket` sobre `gold/athena-metadata/`
- `s3:GetObject` sobre `silver/SAFE/safetransactionresults/data/`
- `glue:GetTable`, `glue:GetPartitions` sobre `dlh_silver_safe_alpha.safetransactionresults`

**Validación AC5** (DATA-1264): post-deploy en alpha + monitoreo 24h CloudWatch del log `similarity.athena_failure`. Si `category=permission` → escalar a platform team. No script aparte — el `connect()` productivo ES la validación.

## Files

- `endpoint/similarity_matcher.py` — el loader, `find_similar_transaction()`, `_hash_idolbuser()`, `classify_exception()`, `_compute_sliding_window()`
- `endpoint/inference_rules.py` L1049–1130 — el bloque donde se llama (D1 `_validate_similarity_input` + integración con K-means+reglas)
- `tests/similarity/test_athena_similarity_*.py` — 7 archivos de tests pytest
- `docs/ATHENA_INTEGRATION.md` — guía detallada (escrita en DATA-1264 T6)

## See also

- [[K-Means-Pipeline]] — proceso paralelo independiente
- [[Statistical-Rules]] — el otro proceso paralelo
- [[Graceful-Degradation]] — qué pasa cuando esto falla
- [[Architecture]] — diagrama del sistema completo

## Backlinks

- [[Agent-Memory]]
- [[Glossary]]
- [[Graceful-Degradation]]
- [[Index]]
- [[K-Means-Pipeline]]
- [[README]]
- [[Statistical-Rules]]

#concept #athena #similarity #sliding-window #parameterized-queries
