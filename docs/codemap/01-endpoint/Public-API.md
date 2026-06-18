---
title: Endpoint Public API
aliases: [SageMaker Handlers, model_fn predict_fn, Endpoint Contract]
tags: [module, endpoint, api, sagemaker]
type: api
last_mapped_at: 2026-06-17T19:07:41Z
last_commit: 2ac735d
---

# Endpoint Public API

Las 4 funciones que SageMaker invoca por contrato + columnas del output.

## `model_fn(model_dir: str) -> dict`

Carga el modelo en RAM al arrancar el contenedor. Se llama una sola vez. **NO** computa la sliding window ni nada que dependa del tiempo — el contenedor queda caliente días.

**Input:** `model_dir` (path absoluto al directorio de artefactos, normalmente `/opt/ml/model`)

**Output:** dict con

| Key | Tipo | Origen |
|---|---|---|
| `kmeans_model` | sklearn KMeans | `kmeans_model.joblib` |
| `pipeline` | sklearn ColumnTransformer | `preprocessing_pipeline.joblib` |
| `selected_features` | list[str] | `selected_features.csv` |
| `centroids` | DataFrame | `centroids.csv` |
| `kmeans_artifacts` | dict | `kmeans_artifacts.json` (scalers + thresholds por cluster) |

## `input_fn(request_body: str|bytes, content_type: str) -> pd.DataFrame`

Parsea el payload del request. Soporta `text/csv` (preferido) y `application/json`.

**CSV path:**
1. `pd.read_csv(io.StringIO(body))`
2. Aplicar `DTYPE_MAP` — cast explícito de tipos (61 columnas, ver `docs/ENDPOINT_INPUT_FORMAT.md`)
3. Validar que las columnas requeridas estén presentes (vía `schema_validator`)

**Errores:** Si una columna requerida está ausente, retorna error 4xx via `output_fn`. Si `idOLBUserTxns` o `createdAtTxns` están null/ausentes → no es error, se maneja en `predict_fn` con `sim_*=null` (D1 graceful).

## `predict_fn(input_data: pd.DataFrame, model_artifacts: dict) -> pd.DataFrame`

El core. Pipeline completo: K-Means + reglas + similitud + combiner.

### Fases internas

1. **Validate gate** — `validate_gate(input_data)` aplica `DTYPE_MAP` final, whitelist de columnas
2. **Derive features** — calcula `hour_sin`, `hour_cos`, `day_of_week_cos`, `is_night`, `recency_user_created_days` si no vienen en el payload
3. **K-Means stage** (~L900–991) — preprocesa con `pipeline.transform()`, predict cluster, calcula `Distance_to_Centroid`, deriva `kmeans_risk_score` + `kmeans_risk_decision` via scalers del cluster
4. **Rules stage** (~L990–1020) — por row, `statistical_rules.score_transaction_v8(row)` → `risk_score`, `risk_decision`, `is_outlier`
5. **Similarity validation** (~L1100) — `_validate_similarity_input(df)` retorna `(sim_input_ok, sim_skip_rows)`
6. **Similarity stage** (~L1049–1130) — para rows no-skip, `find_similar_transaction(idolbuser)` con Athena
7. **Combiner** — escribe columnas `sim_*`, agrega `audit_*` fields, mantiene `kmeans_*` intactos

### Output: columnas en out_df

| Columna | Tipo | Siempre presente | Descripción |
|---|---|---|---|
| `TransactionID` | int64 | sí | Echo del input |
| `Cluster` | int | sí | Cluster K-means asignado |
| `Distance_to_Centroid` | float | sí | Distancia euclidiana al centroide |
| `is_outlier` | bool | sí | `Distance > threshold(Cluster)` |
| `kmeans_risk_score` | int 0–100 | sí | Solo K-Means |
| `kmeans_risk_decision` | str | sí | Solo K-Means: Accept/User Auth/Admin Review/Reject |
| `risk_score` | int 0–100 | sí (default 0 si rules disabled) | K-Means + reglas combinado |
| `risk_decision` | str | sí | Decisión final combinada |
| `sim_match_txn_id` | int o null | **null si Athena fail / no history / D1 skip** | TransactionID del match |
| `sim_score` | float o null | **null si Athena fail** | Score 0–1 de cosine similarity |
| `sim_status` | str o null | **null si Athena fail** | SAFE/RISKY del match histórico |
| `sim_decision` | str o null | **null si Athena fail o sim_score<threshold** | Decisión derivada del match |
| `audit_category` | str | sí | Categoría auditable de la decisión |
| `audit_explanation` | str | sí | Razón en lenguaje natural |
| `ux_copy` | str | sí | Mensaje user-facing |
| `num__*` features | float | sí | Features numéricas post-scaling |
| `cat__*` features | float (0/1) | sí | Features categóricas one-hot |

Total ~70 columnas en el output.

## `output_fn(prediction: pd.DataFrame, accept: str) -> bytes`

Serializa `out_df` a JSON. Soporta `application/json`.

**Formato:**

```json
[
  {
    "TransactionID": 4836236,
    "Cluster": 2,
    "Distance_to_Centroid": 1.847,
    "is_outlier": false,
    "kmeans_risk_score": 18,
    "kmeans_risk_decision": "Accept",
    "risk_score": 24,
    "risk_decision": "Accept",
    "sim_match_txn_id": null,
    "sim_score": null,
    "sim_status": null,
    "sim_decision": null,
    "audit_category": "low_risk_cluster",
    "audit_explanation": "Cluster típico de bajo riesgo; sin historial Athena para reforzar.",
    "ux_copy": "Operación procesada.",
    "num__amount": -0.42,
    "cat__channel_MOBILE": 1.0,
    ...
  },
  ...
]
```

## Errores

| Caso | Comportamiento |
|---|---|
| Schema inválido (columna requerida ausente) | error 4xx via output_fn |
| `idOLBUserTxns` / `createdAtTxns` null | NO es error → `sim_*=null` para ese row |
| Athena timeout / exception | NO es error → `sim_*=null` + log warning |
| Modelo no carga (joblib roto) | error 5xx al arrancar el contenedor (model_fn falla) |
| Excepción inesperada en K-Means | error 5xx (no se enmascara — es bug serio) |

## See also

- [[01-endpoint/README]] — overview del módulo
- [[Architecture]] — flujo completo del sistema
- `docs/ENDPOINT_INPUT_FORMAT.md` — las 61 columnas del input

## Backlinks

- [[Architecture]]
- [[README]]
- [[Schema]]

#endpoint #api #sagemaker #handlers
