# Similarity Fields Reference Guide

## Overview
The endpoint returns **4 similarity fields** when similarity matching is enabled. These fields provide information about matched historical transactions and their relationship to the current transaction.

## Field Definitions

### 1. `sim_match_txn_id`
**Type**: String (nullable)  
**Description**: Transaction ID of the best matching historical transaction  
**Values**:
- Transaction ID string (e.g., "1798449") when match found
- `null` when no match found

**Example**:
```json
"sim_match_txn_id": "1798449"  // Match found
"sim_match_txn_id": null        // No match
```

### 2. `sim_score`
**Type**: Float (0.0-1.0, nullable)  
**Description**: Cosine similarity score between current and matched transaction  
**Values**:
- `0.90 - 1.0`: High similarity (triggers decision logic)
- `0.0 - 0.89`: Low similarity (no decision made)
- `null`: No match found

**Example**:
```json
"sim_score": 0.95  // 95% similar
"sim_score": 0.78  // 78% similar (below threshold)
"sim_score": null  // No match
```

### 3. `sim_status` ⭐ NEW
**Type**: String (nullable)  
**Description**: Risk status of the matched historical transaction  
**Values**:
- `"SAFE"`: Matched transaction was previously approved/safe
- `"RISKY"`: Matched transaction was previously flagged/risky
- `null`: No match found

**Example**:
```json
"sim_status": "SAFE"   // Matched a safe transaction
"sim_status": "RISKY"  // Matched a risky transaction
"sim_status": null     // No match
```

**Purpose**: Allows analysts to understand the nature of the matched transaction without looking it up separately.

### 4. `sim_decision`
**Type**: String (nullable)  
**Description**: Recommended action based on similarity analysis  
**Logic**:
```
IF sim_score >= 0.90 AND sim_status = "SAFE" → "Accept"
IF sim_score >= 0.90 AND sim_status = "RISKY" → "Reject"
ELSE → null
```

**Values**:
- `"Accept"`: High similarity to a safe transaction (recommend approval)
- `"Reject"`: High similarity to a risky transaction (recommend rejection)
- `null`: Score below threshold OR no match

**Example**:
```json
"sim_decision": "Accept"  // Score >= 0.90, status = SAFE
"sim_decision": "Reject"  // Score >= 0.90, status = RISKY
"sim_decision": null      // Score < 0.90 or no match
```

## Complete Examples

### Example 1: High Similarity to SAFE Transaction
```json
{
  "TransactionID": "4836236",
  "risk_score": 75,
  "risk_decision": "User Auth",
  "sim_match_txn_id": "1798449",
  "sim_score": 0.95,
  "sim_status": "SAFE",
  "sim_decision": "Accept"
}
```
**Interpretation**: 95% similar to transaction 1798449 (SAFE) → Recommend Accept

### Example 2: High Similarity to RISKY Transaction
```json
{
  "TransactionID": "4836504",
  "risk_score": 68,
  "risk_decision": "User Auth",
  "sim_match_txn_id": "1798850",
  "sim_score": 0.91,
  "sim_status": "RISKY",
  "sim_decision": "Reject"
}
```
**Interpretation**: 91% similar to transaction 1798850 (RISKY) → Recommend Reject

### Example 3: Low Similarity Match (Below Threshold)
```json
{
  "TransactionID": "4836505",
  "risk_score": 45,
  "risk_decision": "Accept",
  "sim_match_txn_id": "1798920",
  "sim_score": 0.88,
  "sim_status": "SAFE",
  "sim_decision": null
}
```
**Interpretation**: 88% similar to transaction 1798920 (SAFE), but below 90% threshold → No decision

### Example 4: No Match Found
```json
{
  "TransactionID": "4836507",
  "risk_score": 15,
  "risk_decision": "Accept",
  "sim_match_txn_id": null,
  "sim_score": null,
  "sim_status": null,
  "sim_decision": null
}
```
**Interpretation**: No similar historical transaction found

## Field Relationships

```
┌─────────────────┐
│  Match Found?   │
└────────┬────────┘
         │
    Yes  │  No
    ┌────▼────┐         ┌──────────────────┐
    │ sim_*   │         │ All sim_* = null │
    │ populated│        └──────────────────┘
    └────┬────┘
         │
         ▼
   ┌────────────────┐
   │ Score >= 0.90? │
   └────┬───────────┘
        │
   Yes  │  No
   ┌────▼────┐      ┌──────────────────────┐
   │ Status? │      │ sim_decision = null  │
   └────┬────┘      │ (other fields set)   │
        │           └──────────────────────┘
   ┌────▼────┐
   │ SAFE:   │ Accept
   │ RISKY:  │ Reject
   └─────────┘
```

## Analytics Queries

### Match Rate by Status
```sql
SELECT 
  sim_status,
  COUNT(*) as total_matches,
  ROUND(AVG(sim_score), 4) as avg_score,
  COUNT(CASE WHEN sim_decision IS NOT NULL THEN 1 END) as decisions_made
FROM endpoint_results
WHERE sim_status IS NOT NULL
GROUP BY sim_status;
```

### Decision Alignment (Model vs Similarity)
```sql
SELECT 
  risk_decision as model_decision,
  sim_decision as similarity_decision,
  sim_status,
  COUNT(*) as count
FROM endpoint_results
WHERE sim_decision IS NOT NULL
GROUP BY risk_decision, sim_decision, sim_status
ORDER BY count DESC;
```

### Safe vs Risky Match Distribution
```sql
SELECT 
  sim_status,
  CASE 
    WHEN sim_score >= 0.95 THEN '95-100%'
    WHEN sim_score >= 0.90 THEN '90-95%'
    WHEN sim_score >= 0.85 THEN '85-90%'
    ELSE '< 85%'
  END as score_range,
  COUNT(*) as count
FROM endpoint_results
WHERE sim_status IS NOT NULL
GROUP BY sim_status, score_range
ORDER BY sim_status, score_range DESC;
```

### No-Match Analysis
```sql
SELECT 
  risk_decision,
  COUNT(*) as total,
  COUNT(sim_status) as has_match,
  COUNT(*) - COUNT(sim_status) as no_match,
  ROUND((COUNT(*) - COUNT(sim_status)) * 100.0 / COUNT(*), 2) as no_match_pct
FROM endpoint_results
GROUP BY risk_decision
ORDER BY no_match_pct DESC;
```

## Pandas Usage

```python
import pandas as pd

df = pd.read_csv('endpoint_results.csv')

# Filter by status
safe_matches = df[df['sim_status'] == 'SAFE']
risky_matches = df[df['sim_status'] == 'RISKY']
no_matches = df[df['sim_status'].isna()]

# Status distribution
print(df['sim_status'].value_counts(dropna=False))

# Decision by status
print(df.groupby(['sim_status', 'sim_decision']).size())

# Score distribution by status
print(df.groupby('sim_status')['sim_score'].describe())
```

## Field Evolution

| Version | Fields | Notes |
|---------|--------|-------|
| 1.0.0 | sim_match_txn_id, sim_score, sim_decision | Initial implementation |
| 1.1.0 | + sim_status | Added status visibility |

## Total Column Count

**Response now has 63 columns total**:
- 1: TransactionID
- 2-32: num__ features (31)
- 33-50: cat__ features (18)
- 51-59: Model results (9)
- 60-63: Similarity results (4) ⭐ **+1 new field**

---

**Last Updated**: 2026-04-28  
**Version**: 1.1.0  
**Status**: Implemented in endpoint_test/
