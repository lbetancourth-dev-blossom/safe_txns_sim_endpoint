# Refinement — DATA-1264

**Date:** 2026-06-16 17:58
**Mode:** feature
**Risk:** medium
**Published:** yes · https://blossomtechnology.atlassian.net/browse/DATA-1264 (comment id 294468)

## Applied simplifications

_None applied. Listed in the Jira comment as recommendations only._

## Created subtasks

_None created in Jira. Listed in the Jira comment as manual-handling recommendations._

## AC edits applied

_None applied to the ticket. Listed in the Jira comment as recommendations only._

## Developer corrections during refinement

The dev corrected the refiner output mid-session. These corrections are reflected in the published comment:

1. **Window is sliding from `now()`** — not anchored to `createdAtTxns`. The 6-month range is computed at each endpoint request (`now() − 6 months` to `now()`), inside `find_similar_transaction()`, not at model load.
2. **`idOLBUserTxns` and `createdAtTxns` are input contract** — both must be present in every request payload. Endpoint must validate and return 400 if missing.
3. **6 months is arbitrary** — product decision, no statistical justification. AC1 reduced to a one-line documentation note.
4. **SageMaker → Athena connection must be validated from the endpoint** — the notebook ran in SageMaker Studio (different IAM role, container, possibly different VPC). Promoted from "warning" to explicit subtask (blocking AC5).
5. **K-means and similarity are independent, not chained with fallback.** Verified in `endpoint/inference_rules.py`:
   - K-means runs first (L980-991) and writes `kmeans_risk_score`, `kmeans_risk_decision` to `out_df`. Always.
   - Similarity runs after (L1049-1130) as an additive enrichment, writing `sim_match_txn_id`, `sim_score`, `sim_status`, `sim_decision`.
   - When the user has no history in the 6-month window (or Athena errors), `sim_*` go to `None`. The `kmeans_*` columns are untouched because they were computed in a separate earlier stage.
   - The ticket's wording ("fallback to K-means") is imprecise — there is no try/catch or substitution between the two. They are parallel branches of the same `predict_fn`.
   - This affects Scenario 3 framing, AC4 interpretation, and the subtask 5 test harness (now explicit: K-means columns intact in cases b/c, not just "fallback works").

## Full comment

**Análisis previo — Blossom Refinement**

**Riesgo: medio.** Patrón PyAthena validado en notebook de SageMaker Studio, pero la conexión Athena/Glue desde el endpoint productivo (rol IAM, VPC, contenedor) NO está validada. La propagación de `idOLBUserTxns` al matcher tampoco existe hoy.

---

**Decisiones de producto / dev**

- Ventana = **sliding `now() − 6 meses` a `now()`**, calculada en cada request del endpoint (no anclada a `createdAtTxns` del payload).
- 6 meses es **decisión de producto arbitraria**, sin análisis estadístico previo. Cierra AC1.
- `idOLBUserTxns` y `createdAtTxns` son **parámetros de entrada obligatorios** del payload — el endpoint debe validar su presencia antes de invocar la similitud.

**Query Athena final:**

```sql
SELECT ... FROM dlh_silver_safe_alpha.safetransactionresults
WHERE idolbuser = :idOLBUserTxns
  AND createdat >= CURRENT_TIMESTAMP - INTERVAL '6' MONTH
  AND statuswarning IN ('SAFE','RISKY')
```

---

**Advertencias**

- `idOLBUserTxns` no se pasa hoy a `find_similar_transaction()` desde `predict_fn` (`inference_rules.py` L1059-1069). Sin esto la query Athena no puede filtrar por usuario — bloqueador de la implementación.
- El notebook `PyAthena.ipynb` corrió en SageMaker Studio. El endpoint productivo es otro contexto (rol IAM distinto, contenedor distinto, posible VPC distinta). Hay que validar la conexión desde el endpoint específicamente, no asumir que el notebook valida el caso productivo.
- El rol IAM de ejecución del endpoint alpha necesita `athena:StartQueryExecution` + `s3:PutObject` sobre el bucket de staging. No documentado en el repo.
- `datetime.now() − relativedelta(months=6)` debe evaluarse **dentro de `find_similar_transaction()`**, NO en `model_fn()`. El contenedor SageMaker se mantiene caliente por días — si la fecha se calcula al cargar el modelo, la ventana envejece silenciosamente.
- Validar que la columna `idolbuser` en el Glue catalog no sea sparse históricamente (muchos nulls reducen la utilidad del filtro por usuario).

---

**Estimación**

- Tamaño realista: M (14h, +2h por validación de conexión endpoint→Athena que el refiner inicial no contempló)
- Histórico equipo: M (12-16h · mediana ~12h · n=2 · confianza baja)
- Los 16 pts asignados están dentro del rango histórico P75 — sin inflación.

---

**Subtasks sugeridos (no creados en Jira — manejar manualmente)**

1. Validar input contract del endpoint: `idOLBUserTxns` y `createdAtTxns` deben estar presentes en cada request. Si faltan: error 400 explícito.
2. Implementar `load_reference_data_from_athena()` en `similarity_matcher.py` con la query Athena de arriba. Ventana sliding `now() − 6m` calculada en tiempo de inferencia.
3. Validar la conexión SageMaker → Athena/Glue **desde el endpoint** (no desde un notebook). Bloqueante para AC5.
4. Validar permisos IAM del rol SageMaker alpha para Athena + bucket de staging. Documentar los permisos en el repo.
5. Harness de pruebas: (a) usuario con datos en ventana → `sim_score`; (b) usuario sin datos en ventana → fallback K-means sin excepción; (c) `idOLBUserTxns` ausente → error 400 controlado.
6. Doc E2E consolidada (kmeans + rules + similarity + Athena). Reusar los ~15 archivos en /docs con un índice nuevo en `README_E2E.md`.

---

**Edits sugeridos a los ACs (no aplicados — quedan como recomendación)**

- **AC 1:** "El periodo de 6 meses está documentado en el repositorio (decisión de producto, sin análisis estadístico previo)."
- **AC 2:** "El prefiltro por ventana sliding de 6 meses está implementado en `similarity_matcher.py` usando Athena con filtro por `idOLBUser` y `createdat >= now() − 6m`. Los resultados se reflejan en `sim_score`, `sim_status`, `sim_decision` del endpoint."
- **AC 3:** "El orden de filtrado en la query Athena es: ventana de tiempo → usuario → status. Condición de borde inclusiva (`>=`)."

---

**Escenarios de prueba**

- Usuario sin historia en últimos 6 meses → fallback K-means sin excepción (Escenario 3 del ticket).
- Athena cold start (2-10s) → confirmar timeout del endpoint.
- Requests concurrentes al endpoint → throttling Athena → graceful degradation al K-means.
- `idOLBUserTxns` o `createdAtTxns` null/ausente en payload → error 400 controlado, sin propagar excepción al caller.

---

**Positivo**

- `PyAthena.ipynb` da el patrón de conexión validado contra la tabla real. La traducción a Python productivo es directa.
- El repo ya tiene fallback de graceful degradation implementado y probado.

_Notas técnicas: `similarity_matcher.py` L67-69 — `DEFAULT_S3_BUCKET = "blossom-analytics-datalake-alpha"`. Modo Athena: `pyathena.connect(s3_staging_dir='s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/', region_name='us-east-2')`. `idOLBUserTxns` está en `DTYPE_MAP` (`inference_rules.py` L87, `int64`) pero NO se incluye en `query_features` de `predict_fn`. La tabla usa partitioning por `createdat_month=YYYY-MM` — predicado `createdat >= TIMESTAMP '...'` activa partition pruning. Dependencias nuevas en requirements: `pyathena`, `python-dateutil` (pinnar). Columna del Glue catalog: `idolbuser` (lowercase) — confirmar case-sensitivity._

## Raw analysis (JSON)

```jsonc
{
  "status": "completed",
  "risk": "medium",
  "area": {
    "id": "safe_data_science",
    "name": "Safe Transactions — Data Science / ML Endpoint",
    "matched_on": "none",
    "hint": "Prefijo DATA no está en jira-repo-map.yml (archivo ausente). Área inferida del contenido del ticket y del repo actual."
  },
  "relevant_repos": {
    "candidates": ["safe_txns_sim_endpoint"],
    "current_repo": "safe_txns_sim_endpoint",
    "in_scope": true
  },
  "estimation": {
    "bottom_up_hours": 14,
    "bottom_up_bucket": "M",
    "historical_median_hours": 12,
    "historical_p25": 12,
    "historical_p75": 16,
    "historical_sample_size": 2,
    "historical_confidence": "low",
    "delta_multiplier": 0.86
  },
  "published_comment_id": "294468"
}
```
