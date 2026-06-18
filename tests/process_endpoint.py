#!/usr/bin/env python3
"""
Script para procesar transacciones a través del endpoint de SageMaker.

Uso:
    python process_endpoint.py --input data/wp_input.csv --output data/wp_result.csv
    
El script:
1. Lee transacciones desde wp_input.csv
2. Las procesa en el endpoint SAFE_TXNS_ENDPOINT_DEV
3. Guarda resultados con metadata en wp_result.csv
"""

import pandas as pd
import boto3
import json
import argparse
import os
import sys
from datetime import datetime
from typing import Dict, List, Any
import time

# Configuración
ENDPOINT_NAME = "SAFE_TXNS_ENDPOINT_DEV"
AWS_REGION = "us-east-1"  # Ajustar según tu región

def invoke_endpoint(runtime_client, endpoint_name: str, batch_df: pd.DataFrame) -> Dict:
    """
    Invoca el endpoint de SageMaker con datos CSV.
    
    Args:
        runtime_client: Cliente de SageMaker Runtime
        endpoint_name: Nombre del endpoint
        batch_df: DataFrame con datos a enviar
        
    Returns:
        Respuesta del endpoint (dict)
    """
    try:
        # Convertir DataFrame a CSV (sin índice, con header)
        import io
        csv_buffer = io.StringIO()
        batch_df.to_csv(csv_buffer, header=True, index=False)
        payload = csv_buffer.getvalue()
        
        response = runtime_client.invoke_endpoint(
            EndpointName=endpoint_name,
            ContentType='text/csv',
            Accept='application/json',
            Body=payload
        )
        
        result = json.loads(response['Body'].read().decode())
        return result
        
    except Exception as e:
        print(f"❌ Error invocando endpoint: {e}")
        raise

def process_batch(runtime_client, endpoint_name: str, batch_df: pd.DataFrame, batch_num: int) -> pd.DataFrame:
    """
    Procesa un lote de transacciones.
    
    Args:
        runtime_client: Cliente de SageMaker Runtime
        endpoint_name: Nombre del endpoint
        batch_df: DataFrame con transacciones
        batch_num: Número de lote
        
    Returns:
        DataFrame con resultados
    """
    print(f"  📦 Procesando lote {batch_num} ({len(batch_df)} transacciones)...")
    
    # Invocar endpoint con CSV
    start_time = time.time()
    result = invoke_endpoint(runtime_client, endpoint_name, batch_df)
    elapsed = time.time() - start_time
    
    print(f"    ✓ Lote procesado en {elapsed:.2f}s")
    
    # Extraer predictions
    if 'predictions' in result:
        predictions = result['predictions']
    elif isinstance(result, list):
        predictions = result
    else:
        raise ValueError(f"Formato de respuesta inesperado: {result}")
    
    # Verificar que tenemos el mismo número de resultados
    if len(predictions) != len(batch_df):
        print(f"    ⚠️  Advertencia: {len(predictions)} resultados vs {len(batch_df)} entradas")
    
    # Crear DataFrame con resultados
    results_df = pd.DataFrame(predictions)
    
    # Agregar columnas de identificación si no están en el resultado
    if 'TransactionID' not in results_df.columns and 'TransactionID' in batch_df.columns:
        results_df.insert(0, 'TransactionID', batch_df['TransactionID'].values[:len(results_df)])
    
    return results_df

def create_metadata_column(results_df: pd.DataFrame) -> pd.Series:
    """
    Crea la columna metadata en formato JSON para similarity matching.
    
    El formato esperado es:
    {
        "decisionResult": {
            "num__amount": 1500.0,
            "num__is_night": 1,
            "cat__TransactionOrigin": 2,
            "Cluster": 3,
            "Distance_to_Centroid": 45.3,
            "risk_score": 75,
            ...
        }
    }
    """
    metadata_list = []
    
    for _, row in results_df.iterrows():
        decision_result = row.to_dict()
        
        # Crear estructura de metadata
        metadata = {
            "decisionResult": decision_result
        }
        
        # Convertir a JSON string
        metadata_list.append(json.dumps(metadata))
    
    return pd.Series(metadata_list, index=results_df.index)

def main():
    parser = argparse.ArgumentParser(description='Procesar transacciones en endpoint de SageMaker')
    parser.add_argument('--input', default='data/wp_input.csv', help='Archivo CSV de entrada')
    parser.add_argument('--output', default='data/wp_result.csv', help='Archivo CSV de salida')
    parser.add_argument('--endpoint', default=ENDPOINT_NAME, help='Nombre del endpoint de SageMaker')
    parser.add_argument('--region', default=AWS_REGION, help='Región de AWS')
    parser.add_argument('--batch-size', type=int, default=10, help='Tamaño del lote (transacciones por llamada)')
    parser.add_argument('--profile', default=None, help='Perfil de AWS (opcional)')
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("🚀 Procesamiento de Transacciones - SageMaker Endpoint")
    print("=" * 70)
    print(f"Endpoint: {args.endpoint}")
    print(f"Región:   {args.region}")
    print(f"Input:    {args.input}")
    print(f"Output:   {args.output}")
    print(f"Lote:     {args.batch_size} transacciones")
    print("=" * 70)
    
    # Verificar que existe el archivo de entrada
    if not os.path.exists(args.input):
        print(f"❌ Error: Archivo de entrada no encontrado: {args.input}")
        return 1
    
    # Leer datos de entrada
    print(f"\n📖 Leyendo datos de entrada...")
    try:
        input_df = pd.read_csv(args.input)
        print(f"✓ {len(input_df)} transacciones cargadas")
        print(f"✓ {len(input_df.columns)} columnas")
    except Exception as e:
        print(f"❌ Error leyendo archivo: {e}")
        return 1
    
    # Crear cliente de SageMaker Runtime
    print(f"\n🔌 Conectando a SageMaker...")
    try:
        session_kwargs = {'region_name': args.region}
        if args.profile:
            session_kwargs['profile_name'] = args.profile
        
        session = boto3.Session(**session_kwargs)
        runtime_client = session.client('sagemaker-runtime')
        print(f"✓ Cliente de SageMaker Runtime creado")
        
        # Verificar que el endpoint existe
        sm_client = session.client('sagemaker')
        try:
            endpoint_desc = sm_client.describe_endpoint(EndpointName=args.endpoint)
            endpoint_status = endpoint_desc['EndpointStatus']
            print(f"✓ Endpoint encontrado (Estado: {endpoint_status})")
            
            if endpoint_status != 'InService':
                print(f"⚠️  Advertencia: El endpoint no está en servicio (Estado: {endpoint_status})")
                response = input("¿Deseas continuar? (y/n): ")
                if response.lower() != 'y':
                    return 0
        except Exception as e:
            print(f"⚠️  No se pudo verificar el estado del endpoint: {e}")
            response = input("¿Deseas continuar de todos modos? (y/n): ")
            if response.lower() != 'y':
                return 0
                
    except Exception as e:
        print(f"❌ Error conectando a AWS: {e}")
        return 1
    
    # Procesar en lotes
    print(f"\n⚙️  Procesando transacciones...")
    all_results = []
    num_batches = (len(input_df) + args.batch_size - 1) // args.batch_size
    
    for i in range(0, len(input_df), args.batch_size):
        batch_num = (i // args.batch_size) + 1
        batch_df = input_df.iloc[i:i+args.batch_size]
        
        try:
            results_df = process_batch(runtime_client, args.endpoint, batch_df, batch_num)
            all_results.append(results_df)
            
        except Exception as e:
            print(f"    ❌ Error en lote {batch_num}: {e}")
            print(f"    Continuando con siguiente lote...")
            continue
    
    if not all_results:
        print("\n❌ No se procesaron resultados")
        return 1
    
    # Combinar resultados
    print(f"\n📊 Combinando resultados...")
    final_df = pd.concat(all_results, ignore_index=True)
    print(f"✓ {len(final_df)} resultados procesados")
    
    # Agregar columna metadata para similarity matching
    print(f"\n🏷️  Creando columna metadata...")
    final_df['metadata'] = create_metadata_column(final_df)
    print(f"✓ Columna metadata creada")
    
    # Agregar statusWarning si no existe (requerido por similarity matcher)
    if 'statusWarning' not in final_df.columns:
        # Mapear risk_decision o crear campo vacío
        if 'risk_decision' in final_df.columns:
            final_df['statusWarning'] = final_df['risk_decision']
        else:
            final_df['statusWarning'] = ''
        print(f"✓ Columna statusWarning creada")
    
    # Guardar resultados
    print(f"\n💾 Guardando resultados en {args.output}...")
    try:
        # Crear directorio si no existe
        output_dir = os.path.dirname(args.output)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        final_df.to_csv(args.output, index=False)
        print(f"✓ Resultados guardados ({len(final_df)} filas, {len(final_df.columns)} columnas)")
        
        # Mostrar muestra de resultados
        print(f"\n📋 Muestra de columnas en el resultado:")
        print(f"   {list(final_df.columns[:15])}")
        if len(final_df.columns) > 15:
            print(f"   ... y {len(final_df.columns) - 15} columnas más")
        
    except Exception as e:
        print(f"❌ Error guardando resultados: {e}")
        return 1
    
    print("\n" + "=" * 70)
    print("✅ Procesamiento completado exitosamente")
    print("=" * 70)
    print(f"Archivo de salida: {args.output}")
    print(f"Total procesado: {len(final_df)} transacciones")
    print()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
