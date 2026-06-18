# Deployment Guide

## Architecture

The endpoint runs as a SageMaker SKLearn container. All endpoint code and model artifacts are packaged into a single tarball (`model.tar.gz`) stored in S3. On startup, SageMaker extracts the tarball and runs `endpoint/inference_rules.py` as the entry point.

**Tarball location**:
```
s3://blossom-analytics-safe-dev-nv/safe_txns/similarity/endpoint/v2/model.tar.gz
```

**Endpoint**: `SAFE_TXNS_ENDPOINT_DEV`  
**Region**: `us-east-1` (dev account)  
**Instance**: `ml.m5.large`  
**Framework**: `SKLearn 1.2-1`

---

## Step 1: Build the Tarball (when code changes)

Run from the SageMaker Studio notebook `safe-txn-enpoint.ipynb`, cells **Step 1** and **Step 2**.

What these cells do:

1. Download model artifacts from S3:
   - `output/kmeans/kmeans_analysis/artifact/kmeans_model.joblib`
   - `output/preprocessing/preprocessing_pipeline.joblib`
   - `output/feature_selection/selected_features.csv`
   - `output/kmeans/centroids/centroids.csv`
   - `output/kmeans/kmeans_analysis/artifact/kmeans_artifacts.json`

2. Copy endpoint code files:
   - `endpoint/inference_rules.py`
   - `endpoint/similarity_matcher.py`
   - `endpoint/schema_validator.py`
   - `endpoint/statistical_rules.py`
   - `endpoint/requirements.txt`

3. Package everything into `model.tar.gz` with the required SageMaker directory structure:
   ```
   model.tar.gz
   ├── inference_rules.py       (entry point)
   ├── similarity_matcher.py
   ├── schema_validator.py
   ├── statistical_rules.py
   ├── requirements.txt
   ├── kmeans_model.joblib
   ├── preprocessing_pipeline.joblib
   ├── selected_features.csv
   ├── centroids.csv
   └── kmeans_artifacts.json
   ```

4. Upload the tarball to S3:
   ```
   s3://blossom-analytics-safe-dev-nv/safe_txns/similarity/endpoint/v2/model.tar.gz
   ```

---

## Step 2: Deploy from SageMaker Notebook

**Must be done from SageMaker Studio — not from local CLI.**

1. Open SageMaker Studio in the dev AWS account (us-east-1)
2. Open `safe-txn-enpoint.ipynb`
3. Run cells in **Step 3** (deploy):

```python
from sagemaker.sklearn.model import SKLearnModel

sk_model = SKLearnModel(
    model_data="s3://blossom-analytics-safe-dev-nv/safe_txns/similarity/endpoint/v2/model.tar.gz",
    role=role,                          # SageMaker execution role (from notebook context)
    entry_point="inference_rules.py",
    framework_version="1.2-1",
    env={
        "SIMILARITY_ATHENA_DATABASE": "dlh_silver_safe_alpha",
        "SIMILARITY_ATHENA_TABLE": "safetransactionresults",
        "SIMILARITY_ATHENA_REGION": "us-east-2",
        "SIMILARITY_ATHENA_S3_STAGING_DIR": "s3://blossom-analytics-alpha-nv/athena-results/",
        "SIMILARITY_ATHENA_WORKGROUP": "primary",
        "ATHENA_TIMEOUT_SECONDS": "10",
    }
)

predictor = sk_model.deploy(
    initial_instance_count=1,
    instance_type="ml.m5.large",
    endpoint_name="SAFE_TXNS_ENDPOINT_DEV",
)
```

Deployment takes **5–10 minutes**. Monitor via:

```python
sm = boto3.client("sagemaker", region_name="us-east-1")
r = sm.describe_endpoint(EndpointName="SAFE_TXNS_ENDPOINT_DEV")
print(r["EndpointStatus"])  # InService when ready
```

---

## Why Not Local CLI

Deploying from a local machine fails because:

1. The SageMaker execution role is an IAM role with a trust policy that only allows the `sagemaker.amazonaws.com` service principal to assume it.
2. When deploying from a local machine with an IAM user/SSO role, SageMaker cannot assume the execution role on your behalf to pull the model tarball from S3.
3. The SageMaker notebook runs inside the AWS account with instance profile credentials that already have the correct trust relationship.

---

## Environment Variables

Set at deploy time via the `env` dict in `SKLearnModel`:

| Variable | Description | Default |
|---|---|---|
| `SIMILARITY_ATHENA_DATABASE` | Athena database name | `dlh_silver_safe_alpha` |
| `SIMILARITY_ATHENA_TABLE` | Athena table name | `safetransactionresults` |
| `SIMILARITY_ATHENA_REGION` | AWS region for Athena | `us-east-2` |
| `SIMILARITY_ATHENA_S3_STAGING_DIR` | S3 path for Athena query results | `s3://blossom-analytics-alpha-nv/athena-results/` |
| `SIMILARITY_ATHENA_WORKGROUP` | Athena workgroup | `primary` |
| `ATHENA_TIMEOUT_SECONDS` | Max seconds to wait for Athena query | `10` |
| `DISABLE_RULES` | Set to `1` to skip statistical rules | unset |

---

## Cross-Account Athena

The endpoint runs in the **dev account** (us-east-1) but queries Athena in the **alpha account** (us-east-2).

Requirements:

1. The SageMaker execution role (dev account) must have permission to call Athena in the alpha account.
2. The Athena S3 staging bucket (`blossom-analytics-alpha-nv`) must grant write access to the dev execution role.
3. The Glue catalog in the alpha account must grant read access to the dev execution role.

If cross-account access breaks (e.g. role rotation), all `sim_*` fields will be `null` and CloudWatch logs will show an Athena authorization error.

---

## Update Existing Endpoint (Zero Downtime)

To update only the model/code without deleting the endpoint:

```python
# 1. Create a new model object with the updated tarball
new_model = sk_model.create(...)

# 2. Create a new endpoint config pointing to new model
sm.create_endpoint_config(
    EndpointConfigName="SAFE_TXNS_ENDPOINT_DEV-v2",
    ProductionVariants=[{
        "VariantName": "AllTraffic",
        "ModelName": new_model_name,
        "InitialInstanceCount": 1,
        "InstanceType": "ml.m5.large",
    }]
)

# 3. Update the endpoint (blue/green deployment, no downtime)
sm.update_endpoint(
    EndpointName="SAFE_TXNS_ENDPOINT_DEV",
    EndpointConfigName="SAFE_TXNS_ENDPOINT_DEV-v2",
)
```

---

## Delete Endpoint

Run the delete cell in `safe-txn-enpoint.ipynb`, or:

```python
import boto3
sm = boto3.client("sagemaker", region_name="us-east-1")
sm.delete_endpoint(EndpointName="SAFE_TXNS_ENDPOINT_DEV")
sm.delete_endpoint_config(EndpointConfigName="SAFE_TXNS_ENDPOINT_DEV")
```

This stops billing immediately. The model artifacts in S3 are not deleted.
