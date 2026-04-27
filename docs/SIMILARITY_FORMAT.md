# Transformación de Formato para Similarity Matching

## Resumen

Transformación de `wp_result.csv` al formato estándar de `SafeTransactionResults` para uso con similarity matching.

## Proceso Completado

### 1. Archivo de Entrada
- **Origen**: `data/wp_result.csv`
- **Contenido**: Resultado del procesamiento del endpoint de SageMaker
- **Formato**: 35 transacciones × 61 columnas
- **Incluye**: Features transformados (num__*, cat__*) + resultados del modelo

### 2. Archivo Guía
- **Referencia**: `data/_SafeTransactionResults__202604231620.csv`
- **Propósito**: Formato estándar para similarity matching
- **Estructura**: 7 columnas con metadata en JSON

### 3. Archivo de Salida
- **Destino**: `data/wp_similarity.csv` (177 KB)
- **Formato**: 35 transacciones × 7 columnas
- **Estado**: ✅ Listo para usar

## Estructura del Archivo Generado

### Columnas Principales

```
uuid,transactionId,idFi,statusWarning,metadata,createdAt,updatedAt
```

1. **uuid**: Identificador único generado (UUID v4)
2. **transactionId**: ID de la transacción original (de TransactionID)
3. **idFi**: ID de institución financiera (52)
4. **statusWarning**: Estado fijo = `SAFE`
5. **metadata**: JSON con 3 secciones
6. **createdAt**: Timestamp de creación
7. **updatedAt**: Timestamp de actualización

### Estructura del Campo `metadata`

El campo metadata contiene un JSON con 3 secciones:

#### 1. `numericVariables` (27 campos)
Variables numéricas originales sin transformar:
- `amount`, `is_night`, `hour_sin`, `hour_cos`
- `day_of_week_cos`, `month_cos`, `is_batch`
- `count_all_txn_last_5m`, `total_actions_session`
- `user_age`, `total_accounts`
- Y más...

#### 2. `categoricalVariables` (5 campos)
Variables categóricas originales:
- `TransactionProcessingType` (ej: "Intime")
- `TransactionOrigin` (ej: "M2m External")
- `TransactionCategory` (ej: "SEND_MONEY_BATCH_PAYMENT_ACH")
- `user_type` (ej: "mixed")
- `access` (vacío o valor)

#### 3. `decisionResult` (58 campos)
Features transformados + resultados del modelo:
- **Features preprocesados**: `num__*`, `cat__*` (todos los features transformados)
- **Resultados del modelo**:
  - `Cluster`: Cluster asignado (ej: 3, 4, 7)
  - `Distance_to_Centroid`: Distancia al centroide
  - `risk_score`: Score de riesgo (70-99)
  - `risk_decision`: Decisión (ej: "User Auth", "Reject")
  - `is_outlier`: 0 o 1

### Ejemplo de Registro

```json
{
  "uuid": "8fcdf389-e6a0-4516-925b-5e62188a7e17",
  "transactionId": 4836236,
  "idFi": 52,
  "statusWarning": "SAFE",
  "metadata": {
    "numericVariables": {
      "amount": 16623.5,
      "is_night": 0,
      "hour_sin": 0.707,
      ...
    },
    "categoricalVariables": {
      "TransactionProcessingType": "Intime",
      "TransactionOrigin": "M2m External",
      ...
    },
    "decisionResult": {
      "num__amount": 0.713,
      "num__is_night": -0.222,
      "Cluster": 4,
      "Distance_to_Centroid": 12.04,
      "risk_score": 75,
      "risk_decision": "User Auth",
      "is_outlier": 1,
      ...
    }
  },
  "createdAt": "2026-04-27 16:21:42.956 -0500",
  "updatedAt": "2026-04-27 16:21:42.956 -0500"
}
```

## Validación

✅ **Todas las validaciones pasaron:**
- Formato JSON válido en campo metadata
- Estructura coincide 100% con archivo guía
- statusWarning = SAFE en todas las transacciones
- Todas las columnas requeridas presentes
- Compatible con similarity_matcher

## Uso del Archivo

### 1. Subir a S3
```bash
aws s3 cp data/wp_similarity.csv \
  s3://blossom-analytics-safe-dev-nv/safe_txns/similarity/data/ \
  --profile blossom-dev
```

### 2. Usar con Similarity Matcher
```python
from similarity_matcher import find_similar_transaction

# Configurar para usar wp_similarity.csv
result = find_similar_transaction(
    query_result=transaction_data,
    s3_uri="s3://blossom-analytics-safe-dev-nv/safe_txns/similarity/data/wp_similarity.csv",
    threshold=0.90
)
```

### 3. Actualizar endpoint_test
El módulo `endpoint_test` ya está configurado para usar archivos CSV:
```python
# La configuración por defecto en endpoint_test/similarity_matcher.py
DEFAULT_S3_KEY = "safe_txns/similarity/data/wp_result.csv"
```

## Scripts Utilizados

1. **`process_endpoint.py`**: Procesar wp_input.csv en el endpoint
2. **`transform_similarity.py`**: Transformar wp_result.csv al formato estándar
3. **`upload_to_s3.py`**: Subir archivos a S3 (opcional)

## Próximos Pasos

1. ✅ Procesar transacciones en endpoint → `wp_result.csv`
2. ✅ Transformar al formato estándar → `wp_similarity.csv`
3. ⬜ Subir `wp_similarity.csv` a S3
4. ⬜ Actualizar configuración en `endpoint_test` para usar `wp_similarity.csv`
5. ⬜ Probar similarity matching con nuevos datos

## Resumen de Archivos

| Archivo | Descripción | Tamaño | Estado |
|---------|-------------|--------|--------|
| `data/wp_input.csv` | Datos de entrada (35 txns) | 16 KB | ✅ |
| `data/wp_result.csv` | Resultado del endpoint | 161 KB | ✅ |
| `data/wp_similarity.csv` | Formato para similarity | 177 KB | ✅ |
| `transform_similarity.py` | Script de transformación | 8 KB | ✅ |

## Comandos Útiles

```bash
# Ver estructura del archivo
head -2 data/wp_similarity.csv

# Contar registros
wc -l data/wp_similarity.csv

# Validar JSON en metadata (primera línea)
python3 -c "import pandas as pd, json; df=pd.read_csv('data/wp_similarity.csv'); print(json.dumps(json.loads(df.iloc[0]['metadata']), indent=2))" | head -50
```
