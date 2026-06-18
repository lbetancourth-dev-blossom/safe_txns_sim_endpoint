---
title: Tech Stack
aliases: [Dependencies, Frameworks, Libraries]
tags: [overview, tech-stack, dependencies]
type: overview
last_mapped_at: 2026-06-17T19:07:41Z
last_commit: 2ac735d
---

# Tech Stack

| Layer | Tecnología | Notas |
|---|---|---|
| Lenguaje | Python 3.10 (SageMaker SKLearn 1.2-1 image) | |
| Framework ML | scikit-learn | K-Means + ColumnTransformer + OneHotEncoder |
| Modelo serializado | joblib | `.joblib` para modelo, pipeline, scalers |
| Data analytics | pandas, numpy, scipy | |
| Athena client | pyathena ≥3.0, <4 | Parameterized queries (DB-API style) |
| Date math | python-dateutil ≥2.8 | `relativedelta(months=6)` para sliding window |
| Parquet I/O | pyarrow ≥12 | Lectura de Silver layer (offline / data_eng) |
| AWS SDK | boto3 | S3, SageMaker Runtime, Athena, STS |
| Deploy | sagemaker SDK | `SKLearnModel` abstraction |
| Tests | pytest | Suite en `tests/` con fixtures + mocks |
| CI/CD | (no pipeline automatizado en este repo aún) | Deploy manual via scripts en `deploy/` |

## Manifests

- `endpoint/requirements.txt` — deps que se empaquetan en el tarball SageMaker
- (no `pyproject.toml` ni `setup.py` — repo no se publica como paquete)

## Versiones críticas pinneadas

- **pyathena**: forzado a `<4` por compatibilidad con SKLearn 1.2-1 image en SageMaker
- **python-dateutil**: rango compatible con la imagen base
- **scikit-learn**: la versión del image debe coincidir con la del joblib del modelo entrenado

## AWS resources

| Resource | Account | Region |
|---|---|---|
| Endpoint SageMaker `SAFE_TXNS_ENDPOINT_DEV` | development | us-east-1 |
| Glue catalog `dlh_silver_safe_alpha` | alpha | us-east-2 |
| S3 Silver bucket `blossom-analytics-datalake-alpha` | alpha | us-east-2 |
| S3 staging Athena bucket | alpha | us-east-2 |
| IAM role del endpoint | development | n/a |

Cross-account: el rol de ejecución del endpoint en development necesita policies para Athena, S3 y Glue en la cuenta alpha. Ver [[Architecture]] sección "Cross-account IAM".

## Env vars del endpoint (deploy time)

| Env var | Default | Descripción |
|---|---|---|
| `SIMILARITY_THRESHOLD` | `0.90` | Umbral para considerar matched=True |
| `SIMILARITY_ATHENA_DATABASE` | `dlh_silver_safe_alpha` | Glue database |
| `SIMILARITY_ATHENA_TABLE` | `safetransactionresults` | Tabla |
| `SIMILARITY_ATHENA_S3_STAGING` | `s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/` | Bucket donde Athena escribe resultados |
| `SIMILARITY_ATHENA_REGION` | `us-east-2` | Region de Athena/Glue |
| `ATHENA_WINDOW_MONTHS` | `6` | Tamaño de la ventana sliding |
| `ATHENA_TIMEOUT_SECONDS` | `10` | Timeout de cada query |
| `DISABLE_SIMILARITY` | (unset) | `=1` desactiva similitud completa (K-means + reglas solos) |
| `DISABLE_RULES` | (unset) | `=1` desactiva reglas estadísticas |

## Backlinks

- [[Index]]
- [[README]]

#tech-stack #dependencies #aws
