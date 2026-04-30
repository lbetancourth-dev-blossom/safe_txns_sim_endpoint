# Secuencia de Ejecución del Endpoint

**Archivo**: `endpoint/inference_rules.py`  
**Función Principal**: `predict_fn(input_data, model_artifacts)`

---

## 🔄 Flujo Completo (Orden de Ejecución)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         INPUT: Transaction Data                         │
│                         (CSV/JSON con features)                         │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PASO 1: PREPROCESSING & FEATURE ENGINEERING                            │
│  ─────────────────────────────────────────────────────────              │
│  • Parse input data                                                     │
│  • Derive time features (hour_sin, hour_cos, etc.)                     │
│  • Derive recency features                                              │
│  • Derive is_batch                                                      │
│  • Apply ColumnTransformer (pipeline)                                   │
│  • Generate num__ and cat__ features                                    │
│                                                                          │
│  Output: df_transformed (features con prefijos num__/cat__)             │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PASO 2: K-MEANS CLUSTERING (SIEMPRE SE EJECUTA)                       │
│  ─────────────────────────────────────────────────────                 │
│  Líneas: 869-920                                                        │
│                                                                          │
│  ✓ Predict cluster assignment                                           │
│  ✓ Calculate distance to centroid                                       │
│  ✓ Score risk (0-100) usando MinMaxScaler por cluster                  │
│  ✓ Classify risk_decision: Accept/User Auth/Admin Review/Reject        │
│  ✓ Get top_contributors (3 variables más importantes)                   │
│  ✓ Generate audit_category, audit_explanation, ux_copy                  │
│                                                                          │
│  Output:                                                                 │
│    • Cluster (0-4)                                                       │
│    • Distance_to_Centroid                                                │
│    • risk_score (0-100)                                                  │
│    • risk_decision (Accept/User Auth/Admin Review/Reject)               │
│    • top_contributors [var1, var2, var3]                                │
│    • audit_category, audit_explanation, ux_copy                          │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PASO 3: STATISTICAL RULES (OPCIONAL - si está habilitado)             │
│  ─────────────────────────────────────────────────────                 │
│  Líneas: 925-965                                                        │
│                                                                          │
│  ✓ Derive weekend feature (solo para rules, NO para K-means)           │
│  ✓ Run 12 statistical rules (R1-R12)                                    │
│  ✓ Calculate rules_risk_score (0-100)                                   │
│  ✓ Classify rules_risk_decision                                         │
│                                                                          │
│  Output:                                                                 │
│    • rule_1, rule_2, ..., rule_12 (valores individuales)                │
│    • rules_risk_score (0-100)                                            │
│    • rules_risk_decision                                                 │
│    • rules_explanation                                                   │
│                                                                          │
│  Puede deshabilitarse con: DISABLE_RULES=1                              │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PASO 4: HYBRID DECISION (K-Means + Rules)                             │
│  ─────────────────────────────────────────────────────                 │
│  Líneas: 967-1006                                                       │
│                                                                          │
│  ✓ Merge K-means results + Rules results                                │
│  ✓ Apply hybrid logic (Excel-style):                                    │
│    - Si rules dice "Reject" y score >= 90 → escala al máximo           │
│    - Si rules dice "Admin Review" → step up la decisión                │
│    - Si rules dice "User Auth" y K-means="Accept" → eleva              │
│    - Caso contrario → mantiene K-means score                            │
│                                                                          │
│  Output:                                                                 │
│    • kmeans_risk_score (original de K-means)                            │
│    • kmeans_risk_decision (original de K-means)                         │
│    • risk_score (FINAL - híbrido)                                       │
│    • risk_decision (FINAL - híbrido)                                    │
│    • hybrid_decision                                                     │
│    • is_outlier (based on final risk_score >= 70)                       │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PASO 5: SIMILARITY MATCHING (SIEMPRE SE EJECUTA)                      │
│  ─────────────────────────────────────────────────────                 │
│  Líneas: 1049-1128                                                      │
│                                                                          │
│  ✓ Load reference data from Silver layer Parquet                        │
│    (s3://blossom-analytics-datalake-dev/datalake/silver/SAFE/           │
│     safetransactionresults/data/)                                       │
│  ✓ Para cada transacción:                                               │
│    - Extract ONLY num__ and cat__ features (NO post-processing)         │
│    - Calculate cosine similarity vs all reference transactions          │
│    - Find top-5 matches                                                  │
│    - If similarity >= 0.90 → match found                                │
│    - Extract matched transaction's statusWarning (SAFE/RISKY/PENDING)   │
│    - Calculate sim_decision based on status and score                   │
│                                                                          │
│  Output (4 campos de similitud):                                        │
│    • sim_match_txn_id: ID de transacción similar encontrada (o null)   │
│    • sim_score: Score de similitud 0.0-1.0 (o null si no hay match)    │
│    • sim_status: Status de txn matched: SAFE/RISKY/PENDING (o null)    │
│    • sim_decision: Accept/Reject si score>=0.90 (o null)                │
│                                                                          │
│  NOTA: Similarity NO modifica risk_score o risk_decision final.         │
│        Los 4 campos se agregan al output para análisis posterior.       │
│                                                                          │
│  Puede deshabilitarse con: DISABLE_SIMILARITY=1                         │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PASO 6: BUILD FINAL OUTPUT                                             │
│  ─────────────────────────────────────────────────────                 │
│  Líneas: 1132-1205                                                      │
│                                                                          │
│  ✓ Select requested columns (63 total):                                 │
│    - TransactionID (1)                                                   │
│    - 31 numeric features (num__*)                                        │
│    - 18 categorical features (cat__*)                                    │
│    - 9 model outputs (Cluster, Distance, scores, decisions)             │
│    - 4 similarity fields (sim_match_txn_id, sim_score, sim_status,      │
│                            sim_decision)                                 │
│  ✓ Rename columns (TransactionID → transaction_id)                      │
│  ✓ Handle nulls (fillna for numeric, '' for strings)                    │
│  ✓ Convert to records format (list of dicts)                            │
│                                                                          │
│  Output: JSON response with 63 fields per transaction                   │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
                            ┌────────────────┐
                            │  JSON OUTPUT   │
                            └────────────────┘
```

---

## 📊 Resumen de la Secuencia

| Paso | Componente | Obligatorio | Líneas | Output Principal |
|------|-----------|-------------|--------|------------------|
| **1** | **Preprocessing** | ✅ Sí | 764-868 | `df_transformed` (features) |
| **2** | **K-Means** | ✅ Sí | 869-920 | `risk_score`, `risk_decision`, `Cluster` |
| **3** | **Rules** | ⚠️ Opcional | 925-965 | `rules_risk_score`, `rules_risk_decision` |
| **4** | **Hybrid** | ⚠️ Si Rules activo | 967-1006 | `risk_score` final (híbrido) |
| **5** | **Similarity** | ✅ Sí | 1049-1128 | `sim_match_txn_id`, `sim_score`, `sim_status`, `sim_decision` |
| **6** | **Output** | ✅ Sí | 1132-1205 | JSON con 63 campos |

---

## 🔑 Puntos Clave

### 1. K-Means (Base)
- **Siempre se ejecuta primero** (después de preprocessing)
- Genera el `risk_score` inicial y `risk_decision` base
- Usa solo features transformadas (num__ y cat__)
- Identifica top 3 contributors para explainability

### 2. Rules (Elevador Opcional)
- **Solo se ejecuta si está habilitado** (default: habilitado)
- Deriva el feature `weekend` (NO usado por K-means)
- Ejecuta 12 reglas estadísticas independientes
- Genera su propio `rules_risk_score` y `rules_risk_decision`

### 3. Hybrid Logic (Combinación)
- **Solo si Rules está activo**
- Combina K-means + Rules usando lógica de Excel:
  - **Rules NUNCA baja** el score de K-means
  - **Rules SOLO eleva** si detecta patrones sospechosos
  - Estrategia conservadora: "K-means o lo que sea mayor"
- El `risk_score` final es el híbrido, NO solo K-means

### 4. Similarity (Información Adicional)
- **Siempre se ejecuta** (después de K-means/Rules)
- **NO modifica** el `risk_score` ni `risk_decision` final
- Busca transacciones similares en Silver layer (243 refs)
- Usa **solo features** (num__ y cat__), NO post-processing fields
- Agrega 4 campos informativos al output:
  - `sim_match_txn_id`: ID de match encontrado
  - `sim_score`: Similitud coseno (0.0-1.0)
  - `sim_status`: Status del match (SAFE/RISKY/PENDING)
  - `sim_decision`: Accept/Reject si score >= 0.90

---

## ⚙️ Variables de Entorno

```bash
# Deshabilitar componentes opcionales
DISABLE_RULES=1          # Salta el paso de Rules (solo K-means)
DISABLE_SIMILARITY=1     # Salta Similarity matching

# Configurar Similarity
SIMILARITY_THRESHOLD=0.90              # Umbral de similitud (default: 0.90)
SIMILARITY_S3_BUCKET=...               # Bucket de datos de referencia
SIMILARITY_S3_KEY=.../data/            # Path a Parquet files
```

---

## 📈 Comparación de Scores

Ejemplo de cómo evolucionan los scores:

```
Transaction Input → Preprocessing → Features
                                      ↓
                                  K-Means
                                      ↓
                    kmeans_risk_score = 65
                    kmeans_risk_decision = "Accept"
                                      ↓
                                  Rules (opcional)
                                      ↓
                    rules_risk_score = 85
                    rules_risk_decision = "Admin Review"
                                      ↓
                                  Hybrid Logic
                                      ↓
                    risk_score = 85 (elevado por Rules)
                    risk_decision = "Admin Review"
                                      ↓
                                  Similarity
                                      ↓
                    sim_match_txn_id = "1798449"
                    sim_score = 0.95
                    sim_status = "SAFE"
                    sim_decision = "Accept"
                                      ↓
                                  Final Output
                    {
                      "risk_score": 85,           // Híbrido (K-means + Rules)
                      "risk_decision": "Admin Review",  // Híbrido
                      "kmeans_risk_score": 65,    // Original K-means
                      "sim_match_txn_id": "1798449",
                      "sim_score": 0.95,
                      "sim_status": "SAFE",
                      "sim_decision": "Accept",
                      ...
                    }
```

**Interpretación**:
- K-means dice: "Accept" (score 65)
- Rules dice: "Admin Review" (score 85) → **Eleva la decisión**
- Final: "Admin Review" (score 85) ← **Hybrid gana**
- Similarity dice: "Match con txn SAFE anterior" → **Info adicional**

---

## 🎯 Orden Lógico de Decisión

```
┌─────────────┐
│   K-Means   │ → Base score y decisión inicial
└──────┬──────┘
       │
       ▼
┌─────────────┐
│    Rules    │ → Puede elevar el score (nunca bajar)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Hybrid    │ → Combina ambos (conservador: max score)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Similarity  │ → Agrega contexto histórico (NO cambia decisión)
└─────────────┘
```

**Score Final = max(kmeans_score, rules_adjusted_score)**

**Similarity es informativo**, no afecta la decisión final del endpoint. Se usa para análisis posterior y contexto.

---

## 🔍 Diferencias Clave

| Aspecto | K-Means | Rules | Similarity |
|---------|---------|-------|------------|
| **Ejecuta** | ✅ Siempre | ⚠️ Opcional | ✅ Siempre |
| **Modifica risk_score** | ✅ Sí (inicial) | ✅ Sí (eleva) | ❌ No |
| **Modifica risk_decision** | ✅ Sí (inicial) | ✅ Sí (eleva) | ❌ No |
| **Usa features** | ✅ num__/cat__ | ✅ + weekend | ✅ num__/cat__ |
| **Usa post-processing** | ❌ No | ❌ No | ❌ No |
| **Output** | Cluster, Distance, score, decision | 12 rules, score, decision | 4 similarity fields |
| **Propósito** | Detección de anomalías | Validación de reglas | Contexto histórico |

---

## 📝 Campos del Output Final (63 total)

### Identificador (1)
- `transaction_id` (renombrado de TransactionID)

### Features Numéricas (31)
- `num__amount`, `num__is_night`, `num__hour_sin`, `num__hour_cos`, ...

### Features Categóricas (18)
- `cat__TransactionProcessingType_Intime`, ...

### Outputs del Modelo (9)
- `Cluster`
- `Distance_to_Centroid`
- `kmeans_risk_score` (score original de K-means)
- `kmeans_risk_decision` (decisión original de K-means)
- `risk_score` (score FINAL híbrido)
- `risk_decision` (decisión FINAL híbrida)
- `is_outlier` (boolean: risk_score >= 70)
- `top_contributors` (lista de 3 variables)
- `audit_category`, `audit_explanation`, `ux_copy`

### Campos de Similitud (4) ✨ NUEVO
- `sim_match_txn_id`: ID de transacción similar (null si no match)
- `sim_score`: Score de similitud 0.0-1.0 (null si no match)
- `sim_status`: Status del match SAFE/RISKY/PENDING (null si no match)
- `sim_decision`: Accept/Reject si score >= 0.90 (null otherwise)

---

## 🚀 Uso en Producción

El endpoint procesa transacciones en tiempo real siguiendo esta secuencia:

1. **Request** → JSON/CSV con features de transacción
2. **K-Means** → Clasifica y asigna score base
3. **Rules** → Valida y puede elevar el score
4. **Hybrid** → Combina ambos conservadoramente
5. **Similarity** → Busca coincidencias históricas
6. **Response** → JSON con 63 campos (decision + context)

**Latencia típica**: ~200-500ms por transacción (incluye carga de referencia y similarity matching)

---

## 📚 Referencias

- **Código**: `endpoint/inference_rules.py`
- **Similarity**: `endpoint/similarity_matcher.py`
- **Rules**: `endpoint/statistical_rules.py`
- **Configuración**: Variables de entorno `DISABLE_RULES`, `DISABLE_SIMILARITY`, `SIMILARITY_THRESHOLD`
