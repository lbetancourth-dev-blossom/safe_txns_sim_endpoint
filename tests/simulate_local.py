#!/usr/bin/env python3
"""
Simulación local del endpoint. 

NOTA: Requiere scikit-learn==1.2.1 (misma versión del contenedor SageMaker).
  pip install scikit-learn==1.2.1

Para correr con el endpoint real desplegado:
  python tests/process_endpoint.py --input data/test_escenarios.csv \
    --output data/test_escenarios_results.csv

Para correr esta simulación local:
  pip install scikit-learn==1.2.1
  python tests/simulate_local.py
"""
import sys
import os
import pandas as pd
import io
import warnings

# Verificar versión sklearn
try:
    import sklearn
    version = sklearn.__version__
    if not version.startswith('1.2'):
        print(f"⚠️  WARNING: sklearn {version} detectada.")
        print(f"   El preprocessing_pipeline.joblib fue guardado con sklearn 1.2.1")
        print(f"   Instala la versión correcta: pip install scikit-learn==1.2.1")
        print(f"   Continuando (puede fallar)...\n")
    else:
        print(f"✅ sklearn {version} — versión compatible")
except ImportError:
    print("❌ scikit-learn no instalado")
    sys.exit(1)

warnings.filterwarnings('ignore')

# Paths
MODEL_DIR = os.path.join(os.path.dirname(__file__), '..', 'temp_artifacts')
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')

# Si no existe temp_artifacts, descargar del tarball
if not os.path.exists(os.path.join(MODEL_DIR, 'kmeans_model.joblib')):
    tarball = os.path.join(os.path.dirname(__file__), '..', 'model_with_exact_matching.tar.gz')
    if os.path.exists(tarball):
        import tarfile
        os.makedirs(MODEL_DIR, exist_ok=True)
        print(f"📦 Extrayendo modelo desde tarball...")
        with tarfile.open(tarball, 'r:gz') as tar:
            tar.extractall(MODEL_DIR)
        print(f"✅ Modelo extraído a {MODEL_DIR}\n")
    else:
        print(f"❌ No se encontró modelo en {MODEL_DIR} ni tarball")
        print(f"   Corre primero: python deploy/deploy_final.py")
        sys.exit(1)

sys.path.insert(0, MODEL_DIR)

from inference_rules import model_fn, input_fn, predict_fn

print("🚀 Loading model...")
model = model_fn(MODEL_DIR)
print("✅ Model loaded\n")

csv_path = os.path.join(DATA_DIR, 'test_escenarios.csv')
print(f"📖 Reading {csv_path}...")
df = pd.read_csv(csv_path, index_col=0)
print(f"✅ Loaded {len(df)} rows\n")

results = []
print("="*100)
print("PROCESSING TRANSACTIONS")
print("="*100)

for idx, row in df.iterrows():
    txn_id = int(row.get('TransactionID', idx))
    user_id = int(row.get('idOLBUserTxns', 0))
    created_at = row.get('createdAtTxns', '')

    print(f"\n[{idx}] TxnID={txn_id} | User={user_id} | {created_at}")

    try:
        csv_buffer = io.StringIO()
        csv_buffer.write(','.join(str(c) for c in row.index) + '\n')
        csv_buffer.write(','.join(str(v) for v in row.values) + '\n')
        csv_data = csv_buffer.getvalue()

        features = input_fn(csv_data, 'text/csv')
        predictions = predict_fn(features, model)

        result = {
            'TransactionID': txn_id,
            'idOLBUser': user_id,
            'createdAt': created_at,
            'decision': predictions.get('decision'),
            'score': round(float(predictions.get('score', 0)), 4) if predictions.get('score') is not None else None,
            'kmeans_cluster': predictions.get('kmeans_cluster'),
            'sim_match_txn_id': predictions.get('sim_match_txn_id'),
            'sim_score': round(float(predictions.get('sim_score', 0)), 4) if predictions.get('sim_score') is not None else None,
            'sim_status': predictions.get('sim_status'),
            'sim_decision': predictions.get('sim_decision'),
        }
        results.append(result)

        score_str = f"{result['score']}" if result['score'] is not None else "N/A"
        sim_str = f"Match={result['sim_match_txn_id']} (s={result['sim_score']})" if result.get('sim_match_txn_id') else "No sim"
        print(f"  ✅ {result['decision']:15s} | Score={score_str} | Cluster={result['kmeans_cluster']} | {sim_str}")

    except Exception as e:
        import traceback
        print(f"  ❌ {type(e).__name__}: {str(e)[:100]}")
        result = {'TransactionID': txn_id, 'idOLBUser': user_id, 'createdAt': created_at, 'error': str(e)[:150]}
        results.append(result)

results_df = pd.DataFrame(results)
output = os.path.join(DATA_DIR, 'test_escenarios_results.csv')
results_df.to_csv(output, index=False)

print("\n" + "="*100)
print(f"✅ Saved to {output}")
print(f"Successful: {sum(1 for r in results if 'error' not in r)}/{len(results)}")

if 'decision' in results_df.columns:
    print("\nDecision breakdown:")
    for d, c in results_df['decision'].value_counts().items():
        print(f"  {d}: {c}")

sim_count = sum(1 for r in results if r.get('sim_match_txn_id'))
print(f"\nSimilarity matches: {sim_count}/{len(results)}")

print("\n✅ SIMULATION COMPLETE")

