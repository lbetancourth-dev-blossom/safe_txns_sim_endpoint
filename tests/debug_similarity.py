#!/usr/bin/env python3
"""
Debug similarity matching for transaction 1032495 (user 597178).
"""
import sys
import os
from datetime import datetime, timezone
sys.path.insert(0, 'endpoint')

from similarity_matcher import (
    find_similar_transaction,
    load_reference_data_from_athena,
    EXACT_MATCH_FIELDS,
    _extract_exact_fields,
    _calculate_exact_field_match
)

# Transaction data from test_escenarios.csv (user 597178, TransactionID 1032495)
query_result = {
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
print("DEBUG: Similarity Matching for Transaction 1032495")
print("=" * 80)

# Parameters
idolbuser = 597178
transaction_datetime = datetime.fromisoformat("2026-06-18T09:30:23").replace(tzinfo=timezone.utc)
window_months = 6
timeout_seconds = 10

print(f"\n📋 Input Parameters:")
print(f"   User ID: {idolbuser}")
print(f"   Transaction Date: {transaction_datetime}")
print(f"   Window (months): {window_months}")
print(f"   Timeout (seconds): {timeout_seconds}")
print(f"   Query Fields: {len(query_result)} fields")

# Step 1: Extract exact fields
print(f"\n1️⃣  Extracting exact fields...")
query_fields = _extract_exact_fields(query_result, EXACT_MATCH_FIELDS)
print(f"   ✓ Extracted {len(query_fields)} fields")
print(f"   Fields: {list(query_fields.keys())[:5]}... (showing first 5)")

# Step 2: Load reference data from Athena
from dateutil.relativedelta import relativedelta
window_start = transaction_datetime - relativedelta(months=window_months)
print(f"\n2️⃣  Loading reference data from Athena...")
print(f"   Query: user={idolbuser}, date range=[{window_start}, {transaction_datetime}]")

try:
    ref_df, ref_vectors, ref_labels, ref_ids = load_reference_data_from_athena(
        idolbuser=idolbuser,
        window_months=window_months,
        transaction_datetime=transaction_datetime,
        timeout_seconds=timeout_seconds,
        force_reload=True
    )

    if ref_df is None or len(ref_df) == 0:
        print(f"   ⚠️  No data from Athena! (ref_df is None or empty)")
        print(f"   Possible causes:")
        print(f"     - No transactions for this user in the date window")
        print(f"     - Athena connectivity issue")
        print(f"     - Wrong database/table configuration")
    else:
        print(f"   ✓ Loaded {len(ref_df)} reference transactions from Athena")
        print(f"   Columns: {list(ref_df.columns)[:5]}... (showing first 5)")
        print(f"   Sample row 0:")
        for col in list(ref_df.columns)[:3]:
            print(f"     {col}: {ref_df.iloc[0][col]}")

        # Step 3: Calculate exact field match
        print(f"\n3️⃣  Calculating exact field match...")
        import numpy as np
        scores, best_idx = _calculate_exact_field_match(
            query_fields=query_fields,
            ref_rows=ref_df,
            field_list=EXACT_MATCH_FIELDS
        )

        if len(scores) > 0:
            print(f"   ✓ Calculated {len(scores)} match scores")
            for i, (score, idx) in enumerate(zip(scores[:3], range(min(3, len(scores))))):
                txn_id = ref_ids[idx] if idx < len(ref_ids) else "?"
                print(f"     [{i}] txn_id={txn_id}, score={score:.4f}")

            if best_idx >= 0:
                print(f"\n   🏆 Best match:")
                print(f"     Index: {best_idx}")
                print(f"     Transaction ID: {ref_ids[best_idx]}")
                print(f"     Score: {scores[best_idx]:.4f}")
                print(f"     Status: {ref_labels[best_idx]}")
        else:
            print(f"   ⚠️  No match scores calculated!")

except Exception as e:
    print(f"   ✗ ERROR: {type(e).__name__}: {repr(e)}")
    import traceback
    traceback.print_exc()

# Step 4: Call find_similar_transaction directly
print(f"\n4️⃣  Calling find_similar_transaction()...")
try:
    result = find_similar_transaction(
        query_result=query_result,
        threshold=0.90,
        idolbuser=idolbuser,
        window_months=window_months,
        timeout_seconds=timeout_seconds,
        transaction_datetime=transaction_datetime
    )

    print(f"   ✓ Result received:")
    print(f"     sim_match_txn_id: {result.get('sim_match_txn_id')}")
    print(f"     sim_score: {result.get('sim_score')}")
    print(f"     sim_status: {result.get('sim_status')}")
    print(f"     sim_decision: {result.get('sim_decision')}")

    if result.get('sim_match_txn_id') is None:
        print(f"\n   ⚠️  No match found! Possible causes:")
        print(f"     - No reference data from Athena")
        print(f"     - No fields match exactly")
        print(f"     - Score below threshold (0.90)")

except Exception as e:
    print(f"   ✗ ERROR: {type(e).__name__}: {repr(e)}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
