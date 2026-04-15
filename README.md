# SAFE ML Transactions Endpoint

## Descripción General

Este proyecto implementa un **endpoint de predicción en Amazon SageMaker** para detección de fraude en transacciones financieras. El sistema combina un modelo de clustering K-Means con un sistema de reglas estadísticas para evaluar el riesgo de cada transacción en tiempo real o por lotes.

### Características Principales

- **Modelo de ML**: K-Means clustering para detectar patrones anómalos en transacciones
- **Sistema de Reglas**: Reglas estadísticas (v8) para evaluación de riesgo basada en comportamiento histórico
- **Política Híbrida**: Combinación de clustering + reglas para decisiones más robustas
- **Scoring en Tiempo Real**: Capacidad de procesar transacciones individuales o en lote
- **Decisiones Multinivel**: Accept, User Auth, Admin Review, Reject

---

## Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────┐
│                    Input: CSV/JSON                          │
│             (Transacciones desde S3)                        │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              SageMaker Endpoint                             │
│         (ml.m5.large, SKLearn Framework)                    │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  1. Validación y Preprocesamiento                    │  │
│  │     - Limpieza de datos                              │  │
│  │     - Derivación de features temporales              │  │
│  │     - Transformaciones numéricas/categóricas         │  │
│  └──────────────────────────────────────────────────────┘  │
│                         │                                   │
│                         ▼                                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  2. K-Means Clustering                               │  │
│  │     - Asignación de cluster                          │  │
│  │     - Cálculo de distancia al centroide             │  │
│  └──────────────────────────────────────────────────────┘  │
│                         │                                   │
│                         ▼                                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  3. Sistema de Reglas Estadísticas (v8)            │  │
│  │     - Evaluación de 12 reglas de fraude             │  │
│  │     - Scoring normalizado (0-100)                    │  │
│  └──────────────────────────────────────────────────────┘  │
│                         │                                   │
│                         ▼                                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  4. Política Híbrida y Decisión Final              │  │
│  │     - Combinación de cluster + reglas                │  │
│  │     - Clasificación de riesgo                        │  │
│  │     - Generación de explicaciones                    │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                Output: JSON/CSV                              │
│  - Cluster, Distancia, Risk Score, Decisión                 │
│  - Features preprocesados                                    │
│  - Explicaciones y recomendaciones UX                        │
└─────────────────────────────────────────────────────────────┘
```

---

## Contenido del Repositorio

### Estructura de Archivos

```
safe_txns_sim_endpoint/
│
├── safe-txn-enpoint.ipynb      # Notebook principal para deploy y pruebas
│
└── endpoint/
    ├── inference_rules.py      # Script principal de inferencia para SageMaker
    └── statistical_rules.py    # Sistema de reglas estadísticas v8
```

### Descripción de Scripts

#### 1. `safe-txn-enpoint.ipynb`

**Propósito**: Notebook interactivo para el ciclo completo de deploy y testing del endpoint.

**Funcionalidades**:
- **Step 1**: Descarga y empaquetado de artefactos del modelo desde S3
  - `kmeans_model.joblib` (modelo K-Means)
  - `preprocessing_pipeline.joblib` (pipeline de preprocesamiento)
  - `selected_features.csv` (features seleccionados)
  - `centroids.csv` (centroides del clustering)
  - `kmeans_artifacts.json` (metadata del modelo)
  
- **Step 2**: Upload de `model.tar.gz` a S3
  
- **Step 3**: Deploy del endpoint en SageMaker
  - Framework: SKLearn 1.2-1
  - Instance: ml.m5.large
  - Entry point: `inference_rules.py`
  
- **Step 4**: Testing del endpoint
  - Carga de datos desde S3
  - Invocación del endpoint con payload CSV
  - Guardado de resultados en S3

**Versiones del Endpoint**:
- **V2** (deprecated): `final-safe-txns-endpoint`
- **V3** (actual): `data-safe-txns-endpoint`

---

#### 2. `endpoint/inference_rules.py`

**Propósito**: Script principal de inferencia ejecutado por SageMaker. Implementa las funciones `model_fn`, `input_fn`, `predict_fn` y `output_fn` requeridas por el framework.

**Componentes Clave**:

##### A. Validación y Preprocesamiento
- **Validación de tipos de datos**: Conversión y validación de 60+ columnas según `DTYPE_MAP`
- **Manejo de timestamps**: Parsing estricto de fechas con múltiples formatos
- **Derivación de features temporales**: 
  - Cíclicos: `hour_sin`, `hour_cos`, `day_of_week_sin`, `day_of_week_cos`, `month_sin`, `month_cos`
  - Binarios: `weekend`, `is_night`
- **Modes de validación**:
  - `strict`: Falla si hay errores
  - `filter`: Descarta filas inválidas
  - `coerce`: Imputa valores por defecto

##### B. K-Means Clustering
- Carga del modelo entrenado
- Transformación de features según pipeline de preprocesamiento
- Asignación de cluster y cálculo de distancia euclidiana al centroide
- Detección de outliers basada en distancia

##### C. Sistema de Reglas Estadísticas (v8)
Integración opcional del módulo `statistical_rules.py` con 12 reglas de fraude:

**Reglas Implementadas**:
1. ~~**R1**: Monto vs promedio histórico del usuario~~ (desactivada)
2. **R2**: Transacción nocturna (+20 pts)
3. **R3**: Primera transacción al destinatario en 6h (+30 pts)
4. **R4**: Cancelaciones recientes (hasta +20 pts)
5. **R5**: Acciones sospechosas en sesión (hasta +25 pts)
6. **R6**: Monto alto vs perfil histórico bajo (hasta +20 pts)
7. **R7**: Burst de transacciones en 5min (hasta +35 pts)
8. **R8**: Historial con destinatario (hasta +15 pts)
9. ~~**R9**: Cambios en datos de contacto~~ (desactivada)
10. **R10**: Fin de semana (+10 pts)
11. **R11**: Monto desproporcionado vs promedio CU (hasta +45 pts)
12. **R12**: Usuario nuevo (hasta +15 pts)

**Normalización**: Piecewise mapping de score raw (0-295) a score normalizado (0-100) sin hard cap

##### D. Política Híbrida
Combina información del cluster y reglas para decisión final:

**Decisiones por Score**:
- `< 70`: **Accept** - Transacción normal
- `70-79`: **User Auth** - Requiere autenticación adicional
- `80-89`: **Admin Review** - Revisión manual requerida
- `≥ 90`: **Reject** - Transacción bloqueada

##### E. Output Estructurado
Retorna JSON con:
- **Features preprocesados**: Todas las columnas `num__*` y `cat__*` del pipeline
- **Predicciones ML**: `Cluster`, `Distance_to_Centroid`
- **Scoring**: `risk_score`, `risk_decision`, `is_outlier`
- **Explicaciones**: 
  - `top_contributors`: Top 3 features que más aportan al cluster
  - `audit_category`: Clasificación del riesgo
  - `audit_explanation`: Explicación técnica para auditoría
  - `ux_copy`: Texto amigable para mostrar al usuario

**Configuraciones**:
- Variable de entorno `DISABLE_RULES=1` para desactivar reglas estadísticas
- Tolerancia a features faltantes en el pipeline
- Manejo robusto de ColumnTransformer de sklearn

---

#### 3. `endpoint/statistical_rules.py`

**Propósito**: Módulo independiente para scoring de transacciones basado en reglas de negocio. Puede ejecutarse standalone o integrarse con el endpoint.

**Características**:

##### Configuración de Reglas (v8)
- Reducción de peso en reglas sensibles vs v7:
  - R1: ~75% de puntos originales
  - R3: 30 pts (era 40 en v7)
- R11 mantiene peso fuerte (hasta 45 pts) para montos desproporcionados

##### Funciones Principales

**`score_transaction_v8(transaction: Dict) -> Dict`**:
- Evalúa una transacción individual
- Retorna diccionario con:
  - Contribución por regla (`rule_1` a `rule_12`)
  - `risk_score_raw`, `risk_score_clipped`, `risk_score_normalized`
  - `risk_decision`, `explanation`

**`score_dataframe_v8(df: pd.DataFrame) -> pd.DataFrame`**:
- Procesa DataFrame completo
- Auto-detección de columna de ID
- Retorna DF con todas las columnas de scoring

##### Normalización Piecewise
```python
if raw <= 90:
    score = raw
elif 90 < raw < R_MAX (295):
    score = 90 + (raw - 90) × (10 / (R_MAX - 90))
else:
    score = 100
```

**Propósito**: Preservar los thresholds de decisión (70/80/90) mientras mapea scores extremos sin truncar información.

##### Uso Standalone
```bash
# Desde CSV
python statistical_rules.py --csv_in data.csv --out scored_output.csv

# Desde Excel
python statistical_rules.py --excel_insumos Insumos.xlsx --sheet_name Fraud --out fraud_scored.csv
```

---

## Flujo de Datos

### 1. Preparación de Datos de Entrada

**Formato esperado**: CSV con mínimo estas columnas:
- `TransactionID`, `amount`
- Features temporales O `createdAtTxns` timestamp
- Features de comportamiento histórico del usuario
- Features de sesión y contexto

**Ejemplo**:
```csv
TransactionID,amount,createdAtTxns,user_type,count_user_cancelled_txn_in_last_week,...
12345,1500.00,2026-04-15T14:30:00Z,personal,0,...
```

### 2. Invocación del Endpoint

```python
import boto3
import pandas as pd
import io

# Cargar datos
df = pd.read_csv("transactions.csv")

# Convertir a CSV en memoria
csv_buffer = io.StringIO()
df.to_csv(csv_buffer, header=True, index=False)
payload = csv_buffer.getvalue()

# Invocar endpoint
runtime = boto3.client("sagemaker-runtime", region_name="us-east-1")
response = runtime.invoke_endpoint(
    EndpointName="data-safe-txns-endpoint",
    ContentType="text/csv",
    Body=payload
)

# Parsear resultados
result = response['Body'].read().decode('utf-8')
predictions = json.loads(result)
df_result = pd.DataFrame(predictions)
```

### 3. Interpretación de Resultados

**Columnas de Output**:

| Columna | Descripción | Valores |
|---------|-------------|---------|
| `Cluster` | Cluster asignado por K-Means | 0-N (entero) |
| `Distance_to_Centroid` | Distancia euclidiana al centroide | Float ≥ 0 |
| `risk_score` | Score de riesgo normalizado | 0-100 |
| `risk_decision` | Decisión recomendada | Accept, User Auth, Admin Review, Reject |
| `is_outlier` | Flag de outlier (score ≥ 70) | 0 ó 1 |
| `top_contributors` | Top 3 features más relevantes | String separado por " \| " |
| `audit_category` | Categoría de auditoría | Normal, Low Risk, Medium Risk, etc. |
| `audit_explanation` | Explicación técnica | Texto descriptivo |
| `ux_copy` | Mensaje para usuario final | Texto amigable |

**Ejemplo de interpretación**:
```json
{
  "Cluster": 2,
  "Distance_to_Centroid": 45.3,
  "risk_score": 85,
  "risk_decision": "Admin Review",
  "is_outlier": 1,
  "top_contributors": "amount (high) | is_night | count_all_txn_last_5m",
  "audit_category": "High Risk - Multiple Flags",
  "audit_explanation": "R2: nighttime +20 | R7: 3 txns/5m +20 | R11: 3.5× CU +30",
  "ux_copy": "Esta transacción requiere revisión adicional por seguridad."
}
```

---

## Deployment

### Prerrequisitos

1. **Cuenta AWS** con permisos para SageMaker y S3
2. **Bucket S3**: `blossom-analytics-safe-dev-nv` (o modificar en el código)
3. **Artefactos del modelo** en S3:
   - `output/kmeans/kmeans_analysis/artifact/kmeans_model.joblib`
   - `output/preprocessing/preprocessing_pipeline.joblib`
   - `output/feature_selection/selected_features.csv`
   - `output/kmeans/centroids/centroids.csv`
   - `output/kmeans/kmeans_analysis/artifact/kmeans_artifacts.json`

### Pasos de Deploy

1. **Empaquetar artefactos**:
   ```bash
   # Ejecutar celdas del notebook Step 1
   # Esto descarga archivos de S3 y crea model.tar.gz
   ```

2. **Subir a S3**:
   ```bash
   # Ejecutar celda del notebook Step 2
   # Upload de model.tar.gz a S3
   ```

3. **Deploy del endpoint**:
   ```python
   from sagemaker.sklearn.model import SKLearnModel
   
   sk_model = SKLearnModel(
       model_data="s3://blossom-analytics-safe-dev-nv/output/kmeans-endpoint-last3/model.tar.gz",
       role=role,
       entry_point="inference_rules.py",
       source_dir="endpoint",
       framework_version="1.2-1"
   )
   
   predictor = sk_model.deploy(
       initial_instance_count=1,
       instance_type="ml.m5.large",
       endpoint_name="data-safe-txns-endpoint"
   )
   ```

### Verificación del Deploy

```python
import boto3

sm = boto3.client("sagemaker")
response = sm.describe_endpoint(EndpointName="data-safe-txns-endpoint")
print(f"Status: {response['EndpointStatus']}")

# Debe mostrar: Status: InService
```

### Actualización del Endpoint

Para actualizar con un nuevo modelo:

1. Crear nuevo `model.tar.gz` con artefactos actualizados
2. Subir a S3 con nueva ruta
3. Eliminar endpoint anterior:
   ```python
   client = boto3.client("sagemaker")
   client.delete_endpoint(EndpointName="data-safe-txns-endpoint")
   client.delete_endpoint_config(EndpointConfigName="data-safe-txns-endpoint")
   ```
4. Hacer nuevo deploy con nuevo `model_data`

---

## Testing y Validación

### Test Básico

```python
# Test con datos de ejemplo en S3
input_key = "real_time/real-time-col-amucu.csv"
output_key = "real_time/output_endpoint/result-test.csv"

# Ejecutar celdas de Step 4 en el notebook
```

### Test de Performance

```python
import time

start = time.time()
# ... invoke_endpoint ...
elapsed = time.time() - start

print(f"Tiempo de respuesta: {elapsed:.2f}s para {len(df)} transacciones")
print(f"Throughput: {len(df)/elapsed:.1f} txns/sec")
```

### Validación de Output

```python
import pandas as pd

df_result = pd.DataFrame(predictions)

# Verificar columnas requeridas
required_cols = ['Cluster', 'Distance_to_Centroid', 'risk_score', 'risk_decision']
assert all(c in df_result.columns for c in required_cols)

# Verificar rangos de valores
assert df_result['risk_score'].between(0, 100).all()
assert df_result['risk_decision'].isin(['Accept', 'User Auth', 'Admin Review', 'Reject']).all()
assert df_result['is_outlier'].isin([0, 1]).all()
```

---

## Configuración Avanzada

### Variables de Entorno

En el endpoint de SageMaker:
```python
# Desactivar reglas estadísticas
os.environ['DISABLE_RULES'] = '1'
```

### Modos de Validación

En `inference_rules.py`, modificar el modo de validación:

```python
# modo="strict" - Falla si hay errores
# modo="filter" - Descarta filas inválidas (default)
# modo="coerce" - Imputa valores por defecto

df_clean = validate_gate(df_input, mode="filter")
```

### Personalización de Reglas

Para ajustar thresholds en `statistical_rules.py`:

```python
# Modificar configuración de reglas
R1_THRESHOLDS = [0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 3.0, 5.0]
R1_POINTS = [2, 4, 6, 9, 14, 19, 26, 34, 45]

# Modificar clasificación de riesgo
def classify_risk(score: int) -> str:
    if score >= 90:
        return "Reject"
    elif score >= 80:
        return "Admin Review"
    elif score >= 70:
        return "User Auth"
    else:
        return "Accept"
```

---

## Troubleshooting

### Endpoint no arranca

**Síntoma**: `EndpointStatus: Failed`

**Solución**: Revisar logs en CloudWatch:
```python
import boto3
sm = boto3.client("sagemaker")
response = sm.describe_endpoint(EndpointName="data-safe-txns-endpoint")
if "FailureReason" in response:
    print(response["FailureReason"])
```

**Causas comunes**:
- `model.tar.gz` corrupto o mal estructurado
- Falta `inference_rules.py` o `statistical_rules.py` en el tarball
- Incompatibilidad de versión de sklearn

### Error de features faltantes

**Síntoma**: `KeyError: 'feature_name'`

**Solución**: El script maneja features faltantes automáticamente con valores por defecto (0.0). Verificar que el input CSV tenga al menos:
- `amount`
- `TransactionID` (o ID equivalente)
- `createdAtTxns` O todos los features temporales derivados

### Scores inesperados

**Síntoma**: Todos los scores = 0 o muy bajos

**Causas**:
1. Reglas desactivadas: Verificar `DISABLE_RULES` no esté en `1`
2. Features no coinciden con los esperados por las reglas
3. Datos históricos del usuario vacíos (todos los contadores = 0)

**Debug**:
```python
# Activar logs detallados
print("[DEBUG] Score breakdown:")
for rule_num in range(1, 13):
    print(f"  Rule {rule_num}: {result[f'rule_{rule_num}']} pts")
print(f"  Raw total: {result['risk_score_raw']}")
print(f"  Normalized: {result['risk_score_normalized']}")
```

### Problemas de performance

**Síntoma**: Tiempos de respuesta > 5 segundos

**Optimizaciones**:
1. Usar batch size óptimo (100-1000 transacciones)
2. Considerar instancia más grande: `ml.m5.xlarge`
3. Auto-scaling para carga variable

---

## Mantenimiento

### Monitoreo

**Métricas recomendadas**:
- Latencia P50, P90, P99
- Throughput (invocaciones/min)
- Distribución de decisiones (% Accept, User Auth, Admin Review, Reject)
- Tasa de outliers

### Reentrenamiento del Modelo

Cuando el modelo K-Means necesite actualización:

1. Reentrenar con datos recientes
2. Generar nuevos artefactos (centroides, pipeline, etc.)
3. Crear nuevo `model.tar.gz`
4. Deploy a nuevo endpoint o actualización in-place
5. A/B testing entre versiones

### Versionado

**Estrategia recomendada**:
```
s3://bucket/output/kmeans-endpoint-vYYYYMMDD/model.tar.gz
Endpoint name: data-safe-txns-endpoint-vYYYYMMDD
```

Mantener registro de cambios entre versiones en este README.

---

## Limitaciones Conocidas

1. **Features temporales**: Requiere timestamp válido O features pre-derivados
2. **Datos históricos**: Depende de features agregados del usuario (últimos 6 meses)
3. **Batch processing**: No recomendado para batches > 10,000 transacciones (dividir en chunks)
4. **Cold start**: Primera invocación ~10-15s (cargas del modelo)

---

## Roadmap

### Mejoras Futuras
- [ ] Agregar modelo de XGBoost para comparación
- [ ] Implementar explicabilidad con SHAP values
- [ ] API REST wrapper para integraciones más simples
- [ ] Dashboard en tiempo real con métricas del endpoint
- [ ] Auto-tuning de thresholds basado en feedback

---

## Contacto y Soporte

**Bucket S3**: `blossom-analytics-safe-dev-nv`  
**Región**: `us-east-1`  
**Endpoint actual**: `data-safe-txns-endpoint` (V3)

Para soporte técnico o reportar issues, contactar al equipo de ML Engineering.

---

## Licencia

Proyecto interno - Todos los derechos reservados.

---

**Última actualización**: Abril 2026  
**Versión del endpoint**: V3 (data-safe-txns-endpoint)  
**Versión de reglas**: v8
