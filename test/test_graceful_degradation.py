"""
Test graceful degradation when reference data is unavailable.

Tests that the endpoint continues processing without similarity matching
when S3 data is unavailable, empty, or contains only invalid records.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'endpoint'))

import boto3
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np
from similarity_matcher import (
    load_reference_data_from_s3,
    find_similar_transaction
)


def test_no_parquet_files_in_s3():
    """Test graceful handling when S3 directory has no .parquet files"""
    
    with patch('similarity_matcher.boto3.client') as mock_client:
        s3_mock = MagicMock()
        mock_client.return_value = s3_mock
        
        # Simulate empty directory (no .parquet files)
        s3_mock.list_objects_v2.return_value = {
            'Contents': []
        }
        
        # Should return None values instead of crashing
        result = load_reference_data_from_s3(
            bucket='test-bucket',
            key='test-prefix/',
            force_reload=True
        )
        
        assert result == (None, None, None, None), "Should return None tuple when no files found"


def test_all_records_pending():
    """Test graceful handling when all S3 records are PENDING (no SAFE/RISKY)"""
    
    # Create test data with only PENDING records
    test_df = pd.DataFrame({
        'metadata': [
            '{"decisionResult": {"num__amount": 100.0, "cat__type": 1.0}}',
            '{"decisionResult": {"num__amount": 200.0, "cat__type": 2.0}}'
        ],
        'statusWarning': ['PENDING', 'PENDING']
    })
    
    with patch('similarity_matcher.boto3.client') as mock_client, \
         patch('similarity_matcher._load_parquet_directory_from_s3') as mock_load:
        
        s3_mock = MagicMock()
        mock_client.return_value = s3_mock
        
        # Mock file count
        s3_mock.list_objects_v2.return_value = {
            'Contents': [{'Key': 'file.parquet'}]
        }
        
        # Return DataFrame with only PENDING records
        mock_load.return_value = test_df
        
        # Should return None values after filtering
        result = load_reference_data_from_s3(
            bucket='test-bucket',
            key='test-prefix/',
            force_reload=True
        )
        
        assert result == (None, None, None, None), "Should return None when no valid records after filtering"


def test_find_similar_with_no_reference_data():
    """Test that find_similar_transaction handles missing reference data gracefully"""
    
    with patch('similarity_matcher.load_reference_data_from_s3') as mock_load:
        # Simulate no reference data available
        mock_load.return_value = (None, None, None, None)
        
        query = {
            "num__amount": 100.0,
            "cat__type": 1.0
        }
        
        # Should return "not matched" result instead of crashing
        result = find_similar_transaction(
            query_result=query,
            threshold=0.90,
            s3_bucket='test-bucket',
            s3_key='test-prefix/',
            force_reload=True
        )
        
        assert result['matched'] == False
        assert result['similarity_score'] == 0.0
        assert result['status_warning'] == 'NONE'
        assert 'error' in result
        assert 'No reference data available' in result['error']


def test_s3_connection_error():
    """Test graceful handling of S3 connection errors"""
    
    with patch('similarity_matcher.boto3.client') as mock_client:
        s3_mock = MagicMock()
        mock_client.return_value = s3_mock
        
        # Simulate S3 connection error
        s3_mock.list_objects_v2.side_effect = Exception("Connection timeout")
        
        # Should return None values instead of crashing
        result = load_reference_data_from_s3(
            bucket='test-bucket',
            key='test-prefix/',
            force_reload=True
        )
        
        assert result == (None, None, None, None), "Should return None tuple on S3 error"


def test_corrupted_parquet_files():
    """Test graceful handling when parquet files are corrupted"""
    
    with patch('similarity_matcher.boto3.client') as mock_client, \
         patch('similarity_matcher._load_parquet_directory_from_s3') as mock_load:
        
        s3_mock = MagicMock()
        mock_client.return_value = s3_mock
        
        # Mock file count
        s3_mock.list_objects_v2.return_value = {
            'Contents': [{'Key': 'file.parquet'}]
        }
        
        # Simulate corrupted file error
        mock_load.side_effect = Exception("Parquet file corrupted")
        
        # Should return None values instead of crashing
        result = load_reference_data_from_s3(
            bucket='test-bucket',
            key='test-prefix/',
            force_reload=True
        )
        
        assert result == (None, None, None, None), "Should return None tuple when files are corrupted"


if __name__ == '__main__':
    print("Testing graceful degradation scenarios...")
    print("\n1. Testing no parquet files in S3...")
    test_no_parquet_files_in_s3()
    print("   PASSED\n")
    
    print("2. Testing all records PENDING...")
    test_all_records_pending()
    print("   PASSED\n")
    
    print("3. Testing find_similar with no reference data...")
    test_find_similar_with_no_reference_data()
    print("   PASSED\n")
    
    print("4. Testing S3 connection error...")
    test_s3_connection_error()
    print("   PASSED\n")
    
    print("5. Testing corrupted parquet files...")
    test_corrupted_parquet_files()
    print("   PASSED\n")
    
    print("All graceful degradation tests passed!")
