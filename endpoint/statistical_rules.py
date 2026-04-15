"""
FRAUD DETECTOR — RULES v8
======================================================

Changes vs v7:
- Reduce weight of the most sensitive rules recently:
    * R1 (amount vs user's average): same thresholds (>0.5) but FEWER points (~75% of v7).
    * R3 (first-time to recipient 6h): from 40 → 30 pts.
- Keep piecewise normalization to 0–100 without hard cap and same decision logic.
- R11 remains strong (up to 45 pts) to capture disproportionate amounts vs CU.

Decisions (based on the normalized score):
- <70   -> Accept
- 70–79 -> User Auth
- 80–89 -> Admin Review
- >=90  -> Reject
"""

from __future__ import annotations
import math
from typing import Any, Dict, List
import pandas as pd

# =========================
# Rules configuration
# =========================

# R1: same thresholds as v7, but lower points (~75%)
R1_THRESHOLDS = [0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 3.0, 5.0]
# v7: [2,5,8,12,18,25,35,45,60]
R1_POINTS     = [2, 4, 6, 9, 14, 19, 26, 34, 45]  # last one is >5.0

def _r1_points_from_ratio(ratio: float) -> int:
    if ratio <= R1_THRESHOLDS[0]:
        return 0
    elif ratio <= R1_THRESHOLDS[1]:
        return R1_POINTS[0]
    elif ratio <= R1_THRESHOLDS[2]:
        return R1_POINTS[1]
    elif ratio <= R1_THRESHOLDS[3]:
        return R1_POINTS[2]
    elif ratio <= R1_THRESHOLDS[4]:
        return R1_POINTS[3]
    elif ratio <= R1_THRESHOLDS[5]:
        return R1_POINTS[4]
    elif ratio <= R1_THRESHOLDS[6]:
        return R1_POINTS[5]
    elif ratio <= R1_THRESHOLDS[7]:
        return R1_POINTS[6]
    else:
        return R1_POINTS[7]  # 45

# R11: strong weight (same as v7)
def _r11_points(ratio_cu: float) -> int:
    if ratio_cu > 5:
        return 45
    elif ratio_cu > 3:
        return 30
    elif ratio_cu > 2:
        return 20
    else:
        return 0


# =========================
# Piecewise normalization
# =========================

# Theoretical max with new config (R1 max 45, R3 max 30)
# Sum of maxes: 45 + 20 + 30 + 20 + 25 + 20 + 35 + 15 + 15 + 10 + 45 + 15 = 295
R_MAX = 295

def normalize_score_piecewise(raw: float, r_max: float = R_MAX) -> float:
    """
    Map risk_score_raw to [0,100] WITHOUT a hard cap, preserving 70/80/90 cutoffs.
    - If raw <= 90: score = raw
    - If 90 < raw < r_max: score = 90 + (raw - 90) * (10 / (r_max - 90))
    - If raw >= r_max: score = 100
    """
    if raw <= 90:
        return float(raw)
    if raw >= r_max:
        return 100.0
    return 90.0 + (raw - 90.0) * (10.0 / (r_max - 90.0))

def denormalize_score_piecewise(score: float, r_max: float = R_MAX) -> float:
    """
    Return the raw value corresponding to a given normalized score.
    - If score <= 90: raw = score
    - If 90 < score < 100: raw = 90 + (score - 90) * (r_max - 90) / 10
    - If score >= 100: raw = r_max
    """
    if score <= 90:
        return float(score)
    if score >= 100:
        return float(r_max)
    return 90.0 + (score - 90.0) * (r_max - 90.0) / 10.0


# =========================
# Utilities
# =========================
def _to_float(x: Any) -> float:
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return 0.0
        return float(str(x).replace(",", ""))
    except Exception:
        return 0.0

def _to_int(x: Any) -> int:
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return 0
        return int(float(x))
    except Exception:
        return 0

def classify_risk(score: int) -> str:
    if score >= 90:
        return "Reject"
    elif score >= 80:
        return "Admin Review"
    elif score >= 70:
        return "User Auth"
    else:
        return "Accept"

def _get_user_daily_avg(rec: dict) -> float:
    """
    Prefer the new field 'user_avg_amount_txn_per_active_day_last_6_months'.
    Fallback to the old 'user_avg_amount_ach_txn_per_active_day_last_6_months'.
    """
    cand = rec.get("user_avg_amount_txn_per_active_day_last_6_months", None)
    if cand is None or str(cand).strip() == "":
        cand = rec.get("user_avg_amount_ach_txn_per_active_day_last_6_months", 0)
    try:
        return float(str(cand).replace(",", "")) if cand is not None else 0.0
    except Exception:
        return 0.0
        
# =========================
# Scoring ONE transaction
# =========================
def score_transaction_v8(transaction: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute per-rule contributions, raw, normalized (0–100 without hard cap),
    clipped (for comparison), and a human explanation.
    """
    contrib = {f"rule_{i}": 0 for i in range(1, 13)}
    expl: List[str] = []

    amount = _to_float(transaction.get("amount", 0))
    user_type = str(transaction.get("user_type", "personal") or "personal").strip().lower()
    #user_avg = _to_float(transaction.get("user_avg_amount_txn_per_active_day_last_6_months", 0))
    user_avg = _get_user_daily_avg(transaction)
    
    # ---- Rule 1: ONLY user_avg; from ratio > 0.5 (lower weight) ----
    # if amount > 0 and user_avg > 0:
    #     ratio = amount / user_avg
    #     pts = _r1_points_from_ratio(ratio)
    #     if user_type not in ("personal", "mixed", "mixto"):
    #         pts = int(round(pts * 0.9))
    #     contrib["rule_1"] = pts
    #     if pts > 0:
    #         expl.append(f"R1: {ratio:.2f}× user average ({user_avg:,.2f}) +{pts}")

    # ---- Rule 2: Nighttime ----
    if _to_int(transaction.get("is_night", 0)) == 1:
        contrib["rule_2"] = 20
        expl.append("R2: nighttime +20")

    # ---- Rule 3: First-time to recipient (6h window) — 30 pts ----
    if _to_int(transaction.get("is_first_txn_from_this_olb_user_to_this_recipient_account_q_6h", 0)) == 1:
        contrib["rule_3"] = 30
        expl.append("R3: first-time to recipient (6h) +30")

    # ---- Rule 4: Cancellations in the last week ----
    cancelled_week = _to_int(transaction.get("count_user_cancelled_txn_in_last_week", 0))
    if cancelled_week > 0:
        add = min(20, cancelled_week * 10)
        contrib["rule_4"] = add
        expl.append(f"R4: cancellations {cancelled_week} +{add}")

    # ---- Rule 5: Suspected actions in the current session ----
    suspected_actions = _to_int(transaction.get("count_suspected_actions_in_current_session", 0))
    if suspected_actions > 0:
        add = min(25, suspected_actions * 12)
        contrib["rule_5"] = add
        expl.append(f"R5: suspected actions {suspected_actions} +{add}")

    # ---- Rule 6: High amount vs low historical profile ----
    pct_over_1k = _to_float(transaction.get("pct_txns_over_1k_lst6m", 0))
    if amount > 1000 and pct_over_1k < 0.10:
        contrib["rule_6"] = 20
        expl.append(f"R6: ${amount:,.0f} with {pct_over_1k:.1%} >$1k +20")
    elif amount > 1500 and pct_over_1k < 0.20:
        contrib["rule_6"] = 15
        expl.append(f"R6: ${amount:,.0f} with {pct_over_1k:.1%} >$1k +15")
    elif pct_over_1k > 0.50:
        contrib["rule_6"] = 10
        expl.append(f"R6: high pct >$1k {pct_over_1k:.1%} +10")

    # ---- Rule 7: Burst + volume (exclude batch) ----
    is_batch = _to_int(transaction.get("is_batch", 0))
    if is_batch == 0:
        txn_5m = _to_int(transaction.get("count_all_txn_last_5m", 0))
        total_amount_5m = _to_float(transaction.get("total_amount_all_txn_last_5m", 0))
        if txn_5m > 2:
            contrib["rule_7"] += 20
            expl.append(f"R7: {txn_5m} txns/5m +20")
        elif txn_5m > 1:
            contrib["rule_7"] += 10
            expl.append(f"R7: {txn_5m} txns/5m +10")

        # if user_avg > 0 and total_amount_5m > 0:
        #     if total_amount_5m > user_avg * 3:
        #         contrib["rule_7"] += 15
        #         expl.append(f"R7+: 5m volume ${total_amount_5m:,.0f} (>3×) +15")
        #     elif total_amount_5m > user_avg * 2:
        #         contrib["rule_7"] += 8
        #         expl.append(f"R7+: 5m volume ${total_amount_5m:,.0f} (>2×) +8")

    # ---- Rule 8: History with recipient (2 months) ----
    count_to_recipient = _to_int(transaction.get("count_txn_to_recipient_account_in_last_2_months", 0))
    if count_to_recipient == 0:
        contrib["rule_8"] = 15
        expl.append("R8: first time to recipient (2m) +15")
    elif count_to_recipient <= 2:
        contrib["rule_8"] = 8
        expl.append(f"R8: few to recipient ({count_to_recipient}) +8")
    elif count_to_recipient <= 5:
        contrib["rule_8"] = 3
        expl.append(f"R8: occasional to recipient ({count_to_recipient}) +3")

    # ---- Rule 9: Contact details updated ----
    # phone_updated = _to_int(transaction.get("is_personal_user_phone_primary_updated_last_week", 0))
    # email_updated = _to_int(transaction.get("is_personal_user_email_primary_updated_last_week", 0))
    # if phone_updated == 1 or email_updated == 1:
    #     contrib["rule_9"] = 15
    #     changes = []
    #     if phone_updated == 1:
    #         changes.append("phone")
    #     if email_updated == 1:
    #         changes.append("email")
    #     expl.append(f"R9: updated ({', '.join(changes)}) +15")

    # ---- Rule 10: Weekend ----
    if _to_int(transaction.get("weekend", 0)) == 1:
        contrib["rule_10"] = 10
        expl.append("R10: weekend +10")

    # ---- Rule 11: Ratio vs CU (heavy) ----
    ratio_cu = _to_float(transaction.get("txn_amount_vs_cu_avg_amount_ach_txn_in_last_6_months", 0))
    pts11 = _r11_points(ratio_cu)
    if pts11 > 0:
        contrib["rule_11"] = pts11
        expl.append(f"R11: {ratio_cu:.2f}× CU +{pts11}")

    # ---- Rule 12: User tenure ----
    recency_days = _to_int(transaction.get("recency_user_created_days", 9999))
    if recency_days < 30:
        contrib["rule_12"] = 15
        expl.append(f"R12: user {recency_days} days +15")
    elif recency_days < 90:
        contrib["rule_12"] = 8
        expl.append(f"R12: user {recency_days} days +8")

    # ---- Totals and decision ----
    risk_score_raw = int(sum(contrib.values()))
    risk_score_clipped = int(min(risk_score_raw, 100))  # comparative only
    risk_score_normalized = int(round(normalize_score_piecewise(risk_score_raw)))
    risk_decision = classify_risk(risk_score_normalized)
    explanation = " | ".join(expl) if expl else "Normal transaction"

    return {
        **contrib,
        "risk_score_raw": risk_score_raw,
        "risk_score_clipped": risk_score_clipped,
        "risk_score_normalized": risk_score_normalized,
        "risk_decision": risk_decision,
        "explanation": explanation,
    }


# =========================
# Scoring a DataFrame
# =========================
def score_dataframe_v8(df: "pd.DataFrame") -> "pd.DataFrame":
    """Apply score_transaction_v8 row by row and return a DF with useful columns."""
    # Detect an ID column if present; otherwise create an incremental one
    id_col = None
    for c in ("TransactionID", "transaction_id", "txn_id", "id"):
        if c in df.columns:
            id_col = c
            break
    if id_col is None:
        df = df.copy()
        df["TransactionID"] = range(1, len(df) + 1)
        id_col = "TransactionID"

    recs = df.to_dict(orient="records")
    rows: List[Dict[str, Any]] = []
    for rec in recs:
        out = score_transaction_v8(rec)
        rows.append({
            "TransactionID": rec.get(id_col),
            "amount": _to_float(rec.get("amount", 0)),
            **out
        })

    scored = pd.DataFrame(rows)
    rule_cols = [f"rule_{i}" for i in range(1, 13)]
    return scored[[
        "TransactionID", "amount", *rule_cols,
        "risk_score_raw", "risk_score_clipped", "risk_score_normalized",
        "risk_decision", "explanation"
    ]]


# =========================
# CLI / Direct use
# =========================
if __name__ == "__main__":
    import argparse, os

    parser = argparse.ArgumentParser(
        description="Fraud Detector — Rules v8 (R1/R3 lower weight; piecewise normalization without hard cap)"
    )
    parser.add_argument("--csv_in", type=str, default="", help="Path to a CSV to score.")
    parser.add_argument("--excel_insumos", type=str, default="", help="Path to Insumos.xlsx (to use the 'Fraud' sheet).")
    parser.add_argument("--sheet_name", type=str, default="Fraud", help="Sheet name (default 'Fraud').")
    parser.add_argument("--out", type=str, default="scored_output_v8.csv", help="Output CSV path for results.")
    args = parser.parse_args()

    if args.csv_in:
        df_in = pd.read_csv(args.csv_in)
        df_out = score_dataframe_v8(df_in)
        df_out.to_csv(args.out, index=False)
        print(f"[OK] CSV scored: {args.csv_in}")
        print(f"[OK] Results saved to: {os.path.abspath(args.out)}")

    elif args.excel_insumos:
        df_in = pd.read_excel(args.excel_insumos, sheet_name=args.sheet_name)
        df_out = score_dataframe_v8(df_in)
        df_out.to_csv(args.out, index=False)
        print(f"[OK] Excel scored: {args.excel_insumos} (sheet: {args.sheet_name})")
        print(f"[OK] Results saved to: {os.path.abspath(args.out)}")

    else:
        print("Usage:")
        print("  python statistical_rules.py --csv_in data_collection_merged.csv --out data_collection_scored_v8.csv")
        print("  python statistical_rules.py --excel_insumos Insumos.xlsx --sheet_name Fraud --out fraud_scored_v8.csv")
