#!/usr/bin/env python3
"""
Test exact field matching with real Athena metadata values.
"""
import pandas as pd
import numpy as np
import sys
sys.path.insert(0, 'endpoint')

from similarity_matcher import _extract_exact_fields, _calculate_exact_field_match, EXACT_MATCH_FIELDS

# Input data from K-Means (user 597178)
query_input = {
    'num__amount': 0.028759879362860796,
    'num__is_night': -0.224180211168068,
    'num__hour_sin': 1.0343378933149832,
    'num__hour_cos': -0.06547529200862119,
    'num__day_of_week_cos': 0.9403709235745786,
    'num__count_all_txn_last_5m': -0.2670236767785968,
    'num__total_amount_all_txn_last_5m': -0.23001800279551668,
    'num__count_txn_to_recipient_account_last_5m': -0.19822356683283876,
    'num__total_amount_txn_to_recipient_account_last_5m': -0.07048991450586796,
    'num__count_txn_to_recipient_account_in_last_2_months': -0.18583760807657743,
    'num__is_first_txn_from_this_olb_user_to_this_recipient_account_q_6h': 0.6036563186860769,
    'num__amount_coef_var_lst6m': 0.26835398981672637,
    'num__pct_txns_under_100_lst6m': 0.26658935144175544,
    'num__pct_txns_over_1k_lst6m': 0.267230290310821,
    'num__user_avg_amount_txn_per_active_day_last_6_months': -0.23601266044264962,
    'num__count_user_all_txn_in_last_6_months': -0.3082703596124353,
    'num__count_user_cancelled_txn_in_last_week': 1.1282179753800947,
    'num__count_user_cancelled_txn_in_last_month': 0.5377776702010083,
    'num__count_user_potential_fraud_txn_in_last_2_months': 0.32769554469957163,
    'num__recency_user_created_days': 0.11231612838743135,
    'num__count_suspected_actions_in_current_session': 0.7594490986880102,
    'num__total_actions_session': 0.7619225947287157,
    'num__is_auth_email_session': 0.7593037405680916,
    'num__is_auth_phone_session': 0.7590667267563235,
    'num__total_accounts': 0.3533482252295057,
    'num__user_age': 0.8412738339824711,
    'num__is_amount_greater_than_cu_p95_amount_ach_txn_in_last_6_months': 3.017730236245145,
    'num__txn_amount_vs_cu_avg_amount_ach_txn_in_last_6_months': 0.01177517860324851,
    'num__is_batch': -0.46684171215667125,
    'num__amt_vs_user_ach_avg_day': 0.06962478376502793,
    'num__ach_count_share_6m': 0.17539310067728195,
    'cat__TransactionProcessingType_Intime': 1.0,
    'cat__TransactionProcessingType_Intime_From_Recurrent': 0.0,
    'cat__TransactionProcessingType_Recurrent': 0.0,
    'cat__TransactionProcessingType_Schedule': 0.0,
    'cat__TransactionOrigin_External Internal': 0.0,
    'cat__TransactionOrigin_Internal External': 1.0,
    'cat__TransactionOrigin_M2m External': 0.0,
    'cat__TransactionCategory_SEND_MONEY_ACH': 0.0,
    'cat__TransactionCategory_SEND_MONEY_BATCH_PAYMENT_ACH': 0.0,
    'cat__TransactionCategory_SEND_MONEY_PAYROLL_ACH': 0.0,
    'cat__TransactionCategory_SINGLE_COLLECTION_ACH': 0.0,
    'cat__TransactionCategory_TRANSFER_EXTERNAL_TO_LOAN_ACH': 0.0,
    'cat__TransactionCategory_TRANSFER_INTERNAL_EXTERNAL_ACH': 1.0,
    'cat__user_type_mixed': 0.0,
    'cat__user_type_personal': 1.0,
    'cat__access_DESKTOP': 0.0,
    'cat__access_MOBILE': 1.0,
    'cat__access_missing': 0.0,
}

print("=" * 80)
print("EXACT FIELD MATCHING TEST")
print("=" * 80)
print(f"\nInput User: 597178 (K-Means processed values)")
print(f"Input Fields: {len(query_input)} fields")
print(f"Expected Fields: {len(EXACT_MATCH_FIELDS)} fields")

# Extract exact fields from input
extracted = _extract_exact_fields(query_input, EXACT_MATCH_FIELDS)
print(f"\n✓ Extracted {len(extracted)} fields from input")

# Create mock Athena reference data
# Scenario 1: Perfect match (same values as input)
ref_data_perfect = query_input.copy()
ref_data_perfect['transactionid'] = 1816246
ref_data_perfect['statuswarning'] = 'SAFE'

# Scenario 2: 50% match (half fields different)
ref_data_partial = query_input.copy()
for i, field in enumerate(EXACT_MATCH_FIELDS):
    if i % 2 == 0:  # Change every other field
        if field.startswith('num__'):
            ref_data_partial[field] = ref_data_partial[field] + 0.1  # Slightly different
        else:
            # For categorical, flip between 0.0 and 1.0
            ref_data_partial[field] = 1.0 - ref_data_partial[field]
ref_data_partial['transactionid'] = 1815258
ref_data_partial['statuswarning'] = 'User Auth'

# Scenario 3: No match (all different)
ref_data_nomatch = {field: 0.0 for field in EXACT_MATCH_FIELDS}
ref_data_nomatch['transactionid'] = 1814000
ref_data_nomatch['statuswarning'] = 'Admin Review'

# Create DataFrame with 3 reference rows
ref_df = pd.DataFrame([
    ref_data_perfect,
    ref_data_partial,
    ref_data_nomatch
])

print(f"\n📊 Reference Data: {len(ref_df)} Athena transactions")
print(f"   Row 0: transactionid={ref_df.iloc[0]['transactionid']} (perfect match scenario)")
print(f"   Row 1: transactionid={ref_df.iloc[1]['transactionid']} (50% match scenario)")
print(f"   Row 2: transactionid={ref_df.iloc[2]['transactionid']} (no match scenario)")

# Run exact field matching
print(f"\n🔍 Running exact field matching...")
scores, best_idx = _calculate_exact_field_match(
    query_fields=extracted,
    ref_rows=ref_df,
    field_list=EXACT_MATCH_FIELDS
)

print(f"\n✅ RESULTS:")
print(f"\n   Scores for each reference row:")
for i, score in enumerate(scores):
    txn_id = ref_df.iloc[i]['transactionid']
    status = ref_df.iloc[i]['statuswarning']
    matched_fields = int(score * len(EXACT_MATCH_FIELDS))
    print(f"   [{i}] txn={txn_id} | score={score:.4f} | {matched_fields}/{len(EXACT_MATCH_FIELDS)} fields matched | status={status}")

best_score = scores[best_idx]
best_txn_id = ref_df.iloc[best_idx]['transactionid']
best_status = ref_df.iloc[best_idx]['statuswarning']
best_fields = int(best_score * len(EXACT_MATCH_FIELDS))

print(f"\n🏆 BEST MATCH:")
print(f"   Index: {best_idx}")
print(f"   Transaction ID: {best_txn_id}")
print(f"   Score: {best_score:.4f} ({best_fields}/{len(EXACT_MATCH_FIELDS)} fields)")
print(f"   Status: {best_status}")

# Check threshold
threshold = 0.90
matched = best_score >= threshold
print(f"\n📌 THRESHOLD CHECK:")
print(f"   Threshold: {threshold}")
print(f"   Score {best_score:.4f} >= {threshold}? {matched}")

if matched:
    print(f"\n✅ MATCH ACCEPTED")
    result = {
        "sim_match_txn_id": best_txn_id,
        "sim_score": best_score,
        "sim_status": best_status,
        "sim_decision": "match"
    }
else:
    print(f"\n❌ MATCH REJECTED (below threshold)")
    result = {
        "sim_match_txn_id": None,
        "sim_score": best_score,
        "sim_status": None,
        "sim_decision": None
    }

print(f"\n📋 RESPONSE:")
for key, value in result.items():
    print(f"   {key}: {value}")

print("\n" + "=" * 80)
