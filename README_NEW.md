# SAFE ML Transactions Endpoint

## Descripción General

Este proyecto implementa un **endpoint de predicción en Amazon SageMaker** para detección de fraude en transacciones financieras. El sistema combina un modelo de clustering K-Means, matching de similitud con transacciones históricas etiquetadas y reglas estadísticas para evaluar el riesgo de cada transacción en tiempo real o por lotes.

### Características Principales

- **Modelo de ML**: K-Means clustering para detectar patrones anómalos en transacciones
- **Similarity Matching**: Comparación con transacciones históricas etiquetadas (SAFE/RISKY) almacenadas en S3
- **Datos en Parquet**: Soporte para múltiples archivos Parquet con recarga automática
- **Graceful Degradation**: El endpoint continúa funcionando sin similarity si no hay datos disponibles
- **Dynamic Reload**: Detección automática de nuevos datos sin reiniciar el endpoint
- **Sistema de Reglas**: Reglas estadísticas (v8) para evaluación de riesgo basada en comportamiento histórico
- **Política Híbrida**: Combinación de clustering + similitud + reglas para decisiones más robustas
- **Scoring en Tiempo Real**: Capacidad de procesar transacciones individuales o en lote
- **Decisiones Multinivel**: Accept, User Auth, Admin Review, Reject
- **Alta Disponibilidad**: Manejo robusto de errores sin downtime del endpoint

---

## Flujo Completo del Endpoint

### 1. Input: Transacciones

```
┌──────────────────────────────────────────────────┐
│  Input: CSV o JSON                               │
│  - Desde S3, API Gateway, o directo al endpoint  │
│  - Formato: 60+ campos de transacción            │
└──────────────────┬───────────────────────────────┘
                   │
                   ▼
```

### 2. Validación y Preprocesamiento

```
┌──────────────────────────────────────────────────┐
│  VALIDACIÓN Y PREPROCESAMIENTO                   │
├──────────────────────────────────────────────────┤
│  ✓ Validación de tipos de datos (DTYPE_MAP)     │
│  ✓ Parsing de timestamps (múltiples formatos)   │
│  ✓ Derivación de features temporales:           │
│    - Cíclicos: hour_sin/cos, day_sin/cos, etc.  │
│    - Binarios: weekend, is_night                │
│  ✓ Transformaciones numéricas/categóricas       │
│  ✓ Limpieza y normalización de datos            │
└──────────────────┬───────────────────────────────┘
                   │
                   ▼
```

### 3. K-Means Clustering

```
┌──────────────────────────────────────────────────┐
│  K-MEANS CLUSTERING                              │
├──────────────────────────────────────────────────┤
│  ✓ Carga del modelo entrenado (kmeans_model)    │
│  ✓ Aplicación del pipeline de preprocesamiento  │
│  ✓ Asignación de cluster (0-N)                  │
│  ✓ Cálculo de distancia euclidiana al centroide │
│  ✓ Detección de outliers basada en distancia    │
│  ✓ Extracción de features (num__ y cat__)       │
└──────────────────┬───────────────────────────────┘
                   │
                   ▼
```

### 4. Similarity Matching (Opcional pero Recomendado)

```
┌──────────────────────────────────────────────────┐
│  SIMILARITY MATCHING                             │
├──────────────────────────────────────────────────┤
│  1. Carga de Datos de Referencia (S3):          │
│     - Bucket: blossom-analytics-safe-dev-nv     │
│     - Path: safe_txns/similarity/data/...       │
│     - Formato: Múltiples archivos .parquet      │
│     - Filtrado: Solo SAFE/RISKY (no PENDING)    │
│                                                  │
│  2. Dynamic Reload Check:                       │
│     - Cuenta archivos en S3 (~50-100ms)         │
│     - Si count cambió → recarga datos           │
│     - Si no cambió → usa cache (<1ms)           │
│                                                  │
│  3. Feature Extraction:                         │
│     - Extrae num__ y cat__ de transacción       │
│     - Valida esquema con schema_validator       │
│     - Construye vector de features (49 dims)    │
│                                                  │
│  4. Similitud Cosine:                           │
│     - Calcula similitud con todas las refs      │
│     - Ordena por score (mayor = más similar)    │
│     - Retorna top-k matches                     │
│                                                  │
│  5. Decision Override (si score >= threshold):  │
│     - Threshold por defecto: 0.90 (90%)         │
│     - Si matched AND score >= 0.90:             │
│       * Toma statusWarning del dato S3          │
│       * Si RISKY → risk_decision = "Reject"     │
│       * Si SAFE → risk_decision = "Accept"      │
│       * risk_score fijo = 70                    │
│     - Si no matched o score < threshold:        │
│       * Mantiene decisión del K-means           │
│                                                  │
│  6. Graceful Degradation:                       │
│     - Si no hay archivos en S3 → continúa      │
│     - Si archivos vacíos → continúa            │
│     - Si todos PENDING → continúa              │
│     - Si error S3 → continúa con K-means only  │
│     - NUNCA crashea el endpoint                │
└──────────────────┬───────────────────────────────┘
                   │
                   ▼
```

### 5. Reglas Estadísticas (Opcional)

```
┌──────────────────────────────────────────────────┐
│  SISTEMA DE REGLAS ESTADÍSTICAS (v8)            │
├──────────────────────────────────────────────────┤
│  Evalúa 12 reglas de fraude:                    │
│  - R2: Transacción nocturna (+20 pts)           │
│  - R3: Primera transacción destino (+30 pts)    │
│  - R4: Cancelaciones recientes (+20 pts)        │
│  - R5: Acciones sospechosas (+25 pts)           │
│  - R6: Monto alto vs perfil bajo (+20 pts)      │
│  - R7: Burst de transacciones (+35 pts)         │
│  - R8: Historial con destinatario (+15 pts)     │
│  - R10: Fin de semana (+10 pts)                 │
│  - R11: Monto desproporcionado (+45 pts)        │
│  - R12: Usuario nuevo (+15 pts)                 │
│                                                  │
│  Normalización: Piecewise mapping (0-295)→(0-100)│
│  Desactivable con: DISABLE_RULES=1              │
└──────────────────┬───────────────────────────────┘
                   │
                   ▼
```

### 6. Política Híbrida y Decisión Final

```
┌──────────────────────────────────────────────────┐
│  POLÍTICA HÍBRIDA                                │
├──────────────────────────────────────────────────┤
│  Combina:                                        │
│  - Cluster asignado por K-means                 │
│  - Distancia al centroide                       │
│  - Similarity match (si disponible)             │
│  - Score de reglas estadísticas (si habilitado) │
│                                                  │
│  Decisiones por Risk Score:                     │
│  - < 70:  Accept (Verde)                        │
│  - 70-79: User Auth (Amarillo)                  │
│  - 80-89: Admin Review (Naranja)                │
│  - >= 90: Reject (Rojo)                         │
└──────────────────┬───────────────────────────────┘
                   │
                   ▼
```

### 7. Output: Resultado Estructurado

```
┌──────────────────────────────────────────────────┐
│  OUTPUT: JSON                                    │
├──────────────────────────────────────────────────┤
│  {                                               │
│    // Clustering                                 │
│    "Cluster": 2,                                 │
│    "Distance_to_Centroid": 3.45,                 │
│    "is_outlier": false,                          │
│                                                  │
│    // Scoring y Decisión                        │
│    "risk_score": 75,                             │
│    "risk_decision": "User Auth",                 │
│                                                  │
│    // Explicaciones                              │
│    "top_contributors": [                         │
│      {"feature": "num__amount", "value": 500},   │
│      ...                                         │
│    ],                                            │
│    "audit_category": "Medium Risk",              │
│    "audit_explanation": "...",                   │
│    "ux_copy": "Requiere verificación adicional", │
│                                                  │
│    // Features Preprocesados (num__ y cat__)    │
│    "num__amount": 500.0,                         │
│    "cat__payment_method": 1.0,                   │
│    ...                                           │
│                                                  │
│    // Metadata K-means (opcional)               │
│    "kmeans_original_decision": "Accept",         │
│    "kmeans_original_score": 65                   │
│  }                                               │
└──────────────────────────────────────────────────┘
```

---

## Arquitectura del Sistema

```
                    ┌────────────────────────┐
                    │   AWS S3 Buckets       │
                    ├────────────────────────┤
                    │ • Model Artifacts      │
                    │ • Reference Data       │
                    │   (Parquet files)      │
                    │ • Input/Output Data    │
                    └───────┬────────────────┘
                            │
                            ├─────────────────┐
                            │                 │
                            ▼                 ▼
    ┌──────────────────────────────┐  ┌──────────────────┐
    │  SageMaker Endpoint          │  │  Dynamic Reload  │
    │  (ml.m5.large)               │  │  (File Monitor)  │
    │                              │◄─┤  Check S3 files  │
    │  ┌────────────────────────┐  │  │  every inference │
    │  │ inference_rules.py     │  │  └──────────────────┘
    │  │ (Entry Point)          │  │
    │  └──────┬─────────────────┘  │
    │         │                    │
    │  ┌──────▼──────────────────┐ │
    │  │ 1. Preprocessing       │ │
    │  │    (60+ features)      │ │
    │  └──────┬─────────────────┘ │
    │         │                    │
    │  ┌──────▼──────────────────┐ │
    │  │ 2. K-Means Clustering  │ │
    │  │    (kmeans_model)      │ │
    │  └──────┬─────────────────┘ │
    │         │                    │
    │  ┌──────▼──────────────────┐ │
    │  │ 3. Similarity Matching │ │
    │  │    (similarity_matcher)│ │
    │  │    - Load from S3      │ │
    │  │    - Cosine similarity │ │
    │  │    - Override decision │ │
    │  └──────┬─────────────────┘ │
    │         │                    │
    │  ┌──────▼──────────────────┐ │
    │  │ 4. Statistical Rules   │ │
    │  │    (statistical_rules) │ │
    │  │    (optional)          │ │
    │  └──────┬─────────────────┘ │
    │         │                    │
    │  ┌──────▼──────────────────┐ │
    │  │ 5. Hybrid Policy       │ │
    │  │    (Final Decision)    │ │
    │  └──────┬─────────────────┘ │
    │         │                    │
    └─────────┼────────────────────┘
              │
              ▼
    ┌──────────────────────────┐
    │  Output: JSON Response   │
    │  - risk_score            │
    │  - risk_decision         │
    │  - explanations          │
    │  - features              │
    └──────────────────────────┘
```

---

## Contenido del Repositorio

### Estructura de Archivos

```
safe_txns_sim_endpoint/
│
├── README.md                          # Este archivo
├── safe-txn-enpoint.ipynb            # Notebook principal para deploy y pruebas
├── setup_sagemaker.sh                # Script de configuración de SageMaker
│
├── endpoint/                         # Scripts del endpoint
│   ├── inference_rules.py            # ⭐ Entry point de SageMaker
│   ├── similarity_matcher.py         # ⭐ Motor de similarity matching
│   ├── schema_validator.py           # Validación de esquema de features
│   ├── statistical_rules.py          # Sistema de reglas estadísticas v8
│   └── validate_s3_data.py           # Validador de datos en S3
│
├── deploy/                           # Scripts de deployment
│   ├── deploy_similarity_endpoint.py # Deploy completo del endpoint
│   ├── deploy_notebook.py            # Deploy desde notebook
│   └── deploy_with_sdk.py            # Deploy con SageMaker SDK
│
├── test/                             # Suite de tests
│   ├── test_e2e_with_s3.py          # Test end-to-end con S3
│   ├── test_inference_integration.py # Tests de integración
│   ├── test_local_integration.py     # Tests locales
│   ├── test_parquet_similarity.py    # Tests de lectura Parquet
│   ├── test_dynamic_reload.py        # Tests de recarga dinámica
│   ├── test_graceful_degradation.py  # Tests de manejo de errores
│   └── verify_similarity_changes.py  # Verificación de cambios
│
├── data/                             # Datos de prueba
│   └── transactions_test.csv         # Transacciones de ejemplo
│
├── docs/                             # Documentación
│   ├── CHANGES_SUMMARY.md            # Resumen de cambios
│   ├── DEPLOYMENT_SUMMARY.md         # Guía de deployment
│   ├── PARQUET_MIGRATION.md          # Migración CSV→Parquet
│   ├── DYNAMIC_RELOAD.md             # Recarga automática de datos
│   ├── GRACEFUL_DEGRADATION.md       # Manejo de errores
│   ├── S3_PATHS_CONFIGURATION.md     # ⭐ Configuración de rutas S3
│   └── SIMILARITY_INTEGRATION.md     # Integración de similarity
│
└── temp_artifacts/                   # Artefactos temporales (no versionados)
```

---

## Configuración de Rutas S3

### Rutas Principales

#### 1. **Datos de Similitud (Reference Data)**
```bash
Bucket: blossom-analytics-safe-dev-nv
Path:   safe_txns/similarity/data/SafeTransactionResults/
URI:    s3://blossom-analytics-safe-dev-nv/safe_txns/similarity/data/SafeTransactionResults/

Formato: Directorio con múltiples archivos .parquet
Contenido: Transacciones históricas etiquetadas (statusWarning: SAFE/RISKY)
Estado actual: 20 archivos, 199 registros (1 SAFE, 198 PENDING)
```

#### 2. **Modelo Empaquetado**
```bash
Opción A:
URI: s3://blossom-analytics-safe-dev-nv/safe_txns/models/similarity/model.tar.gz

Opción B:
URI: s3://blossom-analytics-safe-dev-nv/output/kmeans-similarity-endpoint/model.tar.gz

Contenido: model.tar.gz con kmeans_model, preprocessing_pipeline, scripts
```

#### 3. **Artefactos del Modelo**
```bash
Bucket: blossom-analytics-safe-dev-nv
Path:   safe_txns/model_artifacts/

Archivos:
- kmeans_model.joblib
- preprocessing_pipeline.joblib
- selected_features.csv
- centroids.csv
```

### Variables de Entorno

Configure estas variables en el deployment del endpoint:

```bash
# Similarity Matching
SIMILARITY_S3_BUCKET=blossom-analytics-safe-dev-nv
SIMILARITY_S3_KEY=safe_txns/similarity/data/SafeTransactionResults/
SIMILARITY_THRESHOLD=0.90      # Umbral de similitud (0.0-1.0)
DISABLE_SIMILARITY=0           # 1 para desactivar similarity

# Reglas Estadísticas
DISABLE_RULES=0                # 1 para desactivar reglas estadísticas
```

### Cambiar Rutas S3

**Opción 1 - Variables de Entorno (Recomendado):**
```bash
export SIMILARITY_S3_BUCKET="nuevo-bucket"
export SIMILARITY_S3_KEY="nueva/ruta/"
```

**Opción 2 - Modificar Código:**
```python
# endpoint/similarity_matcher.py (líneas 68-69)
DEFAULT_S3_BUCKET = "nuevo-bucket"
DEFAULT_S3_KEY = "nueva/ruta/"
```

**Ver:** `docs/S3_PATHS_CONFIGURATION.md` para guía completa.

---

## Deployment

### Opción 1: Deploy con Script Automatizado

```bash
cd deploy/
python deploy_with_sdk.py
```

Este script:
1. Crea el modelo en SageMaker
2. Configura variables de entorno
3. Crea la configuración del endpoint
4. Despliega el endpoint (ml.m5.large)

### Opción 2: Deploy desde Notebook

```bash
jupyter notebook safe-txn-enpoint.ipynb
```

Ejecuta las celdas en orden:
1. Step 1: Descarga de artefactos desde S3
2. Step 2: Empaquetado y upload de model.tar.gz
3. Step 3: Deploy del endpoint en SageMaker
4. Step 4: Testing del endpoint

### Opción 3: Deploy Manual

```python
import sagemaker
from sagemaker.sklearn.model import SKLearnModel

model = SKLearnModel(
    model_data="s3://bucket/path/model.tar.gz",
    role="arn:aws:iam::123456789:role/SageMakerRole",
    entry_point="inference_rules.py",
    framework_version="1.2-1",
    py_version="py3",
    env={
        "SIMILARITY_S3_BUCKET": "blossom-analytics-safe-dev-nv",
        "SIMILARITY_S3_KEY": "safe_txns/similarity/data/SafeTransactionResults/",
        "SIMILARITY_THRESHOLD": "0.90",
        "DISABLE_SIMILARITY": "0",
        "DISABLE_RULES": "0"
    }
)

predictor = model.deploy(
    initial_instance_count=1,
    instance_type="ml.m5.large",
    endpoint_name="safe-txn-similarity-endpoint"
)
```

---

## Testing del Endpoint

### 1. Test Local (Sin SageMaker)

```bash
cd test/
python test_local_integration.py
```

Prueba el flujo completo localmente sin necesidad de deploy.

### 2. Test con S3

```bash
python test_e2e_with_s3.py
```

Prueba con datos reales de S3, incluyendo similarity matching.

### 3. Test de Graceful Degradation

```bash
python test_graceful_degradation.py
```

Verifica que el endpoint maneje errores correctamente:
- No hay archivos en S3
- Archivos vacíos
- Todos los registros son PENDING
- Errores de conexión S3

### 4. Test de Dynamic Reload

```bash
python test_dynamic_reload.py
```

Verifica la recarga automática de datos cuando se agregan nuevos archivos a S3.

### 5. Invocar Endpoint Deployed

```python
import boto3
import json

client = boto3.client('sagemaker-runtime')

# Preparar payload
payload = {
    "transaction_id": "test_001",
    "amount": 500.0,
    "payment_method": "credit_card",
    # ... más campos
}

# Invocar endpoint
response = client.invoke_endpoint(
    EndpointName='safe-txn-similarity-endpoint',
    ContentType='application/json',
    Body=json.dumps([payload])
)

# Parsear resultado
result = json.loads(response['Body'].read())
print(f"Risk Score: {result[0]['risk_score']}")
print(f"Decision: {result[0]['risk_decision']}")
```

O con AWS CLI:

```bash
aws sagemaker-runtime invoke-endpoint \
  --endpoint-name safe-txn-similarity-endpoint \
  --content-type text/csv \
  --body file://test_data.csv \
  output.json

cat output.json | jq '.'
```

---

## Características Avanzadas

### 1. Graceful Degradation

El endpoint **nunca crashea** por falta de datos de similitud:

**Escenarios manejados:**
- ✅ No hay archivos .parquet en S3
- ✅ Archivos vacíos (0 registros)
- ✅ Todos los registros son PENDING (no SAFE/RISKY)
- ✅ Validación de schema falla para todos
- ✅ Errores de conexión S3
- ✅ Archivos corruptos

**Comportamiento:** 
- Loggea WARNING/ERROR
- Continúa procesando con K-means only
- Retorna `matched=False, similarity_score=0.0`
- Alta disponibilidad garantizada

**Ver:** `docs/GRACEFUL_DEGRADATION.md`

### 2. Dynamic Reload

El endpoint **detecta automáticamente nuevos datos** sin reiniciar:

**Cómo funciona:**
1. En cada inferencia, cuenta archivos .parquet en S3 (~50-100ms)
2. Si el count cambió → recarga datos (~2-3s)
3. Si no cambió → usa cache (<1ms)

**Beneficios:**
- Datos de referencia siempre actualizados
- Sin downtime para agregar nuevas transacciones etiquetadas
- Caché eficiente para mejor performance

**Ver:** `docs/DYNAMIC_RELOAD.md`

### 3. Soporte Multi-Formato

**Similarity matcher soporta:**
- ✅ CSV único: `file.csv`
- ✅ Parquet único: `file.parquet`
- ✅ Directorio Parquet: `SafeTransactionResults/` (lee todos los .parquet)

**Auto-detección** basada en extensión del path en S3.

**Ver:** `docs/PARQUET_MIGRATION.md`

### 4. Schema Validation Flexible

**Validación de features:**
- 49 features esperados (num__ y cat__)
- Validación flexible: permite schema parcial
- Logging detallado de features faltantes
- No bloquea inference por features opcionales

### 5. Explicabilidad

Cada predicción incluye:
- **top_contributors**: Top 3 features más importantes
- **audit_category**: Clasificación del riesgo
- **audit_explanation**: Explicación técnica para auditoría
- **ux_copy**: Mensaje amigable para el usuario

---

## Monitoreo y Logs

### Logs Importantes

**Similarity Matching Activo:**
```
[SIMILARITY] Successfully loaded 20 valid reference vectors, shape: (20, 49)
[SIMILARITY] Checking similarity for 10 transactions (threshold: 0.90)
[SIMILARITY] Row 0: Match found (score: 0.9245, status: SAFE)
[SIMILARITY]   → Override: risk_score=70, risk_decision=Accept
```

**Similarity Desactivado (Graceful Degradation):**
```
[SIMILARITY] No .parquet files found in s3://bucket/path/
[SIMILARITY] Similarity matching will be DISABLED. Endpoint will continue processing with K-means only.
```

**Dynamic Reload:**
```
[SIMILARITY] File count changed: 20 → 25. Reloading reference data...
[SIMILARITY] Successfully loaded 25 valid reference vectors
```

### CloudWatch Metrics

Monitorea:
- **ModelLatency**: Tiempo de inferencia
- **Invocations**: Número de invocaciones
- **ModelInvocationErrors**: Errores de modelo (debería ser 0 con graceful degradation)
- **SimilarityMatchRate**: % de transacciones con similarity match

---

## Troubleshooting

### Problema: Similarity no está funcionando

**Verificar:**
1. ¿Hay archivos .parquet en S3?
   ```bash
   aws s3 ls s3://blossom-analytics-safe-dev-nv/safe_txns/similarity/data/SafeTransactionResults/
   ```

2. ¿El rol de SageMaker tiene permisos S3?
   ```json
   {
     "Effect": "Allow",
     "Action": ["s3:GetObject", "s3:ListBucket"],
     "Resource": ["arn:aws:s3:::bucket/*", "arn:aws:s3:::bucket"]
   }
   ```

3. ¿Variables de entorno configuradas?
   ```bash
   SIMILARITY_S3_BUCKET=blossom-analytics-safe-dev-nv
   SIMILARITY_S3_KEY=safe_txns/similarity/data/SafeTransactionResults/
   ```

4. ¿Hay registros SAFE/RISKY? (no solo PENDING)
   ```bash
   # Verificar contenido de archivos parquet
   ```

### Problema: Endpoint tarda mucho en responder

**Causas posibles:**
- Primera llamada: carga de modelo (~5-10s)
- Recarga de datos S3 por cambio en archivos (~2-3s)
- Muchas transacciones en batch

**Solución:**
- Usar cache: llamadas subsecuentes son rápidas (<100ms)
- Procesar en batches más pequeños
- Considerar endpoint con más recursos

### Problema: Decision Override no funciona

**Verificar:**
1. Similarity score >= 0.90?
2. statusWarning del dato S3 es SAFE o RISKY (no PENDING)?
3. Similarity matching está habilitado (DISABLE_SIMILARITY=0)?

**Ver logs:**
```
[SIMILARITY] Row X: Below threshold (score: 0.85), keeping K-means decision
```

---

## Próximos Pasos

### Para Mejorar Accuracy de Similarity

1. **Etiquetar más transacciones:**
   - Actualmente: 1 SAFE, 198 PENDING
   - Objetivo: 50+ SAFE, 50+ RISKY
   - Convirtir PENDING a SAFE/RISKY tras revisión manual

2. **Ajustar threshold:**
   - Actual: 0.90 (90%)
   - Considerar bajar a 0.85 con más datos
   - Monitorear false positives/negatives

3. **Agregar features:**
   - Incluir más features relevantes en comparación
   - Ponderar features más importantes

### Para Producción

1. **Autoscaling:**
   ```python
   predictor.update_endpoint(
       initial_instance_count=2,  # Multiple instances
       instance_type="ml.m5.xlarge"  # Más recursos
   )
   ```

2. **Monitoring:**
   - Configurar CloudWatch Alarms
   - Dashboard con métricas clave
   - Alertas de errores

3. **CI/CD:**
   - Pipeline automatizado para updates
   - Tests automáticos pre-deploy
   - Rollback automático si falla

4. **A/B Testing:**
   - Variant endpoints para testing
   - Tráfico gradual a nuevo modelo
   - Comparación de métricas

---

## Documentación Adicional

### Guías Detalladas

- **`docs/S3_PATHS_CONFIGURATION.md`** - Configuración completa de rutas S3, variables de entorno, checklist de cambios
- **`docs/GRACEFUL_DEGRADATION.md`** - Manejo de errores, escenarios cubiertos, best practices
- **`docs/DYNAMIC_RELOAD.md`** - Recarga automática, performance benchmarks, FAQ
- **`docs/PARQUET_MIGRATION.md`** - Migración CSV→Parquet, beneficios, deployment
- **`docs/SIMILARITY_INTEGRATION.md`** - Integración detallada de similarity matching
- **`docs/DEPLOYMENT_SUMMARY.md`** - Guía paso a paso de deployment
- **`docs/CHANGES_SUMMARY.md`** - Historial de cambios del proyecto

### Scripts Principales

| Script | Propósito | Documentación |
|--------|-----------|---------------|
| `endpoint/inference_rules.py` | Entry point SageMaker | Inline docstrings |
| `endpoint/similarity_matcher.py` | Motor de similarity | `docs/SIMILARITY_INTEGRATION.md` |
| `endpoint/schema_validator.py` | Validación de features | Inline docstrings |
| `endpoint/statistical_rules.py` | Reglas de fraude v8 | Inline docstrings |
| `deploy/deploy_with_sdk.py` | Deploy automatizado | `docs/DEPLOYMENT_SUMMARY.md` |

---

## Contacto y Soporte

Para preguntas, issues o contribuciones:

- **Repositorio:** GitHub - lbetancourth-dev-blossom/safe_txns_sim_endpoint
- **Branch principal:** `dev`
- **Issues:** Crear issue en GitHub
- **Documentación:** Ver carpeta `docs/`

---

## Licencia

Este proyecto es propiedad de Blossom Analytics y está sujeto a las políticas internas de la compañía.

---

## Changelog Reciente

### v3.2.0 (2026-04-16)
- ✅ Implementado Graceful Degradation para similarity matching
- ✅ Actualizado Dynamic Reload con file count tracking
- ✅ Migración completa de CSV a Parquet
- ✅ Actualizadas rutas S3 en todos los scripts de deploy
- ✅ Documentación completa en `docs/`

### v3.1.0
- ✅ Integración de Similarity Matching con S3
- ✅ Schema validation flexible
- ✅ Decision override basado en similarity

### v3.0.0
- ✅ Endpoint base con K-Means clustering
- ✅ Sistema de reglas estadísticas v8
- ✅ Política híbrida de decisiones

**Ver:** `docs/CHANGES_SUMMARY.md` para historial completo.
