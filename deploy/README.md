# Deployment Scripts

Scripts for packaging and deploying the SageMaker endpoint.

## Quick Start

```bash
# Deploy the endpoint with latest code
python3 deploy/deploy_final.py
```

## Scripts

### `deploy_final.py` (Recommended)

**Purpose**: Deploy endpoint with updated code from local repository.

**What it does**:
1. Creates `model.tar.gz` tarball from local `endpoint/*.py` files
2. Uploads tarball to S3
3. Deploys to SageMaker using SKLearnModel

**Usage**:
```bash
python3 deploy/deploy_final.py
```

**Output**: Prints deployment status and endpoint URL

**Requirements**:
- AWS SSO authenticated (`aws sso login --sso-session blossom`)
- SageMaker role configured

---

### `deploy_with_sdk.py` (Legacy)

**Purpose**: Deploy from existing S3 model tarball.

**Usage**:
```bash
python3 deploy/deploy_with_sdk.py
```

**Note**: Uses hardcoded S3 path. Update before using.

---

### `deploy_similarity_endpoint.py` (Full Pipeline)

**Purpose**: Complete deployment pipeline with artifact download.

**Steps**:
1. Downloads K-Means model artifacts from S3
2. Creates tarball with artifacts + code
3. Uploads to S3
4. Creates SageMaker model and endpoint

**Usage**:
```bash
python3 deploy/deploy_similarity_endpoint.py
```

**Requirements**:
- Model artifacts must exist in S3
- More complex setup

---

### `deploy_notebook.py` (Utility)

**Purpose**: Extract deployment code from SageMaker notebook.

**Usage** (rare):
```bash
python3 deploy/deploy_notebook.py safe-txn-enpoint.ipynb
```

---

## Configuration

### AWS Profile
All scripts use `profile_name='blossom-dev'` by default.

To use a different profile, edit the script:
```python
session = boto3.Session(profile_name='your-profile-name', region_name='us-east-1')
```

### SageMaker Configuration

**Endpoint Name**: `SAFE_TXNS_ENDPOINT_DEV` (hardcoded)
**Instance Type**: `ml.m5.large`
**Framework**: SKLearn 1.2-1 (CPU)
**Region**: us-east-1

To change these, edit the script variables at the top.

### S3 Paths

**Code Upload Path**: `s3://blossom-analytics-safe-dev-nv/safe_txns/similarity/endpoint/v2/model.tar.gz`

To change, edit `BUCKET` and `MODEL_PREFIX` variables.

---

## Deployment Checklist

- [ ] AWS SSO authenticated: `aws sso login --sso-session blossom`
- [ ] Code changes committed: `git status` shows clean
- [ ] Tests pass locally: `pytest tests/`
- [ ] Ready to deploy: `python3 deploy/deploy_final.py`
- [ ] Wait 5-10 minutes for endpoint to be `InService`
- [ ] Test endpoint: `python3 tests/process_endpoint.py --input data/test_escenarios.csv`

---

## Troubleshooting

### "Must setup local AWS configuration"
→ Run `aws sso login --sso-session blossom` first

### "Could not access model data at S3..."
→ Check IAM role has S3 permissions (`s3:GetObject`, `s3:ListBucket`)

### "Endpoint creation failed"
→ Check CloudWatch logs: AWS Console → CloudWatch → Log Groups → `/aws/sagemaker/Endpoints/SAFE_TXNS_ENDPOINT_DEV`

### "Timeout waiting for endpoint to be InService"
→ Endpoint may still be updating. Check AWS Console → SageMaker → Endpoints → SAFE_TXNS_ENDPOINT_DEV

---

## Related Documentation

- Deployment guide: `docs/codemap/02-deploy/README.md`
- Testing guide: `tests/README.md`
- Architecture: `docs/codemap/00-overview/Architecture.md`
