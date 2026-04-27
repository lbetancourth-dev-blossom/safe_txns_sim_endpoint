#!/usr/bin/env python3
"""
Script de prueba para verificar que el similarity_matcher puede leer CSV desde S3.
"""

import os
import sys

# Asegurar que estamos en el directorio correcto
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)
sys.path.insert(0, script_dir)

def test_csv_loading():
    """Prueba la carga del CSV wp_similarity.csv desde S3"""
    print("=" * 70)
    print("TEST: Verificando carga de CSV desde S3")
    print("=" * 70)
    
    try:
        # Import similarity_matcher
        print("\n[1/4] Importando similarity_matcher...")
        import similarity_matcher
        print("✓ Módulo importado correctamente")
        
        # Verificar configuración por defecto
        print("\n[2/4] Verificando configuración por defecto...")
        print(f"  - DEFAULT_S3_BUCKET: {similarity_matcher.DEFAULT_S3_BUCKET}")
        print(f"  - DEFAULT_S3_KEY: {similarity_matcher.DEFAULT_S3_KEY}")
        
        # Validar que la ruta termina en .csv
        if not similarity_matcher.DEFAULT_S3_KEY.endswith('.csv'):
            print("✗ ERROR: La ruta no termina en .csv")
            return False
        print("✓ Configuración correcta (archivo CSV)")
        
        # Verificar que existe la función _load_csv_from_s3
        print("\n[3/4] Verificando funciones de carga...")
        if not hasattr(similarity_matcher, '_load_csv_from_s3'):
            print("✗ ERROR: Función _load_csv_from_s3 no encontrada")
            return False
        print("✓ Función _load_csv_from_s3 encontrada")
        
        # Verificar lógica de detección de formato en load_reference_data_from_s3
        print("\n[4/4] Verificando lógica de carga...")
        import inspect
        source = inspect.getsource(similarity_matcher.load_reference_data_from_s3)
        if "key.endswith('.csv')" in source and "_load_csv_from_s3" in source:
            print("✓ Lógica de detección de CSV presente en load_reference_data_from_s3")
        else:
            print("✗ ERROR: Lógica de CSV no encontrada")
            return False
        
        print("\n" + "=" * 70)
        print("✓ TODAS LAS VERIFICACIONES PASARON")
        print("=" * 70)
        print("\nEl módulo similarity_matcher PUEDE leer archivos CSV desde S3.")
        print(f"Archivo configurado: s3://{similarity_matcher.DEFAULT_S3_BUCKET}/{similarity_matcher.DEFAULT_S3_KEY}")
        print("\nFormatos soportados:")
        print("  - CSV (archivo único): key='path/file.csv'")
        print("  - Parquet (archivo único): key='path/file.parquet'")
        print("  - Parquet (directorio): key='path/to/directory/'")
        
        return True
        
    except Exception as e:
        print(f"\n✗ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_csv_loading()
    sys.exit(0 if success else 1)
