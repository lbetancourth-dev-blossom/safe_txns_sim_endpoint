# Escenarios de prueba del endpoint — Safe Transactions

**Archivo de input:** `data/test_scenarios.csv`
**Columnas:** 61 (mismo formato que `data/data_collection_idFi52_mar_2026.csv`)
**Cómo invocar:** `python test/process_endpoint.py --input data/test_scenarios.csv --output data/test_scenarios_result.csv`

Cada fila cubre un escenario distinto del endpoint. Los TransactionIDs son sintéticos (9000001–9000009) para distinguirlos del dato real.

---

## Escenarios

### S1 — Usuario activo con historial completo (`TransactionID=9000001`)

| Campo clave | Valor |
|---|---|
| `idOLBUserTxns` | 83772 |
| `count_user_all_txn_in_last_6_months` | 247 |
| `amount` | $577.00 |
| `recency_user_created_days` | 1027 |
| `TransactionProcessingType` | Schedule |
| `access` | MOBILE |

**Qué prueba:** Pipeline completo. El usuario tiene 247 transacciones en 6 meses → Athena debería devolver historial de similitud → `sim_score` con valor. K-means + reglas + similitud todos activos.

**Resultado esperado:**
- `kmeans_risk_score`: valor numérico
- `kmeans_risk_decision`: `Accept` o `Reject`
- `sim_score`: valor float (>0 si el usuario tiene historial en `dlh_silver_safe_alpha`)
- `sim_status`: `SAFE` o `RISKY` (si `sim_score >= 0.90`)

---

### S2 — Usuario nuevo sin historial de 6 meses (`TransactionID=9000002`)

| Campo clave | Valor |
|---|---|
| `idOLBUserTxns` | 794195 |
| `recency_user_created_days` | 28 (creado hace 28 días) |
| `amount_coef_var_lst6m` | null |
| `count_user_all_txn_in_last_6_months` | 44 |
| `is_night` | 1 |

**Qué prueba:** Escenario 3 del ticket DATA-1264. Usuario sin historial suficiente en la ventana Athena (6 meses) → Athena devuelve 0 rows → `sim_*=null`. K-means sigue corriendo normalmente. Verifica que K-means y similitud son procesos independientes (D5 del refinement).

**Resultado esperado:**
- `kmeans_risk_score`: valor numérico (no null)
- `kmeans_risk_decision`: valor (no null)
- `sim_score`: `null`
- `sim_status`: `null`
- `sim_decision`: `null`
- Log CloudWatch: `similarity.no_history` INFO (no athena_failure)

---

### S3 — Transacción en batch (`TransactionID=9000003`)

| Campo clave | Valor |
|---|---|
| `idOLBUserTxns` | 206 |
| `is_batch` | 1 |
| `num_recipients_batch` | valor no nulo |
| `count_user_all_txn_in_last_6_months` | 941 (usuario muy activo) |
| `TransactionProcessingType` | Intime_From_Recurrent |
| `access` | null (batch frecuentemente sin sesión web) |

**Qué prueba:** Transacción de batch / lote. Verifica que el endpoint maneja `access=null` correctamente y que `TransactionCategory=SEND_MONEY_BATCH_PAYMENT_ACH` se categoriza bien por las reglas de inferencia.

**Resultado esperado:**
- Pipeline completa sin error por `access=null`
- `kmeans_risk_decision`: valor
- Similitud con historial amplio del usuario → `sim_score` esperado

---

### S4 — Monto superior al percentil 95 de la CU (`TransactionID=9000004`)

| Campo clave | Valor |
|---|---|
| `idOLBUserTxns` | 76962 |
| `amount` | $3,000.00 |
| `is_amount_greater_than_cu_p95_amount_ach_txn_in_last_6_months` | 1 |
| `txn_amount_vs_cu_avg_amount_ach_txn_in_last_6_months` | ratio alto |

**Qué prueba:** Transacción inusualmente grande para los estándares de la credit union. Valida que las reglas de inferencia penalizan el monto relativo alto y que el K-means lo clasifica correctamente.

**Resultado esperado:**
- `kmeans_risk_score`: probablemente alto
- `kmeans_risk_decision`: posiblemente `Reject` o escalado
- Reglas de inferencia activadas por monto > p95

---

### S5 — Transacción nocturna desde mobile (`TransactionID=9000005`)

| Campo clave | Valor |
|---|---|
| `idOLBUserTxns` | 143204 |
| `is_night` | 1 |
| `access` | MOBILE |
| `amount` | $80.00 |
| `recency_user_created_days` | 851 |

**Qué prueba:** Transacción de noche desde dispositivo móvil. Verifica la interacción de features temporales (`is_night`, `hour_sin`, `hour_cos`) con el modelo K-means.

**Resultado esperado:**
- Pipeline completa
- `kmeans_risk_score`: valor influenciado por señales nocturnas
- Similitud activa (usuario con algo de historial)

---

### S6 — Transacción programada / recurrente (`TransactionID=9000006`)

| Campo clave | Valor |
|---|---|
| `idOLBUserTxns` | 89039 |
| `TransactionProcessingType` | Schedule |
| `TransactionCategory` | TRANSFER_EXTERNAL_TO_LOAN_ACH |
| `amount` | $25.00 |
| `is_night` | 1 |
| `access` | DESKTOP |

**Qué prueba:** Pago programado de préstamo — patrón típico de bajo riesgo. Verifica que `TransactionProcessingType=Schedule` y `TransactionCategory=TRANSFER_EXTERNAL_TO_LOAN_ACH` se codifican correctamente.

**Resultado esperado:**
- `kmeans_risk_decision`: `Accept` (pago recurrente de préstamo, monto bajo)
- Similitud activa

---

### S7 — Primera transacción a nuevo destinatario, monto alto (`TransactionID=9000007`)

| Campo clave | Valor |
|---|---|
| `idOLBUserTxns` | 93513 |
| `is_first_txn_from_this_olb_user_to_this_recipient_account_q_6h` | 1 |
| `is_first_txn_from_this_account_to_recipient_account_q_72h` | 1 |
| `amount` | $3,000.00 |
| `is_amount_greater_than_cu_p95_amount_ach_txn_in_last_6_months` | 1 |
| `access` | MOBILE |
| `is_access_from_remembered_device` | 0 |

**Qué prueba:** Combinación de señales de riesgo alto: primera vez enviando a este destinatario + monto sobre p95 + dispositivo no recordado + acceso mobile. Escenario más propenso a `Reject`.

**Resultado esperado:**
- `kmeans_risk_score`: alto
- `kmeans_risk_decision`: `Reject` probable
- Reglas de inferencia activadas (primera txn + dispositivo desconocido)
- Similitud: usuario con pocas txn en 6m (6 en total) → posible `sim_score=null`

---

### S8 — `idOLBUserTxns` ausente (degradación graceful D1) (`TransactionID=9000008`)

| Campo clave | Valor |
|---|---|
| `idOLBUserTxns` | **null** |
| `createdAtTxns` | presente |
| `amount` | $500.00 |

**Qué prueba:** Decisión D1 del plan. Cuando `idOLBUserTxns` está ausente → el módulo de similitud lo detecta y retorna `sim_*=null` sin lanzar excepción. K-means y reglas de inferencia corren normalmente.

**Resultado esperado:**
- `kmeans_risk_score`: valor numérico (no null)
- `kmeans_risk_decision`: valor (no null)
- `sim_score`: `null`
- `sim_status`: `null`
- `sim_decision`: `null`
- `sim_match_txn_id`: `null`
- Sin error 500. Log: `[SIMILARITY][VALIDATION]` INFO indicando campo ausente.

---

### S9 — `createdAtTxns` ausente (degradación graceful D1) (`TransactionID=9000009`)

| Campo clave | Valor |
|---|---|
| `idOLBUserTxns` | 88807 (presente) |
| `createdAtTxns` | **null** |
| `amount` | $875.00 |

**Qué prueba:** Segunda variante de D1. `createdAtTxns` ausente no rompe el endpoint porque la ventana de similitud es `now() - 6 meses` (no depende de `createdAtTxns`). Sin embargo `_validate_similarity_input` valida su presencia como parte del input contract → `sim_*=null`.

**Resultado esperado:**
- Igual que S8: K-means completo, `sim_*=null`
- Sin error en el pipeline

---

## Tabla resumen

| TxnID | Escenario | K-means | sim_score | Señal principal |
|---|---|---|---|---|
| 9000001 | Usuario activo normal | ✅ | Con valor | Historial completo 6m |
| 9000002 | Usuario nuevo — Escenario 3 | ✅ | `null` | Sin historial en ventana Athena |
| 9000003 | Batch payment | ✅ | Con valor | `is_batch=1`, usuario muy activo |
| 9000004 | Monto > p95 CU | ✅ | Con valor | Señal de monto inusual |
| 9000005 | Nocturno + mobile | ✅ | Con valor | `is_night=1`, `access=MOBILE` |
| 9000006 | Pago programado préstamo | ✅ | Con valor | `Schedule`, bajo riesgo |
| 9000007 | Nuevo destinatario + monto alto | ✅ | `null` probable | Señales múltiples de riesgo |
| 9000008 | `idOLBUserTxns` ausente | ✅ | `null` | D1 graceful degradation |
| 9000009 | `createdAtTxns` ausente | ✅ | `null` | D1 graceful degradation |

---

## Monitoreo en CloudWatch post-prueba

Después de correr los escenarios contra el endpoint desplegado, verificar:

```
# Debe aparecer para S2 (usuario sin historial):
similarity.no_history  →  INFO, rows=0

# NO debe aparecer para ningún escenario de prueba normal:
similarity.athena_failure  →  WARNING (indica falla de conexión/permisos)

# Si aparece similarity.athena_failure con category=permission:
# → Cross-account IAM roto. Escalar a platform team. Rollback no necesario (K-means sigue).
```
