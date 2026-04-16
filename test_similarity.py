"""
Test Similarity Matcher with Sample Data
=========================================

This script tests the similarity matching workflow:
1. Uses transactions_test.csv as sample data
2. Creates mock processed data (simulating endpoint output)
3. Tests similarity matching against this reference data

Note: In production, step 1 would be done by the SageMaker endpoint
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path

# Create mock processed data (simulating what the endpoint would output)
def create_mock_reference_data(input_csv: str, output_csv: str, num_samples: int = 50):
    """
    Create mock reference data with the expected schema.
    This simulates what the endpoint would produce.
    """
    print(f"\n=== Creating Mock Reference Data ===")
    print(f"Reading from: {input_csv}")
    
    # Read raw data
    df = pd.read_csv(input_csv)
    print(f"Loaded {len(df)} raw transactions")
    
    # Take a sample
    df_sample = df.head(num_samples).copy()
    print(f"Using {len(df_sample)} samples for reference data")
    
    # Create mock processed fields (these would come from endpoint)
    reference_records = []
    
    for idx, row in df_sample.iterrows():
        # Helper function to safely get float value (handles NaN)
        def safe_float(value, default=0.0):
            if pd.isna(value) or value is None:
                return default
            try:
                return float(value)
            except (ValueError, TypeError):
                return default
        
        # Mock decision result (simulating endpoint output)
        decision_result = {
            # Post-processing fields (from clustering and rules)
            "Cluster": int(np.random.randint(0, 5)),
            "Distance_to_Centroid": float(np.random.uniform(10, 100)),
            "risk_score": int(np.random.randint(0, 100)),
            "risk_decision": str(np.random.choice(["Accept", "User Auth", "Admin Review", "Reject"])),
            "is_outlier": int(np.random.choice([0, 1])),
            
            # Numerical features (from preprocessing)
            "num__amount": safe_float(row.get("amount")),
            "num__is_night": safe_float(row.get("is_night")),
            "num__hour_sin": safe_float(row.get("hour_sin")),
            "num__hour_cos": safe_float(row.get("hour_cos")),
            "num__day_of_week_cos": safe_float(row.get("day_of_week_cos")),
            "num__count_all_txn_last_5m": safe_float(row.get("count_all_txn_last_5m")),
            "num__total_amount_all_txn_last_5m": safe_float(row.get("total_amount_all_txn_last_5m")),
            "num__count_txn_to_recipient_account_last_5m": safe_float(row.get("count_txn_to_recipient_account_last_5m")),
            "num__total_amount_txn_to_recipient_account_last_5m": safe_float(row.get("total_amount_txn_to_recipient_account_last_5m")),
            "num__count_txn_to_recipient_account_in_last_2_months": safe_float(row.get("count_txn_to_recipient_account_in_last_2_months")),
            "num__is_first_txn_from_this_olb_user_to_this_recipient_account_q_6h": safe_float(row.get("is_first_txn_from_this_olb_user_to_this_recipient_account_q_6h")),
            "num__amount_coef_var_lst6m": safe_float(row.get("amount_coef_var_lst6m")),
            "num__pct_txns_under_100_lst6m": safe_float(row.get("pct_txns_under_100_lst6m")),
            "num__pct_txns_over_1k_lst6m": safe_float(row.get("pct_txns_over_1k_lst6m")),
            "num__user_avg_amount_txn_per_active_day_last_6_months": safe_float(row.get("user_avg_amount_txn_per_active_day_last_6_months")),
            "num__count_user_all_txn_in_last_6_months": safe_float(row.get("count_user_all_txn_in_last_6_months")),
            "num__count_user_cancelled_txn_in_last_week": safe_float(row.get("count_user_cancelled_txn_in_last_week")),
            "num__count_user_cancelled_txn_in_last_month": safe_float(row.get("count_user_cancelled_txn_in_last_month")),
            "num__count_user_potential_fraud_txn_in_last_2_months": safe_float(row.get("count_user_potential_fraud_txn_in_last_2_months")),
            "num__recency_user_created_days": safe_float(row.get("recency_user_created_days")),
            "num__count_suspected_actions_in_current_session": safe_float(row.get("count_suspected_actions_in_current_session")),
            "num__total_actions_session": safe_float(row.get("total_actions_session")),
            "num__is_auth_email_session": safe_float(row.get("is_auth_email_session")),
            "num__is_auth_phone_session": safe_float(row.get("is_auth_phone_session")),
            "num__total_accounts": safe_float(row.get("total_accounts")),
            "num__user_age": safe_float(row.get("user_age")),
            "num__is_amount_greater_than_cu_p95_amount_ach_txn_in_last_6_months": safe_float(row.get("is_amount_greater_than_cu_p95_amount_ach_txn_in_last_6_months")),
            "num__txn_amount_vs_cu_avg_amount_ach_txn_in_last_6_months": safe_float(row.get("txn_amount_vs_cu_avg_amount_ach_txn_in_last_6_months")),
            "num__is_batch": safe_float(row.get("is_batch")),
            "num__amt_vs_user_ach_avg_day": safe_float(row.get("amt_vs_user_ach_avg_day")),
            "num__ach_count_share_6m": safe_float(row.get("ach_count_share_6m")),
            
            # Categorical features (mock one-hot encoding)
            "cat__TransactionProcessingType_Intime": 1.0 if row.get("TransactionProcessingType") == "Intime" else 0.0,
            "cat__TransactionProcessingType_Intime_From_Recurrent": 0.0,
            "cat__TransactionProcessingType_Recurrent": 0.0,
            "cat__TransactionProcessingType_Schedule": 0.0,
            "cat__TransactionOrigin_External Internal": 0.0,
            "cat__TransactionOrigin_Internal External": 1.0 if row.get("TransactionOrigin") == "Internal External" else 0.0,
            "cat__TransactionOrigin_M2m External": 1.0 if row.get("TransactionOrigin") == "M2m External" else 0.0,
            "cat__TransactionCategory_SEND_MONEY_ACH": 1.0 if row.get("TransactionCategory") == "SEND_MONEY_ACH" else 0.0,
            "cat__TransactionCategory_SEND_MONEY_BATCH_PAYMENT_ACH": 0.0,
            "cat__TransactionCategory_SEND_MONEY_PAYROLL_ACH": 0.0,
            "cat__TransactionCategory_SINGLE_COLLECTION_ACH": 0.0,
            "cat__TransactionCategory_TRANSFER_EXTERNAL_TO_LOAN_ACH": 0.0,
            "cat__TransactionCategory_TRANSFER_INTERNAL_EXTERNAL_ACH": 1.0 if row.get("TransactionCategory") == "TRANSFER_INTERNAL_EXTERNAL_ACH" else 0.0,
            "cat__user_type_mixed": 0.0,
            "cat__user_type_personal": 1.0 if row.get("user_type") == "personal" else 0.0,
            "cat__access_DESKTOP": 0.0,
            "cat__access_MOBILE": 1.0 if row.get("access") == "MOBILE" else 0.0,
            "cat__access_missing": 0.0,
        }
        
        # Assign mock statusWarning based on risk_score
        risk_score = decision_result["risk_score"]
        if risk_score >= 80:
            status_warning = "HIGH_RISK"
        elif risk_score >= 60:
            status_warning = "MEDIUM_RISK"
        elif risk_score >= 40:
            status_warning = "LOW_RISK"
        else:
            status_warning = "NORMAL"
        
        # Create record
        record = {
            "TransactionID": str(row.get("TransactionID", idx)),
            "metadata": json.dumps({"decisionResult": decision_result}),
            "statusWarning": status_warning
        }
        
        reference_records.append(record)
    
    # Create DataFrame and save
    df_reference = pd.DataFrame(reference_records)
    df_reference.to_csv(output_csv, index=False)
    
    print(f"✓ Created reference data: {output_csv}")
    print(f"  Records: {len(df_reference)}")
    print(f"  Status distribution:")
    print(df_reference['statusWarning'].value_counts().to_dict())
    
    return df_reference


def test_similarity_matcher(reference_csv: str):
    """Test the similarity matcher with the reference data."""
    print(f"\n=== Testing Similarity Matcher ===")
    
    # Import similarity matcher
    import sys
    sys.path.insert(0, 'endpoint')
    
    try:
        from similarity_matcher import load_reference_data_from_s3, find_similar_transaction
    except ImportError as e:
        print(f"✗ Error importing similarity_matcher: {e}")
        print("Make sure you're running from the project root directory")
        return
    
    # Test 1: Load reference data from local file (simulating S3)
    print(f"\n--- Test 1: Load Reference Data ---")
    try:
        # Read the CSV directly to simulate S3 load
        import boto3
        from io import StringIO
        
        # Mock S3 load by reading local file
        df_ref = pd.read_csv(reference_csv)
        print(f"✓ Loaded {len(df_ref)} records from {reference_csv}")
        
        # Validate first record
        first_record = df_ref.iloc[0]
        print(f"\n  Sample record:")
        print(f"    TransactionID: {first_record['TransactionID']}")
        print(f"    statusWarning: {first_record['statusWarning']}")
        
        metadata = json.loads(first_record['metadata'])
        decision_result = metadata['decisionResult']
        print(f"    Fields in decisionResult: {len(decision_result)}")
        print(f"    Cluster: {decision_result.get('Cluster')}")
        print(f"    risk_score: {decision_result.get('risk_score')}")
        
    except Exception as e:
        print(f"✗ Error loading reference data: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Test 2: Create a query transaction and find similar
    print(f"\n--- Test 2: Find Similar Transaction ---")
    try:
        # Use the first record as a query (should match itself)
        query_metadata = json.loads(df_ref.iloc[0]['metadata'])
        query_result = query_metadata['decisionResult']
        
        print(f"  Query transaction:")
        print(f"    Cluster: {query_result.get('Cluster')}")
        print(f"    risk_score: {query_result.get('risk_score')}")
        print(f"    amount: {query_result.get('num__amount')}")
        
        # Since we can't actually call S3, we'll test the feature extraction
        from similarity_matcher import _extract_feature_vector
        
        query_vector = _extract_feature_vector(query_result, validate_schema=True)
        print(f"\n  ✓ Feature extraction successful")
        print(f"    Vector dimensions: {len(query_vector)}")
        print(f"    First 5 values: {query_vector[:5]}")
        
        print(f"\n  Note: Full S3 integration test requires uploading to S3")
        print(f"        and setting up AWS credentials")
        
    except Exception as e:
        print(f"✗ Error testing similarity: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print(f"\n✓ Tests completed successfully")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Test similarity matcher with sample data")
    parser.add_argument(
        "--input",
        default="data/transactions_test.csv",
        help="Input CSV file (raw transactions)"
    )
    parser.add_argument(
        "--output",
        default="data/reference_test.csv",
        help="Output CSV file (mock reference data)"
    )
    parser.add_argument(
        "--num-samples",
        type=int,
        default=50,
        help="Number of samples to use for reference data"
    )
    parser.add_argument(
        "--skip-create",
        action="store_true",
        help="Skip creating reference data (use existing file)"
    )
    
    args = parser.parse_args()
    
    # Create reference data
    if not args.skip_create:
        df_ref = create_mock_reference_data(
            args.input,
            args.output,
            num_samples=args.num_samples
        )
    else:
        print(f"Using existing reference file: {args.output}")
    
    # Test similarity matcher
    test_similarity_matcher(args.output)
    
    print(f"\n{'='*60}")
    print(f"Next Steps:")
    print(f"  1. Upload {args.output} to S3:")
    print(f"     aws s3 cp {args.output} s3://bucket/path/reference.csv")
    print(f"")
    print(f"  2. Test with actual S3 data:")
    print(f"     python endpoint/similarity_matcher.py \\")
    print(f"       --s3-uri s3://bucket/path/reference.csv \\")
    print(f"       --threshold 0.90")
    print(f"")
    print(f"  3. Validate reference data:")
    print(f"     python endpoint/validate_s3_data.py \\")
    print(f"       --local-csv {args.output} \\")
    print(f"       --output validation_report.json")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
