# Endpoint Error Diagnosis — safe-txns-endpoint 500 Error

## Current Status
- **Endpoint:** data-safe-txns-endpoint (InService)
- **Error:** HTTP 500 — Internal Server Error
- **Symptom:** When invoking with test_escenarios.csv, returns 500 error instead of predictions

## Root Cause Analysis

### Issue 1: Test Data Date Range Problem (FIXED ✅)
**Problem Identified:** Test data was from 2024-06-04, outside the 6-month sliding window
- Window calculation: `now() ± 6 months`
- Current date: 2026-06-17
- Window range: 2025-12-17 to 2026-06-17
- Test data: 2024-06-04 (outside range)
- Result: Athena query returns 0 rows

**Fix Applied:**
```
Commit: 58a6286
- Updated all 10 transactions to June 2026 (within window)
- Dates now: 2026-06-10 to 2026-06-16
- All transactions fall within valid 6-month lookback
```

### Issue 2: CSV Format Problem (FIXED ✅)
**Problem Identified:** Extra `Unnamed: 0` column (index) causing 62 instead of 61 columns

**Fix Applied:**
```
Commit: 5763143
- Removed index column
- CSV now has exactly 61 columns as expected
```

### Issue 3: Endpoint 500 Error (ACTIVE)
**Symptom:** Even with corrected data, endpoint returns 500

**Possible Causes:**
1. **Endpoint code is outdated**
   - Endpoint was deployed before recent code changes
   - Changes to similarity_matcher.py haven't been deployed
   - Container is running old code

2. **DatetimeFormatError in Input Processing**
   - New date format (2026-06-10 08:00:00.000 UTC) might not match expected format
   - DTYPE_MAP might have different expectations
   - createdAtTxns parsing might fail

3. **Missing Dependencies in Container**
   - pyathena>=3.0 installed in requirements.txt
   - But container might not have been rebuilt after requirements change
   - Causes ImportError when loading similarity_matcher

4. **Unhandled Exception in New Code Path**
   - datetime calculations in `_compute_sliding_window()`
   - New date format parsing
   - Timezone handling

## Data Validation Completed

✅ **Test Data Now Correct:**
- 61 columns (no index)
- 10 rows with valid Athena user IDs
- Dates within 6-month window:
  - User 597178: 4 transactions
  - User 385543: 3 transactions
  - User 604150: 3 transactions

✅ **Athena Data Verified:**
- dlh_silver_safe_alpha.safetransactionresults exists
- Confirmed users exist with historical data
- Window filtering would now work correctly

✅ **Code Changes Verified:**
- similarity_matcher.py: no hashes in Athena comparison
- inference_rules.py: similarity matching code present
- requirements.txt: pyathena>=3.0 included

## Next Steps — Debugging the 500 Error

### Option 1: View CloudWatch Logs (Recommended)
AWS Console → CloudWatch → `/aws/sagemaker/Endpoints/data-safe-txns-endpoint` → AllTraffic

Look for:
- `[PRED] start / [PRED] done` — predict_fn entry/exit
- `[SIMILARITY]` — similarity matching logs
- `ERROR`, `Traceback`, `Exception` — error details

### Option 2: Test with Original Dates (Workaround)
If the problem is date format, try:
```
Use dates from 2024-06-04 but ensure they're formatted identically
to other data in Athena (may require manual Parquet inspection)
```

### Option 3: Re-deploy Endpoint (Most Likely Fix)
The 500 error could be because the endpoint container doesn't have:
1. Latest code changes (similarity_matcher.py updates)
2. Updated dependencies (requirements.txt)
3. Proper module initialization

**Steps:**
1. Use notebook: `safe-txn-enpoint.ipynb` (Cell 11-12)
2. Or use AWS CLI:
   ```bash
   aws sagemaker create-model \
     --model-name safe-txn-similarity-model-$(date +%Y%m%d) \
     --primary-container ... \
     --execution-role-arn ...
   ```

## Summary of Changes Made This Session

| Commit | Change | Status |
|--------|--------|--------|
| 5643d03 | Remove user ID hashing in similarity_matcher.py | Committed ✅ |
| 023e605 | Add similarity testing documentation | Committed ✅ |
| 58a6286 | Update test data to recent dates (within 6-month window) | Committed ✅ |
| 5763143 | Remove index column from CSV | Committed ✅ |

All changes have been pushed to `feat/DATA-1264` branch.

## Testing Checklist

After endpoint is re-deployed:

- [ ] Test with test_escenarios.csv returns 200 OK (not 500)
- [ ] Response includes sim_* columns (not None)
- [ ] Similarity scores are > 0.5 for matching transactions
- [ ] Audit logs show `[SIMILARITY] Loading from Athena for idolbuser=...`
- [ ] CloudWatch shows no exceptions or errors

## Commands to Verify

```bash
# 1. Verify test data format
head -2 data/test_escenarios.csv | wc -w
# Should output: 61 columns

# 2. Check dates are recent
cut -d',' -f4 data/test_escenarios.csv | tail -1
# Should show: 2026-06-XX HH:MM:SS.000 UTC

# 3. Verify commits are pushed
git log --oneline feat/DATA-1264 | head -5
# Should show: 5763143, 58a6286, 023e605, 5643d03
```

## Critical Path Forward

**Unblock:** Re-deploy the endpoint container to include:
- Updated similarity_matcher.py (int comparison, no hashes)
- Updated requirements.txt (pyathena>=3.0)
- Correct DTYPE_MAP for new date formats

**Validate:** Run test_escenarios.csv through endpoint, confirm:
- No 500 errors
- sim_* fields have non-null values
- Similarity scores correlate with transaction similarity

**Success Criteria:**
- First row (TransactionID 1032495, User 597178): sim_* fields populated
- Similarity matches found for users with multiple transactions in window
- Error logging shows Athena queries executing, returning N rows
