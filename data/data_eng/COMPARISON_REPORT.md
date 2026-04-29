# Comparación de Archivos CSV: SafeTransactionResults

**Fecha**: 2026-04-29  
**Archivos comparados**:
1. `_SafeTransactionResults__202604291015.csv`
2. `SafeTxnResultsSilver.csv`

---

## Resumen Ejecutivo

✅ **LOS ARCHIVOS CONTIENEN EXACTAMENTE LOS MISMOS DATOS**

La única diferencia es el **formato del timestamp** (timezone).

---

## Comparación Detallada

### 1. Estructura

| Métrica | Archivo 1 | Archivo 2 | Status |
|---------|-----------|-----------|--------|
| **Filas** | 243 | 243 | ✅ Idéntico |
| **Columnas** | 7 | 7 | ✅ Idéntico |
| **Tamaño** | 1.32 MB | 1.32 MB | ✅ Idéntico |

**Columnas** (ambos archivos):
- uuid
- transactionId
- idFi
- statusWarning
- metadata
- createdAt
- updatedAt

---

### 2. Contenido de Datos

| Aspecto | Resultado |
|---------|-----------|
| **UUIDs únicos** | 243 (100% overlap) |
| **Transacciones comunes** | 243 (todas) |
| **Duplicados** | 0 en ambos |
| **Registros únicos Archivo 1** | 0 |
| **Registros únicos Archivo 2** | 0 |

✅ **Ambos archivos contienen exactamente las mismas 243 transacciones**

---

### 3. Rango de Fechas

**Archivo 1** (_SafeTransactionResults__202604291015.csv):
```
2026-03-27 11:56:16.882 -0500  →  2026-04-29 08:40:06.300 -0500
```

**Archivo 2** (SafeTxnResultsSilver.csv):
```
2026-03-27 16:56:16.882000+00:00  →  2026-04-29 13:40:06.300000+00:00
```

**Nota**: Las fechas son las mismas, solo representadas en diferentes timezones.

---

### 4. Diferencias Encontradas

#### ❗ Única Diferencia: Formato de Timestamp

**Archivo 1** (`_SafeTransactionResults__202604291015.csv`):
- Formato: `YYYY-MM-DD HH:MM:SS.fff -0500`
- Timezone: **UTC-05:00** (hora local Colombia/Bogotá)
- Ejemplo: `2026-03-27 11:56:16.882 -0500`

**Archivo 2** (`SafeTxnResultsSilver.csv`):
- Formato: `YYYY-MM-DD HH:MM:SS.ffffff+00:00`
- Timezone: **UTC** (hora universal coordinada)
- Ejemplo: `2026-03-27 16:56:16.882000+00:00`

**Conversión**:
```
Archivo 1: 2026-03-27 11:56:16.882 -0500
           ↓ (+ 5 horas)
Archivo 2: 2026-03-27 16:56:16.882000+00:00
```

✅ **Los timestamps representan el mismo momento en el tiempo**, solo expresados en diferentes timezones.

---

### 5. Campos de Metadata

**Comparación del campo `metadata` (JSON)**:

Ambos archivos tienen **exactamente el mismo contenido** en el campo metadata:
- Mismos valores numéricos
- Mismos valores categóricos
- Mismos resultados del modelo (risk_score, risk_decision, etc.)
- Mismas explicaciones y categorías de auditoría

**Ejemplo transactionId 1798800**:
- uuid: `5ff45e2e-f327-4dfd-aa5a-32432d68bc83` ✅ Idéntico
- transactionId: `1798800` ✅ Idéntico
- idFi: `216` ✅ Idéntico
- statusWarning: `PENDING` ✅ Idéntico
- risk_score: `72` ✅ Idéntico
- risk_decision: `User Auth` ✅ Idéntico

---

## Conclusión

### ✅ Los archivos son EQUIVALENTES

**Origen de los datos**:
- Ambos archivos provienen del mismo dataset en S3
- Misma fuente: Silver layer Parquet files
- Mismo período: 2026-03-27 a 2026-04-29
- Mismos 243 registros

**Diferencia técnica**:
- El Archivo 1 tiene timestamps en timezone local (UTC-05:00)
- El Archivo 2 tiene timestamps en timezone UTC (+00:00)
- Esto es solo una diferencia de **representación**, no de **contenido**

**Recomendación**:
- ✅ Usa **cualquiera de los dos archivos** - contienen los mismos datos
- ✅ Prefiere **UTC** (Archivo 2) para análisis internacionales
- ✅ Prefiere **UTC-05:00** (Archivo 1) si trabajas solo en Colombia

---

## Validación

```python
# Para verificar que son idénticos (ignorando timezone):
import pandas as pd

df1 = pd.read_csv('_SafeTransactionResults__202604291015.csv')
df2 = pd.read_csv('SafeTxnResultsSilver.csv')

# Normalizar timestamps a UTC
df1['createdAt'] = pd.to_datetime(df1['createdAt']).dt.tz_convert('UTC')
df2['createdAt'] = pd.to_datetime(df2['createdAt']).dt.tz_convert('UTC')

# Comparar
assert df1['uuid'].equals(df2['uuid'])  # ✅ PASS
assert df1['transactionId'].equals(df2['transactionId'])  # ✅ PASS
assert df1['createdAt'].equals(df2['createdAt'])  # ✅ PASS
```

---

**Documento generado**: 2026-04-29 10:17  
**Script**: `compare_csv_files.py`
