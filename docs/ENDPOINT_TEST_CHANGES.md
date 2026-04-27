# Cambios Realizados - Configuración de Datos de Similitud

## Resumen
Se modificó la configuración para que el endpoint use el archivo CSV `wp_result.csv` en lugar del directorio de archivos Parquet para comparar la similitud de transacciones.

## ✅ Verificación de Compatibilidad
**El código SÍ puede leer y comparar archivos CSV desde S3.**

El módulo `similarity_matcher.py` tiene soporte completo para:
- ✅ **CSV** (archivo único): detecta archivos `.csv` automáticamente
- ✅ **Parquet** (archivo único): detecta archivos `.parquet` 
- ✅ **Parquet** (directorio): lee múltiples archivos `.parquet` de un directorio

### Flujo de Carga
1. El script detecta el formato por la extensión del archivo (`.csv`, `.parquet`, o `/` para directorio)
2. Usa la función `_load_csv_from_s3()` para leer archivos CSV
3. Parsea el campo `metadata.decisionResult` en formato JSON
4. Extrae vectores de características (`num__*` y `cat__*`)
5. Calcula similitud coseno contra las transacciones de consulta

## Archivos Modificados

### 1. `endpoint_test/similarity_matcher.py`
**Línea 69** - Se cambió la ruta por defecto de S3:
```python
# ANTES:
DEFAULT_S3_KEY = "safe_txns/similarity/data/SafeTransactionResults/"  # Parquet directory

# DESPUÉS:
DEFAULT_S3_KEY = "safe_txns/similarity/data/wp_result.csv"  # CSV file
```

### 2. `endpoint_test/inference_rules.py`
**Línea 1046** - Se actualizó la clave de S3 por defecto:
```python
# ANTES:
s3_key = os.getenv("SIMILARITY_S3_KEY", "safe_txns/similarity/data/SafeTransactionResults/")  # Parquet directory

# DESPUÉS:
s3_key = os.getenv("SIMILARITY_S3_KEY", "safe_txns/similarity/data/wp_result.csv")  # CSV file
```

## Ubicación del Archivo
- **Bucket**: `blossom-analytics-safe-dev-nv`
- **Ruta completa**: `s3://blossom-analytics-safe-dev-nv/safe_txns/similarity/data/wp_result.csv`

## Notas
- El cambio aplica para el folder `endpoint_test` usado en pruebas con el notebook `safe-txn-enpoint-test.ipynb`
- Si necesitas usar diferentes archivos de referencia, puedes:
  1. Cambiar la variable de entorno `SIMILARITY_S3_KEY`
  2. Pasar el parámetro `s3_key` o `s3_uri` directamente a las funciones
  3. Modificar las constantes `DEFAULT_S3_KEY` en los archivos

## Ejemplo de Uso
```python
from similarity_matcher import find_similar_transaction

# Usará wp_result.csv por defecto
result = find_similar_transaction(
    query_result=transaction_data,
    threshold=0.90
)

# O especificar explícitamente:
result = find_similar_transaction(
    query_result=transaction_data,
    s3_uri="s3://blossom-analytics-safe-dev-nv/safe_txns/similarity/data/wp_result.csv",
    threshold=0.90
)
```
