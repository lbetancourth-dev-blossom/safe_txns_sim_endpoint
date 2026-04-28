# Data Engineering Scripts

This folder contains scripts for extracting and processing data from AWS S3 datalake.

## Scripts

### extract_safe_transactions.py

Extracts Safe transaction data from S3 datalake and consolidates into a single CSV file.

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

**Options**:
- `--start-date YYYY-MM-DD`: Filter files from this date onwards
- `--end-date YYYY-MM-DD`: Filter files up to this date
- `--profile PROFILE`: AWS profile name (default: blossom-dev)
- `--output FILE`: Output CSV file path (default: data/data_eng/SafeTransactionResults.csv)

**Example**:

```bash
# Extract April 2026 data
python data_eng/extract_safe_transactions.py \
  --start-date 2026-04-01 \
  --end-date 2026-04-30 \
  --output data/data_eng/SafeTransactions_April2026.csv
```

**Requirements**:
- boto3
- pandas
- AWS CLI configured with SSO profile

**Data Structure**:

Input files are gzipped JSON lines from Kinesis Firehose:
```json
{
  "data": {
    "uuid": "3caca221-7862-4a7f-9a19-88d5d011909f",
    "transactionId": 1806707,
    "idFi": 216,
    "createdAt": "2026-04-28T14:30:00Z",
    ...
  }
}
```

Output is a flat CSV with all fields from the `data` object, sorted by `createdAt`.

**Performance**:
- Processes ~100 files per progress update
- Handles large datasets (10,000+ files)
- In-memory processing (ensure sufficient RAM for large date ranges)

**Notes**:
- Requires AWS SSO login: `aws sso login --profile blossom-dev`
- Files are stored in S3 with partitioning: `year=YYYY/month=MM/day=DD/`
- Each .gz file contains multiple JSON records (one per line)
- Script automatically creates output directory if it doesn't exist
