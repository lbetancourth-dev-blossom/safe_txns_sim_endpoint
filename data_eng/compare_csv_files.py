#!/usr/bin/env python3
"""
Compare two SafeTransactionResults CSV files and show differences.

Usage:
    python compare_csv_files.py file1.csv file2.csv
"""

import pandas as pd
import sys
from pathlib import Path


def compare_csv_files(file1, file2):
    """
    Compare two CSV files and show differences.
    
    Args:
        file1: Path to first CSV file
        file2: Path to second CSV file
    """
    print(f"[INFO] Comparing CSV files:")
    print(f"  File 1: {file1}")
    print(f"  File 2: {file2}")
    print()
    
    # Check files exist
    if not Path(file1).exists():
        print(f"[ERROR] File not found: {file1}")
        return
    
    if not Path(file2).exists():
        print(f"[ERROR] File not found: {file2}")
        return
    
    # Read files
    print("[INFO] Reading files...")
    try:
        df1 = pd.read_csv(file1)
        df2 = pd.read_csv(file2)
    except Exception as e:
        print(f"[ERROR] Failed to read CSV: {e}")
        return
    
    print(f"  ✅ File 1 loaded: {len(df1)} rows, {len(df1.columns)} columns")
    print(f"  ✅ File 2 loaded: {len(df2)} rows, {len(df2.columns)} columns")
    print()
    
    # Compare basic stats
    print("=" * 80)
    print("1. BASIC STATISTICS")
    print("=" * 80)
    
    print(f"\n{'Metric':<40} {'File 1':<20} {'File 2':<20}")
    print("-" * 80)
    print(f"{'Total rows':<40} {len(df1):<20} {len(df2):<20}")
    print(f"{'Total columns':<40} {len(df1.columns):<20} {len(df2.columns):<20}")
    print(f"{'File size':<40} {Path(file1).stat().st_size / 1024:.2f} KB {Path(file2).stat().st_size / 1024:.2f} KB")
    print()
    
    # Compare columns
    print("=" * 80)
    print("2. COLUMN COMPARISON")
    print("=" * 80)
    
    cols1 = set(df1.columns)
    cols2 = set(df2.columns)
    
    common_cols = cols1 & cols2
    only_in_1 = cols1 - cols2
    only_in_2 = cols2 - cols1
    
    print(f"\n✅ Common columns: {len(common_cols)}")
    if common_cols:
        print(f"   {sorted(common_cols)}")
    
    if only_in_1:
        print(f"\n⚠️  Only in File 1: {len(only_in_1)}")
        print(f"   {sorted(only_in_1)}")
    
    if only_in_2:
        print(f"\n⚠️  Only in File 2: {len(only_in_2)}")
        print(f"   {sorted(only_in_2)}")
    print()
    
    # If no common columns, stop here
    if not common_cols:
        print("[ERROR] No common columns to compare!")
        return
    
    # Compare data using common columns
    print("=" * 80)
    print("3. DATA COMPARISON (using common columns)")
    print("=" * 80)
    
    # Use only common columns for comparison
    df1_common = df1[sorted(common_cols)]
    df2_common = df2[sorted(common_cols)]
    
    # Check for duplicates
    df1_dupes = df1_common.duplicated().sum()
    df2_dupes = df2_common.duplicated().sum()
    
    print(f"\nDuplicate rows:")
    print(f"  File 1: {df1_dupes}")
    print(f"  File 2: {df2_dupes}")
    
    # Find unique identifiers
    if 'uuid' in common_cols:
        id_col = 'uuid'
    elif 'transactionId' in common_cols:
        id_col = 'transactionId'
    else:
        id_col = None
    
    if id_col:
        print(f"\n[INFO] Using '{id_col}' as identifier column")
        
        ids1 = set(df1[id_col].dropna())
        ids2 = set(df2[id_col].dropna())
        
        common_ids = ids1 & ids2
        only_in_1_ids = ids1 - ids2
        only_in_2_ids = ids2 - ids1
        
        print(f"\n{id_col} comparison:")
        print(f"  ✅ Common {id_col}s: {len(common_ids)}")
        print(f"  📊 Only in File 1: {len(only_in_1_ids)}")
        print(f"  📊 Only in File 2: {len(only_in_2_ids)}")
        
        if only_in_1_ids and len(only_in_1_ids) <= 10:
            print(f"\n  Sample IDs only in File 1:")
            for id_val in list(only_in_1_ids)[:10]:
                print(f"    - {id_val}")
        
        if only_in_2_ids and len(only_in_2_ids) <= 10:
            print(f"\n  Sample IDs only in File 2:")
            for id_val in list(only_in_2_ids)[:10]:
                print(f"    - {id_val}")
    
    # Date range comparison
    if 'createdAt' in common_cols:
        print(f"\ncreatedAt date range:")
        try:
            df1['createdAt_dt'] = pd.to_datetime(df1['createdAt'])
            df2['createdAt_dt'] = pd.to_datetime(df2['createdAt'])
            
            print(f"  File 1: {df1['createdAt_dt'].min()} to {df1['createdAt_dt'].max()}")
            print(f"  File 2: {df2['createdAt_dt'].min()} to {df2['createdAt_dt'].max()}")
        except Exception as e:
            print(f"  [WARN] Could not parse dates: {e}")
    
    # Check if files are identical
    print()
    print("=" * 80)
    print("4. IDENTITY CHECK")
    print("=" * 80)
    
    # Sort both dataframes by common columns for comparison
    try:
        df1_sorted = df1_common.sort_values(by=list(common_cols)).reset_index(drop=True)
        df2_sorted = df2_common.sort_values(by=list(common_cols)).reset_index(drop=True)
        
        if df1_sorted.equals(df2_sorted):
            print("\n✅ FILES ARE IDENTICAL (using common columns)")
            print("   The data in both files is exactly the same!")
        else:
            print("\n❌ FILES ARE DIFFERENT")
            
            # Try to find first difference
            if len(df1_sorted) == len(df2_sorted):
                for i, (row1, row2) in enumerate(zip(df1_sorted.iterrows(), df2_sorted.iterrows())):
                    if not row1[1].equals(row2[1]):
                        print(f"\n   First difference found at row {i}:")
                        print(f"   File 1: {row1[1].to_dict()}")
                        print(f"   File 2: {row2[1].to_dict()}")
                        break
            else:
                print(f"   Different number of rows: {len(df1_sorted)} vs {len(df2_sorted)}")
    except Exception as e:
        print(f"\n[WARN] Could not perform identity check: {e}")
    
    # Summary
    print()
    print("=" * 80)
    print("5. SUMMARY")
    print("=" * 80)
    
    if len(df1) == len(df2) and cols1 == cols2:
        print("\n✅ Same structure (rows and columns)")
    else:
        print("\n⚠️  Different structure:")
        if len(df1) != len(df2):
            print(f"   - Row count differs: {len(df1)} vs {len(df2)}")
        if cols1 != cols2:
            print(f"   - Columns differ")
    
    if id_col and len(common_ids) > 0:
        overlap_pct = len(common_ids) / max(len(ids1), len(ids2)) * 100
        print(f"\n📊 Data overlap: {overlap_pct:.1f}% ({len(common_ids)} common {id_col}s)")
    
    print()


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python compare_csv_files.py file1.csv file2.csv")
        sys.exit(1)
    
    file1 = sys.argv[1]
    file2 = sys.argv[2]
    
    compare_csv_files(file1, file2)
