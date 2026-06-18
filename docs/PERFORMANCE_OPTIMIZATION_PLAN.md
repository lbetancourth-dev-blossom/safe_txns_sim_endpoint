# Endpoint Performance Optimization Plan

## Diagnóstico actual

| Fase | Latencia actual | % del total |
|------|----------------|-------------|
| K-Means preprocessing + predict | ~50ms | ~2% |
| Statistical rules v8 | ~10ms | <1% |
| **Athena query (cold)** | **~2,200ms** | **~97%** |
| Athena (warm, mismo usuario/día) | ~5ms | <1% |

**Problema:** El endpoint tarda 2-3 segundos POR transacción principalmente por la query a Athena. Con un batch de 10 transacciones de 3 usuarios distintos → 10 queries → 22 segundos.

---

## Fix inmediato (ya aplicado)

**Cache key por día en lugar de por minuto** (`commit b1b9df3`)

```python
# ANTES: cache miss por cada minuto distinto del mismo usuario
cache_key = f"athena:{user}:{end.strftime('%Y-%m-%d-%H-%M')}"

# DESPUÉS: 1 query por usuario por día
cache_key = f"athena:{user}:{end.strftime('%Y-%m-%d')}"
```

**Impacto:** Un batch con 4 transacciones del mismo usuario en distintas horas del mismo día pasa de 4 queries (~8s) a 1 query + 3 hits de caché (~2.2s).

---

## Optimizaciones prioritarias

### 1. Batch query multi-usuario (impacto alto, esfuerzo bajo)

**Problema:** Cada fila del batch hace un query separado a Athena.
**Fix:** Agrupar todas las filas del mismo batch por usuario antes de llamar a Athena, y hacer 1 query por usuario único.

```python
# En inference_rules.py predict_fn — antes del loop de similitud:
unique_users = df['idOLBUserTxns'].dropna().unique()
# Pre-cargar todos los usuarios del batch en paralelo o secuencial
for user_id in unique_users:
    load_reference_data_from_athena(user_id, 6, batch_date, timeout_seconds)
# El loop por fila ya tiene todo en caché
```

**Impacto:** Batch de 10 filas con 3 usuarios únicos → 3 queries (no 10). Con el caché diario, si todos son del mismo día → 3 queries total para todo el batch.

---

### 2. Pre-warm de caché al iniciar el modelo (impacto medio, esfuerzo bajo)

**Problema:** Primera transacción de cada usuario siempre paga los 2.2s.
**Fix:** En `model_fn()`, cargar el top-N usuarios más frecuentes desde S3/config.

```python
# En inference_rules.py model_fn():
top_users_path = os.path.join(model_dir, "top_users.json")
if os.path.exists(top_users_path):
    with open(top_users_path) as f:
        top_users = json.load(f)["users"]
    today = datetime.now(timezone.utc)
    for user_id in top_users[:50]:  # top 50 usuarios
        try:
            load_reference_data_from_athena(user_id, 6, today, timeout_seconds=5)
        except Exception:
            pass  # graceful
```

Genera `top_users.json` con un job diario offline desde DynamoDB/RDS.

---

### 3. Materializar a DynamoDB (impacto muy alto, esfuerzo medio)

**Problema raíz:** Athena no es una base de datos OLTP. Fue diseñada para análisis batch, no para lookups de <100ms. A medida que `SafeTransactionResults` crezca (crecimiento exponencial), la query `WHERE idolbuser = X AND CAST(createdat AS DATE) >= Y` tardará cada vez más aunque tengamos índices (Athena no tiene índices, solo partition pruning).

**Solución:** Cuando el endpoint escribe un resultado en `SafeTransactionResults`, también escribe en DynamoDB con:
- **PK:** `idolbuser`
- **SK:** `createdat`
- **Atributos:** `metadata` (JSON), `statuswarning`, `transactionid`
- **TTL:** 7 meses (auto-expire registros fuera de ventana)

El endpoint consulta DynamoDB en lugar de Athena:

```python
# similarity_matcher.py — nuevo método
def load_reference_from_dynamodb(idolbuser, window_start, window_end):
    dynamodb = boto3.resource('dynamodb', region_name='us-east-2')
    table = dynamodb.Table('SafeTxnSimilarityCache')
    response = table.query(
        KeyConditionExpression=Key('idolbuser').eq(idolbuser) &
                               Key('createdat').between(window_start, window_end),
        FilterExpression=Attr('statuswarning').is_in(['SAFE', 'RISKY'])
    )
    return response['Items']
```

**Latencia esperada:** DynamoDB P99 < 10ms (vs 2,200ms Athena).
**Costo:** ~$0.25/millón de reads. A 10k transacciones/día → ~$0.0025/día.

---

### 4. Particionar tabla Athena por `idolbuser_bucket` (impacto medio, esfuerzo medio)

Si se mantiene Athena como fuente, particionar la tabla por un hash del usuario:

```sql
-- Partición por bucket de usuario (256 buckets)
ALTER TABLE dlh_silver_safe_alpha.safetransactionresults
ADD PARTITION (idolbuser_bucket = MOD(idolbuser, 256));
```

Athena con partition pruning lee solo 1/256 del dataset por query. A medida que la tabla crezca a 100GB, una query lee ~400MB en lugar de 100GB.

**Latencia esperada:** 800ms–1,200ms (mejora 40-50% sobre sin partición).

---

### 5. Similarity asíncrono (impacto alto, esfuerzo alto)

**Idea:** Iniciar la query Athena al mismo tiempo que K-Means, en paralelo:

```python
import concurrent.futures

with concurrent.futures.ThreadPoolExecutor(max_workers=len(unique_users)) as ex:
    # Lanzar K-Means y Athena en paralelo
    kmeans_future = ex.submit(run_kmeans_pipeline, input_data)
    athena_futures = {uid: ex.submit(load_reference_from_athena, uid, ...) 
                      for uid in unique_users}
    
    kmeans_result = kmeans_future.result()  # ~50ms
    # Athena ya lleva 50ms ejecutándose en paralelo
    # Solo espera la diferencia: ~2,150ms más (no 2,200ms total)
```

**Impacto:** No reduce latencia Athena, pero la oculta detrás de K-Means. Latencia total = max(K-Means, Athena) ≈ 2,200ms en lugar de K-Means + Athena ≈ 2,250ms. Marginal hoy, pero si K-Means crece a 500ms sería más útil.

---

## Roadmap recomendado

| Prioridad | Acción | Latencia esperada | Esfuerzo |
|-----------|--------|-------------------|---------|
| ✅ **Hecho** | Cache key por día | 2,200ms → ~500ms (mismos usuarios) | Bajo |
| **1** | Batch query multi-usuario | ~2,200ms → 2,200ms/N_usuarios | Bajo |
| **2** | DynamoDB como cache de similitud | ~2,200ms → **<20ms** | Medio |
| **3** | Partición Athena | 2,200ms → 1,000ms | Medio |
| **4** | Pre-warm caché top-N usuarios | Primera txn: 0ms | Bajo |
| **5** | Similarity asíncrono | Marginal (ocultar latencia) | Alto |

---

## Proyección de crecimiento

La tabla `SafeTransactionResults` crece con cada transacción procesada:

| Volumen | Sin optimización | Con DynamoDB |
|---------|-----------------|--------------|
| 10k txns/día (hoy) | ~2,200ms | ~15ms |
| 100k txns/día | ~4,000ms | ~15ms |
| 1M txns/día | ~15,000ms (timeout) | ~15ms |

**Conclusión:** La opción 2 (DynamoDB) es la única que escala a largo plazo. Las opciones 1, 3, 4 son mejoras incrementales que se degradan con el crecimiento. DynamoDB + TTL + caché diario en memoria = <20ms para el 95% de las transacciones.

---

## Pregunta 0: Respuesta del endpoint sin datos

Confirmado: si `SafeTransactionResults` no existe, la tabla no tiene datos, o Athena falla — el endpoint responde normalmente con K-Means + rules. Los campos `sim_*` retornan `None`. Es graceful degradation por diseño (D1 del spec).

```json
{
  "decision": "Accept",
  "score": 0.72,
  "kmeans_cluster": 3,
  "sim_match_txn_id": null,
  "sim_score": null,
  "sim_status": null,
  "sim_decision": null
}
```
