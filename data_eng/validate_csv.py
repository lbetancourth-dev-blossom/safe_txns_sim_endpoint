#!/usr/bin/env python3
"""
Validate SafeTransactionResults.csv structure.

Checks:
1. File exists
2. Has correct column order
3. All required columns present
4. No extra columns
5. Data types are reasonable
"""

import pandas as pd
import sys
from pathlib import Path


# Expected structure
EXPECTED_COLUMNS = [
    "uuid",
    "transactionId",
    "idFi",
    "statusWarning",
    "metadata",
    "createdAt",
    "updatedAt"
]


def validate_csv(file_path):
    """
    Validate CSV structure.
    
    Returns:
        bool: True if valid, False otherwise
    """
    print(f"[INFO] Validating: {file_path}")
    
    # Check file exists
    if not Path(file_path).exists():
        print(f"[ERROR] File not found: {file_path}")
        return False
    
    # Read CSV
    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        print(f"[ERROR] Failed to read CSV: {e}")
        return False
    
    # Check columns
    actual_columns = df.columns.tolist()
    
    print(f"\n[VALIDATION] Column Structure:")
    print(f"Expected: {EXPECTED_COLUMNS}")
    print(f"Actual:   {actual_columns}")
    
    # Check exact match
    if actual_columns == EXPECTED_COLUMNS:
        print("✅ [PASS] Column order matches exactly")
    else:
        print("❌ [FAIL] Column order does not match")
        
        # Check for missing columns
        missing = [col for col in EXPECTED_COLUMNS if col not in actual_columns]
        if missing:
            print(f"   Missing columns: {missing}")
        
        # Check for extra columns
        extra = [col for col in actual_columns if col not in EXPECTED_COLUMNS]
        if extra:
            print(f"   Extra columns: {extra}")
        
        # Check for wrong order
        if set(actual_columns) == set(EXPECTED_COLUMNS):
            print(f"   All columns present but in wrong order")
        
        return False
    
    # Validate data
    print(f"\n[VALIDATION] Data Quality:")
    print(f"✅ Total rows: {len(df)}")
    
    # Check for null values in key columns
    key_columns = ["uuid", "transactionId", "createdAt"]
    for col in key_columns:
        null_count = df[col].isna().sum()
        if null_count > 0:
            print(f"⚠️  Warning: {null_count} null values in '{col}'")
        else:
            print(f"✅ No null values in '{col}'")
    
    # Check date format
    try:
        df['createdAt'] = pd.to_datetime(df['createdAt'])
        print(f"✅ createdAt is valid datetime")
        print(f"   Date range: {df['createdAt'].min()} to {df['createdAt'].max()}")
    except Exception as e:
        print(f"❌ createdAt format issue: {e}")
        return False
    
    # Check if sorted by createdAt
    is_sorted = df['createdAt'].is_monotonic_increasing
    if is_sorted:
        print(f"✅ Data is sorted by createdAt")
    else:
        print(f"⚠️  Warning: Data is NOT sorted by createdAt")
    
    print(f"\n✅ [SUCCESS] CSV structure is valid!")
    return True


if __name__ == '__main__':
    file_path = sys.argv[1] if len(sys.argv) > 1 else "data/data_eng/SafeTransactionResults.csv"
    
    valid = validate_csv(file_path)
    sys.exit(0 if valid else 1)
