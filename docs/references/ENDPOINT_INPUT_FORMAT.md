# Formato de entrada al endpoint — Safe Transactions

**Referencia:** `data/data_collection_idFi52_mar_2026.csv` (3 877 transacciones, idFi=52, marzo 2026)

El endpoint acepta un CSV en el body del request (`Content-Type: text/csv`) con **header obligatorio** y **61 columnas** en el orden que se detalla a continuación. El endpoint devuelve `application/json`.

---

## Columnas de identidad

| Campo | Tipo | Nulos | Descripción |
|---|---|---|---|
| `TransactionID` | int64 | 0 | Identificador único de la transacción |
| `idOLBUserTxns` | int64 | 0 | Identificador del usuario OLB. **Requerido para similitud** — si está ausente o nulo, `sim_*` quedan en `null` y K-means corre normalmente |
| `createdAtTxns` | string | 0 | Timestamp de la transacción. Formato: `YYYY-MM-DD HH:MM:SS.mmm`. **Requerido para similitud** — misma regla que `idOLBUserTxns` |
| `idFi` | int64 | 0 | ID de la credit union (ej. `52` = idFi del dataset de referencia) |
| `recipient_key` | string | 0 | Identificador de la cuenta destino |

---

## Features de la transacción

### Monto y temporalidad

| Campo | Tipo | Rango | Nulos | Descripción |
|---|---|---|---|---|
| `amount` | float64 | [0.04, 3 651 750.82] | 0 | Monto de la transacción (USD) |
| `is_night` | int (0/1) | {0, 1} | 0 | 1 si la transacción ocurrió de noche |
| `hour_sin` | float64 | [-1.0, 1.0] | 0 | Componente seno de la hora del día (codificación cíclica) |
| `hour_cos` | float64 | [-1.0, 1.0] | 0 | Componente coseno de la hora del día |
| `day_of_week_cos` | float64 | [-0.9, 1.0] | 0 | Componente coseno del día de la semana |
| `month_cos` | float64 | [-1.0, 1.0] | 0 | Componente coseno del mes |
| `weekend` | int (0/1) | {0, 1} | 0 | 1 si la transacción es en fin de semana |

### Actividad reciente (ventana corta)

| Campo | Tipo | Rango | Nulos | Descripción |
|---|---|---|---|---|
| `count_all_txn_last_5m` | int64 | [0, 129] | 0 | Número de transacciones del usuario en los últimos 5 minutos |
| `total_amount_all_txn_last_5m` | float64 | [0.06, 558 763] | **69%** | Monto total de transacciones del usuario en los últimos 5 min. Nulo si no hay actividad previa |
| `count_txn_to_recipient_account_last_5m` | int64 | [0, 7] | 0 | Transacciones hacia el mismo destinatario en los últimos 5 min |
| `total_amount_txn_to_recipient_account_last_5m` | float64 | [0.06, 68 876] | **94%** | Monto total hacia el mismo destinatario en últimos 5 min |
| `count_txn_to_recipient_account_in_last_2_months` | int64 | [0, 17] | 0 | Transacciones hacia este destinatario en los últimos 2 meses |
| `count_txn_to_recipient_account_in_last_week` | int64 | [0, 14] | 0 | Transacciones hacia este destinatario en la última semana |
| `count_all_txn_after_recipient_account_creation` | float64 | [0, 16] | **70%** | Transacciones totales desde que se creó la cuenta del destinatario |

### Flags de primera transacción

| Campo | Tipo | Nulos | Descripción |
|---|---|---|---|
| `is_first_txn_from_this_olb_user_to_this_recipient_account_q_6h` | int (0/1) | 0 | 1 si es la primera transacción del usuario a este destinatario en las últimas 6h |
| `is_first_txn_from_this_account_to_recipient_account_q_72h` | int (0/1) | 0 | 1 si es la primera transacción de la cuenta a este destinatario en las últimas 72h |

---

## Features del usuario (historial 6 meses)

| Campo | Tipo | Rango | Nulos | Descripción |
|---|---|---|---|---|
| `amount_coef_var_lst6m` | float64 | [0.0, 4.86] | **40%** | Coeficiente de variación del monto en últimos 6 meses |
| `pct_txns_under_100_lst6m` | float64 | [0.0, 1.0] | **40%** | % de transacciones menores a $100 en últimos 6 meses |
| `pct_txns_over_1k_lst6m` | float64 | [0.0, 1.0] | **40%** | % de transacciones mayores a $1000 en últimos 6 meses |
| `user_avg_count_txn_per_active_day_last_6_months` | float64 | [1.0, 42.6] | 2% | Promedio de transacciones por día activo en últimos 6 meses |
| `user_avg_amount_txn_per_active_day_last_6_months` | float64 | [2.0, 1 022 178] | 2% | Monto promedio por día activo en últimos 6 meses |
| `count_user_all_txn_in_last_6_months` | int64 | [0, 3242] | 0 | Total de transacciones del usuario en últimos 6 meses |
| `count_user_cancelled_txn_in_last_week` | float64 | [0, 2] | **54%** | Transacciones canceladas en la última semana |
| `count_user_cancelled_txn_in_last_month` | float64 | [0, 2] | **40%** | Transacciones canceladas en el último mes |
| `count_user_potential_fraud_txn_in_last_2_months` | float64 | [0, 0] | **40%** | Transacciones con flag de fraude potencial en últimos 2 meses |
| `recency_user_created_days` | int64 | [0, 1057] | 0 | Días desde que se creó la cuenta del usuario |
| `amt_vs_user_ach_avg_day` | float64 | [~0, 700] | 4% | Ratio del monto actual vs. promedio diario ACH del usuario |
| `ach_amount_share_6m` | float64 | [~0, 1.0] | 4% | Proporción del monto ACH en el total del usuario (6 meses) |
| `ach_count_share_6m` | float64 | [0.0, 1.0] | 2% | Proporción de transacciones ACH en el total del usuario (6 meses) |

---

## Features de sesión y dispositivo

| Campo | Tipo | Rango | Nulos | Descripción |
|---|---|---|---|---|
| `is_access_from_remembered_device` | int (0/1) | {0, 1} | 0 | 1 si el acceso es desde un dispositivo conocido/recordado |
| `count_suspected_actions_in_current_session` | float64 | [0, 10] | **38%** | Acciones sospechosas en la sesión actual |
| `total_actions_session` | float64 | [1, 576] | **38%** | Total de acciones en la sesión actual |
| `is_auth_email_session` | float64 (0/1) | {0, 1} | **38%** | 1 si la sesión fue autenticada vía email |
| `is_auth_phone_session` | float64 (0/1) | {0, 1} | **38%** | 1 si la sesión fue autenticada vía teléfono |
| `is_any_auth_session` | float64 (0/1) | {0, 1} | **38%** | 1 si hubo algún tipo de autenticación adicional en la sesión |
| `count_failed_actions_in_current_session` | float64 | [0, 9] | **38%** | Acciones fallidas en la sesión actual |
| `access` | string | — | **38%** | Canal de acceso: `DESKTOP`, `MOBILE` |
| `days_since_phone_update` | float64 | [0, 1043] | **26%** | Días desde la última actualización del teléfono del usuario |
| `days_since_email_update` | float64 | [0, 1048] | **62%** | Días desde la última actualización del email del usuario |
| `is_personal_user_phone_primary_updated_last_week` | int (0/1) | {0, 1} | 0 | 1 si el teléfono principal fue actualizado en la última semana |
| `is_personal_user_email_primary_updated_last_week` | int (0/1) | {0, 1} | 0 | 1 si el email principal fue actualizado en la última semana |

---

## Features del usuario (perfil)

| Campo | Tipo | Rango | Nulos | Descripción |
|---|---|---|---|---|
| `total_accounts` | int64 | [0, 179] | 0 | Total de cuentas del usuario |
| `checking_ratio` | float64 | [0.0, 0.67] | ~0.5% | Proporción de cuentas de tipo checking |
| `savings_ratio` | float64 | [0.11, 1.0] | ~0.5% | Proporción de cuentas de tipo savings |
| `credit_loan_ratio` | float64 | [0.0, 0.83] | ~0.5% | Proporción de cuentas de tipo crédito/préstamo |
| `user_age` | float64 | [11, 90] | **28%** | Edad del usuario en años |
| `user_type` | string | — | 0 | Tipo de usuario: `personal`, `mixed` |

---

## Features de la credit union

| Campo | Tipo | Rango | Nulos | Descripción |
|---|---|---|---|---|
| `cu_avg_amount_ach_txn_in_last_6_months` | float64 | [563, 10 479] | 0 | Monto promedio de transacciones ACH de la CU en últimos 6 meses |
| `is_amount_greater_than_cu_p95_amount_ach_txn_in_last_6_months` | int (0/1) | {0, 1} | 0 | 1 si el monto supera el percentil 95 de la CU |
| `txn_amount_vs_cu_avg_amount_ach_txn_in_last_6_months` | float64 | [~0, 357.9] | 0 | Ratio del monto vs. promedio de la CU |

---

## Features de tipo de transacción

| Campo | Tipo | Valores posibles | Nulos | Descripción |
|---|---|---|---|---|
| `TransactionProcessingType` | string | `Intime`, `Intime_From_Recurrent`, `Recurrent`, `Schedule` | 0 | Tipo de procesamiento |
| `TransactionOrigin` | string | `Blossom Pay`, `External Internal`, `Internal External`, `M2m External` | 0 | Origen de la transacción |
| `TransactionCategory` | string | Ver tabla abajo | 0 | Categoría de la transacción |

**Valores de `TransactionCategory`:**

| Valor | Descripción |
|---|---|
| `SEND_MONEY_ACH` | Envío de dinero ACH individual |
| `SEND_MONEY_BATCH_PAYMENT_ACH` | Envío en batch/lote |
| `SEND_MONEY_PAYROLL_ACH` | Pago de nómina |
| `TRANSFER_INTERNAL_EXTERNAL_ACH` | Transferencia interna→externa |
| `TRANSFER_EXTERNAL_TO_LOAN_ACH` | Pago de préstamo desde cuenta externa |
| `TRANSFER_LOAN_TO_EXTERNAL_ACH` | Transferencia de préstamo a externa |
| `SINGLE_COLLECTION_ACH` | Cobro individual ACH |
| `BUSINESS_SINGLE_COLLECTION_ACH` | Cobro individual ACH (negocio) |
| `MAVERICK_CARD_TO_INTERNAL` | Transferencia de tarjeta Maverick a cuenta interna |

---

## Features de batch

| Campo | Tipo | Rango | Nulos | Descripción |
|---|---|---|---|---|
| `is_batch` | int (0/1) | {0, 1} | 0 | 1 si la transacción es parte de un batch |
| `num_recipients_batch` | float64 | [1, 130] | **76%** | Número de destinatarios en el batch. Nulo si `is_batch=0` |
| `amount_share_in_batch` | float64 | [0.0, 1.0] | 0 | Proporción del monto de esta txn en el total del batch (0 si no es batch) |

---

## Columnas opcionales para similitud (DATA-1264)

Estas columnas ya existen en el CSV de entrada estándar y el endpoint las usa para el módulo de similitud desde la versión DATA-1264:

| Campo | Uso en similitud |
|---|---|
| `idOLBUserTxns` | Filtra el historial Athena: `WHERE idolbuser = :idOLBUserTxns` |
| `createdAtTxns` | **No** ancla la ventana. La ventana de similitud es siempre `now() − 6 meses` |

Si cualquiera de estos campos está ausente o nulo, el endpoint devuelve `sim_score=null`, `sim_status=null`, `sim_decision=null`, `sim_match_txn_id=null`. **K-means y las reglas de inferencia corren igualmente.**

---

## Notas de calidad

- **Nulos esperados y normales:** `total_amount_all_txn_last_5m` (69%), `total_amount_txn_to_recipient_account_last_5m` (94%), `num_recipients_batch` (76%), y los campos de sesión (~38%) son nulos por diseño — reflejan ausencia de actividad previa, no errores de datos.
- **Columnas de historial 6m nulas (~40%):** usuarios nuevos (sin 6 meses de historia) tendrán nulos en `amount_coef_var_lst6m`, `pct_txns_*`, `count_user_cancelled_*`, `count_user_potential_fraud_*`. El endpoint maneja estos nulos vía imputación en el pipeline de preprocesamiento.
- **`idFi` siempre es un solo valor por batch:** el endpoint procesa transacciones de una sola credit union por request.

---

## Ejemplo de fila mínima válida

```csv
TransactionID,idOLBUserTxns,createdAtTxns,idFi,recipient_key,amount,...
4836236,120799,2026-03-02 09:42:26.806,52,1487075,16623.5,...
```

La fila mínima requiere los campos sin nulos marcados con `0` en la columna Nulos. El resto puede enviarse como vacío (CSV vacío, no la cadena `"null"`) — el preprocesador los imputa.
