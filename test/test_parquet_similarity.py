#!/usr/bin/env python3
"""
Test parquet-based similarity matching
"""

import sys
import os
sys.path.insert(0, 'endpoint')

# Set AWS profile for testing
os.environ['AWS_PROFILE'] = 'blossom-dev'
os.environ['SIMILARITY_S3_BUCKET'] = 'blossom-analytics-safe-dev-nv'
os.environ['SIMILARITY_S3_KEY'] = 'safe_txns/similarity/data/SafeTransactionResults/'

from similarity_matcher import load_reference_data_from_s3, find_similar_transaction

def test_parquet_loading():
    """Test loading parquet files from S3"""
    print("=" * 70)
    print("TEST 1: Parquet Directory Loading")
    print("=" * 70)
    
    try:
        df, vectors, labels, ids = load_reference_data_from_s3(force_reload=True)
        
        print(f"\n✅ Successfully loaded parquet data")
        print(f"📊 Total records: {len(df)}")
        print(f"📊 Feature vectors shape: {vectors.shape}")
        print(f"📊 Unique labels: {set(labels)}")
        
        if len(labels) == 0:
            print("\n⚠️  WARNING: No SAFE/RISKY records found!")
            print("   All records were filtered out (likely all PENDING)")
            return False
        
        import pandas as pd
        label_counts = pd.Series(labels).value_counts()
        print(f"\n📊 Label distribution:")
        for label, count in label_counts.items():
            print(f"   {label}: {count}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_similarity_matching():
    """Test similarity matching with parquet data"""
    print("\n" + "=" * 70)
    print("TEST 2: Similarity Matching")
    print("=" * 70)
    
    # Create a test query
    query_features = {
        "num__amount": 0.5,
        "num__is_night": 0.0,
        "num__hour_sin": 0.1,
        "num__hour_cos": 0.9,
        "num__day_of_week_cos": 0.5,
        # Add more features as needed...
    }
    
    try:
        result = find_similar_transaction(
            query_result=query_features,
            threshold=0.90,
            top_k=3
        )
        
        print(f"\n✅ Similarity search completed")
        print(f"📊 Matched: {result.get('matched', False)}")
        print(f"📊 Similarity score: {result.get('similarity_score', 0):.4f}")
        print(f"📊 Status warning: {result.get('status_warning', 'NONE')}")
        print(f"📊 Top matches: {len(result.get('top_matches', []))}")
        
        if result.get('top_matches'):
            print(f"\n🔍 Top matches:")
            for i, match in enumerate(result['top_matches'][:3], 1):
                print(f"   {i}. Score: {match['similarity_score']:.4f}, Status: {match['status_warning']}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("\n🚀 PARQUET-BASED SIMILARITY TESTING")
    print("=" * 70)
    print(f"S3 Bucket: {os.getenv('SIMILARITY_S3_BUCKET')}")
    print(f"S3 Key: {os.getenv('SIMILARITY_S3_KEY')}")
    print("=" * 70)
    
    results = []
    
    # Test 1: Loading
    results.append(test_parquet_loading())
    
    # Test 2: Similarity matching
    if results[0]:  # Only if loading succeeded
        results.append(test_similarity_matching())
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 TEST SUMMARY")
    print("=" * 70)
    
    if all(results):
        print("✅ ALL TESTS PASSED")
        print("\n✅ Parquet-based similarity matching is working!")
    else:
        print("❌ SOME TESTS FAILED")
        print(f"   Passed: {sum(results)}/{len(results)}")
    
    print("=" * 70)


if __name__ == "__main__":
    main()
