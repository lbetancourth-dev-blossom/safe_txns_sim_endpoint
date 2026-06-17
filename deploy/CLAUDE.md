# deploy/

> Per-module AI agent context. Companion to `docs/codemap/02-deploy/README.md`.

## Purpose

Scripts para empaquetar `endpoint/*.py` + artefactos del modelo en `model.tar.gz`, subirlo a S3, y desplegarlo como SageMaker endpoint `data-safe-txns-endpoint`.

## Where things live

```
deploy/
├── deploy_similarity_endpoint.py  — orquestación completa (207 líneas)
├── deploy_with_sdk.py             — wrapper simple SageMaker SDK (51 líneas)
└── deploy_notebook.py             — extract code from notebook (64 líneas)
```

## Key files

- `deploy_similarity_endpoint.py` — full pipeline. S3 download → tar → upload → SageMaker create/update.
- `deploy_with_sdk.py` — versión simple con `SKLearnModel`. Usa cuando ya tenés `model.tar.gz` listo en S3.

## Conventions

- **Idempotent.** Si el endpoint existe, hace `update_endpoint`; si no, `create_endpoint`. Mismo nombre `data-safe-txns-endpoint`.
- **Waiter** de status post-deploy: 30s × 20 polls (~10 min) hasta `InService`.
- **`source_dir="endpoint"`** en `SKLearnModel` para que SageMaker auto-instale `requirements.txt`.
- **Env vars cross-account.** Inyecta `SIMILARITY_ATHENA_*` para apuntar a recursos de la cuenta alpha.

## Dependencies

- `boto3` (S3, SageMaker, STS clients)
- `sagemaker` SDK
- AWS profile `blossom-dev`, role `AmazonSageMaker-ExecutionRole-20241029T103557`
- AWS account 436631265256 (development)
- Image base: `scikit-learn 1.2-1 CPU`

## Tests

No hay test suite dedicado. Validación = corrida real + waiter de status. Para CI ideal habría dry-run que valide el tarball antes del upload, pero no existe hoy.

## Gotchas

- **Cross-account permissions.** Para que el endpoint pueda leer Athena en alpha, el rol en development DEBE tener policies adicionales. Si no las tiene, el deploy "funciona" pero el endpoint loguea `similarity.athena_failure` con `category=permission` en cada call.
- **No usar `--no-verify` en commits del deploy.** Los hooks pueden detectar credenciales o configs sensibles.
- **El nombre del endpoint es hardcoded** `data-safe-txns-endpoint`. Cambiar acá implica cambiar también `test/process_endpoint.py` y cualquier consumer.
- **Re-deploy NO retraina el modelo.** Solo reemplaza el código (`endpoint/*.py`) y el tarball. Los artifacts del K-Means se descargan de S3.
- **El bucket de modelos es `blossom-analytics-safe-dev-nv`** (cuenta dev), distinto del datalake (`blossom-analytics-datalake-alpha`).

## See also

- [Module overview](../docs/codemap/02-deploy/README.md)
- [Endpoint module](../docs/codemap/01-endpoint/README.md)
- [Architecture](../docs/codemap/00-overview/Architecture.md)
- [Root project context](../CLAUDE.md)
