# Plan — DATA-1264

**Ticket:** DATA-1264 — Filtro previo de similitud por ventana sliding de 6 meses con Athena
**Área:** `safe_data_science` · **Repo:** `safe_txns_sim_endpoint` · **Branch:** `feat/DATA-1264`
**Stack:** `py-agents` (SageMaker SKLearn endpoint, Python 3.x)
**Riesgo:** **medium** (re-evaluado tras gate decisions applied 2026-06-17: F1 fully mitigated por parametrized queries, F5 redesigned sin validation script, F3 externalized al equipo de audit. Cross-account IAM sigue siendo un riesgo, pero ahora es observable vía structured logging post-deploy en alpha) · **Sensible fintech:** sí (datos transaccionales, PII implícita: `idOLBUser`)
**Estimación:** M (~12h) — re-estimada tras gate decisions (applied 2026-06-17): -2h (no validation script) + 0.5h (parameterized queries) + 0.5h (structured logging + classify_exception) = neto -1h vs 13h previo
**Implementer routing:** `blossom-implementer` (TDD genérico — no es trabajo Figma-driven)
**Estado:** DCR cerrado por el dev + security gate decisions aplicadas (2026-06-17) — listo para `/execute`.

> **Riesgo top-level (cross-account IAM):** El endpoint corre en la cuenta AWS **development**. El data lake (Glue catalog + S3 staging) vive en la cuenta **alpha** (`blossom-analytics-datalake-alpha`). **Cross-account IAM no validado pre-merge**. Si el rol SageMaker en development carece de permisos cross-account a Athena/Glue/S3 en alpha, **toda la feature falla** y la query a Athena devuelve excepción → `sim_*=null` (degradación graceful). Tras gate decision F5 (applied 2026-06-17), la validación se hace **POST-DEPLOY en alpha** observando el log estructurado `similarity.athena_failure` durante 24h (NO pre-merge con script separado).

---

## 0. Pre-merge actions (BLOQUEANTES — fuera del código)

- [ ] **F2 — Platform team: 7-day S3 lifecycle rule.** Coordinar con el equipo de plataforma para añadir una regla de lifecycle de **delete a 7 días** sobre el prefix `s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/` ANTES de mergear este PR. Sin esta regla, los resultados de queries Athena acumulan indefinidamente como residuo PII. Esto es infra config, NO code change. Documentar en el PR description el ticket de plataforma o la confirmación del equipo.
- [ ] **F3 — External owner (audit team).** El audit trail para lookups de transaction history por miembro es propiedad del equipo de audit/compliance (Blossom). Su iniciativa cubrirá este endpoint cuando se entregue. Para DATA-1264, NO se añade audit logging — accepted risk para el deployment window en alpha. NO se crea follow-up ticket en este scope.
- [ ] **AC5 (post-deploy en alpha — bloqueante para promoción a higher envs, NO para merge):** Desplegar en alpha y monitorear `similarity.athena_failure` count en CloudWatch durante 24h. Expected count = 0 (o matchea el baseline horario de timeouts bajo carga normal). Si > 0 con `category=permission` → cross-account IAM roto, rollback o escalar a plataforma.

---

## 1. Contexto

El endpoint productivo (`endpoint/inference_rules.py`) ejecuta hoy un pipeline de 6 pasos: preprocessing → K-means → rules (opcional) → hybrid → similarity → output. El paso de similitud (L1049-1128) carga todo el dataset Silver `safetransactionresults` desde Parquet en S3 (`blossom-analytics-datalake-alpha/datalake/silver/SAFE/safetransactionresults/data/`), lo cachea en memoria y compara cada transacción entrante contra TODO el histórico con cosine similarity.

El ticket pide pre-filtrar ese dataset de referencia por **ventana sliding `now() − 6m`** y por **`idOLBUserTxns`** del payload, usando Athena en lugar de Parquet en bruto. Eso reduce el universo de búsqueda de ~243+ transacciones globales a las del usuario en los últimos 6 meses, mejorando precisión y latencia.

La conexión PyAthena ya está validada en `~/Downloads/PyAthena.ipynb` desde SageMaker Studio (no desde el contenedor productivo del endpoint — eso es bloqueador de AC5).

---

## 2. Decisiones cerradas durante refinement (NO re-litigar)

| # | Decisión | Origen | Grounding |
|---|----------|--------|-----------|
| R1 | Ventana = sliding `now() − 6m` a `now()` calculada en cada request | Dev correction #1 | `refinement.md` L24, evaluar dentro de `find_similar_transaction()` para evitar staleness del contenedor caliente |
| R2 | `idOLBUserTxns` y `createdAtTxns` son input contract obligatorios | Dev correction #2 | `refinement.md` L25-26, `inference_rules.py` L87 (DTYPE_MAP) confirma presencia en schema |
| R3 | 6 meses es decisión arbitraria de producto, sin análisis estadístico | Dev correction #3 | `refinement.md` L26, AC1 reducido a nota documental |
| R4 | Conexión Athena debe validarse DESDE el endpoint, no desde notebook | Dev correction #4 | `refinement.md` L27, IAM/VPC/container del endpoint son distintos a Studio |
| R5 | K-means y similarity son procesos paralelos independientes, NO fallback | Dev correction #5 | `inference_rules.py` L985-988 (kmeans_*) y L1049-1127 (sim_*) son ramas independientes de `predict_fn`. Cuando sim_* falla, kmeans_* queda intacto porque ya se computó antes |

---

## 3. Decisiones auto-cerradas por la IA (con grounding)

> **Nota post-D2:** Tras la decisión del dev D2 (Athena single-source, sin USE_ATHENA toggle), las decisiones A2, A6 y A17 quedan **REVOCADAS** (eran sobre el env var de toggle). El resto sigue válido. Las nuevas decisiones de naming de env vars (`SIMILARITY_ATHENA_*`) vienen de D2.

```yaml
ai_closed:
  - id: A1
    dimension: scope
    decision: "Reemplazar load_reference_data_from_s3() por load_reference_data_from_athena() — Athena es la ÚNICA fuente para similarity. El path Parquet se elimina."
    grounding: "endpoint/similarity_matcher.py L295 tiene load_reference_data_from_s3(); D2 confirma 'la única fuente de datos en athena con el filtro para similitud'. Se elimina (o se deprecia + ruta hacia Athena) load_reference_data_from_s3() y _load_parquet_directory_from_s3()"
    revised_by: "D2 (single-source Athena)"

  - id: A2
    dimension: naming
    decision: "REVOCADA — D2 elimina el toggle USE_ATHENA. Env vars productivas: SIMILARITY_ATHENA_DATABASE, SIMILARITY_ATHENA_TABLE, SIMILARITY_ATHENA_S3_STAGING, SIMILARITY_ATHENA_REGION (sin booleano de switch)"
    grounding: "D2: 'NO USE_ATHENA env var. NO Parquet fallback.'"
    revised_by: "D2"

  - id: A3
    dimension: error_handling
    decision: "Si la conexión Athena falla, log warning + devolver tupla (None, None, None, None). find_similar_transaction() ya maneja eso retornando sim_*=null (graceful degradation)"
    grounding: "similarity_matcher.py L519-527 — patrón existente; sigue siendo válido tras D2 porque el fallback NO es a Parquet sino a sim_*=null directamente"

  - id: A4
    dimension: propagation
    decision: "Propagar idOLBUserTxns desde input_data hasta find_similar_transaction() vía nuevo parámetro idolbuser (lowercase, match con columna Glue) y nuevo parámetro window_months"
    grounding: "inference_rules.py L1058-1067 — query_features se construye iterando df_transformed columnas num__/cat__; idOLBUserTxns NO está en df_transformed (fue filtrado en preprocessing). Hay que tomarlo de input_data antes del loop. Tras D1 (graceful), si idOLBUserTxns es None/missing, NO se llama al matcher para esa row y sim_*=null"

  - id: A5
    dimension: file_placement
    decision: "Lógica de validación de input contract (idOLBUserTxns + createdAtTxns presentes para similarity) vive como helper privado _validate_similarity_input() en inference_rules.py, llamado al inicio del bloque similarity (después de K-means). Reporta missing_rows; NO levanta excepción (D1)"
    grounding: "inference_rules.py L240-330 ya tiene validate_gate() con ValidationError, pero D1 confirma graceful degradation — por eso este helper retorna (ok, missing_rows) sin raise"

  - id: A6
    dimension: feature_flag
    decision: "REVOCADA — D2 elimina el feature flag USE_ATHENA. Athena es default y única ruta. Si Athena falla, sim_*=null (D4); no hay fallback a Parquet"
    grounding: "D2: 'NO USE_ATHENA env var. NO Parquet fallback.'"
    revised_by: "D2"

  - id: A7
    dimension: dependencies
    decision: "Añadir pyathena>=3.0 y python-dateutil>=2.8 — pinnear con >= no ==, en línea con cómo se importa boto3/pyarrow sin pinning estricto en el repo"
    grounding: "similarity_matcher.py L33-37 (pyarrow try/except sin pin), L28 (boto3 sin pin). Repo no tiene requirements.txt — dependencies viajan dentro del tarball SageMaker"

  - id: A8
    dimension: dependencies_placement
    decision: "Crear requirements.txt en /endpoint/ (carpeta source_dir del SKLearnModel). SageMaker SKLearn 1.2-1 instala automáticamente /opt/ml/code/requirements.txt cuando source_dir='endpoint/' en SKLearnModel()"
    grounding: "deploy/deploy_with_sdk.py L18 usa entry_point='inference_rules.py'. Añadir source_dir='endpoint' permite auto-install. NO hay requirements.txt en /endpoint/ hoy (verificado por find -name)"

  - id: A9
    dimension: athena_window_computation
    decision: "datetime.now(timezone.utc) - relativedelta(months=6) se calcula en cada invocación a load_reference_data_from_athena(), nunca en model_fn() ni a nivel de módulo"
    grounding: "refinement.md L65 — el contenedor SageMaker permanece caliente días; calcular en module load congelaría la ventana. PyAthena.ipynb cell 18c4 muestra el patrón exacto con reference_dt y start_dt"

  - id: A10
    dimension: athena_query_format
    decision: "Query usa parámetros formateados como TIMESTAMP literals (no parameterized query), siguiendo exactamente el patrón validado en PyAthena.ipynb cell 8db22c32"
    grounding: "PyAthena.ipynb cell 8db22c32 — `WHERE idolbuser = {idolbuser} AND createdat >= TIMESTAMP '{start_str}' AND createdat <= TIMESTAMP '{ref_str}'`. PyAthena soporta parameterized pero el patrón validado usa f-string. idolbuser es int (DTYPE_MAP L87), no SQL injection risk"

  - id: A11
    dimension: athena_column_case
    decision: "Columnas Glue son lowercase: idolbuser, createdat, statuswarning, metadata, transactionid. Normalización a camelCase ocurre en el DataFrame post-fetch igual que en _load_parquet_directory_from_s3()"
    grounding: "similarity_matcher.py L163-172 — column_mapping ya existe para Parquet. Reusar misma lógica post-Athena-fetch para preservar el contrato downstream (metadata.decisionResult, statusWarning, TransactionID)"

  - id: A12
    dimension: observability
    decision: "Mantener prefijo [SIMILARITY] en logs nuevos y añadir [ATHENA] para llamadas Athena específicas — print() + logger.info() según convención existente"
    grounding: "inference_rules.py L31-72 — prefijos [RULES], [SIMILARITY] en print(); similarity_matcher.py L41 usa logger Python. Patrón establecido"

  - id: A13
    dimension: testing
    decision: "Tests viven en /test/ con prefijo test_athena_similarity_*.py. Usar moto/mock_athena o monkeypatch para evitar llamar Athena real"
    grounding: "test/test_parquet_similarity.py, test/test_e2e_with_s3.py — convención test_<feature>.py existente. No hay framework de mock instalado, monkeypatch sobre pyathena.connect es el camino mínimo"

  - id: A14
    dimension: cache_strategy
    decision: "Cache key incluye (idolbuser, ventana_start_truncada_a_minuto) — invalidar cuando cambie el minuto evita query Athena cada llamada en el mismo segundo"
    grounding: "similarity_matcher.py L73 _REFERENCE_CACHE es dict por cache_key. Truncar la ventana al minuto da hits del 100% en ráfagas de inferencia (batch) sin envejecer la ventana más de 60s"

  - id: A15
    dimension: similarity_threshold
    decision: "Mantener threshold=0.90 default igual que hoy — no cambia con el filtro nuevo"
    grounding: "inference_rules.py L1051 SIMILARITY_THRESHOLD=0.90, similarity_matcher.py L67 DEFAULT_THRESHOLD=0.90. AC del ticket no toca el threshold, solo el conjunto de referencia"

  - id: A16
    dimension: docs
    decision: "Crear docs/ATHENA_INTEGRATION.md como doc nueva (siguiendo convención de SILVER_LAYER_MIGRATION.md, SIMILARITY_INTEGRATION.md) en lugar de modificar README_E2E.md (que no existe). Actualizar ENDPOINT_FLOW_SEQUENCE.md L100-101 con la nueva fuente Athena"
    grounding: "docs/ list: 24 docs en /docs sin README_E2E.md. SILVER_LAYER_MIGRATION.md (~existe) es el precedente más cercano. ENDPOINT_FLOW_SEQUENCE.md L100-101 cita el bucket dev — necesita update a alpha + nota Athena"

  - id: A17
    dimension: backwards_compat
    decision: "REVOCADA — D2 elimina el toggle. load_reference_data_from_s3() y _load_parquet_directory_from_s3() se ELIMINAN (o se mantienen como dead code marcado para borrar en el siguiente PR). El flujo Parquet queda fuera del path de similarity"
    grounding: "D2: 'la Parquet path es fully removed. similarity_matcher.py now has ONE data source: Athena.'"
    revised_by: "D2"

  - id: A18
    dimension: response_shape
    decision: "El shape del response NO cambia — sim_match_txn_id, sim_score, sim_status, sim_decision siguen siendo los mismos 4 campos. Lo único que cambia es el universo desde el que se calculan (Athena con filtro idolbuser + ventana 6m)"
    grounding: "inference_rules.py L1101-1106 sim_* fields. AC4 confirma 'sim_score se devuelve igual'. Sin breaking change downstream"
```

Total auto-cerradas: 18 (3 revocadas por D2: A2, A6, A17).

---

## 4. Decisiones del dev (5/5 CERRADAS — 2026-06-16)

```yaml
ticket: DATA-1264
phase: plan
sub_phase: dcr
stack: py-agents
status: closed
closed_by: "Landneyker Betancourth"
closed_at: "2026-06-16"
blocks:
  - id: D1
    dimension: input_contract_granularity
    status: CLOSED
    closed_choice: "(b) Graceful degradation"
    closed_decision: |
      Cuando idOLBUserTxns o createdAtTxns están ausentes/nulos en el payload,
      K-means + rules corren normalmente y sim_*=null. El endpoint NUNCA devuelve
      HTTP 400 por campos exclusivos de similarity. Coherente con R5 (procesos
      paralelos independientes).
    impact:
      - "_validate_similarity_input() retorna (ok, missing_rows) sin raise"
      - "Para rows en missing_rows: sim_*=null, K-means intacto"
      - "Contrato del endpoint: K-means + rules son obligatorios; similarity es best-effort"
    triggered_flag:
      hard: 9
      reason: "Cambia el contrato del endpoint productivo — decisión de producto cerrada por el dev"

  - id: D2
    dimension: athena_vs_parquet_switching
    status: CLOSED
    closed_choice: "(b) Athena SINGLE-SOURCE — NO env var toggle, NO Parquet fallback"
    closed_decision: |
      Athena es la ÚNICA fuente de datos para similarity. El Parquet path se
      elimina por completo (load_reference_data_from_s3 y _load_parquet_directory_from_s3
      se borran o se marcan como dead code). NO USE_ATHENA env var. NO conditional branching.
      Si Athena falla → sim_*=null (graceful degradation por D4).

      Quote dev: "la única fuente de datos en athena con el filtro para similitud,
      si no hay datos para la similitud respuesta de kmeans+rules y sim None"
    impact:
      - "Elimina A2, A6, A17 (todas relacionadas con el toggle)"
      - "Simplifica el código: una sola ruta en find_similar_transaction()"
      - "Reduce estimación ~1h (no hay dual-mode que mantener)"
      - "AUMENTA RIESGO si Athena falla: mitigado por D4 (timeout) + graceful degradation (D1)"
      - "Env vars keep: SIMILARITY_ATHENA_DATABASE, SIMILARITY_ATHENA_TABLE, SIMILARITY_ATHENA_S3_STAGING, SIMILARITY_ATHENA_REGION"
    triggered_flag:
      hard: 29
      reason: "Single point of failure — Athena down = similarity down. Mitigated by graceful degradation."

  - id: D3
    dimension: athena_connection_lifecycle
    status: CLOSED
    closed_choice: "(a) On-demand"
    closed_decision: |
      Conexión PyAthena se abre dentro de find_similar_transaction() (o dentro del
      nuevo Athena loader) y se cierra al final via try/finally. NO singleton a nivel
      de módulo. NO pool.
    impact:
      - "Cold-start latency: +100-300ms por request"
      - "Sin estado compartido entre requests"
      - "Compensado por cache de resultados (A14): (idolbuser, ventana_minuto)"
    triggered_flag:
      hard: null
      soft: null
      reason: "Decisión cerrada en favor de simplicidad y correctness"

  - id: D4
    dimension: query_timeout_and_retry
    status: CLOSED
    closed_choice: "(b) 10s timeout + log warning + sim_*=null"
    closed_decision: |
      Timeout duro de 10s para la query Athena. Si excede → log warning estructurado
      (una línea por ocurrencia), set sim_*=null, return normalmente. K-means + rules
      quedan intactos. El caller ve respuesta limpia; ops ve la warning en CloudWatch.
    impact:
      - "Cubre el cold-start Athena 2-10s observado en notebook"
      - "Bajo throttling concurrente, requests degradan graceful en lugar de bloquearse"
      - "CloudWatch warning format: [SIMILARITY][ATHENA][TIMEOUT] idolbuser={X} window={start}->{end} elapsed_ms={N}"
    triggered_flag:
      hard: null
      soft: 14
      reason: "Performance SLO — cerrado con 10s explícito"

  - id: D5
    dimension: ac5_validation_scope
    status: CLOSED (AMENDED 2026-06-17 — gate decision F5)
    closed_choice: "(c) NO separate script — validation via production code + post-deploy alpha observation + structured logging"
    closed_decision: |
      AMENDED by security gate F5 (applied 2026-06-17). The previously-planned
      deploy/validate_athena_connection.py is REMOVED. Dev's words:
      "La validación de conexión se hace dentro del script con el connect()
      de pyathena, no es necesario un script aparte."

      Validation now happens via:
        1. The production code's pyathena.connect() call inside
           find_similar_transaction() (the new Athena loader). If cross-account
           permissions are wrong, this fails on the first inference call after deploy.
        2. The dev deploys to alpha first. CloudWatch observation for 24h
           after deploy confirms Athena queries succeed.
        3. If queries fail consistently → rollback (trivial because K-means + rules
           still work).

      AC5 satisfaction is now POST-DEPLOY-IN-ALPHA, NOT pre-merge. The cross-account
      IAM risk stays in the risk matrix but the gating moves from "Run #2 of validation
      script must pass before merge" to "Post-deploy in alpha: monitor logs for 24h
      and confirm no Athena failures."

      The observability that the validation script would have provided is replaced
      by F5+ — structured logging (T_LOGGING task) that distinguishes
      `similarity.no_history` (INFO, 0 rows, normal Scenario 3) from
      `similarity.athena_failure` (WARNING/ERROR, exception with classified category).
      A CloudWatch alarm fires if `similarity.athena_failure` count > N per minute.

      idOLBUser MUST NEVER be logged in plaintext — use sha256-truncated hash for
      the audit dimension. This is PII compliance and also closes part of F4.

      CRITICAL — Cross-environment constraint (UNCHANGED, still applies):
        - El endpoint corre en cuenta AWS DEVELOPMENT
        - El data lake (Glue + S3 staging) está en cuenta AWS ALPHA
        - El rol SageMaker en development necesita permisos CROSS-ACCOUNT:
            * athena:StartQueryExecution, GetQueryExecution, GetQueryResults en alpha (us-east-2)
            * s3:GetObject, PutObject, ListBucket sobre blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/ (staging)
            * s3:GetObject sobre blossom-analytics-datalake-alpha/datalake/silver/SAFE/safetransactionresults/data/ (data)
            * glue:GetTable, GetPartitions sobre dlh_silver_safe_alpha.safetransactionresults
        - Si el rol carece de cross-account access, toda la feature falla → ESCALAR A PLATAFORMA
    impact:
      - "AC5 NO bloquea merge; bloquea promoción de alpha a higher envs"
      - "Cross-account IAM se valida vía production code + structured logging observado en CloudWatch"
      - "deploy/validate_athena_connection.py ELIMINADO del file manifest"
      - "T_AC5 spec task REMOVED; replaced by T_LOGGING (structured logging)"
      - "Top-level risk K_CROSS_ACCOUNT sigue en sección 7, ahora observable vía logs"
    triggered_flag:
      hard: 29
      reason: "Cross-account IAM observable vía logs — gate movido de pre-merge a post-deploy alpha"
```

---

## 5. HLTC — Architectural deltas (revisado tras D1-D5 cerradas)

```yaml
ticket: DATA-1264
phase: plan
sub_phase: hltc
stack: py-agents
status: approved
revised_for: "D2 (single-source Athena) — toggle eliminado, Parquet path removido"
auto_accepted:
  - id: HLTC-1
    type: function
    action: NEW
    summary: "similarity_matcher.load_reference_data_from_athena(idolbuser, window_months=6, force_reload=False, timeout_seconds=10) — REEMPLAZA load_reference_data_from_s3() para similarity"
    derived_from: "A1, R1, R2, D2"

  - id: HLTC-2
    type: function
    action: NEW
    summary: "inference_rules._validate_similarity_input(input_data) — chequea presencia de idOLBUserTxns no nulo; retorna (ok, missing_rows) SIN raise (D1 graceful)"
    derived_from: "A5, R2, D1"

  - id: HLTC-3
    type: code_block
    action: MODIFIED
    summary: "inference_rules.py L1049-1127 — el for-loop de similarity extrae idOLBUserTxns de input_data antes del loop, valida con _validate_similarity_input, llama SIEMPRE a load_reference_data_from_athena (sin condicional USE_ATHENA)"
    derived_from: "A4, R5, D1, D2"

  - id: HLTC-4
    type: config
    action: REMOVED
    summary: "USE_ATHENA env var ELIMINADA por D2. Env vars productivas: SIMILARITY_ATHENA_DATABASE, SIMILARITY_ATHENA_TABLE, SIMILARITY_ATHENA_S3_STAGING, SIMILARITY_ATHENA_REGION, ATHENA_WINDOW_MONTHS, ATHENA_TIMEOUT_SECONDS"
    derived_from: "D2"

  - id: HLTC-5
    type: dependencies
    action: NEW
    summary: "Crear endpoint/requirements.txt con pyathena>=3.0, python-dateutil>=2.8, pyarrow, boto3 — pyarrow se mantiene porque sigue siendo usado en otros paths (no en similarity)"
    derived_from: "A7, A8"

  - id: HLTC-6
    type: docs
    action: NEW
    summary: "docs/ATHENA_INTEGRATION.md — connection pattern (parameterized PyAthena queries), IAM permissions (incluyendo CROSS-ACCOUNT dev→alpha), troubleshooting, F5+ alerting playbook (replaces former validate_athena_connection.py runbook), F2 platform action + F3 external owner notes (gate applied 2026-06-17)"
    derived_from: "A16, R3, D5"

  - id: HLTC-7
    type: code_block
    action: MODIFIED
    summary: "docs/ENDPOINT_FLOW_SEQUENCE.md L100-101 — reemplazar bucket dev por alpha-via-Athena. Eliminar referencia a Parquet directo en el paso 5 del flujo"
    derived_from: "A16, D2"

  - id: HLTC-11
    type: code_removal
    action: DEPRECATED
    summary: "similarity_matcher.load_reference_data_from_s3() y _load_parquet_directory_from_s3() — marcadas como dead code o eliminadas por D2. find_similar_transaction() ya NO las llama"
    derived_from: "D2"

blocks:
  - id: HLTC-8
    type: integration
    action: NEW
    mode: review
    plain_summary: "Conexión nueva del endpoint productivo a AWS Athena CROSS-ACCOUNT (endpoint en dev, Athena/Glue/S3 en alpha). Requiere permisos IAM cross-account en el rol SageMaker de la cuenta development."
    summary: "PyAthena → Athena/Glue/S3 desde contenedor SageMaker en cuenta development hacia cuenta alpha. CROSS-ACCOUNT IAM REQUIRED."
    preview: |
      ARQUITECTURA CROSS-ACCOUNT (confirmada por dev en D5):
        - Endpoint SageMaker: cuenta AWS DEVELOPMENT
        - Athena + Glue + S3 data lake: cuenta AWS ALPHA (blossom-analytics-datalake-alpha)

      Permisos IAM cross-account requeridos en el rol SageMaker en development:
        - athena:StartQueryExecution        (alpha, us-east-2)
        - athena:GetQueryExecution          (alpha, us-east-2)
        - athena:GetQueryResults            (alpha, us-east-2)
        - athena:StopQueryExecution         (alpha, us-east-2)
        - glue:GetTable                     (alpha) sobre dlh_silver_safe_alpha.safetransactionresults
        - glue:GetDatabase                  (alpha) sobre dlh_silver_safe_alpha
        - glue:GetPartitions                (alpha) sobre la tabla
        - s3:PutObject, GetObject, ListBucket sobre s3://blossom-analytics-datalake-alpha/datalake/gold/athena-metadata/
        - s3:GetObject sobre s3://blossom-analytics-datalake-alpha/datalake/silver/SAFE/safetransactionresults/data/

      ADICIONALMENTE — el bucket policy de blossom-analytics-datalake-alpha debe
      permitir explícitamente al principal del rol SageMaker en cuenta development
      (cross-account trust bidireccional).

      Region: us-east-2 (Athena alpha) — el endpoint SageMaker está en us-east-1 según
      deploy_with_sdk.py. Cross-region adds latency + egress charges.

      BLOQUEADOR: si la IAM cross-account NO está provisionada, NINGUNA query funciona.
      Mitigación operativa: D1+D4 graceful degradation → endpoint NO devuelve 5xx,
      pero similarity queda en sim_*=null hasta que IAM se arregle.
    affected_files:
      - "endpoint/similarity_matcher.py (MODIFIED — añadir load_reference_data_from_athena, eliminar load_reference_data_from_s3 de la ruta principal)"
      - "endpoint/requirements.txt (CREATE)"
      - "deploy/deploy_with_sdk.py (MODIFIED — source_dir='endpoint/', env vars Athena)"
      - "docs/ATHENA_INTEGRATION.md (CREATE — incluir cross-account IAM policy + F5+ alerting playbook)"
    triggered_flag:
      hard: 29
      reason: "Nueva integración cross-account AWS — AC5 ahora gated post-deploy (F5 gate applied 2026-06-17)"

  - id: HLTC-9
    type: security
    action: NEW
    mode: review
    plain_summary: "La query Athena usa PyAthena parameterized queries (NO f-string interpolation). El cast int(idolbuser) se mantiene como defensa en profundidad. Estructuralmente seguro contra SQL injection."
    summary: "PyAthena cursor.execute(sql, {'user': int(idolbuser), 'window_start': window_start_ts}) — structural escape. NOT f-string SQL. Test contract: grep verifica que NO existe f-string SQL en el módulo."
    preview: |
      Riesgo SQL injection: muy bajo (mitigación estructural cerrada por F1 gate decision).
      Defensa estructural (F1 mitigation applied 2026-06-17):
        1. PyAthena DB-API parameterized queries — el binding escapa automáticamente:
             cursor.execute(
                 "SELECT ... WHERE idolbuser = %(user)s AND createdat >= %(window_start)s ...",
                 {"user": int(idolbuser), "window_start": window_start_ts}
             )
        2. _validate_similarity_input intenta cast a int — si falla, row va a missing_rows
        3. load_reference_data_from_athena hace int(idolbuser) explícito como defensa en
           profundidad (no como protección primaria — PyAthena ya escapa)
        4. Test: grep el código fuente para detectar f-string SQL — si encuentra → fail
      Por D1: si idolbuser no es castable → sim_*=null para esa row, NO se llama a Athena.
      Riesgo residual: muy bajo (mitigación estructural).
      REVOCA A10 (que decía "PyAthena soporta parameterized pero el patrón validado usa f-string").
    affected_files:
      - "endpoint/inference_rules.py (MODIFIED — _validate_similarity_input con int cast safe)"
      - "endpoint/similarity_matcher.py (MODIFIED — load_reference_data_from_athena usa cursor.execute con params)"
    triggered_flag:
      hard: 12
      reason: "Mitigación estructural completada vía PyAthena parameterized queries (F1 gate decision applied 2026-06-17)"

  - id: HLTC-10
    type: performance
    action: NEW
    mode: review
    plain_summary: "Cada inferencia dispara una query Athena (2-10s cold start) — sin Parquet fallback. Sin cache esto destroza la latencia."
    summary: "Cache key=(idolbuser, ventana_minuto_truncado). Athena query budget: 10s timeout (D4), log+sim_null si excede. Connection: on-demand (D3)."
    preview: |
      Tras D2 (single-source Athena), TODO request productivo va a Athena.
      Latencia Athena cold start: 2-10s.
      Latencia Athena warm + cached resultado: ~200-500ms (cache hit).
      Mitigación:
        - Cache _ATHENA_CACHE por (idolbuser, ventana_minuto), TTL implícito 60s (A14)
        - Timeout 10s (D4): log warning + degradación graceful sim_*=null
        - K-means SIEMPRE devuelve respuesta válida (R5) aunque Athena falle/timeout
      Riesgo elevado: requests con idolbusers distintos generan N queries Athena en
      paralelo → throttling alpha workgroup (DEFAULT_QUERY_CONCURRENCY=5).
      Mitigación: D4 timeout 10s + sim_*=null bajo throttling.
    affected_files:
      - "endpoint/similarity_matcher.py (MODIFIED — _ATHENA_CACHE dict global, timeout config)"
    triggered_flag:
      hard: null
      soft: 14
      reason: "Cambio de característica de performance del endpoint — toda invocación toca Athena ahora"

  - id: HLTC-12
    type: operational_risk
    action: NEW
    mode: review
    plain_summary: "Sin Parquet fallback, una outage de Athena/Glue degrada similarity al 100% (no parcial). K-means sigue OK, pero sim_* se vuelven null para TODOS los requests."
    summary: "Single point of failure introducido por D2. K-means + rules independientes (R5) absorben el blast radius. Observabilidad cubierta por HLTC-13 (structured logging)."
    preview: |
      Antes de D2: Athena down → fallback a Parquet → similarity sigue funcionando.
      Después de D2: Athena down → sim_*=null para 100% de requests (degradación graceful, no caída).

      Mitigaciones existentes:
        - K-means + rules INDEPENDIENTES → el endpoint sigue devolviendo decision
        - sim_*=null es respuesta válida del contrato (D1)
        - HLTC-13 structured logging diferencia exception vs 0 rows → CloudWatch alarm
          dispara SOLO en exception path (no false-positive de Scenario 3)

      Monitoring (cubierto ahora por HLTC-13):
        - Métrica `similarity.athena_failure` count per minute
        - Alarmar si > N por minuto con category=permission → cross-account broken
        - Documentado en ATHENA_INTEGRATION.md
    affected_files:
      - "docs/ATHENA_INTEGRATION.md (CREATE — incluir sección Operational Risk + alerting playbook con HLTC-13)"
    triggered_flag:
      hard: 29
      reason: "Single point of failure introducido — observabilidad cubierta por HLTC-13 structured logging"

  - id: HLTC-13
    type: observability
    action: NEW
    mode: review
    plain_summary: "Dos paths de log distintos para distinguir 'Athena devolvió 0 filas' (normal, Scenario 3 del ticket) de 'Athena lanzó excepción' (cross-account broken, throttling, timeout). Sin esto, las alertas sobre Athena tendrían false positives de usuarios sin historia."
    summary: "structured logging two-path: similarity.no_history (INFO, 0 rows) + similarity.athena_failure (WARNING/ERROR, exception con classify_exception). idOLBUser SIEMPRE sha256-truncated, nunca plaintext."
    preview: |
      Gate decision F5+ (applied 2026-06-17): la observabilidad que el script de validación
      hubiera dado pre-merge es reemplazada por structured logging post-deploy.

      Dos paths distintos:

      a. Athena devolvió 0 rows (usuario sin historia en la ventana) — NORMAL,
         Scenario 3 del ticket, NO alertable:
           logger.info("similarity.no_history", extra={
               "idolbuser_hash": sha256(str(idolbuser).encode()).hexdigest()[:16],
               "window_months": 6,
               "rows": 0,
           })

      b. Athena lanzó excepción (cross-account broken, throttling, timeout, etc.) —
         ALERTABLE:
           logger.warning("similarity.athena_failure", extra={
               "idolbuser_hash": sha256(str(idolbuser).encode()).hexdigest()[:16],
               "exception_class": exc.__class__.__name__,
               "exception_message": str(exc)[:200],   # truncated avoiding log injection
               "category": classify_exception(exc),   # permission/throttling/timeout/query_error/unknown
           })

      classify_exception() es un helper 4-5 líneas que mapea exception types a
      categorías observables.

      CloudWatch dashboard esperado:
        - Alarma: `similarity.athena_failure` count > N per minute
        - Filtros: category=permission → cross-account IAM broken
                   category=throttling → workgroup overload
                   category=timeout → cold-start o latencia elevada
                   category=query_error → schema drift o SQL bug

      PII compliance: idOLBUser SIEMPRE hashed (sha256[:16]), nunca plaintext.
      Cierra parcialmente F4 (PII en logs) para los dos paths nuevos.
    affected_files:
      - "endpoint/similarity_matcher.py (MODIFIED — añadir logger.info/warning + classify_exception helper)"
      - "test/test_athena_similarity_logging.py (CREATE — verifica ambos paths)"
      - "docs/ATHENA_INTEGRATION.md (CREATE — incluir alerting playbook)"
    triggered_flag:
      hard: null
      soft: 14
      reason: "Observabilidad estructurada — gate decision F5+ replaces pre-merge validation script con post-deploy logs"
```

---

## 6. Manifesto de archivos (revisado tras D2)

| Archivo | Acción | Razón |
|---------|--------|-------|
| `endpoint/similarity_matcher.py` | MODIFY | Añadir `load_reference_data_from_athena()`, `_normalize_athena_columns()`, `_compute_sliding_window()`, `_ATHENA_CACHE`, timeout wrapper. **Eliminar** `load_reference_data_from_s3()` y `_load_parquet_directory_from_s3()` de la ruta de similarity (mover a dead code o borrar — D2) |
| `endpoint/inference_rules.py` | MODIFY | Añadir `_validate_similarity_input()`, extraer `idOLBUserTxns` antes del for-loop similarity L1058, llamar SIEMPRE a `load_reference_data_from_athena` (sin `if USE_ATHENA`). Eliminar referencias a `s3_bucket`/`s3_key` en la llamada al matcher |
| `endpoint/requirements.txt` | CREATE | pyathena>=3.0, python-dateutil>=2.8, pyarrow, boto3 |
| `endpoint_test/similarity_matcher.py` | MODIFY | Mirror del cambio en endpoint/ — el test dir es copia del productivo |
| `endpoint_test/inference_rules.py` | MODIFY | Mirror del cambio en endpoint/ |
| `endpoint_test/requirements.txt` | CREATE | Mirror |
| `deploy/deploy_with_sdk.py` | MODIFY | Añadir `source_dir='endpoint'` al `SKLearnModel(...)` constructor. Añadir env vars `SIMILARITY_ATHENA_DATABASE`, `SIMILARITY_ATHENA_TABLE`, `SIMILARITY_ATHENA_S3_STAGING`, `SIMILARITY_ATHENA_REGION`, `ATHENA_WINDOW_MONTHS`, `ATHENA_TIMEOUT_SECONDS`. **NO** añadir `USE_ATHENA` (D2). Eliminar (o marcar deprecated) las env vars `SIMILARITY_S3_BUCKET`/`SIMILARITY_S3_KEY` si ya no se usan |
| `deploy/deploy_notebook.py` | MODIFY | Mismo cambio que deploy_with_sdk.py (es un wrapper) |
| ~~`deploy/validate_athena_connection.py`~~ | ~~CREATE~~ | **REMOVED por gate decision F5 (applied 2026-06-17).** Validation se hace dentro del production code (pyathena.connect en find_similar_transaction) + post-deploy alpha observation (24h en CloudWatch). NO existe script aparte. |
| `docs/ATHENA_INTEGRATION.md` | CREATE | Cross-account IAM policy (dev→alpha), query pattern (parameterized PyAthena), env vars (sin toggle), troubleshooting, structured logging alerting playbook (HLTC-13), operational risk (HLTC-12), post-deploy alpha observation guidance |
| `docs/ENDPOINT_FLOW_SEQUENCE.md` | MODIFY | L100-101 actualizar fuente: paso 5 (similarity) ahora es Athena exclusivamente; eliminar mención a Parquet directo en ese paso |
| `test/test_athena_similarity_input_contract.py` | CREATE | Validar AC1, AC2 (input contract + window) — usa monkeypatch sobre pyathena.connect. Incluye test de D1 graceful degradation |
| `test/test_athena_similarity_window.py` | CREATE | Validar window sliding now-6m calculada en cada call (no en model_fn) |
| `test/test_athena_similarity_fallback.py` | CREATE | Validar R5 — K-means intacto cuando Athena falla / timeout (D4) / no hay data / idOLBUserTxns missing (D1) |
| `test/test_athena_similarity_sql_parametrized.py` | CREATE | **F1 mitigation** — grep el código fuente para asegurar que NO existe f-string SQL en el módulo. Verifica que cursor.execute se llama con dict de params. Verifica el escape estructural de PyAthena. |
| `test/test_athena_similarity_logging.py` | CREATE | **F5+ mitigation** — verifica los dos paths de structured logging: (a) Athena devuelve 0 rows → log INFO `similarity.no_history` con idolbuser_hash truncado; (b) Athena lanza PermissionError → log WARNING `similarity.athena_failure` con `category="permission"`. Verifica que idOLBUser NUNCA aparece en plaintext. |

---

## 7. Riesgos & mitigaciones (revisado tras D2)

| # | Riesgo | Probabilidad | Severidad | Mitigación |
|---|--------|--------------|-----------|------------|
| **K_CROSS_ACCOUNT** | **Cross-account IAM no validado pre-merge. Endpoint en cuenta development debe leer del data lake alpha. Si el rol carece de acceso cross-account, la feature falla 100%.** | **alta** | **alta (gated post-deploy, no pre-merge tras F5 gate applied 2026-06-17)** | **D5 (amended): producción `pyathena.connect()` lo ejerce on first inference. Observabilidad vía structured log `similarity.athena_failure` con `category="permission"` (HLTC-13). 24h CloudWatch window en alpha → 0 events = green; escalar a plataforma si > 0.** |
| K1 | Rol IAM SageMaker en dev sin permisos Athena/Glue/S3 cross-account a alpha | alta | crítica | Subset de K_CROSS_ACCOUNT — observable via `similarity.athena_failure` category="permission" |
| K2 | VPC del endpoint sin VPC endpoints para Athena/Glue/S3 (alpha) → query timeout | media | alta | D4 timeout 10s + sim_*=null graceful (caller no bloquea). Observable via `similarity.athena_failure` category="timeout" |
| K3 | Cross-region (Athena alpha en us-east-2 vs endpoint dev en us-east-1) añade latencia y egress | media | media | Documentar en ATHENA_INTEGRATION.md; mitigado por cache (A14) |
| K4 | `idolbuser` column sparse o sin filas para el usuario en la ventana 6m | baja | baja | Query devuelve 0 rows → `similarity.no_history` INFO log + sim_*=null graceful (D1+R5). NORMAL outcome, NO alerta |
| K5 | PyAthena thread-safety bajo concurrent inference | baja | media | D3 on-demand connection elimina estado compartido. Documentar en doc |
| K6 | Cambio de schema Silver (Glue rename column) rompe la query | baja-media | media | Test contracts en T_SIMILARITY cubren column normalization (_normalize_athena_columns). Observable via `similarity.athena_failure` category="query_error" |
| K7 | SageMaker SKLearn 1.2-1 image NO incluye pyathena | media | alta | A8 — endpoint/requirements.txt resuelve. T0 verifica antes de codear. Observable post-deploy via `similarity.athena_failure` (ImportError) |
| K8 | Athena workgroup alpha throttling bajo carga concurrente (5 queries/s default) | media | media | D4 timeout 10s + sim_*=null graceful. Cache A14 reduce queries duplicadas. Observable via `similarity.athena_failure` category="throttling" |
| K9 | **Single point of failure: Athena down = similarity down (sin Parquet fallback por D2)** | media | alta | K-means + rules INDEPENDIENTES (R5) → endpoint sigue válido con sim_*=null. F5+ structured logging (HLTC-13) alerta ops sin false-positive de Scenario 3. Monitoring de sim_score_null_rate sugerido en doc (ticket aparte) |

---

## 8. Estimación (re-estimada tras gate decisions applied 2026-06-17)

- Bottom-up: **~12h** (neto -1h vs 13h previo)
  - T1 (input contract validation con D1 graceful): 2h
  - T2 (load_reference_data_from_athena + parameterized queries + tests): 5.5h (+0.5h por F1: PyAthena parameterized queries + grep test)
  - T3 (cache + timeout + integración en predict_fn): 2h
  - T4 (deploy script + requirements.txt + env vars Athena): 1h
  - ~~T5 (AC5 validation script)~~: **0h — REMOVED por F5 gate** (-2h)
  - T_LOGGING (structured logging two-path + classify_exception + tests): 0.5h (NEW por F5+ gate)
  - T6 (docs ATHENA_INTEGRATION.md + ENDPOINT_FLOW_SEQUENCE.md): 1h
- Net change: -2h (T5 eliminado) + 0.5h (F1 parameterized) + 0.5h (F5+ structured logging) = **-1h**
- Histórico equipo: M (12-16h · n=2 · confianza baja)
- Confianza: media — incertidumbre principal en cross-account IAM, ahora observada post-deploy vía structured logging en alpha (24h window)

---

## 9. Próximo paso

DCR cerrado. Siguiente: security review automatizado + generación final de `spec.md` con los defaults D1-D5 cerrados ya pre-rellenados. Luego `/execute` invoca a `blossom-implementer` con el spec final.

---

**Decision: approved by Landneyker Betancourth — 2026-06-16**

All DCR decisions closed, HLTC blocks reviewed. Ready for security + spec generation.

Security gate decisions applied 2026-06-17: F1 parametrized, F2 platform pre-merge action, F3 external owner, F5 no separate script, F5+ structured logging.
