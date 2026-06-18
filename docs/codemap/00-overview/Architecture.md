---
title: Architecture
aliases: [System Architecture, Request Flow, Deployment Topology]
tags: [overview, architecture, sagemaker, athena]
type: overview
last_mapped_at: 2026-06-17T19:07:41Z
last_commit: 2ac735d
---

# Architecture

## Sistema de alto nivel

```mermaid
flowchart LR
    Caller[Caller<br/>e.g. OLB transaction service]
    Endpoint[SageMaker Endpoint<br/>SAFE_TXNS_ENDPOINT_DEV<br/>account: dev]
    Athena[(Athena<br/>dlh_silver_safe_alpha<br/>account: alpha · us-east-2)]
    S3Silver[(S3 Silver<br/>safetransactionresults<br/>account: alpha)]
    S3Staging[(S3 Staging<br/>athena-metadata<br/>account: alpha)]
    CW[CloudWatch<br/>structured logs<br/>similarity.athena_failure<br/>similarity.no_history]

    Caller -- CSV body --> Endpoint
    Endpoint -- "parameterized SQL<br/>WHERE idolbuser = :user<br/>AND createdat >= now() - 6m" --> Athena
    Athena -- "Glue catalog metadata" --> Athena
    Athena -- "read Parquet rows" --> S3Silver
    Athena -- "write query results" --> S3Staging
    Endpoint -- "warnings + info logs" --> CW
    Endpoint -- "JSON: kmeans_*, sim_*, audit_*" --> Caller
```

## Componentes

### Endpoint (SageMaker, cuenta development)

- Contenedor SKLearn 1.2-1 CPU, ml.m5.large × 1 instancia
- Carga: `kmeans_model.joblib`, `preprocessing_pipeline.joblib`, `centroids.csv`, `selected_features.csv`, `kmeans_artifacts.json`
- Código: [[01-endpoint/README]] — `inference_rules.py` (orquesta), `similarity_matcher.py` (Athena loader), `statistical_rules.py` (R1–R12), `schema_validator.py`
- Handlers SageMaker: `model_fn`, `input_fn`, `predict_fn`, `output_fn` — ver [[01-endpoint/Public-API]]

### Data lake (cuenta alpha, region us-east-2)

- **Glue catalog**: `dlh_silver_safe_alpha.safetransactionresults` (Hive partitioning por `createdat_month=YYYY-MM`)
- **S3 Silver**: `s3://blossom-analytics-datalake-alpha/datalake/silver/SAFE/safetransactionresults/data/`
- **S3 staging Athena**: `s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/`
- Cross-account: el endpoint en **development** lee del lake en **alpha** — requiere assume-role policy

### Pipeline de ingesta (offline, ver [[04-data-eng/README]])

Bronze (.gz JSON CDC) → Silver (Parquet) → Athena Glue catalog. No se ejecuta en línea con el endpoint; corre en jobs separados.

## Request flow — predict

```mermaid
sequenceDiagram
    autonumber
    participant C as Caller
    participant E as Endpoint
    participant K as K-Means + Rules
    participant S as similarity_matcher
    participant A as Athena
    participant L as CloudWatch

    C->>E: POST text/csv (N transactions)
    E->>E: input_fn() — parse CSV, DTYPE_MAP cast
    E->>K: K-Means cluster + Distance_to_Centroid
    E->>K: statistical_rules.score_transaction_v8()
    Note over K: K-means + rules SIEMPRE corren

    par Per-row similarity (best effort)
        E->>S: find_similar_transaction(idolbuser, threshold)
        S->>S: _validate_similarity_input() — D1 graceful
        alt idOLBUserTxns o createdAtTxns ausente
            S-->>E: (None, None, None, None) · sim_*=null
            S->>L: INFO similarity.validation_skip
        else fields presentes
            S->>S: _compute_sliding_window() — now() − 6m
            S->>A: parameterized SELECT (6m window)
            alt Athena OK con rows
                A-->>S: matching rows
                S-->>E: (matched_id, score, status, decision)
            else Athena 0 rows
                A-->>S: empty
                S->>L: INFO similarity.no_history
                S-->>E: (None, None, None, None)
            else Athena exception (timeout/throttle/permission)
                S->>L: WARNING similarity.athena_failure + category
                S-->>E: (None, None, None, None)
            end
        end
    end

    E->>E: combine_kmeans_and_rules() + similarity override
    E->>C: JSON output (kmeans_*, sim_*, audit_*)
```

## Layers y separación de responsabilidades

| Layer | Responsabilidad | Files |
|---|---|---|
| **Input contract** | Validar payload, cast tipos, derivar features temporales | `inference_rules.input_fn`, `DTYPE_MAP`, `_validate_similarity_input` |
| **K-Means baseline** | Cluster + distancia + score base | `inference_rules.predict_fn` L900–980 |
| **Rules layer** | R1–R12, normalización piecewise 0–100, classify_risk | `statistical_rules.score_transaction_v8` |
| **Similarity stage** | Athena loader + cosine similarity + null fallback | `similarity_matcher.find_similar_transaction` |
| **Combiner** | Override por similarity high-confidence; audit_* fields | `inference_rules.combine_kmeans_and_rules` |
| **Observability** | Structured logs con `_hash_idolbuser`, `classify_exception` | `similarity_matcher` L40–110 |

K-Means + Rules + Similarity son **procesos paralelos independientes** — ver [[Graceful-Degradation]]. Cualquier falla de similarity deja `sim_*=null`; K-means y reglas siempre producen su resultado.

## Deployment topology

- **Dev (developer machine):** corre tests locales con `pytest tests/`, simulación con `tests/integration/test_local_integration.py`, invocación real con `tests/process_endpoint.py`.
- **SageMaker (cuenta development):** endpoint productivo `SAFE_TXNS_ENDPOINT_DEV`. Deploy via [[02-deploy/README]] scripts.
- **Athena/Glue/S3 (cuenta alpha):** data lake compartido. El endpoint requiere permisos cross-account (`athena:*`, `s3:GetObject`, `glue:GetTable`, `glue:GetPartitions`).

## Cross-account IAM (riesgo top-level activo)

El rol de ejecución del endpoint en development necesita:

- `athena:StartQueryExecution`, `athena:GetQueryExecution`, `athena:GetQueryResults` en `us-east-2`
- `s3:GetObject`, `s3:PutObject`, `s3:ListBucket` sobre `blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/`
- `s3:GetObject` sobre `blossom-analytics-datalake-alpha/datalake/silver/SAFE/safetransactionresults/data/`
- `glue:GetTable`, `glue:GetPartitions` sobre `dlh_silver_safe_alpha.safetransactionresults`

Validación: post-deploy en alpha + monitoreo CloudWatch 24h del log `similarity.athena_failure` con `category=permission`. Ver [[changes/DATA-1264/plan.md]] para el contexto de riesgo aceptado.

## Backlinks

- [[Agent-Memory]]
- [[Glossary]]
- [[Index]]
- [[Public-API]]
- [[README]]
- [[SDD-Workflow]]
- [[Similarity-Athena]]
- [[Tech-Stack]]

#architecture #sagemaker #athena #cross-account #ml-endpoint
