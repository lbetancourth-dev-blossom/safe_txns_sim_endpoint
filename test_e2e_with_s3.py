#!/usr/bin/env python3
"""
End-to-End Test: transactions_test.csv → K-means → Similarity with S3
"""
import os
import sys
import pandas as pd
import numpy as np
from collections import Counter

# Add endpoint to path
sys.path.insert(0, 'endpoint')

# Set environment variables
os.environ['SIMILARITY_THRESHOLD'] = '0.90'
os.environ['SIMILARITY_S3_BUCKET'] = 'blossom-analytics-safe-dev-nv'
os.environ['SIMILARITY_S3_KEY'] = 'safe_txns/data/similarity/SafeTransactionResults.csv'
os.environ['AWS_PROFILE'] = 'blossom-dev'

print("="*100)
print("END-TO-END TEST: transactions_test.csv → Inference → Similarity")
print("="*100)

# Load test data
print("\n📥 Loading test data...")
test_df = pd.read_csv('data/transactions_test.csv')
print(f"✓ Loaded {len(test_df)} test transactions")

# For this test, we'll use the ACTUAL inference_rules.py
# But we need to mock the model artifacts since we're testing locally

# Option 1: Run a subset through actual inference
# Option 2: Mock the K-means output with realistic num__/cat__ features

# Let's do Option 2 for speed - create mock K-means output
print("\n🔄 Creating mock K-means output...")

def create_mock_kmeans_output(row):
    """
    Create a mock decisionResult structure from raw transaction data.
    This simulates what inference_rules.py would produce.
    """
    # Extract and process features
    decision_result = {}
    
    # Numerical features (num__*)
    decision_result['num__amount'] = float(row.get('amount', 0))
    decision_result['num__is_night'] = float(row.get('is_night', 0))
    decision_result['num__hour_sin'] = float(row.get('hour_sin', 0))
    decision_result['num__hour_cos'] = float(row.get('hour_cos', 0))
    decision_result['num__day_of_week_cos'] = float(row.get('day_of_week_cos', 0))
    decision_result['num__count_all_txn_last_5m'] = float(row.get('count_all_txn_last_5m', 0))
    decision_result['num__total_amount_all_txn_last_5m'] = float(row.get('total_amount_all_txn_last_5m', 0) if pd.notna(row.get('total_amount_all_txn_last_5m')) else 0)
    decision_result['num__count_txn_to_recipient_account_last_5m'] = float(row.get('count_txn_to_recipient_account_last_5m', 0))
    decision_result['num__total_amount_txn_to_recipient_account_last_5m'] = float(row.get('total_amount_txn_to_recipient_account_last_5m', 0) if pd.notna(row.get('total_amount_txn_to_recipient_account_last_5m')) else 0)
    decision_result['num__count_txn_to_recipient_account_in_last_2_months'] = float(row.get('count_txn_to_recipient_account_in_last_2_months', 0))
    decision_result['num__is_first_txn_from_this_olb_user_to_this_recipient_account_q_6h'] = float(row.get('is_first_txn_from_this_olb_user_to_this_recipient_account_q_6h', 0))
    decision_result['num__amount_coef_var_lst6m'] = float(row.get('amount_coef_var_lst6m', 0) if pd.notna(row.get('amount_coef_var_lst6m')) else 0)
    decision_result['num__pct_txns_under_100_lst6m'] = float(row.get('pct_txns_under_100_lst6m', 0))
    decision_result['num__pct_txns_over_1k_lst6m'] = float(row.get('pct_txns_over_1k_lst6m', 0))
    decision_result['num__user_avg_amount_txn_per_active_day_last_6_months'] = float(row.get('user_avg_amount_txn_per_active_day_last_6_months', 0))
    decision_result['num__count_user_all_txn_in_last_6_months'] = float(row.get('count_user_all_txn_in_last_6_months', 0))
    decision_result['num__count_user_cancelled_txn_in_last_week'] = float(row.get('count_user_cancelled_txn_in_last_week', 0))
    decision_result['num__count_user_cancelled_txn_in_last_month'] = float(row.get('count_user_cancelled_txn_in_last_month', 0))
    decision_result['num__count_user_potential_fraud_txn_in_last_2_months'] = float(row.get('count_user_potential_fraud_txn_in_last_2_months', 0))
    decision_result['num__recency_user_created_days'] = float(row.get('recency_user_created_days', 0) if pd.notna(row.get('recency_user_created_days')) else 0)
    decision_result['num__count_suspected_actions_in_current_session'] = float(row.get('count_suspected_actions_in_current_session', 0))
    decision_result['num__total_actions_session'] = float(row.get('total_actions_session', 0))
    decision_result['num__is_auth_email_session'] = float(row.get('is_auth_email_session', 0))
    decision_result['num__is_auth_phone_session'] = float(row.get('is_auth_phone_session', 0))
    decision_result['num__total_accounts'] = float(row.get('total_accounts', 0))
    decision_result['num__user_age'] = float(row.get('user_age', 0) if pd.notna(row.get('user_age')) else 0)
    decision_result['num__is_amount_greater_than_cu_p95_amount_ach_txn_in_last_6_months'] = float(row.get('is_amount_greater_than_cu_p95_amount_ach_txn_in_last_6_months', 0))
    decision_result['num__txn_amount_vs_cu_avg_amount_ach_txn_in_last_6_months'] = float(row.get('txn_amount_vs_cu_avg_amount_ach_txn_in_last_6_months', 0) if pd.notna(row.get('txn_amount_vs_cu_avg_amount_ach_txn_in_last_6_months')) else 0)
    decision_result['num__is_batch'] = float(row.get('is_batch', 0))
    decision_result['num__amt_vs_user_ach_avg_day'] = float(row.get('amt_vs_user_ach_avg_day', 0) if pd.notna(row.get('amt_vs_user_ach_avg_day')) else 0)
    decision_result['num__ach_count_share_6m'] = float(row.get('ach_count_share_6m', 0))
    
    # Categorical features (cat__*) - one-hot encoded
    proc_type = row.get('TransactionProcessingType', '')
    decision_result['cat__TransactionProcessingType_Intime'] = 1.0 if proc_type == 'Intime' else 0.0
    decision_result['cat__TransactionProcessingType_Intime_From_Recurrent'] = 1.0 if proc_type == 'Intime From Recurrent' else 0.0
    decision_result['cat__TransactionProcessingType_Recurrent'] = 1.0 if proc_type == 'Recurrent' else 0.0
    decision_result['cat__TransactionProcessingType_Schedule'] = 1.0 if proc_type == 'Schedule' else 0.0
    
    origin = row.get('TransactionOrigin', '')
    decision_result['cat__TransactionOrigin_External Internal'] = 1.0 if origin == 'External Internal' else 0.0
    decision_result['cat__TransactionOrigin_Internal External'] = 1.0 if origin == 'Internal External' else 0.0
    decision_result['cat__TransactionOrigin_M2m External'] = 1.0 if origin == 'M2m External' else 0.0
    
    category = row.get('TransactionCategory', '')
    decision_result['cat__TransactionCategory_SEND_MONEY_ACH'] = 1.0 if category == 'SEND_MONEY_ACH' else 0.0
    decision_result['cat__TransactionCategory_SEND_MONEY_BATCH_PAYMENT_ACH'] = 1.0 if category == 'SEND_MONEY_BATCH_PAYMENT_ACH' else 0.0
    decision_result['cat__TransactionCategory_SEND_MONEY_PAYROLL_ACH'] = 1.0 if category == 'SEND_MONEY_PAYROLL_ACH' else 0.0
    decision_result['cat__TransactionCategory_SINGLE_COLLECTION_ACH'] = 1.0 if category == 'SINGLE_COLLECTION_ACH' else 0.0
    decision_result['cat__TransactionCategory_TRANSFER_EXTERNAL_TO_LOAN_ACH'] = 1.0 if category == 'TRANSFER_EXTERNAL_TO_LOAN_ACH' else 0.0
    decision_result['cat__TransactionCategory_TRANSFER_INTERNAL_EXTERNAL_ACH'] = 1.0 if category == 'TRANSFER_INTERNAL_EXTERNAL_ACH' else 0.0
    
    user_type = row.get('user_type', '')
    decision_result['cat__user_type_mixed'] = 1.0 if user_type == 'mixed' else 0.0
    decision_result['cat__user_type_personal'] = 1.0 if user_type == 'personal' else 0.0
    
    access = row.get('access', '')
    decision_result['cat__access_DESKTOP'] = 1.0 if access == 'DESKTOP' else 0.0
    decision_result['cat__access_MOBILE'] = 1.0 if access == 'MOBILE' else 0.0
    decision_result['cat__access_missing'] = 1.0 if access == '' or pd.isna(access) else 0.0
    
    # Mock K-means post-processing (NOT used for similarity matching)
    decision_result['Cluster'] = np.random.randint(0, 3)
    decision_result['Distance_to_Centroid'] = np.random.uniform(5, 15)
    decision_result['risk_score'] = 55  # Mock score
    decision_result['risk_decision'] = 'User Auth'
    decision_result['is_outlier'] = 0
    
    return decision_result

# Process a subset of test transactions
test_sample = test_df.head(5)  # Test with first 5 transactions

results = []

print(f"\n🧪 Processing {len(test_sample)} transactions through similarity matching...\n")

from similarity_matcher import find_similar_transaction, load_reference_data_from_s3

# Load reference data once
print("📥 Loading S3 reference data...")
ref_df, ref_vectors, ref_labels, ref_ids = load_reference_data_from_s3(force_reload=True)
print(f"✓ Loaded {len(ref_vectors)} reference transactions")
print(f"✓ Status distribution: SAFE={sum(1 for l in ref_labels if l=='SAFE')}, RISKY={sum(1 for l in ref_labels if l=='RISKY')}\n")

threshold = 0.90

for idx, row in test_sample.iterrows():
    txn_id = row['TransactionID']
    
    print(f"{'-'*100}")
    print(f"Transaction #{idx+1}: ID={txn_id}")
    print(f"{'-'*100}")
    
    # Create mock K-means output
    decision_result = create_mock_kmeans_output(row)
    
    print(f"  Amount: ${decision_result['num__amount']:.2f}")
    print(f"  Category: {row.get('TransactionCategory', 'N/A')}")
    print(f"  Mock K-means: risk_score={decision_result['risk_score']}, decision={decision_result['risk_decision']}")
    
    # Find similar transaction
    sim_result = find_similar_transaction(
        query_result=decision_result,
        threshold=threshold
    )
    
    print(f"\n  Similarity Result:")
    print(f"    matched: {sim_result['matched']}")
    print(f"    similarity_score: {sim_result['similarity_score']:.4f}")
    print(f"    status_warning: {sim_result['status_warning']}")
    
    if sim_result['matched'] and sim_result['similarity_score'] >= threshold:
        # Override with similarity-based decision
        final_score = 70
        final_decision = 'Accept' if sim_result['status_warning'] == 'SAFE' else 'Reject'
        override = True
        print(f"\n  ✓ SIMILARITY OVERRIDE:")
        print(f"    final_risk_score: {final_score} (from {decision_result['risk_score']})")
        print(f"    final_risk_decision: {final_decision} (from {decision_result['risk_decision']})")
        print(f"    reason: Matched S3 status '{sim_result['status_warning']}' with {sim_result['similarity_score']:.4f} similarity")
    else:
        # Keep K-means decision
        final_score = decision_result['risk_score']
        final_decision = decision_result['risk_decision']
        override = False
        print(f"\n  ○ K-MEANS DECISION (no similarity match):")
        print(f"    final_risk_score: {final_score}")
        print(f"    final_risk_decision: {final_decision}")
    
    results.append({
        'TransactionID': txn_id,
        'amount': decision_result['num__amount'],
        'category': row.get('TransactionCategory', 'N/A'),
        'kmeans_score': decision_result['risk_score'],
        'kmeans_decision': decision_result['risk_decision'],
        'similarity_matched': sim_result['matched'],
        'similarity_score': sim_result['similarity_score'],
        'matched_status': sim_result['status_warning'],
        'override': override,
        'final_score': final_score,
        'final_decision': final_decision
    })

print(f"\n{'='*100}")
print("SUMMARY")
print(f"{'='*100}\n")

results_df = pd.DataFrame(results)
print(results_df.to_string(index=False))

print(f"\n📊 Statistics:")
print(f"  Total transactions: {len(results_df)}")
print(f"  Similarity matched (>= {threshold}): {sum(results_df['similarity_matched'])}/{len(results_df)}")
print(f"  Decisions overridden: {sum(results_df['override'])}/{len(results_df)}")
if sum(results_df['similarity_matched']) > 0:
    print(f"  Average similarity score (matched): {results_df[results_df['similarity_matched']]['similarity_score'].mean():.4f}")

print(f"\n{'='*100}")
print("✅ E2E Test Complete!")
print(f"{'='*100}")
