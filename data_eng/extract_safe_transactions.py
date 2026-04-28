#!/usr/bin/env python3
"""
Extract and consolidate Safe transaction data from S3 datalake.

This script:
1. Lists all .gz files recursively from S3 bucket (year/month/day structure)
2. Downloads and decompresses each file
3. Parses JSON data and extracts transaction records
4. Combines all records and sorts by createdAt
5. Saves to CSV file

Usage:
    python extract_safe_transactions.py [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]
"""

import boto3
import gzip
import json
import pandas as pd
from datetime import datetime
from pathlib import Path
import argparse
import sys
from io import BytesIO


# Configuration
AWS_PROFILE = "blossom-dev"
S3_BUCKET = "blossom-analytics-datalake-dev"
S3_PREFIX = "processed/source/dms/cdc/safe/"
OUTPUT_FILE = "data/data_eng/SafeTransactionResults.csv"


def list_s3_files(s3_client, bucket, prefix, start_date=None, end_date=None):
    """
    List all .gz files in S3 bucket recursively.
    
    Args:
        s3_client: boto3 S3 client
        bucket: S3 bucket name
        prefix: S3 prefix path
        start_date: Optional start date filter (datetime)
        end_date: Optional end date filter (datetime)
    
    Returns:
        List of S3 keys (file paths)
    """
    print(f"[INFO] Listing files from s3://{bucket}/{prefix}")
    
    paginator = s3_client.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket, Prefix=prefix)
    
    gz_files = []
    for page in pages:
        if 'Contents' not in page:
            continue
        
        for obj in page['Contents']:
            key = obj['Key']
            
            # Filter only .gz files
            if not key.endswith('.gz'):
                continue
            
            # Optional date filtering based on file path (year=X/month=Y/day=Z)
            if start_date or end_date:
                try:
                    # Extract date from path: year=2026/month=04/day=28
                    parts = key.split('/')
                    year_part = [p for p in parts if p.startswith('year=')]
                    month_part = [p for p in parts if p.startswith('month=')]
                    day_part = [p for p in parts if p.startswith('day=')]
                    
                    if year_part and month_part and day_part:
                        year = int(year_part[0].split('=')[1])
                        month = int(month_part[0].split('=')[1])
                        day = int(day_part[0].split('=')[1])
                        file_date = datetime(year, month, day)
                        
                        if start_date and file_date < start_date:
                            continue
                        if end_date and file_date > end_date:
                            continue
                except Exception as e:
                    print(f"[WARN] Could not parse date from path: {key}")
            
            gz_files.append(key)
    
    print(f"[INFO] Found {len(gz_files)} .gz files")
    return gz_files


def download_and_parse_gz(s3_client, bucket, key):
    """
    Download .gz file from S3, decompress, and parse JSON data.
    
    Args:
        s3_client: boto3 S3 client
        bucket: S3 bucket name
        key: S3 object key
    
    Returns:
        List of records (dicts)
    """
    records = []
    
    try:
        # Download file to memory
        obj = s3_client.get_object(Bucket=bucket, Key=key)
        compressed_data = obj['Body'].read()
        
        # Decompress
        with gzip.GzipFile(fileobj=BytesIO(compressed_data)) as gz:
            data = gz.read().decode('utf-8')
        
        # Parse JSON objects (may be concatenated without proper line breaks)
        # Use JSON decoder to handle multiple objects
        decoder = json.JSONDecoder()
        idx = 0
        data = data.strip()
        
        while idx < len(data):
            # Skip whitespace
            while idx < len(data) and data[idx].isspace():
                idx += 1
            
            if idx >= len(data):
                break
            
            try:
                # Decode next JSON object
                obj, end_idx = decoder.raw_decode(data, idx)
                idx += end_idx
                
                # Extract data from nested structure
                if 'data' in obj:
                    records.append(obj['data'])
                else:
                    records.append(obj)
            
            except json.JSONDecodeError as e:
                # Try to find next '{' to recover
                next_brace = data.find('{', idx + 1)
                if next_brace == -1:
                    break
                idx = next_brace
    
    except Exception as e:
        print(f"[ERROR] Failed to process {key}: {e}")
    
    return records


def extract_all_data(s3_client, bucket, file_keys, batch_size=100):
    """
    Extract data from all S3 files.
    
    Args:
        s3_client: boto3 S3 client
        bucket: S3 bucket name
        file_keys: List of S3 keys to process
        batch_size: Number of files to report progress
    
    Returns:
        pandas DataFrame with all records
    """
    all_records = []
    
    print(f"[INFO] Processing {len(file_keys)} files...")
    
    for idx, key in enumerate(file_keys, 1):
        if idx % batch_size == 0 or idx == len(file_keys):
            print(f"[PROGRESS] Processed {idx}/{len(file_keys)} files ({len(all_records)} records so far)")
        
        records = download_and_parse_gz(s3_client, bucket, key)
        all_records.extend(records)
    
    print(f"[INFO] Total records extracted: {len(all_records)}")
    
    # Convert to DataFrame
    if not all_records:
        print("[WARN] No records found!")
        return pd.DataFrame()
    
    df = pd.DataFrame(all_records)
    return df


def process_and_save(df, output_file):
    """
    Process DataFrame, sort by createdAt, and save to CSV.
    
    Args:
        df: pandas DataFrame
        output_file: Output CSV file path
    """
    if df.empty:
        print("[ERROR] No data to save!")
        return
    
    print(f"[INFO] Processing {len(df)} records...")
    
    # Define expected column order
    expected_columns = [
        "uuid",
        "transactionId", 
        "idFi",
        "statusWarning",
        "metadata",
        "createdAt",
        "updatedAt"
    ]
    
    # Validate required columns exist
    missing_cols = [col for col in expected_columns if col not in df.columns]
    if missing_cols:
        print(f"[WARN] Missing expected columns: {missing_cols}")
        print(f"[INFO] Available columns: {df.columns.tolist()}")
    
    # Reorder columns to match expected structure
    existing_expected = [col for col in expected_columns if col in df.columns]
    extra_cols = [col for col in df.columns if col not in expected_columns]
    
    # Final column order: expected columns first, then any extra
    final_columns = existing_expected + extra_cols
    df = df[final_columns]
    
    print(f"[INFO] Column order: {final_columns}")
    
    # Sort by createdAt if exists
    if 'createdAt' in df.columns:
        print(f"[INFO] Sorting by createdAt")
        
        try:
            df['createdAt'] = pd.to_datetime(df['createdAt'])
            df = df.sort_values(by='createdAt')
            print(f"[INFO] Date range: {df['createdAt'].min()} to {df['createdAt'].max()}")
        except Exception as e:
            print(f"[WARN] Could not sort by createdAt: {e}")
    
    # Save to CSV
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    df.to_csv(output_file, index=False)
    print(f"[SUCCESS] Data saved to: {output_file}")
    print(f"[INFO] Total rows: {len(df)}, Total columns: {len(df.columns)}")
    print(f"[INFO] File size: {output_path.stat().st_size / 1024 / 1024:.2f} MB")


def main():
    parser = argparse.ArgumentParser(
        description='Extract Safe transaction data from S3 datalake'
    )
    parser.add_argument(
        '--start-date',
        type=str,
        help='Start date filter (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--end-date',
        type=str,
        help='End date filter (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--profile',
        type=str,
        default=AWS_PROFILE,
        help=f'AWS profile name (default: {AWS_PROFILE})'
    )
    parser.add_argument(
        '--output',
        type=str,
        default=OUTPUT_FILE,
        help=f'Output CSV file path (default: {OUTPUT_FILE})'
    )
    
    args = parser.parse_args()
    
    # Parse date filters
    start_date = None
    end_date = None
    
    if args.start_date:
        try:
            start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
            print(f"[INFO] Start date filter: {start_date.date()}")
        except ValueError:
            print("[ERROR] Invalid start date format. Use YYYY-MM-DD")
            sys.exit(1)
    
    if args.end_date:
        try:
            end_date = datetime.strptime(args.end_date, '%Y-%m-%d')
            print(f"[INFO] End date filter: {end_date.date()}")
        except ValueError:
            print("[ERROR] Invalid end date format. Use YYYY-MM-DD")
            sys.exit(1)
    
    # Initialize S3 client
    print(f"[INFO] Connecting to AWS with profile: {args.profile}")
    session = boto3.Session(profile_name=args.profile)
    s3_client = session.client('s3')
    
    # List files
    file_keys = list_s3_files(
        s3_client,
        S3_BUCKET,
        S3_PREFIX,
        start_date=start_date,
        end_date=end_date
    )
    
    if not file_keys:
        print("[ERROR] No files found!")
        sys.exit(1)
    
    # Extract data
    df = extract_all_data(s3_client, S3_BUCKET, file_keys)
    
    # Process and save
    process_and_save(df, args.output)


if __name__ == '__main__':
    main()
