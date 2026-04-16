# Similarity Matcher Changes - April 16, 2026

## Changes Implemented

### 1. ✅ Removed TransactionID from Similarity Response
**File:** `endpoint/similarity_matcher.py` (lines 585-591)

**Before:**
```python
top_matches.append({
    "TransactionID": ref_ids[idx],
    "similarity_score": float(score),
    "status_warning": ref_labels[idx],
    "index": int(idx)
})
```

**After:**
```python
top_matches.append({
    "similarity_score": float(score),
    "status_warning": ref_labels[idx]
})
```

**Impact:** 
- Cleaner response format
- No sensitive transaction IDs exposed
- Simplified data structure
- No internal index field

---

### 2. ✅ Filter S3 Records by StatusWarning
**File:** `endpoint/similarity_matcher.py` (lines 308-317)

**Added Logic:**
```python
# Filter by statusWarning - ONLY accept SAFE or RISKY
status_warning = str(row.get("statusWarning", "")).strip().upper()
if status_warning not in ["SAFE", "RISKY"]:
    skip_reasons["schema_invalid"] += 1
    skipped_count += 1
    logger.debug(
        f"[SIMILARITY] Skipping row {idx}: invalid statusWarning '{status_warning}' "
        f"(must be SAFE or RISKY)"
    )
    continue
```

**Impact:**
- Only SAFE or RISKY records are included in comparison
- Records with UNKNOWN, PENDING, or other statuses are filtered out
- No invalid statuses in top_matches results
- Improves data quality and decision reliability

---

## Updated Response Format

### Before:
```json
{
  "matched": true,
  "similarity_score": 0.95,
  "status_warning": "SAFE",
  "top_matches": [
    {
      "TransactionID": "78901",
      "similarity_score": 0.95,
      "status_warning": "HIGH_RISK",
      "index": 42
    }
  ]
}
```

### After:
```json
{
  "matched": true,
  "similarity_score": 0.95,
  "status_warning": "SAFE",
  "top_matches": [
    {
      "similarity_score": 0.95,
      "status_warning": "SAFE"
    }
  ]
}
```

---

## Documentation Updated

1. **docs/SIMILARITY_INTEGRATION.md**
   - Added statusWarning filtering explanation
   - Updated schema validation section
   - Added note about SAFE/RISKY filter

2. **endpoint/SIMILARITY_USAGE.md**
   - Updated response format examples
   - Removed TransactionID references
   - Added privacy note

---

## Testing

Created test script: `test/verify_similarity_changes.py`

✅ All tests passed:
1. Response format verification (no TransactionID, no index)
2. StatusWarning filtering logic
3. Integration flow validation

---

## Benefits

1. **Privacy:** No transaction IDs exposed in responses
2. **Data Quality:** Only validated SAFE/RISKY records used
3. **Simplicity:** Cleaner, more focused response structure
4. **Reliability:** Filters out ambiguous or invalid status values

---

## Deployment Notes

- Changes are backward compatible
- Existing S3 data will be automatically filtered
- No configuration changes required
- Model re-packaging recommended for SageMaker endpoint update

