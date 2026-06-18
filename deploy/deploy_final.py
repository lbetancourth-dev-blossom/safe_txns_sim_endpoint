#!/usr/bin/env python3
"""
Deploy SageMaker endpoint with code and model artifacts.
Downloads model from S3, creates tarball, deploys with SageMaker SDK.
"""
import tarfile
import os
import boto3
import time
from datetime import datetime
from endpoint_config import (
    ENDPOINT_NAME, BUCKET, MODEL_S3_KEY, MODEL_S3_URI,
    ARTIFACT_S3_PATHS, ENDPOINT_ENV,
)

LOCAL_TAR = "model.tar.gz"

CODE_FILES = [
    "endpoint/inference_rules.py",
    "endpoint/similarity_matcher.py",
    "endpoint/schema_validator.py",
    "endpoint/statistical_rules.py",
    "endpoint/requirements.txt",
]

MODEL_ARTIFACTS = ARTIFACT_S3_PATHS

print("=" * 80)
print("DEPLOYING SAFE TRANSACTIONS ENDPOINT WITH EXACT FIELD MATCHING")
print("=" * 80)

# Initialize S3 client
session = boto3.Session(profile_name='blossom-dev', region_name='us-east-1')
s3 = session.client('s3')

# Step 1: Download model artifacts from S3
print(f"\n📥 Step 1: Downloading model artifacts from S3...")
os.makedirs("temp_artifacts", exist_ok=True)

for filename, s3_key in MODEL_ARTIFACTS.items():
    local_path = f"temp_artifacts/{filename}"
    try:
        print(f"  Downloading {filename}...")
        s3.download_file(BUCKET, s3_key, local_path)
        size = os.path.getsize(local_path) / (1024 * 1024)
        print(f"    ✓ Downloaded ({size:.2f} MB)")
    except Exception as e:
        print(f"    ✗ Error: {e}")
        print(f"    Tip: Check S3 path: s3://{BUCKET}/{s3_key}")
        raise

# Step 2: Create tarball with code + artifacts
print(f"\n📦 Step 2: Creating {LOCAL_TAR}...")

try:
    with tarfile.open(LOCAL_TAR, "w:gz") as tar:
        # Add code files to root of tarball
        print("  Adding code files:")
        for code_file in CODE_FILES:
            if os.path.exists(code_file):
                arcname = os.path.basename(code_file)
                tar.add(code_file, arcname=arcname)
                print(f"    ✓ {code_file}")
            else:
                print(f"    ✗ Warning: {code_file} not found")

        # Add model artifacts to root of tarball
        print("  Adding model artifacts:")
        for filename in MODEL_ARTIFACTS.keys():
            local_path = f"temp_artifacts/{filename}"
            if os.path.exists(local_path):
                tar.add(local_path, arcname=filename)
                print(f"    ✓ {filename}")
            else:
                print(f"    ✗ Missing: {filename}")
                raise FileNotFoundError(f"Model artifact not found: {filename}")

    tar_size = os.path.getsize(LOCAL_TAR) / (1024 * 1024)
    print(f"  ✓ Created {LOCAL_TAR} ({tar_size:.2f} MB)")
except Exception as e:
    print(f"  ✗ Error creating tarball: {e}")
    raise

# Step 3: Upload tarball to S3
print(f"\n📤 Step 3: Uploading tarball to S3...")

s3_key = f"{MODEL_PREFIX}/model.tar.gz"
model_s3_uri = f"s3://{BUCKET}/{s3_key}"

try:
    s3.upload_file(LOCAL_TAR, BUCKET, s3_key)
    print(f"  ✓ Uploaded to {model_s3_uri}")
except Exception as e:
    print(f"  ✗ Error uploading: {e}")
    raise

# Step 4: Deploy with SageMaker SDK
print(f"\n🚀 Step 4: Deploying endpoint...")

from sagemaker.sklearn.model import SKLearnModel
import sagemaker
from sagemaker import get_execution_role, Session

# Get execution role (from SageMaker Notebook environment or IAM)
try:
    role = get_execution_role()
    print(f"  Using execution role: {role}")
except:
    # Fallback to explicit role if not in SageMaker environment
    role = "arn:aws:iam::436631265256:role/service-role/AmazonSageMaker-ExecutionRole-20241029T103557"
    print(f"  Using explicit role: {role}")

# Create SageMaker session with correct profile
sagemaker_session = sagemaker.Session(
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
        **ENDPOINT_ENV,
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

# Step 5: Cleanup
print(f"\n🧹 Step 5: Cleaning up...")
try:
    os.remove(LOCAL_TAR)
    print(f"  ✓ Removed {LOCAL_TAR}")
except:
    pass

# Clean temp artifacts
try:
    import shutil
    shutil.rmtree("temp_artifacts")
    print(f"  ✓ Removed temp_artifacts/")
except:
    pass

print("\n" + "=" * 80)
print("DEPLOYMENT COMPLETE")
print("=" * 80)
