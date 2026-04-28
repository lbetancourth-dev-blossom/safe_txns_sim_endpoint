# Propuesta: Campos para Resultados de Similitud

## 🎯 Resumen Ejecutivo

Esta propuesta enriquece la respuesta del endpoint de inferencia con campos adicionales que facilitan el seguimiento, análisis y debugging de los matches de similitud.

## 📊 Campos Actuales (Implementados)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `matched` | bool | Si se encontró match |
| `similarity_score` | float | Score del mejor match |
| `status_warning` | string | Label del mejor match |
| `top_matches` | array | Top K matches |
| `threshold_used` | float | Threshold aplicado |
| `metric_used` | string | Métrica usada (cosine) |
| `reference_count` | int | # registros en referencia |
| `s3_source` | string | URI de datos de referencia |

## ⭐ Campos Propuestos

### 🔑 Nivel 1: CRÍTICOS (implementar primero)

| Campo | Tipo | Descripción | Justificación |
|-------|------|-------------|---------------|
| `query_transaction_id` | int | TransactionID del input | **Esencial para trazabilidad** |
| `matched_transaction_id` | int | ID del mejor match | **Permite buscar la transacción matched** |
| `confidence_level` | string | "HIGH"/"MEDIUM"/"LOW" | **Facilita decisiones automáticas** |

**Cálculo de confidence_level:**
- HIGH: score >= 0.95
- MEDIUM: 0.90 <= score < 0.95
- LOW: 0.85 <= score < 0.90

### 📊 Nivel 2: MUY ÚTILES (alta prioridad)

| Campo | Tipo | Descripción | Justificación |
|-------|------|-------------|---------------|
| `score_gap` | float | Diferencia con 2do match | Indica qué tan único es el match |
| `matched_risk_score` | int | Risk score del match | Contexto de la decisión matched |
| `matched_cluster` | int | Cluster del match | Para análisis de patrones |
| `matched_uuid` | string | UUID del mejor match | Identificador único global |
| `matches_above_threshold` | int | # matches sobre threshold | Cantidad de candidatos válidos |

### 🎯 Nivel 3: ÚTILES (media prioridad)

| Campo | Tipo | Descripción | Justificación |
|-------|------|-------------|---------------|
| `matched_risk_decision` | string | Decisión del match | Contexto completo de decisión |
| `matched_timestamp` | string | Timestamp del match | Para análisis temporal |
| `processing_time_ms` | float | Tiempo de procesamiento | Para monitoring de performance |
| `match_quality` | string | "excellent"/"good"/"fair" | Clasificación de calidad |

**Cálculo de match_quality:**
- excellent: score >= 0.95 AND score_gap >= 0.10
- good: score >= 0.92 AND score_gap >= 0.05
- fair: todo lo demás

### 🏆 Nivel 4: AVANZADOS (baja prioridad)

| Campo | Tipo | Descripción | Uso |
|-------|------|-------------|-----|
| `matched_idFi` | int | FI del match | Análisis por institución |
| `percentile_rank` | float | Percentil vs ref data | Para análisis estadístico |
| `cache_hit` | bool | Si se usó cache | Debugging |
| `search_timestamp` | string | Timestamp de búsqueda | Auditoría |

## 📋 Enriquecimiento de top_matches[]

Para cada elemento en `top_matches[]`, agregar:

| Campo Actual | Campos a Agregar | Tipo | Descripción |
|--------------|------------------|------|-------------|
| similarity_score ✓ | - | float | Ya existe |
| status_warning ✓ | - | string | Ya existe |
| - | **transaction_id** | int | **ID de la transacción** |
| - | **uuid** | string | UUID único |
| - | **risk_score** | int | Risk score del match |
| - | **cluster** | int | Cluster asignado |
| - | created_at | string | Timestamp |

## 📝 Estructura de Respuesta Propuesta

### Opción A: Flat (más simple)

```json
{
  "TransactionID": 4836236,
  "num__amount": 0.713,
  "Cluster": 3,
  "risk_score": 75,
  "risk_decision": "User Auth",
  
  "similarity_matched": true,
  "similarity_score": 0.95,
  "similarity_confidence": "HIGH",
  "similarity_matched_id": 1798449,
  "similarity_matched_uuid": "044a10e4-...",
  "similarity_status": "SAFE",
  "similarity_score_gap": 0.12,
  "similarity_matched_risk_score": 100,
  "similarity_matched_cluster": 4,
  "similarity_matches_count": 3,
  
  "similarity_top_matches": [
    {
      "transaction_id": 1798449,
      "uuid": "044a10e4-...",
      "similarity_score": 0.95,
      "status_warning": "SAFE",
      "risk_score": 100,
      "cluster": 4
    }
  ]
}
```

### Opción B: Anidada (más estructurada)

```json
{
  "TransactionID": 4836236,
  "num__amount": 0.713,
  "Cluster": 3,
  "risk_score": 75,
  "risk_decision": "User Auth",
  
  "similarity": {
    "matched": true,
    "confidence_level": "HIGH",
    "
_match": {
      "transaction_id": 1798449,
      "uuid": "044a10e4-32e8-4bc1-a55c-c2c3143b88fb",
      "similarity_score": 0.95,
      "status_warning": "SAFE",
      "risk_score": 100,
      "cluster": 4,
      "created_at": "2026-03-27 11:56:16"
    },
    "match_quality": {
      "score": 0.95,
      "score_gap": 0.12,
      "quality_rating": "excellent",
      "matches_above_threshold": 3
    },
    "top_matches": [
      {
        "transaction_id": 1798449,
        "similarity_score": 0.95,
        "status_warning": "SAFE",
        "cluster": 4
      },
      {
        "transaction_id": 1798800,
        "similarity_score": 0.83,
        "status_warning": "PENDING",
        "cluster": 1
      }
    ],
    "metadata": {
      "threshold_used": 0.90,
      "metric_used": "cosine",
      "reference_count": 35,
      "processing_time_ms": 45
    }
  }
}
```

## 🎯 Recomendación de Implementación

### Fase 1: Campos Críticos (día 1)
1. `query_transaction_id` - Agregar TransactionID del input
2. `matched_transaction_id` - ID del mejor match
3. `confidence_level` - HIGH/MEDIUM/LOW
4. `score_gap` - Diferencia con 2do match

### Fase 2: Enriquecimiento (día 2-3)
5. `matched_risk_score` - Risk score del match
6. `matched_cluster` - Cluster del match
7. `matched_uuid` - UUID del match
8. Enriquecer `top_matches[]` con transaction_id, uuid, risk_score, cluster

### Fase 3: Metadata (opcional)
9. `matches_above_threshold` - Contador
10. `processing_time_ms` - Performance tracking
11. `match_quality` - Clasificación de calidad

## 🏗️ Cambios Necesarios en el Código

### 1. similarity_matcher.py
- Agregar `ref_ids` (transaction IDs) y `ref_metadata` (metadata completa)
- Modificar `top_matches` para incluir transaction_id, uuid, etc.
- Calcular `score_gap`, `confidence_level`, `match_quality`

### 2. inference_rules.py
- Pasar TransactionID del input a find_similar_transaction()
- Incluir similarity results en la respuesta final
- Agregar campos calculados (confidence, gap, etc.)

### 3. Cargar metadata adicional desde S3
- Parsear campos adicionales de wp_similarity.csv: uuid, createdAt, etc.
- Mantener referencia a metadata completa para enriquecer respuesta

## ✅ Beneficios

1. **Trazabilidad**: TransactionID permite seguimiento end-to-end
2. **Debugging**: Score gap y confidence ayudan a diagnosticar problemas
3. **Análisis**: Campos de contexto facilitan análisis de patrones
4. **Auditoría**: Metadata completa para compliance
5. **UX**: Información rica para frontend/reportes

## 📊 Impacto Estimado

- **Tamaño respuesta**: +30-40% (de ~2KB a ~3KB por transacción)
- **Performance**: +5-10ms por búsqueda (por parsear metadata adicional)
- **Complejidad**: Media (requiere modificar 2 archivos principales)
- **Valor**: Alto (mejora significativa en usabilidad y debugging)

## ❓ Preguntas para Decidir

1. ¿Prefieres estructura flat (Opción A) o anidada (Opción B)?
2. ¿Qué campos de Nivel 3 y 4 son más relevantes para tu caso de uso?
3. ¿Necesitas agregar campos específicos de tu negocio?
4. ¿Prefieres implementación incremental (Fase 1 → 2 → 3) o todo de una vez?

---

**Recomendación Final**: Implementar Fase 1 (campos críticos) con estructura anidada (Opción B) para mantener respuesta organizada y extensible.
