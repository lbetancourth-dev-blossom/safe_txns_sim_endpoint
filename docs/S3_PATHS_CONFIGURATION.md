# Rutas S3 Configurables - Safe Transactions Endpoint

Este documento lista TODAS las rutas S3 que pueden cambiar en cada script del endpoint.

## 📋 Resumen por Tipo de Ruta

### 1. **Datos de Similitud (Reference Data)**
- **Bucket:** `blossom-analytics-safe-dev-nv`
- **Key/Path:** `safe_txns/similarity/data/SafeTransactionResults/`
- **Formato:** Directorio con archivos `.parquet`
- **Propósito:** Transacciones históricas etiquetadas para comparación de similitud

### 2. **Modelo Empaquetado (Model Artifacts)**
- **Bucket:** `blossom-analytics-safe-dev-nv`
- **Key/Path:** `safe_txns/models/similarity/model.tar.gz` o `output/kmeans-similarity-endpoint/model.tar.gz`
- **Formato:** Archivo `.tar.gz`
- **Propósito:** Modelo K-means + scripts de inferencia para deployment

### 3. **Artefactos del Modelo (Model Components)**
- **Bucket:** `blossom-analytics-safe-dev-nv`
- **Key/Path:** `safe_txns/model_artifacts/`
- **Archivos:**
  - `kmeans_model.joblib`
  - `preprocessing_pipeline.joblib`
  - `selected_features.csv`
  - `centroids.csv`
- **Propósito:** Componentes individuales del modelo K-means

---

## 📂 Rutas S3 por Script

### 1️⃣ **endpoint/similarity_matcher.py**
Script principal de matching de similitud.

#### Rutas Configurables:

```python
# LÍNEA 68-69: Defaults
DEFAULT_S3_BUCKET = "blossom-analytics-safe-dev-nv"
DEFAULT_S3_KEY = "safe_txns/similarity/data/SafeTransactionResults/"  # Directorio parquet
```

#### Variables de Entorno:
```bash
SIMILARITY_S3_BUCKET=blossom-analytics-safe-dev-nv
SIMILARITY_S3_KEY=safe_txns/similarity/data/SafeTransactionResults/
```

#### Uso en el código:
- **Línea 319-320:** Lee de variables de entorno o usa defaults
- **Línea 957-958:** Main CLI también usa estas variables

#### Formatos Soportados:
- ✅ CSV único: `safe_txns/similarity/data/SafeTransactionResults.csv`
- ✅ Parquet único: `safe_txns/similarity/data/SafeTransactionResults.parquet`
- ✅ Directorio parquet: `safe_txns/similarity/data/SafeTransactionResults/` (todos los `.parquet` dentro)

#### Cambiar Ruta:
**Opción 1 - Variables de Entorno:**
```bash
export SIMILARITY_S3_BUCKET="mi-nuevo-bucket"
export SIMILARITY_S3_KEY="mi/ruta/datos/"
```

**Opción 2 - Modificar Código (líneas 68-69):**
```python
DEFAULT_S3_BUCKET = "mi-nuevo-bucket"
DEFAULT_S3_KEY = "mi/ruta/datos/"
```

**Opción 3 - Argumentos CLI:**
```bash
python similarity_matcher.py --s3-bucket mi-bucket --s3-key mi/ruta/
# o
python similarity_matcher.py --s3-uri s3://mi-bucket/mi/ruta/
```

---

### 2️⃣ **endpoint/inference_rules.py**
Script de inferencia del endpoint de SageMaker.

#### Rutas Configurables:

```python
# LÍNEA 1045-1046: Configuración de similitud
s3_bucket = os.getenv("SIMILARITY_S3_BUCKET", "blossom-analytics-safe-dev-nv")
s3_key = os.getenv("SIMILARITY_S3_KEY", "safe_txns/similarity/data/SafeTransactionResults/")
```

#### Variables de Entorno:
```bash
SIMILARITY_S3_BUCKET=blossom-analytics-safe-dev-nv
SIMILARITY_S3_KEY=safe_txns/similarity/data/SafeTransactionResults/
SIMILARITY_THRESHOLD=0.90  # Threshold de similitud
DISABLE_SIMILARITY=0       # 1 para desactivar similarity
```

#### Cambiar Ruta:
Se debe configurar en el **deployment** (ver scripts deploy más abajo).

---

### 3️⃣ **endpoint/validate_s3_data.py**
Script de validación de datos en S3.

#### Rutas Configurables:
```python
# Se pasa como argumento CLI - NO tiene defaults hardcoded
```

#### Uso:
```bash
python validate_s3_data.py --s3-uri s3://bucket/path/file.csv --output report.json
```

#### Formatos Soportados:
- ✅ CSV: `s3://bucket/path/file.csv`
- ❌ No soporta parquet directamente

---

### 4️⃣ **deploy/deploy_similarity_endpoint.py**
Script para deployment completo del endpoint.

#### Rutas Configurables:

```python
# LÍNEA 15-16: Bucket y prefijos
BUCKET = "blossom-analytics-safe-dev-nv"
S3_MODEL_PREFIX = "safe_txns/models/similarity"

# LÍNEA 20: Artefactos del modelo
ARTIFACTS_S3_PREFIX = "safe_txns/model_artifacts"

# LÍNEA 111: Variable de entorno para similarity (DEPRECATED - usar nueva ruta)
'SIMILARITY_S3_KEY': 'safe_txns/data/similarity/SafeTransactionResults.csv'
```

#### ⚠️ **NOTA IMPORTANTE:**
La línea 111 tiene una ruta **VIEJA** (CSV):
```python
'SIMILARITY_S3_KEY': 'safe_txns/data/similarity/SafeTransactionResults.csv'
```

**Debe cambiarse a la ruta NUEVA (Parquet directory):**
```python
'SIMILARITY_S3_KEY': 'safe_txns/similarity/data/SafeTransactionResults/'
```

#### Rutas Generadas:
```python
# Model upload path (línea 88)
model_s3_uri = f"s3://{BUCKET}/{S3_MODEL_PREFIX}/model.tar.gz"
# Ejemplo: s3://blossom-analytics-safe-dev-nv/safe_txns/models/similarity/model.tar.gz
```

#### Cambiar Rutas:
Modificar las constantes en las líneas 15-20:
```python
BUCKET = "mi-nuevo-bucket"
S3_MODEL_PREFIX = "mi/ruta/modelos"
ARTIFACTS_S3_PREFIX = "mi/ruta/artefactos"
```

---

### 5️⃣ **deploy/deploy_notebook.py**
Script simplificado para deployment desde notebook.

#### Rutas Configurables:

```python
# LÍNEA 13: Model data
model_data = "s3://blossom-analytics-safe-dev-nv/output/kmeans-similarity-endpoint/model.tar.gz"

# LÍNEA 30-31: Variables de entorno (DEPRECATED - usar nueva ruta)
"SIMILARITY_S3_BUCKET": "blossom-analytics-safe-dev-nv",
"SIMILARITY_S3_KEY": "safe_txns/data/similarity/SafeTransactionResults.csv",
```

#### ⚠️ **NOTA IMPORTANTE:**
Las líneas 30-31 tienen rutas **VIEJAS** (CSV):
```python
"SIMILARITY_S3_KEY": "safe_txns/data/similarity/SafeTransactionResults.csv"
```

**Debe cambiarse a la ruta NUEVA (Parquet directory):**
```python
"SIMILARITY_S3_KEY": "safe_txns/similarity/data/SafeTransactionResults/"
```

#### Cambiar Rutas:
```python
model_data = "s3://mi-bucket/mi/ruta/modelo.tar.gz"
"SIMILARITY_S3_BUCKET": "mi-bucket",
"SIMILARITY_S3_KEY": "mi/ruta/datos/",
```

---

### 6️⃣ **deploy/deploy_with_sdk.py**
Script de deployment con SageMaker SDK.

#### Rutas Configurables:

```python
# LÍNEA 6: Model data
model_data = "s3://blossom-analytics-safe-dev-nv/output/kmeans-similarity-endpoint/model.tar.gz"

# LÍNEA 23-24: Variables de entorno (DEPRECATED - usar nueva ruta)
"SIMILARITY_S3_BUCKET": "blossom-analytics-safe-dev-nv",
"SIMILARITY_S3_KEY": "safe_txns/data/similarity/SafeTransactionResults.csv",
```

#### ⚠️ **NOTA IMPORTANTE:**
Las líneas 23-24 tienen rutas **VIEJAS** (CSV):
```python
"SIMILARITY_S3_KEY": "safe_txns/data/similarity/SafeTransactionResults.csv"
```

**Debe cambiarse a la ruta NUEVA (Parquet directory):**
```python
"SIMILARITY_S3_KEY": "safe_txns/similarity/data/SafeTransactionResults/"
```

#### Cambiar Rutas:
```python
model_data = "s3://mi-bucket/mi/ruta/modelo.tar.gz"
"SIMILARITY_S3_BUCKET": "mi-bucket",
"SIMILARITY_S3_KEY": "mi/ruta/datos/",
```

---

## 🔧 Cambios Pendientes Críticos

### ⚠️ Scripts de Deploy con Rutas VIEJAS (CSV)

Los siguientes archivos tienen **rutas desactualizadas** que apuntan al CSV viejo:

1. **deploy/deploy_similarity_endpoint.py** - Línea 111
2. **deploy/deploy_notebook.py** - Línea 31
3. **deploy/deploy_with_sdk.py** - Línea 24

**ANTES (CSV - VIEJO):**
```python
"SIMILARITY_S3_KEY": "safe_txns/data/similarity/SafeTransactionResults.csv"
```

**DESPUÉS (Parquet directory - ACTUAL):**
```python
"SIMILARITY_S3_KEY": "safe_txns/similarity/data/SafeTransactionResults/"
```

### Impacto:
Si deployeas con estos scripts SIN actualizar, el endpoint buscará el CSV viejo que **ya no existe**, y:
- ✅ Gracias al graceful degradation: NO crasheará
- ⚠️ PERO: Similarity matching estará **DESACTIVADO**
- 📝 Logs mostrarán: "No .parquet files found in s3://..."

---

## 📊 Estructura Actual de S3

### Bucket: `blossom-analytics-safe-dev-nv`

```
blossom-analytics-safe-dev-nv/
│
├── safe_txns/
│   ├── similarity/
│   │   └── data/
│   │       └── SafeTransactionResults/          ← DATOS ACTUALES (Parquet)
│   │           ├── part-00000.parquet
│   │           ├── part-00001.parquet
│   │           └── ... (20 archivos totales)
│   │
│   ├── models/
│   │   └── similarity/
│   │       └── model.tar.gz                     ← Modelo empaquetado
│   │
│   ├── model_artifacts/                         ← Artefactos individuales
│   │   ├── kmeans_model.joblib
│   │   ├── preprocessing_pipeline.joblib
│   │   ├── selected_features.csv
│   │   └── centroids.csv
│   │
│   └── data/
│       └── similarity/
│           └── SafeTransactionResults.csv       ← VIEJO (Ya no se usa)
│
└── output/
    └── kmeans-similarity-endpoint/
        └── model.tar.gz                         ← Modelo (ruta alternativa)
```

---

## 🔄 Migración de Rutas

### Si cambias el bucket o path de datos de similitud:

#### 1. Actualizar archivos de endpoint:
```bash
# endpoint/similarity_matcher.py (líneas 68-69)
DEFAULT_S3_BUCKET = "nuevo-bucket"
DEFAULT_S3_KEY = "nueva/ruta/"

# endpoint/inference_rules.py (líneas 1045-1046)
# Estos usan os.getenv() con defaults, así que:
# - O actualizas el default en el código
# - O configuras las variables de entorno en el deployment
```

#### 2. Actualizar scripts de deploy:
```bash
# deploy/deploy_similarity_endpoint.py (líneas 15, 111)
BUCKET = "nuevo-bucket"
'SIMILARITY_S3_KEY': 'nueva/ruta/'

# deploy/deploy_notebook.py (líneas 13, 30-31)
model_data = "s3://nuevo-bucket/..."
"SIMILARITY_S3_BUCKET": "nuevo-bucket"
"SIMILARITY_S3_KEY": "nueva/ruta/"

# deploy/deploy_with_sdk.py (líneas 6, 23-24)
model_data = "s3://nuevo-bucket/..."
"SIMILARITY_S3_BUCKET": "nuevo-bucket"
"SIMILARITY_S3_KEY": "nueva/ruta/"
```

#### 3. Re-deploy el endpoint:
```bash
python deploy/deploy_with_sdk.py
# o
python deploy/deploy_similarity_endpoint.py
```

---

## 🧪 Testing con Diferentes Rutas

### Opción 1: Variables de Entorno (Recomendado)
```bash
export SIMILARITY_S3_BUCKET="mi-bucket-test"
export SIMILARITY_S3_KEY="test/datos/"
python endpoint/similarity_matcher.py --test
```

### Opción 2: Argumentos CLI
```bash
python endpoint/similarity_matcher.py \
  --s3-bucket mi-bucket-test \
  --s3-key test/datos/
```

### Opción 3: S3 URI Completa
```bash
python endpoint/similarity_matcher.py \
  --s3-uri s3://mi-bucket-test/test/datos/
```

---

## ✅ Checklist de Cambio de Rutas S3

Cuando cambies rutas S3, verifica estos archivos:

- [ ] `endpoint/similarity_matcher.py` (líneas 68-69)
- [ ] `endpoint/inference_rules.py` (líneas 1045-1046)
- [ ] `deploy/deploy_similarity_endpoint.py` (líneas 15-16, 111)
- [ ] `deploy/deploy_notebook.py` (líneas 13, 30-31)
- [ ] `deploy/deploy_with_sdk.py` (líneas 6, 23-24)
- [ ] Copiar/migrar datos al nuevo bucket/path en S3
- [ ] Actualizar permisos IAM para el nuevo bucket
- [ ] Re-deploy el endpoint con nuevas configuraciones
- [ ] Verificar logs del endpoint tras deployment
- [ ] Probar inference con transacción de prueba

---

## 📝 Recomendaciones

### 1. Usar Variables de Entorno en Deployment
**Mejor práctica:** No hardcodear rutas en código, usar env vars.

```python
# En scripts de deploy
env = {
    "SIMILARITY_S3_BUCKET": os.getenv("SIMILARITY_S3_BUCKET", "default-bucket"),
    "SIMILARITY_S3_KEY": os.getenv("SIMILARITY_S3_KEY", "default/path/"),
}
```

### 2. Mantener Consistencia
Todos los scripts de deploy deben usar **la misma ruta**:
```
safe_txns/similarity/data/SafeTransactionResults/  ← Parquet directory
```

### 3. Documentar Cambios
Si cambias rutas en producción, documenta:
- ¿Qué ruta cambió?
- ¿Por qué cambió?
- ¿Cuándo se migró?
- ¿Hay backups de datos viejos?

### 4. Testing
Siempre probar en ambiente de desarrollo antes de cambiar producción:
```bash
# Dev
SIMILARITY_S3_BUCKET=blossom-analytics-safe-dev-nv

# Staging
SIMILARITY_S3_BUCKET=blossom-analytics-safe-staging

# Prod
SIMILARITY_S3_BUCKET=blossom-analytics-safe-prod
```

---

## 🆘 Troubleshooting

### Problema: "No .parquet files found in s3://..."
**Causa:** Ruta incorrecta o datos no existen.  
**Solución:**
1. Verificar que el path exista en S3:
   ```bash
   aws s3 ls s3://blossom-analytics-safe-dev-nv/safe_txns/similarity/data/SafeTransactionResults/
   ```
2. Verificar permisos IAM del rol de SageMaker
3. Verificar variables de entorno del endpoint

### Problema: "Permission denied" al acceder S3
**Causa:** Rol de SageMaker no tiene permisos.  
**Solución:** Agregar policy al rol:
```json
{
  "Effect": "Allow",
  "Action": ["s3:GetObject", "s3:ListBucket"],
  "Resource": [
    "arn:aws:s3:::bucket-name/*",
    "arn:aws:s3:::bucket-name"
  ]
}
```

### Problema: Similarity está desactivado en producción
**Causa:** Scripts de deploy tienen rutas viejas (CSV).  
**Solución:** Actualizar líneas indicadas en sección "Cambios Pendientes" y re-deploy.

---

## 📞 Resumen Ejecutivo

### Rutas S3 Principales:

1. **Datos de Similitud (ACTUAL):**  
   `s3://blossom-analytics-safe-dev-nv/safe_txns/similarity/data/SafeTransactionResults/`

2. **Modelo Empaquetado:**  
   `s3://blossom-analytics-safe-dev-nv/safe_txns/models/similarity/model.tar.gz`

3. **Artefactos del Modelo:**  
   `s3://blossom-analytics-safe-dev-nv/safe_txns/model_artifacts/`

### Archivos a Actualizar (URGENTE):
- `deploy/deploy_similarity_endpoint.py` - línea 111
- `deploy/deploy_notebook.py` - línea 31  
- `deploy/deploy_with_sdk.py` - línea 24

Cambiar de CSV a Parquet directory path.
