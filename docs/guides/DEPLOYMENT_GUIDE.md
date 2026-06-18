# Deployment Guide

How to deploy the SageMaker endpoint with exact field matching.

## Quick Start

**RECOMMENDED**: Deploy from the SageMaker Notebook (has proper execution role)

```bash
# In SageMaker Notebook, run:
# See: safe-txn-enpoint.ipynb cells 11-12
```

**ALTERNATIVE**: Deploy from CLI (requires IAM permissions)

```bash
cd /path/to/safe_txns_sim_endpoint
python3 deploy/deploy_final.py
```

---

## Method 1: SageMaker Notebook (Recommended)

### Why it's better
- ✅ Auto-detects execution role (no hardcoding)
- ✅ Proper IAM permissions in notebook environment
- ✅ Integrated with AWS SageMaker environment
- ✅ Easy to debug in notebook UI

### Steps

1. **Open SageMaker Notebook Instance**
   - AWS Console → SageMaker → Notebook instances → Open `JupyterLab`

2. **Open the notebook**
   ```
   safe-txn-enpoint.ipynb
   ```

3. **Run cells 11-12: Deploy**
   ```python
   from sagemaker.sklearn.model import SKLearnModel
   from sagemaker import get_execution_role, Session

   # Setup
   sagemaker_session = Session()
   role = get_execution_role()
   model_artifact_uri = "s3://blossom-analytics-safe-dev-nv/safe_txns/similarity/endpoint/v2/model.tar.gz"

   # Create and deploy
   sk_model = SKLearnModel(
       model_data=model_artifact_uri,
       role=role,
       entry_point="inference_rules.py",
       source_dir="endpoint",
       framework_version="1.2-1",
       sagemaker_session=sagemaker_session
   )
   
   predictor = sk_model.deploy(
       initial_instance_count=1,
       instance_type="ml.m5.large",
       endpoint_name="data-safe-txns-endpoint"
   )
   ```

4. **Wait for deployment**
   - Notebook shows progress
   - ~5-10 minutes to reach `InService` status

5. **Verify**
   ```python
   # In notebook
   predictor.predict(...)  # Test with sample data
   ```

---

## Method 2: CLI Deployment (Alternative)

### Prerequisites

```bash
# 1. Authenticate with AWS SSO
aws sso login --sso-session blossom

# 2. Verify credentials
aws s3 ls s3://blossom-analytics-safe-dev-nv/ --profile blossom-dev
```

### Deployment

```bash
# 1. Navigate to repo
cd /path/to/safe_txns_sim_endpoint

# 2. Run deploy script
python3 deploy/deploy_final.py
```

### What the script does

1. **Downloads model artifacts from S3**
   - `kmeans_model.joblib` (0.54 MB)
   - `preprocessing_pipeline.joblib` (0.01 MB)
   - `centroids.csv` (0.00 MB)

2. **Creates tarball with code + artifacts**
   - Python modules (`inference_rules.py`, etc.)
   - Model files
   - Dependencies (`requirements.txt`)

3. **Uploads to S3**
   - `s3://blossom-analytics-safe-dev-nv/safe_txns/similarity/endpoint/v2/model.tar.gz`

4. **Deploys to SageMaker**
   - Instance: `ml.m5.large`
   - Framework: SKLearn 1.2-1
   - Endpoint: `data-safe-txns-endpoint`

5. **Waits for InService status**
   - Polls every 30 seconds
   - Timeout: 10 minutes

### Troubleshooting CLI Deployment

**Error: "Could not access model data"**
→ The SageMaker execution role lacks S3 permissions. Use the notebook method instead.

**Error: "FileNotFoundError: kmeans_model.joblib"**
→ Model artifact not found in S3. Check S3 paths are correct.

**Error: "ModuleNotFoundError"**
→ Missing Python dependency. Check `endpoint/requirements.txt`.

---

## What Gets Deployed

### Container Image
- **Framework**: scikit-learn 1.2-1 (CPU)
- **Python**: 3.9
- **Base Image**: `683313688378.dkr.ecr.us-east-1.amazonaws.com/sagemaker-scikit-learn:1.2-1-cpu-py3`

### Artifacts
- `kmeans_model.joblib` — Trained K-Means clustering model
- `preprocessing_pipeline.joblib` — Feature preprocessing pipeline
- `centroids.csv` — K-Means cluster centroids

### Code
- `inference_rules.py` — Main inference entry point
- `similarity_matcher.py` — Exact field matching (56 fields)
- `schema_validator.py` — Input validation
- `statistical_rules.py` — Risk rules v8

### Configuration
- `requirements.txt` — Python dependencies (pyathena, python-dateutil, pyarrow, boto3)
- Environment variables for Athena integration

---

## Testing After Deployment

### AWS Console Verification

1. AWS Console → SageMaker → Endpoints
2. Find `data-safe-txns-endpoint`
3. Verify Status: `InService`
4. Copy Endpoint ARN

### Local Test

```bash
# Test with sample CSV
python3 tests/process_endpoint.py \
  --input data/test_escenarios.csv \
  --output results.csv \
  --profile blossom-dev

# Verify output has sim_* columns:
# sim_match_txn_id, sim_score, sim_status, sim_decision
```

### CloudWatch Logs

1. AWS Console → CloudWatch → Log Groups
2. Find `/aws/sagemaker/Endpoints/data-safe-txns-endpoint`
3. Check for errors in AllTraffic log stream
4. Search for `[SIMILARITY]` to see matching results

---

## Rollback

If deployment fails, the previous endpoint version remains active.

To revert to previous version:
```bash
aws sagemaker update-endpoint-weights-and-capacities \
  --endpoint-name data-safe-txns-endpoint \
  --desired-weights-and-capacities VariantName=AllTraffic,DesiredWeight=0
```

---

## Performance Notes

### Deployment Time
- Model artifact download: ~30 seconds
- Tarball creation: ~10 seconds
- S3 upload: ~20 seconds
- SageMaker deployment: ~5-10 minutes
- **Total**: ~10 minutes

### Endpoint Startup
- Container initialization: ~1-2 minutes
- Model loading: ~30 seconds
- Ready for inference: ~2-3 minutes after `InService` status

### Cold Start
- First prediction: ~5 seconds (model warming up)
- Subsequent predictions: ~0.5-1 second

---

## Related Documentation

- [Exact Matching Guide](./EXACT_MATCHING.md)
- [Endpoint Input Format](../references/ENDPOINT_INPUT_FORMAT.md)
- [Graceful Degradation](../references/GRACEFUL_DEGRADATION.md)
- [Deployment Scripts](../../deploy/README.md)
