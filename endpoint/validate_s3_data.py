"""
CSV Data Validator for Similarity Matching
==========================================

Offline CLI tool to validate reference CSVs before uploading to the data lake.
Checks that metadata.decisionResult contains the expected schema from
inference_rules.py preprocessing (num__* and cat__* features).

Usage:
    python validate_s3_data.py --local-csv local_file.csv --show-schema
    python validate_s3_data.py --local-csv local_file.csv --output report.json
    python validate_s3_data.py --s3-uri s3://bucket/path/file.csv --output report.json
"""

import argparse
import json
import pandas as pd
import boto3
from typing import Dict, List
import sys

try:
    from schema_validator import (
        EXPECTED_SCHEMA,
        EXPECTED_NUM_FEATURES,
        EXPECTED_CAT_FEATURES,
        EXPECTED_POST_FIELDS,
        CORE_FIELDS_FOR_SIMILARITY,
        validate_decision_result_schema,
        validate_s3_reference_data,
        get_schema_info
    )
except ImportError:
    print("ERROR: schema_validator.py not found in current directory")
    sys.exit(1)


def load_csv_from_s3(s3_uri: str) -> pd.DataFrame:
    """Load CSV from S3 URI."""
    if not s3_uri.startswith("s3://"):
        raise ValueError(f"Invalid S3 URI: {s3_uri}")
    
    parts = s3_uri[5:].split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid S3 URI format: {s3_uri}")
    
    bucket, key = parts
    
    import io
    s3_client = boto3.client("s3")
    response = s3_client.get_object(Bucket=bucket, Key=key)
    csv_content = response["Body"].read().decode("utf-8")

    return pd.read_csv(io.StringIO(csv_content))


def validate_csv_structure(df: pd.DataFrame) -> Dict:
    """
    Validate CSV structure and required columns.
    
    Required columns:
    - metadata: JSON string containing decisionResult
    - statusWarning: Label for similarity matching
    - TransactionID (or similar): Unique identifier
    """
    report = {
        "total_rows": len(df),
        "columns": list(df.columns),
        "has_metadata": "metadata" in df.columns,
        "has_statusWarning": "statusWarning" in df.columns,
        "has_transaction_id": False,
        "issues": []
    }
    
    # Check for TransactionID column
    id_columns = ["TransactionID", "transactionId", "transaction_id", "id"]
    for col in id_columns:
        if col in df.columns:
            report["has_transaction_id"] = True
            report["transaction_id_column"] = col
            break
    
    if not report["has_transaction_id"]:
        report["issues"].append(
            "No TransactionID column found. Expected one of: " + ", ".join(id_columns)
        )
    
    if not report["has_metadata"]:
        report["issues"].append("Missing required column: 'metadata'")
    
    if not report["has_statusWarning"]:
        report["issues"].append("Missing required column: 'statusWarning'")
    
    return report


def validate_metadata_schema(df: pd.DataFrame, sample_size: int = 100) -> Dict:
    """
    Validate that metadata.decisionResult contains expected schema.
    
    Checks a sample of rows to verify schema compliance.
    """
    if "metadata" not in df.columns:
        return {"error": "No 'metadata' column found"}
    
    sample_df = df.head(sample_size) if len(df) > sample_size else df
    
    results = {
        "total_sampled": len(sample_df),
        "valid_count": 0,
        "invalid_count": 0,
        "parse_errors": 0,
        "missing_decisionResult": 0,
        "schema_errors": [],
        "field_coverage": {},
        "sample_valid_record": None,
        "sample_invalid_record": None
    }
    
    all_fields_seen = set()
    
    for idx, row in sample_df.iterrows():
        try:
            # Parse metadata
            metadata = row["metadata"]
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            
            # Check for decisionResult
            if "decisionResult" not in metadata:
                results["missing_decisionResult"] += 1
                continue
            
            decision_result = metadata["decisionResult"]
            
            # Track all fields seen
            all_fields_seen.update(decision_result.keys())
            
            # Validate schema
            is_valid, missing, extra = validate_decision_result_schema(
                decision_result,
                strict=False,
                require_all=False
            )
            
            if is_valid:
                results["valid_count"] += 1
                if results["sample_valid_record"] is None:
                    results["sample_valid_record"] = {
                        "row_index": int(idx),
                        "fields_count": len(decision_result),
                        "has_all_core": len(missing) == 0
                    }
            else:
                results["invalid_count"] += 1
                results["schema_errors"].append({
                    "row_index": int(idx),
                    "missing_fields": missing[:5],
                    "fields_count": len(decision_result)
                })
                if results["sample_invalid_record"] is None:
                    results["sample_invalid_record"] = {
                        "row_index": int(idx),
                        "missing_fields": missing,
                        "fields_count": len(decision_result)
                    }
        
        except json.JSONDecodeError as e:
            results["parse_errors"] += 1
        except Exception as e:
            results["parse_errors"] += 1
    
    # Calculate field coverage
    for field in EXPECTED_SCHEMA:
        results["field_coverage"][field] = field in all_fields_seen
    
    # Summary stats
    results["coverage_rate"] = results["valid_count"] / results["total_sampled"] if results["total_sampled"] > 0 else 0
    results["expected_fields_coverage"] = sum(results["field_coverage"].values()) / len(EXPECTED_SCHEMA) if EXPECTED_SCHEMA else 0
    
    return results


def generate_validation_report(
    s3_uri: str = None,
    local_file: str = None,
    output_file: str = None,
    sample_size: int = 100
) -> Dict:
    """Generate comprehensive validation report."""
    
    # Load data
    if s3_uri:
        print(f"Loading data from S3: {s3_uri}")
        df = load_csv_from_s3(s3_uri)
        source = s3_uri
    elif local_file:
        print(f"Loading data from local file: {local_file}")
        df = pd.read_csv(local_file)
        source = local_file
    else:
        raise ValueError("Must provide either s3_uri or local_file")
    
    print(f"Loaded {len(df)} rows")
    
    # Validate CSV structure
    print("\n=== Validating CSV Structure ===")
    structure_report = validate_csv_structure(df)
    
    if structure_report["issues"]:
        print("⚠️  Issues found:")
        for issue in structure_report["issues"]:
            print(f"  - {issue}")
    else:
        print("✓ CSV structure looks good")
    
    # Validate metadata schema
    print(f"\n=== Validating Metadata Schema (sample: {sample_size}) ===")
    schema_report = validate_metadata_schema(df, sample_size=sample_size)
    
    print(f"Valid records: {schema_report['valid_count']}/{schema_report['total_sampled']} ({schema_report['coverage_rate']:.1%})")
    print(f"Invalid records: {schema_report['invalid_count']}")
    print(f"Parse errors: {schema_report['parse_errors']}")
    print(f"Missing decisionResult: {schema_report['missing_decisionResult']}")
    print(f"Expected fields coverage: {schema_report['expected_fields_coverage']:.1%}")
    
    # Full report
    full_report = {
        "source": source,
        "timestamp": pd.Timestamp.now().isoformat(),
        "structure": structure_report,
        "schema": schema_report,
        "expected_schema_info": get_schema_info(),
        "recommendations": []
    }
    
    # Generate recommendations
    if structure_report["issues"]:
        full_report["recommendations"].append(
            "Fix CSV structure issues before using as reference data"
        )
    
    if schema_report["coverage_rate"] < 0.8:
        full_report["recommendations"].append(
            f"Low schema coverage ({schema_report['coverage_rate']:.1%}). "
            "Ensure metadata.decisionResult contains all preprocessed fields from inference_rules.py"
        )
    
    if schema_report["expected_fields_coverage"] < 0.9:
        full_report["recommendations"].append(
            f"Only {schema_report['expected_fields_coverage']:.1%} of expected fields found. "
            "Check if reference data was generated with the same preprocessing pipeline."
        )
    
    # Save report if requested
    if output_file:
        with open(output_file, 'w') as f:
            json.dump(full_report, f, indent=2)
        print(f"\n✓ Full report saved to: {output_file}")
    
    return full_report


def main():
    parser = argparse.ArgumentParser(
        description="Validate S3 reference data for similarity matching"
    )
    parser.add_argument(
        "--s3-uri",
        type=str,
        help="S3 URI to validate (e.g., s3://bucket/path/file.csv)"
    )
    parser.add_argument(
        "--local-csv",
        type=str,
        help="Local CSV file to validate"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file for validation report (JSON)"
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=100,
        help="Number of rows to sample for schema validation (default: 100)"
    )
    parser.add_argument(
        "--show-schema",
        action="store_true",
        help="Show expected schema information"
    )
    
    args = parser.parse_args()
    
    # Show schema info
    if args.show_schema:
        print("\n=== Expected Schema Information ===")
        schema_info = get_schema_info()
        num_count = schema_info['num_features_count']
        cat_count = schema_info['cat_features_count']
        print(f"\nNumerical Features ({num_count}):")
        for f in schema_info['numerical_features'][:5]:
            print(f"  - {f}")
        print(f"  ... and {num_count - 5} more")

        print(f"\nCategorical Features ({cat_count}):")
        for f in schema_info['categorical_features'][:5]:
            print(f"  - {f}")
        print(f"  ... and {cat_count - 5} more")

        print(f"\nPost-processing Fields ({len(EXPECTED_POST_FIELDS)}):")
        for f in EXPECTED_POST_FIELDS:
            print(f"  - {f}")
        
        print(f"\nCore Fields for Similarity:")
        for f in CORE_FIELDS_FOR_SIMILARITY:
            print(f"  - {f}")
        
        return
    
    # Validate data
    if not args.s3_uri and not args.local_csv:
        parser.print_help()
        print("\nERROR: Must provide either --s3-uri or --local-csv")
        sys.exit(1)
    
    try:
        report = generate_validation_report(
            s3_uri=args.s3_uri,
            local_file=args.local_csv,
            output_file=args.output,
            sample_size=args.sample_size
        )
        
        # Print recommendations
        if report["recommendations"]:
            print("\n=== Recommendations ===")
            for i, rec in enumerate(report["recommendations"], 1):
                print(f"{i}. {rec}")
        else:
            print("\n✓ No issues found. Data looks ready for similarity matching!")
    
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
