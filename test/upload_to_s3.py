#!/usr/bin/env python3
"""
Script para subir wp_similarity.csv a S3 para uso con similarity matching.

Uso:
    python upload_to_s3.py --file data/wp_similarity.csv
"""

import boto3
import argparse
import os
import sys

def main():
    parser = argparse.ArgumentParser(description='Subir archivo a S3')
    parser.add_argument('--file', default='data/wp_similarity.csv', help='Archivo a subir')
    parser.add_argument('--bucket', default='blossom-analytics-safe-dev-nv', help='Bucket de S3')
    parser.add_argument('--key', default='safe_txns/similarity/data/wp_similarity.csv', help='Key en S3')
    parser.add_argument('--profile', default='blossom-dev', help='Perfil de AWS')
    parser.add_argument('--region', default='us-east-1', help='Región de AWS')
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("📤 Subir archivo a S3")
    print("=" * 70)
    print(f"Archivo local: {args.file}")
    print(f"Destino S3:    s3://{args.bucket}/{args.key}")
    print(f"Perfil AWS:    {args.profile}")
    print("=" * 70)
    
    # Verificar que existe el archivo
    if not os.path.exists(args.file):
        print(f"❌ Error: Archivo no encontrado: {args.file}")
        return 1
    
    # Obtener tamaño del archivo
    file_size = os.path.getsize(args.file)
    print(f"\n📊 Tamaño del archivo: {file_size / 1024:.2f} KB")
    
    # Crear cliente S3
    try:
        session = boto3.Session(profile_name=args.profile, region_name=args.region)
        s3_client = session.client('s3')
        print(f"✓ Cliente S3 creado")
    except Exception as e:
        print(f"❌ Error conectando a AWS: {e}")
        return 1
    
    # Confirmar subida
    response = input(f"\n¿Deseas subir el archivo a S3? (y/n): ")
    if response.lower() != 'y':
        print("Operación cancelada")
        return 0
    
    # Subir archivo
    print(f"\n⬆️  Subiendo archivo a S3...")
    try:
        s3_client.upload_file(args.file, args.bucket, args.key)
        print(f"✓ Archivo subido exitosamente")
        
        # Verificar que se subió
        try:
            response = s3_client.head_object(Bucket=args.bucket, Key=args.key)
            s3_size = response['ContentLength']
            print(f"✓ Verificado en S3 ({s3_size / 1024:.2f} KB)")
        except Exception as e:
            print(f"⚠️  No se pudo verificar: {e}")
        
        print(f"\n" + "=" * 70)
        print(f"✅ Archivo disponible en S3")
        print(f"=" * 70)
        print(f"URI: s3://{args.bucket}/{args.key}")
        print(f"\nPuedes usar este archivo con similarity_matcher:")
        print(f"  s3_uri='s3://{args.bucket}/{args.key}'")
        print()
        
    except Exception as e:
        print(f"❌ Error subiendo archivo: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
