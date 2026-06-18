# Graceful Degradation - Error Handling

## Overview

The similarity matching endpoint is designed to be **resilient and always available**, even when reference data is unavailable or invalid. The endpoint implements **graceful degradation**: if similarity matching cannot be performed, the endpoint continues processing transactions using only the K-means model.

## Error Scenarios Handled

The endpoint gracefully handles the following scenarios **WITHOUT crashing**:

### 1. No Parquet Files in S3
**Scenario:** The S3 directory exists but contains no `.parquet` files.

**Behavior:**
- Logs WARNING: "No .parquet files found in s3://..."
- Returns `None` values from `load_reference_data_from_s3()`
- `find_similar_transaction()` returns: `matched=False, similarity_score=0.0, status_warning='NONE'`
- Endpoint processes transactions using K-means only

### 2. All Records are PENDING
**Scenario:** S3 contains parquet files, but all records have `statusWarning` values other than 'SAFE' or 'RISKY' (e.g., all are 'PENDING', 'UNKNOWN', etc.)

**Behavior:**
- Logs WARNING: "No valid feature vectors extracted from reference data"
- After filtering, 0 valid records remain
- Returns `None` values from `load_reference_data_from_s3()`
- Endpoint continues with K-means only

**Current S3 State:** As of last check, the S3 bucket contains:
- 20 parquet files with 199 total records
- Only 1 record with statusWarning='SAFE'
- 198 records with statusWarning='PENDING' (filtered out)

### 3. Empty Parquet Files
**Scenario:** Parquet files exist but contain 0 rows.

**Behavior:**
- Same as "All Records are PENDING" scenario
- Returns `None` values
- Endpoint continues processing

### 4. S3 Connection Errors
**Scenario:** Network issues, permission errors, bucket doesn't exist, etc.

**Behavior:**
- Logs ERROR: "Error loading reference data from s3://... : {error details}"
- Returns `None` values
- Endpoint continues with K-means only

### 5. Corrupted Parquet Files
**Scenario:** Parquet files are corrupted or unreadable.

**Behavior:**
- Logs ERROR with details
- Returns `None` values
- Endpoint continues processing

## Implementation Details

### Code Changes

**similarity_matcher.py:**
```python
# Line ~498: Changed from raising ValueError to returning None
if len(vectors) == 0:
    logger.warning(
        f"[SIMILARITY] No valid feature vectors extracted... "
        f"Similarity matching will be DISABLED."
    )
    return None, None, None, None  # Instead of: raise ValueError(...)

# Line ~539: Changed from re-raising exception to returning None
except Exception as e:
    logger.error(
        f"[SIMILARITY] Error loading reference data from {bucket}/{key}: {e}. "
        f"Similarity matching will be DISABLED. Endpoint will continue processing with K-means only."
    )
    return None, None, None, None  # Instead of: raise

# Line ~707: Added None check in find_similar_transaction()
if ref_vectors is None or ref_labels is None:
    logger.warning("[SIMILARITY] No reference data available - similarity matching disabled")
    return {
        "matched": False,
        "similarity_score": 0.0,
        "status_warning": "NONE",
        "top_matches": [],
        "error": "No reference data available"
    }
```

**inference_rules.py:**
No changes required! The existing code already handles `matched=False` gracefully:
- Line 1090: Only overrides decision if `matched=True AND similarity_score >= threshold`
- If matched=False, keeps the K-means decision
- No errors, no crashes

### Return Values

When reference data is unavailable, `load_reference_data_from_s3()` returns:
```python
(None, None, None, None)
```

And `find_similar_transaction()` returns:
```python
{
    "matched": False,
    "similarity_score": 0.0,
    "status_warning": "NONE",
    "top_matches": [],
    "error": "No reference data available"  # Only when applicable
}
```

## Benefits

### 1. High Availability
- Endpoint remains operational even if S3 data is unavailable
- No downtime when updating reference data
- Can deploy endpoint before reference data exists

### 2. Progressive Enhancement
- Start with K-means only
- Add reference data later to enable similarity matching
- Reference data dynamically reloaded when available

### 3. Resilient to Data Quality Issues
- Handles PENDING/incomplete records gracefully
- Doesn't crash on invalid or corrupted files
- Logs helpful warnings for debugging

### 4. Flexible Deployment
- Can deploy in stages: first K-means, then add similarity
- No hard dependency on S3 data existence
- Testing easier (no need for mock S3 data)

## Monitoring

### Log Messages to Watch

**Normal Operation (with similarity):**
```
[SIMILARITY] Successfully loaded 1 valid reference vectors, shape: (1, 49)
[SIMILARITY] Checking similarity for N transactions (threshold: 0.90)
```

**Graceful Degradation (without similarity):**
```
[SIMILARITY] No .parquet files found in s3://...
[SIMILARITY] Similarity matching will be DISABLED. Endpoint will continue processing with K-means only.
```

or

```
[SIMILARITY] No valid feature vectors extracted from reference data. Total rows: 199, all records were skipped.
[SIMILARITY] Similarity matching will be DISABLED.
```

### Metrics to Track

When monitoring the endpoint:
1. **Similarity Match Rate:** % of transactions where `matched=True`
   - Expected to be LOW if only 1 valid reference record exists
   - Should increase as more SAFE/RISKY records are added to S3

2. **Reference Data Load Failures:** Count of "Error loading reference data" logs
   - Should be 0 in normal operation
   - Alerts if consistently failing

3. **Valid Reference Records:** Number loaded from S3
   - Currently: 1 (out of 199 total)
   - Should increase as more transactions are labeled SAFE/RISKY

## Testing

Comprehensive tests in `tests/endpoint/test_graceful_degradation.py` verify:
- ✅ No parquet files in S3
- ✅ All records PENDING (no SAFE/RISKY)
- ✅ S3 connection errors
- ✅ Corrupted parquet files
- ✅ find_similar_transaction with None reference data

All tests pass, confirming the endpoint handles errors gracefully.

## FAQ

**Q: What happens to existing transactions when similarity is unavailable?**
A: They are processed normally using the K-means model. The `risk_score` and `risk_decision` are determined solely by K-means (cluster assignment and distance to centroid).

**Q: Will the endpoint automatically resume similarity matching when data becomes available?**
A: Yes! The dynamic reload feature checks for new parquet files on each inference call. As soon as valid reference data is added to S3, similarity matching automatically resumes.

**Q: How can I tell if similarity is working or disabled?**
A: Check the inference logs. If similarity is working, you'll see:
```
[SIMILARITY] Checking similarity for N transactions
```
If disabled, you'll see warning messages about missing/invalid data.

**Q: Should I add more SAFE/RISKY records to S3?**
A: Yes! Currently only 1 out of 199 records is valid. The more SAFE/RISKY labeled records you have, the more effective similarity matching becomes. PENDING records are filtered out.

**Q: Can I disable similarity matching intentionally?**
A: Yes, set the environment variable:
```
DISABLE_SIMILARITY=1
```
This skips similarity matching even if reference data exists.

## Best Practices

1. **Monitor reference data quality:** Regularly check how many records are SAFE/RISKY vs PENDING
2. **Label historical data:** Convert PENDING records to SAFE/RISKY as they are reviewed
3. **Set up alerts:** Alert if reference data loading fails repeatedly
4. **Test degradation:** Periodically test endpoint behavior with empty S3 data
5. **Document expectations:** Make it clear to users when similarity is/isn't active

## Summary

The endpoint is now **production-ready** with robust error handling:
- ✅ Never crashes due to missing/invalid reference data
- ✅ Automatically resumes similarity when data becomes available
- ✅ Provides clear logging for monitoring and debugging
- ✅ Maintains high availability and uptime
- ✅ Gracefully degrades to K-means-only mode

This makes the endpoint suitable for production deployment even before comprehensive reference data is collected.
