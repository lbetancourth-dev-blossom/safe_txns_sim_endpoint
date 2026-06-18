# Statistical Rules Reference (v8)

Source: `endpoint/statistical_rules.py`

## Scoring Summary

Each transaction is scored by evaluating up to 12 rules. Points from all active rules are summed into `risk_score_raw`, then normalized to `risk_score_normalized` (0–100) using piecewise mapping.

**Maximum theoretical raw score**: 295 points  
**Normalization**: See [Phase 2 in model architecture guide](02-model-architecture.md#phase-2-statistical-rules-v8-r1r12)

**Decision thresholds (normalized score)**:

| Range | Decision |
|---|---|
| < 70 | Accept |
| 70–79 | User Auth |
| 80–89 | Admin Review |
| ≥ 90 | Reject |

---

## Rules Table

| Rule | Name | Max Points | Status |
|---|---|---|---|
| R1 | Amount vs user average | 45 | Disabled in v8 |
| R2 | Nighttime transaction | 20 | Active |
| R3 | First time to recipient (6h window) | 30 | Active |
| R4 | Recent cancellations | 20 | Active |
| R5 | Suspected session actions | 25 | Active |
| R6 | High amount vs low historical profile | 20 | Active |
| R7 | Transaction burst (5 min) | 35 | Active |
| R8 | Recipient history (2 months) | 15 | Active |
| R9 | Contact details updated | 15 | Disabled in v8 |
| R10 | Weekend transaction | 10 | Active |
| R11 | Disproportionate amount vs CU average | 45 | Active |
| R12 | New user tenure | 15 | Active |

---

## Rule Details

### R1 — Amount vs User Average *(disabled)*

**Field**: `user_avg_amount_txn_per_active_day_last_6_months`  
**Status**: Commented out in v8. Was activated when `ratio = amount / user_avg > 0.5`.  
**Rationale for disabling**: Too sensitive for business accounts; risk of false positives outweighed benefit.

Original piecewise points (for reference):

| ratio | Points (business: ×0.9) |
|---|---|
| ≤ 0.5 | 0 |
| 0.5–0.8 | 2 |
| 0.8–1.0 | 4 |
| 1.0–1.2 | 6 |
| 1.2–1.5 | 9 |
| 1.5–2.0 | 14 |
| 2.0–3.0 | 19 |
| 3.0–5.0 | 26 |
| > 5.0 | 45 |

---

### R2 — Nighttime Transaction

**Field**: `is_night` (int, 0 or 1)  
**Condition**: `is_night == 1`  
**Points**: +20  
**Rationale**: Transactions outside business hours carry elevated fraud risk.

---

### R3 — First Time to Recipient (6h Window)

**Field**: `is_first_txn_from_this_olb_user_to_this_recipient_account_q_6h` (int, 0 or 1)  
**Condition**: `== 1`  
**Points**: +30  
**Rationale**: A user sending to a new recipient for the first time within the last 6 hours is a high-signal fraud indicator. Reduced from 40 pts (v7) to 30 pts (v8) to reduce false positives.

---

### R4 — Recent Cancellations

**Field**: `count_user_cancelled_txn_in_last_week` (int)  
**Condition**: value > 0  
**Points**: `min(20, cancelled_count × 10)`

| Cancellations | Points |
|---|---|
| 0 | 0 |
| 1 | 10 |
| 2+ | 20 (capped) |

**Rationale**: Repeated cancellations in the prior week indicate exploratory fraud behavior.

---

### R5 — Suspected Session Actions

**Field**: `count_suspected_actions_in_current_session` (int)  
**Condition**: value > 0  
**Points**: `min(25, suspected_actions × 12)`

| Suspected actions | Points |
|---|---|
| 0 | 0 |
| 1 | 12 |
| 2 | 24 |
| 3+ | 25 (capped) |

**Rationale**: Session-level anomalies (e.g. rapid navigation, unusual click patterns) correlate with account takeover.

---

### R6 — High Amount vs Low Historical Profile

**Fields**: `amount` (float), `pct_txns_over_1k_lst6m` (float, 0–1)  
**Conditions** (evaluated in order, first match wins):

| Condition | Points |
|---|---|
| `amount > 1000` AND `pct_over_1k < 0.10` | +20 |
| `amount > 1500` AND `pct_over_1k < 0.20` | +15 |
| `pct_over_1k > 0.50` | +10 |
| Otherwise | 0 |

**Rationale**: A large transaction from a user who almost never sends large amounts is a strong anomaly signal. The third condition (high `pct_over_1k`) captures users who send large amounts often — slight elevated risk due to volume.

---

### R7 — Transaction Burst (5 min)

**Fields**: `count_all_txn_last_5m` (int), `is_batch` (int)  
**Condition**: Only evaluated when `is_batch == 0`

| `count_all_txn_last_5m` | Points |
|---|---|
| > 2 | +20 |
| > 1 (i.e., exactly 2) | +10 |
| ≤ 1 | 0 |

**Note**: The volume-relative sub-rule (`total_amount_5m > user_avg × N`) is disabled in v8 (commented out).  
**Max points**: 20 (burst only; was 35 in combined mode).  
**Rationale**: Multiple transactions in a 5-minute window from the same user suggest automated or scripted activity.

---

### R8 — Recipient History (2 Months)

**Field**: `count_txn_to_recipient_account_in_last_2_months` (int)

| Historical count | Points |
|---|---|
| 0 (never sent) | +15 |
| 1–2 | +8 |
| 3–5 | +3 |
| > 5 | 0 |

**Rationale**: Transactions to recipients with no or very little prior history are riskier.

---

### R9 — Contact Details Updated *(disabled)*

**Fields**: `is_personal_user_phone_primary_updated_last_week`, `is_personal_user_email_primary_updated_last_week`  
**Status**: Commented out in v8.  
**Rationale for disabling**: Legitimate profile updates (password reset flows, onboarding) caused too many false positives.

---

### R10 — Weekend Transaction

**Field**: `weekend` (int, 0 or 1)  
**Condition**: `weekend == 1`  
**Points**: +10  
**Rationale**: Lower support staffing and delayed settlement on weekends create a slightly higher risk window.

---

### R11 — Disproportionate Amount vs CU Average

**Field**: `txn_amount_vs_cu_avg_amount_ach_txn_in_last_6_months` (float)  
**Points**:

| Ratio vs CU average | Points |
|---|---|
| > 5× | +45 |
| > 3× | +30 |
| > 2× | +20 |
| ≤ 2× | 0 |

**Rationale**: Strongest single rule. An amount significantly above the credit union's typical ACH transaction average is a primary fraud signal, especially for smaller CUs where the average is low. Maintained at full strength from v7.

---

### R12 — New User Tenure

**Field**: `recency_user_created_days` (int)

| Days since account creation | Points |
|---|---|
| < 30 | +15 |
| 30–89 | +8 |
| ≥ 90 | 0 |

**Rationale**: Newly created accounts have shorter behavioral history and are a common fraud vector.

---

## Scoring Mechanism

```python
# Pseudocode for score_transaction_v8()
risk_score_raw = sum(rule_1 + rule_2 + ... + rule_12)

# Piecewise normalization (no hard cap, preserves 70/80/90 boundaries)
if raw <= 90:
    normalized = raw
elif raw < 295:
    normalized = 90 + (raw - 90) * (10 / (295 - 90))
else:
    normalized = 100

risk_score_normalized = round(normalized)
risk_decision = classify_risk(risk_score_normalized)
```

The `explanation` field in the output concatenates only the rules that contributed points, e.g.:
```
R2: nighttime +20 | R3: first-time to recipient (6h) +30 | R11: 3.5× CU +30
```

If no rule fires: `"Normal transaction"`.
