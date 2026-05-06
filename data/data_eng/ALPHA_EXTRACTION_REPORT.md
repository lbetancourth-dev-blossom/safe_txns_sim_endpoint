# Alpha Silver Layer Data Extraction

**Fecha**: 2026-05-06  
**Bucket**: `blossom-analytics-datalake-alpha`  
**Path**: `datalake/silver/SAFE/safetransactionresults/data/`

---

## 📊 Resumen de Datos Extraídos

### Información General

| Métrica | Valor |
|---------|-------|
| **Total Registros** | 287 |
| **Total Columnas** | 7 |
| **Tamaño Archivo** | 1.6 MB |
| **Archivos Parquet** | 8 |
| **Tamaño Total S3** | 0.12 MB |

### Rango de Fechas

```
Desde: 2026-03-27 16:56:16 UTC
Hasta: 2026-05-06 15:16:11 UTC
```

**Duración**: ~1.5 meses de datos

### Columnas

1. `uuid` - Identificador único de transacción
2. `transactionId` - ID de transacción numérico
3. `idFi` - ID de institución financiera
4. `statusWarning` - Estado de la transacción (SAFE/RISKY/PENDING)
5. `metadata` - JSON con features y resultados del modelo
6. `createdAt` - Timestamp de creación (UTC)
7. `updatedAt` - Timestamp de actualización (UTC)

---

## 🎯 Distribución por Status

| Status | Cantidad | Porcentaje |
|--------|----------|------------|
| **PENDING** | 286 | 99.7% |
| **SAFE** | 1 | 0.3% |
| **RISKY** | 0 | 0.0% |

### ⚠️ Observación Importante

**Solo 1 transacción con status SAFE** (0.3% del total).

Esto significa que:
- ✅ El filtro de similarity matcher **funcionará correctamente**
- ⚠️ **Muy pocas referencias** para similarity matching (solo 1 SAFE)
- ❌ **No hay transacciones RISKY** en el dataset actual
- 📊 La mayoría (286) están en PENDING, que el filtro **excluirá automáticamente**

### Impacto en Similarity Matching

Con el filtro actual (`statusWarning IN ["SAFE", "RISKY"]`):
- **Referencias válidas**: 1 transacción (SAFE)
- **Referencias excluidas**: 286 transacciones (PENDING)

**Recomendación**: Para tener más referencias, considerar:
1. Esperar a que más transacciones cambien de PENDING a SAFE/RISKY
2. Usar otro ambiente con más datos históricos
3. Ajustar el filtro temporalmente para incluir PENDING (si aplica)

---

## 📁 Estructura de Particiones

```
datalake/silver/SAFE/safetransactionresults/data/
├── createdat_month=2026-03/ (1 archivo, 8 registros)
├── createdat_month=2026-04/ (1 archivo, 235 registros)
└── createdat_month=2026-05/ (6 archivos, 44 registros)
```

**Distribución por mes**:
- **Marzo 2026**: 8 registros (2.8%)
- **Abril 2026**: 235 registros (81.9%)
- **Mayo 2026**: 44 registros (15.3%)

---

## 🔄 Comparación: Dev vs Alpha

| Aspecto | Dev (anterior) | Alpha (nuevo) |
|---------|----------------|---------------|
| **Bucket** | blossom-analytics-datalake-dev | blossom-analytics-datalake-alpha |
| **Total Registros** | 243 | 287 (+18%) |
| **Archivos Parquet** | 3 | 8 |
| **SAFE** | ? | 1 (0.3%) |
| **RISKY** | ? | 0 (0.0%) |
| **PENDING** | ? | 286 (99.7%) |
| **Rango Fechas** | 2026-03-27 a 2026-04-29 | 2026-03-27 a 2026-05-06 |
| **Particiones** | 2 meses | 3 meses |

---

## 🛠️ Script Actualizado

### Nuevos Parámetros

El script `extract_safe_silver.py` ahora acepta:

```bash
--bucket BUCKET    # S3 bucket name (default: blossom-analytics-datalake-dev)
--prefix PREFIX    # S3 prefix path (default: datalake/silver/SAFE/...)
```

### Uso

```bash
# Extraer de Dev (default)
python3 data_eng/extract_safe_silver.py

# Extraer de Alpha
python3 data_eng/extract_safe_silver.py \
  --bucket blossom-analytics-datalake-alpha \
  --prefix datalake/silver/SAFE/safetransactionresults/data/ \
  --output data/data_eng/SafeTxnResultsSilver_Alpha.csv

# Con otro profile
python3 data_eng/extract_safe_silver.py \
  --profile blossom-prod \
  --bucket my-bucket \
  --prefix my/path/
```

---

## 📈 Muestras de Datos

### Primeras 3 Transacciones

```
UUID                                 TransactionID  idFi  statusWarning
------------------------------------  -------------  ----  -------------
044a10e4-32e8-4bc1-a55c-c2c3143b88fb  1798449        52    SAFE
5ff45e2e-f327-4dfd-aa5a-32432d68bc83  1798800        216   PENDING
99084911-73fc-41b4-a9c8-8a4882f62806  1798841        216   PENDING
```

**Nota**: Solo la primera transacción es SAFE, las demás son PENDING.

---

## ✅ Validación

### Estructura Validada

- ✅ 7 columnas presentes
- ✅ Columna `_last_cdc_timestamp` removida
- ✅ Datos ordenados por `createdAt`
- ✅ Nombres de columnas en camelCase
- ✅ Sin valores null en campos críticos

### Metadata

Cada registro tiene un campo `metadata` con JSON que contiene:
- `numericVariables` - Features numéricas
- `categoricalVariables` - Features categóricas
- `decisionResult` - Resultados del modelo (num__, cat__, Cluster, etc.)

---

## 📝 Archivo Generado

```
📁 data/data_eng/SafeTxnResultsSilver_Alpha.csv
  - Tamaño: 1.6 MB
  - Registros: 287
  - Formato: CSV con headers
  - Encoding: UTF-8
```

**Ubicación**: `data/data_eng/SafeTxnResultsSilver_Alpha.csv`

---

## 🚨 Recomendaciones

### Para Similarity Matching en Alpha

1. **Dataset Pequeño**: Solo 1 transacción SAFE disponible
   - Similarity matching tendrá muy pocas referencias
   - Probabilidad de match será muy baja

2. **Opciones**:
   - ✅ Usar Dev environment (más datos históricos)
   - ✅ Esperar a que más transacciones cambien de PENDING
   - ⚠️ Considerar incluir PENDING temporalmente (si tiene sentido para el negocio)

3. **Monitoreo**:
   - Verificar periódicamente cuántas transacciones cambian de PENDING a SAFE/RISKY
   - Re-extraer datos cuando haya más referencias disponibles

### Para Producción

Si vas a usar Alpha en producción:
- ⚠️ **Alertar al equipo** sobre el bajo número de referencias
- 📊 **Monitorear** la tasa de match (será muy baja inicialmente)
- 🔄 **Actualizar referencias** frecuentemente (diario o semanal)

---

## 🔧 Cambios Técnicos

### Script Modificado

**Archivo**: `data_eng/extract_safe_silver.py`

**Cambios**:
1. Agregados parámetros `--bucket` y `--prefix`
2. Ambos parametrizados en función `main()`
3. Backward compatible (usa defaults si no se especifican)

**Diff**:
```python
# Antes
parquet_files = list_s3_parquet_files(s3_client, S3_BUCKET, S3_PREFIX)
df = extract_all_data(s3_client, S3_BUCKET, parquet_files)

# Después
parquet_files = list_s3_parquet_files(s3_client, args.bucket, args.prefix)
df = extract_all_data(s3_client, args.bucket, parquet_files)
```

---

## 📚 Referencias

- **Bucket Dev**: `blossom-analytics-datalake-dev`
- **Bucket Alpha**: `blossom-analytics-datalake-alpha`
- **Script**: `data_eng/extract_safe_silver.py`
- **Output**: `data/data_eng/SafeTxnResultsSilver_Alpha.csv`

---

**Generado**: 2026-05-06 10:25  
**Usuario**: lbetancourth  
**Ambiente**: Alpha (blossom-analytics-datalake-alpha)
