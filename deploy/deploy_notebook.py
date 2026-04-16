import json

# Read the notebook
with open('safe-txn-enpoint.ipynb', 'r') as f:
    notebook = json.load(f)

# Create a simplified deployment script based on notebook
deploy_code = '''
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
    framework_version="1.2-1",
    py_version="py3",
    env={
        "SIMILARITY_THRESHOLD": "0.90",
        "SIMILARITY_S3_BUCKET": "blossom-analytics-safe-dev-nv",
        "SIMILARITY_S3_KEY": "safe_txns/data/similarity/SafeTransactionResults.csv",
    }
)

print(f"\\n📦 Model data: {model_data}")
print(f"🔧 Entry point: inference_rules.py")
print(f"🌐 Endpoint: {endpoint_name}")

# Deploy
print(f"\\n⏳ Deploying endpoint (this takes 5-8 minutes)...\\n")

predictor = sklearn_model.deploy(
    initial_instance_count=1,
    instance_type="ml.m5.large",
    endpoint_name=endpoint_name
)

print(f"\\n✅ ENDPOINT DEPLOYED SUCCESSFULLY!")
print(f"\\n📍 Endpoint: {endpoint_name}")
print("="*80)
'''

with open('deploy_with_sdk.py', 'w') as f:
    f.write(deploy_code)

print("✓ Created deploy_with_sdk.py")
