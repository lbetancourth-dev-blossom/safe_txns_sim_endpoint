#!/usr/bin/env python3
"""
Deploy SageMaker endpoint with similarity matching integration.
Based on safe-txn-enpoint.ipynb workflow.
"""
import boto3
import tarfile
import os
import time
from datetime import datetime

# Configuration
ENDPOINT_NAME = "safe-txn-similarity-endpoint"
MODEL_NAME = f"safe-txn-similarity-model-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
BUCKET = "blossom-analytics-safe-dev-nv"
S3_MODEL_PREFIX = "safe_txns/models/similarity"
LOCAL_TAR_PATH = "model_with_similarity.tar.gz"

# S3 paths for artifacts (from existing deployment)
ARTIFACTS_S3_PREFIX = "safe_txns/model_artifacts"
ARTIFACTS = [
    "kmeans_model.joblib",
    "preprocessing_pipeline.joblib", 
    "selected_features.csv",
    "centroids.csv",
    "kmeans_artifacts.json"
]

# Local code files to include
CODE_FILES = [
    "endpoint/inference_rules.py",
    "endpoint/similarity_matcher.py",
    "endpoint/schema_validator.py",
    "endpoint/statistical_rules.py",
    "endpoint/requirements.txt",
]

print("="*80)
print("DEPLOYING SAFE TRANSACTIONS SIMILARITY ENDPOINT")
print("="*80)

# Initialize clients with SSO profile
session = boto3.Session(profile_name='blossom-dev', region_name='us-east-1')
s3 = session.client('s3')
sm = session.client('sagemaker')

# Step 1: Download artifacts from S3
print("\n📥 Step 1: Downloading model artifacts from S3...")
os.makedirs("temp_artifacts", exist_ok=True)

for artifact in ARTIFACTS:
    s3_key = f"{ARTIFACTS_S3_PREFIX}/{artifact}"
    local_path = f"temp_artifacts/{artifact}"
    
    try:
        print(f"  Downloading {artifact}...")
        s3.download_file(BUCKET, s3_key, local_path)
        print(f"  ✓ {artifact} downloaded")
    except Exception as e:
        print(f"  ✗ Error downloading {artifact}: {e}")
        raise

# Step 2: Create model.tar.gz with artifacts + code
print("\n📦 Step 2: Creating model.tar.gz with similarity code...")

with tarfile.open(LOCAL_TAR_PATH, "w:gz") as tar:
    # Add model artifacts
    print("  Adding artifacts:")
    for artifact in ARTIFACTS:
        local_path = f"temp_artifacts/{artifact}"
        tar.add(local_path, arcname=artifact)
        print(f"    ✓ {artifact}")
    
    # Add code files to root of tarball (SageMaker expects them in /)
    print("  Adding code files:")
    for code_file in CODE_FILES:
        if os.path.exists(code_file):
            arcname = os.path.basename(code_file)
            tar.add(code_file, arcname=arcname)
            print(f"    ✓ {code_file} -> {arcname}")
        else:
            print(f"    ✗ Warning: {code_file} not found")

tar_size = os.path.getsize(LOCAL_TAR_PATH) / (1024 * 1024)
print(f"\n  ✓ Created {LOCAL_TAR_PATH} ({tar_size:.2f} MB)")

# Step 3: Upload model.tar.gz to S3
print(f"\n📤 Step 3: Uploading model.tar.gz to S3...")
model_s3_key = f"{S3_MODEL_PREFIX}/model.tar.gz"
model_s3_uri = f"s3://{BUCKET}/{model_s3_key}"

s3.upload_file(LOCAL_TAR_PATH, BUCKET, model_s3_key)
print(f"  ✓ Uploaded to {model_s3_uri}")

# Step 4: Create SageMaker Model
print(f"\n🚀 Step 4: Creating SageMaker model...")

ROLE_ARN = "arn:aws:iam::436631265256:role/service-role/AmazonSageMaker-ExecutionRole-20241029T103557"

# Create model using boto3
model_response = sm.create_model(
    ModelName=MODEL_NAME,
    PrimaryContainer={
        'Image': '683313688378.dkr.ecr.us-east-1.amazonaws.com/sagemaker-scikit-learn:1.2-1-cpu-py3',
        'ModelDataUrl': model_s3_uri,
        'Environment': {
            'SAGEMAKER_PROGRAM': 'inference_rules.py',
            'SAGEMAKER_SUBMIT_DIRECTORY': model_s3_uri,
            # Similarity Athena configuration (DATA-1264: Athena is sole source)
            'SIMILARITY_THRESHOLD': '0.90',
            'SIMILARITY_ATHENA_DATABASE': 'dlh_silver_safe_alpha',
            'SIMILARITY_ATHENA_TABLE': 'safetransactionresults',
            'SIMILARITY_ATHENA_S3_STAGING': 's3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/',
            'SIMILARITY_ATHENA_REGION': 'us-east-2',
            'ATHENA_WINDOW_MONTHS': '6',
            'ATHENA_TIMEOUT_SECONDS': '10',
        }
    },
    ExecutionRoleArn=ROLE_ARN
)

print(f"  ✓ Model created: {MODEL_NAME}")

# Step 5: Create Endpoint Configuration
ENDPOINT_CONFIG_NAME = f"{ENDPOINT_NAME}-config-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
print(f"\n⚙️  Step 5: Creating endpoint configuration...")

config_response = sm.create_endpoint_config(
    EndpointConfigName=ENDPOINT_CONFIG_NAME,
    ProductionVariants=[
        {
            'VariantName': 'AllTraffic',
            'ModelName': MODEL_NAME,
            'InitialInstanceCount': 1,
            'InstanceType': 'ml.m5.large',
            'InitialVariantWeight': 1
        }
    ]
)

print(f"  ✓ Endpoint config created: {ENDPOINT_CONFIG_NAME}")

# Step 6: Create/Deploy Endpoint
print(f"\n🌐 Step 6: Deploying endpoint '{ENDPOINT_NAME}'...")
print("  This will take 5-8 minutes...")
print(f"  Instance type: ml.m5.large")
print(f"  Initial instance count: 1")

try:
    # Check if endpoint already exists
    try:
        endpoint_desc = sm.describe_endpoint(EndpointName=ENDPOINT_NAME)
        print(f"\n  ⚠️  Endpoint '{ENDPOINT_NAME}' already exists with status: {endpoint_desc['EndpointStatus']}")
        print(f"  Updating existing endpoint with new model...")
        
        # Update endpoint
        sm.update_endpoint(
            EndpointName=ENDPOINT_NAME,
            EndpointConfigName=ENDPOINT_CONFIG_NAME
        )
        print(f"  ✓ Endpoint update initiated")
        
    except sm.exceptions.ClientError as e:
        if 'Could not find endpoint' in str(e):
            # Create new endpoint
            sm.create_endpoint(
                EndpointName=ENDPOINT_NAME,
                EndpointConfigName=ENDPOINT_CONFIG_NAME
            )
            print(f"  ✓ Endpoint creation initiated")
        else:
            raise
    
    # Wait for endpoint to be in service
    print(f"\n  ⏳ Waiting for endpoint to be in service...")
    waiter = sm.get_waiter('endpoint_in_service')
    waiter.wait(
        EndpointName=ENDPOINT_NAME,
        WaiterConfig={'Delay': 30, 'MaxAttempts': 20}
    )
    
    print(f"\n✅ Endpoint deployed successfully!")
    print(f"  Endpoint name: {ENDPOINT_NAME}")
    print(f"  Model name: {MODEL_NAME}")
    print(f"  Config name: {ENDPOINT_CONFIG_NAME}")
    
except Exception as e:
    print(f"\n❌ Deployment failed: {e}")
    raise

# Cleanup
print("\n🧹 Cleaning up temporary files...")
import shutil
shutil.rmtree("temp_artifacts")
os.remove(LOCAL_TAR_PATH)
print("  ✓ Cleanup complete")

print("\n" + "="*80)
print("DEPLOYMENT COMPLETE")
print("="*80)
print(f"\nEndpoint: {ENDPOINT_NAME}")
print(f"Model: {MODEL_NAME}")
print(f"S3 Model: {model_s3_uri}")
print("\nEnvironment Variables:")
print(f"  SIMILARITY_THRESHOLD=0.90")
print(f"  SIMILARITY_S3_BUCKET={BUCKET}")
print(f"  SIMILARITY_S3_KEY=safe_txns/similarity/data/SafeTransactionResults/")
print("\nTest with:")
print(f"  aws sagemaker-runtime invoke-endpoint --endpoint-name {ENDPOINT_NAME} \\")
print(f"    --content-type text/csv --body file://test_data.csv output.json")
print("="*80)
