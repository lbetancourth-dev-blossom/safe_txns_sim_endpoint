# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- **Automatic Record Filtering for Invalid S3 Data** (2026-04-16)
  - Automatically filters out S3 records that don't match validation schema
  - Only includes records with valid metadata.decisionResult structure
  - Logs detailed skip statistics (parse errors, missing fields, schema issues)
  - Raises clear error if all records are invalid
  
- **Comprehensive Data Validation System** (2026-04-15)
  - Added `schema_validator.py` for schema definition and validation
  - Added `validate_s3_data.py` CLI tool for pre-upload validation
  - Added `DATA_PREPARATION.md` guide for reference data preparation
  - Integrated automatic validation in similarity_matcher.py

- **Flexible S3 Configuration for Similarity Matcher** (2026-04-15)
  - Added support for custom S3 paths via function parameters
  - Added support for full S3 URI (e.g., `s3://bucket/path/file.csv`)
  - Added environment variable configuration (`SIMILARITY_S3_BUCKET`, `SIMILARITY_S3_KEY`)
  - Enhanced caching system to support multiple S3 sources simultaneously
  - Added `s3_source` field to response showing which S3 path was used
  - Added `get_s3_config_from_env()` utility function
  - Added CLI arguments: `--s3-bucket`, `--s3-key`, `--s3-uri`
  - Created comprehensive usage documentation (`SIMILARITY_USAGE.md`)

### Changed
- **Similarity Matcher Filtering** (2026-04-16)
  - Changed from warning on invalid records to automatic filtering
  - Only valid records are used for similarity matching
  - Invalid records are silently skipped with detailed logging
  
- **Similarity Matcher Cache System**
  - Changed from single global cache to dictionary-based cache (keyed by S3 URI)
  - Cache now supports multiple reference datasets simultaneously
  - `clear_cache()` now accepts optional `s3_uri` parameter to clear specific cache

### Skip Reasons Tracked
1. `parse_error`: JSON parsing failures
2. `missing_metadata`: No metadata field in record
3. `missing_decisionResult`: No decisionResult in metadata
4. `schema_invalid`: Missing core fields (Cluster, Distance_to_Centroid, etc.)
5. `feature_extraction_failed`: Cannot extract feature vector

### Configuration Priority
1. `s3_uri` parameter (highest priority)
2. `s3_bucket` + `s3_key` parameters
3. Environment variables
4. Default hardcoded values (lowest priority)

## [1.0.0] - 2026-04-15

### Added
- Initial release
- SageMaker endpoint implementation with K-Means clustering
- Statistical rules system (v8) for fraud detection
- Similarity matcher for historical transaction comparison
- Comprehensive README with architecture and deployment guide
- Jupyter notebook for deployment and testing

### Features
- K-Means clustering with distance calculation
- 12 configurable fraud detection rules
- Cosine similarity matching against S3 reference data
- Hybrid scoring policy (clustering + rules)
- Multi-level decisions: Accept, User Auth, Admin Review, Reject
- Batch and real-time processing support
