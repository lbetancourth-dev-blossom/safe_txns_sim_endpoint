#!/usr/bin/env python3
"""
Extract and consolidate Safe transaction data from Silver layer (Parquet format).

This script:
1. Lists all .parquet files recursively from S3 bucket (silver layer)
2. Downloads and reads Parquet files
3. Combines all records and sorts by createdat
4. Saves to CSV file

Usage:
    python extract_safe_silver.py [--output FILE]
"""

import boto3
import pandas as pd
from pathlib import Path
import argparse
import sys
from io import BytesIO


# Configuration
AWS_PROFILE = "blossom-dev"
S3_BUCKET = "blossom-analytics-datalake-dev"
S3_PREFIX = "datalake/silver/SAFE/safetransactionresults/data/"
OUTPUT_FILE = "data/data_eng/SafeTxnResultsSilver.csv"


def list_s3_parquet_files(s3_client, bucket, prefix):
    """
    List all .parquet files in S3 bucket recursively.
    
    Args:
        s3_client: boto3 S3 client
        bucket: S3 bucket name
        prefix: S3 prefix path
    
    Returns:
        List of S3 keys (file paths)
    """
    print(f"[INFO] Listing files from s3://{bucket}/{prefix}")
    
    paginator = s3_client.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket, Prefix=prefix)
    
    parquet_files = []
    for page in pages:
        if 'Contents' not in page:
            continue
        
        for obj in page['Contents']:
            key = obj['Key']
            
            # Filter only .parquet files
            if key.endswith('.parquet'):
                parquet_files.append({
                    'key': key,
                    'size': obj['Size'],
                    'last_modified': obj['LastModified']
                })
    
    print(f"[INFO] Found {len(parquet_files)} .parquet files")
    
    # Show file details
    total_size = sum(f['size'] for f in parquet_files)
    print(f"[INFO] Total size: {total_size / 1024 / 1024:.2f} MB")
    
    return parquet_files


def download_and_read_parquet(s3_client, bucket, key):
    """
    Download .parquet file from S3 and read into DataFrame.
    
    Args:
        s3_client: boto3 S3 client
        bucket: S3 bucket name
        key: S3 object key
    
    Returns:
        pandas DataFrame
    """
    try:
        # Download file to memory
        obj = s3_client.get_object(Bucket=bucket, Key=key)
        parquet_data = obj['Body'].read()
        
        # Read Parquet
        df = pd.read_parquet(BytesIO(parquet_data))
        
        return df
    
    except Exception as e:
        print(f"[ERROR] Failed to process {key}: {e}")
        return pd.DataFrame()


def extract_all_data(s3_client, bucket, parquet_files):
    """
    Extract data from all Parquet files.
    
    Args:
        s3_client: boto3 S3 client
        bucket: S3 bucket name
        parquet_files: List of file info dicts
    
    Returns:
        pandas DataFrame with all records
    """
    all_dfs = []
    
    print(f"[INFO] Processing {len(parquet_files)} files...")
    
    for idx, file_info in enumerate(parquet_files, 1):
        key = file_info['key']
        size_mb = file_info['size'] / 1024 / 1024
        
        print(f"[PROGRESS] [{idx}/{len(parquet_files)}] Reading {Path(key).name} ({size_mb:.2f} MB)")
        
        df = download_and_read_parquet(s3_client, bucket, key)
        
        if not df.empty:
            all_dfs.append(df)
            print(f"           → {len(df)} records extracted")
    
    if not all_dfs:
        print("[WARN] No data extracted!")
        return pd.DataFrame()
    
    # Combine all DataFrames
    print(f"[INFO] Combining {len(all_dfs)} DataFrames...")
    combined_df = pd.concat(all_dfs, ignore_index=True)
    
    print(f"[INFO] Total records extracted: {len(combined_df)}")
    
    return combined_df


def process_and_save(df, output_file):
    """
    Process DataFrame, sort by createdat, and save to CSV.
    
    Args:
        df: pandas DataFrame
        output_file: Output CSV file path
    """
    if df.empty:
        print("[ERROR] No data to save!")
        return
    
    print(f"[INFO] Processing {len(df)} records...")
    
    # Normalize column names (Parquet might have lowercase)
    df.columns = df.columns.str.lower()
    
    # Expected columns (lowercase from Parquet)
    expected_columns = [
        "uuid",
        "transactionid",
        "idfi",
        "statuswarning",
        "metadata",
        "createdat",
        "updatedat"
    ]
    
    # Remove CDC metadata columns
    cdc_columns = ['_last_cdc_timestamp', '_hoodie_commit_time', '_hoodie_commit_seqno']
    for col in cdc_columns:
        if col in df.columns:
            df = df.drop(columns=[col])
            print(f"[INFO] Removed CDC column: {col}")
    
    # Check columns
    missing_cols = [col for col in expected_columns if col not in df.columns]
    if missing_cols:
        print(f"[WARN] Missing columns: {missing_cols}")
    
    # Reorder columns
    existing_cols = [col for col in expected_columns if col in df.columns]
    extra_cols = [col for col in df.columns if col not in expected_columns]
    final_columns = existing_cols + extra_cols
    
    df = df[final_columns]
    
    print(f"[INFO] Column order: {final_columns}")
    
    # Sort by createdat
    if 'createdat' in df.columns:
        print(f"[INFO] Sorting by createdat")
        
        try:
            df['createdat'] = pd.to_datetime(df['createdat'])
            df = df.sort_values(by='createdat')
            print(f"[INFO] Date range: {df['createdat'].min()} to {df['createdat'].max()}")
        except Exception as e:
            print(f"[WARN] Could not sort by createdat: {e}")
    
    # Convert column names to match expected format (camelCase for output)
    column_mapping = {
        'uuid': 'uuid',
        'transactionid': 'transactionId',
        'idfi': 'idFi',
        'statuswarning': 'statusWarning',
        'metadata': 'metadata',
        'createdat': 'createdAt',
        'updatedat': 'updatedAt'
    }
    
    df = df.rename(columns=column_mapping)
    
    # Save to CSV
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    df.to_csv(output_file, index=False)
    print(f"[SUCCESS] Data saved to: {output_file}")
    print(f"[INFO] Total rows: {len(df)}, Total columns: {len(df.columns)}")
    print(f"[INFO] File size: {output_path.stat().st_size / 1024 / 1024:.2f} MB")


def main():
    parser = argparse.ArgumentParser(
        description='Extract Safe transaction data from Silver layer (Parquet)'
    )
    parser.add_argument(
        '--profile',
        type=str,
        default=AWS_PROFILE,
        help=f'AWS profile name (default: {AWS_PROFILE})'
    )
    parser.add_argument(
        '--bucket',
        type=str,
        default=S3_BUCKET,
        help=f'S3 bucket name (default: {S3_BUCKET})'
    )
    parser.add_argument(
        '--prefix',
        type=str,
        default=S3_PREFIX,
        help=f'S3 prefix path (default: {S3_PREFIX})'
    )
    parser.add_argument(
        '--output',
        type=str,
        default=OUTPUT_FILE,
        help=f'Output CSV file path (default: {OUTPUT_FILE})'
    )
    
    args = parser.parse_args()
    
    # Initialize S3 client
    print(f"[INFO] Connecting to AWS with profile: {args.profile}")
    session = boto3.Session(profile_name=args.profile)
    s3_client = session.client('s3')
    
    # List Parquet files
    parquet_files = list_s3_parquet_files(s3_client, args.bucket, args.prefix)
    
    if not parquet_files:
        print("[ERROR] No Parquet files found!")
        sys.exit(1)
    
    # Extract data
    df = extract_all_data(s3_client, args.bucket, parquet_files)
    
    # Process and save
    process_and_save(df, args.output)


if __name__ == '__main__':
    main()
