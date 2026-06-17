# data_eng/

> Per-module AI agent context. Companion to `docs/codemap/04-data-eng/README.md`.

## Purpose

Pipeline ETL Bronze→Silver. Offline. NO se ejecuta en línea con el endpoint — produce los Parquet que después se exponen como tabla Athena consumida por `similarity_matcher`.

## Where things live

```
data_eng/
├── extract_safe_silver.py        — Silver Parquet reader (fast path ~3× Bronze)
├── extract_safe_transactions.py  — Bronze .gz JSON reader (slow path, raw CDC)
├── validate_csv.py               — Valida CSV output
├── compare_csv_files.py          — Diff de 2 CSVs
├── README.md                     — Documentación
└── PERFORMANCE.md                — Benchmarks
```

## Key files

- `extract_safe_silver.py` — default path para extracción. Lee Parquet del Silver layer.
- `extract_safe_transactions.py` — fallback / verificación contra Bronze. Más lento pero source-of-truth.
- `validate_csv.py` — usalo antes de tratar un CSV como input válido del modelo.

## Conventions

- **Date filtering** con `--start YYYY-MM-DD --end YYYY-MM-DD`. Si no pasás fechas, escanea todo (lento).
- **Output schema normalizado**: `uuid`, `transactionId`, `idFi`, `statusWarning`, `metadata`, `createdAt`, `updatedAt`. Ambos extractors lo producen igual.
- **Idempotent**: mismas fechas → mismo output (módulo cambios en el lake).
- **AWS profile `blossom-dev`** por default. Para alpha: `--profile blossom-alpha`.

## Dependencies

- `boto3` (S3)
- `pandas`
- `pyarrow>=12` (Parquet)

## Tests

No hay test suite dedicado. Validación = `validate_csv.py` sobre el output + diff manual contra fechas conocidas.

## Gotchas

- **NO se ejecuta en producción.** Es herramienta offline. Si pensás "voy a llamar `extract_safe_silver.py` desde el endpoint", parate — Athena hace eso ya (`similarity_matcher.py`).
- **Cuentas distintas:** Silver de **dev** vs Silver de **alpha**. El endpoint productivo lee de alpha; estos scripts pueden ir contra dev o alpha según el profile.
- **Bronze es lento** — 5.8s para 240 records vs 2.0s en Silver. Para volúmenes grandes, usá Silver.
- **`metadata` es JSON serializado en string** — si lo necesitás como dict, parsealo con `json.loads()`.

## See also

- [Module overview](../docs/codemap/04-data-eng/README.md)
- [Similarity Athena](../docs/codemap/00-overview/Similarity-Athena.md) — cómo el endpoint consume el output de este pipeline
- [Architecture](../docs/codemap/00-overview/Architecture.md)
- [Root project context](../CLAUDE.md)
