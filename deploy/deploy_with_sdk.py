
import sagemaker
from sagemaker.sklearn.model import SKLearnModel

# Configuration
model_data = "s3://blossom-analytics-safe-dev-nv/output/kmeans-similarity-endpoint/model.tar.gz"
role = "arn:aws:iam::436631265256:role/service-role/AmazonSageMaker-ExecutionRole-20241029T103557"
endpoint_name = "safe-txn-similarity-endpoint"

print("="*80)
print("DEPLOYING ENDPOINT WITH SAGEMAKER SDK")
print("="*80)

# Create SKLearn Model
sklearn_model = SKLearnModel(
    model_data=model_data,
    role=role,
    entry_point="inference_rules.py",
    source_dir="endpoint",
    framework_version="1.2-1",
    py_version="py3",
    env={
        "SIMILARITY_THRESHOLD": "0.90",
        # DEPRECATED (D2): SIMILARITY_S3_BUCKET and SIMILARITY_S3_KEY removed — Athena is now the only source
        # Athena env vars (D2 closed — single-source, NO USE_ATHENA toggle)
        "SIMILARITY_ATHENA_DATABASE": "dlh_silver_safe_alpha",
        "SIMILARITY_ATHENA_TABLE": "safetransactionresults",
        "SIMILARITY_ATHENA_S3_STAGING": "s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/",
        "SIMILARITY_ATHENA_REGION": "us-east-2",
        "ATHENA_WINDOW_MONTHS": "6",
        "ATHENA_TIMEOUT_SECONDS": "10",
    }
)

print(f"\n📦 Model data: {model_data}")
print(f"🔧 Entry point: inference_rules.py")
print(f"🌐 Endpoint: {endpoint_name}")

# Deploy
print(f"\n⏳ Deploying endpoint (this takes 5-8 minutes)...\n")

predictor = sklearn_model.deploy(
    initial_instance_count=1,
    instance_type="ml.m5.large",
    endpoint_name=endpoint_name
)

print(f"\n✅ ENDPOINT DEPLOYED SUCCESSFULLY!")
print(f"\n📍 Endpoint: {endpoint_name}")
print("="*80)
