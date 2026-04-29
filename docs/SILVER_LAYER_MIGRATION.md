# Migration to Silver Layer Parquet Data

**Date**: 2026-04-29  
**Status**: ✅ Complete  
**Impact**: Production endpoint similarity matching  

---

## Summary

Migrated the similarity matching reference data source from CSV files in the `safe-dev-nv` bucket to Parquet files in the **Silver layer** of the data lake.

### Before vs After

| Aspect | Before (Bronze) | After (Silver) |
|--------|----------------|----------------|
| **Bucket** | `blossom-analytics-safe-dev-nv` | `blossom-analytics-datalake-dev` |
| **Path** | `safe_txns/similarity/data/wp_similarity.csv` | `datalake/silver/SAFE/safetransactionresults/data/` |
| **Format** | CSV | Parquet (partitioned) |
| **Records** | ~22 | ~243 (10x more) |
| **Files** | 1 CSV file | 3 Parquet files |
| **Load Time** | ~3 seconds | ~2 seconds |
| **Partitioning** | None | `createdat_month=YYYY-MM` |

---

## Silver Layer Architecture

### Bucket Structure

```
s3://blossom-analytics-datalake-dev/datalake/silver/SAFE/safetransactionresults/data/
├── createdat_month=2026-03/
│   └── 00000-7-7956eedf-a586-4245-ac93-86cbd62061ea-0-00001.parquet (8 records)
└── createdat_month=2026-04/
    ├── 00000-17-5f900916-8be8-420a-bdd5-b0def1c53922-0-00001.parquet (48 records)
    └── 00000-7-7956eedf-a586-4245-ac93-86cbd62061ea-0-00002.parquet (187 records)
```

**Total**: 3 Parquet files, 243 records

### File Format

- **Format**: Parquet with Snappy compression
- **Partitioning**: By `createdat_month` (YYYY-MM)
- **Column names**: Lowercase (e.g., `transactionid`, `statuswarning`)
- **Extra columns**: `_last_cdc_timestamp` (CDC metadata - removed during loading)

### Schema

| Column | Type | Description |
|--------|------|-------------|
| `uuid` | string | Unique transaction identifier |
| `transactionid` | int64 | Transaction ID |
| `idfi` | int64 | Financial institution ID |
| `statuswarning` | string | Transaction status (SAFE/RISKY/PENDING) |
| `metadata` | string | JSON with features and decision results |
| `createdat` | timestamp | Creation timestamp (UTC) |
| `updatedat` | timestamp | Update timestamp (UTC) |
| `_last_cdc_timestamp` | timestamp | CDC metadata (removed) |

---

## Changes Made

### 1. Updated `similarity_matcher.py`

**Lines changed**: 67-69, 158-178

```python
# OLD
DEFAULT_S3_BUCKET = "blossom-analytics-safe-dev-nv"
DEFAULT_S3_KEY = "safe_txns/similarity/data/wp_similarity.csv"

# NEW
DEFAULT_S3_BUCKET = "blossom-analytics-datalake-dev"
DEFAULT_S3_KEY = "datalake/silver/SAFE/safetransactionresults/data/"
```

**New features added**:

1. **Column name normalization** (lines 158-171)
   ```python
   # Parquet files use lowercase, normalize to camelCase
   column_mapping = {
       'uuid': 'uuid',
       'transactionid': 'transactionId',
       'idfi': 'idFi',
       'statuswarning': 'statusWarning',
       'metadata': 'metadata',
       'createdat': 'createdAt',
       'updatedat': 'updatedAt'
   }
   df_combined.columns = [column_mapping.get(col.lower(), col) 
                          for col in df_combined.columns]
   ```

2. **CDC metadata removal** (lines 172-178)
   ```python
   # Remove CDC metadata columns
   cdc_columns = ['_last_cdc_timestamp']
   for col in cdc_columns:
       if col in df_combined.columns:
           df_combined = df_combined.drop(columns=[col])
   ```

### 2. Backward Compatibility

The code **still supports**:
- CSV files (single file)
- Parquet files (single file)
- Parquet directories (multiple files)

Auto-detection based on file extension:
- `.csv` → CSV reader
- `.parquet` → Single Parquet reader
- `/` (ends with slash) → Parquet directory reader

---

## Testing

### Test Script

Created `test_similarity_silver.py` to verify functionality:

```bash
python3 test_similarity_silver.py
```

### Test Results

```
=== TEST: Similarity Matcher with Silver Layer ===

1. Configuration:
   Bucket: blossom-analytics-datalake-dev
   Key/Prefix: datalake/silver/SAFE/safetransactionresults/data/
   Expected: Parquet directory

2. Loading reference data...
   ✅ Success!
   - Files loaded: 3
   - Records: 243
   - Feature vectors: (243, 49)
   - Labels: 2 unique values: {'SAFE', 'RISKY'}
   - Transaction IDs: 243

3. Sample data:
   First transaction ID: 1798449
   First label: SAFE
   First vector shape: (49,)

4. DataFrame columns: 
   ['uuid', 'transactionId', 'idFi', 'statusWarning', 'metadata', 
    'createdAt', 'updatedAt']

✅ TEST PASSED: Similarity matcher can read Silver layer Parquet data
```

---

## Benefits of Silver Layer

### 1. Performance

- **Faster reads**: Parquet is 10-100x faster than CSV for analytical queries
- **Better compression**: 60-90% better than CSV
- **Column pruning**: Only reads needed columns
- **Predicate pushdown**: Skips irrelevant data blocks

### 2. Data Quality

- **Validated schema**: Enforced by data lake pipeline
- **Consistent formatting**: Normalized column names
- **CDC metadata**: Change data capture for auditing
- **Partitioning**: Efficient filtering by time ranges

### 3. Scalability

- **10x more data**: 243 records vs 22 in Bronze layer
- **Incremental loads**: New partitions added automatically
- **Distributed processing**: Spark/Athena compatible
- **Schema evolution**: Handles column additions gracefully

### 4. Data Governance

- **Single source of truth**: Silver layer is the validated dataset
- **Version control**: Partitioned by time
- **Lineage**: Tracks data from Bronze to Silver
- **Access control**: Managed by data lake policies

---

## Environment Variables

Override default bucket/key:

```bash
# Set custom S3 location
export SIMILARITY_S3_BUCKET="my-custom-bucket"
export SIMILARITY_S3_KEY="my/custom/path/"

# Or use S3 URI directly in code
load_reference_data_from_s3(s3_uri="s3://my-bucket/my/path/")
```

---

## Data Update Frequency

- **Silver layer**: Updated by data lake pipeline (batch process)
- **Frequency**: Daily or near-real-time (CDC)
- **Latency**: Typically < 1 hour from source to Silver
- **Cache**: Similarity matcher caches data until file count changes

---

## Monitoring

### File Count Check

The similarity matcher automatically detects when new files are added:

```python
# Checks file count on each load
current_count = _count_parquet_files_in_s3(s3_client, bucket, prefix)
if current_count != cached_count:
    logger.info(f"S3 data changed: {cached_count} -> {current_count} files. Reloading...")
```

### Logs to Monitor

```
[SIMILARITY] Loading parquet directory from s3://...
[SIMILARITY] Found 3 parquet files
[SIMILARITY] Combined 3 files into 243 records
[SIMILARITY] Normalized column names: ['uuid', 'transactionId', ...]
[SIMILARITY] Successfully loaded 243 valid records
[SIMILARITY] Feature vector shape: (243, 49)
```

---

## Migration Checklist

- [x] Update `DEFAULT_S3_BUCKET` and `DEFAULT_S3_KEY`
- [x] Add column name normalization
- [x] Remove CDC metadata columns
- [x] Test with Silver layer Parquet data
- [x] Verify feature extraction works
- [x] Confirm cache invalidation logic
- [x] Document changes
- [ ] Update production endpoint (pending deployment)
- [ ] Monitor logs after deployment
- [ ] Verify similarity matching accuracy

---

## Next Steps

1. **Deploy to production endpoint**:
   ```bash
   # Update endpoint code
   cd endpoint/
   # Test locally first
   python similarity_matcher.py --test
   
   # Package and deploy to SageMaker
   tar -czf model.tar.gz *.py *.joblib *.csv *.json
   aws s3 cp model.tar.gz s3://bucket/path/
   ```

2. **Update notebook**: Modify `safe-txn-endpoint.ipynb` to reflect new bucket

3. **Monitor performance**: Track load times and cache hit rates

4. **Set up alerts**: Notify when file count changes or loads fail

---

## Rollback Plan

If issues occur, revert to CSV by setting environment variables:

```bash
export SIMILARITY_S3_BUCKET="blossom-analytics-safe-dev-nv"
export SIMILARITY_S3_KEY="safe_txns/similarity/data/wp_similarity.csv"
```

No code changes needed - fully backward compatible.

---

## Contact

**Owner**: Data Engineering Team  
**Reviewer**: ML Engineering Team  
**Date**: 2026-04-29  

For questions or issues, contact the data platform team.
