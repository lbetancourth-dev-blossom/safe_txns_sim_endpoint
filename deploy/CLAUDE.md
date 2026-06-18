# deploy/

> Per-module AI agent context. Companion to `docs/codemap/02-deploy/README.md`.

## Purpose

Scripts to package `endpoint/*.py` + model artifacts into `model.tar.gz`, upload it to S3, and deploy it as the SageMaker endpoint `SAFE_TXNS_ENDPOINT_DEV`.

## Where things live

```
deploy/
├── deploy_final.py    — full pipeline: S3 download → tar → upload → SageMaker deploy
└── deploy_with_sdk.py — simple SageMaker SDK wrapper (use when tarball is already in S3)
```

## Key files

- `deploy_final.py` — full pipeline. S3 download → tar → upload → SageMaker create/update.
- `deploy_with_sdk.py` — simple version with `SKLearnModel`. Use when you already have `model.tar.gz` ready in S3.

## Conventions

- **Idempotent.** If the endpoint exists, runs `update_endpoint`; if not, `create_endpoint`. Same name `SAFE_TXNS_ENDPOINT_DEV`.
- **Status waiter** post-deploy: 30s × 20 polls (~10 min) until `InService`.
- **`source_dir="endpoint"`** in `SKLearnModel` so SageMaker auto-installs `requirements.txt`.
- **Cross-account env vars.** Injects `SIMILARITY_ATHENA_*` to point to resources in the alpha account.

## Dependencies

- `boto3` (S3, SageMaker, STS clients)
- `sagemaker` SDK
- AWS profile `blossom-dev`, role `AmazonSageMaker-ExecutionRole-20241029T103557`
- AWS account 436631265256 (development)
- Base image: `scikit-learn 1.2-1 CPU`

## Tests

No dedicated test suite. Validation = actual run + status waiter. For ideal CI there would be a dry-run that validates the tarball before the upload, but that does not exist today.

## Gotchas

- **Cross-account permissions.** For the endpoint to read Athena in alpha, the role in development MUST have additional policies. If it does not, the deploy "succeeds" but the endpoint logs `similarity.athena_failure` with `category=permission` on every call.
- **Do not use `--no-verify` on deploy commits.** Hooks may detect credentials or sensitive configs.
- **The endpoint name is hardcoded** as `SAFE_TXNS_ENDPOINT_DEV`. Changing it here also requires changing `test/process_endpoint.py` and any consumer.
- **Re-deploy does NOT retrain the model.** It only replaces the code (`endpoint/*.py`) and the tarball. K-Means artifacts are downloaded from S3.
- **The model bucket is `blossom-analytics-safe-dev-nv`** (dev account), distinct from the datalake bucket (`blossom-analytics-datalake-alpha`).

## See also

- [Module overview](../docs/codemap/02-deploy/README.md)
- [Endpoint module](../docs/codemap/01-endpoint/README.md)
- [Architecture](../docs/codemap/00-overview/Architecture.md)
- [Root project context](../CLAUDE.md)
