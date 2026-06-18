# Implementation Spec: DATA-1264

## Runtime

- **Implementer**: `blossom-implementer`
- **Routing rationale**: Cambios de backend Python (SageMaker endpoint, módulos similarity/inference), sin trabajo de UI. Ticket es feature de datos, no pixel-driven frontend.

---

## Pre-execute checklist

### Pre-merge DoD (BLOQUEANTE — antes de mergear el PR)

- [ ] **F2 — Platform team: 7-day S3 lifecycle rule.** Confirmar que plataforma añadió la regla de delete a 7 días sobre `s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/`. Link el ticket de plataforma o la confirmación del equipo en el PR description.
- [ ] **F1 — Parameterized SQL en el código fuente.** Confirmar via grep que NO existe f-string SQL en `endpoint/similarity_matcher.py` (test contract `test_no_fstring_sql_in_module` debe estar verde).
- [ ] **F5+ — Structured logging en place.** Confirmar `similarity.no_history` y `similarity.athena_failure` se emiten con `idolbuser_hash` (NUNCA `idolbuser` plaintext).
- [ ] **F3 — Audit team ownership documentado.** `docs/ATHENA_INTEGRATION.md` indica que el audit trail per-lookup está owned por el audit/compliance team de Blossom y NO es scope de este ticket.

### Pre-T0 (antes de codear)

- [ ] **Cross-account IAM check (informativo, NO bloqueante para merge tras F5 gate applied 2026-06-17).** El rol SageMaker en cuenta AWS **development** debe tener permisos cross-account para leer del data lake **alpha** (`blossom-analytics-datalake-alpha`). Si NO está provisionado → escalar a plataforma pre-deploy. **AC5 satisfaction es POST-DEPLOY observando structured logs (F5 gate), NO pre-merge.**
- [ ] Bucket policy de `blossom-analytics-datalake-alpha` permite explícitamente el principal del rol SageMaker en development.

### Post-deploy en alpha (BLOQUEANTE para promoción a higher envs, NO para merge)

- [ ] Monitorear CloudWatch `similarity.athena_failure` count durante 24h después del deploy en alpha. Expected count = 0 (o matchea el baseline horario de timeouts bajo carga normal). Si > 0 con `category=permission` → cross-account IAM roto, rollback o escalar a plataforma.

---

## Premisas cerradas (de `plan.md` — D1-D5 CERRADAS POR EL DEV 2026-06-16 + gate decisions aplicadas 2026-06-17)

| ID | Decisión cerrada |
|----|------------------|
| D1 | **Graceful degradation**. Si `idOLBUserTxns` o `createdAtTxns` faltan/null en el payload → K-means + rules corren normalmente, `sim_*=null`. El endpoint NUNCA devuelve 400 por campos de similarity. |
| D2 | **Athena SINGLE-SOURCE. NO `USE_ATHENA` env var. NO Parquet fallback.** El path Parquet se elimina de la ruta de similarity. `similarity_matcher.py` tiene UNA sola fuente: Athena. |
| D3 | **PyAthena on-demand**. Conexión se abre dentro de `find_similar_transaction()` (o del nuevo Athena loader), se cierra al terminar. NO singleton, NO pool. |
| D4 | **Timeout 10s + log warning + sim_*=null**. Sin retry. K-means intacto. |
| D5 | **NO separate validation script** (AMENDED 2026-06-17 — F5 gate). Validation se hace dentro del production code (`pyathena.connect()` en `find_similar_transaction()`) + post-deploy alpha observation (24h en CloudWatch via structured logs). AC5 satisfaction es POST-DEPLOY, NO pre-merge. |
| F1 | **PyAthena parameterized queries** (gate applied 2026-06-17). `cursor.execute(sql, {"user": int(idolbuser), "window_start": window_start_ts})`. NO f-string SQL. Grep test enforced. |
| F5+ | **Structured logging two-path** (gate applied 2026-06-17). `similarity.no_history` (INFO, 0 rows) vs `similarity.athena_failure` (WARNING/ERROR, exception + classified category). `idOLBUser` SIEMPRE sha256-truncated hash, nunca plaintext. |

---

## File manifest (revisado tras D2)

| Archivo | Acción | LoC ~ | Notas |
|---------|--------|-------|-------|
| `endpoint/similarity_matcher.py` | MODIFY | +170 / -90 | Añadir `load_reference_data_from_athena()`, `_normalize_athena_columns()`, `_compute_sliding_window()`, `_ATHENA_CACHE`, timeout wrapper. **Eliminar** `load_reference_data_from_s3()` y `_load_parquet_directory_from_s3()` de la ruta de similarity (D2) |
| `endpoint/inference_rules.py` | MODIFY | +40 / -10 | Añadir `_validate_similarity_input()`, llamar SIEMPRE a `load_reference_data_from_athena` (sin condicional). Eliminar uso de `SIMILARITY_S3_BUCKET`/`SIMILARITY_S3_KEY` en el bloque similarity |
| `endpoint/requirements.txt` | CREATE | 5 | pyathena>=3.0, python-dateutil>=2.8, pyarrow, boto3 |
| `endpoint_test/similarity_matcher.py` | MODIFY | mirror | Idéntico al endpoint/ |
| `endpoint_test/inference_rules.py` | MODIFY | mirror | Idéntico al endpoint/ |
| `endpoint_test/requirements.txt` | CREATE | 5 | Mirror |
| `deploy/deploy_with_sdk.py` | MODIFY | +8 | Añadir `source_dir='endpoint'`. Añadir env vars Athena (SIMILARITY_ATHENA_DATABASE/TABLE/S3_STAGING/REGION + ATHENA_WINDOW_MONTHS + ATHENA_TIMEOUT_SECONDS). **NO** añadir USE_ATHENA (D2) |
| `deploy/deploy_notebook.py` | MODIFY | +8 | Mismo cambio que deploy_with_sdk.py |
| ~~`deploy/validate_athena_connection.py`~~ | ~~CREATE~~ | — | **REMOVED por F5 gate (applied 2026-06-17).** Validation via production code + post-deploy alpha observation. NO script aparte. |
| `docs/ATHENA_INTEGRATION.md` | CREATE | ~220 | Cross-account IAM policy (dev→alpha), query pattern (PyAthena parameterized), env vars (sin toggle), troubleshooting, structured logging alerting playbook (F5+), post-deploy alpha observation runbook |
| `docs/ENDPOINT_FLOW_SEQUENCE.md` | MODIFY | +5 / -3 | Paso 5 (similarity) usa Athena exclusivamente; eliminar mención a Parquet |
| `test/test_athena_similarity_input_contract.py` | CREATE | ~100 | AC1, AC2 + D1 graceful tests + cross-account env var presence |
| `test/test_athena_similarity_window.py` | CREATE | ~100 | Window sliding now-6m por call |
| `test/test_athena_similarity_fallback.py` | CREATE | ~120 | R5 + D1 + D4 — K-means intacto bajo todo failure mode |
| `test/test_athena_similarity_sql_parametrized.py` | CREATE | ~60 | **F1 mitigation** — grep test que verifica NO existe f-string SQL en el módulo. Verifica que `cursor.execute()` se llama con dict de params. |
| `test/test_athena_similarity_logging.py` | CREATE | ~100 | **F5+ mitigation** — verifica los dos paths: `similarity.no_history` (INFO) y `similarity.athena_failure` (WARNING) con `idolbuser_hash` truncado. Verifica que `classify_exception()` clasifica correctamente PermissionError, ThrottlingError, TimeoutError, etc. |

UNCHANGED:
- `endpoint/schema_validator.py` (sin cambios — features extraction sigue igual)
- `endpoint/statistical_rules.py` (independiente)
- Todos los modelos joblib / csv (sin cambios)

REMOVED (de la ruta de similarity, por D2):
- `similarity_matcher.load_reference_data_from_s3()` (dead code o eliminar — el implementer decide después de buscar otros callers con grep)
- `similarity_matcher._load_parquet_directory_from_s3()` (dead code o eliminar)
- Env vars `SIMILARITY_S3_BUCKET`, `SIMILARITY_S3_KEY` (deprecated en deploy scripts)

---

## Function / endpoint signatures

### `similarity_matcher.load_reference_data_from_athena()` (NEW)

```python
def load_reference_data_from_athena(
    idolbuser: int,
    window_months: int = 6,
    force_reload: bool = False,
    timeout_seconds: int = 10,
) -> Tuple[Optional[pd.DataFrame], Optional[np.ndarray], Optional[np.ndarray], Optional[np.ndarray]]:
    """
    Load reference transaction data from Athena, filtered by idolbuser and
    sliding window [now() - window_months, now()].

    Window is computed AT CALL TIME, not at module load. Critical because the
    SageMaker container stays warm for days; computing at load would freeze
    the window.

    Returns (df, feature_vectors, labels, txn_ids) — same shape as
    load_reference_data_from_s3(). Returns (None, None, None, None) on any
    failure (graceful degradation, follows the L527-528 pattern).
    """
```

Patrón insertion: añadir DESPUÉS de `load_reference_data_from_s3()` (después de su return final, antes del `def _extract_feature_vector`).

### `similarity_matcher._normalize_athena_columns()` (NEW)

```python
def _normalize_athena_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize Athena column names (all lowercase from Glue) to the canonical
    camelCase names used by `DTYPE_MAP` in `endpoint/inference_rules.py`,
    `_load_from_local_csv`, and `predict_fn`.
    """
```

**Canonical column mapping (self-contained — do NOT reference other functions' mappings):**

| Athena (lowercase) | Canonical (camelCase) |
|--------------------|-----------------------|
| `transactionid`    | `TransactionID`       |
| `idolbuser`        | `idOLBUser`           |
| `createdat`        | `createdAt`           |
| `statuswarning`    | `statusWarning`       |
| `metadata`         | `metadata` (unchanged) |

<!-- Why TransactionID (uppercase D): matches DTYPE_MAP and predict_fn convention. Do not change without updating those callers. -->

### `similarity_matcher._compute_sliding_window()` (NEW)

```python
def _compute_sliding_window(window_months: int = 6) -> Tuple[datetime, datetime]:
    """
    Compute (start, end) for the sliding window. End = now() UTC,
    start = end - relativedelta(months=window_months).

    Returns datetime objects in UTC. Formatting to Athena TIMESTAMP literal
    happens in load_reference_data_from_athena().
    """
```

### `inference_rules._validate_similarity_input()` (NEW)

```python
def _validate_similarity_input(input_data: pd.DataFrame) -> Tuple[bool, List[int]]:
    """
    Validate that idOLBUserTxns is present and non-null for each row.
    createdAtTxns presence is already enforced by validate_gate() for the
    K-means path; this only adds the idOLBUserTxns check needed for the
    Athena filter.

    Returns (all_valid, missing_rows). For rows in missing_rows, similarity
    will return sim_*=null but K-means/rules outputs are preserved.

    NOTE: Per D1 default, we do NOT raise. We mark rows as similarity-skip.
    """
```

Patrón insertion: añadir como helper privado en `inference_rules.py` justo antes del bloque `# ===== Similarity Matching (MANDATORY) =====` (línea L1049).

### `find_similar_transaction()` (MODIFIED — signature simplificada por D2)

```python
def find_similar_transaction(
    query_result: Dict[str, Any],
    threshold: float = DEFAULT_THRESHOLD,
    metric: str = "cosine",
    top_k: int = 1,
    force_reload: bool = False,
    # NEW REQUIRED PARAMS — Athena single-source (D2)
    idolbuser: Optional[int] = None,
    window_months: int = 6,
    timeout_seconds: int = 10,
    # DEPRECATED — mantener temporalmente para no romper callers externos, raise DeprecationWarning si se pasan
    s3_bucket: Optional[str] = None,
    s3_key: Optional[str] = None,
    s3_uri: Optional[str] = None,
    local_csv_path: Optional[str] = None,
) -> Dict[str, Any]:
```

**Comportamiento tras D2:**
- `idolbuser` es **required** (None → log warning + retornar dict con `sim_*=null`, NO raise)
- Llama SIEMPRE a `load_reference_data_from_athena()`. El path Parquet se elimina.
- Si `load_reference_data_from_athena()` retorna `(None, None, None, None)` → mismo path de degradación → sim_*=null (D4 + R5)
- Los args `s3_*`/`local_csv_path` quedan como deprecated — si se pasan, log DeprecationWarning. NO cambian el comportamiento.

---

## Data contracts

### Input contract para similarity (NEW — tras D1)

| Campo | Tipo | Obligatorio | Default si falta | Origen |
|-------|------|-------------|------------------|--------|
| `idOLBUserTxns` | int64 | Para similarity | `sim_*=null`, K-means OK (D1 graceful) | Payload del request |
| `createdAtTxns` | string ISO | Para similarity | `sim_*=null`, K-means OK (D1 graceful) | Payload del request |

**Nota D1:** Ambos campos eran obligatorios en el refinement original. Tras el cierre de D1, **ninguno de los dos causa un 400**. Si cualquiera falta o es null → la row es marcada como `missing_rows` por `_validate_similarity_input()` y se le asigna `sim_*=null`. K-means + rules para esa row corren con normalidad.

### Output contract sim_* (UNCHANGED)

| Campo | Tipo | Valor cuando Athena falla |
|-------|------|---------------------------|
| `sim_match_txn_id` | str / None | None |
| `sim_score` | float / None | None |
| `sim_status` | "SAFE" / "RISKY" / None | None |
| `sim_decision` | "Accept" / "Reject" / None | None |

### Athena query (closed) — F1 mitigation: PyAthena parameterized queries

**Query template (con parameters, NO f-string):**

```sql
SELECT idolbuser, createdat, statuswarning, metadata, transactionid
FROM dlh_silver_safe_alpha.safetransactionresults
WHERE idolbuser = %(user)s
  AND createdat >= %(window_start)s
  AND createdat <= %(window_end)s
  AND statuswarning IN ('SAFE', 'RISKY')
```

**Execution pattern (F1 closed — gate applied 2026-06-17):**

```python
with pyathena.connect(
    s3_staging_dir=os.getenv("SIMILARITY_ATHENA_S3_STAGING", "s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/"),
    region_name=os.getenv("SIMILARITY_ATHENA_REGION", "us-east-2"),
) as conn:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT idolbuser, createdat, statuswarning, metadata, transactionid
        FROM dlh_silver_safe_alpha.safetransactionresults
        WHERE idolbuser = %(user)s
          AND createdat >= %(window_start)s
          AND createdat <= %(window_end)s
          AND statuswarning IN ('SAFE', 'RISKY')
        """,
        {
            "user": int(idolbuser),               # int cast as defense-in-depth
            "window_start": window_start_ts,      # datetime object
            "window_end": window_end_ts,          # datetime object
        },
    )
    rows = cursor.fetchall()
    df = pd.DataFrame(rows, columns=[d[0] for d in cursor.description])
```

**Key changes from previous A10 (REVOKED 2026-06-17):**

- **NO f-string SQL.** Structural escape via PyAthena DB-API named parameters (`%(name)s` style).
- `int(idolbuser)` cast is now **defense-in-depth** (no longer the primary protection — PyAthena's parameter binding is the primary control).
- **F11 also closed:** explicit column list (`idolbuser, createdat, statuswarning, metadata, transactionid`) — NO `SELECT *`. Eliminates risk of fetching undocumented PII columns.
- Connection: `pyathena.connect(s3_staging_dir='s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/', region_name='us-east-2')` (unchanged)

**Test contract (enforced in T_SIMILARITY):**
- `test_no_fstring_sql_in_module`: greps `endpoint/similarity_matcher.py` for f-string SQL patterns (`f"SELECT`, `f"FROM`, `f"WHERE`, `.format(` against SQL keywords). If any match found → fail.
- `test_cursor_execute_uses_dict_params`: verifies that `cursor.execute()` is called with a dict (not a tuple, not just SQL string).

### Env vars (revisado tras D2 — NO toggle USE_ATHENA)

| Var | Default | Efecto |
|-----|---------|--------|
| `SIMILARITY_ATHENA_DATABASE` | `dlh_silver_safe_alpha` | DB Glue (alpha) |
| `SIMILARITY_ATHENA_TABLE` | `safetransactionresults` | Tabla Glue (alpha) |
| `SIMILARITY_ATHENA_S3_STAGING` | `s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/` | Staging S3 (cross-account a alpha) |
| `SIMILARITY_ATHENA_REGION` | `us-east-2` | Region Athena (cross-region desde endpoint dev en us-east-1) |
| `ATHENA_WINDOW_MONTHS` | `6` | Override de la ventana sliding |
| `ATHENA_TIMEOUT_SECONDS` | `10` | Timeout query Athena (D4) |
| `SIMILARITY_THRESHOLD` | `0.90` | Sin cambio |
| `DISABLE_SIMILARITY` | `0` | Sin cambio |
| ~~`USE_ATHENA`~~ | — | **ELIMINADA por D2** — Athena es ahora la única fuente |
| ~~`SIMILARITY_S3_BUCKET`~~ | — | **DEPRECATED por D2** — ya no se usa en similarity |
| ~~`SIMILARITY_S3_KEY`~~ | — | **DEPRECATED por D2** — ya no se usa en similarity |

---

## Tasks (TDD: test first, then implementation)

### T0 — Verificación de prerequisitos (15 min)

**Implementer debe verificar antes de codear:**

1. `pip install pyathena python-dateutil` localmente y verificar `import pyathena; from pyathena import connect; from dateutil.relativedelta import relativedelta` no falla.
2. Confirmar que la SageMaker SKLearn 1.2-1 image instala automáticamente `/opt/ml/code/requirements.txt` cuando `source_dir='endpoint/'`. Doc: https://docs.aws.amazon.com/sagemaker/latest/dg/inference-best-practices-byom-frameworks.html#sklearn (consultar Context7 si es necesario).
3. **F1 gate (applied 2026-06-17): USAR PyAthena parameterized queries.** Verificar que `cursor.execute(sql, {"user": int(idolbuser), "window_start": start_ts, "window_end": end_ts})` con placeholders `%(user)s` / `%(window_start)s` / `%(window_end)s` funciona desde la sesión local (replicar el patrón del notebook pero **NO** copiar la f-string del notebook — el notebook está superseded por F1 gate). Si PyAthena rechaza el formato → escalar al planner, NO improvisar.
4. `unverified — método name confirm`: Confirmar que `pyathena.connect()` retorna un objeto compatible con `pandas.read_sql()` (sí en notebook, replicar local). Para el path productivo se usa `cursor.execute()` directamente con dict de params (no `pandas.read_sql` con f-string) — alineado con F1.
5. **Cross-account IAM check (informativo, NO bloqueante para merge tras F5 gate applied 2026-06-17):** Verificar con `aws sts get-caller-identity` (o equivalente) que el rol SageMaker del endpoint en development está documentado y tiene una trust policy con `blossom-analytics-datalake-alpha`. Si NO está documentado → escalar a plataforma ANTES de codear. La validación final se hace POST-DEPLOY observando `similarity.athena_failure` durante 24h.

**Si T0 falla:** detener y reportar al dev. NO inventar fixes.

---

### T1 — Input contract validation (`_validate_similarity_input`)

**Test contracts (escribir PRIMERO):**

```python
# test/test_athena_similarity_input_contract.py
import pandas as pd
import pytest
from endpoint.inference_rules import _validate_similarity_input

def test_validate_all_present_returns_ok():
    df = pd.DataFrame({"idOLBUserTxns": [604150, 604151], "createdAtTxns": ["2026-06-15T20:03:08", "2026-06-15T20:03:09"]})
    ok, missing = _validate_similarity_input(df)
    assert ok is True
    assert missing == []

def test_validate_missing_idolbuser_marks_row():
    df = pd.DataFrame({"idOLBUserTxns": [604150, None], "createdAtTxns": ["2026-06-15T20:03:08", "2026-06-15T20:03:09"]})
    ok, missing = _validate_similarity_input(df)
    assert ok is False
    assert missing == [1]  # row index 1

def test_validate_missing_idolbuser_column_marks_all():
    df = pd.DataFrame({"createdAtTxns": ["2026-06-15T20:03:08"]})
    ok, missing = _validate_similarity_input(df)
    assert ok is False
    assert missing == [0]

def test_validate_idolbuser_non_int_marks_row():
    df = pd.DataFrame({"idOLBUserTxns": [604150, "not_an_int"], "createdAtTxns": ["2026-06-15T20:03:08", "2026-06-15T20:03:09"]})
    ok, missing = _validate_similarity_input(df)
    assert ok is False
    assert 1 in missing

def test_validate_does_not_raise_when_all_missing():
    # D1 closed: graceful degradation, never raise
    df = pd.DataFrame({"foo": [1]})
    ok, missing = _validate_similarity_input(df)
    assert ok is False
    # No exception

def test_validate_missing_createdat_marks_row_d1_graceful():
    """D1 CLOSED: createdAtTxns missing → sim_*=null, NOT 400."""
    df = pd.DataFrame({"idOLBUserTxns": [604150, 604151], "createdAtTxns": [None, "2026-06-15T20:03:09"]})
    ok, missing = _validate_similarity_input(df)
    assert ok is False
    assert 0 in missing  # row 0 marked
    # Crucially: no exception raised

def test_validate_both_missing_marks_row_d1_graceful():
    """D1 CLOSED: both idOLBUserTxns AND createdAtTxns null → sim_*=null per row."""
    df = pd.DataFrame({"idOLBUserTxns": [None], "createdAtTxns": [None]})
    ok, missing = _validate_similarity_input(df)
    assert ok is False
    assert missing == [0]
    # Once again: no exception, K-means path will still run for that row
```

**Minimum implementation contract:**

- Helper privado en `inference_rules.py` justo antes de L1049 (bloque similarity).
- Iterar input_data rows, chequear que AMBOS campos cumplan:
  - `idOLBUserTxns` presente, non-null, castable a int
  - `createdAtTxns` presente, non-null (parseable a datetime se valida downstream en Athena)
- NO levantar excepción (D1 CLOSED — graceful para AMBOS campos).
- Logging `[SIMILARITY][VALIDATION] Row {idx}: missing {field_name}, sim_*=null for this row`.
- Retornar `(ok: bool, missing_rows: List[int])` donde `missing_rows` contiene los índices de rows con cualquiera de los dos campos faltantes.

**Inserción patrón:**
```python
# Insert AFTER the line matching: out_df[["audit_category","audit_explanation","ux_copy"]] = out_df.apply(
# Insert BEFORE the line matching: # ===== Similarity Matching (MANDATORY) =====
```

---

### T_SIMILARITY (was T2) — `load_reference_data_from_athena()` (core function) — **F1 parameterized + F11 explicit columns**

**Test contracts (escribir PRIMERO):**

```python
# test/test_athena_similarity_window.py
import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from endpoint.similarity_matcher import (
    load_reference_data_from_athena,
    _compute_sliding_window,
    _normalize_athena_columns,
)

def test_compute_window_uses_now_at_call():
    start1, end1 = _compute_sliding_window(window_months=6)
    # end is approximately now()
    assert (datetime.now(timezone.utc) - end1).total_seconds() < 5
    # start is exactly 6 months earlier
    from dateutil.relativedelta import relativedelta
    assert start1 == end1 - relativedelta(months=6)

def test_compute_window_changes_between_calls():
    """R1: window must be computed at each call, not memoized at module load."""
    start1, end1 = _compute_sliding_window()
    import time; time.sleep(1.1)
    start2, end2 = _compute_sliding_window()
    assert end2 > end1

def test_normalize_athena_columns_maps_lowercase_to_camelcase():
    df = pd.DataFrame({
        "idolbuser": [604150],
        "transactionid": [1],
        "createdat": ["2026-06-15"],
        "statuswarning": ["SAFE"],
        "metadata": ['{"decisionResult": {"num__amount": 1.0}}'],
    })
    out = _normalize_athena_columns(df)
    # Canonical mapping (matches DTYPE_MAP / predict_fn convention)
    assert "TransactionID" in out.columns  # uppercase D — canonical
    assert "idOLBUser" in out.columns
    assert "createdAt" in out.columns
    assert "statusWarning" in out.columns
    assert "metadata" in out.columns

@patch("endpoint.similarity_matcher.connect")
def test_load_from_athena_calls_connect_with_alpha_staging(mock_connect):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.description = [("idolbuser",), ("createdat",), ("statuswarning",), ("metadata",), ("transactionid",)]
    mock_cursor.fetchall.return_value = [
        (604150, pd.Timestamp("2026-06-15", tz="UTC"), "SAFE", '{"decisionResult": {"num__amount": 1.0, "cat__TransactionProcessingType_Intime": 1.0}}', "t1"),
    ]
    mock_conn.cursor.return_value = mock_cursor
    mock_connect.return_value = mock_conn
    load_reference_data_from_athena(idolbuser=604150)
    mock_connect.assert_called_once()
    call_kwargs = mock_connect.call_args.kwargs
    assert call_kwargs["s3_staging_dir"] == "s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/"
    assert call_kwargs["region_name"] == "us-east-2"

@patch("endpoint.similarity_matcher.connect")
def test_load_from_athena_uses_parameterized_query_F1(mock_connect):
    """F1 gate decision: PyAthena parameterized queries, NOT f-string."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.description = [("idolbuser",), ("createdat",), ("statuswarning",), ("metadata",), ("transactionid",)]
    mock_cursor.fetchall.return_value = []
    mock_conn.cursor.return_value = mock_cursor
    mock_connect.return_value = mock_conn

    load_reference_data_from_athena(idolbuser=604150)

    # Verify cursor.execute was called with SQL + dict of params (not just SQL string)
    assert mock_cursor.execute.called
    call_args = mock_cursor.execute.call_args
    sql = call_args[0][0]
    params = call_args[0][1]

    # Must use named param placeholders, not f-string interpolated values
    assert "%(user)s" in sql, "F1: SQL must use %(user)s param, not interpolated idolbuser"
    assert "%(window_start)s" in sql
    assert "%(window_end)s" in sql
    assert "604150" not in sql, "F1: idolbuser value MUST NOT appear in SQL string (parameterized)"

    # Params dict must contain int-cast user + datetime windows
    assert isinstance(params, dict)
    assert params["user"] == 604150
    assert isinstance(params["user"], int), "Defense-in-depth: int cast still applied"

@patch("endpoint.similarity_matcher.connect")
def test_load_from_athena_uses_explicit_column_list_F11(mock_connect):
    """F11 gate decision: explicit column list, NO SELECT *."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.description = [("idolbuser",), ("createdat",), ("statuswarning",), ("metadata",), ("transactionid",)]
    mock_cursor.fetchall.return_value = []
    mock_conn.cursor.return_value = mock_cursor
    mock_connect.return_value = mock_conn

    load_reference_data_from_athena(idolbuser=604150)

    sql = mock_cursor.execute.call_args[0][0]
    assert "SELECT *" not in sql.upper(), "F11: SELECT * forbidden"
    # Required explicit columns
    for col in ("idolbuser", "createdat", "statuswarning", "metadata", "transactionid"):
        assert col in sql.lower(), f"F11: explicit column {col} required in SELECT"

@patch("endpoint.similarity_matcher.connect")
def test_load_from_athena_returns_none_on_connection_error(mock_connect):
    mock_connect.side_effect = ConnectionError("VPC unreachable")
    result = load_reference_data_from_athena(idolbuser=604150)
    assert result == (None, None, None, None)

def test_load_from_athena_casts_idolbuser_to_int_defense_in_depth():
    """HLTC-9 + F1 defense-in-depth: int cast still applied even with parameterized queries."""
    with pytest.raises((ValueError, TypeError)):
        load_reference_data_from_athena(idolbuser="1; DROP TABLE x")

@patch("endpoint.similarity_matcher.connect")
def test_load_from_athena_empty_result_returns_none_tuple(mock_connect):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.description = [("idolbuser",), ("createdat",), ("statuswarning",), ("metadata",), ("transactionid",)]
    mock_cursor.fetchall.return_value = []
    mock_conn.cursor.return_value = mock_cursor
    mock_connect.return_value = mock_conn
    result = load_reference_data_from_athena(idolbuser=604150)
    # Empty result → no reference data → graceful degradation
    assert result[1] is None  # feature_vectors None
```

**F1 grep test (separate file `test/test_athena_similarity_sql_parametrized.py`):**

```python
# test/test_athena_similarity_sql_parametrized.py
"""F1 mitigation — structural enforcement that NO f-string SQL exists in similarity_matcher.py."""
import pathlib
import re


def test_no_fstring_sql_in_module():
    """F1 gate decision (applied 2026-06-17): the source file must NOT contain f-string SQL.
    If a future refactor reintroduces f-string SQL, this test fails immediately."""
    src = pathlib.Path("endpoint/similarity_matcher.py").read_text()

    # Patterns that indicate f-string SQL:
    forbidden_patterns = [
        r'f"[^"]*\b(SELECT|FROM|WHERE|INSERT|UPDATE|DELETE)\b',  # f"...SELECT..."
        r"f'[^']*\b(SELECT|FROM|WHERE|INSERT|UPDATE|DELETE)\b",  # f'...SELECT...'
        r'\.format\([^)]*\)\s*$.*\b(SELECT|FROM|WHERE)\b',         # .format() with SQL keywords nearby
    ]
    # Note: this is intentionally over-cautious; the implementer should add
    # `# noqa: F1-no-fstring-sql` comments only with reviewer approval.

    offenders = []
    for line_no, line in enumerate(src.splitlines(), start=1):
        for pat in forbidden_patterns:
            if re.search(pat, line, flags=re.IGNORECASE):
                if "# noqa: F1-no-fstring-sql" in line:
                    continue  # explicit waiver
                offenders.append(f"L{line_no}: {line.strip()}")

    assert not offenders, (
        f"F1 violation — f-string SQL found in endpoint/similarity_matcher.py:\n"
        + "\n".join(offenders)
    )


def test_cursor_execute_uses_dict_params():
    """F1: every cursor.execute call in similarity_matcher must pass a dict as second arg."""
    src = pathlib.Path("endpoint/similarity_matcher.py").read_text()
    # Find all cursor.execute(...) call sites
    matches = re.findall(r"cursor\.execute\s*\([^)]+\)", src, flags=re.DOTALL)
    assert matches, "Expected at least one cursor.execute call in similarity_matcher.py"
    for m in matches:
        # Must contain a comma + dict-like content (either {...} literal or **kwargs)
        assert "," in m, f"cursor.execute call missing params dict: {m[:120]}"
```

**Minimum implementation contract (F1 + F11 closed):**

- `_compute_sliding_window(months)` retorna `(start, end)` UTC, `end=datetime.now(timezone.utc)`, `start=end - relativedelta(months=months)`.
- `_normalize_athena_columns(df)` aplica el mapping canónico documentado arriba (`transactionid` → `TransactionID`, `idolbuser` → `idOLBUser`, `createdat` → `createdAt`, `statuswarning` → `statusWarning`, `metadata` unchanged). Estos nombres canónicos vienen de `DTYPE_MAP` en `endpoint/inference_rules.py` (L87+) y son los que consume `predict_fn`. NO mirror ciegamente otras funciones — usa esta tabla como fuente de verdad.
- `load_reference_data_from_athena(idolbuser, window_months=6, force_reload=False, timeout_seconds=10)`:
  1. `idolbuser_int = int(idolbuser)` (raise si no castable — defense-in-depth; PyAthena escape es la protección estructural)
  2. Compute window con `_compute_sliding_window(window_months)`
  3. Cache key = `f"athena:{idolbuser_int}:{end.strftime('%Y-%m-%d-%H-%M')}"` (truncado a minuto)
  4. Si cache hit y no force_reload → retornar cached
  5. `conn = connect(s3_staging_dir=os.getenv("SIMILARITY_ATHENA_S3_STAGING", "s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/"), region_name=os.getenv("SIMILARITY_ATHENA_REGION", "us-east-2"))`
  6. **F1 + F11**: Build SQL with named param placeholders + explicit column list:
     ```python
     sql = """
         SELECT idolbuser, createdat, statuswarning, metadata, transactionid
         FROM dlh_silver_safe_alpha.safetransactionresults
         WHERE idolbuser = %(user)s
           AND createdat >= %(window_start)s
           AND createdat <= %(window_end)s
           AND statuswarning IN ('SAFE', 'RISKY')
     """
     cursor = conn.cursor()
     cursor.execute(sql, {"user": idolbuser_int, "window_start": start, "window_end": end})
     rows = cursor.fetchall()
     df = pd.DataFrame(rows, columns=[d[0] for d in cursor.description])
     ```
     **NO f-string. NO `SELECT *`.** Timeout via `concurrent.futures.ThreadPoolExecutor` (D4 default 10s) — wrap the `cursor.execute(...) + fetchall()` block.
  7. `df = _normalize_athena_columns(df)`
  8. **F5+ Logging:** Si `len(df) == 0` → `logger.info("similarity.no_history", extra={"idolbuser_hash": sha256(...), "window_months": window_months, "rows": 0})` + retornar `(None, None, None, None)` (NORMAL outcome, Scenario 3)
  9. Procesar metadata.decisionResult IDÉNTICO a load_reference_data_from_s3 L416-507 — extraer este loop a helper `_extract_vectors_from_df()` para reuso
  10. Cache + retornar
  11. **F5+ Logging:** Cualquier excepción (que no sea cast error pre-Athena) → `logger.warning("similarity.athena_failure", extra={"idolbuser_hash": ..., "exception_class": ..., "exception_message": ..., "category": classify_exception(exc)})` + retornar `(None, None, None, None)` (graceful degradation)
- Close de conexión: try/finally con `conn.close()` (D3 default on-demand). Use context manager pattern (`with pyathena.connect(...) as conn:`).

**Refactor sugerido (no obligatorio):** Extraer el loop L416-507 de `load_reference_data_from_s3` a `_extract_vectors_from_df(df) -> Tuple[df, vectors, labels, ids]` y llamarlo desde ambas funciones. Reduce LoC duplicado en ~80 líneas.

---

### T3 — Integración en `predict_fn` (inference_rules.py) — simplificado tras D2

**Test contracts (escribir PRIMERO):**

```python
# test/test_athena_similarity_fallback.py
import os
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
# Note: predict_fn integration tests need real model artifacts; use existing test/test_inference_integration.py as harness


# Why autouse reset: `_similarity_mod` is module-cached; without reset, test order changes test outcomes.
@pytest.fixture(autouse=True)
def reset_similarity_module_state(monkeypatch):
    """Reset _similarity_mod and HAS_SIMILARITY between tests to avoid cache pollution.

    The module-level `_similarity_mod` is populated by `_ensure_similarity_loaded()`
    via `importlib.import_module()` on first call and then cached. Once
    `HAS_SIMILARITY = True` is set by an earlier test, subsequent patches on
    `_ensure_similarity_loaded` short-circuit and the cached `_similarity_mod`
    is used instead — leading to order-dependent test failures.

    By resetting both to None before every test, each test starts from a clean
    state and can patch `_similarity_mod` directly with its own mock.
    """
    import endpoint.inference_rules as ir
    monkeypatch.setattr(ir, "_similarity_mod", None, raising=False)
    monkeypatch.setattr(ir, "HAS_SIMILARITY", None, raising=False)
    yield


def _make_sim_mock(athena_return=(None, None, None, None), find_return=None):
    """Build a MagicMock that mimics the `endpoint.similarity_matcher` module surface
    used by `predict_fn`. Patch `_similarity_mod` directly with this — bypasses
    `_ensure_similarity_loaded` entirely so cached state cannot interfere."""
    mock_sim = MagicMock()
    mock_sim.load_reference_data_from_athena.return_value = athena_return
    mock_sim.find_similar_transaction.return_value = find_return or {
        "sim_match_txn_id": None,
        "sim_score": None,
        "sim_status": None,
        "sim_decision": None,
    }
    return mock_sim


def test_predict_fn_always_calls_athena(monkeypatch, model_artifacts, sample_input):
    """D2 CLOSED: similarity loop SIEMPRE llama al Athena loader (sin condicional)."""
    mock_sim = _make_sim_mock(athena_return=(None, None, None, None))
    monkeypatch.setattr("endpoint.inference_rules._similarity_mod", mock_sim)
    monkeypatch.setattr("endpoint.inference_rules.HAS_SIMILARITY", True)

    from endpoint.inference_rules import predict_fn
    out = predict_fn(sample_input, model_artifacts)

    assert mock_sim.load_reference_data_from_athena.called or mock_sim.find_similar_transaction.called
    # K-means columns intact (R5)
    assert "kmeans_risk_score" in out.columns
    assert out["kmeans_risk_score"].notna().all()
    # sim_* null because no Athena data
    assert out["sim_score"].isna().all()


def test_predict_fn_never_calls_parquet_loader_d2(monkeypatch, model_artifacts, sample_input):
    """D2 CLOSED: load_reference_data_from_s3 NEVER se llama en el path de similarity."""
    mock_sim = _make_sim_mock(athena_return=(None, None, None, None))
    # Add the parquet-loader attr to the mock so we can assert it is never called
    mock_sim.load_reference_data_from_s3 = MagicMock()
    monkeypatch.setattr("endpoint.inference_rules._similarity_mod", mock_sim)
    monkeypatch.setattr("endpoint.inference_rules.HAS_SIMILARITY", True)

    from endpoint.inference_rules import predict_fn
    predict_fn(sample_input, model_artifacts)

    assert not mock_sim.load_reference_data_from_s3.called, "D2: Parquet path eliminado de similarity"


def test_predict_fn_kmeans_intact_when_idolbuser_missing(monkeypatch, model_artifacts, sample_input_no_idolbuser):
    """D1 CLOSED: K-means runs normally, sim_* are null when idOLBUserTxns missing."""
    mock_sim = _make_sim_mock()
    monkeypatch.setattr("endpoint.inference_rules._similarity_mod", mock_sim)
    monkeypatch.setattr("endpoint.inference_rules.HAS_SIMILARITY", True)

    from endpoint.inference_rules import predict_fn
    out = predict_fn(sample_input_no_idolbuser, model_artifacts)
    # K-means OK
    assert out["kmeans_risk_decision"].notna().all()
    # Similarity skipped → null
    assert out["sim_score"].isna().all()
    assert out["sim_decision"].isna().all()


def test_predict_fn_kmeans_intact_when_createdat_missing(monkeypatch, model_artifacts, sample_input_no_createdat):
    """D1 CLOSED: createdAtTxns missing → sim_*=null, NO 400, K-means OK."""
    mock_sim = _make_sim_mock()
    monkeypatch.setattr("endpoint.inference_rules._similarity_mod", mock_sim)
    monkeypatch.setattr("endpoint.inference_rules.HAS_SIMILARITY", True)

    from endpoint.inference_rules import predict_fn
    out = predict_fn(sample_input_no_createdat, model_artifacts)
    assert out["kmeans_risk_score"].notna().all()
    assert out["sim_score"].isna().all()


def test_predict_fn_kmeans_intact_on_athena_exception(monkeypatch, model_artifacts, sample_input):
    """R5 + D4: K-means columns are not corrupted by Athena failures."""
    mock_sim = MagicMock()
    mock_sim.load_reference_data_from_athena.side_effect = Exception("Athena timeout")
    mock_sim.find_similar_transaction.side_effect = Exception("Athena timeout")
    monkeypatch.setattr("endpoint.inference_rules._similarity_mod", mock_sim)
    monkeypatch.setattr("endpoint.inference_rules.HAS_SIMILARITY", True)

    from endpoint.inference_rules import predict_fn
    out = predict_fn(sample_input, model_artifacts)
    assert out["kmeans_risk_score"].notna().all()
    assert out["sim_score"].isna().all()


def test_predict_fn_kmeans_intact_on_athena_timeout_d4(monkeypatch, model_artifacts, sample_input, caplog):
    """D4 CLOSED: timeout 10s → log warning, sim_*=null, K-means OK."""
    mock_sim = MagicMock()
    mock_sim.load_reference_data_from_athena.side_effect = TimeoutError("query exceeded 10s")
    mock_sim.find_similar_transaction.side_effect = TimeoutError("query exceeded 10s")
    monkeypatch.setattr("endpoint.inference_rules._similarity_mod", mock_sim)
    monkeypatch.setattr("endpoint.inference_rules.HAS_SIMILARITY", True)

    from endpoint.inference_rules import predict_fn
    out = predict_fn(sample_input, model_artifacts)
    assert out["kmeans_risk_score"].notna().all()
    assert out["sim_score"].isna().all()
    # Warning is logged
    assert any("[ATHENA]" in rec.message or "timeout" in rec.message.lower() for rec in caplog.records)


def test_predict_fn_succeeds_when_athena_returns_rows(monkeypatch, model_artifacts, sample_input):
    """Happy path: Athena returns rows → find_similar_transaction returns a match."""
    fixture_df = pd.DataFrame({
        "TransactionID": ["txn-A"],
        "idOLBUser": [604150],
        "createdAt": [pd.Timestamp("2026-06-15", tz="UTC")],
        "statusWarning": ["SAFE"],
        "metadata": ['{"decisionResult": {"num__amount": 1.0, "cat__TransactionProcessingType_Intime": 1.0}}'],
    })
    import numpy as np
    mock_sim = _make_sim_mock(
        athena_return=(fixture_df, np.array([[1.0, 1.0]]), np.array(["SAFE"]), np.array(["txn-A"])),
        find_return={
            "sim_match_txn_id": "txn-A",
            "sim_score": 0.97,
            "sim_status": "SAFE",
            "sim_decision": "Accept",
        },
    )
    monkeypatch.setattr("endpoint.inference_rules._similarity_mod", mock_sim)
    monkeypatch.setattr("endpoint.inference_rules.HAS_SIMILARITY", True)

    from endpoint.inference_rules import predict_fn
    out = predict_fn(sample_input, model_artifacts)
    # K-means intact AND sim_* populated
    assert out["kmeans_risk_score"].notna().all()
    assert (out["sim_score"] == 0.97).all()
    assert (out["sim_match_txn_id"] == "txn-A").all()
```

**Why the patch strategy changed (anti-cache-pollution):**
- `_similarity_mod` is set via `importlib.import_module()` at first call and cached at module level.
- Once `HAS_SIMILARITY = True` is set by a prior test, patching `_ensure_similarity_loaded` does nothing (it short-circuits because the module is already loaded).
- The patches above target `endpoint.inference_rules._similarity_mod` DIRECTLY with a `MagicMock`, bypassing `_ensure_similarity_loaded` entirely.
- The `autouse` fixture resets `_similarity_mod` and `HAS_SIMILARITY` to `None` between tests, so each test starts clean and test order is irrelevant.

**Minimum implementation contract (simplificado por D2):**

1. Al inicio del bloque similarity (insertar **después de** la línea `out_df[["audit_category","audit_explanation","ux_copy"]] = out_df.apply(...)` y **antes de** `# ===== Similarity Matching (MANDATORY) =====`):
   ```python
   # Validate similarity input contract (D1: graceful — never raises)
   sim_input_ok, sim_skip_rows = _validate_similarity_input(input_data)
   ```

   **NO** leer `USE_ATHENA` env var — D2 elimina el toggle.

2. Dentro del for-loop de similarity (después de L1066 donde se construye `query_features`):
   ```python
   # Skip similarity for rows missing input contract (D1 graceful)
   if idx in sim_skip_rows:
       similarity_results.append({"sim_match_txn_id": None, "sim_score": None, "sim_status": None, "sim_decision": None})
       continue
   ```

3. En la llamada a `_similarity_mod.find_similar_transaction()` (L1073), reemplazar por la versión Athena (única ruta):
   ```python
   idolbuser_int = int(input_data.iloc[idx]["idOLBUserTxns"])
   result = _similarity_mod.find_similar_transaction(
       query_result=query_features,
       threshold=similarity_threshold,
       top_k=5,
       idolbuser=idolbuser_int,
       window_months=int(os.getenv("ATHENA_WINDOW_MONTHS", "6")),
       timeout_seconds=int(os.getenv("ATHENA_TIMEOUT_SECONDS", "10")),
   )
   ```

   Eliminar los kwargs `s3_bucket=`, `s3_key=` — D2 los hace innecesarios.

4. Wrap el `try` existente para garantizar que K-means no se corrompa:
   - K-means output (`out_df["kmeans_risk_score"]`, etc.) ya está computado antes del bloque (L985-988).
   - El except de L1108 ya neutraliza la excepción a sim_*=null. Confirmar que se mantiene.
   - **D4:** dentro del except, log warning estructurado: `[SIMILARITY][ATHENA][TIMEOUT] idolbuser={X} elapsed_ms={N}` si la excepción es TimeoutError.

---

### T4 — Requirements + Deploy script

**Test contracts:**

```python
# test/test_athena_similarity_input_contract.py (extender)
def test_endpoint_requirements_has_pyathena():
    import pathlib
    req = pathlib.Path("endpoint/requirements.txt").read_text()
    assert "pyathena" in req
    assert "python-dateutil" in req
```

**Minimum implementation contract (revisado por D2 — sin USE_ATHENA):**

- `endpoint/requirements.txt` — CREATE:
  ```
  pyathena>=3.0,<4
  python-dateutil>=2.8
  pyarrow>=12
  boto3
  ```
- `endpoint_test/requirements.txt` — CREATE (mismo contenido).
- `deploy/deploy_with_sdk.py` — MODIFY:
  - Añadir `source_dir="endpoint"` al `SKLearnModel(...)` constructor para que pip auto-instale requirements.txt.
  - Añadir env vars Athena al dict `env={...}` (insertar después de la línea matching `"SIMILARITY_THRESHOLD"` o similar):
    ```python
    "SIMILARITY_ATHENA_DATABASE": "dlh_silver_safe_alpha",
    "SIMILARITY_ATHENA_TABLE": "safetransactionresults",
    "SIMILARITY_ATHENA_S3_STAGING": "s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/",
    "SIMILARITY_ATHENA_REGION": "us-east-2",
    "ATHENA_WINDOW_MONTHS": "6",
    "ATHENA_TIMEOUT_SECONDS": "10",
    ```
  - **NO** añadir `USE_ATHENA` (D2 cerrada — Athena es la única ruta).
  - Marcar como deprecated (o eliminar) `SIMILARITY_S3_BUCKET` y `SIMILARITY_S3_KEY` si su único consumer era similarity. Verificar con `grep -rn SIMILARITY_S3_BUCKET endpoint/` antes de eliminar.

  Patrón de inserción para `source_dir` (después de `entry_point="inference_rules.py",`):
  ```python
  source_dir="endpoint",
  ```

- `deploy/deploy_notebook.py` — MODIFY: aplicar el mismo cambio (es wrapper).

---

### T_LOGGING (REPLACES T_AC5) — Structured logging two-path (F5+ gate decision)

**Why this replaces T_AC5:** Gate decision F5 (applied 2026-06-17) removed the separate `deploy/validate_athena_connection.py` script. The observability that the validation script would have provided pre-merge is now provided post-deploy via structured logging in production code. This task implements that logging.

**Key requirement:** `idOLBUser` MUST NEVER be logged in plaintext. Always use sha256-truncated hash (first 16 hex chars) for the audit dimension. This is PII compliance and closes part of F4 for these new log paths.

**Test contracts (escribir PRIMERO):**

```python
# test/test_athena_similarity_logging.py
import hashlib
import logging
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest


def _expected_hash(idolbuser: int) -> str:
    return hashlib.sha256(str(idolbuser).encode()).hexdigest()[:16]


@patch("endpoint.similarity_matcher.connect")
def test_athena_zero_rows_emits_no_history_log(mock_connect, caplog):
    """F5+ gate: when Athena returns 0 rows (Scenario 3 — normal), emit INFO `similarity.no_history`."""
    from endpoint.similarity_matcher import load_reference_data_from_athena
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.description = [("idolbuser",), ("createdat",), ("statuswarning",), ("metadata",), ("transactionid",)]
    mock_cursor.fetchall.return_value = []  # 0 rows
    mock_conn.cursor.return_value = mock_cursor
    mock_connect.return_value = mock_conn

    with caplog.at_level(logging.INFO, logger="endpoint.similarity_matcher"):
        result = load_reference_data_from_athena(idolbuser=604150)

    assert result == (None, None, None, None)

    # Find the no_history log record
    rec = next((r for r in caplog.records if "similarity.no_history" in r.message or r.message == "similarity.no_history"), None)
    assert rec is not None, "Expected similarity.no_history log entry"
    assert rec.levelno == logging.INFO
    # idolbuser must be HASHED, never plaintext
    assert "604150" not in rec.getMessage(), "PII: idolbuser must NEVER appear in plaintext"
    # The hash must be present in the extra fields
    assert getattr(rec, "idolbuser_hash", None) == _expected_hash(604150)
    assert getattr(rec, "rows", None) == 0


@patch("endpoint.similarity_matcher.connect")
def test_athena_permission_error_emits_failure_log_with_category(mock_connect, caplog):
    """F5+ gate: when Athena raises PermissionError, emit WARNING `similarity.athena_failure` with category='permission'."""
    from endpoint.similarity_matcher import load_reference_data_from_athena
    mock_connect.side_effect = PermissionError("AccessDeniedException: cross-account denied")

    with caplog.at_level(logging.WARNING, logger="endpoint.similarity_matcher"):
        result = load_reference_data_from_athena(idolbuser=604150)

    assert result == (None, None, None, None)
    rec = next((r for r in caplog.records if "similarity.athena_failure" in r.message or r.message == "similarity.athena_failure"), None)
    assert rec is not None, "Expected similarity.athena_failure log entry"
    assert rec.levelno in (logging.WARNING, logging.ERROR)
    assert "604150" not in rec.getMessage(), "PII: idolbuser must NEVER appear in plaintext"
    assert getattr(rec, "idolbuser_hash", None) == _expected_hash(604150)
    assert getattr(rec, "exception_class", None) == "PermissionError"
    assert getattr(rec, "category", None) == "permission"


@patch("endpoint.similarity_matcher.connect")
def test_athena_timeout_emits_failure_log_with_category_timeout(mock_connect, caplog):
    from endpoint.similarity_matcher import load_reference_data_from_athena
    mock_connect.side_effect = TimeoutError("query exceeded 10s")
    with caplog.at_level(logging.WARNING, logger="endpoint.similarity_matcher"):
        load_reference_data_from_athena(idolbuser=604150)
    rec = next((r for r in caplog.records if "similarity.athena_failure" in r.message), None)
    assert rec is not None
    assert getattr(rec, "category", None) == "timeout"


def test_classify_exception_maps_permission_error():
    from endpoint.similarity_matcher import classify_exception
    assert classify_exception(PermissionError("AccessDenied")) == "permission"


def test_classify_exception_maps_timeout_error():
    from endpoint.similarity_matcher import classify_exception
    assert classify_exception(TimeoutError("query timed out")) == "timeout"


def test_classify_exception_maps_throttling_string_match():
    """Throttling exceptions from boto3 contain 'Throttling' in the message."""
    from endpoint.similarity_matcher import classify_exception
    class FakeThrottle(Exception):
        pass
    exc = FakeThrottle("ThrottlingException: rate exceeded")
    assert classify_exception(exc) == "throttling"


def test_classify_exception_unknown_fallback():
    from endpoint.similarity_matcher import classify_exception
    assert classify_exception(RuntimeError("oh no")) == "unknown"


def test_exception_message_truncated_to_200_chars():
    """F5+ defense against log injection: exception_message truncated to 200 chars."""
    from endpoint.similarity_matcher import load_reference_data_from_athena
    long_msg = "X" * 5000
    with patch("endpoint.similarity_matcher.connect", side_effect=RuntimeError(long_msg)), \
         pytest.MonkeyPatch.context() as mp:
        # capture via logging handler instead of caplog for explicitness
        import logging
        records = []
        class Cap(logging.Handler):
            def emit(self, r): records.append(r)
        h = Cap()
        logger = logging.getLogger("endpoint.similarity_matcher")
        logger.addHandler(h)
        try:
            load_reference_data_from_athena(idolbuser=604150)
        finally:
            logger.removeHandler(h)
    failure_recs = [r for r in records if "similarity.athena_failure" in r.message]
    assert failure_recs, "Expected athena_failure log"
    assert len(getattr(failure_recs[0], "exception_message", "")) <= 200
```

**Minimum implementation contract:**

Add to `endpoint/similarity_matcher.py`:

1. **The `classify_exception()` helper** (4-5 lines, at module scope near the top of the file, after imports):

   ```python
   def classify_exception(exc: BaseException) -> str:
       """Map an exception to an observable category for structured logging.

       Categories:
         - "permission":  IAM denied (cross-account broken)
         - "throttling":  Athena/AWS throttled the request
         - "timeout":     query exceeded ATHENA_TIMEOUT_SECONDS
         - "query_error": SQL syntax or schema drift
         - "unknown":     anything else
       """
       msg = str(exc).lower()
       if isinstance(exc, PermissionError) or "accessdenied" in msg or "access denied" in msg:
           return "permission"
       if "throttl" in msg or "ratelimit" in msg or "rate exceeded" in msg:
           return "throttling"
       if isinstance(exc, TimeoutError) or "timeout" in msg or "timed out" in msg:
           return "timeout"
       if "syntaxerror" in msg or "table not found" in msg or "column" in msg:
           return "query_error"
       return "unknown"
   ```

2. **The hashing helper** (also module scope):

   ```python
   import hashlib

   def _hash_idolbuser(idolbuser) -> str:
       """sha256-truncated hash for use as observability dimension. NEVER log raw idolbuser."""
       return hashlib.sha256(str(idolbuser).encode()).hexdigest()[:16]
   ```

3. **Two distinct log paths inside `load_reference_data_from_athena()`:**

   a. **Zero-rows path** (after fetch, BEFORE returning `(None, None, None, None)`):
      ```python
      if len(df) == 0:
          logger.info("similarity.no_history", extra={
              "idolbuser_hash": _hash_idolbuser(idolbuser_int),
              "window_months": window_months,
              "rows": 0,
          })
          return (None, None, None, None)
      ```

   b. **Exception path** (in the outer `except Exception as exc:` of the function, BEFORE returning `(None, None, None, None)`):
      ```python
      except Exception as exc:
          logger.warning("similarity.athena_failure", extra={
              "idolbuser_hash": _hash_idolbuser(idolbuser_int) if 'idolbuser_int' in locals() else _hash_idolbuser(idolbuser),
              "exception_class": exc.__class__.__name__,
              "exception_message": str(exc)[:200],  # truncated to avoid log injection
              "category": classify_exception(exc),
          })
          return (None, None, None, None)
      ```

4. **Update D4 timeout log (existing) to use the same structured pattern.** The previous `[SIMILARITY][ATHENA][TIMEOUT] idolbuser={X}` format is REPLACED. Timeout logs go through the same `similarity.athena_failure` path with `category="timeout"`. This closes F4 for the timeout case.

5. **Required CloudWatch alarm (documented in T6 docs, not implemented in code):** alarm fires if `similarity.athena_failure` count > N per minute, with optional filter `category="permission"` to detect cross-account broken.

**Patrón insertion:**

- `classify_exception()` and `_hash_idolbuser()`: add at module scope after the existing imports and before any function definitions.
- The two log calls: inside `load_reference_data_from_athena()` at the zero-rows and exception sites described above.

---

### T6 — Docs

**Minimum implementation contract:**

- `docs/ATHENA_INTEGRATION.md` — CREATE con secciones:
  1. Overview (qué hace, por qué Athena es single-source tras D2)
  2. **Cross-account architecture** (endpoint en development, data lake en alpha; diagrama de flujo)
  3. Window decision (R3 — 6 meses arbitrario, producto)
  4. Env vars (tabla completa — SIMILARITY_ATHENA_*, sin USE_ATHENA)
  5. **Cross-account IAM permissions required** (policy JSON exacta — copy de HLTC-8 preview, incluyendo bucket policy alpha)
  6. Connection pattern (PyAthena `connect()` + `cursor.execute()` con dict de params — NO replicar el patrón f-string del notebook; ese patrón está superseded por F1 gate applied 2026-06-17)
  7. **Query format (F1):** SQL con `%(user)s`, `%(window_start)s`, `%(window_end)s` placeholders + dict de params en `cursor.execute(sql, params)`. NO f-string. Explicit column list (F11). Incluir ejemplo verbatim.
  8. Cache strategy (A14)
  9. Graceful degradation (D1+D4 — qué pasa si Athena falla)
  10. **F5+ Structured logging & alerting playbook (replaces validation script runbook):**
      - Dos paths de log: `similarity.no_history` (INFO, normal Scenario 3, NO alertar) vs `similarity.athena_failure` (WARNING, alertable, con `category=permission/throttling/timeout/query_error/unknown`).
      - CloudWatch alarm sugerida: `count(similarity.athena_failure) > N per minute` con filtro `category=permission` → cross-account IAM roto.
      - **idOLBUser SIEMPRE sha256-truncated, nunca plaintext.**
      - **Post-deploy alpha observation:** 24h monitoring window con `similarity.athena_failure` count esperado = 0 para promoción a higher envs. Esto reemplaza al runbook del antiguo `validate_athena_connection.py` (removed por F5 gate).
  11. **F2 platform pre-merge action:** la regla de S3 lifecycle 7d en `s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/` es propiedad del equipo de plataforma. Debe estar provisionada ANTES del merge — link al ticket de plataforma en el PR description.
  12. **F3 external owner:** el audit trail per-lookup es scope del equipo de audit/compliance de Blossom. NO es scope de DATA-1264. Su iniciativa cubrirá este endpoint cuando se entregue.
  13. **Operational risk** (HLTC-12 — single point of failure por D2; sugerencia de monitoring de `sim_score_null_rate` en ticket aparte)
  14. Troubleshooting (cold start, throttling, cross-region latencia, cross-account perms denegados — vincular cada caso a su `category` en `similarity.athena_failure`)

- `docs/ENDPOINT_FLOW_SEQUENCE.md` — MODIFY L100-101: actualizar paso 5 para reflejar que similarity usa Athena exclusivamente (D2). Eliminar referencias a Parquet en ese paso. Añadir nota sobre cross-account dev→alpha.

---

## Verification steps (V1-V8) — revisado tras D2 (Athena single-source) + gate decisions applied 2026-06-17

V1. **Tests unitarios pasan:** `pytest test/test_athena_similarity_*.py -v` con cobertura ≥ 85% en el código nuevo. Incluye los tests F1 (`test_athena_similarity_sql_parametrized.py`) y F5+ (`test_athena_similarity_logging.py`).

V2. **Tests existentes no rompen:** `pytest test/test_inference_integration.py test/test_e2e_with_s3.py test/test_graceful_degradation.py` siguen verdes. **Nota D2:** `test/test_parquet_similarity.py` quizá requiera ajuste o sea eliminado — el Parquet path ya no es ruta de similarity. El implementer revisa si el test cubre la función helper general o si era específico al path de similarity, y actúa según corresponda (mantener si cubre otros usos, eliminar si era exclusivo de similarity).

V3. **Linting:** sin nuevas violaciones en archivos modificados (`flake8` o el linter actual del repo).

V4. **Local smoke test con Athena mockeado:** correr `predict_fn` con un sample input con `idOLBUserTxns` presente y `pyathena.connect` monkeypatched a un MagicMock que devuelve un DataFrame con 2 rows. Confirmar que se invoca `load_reference_data_from_athena`, **`cursor.execute()` se llama con dict de params (NO con f-string SQL — F1)**, y sim_* poblados.

V5. **Local smoke test de graceful degradation (D1+D4):** correr `predict_fn` con:
   - (a) sample input SIN `idOLBUserTxns` → K-means OK, sim_*=null sin excepción.
   - (b) sample input SIN `createdAtTxns` → K-means OK, sim_*=null sin excepción.
   - (c) `pyathena.connect` mockeado para raise TimeoutError → K-means OK, sim_*=null, `similarity.athena_failure` log emitido con `category="timeout"` y `idolbuser_hash` (NO plaintext).

V6. **AC5 — Post-deploy en alpha (BLOQUEANTE para promoción a higher envs, NO para merge — F5 gate applied 2026-06-17):**
   - Desplegar el endpoint en cuenta **alpha** primero.
   - Monitorear CloudWatch durante **24h** después del deploy. Métrica observada: count de `similarity.athena_failure` con `category="permission"`.
   - **Expected:** count = 0 (o matchea baseline de timeouts bajo carga normal). Si > 0 con `category=permission` → cross-account IAM roto, rollback o escalar a plataforma/infra para configurar la cross-account assume-role policy entre el rol SageMaker de development y `blossom-analytics-datalake-alpha`. NO es un fix de código.
   - **Sin script aparte** (F5 gate). La validación de conexión la hace el propio `pyathena.connect()` dentro del production code en la primera invocación post-deploy. Si fallara, el log estructurado lo reporta inmediatamente.
   - **Evidencia PR:** snapshot del CloudWatch dashboard mostrando `similarity.athena_failure` count = 0 durante la ventana de 24h se adjunta como comment del PR ANTES de promover de alpha a higher envs. Para merge a `dev` branch NO se requiere esta evidencia — solo para promoción posterior.

V7. **Docs review:** `docs/ATHENA_INTEGRATION.md` contiene:
   - Policy IAM exacta cross-account (dev→alpha).
   - Env vars (sin USE_ATHENA).
   - **Sección F5+ alerting playbook:** cómo interpretar `similarity.no_history` (NORMAL, Scenario 3) vs `similarity.athena_failure` (ALERTABLE, con categorías permission/throttling/timeout/query_error/unknown).
   - **Sección F2 platform action:** documentación que la regla de S3 lifecycle 7d en `gold/athena-metadata/` debe estar provisionada por el equipo de plataforma ANTES del merge.
   - **Sección F3 external owner:** nota que el audit trail per-lookup es scope del equipo de audit/compliance, NO de este ticket.
   - Operational risk (HLTC-12).
   - `docs/ENDPOINT_FLOW_SEQUENCE.md` L100-101 actualizado para reflejar Athena single-source.

V8. **PR auto-checklist:** `plan.md`, `spec.md` y `threats.md` están en `changes/DATA-1264/`. Manifesto de archivos coincide con `git diff --stat`. No hay TODO sin cerrar. Pre-merge DoD checkboxes (F1 / F2 / F3 / F5+) todos marcados en el PR description con evidencia (link al ticket de plataforma para F2, link al equipo de audit para F3, link al test verde de grep F1, snippet del log F5+).

---

## Execution Report (implementer fills)

- [ ] T0 prereq check — pyathena instala, SDK SKLearn confirmed, parameterized query pattern confirmado (F1), cross-account IAM documentado
- [ ] T1 `_validate_similarity_input` — 7/7 tests verdes (incluye D1 graceful tests para idOLBUserTxns + createdAtTxns)
- [ ] T_SIMILARITY `load_reference_data_from_athena` — todos los tests verdes (incluye F1 parameterized query test + F11 explicit column list test + grep test `test_no_fstring_sql_in_module`)
- [ ] T3 `predict_fn` integration — 6/6 tests verdes (incluye D1 graceful test para createdAtTxns missing y D4 timeout)
- [ ] T4 requirements + deploy — script de deploy parsea OK, source_dir confirmado, SIN USE_ATHENA env var
- [ ] T_LOGGING structured logging — `classify_exception()` + `_hash_idolbuser()` + dos paths de log emitidos, 7/7 tests verdes (F5+ gate)
- [ ] T6 docs — ATHENA_INTEGRATION.md (con cross-account IAM + F5+ alerting playbook + F2 platform action + F3 external owner + operational risk) + ENDPOINT_FLOW_SEQUENCE.md updated
- [ ] V1-V8 — todas verdes

### Pre-merge DoD (gate decisions applied 2026-06-17)

- [ ] **F1** — grep test `test_no_fstring_sql_in_module` está VERDE. NO existe f-string SQL en `endpoint/similarity_matcher.py`. `cursor.execute()` se llama con dict de params.
- [ ] **F2** — confirmación del equipo de plataforma adjuntada al PR (link al ticket de plataforma o screenshot de la AWS console mostrando la regla de S3 lifecycle 7d activa sobre `s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/`).
- [ ] **F3** — PR description menciona explícitamente que el audit trail per-lookup es scope del equipo de audit/compliance y NO de DATA-1264. Si el owner del equipo de audit es conocido al momento del PR, registrarlo en el PR description.
- [ ] **F5+** — structured logs `similarity.no_history` y `similarity.athena_failure` emitiéndose en local smoke test (V5) con `idolbuser_hash` (NUNCA plaintext).

### Post-deploy en alpha (BLOQUEANTE para promoción a higher envs, NO para merge — F5 gate)

- [ ] **AC5** — 24h CloudWatch monitoring window en alpha: `count(similarity.athena_failure WHERE category=permission)` = 0. Snapshot del dashboard adjuntado como comment del PR ANTES de promover de alpha. Si `count > 0` → rollback o escalar a plataforma/infra (cross-account IAM).
