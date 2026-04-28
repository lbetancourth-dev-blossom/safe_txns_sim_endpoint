# Similarity Response Enhancement - Changelog

## Fecha: 2026-04-28

## Resumen
Se agregaron campos de similitud a la respuesta del endpoint de inferencia y se eliminó la lógica que sobrescribía los resultados del modelo K-means.

## Cambios Implementados

### 1. Archivos Modificados

#### `endpoint_test/similarity_matcher.py`
- **Línea 771-778**: Agregado `transaction_id` a cada elemento de `top_matches[]`
- **Línea 784**: Agregado `best_txn_id = ref_ids[best_idx]` para capturar el ID del mejor match
- **Línea 790**: Agregado campo `matched_transaction_id` al resultado

**Impacto**: Ahora `top_matches[]` incluye el TransactionID de cada match, facilitando la trazabilidad.

#### `endpoint_test/inference_rules.py`
- **Líneas 798-805**: Preservación del TransactionID del input
- **Líneas 1088-1096**: Cálculo de `similarity_decision` basado en status (SAFE→Accept, RISKY→Reject)
- **Líneas 1098-1106**: Agregados campos al resultado de similitud:
  - `TransactionID` (del input)
  - `matched_transaction_id`
  - `similarity_decision`
- **Líneas 1098-1117 (REMOVIDAS)**: Eliminada lógica que sobrescribía:
  - `risk_score` (ya no se cambia a 70)
  - `risk_decision` (ya no se sobrescribe con Accept/Reject)
  - `kmeans_original_decision` y `kmeans_original_score` (ya no se guardan)
- **Líneas 1191-1199**: Agregados campos de similitud a la respuesta final del endpoint

**Impacto**: El modelo K-means mantiene su decisión original. La similitud solo proporciona información adicional.

### 2. Archivos Nuevos

#### `test/test_similarity_fields.py`
Script de prueba para verificar la estructura de los campos de similitud.

#### `docs/SIMILARITY_RESPONSE_ENHANCEMENT.md`
Documentación completa de la propuesta de enriquecimiento de campos de similitud.

## Campos Agregados a la Respuesta del Endpoint

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `similarity_matched` | bool | True si se encontró match sobre threshold |
| `similarity_TransactionID` | int | TransactionID del input (query) |
| `similarity_matched_transaction_id` | str | TransactionID del mejor match encontrado |
| `similarity_score` | float | Score de similitud (0.0-1.0) |
| `similarity_status` | str | SAFE, RISKY, NONE, DISABLED, ERROR |
| `similarity_decision` | str | Accept (SAFE) o Reject (RISKY), None si no hay match |

## Cambios en top_matches[]

### Antes:
```json
{
  "similarity_score": 0.95,
  "status_warning": "SAFE"
}
```

### Ahora:
```json
{
  "transaction_id": "1798449",
  "similarity_score": 0.95,
  "status_warning": "SAFE"
}
```

## Lógica Removida

### Antes (sobrescribía el modelo):
```python
if matched and similarity_score >= threshold and status_warning in ["SAFE", "RISKY"]:
    # Store original K-means decision for audit
    out_df.at[idx, "kmeans_original_decision"] = row["risk_decision"]
    out_df.at[idx, "kmeans_original_score"] = row["risk_score"]
    
    # Override with fixed similarity-based rules
    out_df.at[idx, "risk_score"] = 70
    
    if status_warning == "RISKY":
        out_df.at[idx, "risk_decision"] = "Reject"
    elif status_warning == "SAFE":
        out_df.at[idx, "risk_decision"] = "Accept"
```

### Ahora (no sobrescribe):
```python
# Calculate similarity_decision based on status
similarity_decision = None
if matched and status_warning in ["SAFE", "RISKY"]:
    similarity_decision = "Accept" if status_warning == "SAFE" else "Reject"

# Store similarity result (do NOT override model's risk_score/risk_decision)
similarity_result = {
    "matched": matched,
    "TransactionID": transaction_ids[idx],
    "matched_transaction_id": matched_txn_id,
    "similarity_score": float(similarity_score),
    "similarity_status": status_warning,
    "similarity_decision": similarity_decision,
    "top_matches": top_matches
}
```

## Ejemplo de Respuesta

### Antes:
```json
{
  "num__amount": 0.713,
  "Cluster": 3,
  "risk_score": 70,
  "risk_decision": "Accept",
  "kmeans_original_decision": "User Auth",
  "kmeans_original_score": 45
}
```

### Ahora:
```json
{
  "num__amount": 0.713,
  "Cluster": 3,
  "risk_score": 45,
  "risk_decision": "User Auth",
  "similarity_matched": true,
  "similarity_TransactionID": 4836236,
  "similarity_matched_transaction_id": "1798449",
  "similarity_score": 0.95,
  "similarity_status": "SAFE",
  "similarity_decision": "Accept"
}
```

## Beneficios

1. **Trazabilidad**: Identificación completa de query y match (TransactionID → matched_transaction_id)
2. **Separación de responsabilidades**: El modelo mantiene su decisión, la similitud proporciona contexto adicional
3. **Flexibilidad**: Permite implementar lógica de decisión final en capas superiores (API, frontend)
4. **Auditoría**: Historial completo de decisiones del modelo y matches de similitud
5. **Debugging**: Facilita identificar discrepancias entre modelo y similitud

## Próximos Pasos

1. ✅ Cambios implementados y probados localmente
2. ⏳ Hacer commit y push de los cambios
3. ⏳ Desplegar al endpoint de SageMaker (si es necesario)
4. ⏳ Probar con datos reales usando `test/process_endpoint.py`
5. ⏳ Validar respuestas del endpoint en producción

## Notas Técnicas

- Los cambios son retrocompatibles (los campos se agregan, no se remueven existentes)
- Si el módulo de similitud no está disponible, los campos se llenan con valores por defecto (DISABLED)
- Los errores en similitud no afectan la respuesta del modelo (campos se llenan con ERROR)
- El campo `similarity_decision` puede ser `None` si no hay match o si el status no es SAFE/RISKY

## Testing

Ejecutar:
```bash
python3 test/test_similarity_fields.py
```

Para probar con el endpoint real:
```bash
python3 test/process_endpoint.py
```
