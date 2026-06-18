# SageMaker Model Packaging: Why Tarball?

## Why SageMaker Uses Tarball Format

### The Standard
SageMaker expects models packaged as `.tar.gz` (gzipped tarball) for several reasons:

1. **Container Initialization**
   - SageMaker downloads the tarball from S3
   - Extracts it to `/opt/ml/model/` inside the container
   - Your code and model files are available at this path

2. **Multi-file Models**
   - A model often has multiple files (code, weights, configs, etc.)
   - Tarball is a single S3 object (efficient)
   - Individual files would require multiple S3 downloads

3. **Atomic Operations**
   - Download tarball → Extract → Model ready
   - All files are guaranteed to be present together
   - No partial/incomplete model states

4. **Standardization**
   - Works across all SageMaker container types (SKLearn, PyTorch, TensorFlow, etc.)
   - Documented format that tools expect
   - Same interface for all frameworks

---

## Our Tarball Structure

For this endpoint, the tarball contains:

```
model.tar.gz
├── inference_rules.py              (Entry point)
├── similarity_matcher.py           (Athena similarity)
├── schema_validator.py             (Input validation)
├── statistical_rules.py            (Risk rules v8)
├── requirements.txt                (Dependencies)
│
├── kmeans_model.joblib             (K-Means model ~0.54 MB)
├── preprocessing_pipeline.joblib   (Feature preprocessing)
├── centroids.csv                   (Cluster centroids)
├── selected_features.csv           (Feature selection)
└── kmeans_artifacts.json           (K-Means metadata)
```

**Total size**: ~0.11 MB (mostly code, compressed)

---

## SageMaker Container Initialization Flow

```
1. S3 Download
   model.tar.gz → /opt/ml/code/model.tar.gz

2. Extract
   tar -xzf /opt/ml/code/model.tar.gz -C /opt/ml/model/

3. Structure After Extract
   /opt/ml/model/
   ├── inference_rules.py
   ├── kmeans_model.joblib
   ├── ...

4. Python Code Loading
   model_fn(model_dir="/opt/ml/model/")
   
   Your code reads files from model_dir:
   - joblib.load(os.path.join(model_dir, "kmeans_model.joblib"))
   - pd.read_csv(os.path.join(model_dir, "centroids.csv"))
```

---

## Alternatives & Trade-offs

### Alternative 1: S3 as Model Store (Direct)
Download model files directly from S3 inside `model_fn()`:

```python
def model_fn(model_dir):
    s3 = boto3.client('s3')
    s3.download_file('bucket', 'path/to/kmeans_model.joblib', '/tmp/model.joblib')
    model = joblib.load('/tmp/model.joblib')
    return model
```

**Pros**:
- ✓ More flexible (change model without re-deploying)
- ✓ Smaller endpoint artifact

**Cons**:
- ✗ Every endpoint restart re-downloads model (slower cold start)
- ✗ Requires S3 permissions inside endpoint
- ✗ Model can change mid-deployment (version control issue)
- ✗ More complex error handling

### Alternative 2: ECR Custom Container
Bake the model directly into the Docker image:

```dockerfile
FROM python:3.9
COPY kmeans_model.joblib /opt/ml/model/
COPY inference_rules.py /opt/ml/code/
```

**Pros**:
- ✓ Fastest cold start (model already in image)
- ✓ No S3 dependency
- ✓ Simplest deployment

**Cons**:
- ✗ Large Docker images (~1-2 GB)
- ✗ Longer image builds
- ✗ Hard to version models separately from code
- ✗ Requires custom Docker setup

### Alternative 3: Mounted EBS Volume
Store model on persistent EBS volume:

**Pros**:
- ✓ Fast access (local storage)
- ✓ Can update model without re-deploy

**Cons**:
- ✗ Manual setup
- ✗ Not standard SageMaker practice
- ✗ Hard to reproduce in other AWS accounts

---

## Why Tarball is Best for Us

✅ **Standard SageMaker format**
- No custom setup needed
- Clear separation: code + model files
- Works with notebooks, CLI, CloudFormation

✅ **Clear versioning**
- Each deploy gets a new tarball version
- Model and code versions are locked together
- Easy rollback if needed

✅ **Efficient**
- Single S3 object to download
- Compressed (~0.11 MB)
- Standard SageMaker tooling works out-of-the-box

✅ **Reproducible**
- Same tarball can be deployed to multiple accounts
- Same tarball can be re-deployed anytime
- Easy to test locally (extract, run model_fn)

✅ **Security**
- No extra S3 access needed inside endpoint
- Model and code travel together
- Audit trail: who deployed which tarball

---

## Local Testing of Tarball

You can test the tarball structure locally:

```bash
# Extract
tar -xzf model_with_exact_matching.tar.gz -C /tmp/test_model

# Verify structure
ls -la /tmp/test_model

# Test model_fn directly
python3 << 'EOF'
import sys
sys.path.insert(0, '/tmp/test_model')
from inference_rules import model_fn

model = model_fn('/tmp/test_model')
print("✓ Model loaded successfully")
print(f"K-Means clusters: {model.n_clusters}")
EOF
```

---

## Deployment Timeline

| Method | Cold Start | Model Update | Flexibility |
|--------|-----------|---|---|
| **Tarball (Current)** | ~2-3 min | Full re-deploy | Medium |
| **S3 Direct** | ~4-5 min | Fast (hot-patch) | High |
| **Custom ECR** | ~1-2 min | Re-build image | Low |
| **EBS Volume** | ~1 min | Fast (update vol) | High |

---

## Conclusion

**Tarball is the right choice** because:
1. ✓ Standard SageMaker practice
2. ✓ Good balance of simplicity + flexibility
3. ✓ Clear versioning and auditing
4. ✓ No custom infrastructure needed
5. ✓ Works with SageMaker Notebook directly

If you needed **faster model updates** or **dynamic model switching**, you'd use S3 Direct or EBS.
If you needed **fastest cold start**, you'd use custom ECR.

But for **reliable, reproducible, auditable deployments**, tarball is best.

---

## References

- [SageMaker Model Format](https://docs.aws.amazon.com/sagemaker/latest/dg/your-algorithms-training-algo.html)
- [SKLearn Containers](https://sagemaker.readthedocs.io/en/stable/using_sklearn.html)
- [Model Artifacts](https://docs.aws.amazon.com/sagemaker/latest/dg/model-registry-details.html)
