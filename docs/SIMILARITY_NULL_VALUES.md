# Similarity Fields: Null Values Strategy

## Overview
When no similarity match is found, all similarity fields return `null` values instead of default placeholders. This provides semantic clarity and better analytics capabilities.

## Null Values Behavior

### When Match Found (score >= 0.90):
```json
{
  "sim_match_txn_id": "1798449",  // ID of matched transaction
  "sim_score": 0.95,                // Similarity score (0.90-1.0)
  "sim_decision": "Accept"          // or "Reject" based on status
}
```

### When Match Found (score < 0.90):
```json
{
  "sim_match_txn_id": "1798920",  // ID of matched transaction
  "sim_score": 0.88,                // Similarity score below threshold
  "sim_decision": null              // No decision (below threshold)
}
```

### When NO Match Found:
```json
{
  "sim_match_txn_id": null,  // No matched transaction
  "sim_score": null,          // No score calculated
  "sim_decision": null        // No decision
}
```

## Rationale: Why Nulls Over Defaults?

### ✅ Advantages of Null Strategy:

1. **Semantic Correctness**
   - `null` = "value not calculated/not available"
   - `0.0` = "similarity is zero" (misleading when not calculated)

2. **SQL Analytics Simplification**
   ```sql
   -- Count transactions with matches
   SELECT COUNT(sim_score) FROM results;
   
   -- Average similarity score (only for matches)
   SELECT AVG(sim_score) FROM results;
   
   -- Find transactions without matches
   SELECT * FROM results WHERE sim_score IS NULL;
   
   -- Match rate calculation
   SELECT 
     COUNT(*) as total,
     COUNT(sim_score) as matched,
     ROUND(COUNT(sim_score) * 100.0 / COUNT(*), 2) as match_rate_pct
   FROM results;
   ```

3. **Statistical Accuracy**
   - Aggregate functions (`AVG`, `MIN`, `MAX`) automatically exclude nulls
   - No need to filter `WHERE sim_score > 0` to avoid false zeros
   - Standard deviation and percentiles are more accurate

4. **Data Integrity**
   - Clear distinction between "no match" vs "perfect non-similarity"
   - Prevents accidental inclusion of non-matches in score-based filters

5. **BI Tool Compatibility**
   - Tableau, Power BI, and Excel handle nulls natively
   - Can be easily converted to custom labels: `COALESCE(sim_score, 'NO_MATCH')`

## CSV Representation

In CSV format, null values are represented as empty fields:

```csv
TransactionID,sim_match_txn_id,sim_score,sim_decision
4836236,1798449,0.95,Accept
4836503,1798800,0.92,Accept
4836505,1798920,0.88,
4836507,,,
```

**Note**: The last row shows all three similarity fields as empty (null).

## Python/Pandas Handling

```python
import pandas as pd

# Load results
df = pd.read_csv('results.csv')

# Check for nulls
df['sim_score'].isna()  # Returns True for no-match rows

# Filter only matches
matched = df[df['sim_score'].notna()]

# Calculate statistics (nulls excluded automatically)
avg_score = df['sim_score'].mean()
max_score = df['sim_score'].max()

# Replace nulls for display
df['sim_score_display'] = df['sim_score'].fillna('NO_MATCH')
```

## API Response Examples

### Match Found:
```json
{
  "TransactionID": "4836236",
  "risk_score": 75,
  "risk_decision": "User Auth",
  "sim_match_txn_id": "1798449",
  "sim_score": 0.95,
  "sim_decision": "Accept"
}
```

### No Match:
```json
{
  "TransactionID": "4836507",
  "risk_score": 15,
  "risk_decision": "Accept",
  "sim_match_txn_id": null,
  "sim_score": null,
  "sim_decision": null
}
```

## Analytics Queries

### Match Rate by Risk Decision
```sql
SELECT 
  risk_decision,
  COUNT(*) as total_txns,
  COUNT(sim_score) as matched_txns,
  ROUND(COUNT(sim_score) * 100.0 / COUNT(*), 2) as match_rate_pct,
  ROUND(AVG(sim_score), 4) as avg_similarity
FROM endpoint_results
GROUP BY risk_decision
ORDER BY match_rate_pct DESC;
```

### Score Distribution (Only Matches)
```sql
SELECT 
  CASE 
    WHEN sim_score >= 0.95 THEN '95-100%'
    WHEN sim_score >= 0.90 THEN '90-95%'
    WHEN sim_score >= 0.85 THEN '85-90%'
    ELSE '< 85%'
  END as score_range,
  COUNT(*) as count
FROM endpoint_results
WHERE sim_score IS NOT NULL
GROUP BY score_range
ORDER BY score_range DESC;
```

### Decision Alignment Analysis
```sql
SELECT 
  risk_decision,
  sim_decision,
  COUNT(*) as count
FROM endpoint_results
WHERE sim_decision IS NOT NULL  -- Only rows with similarity decisions
GROUP BY risk_decision, sim_decision
ORDER BY count DESC;
```

## Implementation Details

**File**: `endpoint_test/inference_rules.py`

**Lines 1098-1102**: Match found
```python
similarity_result = {
    "sim_match_txn_id": matched_txn_id,
    "sim_score": float(similarity_score) if similarity_score is not None else None,
    "sim_decision": sim_decision
}
```

**Lines 1106-1110**: No match or error
```python
similarity_result = {
    "sim_match_txn_id": None,
    "sim_score": None,
    "sim_decision": None
}
```

## Migration from Previous Version

### Old Behavior (0.0 default):
- No match: `sim_score = 0.0`
- Could be confused with "zero similarity"
- Required filtering: `WHERE sim_score > 0`

### New Behavior (null):
- No match: `sim_score = null`
- Semantically clear: "not calculated"
- Natural filtering: `WHERE sim_score IS NOT NULL`

**Note**: If you have existing data with `0.0` for no-match, update it:
```sql
UPDATE endpoint_results 
SET sim_score = NULL 
WHERE sim_score = 0.0 AND sim_match_txn_id IS NULL;
```

---

**Last Updated**: 2026-04-28  
**Version**: 1.1.0  
**Status**: Implemented in endpoint_test/
