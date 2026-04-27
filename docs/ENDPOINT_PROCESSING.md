# Procesamiento de Transacciones - Endpoint de SageMaker

## Resumen

Script para procesar transacciones a través del endpoint de SageMaker `data-safe-txns-endpoint`.

## Ejecución

### 1. Login a AWS SSO
```bash
aws sso login --profile blossom-dev
```

### 2. Ejecutar procesamiento
```bash
python3 process_endpoint.py \
  --input data/wp_input.csv \
  --output data/wp_result.csv \
  --batch-size 10 \
  --profile blossom-dev
```

## Parámetros

- `--input`: Archivo CSV de entrada (default: `data/wp_input.csv`)
- `--output`: Archivo CSV de salida (default: `data/wp_result.csv`)
- `--endpoint`: Nombre del endpoint (default: `data-safe-txns-endpoint`)
- `--region`: Región de AWS (default: `us-east-1`)
- `--batch-size`: Transacciones por lote (default: 10)
- `--profile`: Perfil de AWS (default: None)

## Resultado del Procesamiento

### Entrada
- **Archivo**: `data/wp_input.csv`
- **Registros**: 35 transacciones
- **Columnas**: 61 features originales

### Salida
- **Archivo**: `data/wp_result.csv`
- **Registros**: 35 transacciones procesadas
- **Columnas**: 61 columnas (features transformados + resultados del modelo)

### Columnas Generadas

El endpoint genera las siguientes columnas adicionales:

1. **Features transformados**: `num__*` y `cat__*` (features preprocesados)
2. **Cluster**: Cluster asignado por K-Means
3. **Distance_to_Centroid**: Distancia al centroide del cluster
4. **risk_score**: Score de riesgo (0-100)
5. **risk_decision**: Decisión de riesgo
6. **is_outlier**: Indicador de outlier (1 si risk_score >= 70)
7. **metadata**: Campo JSON con estructura para similarity matching
8. **statusWarning**: Etiqueta de estado (requerida por similarity matcher)

### Estructura de Metadata

El campo `metadata` contiene un JSON con la siguiente estructura:

```json
{
  "decisionResult": {
    "TransactionID": 4836236,
    "num__amount": 0.713,
    "num__is_night": -0.222,
    "num__hour_sin": 0.812,
    "Cluster": 3,
    "Distance_to_Centroid": 12.45,
    "risk_score": 70,
    "risk_decision": "APPROVE",
    "is_outlier": 1,
    ...
  }
}
```

## Estadísticas del Procesamiento

- **Tiempo total**: ~1.6 segundos
- **Lotes procesados**: 4 (10+10+10+5 transacciones)
- **Formato**: CSV (text/csv)
- **Risk Score promedio**: 72.71
- **Risk Score rango**: 70 - 99
- **Clusters únicos**: 3 (distribución: {3: 30, 7: 4, 4: 1})

## Uso del Resultado

El archivo `wp_result.csv` puede ser usado:

1. **Como datos de referencia para similarity matching**:
   ```python
   from similarity_matcher import find_similar_transaction
   
   result = find_similar_transaction(
       query_result=transaction_data,
       s3_uri="s3://blossom-analytics-safe-dev-nv/safe_txns/similarity/data/wp_result.csv",
       threshold=0.90
   )
   ```

2. **Para análisis de resultados del modelo**:
   - Análisis de distribución de clusters
   - Evaluación de scores de riesgo
   - Identificación de outliers
   - Análisis de distancias a centroides

3. **Subir a S3 para uso en producción**:
   ```bash
   aws s3 cp data/wp_result.csv \
     s3://blossom-analytics-safe-dev-nv/safe_txns/similarity/data/ \
     --profile blossom-dev
   ```

## Troubleshooting

### Error: Unable to locate credentials
```bash
# Solución: Ejecutar AWS SSO login
aws sso login --profile blossom-dev
```

### Error 500 del endpoint
- Verificar que el formato sea CSV (text/csv), no JSON
- Revisar logs de CloudWatch del endpoint
- Verificar que el endpoint esté en estado "InService"

### Error: Endpoint not found
```bash
# Verificar endpoints disponibles
aws sagemaker list-endpoints --profile blossom-dev
```

## Archivos Generados

- `process_endpoint.py`: Script principal de procesamiento
- `data/wp_input.csv`: Datos de entrada (35 transacciones)
- `data/wp_result.csv`: Resultados procesados (161 KB)

## Próximos Pasos

1. ✅ Procesar transacciones en endpoint
2. ✅ Guardar resultados en wp_result.csv
3. ⬜ Subir wp_result.csv a S3 (opcional)
4. ⬜ Probar similarity matching con los nuevos datos
