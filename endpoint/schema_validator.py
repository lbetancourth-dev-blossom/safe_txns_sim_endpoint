"""
Schema Validator for Similarity Matching
==========================================

This module defines and validates the expected schema for similarity matching.
It ensures that both incoming transactions and reference data from S3 have
the exact same structure.

Schema Definition:
- All features from inference_rules.py preprocessing output
- Includes num__* features (numerical/transformed)
- Includes cat__* features (categorical/one-hot encoded)
- Includes post-processing fields (Cluster, Distance_to_Centroid, etc.)
"""

from typing import Dict, List, Set, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# =========================
# Expected Schema Definition
# =========================

# Numerical features (from preprocessing pipeline)
EXPECTED_NUM_FEATURES = [
    "num__amount",
    "num__is_night",
    "num__hour_sin",
    "num__hour_cos",
    "num__day_of_week_cos",
    "num__count_all_txn_last_5m",
    "num__total_amount_all_txn_last_5m",
    "num__count_txn_to_recipient_account_last_5m",
    "num__total_amount_txn_to_recipient_account_last_5m",
    "num__count_txn_to_recipient_account_in_last_2_months",
    "num__is_first_txn_from_this_olb_user_to_this_recipient_account_q_6h",
    "num__amount_coef_var_lst6m",
    "num__pct_txns_under_100_lst6m",
    "num__pct_txns_over_1k_lst6m",
    "num__user_avg_amount_txn_per_active_day_last_6_months",
    "num__count_user_all_txn_in_last_6_months",
    "num__count_user_cancelled_txn_in_last_week",
    "num__count_user_cancelled_txn_in_last_month",
    "num__count_user_potential_fraud_txn_in_last_2_months",
    "num__recency_user_created_days",
    "num__count_suspected_actions_in_current_session",
    "num__total_actions_session",
    "num__is_auth_email_session",
    "num__is_auth_phone_session",
    "num__total_accounts",
    "num__user_age",
    "num__is_amount_greater_than_cu_p95_amount_ach_txn_in_last_6_months",
    "num__txn_amount_vs_cu_avg_amount_ach_txn_in_last_6_months",
    "num__is_batch",
    "num__amt_vs_user_ach_avg_day",
    "num__ach_count_share_6m",
]

# Categorical features (from preprocessing pipeline)
EXPECTED_CAT_FEATURES = [
    "cat__TransactionProcessingType_Intime",
    "cat__TransactionProcessingType_Intime_From_Recurrent",
    "cat__TransactionProcessingType_Recurrent",
    "cat__TransactionProcessingType_Schedule",
    "cat__TransactionOrigin_External Internal",
    "cat__TransactionOrigin_Internal External",
    "cat__TransactionOrigin_M2m External",
    "cat__TransactionCategory_SEND_MONEY_ACH",
    "cat__TransactionCategory_SEND_MONEY_BATCH_PAYMENT_ACH",
    "cat__TransactionCategory_SEND_MONEY_PAYROLL_ACH",
    "cat__TransactionCategory_SINGLE_COLLECTION_ACH",
    "cat__TransactionCategory_TRANSFER_EXTERNAL_TO_LOAN_ACH",
    "cat__TransactionCategory_TRANSFER_INTERNAL_EXTERNAL_ACH",
    "cat__user_type_mixed",
    "cat__user_type_personal",
    "cat__access_DESKTOP",
    "cat__access_MOBILE",
    "cat__access_missing",
]

# Post-processing fields (from clustering and rules)
EXPECTED_POST_FIELDS = [
    "Cluster",
    "Distance_to_Centroid",
    "risk_score",
    "risk_decision",
    "is_outlier",
]

# Optional fields (not used for similarity but may be present)
OPTIONAL_FIELDS = [
    "top_contributors",
    "audit_category",
    "audit_explanation",
    "ux_copy",
]

# Complete expected schema
EXPECTED_SCHEMA = EXPECTED_NUM_FEATURES + EXPECTED_CAT_FEATURES + EXPECTED_POST_FIELDS

# Core fields required for similarity (minimum)
CORE_FIELDS_FOR_SIMILARITY = [
    "Cluster",
    "Distance_to_Centroid",
    "risk_score",
    "is_outlier",
]


# =========================
# Validation Functions
# =========================

def validate_decision_result_schema(
    decision_result: Dict,
    strict: bool = False,
    require_all: bool = False
) -> Tuple[bool, List[str], List[str]]:
    """
    Validate that a decision result has the expected schema.
    
    Args:
        decision_result: Dictionary containing transaction decision result
        strict: If True, fails if extra fields are present
        require_all: If True, requires all expected fields (not just core)
    
    Returns:
        Tuple of (is_valid, missing_fields, extra_fields)
    """
    if not isinstance(decision_result, dict):
        return False, ["Not a dictionary"], []
    
    result_keys = set(decision_result.keys())
    
    # Determine which fields to require
    if require_all:
        required_fields = set(EXPECTED_SCHEMA)
    else:
        # At minimum, require core fields for similarity
        required_fields = set(CORE_FIELDS_FOR_SIMILARITY)
    
    # Check for missing fields
    missing = sorted(required_fields - result_keys)
    
    # Check for extra fields (only if strict)
    extra = []
    if strict:
        allowed_fields = set(EXPECTED_SCHEMA + OPTIONAL_FIELDS)
        extra = sorted(result_keys - allowed_fields)
    
    is_valid = len(missing) == 0 and (not strict or len(extra) == 0)
    
    return is_valid, missing, extra


def validate_s3_reference_data(
    reference_data: List[Dict],
    min_coverage: float = 0.9
) -> Tuple[bool, Dict]:
    """
    Validate that reference data from S3 has consistent schema.
    
    Args:
        reference_data: List of dictionaries with 'metadata' field
        min_coverage: Minimum fraction of records that must have valid schema
    
    Returns:
        Tuple of (is_valid, validation_report)
    """
    total_records = len(reference_data)
    valid_records = 0
    schema_issues = []
    field_coverage = {field: 0 for field in EXPECTED_SCHEMA}
    
    for i, record in enumerate(reference_data):
        # Check if metadata exists
        if "metadata" not in record:
            schema_issues.append(f"Record {i}: Missing 'metadata' field")
            continue
        
        # Parse metadata (should be dict or JSON string)
        metadata = record["metadata"]
        if isinstance(metadata, str):
            try:
                import json
                metadata = json.loads(metadata)
            except Exception as e:
                schema_issues.append(f"Record {i}: Invalid JSON in metadata - {e}")
                continue
        
        # Check if decisionResult exists
        if "decisionResult" not in metadata:
            schema_issues.append(f"Record {i}: Missing 'decisionResult' in metadata")
            continue
        
        decision_result = metadata["decisionResult"]
        
        # Validate schema
        is_valid, missing, extra = validate_decision_result_schema(
            decision_result,
            strict=False,
            require_all=False
        )
        
        if is_valid:
            valid_records += 1
            # Track field coverage
            for field in decision_result.keys():
                if field in field_coverage:
                    field_coverage[field] += 1
        else:
            schema_issues.append(
                f"Record {i}: Invalid schema - missing {missing[:5]}"
            )
    
    coverage_rate = valid_records / total_records if total_records > 0 else 0
    is_valid = coverage_rate >= min_coverage
    
    report = {
        "total_records": total_records,
        "valid_records": valid_records,
        "invalid_records": total_records - valid_records,
        "coverage_rate": coverage_rate,
        "min_coverage_required": min_coverage,
        "is_valid": is_valid,
        "field_coverage": {
            field: count / total_records if total_records > 0 else 0
            for field, count in field_coverage.items()
        },
        "schema_issues": schema_issues[:10],  # First 10 issues
        "total_issues": len(schema_issues)
    }
    
    return is_valid, report


def get_schema_info() -> Dict:
    """Get information about the expected schema."""
    return {
        "numerical_features": EXPECTED_NUM_FEATURES,
        "categorical_features": EXPECTED_CAT_FEATURES,
        "num_features_count": len(EXPECTED_NUM_FEATURES),
        "cat_features_count": len(EXPECTED_CAT_FEATURES),
        "total_features": len(EXPECTED_NUM_FEATURES) + len(EXPECTED_CAT_FEATURES),
    }


def validate_features_only(decision_result: Dict, require_all: bool = True) -> bool:
    """
    Quick validation that checks only for presence of num__ and cat__ features.
    
    Used for similarity matching where post-processing fields are not required.
    
    Args:
        decision_result: Dictionary to validate
        require_all: If True, requires ALL expected features. If False, accepts partial matches.
    
    Returns:
        True if all (or sufficient) num__ and cat__ features are present, False otherwise
    """
    if not decision_result:
        return False
    
    if require_all:
        # Check all numerical features
        for feat in EXPECTED_NUM_FEATURES:
            if feat not in decision_result:
                return False
        
        # Check all categorical features  
        for feat in EXPECTED_CAT_FEATURES:
            if feat not in decision_result:
                return False
        
        return True
    else:
        # Flexible mode: accept if at least 50% of expected features are present
        present_num = sum(1 for feat in EXPECTED_NUM_FEATURES if feat in decision_result)
        present_cat = sum(1 for feat in EXPECTED_CAT_FEATURES if feat in decision_result)
        
        num_coverage = present_num / len(EXPECTED_NUM_FEATURES) if len(EXPECTED_NUM_FEATURES) > 0 else 0
        cat_coverage = present_cat / len(EXPECTED_CAT_FEATURES) if len(EXPECTED_CAT_FEATURES) > 0 else 0
        
        # Require at least 50% coverage of both num and cat features
        return num_coverage >= 0.5 and cat_coverage >= 0.5


def check_schema_compatibility(
    source1_fields: List[str],
    source2_fields: List[str]
) -> Dict:
    """
    Check compatibility between two schemas.
    
    Args:
        source1_fields: Fields from first source (e.g., incoming transaction)
        source2_fields: Fields from second source (e.g., reference data)
    
    Returns:
        Dictionary with compatibility report
    """
    set1 = set(source1_fields)
    set2 = set(source2_fields)
    
    common = set1 & set2
    only_in_1 = set1 - set2
    only_in_2 = set2 - set1
    
    # Check if core fields are present in both
    core_set = set(CORE_FIELDS_FOR_SIMILARITY)
    core_in_1 = core_set & set1
    core_in_2 = core_set & set2
    core_in_both = core_set & common
    
    compatibility_score = len(common) / len(set1 | set2) if (set1 | set2) else 0
    
    return {
        "compatible": len(core_in_both) == len(CORE_FIELDS_FOR_SIMILARITY),
        "compatibility_score": compatibility_score,
        "common_fields_count": len(common),
        "total_unique_fields": len(set1 | set2),
        "only_in_source1": sorted(only_in_1),
        "only_in_source2": sorted(only_in_2),
        "core_fields_in_both": sorted(core_in_both),
        "missing_core_in_source1": sorted(core_set - core_in_1),
        "missing_core_in_source2": sorted(core_set - core_in_2),
    }


# =========================
# Standalone Testing
# =========================

if __name__ == "__main__":
    import json
    
    print("\n=== Schema Validator for Similarity Matching ===\n")
    
    # Display schema info
    schema_info = get_schema_info()
    print(f"Expected Schema:")
    print(f"  - Numerical features: {schema_info['num_features_count']}")
    print(f"  - Categorical features: {schema_info['cat_features_count']}")
    print(f"  - Post-processing fields: {len(EXPECTED_POST_FIELDS)}")
    print(f"  - Total expected fields: {schema_info['total_features']}")
    print(f"  - Core fields for similarity: {len(CORE_FIELDS_FOR_SIMILARITY)}")
    print(f"\nCore fields: {CORE_FIELDS_FOR_SIMILARITY}")
    
    # Test with a sample decision result
    print("\n=== Testing Sample Decision Result ===")
    
    sample_result = {
        "Cluster": 2,
        "Distance_to_Centroid": 45.3,
        "risk_score": 75,
        "is_outlier": 1,
        "num__amount": 1500.0,
        "num__is_night": 1,
        # Add more fields as needed
    }
    
    is_valid, missing, extra = validate_decision_result_schema(
        sample_result,
        strict=False,
        require_all=False
    )
    
    print(f"\nValidation Result:")
    print(f"  Valid: {is_valid}")
    print(f"  Missing core fields: {missing if missing else 'None'}")
    print(f"  Extra fields: {extra if extra else 'None'}")
    
    # Test schema compatibility
    print("\n=== Testing Schema Compatibility ===")
    
    fields1 = list(sample_result.keys())
    fields2 = EXPECTED_SCHEMA[:20]  # Simulate partial match
    
    compat = check_schema_compatibility(fields1, fields2)
    print(f"\nCompatibility Score: {compat['compatibility_score']:.2%}")
    print(f"Compatible (core fields): {compat['compatible']}")
    print(f"Common fields: {compat['common_fields_count']}")
    print(f"Missing core in source1: {compat['missing_core_in_source1']}")
    
    print("\n✓ Schema validation tests completed")
