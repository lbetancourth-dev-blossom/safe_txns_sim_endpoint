#!/usr/bin/env python3
"""
Local Integration Test - Simulate full endpoint flow without deployment

This script simulates the complete inference pipeline locally:
1. Load transaction data from data/transactions_test.csv
2. Load reference data from S3 (or local cache)
3. Process through similarity matching
4. Display results with similarity decisions

Usage:
    export AWS_PROFILE=blossom-dev
    python3 test_local_integration.py [--num-txns 5]
"""

import os
import sys
import argparse
import pandas as pd
import json
from pathlib import Path

# Add endpoint directory to path
sys.path.insert(0, 'endpoint')

# Set AWS profile
os.environ['AWS_PROFILE'] = 'blossom-dev'

# Configuration
os.environ['SIMILARITY_THRESHOLD'] = '0.85'
os.environ['SIMILARITY_S3_BUCKET'] = 'blossom-analytics-safe-dev-nv'
os.environ['SIMILARITY_S3_KEY'] = 'safe_txns/data/similarity/SafeTransactionResults.csv'

print("=" * 100)
print("LOCAL INTEGRATION TEST - SIMILARITY MATCHING")
print("=" * 100)

# Import similarity matcher
try:
    from similarity_matcher import find_similar_transaction
    print("\n✓ similarity_matcher module loaded")
except ImportError as e:
    print(f"\n❌ Error importing similarity_matcher: {e}")
    sys.exit(1)

# Import schema validator
try:
    from schema_validator import validate_features_only, get_schema_info
    print("✓ schema_validator module loaded")
except ImportError as e:
    print(f"\n❌ Error importing schema_validator: {e}")
    sys.exit(1)


def create_mock_features(row):
    """
    Create mock preprocessed features from raw transaction data.
    
    In real endpoint, these come from inference_rules.py preprocessing.
    For this test, we create mock values.
    """
    # Mock numerical features (31 total)
    features = {
        # Basic features
        "num__amount": float(row.get("amount", 100.0)),
        "num__is_night": 0.0,
        "num__hour_sin": 0.5,
        "num__hour_cos": 0.866,
        "num__day_of_week_cos": 0.5,
        
        # Transaction velocity
        "num__count_all_txn_last_5m": float(row.get("count_all_txn_last_5m", 1)),
        "num__total_amount_all_txn_last_5m": float(row.get("total_amount_all_txn_last_5m", 0)),
        "num__count_txn_to_recipient_account_last_5m": float(row.get("count_txn_to_recipient_account_last_5m", 0)),
        "num__total_amount_txn_to_recipient_account_last_5m": float(row.get("total_amount_txn_to_recipient_account_last_5m", 0)),
        "num__count_txn_to_recipient_account_in_last_2_months": float(row.get("count_txn_to_recipient_account_in_last_2_months", 0)),
        "num__is_first_txn_from_this_olb_user_to_this_recipient_account_q_6h": 0.0,
        
        # User statistics
        "num__amount_coef_var_lst6m": float(row.get("amount_coef_var_lst6m", 0)),
        "num__pct_txns_under_100_lst6m": float(row.get("pct_txns_under_100_lst6m", 0)),
        "num__pct_txns_over_1k_lst6m": float(row.get("pct_txns_over_1k_lst6m", 0)),
        "num__user_avg_amount_txn_per_active_day_last_6_months": float(row.get("user_avg_amount_txn_per_active_day_last_6_months", 0)),
        "num__count_user_all_txn_in_last_6_months": float(row.get("count_user_all_txn_in_last_6_months", 0)),
        "num__count_user_cancelled_txn_in_last_week": float(row.get("count_user_cancelled_txn_in_last_week", 0)),
        "num__count_user_cancelled_txn_in_last_month": float(row.get("count_user_cancelled_txn_in_last_month", 0)),
        "num__count_user_potential_fraud_txn_in_last_2_months": float(row.get("count_user_potential_fraud_txn_in_last_2_months", 0)),
        "num__recency_user_created_days": float(row.get("recency_user_created_days", 100)),
        
        # Session features
        "num__count_suspected_actions_in_current_session": float(row.get("count_suspected_actions_in_current_session", 0)),
        "num__total_actions_session": float(row.get("total_actions_session", 1)),
        "num__is_auth_email_session": 0.0,
        "num__is_auth_phone_session": 0.0,
        
        # User profile
        "num__total_accounts": float(row.get("total_accounts", 1)),
        "num__user_age": float(row.get("user_age", 30)),
        
        # CU comparisons
        "num__is_amount_greater_than_cu_p95_amount_ach_txn_in_last_6_months": 0.0,
        "num__txn_amount_vs_cu_avg_amount_ach_txn_in_last_6_months": 0.01,
        "num__is_batch": 0.0,
        "num__amt_vs_user_ach_avg_day": 0.01,
        "num__ach_count_share_6m": float(row.get("ach_count_share_6m", 0)),
    }
    
    # Mock categorical features (18 total)
    cat_features = {
        "cat__TransactionProcessingType_Intime": 1.0 if row.get("TransactionProcessingType") == "Intime" else 0.0,
        "cat__TransactionProcessingType_Intime_From_Recurrent": 0.0,
        "cat__TransactionProcessingType_Recurrent": 0.0,
        "cat__TransactionProcessingType_Schedule": 0.0,
        "cat__TransactionOrigin_External Internal": 0.0,
        "cat__TransactionOrigin_Internal External": 1.0,
        "cat__TransactionOrigin_M2m External": 0.0,
        "cat__TransactionCategory_SEND_MONEY_ACH": 1.0,
        "cat__TransactionCategory_SEND_MONEY_BATCH_PAYMENT_ACH": 0.0,
        "cat__TransactionCategory_SEND_MONEY_PAYROLL_ACH": 0.0,
        "cat__TransactionCategory_SINGLE_COLLECTION_ACH": 0.0,
        "cat__TransactionCategory_TRANSFER_EXTERNAL_TO_LOAN_ACH": 0.0,
        "cat__TransactionCategory_TRANSFER_INTERNAL_EXTERNAL_ACH": 0.0,
        "cat__user_type_mixed": 0.0,
        "cat__user_type_personal": 1.0,
        "cat__access_DESKTOP": 0.0,
        "cat__access_MOBILE": 1.0,
        "cat__access_missing": 0.0,
    }
    
    features.update(cat_features)
    return features


def main():
    parser = argparse.ArgumentParser(description='Test similarity integration locally')
    parser.add_argument('--num-txns', type=int, default=5, help='Number of transactions to test')
    parser.add_argument('--threshold', type=float, default=0.85, help='Similarity threshold')
    args = parser.parse_args()
    
    # Update threshold
    os.environ['SIMILARITY_THRESHOLD'] = str(args.threshold)
    
    print(f"\n📋 Configuration:")
    print(f"  Threshold: {args.threshold}")
    print(f"  S3 Bucket: {os.environ['SIMILARITY_S3_BUCKET']}")
    print(f"  S3 Key: {os.environ['SIMILARITY_S3_KEY']}")
    print(f"  Transactions to test: {args.num_txns}")
    
    # Load test transactions
    print(f"\n" + "=" * 100)
    print("LOADING TEST TRANSACTIONS")
    print("=" * 100)
    
    test_file = "data/transactions_test.csv"
    if not os.path.exists(test_file):
        print(f"\n❌ Error: {test_file} not found")
        sys.exit(1)
    
    df = pd.read_csv(test_file, nrows=args.num_txns)
    print(f"\n✓ Loaded {len(df)} transactions from {test_file}")
    
    # Process each transaction
    print(f"\n" + "=" * 100)
    print("PROCESSING TRANSACTIONS")
    print("=" * 100)
    
    results = []
    
    for idx, row in df.iterrows():
        txn_id = row.get('TransactionID', idx)
        amount = row.get('amount', 0)
        
        print(f"\n{'-' * 100}")
        print(f"Transaction #{idx + 1}: ID={txn_id}, Amount=${amount:.2f}")
        print(f"{'-' * 100}")
        
        # Create mock preprocessed features
        features = create_mock_features(row)
        
        # Validate features
        is_valid = validate_features_only(features)
        print(f"  Feature validation: {'✓ PASS' if is_valid else '✗ FAIL'}")
        
        if not is_valid:
            print("  ⚠️  Skipping - invalid feature schema")
            continue
        
        # Mock K-means results (in real endpoint, these come from clustering)
        mock_kmeans_score = 45  # Mock risk score from K-means
        mock_kmeans_decision = "Accept"  # Mock decision from K-means
        
        print(f"  K-means (mock):")
        print(f"    risk_score: {mock_kmeans_score}")
        print(f"    risk_decision: {mock_kmeans_decision}")
        
        # Call similarity matcher
        try:
            result = find_similar_transaction(
                query_result=features,
                threshold=args.threshold,
                top_k=3
            )
            
            matched = result.get("matched", False)
            sim_score = result.get("similarity_score", 0.0)
            status = result.get("status_warning", "NONE")
            top_matches = result.get("top_matches", [])
            
            print(f"\n  Similarity matching:")
            print(f"    matched: {matched}")
            print(f"    similarity_score: {sim_score:.4f}")
            print(f"    S3 status: {status}")
            
            if top_matches:
                print(f"    Top {len(top_matches)} matches:")
                for i, match in enumerate(top_matches, 1):
                    print(f"      {i}. TxnID: {match.get('TransactionID', 'N/A')}, "
                          f"Similarity: {match.get('similarity', 0):.4f}, "
                          f"Status: {match.get('statusWarning', 'N/A')}")
            
            # Apply decision logic
            if matched and sim_score >= args.threshold and status in ["SAFE", "RISKY"]:
                # Override with similarity-based decision
                final_score = 70
                final_decision = "Accept" if status == "SAFE" else "Reject"
                print(f"\n  ✓ SIMILARITY OVERRIDE:")
                print(f"    final_risk_score: {final_score} (overridden from {mock_kmeans_score})")
                print(f"    final_risk_decision: {final_decision} (overridden from {mock_kmeans_decision})")
                print(f"    reason: Similarity match with S3 status '{status}' (score: {sim_score:.4f})")
            else:
                # Keep K-means decision
                final_score = mock_kmeans_score
                final_decision = mock_kmeans_decision
                print(f"\n  → K-MEANS DECISION KEPT:")
                print(f"    final_risk_score: {final_score}")
                print(f"    final_risk_decision: {final_decision}")
                print(f"    reason: No similarity match above threshold ({sim_score:.4f} < {args.threshold})")
            
            results.append({
                'TransactionID': txn_id,
                'amount': amount,
                'kmeans_score': mock_kmeans_score,
                'kmeans_decision': mock_kmeans_decision,
                'similarity_matched': matched,
                'similarity_score': sim_score,
                'similarity_status': status,
                'final_score': final_score,
                'final_decision': final_decision
            })
            
        except Exception as e:
            print(f"\n  ❌ Error in similarity matching: {e}")
            import traceback
            traceback.print_exc()
    
    # Summary
    print(f"\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    
    if results:
        results_df = pd.DataFrame(results)
        print(f"\nProcessed {len(results)} transactions:")
        print(f"\nDecision distribution:")
        print(results_df['final_decision'].value_counts())
        
        overridden = results_df[results_df['similarity_matched'] == True]
        if len(overridden) > 0:
            print(f"\n✓ {len(overridden)} transactions overridden by similarity matching")
        
        print(f"\nDetailed results:")
        print(results_df.to_string(index=False))
    else:
        print("\n⚠️  No results to display")
    
    print(f"\n" + "=" * 100)


if __name__ == "__main__":
    main()
