# Deployment Guide

How to deploy the SageMaker endpoint with exact field matching and Athena similarity.

## Quick Start

**REQUIRED**: Deploy from a SageMaker Notebook. CLI deployment fails due to IAM trust policy — the local machine lacks the SageMaker execution role, so SageMaker cannot access the model tarball in S3 on your behalf.

---

## Model Tarball Location

The current model artifact (after DATA-1264 fixes) lives at:

```
s3://blossom-analytics-safe-dev-nv/output/kmeans-endpoint-v2-fixes/model.tar.gz
```

---

## Method 1: SageMaker Notebook (Required)

### Why notebook-only

- The local CLI (`deploy/deploy_final.py`) can upload the tarball to S3 but cannot deploy the endpoint because the IAM trust policy on the SageMaker execution role only trusts `sagemaker.amazonaws.com`, not your local dev role.
- The notebook runs inside SageMaker, so `get_execution_role()` returns the correct role automatically.

### Steps

1. **Open SageMaker Notebook Instance**
   - AWS Console → SageMaker → Notebook instances → Open `JupyterLab`

2. **Open a new notebook or the existing one**
   ```
   safe-txn-enpoint.ipynb
   ```

3. **Paste and run this deploy cell**

   ```python
   from sagemaker.sklearn.model import SKLearnModel
   from sagemaker import get_execution_role, Session

   sagemaker_session = Session()
   role = get_execution_role()

   # Current model artifact (DATA-1264 fixes)
   model_artifact_uri = "s3://blossom-analytics-safe-dev-nv/output/kmeans-endpoint-v2-fixes/model.tar.gz"

   sk_model = SKLearnModel(
       model_data=model_artifact_uri,
       role=role,
       entry_point="inference_rules.py",
       framework_version="1.2-1",
       sagemaker_session=sagemaker_session
   )

   # Option A: update existing endpoint (recommended if endpoint already exists)
   endpoint_name = "data-safe-txns-endpoint"

   # Option B: create a new endpoint with a versioned name
   # endpoint_name = "data-safe-txns-v2"

   predictor = sk_model.deploy(
       initial_instance_count=1,
       instance_type="ml.m5.large",
       endpoint_name=endpoint_name,
   )

   print(f"Deployed to: {endpoint_name}")
   ```

4. **Wait for deployment** (~5-10 minutes)
   - The notebook cell blocks until the endpoint reaches `InService`.

5. **Verify**
   ```python
   import boto3
   sm = boto3.client("sagemaker")
   response = sm.describe_endpoint(EndpointName=endpoint_name)
   print(f"Status: {response['EndpointStatus']}")
   # Expected: Status: InService
   ```

---

## Endpoint Name Options

| Name | When to use |
|------|-------------|
| `data-safe-txns-endpoint` | Existing endpoint — update in-place. Zero downtime if config update is supported. |
| `data-safe-txns-v2` | New endpoint for side-by-side testing before cutting over. |

To delete the old endpoint after verifying the new one:

```python
client = boto3.client("sagemaker")
client.delete_endpoint(EndpointName="data-safe-txns-endpoint")
client.delete_endpoint_config(EndpointConfigName="data-safe-txns-endpoint")
```

---

## What Gets Deployed

### Container Image
- **Framework**: scikit-learn 1.2-1 (CPU)
- **Python**: 3.9
- **Base Image**: `683313688378.dkr.ecr.us-east-1.amazonaws.com/sagemaker-scikit-learn:1.2-1-cpu-py3`

### Artifacts (inside model.tar.gz)
- `kmeans_model.joblib` — Trained K-Means clustering model
- `preprocessing_pipeline.joblib` — Feature preprocessing pipeline
- `centroids.csv` — K-Means cluster centroids
- `inference_rules.py` — Main inference entry point
- `similarity_matcher.py` — Exact field matching (49 scored fields)
- `schema_validator.py` — Input validation
- `statistical_rules.py` — Risk rules v8
- `requirements.txt` — Python dependencies (pyathena, python-dateutil, pyarrow, boto3)

---

## Testing After Deployment

### Local Test via process_endpoint.py

```bash
# Test with the 16-scenario test CSV
python3 tests/process_endpoint.py \
  --input data/test_escenarios.csv \
  --output results.csv \
  --profile blossom-dev

# Verify sim_* columns are populated:
# sim_match_txn_id, sim_score, sim_status, sim_decision
```

### CloudWatch Logs

```bash
aws logs tail /aws/sagemaker/Endpoints/data-safe-txns-endpoint --follow \
  --region us-east-1
```

Look for:
- `[SIMILARITY] Loading from Athena` — Athena query fired
- `[SIMILARITY] Exact field match: best match score=` — matching result
- `[SIMILARITY] No Athena data` — user has no history (graceful degradation)

### Console Verification

1. AWS Console → SageMaker → Endpoints
2. Find `data-safe-txns-endpoint`
3. Verify Status: `InService`

---

## Rollback

If deployment fails, the previous endpoint version remains active (SageMaker does not swap until the new one is InService).

To force a rollback to a previous config:
```bash
aws sagemaker update-endpoint \
  --endpoint-name data-safe-txns-endpoint \
  --endpoint-config-name <previous-config-name> \
  --region us-east-1
```

---

## Performance Notes

- **Deployment time**: ~5-10 minutes total
- **Cold start**: First prediction ~5s (model warming up)
- **Steady state**: ~0.5-1s per batch

---

## Related Documentation

- [Exact Matching Guide](./EXACT_MATCHING.md)
- [Similarity Matching Reference](../references/SIMILARITY_MATCHING.md)
- [Athena Troubleshooting](./ATHENA_TROUBLESHOOTING.md)
- [Endpoint Input Format](../references/ENDPOINT_INPUT_FORMAT.md)
- [Graceful Degradation](../references/GRACEFUL_DEGRADATION.md)
