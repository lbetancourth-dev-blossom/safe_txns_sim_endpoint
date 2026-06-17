# AI Agent Instructions

> Lee esto antes de hacer cambios en este repo.

<!-- codemap:auto-generated:start -->

## Module map

| Module | Path | Purpose |
|---|---|---|
| Endpoint | `endpoint/` | Código del contenedor SageMaker (K-means + reglas + similitud Athena) |
| Deploy | `deploy/` | Scripts SageMaker SDK |
| Test | `test/` | Tests pytest + scripts manuales |
| Data Engineering | `data_eng/` | Pipeline ETL Bronze→Silver (offline) |

## Critical files

- `endpoint/inference_rules.py` — orquestador. `model_fn`, `predict_fn`, `DTYPE_MAP`, `_validate_similarity_input` (D1). **Crítico.**
- `endpoint/similarity_matcher.py` — Athena loader. La query SQL, `_compute_sliding_window`, `classify_exception`, `_hash_idolbuser`. **Crítico.**
- `endpoint/statistical_rules.py` — 12 reglas v8. R_MAX=295, cutoffs Accept/User Auth/Admin Review/Reject.
- `endpoint/schema_validator.py` — schema enforcement. 58 features esperadas.
- `endpoint/requirements.txt` — deps que se empaquetan. Cambios acá requieren testing contra el image SKLearn 1.2-1.

## Architecture rules

- **K-Means, reglas, y similitud son PROCESOS PARALELOS INDEPENDIENTES.** No es una cadena con fallback. Cualquier rama que falle deja sus columnas en null sin afectar las demás. Ver `docs/codemap/00-overview/Graceful-Degradation.md`.
- **K-means corre SIEMPRE.** Aunque el resto falle, `kmeans_risk_score` y `kmeans_risk_decision` siempre tienen valor.
- **Ventana sliding `now() − 6 meses`** se computa en cada call dentro de `find_similar_transaction()`. NUNCA en `model_fn()` (el contenedor queda caliente días).
- **D1 graceful:** `idOLBUserTxns` o `createdAtTxns` ausentes → `sim_*=null` para ese row, NO error 400.
- **PyAthena parameterized queries.** F-string SQL está prohibido. Hay un test que grepea el código.
- **Connection on-demand por call.** No singleton de PyAthena.

## Security considerations

- **PII:** `idOLBUser` NUNCA en plaintext en logs. Siempre via `_hash_idolbuser()` (sha256 truncado a 16 chars).
- **SQL injection:** parameterized queries. El `int()` cast es defensa-in-depth, NO la única defensa.
- **Exception messages:** truncar a 200 chars en logs para evitar log injection.
- **Cross-account IAM:** endpoint en development → recursos en alpha. Si el rol falla → `similarity.athena_failure` con `category=permission`. NO esconder el error — alertar.
- **S3 staging Athena:** los resultados de queries quedan en `gold/athena-metadata/`. Platform team debe tener lifecycle policy 7d (acción pre-merge).
- **Audit trail:** lookups de transaction history por miembro NO se loguean como audit todavía. Otro equipo lo maneja. Mientras tanto, accepted risk.

## Patterns to follow

- **Lazy imports** de `similarity_matcher` y `statistical_rules` via `importlib`. Disabled vía env vars `DISABLE_SIMILARITY=1` / `DISABLE_RULES=1`.
- **Structured logging:** `logger.info("similarity.no_history", extra={...})` y `logger.warning("similarity.athena_failure", extra={"category": classify_exception(exc), ...})`. Categories: `permission | throttling | timeout | query_error | unknown`.
- **`classify_exception()`** para mapear excepciones AWS a categories observables.
- **`_compute_sliding_window(months=6)`** dentro de cada call.
- **TDD strict:** test commit primero (RED), impl commit después (GREEN). Separados.

## Patterns to avoid

- ❌ F-string SQL (`f"WHERE idolbuser = {x}"`)
- ❌ `pyathena.connect()` cacheado a nivel módulo
- ❌ Calcular ventana en `model_fn()`
- ❌ `try/except` alrededor de TODO el `predict_fn` (esconde K-means failures)
- ❌ Loguear `idOLBUser` en plaintext
- ❌ Retornar 400 cuando falta `idOLBUserTxns` o `createdAtTxns` (D1 graceful)
- ❌ `--no-verify` en commits
- ❌ Imports cross-file sin lazy load (rompe el `DISABLE_*` env var pattern)
- ❌ `SELECT *` en queries productivas (usar lista explícita con `metadata`)
- ❌ Hardcodear endpoint name fuera de `deploy/`

## Where to find context

- **Project overview** → `CLAUDE.md` (root)
- **Per-module context** → `<module>/CLAUDE.md` (ej. `endpoint/CLAUDE.md`)
- **Architecture deep-dive** → `docs/codemap/00-overview/Architecture.md`
- **Glossary de términos** → `docs/codemap/00-overview/Glossary.md`
- **SDD workflow** → `docs/codemap/00-overview/SDD-Workflow.md`
- **Agent reading order** → `docs/codemap/00-overview/Agent-Memory.md`
- **Ticket activo** → `changes/<TICKET>/spec.md` (qué hacer) y `plan.md` (decisiones)
- **Endpoint input format** → `docs/ENDPOINT_INPUT_FORMAT.md`
- **Test scenarios** → `docs/TEST_SCENARIOS.md`

<!-- codemap:auto-generated:end -->
