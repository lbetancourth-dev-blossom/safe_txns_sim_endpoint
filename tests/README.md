# Tests — safe_txns_sim_endpoint

Testing suite for the SageMaker similarity matching endpoint.

## Structure

```
tests/
├── conftest.py                    — pytest fixtures and configuration
├── test_exact_matching.py         — exact field matching logic test
├── process_endpoint.py            — endpoint invocation utility
├── install_sagemaker_notebook.py  — SageMaker notebook setup helper
│
├── similarity/                    — similarity matching tests
│   ├── test_athena_similarity_*.py — Athena query and fallback tests
│   ├── test_similarity_fields.py   — field extraction tests
│   └── test_parquet_similarity.py  — Parquet data integration tests
│
├── endpoint/                      — endpoint code tests
│   ├── test_inference_integration.py      — full pipeline tests
│   ├── test_graceful_degradation.py       — error handling tests
│   └── test_dynamic_reload.py             — module reload tests
│
└── integration/                   — end-to-end tests
    ├── test_local_integration.py  — local CSV tests
    └── test_e2e_with_s3.py        — S3 reference data tests
```

## Running Tests

### All tests
```bash
pytest tests/ -v
```

### By category
```bash
pytest tests/similarity/ -v        # Similarity matching tests
pytest tests/endpoint/ -v          # Endpoint code tests
pytest tests/integration/ -v       # End-to-end tests
```

### Single test
```bash
pytest tests/test_exact_matching.py -v
pytest tests/similarity/test_athena_similarity_window.py -v
```

### With coverage
```bash
pytest tests/ --cov=endpoint --cov-report=html
```

## Utilities

### `process_endpoint.py`
Invoke the endpoint with CSV input and capture response.

```bash
python tests/process_endpoint.py --input data/test_escenarios.csv --output results.csv
```

### `install_sagemaker_notebook.py`
Extract endpoint code from SageMaker notebook (legacy).

## Test Categories

### Similarity Matching (`tests/similarity/`)
- Athena query window calculations
- Parameterized SQL (no f-strings)
- Fallback behavior when no data
- Field extraction and validation
- Parquet data parsing

### Endpoint Integration (`tests/endpoint/`)
- K-Means pipeline execution
- Statistical rules v8
- Graceful degradation (null handling)
- Module hot-reload (dynamic updates)

### End-to-End (`tests/integration/`)
- Full input → output pipeline
- Local CSV reference data
- S3 reference data with Athena
- Cross-account permissions

## Adding New Tests

1. **Similarity test:** Add to `tests/similarity/`
2. **Endpoint test:** Add to `tests/endpoint/`
3. **Integration test:** Add to `tests/integration/`
4. **Quick validation:** Add to `tests/test_*.py` at root level

## Fixtures

Available via `conftest.py`:

- `reset_similarity_module` — Clear caches between tests
- `reset_inference_module` — Reload inference module between tests

Example:
```python
def test_something(reset_similarity_module):
    # Cache is clean
    ...
```

## Test Requirements

See `endpoint/requirements.txt` for runtime dependencies.

Test-specific packages:
- `pytest>=7.0`
- `pytest-cov` (for coverage reports)
- `pandas` (for test data)
- `numpy` (for vector operations)
