---
title: Statistical Rules
aliases: [Rules v8, R1 R12, Fraud Detection Rules]
tags: [concept, rules, fraud-detection, ml-endpoint]
type: concept
last_mapped_at: 2026-06-17T19:07:41Z
last_commit: 2ac735d
---

# Statistical Rules

Reglas estadísticas v8 que escoran señales de riesgo. Es la **segunda rama paralela** del endpoint (junto a K-Means y similitud). Define `statistical_rules.py`.

## Las 12 reglas

| Rule | Señal | Pts máx (v8) |
|---|---|---|
| R1 | Amount vs user avg (8 buckets) | 45 |
| R2 | Amount vs CU avg (`txn_amount_vs_cu_avg_*`) | 25 |
| R3 | Primera txn a este recipient en 6h | 30 (reducido de 40 en v7) |
| R4 | Primera txn de este account a recipient en 72h | 20 |
| R5 | Transacciones canceladas última semana/mes | 20 |
| R6 | Potential fraud txn en 2 meses | 25 |
| R7 | Acciones sospechosas en sesión actual | 20 |
| R8 | Acciones fallidas en sesión actual | 15 |
| R9 | Sin remembered device | 15 |
| R10 | Nocturnal + weekend + recency baja | 20 |
| R11 | Ratio amount/CU avg (>5×=45, >3×=30, >2×=20) | 45 |
| R12 | Auth state (`is_any_auth_session=0`) | 15 |
| **Total** | | **R_MAX = 295** |

Las pts exactas y los thresholds están en `statistical_rules.py`. Los buckets de R1 son piecewise: thresholds `[0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 3.0, 5.0]` → pts `[2, 4, 6, 9, 14, 19, 26, 34, 45]`.

## Piecewise normalization

```python
if raw_score <= 90:
    score = raw_score
elif raw_score < 295:
    score = 90 + (raw_score - 90) * (10 / 205)
else:
    score = 100
```

Diseño:

- **0–90:** identidad. La mayoría de las transacciones caen acá. Score lineal con suma de pts.
- **90–295:** compresión. Una transacción muy mala (suma > 90) escala hacia 100 pero sin saltar bruscamente.
- **≥295:** clip a 100.

Esto evita que pequeñas variaciones en las reglas R3+R11 (que solas ya suman 75) crucen el cutoff `Reject=90` sin razón sistémica.

## Cutoffs

| Score | Decision |
|---|---|
| `< 70` | Accept |
| `70–79` | User Auth |
| `80–89` | Admin Review |
| `≥ 90` | Reject |

## Graceful defaults

Cada regla maneja campos ausentes en el payload con default `0` (sin penalización):

- `count_user_cancelled_txn_in_last_week` null → no contribuye a R5
- `count_suspected_actions_in_current_session` null → no contribuye a R7
- `is_any_auth_session` null → no contribuye a R12

El payload puede tener hasta 38% de nulls en columnas de sesión sin romper el pipeline (ver [[Glossary]] y `docs/ENDPOINT_INPUT_FORMAT.md`).

## Independencia

- Corre **después** de K-Means en el mismo `predict_fn` (`endpoint/inference_rules.py` L990–1020).
- **No** depende de Athena.
- **No** depende de `idOLBUserTxns` ni `createdAtTxns` (esos sólo afectan similitud).
- Se desactiva con env var `DISABLE_RULES=1` → K-means + similitud siguen corriendo.

## Combiner

El score final del endpoint es una combinación de K-means + rules vía `combine_kmeans_and_rules()`. La similitud (cuando hay match high-confidence) puede hacer **override** sobre la decisión final pero no modifica `kmeans_*` ni el resultado base de las reglas (que permanecen en el output como columnas separadas).

## Files

- `endpoint/statistical_rules.py` — 354 líneas, las 12 reglas + scoring + classify_risk
- `endpoint/inference_rules.py` L990–1020 — invocación de `score_transaction_v8()` por row
- `test/test_inference_integration.py` — cobertura E2E

## See also

- [[K-Means-Pipeline]] — la primera rama paralela
- [[Similarity-Athena]] — la tercera rama (opcional aditiva)
- [[Graceful-Degradation]] — qué pasa cuando alguna rama falla

## Backlinks

- [[Graceful-Degradation]]
- [[Index]]
- [[K-Means-Pipeline]]
- [[README]]
- [[Similarity-Athena]]

#concept #rules #fraud-detection #ml-endpoint
