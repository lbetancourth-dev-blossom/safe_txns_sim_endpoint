---
title: Glossary
aliases: [Domain Terms, Vocabulary]
tags: [overview, glossary, domain]
type: overview
last_mapped_at: 2026-06-17T19:07:41Z
last_commit: 2ac735d
---

# Glossary

Términos del dominio que aparecen en este repo. Si no entendés alguno mientras leés un module page, volvé acá.

## ML / inference

| Término | Definición |
|---|---|
| **K-Means** | Modelo de clustering no supervisado. Asigna cada transacción a un cluster + calcula `Distance_to_Centroid`. La distancia normalizada produce `kmeans_risk_score`. |
| **Cluster** | ID entero del cluster asignado por K-Means (0..N-1). |
| **Distance_to_Centroid** | Distancia euclidiana entre la transacción y el centroide de su cluster. Mayor distancia = más outlier. |
| **risk_score** | Score final 0–100 después de aplicar reglas y normalización piecewise. |
| **risk_decision** | Decisión multi-nivel: `Accept`, `User Auth`, `Admin Review`, `Reject`. Derivada del `risk_score`. |
| **kmeans_risk_score** / **kmeans_risk_decision** | Score y decisión basados SOLO en K-Means (sin reglas, sin similitud). Siempre presentes en el output. |
| **statusWarning** | Tag de la transacción histórica en el datalake: `SAFE`, `RISKY`, o `NONE`. Filtra qué rows entran a similitud. |
| **sim_score** | Similitud (cosine) del input con la transacción más similar en la ventana de 6m. `null` si no hay historial o falla Athena. |
| **sim_status** | Status de la transacción matched (SAFE/RISKY). |
| **sim_decision** | Decisión derivada del par (sim_score, sim_status). `null` si sim_score < threshold o no hubo match. |
| **sim_match_txn_id** | TransactionID del match histórico. `null` si no hubo match. |
| **Centroide** | Punto representativo de un cluster K-Means. |

## Reglas (statistical_rules.py)

| Término | Definición |
|---|---|
| **R1–R12** | Las 12 reglas de fraud detection en v8. Cada una asigna pts; la suma se normaliza vía piecewise a 0–100. |
| **R_MAX = 295** | Máximo teórico de puntos sumando todas las reglas. |
| **Piecewise normalization** | Si raw ≤ 90 → score = raw; si 90 < raw < 295 → score = 90 + (raw-90)×(10/205); si raw ≥ 295 → score = 100. |
| **Cutoffs** | `<70` Accept, `70–79` User Auth, `80–89` Admin Review, `≥90` Reject. |

## Athena / similarity

| Término | Definición |
|---|---|
| **Sliding window** | Ventana de 6 meses calculada en cada call: `[now() − 6m, now()]`. **No** anclada a `createdAtTxns`. |
| **Glue catalog** | Metadata store de AWS. Tabla `dlh_silver_safe_alpha.safetransactionresults` particionada por `createdat_month`. |
| **S3 staging Athena** | Bucket donde Athena escribe los resultados intermedios de cada query. `gold/athena-metadata/` en cuenta alpha. |
| **Partition pruning** | Filtrar particiones de Glue antes de leer datos. El predicado `createdat >= TIMESTAMP '...'` lo activa automáticamente. |
| **Parameterized query** | Query con placeholders `%(name)s` que PyAthena escapa automáticamente. Defensa estructural contra SQL injection. Ver [[Similarity-Athena]]. |
| **classify_exception** | Helper que mapea excepciones de Athena a 5 categorías: `permission`, `throttling`, `timeout`, `query_error`, `unknown`. Habilita alertas focalizadas. |

## Identidad / datos

| Término | Definición |
|---|---|
| **idOLBUserTxns** | Identificador del usuario OLB. Campo del payload. Filtra similarity por usuario. `null` → graceful degradation (`sim_*=null`). |
| **idolbuser** | Mismo campo, lowercase, como aparece en la tabla Athena. |
| **createdAtTxns** | Timestamp de la transacción. Campo del payload. Requerido en input contract (junto con `idOLBUserTxns`); su nulo → `sim_*=null`. |
| **idFi** | ID de la credit union. |
| **TransactionID** | ID único de la transacción. |
| **recipient_key** | Identificador de la cuenta destino. |
| **idOLBUser** (CamelCase) | Forma canónica en el código Python; mismo campo que `idOLBUserTxns` después del normalize. |

## Compliance / risk categories

| Término | Definición |
|---|---|
| **SAFE / RISKY** | Status de transacciones históricas usadas como referencia en similarity. Filtra `WHERE statuswarning IN ('SAFE','RISKY')`. |
| **PII** | Personally Identifiable Information. `idOLBUser` es un identificador interno — nunca debe loguearse en plaintext (siempre via `_hash_idolbuser`). |
| **PCI DSS / BSA-AML / NCUA** | Frameworks de compliance fintech. Aplican al manejo de datos transaccionales. Ver [[changes/DATA-1264/threats.md]]. |
| **Cross-account IAM** | Endpoint en development necesita policies para leer Athena/S3/Glue en alpha. Ver [[Architecture]]. |

## SDD / workflow

| Término | Definición |
|---|---|
| **SDD+TDD** | Spec-Driven Development + Test-Driven Development. Ciclo de Blossom. Ver [[SDD-Workflow]]. |
| **DCR** | Decision-Closed Refinement. Sub-fase de `/plan` que cierra decisiones arquitectónicas. |
| **HLTC** | High-Level Technical Contract. Sub-fase de `/plan` que documenta bloques arquitectónicos. |
| **Preflight** | Audit adversarial del spec antes de `/execute`. Bloquea CRITICAL findings. |
| **Threats** | Análisis de seguridad fintech. 10 categorías mandatorias para tickets sensibles. |

## Backlinks

- [[Index]]
- [[README]]
- [[Statistical-Rules]]

#glossary #domain-terms #vocabulary
