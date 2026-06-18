#!/usr/bin/env python3
"""
Simple endpoint deployment script.
Creates tarball from local code, uploads to S3, deploys with SageMaker SDK.
"""
import tarfile
import os
import boto3
import time
from datetime import datetime

# Configuration
ENDPOINT_NAME = "data-safe-txns-endpoint"
BUCKET = "blossom-analytics-safe-dev-nv"
MODEL_PREFIX = "safe_txns/similarity/endpoint/v2"
LOCAL_TAR = "model_with_exact_matching.tar.gz"
CODE_FILES = [
    "endpoint/inference_rules.py",
    "endpoint/similarity_matcher.py",
    "endpoint/schema_validator.py",
    "endpoint/statistical_rules.py",
    "endpoint/requirements.txt",
]

print("=" * 80)
print("DEPLOYING SAFE TRANSACTIONS ENDPOINT WITH EXACT FIELD MATCHING")
print("=" * 80)

# Create tarball locally
print(f"\n📦 Step 1: Creating {LOCAL_TAR}...")
os.makedirs("temp_artifacts", exist_ok=True)

try:
    with tarfile.open(LOCAL_TAR, "w:gz") as tar:
        for code_file in CODE_FILES:
            if os.path.exists(code_file):
                arcname = os.path.basename(code_file)
                tar.add(code_file, arcname=arcname)
                print(f"  ✓ Added {code_file}")
            else:
                print(f"  ✗ Warning: {code_file} not found")

    tar_size = os.path.getsize(LOCAL_TAR) / (1024 * 1024)
    print(f"  ✓ Created {LOCAL_TAR} ({tar_size:.2f} MB)")
except Exception as e:
    print(f"  ✗ Error creating tarball: {e}")
    raise

# Upload to S3
print(f"\n📤 Step 2: Uploading to S3...")
session = boto3.Session(profile_name='blossom-dev', region_name='us-east-1')
s3 = session.client('s3')

s3_key = f"{MODEL_PREFIX}/model.tar.gz"
model_s3_uri = f"s3://{BUCKET}/{s3_key}"

try:
    s3.upload_file(LOCAL_TAR, BUCKET, s3_key)
    print(f"  ✓ Uploaded to {model_s3_uri}")
except Exception as e:
    print(f"  ✗ Error uploading: {e}")
    raise

# Deploy with SageMaker SDK
print(f"\n🚀 Step 3: Deploying endpoint...")

from sagemaker.sklearn.model import SKLearnModel
from sagemaker.session import Session

role = "arn:aws:iam::436631265256:role/service-role/AmazonSageMaker-ExecutionRole-20241029T103557"

# Create SageMaker session with correct profile
sagemaker_session = Session(
    boto_session=session,
    default_bucket=BUCKET
)

sklearn_model = SKLearnModel(
    model_data=model_s3_uri,
    role=role,
    entry_point="inference_rules.py",
    source_dir="endpoint",
    framework_version="1.2-1",
    py_version="py3",
    sagemaker_session=sagemaker_session,
    env={
        "SIMILARITY_THRESHOLD": "0.90",
        "SIMILARITY_ATHENA_DATABASE": "dlh_silver_safe_alpha",
        "SIMILARITY_ATHENA_TABLE": "safetransactionresults",
        "SIMILARITY_ATHENA_S3_STAGING": "s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/",
        "SIMILARITY_ATHENA_REGION": "us-east-2",
        "ATHENA_WINDOW_MONTHS": "6",
        "ATHENA_TIMEOUT_SECONDS": "10",
    }
)

try:
    print(f"  Deploying {ENDPOINT_NAME}...")
    print(f"  Model URI: {model_s3_uri}")
    predictor = sklearn_model.deploy(
        initial_instance_count=1,
        instance_type="ml.m5.large",
        endpoint_name=ENDPOINT_NAME,
        wait=True
    )
    print(f"\n✅ DEPLOYMENT SUCCESSFUL!")
    print(f"  Endpoint: {ENDPOINT_NAME}")
    print(f"  Status: InService")
    print(f"  Instance: ml.m5.large")
except Exception as e:
    print(f"  ✗ Deployment error: {e}")
    raise

# Cleanup
print(f"\n🧹 Cleaning up...")
try:
    os.remove(LOCAL_TAR)
    print(f"  ✓ Removed {LOCAL_TAR}")
except:
    pass

print("\n" + "=" * 80)
print("DEPLOYMENT COMPLETE")
print("=" * 80)
