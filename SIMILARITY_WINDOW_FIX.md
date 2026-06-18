# Critical Fix: Similarity Matching Window Calculation

## Problem Identified

The Athena similarity matching query was using an **incorrect time window** for all transactions:

```python
# INCORRECT (old code)
window_start = now() - 6 months
window_end = now()
# Query all users' historical data in this fixed global range
```

This meant:
- Query always looked in [2025-12-17, 2026-06-17] regardless of transaction date
- If evaluating transaction from April 2026, still searched in the global window
- Not designed for individual transaction-relative history

## Solution Implemented

**Each transaction now uses its OWN date as the window anchor:**

```python
# CORRECT (new code)
for each transaction:
    transaction_date = transaction['createdAtTxns']  # e.g., 2026-04-15
    window_start = transaction_date - 6 months       # 2025-10-15
    window_end = transaction_date                    # 2026-04-15
    # Query user's history BEFORE this transaction
```

## Example

**Scenario:** Evaluating transaction on 2026-04-15

**Old Logic:**
```
Search window: [2025-12-17, 2026-06-17]
Found: User's April AND May AND June transactions
Problem: Includes transactions AFTER the one being evaluated
```

**New Logic:**
```
Search window: [2025-10-15, 2026-04-15]
Found: User's October, November, December, January, February, March, April transactions
Correct: Only historical data BEFORE the transaction
```

## Code Changes

### 1. `similarity_matcher.py`

**Function:** `_compute_sliding_window()`
```python
# OLD: Used now() as fixed end date
def _compute_sliding_window(window_months: int = 6):
    end = datetime.now(timezone.utc)
    start = end - relativedelta(months=window_months)
    return start, end

# NEW: Uses transaction date as end date
def _compute_sliding_window(window_months: int = 6, reference_dt: Optional[datetime] = None):
    if reference_dt is None:
        end = datetime.now(timezone.utc)
    else:
        end = reference_dt.astimezone(timezone.utc) if reference_dt.tzinfo else reference_dt.replace(tzinfo=timezone.utc)
    start = end - relativedelta(months=window_months)
    return start, end
```

**Function:** `load_reference_data_from_athena()`
```python
# OLD: Calculated window without transaction context
start, end = _compute_sliding_window(window_months)

# NEW: Uses transaction's createdAtTxns for window
def load_reference_data_from_athena(
    idolbuser: int,
    window_months: int = 6,
    transaction_datetime: Optional[datetime] = None,  # NEW PARAMETER
    ...
):
    start, end = _compute_sliding_window(window_months, reference_dt=transaction_datetime)
```

**Function:** `find_similar_transaction()`
```python
# OLD: No transaction date parameter
def find_similar_transaction(
    query_result: Dict[str, Any],
    idolbuser: Optional[int] = None,
    window_months: int = 6,
    ...
):

# NEW: Accepts transaction date parameter
def find_similar_transaction(
    query_result: Dict[str, Any],
    idolbuser: Optional[int] = None,
    window_months: int = 6,
    transaction_datetime: Optional[datetime] = None,  # NEW PARAMETER
    ...
):
    ref_df, ref_vectors, ref_labels, ref_ids = load_reference_data_from_athena(
        idolbuser=idolbuser,
        window_months=window_months,
        transaction_datetime=transaction_datetime,  # NEW: Pass transaction date
        ...
    )
```

### 2. `inference_rules.py`

**In `predict_fn()` similarity matching loop:**
```python
# OLD: No transaction date passed
result = _similarity_mod.find_similar_transaction(
    query_result=query_features,
    threshold=similarity_threshold,
    idolbuser=idolbuser_int,
    window_months=6,
    timeout_seconds=10,
)

# NEW: Extract and pass transaction date
txn_date_val = out_df.iloc[idx].get("__createdAtTxns_dt")
result = _similarity_mod.find_similar_transaction(
    query_result=query_features,
    threshold=similarity_threshold,
    idolbuser=idolbuser_int,
    window_months=6,
    timeout_seconds=10,
    transaction_datetime=txn_date_val,  # NEW: Pass transaction date
)
```

## Impact

### Before
- Athena query for all transactions: Same 6-month window
- Results: Mixed historical data regardless of transaction date
- Similarity matching: Potentially matching against future transactions (wrong)

### After
- Athena query for each transaction: Relative to transaction date
- Results: Historical data up to transaction date
- Similarity matching: Correct historical context (transactions before current one)

## Athena Query Behavior

### Example: User 597178 evaluating transaction on 2026-04-15

**Query Execution:**
```sql
SELECT idolbuser, createdat, statuswarning, metadata, transactionid
FROM dlh_silver_safe_alpha.safetransactionresults
WHERE idolbuser = 597178
  AND createdat >= 2025-10-15  -- 6 months before transaction
  AND createdat <= 2026-04-15  -- Transaction date (NOT current date)
  AND statuswarning IN ('SAFE', 'RISKY')
```

**Expected Results:**
- User's October 2025 transactions
- User's November 2025 transactions
- ...
- User's April 2026 transactions (up to but not after 2026-04-15)

**NOT Included:**
- Any transactions after 2026-04-15
- Transactions from other users
- Transactions outside SAFE/RISKY status

## Testing

After endpoint re-deployment:

```bash
# Test with test_escenarios.csv (dates in April-June 2026)
python3 test/process_endpoint.py --input data/test_escenarios.csv

# For row 0: Transaction at 2026-04-15
# Expected: Athena queries [2025-10-15, 2026-04-15]
# User 597178 should return historical matches from Oct-Apr period

# For row 2: Transaction at 2026-05-05
# Expected: Athena queries [2024-11-05, 2026-05-05]
# User 604150 should return historical matches from Nov-May period
```

## Commit

```
24c62f5 fix(similarity): use transaction date for Athena window calculation
```

Branch: `feat/DATA-1264`
Status: ✅ Ready for endpoint re-deployment
