---
title: Similarity Matching Reference
tags: [similarity, athena, exact-match]
type: reference
---

# Similarity Matching Reference

## Overview
The endpoint queries Athena for historical transactions from the same user within a 6-month sliding window and scores field-level similarity against the incoming transaction.

## Return fields
| Field | Type | When populated |
|-------|------|----------------|
| sim_match_txn_id | string | Always, if Athena has data |
| sim_score | float 0-1 | Always, if Athena has data |
| sim_status | SAFE/RISKY | Always, if Athena has data |
| sim_decision | Accept/Reject/None | Only when sim_score >= 0.90 |

## Scoring logic
- Compares 49 fields (31 num__ + 18 cat__) between input and each reference transaction
- Score = exact_matches / 49
- Float tolerance: 1e-9 (handles preprocessing round-trip precision)
- None vs 0: absent field treated as 0 (handles SELECTED list filtering)
- Threshold: 0.90 (configurable via SIMILARITY_THRESHOLD env var)

## sim_decision values
- `Accept` — score >= 0.90 AND sim_status = SAFE
- `Reject` — score >= 0.90 AND sim_status = RISKY
- `None` — score < 0.90 (no similarity-based decision taken)

## Athena query
```sql
SELECT idolbuser, createdat, statuswarning, metadata, transactionid
FROM dlh_silver_safe_alpha.safetransactionresults
WHERE idolbuser = %(user)s
  AND CAST(createdat AS DATE) >= CAST(%(window_start_date)s AS DATE)
  AND CAST(createdat AS DATE) <= CAST(%(window_end_date)s AS DATE)
  AND statuswarning IN ('SAFE', 'RISKY')
```

## Sliding window
- End: transaction datetime
- Start: end - 6 months
- Configurable via `ATHENA_WINDOW_MONTHS` env var (default: 6)

## OHE encoding note
Reference data in Athena was stored by an older pipeline version using `drop='first'` OHE. This means:
- TransactionProcessingType='Intime' → all cat__ zeros (not 1.0)
- TransactionOrigin='External Internal' → all cat__ zeros
- Use `''` for these fields in test data to produce all-zeros via `handle_unknown='ignore'`

## Graceful degradation
If Athena is unavailable (timeout, permissions, no data): all `sim_*` fields return None. Endpoint continues functioning with K-Means + statistical rules only.

## Test scenarios
See `data/test_escenarios.csv` (16 rows covering all cases):
- Rows 1-5: HIGH_SIM (score ~0.9796, sim_decision=Accept)
- Rows 6-8: LOW_SIM (score 0.77-0.84, sim_decision=None)
- Rows 9-11: NO_HISTORY (no Athena data, all None)
- Rows 12-16: Edge cases (outlier, first txn, batch, night, old window)
