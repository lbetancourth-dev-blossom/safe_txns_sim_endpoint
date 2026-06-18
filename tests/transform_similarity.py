#!/usr/bin/env python3
"""
Script para transformar wp_result.csv al formato de SafeTransactionResults.

El formato final incluye:
- uuid: generado automáticamente
- transactionId: de TransactionID
- idFi: extraído del input original
- statusWarning: SAFE (forzado)
- metadata: JSON con numericVariables, categoricalVariables y decisionResult
- createdAt: timestamp actual
- updatedAt: timestamp actual
"""

import pandas as pd
import numpy as np
import json
import uuid
from datetime import datetime
import sys

def extract_numeric_variables(row, input_df_row):
    """
    Extrae las variables numéricas originales (sin transformar).
    """
    # Estas son las variables originales antes del preprocesamiento
    numeric_vars = {}
    
    # Lista de campos numéricos originales del input
    original_numeric_fields = [
        'amount', 'is_night', 'hour_sin', 'hour_cos', 'day_of_week_cos', 'month_cos',
        'is_batch', 'count_suspected_actions_in_current_session', 'total_actions_session',
        'is_auth_email_session', 'is_auth_phone_session', 'user_age', 'total_accounts',
        'count_all_txn_last_5m', 'total_amount_all_txn_last_5m',
        'count_user_all_txn_in_last_6_months', 'user_avg_amount_txn_per_active_day_last_6_months',
        'count_user_potential_fraud_txn_in_last_2_months', 'count_user_cancelled_txn_in_last_week',
        'count_user_cancelled_txn_in_last_month', 'amount_coef_var_lst6m',
        'pct_txns_under_100_lst6m', 'pct_txns_over_1k_lst6m', 'recency_user_created_days',
        'is_amount_greater_than_cu_p95_amount_ach_txn_in_last_6_months',
        'txn_amount_vs_cu_avg_amount_ach_txn_in_last_6_months', 'amt_vs_user_ach_avg_day',
        'ach_count_share_6m', 'ach_amount_share_6m',
        'is_first_txn_from_this_olb_user_to_this_recipient_account_q_6h',
        'count_txn_to_recipient_account_in_last_2_months',
        'count_txn_to_recipient_account_last_5m', 'total_amount_txn_to_recipient_account_last_5m',
        'num_recipients_batch', 'amount_share_in_batch',
        'count_failed_actions_in_current_session', 'count_txn_to_recipient_account_in_last_week',
        'count_all_txn_after_recipient_account_creation', 'is_any_auth_session',
        'days_since_phone_update', 'days_since_email_update', 'weekend',
        'is_personal_user_phone_primary_updated_last_week',
        'is_personal_user_email_primary_updated_last_week'
    ]
    
    for field in original_numeric_fields:
        if field in input_df_row and pd.notna(input_df_row[field]):
            val = input_df_row[field]
            # Convertir tipos numpy a tipos nativos de Python
            if isinstance(val, (np.integer, np.int64, np.int32)):
                numeric_vars[field] = int(val)
            elif isinstance(val, (np.floating, np.float64, np.float32)):
                numeric_vars[field] = float(val)
            else:
                numeric_vars[field] = val
    
    return numeric_vars

def extract_categorical_variables(input_df_row):
    """
    Extrae las variables categóricas originales (sin transformar).
    """
    categorical_vars = {}
    
    # Lista de campos categóricos originales
    original_categorical_fields = [
        'TransactionProcessingType', 'TransactionOrigin', 'TransactionCategory',
        'user_type', 'access'
    ]
    
    for field in original_categorical_fields:
        if field in input_df_row:
            val = input_df_row[field]
            categorical_vars[field] = str(val) if pd.notna(val) else ""
    
    return categorical_vars

def extract_decision_result(row):
    """
    Extrae todos los campos del resultado del modelo (features transformados + resultados).
    """
    decision_result = {}
    
    # Incluir todos los campos num__ y cat__
    for col in row.index:
        if col.startswith('num__') or col.startswith('cat__'):
            val = row[col]
            # Convertir tipos numpy a tipos nativos de Python
            if pd.notna(val):
                if isinstance(val, (np.integer, np.int64, np.int32)):
                    decision_result[col] = int(val)
                elif isinstance(val, (np.floating, np.float64, np.float32)):
                    decision_result[col] = float(val)
                else:
                    decision_result[col] = val
    
    # Incluir campos del modelo
    model_fields = [
        'Cluster', 'Distance_to_Centroid', 'risk_score', 'risk_decision', 'is_outlier'
    ]
    
    # Incluir campos adicionales si existen
    optional_fields = [
        'top_contributors', 'audit_category', 'audit_explanation', 'ux_copy'
    ]
    
    for field in model_fields + optional_fields:
        if field in row.index and pd.notna(row[field]):
            val = row[field]
            # Convertir tipos numpy a tipos nativos de Python
            if isinstance(val, (np.integer, np.int64, np.int32)):
                decision_result[field] = int(val)
            elif isinstance(val, (np.floating, np.float64, np.float32)):
                decision_result[field] = float(val)
            else:
                decision_result[field] = val
    
    return decision_result

def transform_to_similarity_format(wp_result_path, wp_input_path, output_path):
    """
    Transforma wp_result.csv al formato de SafeTransactionResults.
    """
    print("=" * 70)
    print("🔄 Transformación al Formato de Similarity")
    print("=" * 70)
    
    # Leer datos
    print(f"\n📖 Leyendo archivos...")
    df_result = pd.read_csv(wp_result_path)
    df_input = pd.read_csv(wp_input_path)
    
    print(f"✓ wp_result.csv: {len(df_result)} filas")
    print(f"✓ wp_input.csv: {len(df_input)} filas")
    
    # Verificar que tengan el mismo número de filas
    if len(df_result) != len(df_input):
        print(f"⚠️  Advertencia: Diferente número de filas")
    
    # Crear DataFrame de salida
    output_rows = []
    
    print(f"\n⚙️  Procesando transacciones...")
    for idx in range(len(df_result)):
        result_row = df_result.iloc[idx]
        input_row = df_input.iloc[idx] if idx < len(df_input) else pd.Series()
        
        # Extraer TransactionID e idFi
        transaction_id = int(result_row.get('TransactionID', 0))
        id_fi = int(input_row.get('idFi', 52)) if 'idFi' in input_row else 52
        
        # Construir metadata
        metadata = {
            "numericVariables": extract_numeric_variables(result_row, input_row),
            "categoricalVariables": extract_categorical_variables(input_row),
            "decisionResult": extract_decision_result(result_row)
        }
        
        # Crear fila de salida
        output_row = {
            'uuid': str(uuid.uuid4()),
            'transactionId': transaction_id,
            'idFi': id_fi,
            'statusWarning': 'SAFE',  # Forzado a SAFE
            'metadata': json.dumps(metadata),
            'createdAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3] + ' -0500',
            'updatedAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3] + ' -0500'
        }
        
        output_rows.append(output_row)
        
        if (idx + 1) % 10 == 0:
            print(f"  Procesadas: {idx + 1}/{len(df_result)}")
    
    # Crear DataFrame final
    df_output = pd.DataFrame(output_rows)
    
    print(f"\n✓ {len(df_output)} transacciones transformadas")
    
    # Guardar archivo
    print(f"\n💾 Guardando en {output_path}...")
    df_output.to_csv(output_path, index=False)
    print(f"✓ Archivo guardado ({len(df_output)} filas, {len(df_output.columns)} columnas)")
    
    # Mostrar muestra
    print(f"\n📋 Estructura del archivo de salida:")
    print(f"  Columnas: {list(df_output.columns)}")
    print(f"\n📄 Primera transacción (muestra):")
    first_row = df_output.iloc[0]
    print(f"  - uuid: {first_row['uuid']}")
    print(f"  - transactionId: {first_row['transactionId']}")
    print(f"  - idFi: {first_row['idFi']}")
    print(f"  - statusWarning: {first_row['statusWarning']}")
    print(f"  - metadata (primeros 200 chars): {first_row['metadata'][:200]}...")
    print(f"  - createdAt: {first_row['createdAt']}")
    print(f"  - updatedAt: {first_row['updatedAt']}")
    
    # Validar metadata
    print(f"\n🔍 Validando metadata...")
    try:
        metadata_dict = json.loads(first_row['metadata'])
        print(f"  ✓ metadata es JSON válido")
        print(f"  ✓ Keys: {list(metadata_dict.keys())}")
        if 'decisionResult' in metadata_dict:
            print(f"  ✓ decisionResult presente ({len(metadata_dict['decisionResult'])} campos)")
        if 'numericVariables' in metadata_dict:
            print(f"  ✓ numericVariables presente ({len(metadata_dict['numericVariables'])} campos)")
        if 'categoricalVariables' in metadata_dict:
            print(f"  ✓ categoricalVariables presente ({len(metadata_dict['categoricalVariables'])} campos)")
    except Exception as e:
        print(f"  ✗ Error validando metadata: {e}")
    
    print("\n" + "=" * 70)
    print("✅ Transformación completada exitosamente")
    print("=" * 70)
    print(f"Archivo de salida: {output_path}")
    print(f"Formato: Compatible con similarity matching")
    print(f"statusWarning: SAFE (todas las transacciones)")
    print()

if __name__ == "__main__":
    wp_result_path = "data/wp_result.csv"
    wp_input_path = "data/wp_input.csv"
    output_path = "data/wp_similarity.csv"
    
    transform_to_similarity_format(wp_result_path, wp_input_path, output_path)
