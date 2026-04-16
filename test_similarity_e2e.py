"""
End-to-End Similarity Matcher Test
===================================

This script performs a complete test of the similarity matching system:
1. Loads mock reference data (simulating S3)
2. Creates query transactions
3. Finds similar matches
4. Displays detailed results
"""

import sys
import json
sys.path.insert(0, 'endpoint')

from similarity_matcher import (
    _extract_feature_vector,
    calculate_similarity,
    CORE_FIELDS_FOR_SIMILARITY
)
import pandas as pd
import numpy as np


def load_mock_reference_data(csv_path: str):
    """Load and parse reference data from CSV."""
    print(f"\n=== Loading Reference Data ===")
    print(f"Source: {csv_path}")
    
    df = pd.read_csv(csv_path)
    print(f"Total records: {len(df)}")
    
    # Parse and extract features
    vectors = []
    labels = []
    transaction_ids = []
    
    for idx, row in df.iterrows():
        metadata = json.loads(row['metadata'])
        decision_result = metadata['decisionResult']
        
        vector = _extract_feature_vector(decision_result, validate_schema=True)
        if vector is not None:
            vectors.append(vector)
            labels.append(row['statusWarning'])
            transaction_ids.append(str(row['TransactionID']))
    
    vectors_array = np.array(vectors)
    print(f"Valid vectors: {len(vectors)}")
    print(f"Vector shape: {vectors_array.shape}")
    print(f"Status distribution: {pd.Series(labels).value_counts().to_dict()}")
    
    return vectors_array, labels, transaction_ids, df


def test_similarity_with_query(
    query_idx: int,
    ref_vectors: np.ndarray,
    ref_labels: list,
    ref_ids: list,
    df_reference: pd.DataFrame,
    threshold: float = 0.90
):
    """Test similarity matching with a specific query."""
    print(f"\n{'='*70}")
    print(f"Test #{query_idx + 1}: Query Transaction")
    print(f"{'='*70}")
    
    # Get query data
    query_row = df_reference.iloc[query_idx]
    query_metadata = json.loads(query_row['metadata'])
    query_result = query_metadata['decisionResult']
    query_vector = _extract_feature_vector(query_result, validate_schema=True)
    
    # Display query info
    print(f"\nQuery Transaction Details:")
    print(f"  TransactionID: {query_row['TransactionID']}")
    print(f"  Actual Label: {query_row['statusWarning']}")
    print(f"  Amount: ${query_result.get('num__amount', 0):,.2f}")
    print(f"  Cluster: {query_result.get('Cluster')}")
    print(f"  Risk Score: {query_result.get('risk_score')}")
    print(f"  Risk Decision: {query_result.get('risk_decision')}")
    
    # Calculate similarities
    similarities = calculate_similarity(query_vector, ref_vectors, metric="cosine")
    
    # Get top 5 matches
    top_indices = np.argsort(similarities)[::-1][:5]
    top_scores = similarities[top_indices]
    
    print(f"\n{'─'*70}")
    print(f"Top 5 Similar Transactions:")
    print(f"{'─'*70}")
    
    for rank, (idx, score) in enumerate(zip(top_indices, top_scores), 1):
        matched_id = ref_ids[idx]
        matched_label = ref_labels[idx]
        is_match = score >= threshold
        match_symbol = "✓" if is_match else "✗"
        
        # Get details of matched transaction
        matched_row = df_reference[df_reference['TransactionID'].astype(str) == matched_id].iloc[0]
        matched_metadata = json.loads(matched_row['metadata'])
        matched_result = matched_metadata['decisionResult']
        
        print(f"\n  {rank}. {match_symbol} TxnID: {matched_id}")
        print(f"     Similarity: {score:.4f} ({'MATCH' if is_match else 'no match'})")
        print(f"     Label: {matched_label}")
        print(f"     Amount: ${matched_result.get('num__amount', 0):,.2f}")
        print(f"     Cluster: {matched_result.get('Cluster')}, "
              f"Risk Score: {matched_result.get('risk_score')}")
        
        # Show feature differences for top match
        if rank == 1 and idx != query_idx:
            print(f"\n     Key Differences from Query:")
            diffs = []
            
            # Check key fields
            for field in ['num__amount', 'Cluster', 'risk_score']:
                query_val = query_result.get(field, 0)
                match_val = matched_result.get(field, 0)
                if query_val != match_val:
                    diffs.append(f"{field}: {query_val} → {match_val}")
            
            if diffs:
                for diff in diffs[:3]:  # Show top 3 differences
                    print(f"       - {diff}")
            else:
                print(f"       - Almost identical!")
    
    # Decision
    best_score = top_scores[0]
    best_label = ref_labels[top_indices[0]]
    
    print(f"\n{'─'*70}")
    print(f"Similarity Matching Result:")
    print(f"{'─'*70}")
    
    if best_score >= threshold:
        print(f"  ✓ MATCH FOUND")
        print(f"  Similarity Score: {best_score:.4f}")
        print(f"  Matched Label: {best_label}")
        print(f"  Threshold: {threshold}")
    else:
        print(f"  ✗ NO MATCH")
        print(f"  Best Similarity: {best_score:.4f}")
        print(f"  Threshold: {threshold}")
        print(f"  Would return: NONE")


def run_comprehensive_test(csv_path: str, num_tests: int = 5, threshold: float = 0.90):
    """Run comprehensive tests with multiple queries."""
    print(f"\n{'#'*70}")
    print(f"# COMPREHENSIVE SIMILARITY MATCHER TEST")
    print(f"{'#'*70}")
    print(f"\nConfiguration:")
    print(f"  Reference Data: {csv_path}")
    print(f"  Similarity Threshold: {threshold}")
    print(f"  Number of Test Cases: {num_tests}")
    
    # Load reference data
    ref_vectors, ref_labels, ref_ids, df_ref = load_mock_reference_data(csv_path)
    
    # Run tests with random samples
    print(f"\n{'#'*70}")
    print(f"# RUNNING TEST CASES")
    print(f"{'#'*70}")
    
    test_indices = np.random.choice(len(df_ref), size=min(num_tests, len(df_ref)), replace=False)
    
    for test_num, query_idx in enumerate(test_indices):
        test_similarity_with_query(
            query_idx=int(query_idx),
            ref_vectors=ref_vectors,
            ref_labels=ref_labels,
            ref_ids=ref_ids,
            df_reference=df_ref,
            threshold=threshold
        )
    
    # Summary
    print(f"\n{'#'*70}")
    print(f"# TEST SUMMARY")
    print(f"{'#'*70}")
    print(f"\n✓ All {num_tests} test cases completed successfully")
    print(f"\nReference Data Quality:")
    print(f"  Total records: {len(df_ref)}")
    print(f"  Valid vectors: {len(ref_vectors)}")
    print(f"  Vector dimensions: {ref_vectors.shape[1]}")
    print(f"\nLabel Distribution:")
    for label, count in pd.Series(ref_labels).value_counts().items():
        print(f"  {label}: {count} ({count/len(ref_labels)*100:.1f}%)")
    
    print(f"\n{'#'*70}")
    print(f"# NEXT STEPS")
    print(f"{'#'*70}")
    print(f"\n1. Upload to S3:")
    print(f"   aws s3 cp {csv_path} \\")
    print(f"     s3://blossom-analytics-safe-dev-nv/safe_txns/data/similarity/SafeTransactionResults.csv")
    print(f"\n2. Test with S3:")
    print(f"   python endpoint/similarity_matcher.py \\")
    print(f"     --s3-uri s3://blossom-analytics-safe-dev-nv/safe_txns/data/similarity/SafeTransactionResults.csv \\")
    print(f"     --threshold {threshold}")
    print(f"\n3. Integrate with endpoint:")
    print(f"   - Add similarity matching to inference_rules.py")
    print(f"   - Return similarity results in endpoint response")
    print(f"\n{'#'*70}\n")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test similarity matcher end-to-end")
    parser.add_argument(
        "--reference",
        default="data/reference_test.csv",
        help="Reference data CSV file"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.90,
        help="Similarity threshold (0.0-1.0)"
    )
    parser.add_argument(
        "--num-tests",
        type=int,
        default=5,
        help="Number of test queries to run"
    )
    
    args = parser.parse_args()
    
    run_comprehensive_test(
        csv_path=args.reference,
        num_tests=args.num_tests,
        threshold=args.threshold
    )
