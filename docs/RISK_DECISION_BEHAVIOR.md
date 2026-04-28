# Ejemplos de Resultados: risk_decision con y sin Match

## 🎯 Resumen: risk_decision NO cambia por match

Con los cambios actuales, **`risk_decision` SIEMPRE muestra la decisión del modelo K-means**, sin importar si hay match de similitud o no.

---

## 📊 Ejemplos Detallados

### Ejemplo 1: Match Alta Similitud + Modelo dice "User Auth"

```
TransactionID:                    4836236
Cluster:                          4
Distance_to_Centroid:             12.038
risk_score:                       75          ← Del modelo K-means
risk_decision:                    "User Auth" ← Del modelo K-means (NO cambia)
is_outlier:                       1

similarity_TransactionID:         4836236
similarity_matched_transaction_id: 1798449
similarity_score:                 0.95        ← Match encontrado!
```

**Resultado**: Aunque hay match con score 0.95, `risk_decision` sigue siendo "User Auth" (la decisión del modelo).

---

### Ejemplo 2: Match Alta Similitud + Modelo dice "Accept"

```
TransactionID:                    4836505
Cluster:                          2
Distance_to_Centroid:             5.234
risk_score:                       45          ← Del modelo K-means
risk_decision:                    "Accept"    ← Del modelo K-means (NO cambia)
is_outlier:                       0

similarity_TransactionID:         4836505
similarity_matched_transaction_id: 1798920
similarity_score:                 0.92        ← Match encontrado!
```

**Resultado**: Aunque hay match con score 0.92, `risk_decision` sigue siendo "Accept" (la decisión del modelo).

---

### Ejemplo 3: Match Media Similitud + Modelo dice "Reject"

```
TransactionID:                    4836506
Cluster:                          1
Distance_to_Centroid:             18.567
risk_score:                       95          ← Del modelo K-means
risk_decision:                    "Reject"    ← Del modelo K-means (NO cambia)
is_outlier:                       1

similarity_TransactionID:         4836506
similarity_matched_transaction_id: 1799100
similarity_score:                 0.78        ← Match encontrado
```

**Resultado**: Aunque hay match con score 0.78, `risk_decision` sigue siendo "Reject" (la decisión del modelo).

---

### Ejemplo 4: Sin Match + Modelo dice "Accept"

```
TransactionID:                    4836507
Cluster:                          0
Distance_to_Centroid:             2.345
risk_score:                       15          ← Del modelo K-means
risk_decision:                    "Accept"    ← Del modelo K-means
is_outlier:                       0

similarity_TransactionID:         4836507
similarity_matched_transaction_id: [vacío]    ← Sin match
similarity_score:                 0.0          ← Debajo threshold
```

**Resultado**: Sin match, `risk_decision` muestra "Accept" (la decisión del modelo).

---

## ⚙️ Lógica Actual: NO hay validación

### Código actual (líneas 1088-1097 en inference_rules.py):

```python
# Log match if found
if matched:
    print(f"[SIMILARITY] Row {idx}: Match found (score: {similarity_score:.4f}, matched_id: {matched_txn_id})")

# Store only 3 fields: TransactionID, matched_transaction_id, similarity_score
similarity_result = {
    "TransactionID": transaction_ids[idx] if idx < len(transaction_ids) else None,
    "matched_transaction_id": matched_txn_id,
    "similarity_score": float(similarity_score) if similarity_score is not None else 0.0
}

# NO hay código que modifique out_df["risk_decision"]
# NO hay código que modifique out_df["risk_score"]
```

**No existe validación ni lógica que cambie `risk_decision` basado en similitud.**

---

## 🔍 ¿Cómo usar los datos de similitud para decisiones?

Si quieres tomar decisiones basadas en similitud, implementa la lógica en tu aplicación/API:

### Ejemplo de lógica personalizada:

```python
# Pseudo-código para tu aplicación
def tomar_decision_final(row):
    model_decision = row['risk_decision']
    similarity_score = row['similarity_score']
    matched_id = row['similarity_matched_transaction_id']
    
    # Si hay match con alta similitud
    if similarity_score >= 0.90 and matched_id:
        # Buscar el status del matched transaction en tu base de datos
        matched_status = buscar_en_db(matched_id)
        
        if matched_status == "SAFE":
            return "Accept"  # Override
        elif matched_status == "RISKY":
            return "Reject"  # Override
    
    # Si no hay match o similitud baja, usar decisión del modelo
    return model_decision
```

---

## 📌 Resumen

| Situación | risk_decision muestra | Validación aplicada |
|-----------|----------------------|---------------------|
| Match alto (0.95) + modelo dice "User Auth" | "User Auth" | Ninguna |
| Match alto (0.92) + modelo dice "Accept" | "Accept" | Ninguna |
| Match medio (0.78) + modelo dice "Reject" | "Reject" | Ninguna |
| Sin match (0.0) + modelo dice "Accept" | "Accept" | Ninguna |

**`risk_decision` SIEMPRE refleja la decisión del modelo K-means, independiente de similitud.**

Los campos de similitud (`similarity_TransactionID`, `similarity_matched_transaction_id`, `similarity_score`) solo proporcionan **información adicional** para que tú decidas qué hacer en capas superiores.
