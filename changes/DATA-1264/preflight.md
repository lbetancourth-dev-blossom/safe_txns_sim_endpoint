# Preflight Review — DATA-1264

---

## Amendment 2026-06-17 — Re-run on CRITICAL-1 and CRITICAL-2 only

**Re-run date:** 2026-06-17
**Re-run scope:** Targeted re-check of the two previously-CRITICAL findings after the planner applied spec fixes approved by the dev. All other findings from the original run (5 refinement corrections, 6 gate decisions, 8 warnings) are unchanged and still stand.

### CRITICAL-1 — Column mapping contradiction

**Status: RESOLVED**

**Evidence:**

The original complaint was that the spec said "mirror L163-172 EXACTLY" in two places (docstring of `_normalize_athena_columns()` and the T_SIMILARITY implementation contract), which produced `transactionid -> transactionId` (lowercase d), contradicting the test assertion `assert "TransactionID" in out.columns` (uppercase D).

The amendment replaced both occurrences. In the current `changes/DATA-1264/spec.md`:

- Lines 107-113: The docstring of `_normalize_athena_columns()` now reads "Normalize Athena column names (all lowercase from Glue) to the canonical camelCase names used by `DTYPE_MAP` in `endpoint/inference_rules.py`, `_load_from_local_csv`, and `predict_fn`." No reference to L163-172 or "EXACTLY".

- Lines 115-125: An explicit self-contained canonical mapping table appears immediately after the docstring:

  | Athena (lowercase) | Canonical (camelCase) |
  |--------------------|-----------------------|
  | `transactionid`    | `TransactionID`       |
  | `idolbuser`        | `idOLBUser`           |
  | `createdat`        | `createdAt`           |
  | `statuswarning`    | `statusWarning`       |
  | `metadata`         | `metadata` (unchanged)|

  An HTML comment on line 125 reinforces the intent: `<!-- Why TransactionID (uppercase D): matches DTYPE_MAP and predict_fn convention. Do not change without updating those callers. -->`

- Line 555 (T_SIMILARITY minimum implementation contract): "NO mirror ciegamente otras funciones — usa esta tabla como fuente de verdad." The old "idéntico a _load_parquet_directory_from_s3 L163-172" text is gone; it is replaced by the verbatim mapping from the table.

- Line 411 (test assertion in `test_normalize_athena_columns_maps_lowercase_to_camelcase`): `assert "TransactionID" in out.columns` — still the assertion, now consistent with the canonical table.

The spec is internally consistent. The mapping table, the docstring, the implementation contract, and the test all agree on `TransactionID` (uppercase D). No reference to L163-172 or "EXACTLY" remains anywhere in the spec.

**No new issues introduced by this fix.**

---

### CRITICAL-2 — T3 mock wiring unreliable due to module cache

**Status: RESOLVED**

**Evidence:**

The original complaint was that T3 tests patched `_ensure_similarity_loaded` and `endpoint.similarity_matcher.load_reference_data_from_athena` at the module level, but `_similarity_mod` is set via `importlib.import_module()` and cached at module level, making patches order-dependent.

The amendment rewrote the entire T3 test block. In the current `changes/DATA-1264/spec.md`:

- Lines 603-619: An `autouse` pytest fixture `reset_similarity_module_state` is defined at the top of `test/test_athena_similarity_fallback.py`. It uses `monkeypatch.setattr(ir, "_similarity_mod", None, raising=False)` and `monkeypatch.setattr(ir, "HAS_SIMILARITY", None, raising=False)` before every test. Because `monkeypatch` is a pytest built-in that automatically reverts all setattr calls at test teardown, no explicit teardown code is needed and there is no path where the state leaks between tests.

- Lines 622-634: A helper `_make_sim_mock()` builds a `MagicMock` representing the `endpoint.similarity_matcher` module surface (with `load_reference_data_from_athena` and `find_similar_transaction` controlled return values).

- Lines 637-752: All six test functions now use `monkeypatch.setattr("endpoint.inference_rules._similarity_mod", mock_sim)` and `monkeypatch.setattr("endpoint.inference_rules.HAS_SIMILARITY", True)` to inject state directly. None of the six tests use `@patch("endpoint.inference_rules._ensure_similarity_loaded")` or `@patch("endpoint.similarity_matcher.load_reference_data_from_athena")`. The `_ensure_similarity_loaded` code path is bypassed entirely for every test.

- Lines 755-759: A "Why the patch strategy changed" explanation block is present confirming the fix rationale and documenting the cache-pollution risk for future contributors.

The fix is complete, sound, and covers the full scope of the original finding. There is no residual path where `_similarity_mod` from a prior test bleeds into a later one. Test order is irrelevant.

**No new issues introduced by this fix.**

---

### Final verdict (Amendment run): PASS

Both previously-CRITICAL findings are RESOLVED. No new critical or warning findings were introduced by the amendments. The 8 warnings from the original run stand unchanged (none were introduced or exacerbated by the fixes). The spec is clear to proceed to `/blossom-workflow:execute`.

---

---

## Original Preflight Run — 2026-06-17

**Verdict:** PASS WITH WARNINGS (superseded by Amendment above — final verdict is PASS)
**Date:** 2026-06-17
**Reviewer:** blossom-reviewer (preflight mode)

---

## Summary

El spec es ejecutable. La arquitectura, los contratos de datos, las firmas de funciones y los contratos de tests estan bien definidos. Sin embargo, se identificaron **dos problemas criticos que causaran un halt del implementer** si no se resuelven antes de `/execute`: (1) el spec define `_normalize_athena_columns()` como un mirror de `_load_parquet_directory_from_s3` L163-172, pero esa funcion mapea `transactionid -> transactionId` (camelCase con 'd' minuscula), mientras que el test `test_normalize_athena_columns_maps_lowercase_to_camelcase` exige `TransactionID` (Pascal case con 'D' mayuscula) — la columna que el resto del codigo usa. El implementer que siga la instruccion "Idéntico a L163-172 EXACTLY" producira un mismatch con el test. (2) el mock del test T3 parchea `endpoint.inference_rules._ensure_similarity_loaded` pero la firma del test importa `predict_fn` despues del patch, lo que probablemente no intercepte el lazy-loader ya evaluado. Hay ademas ocho warnings que no bloquean ejecucion pero generaran confusion o bugs silenciosos.

---

## Findings

### CRITICAL (bloquea /execute)

**CRITICAL-1 — Contradiccion en `_normalize_athena_columns()`: "mirror L163-172 EXACTLY" vs. test que exige `TransactionID`**

El spec dice en dos lugares que `_normalize_athena_columns()` debe replicar "EXACTAMENTE" el mapeo de `_load_parquet_directory_from_s3` L163-172:

- T_SIMILARITY implementation contract: "_normalize_athena_columns(df) aplica mapping idéntico a _load_parquet_directory_from_s3 L163-172."
- Docstring de `_normalize_athena_columns()`: "Mirrors the mapping in _load_parquet_directory_from_s3() L163-172 EXACTLY."

El mapeo real en `similarity_matcher.py` L163-172 (fuente verificada) es:

```python
column_mapping = {
    'uuid': 'uuid',
    'transactionid': 'transactionId',   # <-- minuscula 'd'
    'idfi': 'idFi',
    'statuswarning': 'statusWarning',
    'metadata': 'metadata',
    'createdat': 'createdAt',
    'updatedat': 'updatedAt'
}
```

Sin embargo, el test en `test/test_athena_similarity_window.py` exige:

```python
assert "TransactionID" in out.columns   # <-- 'D' mayuscula (Pascal case)
assert "createdAt" in out.columns
assert "statusWarning" in out.columns
```

`TransactionID` (mayuscula) es la convencion correcta usada en todo el resto del codigo (`inference_rules.py` L87 en `DTYPE_MAP`, L498 en `_load_from_local_csv`, L1172 en `predict_fn`). El mapeo de L163-172 tiene un error historico (`transactionId` con 'd' minuscula). Si el implementer sigue "EXACTLY" la instruccion del spec, `_normalize_athena_columns()` producira `transactionId`, el test fallara en `assert "TransactionID" in out.columns`, y el implementer quedara atrapado en un loop sin saber que corregir.

**Resolucion requerida antes de /execute:** En el spec, reemplazar "Mirrors the mapping in _load_parquet_directory_from_s3() L163-172 EXACTLY" por el mapeo correcto explicito:

```python
column_mapping = {
    'transactionid': 'TransactionID',   # Pascal case — matches DTYPE_MAP and predict_fn
    'idolbuser': 'idOLBUser',           # Athena lowercase -> camelCase
    'statuswarning': 'statusWarning',
    'metadata': 'metadata',
    'createdat': 'createdAt',
}
```

El docstring debe decir "Mirrors the _intent_ of L163-172 but corrects 'transactionId' -> 'TransactionID' to match DTYPE_MAP."

---

**CRITICAL-2 — El mock en T3 `test_predict_fn_always_calls_athena` parchea `_ensure_similarity_loaded` pero el import de `predict_fn` ocurre DESPUES del patch, lo que puede no interceptar el lazy-loader**

El test es:

```python
@patch("endpoint.inference_rules._ensure_similarity_loaded", return_value=True)
@patch("endpoint.similarity_matcher.load_reference_data_from_athena")
def test_predict_fn_always_calls_athena(mock_athena, mock_load, model_artifacts, sample_input):
    mock_athena.return_value = (None, None, None, None)
    from endpoint.inference_rules import predict_fn
    out = predict_fn(sample_input, model_artifacts)
    assert mock_athena.called
```

El problema: `_ensure_similarity_loaded()` en `inference_rules.py` (L53-72) usa un patron lazy con variable global `HAS_SIMILARITY`. Si el modulo ya fue importado en una sesion de test anterior (o en el mismo proceso de pytest), `HAS_SIMILARITY` ya esta en `True` y `_similarity_mod` ya esta seteado. El `@patch` de `_ensure_similarity_loaded` retornara `True`, pero `_similarity_mod` (la referencia real al modulo) puede NO ser `endpoint.similarity_matcher` — puede ser el modulo real ya importado via `importlib`. Esto significa que `mock_athena` (que parchea `endpoint.similarity_matcher.load_reference_data_from_athena`) puede no interceptar el llamado real si `_similarity_mod` es una referencia directa al modulo cargado.

Ademas, el orden de los argumentos del decorador es incorrecto. `@patch` aplica los decoradores de abajo hacia arriba, por lo que el primer argumento del test (`mock_athena`) corresponde al ultimo `@patch` en la lista (que es `endpoint.similarity_matcher.load_reference_data_from_athena`), y `mock_load` corresponde a `_ensure_similarity_loaded`. La asignacion de nombres en el test esta invertida respecto a lo que el implementer esperaria leer: `mock_load` recibe el patch de `_ensure_similarity_loaded` (que deberia llamarse `mock_ensure`) y `mock_athena` recibe el patch del loader. Esto no bloquea la ejecucion del test pero confunde al implementer y puede producir asserts sobre el mock equivocado.

La confusion mas profunda: el test aserta `assert mock_athena.called` — pero `mock_athena` en realidad es el patch de `load_reference_data_from_athena`. Si el wiring de `predict_fn` esta bien (llama a `_similarity_mod.load_reference_data_from_athena`), el test PUEDE pasar si el patch de modulo intercepta la referencia. Pero si `_similarity_mod` fue cacheado via `importlib.import_module` antes del patch, el mock no intercepta nada y el test falla silenciosamente (retorna un mock pero el codigo real no fue parcheado).

**Resolucion requerida antes de /execute:** Reescribir el test usando `patch.object` o asegurarse de que el patch se aplica sobre la referencia exacta que `predict_fn` usa internamente. La forma robusta es parchear `endpoint.inference_rules._similarity_mod` directamente para inyectar un MagicMock con `load_reference_data_from_athena` controlado. Incluir `autouse` fixture que resetea `HAS_SIMILARITY = None` entre tests.

---

### WARNINGS (no bloquean, pero el dev debe estar informado)

**WARNING-1 — `logger` se usa antes de ser definido en `similarity_matcher.py` (L38)**

En el archivo actual, L33-38 intentan importar `pyarrow` y en el bloque `except` ejecutan `logger.warning(...)`. Pero `logger` se define en L41. Si `pyarrow` no esta instalado, el `except` lanza `NameError: name 'logger' is not defined`. El spec dice "Create endpoint/requirements.txt con pyarrow>=12" pero si el entorno local no tiene pyarrow instalado durante el desarrollo, el modulo explota al importarlo. El implementer que siga el spec y intente ejecutar los tests sin instalar requirements primero vera un error de import no relacionado con su codigo nuevo. El spec deberia advertir esto en T0 o mover la definicion de `logger` antes del bloque pyarrow.

**WARNING-2 — Fixtures `model_artifacts`, `sample_input`, `sample_input_no_idolbuser`, `sample_input_no_createdat` no estan definidas en el spec ni en un `conftest.py` existente**

Los tests de T3 (`test/test_athena_similarity_fallback.py`) dependen de fixtures como `model_artifacts`, `sample_input`, `sample_input_no_idolbuser`, `sample_input_no_createdat`. Estas fixtures no son triviales: `model_artifacts` requiere los archivos `.joblib` reales (o un mock completo del pipeline sklearn), y `sample_input` debe ser un DataFrame valido que pase `validate_gate()`. El spec no define estas fixtures ni apunta a un `conftest.py` existente donde vivirían. Si el implementer las crea desde cero sin una guia, es muy probable que produzca fixtures que no son compatibles con el pipeline real de `predict_fn`.

El spec deberia decir: "Reusar las fixtures de `test/test_inference_integration.py` — crear un `conftest.py` en `test/` que exponga `model_artifacts` y `sample_input` como fixtures compartidas, basandose en el patron existente en ese archivo."

**WARNING-3 — El test `test_compute_window_changes_between_calls` usa `time.sleep(1.1)` — flaky en CI slow environments**

`test/test_athena_similarity_window.py` contiene:
```python
import time; time.sleep(1.1)
```
Este test pasara en la mayoria de entornos pero puede fallar en CI si el sistema operativo tiene resolucion de tiempo < 1s o si hay drift de reloj bajo alta carga. No es un bloqueador pero agregara segundos al tiempo de test suite y puede ser marcado como flaky. El spec deberia mencionar esto como un tradeoff conocido o sugerir `freeze_time` (de la libreria `freezegun`) como alternativa.

**WARNING-4 — `test_load_from_athena_casts_idolbuser_to_int_defense_in_depth` no mocquea `connect` — puede intentar una conexion Athena real**

```python
def test_load_from_athena_casts_idolbuser_to_int_defense_in_depth():
    with pytest.raises((ValueError, TypeError)):
        load_reference_data_from_athena(idolbuser="1; DROP TABLE x")
```

Este test NO tiene `@patch("endpoint.similarity_matcher.connect")`. La expectativa es que `int("1; DROP TABLE x")` lance `ValueError` ANTES de que se abra la conexion Athena. Eso es correcto si el implementer hace `int(idolbuser)` como primera linea de la funcion. Pero si el implementer hace el cast mas tarde (despues de `connect()`), el test intentara una conexion Athena real y colgara durante 10s (timeout de red) antes de fallar. El spec deberia hacer esto explicito: "El cast `int(idolbuser)` DEBE ser la primera operacion de la funcion, antes de cualquier llamada a pyathena."

**WARNING-5 — `test_cursor_execute_uses_dict_params` en `test_athena_similarity_sql_parametrized.py` puede producir falsos positivos**

El regex `re.findall(r"cursor\.execute\s*\([^)]+\)", src, flags=re.DOTALL)` no captura correctamente llamadas multi-linea donde el argumento de `cursor.execute()` contiene parentesis anidados (como un dict literal `{"user": ..., "window_start": ...}`). El `[^)]+` se detiene en el primer `)` del dict, no en el cierre del `cursor.execute()`. Esto significa que el test puede encontrar `matches` con contenido truncado y el assert `"," in m` puede pasar aunque el dict este cortado. En el peor caso, pasa cuando no deberia. El spec deberia usar un approach diferente: verificar que el segundo argumento de `cursor.execute` sea un dict usando el mock de `test_load_from_athena_uses_parameterized_query_F1` (que ya lo hace correctamente) en lugar de parsear el source con regex para este aspecto especifico.

**WARNING-6 — El spec especifica insercion "DESPUES de la linea `out_df[["audit_category","audit_explanation","ux_copy"]] = out_df.apply(`" pero esa linea tiene una continuation — el pattern de busqueda es ambiguo**

El minimum implementation contract de T3 dice:
> Al inicio del bloque similarity (insertar DESPUES de la línea `out_df[["audit_category","audit_explanation","ux_copy"]] = out_df.apply(...)`)

Pero en el codigo real (L1045-1047), esta expresion esta dividida en multiples lineas:
```python
out_df[["audit_category","audit_explanation","ux_copy"]] = out_df.apply(
    lambda r: pd.Series(_rebuild_audit_columns(r)), axis=1
)
```
El punto de insercion correcto es DESPUES de L1047 (el cierre del `apply(...)`), no despues de L1045. El spec no hace esto lo suficientemente preciso. La referencia correcta deberia ser "insertar en L1048, inmediatamente antes del comentario `# ===== Similarity Matching (MANDATORY) =====` en L1049." Usar el numero de linea exacto o el comentario como anchor elimina la ambiguedad.

**WARNING-7 — El spec especifica `endpoint/requirements.txt` como CREATE pero no verifica callers de `pyarrow` fuera de similarity**

El spec dice (HLTC-5): "pyarrow se mantiene porque sigue siendo usado en otros paths (no en similarity)." Sin embargo, el `endpoint/` folder no tiene `requirements.txt` hoy. Si pyarrow ya esta en el entorno SageMaker base image, no habria problema. Si NO esta, los tests existentes que usan `_load_parquet_directory_from_s3` fallaran despues de que el implementer cree `requirements.txt` con `pyarrow>=12` (porque antes pyarrow no estaba declarado, el entorno lo tenia via otro mecanismo). El spec deberia indicar al implementer que verifique si pyarrow ya esta en la imagen base antes de pinnear la version.

**WARNING-8 — `docs/ENDPOINT_FLOW_SEQUENCE.md` referencia "L100-101" pero el spec no verifica que esas lineas existan o contengan lo que se describe**

El spec dice: `docs/ENDPOINT_FLOW_SEQUENCE.md — MODIFY L100-101: actualizar paso 5`. Pero no hay ningun mecanismo de verificacion de que L100-101 del archivo actual contengan el paso 5 de similarity. Si el archivo fue modificado en commits recientes (hay `16da232` y `319edca` en el git log que tocan secuencias y flow), L100-101 puede ya no corresponder al paso de similarity. El implementer deberia buscar por contenido, no por numero de linea. El spec deberia decir: "buscar la linea que menciona 'Parquet' o 'S3 silver' en el paso de similarity y actualizarla."

---

## Verification of refinement corrections

Los 5 corrections del dev en `refinement.md` vs. lo que el spec implementa:

- [✓] **Correction 1 — Window sliding `now()` at inference time, NOT at model_fn().** Cubierto. `_compute_sliding_window()` es una funcion separada, spec T_SIMILARITY step 2 llama `_compute_sliding_window(window_months)` dentro de `load_reference_data_from_athena()`, y el test `test_compute_window_changes_between_calls` verifica que end2 > end1.

- [✓] **Correction 2 — `idOLBUserTxns` y `createdAtTxns` son required, con graceful degradation (no 400).** El refinement original decia "400 si missing". El spec cierra D1 correctamente como graceful degradation. `_validate_similarity_input()` retorna `(ok, missing_rows)` sin raise. Los tests `test_validate_missing_idolbuser_marks_row`, `test_validate_missing_createdat_marks_row_d1_graceful` y `test_validate_both_missing_marks_row_d1_graceful` estan presentes. NOTA: el refinement original especificaba 400, pero D1 (dev decision) lo cambio a graceful. El spec refleja D1 correctamente.

- [✓] **Correction 3 — 6 meses es arbitrario, sin analisis estadistico.** Cubierto via D en `plan.md` R3, nota en spec `load_reference_data_from_athena` docstring, y T6 docs item "Window decision (R3 — 6 meses arbitrario, producto)."

- [✓] **Correction 4 — Conexion Athena debe validarse DESDE el endpoint, no desde notebook.** Cubierto via T0 step 3 y 4 (verificacion local), y D5 (amended): validacion via production code `pyathena.connect()` en el propio loader en lugar de script externo.

- [✓] **Correction 5 — K-means y similarity son procesos PARALELOS independientes, no fallback.** Cubierto. R5 documentado en `plan.md`. El spec T3 explicitamente dice "Wrap el try existente para garantizar que K-means no se corrompa" y los tests `test_predict_fn_kmeans_intact_*` cubren todos los failure modes. Ninguna logica de similarity envuelve ni toca K-means columns.

---

## Verification of threats.md gate decisions

- [✓] **F1 — Parameterized SQL, no f-string.** El spec usa `cursor.execute(sql, {"user": int(idolbuser), ...})` con placeholders `%(user)s`. Grep test `test_no_fstring_sql_in_module` enforced. Test `test_load_from_athena_uses_parameterized_query_F1` verifica el dict en runtime.

- [✓] **F2 — Pre-merge DoD checkbox para S3 lifecycle 7d.** Presente en Pre-execute checklist del spec como checkbox bloqueante antes del merge. Documentacion en T6 `docs/ATHENA_INTEGRATION.md` item F2.

- [✓] **F3 — Audit team ownership documentado.** Pre-execute checklist item F3 presente. T6 doc item F3. PR description menciona explicitamente que el audit trail per-lookup es scope del equipo externo.

- [✓] **F5 — Sin validation script separado. Validacion via production code + post-deploy alpha observation.** `deploy/validate_athena_connection.py` marcado como REMOVED en el file manifest. D5 closed con la logica de produccion. V6 redefinido como post-deploy observation (no pre-merge).

- [✓] **F5+ — Structured logging two-path con classify_exception() y sha256-hashed idolbuser.** T_LOGGING task completo. `classify_exception()`, `_hash_idolbuser()`, dos paths de log (`similarity.no_history` INFO y `similarity.athena_failure` WARNING) con `idolbuser_hash`. 8 tests en `test_athena_similarity_logging.py`. PII check: tests aseguran `"604150" not in rec.getMessage()`.

- [✓] **F11 — SELECT explicito, no SELECT *.** Query en spec usa `SELECT idolbuser, createdat, statuswarning, metadata, transactionid`. Test `test_load_from_athena_uses_explicit_column_list_F11` verifica ausencia de `SELECT *` y presencia de los 5 campos.

---

## Recommendation

**PASS WITH WARNINGS — el spec es ejecutable con dos correcciones requeridas antes de `/execute`:**

### Correcciones requeridas en `spec.md` (no iniciar `/execute` sin estas):

**Fix CRITICAL-1:** En la docstring de `_normalize_athena_columns()` y en el implementation contract de T_SIMILARITY, reemplazar "Mirrors the mapping in _load_parquet_directory_from_s3() L163-172 EXACTLY" con el mapeo correcto explicito que resuelve la contradiccion con el test:

```python
# Mapping correcto para _normalize_athena_columns():
column_mapping = {
    'transactionid': 'TransactionID',  # Pascal — DTYPE_MAP, no 'transactionId'
    'idolbuser': 'idOLBUser',
    'statuswarning': 'statusWarning',
    'metadata': 'metadata',
    'createdat': 'createdAt',
}
```

Actualizar el test `test_normalize_athena_columns_maps_lowercase_to_camelcase` para que el `assert "TransactionID" in out.columns` siga siendo la afirmacion correcta (ya lo esta — el test es correcto, el texto del spec es el que contradice).

**Fix CRITICAL-2:** En T3, reescribir `test_predict_fn_always_calls_athena` para parchear la referencia interna que `predict_fn` realmente usa:

```python
@patch("endpoint.inference_rules._ensure_similarity_loaded", return_value=True)
def test_predict_fn_always_calls_athena(mock_ensure, model_artifacts, sample_input):
    mock_module = MagicMock()
    mock_module.load_reference_data_from_athena.return_value = (None, None, None, None)
    mock_module.find_similar_transaction.return_value = {
        "matched": False, "similarity_score": 0.0, "status_warning": "NONE", "top_matches": []
    }
    import endpoint.inference_rules as ir
    ir._similarity_mod = mock_module
    from endpoint.inference_rules import predict_fn
    out = predict_fn(sample_input, model_artifacts)
    assert mock_module.load_reference_data_from_athena.called
    assert "kmeans_risk_score" in out.columns
```

Adicionalmente, anadir a `conftest.py` (o al inicio del archivo de test):
```python
@pytest.fixture(autouse=True)
def reset_similarity_state():
    import endpoint.inference_rules as ir
    ir.HAS_SIMILARITY = None
    ir._similarity_mod = None
    yield
    ir.HAS_SIMILARITY = None
    ir._similarity_mod = None
```

### Warnings que el dev debe leer antes de que el implementer empiece:

- **W-1** (logger antes de definicion): El implementer debe mover `logger = logging.getLogger(__name__)` antes del bloque `try: import pyarrow`.
- **W-2** (fixtures no definidas): El implementer debe crear `test/conftest.py` con `model_artifacts` y `sample_input` antes de escribir los tests de T3. Reusar patron de `test/test_inference_integration.py`.
- **W-4** (cast antes de connect): Instruir al implementer que `int(idolbuser)` debe ser la primera linea del cuerpo de `load_reference_data_from_athena`, antes de cualquier llamada a `connect()`.
- **W-6** (insertion point ambiguo): Cambiar el punto de insercion de T3 a "insertar en L1048, inmediatamente antes del comentario `# ===== Similarity Matching (MANDATORY) =====`."
