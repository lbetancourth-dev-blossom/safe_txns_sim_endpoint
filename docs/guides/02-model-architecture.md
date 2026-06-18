# Model Architecture

## Overview

```
Input CSV (61 columns)
        │
        ▼
┌───────────────────────────────────────────────────────┐
│           SageMaker Endpoint (ml.m5.large)            │
│                                                       │
│  ┌─────────────────────────────────────────────────┐  │
│  │  1. Validation & Preprocessing                  │  │
│  │     - Type coercion (DTYPE_MAP)                 │  │
│  │     - Temporal feature derivation               │  │
│  │       (hour_sin/cos, day_of_week_sin/cos, etc.) │  │
│  └────────────────────┬────────────────────────────┘  │
│                       │                               │
│          ┌────────────┼────────────┐                  │
│          ▼            ▼            ▼                  │
│  ┌──────────────┐ ┌─────────┐ ┌──────────────────┐   │
│  │  K-Means     │ │ Rules   │ │ Similarity       │   │
│  │  Clustering  │ │  v8     │ │ Matching (Athena)│   │
│  │  (Phase 1)   │ │(Phase 2)│ │   (Phase 3)      │   │
│  └──────┬───────┘ └────┬────┘ └────────┬─────────┘   │
│         │              │               │              │
│         └──────────────┼───────────────┘              │
│                        ▼                              │
│              ┌─────────────────┐                      │
│              │  Hybrid Policy  │                      │
│              │  Final Decision │                      │
│              └─────────────────┘                      │
└───────────────────────────────────────────────────────┘
        │
        ▼
Output JSON (one object per input row)
```

---

## Phase 1: K-Means Clustering

**Purpose**: Assign each transaction to a behavioral cluster and measure how anomalous it is within that cluster.

**Training data**: 168,000 ACH transactions from Nov 2023 to Nov 2025.

**Number of clusters**: 8 (k=8).

**Preprocessing pipeline** (scikit-learn `ColumnTransformer`):

| Step | Transformer | Features |
|---|---|---|
| Numeric scaling | `StandardScaler` | 47 numeric features |
| Categorical encoding | `OneHotEncoder(handle_unknown='ignore')` | 5 categorical features |

**Feature selection**: 49 features selected after feature importance analysis (from the full 52-feature transformed space).

**Artifacts** (loaded at endpoint startup from `model.tar.gz`):

| File | Description |
|---|---|
| `kmeans_model.joblib` | Trained KMeans model |
| `preprocessing_pipeline.joblib` | ColumnTransformer pipeline |
| `selected_features.csv` | List of 49 selected feature names |
| `centroids.csv` | Cluster centroid coordinates |
| `kmeans_artifacts.json` | Model metadata (k, training date, feature list) |

**Output fields**:

| Field | Type | Description |
|---|---|---|
| `kmeans_cluster` | int | Assigned cluster (0–7) |
| `risk_score` | float | Distance to centroid scaled to 0–1 (higher = more anomalous) |
| `Distance_to_Centroid` | float | Raw Euclidean distance |
| `is_outlier` | int | 1 if risk_score ≥ 0.70 threshold |

---

## Phase 2: Statistical Rules v8 (R1–R12)

**Purpose**: Score each transaction on behavior-based fraud signals. Produces a normalized 0–100 score that maps directly to a risk decision.

**Decision thresholds**:

| Score range | Decision |
|---|---|
| < 70 | Accept |
| 70–79 | User Auth |
| 80–89 | Admin Review |
| ≥ 90 | Reject |

**Normalization**: Piecewise mapping from raw score (0–295) to normalized score (0–100), preserving the 70/80/90 decision boundaries without a hard cap:

```
if raw ≤ 90:    normalized = raw
if 90 < raw < 295: normalized = 90 + (raw − 90) × (10 / (295 − 90))
if raw ≥ 295:   normalized = 100
```

See [`docs/guides/03-statistical-rules.md`](03-statistical-rules.md) for each rule's conditions and points.

**Output fields**:

| Field | Description |
|---|---|
| `risk_score_normalized` | Normalized score (0–100) |
| `risk_decision` | Accept / User Auth / Admin Review / Reject |
| `risk_score_raw` | Sum of all rule points before normalization |
| `rule_1` … `rule_12` | Points contributed by each individual rule |
| `explanation` | Human-readable breakdown (e.g. `R2: nighttime +20 \| R11: 3.5× CU +30`) |

---

## Phase 3: Similarity Matching

**Purpose**: Compare the incoming transaction against historical transactions stored in the Silver data lake (Athena) to detect known-good or known-bad patterns.

**Data source**: Athena table `dlh_silver_safe_alpha.safetransactionresults`  
**Window**: 6-month sliding window centered on each transaction date  
**Account**: Alpha account (us-east-2) — cross-account from endpoint in us-east-1

**Comparison logic**:

- 49 fields compared field by field
- Float comparison: absolute difference < 1e-9 (effectively exact)
- `None` / NaN treated as 0 for comparison
- Similarity score = fraction of matching fields (0.0–1.0)
- Best-matching transaction is returned if score ≥ 0.90

**Output fields**:

| Field | Type | Description |
|---|---|---|
| `sim_match_txn_id` | string \| null | ID of the best-matching historical transaction |
| `sim_score` | float \| null | Similarity score (0.0–1.0) |
| `sim_status` | string \| null | `HIGH_SIM` (≥ 0.90), `LOW_SIM` (< 0.90), `NO_HISTORY` |
| `sim_decision` | string \| null | `Accept` if HIGH_SIM, `Reject` if LOW_SIM/NO_HISTORY, null if phase failed |

---

## Final Decision Logic

The `decision` field is derived from combining all three phases:

1. If `sim_decision` is available (similarity phase succeeded):
   - `HIGH_SIM` (score ≥ 0.90) → lean toward Accept
   - Otherwise → use rules-based `risk_decision`
2. Rules decision (`risk_decision`) always present as primary signal
3. K-Means `is_outlier` flag is used as a tiebreaker and for audit context

The exact combination logic is in `endpoint/inference_rules.py` (function `predict_fn`).

---

## Graceful Degradation

The endpoint continues operating even if a phase fails:

| Failure | Behavior |
|---|---|
| Athena query timeout | `sim_*` fields set to `null`; rules decision used |
| Athena permissions error | Same as timeout; error logged to CloudWatch |
| K-Means artifact missing | Rules-only mode; `kmeans_cluster = null` |
| Rules module import error | K-Means cluster + distance returned; `risk_decision = null` |
| Single row parse error | Row excluded (filter mode) or imputed (coerce mode) |

Environment variable `DISABLE_RULES=1` disables the rules phase intentionally (testing use only).
