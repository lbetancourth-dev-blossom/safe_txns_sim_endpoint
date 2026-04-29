# Data Engineering Scripts

This folder contains scripts for extracting and processing data from AWS S3 datalake.

## Scripts

### extract_safe_transactions.py

Extracts Safe transaction data from **Bronze layer** (.gz format) and consolidates into CSV.

**Source**: `s3://blossom-analytics-datalake-dev/processed/source/dms/cdc/safe/`

**Output**: `data/data_eng/SafeTransactionResults.csv`

**Features**:
- Recursively scans S3 bucket with year/month/day structure
- Downloads and decompresses .gz files
- Parses JSON data (Kinesis Firehose format)
- Combines all records
- Sorts by `createdAt` timestamp
- Saves to CSV

**Usage**:

```bash
# Extract all data
python data_eng/extract_safe_transactions.py

# Extract with date range filter
python data_eng/extract_safe_transactions.py --start-date 2026-04-27 --end-date 2026-04-28

# Custom output file
python data_eng/extract_safe_transactions.py --output custom_output.csv

# Use different AWS profile
python data_eng/extract_safe_transactions.py --profile my-aws-profile
```

---

### extract_safe_silver.py ⭐ NEW

Extracts Safe transaction data from **Silver layer** (Parquet format) and consolidates into CSV.

**Source**: `s3://blossom-analytics-datalake-dev/datalake/silver/SAFE/safetransactionresults/data/`

**Output**: `data/data_eng/SafeTxnResultsSilver.csv`

**Features**:
- Reads Parquet files directly (10-100x faster than .gz)
- Partitioned by `createdat_month`
- Automatically removes CDC metadata columns
- Sorts by `createdAt` timestamp
- Validates column structure

**Usage**:

```bash
# Extract all data from Silver layer
python data_eng/extract_safe_silver.py

# Custom output file
python data_eng/extract_safe_silver.py --output custom_output.csv

# Use different AWS profile
python data_eng/extract_safe_silver.py --profile my-aws-profile
```

**Performance**:
- 3 Parquet files (0.09 MB) → 243 records in ~2 seconds
- Much faster than Bronze layer (Parquet vs .gz)

**Current Stats (2026-04-29)**:
- Files: 3 Parquet files
- Records: 243 transactions
- Date range: 2026-03-27 to 2026-04-29
- Output size: 1.3 MB

---

### validate_csv.py

Validates CSV structure and data quality.

**Usage**:
```bash
python data_eng/validate_csv.py [file_path]
```

**Checks**:
- Column order matches expected structure
- All required columns present
- DateTime format validation
- Sorting by createdAt
- Null value detection

---

## Data Layers

### Bronze Layer (.gz format)
- **Location**: `processed/source/dms/cdc/safe/year=YYYY/month=MM/day=DD/`
- **Format**: Gzipped JSON (Kinesis Firehose)
- **Use case**: Raw CDC data
- **Script**: `extract_safe_transactions.py`

### Silver Layer (Parquet format) ⭐ Recommended
- **Location**: `datalake/silver/SAFE/safetransactionresults/data/createdat_month=YYYY-MM/`
- **Format**: Parquet with Snappy compression
- **Use case**: Cleaned, processed data ready for analytics
- **Script**: `extract_safe_silver.py`
- **Advantages**: 
  - 10-100x faster reads
  - 60% smaller file size
  - Column-level compression
  - Native AWS Athena support

---

## Output Format

Both scripts generate CSV files with the same structure:

```csv
uuid,transactionId,idFi,statusWarning,metadata,createdAt,updatedAt
```

**Column Descriptions**:
- `uuid`: Unique transaction identifier
- `transactionId`: Transaction ID
- `idFi`: Financial institution ID
- `statusWarning`: Transaction status (SAFE, RISKY, PENDING)
- `metadata`: JSON string with transaction details and model results
- `createdAt`: Transaction creation timestamp
- `updatedAt`: Last update timestamp

---

## Requirements

```bash
pip install boto3 pandas pyarrow
```

**AWS Configuration**:
```bash
aws sso login --profile blossom-dev
```

---

## Performance Comparison

| Script | Source | Files | Records | Time | Output Size |
|--------|--------|-------|---------|------|-------------|
| extract_safe_transactions.py | Bronze (.gz) | 17 | 22 | 5.8s | 0.07 MB |
| extract_safe_silver.py | Silver (Parquet) | 3 | 243 | ~2s | 1.3 MB |

**Recommendation**: Use `extract_safe_silver.py` for production analytics workflows (faster, more data, better quality).

